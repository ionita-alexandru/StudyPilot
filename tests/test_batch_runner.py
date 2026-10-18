import unittest,tempfile,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import terminer_cours as full

class FullRunnerTests(unittest.TestCase):
 def exercise(self,scenario):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folders={cid:root/cid for cid in ['a','b']}
   for f in folders.values():f.mkdir()
   repo=SimpleNamespace(list_course_ids=lambda:['a','b'],paths=lambda cid:SimpleNamespace(root=folders[cid]))
   counts={'a':0,'b':0};calls=[]
   def state(repo,cid):
    done=(counts[cid]>=2 if cid=='a' else counts[cid]>=1) if scenario in ('progress','timeslice','transient') else False
    return {'course_id':cid,'complete':done,'cards':counts[cid]},str(counts[cid])
   def run(command,*args):
    calls.append(command)
    if command[0]=='verifier_gemma.py':return 0
    cid=command[-1]
    if scenario=='quota':return 3
    if scenario in ('progress','timeslice','transient'):
     counts[cid]+=1
     if scenario=='timeslice' and cid=='a' and counts[cid]==1:raise TimeoutError('Créneau atteint')
     if scenario=='transient' and cid=='a' and counts[cid]==1:return 4
     return 2 if cid=='a' and counts[cid]==1 else 0
    return 2
   with patch.dict(full.main.__globals__,{'__file__':str(root/'runner.py'),'CourseRepository':lambda:repo,'state':state,'run':run,'collect_diagnostic':lambda *a:root/'diagnostic.zip'}),patch.dict(os.environ,{'GEMINI_API_KEY':'dummy'}),patch('builtins.print'),patch('src.config.AI_PROVIDER','gemma'):
    code=full.main([])
   return code,[x[-1] for x in calls if x[0]=='manage.py']
 def test_partial_course_does_not_block_other_courses_and_resume_is_targeted(self):
  code,calls=self.exercise('progress');self.assertEqual(code,0);self.assertEqual(calls,['a','b','a'])
 def test_fatal_quota_stops_before_next_course(self):
  code,calls=self.exercise('quota');self.assertEqual(code,3);self.assertEqual(calls,['a'])
 def test_transient_failure_continues_next_course_then_resumes(self):
  code,calls=self.exercise('transient');self.assertEqual(code,0);self.assertEqual(calls,['a','b','a'])
 def test_course_time_limit_continues_next_course_then_resumes_checkpoints(self):
  code,calls=self.exercise('timeslice');self.assertEqual(code,0);self.assertEqual(calls,['a','b','a'])
 def test_two_stagnant_passes_stop(self):
  code,calls=self.exercise('stagnant');self.assertEqual(code,2);self.assertEqual(calls,['a','b','a','b'])
