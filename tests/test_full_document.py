import json
import unittest
from unittest.mock import patch, Mock
from webapp.api import ApiSummarizer
from webapp.jobs import document_targets


class FullDocumentTests(unittest.TestCase):
    def engine(self):
        return ApiSummarizer('https://example.test/v1','test','test',100000,8192)

    def test_reason_only_document_has_target(self):
        self.assertEqual(document_targets(['지원법 일부개정법률안','1. 개정이유','신청기한을 14일로 연장함']),['지원법'])

    def test_whole_text_sent(self):
        text='지원법\n제정이유: 신청기한 연장\n주요내용: 절차 정비\n부칙: 시행일'
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':'{"items":["- 신청기한 연장"]}'}}]}
        with patch('webapp.api.httpx.post',return_value=response) as send:
            self.engine().summarize_document(text,'지원법','신청기한 연장')
        content=send.call_args.kwargs['json']['messages'][1]['content']
        source=json.loads(content.removeprefix('<자료>\n').removesuffix('\n</자료>'))
        self.assertEqual(source['문서 전체'],text)
        self.assertEqual(source['우선 요약할 주요내용'],'신청기한 연장')
        self.assertEqual(source['요약 대상 법령'],'지원법')

    def test_overflow_does_not_send_partial_document(self):
        engine=self.engine()
        engine.budget=100
        with patch('webapp.api.httpx.post') as send:
            with self.assertRaisesRegex(ValueError,'입력 한도'):
                engine.summarize_document('가'*100,'지원법')
            send.assert_not_called()

    def test_output_truncation_does_not_split_context(self):
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'length'}]}
        with patch('webapp.api.httpx.post',return_value=response) as send:
            with self.assertRaisesRegex(ValueError,'잘렸습니다'):
                self.engine().summarize_document('가'*1000,'지원법')
            self.assertEqual(send.call_count,1)
