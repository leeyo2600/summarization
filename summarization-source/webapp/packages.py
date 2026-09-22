"""Bounded archive reading and source-backed consultation metadata."""
import io
import re
import zipfile
from pathlib import PurePosixPath, Path
from pypdf import PdfReader
from lawtool import read_hwpx, convert_hwp, ReviewRequired


def unpack(files):
    documents=[]; used=0; count=0
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
                    visit(path.name,archive.read(entry),scope+(name,)+path.parts[:-1],depth+1)
        elif suffix in {'.hwp','.hwpx','.pdf'}:
            documents.append({'name':name,'data':data,'scope':scope,'source':' / '.join(scope+(name,))})
    for index,(name,data) in enumerate(files):
        visit(name,data,(str(index),) if name.lower().endswith('.zip') else ('loose',),0)
    return documents


def metadata(text):
    compact=re.sub(r'\s+','',text)
    title=re.search(r'제목(.*?)(?:1\.|귀\s*기관)',text,re.S)
    law=re.search(r'[「｢]([^」｣]+)[」｣]',title.group(1) if title else '')
    header=text.split('수신',1)[0]
    sender=[re.sub(r'\s+','',line) for line in header.splitlines() if re.fullmatch(r'[가-힣\s]+(?:부|청|위원회)\s*',line.strip())]
    department=re.search(r'시행([가-힣A-Za-z0-9]+)-\d+',compact)
    dates=re.findall(r"(?<!\d)(20\d{2}|\d{2})[.년](\d{1,2})[.월](\d{1,2})[.일]?(?:\([월화수목금토일]\))?까지",compact)
    dates=list(dict.fromkeys(f'{int(y) if len(y)==4 else 2000+int(y):04d}-{int(m):02d}-{int(d):02d}' for y,m,d in dates))
    return {'law':re.sub(r'\s+',' ',law.group(1)).strip() if law else '',
            'agency':sender[-1] if sender else '',
            'department':department.group(1) if department else '',
            'deadline':dates[0] if len(dates)==1 else '',
            'warnings':[] if len(dates)==1 else ['제출기한 확인 필요']}


def prepare(files,folder,cfg):
    docs=unpack(files); letters=[]; bills=[]; ignored=[]
    for index,doc in enumerate(docs):
        if re.search(r'(검토.*(?:양식|의견서)|검토서\(양식\))',doc['name']):
            ignored.append(doc['source']); continue
        suffix=Path(doc['name']).suffix.lower()
        if suffix=='.pdf':
            reader=PdfReader(io.BytesIO(doc['data']))
            text='\n'.join(page.extract_text() or '' for page in reader.pages)
            if not text.strip(): raise ReviewRequired('이미지 PDF는 OCR 필요: '+doc['name'])
            if '수신' in text and '제목' in text and '시행' in text:
                doc.update(metadata(text)); doc['text']=text; letters.append(doc)
            else: raise ReviewRequired('요청공문으로 확인되지 않은 PDF: '+doc['name'])
        else:
            path=Path(folder)/f'source_{index}{suffix}'; path.write_bytes(doc['data'])
            target=convert_hwp(path,folder,cfg) if suffix=='.hwp' else path
            doc['lines']=read_hwpx(target); bills.append(doc)
    groups={}
    for bill in bills:
        candidates=[letter for letter in letters if bill['scope'][:len(letter['scope'])]==letter['scope']]
        if candidates:
            depth=max(len(x['scope']) for x in candidates)
            candidates=[x for x in candidates if len(x['scope'])==depth]
            if len(candidates)>1:
                compact=re.sub(r'\s+','','\n'.join(bill['lines'])+bill['name'])
                candidates=[x for x in candidates if x['law'] and re.sub(r'\s+','',x['law']) in compact]
            if len(candidates)!=1: raise ReviewRequired('공문-법안 연결 확인 필요: '+bill['source'])
            letter=candidates[0]
            if not letter['law']: raise ReviewRequired('공문에서 법령명 확인 필요: '+letter['source'])
            key=letter['source']
        else:
            letter=None; key=bill['source']
        group=groups.setdefault(key,{'name':key,'letter':letter,'documents':[]})
        group['documents'].append(bill)
    for letter in letters:
        if letter['source'] not in groups: raise ReviewRequired('공문에 연결된 법안이 없습니다: '+letter['source'])
    return list(groups.values()),ignored


def representative(lines):
    names=re.findall(r'([가-힣]{2,5})\s*의원\s*대표\s*발의','\n'.join(lines))
    names=list(dict.fromkeys(names))
    return names[0] if len(names)==1 else ''
