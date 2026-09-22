"""Three-step API UI. Run python start_web.py."""
from queue import Queue, Empty
import streamlit as st
from lawtool import ROOT
from webapp.jobs import EXECUTOR, process

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

if (ROOT/'assets'/'logo.png').is_file(): st.image(str(ROOT/'assets'/'logo.png'),width=260)
else: st.markdown('<div class="brand"><strong>행정안전부</strong><span>법령 제·개정안 요약 도우미</span></div>',unsafe_allow_html=True)
state=st.session_state
if 'page' not in state: state.page='input'
pages=['input','processing','complete']
labels=['문서 등록','요약 진행','결과 확인']
current=pages.index(state.page)
st.markdown('<nav class="steps" aria-label="처리 단계">'+''.join(f'<div class="step {"active" if current==i else "done" if current>i else ""}" '+('aria-current="step"' if current==i else '')+f'><b>{"✓" if current>i else i+1}</b>{label}</div>' for i,label in enumerate(labels))+'</nav>',unsafe_allow_html=True)

def reset():
    for name in ('job','progress','result','fatal','api_key','files','consent','last_progress'):
        state.pop(name,None)
    state.page='input'

if state.page=='input':
    st.title('법령 요약, 문서 등록부터')
    st.write('문서 전체를 검토해 제·개정사항을 정리하고 엑셀로 만들어드립니다.')
    with st.container(border=True):
        st.subheader('API 연결',anchor=False)
        key=st.text_input('OpenAI API 키',type='password',placeholder='발급받은 API 키를 붙여넣으세요',key='api_key')
        st.caption('GPT-5.6 Luna · 입력한 키는 파일에 저장하지 않습니다.')
    with st.container(border=True):
        st.subheader('문서 등록',anchor=False)
        files=st.file_uploader('의견조회 ZIP 또는 문서를 선택하세요',type=['zip','pdf','hwp','hwpx'],accept_multiple_files=True,key='files',help='공문 PDF와 법안 HWP·HWPX를 함께 넣은 ZIP 권장. 전체 100MB 이하')
        st.caption('개별 ZIP·통합 ZIP 지원 · 공문과 첨부문서의 폴더 구조를 유지해주세요. PDF는 텍스트 추출 가능한 요청공문을 지원합니다.')
        with st.expander('지원 파일 형식과 넣는 방법'):
            st.markdown('''- **ZIP (권장):** 의견조회 요청공문 PDF와 첨부 법안 HWP/HWPX를 같은 폴더에 넣어주세요. 여러 건의 ZIP을 다시 하나로 압축해도 됩니다.
- **HWP / HWPX:** 법안 단독 업로드도 가능합니다. 공문이 없으면 소관기관·제출기한은 빈칸입니다. HWP는 Java 변환 환경이 필요합니다.
- **PDF:** 텍스트를 읽을 수 있는 요청공문용입니다. 스캔·이미지 PDF와 PDF 법안은 현재 지원하지 않습니다.
- 빈 검토의견서 양식은 제외하고, 개정안·별표는 같은 건의 보조자료로 읽습니다.
- 전체 업로드 100MB 이하, 압축 해제 누적 250MB 이하입니다. 비밀번호·DRM 문서는 지원하지 않습니다.''')
            st.code('통합.zip\n  ├─ 의견조회_1.zip\n  │    ├─ 요청공문.pdf\n  │    └─ 법률안.hwpx\n  └─ 의견조회_2.zip\n       ├─ 요청공문.pdf\n       └─ 첨부.zip\n            ├─ 개정안.hwpx\n            └─ 별표.hwpx',language=None)
    too_large=bool(files) and sum(f.size for f in files)>100*1024*1024
    if too_large: st.error('전체 파일 용량을 100MB 이하로 줄여주세요.')
    if files: st.caption(f'{len(files)}개 파일 선택됨')
    consent=st.checkbox('문서에서 추출한 전체 텍스트를 OpenAI API로 전송하는 데 동의합니다.',key='consent')
    ready=bool(key.strip() and files and consent) and not too_large
    if not ready: st.caption('API 키 입력 → 문서 선택 → 전송 동의 후 시작할 수 있습니다.')
    if st.button('제·개정사항 요약 시작',icon=':material/auto_awesome:',type='primary',width='stretch',disabled=not ready):
        data=[(f.name,f.getvalue()) for f in files]
        state.progress=Queue()
        state.job=EXECUTOR.submit(process,data,key.strip(),state.progress)
        state.page='processing'
        st.rerun()

elif state.page=='processing':
    st.title('제·개정사항을 정리하고 있어요')
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
                st.markdown('<div class="eyebrow">문서 분석 및 요약</div>',unsafe_allow_html=True)
                st.progress(done/max(total,1),text=f'{done} / {total}개 파일 처리 완료')
                st.text(name)
            st.caption('창을 유지해주세요. 원문 분석과 API 응답에 따라 시간이 달라집니다.')
            if state.job.done():
                try: state.result=state.job.result()
                except Exception: state.fatal='작업을 완료하지 못했습니다. 연결 상태와 저장 폴더 권한을 확인해주세요.'
                state.pop('api_key',None); state.pop('files',None)
                state.pop('job',None); state.pop('progress',None)
                state.page='complete'
                st.rerun(scope='app')
        monitor()

else:
    result=state.get('result')
    if state.get('fatal'):
        st.title('처리를 완료하지 못했어요'); st.error(state.fatal)
    elif result:
        st.title('요약이 완료됐어요' if not result['issues'] else '처리 결과를 확인해주세요')
        st.write(f"전체 {result['total']}개 중 {result['success']}개 완료 · 확인 필요 {len(result['issues'])}개")
        with st.container(border=True):
            first,second,third=st.columns(3)
            first.metric('등록 문서',f"{result['total']}개")
            second.metric('처리 완료',f"{result['success']}개")
            third.metric('확인 필요',f"{len(result['issues'])}개")
        if result['xlsx']:
            st.download_button('요약 엑셀 다운로드',result['xlsx'],'법령_주요내용_요약.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',icon=':material/download:',type='primary',width='stretch')
            st.caption('활용 전 원문과 대조하여 요약 내용을 확인해주세요.')
            with st.expander('요약 미리보기'):
                st.dataframe([{'법령명':r[0],'주요내용':r[1]} for r in result['rows']],hide_index=True,use_container_width=True)
        else: st.error('다운로드할 요약이 없습니다. 아래 내용을 확인해주세요.')
        if result['issues']:
            with st.expander('처리하지 못한 문서',expanded=True):
                for issue in result['issues']: st.write(issue['file']); st.caption(issue['error'])
        with st.expander('처리기록'):
            st.download_button('처리기록 다운로드',result['report'],'처리기록.json',mime='application/json')
            st.caption(result['folder'])
    else: st.warning('완료된 작업이 없습니다.')
    st.button('다른 문서 요약하기',icon=':material/add:',on_click=reset,width='stretch')

st.markdown('<div class="footer-note">AI 요약은 업무 검토를 돕는 참고자료입니다. 외부 전송이 허용된 문서만 등록해주세요.</div>',unsafe_allow_html=True)
