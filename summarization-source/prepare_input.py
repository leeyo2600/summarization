"""Extract the consultation archive preserving provenance and separating references."""
import io, json, re, zipfile, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def prepare():
    parent=ROOT/'input'/'prepared'
    parent.mkdir(exist_ok=True)
    dest=Path(tempfile.mkdtemp(prefix='batch_',dir=parent))
    records=[]
    def walk(data, chain=(), depth=0):
        if depth>8: raise ValueError('Archive nesting limit exceeded')
        with zipfile.ZipFile(io.BytesIO(data), metadata_encoding='cp949') as archive:
            for entry in archive.infolist():
                if entry.is_dir(): continue
                name=entry.filename
                if entry.file_size>100_000_000: raise ValueError('Archive member too large')
                content=archive.read(entry)
                lineage=chain+(name,)
                suffix=Path(name).suffix.lower()
                if suffix=='.zip': walk(content,lineage,depth+1)
                elif suffix in {'.hwp','.hwpx'}:
                    category='reference' if depth==0 else 'source'
                    if re.search(r'검토.*(?:서식|양식)|의견.*(?:서식|양식)|(?:서식|양식).*의견',name): category='attachments'
                    if any(s in name for s in ('양식','서식','조문별 개정이유서','개정안 전문','개정안 별첨')): category='attachments'
                    if name.startswith('(개정안) 공항안전'): category='attachments'
                    group=next((re.search(r'(?:^|/)(\d+)\.',s).group(1) for s in chain if re.search(r'(?:^|/)(\d+)\.',s)), '0')
                    if group=='19': category='excluded'
                    actual='.hwpx' if content.startswith(b'PK') else '.hwp' if content.startswith(bytes.fromhex('d0cf11e0a1b11ae1')) else suffix
                    path=dest/category/f'{int(group):02d}_{len(records):03d}{actual}'
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(content)
                    records.append({'path':str(path),'original':list(lineage),'category':category,'group':group})
    walk((ROOT/'input'/'opinions_source.zip').read_bytes())
    (dest/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:sum(r['category']==k for r in records) for k in ('source','reference','attachments')})
    return dest/'source'

if __name__=='__main__': prepare()
