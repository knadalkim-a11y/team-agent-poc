import json
import unittest
from test_ees_work_figma_runtime_native import FigmaRuntimeNativeTests
original = FigmaRuntimeNativeTests.stage_capture

def stable_capture(self, label):
    self.browser.evaluate("Promise.all(document.querySelector('#ees-work-panel').getAnimations({subtree:true}).filter(a=>a.playState==='running' && a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>null))).then(()=>true)")
    original(self, label)
    observation = self.browser.evaluate("""(() => {const selectors=['.ew-run-nav','.ew-vd-head','.ew-stage-heading','.ew-tabs','.ew-vd-label','.ew-vd-item','.ew-vd-name','.ew-vd-run','.ew-vd-pick','.ew-vd-menu','.ew-vd-option'];return selectors.map(selector=>{const e=document.querySelector('#ees-work-panel '+selector);if(!e)return {selector,missing:true};const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {selector,width:r.width,height:r.height,fontSize:s.fontSize,lineHeight:s.lineHeight,fontWeight:s.fontWeight,padding:s.padding,background:s.backgroundColor,opacity:s.opacity,outline:s.outline,boxShadow:s.boxShadow};});})()""")
    directory = self.screenshot(label)
    (directory / (label + '-computed.json')).write_text(json.dumps(observation, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

FigmaRuntimeNativeTests.stage_capture = stable_capture
suite = unittest.TestSuite(FigmaRuntimeNativeTests(name) for name in ['test_operations_stage_actual_jobs_header_and_judgment_menu_at_two_widths','test_operations_stage_actual_tool_evidence_retry_and_scope_execution'])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
