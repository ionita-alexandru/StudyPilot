"""Régressions sur les PDF fournis ; aucune génération Ollama prétendue.

Les inventaires de test sont isolés des données utilisateur. La sélection par
le modèle est simulée, puis les citations, migrations et images
sont contrôlées contre les vrais PDF. Le test saute si ces PDF ne sont pas fournis.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from src.config import COURSE_PDF_DIR
from src.courses import cards, pedagogy
from src.courses.card_presentation import publication_view
from src.courses.planner import extract_document
from src.courses.source_recovery import illustrations_supported
from src.models.card import CardCollection, StudyCard
from src.models.concept import ConceptInventory, Concept
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, fact


class RealSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.courses = {}
        # Les PDF sont des sources de régression ; les inventaires, plans et
        # fiches utilisateur sont mutables et ne sont jamais des fixtures.
        filenames = {
            'css': 'Cours-de-CSS-c41d0f1887.pdf',
            'fourier': 'Séries de Fourier ING2 2024-2025.pdf',
            'algebra': 'Chapitre 4 Réduction endomorphismes ING2 2024-2025.pdf',
        }
        for key, name in filenames.items():
            path = COURSE_PDF_DIR / name
            if not path.is_file():
                continue
            document = extract_document(path)
            cls.courses[key] = dict(path=path, document=document,
                plan={'parts': [{'id': 'fixture-part', 'number': '1', 'page_start': 1,
                                 'page_end': len(document['pages'])}]})
        if set(cls.courses) != {'css', 'fourier', 'algebra'}:
            raise unittest.SkipTest('Les trois PDF de régression ne sont pas tous présents.')

    def prepare(self, course, concepts, facts_by_page, actions=None):
        fake = FakeModel(facts_by_page, actions)
        fake.target_titles = {c.concept_id:c.title for c in concepts}
        pages = [p for p in course['document']['pages'] if p['page'] in facts_by_page]
        fake.allow_missing_in_stream = True
        reply = fake
        inv = ConceptInventory(course_id='regression-source', file_hash=course['document']['file_hash'],
            model=MODEL, concepts=concepts, parts=[dict(part_id='fixture-part', part_number='1',
            status='complete', concepts_found=len(concepts), concepts_added_by_audit=0)])
        with tempfile.TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=reply):
            material = pedagogy.prepare_material(inv, {**course['document'], 'pages':pages}, course['plan'],
                                                CourseRepository(Path(folder)), model=MODEL)
        self.assertFalse(material.issues, material.issues)
        return material, pages

    @staticmethod
    def source_concept(identifier, title, number, quote, kind='concept', anchor=None):
        return Concept(concept_id=identifier, title=title, source_anchor=anchor or title,
            type=kind, primary_part_id='fixture-part', source_pages=[number],
            evidence=[{'page': number, 'excerpt': quote}])

    def test_all_historical_cards_require_current_review(self):
        for schema, course in zip((1, 2, 4), self.courses.values()):
            quote = course['document']['pages'][0]['raw_text'].strip()[:1000]
            card = StudyCard(card_id='fixture-legacy-card', concept_id='fixture-legacy-concept',
                title='Ancienne fiche', concept_type='concept', primary_part_id='fixture-part',
                source_pages=[1], sections=[{'key': 'definition', 'title': 'Définition', 'content': quote}])
            collection = CardCollection(course_id='regression-source', model=MODEL, schema_version=schema,
                file_hash=course['document']['file_hash'], inventory_hash='a' * 64, cards=[card],
                parts=[dict(part_id='fixture-part', part_number='1', status='complete', cards_generated=1)])
            original = collection.model_dump()
            view = publication_view(collection)
            self.assertFalse(view.cards)
            self.assertEqual(len(view.failures), 1)
            self.assertEqual(view.failures[0].status, 'review_pending')
            self.assertEqual(collection.model_dump(), original)

    def test_font_family_collects_definition_and_usage_elsewhere_in_pdf(self):
        course = self.courses['css']
        title = 'Propriété font-family'
        facts = {}
        for p in course['document']['pages']:
            for pattern, kind in [(r'font-family\s*=\s*[^\n]+', 'explanation'), (r'font-family\s*:[^;\n]+;', 'example')]:
                for m in re.finditer(pattern, p['evidence_text']):
                    facts.setdefault(p['page'], []).append(fact(m.group(), kind, title=title))
        self.assertTrue(any(f['kind'] == 'example' for fs in facts.values() for f in fs))
        number = min(facts)
        c = self.source_concept('fixture-font-family', title, number, facts[number][0]['quote'], 'property', 'font-family')
        material, _ = self.prepare(course, [c], facts)
        enriched = material.inventory.concepts[0]
        self.assertGreater(len(enriched.source_pages), 1)
        self.assertIn('example', [p.kind for p in enriched.learning_points])
        self.assertIn('explanation', [p.kind for p in enriched.learning_points])
        self.assertEqual(enriched.concept_id, c.concept_id)

    def test_colour_choices_are_retained_as_alternatives_when_attached(self):
        course = self.courses['css']
        p = course['document']['pages'][2]
        scheme_quote = next(u['excerpt'] for u in p['source_units'] if 'choose a color scheme' in u['heading'])
        target_quote = next(u['excerpt'] for u in p['source_units'] if u['heading'] == 'Configuring Color')
        target = self.source_concept('fixture-color', 'Configurer la couleur', 3, target_quote, anchor='Configuring Color')
        scheme = self.source_concept('fixture-scheme', 'Schéma de couleur', 3, scheme_quote)
        material, _ = self.prepare(course, [target, scheme], {3:[
            fact(target_quote, 'explanation', ids=['c1'], title=target.title),
            fact(scheme_quote, 'alternatives', ids=['c2'], title=scheme.title)]}, {scheme.concept_id:('attach', target.concept_id)})
        self.assertEqual(len(material.inventory.concepts), 1)
        points = material.inventory.concepts[0].learning_points
        self.assertIn(scheme_quote, [p.quote for p in points if p.kind == 'alternatives'])
        self.assertNotIn('steps', [p.kind for p in points])
        self.assertEqual(material.relations[0]['concept_id'], scheme.concept_id)

    def test_fourier_fraction_keeps_original_pdf_pixels(self):
        course = self.courses['fourier']
        p = course['document']['pages'][4]
        quote = re.search(r'd’où le coe[\s\S]*?complexe cn = [\s\S]*?\n2\n,', p['raw_text']).group()
        self.assertIn('(an −ibn)\n2', quote)
        c = self.source_concept('fixture-complex-coefficient', 'Coefficient complexe', 5, quote, 'formula')
        f = fact(quote, 'formula', title=c.title); f['concept_type']='formula'
        material, pages = self.prepare(course, [c], {5:[f]})
        fixed = material.inventory.concepts[0]
        self.assertEqual(fixed.card_role, 'visual')
        self.assertTrue(illustrations_supported(fixed, pages))
        with patch.object(cards, 'chat_json') as generate:
            card = cards._generate_batch({'number':'1'}, pages, [fixed], model=MODEL)[0]
        generate.assert_not_called()
        with pymupdf.open(course['path']) as doc:
            image = doc[4].get_pixmap(clip=pymupdf.Rect(card.illustrations[0].bbox))
            self.assertGreater(image.width, 300)
            self.assertGreater(len(image.tobytes('png')), 10000)
        self.assertEqual(card.concept_id, c.concept_id)

    def test_dirichlet_original_contains_hypotheses_and_two_sided_limit(self):
        course = self.courses['fourier']
        p = course['document']['pages'][5]
        quote = re.search(r'Théorème de Dirichlet[\s\S]*?(?=Conséquences)', p['raw_text']).group().strip()
        self.assertIn('par morceaux', quote)
        self.assertIn('f(x+)', quote)
        self.assertIn('f(x−)', quote)
        c = self.source_concept('fixture-dirichlet', 'Théorème de Dirichlet', 6, quote, 'theorem')
        f = fact(quote, 'condition', title=c.title, ambiguous=True); f['concept_type']='theorem'
        material, pages = self.prepare(course, [c], {6:[f]})
        fixed = material.inventory.concepts[0]
        self.assertIn('par morceaux', fixed.learning_points[0].quote)
        self.assertTrue(illustrations_supported(fixed, pages))
        self.assertEqual(fixed.illustrations[0].page, 6)

    def test_algebra_duplicate_merge_retains_both_origins(self):
        course = self.courses['algebra']
        available = next(p for p in course['document']['pages'] if 'On appelle valeur propre' in p['raw_text'])
        quote = re.search(r'Un vecteur propre[\s\S]*?On appelle valeur propre[\s\S]*?scalaire λ\.', available['raw_text']).group()
        # Le scénario introduit explicitement deux doublons sur la même preuve
        # réelle, même si l'utilisateur a déjà regroupé ou renommé ses notions.
        a = self.source_concept('fixture-eigenvalue-a', 'Valeur propre', available['page'], quote)
        b = self.source_concept('fixture-eigenvalue-b', 'Valeur propre d’un endomorphisme', available['page'], quote)
        concepts = [a, b]
        f = fact(quote, 'explanation', ids=['c1','c2'], title=a.title)
        material, _ = self.prepare(course, concepts, {available['page']:[f]}, {b.concept_id:('merge',a.concept_id)})
        self.assertEqual([c.concept_id for c in material.inventory.concepts], [a.concept_id])
        self.assertEqual(material.relations[0]['concept_id'], b.concept_id)
        self.assertEqual(material.relations[0]['target_id'], a.concept_id)
        self.assertEqual(material.relations[0]['source_pages'], [available['page']])
        self.assertTrue(material.relations[0]['grounding']['supported'])
        self.assertTrue(any(' '.join(quote.split()) in ' '.join(p.quote.split())
                            for p in material.inventory.concepts[0].learning_points))
        self.assertEqual([c.concept_id for c in concepts], [a.concept_id, b.concept_id])

    def test_fourier_folio_is_blank_and_page_four_has_real_continuation_context(self):
        document=self.courses['fourier']['document']
        folio=next(p for p in document['pages'] if p['page']==2)
        self.assertTrue(pedagogy.folio_only(folio))
        chunks=pedagogy.source_chunks(document)
        fourth=[c for c in chunks if c['page']==4]
        self.assertTrue(fourth)
        for chunk in fourth:
            context=pedagogy.continuation_context(chunk,chunks,document)
            self.assertTrue(context['following_text'].strip())
            self.assertTrue(context['previous_page'].strip())

    def test_three_implementation_modes_recovered_across_real_blocks_and_pages(self):
        from src.courses import learning_material
        course=self.courses['css'];document=course['document']
        units=[(p,u) for p in document['pages'] for u in p.get('source_units',[])]
        introduction=next((p,u) for p,u in units if u['heading']=='Three ways to implement CSS')
        modes={name:next((p,u) for p,u in units if u['heading']==name) for name in
            ('Inline Styles','Embedded Styles','External Styles')}
        p,heading=introduction
        c=self.source_concept('fixture-three-modes','Trois modes d’intégration',p['page'],heading['excerpt'],anchor=heading['heading'])
        # Preuve initiale réellement incomplète : le titre et le seul mode inline.
        inline=modes['Inline Styles'][1]['excerpt']
        fake=FakeModel({q['page']:[] for q in document['pages']})
        fake.by_page[p['page']]=[fact(heading['excerpt'],ids=['c1'],title=c.title),fact(inline,'example',ids=['c1'],title=c.title)]
        fake.allow_missing_in_stream=True
        def reply(**kw):
            data=json.loads(kw['messages'][-1]['content'].split('\nRéponse précédente rejetée : ')[0])
            name=kw['response_model'].__name__
            if name=='ContentAssessment':
                complete=all(any(label in pt['quote'] for pt in data['points']) for label in modes)
                return dict(disposition='developed' if complete else 'incomplete',concept_type='concept',
                    reason='Trois possibilités décrites.' if complete else 'Un seul mode sur trois est décrit.',
                    missing_information=[] if complete else ['Embedded Styles','External Styles'])
            if name=='EvidenceRecovery':
                selections=[]
                for label in ('Embedded Styles','External Styles'):
                    for unit in data['sources']:
                        if unit['heading']==label:
                            selections.append(dict(source_ref=unit['ref'],start_line=1,end_line=len(unit['lines']),kind='alternatives'))
                return dict(selections=selections,reason='Les autres possibilités suivent sur deux pages.')
            if name=='EvidenceScope':return dict(verdict='about_this_notion',reason='Les trois unités expliquent les trois modes annoncés.')
            return fake(**kw)
        inv=ConceptInventory(course_id='regression-source',file_hash=document['file_hash'],model=MODEL,concepts=[c])
        with tempfile.TemporaryDirectory() as folder,patch.object(pedagogy,'chat_json',side_effect=reply):
            result=pedagogy.prepare_material(inv,document,course['plan'],CourseRepository(Path(folder)),model=MODEL)
        self.assertFalse(result.issues,result.issues)
        evidence=result.inventory.concepts[0].evidence
        self.assertEqual(result.inventory.concepts[0].source_pages,[2,3])
        for name,(source_page,unit) in modes.items():
            self.assertTrue(any(name in e.excerpt for e in evidence),name)
            if name!='Inline Styles':
                self.assertTrue(any(e.page==source_page['page'] and e.excerpt==unit['excerpt'] for e in evidence))
        self.assertNotIn('<div style=', '\n'.join(e.excerpt for e in evidence))

    def test_recovery_retrieves_exact_math_without_normalizing_flattened_fraction(self):
        from src.courses.learning_material import recover
        course=self.courses['fourier'];document=course['document']
        found=next((p,u) for p in document['pages'] for u in p.get('source_units',[])
            if 'an' in u['excerpt'] and 'ibn' in u['excerpt'] and 'cn' in u['excerpt'])
        p,unit=found
        c=self.source_concept('fixture-complex','Coefficients complexes',p['page'],unit['excerpt'])
        def reply(**kw):
            data=json.loads(kw['messages'][-1]['content'].split('\nRéponse précédente rejetée : ')[0])
            if kw['response_model'].__name__=='EvidenceRecovery':
                candidates=[s for s in data['sources'] if s['page']==p['page'] and
                    ''.join(l['text'] for l in s['lines'])==unit['excerpt']]
                return dict(selections=[dict(source_ref=candidate['ref'],start_line=1,end_line=len(candidate['lines']),
                    kind='formula',ambiguous=True) for candidate in candidates],reason='Notation présente, extraction aplatie : utiliser le PDF original.')
            return dict(verdict='about_this_notion',reason='Formule du coefficient complexe dans le cours.')
        with patch.object(pedagogy,'chat_json',side_effect=reply):
            recovered=recover(c,[],document,MODEL,pedagogy.call_checked)
        self.assertEqual(recovered['points'][0]['quote'],unit['excerpt'])
        self.assertTrue(pedagogy.visual_needed(recovered['points'][0]))
        sources=pedagogy.visual_sources(c,recovered['points'],document)
        self.assertTrue(sources)
        self.assertEqual(sources[0].page,p['page'])
