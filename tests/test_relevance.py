"""Pertinence vérifiable, reprise automatique et recherche dans tout le PDF."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from src.config import STUDY_MODEL
from src.courses import cards, inventory, relevance
from src.courses.planner import extract_document
from src.courses.source_recovery import recover_document_evidence
from src.models.card import CardCollection
from src.models.concept import Concept, ConceptEvidence, ConceptInventory
from src.storage.course_repository import CourseRepository


def concept(name, page=1, kind='concept'):
    return Concept(concept_id=name,title=name,source_anchor=name,type=kind,
        primary_part_id='p1',source_pages=[page],evidence=[{'page':page,'excerpt':name}])


def page(n,text,heading=''):
    return {'page':n,'raw_text':text,'analysis_text':text,'evidence_text':text,
        'source_units':[{'heading':heading,'excerpt':text,'ocr_used':False}]}


def document(pages):
    return {'file_hash':'a'*64,'page_count':len(pages),'pages':pages}


class RelevanceTests(unittest.TestCase):
    def test_isolated_mention_is_recorded_and_idempotent(self):
        d=document([page(1,'Liste de noms\nCytosol')])
        c=relevance.review_concept(concept('Cytosol'),d)
        self.assertEqual(c.relevance,'mention_only')
        self.assertIn('1 pages',c.relevance_reason)
        self.assertTrue(relevance.verified_mention(c,d))
        self.assertEqual(relevance.review_concept(c,d),c)

    def test_heading_elsewhere_recovers_definition_without_changing_identity(self):
        d=document([page(1,'Liste de noms\nCytosol'),page(2,'Cytosol\nLe cytosol constitue le milieu liquide de la cellule.','Cytosol')])
        original=concept('Cytosol');c=relevance.review_concept(original,d)
        self.assertEqual(c.concept_id,original.concept_id)
        self.assertEqual(c.primary_part_id,'p1')
        self.assertEqual(c.source_pages,[1,2]);self.assertIsNone(c.evidence_issue)
        self.assertEqual(c.evidence[0].page,2)
        self.assertIn('milieu liquide',c.evidence[0].excerpt)

    def test_exact_identifier_and_real_page_for_programming_property(self):
        d=document([page(1,'Noms des paramètres\nmax-retries'),page(2,'max-retries: 4;\nmin-retries: 1;')])
        c=relevance.review_concept(concept('max-retries',kind='property'),d)
        self.assertEqual(c.evidence[0].excerpt,'max-retries: 4;')
        self.assertEqual(c.evidence[0].page,2)
        other=document([page(1,'max-retries'),page(2,'min-retries: 4;')])
        c=relevance.review_concept(concept('max-retries',kind='property'),other)
        self.assertNotIn('min-retries',c.evidence[0].excerpt)

    def test_damaged_or_unreadable_extraction_is_not_a_mention(self):
        for second in [dict(page(2,''),image_regions=[[0,0,100,100]]),page(2,'Texte illisible �'),dict(page(2,'x'),extraction_error='OCR failed')]:
            d=document([page(1,'Cytosol'),second])
            c=relevance.review_concept(concept('Cytosol'),d)
            self.assertEqual(c.relevance,'active');self.assertIsNotNone(c.evidence_issue)
        d=document([page(1,'Cytosol')]);d['page_count']=2
        self.assertEqual(relevance.review_concept(concept('Cytosol'),d).relevance,'active')

    def test_new_explanation_reactivates_previous_mention(self):
        d=document([page(1,'Cytosol')]);c=relevance.review_concept(concept('Cytosol'),d)
        d['pages'][0]=page(1,'Cytosol\nLe cytosol constitue le milieu liquide de la cellule.','Cytosol')
        self.assertFalse(relevance.verified_mention(c,d))
        reviewed=relevance.review_concept(c,d)
        self.assertEqual(reviewed.relevance,'active');self.assertIsNone(reviewed.evidence_issue)

    def test_plural_occurrence_prevents_false_exclusion(self):
        d=document([page(1,'Mitochondrie'),page(2,'Les mitochondries participent à la production énergétique.')])
        self.assertIsNone(relevance.mention_only_reason(concept('Mitochondrie'),d))

    def test_ambiguous_names_and_missing_term_are_not_silently_excluded(self):
        d=document([page(1,'Cytosol'),page(2,'Cytosol\nPremière explication de ce sujet.','Cytosol'),page(3,'Cytosol\nAutre explication incompatible avec la précédente.','Cytosol')])
        self.assertIsNotNone(relevance.review_concept(concept('Cytosol'),d).evidence_issue)
        self.assertEqual(relevance.review_concept(concept('Absent'),d).relevance,'active')

    def test_semantic_review_of_incidental_sentence_uses_same_model(self):
        d=document([page(1,'Cytosol est cité ici parmi les thèmes qui ne seront pas étudiés.')])
        c=concept('Cytosol').model_copy(update={'evidence_issue':'preuve insuffisante'})
        def reply(**kwargs):
            payload=json.loads(kwargs['messages'][-1]['content'])
            return {'verdicts':[{'source_id':s['source_id'],'status':'mention','quote':'','reason':'Nom cité sans explication.'} for s in payload['sources']]}
        with patch.object(relevance,'chat_json',side_effect=reply) as model:
            r=relevance.resolve_uncertain(c,d,model=STUDY_MODEL)
        self.assertEqual(r.relevance,'mention_only');self.assertTrue(relevance.verified_mention(r,d))
        self.assertEqual(model.call_args.kwargs['model'],STUDY_MODEL)
        d['pages'][0]['evidence_text']+='\nCytosol : une explication nouvelle.'
        self.assertFalse(relevance.verified_mention(r,d))

    def test_semantic_failure_invention_or_missing_verdict_keeps_blocked(self):
        d=document([page(1,'Cytosol est cité ici.')]);c=concept('Cytosol').model_copy(update={'evidence_issue':'insuffisant'})
        replies=[RuntimeError('Ollama indisponible'),{'verdicts':[]},
                 {'verdicts':[{'source_id':0,'status':'developed','quote':'Cytosol : définition inventée.','reason':'Définition.'}]}]
        for response in replies:
            with patch.object(relevance,'chat_json',side_effect=response if isinstance(response,Exception) else None,return_value=response):
                result=relevance.resolve_uncertain(c,d,model=STUDY_MODEL)
            self.assertEqual(result.relevance,'active');self.assertIn('à reprendre',result.evidence_issue)

    def test_semantic_review_recovers_only_literal_supported_quote(self):
        text='Cytosol est le milieu liquide de la cellule.'
        d=document([page(1,text)]);c=concept('Cytosol').model_copy(update={'evidence_issue':'insuffisant'})
        with patch.object(relevance,'chat_json',return_value={'verdicts':[{'source_id':0,'status':'developed','quote':text,'reason':'Définition explicite.'}]}):
            result=relevance.resolve_uncertain(c,d,model=STUDY_MODEL)
        self.assertIsNone(result.evidence_issue);self.assertEqual(result.evidence[0].excerpt,text)

    def test_whole_pdf_review_does_not_truncate_before_late_occurrence(self):
        pages=[page(1,'Cytosol')]+[page(n,'Le cours présente ce nom : Cytosol, sans explication supplémentaire.') for n in range(2,10)]
        d=document(pages);c=concept('Cytosol').model_copy(update={'evidence_issue':'insuffisant'})
        called=[]
        def reply(**kwargs):
            sources=json.loads(kwargs['messages'][-1]['content'])['sources'];called.extend(s['page'] for s in sources)
            return {'verdicts':[{'source_id':s['source_id'],'status':'uncertain' if s['page']==9 else 'mention','reason':'Contexte à vérifier.','quote':''} for s in sources]}
        with patch.object(relevance,'chat_json',side_effect=reply):result=relevance.resolve_uncertain(c,d,model=STUDY_MODEL)
        self.assertIn(9,called);self.assertEqual(result.relevance,'active')

    def test_ignored_mention_preserves_cached_cards_and_remains_visible(self):
        d=document([page(1,'Noms des sujets\nCytosol\nUne cellule est une unité du vivant.')])
        ignored=relevance.review_concept(concept('Cytosol'),d)
        good=concept('Cellule').model_copy(update={'evidence':[ConceptEvidence(page=1,excerpt='Une cellule est une unité du vivant.')]})
        inv=ConceptInventory(course_id='biologie',file_hash=d['file_hash'],model=STUDY_MODEL,concepts=[good,ignored],
            parts=[{'part_id':'p1','part_number':'1','status':'complete','concepts_found':2,'concepts_added_by_audit':0}])
        card=cards._validate_cards([{'concept_id':good.concept_id,'sections':[{'title':'Définition','content':good.evidence[0].excerpt}]}],[good],d['pages'])[good.concept_id]
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory('biologie',inv.model_dump(mode='json'))
            # Réutilise un hash v11 sans les nouveaux champs de pertinence.
            legacy=good.model_dump(mode='json')
            for f in ('illustrations','relevance','relevance_reason','relevance_file_hash','relevance_proof_hash','learning_points','card_role'):legacy.pop(f)
            oldhash=hashlib.sha256(json.dumps(legacy,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            repo.save_cards('biologie',CardCollection(course_id='biologie',file_hash=d['file_hash'],inventory_hash='b'*64,model=STUDY_MODEL,cards=[card],concept_hashes={good.concept_id:oldhash}).model_dump(mode='json'))
            for name,value in [('CourseRepository',repo),('load_course',{'file_hash':d['file_hash'],'source_filename':'bio.pdf'}),('load_course_plan',{'parts':[{'id':'p1','number':'1'}]}),('extract_document',d)]:stack.enter_context(patch.object(cards,name,return_value=value))
            from src.courses.pedagogy import Material
            stack.enter_context(patch.object(cards,'prepare_material',return_value=Material(inv, 'test')))
            audit=stack.enter_context(patch.object(cards,'audit_cards',return_value={good.concept_id:[]}))
            generate=stack.enter_context(patch.object(cards,'_generate_batch'))
            result=cards.build_cards('biologie')
            audit.assert_called_once()
            generate.assert_not_called();self.assertEqual(result.cards,[card])
            self.assertEqual(len(result.ignored),1);self.assertEqual(result.parts[0].status,'complete')
            self.assertFalse(result.blocked)
            import app
            with app.app.test_request_context():
                html=app.app.jinja_env.get_template('part.html').render(course={'course_id':'biologie','title':'Biologie'},courses=[],plan={'parts':[]},part={'id':'p1','number':'1','title':'Cellule','page_start':1,'page_end':1},cards=[card.model_dump(mode='json')],ignored_mentions=[i.model_dump(mode='json') for i in result.ignored],pdf_url='/bio.pdf')
            self.assertIn('mention(s) sans fiche',html);self.assertIn('Cytosol',html)


class RealRelevanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        p=cls.root/'data/pdfs/Cours-de-CSS-c41d0f1887.pdf'
        if not p.exists():raise unittest.SkipTest('PDF de régression absent')
        cls.document=extract_document(p)

    def test_real_seven_remaining_cases_six_recovered_one_ignored(self):
        for name in ('background-color','font-height','margin','text-align','text-decoration','width'):
            c=concept(name,3,'property');c.title='Propriété '+name
            fixed=relevance.review_concept(c,self.document)
            self.assertEqual(fixed.relevance,'mention_only' if name=='font-height' else 'active')
            if name!='font-height':
                self.assertIsNone(fixed.evidence_issue,name)
                self.assertIn(name,fixed.evidence[0].excerpt)
            self.assertEqual(fixed,relevance.review_concept(fixed,self.document))
        # Reproduit le cache enrichi dont l'ancre n'est pas conservée.
        c=concept('Layout de page avec colonnes',21).model_copy(update={'source_anchor':None,
            'evidence':[ConceptEvidence(page=21,excerpt='Two Column Page Layout\nleftcolumn\nrightcolumn\ncontent\nfloatright')]})
        fixed=relevance.review_concept(c,self.document)
        self.assertIsNone(fixed.evidence_issue);self.assertEqual(len(fixed.illustrations),1)
        self.assertEqual(fixed.illustrations[0].page,21)

    def test_another_real_math_pdf_keeps_native_text_and_uses_no_css_rules(self):
        p=self.root/'data/pdfs/Séries de Fourier ING2 2024-2025.pdf'
        if not p.exists():self.skipTest('PDF de mathématiques absent')
        doc=extract_document(p)
        with pymupdf.open(p) as native:
            self.assertEqual(len(doc['pages']),len(native))
            for i,physical in enumerate(native):self.assertEqual(doc['pages'][i]['raw_text'],physical.get_text('text',sort=False))
        # Un terme inexistant reste un défaut de preuve, pas une simple mention.
        c=concept('TermeQuiNeFigurePasDansLeCours')
        self.assertEqual(relevance.review_concept(c,doc).relevance,'active')
