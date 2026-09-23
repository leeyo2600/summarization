import unittest
from webapp.packages import metadata, representative
from webapp.jobs import document_targets, build_units


class RealPackageFixTests(unittest.TestCase):
    def test_split_bill_title(self):
        lines=['자율주행자동차 상용화 촉진 및 지원에 관한 법률','일부개정법률안','제안이유 및 주요내용','신규 서비스 지원 범위를 확대하려는 것임']
        self.assertEqual(document_targets(lines),['자율주행자동차 상용화 촉진 및 지원에 관한 법률'])

    def test_metadata_time_and_agency_suffix(self):
        a=metadata('인 사 혁 신 처\n수신 관계기관\n제목 「지원법」 의견조회\n1. 26.9.14.(월) 18:00까지 제출\n시행 정책과-1 (2026.8.25.)')
        self.assertEqual(a['agency'],'인사혁신처')
        self.assertEqual(a['deadline'],'2026-09-14 18:00')
        b=metadata('금융정보분석원\n수신 기관\n제목 「지원법」 의견조회\n1. 9월 4일(금)까지 제출\n시행 기획행정실-1 (2026.8.25.)')
        self.assertEqual(b['agency'],'금융정보분석원')
        self.assertEqual(b['deadline'],'2026-09-04')
        self.assertTrue(b['warnings'])

    def test_hanja_representative_preserved(self):
        self.assertEqual(representative(['(朴芝源의원 대표발의)']),'朴芝源')

    def test_distinct_bills_stay_separate(self):
        docs=[]
        for number in ('20238','20327','20347'):
            docs.append({'name':number+'.hwpx','source':number,'lines':['전자정부법 일부개정법률안','(김영진의원 대표발의)','의 안','번 호',number,'주요내용','해당 의안의 제도를 개선하고 지원 범위를 확대함']})
        units,warnings=build_units({'documents':docs})
        self.assertEqual(len(units),3)
        self.assertEqual({u['bill_number'] for u in units},{'20238','20327','20347'})
        self.assertTrue(all(len(u['documents'])==1 for u in units))

    def test_two_laws_in_one_document(self):
        d={'name':'두법.hwpx','source':'test','lines':['첫째법','주요내용','첫째 지원 범위를 확대하도록 함','3. 참고사항','둘째법','주요내용','둘째 지원 제도를 폐지하도록 함']}
        units,_=build_units({'documents':[d]})
        self.assertEqual({u['law'] for u in units},{'첫째법','둘째법'})

    def test_annex_bullet_is_not_law(self):
        d={'name':'법안.hwpx','source':'bill','lines':['지원법','주요내용','지원 범위와 신청 절차를 정비함']}
        annex={'name':'별표.hwpx','source':'annex','lines':['◦ 공항분야 지침·기준·규정']}
        units,_=build_units({'documents':[d,annex]})
        self.assertEqual(len(units),1)
        self.assertEqual(len(units[0]['documents']),2)
