import json
import time
import unittest
from pathlib import Path
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests

class SaveUIObservation(FigmaAuthoringNativeTests):
    def screenshot(self, label, *, wait_for_fonts=True):
        directory=super().screenshot(label, wait_for_fonts=wait_for_fonts)
        if label == 'easy-tools-empty-starter':
            # Observe normal 400ms UI selection persistence before continuing;
            # no injected commands, product mutation or increased test timeout.
            deadline=time.monotonic()+9
            while not any(b['action']=='save_ui' for b in self.server.workspace_commands):
                self.browser.evaluate('document.readyState')
                if time.monotonic()>=deadline:
                    self.fail('Normal save_ui not observed')
                time.sleep(.025)
        return directory
    def tearDown(self):
        Path('/workspace/scratch/f5cd50d81fb4/c18-q5-ci-observation-20261012/probe-commands.json').write_text(json.dumps({'scope':'actual browser; real workflow commands on temporary SQLite, synthetic Native session; existing save_ui observed before first tool save','commands':self.server.workspace_commands,'tools':self.operations()['tools'],'external_calls':self.bridge.calls,'completions':self.server.completions},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        super().tearDown()

if __name__=='__main__':
    suite=unittest.TestSuite([SaveUIObservation('test_easy_tools_unconnected_example_and_live_read_confirmation_roundtrip')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
