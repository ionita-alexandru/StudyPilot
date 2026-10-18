import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pydantic import BaseModel, ConfigDict
from src.ai import client, gemma

MODEL = 'gemma-4-31b-it'

def answer(text='{"ok":true}', reason='STOP'):
    return {'candidates': [{'finishReason': reason, 'content': {'parts': [
        {'text': 'raisonnement privé', 'thought': True}, {'text': text}]}}]}

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ok: bool

class GemmaTests(unittest.TestCase):
    def test_dispatch_contract_and_model_without_ollama(self):
        responses = [{'totalTokens': 200}, answer()]
        with patch.object(client, 'AI_PROVIDER', 'gemma'), patch.object(gemma, '_post', side_effect=responses) as post, patch.object(gemma, '_reserve') as reserve, patch.object(client, '_ollama_chat') as ollama:
            result = client.chat_json(model=MODEL, response_model=Contract,
                messages=[{'role':'system','content':'PDF uniquement'}, {'role':'user','content':'x > 0'}],
                options={'num_predict': 4000, 'temperature': 0})
        self.assertEqual(result, {'ok':True}); ollama.assert_not_called(); reserve.assert_called_once_with(200)
        counted = post.call_args_list[0].args[2]['generateContentRequest']
        generated = post.call_args_list[1].args[2]
        self.assertEqual(counted['contents'], generated['contents'])
        self.assertEqual(counted['systemInstruction'], generated['systemInstruction'])
        self.assertEqual(json.dumps(counted).count('SCH'), 1)
        self.assertEqual(generated['generationConfig']['maxOutputTokens'], 4000)
        self.assertNotIn('responseMimeType', generated['generationConfig'])

    def test_schema_invalid_response_still_rejected(self):
        with patch.object(client,'AI_PROVIDER','gemma'), patch.object(gemma,'_post',side_effect=[{'totalTokens':1},answer('{"unknown":1}')]),patch.object(gemma,'_reserve'),self.assertRaises(ValueError):
            client.chat_json(model=MODEL,response_model=Contract,messages=[{'role':'user','content':'source'}])

    def test_long_base64_image_and_mathematics_are_preserved(self):
        raw = b'\x89PNG\r\n\x1a\n' + b'a' * 400
        text = r'c_n=(a_n-i b_n)/2 ; x\geq0'
        with patch.object(gemma,'_post',side_effect=[{'totalTokens':42},answer()]) as post,patch.object(gemma,'_reserve'):
            gemma.gemma_chat(model=MODEL,messages=[{'role':'user','content':text,'images':[base64.b64encode(raw).decode()]}])
        parts=post.call_args.args[2]['contents'][0]['parts']
        self.assertEqual(parts[0]['text'],text)
        self.assertEqual(base64.b64decode(parts[1]['inlineData']['data']),raw)
        self.assertEqual(parts[1]['inlineData']['mimeType'],'image/png')

    def test_truncated_reply_is_not_validated_as_complete(self):
        with patch.object(gemma,'_post',side_effect=[{'totalTokens':1},answer(reason='MAX_TOKENS')]),patch.object(gemma,'_reserve'),self.assertRaisesRegex(ValueError,'MAX_TOKENS'):
            gemma.gemma_chat(model=MODEL,messages=[{'role':'user','content':'source'}])

    def test_missing_key_before_network(self):
        with patch.dict('os.environ',{},clear=True),patch.object(gemma,'_send') as network,self.assertRaises(client.AIUnavailableError):
            gemma._post(MODEL,'countTokens',{})
        network.assert_not_called()

    def test_http_errors_stop_pipeline_without_exposing_secrets(self):
        for code in (400,401,403,429,503):
            with self.subTest(code=code),patch.dict('os.environ',{'GEMINI_API_KEY':'secret-value'}),patch.object(gemma,'_send',side_effect=HTTPError('url',code,'secret-value',{},io.BytesIO(b'secret-value'))),patch.object(gemma,'_record_failure'),patch.object(gemma.time,'sleep'),self.assertRaises(client.AIUsageLimitError) as caught:
                gemma._post(MODEL,'generateContent',{})
            self.assertNotIn('secret-value',str(caught.exception))

    def test_network_error_not_converted_into_bad_source(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=URLError('secret')),self.assertRaises(client.AIUsageLimitError) as caught:
            gemma._post(MODEL,'generateContent',{})
        self.assertIsInstance(caught.exception,client.AIUnavailableError)
        self.assertNotIn('secret',str(caught.exception))

    def test_key_in_header_not_url(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',return_value=io.BytesIO(b'{"totalTokens":12}')) as call:
            self.assertEqual(gemma._post(MODEL,'countTokens',{}),{'totalTokens':12})
        request=call.call_args.args[0]
        self.assertNotIn('secret',request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'),'secret')

    def test_invalid_count_prevents_generation(self):
        with patch.object(gemma,'_post',return_value={'totalTokens':True}) as post,self.assertRaises(client.AIUsageLimitError):
            gemma.gemma_chat(model=MODEL,messages=[{'role':'user','content':'source'}])
        self.assertEqual(post.call_count,1)

    def test_wrong_model_no_fallback(self):
        with patch.object(gemma,'_post') as post,self.assertRaises(client.AIUnavailableError):
            gemma.gemma_chat(model='gpt-oss:120b-cloud',messages=[])
        post.assert_not_called()

    def test_large_prompt_never_truncated_or_sent(self):
        with patch.object(gemma,'_post',return_value={'totalTokens':16001}) as post,self.assertRaisesRegex(client.AIUsageLimitError,'Aucune source tronquée'):
            gemma.gemma_chat(model=MODEL,messages=[{'role':'user','content':'source complète'}])
        self.assertEqual(post.call_count,1)

    def test_token_window_waits_then_reserves(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'rate.json';path.write_text('[[100,14000]]')
            with patch.object(gemma.time,'time',side_effect=[110,162]),patch.object(gemma.time,'sleep') as sleep:
                gemma._reserve(1000,path)
            sleep.assert_called_once();self.assertEqual(json.loads(path.read_text()),[[162,1000]])

    def test_request_window_waits_even_for_tiny_prompts(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'rate.json';path.write_text(json.dumps([[100,1]]*gemma.RPM))
            with patch.object(gemma.time,'time',side_effect=[110,162]),patch.object(gemma.time,'sleep') as sleep:
                gemma._reserve(1,path)
            sleep.assert_called_once()

    def test_concurrent_reservations_keep_both_entries(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'rate.json'; errors=[]
            def reserve():
                try: gemma._reserve(10,path)
                except Exception as error: errors.append(error)
            threads=[threading.Thread(target=reserve) for _ in range(4)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertFalse(errors);self.assertEqual(len(json.loads(path.read_text())),4)

    def test_corrupt_ledger_is_preserved(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'rate.json';path.write_text('broken')
            with self.assertRaises(client.AIUsageLimitError):gemma._reserve(10,path)
            self.assertEqual(path.read_text(),'broken')

if __name__=='__main__':unittest.main()
