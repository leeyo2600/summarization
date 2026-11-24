"""Local-only law amendment summarizer. No inference network calls."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys, traceback, zipfile, tempfile, shutil
from pathlib import Path
from datetime import datetime
from defusedxml import ElementTree as ET
ROOT = Path(__file__).resolve().parent

class ReviewRequired(ValueError): pass

def local(tag): return tag.rsplit('}',1)[-1]

def read_hwpx(path):
    """Walk XML in order; emit nested table paragraphs exactly once."""
    with Path(path).open('rb') as stream:
        if b'DRM' in stream.read(128):
            raise ReviewRequired('Fasoo DRM 암호화 문서입니다. 권한 있는 환경에서 보호 해제된 원문을 제공해야 합니다.')
    lines=[]
    with zipfile.ZipFile(path) as z:
        names=sorted((n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)),
                     key=lambda n:int(re.search(r'(\d+)\.xml',n).group(1)))
        if not names: raise ReviewRequired('HWPX 본문 section XML이 없습니다.')
        if sum(z.getinfo(n).file_size for n in names)>100_000_000:
            raise ReviewRequired('본문 XML이 100MB를 초과합니다.')
        def walk(e):
            tag=local(e.tag)
            if tag in {'header','footer','footNote','endNote'}: return
            if tag=='t':
                if e.text: buf.append(e.text)
                for child in e:
                    walk(child)
                    if child.tail: buf.append(child.tail)
                return
            if tag in {'lineBreak','br'}: flush()
            if tag=='tab': buf.append(' ')
            if tag=='p': flush()
            for child in e: walk(child)
            if tag in {'p','tc','tr'}: flush()
        def flush():
            s=''.join(buf).strip(); buf.clear()
            if s: lines.append(s)
        for name in names:
            buf=[]; walk(ET.fromstring(z.read(name))); flush()
    if not lines: raise ReviewRequired('본문 텍스트가 없습니다. 이미지 문서는 OCR이 필요합니다.')
    return lines

def collect_documents(path, temp_root):
    """Expand an input ZIP recursively (the real package has nested ZIPs)."""
    path = Path(path)
    if path.suffix.lower() in {'.hwp', '.hwpx'}:
        return [path]
    if path.suffix.lower() != '.zip':
        raise ValueError(f'Unsupported input format: {path.name}')
    Path(temp_root).mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='pkg_', dir=str(temp_root)))
    with zipfile.ZipFile(path) as z:
        z.extractall(out)
    docs = []
    for p in out.rglob('*'):
        if p.suffix.lower() in {'.hwp', '.hwpx'}:
            docs.append(p)
        elif p.suffix.lower() == '.zip':
            docs.extend(collect_documents(p, Path(temp_root)))
    # ZIPs in this package contain legacy CP949 filenames.  Java and Windows
    # can disagree on those decoded names, so hand downstream stages stable
    # ASCII paths while retaining the original name only in the report.
    safe=[]
    for i, doc in enumerate(sorted(docs, key=lambda p: str(p)), 1):
        fd, name = tempfile.mkstemp(prefix=f'doc_{i:04d}_', suffix=doc.suffix.lower(), dir=str(temp_root))
        import os
        os.close(fd)
        target=Path(name)
        shutil.copy2(doc, target)
        safe.append(target)
    return safe

# Match a heading only, not a table-of-contents entry ending in page numbers.
HEAD=re.compile(r'^\s*(?P<prefix>(?:\d+\s*[.)]|[가-하]\s*[.)]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.\s]*|[□■○●◆◇▶]+)\s*)?(?:주\s*요\s*(?:개\s*정\s*)?내\s*용|개\s*정\s*주\s*요\s*내\s*용)\s*[:：]?\s*$')
STOP=re.compile(r'^\s*(?:(?:\d+|[가-하ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)[.)]?\s*|[□■○●◆◇▶]\s*)?(?:참고\s*사항|의견\s*제출|입법\s*예고|행정\s*예고|개정\s*이유|제정\s*이유|제안\s*이유|추진\s*배경|기대\s*효과|향후\s*(?:계획|일정)|추진\s*(?:계획|일정)|신[ㆍ·]?구조문\s*대비표|관계\s*법령|붙임|첨부|검토\s*의견)(?:\s|[:：(]|$)')
TITLE=re.compile(r'^\s*(?:[□■○●◆◇▶]|\d+[.)])?\s*[「『]?(.{2,100}?(?:법률|법|시행령|시행규칙|규정|조례|규칙))[」』]?\s*(?:(?:일부|전부)?\s*(?:개정|제정)(?:법률|령|규칙)?\s*안|일부개정령안|전부개정령안)?\s*(?:입법예고|행정예고)?\s*$')
def level(prefix):
    t=(prefix or '').strip()
    if re.match(r'\d',t): return 'number'
    if re.match(r'[가-하]',t): return 'korean'
    if re.match(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]',t): return 'roman'
    return 'symbol' if t else None

# Real bills also combine the reason and main provisions in one heading.
HEAD=re.compile(HEAD.pattern.replace('(?:주\\s*요', '(?:(?:개정|제정|제안)\\s*이유\\s*및\\s*주요내용|주\\s*요'))
TITLE=re.compile(TITLE.pattern.replace('규정|조례|규칙', '규정|조례|규칙|지침|고시').replace('법률|령|규칙', '법률|령|규칙|예규|고시|훈령').replace('\\s*안|', '\\s*\\(?안\\)?|'))
TITLE=re.compile(TITLE.pattern.replace('시행령|','시행령|시험령|'))
TITLE=re.compile(r'^\s*(?:[□■○●◆◇▶]|\d+[.)])?\s*[「『]?(?P<law>[^「」『』:：*\n]{2,100}?(?:법률|법|시행령|시험령|시행규칙|규정|조례|규칙|지침|고시))[」』]?\s*(?:(?:일부|전부)?\s*(?:개정|제정)(?:법률|령|규칙|예규|고시|훈령)?\s*\(?안\)?|안)?\s*(?:입법예고|행정예고)?\s*$')

def find_sections(lines):
    lines=join_split_titles(lines)
    lines=[x.replace('｢','「').replace('｣','」').replace('재입법예고','입법예고') for x in lines]
    result=[]
    for start,line in enumerate(lines):
        m=HEAD.fullmatch(line)
        if not m: continue
        body=[]; kind=level(m.group('prefix')); boundary='document_end'
        for s in lines[start+1:]:
            if HEAD.fullmatch(s) or STOP.match(s) or (TITLE.fullmatch(s) and not re.match(r'^\s*[-*가-하][ .)]',s)):
                boundary=s; break
            # Stop at a new heading of the same numbered level.
            same=False
            if kind=='number':
                next_number=int(re.search(r'\d+',m.group('prefix')).group())+1
                same=bool(re.match(r'^\s*'+str(next_number)+re.escape(m.group('prefix').strip()[-1])+r'\s*\S',s))
            if kind=='roman': same=bool(re.match(r'^\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[.\s]+\S',s))
            if kind=='korean' and re.match(r'^\s*[가-하][.)]\s*\S',s): same=True
            if kind=='symbol' and s.lstrip().startswith(m.group('prefix').strip()): same=True
            if same: boundary=s; break
            body.append(s)
        if not body: continue
        # Empty TOC/heading sequences are not content.
        if len(''.join(body))<12: continue
        title=''
        for candidate in list(reversed(lines[:start]))+lines[start+1:]:
            if re.match(r'^\s*[-*가-하][ .)]',candidate): continue
            tm=TITLE.fullmatch(candidate)
            if tm: title=tm.group(1).strip(); break
        if not title: raise ReviewRequired('주요내용은 찾았으나 법령명을 확정하지 못했습니다. 추출 원문을 확인하세요.')
        result.append({'law':title,'text':'\n'.join(body),'heading_line':start+1,'boundary':boundary})
    if not result: raise ReviewRequired('주요내용 제목/본문을 찾지 못했습니다. 전체 문서는 요약하지 않았습니다.')
    return result


def join_split_titles(lines):
    """Join a title whose amendment suffix was extracted as a separate paragraph."""
    result=[]
    for line in lines:
        if re.fullmatch(r'\s*(?:일부|전부)?\s*(?:개정|제정)(?:법률|령|규칙)?안\s*',line) and result:
            result[-1]+=' '+line.strip()
        else:
            result.append(line)
    return result

def convert_hwp(src, folder, cfg):
    jar=ROOT/cfg['converter_jar']
    if not jar.exists():
        from webapp.converter_runtime import ensure_converter
        try: ensure_converter(jar)
        except ValueError as error: raise ReviewRequired(str(error)) from error
    out=folder/(src.stem+'.hwpx')
    try:
        r=subprocess.run(['java','-jar',str(jar),str(src.resolve()),str(out.resolve())],capture_output=True,timeout=180)
    except FileNotFoundError: raise ReviewRequired('Java 실행 환경이 없습니다. Java 17 설치 후 VS Code를 다시 실행하세요.')
    if r.returncode or not out.exists():
        raise ReviewRequired('HWP 변환 실패: '+r.stderr.decode('utf-8',errors='replace')[-1800:])
    return out

SYSTEM = """법령의 주요내용을 짧고 명확하게 요약한다. 문서 전체의 상세 요약이나 조문별 목록을 만드는 작업이 아니다.

[규칙]
1. '우선 요약할 주요내용'을 요약의 범위와 항목 구성의 기준으로 삼는다. 이 구간이 비어 있으면 문서 전체에서 주요내용을 먼저 찾는다. 주요내용이 아예 없는 문서만 이유·본문에서 핵심 제·개정사항을 선별한다.
2. 제정이유·개정이유·제안이유, 본문, 대비표, 부칙·별표는 보조 근거다. 주요내용만으로 대상이나 변경 방향을 알 수 없을 때, 또는 핵심 변경을 빠뜨려 의미가 달라질 때만 필요한 정보를 보완한다. 다른 구간에 변경사항이 있다는 이유만으로 모두 추가하지 않는다.
3. 대상과 변경 방향은 반드시 남긴다. 수치·비율·조건·산정방식은 생략하면 적용 범위나 변경 의미가 달라질 때 유지한다. 단순 인용 조문번호·반복 표현·세부 나열은 생략할 수 있다. 의미를 보존할 수 있으면 짧게, 복잡한 조건 때문에 필요한 경우만 길게 쓴다.
4. 문서에서 확인되는 사실만 사용한다. 외부 지식으로 보충하거나 원문보다 구체화하지 않는다. 배경·필요성·기대효과는 출력하지 않는다.
5. 서로 독립된 개정사항은 각각 분리하되, 하나의 변경에 연결된 조건과 결과는 함께 작성한다.
6. 각 개정사항은 반드시 '- '로 시작한다.
7. 현행 규정·인용된 다른 법령·과거 개정 이력은 이번 변경으로 오인하지 않는다. 신·구조문대비표는 현행과 개정안을 구별한다. 제정안은 새로 도입되는 제도·의무·절차를 정리한다.
8. 같은 변경이 여러 구간에 반복되면 한 번만 작성한다. 구체적인 대상·조건은 관련 조문과 대조하되, 근거끼리 충돌하여 확정할 수 없는 내용은 추측하지 않는다.
9. 부칙의 시행일·경과조치·적용례는 주요내용의 핵심이거나 이를 빼면 요약이 오해를 낳는 경우만 포함한다. 의견 제출 방법·연락처·입법예고 기간·목차·단순 법령 제목은 제외한다.
10. 요약 대상 법령이 지정되면 그 법령의 제·개정사항만 작성한다. 함께 수록되거나 인용된 다른 법령의 내용을 섞지 않는다.
11. 각 항목은 '대상 + 무엇을 어떻게 변경하는지'가 드러나는 간결한 명사형으로 작성한다. '개선하려는 것임' 같은 목적만 적지 않는다. 확실한 제·개정사항이 없으면 {"items":[]}를 출력한다.
12. 원칙적으로 주요내용 원문보다 짧게 작성한다. 이미 간결한 항목은 그대로 유지해도 된다. 글자 수·항목 수를 일률적으로 맞추거나 정보를 기계적으로 잘라내지 않는다. 보조자료의 설명을 덧붙여 원문보다 길게 늘리지 않는다.

[예시: 짧게 정리할 수 있는 경우]
주요내용: 특별사법경찰 부서 과장급 직위에 대한 보직관리 규정을 신설하려는 것임(안 제46조).
출력: {"items":["- 특별사법경찰 부서 과장급 직위 보직관리 규정 신설"]}

[예시: 보조자료의 세부사항을 추가하지 않는 경우]
주요내용: 신청서 제출기한을 7일에서 14일로 연장
본문·부칙: 신청서 서식의 항목별 기재 방법, 제출 부서와 시행일을 규정함.
출력: {"items":["- 신청서 제출기한을 7일에서 14일로 연장"]}

[예시: 이유란에만 변경사항이 있는 경우]
입력:
제정이유: 업무 부담을 줄이기 위해 신청서 제출기한을 7일에서 14일로 연장하려는 것임.
주요내용: 신청 절차 정비
출력:
{"items":["- 신청서 제출기한을 7일에서 14일로 연장"]}

[예시 1: 주요내용이 이미 간결한 경우]
입력:
일반회계로부터 영유아특별회계로의 전입금 규정 정비(안 제5조)

출력:
{"items":["- 일반회계로부터 영유아특별회계로의 전입금 규정 정비(안 제5조)"]}

[예시 2: 개정이유와 주요내용이 합쳐진 경우]
입력:
학령인구 감소 등 교육환경 변화에 따라 국가가 지방자치단체에 교부하는 교육기관 등의 설치ㆍ경영을 위한 재원이 전면 개편되는 것에 맞추어, 개별소비세, 교통ㆍ에너지ㆍ환경세, 주세의 납세의무자에 부과하는 교육세 세입 예산액의 100분의 40에 해당하는 금액을 고등ㆍ평생교육지원특별회계의 세입 중 일반회계로부터의 전입금에 추가하려는 것임.

출력:
{"items":["- 개별소비세·교통·에너지·환경세·주세의 납세의무자에게 부과하는 교육세 세입 예산액의 100분의 40에 해당하는 금액을 고등·평생교육지원특별회계의 세입 중 일반회계로부터의 전입금에 추가"]}

[예시 3: 여러 개정사항이 한 문단에 있는 경우]
입력:
소방용품 수집검사 결과 회수ㆍ교환ㆍ폐기 또는 판매중지 등 행정조치의 기준이 되는 중대한 결함의 판단기준을 명확히 하고, 형식승인 및 성능인증 취소 시 분실된 형식승인서ㆍ성능인증서의 제출의무를 제외하며, 성능인증 품목 규정을 행정안전부령으로 일원화하고, 제품검사 신청수량이 101개 이상 500개 이하인 경우 검사수수료를 3퍼센트 할인함.

출력:
{"items":[
"- 소방용품 수집검사 결과 회수·교환·폐기 또는 판매중지 등 행정조치의 기준이 되는 중대한 결함의 판단기준 명확화",
"- 형식승인 및 성능인증 취소 시 분실된 형식승인서·성능인증서의 제출의무 제외",
"- 성능인증 품목 규정을 행정안전부령으로 일원화",
"- 제품검사 신청수량이 101개 이상 500개 이하인 경우 검사수수료를 3퍼센트 할인"
]}

반드시 JSON 형식 {"items":["- 개정사항"]}만 출력한다."""
class Summarizer:
    def __init__(self,cfg):
        from windows_runtime import prepare_windows_dlls
        prepare_windows_dlls()
        import llama_cpp
        if cfg['n_gpu_layers']!=0 and not llama_cpp.llama_supports_gpu_offload():
            raise RuntimeError('GPU 지원 없는 llama-cpp-python입니다. setup_gpu.cmd를 실행하세요. CPU 시험은 config.json의 n_gpu_layers를 0으로 설정합니다.')
        path=ROOT/cfg['model_path']
        if not path.exists(): raise FileNotFoundError(f'모델 파일이 없습니다: {path}')
        self.cfg=cfg
        self.llm=llama_cpp.Llama(model_path=str(path),n_ctx=cfg['n_ctx'],n_gpu_layers=cfg['n_gpu_layers'],
            n_batch=cfg['n_batch'],seed=42,verbose=False)
    def count(self,s): return len(self.llm.tokenize(s.encode('utf-8')))
    def chunks(self,text):
        budget=self.cfg['n_ctx']-self.cfg['max_tokens']-self.count(SYSTEM)-300
        if budget<300: raise ValueError('n_ctx가 너무 작습니다.')
        chunks=[]; current=''
        # Preserve paragraphs; only split very long paragraphs by Unicode characters.
        for line in text.splitlines():
            if self.count(line)>budget:
                if current: chunks.append(current); current=''
                while line:
                    lo,hi=1,len(line)
                    while lo<hi:
                        mid=(lo+hi+1)//2
                        if self.count(line[:mid])<=budget: lo=mid
                        else: hi=mid-1
                    chunks.append(line[:lo]); line=line[lo:]
                continue
            candidate=current+'\n'+line if current else line
            if self.count(candidate)>budget:
                chunks.append(current); current=line
            else: current=candidate
        if current: chunks.append(current)
        return chunks
    def summarize(self,text):
        items=[]
        for chunk in self.chunks(text):
            response=self.llm.create_chat_completion(messages=[{'role':'system','content':SYSTEM},
                {'role':'user','content':'<주요내용>\n'+chunk+'\n</주요내용>'}],
                response_format={'type':'json_object'},temperature=self.cfg['temperature'],max_tokens=self.cfg['max_tokens'])
            choice=response['choices'][0]
            if choice.get('finish_reason')=='length': raise ReviewRequired('요약 출력 길이 초과: max_tokens를 늘리거나 입력을 더 작게 나눠야 합니다.')
            try: obj=json.loads(choice['message']['content'])
            except (ValueError,TypeError): raise ReviewRequired('모델 JSON 응답을 해석할 수 없습니다.')
            values=obj.get('items') if isinstance(obj,dict) else None
            if not isinstance(values,list) or not values or not all(isinstance(v,str) and v.strip() for v in values):
                raise ReviewRequired('모델 응답의 items 형식이 올바르지 않습니다.')
            for item in values:
                item=re.sub(r'^\s*[-•]\s*','',item).strip().replace('\n',' ')
                # Reject new numeric facts/article identifiers, ignoring formatting spaces.
                original=re.sub(r'\s','',chunk)
                original=re.sub(r'안(\d+조)',r'안제\1',original)
                for num in re.findall(r'\d+(?:[.,]\d+)*',item):
                    if num not in original: raise ReviewRequired('원문에 없는 숫자가 요약에 생성되었습니다: '+num)
                for article in re.findall(r'제\s*\d+\s*조(?:\s*의\s*\d+)?',item):
                    if re.sub(r'\s','',article) not in original: raise ReviewRequired('원문에 없는 조문이 생성되었습니다: '+article)
                if item not in items: items.append(item)
        return items

def write_excel(rows,path,headers=None,widths=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb=Workbook(); ws=wb.active; ws.title='법령 개정 요약'
    ws.append(headers or ['법령명','주요내용','소관기관','기한','비고'])
    for row in rows:
        if any(isinstance(value,str) and len(value)>32767 for value in row): raise ReviewRequired('엑셀 셀 글자 수 한도 초과')
        ws.append(row)
        for c in ws[ws.max_row]: c.data_type='s' # Prevent Excel formula interpretation.
    for c in ws[1]: c.font=Font(bold=True,color='FFFFFF'); c.fill=PatternFill('solid',fgColor='23465C')
    for r in ws.iter_rows(min_row=2):
        for c in r: c.alignment=Alignment(vertical='top',wrap_text=True)
    for i,w in enumerate(widths or [38,105,22,20,25],1): ws.column_dimensions[get_column_letter(i)].width=w
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    wb.save(path)

def run(input_path,extract_only=False):
    cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    unpack = ROOT/'output'/'_input_unpack'
    if input_path.is_file() and input_path.suffix.lower()=='.zip':
        files = collect_documents(input_path, unpack)
    else:
        candidates=[input_path] if input_path.is_file() else sorted(p for p in input_path.rglob('*') if p.suffix.lower() in {'.hwp','.hwpx','.zip'})
        files=[]
        for p in candidates:
            files.extend(collect_documents(p, unpack) if p.suffix.lower()=='.zip' else [p])
    if not files: raise ValueError('input 폴더에 HWP 또는 HWPX 파일을 넣어주세요.')
    folder=ROOT/'output'/datetime.now().strftime('%Y%m%d_%H%M%S_%f'); folder.mkdir(parents=True)
    rows=[]; issues=[]; records=[]; engine=None
    if not extract_only: engine=Summarizer(cfg)
    for idx,src in enumerate(files,1):
        print(f'[{idx}/{len(files)}] {src.name}',flush=True)
        work=folder/f'{idx:03d}_{src.stem}'; work.mkdir()
        try:
            target=convert_hwp(src,work,cfg) if src.suffix.lower()=='.hwp' else src
            lines=read_hwpx(target)
            (work/'extracted.txt').write_text('\n'.join(lines),encoding='utf-8')
            sections=find_sections(lines)
            (work/'sections.json').write_text(json.dumps(sections,ensure_ascii=False,indent=2),encoding='utf-8')
            if extract_only:
                records.append({'source':str(src),'status':'extracted','sections':sections}); continue
            if engine is None: engine=Summarizer(cfg)
            # Commit a file only after ALL sections succeed.
            grouped={}
            for sec in sections:
                grouped.setdefault(sec['law'],[]).extend(engine.summarize(sec['text']))
            newrows=[]
            for law,items in grouped.items():
                summary='\n'.join('- '+v for v in dict.fromkeys(items))
                if len(summary)>32767: raise ReviewRequired('요약이 엑셀 셀 한도 초과')
                meta = next((s for s in sections if s['law']==law), {})
                newrows.append([law,summary,meta.get('agency',''),meta.get('deadline',''),meta.get('note','')])
            rows.extend(newrows)
            records.append({'source':str(src),'status':'summarized','laws':list(grouped)})
        except Exception as e:
            issues.append({'source':str(src),'error':str(e)})
            (work/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            print('  확인 필요: '+str(e),flush=True)
    (folder/'report.json').write_text(json.dumps({'mode':'extract_only' if extract_only else 'summary','model_path':cfg.get('model_path'),'model_source':cfg.get('model_source'), 'settings':{k:cfg.get(k) for k in ['n_ctx','n_gpu_layers','max_tokens','temperature']},'files':records,'issues':issues},ensure_ascii=False,indent=2),encoding='utf-8')
    if not extract_only: write_excel(rows,folder/'summary.xlsx')
    print(f'완료: {len(records)}개 / 확인 필요: {len(issues)}개\n결과 폴더: {folder}')
    if not extract_only and not rows: print('성공한 요약이 없어 엑셀에는 열 제목만 있습니다.')
    return 2 if issues else 0

if __name__=='__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=ROOT/'input'/'source')
    parser.add_argument('--extract-only',action='store_true',help='모델 없이 변환/주요내용 추출만 시험')
    args=parser.parse_args()
    try: sys.exit(run(args.input,args.extract_only))
    except Exception:
        traceback.print_exc(); sys.exit(1)
