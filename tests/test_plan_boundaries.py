"""Tests sans Ollama; les tests sémantiques restent une revue humaine."""
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from src.courses.planner import extract_document
from src.courses.plan_boundaries import (suggest_boundaries, check_boundaries,
                                title_candidate, boundary_evidence)

ROOT = Path(__file__).resolve().parents[1]

class PlanBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        css = ROOT/'data/pdfs/Cours-de-CSS-c41d0f1887.pdf'
        if not css.exists():
            raise unittest.SkipTest('Fixture PDF CSS non présente dans ce projet')
        cls.doc=extract_document(css)
        cls.saved=json.loads((ROOT/'data/plans/Cours-de-CSS-c41d0f1887.json').read_text(encoding='utf-8'))

    def test_01_non_destructive_and_coverage(self):
        saved=deepcopy(self.saved)
        proposal=suggest_boundaries(saved, self.doc)
        self.assertEqual(saved,self.saved)
        self.assertEqual(check_boundaries(proposal,saved,self.doc)[0][0],1)
        self.assertEqual(check_boundaries(proposal,saved,self.doc)[-1][1],26)
        self.assertEqual(sum(b-a+1 for a,b in check_boundaries(proposal,saved,self.doc)),26)
        self.assertEqual(proposal['page_count'],26)

    def test_02_transition_between_columns_and_links(self):
        boundaries=suggest_boundaries(self.saved,self.doc)
        ranges=check_boundaries(boundaries,self.saved,self.doc)
        self.assertIn((24,26), ranges)
        self.assertFalse(any(a<=23 and b>=24 for a,b in ranges))
        self.assertTrue(any(e['after_page']==23 and e['score']>0 for e in boundaries['transitions']))

    def test_03_reject_malformed_ranges_and_wrong_hash(self):
        proposal=suggest_boundaries(self.saved,self.doc)
        proposal['parts'][0]['end_page']=2
        with self.assertRaisesRegex(ValueError,'non contiguës'):
            check_boundaries(proposal,self.saved,self.doc)
        proposal=suggest_boundaries(self.saved,self.doc)
        proposal['file_hash']='wrong'
        with self.assertRaisesRegex(ValueError,'incompatibles'):
            check_boundaries(proposal,self.saved,self.doc)

    def test_04_title_calls_per_fixed_range_and_resume(self):
        proposal=suggest_boundaries(self.saved,self.doc)
        calls=[]
        checkpoints=[]
        def fake(prompt,model):
            m=re.search(r'plage p\.(\d+)–(\d+)',prompt)
            self.assertIsNotNone(m)
            a,b=map(int,m.groups())
            calls.append((a,b))
            return {'title':f'Notions de la plage {a} à {b}', 'evidence_pages':[a], 'warning':''}
        result=title_candidate(proposal,self.saved,self.doc,ai_call=fake,
                               on_progress=lambda done,total,data:checkpoints.append(deepcopy(data)))
        ranges=check_boundaries(proposal,self.saved,self.doc)
        self.assertEqual(calls,ranges)
        self.assertTrue(all(p['title_status']=='draft' for p in result['parts']))
        self.assertTrue(all(p['overview']['status']=='pending' for p in result['parts']))
        self.assertEqual(self.saved['parts'][0]['overview']['status'],'draft')
        resumed=title_candidate(proposal,self.saved,self.doc,ai_call=fake,checkpoint=checkpoints[-1])
        self.assertEqual(len(calls),len(ranges))
        self.assertEqual(resumed['parts'],result['parts'])

    def test_05_bad_evidence_error_but_next_part_continues(self):
        proposal=suggest_boundaries(self.saved,self.doc)
        def fake(prompt,model):
            return {'title':'Titre erroné','evidence_pages':[999], 'warning':''}
        result=title_candidate(proposal,self.saved,self.doc,ai_call=fake)
        self.assertTrue(all(p['title_status']=='error' for p in result['parts']))
        self.assertTrue(all(p['overview']['status']=='pending' for p in result['parts']))

    def test_06_numbered_preferred(self):
        saved=deepcopy(self.saved)
        saved['mode']='numbered'
        with self.assertRaises(Exception):
            suggest_boundaries(saved,self.doc)

    def test_08_real_maths_documents_are_numbered(self):
        from src.courses.planner import initial_plan
        paths = [p for p in (ROOT/'data/pdfs').glob('*.pdf') if 'CSS' not in p.name]
        if not paths:
            self.skipTest('PDF maths non disponibles dans cette copie')
        for path in paths:
            doc = extract_document(path)
            saved = initial_plan(doc)
            self.assertEqual(saved['mode'], 'numbered')
            with self.assertRaises(ValueError):
                suggest_boundaries(saved,doc)

    def test_09_short_unstructured_document_single_part(self):
        from src.courses.plan_boundaries import _partition
        pages=[{'page':1}, {'page':2}, {'page':3}]
        self.assertEqual(_partition(pages, []), [(1,3)])

    def test_07_no_model_dependency_boundary_evidence(self):
        evidence=boundary_evidence(self.doc['pages'][22],self.doc['pages'][23])
        self.assertEqual(evidence['after_page'],23)
        self.assertIn('Hyperlink',evidence['next_source_heading'])
        self.assertIn('score',evidence)

if __name__=='__main__': unittest.main()
