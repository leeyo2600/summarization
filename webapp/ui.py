"""Presentation helpers. No API calls or credentials stored here."""
from base64 import b64encode
from functools import lru_cache
import streamlit as st
from lawtool import ROOT


SERVICE_NAME='의견조회 요약 도우미'
COPYRIGHT_NOTICE='© 2026 행정안전부 데이터정보화담당관'


UPLOAD_HELP='''요청공문 PDF와 첨부 법안 HWP/HWPX를 같은 폴더에 넣은 ZIP을 권장합니다.
여러 ZIP을 하나로 압축한 통합 ZIP도 지원합니다. 폴더 구조를 유지하세요.

공문이 없으면 소관기관·제출기한은 빈칸입니다. HWP는 서버에 Java 변환기가 필요합니다.
PDF는 텍스트 기반 공문·예고 보조자료만 지원하며, 스캔 PDF·암호·DRM 문서는 지원하지 않습니다.

전체 업로드 100MB 이하, 압축 해제 누적 250MB 이하입니다. 빈 검토양식은 제외합니다.'''
DEPARTMENT_HELP='''소관부서 추천은 모든 요약에 기본 포함됩니다.
국가법령정보센터의 현행 직제 시행규칙에서 전체 업무분장을 조회해 주요내용과 비교합니다.
근거가 있으면 관련 부서 하나, 없으면 “없음”으로 기록합니다. API 오류로 처리하지 못한 경우는 빈칸과 오류로 구분합니다.
요약과 부서 추천은 Luna를 사용하며 각각 API 비용이 발생합니다.'''


def missing_requirements(files,key,consent,law_oc,too_large):
    missing=[]
    if not files: missing.append('문서 선택')
    if too_large: missing.append('전체 파일 100MB 이하')
    if not key.strip(): missing.append('API 키 입력')
    if not law_oc.strip(): missing.append('국가법령정보 API 키 입력')
    if not consent: missing.append('외부 전송 동의')
    return missing


STEPS=(('input','자료 등록'),('processing','요약 생성'),('complete','결과 확인'))


def available_pages(state):
    # Keep a running (or not-yet-collected) job on its monitor screen.
    if state.get('job') is not None:
        return {'processing'}
    return {'input','complete'} if state.get('result') or state.get('fatal') else {'input'}


def navigate(page):
    if page in available_pages(st.session_state):
        # Navigation must not clear the last result or start another API call.
        st.session_state.page=page


@lru_cache(maxsize=1)
def font_styles():
    """Bundle trusted local font bytes; no CDN request or static-file exposure."""
    faces=[]
    for weight,name in ((400,'Regular'),(500,'Medium'),(700,'Bold')):
        path=ROOT/'assets/fonts'/f'NotoSansKR-{name}-Hestia.woff2'
        if path.is_file():
            encoded=b64encode(path.read_bytes()).decode('ascii')
            faces.append("@font-face{font-family:'Noto Sans KR';font-style:normal;"
                         f"font-weight:{weight};font-display:swap;"
                         f"src:url(data:font/woff2;base64,{encoded}) format('woff2');}}")
    return ''.join(faces)


def render_header(page):
    st.markdown('<style>'+font_styles()+(ROOT/'assets/web.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
    logo=ROOT/'assets/mois-logo.jpg'
    logo_html=''
    if logo.is_file():
        encoded=b64encode(logo.read_bytes()).decode('ascii')
        # Keep the supplied JPEG unchanged; the viewport removes only its blank canvas.
        logo_html=('<span class="agency-logo"><img alt="행정안전부" '
                   f'src="data:image/jpeg;base64,{encoded}" width="942" height="228"></span>')
    st.markdown('<header class="brand">'+logo_html+f'<strong>{SERVICE_NAME}</strong></header>',unsafe_allow_html=True)
    allowed=available_pages(st.session_state)
    with st.container(key='workflow_nav'):
        columns=st.columns(3,gap=None)
        for i,((target,label),column) in enumerate(zip(STEPS,columns),1):
            help_text=('현재 보고 있는 화면입니다.' if target==page else
                       '작업 중에는 화면 이동이 제한됩니다.' if st.session_state.get('job') is not None else
                       '요약이 완료되면 확인할 수 있습니다.' if target=='complete' else
                       '문서 처리가 시작되면 열립니다.' if target=='processing' else
                       '기존 결과를 유지한 채 새 문서를 등록합니다.')
            with column:
                st.button(f'{i:02d}  {label}',key='nav_'+target,width='stretch',
                          type='primary' if target==page else 'secondary',
                          disabled=target not in allowed,on_click=navigate,args=(target,),help=help_text)


def render_footer():
    st.markdown('<footer class="footer-note">'
                '<div>AI 요약은 업무 검토를 돕는 참고자료입니다. 외부 전송이 허용된 문서만 등록해주세요.</div>'
                f'<small class="copyright">{COPYRIGHT_NOTICE}</small></footer>',unsafe_allow_html=True)
