import unittest
from unittest.mock import patch
from webapp.api import ApiSummarizer, split_text

class ApiTests(unittest.TestCase):
    def test_no_character_lost(self):
        text=('가나다🙂\n변경사항 입니다. '*300)
        chunks=split_text(text,256)
        self.assertEqual(''.join(chunks),text)
        self.assertTrue(all(len(c.encode('utf-8'))<=256 for c in chunks))

    def response(self,reason,content='{"items":["지원 범위 확대"]}'):
        class Response:
            status_code=200
            def json(self): return {'choices':[{'finish_reason':reason,'message':{'content':content}}],'usage':{'prompt_tokens':100}}
        return Response()

    def test_truncated_response_retried_not_committed(self):
        engine=ApiSummarizer('https://example.test/v1','secret','luna-test',32768,2048)
        with patch('webapp.api.httpx.post',side_effect=[self.response('length'),self.response('stop'),self.response('stop')]) as send:
            self.assertEqual(engine.summarize('가'*150),['지원 범위 확대'])
            self.assertEqual(send.call_count,3)
        self.assertNotIn('secret',str(engine.audit))

    def test_incomplete_cannot_succeed(self):
        engine=ApiSummarizer('https://example.test/v1','secret','luna-test',32768,2048)
        with patch('webapp.api.httpx.post',return_value=self.response('length')):
            with self.assertRaises(ValueError): engine.summarize('짧은 원문')

    def test_bad_json(self):
        engine=ApiSummarizer('https://example.test/v1','secret','luna-test',32768,2048)
        with patch('webapp.api.httpx.post',return_value=self.response('stop','not json')):
            with self.assertRaises(ValueError): engine.summarize('주요내용')
