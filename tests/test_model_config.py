import unittest
from unittest.mock import Mock, patch

from webapp.api import ApiSummarizer, BASE_URL, CHANGE_PROMPT, CONTEXT, MODEL, OUTPUT


class ModelConfigTests(unittest.TestCase):
    def test_luna_request_preserves_summary_contract(self):
        self.assertEqual(MODEL, 'gpt-6-luna')
        self.assertEqual(CONTEXT, 1_050_000)
        self.assertEqual(OUTPUT, 8192)
        response = Mock(status_code=200)
        response.json.return_value = {
            'choices': [{'finish_reason': 'stop', 'message': {
                'content': '{"items":["- 신청기한을 7일에서 14일로 연장"]}'
            }}]
        }
        engine = ApiSummarizer(BASE_URL, 'test-key', MODEL, CONTEXT, OUTPUT,
                               token_field='max_completion_tokens')
        with patch('webapp.api.httpx.post', return_value=response) as send:
            items = engine.summarize_document('현행 7일, 개정 14일', '지원법', '신청기한 연장')
        self.assertEqual(items, ['신청기한을 7일에서 14일로 연장'])
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], BASE_URL + '/chat/completions')
        payload = send.call_args.kwargs['json']
        self.assertEqual(payload['model'], 'gpt-6-luna')
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(payload['max_completion_tokens'], OUTPUT)
        self.assertNotIn('max_tokens', payload)
        self.assertEqual(payload['messages'][0]['content'], CHANGE_PROMPT)
