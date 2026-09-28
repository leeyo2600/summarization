import json
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock,patch
from webapp.gpt_departments import GptDepartmentMatcher
from webapp.department_retry import retry_departments


class ProductionGptTests(unittest.TestCase):
    def test_all_rows_including_none_use_gpt_and_no_embeddings(self):
        record={'department':'행정안전부 지원과','department_name':'지원과','reference':'제5조',
                'paragraph':'③','duty':'기관 지원','article_title':'지원업무'}
        engine=Mock(model='gpt-6-luna',context=1000000,output=8192,audit=[])
        engine._request.return_value=['D0','U0','기관 지원 검토에 적합']
        previous={'rows':[[f'법령{i}','- 기관 지원','','','없음'] for i in range(5)],
                  'report':b'{"issues":[],"files":[]}', 'folder':'output/previous',
                  'success':5,'total':5}
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.jobs.ROOT',Path(tmp)),\
             patch('webapp.gpt_departments.fetch_duties',return_value=([record],{'effective_date':'20260828'})),\
             patch('webapp.department_retry.ApiSummarizer',return_value=engine),\
             patch('webapp.departments.embedding_model') as embed,\
             patch('webapp.departments.ensure_embedding_files') as download:
            result=retry_departments(previous,'key',Queue(),'oc',retry_all=True)
        self.assertEqual(engine._request.call_count,5)
        self.assertTrue(all(row[4]=='지원과' for row in result['rows']))
        self.assertTrue(all(row[4]=='없음' for row in previous['rows']))
        embed.assert_not_called(); download.assert_not_called()
        audit=json.loads(result['report'])['department_matching']
        self.assertEqual(audit['mode'],'gpt_only')
        self.assertFalse(audit['embedding_used'])
        self.assertIsNone(audit['threshold'])
        self.assertEqual(len(audit['results']),5)

    def test_actual_matcher_abstains_and_rejects_invalid_evidence(self):
        engine=Mock(model='gpt-6-luna',context=1000000,output=8192)
        with patch('webapp.gpt_departments.fetch_duties',return_value=([],{'effective_date':'20260828'})):
            matcher=GptDepartmentMatcher('oc',engine)
        engine._request.return_value=['없음','없음','검토 근거 없음']
        self.assertEqual(matcher.match('법',['내용'])[0],'없음')
        engine._request.return_value=['D0','U0','근거']
        with self.assertRaises(ValueError): matcher.match('법',['내용'])
