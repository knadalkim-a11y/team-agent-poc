"""Built Native authoring UI with real workspace/operations SQLite commands.

Reconstructed from retained session source/patch text after workspace loss;
requires new verification and new screenshots. Native session and external read
transport are synthetic. The complete CLI gate verifies real login separately.
"""
import asyncio
from copy import deepcopy
import json
from uuid import UUID, uuid4

from ees_work_integrated_fixture import IntegratedNativeCase


class FigmaAuthoringNativeTests(IntegratedNativeCase):
    def operations(self):
        return asyncio.run(self.server.workflow.operations.state(self.server.user, system_id='EMS'))

    def tool_connections(self):
        """Register metadata only in this synthetic transport, never Native assets."""
        self.connected_tools = []

        def function(tool_id, name, function_name, kind):
            return {'name': name, 'function_name': function_name, 'kind': kind,
                    'reference': {'tool_id': tool_id, 'function': function_name,
                                  'revision': 1, 'content_hash': 'a' * 64,
                                  'schema_hash': 'b' * 64},
                    'schema': {'type': 'object', 'properties': {
                        'target': {'type': 'string', 'title': '대상'}}, 'required': ['target']}}

        async def registered(actor):
            return deepcopy(self.connected_tools)

        async def inspect(actor, tool_id, function_name):
            item = next((item for item in self.connected_tools
                         if item['reference']['tool_id'] == tool_id
                         and item['reference']['function'] == function_name), None)
            if item is None:
                raise self.backend.WorkflowError('native_access_denied', '연결된 기능을 확인해 주세요.')
            return deepcopy(item)

        self.bridge.registered_capabilities = registered
        self.bridge.inspect = inspect
        self.bridge.inspect_registered = inspect
        return function

    def tool_command(self, action, revision=0, **kwargs):
        result = asyncio.run(self.server.workflow.operations.command(self.server.user, {
            'action': action, 'expected_revision': revision,
            'request_id': str(uuid4()), **kwargs}))
        self.assertTrue(result['ok'], result)
        return result

    def open_tools(self):
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-action="tools"]')
        self.wait("document.querySelector('[data-author-action=tool_create]')")

    def screenshot(self, label, *, wait_for_fonts=True):
        directory = super().screenshot(label, wait_for_fonts=wait_for_fonts)
        observed = self.browser.evaluate("""(()=>{
          const panel=document.querySelector('#ees-work-panel');
          const author=document.querySelector('#ees-work-designer');
          const active=document.activeElement;
          const region=e=>e?{text:e.innerText,html:e.outerHTML}:null;
          const geometry=selector=>{const e=document.querySelector(selector);if(!e)return null;const r=e.getBoundingClientRect(),c=getComputedStyle(e);return {x:r.x,y:r.y,width:r.width,height:r.height,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,clientHeight:e.clientHeight,scrollHeight:e.scrollHeight,scrollTop:e.scrollTop,overflowY:c.overflowY,background:c.backgroundColor,outline:c.outline,focusVisible:e.matches(':focus-visible'),borderWidth:c.borderWidth,borderRadius:c.borderRadius,minHeight:c.minHeight};};
          return {scope:'built Native UI; synthetic session and data',
            path:location.pathname,ready:document.readyState,fonts:document.fonts.status,
            nativeMount:{chatPane:!!document.querySelector('#chat-container #chat-pane'),sidebarSearch:!!document.querySelector('#sidebar-search-button'),sidebarToggle:!!document.querySelector('#sidebar-toggle-button')},
            viewport:[innerWidth,innerHeight],active:{tag:active?.tagName,id:active?.id,name:active?.name},
            panel:region(panel),authoring:region(author),
            layout:{panel:geometry('#ees-work-panel'),scroll:geometry('.ew-author-scroll'),radio:geometry('[name=procedure_template]:checked'),selected:geometry('.ew-procedure-card[data-selected=true]'),unselected:geometry('.ew-procedure-card[data-selected=false]'),name:geometry('#ew-procedure-name'),footer:geometry('#ees-work-designer>footer'),back:geometry('.ew-author-procedure-start .ew-author-back'),questionGroup:geometry('.ew-procedure-questions'),firstQuestion:geometry('.ew-procedure-questions>button'),cardGaps:[...document.querySelectorAll('.ew-procedure-choices>.ew-procedure-card')].filter(e=>e.previousElementSibling).map(e=>e.getBoundingClientRect().top-e.previousElementSibling.getBoundingClientRect().bottom)},
            nativeDraft:window.__eesNativeDraftV1?.read?.(),
            nativeInput:region(document.querySelector('#chat-input'))};
        })()""")
        (directory / (label + '-dom.json')).write_text(
            json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return directory

    def test_easy_tools_unconnected_example_and_live_read_confirmation_roundtrip(self):
        function = self.tool_connections()
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_create"]')
        self.assertIn('예시에서 시작', self.text('#ees-work-designer'))
        self.assertIn('아직 연결된 기능이 없습니다', self.text('#ees-work-designer'))
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('[data-author-action=tool_example]').length"), 4)
        self.assertEqual(self.operations()['tools'], [])
        self.screenshot('easy-tools-empty-starter')
        self.click('[data-author-action="tool_example"][data-id="collection-queue"]')
        self.assertIn('필요한 기능이 아직 연결되지 않았습니다', self.text('#ees-work-designer'))
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        unconnected = self.operations()['tools'][0]
        self.assertEqual(unconnected['name'], '수집 대기열 조회')
        self.assertEqual(unconnected['kind'], 'read')
        self.assertEqual(unconnected['reference'], {})
        self.assertEqual(unconnected['state'], 'draft')
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        self.assertEqual([body['action'] for body in self.server.workspace_commands], ['tool_save'])
        self.screenshot('easy-tools-unconnected-saved')

        self.connected_tools.append(function('jira', '합성 Jira', 'jira_search_crs', 'read'))
        self.refresh()
        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.wait("document.querySelector('[data-author-action=tool_pick]')")
        self.assertEqual(self.read('[data-author-action="tool_example"][data-id="jira-query"] .ew-tool-connection', 'dataset.connected'), 'true')
        self.fill('#ew-tool-search', 'jira_search')
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('[data-author-action=tool_pick]')].map(e=>e.dataset.id)"), ['jira:jira_search_crs'])
        self.click('[data-author-action="tool_pick"][data-id="jira:jira_search_crs"]')
        self.fill('#ew-author-tool [name=name]', '합성 CR 확인')
        self.assertIn('하는 일: 정보 읽기', self.text('#ees-work-designer'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ew-author-tool [name=kind],#ew-author-tool [name=timeout_seconds],#ew-author-tool [name=responsible_user_id]')"))
        self.assertFalse(self.read('.ew-tool-advanced', 'open'))
        self.assertEqual(self.read('#ew-author-tool [name=guide_url]', 'value'), '')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('[data-author-action=tool_review]')?.disabled === false")
        self.screenshot('easy-tools-read-ready')
        self.click('[data-author-action="tool_review"]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('담당자 확인 대기')")
        saved = next(item for item in self.operations()['tools'] if item['name'] == '합성 CR 확인')
        self.assertEqual(saved['reference'], self.connected_tools[0]['reference'])
        self.assertEqual(saved['input_schema'], self.connected_tools[0]['schema'])
        self.assertEqual(saved['state'], 'review_requested')
        self.assertEqual(saved.get('guide_url', ''), '')
        self.assertNotEqual(saved['id'], unconnected['id'])
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.server.completions, [])

    def test_easy_request_choices_missing_output_and_legacy_time_values_roundtrip(self):
        function = self.tool_connections()
        primary = function('ops', '합성 EES', 'restart_service', 'request')
        self.connected_tools.extend([primary,
            function('ops', '합성 EES', 'restart_status', 'request'),
            function('unrelated', '다른 연결', 'other_status', 'request')])
        legacy = self.tool_command('tool_save', tool={
            'name': '기존 요청 도구', 'system_id': 'EMS', 'kind': 'request',
            'reference': primary['reference'], 'status_function': 'restart_status',
            'responsible_user_id': self.server.user['id'],
            'guide_url': 'https://example.invalid/guide',
            'output_schema': {'type': 'object', 'properties': {'kept': {'type': 'boolean'}}},
            'timeout_seconds': 47, 'completion_wait_seconds': 651})['tool']
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_open"][data-id="' + legacy['id'] + '"]')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[name=timeout_seconds],[name=completion_wait_seconds],[name=kind]')"))
        self.fill('#ew-author-tool [name=description]', '기존 값을 보존하는 설명 수정')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        saved = next(item for item in self.operations()['tools'] if item['id'] == legacy['id'])
        self.assertEqual(saved['timeout_seconds'], 47)
        self.assertEqual(saved['completion_wait_seconds'], 651)
        self.assertEqual(saved['output_schema'], legacy['output_schema'])
        self.assertEqual(saved['description'], '기존 값을 보존하는 설명 수정')

        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_pick"][data-id="ops:restart_service"]')
        self.assertIn('하는 일: EES에 작업 부탁', self.text('#ees-work-designer'))
        self.assertEqual(self.read('[name=status_function]', 'value'), 'restart_status')
        self.assertEqual(self.browser.evaluate("[...document.querySelector('[name=status_function]').options].map(e=>e.value)"), ['', 'restart_status'])
        self.assertIn(self.server.user['name'], self.text('#ees-work-designer'))
        self.assertFalse(self.read('.ew-tool-advanced', 'open'))
        self.assertEqual(self.read('[name=output_schema_json]', 'value'), '')
        self.fill('#ew-author-tool [name=guide_url]', 'https://example.invalid/request-guide')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('#ees-work-designer footer')?.textContent.includes('저장된 초안')")
        self.assertIn('결과 형식이 비어 있습니다', self.text('#ew-tool-submit-reason'))
        self.assertTrue(self.read('[data-author-action="tool_review"]', 'disabled'))
        created = next(item for item in self.operations()['tools'] if item['id'] != legacy['id'])
        self.assertEqual(created['status_function'], 'restart_status')
        self.assertEqual(created['responsible_user_id'], self.server.user['id'])
        self.assertNotIn('output_schema', created)
        self.screenshot('easy-tools-request-output-required')
        self.click('.ew-tool-advanced > summary')
        self.fill('#ew-author-tool [name=output_schema_json]', '{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}')
        self.click('[data-author-action="tool_save"]')
        self.wait("document.querySelector('[data-author-action=tool_review]')?.disabled === false")
        self.screenshot('easy-tools-request-ready')
        self.click('[data-author-action="tool_review"]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('담당자 확인 대기')")
        submitted = next(item for item in self.operations()['tools'] if item['id'] == created['id'])
        self.assertEqual(submitted['state'], 'review_requested')
        self.assertEqual(submitted['status_reference'], self.connected_tools[1]['reference'])
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.server.completions, [])

    def test_help_keyboard_escape_and_questions_fill_native_composer_without_sending(self):
        def enter_button():
            # CDP needs Enter's character data to synthesize the native button
            # activation (keydown alone does not emit keypress/click).
            for kind in ('keyDown', 'keyUp'):
                self.browser.call('Input.dispatchKeyEvent', {
                    'type': kind, 'key': 'Enter', 'code': 'Enter',
                    'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13,
                    **({'text': '\r', 'unmodifiedText': '\r'} if kind == 'keyDown' else {}),
                })

        self.tool_connections()
        self.fill('#chat-input', '보존할 개인 대화 초안')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.refresh()
        self.open_tools()
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_example"][data-id="jira-query"]')
        self.click('#ew-author-tool [name=name]')
        for _ in range(12):
            self.key('Tab', 9)
            if self.browser.evaluate("document.activeElement?.matches('[data-author-action=help][data-id=read_tool]')"):
                break
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-author-action=help][data-id=read_tool]')"))
        enter_button()
        self.wait("document.querySelector('#ees-work-help')")
        self.assertEqual(self.read('#ees-work-help', 'getAttribute("role")'), 'dialog')
        source_term = next(item for item in self.state()['help']['terms'] if item['id'] == 'read_tool')
        self.assertEqual(self.text('#ees-work-help .ew-help-summary'), source_term['summary'])
        self.assertIn(source_term['example'], self.text('#ees-work-help .ew-help-example'))
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-help-close]')"))
        self.screenshot('easy-tools-help-keyboard-open')
        # Normal workspace refresh replaces authoring controls. An open help
        # popover must keep its content and return focus to the current button.
        self.refresh()
        self.wait("document.querySelector('#ees-work-help')")
        self.assertEqual(self.text('#ees-work-help .ew-help-summary'), source_term['summary'])
        self.key('Escape', 27)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-help')"))
        focus = self.browser.evaluate("(()=>{const e=document.activeElement,s=getComputedStyle(e);return {trigger:e.matches('[data-author-action=help][data-id=read_tool]'),visible:e.matches(':focus-visible'),style:s.outlineStyle,width:parseFloat(s.outlineWidth)};})()")
        self.assertTrue(focus['trigger'], focus)
        self.assertTrue(focus['visible'], focus)
        self.assertNotEqual(focus['style'], 'none', focus)
        self.assertGreater(focus['width'], 0, focus)
        enter_button()
        self.wait("document.querySelector('#ees-work-help')")
        self.click('#ees-work-help [data-help-ask]')
        self.wait("window.__eesNativeDraftV1?.read()?.prompt?.includes('read_tool')")
        after = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        directory = self.screenshot('easy-tools-help-native-draft')
        (directory / 'easy-tools-help-draft-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native composer; synthetic personal draft and transport',
            'before': before, 'after': after, 'completion_count': len(self.server.completions),
            'input': self.browser.evaluate("(()=>{const e=document.querySelector('#chat-input');return {html:e?.innerHTML,text:e?.textContent};})()"),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(after['prompt'].startswith(before['prompt']))
        # Native Tiptap serializes a blank paragraph with interior spaces.
        self.assertRegex(after['prompt'][len(before['prompt']):], r'^\n[ \t]*\nEES Work 도움말')
        for text in ('도움말 용어 ID: read_tool', '현재 화면:', '초안 이름: Jira 조회', '하는 일: 정보 읽기'):
            self.assertIn(text, after['prompt'])
        self.assertEqual({key: value for key, value in before.items() if key != 'prompt'},
                         {key: value for key, value in after.items() if key != 'prompt'})
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.operations()['tools'], [])
        self.click('.ew-tool-advanced > summary')
        self.click('[data-author-action="help"][data-id="output_schema"]')
        self.wait("document.querySelector('#ees-work-help')")
        self.refresh()
        self.wait("document.querySelector('.ew-tool-advanced')?.open && document.querySelector('#ees-work-help')")
        self.assertEqual(self.text('#ees-work-help-title'), '결과 형식')
        self.screenshot('easy-tools-help-advanced-refresh')
        self.key('Escape', 27)
        advanced_focus = self.browser.evaluate("(()=>{const e=document.activeElement;return {trigger:e.matches('[data-author-action=help][data-id=output_schema]'),visible:e.getClientRects().length>0,open:document.querySelector('.ew-tool-advanced')?.open};})()")
        self.assertEqual(advanced_focus, {'trigger': True, 'visible': True, 'open': True})
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-help')"))
        self.click('[data-author-action="tool_list"]')
        self.click('[data-author-action="tool_create"]')
        self.click('[data-author-action="tool_question"][data-id="1"]')
        self.wait("window.__eesNativeDraftV1?.read()?.prompt?.includes('Jira에서 CR 승인 상태를 확인하는 도구를 만들고 싶어')")
        question = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertTrue(question['prompt'].startswith(after['prompt']))
        self.assertRegex(question['prompt'][len(after['prompt']):], r'^\n[ \t]*\nJira에서 CR 승인 상태')
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.operations()['tools'], [])

    def test_procedure_example_preview_reentry_and_native_question_create_an_unpublished_draft(self):
        self.browser.evaluate("Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});true")
        self.fill('#chat-input', '새 절차 전에 작성한 개인 질문')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action="mode"][data-mode="author"]')
        original_reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        original_panel_width = self.browser.evaluate("document.querySelector('#ees-work-panel').getBoundingClientRect().width")
        self.click('[data-author-action="create"]')
        self.wait("document.querySelector('.ew-procedure-start')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-dialog')"))
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('[name=procedure_template]')].map(e=>e.value)"),
                         ['delivery_review', 'factory_rollout', 'daily_check', 'blank'])
        self.assertEqual(self.read('[name=procedure_template]:checked', 'value'), 'factory_rollout')
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '신규 공장 횡전개')
        for stage in ('사전준비', 'AP·DB 인프라 준비', '시스템 설치', '시스템 간 인터페이스 확인'):
            self.assertIn(stage, self.text('.ew-procedure-stages'))
        self.assertEqual(self.state()['workflows'], [])
        self.assertEqual(self.operations()['schedules'], [])
        self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference().kind'), 'help')
        self.wait("Math.abs(document.querySelector('#ees-work-panel').getBoundingClientRect().width-580)<1.5")
        layout = self.browser.evaluate("""(()=>{const panel=document.querySelector('#ees-work-panel'),scroll=document.querySelector('.ew-author-scroll'),radio=document.querySelector('[name=procedure_template]:checked');return {radioWidth:radio.getBoundingClientRect().width,radioHeight:radio.getBoundingClientRect().height,selected:getComputedStyle(document.querySelector('.ew-procedure-card[data-selected=true]')).backgroundColor,unselected:getComputedStyle(document.querySelector('.ew-procedure-card[data-selected=false]')).backgroundColor,overflow:getComputedStyle(scroll).overflowY,scrollHeight:scroll.scrollHeight,clientHeight:scroll.clientHeight,panelOverflow:panel.scrollWidth-panel.clientWidth,cardGaps:[...document.querySelector('.ew-procedure-choices').children].slice(1).map(e=>e.getBoundingClientRect().top-e.previousElementSibling.getBoundingClientRect().bottom)};})()""")
        self.assertAlmostEqual(layout['radioWidth'], 16, delta=0.5)
        self.assertAlmostEqual(layout['radioHeight'], 16, delta=0.5)
        self.assertNotEqual(layout['selected'], layout['unselected'])
        self.assertIn(layout['overflow'], ('auto', 'scroll'))
        self.assertGreaterEqual(layout['scrollHeight'], layout['clientHeight'])
        self.assertLessEqual(layout['panelOverflow'], 1)
        self.assertEqual(len(layout['cardGaps']), 2)
        self.assertTrue(all(abs(gap)<=1/64 for gap in layout['cardGaps']), layout['cardGaps'])
        self.screenshot('procedure-examples-factory-preview')
        # Native radio navigation must select and repaint the corresponding
        # preview without creating or publishing any workflow.
        self.click('[name=procedure_template][value=factory_rollout]')
        self.key('ArrowUp', 38)
        self.wait("document.querySelector('[name=procedure_template]:checked')?.value === 'delivery_review'")
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '배포 산출물 점검')
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[name=procedure_template]:checked:focus-visible')"))
        self.assertTrue(self.browser.evaluate("parseFloat(getComputedStyle(document.activeElement).outlineWidth)>0"))
        self.screenshot('procedure-examples-keyboard-preview')
        self.key('ArrowDown', 40)
        self.wait("document.querySelector('[name=procedure_template]:checked')?.value === 'factory_rollout'")
        self.fill('#ew-procedure-name', '합성 횡전개 절차')
        self.click('[data-author-action="procedure_cancel"]')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-procedure-start')"))
        self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference().kind'), original_reference['kind'])
        self.wait("Math.abs(document.querySelector('#ees-work-panel').getBoundingClientRect().width-" + str(original_panel_width) + ")<1.5")
        self.assertEqual(self.state()['workflows'], [])
        self.click('[data-author-action="create"]')
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '합성 횡전개 절차')

        self.click('#ees-work-system-trigger')
        self.click('[data-action=choose_system][data-system-id=APC]')
        self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('APC')")
        if not self.browser.evaluate("!!document.querySelector('.ew-procedure-start')"):
            self.click('[data-author-action="create"]')
        self.assertNotEqual(self.read('#ew-procedure-name', 'value'), '합성 횡전개 절차')
        self.fill('#ew-procedure-name', 'APC 별도 초안 이름')
        self.click('#ees-work-system-trigger')
        self.click('[data-action=choose_system][data-system-id=EMS]')
        self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('EMS')")
        if not self.browser.evaluate("!!document.querySelector('.ew-procedure-start')"):
            self.click('[data-author-action="create"]')
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '합성 횡전개 절차')

        self.wait("document.querySelector('#ees-work-procedure-start [data-action=procedure_question]')")
        question_selector = '#ees-work-procedure-start [data-action=procedure_question][data-question-index="0"]'
        question_style = self.browser.evaluate("""(()=>{const group=getComputedStyle(document.querySelector('.ew-procedure-questions')),first=getComputedStyle(document.querySelector('.ew-procedure-questions>button'));return {radius:first.borderRadius,border:first.borderWidth,groupBorder:group.borderWidth,groupStyle:group.borderStyle};})()""")
        self.assertEqual(question_style['radius'], '0px')
        self.assertEqual(question_style['border'], '0px')
        self.assertEqual(question_style['groupBorder'], '1px')
        self.assertEqual(question_style['groupStyle'], 'solid')
        question = self.text(question_selector).strip()
        self.click(question_selector)
        self.wait('window.__eesNativeDraftV1?.read()?.prompt?.includes(' + json.dumps(question) + ')')
        after = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertTrue(after['prompt'].startswith(before['prompt']))
        self.assertRegex(after['prompt'][len(before['prompt']):], r'^\n[ \t]*\n')
        self.assertEqual({key: value for key, value in before.items() if key != 'prompt'},
                         {key: value for key, value in after.items() if key != 'prompt'})
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.state()['workflows'], [])
        self.screenshot('procedure-examples-native-question-draft')

        self.click('[data-author-action="procedure_create"]')
        self.wait("document.querySelector('[data-author-action=add_stage]')")
        created = [body for body in self.server.workspace_commands if body.get('action') == 'create_workflow']
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]['template_id'], 'factory_rollout')
        self.assertEqual(created[0]['name'], '합성 횡전개 절차')
        self.assertEqual(created[0]['system_id'], 'EMS')
        self.assertEqual(UUID(created[0]['request_id']).version, 4)
        self.assertNotIn('definition', created[0])
        record = self.state()['workflows'][0]
        saved = self.state(workflow_id=record['id'])['workflow']
        self.assertEqual(saved['revision'], 1)
        self.assertIsNone(saved['published_version'])
        definition = saved['draft']
        self.assertEqual((definition['category'], definition['mode'], definition['execution_scope']),
                         ('setup', 'on_demand', 'factory'))
        nodes = definition['nodes']
        self.assertEqual(sum(node['type'] == 'p' for node in nodes.values()), 1)
        self.assertEqual(sum(node['type'] == 't' for node in nodes.values()), 4)
        self.assertEqual(sum(node['type'] == 'j' for node in nodes.values()), 6)
        self.assertEqual(len({node['id'] for node in nodes.values()}), 11)
        for key, node in nodes.items():
            self.assertEqual(key, node['id'])
            self.assertRegex(key, r'^[ptj]-[0-9a-f]{12}$')
            self.assertTrue(all(value in nodes for value in node.get('children', []) + node.get('deps', [])))
            if node.get('parent'):
                self.assertIn(key, nodes[node['parent']]['children'])
        tool_jobs = [node for node in nodes.values() if node.get('mode') == 'tool']
        self.assertTrue(tool_jobs)
        self.assertTrue(all(not node.get('tool_reference') and not node.get('tool_contract_id') for node in tool_jobs))
        self.assertEqual(self.operations()['schedules'], [])
        self.assertEqual(self.bridge.calls, [])
        self.assertIn('도구 연결 전', self.text('#ees-work-designer'))
        self.click('[data-author-action="edit_workflow"]')
        category_help = '#ees-work-dialog [data-author-action=help][data-id=category]'
        self.click(category_help)
        self.wait("document.querySelector('#ees-work-help')")
        self.assertIn('분류', self.text('#ees-work-help'))
        self.key('Escape', 27)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-help')"))
        self.assertTrue(self.browser.evaluate("!!document.querySelector('#ees-work-dialog')"))
        self.assertTrue(self.browser.evaluate('document.activeElement === document.querySelector(' + json.dumps(category_help) + ')'))
        self.click('#ees-work-dialog-cancel')
        self.assertEqual(self.state(workflow_id=record['id'])['workflow']['revision'], 1)
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('.ew-author-validation')")
        validated = self.state(workflow_id=record['id'])['workflow']
        self.assertTrue(validated['validation']['errors'])
        self.assertRegex(' '.join(validated['validation']['errors']), r'도구|연결|Native')
        self.assertTrue(self.read('[data-author-action=publish]', 'disabled'))
        self.assertIsNone(validated['published_version'])
        self.assertEqual(self.server.completions, [])
        self.screenshot('procedure-examples-created-publication-blocked')

        # At a narrow viewport the same starter remains scrollable, and its
        # name and fixed footer can both be reached without horizontal overflow.
        self.click('[data-author-action="list"]')
        self.click('[data-author-action="create"]')
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 600, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 600')
        # Native replaces its desktop sidebar at this breakpoint. Reopen its
        # actual sidebar control before expecting Work to mount again.
        self.wait("!document.querySelector('#sidebar-search-button') && document.querySelector('#sidebar-toggle-button')?.getBoundingClientRect().width > 0")
        self.click('#sidebar-toggle-button')
        self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width<=innerWidth")
        if not self.browser.evaluate("!!document.querySelector('.ew-procedure-start')"):
            self.click('[data-author-action="create"]')
        self.click('[name=procedure_template][value=blank]')
        self.fill('#ew-procedure-name', '좁은 화면에서 보존할 이름')
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '좁은 화면에서 보존할 이름')
        narrow = self.browser.evaluate("""(()=>{const panel=document.querySelector('#ees-work-panel'),name=document.querySelector('#ew-procedure-name'),footer=document.querySelector('#ees-work-designer>footer'),r=footer.getBoundingClientRect();return {overflow:panel.scrollWidth-panel.clientWidth,nameVisible:name.getBoundingClientRect().width>0,footerTop:r.top,footerBottom:r.bottom,viewport:innerHeight};})()""")
        self.assertLessEqual(narrow['overflow'], 1)
        self.assertTrue(narrow['nameVisible'])
        self.assertGreaterEqual(narrow['footerTop'], 0)
        self.assertLessEqual(narrow['footerBottom'], narrow['viewport']+1)
        self.assertFalse(self.read('[data-author-action=procedure_cancel]', 'disabled'))
        self.screenshot('procedure-examples-narrow-name-and-footer')
        self.click('[data-author-action="procedure_cancel"]')
        self.assertEqual(len(self.state()['workflows']), 1)
        self.assertEqual(self.server.completions, [])

    def test_missing_random_uuid_creates_and_saves_draft_in_native_ui(self):
        # Loopback is trustworthy in Chrome. Explicit API removal reproduces
        # the intranet capability boundary, not a real insecure-origin test.
        self.browser.evaluate("Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});true")
        self.assertEqual(self.browser.evaluate('typeof crypto.randomUUID'), 'undefined')
        self.assertEqual(self.browser.evaluate('typeof crypto.getRandomValues'), 'function')
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action="create"]')
        self.click('[name=procedure_template][value=blank]')
        self.fill('#ew-procedure-name', 'HTTP 초안 생성 검증')
        self.click('[data-author-action=procedure_create]')
        self.wait("document.querySelector('[data-author-action=add_stage]')")
        created = next(body for body in self.server.workspace_commands
                       if body.get('action') == 'create_workflow')
        self.assertEqual(created['name'], 'HTTP 초안 생성 검증')
        self.assertEqual(UUID(created['request_id']).version, 4)
        record = next(item for item in self.state()['workflows']
                      if item['name'] == created['name'])
        key = record['id']
        self.click('[data-author-action="add_stage"]')
        self.click('[data-author-action="tab"][data-tab="structure"]')
        self.click('[data-author-action="add_job"]')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved['draft']['category'], 'ops')
        self.assertEqual(saved['draft']['mode'], 'on_demand')
        self.assertFalse(saved['draft'].get('execution_scope'))
        self.assertIsNone(saved['published_version'])
        stage = next(node for node in saved['draft']['nodes'].values() if node['type'] == 't')
        job = next(node for node in saved['draft']['nodes'].values() if node['type'] == 'j')
        self.assertEqual(UUID(stage['id'].removeprefix('stage-')).version, 4)
        self.assertEqual(UUID(job['id'].removeprefix('job-')).version, 4)
        self.assertEqual(job['parent'], stage['id'])
        self.assertIn(job['id'], stage['children'])
        request_ids = [body['request_id'] for body in self.server.workspace_commands
                       if body.get('action') in ('create_workflow', 'save_draft')]
        self.assertEqual(len(request_ids), 2)
        self.assertEqual(len(set(request_ids)), 2)
        self.assertTrue(all(UUID(value).version == 4 for value in request_ids))
        self.browser.call('Page.reload')
        self.wait("document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.wait("document.querySelector('[data-author-action=save]')")
        self.assertEqual(self.state(workflow_id=key)['workflow']['draft'], saved['draft'])
        self.screenshot('http-id-native-create-save-reload')

    def test_schedule_mouse_field_transition_keeps_focus_and_saves_both_values(self):
        key = self.author(name='합성 일정 포커스 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition.update(mode='periodic', schedule={
            'timezone': 'Asia/Seoul', 'anchor': '2026-10-06T09:00',
            'frequency': 'weekly', 'interval': 1, 'weekday': 1,
            'name_template': '기존 {date} 회차',
        })
        self.command('save_draft', workflow_id=key,
                     expected_revision=workflow['revision'], definition=definition)
        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
        self.click('[data-author-action="schedule_preview"]')
        self.wait("document.querySelector('.ew-schedule-preview')?.textContent.includes('다음 회차 기존')")
        self.click('#ew-author-schedule [name=interval]')
        for kind in ('keyDown', 'keyUp'):
            self.browser.call('Input.dispatchKeyEvent', {
                'type': kind, 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 2,
            })
        self.browser.call('Input.insertText', {'text': '2'})
        self.assertIn('일정이 바뀌었습니다', self.text('.ew-schedule-preview'))
        self.assertNotIn('다음 회차 기존', self.text('.ew-schedule-preview'))
        # Do not use fill()'s Tab commit: a real mouse transition must keep its
        # target rather than replacing the entire form during blur/change.
        self.click('#ew-author-schedule [name=name_template]')
        self.assertEqual(self.browser.evaluate('document.activeElement?.name'), 'name_template')
        for kind in ('keyDown', 'keyUp'):
            self.browser.call('Input.dispatchKeyEvent', {
                'type': kind, 'key': 'a', 'code': 'KeyA',
                'windowsVirtualKeyCode': 65, 'modifiers': 2,
            })
        self.browser.call('Input.insertText', {'text': '마우스로 입력한 {date} 회차'})
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['draft']['schedule']['interval'], 2)
        self.assertEqual(saved['draft']['schedule']['name_template'], '마우스로 입력한 {date} 회차')
        self.screenshot('integrated-figma-b21-mouse-focus-saved')

    def test_schedule_preview_save_publish_and_explicit_delegation_preserve_existing_cycle(self):
        key = self.author(name='합성 일정 UI 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition['mode'] = 'periodic'
        definition['schedule'] = {
            'timezone': 'Asia/Seoul', 'anchor': '2026-10-06T09:00',
            'frequency': 'weekly', 'interval': 1, 'weekday': 1,
            'name_template': '기존 {date} 회차',
            'stage_deadlines': {'stage': {'offset_days': -8, 'end_offset_days': -6}},
            'opening': 'after_previous_closed', 'closing': 'after_last_stage',
            'non_working_days': 'notify_no_shift',
        }
        saved = self.command('save_draft', workflow_id=key,
                             expected_revision=workflow['revision'], definition=definition)
        self.command('validate_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
        original = self.start(key, mode='periodic')
        published_before = original['version']
        revision_before = self.state(workflow_id=key)['workflow']['revision']

        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('[data-author-action=open][data-id=\"" + key + "\"]')")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
        self.wait("document.querySelector('#ew-author-schedule [name=interval]')")
        self.assertEqual(self.read('#ew-author-schedule [name=interval]', 'value'), '1')
        self.fill('#ew-author-schedule [name=interval]', '2')
        self.fill('#ew-author-schedule [name=name_template]', '화면에서 저장한 {date} 회차')
        self.click('[data-author-action="schedule_preview"]')
        self.wait("document.querySelector('.ew-schedule-preview')?.textContent.includes('다음 회차 화면에서 저장한')")
        self.assertEqual(self.state(workflow_id=key)['workflow']['revision'], revision_before)
        self.assertEqual(self.operations()['schedules'], [])
        preview_requests = [body for body in self.server.workspace_commands
                            if body.get('action') == 'schedule_preview']
        self.assertEqual(preview_requests[-1]['definition']['schedule']['interval'], 2)
        self.assertEqual(self.bridge.calls, [])
        self.assertIn('공휴일 달력', self.text('.ew-schedule-preview'))
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('.ew-schedule-modes [aria-pressed=true]')].map(e=>e.textContent)"), ['주기'])
        geometry = self.browser.evaluate("""(()=>{const e=document.querySelector('.ew-schedule-preview .ew-icon'),r=e.getBoundingClientRect();return {width:r.width,height:r.height,src:e.currentSrc,loaded:e.complete&&e.naturalWidth>0,font:getComputedStyle(document.querySelector('.ew-schedule-card')).fontFamily,overflow:document.querySelector('.ew-author-scroll').scrollHeight>document.querySelector('.ew-author-scroll').clientHeight};})()""")
        self.assertTrue(geometry['loaded'], geometry)
        self.assertAlmostEqual(geometry['width'], 14, delta=.1)
        self.assertAlmostEqual(geometry['height'], 14, delta=.1)
        self.assertIn('1fc4e.svg', geometry['src'])
        directory = self.screenshot('integrated-figma-b21-live-preview')

        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        current = self.state(workflow_id=key)['workflow']
        self.assertEqual(current['draft']['schedule']['interval'], 2)
        self.assertEqual(current['draft']['schedule']['name_template'], '화면에서 저장한 {date} 회차')
        self.assertGreater(current['revision'], revision_before)
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('[data-author-action=publish]')")
        self.click('[data-author-action="publish"]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('게시 v" + str(published_before + 1) + "')")
        published = self.state(workflow_id=key)['workflow']
        prior = self.state(run_id=original['id'])['run']
        self.assertEqual(prior['version'], published_before)
        self.assertEqual(prior['definition']['schedule']['interval'], 1)
        self.assertEqual(prior['definition']['schedule']['name_template'], '기존 {date} 회차')
        self.click('[data-author-action="tab"][data-tab="schedule"]')
        self.click('.ew-author-schedules > summary')
        self.click('[data-author-action="schedule_create"]')
        self.assertFalse(self.read('#ees-work-dialog [name=delegated]', 'checked'))
        self.assertIn('게시 버전 그대로', self.text('#ees-work-dialog'))
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('.ew-author-schedules')?.textContent.includes('실행 위임 없음')")
        undelegated = self.operations()['schedules']
        self.assertEqual(len(undelegated), 1)
        self.assertFalse(undelegated[0]['delegated'])
        self.assertFalse(undelegated[0]['lifecycle_enabled'])
        self.assertEqual(undelegated[0]['rule'], published['draft']['schedule'])

        # A separate explicit confirmation enables lifecycle. No timer or
        # fixture mutation provides user delegation.
        if not self.read('.ew-author-schedules', 'open'):
            self.click('.ew-author-schedules > summary')
        self.click('[data-author-action="schedule_create"]')
        self.click('#ees-work-dialog [name=delegated]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('.ew-author-schedules')?.textContent.includes('실행 위임됨')")
        schedules = self.operations()['schedules']
        self.assertEqual(len(schedules), 2)
        active = next(item for item in schedules if item['delegated'])
        self.assertTrue(active['lifecycle_enabled'])
        self.assertEqual(active['version'], published_before + 1)
        self.assertEqual(active['identity_user_id'], self.server.user['id'])
        self.assertEqual(active['rule'], published['draft']['schedule'])
        self.assertEqual(self.bridge.calls, [])
        self.screenshot('integrated-figma-b21-published-reservation')
        (directory / 'integrated-figma-b21-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native UI; synthetic Native session; real workspace and operations SQLite',
            'geometry': geometry, 'preview_saved_definition': False,
            'saved_interval': current['draft']['schedule']['interval'],
            'preserved_existing_version': prior['version'], 'published_version': active['version'],
            'undelegated_lifecycle_enabled': undelegated[0]['lifecycle_enabled'],
            'explicit_lifecycle_enabled': active['lifecycle_enabled'],
            'external_transport_calls': len(self.bridge.calls),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_read_retry_policy_saved_in_ui_records_failed_and_successful_attempts_separately(self):
        key = self.author(name='합성 읽기 재조회 UI 검증', jobs=1)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        definition['nodes']['job-0'].update(mode='tool', tool_reference={
            'tool_id': 'jira', 'function': 'jira_dashboard', 'revision': 1,
            'content_hash': 'a' * 64, 'schema_hash': 'b' * 64,
            'config_hash': 'c' * 64, 'environment': 'd' * 64,
        })
        self.command('save_draft', workflow_id=key,
                     expected_revision=workflow['revision'], definition=definition)
        self.refresh()
        self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('[data-author-action=open][data-id=\"" + key + "\"]')")
        self.click('[data-author-action="open"][data-id="' + key + '"]')
        self.click('[data-author-action="node"][data-id="job-0"]')
        self.assertEqual(self.read('#ew-author-node [name=read_retry_count]', 'value'), '0')
        self.assertNotIn('read_retry', self.state(workflow_id=key)['workflow']['draft']['nodes']['job-0'])
        # Read-only observation captures any asynchronous control replacement;
        # it never enables a control or changes product state.
        self.browser.evaluate("""(()=>{window.__eesAuthoringObservations=[];const record=()=>{const f=document.querySelector('#ew-author-node');const row={time:performance.now(),mode:f?.querySelector('[name=mode]')?.value,read_retry_count:f?.querySelector('[name=read_retry_count]')?.value,status:document.querySelector('[data-author-status]')?.textContent};if(window.__eesAuthoringObservations.length<100)window.__eesAuthoringObservations.push(row);};window.__eesAuthoringObserver=new MutationObserver(record);window.__eesAuthoringObserver.observe(document.querySelector('#ees-work-authoring-panel'),{childList:true,subtree:true});record();return true;})()""")
        try:
            self.fill('#ew-author-node [name=read_retry_count]', '2')
        finally:
            observed = self.browser.evaluate("""(()=>{window.__eesAuthoringObserver.disconnect();const form=document.querySelector('#ew-author-node');return {changes:window.__eesAuthoringObservations,fields:[...(form?.elements || [])].map(e=>({name:e.name,value:e.value,disabled:e.disabled})),html:form?.outerHTML};})()""")
            directory = self.screenshot('integrated-figma-read-retry-control-observation')
            (directory / 'integrated-figma-read-retry-control-observation.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('.ew-author-validation-row')?.textContent.includes('조회 재시도는 검증된 읽기 작업에만')")
        self.assertEqual(self.text('.ew-author-validation h2'), '게시 전 확인')
        self.assertIn('게시를 막는 문제 1', self.text('.ew-author-validation summary'))
        incomplete = self.state(workflow_id=key)['workflow']
        self.assertEqual(len(incomplete['validation']['errors']), 1)
        self.assertIn('job-0: 조회 재시도는 검증된 읽기 작업에만 0~3회, 전체 1~300초',
                      incomplete['validation']['errors'][0])
        self.assertTrue(self.read('[data-author-action="publish"]', 'disabled'))
        self.screenshot('integrated-figma-read-retry-publication-blocker')
        self.click('[data-author-action="validation_open"][data-id="errors:0"]')
        self.wait("document.querySelector('#ew-author-node [name=read_retry_deadline]')")
        self.assertEqual(self.read('#ew-author-node [name=read_retry_count]', 'value'), '2')
        self.fill('#ew-author-node [name=read_retry_deadline]', '30')
        self.click('[data-author-action="save"]')
        self.wait("!document.querySelector('[data-author-action=validate]')?.disabled")
        saved = self.state(workflow_id=key)['workflow']
        self.assertEqual(saved['draft']['nodes']['job-0']['read_retry'], {'count': 2, 'deadline_seconds': 30})
        self.click('[data-author-action="validate"]')
        self.wait("document.querySelector('[data-author-action=publish]')?.disabled === false")
        self.assertEqual(self.state(workflow_id=key)['workflow']['validation']['errors'], [])
        self.click('[data-author-action="publish"]')
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.textContent.includes('게시 v2')")

        async def invoke(actor, reference, arguments, context):
            await self.bridge.check(actor, reference)
            self.bridge.calls.append({'actor': actor['id'], 'arguments': deepcopy(arguments),
                                      'context': deepcopy(context)})
            if len(self.bridge.calls) == 1:
                return {'status': 'failed', 'transport': 'failed', 'failure_confirmed': True,
                        'completeness': 'unknown', 'error': {'code': 'upstream_error'}}
            return {'status': 'succeeded', 'completeness': 'complete',
                    'data': {'summary': '두 번째 합성 읽기 결과'}}

        self.bridge.invoke = invoke
        run = self.start(key)
        self.click('[data-action="mode"][data-mode="work"]')
        self.open_run(key, run)
        self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-work-panel .ew-status[data-status=waiting_confirmation]')")
        result = self.state(run_id=run['id'])['run']
        self.assertEqual(len(self.bridge.calls), 2)
        self.assertEqual([attempt['status'] for attempt in result['attempts']], ['failed', 'succeeded'])
        self.assertEqual(result['jobs']['job-0']['status'], 'waiting_confirmation')
        self.assertEqual(result['jobs']['job-0']['decisions'], [])
        self.assertEqual(result['attempts'][0]['result']['error']['code'], 'upstream_error')
        self.assertEqual(result['definition']['nodes']['job-0']['read_retry'], {'count': 2, 'deadline_seconds': 30})
        directory = self.screenshot('integrated-figma-read-retry-human-boundary')
        (directory / 'integrated-figma-read-retry-roundtrip.json').write_text(json.dumps({
            'scope': 'built Native UI; synthetic Native session and read transport; real SQLite executor',
            'explicit_policy': result['definition']['nodes']['job-0']['read_retry'],
            'attempt_statuses': [attempt['status'] for attempt in result['attempts']],
            'external_transport_calls': len(self.bridge.calls),
            'business_status': result['jobs']['job-0']['status'],
            'human_decisions': result['jobs']['job-0']['decisions'],
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
