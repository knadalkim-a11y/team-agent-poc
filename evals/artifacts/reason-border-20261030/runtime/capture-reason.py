"""Actual Native reason focus/selection verification; no product DOM replacement."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[4]
SOURCE_RUNNER = ROOT / 'evals/artifacts/operations31-authoring12-parity-20261030/runtime/capture-parity.py'
spec = importlib.util.spec_from_file_location('prior_parity_capture', SOURCE_RUNNER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
OUT = Path(os.environ['EES_TEST_SCREENSHOT_DIR'])
OBSERVATIONS = []


class ReasonBorder(prior.Parity):
    def reason_observation(self, selector, label, state):
        value = self.browser.evaluate("""(() => {
          const e=document.querySelector(SELECTOR),s=getComputedStyle(e),r=e.getBoundingClientRect();
          return {active:document.activeElement===e,focusVisible:e.matches(':focus-visible'),readOnly:e.readOnly,
            value:e.value,selectionStart:e.selectionStart,selectionEnd:e.selectionEnd,
            outlineStyle:s.outlineStyle,outlineWidth:s.outlineWidth,outlineColor:s.outlineColor,outlineOffset:s.outlineOffset,
            boxShadow:s.boxShadow,borderWidth:s.borderWidth,borderColor:s.borderColor,borderRadius:s.borderRadius,
            rect:{x:r.x,y:r.y,width:r.width,height:r.height},viewport:{width:innerWidth,height:innerHeight}};
        })()""".replace('SELECTOR', json.dumps(selector)))
        value.update(label=label, state=state)
        OBSERVATIONS.append(value)
        (OUT / 'focus-observations.json').write_text(json.dumps(OBSERVATIONS, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        self.assertEqual(value['borderWidth'], '1px')
        self.assertEqual(value['borderColor'], 'rgb(213, 214, 218)')
        self.assertEqual(value['borderRadius'], '6px')
        self.assertEqual(value['boxShadow'], 'none')
        self.assertEqual(value['rect']['height'], 66)
        if state == 'idle':
            self.assertFalse(value['active'])
            self.assertEqual(value['outlineStyle'], 'none')
        else:
            self.assertTrue(value['active'])
            if state == 'keyboard':
                self.assertTrue(value['focusVisible'])
            if value['focusVisible']:
                self.assertEqual(value['outlineWidth'], '2px')
                self.assertEqual(value['outlineColor'], 'rgb(92, 94, 101)')
                self.assertEqual(value['outlineOffset'], '-2px')
        super().stage_capture(label+'-'+state)
        png=self.browser.call('Page.captureScreenshot', {'format':'png','clip':{**value['rect'],'scale':1},'captureBeyondViewport':True})['data']
        (OUT/(label+'-'+state+'-textarea.png')).write_bytes(base64.b64decode(png))
        return value

    def reason_focus_states(self, selector, label):
        expected=self.read(selector, 'value')
        readonly=self.read(selector, 'readOnly')
        self.click(selector.rsplit(' ',1)[0]+' .ew-vd-selection-record')
        idle=self.reason_observation(selector,label,'idle')
        self.click(selector)
        pointer=self.reason_observation(selector,label,'pointer')
        self.key('Tab',9)
        self.key('Tab',9,8)
        self.wait('document.activeElement===document.querySelector('+json.dumps(selector)+')')
        keyboard=self.reason_observation(selector,label,'keyboard')
        # The existing 56px Native rail leaves a 424px panel at viewport480;
        # source5 measured the same 357px note field in this responsive state.
        expected_width=413 if idle['viewport']['width']==1920 else 357
        self.assertEqual([idle['rect']['width'],pointer['rect']['width'],keyboard['rect']['width']],[expected_width]*3)
        self.browser.call('Browser.grantPermissions', {'origin':self.server.url,'permissions':['clipboardReadWrite','clipboardSanitizedWrite']})
        self.key('a',65,2)
        self.key('c',67,2)
        copied=self.browser.evaluate('navigator.clipboard.readText()')
        self.assertEqual(copied,expected)
        if readonly:
            self.browser.call('Input.insertText', {'text':'읽기 전용에 저장되면 안 되는 입력'})
            self.assertEqual(self.read(selector,'value'),expected)
        OBSERVATIONS[-1].update(copy_verified=True,readonly_input_blocked=bool(readonly))
        (OUT/'focus-observations.json').write_text(json.dumps(OBSERVATIONS,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def stage_capture(self, label):
        super().stage_capture(label)
        cases={
          'operations31-reason-reference-1920':('#stage-evidence-job-6 [data-stage-note]','reason-reference-readonly-1920'),
          'operations31-reason-draft-1920':('#stage-evidence-job-2 [data-stage-note]','reason-draft-editable-1920'),
          'operations31-reason-saved-480':('#stage-evidence-job-2 [data-stage-note]','reason-saved-readonly-480'),
        }
        if label in cases:
            self.reason_focus_states(*cases[label])
        if label=='operations31-reason-draft-1920':
            self.browser.call('Emulation.setDeviceMetricsOverride',{'width':480,'height':1080,'deviceScaleFactor':1,'mobile':False})
            self.wait('innerWidth===480')
            self.reason_focus_states('#stage-evidence-job-2 [data-stage-note]','reason-draft-editable-480')
            self.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
            self.wait('innerWidth===1920')
        if label=='operations31-reason-reference-1920':
            self.click('[data-action=stage_evidence][data-job-id=job-3]')
            self.wait("document.querySelector('#stage-evidence-job-3 .ew-vd-tool-toggle')")
            toggle='#stage-evidence-job-3 .ew-vd-tool-toggle'
            self.click(toggle)
            self.key('Tab',9);self.key('Tab',9,8)
            self.wait('document.activeElement===document.querySelector('+json.dumps(toggle)+')')
            style=self.browser.evaluate('(()=>{const e=document.querySelector('+json.dumps(toggle)+'),s=getComputedStyle(e);return {focusVisible:e.matches(":focus-visible"),width:s.outlineWidth,color:s.outlineColor,offset:s.outlineOffset,boxShadow:s.boxShadow};})()')
            self.assertTrue(style['focusVisible']);self.assertEqual(style['width'],'2px');self.assertEqual(style['offset'],'2px')
            self.assertNotEqual(style['color'],'rgb(92, 94, 101)')
            (OUT/'tool-toggle-focus.json').write_text(json.dumps(style,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    names=['test_operations31_saved_reason_reference_state','test_operations31_reason_draft_is_private_and_saved_with_explicit_verdict']
    files=['branding/ees/ui/ees-work-launcher.js','branding/ees/ui/ees-work-view.js','branding/ees/ui/ees-work-designer.js','branding/ees/ui/ees-work-launcher.css','tests/test_ees_work_figma_runtime_native.py','tests/ees_work_integrated_fixture.py',str(SOURCE_RUNNER.relative_to(ROOT)),str(Path(__file__).relative_to(ROOT))]
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    manifest_path=Path(os.environ['EES_TEST_BRANDING_DIR'])/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    built={name:manifest['source_frontend']['source_inputs'][name] for name in files[:4]}
    assert all(hashes[name]==value for name,value in built.items()),'Source and wheel differ'
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ReasonBorder(name) for name in names))
    unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in hashes.items())
    report={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,encoding='utf-8').strip(),'working_tree_modified':True,'source_hashes':hashes,'built_ui_hashes':built,'source_unchanged_during_run':unchanged,'wheel':manifest['wheel'],'branding_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'tests':names,'testsRun':result.testsRun,'success':result.wasSuccessful() and unchanged,'failures':[(str(t),e) for t,e in result.failures],'errors':[(str(t),e) for t,e in result.errors],'scope':'Actual Native production UI and SQLite; physical pointer/Tab/clipboard input, real draft and explicit verdict contract. No product DOM substitution. Prior source5 evidence remains untouched.'}
    (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not report['success'])
