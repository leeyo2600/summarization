"""Offline regression fixtures: law wording reproduced in minimal DRF XML.
No production credentials, network calls, or AI calls are used.
Run from law_summary: runtime\\python\\python.exe -S tests\\test_department_v3.py
"""
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE),str(BASE/'vendor'/'cp313')]
import unittest
from xml.etree.ElementTree import Element, SubElement
from webapp.departments import parse_duties
from webapp.gpt_departments import GptDepartmentMatcher


def article(root,branch,role,items=(),intro=None,number='⑥'):
    a=SubElement(root,'조문단위')
    for tag,text in [('조문번호','39'),('조문가지번호',str(branch)),('조문여부','조문'),('조문내용',f'제39조의{branch}(시험센터)')]:
        SubElement(a,tag).text=text
    p=SubElement(a,'항')
    SubElement(p,'항번호').text=number
    SubElement(p,'항내용').text=intro or f'{number} {role}은 다음 사항을 분장한다.'
    for n,text in items:
        item=SubElement(p,'호')
        SubElement(item,'호번호').text=str(n)+'.'
        SubElement(item,'호내용').text=f'{n}. {text}'
    return a


def fixture(ref='제39조의4제6항제1호부터 제6호까지에 규정된 사항'):
    root=Element('법령')
    article(root,4,'보안통신과장',[(n,f'보안 업무 {n}') for n in range(1,7)])
    article(root,5,'보안통신과장',intro=f'⑥ 보안통신과장은 {ref}을 분장한다.')
    return root


class Regression(unittest.TestCase):
    def test_numeric_roles(self):
        for role in ['정보시스템1과장','정보시스템2과장','정보시스템12과장','기획전략과장']:
            with self.subTest(role=role):
                root=Element('법령'); article(root,3,role,[(1,'전산 시스템 운영')])
                self.assertEqual(parse_duties(root)[0]['department_name'],role[:-1])

    def test_external_article_range(self):
        rows=[r for r in parse_duties(fixture()) if r['reference']=='제39조의5']
        self.assertEqual(len(rows),6)
        for i,r in enumerate(rows,1):
            self.assertIn(f'보안 업무 {i}',r['duty'])
            self.assertIn('제39조의4',r['duty'])

    def test_same_article(self):
        root=Element('법령'); a=article(root,4,'관리과장',[(1,'예산'),(2,'인사')],number='①')
        p=SubElement(a,'항'); SubElement(p,'항번호').text='②'
        SubElement(p,'항내용').text='② 운영과장은 제1항제1호부터 제2호까지에 규정된 사항을 분장한다.'
        self.assertEqual(len(parse_duties(root)),4)

    def test_disjoint_ranges(self):
        root=Element('법령')
        article(root,4,'관리과장',[(n,f'업무 {n}') for n in range(1,21)],number='③')
        article(root,5,'운영총괄과장',[(1,'제39조의4제3항제1호부터 제11호까지 및 제16호부터 제20호까지에 규정된 사항')])
        rows=[r for r in parse_duties(root) if r['reference']=='제39조의5']
        self.assertEqual(len(rows),16)
        self.assertFalse(any('] 12. 업무' in r['duty'] for r in rows))

    def test_recursive_reference(self):
        root=fixture()
        article(root,3,'정보시스템1과장',[(1,'제39조의5제6항제1호에 규정된 사항')])
        # Add an explicit item to the referenced paragraph, itself adopting duties.
        p=root.findall('조문단위')[1].find('항')
        item=SubElement(p,'호'); SubElement(item,'호번호').text='1.'
        SubElement(item,'호내용').text='1. 제39조의4제6항제2호에 규정된 사항'
        rows=parse_duties(root)
        row=next(r for r in rows if r['reference']=='제39조의3')
        self.assertIn('보안 업무 2',row['duty'])

    def test_missing_item_fails(self):
        with self.assertRaisesRegex(ValueError,'인용 호 없음'):
            parse_duties(fixture('제39조의4제6항제1호부터 제7호까지에 규정된 사항'))

    def test_missing_article_fails(self):
        with self.assertRaisesRegex(ValueError,'인용 조문 없음'):
            parse_duties(fixture('제38조제6항제1호에 규정된 사항'))

    def test_missing_paragraph_fails(self):
        with self.assertRaisesRegex(ValueError,'인용 항 없음'):
            parse_duties(fixture('제39조의4제9항제1호에 규정된 사항'))

    def test_reversed_range_fails(self):
        with self.assertRaisesRegex(ValueError,'범위 역전'):
            parse_duties(fixture('제39조의4제6항제6호부터 제1호까지에 규정된 사항'))

    def test_cycle_fails(self):
        root=Element('법령')
        article(root,4,'관리과장',[(1,'제39조의5제6항제1호에 규정된 사항')])
        article(root,5,'운영과장',[(1,'제39조의4제6항제1호에 규정된 사항')])
        with self.assertRaisesRegex(ValueError,'순환'): parse_duties(root)

    def test_deleted_item_omitted(self):
        root=fixture(); root.find('.//호/호내용').text='1. 삭제 <2026. 9. 29.>'
        rows=[r for r in parse_duties(root) if r['reference']=='제39조의5']
        self.assertEqual(len(rows),5)

    def test_exception_preserved(self):
        root=fixture('제39조의4제6항제1호에 규정된 사항(센터 소관 업무에 한정한다)')
        self.assertIn('센터 소관 업무에 한정한다',parse_duties(root)[-1]['duty'])

    def test_normal_legal_citation_not_expanded(self):
        root=Element('법령'); article(root,4,'관리과장',[(1,'제10조에 따른 전산 장비 관리')])
        self.assertEqual(parse_duties(root)[0]['duty'],'1. 제10조에 따른 전산 장비 관리')

    def test_bracket_paragraph(self):
        root=fixture(); root.find('.//항번호').text='<16>'
        root.findall('조문단위')[1].find('항/항내용').text='⑥ 보안통신과장은 제39조의4제16항제1호에 규정된 사항을 분장한다.'
        self.assertEqual(len(parse_duties(root)),7)

    def test_49_rows_reach_matching_with_fake_engine(self):
        class FakeEngine:
            model='offline-test'; context=1_050_000; output=8192
            calls=0
            def _request(self,*args,**kwargs):
                self.calls+=1
                return ['없음','없음','회귀검증용 응답']
        engine=FakeEngine()
        matcher=GptDepartmentMatcher('offline-test',engine,law_data=(parse_duties(fixture()),{'effective_date':'20261001'}))
        for _ in range(49): self.assertEqual(matcher.match('시험법',['시험 내용'])[0],'없음')
        self.assertEqual(engine.calls,49)

if __name__=='__main__': unittest.main(verbosity=2)
