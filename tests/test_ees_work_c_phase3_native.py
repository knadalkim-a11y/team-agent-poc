"""Bounded phase 3 cross-tab and late-history browser regressions.

The packaged Native frontend, EES HTTP service and temporary SQLite are real.
Authentication/chat and external/model transports are synthetic, as in the
existing Native UI fixture; full Native authentication is tested separately.
"""
import asyncio
from copy import deepcopy
import json
import threading
import unittest
from unittest.mock import patch

import test_ees_work_demo as native
import test_ees_work_c_phase2_native as phase2


class CPhaseThreeNativeTests(unittest.TestCase):
    # Share the established environment without inheriting/replaying its suite.
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
    screenshot = native.EESWorkNativeBrowserTests.screenshot
    save_visual_measurements = native.EESWorkNativeBrowserTests.save_visual_measurements
    ready = phase2.CPhaseTwoNativeTests.ready
    run_state = phase2.CPhaseTwoNativeTests.run_state
    settle = phase2.CPhaseTwoNativeTests.settle
    drain = phase2.CPhaseTwoNativeTests.drain
    open_past_case = phase2.CPhaseTwoNativeTests.open_past_case
    arrange_history_run = phase2.CPhaseTwoNativeTests.arrange_history_run

    def test_same_account_two_tabs_keep_local_input_on_revision_conflict(self):
        before = self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait_scope_ready('site')
        self.choose('db-j')
        first_session = self.browser.session
        self.browser.navigate(self.server.url + '/c/existing-chat')
        second_session = self.browser.session
        self.browser.call('Runtime.enable')
        self.browser.call('Network.enable')
        self.wait("!!document.querySelector('#chat-input.ProseMirror') && !!document.querySelector('#ees-work-entry')")
        if self.read('#sidebar', 'getBoundingClientRect().width') < 200:
            self.click('button[aria-label="사이드바 열기"]')
        self.wait_scope_ready('site')
        self.choose('db-j')
        self.browser.session = first_session
        self.browser.call('Page.bringToFront')
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.settle()
        self.fill('#ees-work-inputs input[name=db]', '첫 탭의 미저장 합성 입력')
        self.browser.session = second_session
        self.browser.call('Page.bringToFront')
        self.fill('#ees-work-inputs input[name=db]', '둘째 탭에서 먼저 저장한 합성 입력')
        self.click('#ees-work-inputs-save')
        self.wait("document.querySelector('#ees-work-inputs-save')?.disabled && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        saved = deepcopy(self.current()['case'])
        self.assertEqual(saved['jobs']['db-j']['inputs']['db'], '둘째 탭에서 먼저 저장한 합성 입력')
        self.assertEqual(saved['jobs']['db-j']['history'], before['jobs']['db-j']['history'])
        self.browser.session = first_session
        self.browser.call('Page.bringToFront')
        self.click('#ees-work-inputs-save')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn('먼저 변경되었습니다', self.text('#ees-work-dialog'))
        self.assertEqual(self.read('#ees-work-inputs input[name=db]', 'value'), '첫 탭의 미저장 합성 입력')
        self.assertEqual(self.current()['case']['jobs'], saved['jobs'])
        self.screenshot('c-phase3-two-tab-revision-conflict')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')?.open")
        self.assertEqual(self.read('#ees-work-inputs input[name=db]', 'value'), '첫 탭의 미저장 합성 입력')
        self.assertEqual(self.current()['case']['jobs'], saved['jobs'])
        self.save_visual_measurements('c-phase3-two-tab-revision-conflict', {
            'boundary': 'Two Chrome targets sharing one synthetic Native account and actual EES service/SQLite',
            'different_tabs': first_session != second_session,
            'case_id': saved['id'], 'second_tab_saved': saved['jobs']['db-j'],
            'first_tab_unsaved': self.read('#ees-work-inputs input[name=db]', 'value'),
            'after_conflict': self.current()['case']['jobs']['db-j'],
            'completion_count': len(self.server.completions)})
        self.assertEqual(self.server.completions, [])

    def test_late_past_execution_response_cannot_replace_current_case(self):
        saved, past = self.arrange_history_run('succeeded')
        current = deepcopy(self.current()['case'])
        # Leave the past view, then hold only its next execution lookup after
        # the real service has produced the response. No UI state is mocked.
        self.click('.ew-panel-menu > summary')
        self.click('#ees-work-run-view [data-action=current_view]')
        self.choose('new-operations-p')
        started, release = threading.Event(), threading.Event()
        original = self.server.workflow.execution_state

        async def delayed(user, **kwargs):
            result = await original(user, **kwargs)
            if kwargs.get('case_id') == past['id'] and not started.is_set():
                started.set()
                if not await asyncio.to_thread(release.wait, 8):
                    raise RuntimeError('Late history response was not released by the test')
            return result

        try:
            with patch.object(self.server.workflow, 'execution_state', delayed):
                if not self.read('.ew-panel-menu', 'open'):
                    self.click('.ew-panel-menu > summary')
                self.click('#ees-work-run-view [data-action=history_view]')
                selector = '[data-action=history_case][data-case-id=' + json.dumps(past['id']) + ']'
                self.wait('!!document.querySelector(' + json.dumps(selector) + ')')
                self.click(selector)
                self.assertTrue(started.wait(3), 'Past execution lookup did not begin')
                before = self.browser.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.includes('/execution/state?')).length")
                if not self.read('.ew-panel-menu', 'open'):
                    self.click('.ew-panel-menu > summary')
                self.click('#ees-work-run-view [data-action=current_view]')
                self.choose('new-operations-summary-j')
                self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '근거와 미확인 정리'")
                title = self.text('#ees-work-panel .ew-title')
                release.set()
                self.wait("performance.getEntriesByType('resource').filter(e=>e.name.includes('/execution/state?')).length > " + str(before))
                # Let the response continuation and next frame render.
                self.browser.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                self.assertEqual(self.text('#ees-work-panel .ew-title'), title)
                self.assertNotIn('읽기 전용', self.text('#ees-work-content'))
                self.assertNotIn(saved['id'], self.text('#ees-work-content'))
                self.assertNotIn('저장 당시 T 완료 기준', self.text('#ees-work-content'))
                self.assertEqual(self.current()['case']['jobs'], current['jobs'])
                self.screenshot('c-phase3-late-history-current-retained')
                self.save_visual_measurements('c-phase3-late-history-current-retained', {
                    'boundary': 'Actual packaged frontend/EES service/SQLite, held response only; synthetic auth/chat/HTTP',
                    'past_case_id': past['id'], 'past_run_id': saved['id'],
                    'current_case_id': current['id'], 'current_title': title,
                    'read_only_history_visible': '읽기 전용' in self.text('#ees-work-content'),
                    'current_jobs_preserved': self.current()['case']['jobs'] == current['jobs']})
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()
