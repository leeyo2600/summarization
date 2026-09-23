"""Bounded archive reading and source-backed consultation metadata."""
import io
import re
import zipfile
from datetime import date
from pathlib import PurePosixPath, Path
from pypdf import PdfReader
from lawtool import read_hwpx, convert_hwp, ReviewRequired


def natural_key(value):
    """Compare digit runs numerically (2 before 10), preserving stable ties."""
    return tuple((1, int(part)) if part.isdecimal() else (0, part.casefold())
                 for part in re.split(r'(\d+)', value) if part)


def document_order(doc):
    # The first scope component is an upload index or 'loose', not a filename.
    # Keep real archive/folder hierarchy; never sort by the synthetic index.
    parts=tuple(doc.get('scope', ()))[1:]+(doc['name'],)
    return tuple(natural_key(part) for part in parts)


def unpack(files,issues=None):
    documents=[]; used=0; count=0
    recoverable=(zipfile.BadZipFile, EOFError, OSError, RuntimeError, NotImplementedError)
    def record(source,error):
        if issues is None: raise error
        issues.append({'file':source,'error':type(error).__name__+': '+str(error)[:500]})
    def visit(name,data,scope,depth):
        nonlocal used,count
        count+=1
        if depth>8 or count>1000: raise ReviewRequired('압축 깊이 또는 파일 수 한도 초과')
        suffix=PurePosixPath(name).suffix.lower()
        if suffix=='.zip':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in archive.infolist():
                    if entry.is_dir(): continue
                    member=entry.filename
                    if not entry.flag_bits & 2048:
                        try: member=member.encode('cp437').decode('cp949')
                        except UnicodeError: pass
                    member=member.replace('\\','/')
                    path=PurePosixPath(member)
                    if path.is_absolute() or '..' in path.parts or ':' in member:
                        raise ReviewRequired('안전하지 않은 압축 경로')
                    used+=entry.file_size
                    if used>250*1024*1024: raise ReviewRequired('압축 해제 용량 250MB 초과')
                    try:
                        visit(path.name,archive.read(entry),scope+(name,)+path.parts[:-1],depth+1)
                    except recoverable as error:
                        record(' / '.join(scope+(name,member)),error)
        elif suffix in {'.hwp','.hwpx','.pdf'}:
            documents.append({'name':name,'data':data,'scope':scope,'source':' / '.join(scope+(name,))})
    for index,(name,data) in enumerate(files):
        try:
            visit(name,data,(str(index),) if name.lower().endswith('.zip') else ('loose',),0)
        except recoverable as error:
            record(name,error)
    return sorted(documents,key=document_order)


def metadata(text):
    compact=re.sub(r'\s+','',text)
    title=re.search(r'제목(.*?)(?:1\.|귀\s*기관)',text,re.S)
    laws=re.findall(r'[「｢]([^」｣]+)[」｣]',title.group(1) if title else '')
    laws=[re.sub(r'\s+',' ',x).strip() for x in laws]
    header=text.split('수신',1)[0]
    sender=[re.sub(r'\s+','',line) for line in header.splitlines() if re.fullmatch(r'[가-힣\s]+(?:부|청|처|원|위원회)\s*',line.strip())]
    department=re.search(r'시행([가-힣A-Za-z0-9]+)-\d+',compact)
    suffix=r'(?:\([월화수목금토일]\))?(?:(\d{1,2}):(\d{2}))?까지'
    matches=re.findall(r'(?<!\d)(20\d{2}|\d{2})[.년](\d{1,2})[.월](\d{1,2})[.일]?'+suffix,compact)
    inferred=False
    if not matches:
        issued=re.search(r'시행[^()]+\((20\d{2})[.년]',compact)
        short=re.findall(r'(?<!\d)(\d{1,2})월(\d{1,2})일'+suffix,compact)
        if issued and short:
            matches=[(issued.group(1),m,d,h,minute) for m,d,h,minute in short]
            inferred=True
    dates=[]
    for y,m,d,h,minute in matches:
        try:
            value=date(int(y) if len(y)==4 else 2000+int(y),int(m),int(d)).isoformat()
            if h:
                if int(h)>23 or int(minute)>59: continue
                value+=f' {int(h):02d}:{int(minute):02d}'
            dates.append(value)
        except ValueError: pass
    dates=list(dict.fromkeys(dates))
    warnings=[] if len(dates)==1 else ['제출기한 확인 필요']
    if inferred: warnings.append('제출기한 연도는 공문 시행연도로 보완: 연말·연초 문서는 검토 필요')
    return {'law':laws[0] if laws else '', 'laws':laws,
            'agency':sender[-1] if sender else '',
            'department':department.group(1) if department else '',
            'deadline':dates[0] if len(dates)==1 else '',
            'warnings':warnings}


def prepare(files,folder,cfg,issues=None):
    issues=issues if issues is not None else []
    docs=unpack(files,issues); letters=[]; bills=[]; ignored=[]
    failed_scopes=[]
    for index,doc in enumerate(docs):
        if re.search(r'양식|서식',doc['name']) and re.search(r'검토|의견',doc['name']):
            ignored.append(doc['source']); continue
        suffix=Path(doc['name']).suffix.lower()
        try:
            if suffix=='.pdf':
                if b'DRM' in doc['data'][:128]:
                    raise ReviewRequired('DRM 보호 PDF입니다. 보호 해제된 원문이 필요하며 이 파일은 건너뜁니다.')
                reader=PdfReader(io.BytesIO(doc['data']))
                text='\n'.join(page.extract_text() or '' for page in reader.pages)
                if not text.strip(): raise ReviewRequired('이미지 PDF는 OCR 필요')
                if '수신' in text and '제목' in text and '시행' in text:
                    doc.update(metadata(text)); doc['text']=text; letters.append(doc)
                elif re.search(r'입법\s*예고|행정\s*예고',text):
                    doc['lines']=[line.strip() for line in text.splitlines() if line.strip()]
                    doc['role']='support'; bills.append(doc)
                else:
                    issues.append({'file':doc['source'],'error':'지원하지 않는 PDF 자료입니다. 공문 및 입법·행정예고 PDF만 처리합니다.'})
            else:
                path=Path(folder)/f'source_{index}{suffix}'; path.write_bytes(doc['data'])
                target=convert_hwp(path,folder,cfg) if suffix=='.hwp' else path
                doc['lines']=read_hwpx(target); bills.append(doc)
        except Exception as error:
            issues.append({'file':doc['source'],'error':type(error).__name__+': '+str(error)[:500]})
            if suffix=='.pdf': failed_scopes.append(doc['scope'])
    groups={}
    for bill in bills:
        candidates=[letter for letter in letters if bill['scope'][:len(letter['scope'])]==letter['scope']]
        # Never attach a parent/other letter after a nearer letter failed to read.
        nearest_valid=max((len(x['scope']) for x in candidates),default=0)
        if any(bill['scope'][:len(scope)]==scope and len(scope)>=nearest_valid for scope in failed_scopes):
            candidates=[]
        if candidates:
            depth=max(len(x['scope']) for x in candidates)
            candidates=[x for x in candidates if len(x['scope'])==depth]
            if len(candidates)>1:
                compact=re.sub(r'\s+','','\n'.join(bill['lines'])+bill['name'])
                candidates=[x for x in candidates if x['law'] and re.sub(r'\s+','',x['law']) in compact]
            if len(candidates)!=1:
                issues.append({'file':bill['source'],'error':'공문-법안 연결 확인 필요: 이 문서는 건너뛰었습니다.'})
                continue
            letter=candidates[0]
            # A unique letter in the same package establishes metadata lineage;
            # actual law names come from the attached bill, not only the letter title.
            key=letter['source']
        else:
            letter=None; key=bill['source']
        group=groups.setdefault(key,{'name':key,'letter':letter,'documents':[]})
        group['documents'].append(bill)
    for letter in letters:
        if letter['source'] not in groups:
            issues.append({'file':letter['source'],'error':'공문에 연결된 읽을 수 있는 법안이 없습니다.'})
    ordered=sorted(groups.values(),key=lambda group: document_order(group['letter'])
                   if group['letter'] else min(document_order(doc) for doc in group['documents']))
    return ordered,ignored


def representative(lines):
    names=re.findall(r'([가-힣\u3400-\u9fff]{2,5})\s*의원\s*대표\s*발의','\n'.join(lines))
    names=list(dict.fromkeys(names))
    return names[0] if len(names)==1 else ''
