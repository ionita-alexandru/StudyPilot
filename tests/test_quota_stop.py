"""Régression HTTP 429 du diagnostic réel v15.2 ; aucun appel réseau."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import json
from src.ai import client
from src.courses import pedagogy, cards, learning_material, card_groups, pipeline, service
from src.storage.course_repository import CourseRepository
from test_pedagogy import MODEL, notion, page
import manage

class QuotaStopTests(unittest.TestCase):
    def test_provider_429_is_typed_and_not_retried(self):
        class RateError(Exception):status_code=429
        with patch.object(client,'_ollama_chat',return_value=lambda **kw: (_ for _ in ()).throw(RateError('monthly usage limit'))), self.assertRaises(client.AIUsageLimitError):client.chat(messages=[])

    def test_ordinary_failure_is_not_treated_as_quota(self):
        with patch.object(client,'_ollama_chat',return_value=lambda **kw: (_ for _ in ()).throw(ConnectionError('network'))), self.assertRaises(ConnectionError):client.chat(messages=[])

    def test_checked_audit_stops_after_one_attempt(self):
        with patch.object(pedagogy,'chat_json',side_effect=client.AIUsageLimitError('429')) as call, self.assertRaises(client.AIUsageLimitError):
            pedagogy.call_checked(learning_material.ContentAssessment,'prompt',{},MODEL,lambda x:x)
        self.assertEqual(call.call_count,1)

    def test_review_does_not_record_quota_as_bad_source_or_continue(self):
        cache={};problems=[];c=notion();p=dict(point_id='p',page=1,kind='explanation',quote=c.evidence[0].excerpt)
        with patch.object(learning_material,'assess',side_effect=client.AIUsageLimitError('429')) as call,self.assertRaises(client.AIUsageLimitError):
            learning_material.review_contents({'a':c,'b':c},{'a':[p],'b':[p]}, {'pages':[page(1,p['quote'])]},cache,problems,model=MODEL,call=None,save=lambda:None)
        self.assertEqual(call.call_count,1);self.assertFalse(problems)
        self.assertNotIn('last_error',cache['content_reviews']['a'])

    def test_all_courses_stops_before_next_course(self):
        with patch.object(service,'list_courses',return_value=[dict(course_id='a',title='A'),dict(course_id='b',title='B')]),patch.object(pipeline,'process_course',side_effect=client.AIUsageLimitError('429')) as call:
            self.assertEqual(manage.main(['process','--all']),3)
        self.assertEqual(call.call_count,1)

    def test_previous_cards_restored_and_interrupted_checkpoint_preserved(self):
        with TemporaryDirectory() as d:
            repo=CourseRepository(Path(d));path=repo.paths('quota-test').cards;path.parent.mkdir(parents=True);original=b'{"previous":"valid snapshot"}';path.write_bytes(original)
            def fail(*args,**kwargs):path.write_bytes(b'{"checkpoint":"partial"}');raise client.AIUsageLimitError('429')
            with patch.object(cards,'CourseRepository',return_value=repo),patch.object(cards,'_build_cards',side_effect=fail),self.assertRaises(client.AIUsageLimitError):cards.build_cards('quota-test',force=True)
            self.assertEqual(path.read_bytes(),original)
            backups=list((path.parent/'_backups').glob('cards.interrupted_quota.*.json'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),b'{"checkpoint":"partial"}')

    def test_before_write_quota_keeps_cards_exactly(self):
        with TemporaryDirectory() as d:
            repo=CourseRepository(Path(d));path=repo.paths('quota-test').cards;path.parent.mkdir(parents=True);path.write_bytes(b'{"previous":true}')
            with patch.object(cards,'CourseRepository',return_value=repo),patch.object(cards,'_build_cards',side_effect=client.AIUsageLimitError('429')),self.assertRaises(client.AIUsageLimitError):cards.build_cards('quota-test')
            self.assertEqual(path.read_bytes(),b'{"previous":true}');self.assertFalse((path.parent/'_backups').exists())
