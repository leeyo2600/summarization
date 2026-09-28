import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import Future
from queue import Queue
from streamlit.testing.v1 import AppTest
from lawtool import ROOT
from webapp import embedding_files as assets


class EmbeddingFilesTests(unittest.TestCase):
    def setUp(self):
        environment=patch.dict('os.environ',{'EMBED_DOWNLOAD_MODE':'hub'})
        environment.start(); self.addCleanup(environment.stop)

    def test_download_workers_default_override_and_bounds(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(assets.download_workers(),8)
        for configured,expected in [('16',16),('0',1),('100',32),('invalid',8)]:
            with self.subTest(configured=configured), \
                 patch.dict('os.environ',{'EMBED_DOWNLOAD_WORKERS':configured}):
                self.assertEqual(assets.download_workers(),expected)

    def test_download_then_offline_skip_and_missing_file_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'snapshot'; folder.mkdir()
            files={'config.json':2,'modules.json':2,'tokenizer_config.json':2,'model.safetensors':3}
            for name,size in files.items(): (folder/name).write_bytes(b'x'*size)
            plan=[SimpleNamespace(filename=name,file_size=size,commit_hash='a'*40,will_download=True)
                  for name,size in files.items()]
            with patch.object(assets,'MARKER',Path(tmp)/'marker.json'),\
                 patch('huggingface_hub.snapshot_download',side_effect=[plan,str(folder)]) as download:
                messages=[]
                self.assertEqual(assets.ensure_embedding_files(messages.append),str(folder))
                self.assertEqual(download.call_count,2)
                self.assertEqual(download.call_args_list[0].kwargs['max_workers'],8)
                self.assertEqual(download.call_args_list[1].kwargs['max_workers'],8)
                download.reset_mock()
                self.assertEqual(assets.ensure_embedding_files(messages.append),str(folder))
                download.assert_not_called()
                self.assertTrue(any('다운로드 중' in m for m in messages))
                (folder/'model.safetensors').unlink()
                self.assertIsNone(assets.cached_model_path())

    def test_failure_never_marks_complete_and_retry_allowed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(assets,'MARKER',Path(tmp)/'marker.json'),\
             patch('huggingface_hub.snapshot_download',side_effect=OSError('private connection detail')) as download:
            for attempt in range(2):
                with self.assertRaisesRegex(ValueError,'다운로드 실패'):
                    assets.ensure_embedding_files()
                self.assertFalse(assets.MARKER.exists())
            self.assertEqual(download.call_count,2)

    def test_ranges_pipeline_validates_then_works_offline(self):
        import hashlib
        import httpx
        from webapp import resumable_download
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cache=root/'cache'; cache.mkdir()
            files={'config.json':2,'modules.json':2,'tokenizer_config.json':2,'model.safetensors':4}
            for name,size in files.items():
                if not name.endswith('.safetensors'): (cache/name).write_bytes(b'{}')
            plan=[SimpleNamespace(filename=name,file_size=size,commit_hash='a'*40,will_download=name.endswith('.safetensors')) for name,size in files.items()]
            def lookup(model,name,**kwargs): return str(cache/name) if (cache/name).exists() else None
            def server(request): return httpx.Response(206,headers={'Content-Range':'bytes 0-3/4'},content=b'abcd')
            client_type=httpx.Client
            with patch.dict('os.environ',{'EMBED_DOWNLOAD_MODE':'ranges'}), patch.object(assets,'ROOT',root), patch.object(assets,'MARKER',root/'marker.json'), patch('huggingface_hub.get_token',return_value=None), patch('huggingface_hub.snapshot_download',return_value=plan) as snapshot, patch('huggingface_hub.try_to_load_from_cache',side_effect=lookup), patch('huggingface_hub.get_hf_file_metadata',return_value=SimpleNamespace(size=4,commit_hash='a'*40,etag=hashlib.sha256(b'abcd').hexdigest())), patch.object(resumable_download.httpx,'Client',side_effect=lambda **kw:client_type(transport=httpx.MockTransport(server),**kw)):
                folder=assets.ensure_embedding_files()
                self.assertEqual((Path(folder)/'model.safetensors').read_bytes(),b'abcd')
                self.assertEqual(assets.ensure_embedding_files(),folder)
                snapshot.assert_called_once()

    def test_token_is_used_for_plan_and_download_without_persistence(self):
        for explicit,saved,expected in [('hf_input','hf_saved','hf_input'),(None,'hf_saved','hf_saved'),(None,None,False)]:
            with self.subTest(explicit=bool(explicit),saved=bool(saved)), tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)/'snapshot'; folder.mkdir()
                files={'config.json':2,'modules.json':2,'tokenizer_config.json':2,'model.safetensors':3}
                for name,size in files.items(): (folder/name).write_bytes(b'x'*size)
                plan=[SimpleNamespace(filename=name,file_size=size,commit_hash='a'*40,will_download=True) for name,size in files.items()]
                with patch.object(assets,'MARKER',Path(tmp)/'marker.json'), patch('huggingface_hub.get_token',return_value=saved), patch('huggingface_hub.snapshot_download',side_effect=[plan,str(folder)]) as fetch:
                    events=[]
                    assets.ensure_embedding_files(events.append,hf_token=explicit)
                    self.assertTrue(all(call.kwargs['token']==expected for call in fetch.call_args_list))
                    self.assertNotIn('hf_input',assets.MARKER.read_text())
                    self.assertNotIn('hf_saved',assets.MARKER.read_text())
                    self.assertNotIn('hf_input',str(events))

    def test_errors_are_actionable_and_redacted(self):
        import httpx
        for status,expected in [(401,'인증'),(403,'접근'),(429,'요청 제한')]:
            response=httpx.Response(status,request=httpx.Request('GET','https://example.test'))
            message=assets.download_error(httpx.HTTPStatusError('hf_secret',request=response.request,response=response))
            self.assertIn(expected,message)
            self.assertNotIn('hf_secret',message)
        self.assertIn('시간 초과',assets.download_error(httpx.ReadTimeout('hf_secret')))
        self.assertIn('끊겼습니다',assets.download_error(httpx.RemoteProtocolError('hf_secret')))

    def test_luna_ui_does_not_need_embedding_cache_or_download(self):
        with patch('webapp.embedding_files.cached_model_path') as cache,\
             patch('webapp.embedding_files.ensure_embedding_files') as download:
            app=AppTest.from_file(str(ROOT/'app.py')).run()
            self.assertFalse(app.exception)
            cache.assert_not_called(); download.assert_not_called()
            self.assertFalse(any(button.key=='download_embedding' for button in app.button))
            self.assertFalse(any(item.key=='hf_token' for item in app.text_input))
            self.assertTrue(any('전체 업무분장' in caption.value for caption in app.caption))
