import unittest
from webapp.display import department_label, organization_label


class OrganizationLabelTests(unittest.TestCase):
    def test_parent_units(self):
        for title,name,expected in [
            ('기획조정실장','법무담당관','기획조정실\n법무담당관'),
            ('자치혁신실','지방인사제도과','자치혁신실\n지방인사제도과'),
            ('재난복구지원국','복구지원과','재난복구지원국\n복구지원과'),
            ('서울청사관리소','관리과','서울청사관리소\n관리과'),
            ('운영지원과','운영지원과','행정안전부\n운영지원과'),
            ('센터','운영과','행정안전부\n운영과')]:
            with self.subTest(title=title):
                self.assertEqual(department_label({'article_title':title,'department_name':name,
                    'organization':'행정안전부'}),expected)

    def test_unknown_parent_not_invented(self):
        self.assertEqual(department_label({'department_name':'지원과'}),'지원과')

    def test_agency_newline_and_missing_parts(self):
        self.assertEqual(organization_label('행정안전부','법무담당관'),'행정안전부\n법무담당관')
        self.assertEqual(organization_label('행정안전부',''),'행정안전부')
        self.assertEqual(organization_label('','법무담당관'),'법무담당관')
