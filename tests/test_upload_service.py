"""Tests rapides de l'import sans démarrer Flask ni appeler Ollama."""

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import pymupdf
from src import upload_service as service


def sample_pdf(text="Voici un cours de programmation sur les fonctions.") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    result = document.tobytes()
    document.close()
    return result


class UploadServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.original_folder = service.UPLOAD_FOLDER
        service.UPLOAD_FOLDER = Path(self.folder.name)
        self.jobs_patch = patch.object(service, 'JOB_DIR', Path(self.folder.name) / 'imports')
        self.jobs_patch.start()
        self.jobs_before = dict(service._JOBS)
        service._JOBS.clear()

    def tearDown(self):
        service.UPLOAD_FOLDER = self.original_folder
        service._JOBS.clear()
        service._JOBS.update(self.jobs_before)
        self.jobs_patch.stop()
        self.folder.cleanup()

    def test_real_pdf_accepted_and_name_is_safe(self):
        path, title, count = service.save_validated_pdf(
            BytesIO(sample_pdf()), "../Cours Python épreuve.pdf"
        )
        self.assertEqual(count, 1)
        self.assertEqual(title, "Cours Python épreuve")
        self.assertEqual(path.parent, Path(self.folder.name))
        self.assertTrue(path.name.startswith("Cours-Python-epreuve-"))
        self.assertTrue(path.is_file())

    def test_misnamed_file_rejected_and_temp_cleaned(self):
        with self.assertRaises(service.UploadError):
            service.save_validated_pdf(BytesIO(b"not a real PDF"), "cours.pdf")
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])

    def test_scanned_pdf_rejected_without_ocr(self):
        document = pymupdf.open()
        document.new_page()
        data = document.tobytes()
        document.close()
        with self.assertRaisesRegex(service.UploadError, "OCR"):
            service.save_validated_pdf(BytesIO(data), "scan.pdf")

    def test_size_limit(self):
        with patch.object(service, "MAX_PDF_BYTES", 10):
            with self.assertRaisesRegex(service.UploadError, "20 Mo"):
                service.save_validated_pdf(BytesIO(sample_pdf()), "long.pdf")

    def test_job_processes_pdf_and_reports_course_id(self):
        fake_service = types.ModuleType("src.courses.service")
        calls = []

        def create_course(path, **kwargs):
            calls.append((Path(path), kwargs))
            progress = kwargs["progress_callback"]
            progress(1, 2, "1", "overview")
            progress(2, 2, "2", "overview")
            return {
                "status": "ready",
                "course_id": "cours-informatique-1234567890",
                "done": 2,
                "total": 2,
                "incomplete": 0,
            }

        fake_service.create_course = create_course
        fake_service.make_course_id = lambda title, digest: 'cours-informatique-1234567890'
        with patch.dict(sys.modules, {"src.courses.service": fake_service}):
            job_id = service.enqueue_pdf(BytesIO(sample_pdf()), "Cours informatique.pdf")
            status = None
            for _ in range(200):
                status = service.job_status(job_id)
                if status["status"] in ("ready", "error"):
                    break
                time.sleep(0.01)

        self.assertEqual(status["status"], "ready", status)
        self.assertEqual(status["title"], "Cours informatique")
        self.assertEqual(status["course_id"], "cours-informatique-1234567890")
        self.assertEqual(status["done"], 2)
        self.assertEqual(status["total"], 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["title"], "Cours informatique")
        self.assertEqual(calls[0][1]["original_filename"], "Cours informatique.pdf")
        self.assertTrue(callable(calls[0][1]["progress_callback"]))
        self.assertNotIn("pdf_path", status)

    def test_restart_and_resume_keep_job_id_and_reject_duplicate_submission(self):
        path, _, _ = service.save_validated_pdf(BytesIO(sample_pdf()), 'Cours.pdf')
        job_id = 'a' * 32
        service._JOBS[job_id] = dict(status='processing', pdf_path=str(path), title='Cours', pages=1, done=1, total=2)
        service._persist(job_id)
        service._JOBS.clear()
        service.restore_jobs()
        self.assertEqual(service.job_status(job_id)['status'], 'interrupted')
        self.assertEqual(service.job_status(job_id)['done'], 1)
        self.assertNotIn('pdf_path', service.job_status(job_id))
        with patch.object(service._EXECUTOR, 'submit') as submit:
            service.resume_job(job_id)
            with self.assertRaises(service.UploadError):
                service.resume_job(job_id)
        submit.assert_called_once_with(service._run_job, job_id)
        self.assertEqual(service.read_json(service.JOB_DIR / (job_id+'.json'))['status'], 'queued')

    def test_quota_and_foreign_path_cannot_become_ready_or_resume(self):
        from src.ai.client import AIUsageLimitError
        job_id = 'b' * 32
        service._JOBS[job_id] = dict(status='queued', pdf_path=str(Path(self.folder.name)/'cours.pdf'))
        with patch.object(service, '_run_import', side_effect=AIUsageLimitError('Quota atteint')):
            service._run_job(job_id)
        self.assertEqual(service.job_status(job_id)['status'], 'interrupted')
        service._JOBS[job_id]['pdf_path'] = str(Path(self.folder.name).parent / 'outside.pdf')
        with patch.object(service._EXECUTOR, 'submit') as submit, self.assertRaises(service.UploadError):
            service.resume_job(job_id)
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
