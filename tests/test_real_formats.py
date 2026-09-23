import unittest
import lawtool as l

class RealFormats(unittest.TestCase):
    def test_combined_heading(self):
        result=l.find_sections(['특별법 일부개정법률안','제안이유 및 주요내용','지원 대상을 확대하려는 것임(안 제2조).','참고사항','제외'])
        self.assertEqual(result[0]['law'],'특별법')
        self.assertNotIn('제외',result[0]['text'])

    def test_title_after_main_contents(self):
        result=l.find_sections(['1. 제정이유','* 관련근거 : 「다른법」','2. 주요내용','가. 구성과 기능을 정함','- 기관별 역할을 규정','나. 적용 범위를 정함','3. 참고사항','「사업 운영규정」 제정안'])
        self.assertEqual(result[0]['law'],'사업 운영규정')
        self.assertIn('나. 적용',result[0]['text'])

    def test_nested_numbered_content(self):
        result=l.find_sections(['운영지침 일부개정안','2. 주요내용','Ⅱ. 학사운영','4. 수업기간','학습기간을 1주 이상으로 함','3. 의견제출'])
        self.assertIn('1주',result[0]['text'])

    def test_new_bill(self):
        result=l.find_sections(['불평등 대응 특별법안','주요내용','위원회 및 시행계획의 수립을 규정함','불평등 대응 특별법안','제1장 총칙'])
        self.assertEqual(result[0]['law'],'불평등 대응 특별법')
        self.assertNotIn('총칙',result[0]['text'])
