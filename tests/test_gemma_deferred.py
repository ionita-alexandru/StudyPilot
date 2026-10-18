import unittest
from unittest.mock import patch
from src.ai.client import AITransientError, AIUsageLimitError
from src.courses import learning_material as lm
from test_pedagogy import notion
class DeferredTests(unittest.TestCase):
    def review(self, errors):
        concepts={str(i):notion(str(i)) for i in range(len(errors))}
        points={k:[{'point_id':k,'page':1,'kind':'explanation','quote':'Texte'}] for k in concepts}
        good={'disposition':'developed','excluded_points':{},'point_kinds':{}}
        cache={}; problems=[]; saved=[]
        with patch.object(lm,'assess',side_effect=[e if e else good.copy() for e in errors]):
            result=lm.review_contents(concepts,points,{},cache,problems,model='test',call=None,save=lambda:saved.append(True))
        return result,cache,problems,saved
    def test_isolated_failure_continues(self):
        result,cache,problems,saved=self.review([AITransientError('500'),None])
        self.assertEqual(list(result),['1']);self.assertEqual(problems[0]['status'],'review_pending')
        self.assertNotIn('assessment',cache['content_reviews']['0']);self.assertTrue(saved)
    def test_quota_stops(self):
        with self.assertRaises(AIUsageLimitError):self.review([AIUsageLimitError('429'),None])
    def test_three_failures_stop(self):
        with self.assertRaises(AITransientError):self.review([AITransientError('500') for _ in range(4)])
    def test_success_resets_streak(self):
        result,_,problems,_=self.review([AITransientError('500'),AITransientError('500'),None,AITransientError('500'),None])
        self.assertEqual(len(result),2);self.assertEqual(len(problems),3)
    def test_organization_defers_failed_group_without_publishing_it(self):
        from src.courses import card_groups as cg
        cs={str(i):notion(str(i)) for i in range(3)}
        pts={k:[{'point_id':k,'page':1,'kind':'explanation','quote':'Texte'}] for k in cs}
        assessments={k:{'disposition':'developed','reason':'valide','concept_type':c.type} for k,c in cs.items()}
        cache={'decisions':{}};problems=[]
        with patch.object(cg,'candidate_roots',side_effect=lambda cid,roots,*args:list(roots)),patch.object(cg,'choose_group',side_effect=[AITransientError('500'),{'relation':'independent'}]):
            decisions=cg.organize(cs,pts,assessments,cache,problems,model='test',call=None,save=lambda:None)
        self.assertEqual(set(decisions),{'0','2'})
        self.assertEqual(cache['decisions']['1'],{'pending':True})
        self.assertEqual(problems[0]['status'],'review_pending')
    def test_completed_assessment_is_reused(self):
        cs={'a':notion('a')};pts={'a':[{'point_id':'a','page':1,'kind':'explanation','quote':'Texte'}]};cache={}
        good={'disposition':'developed','excluded_points':{},'point_kinds':{}}
        with patch.object(lm,'assess',return_value=good) as call:
            for _ in range(2):lm.review_contents(cs,pts,{},cache,[],model='test',call=None,save=lambda:None)
        self.assertEqual(call.call_count,1)
