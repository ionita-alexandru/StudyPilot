"""Tests de la recherche et du chat au niveau d'une partie."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from src.part_study import answer_part_question, retrieve_pdf_contexts, select_part


class PartStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "cours.pdf"
        document = pymupdf.open()
        for text in (
            "Intro CSS, propriétés color.",
            "Les sélecteurs HTML.",
            "Utiliser un lien index.html dans le document.",
            "La propriété z-index fixe l'ordre de superposition CSS.",
        ):
            page = document.new_page()
            page.insert_text((40, 50), text, fontsize=12)
        document.save(self.pdf)
        document.close()
        self.plan = {
            "parts": [
                {"number": "1", "title": "Introduction", "page_start": 1, "page_end": 2},
                {"number": "2", "title": "Positionnement", "page_start": 3, "page_end": 4},
            ]
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_select_part(self):
        self.assertEqual(select_part(self.plan, "2")["page_start"], 3)
        self.assertIsNone(select_part(self.plan, "9"))

    def test_chat_retrieves_outside_active_part_and_preserves_physical_page(self):
        contexts = retrieve_pdf_contexts(
            self.pdf, self.plan["parts"][0], "C'est quoi z-index ?", "Cours"
        )
        self.assertEqual([context["page"] for context in contexts], [4])
        self.assertIn("z-index", contexts[0]["content"])
        self.assertEqual(contexts[0]["section_number"], "page physique 4")

    def test_off_topic_does_not_force_source(self):
        contexts = retrieve_pdf_contexts(
            self.pdf, self.plan["parts"][0], "capitale du Japon ?", "Cours"
        )
        self.assertEqual(contexts, [])

    def test_knowledge_fallback_does_not_fabricate_pdf_source(self):
        class Message:
            content = "Complément StudyPilot : réponse."

        class Response:
            message = Message()

        with patch("src.part_study.chat", return_value=Response()) as fake_chat:
            answer = answer_part_question("C'est quoi Flexbox ?", [], "qwen2.5:3b")
        self.assertEqual(answer, "Complément StudyPilot : réponse.")
        self.assertIn("Aucun extrait", fake_chat.call_args.kwargs["messages"][1]["content"])

    def test_bilingual_expansion_when_no_literal_match(self):
        document = pymupdf.open()
        for text in (
            "Introduction to CSS.",
            "The border property sets the line around an element.",
            "Other content.",
            "Some additional content.",
        ):
            page = document.new_page()
            page.insert_text((40, 50), text, fontsize=12)
        document.save(self.pdf)
        document.close()
        contexts = retrieve_pdf_contexts(
            self.pdf,
            self.plan["parts"][0],
            "Explique la bordure",
            "Cours",
            expand_terms=lambda _question: ["border", "bordure"],
        )
        self.assertEqual(contexts[0]["page"], 2)
        self.assertIn("border", contexts[0]["content"])

    def test_retrieval_is_read_only(self):
        before = self.pdf.read_bytes()
        retrieve_pdf_contexts(self.pdf, self.plan["parts"][0], "z-index", "Cours")
        self.assertEqual(before, self.pdf.read_bytes())


if __name__ == "__main__":
    unittest.main()
