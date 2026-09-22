"""Edit REPO_ID and FILENAME to download a different single-file GGUF."""
from pathlib import Path
from huggingface_hub import hf_hub_download
from tools.download_model import token_prompt, activate
import os

ROOT = Path(__file__).resolve().parent
REPO_ID = "mykor/A.X-4.0-Light-gguf"
FILENAME = "A.X-4.0-Light-Q4_K_M.gguf"

def main():
    os.environ["HF_DEBUG"] = "0"
    from huggingface_hub.utils import logging
    logging.set_verbosity_error()
    token = token_prompt()
    try:
        print("Downloading:", REPO_ID, FILENAME, flush=True)
        path = hf_hub_download(repo_id=REPO_ID, filename=FILENAME,
            local_dir=ROOT/"models"/REPO_ID, token=token,
            endpoint="https://huggingface.co")
        activate(path, {"type":"huggingface", "repo_id":REPO_ID,"filename":FILENAME})
        print("Download complete. Run lawtool.py next.")
        return 0
    except Exception as error:
        # Avoid printing HTTP headers or credentials in exceptions.
        print("Download failed:", type(error).__name__)
        print("Check repository, filename, token permissions and network.")
        return 1
    finally:
        token = None

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.")
