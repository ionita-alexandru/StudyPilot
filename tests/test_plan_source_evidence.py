"""Tests Plan source evidence — source PDF prioritaire, cache conservé."""
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf
from src.courses.planner import _id, extract_document
from src.courses.plan_review import (build_prompt, create_candidate, index_diagnostics,
                             source_evidence)
from src.config import STUDY_MODEL


class PlanSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.pdf = Path(self.folder.name) / 'cours-test.pdf'
        with pymupdf.open() as doc:
            for i, text in enumerate((
                'Ondes electromagnetiques\nDefinition et propagation',
                'Ondes electromagnetiques\nExemple de propagation',
                'Algebre lineaire\nBases et matrices',
                'Algebre lineaire\nExemple de calcul',
            ), 1):
                page = doc.new_page()
                page.insert_text((40, 65), f'Chapitre {i}: {text}')
            doc.save(self.pdf)
        self.document = extract_document(self.pdf)
        h = self.document['file_hash']
        self.active = {
            'plan_version': 1, 'filename': self.pdf.name, 'file_hash': h,
            'page_count': 4, 'mode': 'thematic_ai_draft', 'status': 'draft',
            'warnings': [], 'page_diagnostics': [], 'model': STUDY_MODEL,
            'parts': [{
                'id': _id(h, 'pages:1:4'), 'number': '1', 'title': 'Cours en général',
                'page_start': 1, 'page_end': 4, 'title_origin': 'ai_proposal',
                'overview': {'status': 'draft', 'summary': 'Ancienne synthèse'},
                'source_pages': [1, 2, 3, 4],
            }],
        }
        self.index = {
            'index_version': 1, 'filename': self.pdf.name, 'file_hash': h,
            'page_count': 4, 'model': STUDY_MODEL,
            'pages': [{'page': n, 'topics': ['document', 'cours']} for n in range(1, 5)],
        }
        self.cache = Path(self.folder.name) / 'themes.json'
        self.cache.write_text(json.dumps(self.index, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.folder.cleanup()

    def test_raw_source_is_prioritized_over_weak_index(self):
        prompt = build_prompt(self.active, self.document, self.index)
        self.assertIn('SOURCE PDF, PAGE PAR PAGE (prioritaire)', prompt)
        self.assertIn('INDEX PAGE PAR PAGE (secondaire', prompt)
        self.assertIn('Ondes electromagnetiques', prompt)
        self.assertIn('Algebre lineaire', prompt)
        self.assertNotIn('Cours en général', prompt)
        self.assertIn('document ; cours', prompt)

    def test_uses_complete_cached_index_without_reindexing(self):
        calls = []
        def fake(prompt, model):
            calls.append(prompt)
            if 'SOURCE PDF' not in prompt:
                raise AssertionError('Ne doit pas appeler Ollama pour les pages déjà indexées')
            return {'parts': [
                {'start_page': 1, 'end_page': 2, 'title': 'Ondes électromagnétiques'},
                {'start_page': 3, 'end_page': 4, 'title': 'Algèbre linéaire'},
            ]}
        candidate = create_candidate(self.active, self.document, ai_call=fake, index_cache=self.cache)
        self.assertEqual(len(calls), 1)
        self.assertEqual([p['page_end'] for p in candidate['parts']], [2, 4])
        self.assertEqual(self.active['parts'][0]['overview']['status'], 'draft')
        self.assertTrue(all(p['overview']['status'] == 'pending' for p in candidate['parts']))

    def test_diagnostic_marks_repeats_without_mutating_index(self):
        index = json.loads(json.dumps(self.index))
        index['pages'][2]['topics'].append('cours')
        self.assertEqual(index_diagnostics(index), ['p.3 : thèmes textuellement répétés dans l\'index IA'])
        self.assertEqual(len(index['pages'][2]['topics']), 3)

    def test_source_evidence_without_heading_has_real_code(self):
        page = {'page': 1, 'headings': [], 'analysis_text': 'Another Example:\nfunc(x) { return x + 1; }\nResult'}
        evidence = source_evidence(page)
        self.assertIn('func(x)', evidence)
        self.assertIn('p.1', evidence)


if __name__ == '__main__':
    unittest.main()
