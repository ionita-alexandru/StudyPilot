"""Régressions utiles : verdict, identité de l'exercice et reprise après redémarrage."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from src import learning_tutor as learning, tutor
from src.courses import service
from test_study_guide import COURSE, PLAN, SOURCES


def exercise():
    checker=learning.Checker(operation='eigenvalue',matrix=[[4,2],[1,3]],vector=[2,1])
    return dict(id='ex1',title='Valeur propre',statement='Chercher la valeur propre associée.',objective='Identifier la valeur propre.',
        checker=checker.model_dump(),reference=learning.reference(checker),criteria=['Donner le résultat numérique demandé.'],
        hint='Calcule Av.',solution='Av = 5v.',expected_answer='5',assisted=False,attempts=0,card_id='f1')


class LearningTutorTests(unittest.TestCase):
    def test_correct_result_is_never_announced_as_a_mistake_and_needs_no_model(self):
        with patch.object(learning,'model_call',side_effect=AssertionError('appel inutile')):
            for answer,status in [('5','correct'),('λ = 5','correct'),('10/2','correct'),('lambda vaut 5','correct'),(r'\frac{10}{2}','correct'),('4','incorrect')]:
                with self.subTest(answer=answer):
                    text,result=learning.assess(exercise(),answer,'test')
                    self.assertEqual(result['status'],status)
                    self.assertEqual(result['basis'],'local_calculation')
                    if status=='correct':self.assertNotIn('à corriger',text)
            self.assertEqual(learning.assess(exercise(),'Je me demande si je dois calculer 2 fois 5.', 'test')[1]['status'],'uncertain')

    def test_mismatched_reference_prevents_publication_and_data_drives_statement(self):
        proposal=exercise();proposal={k:v for k,v in proposal.items() if k in learning.Exercise.model_fields}
        proposal.update(statement='Données erronées du modèle à remplacer.',solution='Une solution incohérente mais assez longue.',hint='Un indice du modèle.')
        with patch.object(learning,'model_call',return_value=learning.Exercise(**proposal)):
            result=learning.new_exercise({'id':'f1'},[], 'Exercice','test')
            self.assertIn('4 & 2',result['statement']);self.assertNotIn('erronées',result['statement'])
            self.assertIn('5',result['solution'])
        proposal['expected_answer']='4'
        with patch.object(learning,'model_call',return_value=learning.Exercise(**proposal)):
            with self.assertRaisesRegex(ValueError,'non publié'):learning.new_exercise({'id':'f1'},[],'Exercice','test')
        with self.assertRaises(ValueError):learning.reference(learning.Checker(operation='eigenvalue',matrix=[[1,0],[0,2]],vector=[1,1]))

    def test_missing_justification_is_partial_and_invented_error_is_uncertain(self):
        e=exercise();e['reference']=None;e['criteria']=['Résultat','Justification']
        observations=[dict(criterion='Résultat',status='met'),dict(criterion='Justification',status='missing')]
        with patch.object(learning,'model_call',return_value=learning.Assessment(observations=observations)):
            text,result=learning.assess(e,'5','test')
            self.assertEqual(result['status'],'partial');self.assertIn('À préciser',text)
        observations[0]=dict(criterion='Résultat',status='incorrect',quote='4',correction='Le résultat est 5.')
        with patch.object(learning,'model_call',return_value=learning.Assessment(observations=observations)):
            self.assertEqual(learning.assess(e,'5','test')[1]['status'],'uncertain')

    def test_hint_and_solution_are_cached_and_mark_assistance(self):
        state={'exercise':exercise()}
        with patch.object(learning,'model_call',side_effect=AssertionError('appel inutile')):
            for intent in ('hint','solution'):
                result=learning.exercise_action(state,None,[],intent,'','test')
                self.assertTrue(state['exercise']['assisted']);self.assertEqual(state['exercise']['id'],'ex1')
            self.assertIn('5',result['answer'])
            self.assertTrue(learning.assess(state['exercise'],'5','test')[1]['assisted'])

    def test_restart_restores_exercise_but_guide_change_invalidates_it(self):
        guide=dict(revision='v1',entries=[],sources=SOURCES)
        with tempfile.TemporaryDirectory() as folder, patch.object(service,'_repository',return_value=SimpleNamespace(paths=lambda _:SimpleNamespace(root=Path(folder)))),patch.object(tutor,'load_guide',return_value=guide):
            with tutor.conversation(COURSE,PLAN) as (state,_):
                identifier=state['id'];state['exercise']=exercise();state['history']=[dict(role='user',content='5')]
            tutor._SESSIONS.pop(identifier)
            public=tutor.restore(COURSE,PLAN,identifier)
            self.assertEqual(public['exercise']['id'],'ex1');self.assertNotIn('expected_answer',public['exercise']);self.assertNotIn('solution',public['exercise'])
            self.assertEqual(public['history'][0]['content'],'5')
            guide['revision']='v2'
            self.assertIsNone(tutor.restore(COURSE,PLAN,identifier)['exercise'])
        tutor._SESSIONS.pop(identifier,None)

    def test_learning_sources_are_inspectable_without_claiming_full_coverage(self):
        from src.learning_view import learning_view
        guide=dict(revision='v1',sources=[dict(SOURCES[0],has_visual_content=True),dict(id='s2',page=1,text='Autre passage')],entries=[dict(id='f1',role='core',part_id='p1',title='Fonction',body='Une fonction.',objective='Comprendre la fonction',source_ids=['s1'])],parts=[dict(part_id='p1',status='partial')],decisions=[dict(card_id='s1',reason='Décision éditoriale ancienne.')])
        with patch('src.learning_view.load_guide',return_value=guide):
            view=learning_view(COURSE,PLAN)
            self.assertTrue(view['incomplete']);self.assertEqual(view['coverage'][1]['status'],'À vérifier')
            self.assertTrue(view['has_unverified_visuals'])
            self.assertEqual(view['coverage'][0]['status'],'Texte rattaché · visuel à vérifier')
