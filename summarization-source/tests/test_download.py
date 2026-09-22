import contextlib, io, json, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
from tools import download_model as d

class DownloadTests(unittest.TestCase):
    def test_activation_preserves_settings(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'config.json').write_text('{"n_ctx":4096,"model_path":"old"}')
            f=root/'models/test.gguf'; f.parent.mkdir(); f.write_bytes(b'GGUFtest')
            with patch.object(d,'ROOT',root): d.activate(f)
            cfg=json.loads((root/'config.json').read_text())
            self.assertEqual(cfg['n_ctx'],4096); self.assertEqual(cfg['model_path'],'models/test.gguf')
            f.write_bytes(b'bad')
            with patch.object(d,'ROOT',root), self.assertRaises(ValueError): d.activate(f)
            self.assertEqual(json.loads((root/'config.json').read_text()),cfg)
    def test_token_blank_and_hidden(self):
        with patch.object(d.getpass,'getpass',return_value=''),contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(d.token_prompt(),False)
        out=io.StringIO()
        with patch.object(d.getpass,'getpass',return_value='hf_TEST_SECRET'),contextlib.redirect_stdout(out):
            self.assertEqual(d.token_prompt(),'hf_TEST_SECRET')
        self.assertNotIn('hf_TEST_SECRET',out.getvalue())
    def test_download_and_no_secret_persistence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'config.json').write_text('{"n_ctx":4096}')
            received=[]
            class Api:
                def __init__(self,**kw): received.append(kw['token'])
                def model_info(self,**kw):
                    received.append(kw['token'])
                    return types.SimpleNamespace(sha='a'*40,siblings=[types.SimpleNamespace(rfilename='test.gguf',size=4)])
            def fetch(**kw):
                received.append(kw['token']); f=kw['local_dir']/kw['filename']
                f.parent.mkdir(parents=True); f.write_bytes(b'GGUF');return str(f)
            hf=types.ModuleType('huggingface_hub'); hf.HfApi=Api;hf.hf_hub_download=fetch
            utils=types.ModuleType('huggingface_hub.utils');utils.logging=types.SimpleNamespace(set_verbosity_error=lambda:None)
            out=io.StringIO()
            with patch.dict('sys.modules',{'huggingface_hub':hf,'huggingface_hub.utils':utils}), patch.object(d,'ROOT',root), patch('builtins.input',side_effect=['owner/model','','']),patch.object(d.getpass,'getpass',return_value='hf_TEST_SECRET'),contextlib.redirect_stdout(out):
                self.assertEqual(d.download(),0)
            self.assertEqual(received,['hf_TEST_SECRET']*3)
            self.assertNotIn('hf_TEST_SECRET',out.getvalue())
            self.assertNotIn('hf_TEST_SECRET',(root/'config.json').read_text())
            self.assertEqual(json.loads((root/'config.json').read_text())['model_source']['repo_id'],'owner/model')
