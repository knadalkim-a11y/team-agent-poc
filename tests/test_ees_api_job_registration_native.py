"""Register a missing API from a real workflow editor and return to the same task."""
from ees_work_integrated_fixture import IntegratedNativeCase
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests as _AuthoringHelpers


class RegisterFromJobTests(IntegratedNativeCase):
    open_initialized_author_list = _AuthoringHelpers.open_initialized_author_list
    authoring_viewport = _AuthoringHelpers.authoring_viewport

    def test_staged_mapping_survives_cancel_and_saved_registration_requires_connect(self):
        service_id=self.phase3_command('api_service_save',service={'name':'테스트 EMS'})['service']['id']
        original=self.phase3_command('api_save',api={'name':'기존 조회','purpose':'확인','service_id':service_id,
            'method':'GET','url':'https://ems.example/current','inputs':[{'name':'query','type':'string','in':'query','required':True}],'fields':[]})['api']
        key=self.author(name='API 등록 복귀 확인',jobs=1,mode='tool')
        self.authoring_viewport(1920,1080,overlay=False)
        self.open_initialized_author_list()
        self.click('[data-author-action=open][data-id="'+key+'"]')
        self.click('[data-author-action=tab][data-tab=content]')
        cta='[data-job-id=job-0] [data-author-action=job_api_setup]'
        if not self.read(cta,'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        self.click(cta)
        self.click('[data-api-candidate="'+original['id']+'"]')
        self.choose('[data-api-source=query]','constant')
        self.fill('[data-api-value=query]','보존할 입력')
        self.fill('[data-api-search]','기존')
        self.click('[data-api-register]')
        self.wait("document.querySelector('[data-api-screen=create]')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-dialog[open]')"))
        self.click('[data-api-action=cancel]')
        self.wait("document.querySelector('#ees-work-dialog [data-api-value=query]')")
        self.assertEqual(self.read('[data-api-search]','value'),'기존')
        self.assertEqual(self.read('[data-api-value=query]','value'),'보존할 입력')

        self.click('[data-api-register]')
        self.fill('[name=api-url]','https://ems.example/new')
        self.fill('[name=api-name]','신규 업무 조회')
        self.fill('[name=api-purpose]','최근 데이터를 조회합니다.')
        self.choose('[name=api-service_id]',service_id)
        self.click('[data-api-action=save]')
        self.wait("""(() => {const selected=document.querySelector('[data-api-candidate][aria-pressed=true]');
                      return selected && selected.textContent.includes('신규 업무 조회')})()""")
        selected=self.browser.evaluate("document.querySelector('[data-api-candidate][aria-pressed=true]').dataset.apiCandidate")
        self.assertNotEqual(selected,original['id'])
        self.assertNotIn('api_binding',self.state(workflow_id=key)['workflow']['draft']['nodes']['job-0'])
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-job-id=job-0] [data-api-job-binding]')")
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        self.assertEqual(self.state(workflow_id=key)['workflow']['draft']['nodes']['job-0']['api_binding']['operation_id'],selected)


# Import helpers without exposing their TestCase to unittest module discovery.
del _AuthoringHelpers
