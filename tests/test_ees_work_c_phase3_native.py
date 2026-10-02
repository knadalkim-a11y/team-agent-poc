"""Integrated same-account tab conflict and delayed-context browser contracts."""
from ees_work_integrated_fixture import IntegratedNativeCase


class CPhaseThreeNativeTests(IntegratedNativeCase):
    def test_same_account_two_native_targets_keep_local_input_after_conflict(self):
        key=self.author(fields=[{'id':'note','type':'text','scope':'run'}]);run=self.start(key);self.open_run(key,run)
        first=self.browser.session
        self.browser.navigate(self.server.url+'/c/existing-chat');second=self.browser.session
        self.browser.call('Runtime.enable');self.browser.call('Network.enable')
        self.wait("document.querySelector('#ees-work-entry') && document.querySelector('#chat-input')")
        self.open_run(key,run)
        self.browser.session=first;self.browser.call('Page.bringToFront')
        self.fill('[data-work-input][name="note"]','첫 탭 미저장')
        self.browser.session=second;self.browser.call('Page.bringToFront')
        self.fill('[data-work-input][name="note"]','둘째 탭 저장');self.click('[data-action="save_inputs"]')
        self.wait("!document.querySelector('[data-action=save_inputs]')?.disabled")
        saved=self.state(run_id=run['id'])['run'];self.assertEqual(saved['inputs']['note'],'둘째 탭 저장')
        self.browser.session=first;self.browser.call('Page.bringToFront');self.click('[data-action="save_inputs"]')
        self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('변경')")
        self.assertEqual(self.read('[data-work-input][name="note"]','value'),'첫 탭 미저장')
        self.assertEqual(self.state(run_id=run['id'])['run']['inputs'],saved['inputs'])
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'],[])
        self.assertNotEqual(first,second);self.screenshot('integrated-two-native-tabs-conflict')

    def test_delayed_workspace_read_cannot_replace_new_workflow(self):
        a=self.author(name='원래 대상');ra=self.start(a);self.open_run(a,ra)
        b=self.author(name='새로운 대상');rb=self.start(b);self.refresh()
        self.server.workspace_response_hold.clear();self.server.delay_next_workspace=True
        self.browser.evaluate('void window.__eesNativeWorkV1.refresh()')
        self.assertTrue(self.server.workspace_response_started.wait(3))
        self.click('[data-action="workflow"][data-workflow-id="'+b+'"]')
        self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('새로운 대상')")
        self.server.workspace_response_hold.set()
        self.wait("document.querySelector('#ees-work-entry [aria-current=page][data-workflow-id]')?.dataset.workflowId === '"+b+"'")
        self.assertIn('새로운 대상',self.text('#ees-work-panel'));self.assertNotIn('원래 대상',self.text('#ees-work-panel'))
        self.assertEqual(self.state(run_id=ra['id'])['run']['attempts'],[])
        self.assertEqual(self.state(run_id=rb['id'])['run']['attempts'],[])
        self.screenshot('integrated-late-read-new-target')

    def test_delayed_input_write_keeps_exact_original_run_after_chat_change(self):
        a=self.author(name='첫 진행',fields=[{'id':'note','type':'text','scope':'run'}]);ra=self.start(a);self.open_run(a,ra)
        b=self.author(name='둘째 진행',fields=[{'id':'note','type':'text','scope':'run'}]);rb=self.start(b);self.refresh()
        self.fill('[data-work-input][name="note"]','첫 진행에만 저장')
        self.server.action_response_hold.clear();self.server.delay_next_action=True;self.click('[data-action="save_inputs"]')
        self.assertTrue(self.server.action_response_started.wait(3))
        self.navigate('/c/other-chat');self.wait("document.querySelector('#ees-work-entry')")
        self.open_run(b,rb);self.server.action_response_hold.set()
        self.assertEqual(self.read('[data-work-input][name="note"]','value'),'')
        self.assertEqual(self.state(run_id=ra['id'])['run']['inputs'],{'note':'첫 진행에만 저장'})
        self.assertEqual(self.state(run_id=rb['id'])['run']['inputs'],{})
        self.assertEqual(self.state(run_id=ra['id'])['run']['attempts'],[])
        self.screenshot('integrated-late-write-original-target')
