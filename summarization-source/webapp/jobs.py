"""Document jobs run independently of UI rerenders."""
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from lawtool import ROOT, read_hwpx, convert_hwp, find_sections, write_excel, TITLE, ReviewRequired
from webapp.api import ApiSummarizer, BASE_URL, MODEL, CONTEXT, OUTPUT
from webapp.packages import prepare, representative

EXECUTOR=ThreadPoolExecutor(max_workers=2)


def document_targets(lines):
    """Use sections for identifying laws only, never for limiting source content."""
    try:
        return list(dict.fromkeys(section['law'] for section in find_sections(lines)))
    except ReviewRequired:
        titles=[]
        for line in lines:
            match=TITLE.fullmatch(line.replace('｢','「').replace('｣','」'))
            if match: titles.append(match.group('law').strip())
        titles=list(dict.fromkeys(titles))
        if len(titles)!=1:
            raise ReviewRequired('문서 전체의 요약 대상 법령을 확정하지 못했습니다. 원문 검토가 필요합니다.')
        return titles

def process(files,key,progress):
    engine=ApiSummarizer(BASE_URL,key,MODEL,CONTEXT,OUTPUT,'max_completion_tokens')
    cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    rows=[]; reports=[]; issues=[]
    with tempfile.TemporaryDirectory(prefix='law_upload_') as tmp:
        try:
            groups,ignored=prepare(files,Path(tmp),cfg)
        except Exception as error:
            groups=[]; ignored=[]
            issues.append({'file':'입력 묶음','error':str(error) if isinstance(error,ValueError) else '문서 읽기 실패: '+type(error).__name__})
        for index,group in enumerate(groups):
            name=group['name']; letter=group['letter']
            progress.put((index,len(groups),name))
            try:
                lines=[line for doc in group['documents'] for line in doc['lines']]
                full_text='\n\n'.join('첨부문서: '+doc['name']+'\n'+'\n'.join(doc['lines']) for doc in group['documents'])
                laws=[letter['law']] if letter else document_targets(lines)
                before=len(engine.audit); sections=[]
                for doc in group['documents']:
                    try: sections.extend(find_sections(doc['lines']))
                    except ReviewRequired: pass
                member=representative(lines) if len(laws)==1 else ''
                agency=' / '.join(x for x in (letter['agency'],letter['department']) if x) if letter else ''
                deadline=letter['deadline'] if letter else ''
                pending=[]
                for law in laws:
                    main_content='\n'.join(section['text'] for section in sections if section['law']==law)
                    display=law+(f'({member} 의원 대표발의)' if member else '')
                    changed=engine.summarize_document(full_text,law,main_content)
                    pending.append([display,'\n'.join('- '+x for x in changed),agency,deadline,''])
                rows.extend(pending)
                reports.append({'file':name,'source_scope':'main_content_with_full_document_support','laws':laws,'representative':member,'letter_metadata':{k:letter[k] for k in ('source','agency','department','deadline','warnings')} if letter else None,'attachments':[d['source'] for d in group['documents']],'source_chars':len(full_text),'requests':engine.audit[before:]})
            except Exception as error:
                message=str(error) if isinstance(error,ValueError) else '문서 처리 실패: '+type(error).__name__
                issues.append({'file':name,'error':message})
            progress.put((index+1,len(groups),name))
    destination=ROOT/'output'/('법령요약_'+datetime.now().strftime('%Y-%m-%d_%H시%M분%S초_%f'))
    destination.mkdir(parents=True)
    excel=destination/'법령_주요내용_요약.xlsx'
    if rows: write_excel(rows,excel,headers=['법령명','주요내용','소관기관','제출기한','비고(소관부서)'])
    report={'model':MODEL,'ignored_templates':ignored,'context_limit':CONTEXT,'output_limit':OUTPUT,'token_estimate':'UTF-8 bytes, not exact model tokens','files':reports,'issues':issues}
    raw=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    (destination/'처리기록.json').write_bytes(raw)
    return {'xlsx':excel.read_bytes() if rows else None,'report':raw,'rows':rows,'issues':issues,'success':len(reports),'total':len(groups) or len(issues),'folder':str(destination)}
