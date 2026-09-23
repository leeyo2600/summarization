import unittest
from concurrent.futures import Future
from queue import Queue
from streamlit.testing.v1 import AppTest
from lawtool import ROOT
from webapp.api import MODEL


class UiTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT/'app.py')).run()

    def test_input(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertTrue(app.button[0].disabled)
        self.assertTrue(any(MODEL in caption.value for caption in app.caption))
        self.assertFalse(any('A/B' in x.label for x in app.checkbox))

    def test_processing_partial_result_and_reset(self):
        app=self.app(); future=Future()
        app.session_state.page='processing'
        app.session_state.job=future
        app.session_state.progress=Queue()
        app.session_state.progress.put((0,0,'자료 준비 중'))
        app.run(); self.assertFalse(app.exception)
        future.set_result({'total':1,'success':1,'rows':[['지원법','- 지원 확대','','','']],
                           'issues':[{'file':'bad.pdf','error':'PdfStreamError'}],
                           'xlsx':b'test','report':b'{}','folder':'output/test'})
        app.run(); self.assertFalse(app.exception)
        self.assertEqual(app.session_state.page,'complete')
        self.assertTrue(app.warning)
        app.button[0].click().run()
        self.assertEqual(app.session_state.page,'input')

    def test_all_failed(self):
        app=self.app()
        app.session_state.page='complete'
        app.session_state.result={'total':0,'success':0,'issues':[{'file':'bad.pdf','error':'error'}],
                                  'rows':[],'xlsx':None,'report':b'{}','folder':'output/test'}
        app.run(); self.assertFalse(app.exception)
        self.assertTrue(app.error)
