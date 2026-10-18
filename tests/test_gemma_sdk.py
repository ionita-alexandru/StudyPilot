import base64
import io
import json
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError

import httpx
from google import genai
from src.ai import gemma


class SDKTransport(unittest.TestCase):
    def run_sdk(self, method, payload, status=200):
        calls = []
        original = genai.Client
        def respond(request):
            calls.append(request)
            body = ({'error': {'code': status, 'status': 'INTERNAL', 'message': 'SECRET source'}} if status != 200
                else {'totalTokens': 200} if method == 'countTokens' else
                {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"ok":true}'}]}}]})
            return httpx.Response(status, json=body)
        def factory(**kw):
            self.assertEqual(kw['http_options'].retry_options.attempts, 1)
            kw['http_options'].httpx_client = httpx.Client(transport=httpx.MockTransport(respond))
            kw['http_options'].async_client_args = {'trust_env': False}
            return original(**kw)
        request = Request(gemma.BASE_URL + 'gemma-4-26b-a4b-it:' + method,
            data=json.dumps(payload).encode(), headers={'x-goog-api-key': 'fake-key'})
        with patch.object(genai, 'Client', side_effect=factory):
            try:
                response = gemma._send(request, 180)
            except HTTPError as error:
                self.assertEqual(len(calls), 1)
                return error, calls
        return json.load(response), calls

    def payload(self):
        return {'contents': [{'role': 'user', 'parts': [{'text': 'x > 0 ; cₙ = (aₙ − i bₙ)/2'},
            {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(b'pixels-source').decode()}}]}],
            'systemInstruction': {'parts': [{'text': 'PDF uniquement'}]}}

    def test_count_complete_instructions_images_and_model(self):
        payload = {'generateContentRequest': {'model': 'models/gemma-4-26b-a4b-it', **self.payload()}}
        result, calls = self.run_sdk('countTokens', payload)
        self.assertEqual(result['totalTokens'], 200)
        self.assertEqual(json.loads(calls[0].content), payload)
        self.assertEqual(calls[0].headers['x-goog-api-key'], 'fake-key')
        self.assertNotIn('fake-key', str(calls[0].url))

    def test_generate_preserves_math_pixels_and_options(self):
        payload = self.payload()
        payload['generationConfig'] = {'temperature': 0, 'maxOutputTokens': 5000,
            'thinkingConfig': {'thinkingLevel': 'minimal'}}
        result, calls = self.run_sdk('generateContent', payload)
        sent = json.loads(calls[0].content)
        self.assertEqual(sent['contents'][0]['parts'][0]['text'], payload['contents'][0]['parts'][0]['text'])
        image = sent['contents'][0]['parts'][1]['inlineData']
        self.assertEqual(base64.b64decode(image['data']), b'pixels-source')
        self.assertEqual(image.get('mimeType', image.get('mime_type')), 'image/png')
        self.assertEqual(sent['systemInstruction'], payload['systemInstruction'])
        self.assertEqual(sent['generationConfig']['maxOutputTokens'], 5000)
        thought = sent['generationConfig']['thinkingConfig']
        self.assertEqual(thought.get('thinkingLevel', thought.get('thinking_level')).lower(), 'minimal')
        self.assertEqual(result['candidates'][0]['finishReason'], 'STOP')

    def test_server_error_has_no_hidden_sdk_retry_or_raw_message(self):
        payload = self.payload(); payload['generationConfig'] = {'temperature': 0}
        error, calls = self.run_sdk('generateContent', payload, 500)
        self.assertEqual(error.code, 500)
        body = error.read()
        self.assertNotIn(b'SECRET', body)
        self.assertEqual(json.loads(body)['error']['status'], 'INTERNAL')


if __name__ == '__main__':
    unittest.main()
