import unittest
from unittest.mock import patch
from webapp.download_progress import DownloadProgress, progress_view, duration


class DownloadProgressTests(unittest.TestCase):
    def test_bytes_speed_eta_and_stall(self):
        events=[]
        with patch('webapp.download_progress.time.monotonic',return_value=100):
            tracker=DownloadProgress(1000,100,events.append)
        with patch('webapp.download_progress.time.monotonic',return_value=101):
            tracker.update('completed',100)
        with patch('webapp.download_progress.time.monotonic',return_value=102):
            tracker.update('transfer',200)
        with patch('webapp.download_progress.time.monotonic',return_value=103):
            tracker.update('completed',300)
        event=events[-1]
        self.assertEqual(event['received'],400)
        self.assertEqual(event['eta'],6)
        self.assertAlmostEqual(event['speed'],200/3)
        self.assertEqual(progress_view(event,103)['fraction'],0.4)
        self.assertEqual(progress_view(event,120)['eta'],'계산 중')
        self.assertEqual(progress_view(event,120)['speed'],'측정 대기')

    def test_initial_and_overflow(self):
        events=[]
        tracker=DownloadProgress(100,0,events.append)
        tracker.update('completed',0)
        self.assertIsNone(events[-1]['eta'])
        tracker.last_emit=0
        tracker.update('completed',999)
        self.assertEqual(events[-1]['received'],100)
        self.assertEqual(duration(3661),'1시간 1분 1초')

    def test_restored_parts_do_not_inflate_download_rate(self):
        events=[]
        with patch('webapp.download_progress.time.monotonic',return_value=100):
            tracker=DownloadProgress(1000,0,events.append)
            tracker.update('completed',500)
            tracker.reset_rate()
        with patch('webapp.download_progress.time.monotonic',return_value=110):
            tracker.update('completed',600)
        self.assertEqual(events[-1]['eta'],40)

    def test_status_distinguishes_transfer_from_no_reports(self):
        event={'received':10,'total':100,'started':0,'updated':1,
               'transfer_updated':39,'eta':9,'speed':2}
        self.assertIn('데이터 전송 중',progress_view(event,40)['status'])
        self.assertIn('진행 보고가 없습니다',progress_view(event,80)['status'])
        self.assertEqual(progress_view(event,80)['speed'],'측정 대기')

    def test_real_tqdm_hooks_ignore_file_counts(self):
        events=[]
        tracker=DownloadProgress(1000,0,events.append)
        bar_type=tracker.tqdm_class()
        with bar_type(desc='Downloading bytes',total=1000,unit='B') as bar:
            bar.update(100)
        tracker.last_emit=0
        with bar_type(desc='Reconstructing (incomplete total...)',total=1000,unit='B') as bar:
            bar.update(200)
        self.assertEqual(events[-1]['transferred'],100)
        self.assertEqual(events[-1]['received'],200)
        previous=len(events)
        with bar_type(desc='Fetching files',total=1) as bar:
            bar.update(1)
        self.assertEqual(len(events),previous)
