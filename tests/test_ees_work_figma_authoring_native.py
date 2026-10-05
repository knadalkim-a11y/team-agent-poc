"""Built Native authoring UI with real workspace/operations SQLite commands.

Reconstructed from retained session source/patch text after workspace loss;
requires new verification and new screenshots. Native session and external read
transport are synthetic. The complete CLI gate verifies real login separately.
"""
import asyncio
from copy import deepcopy
import json

from ees_work_integrated_fixture import IntegratedNativeCase


class FigmaAuthoringNativeTests(IntegratedNativeCase):
    def operations(self):
        return asyncio.run(self.server.workflow.operations.state(self.server.user, system_id='EMS'))

    def screenshot(self, label, *, wait_for_fonts=True):
        directory = super().screenshot(label, wait_for_fonts=wait_for_fonts)
        observed = self.browser.evaluate("""(()=>{
          const panel=document.querySelector('#ees-work-panel');
          const author=document.querySelector('#ees-work-designer');
          const active=document.activeElement;
          const region=e=>e?{text:e.innerText,html:e.outerHTML}:null;
          return {scope:'built Native UI; synthetic session and data',
            path:location.pathname,ready:document.readyState,fonts:document.fonts.status,
            viewport:[innerWidth,innerHeight],active:{tag:active?.tagName,id:active?.id,name:active?.name},
            panel:region(panel),authoring:region(author)};
        })()""")
        (directory / (label + '-dom.json')).write_text(
            json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return directory

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
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
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
        self.wait("document.querySelector('[data-author-action=open][data-id=\"" + key + "\"]')")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
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
        self.click('[data-author-action="node"][data-id="job-0"]')
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
