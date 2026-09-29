import unittest
import json
import tempfile
import shutil
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch
from lawtool import ROOT
from webapp.jobs import process

from webapp.api import ApiSummarizer, BASE_URL, CHANGE_PROMPT, CONTEXT, MODEL, OUTPUT


class ModelConfigTests(unittest.TestCase):
    def test_full_job_routes_summary_and_remarks_to_luna(self):
        doc={'name':'법안.hwpx','source':'법안.hwpx','scope':('0','1. 의견조회.zip'),
             'lines':['지원법 일부개정법률안','주요내용','기관 지원 확대']}
        group={'name':'공문','letter':{'agency':'행정안전부','department':'법무담당관',
            'deadline':'2026-09-23','source':'공문.pdf','warnings':[], 'scope':doc['scope']},'documents':[doc]}
        record={'department':'행정안전부 지원과','department_name':'지원과','article_title':'지원실',
                'reference':'제5조','paragraph':'③','duty':'기관 지원'}
        responses=[]
        for items in [['기관 지원 확대'],['D0','U0','지원 검토에 적합']]:
            response=Mock(status_code=200)
            response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'items':items})}}]}
            responses.append(response)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); shutil.copy2(ROOT/'config.json',directory/'config.json')
            with patch('webapp.jobs.ROOT',directory),patch('webapp.jobs.prepare',return_value=([group],[])),\
                 patch('webapp.gpt_departments.fetch_duties',return_value=([record],{'effective_date':'20260828'})),\
                 patch('webapp.api.httpx.post',side_effect=responses) as send:
                result=process([],'key',Queue(),law_oc='oc')
        calls=[call.kwargs['json'] for call in send.call_args_list]
        self.assertEqual([p['model'] for p in calls],['gpt-6-luna','gpt-6-luna'])
        self.assertEqual([p['reasoning_effort'] for p in calls],['none','none'])
        self.assertEqual(result['rows'][0],['1. 지원법','- 기관 지원 확대','행정안전부\n법무담당관','2026.9.23(수)','지원실\n지원과'])
        report=json.loads(result['report'])
        self.assertEqual(report['model'],'gpt-6-luna')
        self.assertEqual(report['department_matching']['model'],'gpt-6-luna')
        self.assertEqual(len(report['files'][0]['requests']),1)
        self.assertEqual(len(report['department_matching']['requests']),1)

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
        self.assertEqual(send.call_args.kwargs['timeout'],120)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(payload['max_completion_tokens'], OUTPUT)
        self.assertNotIn('max_tokens', payload)
        self.assertEqual(payload['messages'][0]['content'], CHANGE_PROMPT)
