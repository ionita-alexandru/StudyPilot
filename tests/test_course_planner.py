"""Tests du planner de cours, sans modèle local requis."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf

from src.courses.planner import extract_document, initial_plan, make_preview, propose_ai_titles, generate_overviews, propose_ai_structure


class CoursePlannerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.pdf"

    def tearDown(self):
        self.directory.cleanup()

    def _make_pdf(self, numbered=False):
        doc = pymupdf.open()
        for n in range(1, 9):
            page = doc.new_page()
            if numbered and n in (2, 5):
                page.insert_text((40, 30), f"2.{1 if n == 2 else 2} - Partie de cours", fontsize=19)
            page.insert_text((40, 65), f"Domaine {n}: notion pédagogique et explication substantielle pour des étudiants.", fontsize=12)
            page.insert_text((40, 92), "Méthode avec exemples, définitions, applications et exercices.", fontsize=12)
        doc.save(self.path)
        doc.close()

    def test_preview_retains_pages_and_ids(self):
        self._make_pdf()
        original = self.path.read_bytes()
        preview = make_preview(self.path)
        self.assertEqual(preview["page_count"], 8)
        all_pages = [p for part in preview["parts"] for p in part["source_pages"]]
        self.assertEqual(sorted(all_pages), list(range(1, 9)))
        self.assertEqual(len({x["id"] for x in preview["parts"]}), len(preview["parts"]))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(all(x["overview"]["status"] == "pending" for x in preview["parts"]))

    def test_raw_text_preserved(self):
        self._make_pdf()
        data = extract_document(self.path)
        self.assertIn("Domaine", data["pages"][0]["raw_text"])
        self.assertIn("Domaine", data["pages"][0]["analysis_text"])

    def test_invalid_ai_titles_dont_mutate(self):
        self._make_pdf()
        data = extract_document(self.path)
        preview = initial_plan(data)
        titles = [p["title"] for p in preview["parts"]]
        with patch("src.courses.planner._json_ollama", return_value={"titles": ["Un seul titre"]}):
            with self.assertRaises(ValueError):
                propose_ai_titles(preview, data)
        self.assertEqual([p["title"] for p in preview["parts"]], titles)

    def test_duplicate_numbered_sections_merged_with_stable_ids(self):
        self._make_pdf()
        data = extract_document(self.path)
        fake = [
            {"number": "4.1", "title": "Définition", "page_start": 2,
             "content_pages": [{"page": 2, "text": "Définition complète"}], "content": "Définition complète"},
            {"number": "4.2", "title": "Valeurs propres", "page_start": 4,
             "content_pages": [{"page": 4, "text": "Cours des valeurs propres"}], "content": "Cours des valeurs propres"},
            {"number": "4.2", "title": "Valeurs propres", "page_start": 5,
             "content_pages": [{"page": 5, "text": "Suite des valeurs propres"}], "content": "Suite des valeurs propres"},
        ]
        with patch("src.courses.planner.extract_sections", return_value=fake):
            plan = initial_plan(data)
        self.assertEqual([p["number"] for p in plan["parts"]], ["4.1", "4.2"])
        self.assertEqual(plan["parts"][1]["page_end"], 5)
        self.assertEqual(len({p["id"] for p in plan["parts"]}), 2)

    def test_ai_structure_fails_atomically_on_missing_page(self):
        self._make_pdf()
        data = extract_document(self.path)
        plan = initial_plan(data)
        before = [part["id"] for part in plan["parts"]]
        bad = {"parts": [{"start_page": 1, "end_page": 4, "title": "Introduction"},
                         {"start_page": 6, "end_page": 8, "title": "Applications"}]}
        with patch("src.courses.planner._json_ollama", return_value=bad):
            with self.assertRaises(ValueError):
                propose_ai_structure(plan, data)
        self.assertEqual([part["id"] for part in plan["parts"]], before)

    def test_ai_structure_replaces_provisional_only_when_complete(self):
        self._make_pdf()
        data = extract_document(self.path)
        plan = initial_plan(data)
        proposed = {"parts": [{"start_page": 1, "end_page": 4, "title": "Fondamentaux"},
                              {"start_page": 5, "end_page": 8, "title": "Applications"}]}
        with patch("src.courses.planner._json_ollama", return_value=proposed):
            propose_ai_structure(plan, data)
        self.assertEqual(plan["mode"], "thematic_ai_draft")
        self.assertEqual([p["title"] for p in plan["parts"]], ["Fondamentaux", "Applications"])
        self.assertEqual(len({p["id"] for p in plan["parts"]}), 2)


    def test_scanned_file_rejected(self):
        doc = pymupdf.open()
        doc.new_page()
        doc.save(self.path)
        doc.close()
        with self.assertRaisesRegex(ValueError, "OCR"):
            extract_document(self.path)


if __name__ == "__main__":
    unittest.main()

class PlannerBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "cours.pdf"
        document = pymupdf.open()
        for n in range(1, 9):
            page = document.new_page()
            page.insert_text((40, 65), f"Domaine {n} : présentation du cours et des méthodes de travail.")
            page.insert_text((40, 93), "Exercices et applications nécessaires à la compréhension.")
        document.save(self.path)
        document.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_strict_ai_refuses_invalid_plan_instead_of_saving_fallback(self):
        with patch("src.courses.planner._json_ollama", return_value={"parts": []}):
            with self.assertRaisesRegex(ValueError, "Plan IA indisponible"):
                make_preview(self.path, with_ai_titles=True, strict_ai=True)

    def test_progress_and_snapshot_do_not_remove_sources(self):
        from src.courses.planner import preview_snapshot
        doc = extract_document(self.path)
        plan = initial_plan(doc)
        seen = []
        answer = {
            "summary": "Cette partie expose les notions fondamentales du cours, accompagnées d'exercices et de méthodes pour les appliquer.",
            "learning_objectives": ["Expliquer la notion enseignée."], "key_concepts": ["Notions fondamentales"],
            "prerequisites": [],
            "why_important": "Elle prépare les exercices suivants.",
        }
        def callback(active, part):
            snapshot = preview_snapshot(active)
            self.assertTrue(all("source_slices" not in p for p in snapshot["parts"]))
            self.assertTrue(all("source_slices" in p for p in active["parts"]))
            seen.append(part["id"])
        with patch("src.courses.planner._json_ollama", return_value=answer):
            generate_overviews(plan, doc, progress_callback=callback)
        self.assertEqual(len(seen), len(plan["parts"]))
        self.assertTrue(all(p["overview"]["why_important"] for p in plan["parts"]))

    def test_pdf_name_normalization_handles_hyphens_spaces_and_accents(self):
        from src.courses.plan_manager import normalize_name
        self.assertEqual(normalize_name("Cours-de-CSS"), normalize_name("Cours de CSS"))
        self.assertEqual(normalize_name("Réduction"), normalize_name("reduction"))

class PlannerResumeTests(unittest.TestCase):
    def test_saved_css_plan_resumes_without_rebuilding(self):
        import json
        from src.courses.planner import restore_preview, preview_snapshot
        root = Path(__file__).resolve().parents[1]
        pdf = root / "data" / "pdfs" / "Cours-de-CSS-c41d0f1887.pdf"
        preview_file = root / "data" / "plans" / "Cours-de-CSS-c41d0f1887.json"
        if not (pdf.exists() and preview_file.exists()):
            self.skipTest("Fixtures CSS non disponibles")
        document = extract_document(pdf)
        saved = json.loads(preview_file.read_text(encoding="utf-8"))
        restored = restore_preview(saved, document)
        self.assertEqual(preview_snapshot(restored), saved)
        self.assertEqual(len(restored["parts"]), 8)
        with patch("src.courses.planner._json_ollama", return_value={"summary": "court"}):
            generate_overviews(restored, document, max_parts=1, force_parts={"1"})
        self.assertEqual(restored["parts"][0]["overview"]["status"], "error")
        message = restored["parts"][0]["overview"]["message"]
        self.assertIn("summary invalide", message)
        self.assertIn("key_concepts", message)
        self.assertIn("prerequisites", message)
        self.assertEqual(restored["parts"][1]["overview"], saved["parts"][1]["overview"])
        self.assertEqual([p["title"] for p in restored["parts"]], [p["title"] for p in saved["parts"]])

    def test_resume_refuses_wrong_hash(self):
        from src.courses.planner import restore_preview
        with self.assertRaisesRegex(ValueError, "correspond"):
            restore_preview({"plan_version": 1, "file_hash": "bad"}, {"file_hash": "good", "filename": "x", "page_count": 2})
