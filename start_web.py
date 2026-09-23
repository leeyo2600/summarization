"""Single entry point for the API upload UI; no local model loading."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parent
python=root/'.venv'/'Scripts'/'python.exe'
if __name__=='__main__':
    raise SystemExit(subprocess.call([str(python) if python.exists() else sys.executable,'-m','streamlit','run',str(root/'app.py'),'--server.address','127.0.0.1','--browser.gatherUsageStats','false']))
