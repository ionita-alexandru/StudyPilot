import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict
from src.ai import client, gemma
from src.courses import learning_material as material


class Judgment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supported: bool
    reason: str


class RecoveryBudget(unittest.TestCase):
    def test_exact_schema_prefix_removed_but_actual_answer_validated(self):
        schema = json.dumps(Judgment.model_json_schema())
        with patch.object(client, 'chat_text', return_value=schema + '\n{"supported":true,"reason":"citation"}'):
            self.assertTrue(client.chat_json(response_model=Judgment)['supported'])
        for text in (schema, schema + '\n{"supported":true,"reason":"a"}\n{"supported":false,"reason":"b"}',
                     schema + '\n{"supported":true,"reason":"a","extra":1}'):
            with self.subTest(text=text), patch.object(client, 'chat_text', return_value=text), self.assertRaises(ValueError) as caught:
                client.chat_json(response_model=Judgment)
            self.assertEqual(caught.exception.response_text, text[:6000])

    def test_different_schema_is_never_discarded(self):
        with patch.object(client, 'chat_text', return_value='{"properties":{}}\n{"supported":true,"reason":"a"}'), self.assertRaises(ValueError):
            client.chat_json(response_model=Judgment)

    def test_fenced_exact_schema_and_fenced_answer(self):
        schema = json.dumps(Judgment.model_json_schema())
        with patch.object(client, 'chat_text', return_value='```json\n' + schema + '\n```\n```json\n{"supported":true,"reason":"source"}\n```'):
            self.assertTrue(client.chat_json(response_model=Judgment)['supported'])

    def test_theorem_kind_is_explanation_without_changing_line_selection(self):
        from src.courses.pedagogy import Fact
        f = Fact(title='Énoncé', kind='theorem', start_line=2, end_line=6)
        self.assertEqual((f.kind, f.start_line, f.end_line), ('explanation', 2, 6))
        for kind in ('developed', 'unreadable', 'invented'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                Fact(title='Énoncé', kind=kind, start_line=2, end_line=6)

    def sources(self):
        # Extraction mathématique très fragmentée, comme le diagnostic réel.
        return [{'ref': f'u{i}', 'page': i+1, 'heading': 'Formule',
                 'lines': [{'id': n+1, 'text': f'{n} − xₙ / 2\n'} for n in range(100)]} for i in range(12)]

    def test_large_recovery_split_all_sources_preserved_and_resume(self):
        sources = self.sources(); calls = []; checkpoint = {}; saves = []
        concept = SimpleNamespace(concept_id='c1', title='Notion')
        def call(schema, prompt, payload, model, validate):
            if schema is material.EvidenceScope:
                return validate(material.EvidenceScope(verdict='about_this_notion', reason='Source propre à la notion'))
            calls.append(payload['sources'])
            if len(payload['sources']) > 3:
                raise client.AIInputTooLargeError('trop grand')
            return validate(material.EvidenceRecovery(selections=[material.SourceSelection(
                source_ref=s['ref'], start_line=1, end_line=100, kind='formula') for s in payload['sources']], reason='Toutes les formules sélectionnées'))
        with patch.object(material, 'source_candidates', return_value=sources):
            result = material.recover(concept, [], {}, 'gemma-4-26b-a4b-it', call, checkpoints=checkpoint, save=lambda:saves.append(1))
            self.assertEqual(len(result['points']), len(sources))
            self.assertEqual(set(result['searched_sources']), {s['ref'] for s in sources})
            for p in result['points']:
                source = next(s for s in sources if s['ref'] == p['source_ref'])
                self.assertEqual(p['quote'], ''.join(l['text'] for l in source['lines']))
            self.assertTrue(saves)
            with patch.object(material, 'source_candidates', return_value=sources):
                again = material.recover(concept, [], {}, 'gemma-4-26b-a4b-it', lambda *a: self.fail('Lot déjà validé rappelé'), checkpoints=checkpoint)
            self.assertEqual(again, result)

    def test_quota_is_not_split_or_retried(self):
        call = unittest.mock.Mock(side_effect=client.AIUsageLimitError('HTTP 429'))
        with patch.object(material, 'source_candidates', return_value=self.sources()), self.assertRaises(client.AIUsageLimitError):
            material.recover(SimpleNamespace(concept_id='c', title='notion'), [], {}, 'm', call)
        self.assertEqual(call.call_count, 1)

    def test_single_oversize_unit_stops_without_truncation(self):
        sources = self.sources()[:1]
        call = unittest.mock.Mock(side_effect=client.AIInputTooLargeError('trop grand'))
        with patch.object(material, 'source_candidates', return_value=sources), self.assertRaises(client.AIInputTooLargeError):
            material.recover(SimpleNamespace(concept_id='c', title='notion'), [], {}, 'm', call)
        self.assertEqual(call.call_args.args[2]['sources'], sources)

    def test_failed_second_batch_keeps_validated_first_for_resume(self):
        checkpoint = {}; sources = self.sources()[:2]; seen = []
        def call(schema, prompt, payload, model, validate):
            if len(payload['sources']) > 1:
                raise client.AIInputTooLargeError('trop grand')
            ref = payload['sources'][0]['ref']; seen.append(ref)
            if ref == 'u1':
                raise client.AIUsageLimitError('HTTP 429')
            return validate(material.EvidenceRecovery(selections=[], reason='Pas de nouvel ajout'))
        with patch.object(material, 'source_candidates', return_value=sources), self.assertRaises(client.AIUsageLimitError):
            material.recover(SimpleNamespace(concept_id='c', title='notion'), [], {}, 'm', call, checkpoints=checkpoint)
        self.assertEqual(sum('points' in v for v in checkpoint.values()), 1)
        self.assertTrue(any(v.get('split') for v in checkpoint.values()))
        self.assertEqual(seen, ['u0', 'u1'])

    def test_oversize_distinct_from_daily_quota(self):
        with self.assertRaises(client.AIInputTooLargeError):
            gemma._reserve(gemma.TPM + 1)


if __name__ == '__main__':
    unittest.main()
