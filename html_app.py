"""Local HTML/Flask adapter for the unchanged document-processing pipeline."""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
from threading import Condition, RLock
import hmac
import secrets
import time

from flask import Flask, jsonify, render_template, request, send_file, session
from werkzeug.exceptions import RequestEntityTooLarge
from credential_store import CredentialStore, CredentialStoreError
from webapp.jobs import EXECUTOR, process_web
from webapp.llm_connection import LlmConnection, resolve_connection

ROOT = Path(__file__).resolve().parent
UPLOAD_LIMIT = 100 * 1024 * 1024


@dataclass
class Job:
    owner: str
    connection: LlmConnection
    id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    progress: Queue = field(default_factory=Queue)
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    last: tuple = (0, 0, '작업 준비 중')
    result: dict | None = None
    error: str = ''


def create_app(processor=None, executor=None, credentials_path=None):
    app = Flask(__name__, template_folder='templates', static_folder='assets', static_url_path='/assets')
    app.config.update(SECRET_KEY=secrets.token_bytes(32), MAX_CONTENT_LENGTH=UPLOAD_LIMIT + 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')
    processor = processor or process_web
    executor = executor or EXECUTOR
    jobs = {}
    lock = RLock()
    credentials = CredentialStore(credentials_path if credentials_path is not None else ROOT / '.local' / 'credentials.json')
    credential_revisions = {}
    credential_saved = Condition(lock)
    latest_credential_revision = -1

    def cleanup():
        expired = [key for key, job in jobs.items() if job.finished is not None and time.monotonic() - job.finished > 3600]
        completed = sorted((job for job in jobs.values() if job.finished is not None), key=lambda job: job.finished)
        expired += [job.id for job in completed[:max(0, len(completed) - 30)]]
        for key in expired:
            jobs.pop(key, None)

    def owned_job(job_id):
        job = jobs.get(job_id)
        return job if job and job.owner == session.get('owner') else None

    def snapshot(job):
        while True:
            try:
                job.last = job.progress.get_nowait()
            except Empty:
                break
        done, total, message = job.last
        if isinstance(message, dict):
            message = message.get('message', '작업 처리 중')
        payload = {'id': job.id, 'status': 'running' if job.finished is None else 'error' if job.error else 'complete',
                   'connection': {'provider': job.connection.provider, 'label': job.connection.label, 'model': job.connection.model},
                   'done': done, 'total': total, 'message': str(message),
                   'elapsed': max(0, (job.finished or time.monotonic()) - job.started), 'error': job.error}
        if job.result is not None:
            result = job.result
            payload['result'] = {key: result.get(key, default) for key, default in
                                 (('rows', []), ('issues', []), ('total', 0), ('success', 0), ('ignored_count', 0))}
            payload['result']['download'] = f'/api/jobs/{job.id}/download' if result.get('xlsx') else None
        return payload

    def run_job(job, files, key, law_oc):
        try:
            # The connection is immutable and belongs to this job, never a global switch.
            result = processor(files, key, job.progress, law_oc, connection=job.connection)
            with lock:
                job.result = result
        except Exception:
            with lock:
                job.error = '작업을 완료하지 못했습니다. 연결 상태와 저장 폴더 권한을 확인해주세요.'
        finally:
            with lock:
                job.finished = time.monotonic()

    @app.before_request
    def protect_local_app():
        if request.host.split(':')[0].lower() not in ('127.0.0.1', 'localhost'):
            return jsonify(error='허용되지 않은 호스트입니다.'), 400
        if request.method == 'POST' or request.path == '/api/credentials':
            expected = session.get('csrf', '')
            actual = request.headers.get('X-CSRF-Token', '')
            if not expected or not hmac.compare_digest(expected, actual):
                return jsonify(error='화면을 새로고침한 뒤 다시 시도해주세요.'), 403

    @app.after_request
    def response_headers(response):
        if not request.path.startswith('/assets/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(error='전체 파일 용량을 100MB 이하로 줄여주세요.'), 413

    @app.get('/_health')
    def health():
        return {'status': 'ok'}

    @app.get('/')
    def index():
        session.setdefault('owner', secrets.token_urlsafe(24))
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return render_template('index.html', csrf=session['csrf'])

    @app.get('/api/state')
    def state():
        with lock:
            cleanup()
            job = owned_job(session.get('job_id'))
            return jsonify(job=snapshot(job) if job else None)

    @app.get('/api/credentials')
    def load_credentials():
        try:
            pending = request.args.get('revision', type=int)
            client = (session.get('owner'), request.args.get('client_id', ''))
            if pending is not None and 0 <= pending <= 9007199254740991:
                # A refresh may arrive before the previous page's final save.
                with credential_saved:
                    credential_saved.wait_for(lambda: credential_revisions.get(client, -1) >= pending, timeout=1)
            return jsonify(credentials.load())
        except CredentialStoreError:
            return jsonify(error='저장된 API 키를 불러오지 못했습니다. 사용할 키를 다시 입력해주세요.'), 500

    @app.post('/api/credentials')
    def save_credentials():
        nonlocal latest_credential_revision
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error='저장할 API 키를 확인해주세요.'), 400
        key, law_oc = payload.get('api_key'), payload.get('law_oc')
        client_id, revision = payload.get('client_id'), payload.get('revision')
        if (not isinstance(key, str) or not isinstance(law_oc, str)
                or len(key) > 4096 or len(law_oc) > 4096
                or not isinstance(client_id, str) or not 1 <= len(client_id) <= 100
                or type(revision) is not int or not 0 <= revision <= 9007199254740991):
            return jsonify(error='저장할 API 키를 확인해주세요.'), 400
        try:
            with lock:
                client = (session.get('owner'), client_id)
                if revision <= credential_revisions.get(client, -1):
                    return jsonify(saved=True)
                if revision > latest_credential_revision:
                    credentials.save(key, law_oc)
                    latest_credential_revision = revision
                credential_revisions[client] = revision
                credential_saved.notify_all()
            return jsonify(saved=True)
        except CredentialStoreError:
            return jsonify(error='API 키를 저장하지 못했습니다. 프로그램 폴더의 쓰기 권한을 확인해주세요.'), 500

    @app.post('/api/jobs')
    def submit():
        try:
            connection = resolve_connection(request.form.get('provider', 'openai'))
        except ValueError as error:
            return jsonify(error=str(error)), 400
        key = request.form.get('api_key', '').strip()
        law_oc = request.form.get('law_oc', '').strip()
        if not key or not law_oc or request.form.get('consent') != 'true':
            return jsonify(error='OpenAI API 키, 국가법령정보 API 키, 외부 전송 동의를 확인해주세요.'), 400
        if len(key) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in key):
            return jsonify(error='OpenAI API 키를 공백 없이 입력해주세요.'), 400
        uploads = request.files.getlist('files')
        if not uploads:
            return jsonify(error='처리할 문서를 선택해주세요.'), 400
        files = []
        used = 0
        for upload in uploads:
            name = (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
            if Path(name).suffix.lower() not in ('.zip', '.pdf', '.hwp', '.hwpx'):
                return jsonify(error='ZIP, PDF, HWP, HWPX 파일을 선택해주세요.'), 400
            data = upload.read(UPLOAD_LIMIT - used + 1)
            used += len(data)
            if used > UPLOAD_LIMIT:
                return jsonify(error='전체 파일 용량을 100MB 이하로 줄여주세요.'), 413
            files.append((name, data))
        with lock:
            cleanup()
            owner = session.get('owner')
            if not owner:
                return jsonify(error='화면을 새로고침해주세요.'), 403
            if any(job.owner == owner and job.finished is None for job in jobs.values()):
                return jsonify(error='현재 진행 중인 작업을 먼저 기다려주세요.'), 409
            if sum(job.finished is None for job in jobs.values()) >= 8:
                return jsonify(error='대기 작업이 많습니다. 잠시 후 다시 시도해주세요.'), 503
            job = Job(owner=owner, connection=connection)
            jobs[job.id] = job
            try:
                executor.submit(run_job, job, files, key, law_oc)
            except RuntimeError:
                jobs.pop(job.id, None)
                return jsonify(error='실행 창을 다시 열고 시도해주세요.'), 503
            session['job_id'] = job.id
            return jsonify(job=snapshot(job)), 202

    @app.get('/api/jobs/<job_id>')
    def status(job_id):
        with lock:
            job = owned_job(job_id)
            if not job:
                return jsonify(error='작업을 찾을 수 없습니다. 화면을 새로고침해주세요.'), 404
            return jsonify(job=snapshot(job))

    @app.get('/api/jobs/<job_id>/download')
    def download(job_id):
        with lock:
            job = owned_job(job_id)
            if not job or not job.result or not job.result.get('xlsx'):
                return jsonify(error='내려받을 결과가 없습니다.'), 404
            data = job.result['xlsx']
        return send_file(BytesIO(data), as_attachment=True, download_name='법령_주요내용_요약.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)

    return app


def serve(port):
    from waitress import serve as serve_wsgi
    serve_wsgi(create_app(), host='127.0.0.1', port=port, threads=4, max_request_body_size=UPLOAD_LIMIT + 1024 * 1024)
