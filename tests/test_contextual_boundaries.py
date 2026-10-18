"""Tests de régression : CSS comme fixture, mais aucune règle CSS en production.
Tests sans Ollama, aucune écriture dans les données historiques.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from src.courses.plan_boundaries import (contextual_boundaries, suggest_boundaries,
                                check_boundaries, title_candidate)
from src.courses.planner import extract_document

ROOT = Path(__file__).resolve().parents[1]


class ContextualBoundaryTests(unittest.TestCase):
    def test_context_generique_sans_matiere(self):
        # Deux sujets artificiels non CSS ; couverture et invariants sur pages source.
        pages = []
        for n in range(1, 13):
            if n < 7:
                topic = 'La respiration cellulaire'
                body = 'La respiration cellulaire et les mitochondries expliquent la production énergétique.'
            else:
                topic = 'Les lois du mouvement'
                body = 'Les forces et l accélération décrivent le mouvement d un objet.'
            pages.append({'page': n, 'analysis_text': f'• {topic}\n{body}\n{body}', 'headings': []})
        transitions = contextual_boundaries(pages)
        self.assertEqual(len(transitions), 11)
        self.assertGreater(transitions[5]['score'], transitions[4]['score'])
        self.assertEqual([e['after_page'] for e in transitions], list(range(1, 12)))

    def test_regression_source_css(self):
        pdf = ROOT / 'data/pdfs/Cours-de-CSS-c41d0f1887.pdf'
        saved = ROOT / 'data/plans/Cours-de-CSS-c41d0f1887.json'
        if not pdf.is_file() or not saved.is_file():
            self.skipTest('PDF / plan CSS non fournis : test d’intégration local ignoré')
        doc = extract_document(pdf)
        baseline = json.loads(saved.read_text(encoding='utf-8'))
        untouched = deepcopy(baseline)
        candidate = suggest_boundaries(baseline, doc)
        ranges = check_boundaries(candidate, baseline, doc)
        self.assertEqual(candidate['boundary_version'], 4)
        self.assertEqual(baseline, untouched)
        self.assertEqual(ranges, [(1,3),(4,6),(7,9),(10,12),(13,15),(16,20),(21,23),(24,26)])
        self.assertEqual(sum(b-a+1 for a,b in ranges),26)
        self.assertEqual(len({e['after_page'] for e in candidate['transitions']}),25)
        self.assertTrue(all('score' in e and 'reasons' in e for e in candidate['transitions']))
        self.assertEqual(candidate['status'], 'candidate')
        self.assertTrue(candidate['review_required'])
        self.assertEqual(baseline['parts'][0]['overview']['status'], 'draft')
        self.assertNotIn('overview', candidate['parts'][0])

if __name__ == '__main__':
    unittest.main()
