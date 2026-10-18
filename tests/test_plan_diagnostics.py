"""Plan diagnostics : ne pas perdre une proposition imparfaite, ne jamais l'accepter."""
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf
from src.courses.planner import _id, extract_document
from src.courses.plan_review import create_candidate, validate_proposals
from src.config import STUDY_MODEL


class PlanDiagnosticsTests(unittest.TestCase):
    def test_repeated_title_kept_for_diagnosis_but_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "test.pdf"
            with pymupdf.open() as document:
                for i in range(1, 5):
                    page = document.new_page()
                    page.insert_text((50, 70), f"Contenu de la page {i} exemple détaillé")
                document.save(pdf)
            doc = extract_document(pdf)
            h = doc["file_hash"]
            saved = {"plan_version": 1, "filename": pdf.name, "file_hash": h,
                     "page_count": 4, "mode": "thematic_ai_draft", "status": "draft",
                     "warnings": [], "page_diagnostics": [], "model": STUDY_MODEL,
                     "parts": [{"id": _id(h, "pages:1:4"), "number": "1", "title": "Cours",
                                "page_start": 1, "page_end": 4, "title_origin": "ai_proposal",
                                "overview": {"status": "pending"}, "source_pages": [1, 2, 3, 4]}]}
            index = {"index_version": 1, "file_hash": h, "filename": pdf.name,
                     "page_count": 4, "model": STUDY_MODEL,
                     "pages": [{"page": i, "topics": ["concept"]} for i in range(1, 5)]}
            cache = root / "test.themes.json"
            cache.write_text(json.dumps(index), encoding="utf-8")
            reply = {"parts": [
                {"start_page": 1, "end_page": 1, "title": "CSS Styling et couleurs"},
                {"start_page": 2, "end_page": 2, "title": "CSS Styling et sélecteurs"},
                {"start_page": 3, "end_page": 4, "title": "CSS Styling et affichage"}]}
            calls = []
            def fake(prompt, model):
                calls.append(prompt)
                return reply
            candidate = create_candidate(saved, doc, ai_call=fake, index_cache=cache)
            self.assertEqual(len(calls), 1)  # index réutilisé
            self.assertEqual(len(candidate["parts"]), 3)
            self.assertIn("css styling", candidate["review"]["title_warnings"][0])
            raw = root / "test.proposal_raw.json"
            self.assertTrue(raw.is_file())
            self.assertEqual(json.loads(raw.read_text(encoding="utf-8"))["response"], reply)
            with self.assertRaisesRegex(ValueError, "Titres génériques"):
                validate_proposals(candidate["parts"], doc)
            self.assertEqual(saved["parts"][0]["overview"]["status"], "pending")

    def test_raw_reply_saved_when_structure_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "test.pdf"
            with pymupdf.open() as document:
                document.new_page().insert_text((50, 70), "Ondes électromagnétiques et propagation : présentation détaillée des phénomènes")
                document.save(pdf)
            doc = extract_document(pdf)
            h = doc["file_hash"]
            saved = {"plan_version": 1, "filename": pdf.name, "file_hash": h,
                     "page_count": 1, "mode": "thematic_ai_draft", "status": "draft",
                     "warnings": [], "page_diagnostics": [], "model": STUDY_MODEL,
                     "parts": [{"id": _id(h, "pages:1:1"), "number": "1", "title": "Ondes",
                                "page_start": 1, "page_end": 1, "title_origin": "ai_proposal",
                                "overview": {"status": "pending"}, "source_pages": [1]}]}
            index = {"index_version": 1, "file_hash": h, "filename": pdf.name,
                     "page_count": 1, "model": STUDY_MODEL,
                     "pages": [{"page": 1, "topics": ["ondes"]}]}
            cache = root / "test.themes.json"
            cache.write_text(json.dumps(index), encoding="utf-8")
            reply = {"parts": [{"start_page": 2, "end_page": 2, "title": "Erreur"}]}
            with self.assertRaisesRegex(ValueError, "pages"):
                create_candidate(saved, doc, ai_call=lambda prompt, model: reply, index_cache=cache)
            self.assertEqual(json.loads((root / "test.proposal_raw.json").read_text(encoding="utf-8"))["response"], reply)


if __name__ == "__main__":
    unittest.main()
