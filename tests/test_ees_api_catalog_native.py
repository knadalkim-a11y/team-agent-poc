"""Product browser evidence for the API screens.

Registration and task connection follow the v11 frames. The list, the opened API and editing follow
design mock 17 revision 2 (docs/mockups/ees-work/TASK.md#workspace-product-step1-20261116).
"""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from confluence_provider import CHILDREN, PAGE, PAGE_ID, confluence_provider
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
            search:rect('[name=api-search]'), create:rect('[data-api-action=create]'),
            thead:rect('.ew-api-thead'), columns:[...document.querySelectorAll('.ew-api-columns>div')].map(e=>{
              const {x, y, width, height} = e.getBoundingClientRect(); return {x, y, width, height};}),
            mapping:rect('[data-api-mapping]'), foot:rect('.ew-api-foot'),
            fields:['url','name','purpose'].map(name=>rect('[name=api-'+name+']')),
            stage:rect('[data-stage-id=stage]'), jobs:['job-0','job-1'].map(id=>rect('[data-job-id='+id+']')),
            overview:rect('.ew-content-overview'), stageHeading:rect('.ew-content-heading'),
            looseJobForm:rect('#ew-loose-job-editor'), addJobToList:rect('#ew-loose-job-editor [data-author-action=loose_apply]'),
            stageHead:rect('[data-stage-id=stage] .ew-stage-head'),
            addJob:rect('[data-stage-id=stage] .ew-stage-head > [data-author-action=add_job]'),
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
        if name in ('tools-create-empty', 'tools-create'):
            for field, y in zip(report['fields'], (237, 325, 413)):
                self.assertAlmostEqual(field['y'], y, delta=2, msg=name)
                self.assertAlmostEqual(field['height'], 46, delta=2, msg=name)
        if name == 'tools-list':
            # One search row, then one table: no second title above them.
            self.assertAlmostEqual(report['search']['x'], 328, delta=1)
            self.assertLess(report['search']['y'], 100)
            self.assertAlmostEqual(report['create']['x'] + report['create']['width'], 1288, delta=1)
            self.assertLess(abs(report['create']['y'] + report['create']['height'] / 2 -
                                report['search']['y'] - report['search']['height'] / 2), 2)
            self.assertAlmostEqual(report['thead']['width'], 960, delta=1)
            self.assertGreater(report['thead']['y'], report['search']['y'] + report['search']['height'])
        if name in ('tools-detail', 'tools-edit'):
            # What is sent sits beside what comes back.
            left, right = report['columns']
            self.assertAlmostEqual(left['x'], 328, delta=1, msg=name)
            self.assertAlmostEqual(left['y'], right['y'], delta=1, msg=name)
            self.assertGreater(right['x'], left['x'] + 400, msg=name)
            self.assertAlmostEqual(right['x'] + right['width'], 1288, delta=1, msg=name)
        if name == 'tools-edit':
            url, api_name, purpose = report['fields']
            self.assertAlmostEqual(url['y'], api_name['y'], delta=1)
            self.assertGreater(api_name['x'], url['x'] + url['width'])
            self.assertGreater(purpose['y'], url['y'] + url['height'])
            self.assertAlmostEqual(purpose['x'], 328, delta=1)
            self.assertAlmostEqual(purpose['width'], 960, delta=1)
            self.assertGreater(report['mapping']['y'], purpose['y'] + purpose['height'])
        if name.startswith('task-'):
            overview, heading, stage = (report[key] for key in ('overview', 'stageHeading', 'stage'))
            self.assertGreater(overview['height'], 0)
            self.assertGreaterEqual(heading['y'], overview['y'] + overview['height'])
            self.assertGreaterEqual(stage['y'], heading['y'] + heading['height'])
            self.assertAlmostEqual(stage['x'], overview['x'], delta=2)
            self.assertAlmostEqual(stage['width'], overview['width'], delta=2)
            for control, row in ((report['addJobToList'], report['looseJobForm']), (report['addJob'], report['stageHead'])):
                self.assertGreaterEqual(control['height'], 32)
                self.assertGreater(control['width'], 24)
                self.assertGreaterEqual(control['y'], row['y'])
                self.assertLessEqual(control['y'] + control['height'], row['y'] + row['height'])
        if name == 'tools-edit':
            # Save stays below the settings, at the right edge of the form and the bottom edge of the pane.
            self.assertGreater(report['save']['x'], report['form']['x'] + 800)
            self.assertGreater(report['save']['y'], report['mapping']['y'] + report['mapping']['height'] - 1)
            self.assertGreater(report['save']['y'], report['foot']['y'])
            self.assertAlmostEqual(report['foot']['y'] + report['foot']['height'], report['viewport'][1], delta=1)

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
        self.assertLess(row['text'].index('백업 결과 조회'), row['text'].index('/backups'))
        self.assertEqual(self.text('[data-api-screen=list] h2'), 'API 명세 3개')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-api-screen=list] .ew-api-head')"))
        methods = self.browser.evaluate("""Object.fromEntries([...document.querySelectorAll('.ew-api-row')].map(row => {
          const style = getComputedStyle(row.querySelector('.ew-api-method'));
          return [row.dataset.method, [style.backgroundColor, style.color, getComputedStyle(row).backgroundColor]];}))""")
        # Reading is outlined and a request that changes something is filled; rows carry no tint.
        self.assertEqual(methods['GET'], ['rgba(0, 0, 0, 0)', 'rgb(29, 33, 40)', 'rgba(0, 0, 0, 0)'])
        self.assertEqual(methods['POST'], ['rgb(29, 33, 40)', 'rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)'])
        self.fill('[name=api-search]', '재처리')
        self.wait("document.querySelector('[data-api-screen=list] h2')?.textContent === 'API 명세 3개 중 1개'")
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-api-action=open]').length"), 1)
        self.fill('[name=api-search]', '사내')
        self.wait("document.querySelector('[data-api-screen=list] h2')?.textContent === 'API 명세 3개 중 3개'")
        opener = '[data-api-action=open][data-id="' + row['id'] + '"]'
        self.click(opener)
        self.wait("document.querySelector('[data-api-screen=detail]')?.textContent.includes('연결된 작업이 없습니다.')")
        self.assertEqual(self.text('[data-api-screen=detail] .ew-api-route').split(), ['GET', '사내', '백업', 'https://backup.example/backups'])
        self.assertEqual([line for line in self.text('[data-api-screen=detail] .ew-api-title').split('\n') if line],
                         ['백업 결과 조회', '백업 작업별 성공 여부와 완료 시각을 확인합니다.'])
        self.capture_state('tools-detail', '[data-api-screen=detail]')
        self.click('[data-api-action=edit]')
        self.assertEqual(self.read('[name=api-service_id]', 'value'), backup)
        self.assertEqual(self.read(url, 'value'), 'https://backup.example/backups')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-api-screen=edit] [data-api-advanced]')"))
        self.assertTrue(self.read('[data-api-action=save]', 'disabled'))
        self.assertTrue(self.read('[data-api-dirty]', 'hidden'))
        self.capture_state('tools-edit', '[data-api-screen=edit]')
        self.fill('[name=api-purpose]', '완료 시각과 처리 상태를 함께 확인합니다.')
        self.assertFalse(self.read('[data-api-action=save]', 'disabled'))
        self.assertFalse(self.read('[data-api-dirty]', 'hidden'))
        self.assertEqual(self.text('[data-api-dirty]'), '저장하지 않은 변경 있음')
        self.click('[data-api-action=save]')
        self.wait("document.querySelector('[data-api-screen=list]')")
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('[data-action=tools]')")
        self.open_catalog()
        self.click(opener)
        self.click('[data-api-action=edit]')
        self.assertEqual(self.read('[name=api-purpose]', 'value'), '완료 시각과 처리 상태를 함께 확인합니다.')

    def test_edit_save_row_stays_at_the_bottom_edge_and_settings_stay_readable_when_narrow(self):
        backup = self.register_service('사내 백업')
        api = self.seed_api(backup, 'GET', 'https://backup.example/backups', '백업 결과 조회',
                            '백업 작업별 성공 여부와 완료 시각을 확인합니다.',
                            inputs=[{'name': 'date', 'in': 'query', 'type': 'string', 'required': True, 'label': '조회 날짜'},
                                    {'name': 'status', 'in': 'query', 'type': 'string', 'required': False, 'label': '작업 상태'}],
                            result_path='items',
                            fields=[{'path': 'job_name', 'type': 'string', 'label': '작업 이름'},
                                    {'path': 'succeeded', 'type': 'boolean', 'label': '성공 여부'},
                                    {'path': 'finished_at', 'type': 'string', 'label': '완료 시각'}],
                            example={'items': [{'job_name': 'EMS 운영 DB 백업', 'succeeded': True, 'finished_at': '2026-11-05 02:14'}]})
        self.authoring_viewport(1920, 1080, overlay=False)
        self.open_catalog()
        self.click('[data-api-action=open][data-id="' + api['id'] + '"]')
        self.click('[data-api-action=edit]')
        self.wait("document.querySelector('[data-api-screen=edit] [data-api-mapping]')")

        def measure():
            return self.browser.evaluate("""(() => {
              const box = e => { const {x, y, width, height, right, bottom} = e.getBoundingClientRect(); return {x, y, width, height, right, bottom}; };
              const area = box(document.querySelector('#ees-work-designer > .ew-author-scroll'));
              const catalog = document.querySelector('[data-api-catalog]');
              return {columns:[...document.querySelectorAll('[data-api-mapping]>div')].map(box), area, catalog:box(catalog),
                foot:box(document.querySelector('.ew-api-foot')),
                controls:[...document.querySelectorAll('.ew-api-map :is(input,select)')].map(e => e.getBoundingClientRect().width),
                titles:[...document.querySelectorAll('.ew-api-map-head')].every(e => e.checkVisibility()),
                names:[...document.querySelectorAll('.ew-api-map label>span')].map(e => {
                  const {width, height, bottom} = e.getBoundingClientRect();
                  return {text:e.textContent, shown:width > 8 && height > 8, above:bottom <= e.parentElement.querySelector('input,select').getBoundingClientRect().y + 1};
                }),
                overflow:document.documentElement.scrollWidth > innerWidth ||
                  [...catalog.querySelectorAll('*')].some(e => e.getClientRects().length && e.getBoundingClientRect().right > area.right + 1)};
            })()""")

        wide = measure()
        self.assertAlmostEqual(wide['columns'][0]['y'], wide['columns'][1]['y'], delta=1)
        self.assertGreater(wide['columns'][1]['x'], wide['columns'][0]['right'] - 1)
        # These settings are shorter than the work area: the save row is still at its bottom edge, not under the settings.
        self.assertGreater(wide['foot']['y'], max(column['bottom'] for column in wide['columns']) + 40, wide)
        self.assertAlmostEqual(wide['foot']['bottom'], wide['area']['bottom'], delta=1)
        self.assertLessEqual(wide['catalog']['bottom'], wide['area']['bottom'] + 1)
        self.assertFalse(wide['overflow'])
        # Column titles name the controls here, so the controls' own names are for assistive technology only.
        self.assertTrue(wide['titles'])
        self.assertEqual(len(wide['names']), 19)
        self.assertFalse(any(name['shown'] for name in wide['names']), wide['names'])
        for width, height, overlay in ((1366, 768, False), (480, 800, True)):
            with self.subTest(width=width):
                self.authoring_viewport(width, height, overlay=overlay)
                self.wait("document.querySelector('[data-api-screen=edit] [data-api-mapping]')?.checkVisibility()")
                narrow = measure()
                # Six controls on a parameter line do not fit beside the result settings here: the columns stack.
                self.assertGreater(narrow['columns'][1]['y'], narrow['columns'][0]['bottom'] - 1, narrow['columns'])
                self.assertGreaterEqual(min(narrow['controls']), 56, narrow['controls'])
                self.assertFalse(narrow['overflow'])
                # Every control is named on screen: by the column titles, or by its own name once the lines wrap.
                self.assertEqual(narrow['titles'], width == 1366)
                for name in narrow['names']:
                    self.assertTrue(name['text'].strip())
                    self.assertEqual(name['shown'], width == 480, name)
                    if width == 480:
                        self.assertTrue(name['above'], name)
                # The settings are longer than the work area; the save row stays flush with its bottom edge.
                self.assertGreater(narrow['catalog']['bottom'], narrow['area']['bottom'])
                self.assertAlmostEqual(narrow['foot']['bottom'], narrow['area']['bottom'], delta=1)

        # A refused save is reported with the save row, in view without scrolling the long settings.
        self.fill('[name=api-url]', 'not a url')
        self.click('[data-api-action=save]')
        self.wait("document.querySelector('[data-api-screen=edit] .ew-api-error')")
        refused = self.browser.evaluate("""(() => {
          const box = e => { const {y, bottom} = e.getBoundingClientRect(); return {y, bottom}; };
          return {error:box(document.querySelector('[data-api-screen=edit] .ew-api-error')),
            foot:box(document.querySelector('.ew-api-foot')), area:box(document.querySelector('#ees-work-designer > .ew-author-scroll'))};
        })()""")
        self.assertGreater(refused['error']['y'], refused['area']['y'], refused)
        self.assertLessEqual(refused['error']['bottom'], refused['foot']['y'] + 1, refused)
        self.assertAlmostEqual(refused['foot']['bottom'], refused['area']['bottom'], delta=1, msg=refused)

    def test_wide_work_area_keeps_the_api_list_beside_the_opened_api(self):
        """From 1264px of work area the API list stays beside the opened API; narrower, the API replaces the list."""
        backup = self.register_service('사내 백업')
        retry = self.seed_api(backup, 'POST', 'https://backup.example/backups/retries', '실패 백업 재처리',
                              '실패한 백업 작업의 재처리를 요청합니다.')
        purpose = '백업 작업별 성공 여부와 완료 시각을 확인합니다.'
        api = self.seed_api(backup, 'GET', 'https://backup.example/backups', '백업 결과 조회', purpose,
                            inputs=[{'name': 'date', 'in': 'query', 'type': 'string', 'required': True, 'label': '조회 날짜'}],
                            result_path='items', fields=[{'path': 'job_name', 'type': 'string', 'label': '작업 이름'}])
        self.authoring_viewport(1920, 1080, overlay=False)
        self.open_catalog()
        row = '[data-api-action=open][data-id="%s"]'
        chat = "document.querySelector('[data-ees-source-shell]').dataset.eesChatState"
        split = "document.querySelector('[data-api-catalog]')?.dataset.apiSplit"
        width = "document.querySelector('#ees-work-authoring-panel').getBoundingClientRect().width"

        def layout():
            return self.browser.evaluate("""(() => {
              const box = e => { if (!e) return null; const r = e.getBoundingClientRect(); return {x:r.x, y:r.y, right:r.right, bottom:r.bottom, width:r.width}; };
              const pane = document.querySelector('.ew-api-pane'), main = document.querySelector('.ew-api-main');
              const area = document.querySelector('#ees-work-authoring-panel').getBoundingClientRect();
              return {pane:box(pane), main:box(main), foot:box(document.querySelector('.ew-api-foot')),
                current:[...document.querySelectorAll('.ew-api-row[aria-current=true] strong')].map(e => e.textContent),
                rows:pane ? pane.querySelectorAll('.ew-api-row').length : 0,
                address:!!pane?.querySelector('.ew-api-path')?.checkVisibility(),
                toList:!!document.querySelector('[data-api-catalog] [data-api-action=list]')?.checkVisibility(),
                title:(main || document.querySelector('[data-api-catalog]')).querySelector('.ew-api-head h2')?.textContent || '',
                overflow:document.documentElement.scrollWidth > innerWidth ||
                  [...document.querySelectorAll('[data-api-catalog] *')].some(e => e.getClientRects().length && e.getBoundingClientRect().right > area.right + 1)};
            })()""")

        # With the chat docked the work area is 1104px: the API replaces the list and links back to it.
        self.click(row % api['id'])
        self.wait("document.querySelector('[data-api-screen=detail]')?.textContent.includes('연결된 작업이 없습니다.')")
        single = layout()
        self.assertEqual((self.browser.evaluate(split), single['pane'], single['toList'], single['title']),
                         ('false', None, True, '백업 결과 조회'), single)
        # Closing the chat widens it to 1664px: the same API stays open and the list appears beside it.
        self.click('[data-ees-chat-close]')
        self.wait(chat + " === 'closed' && " + width + " === 1664 && " + split + " === 'true'")
        beside = layout()
        self.assertEqual((beside['pane']['x'], beside['pane']['width'], beside['main']['x'], beside['main']['right']),
                         (256, 420, 676, 1920), beside)
        self.assertEqual((beside['current'], beside['rows'], beside['title']), (['백업 결과 조회'], 2, '백업 결과 조회'), beside)
        # The 420px list shows the method and the name; the opened API is marked, so no link back to the list is needed.
        self.assertFalse(beside['address'] or beside['toList'] or beside['overflow'], beside)
        self.screenshot('ws3-ws4-wide')

        self.click('[data-api-action=edit]')
        self.wait("document.querySelector('[data-api-screen=edit][data-api-split=true] [data-api-mapping]')")
        self.wait("document.activeElement?.matches('.ew-api-main .ew-api-head h2')")
        editing = layout()
        self.assertAlmostEqual(editing['foot']['bottom'], editing['main']['bottom'], delta=1, msg=editing)
        self.assertGreaterEqual(editing['foot']['x'], editing['main']['x'])
        self.assertFalse(editing['overflow'], editing)
        self.screenshot('ws3-ws5-wide')

        # Another row is a way out of the editor, so unsaved changes are confirmed first, as with Cancel.
        changed = '완료 시각과 처리 상태를 함께 확인합니다.'
        self.fill('[name=api-purpose]', changed)
        self.click(row % retry['id'])
        self.wait("document.activeElement?.matches('.ew-api-main [data-api-action=stay]')")
        self.assertEqual(self.read('[data-api-catalog]', 'dataset.apiScreen'), 'edit')
        self.click('[data-api-action=stay]')
        self.wait("document.querySelector('[name=api-purpose]')?.value === " + json.dumps(changed))
        # What was typed and the place the editor was scrolled to survive the list leaving and returning
        # as the chat opens and closes. A short window makes the settings longer than the work area.
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 600, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait("innerHeight === 600 && document.querySelector('.ew-api-main').scrollHeight > document.querySelector('.ew-api-main').clientHeight + 140")
        self.browser.evaluate("document.querySelector('.ew-api-main').scrollTop = 140")
        self.click('[data-ees-chat-toggle]')
        self.wait(chat + " === 'docked' && " + width + " === 1104 && " + split + " === 'false'")
        self.assertEqual((self.read('[name=api-purpose]', 'value'), layout()['pane']), (changed, None))
        self.assertEqual(self.read('#ees-work-designer > .ew-author-scroll', 'scrollTop'), 140)
        self.click('[data-ees-chat-close]')
        self.wait(chat + " === 'closed' && " + width + " === 1664 && " + split + " === 'true'")
        self.assertEqual((self.read('[name=api-purpose]', 'value'), self.read('.ew-api-main', 'scrollTop')), (changed, 140))
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerHeight === 1080')
        self.click(row % retry['id'])
        self.wait("document.querySelector('.ew-api-main [data-api-action=discard]')")
        self.click('[data-api-action=discard]')
        self.wait("document.querySelector('[data-api-screen=detail] .ew-api-main .ew-api-head h2')?.textContent === '실패 백업 재처리'")
        self.assertEqual(layout()['current'], ['실패 백업 재처리'])
        # The opened row keeps keyboard focus, so the next row is one key away.
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('.ew-api-pane .ew-api-row[aria-current=true]')"))
        apis = asyncio.run(self.server.workflow.api_catalog.state(self.server.user))['apis']
        self.assertEqual(next(item for item in apis if item['id'] == api['id'])['purpose'], purpose)
        # Service management opened from the list returns to the opened API.
        self.click('[data-api-action=services]')
        self.wait("document.querySelector('dialog[data-api-modal]')?.matches(':modal')")
        self.click('dialog[data-api-modal] [data-api-action=list]')
        self.wait("document.querySelector('[data-api-screen=detail][data-api-split=true] .ew-api-main .ew-api-head h2')?.textContent === '실패 백업 재처리'")

    def test_open_workflow_connect_apis_and_persist_handoff(self):
        service = self.register_service('EMS 설비 이력')
        reader = self.seed_api(service, 'GET', 'https://ems.example/equipment/{equipmentId}/alarms',
            '설비 알람 조회', '설비에서 발생한 알람을 조회합니다.',
            inputs=[dict(name='equipmentId', label='설비 번호', required=True, type='string', **{'in':'path'}),
                    dict(name='hours', label='조회 기간', required=True, type='integer', **{'in':'query'})],
            fields=[dict(path='code', label='알람 코드', type='string'), dict(path='state', label='알람 상태', type='string')],
            example=[{'code':'F101','state':'점검 필요'}, {'code':'F205','state':'정지'}])
        writer = self.seed_api(service, 'POST', 'https://ems.example/equipment/{equipmentId}/alarms',
            '알람 확인 등록', '확인한 알람을 등록합니다.',
            inputs=[dict(name='equipmentId', label='설비 번호', required=True, type='string', **{'in':'path'}),
                    dict(name='code', label='알람 코드', required=True, type='string', **{'in':'body'})],
            fields=[dict(path='receipt', label='접수 번호', type='string')], example={'receipt':'ACK-104'})
        key = self.author(name='설비 알람 처리', start_fields=[
            {'id': 'target-equipment', 'name': '대상 설비 번호', 'type': 'text',
             'scope': 'run', 'required': True},
        ])
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
        add_job_to_list = '#ew-loose-job-editor [data-author-action=loose_apply]'
        add_job = '[data-stage-id=stage] .ew-stage-head > [data-author-action=add_job]'
        self.wait(f'document.querySelector({json.dumps(add_job_to_list)})?.checkVisibility()')
        self.assertFalse(self.read('[data-author-action=api_structure_edit]', 'isConnected'))
        self.assertFalse(self.read('.ew-work-content .ew-content-start-inputs', 'isConnected'))
        self.assertEqual(self.browser.evaluate("Array.from(document.querySelectorAll('.ew-author-tabs [role=tab]'), button => button.dataset.tab)"),
                         ['content', 'history'])
        first = '[data-job-id=job-0] [data-author-action=job_api_setup]'
        if not self.read(first, 'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        self.wait(f'document.querySelector({json.dumps(add_job)})?.checkVisibility()')
        self.capture_state('task-connection', first)
        self.assertFalse(self.read('[data-api-job-binding]', 'isConnected'))
        for job, op in (('job-0', reader), ('job-1', writer)):
            self.click('[data-job-id="' + job + '"] [data-author-action=job_api_setup]')
            self.click('[data-api-candidate="' + op['id'] + '"]')
            self.choose('[data-api-source="equipmentId"]', 'run_input:target-equipment')
            if job == 'job-1':
                self.choose('[data-api-source="code"]', 'result')
                self.choose('[data-api-result="code"]', '["job-0","code"]')
            self.click('#ees-work-dialog [data-dialog-confirm]')
            self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.capture_state('task-mapped', '[data-api-job-binding]')
        self.click('[data-job-id=job-0] [data-author-action=job_api_example]')
        self.wait("document.querySelector('#ees-work-dialog[open] .ew-api-result-example')?.textContent.includes('F101')")
        self.key('Escape', 27)
        self.click('[data-job-id=job-1] [data-author-action=job_api_setup][data-api-setup=inputs]')
        self.assertEqual(self.read('#ees-work-dialog [data-api-result="code"]', 'value'), '["job-0","code"]')
        self.assertEqual(self.read('#ees-work-dialog [data-api-source="equipmentId"]', 'value'),
                         'run_input:target-equipment')
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.click('.ew-procedure-menu summary')
        self.click('[data-author-action=execution_parameters]')
        self.wait("document.querySelector('#ees-work-dialog[open] [data-execution-parameter-uses]')")
        uses = self.text('#ees-work-dialog [data-execution-parameter-uses]')
        self.assertIn('설비 알람 조회', uses)
        self.assertIn('알람 확인 등록', uses)
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog[open]')")

        added_job_id = self.add_loose_job_ui('요청 등록 결과 확인')
        added_stage_id = self.group_jobs_ui('결과 검토', [added_job_id])
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        saved = self.state(workflow_id=key)['workflow']['draft']['nodes']
        self.assertEqual(saved['job-0']['api_binding']['operation_id'], reader['id'])
        self.assertEqual(saved['job-1']['api_binding']['operation_id'], writer['id'])
        for job_id in ['job-0', 'job-1']:
            self.assertEqual(saved[job_id]['api_binding']['inputs']['equipmentId'],
                             {'run_input': 'target-equipment'})
            self.assertFalse(any(field['id'] == 'target-equipment' for field in saved[job_id]['inputs']))
        source = saved['job-1']['api_binding']['inputs']['code']['result']
        self.assertEqual(source, {'job_id':'job-0', 'field':'code', 'confirmed':True})
        self.assertEqual(saved[added_stage_id]['name'], '결과 검토')
        self.assertEqual(saved[added_job_id]['parent'], added_stage_id)

        # The authored run field is collected once. The reader's hours still
        # belongs to the reader, so the start form must not collect it.
        revision = self.state(workflow_id=key)['workflow']['revision']
        self.command('publish_workflow', workflow_id=key, expected_revision=revision)
        self.refresh()
        self.click('[data-action=mode][data-mode=work]')
        self.open_sidebar()
        self.click('[data-action=workflow][data-workflow-id="' + key + '"]')
        self.click('[data-action=overview_start]')
        start_form = '#ees-work-start[data-inline-start]'
        target = start_form + ' [data-work-input][name=target-equipment]'
        self.wait("document.querySelector(" + json.dumps(target) + ")?.checkVisibility()")
        self.assertEqual(self.browser.evaluate("Array.from(document.querySelectorAll('#ees-work-start[data-inline-start] [data-work-input]'), input => input.name)"),
                         ['target-equipment'])
        self.fill(target, 'EQ-001')
        self.click(start_form + ' [type=submit]')
        self.wait("window.__eesNativeWorkV1.captureReference()?.run_id")
        run_id = self.browser.evaluate("window.__eesNativeWorkV1.captureReference().run_id")
        self.assertEqual(self.state(run_id=run_id)['run']['inputs'], {'target-equipment': 'EQ-001'})
        self.click('[data-action=stage_open][data-node-id=stage]')
        period = saved['job-0']['api_binding']['inputs']['hours']['input']
        period_control = '#stage-values-job-0 [data-work-input][name="' + period + '"]'
        self.wait("document.querySelector(" + json.dumps(period_control) + ")?.checkVisibility()")
        self.assertIn('EQ-001', self.text('#stage-values-job-0'))
        self.assertIn('시작할 때 입력', self.text('#stage-values-job-0 .ew-vd-given'))
        self.assertFalse(self.read('#stage-values-job-0 [name=target-equipment]', 'isConnected'))

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

    def test_confluence_readonly_import_mapping_and_execution(self):
        """Exercise the shipped content/children contract over authenticated loopback HTTPS."""
        directory = self.enterContext(tempfile.TemporaryDirectory())
        upstream = self.enterContext(confluence_provider(directory))
        self.enterContext(patch.dict(os.environ, {'SSL_CERT_FILE':upstream.ca,
            'EES_CONFLUENCE_AUTHORIZATION':upstream.bearer,
            'EES_WORK_API_SERVICES':json.dumps({'confluence': {'base_url':upstream.base_url, 'credential_headers':{'Authorization':'EES_CONFLUENCE_AUTHORIZATION'}}})}))
        spec = json.loads((Path(__file__).resolve().parents[1] / 'examples/confluence/confluence-readonly.openapi.json').read_text(encoding='utf-8'))
        spec['servers'][0]['url'] = upstream.base_url
        key = self.author(name='Confluence 점검 문서 확인', jobs=2)
        base = self.state(workflow_id=key)['workflow']
        definition = deepcopy(base['draft'])
        names = ['기준 문서 확인','하위 문서 목록 조회']
        for i, name in enumerate(names):
            definition['nodes']['job-'+str(i)].update(name=name, mode='tool')
        self.command('save_draft', workflow_id=key, expected_revision=base['revision'], definition=definition)
        self.authoring_viewport(1920,1080,overlay=False)
        self.open_catalog()
        self.click('[data-api-action=create]')
        self.click('[data-api-action=import]')
        self.click('[data-import-more] > summary')
        self.fill('[name=api-import_text]', json.dumps(spec,ensure_ascii=False))
        self.click('[data-api-action=import-text]')
        self.wait("document.querySelectorAll('[data-op-index]').length === 2")
        for i in range(2):
            self.click(f'[data-op-index="{i}"]')
        self.click('[data-api-action=import-confirm]')
        self.wait("document.querySelectorAll('[data-api-screen=list] [data-api-action=open]').length === 2")
        rows = self.browser.evaluate("[...document.querySelectorAll('[data-api-action=open]')].map(n=>({id:n.dataset.id,name:n.innerText}))")
        ids = [next(row['id'] for row in rows if name in row['name']) for name in names]
        self.click('[data-action=procedures]')
        self.click('[data-author-action=open][data-id="'+key+'"]')
        self.click('[data-author-action=tab][data-tab=content]')
        if not self.read('[data-job-id=job-0] [data-author-action=job_api_setup]', 'isConnected'):
            self.click('[data-author-action=stage_toggle][data-id=stage]')
        for i, id_ in enumerate(ids):
            self.click(f'[data-job-id=job-{i}] [data-author-action=job_api_setup]')
            self.click(f'[data-api-candidate="{id_}"]')
            if i == 0:
                self.choose('[data-api-source="id"]','input')
            else:
                self.choose('[data-api-source="id"]','result')
                self.choose('[data-api-result="id"]','["job-0","id"]')
                self.choose('[data-api-source="limit"]','constant')
                self.fill('[data-api-value="limit"]','5')
            self.click('#ees-work-dialog [data-dialog-confirm]')
            self.wait("!document.querySelector('#ees-work-dialog[open]')")
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('[data-author-status]')?.dataset.dirty === 'false'")
        saved = self.state(workflow_id=key)['workflow']
        jobs = saved['draft']['nodes']
        input_id = jobs['job-0']['api_binding']['inputs']['id']['input']
        self.assertEqual(jobs['job-1']['api_binding']['inputs']['id']['result']['field'],'id')
        self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
        run = self.start(key, inputs={input_id: PAGE_ID})
        self.refresh()
        self.click('[data-action=mode][data-mode=work]')
        self.check_confluence_results(key, run, 'job-0', 'job-1', upstream, 'confluence')

    def test_upgrade_shows_only_shipped_confluence_guide_and_starts_it_from_operations(self):
        """Exercise the operator's first run from an existing installation with old assets."""
        old_workflow = self.author(name='전환 전 업무', jobs=1)
        old_service = self.register_service('전환 전 서비스')
        self.seed_api(old_service, 'GET', 'https://previous.example/check', '전환 전 조회', '이전 목록 점검')
        directory = self.enterContext(tempfile.TemporaryDirectory())
        upstream = self.enterContext(confluence_provider(directory))
        actor = self.server.user['id']
        config = {'confluence-readonly-pilot': {'base_url': upstream.base_url + '/content',
                  'actor_ids': [actor], 'user_credential_headers': {actor: {'Authorization': 'EES_GUIDE_TEST_AUTH'}}}}
        self.enterContext(patch.dict(os.environ, {'SSL_CERT_FILE': upstream.ca,
            'EES_GUIDE_TEST_AUTH': upstream.bearer, 'EES_WORK_API_SERVICES': json.dumps(config)}))
        self.server.workflow = self.backend.WorkflowService(Path(self.temporary.name) / 'work.sqlite3',
            self.users.get, self.server.chats.get, native_bridge=self.bridge, confluence_guide=True)
        self.backend._service = self.server.workflow
        self.authoring_viewport(1920, 1080, overlay=False)
        self.refresh()
        self.open_catalog()
        api_names = self.browser.evaluate("[...document.querySelectorAll('[data-api-screen=list] .ew-api-row strong')].map(e=>e.textContent)")
        self.assertCountEqual(api_names, ['기준 문서 확인', '하위 문서 목록 조회'])
        retired = ('[data-api-action=legacy],.ew-draft-list,.ew-draft-legacy,'
                   '[data-author-action=tool_create],[data-author-action=draft_new],'
                   '[data-author-action=draft_import],[data-author-action=job_tool_setup]')
        self.assertFalse(self.browser.evaluate('!!document.querySelector(' + json.dumps(retired) + ')'))
        self.click('[data-api-action=create]')
        self.wait("document.querySelector('[name=api-url]')?.checkVisibility()")
        self.assertFalse(self.browser.evaluate('!!document.querySelector(' + json.dumps(retired) + ')'))
        self.click('[data-api-action=cancel]')
        self.wait("document.querySelector('[data-api-screen=list]')")
        # Simulate a stale/partial API response on a previously selected Tools tab.
        # The old server included admin data and had neither guide nor API catalog.
        # Loading failures must offer a retry instead of changing editor type.
        current_workspace = self.server.workflow.workspace_state
        async def stale_workspace(*args, **kwargs):
            payload = await current_workspace(*args, **kwargs)
            payload.pop('confluence_guide', None)
            return payload
        async def stale_operations(*_args, **_kwargs):
            return {'ok': True, 'tool_draft_phase': 3,
                    'tool_drafts': [{'id':'old-tool','name':'전환 전 코드 도구'}],
                    'shared_tools': [], 'all_tools': []}
        with (patch.object(self.server.workflow, 'workspace_state', stale_workspace),
              patch.object(self.server.workflow.operations, 'state', stale_operations)):
            self.refresh()
            self.wait("document.querySelector('#ees-work-designer [data-action=refresh]')?.checkVisibility()")
            self.assertFalse(self.browser.evaluate('!!document.querySelector(' + json.dumps(retired) + ')'))
            panel = self.text('#ees-work-designer')
            for label in ('기존 도구 관리','이전 방식 도구','기존 도구에서 가져오기','전환 전 코드 도구'):
                self.assertNotIn(label, panel)
        # The guide catalog has an independent read, including on retry after
        # an incomplete catalog response. Other integrations can stay offline.
        with patch.object(self.server.workflow.operations, 'state', new_callable=AsyncMock) as operations:
            operations.return_value = {'ok': False, 'error': {'code':'unavailable','message':'운영 상태 조회 실패'}}
            with patch.object(self.server.workflow.api_catalog, 'state', new_callable=AsyncMock,
                              return_value={'services': []}) as catalog:
                self.click('#ees-work-designer [data-action=refresh]')
                self.wait("document.querySelector('#ees-work-designer [data-action=refresh]')?.checkVisibility()")
                self.refresh()
                catalog.assert_awaited()
            self.click('#ees-work-designer [data-action=refresh]')
            self.wait("document.querySelector('[data-api-action=open][data-id=guide-confluence-page]')")
            self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-api-screen=list] .ew-api-row').length"), 2)
            operations.assert_not_awaited()
        self.click('[data-api-action=open][data-id=guide-confluence-page]')
        # A path is shown with its service; the route keeps the base-address wording as its description.
        self.assertEqual(self.text('[data-api-screen=detail] .ew-api-route').split()[-1], '/{id}')
        self.assertEqual(self.read('[data-api-screen=detail] .ew-api-route', 'title'), '서비스 기본 주소 + /{id}')
        self.click('[data-action=procedures]')
        key = 'guide-confluence-documents'
        self.wait("document.querySelector('[data-author-action=open][data-id=guide-confluence-documents]')")
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('.ew-author-list [data-author-action=open]')].map(e=>e.dataset.id)"), [key])
        self.click('[data-action=mode][data-mode=work]')
        self.click('[data-action=workflow][data-workflow-id=guide-confluence-documents]')
        self.assertNotIn(old_workflow, self.browser.evaluate("[...document.querySelectorAll('[data-action=workflow]')].map(e=>e.dataset.workflowId)"))
        self.click('[data-action=stage_open][data-node-id=documents]')
        # 2026-11-19: no window asks for the value. The job that asks for it is open under its row with the field
        # ready, and the job that waits for the first job's result cannot run yet.
        field = '#stage-values-page [data-work-input][name="page-id"]'
        no_window = "!document.querySelector('#ees-work-dialog[open]')"
        self.wait('document.activeElement?.matches(' + json.dumps(field) + ')')
        self.assertEqual(self.read(field, 'placeholder'), '예: 123456789')
        self.assertEqual(self.read('[data-stage-job=page]', 'dataset.expanded'), 'true')
        self.assertTrue(self.read('[data-stage-job=children] .ew-vd-run', 'disabled'))
        self.assertEqual(self.text('[data-stage-job=children] [data-decision-status]'), '대기')
        # 실행 without the value starts nothing and says so at the field.
        self.click('[data-stage-job=page] .ew-vd-run')
        self.wait("document.querySelector('#stage-values-page .ew-vd-ask-error')?.textContent === '값을 넣어 주세요'")
        self.assertEqual(self.read(field, 'ariaInvalid'), 'true')
        self.assertTrue(self.browser.evaluate(no_window + ' && !window.__eesNativeWorkV1.captureReference()?.run_id'))
        self.assertEqual(upstream.records, [])
        # Enter in the field does what the row's 실행 does: the round starts with the value and the job runs.
        self.click(field); self.browser.call('Input.insertText', {'text': PAGE_ID})
        self.wait("!document.querySelector('#stage-values-page .ew-vd-ask-error')")
        self.key('Enter', 13)
        self.wait("document.querySelector('#stage-values-page [data-stage-result]')?.innerText.includes(" + json.dumps(PAGE['title']) + ")")
        self.assertTrue(self.browser.evaluate(no_window))
        run_id = self.browser.evaluate('window.__eesNativeWorkV1.captureReference().run_id')
        run = self.state(run_id=run_id)['run']
        self.assertEqual(run['inputs'], {'page-id': PAGE_ID})
        self.assertEqual([(attempt['job_id'], attempt['status']) for attempt in run['attempts']], [('page', 'succeeded')])
        self.assertEqual(upstream.records, [('/rest/api/content/' + PAGE_ID, {}, True)])
        result = self.text('#stage-values-page [data-stage-result]')
        for word in ('문서 제목', PAGE['title'], '페이지 ID', PAGE_ID):
            self.assertIn(word, result)
        self.assertEqual(self.read(field, 'value'), PAGE_ID)
        self.screenshot('confluence-guide-page')
        # The answer is given on the row as before. The answered job closes and the next opens with the value it is
        # given, which it could not run without.
        self.click('[data-action=stage_verdict][data-job-id=page]')
        self.click('#ees-stage-verdict-menu [data-action=stage_decide][data-verdict=completed]')
        self.wait("document.querySelector('[data-stage-job=children]')?.dataset.expanded === 'true' && document.querySelector('[data-stage-job=page]')?.dataset.expanded === 'false'")
        given = self.text('#stage-values-children')
        self.assertIn(PAGE_ID, given); self.assertIn('기준 문서 확인에서', given)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#stage-values-children [data-work-input]')"))
        self.click('[data-stage-job=children] .ew-vd-run')
        self.wait("document.querySelector('#stage-values-children .ew-vd-rows')?.innerText.includes('주간 점검표')")
        rows = self.text('#stage-values-children .ew-vd-rows')
        for row in CHILDREN:
            self.assertIn(row['title'], rows)
        self.screenshot('confluence-guide-children')
        # The list is confirmed from its row with the reason the product asks for.
        self.click('[data-action=stage_confirm_list][data-job-id=children]')
        self.fill('#ees-list-confirm-reason', '하위 문서 두 건을 확인했습니다.')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('[data-action=stage_confirm_list]') && document.querySelector('[data-stage-job=children]')?.dataset.expanded === 'false'")
        final = self.state(run_id=run_id)['run']
        self.assertEqual(len(final['attempts']), 2)
        self.assertEqual([final['jobs'][job]['status'] for job in ('page', 'children')], ['completed', 'completed'])
        self.assertEqual(upstream.records, [
            ('/rest/api/content/' + PAGE_ID, {}, True),
            ('/rest/api/content/' + PAGE_ID + '/child/page', {'limit': ['5']}, True)])
        # The name opens and closes the area; the way to the job screen is 자세히 at its end.
        self.click('[data-stage-job=children] .ew-vd-name')
        self.click('#stage-under-children .ew-vd-more [data-action=job]')
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes('주간 점검표')")
        self.assertEqual(self.text('#ees-work-panel h2'), run['definition']['nodes']['children']['name'])

    def check_confluence_results(self, key, run, page_job, children_job, upstream, capture_name):
        self.open_run(key, run, job=page_job)
        self.assertEqual(upstream.records, [])
        self.click('[data-action=execute]')
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes(" + json.dumps(PAGE['title']) + ")")
        page_table = self.text('.ew-api-table')
        self.assertIn('페이지 ID',page_table)
        self.assertIn(PAGE_ID,page_table)
        self.screenshot(capture_name + '-page')
        self.click('[data-action=confirm]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('[data-action=confirm]')")
        self.open_run(key, run, job=children_job)
        self.click('[data-action=execute]')
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes('주간 점검표')")
        child_table = self.text('.ew-api-table')
        for row in CHILDREN:
            self.assertIn(row['title'],child_table)
        self.screenshot(capture_name + '-children')
        self.click('[data-action=confirm_list]')
        self.fill('#ees-list-confirm-reason', '하위 문서 두 건을 확인했습니다.')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('[data-action=confirm_list]')")
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-panel')")
        self.click('[data-action=mode][data-mode=work]')
        self.open_run(key, run, job=children_job)
        self.wait("document.querySelector('.ew-api-table')?.innerText.includes('주간 점검표')")
        final = self.state(run_id=run['id'])['run']
        self.assertEqual(len(final['attempts']),2)
        self.assertEqual([final['jobs'][job]['status'] for job in (page_job, children_job)], ['completed','completed'])
        self.assertEqual(upstream.records, [
            ('/rest/api/content/'+PAGE_ID,{},True),
            ('/rest/api/content/'+PAGE_ID+'/child/page',{'limit':['5']},True)])
