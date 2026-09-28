import hashlib
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

import httpx
from filelock import FileLock
from webapp import resumable_download as download


class ResumableTests(unittest.TestCase):
    def test_saved_ranges_survive_interruption_and_restart(self):
        data=b'abcdefghijkl'; digest=hashlib.sha256(data).hexdigest()
        requested=[]; cancel=Event(); events=[]
        def server(request):
            start,end=map(int,request.headers['range'][6:].split('-'))
            requested.append(start)
            return httpx.Response(206,headers={'Content-Range':f'bytes {start}-{end}/{len(data)}'},content=data[start:end+1])
        def progress(done,received):
            events.append((done,received))
            if done==4: cancel.set()
        client_type=httpx.Client
        with tempfile.TemporaryDirectory() as tmp,patch.object(download,'CHUNK_SIZE',4),patch.object(download.httpx,'Client',side_effect=lambda **kw:client_type(transport=httpx.MockTransport(server),**kw)):
            target=Path(tmp)/'model.safetensors'
            with self.assertRaisesRegex(ValueError,'중단'):
                download.range_file('https://huggingface.co/test',target,len(data),digest,False,progress,1,cancel)
            self.assertFalse(target.exists())
            self.assertEqual(requested,[0])
            download.range_file('https://huggingface.co/test',target,len(data),digest,False,lambda *args:None,1)
            self.assertEqual(requested,[0,4,8])
            self.assertEqual(target.read_bytes(),data)

    def test_wrong_range_never_publishes_model(self):
        def server(request): return httpx.Response(200,content=b'abcd')
        self.assert_invalid_server(server,'파일 구간')

    def test_hash_mismatch_is_quarantined_and_next_attempt_can_retry(self):
        def server(request): return httpx.Response(206,headers={'Content-Range':'bytes 0-3/4'},content=b'xxxx')
        self.assert_invalid_server(server,'SHA-256')

    def assert_invalid_server(self,server,message):
        client_type=httpx.Client
        with tempfile.TemporaryDirectory() as tmp,patch.object(download,'CHUNK_SIZE',4),patch.object(download.httpx,'Client',side_effect=lambda **kw:client_type(transport=httpx.MockTransport(server),**kw)):
            target=Path(tmp)/'model.safetensors'
            with self.assertRaisesRegex(ValueError,message):
                download.range_file('https://huggingface.co/test',target,4,hashlib.sha256(b'abcd').hexdigest(),False,lambda *args:None,1)
            self.assertFalse(target.exists())

    def test_cross_origin_redirect_drops_token(self):
        calls=[]
        def server(request):
            calls.append(request)
            if request.url.host=='huggingface.co':
                return httpx.Response(302,headers={'Location':'https://cdn.example.test/model'})
            self.assertNotIn('authorization',request.headers)
            return httpx.Response(206,headers={'Content-Range':'bytes 0-3/4'},content=b'abcd')
        client_type=httpx.Client
        with tempfile.TemporaryDirectory() as tmp,patch.object(download.httpx,'Client',side_effect=lambda **kw:client_type(transport=httpx.MockTransport(server),**kw)):
            target=Path(tmp)/'model'
            download.range_file('https://huggingface.co/test',target,4,hashlib.sha256(b'abcd').hexdigest(),'hf_test',lambda *args:None,1)
            self.assertEqual(calls[0].headers['authorization'],'Bearer hf_test')
            self.assertEqual(target.read_bytes(),b'abcd')

    def test_connection_break_resumes_inside_the_same_range(self):
        data=b'a'*(128*1024); requests=[]
        class BrokenStream(httpx.SyncByteStream):
            def __iter__(self):
                yield data[:65536]
                raise httpx.RemoteProtocolError('broken connection')
        def server(request):
            requests.append(request.headers['range'])
            if len(requests)==1:
                return httpx.Response(206,headers={'Content-Range':f'bytes 0-131071/{len(data)}'},stream=BrokenStream())
            return httpx.Response(206,headers={'Content-Range':f'bytes 65536-131071/{len(data)}'},content=data[65536:])
        client_type=httpx.Client
        with tempfile.TemporaryDirectory() as tmp,patch.object(download.httpx,'Client',side_effect=lambda **kw:client_type(transport=httpx.MockTransport(server),**kw)):
            target=Path(tmp)/'model'
            download.range_file('https://huggingface.co/test',target,len(data),hashlib.sha256(data).hexdigest(),False,lambda *args:None,1)
            self.assertEqual(requests,['bytes=0-131071','bytes=65536-131071'])
            self.assertEqual(target.read_bytes(),data)

    def test_active_download_fails_without_waiting_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'model'
            with FileLock(str(target)+'.lock'):
                with self.assertRaisesRegex(ValueError,'다른 프로세스'):
                    download.range_file('https://huggingface.co/test',target,4,'a'*64,False,lambda *args:None,1)
