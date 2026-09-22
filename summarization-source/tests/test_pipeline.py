import unittest, tempfile, zipfile
from pathlib import Path
from unittest.mock import patch
import lawtool as l
from openpyxl import load_workbook

class PipelineTests(unittest.TestCase):
    def test_numbered_boundary(self):
        s=l.find_sections(['영유아특별회계법 일부개정법률안','1. 개정이유','필요함','2. 주요내용',
            '가. 전입금 규정 정비(안 제5조)','나. 보고 절차 신설(안 제9조)','3. 참고사항','예산 관련 내용'])
        self.assertEqual(s[0]['law'],'영유아특별회계법')
        self.assertNotIn('예산',s[0]['text']); self.assertIn('나.',s[0]['text'])
    def test_no_fallback(self):
        with self.assertRaises(l.ReviewRequired): l.find_sections(['영유아특별회계법','개정이유','배경만 있습니다.'])
    def test_toc_skipped(self):
        s=l.find_sections(['영유아특별회계법','2. 주요내용 .... 3','3. 참고사항 .... 4',
            '2. 주요내용','가. 전입금의 규정 정비(안 제5조)','3. 참고사항'])
        self.assertEqual(len(s),1); self.assertEqual(s[0]['heading_line'],4)
    def test_roman_symbol_korean_boundaries(self):
        for h,n in [('Ⅱ. 주요내용','Ⅲ. 기타 사항'),('□ 주요내용','□ 기타 사항'),('나. 주요내용','다. 기타 사항')]:
            s=l.find_sections(['영유아특별회계법',h,'지원 대상 기관의 범위를 확대함',n,'제외해야 할 문장'])
            self.assertNotIn('제외',s[0]['text'])
    def test_multiple_laws(self):
        s=l.find_sections(['첫째법','2. 주요내용','지원 대상 기관의 범위를 확대함','3. 참고사항',
          '둘째법 시행령','주요내용','제출 절차를 정비하도록 규정함','참고사항'])
        self.assertEqual([x['law'] for x in s],['첫째법','둘째법 시행령'])
    def test_nested_table_no_duplication_and_section_order(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.hwpx'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('Contents/section10.xml','<sec><p><t>끝</t></p></sec>')
                z.writestr('Contents/section2.xml','<sec><p><run><t>앞</t><tbl><tr><tc><p><run><t>셀</t></run></p></tc></tr></tbl><t>뒤</t></run></p></sec>')
            self.assertEqual(l.read_hwpx(p),['앞','셀','뒤','끝'])
    def test_excel(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a.xlsx'; l.write_excel([['=법령','- 내용1\n- 내용2','','','']],p)
            w=load_workbook(p); s=w.active
            self.assertEqual(s.max_column,5); self.assertEqual(s['A2'].data_type,'s')
            self.assertEqual(s['B2'].value,'- 내용1\n- 내용2'); self.assertIsNone(s['E2'].value)
    def test_pipeline_only_selected_text_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); inp=root/'input'; inp.mkdir()
            (root/'config.json').write_text('{}')
            xml='<sec>'+''.join('<p><t>'+x+'</t></p>' for x in [
                '영유아특별회계법','1. 개정이유','요약하지 않을 배경',
                '2. 주요내용','전입금 규정 정비(안 제5조)','3. 참고사항','요약하지 않을 예산'])+'</sec>'
            with zipfile.ZipFile(inp/'ok.hwpx','w') as z: z.writestr('Contents/section0.xml',xml)
            (inp/'broken.hwpx').write_text('invalid')
            seen=[]
            class FakeEngine:
                def __init__(self,cfg): pass
                def summarize(self,text): seen.append(text); return ['전입금 규정 정비(안 제5조)']
            with patch.object(l,'ROOT',root), patch.object(l,'Summarizer',FakeEngine):
                self.assertEqual(l.run(inp),2)
            self.assertEqual(seen,['전입금 규정 정비(안 제5조)'])
            book=load_workbook(next((root/'output').rglob('summary.xlsx')))
            self.assertEqual(book.active.max_row,2)
            self.assertEqual(book.active['B2'].value,'- 전입금 규정 정비(안 제5조)')

    def test_missing_title(self):
        with self.assertRaises(l.ReviewRequired): l.find_sections(['제목 없음','주요내용','지원 대상 기관의 범위를 확대함'])
    def test_fake_model_validation(self):
        engine=l.Summarizer.__new__(l.Summarizer)
        engine.cfg={'max_tokens':700,'temperature':0}
        engine.chunks=lambda s:[s]
        class Fake:
            def create_chat_completion(self,**kwargs):
                return {'choices':[{'finish_reason':'stop','message':{'content':'{"items":["절차 정비(안 제99조)"]}'}}]}
        engine.llm=Fake()
        with self.assertRaises(l.ReviewRequired): engine.summarize('절차를 정비함(안 제5조)')

if __name__=='__main__': unittest.main()
