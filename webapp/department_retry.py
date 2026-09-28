"""Fill missing recommendations without resummarizing or overwriting old runs."""
import json
import re
from copy import deepcopy
from pathlib import Path

from openpyxl import load_workbook
from lawtool import ROOT
from webapp.api import ApiSummarizer, BASE_URL, DEPARTMENT_MODEL as MODEL, CONTEXT, OUTPUT
from webapp.gpt_departments import GptDepartmentMatcher as DepartmentMatcher
from webapp.jobs import save_result


HEADERS=['법령명','주요내용','소관기관','제출기한','비고(소관부서)']


def saved_results():
    output=ROOT/'output'
    return sorted((p.name for p in output.glob('법령요약_*')
                   if p.is_dir() and not p.is_symlink()
                   and (p/'법령_주요내용_요약.xlsx').is_file()
                   and (p/'처리기록.json').is_file()),reverse=True)


def load_saved_result(name):
    output=(ROOT/'output').resolve()
    folder=(output/name).resolve()
    if folder.parent!=output or name not in saved_results():
        raise ValueError('이 앱에서 저장한 요약 결과만 불러올 수 있습니다.')
    excel=folder/'법령_주요내용_요약.xlsx'
    raw=(folder/'처리기록.json').read_bytes()
    report=json.loads(raw)
    book=load_workbook(excel,read_only=True,data_only=False)
    try:
        sheet=book.active
        if sheet.max_column!=5 or sheet.max_row>10000:
            raise ValueError('기존 결과의 열 또는 행 범위를 확인하세요.')
        values=list(sheet.iter_rows(values_only=True))
        if list(values[0])!=HEADERS:
            raise ValueError('비고(소관부서) 열이 있는 요약 결과만 지원합니다.')
        rows=[[value if value is not None else '' for value in row] for row in values[1:]]
        if not rows or any(not isinstance(value,str) for row in rows for value in row):
            raise ValueError('기존 결과의 텍스트 형식을 확인하세요.')
        if any(cell.data_type=='f' for row in sheet.iter_rows() for cell in row):
            raise ValueError('수식이 포함된 결과는 재처리하지 않습니다.')
    finally:
        book.close()
    success=len(report.get('files',[]))
    counts=report.get('summary_counts',{})
    return {'xlsx':excel.read_bytes(),'report':raw,'rows':rows,'issues':report.get('issues',[]),
            'success':counts.get('success',success),'total':counts.get('total',success),
            'uploaded':counts.get('uploaded',0),
            'ignored_count':counts.get('ignored_count',len(report.get('ignored_templates',[]))),
            'folder':str(folder)}


def retry_departments(previous,key,progress,law_oc,hf_token=None,retry_all=False):
    rows=deepcopy(previous['rows'])
    targets=[index for index,row in enumerate(rows) if retry_all or not row[4].strip()]
    if not targets: raise ValueError('재처리할 빈 비고가 없습니다.')
    report=json.loads(previous['report'])
    old=report.get('department_matching',{})
    old_results=old.get('results',[])
    engine=ApiSummarizer(BASE_URL,key,MODEL,CONTEXT,OUTPUT,'max_completion_tokens')
    progress.put((0,len(targets),f'비고 재처리 · 현행 업무분장 조회 및 {MODEL} 준비 중'))
    # Initialization failure propagates: the UI keeps the previous result.
    matcher=DepartmentMatcher(law_oc,engine,
        notify=lambda message: progress.put((0,len(targets),message)),hf_token=hf_token)
    old_errors={r.get('error') for r in old_results if r.get('status')=='error'}
    old_errors.add(old.get('error'))
    target_names={rows[index][0] for index in targets}
    issues=[i for i in report.get('issues',[]) if not (
        i.get('file')=='소관부서 추천' or
        (i.get('file') in target_names and i.get('error') in old_errors))]
    results=deepcopy(old_results) if len(old_results)==len(rows) else [
        {'law':row[0],'status':'preserved' if row[4].strip() else 'pending','selected':row[4]}
        for row in rows]
    for done,index in enumerate(targets,1):
        row=rows[index]
        progress.put((done-1,len(targets),'비고 재처리 · '+row[0]))
        law=results[index].get('law') or row[0]
        try:
            items=[re.sub(r'^\s*-\s*','',line).strip() for line in row[1].splitlines() if line.strip()]
            if not items: raise ValueError('부서 추천에 사용할 주요내용이 없습니다.')
            row[4],audit=matcher.match(law,items)
            results[index]={**audit,'row':index+2}
        except Exception as error:
            row[4]=''
            message=str(error) if isinstance(error,ValueError) else '부서 추천 처리 실패'
            issues.append({'file':row[0],'error':message})
            results[index]={'law':law,'row':index+2,'status':'error','error':message}
        progress.put((done,len(targets),row[0]))
    report['issues']=issues
    report['department_matching']={'enabled':True,'mode':'gpt_only','embedding_used':False,'threshold':None,'source':matcher.source,'error':'',
        'results':results,'retry_of':Path(previous['folder']).name,
        'previous_source':old.get('source'),
        'retried_rows':[index+2 for index in targets]}
    return save_result(rows,report,success=previous['success'],total=previous['total'],
        uploaded=previous.get('uploaded',0),ignored_count=previous.get('ignored_count',0))
