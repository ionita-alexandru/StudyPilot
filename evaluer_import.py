"""Campagne réelle isolée : jamais de fiches relues ni de réponse IA simulée.

Usage : définir STUDYPILOT_DATA_DIR hors des données personnelles avant le
lancement, puis --corpus <dossier PDF> --output <rapport JSON> --live.
Les appels sont bornés ; un arrêt est un résultat incomplet, jamais un succès.
"""
import argparse
import json
import time
from pathlib import Path
from src.config import DATA_DIR, PROJECT_ROOT, COURSE_PDF_DIR, STUDY_MODEL
from src.upload_service import save_validated_pdf
from src.courses import service
from src.courses.study_guide import load_guide
from src.storage.repository import write_json_atomic, StorageError
from src.ai import client


class EvaluationBudgetExceeded(client.AIUsageLimitError):
    """Arrêt propre décidé par la campagne, distinct d'un refus du fournisseur."""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='Autorise les appels réels au fournisseur configuré.')
    parser.add_argument('--max-calls', type=int, default=60)
    parser.add_argument('--minutes', type=float, default=12)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--regenerate-cards', action='store_true', help='Réévaluer les consignes de rédaction sans modifier manuellement les fiches du corpus.')
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('--live est nécessaire : cette campagne appelle réellement le fournisseur IA.')
    if DATA_DIR == (PROJECT_ROOT / 'data').resolve():
        parser.error('Définir STUDYPILOT_DATA_DIR vers un espace isolé avant le lancement.')
    if args.max_calls < 1 or args.minutes <= 0:
        parser.error('Budgets strictement positifs requis.')
    cases = [p for p in sorted(args.corpus.glob('*.pdf')) if not p.stem.endswith('-texte')
             and (not args.only or p.stem in args.only)]
    if not cases:
        parser.error('Aucun PDF sélectionné.')
    report = {'model': STUDY_MODEL, 'data_dir': str(DATA_DIR), 'cases': [],
              'kind': 'real_model_new_synthetic_documents', 'editorial_cards': False}
    started = time.monotonic()
    calls = 0
    case_start = 0
    case_name = ''
    per_case = max(1, args.max_calls // len(cases))
    original_chat = client.chat

    def measured_chat(**kwargs):
        nonlocal calls
        if calls - case_start >= per_case:
            raise EvaluationBudgetExceeded('Budget du cas atteint ; résultats partiels conservés.')
        if calls >= args.max_calls or time.monotonic() - started > args.minutes * 60:
            raise EvaluationBudgetExceeded('Budget de campagne atteint ; résultats partiels conservés.')
        calls += 1
        print('CALL', calls, 'case', calls-case_start, flush=True)
        result = original_chat(**kwargs)
        # Diagnostic local du seul corpus synthétique, sans prompt ni clé.
        write_json_atomic(args.output.parent / (args.output.stem + '_responses') / f'{case_name}-{calls:03}.json',
                          {'response': result.message.content})
        return result

    # Les modules appellent des alias du client unique : instrumenter les alias
    # déjà chargés et le point client pour ceux qui seront chargés ensuite.
    import sys
    for module in list(sys.modules.values()):
        if getattr(module, '__name__', '').startswith('src.') and getattr(module, 'chat', None) is original_chat:
            module.chat = measured_chat
    client.chat = measured_chat
    specs = json.loads((PROJECT_ROOT / 'tests/fixtures/generalisation.json').read_text(encoding='utf-8'))
    for pdf in cases:
        before, tick = calls, time.monotonic()
        case_start = calls
        case_name = pdf.stem
        item = {'case': pdf.stem, 'status': 'error', 'cards': 0, 'topics': specs.get(pdf.stem, {}).get('topics', [])}
        cid = None
        try:
            import hashlib
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            cid = service.make_course_id(pdf.stem, digest)
            try:
                previous = service._repository().load_course(cid)
                stored, title = COURSE_PDF_DIR / previous['source_filename'], previous['title']
                if hashlib.sha256(stored.read_bytes()).hexdigest() != digest:
                    raise ValueError('PDF de reprise modifié.')
            except StorageError:
                with pdf.open('rb') as stream:
                    stored, title, _ = save_validated_pdf(stream, pdf.name)
            result = service.create_course(stored, title=title, original_filename=pdf.name, model=STUDY_MODEL,
                progress_callback=lambda done, total, part, state: print(pdf.stem, part, state, flush=True))
            if args.regenerate_cards and result['status'] == 'ready':
                from src.courses.guide_generation import build_guide
                result = build_guide(cid, model=STUDY_MODEL, force=True, max_calls=max(1, per_case-(calls-case_start)))
            item['status'] = result['status']
            item['incomplete'] = result['incomplete']
        except Exception as exc:
            # Pas de message fournisseur brut, de prompt ou de clé dans le rapport.
            item['error_type'] = type(exc).__name__
            if isinstance(exc, client.AIUsageLimitError):
                item['status'] = 'interrupted'
                item['stop_reason'] = 'evaluation_budget' if isinstance(exc, EvaluationBudgetExceeded) else 'provider'
        if cid:
            item['course_id'] = cid
            repo = service._repository()
            try:
                plan = repo.load_plan(cid)
                item['overviews'] = [p['overview'] for p in plan['parts']]
                guide = load_guide(service.load_course(cid), plan)
                if guide:
                    item['published'] = [e for e in guide['entries'] if e['role'] == 'core']
                    item['cards'] = len(item['published'])
                    item['resources'] = [e for e in guide['entries'] if e['role'] != 'core']
                    item['issues'] = [p for p in guide['parts'] if p['status'] != 'complete']
            except (StorageError, ValueError):
                pass
        item.update(calls=calls-before, call_budget=per_case, seconds=round(time.monotonic()-tick, 1))
        report['cases'].append(item)
        report.update(calls=calls, seconds=round(time.monotonic()-started, 1))
        write_json_atomic(args.output, report)
        print('RESULT', pdf.stem, item['status'], item['cards'], item['calls'], flush=True)
        if calls >= args.max_calls or time.monotonic() - started > args.minutes * 60:
            report['not_attempted'] = [p.stem for p in cases[len(report['cases']):]]
            write_json_atomic(args.output, report)
            break
    return 0 if len(report['cases']) == len(cases) and all(c['status'] == 'ready' and c['cards'] for c in report['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
