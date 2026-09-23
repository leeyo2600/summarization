import ssl
import unittest
from unittest.mock import patch
import httpx
from webapp.api import ApiSummarizer, SSL_CONTEXT


class TlsTests(unittest.TestCase):
    def test_verification_stays_enabled(self):
        self.assertEqual(SSL_CONTEXT.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(SSL_CONTEXT.check_hostname)

    def test_context_passed_and_errors_distinguished(self):
        engine=ApiSummarizer('https://example.test/v1','test','test',100000,8192)
        for error,message in [
            (httpx.ConnectError('CERTIFICATE_VERIFY_FAILED'),'SSL 인증서'),
            (httpx.ConnectError('connection refused'),'서버 연결 실패'),
            (httpx.ReadTimeout('timeout'),'시간 초과'),
        ]:
            with self.subTest(message=message):
                with patch('webapp.api.httpx.post',side_effect=error) as send:
                    with self.assertRaisesRegex(ValueError,message):
                        engine.summarize_document('지원 범위 확대','지원법')
                    self.assertIs(send.call_args.kwargs['verify'],SSL_CONTEXT)
