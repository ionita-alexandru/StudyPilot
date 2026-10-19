"""Compléments : rattachement, reprise sans génération répétée et séparation des sources."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from src import course_documents as documents, tutor
from src.courses.study_guide import Draft
from src.storage.course_repository import CourseRepository


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=CourseRepository(self.root/'courses')
        self.course=dict(course_id='course-test',title='Cours test',file_hash='base',source_filename='base.pdf')
        self.plan=dict(parts=[dict(id='p1',number='1',title='Fonctions',page_start=1,page_end=1)])
        self.base=dict(revision='base-v1',entries=[],sources=[],parts=[])
        for target,name,value in [(documents.service,'_repository',self.repo),(documents.service,'load_course',self.course),
                                  (documents.service,'load_course_plan',self.plan),(documents,'load_guide',self.base)]:
            p=patch.object(target,name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch('src.upload_service.UPLOAD_FOLDER',self.root/'pdfs');p.start();self.addCleanup(p.stop)
        p=patch('src.upload_service._EXECUTOR.submit');self.submit=p.start();self.addCleanup(p.stop)
        documents._PENDING.clear();self.addCleanup(documents._PENDING.clear)
        with pymupdf.open() as pdf:
            page=pdf.new_page();page.insert_text((72,72),'Une fonction associe une sortie a une entree.')
            self.pdf=pdf.tobytes()

    def add(self,scope='optional',role='course'):
        return documents.enqueue('course-test',io.BytesIO(self.pdf),'Complement.pdf',role,scope)

    def test_duplicate_is_refused_and_public_metadata_never_exposes_storage_paths(self):
        item=self.add()
        self.assertEqual(item['status'],'queued');self.assertNotIn('filename',item)
        self.assertNotIn('sources',item);self.assertTrue(item['pdf_url'].startswith('/course/course-test/document/'))
        with self.assertRaisesRegex(ValueError,'déjà rattaché'):self.add()
        self.assertEqual(len(list((self.root/'pdfs').glob('*.pdf'))),1)
        with self.assertRaises(ValueError):documents.load('course-test','../escape')

    def test_validated_batches_are_reused_on_resume_and_scope_changes_only_the_programme(self):
        item=self.add();identifier=item['id']
        source=dict(id=identifier+'-p1-0',page=1,text='Une fonction associe une sortie à une entrée.')
        entry=dict(key='function',title='Fonction',role='core',kind='definition',objective='Comprendre une fonction',
                   body='Une fonction associe une sortie à chaque entrée.',source_ids=[source['id']])
        proposal=Draft.model_validate(dict(entries=[entry],coverage=[dict(source_id=source['id'],entry_keys=['function'],reason='Définition utile.')]))
        documents._update('course-test',identifier,sources=[source])
        with patch('src.courses.guide_generation.generate_batch',return_value=(proposal,{})) as generate:
            documents._run('course-test',identifier)
            self.assertEqual(generate.call_count,1)
            documents._update('course-test',identifier,status='interrupted')
            documents._run('course-test',identifier)
            self.assertEqual(generate.call_count,1)
        combined=documents.combined_guide(self.course,self.plan)
        self.assertTrue(combined['entries'][0]['optional'])
        old=combined['revision'];documents.change('course-test',identifier,'course','required')
        combined=documents.combined_guide(self.course,self.plan)
        self.assertFalse(combined['entries'][0]['optional']);self.assertNotEqual(old,combined['revision'])
        self.assertEqual(combined['sources'][0]['document_id'],identifier)
        self.assertEqual(combined['base_revision'],'base-v1')
        import app as webapp
        with patch.object(webapp,'COURSE_PDF_DIR',self.root/'pdfs'):
            client=webapp.app.test_client()
            page=client.get('/course/course-test')
            self.assertEqual(page.status_code,200)
            self.assertIn('Complément à apprendre',page.get_data(as_text=True))
            view=client.get('/course/course-test/discover?card='+combined['entries'][0]['id'])
            self.assertEqual(view.status_code,200)
            self.assertIn(f'/document/{identifier}/pdf',view.get_data(as_text=True))
            pdf=client.get(f'/course/course-test/document/{identifier}/pdf')
            self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF-'))
            pdf.close()

    def test_correction_is_not_retrieved_for_a_normal_attempt(self):
        core=dict(id='f1',title='Fonction',role='core',part_id='p1',body='Définition',source_ids=['s1'])
        guide=dict(entries=[core],sources=[dict(id='s1',page=1,text='fonction sortie'),
                   dict(id='d1',page=2,text='fonction sortie correction',document_id='doc',document_title='Corrigé',document_role='correction',pdf_url='/course/course-test/document/doc/pdf')])
        state=dict(card_id='f1')
        _,_,contexts=tutor.context_for(self.course,self.plan,self.plan['parts'][0],'fonction sortie',state,guide)
        self.assertFalse(any(c.get('document_id') for c in contexts))
        _,_,contexts=tutor.context_for(self.course,self.plan,self.plan['parts'][0],'fonction sortie',state,guide,allow_corrections=True)
        self.assertTrue(any(c.get('document_id') for c in contexts))

    def test_adding_a_document_keeps_the_current_exercise_when_main_course_is_unchanged(self):
        self.repo.paths('course-test').root.mkdir(parents=True)
        guide=dict(self.base)
        with patch.object(tutor,'load_guide',return_value=guide):
            with tutor.conversation(self.course,self.plan) as (state,_):
                identifier=state['id'];state['exercise']={'id':'kept-exercise'}
            guide.update(revision='with-document',base_revision='base-v1')
            with tutor.conversation(self.course,self.plan,identifier) as (state,_):
                self.assertEqual(state['exercise']['id'],'kept-exercise')
                self.assertEqual(state['version'],'with-document')


if __name__=='__main__':unittest.main()
