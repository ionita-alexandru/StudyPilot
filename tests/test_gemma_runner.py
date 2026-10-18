from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import reprendre_cours as runner
from src import config

class RunnerTests(unittest.TestCase):
    def execute(self,arguments,codes=None):
        with TemporaryDirectory() as folder:
            project=Path(folder);(project/'manage.py').write_text('')
            course=project/'data'/'courses'/'cours-a';course.mkdir(parents=True)
            original=b'{"previous":"preserved"}'
            for name in ('inventory.json','cards.json'): (course/name).write_bytes(original)
            other=course.parent/'cours-b';other.mkdir()
            for name in ('inventory.json','cards.json'): (other/name).write_bytes(original)
            repository=SimpleNamespace(list_course_ids=lambda:['cours-a','cours-b'],paths=lambda cid:SimpleNamespace(root=course.parent/cid))
            with patch.object(runner,'__file__',str(project/'reprendre_cours.py')),patch.object(runner,'CourseRepository',return_value=repository),patch.object(config,'AI_PROVIDER','gemma'),patch.object(runner,'run_logged',side_effect=codes or (lambda *a:0)) as run,patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='préflight simulé\n')) as preflight:
                code=runner.main(arguments)
            commands=[c.args[1] for c in run.call_args_list]
            backups=list(course.parent.glob('*/_backups/before_gemma_*'))
            for backup in backups:
                self.assertEqual((backup/'inventory.json').read_bytes(),original)
                self.assertEqual((backup/'cards.json').read_bytes(),original)
            self.assertEqual((course/'cards.json').read_bytes(),original)
            return code,commands,len(backups),preflight.call_count

    def test_default_only_checks_api_and_collects_diagnostic(self):
        code,commands,backups,preflight=self.execute([])
        self.assertEqual(code,0);self.assertEqual(backups,0);self.assertEqual(preflight,1)
        self.assertFalse(any(c[:2]==['cards','build'] for c in commands))

    def test_course_backs_up_without_inventory_rebuild(self):
        code,commands,backups,_=self.execute(['--course','cours-a'])
        self.assertEqual(code,0);self.assertEqual(backups,1)
        self.assertIn(['cards','build','--course','cours-a'],commands)
        self.assertFalse(any(c[0] in ('inventory','process') for c in commands))

    def test_quota_stops_before_second_course(self):
        code,commands,backups,_=self.execute(['--all'],[0,3,0,0])
        self.assertEqual(code,3);self.assertEqual(backups,1)
        self.assertEqual(sum(c[:2]==['cards','build'] for c in commands),1)

    def test_temporary_failure_continues_and_remains_visible_in_exit_code(self):
        code,commands,backups,_=self.execute(['--all'],[0,4,0,0,0])
        self.assertEqual(code,4);self.assertEqual(backups,2)
        self.assertEqual(sum(c[:2]==['cards','build'] for c in commands),2)

    def test_diagnostic_only_never_calls_ai(self):
        code,commands,backups,preflight=self.execute(['--diagnostic-only'])
        self.assertEqual(code,0);self.assertEqual(backups,0);self.assertEqual(preflight,0)
        self.assertTrue(all(c[:2]==['cards','status'] for c in commands))

    def test_unknown_course_stops_before_ai_or_backup(self):
        code,commands,backups,preflight=self.execute(['--course','absent'])
        self.assertEqual(code,1);self.assertEqual(backups,0);self.assertEqual(preflight,0)

if __name__=='__main__':unittest.main()
