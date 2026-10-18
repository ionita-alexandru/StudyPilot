from src.courses.pedagogy import QUALITY_VERSION
import unittest
from unittest.mock import patch
from src.courses.card_presentation import publication_issue, publication_view, present_card, render_text


def card(*contents, title='Notion'):
    return {'title': title, 'sections': [{'key': str(i), 'title': 'Définition' if i == 0 else 'Exemple', 'content': c} for i, c in enumerate(contents)]}


def model_card(identifier, content):
    from src.models.card import StudyCard
    return StudyCard(card_id='card-' + identifier, concept_id=identifier, title='Notion',
                     concept_type='concept', primary_part_id='p1', source_pages=[3],
                     sections=[{'key': 'definition', 'title': 'Définition', 'content': content}])


class PresentationTests(unittest.TestCase):
    def test_original_regressions_are_publishable(self):
        definitions = [
            'Ice Design, aussi appelé design rigide ou fixe, désigne une mise en page à largeur fixe, généralement alignée à la marge gauche.',
            'Le sélecteur d’élément HTML applique une règle CSS à tous les éléments d’un même type, par exemple : `<body>`, `<h1>`, `<h2>`.',
            'Les pseudo-classes CSS permettent de styliser un élément selon son état : :link, :visited, :focus, :hover, :active.',
        ]
        for text in definitions:
            with self.subTest(text=text):
                self.assertIsNone(publication_issue(card(text)))

    def test_other_disciplines_and_short_definitions(self):
        for text in ['Ensemble vide.', 'La tension augmente, le courant diminue, la résistance varie, le système se stabilise.',
                     'The algorithm visits vertices, records visits, stacks neighbours, stops the search.',
                     '速度表示位置随时间的变化。']:
            self.assertIsNone(publication_issue(card(text)))

    def test_technical_support_is_not_rejected_without_prose(self):
        for text in ['```css\ncolor: red;\n```', 'color: red;', r'\[ E = mc^2 \]',
                     'Étapes :\n1. Mesurer.\n2. Comparer.', 'Couleurs : rouge, vert, bleu.']:
            self.assertIsNone(publication_issue(card(text)))

    def test_empty_or_title_only_is_rejected(self):
        for text in ['   ', 'Notion', '```\n\n```']:
            self.assertIsNotNone(publication_issue(card(text)))

    def test_html_is_escaped_everywhere(self):
        html = render_text('```html\n<script>alert(1)</script>\n```\n\n**<img src=x onerror=alert(1)>** et `<div>`')
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('<code>&lt;div&gt;</code>', html)

    def test_code_is_not_markdown(self):
        self.assertEqual(render_text('```python\nx = a**2 + b**2\n# **literal**\n```'),
                         '<pre><code>x = a**2 + b**2\n# **literal**</code></pre>')
        self.assertEqual(render_text('`a**2 + b**2`'), '<p><code>a**2 + b**2</code></p>')
        self.assertEqual(render_text('`$x**2$`'), '<p><code>$x**2$</code></p>')

    def test_math_is_not_markdown(self):
        for text in ['\\[\na = b\n\\]', r'\[ x^{**} + y^{**} \]', r'\( x^{**} + y^{**} \)',
                     '$$x^{**} + y^{**}$$', '$x^{**} + y^{**}$']:
            html = render_text(text)
            self.assertIn(text, html)
            self.assertNotIn('<strong>', html)



    def test_lists_after_intro_and_ordered_lists(self):
        html = render_text('Procédure :\n1. Mesurer\n2. Comparer\n\nÉléments :\n- Tension\n- Courant')
        self.assertIn('<p>Procédure :</p><ol>', html)
        self.assertIn('<p>Éléments :</p><ul>', html)
        self.assertEqual(render_text('### Résultat\n\n***\n\nUne phrase.'), '<h3>Résultat</h3><hr><p>Une phrase.</p>')

    def test_heading_and_order_preserved_without_duplication(self):
        c = card('Définition attestée dans le cours.', '```css\ncolor: red;\n```')
        html = present_card(c)['content_html']
        self.assertEqual(html.count('Définition attestée'), 1)
        self.assertIn('<h3>Définition</h3>', html)
        self.assertNotIn('<h3>À retenir</h3>', html)
        self.assertEqual(c['sections'][0]['content'], 'Définition attestée dans le cours.')

    def test_diagram_remains_available(self):
        c = card('Observe le schéma.'); c['illustrations'] = [{'page': 3}]
        self.assertIsNone(publication_issue(c))


class PublicationIntegrationTests(unittest.TestCase):
    def collection(self):
        from src.models.card import CardCollection, CardPartCoverage
        return CardCollection(course_id='cours', file_hash='a'*64, inventory_hash='b'*64,
                              quality_version=QUALITY_VERSION, model='test', cards=[model_card('empty', 'Notion'), model_card('valid', 'Ensemble vide.')],
                              parts=[CardPartCoverage(part_id='p1', part_number='1', status='complete', cards_generated=2)])

    def test_cache_status_is_consistent_and_does_not_mutate_original(self):
        from src.courses.cards import cards_summary
        original = self.collection()
        view = publication_view(original)
        self.assertEqual(len(view.cards), 1)
        self.assertEqual(len(view.failures), 1)
        self.assertEqual(view.parts[0].status, 'error')
        self.assertEqual(view.parts[0].cards_generated, 1)
        self.assertEqual(len(original.cards), 2)
        self.assertEqual(original.parts[0].status, 'complete')
        self.assertEqual(cards_summary(original)['cards'], 1)
        self.assertEqual(cards_summary(original)['failed_concepts'], 1)
        self.assertEqual(cards_summary(original)['complete_parts'], 0)
        self.assertEqual(len(publication_view(view).failures), 1)

    def test_revision_and_unavailable_use_same_control(self):
        from src.courses import service
        from src.revision_service import revision_course_data
        original = self.collection()
        course = {'course_id': 'cours', 'file_hash': 'a'*64, 'title': 'Cours'}
        with patch.object(service, '_repository') as repo, patch.object(service, 'load_course', return_value=course), patch.object(service, 'load_course_plan', return_value={'parts': [{'id': 'p1', 'number': '1', 'title': 'Cours'}]}):
            repo.return_value.load_cards.return_value = original.model_dump(mode='json')
            data = revision_course_data('cours')
            self.assertEqual(data['card_count'], 1)
            self.assertEqual(data['cards'][0]['card_id'], 'card-valid')
            self.assertEqual(len(service.load_part_unavailable(course, 'p1')), 1)

    def test_literal_code_cache_is_kept(self):
        from src.courses import service
        collection = self.collection()
        collection.cards = [model_card('code', '```css\ncolor: red;\n```')]
        course = {'course_id': 'cours', 'file_hash': 'a'*64}
        with patch.object(service, '_repository') as repo:
            repo.return_value.load_cards.return_value = collection.model_dump(mode='json')
            cards = service.load_part_cards(course, 'p1')
            self.assertEqual(len(cards), 1)
            self.assertIn('<pre><code>color: red;</code></pre>', cards[0]['content_html'])

    def test_preview_rejects_title_only(self):
        import src.courses.cards as module
        from src.models.concept import Concept, ConceptEvidence, ConceptInventory
        concept = Concept(concept_id='empty', title='Notion', type='concept', primary_part_id='p1', source_pages=[3],
                          evidence=[ConceptEvidence(page=3, excerpt='Définition présente dans le document source.')])
        inventory = ConceptInventory(course_id='cours', file_hash='a'*64, model='test', concepts=[concept])
        with patch.object(module, 'load_course', return_value={'file_hash': 'a'*64, 'source_filename': 'cours.pdf'}), patch.object(module, 'load_course_plan', return_value={'parts': [{'id': 'p1', 'number': '1'}]}), patch.object(module, 'CourseRepository') as repo, patch.object(module, 'extract_document', return_value={'file_hash': 'a'*64, 'pages': [{'page': 3, 'raw_text': 'Définition présente dans le document source.'}]}), patch.object(module, '_generate_batch', return_value=[model_card('empty', 'Notion')]):
            repo.return_value.load_inventory.return_value = inventory.model_dump(mode='json')
            from src.courses.pedagogy import Material
            with patch.object(module, 'prepare_material', return_value=Material(inventory, 'test')), self.assertRaisesRegex(ValueError, 'sans contenu distinct'):
                module.preview_card('cours', concept_title='Notion')
