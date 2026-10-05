"""Current schema-driven panel: draft retention, attempts and readonly history."""
from copy import deepcopy
import json
from ees_work_integrated_fixture import IntegratedNativeCase


class CPhaseOneNativeTests(IntegratedNativeCase):
    def test_retry_keeps_original_attempt_input_and_immutable_published_version(self):
        key = self.author(fields=[{'id':'note','type':'text','scope':'run'}]); run = self.start(key, inputs={'note':'첫 입력'})
        saved = self.command('human_confirm', run_id=run['id'], job_id='job-0', expected_revision=run['revision'])['run']
        saved = self.command('save_inputs', run_id=run['id'], inputs={'note':'두 번째 입력'}, expected_revision=saved['revision'])['run']
        saved = self.command('human_confirm', run_id=run['id'], job_id='job-0', expected_revision=saved['revision'])['run']
        definition = deepcopy(self.state(workflow_id=key)['workflow']['draft']); definition['name']='새 게시 이름'
        self.command('save_draft', workflow_id=key, expected_revision=3, definition=definition)
        self.command('validate_workflow', workflow_id=key, expected_revision=4)
        self.command('publish_workflow', workflow_id=key, expected_revision=4)
        self.open_run(key, saved); self.click('[data-action="tab"][data-tab="history"]')
        summaries = self.browser.evaluate("document.querySelectorAll('.ew-history summary').length")
        self.assertEqual(summaries, 2)
        for n in (1,2): self.click('.ew-history:nth-of-type('+str(n)+') summary')
        text=self.text('#ees-work-panel'); self.assertIn('첫 입력',text);self.assertIn('두 번째 입력',text); self.assertIn('절차 v1',text)
        current=self.state(run_id=run['id'])['run']; self.assertEqual(current['definition']['name'],'합성 절차'); self.assertEqual(current['version'],1)
        self.screenshot('integrated-immutable-attempts')

    def test_closed_run_remains_readonly_and_uses_its_saved_completion(self):
        key=self.author();run=self.start(key)
        for job in ('job-0','job-1'):
            run=self.command('human_confirm',run_id=run['id'],job_id=job,expected_revision=run['revision'])['run']
        run=self.command('close_run',run_id=run['id'],expected_revision=run['revision'])['run']
        self.refresh();self.click('[data-action="records"]');self.click('[data-action="open_run"][data-run-id="'+run['id']+'"]')
        self.wait("document.querySelector('[data-action=job][data-job-id=job-0]')")
        self.click('[data-action="job"][data-job-id="job-0"]')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=confirm],[data-action=execute],[data-action=save_inputs]')"))
        self.assertEqual(run['progress']['completed'],2)
        self.click('[data-action="tab"][data-tab="history"]'); self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-history').length"),1)
        self.screenshot('integrated-closed-history')

    def test_long_form_scrolling_keeps_heading_and_unsaved_values(self):
        fields=[{'id':'value-'+str(i),'name':'한글 입력 항목 '+str(i),'type':'text','scope':'run'} for i in range(20)]
        key=self.author(fields=fields);run=self.start(key);self.open_run(key,run)
        self.fill('[data-work-input][name="value-19"]','마지막 값')
        self.assertEqual(self.read('[data-work-input][name="value-19"]','value'),'마지막 값')
        self.assertTrue(self.browser.evaluate("document.querySelector('#ees-work-content').scrollHeight > document.querySelector('#ees-work-content').clientHeight"))
        self.click('[data-action="overview"]');self.click('[data-action="job"][data-job-id="job-0"]')
        self.assertEqual(self.read('[data-work-input][name="value-19"]','value'),'마지막 값')
        self.assertEqual(self.state(run_id=run['id'])['run']['inputs'],{})
        self.screenshot('integrated-long-korean-form')

    def test_run_and_workflow_setting_forms_preserve_zero_false_and_empty(self):
        fields=[{'id':'count','name':'수량','type':'number','scope':'workflow'}, {'id':'enabled','name':'사용','type':'boolean','scope':'workflow'}, {'id':'note','name':'입력','type':'text','scope':'run'}]
        key=self.author(fields=fields);self.command('save_settings',workflow_id=key,values={'count':0,'enabled':False})
        run=self.start(key,inputs={'note':''});self.open_run(key,run)
        self.assertEqual(self.read('[data-work-input][name="note"]','value'),'')
        self.click('[data-action="tab"][data-tab="settings"]')
        self.assertEqual(self.read('[data-work-input][name="count"]','value'),'0')
        self.assertEqual(self.read('[data-work-input][name="enabled"]','value'),'false')
        self.assertEqual(self.state(run_id=run['id'])['run']['inputs'],{'note':''})
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'],[])

    def test_eight_declared_native_input_types_survive_visible_save_and_reload(self):
        fields=[{'id':kind,'name':'입력 '+kind,'type':kind,'scope':'run',**({'options':['one','two']} if kind=='single' else {'options':['a','b']} if kind=='multi' else {})} for kind in ('text','number','datetime','single','multi','list','person','boolean')]
        values={'text':'기존 문자','number':0,'datetime':'2026-10-02T09:30','single':'one','multi':['a','b'],'list':['첫째','둘째'],'person':{'kind':'user','id':self.server.user['id']},'boolean':False}
        key=self.author(fields=fields);run=self.start(key,inputs=values);self.open_run(key,run)
        controls=self.browser.evaluate("[...document.querySelectorAll('[data-work-input]')].map(e=>({name:e.name,kind:e.dataset.inputType,value:e.value,selected:e.multiple?[...e.selectedOptions].map(option=>option.value):null}))")
        self.assertEqual({row['kind'] for row in controls},{field['type'] for field in fields})
        self.assertEqual(len(controls),8)
        by_id={row['name']:row for row in controls}
        self.assertEqual(by_id['number']['value'],'0');self.assertEqual(by_id['boolean']['value'],'false')
        self.assertEqual(json.loads(by_id['person']['value']),values['person'])
        self.assertEqual([json.loads(value) for value in by_id['multi']['selected']],values['multi'])
        self.assertEqual(by_id['datetime']['value'],values['datetime'])
        self.fill('[data-work-input][name=text]','사람이 수정한 문자');self.click('[data-action=save_inputs]')
        self.wait("!document.querySelector('[data-action=save_inputs]')?.disabled")
        expected={**values,'text':'사람이 수정한 문자'}
        saved=self.state(run_id=run['id'])['run'];self.assertEqual(saved['inputs'],expected)
        self.assertIs(type(saved['inputs']['boolean']),bool);self.assertIs(type(saved['inputs']['number']),int)
        self.assertEqual(saved['attempts'],[])
        self.navigate('/c/other-chat');self.wait("document.querySelector('#ees-work-entry')")
        self.open_run(key,saved)
        self.assertEqual(self.read('[data-work-input][name=text]','value'),expected['text'])
        self.assertEqual(self.read('[data-work-input][name=boolean]','value'),'false')
        self.assertEqual(self.state(run_id=run['id'])['run']['inputs'],expected)
        self.screenshot('integrated-eight-native-input-types')
