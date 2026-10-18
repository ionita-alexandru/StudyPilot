"""Tests du stockage canonique par cours."""

from pathlib import Path
import tempfile
import unittest

from src.storage.course_repository import CourseRepository
from src.storage.repository import StorageError


class CourseRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = CourseRepository(self.root)
        self.course_id = "analyse-1234567890"

    def tearDown(self):
        self.temp.cleanup()


    def test_invalid_course_id_cannot_escape_storage_root(self):
        for value in ("../cours", "Cours avec espaces", "a/b", "x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.repository.paths(value)

    def test_documents_round_trip_and_listing(self):
        self.repository.save_course(self.course_id, {"schema_version": 1, "title": "Analyse"})
        self.repository.save_plan(self.course_id, {"schema_version": 1, "parts": []})
        self.repository.save_inventory(self.course_id, {"schema_version": 1, "concepts": []})
        self.repository.save_cards(self.course_id, {"schema_version": 1, "cards": []})

        self.assertEqual(self.repository.load_course(self.course_id)["title"], "Analyse")
        self.assertEqual(self.repository.load_plan(self.course_id)["parts"], [])
        self.assertEqual(self.repository.load_inventory(self.course_id)["concepts"], [])
        self.assertEqual(self.repository.load_cards(self.course_id)["cards"], [])
        self.assertEqual(self.repository.list_course_ids(), [self.course_id])

    def test_missing_document_raises_storage_error(self):
        with self.assertRaises(StorageError):
            self.repository.load_course(self.course_id)


if __name__ == "__main__":
    unittest.main()
