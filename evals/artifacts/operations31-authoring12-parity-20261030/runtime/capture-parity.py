"""Capture real Native tests without altering product DOM or compiled assets."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from ees_work_integrated_fixture import IntegratedNativeCase
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests
from test_ees_work_figma_runtime_native import FigmaRuntimeNativeTests

OUT = Path(os.environ.get('EES_TEST_SCREENSHOT_DIR', Path(__file__).parent))

class Parity(FigmaAuthoringNativeTests, FigmaRuntimeNativeTests):
    def test_operations31_saved_reason_reference_state(self):
        """Use real commands for the design's two-result state, without forged history."""
        self.command('save_factory', factory_id='figma-factory-a', system_id='EMS', name='공장 A', attributes={})
        key, _ = self.operations_stage(start=False)
        run = self.start(key, factory_id='figma-factory-a', inputs={'query': '이번 배포 문서'})
        self.bridge.result = {'status': 'failed', 'completeness': 'complete', 'items': [], 'data': {'summary': '합성 실패 원본'}}
        result = asyncio.run(self.server.workflow.operations.command(self.server.user, {
            'action': 'execute_job', 'run_id': run['id'], 'job_id': 'job-3',
            'expected_revision': run['revision'], 'request_id': str(uuid4())}))
        self.assertEqual(result['attempt']['status'], 'failed')
        run = self.state(run_id=run['id'])['run']
        note = '배치 주기 변경 내용을 확인했습니다.'
        run = self.command('human_confirm', run_id=run['id'], job_id='job-6',
            expected_revision=run['revision'], judgment_id='approved', note=note)['run']
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.refresh()
        self.open_sidebar()
        self.click('#ees-work-site-trigger')
        self.click('[data-action=choose_factory][data-factory-id=figma-factory-a]')
        self.wait("document.querySelector('#ees-work-site-trigger')?.textContent.includes('공장 A')")
        self.open_run(key, run, job='')
        self.assertIn('나머지 승인 1건', self.text('[data-action=stage_approved]'))
        if not self.browser.evaluate("!!document.querySelector('[data-action=stage_evidence][data-job-id=job-6]')"):
            self.click('[data-action=stage_approved]')
            self.wait("document.querySelector('[data-action=stage_evidence][data-job-id=job-6]')")
        self.click('[data-action=stage_evidence][data-job-id=job-6]')
        self.click('[data-action=stage_approved]')
        self.wait("!document.querySelector('#stage-evidence-job-6') && document.querySelector('[data-action=stage_approved]')?.getAttribute('aria-expanded')==='false'")
        self.click('[data-action=stage_approved]')
        self.click('[data-action=stage_evidence][data-job-id=job-6]')
        self.click('#stage-evidence-job-6 [data-stage-note]')
        self.assertEqual(self.read('#stage-evidence-job-6 [data-stage-note]', 'value'), note)
        self.assertTrue(self.read('#stage-evidence-job-6 [data-stage-note]', 'readOnly'))
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel', 'x': 1700, 'y': 900, 'deltaX': 0, 'deltaY': 10000})
        self.browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        self.stage_capture('operations31-reason-reference-1920')

    def screenshot(self, label, *, wait_for_fonts=True):
        directory = IntegratedNativeCase.screenshot(self, label, wait_for_fonts=wait_for_fonts)
        if getattr(self, '_capturing_panel', False):
            return directory
        if not self.browser.evaluate("!!document.querySelector('#ees-work-dialog[open],.ees-panel-region')"):
            return directory
        self._capturing_panel = True
        previous = self.browser.evaluate('({width:innerWidth,height:innerHeight})')
        if label.startswith('c66-b3-') and label.endswith('-1366'):
            height = 918 if 'unconnected' in label else 1186 if 'review-required' in label else 1077 if 'connected' in label else 865
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth===1920 && innerHeight===' + str(height))
        if label.startswith('c66-'):
            self.browser.evaluate("document.querySelector('.ew-author-scroll')?.scrollTo(0,0)")
        self.browser.evaluate('document.fonts.ready.then(()=>true)')
        self.wait("!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing]') && [...document.getAnimations()].every(a=>a.effect?.getTiming().iterations===Infinity||(!a.pending&&a.playState!=='running'))")
        observation = self.browser.evaluate("""(()=>{
          const panel=document.querySelector('#ees-work-dialog[open]')||document.querySelector('.ees-panel-region'), r=panel.getBoundingClientRect();
          const box=e=>{if(!e)return null;const b=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:b.x-r.x,y:b.y-r.y,width:b.width,height:b.height,fontSize:s.fontSize,lineHeight:s.lineHeight,fontWeight:s.fontWeight,color:s.color,background:s.backgroundColor,borderRadius:s.borderRadius,text:(e.value??e.innerText??'').slice(0,1000)};};
          const selectors=['.ew-panel-header','.ew-operation-overview','.ew-operation-overview h2','.ew-operation-context','.ew-operation-context dt','.ew-operation-context dd','.ew-operation-stages','.ew-operation-stage','.ew-vd-head','.ew-tabs','.ew-vd-label','.ew-vd-item','.ew-vd-note textarea','.ew-vd-note small','.ew-vd-selection-record','.ew-author>header','.ew-author-definition-head','.ew-author-tabs','.ew-job-detail-header','#ew-author-node [name=name]','.ew-job-method','#ew-author-node [name=job_guidance]','#ew-author-node [name=result_block]','#ew-author-node [name=completion_rule]','#ew-author-node [name=assignee]','.ew-author>footer','.ew-job-tool-state','.ew-job-tool-state img','.ew-job-result-confirmation','.ew-job-tool-summary'];
          const stage=panel.querySelector('.ew-operation-stage'),s=stage&&getComputedStyle(stage),after=stage&&getComputedStyle(stage,'::after');
          const stageDivider=stage?{borderBottomWidth:s.borderBottomWidth,borderRadius:s.borderRadius,overflow:s.overflow,afterHeight:after.height,afterBottom:after.bottom,afterColor:after.backgroundColor,afterContent:after.content}:null;
          return {label:null,viewport:{width:innerWidth,height:innerHeight},panel:{x:r.x,y:r.y,width:r.width,height:r.height},bodyOverflow:document.documentElement.scrollWidth-innerWidth,panelOverflow:panel.scrollWidth-panel.clientWidth,text:panel.innerText,stageDivider,geometry:Object.fromEntries(selectors.map(s=>[s,box(panel.querySelector(s))])),images:[...panel.querySelectorAll('img')].map(e=>({src:e.getAttribute('src'),naturalWidth:e.naturalWidth,naturalHeight:e.naturalHeight,box:box(e)}))};
        })()""")
        observation['label'] = label
        self.assertLessEqual(observation['bodyOverflow'], 0)
        self.assertLessEqual(observation['panelOverflow'], 1)
        self.assertTrue(all(x['naturalWidth'] > 0 for x in observation['images']), observation['images'])
        if observation['stageDivider']:
            divider=observation['stageDivider']
            self.assertEqual(divider['borderBottomWidth'],'0px')
            self.assertEqual(divider['afterHeight'],'1px')
            self.assertEqual(divider['afterBottom'],'0px')
            self.assertEqual(divider['overflow'],'hidden')
            self.assertEqual(observation['geometry']['.ew-operation-stage']['height'],71)
        for selector in ['.ew-operation-context dt','.ew-job-detail-header','.ew-vd-note small']:
            if observation['geometry'][selector]:
                self.assertEqual(observation['geometry'][selector]['color'],'rgb(111, 113, 122)',selector)
        (OUT / (label + '-panel.json')).write_text(json.dumps(observation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        clip = {**observation['panel'], 'scale': 1}
        png = base64.b64decode(self.browser.call('Page.captureScreenshot', {'format': 'png', 'clip': clip, 'captureBeyondViewport': True})['data'])
        (OUT / (label + '-panel.png')).write_bytes(png)
        self.browser.call('Emulation.setDeviceMetricsOverride', {**previous, 'deviceScaleFactor': 1, 'mobile': False})
        self._capturing_panel = False
        return directory

TESTS = [
    'test_operations31_saved_reason_reference_state',
    'test_operations31_preexecution_navigation_creates_no_run_or_attempt',
    'test_operations31_reason_draft_is_private_and_saved_with_explicit_verdict',
    'test_operations_stage_actual_jobs_header_and_judgment_menu_at_two_widths',
    'test_operations_stage_actual_tool_evidence_retry_and_scope_execution',
    'test_c66_job_methods_arguments_d5_and_read_only_at_480_and_1366',
]

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('tests',nargs='*');args=parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names=args.tests or TESTS
    files=['branding/ees/ui/ees-work-launcher.js','branding/ees/ui/ees-work-view.js','branding/ees/ui/ees-work-designer.js','branding/ees/ui/ees-work-launcher.css','tests/test_ees_work_figma_runtime_native.py','tests/test_ees_work_figma_authoring_native.py','tests/ees_work_integrated_fixture.py',str(Path(__file__).relative_to(ROOT))]
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    manifest_path=Path(os.environ['EES_TEST_BRANDING_DIR'])/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    built_ui={name:manifest['source_frontend']['source_inputs'][name] for name in files[:4]}
    assert all(hashes[name]==value for name,value in built_ui.items()), 'Source and built frontend differ'
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Parity(name) for name in names))
    unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in hashes.items())
    report={'tests':names,'testsRun':result.testsRun,'success':result.wasSuccessful() and unchanged,'failures':[(str(t),e) for t,e in result.failures],'errors':[(str(t),e) for t,e in result.errors],'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,encoding='utf-8').strip(),'working_tree_modified':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True,encoding='utf-8').strip()),'source_hashes':hashes,'source_unchanged_during_run':unchanged,'built_ui_hashes':built_ui,'wheel':manifest['wheel'],'branding_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'scope':'Actual built Native frontend and production workflow service/SQLite; synthetic authentication, tool metadata and external transports. No product DOM substitutions.'}
    (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not report['success'])
