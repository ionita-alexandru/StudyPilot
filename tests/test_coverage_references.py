"""Régression du journal utilisateur v14 : protocole source, panne et reprise.

Réponses Ollama simulées (y compris invalides), validation et stockage réels.
"""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from pydantic import ValidationError

from src.courses import cards, pedagogy
from src.models.card import CardCollection, StudyCard
from src.storage.course_repository import CourseRepository
from test_pedagogy import FakeModel, MODEL, SHA, PLAN, fact, inventory, notion, page


class ReferenceContractTests(unittest.TestCase):
    def test_ranges_copy_original_characters_without_model_transcription(self):
        text = '• Propriété\r\n  x: "a  b";\r\n  cₙ = (aₙ − i bₙ)/2\nSuite\n'
        lines = pedagogy.numbered_lines(text)
        item = pedagogy.Fact(title='Expression', concept_ids=['c1'], kind='formula', start_line=2, end_line=3)
        self.assertEqual(pedagogy.selected_quote(item, lines), '  x: "a  b";\r\n  cₙ = (aₙ − i bₙ)/2\n')
        self.assertEqual(''.join(l['text'] for l in lines), text)
        long = 'texte ' * 900 + 'FIN'
        self.assertEqual(''.join(l['text'] for l in pedagogy.numbered_lines(long)), long)

    def test_invalid_ranges_and_injected_quote_are_rejected(self):
        lines = pedagogy.numbered_lines('Source réelle\n')
        valid = dict(title='Notion', kind='explanation', start_line=1, end_line=1)
        for extra in [dict(start_line=0), dict(start_line='1'), dict(start_line=True),
                      dict(quote='Un énoncé inventé'), dict(concept_type='illustration'), dict(kind='method')]:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                pedagogy.Fact(**(valid | extra))
        for extra in [dict(end_line=2), dict(start_line=2, end_line=1)]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                pedagogy.selected_quote(pedagogy.Fact(**(valid | extra)), lines)

    def test_coverage_contract_has_no_quote_or_competing_type_enum(self):
        fields = pedagogy.Fact.model_json_schema()['properties']
        self.assertNotIn('quote', fields)
        self.assertNotIn('source_anchor', fields)
        self.assertNotIn('concept_type', fields)
        self.assertIn('illustration', fields['kind']['enum'])
        self.assertNotIn('method', fields['kind']['enum'])

    def test_malformed_json_retries_with_feedback_then_copies_source(self):
        c = notion(); fake = FakeModel({1: [fact(c.evidence[0].excerpt)]}); attempts = []
        def reply(**kw):
            if kw['response_model'] is pedagogy.CoverageResponse:
                attempts.append(kw)
                if len(attempts) == 1:
                    return pedagogy.CoverageResponse.model_validate_json('{"status":"complete","facts":[')
            return fake(**kw)
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=reply):
            result = pedagogy.prepare_material(inventory(c), dict(file_hash=SHA, pages=[page(1, c.evidence[0].excerpt)]),
                                              PLAN, CourseRepository(Path(folder)), model=MODEL)
        self.assertFalse(result.issues)
        self.assertEqual(len(attempts), 2)
        self.assertIn('Réponse précédente rejetée', attempts[1]['messages'][-1]['content'])
        self.assertEqual(result.inventory.concepts[0].learning_points[0].quote, c.evidence[0].excerpt)
        self.assertTrue(all(a['model'] == MODEL for a in attempts))

    def test_permanent_schema_failure_keeps_local_diagnostic_after_two_attempts(self):
        c = notion(); calls = []
        def invalid(**kw):
            calls.append(kw)
            return dict(status='complete', facts=[dict(title='Notion', kind='method', start_line=1, end_line=1)])
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=invalid):
            repo = CourseRepository(Path(folder))
            result = pedagogy.prepare_material(inventory(c), dict(file_hash=SHA, pages=[page(1, c.evidence[0].excerpt)]), PLAN, repo, model=MODEL)
            stored = json.loads((repo.paths('cours-test').root / 'pedagogy.json').read_text())
        self.assertEqual(len(calls), 2)
        self.assertFalse(result.inventory.concepts)
        self.assertEqual(result.issues[0]['page'], 1)
        self.assertEqual(result.issues[0]['chunk_id'], 'p1-s0-0')
        self.assertIn('method', result.issues[0]['reason'])
        self.assertEqual(stored['chunks'], {})

    def test_old_coverage_cache_is_backed_up_and_reselected(self):
        c = notion(); fake = FakeModel({1: [fact(c.evidence[0].excerpt)]})
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=fake):
            repo = CourseRepository(Path(folder)); target = repo.paths('cours-test').root / 'pedagogy.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            before = json.dumps(dict(version=14, fingerprint='v14-old-contract', chunks={'p1-s0-0': []}, decisions={}))
            target.write_text(before)
            result = pedagogy.prepare_material(inventory(c), dict(file_hash=SHA, pages=[page(1, c.evidence[0].excerpt)]), PLAN, repo, model=MODEL)
            self.assertTrue(any(p.read_text() == before for p in target.parent.glob('_backups/pedagogy*.json')))
            self.assertEqual(json.loads(target.read_text())['coverage_protocol'], 2)
        self.assertFalse(result.issues)
        self.assertEqual(sum(n == 'CoverageResponse' for n, _ in fake.calls), 1)

    def test_bad_anchor_metadata_cannot_pull_in_neighboring_proof(self):
        c = notion(); fake = FakeModel({1: [fact(c.evidence[0].excerpt, ids=[], title='Nouvelle notion')]})
        def misplaced(**kw):
            response = fake(**kw)
            if kw['response_model'] is pedagogy.CoverageResponse:
                response['facts'][0]['anchor_line'] = 2
            return response
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=misplaced):
            result = pedagogy.prepare_material(inventory(c), dict(file_hash=SHA,
                pages=[page(1, c.evidence[0].excerpt + '\nAutre sujet')]), PLAN, CourseRepository(Path(folder)), model=MODEL)
        discovered = next(v for v in result.inventory.concepts if v.title == 'Nouvelle notion')
        self.assertEqual(discovered.source_anchor, c.evidence[0].excerpt)
        self.assertNotIn('Autre sujet', discovered.evidence[0].excerpt)
        self.assertFalse(any(i.get('chunk_id') for i in result.issues))

    def test_discovered_identity_survives_protocol_migration(self):
        c = notion(); inv = inventory(c); text = c.evidence[0].excerpt
        prior = notion('discovered-stable-id', 'Membrane', 'La membrane délimite la cellule.', page=2)
        fake = FakeModel({1: [fact(text)], 2: [fact(prior.evidence[0].excerpt, ids=[], title='Membrane')]})
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=fake):
            repo = CourseRepository(Path(folder)); target = repo.paths(inv.course_id).root / 'pedagogy.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dict(version=14, fingerprint='ancien-protocole', chunks={}, decisions={},
                effective_inventory=inventory(c, prior).model_dump(mode='json'))))
            result = pedagogy.prepare_material(inv, dict(file_hash=SHA, pages=[page(1, text), page(2, prior.evidence[0].excerpt)]), PLAN, repo, model=MODEL)
            self.assertFalse(result.issues)
            self.assertEqual(next(c.concept_id for c in result.inventory.concepts if c.title == 'Membrane'), prior.concept_id)

    def test_different_new_notions_on_same_line_do_not_share_identity(self):
        text = 'La cellule est une unité. La membrane est une limite.'
        fake = FakeModel({1: [fact(text, ids=[], title='Cellule'), fact(text, ids=[], title='Membrane')]})
        with TemporaryDirectory() as folder, patch.object(pedagogy, 'chat_json', side_effect=fake):
            result = pedagogy.prepare_material(inventory(), dict(file_hash=SHA, pages=[page(1, text)]), PLAN, CourseRepository(Path(folder)), model=MODEL)
        self.assertFalse(result.issues)
        self.assertEqual(len({c.concept_id for c in result.inventory.concepts}), 2)


class PartialProgressTests(unittest.TestCase):
    def test_verified_card_publishes_while_other_page_is_pending_then_resumes(self):
        first = notion(); second = notion('membrane', 'Membrane', 'La membrane délimite la cellule.', page=2)
        inv = inventory(first, second)
        fake = FakeModel({1: [fact(first.evidence[0].excerpt)],
                          2: [fact(second.evidence[0].excerpt, ids=['c2'], title='Membrane')]})
        fake.fail_pages = {2}
        old_card = StudyCard(card_id='ancien-identifiant', concept_id=second.concept_id, title=second.title,
                            concept_type=second.type, primary_part_id='p1', source_pages=[2],
                            sections=[dict(key='d', title='Définition', content=second.evidence[0].excerpt)])
        generated = []
        def generate(part, pages, concepts, **kw):
            generated.extend(c.concept_id for c in concepts)
            return [StudyCard(card_id='card-' + c.concept_id, concept_id=c.concept_id, title=c.title,
                concept_type=c.type, primary_part_id=c.primary_part_id, source_pages=c.source_pages,
                sections=[dict(key='definition', title='Définition', content=c.evidence[0].excerpt)]) for c in concepts]
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder)); repo.save_inventory(inv.course_id, inv.model_dump(mode='json'))
            old = CardCollection(course_id=inv.course_id, file_hash=SHA, inventory_hash=SHA, model=MODEL, cards=[old_card])
            repo.save_cards(inv.course_id, old.model_dump(mode='json'))
            for name, value in [('CourseRepository', repo), ('load_course', dict(file_hash=SHA, source_filename='test.pdf')),
                ('load_course_plan', PLAN), ('extract_document', dict(file_hash=SHA, pages=[page(1, first.evidence[0].excerpt), page(2, second.evidence[0].excerpt)]))]:
                stack.enter_context(patch.object(cards, name, return_value=value))
            stack.enter_context(patch.object(pedagogy, 'chat_json', side_effect=fake))
            stack.enter_context(patch.object(cards, '_generate_batch', side_effect=generate))
            stack.enter_context(patch.object(cards, 'audit_cards', return_value={second.concept_id: ['À reconstruire pour ce test']}))
            partial = cards.build_cards(inv.course_id, model=MODEL)
            self.assertEqual([c.concept_id for c in partial.cards], [first.concept_id])
            self.assertEqual(partial.unreviewed_cards, [old_card])
            self.assertEqual(partial.parts[0].status, 'partial')
            self.assertGreater(cards.cards_summary(partial)['review_issues'], 0)
            self.assertEqual(generated, [first.concept_id])
            fake.fail_pages.clear(); fake.calls.clear(); generated.clear()
            resumed = cards.build_cards(inv.course_id, model=MODEL)
            self.assertEqual({c.concept_id for c in resumed.cards}, {first.concept_id, second.concept_id})
            self.assertEqual(next(c.card_id for c in resumed.cards if c.concept_id == second.concept_id), old_card.card_id)
            self.assertEqual(generated, [second.concept_id])
            self.assertEqual([p['source']['page'] for name, p in fake.calls if name == 'CoverageResponse'], [2])
            self.assertFalse(resumed.review_issues)
            self.assertFalse(resumed.unreviewed_cards)
            self.assertEqual(resumed.parts[0].status, 'complete')

    def test_page_issue_blocks_local_concept_but_not_unrelated_concept(self):
        c = notion()
        self.assertTrue(pedagogy.issue_blocks_concept({'page': 1}, c))
        self.assertFalse(pedagogy.issue_blocks_concept({'page': 9}, c))
        self.assertTrue(pedagogy.issue_blocks_concept({'reason': 'Portée inconnue'}, c))
        self.assertTrue(pedagogy.issue_blocks_concept({'concept_id': c.concept_id}, c))

