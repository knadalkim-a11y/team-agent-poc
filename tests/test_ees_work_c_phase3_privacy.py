"""Legacy evidence must also fail closed after a case read is unavailable.

The packaged frontend, EES HTTP routes and temporary SQLite service are real.
Native authentication/chat are the established synthetic browser fixture.
Only the failed case lookup is injected; evidence is saved by the real service.
"""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_ees_work_demo as native
import test_ees_work_c_phase2_native as phase_two


class CPhaseThreeLegacyPrivacyTests(unittest.TestCase):
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
    run_job = native.EESWorkNativeBrowserTests.run_job
    screenshot = native.EESWorkNativeBrowserTests.screenshot
    save_visual_measurements = native.EESWorkNativeBrowserTests.save_visual_measurements
    ready = phase_two.CPhaseTwoNativeTests.ready
    settle = phase_two.CPhaseTwoNativeTests.settle
    open_past_case = phase_two.CPhaseTwoNativeTests.open_past_case

    def open_history_nodes(self, names):
        for name in names:
            selector = self.browser.evaluate("""(name => {
                let el = [...document.querySelectorAll('#ees-work-content .ew-history-node > summary')]
                    .find(e => e.textContent.trim() === name);
                if (!el) return null;
                const parts = [];
                while (el.id !== 'ees-work-content') {
                    parts.unshift(el.tagName.toLowerCase() + ':nth-child(' +
                        ([...el.parentElement.children].indexOf(el) + 1) + ')');
                    el = el.parentElement;
                }
                return '#ees-work-content > ' + parts.join(' > ');
            })(""" + json.dumps(name) + ")")
            self.assertIsNotNone(selector, name)
            if not self.read(selector, 'parentElement.open'):
                self.click(selector)
                self.wait("document.querySelector(" + json.dumps(selector) + ")?.parentElement.open")

    def assert_failed_read_hides_copied_evidence(self, marker, selector, code, label, unsaved=None, case_id=None, history_names=()):
        def saved_jobs():
            result = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=case_id)) if case_id else self.current()
            self.assertTrue(result['ok'], result)
            return result['case']['jobs']

        def open_record():
            self.open_history_nodes(history_names)
            self.click(selector)
            self.wait("document.querySelector('#ees-work-dialog')?.open")
            if history_names:
                attempt = '#ees-work-dialog .ew-history-attempt > summary'
                self.click(attempt)
                self.wait("document.querySelector(" + json.dumps(attempt) + ")?.parentElement.open")
            self.assertIn(marker, self.text('#ees-work-dialog'))

        before = deepcopy(saved_jobs())
        open_record()

        async def unavailable(*args, **kwargs):
            return {'ok': False, 'error': {'code': code, 'message': '합성 과거 자료 조회 불가'}}

        with patch.object(self.server.workflow, 'get_state', unavailable):
            self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
            self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('합성 과거 자료 조회 불가')")
            observed = self.browser.evaluate("""(marker => {
                const dialog = document.querySelector('#ees-work-dialog');
                const sections = [...document.querySelectorAll('#ees-work-content .ew-history, #ees-work-content .ew-work-detail, #ees-work-content [data-work-section=current-result]')];
                return {dialog_open: !!dialog?.open,
                    dialog_retains_evidence: !!dialog?.textContent.includes(marker),
                    panel_evidence_sections_retain_marker: sections.some(e => e.textContent.includes(marker)),
                    panel_error: document.querySelector('#ees-work-panel')?.innerText.includes('합성 과거 자료 조회 불가')};
            })(""" + json.dumps(marker) + ")")
            self.screenshot('c-phase3-legacy-' + label)
            self.save_visual_measurements('c-phase3-legacy-' + label, {
                'boundary': 'Packaged frontend and real EES service/temporary SQLite; synthetic Native auth/chat; failed public case lookup injected',
                'lookup_code': code, 'saved_jobs_before': before, 'unsaved_local_document': unsaved, 'observed': observed})
            self.assertFalse(observed['dialog_retains_evidence'], observed)
            self.assertFalse(observed['panel_evidence_sections_retain_marker'], observed)

        self.click('#ees-work-content [data-action=execution_refresh]')
        self.wait("!document.querySelector('#ees-work-panel')?.innerText.includes('합성 과거 자료 조회 불가')")
        self.assertEqual(saved_jobs(), before)
        if unsaved is not None:
            self.assertEqual(self.read('#ees-work-document textarea', 'value'), unsaved,
                             'A failed read must preserve the local document for successful revalidation')
        if self.read('#ees-work-dialog', 'open'):
            self.key('Escape', 27)
        open_record()
        self.screenshot('c-phase3-legacy-' + label + '-restored')

    def test_legacy_draft_review_overlay_hides_saved_document_after_lookup_failure(self):
        definition = deepcopy(self.current()['catalog'])
        definition['nodes']['install-j']['mode'] = 'draft'
        definition['nodes']['install-j']['deps'] = []
        self.publish_runtime_fixture(definition)
        self.ready()
        self.choose('install-j')
        marker = 'SYNTHETIC-PRIVATE-LEGACY-DRAFT-REVIEW-PHASE3'
        self.fill('#ees-work-document textarea', marker)
        self.click('button[form="ees-work-document"]')
        self.settle()
        self.assertEqual(self.current()['case']['jobs']['install-j']['document'], marker)
        unsaved = 'SYNTHETIC-UNSAVED-LEGACY-DRAFT-PHASE3'
        self.fill('#ees-work-document textarea', unsaved)
        self.assert_failed_read_hides_copied_evidence(marker,
            '#ees-work-content .ew-work-detail > summary[data-work-overlay]',
            'state_read_failed', 'draft-review-lookup-failed', unsaved=unsaved)

    def test_legacy_history_overlay_hides_saved_inputs_after_access_restriction(self):
        case = self.seed_case('', ready=True)
        marker = 'SYNTHETIC-PRIVATE-LEGACY-HISTORY-PHASE3'
        # Arrange past evidence through the real service; the tested privacy
        # boundary begins with the visible More/history/past-case controls.
        actions = [('update_inputs', 'ap-j', {'inputs': {'ap': marker}}),
                   ('run', 'ap-j', {}), ('run', 'ap-j', {}), ('run', 'db-j', {})]
        if case['site']['interface']:
            actions.append(('run', 'interface-j', {}))
        for action, node, payload in actions:
            result = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                'action': action, 'chat_id': '', 'case_id': case['id'],
                'expected_revision': case['revision'], 'node_id': node, 'payload': payload}))
            self.assertTrue(result['ok'], result)
            case = result['case']
        self.assertEqual(case['status'], 'passed')
        self.assertEqual(len(case['jobs']['ap-j']['history']), 2)
        self.seed_case('existing-chat')
        self.navigate('/c/existing-chat')
        self.wait_scope_ready('site')
        self.choose('setup-p')
        self.open_past_case(case['id'])
        names = [case['definition']['nodes'][case['definition']['nodes']['ap-j']['parent']]['name'],
                 case['definition']['nodes']['ap-j']['name']]
        self.assert_failed_read_hides_copied_evidence(marker,
            '#ees-work-content .ew-history > summary[data-work-overlay]',
            'chat_forbidden', 'history-access-restricted', case_id=case['id'], history_names=names)


if __name__ == '__main__':
    unittest.main()
