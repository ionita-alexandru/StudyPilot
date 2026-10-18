import json,hashlib,unittest,os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pydantic import ValidationError
from src.courses.reviewed import load_reviewed
from src.courses import learning_material as lm
from src.ai import gemma,client
from types import SimpleNamespace
from urllib.error import URLError
class IntegratedTests(unittest.TestCase):
 def test_review_bound_to_actual_pdf_and_part(self):
  with TemporaryDirectory() as d:
   root=Path(d);pdf=root/'course.pdf';pdf.write_bytes(b'original');digest=hashlib.sha256(pdf.read_bytes()).hexdigest();course=dict(course_id='cours-test',source_filename='course.pdf',file_hash=digest,page_count=2)
   raw=dict(schema_version=1,course_id='cours-test',file_hash=digest,provenance='editorial_review',review_date='2026-10-12',coverage='selection',cards=[dict(card_id='reviewed-1',concept_id='c1',title='Valeur propre',concept_type='definition',primary_part_id='part-1',sections=[dict(key='definition',title='Définition',content='Av = λv, v non nul.')],source_pages=[1])],questions={});(root/'reviewed_cards.json').write_text(json.dumps(raw))
   self.assertEqual(load_reviewed(course,{'parts':[{'id':'part-1'}]},root,root).provenance,'editorial_review')
   self.assertIsNone(load_reviewed(course,{'parts':[{'id':'other'}]},root,root))
   pdf.write_bytes(b'changed');self.assertIsNone(load_reviewed(course,{'parts':[{'id':'part-1'}]},root,root))
 def test_schema_rejects_category_as_point_key(self):
  def call(schema,*args):
   raw=dict(disposition='developed',concept_type='theorem',reason='Source suffisante',missing_information=[],excluded_points={},point_kinds={'formula':'formula'})
   with self.assertRaises(ValidationError):schema.model_validate(raw)
   raw['point_kinds']={'p1':'property'};self.assertEqual(schema.model_validate(raw).point_kinds,{'p1':'explanation'});return 'tested'
  self.assertEqual(lm.assess(SimpleNamespace(concept_id='c1',title='Propriété',type='theorem'),[dict(point_id='full-id',page=1,quote='Source',kind='explanation')],'test',call),'tested')
 def test_network_failure_is_differable_once(self):
  with patch.dict(os.environ,{'GEMINI_API_KEY':'valid'}),patch.object(gemma,'_send',side_effect=URLError('private')) as call:
   with self.assertRaises(client.AITransientError):gemma._post('gemma-4-26b-a4b-it','generateContent',{},retry_tokens=5)
  self.assertEqual(call.call_count,1)
 def test_bad_paste_detected(self):
  with patch.dict(os.environ,{'GEMINI_API_KEY':'abc def'}),self.assertRaisesRegex(gemma.GemmaServiceError,'caractères incompatibles'):gemma._post('gemma-4-26b-a4b-it','countTokens',{})
