import json
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch
from webapp.gpt_department_experiment import experiment


class ExperimentTests(unittest.TestCase):
    def run_experiment(self,answers):
        records=[{'department':'행정안전부 지원과','department_name':'지원과','reference':'제5조',
                  'paragraph':'③','duty':'기관 지원','article_title':'지원업무'},
                 {'department':'소속기관 지원과','department_name':'지원과','reference':'제6조',
                  'paragraph':'③','duty':'소속기관 지원','article_title':'지원업무'}]
        engine=Mock(context=1000000,output=8192,audit=[])
        engine._request.side_effect=answers
        original={'folder':'output/source','rows':[['지원법','- 기관 지원','','','없음']]*3}
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.gpt_department_experiment.ROOT',Path(tmp)),\
             patch('webapp.gpt_department_experiment.fetch_duties',return_value=(records,{'effective_date':'20260828'})),\
             patch('webapp.gpt_department_experiment.ApiSummarizer',return_value=engine),\
             patch('webapp.departments.embedding_model') as embedding:
            result=experiment(original,'private-key','private-oc',Queue())
        embedding.assert_not_called()
        self.assertEqual(engine._request.call_count,2)
        self.assertEqual(original['rows'][0][4],'없음')
        self.assertNotIn('private-',result['report'].decode())
        payload=json.loads(engine._request.call_args.args[0])
        self.assertEqual(len(payload['departments']),2)
        self.assertNotIn('0.7',engine._request.call_args.kwargs['prompt'])
        return result

    def test_direct_selection_and_abstention(self):
        result=self.run_experiment([['D0','U0','기관 지원 업무에 해당'],['없음','없음','관련 업무 없음']])
        self.assertEqual([r['selected'] for r in result['results']],['지원과','없음'])
        self.assertEqual(result['results'][0]['evidence']['text'],'기관 지원')

    def test_wrong_department_evidence_and_invalid_response_fail(self):
        result=self.run_experiment([['D0','U1','다른 부서 근거'],['없는부서']])
        self.assertTrue(all(r['status']=='error' and r['selected']=='' for r in result['results']))

    def test_api_failure_is_not_none(self):
        result=self.run_experiment([ValueError('API HTTP 401'),['없음','없음','관련 업무 없음']])
        self.assertEqual(result['results'][0]['status'],'error')
        self.assertEqual(result['results'][0]['selected'],'')
