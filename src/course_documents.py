"""Compléments PDF : file unique, lots relus et sources distinctes du cours principal."""
from __future__ import annotations

import hashlib
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.courses import service
from src.courses.study_guide import load_guide, digest, sources_from_document, validate_draft
from src.storage.repository import read_json, write_json_atomic, StorageError
from src.config import COURSE_PDF_DIR, STUDY_MODEL

ROLES = {'td':'TD', 'exam':'Annale', 'correction':'Corrigé', 'article':'Article', 'course':'Complément de cours'}
SCOPES = {'required':'À apprendre', 'practice':'Entraînement', 'optional':'Approfondissement'}
_LOCK = threading.RLock()
_PENDING = set()


def _path(course_id, identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', str(identifier)):
        raise ValueError('Identifiant de document invalide.')
    return service._repository().paths(course_id).root / 'documents' / (identifier + '.json')


def records(course_id):
    result = []
    for path in (service._repository().paths(course_id).root / 'documents').glob('*.json'):
        try:
            item = read_json(path)
            if re.fullmatch(r'[a-f0-9]{32}', item.get('id', '')):
                result.append(item)
        except StorageError:
            continue
    return sorted(result, key=lambda d:d.get('created_at',''))


def public(item):
    keys = ('id','title','role','scope','status','page_count','error','completed_batches','total_batches','created_at','file_hash')
    result = {k:item.get(k) for k in keys}
    result.update(role_label=ROLES[item['role']], scope_label=SCOPES[item['scope']], entry_count=len(item.get('entries', [])),
                  pdf_url=f"/course/{item['course_id']}/document/{item['id']}/pdf")
    return result


def load(course_id, identifier):
    return read_json(_path(course_id, identifier))


def listing(course_id):
    items = records(course_id)
    return dict(documents=[public(d) for d in items], revision=digest([(d['id'],d.get('revision'),d['scope']) for d in items]))


def _update(course_id, identifier, **changes):
    with _LOCK:
        path = _path(course_id, identifier)
        item = read_json(path)
        item.update(changes)
        write_json_atomic(path, item)
        return item


def enqueue(course_id, stream, filename, role, scope):
    from src.upload_service import save_validated_pdf, _EXECUTOR, UploadError
    if role not in ROLES or scope not in SCOPES:
        raise ValueError('Choisis le rôle du document et sa place dans la révision.')
    course=service.load_course(course_id)
    with _LOCK:
        if len(_PENDING) >= 3:
            raise UploadError('Trois compléments sont déjà en attente. Attends la fin d’un traitement.')
    stored, title, pages = save_validated_pdf(stream, filename)
    fingerprint = hashlib.sha256(stored.read_bytes()).hexdigest()
    with _LOCK:
        if fingerprint == course['file_hash'] or any(d['file_hash'] == fingerprint for d in records(course_id)):
            stored.unlink(missing_ok=True)
            raise ValueError('Ce PDF est déjà rattaché à ce cours. Modifie son rôle si nécessaire.')
        if len(_PENDING)>=3:
            stored.unlink(missing_ok=True)
            raise UploadError('La file des compléments est pleine. Réessaie après un traitement.')
        identifier = uuid.uuid4().hex
        item = dict(id=identifier, course_id=course_id, title=title, filename=stored.name, file_hash=fingerprint,
                    page_count=pages, role=role, scope=scope, status='queued', entries=[], sources=[], batches={},
                    completed_batches=0, total_batches=0, error=None, created_at=datetime.now(timezone.utc).isoformat())
        write_json_atomic(_path(course_id,identifier),item)
        _PENDING.add((course_id,identifier))
    try:
        _EXECUTOR.submit(_run,course_id,identifier)
    except Exception:
        _PENDING.discard((course_id,identifier));_update(course_id,identifier,status='interrupted',error='Traitement à reprendre.')
        raise
    return public(item)


def resume(course_id, identifier):
    from src.upload_service import _EXECUTOR
    with _LOCK:
        item = load(course_id,identifier)
        if item['status'] not in {'partial','error','interrupted'} or (course_id,identifier) in _PENDING:
            raise ValueError('Ce document est terminé ou déjà en cours.')
        if len(_PENDING) >= 3:
            raise ValueError('La file des compléments est pleine.')
        _PENDING.add((course_id,identifier));_update(course_id,identifier,status='queued',error=None)
    try:
        _EXECUTOR.submit(_run,course_id,identifier)
    except Exception:
        with _LOCK:_PENDING.discard((course_id,identifier))
        _update(course_id,identifier,status='interrupted',error='Traitement à reprendre.')
        raise


def change(course_id, identifier, role, scope):
    if role not in ROLES or scope not in SCOPES:
        raise ValueError('Rôle ou périmètre invalide.')
    with _LOCK:
        item=load(course_id,identifier)
        if (course_id,identifier) in _PENDING:
            raise ValueError('Attends la fin du traitement pour modifier le rôle.')
        # Changer le rôle nécessite une nouvelle relecture, le périmètre seul est immédiat.
        changes=dict(role=role,scope=scope)
        if role != item['role']:
            changes.update(status='interrupted',batches={},entries=[],revision=None,error='Rôle modifié : reprends la préparation.')
        return public(_update(course_id,identifier,**changes))


def _run(course_id, identifier):
    from src.courses.planner import extract_document
    from src.courses.guide_generation import generate_batch, batches, Budget
    try:
        course=service.load_course(course_id);plan=service.load_course_plan(course)
        guide=load_guide(course,plan) or {}
        if not guide or not plan or not plan.get('parts'):
            raise ValueError('Prépare le cours principal avant ses compléments.')
        item=_update(course_id,identifier,status='processing',error=None)
        sources=item.get('sources')
        if not sources:
            document=extract_document(COURSE_PDF_DIR/item['filename'])
            sources=[dict(s,id=identifier+'-'+s['id'],document_id=identifier) for s in sources_from_document(document)]
            _update(course_id,identifier,sources=sources)
        if not sources:
            raise ValueError('Aucun passage exploitable : consulte le PDF original.')
        chunks=list(batches(sources));budget=Budget(max_calls=8)
        cache=item.get('batches',{}) if item.get('base_revision')==guide.get('revision') else {}
        entries=[]
        base=[dict(id=e['id'],title=e['title'],objective=e['objective']) for e in guide.get('entries',[]) if e['role']=='core']
        _update(course_id,identifier,total_batches=len(chunks),base_revision=guide.get('revision'))
        for index,chunk in enumerate(chunks):
            existing=base+[dict(id=e['id'],title=e['title'],objective=e['objective']) for e in entries if e['role']=='core']
            key=str(index)
            if key not in cache:
                # Le rôle est une donnée pédagogique, pas une consigne issue du PDF.
                marked=[dict(s,text=f"Document : {ROLES[item['role']]}. Les corrigés restent des ressources à la demande.\n"+s['text']) for s in chunk]
                draft,review=generate_batch(marked,existing,model=STUDY_MODEL,budget=budget)
                cache[key]=dict(draft=draft.model_dump(mode='json'),review=review)
            draft=validate_draft(cache[key]['draft'],chunk,[e['id'] for e in existing])
            ids={e.key:'doc-'+digest([identifier,index,e.key])[:20] for e in draft.entries}
            for e in draft.entries:
                targets=[ids.get(t,t) for t in e.targets]
                target=next((x for x in guide.get('entries',[]) if x['id'] in targets),None)
                entries.append(e.model_dump(mode='json')|dict(id=ids[e.key],targets=targets,
                    part_id=target['part_id'] if target else plan['parts'][0]['id'],document_id=identifier))
            _update(course_id,identifier,entries=entries,batches=cache,completed_batches=index+1,
                    revision=digest([item['file_hash'],entries]))
        _update(course_id,identifier,status='ready',error=None)
    except Exception as error:
        from src.ai.client import AIUsageLimitError
        item=load(course_id,identifier)
        message=str(error)[:450] if isinstance(error,(ValueError,AIUsageLimitError)) else 'La préparation a été interrompue. Le PDF et les lots terminés sont conservés.'
        _update(course_id,identifier,status='partial' if item.get('entries') else 'interrupted',error=message)
    finally:
        with _LOCK:_PENDING.discard((course_id,identifier))


def recover():
    for course_id in service._repository().list_course_ids():
        for item in records(course_id):
            if item['status'] in {'queued','processing'}:
                _update(course_id,item['id'],status='interrupted',error='Serveur redémarré : reprends la préparation.')


def combined_guide(course, plan):
    guide=load_guide(course,plan)
    if not guide:return None
    entries=list(guide['entries']);sources=list(guide['sources'])
    documents=records(course['course_id'])
    for item in documents:
        if item['status'] not in {'ready','partial'}:continue
        sources.extend(dict(s,document_id=item['id'],document_title=item['title'],document_role=item['role'],
                            pdf_url=public(item)['pdf_url']) for s in item.get('sources',[]))
        for e in item.get('entries',[]):
            optional=item['scope']!='required' or item['role']=='correction'
            entries.append(dict(e,optional=optional,document_role=item['role'],document_title=item['title'],pdf_url=public(item)['pdf_url']))
    revision=digest([guide['revision'],[(d['id'],d.get('revision'),d['scope'],d['role']) for d in documents]])
    return dict(guide,entries=entries,sources=sources,revision=revision,base_revision=guide['revision'])
