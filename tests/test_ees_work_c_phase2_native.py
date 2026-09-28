"""C phase 2 interactions in the packaged Native UI and real workflow service.

The browser, public EES HTTP routes, validators, scheduler, projection and
temporary SQLite store are real. Native login/chat and external HTTP/model
responses use the existing synthetic fixture. This is not company acceptance.
"""
import asyncio
from copy import deepcopy
import json
import threading
import time
import unittest
from unittest.mock import patch

import test_ees_work_demo as native
import test_ees_workflow_execution as runtime


class CPhaseTwoNativeTests(unittest.TestCase):
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
    open_category = native.EESWorkNativeBrowserTests.open_category
    choose = native.EESWorkNativeBrowserTests.choose
    seed_case = native.EESWorkNativeBrowserTests.seed_case
    seed_large_case = native.EESWorkNativeBrowserTests.seed_large_case
    screenshot = native.EESWorkNativeBrowserTests.screenshot
    visual_style = native.EESWorkNativeBrowserTests.visual_style
    save_visual_measurements = native.EESWorkNativeBrowserTests.save_visual_measurements

    def ready(self, fragment=None):
        self.bridge, self.model = runtime.Bridge(), runtime.Model()
        self.server.workflow.execution.bridge = self.bridge
        self.server.workflow.execution.model = self.model
        definition = deepcopy(self.current()['catalog'])
        process_id = 'setup-p'
        if fragment:
            process_id = fragment['process_id']
            definition['nodes'].update(fragment['nodes'])
            definition['roots'][fragment['nodes'][process_id]['category']].append(process_id)
            self.publish_runtime_fixture(definition)
        result = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            'action': 'create', 'chat_id': 'existing-chat',
            'payload': {'site_id': 'us-a', 'system': 'EMS', 'process_id': process_id}}))
        self.assertTrue(result['ok'], result)
        self.case_id = result['case']['id']
        self.navigate('/c/existing-chat')
        self.wait_scope_ready('site')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        return result['case']

    def run_state(self):
        result = asyncio.run(self.server.workflow.execution_state(self.server.user, case_id=self.case_id))
        self.assertTrue(result['ok'], result)
        return result['run']

    def settle(self):
        self.wait("!!document.querySelector('#ees-work-panel') && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")

    def drain(self):
        async def work():
            for _ in range(30):
                if not await self.server.workflow.execution.process_once():
                    break
        asyncio.run(work())
        return self.run_state()

    def refresh_runtime(self, expected):
        self.click('[data-action="execution_refresh"]')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === " + json.dumps(expected))
        self.settle()

    def start(self, node_id, inputs=None):
        self.choose(node_id)
        self.assertIsNone(self.read('#ees-work-inputs-save'), 'Native execution must not acquire a fake legacy save')
        self.click('#ees-work-run')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        for key, value in (inputs or {}).items():
            self.fill('#ees-runtime-input-form [name=' + json.dumps(key) + ']', value)
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'queued'")
        self.settle()
        return self.run_state()

    def control(self, action, confirm=False):
        self.click('[data-runtime-action="' + action + '"]')
        if confirm:
            self.wait("document.querySelector('#ees-work-dialog')?.open")
            self.click('#ees-work-dialog [data-dialog-confirm]')
        self.settle()

    def action_layout(self, label, expected_regions=1):
        result = self.browser.evaluate("""(()=>{const regions=[...document.querySelectorAll('.ew-work-action-region')]
            .filter(e=>e.getClientRects().length),r=regions[0],box=r?.getBoundingClientRect();
            const controls=r?[...r.querySelectorAll('button')].filter(e=>e.getClientRects().length):[];
            return {viewport:[innerWidth,innerHeight],regions:regions.length,
                placement:r?.closest('#ees-work-action-dock')?'dock':'inline',
                rect:box?.toJSON(),pageWidth:document.documentElement.scrollWidth,
                panel:document.querySelector('#ees-work-panel')?.getBoundingClientRect().toJSON(),
                chat:document.querySelector('#chat-pane')?.getBoundingClientRect().toJSON(),
                composer:document.querySelector('#chat-input')?.getBoundingClientRect().toJSON(),
                controls:controls.map(e=>{const a=e.getBoundingClientRect();return{text:e.textContent,
                    action:e.dataset.runtimeAction||e.dataset.action,disabled:e.disabled,rect:a.toJSON(),
                    hit:e.contains(document.elementFromPoint(a.x+a.width/2,a.y+a.height/2))};})};})()""")
        self.save_visual_measurements('c-phase2-' + label + '-layout', result)
        self.screenshot('c-phase2-' + label)
        self.assertEqual(result['regions'], expected_regions, result)
        self.assertLessEqual(result['pageWidth'], result['viewport'][0] + 1, result)
        if expected_regions:
            self.assertTrue(result['controls'], result)
        for control in result['controls']:
            self.assertGreaterEqual(control['rect']['left'], result['panel']['left'], control)
            self.assertLessEqual(control['rect']['right'], result['panel']['right'] + 1, control)
        return result

    def evidence(self, label, **extra):
        run = self.run_state()
        self.save_visual_measurements('c-phase2-' + label + '-service', {
            'boundary': 'Packaged Native UI + real WorkflowService/SQLite; synthetic login/chat, external HTTP and model responses',
            'run': run, 'case': self.current()['case'], 'external_calls': self.bridge.calls,
            'model_calls': self.model.calls, **extra})

    def test_native_fixed_scope_pause_reconnect_grounded_ai_and_c_actions(self):
        self.ready(runtime.examples.operations_workflow(runtime.REFERENCES, 'fixture-model'))
        inputs = {'project_key': 'TEST', 'repository': 'team/example', 'ops_page_id': '42'}
        initial = self.start('new-operations-read-t', inputs)
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(initial['inputs'], inputs)
        self.action_layout('fixed-queued')
        self.control('pause')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'paused'")
        self.browser.events.clear()
        self.browser.call('Page.reload')
        deadline = time.monotonic() + 15
        while not any(event.get('method') == 'Page.loadEventFired' for event in self.browser.events):
            self.browser.events.append(self.browser.receive(deadline))
        self.wait_scope_ready('site')
        if self.read('#sidebar', 'getBoundingClientRect().width') < 200:
            self.click('button[aria-label="사이드바 열기"]')
        self.wait("document.querySelector('#sidebar')?.getBoundingClientRect().width > 200")
        self.choose('new-operations-read-t')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'paused'")
        self.control('inputs')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        for key, value in inputs.items():
            self.assertEqual(self.read('#ees-runtime-input-form [name=' + json.dumps(key) + ']', 'value'), value)
        self.key('Escape', 27)
        self.control('resume')
        # Hold only the synthetic external response. The worker, running call
        # record, HTTP state polling and browser navigation remain real.
        started, release = threading.Event(), threading.Event()
        original_invoke = self.bridge.invoke
        worker_result = {}

        async def held_call(*args, **kwargs):
            if not started.is_set():
                started.set()
                if not await asyncio.to_thread(release.wait, 8):
                    raise RuntimeError('Browser did not release the held synthetic response')
            return await original_invoke(*args, **kwargs)

        def worker():
            try:
                worker_result['run'] = self.drain()
            except Exception as error:
                worker_result['error'] = error

        self.bridge.invoke = held_call
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(5), 'The existing worker did not dispatch the first call')
            self.refresh_runtime('running')
            self.choose('new-operations-jira-j')
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'running'")
            self.click('#ees-work-close')
            self.click('#ees-work-context-open')
            inflight = self.run_state()
            self.assertEqual(inflight['status'], 'running')
            self.assertEqual(inflight['id'], initial['id'])
            self.action_layout('native-running-move-reopened')
        finally:
            release.set()
            thread.join(timeout=5)
            self.bridge.invoke = original_invoke
        self.assertFalse(thread.is_alive(), 'The bounded synthetic worker must finish')
        if 'error' in worker_result:
            raise worker_result['error']
        finished = worker_result['run']
        self.assertEqual(finished['status'], 'succeeded', finished)
        self.assertEqual(len(self.bridge.calls), 3)
        self.assertEqual(self.model.calls, [])
        self.refresh_runtime('succeeded')
        self.action_layout('fixed-completed')
        self.assertEqual(self.text('.ew-work-action-region [data-action=panel_parent]'), '단계로 돌아가기')
        self.click('.ew-work-action-region [data-action=panel_parent]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '자료 조회'")
        self.assertEqual(self.current()['case']['progress'], {'done': 3, 'total': 4})
        self.start('new-operations-p')  # T results are reused; only the AI J remains.
        completed = self.drain()
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertEqual(len(self.bridge.calls), 3)
        self.assertEqual(len(self.model.calls), 1)
        self.refresh_runtime('succeeded')
        self.choose('new-operations-summary-j')
        self.assertEqual(self.current()['case']['status'], 'passed')
        self.assertEqual(self.current()['case']['progress'], {'done': 4, 'total': 4})
        observations = self.browser.evaluate("[...document.querySelectorAll('[data-runtime-observation]')].map(e=>(e.closest('section')?.querySelector('h4')?.innerText||'')+' · '+e.innerText)")
        self.assertEqual(len(observations), 6, observations)
        for source, field in [('Jira 현황', '전체'), ('Jira 현황', '열림'), ('GitHub PR 목록', '반환'),
                              ('GitHub PR 목록', '다음 페이지'), ('운영 기준 문서', '제목'), ('운영 기준 문서', '버전')]:
            self.assertTrue(any(source in text and field in text for text in observations), (source, field, observations))
        self.action_layout('ai-completed')
        self.evidence('fixed-ai', saved_inputs=inputs, fixed_model_calls=0, ai_model_calls=1,
                      actual_running_during_navigation=inflight, displayed_observations=observations)

    def test_native_candidate_input_wait_save_and_explicit_resume(self):
        self.ready(runtime.examples.installation_docs_workflow(runtime.REFERENCES))
        self.bridge.results['search_pages'] = runtime.envelope({'results': [
            {'page_id': '41', 'title': '합성 설치 후보 A'}, {'page_id': '42', 'title': '합성 설치 후보 B'}]})
        self.start('new-documents-p', {'query': '설치 문서', 'space_key': 'TEAM'})
        waiting = self.drain()
        self.assertEqual(waiting['status'], 'waiting_input', waiting)
        self.refresh_runtime('waiting_input')
        self.action_layout('candidate-wait')
        self.control('inputs')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.click('[data-candidate-id="42"]')
        self.assertEqual(self.read('#ees-runtime-input-form [name=page_id]', 'value'), '42')
        self.screenshot('c-phase2-candidate-picker')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')?.open && "
                  "[...document.querySelectorAll('[data-work-section=runtime-inputs] .ew-work-target-row p')]"
                  ".some(e=>e.textContent==='42')")
        self.settle()
        saved = self.run_state()
        self.assertEqual(saved['inputs']['page_id'], '42')
        self.assertEqual(saved['status'], 'waiting_input', 'Input save must not silently resume')
        self.assertEqual(len(self.bridge.calls), 1)
        original = deepcopy(saved['calls'][0])
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.control('resume')
        completed = self.drain()
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertEqual(completed['calls'][0], original, 'Supplementing current inputs must retain search snapshot')
        self.assertEqual([call['function'] for call in self.bridge.calls], ['search_pages', 'get_page'])
        self.assertEqual(self.bridge.calls[-1]['arguments']['page_id'], '42')
        self.refresh_runtime('succeeded')
        self.choose('new-documents-page-j')
        self.action_layout('candidate-completed')
        self.choose('new-documents-search-j')
        self.click('.ew-work-runtime-detail [data-work-overlay]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        displayed = self.browser.evaluate("""(()=>{const root=document.querySelector('#ees-work-dialog');
            const current=[...root.querySelectorAll('h4')].find(e=>e.textContent==='현재 실행 입력');
            const snapshot=[...root.querySelectorAll('h5')].find(e=>e.textContent.includes('호출 당시 snapshot'));
            return {current:JSON.parse(current.nextElementSibling.textContent),
                snapshot:JSON.parse(snapshot.nextElementSibling.textContent)};})()""")
        self.assertEqual(displayed['current'], completed['inputs'])
        self.assertEqual(displayed['snapshot'], original['arguments'])
        self.assertNotIn('page_id', displayed['snapshot'])
        self.assertEqual(displayed['current']['page_id'], '42')
        self.screenshot('c-phase2-current-input-versus-call-snapshot')
        self.key('Escape', 27)
        self.evidence('candidate', saved_before_resume=saved)

    def test_native_human_confirmation_no_tool_call_and_explicit_resume(self):
        fragment = runtime.examples.installation_docs_workflow(runtime.REFERENCES)
        fragment['nodes']['new-documents-page-j']['execution'] = {
            'protocol': 1, 'kind': 'human', 'calls': [],
            'completion': {'validator': 'selection_v1', 'version': 1, 'input_key': 'page_id', 'choices': {
                'job_id': 'new-documents-search-j', 'call_id': 'search', 'path': ['data', 'results'], 'value_path': ['page_id']}},
            'limits': {'timeout_seconds': 30, 'max_tool_calls': 0, 'max_model_calls': 0, 'max_retries': 0}}
        self.ready(fragment)
        self.bridge.results['search_pages'] = runtime.envelope({'results': [{'page_id': '42', 'title': '합성 승인 후보'}]})
        self.start('new-documents-p', {'query': '설치', 'space_key': 'TEAM', 'page_id': '42'})
        waiting = self.drain()
        self.assertEqual(waiting['status'], 'waiting_input', waiting)
        self.refresh_runtime('waiting_input')
        self.choose('new-documents-page-j')
        self.assertIsNone(self.read('#ees-work-inputs-save'))
        self.action_layout('human-confirmation')
        self.control('confirm', confirm=True)
        confirmed = self.run_state()
        self.assertEqual(confirmed['jobs']['new-documents-page-j']['status'], 'succeeded')
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertEqual(self.model.calls, [])
        if confirmed['status'] != 'succeeded':
            self.control('resume')
            confirmed = self.drain()
        self.assertEqual(confirmed['status'], 'succeeded', confirmed)
        self.refresh_runtime('succeeded')
        self.evidence('human')

    def test_unknown_has_no_mutation_or_automatic_repeat(self):
        self.ready(runtime.examples.operations_workflow(runtime.REFERENCES, 'fixture-model'))
        self.bridge.results['jira_dashboard'] = runtime.envelope(status='unknown')
        self.start('new-operations-jira-j', {'project_key': 'TEST', 'repository': 'team/example', 'ops_page_id': '42'})
        unknown = self.drain()
        self.assertEqual(unknown['status'], 'unknown', unknown)
        self.refresh_runtime('unknown')
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-runtime-action]').length"), 0,
                         'UNKNOWN is reconciled externally; no resume/cancel/automatic rerun')
        self.assertEqual(self.current()['case']['progress']['done'], 0)
        self.action_layout('unknown', expected_regions=0)
        before = deepcopy(self.bridge.calls)
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.refresh_runtime('unknown')
        self.assertEqual(self.bridge.calls, before)
        self.evidence('unknown')

    def test_native_permission_wait_revocation_and_open_detail_lookup_failure(self):
        self.ready(runtime.examples.installation_docs_workflow(runtime.REFERENCES))
        marker = 'SYNTHETIC-PRIVATE-RESULT-PHASE2'
        self.bridge.results['search_pages'] = runtime.envelope({'results': [{'page_id': '42', 'title': marker}]})
        self.start('new-documents-search-j', {'query': '설치', 'space_key': 'TEAM'})
        original_check = self.bridge.check

        async def denied(*args, **kwargs):
            raise self.backend.WorkflowError('native_access_denied', '합성 현재 권한 회수')

        self.bridge.check = denied
        waiting = self.drain()
        self.assertEqual(waiting['status'], 'waiting_authorization', waiting)
        self.assertEqual(self.bridge.calls, [])
        self.refresh_runtime('waiting_authorization')
        self.action_layout('permission-wait')
        self.assertNotIn(marker, self.text('#ees-work-panel'))
        self.bridge.check = original_check
        self.control('resume')
        completed = self.drain()
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.refresh_runtime('succeeded')
        self.click('.ew-work-runtime-detail [data-work-overlay]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn(marker, self.text('#ees-work-dialog'))

        async def lookup_failed(*args, **kwargs):
            return {'ok': False, 'error': {'code': 'state_read_failed', 'message': '합성 실행 기록 조회 실패'}}

        with patch.object(self.server.workflow, 'execution_state', lookup_failed):
            self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'lookup-failed'")
            self.assertNotIn(marker, self.text('#ees-work-dialog'))
            self.assertIsNone(self.read('[data-runtime-action]'))
            self.assertNotIn(marker, self.text('#ees-work-panel'))
            self.screenshot('c-phase2-native-detail-lookup-failed')
        if self.read('#ees-work-dialog', 'open'):
            self.key('Escape', 27)
        self.refresh_runtime('succeeded')
        self.click('.ew-work-runtime-detail [data-work-overlay]')
        self.assertIn(marker, self.text('#ees-work-dialog'))
        with patch.object(self.server.workflow, 'get_state', lookup_failed):
            self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
            self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('합성 실행 기록 조회 실패')")
            self.assertNotIn(marker, self.text('#ees-work-dialog'))
            self.assertNotIn(marker, self.text('#ees-work-panel'))
            self.screenshot('c-phase2-native-case-lookup-failed')
        if self.read('#ees-work-dialog', 'open'):
            self.key('Escape', 27)
        self.refresh_runtime('succeeded')  # Same run revision: visible retry must recover the failed case read.
        self.click('.ew-work-runtime-detail [data-work-overlay]')
        self.assertIn(marker, self.text('#ees-work-dialog'))
        self.bridge.check = denied
        self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
        self.wait("document.querySelector('#ees-work-content')?.innerText.includes('현재 권한으로 결과 근거를 볼 수 없습니다')")
        immediate = self.browser.evaluate("""(()=>{const dialog=document.querySelector('#ees-work-dialog');
            return {open:!!dialog?.open,visible:!!dialog?.getClientRects().length,
                retainedMarker:!!dialog?.textContent.includes('SYNTHETIC-PRIVATE-RESULT-PHASE2')};})()""")
        self.save_visual_measurements('c-phase2-revocation-immediate-dialog', immediate)
        self.assertFalse(immediate['open'] or immediate['visible'], immediate)
        self.assertFalse(immediate['retainedMarker'], immediate)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertNotIn(marker, self.text('#ees-work-dialog'))
        if self.read('#ees-work-dialog', 'open'):
            self.key('Escape', 27)
        self.click('.ew-work-runtime-detail [data-work-overlay]')
        self.assertNotIn(marker, self.text('#ees-work-dialog'))
        self.assertIn('현재 권한으로', self.text('#ees-work-dialog'))
        redacted = self.run_state()
        self.assertFalse(redacted['evidence_available'])
        self.assertNotIn('result', redacted['calls'][0])
        self.screenshot('c-phase2-native-detail-access-restricted')
        self.save_visual_measurements('c-phase2-permission-lookup-service', {
            'boundary': 'Current ACL deny is injected at existing bridge check; real runtime and public state redaction',
            'waiting': waiting, 'redacted': redacted, 'calls': len(self.bridge.calls),
            'open_overlay_cleared_on_lookup_failure_and_revocation': True})

    def test_native_partial_and_failed_results_are_not_scope_completion(self):
        self.ready(runtime.examples.installation_docs_workflow(runtime.REFERENCES))
        self.bridge.results['search_pages'] = {**runtime.envelope({'results': [{'page_id': '42'}]}, completeness='partial'),
                                               'scope': 'single_page'}
        self.start('new-documents-search-j', {'query': '설치', 'space_key': 'TEAM'})
        partial = self.drain()
        self.assertEqual(partial['status'], 'succeeded', partial)
        self.refresh_runtime('succeeded')
        self.assertIn('일부 범위 결과', self.text('#ees-work-content'))
        self.assertEqual(self.read('[data-work-criterion-status]', 'dataset.workCriterionStatus'), 'passed',
                         'observed_v1 allows a bounded observation J while full-scope completion remains separate')
        self.assertNotEqual(self.current()['case']['status'], 'passed')
        self.screenshot('c-phase2-native-partial-result')
        self.choose('new-documents-p')
        self.assertNotEqual(self.read('[data-work-criterion-status]', 'dataset.workCriterionStatus'), 'passed')
        self.bridge.results['get_page'] = runtime.envelope(status='failed')
        self.start('new-documents-page-j', {'page_id': '42'})
        failed = self.drain()
        self.assertEqual(failed['status'], 'failed', failed)
        self.refresh_runtime('failed')
        self.assertNotEqual(self.current()['case']['status'], 'passed')
        self.action_layout('native-failed')
        failed_call = deepcopy(failed['calls'][0])
        self.bridge.results['get_page'] = runtime.envelope()
        self.start('new-documents-page-j')
        retried = self.drain()
        self.assertEqual(retried['status'], 'succeeded', retried)
        self.assertNotEqual(retried['id'], failed['id'], 'A failed run is preserved; an explicit new plan creates the next run')
        previous = asyncio.run(self.server.workflow.execution_state(self.server.user, run_id=failed['id']))['run']
        self.assertEqual(previous['status'], 'failed')
        self.assertEqual(previous['calls'][0], failed_call)
        self.refresh_runtime('succeeded')
        self.action_layout('native-failed-new-plan-completed')
        self.evidence('partial-failed', partial_run=partial, preserved_failed_run=previous)

    def test_three_sizes_long_native_inputs_dark_narrow_keyboard_and_cancel(self):
        fragment = runtime.examples.installation_docs_workflow(runtime.REFERENCES)
        fragment['nodes']['new-documents-search-j']['name'] = ('설치 지침을 확인하는 긴 작업 이름과 공개 조회 대상 ' * 7)[:160]
        fragment['nodes']['new-documents-search-j']['description'] = '현장 문서의 적용 범위와 남은 조건을 확인합니다. ' * 20
        fragment['nodes']['new-documents-search-j']['instructions'] = '저장된 조회 범위를 확인하고 근거가 없는 결과를 생성하지 않습니다. ' * 40
        self.ready(fragment)
        query = '합성 설치 문서 검색어 ' * 12
        rows = []
        for width, height in ((1920, 1080), (1536, 960), (1366, 768)):
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            self.choose('new-documents-search-j')
            layout = self.action_layout('native-long-' + str(width))
            self.assertLessEqual(layout['chat']['right'], layout['panel']['left'] + 1)
            self.assertLessEqual(layout['composer']['bottom'], height)
            self.start('new-documents-search-j', {'query': query, 'space_key': 'TEAM'})
            self.assertEqual(self.run_state()['inputs']['query'], query)
            self.action_layout('native-queued-' + str(width))
            self.control('cancel', confirm=True)
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'cancelled'")
            cancelled = self.run_state()
            self.assertEqual(cancelled['status'], 'cancelled')
            self.assertEqual(cancelled['calls'], [])
            self.assertEqual(self.current()['case']['progress']['done'], 0)
            rows.append({'viewport': [width, height], 'layout': layout, 'run': cancelled})
        self.browser.evaluate("document.querySelector('#ees-work-resizer').focus()")
        self.key('Home', 36)
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), 340, delta=1)
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), 340, delta=1)
        self.browser.evaluate("document.documentElement.classList.add('dark')")
        self.browser.evaluate("Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))")
        identity = self.read('#ees-work-identity-slot', 'getBoundingClientRect().toJSON()')
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
            'x': identity['x'] + identity['width'] / 2, 'y': identity['y'] + identity['height'] / 2,
            'deltaX': 0, 'deltaY': 500})
        self.wait("document.querySelector('#ees-work-identity-slot').scrollTop > 0")
        self.assertGreaterEqual(self.read('#ees-work-content', 'clientHeight'), 120)
        self.click('#ees-work-run')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertEqual(self.read('#ees-runtime-input-form [name=query]', 'value'), query)
        self.fill('#ees-runtime-input-form [name=space_key]', 'TEAM')
        for _ in range(12):
            if self.browser.evaluate("document.activeElement?.matches('#ees-work-dialog [data-dialog-confirm]')"):
                break
            self.key('Tab', 9)
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('#ees-work-dialog [data-dialog-confirm]:focus-visible')"))
        style = self.visual_style('#ees-work-dialog [data-dialog-confirm]')
        self.assertGreaterEqual(style['contrast'], 4.5)
        self.assertGreaterEqual(style['outlineWidth'], 2)
        self.screenshot('c-phase2-native-dark-keyboard')
        self.key('Enter', 13, text='\r')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'queued'")
        self.action_layout('native-dark-narrow-queued')
        self.control('cancel', confirm=True)
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'cancelled'")
        self.assertEqual(self.bridge.calls, [])
        self.save_visual_measurements('c-phase2-responsive-native-service', {
            'boundary': 'Real plan/start/cancel APIs and SQLite; no external dispatch. Native theme/resizer and keyboard used.',
            'sizes': rows, 'dark_focus': style, 'final': self.run_state()})

    def test_legacy_manual_and_draft_keep_distinct_save_confirmation(self):
        definition = deepcopy(self.current()['catalog'])
        definition['nodes']['install-j']['mode'] = 'draft'
        definition['nodes']['install-j']['deps'] = []
        self.publish_runtime_fixture(definition)
        self.ready()
        self.choose('scope-j')
        self.assertIsNone(self.read('#ees-work-inputs'))
        self.assertIsNone(self.read('#ees-work-inputs-save'))
        self.action_layout('legacy-manual')
        self.click('#ees-work-run', confirm=False)
        self.assertEqual(self.current()['case']['jobs']['scope-j']['attempt'], 0)
        self.click('#ees-work-run', confirm=True)
        self.settle()
        self.assertEqual(self.current()['case']['jobs']['scope-j']['status'], 'passed')
        self.choose('install-j')
        self.assertIsNone(self.read('#ees-work-inputs-save'))
        document = '검토할 합성 업무 초안 · 현장 적용 범위와 남은 조건을 담당자가 확인합니다. ' * 20
        self.fill('#ees-work-document textarea', document)
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        self.click('button[form="ees-work-document"]')
        self.settle()
        before = deepcopy(self.current()['case']['jobs']['install-j'])
        self.assertEqual(before['document'], document)
        self.assertNotEqual(before['status'], 'passed')
        self.action_layout('legacy-draft-review')
        self.click('#ees-work-run', confirm=True)
        self.settle()
        done = self.current()['case']['jobs']['install-j']
        self.assertEqual(done['status'], 'passed')
        self.assertEqual(done['history'][-1]['document'], document)
        self.assertEqual(done['history'][-1]['kind'], 'human_confirmation')
        self.assertEqual(done['history'][-1]['checks'], [])
        self.screenshot('c-phase2-legacy-draft-completed')
        self.save_visual_measurements('c-phase2-legacy-human-service', {
            'boundary': 'Real service/SQLite and packaged UI; manual confirmation and draft only, no tool or model',
            'before_confirmation': before, 'after_confirmation': done})

    def test_legacy_scope_unconnected_excluded_and_empty_saved_input(self):
        # The already-supported scope contract is directly affected by moving
        # its action region. Reuse its meaningful service/history assertions.
        native.EESWorkNativeBrowserTests.test_management_scope_run_excludes_human_retry_and_marks_unconnected_unperformed(self)
        self.action_layout('legacy-unconnected')
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        before = deepcopy(self.current()['case']['jobs'])
        self.choose('bulk-004-j')
        self.assertIn('적용 제외', self.text('#ees-work-content'))
        self.assertIsNone(self.read('#ees-work-run'))
        self.assertEqual(self.current()['case']['jobs'], before)
        self.screenshot('c-phase2-legacy-excluded')
        self.choose('bulk-052-j')
        history = deepcopy(self.current()['case']['jobs']['bulk-052-j']['history'])
        if self.read('.ew-work-edit', 'open') is False:
            self.click('.ew-work-edit > summary')
        self.fill('#ees-work-inputs [name=db]', '')
        self.click('#ees-work-inputs-save')
        self.settle()
        self.assertEqual(self.current()['case']['jobs']['bulk-052-j']['inputs']['db'], '')
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        self.assertEqual(self.current()['case']['jobs']['bulk-052-j']['history'], history)
        self.assertIn('입력', self.text('#ees-work-content'))
        self.screenshot('c-phase2-legacy-input-required')
        self.save_visual_measurements('c-phase2-legacy-exceptions-service', {
            'boundary': 'Existing real legacy simulation scope and public input service; no external tool calls',
            'unconnected': self.current()['case']['jobs']['bulk-005-j'],
            'empty_input': self.current()['case']['jobs']['bulk-052-j'],
            'excluded': self.current()['case']['jobs']['bulk-004-j']})

    def test_legacy_prerequisite_wait_does_not_run(self):
        before = self.ready()
        self.choose('db-j')
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        self.assertIn('선행', self.text('#ees-work-content'))
        self.action_layout('legacy-prerequisite-wait')
        self.assertEqual(self.current()['case']['jobs'], before['jobs'])

    def test_mixed_scope_keeps_child_paths_and_blocks_legacy_writes_during_native_run(self):
        fragment = runtime.examples.installation_docs_workflow(runtime.REFERENCES)
        legacy = deepcopy(self.current()['catalog']['nodes']['db-j'])
        legacy.update(id='mixed-legacy-j', name='기존 모의 점검 유지', parent='new-documents-t', deps=[])
        fragment['nodes'][legacy['id']] = legacy
        fragment['nodes']['new-documents-t']['children'].append(legacy['id'])
        self.ready(fragment)
        self.choose('new-documents-p')
        self.assertIsNone(self.read('#ees-work-run'), 'Mixed scopes cannot turn legacy work into Native execution')
        self.start('new-documents-search-j', {'query': '설치', 'space_key': 'TEAM'})
        self.choose(legacy['id'])
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
        self.assertTrue(self.read('#ees-work-inputs-save', 'disabled'))
        value = '실행 중 보존할 합성 기존 입력'
        self.fill('#ees-work-inputs [name=db]', value)
        self.assertTrue(self.read('#ees-work-inputs-save', 'disabled'))
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.assertEqual(self.read('#ees-work-inputs [name=db]', 'value'), value)
        self.assertEqual(self.current()['case']['jobs'][legacy['id']]['inputs'], {})
        self.screenshot('c-phase2-mixed-legacy-write-blocked')
        self.choose('new-documents-search-j')
        self.control('cancel', confirm=True)
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'cancelled'")
        self.choose(legacy['id'])
        self.assertEqual(self.read('#ees-work-inputs [name=db]', 'value'), value)
        self.click('#ees-work-inputs-save')
        self.settle()
        self.assertEqual(self.current()['case']['jobs'][legacy['id']]['inputs']['db'], value)
        self.click('#ees-work-run')
        self.settle()
        case = self.current()['case']
        self.assertEqual(case['jobs'][legacy['id']]['status'], 'passed')
        self.assertNotEqual(case['jobs']['new-documents-search-j']['status'], 'passed')
        self.assertEqual(self.bridge.calls, [])
        self.screenshot('c-phase2-mixed-legacy-restored')
        self.evidence('mixed-scope', legacy_saved=value, separate_simulation=True)

    def test_completed_process_lookup_failure_offers_only_one_read_retry(self):
        self.ready(runtime.examples.operations_workflow(runtime.REFERENCES, 'fixture-model'))
        plan = asyncio.run(self.server.workflow.execution_plan(self.server.user, {
            'case_id': self.case_id, 'node_id': 'new-operations-p',
            'inputs': {'project_key': 'TEST', 'repository': 'team/example', 'ops_page_id': '42'}}))
        self.assertTrue(plan['ok'], plan)
        started = asyncio.run(self.server.workflow.execution_action(self.server.user, {
            'action': 'start', 'plan_id': plan['plan']['id'], 'plan_hash': plan['plan']['hash'],
            'request_id': 'completed-p-browser-arrangement'}))
        self.assertTrue(started['ok'], started)
        self.assertEqual(self.drain()['status'], 'succeeded')
        self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
        self.choose('new-operations-p')
        self.wait("document.querySelector('[data-action=start_case]')")
        self.action_layout('native-process-completed')

        async def lookup_failed(*args, **kwargs):
            return {'ok': False, 'error': {'code': 'state_read_failed', 'message': '합성 완료 업무 조회 실패'}}

        with patch.object(self.server.workflow, 'get_state', lookup_failed):
            self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'lookup-failed'")
            self.assertIsNone(self.read('[data-action=start_case]'))
            self.assertIsNone(self.read('[data-runtime-action]'))
            self.action_layout('completed-process-lookup-failed')
        self.refresh_runtime('succeeded')
        self.assertIsNotNone(self.read('[data-action=start_case]'))
        self.evidence('completed-process-recovered', single_retry=True)

    def open_past_case(self, case_id):
        if not self.read('.ew-panel-menu', 'open'):
            self.click('.ew-panel-menu > summary')
        self.click('#ees-work-run-view [data-action="history_view"]')
        selector = '[data-action="history_case"][data-case-id=' + json.dumps(case_id) + ']'
        self.wait('!!document.querySelector(' + json.dumps(selector) + ')')
        self.click(selector)
        self.wait("document.querySelector('#ees-work-content')?.innerText.includes('읽기 전용')")
        if self.read('.ew-panel-menu', 'open'):
            self.click('.ew-panel-menu > summary')
        self.settle()

    def arrange_history_run(self, result_status='succeeded', partial=False, historical_failed_final=False):
        fragment = runtime.examples.operations_workflow(runtime.REFERENCES, 'fixture-model')
        fragment['nodes']['new-operations-read-t']['rule'] = '저장 당시 T 완료 기준 · 자료 3종의 검증'
        fragment['nodes']['new-operations-jira-j']['rule'] = '저장 당시 J 완료 기준 · 조회 응답 검증'
        self.ready(fragment)
        created = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            'action': 'create', 'payload': {'site_id': 'us-a', 'system': 'EMS',
                'process_id': fragment['process_id']}}))
        self.assertTrue(created['ok'], created)
        past_id = created['case']['id']
        self.bridge.results['jira_dashboard'] = runtime.envelope(
            status=result_status, completeness='partial' if partial else 'complete')
        if partial:
            self.bridge.results['jira_dashboard']['scope'] = 'single_page'
        plan = asyncio.run(self.server.workflow.execution_plan(self.server.user, {
            'case_id': past_id, 'node_id': 'new-operations-read-t',
            'inputs': {'project_key': 'HISTORY', 'repository': 'team/saved', 'ops_page_id': '42'}}))
        self.assertTrue(plan['ok'], plan)
        started = asyncio.run(self.server.workflow.execution_action(self.server.user, {
            'action': 'start', 'plan_id': plan['plan']['id'], 'plan_hash': plan['plan']['hash'],
            'request_id': 'history-review-' + result_status}))
        self.assertTrue(started['ok'], started)
        self.drain()
        saved = asyncio.run(self.server.workflow.execution_state(self.server.user, case_id=past_id))['run']
        if historical_failed_final:
            # Current workers stop at a failed call before final validation.
            # Exercise compatibility with an already stored final failure,
            # explicitly arranging that historical record in this temp DB.
            # This is not evidence that today's scheduler emits this record.
            with self.server.workflow._db(write=True) as db:
                row = db.execute('SELECT data FROM execution_runs WHERE id=?', (saved['id'],)).fetchone()
                record = json.loads(row['data'])
                record['final_validation'] = {'status': 'failed', 'validator': 'all_required_v1',
                    'version': 1, 'reason': 'required_jobs_incomplete', 'scope_complete': False,
                    'evidence': [], 'output': {}}
                db.execute('UPDATE execution_runs SET data=? WHERE id=?',
                           (json.dumps(record, ensure_ascii=False), saved['id']))
            saved = asyncio.run(self.server.workflow.execution_state(self.server.user, case_id=past_id))['run']
        past = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=past_id))['case']
        # The current catalog changes after this case was saved. Historical
        # rule/title must still come from the case's pinned definition.
        definition = deepcopy(self.current()['catalog'])
        definition['nodes']['new-operations-read-t']['rule'] = '현재 게시 기준 · 과거와 다름'
        definition['nodes']['new-operations-jira-j']['rule'] = '현재 게시 J 기준 · 과거와 다름'
        self.publish_runtime_fixture(definition)
        self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
        self.choose('new-operations-p')
        self.open_past_case(past_id)
        self.wait("!!document.querySelector('[data-runtime-record]')")
        self.browser.evaluate("document.querySelector('[data-runtime-record]').scrollIntoView({block:'start'})")
        return saved, past

    def check_history_final(self, status):
        saved, past = self.arrange_history_run(status, historical_failed_final=status == 'failed')
        runtime_selector = '#ees-work-content [data-runtime-record]'
        displayed = self.browser.evaluate("(()=>{const e=document.querySelector(" + json.dumps(runtime_selector) + ");"
            "return {record:e?.dataset.runtimeRecord,criterion:e?.querySelector('[data-work-criterion-status]')?.dataset.workCriterionStatus,"
            "text:e?.innerText,mutations:document.querySelectorAll('#ees-work-content [data-mutation]').length,"
            "parentJobs:document.querySelector('#ees-work-content [data-work-metric=jobs]')?.innerText,"
            "parentStages:document.querySelector('#ees-work-content [data-work-metric=stages]')?.innerText};})()")
        before = deepcopy(self.current()['case'])
        self.save_visual_measurements('c-phase2-review-history-' + status, {
            'boundary': 'Actual packaged Native frontend; more -> execution history -> past case; real service/SQLite with synthetic HTTP results',
            'historical_failed_final_fixture': status == 'failed',
            'failed_final_boundary': 'Persisted compatibility fixture only; current worker call failure has no final_validation' if status == 'failed' else None,
            'saved_run': saved, 'saved_case': past, 'current_case': before, 'displayed': displayed})
        self.screenshot('c-phase2-review-history-' + status)
        self.assertEqual(saved['status'], status)
        self.assertEqual(displayed['record'], status)
        validation = saved['final_validation']
        expected = 'passed' if validation['status'] == 'succeeded' else 'failed'
        self.assertEqual(displayed['criterion'], expected, displayed)
        self.assertIn('저장 당시 T 완료 기준', displayed['text'])
        self.assertNotIn('현재 게시 기준', displayed['text'])
        self.assertEqual(displayed['mutations'], 0)
        self.assertIsNone(self.read('#ees-work-content [data-action=panel_parent]'))
        self.assertNotEqual(past['status'], 'passed', 'Succeeded child T must not complete its parent P')
        self.assertEqual(past['progress']['done'], 3 if status == 'succeeded' else 0)
        if status == 'succeeded':
            self.assertIn('3 / 4', displayed['parentJobs'])
            self.assertIn('1 / 2', displayed['parentStages'])
        self.click('#ees-work-content .ew-work-runtime-detail [data-work-overlay]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn(json.dumps(validation, ensure_ascii=False, indent=2), self.text('#ees-work-dialog'))
        self.screenshot('c-phase2-review-history-' + status + '-saved-detail')
        self.key('Escape', 27)
        self.assertEqual(self.current()['case'], before, 'History must not mutate the current case')

    def test_past_native_success_uses_saved_target_definition_and_final_validation(self):
        self.check_history_final('succeeded')

    def test_past_native_failure_uses_saved_final_validation(self):
        self.check_history_final('failed')

    def test_past_failed_scope_without_final_validation_remains_unjudged(self):
        saved, past = self.arrange_history_run('failed')
        self.assertNotIn('final_validation', saved)
        self.assertEqual(saved['status'], 'failed')
        self.assertEqual(self.read('#ees-work-content [data-runtime-record] [data-work-criterion-status]',
                                   'dataset.workCriterionStatus'), 'pending')
        self.assertIn('아직 판정하지 않음', self.text('#ees-work-content [data-runtime-record]'))
        self.assertEqual(past['progress']['done'], 0)
        self.screenshot('c-phase2-review-history-unrecorded-final')
        self.save_visual_measurements('c-phase2-review-history-unrecorded-final', {'saved_run': saved, 'saved_case': past})

    def test_past_native_partial_unknown_and_access_restriction_keep_record_meanings(self):
        saved, past = self.arrange_history_run(partial=True)
        self.assertEqual(saved['status'], 'succeeded')
        self.assertIn('일부 범위 결과', self.text('#ees-work-content [data-runtime-record]'))
        self.assertNotEqual(self.read('#ees-work-content [data-runtime-record] [data-work-criterion-status]',
                                      'dataset.workCriterionStatus'), 'passed')
        self.assertNotEqual(past['status'], 'passed')
        self.screenshot('c-phase2-review-history-partial')
        async def denied(*args, **kwargs):
            raise self.backend.WorkflowError('native_access_denied', '합성 과거 기록 권한 회수')
        self.bridge.check = denied
        self.open_past_case(past['id'])
        self.wait("document.querySelector('#ees-work-content')?.innerText.includes('현재 권한으로 결과 근거를 볼 수 없습니다')")
        self.assertIsNone(self.read('#ees-work-content [data-runtime-action]'))
        self.click('#ees-work-content .ew-work-runtime-detail [data-work-overlay]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertNotIn('운영 문서', self.text('#ees-work-dialog'))
        self.assertIn('현재 권한으로', self.text('#ees-work-dialog'))
        redacted = asyncio.run(self.server.workflow.execution_state(self.server.user, case_id=past['id']))['run']
        self.assertFalse(redacted['evidence_available'])
        self.screenshot('c-phase2-review-history-access-restricted')
        self.save_visual_measurements('c-phase2-review-history-partial-access', {
            'saved_run': saved, 'redacted_run': redacted, 'parent_status': past['status']})

    def test_past_native_unknown_has_no_completed_validation_or_mutation(self):
        saved, past = self.arrange_history_run('unknown')
        self.assertEqual(saved['status'], 'unknown')
        self.assertIn('미확정', self.text('#ees-work-content [data-runtime-record]'))
        self.assertNotEqual(self.read('#ees-work-content [data-runtime-record] [data-work-criterion-status]',
                                      'dataset.workCriterionStatus'), 'passed')
        self.assertIsNone(self.read('#ees-work-content [data-runtime-action]'))
        self.assertEqual(past['progress']['done'], 0)
        self.screenshot('c-phase2-review-history-unknown')
        self.save_visual_measurements('c-phase2-review-history-unknown', {'saved_run': saved, 'saved_case': past})

    def check_legacy_draft_native_lock(self, state, require_prerequisite=False):
        fragment = runtime.examples.installation_docs_workflow(runtime.REFERENCES)
        legacy = deepcopy(self.current()['catalog']['nodes']['install-j'])
        legacy.update(id='mixed-draft-j', name='기존 검토 초안', parent='new-documents-t', deps=[], mode='draft')
        fragment['nodes'][legacy['id']] = legacy
        fragment['nodes']['new-documents-t']['children'].append(legacy['id'])
        if require_prerequisite:
            prerequisite = deepcopy(self.current()['catalog']['nodes']['scope-j'])
            prerequisite.update(id='mixed-review-j', name='초안 반영의 선행 확인', parent='new-documents-t', deps=[])
            fragment['nodes'][prerequisite['id']] = prerequisite
            fragment['nodes']['new-documents-t']['children'].append(prerequisite['id'])
            legacy['deps'] = [prerequisite['id']]
        self.ready(fragment)
        target = 'new-documents-page-j' if state == 'waiting_input' else 'new-documents-search-j'
        if state == 'waiting_input':
            self.bridge.results['search_pages'] = runtime.envelope({'results': [
                {'page_id': '41', 'title': '합성 후보 A'}, {'page_id': '42', 'title': '합성 후보 B'}]})
            self.start('new-documents-search-j', {'query': '설치', 'space_key': 'TEAM'})
            self.assertEqual(self.drain()['status'], 'succeeded')
            self.refresh_runtime('succeeded')
        self.start(target, {'query': '설치', 'space_key': 'TEAM'})
        release, started, thread = threading.Event(), threading.Event(), None
        original_invoke = self.bridge.invoke
        try:
            if state == 'running':
                async def held(*args, **kwargs):
                    started.set()
                    if not await asyncio.to_thread(release.wait, 20):
                        raise RuntimeError('Draft browser did not release the synthetic response')
                    return await original_invoke(*args, **kwargs)
                self.bridge.invoke = held
                thread = threading.Thread(target=self.drain, daemon=True)
                thread.start()
                self.assertTrue(started.wait(5))
            elif state == 'paused':
                self.control('pause')
            elif state == 'waiting_authorization':
                async def denied(*args, **kwargs):
                    raise self.backend.WorkflowError('native_access_denied', '합성 현재 권한 대기')
                self.bridge.check = denied
                self.drain()
            elif state == 'unknown':
                self.bridge.results['search_pages'] = runtime.envelope(status='unknown')
                self.drain()
            elif state == 'waiting_input':
                self.drain()
            self.refresh_runtime(state)
            self.choose(legacy['id'])
            value = 'Native ' + state + ' 동안 작성한 초안 · 임시 보존'
            self.fill('#ees-work-document textarea', value)
            before = deepcopy(self.current()['case']['jobs'][legacy['id']])
            before_count = self.server.requests.count(('POST', '/api/ees-work/action'))
            selector = 'button[form="ees-work-document"]'
            # Actual pointer and keyboard events. A disabled control must not
            # dispatch, and Enter in a textarea remains an edit, not a save.
            point = self.browser.evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector) + ");"
                "e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2,disabled:e.disabled};})()")
            for event in ('mousePressed', 'mouseReleased'):
                self.browser.call('Input.dispatchMouseEvent', {'type': event, 'x': point['x'], 'y': point['y'],
                    'button': 'left', 'buttons': 1 if event == 'mousePressed' else 0, 'clickCount': 1})
            self.settle()
            self.browser.evaluate('document.querySelector(' + json.dumps(selector) + ').focus()')
            self.key('Enter', 13, text='\r')
            self.settle()
            self.browser.evaluate("document.querySelector('#ees-work-document textarea').focus()")
            self.key('End', 35, modifiers=2)
            self.key('Enter', 13, text='\r')
            edited = self.read('#ees-work-document textarea', 'value')
            # A submitted form can also come from browser accessibility or
            # requestSubmit; it must hit the same client guard, not the server.
            self.browser.evaluate("document.querySelector('#ees-work-document').requestSubmit()")
            self.settle()
            after = deepcopy(self.current()['case']['jobs'][legacy['id']])
            dispatched = self.server.requests.count(('POST', '/api/ees-work/action')) - before_count
            note = self.text('[data-work-next]')
            self.click('#ees-work-close')
            self.click('#ees-work-context-open')
            retained = self.read('#ees-work-document textarea', 'value')
            label = state + ('-prerequisite' if require_prerequisite else '')
            self.save_visual_measurements('c-phase2-review-draft-' + label, {
                'boundary': 'Real UI pointer/keyboard/requestSubmit and public service; temporary SQLite; external result synthetic',
                'run': self.run_state(), 'button': point, 'note': note, 'before': before, 'after': after,
                'action_posts': dispatched, 'edited': edited, 'retained_after_reopen': retained})
            self.screenshot('c-phase2-review-draft-' + label)
            self.assertTrue(point['disabled'], 'Active Native runtime must disable legacy draft reflection')
            self.assertEqual(dispatched, 0, 'Blocked submit should not send a known-rejected legacy action')
            self.assertEqual(after, before, 'Blocked edits cannot alter saved draft, attempts, completion or history')
            self.assertEqual(retained, edited)
            self.assertIn('연결 실행', note)
        finally:
            release.set()
            if thread:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.bridge.invoke = original_invoke
        if state == 'unknown':
            self.assertEqual(self.run_state()['status'], 'unknown')
            return
        if state != 'running':
            self.choose(target)
            self.control('cancel', confirm=True)
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'cancelled'")
        else:
            self.choose(target)
            self.refresh_runtime('succeeded')
        self.choose(legacy['id'])
        self.assertEqual(self.read('#ees-work-document textarea', 'value'), edited)
        if require_prerequisite:
            self.assertTrue(self.read('button[form="ees-work-document"]', 'disabled'))
            posts = self.server.requests.count(('POST', '/api/ees-work/action'))
            self.browser.evaluate("document.querySelector('#ees-work-document').requestSubmit()")
            self.settle()
            self.assertEqual(self.server.requests.count(('POST', '/api/ees-work/action')), posts)
            self.assertEqual(self.current()['case']['jobs'][legacy['id']], before)
            self.screenshot('c-phase2-review-draft-terminal-prerequisite-blocked')
            self.choose(prerequisite['id'])
            self.click('#ees-work-run', confirm=True)
            self.settle()
            self.choose(legacy['id'])
        self.assertFalse(self.read('button[form="ees-work-document"]', 'disabled'))
        self.browser.evaluate("document.querySelector('button[form=\"ees-work-document\"]').focus()")
        self.key('Enter', 13, text='\r')
        self.settle()
        reflected = self.current()['case']['jobs'][legacy['id']]
        self.assertEqual(reflected['document'], edited)
        self.assertNotEqual(reflected['status'], 'passed', 'Reflecting a draft is not human completion')
        self.screenshot('c-phase2-review-draft-' + label + '-unlocked')
        self.save_visual_measurements('c-phase2-review-draft-' + label + '-unlocked', {
            'run': self.run_state(), 'reflected': reflected, 'retained_input': edited})

    def test_legacy_draft_blocked_while_native_running(self):
        self.check_legacy_draft_native_lock('running')

    def test_legacy_draft_blocked_while_native_paused(self):
        self.check_legacy_draft_native_lock('paused')

    def test_legacy_draft_blocked_while_native_waiting_input(self):
        self.check_legacy_draft_native_lock('waiting_input')

    def test_legacy_draft_blocked_while_native_waiting_authorization(self):
        self.check_legacy_draft_native_lock('waiting_authorization')

    def test_legacy_draft_blocked_while_native_unknown(self):
        self.check_legacy_draft_native_lock('unknown')

    def test_legacy_draft_cancelled_native_still_requires_legacy_prerequisite(self):
        self.check_legacy_draft_native_lock('paused', require_prerequisite=True)


if __name__ == '__main__':
    unittest.main()
