"""Contrats limitant les erreurs constatées dans le journal réel du 8 octobre."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from src.courses import pedagogy, card_groups
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, SHA, PLAN, notion, inventory, page, fact


class DecisionProtocolTests(unittest.TestCase):
    def test_schema_excludes_identity_and_exhaustive_selection(self):
        schema=card_groups.group_schema({'t1':'stable-target'})
        properties=schema.model_json_schema()['properties']
        for name in ('concept_id','point_ids','decisions','target_id'):
            self.assertNotIn(name,properties)
        base=dict(relation='duplicate',target_ref='t1',reason='Même notion.')
        self.assertEqual(schema.model_validate(base).target_ref,'t1')
        for target in ('c1','stable-target','t2',None):
            with self.subTest(target=target),self.assertRaises(ValidationError):
                schema.model_validate({**base,'target_ref':target})
        with self.assertRaises(ValidationError):
            schema.model_validate({**base,'concept_id':'wrong'})
        self.assertIsNone(schema.model_validate({**base,'relation':'independent'}).target_ref)

    def test_no_available_target_can_be_invented(self):
        schema=card_groups.group_schema({})
        base=dict(relation='independent',reason='Définition suffisante.')
        self.assertIsNone(schema.model_validate(base).target_ref)
        self.assertIsNone(schema.model_validate({**base,'target_ref':'t1'}).target_ref)
        with self.assertRaises(ValidationError):schema.model_validate({**base,'relation':'supplement'})

    def test_self_not_offered_and_long_point_ids_not_sent(self):
        a=notion('a');b=notion('b','Membrane',text='La membrane délimite la cellule.')
        fake=FakeModel({1:[fact(a.evidence[0].excerpt),fact(b.evidence[0].excerpt,ids=['c2'],title=b.title)]})
        with TemporaryDirectory() as root,patch.object(pedagogy,'chat_json',side_effect=fake):
            result=pedagogy.prepare_material(inventory(a,b),dict(file_hash=SHA,pages=[page(1,a.evidence[0].excerpt+'\n'+b.evidence[0].excerpt)]),PLAN,CourseRepository(Path(root)),model=MODEL)
        self.assertFalse(result.issues)
        contents=[p for name,p in fake.calls if name=='ContentAssessment']
        self.assertEqual(len(contents),2)
        self.assertTrue(all('possible_targets' not in p for p in contents))
        self.assertTrue(all(p['points'][0]['point_id']=='p1' for p in contents))
        groups=[p for name,p in fake.calls if name=='GroupProposal']
        self.assertEqual(len(groups),1)
        payload=groups[0]
        self.assertEqual(len(payload['possible_targets']),1)
        self.assertNotEqual(payload['possible_targets'][0]['title'],payload['concept']['title'])
        self.assertEqual(payload['possible_targets'][0]['id'],'t1')

    def test_folio_page_never_sent_to_model_but_note_is_saved(self):
        fake=FakeModel({2:[]})
        with TemporaryDirectory() as root,patch.object(pedagogy,'chat_json',side_effect=fake):
            repo=CourseRepository(Path(root))
            result=pedagogy.prepare_material(inventory(),dict(file_hash=SHA,pages=[page(2,'2\n')]),PLAN,repo,model=MODEL)
            saved=json.loads((repo.paths('cours-test').root/'pedagogy.json').read_text())
        self.assertFalse(result.issues);self.assertFalse(fake.calls)
        self.assertEqual(saved['chunks']['p2-s0-0'],[])
        self.assertIn('p2-s0-0',saved['coverage_notes'])

    def test_numeric_content_or_visual_page_is_not_treated_as_blank(self):
        for item in [page(2,'42'),page(2,'2\n3'),{**page(2,'2'),'has_visual_content':True},
                     {**page(2,'2'),'image_regions':[[0,0,100,100]]},{**page(2,'2'),'ocr_used':True}]:
            with self.subTest(item=item):self.assertFalse(pedagogy.folio_only(item))

    def test_continuation_context_is_not_selectable_evidence(self):
        c=notion(text='Une phrase débute ici.')
        fake=FakeModel({1:[fact(c.evidence[0].excerpt)]})
        document=dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt),page(2,'Elle continue ailleurs.')])
        chunks=pedagogy.source_chunks(document)
        context=pedagogy.continuation_context(chunks[0],chunks,document)
        self.assertEqual(context['following_text'],'Elle continue ailleurs.')
        lines=pedagogy.numbered_lines(chunks[0]['text'])
        with self.assertRaises(ValueError):
            pedagogy.selected_quote(pedagogy.Fact(title='Cellule',kind='explanation',start_line=1,end_line=2),lines)

    def test_protocol_migration_keeps_coverage_and_backs_up_decisions(self):
        c=notion();inv=inventory(c);doc=dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt)])
        fake=FakeModel({1:[fact(c.evidence[0].excerpt)]})
        with TemporaryDirectory() as root,patch.object(pedagogy,'chat_json',side_effect=fake):
            repo=CourseRepository(Path(root))
            with patch.object(pedagogy,'DECISION_PROTOCOL',2):
                pedagogy.prepare_material(inv,doc,PLAN,repo,model=MODEL)
            path=repo.paths('cours-test').root/'pedagogy.json';before=path.read_bytes();fake.calls.clear()
            result=pedagogy.prepare_material(inv,doc,PLAN,repo,model=MODEL)
            self.assertFalse(result.issues)
            self.assertFalse(any(name=='CoverageResponse' for name,_ in fake.calls))
            self.assertTrue(any(name=='ContentAssessment' for name,_ in fake.calls))
            self.assertTrue(any(p.read_bytes()==before for p in path.parent.glob('_backups/pedagogy.before_decision_protocol*')))
            fake.calls.clear();pedagogy.prepare_material(inv,doc,PLAN,repo,model=MODEL)
            self.assertFalse(fake.calls)

    def test_unknown_exclusion_cannot_silently_remove_information(self):
        c=notion();fake=FakeModel({1:[fact(c.evidence[0].excerpt)]})
        def invalid(**kw):
            reply=fake(**kw)
            if kw['response_model'].__name__=='ContentAssessment':reply['excluded_points']={'p99':'Autre notion.'}
            return reply
        with TemporaryDirectory() as root,patch.object(pedagogy,'chat_json',side_effect=invalid):
            result=pedagogy.prepare_material(inventory(c),dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt)]),PLAN,CourseRepository(Path(root)),model=MODEL)
        self.assertFalse(result.inventory.concepts)
        self.assertTrue(result.issues)
