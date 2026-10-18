"""Régressions de fidélité au PDF : OCR, preuves et validation des fiches."""

from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pymupdf

from src.config import COURSE_DATA_DIR, COURSE_PDF_DIR, STUDY_MODEL
from src.courses import cards, inventory
from src.courses.card_grounding import audit_cards, code_issue, proof_issue
from src.courses.planner import extract_document
from src.models.concept import Concept, ConceptInventory
from src.pdf.ocr import extract_page_sources
from src.storage.course_repository import CourseRepository


def syntax_concept(excerpt="CSS Syntax\nbody { color: blue }"):
    return Concept(
        concept_id="css-syntax", title="Syntaxe CSS", source_anchor="CSS Syntax",
        type="syntax", primary_part_id="part-1", source_pages=[2],
        evidence=[{"page": 2, "excerpt": excerpt}],
    )


def syntax_raw(content="body { color: blue }"):
    return [{"concept_id": "css-syntax", "sections": [{"title": "Syntaxe", "content": content}]}]


class CardGroundingTests(unittest.TestCase):
    def setUp(self):
        self.concept = syntax_concept()
        self.pages = [{"page": 2, "raw_text": self.concept.evidence[0].excerpt,
                       "analysis_text": self.concept.evidence[0].excerpt, "headings": ["CSS Syntax"]}]

    def test_label_alone_is_not_enough_and_does_not_call_ai(self):
        concept = syntax_concept("CSS Syntax")
        self.assertIn("titre", proof_issue(concept, self.pages))
        with patch.object(cards, "chat_json") as call:
            with self.assertRaisesRegex(ValueError, "Sources insuffisantes"):
                cards._generate_batch({}, self.pages, [concept], model=STUDY_MODEL)
        call.assert_not_called()

    def test_true_example_is_accepted_with_only_layout_changes(self):
        self.assertIsNone(code_issue("body {\n color: blue\n}", self.concept))
        result = cards._validate_cards(syntax_raw(), [self.concept], self.pages)
        self.assertIn("css-syntax", result)

    def test_invented_inventory_proof_is_rejected_before_generation(self):
        concept = syntax_concept("CSS Syntax\np { color: red; }")
        with patch.object(cards, "chat_json") as call:
            with self.assertRaisesRegex(ValueError, "preuve absente"):
                cards._generate_batch({}, self.pages, [concept], model=STUDY_MODEL)
        call.assert_not_called()

    def test_invented_example_rejects_whole_card_instead_of_leaking_other_sections(self):
        raw = syntax_raw("p { color: red; font-size: 16px; }")
        raw[0]["sections"].insert(0, {"title": "À retenir", "content": "Une règle CSS."})
        diagnostics = {}
        self.assertEqual(cards._validate_cards(raw, [self.concept], self.pages, diagnostics), {})
        self.assertIn("code absent", " ".join(diagnostics["css-syntax"]))

    def test_code_on_same_page_but_outside_concept_proof_is_rejected(self):
        concept = syntax_concept("Inline Styles Uses the style attribute of an HTML tag")
        self.pages[0]["raw_text"] += "\n" + concept.evidence[0].excerpt
        self.assertEqual(cards._validate_cards(syntax_raw(), [concept], self.pages), {})

    def test_code_identifier_case_is_preserved(self):
        concept = syntax_concept('```python\nprint("Hello")\n```')
        self.assertIsNone(code_issue('```python\nprint("Hello")\n```', concept))
        self.assertIn("code absent", code_issue('```python\nprint("hello")\n```', concept))

    def test_plain_attribute_cannot_introduce_a_fictitious_name(self):
        concept = syntax_concept('Use the class attribute in the XHTML.')
        self.assertIn('code absent', code_issue('Attribut : class="nomDeClasse"', concept))
        concept = syntax_concept('Use <div class="footer">Copyright</div>')
        self.assertIsNone(code_issue('Attribut : class="footer"', concept))

    def test_literal_declaration_is_accepted_but_not_completed_or_generalized(self):
        concept = syntax_concept('border-bottom: 2px solid #ff0000')
        self.assertIsNone(code_issue('```css\nborder-bottom: 2px solid #ff0000\n```', concept))
        for fragment in ['border-bottom: 2px solid #ff0000;', 'border-bottom: <largeur> <style> <couleur>']:
            self.assertIn('code absent', code_issue('```css\n' + fragment + '\n```', concept))

    def test_single_retries_receive_the_latest_rejection(self):
        responses = [
            {'cards': syntax_raw('```html\n<head>\n```')},
            {'cards': syntax_raw('```html\n<body>\n```')},
            {'cards': syntax_raw('```html\n<footer>\n```')},
            {'cards': syntax_raw()},
        ]
        with patch.object(cards, 'chat_json', side_effect=responses) as generate, patch.object(cards, 'audit_cards', return_value={}):
            result = cards._generate_batch({}, self.pages, [self.concept], model=STUDY_MODEL)
        self.assertEqual(len(result), 1)
        last_prompt = generate.call_args_list[-1].kwargs['messages'][-1]['content']
        self.assertIn('<footer>', last_prompt)

    def test_unrelated_formula_on_page_is_not_a_source_for_this_concept(self):
        concept = syntax_concept("α = a0")
        self.pages[0]["raw_text"] = "α = a0\nβ = b0"
        self.pages[0]["analysis_text"] = self.pages[0]["raw_text"]
        raw = syntax_raw(r"\[\beta = b_0\]")
        self.assertEqual(cards._validate_cards(raw, [concept], self.pages), {})

    def test_audit_rejects_missing_duplicate_or_incoherent_verdicts(self):
        valid = cards._validate_cards(syntax_raw(), [self.concept], self.pages)
        for payload in [
            {"cards": []},
            {"cards": [{"concept_id": "css-syntax", "supported": True, "issues": ["sans preuve"]}]},
            {"cards": [{"concept_id": "css-syntax", "supported": False, "issues": []}]},
            {"cards": [{"concept_id": "unknown", "supported": True, "issues": []}]},
            {"cards": [{"concept_id": "css-syntax", "supported": True, "issues": []}] * 2},
        ]:
            with self.subTest(payload=payload), patch("src.courses.card_grounding.chat_json", return_value=payload):
                with self.assertRaises(ValueError):
                    audit_cards(valid, [self.concept], model=STUDY_MODEL)

    def test_generation_audits_with_same_model_before_accepting(self):
        good = {"cards": syntax_raw()}
        audit = {"cards": [{"concept_id": "css-syntax", "supported": True, "issues": []}]}
        with patch.object(cards, "chat_json", return_value=good) as generate, patch(
            "src.courses.card_grounding.chat_json", return_value=audit,
        ) as check:
            result = cards._generate_batch({}, self.pages, [self.concept], model=STUDY_MODEL)
        self.assertEqual(len(result), 1)
        self.assertEqual(generate.call_args.kwargs["model"], check.call_args.kwargs["model"])
        self.assertIn("body { color: blue }", check.call_args.kwargs["messages"][-1]["content"])

    def test_unsupported_prose_is_retried_and_failure_is_visible(self):
        raw = syntax_raw("Toutes les déclarations doivent toujours finir par un point-virgule.")
        reject = {"cards": [{"concept_id": "css-syntax", "supported": False, "issues": ["règle universelle absente des preuves"]}]}
        with patch.object(cards, "chat_json", return_value={"cards": raw}) as generate, patch(
            "src.courses.card_grounding.chat_json", return_value=reject,
        ):
            with self.assertRaisesRegex(ValueError, "règle universelle"):
                cards._generate_batch({}, self.pages, [self.concept], model=STUDY_MODEL)
        self.assertIn("règle universelle", generate.call_args.kwargs["messages"][-1]["content"])

    def test_ocr_failure_is_visible_instead_of_silently_omitting_image(self):
        page = Mock(number=1)
        page.get_text.side_effect = ["native", {"blocks": [{"type": 1, "bbox": [0, 0, 50, 50]}]}]
        page.get_textpage_ocr.side_effect = RuntimeError("traineddata absent")
        with self.assertRaisesRegex(ValueError, "OCR indisponible à la page 2"):
            extract_page_sources(page)


class TargetedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = CourseRepository(Path(self.folder.name))
        self.course = {"course_id": "css", "source_filename": "css.pdf", "file_hash": "a" * 64}
        self.plan = {"parts": [
            {"id": f"part-{n}", "number": str(n), "title": f"Partie {n}", "page_start": n, "page_end": n}
            for n in (1, 2)
        ]}
        self.document = {"file_hash": "a" * 64, "pages": [
            {"page": n, "raw_text": "CSS Syntax\nbody { color: blue }", "analysis_text": "CSS Syntax\nbody { color: blue }", "headings": ["CSS Syntax"]}
            for n in (1, 2)
        ]}
        self.saved = ConceptInventory(
            course_id="css", file_hash="a" * 64, model=STUDY_MODEL,
            parts=[{"part_id": f"part-{n}", "part_number": str(n), "status": "complete", "concepts_found": 1, "concepts_added_by_audit": 0} for n in (1, 2)],
            concepts=[syntax_concept().model_copy(update={
                "concept_id": f"c{n}", "primary_part_id": f"part-{n}", "source_pages": [n],
                "evidence": [syntax_concept().evidence[0].model_copy(update={"page": n})],
            }) for n in (1, 2)],
        )
        self.repo.save_inventory("css", self.saved.model_dump(mode="json"))
        self.replies = [{"concepts": [{"title": "Syntaxe CSS", "source_anchor": "CSS Syntax", "type": "syntax", "source_pages": [1],
                                         "evidence": [{"page": 1, "excerpt": "CSS Syntax\nbody { color: blue }"}]}]}, {"missing_concepts": []}]

    def context(self, call):
        stack = ExitStack()
        for name, value in [("load_course", self.course), ("load_course_plan", self.plan),
                            ("extract_document", self.document), ("CourseRepository", self.repo)]:
            stack.enter_context(patch.object(inventory, name, return_value=value))
        stack.enter_context(patch.object(inventory, "chat_json", call))
        return stack

    def test_unknown_part_does_not_change_saved_inventory_or_call_model(self):
        before = deepcopy(self.repo.load_inventory("css"))
        call = Mock()
        with self.context(call), self.assertRaisesRegex(ValueError, "Parties inconnues"):
            inventory.build_inventory("css", redo_parts={"9"})
        call.assert_not_called()
        self.assertEqual(self.repo.load_inventory("css"), before)

    def test_incompatible_cache_does_not_trigger_whole_course_rebuild(self):
        self.saved.model = "autre-modele"
        self.repo.save_inventory("css", self.saved.model_dump(mode="json"))
        before = deepcopy(self.repo.load_inventory("css"))
        call = Mock()
        with self.context(call), self.assertRaisesRegex(ValueError, "Reprise ciblée impossible"):
            inventory.build_inventory("css", redo_parts={"1"})
        call.assert_not_called()
        self.assertEqual(self.repo.load_inventory("css"), before)

    def test_failed_audit_commits_no_selected_concept_and_keeps_other_part(self):
        call = Mock(side_effect=[self.replies[0], RuntimeError("audit indisponible"), RuntimeError("audit indisponible")])
        with self.context(call):
            result = inventory.build_inventory("css", redo_parts={"1"})
        self.assertEqual(result.concepts, [self.saved.concepts[1]])
        self.assertEqual(next(p for p in result.parts if p.part_number == "2"), self.saved.parts[1])
        self.assertEqual(next(p for p in result.parts if p.part_number == "1").status, "error")
        self.assertEqual(ConceptInventory.model_validate(self.repo.load_inventory("css")).concepts, result.concepts)

    def test_unselected_error_is_preserved_without_model_call_for_it(self):
        self.saved.parts[1].status = "error"
        self.saved.parts[1].concepts_found = 0
        self.saved.parts[1].message = "ancienne erreur de partie 2"
        self.saved.concepts = self.saved.concepts[:1]
        self.repo.save_inventory("css", self.saved.model_dump(mode="json"))
        call = Mock(side_effect=self.replies)
        with self.context(call):
            result = inventory.build_inventory("css", redo_parts={"1"})
        self.assertEqual(call.call_count, 2)
        self.assertEqual(next(p for p in result.parts if p.part_number == "2"), self.saved.parts[1])

    def test_preview_by_title_survives_changed_concept_index(self):
        self.saved.concepts[0].title = "Autre notion"
        self.repo.save_inventory("css", self.saved.model_dump(mode="json"))
        with ExitStack() as stack:
            for name, value in [("load_course", self.course), ("load_course_plan", self.plan),
                                ("extract_document", self.document), ("CourseRepository", self.repo)]:
                stack.enter_context(patch.object(cards, name, return_value=value))
            generate = stack.enter_context(patch.object(cards, "_generate_batch", return_value=[Mock()]))
            from src.courses.pedagogy import Material
            with patch.object(cards, "prepare_material", return_value=Material(self.saved, "test")):
                concept, _ = cards.preview_card("css", concept_title="Syntaxe CSS")
        self.assertEqual(concept.concept_id, "c2")
        self.assertEqual(generate.call_args.args[2], [concept])

    def test_preview_by_ambiguous_title_does_not_call_model(self):
        with ExitStack() as stack:
            for name, value in [("load_course", self.course), ("load_course_plan", self.plan), ("CourseRepository", self.repo)]:
                stack.enter_context(patch.object(cards, name, return_value=value))
            generate = stack.enter_context(patch.object(cards, "_generate_batch"))
            with self.assertRaisesRegex(ValueError, "correspond à 2 notions"):
                cards.preview_card("css", concept_title="Syntaxe CSS")
        generate.assert_not_called()


class GenericPartialCardsTests(unittest.TestCase):
    def setUp(self):
        # Ces tests isolent le générateur ; la lecture complète est testée dans test_pedagogy.
        from src.courses.pedagogy import Material
        patcher = patch.object(cards, "prepare_material", side_effect=lambda inventory, *args, **kw: Material(inventory, "test"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_partial_generation_resume_and_repaired_source_across_subjects(self):
        for subject, title, explanation in [
            ('biologie', 'Cellule', 'La cellule constitue une unité du vivant.'),
            ('histoire', 'Chronologie', 'La chronologie ordonne les événements dans le temps.'),
            ('mathematiques', 'Suite', 'Une suite associe un nombre à chaque entier naturel.'),
        ]:
            with self.subTest(subject=subject), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                repo = CourseRepository(Path(folder))
                course = {'course_id': subject, 'file_hash': 'a' * 64, 'source_filename': 'cours.pdf'}
                plan = {'parts': [{'id': 'p1', 'number': '1'}, {'id': 'p2', 'number': '2'}]}
                good = Concept(concept_id='good', title=title, type='definition', primary_part_id='p1',
                               source_pages=[1], evidence=[{'page': 1, 'excerpt': explanation}])
                weak = Concept(concept_id='weak', title='Méthode', type='method', primary_part_id='p1',
                               source_pages=[1], evidence=[{'page': 1, 'excerpt': 'Méthode'}])
                other = weak.model_copy(update={'concept_id': 'other', 'primary_part_id': 'p2'})
                saved = ConceptInventory(course_id=subject, file_hash=course['file_hash'], model=STUDY_MODEL,
                    concepts=[good, weak, other], parts=[
                        {'part_id': p['id'], 'part_number': p['number'], 'status': 'complete',
                         'concepts_found': 2 if p['id'] == 'p1' else 1, 'concepts_added_by_audit': 0}
                        for p in plan['parts']])
                path = repo.save_inventory(subject, saved.model_dump(mode='json'))
                original = path.read_bytes()
                page = {'page': 1, 'raw_text': explanation + '\nMéthode', 'analysis_text': explanation + '\nMéthode'}
                document = {'file_hash': course['file_hash'], 'pages': [page]}
                for name, value in [('load_course', course), ('load_course_plan', plan),
                                    ('extract_document', document), ('CourseRepository', repo)]:
                    stack.enter_context(patch.object(cards, name, return_value=value))
                def generate(part, pages, concepts, **kwargs):
                    raw = [{'concept_id': c.concept_id, 'sections': [{'title': 'Définition', 'content': c.evidence[0].excerpt}]} for c in concepts]
                    return list(cards._validate_cards(raw, concepts, pages).values())
                call = stack.enter_context(patch.object(cards, '_generate_batch', side_effect=generate))
                result = cards.build_cards(subject)
                self.assertEqual([c.concept_id for c in result.cards], ['good'])
                self.assertEqual([c.concept_id for c in result.blocked], ['weak', 'other'])
                self.assertEqual([p.status for p in result.parts], ['partial', 'partial'])
                self.assertEqual(cards.cards_summary(result)['blocked_concepts'], 2)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(cards.build_cards(subject), result)
                self.assertEqual(call.call_count, 1)
                # Une preuve réellement ajoutée permet de reprendre la notion bloquée.
                repaired_text = 'Méthode : comparer les observations puis décrire les différences.'
                for c in saved.concepts[1:]:
                    c.evidence[0].excerpt = repaired_text
                page['raw_text'] += '\n' + repaired_text
                page['analysis_text'] = page['raw_text']
                repo.save_inventory(subject, saved.model_dump(mode='json'))
                repaired = cards.build_cards(subject)
                self.assertEqual(len(repaired.cards), 3)
                self.assertEqual(repaired.blocked, [])
                self.assertTrue(all(p.status == 'complete' for p in repaired.parts))
                # Une panne de génération reste une erreur, pas une source insuffisante.
                call.side_effect = ConnectionError('Modèle indisponible')
                failed = cards.build_cards(subject, force=True)
                self.assertEqual(failed.cards, [])
                self.assertEqual(failed.blocked, [])
                self.assertTrue(all(p.status == 'error' for p in failed.parts))
                call.side_effect = generate
                resumed = cards.build_cards(subject)
                self.assertEqual(len(resumed.cards), 3)
                self.assertTrue(all(p.status == 'complete' for p in resumed.parts))


class GenericSourceUnitTests(unittest.TestCase):
    def test_nested_conditions_and_tagged_heading_on_non_css_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document_scientifique.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                lines = [
                    (50, 60, 18, "Etude du <module>"),
                    (90, 95, 14, "Conditions:"),
                    (110, 115, 11, "Le signal est positif."),
                    (110, 135, 11, "La mesure est disponible."),
                    (90, 175, 14, "Resultat:"),
                    (110, 195, 11, "Le modele fournit une estimation."),
                    (110, 215, 14, "alpha < beta"),
                    (50, 260, 18, "Second sujet"),
                    (90, 285, 11, "Ce paragraphe appartient au sujet suivant."),
                    (90, 305, 11, "Les deux rubriques restent distinctes."),
                ]
                for x, y, size, value in lines:
                    page.insert_text((x, y), value, fontsize=size)
                pdf.save(path)
            document = extract_document(path)
            units = {u["heading"]: u for u in document["pages"][0]["source_units"]}
            root = units["Etude du <module>"]["excerpt"]
            self.assertIn("Le signal est positif", root)
            self.assertIn("Le modele fournit", root)
            self.assertIn("alpha < beta", root)
            self.assertNotIn("Second sujet", root)
            self.assertNotIn("Resultat", units["Conditions"]["excerpt"])
            self.assertNotIn("alpha < beta", units)


CSS_FOLDER = COURSE_DATA_DIR / "cours-de-css-db7e58791b"


@unittest.skipUnless((CSS_FOLDER / "course.json").exists(), "PDF CSS réel non fourni")
class RealCSSSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = json.loads((CSS_FOLDER / "course.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((CSS_FOLDER / "plan.json").read_text(encoding="utf-8"))
        cls.document = extract_document(COURSE_PDF_DIR / cls.course["source_filename"])

    def test_ocr_recovers_body_blue_and_preserves_native_text(self):
        page = self.document["pages"][1]
        with pymupdf.open(COURSE_PDF_DIR / self.course["source_filename"]) as pdf:
            self.assertEqual(page["raw_text"], pdf[1].get_text("text", sort=False))
        self.assertNotIn("body { color: blue }", page["raw_text"])
        self.assertIn("body { color: blue }", page["ocr_text"])

    def test_definition_recovers_explanation_after_generic_question(self):
        raw = [{"title": "Définition du CSS", "source_anchor": "What is CSS?", "type": "definition",
                "source_pages": [2], "evidence": [{"page": 2, "excerpt": "What is CSS?"}]}]
        result = inventory._validate_ai_concepts(raw, file_hash=self.course["file_hash"], part=self.plan["parts"][0], pages=self.document["pages"][:3])
        concept = result[0]
        self.assertIsNone(concept.evidence_issue)
        self.assertIn("CSS is a language", concept.evidence[0].excerpt)
        self.assertIn("CSS describes how HTML", concept.evidence[0].excerpt)
        self.assertNotIn("CSS Syntax", concept.evidence[0].excerpt)

    def test_colour_unit_does_not_include_neighboring_declarations_or_scheme(self):
        page = self.document["pages"][2]
        concept = Concept(concept_id="colour", title="Configuration de la couleur", type="method", primary_part_id=self.plan["parts"][0]["id"],
                          source_pages=[3], evidence=[{"page": 3, "excerpt": page["evidence_text"][page["evidence_text"].index("• Configuring Color"):][:1100]}])
        repaired = inventory.refresh_concept_evidence(concept, [page])
        self.assertIsNone(repaired.evidence_issue)
        self.assertIn("color: #0000FF;", repaired.evidence[0].excerpt)
        self.assertNotIn("Three Ways", repaired.evidence[0].excerpt)
        self.assertNotIn("How to choose", repaired.evidence[0].excerpt)

    def test_bare_property_is_signalled_during_inventory_without_borrowing_code(self):
        for name in ("background-color", "margin", "font-height"):
            raw = [{"title": f"Propriété {name}", "source_anchor": name, "type": "property", "source_pages": [3], "evidence": [{"page": 3, "excerpt": name}]}]
            with self.subTest(name=name):
                result = inventory._validate_ai_concepts(raw, file_hash=self.course["file_hash"], part=self.plan["parts"][0], pages=self.document["pages"][:3])
                self.assertEqual(result[0].evidence[0].excerpt, name)
                self.assertIn("identifiant", result[0].evidence_issue)

    def test_colour_property_recovers_declaration_from_its_named_teaching_unit(self):
        concept = Concept(concept_id="color", title="Propriété color", source_anchor="color", type="property", primary_part_id="part-1", source_pages=[3],
                          evidence=[{"page": 3, "excerpt": "color"}])
        repaired = inventory.refresh_concept_evidence(concept, [self.document["pages"][2]])
        self.assertIsNone(repaired.evidence_issue)
        self.assertEqual(repaired.evidence[0].excerpt, "color: red;")
        self.assertNotIn("background-color", repaired.evidence[0].excerpt)

    def test_cached_wrong_border_proof_recovers_only_its_literal_declaration(self):
        concept = Concept(concept_id="border-bottom", title="Propriété border-bottom", type="property", primary_part_id=self.plan["parts"][2]["id"],
                          source_pages=[8], evidence=[{"page": 8, "excerpt": "The CSS border-style property"}])
        repaired = inventory.refresh_concept_evidence(concept, [self.document["pages"][7]])
        self.assertIsNone(repaired.evidence_issue)
        self.assertEqual(repaired.title, concept.title)
        self.assertEqual(repaired.concept_id, concept.concept_id)
        self.assertEqual(repaired.source_pages, concept.source_pages)
        self.assertIn("border-bottom: 2px solid #ff0000", repaired.evidence[0].excerpt)
        self.assertNotIn("border-style", repaired.evidence[0].excerpt)

    def test_real_footer_recovers_missing_end_without_neighboring_selector(self):
        concept = Concept(concept_id="footer", title="Footer", type="concept", primary_part_id="part-7",
            source_pages=[22], evidence=[{"page": 22, "excerpt": "#footer {font-size: xx-small; text-align: center; clear: right;"}])
        repaired = inventory.refresh_concept_evidence(concept, [self.document["pages"][21]])
        self.assertIn("padding-bottom: 20px; }", repaired.evidence[0].excerpt)
        self.assertNotIn("div#leftcolumn", repaired.evidence[0].excerpt)

    def test_real_link_subtitle_recovers_its_own_example(self):
        concept = Concept(concept_id="link", title="Ouvrir un lien dans une nouvelle fenêtre", type="method", primary_part_id="part-8",
            source_pages=[24], evidence=[{"page": 24, "excerpt": "Opening a link in a new browser window"}])
        repaired = inventory.refresh_concept_evidence(concept, [self.document["pages"][23]])
        self.assertIn("_blank", repaired.evidence[0].excerpt)
        self.assertNotIn("Pseudo-classes", repaired.evidence[0].excerpt)

    def test_real_liquid_design_label_is_blocked(self):
        concept = Concept(concept_id="liquid", title="Liquid Design", type="concept", primary_part_id="part-5",
            source_pages=[15], evidence=[{"page": 15, "excerpt": "Liquid Design"}])
        pages = [self.document["pages"][14]]
        self.assertIn("titre", inventory.concept_evidence_issue(concept, pages))
        repaired = inventory.refresh_concept_evidence(concept, pages)
        # L'OCR des images peut enrichir l'unité différemment selon la plateforme.
        # Un titre seul reste bloqué ; une réparation doit ajouter une vraie citation.
        if repaired.evidence_issue is None:
            self.assertNotEqual(repaired.evidence, concept.evidence)
            self.assertTrue(all(inventory._excerpt_is_grounded(e.excerpt, pages[0]) for e in repaired.evidence))
            self.assertIsNone(inventory.concept_evidence_issue(repaired, pages))
        else:
            self.assertIn("titre", repaired.evidence_issue)

    def test_class_id_parent_keeps_both_conditions_and_stops_before_div(self):
        page = self.document["pages"][5]
        concept = Concept(concept_id="choice", title="Choisir entre classe et ID", type="remark", primary_part_id="part-2", source_pages=[6],
                          evidence=[{"page": 6, "excerpt": "Deciding to Configure a class or id"}])
        repaired = inventory.refresh_concept_evidence(concept, [page])
        self.assertIsNone(repaired.evidence_issue)
        self.assertIn("If the style may apply to more than one element", repaired.evidence[0].excerpt)
        self.assertIn("If the style is specific to only one element", repaired.evidence[0].excerpt)
        self.assertNotIn("The <div>", repaired.evidence[0].excerpt)

    def test_html_names_in_headings_do_not_mix_block_and_inline_explanations(self):
        page = self.document["pages"][5]
        for name, phrase, forbidden in [("div", "A block-level element", "An inline element"), ("span", "An inline element", "A block-level element")]:
            with self.subTest(name=name):
                concept = Concept(concept_id=name, title=f"Élément HTML <{name}>", type="concept", primary_part_id="part-2", source_pages=[6],
                                  evidence=[{"page": 6, "excerpt": f"The <{name}> HTML Element"}])
                repaired = inventory.refresh_concept_evidence(concept, [page])
                self.assertIsNone(repaired.evidence_issue)
                self.assertIn(phrase, repaired.evidence[0].excerpt)
                self.assertNotIn(forbidden, repaired.evidence[0].excerpt)

    def test_private_font_bullet_is_supported_for_container_heading(self):
        page = self.document["pages"][22]
        concept = Concept(concept_id="container", title="Container", type="concept", primary_part_id="part-7", source_pages=[23],
                          evidence=[{"page": 23, "excerpt": "Container"}])
        repaired = inventory.refresh_concept_evidence(concept, [page])
        self.assertIsNone(repaired.evidence_issue)
        self.assertIn("sets default background color", repaired.evidence[0].excerpt)
        self.assertNotIn("Left-column", repaired.evidence[0].excerpt)

    def test_property_repair_accepts_own_declaration_but_not_neighbor_or_bare_mention(self):
        page = self.document["pages"][8]
        for name, has_declaration in [("padding-left", True), ("padding-right", False)]:
            with self.subTest(name=name):
                concept = Concept(concept_id=name, title=f"Propriété {name}", type="property", primary_part_id="part-3", source_pages=[9],
                                  evidence=[{"page": 9, "excerpt": name}])
                repaired = inventory.refresh_concept_evidence(concept, [page])
                if has_declaration:
                    self.assertIsNone(repaired.evidence_issue)
                    self.assertEqual(repaired.evidence[0].excerpt, "padding-left: 5px;")
                else:
                    self.assertIsNotNone(repaired.evidence_issue)
                    self.assertNotIn("padding-left", repaired.evidence[0].excerpt)

    def test_wrong_identifier_with_no_direct_declaration_remains_flagged(self):
        page = {"page": 8, "analysis_text": "The border-style property\nborder-bottom\nborder-left: 5px;", "headings": ["The border-style property"]}
        concept = Concept(concept_id="bad", title="Propriété border-bottom", type="property", primary_part_id="part-3", source_pages=[8],
                          evidence=[{"page": 8, "excerpt": "The border-style property"}])
        repaired = inventory.refresh_concept_evidence(concept, [page])
        self.assertIn("border-bottom", repaired.evidence_issue)
        self.assertEqual(repaired.evidence, concept.evidence)

    def test_repair_preserves_identities_coverage_and_backup_and_calls_no_model(self):
        # Le scénario doit rester identique après réparation de l'inventaire utilisateur.
        part_id = self.plan["parts"][0]["id"]
        saved = ConceptInventory(
            course_id=self.course["course_id"], file_hash=self.course["file_hash"],
            model=STUDY_MODEL,
            parts=[{"part_id": part_id, "part_number": "1", "status": "complete",
                    "concepts_found": 2, "concepts_added_by_audit": 0}],
            concepts=[
                Concept(concept_id="repair-definition", title="Définition du CSS",
                        source_anchor="What is CSS?", type="definition", primary_part_id=part_id,
                        source_pages=[2], evidence=[{"page": 2, "excerpt": "What is CSS?"}]),
                Concept(concept_id="repair-syntax", title="Syntaxe CSS",
                        source_anchor="CSS Syntax", type="syntax", primary_part_id=part_id,
                        related_part_ids=[self.plan["parts"][1]["id"]],
                        source_pages=[2], evidence=[{"page": 2, "excerpt": "CSS Syntax"}]),
            ],
        )
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder))
            path = repo.save_inventory(self.course["course_id"], saved.model_dump(mode="json"))
            original_bytes = path.read_bytes()
            stack.enter_context(patch.object(inventory, "load_course", return_value=self.course))
            stack.enter_context(patch.object(inventory, "extract_document", return_value=self.document))
            stack.enter_context(patch.object(inventory, "CourseRepository", return_value=repo))
            call = stack.enter_context(patch.object(inventory, "chat_json"))
            repaired, backup, changed = inventory.repair_inventory_evidence(self.course["course_id"])
            self.assertEqual(changed, 2)
            self.assertIn("CSS is a language", repaired.concepts[0].evidence[0].excerpt)
            self.assertIn("body { color: blue }", repaired.concepts[1].evidence[0].excerpt)
            self.assertEqual(Path(backup).read_bytes(), original_bytes)
            self.assertEqual(repaired.parts, saved.parts)
            self.assertEqual(repaired.model, saved.model)
            self.assertEqual(len(repaired.concepts), len(saved.concepts))
            for old, new in zip(saved.concepts, repaired.concepts):
                for field in ("concept_id", "title", "source_anchor", "type", "primary_part_id", "related_part_ids", "source_pages"):
                    self.assertEqual(getattr(old, field), getattr(new, field))
            self.assertNotEqual(cards._inventory_hash(saved), cards._inventory_hash(repaired))
            self.assertEqual(inventory.repair_inventory_evidence(self.course["course_id"]), (repaired, None, 0))
            call.assert_not_called()

    def test_changed_pdf_refuses_repair_before_modifying_inventory(self):
        data = json.loads((CSS_FOLDER / "inventory.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder))
            path = repo.save_inventory(self.course["course_id"], data)
            original_bytes = path.read_bytes()
            stack.enter_context(patch.object(inventory, "load_course", return_value=self.course))
            stack.enter_context(patch.object(inventory, "extract_document", return_value={**self.document, "file_hash": "b" * 64}))
            stack.enter_context(patch.object(inventory, "CourseRepository", return_value=repo))
            with self.assertRaisesRegex(ValueError, "réparation refusée"):
                inventory.repair_inventory_evidence(self.course["course_id"])
            self.assertEqual(path.read_bytes(), original_bytes)

    def test_heading_proof_is_enriched_from_its_own_unit_only(self):
        raw = [{"title": "Syntaxe CSS", "source_anchor": "CSS Syntax", "type": "syntax",
                "source_pages": [2], "evidence": [{"page": 2, "excerpt": "CSS Syntax"}]}]
        result = inventory._validate_ai_concepts(
            raw, file_hash=self.course["file_hash"], part=self.plan["parts"][0],
            pages=self.document["pages"][:3],
        )
        self.assertEqual(result[0].source_anchor, "CSS Syntax")
        self.assertIn("body { color: blue }", result[0].evidence[0].excerpt)
        self.assertNotIn("Three ways", result[0].evidence[0].excerpt)
        self.assertNotIn("Inline Styles", result[0].evidence[0].excerpt)

    def test_border_style_is_not_a_proof_for_border_bottom(self):
        raw = [{"title": "Propriété border-bottom", "source_anchor": "The CSS border-style property",
                "type": "property", "source_pages": [8],
                "evidence": [{"page": 8, "excerpt": "The CSS border-style property"}]}]
        with self.assertRaisesRegex(ValueError, "Preuves non pertinentes"):
            inventory._validate_ai_concepts(
                raw, file_hash=self.course["file_hash"], part=self.plan["parts"][2],
                pages=self.document["pages"][6:9],
            )

    def test_french_word_en_is_not_treated_as_a_mathematical_notation(self):
        raw = [{"title": "Styles en ligne", "source_anchor": "Inline Styles", "type": "concept",
                "source_pages": [2], "evidence": [{"page": 2, "excerpt": "Inline Styles"}]}]
        result = inventory._validate_ai_concepts(
            raw, file_hash=self.course["file_hash"], part=self.plan["parts"][0],
            pages=self.document["pages"][:3],
        )
        self.assertEqual(result[0].title, "Styles en ligne")

    def test_targeted_rebuild_keeps_other_seven_parts(self):
        data = json.loads((CSS_FOLDER / "inventory.json").read_text(encoding="utf-8"))
        data.update(schema_version=3, model=STUDY_MODEL)
        saved = ConceptInventory.model_validate(data)
        target = self.plan["parts"][0]["id"]
        old = {c.concept_id: c for c in saved.concepts if c.primary_part_id != target and target not in c.related_part_ids}
        replies = [{"concepts": [{"title": "Syntaxe CSS", "source_anchor": "CSS Syntax", "type": "syntax",
                    "source_pages": [2], "evidence": [{"page": 2, "excerpt": "CSS Syntax"}]}]}, {"missing_concepts": []}]
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder))
            repo.save_inventory(self.course["course_id"], saved.model_dump(mode="json"))
            stack.enter_context(patch.object(inventory, "load_course", return_value=self.course))
            stack.enter_context(patch.object(inventory, "load_course_plan", return_value=self.plan))
            stack.enter_context(patch.object(inventory, "extract_document", return_value=self.document))
            stack.enter_context(patch.object(inventory, "CourseRepository", return_value=repo))
            call = stack.enter_context(patch.object(inventory, "chat_json", side_effect=replies))
            progress = []
            result = inventory.build_inventory(self.course["course_id"], redo_parts={"1"}, progress_callback=lambda *a: progress.append(a))
            self.assertEqual(call.call_count, 2)
            self.assertEqual(sum(p[-1] == "cached" for p in progress), 7)
            self.assertEqual(inventory.inventory_summary(result)["error_parts"], 0)
            by_id = {c.concept_id: c for c in result.concepts}
            for identifier, concept in old.items():
                self.assertEqual(by_id[identifier], concept)


if __name__ == "__main__":
    unittest.main()
