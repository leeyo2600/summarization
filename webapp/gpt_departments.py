"""Production department matching with GPT only; no embedding initialization."""
import json
from webapp.departments import fetch_duties, LAW_NAME
from webapp.gpt_department_experiment import PROMPT, catalog
from webapp.display import department_label


class GptDepartmentMatcher:
    def __init__(self,oc,engine,notify=lambda message:None,hf_token=None,*,law_data=None):
        if not oc.strip(): raise ValueError('국가법령정보 API 키를 입력하세요.')
        notify(f'현행 직제 시행규칙 조회 중 · {engine.model} 전체 업무분장 검토')
        records,self.source=fetch_duties(oc.strip()) if law_data is None else law_data
        self.engine=engine
        self.departments=catalog(records)
        self.allowed={d['id']:d for d in self.departments}
        self.source={**self.source,'matching_mode':'gpt_only','model':engine.model,
                     'embedding_used':False,'department_count':len(self.departments)}

    def match(self,law,items):
        if not items: raise ValueError('부서 추천에 사용할 주요내용이 없습니다.')
        # Stable catalog first permits reuse of a common input prefix across rows.
        payload=json.dumps({'department_law':LAW_NAME,'effective_date':self.source['effective_date'],
            'departments':self.departments,'law':law,'summary':items},ensure_ascii=False)
        if len((payload+PROMPT).encode('utf-8'))>self.engine.context-self.engine.output-512:
            raise ValueError('전체 업무분장이 입력 한도를 초과했습니다. 임의로 자르지 않았습니다.')
        answer=self.engine._request(payload,0,whole_document=True,prompt=PROMPT)
        if len(answer)!=3: raise ValueError('부서·근거·이유 응답 형식 오류')
        selected,evidence_id,reason=answer
        audit={'law':law,'status':'ok','mode':'gpt_only','model':self.engine.model,
               'embedding_used':False,'threshold':None,'reason':reason}
        if selected=='없음':
            if evidence_id!='없음': raise ValueError('없음 응답의 근거 형식 오류')
            return '없음',{**audit,'selected':'없음','evidence':None}
        department=self.allowed.get(selected)
        evidence=next((d for d in department['duties'] if d['id']==evidence_id),None) if department else None
        if evidence is None: raise ValueError('부서 또는 해당 부서의 근거 업무 ID가 유효하지 않습니다.')
        name=department_label(department)
        return name,{**audit,'selected':name,'selected_department':department['department'],
                     'reference':department['reference'],'evidence':evidence}
