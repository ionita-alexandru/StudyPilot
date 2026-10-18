import unittest

from src.courses import cards as cards_module
from src.models.concept import Concept


class CardTests(unittest.TestCase):
    def setUp(self):
        self.concept = Concept(
            concept_id="concept-test",
            title="Notion test",
            type="definition",
            primary_part_id="part-1",
            source_pages=[1],
            evidence=[
                {
                    "page": 1,
                    "excerpt": "Notion test : définition exacte.",
                }
            ],
        )
        self.pages = [
            {
                "page": 1,
                "raw_text": "Notion test : définition exacte.",
                "analysis_text": "Notion test : définition exacte.",
            }
        ]


    def test_validate_cards_inherits_sources_from_concept(self):
        raw = [
            {
                "concept_id": self.concept.concept_id,
                "sections": [
                    {
                        "title": "Définition",
                        "content": "Notion test : définition exacte.",
                    }
                ],
            }
        ]

        result = cards_module._validate_cards(
            raw,
            [self.concept],
            self.pages,
        )

        card = result[self.concept.concept_id]
        self.assertEqual(card.source_pages, [1])
        self.assertEqual(card.sections[0].key, "definition")

    def test_validate_cards_reports_missing_concept_id(self):
        diagnostics = {}

        result = cards_module._validate_cards(
            [],
            [self.concept],
            self.pages,
            diagnostics,
        )

        self.assertEqual(result, {})
        self.assertIn(
            "CONCEPT_ID absent de la réponse IA",
            diagnostics[self.concept.concept_id],
        )

    def test_preview_rejects_invalid_index_before_ai_call(self):
        with self.assertRaisesRegex(ValueError, "--index"):
            cards_module.preview_card("cours-test", 0)


if __name__ == "__main__":
    unittest.main()
