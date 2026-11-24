'use strict';
const $ = (id) => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const form = $('upload-form');
const limit = 100 * 1024 * 1024;
function setSecretVisible(id, visible) {
  $(id).type = visible ? 'text' : 'password';
  const button = $(`toggle-${id}`);
  button.textContent = visible ? '숨기기' : '보기';
  button.setAttribute('aria-pressed', String(visible));
  button.setAttribute('aria-label', `${id === 'api-key' ? 'OpenAI API 키' : '국가법령정보 API 키'} ${visible ? '숨기기' : '보기'}`);
}
for (const id of ['api-key', 'law-oc']) {
  $(`toggle-${id}`).addEventListener('click', () => setSecretVisible(id, $(id).type === 'password'));
}
let files = [], job = null, page = 'input', submitting = false, pollTimer;
const credentialsMetaKey = 'law_summary.credentials_order';
let credentialsMeta;
try { credentialsMeta = JSON.parse(sessionStorage.getItem(credentialsMetaKey)); } catch (_) { /* Storage may be unavailable. */ }
const credentialsClient = typeof credentialsMeta?.client === 'string' ? credentialsMeta.client : crypto.randomUUID();
let credentialsRevision = Number.isSafeInteger(credentialsMeta?.revision) ? credentialsMeta.revision : 0;
let credentialsReady = false, credentialsDirty = false;
function rememberCredentialsOrder(pending) {
  try { sessionStorage.setItem(credentialsMetaKey, JSON.stringify({client: credentialsClient, revision: credentialsRevision, pending})); }
  catch (_) { /* Key values are never stored in browser storage. */ }
}
const savedMessage = '마지막 입력 키는 이 PC에 암호화해 저장하며, 다음 실행 시 자동으로 불러옵니다.';
function credentialsStatus(message, failed = false) {
  $('credentials-status').textContent = message;
  $('credentials-status').className = failed ? 'notice warning' : 'caption';
}
async function saveCredentials(keepalive = false) {
  if (!credentialsReady || !credentialsDirty) return;
  const revision = credentialsRevision;
  try {
    await api('/api/credentials', {method: 'POST', keepalive,
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify({api_key: $('api-key').value.trim(), law_oc: $('law-oc').value.trim(),
        client_id: credentialsClient, revision})});
    if (revision === credentialsRevision) {
      credentialsDirty = false;
      rememberCredentialsOrder(false);
      credentialsStatus(savedMessage);
    }
  } catch (error) {
    if (revision === credentialsRevision) credentialsStatus(error.message, true);
  }
}
function queueCredentials() {
  if (!credentialsReady) return;
  credentialsRevision = Math.max(credentialsRevision + 1, Date.now() * 1000);
  credentialsDirty = true;
  rememberCredentialsOrder(true);
  credentialsStatus('API 키를 저장하는 중입니다.');
  saveCredentials();
}
for (const id of ['api-key', 'law-oc']) {
  $(id).addEventListener('input', queueCredentials);
  $(id).addEventListener('change', queueCredentials);
}
window.addEventListener('pagehide', () => { saveCredentials(true); });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') saveCredentials(true);
});
async function restoreCredentials() {
  try {
    const pending = credentialsMeta?.pending ? `?client_id=${encodeURIComponent(credentialsClient)}&revision=${credentialsRevision}` : '';
    const saved = await api(`/api/credentials${pending}`, {headers: {'X-CSRF-Token': csrf}});
    $('api-key').value = saved.api_key || '';
    $('law-oc').value = saved.law_oc || '';
    rememberCredentialsOrder(false);
    credentialsStatus(savedMessage);
  } catch (error) { credentialsStatus(error.message, true); }
  finally {
    credentialsReady = true;
    $('api-key').disabled = $('law-oc').disabled = false;
    validate();
  }
}
const duration = (seconds) => {
  const n = Math.max(0, Math.floor(seconds || 0));
  return `${n >= 3600 ? `${Math.floor(n / 3600)}시간 ` : ''}${Math.floor(n % 3600 / 60)}분 ${n % 60}초`;
};
function showError(message) {
  $('input-error').textContent = message;
  $('input-error').hidden = !message;
}
function validate() {
  const size = files.reduce((sum, file) => sum + file.size, 0);
  $('generate').disabled = !credentialsReady || submitting || !files.length || size > limit || !$('api-key').value.trim() || !$('law-oc').value.trim() || !$('consent').checked;
  $('file-count').textContent = files.length ? `선택한 파일 ${files.length}개 · 합계 ${(size / 1024 ** 2).toFixed(1)}MB / 100MB` : '전체 파일 100MB 이하';
  if (size > limit) showError('전체 파일 용량을 100MB 이하로 줄여주세요.');
}
function renderFiles() {
  $('file-list').replaceChildren();
  files.forEach((file, index) => {
    const item = document.createElement('li'), name = document.createElement('span'), remove = document.createElement('button');
    name.textContent = file.name;
    remove.type = 'button'; remove.textContent = '삭제'; remove.setAttribute('aria-label', `${file.name} 삭제`);
    remove.addEventListener('click', () => { files.splice(index, 1); showError(''); renderFiles(); });
    item.append(name, remove); $('file-list').append(item);
  });
  validate();
}
function addFiles(incoming) {
  showError('');
  for (const file of incoming) {
    if (!/\.(zip|pdf|hwp|hwpx)$/i.test(file.name)) { showError('ZIP, PDF, HWP, HWPX 파일을 선택해주세요.'); continue; }
    if (!files.some((old) => old.name === file.name && old.size === file.size && old.lastModified === file.lastModified)) files.push(file);
  }
  renderFiles();
}
$('files').addEventListener('change', (event) => { addFiles(event.target.files); event.target.value = ''; });
for (const name of ['dragenter', 'dragover']) $('dropzone').addEventListener(name, (e) => { e.preventDefault(); $('dropzone').classList.add('dragging'); });
for (const name of ['dragleave', 'drop']) $('dropzone').addEventListener(name, (e) => { e.preventDefault(); $('dropzone').classList.remove('dragging'); });
$('dropzone').addEventListener('drop', (e) => addFiles(e.dataTransfer.files));
form.addEventListener('input', validate);
function navigate(target, focus = true) {
  const running = submitting || job?.status === 'running';
  const allowed = running ? ['processing'] : job ? ['input', 'complete'] : ['input'];
  if (!allowed.includes(target)) return;
  page = target;
  for (const name of ['input', 'processing', 'complete']) $(`${name}-page`).hidden = name !== page;
  document.querySelectorAll('[data-page]').forEach((button) => {
    button.disabled = !allowed.includes(button.dataset.page);
    if (button.dataset.page === page) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  if (focus) $(`${page}-title`).focus({preventScroll: true});
}
document.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.page)));
async function api(url, options = {}) {
  const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '요청을 처리하지 못했습니다.');
  return data;
}
function renderResult() {
  $('total-time').textContent = `총 소요 시간: ${duration(job.elapsed)}`;
  $('fatal').hidden = !job.error; $('fatal').textContent = job.error || '';
  $('result-content').hidden = !job.result;
  $('complete-title').textContent = job.error ? '처리 중 문제가 발생했습니다' : job.result?.issues.length ? '처리 결과 확인' : '요약 결과 내려받기';
  if (!job.result) return;
  const result = job.result, rows = result.rows, issues = result.issues, downloadable = Boolean(result.download);
  $('total-count').textContent = `${result.total}건`;
  $('success-count').textContent = `${result.success}건`;
  $('issues-count').textContent = `${issues.length}건`;
  $('ignored').hidden = !result.ignored_count;
  $('ignored').textContent = `빈 검토양식 ${result.ignored_count}개는 요약에서 제외했습니다.`;
  $('partial').hidden = !issues.length || !downloadable;
  $('download').hidden = !downloadable;
  if (downloadable) $('download').href = result.download;
  $('compare-note').hidden = $('preview').hidden = !downloadable;
  $('no-download').hidden = downloadable;
  $('result-rows').replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    row.forEach((value) => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
    $('result-rows').append(tr);
  });
  const blanks = rows.filter((row) => !(row[4] || '').trim()).length;
  $('department-status').hidden = !rows.length;
  $('department-status').className = `notice ${blanks ? 'warning' : 'success'}`;
  $('department-status').textContent = blanks ? `비고 미완료 ${blanks}행 · 빈칸은 “관련 부서 없음” 판정이 아닙니다.` : `비고 ${rows.length}행 처리 완료 · 부서명 또는 “없음”을 확인하세요.`;
  $('issues').hidden = !issues.length;
  $('issue-list').replaceChildren();
  issues.forEach((issue) => { const li = document.createElement('li'), name = document.createElement('strong'), message = document.createElement('p'); name.textContent = issue.file; message.textContent = issue.error; li.append(name, message); $('issue-list').append(li); });
}
function updateJob(next, restore = false) {
  job = next;
  if (!job) { navigate('input', false); return; }
  const connection = job.connection;
  const label = connection ? `사용 서비스: ${connection.label}` : '';
  $('processing-provider').textContent = $('result-provider').textContent = label;
  if (job.status === 'running') {
    $('elapsed').textContent = duration(job.elapsed);
    $('progress').value = Math.min(1, Math.max(0, job.done / Math.max(job.total, 1)));
    $('progress-count').textContent = job.total ? `${job.done} / ${job.total}건 요약 완료` : '자료 준비 중';
    $('progress-message').textContent = job.message;
    if (page !== 'processing') navigate('processing');
    clearTimeout(pollTimer); pollTimer = setTimeout(poll, 1000);
  } else {
    clearTimeout(pollTimer); renderResult();
    if (page === 'processing' || restore) navigate('complete');
  }
}
async function poll() {
  try { const data = await api(`/api/jobs/${job.id}`); $('connection-error').hidden = true; updateJob(data.job); }
  catch (error) {
    $('connection-error').textContent = `진행 상태 연결을 다시 확인하고 있습니다. 실행 창을 유지해주세요. ${error.message}`;
    $('connection-error').hidden = false;
    pollTimer = setTimeout(poll, 2500);
  }
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if ($('generate').disabled) return;
  const data = new FormData();
  files.forEach((file) => data.append('files', file, file.name));
  data.append('api_key', $('api-key').value.trim()); data.append('law_oc', $('law-oc').value.trim()); data.append('consent', 'true');
  saveCredentials();
  setSecretVisible('api-key', false); setSecretVisible('law-oc', false);
  submitting = true; validate(); $('generate').textContent = '문서 전달 중…'; showError('');
  try {
    const response = await api('/api/jobs', {method: 'POST', headers: {'X-CSRF-Token': csrf}, body: data});
    $('consent').checked = false; files = []; renderFiles(); submitting = false;
    updateJob(response.job, true);
  } catch (error) { showError(error.message); }
  finally { submitting = false; $('generate').textContent = '생성'; validate(); }
});
restoreCredentials();
api('/api/state').then((data) => updateJob(data.job, true)).catch(() => showError('실행 창과 연결할 수 없습니다. 화면을 새로고침해주세요.'));
