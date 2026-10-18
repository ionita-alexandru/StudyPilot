import unittest

from src.courses import inventory as inventory_module


class InventoryLanguageTests(unittest.TestCase):
    def setUp(self):
        self.file_hash = "a" * 64
        self.part = {
            "id": "part-css",
            "number": "1",
            "title": "CSS",
            "page_start": 1,
            "page_end": 1,
        }
        self.pages = [
            {
                "page": 1,
                "raw_text": (
                    "CSS Syntax\n"
                    "Three ways to implement CSS\n"
                    "Inline Styles\n"
                    "Uses the HTML style attribute"
                ),
                "analysis_text": (
                    "CSS Syntax\n"
                    "Three ways to implement CSS\n"
                    "Inline Styles\n"
                    "Uses the HTML style attribute"
                ),
                "headings": [
                    "CSS Syntax",
                    "Inline Styles",
                ],
            }
        ]

    def test_obvious_english_display_title_is_detected(self):
        self.assertTrue(
            inventory_module._title_looks_mostly_english(
                "CSS Syntax"
            )
        )
        self.assertFalse(
            inventory_module._title_looks_mostly_english(
                "Syntaxe CSS"
            )
        )
        self.assertFalse(
            inventory_module._title_looks_mostly_english(
                "font-size"
            )
        )

    def test_french_title_can_be_grounded_by_english_source_anchor(self):
        raw = [
            {
                "title": "Syntaxe CSS",
                "source_anchor": "CSS Syntax",
                "type": "syntax",
                "source_pages": [1],
                "evidence": [
                    {
                        "page": 1,
                        "excerpt": "citation volontairement invalide",
                    }
                ],
            }
        ]

        result = inventory_module._validate_ai_concepts(
            raw,
            file_hash=self.file_hash,
            part=self.part,
            pages=self.pages,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Syntaxe CSS")
        self.assertEqual(result[0].source_pages, [1])
        self.assertIn(
            "CSS Syntax",
            result[0].evidence[0].excerpt,
        )

    def test_source_anchor_makes_id_independent_from_french_wording(self):
        first = inventory_module._concept_id(
            self.file_hash,
            "Syntaxe CSS",
            source_anchor="CSS Syntax",
            concept_type="syntax",
            part_id="part-css",
        )
        second = inventory_module._concept_id(
            self.file_hash,
            "Syntaxe de CSS",
            source_anchor="CSS Syntax",
            concept_type="syntax",
            part_id="part-css",
        )

        self.assertEqual(first, second)

    def test_english_display_title_is_rejected_at_validation(self):
        raw = [
            {
                "title": "CSS Syntax",
                "source_anchor": "CSS Syntax",
                "type": "syntax",
                "source_pages": [1],
                "evidence": [
                    {
                        "page": 1,
                        "excerpt": "CSS Syntax",
                    }
                ],
            }
        ]

        with self.assertRaisesRegex(
            ValueError,
            "titre pédagogique",
        ):
            inventory_module._validate_ai_concepts(
                raw,
                file_hash=self.file_hash,
                part=self.part,
                pages=self.pages,
            )


if __name__ == "__main__":
    unittest.main()
