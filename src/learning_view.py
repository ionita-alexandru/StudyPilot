"""Parcours lisible et traçabilité du guide publié, sans nouvel appel IA."""
from src.course_documents import combined_guide as load_guide
from src.courses.card_presentation import render_text
from src.courses.study_guide import symbol_name


def learning_view(course, plan):
    from src.courses import service
    from src.storage.repository import read_json, StorageError
    guide = load_guide(course, plan) or {}
    reports = []
    for path in (service._repository().paths(course['course_id']).root/'feedback').glob('*.json'):
        try:
            report=read_json(path)
            if report.get('revision')==guide.get('revision') and report.get('status')=='open':
                reports.append(report)
        except StorageError:
            continue
    entries = guide.get('entries', [])
    sources = {s['id']:s for s in guide.get('sources', [])}
    def first_page(entry):
        return min((p for sid in entry['source_ids'] if sid in sources
                    for p in sources[sid].get('pages',[sources[sid]['page']])),default=0)
    cores = [e for part in plan['parts'] for e in sorted(
        (e for e in entries if e['role']=='core' and not e.get('optional') and e['part_id']==part['id']),key=lambda e:(bool(e.get('document_id')),first_page(e)))]
    cores.sort(key=lambda e:bool(e.get('document_id')))
    states = {p['part_id']:p for p in guide.get('parts', [])}
    decisions = {d.get('source_id') or d.get('card_id'):d for d in guide.get('decisions', [])}
    names = {}
    for e in cores:
        for name in [e['title'], *e.get('aliases', [])]:
            names.setdefault(name.strip().casefold(), []).append(e['id'])
    result = []
    for e in cores:
        part = next(p for p in plan['parts'] if p['id']==e['part_id'])
        prerequisites = e.get('prerequisites') or part.get('overview', {}).get('prerequisites', [])
        links = []
        for name in prerequisites:
            matches = [i for i in names.get(name.strip().casefold(), []) if i != e['id']]
            links.append(dict(title=name, id=matches[0] if len(matches)==1 else None))
        result.append(dict(e, html=render_text(e['body']), part_number=part['number'], part_title=e.get('document_title',part['title']),
            symbols=[dict(s,name=symbol_name(s['name'])) for s in e.get('symbols',[])],
            prerequisites_view=links, sources=[sources[i] for i in e['source_ids'] if i in sources],
            resources=[dict(r,html=render_text(r['body'])) for r in entries if e['id'] in r.get('targets', []) and r.get('document_role')!='correction'],
            feedback=[r for r in reports if r.get('card_id')==e['id']]))
    coverage = []
    for sid,s in sources.items():
        destinations = [e for e in entries if sid in e['source_ids']]
        status = 'Rattaché' if destinations else 'Écarté avec motif' if sid in decisions else 'À vérifier'
        if s.get('has_visual_content'):
            status = 'Texte rattaché · visuel à vérifier' if destinations else 'Visuel à vérifier'
        coverage.append(dict(s, destinations=destinations, reason=decisions.get(sid,{}).get('reason',''),
            status=status))
    return dict(entries=result, coverage=coverage, objectives=guide.get('objectives',[]), states=states, revision=guide.get('revision'),
                origin=guide.get('origin'), has_unverified_visuals=any(s.get('has_visual_content') for s in sources.values()),
                incomplete=not guide or any(p.get('status')!='complete' for p in guide.get('parts', [])))
