"""Explicit, resumable model preparation; completed snapshots work offline."""
import json
import os

# hf-xet reads its settings when first used. Configure before importing Hub
# or sentence-transformers; preserve explicit user overrides.
os.environ.setdefault('HF_XET_HIGH_PERFORMANCE','1')

from pathlib import Path
from threading import RLock
from lawtool import ROOT
from webapp.download_progress import DownloadProgress

EMBED_MODEL='dragonkue/snowflake-arctic-embed-l-v2.0-ko'
MARKER=ROOT/'models'/'embedding-ready.json'
DOWNLOAD_LOCK=RLock()
PATTERNS=['*.json','*.safetensors','*.model','*.txt']
IGNORE=['onnx/*','openvino/*']
DEFAULT_DOWNLOAD_WORKERS=8


def download_workers():
    """Return a bounded parallel-download setting with a safe override."""
    try:
        value=int(os.environ.get('EMBED_DOWNLOAD_WORKERS',DEFAULT_DOWNLOAD_WORKERS))
    except ValueError:
        value=DEFAULT_DOWNLOAD_WORKERS
    return max(1,min(32,value))


def valid_files(folder,files):
    if not files or not any(name.endswith('.safetensors') for name in files): return False
    for name in ('config.json','modules.json','tokenizer_config.json'):
        if name not in files: return False
    for name,size in files.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts: return False
        path=folder/relative
        if not path.is_file() or size<=0 or path.stat().st_size!=size: return False
    return True


def cached_model_path():
    """No network, imports of torch, or multi-GB hashing on UI reruns."""
    try:
        record=json.loads(MARKER.read_text(encoding='utf-8'))
        folder=Path(record['path'])
        if record['model']==EMBED_MODEL and valid_files(folder,record['files']):
            return str(folder)
    except (OSError,ValueError,KeyError,TypeError): pass
    return None


def download_error(error):
    """Expose categories without leaking URLs, headers or credentials."""
    import httpx
    from webapp.resumable_download import DownloadError
    if isinstance(error,DownloadError): return str(error)
    status=getattr(getattr(error,'response',None),'status_code',None)
    if status in (401,403): return '인증 또는 접근 거부: Hugging Face 토큰의 유효성과 읽기 권한을 확인하세요.'
    if status==429: return '요청 제한: Hugging Face 토큰을 입력하거나 잠시 후 다시 시도하세요.'
    if isinstance(error,httpx.TimeoutException): return '서버 응답 시간 초과: 네트워크·프록시 연결을 확인하고 다시 시도하세요.'
    if 'CERTIFICATE_VERIFY_FAILED' in str(error): return 'SSL 인증서 확인 실패: PC의 인증서·사내 프록시 설정을 확인하세요.'
    if isinstance(error,httpx.RemoteProtocolError): return '다운로드 연결이 중간에 끊겼습니다. 다시 시도하세요.'
    if isinstance(error,httpx.ConnectError): return '서버 연결 실패: Hugging Face 및 모델 CDN 접근을 확인하세요.'
    if isinstance(error,OSError) and error.errno==28: return '모델 저장 디스크 공간이 부족합니다.'
    return '인터넷·디스크 공간을 확인한 뒤 다시 시도하세요. 완료되지 않은 모델은 사용하지 않습니다.'


def ensure_embedding_files(notify=lambda message: None,hf_token=None,stop=None):
    notify('임베딩 모델 다운로드 상태 확인 중')
    with DOWNLOAD_LOCK:
        cached=cached_model_path()
        if cached:
            notify('임베딩 모델 다운로드 완료 상태 · 기존 파일 사용')
            return cached
        try:
            from huggingface_hub import snapshot_download, get_token, constants
        except ImportError:
            raise ValueError('부서 추천 패키지를 설치하세요: pip install -r requirements-departments.txt') from None
        try:
            notify('모델 파일 목록 확인 중 · 기존 캐시가 있으면 재사용합니다')
            workers=download_workers()
            # Hub 1.x buffers 10 MB before writing/reporting HTTP progress.
            # Smaller chunks also preserve more progress on interrupted links.
            constants.DOWNLOAD_CHUNK_SIZE=256*1024
            token=(hf_token or '').strip() or get_token() or False
            notify('Hugging Face 인증 다운로드 사용' if token else 'Hugging Face 공개 다운로드 사용 · 토큰 없이 진행')
            plan=snapshot_download(EMBED_MODEL,allow_patterns=PATTERNS,ignore_patterns=IGNORE,
                                   dry_run=True,token=token,max_workers=workers)
            if not plan: raise ValueError('Empty model')
            revisions={entry.commit_hash for entry in plan}
            if len(revisions)!=1: raise ValueError('Mixed revisions')
            remaining=sum(entry.file_size for entry in plan if entry.will_download)
            total=sum(entry.file_size for entry in plan)
            ranged=os.environ.get('EMBED_DOWNLOAD_MODE','ranges')=='ranges'
            tracker=DownloadProgress(total,0 if ranged else total-remaining,notify)
            notify(f'임베딩 모델 다운로드 중 · 필요한 용량 약 {remaining/1024**2:,.0f} MB · 완료될 때까지 기다려주세요'
                   if remaining else '기존 모델 캐시 확인 중 · 추가 다운로드 없음')
            tracker.update('completed',0)
            if ranged:
                from webapp.resumable_download import prepare_snapshot
                folder=prepare_snapshot(EMBED_MODEL,next(iter(revisions)),plan,ROOT/'models'/'embedding',
                    token,tracker,notify,workers,stop)
            else:
                folder=Path(snapshot_download(EMBED_MODEL,revision=next(iter(revisions)),
                    allow_patterns=PATTERNS,ignore_patterns=IGNORE,token=token,max_workers=workers,
                    tqdm_class=tracker.tqdm_class()))
            files={entry.filename:entry.file_size for entry in plan}
            notify('다운로드 파일 검사 중')
            if not valid_files(folder,files): raise ValueError('Incomplete model')
            MARKER.parent.mkdir(parents=True,exist_ok=True)
            temporary=MARKER.with_suffix('.tmp')
            temporary.write_text(json.dumps({'model':EMBED_MODEL,'path':str(folder),'files':files}),encoding='utf-8')
            temporary.replace(MARKER)
            notify('임베딩 모델 다운로드 완료')
            return str(folder)
        except Exception as error:
            raise ValueError('임베딩 모델 다운로드 실패: '+download_error(error)) from None
