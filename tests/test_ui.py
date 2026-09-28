import unittest
import time
from concurrent.futures import Future
from queue import Queue
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from lawtool import ROOT
from webapp.api import MODEL


class UiTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT/'app.py')).run()

    def test_input(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='start_summary').disabled)
        self.assertTrue(any(MODEL in caption.value for caption in app.caption))
        self.assertEqual(app.text_input(key='law_oc').label,'국가법령정보센터 API OC')
        self.assertTrue(app.checkbox(key='match_departments').value)
        app.checkbox(key='match_departments').uncheck().run()
        self.assertTrue(app.text_input(key='law_oc').disabled)
        self.assertFalse(any('A/B' in x.label for x in app.checkbox))

    def test_gpt_experiment_keeps_original_and_clears_credentials(self):
        app=self.app(); future=Future()
        previous={'total':1,'success':1,'rows':[['지원법','- 지원 확대','','','없음']],
                  'issues':[],'xlsx':b'test','report':b'{}','folder':'output/test'}
        app.session_state.page='complete'; app.session_state.result=previous
        app.run()
        self.assertTrue(app.button(key='gpt_test_start').disabled)
        app.text_input(key='gpt_test_key').set_value('test-key')
        app.text_input(key='gpt_test_oc').set_value('test-oc')
        app.checkbox(key='gpt_test_consent').check().run()
        with patch('webapp.jobs.EXECUTOR.submit',return_value=future) as submit:
            app.button(key='gpt_test_start').click().run()
            self.assertEqual(submit.call_count,1)
        self.assertFalse(app.exception)
        future.set_result({'results':[{'excel_row':2,'law':'지원법','status':'ok',
            'selected':'없음','reason':'직접 관련 업무 없음','evidence':None}],
            'report':b'{}','folder':'output/experiment'})
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.result,previous)
        self.assertEqual(app.text_input(key='gpt_test_key').value,'')
        self.assertTrue(any('직접 관련 업무 없음' in caption.value for caption in app.caption))

    def test_processing_partial_result_and_reset(self):
        app=self.app(); future=Future()
        app.session_state.page='processing'
        app.session_state.job=future
        app.session_state.job_timing={'started':time.monotonic()-65}
        app.session_state.progress=Queue()
        app.session_state.progress.put((0,0,'자료 준비 중'))
        app.run(); self.assertFalse(app.exception)
        self.assertTrue(any(metric.label=='경과 시간' and metric.value.startswith('1분 ') for metric in app.metric))
        app.session_state.job_timing={'started':100,'finished':225}
        future.set_result({'total':1,'success':1,'rows':[['지원법','- 지원 확대','','','']],
                           'issues':[{'file':'bad.pdf','error':'PdfStreamError'}],
                           'xlsx':b'test','report':b'{}','folder':'output/test'})
        app.run(); self.assertFalse(app.exception)
        self.assertEqual(app.session_state.page,'complete')
        self.assertTrue(app.warning)
        self.assertTrue(any(caption.value=='총 소요 시간: 2분 5초' for caption in app.caption))
        app.run()
        self.assertTrue(any(caption.value=='총 소요 시간: 2분 5초' for caption in app.caption))
        self.assertTrue(app.button(key='retry_departments').disabled)
        app.button(key='reset').click().run()
        self.assertEqual(app.session_state.page,'input')
        self.assertNotIn('job_timing',app.session_state)

    def test_all_failed(self):
        app=self.app()
        app.session_state.page='complete'
        app.session_state.result={'total':0,'success':0,'issues':[{'file':'bad.pdf','error':'error'}],
                                  'rows':[],'xlsx':None,'report':b'{}','folder':'output/test'}
        app.run(); self.assertFalse(app.exception)
        self.assertTrue(app.error)

    def test_retry_initialization_failure_preserves_previous_result(self):
        app=self.app(); future=Future()
        previous={'total':1,'success':1,'rows':[['지원법','- 지원 확대','','','']],
                  'issues':[],'xlsx':b'test','report':b'{}','folder':'output/test'}
        app.session_state.page='complete'; app.session_state.result=previous
        app.run()
        app.text_input(key='retry_key').set_value('test-key')
        app.text_input(key='retry_oc').set_value('test-oc')
        app.checkbox(key='retry_consent').check().run()
        with patch('webapp.jobs.EXECUTOR.submit',return_value=future) as submit:
            app.button(key='retry_departments').click().run()
            self.assertEqual(submit.call_count,1)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.page,'processing')
        future.set_exception(ValueError('조회 실패'))
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.page,'complete')
        self.assertEqual(app.session_state.result['rows'],previous['rows'])
        self.assertTrue(any('기존 요약은 그대로 보존' in error.value for error in app.error))
        self.assertEqual(app.text_input(key='retry_key').value,'')

    def test_load_saved_result_and_retry_success(self):
        previous={'total':1,'success':1,'rows':[['지원법','- 지원 확대','','','']],
                  'issues':[],'xlsx':b'test','report':b'{}','folder':'output/test'}
        with patch('webapp.department_retry.saved_results',return_value=['법령요약_test']),\
             patch('webapp.department_retry.load_saved_result',return_value=previous):
            app=self.app()
            app.button(key='load_saved_result').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.page,'complete')
        self.assertEqual(app.session_state.result['rows'],previous['rows'])
        future=Future()
        app.text_input(key='retry_key').set_value('test-key')
        app.text_input(key='retry_oc').set_value('test-oc')
        app.checkbox(key='retry_consent').check().run()
        with patch('webapp.jobs.EXECUTOR.submit',return_value=future):
            app.button(key='retry_departments').click().run()
        completed={**previous,'rows':[['지원법','- 지원 확대','','','지원과']]}
        future.set_result(completed)
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('비고 1행 처리 완료' in item.value for item in app.success))
        self.assertTrue(app.button(key='retry_departments').disabled)
