"""Optional real-fixture regression. No provider calls or permanent outputs."""
import shutil
import re
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import patch, Mock
from lawtool import ROOT
from webapp.jobs import process


class Batch46Tests(unittest.TestCase):
    def test_batch_keeps_45_cases_and_49_law_rows(self):
        source=Path('C:/Users/User/Desktop/260825-1 타부처의견조회(46건).zip')
        if not source.exists(): self.skipTest('46건 실자료 없음')
        engine=Mock(audit=[])
        engine.summarize_document.return_value=['테스트 응답: 실제 요약 아님']
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)
            shutil.copy2(ROOT/'config.json',destination/'config.json')
            with patch('webapp.jobs.ROOT',destination),patch('webapp.jobs.ApiSummarizer',return_value=engine):
                result=process([(source.name,source.read_bytes())],'test-key',Queue())
            self.assertEqual(result['success'],45)
            self.assertEqual(len(result['rows']),49)
            self.assertEqual(engine.summarize_document.call_count,49)
            self.assertEqual(len(result['issues']),2)
            self.assertTrue(all('DRM' in x['error'] for x in result['issues']))
            self.assertTrue(all(r[2] and r[3] and not r[4] for r in result['rows']))
            labels=[re.sub(r'^\d+(?:-\d+)?\. ','',r[0]) for r in result['rows']]
            self.assertEqual(sum(label.startswith('전자정부법') for label in labels),3)
            self.assertTrue(any(label.startswith('학점인정 등에 관한 업무처리 지침') for label in labels))
            self.assertTrue(any(label.startswith('자율주행자동차 상용화 촉진 및 지원에 관한 법률(김희정') for label in labels))
            self.assertFalse(any(label.startswith('◦') for label in labels))
            self.assertTrue(all('대표발의' not in row[0] and ' / ' not in row[2] for row in result['rows']))
            self.assertIsNotNone(result['xlsx'])
