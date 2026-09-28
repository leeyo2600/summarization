"""Compare exactly four requested laws, without modifying saved summaries."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from lawtool import ROOT
from webapp.api import ApiSummarizer, BASE_URL, CONTEXT, OUTPUT
from webapp.departments import fetch_duties
from webapp.gpt_departments import GptDepartmentMatcher
from webapp.gpt_department_experiment import PROMPT

TARGETS={1:'공무원 임용규칙',5:'지방교부세법',
    13:'우주항공청 소관 연구개발사업 수행기관 등의 연구윤리 확보를 위한 지침',
    25:'특정 금융거래정보의 보고 및 이용 등에 관한 법률'}
MODELS=('gpt-6-sol','gpt-6-astra')


def select_rows(rows):
    selected=[]
    for number,title in TARGETS.items():
        matches=[]
        for index,row in enumerate(rows):
            label=re.sub(r'\([^()]*의원\)$','',row[0]).strip()
            match=re.match(r'^(\d+)\.\s*(.*)$',label)
            if match and int(match[1])==number and re.sub(r'\s+','',match[2])==re.sub(r'\s+','',title):
                matches.append((index+2,row))
        if len(matches)!=1: raise ValueError(f'{number}. {title}: 대상 행을 하나로 확정할 수 없습니다.')
        selected.append(matches[0])
    return selected


def compare(previous,key,oc,progress):
    rows=select_rows(previous['rows'])
    progress.put('현행 업무분장 조회 중 · 두 모델에 동일한 자료를 사용합니다.')
    law_data=fetch_duties(oc)
    report={'mode':'sol_astra_comparison','source_run':Path(previous['folder']).name,
        'source':law_data[1],'models':MODELS,'reasoning_effort':'medium',
        'prompt':PROMPT,'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
        'embedding_used':False,'threshold':None,'results':[],'requests':{}}
    for model in MODELS:
        engine=ApiSummarizer(BASE_URL,key,model,CONTEXT,OUTPUT,'max_completion_tokens')
        matcher=GptDepartmentMatcher(oc,engine,law_data=law_data)
        for excel_row,row in rows:
            progress.put(f'{len(report["results"])+1} / 8 · {model} · {row[0]}')
            entry={'excel_row':excel_row,'law':row[0],'model':model,'previous_department':row[4],
                   'summary':row[1]}
            try:
                items=[re.sub(r'^\s*-\s*','',s).strip() for s in row[1].splitlines() if s.strip()]
                _,audit=matcher.match(row[0],items)
                entry.update(audit)
            except Exception as error:
                entry.update(status='error',selected='',error=str(error) if isinstance(error,ValueError) else '모델 비교 처리 실패')
            report['results'].append(entry)
        report['requests'][model]=engine.audit
    destination=ROOT/'output'/('model_comparison_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    destination.mkdir(parents=True)
    raw=json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    (destination/'comparison.json').write_bytes(raw)
    return {'results':report['results'],'report':raw,'folder':str(destination)}
