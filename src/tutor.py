"""Contexte documentaire partagé du chat, sans relecture du PDF à chaque tour."""
from __future__ import annotations

from contextlib import contextmanager
import re
import threading
import time
import uuid

from src.courses.study_guide import load_guide, digest, resource_view, sources_from_document
from src.courses.card_presentation import render_text
from src.storage.repository import read_json, write_json_atomic, StorageError

INTENTS = {'question', 'example', 'explain', 'exercise', 'hint', 'solution', 'assess', 'discover', 'prerequisite'}
_LOCK = threading.Lock()
_SESSIONS = {}
_DOCUMENT_LOCK = threading.Lock()


def session_path(course, identifier):
    from src.courses import service
    root = service._repository().paths(course['course_id']).root
    return root / 'conversations' / (str(uuid.UUID(identifier)) + '.json')


@contextmanager
def conversation(course, plan, conversation_id=None, card_id=None):
    """Une seule réponse par conversation ; historique lié au cours et à sa version."""
    from src.courses.study_guide import plan_version
    if conversation_id:
        try:
            uuid.UUID(conversation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Conversation invalide.')
    identifier = conversation_id or str(uuid.uuid4())
    guide = load_guide(course, plan)
    version = guide['revision'] if guide else digest([course['file_hash'], plan_version(plan)])
    with _LOCK:
        now = time.monotonic()
        for key in list(_SESSIONS):
            if not _SESSIONS[key]['busy'] and now - _SESSIONS[key]['updated'] > 3600:
                del _SESSIONS[key]
        state = _SESSIONS.get(identifier)
        if state is None and conversation_id:
            try:
                saved = read_json(session_path(course, identifier))
                state = dict(saved, busy=False, updated=now)
                _SESSIONS[identifier] = state
            except StorageError:
                pass
        if state and state['course_id'] != course['course_id']:
            raise ValueError('Cette conversation appartient à un autre cours.')
        if state and state['busy']:
            raise RuntimeError('Une réponse est déjà en cours dans cette conversation.')
        if state is None or state['version'] != version:
            state = dict(id=identifier, course_id=course['course_id'], version=version, card_id=None,
                         history=[], exercise=None, busy=False, updated=now)
            _SESSIONS[identifier] = state
        if len(_SESSIONS) > 200:
            for key in sorted(_SESSIONS, key=lambda k: _SESSIONS[k]['updated']):
                if key != identifier and not _SESSIONS[key]['busy']:
                    del _SESSIONS[key]
                    break
        if card_id is not None and card_id != state['card_id']:
            state['card_id'] = card_id or None
            state['history'] = []
            state['exercise'] = None
        state['busy'] = True
    try:
        yield state, guide
    finally:
        with _LOCK:
            state['busy'] = False
            state['updated'] = time.monotonic()
            path = session_path(course, identifier)
            if path.parent.parent.exists():
                write_json_atomic(path, {k: v for k, v in state.items() if k not in {'busy', 'updated'}})


def document_sources(course):
    from src.courses import service
    from src.courses.planner import extract_document
    from src.config import COURSE_PDF_DIR
    path = service._repository().paths(course['course_id']).root / 'document_sources.json'
    with _DOCUMENT_LOCK:
        try:
            cache = read_json(path)
        except StorageError:
            cache = {}
        if cache.get('file_hash') != course['file_hash']:
            cache = dict(file_hash=course['file_hash'], sources=sources_from_document(
                extract_document(COURSE_PDF_DIR / course['source_filename'])))
            write_json_atomic(path, cache)
    return cache['sources']


def terms(text):
    from src.part_study import _normalized
    stop = {'pour', 'dans', 'avec', 'cette', 'celui', 'cela', 'cours', 'exemple', 'donne', 'explique', 'pourquoi', 'comment'}
    return set(re.findall(r'[\w-]{3,}', _normalized(text))) - stop


def context_for(course, plan, part, question, state, guide, *, allow_switch=True):
    entries = guide['entries'] if guide else []
    active = next((e for e in entries if e['id'] == state.get('card_id')), None)
    if state.get('card_id') and active is None:
        # Les collections anciennes restent consultables tant qu'elles ne sont pas migrées.
        from src.courses import service
        legacy = [c for p in plan['parts'] for c in service.load_part_cards(course, p['id'])]
        card = next((c for c in legacy if c['card_id'] == state['card_id']), None)
        if not card:
            raise ValueError('Fiche introuvable dans la version actuelle du cours.')
        active = dict(id=card['card_id'], title=card['title'], part_id=card['primary_part_id'],
                      role='core', body='\n\n'.join(s['content'] for s in card['sections']), source_ids=[])
    sources = guide['sources'] if guide else document_sources(course)
    if guide and guide.get('origin') == 'editorial_review':
        # Les anciennes fiches apportent un contexte relu, mais le chat peut aussi
        # consulter le document original, y compris les passages hors des fiches.
        sources = sources + document_sources(course)
    query = terms(question)
    # Un nom de notion explicite peut remplacer la sélection ; les pronoms seuls la conservent.
    candidates = [(len(query & terms(e['title'] + ' ' + ' '.join(e.get('aliases', [])))), e)
                  for e in entries if e['role'] == 'core']
    candidates.sort(key=lambda pair: -pair[0])
    current_score = len(query & terms(active['title'] + ' ' + ' '.join(active.get('aliases', [])))) if active else 0
    if (allow_switch and candidates and candidates[0][0] > current_score and candidates[0][0] > 0
            and (len(candidates) == 1 or candidates[0][0] > candidates[1][0])):
        active = candidates[0][1]
        state['card_id'] = active['id']
    if active and active['part_id'] != part['id']:
        part = next(p for p in plan['parts'] if p['id'] == active['part_id'])
    # Référence explicite sélectionnée par l'interface. L'historique conserve ensuite ce sujet.
    linked = set(active['source_ids']) if active else set()
    if active and active['role'] != 'core':
        parents = set(active.get('targets', []))
        linked |= {sid for e in entries if e['id'] in parents for sid in e['source_ids']}
    matched = sorted(entries, key=lambda e: -len(query & terms(e['title'] + ' ' + ' '.join(e.get('aliases', [])))))
    for e in matched[:3]:
        if query & terms(e['title'] + ' ' + ' '.join(e.get('aliases', []))):
            linked.update(e['source_ids'])
    ranked = sorted(sources, key=lambda s: (
        -(100 if s['id'] in linked else 0) - len(query & terms(s['text'])) * 3
        - (1 if part['page_start'] <= s['page'] <= part['page_end'] else 0), s['page']))
    contexts, size = [], 0
    for source in ranked:
        if source['id'] not in linked and not (query & terms(source['text'])):
            continue
        if size + len(source['text']) > 10500:
            continue
        contexts.append(dict(source_id=source['id'], page=source['page'], content=source['text'],
                             origin=source.get('origin', 'pdf'), source_pages=source.get('pages', [source['page']])))
        size += len(source['text'])
        if len(contexts) >= 7:
            break
    return active, part, contexts


def saved_example(active, guide):
    if not active or not guide:
        return None
    entry = next((e for e in guide['entries'] if e['role'] == 'example' and active['id'] in e.get('targets', [])), None)
    if not entry:
        return None
    resource = resource_view(entry, guide)
    return dict(answer='### ' + entry['title'] + '\n\n' + entry['body'], pages=resource['pages'],
                source='saved_resource', resource_id=entry['id'])


def answer(course, plan, part, question, *, card_id=None, conversation_id=None, intent='question', model):
    from src.part_study import answer_part_question, build_course_outline_context
    if intent not in INTENTS:
        raise ValueError('Action de discussion inconnue.')
    with conversation(course, plan, conversation_id, card_id) as (state, guide):
        active, actual_part, contexts = context_for(course, plan, part, question, state, guide,
            allow_switch=not state.get('exercise') and intent not in {'hint', 'solution', 'assess'})
        cached = saved_example(active, guide) if intent == 'example' else None
        if intent in {'exercise', 'hint', 'solution', 'assess'}:
            from src.learning_tutor import exercise_action
            from src.ai.workload import interactive
            with interactive():
                result = exercise_action(state, active, contexts, intent, question, model)
            result['pages'] = sorted({p for c in contexts for p in c['source_pages']})
        elif cached:
            result = cached
        else:
            from src.ai.workload import interactive
            with interactive():
                response = answer_part_question(question, contexts, model, course_title=course['title'], part=actual_part,
                    course_outline=build_course_outline_context(plan), history=state['history'], course_overview=True,
                    active_card=active, intent=intent, exercise=public_exercise(state.get('exercise')))
            result = dict(answer=response, pages=sorted({p for c in contexts for p in c['source_pages']}), source='model')
        from src.study_checks import verify_response
        result['answer'], checks = verify_response(result['answer'])
        state['history'] = (state['history'] + [dict(role='user', content=question),
                                              dict(role='assistant', content=result['answer'])])[-8:]
        return result | dict(answer_html=render_text(result['answer']), conversation_id=state['id'],
                             active_card_id=state['card_id'], active_title=active['title'] if active else None,
                             version=state['version'], scope='course_context', checks=checks,
                             exercise=public_exercise(state.get('exercise')))


def public_exercise(exercise):
    if not exercise:
        return None
    return {key: exercise[key] for key in ('id', 'title', 'statement', 'card_id', 'assisted', 'attempts')} | dict(statement_html=render_text(exercise['statement']))


def restore(course, plan, identifier):
    with conversation(course, plan, identifier) as (state, guide):
        active = next((e for e in (guide or {}).get('entries', []) if e['id'] == state['card_id']), None)
        return dict(conversation_id=state['id'], active_card_id=state['card_id'],
                    active_title=active['title'] if active else None,
                    exercise=public_exercise(state.get('exercise')),
                    history=[dict(m, html=render_text(m['content']) if m['role']=='assistant' else None) for m in state['history']])
