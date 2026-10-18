import unittest,os
from unittest.mock import patch
from types import SimpleNamespace
from src import part_study
from src.ai.client import readable_contract
import app
class ChatTests(unittest.TestCase):
 def test_real_chat_accepts_course_and_history(self):
  with patch.object(part_study,'chat',return_value=SimpleNamespace(message=SimpleNamespace(content='Réponse IA'))) as call:
   out=part_study.answer_part_question('Pourquoi ?', [{'page':3,'content':'Av = λv'}], 'gemma-4-26b-a4b-it',course_title='Algèbre',part={'title':'Valeurs propres'},course_outline='Plan',history=[{'role':'user','content':'Valeur propre'}],course_overview=True)
  self.assertEqual(out,'Réponse IA');kw=call.call_args.kwargs;self.assertEqual(len(kw['messages']),3);self.assertIn('PAGE PHYSIQUE 3',kw['messages'][-1]['content']);self.assertIn('Plan',kw['messages'][-1]['content'])
 def fixture(self):return dict(course_id='cours-test',title='CSS',source_filename='course.pdf'),{'parts':[{'id':'p1','number':'1','title':'Styles','page_start':1,'page_end':3}]}
 def test_presentation_flag_never_substitutes_local_answer(self):
  with patch.object(app,'_load_course_and_plan',return_value=self.fixture()),patch.object(app,'retrieve_pdf_contexts',return_value=[{'page':2,'content':'style'}]),patch.object(part_study,'chat',return_value=SimpleNamespace(message=SimpleNamespace(content='Vraie réponse modèle'))) as model,patch.dict(os.environ,{'STUDYPILOT_PRESENTATION':'1'}):
   response=app.app.test_client().post('/api/part-chat',json=dict(course_id='cours-test',part_number='1',question='Que fait style ?'))
  self.assertEqual(response.status_code,200);self.assertEqual(response.get_json()['answer'],'Vraie réponse modèle');model.assert_called_once();self.assertEqual(response.get_json()['pages'],[2])
 def test_api_failure_is_error_not_saved_text(self):
  with patch.object(app,'_load_course_and_plan',return_value=self.fixture()),patch.object(app,'retrieve_pdf_contexts',return_value=[]),patch.object(part_study,'chat',side_effect=RuntimeError('API inaccessible')):
   response=app.app.test_client().post('/api/part-chat',json=dict(course_id='cours-test',part_number='1',question='Que fait style ?'))
  self.assertEqual(response.status_code,503);self.assertNotIn('answer',response.get_json())
 def test_contract_preserves_enum_keys(self):
  contract=readable_contract({'type':'object','required':['keys'],'properties':{'keys':{'type':'object','propertyNames':{'enum':['p1','p2']},'additionalProperties':{'enum':['formula','explanation']}}}})
  for item in ['keys','p1','p2','formula','explanation']:self.assertIn(item,contract)
  self.assertNotIn('properties',contract);self.assertNotIn('required',contract)
