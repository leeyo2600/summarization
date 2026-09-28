import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

import httpx
import numpy as np
from defusedxml import ElementTree as ET
from openpyxl import load_workbook
from lawtool import ROOT
from webapp.departments import DepartmentMatcher, parse_duties, request_xml, split_for_model, fetch_duties, paragraph_number
from webapp.display import package_number, law_label, deadline_label
from webapp.jobs import process


XML='''<법령><기본정보><법령명_한글>행정안전부와 그 소속기관 직제 시행규칙</법령명_한글><시행일자>20260101</시행일자></기본정보>
<조문><조문단위><조문여부>전문</조문여부><조문내용>제2장 행정안전부</조문내용></조문단위>
<조문단위><조문번호>5</조문번호><조문여부>조문</조문여부><조문내용>제5조(기획조정실)</조문내용>
<항><항번호>⑦</항번호><항내용>⑦ 법무담당관은 다음 사항을 분장한다.</항내용>
<호><호번호>1.</호번호><호내용>법령안 심사에 관한 사항</호내용></호>
<호><호번호>2.</호번호><호내용>삭제</호내용></호></항>
<항><항번호>⑧</항번호><항내용>⑧ 지원과장은 다음 사항을 분장한다.</항내용>
<호><호번호>1.</호번호><호내용>기관 지원에 관한 사항</호내용></호></항></조문단위></조문></법령>'''


class DepartmentTests(unittest.TestCase):
    def test_display_formats_and_nested_number(self):
        group={'letter':None,'documents':[{'scope':('0','260825-1 통합.zip','18. 국민연금법.zip','첨부.zip')}]}
        self.assertEqual(package_number(group),'18')
        self.assertEqual(law_label('국민연금법','박홍배','18'),'18. 국민연금법')
        self.assertEqual(law_label('국민연금법','박홍배',''),'국민연금법')
        self.assertEqual(law_label('국민연금법','','18'),'18. 국민연금법')
        self.assertEqual(deadline_label('2026-09-23'),'2026.9.23(수)')
        self.assertEqual(deadline_label('2026-09-23 18:00'),'2026.9.23(수)')
        self.assertEqual(deadline_label('2026-09-23T18:00:00+09:00'),'2026.9.23(수)')
        self.assertEqual(deadline_label(''),'')
        group['documents'][0]['scope']=('99','통합.zip','10-2. 의견조회.zip')
        self.assertEqual(package_number(group),'10-2')
        group['documents'][0]['scope']=('99','260825-1 통합.zip','첨부.zip')
        self.assertEqual(package_number(group),'')

    def test_parse_duties_and_deleted_item(self):
        records=parse_duties(ET.fromstring(XML))
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['department'],'행정안전부 법무담당관')
        self.assertEqual(records[1]['department'],'행정안전부 지원과')
        self.assertEqual(records[0]['reference'],'제5조')

    def test_separate_item_numbers_and_nested_subitems(self):
        xml=XML.replace('<호번호>1.</호번호><호내용>법령안 심사에 관한 사항</호내용>',
                        '<호번호>1.</호번호><호내용>1. 법령안 심사에 관한 사항</호내용><목><목내용>가. 자치법규 검토</목내용></목>')
        records=parse_duties(ET.fromstring(xml))
        self.assertEqual(len(records),2)
        self.assertTrue(records[0]['duty'].startswith('1. 법령안'))
        self.assertIn('자치법규 검토',records[0]['duty'])

    def test_unknown_structure_fails_not_empty_result(self):
        with self.assertRaises(ValueError):
            parse_duties(ET.fromstring(XML.replace('법무담당관은 다음','다른 조직에서 해당')))

    def test_drf_bracket_paragraph_numbers(self):
        # Actual DRF response switches from circled numbers to escaped <16>.
        for number in (16,17,20,21,24,50):
            with self.subTest(number=number):
                marker=f'&lt;{number}&gt;'
                root=ET.fromstring(XML.replace('⑦',marker))
                self.assertEqual(paragraph_number(root.find('.//항')),number)
                records=parse_duties(root)
                self.assertEqual(len(records),2)
                self.assertEqual(records[0]['department_name'],'법무담당관')
                self.assertEqual(records[0]['paragraph'],f'<{number}>')

    def test_reference_to_drf_bracket_number(self):
        xml=XML.replace('⑦','&lt;16&gt;').replace('⑧','&lt;17&gt;')
        xml=xml.replace('지원과장은 다음 사항을 분장한다.','지원과장은 제16항제1호의 사항을 분장한다.')
        xml=xml.replace('<호><호번호>1.</호번호><호내용>기관 지원에 관한 사항</호내용></호>','')
        records=parse_duties(ET.fromstring(xml))
        self.assertEqual(records[1]['department_name'],'지원과')
        self.assertIn('법령안 심사',records[1]['duty'])

    def test_centers_branches_and_office_heads(self):
        for role,name in [('중앙민방위경보통제센터장','중앙민방위경보통제센터'),
                          ('성남분원장','성남분원'),('춘천지소장','춘천지소'),
                          ('광주청사관리소장','광주청사관리소'),('정책기획관','정책기획관')]:
            with self.subTest(role=role):
                records=parse_duties(ET.fromstring(XML.replace('법무담당관',role)))
                self.assertEqual(records[0]['department_name'],name)

    def test_referenced_items_preserve_scope_and_validate_completeness(self):
        xml='''<법령><조문단위><조문번호>32</조문번호><조문내용>제32조(정부청사관리본부에 두는 과)</조문내용>
        <항><항번호>⑦</항번호><항내용>⑦ 시설총괄과장은 다음 사항을 분장한다.</항내용>
        <호><호내용>8. 시설물 및 설비 유지</호내용></호><호><호내용>9. 시설물 안전점검</호내용></호>
        <호><호내용>10. 정보통신설비 유지</호내용></호><호><호내용>11. 시설 분야 근로자 관리</호내용></호></항>
        <항><항번호>⑧</항번호><항내용>⑧ 시설관리과장은 제7항제8호부터 제11호까지의 사항을 분장한다. 이 경우 정부세종청사 1동부터 17동까지 및 주차 4동의 시설물로 한다.</항내용></항>
        </조문단위></법령>'''
        records=parse_duties(ET.fromstring(xml))
        referred=[r for r in records if r['department_name']=='시설관리과']
        self.assertEqual(len(referred),4)
        self.assertTrue(any('정보통신설비 유지' in r['duty'] for r in referred))
        self.assertTrue(all('주차 4동' in r['duty'] for r in referred))
        with self.assertRaisesRegex(ValueError,'미해석'):
            parse_duties(ET.fromstring(xml.replace('<호><호내용>9. 시설물 안전점검</호내용></호>','')))

    def test_plain_duty_and_branched_article(self):
        xml='''<법령><조문단위><조문번호>39</조문번호><조문가지번호>2</조문가지번호>
        <조문내용>제39조의2(인천청사관리소)</조문내용><항><항번호>②</항번호>
        <항내용>② 인천청사관리소장은 청사 시설의 유지 및 보수 업무를 분장한다.</항내용></항></조문단위></법령>'''
        records=parse_duties(ET.fromstring(xml))
        self.assertEqual(records[0]['department_name'],'인천청사관리소')
        self.assertEqual(records[0]['reference'],'제39조의2')

    def test_fetch_exact_current_law_and_audit_no_oc(self):
        listing=ET.fromstring('<LawSearch><law><법령명한글>행정안전부와 그 소속기관 직제 시행규칙</법령명한글><법령ID>012925</법령ID></law></LawSearch>')
        with patch('webapp.departments.request_xml',side_effect=[(listing,b''),(ET.fromstring(XML),XML.encode())]) as request:
            records,audit=fetch_duties('private-oc')
        self.assertEqual(request.call_args_list[0].kwargs['nw'],3)
        self.assertEqual(request.call_args_list[1].kwargs['ID'],'012925')
        self.assertNotIn('private-oc',json.dumps(audit))
        self.assertEqual(len(records),2)

    def test_http_error_does_not_expose_oc(self):
        with patch('webapp.departments.httpx.get',side_effect=httpx.ConnectError('OC=private-oc')):
            with self.assertRaises(ValueError) as caught:
                request_xml('lawSearch.do','private-oc')
        self.assertNotIn('private-oc',str(caught.exception))

    def test_future_law_and_ambiguous_search_are_rejected(self):
        entry='<law><법령명한글>행정안전부와 그 소속기관 직제 시행규칙</법령명한글><법령ID>012925</법령ID></law>'
        with patch('webapp.departments.request_xml',return_value=(ET.fromstring('<LawSearch>'+entry*2+'</LawSearch>'),b'')):
            with self.assertRaisesRegex(ValueError,'하나로'):
                fetch_duties('test')
        with patch('webapp.departments.request_xml',side_effect=[
                (ET.fromstring('<LawSearch>'+entry+'</LawSearch>'),b''),
                (ET.fromstring(XML.replace('20260101','20990101')),b'')]):
            with self.assertRaisesRegex(ValueError,'시행 예정'):
                fetch_duties('test')

    def matcher(self,score,response=('D0',)):
        matcher=DepartmentMatcher.__new__(DepartmentMatcher)
        matcher.engine=Mock(context=100000,output=8192)
        matcher.engine._request.return_value=list(response)
        matcher.model=Mock(max_seq_length=8192,prompts={'query':'query: '})
        matcher.model.tokenizer.encode.side_effect=lambda text,**kwargs:list(text)
        matcher.model.encode.return_value=np.array([[1.,0.]])
        matcher.vectors=np.array([[score,(1-score**2)**0.5]])
        matcher.chunks=[{'department':'행정안전부 지원과','reference':'제5조','duty':'기관 지원','paragraph':'⑧'}]
        return matcher

    def test_threshold_boundary_and_query_prompt(self):
        for score in (0.6999,0.7,0.8):
            matcher=self.matcher(score)
            selected,audit=matcher.match('지원법',['기관 지원 확대'])
            self.assertEqual(selected,'없음' if score<0.7 else '지원과')
            self.assertEqual(matcher.engine._request.call_count,0 if score<0.7 else 1)
            self.assertEqual(matcher.model.encode.call_args.kwargs['prompt_name'],'query')

    def test_same_department_name_in_different_offices_is_not_merged(self):
        matcher=self.matcher(0.8)
        matcher.chunks=[{'department':'정부청사관리본부 관리과','department_name':'관리과',
            'article_title':title,'reference':ref,'paragraph':'③','duty':duty}
            for title,ref,duty in [('서울청사관리소','제33조','서울청사 운영'),('과천청사관리소','제34조','과천청사 운영')]]
        matcher.vectors=np.array([[0.8,0.6],[0.9,(1-0.9**2)**0.5]])
        result,audit=matcher.match('청사법',['청사 운영 지원'])
        self.assertEqual(result,'관리과')
        self.assertEqual(len(audit['candidates']),2)
        source=json.loads(matcher.engine._request.call_args.args[0])
        self.assertEqual(source['summary'],['청사 운영 지원'])
        self.assertEqual({c['reference'] for c in source['candidates']},{'제33조','제34조'})
        self.assertTrue(all(len(c['duties'])==1 for c in source['candidates']))

    def test_gpt_receives_all_duties_for_a_qualified_department(self):
        matcher=self.matcher(0.8)
        matcher.records=[*matcher.chunks,{**matcher.chunks[0],'duty':'기관 인력 관리'}]
        result,audit=matcher.match('지원법',['기관 지원 확대'])
        self.assertEqual(result,'지원과')
        payload=json.loads(matcher.engine._request.call_args.args[0])
        self.assertEqual(len(payload['candidates'][0]['duties']),2)

    def test_llm_rejection_and_invalid_candidate(self):
        selected,_=self.matcher(0.9,('없음',)).match('지원법',['기관 지원'])
        self.assertEqual(selected,'없음')
        for response in (('없는부서',),('D1',),('D0','D1')):
            with self.assertRaises(ValueError):
                self.matcher(0.9,response).match('지원법',['기관 지원'])

    def test_long_text_not_truncated(self):
        model=self.matcher(0.8).model
        text='기관 지원 업무 '*200
        chunks=split_for_model(model,text,True)
        self.assertEqual(''.join(chunks),text)
        self.assertGreater(len(chunks),1)
        self.assertTrue(all(len('query: '+chunk)<=512 for chunk in chunks))

    def test_job_formats_and_matching_failure_preserves_summary(self):
        document={'name':'법안.hwpx','scope':('0','1. 의견조회.zip'),'source':'1. 의견조회.zip / 법안.hwpx',
                  'lines':['지원법 일부개정법률안','홍길동 의원 대표발의','주요내용','기관 지원 확대']}
        letter={'source':'공문.pdf','agency':'행정안전부','department':'법무담당관','deadline':'2026-09-23 18:00','warnings':[],
                'scope':('0','1. 의견조회.zip')}
        group={'name':'공문.pdf','letter':letter,'documents':[document]}
        for failure in (None,'init','match'):
            with tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp); shutil.copy2(ROOT/'config.json',directory/'config.json')
                engine=Mock(audit=[]); engine.summarize_document.return_value=['기관 지원 확대']
                matcher=Mock(source={'law_id':'012925'})
                matcher.match.return_value=('지원과',{'selected':'지원과'})
                if failure=='match': matcher.match.side_effect=ValueError('부서 추천 응답 오류')
                with patch('webapp.jobs.ROOT',directory),patch('webapp.jobs.prepare',return_value=([group],[])),\
                     patch('webapp.jobs.ApiSummarizer',return_value=engine),\
                     patch('webapp.jobs.DepartmentMatcher',return_value=matcher,side_effect=ValueError('조회 실패') if failure=='init' else None):
                    result=process([],'test-key',Queue(),law_oc='private-oc')
                row=result['rows'][0]
                self.assertEqual(row[0],'1. 지원법')
                self.assertEqual(row[2:4],['행정안전부\n법무담당관','2026.9.23(수)'])
                self.assertEqual(row[4],'' if failure else '지원과')
                if failure:
                    self.assertTrue(result['issues'])
                    self.assertEqual(json.loads(result['report'])['department_matching']['results'][0]['status'],'error')
                self.assertNotIn('private-oc',result['report'].decode())
                self.assertEqual(json.loads(result['report'])['files'][0]['letter_metadata']['deadline'],'2026-09-23 18:00')
                book=load_workbook(io.BytesIO(result['xlsx']))
                self.assertEqual(book.active.cell(2,1).value,'1. 지원법')
                self.assertEqual(book.active.cell(2,3).value,'행정안전부\n법무담당관')
                self.assertTrue(book.active.cell(2,3).alignment.wrap_text)
                self.assertEqual(book.active.cell(2,4).value,'2026.9.23(수)')
                self.assertEqual(book.active.cell(2,5).value or '',row[4]); book.close()
