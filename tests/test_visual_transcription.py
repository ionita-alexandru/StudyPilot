import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from src.models.concept import Concept,ConceptEvidence,LearningPoint,SourceIllustration
from src.courses import visual_cards,cards
from src.courses.card_presentation import render_text,publication_issue

class WrittenVisualTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'course.pdf'
  with pymupdf.open() as doc:
   page=doc.new_page(width=400,height=200);page.insert_text((30,60),'c_n = (a_n - i b_n)/2');doc.save(self.path)
  self.concept=Concept(concept_id='coeff',title='Coefficient complexe',type='formula',primary_part_id='p1',source_pages=[1],
   evidence=[ConceptEvidence(page=1,excerpt='c_n = (a_n - i b_n)/2')],
   learning_points=[LearningPoint(point_id='f1',kind='formula',page=1,quote='c_n = (a_n - i b_n)/2')],
   illustrations=[SourceIllustration(page=1,anchor_page=1,heading='Coefficient complexe',bbox=(0,0,400,200),origin='quote')],card_role='visual')
  self.written={'status':'complete','reason':'Lisible','sections':[{'key':'formula','title':'Formule','content':r'\[c_n=\frac{a_n-i b_n}{2}\]'}]}
  self.verdict={'supported':True,'complete':True,'covered_point_ids':['f1'],'missing_point_ids':[],'issues':[]}
 def tearDown(self):self.tmp.cleanup()
 def test_written_formula_is_audited_against_the_same_pixels(self):
  with patch.object(visual_cards,'chat_json',side_effect=[self.written,self.verdict]) as call:
   card=visual_cards.write_visual_card(self.concept,self.path,model='gemma',card_id='card')
  self.assertEqual(card.illustrations,[]);self.assertIn(r'\frac',card.sections[0].content)
  self.assertEqual(call.call_args_list[0].kwargs['messages'][1]['images'],call.call_args_list[1].kwargs['messages'][1]['images'])
  self.assertGreater(len(call.call_args_list[0].kwargs['messages'][1]['images'][0]),1000)
 def test_wrong_fraction_fails_visual_audit(self):
  verdict={**self.verdict,'supported':False,'issues':['Dénominateur incorrect']}
  with patch.object(visual_cards,'chat_json',side_effect=[self.written,verdict]),self.assertRaisesRegex(ValueError,'Dénominateur'):
   visual_cards.write_visual_card(self.concept,self.path,model='gemma',card_id='card')
 def test_omitted_required_point_is_rejected_even_with_positive_verdict(self):
  verdict={**self.verdict,'covered_point_ids':[]}
  with patch.object(visual_cards,'chat_json',side_effect=[self.written,verdict]),self.assertRaisesRegex(ValueError,'couverture'):
   visual_cards.write_visual_card(self.concept,self.path,model='gemma',card_id='card')
 def test_uncertain_source_never_publishes_placeholder(self):
  with patch.object(visual_cards,'chat_json',return_value={'status':'uncertain','reason':'Indice illisible','sections':[]}) as call,self.assertRaisesRegex(ValueError,'Indice'):
   visual_cards.write_visual_card(self.concept,self.path,model='gemma',card_id='card')
  self.assertEqual(call.call_count,1)
 def test_generation_dispatches_to_pixels_and_never_falls_back_to_page_only(self):
  pages=[{'page':1,'_source_pdf':str(self.path)}]
  with patch.object(cards,'proof_issue',return_value=None),patch.object(cards,'chat_json') as text_call,patch.object(visual_cards,'chat_json',side_effect=[self.written,self.verdict]):
   result=cards._generate_batch({},pages,[self.concept],model='gemma')
  text_call.assert_not_called();self.assertIn(r'\frac',result[0].sections[0].content)
  with patch.object(cards,'proof_issue',return_value=None),patch.object(cards,'chat_json') as text_call,patch.object(visual_cards,'chat_json',return_value={'status':'uncertain','reason':'Symbole illisible','sections':[]}):
   with self.assertRaises(cards.CardGenerationError) as error:cards._generate_batch({},pages,[self.concept],model='gemma')
  text_call.assert_not_called();self.assertEqual(error.exception.generated,[])
 def test_pdf_only_legacy_card_is_pending(self):
  c={'title':'Coefficient','illustrations':[{'page':1}],'sections':[{'content':'Le passage original est conservé ci-dessous pour respecter sa mise en page et ses notations.'}]}
  self.assertIn('transcription',publication_issue(c))
 def test_double_escaped_latex_is_fixed_without_touching_matrix_rows_or_code(self):
  html=render_text(r'\\(\\frac{a}{b}\\)')
  self.assertIn(r'\(\frac{a}{b}\)',html);self.assertNotIn(r'\\frac',html)
  matrix=render_text(r'\[\begin{matrix}a\\b\end{matrix}\]');self.assertIn(r'a\\b',matrix)
  code=render_text('```python\n'+r'path="C:\\bin"'+'\n```');self.assertIn(r'C:\\bin',code)
