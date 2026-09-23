import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from queue import Queue
from unittest.mock import patch, Mock
from openpyxl import load_workbook
from lawtool import ROOT
from webapp.jobs import process


class JobRecoveryTests(unittest.TestCase):
    def test_good_summary_saved_despite_corrupt_pdf_and_zip(self):
        hwpx=io.BytesIO()
        with zipfile.ZipFile(hwpx,'w') as z:
            z.writestr('Contents/section0.xml','<section><p><t>지원법 일부개정법률안</t></p><p><t>주요내용</t></p><p><t>지원 대상 기관의 범위를 확대함</t></p></section>')
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:
            z.writestr('요청공문.pdf',b'%PDF-1.4\nbroken')
            z.writestr('broken.zip',b'broken')
            z.writestr('법안.hwpx',hwpx.getvalue())
        engine=Mock(audit=[])
        engine.summarize_document.return_value=['지원 대상 기관 범위 확대']
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            shutil.copy2(ROOT/'config.json',directory/'config.json')
            with patch('webapp.jobs.ROOT',directory),patch('webapp.jobs.ApiSummarizer',return_value=engine):
                result=process([('묶음.zip',outer.getvalue())],'test-key',Queue())
            self.assertEqual(result['success'],1)
            self.assertEqual(len(result['issues']),2)
            self.assertEqual(result['rows'][0][2:],['','',''])
            report=json.loads(result['report'])
            self.assertNotIn('test-key',result['report'].decode())
            self.assertEqual(len(report['files']),1)
            workbook=load_workbook(io.BytesIO(result['xlsx']))
            self.assertEqual(workbook.active.cell(2,1).value,'지원법')
            self.assertIsNone(workbook.active.cell(2,5).value)
            engine.summarize_document.assert_called_once()
