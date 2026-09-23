import tempfile
import io
import zipfile
import unittest
from pathlib import Path
from unittest.mock import patch
from webapp.packages import prepare, unpack


class SkipErrorsTests(unittest.TestCase):
    def test_bad_pdf_and_hwp_do_not_stop_good_document(self):
        issues=[]
        with tempfile.TemporaryDirectory() as tmp:
            with patch('webapp.packages.read_hwpx',side_effect=[ValueError('bad file'),['지원법','주요내용','지원 범위 확대']]):
                groups,ignored=prepare([('bad.pdf',b'not a pdf'),('bad.hwpx',b'bad'),('good.hwpx',b'good')],Path(tmp),{},issues)
        self.assertEqual(len(groups),1)
        self.assertIsNone(groups[0]['letter'])
        self.assertEqual(groups[0]['documents'][0]['name'],'good.hwpx')
        self.assertEqual(len(issues),2)
        self.assertEqual([issue['file'] for issue in issues],
                         ['loose / bad.hwpx','loose / bad.pdf'])

    def test_all_failed_returns_issues(self):
        issues=[]
        with tempfile.TemporaryDirectory() as tmp:
            groups,_=prepare([('bad.pdf',b'not pdf')],Path(tmp),{},issues)
        self.assertEqual(groups,[])
        self.assertEqual(len(issues),1)

    def test_corrupt_nested_zip_does_not_stop_siblings(self):
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('broken.zip',b'not zip')
            z.writestr('good.hwpx',b'good')
        issues=[]
        docs=unpack([('outer.zip',archive.getvalue()),('another.zip',b'bad')],issues)
        self.assertEqual([d['name'] for d in docs],['good.hwpx'])
        self.assertEqual(len(issues),2)
        self.assertIn('broken.zip',issues[0]['file'])

    def test_safety_violation_is_not_silently_skipped(self):
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z: z.writestr('../bad.hwpx',b'bad')
        with self.assertRaises(ValueError): unpack([('bad.zip',archive.getvalue())],[])

    def test_filled_opinion_is_not_skipped_based_on_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('webapp.packages.read_hwpx',return_value=['지원법','주요내용','지원범위 확대']):
                groups,ignored=prepare([('검토의견서.hwpx',b'data')],Path(tmp),{},[])
        self.assertEqual(len(groups),1)
        self.assertEqual(ignored,[])
