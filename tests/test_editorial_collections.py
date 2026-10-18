import json,unittest,tempfile,shutil
from pathlib import Path
from unittest.mock import patch
from src.courses import reviewed,service
from src.courses.card_presentation import publication_issue

ROOT=Path(__file__).resolve().parents[1]
class CompleteReviewTests(unittest.TestCase):
 def sources(self):
  for folder in (ROOT/'data/courses').iterdir():
   if (folder/'reviewed_coverage.json').exists():
    yield folder,json.loads((folder/'course.json').read_text()),json.loads((folder/'plan.json').read_text())
 def test_all_three_original_pdfs_have_source_bound_sets_without_placeholder_cards(self):
  counts=[]
  for folder,course,plan in self.sources():
   data=reviewed.load_reviewed(course,plan,folder,ROOT/'data/pdfs');self.assertIsNotNone(data);counts.append(len(data.cards))
   self.assertEqual(data.coverage,'course_review')
   for card in data.cards:
    self.assertIsNone(publication_issue(card));self.assertFalse(card.illustrations)
    self.assertTrue(all('Le passage original est conservé' not in s.content for s in card.sections))
  self.assertEqual(sorted(counts),[21,36,59])
 def test_missing_page_in_full_review_is_rejected(self):
  folder,course,plan=next(self.sources())
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for n in ['reviewed_cards.json','reviewed_coverage.json']:shutil.copy2(folder/n,root/n)
   report=json.loads((root/'reviewed_coverage.json').read_text());report['pages'].pop();(root/'reviewed_coverage.json').write_text(json.dumps(report))
   self.assertIsNone(reviewed.load_reviewed(course,plan,root,ROOT/'data/pdfs'))
 def test_unknown_card_link_in_coverage_report_is_rejected(self):
  folder,course,plan=next(self.sources())
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for n in ['reviewed_cards.json','reviewed_coverage.json']:shutil.copy2(folder/n,root/n)
   report=json.loads((root/'reviewed_coverage.json').read_text());next(p for p in report['pages'] if p['card_ids'])['card_ids'].append('unknown');(root/'reviewed_coverage.json').write_text(json.dumps(report))
   self.assertIsNone(reviewed.load_reviewed(course,plan,root,ROOT/'data/pdfs'))
 def test_existing_generation_errors_do_not_replace_or_duplicate_full_prepared_set(self):
  for folder,course,plan in self.sources():
   data=reviewed.load_reviewed(course,plan,folder,ROOT/'data/pdfs')
   with patch.object(service,'_reviewed_collection',return_value=data), patch('src.courses.study_guide.load_guide', return_value=None):
    found={c['card_id'] for p in plan['parts'] for c in service.load_part_cards(course,p['id'])}
    self.assertEqual(found,{c.card_id for c in data.cards})
    self.assertTrue(all(not service.load_part_unavailable(course,p['id']) for p in plan['parts']))

if __name__=='__main__':unittest.main()
