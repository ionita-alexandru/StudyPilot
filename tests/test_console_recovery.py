"""Reproduction des arrêts Windows, sans appel Ollama réel."""
import io, json, os, subprocess, sys, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from src.console import configure_console
from src.courses import pedagogy
from src.storage.course_repository import CourseRepository
from src.storage.repository import write_json_atomic
from src.models.card import CardCollection
from test_pedagogy import MODEL, SHA, PLAN, FakeModel, fact, inventory, notion, page

class ConsoleRecoveryTests(unittest.TestCase):
    def test_cp1252_failure_then_unicode_on_both_streams(self):
        sample = 'Théorème : x ∈ E ; ω ; non‑nul\n'
        with self.assertRaises(UnicodeEncodeError): sample.encode('cp1252')
        # newline=None suit la plateforme : CRLF sous Windows, LF sous Linux.
        # Tester aussi chaque convention explicitement sur les deux plateformes.
        for newline in (None, '\n', '\r\n'):
            with self.subTest(newline=newline):
                buffers = [io.BytesIO(), io.BytesIO()]
                out, err = [io.TextIOWrapper(b, encoding='cp1252', newline=newline) for b in buffers]
                try:
                    with patch.object(sys,'stdout',out), patch.object(sys,'stderr',err):
                        configure_console()
                        print(sample,end=''); print(sample,end='',file=sys.stderr)
                        expected = sample.replace('\n', os.linesep if newline is None else newline)
                        for buffer in buffers:
                            self.assertEqual(buffer.getvalue().decode('utf-8'), expected)
                finally:
                    out.detach(); err.detach()

    def test_captured_stream_is_not_replaced(self):
        stream=io.StringIO()
        with patch.object(sys,'stdout',stream),patch.object(sys,'stderr',stream):
            configure_console();self.assertIs(sys.stdout,stream);print('ω ∈ E')
        self.assertEqual(stream.getvalue(),'ω ∈ E\n')

    def test_cli_process_survives_redirected_cp1252_progress_and_json(self):
        code='''
from unittest.mock import patch
import manage
from src.courses import pipeline, service
text='Non‑nul : ω ∈ E'
def process(course_id, **kw):
    kw['progress_callback'](1,1,'—',text)
    return {'status':'ready','detail':text}
with patch.object(service,'list_courses',return_value=[{'course_id':'regression','title':text}]),patch.object(pipeline,'process_course',side_effect=process):
    raise SystemExit(manage.main(['process','--all']))
'''
        env={**os.environ,'PYTHONUTF8':'0','PYTHONIOENCODING':'cp1252:strict'}
        result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.decode('utf-8').count('Non‑nul : ω ∈ E'),3)

    def test_failed_review_is_saved_before_interrupted_progress(self):
        first=notion('first','Commande','lire(fichier)',kind='command')
        second=notion('second','Cellule','La cellule est une unité.',page=2)
        fake=FakeModel({1:[fact('lire(fichier)','example')],2:[fact(second.evidence[0].excerpt,ids=['c2'])]})
        def interrupt(done,total,part,state):
            if state.startswith('contenu'): raise KeyboardInterrupt()
        with TemporaryDirectory() as folder,patch.object(pedagogy,'chat_json',side_effect=fake):
            repo=CourseRepository(Path(folder))
            with self.assertRaises(KeyboardInterrupt):
                pedagogy.prepare_material(inventory(first,second),{'file_hash':SHA,'pages':[page(1,first.evidence[0].excerpt),page(2,second.evidence[0].excerpt)]},PLAN,repo,model=MODEL,progress_callback=interrupt)
            saved=json.loads((repo.paths('cours-test').root/'pedagogy.json').read_text())
            self.assertEqual(saved['stage'],'content')
            self.assertEqual(saved['review_progress'],{'checked':1,'total':2,'validated':1})
            self.assertEqual(saved['content_reviews']['first']['assessment']['disposition'],'supporting')
            self.assertIn('recovery',saved['content_reviews']['first'])
            self.assertEqual(len(saved['chunks']),2)

    def test_status_separates_old_snapshot_and_current_preparation(self):
        import manage
        with TemporaryDirectory() as folder:
            repo=CourseRepository(Path(folder))
            saved=CardCollection(course_id='cours-test',file_hash=SHA,inventory_hash=SHA,model=MODEL,quality_version=14,quality_hash='old',cards=[])
            repo.save_cards('cours-test',saved.model_dump(mode='json'))
            write_json_atomic(repo.paths('cours-test').root/'pedagogy.json',{'fingerprint':'new','stage':'relevance','chunks':{'one':[]},'decisions':{},'issues':[{'page':4,'reason':'Association à vérifier'}]})
            original=repo.paths('cours-test').cards.read_bytes(); output=io.StringIO()
            with patch('src.storage.course_repository.CourseRepository',return_value=repo),patch.object(manage,'find_course',return_value={'course_id':'cours-test','title':'Cours'}),patch.object(sys,'stdout',output):
                result=manage.main(['cards','status','--course','Cours'])
            self.assertEqual(result,2)
            self.assertIn('PRÉPARATION NON PUBLIÉE',output.getvalue())
            self.assertIn('Association à vérifier',output.getvalue())
            self.assertIn('diagnostics suivants peuvent être anciens',output.getvalue())
            self.assertEqual(repo.paths('cours-test').cards.read_bytes(),original)
