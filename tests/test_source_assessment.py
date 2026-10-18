"""Données v15.1 réelles ; nouvelles réponses contrôlées, sans mesure d'Ollama."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from src.courses import learning_material as material, pedagogy, card_groups
from src.models.concept import Concept
from test_pedagogy import MODEL, FakeModel, notion, page
from test_material_architecture import payload

CASES = json.loads(Path(__file__).with_name('fixtures').joinpath('v15_1_recorded.json').read_text())


def case_named(title):
    return next(c for c in CASES if c.get('issue', {}).get('title') == title)


class V152Regressions(unittest.TestCase):
    def assess_gap(self, points, *, confirmed=True, ref=None, disposition='incomplete'):
        def reply(**kw):
            name = kw['response_model'].__name__
            if name == 'ContentAssessment':
                return dict(disposition='incomplete', concept_type='concept', reason='À contrôler.', missing_information=['Développement'])
            if name == 'ReferencedAdequacy':
                data = payload(kw)
                self.assertTrue(data['points'][0]['lines'])
                return dict(disposition='incomplete', reason='Manque proposé.', blocking_gaps=[dict(description='Développement annoncé absent.',
                    references=[ref or dict(point_id='p1', start_line=1, end_line=1)])])
            if name == 'GapAudit':
                data = payload(kw)
                self.assertEqual(data['proposed_gaps'][0]['source_signal'], points[0]['quote'].splitlines(keepends=True)[0])
                return dict(disposition=disposition if confirmed else 'developed', confirmed_gap_indices=[1] if confirmed else [],
                    reason='Manque réel.' if confirmed else 'Le cours ne promet pas de démonstration.')
            return FakeModel({1:[]})(**kw)
        with patch.object(pedagogy, 'chat_json', side_effect=reply):
            return material.assess(notion(), points, MODEL, pedagogy.call_checked)

    def test_recorded_commented_signals_reproduce_the_old_failure(self):
        records=[a for c in CASES for a in c.get('rejected', []) if 'passage réel' in a['error']]
        self.assertTrue(records)
        for a in records:
            old = material.SourceAdequacy.model_validate_json(a['response_excerpt'])
            self.assertTrue(old.blocking_gaps)
            # Le contrat nouveau ne permet plus de rédiger ce commentaire en guise de citation.
            with self.assertRaises(ValidationError):
                material.ReferencedAdequacy.model_validate_json(a['response_excerpt'])

    def test_real_points_are_copied_with_signs_unchanged(self):
        points=case_named('Calcul des coefficients de Fourier (Proposition 2.2.1)')['points']
        original=deepcopy(points)
        result=self.assess_gap(points)
        self.assertEqual(result['adequacy_check']['blocking_gaps'][0]['source_signal'], points[0]['quote'].splitlines(keepends=True)[0])
        self.assertEqual(points, original)

    def test_optional_proof_is_not_a_blocking_gap_even_with_real_citation(self):
        points=case_named('Exemple de convergence d’une série de Fourier : \\(\\sum_{n\\ge1} \\sin(nx)/n\\) converge')['points']
        result=self.assess_gap(points, confirmed=False)
        self.assertEqual(result['disposition'], 'developed')
        self.assertFalse(result['missing_information'])
        self.assertTrue(result['adequacy_check']['optional_information'])
        self.assertFalse(result['adequacy_check']['gap_audit']['confirmed_gap_indices'])

    def test_true_omission_stays_blocking(self):
        p=dict(point_id='origin', page=1, kind='explanation', quote='La méthode comporte deux phases.')
        result=self.assess_gap([p])
        self.assertEqual(result['disposition'], 'incomplete')
        self.assertTrue(result['missing_information'])

    def test_invalid_interval_or_unknown_point_cannot_be_clamped(self):
        p=dict(point_id='origin', page=1, kind='explanation', quote='Un développement annoncé.')
        for ref in [dict(point_id='p1',start_line=1,end_line=99),dict(point_id='ghost',start_line=1,end_line=1)]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):self.assess_gap([p], ref=ref)

    def test_schema_keeps_disposition_out_of_point_kinds(self):
        for value in ['name_only','supporting','unreadable','example']:
            if value=='example':
                with self.assertRaises(ValidationError):material.ContentAssessment.model_validate(dict(disposition=value,concept_type='concept',reason='Avis'))
            else:
                with self.assertRaises(ValidationError):material.ContentAssessment.model_validate(dict(disposition='developed',concept_type='concept',reason='Avis',point_kinds={'p1':value}))
        schema=material.ReferencedAdequacy.model_json_schema()
        self.assertNotIn('source_signal', json.dumps(schema))

    def test_long_target_preview_includes_the_actual_support_passage(self):
        own=[dict(quote='padding-right: 2px;')]
        target=[dict(quote='Introduction générale. '*100),dict(quote='padding-right: 2px;')]
        self.assertIn('padding-right: 2px;',card_groups.target_preview(own,target))

    def test_real_supporting_response_explains_the_missing_supplement_choice(self):
        c=case_named('Propriété padding-right')
        self.assertEqual(c['group']['result']['relation'],'independent')
        self.assertIn('padding',c['group']['result']['reason'])
        # Rejouer une proposition supplement auditée : le titre plus large n'empêche pas le lien.
        a=notion('a','Propriété padding','Le padding règle l’espace intérieur.');b=notion('b','Propriété padding-right','padding-right: 2px;')
        points={'a':[dict(point_id='a1',quote=a.evidence[0].excerpt,page=1)],'b':[dict(point_id='b1',quote=b.evidence[0].excerpt,page=1)]}
        def reply(**kw):
            if kw['response_model'].__name__=='RelationReview':return dict(relation='develops_target',source_point_ids=['b1'],target_point_ids=['a1'],reason='Usage concret de la même propriété.')
            self.assertIn('enseignement plus large',kw['messages'][0]['content'])
            return dict(relation='supplement',target_ref='t1',reason='Sous-partie illustrée.')
        with patch.object(pedagogy,'chat_json',side_effect=reply):
            result=card_groups.choose_group('b',['a'],{'a':a,'b':b},points,dict(disposition='supporting'),model=MODEL,call=pedagogy.call_checked)
        self.assertEqual(result['relation'],'supplement');self.assertTrue(result['grounding']['supported'])

    def test_incomplete_extraction_reaches_original_pdf_check(self):
        c=notion('c','Formule', 'Expression annoncée.');point=dict(point_id='p',page=1,quote='Expression annoncée.',kind='formula')
        cache={};problems=[];calls=[]
        def fake_visual(*args):
            calls.append(args[2]['disposition']);return args[2] | {'visual_check': {'identified':False,'complete_excerpt':False}}
        with patch.object(material,'assess',return_value=dict(disposition='incomplete',concept_type='formula',reason='Extraction tronquée.',missing_information=['Suite'],excluded_points={})),patch.object(material,'recover',return_value={'points':[]}),patch.object(material,'visual_assessment',side_effect=fake_visual):
            result=material.review_contents({'c':c},{'c':[point]}, {'pages':[page(1,point['quote'])]}, cache,problems,model=MODEL,call=None,save=lambda:None)
        self.assertEqual(calls,['incomplete'])
        self.assertEqual(result['c']['disposition'],'incomplete')
        self.assertFalse(result['c']['visual_check']['complete_excerpt'])

    def test_failed_gap_audit_cannot_publish_or_be_cached_as_sufficient(self):
        p=dict(point_id='origin',page=1,kind='explanation',quote='La méthode comporte deux phases.')
        def reply(**kw):
            name=kw['response_model'].__name__
            if name=='ContentAssessment':return dict(disposition='incomplete',concept_type='method',reason='Deux phases annoncées.',missing_information=['Phases'])
            if name=='ReferencedAdequacy':return dict(disposition='incomplete',reason='Phases absentes.',blocking_gaps=[dict(description='Phases absentes.',references=[dict(point_id='p1',start_line=1,end_line=1)])])
            raise ConnectionError('Audit indisponible')
        with patch.object(pedagogy,'chat_json',side_effect=reply),self.assertRaisesRegex(ValueError,'Audit indisponible'):
            material.assess(notion(),[p],MODEL,pedagogy.call_checked)

    def test_real_diagnostic_counts_preparation_source_gaps_in_summary(self):
        from src.courses.cards import cards_summary
        from src.models.card import CardCollection
        cases=[c for c in CASES if c.get('issue',{}).get('status')=='source_insufficient']
        self.assertEqual(len(cases),3)
        collection=CardCollection(course_id='test-real',file_hash='a'*64,
            model='fixture',inventory_hash='c'*64,cards=[],parts=[],review_issues=[c['issue'] for c in cases])
        result=cards_summary(collection)
        self.assertEqual(result['blocked_concepts'],0)
        self.assertEqual(result['insufficient_sources'],3)
        self.assertEqual(result['review_issues'],3)
