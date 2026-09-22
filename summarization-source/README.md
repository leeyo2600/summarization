# 법령 개정 주요내용 요약기 v0.3

## 현재 웹앱 실행 안내

**현재 버전은 [README_WEB.md](README_WEB.md)를 따라 실행하세요.**
변경점 중심 요약, 공문 PDF·법안 HWP/HWPX 및 중첩 ZIP 입력을 지원합니다.
A/B 비교와 행안부 소관부서 자동 추천은 사용하지 않습니다.
배포 ZIP에는 원본 업무자료, 결과물, 모델, 가상환경, 변환 JAR가 포함되지 않습니다.
HWP 변환기는 실행 안내에 따라 별도로 빌드하세요.

---

아래는 이전 로컬 LLM 버전의 기록으로 현재 웹앱 설치 안내가 아닙니다.

> 2026-09-21 실행 안내: [RUNNING.md](RUNNING.md)를 우선 참고하세요. 현재 실행기는 프로젝트 `.venv`를 자동 사용합니다. 아래의 v0.1 환경 경로와 0.3.35 설치 안내는 과거 기록입니다. 이 PC에서 검증한 추론 패키지는 CUDA 12.4용 llama-cpp-python 0.3.4입니다.

지금까지 확인한 Windows DLL 로딩 수정, Hugging Face 다운로드, 테스트 HWP를 통합했습니다.
모든 작업은 Python 파일로 실행합니다. .cmd와 .exe 실행기는 포함하지 않습니다.
HWP 변환 라이브러리인 JAR는 포함되어 있으며 Java가 필요합니다.
모델 가중치(약 4.44GB)와 .venv는 포함하지 않았습니다.

## 폴더 열기
압축을 풀고 **lawtool.py, get_model.py, config.json이 있는 law_summary_v0.3 폴더**를 VS Code로 엽니다.
아래 명령은 그 폴더를 현재 위치로 가정합니다.

## 기존 환경을 그대로 사용하는 방법 — 현재 사용자 권장
기존 .venv에는 GPU 패키지와 CUDA 라이브러리가 이미 설치되어 있습니다.
새 폴더를 열어도 기존 환경을 지정하면 재설치가 필요 없습니다.
VS Code에서 Ctrl+Shift+P → Python: Select Interpreter → Enter interpreter path로 다음을 선택합니다.

`C:\Users\User\Desktop\law_summary_v0.1\.venv\Scripts\python.exe`

그다음 get_model.py 또는 lawtool.py를 열고 Python: Run Python File in Terminal로 실행하세요.
Code Runner의 Run Code가 아니라 Python 확장의 실행 기능을 사용합니다.
터미널에서 확실하게 기존 환경을 지정하려면:

```powershell
& "C:\Users\User\Desktop\law_summary_v0.1\.venv\Scripts\python.exe" .\get_model.py
& "C:\Users\User\Desktop\law_summary_v0.1\.venv\Scripts\python.exe" .\lawtool.py
```

## 새 환경을 만드는 경우에만
Python 3.12 64bit가 설치되어 있어야 합니다.
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --only-binary=llama-cpp-python --no-deps --index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 llama-cpp-python==0.3.35
.\.venv\Scripts\python.exe -m pip install diskcache jinja2 numpy typing-extensions
.\.venv\Scripts\python.exe -m pip install -r requirements-cuda.txt
```
VS Code 인터프리터를 새 폴더의 .venv/Scripts/python.exe로 선택합니다.
HWP 입력은 Java 17 이상 필요: `java -version`으로 확인하세요.

## 1. 모델 다운로드
get_model.py를 실행하면 토큰 입력을 받고 Hugging Face에서 가중치를 직접 다운로드합니다.
공개 모델도 토큰 입력 단계가 나오며 Enter면 비인증 다운로드입니다. 토큰은 숨김 입력이며 저장하지 않습니다.
다운로드 완료 후 config.json의 model_path를 자동으로 변경합니다.

```powershell
.\.venv\Scripts\python.exe .\get_model.py
```
다른 모델은 get_model.py의 REPO_ID와 FILENAME을 변경해 실험합니다.
단일 GGUF 모델을 대상으로 하며 모델 구조 지원/메모리 요구량은 별도 확인이 필요합니다.
파일 목록에서 고르거나 기존 모델을 선택하고 싶으면 아래 선택형 도구도 사용할 수 있습니다.
```powershell
.\.venv\Scripts\python.exe .\tools\download_model.py
```
이미 받은 GGUF는 models 폴더에 복사한 뒤 선택형 도구의 2번으로 활성화하면 됩니다.

## 2. 문서 넣기 및 실행
input 폴더에 HWP 또는 HWPX를 넣으세요. 가상 문서 test_law_amendment.hwp가 기본 포함됩니다.
실제 문서만 처리하려면 테스트 문서를 input 밖으로 옮기세요.

추출만 시험:
```powershell
.\.venv\Scripts\python.exe .\lawtool.py --extract-only
```
모델 요약과 엑셀 저장:
```powershell
.\.venv\Scripts\python.exe .\lawtool.py
```
이제 lawtool.py가 CUDA DLL 경로 등록과 사전 로딩을 직접 수행합니다.
run_lawtool.py는 호환용이며 선택적으로 사용할 수 있습니다.

## 처리 기준
- ‘주요내용’ 제목부터 같은 단계 다음 목차 전까지 추출해 그 본문만 LLM에 전달합니다.
- 개정이유/참고사항 등 별도 항목을 요약하지 않습니다.
- 한 문서 내 같은 법령은 한 행. 여러 개정사항은 같은 셀에 `-`와 줄바꿈으로 나열합니다.
- 핵심 대상/조건/수치와 원문 조문을 유지하고 명사형으로 요약합니다.
- 엑셀 열: 법령명 / 주요내용 / 소관기관 / 기한 / 비고.
- 소관기관, 기한, 비고는 현재 빈칸입니다.
- 주요내용이나 법령명을 찾지 못한 문서는 확인 필요로 기록합니다.
- 목차 자동번호나 복잡한 표 등 모든 문서 양식을 완벽하게 지원하지는 않습니다.
- 인식 가능한 다음 제목이 없으면 문서 끝까지 추출합니다. sections.json에서 boundary가 document_end인 경우 범위를 확인하세요.

## 결과
output 아래 실행시각별 폴더에 저장됩니다.
- summary.xlsx: 성공한 문서 요약. 실패만 있으면 제목 행만 존재합니다.
- report.json: 사용 모델/설정, 성공 파일, 오류 정보.
- 문서별 extracted.txt: 추출 전체 원문. 전체 원문을 모델에 보내지는 않습니다.
- 문서별 sections.json: 실제 모델 입력 구간.
- 문서별 error.txt: 실패 상세.

테스트 문서의 기대 결과:
- 일반회계로부터 영유아특별회계로의 전입금 규정 정비(안 제5조)
- 지원 대상을 국공립어린이집에서 민간어린이집까지 확대(안 제7조)
- 사업 실적 보고기한을 회계연도 종료 후 30일에서 60일 이내로 변경(안 제9조)
위 문구는 검토용 예시입니다. 모델 표현은 달라질 수 있습니다.
참고사항의 999억원과 의견제출 기한은 요약에 들어가면 안 됩니다.

## 오류 진단
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-diagnostic.txt
.\.venv\Scripts\python.exe .\diagnose_llama.py
```
llama_diagnostic.txt에 결과가 저장됩니다.
잘못된 일반 Python으로 실행하면 설치된 패키지가 없다고 나옵니다. .venv 인터프리터를 확인하세요.
GPU 메모리 부족은 config.json의 n_ctx/n_batch를 줄여 시험합니다.
현재 통합 로더는 Windows GPU용 패키지를 기준으로 구성했습니다.

## 확인된 범위
사용자 PC에서 DLL 사전 로딩 및 RTX 4060 인식, GPU offload=True가 확인됐습니다.
아직 실제 모델 로딩/요약 성공 결과는 확인되지 않았습니다.
코드 테스트 및 샘플 HWP 구간 추출은 검증했습니다. 구체 검증은 VALIDATION.md 참고.
