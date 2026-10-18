"""Contrats du parcours actif : publication, reprise, sources et conversation."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.courses import service, guide_generation as generation
from src.courses.study_guide import validate_draft, save_guide, load_guide, plan_version
from src.storage.repository import write_json_atomic
from src import tutor
from src.study_checks import calculate, verify_response


COURSE = dict(course_id='cours-test', file_hash='a'*64, title='Cours', source_filename='test.pdf')
PLAN = dict(parts=[dict(id='p1', number='1', title='Fonctions', page_start=1, page_end=1)])
SOURCES = [dict(id='s1', page=1, origin='pdf_ocr', text='Une fonction renvoie un résultat avec return.')]
DRAFT = dict(entries=[dict(key='function', title='Fonction', role='core', kind='concept',
    objective='Comprendre le résultat renvoyé', body='Une fonction renvoie un résultat avec `return`.',
    source_ids=['s1'], targets=[], aliases=[])],
    coverage=[dict(source_id='s1', entry_keys=['function'], reason='La règle principale est expliquée.')])
REVIEW = dict(entries=[dict(key='function', supported=True, essential_complete=True, useful_role=True, issues=[])],
              coverage_complete=True, coverage_issues=[],objectives=[dict(objective='Comprendre le résultat renvoyé',source_ids=['s1'],entry_keys=['function'])])


class GuideTests(unittest.TestCase):
    def test_reference_and_coverage_failures_cannot_publish(self):
        mutations = [lambda d:d['entries'][0].update(source_ids=['missing']),
                     lambda d:d['entries'][0].update(role='detail',targets=['function']),
                     lambda d:d.update(coverage=[]),
                     lambda d:d['coverage'][0].update(entry_keys=[]),
                     lambda d:d['entries'][0].update(body='mot '*111)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data=deepcopy(DRAFT); mutate(data)
                with self.assertRaises(ValueError): validate_draft(data,SOURCES)
        self.assertEqual(validate_draft(DRAFT,SOURCES).entries[0].source_ids,['s1'])
        grammar=deepcopy(DRAFT);grammar['entries'][0]['kind']='rule'
        self.assertEqual(validate_draft(grammar,SOURCES).entries[0].kind,'rule')
        technical=deepcopy(DRAFT);technical['entries'][0].update(kind='distinction',targets=['function'])
        normalized=validate_draft(technical,SOURCES).entries[0]
        self.assertEqual((normalized.kind,normalized.targets,normalized.body),('concept',[],DRAFT['entries'][0]['body']))

    def test_semantic_failure_gets_only_one_correction(self):
        rejected=deepcopy(REVIEW);rejected['entries'][0].update(essential_complete=False,issues=['Condition manquante'])
        with patch.object(generation,'chat_json',side_effect=[DRAFT,rejected,DRAFT,rejected]) as call:
            with self.assertRaisesRegex(ValueError,'Condition manquante'):
                generation.generate_batch(SOURCES)
        self.assertEqual(call.call_count,4)
        import json
        correction=json.loads(call.call_args_list[2].kwargs['messages'][-1]['content'])
        self.assertEqual(correction['previous_proposal'],DRAFT)
        self.assertIn('Condition manquante',correction['corrections'][0])
        with patch.object(generation,'chat_json') as call:
            with self.assertRaises(generation.AIUsageLimitError):
                generation.generate_batch(SOURCES,budget=generation.Budget(max_calls=0))
            call.assert_not_called()

    def test_import_checkpoint_reuses_ocr_and_validated_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); repo=SimpleNamespace(paths=lambda _:SimpleNamespace(root=root))
            write_json_atomic(root/'document_sources.json',dict(file_hash=COURSE['file_hash'],sources=SOURCES))
            with patch.object(service,'load_course',return_value=COURSE),patch.object(service,'load_course_plan',return_value=PLAN), \
                 patch.object(service,'_repository',return_value=repo),patch.object(generation,'chat_json',side_effect=[DRAFT,REVIEW]) as call, \
                 patch('src.courses.planner.extract_document',side_effect=AssertionError('OCR relancé')):
                from src.courses.pipeline import process_course
                first=process_course('cours-test')
                self.assertEqual(first['status'],'ready')
                before=(root/'study_guide.json').read_bytes()
                second=process_course('cours-test')
                self.assertEqual(second['calls'],0);self.assertEqual(call.call_count,2)
                self.assertEqual(before,(root/'study_guide.json').read_bytes())
                self.assertEqual(service.load_part_cards(COURSE,'p1')[0]['sections'][0]['content'],DRAFT['entries'][0]['body'])
                changed=deepcopy(PLAN);changed['parts'][0]['title']='Autre version'
                self.assertIsNone(load_guide(COURSE,changed))

    def test_failed_later_batch_preserves_earlier_publication(self):
        second=dict(id='s2',page=1,text='Deuxième enseignement indépendant.')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=SimpleNamespace(paths=lambda _:SimpleNamespace(root=root))
            write_json_atomic(root/'document_sources.json',dict(file_hash=COURSE['file_hash'],sources=SOURCES+[second]))
            with patch.object(service,'load_course',return_value=COURSE),patch.object(service,'load_course_plan',return_value=PLAN), \
                 patch.object(service,'_repository',return_value=repo),patch.object(generation,'batches',return_value=[SOURCES,[second]]), \
                 patch.object(generation,'generate_batch',side_effect=[(validate_draft(DRAFT,SOURCES),REVIEW),generation.AIUsageLimitError('quota')]):
                with self.assertRaises(generation.AIUsageLimitError):generation.build_guide('cours-test')
                saved=load_guide(COURSE,PLAN)
                self.assertEqual(len(saved['entries']),1);self.assertEqual(saved['parts'][0]['status'],'partial')
                self.assertEqual(len(saved['sources']),2)

    def test_conversation_keeps_active_notion_but_rejects_cross_course_and_parallel_send(self):
        guide=dict(revision='v1',entries=[dict(id='f1',title='Fonction',role='core',body='return transmet une valeur.',part_id='p1',source_ids=['s1'])],sources=SOURCES)
        with patch.object(tutor,'load_guide',return_value=guide):
            with tutor.conversation(COURSE,PLAN,card_id='f1') as (state,_):
                identifier=state['id']
                with self.assertRaises(RuntimeError):
                    with tutor.conversation(COURSE,PLAN,identifier): pass
                _,_,contexts=tutor.context_for(COURSE,PLAN,PLAN['parts'][0],'Pourquoi ?',state,guide)
                self.assertEqual(contexts[0]['origin'],'pdf_ocr')
            with tutor.conversation(COURSE,PLAN,identifier) as (state,_):
                self.assertEqual(state['card_id'],'f1')
                guide['entries'].append(dict(id='f2',title='Boucle répétitive',role='core',body='Une boucle répète une action.',part_id='p1',source_ids=['s1']))
                active,_,_=tutor.context_for(COURSE,PLAN,PLAN['parts'][0],'Explique la boucle répétitive.',state,guide)
                self.assertEqual(active['id'],'f2')
                active,_,_=tutor.context_for(COURSE,PLAN,PLAN['parts'][0],'Pourquoi ?',state,guide)
                self.assertEqual(active['id'],'f2')
            with self.assertRaises(ValueError):
                with tutor.conversation(dict(COURSE,course_id='autre-cours'),PLAN,identifier):pass
            guide['revision']='v2'
            with tutor.conversation(COURSE,PLAN,identifier) as (state,_):
                self.assertIsNone(state['card_id']);self.assertEqual(state['history'],[])

    def test_saved_example_needs_no_model_and_html_is_safe(self):
        guide=dict(revision='v1',entries=[dict(id='f1',title='Fonction',role='core',body='return transmet une valeur.',part_id='p1',source_ids=['s1']),
            dict(id='e1',title='Exemple',role='example',body='```python\ndef f(x):\n    return x\n```\n<script>alert(1)</script>',
                 part_id='p1',source_ids=['s1'],targets=['f1'])],sources=SOURCES)
        with patch.object(tutor,'load_guide',return_value=guide),patch('src.part_study.chat') as call:
            result=tutor.answer(COURSE,PLAN,PLAN['parts'][0],'Un exemple',card_id='f1',intent='example',model='test')
            call.assert_not_called()
        self.assertIn('<pre><code>',result['answer_html']);self.assertNotIn('<script>',result['answer_html'])
        self.assertEqual(result['source'],'saved_resource')

    def test_calculations_are_bounded_and_never_execute_arbitrary_python(self):
        self.assertEqual(calculate(dict(operation='arithmetic',expression='3*2**3',expected=24))[:2],('24',True))
        self.assertEqual(calculate(dict(operation='matrix_vector',matrix=[[2,1],[1,2]],vector=[1,1],expected=[3,3]))[1],True)
        self.assertEqual(calculate(dict(operation='python_function',code='def doubler(x):\n return 2*x',argument=3,expected=6))[1],True)
        for code in ['__import__("os").system("echo bad")','10**999999','1e99999999','[x for x in range(100)]']:
            with self.subTest(code=code),self.assertRaises((ValueError,OverflowError)):
                calculate(dict(operation='arithmetic',expression=code,expected=0))
        text,checks=verify_response('Calcul\n```verification\n{"operation":"arithmetic","expression":"2+2","expected":5}\n```')
        self.assertFalse(checks[0]['passed']);self.assertIn('Écart détecté',text)

    def test_network_retries_share_the_generation_budget(self):
        from src.ai.workload import budget_scope, request_attempt
        budget=generation.Budget(max_calls=1)
        with budget_scope(budget):
            request_attempt(100,6000)
            request_attempt(100,6000)
            with self.assertRaises(generation.AIUsageLimitError):request_attempt(100,6000)
        self.assertEqual(budget.network_requests,2)
        self.assertEqual(budget.reserved_tokens,12200)

    def test_migration_keeps_all_originals_as_resources_without_duplicate_core_ids(self):
        for course in service.list_courses():
            guide=load_guide(course)
            if not guide or guide['origin']!='editorial_review':continue
            original=service._reviewed_collection(course)
            if not original:continue
            self.assertTrue({c.card_id for c in original.cards} <= {s['id'] for s in guide['sources']})
            ids={e['id'] for e in guide['entries']};self.assertEqual(len(ids),len(guide['entries']))
            for entry in guide['entries']:self.assertTrue(set(entry['targets'])<=ids)
            self.assertFalse(any(e['role']=='core' and e['title'].startswith('Exercices du cours') for e in guide['entries']))
