"""Product browser evidence for the six screens pinned by the v11 design."""
import asyncio
from copy import deepcopy
import json
import os
from unittest.mock import patch

from ees_work_integrated_fixture import IntegratedNativeCase
from test_ees_api_spec_execution import backup_service
import test_ees_work_figma_authoring_native as authoring


class RegisteredApiNativeTests(IntegratedNativeCase):
    authoring_viewport = authoring.FigmaAuthoringNativeTests.authoring_viewport
    open_initialized_author_list = authoring.FigmaAuthoringNativeTests.open_initialized_author_list

    def register_service(self, name):
        return self.phase3_command('api_service_save', service={'name': name})['service']['id']

    def seed_api(self, service, method, url, name, purpose, **options):
        record = dict(service_id=service, name=name, method=method, url=url, purpose=purpose,
                      inputs=[], result_path='', fields=[])
        record.update(options)
        return self.phase3_command('api_save', api=record)['api']

    def capture_state(self, name, selector):
        self.wait('document.querySelector(' + json.dumps(selector) + ')?.checkVisibility()')
        self.wait("""!document.querySelector('[data-ees-motion=closing]') &&
            document.getAnimations().every(a=>!a.pending && a.playState !== 'running' ||
                a.effect.getTiming().iterations === Infinity)""")
        self.browser.evaluate('document.fonts.ready.then(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(()=>done(true)))))')
        report = self.browser.evaluate("""(() => {
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const {x, y, width, height} = element.getBoundingClientRect();
            return {x, y, width, height};
          };
          return {viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,
            sidebar:rect('[data-ees-source-sidebar]'), work:rect('[data-ees-work-surface]'),
            chat:rect('[data-ees-chat-surface]'), form:rect('[data-api-catalog]'),
            save:rect('[data-api-action=save]'), title:rect('[data-api-catalog] h2'),
            search:rect('[name=api-search]'),
            fields:['url','name','purpose'].map(name=>rect('[name=api-'+name+']')),
            stage:rect('[data-stage-id=stage]'), jobs:['job-0','job-1'].map(id=>rect('[data-job-id='+id+']')),
            bindings:[...document.querySelectorAll('[data-api-job-binding]')].map(e=>e.innerText)};
        })()""")
        report['scene'] = name
        directory = self.screenshot('api-v11-' + name)
        (directory / ('api-v11-' + name + '.json')).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertEqual(report['viewport'], [1920, 1080])
        self.assertEqual(report['dpr'], 1)
        for region, x, width in (('sidebar', 0, 256), ('work', 256, 1104), ('chat', 1360, 560)):
            self.assertAlmostEqual(report[region]['width'], width, delta=1, msg=region)
            self.assertAlmostEqual(report[region]['x'], x, delta=1, msg=region)
        if name.startswith('tools-'):
            self.assertAlmostEqual(report['form']['x'], 328, delta=1)
            self.assertAlmostEqual(report['form']['width'], 960, delta=1)
        if name in ('tools-create-empty', 'tools-create', 'tools-edit'):
            expected_tops = (197, 288, 379) if name == 'tools-edit' else (237, 325, 413)
            for field, y in zip(report['fields'], expected_tops):
                self.assertAlmostEqual(field['y'], y, delta=2, msg=name)
                self.assertAlmostEqual(field['height'], 46, delta=2, msg=name)
        if name.startswith('task-'):
            self.assertAlmostEqual(report['stage']['x'], 328, delta=2)
            self.assertAlmostEqual(report['stage']['width'], 960, delta=2)
            self.assertAlmostEqual(report['stage']['y'], 234, delta=2)
        if name == 'tools-edit':
            self.assertGreater(report['save']['x'], report['form']['x'] + 800)
            self.assertLess(abs(report['save']['y'] - report['title']['y']), 22)

    def open_catalog(self):
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=tools]')
        self.wait("document.querySelector('[data-api-screen=list] [data-api-action=create]')")

    def test_register_edit_reopen_and_compare_catalog_frames(self):
        backup = self.register_service('사내 백업')
        wiki = self.register_service('사내 위키')
        self.seed_api(backup, 'POST', 'https://backup.example/backups/retries', '실패 백업 재처리',
                      '실패한 백업 작업의 재처리를 요청합니다.')
        self.seed_api(wiki, 'GET', 'https://wiki.example/content/search', '배포 문서 찾기',
                      '공간과 검색어로 사내 위키의 배포 문서를 찾습니다.')
        self.authoring_viewport(1920, 1080, overlay=False)
        self.open_catalog()
        self.click('[data-api-action=create]')
        url = '[name=api-url]'
        self.assertEqual(self.read(url, 'value'), '')
        self.assertEqual(self.read('[name=api-name]', 'value'), '')
        self.capture_state('tools-create-empty', '[data-api-screen=create]')
        self.fill(url, 'https://backup.example/backups')
        self.fill('[name=api-name]', '백업 결과 조회')
        self.fill('[name=api-purpose]', '백업 작업별 성공 여부와 완료 시각을 확인합니다.')
        self.capture_state('tools-create', '[data-api-screen=create]')
        self.choose('[name=api-service_id]', backup)
        self.click('[data-api-action=save]')
        self.wait("document.querySelector('[data-api-screen=list]') && document.querySelectorAll('[data-api-action=open]').length === 3")
        self.capture_state('tools-list', '[data-api-screen=list]')
        rows = self.browser.evaluate("""[...document.querySelectorAll('[data-api-action=open]')]
          .map(e=>({id:e.dataset.id,text:e.innerText}))""")
        row = next(r for r in rows if '백업 결과 조회' in r['text'])
        self.assertLess(row['text'].index('/backups'), row['text'].index('백업 결과 조회'))
        opener = '[data-api-action=open][data-id="' + row['id'] + '"]'
        self.click(opener)
        self.click('[data-api-action=edit]')
        self.assertEqual(self.read('[name=api-service_id]', 'value'), backup)
        self.assertEqual(self.read(url, 'value'), 'https://backup.example/backups')
        self.capture_state('tools-edit', '[data-api-screen=edit]')
        self.fill('[name=api-purpose]', '완료 시각과 처리 상태를 함께 확인합니다.')
        self.click('[data-api-action=save]')
        self.wait("document.querySelector('[data-api-screen=list]')")
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('[data-action=tools]')")
        self.open_catalog()
        self.click(opener)
        self.click('[data-api-action=edit]')
        self.assertEqual(self.read('[name=api-purpose]', 'value'), '완료 시각과 처리 상태를 함께 확인합니다.')

    def test_open_workflow_connect_apis_and_persist_handoff(self):
        service = self.register_service('EMS 설비 이력')
        reader = self.seed_api(service, 'GET', 'https://ems.example/equipment/{equipmentId}/alarms',
            '설비 알람 조회', '설비에서 발생한 알람을 조회합니다.',
            inputs=[dict(name='equipmentId', label='설비 번호', required=True, type='string', **{'in':'path'})],
            fields=[dict(path='code', label='알람 코드', type='string'), dict(path='state', label='알람 상태', type='string')],
            example=[{'code':'F101','state':'점검 필요'}, {'code':'F205','state':'정지'}])
        writer = self.seed_api(service, 'POST', 'https://ems.example/equipment/{equipmentId}/alarms',
            '알람 확인 등록', '확인한 알람을 등록합니다.',
            inputs=[dict(name='equipmentId', label='설비 번호', required=True, type='string', **{'in':'path'}),
                    dict(name='code', label='알람 코드', required=True, type='string', **{'in':'body'})],
            fields=[dict(path='receipt', label='접수 번호', type='string')], example={'receipt':'ACK-104'})
        key = self.author(name='설비 알람 처리')
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        nodes = definition['nodes']
        nodes['stage']['name'] = '설비 알람 점검'
        nodes['job-0'].update(name='설비 알람 조회', mode='tool')
        nodes['job-1'].update(name='알람 확인 등록', mode='tool')
        self.command('save_draft', expected_revision=workflow['revision'], workflow_id=key, definition=definition)
        self.authoring_viewport(1920, 1080, overlay=False)
        self.open_initialized_author_list()
        self.click('[data-author-action=open][data-id="' + key + '"]')
        self.click('[data-author-action=tab][data-tab=content]')
        first = '[data-job-id=job-0] [data-author-action=job_api_setup]'
        if not self.read(first, 'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        self.capture_state('task-connection', first)
        self.assertFalse(self.read('[data-api-job-binding]', 'isConnected'))
        for job, op in (('job-0', reader), ('job-1', writer)):
            self.click('[data-job-id="' + job + '"] [data-author-action=job_api_setup]')
            self.click('[data-api-candidate="' + op['id'] + '"]')
            self.choose('[data-api-source="equipmentId"]', 'constant')
            self.fill('[data-api-value="equipmentId"]', 'EQ-100')
            if job == 'job-1':
                self.choose('[data-api-source="code"]', 'result')
                self.choose('[data-api-result="code"]', '["job-0","code"]')
            self.click('#ees-work-dialog [data-dialog-confirm]')
            self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.capture_state('task-mapped', '[data-api-job-binding]')
        self.click('[data-author-action=job_api_example]')
        self.wait("document.querySelector('#ees-work-dialog[open] .ew-api-result-example')?.textContent.includes('F101')")
        self.key('Escape', 27)
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        saved = self.state(workflow_id=key)['workflow']['draft']['nodes']
        self.assertEqual(saved['job-0']['api_binding']['operation_id'], reader['id'])
        self.assertEqual(saved['job-1']['api_binding']['operation_id'], writer['id'])
        source = saved['job-1']['api_binding']['inputs']['code']['result']
        self.assertEqual(source, {'job_id':'job-0', 'field':'code', 'confirmed':True})

    def test_registered_query_reaches_service_and_result_reopens_from_records(self):
        http = self.enterContext(backup_service())
        url = f'http://127.0.0.1:{http.server_port}'
        service = self.register_service('실행 검증')
        self.enterContext(patch.dict(os.environ, {'EES_WORK_API_SERVICES':json.dumps({service:{'base_url':url}})}))
        key = self.author(name='백업 확인', jobs=1)
        saved = self.state(workflow_id=key)['workflow']
        definition = deepcopy(saved['draft'])
        definition['nodes']['job-0'].update(name='백업 확인 작업', mode='tool')
        self.command('save_draft', workflow_id=key, expected_revision=saved['revision'], definition=definition)
        self.authoring_viewport(1920, 1080, overlay=False)
        self.open_catalog()
        self.click('[data-api-action=create]')
        self.fill('[name=api-name]', '백업 결과 조회')
        self.fill('[name=api-purpose]', '백업 서비스 응답의 이름을 확인합니다.')
        self.fill('[name=api-url]', url + '/backups')
        self.choose('[name=api-service_id]', service)
        self.click('[data-api-advanced] > summary')
        self.fill('[name=api-result_path]', 'backup.entries')
        self.click('[data-api-action=add-field]')
        self.fill('[name=api-fields-0-path]', 'label')
        self.fill('[name=api-fields-0-label]', '백업 이름')
        self.click('[data-api-action=save]')
        self.wait("document.querySelector('[data-api-screen=list] [data-api-action=open]')")
        api = self.read('[data-api-action=open]', 'dataset.id')
        self.click('[data-action=procedures]')
        self.click('[data-author-action=open][data-id="' + key + '"]')
        self.click('[data-author-action=tab][data-tab=content]')
        link = '[data-job-id=job-0] [data-author-action=job_api_setup]'
        if not self.read(link, 'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        self.click(link)
        self.click('[data-api-candidate="' + api + '"]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-api-job-binding]')")
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        current = self.state(workflow_id=key)['workflow']
        self.assertEqual(current['draft']['nodes']['job-0']['api_binding']['operation_id'], api)
        # Use the same workspace commands as the publication and new-run forms.
        self.command('publish_workflow', workflow_id=key, expected_revision=current['revision'])
        run = self.start(key)
        self.refresh()
        self.click('[data-action=mode][data-mode=work]')
        self.open_run(key, run)
        self.assertEqual(http.requests, [])
        self.click('[data-action=execute]')
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes('nightly-ok')")
        self.assertIn('백업 이름', self.text('.ew-api-table'))
        self.assertEqual(http.requests, [('/backups', {})])
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-panel')")
        self.click('[data-action=mode][data-mode=work]')
        self.open_run(key, run)
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes('nightly-ok')")
        self.assertEqual(len(self.state(run_id=run['id'])['run']['attempts']), 1)
        self.assertEqual(http.requests, [('/backups', {})])

    def test_manage_service_and_import_selected_openapi_operation(self):
        self.click('[data-action=mode][data-mode=author]')
        self.open_workspace_assets()
        self.click('[data-action=tools]')
        self.click('[data-api-action=services]')
        self.wait("document.querySelector('dialog[data-api-modal]')?.matches(':modal')")
        self.click('[data-api-action=service-new]')
        self.fill('[name=api-service_edit]','설비 이력')
        self.click('[data-api-action=service-save]')
        self.wait("document.querySelector('.ew-api-service')?.textContent.includes('설비 이력')")
        self.click('[data-api-action=service-edit]')
        self.fill('[name=api-service_edit]','현장 설비')
        self.click('[data-api-action=service-save]')
        self.wait("document.querySelector('.ew-api-service')?.textContent.includes('현장 설비')")
        self.click('[data-api-action=list]')
        self.click('[data-api-action=create]')
        self.click('[data-api-action=import]')
        self.click('[data-api-action=import-example]')
        self.wait("document.querySelectorAll('[data-op-index]').length===2")
        self.click('[data-op-index="0"]')
        self.click('[data-api-action=import-confirm]')
        self.wait("document.querySelector('[data-api-screen=list] [data-api-action=open]')")
        apis = asyncio.run(self.server.workflow.api_catalog.state(self.server.user))['apis']
        self.assertEqual(len(apis),1)
        self.click('[data-api-action=open]')
        self.wait("document.querySelector('[data-api-screen=detail]')?.textContent.includes('연결된 작업이 없습니다.')")
        self.assertIn(apis[0]['name'],self.text('[data-api-screen=detail]'))
        self.assertIn('요청 파라미터',self.text('[data-api-screen=detail]'))
