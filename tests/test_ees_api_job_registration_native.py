"""Register a missing API from a real workflow editor and return to the same task."""
from ees_work_integrated_fixture import IntegratedNativeCase
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests as _AuthoringHelpers


class RegisterFromJobTests(IntegratedNativeCase):
    open_initialized_author_list = _AuthoringHelpers.open_initialized_author_list
    authoring_viewport = _AuthoringHelpers.authoring_viewport

    def test_factory_is_an_input_source_only_where_the_procedure_runs_for_a_factory(self):
        # 2026-11-25: a procedure run for a whole system has no factory to pass to an API.
        service_id=self.phase3_command('api_service_save',service={'name':'테스트 EMS'})['service']['id']
        api=self.phase3_command('api_save',api={'name':'공장 조회','purpose':'확인','service_id':service_id,
            'method':'GET','url':'https://ems.example/site','inputs':[{'name':'site','type':'string','in':'query','required':True}],'fields':[]})['api']
        keys={}
        for scope in ('factory','system'):
            keys[scope]=self.author(name='공장 선택지 확인 '+scope,jobs=1,mode='tool')
            current=self.state(workflow_id=keys[scope])['workflow']
            draft=current['draft']; draft['execution_scope']=scope
            self.command('save_draft',workflow_id=keys[scope],expected_revision=current['revision'],definition=draft)
        self.authoring_viewport(1920,1080,overlay=False)
        cta='[data-job-id=job-0] [data-author-action=job_api_setup]'
        offered={}
        for scope in ('factory','system'):
            self.open_initialized_author_list()
            self.click('[data-author-action=open][data-id="'+keys[scope]+'"]')
            self.click('[data-author-action=tab][data-tab=content]')
            if not self.read(cta,'isConnected'):
                self.click('[data-author-action=stage_toggle][data-id=stage]')
            self.click(cta)
            self.click('[data-api-candidate="'+api['id']+'"]')
            offered[scope]=self.browser.evaluate("[...document.querySelectorAll('#ees-work-dialog [data-api-source=site] option')].map(option=>option.value)")
            self.click('#ees-work-dialog [data-dialog-cancel]')
            self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.assertIn('factory_id',offered['factory'])
        self.assertIn('system_id',offered['system'])
        self.assertNotIn('factory_id',offered['system'])

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
        # Connected: the row no longer offers 도구 연결 (what the tool takes and gives back is on the job's page).
        self.wait("document.querySelector('[data-job-id=job-0]') && !document.querySelector('[data-job-id=job-0] [data-author-action=job_api_setup]')")
        # The button that was pressed is gone, so the keyboard stays on that job's row instead of falling off the list.
        self.assertTrue(self.browser.evaluate("document.activeElement === document.querySelector('[data-job-id=job-0] [data-author-action=node]')"))
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        self.assertEqual(self.state(workflow_id=key)['workflow']['draft']['nodes']['job-0']['api_binding']['operation_id'],selected)


    def test_job_page_connection_keeps_sections_keyboard_and_row_marks_in_place(self):
        # 2026-11-27, review of the design mock 23 (revision 3) implementation: what a still picture does not show.
        service_id=self.phase3_command('api_service_save',service={'name':'테스트 EMS'})['service']['id']
        api=self.phase3_command('api_save',api={'name':'설비 조회','purpose':'확인','service_id':service_id,
            'method':'GET','url':'https://ems.example/equipment','inputs':[{'name':'query','type':'string','in':'query','required':True}],'fields':[]})['api']
        # a tool job with no tool yet (a job connected the older way has no API button on its page in this setting)
        key=self.author(name='작업 화면에서 도구 연결',jobs=1)
        current=self.state(workflow_id=key)['workflow']
        draft=current['draft']; draft['nodes']['job-0'].update(mode='tool')
        self.command('save_draft',workflow_id=key,expected_revision=current['revision'],definition=draft)
        self.authoring_viewport(1920,1080,overlay=False)
        self.open_initialized_author_list()
        self.click('[data-author-action=open][data-id="'+key+'"]')
        self.click('[data-author-action=tab][data-tab=content]')
        cta='[data-job-id=job-0] [data-author-action=job_api_setup]'
        if not self.read(cta,'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        self.wait("document.querySelector('[data-job-id=job-0] [data-author-action=job_api_setup]')?.checkVisibility()")
        self.assertEqual(self.text('[data-job-id=job-0] .ew-author-tag[data-tool-state]'),'도구 연결 전')
        # A factory-condition or proposal mark on the row stays clear of the row's 도구 연결 (it was under the button).
        gap=self.browser.evaluate("""(() => {
            const job=document.querySelector('[data-job-id=job-0] .ew-author-job'),mark=document.createElement('small');
            mark.className='ew-author-tag';mark.dataset.factoryCondition='excluded';mark.textContent='이 공장 제외';
            job.insertBefore(mark,job.querySelector(':scope>img:last-child'));
            const a=mark.getBoundingClientRect(),b=document.querySelector('[data-job-id=job-0] [data-author-action=job_api_setup]').getBoundingClientRect();
            mark.remove();return b.left-a.right;})()""")
        self.assertGreaterEqual(gap,8)
        # In the narrowest panel the button is in the row's own flow: the name keeps its width (it wrapped a letter a line).
        self.authoring_viewport(360,768,overlay=True)
        narrow=self.browser.evaluate("""(() => {const row=document.querySelector('[data-job-id=job-0]');
            return {row:row.getBoundingClientRect().height,name:row.querySelector('.ew-job-row-label>span').getBoundingClientRect().width};})()""")
        # measured 62px wide in an 85px row; with the wide layout's padding it was 19px wide in a 253px row
        self.assertGreater(narrow['name'],40,narrow)
        self.assertLess(narrow['row'],140,narrow)
        self.authoring_viewport(1920,1080,overlay=False)
        # On the job's page: a section opened before the tool is connected stays open, and the new card's 상세 보기
        # does not take that section's state.
        self.click('[data-author-action=node][data-id=job-0]')
        self.wait("document.querySelector('#ew-author-node .ew-job-assignment')")
        self.click('.ew-job-assignment>summary')
        self.assertTrue(self.read('.ew-job-assignment','open'))
        self.click('.ew-tool-card[data-tool-state=unconnected]>[data-author-action=job_api_setup]')
        self.click('[data-api-candidate="'+api['id']+'"]')
        self.choose('[data-api-source=query]','constant')
        self.fill('[data-api-value=query]','EQ-100')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('.ew-tool-card>details')")
        self.assertFalse(self.read('.ew-tool-card>details','open'))
        self.assertTrue(self.read('.ew-job-assignment','open'))
        # The keyboard stays on the button that was pressed (도구 변경 on the card now).
        self.assertTrue(self.browser.evaluate("document.activeElement === document.querySelector('.ew-tool-card>[data-author-action=job_api_setup]')"))
        # 상세 보기, once opened, stays open when the page is drawn again.
        self.click('.ew-tool-card>details>summary')
        self.assertTrue(self.read('.ew-tool-card>details','open'))
        self.click('.ew-tool-card>[data-author-action=job_api_setup]')
        self.wait("document.querySelector('#ees-work-dialog[open] [data-dialog-confirm]')")
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.assertTrue(self.read('.ew-tool-card>details','open'))
        self.assertTrue(self.read('.ew-job-assignment','open'))


# Import helpers without exposing their TestCase to unittest module discovery.
del _AuthoringHelpers
