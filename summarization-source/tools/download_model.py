"""Interactive GGUF downloader / selector for the VS Code terminal."""
from pathlib import Path
import getpass
import json
import os
import re
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = 'mykor/A.X-4.0-Light-gguf'
DEFAULT_FILE = 'A.X-4.0-Light-Q4_K_M.gguf'


def choose(entries, default=0):
    for i, label in enumerate(entries, 1):
        print(f'  {i}. {label}')
    while True:
        answer = input(f'번호 선택 [Enter={default+1}]: ').strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(entries):
            return int(answer)-1
        print('목록에 있는 번호를 입력하세요.')


def token_prompt():
    # Do not permit getpass to fall back to echoed standard input.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            token = getpass.getpass('Hugging Face 토큰 (숨김 입력 / 없으면 Enter): ').strip()
        except getpass.GetPassWarning:
            raise RuntimeError('숨김 입력을 지원하지 않습니다. VS Code의 터미널에서 실행하세요.') from None
    print('인증: 입력 토큰 사용 (저장 안 함)' if token else '인증: 토큰 없이 진행')
    # False explicitly disables implicit cached/environment authentication.
    return token if token else False


def activate(path, metadata=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('모델 파일이 없습니다.')
    with path.open('rb') as f:
        if f.read(4) != b'GGUF':
            raise ValueError('GGUF 파일 헤더가 아닙니다. 모델 설정은 변경하지 않았습니다.')
    cfg_path = ROOT/'config.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
    try:
        cfg['model_path'] = path.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        cfg['model_path'] = path.as_posix()
    cfg['model_source'] = metadata or {'type': 'local'}
    tmp = cfg_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(tmp, cfg_path)
    print('요약에 사용할 모델 설정 완료:', cfg['model_path'])


def is_single_gguf(name):
    return name.lower().endswith('.gguf') and not re.search(r'-\d{5}-of-\d{5}\.gguf$', name, re.I)


def select_local():
    files = sorted(p for p in (ROOT/'models').rglob('*') if p.is_file() and is_single_gguf(p.name))
    if not files:
        print('models 폴더에 GGUF 파일이 없습니다. 먼저 다운로드하거나 직접 넣어주세요.')
        return
    index = choose([str(p.relative_to(ROOT)) for p in files])
    activate(files[index])


def download():
    # Import after suppressing verbose HTTP debug logs; never persist login credentials.
    os.environ['HF_DEBUG'] = '0'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import logging as hf_logging
    hf_logging.set_verbosity_error()
    cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    previous = cfg.get('model_source', {})
    default_repo = previous.get('repo_id', DEFAULT_REPO)
    repo = input(f'모델 저장소 [Enter={default_repo}]: ').strip() or default_repo
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or any(x in {'.','..'} for x in repo.split('/')):
        raise ValueError('저장소는 사용자명/모델명 형식으로 입력하세요. 예: mykor/A.X-4.0-Light-gguf')
    revision = input('버전/브랜치 [Enter=main]: ').strip() or 'main'
    token = token_prompt()  # Always prompt, even for public repositories.
    try:
        api = HfApi(endpoint='https://huggingface.co', token=token)
        info = api.model_info(repo_id=repo, revision=revision, files_metadata=True, token=token)
        files = sorted((f for f in info.siblings if is_single_gguf(f.rfilename)), key=lambda f:f.rfilename)
        if not files:
            raise ValueError('단일 GGUF 파일이 없습니다. safetensors 및 분할 GGUF 모델은 이 다운로드 메뉴에서 지원하지 않습니다.')
        labels = [f'{f.rfilename}  ({f.size/1e9:.2f} GB)' if f.size is not None else f.rfilename for f in files]
        preferred = previous.get('filename',DEFAULT_FILE) if repo == default_repo else ''
        default = next((i for i,f in enumerate(files) if f.rfilename == preferred),0)
        print('\n다운로드할 GGUF 파일:')
        selected = files[choose(labels,default)]
        print('다운로드:', repo, '/', selected.rfilename)
        # Repo and immutable commit separate models and revisions with identical filenames.
        commit = info.sha
        if not commit or not re.fullmatch(r'[A-Fa-f0-9]{7,64}',commit):
            raise ValueError('모델 버전 식별자를 확인하지 못했습니다.')
        owner,model = repo.split('/')
        destination = ROOT/'models'/owner/model/commit
        path = hf_hub_download(repo_id=repo, filename=selected.rfilename, revision=commit,
                               token=token, local_dir=destination, endpoint='https://huggingface.co')
        activate(path, {'type':'huggingface','repo_id':repo,'filename':selected.rfilename,'revision':commit})
        print('다운로드 완료. lawtool.py를 실행하면 선택한 모델을 사용합니다.')
    except Exception as exc:
        # Raw HTTP exceptions can contain URLs/headers; report only safe diagnostic fields.
        if isinstance(exc,ValueError):
            print(str(exc).replace(token,'[숨김]') if token else str(exc))
        else:
            response = getattr(exc,'response',None)
            status = getattr(response,'status_code',None)
            print('다운로드 실패:', type(exc).__name__, f'(HTTP {status})' if status else '')
            print('저장소/버전, 네트워크, 토큰의 읽기 권한을 확인하세요. 제한 모델은 사이트에서 이용 동의가 필요할 수 있습니다.')
        return 1
    finally:
        token = None
    return 0


def main():
    print('로컬 요약 모델 관리 — 토큰은 화면·파일에 기록하지 않습니다.')
    mode=choose(['Hugging Face에서 모델 다운로드 후 선택','이미 받은 GGUF 모델로 변경'])
    if mode == 0: return download()
    select_local()
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt,EOFError):
        print('\n취소했습니다.'); sys.exit(130)
    except Exception as exc:
        if isinstance(exc,(ValueError,RuntimeError)):
            print(str(exc))
        else:
            print('실행 실패:',type(exc).__name__, '— requirements.txt 설치 여부를 확인하세요.')
        sys.exit(1)
