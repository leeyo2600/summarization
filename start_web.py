"""Single entry point for the API upload UI; no local model loading."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
root=Path(__file__).resolve().parent
python=root/'.venv'/'Scripts'/'python.exe'
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='법령 요약 웹앱 실행')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--http',action='store_true',help='Hugging Face의 일반 HTTP 다운로드 사용')
    mode.add_argument('--xet',action='store_true',help='Hugging Face의 Xet 다운로드 사용')
    args=parser.parse_args()
    # The Streamlit child inherits this before Hugging Face is imported.
    os.environ['EMBED_DOWNLOAD_MODE']='hub' if args.http or args.xet else 'ranges'
    os.environ['HF_HUB_DISABLE_XET']='0' if args.xet else '1'
    os.environ.setdefault('HF_XET_HIGH_PERFORMANCE','1')
    raise SystemExit(subprocess.call([str(python) if python.exists() else sys.executable,'-m','streamlit','run',str(root/'app.py'),'--server.address','127.0.0.1','--browser.gatherUsageStats','false']))
