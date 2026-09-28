import json
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock,patch
from webapp.model_comparison import TARGETS,MODELS,select_rows,compare
from webapp.api import ApiSummarizer,BASE_URL,CONTEXT,OUTPUT


class ComparisonTests(unittest.TestCase):
    def rows(self):
        return [['0. 기타법','- 기타','','',''],*[[f'{n}. {law}','- 지원','','','없음'] for n,law in TARGETS.items()]]

    def test_exact_selection_not_excel_indices(self):
        self.assertEqual([n for n,_ in select_rows(self.rows())],[3,4,5,6])
        with self.assertRaises(ValueError): select_rows(self.rows()[:-1])
        with self.assertRaises(ValueError): select_rows(self.rows()+[self.rows()[1]])

    def test_eight_calls_same_source_no_mutation(self):
        previous={'rows':self.rows(),'folder':'output/source'}
        before=json.dumps(previous)
        record={'department':'지원실 지원과','department_name':'지원과','reference':'제1조',
                'paragraph':'①','duty':'지원','article_title':'지원실'}
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':'{"items":["D0","U0","지원 관련"]}'}}]}
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.model_comparison.ROOT',Path(tmp)),\
             patch('webapp.model_comparison.fetch_duties',return_value=([record],{'effective_date':'20260828'})) as fetch,\
             patch('webapp.api.httpx.post',return_value=response) as post:
            result=compare(previous,'private-key','private-oc',Queue())
        self.assertEqual(post.call_count,8); fetch.assert_called_once()
        self.assertEqual(json.dumps(previous),before)
        self.assertTrue(all(r['selected']=='지원실\n지원과' for r in result['results']))
        self.assertNotIn('private-',result['report'].decode())
        payloads=[call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual([p['model'] for p in payloads],['gpt-6-sol']*4+['gpt-6-astra']*4)
        for i in range(4): self.assertEqual(payloads[i]['messages'],payloads[i+4]['messages'])
        for p in payloads:
            self.assertEqual(p['reasoning_effort'],'medium')
            self.assertEqual(p['response_format'],{'type':'json_object'})
