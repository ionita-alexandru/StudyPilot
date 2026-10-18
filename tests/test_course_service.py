"""Tests du service canonique des cours."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.courses import plan_manager, service
from src.storage.repository import read_json, write_json_atomic


class CourseServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf_dir = self.root / "cours"
        self.plan_dir = self.root / "plans"
        self.course_data_dir = self.root / "courses"
        for folder in (self.pdf_dir, self.plan_dir, self.course_data_dir):
            folder.mkdir()

        self.patches = [
            patch.object(service, "COURSE_PDF_DIR", self.pdf_dir),
            patch.object(service, "COURSE_DATA_DIR", self.course_data_dir),
            patch.object(plan_manager, "PLAN_DIR", self.plan_dir),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _save_canonical_course(self, *, title="Cours", hash_value="a" * 64, pages=8):
        course_id = service.make_course_id(title, hash_value)
        pdf = self.pdf_dir / "cours.pdf"
        pdf.write_bytes(b"%PDF-placeholder")
        write_json_atomic(
            self.course_data_dir / course_id / "course.json",
            {
                "schema_version": 1,
                "course_id": course_id,
                "title": title,
                "source_filename": pdf.name,
                "file_hash": hash_value,
                "page_count": pages,
                "original_filename": "Cours.pdf",
                "uploaded_at": None,
            },
        )
        return course_id, pdf

    def test_catalog_reads_canonical_storage_and_modern_plan_count(self):
        course_id, pdf = self._save_canonical_course()
        write_json_atomic(
            self.course_data_dir / course_id / "plan.json",
            {
                "schema_version": 1,
                "course_id": course_id,
                "plan_version": 1,
                "filename": pdf.name,
                "file_hash": "a" * 64,
                "page_count": 8,
                "parts": [
                    {"id": "p1", "number": "1", "title": "A", "page_start": 1, "page_end": 2, "source_pages": [1, 2]},
                    {"id": "p2", "number": "2", "title": "B", "page_start": 3, "page_end": 4, "source_pages": [3, 4]},
                    {"id": "p3", "number": "3", "title": "C", "page_start": 5, "page_end": 6, "source_pages": [5, 6]},
                    {"id": "p4", "number": "4", "title": "D", "page_start": 7, "page_end": 8, "source_pages": [7, 8]},
                ],
            },
        )

        courses = service.list_courses()

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_id"], course_id)
        self.assertEqual(courses[0]["part_count"], 4)
        self.assertTrue(courses[0]["plan_available"])

    def test_invalid_canonical_plan_is_not_silently_used(self):
        course_id, pdf = self._save_canonical_course()
        write_json_atomic(
            self.course_data_dir / course_id / "plan.json",
            {
                "schema_version": 1,
                "course_id": course_id,
                "plan_version": 1,
                "filename": pdf.name,
                "file_hash": "a" * 64,
                "page_count": 8,
                "parts": [
                    {"id": "p1", "number": "1", "title": "Trou", "page_start": 2, "page_end": 8, "source_pages": list(range(2, 9))},
                ],
            },
        )
        course = service.load_course(course_id)
        self.assertIsNone(service.load_course_plan(course))

    def test_generation_contracts_upgrade_updates_matching_plans_and_preserves_generated_material(self):
        from src.courses.planner import _id
        from src.courses.overview import is_current
        from test_generation_contracts import ANSWER
        course_id, pdf = self._save_canonical_course(pages=1)
        document = dict(filename=pdf.name, file_hash='a'*64, page_count=1,
                        pages=[dict(page=1, raw_text='Source', analysis_text='Source')])
        plan = dict(plan_version=1, filename=pdf.name, file_hash='a'*64, page_count=1,
            mode='thematic_ai_draft', parts=[dict(id=_id('a'*64, 'pages:1:1'), number='1',
                title='Archives', page_start=1, page_end=1, source_pages=[1],
                overview=dict(status='draft', summary='Ancien résumé'))])
        repo = service._repository()
        repo.save_plan(course_id, service._canonical_plan(plan, course_id))
        for path in plan_manager.plan_paths(pdf):
            write_json_atomic(path, plan)
        paths = [repo.paths(course_id).root / name for name in ('inventory.json', 'cards.json', 'pedagogy.json')]
        for path in paths:
            path.write_bytes(b'{"unchanged":true}')
        with patch.object(service, 'extract_document', return_value=document), patch('src.courses.planner._json_ollama', return_value=ANSWER) as model:
            self.assertEqual(service.refresh_overviews(course_id), dict(status='ready', updated=1))
            self.assertEqual(service.refresh_overviews(course_id), dict(status='ready', updated=0))
        model.assert_called_once()
        for path in [repo.paths(course_id).plan, *plan_manager.plan_paths(pdf)]:
            self.assertTrue(is_current(read_json(path)['parts'][0]['overview']))
        self.assertTrue(all(path.read_bytes() == b'{"unchanged":true}' for path in paths))

    def test_create_course_saves_record_candidate_and_active_plan(self):
        pdf = self.pdf_dir / "nouveau.pdf"
        pdf.write_bytes(b"%PDF-placeholder")
        document = {
            "filename": pdf.name,
            "file_hash": "b" * 64,
            "page_count": 4,
            "pages": [
                {"page": page, "raw_text": f"page {page}", "analysis_text": f"page {page}",
                 "headings": [], "warnings": []}
                for page in range(1, 5)
            ],
        }
        candidate = {
            "plan_version": 1,
            "filename": pdf.name,
            "file_hash": "b" * 64,
            "page_count": 4,
            "mode": "thematic_ai_draft",
            "status": "draft",
            "model": "qwen2.5:3b",
            "parts": [
                {"id": "p1", "number": "1", "title": "Première partie",
                 "page_start": 1, "page_end": 2, "title_origin": "pdf_proposal",
                 "title_status": "draft", "overview": {"status": "pending"},
                 "source_pages": [1, 2]},
                {"id": "p2", "number": "2", "title": "Deuxième partie",
                 "page_start": 3, "page_end": 4, "title_origin": "pdf_proposal",
                 "title_status": "draft", "overview": {"status": "pending"},
                 "source_pages": [3, 4]},
            ],
            "warnings": [],
            "page_diagnostics": [],
            "consolidation": {"version": 1, "origin": "new_pdf_proposal", "review_required": True},
        }
        restored = {
            **candidate,
            "parts": [
                {**candidate["parts"][0], "source_slices": [
                    {"page": 1, "text": "page 1"}, {"page": 2, "text": "page 2"}
                ]},
                {**candidate["parts"][1], "source_slices": [
                    {"page": 3, "text": "page 3"}, {"page": 4, "text": "page 4"}
                ]},
            ],
        }

        def fake_generate(plan, _document, model, progress_callback):
            for part in plan["parts"]:
                part["overview"] = {
                    "status": "draft",
                    "summary": "Résumé suffisamment long pour le test de service StudyPilot.",
                    "key_concepts": [part["title"]],
                    "prerequisites": [],
                    "why_important": "",
                    "source_pages": part["source_pages"],
                    "model": model,
                }
                progress_callback(plan, part)

        with (
            patch.object(service, "extract_document", return_value=document),
            patch.object(service, "build_candidate", return_value=candidate),
            patch.object(service, "validate_candidate", return_value=restored),
            patch.object(service, "generate_overviews", side_effect=fake_generate),
            patch("src.courses.pipeline.process_course", return_value={"status": "ready", "incomplete": 0}) as process,
        ):
            result = service.create_course(
                pdf,
                title="Nouveau cours",
                original_filename="Cours original.pdf",
            )

        self.assertEqual(result["status"], "ready")
        process.assert_called_once()
        self.assertEqual(process.call_args.args[0], result["course_id"])
        course_id = result["course_id"]
        canonical_course = read_json(self.course_data_dir / course_id / "course.json")
        canonical_plan = read_json(self.course_data_dir / course_id / "plan.json")
        self.assertEqual(canonical_course["course_id"], course_id)
        self.assertEqual(canonical_plan["course_id"], course_id)
        self.assertEqual(len(canonical_plan["parts"]), 2)



if __name__ == "__main__":
    unittest.main()
