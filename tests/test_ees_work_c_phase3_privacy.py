"""Evidence rendering fails closed after current access or lookup failure."""
import asyncio
from ees_work_integrated_fixture import IntegratedNativeCase


class CPhaseThreeLegacyPrivacyTests(IntegratedNativeCase):
    def test_revoked_native_actor_scope_removes_open_result_and_author_controls(self):
        key=self.author(fields=[{'id':'note','type':'text','scope':'run'}]);run=self.start(key,inputs={'note':'synthetic-sensitive-result'})
        self.command('human_confirm',run_id=run['id'],job_id='job-0',expected_revision=run['revision'])
        self.open_run(key,run);self.click('[data-action="tab"][data-tab="history"]');self.click('.ew-history summary')
        self.assertIn('synthetic-sensitive-result',self.text('#ees-work-panel'))
        self.server.user['role']='user';self.refresh()
        self.assertNotIn('synthetic-sensitive-result',self.text('#ees-work-panel'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-panel [data-action=confirm],#ees-work-panel [data-action=execute]')"))
        denied=asyncio.run(self.server.workflow.workspace_state(self.server.user,run_id=run['id']))
        self.assertFalse(denied['ok']);self.screenshot('integrated-current-scope-revoked')

    def test_failed_history_lookup_never_reveals_previous_attempt_or_input(self):
        key=self.author(fields=[{'id':'note','type':'text','scope':'run'}]);run=self.start(key,inputs={'note':'synthetic-private-history'})
        self.command('human_confirm',run_id=run['id'],job_id='job-0',expected_revision=run['revision'])
        self.open_run(key,run);self.click('[data-action="tab"][data-tab="history"]');self.click('.ew-history summary')
        self.assertIn('synthetic-private-history',self.text('#ees-work-panel'))
        self.server.workspace_error='기록을 조회하지 못했습니다';self.refresh()
        self.assertNotIn('synthetic-private-history',self.text('#ees-work-panel'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-history')"))
        self.assertIn('기록을 조회하지 못했습니다',self.text('#ees-work-panel'));self.screenshot('integrated-history-failed-closed')
