"""Current Figma Native UI regressions replacing retired demo/recursive panels.

The name remains the CI entry point. Actual built Svelte/Tiptap/UI assets and
real EES SQLite commands run here; Native account and model HTTP are fixtures.
"""
import json
from ees_work_integrated_fixture import IntegratedNativeCase


class EESWorkNativeBrowserTests(IntegratedNativeCase):
    def test_empty_state_has_no_seed_run_or_fake_success(self):
        self.assertEqual(self.state()['workflows'], [])
        self.assertEqual(self.state()['runs'], [])
        self.assertIn('등록된 업무 절차가 없습니다', self.text('#ees-work-entry'))
        self.assertIn('지금 처리할 내 업무가 없습니다', self.text('#ees-work-panel'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=execute],[data-action=confirm]')"))
        self.assertEqual([x for x in self.server.workspace_commands if x['action'] != 'save_ui'], [])
        self.screenshot('integrated-empty-native')

    def test_native_three_regions_fonts_and_narrow_geometry(self):
        for width in (1920, 1440, 1180):
            with self.subTest(width=width):
                self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
                self.browser.evaluate('document.fonts.ready.then(()=>true)')
                values = self.browser.evaluate("(()=>{const selectors=['#sidebar','#chat-input','#ees-work-panel'];return selectors.map(selector=>{const e=document.querySelector(selector),r=e.getBoundingClientRect(),s=getComputedStyle(e);return {selector,x:r.x,y:r.y,w:r.width,h:r.height,font:s.fontFamily,display:s.display};})})()")
                for item in values:
                    self.assertGreater(item['w'], 50, item); self.assertGreaterEqual(item['x'], -1, item)
                    self.assertLessEqual(item['x'] + item['w'], width + 2, item)
                self.assertGreater(values[1]['x'], values[0]['x'], values)
                self.assertGreater(values[2]['x'], values[1]['x'], values)
                self.screenshot('integrated-layout-' + str(width))

    def test_scope_dialog_escape_cancel_and_chat_draft_preservation(self):
        self.command('save_factory', factory_id='factory-one', system_id='EMS', name='합성 공장')
        self.refresh(); self.fill('#chat-input', '전송 전 개인 대화 내용')
        self.click('#ees-work-site-trigger')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertTrue(self.browser.evaluate("document.activeElement?.hasAttribute('data-dialog-close')"))
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')?.open")
        self.assertEqual(self.text('#chat-input'), '전송 전 개인 대화 내용')
        self.click('#ees-work-site-trigger')
        self.click('[data-action="choose_factory"][data-factory-id="factory-one"]')
        self.wait("document.querySelector('#ees-work-site-trigger')?.innerText.includes('합성 공장')")
        self.assertEqual(self.text('#chat-input'), '전송 전 개인 대화 내용')
        self.assertEqual(self.state()['runs'], [])

    def test_input_save_is_not_execute_and_repeat_click_is_single_write(self):
        key = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}]); run = self.start(key)
        self.open_run(key, run); self.fill('[data-work-input][name="note"]', '이번 값')
        self.server.delay_next_action = True
        self.server.action_response_hold.clear()
        self.addCleanup(self.server.action_response_hold.set)
        self.click('[data-action="save_inputs"]')
        self.assertTrue(self.server.action_response_started.wait(5))
        self.assertTrue(self.read('[data-action="save_inputs"]', 'disabled'))
        point = self.browser.evaluate("(()=>{const r=document.querySelector('[data-action=save_inputs]').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()")
        for kind in ('mousePressed','mouseReleased'):
            self.browser.call('Input.dispatchMouseEvent',{'type':kind,'button':'left','clickCount':1,**point})
        self.server.action_response_hold.set()
        self.wait("!document.querySelector('[data-action=save_inputs]')?.disabled")
        self.wait("document.querySelector('[data-work-input][name=note]')?.value === '이번 값'")
        saved = self.state(run_id=run['id'])['run']
        self.assertEqual(saved['inputs']['note'], '이번 값')
        self.assertEqual(saved['attempts'], []); self.assertNotEqual(saved['jobs']['job-0']['status'], 'completed')
        self.assertEqual(len([x for x in self.server.workspace_commands if x['action'] == 'save_inputs']), 1)
        self.assertEqual(self.server.completions, [])
        self.screenshot('integrated-saved-input-not-execution')

    def test_enter_in_work_input_does_not_send_chat_or_run_job(self):
        key = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}]); run = self.start(key)
        self.open_run(key, run); self.fill('[data-work-input][name="note"]', '작성 중')
        self.click('[data-work-input][name="note"]'); self.key('Enter', 13)
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'], [])
        self.assertEqual(self.server.completions, [])
        self.assertFalse([x for x in self.server.workspace_commands if x['action'] in {'execute', 'execute_job', 'human_confirm'}])

    def test_human_cancel_then_explicit_confirm_and_history(self):
        key = self.author(); run = self.start(key); self.open_run(key, run)
        self.click('[data-action="confirm"]'); self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertTrue(self.browser.evaluate("document.activeElement?.hasAttribute('data-dialog-close')"))
        self.key('Escape', 27)
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'], [])
        self.click('[data-action="confirm"]'); self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-panel .ew-status')?.textContent.includes('완료')")
        saved = self.state(run_id=run['id'])['run']; self.assertEqual(saved['jobs']['job-0']['status'], 'completed')
        self.assertEqual(len(saved['attempts']), 1)
        self.click('[data-action="tab"][data-tab="history"]')
        self.wait("!!document.querySelector('.ew-history')")
        self.click('.ew-history summary'); self.assertIn('실행 당시 절차', self.text('#ees-work-panel'))
        self.screenshot('integrated-human-confirm-history')

    def test_navigation_preserves_local_input_and_does_not_change_business_revision(self):
        key = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}]); run = self.start(key)
        self.open_run(key, run); self.fill('[data-work-input][name="note"]', '아직 저장하지 않음')
        self.click('[data-action="overview"]'); self.click('[data-action="job"][data-job-id="job-1"]')
        self.assertNotEqual(self.read('[data-work-input][name="note"]', 'value'), '아직 저장하지 않음')
        self.click('[data-action="overview"]'); self.click('[data-action="job"][data-job-id="job-0"]')
        self.assertEqual(self.read('[data-work-input][name="note"]', 'value'), '아직 저장하지 않음')
        current = self.state(run_id=run['id'])['run']; self.assertEqual(current['revision'], run['revision']); self.assertEqual(current['inputs'], {})

    def test_lookup_failure_removes_previously_visible_private_evidence(self):
        key = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}]); run = self.start(key, inputs={'note': 'synthetic-private-evidence'})
        self.command('human_confirm', run_id=run['id'], job_id='job-0', expected_revision=run['revision'])
        self.open_run(key, run); self.click('[data-action="tab"][data-tab="history"]'); self.click('.ew-history summary')
        self.assertIn('synthetic-private-evidence', self.text('#ees-work-panel'))
        self.server.workspace_error = '조회 실패 · 이전 자료를 표시하지 않습니다'; self.refresh()
        self.assertNotIn('synthetic-private-evidence', self.text('#ees-work-panel'))
        self.assertIn('조회 실패', self.text('#ees-work-panel'))
        self.assertEqual(len(self.state(run_id=run['id'])['run']['attempts']), 1)

    def test_scope_and_history_do_not_bind_or_replace_native_chat(self):
        original = json.dumps(self.server.chats, sort_keys=True)
        key = self.author(); run = self.start(key); self.open_run(key, run)
        self.click('[data-action="records"]')
        self.assertEqual(json.dumps(self.server.chats, sort_keys=True), original)
        self.assertEqual(self.state(run_id=run['id'])['run'].get('chat_links', []), [])
        self.assertFalse([x for x in self.server.workspace_commands if x['action'] == 'link_chat'])
        self.assertEqual(self.browser.evaluate('location.pathname'), '/c/existing-chat')

    def test_sidebar_close_restore_retains_chat_and_work_input(self):
        key = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}]); run = self.start(key)
        self.open_run(key, run); self.fill('[data-work-input][name="note"]', '보존할 업무 입력')
        self.fill('#chat-input', '보존할 대화 초안')
        self.click('[data-action="close_panel"]')
        self.wait("document.querySelector('#ees-work-panel')?.hidden")
        self.click('[data-action="open_panel"]')
        self.wait("!document.querySelector('#ees-work-panel')?.hidden")
        self.assertEqual(self.text('#chat-input'), '보존할 대화 초안')
        self.assertEqual(self.read('[data-work-input][name="note"]', 'value'), '보존할 업무 입력')
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'], [])

    def test_native_message_send_stream_and_work_panel_are_independent(self):
        key = self.author(); run = self.start(key); self.open_run(key, run)
        self.fill('#chat-input', '합성 Native 대화 왕복')
        self.click('#send-message-button')
        self.wait("document.querySelector('#chat-input')?.textContent.trim() === ''")
        self.assertEqual(len(self.server.completions), 1)
        self.assertEqual(self.server.completions[0]['user_message']['content'], '합성 Native 대화 왕복')
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'], [])
        self.assertIn('합성 작업 0', self.text('#ees-work-panel'))
        self.screenshot('integrated-native-chat-and-work')

    def test_model_zero_one_multiple_use_native_source_without_demo_presets(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.server.models = [{'id': 'fixture-' + str(i), 'name': '합성 모델 ' + str(i), 'owned_by': 'openai'} for i in range(count)]
                self.navigate('/c/other-chat' if count % 2 else '/c/existing-chat')
                self.wait("document.body?.dataset.eesModelCount === " + json.dumps(str(count)))
                self.assertNotIn('ees_demo_', json.dumps(self.server.models))
                self.assertEqual(self.state()['workflows'], [])
