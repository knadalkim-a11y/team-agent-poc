"""C phase 1 acceptance in packaged Native Svelte/Tiptap and real Chrome.

Workflow actions, snapshots and SQLite persistence are real. Login, chat APIs
and external/model transports use the existing temporary Native UI fixture;
these tests do not claim full Open WebUI startup or company acceptance.
"""
from copy import deepcopy
import asyncio
import json
import unittest

import test_ees_work_demo as native


class CPhaseOneNativeTests(unittest.TestCase):
    # Reuse helpers explicitly, without inheriting/replaying the old full suite.
    setUpClass = classmethod(native.EESWorkNativeBrowserTests.setUpClass.__func__)
    setUp = native.EESWorkNativeBrowserTests.setUp
    tearDown = native.EESWorkNativeBrowserTests.tearDown
    call_workflow_tool = native.EESWorkNativeBrowserTests.call_workflow_tool
    current = native.EESWorkNativeBrowserTests.current
    publish_runtime_fixture = native.EESWorkNativeBrowserTests.publish_runtime_fixture
    navigate = native.EESWorkNativeBrowserTests.navigate
    wait = native.EESWorkNativeBrowserTests.wait
    read = native.EESWorkNativeBrowserTests.read
    text = native.EESWorkNativeBrowserTests.text
    click = native.EESWorkNativeBrowserTests.click
    key = native.EESWorkNativeBrowserTests.key
    fill = native.EESWorkNativeBrowserTests.fill
    wait_scope_ready = native.EESWorkNativeBrowserTests.wait_scope_ready
    select_scope = native.EESWorkNativeBrowserTests.select_scope
    open_category = native.EESWorkNativeBrowserTests.open_category
    choose = native.EESWorkNativeBrowserTests.choose
    run_job = native.EESWorkNativeBrowserTests.run_job
    seed_case = native.EESWorkNativeBrowserTests.seed_case
    screenshot = native.EESWorkNativeBrowserTests.screenshot
    hover = native.EESWorkNativeBrowserTests.hover
    visual_style = native.EESWorkNativeBrowserTests.visual_style
    save_visual_measurements = native.EESWorkNativeBrowserTests.save_visual_measurements
    assert_native_korean_font = native.EESWorkNativeBrowserTests.assert_native_korean_font

    def ready_case(self):
        case = self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.wait_scope_ready('site')
        return case

    def settle(self):
        self.wait("!!document.querySelector('#ees-work-panel') && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")

    def assert_job_status_visible(self):
        bounds = self.browser.evaluate("""(()=>{const slot=document.querySelector('#ees-work-identity-slot'),
            badge=slot.querySelector('.ew-badge'),r=badge.getBoundingClientRect();
            return {slot:slot.getBoundingClientRect().toJSON(),badge:r.toJSON(),
                hit:badge.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)),text:badge.textContent};})()""")
        self.assertTrue(bounds['text'])
        self.assertGreaterEqual(bounds['badge']['top'], bounds['slot']['top'])
        self.assertLessEqual(bounds['badge']['bottom'], bounds['slot']['bottom'])
        self.assertGreaterEqual(bounds['badge']['left'], bounds['slot']['left'])
        self.assertLessEqual(bounds['badge']['right'], bounds['slot']['right'])
        self.assertTrue(bounds['hit'], bounds)
        return bounds

    def seed_return_case(self, long_body=False):
        """Arrange volume through the existing definition/service contracts.

        Forty real manual confirmations make a non-default completed filter
        span two pages. No production state or rendered DOM is fabricated.
        """
        definition = deepcopy(self.current()['catalog'])
        nodes = definition['nodes']
        nodes['return-p'] = dict(deepcopy(nodes['setup-p']), id='return-p',
            name='복귀 검증 업무', children=['return-t'], skills=[])
        nodes['return-t'] = dict(deepcopy(nodes['prep-t']), id='return-t',
            name='복귀 검증 단계', parent='return-p', children=[])
        definition['roots']['setup'].append('return-p')
        for number in range(60):
            node_id = f'return-{number:03d}-j'
            nodes[node_id] = dict(deepcopy(nodes['scope-j']), id=node_id,
                name=f'복귀 검증 작업 {number:03d}', parent='return-t',
                deps=['return-000-j'] if number == 30 else [])
            nodes['return-t']['children'].append(node_id)
        if long_body:
            nodes['return-030-j']['rule'] = '현장 담당자가 적용 범위와 확인 자료를 검토했습니다. ' * 16
        self.publish_runtime_fixture(definition)
        state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            'action': 'create', 'chat_id': 'existing-chat',
            'payload': {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'return-p'}}))
        self.assertTrue(state['ok'], state)
        for number in range(40):
            case = state['case']
            state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                'action': 'run', 'chat_id': 'existing-chat', 'case_id': case['id'],
                'expected_revision': case['revision'], 'node_id': f'return-{number:03d}-j',
                'payload': {'confirm': True}}))
            self.assertTrue(state['ok'], state)
        self.assertEqual(state['case']['progress'], {'done': 40, 'total': 60})
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.wait_scope_ready('site')
        return state['case']

    def return_list_snapshot(self):
        return self.browser.evaluate("""(()=>{const body=document.querySelector('#ees-work-content'),
            active=document.activeElement,rect=active?.getBoundingClientRect(),clip=body.getBoundingClientRect();
            return {query:body.querySelector('#ees-work-job-search')?.value,
                filter:body.querySelector('[data-action=job_filter][aria-pressed=true]')?.dataset.filter,
                page:body.querySelector('.ew-work-pagination')?.innerText,
                expanded:[...body.querySelectorAll('[data-action=job_condition][aria-expanded=true]')].map(e=>e.dataset.nodeId),
                rows:[...body.querySelectorAll('[data-work-job]')].map(e=>e.dataset.workJob),
                scroll:body.scrollTop,focus:{tag:document.activeElement?.tagName,id:document.activeElement?.id,
                    action:document.activeElement?.dataset.action,node:document.activeElement?.dataset.nodeId,
                    rect:rect?.toJSON(),visible:!!rect&&rect.top>=clip.top&&rect.bottom<=clip.bottom,
                    hit:!!rect&&active.contains(document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2))},
                back:document.querySelector('#ees-work-parent')?.innerText,
                backLabel:document.querySelector('#ees-work-parent [data-action=panel_back]')?.getAttribute('aria-label')};})()""")

    def assert_return_list(self, before, focus_selector):
        after = self.return_list_snapshot()
        for key in ('query', 'filter', 'page', 'expanded', 'rows'):
            self.assertEqual(after[key], before[key], key)
        self.assertAlmostEqual(after['scroll'], before['scroll'], delta=2)
        self.assertTrue(self.browser.evaluate('document.activeElement?.matches(' + json.dumps(focus_selector) + ')'), after)
        self.assertTrue(after['focus']['visible'] and after['focus']['hit'], after['focus'])
        return after

    def completion_return_scenario(self, dock):
        before_case = self.seed_return_case(long_body=dock)
        width, height = (1366, 768) if dock else (1920, 1080)
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
        kind = 'long-adjacent' if dock else 'inline'
        self.choose('return-p')
        p_to_t = '#ees-work-content [data-action=select][data-node-id="return-t"]'
        self.click(p_to_t)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
        self.fill('#ees-work-job-search', '복귀 검증 작업')
        self.click('[data-action=job_filter][data-filter=completed]')
        # Six visible rows match C's list density. Reach a later page through
        # the actual pagination controls, retaining the non-default page gate.
        for page in range(1, 6):
            self.click('[data-action=job_page][data-page="' + str(page) + '"]')
        self.click('[data-action=job_condition][data-node-id="return-030-j"]')
        row = '[data-work-job="return-030-j"] [data-action=select][data-node-id="return-030-j"]'
        self.browser.evaluate('document.querySelector(' + json.dumps(row) + ').scrollIntoView({block:"center"})')
        before = self.return_list_snapshot()
        self.assertIn('31–36 / 40개 작업', before['page'])
        self.screenshot('c-return-' + kind + '-t-before')
        self.click(row)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 작업 030' && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")
        # Reopen preserves the completed J and the existing T→J entry.
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 작업 030'")
        # Deliberately select the completion-area CTA by its public text and
        # physical region, never the header path or a particular action token.
        cta = '.ew-work-action-region .ew-primary'
        self.assertEqual(self.text(cta), '단계로 돌아가기')
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('#ees-work-panel .ew-work-action-region').length"), 1)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-work-action-region .ew-primary')?.closest('#ees-work-action-dock')"))
        self.assertTrue(self.browser.evaluate("document.querySelector('.ew-work-action-region')?.previousElementSibling?.matches('[data-work-section=current-result]')"))
        self.screenshot('c-return-' + kind + '-completed-button')
        self.click(cta)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계' && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")
        after = self.return_list_snapshot()
        self.screenshot('c-return-' + kind + '-t-after')
        self.save_visual_measurements('c-return-' + kind + '-evidence', {
            'viewport': [width, height], 'completion_button_placement': kind,
            'before': before, 'after': after,
            'boundary': 'Packaged Native UI, real WorkflowService/SQLite; synthetic Native login/chat and test catalog.'})
        self.assert_return_list(before, row)
        self.assertIn('복귀 검증 업무', after['back'])
        self.assertIn('복귀 검증 업무로 돌아가기', after['backLabel'])
        self.assertNotIn('복귀 검증 작업 030로 돌아가기', after['backLabel'])
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
        reopened = self.return_list_snapshot()
        for key in ('query', 'filter', 'page', 'expanded', 'rows', 'scroll', 'back', 'backLabel'):
            self.assertEqual(reopened[key], after[key], 'T close/reopen: ' + key)
        self.click('#ees-work-parent [data-action=panel_back]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 업무'")
        self.assertTrue(self.browser.evaluate('document.activeElement?.matches(' + json.dumps(p_to_t) + ')'))

        # Existing panel_back uses the same origin row and keeps list state.
        self.click(p_to_t)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
        self.browser.evaluate('document.querySelector(' + json.dumps(row) + ').scrollIntoView({block:"center"})')
        back_before = self.return_list_snapshot()
        self.click(row)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 작업 030'")
        self.click('#ees-work-parent [data-action=panel_back]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
        self.assert_return_list(back_before, row)

        # Direct sidebar entry must not invent a J→T back entry, even when
        # a previous list visit exists in this same panel session.
        self.choose('return-t')
        sidebar_job = '#ees-work-entry [data-action=select][data-node-id="return-030-j"]'
        self.assertTrue(self.read(sidebar_job, 'getClientRects().length'))
        self.click(sidebar_job)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 작업 030'")
        self.click(cta)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
        self.assertIsNone(self.read('#ees-work-parent [data-action=panel_back]'))
        parent = '#ees-work-parent [data-action=select][data-node-id="return-p"]'
        self.click(parent)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 업무'")
        self.assertEqual(self.current()['case']['jobs'], before_case['jobs'])
        self.assertEqual(self.server.completions, [])
        self.save_visual_measurements('c-return-' + kind + '-evidence', {
            'viewport': [width, height], 'completion_button_placement': kind,
            'before': before, 'after': after,
            'verified': ['completion CTA restores search/filter/page/expanded rows/scroll/focus',
                'J and T close/reopen', 'T to P trail and focus', 'existing panel_back',
                'sidebar direct J uses parent without false back entry', 'saved jobs unchanged'],
            'boundary': 'Packaged Native UI, real WorkflowService/SQLite; synthetic Native login/chat and test catalog.'})

    def test_completed_return_inline_restores_task_list_and_parent_navigation(self):
        self.completion_return_scenario(dock=False)

    def test_completed_return_dock_restores_task_list_and_parent_navigation(self):
        self.completion_return_scenario(dock=True)

    def test_completed_return_preserves_incomplete_filter_when_finished_row_disappears(self):
        self.seed_return_case()
        self.choose('return-t')
        self.fill('#ees-work-job-search', '복귀 검증 작업')
        self.click('[data-action=job_filter][data-filter=incomplete]')
        for number, remaining in ((40, 19), (55, 18)):
            with self.subTest(finished_row=number):
                node_id = f'return-{number:03d}-j'
                row = '[data-work-job="' + node_id + '"] [data-action=select]'
                while not self.read(row):
                    next_page = self.browser.evaluate("[...document.querySelectorAll('[data-action=job_page]')].find(e=>e.textContent==='다음'&&!e.disabled)?.dataset.page")
                    self.assertIsNotNone(next_page, 'Expected incomplete job must remain reachable')
                    self.click('[data-action=job_page][data-page="' + next_page + '"]')
                self.click(row)
                self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 작업 " + f'{number:03d}' + "'")
                self.click('#ees-work-run', confirm=True)
                self.wait("document.querySelector('.ew-work-action-region .ew-primary')?.textContent === '단계로 돌아가기' && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")
                self.assertEqual(self.current()['case']['jobs'][node_id]['status'], 'passed')
                self.click('.ew-work-action-region .ew-primary')
                self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '복귀 검증 단계'")
                after = self.return_list_snapshot()
                self.save_visual_measurements('c-return-filtered-out-' + str(number) + '-evidence', after)
                self.screenshot('c-return-filtered-out-' + str(number) + '-focus')
                self.assertEqual(after['query'], '복귀 검증 작업')
                self.assertEqual(after['filter'], 'incomplete')
                self.assertNotIn(node_id, after['rows'])
                self.assertIn(f'/ {remaining}개 작업', after['page'])
                self.assertTrue(self.browser.evaluate("document.activeElement?.matches('#ees-work-job-search, [data-action=job_filter][aria-pressed=true], [data-work-job] [data-action=select]')"), after)
                self.assertTrue(after['focus']['visible'] and after['focus']['hit'], after['focus'])

    def test_existing_ap_save_reload_fail_retry_evidence_and_return(self):
        case = self.ready_case()
        untouched = deepcopy({key: value for key, value in case['jobs'].items() if key != 'ap-j'})
        self.choose('ap-j')
        first_target = 'C안 합성 AP 대상 1 · 해외 생산설비 연결 확인'
        self.fill('#ees-work-inputs input[name=ap]', first_target)
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        self.click('#ees-work-inputs-save')
        self.settle()
        saved = self.current()['case']
        self.assertEqual(saved['jobs']['ap-j']['inputs']['ap'], first_target)
        self.assertEqual(saved['jobs']['ap-j']['attempt'], 0)
        self.assertEqual(self.server.completions, [])
        self.screenshot('c-phase1-ap-saved')

        # A real document reload reconnects to the existing saved case. It
        # must not create an attempt or send the Native chat composer.
        self.browser.call('Page.reload', {'ignoreCache': True})
        self.wait("!!document.querySelector('#chat-input.ProseMirror') && !!document.querySelector('#ees-work-entry')")
        self.wait_scope_ready('site')
        self.choose('ap-j')
        self.assertEqual(self.read('#ees-work-inputs input[name=ap]', 'value'), first_target)
        self.assertEqual(self.current()['case']['id'], saved['id'])
        self.assertEqual(self.current()['case']['jobs'], saved['jobs'])
        self.fill('#chat-input', 'C안 점검 중 보존할 Native 대화 초안')

        self.run_job('ap-j', 'failed')
        first = deepcopy(self.current()['case']['jobs']['ap-j']['history'][0])
        self.assertEqual([check['status'] for check in first['checks']],
                         ['passed', 'passed', 'failed', 'skipped'])
        self.assertIn(first['checks'][2]['detail'], self.text('#ees-work-content'))
        self.assertIn('다시', self.text('#ees-work-run'))
        self.screenshot('c-phase1-ap-first-failure')
        second_target = 'C안 합성 AP 대상 2 · 재시도용 저장 값'
        self.click('.ew-work-edit > summary')
        self.fill('#ees-work-inputs input[name=ap]', second_target)
        self.click('#ees-work-inputs-save')
        self.settle()
        self.assertEqual(self.current()['case']['jobs']['ap-j']['history'][0], first)
        self.run_job('ap-j')
        after = self.current()['case']
        records = deepcopy(after['jobs']['ap-j']['history'])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], first)
        self.assertNotEqual(records[0]['checks'][2]['input'], records[1]['checks'][2]['input'])
        self.assertIn('완료 기준', self.text('#ees-work-content'))
        self.screenshot('c-phase1-ap-retry-passed')

        # Current form values must never be substituted for the saved first
        # failed call, and a skipped call has no fabricated input/output.
        trigger = '[data-action=work_detail][data-detail-tab=history]'
        self.click(trigger)
        self.click('[data-action=detail_attempt][data-attempt-index="0"]')
        self.click('[data-work-detail-content=history] [data-action=detail_call][data-call-index="2"]')
        self.assertEqual(self.text('[data-call-output]'), first['checks'][2]['detail'])
        self.assertEqual(self.text('[data-call-verdict]'), '점검 실패')
        self.click('[data-action=detail_tab][data-detail-tab=input]')
        self.assertEqual(self.text('[data-call-input]'), first['checks'][2]['input'])
        self.assertNotIn(second_target, self.text('[data-call-input]'))
        self.click('.ew-detail-calls [data-action=detail_call][data-call-index="3"]')
        self.assertIsNone(self.read('[data-call-input]'))
        self.assertIn('전달 입력 없음 · 미수행', self.text('#ees-work-dialog'))
        self.click('[data-action=detail_attempt][data-attempt-index="1"]')
        self.click('.ew-detail-calls [data-action=detail_call][data-call-index="2"]')
        self.assertEqual(self.text('[data-call-input]'), records[1]['checks'][2]['input'])
        self.screenshot('c-phase1-ap-recorded-call-input')
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertTrue(self.browser.evaluate('document.activeElement?.matches(' + json.dumps(trigger) + ')'))
        self.click('.ew-work-procedure > summary')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn('완료', self.text('#ees-work-dialog'))
        self.key('Escape', 27)

        parent_id = after['definition']['nodes']['ap-j']['parent']
        self.click('.ew-work-path [data-action=select][data-node-id="' + parent_id + '"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === "
                  + json.dumps(after['definition']['nodes'][parent_id]['name']))
        self.screenshot('c-phase1-t-return')
        self.choose('setup-p')
        self.assertIn('작업 완료', self.text('#ees-work-content'))
        self.choose('db-j')
        self.assertEqual(self.current()['case']['jobs']['db-j'], untouched['db-j'])
        self.screenshot('c-phase1-db-same-task-comparison')
        self.choose('ap-j')
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === "
                  + json.dumps(after['definition']['nodes']['ap-j']['name']))
        self.assertEqual(self.current()['case']['jobs']['ap-j']['history'], records)
        self.assertEqual({key: value for key, value in self.current()['case']['jobs'].items() if key != 'ap-j'}, untouched)
        self.assertEqual(self.text('#chat-input'), 'C안 점검 중 보존할 Native 대화 초안')
        self.assertEqual(self.server.completions, [])
        self.save_visual_measurements('c-phase1-functional-evidence', {
            'case_id': after['id'], 'version': after['version'], 'attempts': records,
            'other_jobs_unchanged': True, 'chat_completions': 0,
            'boundary': 'Packaged Native frontend + actual WorkflowService/SQLite; synthetic login/chat and mock business checks.'})
        # Saving a changed target after completion invalidates only the
        # current verdict; both recorded attempts remain immutable.
        self.click('.ew-work-edit > summary')
        self.fill('#ees-work-inputs input[name=ap]', '완료 후 변경한 합성 AP 대상')
        self.click('#ees-work-inputs-save')
        self.settle()
        invalidated = self.current()['case']['jobs']['ap-j']
        self.assertNotEqual(invalidated['status'], 'passed')
        self.assertEqual(invalidated['attempt'], 2)
        self.assertEqual(invalidated['history'], records)
        self.assertNotIn('완료 기준을 충족했습니다.', self.text('#ees-work-content'))
        self.screenshot('c-phase1-input-change-invalidates-current-result')

    def test_existing_native_execution_plan_and_return_smoke(self):
        # #65 execution_inputs/run.inputs remain separate from the legacy
        # J editable form. Reuse one existing fixed execution contract test.
        native.EESWorkNativeBrowserTests.test_durable_runtime_panel_plan_real_service_and_browser_return(self)

    def test_three_sizes_long_forms_fixed_header_and_dialog_focus(self):
        first_case = self.ready_case()
        self.choose('db-j')
        self.fill('#ees-work-inputs input[name=db]', '테스트 DB-A · 예시')
        self.click('#ees-work-inputs-save')
        self.settle()
        self.click('.ew-panel-menu > summary')
        retained = self.browser.evaluate("""new Promise(resolve=>{
            const target=document.activeElement,slot=document.querySelector('#ees-work-identity-slot');
            const observer=new MutationObserver(()=>{observer.disconnect();requestAnimationFrame(()=>resolve(document.activeElement===target))});
            observer.observe(slot,{childList:true,subtree:true});
            setTimeout(()=>{observer.disconnect();resolve(false)},4000);
            window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}));
        })""")
        self.assertTrue(retained, 'Refreshing the same J stole focus from the persistent toolbar menu')
        self.click('.ew-panel-menu > summary')
        measurements = []
        for width, height in ((1920, 1080), (1536, 960), (1366, 768)):
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            self.hover()
            layout = self.browser.evaluate("""(()=>{const box=s=>document.querySelector(s).getBoundingClientRect().toJSON();
                return {width:innerWidth,height:innerHeight,sidebar:box('#sidebar'),panel:box('#ees-work-panel'),
                    chat:box('#chat-pane'),composer:box('#chat-input'),title:box('#ees-work-panel .ew-title'),
                    input:box('#ees-work-inputs'),save:box('#ees-work-inputs-save'),run:box('#ees-work-run'),
                    content:box('#ees-work-content'),pageWidth:document.documentElement.scrollWidth};})()""")
            self.assertLessEqual(layout['pageWidth'], width + 1)
            self.assertLessEqual(layout['chat']['right'], layout['panel']['left'] + 1)
            self.assertGreaterEqual(layout['chat']['width'], 420)
            self.assertLessEqual(layout['composer']['bottom'], height)
            self.assertGreaterEqual(layout['input']['top'], layout['content']['top'])
            self.assertLessEqual(layout['run']['bottom'], height - 8)
            self.assertAlmostEqual(layout['save']['top'], layout['run']['top'], delta=1)
            if width == 1920:
                self.assertAlmostEqual(layout['panel']['width'], 840, delta=1)
            self.assertTrue(self.browser.evaluate("document.querySelector('#ees-work-inputs-save').form === document.querySelector('#ees-work-inputs')"))
            self.assertTrue(self.read('#ees-work-inputs-save', 'disabled'))
            self.assertFalse(self.read('#ees-work-run', 'disabled'))
            for selector in ('#ees-work-panel .ew-title', '.ew-work-action-note', '.ew-work-result h3'):
                style = self.visual_style(selector)
                self.assertGreaterEqual(style['contrast'], 4.5, (selector, style))
                layout.setdefault('styles', {})[selector] = style
            if width == 1920:
                self.assert_native_korean_font('#ees-work-panel .ew-title', 'c-phase1-rendered-korean-font')
            self.screenshot('c-phase1-db-' + str(width))
            measurements.append({'kind': 'same DB task', **layout})

        # Native's own resize gesture sets the user preference used for the
        # Figma 312px comparison. No DOM style or Svelte store is patched.
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        point = self.browser.evaluate("(()=>{const e=document.querySelector('#sidebar-resizer'),r=e.getBoundingClientRect();for(const y of [innerHeight/2,80,innerHeight-60])for(let x=r.x-5;x<=r.right+5;x+=1){if(e.contains(document.elementFromPoint(x,y)))return {x,y};}throw new Error('Native sidebar resizer has no exposed pointer target')})()")
        target = point['x'] + 312 - self.read('#sidebar', 'getBoundingClientRect().width')
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mousePressed', **point, 'button': 'left', 'buttons': 1, 'clickCount': 1})
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': target, 'y': point['y'], 'button': 'left', 'buttons': 1})
        self.browser.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': target, 'y': point['y'], 'button': 'left', 'buttons': 0, 'clickCount': 1})
        self.wait("Math.abs(document.querySelector('#sidebar').getBoundingClientRect().width-312)<1")
        self.assertAlmostEqual(self.read('#sidebar', 'getBoundingClientRect().width'), 312, delta=1)
        self.screenshot('c-phase1-db-1920-sidebar312')

        # Long text is published through the supported fixture arrangement
        # before a second case snapshots it; the first case stays untouched.
        definition = deepcopy(self.current()['catalog'])
        for node_id in ('setup-p', 'install-t', 'db-j'):
            definition['nodes'][node_id]['name'] += ' · 해외 생산설비 데이터베이스 대상과 현장 연결 상태 확인'
            definition['nodes'][node_id]['description'] = '현장 담당자와 입력값, 적용 범위 및 결과를 확인합니다. ' * 10
            definition['nodes'][node_id]['instructions'] = '저장된 수행 안내와 근거 자료를 검토합니다. ' * 60
        definition['nodes']['install-t']['name'] = ('현장 적용 대상과 시스템 설치 상태를 확인하는 긴 단계 이름 ' * 7)[:160]
        definition['nodes']['db-j']['name'] = ('데이터베이스 연결 및 현장 적용 상태를 확인하는 긴 작업 이름 ' * 7)[:160]
        self.publish_runtime_fixture(definition)
        self.seed_case('other-chat', ready=True)
        self.navigate('/c/other-chat')
        self.wait_scope_ready('site')
        self.fill('#chat-input', '긴 내용 확인 중에도 유지할 Native 대화 초안')
        for width, height in ((1920, 1080), (1536, 960), (1366, 768)):
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            self.choose('db-j', chat_id='other-chat')
            self.assert_job_status_visible()
            self.fill('#ees-work-inputs input[name=db]', '합성 장문 DB 대상 ' * 14 + str(width))
            self.assertTrue(self.read('#ees-work-run', 'disabled'))
            # C keeps one action adjacent to its input, including long text.
            # Reach it with real Tab presses, without tabindex overrides or
            # programmatically focusing the save control.
            for _ in range(12):
                if self.browser.evaluate("document.activeElement?.id === 'ees-work-inputs-save'"):
                    break
                self.key('Tab', 9)
            self.assertTrue(self.browser.evaluate("document.activeElement?.id === 'ees-work-inputs-save'"))
            style = self.browser.evaluate("(()=>{const e=document.activeElement,s=getComputedStyle(e);return {visible:e.matches(':focus-visible'),width:parseFloat(s.outlineWidth)}})()")
            self.assertTrue(style['visible'])
            self.assertGreaterEqual(style['width'], 2)
            revision = self.current('other-chat')['case']['revision']
            self.key('Enter', 13, text='\r')
            self.wait("document.querySelector('#ees-work-inputs-save')?.disabled && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")
            self.settle()
            self.assertEqual(self.current('other-chat')['case']['revision'], revision + 1)
            self.assertEqual(self.current('other-chat')['case']['jobs']['db-j']['attempt'], 0)
            box = self.read('#ees-work-content', 'getBoundingClientRect().toJSON()')
            header_y = self.read('#ees-work-panel .ew-title', 'getBoundingClientRect().y')
            composer_y = self.read('#chat-input', 'getBoundingClientRect().y')
            self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
                'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2, 'deltaX': 0, 'deltaY': 600})
            self.wait("document.querySelector('#ees-work-content').scrollTop > 0")
            self.assertAlmostEqual(self.read('#ees-work-panel .ew-title', 'getBoundingClientRect().y'), header_y, delta=1)
            self.assertAlmostEqual(self.read('#chat-input', 'getBoundingClientRect().y'), composer_y, delta=1)
            self.assertLessEqual(self.read('#ees-work-panel', 'scrollWidth'), self.read('#ees-work-panel', 'clientWidth') + 1)
            for delta in (-10000, 300, 10000):
                self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
                    'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2, 'deltaX': 0, 'deltaY': delta})
                self.browser.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                actions = self.browser.evaluate("""(()=>{const body=document.querySelector('#ees-work-content').getBoundingClientRect();
                    return {count:document.querySelectorAll('#ees-work-panel .ew-work-action-region').length,
                        buttons:['#ees-work-inputs-save','#ees-work-run'].map(s=>{const e=document.querySelector(s),r=e.getBoundingClientRect();
                            return {top:r.top,bottom:r.bottom,hit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)),bodyBottom:body.bottom}})};})()""")
                self.assertEqual(actions['count'], 1)
                self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-action-dock .ew-work-action-region')"))
                self.assertTrue(self.browser.evaluate("document.querySelector('.ew-work-action-region')?.previousElementSibling?.matches('#ees-work-inputs, [data-work-dirty], .ew-work-input-edit, .ew-work-edit')"))
            # An action may scroll with a long body. Keyboard navigation must
            # bring the same enabled control into view without a duplicate.
            self.click('#ees-work-inputs input[name=db]')
            for _ in range(12):
                if self.browser.evaluate("document.activeElement?.id === 'ees-work-run'"):
                    break
                self.key('Tab', 9)
            self.assertTrue(self.browser.evaluate("document.activeElement?.id === 'ees-work-run'"))
            self.assertTrue(self.browser.evaluate("(()=>{const e=document.activeElement,r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()"))
            self.screenshot('c-phase1-long-job-scroll-' + str(width))
            trigger = '[data-action=work_detail][data-detail-tab=config]'
            self.click(trigger)
            self.wait("document.querySelector('#ees-work-dialog')?.open")
            dialog = self.read('#ees-work-dialog', 'getBoundingClientRect().toJSON()')
            self.assertGreaterEqual(dialog['top'], 8)
            self.assertLessEqual(dialog['bottom'], height - 8)
            self.assertLessEqual(self.read('#ees-work-dialog', 'scrollWidth'), self.read('#ees-work-dialog', 'clientWidth') + 1)
            title_y = self.read('#ees-work-dialog-title', 'getBoundingClientRect().y')
            body = self.read('#ees-work-dialog .ew-dialog-body', 'getBoundingClientRect().toJSON()')
            self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
                'x': body['x'] + body['width']/2, 'y': body['y'] + body['height']/2, 'deltaX': 0, 'deltaY': 700})
            self.wait("document.querySelector('#ees-work-dialog .ew-dialog-body').scrollTop > 0")
            self.assertAlmostEqual(self.read('#ees-work-dialog-title', 'getBoundingClientRect().y'), title_y, delta=1)
            focusables = "[...document.querySelectorAll('#ees-work-dialog button,#ees-work-dialog input,#ees-work-dialog textarea,#ees-work-dialog select,#ees-work-dialog a[href],#ees-work-dialog summary,#ees-work-dialog [tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length)"
            self.browser.evaluate('(' + focusables + ').at(-1).focus()')
            self.key('Tab', 9)
            self.assertTrue(self.browser.evaluate('document.activeElement === (' + focusables + ')[0]'))
            self.key('Tab', 9, modifiers=8)
            self.assertTrue(self.browser.evaluate('document.activeElement === (' + focusables + ').at(-1)'))
            self.screenshot('c-phase1-long-dialog-' + str(width))
            self.key('Escape', 27)
            self.wait("!document.querySelector('#ees-work-dialog')")
            self.assertTrue(self.browser.evaluate('document.activeElement?.matches(' + json.dumps(trigger) + ')'))
            self.assertEqual(self.text('#chat-input'), '긴 내용 확인 중에도 유지할 Native 대화 초안')
            for node_id in ('install-t', 'setup-p'):
                self.choose(node_id, chat_id='other-chat')
                self.assertEqual(self.text('#ees-work-panel .ew-title'), definition['nodes'][node_id]['name'])
                self.assertLessEqual(self.read('#ees-work-content', 'scrollWidth'), self.read('#ees-work-content', 'clientWidth') + 1)
        self.choose('db-j', chat_id='other-chat')
        self.browser.evaluate("document.querySelector('#ees-work-resizer').focus()")
        self.key('Home', 36)
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), 340, delta=1)
        self.assert_job_status_visible()
        self.assertGreaterEqual(self.read('#ees-work-content', 'clientHeight'), 120)
        self.assertLessEqual(self.read('#ees-work-parent', 'getBoundingClientRect().height'), 73)
        measurements.append({'kind': '160-character names at minimum panel width',
            'panel_width': self.read('#ees-work-panel', 'getBoundingClientRect().width'),
            'body_height': self.read('#ees-work-content', 'clientHeight'),
            'parent_height': self.read('#ees-work-parent', 'getBoundingClientRect().height'),
            'status': self.assert_job_status_visible()})
        self.screenshot('c-phase1-long-parent-minimum-width')
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), 340, delta=1)
        self.click('#ees-work-inputs input[name=db]')
        self.assertGreaterEqual(self.read('#ees-work-inputs input[name=db]', 'getBoundingClientRect().top'),
                                self.read('#ees-work-content', 'getBoundingClientRect().top'))
        self.browser.evaluate("document.documentElement.classList.add('dark')")
        self.browser.evaluate("Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))")
        self.fill('#ees-work-inputs input[name=db]', '다크 테마에서 편집 중인 합성 DB 입력')
        for _ in range(12):
            if self.browser.evaluate("document.activeElement?.id === 'ees-work-inputs-save'"):
                break
            self.key('Tab', 9)
        self.assertTrue(self.browser.evaluate("document.activeElement?.id === 'ees-work-inputs-save' && document.activeElement.matches(':focus-visible')"))
        dark_styles = {selector: self.visual_style(selector) for selector in (
            '#ees-work-panel .ew-title', '.ew-work-action-note', '#ees-work-inputs-save')}
        for selector, style in dark_styles.items():
            self.assertGreaterEqual(style['contrast'], 4.5, (selector, style))
        self.assertGreaterEqual(dark_styles['#ees-work-inputs-save']['outlineWidth'], 2)
        self.screenshot('c-phase1-dark-keyboard-minimum-width')
        measurements.append({'kind': 'dark minimum width', 'styles': dark_styles})
        self.assertEqual(self.current('existing-chat')['case']['id'], first_case['id'])
        self.assertEqual(self.current('existing-chat')['case']['jobs']['db-j']['attempt'], 0)
        self.assertEqual(self.server.completions, [])
        self.save_visual_measurements('c-phase1-responsive-layouts', measurements)


if __name__ == '__main__':
    unittest.main()
