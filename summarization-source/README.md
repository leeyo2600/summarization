# 법령 의견조회 요약 웹앱

주요내용을 중심으로 기존 제도에서 달라지는 점을 요약하고 엑셀로 출력하는 로컬 웹앱입니다.
이유·본문·대비표는 부족한 정보를 보완하는 데 사용합니다.

## 실행 (Windows / Python 3.12)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe start_web.py
```

HWPX·공문 PDF만 사용할 때는 Java가 필요하지 않습니다. HWP를 사용하려면 Java 17 이상을 설치하고 다음을 실행하세요.

```powershell
.\.venv\Scripts\python.exe tools/build_converter.py
```

화면에서 API 키를 입력합니다. 사용 모델은 `gpt-6-luna`이며, 모델 ID는 `webapp/api.py`에서 관리합니다. 해당 모델에 접근할 수 있는 API 계정이 필요합니다.
Chat Completions의 `reasoning_effort=none`과 JSON 응답을 사용하며, 컨텍스트 한도는 1,050,000토큰, 앱 출력 예산은 8,192토큰입니다. 입력 크기는 UTF-8 바이트로 보수적으로 검사하고 한도 초과 시 원문을 자르지 않고 오류를 표시합니다.
웹앱은 로컬 모델을 다운로드하거나 실행하지 않습니다.

## 폴더 구성

- `app.py`, `start_web.py`: 화면과 실행 진입점
- `webapp/`: API 요청, ZIP·공문 처리, 정렬 및 작업 실행
- `lawtool.py`, `windows_runtime.py`: 문서·엑셀 공통 처리와 기존 호환 보조 코드
- `assets/`: 화면 스타일과 로고 안내
- `tools/`: HWP 변환기 소스·빌드와 소스 ZIP 생성
- `tests/`: 자동 검증
- `config.json`, `requirements-web.txt`: 변환기 경로 등 설정과 웹앱 의존성
- `output/`: 실행 결과 저장(자동 생성, GitHub 제외)
- `.venv/`: 이 PC의 실행환경(GitHub 제외)

## GitHub용 ZIP 만들기

```powershell
.\.venv\Scripts\python.exe tools/package_source.py
```

`output/source_release_날짜_시간/summarization-source.zip`에 코드·테스트·사용 안내만 저장합니다.
ZIP을 풀어서 내부 파일을 저장소에 올리세요. 원본 업무문서, 결과물, 가상환경, 모델, API 키, 빌드된 JAR는 포함하지 않습니다.

## 입력

- 권장: 요청공문 PDF와 법안 HWP/HWPX를 함께 넣은 의견조회별 ZIP.
- 여러 의견조회 ZIP을 하나로 묶은 통합 ZIP, 내부 첨부 ZIP 지원.
- 원래 폴더 관계를 유지하세요. 연결이 불명확하면 검토 오류로 처리합니다.
- 결과 화면·엑셀·처리기록의 성공 문서는 원본 ZIP/폴더/파일명의 자연 정렬 순서(2 → 10, 10-1 → 10-2)를 따릅니다. 업로드 선택 순서나 ZIP 내부 저장 순서와 무관하며, 실패 문서는 건너뜁니다. 한 문서의 여러 법령은 원문 등장 순서를 유지합니다.
- PDF는 텍스트 기반 요청공문과 입법·행정예고 보조자료를 지원합니다. 스캔 PDF, 그 밖의 PDF 법안, 암호·DRM 문서는 지원하지 않습니다.
- 업로드 합계 100MB, 압축 해제 누적 250MB, 최대 중첩 8단계 및 방문 항목 1,000개.
- 법안 단독 입력 시 공문에서 추출하는 기관·부서·기한은 빈칸입니다.

## 결과

법령명(확인된 대표발의자 병기), 변경점 중심 주요내용, 발신기관/부서, 제출기한을 출력합니다.
비고(행안부 소관부서) 자동 추천은 구현하지 않았으며 빈칸을 유지합니다.
변경점 중심 요약 한 가지 방식으로 실행합니다.
결과와 추출 이력은 `output/`에 저장됩니다. 원문 대조 검토 후 사용하세요.

## 보안·제약

문서 전체에서 추출한 텍스트가 OpenAI API로 전송됩니다. 외부 전송이 허용된 자료만 사용하세요.
API 키는 앱에서 파일로 저장하지 않습니다. 결과·처리기록에는 업무정보가 포함될 수 있습니다.
소스 저장소에 원본 자료, 결과물, API 키, 모델, 가상환경을 올리지 마세요.
공문 메타데이터 추출은 규칙 기반이므로 모든 공문 서식을 보장하지 않습니다.
문서 읽기 오류는 파일명과 함께 기록하고 나머지를 처리합니다. 공문을 못 읽으면 기관·기한은 빈칸입니다. 압축 안전 한도 위반은 중단합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

실제 샘플 ZIP이 없는 환경에서는 샘플 의존 테스트가 생략됩니다. 원본 업무자료는 저장소에 포함하지 않습니다.
