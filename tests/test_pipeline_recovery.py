"""Régressions du parcours automatique, sans dépendre d'un inventaire utilisateur."""
from contextlib import ExitStack
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import pymupdf

from src.ai import client
from src.config import STUDY_MODEL
from src.courses import cards, inventory, pipeline
from src.courses.card_grounding import source_code_snippets, code_issue
from src.models.card import CardCollection
from src.models.concept import Concept, ConceptInventory
from src.storage.course_repository import CourseRepository
from src import upload_service


def concept(identifier, title, excerpt):
    return Concept(concept_id=identifier, title=title, type='concept', primary_part_id='p1',
                   source_pages=[1], evidence=[{'page': 1, 'excerpt': excerpt}])


def card_for(c, pages):
    raw = [{'concept_id': c.concept_id, 'sections': [{'title': 'Définition', 'content': c.evidence[0].excerpt}]}]
    return cards._validate_cards(raw, [c], pages)[c.concept_id]


class RecoveryTests(TestCase):
    def setUp(self):
        # Ces tests isolent le générateur ; la lecture complète est testée dans test_pedagogy.
        from src.courses.pedagogy import Material
        patcher = patch.object(cards, "prepare_material", side_effect=lambda inventory, *args, **kw: Material(inventory, "test"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_interruption_keeps_previous_batch_and_resumes_only_remaining(self):
        cs = [concept('first', 'Événement', 'Cet événement précède la réforme.'),
              concept('second', 'Réforme', 'La réforme modifie les institutions.')]
        pages = [{'page': 1, 'raw_text': '\n'.join(c.evidence[0].excerpt for c in cs)}]
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder))
            inv = ConceptInventory(course_id='histoire', file_hash='a' * 64, model=STUDY_MODEL,
                concepts=cs, parts=[{'part_id': 'p1', 'part_number': '1', 'status': 'complete',
                                    'concepts_found': 2, 'concepts_added_by_audit': 0}])
            repo.save_inventory('histoire', inv.model_dump(mode='json'))
            for name, value in [('CourseRepository', repo),
                ('load_course', {'course_id': 'histoire', 'file_hash': 'a' * 64, 'source_filename': 'histoire.pdf'}),
                ('load_course_plan', {'parts': [{'id': 'p1', 'number': '1'}]}),
                ('extract_document', {'file_hash': 'a' * 64, 'pages': pages})]:
                stack.enter_context(patch.object(cards, name, return_value=value))
            stack.enter_context(patch.object(cards, '_split_concepts', side_effect=lambda concepts: [[c] for c in concepts]))
            generate = stack.enter_context(patch.object(cards, '_generate_batch', side_effect=[[card_for(cs[0], pages)], KeyboardInterrupt()]))
            with self.assertRaises(KeyboardInterrupt):
                cards.build_cards('histoire')
            saved = CardCollection.model_validate(repo.load_cards('histoire'))
            self.assertEqual([c.concept_id for c in saved.cards], ['first'])
            self.assertEqual(saved.parts[0].status, 'error')
            generate.reset_mock(side_effect=True)
            generate.return_value = [card_for(cs[1], pages)]
            result = cards.build_cards('histoire')
            self.assertEqual([c.concept_id for c in generate.call_args.args[2]], ['second'])
            self.assertEqual(len(result.cards), 2)

    def test_failed_batch_preserves_valid_card_and_resume_requests_only_missing(self):
        good = concept('good', 'Cellule', 'La cellule est une unité du vivant.')
        bad = concept('bad', 'Membrane', 'La membrane délimite la cellule.')
        third = concept('third', 'Noyau', 'Le noyau contient le matériel génétique.')
        concepts = [good, bad, third]
        text = '\n'.join(c.evidence[0].excerpt for c in concepts)
        pages = [{'page': 1, 'raw_text': text, 'analysis_text': text}]
        with TemporaryDirectory() as folder, ExitStack() as stack:
            repo = CourseRepository(Path(folder))
            saved = ConceptInventory(course_id='biologie', file_hash='a' * 64, model=STUDY_MODEL,
                concepts=concepts, parts=[{'part_id': 'p1', 'part_number': '1', 'status': 'complete',
                                        'concepts_found': 3, 'concepts_added_by_audit': 0}])
            path = repo.save_inventory('biologie', saved.model_dump(mode='json'))
            original = path.read_bytes()
            for name, value in [('CourseRepository', repo),
                ('load_course', {'course_id': 'biologie', 'file_hash': 'a' * 64, 'source_filename': 'bio.pdf'}),
                ('load_course_plan', {'parts': [{'id': 'p1', 'number': '1'}]}),
                ('extract_document', {'file_hash': 'a' * 64, 'pages': pages})]:
                stack.enter_context(patch.object(cards, name, return_value=value))
            stack.enter_context(patch.object(cards, '_split_concepts', side_effect=lambda cs: ([cs[:2], cs[2:]] if len(cs) > 2 else [cs]) if cs else []))
            ok_card = card_for(good, pages)
            failure = cards.CardGenerationError('Une fiche rejetée', [ok_card], {'bad': 'Affirmation sans preuve'})
            generate = stack.enter_context(patch.object(cards, '_generate_batch', side_effect=[failure, [card_for(third, pages)]]))
            result = cards.build_cards('biologie')
            self.assertEqual({c.concept_id for c in result.cards}, {'good', 'third'})
            self.assertEqual(result.parts[0].cards_generated, 2)
            self.assertEqual(result.parts[0].status, 'error')
            self.assertEqual(result.failures[0].concept_id, 'bad')
            self.assertEqual(result.failures[0].status, 'generation_error')
            self.assertEqual(path.read_bytes(), original)
            generate.reset_mock(side_effect=True)
            generate.return_value = [card_for(bad, pages)]
            resumed = cards.build_cards('biologie')
            self.assertEqual([c.concept_id for c in generate.call_args.args[2]], ['bad'])
            self.assertEqual(len(resumed.cards), 3)
            self.assertEqual(resumed.failures, [])
            self.assertEqual(resumed.parts[0].status, 'complete')
            generate.reset_mock()
            self.assertEqual(cards.build_cards('biologie'), resumed)
            generate.assert_not_called()

    def test_generate_batch_exposes_valid_cards_when_another_fails_audit(self):
        good = concept('good', 'Cellule', 'La cellule est une unité du vivant.')
        bad = concept('bad', 'Membrane', 'La membrane délimite la cellule.')
        pages = [{'page': 1, 'raw_text': good.evidence[0].excerpt + '\n' + bad.evidence[0].excerpt}]
        def generate(**kwargs):
            return {'cards': [{'concept_id': c.concept_id, 'sections': [{'title': 'Définition', 'content': c.evidence[0].excerpt}]} for c in [good, bad]]}
        def audit(valid, concepts, **kwargs):
            return {key: ['Non soutenu'] if key == 'bad' else [] for key in valid}
        with patch.object(cards, 'chat_json', side_effect=generate), patch.object(cards, 'audit_cards', side_effect=audit):
            with self.assertRaises(cards.CardGenerationError) as caught:
                cards._generate_batch({}, pages, [good, bad], model=STUDY_MODEL)
        self.assertEqual([c.concept_id for c in caught.exception.generated], ['good'])
        self.assertEqual(set(caught.exception.failures), {'bad'})


class SourceReferenceTests(TestCase):
    def test_tag_reference_in_prose_is_supported_by_an_attributed_tag(self):
        for tag, source in [('a', '<a href="page.html" target="_blank">Page</a>'),
                            ('measure:value', '<measure:value unit="m">3</measure:value>')]:
            c = concept('tag', 'Balisage', source)
            for text in [f"Utiliser la balise <{tag}> du cours.", f"L’élément `<{tag}>` apparaît dans cet exemple."]:
                self.assertIsNone(code_issue(text, c))

    def test_tag_reference_does_not_allow_new_tags_attributes_or_code_examples(self):
        c = concept('tag', 'Balisage', '<a href="page.html" target="_blank">Page</a>')
        for text in ['Utiliser la balise <article>.', 'Utiliser <A> dans la page.',
                     'Utiliser <a href="autre.html"> dans la page.',
                     '```html\n<a>\n```', '<a>Texte du lien</a>',
                     'Utiliser la balise <a>.\n```html\n<a>\n```',
                     'Utiliser la balise <a>.\n<a>']:
            self.assertIsNotNone(code_issue(text, c), text)
        no_markup = concept('tag', 'Lien', 'Use an anchor element to contain an image element.')
        self.assertIsNotNone(code_issue('Utiliser la balise <a>.', no_markup))

    def test_tag_reference_passes_to_semantic_audit(self):
        c = concept('tag', 'Ouvrir un lien', '<a href="page.html" target="_blank">Page</a>')
        # Le titre de la source évite le chemin de citation automatique afin de
        # reproduire une phrase générée contenant le nom de la balise.
        c.evidence[0].excerpt = 'Exemple de lien\n' + c.evidence[0].excerpt
        pages = [{'page': 1, 'raw_text': c.evidence[0].excerpt}]
        raw = {'cards': [{'concept_id': 'tag', 'sections': [{'title': 'Méthode',
            'content': 'Utiliser la balise <a> avec l’attribut target="_blank".'}]}]}
        with patch.object(cards, 'chat_json', return_value=raw), \
             patch.object(cards, 'audit_cards', return_value={'tag': []}) as audit:
            result = cards._generate_batch({}, pages, [c], model=STUDY_MODEL)
        self.assertEqual(len(result), 1)
        audit.assert_called_once()

    def test_redundant_literal_content_is_accepted_without_allowing_modification(self):
        c = concept('code', 'Programme', 'print("Bonjour")')
        pages = [{'page': 1, 'raw_text': c.evidence[0].excerpt}]
        ref = next(iter(source_code_snippets(c)))
        for content in ['print("Bonjour")', '```python\nprint("Bonjour")\n```']:
            raw = [{'concept_id': 'code', 'sections': [{'title': 'Exemple', 'source_ref': ref, 'content': content}]}]
            self.assertIn('code', cards._validate_cards(raw, [c], pages))
        for content in ['print("Autre")', 'print("Bonjour");', 'Ce programme affiche Bonjour.']:
            raw = [{'concept_id': 'code', 'sections': [{'title': 'Exemple', 'source_ref': ref, 'content': content}]}]
            self.assertEqual(cards._validate_cards(raw, [c], pages), {})

    def test_other_concept_pages_do_not_change_the_preflight_diagnosis(self):
        first = concept('first', 'Types de cellules', 'Neurone\nCellule gliale')
        second = concept('second', 'Cellule gliale', 'La cellule gliale accompagne les neurones.')
        second.source_pages = [2]
        second.evidence[0].page = 2
        pages = [
            {'page': 1, 'raw_text': first.evidence[0].excerpt, 'headings': ['Types de cellules']},
            {'page': 2, 'raw_text': second.evidence[0].excerpt, 'headings': ['Cellule gliale']},
        ]
        self.assertIsNone(inventory.concept_evidence_issue(first, [pages[0]]))
        raw = {'cards': [
            {'concept_id': 'first', 'sections': [{'title': 'Types cités', 'content': 'Le cours cite le neurone et la cellule gliale.'}]},
            {'concept_id': 'second', 'sections': [{'title': 'Définition', 'content': second.evidence[0].excerpt}]},
        ]}
        with patch.object(cards, 'chat_json', return_value=raw), patch.object(cards, 'audit_cards', return_value={}):
            result = cards._generate_batch({}, pages, [first, second], model=STUDY_MODEL)
        self.assertEqual(len(result), 2)

    def test_schema_error_is_sent_to_next_attempt(self):
        c = concept('cell', 'Cellule', 'La cellule est une unité du vivant.')
        pages = [{'page': 1, 'raw_text': c.evidence[0].excerpt}]
        raw = {'cards': [{'concept_id': 'cell', 'sections': [{'title': 'Définition', 'content': c.evidence[0].excerpt}]}]}
        with patch.object(cards, 'chat_json', side_effect=[ValueError('sections: maximum 8 éléments, reçu 9'), raw]) as generate, \
             patch.object(cards, 'audit_cards', return_value={}):
            result = cards._generate_batch({}, pages, [c], model=STUDY_MODEL)
        self.assertEqual(len(result), 1)
        prompt = generate.call_args.kwargs['messages'][-1]['content']
        self.assertIn('maximum 8 éléments, reçu 9', prompt)
        self.assertIn('source_ref valide avec content vide', prompt)

    def test_source_reference_inserts_exact_code_and_rejects_foreign_reference(self):
        c = concept('code', 'Exemple de programme', 'print("Bonjour")')
        pages = [{'page': 1, 'raw_text': c.evidence[0].excerpt}]
        catalog = source_code_snippets(c)
        ref = next(iter(catalog))
        raw = [{'concept_id': c.concept_id, 'sections': [{'title': 'Exemple du cours', 'source_ref': ref, 'content': ''}]}]
        valid = cards._validate_cards(raw, [c], pages)
        self.assertIn('print("Bonjour")', valid['code'].sections[0].content)
        for invalid in [{'source_ref': 'code-999', 'content': ''}, {'source_ref': ref, 'content': 'print("Inventé")'}]:
            raw[0]['sections'][0].update(invalid)
            self.assertEqual(cards._validate_cards(raw, [c], pages), {})

    def test_literal_code_uses_same_model_audit_without_rewriting(self):
        c = concept('code', 'Programme', 'print("Bonjour")')
        pages = [{'page': 1, 'raw_text': c.evidence[0].excerpt}]
        with patch.object(cards, 'chat_json') as generate, patch.object(cards, 'audit_cards', return_value={'code': []}) as audit:
            result = cards._generate_batch({}, pages, [c], model=STUDY_MODEL)
        generate.assert_not_called()
        self.assertEqual(audit.call_args.kwargs['model'], STUDY_MODEL)
        self.assertEqual(result[0].sections[0].content, '```\nprint("Bonjour")\n```')

    def test_heading_only_proof_with_bullets_is_blocked_for_any_subject(self):
        c = concept('label', 'Photosynthèse', 'Photosynthèse\n•\nPhotosynthèse')
        page = {'page': 1, 'raw_text': c.evidence[0].excerpt}
        self.assertIn('titre', inventory.concept_evidence_issue(c, [page]))

    def test_truncated_code_is_completed_from_same_block_only(self):
        c = concept('code', 'Exemple', 'sample { value: 3;')
        source = 'Solution\nsample { value: 3;\nother: 4; }\nneighbor { value: 99; }'
        page = {'page': 1, 'raw_text': source, 'source_units': [{'heading': 'Solution', 'excerpt': source}]}
        repaired = inventory.refresh_concept_evidence(c, [page])
        self.assertEqual(repaired.evidence[0].excerpt, 'sample { value: 3;\nother: 4; }')
        self.assertNotIn('neighbor', repaired.evidence[0].excerpt)

    def test_subtitle_recovers_only_its_attached_markup(self):
        c = concept('code', 'Exemple de balisage', 'Afficher le résultat')
        source = 'Document\nAfficher le résultat\n▪\n<output>Résultat</output>'
        page = {'page': 1, 'raw_text': source, 'source_units': [{'heading': 'Document', 'excerpt': source}]}
        self.assertIn('<output>', inventory.refresh_concept_evidence(c, [page]).evidence[0].excerpt)
        page['source_units'][0]['excerpt'] += '\nAutre notion\n<secret>Autre</secret>'
        self.assertEqual(inventory.refresh_concept_evidence(c, [page]).evidence, c.evidence)


class AutomaticPipelineTests(TestCase):


    def test_empty_json_retries_once_with_larger_budget_without_mutating_options(self):
        options = {'num_predict': 2200}
        original = deepcopy(options)
        with patch.object(client, 'chat_text', side_effect=['', '{"ok": true}']) as call:
            self.assertEqual(client.chat_json(model=STUDY_MODEL, options=options), {'ok': True})
        self.assertEqual(options, original)
        self.assertEqual(call.call_args.kwargs['options']['num_predict'], 4400)
        self.assertEqual(call.call_args.kwargs['model'], STUDY_MODEL)
        with patch.object(client, 'chat_text', return_value='') as call:
            with self.assertRaisesRegex(ValueError, 'deux réponses JSON vides'):
                client.chat_json()
        self.assertEqual(call.call_count, 2)

    def test_scanned_upload_uses_ocr(self):
        with pymupdf.open() as pdf:
            pdf.new_page()
            data = pdf.tobytes()
        with TemporaryDirectory() as folder, patch.object(upload_service, 'UPLOAD_FOLDER', Path(folder)), \
             patch('src.pdf.ocr.extract_page_sources', return_value={'ocr_text': 'Un cours lisible par OCR.'}) as ocr:
            path, title, count = upload_service.save_validated_pdf(BytesIO(data), 'Biologie.pdf')
            self.assertTrue(path.exists())
            self.assertEqual(count, 1)
            ocr.assert_called_once()

    def test_cli_process_runs_the_shared_pipeline(self):
        import manage
        with patch.object(manage, 'find_course', return_value={'course_id': 'cours'}), \
             patch.object(pipeline, 'process_course', return_value={'status': 'ready'}) as process, \
             patch('builtins.print'):
            self.assertEqual(manage.main(['process', '--course', 'Cours']), 0)
        self.assertEqual(process.call_args.args, ('cours',))
