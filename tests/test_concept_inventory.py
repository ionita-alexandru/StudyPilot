import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import STUDY_MODEL
from src.courses import inventory as inventory_module
from src.models.concept import ConceptInventory
from src.storage.course_repository import CourseRepository


class ConceptInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.pdf_dir = root / "pdfs"
        self.data_dir = root / "courses"
        self.pdf_dir.mkdir()
        self.data_dir.mkdir()
        self.pdf = self.pdf_dir / "cours.pdf"
        self.pdf.write_bytes(b"%PDF-placeholder")
        self.course = {
            "course_id": "cours-1234567890",
            "title": "Cours",
            "source_filename": "cours.pdf",
            "file_hash": "a" * 64,
            "page_count": 2,
        }
        self.plan = {
            "parts": [
                {
                    "id": "part-1",
                    "number": "1",
                    "title": "Introduction",
                    "page_start": 1,
                    "page_end": 2,
                    "overview": {
                        "status": "draft",
                        "key_concepts": ["Notion A"],
                    },
                }
            ]
        }
        self.document = {
            "file_hash": "a" * 64,
            "pages": [
                {
                    "page": 1,
                    "raw_text": "Notion A est une définition importante.",
                    "analysis_text": "Notion A est une définition importante.",
                    "headings": ["Notion A"],
                },
                {
                    "page": 2,
                    "raw_text": "Méthode B : appliquer les étapes dans l'ordre.",
                    "analysis_text": "Méthode B : appliquer les étapes dans l'ordre.",
                    "headings": ["Méthode B"],
                },
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_unverifiable_concept_is_rejected(self):
        raw = [
            {
                "title": "Notion totalement absente",
                "type": "definition",
                "source_pages": [1],
                "evidence": [
                    {
                        "page": 1,
                        "excerpt": "texte inventé absent du PDF",
                    }
                ],
            }
        ]

        with self.assertRaises(ValueError):
            inventory_module._validate_ai_concepts(
                raw,
                file_hash=self.course["file_hash"],
                part=self.plan["parts"][0],
                pages=self.document["pages"],
            )

    def test_bad_ai_quote_is_recovered_from_pdf(self):
        raw = [
            {
                "title": "Notion A",
                "type": "definition",
                "source_pages": [1],
                "evidence": [
                    {
                        "page": 1,
                        "excerpt": "citation paraphrasée qui n'existe pas",
                    }
                ],
            }
        ]

        result = inventory_module._validate_ai_concepts(
            raw,
            file_hash=self.course["file_hash"],
            part=self.plan["parts"][0],
            pages=self.document["pages"],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Notion A")
        self.assertEqual(result[0].source_pages, [1])
        self.assertIn("Notion A", result[0].evidence[0].excerpt)

    def test_grounded_but_irrelevant_evidence_is_rejected(self):
        pages = [
            {
                "page": 1,
                "raw_text": "Polynôme trigonométrique\nn = -∞",
                "analysis_text": "Polynôme trigonométrique\nn = -∞",
                "headings": [],
            }
        ]

        self.assertFalse(
            inventory_module._evidence_supports_title(
                "Polynôme trigonométrique",
                "n = -∞",
            )
        )
        self.assertNotEqual(
            inventory_module._source_evidence_for_title(
                "Polynôme trigonométrique",
                pages[0],
            ),
            "n = -∞",
        )


    def test_formula_evidence_requires_its_notation(self):
        self.assertFalse(
            inventory_module._evidence_supports_title(
                "Formule des coefficients de Fourier a0",
                "Forme complexe d’une série de Fourier.",
            )
        )
        self.assertTrue(
            inventory_module._evidence_supports_title(
                "Formule des coefficients de Fourier a0",
                "a0 = 1/T ∫ f(x) dx",
            )
        )

    def test_specific_concept_needs_all_short_distinctive_anchors(self):
        self.assertFalse(
            inventory_module._evidence_supports_title(
                "Convergence normale d’une série de Fourier",
                "Définition. Etude de la convergence. Série de Fourier.",
            )
        )
        self.assertTrue(
            inventory_module._evidence_supports_title(
                "Convergence normale d’une série de Fourier",
                "la série de Fourier est normalement convergente sur R",
            )
        )

    def test_gamma_convolution_title_needs_both_semantic_anchor_and_notation(self):
        self.assertFalse(
            inventory_module._evidence_supports_title(
                "Coefficient de convolution γ_n",
                "Produit. Convolution.",
            )
        )
        self.assertFalse(
            inventory_module._evidence_supports_title(
                "Coefficient de convolution γ_n",
                "γ_n = somme des coefficients du produit",
            )
        )

    def test_build_inventory_runs_extraction_then_coverage_audit(self):
        replies = [
            {
                "concepts": [
                    {
                        "title": "Notion A",
                        "type": "definition",
                        "source_pages": [1],
                        "evidence": [
                            {
                                "page": 1,
                                "excerpt": "Notion A est une définition importante.",
                            }
                        ],
                    }
                ]
            },
            {
                "missing_concepts": [
                    {
                        "title": "Méthode B",
                        "type": "method",
                        "source_pages": [2],
                        "evidence": [
                            {
                                "page": 2,
                                "excerpt": "Méthode B : appliquer les étapes dans l'ordre.",
                            }
                        ],
                    }
                ]
            },
        ]
        repository = CourseRepository(self.data_dir)

        with (
            patch.object(inventory_module, "COURSE_PDF_DIR", self.pdf_dir),
            patch.object(inventory_module, "load_course", return_value=self.course),
            patch.object(inventory_module, "load_course_plan", return_value=self.plan),
            patch.object(inventory_module, "extract_document", return_value=self.document),
            patch.object(inventory_module, "CourseRepository", return_value=repository),
            patch.object(inventory_module, "chat_json", side_effect=replies) as mocked_chat,
        ):
            result = inventory_module.build_inventory(self.course["course_id"])

        self.assertEqual(mocked_chat.call_count, 2)
        self.assertEqual(
            {item.title for item in result.concepts},
            {"Notion A", "Méthode B"},
        )
        self.assertEqual(result.parts[0].status, "complete")
        self.assertEqual(result.parts[0].concepts_added_by_audit, 1)
        self.assertEqual(result.schema_version, 3)

        saved = ConceptInventory.model_validate(
            repository.load_inventory(self.course["course_id"])
        )
        self.assertEqual(len(saved.concepts), 2)

    def test_failed_audit_does_not_leak_partial_concepts(self):
        repository = CourseRepository(self.data_dir)
        replies = [
            {
                "concepts": [
                    {
                        "title": "Notion A",
                        "type": "definition",
                        "source_pages": [1],
                        "evidence": [
                            {
                                "page": 1,
                                "excerpt": "Notion A est une définition importante.",
                            }
                        ],
                    }
                ]
            },
            RuntimeError("audit cassé"),
            RuntimeError("audit cassé"),
        ]

        with (
            patch.object(inventory_module, "COURSE_PDF_DIR", self.pdf_dir),
            patch.object(inventory_module, "load_course", return_value=self.course),
            patch.object(inventory_module, "load_course_plan", return_value=self.plan),
            patch.object(inventory_module, "extract_document", return_value=self.document),
            patch.object(inventory_module, "CourseRepository", return_value=repository),
            patch.object(inventory_module, "chat_json", side_effect=replies),
        ):
            result = inventory_module.build_inventory(self.course["course_id"])

        self.assertEqual(result.parts[0].status, "error")
        self.assertEqual(result.concepts, [])

    def test_resume_skips_complete_part(self):
        repository = CourseRepository(self.data_dir)
        existing = ConceptInventory(
            schema_version=3,
            course_id=self.course["course_id"],
            file_hash=self.course["file_hash"],
            model=STUDY_MODEL,
            parts=[
                {
                    "part_id": "part-1",
                    "part_number": "1",
                    "status": "complete",
                    "concepts_found": 1,
                    "concepts_added_by_audit": 0,
                    "audit_passes": 1,
                }
            ],
            concepts=[
                {
                    "concept_id": "concept-a",
                    "title": "Notion A",
                    "type": "definition",
                    "primary_part_id": "part-1",
                    "source_pages": [1],
                    "evidence": [
                        {
                            "page": 1,
                            "excerpt": "Notion A est une définition importante.",
                        }
                    ],
                }
            ],
        )
        repository.save_inventory(
            self.course["course_id"],
            existing.model_dump(mode="json"),
        )

        with (
            patch.object(inventory_module, "COURSE_PDF_DIR", self.pdf_dir),
            patch.object(inventory_module, "load_course", return_value=self.course),
            patch.object(inventory_module, "load_course_plan", return_value=self.plan),
            patch.object(inventory_module, "extract_document", return_value=self.document),
            patch.object(inventory_module, "CourseRepository", return_value=repository),
            patch.object(inventory_module, "chat_json") as mocked_chat,
        ):
            result = inventory_module.build_inventory(self.course["course_id"])

        mocked_chat.assert_not_called()
        self.assertEqual(len(result.concepts), 1)


if __name__ == "__main__":
    unittest.main()

def test_composite_concept_can_use_multiple_evidence_fragments(self):
    pages = [
        {
            "page": 1,
            "raw_text": (
                "Calcul des coefficients de Fourier.\n"
                "Proposition 2.2.1\n"
                "a0 = formule\n"
                "an = formule\n"
                "bn = formule"
            ),
            "analysis_text": (
                "Calcul des coefficients de Fourier.\n"
                "Proposition 2.2.1\n"
                "a0 = formule\n"
                "an = formule\n"
                "bn = formule"
            ),
            "headings": [
                "Calcul des coefficients de Fourier",
                "Proposition 2.2.1",
            ],
        }
    ]

    raw = [
        {
            "title": (
                "Calcul des coefficients de Fourier "
                "a0, an et bn (Proposition 2.2.1)"
            ),
            "type": "theorem",
            "source_pages": [1],
            "evidence": [
                {
                    "page": 1,
                    "excerpt": "Calcul des coefficients de Fourier.",
                },
                {
                    "page": 1,
                    "excerpt": "Proposition 2.2.1",
                },
                {
                    "page": 1,
                    "excerpt": "a0 = formule",
                },
                {
                    "page": 1,
                    "excerpt": "an = formule",
                },
                {
                    "page": 1,
                    "excerpt": "bn = formule",
                },
            ],
        }
    ]

    result = inventory_module._validate_ai_concepts(
        raw,
        file_hash=self.course["file_hash"],
        part=self.plan["parts"][0],
        pages=pages,
    )

    self.assertEqual(len(result), 1)
    self.assertEqual(len(result[0].evidence), 5)
