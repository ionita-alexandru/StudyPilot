"""Contrat JSON strict, reprises et preuves des réponses d'inventaire."""

from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from src.ai import client
from src.config import COURSE_DATA_DIR, COURSE_PDF_DIR, STUDY_MODEL
from src.courses import inventory
from src.courses.planner import extract_document
from src.models.concept import Concept, ConceptInventory
from src.storage.course_repository import CourseRepository


def css_concept():
    return {
        "title": "Pseudo-classe :hover",
        "source_anchor": ":hover",
        "type": "syntax",
        "source_pages": [24],
        "evidence": [{"page": 24, "excerpt": "#button a:hover { color:#66CCFF;"}],
    }


class JSONSchemaClientTests(unittest.TestCase):
    def test_schema_is_visible_in_prompt_without_mutating_messages(self):
        messages = [
            {"role": "system", "content": "Le PDF est la seule source."},
            {"role": "user", "content": "Inventorie le cours."},
        ]
        original = deepcopy(messages)
        with patch.object(client, "chat_text", return_value='{"concepts": []}') as call:
            client.chat_json(
                response_model=inventory._AIInventoryResponse,
                messages=messages,
            )

        sent = call.call_args.kwargs
        schema = inventory._AIInventoryResponse.model_json_schema()
        self.assertEqual(sent["format"], schema)
        self.assertIn(json.dumps(schema, ensure_ascii=False), sent["messages"][0]["content"])
        self.assertIn("Le PDF est la seule source.", sent["messages"][0]["content"])
        self.assertEqual(sent["messages"][1], original[1])
        self.assertEqual(messages, original)

    def test_schema_is_added_when_there_is_no_system_message(self):
        messages = [{"role": "user", "content": "Inventorie le cours."}]
        with patch.object(client, "chat_text", return_value='{"missing_concepts": []}') as call:
            client.chat_json(response_model=inventory._AIAuditResponse, messages=messages)
        sent = call.call_args.kwargs["messages"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertIn('"missing_concepts"', sent[0]["content"])
        self.assertEqual(sent[1:], messages)
        self.assertEqual(len(messages), 1)

    def test_plain_json_calls_keep_their_original_messages(self):
        messages = [{"role": "user", "content": "Une réponse JSON."}]
        with patch.object(client, "chat_text", return_value='{"ok": true}') as call:
            self.assertEqual(client.chat_json(messages=messages), {"ok": True})
        self.assertEqual(call.call_args.kwargs["messages"], messages)
        self.assertEqual(call.call_args.kwargs["format"], "json")


class InventoryResponseContractTests(unittest.TestCase):
    def setUp(self):
        self.part = {"id": "part-css", "number": "8", "title": "CSS", "page_start": 24, "page_end": 24}
        self.pages = [{
            "page": 24,
            "raw_text": "#button a:hover { color:#66CCFF;",
            "analysis_text": "#button a:hover { color:#66CCFF;",
            "headings": [],
        }]

    def validate(self, raw):
        return inventory._validate_ai_concepts(
            raw, file_hash="a" * 64, part=self.part, pages=self.pages,
        )

    def call(self, key="concepts", response_model=inventory._AIInventoryResponse):
        return inventory._call_with_retry(
            "Le PDF est la seule source.", key, model=STUDY_MODEL,
            response_model=response_model, validator=self.validate,
        )

    def test_single_evidence_object_is_rejected_in_both_passes(self):
        for model, key in [
            (inventory._AIInventoryResponse, "concepts"),
            (inventory._AIAuditResponse, "missing_concepts"),
        ]:
            with self.subTest(key=key):
                bad = css_concept()
                bad["evidence"] = bad["evidence"][0]
                with self.assertRaises(ValidationError):
                    model.model_validate({key: [bad]})

    def test_course_term_is_not_accepted_as_a_pedagogical_type(self):
        bad = dict(css_concept(), type="pseudo-class")
        with self.assertRaises(ValidationError):
            inventory._AIInventoryResponse.model_validate({"concepts": [bad]})

    def test_audit_retries_single_evidence_object_with_exact_field_feedback(self):
        valid = {"missing_concepts": [css_concept()]}
        bad = deepcopy(valid)
        bad["missing_concepts"][0]["evidence"] = bad["missing_concepts"][0]["evidence"][0]
        with patch.object(client, "chat_text", side_effect=[json.dumps(bad), json.dumps(valid)]) as call:
            result = self.call("missing_concepts", inventory._AIAuditResponse)

        self.assertEqual(call.call_count, 2)
        feedback = call.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("missing_concepts.0.evidence", feedback)
        self.assertIn("même pour une seule preuve", feedback)
        self.assertEqual(result[0].title, "Pseudo-classe :hover")
        self.assertEqual(result[0].evidence[0].excerpt, css_concept()["evidence"][0]["excerpt"])

    def test_retry_reports_all_five_invalid_types_without_truncation(self):
        bad = {"concepts": [dict(css_concept(), type="pseudo-class") for _ in range(5)]}
        good = {"concepts": [css_concept()]}
        with patch.object(client, "chat_text", side_effect=[json.dumps(bad), json.dumps(good)]) as call:
            result = self.call()
        feedback = call.call_args.kwargs["messages"][-1]["content"]
        for index in range(5):
            self.assertIn(f"concepts.{index}.type", feedback)
        self.assertEqual(result[0].type, "syntax")

    def test_two_invalid_responses_still_raise_instead_of_being_coerced(self):
        bad = {"concepts": [dict(css_concept(), type="pseudo-class")]}
        with patch.object(client, "chat_text", return_value=json.dumps(bad)) as call:
            with self.assertRaises(ValidationError):
                self.call()
        self.assertEqual(call.call_count, 2)

    def test_valid_schema_does_not_bypass_pdf_grounding(self):
        invented = css_concept()
        invented["source_anchor"] = "notion absent from the PDF"
        invented["evidence"][0]["excerpt"] = "Invented explanation absent from the PDF."
        with patch.object(client, "chat_text", return_value=json.dumps({"concepts": [invented]})):
            with self.assertRaisesRegex(ValueError, "preuve réelle"):
                self.call()

    def test_audit_prompt_explicitly_requires_a_list_even_for_one_quote(self):
        prompt = inventory._audit_prompt(self.part, self.pages, [])
        self.assertIn("evidence est TOUJOURS une liste", prompt)
        self.assertIn("même pour une seule preuve", prompt)

    def test_repetition_error_keeps_its_specific_retry_instructions(self):
        good = {"concepts": [css_concept()]}
        with patch.object(client, "chat_text", side_effect=[
            RuntimeError("prediction aborted, token repeat limit reached"), json.dumps(good),
        ]) as call:
            self.call()
        self.assertIn("boucle de répétition", call.call_args.kwargs["messages"][-1]["content"])


CSS_FOLDER = COURSE_DATA_DIR / "cours-de-css-db7e58791b"


@unittest.skipUnless((CSS_FOLDER / "course.json").exists(), "PDF CSS réel non fourni")
class CSSInventoryReplayTests(unittest.TestCase):
    """Vrai PDF, réponses IA simulées : aucun appel réseau ni donnée modifiée."""

    def test_resume_repairs_parts_3_and_8_and_preserves_six_complete_parts(self):
        course = json.loads((CSS_FOLDER / "course.json").read_text(encoding="utf-8"))
        plan = json.loads((CSS_FOLDER / "plan.json").read_text(encoding="utf-8"))
        document = extract_document(COURSE_PDF_DIR / course["source_filename"])
        # État de départ contrôlé : le vrai inventaire de l'utilisateur peut
        # déjà contenir padding ou :hover et évoluer après chaque génération.
        # Le test de conservation ne doit pas dépendre de ces données vivantes.
        cached = [
            ("1", "Styles en ligne", 2, "Inline Styles"),
            ("2", "Taille de police", 4, "The font-size Property"),
            ("4", "Élément image HTML", 10, "HTML Image Element"),
            ("5", "Icône de favoris", 13, "Favorites Icon"),
            ("6", "Flux normal", 16, "Normal Flow"),
            ("7", "Disposition à deux colonnes", 21, "Two Column Page Layout"),
        ]
        parts_by_number = {part["number"]: part for part in plan["parts"]}
        saved_data = {
            "schema_version": 3, "course_id": course["course_id"],
            "file_hash": course["file_hash"], "model": STUDY_MODEL,
            "parts": [], "concepts": [],
        }
        for number, title, page_number, anchor in cached:
            part = parts_by_number[number]
            page = next(p for p in document["pages"] if p["page"] == page_number)
            excerpt = inventory._source_evidence_for_title(anchor, page)
            self.assertIsNotNone(excerpt, f"Preuve de fixture absente : {anchor}")
            self.assertTrue(inventory._excerpt_is_grounded(excerpt, page))
            saved_data["parts"].append({
                "part_id": part["id"], "part_number": number, "status": "complete",
                "concepts_found": 1, "concepts_added_by_audit": 0,
            })
            saved_data["concepts"].append({
                "concept_id": f"cached-css-part-{number}", "title": title,
                "source_anchor": anchor, "type": "concept", "primary_part_id": part["id"],
                "source_pages": [page_number], "evidence": [{"page": page_number, "excerpt": excerpt}],
            })
        saved = ConceptInventory.model_validate(saved_data)

        padding = {
            "title": "Propriété padding", "source_anchor": "The CSS padding Property",
            "type": "property", "source_pages": [8],
            "evidence": [{"page": 8, "excerpt": "The CSS padding Property"}],
        }
        inline = {
            "title": "Bordure des éléments en ligne", "source_anchor": "Inline element",
            "type": "definition", "source_pages": [8],
            "evidence": [{"page": 8, "excerpt": "Inline element = border closely outlines the element content"}],
        }
        audit_bad = dict(inline, evidence=inline["evidence"][0])
        states = []
        for state in ["link", "visited", "focus", "hover", "active"]:
            page = next(p for p in document["pages"] if p["page"] == 24)
            quote = next(line for line in page["analysis_text"].splitlines() if line.startswith(f"#button a:{state}"))
            states.append({
                "title": f"Pseudo-classe :{state}", "source_anchor": f":{state}",
                "type": "syntax", "source_pages": [24],
                "evidence": [{"page": 24, "excerpt": quote}],
            })
        replies = [
            {"concepts": [padding]}, {"missing_concepts": [audit_bad]},
            {"missing_concepts": [inline]},
            {"concepts": [dict(c, type="pseudo-class") for c in states]},
            {"concepts": states}, {"missing_concepts": []},
        ]

        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            repository = CourseRepository(Path(folder))
            repository.save_inventory(course["course_id"], saved.model_dump(mode="json"))
            stack.enter_context(patch.object(inventory, "load_course", return_value=course))
            stack.enter_context(patch.object(inventory, "load_course_plan", return_value=plan))
            stack.enter_context(patch.object(inventory, "extract_document", return_value=document))
            stack.enter_context(patch.object(inventory, "CourseRepository", return_value=repository))
            call = stack.enter_context(patch.object(client, "chat_text", side_effect=[json.dumps(r) for r in replies]))
            progress = []
            result = inventory.build_inventory(course["course_id"], progress_callback=lambda *args: progress.append(args))

            self.assertEqual(call.call_count, 6)
            self.assertEqual(inventory.inventory_summary(result)["complete_parts"], 8)
            self.assertEqual(inventory.inventory_summary(result)["error_parts"], 0)
            self.assertEqual(sum(item[-1] == "cached" for item in progress), 6)
            by_id = {c.concept_id: c for c in result.concepts}
            for old in saved.concepts:
                self.assertEqual(by_id[old.concept_id], old)
            self.assertEqual(len(result.concepts), len(saved.concepts) + 7)
            self.assertEqual(repository.load_inventory(course["course_id"]), result.model_dump(mode="json"))
            second = inventory.build_inventory(course["course_id"])
            self.assertEqual(call.call_count, 6)
            self.assertEqual(second, result)

    def test_reappearing_concept_adds_relation_without_widening_primary_proof(self):
        old = Concept(
            concept_id="cached-padding", title="Propriété padding", type="property",
            primary_part_id="part-4", source_pages=[10],
            evidence=[{"page": 10, "excerpt": "Configure top, right, bottom, and left padding"}],
        )
        incoming = Concept(
            concept_id="new-padding", title="Propriété padding", type="property",
            source_anchor="The CSS padding Property", primary_part_id="part-3", source_pages=[8],
            evidence=[{"page": 8, "excerpt": "The CSS padding Property"}],
        )
        before = old.model_dump(mode="json")
        result = inventory._merge_many([old], [incoming], "part-3")
        self.assertEqual(len(result), 1)
        merged = result[0]
        self.assertEqual(merged.related_part_ids, ["part-3"])
        self.assertEqual(merged.source_pages, [10])
        self.assertEqual(merged.evidence, old.evidence)
        self.assertEqual(merged.primary_part_id, old.primary_part_id)
        self.assertEqual(merged.concept_id, old.concept_id)
        self.assertEqual(old.model_dump(mode="json"), before)


if __name__ == "__main__":
    unittest.main()
