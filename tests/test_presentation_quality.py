"""Aperçus mathématiques complets et HTML échappé."""
import unittest
from src.presentation import card_summary
from src.courses.card_presentation import render_text


class CardSummaryTests(unittest.TestCase):
    def test_new_course_with_pending_cards_remains_visible_without_invented_discipline(self):
        from contextlib import ExitStack
        from unittest.mock import patch
        from src.courses import service
        from app import app
        course = dict(course_id='histoire-123', title='Archives et histoire', source_filename='archives.pdf')
        with ExitStack() as stack:
            for name, value in [('list_courses', [course]), ('load_course_plan', {'parts':[dict(id='p1', number='1')]}),
                                ('_reviewed_collection', None), ('load_part_cards', []),
                                ('load_part_unavailable', [{'reason':'Lecture à reprendre'}])]:
                stack.enter_context(patch.object(service, name, return_value=value))
            result = app.test_client().get('/api/presentation')
        self.assertEqual(result.status_code, 200)
        data = result.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], course['title'])
        self.assertEqual(data[0]['tag'], 'Cours')
        self.assertTrue(data[0]['pending'])
        self.assertEqual(data[0]['cards'], [])

    def test_summary_does_not_cut_inline_tex_at_character_limit(self):
        formula = r'\(E_\lambda=\operatorname{Ker}(A-\lambda I)\)'
        sections = [{'kind': 'text', 'content': 'Dans un espace vectoriel, ' + formula},
                    {'kind': 'text', 'content': 'Résoudre le système homogène permet de calculer une base.'}]
        self.assertEqual(card_summary(sections, 'Espace propre'), sections[1]['content'])
        self.assertEqual(card_summary(sections[:1], 'Espace propre'), formula)
        sentence = r'\(\cos(n\omega x)\) est une harmonique de la fonction périodique.'
        self.assertEqual(card_summary([{'kind': 'text', 'content': sentence}], 'Harmonique'), r'\(\cos(n\omega x)\)')

    def test_formula_summary_preserves_tex_and_escapes_html(self):
        formula = r'\[a_n=\frac2T\int_0^T f(x)\cos(n\omega x)\,dx\]'
        self.assertEqual(card_summary([{'kind': 'text', 'content': formula}], 'Coefficient'), formula)
        self.assertIn(formula, render_text(formula))
        self.assertNotIn('<img', render_text('<img src=x onerror=alert(1)>'))
