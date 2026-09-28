"""Three-step API UI. Run python start_web.py."""
from queue import Queue, Empty
import time
import streamlit as st
from lawtool import ROOT
from webapp.api import MODEL as SUMMARY_MODEL, DEPARTMENT_MODEL as MODEL
from webapp.jobs import EXECUTOR, process
from webapp.department_retry import saved_results, load_saved_result, retry_departments
from webapp.gpt_department_experiment import experiment as gpt_department_experiment
from webapp.model_comparison import compare as compare_department_models, select_rows as comparison_rows
from webapp.download_progress import progress_view, duration

st.set_page_config(page_title='법령 주요내용 정리',page_icon='📄',layout='centered')
st.markdown('''<style>
.stApp {background:#f3f6fa;color:#19334b;font-family:'Malgun Gothic',sans-serif}
.block-container {max-width:860px;padding-top:2.8rem;padding-bottom:4rem}
h1,h2,h3 {color:#003863;letter-spacing:-.045em}
h1 {font-size:2.05rem!important;font-weight:800!important;padding-bottom:.6rem!important}
[data-testid="stCaptionContainer"] {color:#526779}
.brand {display:flex;align-items:center;gap:14px;padding:0 0 22px;border-bottom:1px solid #d8e1eb;margin-bottom:8px;color:#003863}
.brand strong {font-size:21px;letter-spacing:-.05em}
.brand span {font-size:13px;color:#526779;border-left:1px solid #c4d1de;padding-left:14px}
.steps {display:flex;gap:8px;margin:18px 0 30px}
.step {flex:1;display:flex;align-items:center;gap:10px;padding:13px 12px;border-radius:10px;background:#e9eef4;color:#526779;font-size:13px;font-weight:600}
.step b {display:grid;place-items:center;min-width:25px;height:25px;border-radius:50%;background:#fff;font-size:12px}
.step.active {background:#003863;color:#fff}
.step.active b {color:#003863}
.step.done {background:#e2eee9;color:#23614c}
[data-testid="stVerticalBlockBorderWrapper"] {background:#fff;border-radius:16px!important;border-color:#dce4ed!important}
[data-testid="stTextInput"] input {min-height:48px;font-size:15px}
[data-testid="stTextInput"] [data-baseweb="input"] {border-radius:9px;background:#f8fafc;border-color:#bac9d8}
[data-testid="stFileUploaderDropzone"] {background:#f7faff;border:1.5px dashed #9aafc1;border-radius:12px;padding:25px 18px}
div.stButton>button,div.stDownloadButton>button,[data-testid="stFileUploaderDropzone"] button {min-height:46px;border-radius:9px;border:1px solid #a7bbce;background:#fff;color:#003863;font-weight:650;transition:background .15s,border-color .15s}
div.stButton>button:hover,div.stDownloadButton>button:hover,[data-testid="stFileUploaderDropzone"] button:hover {background:#eaf1f8;border-color:#003863;color:#003863}
div.stButton>button[kind="primary"],div.stDownloadButton>button[kind="primary"] {background:#003863;color:#fff;border:1px solid #003863;min-height:54px;box-shadow:0 4px 10px #00386318}
div.stButton>button[kind="primary"]:hover,div.stDownloadButton>button[kind="primary"]:hover {background:#00518b;border-color:#00518b;color:#fff}
div.stButton>button:disabled {background:#e3e9f0!important;color:#63758a!important;border-color:#d5dee8!important;box-shadow:none;cursor:not-allowed}
button:focus-visible,input:focus-visible {outline:3px solid #3685c5!important;outline-offset:3px}
[data-testid="stMetricValue"] {color:#003863;font-size:1.8rem}
.eyebrow {color:#63798b;font-size:12px;font-weight:700;letter-spacing:.08em;margin:10px 0 8px}
.footer-note {margin-top:32px;padding-top:16px;border-top:1px solid #d8e1eb;color:#607386;font-size:12px;line-height:1.8}
@media(max-width:540px) {.block-container {padding:1.4rem 1rem 2rem}.brand {gap:8px}.brand strong {font-size:18px}.brand span {font-size:11px;padding-left:8px}.steps {gap:5px}.step {padding:10px 6px;gap:5px;font-size:11px}h1 {font-size:1.65rem!important}}
</style>''',unsafe_allow_html=True)
st.markdown('<style>'+(ROOT/'assets'/'web.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
st.markdown('<div class="service-strip"><span>행정안전부 업무지원 도구</span><span>법령 의견조회 · AI 요약</span></div>',unsafe_allow_html=True)

if (ROOT/'assets'/'logo.png').is_file(): st.image(str(ROOT/'assets'/'logo.png'),width=260)
else: st.markdown('<div class="brand"><strong>행정안전부</strong><span>법령 제·개정안 요약 도우미</span></div>',unsafe_allow_html=True)
state=st.session_state
if 'page' not in state: state.page='input'
pages=['input','processing','complete']
labels=['문서 등록','요약 진행','결과 확인']
current=pages.index(state.page)
st.markdown('<nav class="steps" aria-label="처리 단계">'+''.join(f'<div class="step {"active" if current==i else "done" if current>i else ""}" '+('aria-current="step"' if current==i else '')+f'><b>{"✓" if current>i else i+1}</b>{label}</div>' for i,label in enumerate(labels))+'</nav>',unsafe_allow_html=True)

def reset():
    for name in ('job','job_kind','job_timing','progress','result','fatal','api_key','law_oc','match_departments','files','consent','last_progress',
                 'retry_key','retry_oc','retry_consent','retry_error','retry_all',
                 'gpt_test_job','gpt_test_queue','gpt_test_result','gpt_test_error','gpt_test_message',
                 'gpt_test_key','gpt_test_oc','gpt_test_consent','gpt_test_mode'):
        state.pop(name,None)
    state.page='input'


def summary_elapsed():
    timing=state.get('job_timing')
    if timing is None: return None
    return max(0,timing.get('finished',time.monotonic())-timing['started'])


def show_download_status(message,started=None):
    if isinstance(message,dict) and message.get('kind')=='download':
        view=progress_view(message)
        st.caption(view['status'])
        st.progress(view['fraction'],text=f"{view['fraction']*100:.1f}% · 준비된 용량 {view['size']}")
        st.caption(f"경과 {view['elapsed']} · 평균 전송 속도 {view['speed']} · 예상 남은 시간 {view['eta']}")
        st.caption(f"기존 캐시 {message['cached']/1024**2:,.1f} MB · 이번 전송 {message['transferred']/1024**2:,.1f} MB. 남은 시간은 파일 준비 속도 기준 추정치입니다.")
    else:
        st.caption(message)
        if started is not None: st.caption('준비 경과 시간 '+duration(time.monotonic()-started))

if state.page=='input':
    st.title('법령 의견조회 요약')
    st.write('주요내용을 중심으로 제·개정사항을 정리하고 엑셀로 제공합니다.')
    st.markdown('<div class="intro-note">요청공문과 법안을 함께 등록하세요. 발신기관·부서·제출기한은 공문에서 확인하고, 읽을 수 없는 파일은 기록 후 건너뜁니다.</div>',unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader('01  API 연결',anchor=False)
        key=st.text_input('OpenAI API 키',type='password',placeholder='발급받은 API 키를 붙여넣으세요',key='api_key')
        st.caption(f'주요내용 요약: {SUMMARY_MODEL} · 비고 추천: {MODEL} · 입력한 키는 파일에 저장하지 않습니다.')
        match_departments=st.checkbox('행정안전부 소관부서 추천',value=True,key='match_departments')
        law_oc=st.text_input('국가법령정보센터 API OC',type='password',key='law_oc',
            disabled=not match_departments,help='공동활용 API에서 승인받은 OC 인증값을 입력하세요. 파일에 저장하지 않습니다.')
        st.caption(f'비고 추천: {MODEL}가 현행 직제 시행규칙의 전체 업무분장과 각 법령 주요내용을 비교합니다. 임베딩 모델·다운로드·유사도 기준은 사용하지 않습니다.')
        st.caption('의견 검토에 관련된 부서 하나 또는 “없음”을 기록합니다. 선택 근거와 이유는 처리기록에 저장됩니다. 법령별 전체 업무분장 전송에 따른 API 비용이 발생합니다.')
    with st.expander('기존 요약 결과 불러오기 · 빈 비고만 채우기'):
        st.caption('이 PC에 저장된 결과를 불러옵니다. 원본 문서를 다시 요약하지 않고 빈 비고만 재처리할 수 있습니다.')
        saved=saved_results()
        if saved:
            selected=st.selectbox('저장된 요약 결과',saved,key='saved_result')
            if st.button('기존 결과 불러오기',key='load_saved_result'):
                try:
                    state.result=load_saved_result(selected)
                    for name in ('fatal','retry_error','job_timing','last_progress','job_kind'):
                        state.pop(name,None)
                    state.page='complete'
                    st.rerun()
                except (ValueError,OSError) as error:
                    st.error(str(error) if isinstance(error,ValueError) else '저장된 결과 파일을 읽지 못했습니다.')
        else:
            st.caption('저장된 요약 결과가 없습니다.')
    with st.container(border=True):
        st.subheader('02  의견조회 자료 등록',anchor=False)
        files=st.file_uploader('의견조회 ZIP 또는 문서를 선택하세요',type=['zip','pdf','hwp','hwpx'],accept_multiple_files=True,key='files',help='공문 PDF와 법안 HWP·HWPX를 함께 넣은 ZIP 권장. 전체 100MB 이하')
        st.caption('개별 ZIP·통합 ZIP 지원 · 공문과 첨부문서의 폴더 구조를 유지해주세요. PDF는 텍스트 추출 가능한 요청공문을 지원합니다.')
        with st.expander('지원 파일 형식과 넣는 방법'):
            st.markdown('''- **ZIP (권장):** 의견조회 요청공문 PDF와 첨부 법안 HWP/HWPX를 같은 폴더에 넣어주세요. 여러 건의 ZIP을 다시 하나로 압축해도 됩니다.
- **HWP / HWPX:** 법안 단독 업로드도 가능합니다. 공문이 없으면 소관기관·제출기한은 빈칸입니다. HWP는 Java 변환 환경이 필요합니다.
- **PDF:** 텍스트 기반 요청공문과 입법·행정예고 보조자료를 읽습니다. 스캔·이미지 PDF와 그 밖의 PDF 법안은 지원하지 않습니다.
- 빈 검토의견서 양식은 제외하고, 개정안·별표는 같은 건의 보조자료로 읽습니다.
- 전체 업로드 100MB 이하, 압축 해제 누적 250MB 이하입니다. 비밀번호·DRM 문서는 지원하지 않습니다.''')
            st.code('통합.zip\n  ├─ 의견조회_1.zip\n  │    ├─ 요청공문.pdf\n  │    └─ 법률안.hwpx\n  └─ 의견조회_2.zip\n       ├─ 요청공문.pdf\n       └─ 첨부.zip\n            ├─ 개정안.hwpx\n            └─ 별표.hwpx',language=None)
    too_large=bool(files) and sum(f.size for f in files)>100*1024*1024
    if too_large: st.error('전체 파일 용량을 100MB 이하로 줄여주세요.')
    if files: st.caption(f'{len(files)}개 파일 선택됨')
    consent=st.checkbox('문서에서 추출한 전체 텍스트를 OpenAI API로 전송하는 데 동의합니다.',key='consent')
    ready=bool(key.strip() and files and consent) and not too_large and (not match_departments or bool(law_oc.strip()))
    if not ready: st.caption('API 키·추천용 OC 입력 → 문서 선택 → 전송 동의 후 시작할 수 있습니다. OC 없이 요약만 하려면 부서 추천을 해제하세요.')
    if st.button('제·개정사항 요약 시작',key='start_summary',icon=':material/auto_awesome:',type='primary',width='stretch',disabled=not ready):
        state.job_kind='summary'
        state.job_timing={'started':time.monotonic()}
        data=[(f.name,f.getvalue()) for f in files]
        state.progress=Queue()
        state.job=EXECUTOR.submit(process,data,key.strip(),state.progress,law_oc.strip() if match_departments else None)
        # Capture the dict, not Streamlit session state, in the worker callback.
        # Completion time stays accurate even if the browser stops polling.
        state.job.add_done_callback(lambda future,timing=state.job_timing: timing.update(finished=time.monotonic()))
        state.page='processing'
        st.rerun()

elif state.page=='processing':
    st.title('빈 비고 채우는 중' if state.get('job_kind')=='departments' else '법령 요약 진행 중')
    st.write('완료되면 다운로드 화면으로 자동 이동합니다.')
    if 'job' not in state:
        st.error('진행 중인 작업을 찾을 수 없습니다.')
        st.button('처음으로',on_click=reset)
    else:
        @st.fragment(run_every=1)
        def monitor():
            try:
                while True: state.last_progress=state.progress.get_nowait()
            except Empty: pass
            done,total,name=state.get('last_progress',(0,1,'작업 준비 중'))
            with st.container(border=True):
                st.markdown('<div class="eyebrow">'+('소관부서 추천 재처리' if state.get('job_kind')=='departments' else '문서 분석 및 요약')+'</div>',unsafe_allow_html=True)
                elapsed=summary_elapsed()
                if elapsed is not None:
                    st.metric('경과 시간',duration(elapsed),help='요약 시작부터 문서·모델 준비, 요약, 부서 추천, 결과 파일 저장까지 포함합니다.')
                st.markdown('<div class="loading-line" role="status"><span class="loading-ring"></span>처리 중 · 잠시 기다려주세요</div>',unsafe_allow_html=True)
                operation='비고 처리' if state.get('job_kind')=='departments' else '요약'
                st.progress(min(max(done/max(total,1),0),1),text=f'{done} / {total}건 {operation} 완료' if total else '자료 준비 중')
                if isinstance(name,dict): show_download_status(name)
                else: st.text(name)
            st.caption('창을 유지해주세요. 원문 분석과 API 응답에 따라 시간이 달라집니다.')
            if state.job.done():
                if 'job_timing' in state: state.job_timing.setdefault('finished',time.monotonic())
                try: state.result=state.job.result()
                except Exception as error:
                    if state.get('job_kind')=='departments':
                        state.retry_error=str(error) if isinstance(error,ValueError) else '비고 재처리를 완료하지 못했습니다. 연결 상태와 저장 폴더 권한을 확인해주세요.'
                    else:
                        state.fatal='작업을 완료하지 못했습니다. 연결 상태와 저장 폴더 권한을 확인해주세요.'
                state.pop('api_key',None); state.pop('law_oc',None); state.pop('files',None)
                state.pop('retry_key',None); state.pop('retry_oc',None); state.pop('retry_consent',None)
                state.pop('job',None); state.pop('progress',None)
                state.page='complete'
                st.rerun(scope='app')
        monitor()

else:
    result=state.get('result')
    if state.get('fatal'):
        st.title('처리를 완료하지 못했어요'); st.error(state.fatal)
        if summary_elapsed() is not None: st.caption('중단까지 경과 시간: '+duration(summary_elapsed()))
    elif result:
        st.title('요약 완료' if not result['issues'] else '처리 결과 확인')
        st.write(f"요약 완료 {result['success']}건 · 파일/연결 오류 {len(result['issues'])}건")
        if summary_elapsed() is not None:
            st.caption(('비고 재처리 소요 시간: ' if state.get('job_kind')=='departments' else '총 소요 시간: ')+duration(summary_elapsed()))
        if state.get('retry_error'): st.error('비고 재처리 실패 · 기존 요약은 그대로 보존했습니다. '+state.retry_error)
        with st.container(border=True):
            first,second,third=st.columns(3)
            first.metric('요약 대상',f"{result['total']}건")
            second.metric('요약 완료',f"{result['success']}건")
            third.metric('오류·확인사항',f"{len(result['issues'])}건")
        if result.get('ignored_count'): st.caption(f"빈 검토양식 {result['ignored_count']}개는 요약에서 제외했습니다.")
        if result['issues'] and result['xlsx']: st.warning('일부 처리에 오류·확인사항이 있습니다. 오류 목록을 확인하고 원문과 대조해주세요. 공문을 읽지 못하면 기관·기한이, 부서 추천에 실패하면 비고가 빈칸입니다.')
        if result['xlsx']:
            st.download_button('요약 엑셀 다운로드',result['xlsx'],'법령_주요내용_요약.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',icon=':material/download:',type='primary',width='stretch')
            st.caption('활용 전 원문과 대조하여 요약 내용을 확인해주세요.')
            with st.expander('요약 미리보기'):
                st.dataframe([{'법령명':r[0],'주요내용':r[1],'소관기관':r[2],'제출기한':r[3],'비고(소관부서)':r[4]} for r in result['rows']],hide_index=True,width='stretch')
            blank_count=sum(not row[4].strip() for row in result['rows'])
            if result['rows']:
                if blank_count: st.warning(f'비고 미완료 {blank_count}행 · 빈칸은 “관련 부서 없음” 판정이 아닙니다.')
                else: st.success(f'비고 {len(result["rows"])}행 처리 완료 · 부서명 또는 “없음”을 확인하세요.')
                with st.expander(f'{MODEL}로 비고 재처리 · 전체 또는 빈칸',expanded=bool(blank_count)):
                    st.caption(f'기존 주요내용·기관·제출기한은 유지합니다. {MODEL}가 전체 업무분장을 검토하여 비고를 새로 판정하고 별도 엑셀로 저장합니다. API 비용이 발생합니다.')
                    retry_all=st.checkbox('기존 “없음”을 포함해 모든 행의 비고를 다시 판정',value=not bool(blank_count),key='retry_all')
                    retry_key=st.text_input('부서 추천용 OpenAI API 키',type='password',key='retry_key')
                    retry_oc=st.text_input('부서 추천용 국가법령정보센터 OC',type='password',key='retry_oc')
                    retry_consent=st.checkbox('기존 주요내용을 부서 추천을 위해 OpenAI API에 전송하는 데 동의합니다.',key='retry_consent')
                    if st.button(f'{MODEL}로 비고 재처리',key='retry_departments',type='primary',
                                 disabled=not (retry_key.strip() and retry_oc.strip() and retry_consent and (retry_all or blank_count))):
                        state.pop('retry_error',None)
                        state.pop('last_progress',None)
                        state.job_kind='departments'
                        state.job_timing={'started':time.monotonic()}
                        state.progress=Queue()
                        state.job=EXECUTOR.submit(retry_departments,result,retry_key.strip(),state.progress,
                                                  retry_oc.strip(),retry_all=retry_all)
                        state.job.add_done_callback(lambda future,timing=state.job_timing: timing.update(finished=time.monotonic()))
                        state.page='processing'
                        st.rerun()
            with st.expander(f'실험 · {MODEL} 두 행 / Sol·Astra 지정 네 법령 비교',expanded=True):
                st.caption('전체 업무분장을 사용하며 임베딩은 사용하지 않습니다. 원본 엑셀과 운영 모델은 바꾸지 않습니다. API 비용이 발생하며 Sol·Astra 비교는 두 모델에 각각 4회, 총 8회 요청합니다.')
                @st.fragment(run_every=1)
                def gpt_test_panel():
                    future=state.get('gpt_test_job')
                    if future is not None:
                        if not future.done():
                            try:
                                while True: state.gpt_test_message=state.gpt_test_queue.get_nowait()
                            except Empty: pass
                            st.info(state.get('gpt_test_message','실험 준비 중'))
                            return
                        try: state.gpt_test_result=future.result()
                        except Exception as error:
                            state.gpt_test_error=str(error) if isinstance(error,ValueError) else '실험을 완료하지 못했습니다.'
                        for name in ('gpt_test_job','gpt_test_queue','gpt_test_key','gpt_test_oc','gpt_test_consent'):
                            state.pop(name,None)
                    if state.get('gpt_test_error'): st.error(state.gpt_test_error)
                    tested=state.get('gpt_test_result')
                    if tested:
                        for row in tested['results']:
                            st.write(f"{row.get('model',MODEL)} · {row['excel_row']}행 · {row['law']} → {row['selected'] or '처리 실패'}")
                            if row['status']=='error': st.error(row['error'])
                            else:
                                st.caption(row['reason'])
                                if row.get('evidence'):
                                    st.text(row['selected_department']+' · '+row['reference']+' · '+row['evidence']['text'])
                        st.download_button('GPT 실험 기록 다운로드',tested['report'],'gpt_department_experiment.json',mime='application/json',key='gpt_test_download')
                    test_mode=st.radio('실험 종류',[f'{MODEL} · 첫 두 행','Sol·Astra · 1·5·13·25번 법령'],key='gpt_test_mode')
                    compare_mode=test_mode.startswith('Sol')
                    valid_targets=True
                    if compare_mode:
                        st.caption('두 모델 모두 reasoning_effort=medium · 같은 프롬프트·같은 주요내용·같은 현행 업무분장으로 비교합니다. 기존 Luna 결과는 이전 실행 값이므로 동일 조건의 재실험은 아닙니다.')
                        try:
                            for excel_row,row in comparison_rows(result['rows']):
                                st.text(f'엑셀 {excel_row}행 · {row[0]}')
                        except ValueError as error:
                            st.error(str(error)); valid_targets=False
                    test_key=st.text_input('실험용 OpenAI API 키',type='password',key='gpt_test_key')
                    test_oc=st.text_input('실험용 국가법령정보센터 OC',type='password',key='gpt_test_oc')
                    consent=st.checkbox('선택한 실험 대상의 주요내용·전체 업무분장을 OpenAI API에 전송하고 유료 호출하는 데 동의합니다.',key='gpt_test_consent')
                    if st.button('Sol·Astra 네 법령 비교 실행' if compare_mode else 'GPT만으로 두 행 실험',key='gpt_test_start',disabled=not(test_key.strip() and test_oc.strip() and consent and valid_targets)):
                        state.pop('gpt_test_error',None); state.pop('gpt_test_result',None)
                        state.gpt_test_message='실험 준비 중'
                        state.gpt_test_queue=Queue()
                        state.gpt_test_job=EXECUTOR.submit(compare_department_models if compare_mode else gpt_department_experiment,result,test_key.strip(),test_oc.strip(),state.gpt_test_queue)
                        st.rerun()
                gpt_test_panel()
        else: st.error('다운로드할 요약이 없습니다. 아래 내용을 확인해주세요.')
        if result['issues']:
            with st.expander('건너뛴 파일 및 확인사항',expanded=True):
                for issue in result['issues']: st.text(issue['file']); st.caption(issue['error'])
        with st.expander('처리기록'):
            st.download_button('처리기록 다운로드',result['report'],'처리기록.json',mime='application/json')
            st.caption(result['folder'])
    else: st.warning('완료된 작업이 없습니다.')
    st.button('다른 문서 요약하기',key='reset',icon=':material/add:',on_click=reset,width='stretch')

st.markdown('<div class="footer-note">AI 요약은 업무 검토를 돕는 참고자료입니다. 외부 전송이 허용된 문서만 등록해주세요.</div>',unsafe_allow_html=True)
