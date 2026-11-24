"""Document jobs run independently of UI rerenders."""
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from lawtool import ROOT, find_sections, write_excel, TITLE, ReviewRequired, join_split_titles
from webapp.api import ApiSummarizer, BASE_URL, MODEL, DEPARTMENT_MODEL, CONTEXT, OUTPUT
from webapp.llm_connection import resolve_connection
from webapp.packages import prepare, representative, document_order
from webapp.display import package_number, unit_labels, deadline_label, organization_label
from webapp.gpt_departments import GptDepartmentMatcher as DepartmentMatcher

EXECUTOR=ThreadPoolExecutor(max_workers=2)


def document_targets(lines):
    """Use sections for identifying laws only, never for limiting source content."""
    lines=join_split_titles(lines)
    try:
        return list(dict.fromkeys(section['law'] for section in find_sections(lines)))
    except ReviewRequired:
        titles=[]
        for line in lines:
            if re.match(r'^\s*[-*◦•·]',line): continue
            match=TITLE.fullmatch(line.replace('｢','「').replace('｣','」'))
            if match: titles.append(match.group('law').strip())
        titles=list(dict.fromkeys(titles))
        if len(titles)!=1:
            raise ReviewRequired('문서 전체의 요약 대상 법령을 확정하지 못했습니다. 원문 검토가 필요합니다.')
        return titles


def build_units(group):
    """One row per law and distinct parliamentary bill; keep its source lineage."""
    units={}; unresolved=[]
    for doc in sorted(group['documents'],key=lambda d:(d.get('role')=='support',document_order(d))):
        try:
            sections=find_sections(doc['lines'])
        except ReviewRequired: sections=[]
        try: laws=document_targets(doc['lines'])
        except ReviewRequired:
            unresolved.append(doc); continue
        laws=[law for law in laws if not re.match(r'^\s*[-*◦•·]',law) and not re.fullmatch(r'(?:일부|전부)?(?:개정|제정)(?:법률|법|령|규칙)',law)]
        if not laws:
            unresolved.append(doc); continue
        member=representative(doc['lines']) if len(laws)==1 else ''
        number=''
        if member:
            match=re.search(r'의안번호(\d{4,8})',re.sub(r'\s+','',''.join(doc['lines'][:35])))
            number=match.group(1) if match else doc['source']
        for law in laws:
            # Exclude generic heading fragments which are not real law names.
            if re.fullmatch(r'(?:일부|전부)?(?:개정|제정)(?:법률|법|령|규칙)',law): continue
            key=(law,number)
            existing=[k for k in units if k[0]==law]
            if not number and len(existing)==1: key=existing[0]
            unit=units.setdefault(key,{'law':law,'bill_number':number,'representative':member,'documents':[],'sections':[]})
            if doc not in unit['documents']: unit['documents'].append(doc)
            unit['sections'].extend(s['text'] for s in sections if s['law']==law)
    # Title-free annexes can join only an unambiguous unit; do not guess among bills.
    warnings=[]
    for doc in unresolved:
        candidates=[u for u in units.values() if re.sub(r'\s+','',u['law']) in re.sub(r'\s+','',doc['name'])]
        if len(candidates)!=1 and len(units)==1: candidates=list(units.values())
        if len(candidates)==1:
            candidates[0]['documents'].append(doc)
        else: warnings.append({'file':doc['source'],'error':'첨부자료의 대상 법령 연결 확인 필요: 요약에서 제외했습니다.'})
    if not units: raise ReviewRequired('첨부 법안에서 법령명을 확정하지 못했습니다.')
    return list(units.values()),warnings

def process_web(files,key,progress,law_oc,*,connection=None):
    """The web workflow always includes department recommendations."""
    if not isinstance(law_oc,str) or not law_oc.strip():
        raise ValueError('소관부서 추천에 필요한 국가법령정보 API 키를 입력해주세요.')
    return process(files,key,progress,law_oc=law_oc.strip(),connection=connection)


def process(files,key,progress,law_oc=None,hf_token=None,*,connection=None):
    connection=connection or resolve_connection()
    engine=ApiSummarizer(connection.base_url,key,connection.model,CONTEXT,OUTPUT,connection.token_field)
    cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
    rows=[]; reports=[]; issues=[]; department_reports=[]
    matcher=None; department_error=''; department_engine=None
    progress.put((0,0,'압축 해제 및 문서 읽기 · 오류 파일은 기록 후 건너뜁니다.'))
    with tempfile.TemporaryDirectory(prefix='law_upload_') as tmp:
        try:
            groups,ignored=prepare(files,Path(tmp),cfg,issues)
        except Exception as error:
            groups=[]; ignored=[]
            issues.append({'file':'입력 묶음','error':str(error) if isinstance(error,ValueError) else '문서 읽기 실패: '+type(error).__name__})
        if not groups and not issues:
            issues.append({'file':'입력 묶음','error':'요약할 법안이 없습니다. 빈 양식만 있거나 지원하지 않는 형식인지 확인하세요.'})
        if groups and law_oc is not None:
            progress.put((0,len(groups),f'현행 직제 시행규칙 조회 중 · {connection.department_model}로 전체 부서 업무분장 검토'))
            try:
                department_engine=ApiSummarizer(connection.base_url,key,connection.department_model,CONTEXT,OUTPUT,connection.token_field)
                matcher=DepartmentMatcher(law_oc,department_engine,notify=lambda message: progress.put((0,len(groups),message)),hf_token=hf_token)
            except Exception as error:
                department_error=str(error) if isinstance(error,ValueError) else '부서 추천 초기화 실패'
                issues.append({'file':'소관부서 추천','error':department_error})
        for index,group in enumerate(groups):
            name=group['name']; letter=group['letter']
            progress.put((index,len(groups),name))
            try:
                units,warnings=build_units(group)
                issues.extend(warnings)
                laws=[u['law'] for u in units]; before=len(engine.audit)
                agency=organization_label(letter['agency'],letter['department']) if letter else ''
                deadline=deadline_label(letter['deadline']) if letter else ''
                number=package_number(group)
                pending=[]
                for unit,display in zip(units,unit_labels(units,number)):
                    law=unit['law']; member=unit['representative']
                    main_content='\n'.join(dict.fromkeys(unit['sections']))
                    full_text='\n\n'.join('첨부문서: '+doc['name']+'\n'+'\n'.join(doc['lines']) for doc in unit['documents'])
                    changed=engine.summarize_document(full_text,law,main_content)
                    department=''
                    if matcher:
                        try:
                            department,matching=matcher.match(law,changed)
                            department_reports.append({'file':name,**matching})
                        except Exception as error:
                            department=''
                            message=str(error) if isinstance(error,ValueError) else '부서 추천 처리 실패'
                            issues.append({'file':display,'error':message})
                            department_reports.append({'file':name,'law':law,'status':'error','error':message})
                    elif department_error:
                        department_reports.append({'file':name,'law':law,'status':'error','error':department_error})
                    pending.append([display,'\n'.join('- '+x for x in changed),agency,deadline,department])
                rows.extend(pending)
                reports.append({'file':name,'source_scope':'main_content_with_full_document_support','laws':laws,'units':[{'law':u['law'],'bill_number':u['bill_number'],'representative':u['representative'],'attachments':[d['source'] for d in u['documents']]} for u in units],'letter_metadata':{k:letter[k] for k in ('source','agency','department','deadline','warnings')} if letter else None,'requests':engine.audit[before:]})
            except Exception as error:
                message=str(error) if isinstance(error,ValueError) else '문서 처리 실패: '+type(error).__name__
                issues.append({'file':name,'error':message})
            progress.put((index+1,len(groups),name))
    report={'provider':connection.provider,'model':connection.model,'ignored_templates':ignored,'context_limit':CONTEXT,'output_limit':OUTPUT,'token_estimate':'UTF-8 bytes, not exact model tokens','files':reports,'issues':issues,
            'department_matching':{'enabled':law_oc is not None,'model':connection.department_model,'mode':'gpt_only','embedding_used':False,'threshold':None,'source':matcher.source if matcher else None,'error':department_error,'results':department_reports,'requests':department_engine.audit if department_engine else []}}
    return save_result(rows,report,success=len(reports),total=len(groups),uploaded=len(files),ignored_count=len(ignored))


def save_result(rows,report,*,success,total,uploaded=0,ignored_count=0):
    """Write a new run; never overwrite the previous summary or audit."""
    destination=ROOT/'output'/('법령요약_'+datetime.now().strftime('%Y-%m-%d_%H시%M분%S초_%f'))
    destination.mkdir(parents=True)
    excel=destination/'법령_주요내용_요약.xlsx'
    if rows: write_excel(rows,excel,headers=['법령명','주요내용','소관기관','제출기한','비고(소관부서)'])
    counts={'success':success,'total':total,'uploaded':uploaded,'ignored_count':ignored_count}
    report['summary_counts']=counts
    raw=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    (destination/'처리기록.json').write_bytes(raw)
    return {'xlsx':excel.read_bytes() if rows else None,'report':raw,'rows':rows,'issues':report['issues'],**counts,'folder':str(destination)}
