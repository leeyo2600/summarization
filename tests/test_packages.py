import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from lawtool import ROOT, ReviewRequired
from webapp.packages import unpack, prepare, metadata, representative


class PackageTests(unittest.TestCase):
    def test_unsafe_path(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z: z.writestr('../escape.hwpx',b'x')
        with self.assertRaises(ReviewRequired): unpack([('test.zip',buffer.getvalue())])

    def test_sender_not_recipient_and_deadline_not_issue_date(self):
        text='보 건 복 지 부\n수신 다른부장관\n제목 「국민연금법」 의견조회\n1. 26.9.4.(금)까지 제출\n시행 국민연금정책과-2200 (2026.8.24.) 접수 법무담당관-1'
        result=metadata(text)
        self.assertEqual(result['agency'],'보건복지부')
        self.assertEqual(result['department'],'국민연금정책과')
        self.assertEqual(result['deadline'],'2026-09-04')
        self.assertEqual(representative(['박홍배 의원 대표발의','발의자: 다른의원']), '박홍배')

    def test_supplied_packages_and_outer_zip(self):
        paths=[p for p in Path('C:/Users/User/Desktop').glob('*.zip') if p.name.startswith(('2. ','12. ','18. '))]
        if len(paths)!=3: self.skipTest('실제 샘플 3건 없음')
        files=[(p.name,p.read_bytes()) for p in paths]
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:
            for name,data in files: z.writestr(name,data)
        cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
        for inputs in (files,[('통합.zip',outer.getvalue())]):
            with tempfile.TemporaryDirectory() as tmp:
                groups,ignored=prepare(inputs,Path(tmp),cfg)
                self.assertEqual(len(groups),3)
                self.assertEqual(len(ignored),3)
                actual={g['letter']['law']:(g['letter']['agency'],g['letter']['department'],g['letter']['deadline']) for g in groups}
                self.assertEqual(actual['국민연금법'],('보건복지부','국민연금정책과','2026-09-04'))
                self.assertEqual(actual['영유아특별회계법'],('교육부','영유아재정과','2026-08-28'))
                self.assertEqual(actual['공항안전 운영을 위한 공항운영검사 등의 업무지침'],('국토교통부','공항운영과','2026-09-03'))
