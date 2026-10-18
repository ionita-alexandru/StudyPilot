import io,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from src.ai import gemma,client
import reprendre_cours as runner
from types import SimpleNamespace

def failure(code=500):
    return HTTPError('url',code,'secret',{},io.BytesIO(json.dumps({'error':{'status':'INTERNAL','message':'secret-key source text'}}).encode()))

class ServerRecovery(unittest.TestCase):
    def test_500_then_success_same_source_reserved_on_retry(self):
        payload={'contents':[{'role':'user','parts':[{'text':'source intacte x >= 0'}]}]}
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=[failure(),io.BytesIO(b'{"ok":true}')]) as call,patch.object(gemma,'_record_failure') as record,patch.object(gemma,'_reserve') as reserve,patch.object(gemma.time,'sleep') as sleep:
            self.assertEqual(gemma._post('gemma-4-31b-it','generateContent',payload,retry_tokens=1700),{'ok':True})
        self.assertEqual(call.call_count,2);reserve.assert_called_once_with(1700);self.assertEqual(sleep.call_count,1)
        self.assertEqual(call.call_args_list[0].args[0].data,call.call_args_list[1].args[0].data)
        self.assertEqual(record.call_args.args[4],'INTERNAL')

    def test_persistent_5xx_stops_after_three_and_keeps_error_explicit(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=[failure(500),failure(503),failure(502)]) as call,patch.object(gemma,'_record_failure') as record,patch.object(gemma,'_reserve') as reserve,patch.object(gemma.time,'sleep'),self.assertRaisesRegex(client.AIUsageLimitError,'après 3 tentatives'):
            gemma._post('gemma-4-31b-it','generateContent',{},retry_tokens=1000)
        self.assertEqual(call.call_count,3);self.assertEqual(reserve.call_count,2);self.assertEqual(record.call_count,3)

    def test_429_and_client_errors_never_retry(self):
        for code in (400,401,403,404,429):
            with self.subTest(code=code),patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=failure(code)) as call,patch.object(gemma,'_record_failure'),patch.object(gemma,'_reserve') as reserve,patch.object(gemma.time,'sleep') as sleep,self.assertRaises(client.AIUsageLimitError):
                gemma._post('gemma-4-31b-it','generateContent',{},retry_tokens=1000)
            self.assertEqual(call.call_count,1);sleep.assert_not_called();reserve.assert_not_called()

    def test_quota_during_reservation_prevents_another_network_call(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=failure()) as call,patch.object(gemma,'_record_failure'),patch.object(gemma,'_reserve',side_effect=client.AIUsageLimitError('budget atteint')),patch.object(gemma.time,'sleep'),self.assertRaisesRegex(client.AIUsageLimitError,'budget atteint'):
            gemma._post('gemma-4-31b-it','generateContent',{},retry_tokens=1000)
        self.assertEqual(call.call_count,1)

    def test_count_tokens_retry_does_not_reserve_a_generation(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'secret'}),patch.object(gemma,'_send',side_effect=[failure(503),io.BytesIO(b'{"totalTokens":1200}')]),patch.object(gemma,'_record_failure'),patch.object(gemma,'_reserve') as reserve,patch.object(gemma.time,'sleep'):
            self.assertEqual(gemma._post('gemma-4-31b-it','countTokens',{}),{'totalTokens':1200})
        reserve.assert_not_called()

    def test_metadata_locates_source_without_key_prompt_or_pixels(self):
        with TemporaryDirectory() as d,patch.object(gemma,'DATA_DIR',Path(d)):
            payload={'contents':[{'role':'user','parts':[{'text':json.dumps({'source':{'id':'p4-s1-0','page':4,'lines':[{'text':'secret-source'}]}})},{'inlineData':{'data':'secret-pixels'}}]}]}
            gemma._record_failure('gemma-4-31b-it','generateContent',payload,500,'INTERNAL',1,2400)
            data=(Path(d)/'_ai/gemma_failures.json').read_text();entry=json.loads(data)[0]
            self.assertNotIn('secret',data);self.assertEqual(entry['source_id'],'p4-s1-0');self.assertEqual(entry['source_page'],4);self.assertEqual(entry['input_tokens'],2400)

    def test_unknown_server_status_is_not_printed(self):
        error=HTTPError('url',500,'',{},io.BytesIO(b'{"error":{"status":"secret-key"}}'))
        self.assertEqual(gemma._failure_status(error),'UNKNOWN')

    def test_diagnostic_collection_includes_only_failure_metadata(self):
        import zipfile
        with TemporaryDirectory() as d:
            root=Path(d);(root/'data/_ai').mkdir(parents=True)
            (root/'data/_ai/gemma_failures.json').write_text('[{"http_status":500}]')
            (root/'data/_ai/gemma_rate.json').write_text('private-ledger')
            log=root/'resultats.txt';log.write_text('journal')
            result=runner.collect_diagnostic(root,SimpleNamespace(list_course_ids=lambda:[]),log,'test')
            with zipfile.ZipFile(result) as z:self.assertEqual(set(z.namelist()),{'resultats.txt','ai/gemma_failures.json'})

if __name__=='__main__':unittest.main()
