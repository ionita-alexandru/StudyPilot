"""Reproductions des causes observées dans le diagnostic du 8 octobre.

Citations issues des données réelles CSS/Fourier/algèbre. Ollama est simulé.
Les tests de PDF existants vérifient séparément extraction et régions originales.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from src.courses import pedagogy
from src.courses.inventory import concept_evidence_issue
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, SHA, PLAN, notion, inventory, page, fact


class DiagnosticReplayTests(unittest.TestCase):
    def prepare(self, text, reply, root, c=None):
        c = c or notion(text=text)
        return pedagogy.prepare_material(inventory(c), dict(file_hash=SHA, pages=[page(1, text)]),
            PLAN, CourseRepository(Path(root)), model=MODEL)

    def test_real_short_explanations_are_not_labels_because_they_are_anchors(self):
        for title, text in [('Propriété font-size', 'font-size = configures the size of the text'),
                            ('content', 'content = text & web page elements in the container')]:
            with self.subTest(title=title):
                c = notion(title=title, text=text).model_copy(update={'source_anchor': text})
                self.assertIsNone(concept_evidence_issue(c, [page(1, text)]))
        for label in ['font-size', 'Navigation', 'Simple titre']:
            c = notion(title=label, text=label)
            self.assertIn('preuves limitées', concept_evidence_issue(c, [page(1, label)]))
        c = notion(title='Exemple', text='Texte réellement absent du PDF.')
        self.assertIn('absente', concept_evidence_issue(c, [page(1, 'Autre texte')]))

    def test_real_math_mislabeled_as_explanations_needs_original_pdf(self):
        samples = [
            'Le réel ∥f∥2 mesure le carré de la valeur eﬃcace de f sur l’intervalle [0, T].',
            '1. cn = (an −ibn)\n2\net c−n = (an + ibn)\n2\ndonc |c−n| = |cn|',
            'c0 = det(A) et cn−1 = tr(A) =\nn\nX\ni=1\naii avec tr(A) appelée trace de A.',
            'Ce polynôme s’écrit P(X) = C Πp\ni=1(X −αi)mi avec αi ∈K et C ∈K.',
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(pedagogy.visual_needed(dict(quote=text, kind='explanation', ambiguous=False)))
                fake = FakeModel({1:[fact(text)]})
                with TemporaryDirectory() as root, patch.object(pedagogy, 'chat_json', side_effect=fake):
                    result = self.prepare(text, fake, root)
                    self.assertFalse(result.issues)
                    self.assertTrue(result.inventory.concepts[0].illustrations)
                    self.assertEqual(result.inventory.concepts[0].evidence[0].excerpt, text)
        for text in ['font-size = configures the size of the text', 'body { color: blue; }', 'La cellule est une unité du vivant.']:
            self.assertFalse(pedagogy.visual_needed(dict(quote=text, kind='explanation')))

    def test_omitted_identifier_and_selection_preserve_every_point(self):
        text = 'La cellule est une unité du vivant.\nUne cellule musculaire se contracte.'
        fake = FakeModel({1:[fact(text.splitlines()[0]), fact(text.splitlines()[1], 'example')]})
        def respond(**kw):
            raw = fake(**kw)
            if kw['response_model'].__name__ == 'ContentAssessment':
                self.assertNotIn('point_ids', raw)
                self.assertNotIn('concept_id', raw)
            return raw
        with TemporaryDirectory() as root, patch.object(pedagogy, 'chat_json', side_effect=respond):
            result = self.prepare(text, respond, root)
            self.assertFalse(result.issues)
            self.assertEqual(len(result.inventory.concepts[0].learning_points), 2)
            self.assertTrue(all(p.point_id not in {'p1', 'p2'} for p in result.inventory.concepts[0].learning_points))

    def test_explicit_incomplete_selection_remains_rejected(self):
        text = 'La cellule est une unité du vivant.'; fake = FakeModel({1:[fact(text)]})
        def respond(**kw):
            raw = fake(**kw)
            if kw['response_model'].__name__ == 'ContentAssessment':
                raw['point_ids'] = []
            return raw
        with TemporaryDirectory() as root, patch.object(pedagogy, 'chat_json', side_effect=respond):
            result = self.prepare(text, respond, root)
            self.assertFalse(result.inventory.concepts)
            self.assertIn('point_ids', result.issues[0]['reason'])

    def test_wrongly_assigned_example_requires_independent_exclusion_audit(self):
        text = 'La cellule est une unité du vivant.\nUn triangle possède trois côtés.'
        fake = FakeModel({1:[fact(text.splitlines()[0]), fact(text.splitlines()[1], 'example')]})
        def respond(**kw):
            if kw['response_model'] is pedagogy.SourceJudgment:
                payload = json.loads(kw['messages'][-1]['content'])
                self.assertEqual(payload['title'], 'Cellule')
                return dict(supported=True, reason='La phrase décrit un triangle, pas une cellule.')
            raw = fake(**kw)
            if kw['response_model'].__name__ == 'ContentAssessment':
                raw['excluded_points']={'p2':'Autre notion.'}
            return raw
        with TemporaryDirectory() as root, patch.object(pedagogy, 'chat_json', side_effect=respond):
            result=self.prepare(text,respond,root)
            self.assertFalse(result.issues)
            self.assertEqual(len(result.inventory.concepts[0].learning_points),1)
            cache=json.loads((CourseRepository(Path(root)).paths('cours-test').root/'pedagogy.json').read_text())
            self.assertTrue(cache['decisions']['cellule']['decision']['exclusion_checks'])

    def test_code_mislabeled_explanation_is_not_automatically_autonomous(self):
        text='color: red;'; fake=FakeModel({1:[fact(text)]})
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=fake):
            result=self.prepare(text,fake,root)
            self.assertFalse(result.inventory.concepts)
            self.assertEqual(result.issues[0]['status'],'card_incomplete')

    def test_developed_example_can_be_autonomous_after_review(self):
        text='Pour x = 2, on calcule x + 1 = 3. Le résultat est donc 3.'
        fake=FakeModel({1:[fact(text,'example')]})
        def respond(**kw):
            if kw['response_model'] is pedagogy.SourceJudgment:
                return dict(supported=True,reason='Calcul expliqué avec donnée et résultat dans la source.')
            return fake(**kw)
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=respond):
            result=self.prepare(text,respond,root)
            self.assertFalse(result.issues)
            self.assertEqual(len(result.inventory.concepts),1)

    def test_real_behavior_mislabeled_mention_is_not_silently_discarded(self):
        text='Browsers automatically add a border to image links.'
        fake=FakeModel({1:[fact(text,'mention')]},{'cellule':('mention',None)})
        def respond(**kw):
            if kw['response_model'] is pedagogy.SourceJudgment:
                return dict(supported=False,reason='La source explique un comportement, pas seulement un nom.')
            return fake(**kw)
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=respond):
            result=self.prepare(text,respond,root)
            self.assertFalse(result.issues)
            self.assertEqual(result.inventory.concepts[0].relevance,'active')
            self.assertIn('automatically',result.inventory.concepts[0].evidence[0].excerpt)

    def test_migration_reuses_exact_coverage_but_rechecks_decisions(self):
        text='La cellule est une unité du vivant.'; c=notion(text=text)
        fake=FakeModel({1:[fact(text)]})
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=fake):
            with patch.object(pedagogy,'QUALITY_VERSION',14):
                self.prepare(text,fake,root,c)
            path=CourseRepository(Path(root)).paths('cours-test').root/'pedagogy.json'
            previous=path.read_bytes(); fake.calls.clear()
            result=self.prepare(text,fake,root,c)
            self.assertFalse(result.issues)
            self.assertFalse(any(name=='CoverageResponse' for name,_ in fake.calls))
            self.assertTrue(any(name=='ContentAssessment' for name,_ in fake.calls))
            self.assertTrue(any(p.read_bytes()==previous for p in path.parent.glob('_backups/pedagogy*.json')))
            fake.calls.clear();self.prepare(text,fake,root,c);self.assertEqual(fake.calls,[])

    def test_unassigned_historical_proof_is_rechecked_not_assumed_missing(self):
        text='La cellule est une unité du vivant.'; fake=FakeModel({1:[]})
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=fake):
            result=self.prepare(text,fake,root)
            self.assertFalse(result.issues)
            self.assertEqual(result.inventory.concepts[0].evidence[0].excerpt,text)
            self.assertTrue(any(name=='ContentAssessment' for name,_ in fake.calls))

    def test_unassigned_historical_fabrication_stays_blocked(self):
        text='Autre source, sans la définition recherchée.'; fake=FakeModel({1:[]})
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=fake):
            result=self.prepare(text,fake,root,notion(text='Une information absente du PDF.'))
            self.assertFalse(result.inventory.concepts)
            self.assertTrue(result.issues)

    def test_same_evidence_is_a_candidate_not_an_automatic_merge(self):
        text='La cellule est une unité du vivant.'; a=notion('a'); b=notion('b','Autre titre')
        fake=FakeModel({1:[fact(text,ids=['c1','c2'])]})
        with TemporaryDirectory() as root, patch.object(pedagogy,'chat_json',side_effect=fake):
            result=pedagogy.prepare_material(inventory(a,b),dict(file_hash=SHA,pages=[page(1,text)]),PLAN,
                CourseRepository(Path(root)),model=MODEL)
            self.assertFalse(result.issues)
            self.assertEqual(len(result.inventory.concepts),2)
            payload=next(data for name,data in fake.calls if name=='GroupProposal')
            self.assertTrue(all(v['same_evidence'] for v in payload['possible_targets']))
