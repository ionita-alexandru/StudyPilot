"""Contrats v14 : le modèle est simulé, les sources et contrôles Python sont réels.

Ces tests ne constituent pas une validation d'une génération réelle Ollama.
"""
from contextlib import ExitStack
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.courses import cards, card_grounding, pedagogy
from src.courses.card_presentation import publication_view, present_card
from src.models.concept import Concept, ConceptEvidence, ConceptInventory, LearningPoint
from src.models.card import StudyCard, CardCollection
from src.storage.course_repository import CourseRepository

MODEL = 'modele-configure-test'
SHA = 'e' * 64
PLAN = {'parts': [{'id': 'p1', 'number': '1', 'page_start': 1, 'page_end': 20}]}


def notion(identifier='cellule', title='Cellule', text='La cellule est une unité du vivant.', page=1, kind='concept'):
    return Concept(concept_id=identifier, title=title, source_anchor=title, type=kind,
                   primary_part_id='p1', source_pages=[page], evidence=[{'page': page, 'excerpt': text}])


def inventory(*concepts):
    return ConceptInventory(course_id='cours-test', file_hash=SHA, model=MODEL, concepts=list(concepts),
        parts=[{'part_id': 'p1', 'part_number': '1', 'status': 'complete',
                'concepts_found': len(concepts), 'concepts_added_by_audit': 0}])


def page(number, text):
    return {'page': number, 'raw_text': text, 'analysis_text': text, 'evidence_text': text,
            'page_rect': [0, 0, 500, 700]}


def fact(quote, kind='explanation', ids=None, title='Cellule', **extra):
    return dict(title=title, source_anchor=title, concept_type='concept',
                concept_ids=['c1'] if ids is None else ids, kind=kind, quote=quote, **extra)


class FakeModel:
    def __init__(self, by_page, actions=None):
        self.by_page, self.actions = by_page, actions or {}
        self.calls = []
        self.target_titles = {}
        self.fail_pages = set()
        self.links_supported = True
        self.allow_missing_in_stream = False

    def __call__(self, **kw):
        assert kw['model'] == MODEL
        payload = json.loads(kw['messages'][-1]['content'].split('\nRéponse précédente rejetée : ')[0])
        name = kw['response_model'].__name__
        self.calls.append((name, payload))
        if name == 'CoverageResponse':
            number = payload['source']['page']
            if number in self.fail_pages:
                raise ConnectionError('Test de panne du modèle configuré')
            lines = payload['source']['lines']
            source = ''.join(line['text'] for line in lines)
            selected = []
            for f in self.by_page[number]:
                # Les fixtures historiques indiquent les passages attendus ; le faux
                # modèle les sélectionne par numéro comme le protocole de production.
                match = re.search(r'\s+'.join(re.escape(w) for w in f['quote'].split()), source)
                if match is None and self.allow_missing_in_stream:
                    continue
                offsets = []; start = 0
                for line in lines:
                    offsets.append((start, start + len(line['text'])))
                    start += len(line['text'])
                first = next((i+1 for i, (_, end) in enumerate(offsets) if match and end > match.start()), 99999)
                last = next((i+1 for i, (_, end) in enumerate(offsets) if match and end >= match.end()), 99999)
                selected.append({k: v for k, v in f.items() if k not in {'quote', 'source_anchor', 'concept_type'}} |
                    dict(start_line=first, end_line=last, anchor_line=first if not f['concept_ids'] else None))
            return dict(status='complete', reason='Lecture du passage achevée.', facts=selected)
        if name == 'SourceJudgment':
            if 'excluded' in payload:
                return dict(supported=False, reason='Le point exclu reste utile à la notion.')
            return dict(supported=payload['action'] == 'mention', reason='Fixture de pertinence : simple mention sans développement.')
        if name == 'TeachingReview':
            quotes = [p['quote'] for p in payload['points']]
            if all(pedagogy.code_only(dict(quote=q)) for q in quotes):
                disposition = 'supporting'
            elif all(len(q.split()) <= 3 and not q.strip().endswith('.') for q in quotes):
                disposition = 'name_only'
            else:
                disposition = 'developed'
            return dict(disposition=disposition, reason='Lecture indépendante du contenu de la fixture.')
        if name == 'EvidenceRecovery':
            return dict(selections=[], reason='Pas de passage complémentaire dans cette fixture.')
        if name == 'EvidenceAssignments':
            return dict(items=[dict(point_id=p['point_id'], verdict='about_this_notion',
                reason='Usage technique confirmé dans cette fixture.') for p in payload['candidates']])
        if name == 'ReferencedAdequacy':
            previous = payload['previous_assessment']
            gaps = ([dict(description='Développement annoncé absent de la fixture.',
                references=[dict(point_id='p1', start_line=1, end_line=len(payload['points'][0]['lines']))])]
                if previous['disposition'] in {'incomplete', 'unreadable'} else [])
            return dict(disposition=previous['disposition'], reason=previous['reason'], blocking_gaps=gaps)
        if name == 'GapAudit':
            return dict(disposition='incomplete', confirmed_gap_indices=list(range(1,len(payload['proposed_gaps'])+1)),
                reason='Manque réel annoncé dans cette fixture.')
        if name == 'VisualAnchorReview':
            return dict(identified=False, point_ids=[], reason='Aucun ancrage visuel simulé dans cette fixture.')
        if name == 'RelationReview':
            return dict(relation=('same_notion' if self.last_relation == 'duplicate' else 'develops_target') if self.links_supported else 'unrelated',
                reason='Lien contrôlé entre les deux extraits.',
                source_point_ids=[p['point_id'] for p in payload['source']['points']],
                target_point_ids=[p['point_id'] for p in payload['target']['points']])
        c = payload['concept']; points = payload['points']
        action, target = self.actions.get(c['id'], ('standalone', None))
        if name == 'ContentAssessment':
            return dict(disposition={'standalone':'developed','attach':'supporting','merge':'developed',
                'mention':'name_only','uncertain':'incomplete'}[action],
                excluded_points={}, missing_information=[], reason='Décision à partir du développement cité.', concept_type=c['type'])
        if name == 'GroupProposal':
            target_ref = next((v['id'] for v in payload['possible_targets']
                if v['title'] == self.target_titles.get(target, target)), None) if target else None
            self.last_relation = ('duplicate' if action == 'merge' else 'supplement') if target_ref else 'independent'
            return dict(relation=self.last_relation, target_ref=target_ref, reason='Organisation de la fixture.')
        raise AssertionError('Appel de modèle inattendu : ' + name)



class CoverageTests(unittest.TestCase):
    def material(self, inv, pages, fake, repo):
        if isinstance(fake, FakeModel):
            fake.target_titles = {c.concept_id:c.title for c in inv.concepts}
        with patch.object(pedagogy, 'chat_json', side_effect=fake):
            return pedagogy.prepare_material(inv, {'file_hash': SHA, 'pages': pages}, PLAN, repo, model=MODEL)

    def test_whole_document_adds_late_example_and_missing_notion_preserving_original(self):
        c = notion(); inv = inventory(c); original = inv.model_dump()
        explanation = c.evidence[0].excerpt
        example = 'Une cellule musculaire se contracte.'
        missing = 'La membrane délimite la cellule.'
        pages = [page(1, explanation), page(17, example + '\n' + missing)]
        fake = FakeModel({1: [fact(explanation)], 17: [fact(example, 'example'),
            fact(missing, ids=[], title='membrane')]})
        with TemporaryDirectory() as folder:
            repo = CourseRepository(Path(folder))
            result = self.material(inv, pages, fake, repo)
            self.assertEqual(result.issues, [])
            self.assertEqual(len(result.inventory.concepts), 2)
            cell = result.inventory.concepts[0]
            self.assertEqual(cell.concept_id, c.concept_id)
            self.assertEqual(cell.source_pages, [1, 17])
            self.assertEqual([p.kind for p in cell.learning_points], ['explanation', 'example'])
            self.assertEqual(inv.model_dump(), original)
            count = len(fake.calls)
            self.assertEqual(self.material(inv, pages, fake, repo), result)
            self.assertEqual(len(fake.calls), count)

    def test_changed_extraction_invalidates_coverage_even_with_same_pdf_hash(self):
        c = notion(); fake = FakeModel({1: [fact(c.evidence[0].excerpt)]})
        with TemporaryDirectory() as folder:
            repo = CourseRepository(Path(folder))
            first = self.material(inventory(c), [page(1, c.evidence[0].excerpt)], fake, repo)
            second = self.material(inventory(c), [page(1, c.evidence[0].excerpt + '\nUne suite.')], fake, repo)
            self.assertNotEqual(first.quality_hash, second.quality_hash)
            self.assertEqual(len([n for n, _ in fake.calls if n == 'CoverageResponse']), 2)
            self.assertTrue(list(repo.paths('cours-test').root.glob('_backups/pedagogy.*.json')))

    def test_failure_is_bounded_and_resume_reads_only_missing_page(self):
        c = notion(); extra = 'La cellule contient une membrane.'
        pages = [page(1, c.evidence[0].excerpt), page(2, extra)]
        fake = FakeModel({1: [fact(c.evidence[0].excerpt)], 2: [fact(extra)]})
        fake.fail_pages = {2}
        with TemporaryDirectory() as folder:
            repo = CourseRepository(Path(folder))
            first = self.material(inventory(c), pages, fake, repo)
            self.assertEqual(first.issues[0]['status'], 'review_pending')
            self.assertEqual(sum(n == 'CoverageResponse' for n, _ in fake.calls), 3)  # page 1 + deux essais page 2
            fake.fail_pages.clear(); fake.calls.clear()
            resumed = self.material(inventory(c), pages, fake, repo)
            self.assertFalse(resumed.issues)
            reads = [p['source']['page'] for n, p in fake.calls if n == 'CoverageResponse']
            self.assertEqual(reads, [2])

    def test_unsupported_quote_does_not_enter_the_cache(self):
        c = notion(); fake = FakeModel({1: [fact('La cellule est invincible.')]})
        with TemporaryDirectory() as folder:
            repo = CourseRepository(Path(folder))
            result = self.material(inventory(c), [page(1, c.evidence[0].excerpt)], fake, repo)
            self.assertTrue(result.issues)
            state = json.loads((repo.paths('cours-test').root / 'pedagogy.json').read_text())
            self.assertEqual(state['chunks'], {})
            self.assertEqual(len(fake.calls), 2)

    def test_source_chunks_keep_the_end_of_long_pages_and_raw_stream(self):
        text = 'Du contenu pédagogique. ' * 1200 + 'DERNIERE_INFORMATION'
        chunks = pedagogy.source_chunks({'pages': [page(1, text), {**page(2, 'native'), 'evidence_text': 'OCR'}]})
        self.assertTrue(any('DERNIERE_INFORMATION' in c['text'] for c in chunks))
        self.assertEqual({c['text'] for c in chunks if c['page'] == 2}, {'native', 'OCR'})

    def test_mention_has_trace_but_developed_information_cannot_be_discarded(self):
        c = notion(text='Cellule'); fake = FakeModel({1: [fact('Cellule', 'mention')]}, {'cellule': ('mention', None)})
        with TemporaryDirectory() as folder:
            result = self.material(inventory(c), [page(1, 'Cellule')], fake, CourseRepository(Path(folder)))
            self.assertEqual(result.inventory.concepts[0].relevance, 'mention_only')
            self.assertTrue(result.inventory.concepts[0].relevance_reason)
            self.assertFalse(result.issues)
        fake.by_page[1] = [fact('La cellule est une unité du vivant.')]
        with TemporaryDirectory() as folder:
            result = self.material(inventory(c), [page(1, fake.by_page[1][0]['quote'])], fake, CourseRepository(Path(folder)))
            self.assertFalse(result.issues)
            self.assertFalse(any(c.relevance == 'mention_only' for c in result.inventory.concepts))

    def test_example_alone_requires_attachment_or_an_explicit_problem(self):
        c = notion('commande', 'Commande', 'out = lire(fichier)', kind='command')
        fake = FakeModel({1: [fact(c.evidence[0].excerpt, 'example', title='Commande')]})
        with TemporaryDirectory() as folder:
            result = self.material(inventory(c), [page(1, c.evidence[0].excerpt)], fake, CourseRepository(Path(folder)))
            self.assertTrue(result.issues)
            self.assertEqual(result.issues[0]['status'], 'card_incomplete')

    def test_merge_across_pages_keeps_provenance_and_stable_target_id(self):
        a = notion('a', 'Réforme', 'La réforme modifie les institutions.')
        b = notion('b', 'Réforme institutionnelle', 'Cette réforme change les institutions.', page=4)
        fake = FakeModel({1: [fact(a.evidence[0].excerpt, ids=['c1'], title=a.title)],
                          4: [fact(b.evidence[0].excerpt, ids=['c2'], title=b.title)]}, {'b': ('merge', 'a')})
        with TemporaryDirectory() as folder:
            result = self.material(inventory(a, b), [page(1, a.evidence[0].excerpt), page(4, b.evidence[0].excerpt)], fake, CourseRepository(Path(folder)))
            self.assertFalse(result.issues)
            self.assertEqual([c.concept_id for c in result.inventory.concepts], ['a'])
            self.assertEqual(result.inventory.concepts[0].source_pages, [1, 4])
            self.assertEqual(result.relations[0]['concept_id'], 'b')
            self.assertTrue(result.relations[0]['grounding']['target_point_ids'])

    def test_unrelated_attachment_and_cycles_are_not_published(self):
        a = notion('a', text='La cellule est une unité du vivant.')
        b = notion('b', 'Noyau', 'Le noyau contient du matériel génétique.')
        text = a.evidence[0].excerpt + '\n' + b.evidence[0].excerpt
        fake = FakeModel({1: [fact(a.evidence[0].excerpt, ids=['c1']), fact(b.evidence[0].excerpt, ids=['c2'], title='Noyau')]}, {'b': ('attach', 'a')})
        fake.links_supported = False
        with TemporaryDirectory() as folder:
            result = self.material(inventory(a, b), [page(1, text)], fake, CourseRepository(Path(folder)))
            self.assertFalse(result.relations)
            self.assertTrue(any('Rattachement' in i['reason'] for i in result.issues))
        fake.links_supported = True; fake.actions['a'] = ('merge', 'b')
        with TemporaryDirectory() as folder:
            result = self.material(inventory(a, b), [page(1, text)], fake, CourseRepository(Path(folder)))
            self.assertEqual([c.concept_id for c in result.inventory.concepts], ['a'])
            self.assertFalse(result.issues)
            self.assertEqual([(r['concept_id'], r['target_id']) for r in result.relations], [('b', 'a')])

    def test_missing_definition_or_example_cannot_be_excluded_to_shorten_card(self):
        c = notion(); example = 'Une cellule musculaire se contracte.'
        fake = FakeModel({1: [fact(c.evidence[0].excerpt), fact(example, 'example')]})
        def omit(**kw):
            result = fake(**kw)
            if kw['response_model'].__name__ == 'ContentAssessment':
                result['excluded_points']['p2'] = 'Pour faire plus court.'
            return result
        with TemporaryDirectory() as folder:
            result = self.material(inventory(c), [page(1, c.evidence[0].excerpt + '\n' + example)], omit, CourseRepository(Path(folder)))
            self.assertTrue(any('omise : example' in i['reason'] for i in result.issues))


class ValidationTests(unittest.TestCase):
    def specimen(self, kinds=('explanation', 'example')):
        texts = ['La cellule est une unité du vivant.', 'Une cellule musculaire se contracte.']
        c = notion().model_copy(update={'learning_points': [LearningPoint(point_id=str(i), kind=k, page=1, quote=t)
            for i, (k, t) in enumerate(zip(kinds, texts))], 'evidence': [ConceptEvidence(page=1, excerpt=t) for t in texts]})
        c = Concept.model_validate(c.model_dump())
        card = StudyCard(card_id='stable-card', concept_id=c.concept_id, title=c.title, concept_type=c.type,
            primary_part_id='p1', source_pages=[1], sections=[dict(key='definition', title='Définition', content=texts[0])])
        return c, card

    def test_truthful_but_incomplete_card_is_rejected(self):
        c, card = self.specimen()
        verdict = dict(concept_id=c.concept_id, supported=True, issues=[], complete=False,
                       covered_point_ids=['0'], missing_point_ids=['1'])
        with patch.object(card_grounding, 'chat_json', return_value={'cards': [verdict]}):
            result = card_grounding.audit_cards({c.concept_id: card}, [c], model=MODEL)
        self.assertIn('Fiche incomplète', result[c.concept_id][0])
        self.assertIn('musculaire', result[c.concept_id][0])

    def test_audit_cannot_claim_complete_without_accounting_for_all_points(self):
        c, card = self.specimen()
        verdict = dict(concept_id=c.concept_id, supported=True, issues=[], complete=True,
                       covered_point_ids=['0'], missing_point_ids=[])
        with patch.object(card_grounding, 'chat_json', return_value={'cards': [verdict]}), self.assertRaisesRegex(ValueError, 'couverture incohérente'):
            card_grounding.audit_cards({c.concept_id: card}, [c], model=MODEL)

    def test_alternatives_are_not_steps_even_when_model_accepts_them(self):
        c, card = self.specimen(('explanation', 'alternatives'))
        card.sections[0].content = '1. Choisir A.\n2. Choisir B.'
        verdict = dict(concept_id=c.concept_id, supported=True, issues=[], complete=True,
                       covered_point_ids=['0', '1'], missing_point_ids=[])
        with patch.object(card_grounding, 'chat_json', return_value={'cards': [verdict]}):
            result = card_grounding.audit_cards({c.concept_id: card}, [c], model=MODEL)
        self.assertTrue(any('alternatives' in p for p in result[c.concept_id]))

    def test_fraction_sign_index_and_coefficient_changes_are_rejected(self):
        source = r'\[q_k = \frac{u_k - i v_k}{2}\]'
        self.assertTrue(cards._math_is_supported(source, source)[0])
        for wrong in [r'\[q_k = u_k - i v_k\]', r'\[q_k = \frac{u_k + i v_k}{2}\]',
                      r'\[q_k = \frac{u_k - i v_k}{3}\]', r'\[q_n = \frac{u_k - i v_k}{2}\]']:
            self.assertFalse(cards._math_is_supported(wrong, source)[0], wrong)
        self.assertEqual(pedagogy.literal_quote('x = 1 / 2', 'x  = 1 / 2'), 'x  = 1 / 2')
        with self.assertRaises(ValueError):
            pedagogy.literal_quote('x = 1', 'x = 2')

    def test_omission_feedback_repairs_only_failed_card(self):
        c, _ = self.specimen()
        pages = [page(1, '\n'.join(e.excerpt for e in c.evidence))]
        thin = {'cards': [{'concept_id': c.concept_id, 'sections': [{'title': 'Définition', 'content': c.evidence[0].excerpt}]}]}
        full = {'cards': [{'concept_id': c.concept_id, 'sections': [
            {'title': 'Définition', 'content': c.evidence[0].excerpt}, {'title': 'Exemple', 'content': c.evidence[1].excerpt}]}]}
        verdict = dict(concept_id=c.concept_id, supported=True, issues=[], complete=False, covered_point_ids=['0'], missing_point_ids=['1'])
        success = dict(verdict, complete=True, covered_point_ids=['0','1'], missing_point_ids=[])
        with patch.object(cards, 'chat_json', side_effect=[thin, full]) as generate, patch.object(card_grounding, 'chat_json', side_effect=[{'cards':[verdict]}, {'cards':[success]}]):
            result = cards._generate_batch({'number':'1', 'title':'Cellule'}, pages, [c], model=MODEL)
        self.assertEqual(len(result[0].sections), 2)
        self.assertIn('musculaire', generate.call_args.kwargs['messages'][-1]['content'])
        self.assertEqual(generate.call_count, 2)

    def test_ambiguous_formula_uses_original_region_and_rejects_forged_bbox(self):
        from src.courses.source_recovery import illustrations_supported
        c = notion('formule', 'Relation', 'Relation\nqk = uk - i vk\n2', kind='formula')
        text = c.evidence[0].excerpt
        p = page(1, text)
        p['source_units'] = [{'heading':'Relation', 'y':50, 'native_text':text,
            'native_lines':[{'text':text, 'bbox':[40,50,350,150]}]}, {'heading':'Autre', 'y':200, 'native_text':'Autre'}]
        f = fact(text, 'formula', title='Relation'); f['concept_type']='formula'
        fake = FakeModel({1:[f]})
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=fake):
            result = pedagogy.prepare_material(inventory(c), {'file_hash':SHA,'pages':[p]}, PLAN, CourseRepository(Path(folder)), model=MODEL)
        self.assertFalse(result.issues)
        c = result.inventory.concepts[0]
        self.assertEqual(c.card_role, 'visual')
        self.assertEqual(c.illustrations[0].bbox, (0,44,500,200))
        self.assertTrue(illustrations_supported(c, [p]))
        forged = c.model_copy(deep=True); forged.illustrations[0].bbox=(0,44,500,140)
        self.assertFalse(illustrations_supported(forged, [p]))
        with patch.object(cards, 'chat_json') as model:
            result = cards._generate_batch({'number':'1'}, [p], [c], model=MODEL)
        model.assert_not_called()
        self.assertEqual(result[0].illustrations, c.illustrations)
        self.assertNotIn('qk =', result[0].sections[0].content)

    def test_legacy_cache_is_review_pending_not_valid_or_deleted(self):
        _, card = self.specimen()
        old = CardCollection(course_id='cours-test', file_hash=SHA, inventory_hash=SHA, model=MODEL,
                             schema_version=1, cards=[card], parts=[dict(part_id='p1', part_number='1', status='complete', cards_generated=1)])
        view = publication_view(old)
        self.assertEqual(view.cards, [])
        self.assertEqual(view.failures[0].status, 'review_pending')
        self.assertEqual(view.parts[0].status, 'partial')
        self.assertEqual(old.cards, [card])

    def test_title_code_and_formulas_render_safely(self):
        data = dict(title='Propriété taille', sections=[dict(key='example', title='Exemple du cours', content='```\ntaille: 3;\n```')])
        rendered = present_card(data)
        self.assertIn('<code>taille</code>', rendered['title_html'])
        self.assertIn('<pre><code>taille: 3;</code></pre>', rendered['content_html'])


class MigrationTests(unittest.TestCase):
    def test_interruption_before_first_card_keeps_all_parts_pending(self):
        c = notion(); inv=inventory(c)
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory(inv.course_id,inv.model_dump(mode='json'))
            plan={'parts':PLAN['parts']+[{'id':'p2','number':'2','page_start':21,'page_end':22}]}
            inv.parts.append(inv.parts[0].model_copy(update={'part_id':'p2','part_number':'2','concepts_found':0}))
            repo.save_inventory(inv.course_id,inv.model_dump(mode='json'))
            for name,value in [('CourseRepository',repo),('load_course',dict(file_hash=SHA,source_filename='cours.pdf')),
                               ('load_course_plan',plan),('extract_document',dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt)]))]:
                stack.enter_context(patch.object(cards,name,return_value=value))
            stack.enter_context(patch.object(cards,'prepare_material',return_value=pedagogy.Material(inv,'test')))
            stack.enter_context(patch.object(cards,'_generate_batch',side_effect=KeyboardInterrupt()))
            with self.assertRaises(KeyboardInterrupt):
                cards.build_cards(inv.course_id,model=MODEL)
            saved=CardCollection.model_validate(repo.load_cards(inv.course_id))
            self.assertEqual(len(saved.parts),2)
            self.assertTrue(all(p.status!='complete' for p in saved.parts))
            self.assertEqual(cards.cards_summary(saved)['complete_parts'],0)

    def test_old_valid_card_is_reaudited_backed_up_and_then_cached(self):
        c = notion(); inv = inventory(c); text=c.evidence[0].excerpt
        fake = FakeModel({1:[fact(text)]})
        card = StudyCard(card_id='ancien-identifiant-a-preserver', concept_id=c.concept_id, title=c.title,
            concept_type=c.type, primary_part_id='p1', source_pages=[1],
            sections=[dict(key='definition', title='Définition', content=text)])
        old = CardCollection(course_id=inv.course_id, file_hash=SHA, inventory_hash=SHA,
                             model=MODEL, schema_version=4, cards=[card])
        def audit(**kw):
            data=json.loads(kw['messages'][-1]['content'])
            return {'cards':[dict(concept_id=v['concept_id'],supported=True,issues=[],complete=True,
                covered_point_ids=[p['point_id'] for p in v['required_points']],missing_point_ids=[]) for v in data]}
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory(inv.course_id,inv.model_dump(mode='json'))
            file=repo.save_cards(inv.course_id,old.model_dump(mode='json'));original=file.read_bytes()
            for name,value in [('CourseRepository',repo),('load_course',dict(course_id=inv.course_id,file_hash=SHA,source_filename='cours.pdf')),
                               ('load_course_plan',PLAN),('extract_document',dict(file_hash=SHA,pages=[page(1,text)]))]:
                stack.enter_context(patch.object(cards,name,return_value=value))
            stack.enter_context(patch.object(pedagogy,'chat_json',side_effect=fake))
            check=stack.enter_context(patch.object(card_grounding,'chat_json',side_effect=audit))
            generate=stack.enter_context(patch.object(cards,'chat_json'))
            first=cards.build_cards(inv.course_id,model=MODEL)
            self.assertEqual(first.cards[0].card_id,card.card_id)
            self.assertFalse(first.unreviewed_cards)
            self.assertEqual(first.quality_version,pedagogy.QUALITY_VERSION)
            self.assertTrue(any(p.read_bytes()==original for p in file.parent.glob('_backups/cards*.json')))
            check.assert_called_once();generate.assert_not_called()
            check.reset_mock();n=len(fake.calls)
            self.assertEqual(cards.build_cards(inv.course_id,model=MODEL), first)
            check.assert_not_called();self.assertEqual(len(fake.calls),n)

    def test_failed_review_preserves_previous_cards_as_unreviewed_drafts(self):
        c = notion(); inv=inventory(c); fake=FakeModel({1:[]});fake.fail_pages={1}
        old_card=StudyCard(card_id='card-keep',concept_id=c.concept_id,title=c.title,concept_type=c.type,
            primary_part_id='p1',source_pages=[1],sections=[dict(key='d',title='Définition',content=c.evidence[0].excerpt)])
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo=CourseRepository(Path(folder));repo.save_inventory(inv.course_id,inv.model_dump(mode='json'))
            old=CardCollection(course_id=inv.course_id,file_hash=SHA,inventory_hash=SHA,model=MODEL,cards=[old_card])
            repo.save_cards(inv.course_id,old.model_dump(mode='json'))
            for name,value in [('CourseRepository',repo),('load_course',dict(file_hash=SHA,source_filename='cours.pdf')),
                               ('load_course_plan',PLAN),('extract_document',dict(file_hash=SHA,pages=[page(1,c.evidence[0].excerpt)]))]:
                stack.enter_context(patch.object(cards,name,return_value=value))
            stack.enter_context(patch.object(pedagogy,'chat_json',side_effect=fake))
            result=cards.build_cards(inv.course_id,model=MODEL)
            self.assertEqual(result.cards,[])
            self.assertEqual(result.unreviewed_cards,[old_card])
            self.assertEqual(result.parts[0].status,'partial')
            self.assertGreater(cards.cards_summary(result)['review_issues'],0)

    def test_process_all_continues_after_one_failed_course(self):
        import manage
        from src.courses import service, pipeline
        with patch.object(service,'list_courses',return_value=[dict(course_id='one',title='Biologie'),dict(course_id='two',title='Physique')]), patch.object(pipeline,'process_course',side_effect=[ConnectionError('arrêt'),dict(status='ready')]) as run:
            self.assertEqual(manage.main(['process','--all','--model',MODEL]),2)
        self.assertEqual([c.args[0] for c in run.call_args_list],['one','two'])


if __name__ == '__main__':
    unittest.main()
