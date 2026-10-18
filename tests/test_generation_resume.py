"""Régressions des sauvegardes fines et de la distinction panne/quota."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.ai.client import AITransientError, AIUsageLimitError, AIInputTooLargeError
from src.courses import learning_material as lm, pedagogy
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, notion, inventory, page, fact, MODEL, SHA, PLAN
import manage


class RecoveryCheckpoints(unittest.TestCase):
    def sources(self):
        return [{'ref': f'u{i}', 'page': i + 1, 'heading': 'Notion',
                 'lines': [{'id': 1, 'text': f'Enseignement {i}.\n'}]} for i in range(2)]

    def test_interruption_in_second_audit_resumes_only_that_audit_from_disk(self):
        for failure in (AITransientError, AIInputTooLargeError):
            with self.subTest(failure=failure), TemporaryDirectory() as folder:
                path = Path(folder) / 'checkpoint.json'
                cache = {}; calls = []; interrupted = True
                def save():
                    path.write_text(json.dumps(cache), encoding='utf-8')
                def call(schema, prompt, payload, model, validate):
                    calls.append(schema.__name__)
                    if schema is lm.EvidenceRecovery:
                        return validate(lm.EvidenceRecovery(selections=[lm.SourceSelection(
                            source_ref=s['ref'], start_line=1, end_line=1, kind='explanation')
                            for s in payload['sources']], reason='Deux passages'))
                    self.assertIn('selection', next(iter(cache.values())))
                    if payload['additions'][0]['page'] == 2 and interrupted:
                        raise failure('Interruption du second audit')
                    return validate(lm.EvidenceScope(verdict='about_this_notion', reason='Source vérifiée'))
                c = SimpleNamespace(concept_id='c', title='Notion')
                with patch.object(lm, 'source_candidates', return_value=self.sources()):
                    with self.assertRaises(failure):
                        lm.recover(c, [], {}, 'm', call, checkpoints=cache, save=save)
                    self.assertEqual(calls, ['EvidenceRecovery', 'EvidenceScope', 'EvidenceScope'])
                    cache = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(len(next(iter(cache.values()))['audits']), 1)
                    interrupted = False; calls.clear()
                    result = lm.recover(c, [], {}, 'm', call, checkpoints=cache, save=save)
                    self.assertEqual(calls, ['EvidenceScope'])
                    self.assertEqual(len(result['points']), 2)

    def test_line_repair_is_saved_before_failed_audit(self):
        cache = {}; calls = []; broken = True
        def call(schema, prompt, payload, model, validate):
            calls.append(schema.__name__)
            if schema is lm.EvidenceRecovery:
                return validate(lm.EvidenceRecovery(selections=[lm.SourceSelection(
                    source_ref='u0', start_line=9, end_line=9, kind='explanation')], reason='Passage'))
            if schema.__name__ == 'SelectionRepair':
                return validate(schema(start_line=1, end_line=1))
            if broken:
                raise AITransientError('503')
            return validate(lm.EvidenceScope(verdict='about_this_notion', reason='Source vérifiée'))
        with patch.object(lm, 'source_candidates', return_value=self.sources()[:1]):
            c = SimpleNamespace(concept_id='c', title='Notion')
            with self.assertRaises(AITransientError):
                lm.recover(c, [], {}, 'm', call, checkpoints=cache)
            cache = json.loads(json.dumps(cache)); broken = False; calls.clear()
            result = lm.recover(c, [], {}, 'm', call, checkpoints=cache)
            self.assertEqual(calls, ['EvidenceScope'])
            self.assertEqual(result['points'][0]['quote'], 'Enseignement 0.\n')

    def test_split_is_remembered_and_foreign_reference_rejected(self):
        cache = {}; seen = []
        def call(schema, prompt, payload, model, validate):
            refs = [s['ref'] for s in payload['sources']]; seen.append(refs)
            if len(refs) > 1:
                raise AIInputTooLargeError('Trop volumineux')
            if refs == ['u1']:
                # u0 existe dans le document, mais pas dans ce sous-lot.
                return validate(lm.EvidenceRecovery(selections=[lm.SourceSelection(
                    source_ref='u0', start_line=1, end_line=1, kind='explanation')], reason='Invalide'))
            return validate(lm.EvidenceRecovery(selections=[], reason='Aucun ajout'))
        with patch.object(lm, 'source_candidates', return_value=self.sources()):
            c = SimpleNamespace(concept_id='c', title='Notion')
            with self.assertRaisesRegex(ValueError, 'sous-lot'):
                lm.recover(c, [], {}, 'm', call, checkpoints=cache)
            seen.clear(); cache = json.loads(json.dumps(cache))
            with self.assertRaisesRegex(ValueError, 'sous-lot'):
                lm.recover(c, [], {}, 'm', call, checkpoints=cache)
            self.assertEqual(seen, [['u1']])

    def test_large_serialized_sources_are_split_before_first_request(self):
        sources = self.sources(); seen = []
        for source in sources:
            source['lines'] = [{'id': i+1, 'text': 'x\n'} for i in range(450)]
        def call(schema, prompt, payload, model, validate):
            seen.append(len(payload['sources']))
            return validate(lm.EvidenceRecovery(selections=[], reason='Aucun ajout'))
        with patch.object(lm, 'source_candidates', return_value=sources):
            result = lm.recover(SimpleNamespace(concept_id='c', title='Notion'), [], {}, 'm', call)
        self.assertEqual(seen, [1, 1])
        self.assertEqual(result['searched_sources'], ['u0', 'u1'])


class CoverageRecovery(unittest.TestCase):
    def exercise(self, failures):
        c = notion(); texts = [c.evidence[0].excerpt] * len(failures)
        fake = FakeModel({i+1: [fact(t)] for i, t in enumerate(texts)})
        seen = []
        def call(**kwargs):
            if kwargs['response_model'] is pedagogy.CoverageResponse:
                payload = json.loads(kwargs['messages'][-1]['content'])
                number = payload['source']['page']; seen.append(number)
                error = failures[number-1]
                if error:
                    raise error('Panne test')
            return fake(**kwargs)
        folder = TemporaryDirectory(); self.addCleanup(folder.cleanup)
        repo = CourseRepository(Path(folder.name))
        document = {'file_hash': SHA, 'pages': [page(i+1, t) for i, t in enumerate(texts)]}
        return c, call, repo, document, seen

    def test_temporary_page_failure_keeps_other_pages_and_resumes_only_missing(self):
        failures = [None, AITransientError, None]
        c, call, repo, doc, seen = self.exercise(failures)
        with patch.object(pedagogy, 'chat_json', side_effect=call):
            result = pedagogy.prepare_material(inventory(c), doc, PLAN, repo, model=MODEL)
            self.assertTrue(any(i.get('page') == 2 for i in result.issues))
            self.assertEqual(seen, [1, 2, 3])
            failures[1] = None; seen.clear()
            result = pedagogy.prepare_material(inventory(c), doc, PLAN, repo, model=MODEL)
            self.assertEqual(seen, [2])
            self.assertFalse(result.issues)

    def test_three_consecutive_temporary_failures_stop_but_save_issues(self):
        c, call, repo, doc, seen = self.exercise([AITransientError] * 4)
        with patch.object(pedagogy, 'chat_json', side_effect=call), self.assertRaises(AITransientError):
            pedagogy.prepare_material(inventory(c), doc, PLAN, repo, model=MODEL)
        self.assertEqual(seen, [1, 2, 3])
        saved = json.loads((repo.paths('cours-test').root / 'pedagogy.json').read_text(encoding='utf-8'))
        self.assertEqual(len(saved['issues']), 3)

    def test_quota_stops_on_first_page(self):
        c, call, repo, doc, seen = self.exercise([AIUsageLimitError, None])
        with patch.object(pedagogy, 'chat_json', side_effect=call), self.assertRaises(AIUsageLimitError):
            pedagogy.prepare_material(inventory(c), doc, PLAN, repo, model=MODEL)
        self.assertEqual(seen, [1])

    def test_cli_has_distinct_codes(self):
        for error, code in [(AITransientError('503'), 4), (AIUsageLimitError('429'), 3)]:
            with self.subTest(code=code), patch.object(manage, 'run_cards_command', side_effect=error):
                self.assertEqual(manage.main(['cards', 'build', '--course', 'test']), code)


class WholeSourceGrouping(unittest.TestCase):
    def test_one_shared_point_cannot_merge_an_entire_topic_into_a_subtopic(self):
        from src.courses import card_groups as cg
        concepts = {'cycle': notion('cycle', 'Cycle'), 'condensation': notion('condensation', 'Condensation')}
        common = {'point_id': 'cond', 'page': 1, 'quote': 'La condensation transforme la vapeur en liquide.'}
        other = {'point_id': 'evap', 'page': 1, 'quote': "L'évaporation transforme le liquide en vapeur."}
        points = {'cycle': [common, other], 'condensation': [common]}
        def call(schema, prompt, payload, model, validate):
            if schema is cg.RelationReview:
                return validate(schema(relation='same_notion', reason='Une citation identique.',
                    source_point_ids=['cond'], target_point_ids=['cond']))
            return validate(schema(relation='duplicate', target_ref='t1', reason='Un point partagé.'))
        with self.assertRaisesRegex(ValueError, 'tous les points'):
            cg.choose_group('cycle', ['condensation'], concepts, points, {'disposition': 'developed'}, model='m', call=call)
