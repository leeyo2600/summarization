import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

from openpyxl import load_workbook
from lawtool import ROOT
from webapp.jobs import build_units, process
from webapp.packages import unpack
from webapp.display import unit_labels


def archive(entries):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        for name,data in entries:
            z.writestr(name,data)
    return buffer.getvalue()


def bill(law):
    return archive([('Contents/section0.xml',
        f'<section><p><t>{law} 일부개정법률안</t></p><p><t>주요내용</t></p>'
        '<p><t>지원 대상 기관의 범위를 확대함</t></p></section>')])


class OutputOrderTests(unittest.TestCase):
    def test_duplicate_law_labels(self):
        units=[{'law':'전자정부법','representative':'김영진'} for _ in range(3)]
        self.assertEqual(unit_labels(units,'37'),['37-1. 전자정부법','37-2. 전자정부법','37-3. 전자정부법'])
        self.assertEqual(unit_labels(units[:1],'37'),['37. 전자정부법'])
        self.assertEqual(unit_labels(units,'10-2'),['10-2-1. 전자정부법','10-2-2. 전자정부법','10-2-3. 전자정부법'])
        self.assertEqual(unit_labels([units[0],{'law':'다른법'},units[1]],'37'),
                         ['37-1. 전자정부법','37. 다른법','37-2. 전자정부법'])

    def test_duplicate_bills_written_as_separate_numbered_rows(self):
        docs=[{'name':f'{i}.hwpx','source':f'{i}.hwpx','scope':('0','37. 의견조회.zip'),
               'lines':['전자정부법 일부개정법률안','주요내용','지원 확대']} for i in range(3)]
        units=[{'law':'전자정부법','representative':'김영진','bill_number':str(i),
                'sections':['지원 확대'],'documents':[doc]} for i,doc in enumerate(docs)]
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); shutil.copy2(ROOT/'config.json',directory/'config.json')
            engine=Mock(audit=[]); engine.summarize_document.return_value=['지원 확대']
            with patch('webapp.jobs.ROOT',directory),patch('webapp.jobs.ApiSummarizer',return_value=engine),\
                 patch('webapp.jobs.prepare',return_value=([{'name':'묶음','letter':None,'documents':docs}],[])),\
                 patch('webapp.jobs.build_units',return_value=(units,[])):
                result=process([],'key',Queue())
            book=load_workbook(io.BytesIO(result['xlsx']))
            self.assertEqual([row[0] for row in book.active.iter_rows(min_row=2,values_only=True)],
                             ['37-1. 전자정부법','37-2. 전자정부법','37-3. 전자정부법'])
            book.close()
            self.assertEqual([u['bill_number'] for u in json.loads(result['report'])['files'][0]['units']],['0','1','2'])

    def test_nested_archives_ignore_upload_and_entry_order(self):
        files=[('10.zip',archive([('법안.hwpx',b'x')])),
               ('2.zip',archive([('10/첨부.zip',archive([('2.hwpx',b'x'),('1.hwpx',b'x')])),
                                  ('2/법안.hwpx',b'x')]))]
        paths=[doc['source'].split(' / ',1)[1] for doc in unpack(files)]
        self.assertEqual(paths,['2.zip / 2 / 법안.hwpx',
            '2.zip / 10 / 첨부.zip / 1.hwpx','2.zip / 10 / 첨부.zip / 2.hwpx',
            '10.zip / 법안.hwpx'])

    def test_units_follow_attachment_numbers(self):
        docs=[{'name':name,'source':name,'scope':('loose',),
               'lines':[law+' 일부개정법률안','주요내용','지원 확대']}
              for name,law in [('10.hwpx','교육법'),('2.hwpx','지원법')]]
        units,warnings=build_units({'documents':docs})
        self.assertEqual([unit['law'] for unit in units],['지원법','교육법'])
        self.assertFalse(warnings)

    def test_preview_download_disk_and_report_keep_same_order(self):
        entries=[('10-2.hwpx',bill('교육법')),('2.hwpx',bill('지원법')),
                 ('3.hwpx',b'broken'),('10-1.hwpx',bill('보육법')),
                 ('01.hwpx',bill('안전법'))]
        expected=['안전법','지원법','보육법','교육법']
        for files in (entries,[('통합.zip',archive(entries))]):
            with self.subTest(zipped=len(files)==1), tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp)
                shutil.copy2(ROOT/'config.json',directory/'config.json')
                engine=Mock(audit=[])
                engine.summarize_document.return_value=['지원 확대']
                with patch('webapp.jobs.ROOT',directory),patch('webapp.jobs.ApiSummarizer',return_value=engine):
                    result=process(files,'test-key',Queue())
                self.assertEqual([row[0] for row in result['rows']],expected)
                self.assertEqual(len(result['issues']),1)
                self.assertEqual([entry['laws'][0] for entry in json.loads(result['report'])['files']],expected)
                disk=Path(result['folder'])/'법령_주요내용_요약.xlsx'
                self.assertEqual(disk.read_bytes(),result['xlsx'])
                workbook=load_workbook(io.BytesIO(result['xlsx']))
                self.assertEqual([row[0].value for row in list(workbook.active.rows)[1:]],expected)
                workbook.close()
