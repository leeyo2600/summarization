import json
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

from webapp.jobs import save_result
from webapp.department_retry import load_saved_result, saved_results, retry_departments


class RetryTests(unittest.TestCase):
    def previous(self):
        return {'rows':[['지원법','- 기관 지원 확대\n- 지원 기준 개선','기관','2026.9.23(수)',''],
                        ['기존법','- 기존 내용','기관','2026.9.23(수)','지원과']],
                'report':json.dumps({'files':[{},{}],'issues':[
                    {'file':'소관부서 추천','error':'미해석 조문'},
                    {'file':'원문.pdf','error':'DRM 문서'}],
                    'department_matching':{'enabled':True,'error':'미해석 조문','results':[
                        {'law':'지원법','status':'error','error':'미해석 조문'},
                        {'law':'기존법','status':'ok','selected':'지원과'}]}}).encode(),
                'success':2,'total':2,'folder':'output/법령요약_previous'}

    def test_retry_only_blank_and_preserve_summary_original_and_errors(self):
        previous=self.previous()
        snapshot=json.dumps(previous['rows'],ensure_ascii=False)
        engine=Mock()
        matcher=Mock(source={'law_id':'012925'})
        matcher.match.return_value=('법무담당관',{'law':'지원법','status':'ok','selected':'법무담당관'})
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.jobs.ROOT',Path(tmp)),\
             patch('webapp.department_retry.ROOT',Path(tmp)),\
             patch('webapp.department_retry.ApiSummarizer',return_value=engine),\
             patch('webapp.department_retry.DepartmentMatcher',return_value=matcher):
            result=retry_departments(previous,'secret-key',Queue(),'secret-oc')
            self.assertEqual(matcher.match.call_count,1)
            matcher.match.assert_called_once_with('지원법',['기관 지원 확대','지원 기준 개선'])
            engine.summarize_document.assert_not_called()
            self.assertEqual([r[:4] for r in result['rows']],[r[:4] for r in previous['rows']])
            self.assertEqual([r[4] for r in result['rows']],['법무담당관','지원과'])
            self.assertEqual(result['issues'],[{'file':'원문.pdf','error':'DRM 문서'}])
            names=saved_results()
            self.assertEqual(len(names),1)
            loaded=load_saved_result(names[0])
            self.assertEqual(loaded['rows'],result['rows'])
            self.assertEqual(loaded['total'],2)
            raw=loaded['report'].decode()
            self.assertNotIn('secret-key',raw)
            self.assertNotIn('secret-oc',raw)
            self.assertEqual(json.loads(raw)['department_matching']['retried_rows'],[2])
        self.assertEqual(json.dumps(previous['rows'],ensure_ascii=False),snapshot)

    def test_init_error_does_not_save_or_modify_previous(self):
        previous=self.previous()
        with patch('webapp.department_retry.DepartmentMatcher',side_effect=ValueError('조회 실패')),\
             patch('webapp.department_retry.save_result') as save:
            with self.assertRaisesRegex(ValueError,'조회 실패'):
                retry_departments(previous,'key',Queue(),'oc')
        save.assert_not_called()
        self.assertEqual(previous['rows'][0][4],'')

    def test_match_error_is_not_none_result_and_is_retryable(self):
        previous=self.previous()
        matcher=Mock(source={})
        matcher.match.side_effect=ValueError('부서 추천 응답 오류')
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.jobs.ROOT',Path(tmp)),\
             patch('webapp.department_retry.DepartmentMatcher',return_value=matcher):
            result=retry_departments(previous,'key',Queue(),'oc')
        self.assertEqual(result['rows'][0][4],'')
        self.assertEqual(result['rows'][1][4],'지원과')
        self.assertEqual(result['issues'][-1]['error'],'부서 추천 응답 오류')

    def test_below_threshold_none_is_written_and_old_run_is_unchanged(self):
        previous=self.previous()
        matcher=Mock(source={})
        matcher.match.return_value=('없음',{'law':'지원법','status':'ok','selected':'없음'})
        with tempfile.TemporaryDirectory() as tmp,patch('webapp.jobs.ROOT',Path(tmp)),\
             patch('webapp.department_retry.ROOT',Path(tmp)),\
             patch('webapp.department_retry.DepartmentMatcher',return_value=matcher):
            original=save_result(previous['rows'],json.loads(previous['report']),success=2,total=2)
            original_path=Path(original['folder'])/'법령_주요내용_요약.xlsx'
            before=original_path.read_bytes()
            result=retry_departments(original,'key',Queue(),'oc')
            self.assertEqual(result['rows'][0][4],'없음')
            self.assertEqual(original_path.read_bytes(),before)
            self.assertNotEqual(result['folder'],original['folder'])
            self.assertEqual(len(saved_results()),2)

    def test_completed_result_does_not_call_api(self):
        previous=self.previous(); previous['rows'][0][4]='없음'
        with patch('webapp.department_retry.DepartmentMatcher') as matcher:
            with self.assertRaisesRegex(ValueError,'빈 비고'):
                retry_departments(previous,'key',Queue(),'oc')
            matcher.assert_not_called()

    def test_loader_rejects_outside_directory(self):
        with self.assertRaisesRegex(ValueError,'이 앱에서 저장한'):
            load_saved_result('../../config.json')
