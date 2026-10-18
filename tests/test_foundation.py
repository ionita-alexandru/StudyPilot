"""Tests du socle technique commun de StudyPilot."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.models import CoursePart
from src.storage.repository import StorageError, read_json


class FoundationTests(unittest.TestCase):

    def test_invalid_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertRaises(StorageError):
                read_json(path)

    def test_plan_part_rejects_inverted_pages(self):
        with self.assertRaises(ValidationError):
            CoursePart(id="part-1", number="1", title="Test", page_start=4, page_end=2, source_pages=[4])



if __name__ == "__main__":
    unittest.main()
