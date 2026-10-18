"""Journal de reprise indépendant du décodage de PowerShell et collecte bornée."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import reprendre_cours as runner
from src.storage.course_repository import CourseRepository


class ResumeRunnerTests(unittest.TestCase):
    def test_utf8_child_log_preserves_math_and_nonzero_exit(self):
        with TemporaryDirectory() as folder:
            project=Path(folder);(project/'manage.py').write_text("print('x ∈ ℝ — définition')\nraise SystemExit(2)\n",encoding='utf-8')
            log=io.StringIO()
            with patch('sys.stdout',io.StringIO()):code=runner.run_logged(project,['status'],log)
            self.assertEqual(code,2)
            self.assertIn('x ∈ ℝ — définition',log.getvalue())

    def test_diagnostic_whitelist_preserves_user_files(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);repo=CourseRepository(root/'courses')
            repo.save_course('cours-test',{'title':'Cours générique'})
            path=repo.paths('cours-test').root
            for name in ('plan.json','inventory.json','cards.json','pedagogy.json','secret.env','source.pdf'):
                (path/name).write_text('Données privées préservées ∈',encoding='utf-8')
            before={p.name:p.read_bytes() for p in path.iterdir()}
            log=root/'resultats.txt';log.write_text('État ∈ UTF-8',encoding='utf-8')
            archive=runner.collect_diagnostic(root,repo,log,'fixture')
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()),{'resultats.txt'}|{'courses/cours-test/'+n for n in ('course.json','plan.json','inventory.json','cards.json','pedagogy.json')})
                self.assertIn('∈',z.read('resultats.txt').decode('utf-8'))
            self.assertEqual(before,{p.name:p.read_bytes() for p in path.iterdir()})
            with self.assertRaises(FileExistsError):runner.collect_diagnostic(root,repo,log,'fixture')
