"""Régressions du ZIP du 10 octobre : données/réponses réelles, audits simulés.

Les nouvelles décisions d'audit sont attendues explicitement, pas présentées
comme une mesure d'Ollama. Le client, les validations et le stockage sont réels.
"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from src.ai import client
from src.courses import pedagogy, learning_material as material, card_groups, cards
from src.courses.inventory import _excerpt_is_grounded, concept_evidence_issue
from src.models.concept import Concept, ConceptEvidence, LearningPoint
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, SHA, PLAN, notion, inventory, page, fact
from test_material_architecture import payload

FIXTURE = json.loads(Path(__file__).with_name('fixtures').joinpath('v15_recorded.json').read_text(encoding='utf-8'))


def raw_assessment(case):
    a = deepcopy(case['assessment'])
    aliases = {p['point_id']: f'p{i+1}' for i,p in enumerate(case['points'])}
    for key in ('point_kinds','excluded_points'):
        a[key] = {aliases[k]: v for k,v in a[key].items()}
    return {k:v for k,v in a.items() if k in material.ContentAssessment.model_fields}


class RecordedRegressionTests(unittest.TestCase):
    def test_real_optional_wishlists_do_not_override_sourced_sufficiency(self):
        for case in FIXTURE['assessments']:
            if case['concept']['title'].startswith('Calcul des coefficients'): continue
            with self.subTest(title=case['concept']['title']):
                c = Concept.model_validate(case['concept']); old = deepcopy(case)
                def reply(**kw):
                    name = kw['response_model'].__name__
                    if name == 'ContentAssessment': return raw_assessment(case)
                    if name == 'SourceJudgment':
                        return dict(supported=True,reason='Même phrase conservée ; seul un doublon est exclu.')
                    if name == 'ReferencedAdequacy':
                        return dict(disposition='developed',reason='Rôle ou enseignement annoncé présent dans les passages.',
                            blocking_gaps=[], optional_information=case['assessment']['missing_information'])
                    raise AssertionError(name)
                with patch.object(pedagogy,'chat_json',side_effect=reply):
                    a = material.assess(c,case['points'],MODEL,pedagogy.call_checked)
                self.assertEqual(a['disposition'],'developed')
                self.assertFalse(a['missing_information'])
                self.assertEqual(a['adequacy_check']['optional_information'],case['assessment']['missing_information'])
                self.assertEqual(case,old)  # aucune réécriture de citation

    def test_a_true_omission_needs_a_literal_source_signal_and_remains_blocking(self):
        c=notion(text='La méthode comporte deux phases.');p=dict(point_id='original',kind='explanation',page=1,quote=c.evidence[0].excerpt)
        def reply(**kw):
            if kw['response_model'].__name__=='ContentAssessment':
                return dict(disposition='developed',concept_type='method',reason='Annonce de deux phases.',missing_information=['Phases'])
            if kw['response_model'].__name__=='GapAudit':
                return dict(disposition='incomplete',confirmed_gap_indices=[1],reason='Deux phases promises et absentes.')
            return dict(disposition='incomplete',reason='Les deux phases annoncées manquent.',blocking_gaps=[
                dict(description='Les phases ne sont pas présentes.',references=[dict(point_id='p1',start_line=1,end_line=1)])])
        with patch.object(pedagogy,'chat_json',side_effect=reply):
            result=material.assess(c,[p],MODEL,pedagogy.call_checked)
        self.assertEqual(result['disposition'],'incomplete')
        self.assertTrue(result['missing_information'])
        def fabricated(**kw):
            value=reply(**kw)
            if kw['response_model'].__name__=='ReferencedAdequacy':value['blocking_gaps'][0]['references'][0]['end_line']=99
            return value
        with patch.object(pedagogy,'chat_json',side_effect=fabricated), self.assertRaisesRegex(ValueError,'Intervalle source invalide'):
            material.assess(c,[p],MODEL,pedagogy.call_checked)

    def test_real_native_unit_quotes_are_accepted_without_erasing_math_symbols(self):
        seen=0
        for record in FIXTURE['grounding']:
            quote=record['evidence']['excerpt']; pg=record['page']
            self.assertTrue(_excerpt_is_grounded(quote,pg),record['title'])
            # Certains passages sont présents uniquement dans l'ordre des blocs.
            if not _excerpt_is_grounded(quote,{k:v for k,v in pg.items() if k!='source_units'}):seen+=1
        self.assertGreater(seen,0)
        for correct,wrong in [('c_n = (a_n - i b_n)/2','c_n = a_n - i b_n'),
                              ('x <= 2','x >= 2'),('f(x) = x^2','f(x) = x2'),('A = B','a = B')]:
            self.assertFalse(_excerpt_is_grounded(wrong,page(1,correct)),wrong)
        self.assertFalse(_excerpt_is_grounded('x',page(1,'exemple')))

    def test_independent_with_stale_target_cannot_create_a_relation(self):
        self.assertIn('independent exige',FIXTURE['invalid_independent_target_error']['error'])
        # Le client v15 perdait le JSON en cas de ValidationError. Le journal
        # prouve le conflit ; ces variations reproduisent le contrat en faute.
        records=[dict(relation='independent',target_ref=target,reason='Contenu autonome.') for target in ('t1','unknown')]
        for record in records:
            value=card_groups.group_schema({}).model_validate(record)
            self.assertEqual(value.relation,'independent');self.assertIsNone(value.target_ref)
        with self.assertRaises(ValidationError):
            card_groups.group_schema({}).model_validate(dict(relation='supplement',target_ref='ghost',reason='Aucune cible réelle.'))

    def test_audit_can_correct_supplement_to_duplicate_with_both_proofs(self):
        candidates=[r['response'] for r in FIXTURE['rejected'] if r['schema']=='RelationReview' and r['response'].get('relation')=='same_notion']
        self.assertTrue(candidates)
        recorded=candidates[0]
        a=notion('a','Types de liste','Les listes utilisent list-style-type.');b=notion('b','Propriété list-style-type',a.evidence[0].excerpt)
        own=[dict(point_id=p,quote=a.evidence[0].excerpt,page=1,kind='explanation') for p in recorded['source_point_ids']]
        target=[dict(point_id=p,quote=a.evidence[0].excerpt,page=1,kind='explanation') for p in recorded['target_point_ids']]
        def reply(**kw):
            if kw['response_model'].__name__=='RelationReview':return recorded
            return dict(relation='supplement',target_ref='t1',reason='Proposition initiale de rattachement.')
        with patch.object(pedagogy,'chat_json',side_effect=reply):
            result=card_groups.choose_group('b',['a'],{'a':a,'b':b},{'a':target,'b':own},
                dict(disposition='supporting'),model=MODEL,call=pedagogy.call_checked)
        self.assertEqual(result['relation'],'duplicate')
        self.assertEqual(result['proposed_relation'],'supplement')
        self.assertTrue(result['grounding']['supported'])
        self.assertEqual(result['grounding']['source_point_ids'],recorded['source_point_ids'])

    def test_source_recovery_retains_valid_addition_when_neighbor_is_refused(self):
        c=notion('a','Mesurer','La mesure comporte deux phases.')
        original=dict(point_id='a',page=1,kind='explanation',quote=c.evidence[0].excerpt)
        doc={'pages':[page(1,c.evidence[0].excerpt),page(2,'On observe, puis on note la durée.'),page(3,'Un triangle possède trois côtés.')]}
        def reply(**kw):
            data=payload(kw)
            if kw['response_model'].__name__=='EvidenceRecovery':
                return dict(selections=[dict(source_ref=u['ref'],start_line=1,end_line=1,kind='explanation')
                    for u in data['sources'] if u['page'] in (2,3)],reason='Deux ajouts proposés.')
            addition=data['additions'][0]
            return dict(verdict='about_this_notion' if addition['page']==2 else 'other_notion',reason='Portée contrôlée sur chaque ajout.')
        with patch.object(pedagogy,'chat_json',side_effect=reply) as model:
            result=material.recover(c,[original],doc,MODEL,pedagogy.call_checked)
        self.assertEqual([p['page'] for p in result['points']],[2])
        self.assertEqual(result['rejected'][0]['point']['page'],3)
        self.assertEqual(model.call_count,3)

    def test_invalid_interval_is_reselected_locally_never_clamped(self):
        recorded=next(r['response'] for r in FIXTURE['rejected'] if 'Intervalle source invalide : 1..4, lignes 1..3' in r['error'])
        selection=recorded['selections'][0]
        c=notion();doc={'pages':[page(21,'Titre\nInformation propre à cette notion.\nAutre explication.')]}
        unit={'ref':selection['source_ref'],'page':21,'heading':'Titre','lines':pedagogy.numbered_lines(doc['pages'][0]['raw_text'])}
        def reply(**kw):
            name=kw['response_model'].__name__
            if name=='EvidenceRecovery':return dict(selections=[selection],reason=recorded['reason'])
            if name=='SelectionRepair':
                self.assertEqual(payload(kw)['invalid_selection']['end_line'],4)
                return dict(start_line=2,end_line=2)
            return dict(verdict='about_this_notion',reason='Le nouveau passage sélectionné concerne la notion.')
        with patch.object(material,'source_candidates',return_value=[unit]),patch.object(pedagogy,'chat_json',side_effect=reply):
            result=material.recover(c,[],doc,MODEL,pedagogy.call_checked)
        self.assertEqual(result['points'][0]['quote'],'Information propre à cette notion.\n')
        with patch.object(material,'source_candidates',return_value=[unit]),patch.object(pedagogy,'chat_json',side_effect=lambda **kw:
                dict(start_line=1,end_line=4) if kw['response_model'].__name__=='SelectionRepair' else reply(**kw)), self.assertRaises(ValueError):
            material.recover(c,[],doc,MODEL,pedagogy.call_checked)

    def test_metadata_synonyms_are_safe_but_do_not_turn_alternatives_into_steps(self):
        a=material.ContentAssessment.model_validate(dict(disposition='developed',concept_type='concept',reason='Définition.',point_kinds={'p1':'definition','p2':'remark'}))
        self.assertEqual(a.point_kinds,{'p1':'explanation','p2':'explanation'})
        with self.assertRaises(ValidationError):
            material.ContentAssessment.model_validate(dict(disposition='developed',concept_type='method',reason='Avis.',point_kinds={'p1':'method'}))
        self.assertEqual(material.SourceSelection.model_validate(dict(source_ref='u1',start_line=1,end_line=1,kind='alternatives')).kind,'alternatives')

    def test_short_real_advice_survives_while_a_code_fragment_stays_supporting(self):
        text='color: red;';c=notion(text=text);p=dict(point_id='p',quote=text,page=1,kind='example')
        fake=FakeModel({1:[]})
        with patch.object(pedagogy,'chat_json',side_effect=fake):a=material.assess(c,[p],MODEL,pedagogy.call_checked)
        self.assertEqual(a['disposition'],'supporting')

    def test_math_continuation_is_prioritized_and_partial_visual_is_not_published(self):
        case=next(x for x in FIXTURE['assessments'] if x['concept']['title'].startswith('Calcul des coefficients'))
        c=Concept.model_validate(case['concept']);doc=FIXTURE['continuation'];first=case['points']
        candidates=material.source_candidates(c,first,doc,limit=2200)
        self.assertTrue(any(u['page']==5 and u['ref'].startswith('u5-0') for u in candidates))
        assessment=case['assessment']
        with patch.object(pedagogy,'chat_json',return_value=dict(identified=True,complete_excerpt=False,point_ids=['p1'],reason='L’énoncé finit au milieu de la phrase.')):
            partial=material.visual_assessment(c,first,assessment,doc,MODEL,pedagogy.call_checked)
        self.assertEqual(partial['disposition'],'unreadable')
        # Continuation réellement présente dans les blocs natifs de la page 5.
        tail=dict(point_id='continuation',page=5,kind='formula',quote=doc['pages'][1]['source_units'][0]['native_text'])
        full=first+[tail]
        with patch.object(pedagogy,'chat_json',return_value=dict(identified=True,complete_excerpt=True,point_ids=['p1','p6'],reason='Début de proposition et expressions des coefficients localisés.')):
            verified=material.visual_assessment(c,full,assessment,doc,MODEL,pedagogy.call_checked)
        self.assertEqual(verified['presentation'],'source_visual')
        self.assertEqual({i['page'] for i in verified['visual_sources']},{4,5})
        self.assertEqual(verified['source_disposition'],'unreadable')

    def test_anchor_match_is_not_a_proof_of_assignment(self):
        case=next(x for x in FIXTURE['assessments'] if x['concept']['title']=='Propriété margin')
        wrong=next(p for p in case['points'] if 'AKA rigid or fixed' in p['quote'])
        c=Concept.model_validate(case['concept'])
        with patch.object(pedagogy,'chat_json',return_value=dict(items=[dict(point_id='p1',verdict='other_notion',reason='Marge de la page dans un conseil de design ; pas la propriété annoncée.')])):
            result=material.check_candidates(c,[wrong],MODEL,pedagogy.call_checked)
        self.assertEqual(result[0]['point_id'],wrong['point_id'])
        self.assertEqual(result[0]['verdict'],'other_notion')

    def test_single_fenced_json_is_accepted_and_multiple_objects_are_diagnosed(self):
        reply=dict(disposition='developed',concept_type='concept',reason='Définition complète.')
        with patch.object(client,'chat_text',return_value='```json\n'+json.dumps(reply)+'\n```'):
            self.assertEqual(client.chat_json(response_model=material.ContentAssessment,messages=[])['disposition'],'developed')
        raw=json.dumps(reply)+'\n'+json.dumps(reply)
        with patch.object(client,'chat_text',return_value=raw),self.assertRaises(ValidationError) as caught:
            client.chat_json(response_model=material.ContentAssessment,messages=[])
        self.assertEqual(caught.exception.response_text,raw)
        self.assertTrue(caught.exception.errors())
        diagnostics=[]
        with patch.object(pedagogy,'chat_json',side_effect=caught.exception),self.assertRaises(ValueError):
            pedagogy.call_checked(material.ContentAssessment,'Contrôle',{},MODEL,lambda r:r,diagnostics)
        self.assertEqual(len(diagnostics),2)
        self.assertTrue(all(r['response_excerpt']==raw for r in diagnostics))

    def test_v15_migration_reuses_coverage_backs_up_and_does_not_reuse_bad_decisions(self):
        c=notion();text=c.evidence[0].excerpt;fake=FakeModel({1:[fact(text)]})
        with TemporaryDirectory() as folder,patch.object(pedagogy,'chat_json',side_effect=fake):
            repo=CourseRepository(Path(folder));doc={'file_hash':SHA,'pages':[page(1,text)]}
            with patch.object(pedagogy,'QUALITY_VERSION',16),patch.object(pedagogy,'DECISION_PROTOCOL',4):
                pedagogy.prepare_material(inventory(c),doc,PLAN,repo,model=MODEL)
            path=repo.paths('cours-test').root/'pedagogy.json';old=json.loads(path.read_text())
            old['content_reviews'][c.concept_id]['assessment'].update(disposition='incomplete',missing_information=['Un exemple de plus'])
            path.write_text(json.dumps(old));before=path.read_bytes();fake.calls.clear()
            materialized=pedagogy.prepare_material(inventory(c),doc,PLAN,repo,model=MODEL)
            self.assertFalse(materialized.issues)
            self.assertFalse(any(n=='CoverageResponse' for n,_ in fake.calls))
            self.assertTrue(any(n=='ContentAssessment' for n,_ in fake.calls))
            self.assertTrue(any(p.read_bytes()==before for p in path.parent.glob('_backups/*.json')))
            fake.calls.clear();again=pedagogy.prepare_material(inventory(c),doc,PLAN,repo,model=MODEL)
            self.assertEqual(materialized,again);self.assertFalse(fake.calls)


if __name__=='__main__': unittest.main()
