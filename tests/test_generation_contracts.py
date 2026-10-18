"""Contrat utilisateur : bref, structuré, sûr, régénérable sans matière imposée."""
import copy
import unittest
from unittest.mock import patch
from src.courses.overview import is_current, validate_overview, overview_view
from src.courses.planner import generate_overviews


ANSWER = dict(summary="Le classement organise les documents, tandis que l’indexation permet de les retrouver par sujet.",
              learning_objectives=['Distinguer classement et indexation.'],
              key_concepts=['Classement', 'Indexation'], prerequisites=[], why_important='')


class GenerationContractTests(unittest.TestCase):
    def test_shared_json_preserves_math_and_rejects_silently_overwritten_notions(self):
        from src.ai.client import parse_json_response
        from src.courses.planner import _json_ollama
        from types import SimpleNamespace
        raw = r'{"summary":"Une notation \(u_n=\frac{1}{2}\) conservée."}'
        with patch('src.courses.planner.chat', return_value=SimpleNamespace(message=SimpleNamespace(content=raw))):
            self.assertEqual(_json_ollama('prompt', 'test')['summary'], r'Une notation \(u_n=\frac{1}{2}\) conservée.')
        for raw in ['{"concepts":[1],"concepts":[2]}', '{"outer":{"a":1,"a":2}}']:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'dupliquée'):
                parse_json_response(raw)

    def test_accented_formula_title_does_not_invent_mathematical_symbols(self):
        from src.courses.inventory import _notation_tokens, _validate_ai_concepts
        title = "Terme général d’une suite géométrique"
        quote = 'Pour tout entier n supérieur ou égal à zéro, le terme général est : u_n = u_0 * q^n'
        self.assertEqual(_notation_tokens(title), set())
        self.assertTrue({'un', 'u0', 'qn'} <= _notation_tokens(quote))
        raw = [dict(title=title, source_anchor='le terme général est :', type='formula',
                    source_pages=[1], evidence=[dict(page=1, excerpt=quote)])]
        concepts = _validate_ai_concepts(raw, file_hash='a'*64, part={'id':'p1'},
            pages=[dict(page=1, raw_text=quote, analysis_text=quote)])
        self.assertEqual(len(concepts), 1)

    def test_mathematical_example_is_not_presented_as_a_code_reference(self):
        from src.courses.card_grounding import source_code_snippets
        from src.models.concept import Concept
        concept = Concept(concept_id='geom', title='Suite géométrique', type='formula',
            primary_part_id='p1', source_pages=[1], evidence=[dict(page=1, excerpt='Exemple : si u_0 = 3 et q = 2, u_3 = 24.')])
        self.assertEqual(source_code_snippets(concept), {})
        from src.models.concept import ConceptEvidence
        prop = concept.model_copy(update=dict(type='property', source_anchor='margin',
            evidence=[ConceptEvidence(page=1, excerpt='margin: 3px')]))
        self.assertEqual(source_code_snippets(prop), {'code-1':'margin: 3px'})

    def test_wrapped_prose_requires_reselection_without_rewriting_source(self):
        from src.courses.pedagogy import check_wrapped_prose, complete_wrapped_selection, Fact
        lines = [dict(id=1, text='Un document peut recevoir plusieurs mots-clés. Par exemple, un\n'),
                 dict(id=2, text='rapport peut être indexé avec transport et énergie.\n')]
        with self.assertRaisesRegex(ValueError, 'continuation'):
            check_wrapped_prose(lines[0]['text'], 'explanation', 1, lines)
        complete = ''.join(line['text'] for line in lines)
        check_wrapped_prose(complete, 'explanation', 2, lines)
        check_wrapped_prose(lines[0]['text'], 'formula', 1, lines)
        fact = Fact(title='Indexation', kind='explanation', start_line=1, end_line=1)
        fixed, quote, original = complete_wrapped_selection(fact, lines)
        self.assertEqual(quote, complete)
        self.assertEqual((fact.end_line, original['end_line'], fixed.end_line), (1,1,2))
        unrelated = [lines[0], dict(id=2, text='def unrelated():\n')]
        with self.assertRaises(ValueError):
            complete_wrapped_selection(fact, unrelated)
        wrapped = [dict(id=1, text='Le classement chronologique suit la date des documents. Il convient de conserver le même\n'),
                   dict(id=2, text='critère dans un groupe.\n')]
        fixed, quote, _ = complete_wrapped_selection(fact, wrapped)
        self.assertEqual(fixed.end_line, 2)
        self.assertIn('le même\ncritère', quote)

    def test_contract_rejects_dense_or_unstructured_output_without_cutting_it(self):
        for change in [dict(summary='mot '*80), dict(summary=r'La formule du cours est \(u_n=q^n\), à appliquer chaque fois.'),
                       dict(learning_objectives=[]), dict(prerequisites='aucun'), dict(why_important='mot '*40)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_overview({**ANSWER, **change})
        self.assertEqual(validate_overview(ANSWER), ANSWER)

    def test_old_draft_regenerates_failed_contract_retries_and_current_cache_is_reused(self):
        plan = {'parts': [dict(number='1', title='Archives', page_start=1, page_end=1,
                               overview=dict(status='draft', summary='Ancien résumé '*80))]}
        document = {'pages': [dict(page=1, analysis_text='Le classement organise les documents selon un critère.') ]}
        with patch('src.courses.planner._json_ollama', side_effect=[{**ANSWER, 'summary':'mot '*90}, ANSWER]) as call:
            generate_overviews(plan, document)
        self.assertEqual(call.call_count, 2)
        self.assertIn('Corrige ces défauts', call.call_args.args[0])
        self.assertTrue(is_current(plan['parts'][0]['overview']))
        before = copy.deepcopy(plan)
        with patch('src.courses.planner._json_ollama') as call:
            generate_overviews(plan, document)
        call.assert_not_called()
        self.assertEqual(plan, before)

    def test_shared_view_escapes_html_and_preserves_complete_math_and_legacy_content(self):
        text = r'\(x=\frac{1}{2}\) <img src=x onerror=alert(1)>'
        view = overview_view(dict(status='draft', summary=text))
        self.assertTrue(view['legacy'])
        self.assertNotIn('<img', view['summary_html'])
        self.assertIn(r'\frac{1}{2}', view['summary_html'])
        view = overview_view(dict(ANSWER, status='draft', content_version=2))
        self.assertFalse(view['legacy'])
        self.assertEqual(len(view['objectives']), 1)
