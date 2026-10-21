"""Built Native authoring UI with real workspace/operations SQLite commands.

Reconstructed from retained session source/patch text after workspace loss;
requires new verification and new screenshots. Native session and external read
transport are synthetic. The complete CLI gate verifies real login separately.
"""
import asyncio
import base64
from copy import deepcopy
import importlib
import json
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from uuid import UUID, uuid4

from ees_work_integrated_fixture import IntegratedNativeCase
from native_ui_fixture import MODELS, NativeUIHandler
from test_ees_helper_chat_native import install_helper_status_fixture


class FigmaAuthoringNativeTests(IntegratedNativeCase):
    def test_c44_manual_authoring_inline_cancel_save_reopen_and_fix_validation(self):
        self.server.models = []
        self.navigate('/')
        self.wait("document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action=create]')
        self.fill('#ees-work-dialog [name=name]', 'EES Workflow 셋업 · 합성 검증')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        identifier = next(item['id'] for item in self.state()['workflows'] if item['name'] == 'EES Workflow 셋업 · 합성 검증')
        self.assertIn('업무 도우미가 아직 연결되지 않았습니다', self.text('[data-ees-procedure-fallback]'))
        self.click('[data-author-action=summary_edit][data-id=business]')
        self.choose('#ew-summary-editor [name=category]', 'setup')
        self.fill('#ew-summary-editor [name=description]', '개인 PC 개발 준비 · 취소할 내용')
        self.click('[data-author-action=summary_cancel]')
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['draft']['category'], 'ops')
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=summary_edit][data-id=business]')"),
                        self.browser.evaluate('document.activeElement?.outerHTML'))
        self.click('[data-author-action=summary_edit][data-id=business]')
        self.choose('#ew-summary-editor [name=category]', 'setup')
        self.fill('#ew-summary-editor [name=description]', '개인 PC에서 개발 환경 준비')
        self.click('[data-author-action=tab][data-tab=history]')
        self.click('[data-author-action=tab][data-tab=content]')
        self.assertEqual(self.read('#ew-summary-editor [name=description]', 'value'), '개인 PC에서 개발 환경 준비')
        self.click('[data-author-action=save]')
        self.assertIn('적용하거나 취소', self.text('[role=alert]'))
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['revision'], 1)
        self.click('[data-author-action=summary_apply]')
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['revision'], 1)
        self.click('[data-author-action=summary_open]')
        self.click('[data-summary=inputs] .ew-summary-help>summary')
        self.assertIn('실제 경로 값은 실행자', self.text('[data-summary=inputs]'))
        self.click('[data-author-action=summary_optional][data-id=inputs]')
        self.click('[data-summary=rules] .ew-summary-help>summary')
        self.click('[data-author-action=summary_optional][data-id=rules]')
        original_command = self.server.workflow.workspace_command

        async def reject_save(user, body, **kwargs):
            if body.get('action') == 'save_draft':
                return {'ok': False, 'error': {'code': 'invalid_definition', 'message': '합성 저장 실패 · 재시도'}}
            return await original_command(user, body, **kwargs)

        with patch.object(self.server.workflow, 'workspace_command', side_effect=reject_save):
            self.click('[data-author-action=save]')
            self.wait("document.querySelector('[role=alert]')?.textContent.includes('합성 저장 실패')")
            self.assertEqual(self.state(workflow_id=identifier)['workflow']['revision'], 1)
            self.assertIn('저장 안 됨', self.text('[data-author-status]'))
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.textContent.includes('저장됨')")
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['draft']['category'], 'setup')
        self.click('[data-author-action=validate]')
        self.wait("document.querySelector('.ew-author-validation')")
        self.assertTrue(self.state(workflow_id=identifier)['workflow']['validation']['errors'])
        self.click('[data-author-action=validation_open][data-id="errors:0"]')
        self.click('[data-author-action=tab][data-tab=content]')
        self.add_stage_ui('개발 환경 준비')
        stage_id = self.browser.evaluate("document.querySelector('[data-author-action=stage_edit]').dataset.id")
        self.click('[data-author-action=stage_edit][data-id="' + stage_id + '"]')
        self.assertIn('아직 설정 없음', self.text('#ew-stage-editor .ew-stage-advanced > summary'))
        self.click('#ew-stage-editor .ew-stage-advanced > summary')
        self.click('#ew-stage-editor [data-author-action=node][data-id="' + stage_id + '"]')
        self.wait("document.querySelector('#ew-author-node [name=instructions]')")
        self.assertEqual(self.read('#ew-author-node [name=instructions]', 'value'), '')
        self.fill('#ew-author-node [name=instructions]', '작업을 시작하기 전에 개발 준비 사항을 확인합니다.')
        self.click('#ew-author-node .ew-job-advanced > summary')
        self.click('#ew-author-node [data-author-action=input_add]')
        self.fill('#ees-work-dialog [name=name]', '개발 준비 메모')
        self.fill('#ees-work-dialog [name=description]', '이번 진행 건의 개발 준비 사항입니다.')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.click('[data-author-action=node][data-id=""]')
        self.add_job_ui('Python 버전 확인')
        self.fill('#ew-author-node [name=instructions]', '터미널에서 Python 버전을 확인하고 결과를 기록합니다.')
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.textContent.includes('저장됨')")
        saved = self.state(workflow_id=identifier)['workflow']['draft']
        self.assertEqual(saved['nodes'][stage_id]['instructions'], '작업을 시작하기 전에 개발 준비 사항을 확인합니다.')
        self.assertEqual(len(saved['nodes'][stage_id]['inputs']), 1)
        self.assertEqual(saved['nodes'][stage_id]['inputs'][0]['name'], '개발 준비 메모')
        self.assertEqual(saved['nodes'][stage_id]['inputs'][0]['scope'], 'run')
        self.assertNotIn('value', saved['nodes'][stage_id]['inputs'][0])
        self.click('[data-author-action=list]')
        self.wait("document.querySelector('.ew-author-list')?.textContent.includes('미게시 · 이어서 작성하기')")
        self.assertIn('미게시 · 이어서 작성하기', self.text('.ew-author-list'))
        self.click('[data-author-action=open][data-id="' + identifier + '"]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('[data-author-action=tab][data-tab=content]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['draft'], saved)
        for width in (1366, 540):
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.click('[data-author-action=summary_edit][data-id=business]')
            self.assertEqual(self.read('#ew-summary-editor [name=description]', 'value'), '개인 PC에서 개발 환경 준비')
            self.click('#ew-summary-editor [name=name]')
            self.key('Tab', 9)
            self.assertEqual(self.browser.evaluate('document.activeElement.name'), 'category')
            self.assertLessEqual(self.browser.evaluate("document.querySelector('.ew-author-scroll').scrollWidth-document.querySelector('.ew-author-scroll').clientWidth"), 1)
            self.screenshot('c44-inline-business-' + str(width))
            self.key('Escape', 27)
            self.wait("!document.querySelector('#ew-summary-editor')")
        self.click('[data-author-action=validate]')
        self.wait("document.querySelector('.ew-author-validation')")
        checked = self.state(workflow_id=identifier)['workflow']
        self.assertEqual(checked['validation']['errors'], [])
        self.assertIsNone(checked['published_version'])
        self.assertEqual(checked['draft'], saved)
        self.assertEqual(self.server.completions, [])
        self.assertFalse(any(body.get('action') in ('publish_workflow', 'start_run', 'schedule_save') for body in self.server.workspace_commands))
        self.screenshot('c44-manual-validation')

        self.click('[data-author-action=tab][data-tab=content]')
        if self.read('[data-author-action=stage_toggle][data-id="' + stage_id + '"]', 'ariaExpanded') != 'true':
            self.click('[data-author-action=stage_toggle][data-id="' + stage_id + '"]')
        self.click('[data-author-action=stage_edit][data-id="' + stage_id + '"]')
        self.fill('#ew-stage-editor [name=name]', '이전 버전에서 작성한 단계 이름')
        self.fill('#ew-stage-editor [name=description]', '이전 버전에서 작성한 단계 설명')
        remote = deepcopy(checked['draft'])
        remote['nodes'][stage_id].update(name='다른 작성자의 최신 단계', description='다른 작성자가 저장한 최신 설명')
        self.users['other-user']['role'] = 'admin'
        changed = self.command('save_draft', user=self.users['other-user'], workflow_id=identifier,
            expected_revision=checked['revision'], definition=remote)
        writes = len(self.server.workspace_commands)
        self.refresh()
        self.wait("document.querySelector('[data-author-status]')?.textContent.includes(" + json.dumps('r' + str(changed['revision'])) + ")")
        self.assertEqual(self.text('[data-stage-id="' + stage_id + '"] .ew-stage-name'), '다른 작성자의 최신 단계')
        self.click('[data-author-action=inline_apply]')
        self.wait("document.querySelector('#ew-stage-name-error')?.textContent.includes('저장된 초안이 바뀌었습니다.')")
        self.assertEqual(self.read('#ew-stage-editor [name=name]', 'value'), '이전 버전에서 작성한 단계 이름')
        self.assertEqual(self.read('#ew-stage-editor [name=description]', 'value'), '이전 버전에서 작성한 단계 설명')
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('#ew-stage-editor [name=name]')"))
        self.screenshot('e1-stale-stage-buffer-preserved')
        self.click('[data-author-action=inline_cancel]')
        self.assertEqual(self.text('[data-stage-id="' + stage_id + '"] .ew-stage-name'), '다른 작성자의 최신 단계')
        self.assertIn('다른 작성자가 저장한 최신 설명', self.text('[data-stage-id="' + stage_id + '"] .ew-stage-description'))
        latest = self.state(workflow_id=identifier)['workflow']
        self.assertEqual(latest['draft'], remote)
        self.assertEqual(latest['revision'], changed['revision'])
        self.assertEqual([body for body in self.server.workspace_commands[writes:] if body.get('action') != 'save_ui'], [])

        self.click('[data-author-action=stage_edit][data-id="' + stage_id + '"]')
        self.fill('#ew-stage-editor [name=name]', '삭제 전에 작성한 단계 이름')
        removed = deepcopy(latest['draft'])
        stage = removed['nodes'][stage_id]
        removed['nodes'][stage['parent']]['children'].remove(stage_id)
        for child_id in stage['children']:
            del removed['nodes'][child_id]
        del removed['nodes'][stage_id]
        changed = self.command('save_draft', user=self.users['other-user'], workflow_id=identifier,
            expected_revision=latest['revision'], definition=removed)
        writes = len(self.server.workspace_commands)
        self.refresh()
        self.wait("document.querySelector('#ew-stage-editor')?.textContent.includes('편집하던 단계가 최신 초안에서 삭제되었습니다.')")
        self.assertGreater(self.browser.evaluate("document.querySelector('#ew-stage-editor').getBoundingClientRect().height"), 0)
        self.click('[data-author-action=inline_apply]')
        self.wait("document.querySelector('#ew-stage-name-error')?.textContent.includes('저장된 초안이 바뀌었습니다.')")
        self.assertEqual(self.read('#ew-stage-editor [name=name]', 'value'), '삭제 전에 작성한 단계 이름')
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-content-stage').length"), 0)
        self.screenshot('e1-deleted-stage-buffer-preserved')
        self.click('[data-author-action=inline_cancel]')
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=add_stage]')"))
        latest = self.state(workflow_id=identifier)['workflow']
        self.assertEqual(latest['draft'], removed)
        self.assertEqual(latest['revision'], changed['revision'])
        self.assertEqual([body for body in self.server.workspace_commands[writes:] if body.get('action') != 'save_ui'], [])

    def test_c44_input_definition_dialog_preserves_cancelled_values_and_narrow_focus(self):
        created = self.command('create_workflow', name='합성 입력 절차', system_id='EMS')
        identifier = created['workflow_id']
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action=open][data-id="' + identifier + '"]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('[data-author-action=summary_open]')
        self.click('[data-author-action=summary_edit][data-id=inputs]')
        self.click('[data-author-action=start_input_add]')
        self.fill('#ees-work-dialog [name=name]', '취소할 입력')
        self.key('Escape', 27)
        self.assertFalse(any(node.get('inputs') for node in self.state(workflow_id=identifier)['workflow']['draft']['nodes'].values()))
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 540, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
        self.click('[data-author-action=start_input_add]')
        self.assertEqual(self.browser.evaluate('document.activeElement.name'), 'name')
        self.fill('#ees-work-dialog [name=name]', '설치 경로')
        self.fill('#ees-work-dialog [name=description]', '실행자가 실제 설치할 폴더를 입력합니다.')
        self.click('#ees-work-dialog [name=required]')
        self.assertIn('실제 값 입력이나 초안 저장은 하지 않습니다', self.text('#ees-work-dialog'))
        self.assertLessEqual(self.browser.evaluate("document.querySelector('#ees-work-dialog').scrollWidth-document.querySelector('#ees-work-dialog').clientWidth"), 1)
        self.screenshot('c44-input-definition-540')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.assertEqual(self.state(workflow_id=identifier)['workflow']['revision'], 1)
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.textContent.includes('저장됨')")
        fields = [field for node in self.state(workflow_id=identifier)['workflow']['draft']['nodes'].values() for field in node.get('inputs', [])]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]['name'], '설치 경로')
        self.assertTrue(fields[0]['required'])
        self.assertNotIn('value', fields[0])

    def test_no_model_procedure_uses_figma_notice_without_hiding_saved_chat(self):
        self.server.models = []
        created = self.command('create_workflow', name='연결 없이 직접 작성', system_id='EMS')
        self.navigate('/')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.fill('#chat-input', '연결 뒤 보낼 개인 질문')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action="mode"][data-mode="author"]')
        selector = '[data-author-action="open"][data-id="' + created['workflow_id'] + '"]'
        self.wait('document.querySelector(' + json.dumps(selector) + ')')
        self.click(selector)
        self.wait("document.querySelector('[data-ees-procedure-fallback]')")
        self.assertIn('업무 도우미가 아직 연결되지 않았습니다', self.text('[data-ees-procedure-fallback]'))
        self.assertNotIn('무엇을 도와드릴까요', self.text('#messages-container'))
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-input').length"), 1)
        self.screenshot('procedure-visual-no-model')
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#messages-container')?.textContent.includes('기존')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-ees-procedure-fallback]')"))
        self.assertEqual(self.server.completions, [])

    def test_e1_content_variants_keep_names_focus_and_drafts_at_480_and_1366(self):
        """Figma A–D and examples 1–12 use real controls and synthetic records."""
        fixtures = {}
        for count in (0, 1, 3, 6):
            created = self.command('create_workflow', name='단계 화면 대조 ' + str(count), system_id='EMS')
            key = created['workflow_id']; definition = deepcopy(created['workflow']['draft'])
            root = next(node for node in definition['nodes'].values() if node['type'] == 'p')
            root['children'] = ['stage-' + str(index) for index in range(count)]
            definition['description'] = '새 공장에 EES 시스템을 설치하고 연결을 확인하는 업무'
            definition['schedule'] = {'frequency': 'daily', 'interval': 1, 'anchor': '2026-10-20T09:00',
                                      'timezone': 'Asia/Seoul', 'stage_deadlines': {'stage-0': {'offset_days': 0}}} if count else {}
            for index in range(count):
                stage_id = 'stage-' + str(index)
                jobs = ['job-' + str(index) + '-' + str(value) for value in range(2 if index == 0 else 1)]
                definition['nodes'][stage_id] = {'id': stage_id, 'type': 't', 'parent': root['id'], 'children': jobs,
                    'name': '사전준비' if index == 0 else ('긴 단계 이름 · 설치 환경과 시스템 연결 및 인계 조건을 빠짐없이 확인합니다' if index == count - 1 else '단계 ' + str(index + 1)),
                    'description': '셋업 범위와 설치 가이드를 확인합니다.\n승인된 자료를 함께 봅니다.',
                    'instructions': '기존 수행 안내 유지', 'deps': []}
                for job_id in jobs:
                    definition['nodes'][job_id] = {'id': job_id, 'type': 'j', 'parent': stage_id,
                        'children': [], 'deps': [], 'name': '셋업 가이드 찾기 ' + job_id,
                        'description': '', 'instructions': '직접 확인합니다.', 'mode': 'human', 'inputs': [],
                        'result_block': 'human_confirm', 'human_confirmation': True, 'completion': {'rule': ''}}
            self.command('save_draft', workflow_id=key, expected_revision=1, definition=definition)
            fixtures[count] = (key, definition)
        evidence = []

        def capture(label, extra=None):
            self.wait("[...document.querySelectorAll('.ew-work-content img')].every(image=>image.complete&&image.naturalWidth>0)")
            self.wait("""!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing],.ew-dialog-exit-backdrop') &&
                [...document.querySelectorAll('#ees-work-designer,#ees-work-dialog,#ees-work-help')]
                    .every(surface=>surface.getAnimations({subtree:true}).every(animation=>!animation.pending&&animation.playState!=='running'))""")
            observed = self.browser.evaluate("""(() => {
                const scroll=document.querySelector('.ew-author-scroll'), active=document.activeElement;
                const box=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {width:r.width,height:r.height,fontSize:s.fontSize,lineHeight:s.lineHeight,background:s.backgroundColor};};
                const alert=document.querySelector('#ew-stage-editor [role=alert]');
                let inlineAlert=null;
                if(alert){
                    const rect=alert.getBoundingClientRect(),scrollRect=scroll.getBoundingClientRect(),panelRect=document.querySelector('.ees-panel-region').getBoundingClientRect(),style=getComputedStyle(alert);
                    const contains=outer=>rect.left>=outer.left-1&&rect.right<=outer.right+1&&rect.top>=outer.top-1&&rect.bottom<=outer.bottom+1;
                    const hit=document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2);
                    inlineAlert={text:alert.textContent,rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom},
                        withinScroll:contains(scrollRect),withinPanel:contains(panelRect),withinViewport:contains({left:0,right:innerWidth,top:0,bottom:innerHeight}),
                        visible:rect.width>0&&rect.height>0&&style.visibility==='visible'&&Number(style.opacity)>0,
                        hitTest:!!hit&&(hit===alert||alert.contains(hit)),focusInsideEditor:!!active?.closest('#ew-stage-editor')};
                }
                return {viewport:[innerWidth,innerHeight],scrollTop:scroll.scrollTop,overflow:scroll.scrollWidth-scroll.clientWidth,
                    stages:[...document.querySelectorAll('.ew-stage-toggle')].map(e=>({id:e.dataset.id,expanded:e.getAttribute('aria-expanded'),...box(e)})),
                    jobs:[...document.querySelectorAll('.ew-job-row')].map(e=>({id:e.dataset.jobId,returned:e.dataset.returned,...box(e)})),
                    focus:{action:active?.dataset.authorAction,id:active?.dataset.id,name:active?.name},
                    inline:!!document.querySelector('#ew-stage-editor'),invalid:!!document.querySelector('#ew-stage-editor [aria-invalid=true]'),
                    inlineAlert,surfaces:[...document.querySelectorAll('#ees-work-dialog[open],#ees-work-help')].map(e=>({id:e.id,opacity:getComputedStyle(e).opacity})),
                    proposal:!!document.querySelector('.ew-author-proposal'),footer:document.querySelector('#ees-work-designer>footer')?.innerText,
                    icons:[...document.querySelectorAll('.ew-work-content img')].map(e=>({src:e.src,natural:e.naturalWidth,rendered:e.getBoundingClientRect().width}))};
            })()""")
            self.assertLessEqual(observed['overflow'], 1, observed)
            self.assertLessEqual(sum(stage['expanded'] == 'true' for stage in observed['stages']), 1)
            self.assertTrue(all(stage['height'] >= 52 for stage in observed['stages']), observed)
            self.assertTrue(all(icon['natural'] == icon['rendered'] for icon in observed['icons']), observed)
            observed.update(extra or {})
            observed['label'] = label; evidence.append(observed)
            directory = self.screenshot(label)
            (directory / 'e1-content-variants-observations.json').write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return observed

        for width in (1366, 480):
            # Establish the authoring destination while its sidebar is exposed.
            # At 480 px the open overlay correctly covers that sidebar; all
            # content actions and evidence below still use the requested width.
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === 1366')
            self.navigate('/c/existing-chat')
            self.wait("document.querySelector('#ees-work-entry')")
            self.open_sidebar(); self.click('[data-action=mode][data-mode=author]'); self.refresh()
            self.wait("document.querySelector('#ees-work-designer')")
            if self.browser.evaluate("!!document.querySelector('[data-author-action=list]')"):
                self.click('[data-author-action=list]')
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === ' + str(width))
            for count in (0, 1, 3, 6):
                key, definition = fixtures[count]
                selector = '[data-author-action=open][data-id="' + key + '"]'
                self.wait('document.querySelector(' + json.dumps(selector) + ')')
                self.click(selector)
                self.wait("document.querySelector('.ew-work-content')")
                self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-stage-toggle').length"), count)
                self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-stage-toggle[aria-expanded=true]').length"), 0)
                capture('e1-a-stage-count-' + str(count) + '-' + str(width))
                if count != 6:
                    self.click('[data-author-action=list]')
            key, original = fixtures[6]
            self.click('[data-author-action=stage_toggle][data-id=stage-0]')
            self.assertEqual(self.read('[data-author-action=move_up][data-id=stage-0]', 'disabled'), True)
            capture('e1-b-expanded-' + str(width))
            self.click('[data-author-action=stage_edit][data-id=stage-0]')
            self.assertEqual(self.browser.evaluate('document.activeElement.name'), 'name')
            self.assertFalse(self.browser.evaluate("!!document.querySelector('#ew-stage-editor [name=mode],#ew-stage-editor [name=result_block]')"))
            capture('e1-c1-stage-edit-' + str(width))
            self.fill('#ew-stage-editor [name=description]', '여러 줄 설명 보존\n두 번째 줄')
            self.click('[data-author-action=stage_toggle][data-id=stage-1]')
            self.assertIn('편집 중인 항목을 먼저 적용하거나 취소해 주세요.', self.text('#ew-stage-editor'))
            self.assertEqual(self.read('[data-author-action=stage_toggle][data-id=stage-0]', 'ariaExpanded'), 'true')
            guard = capture('e1-example7-dirty-guard-' + str(width))['inlineAlert']
            self.assertIsNotNone(guard)
            for boundary in ('withinScroll', 'withinPanel', 'withinViewport', 'visible', 'hitTest', 'focusInsideEditor'):
                self.assertTrue(guard[boundary], guard)
            self.click('[data-author-action=inline_apply]')
            self.assertIn('두 번째 줄', self.text('[data-stage-id=stage-0] .ew-stage-description'))
            self.click('[data-author-action=job_menu][data-id=job-0-0]')
            capture('e1-example4-job-menu-' + str(width))
            self.key('Escape', 27)
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-job-menu')"))
            self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=job_menu][data-id=job-0-0]')"))
            self.assertFalse(self.read('.ees-panel-region', 'hidden'))
            if width == 480:
                # The just-closed menu trigger must yield Escape to C60.
                self.key('Escape', 27)
                self.wait("document.querySelector('.ees-panel-region').hidden")
                self.click('[data-action=open_panel]')
                self.wait("!document.querySelector('.ees-panel-region').hidden && !document.querySelector('[data-ees-motion=opening]')")
            self.browser.evaluate("document.querySelector('[data-author-action=move_down][data-id=stage-0]').scrollIntoView({block:'center'})")
            before_move = self.browser.evaluate("""(() => {
                const button=document.querySelector('[data-author-action=move_down][data-id=stage-0]'),
                    current=document.querySelector('[data-stage-id=stage-0]').getBoundingClientRect(),
                    next=document.querySelector('[data-stage-id=stage-1]').getBoundingClientRect(),
                    rect=button.getBoundingClientRect();
                return {x:rect.x+rect.width/2,y:rect.y+rect.height/2,top:rect.top,
                    scroll:document.querySelector('.ew-author-scroll').scrollTop,
                    step:next.height+next.top-current.bottom,hitTest:button.contains(document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2))};
            })()""")
            self.assertTrue(before_move['hitTest'], before_move)
            for kind in ('mousePressed', 'mouseReleased'):
                self.browser.call('Input.dispatchMouseEvent', {'type':kind,'x':before_move['x'],'y':before_move['y'],
                    'button':'left','buttons':int(kind == 'mousePressed'),'clickCount':1})
            self.wait("document.querySelector('[data-author-live]')?.textContent === '2번째로 옮겼습니다'")
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-author-scroll > .ew-author-note[role=status]')"))
            move = self.browser.evaluate("""(() => {
                const button=document.querySelector('[data-author-action=move_down][data-id=stage-0]'),
                    live=document.querySelector('[data-author-live]'),rect=live.getBoundingClientRect(),style=getComputedStyle(live);
                return {top:button.getBoundingClientRect().top,scroll:document.querySelector('.ew-author-scroll').scrollTop,
                    focus:document.activeElement===button,live:live.textContent,livePosition:style.position,
                    liveWidth:rect.width,liveHeight:rect.height};
            })()""")
            self.assertAlmostEqual(move['top'] + move['scroll'] - before_move['top'] - before_move['scroll'], before_move['step'], delta=1)
            self.assertTrue(move['focus'], move)
            self.assertEqual(move['livePosition'], 'absolute', move)
            self.assertLessEqual(move['liveWidth'], 1, move)
            self.assertLessEqual(move['liveHeight'], 1, move)

            self.assertEqual(self.read('[data-author-action=stage_toggle][data-id=stage-0]', 'ariaExpanded'), 'true')
            capture('e1-example8-stage-moved-' + str(width), {'reorder': {'before': before_move, 'after': move}})
            self.browser.evaluate("document.querySelector('[data-author-action=node][data-id=job-0-0]').scrollIntoView({block:'center',inline:'nearest'})")
            return_scroll = self.read('.ew-author-scroll', 'scrollTop')
            self.click('[data-author-action=node][data-id=job-0-0]')
            self.wait("document.querySelector('#ew-author-node')")
            self.fill('#ew-author-node [name=instructions]', '돌아와도 유지할 작업 초안')
            self.click('[data-author-action=node][data-id=""]')
            self.wait("document.querySelector('.ew-job-row[data-returned=true]')")
            self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=node][data-id=job-0-0]')"))
            self.assertIn('변경 있음 · 저장 안 됨', self.text('[data-author-status]'))
            self.assertAlmostEqual(self.read('.ew-author-scroll', 'scrollTop'), return_scroll, delta=1)
            capture('e1-d-job-return-' + str(width))
            self.click('[data-author-action=delete_node][data-id=stage-0]')
            self.wait("document.querySelector('#ees-work-dialog[open]')")
            self.assertIn('2개 작업', self.text('#ees-work-dialog'))
            self.assertIn('이 단계의 기간 설정(실행 방식)도 함께 지웁니다.', self.text('#ees-work-dialog'))
            self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-dialog-cancel]')"))
            capture('e1-example3-stage-delete-' + str(width))
            self.key('Escape', 27)
            self.click('[data-author-action=add_stage]')
            self.assertEqual(self.read('#ew-stage-editor [name=name]', 'placeholder'), '예: 운영 인계')
            capture('e1-c2-stage-add-' + str(width))
            self.click('[data-author-action=inline_apply]')
            self.assertIn('단계 이름을 입력해 주세요.', self.text('#ew-stage-editor'))
            capture('e1-example6-empty-name-' + str(width))
            self.fill('#ew-stage-editor [name=name]', '운영 인계')
            self.click('[data-author-action=inline_apply]')
            self.wait("document.activeElement?.matches('[data-author-action=add_job]')")
            self.assertIn('이 단계에는 아직 작업이 없습니다.', self.text('.ew-stage-body'))
            capture('e1-example2-empty-stage-' + str(width))
            self.click('[data-author-action=add_job]')
            self.assertEqual(self.read('#ew-stage-editor [name=name]', 'placeholder'), '예: 설치 상태 확인')
            capture('e1-example5-job-add-' + str(width))
            self.key('Escape', 27)
            self.click('[data-author-action=help][data-id=stages_and_jobs]')
            self.wait("document.querySelector('#ees-work-help')")
            self.assertIn('단계는 작업을 묶는 이름입니다. 개수·이름·순서는 업무에 맞게 정합니다.', self.text('#ees-work-help'))
            self.assertIn('단계 순서는 화면에 보이는 순서입니다.', self.text('#ees-work-help'))
            self.assertIn('먼저 끝나야 하는 작업은 작업 상세의 ‘앞 작업’에서 정합니다.', self.text('#ees-work-help'))
            capture('e1-example10-stage-help-' + str(width))
            self.key('Escape', 27)
            self.click('[data-author-action=stage_toggle][data-id=stage-0]')
            proposed = deepcopy(original)
            proposed['nodes']['job-0-0']['name'] = 'DB 연결·계정 확인'
            proposed['nodes']['job-0-0']['instructions'] = '제안된 수행 안내'
            reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
            payload = {'workflow_id': key, 'base_revision': 2, 'context_id': reference['context_id'], 'definition': proposed}
            result = self.browser.evaluate("window.__eesNativeWorkV1.propose('existing-chat'," + json.dumps(payload, ensure_ascii=False) + ")")
            self.assertTrue(result['ok'], result)
            self.assertIn('바뀌는 것', self.text('.ew-author-proposal'))
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-author-proposal pre,.ew-author-proposal textarea')"))
            self.assertTrue(self.browser.evaluate("!!document.querySelector('.ew-proposal-bar [data-author-action=ai_apply]')"))
            self.assertTrue(self.browser.evaluate("!!document.querySelector('.ew-proposal-bar [data-author-action=ai_discard]')"))
            self.browser.evaluate("document.querySelector('.ew-author-scroll').scrollTop=0")
            capture('e1-example12-proposal-' + str(width))
            self.browser.evaluate("document.querySelector('.ew-job-row[data-job-id=job-0-0]').scrollIntoView({block:'center'})")
            self.assertTrue(self.browser.evaluate("!!document.querySelector('.ew-job-row[data-job-id=job-0-0] .ew-proposal-mark')"))
            capture('e1-example12-changed-row-' + str(width))
            self.click('[data-author-action=ai_discard]')
            current_state = self.server.workflow.workspace_state

            async def read_only_state(user, **query):
                result = await current_state(user, **query)
                if result.get('workflow'):
                    result['workflow']['can_edit'] = False; result['workflow']['can_manage'] = False
                return result

            with patch.object(self.server.workflow, 'workspace_state', side_effect=read_only_state):
                self.refresh()
                self.wait("!document.querySelector('[data-author-action=add_stage]')")
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-stage-actions,.ew-job-menu-button,[data-author-action=stage_edit],[data-author-action=add_job]')"))
                self.click('[data-author-action=stage_toggle][data-id=stage-1]')
                self.click('[data-author-action=stage_toggle][data-id=stage-0]')
                capture('e1-example9-read-only-' + str(width))
            self.assertEqual(self.state(workflow_id=key)['workflow']['draft'], original)
            self.assertEqual(self.state(workflow_id=key)['workflow']['revision'], 2)
        self.assertEqual(self.server.completions, [])

    def test_e1_proposal_position_counts_and_grouped_rows_at_480_and_1366(self):
        created = self.command('create_workflow', name='제안 변경 위치 합성 검증', system_id='EMS')
        key = created['workflow_id']; original = deepcopy(created['workflow']['draft'])
        root = next(node for node in original['nodes'].values() if node['type'] == 'p')
        root['children'] = ['stage-0', 'stage-1', 'stage-2']
        original['schedule'] = {'frequency': 'daily', 'interval': 1, 'anchor': '2026-10-20T09:00',
            'timezone': 'Asia/Seoul', 'stage_deadlines': {'stage-0': {'offset_days': 0}}}
        for index, name in enumerate(('사전준비', '시스템 설치', '운영 인계')):
            stage = 'stage-' + str(index)
            children = [stage + '-job-' + str(number) for number in range(2)]
            original['nodes'][stage] = {'id': stage, 'type': 't', 'name': name, 'parent': root['id'], 'children': children, 'deps': []}
            for number, job in enumerate(children):
                original['nodes'][job] = {'id': job, 'type': 'j', 'name': name + ' 작업 ' + str(number + 1),
                    'parent': stage, 'children': [], 'deps': [], 'mode': 'human', 'inputs': [],
                    'instructions': '합성 확인', 'result_block': 'human_confirm'}
        self.command('save_draft', workflow_id=key, expected_revision=1, definition=original)

        def propose(definition, count):
            reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
            payload = {'workflow_id': key, 'base_revision': 2, 'context_id': reference['context_id'], 'definition': definition}
            result = self.browser.evaluate("window.__eesNativeWorkV1.propose('existing-chat'," + json.dumps(payload, ensure_ascii=False) + ")")
            self.assertTrue(result['ok'], result)
            self.assertEqual(self.text('.ew-proposal-changes h3'), '바뀌는 것 ' + str(count))
            self.assertIn(str(count) + '곳', self.text('.ew-proposal-bar'))
            return self.browser.evaluate("[...document.querySelectorAll('.ew-proposal-change-list>li')].map(e=>({kind:e.dataset.change,text:e.textContent}))")

        observations = []
        for width in (1366, 480):
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.navigate('/c/existing-chat'); self.wait("document.querySelector('#ees-work-entry')")
            self.open_sidebar(); self.click('[data-action=mode][data-mode=author]'); self.refresh()
            if self.browser.evaluate("!!document.querySelector('[data-author-action=list]')"):
                self.click('[data-author-action=list]')
            self.click('[data-author-action=open][data-id="' + key + '"]')
            self.wait("document.querySelectorAll('.ew-stage-toggle').length===3")
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === ' + str(width))
            removed = deepcopy(original)
            removed['nodes'][root['id']]['children'].remove('stage-0')
            for identifier in ['stage-0', *original['nodes']['stage-0']['children']]:
                del removed['nodes'][identifier]
            # Deliberately retain the deadline key sent by the current chat tool.
            rows = propose(removed, 3)
            self.assertEqual([row['kind'] for row in rows], ['removed'], rows)
            self.assertIn('기간 설정도 함께 지웁니다', rows[0]['text'])
            for identifier in ('stage-1', 'stage-2'):
                self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-stage-id=" + identifier + "] .ew-proposal-mark')"))
            self.screenshot('e1-example12-delete-only-' + str(width))
            self.click('[data-author-action=ai_discard]')

            inserted = deepcopy(original)
            inserted['nodes']['inserted'] = {'id': 'inserted', 'type': 't', 'name': '맨 앞 단계', 'parent': root['id'], 'children': [], 'deps': []}
            inserted['nodes'][root['id']]['children'].insert(0, 'inserted')
            self.assertEqual([row['kind'] for row in propose(inserted, 1)], ['added'])
            self.click('[data-author-action=ai_discard]')
            swapped = deepcopy(original)
            swapped['nodes']['stage-1']['children'].reverse()
            self.assertEqual([row['kind'] for row in propose(swapped, 1)], ['changed'])
            self.click('[data-author-action=ai_discard]')
            moved = deepcopy(original)
            job = moved['nodes']['stage-1']['children'].pop(0)
            moved['nodes']['stage-2']['children'].append(job); moved['nodes'][job]['parent'] = 'stage-2'
            self.assertEqual([row['kind'] for row in propose(moved, 1)], ['changed'])
            self.click('[data-author-action=ai_discard]')

            grouped = deepcopy(removed)
            for identifier, name in (('new-a', '인계 문서 확인'), ('new-b', '담당자 인계')):
                grouped['nodes'][identifier] = {**deepcopy(original['nodes']['stage-2-job-0']), 'id': identifier, 'name': name}
                grouped['nodes']['stage-2']['children'].append(identifier)
            grouped['nodes']['stage-1-job-0']['name'] = '설치·계정 확인'
            rows = propose(grouped, 6)
            self.assertEqual([row['kind'] for row in rows], ['removed', 'added', 'changed'], rows)
            self.assertIn('인계 문서 확인', rows[1]['text']); self.assertIn('담당자 인계', rows[1]['text'])
            self.assertIn('— 운영 인계', rows[1]['text'])
            self.browser.evaluate("document.querySelector('.ew-author-scroll').scrollTop=0")
            self.wait("!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing]')")
            self.assertLessEqual(self.browser.evaluate("document.querySelector('.ew-author-scroll').scrollWidth-document.querySelector('.ew-author-scroll').clientWidth"), 1)
            directory = self.screenshot('e1-example12-grouped-' + str(width))
            observations.append({'width': width, 'rows': rows, 'count': 6, 'deletionOnlyCount': 3,
                'frontInsertionCount': 1, 'adjacentSwapCount': 1, 'crossStageMoveCount': 1})
            (directory / 'e1-proposal-review-observations.json').write_text(json.dumps(observations, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            self.click('[data-author-action=ai_discard]')
            self.assertEqual(self.state(workflow_id=key)['workflow']['draft'], original)
            self.assertEqual(self.state(workflow_id=key)['workflow']['revision'], 2)

    def test_procedure_visual_geometry_matches_figma_and_preserves_native_draft(self):
        created = self.command('create_workflow', name='시각 대조 절차', system_id='EMS')
        identifier = created['workflow_id']
        workspace = self.state(workflow_id=identifier)
        original = workspace['workflow']
        expected_factory_views = [{'id': '', 'label': '기본 절차', 'selected': 'true'}] + [
            {'id': item['id'], 'label': item.get('name') or item['id'], 'selected': 'false'}
            for item in workspace.get('factories', [])]
        self.fill('#chat-input', '화면 전환 전 개인 입력')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('[data-author-action=open][data-id=" + json.dumps(identifier) + "]')")
        self.click('[data-author-action="open"][data-id="' + identifier + '"]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        for width, height in ((1920, 1080), (1440, 1080), (1366, 768), (480, 768)):
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === ' + str(width))
            metrics = self.browser.evaluate("""(() => {
              const bounds = selector => {const box=document.querySelector(selector).getBoundingClientRect();return {x:box.x,y:box.y,width:box.width,height:box.height};};
              const style = selector => {const value=getComputedStyle(document.querySelector(selector));return {font:value.fontFamily,size:value.fontSize,line:value.lineHeight,background:value.backgroundColor};};
              return {panel:bounds('.ees-panel-region'),frame:bounds('[data-ees-source-shell]'),sidebar:bounds('#sidebar'),
                overlay:document.querySelector('.ees-panel-region').getAttribute('data-overlay'),header:bounds('.ew-author>header'),
                card:bounds('.ew-work-content'),purpose:bounds('.ew-content-purpose'),needs:bounds('.ew-content-needs'),steps:bounds('.ew-content-heading'),list:bounds('.ew-stage-list'),footer:bounds('.ew-author>footer'),
                availableWidth:document.querySelector('.ees-panel-region').parentElement.getBoundingClientRect().width,
                badge:style('.ew-author-heading>.ew-author-tag'),detail:style('.ew-content-purpose>p'),
                tabs:style('.ew-author-tabs>button'),heading:style('.ew-author h2'),
                extraHeader:document.querySelectorAll('#ees-work-panel>.ew-panel-header').length,
                factoryTabs:document.querySelectorAll('.ew-author-factories').length,
                factoryLabel:document.querySelector('.ew-author-factories')?.getAttribute('aria-label'),
                factoryViews:[...document.querySelectorAll('.ew-author-factories [data-author-action=factory]')].map(e=>({id:e.dataset.id,label:e.textContent.trim(),selected:e.getAttribute('aria-selected')})),
                overflow:document.querySelector('.ew-author-scroll').scrollWidth-document.querySelector('.ew-author-scroll').clientWidth};
            })()""")
            self.assertEqual(metrics['overlay'], 'true' if width == 480 else 'false')
            # Overlay retains the existing 56 px navigation rail even when the
            # authoring panel's preferred 580 px width cannot fit the frame.
            available_panel_width = metrics['availableWidth'] - (56 if metrics['overlay'] == 'true' else 0)
            metrics['expectedPanelWidth'] = min(580, available_panel_width)
            metrics['panelFrameLeftGap'] = metrics['panel']['x'] - metrics['frame']['x']
            self.assertEqual(metrics['panel']['width'], metrics['expectedPanelWidth'])
            self.assertEqual(metrics['panel']['x'] + metrics['panel']['width'], width)
            if metrics['overlay'] == 'true':
                self.assertEqual(metrics['sidebar']['width'], 56)
                self.assertEqual(metrics['panelFrameLeftGap'], max(56, metrics['availableWidth'] - 580))
            self.assertEqual(metrics['header']['height'], 48)
            self.assertEqual(metrics['extraHeader'], 0)
            self.assertEqual(metrics['factoryTabs'], 1)
            self.assertEqual(metrics['factoryLabel'], '공장별 차이')
            self.assertEqual(metrics['factoryViews'], expected_factory_views)
            self.assertAlmostEqual(metrics['card']['x'] - metrics['panel']['x'], 21, delta=1)
            self.assertLess(metrics['purpose']['y'], metrics['needs']['y'])
            self.assertLess(metrics['needs']['y'], metrics['steps']['y'])
            self.assertLess(metrics['steps']['y'], metrics['list']['y'])
            self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-author-action=stage_toggle]').length"), 0)
            self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('.ew-author-tabs>button')].map(e=>e.textContent.trim())"), ['업무 내용', '실행 방식', '판정 규칙', '게시 기록'])
            self.assertEqual(metrics['footer']['height'], 59)
            self.assertEqual(metrics['heading']['size'], '20px')
            self.assertTrue(metrics['heading']['font'].startswith('"EES Noto Sans KR"'))
            self.assertEqual(metrics['detail']['size'], '14px')
            self.assertEqual(metrics['detail']['line'], '22px')
            self.assertEqual(metrics['tabs']['size'], '14px')
            self.assertEqual(metrics['badge']['size'], '12px')
            self.assertEqual(metrics['badge']['background'], 'rgb(250, 241, 228)')
            self.assertLessEqual(metrics['overflow'], 1)
            self.assertEqual(self.text('.ew-author-heading>.ew-author-tag'), '초안')
            self.assertIn('초안 r1 · 저장됨', self.text('[data-author-status]'))
            directory = self.screenshot('procedure-visual-content-empty-' + str(width))
            (directory / ('procedure-visual-content-empty-' + str(width) + '-geometry.json')).write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.wait("[...document.querySelectorAll('#ees-work-designer img')].every(image=>image.complete&&image.naturalWidth>0)")
        assets = self.browser.evaluate("[...document.querySelectorAll('.ew-author-back img,.ew-content-heading img')].map(image=>[image.naturalWidth,image.getBoundingClientRect().width])")
        self.assertTrue(assets)
        self.assertTrue(all(natural == rendered for natural, rendered in assets), assets)
        self.click('.ew-author>header [data-action=close_panel]')
        self.wait("document.querySelector('.ees-panel-region')?.hidden")
        self.click('#ees-work-panel-open')
        self.wait("!document.querySelector('.ees-panel-region')?.hidden")
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.state(workflow_id=identifier)['workflow'], original)
        self.assertEqual(self.server.completions, [])

    def test_b10_shared_tools_list_detail_picker_style_and_keyboard(self):
        # The product uses its real HTTP/SQLite paths; only installed Native
        # metadata and session are synthetic here (real Native is a separate gate).
        def badge_colors(selector):
            return self.browser.evaluate("(()=>{const s=getComputedStyle(document.querySelector("+json.dumps(selector)+"));return {background:s.backgroundColor.match(/[\\d.]+/g).map(Number),foreground:s.color.match(/[\\d.]+/g).map(Number)};})()")

        def assert_neutral_badge(colors):
            # The B10 cards distinguish unreviewed gray from the warm warning
            # badge. Check rendered colors, independent of CSS token/class names.
            for channels in colors.values():
                self.assertLessEqual(max(channels[:3])-min(channels[:3]), 20, colors)
                if len(channels) == 4:
                    self.assertGreaterEqual(channels[3], 0.95, colors)
            self.assertGreater(sum(colors['background'][:3])/3, 180, colors)
            self.assertLess(sum(colors['background'][:3])/3, 250, colors)
            self.assertGreater(sum(colors['background'][:3])-sum(colors['foreground'][:3]), 240, colors)

        self.server.native_plugins_enabled = True
        self.native_menu_fixture()
        self.navigate('/c/existing-chat')  # Reload Native config after enabling the fixture flag.
        self.wait("document.querySelector('#chat-input.ProseMirror') && document.querySelector('#ees-work-entry') && window.__eesNativeWorkV1?.refresh")
        self.open_sidebar()
        self.wait("document.querySelector('#ees-work-panel') && document.querySelector('#ees-work-system-trigger')?.getBoundingClientRect().height > 0")
        native = importlib.import_module(self.backend.__package__ + '.ees_workflow_native')
        source = (Path(__file__).resolve().parents[1] / 'agent-pack/skills/confluence-read/scripts/confluence_tool.py').read_text(encoding='utf-8')
        schemas = {'search_pages': {'type':'object','properties':{'query':{'type':'string'},'space_key':{'type':'string','default':''},'limit':{'type':'integer','default':5}},'required':['query']}, 'get_page': {'type':'object','properties':{'page_id':{'type':'string'}},'required':['page_id']}}
        reference = {'tool_id':'arbitrary-installed-id','function':'search_pages','revision':1,'content_hash':native.MANAGED_READ_SOURCE_HASHES['confluence'],'schema_hash':'b'*64,'config_hash':'c'*64,'environment':'d'*64}
        async def managed(): return [{'id':'arbitrary-installed-id','content':source}]
        async def inspect(actor, tool_id, function):
            return {'reference':{**reference,'function':function},'schema':schemas[function],'state':'allowed'}
        self.bridge.managed_tools, self.bridge.inspect = managed, inspect
        self.server.workflow.group_lookup = lambda _: [{'id':'shared-readers','name':'조회 팀'}]
        self.server.workflow.group_list_lookup = lambda: [{'id':'shared-readers','name':'조회 팀'}]
        items = asyncio.run(self.server.workflow.shared_tools.discover(self.server.user))
        self.refresh(); self.open_tools(shared_list=True)
        self.wait("document.querySelector('[data-author-action=shared_open][data-id=managed-search_pages]')")
        self.assertEqual(self.text('#ees-work-designer > header'), '도구 · 공용')
        self.assertEqual(self.text('[data-author-action=shared_open][data-id=managed-search_pages] .ew-author-tag'), '확인 전')
        unreviewed_list_colors = badge_colors('[data-author-action=shared_open][data-id=managed-search_pages] .ew-author-tag')
        assert_neutral_badge(unreviewed_list_colors)
        self.screenshot('shared-b10-1-before-review')
        self.click('[data-author-action=shared_open][data-id=managed-search_pages]')
        self.assertEqual(self.text('.ew-shared-card .ew-author-tag'), '확인 전')
        unreviewed_detail_colors = badge_colors('.ew-shared-card .ew-author-tag')
        assert_neutral_badge(unreviewed_detail_colors)
        self.assertTrue(self.read('[data-author-action=shared_review]', 'checkVisibility()'))
        self.screenshot('shared-b10-2-before-review')
        self.click('[data-author-action=shared_list]')
        with self.server.workflow._db(write=True) as db:
            for item in items:
                if item['target']!='Confluence': continue
                item.update(state='available', version=1, revision=1, group_ids=['shared-readers'] if item['function']=='search_pages' else ['other-readers'], responsible_user_id=self.server.user['id'])
                db.execute('INSERT INTO work_shared_tools VALUES(?,?,?)',(item['id'],1,json.dumps(item,ensure_ascii=False)))
                db.execute('INSERT INTO work_shared_tool_versions VALUES(?,?,?)',(item['id'],1,json.dumps({'version':1,'at':1792051200,'input_schema':item['input_schema'],'output_schema':item['output_schema'],'reference':item['reference']},ensure_ascii=False)))
        wid = self.author(name='공용 도구 선택 시험', jobs=1)
        self.refresh()
        self.open_tools(shared_list=True)
        self.wait("document.querySelector('[data-author-action=shared_open]')")
        self.assertEqual(self.text('#ees-work-designer > header'), '도구 · 공용')
        self.assertNotIn('기능 연결', self.text('#ees-work-entry'))
        self.assertIn('개인 PAT(기존 방식)', self.text('#ees-work-designer'))
        self.assertIn('이전 방식 도구(관리 시스템별)', self.text('#ees-work-designer'))
        self.screenshot('shared-b10-1-list')
        self.click('[data-author-action="shared_open"][data-id="managed-search_pages"]')
        for label in ('하는 일','입력과 결과','쓰는 곳','지금 버전','버전 기록','프로그램 갱신으로만 바뀝니다'):
            self.assertIn(label,self.text('#ees-work-designer'))
        self.screenshot('shared-b10-2-detail-top')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-author-action=shared_review]')"))
        for label in ('찾을 말', '공간', '개수', '글자', '숫자'):
            self.assertIn(label, self.text('#ees-work-designer'))
        reference['config_hash'] = 'e'*64
        self.refresh()
        self.wait("!!document.querySelector('[data-author-action=shared_review]')")
        self.assertEqual(self.text('.ew-shared-card .ew-author-tag'), '도구 확인 필요')
        review_colors = badge_colors('.ew-shared-card .ew-author-tag')
        self.assertGreater(review_colors['foreground'][0]-review_colors['foreground'][2], 40, review_colors)
        self.assertNotEqual(unreviewed_list_colors, review_colors)
        self.assertNotEqual(unreviewed_detail_colors, review_colors)
        self.click('[data-author-action=shared_review]')
        for label in ('항목별 비교', '현재', '새 내용', '찾을 말', '공간', '개수', '결과', '확인 근거 (필수)'):
            self.assertIn(label, self.text('#ees-work-dialog'))
        self.assertIn('바뀐 항목: 연결 설정', self.text('#ees-work-dialog'))
        self.assertNotIn('e'*64, self.text('#ees-work-dialog'))
        review_layout = self.browser.evaluate("(()=>{const access=document.querySelector('.ew-shared-access'),g=access.querySelector('fieldset').getBoundingClientRect(),o=access.querySelector('[name=owner]').closest('label').getBoundingClientRect();return {display:getComputedStyle(access).display,group_bottom:g.bottom,owner_top:o.top,gap:o.top-g.bottom};})()")
        self.assertEqual(review_layout['display'], 'grid')
        self.assertGreaterEqual(review_layout['gap'], 10, review_layout)
        self.screenshot('shared-b10-2-review-comparison')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        reference['config_hash'] = 'c'*64
        self.refresh()
        self.wait("!document.querySelector('[data-author-action=shared_review]')")
        self.assertTrue(self.read('[data-author-action=shared_native]','checkVisibility()'))
        self.browser.evaluate("document.querySelector('[data-author-action=shared_native]').focus()")
        self.key('Tab',9)
        detail_focus = self.browser.evaluate("({visible:document.activeElement.matches(':focus-visible'),outline:getComputedStyle(document.activeElement).outlineStyle})")
        self.assertTrue(detail_focus['visible'], detail_focus)
        self.assertNotEqual(detail_focus['outline'],'none', detail_focus)
        geometry = self.browser.evaluate("[...document.querySelectorAll('.ew-shared-card')].map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {width:r.width,x:r.x,border:s.borderRadius,background:s.backgroundColor,padding:s.padding};})")
        self.assertGreater(len(geometry),4)
        self.assertTrue(all(item['width']>250 for item in geometry),geometry)
        self.assertEqual(len({round(item['x']) for item in geometry}),1)
        directory = self.screenshot('shared-b10-2-detail')
        self.click('[data-author-action=shared_native]')
        self.wait("location.pathname==='/workspace/tools' && document.querySelector('#workspace-container input')")
        self.assertNotIn('기능 연결', self.text('#workspace-container'))
        self.click('[data-action=procedures]')
        self.wait("document.querySelector('[data-author-action=open][data-id=\""+wid+"\"]')")
        self.click('[data-author-action="open"][data-id="'+wid+'"]')
        self.click('.ew-author-tabs [data-author-action=tab][data-tab=content]')
        self.open_author_job_ui('job-0')
        self.click('.ew-shared-picker summary')
        self.assertTrue(self.read('.ew-shared-picker','open'))
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-author-action=pick_job_tool][data-id=managed-search_pages]')"))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-author-action=pick_job_tool][data-id=managed-get_page]')"))
        self.assertIn('조회', self.text('[data-author-action=pick_job_tool][data-id=managed-search_pages]'))
        self.assertIn('필요한 도구가 없으면 관리자에게 요청하세요.', self.text('.ew-shared-picker'))
        picker_geometry = self.browser.evaluate("(()=>{const row=document.querySelector('[data-author-action=pick_job_tool][data-id=managed-search_pages]'),name=row.querySelector('strong'),range=document.createRange();range.selectNodeContents(name.firstChild);const rect=r=>({left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height});return {row:rect(row.getBoundingClientRect()),name:rect(range.getBoundingClientRect()),badge:rect(row.querySelector('.ew-author-tag').getBoundingClientRect()),description:rect(row.querySelector(':scope > small').getBoundingClientRect())};})()")
        badge_rect, name_rect = picker_geometry['badge'], picker_geometry['name']
        # The card puts the read badge beside the name, with the description on
        # its own row. A full-width badge fails both horizontal and line checks.
        self.assertGreater(badge_rect['width'], 0, picker_geometry)
        self.assertLess(badge_rect['width'], picker_geometry['row']['width']/2, picker_geometry)
        self.assertGreaterEqual(badge_rect['left'], name_rect['right']-1, picker_geometry)
        self.assertGreater(min(badge_rect['bottom'],name_rect['bottom'])-max(badge_rect['top'],name_rect['top']), min(badge_rect['height'],name_rect['height'])/2, picker_geometry)
        self.assertGreaterEqual(picker_geometry['description']['top'], max(badge_rect['bottom'],name_rect['bottom'])-1, picker_geometry)
        self.browser.evaluate("document.querySelector('#ew-shared-picker-search').focus()")
        self.key('Tab',9)
        self.assertTrue(self.browser.evaluate("document.activeElement.matches(':focus-visible')"))
        self.assertNotEqual(self.browser.evaluate("getComputedStyle(document.activeElement).outlineStyle"),'none')
        self.screenshot('shared-b10-5-picker')
        self.click('[data-author-action=pick_job_tool][data-id=managed-search_pages]')
        self.assertFalse(self.read('.ew-shared-picker','open'))
        self.assertIn('페이지 찾기',self.text('.ew-shared-picker summary'))
        self.assertNotIn('확정 목록에서 도구 인자 연결', self.text('#ees-work-designer'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ew-author-node [name=result_argument],#ew-author-node [name=result_job_id]')"))
        self.screenshot('shared-b10-5-selected-no-handoff')
        self.fill('#ew-author-node [name=read_retry_count]', '1')
        self.fill('#ew-author-node [name=read_retry_deadline]', '30')
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.textContent.includes('저장됨')")
        stored=self.state(workflow_id=wid)['workflow']['draft']['nodes']['job-0']
        self.assertEqual(stored['shared_tool_id'],'managed-search_pages')
        self.assertNotIn('tool_reference',stored)
        self.assertNotIn('tool_contract_revision',stored)
        self.assertEqual(set(stored['argument_bindings']), {'query','space_key','limit'})
        self.assertEqual(stored['read_retry'], {'count': 1, 'deadline_seconds': 30})
        self.click('[data-author-action=validate]')
        self.wait("document.querySelector('[data-author-action=publish]')?.disabled === false")
        self.assertEqual(self.state(workflow_id=wid)['workflow']['validation']['errors'], [])
        self.click('[data-author-action=publish]'); self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.innerText.includes('게시 v2')")
        self.screenshot('shared-b10-5-read-retry-published')
        self.command('save_access', principal_kind='user', principal_id=self.server.user['id'],
            system_id='EMS', factory_id='*', roles=['manager', 'participant'])
        self.server.user['role'] = 'user'
        self.server.workflow.group_lookup = lambda _: []
        self.refresh(); self.open_tools(shared_list=True)
        self.wait("document.querySelector('#ees-work-designer')?.innerText.includes('공용 도구 0개')")
        self.assertIn('쓸 수 있는 공용 도구가 없습니다. 필요한 도구는 관리자에게 요청하세요.', self.text('#ees-work-designer'))
        self.screenshot('shared-b10-1-empty-list')
        (directory/'shared-b10-comparison.json').write_text(json.dumps({'scope':'actual built product with synthetic Native session/metadata; real HTTP and SQLite','figma':{'B10-1':'1369:732','B10-2':'1368:724','B10-5':'1372:741'},'detail_cards':geometry,'review_layout':review_layout,'keyboard_focus':detail_focus,'badge_colors':{'unreviewed_list':unreviewed_list_colors,'unreviewed_detail':unreviewed_detail_colors,'review_required':review_colors},'picker_geometry':picker_geometry,'checked':['common panel heading','before-review tags in list and detail','neutral before-review badges distinct from review warning','empty visible list notice','target grouping','personal PAT label','legacy group','detail sections','admin Native link','no C45 menu','usable-only single-step picker','picker read tag beside name with description below','picker read tag and footer notice','saved shared ID without fixed reference','real query/space_key/limit schema','no redundant review button','per-field current/new comparison','Native Tools title','changed category notice','group and owner separate rows','shared list handoff controls absent','only query/space_key/limit binding keys','read retry saved and published'],'onsite':'unverified'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def operations(self):
        return asyncio.run(self.server.workflow.operations.state(self.server.user, system_id='EMS'))

    def tool_connections(self):
        """Register metadata only in this synthetic transport, never Native assets."""
        self.connected_tools = []

        def function(tool_id, name, function_name, kind):
            return {'name': name, 'function_name': function_name, 'kind': kind,
                    'reference': {'tool_id': tool_id, 'function': function_name,
                                  'revision': 1, 'content_hash': 'a' * 64,
                                  'schema_hash': 'b' * 64},
                    'schema': {'type': 'object', 'properties': {
                        'target': {'type': 'string', 'title': '대상'}}, 'required': ['target']}}

        async def registered(actor):
            return deepcopy(self.connected_tools)

        async def inspect(actor, tool_id, function_name):
            item = next((item for item in self.connected_tools
                         if item['reference']['tool_id'] == tool_id
                         and item['reference']['function'] == function_name), None)
            if item is None:
                raise self.backend.WorkflowError('native_access_denied', '연결된 기능을 확인해 주세요.')
            return deepcopy(item)

        self.bridge.registered_capabilities = registered
        self.bridge.inspect = inspect
        self.bridge.inspect_registered = inspect
        return function

    def tool_command(self, action, revision=0, **kwargs):
        result = asyncio.run(self.server.workflow.operations.command(self.server.user, {
            'action': action, 'expected_revision': revision,
            'request_id': str(uuid4()), **kwargs}))
        self.assertTrue(result['ok'], result)
        return result

    def open_tools(self, *, shared_list=False):
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-action="tools"]')
        if shared_list:
            self.wait("document.querySelector('#ees-work-designer > header')?.textContent.trim() === '도구 · 공용' && document.querySelector('#ees-work-designer .ew-author-scroll > h2')?.textContent.startsWith('공용 도구')")
        else:
            self.wait("document.querySelector('[data-author-action=tool_create]')")

    def native_menu_fixture(self, **grants):
        """UI capability fixture only; real Native ACL is tested separately."""
        self.menu_grants = dict.fromkeys(('models', 'knowledge', 'prompts', 'skills', 'tools', 'admin'), True)
        self.menu_grants.update(grants)
        native = importlib.import_module(self.backend.__package__ + '.ees_workflow_native')

        async def access(_actor):
            return {'native_access': dict(self.menu_grants), 'native_access_available': True}

        provider = patch.object(native, 'native_workspace_access', access)
        provider.start()
        self.addCleanup(provider.stop)
        self.refresh()

    def assert_reference_preserved(self, before):
        after = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        # Navigation creates a fresh request context; the selected work/help
        # reference itself must remain unchanged.
        self.assertTrue(after.get('context_id'))
        self.assertNotEqual(after['context_id'], before['context_id'])
        self.assertEqual({key: value for key, value in after.items() if key != 'context_id'},
                         {key: value for key, value in before.items() if key != 'context_id'})

    def assert_source_shell(self):
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-ees-source-shell] [data-ees-source-sidebar] #ees-work-entry')"))
        self.assertFalse(self.browser.evaluate("[...document.querySelectorAll('#sidebar-search-button,.sidebar-new-chat-icon')].some(node=>!node.closest('[data-ees-source-sidebar]'))"),
                         'The Native sidebar is no longer a mount anchor or a hidden duplicate')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))

    def assert_work_panel_not_displayed(self):
        # The source shell may retain its panel slot across Native navigation.
        # Its contents must not cover the original asset-management screen.
        self.assertFalse(self.browser.evaluate("(()=>{const panel=document.querySelector('#ees-work-panel');return !!panel&&panel.checkVisibility({visibilityProperty:true})&&panel.getBoundingClientRect().height>0;})()"))

    def search_native_skills(self, selector, query):
        first_event = len(self.browser.events)
        self.fill(selector, query)
        deadline = time.monotonic() + 9
        while time.monotonic() < deadline:
            # Drain real CDP request/response events. ResourceTiming's bounded
            # buffer is not evidence that a request was (or was not) sent.
            self.browser.evaluate('document.readyState')
            events = self.browser.events[first_event:]
            requests = [event['params'] for event in events
                        if event.get('method') == 'Network.requestWillBeSent'
                        and urlsplit(event['params']['request']['url']).path == '/api/v1/skills/list'
                        and parse_qs(urlsplit(event['params']['request']['url']).query).get('query') == [query]]
            if requests:
                request = requests[-1]
                response = next((event['params']['response'] for event in events
                                 if event.get('method') == 'Network.responseReceived'
                                 and event['params']['requestId'] == request['requestId']), None)
                finished = any(event.get('method') == 'Network.loadingFinished'
                               and event['params']['requestId'] == request['requestId'] for event in events)
                if response and finished:
                    self.assertEqual(response['status'], 200)
                    body = self.browser.call('Network.getResponseBody', {'requestId': request['requestId']})
                    payload = json.loads(base64.b64decode(body['body']) if body['base64Encoded'] else body['body'])
                    self.assertEqual(payload, {'items': [], 'total': 0})
                    self.assertEqual(self.read(selector, 'value'), query)
                    self.native_search_evidence = {'request': {'url': request['request']['url'],
                        'method': request['request']['method']}, 'status': response['status'],
                        'response': payload, 'displayed_query': self.read(selector, 'value')}
                    return
            time.sleep(.025)
        self.fail('Native skills search request/response not observed for ' + query)

    def skills_roundtrip(self, label):
        if label == 'procedure-start':
            self.wait("window.__eesNativeWorkV1.captureReference()?.kind === 'none'")
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        model = self.read('#model-selector-model-button', 'getAttribute("aria-label")')
        self.assertIn('Fixture AI', model)
        chat_params = deepcopy(self.server.chats['existing-chat']['chat']['params'])
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        self.browser.evaluate('window.__menuRoundtripDocument=' + json.dumps(label))
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]') && document.querySelector('#ees-work-entry [data-action=procedures]')")
        self.assertEqual(self.browser.evaluate('window.__menuRoundtripDocument'), label)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assert_work_panel_not_displayed()
        self.assert_source_shell()
        self.wait("document.querySelector('[data-action=native_open][data-native-id=skills]')?.getAttribute('aria-current') === 'page'")
        self.assertEqual(self.read('[data-action=native_open][data-native-id=skills]', 'getAttribute("aria-current")'), 'page')
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('#ees-work-entry [aria-current=page]')].map(e=>e.dataset.nativeId)"), ['skills'])
        self.assertFalse(self.browser.evaluate("document.querySelector('#workspace-container')?.previousElementSibling?.querySelector('a[href=\"/workspace/skills\"]')?.getBoundingClientRect().height > 0"))
        query = 'native-menu-' + label
        self.search_native_skills('#workspace-container input[aria-label]', query)
        self.screenshot('menu-c18-skills-' + label)
        self.click('#ees-work-entry [data-action=' + ('tools' if label == 'tool' else 'procedures') + ']')
        # Persistent source slots exist before the returning workspace read is
        # validated. The reference becomes available at that actual boundary.
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-designer') && !document.querySelector('#ees-work-native-return')")
        if reference and reference.get('context_id'):
            self.wait("window.__eesNativeWorkV1?.captureReference()?.context_id")
        self.assertEqual(self.browser.evaluate('window.__menuRoundtripDocument'), label)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(self.read('#model-selector-model-button', 'getAttribute("aria-label")'), model)
        self.assertEqual(self.server.chats['existing-chat']['chat']['params'], chat_params)
        if reference and reference.get('context_id'):
            self.assert_reference_preserved(reference)
        else:
            self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference()'), reference)
        self.assertEqual(self.server.completions, [])
        return before

    def screenshot(self, label, *, wait_for_fonts=True):
        directory = super().screenshot(label, wait_for_fonts=wait_for_fonts)
        observed = self.browser.evaluate("""(()=>{
          const panel=document.querySelector('#ees-work-panel');
          const author=document.querySelector('#ees-work-designer');
          const active=document.activeElement;
          const region=e=>e?{text:e.innerText,html:e.outerHTML}:null;
          const box=e=>{if(!e)return null;const r=e.getBoundingClientRect(),c=getComputedStyle(e);return {x:r.x,y:r.y,bottom:r.bottom,width:r.width,height:r.height,display:c.display,visibility:c.visibility,position:c.position,flex:c.flex,font:c.font,maskImage:c.maskImage,background:c.backgroundColor};};
          const geometry=selector=>{const e=document.querySelector(selector);if(!e)return null;const r=e.getBoundingClientRect(),c=getComputedStyle(e);return {x:r.x,y:r.y,width:r.width,height:r.height,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,clientHeight:e.clientHeight,scrollHeight:e.scrollHeight,scrollTop:e.scrollTop,overflowY:c.overflowY,background:c.backgroundColor,outline:c.outline,focusVisible:e.matches(':focus-visible'),borderWidth:c.borderWidth,borderRadius:c.borderRadius,minHeight:c.minHeight};};
          return {scope:'built Native UI; synthetic session and data',
            path:location.pathname,ready:document.readyState,fonts:document.fonts.status,
            nativeMount:{chatPane:!!document.querySelector('#chat-container #chat-pane'),sidebarSearch:!!document.querySelector('#sidebar-search-button'),sidebarToggle:!!document.querySelector('#sidebar-toggle-button')},
            sourceShell:{root:box(document.querySelector('[data-ees-source-shell]')),sidebar:box(document.querySelector('[data-ees-source-sidebar]')),panelSlot:box(document.querySelector('[data-ees-source-slot]')),persistentChat:window.__eesNativeDraftV1?.persistent===true,startupGate:document.documentElement.dataset.eesStartup||null},
            viewport:[innerWidth,innerHeight],active:{tag:active?.tagName,id:active?.id,name:active?.name},
            panel:region(panel),authoring:region(author),
            nativeTheme:{modalSurface:box(document.querySelector('.modal[role=dialog]>div')),selectedSettingsTab:box(document.querySelector('#settings-tabs-container [aria-selected=true]')),valves:box(document.querySelector('.chat-control-valves')),valveInput:box(document.querySelector('.chat-control-valves input'))},
            nativeMenu:{draftReady:window.__eesNativeDraftV1?.ready?.(),settingsTabs:box(document.querySelector('#settings-tabs-container')),returnBar:box(document.querySelector('#ees-work-native-return')),workspace:box(document.querySelector('#workspace-container')),workspaceNav:box(document.querySelector('#workspace-container')?.previousElementSibling),workspaceTabs:[...document.querySelectorAll('#workspace-container')][0]?.previousElementSibling?[...document.querySelector('#workspace-container').previousElementSibling.querySelectorAll('a')].map(e=>({href:e.getAttribute('href'),box:box(e)})):[],search:region(document.querySelector('#workspace-container')),items:[...document.querySelectorAll('.ew-nav-button')].map(e=>({text:e.textContent,button:box(e),children:[...e.children].map(child=>({tag:child.tagName,text:child.textContent,layout:box(child)}))})),captions:[...document.querySelectorAll('.ew-nav-group-title')].map(e=>({text:e.textContent,layout:box(e)}))},
            layout:{panel:geometry('#ees-work-panel'),scroll:geometry('.ew-author-scroll'),radio:geometry('[name=procedure_template]:checked'),selected:geometry('.ew-procedure-card[data-selected=true]'),unselected:geometry('.ew-procedure-card[data-selected=false]'),name:geometry('#ew-procedure-name'),footer:geometry('#ees-work-designer>footer'),back:geometry('.ew-author-procedure-start .ew-author-back'),questionGroup:geometry('.ew-procedure-questions'),firstQuestion:geometry('.ew-procedure-questions>button'),cardGaps:[...document.querySelectorAll('.ew-procedure-choices>.ew-procedure-card')].filter(e=>e.previousElementSibling).map(e=>e.getBoundingClientRect().top-e.previousElementSibling.getBoundingClientRect().bottom)},
            nativeDraft:window.__eesNativeDraftV1?.read?.(),
            nativeInput:region(document.querySelector('#chat-input'))};
        })()""")
        observed['native_search'] = getattr(self, 'native_search_evidence', None)
        (directory / (label + '-dom.json')).write_text(
            json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return directory

    def test_native_menu_skills_returns_to_unsaved_procedure_tool_and_start_with_nonimage_draft(self):
        # With one available model the approved source UI omits the selector.
        # Supply two synthetic choices to verify the real Native selected model
        # before and after navigation, without a test-only product state hook.
        second_model = deepcopy(MODELS[0])
        second_model.update(id='fixture-other-model', name='Other Fixture AI')
        second_model['info'].update(id='fixture-other-model', name='Other Fixture AI')
        self.server.models = [deepcopy(MODELS[0]), second_model]
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#model-selector-model-button') && document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.native_menu_fixture()
        self.tool_connections()
        self.wait('window.__eesNativeDraftV1?.ready()')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        draft.update(prompt='메뉴 왕복 중 보존할 개인 질문',
                     files=[{'type': 'file', 'id': 'fixture-file', 'name': 'menu-draft.txt',
                             'url': '/api/v1/files/fixture-file/content', 'status': 'processed', 'size': 7}],
                     selectedToolIds=['fixture-selected-tool'], selectedSkillIds=['fixture-selected-skill'],
                     selectedFilterIds=['fixture-selected-filter'])
        self.assertTrue(self.browser.evaluate('window.__eesNativeDraftV1.restore(' + json.dumps(json.dumps(draft, ensure_ascii=False)) + ')'))
        self.wait("document.querySelector('#chat-input')?.textContent.includes('메뉴 왕복 중 보존할 개인 질문')")
        full_draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        for field in ('files', 'selectedToolIds', 'selectedSkillIds', 'selectedFilterIds'):
            self.assertEqual(full_draft[field], draft[field])
        original_chat = deepcopy(self.server.chats['existing-chat'])

        created = self.command('create_workflow', system_id='EMS', name='메뉴 왕복 절차')
        workflow_id = created['workflow_id']
        self.refresh()
        self.click('[data-action=mode][data-mode=author]')
        self.wait('document.querySelector(' + json.dumps('[data-author-action=open][data-id="' + workflow_id + '"]') + ')')
        self.click('[data-author-action=open][data-id="' + workflow_id + '"]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('[data-author-action=tab][data-tab=content]')
        self.wait("document.querySelector('[data-author-action=add_stage]')")
        self.add_stage_ui('아직 저장하지 않은 메뉴 단계')
        self.add_job_ui('아직 저장하지 않은 메뉴 작업')
        self.fill('#ew-author-node [name=instructions]', '복귀 후에도 유지할 미저장 설명')
        saved = self.state(workflow_id=workflow_id)['workflow']
        self.screenshot('menu-c18-admin-workspace')
        self.assertEqual(self.skills_roundtrip('procedure'), full_draft)
        self.assertEqual(self.read('#ew-author-node [name=name]', 'value'), '아직 저장하지 않은 메뉴 작업')
        self.assertEqual(self.read('#ew-author-node [name=instructions]', 'value'), '복귀 후에도 유지할 미저장 설명')
        self.assertEqual(self.state(workflow_id=workflow_id)['workflow'], saved)
        self.screenshot('menu-c18-procedure-returned')

        self.click('[data-action=tools]')
        self.wait("document.querySelector('[data-author-action=tool_create]')")
        self.click('[data-author-action=tool_create]')
        self.click('[data-author-action=tool_example][data-id=jira-query]')
        self.fill('#ew-author-tool [name=name]', '미저장 개인 도구 이름')
        self.fill('#ew-author-tool [name=description]', '배포 전에 필요한 승인 상태를 확인')
        self.assertEqual(self.skills_roundtrip('tool'), full_draft)
        self.assertEqual(self.read('#ew-author-tool [name=name]', 'value'), '미저장 개인 도구 이름')
        self.assertEqual(self.read('#ew-author-tool [name=description]', 'value'), '배포 전에 필요한 승인 상태를 확인')
        self.assertEqual(self.operations()['tools'], [])
        self.screenshot('menu-c18-tool-returned')

        self.click('[data-action=procedures]')
        self.click('[data-author-action=create]')
        self.fill('#ees-work-dialog [name=name]', '왕복 중인 새 절차 시작 이름')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        self.assertEqual(self.skills_roundtrip('procedure-start'), full_draft)
        self.click('[data-author-action=create]')
        self.assertEqual(self.read('#ees-work-dialog [name=name]', 'value'), '왕복 중인 새 절차 시작 이름')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        self.assertEqual(len(self.state()['workflows']), 4)
        self.assertEqual(self.server.chats['existing-chat'], original_chat)
        self.assertEqual(self.server.completions, [])
        directory = self.screenshot('menu-c18-procedure-start-returned')
        (directory / 'menu-c18-draft-preservation.json').write_text(json.dumps({
            'scope': 'actual compiled Native routes/composer; text/nonimage Native snapshot; synthetic session, capability response, attachment and selected asset IDs; existing model/params stay Native-owned; not a Native ACL test',
            'before': full_draft, 'after': self.browser.evaluate('window.__eesNativeDraftV1.read()'),
            'chat_models': self.server.chats['existing-chat']['chat']['models'],
            'chat_params': self.server.chats['existing-chat']['chat']['params'],
            'completion_count': len(self.server.completions), 'workflow_revision': saved['revision'],
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_native_menu_admin_redirect_opens_original_settings_and_returns_without_saving(self):
        self.native_menu_fixture()
        self.fill('#chat-input', '관리자 화면 왕복 전에 작성한 개인 질문')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=create]')
        self.fill('#ees-work-dialog [name=name]', '관리자 설정을 다녀올 새 절차')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        initial_workflows = self.state()['workflows']
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        self.click('[data-action=native_open][data-native-id=admin]')
        self.wait("document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-admin-general][aria-selected=true]') && document.querySelector('[role=dialog][aria-modal=true] input[type=text][placeholder*=\"localhost:3000\"]')")
        self.assertEqual(self.browser.evaluate('location.pathname + location.search'), '/c/existing-chat')
        self.wait("document.querySelector('#ees-work-entry')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        original_url = self.read('[role=dialog] input[type=text][placeholder*="localhost:3000"]', 'value')
        self.assertEqual(original_url, 'https://fixture.invalid')
        self.fill('[role=dialog] input[type=text][placeholder*="localhost:3000"]', 'https://unsaved-fixture.invalid')
        self.assertEqual(self.read('[role=dialog] input[type=text][placeholder*="localhost:3000"]', 'value'), 'https://unsaved-fixture.invalid')
        self.screenshot('menu-c18-native-admin-unsaved')
        self.click('#settings-tabs-container > button')
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('[data-author-action=create]') && !document.querySelector('#settings-tabs-container') && !document.querySelector('#ees-work-native-return')")
        self.click('[data-author-action=create]')
        self.assertEqual(self.read('#ees-work-dialog [name=name]', 'value'), '관리자 설정을 다녀올 새 절차')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        # Opening the original modal now leaves the source route and Chat in
        # place. Its reference remains the same, rather than a new route token.
        self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference()'), reference)
        self.screenshot('menu-c18-native-admin-returned')

        self.click('[data-action=native_open][data-native-id=admin]')
        self.wait("document.querySelector('[role=dialog] input[type=text][placeholder*=\"localhost:3000\"]')?.value === 'https://fixture.invalid'")
        self.assertFalse(any(method != 'GET' and path in {
            '/api/v1/auths/admin/config', '/api/v1/auths/admin/config/update',
            '/api/v1/configs/banners', '/api/events/webhooks'} for method, path in self.server.requests))
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.state()['workflows'], initial_workflows)
        self.click('#settings-tabs-container [role=tab][aria-controls=tab-general]')
        self.wait("document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-general][aria-selected=true]')")
        self.assertEqual(self.browser.evaluate('location.pathname'), '/c/existing-chat')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.screenshot('menu-c18-admin-to-personal-settings')
        self.click('#settings-tabs-container > button')
        self.wait("location.pathname === '/c/existing-chat' && !document.querySelector('#settings-tabs-container')")

    def test_native_admin_dialog_contains_keyboard_focus(self):
        self.native_menu_fixture()
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=native_open][data-native-id=admin]')
        self.wait("document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-admin-general][aria-selected=true]') && document.querySelector('[role=dialog][aria-modal=true] input[type=text][placeholder*=\"localhost:3000\"]') && document.querySelector('#ees-work-entry [data-action=procedures]')")
        observe = """(()=>{
          const modal=document.querySelector('[role=dialog][aria-modal=true]:has(#settings-tabs-container)');
          const controls=[...modal.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].filter(e=>e.tabIndex>=0&&!e.matches(':disabled')&&!e.closest('[inert]')&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          const describe=e=>({tag:e?.tagName,id:e?.id||'',name:e?.name||'',role:e?.getAttribute('role'),label:e?.getAttribute('aria-label')||'',text:e?.textContent?.trim().slice(0,80)||''});
          const active=document.activeElement,menu=document.querySelector('#ees-work-entry');
          return {path:location.pathname,dialog:!!modal,contained:modal.contains(active),menuFocused:menu.contains(active),menuInert:!!menu.closest('[inert]'),active:describe(active),index:controls.indexOf(active),controls:controls.map(describe)};
        })()"""
        # Establish focus with a real pointer, then use trusted browser Tab
        # events. DOM dispatchEvent/focus() cannot prove Native's focus trap.
        self.click('[role=dialog] input[type=text][placeholder*="localhost:3000"]')
        initial = self.browser.evaluate(observe)
        self.assertTrue(initial['contained'])
        self.assertGreater(len(initial['controls']), 2)
        sequence = []
        for direction, modifiers in (('Tab', 0), ('Shift+Tab', 8)):
            for index in range(len(initial['controls']) * 2 + 4):
                self.key('Tab', 9, modifiers)
                record = self.browser.evaluate(observe)
                record.pop('controls')
                record.update(direction=direction,step=index+1)
                sequence.append(record)
        menu_pointer = self.browser.evaluate("""(()=>{const e=document.querySelector('#ees-work-entry [data-action=procedures]'),r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);return {point:{x,y},reachable:e.contains(hit),hit:{tag:hit?.tagName,id:hit?.id,classes:hit?.className,role:hit?.getAttribute('role')},menuInert:!!e.closest('[inert]')};})()""")
        directory = self.screenshot('menu-c18-admin-keyboard-focus')
        (directory / 'menu-c18-admin-keyboard-focus.json').write_text(json.dumps({
            'scope': 'actual compiled Open WebUI 0.11.3 modal and trusted Chrome CDP keyboard/pointer; temporary workflow SQLite and synthetic Native session/capability responses; not real company authentication or ACL verification',
            'initial': initial, 'sequence': sequence, 'menu_pointer': menu_pointer,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(all(item['dialog'] and item['contained'] and not item['menuFocused']
                            for item in sequence), sequence)
        for direction in ('Tab', 'Shift+Tab'):
            visited = [item['index'] for item in sequence if item['direction'] == direction]
            self.assertIn(0, visited)
            self.assertIn(len(initial['controls']) - 1, visited)
            self.assertLess(len(set(visited)), len(visited), 'Expected a complete focus cycle')
            boundary = (len(initial['controls']) - 1, 0) if direction == 'Tab' else (0, len(initial['controls']) - 1)
            self.assertIn(boundary, list(zip(visited, visited[1:])))

    def test_native_menu_image_attachment_blocks_departure_without_losing_image_or_prompt(self):
        # Keep the historical test ID in the audit. Phase 2-1 replaces the old
        # departure block with a persistent Native Chat that preserves images.
        self.native_menu_fixture()
        self.fill('#chat-input', '이미지와 함께 보존할 개인 질문')
        # A real PNG goes through the unchanged Native input-file handler;
        # with real uploaded PNG metadata, this renders Native's image component.
        sample = Path(self.temporary.name) / 'menu-preserved-image.png'
        sample.write_bytes(self.server.wheel.read('open_webui/frontend/static/user.png'))
        self.browser.call('DOM.enable')
        document = self.browser.call('DOM.getDocument')['root']['nodeId']
        upload = self.browser.call('DOM.querySelector', {'nodeId': document, 'selector': '#chat-container input[type=file][multiple]'})['nodeId']
        self.assertGreater(upload, 0)
        self.browser.call('DOM.setFileInputFiles', {'nodeId': upload, 'files': [str(sample)]})
        image_selector = '#message-input-container [data-cy=image]'
        self.wait('document.querySelector(' + json.dumps(image_selector) + ')?.complete')
        self.assertGreater(self.read(image_selector, 'naturalWidth'), 0)
        image = self.read(image_selector, 'src')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertEqual(before['files'][0]['content_type'], 'image/png')
        self.assertEqual(self.server.uploaded_file[1], 'image/png')
        self.assertTrue(self.server.uploaded_file[0].startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(before['files'][0]['file']['meta']['size'], len(self.server.uploaded_file[0]))
        self.assertTrue(self.browser.evaluate('window.__eesNativeDraftV1.persistent === true'))
        self.browser.evaluate("window.__eesPreservedComposer=document.querySelector('#chat-input');window.__eesPreservedImage=document.querySelector('#message-input-container [data-cy=image]');true")
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]')")
        self.assert_source_shell()
        self.assert_work_panel_not_displayed()
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-native-navigation-error][role=alert]')"))
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesPreservedComposer && document.querySelector('#message-input-container [data-cy=image]')===window.__eesPreservedImage"))
        self.assertEqual(self.read('#chat-input', 'textContent'), before['prompt'])
        self.search_native_skills('#workspace-container input[aria-label]', 'preserved-image-roundtrip')
        self.click('#ees-work-entry [data-action=procedures]')
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-designer')")
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesPreservedComposer && document.querySelector('#message-input-container [data-cy=image]')===window.__eesPreservedImage"))
        self.assertEqual(self.read(image_selector, 'src'), image)
        self.assertGreater(self.read(image_selector, 'naturalWidth'), 0)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assertEqual(self.server.completions, [])
        self.screenshot('menu-phase2-native-image-preserved-roundtrip')

    def test_native_personal_settings_keep_original_tabs_and_close_controls(self):
        self.native_menu_fixture()
        # Observe the head gate from document creation. A later timeout/release
        # must not mask hiding Native's modal before its focus trap activates.
        observer = self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': """
          window.__eesSettingsGateChanges=0;
          new MutationObserver(records=>{window.__eesSettingsGateChanges+=records.length;})
            .observe(document,{subtree:true,attributes:true,attributeFilter:['data-ees-startup']});
        """})['identifier']
        self.addCleanup(lambda: self.browser.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier': observer}))
        self.navigate('/?settings=general')
        self.wait("document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-general][aria-selected=true]')")
        self.assertEqual(self.browser.evaluate('window.__eesSettingsGateChanges'), 0,
                         'Native settings hard loads must never arm the chat startup gate')
        # Native can open its modal before the authenticated EES workspace
        # finishes mounting. Its portaled Native form retains the approved
        # shared EES typography without moving it into the source shell.
        self.wait("document.querySelector('[data-ees-source-shell] #ees-work-entry') && document.querySelector('#ees-work-panel')")
        self.assert_source_shell()
        modal = '[role=dialog][aria-modal=true]:has(#settings-tabs-container)'
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assertGreater(self.browser.evaluate("document.querySelector('#settings-tabs-container > button').getBoundingClientRect().height"), 0)
        typography = self.browser.evaluate("""(()=>{const tabs=document.querySelector('#settings-tabs-container'),modal=tabs.closest('[role=dialog][aria-modal=true]'),tab=tabs.querySelector('[role=tab][aria-selected=true]');return {modal:getComputedStyle(modal.firstElementChild).fontFamily,tab:getComputedStyle(tab).fontFamily,native:getComputedStyle(document.body).fontFamily,insideShell:!!modal.closest('[data-ees-source-shell]'),tabCount:tabs.querySelectorAll('[role=tab]').length};})()""")
        self.assertFalse(typography['insideShell'])
        self.assertIn('EES Inter', typography['modal'])
        self.assertIn('EES Inter', typography['tab'])
        self.assertGreater(typography['tabCount'], 1)
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(modal) + ')).visibility'), 'visible')
        self.click('#settings-tabs-container [role=tab][aria-selected=true]')
        for modifiers in (0, 8):
            self.key('Tab', 9, modifiers)
            self.assertTrue(self.browser.evaluate('document.querySelector(' + json.dumps(modal) + ').contains(document.activeElement)'))
        self.screenshot('menu-c18-native-personal-settings')
        self.click('#settings-tabs-container > button')
        self.wait('!document.querySelector(' + json.dumps(modal) + ') && window.__eesNativeDraftV1?.ready()')
        self.assertEqual(self.server.completions, [])

    def test_native_menu_upload_in_flight_finishes_in_persistent_composer(self):
        self.native_menu_fixture()
        self.fill('#chat-input', '업로드 중 이동해도 보존할 개인 질문')
        original_post = NativeUIHandler.do_POST
        upload_started, upload_hold = threading.Event(), threading.Event()
        self.addCleanup(upload_hold.set)

        def held_upload(handler):
            if urlsplit(handler.path).path == '/api/v1/files/':
                upload_started.set()
                if not upload_hold.wait(timeout=8):
                    raise AssertionError('The browser did not release the held upload')
            return original_post(handler)

        provider = patch.object(NativeUIHandler, 'do_POST', held_upload)
        provider.start()
        self.addCleanup(provider.stop)
        sample = Path(self.temporary.name) / 'menu-upload-in-flight.png'
        sample.write_bytes(self.server.wheel.read('open_webui/frontend/static/user.png'))
        self.browser.call('DOM.enable')
        document = self.browser.call('DOM.getDocument')['root']['nodeId']
        upload = self.browser.call('DOM.querySelector', {'nodeId': document,
            'selector': '#chat-container input[type=file][multiple]'})['nodeId']
        self.assertGreater(upload, 0)
        self.browser.call('DOM.setFileInputFiles', {'nodeId': upload, 'files': [str(sample)]})
        self.assertTrue(upload_started.wait(timeout=2), 'Native upload request was not received')
        self.wait('window.__eesNativeDraftV1?.attachmentState().uploading')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertEqual(len(before['files']), 1)
        self.assertEqual(before['files'][0]['status'], 'uploading')
        self.browser.evaluate("window.__eesUploadingComposer=document.querySelector('#chat-input');true")
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]')")
        self.assert_source_shell()
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesUploadingComposer"))
        self.assertEqual(self.read('#chat-input', 'textContent'), before['prompt'])
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-native-navigation-error][role=alert]')"))
        upload_hold.set()
        image_selector = '#message-input-container [data-cy=image]'
        self.wait('document.querySelector(' + json.dumps(image_selector) + ')?.naturalWidth > 0')
        self.click('#ees-work-entry [data-action=procedures]')
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-designer')")
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesUploadingComposer"))
        after = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertEqual({key: value for key, value in after.items() if key != 'files'},
                         {key: value for key, value in before.items() if key != 'files'})
        self.assertEqual(len(after['files']), 1)
        self.assertEqual(after['files'][0]['itemId'], before['files'][0]['itemId'])
        self.assertNotEqual(after['files'][0]['status'], 'uploading')
        self.assertEqual(after['files'][0]['id'], 'fixture-file')
        self.assertEqual(after['files'][0]['content_type'], 'image/png')
        self.assertEqual(after['files'][0]['file']['meta']['size'], len(sample.read_bytes()))
        self.assertEqual(self.server.uploaded_file, (sample.read_bytes(), 'image/png'))
        self.assertGreater(self.read(image_selector, 'naturalWidth'), 0)
        self.assertEqual(self.server.completions, [])
        self.screenshot('menu-phase2-upload-in-flight-preserved')

    def test_native_folder_uses_one_chat_and_preserves_draft_through_asset_navigation(self):
        # Exercise the real compiled folder row, route and Native Chat. Only
        # folder metadata and model transport are synthetic; no source overlay.
        self.native_menu_fixture()
        original_get = NativeUIHandler.do_GET
        folder = {'id': 'source-folder', 'user_id': self.server.user['id'],
                  'name': '합성 보존 폴더', 'parent_id': None, 'is_expanded': True,
                  'data': {'model_ids': ['fixture-model']}, 'meta': {},
                  'created_at': 1, 'updated_at': 1}

        def folder_get(handler):
            path = urlsplit(handler.path).path
            responses = {
                '/api/v1/folders/': [folder],
                '/api/v1/folders/source-folder': folder,
                '/api/v1/folders/source-folder/shared/chats': {'chats': [], 'has_more': False},
            }
            if path in responses:
                handler.server.requests.append(('GET', path))
                return handler.send_content(responses[path])
            if path == '/folders/source-folder':
                handler.server.requests.append(('GET', path))
                return handler.send_content(handler.server.read_frontend('open_webui/frontend/index.html'), 'text/html')
            return original_get(handler)

        provider = patch.object(NativeUIHandler, 'do_GET', folder_get)
        provider.start()
        self.addCleanup(provider.stop)
        self.browser.evaluate("localStorage.setItem('sidebar-folders-folder-state','true');true")
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-entry [data-action=chats]')")
        self.open_sidebar()
        self.click('#ees-work-entry [data-action=chats]')
        folder_button = '#folder-source-folder-button'
        self.wait('document.querySelector(' + json.dumps(folder_button) + ')?.checkVisibility({visibilityProperty:true})')
        self.browser.evaluate("window.__eesFolderChatRoot=document.querySelector('#chat-container');window.__eesFolderDraftBridge=window.__eesNativeDraftV1;true")
        self.click(folder_button)
        self.wait("location.pathname === '/folders/source-folder' && window.__eesNativeDraftV1?.ready()")
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-container').length"), 1)
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-input').length"), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-container')===window.__eesFolderChatRoot && window.__eesNativeDraftV1===window.__eesFolderDraftBridge"))
        self.fill('#chat-input', '폴더에서 생성할 개인 합성 대화')
        sample = Path(self.temporary.name) / 'folder-preserved-image.png'
        sample.write_bytes(self.server.wheel.read('open_webui/frontend/static/user.png'))
        self.browser.call('DOM.enable')
        document = self.browser.call('DOM.getDocument')['root']['nodeId']
        upload = self.browser.call('DOM.querySelector', {'nodeId': document,
            'selector': '#chat-container input[type=file][multiple]'})['nodeId']
        self.assertGreater(upload, 0)
        self.browser.call('DOM.setFileInputFiles', {'nodeId': upload, 'files': [str(sample)]})
        image_selector = '#message-input-container [data-cy=image]'
        self.wait('document.querySelector(' + json.dumps(image_selector) + ')?.naturalWidth > 0')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.browser.evaluate("window.__eesFolderImage=document.querySelector('#message-input-container [data-cy=image]');true")
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]')")
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-container').length"), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-container')===window.__eesFolderChatRoot && window.__eesNativeDraftV1===window.__eesFolderDraftBridge"))
        self.click('#ees-work-entry [data-action=procedures]')
        self.wait("location.pathname === '/folders/source-folder' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-designer')")
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-container').length"), 1)
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-input').length"), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-container')===window.__eesFolderChatRoot && window.__eesNativeDraftV1===window.__eesFolderDraftBridge && document.querySelector('#message-input-container [data-cy=image]')===window.__eesFolderImage"))
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(self.server.completions, [])
        self.screenshot('menu-phase2-folder-native-roundtrip')
        self.click('#send-message-button')
        self.wait("location.pathname.startsWith('/c/') && document.querySelector('#messages-container')?.textContent.includes('실제 대화 입력이 전달되었습니다.')")
        self.assertEqual(len(self.server.completions), 1)
        self.assertEqual(self.server.completions[0]['model'], 'fixture-model')
        self.assertEqual(self.server.completions[0]['folder_id'], folder['id'])
        self.assertEqual(self.server.completions[0]['user_message']['content'], before['prompt'])
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#chat-container').length"), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-container')===window.__eesFolderChatRoot && window.__eesNativeDraftV1===window.__eesFolderDraftBridge"))
        self.assertEqual(folder['name'], '합성 보존 폴더')
        self.screenshot('menu-phase2-folder-new-chat-single-instance')

    def test_native_initial_changelog_keeps_focus_while_chat_startup_is_hidden(self):
        # Historical test ID retained: the source shell now makes the first
        # frame itself correct, so the former whole-body startup gate is absent.
        # Actual Native ChangelogModal selection: an administrator who has not
        # seen this version. Only HTTP settings/release-note data are synthetic.
        original_get = NativeUIHandler.do_GET

        def fixture_get(handler):
            path = urlsplit(handler.path).path
            if path == '/api/v1/users/user/settings':
                handler.server.requests.append(('GET', path))
                return handler.send_content({'ui': {'models': ['fixture-model'],
                    'showChangelog': True, 'version': '0.11.2', 'autoFollowUps': False}})
            if path == '/api/changelog':
                handler.server.requests.append(('GET', path))
                return handler.send_content({'0.11.3': {'date': '2026-10-13',
                    'fixed': [{'raw': '<p>Synthetic release-note fixture</p>'}]}})
            return original_get(handler)

        patched = patch.object(NativeUIHandler, 'do_GET', fixture_get)
        patched.start()
        self.addCleanup(patched.stop)
        self.server.delay_next_workspace = True
        self.server.workspace_response_started.clear()
        self.server.workspace_response_hold.clear()
        observer = self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': """
          window.__eesChangelogGateChanges=0;
          new MutationObserver(records=>{window.__eesChangelogGateChanges+=records.length;})
            .observe(document,{subtree:true,attributes:true,attributeFilter:['data-ees-startup']});
        """})['identifier']
        self.addCleanup(lambda: self.browser.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier': observer}))
        self.navigate('/c/existing-chat')
        modal = '[role=dialog][aria-modal=true]:not(:has(#settings-tabs-container))'
        self.wait("document.querySelector('[data-ees-source-shell]') && document.querySelector(" + json.dumps(modal) + ')')
        self.assertTrue(self.server.workspace_response_started.wait(timeout=2), 'Held workspace read was not reached')
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.body).visibility'), 'visible')
        self.assertFalse(self.browser.evaluate('Boolean(document.documentElement.dataset.eesStartup)'))
        self.assertEqual(self.browser.evaluate('window.__eesChangelogGateChanges'), 0)
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(modal) + ')).visibility'), 'visible')
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(modal + ' button') + ')).visibility'), 'visible')
        self.wait('document.querySelector(' + json.dumps(modal) + ')?.textContent.includes("Synthetic release-note fixture")')
        self.assertIn('Synthetic release-note fixture', self.text(modal))
        # A temporary, non-interactive CSS probe inside the actual Native modal
        # verifies that the EES shell theme respects a child's own hidden state.
        self.assertEqual(self.browser.evaluate("""(()=>{
          const modal=document.querySelector('[role=dialog][aria-modal=true]');
          const probe=document.createElement('span');probe.style.visibility='hidden';
          modal.append(probe);const visibility=getComputedStyle(probe).visibility;probe.remove();
          return visibility;
        })()"""), 'hidden')
        self.wait('document.querySelector(' + json.dumps(modal) + ')?.contains(document.activeElement)')
        for modifiers in (0, 8):
            self.key('Tab', 9, modifiers)
            self.assertTrue(self.browser.evaluate('document.querySelector(' + json.dumps(modal) + ').contains(document.activeElement)'))
        self.assertFalse(self.browser.evaluate('Boolean(document.documentElement.dataset.eesStartup)'))
        self.screenshot('startup-native-changelog-source-shell')
        self.click(modal + ' button')
        self.wait('!document.querySelector(' + json.dumps(modal) + ')')
        self.assertEqual(self.browser.evaluate('window.__eesChangelogGateChanges'), 0)
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.body).visibility'), 'visible')
        self.server.workspace_response_hold.set()
        self.wait("!document.documentElement.dataset.eesStartup && document.querySelector('#ees-work-entry') && document.querySelector('#ees-work-panel') && window.__eesNativeDraftV1?.ready()")
        self.assertEqual(self.server.completions, [])

    def test_native_personal_key_uses_original_valves_controls_and_theme(self):
        # Original compiled Native UserValves component and published API paths;
        # a synthetic tool/schema/value only, not real credentials or ACL proof.
        original_get = NativeUIHandler.do_GET

        def fixture_get(handler):
            path = urlsplit(handler.path).path
            responses = {
                '/api/v1/tools/': [{'id': 'fixture-personal-key', 'name': '합성 개인 키 도구',
                                   'has_user_valves': True, 'specs': []}],
                '/api/v1/tools/id/fixture-personal-key/valves/user': {'API_KEY': 'synthetic-key-only'},
                '/api/v1/tools/id/fixture-personal-key/valves/user/spec': {
                    'type': 'object', 'properties': {'API_KEY': {'title': '합성 개인 키',
                        'description': '실제 키가 아닌 화면 검증 값입니다.', 'type': 'string',
                        'input': {'type': 'password'}}}, 'required': ['API_KEY']},
            }
            if path in responses:
                handler.server.requests.append(('GET', path))
                return handler.send_content(responses[path])
            return original_get(handler)

        provider = patch.object(NativeUIHandler, 'do_GET', fixture_get)
        provider.start()
        self.addCleanup(provider.stop)
        self.browser.evaluate("localStorage.setItem('chatControls.valves','true')")
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('button[aria-label=Controls]')")
        self.click('button[aria-label=Controls]')
        self.wait("document.querySelector('select:has(option[value=fixture-personal-key])')")
        self.choose('select:has(option[value=fixture-personal-key])', 'fixture-personal-key')
        self.wait("document.querySelector('.chat-control-valves #valve-API_KEY')")
        key = '.chat-control-valves #valve-API_KEY'
        # Pinned SensitiveInput keeps type=text and masks with .password.
        # Verify the actual masking and its original show/hide control.
        self.assertEqual(self.read(key, 'type'), 'text')
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(key) + ')).webkitTextSecurity'), 'disc')
        self.assertEqual(self.read(key, 'value'), 'synthetic-key-only')
        self.assertTrue(self.read(key, 'required'))
        styles = self.browser.evaluate("""(()=>{const e=document.querySelector('.chat-control-valves'),input=e.querySelector('input');return {font:getComputedStyle(e).fontFamily,inputFont:getComputedStyle(input).fontFamily,background:getComputedStyle(e).backgroundColor,inputBackground:getComputedStyle(input).backgroundColor};})()""")
        self.assertIn('EES Inter', styles['font'])
        self.assertIn('EES Inter', styles['inputFont'])
        self.assertEqual(styles['background'], 'rgb(255, 255, 255)')
        self.assertEqual(styles['inputBackground'], 'rgb(255, 255, 255)')
        reveal = '.chat-control-valves button[aria-pressed]'
        self.click(reveal)
        self.assertEqual(self.read(reveal, 'getAttribute("aria-pressed")'), 'true')
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(key) + ')).webkitTextSecurity'), 'none')
        self.click(reveal)
        self.assertEqual(self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(key) + ')).webkitTextSecurity'), 'disc')
        self.screenshot('menu-c18-native-personal-key')
        self.assertFalse(any(method != 'GET' and '/valves/user' in path for method, path in self.server.requests))
        self.assertEqual(self.server.completions, [])

    def test_native_menu_missing_mount_and_direct_entry_keep_original_skills_search(self):
        self.native_menu_fixture()
        self.assert_source_shell()
        self.browser.evaluate("window.__eesPreservedSourceSidebar=document.querySelector('[data-ees-source-sidebar]');true")
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#ees-work-entry') && document.querySelector('#workspace-container input[aria-label]')")
        # Keep this historical ID: the source-owned search control may retain
        # Native's keyboard shortcut ID, but it must not be a DOM mount anchor.
        self.browser.evaluate("document.querySelector('#sidebar-search-button').id='fixture-unrecognized-sidebar-search';true")
        self.assert_source_shell()
        self.assertTrue(self.browser.evaluate("document.querySelector('[data-ees-source-sidebar]')===window.__eesPreservedSourceSidebar"))
        self.search_native_skills('#workspace-container input[aria-label]', 'missing-mount-search')
        self.assert_work_panel_not_displayed()
        self.screenshot('menu-phase2-native-without-dom-mount')

        # A fresh direct Native route has no EES departure ticket.
        self.navigate('/workspace/skills')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]') && document.querySelector('#ees-work-entry')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assert_work_panel_not_displayed()
        self.assert_source_shell()
        self.search_native_skills('#workspace-container input[aria-label]', 'direct-native-search')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assertEqual(self.server.completions, [])
        self.screenshot('menu-c18-direct-native-search')

        # All four asset kinds remain the compiled Native screens in 2-1.
        # A direct Native entry must not require a previous chat departure.
        self.open_sidebar()
        for target in ('models', 'knowledge', 'prompts', 'skills'):
            self.click('[data-action=native_open][data-native-id=' + target + ']')
            self.wait('location.pathname === ' + json.dumps('/workspace/' + target)
                      + ' && document.querySelector("#workspace-container input")'
                      + ' && document.querySelector("#ees-work-entry [data-action=native_open][data-native-id=' + target + '][aria-current=page]")')
            self.assert_work_panel_not_displayed()
            self.assert_source_shell()
        self.click('#ees-work-entry [data-action=procedures]')
        self.wait("location.pathname === '/' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-designer')")
        self.wait("document.querySelectorAll('[data-author-action=open]').length === 3")
        self.assertEqual(len(self.state()['workflows']), 3)
        self.assertEqual(self.state()['runs'], [])

    def test_native_shell_browser_back_preserves_draft_and_mobile_navigation(self):
        self.native_menu_fixture()
        self.fill('#chat-input', '뒤로 가기로 복원할 개인 질문')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=create]')
        self.fill('#ees-work-dialog [name=name]', '브라우저 뒤로 가기 중인 미저장 절차')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        self.click('[data-action=native_open][data-native-id=skills]')
        self.wait("location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input[aria-label]')")
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 600, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 600')
        # The source shell owns responsive navigation from its first render;
        # the original workspace tabs/sidebar are not mounted then covered.
        self.open_sidebar()
        self.assert_source_shell()
        self.wait("document.querySelector('[data-ees-source-sidebar]')?.getBoundingClientRect().x >= 0")
        self.assertFalse(self.browser.evaluate("[...(document.querySelector('#workspace-container').previousElementSibling?.querySelectorAll('a[href^=\"/workspace\"]') || [])].some(e=>e.getBoundingClientRect().height>0)"))
        self.assertFalse(self.browser.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.screenshot('menu-c18-native-mobile')
        self.browser.evaluate('history.back()')
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('[data-author-action=create]')")
        self.click('[data-author-action=create]')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.read('#ees-work-dialog [name=name]', 'value'), '브라우저 뒤로 가기 중인 미저장 절차')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-native-return')"))
        self.assertEqual(self.server.completions, [])
        self.screenshot('menu-c18-mobile-browser-back')

    def test_native_menu_uses_server_capabilities_for_admin_author_member_and_tools_only(self):
        self.native_menu_fixture()
        self.click('[data-action=mode][data-mode=author]')

        def menu_ids():
            return self.browser.evaluate("[...document.querySelectorAll('#ees-work-entry [data-action=native_open]')].map(e=>e.dataset.nativeId)")

        self.assertEqual(menu_ids(), ['skills', 'models', 'knowledge', 'prompts', 'admin'])
        self.assertNotIn('기능 연결', self.text('#ees-work-entry'))
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('.ew-nav-group-title')].map(e=>e.textContent)"),
                         ['업무 만들기', 'AI 설정', '관리자만'])
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=native_skills],[data-action=native_workspace]')"))
        self.screenshot('menu-c18-admin-menu')

        self.command('save_access', principal_kind='user', principal_id=self.server.user['id'],
                     system_id='EMS', factory_id='*', roles=['manager', 'participant'])
        self.server.user['role'] = 'user'
        self.menu_grants = {key: key in ('skills', 'prompts') for key in self.menu_grants}
        self.refresh()
        self.wait("!document.querySelector('[data-action=native_open][data-native-id=admin]')")
        self.assertEqual(menu_ids(), ['skills', 'prompts'])
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-action=tools]')"))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=workspace_admin]')"))
        self.screenshot('menu-c18-author-menu')

        self.server.user['role'] = 'admin'
        grant = next(item for item in self.state()['access'] if item['principal_id'] == self.server.user['id'])
        self.command('save_access', access_id=grant['id'], principal_kind='user', principal_id=self.server.user['id'],
                     system_id='EMS', factory_id='*', roles=['viewer'], expected_revision=grant['revision'])
        self.server.user['role'] = 'user'
        self.menu_grants = dict.fromkeys(self.menu_grants, False)
        self.refresh()
        self.wait("!document.querySelector('[data-action=mode][data-mode=author]')")
        self.assertEqual(menu_ids(), [])
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-designer')"))
        self.screenshot('menu-c18-member-work-only')

        self.menu_grants['tools'] = True
        self.refresh()
        self.wait("document.querySelector('[data-action=mode][data-mode=author]')")
        self.click('[data-action=mode][data-mode=author]')
        self.assertEqual(menu_ids(), [])
        self.assertIn('EES Workflow에서 열 수 있는 항목이 없습니다', self.text('#ees-work-entry'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=tools],[data-action=workspace_admin]')"))
        directory = self.screenshot('menu-c18-tools-only-menu')
        (directory / 'menu-c18-role-scope.json').write_text(json.dumps({
            'scope': 'server capability rendering with synthetic Native permission provider; actual Native account/API ACL is a separate gate',
            'cases': ['admin', 'EES manager with skills/prompts', 'viewer without Native workspace grants', 'Native tools-only non-admin'],
            'tools_only_capabilities': self.state()['capabilities'],
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_easy_tools_unconnected_example_and_live_read_confirmation_roundtrip(self):
        function = self.tool_connections()
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_create"]')
        self.assertIn('예시에서 시작', self.text('#ees-work-designer'))
        self.assertIn('아직 연결된 기능이 없습니다', self.text('#ees-work-designer'))
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-author-action=tool_example]').length"), 4)
        self.assertEqual(self.operations()['tools'], [])
        self.screenshot('easy-tools-empty-starter')
        self.click('[data-author-action="tool_example"][data-id="collection-queue"]')
        self.assertIn('필요한 기능이 아직 연결되지 않았습니다', self.text('#ees-work-designer'))
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        unconnected = self.operations()['tools'][0]
        self.assertEqual(unconnected['name'], '수집 대기열 조회')
        self.assertEqual(unconnected['kind'], 'read')
        self.assertEqual(unconnected['reference'], {})
        self.assertEqual(unconnected['state'], 'draft')
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        # Menu selection has its own debounced personal UI save. Its timing
        # must not change the required single business command for this draft.
        self.assertEqual([body['action'] for body in self.server.workspace_commands
                          if body['action'] not in ('save_ui', 'initialize_procedures')], ['tool_save'])
        self.screenshot('easy-tools-unconnected-saved')

        self.connected_tools.append(function('jira', '합성 Jira', 'jira_search_crs', 'read'))
        self.refresh()
        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.wait("document.querySelector('[data-author-action=tool_pick]')")
        self.assertEqual(self.read('[data-author-action="tool_example"][data-id="jira-query"] .ew-tool-connection', 'dataset.connected'), 'true')
        self.fill('#ew-tool-search', 'jira_search')
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('[data-author-action=tool_pick]')].map(e=>e.dataset.id)"), ['jira:jira_search_crs'])
        self.click('[data-author-action="tool_pick"][data-id="jira:jira_search_crs"]')
        self.click('#ew-author-tool [name=name]')
        self.key('a', 65, 2)
        self.browser.call('Input.insertText', {'text': '합성 CR 확인'})
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('#ew-author-tool [name=name]')"))
        self.assertIn('하는 일: 정보 읽기', self.text('#ees-work-designer'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ew-author-tool [name=kind],#ew-author-tool [name=timeout_seconds],#ew-author-tool [name=responsible_user_id]')"))
        self.assertFalse(self.read('.ew-tool-advanced', 'open'))
        self.assertEqual(self.read('#ew-author-tool [name=guide_url]', 'value'), '')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('[data-author-action=tool_review]')?.disabled === false")
        self.assertEqual(sum(body['action']=='tool_save' for body in self.server.workspace_commands), 2)
        self.screenshot('easy-tools-read-ready')
        self.click('[data-author-action="tool_review"]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('담당자 확인 대기')")
        saved = next(item for item in self.operations()['tools'] if item['name'] == '합성 CR 확인')
        self.assertEqual(saved['reference'], self.connected_tools[0]['reference'])
        self.assertEqual(saved['input_schema'], self.connected_tools[0]['schema'])
        self.assertEqual(saved['state'], 'review_requested')
        self.assertEqual(saved.get('guide_url', ''), '')
        self.assertNotEqual(saved['id'], unconnected['id'])
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.server.completions, [])

    def test_easy_request_choices_missing_output_and_legacy_time_values_roundtrip(self):
        function = self.tool_connections()
        primary = function('ops', '합성 EES', 'restart_service', 'request')
        self.connected_tools.extend([primary,
            function('ops', '합성 EES', 'restart_status', 'request'),
            function('unrelated', '다른 연결', 'other_status', 'request')])
        legacy = self.tool_command('tool_save', tool={
            'name': '기존 요청 도구', 'system_id': 'EMS', 'kind': 'request',
            'reference': primary['reference'], 'status_function': 'restart_status',
            'responsible_user_id': self.server.user['id'],
            'guide_url': 'https://example.invalid/guide',
            'output_schema': {'type': 'object', 'properties': {'kept': {'type': 'boolean'}}},
            'timeout_seconds': 47, 'completion_wait_seconds': 651})['tool']
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_open"][data-id="' + legacy['id'] + '"]')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[name=timeout_seconds],[name=completion_wait_seconds],[name=kind]')"))
        self.fill('#ew-author-tool [name=description]', '기존 값을 보존하는 설명 수정')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        saved = next(item for item in self.operations()['tools'] if item['id'] == legacy['id'])
        self.assertEqual(saved['timeout_seconds'], 47)
        self.assertEqual(saved['completion_wait_seconds'], 651)
        self.assertEqual(saved['output_schema'], legacy['output_schema'])
        self.assertEqual(saved['description'], '기존 값을 보존하는 설명 수정')

        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_pick"][data-id="ops:restart_service"]')
        self.assertIn('하는 일: EES에 작업 부탁', self.text('#ees-work-designer'))
        self.assertEqual(self.read('[name=status_function]', 'value'), 'restart_status')
        self.assertEqual(self.browser.evaluate("[...document.querySelector('[name=status_function]').options].map(e=>e.value)"), ['', 'restart_status'])
        self.assertIn(self.server.user['name'], self.text('#ees-work-designer'))
        self.assertFalse(self.read('.ew-tool-advanced', 'open'))
        self.assertEqual(self.read('[name=output_schema_json]', 'value'), '')
        self.fill('#ew-author-tool [name=guide_url]', 'https://example.invalid/request-guide')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        self.assertIn('결과 형식이 비어 있습니다', self.text('#ew-tool-submit-reason'))
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        created = next(item for item in self.operations()['tools'] if item['id'] != legacy['id'])
        self.assertEqual(created['status_function'], 'restart_status')
        self.assertEqual(created['responsible_user_id'], self.server.user['id'])
        self.assertNotIn('output_schema', created)
        self.screenshot('easy-tools-request-output-required')
        self.click('.ew-tool-advanced > summary')
        self.fill('#ew-author-tool [name=output_schema_json]', '{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('[data-author-action=tool_review]')?.disabled === false")
        self.screenshot('easy-tools-request-ready')
        self.click('[data-author-action="tool_review"]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('담당자 확인 대기')")
        submitted = next(item for item in self.operations()['tools'] if item['id'] == created['id'])
        self.assertEqual(submitted['state'], 'review_requested')
        self.assertEqual(submitted['status_reference'], self.connected_tools[1]['reference'])
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.server.completions, [])

    def test_help_keyboard_escape_and_questions_fill_native_composer_without_sending(self):
        # Historical ID retained: phase 2-2 sends only the question immediately
        # while preserving the independently authored Native composer draft.
        install_helper_status_fixture(self)
        def enter_button():
            # CDP needs Enter's character data to synthesize the native button
            # activation (keydown alone does not emit keypress/click).
            for kind in ('keyDown', 'keyUp'):
                self.browser.call('Input.dispatchKeyEvent', {
                    'type': kind, 'key': 'Enter', 'code': 'Enter',
                    'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13,
                    **({'text': '\r', 'unmodifiedText': '\r'} if kind == 'keyDown' else {}),
                })

        self.tool_connections()
        self.fill('#chat-input', '보존할 개인 대화 초안')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_example"][data-id="jira-query"]')
        self.click('#ew-author-tool [name=name]')
        for _ in range(12):
            self.key('Tab', 9)
            if self.browser.evaluate("document.activeElement?.matches('[data-author-action=help][data-id=read_tool]')"):
                break
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=help][data-id=read_tool]')"))
        enter_button()
        self.wait("document.querySelector('#ees-work-help')")
        self.assertEqual(self.read('#ees-work-help', 'getAttribute("role")'), 'dialog')
        source_term = next(item for item in self.state()['help']['terms'] if item['id'] == 'read_tool')
        self.assertEqual(self.text('#ees-work-help .ew-help-summary'), source_term['summary'])
        self.assertIn(source_term['example'], self.text('#ees-work-help .ew-help-example'))
        # C3 reads the help content first; the close control remains keyboard reachable.
        self.assertTrue(self.browser.evaluate("document.activeElement?.id === 'ees-work-help-body'"))
        self.screenshot('easy-tools-help-keyboard-open')
        # Normal workspace refresh replaces authoring controls. An open help
        # popover must keep its content and return focus to the current button.
        self.refresh()
        self.wait("document.querySelector('#ees-work-help')")
        self.assertEqual(self.text('#ees-work-help .ew-help-summary'), source_term['summary'])
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-help')")
        focus = self.browser.evaluate("(()=>{const e=document.activeElement,s=getComputedStyle(e);return {trigger:e.matches('[data-author-action=help][data-id=read_tool]'),visible:e.matches(':focus-visible'),style:s.outlineStyle,width:parseFloat(s.outlineWidth)};})()")
        self.assertTrue(focus['trigger'], focus)
        self.assertTrue(focus['visible'], focus)
        self.assertNotEqual(focus['style'], 'none', focus)
        self.assertGreater(focus['width'], 0, focus)
        enter_button()
        self.wait("document.querySelector('#ees-work-help')")
        self.click('#ees-work-help [data-help-ask]')
        self.wait("document.querySelector('#messages-container')?.textContent.includes('실제 대화 입력이 전달되었습니다.') && !window.__eesSourceShellV1.helpState().busy")
        after = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        directory = self.screenshot('easy-tools-help-native-chat')
        (directory / 'easy-tools-help-draft-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native composer; synthetic personal draft and transport',
            'before': before, 'after': after, 'completion_count': len(self.server.completions),
            'input': self.browser.evaluate("(()=>{const e=document.querySelector('#chat-input');return {html:e?.innerHTML,text:e?.textContent};})()"),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertEqual(after, before)
        self.assertEqual(len(self.server.completions), 1)
        help_message = self.server.completions[0]['user_message']
        self.assertEqual(help_message['meta']['ees_work_reference']['kind'], 'help')
        self.assertEqual(help_message['meta']['ees_work_reference']['term_id'], 'read_tool')
        for text in ('read_tool', '현재 화면:', '초안 이름:', before['prompt']):
            self.assertNotIn(text, help_message['content'])
        response = '#message-' + self.server.completions[0]['id']
        self.assertEqual(self.text(response + ' #response-message-model-name').strip(), 'Fixture AI')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-ees-helper-label]')"))
        self.assertEqual(self.operations()['tools'], [])
        self.click('.ew-tool-advanced > summary')
        self.click('[data-author-action="help"][data-id="output_schema"]')
        self.wait("document.querySelector('#ees-work-help')")
        self.refresh()
        self.wait("document.querySelector('.ew-tool-advanced')?.open && document.querySelector('#ees-work-help')")
        self.assertEqual(self.text('#ees-work-help-title'), '결과 형식')
        self.screenshot('easy-tools-help-advanced-refresh')
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-help')")
        advanced_focus = self.browser.evaluate("(()=>{const e=document.activeElement;return {trigger:e.matches('[data-author-action=help][data-id=output_schema]'),visible:e.getClientRects().length>0,open:document.querySelector('.ew-tool-advanced')?.open};})()")
        self.assertEqual(advanced_focus, {'trigger': True, 'visible': True, 'open': True})
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-help')"))
        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_question"][data-id="1"]')
        self.wait("document.querySelector('#messages-container')?.textContent.includes('Jira에서 CR 승인 상태를 확인하는 도구를 만들고 싶어') && !window.__eesSourceShellV1.helpState().busy")
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(len(self.server.completions), 2)
        self.assertEqual(self.server.completions[1]['user_message']['content'],
                         'Jira에서 CR 승인 상태를 확인하는 도구를 만들고 싶어')
        self.assertEqual(self.server.completions[1]['user_message']['meta']['ees_work_reference']['kind'], 'help')
        self.assertEqual(self.operations()['tools'], [])

    def test_initial_procedures_open_editable_and_save_as_creates_an_unpublished_draft(self):
        self.browser.evaluate("Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});true")
        self.fill('#chat-input', '새 절차 전에 작성한 개인 질문')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelectorAll('[data-author-action=open]').length === 3")
        self.assertNotIn('기본 제공 절차', self.text('#ees-work-designer'))
        record = next(item for item in self.state()['workflows'] if item['name'] == '신규 공장 횡전개')
        self.click('[data-author-action="open"][data-id="' + record['id'] + '"]')
        self.wait("document.querySelector('[data-author-action=save]')")
        self.click('.ew-author-tabs [data-author-action="tab"][data-tab="content"]')
        for stage in ('사전준비', 'AP·DB 인프라 준비', '시스템 설치', '시스템 간 인터페이스 확인'):
            self.assertIn(stage, self.text('#ees-work-designer'))
        self.assertEqual(self.operations()['schedules'], [])
        self.assertIsNone(record['published_version'])
        self.screenshot('procedure-initial-editable')
        self.click('.ew-procedure-menu summary')
        self.click('[data-author-action="copy"]')
        self.wait("document.querySelector('#ees-work-dialog [name=name]')")
        self.fill('#ees-work-dialog [name=name]', '합성 횡전개 절차 최종')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[name=procedure_template]')"))
        self.assertIn('게시 기록', self.text('#ees-work-dialog'))
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(self.server.completions, [])
        self.click('[data-author-action="tab"][data-tab="content"]')
        created = [body for body in self.server.workspace_commands if body.get('action') == 'copy_workflow']
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]['workflow_id'], record['id'])
        self.assertEqual(created[0]['name'], '합성 횡전개 절차 최종')
        self.assertEqual(created[0]['system_id'], 'EMS')
        self.assertEqual(UUID(created[0]['request_id']).version, 4)
        self.assertNotIn('definition', created[0])
        record = next(item for item in self.state()['workflows'] if item['name'] == '합성 횡전개 절차 최종')
        saved = self.state(workflow_id=record['id'])['workflow']
        self.assertEqual(saved['revision'], 1)
        self.assertIsNone(saved['published_version'])
        definition = saved['draft']
        self.assertEqual((definition['category'], definition['mode'], definition['execution_scope']),
                         ('setup', 'on_demand', 'factory'))
        nodes = definition['nodes']
        self.assertEqual(sum(node['type'] == 'p' for node in nodes.values()), 1)
        self.assertEqual(sum(node['type'] == 't' for node in nodes.values()), 4)
        self.assertEqual(sum(node['type'] == 'j' for node in nodes.values()), 6)
        self.assertEqual(len({node['id'] for node in nodes.values()}), 11)
        for key, node in nodes.items():
            self.assertEqual(key, node['id'])
            self.assertRegex(key, r'^[ptj]-[0-9a-f]{12}$')
            self.assertTrue(all(value in nodes for value in node.get('children', []) + node.get('deps', [])))
            if node.get('parent'):
                self.assertIn(key, nodes[node['parent']]['children'])
        tool_jobs = [node for node in nodes.values() if node.get('mode') == 'tool']
        self.assertTrue(tool_jobs)
        self.assertTrue(all(not node.get('tool_reference') and not node.get('tool_contract_id') for node in tool_jobs))
        self.assertEqual(self.operations()['schedules'], [])
        self.assertEqual(self.bridge.calls, [])
        self.click('[data-author-action=stage_toggle][data-id="' + tool_jobs[0]['parent'] + '"]')
        self.assertIn('도구 연결 전', self.text('#ees-work-designer'))
        self.click('.ew-procedure-menu summary')
        self.click('[data-author-action="edit_workflow"]')
        self.wait("document.querySelector('#ew-summary-editor')")
        self.assertIn('분류 변경은 같은 시스템 안에서 목록 위치만 바꿉니다', self.text('#ew-summary-editor'))
        self.click('#ew-summary-editor [name=name]')
        self.key('Tab', 9)
        self.assertEqual(self.browser.evaluate('document.activeElement.name'), 'category')
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ew-summary-editor')")
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=summary_edit][data-id=business]')"),
                        self.browser.evaluate('document.activeElement?.outerHTML'))
        self.assertEqual(self.state(workflow_id=record['id'])['workflow']['revision'], 1)
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('.ew-author-validation')")
        validated = self.state(workflow_id=record['id'])['workflow']
        self.assertTrue(validated['validation']['errors'])
        self.assertRegex(' '.join(validated['validation']['errors']), r'도구|연결|Native')
        self.assertTrue(self.read('[data-author-action=publish]', 'disabled'))
        self.assertIsNone(validated['published_version'])
        self.assertEqual(len(self.server.completions), 0)
        self.screenshot('procedure-examples-created-publication-blocked')

        self.click('[data-author-action="list"]')
        self.click('[data-author-action="create"]')
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 600, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 600')
        self.fill('#ees-work-dialog [name=name]', '좁은 화면에서 보존할 이름')
        narrow = self.browser.evaluate("(()=>{const modal=document.querySelector('#ees-work-dialog'),bounds=modal.getBoundingClientRect();return {overflow:modal.scrollWidth-modal.clientWidth,left:bounds.left,right:bounds.right,bottom:bounds.bottom};})()")
        self.assertLessEqual(narrow['overflow'], 1)
        self.assertGreaterEqual(narrow['left'], 0)
        self.assertLessEqual(narrow['right'], 601)
        self.assertLessEqual(narrow['bottom'], 901)
        self.screenshot('procedure-name-dialog-narrow')
        self.click('#ees-work-dialog [data-dialog-cancel]')
        self.assertEqual(len(self.state()['workflows']), 4)
        self.assertEqual(self.server.completions, [])

    def test_missing_random_uuid_creates_and_saves_draft_in_native_ui(self):
        # Loopback is trustworthy in Chrome. Explicit API removal reproduces
        # the intranet capability boundary, not a real insecure-origin test.
        self.browser.evaluate("Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});true")
        self.assertEqual(self.browser.evaluate('typeof crypto.randomUUID'), 'undefined')
        self.assertEqual(self.browser.evaluate('typeof crypto.getRandomValues'), 'function')
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action="create"]')
        self.fill('#ees-work-dialog [name=name]', 'HTTP 초안 생성 검증')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('[data-author-action="tab"][data-tab="content"]')
        creations = [body for body in self.server.workspace_commands
                     if body.get('action') == 'create_workflow']
        self.assertEqual(len(creations), 1)
        created = creations[0]
        self.assertEqual(created['name'], 'HTTP 초안 생성 검증')
        self.assertEqual(UUID(created['request_id']).version, 4)
        record = next(item for item in self.state()['workflows']
                      if item['name'] == created['name'])
        key = record['id']
        self.add_stage_ui('HTTP 생성 단계')
        self.add_job_ui('HTTP 생성 작업')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved['draft']['category'], 'ops')
        self.assertEqual(saved['draft']['mode'], 'on_demand')
        self.assertFalse(saved['draft'].get('execution_scope'))
        self.assertIsNone(saved['published_version'])
        stage = next(node for node in saved['draft']['nodes'].values() if node['type'] == 't')
        job = next(node for node in saved['draft']['nodes'].values() if node['type'] == 'j')
        self.assertEqual(UUID(stage['id'].removeprefix('stage-')).version, 4)
        self.assertEqual(UUID(job['id'].removeprefix('job-')).version, 4)
        self.assertEqual(job['parent'], stage['id'])
        self.assertIn(job['id'], stage['children'])
        request_ids = [body['request_id'] for body in self.server.workspace_commands
                       if body.get('action') in ('create_workflow', 'save_draft')]
        self.assertEqual(len(request_ids), 2)
        self.assertEqual(len(set(request_ids)), 2)
        self.assertTrue(all(UUID(value).version == 4 for value in request_ids))
        self.browser.call('Page.reload')
        self.wait("document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('#ees-work-designer')")
        if self.browser.evaluate("!!document.querySelector('[data-author-action=list]')"):
            self.click('[data-author-action=list]')
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.wait("document.querySelector('[data-author-action=save]')")
        self.assertEqual(self.state(workflow_id=key)['workflow']['draft'], saved['draft'])
        self.screenshot('http-id-native-create-save-reload')

    def test_schedule_mouse_field_transition_keeps_focus_and_saves_both_values(self):
        key = self.author(name='합성 일정 포커스 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition.update(mode='periodic', schedule={
            'timezone': 'Asia/Seoul', 'anchor': '2026-10-06T09:00',
            'frequency': 'weekly', 'interval': 1, 'weekday': 1,
            'name_template': '기존 {date} 회차',
        })
        self.command('save_draft', workflow_id=key,
                     expected_revision=workflow['revision'], definition=definition)
        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        # First entry adds three initial procedures; wait for the final list
        # before a physical row click, as in the schedule/delegation test.
        self.wait("document.querySelectorAll('.ew-author-list>[data-author-action=open]').length === 4")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.wait('window.__eesNativeWorkV1?.captureReference()?.workflow_id === ' + json.dumps(key))
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('.ew-author-tabs [data-author-action="tab"][data-tab="schedule"]')
        self.wait("document.querySelector('#ew-author-schedule [name=run_mode]')?.value === 'periodic'")
        self.click('[data-author-action="schedule_preview"]')
        self.wait("document.querySelector('.ew-schedule-preview')?.textContent.includes('다음 회차 기존')")
        self.click('#ew-author-schedule [name=interval]')
        for kind in ('keyDown', 'keyUp'):
            self.browser.call('Input.dispatchKeyEvent', {
                'type': kind, 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 2,
            })
        self.browser.call('Input.insertText', {'text': '2'})
        self.assertIn('일정이 바뀌었습니다', self.text('.ew-schedule-preview'))
        self.assertNotIn('다음 회차 기존', self.text('.ew-schedule-preview'))
        # Do not use fill()'s Tab commit: a real mouse transition must keep its
        # target rather than replacing the entire form during blur/change.
        self.click('#ew-author-schedule [name=name_template]')
        self.assertEqual(self.browser.evaluate('document.activeElement?.name'), 'name_template')
        for kind in ('keyDown', 'keyUp'):
            self.browser.call('Input.dispatchKeyEvent', {
                'type': kind, 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 2,
            })
        self.browser.call('Input.insertText', {'text': '마우스로 입력한 {date} 회차'})
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['draft']['schedule']['interval'], 2)
        self.assertEqual(saved['draft']['schedule']['name_template'], '마우스로 입력한 {date} 회차')
        self.screenshot('integrated-figma-b21-mouse-focus-saved')

    def test_schedule_preview_save_publish_and_explicit_delegation_preserve_existing_cycle(self):
        key = self.author(name='합성 일정 UI 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition['mode'] = 'periodic'
        definition['schedule'] = {
            'timezone': 'Asia/Seoul', 'anchor': '2026-10-06T09:00',
            'frequency': 'weekly', 'interval': 1, 'weekday': 1,
            'name_template': '기존 {date} 회차',
            'stage_deadlines': {'stage': {'offset_days': -8, 'end_offset_days': -6}},
            'opening': 'after_previous_closed', 'closing': 'after_last_stage',
            'non_working_days': 'notify_no_shift',
        }
        saved = self.command('save_draft', workflow_id=key,
                             expected_revision=workflow['revision'], definition=definition)
        self.command('validate_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
        original = self.start(key, mode='periodic')
        published_before = original['version']
        revision_before = self.state(workflow_id=key)['workflow']['revision']

        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelectorAll('.ew-author-list>[data-author-action=open]').length === 4")
        self.wait("document.querySelector('[data-author-action=open][data-id=\"" + key + "\"]')")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.wait('window.__eesNativeWorkV1?.captureReference()?.workflow_id === ' + json.dumps(key))
        self.wait("document.querySelector('[data-author-action=tab][data-tab=content]')")
        self.click('.ew-author-tabs [data-author-action="tab"][data-tab="schedule"]')
        self.wait("document.querySelector('#ew-author-schedule [name=interval]')")
        self.assertEqual(self.read('#ew-author-schedule [name=interval]', 'value'), '1')
        self.fill('#ew-author-schedule [name=interval]', '2')
        self.fill('#ew-author-schedule [name=name_template]', '화면에서 저장한 {date} 회차')
        self.click('[data-author-action="schedule_preview"]')
        self.wait("document.querySelector('.ew-schedule-preview')?.textContent.includes('다음 회차 화면에서 저장한')")
        self.assertEqual(self.state(workflow_id=key)['workflow']['revision'], revision_before)
        self.assertEqual(self.operations()['schedules'], [])
        preview_requests = [body for body in self.server.workspace_commands
                            if body.get('action') == 'schedule_preview']
        self.assertEqual(preview_requests[-1]['definition']['schedule']['interval'], 2)
        self.assertEqual(self.bridge.calls, [])
        self.assertIn('공휴일 달력', self.text('.ew-schedule-preview'))
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('.ew-schedule-modes [aria-pressed=true]')].map(e=>e.textContent)"), ['주기'])
        geometry = self.browser.evaluate("""(()=>{const e=document.querySelector('.ew-schedule-preview .ew-icon'),r=e.getBoundingClientRect();return {width:r.width,height:r.height,src:e.currentSrc,loaded:e.complete&&e.naturalWidth>0,font:getComputedStyle(document.querySelector('.ew-schedule-card')).fontFamily,overflow:document.querySelector('.ew-author-scroll').scrollHeight>document.querySelector('.ew-author-scroll').clientHeight};})()""")
        self.assertTrue(geometry['loaded'], geometry)
        self.assertAlmostEqual(geometry['width'], 14, delta=.1)
        self.assertAlmostEqual(geometry['height'], 14, delta=.1)
        self.assertIn('1fc4e.svg', geometry['src'])
        directory = self.screenshot('integrated-figma-b21-live-preview')

        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        current = self.state(workflow_id=key)['workflow']
        self.assertEqual(current['draft']['schedule']['interval'], 2)
        self.assertEqual(current['draft']['schedule']['name_template'], '화면에서 저장한 {date} 회차')
        self.assertGreater(current['revision'], revision_before)
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('[data-author-action=publish]')")
        self.click('[data-author-action="publish"]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('게시 v" + str(published_before + 1) + "')")
        published = self.state(workflow_id=key)['workflow']
        prior = self.state(run_id=original['id'])['run']
        self.assertEqual(prior['version'], published_before)
        self.assertEqual(prior['definition']['schedule']['interval'], 1)
        self.assertEqual(prior['definition']['schedule']['name_template'], '기존 {date} 회차')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
        self.click('.ew-author-schedules > summary')
        self.click('[data-author-action="schedule_create"]')
        self.assertFalse(self.read('#ees-work-dialog [name=delegated]', 'checked'))
        self.assertIn('게시 버전 그대로', self.text('#ees-work-dialog'))
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('.ew-author-schedules')?.textContent.includes('실행 위임 없음')")
        undelegated = self.operations()['schedules']
        self.assertEqual(len(undelegated), 1)
        self.assertFalse(undelegated[0]['delegated'])
        self.assertFalse(undelegated[0]['lifecycle_enabled'])
        self.assertEqual(undelegated[0]['rule'], published['draft']['schedule'])

        # A separate explicit confirmation enables lifecycle. No timer or
        # fixture mutation provides user delegation.
        if not self.read('.ew-author-schedules', 'open'):
            self.click('.ew-author-schedules > summary')
        self.click('[data-author-action="schedule_create"]')
        self.click('#ees-work-dialog [name=delegated]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('.ew-author-schedules')?.textContent.includes('실행 위임됨')")
        schedules = self.operations()['schedules']
        self.assertEqual(len(schedules), 2)
        active = next(item for item in schedules if item['delegated'])
        self.assertTrue(active['lifecycle_enabled'])
        self.assertEqual(active['version'], published_before + 1)
        self.assertEqual(active['identity_user_id'], self.server.user['id'])
        self.assertEqual(active['rule'], published['draft']['schedule'])
        self.assertEqual(self.bridge.calls, [])
        self.screenshot('integrated-figma-b21-published-reservation')
        (directory / 'integrated-figma-b21-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native UI; synthetic Native session; real workspace and operations SQLite',
            'geometry': geometry, 'preview_saved_definition': False,
            'saved_interval': current['draft']['schedule']['interval'],
            'preserved_existing_version': prior['version'], 'published_version': active['version'],
            'undelegated_lifecycle_enabled': undelegated[0]['lifecycle_enabled'],
            'explicit_lifecycle_enabled': active['lifecycle_enabled'],
            'external_transport_calls': len(self.bridge.calls),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_read_retry_policy_saved_in_ui_records_failed_and_successful_attempts_separately(self):
        key = self.author(name='합성 읽기 재조회 UI 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition['nodes']['job-0'].update(mode='tool', tool_reference={
            'tool_id': 'jira', 'function': 'jira_dashboard', 'revision': 1,
            'content_hash': 'a' * 64, 'schema_hash': 'b' * 64,
            'config_hash': 'c' * 64, 'environment': 'd' * 64,
        })
        self.command('save_draft', workflow_id=key,
                     expected_revision=workflow['revision'], definition=definition)
        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('[data-author-action=open][data-id=\"" + key + "\"]')")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('.ew-author-tabs [data-author-action=tab][data-tab=content]')
        self.open_author_job_ui('job-0')
        self.assertEqual(self.read('#ew-author-node [name=read_retry_count]', 'value'), '0')
        self.assertNotIn('read_retry', self.state(workflow_id=key)['workflow']['draft']['nodes']['job-0'])
        # Read-only observation captures any asynchronous control replacement;
        # it never enables a control or changes product state.
        self.browser.evaluate("""(()=>{window.__eesAuthoringObservations=[];const record=()=>{const f=document.querySelector('#ew-author-node');const row={time:performance.now(),mode:f?.querySelector('[name=mode]')?.value,read_retry_count:f?.querySelector('[name=read_retry_count]')?.value,status:document.querySelector('[data-author-status]')?.textContent};if(window.__eesAuthoringObservations.length<100)window.__eesAuthoringObservations.push(row);};window.__eesAuthoringObserver=new MutationObserver(record);window.__eesAuthoringObserver.observe(document.querySelector('#ees-work-authoring-panel'),{childList:true,subtree:true});record();return true;})()""")
        try:
            self.fill('#ew-author-node [name=read_retry_count]', '2')
        finally:
            observed = self.browser.evaluate("""(()=>{window.__eesAuthoringObserver.disconnect();const form=document.querySelector('#ew-author-node');return {changes:window.__eesAuthoringObservations,fields:[...(form?.elements || [])].map(e=>({name:e.name,value:e.value,disabled:e.disabled})),html:form?.outerHTML};})()""")
            directory = self.screenshot('integrated-figma-read-retry-control-observation')
            (directory / 'integrated-figma-read-retry-control-observation.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('.ew-author-validation-row')?.textContent.includes('조회 재시도는 검증된 읽기 작업에만')")
        self.assertEqual(self.text('.ew-author-validation h2'), '게시 전 확인')
        self.assertIn('게시를 막는 문제 1', self.text('.ew-author-validation summary'))
        incomplete = self.state(workflow_id=key)['workflow']
        self.assertEqual(len(incomplete['validation']['errors']), 1)
        self.assertIn('job-0: 조회 재시도는 검증된 읽기 작업에만 0~3회, 전체 1~300초',
                      incomplete['validation']['errors'][0])
        self.assertTrue(self.read('[data-author-action="publish"]', 'disabled'))
        self.screenshot('integrated-figma-read-retry-publication-blocker')
        self.click('[data-author-action="validation_open"][data-id="errors:0"]')
        self.wait("document.querySelector('#ew-author-node [name=read_retry_deadline]')")
        self.assertEqual(self.read('#ew-author-node [name=read_retry_count]', 'value'), '2')
        self.fill('#ew-author-node [name=read_retry_deadline]', '30')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['draft']['nodes']['job-0']['read_retry'], {'count': 2, 'deadline_seconds': 30})
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('[data-author-action=publish]')?.disabled === false")
        self.assertEqual(self.state(workflow_id=key)['workflow']['validation']['errors'], [])
        self.click('[data-author-action="publish"]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('게시 v2')")

        async def invoke(actor, reference, arguments, context):
            await self.bridge.check(actor, reference)
            self.bridge.calls.append({'actor': actor['id'], 'arguments': deepcopy(arguments),
                                      'context': deepcopy(context)})
            if len(self.bridge.calls) == 1:
                return {'status': 'failed', 'transport': 'failed', 'failure_confirmed': True,
                        'completeness': 'unknown', 'error': {'code': 'upstream_error'}}
            return {'status': 'succeeded', 'completeness': 'complete',
                    'data': {'summary': '두 번째 합성 읽기 결과'}}

        self.bridge.invoke = invoke
        run = self.start(key)
        self.click('[data-action="mode"][data-mode="work"]')
        self.open_run(key, run)
        self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-work-panel .ew-status[data-status=waiting_confirmation]')")
        result = self.state(run_id=run['id'])['run']
        self.assertEqual(len(self.bridge.calls), 2)
        self.assertEqual([attempt['status'] for attempt in result['attempts']], ['failed', 'succeeded'])
        self.assertEqual(result['jobs']['job-0']['status'], 'waiting_confirmation')
        self.assertEqual(result['jobs']['job-0']['decisions'], [])
        self.assertEqual(result['attempts'][0]['result']['error']['code'], 'upstream_error')
        self.assertEqual(result['definition']['nodes']['job-0']['read_retry'], {'count': 2, 'deadline_seconds': 30})
        directory = self.screenshot('integrated-figma-read-retry-human-boundary')
        (directory / 'integrated-figma-read-retry-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native UI; synthetic Native session and read transport; real SQLite executor',
            'explicit_policy': result['definition']['nodes']['job-0']['read_retry'],
            'attempt_statuses': [attempt['status'] for attempt in result['attempts']],
            'external_transport_calls': len(self.bridge.calls),
            'business_status': result['jobs']['job-0']['status'],
            'human_decisions': result['jobs']['job-0']['decisions'],
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
