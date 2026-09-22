import unittest
from unittest.mock import Mock, patch
from webapp.api import ApiSummarizer, PROMPT, CHANGE_PROMPT


class ChangeSummaryTests(unittest.TestCase):
    def test_change_prompt_is_only_document_mode(self):
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':'{"items":["- 기한 연장"]}'}}]}
        engine=ApiSummarizer('https://example.test/v1','test','test',100000,8192)
        with patch('webapp.api.httpx.post',return_value=response) as send:
            engine.summarize_document('현행 7일, 개정 14일','지원법','기한 연장')
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.kwargs['json']['messages'][0]['content'],CHANGE_PROMPT)

    def test_unknown_variant_rejected(self):
        engine=ApiSummarizer('https://example.test/v1','test','test',100000,8192)
        with self.assertRaises(TypeError):
            engine.summarize_document('원문','지원법',variant='unknown')
