"""Suite courante par risque ; --full ajoute les régressions historiques et PDF locaux.

Ce lanceur ne déclenche jamais d'appel IA réel. L'évaluation réelle se lance
séparément avec evaluer_import.py et des budgets explicites.
"""
import argparse
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

CORE = {
    'test_learning_tutor', 'test_app_navigation', 'test_card_presentation', 'test_study_guide',
    'test_chat_api', 'test_course_planner',
    'test_course_repository', 'test_course_service', 'test_foundation',
    'test_gemma_provider', 'test_gemma_sdk',
    'test_generation_contracts', 'test_part_study', 'test_pdf_structure',
    'test_presentation_quality', 'test_quota_stop',
    'test_storage_atomic', 'test_upload_service', 'test_course_documents',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Inclure toutes les régressions, y compris les PDF locaux.')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    if args.full:
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    else:
        suite = unittest.defaultTestLoader.loadTestsFromNames(sorted(CORE))
    tick = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, durations=8).run(suite)
    print(f"Profil {'complet' if args.full else 'courant'} : {result.testsRun} tests en {time.monotonic()-tick:.1f} s.")
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
