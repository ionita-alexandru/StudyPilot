
"""Tests de gestion des candidats de plan, sans appel réel à Ollama."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from src.courses import plan_manager
from src.courses.planner import _id, extract_document


class PlanManagementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.plans = self.root / 'data' / 'plans'
        self.plans.mkdir(parents=True)
        self.pdf = self.root / 'data' / 'pdfs' / 'cours.pdf'
        self.pdf.parent.mkdir(parents=True)

        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text(
                (50, 70),
                f'Chapitre de test {i+1} et definition complete du sujet.',
                fontsize=12
            )
        doc.save(self.pdf)
        doc.close()

        source = extract_document(self.pdf)

        self.candidate = {
            'plan_version': 1,
            'filename': self.pdf.name,
            'file_hash': source['file_hash'],
            'page_count': 3,
            'mode': 'thematic_ai_draft',
            'status': 'draft',
            'model': 'qwen2.5:3b',
            'warnings': [],
            'page_diagnostics': [],
            'parts': [
                {
                    'id': _id(source['file_hash'], f'pages:{i}:{i}'),
                    'number': str(i),
                    'title': f'Notion pédagogique {i}',
                    'page_start': i,
                    'page_end': i,
                    'source_pages': [i],
                    'title_status': 'draft',
                    'overview': {'status': 'pending'}
                }
                for i in range(1, 4)
            ],
            'consolidation': {
                'version': 1,
                'origin': 'test'
            },
        }

        self.old = self.plans / 'cours.json'
        self.ready = self.plans / 'cours.candidate.json'

        self.ready.write_text(
            json.dumps(self.candidate, ensure_ascii=False),
            encoding='utf-8'
        )

        self.patches = [
            patch.object(plan_manager, 'PLAN_DIR', self.plans),
            patch.object(plan_manager, 'COURSE_PDF_DIR', self.pdf.parent)
        ]

        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_status_is_read_only(self):
        original = self.ready.read_bytes()

        plan_manager.show_plan_status(
            self.pdf,
            self.old,
            self.ready,
            self.candidate
        )

        self.assertEqual(original, self.ready.read_bytes())
        self.assertFalse(self.old.exists())

    def test_pending_blocks_publication(self):
        with self.assertRaisesRegex(ValueError, 'pending/error'):
            plan_manager.publish_candidate(
                self.pdf,
                self.old,
                self.ready,
                self.candidate
            )

        self.assertFalse(self.old.exists())

    def test_overviews_checkpoint_and_resume(self):
        answer = {
            'summary': (
                'Cette partie expose une notion pédagogique '
                'avec son explication, ses méthodes et ses applications.'
            ),
            'learning_objectives': ['Expliquer la notion enseignée.'], 'key_concepts': ['Notion de test'],
            'prerequisites': [],
            'why_important': ''
        }

        with patch(
            'src.courses.planner._json_ollama',
            return_value=answer
        ) as call:
            plan_manager.generate_candidate_overviews(
                self.pdf,
                self.ready,
                self.candidate,
                'qwen2.5:3b',
                1
            )

            self.assertEqual(call.call_count, 1)

            snapshot = plan_manager.load_plan_file(self.ready)
            self.assertEqual(
                plan_manager.overview_summary(snapshot)['pending'],
                2
            )

            plan_manager.generate_candidate_overviews(
                self.pdf,
                self.ready,
                snapshot,
                'qwen2.5:3b',
                None
            )

            # La première partie n'est pas régénérée.
            self.assertEqual(call.call_count, 3)

        self.assertEqual(
            plan_manager.overview_summary(plan_manager.load_plan_file(self.ready))['draft'],
            3
        )

    def test_publish_backs_up_old_plan_and_is_idempotent(self):
        old_plan = dict(self.candidate, status='old')

        self.old.write_text(
            json.dumps(old_plan, ensure_ascii=False),
            encoding='utf-8'
        )

        for part in self.candidate['parts']:
            part['overview'] = {
                'status': 'draft',
                'summary': 'Test'
            }

        previous = self.old.read_bytes()

        plan_manager.publish_candidate(
            self.pdf,
            self.old,
            self.ready,
            self.candidate
        )

        backups = list(
            (self.plans / '_backups').glob(
                'cours.before_plan_publish.*.json'
            )
        )

        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), previous)
        self.assertEqual(plan_manager.load_plan_file(self.old), self.candidate)

        plan_manager.publish_candidate(
            self.pdf,
            self.old,
            self.ready,
            self.candidate
        )

        self.assertEqual(
            len(list((self.plans / '_backups').glob('*.json'))),
            1
        )

    def test_mismatched_hash_and_page_gap_refused(self):
        bad = dict(self.candidate, file_hash='incorrect')

        with self.assertRaises(ValueError):
            plan_manager.validate_candidate(bad, self.pdf)

        bad = json.loads(json.dumps(self.candidate))
        bad['parts'][1]['page_start'] = 3

        with self.assertRaises(ValueError):
            plan_manager.validate_candidate(bad, self.pdf)


    def test_prepare_candidate_has_no_arbitrary_seven_page_limit(self):
        long_pdf = self.pdf.parent / "long-course.pdf"
        document = pymupdf.open()
        for index in range(10):
            page = document.new_page()
            page.insert_text(
                (50, 70),
                f"Même thème continu, explication pédagogique page {index + 1} sans nouvelle section.",
                fontsize=12,
            )
        document.save(long_pdf)
        document.close()

        candidate_path = self.plans / "long-course.candidate.json"
        plan_manager.prepare_candidate(long_pdf, candidate_path)
        candidate = plan_manager.load_plan_file(candidate_path)

        self.assertEqual(
            [page for part in candidate["parts"] for page in part["source_pages"]],
            list(range(1, 11)),
        )
        self.assertTrue(any(part["page_end"] - part["page_start"] + 1 > 7
                            for part in candidate["parts"]))

    def test_three_real_candidates_are_structurally_valid(self):
        root = Path(__file__).resolve().parents[1]
        folder = root / 'data' / 'pdfs'

        for name in [
            'Cours-de-CSS-c41d0f1887',
            'Séries de Fourier ING2 2024-2025',
            'Chapitre 4 Réduction endomorphismes ING2 2024-2025'
        ]:
            pdf = folder / f'{name}.pdf'
            candidate = (
                root / 'data' / 'plans'
                / f'{name}.candidate.json'
            )

            if not pdf.is_file() or not candidate.is_file():
                self.skipTest(
                    'PDF et plans réels non fournis dans la suite locale'
                )

            value = json.loads(
                candidate.read_text(encoding='utf-8')
            )

            plan_manager.validate_candidate(value, pdf)

            self.assertEqual(
                [
                    page
                    for part in value['parts']
                    for page in part['source_pages']
                ],
                list(range(1, value['page_count'] + 1))
            )


if __name__ == '__main__':
    unittest.main()
