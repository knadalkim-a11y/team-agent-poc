"""Actual built Native Chat helper UI; only account/model transport is synthetic.

The real source components, Native composer, uploads, history and socket event
handling run in Chrome. These checks do not represent in-house model quality or
live Native authentication/ACL; the server tests cover the status endpoint.
"""
from copy import deepcopy
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from ees_work_integrated_fixture import IntegratedNativeCase
from native_ui_fixture import NativeUIHandler


QUESTION = '#ees-work-procedure-start [data-action=procedure_question]'
NOTICE = '[data-ees-helper-notice]'
ANSWER = '실제 대화 입력이 전달되었습니다.'


def install_helper_status_fixture(case):
    """Per-case Native authorization transport; never a product source overlay."""
    state = {'available': True, 'code': 'helper_unavailable',
             'message': '지금은 업무 도우미를 사용할 수 없습니다.', 'requests': [],
             'started': threading.Event(), 'hold': None}
    original_get = NativeUIHandler.do_GET

    def helper_status(handler):
        parsed = urlsplit(handler.path)
        if parsed.path != '/api/ees-work/help/status':
            return original_get(handler)
        handler.server.requests.append(('GET', parsed.path))
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        state['requests'].append(query)
        state['started'].set()
        if state['hold'] is not None and not state['hold'].wait(timeout=8):
            raise AssertionError('Held helper status was not released by the browser test')
        response = {'ok': True, 'available': state['available'], 'protocol': 1}
        if state['available']:
            response['model_id'] = query.get('model_id', 'fixture-model')
        else:
            response.update(code=state['code'], message=state['message'])
        return handler.send_content(response)

    provider = patch.object(NativeUIHandler, 'do_GET', helper_status)
    provider.start()
    case.addCleanup(provider.stop)
    return state


class HelperChatNativeTests(IntegratedNativeCase):
    def setUp(self):
        super().setUp()
        self.helper_status = install_helper_status_fixture(self)
        self.wait('window.__eesNativeDraftV1?.ready()')

    def open_guide(self):
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=create]')
        self.wait('document.querySelector(' + json.dumps(QUESTION) + ')?.checkVisibility({visibilityProperty:true})')
        self.assertTrue(self.browser.evaluate("!!document.querySelector('#chat-container #ees-work-procedure-start')"))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-panel #ees-work-procedure-start,#ees-work-panel .ew-procedure-intro')"))
        self.assertIn('지금은 대화 내용으로 초안을 바로 만들지는 않습니다.', self.text('#ees-work-procedure-start'))
        self.assertEqual(self.state()['workflows'], [])
        return self.text(QUESTION).strip()

    def attach(self, name, data, *, wait=True):
        sample = Path(self.temporary.name) / name
        sample.write_bytes(data)
        self.browser.call('DOM.enable')
        document = self.browser.call('DOM.getDocument')['root']['nodeId']
        upload = self.browser.call('DOM.querySelector', {'nodeId': document,
            'selector': '#chat-container input[type=file][multiple]'})['nodeId']
        self.assertGreater(upload, 0)
        self.browser.call('DOM.setFileInputFiles', {'nodeId': upload, 'files': [str(sample)]})
        if wait:
            self.wait('window.__eesNativeDraftV1?.read()?.files?.length === 1 && !window.__eesNativeDraftV1.attachmentState().uploading')
        return sample

    def wait_reply(self, count=1):
        self.wait("document.querySelector('#messages-container')?.textContent.includes(" + json.dumps(ANSWER) + ") && !window.__eesSourceShellV1?.helpState()?.busy")
        self.assertEqual(len(self.server.completions), count)
        self.wait("!!document.querySelector('[data-ees-helper-label]')")

    def assert_helper_request(self, question, reference=None, index=-1):
        body = self.server.completions[index]
        self.assertEqual(body['model'], 'fixture-model')
        self.assertEqual(body['user_message']['content'], question)
        self.assertFalse(body['user_message'].get('files'))
        for key in ('files', 'tool_ids', 'skill_ids', 'filter_ids', 'terminal_id', 'tool_servers'):
            self.assertFalse(body.get(key), (key, body.get(key)))
        self.assertFalse(any(body.get('features', {}).values()))
        self.assertEqual(body['user_message']['meta']['ees_work_help'], 1)
        saved = body['user_message']['meta']['ees_work_reference']
        self.assertEqual(saved['kind'], 'help')
        self.assertEqual(saved['system_id'], 'EMS')
        self.assertTrue(saved['context_id'])
        if reference is not None:
            for key in ('kind', 'system_id', 'context_id'):
                self.assertEqual(saved[key], reference[key])
        message = '#message-' + body['user_message']['id']
        self.assertEqual(self.text(message + ' .markdown-prose').strip(), question)
        self.assertTrue(self.browser.evaluate('!!document.querySelector(' + json.dumps(message + ' [data-ees-helper-reference]') + ')'))
        self.assertNotIn('context_id', self.text(message))
        self.assertNotIn(saved['context_id'], self.text(message))
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.state()['workflows'], [])
        return deepcopy(saved)

    def screenshot(self, label, **kwargs):
        directory = super().screenshot(label, **kwargs)
        evidence = self.browser.evaluate("""(()=>({
          path:location.pathname,helperState:window.__eesSourceShellV1?.helpState(),
          draft:window.__eesNativeDraftV1?.read(),
          guideInChat:!!document.querySelector('#chat-container #ees-work-procedure-start'),
          guideInPanel:!!document.querySelector('#ees-work-panel #ees-work-procedure-start'),
          references:[...document.querySelectorAll('[data-ees-helper-reference]')].map(e=>e.innerText),
          helperLabels:[...document.querySelectorAll('[data-ees-helper-label]')].map(e=>e.innerText),
          horizontalOverflow:document.documentElement.scrollWidth>innerWidth
        }))()""")
        (directory / (label + '-dom.json')).write_text(json.dumps({
            'scope': 'actual built Native UI; synthetic account, permission response and model transport',
            'completion_count': len(self.server.completions), 'status_requests': getattr(self, 'helper_status', {}).get('requests', []),
            'observed': evidence}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return directory

    def test_inline_guide_sends_question_preserves_text_file_and_fixed_reference_after_reload(self):
        self.fill('#chat-input', '아직 보내지 않을 개인 질문')
        self.attach('personal-draft.txt', b'private synthetic attachment')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        # The public Native draft contract supplies otherwise unavailable
        # synthetic selections; the real composer retains them during send.
        draft.update(selectedToolIds=['synthetic-personal-tool'],
                     selectedSkillIds=['synthetic-personal-skill'],
                     selectedFilterIds=['synthetic-personal-filter'])
        self.assertTrue(self.browser.evaluate('window.__eesNativeDraftV1.restore(' + json.dumps(json.dumps(draft, ensure_ascii=False)) + ')'))
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        question = self.open_guide()
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        self.browser.evaluate("window.__eesHelperComposer=document.querySelector('#chat-input');true")
        self.click(QUESTION)
        self.wait_reply()
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesHelperComposer"))
        frozen = self.assert_helper_request(question, reference)
        self.assertEqual(len(self.helper_status['requests']), 1)
        self.assertEqual(self.helper_status['requests'][0]['chat_id'], 'existing-chat')
        self.screenshot('helper-chat-question-and-personal-file')
        message_id = self.server.completions[0]['user_message']['id']
        self.click('[data-author-action=procedure_cancel]')
        self.click('#ees-work-system-trigger')
        self.click('[data-action=choose_system][data-system-id=APC]')
        self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('APC')")
        stored = self.server.chats['existing-chat']['chat']['history']['messages'][message_id]
        self.assertEqual(stored['meta']['ees_work_reference'], frozen)
        self.assertEqual(stored['meta']['ees_work_help'], 1)
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#message-" + message_id + " [data-ees-helper-reference]') && document.querySelector('[data-ees-helper-label]')")
        self.assertEqual(self.server.chats['existing-chat']['chat']['history']['messages'][message_id]['meta']['ees_work_reference'], frozen)
        self.assertEqual(self.server.chats['existing-chat']['chat']['history']['messages'][message_id]['meta']['ees_work_help'], 1)
        self.assertEqual(self.text('#message-' + message_id + ' .markdown-prose').strip(), question)
        self.assertEqual(len(self.server.completions), 1)
        self.screenshot('helper-chat-fixed-reference-after-reload')

    def test_helper_question_preserves_live_image_and_composer(self):
        # Empty chat -> first helper response must not replace the composer.
        self.navigate('/')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.wait("document.querySelector('#messages-container img[alt=logo]')?.checkVisibility({visibilityProperty:true}) && document.querySelector('#messages-container')?.textContent.includes('Fixture AI')")
        self.fill('#chat-input', '이미지와 함께 보존할 개인 질문')
        self.attach('personal-draft.png', self.server.wheel.read('open_webui/frontend/static/user.png'))
        self.wait("document.querySelector('#message-input-container [data-cy=image]')?.naturalWidth > 0")
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.browser.evaluate("window.__eesHelperImage=document.querySelector('#message-input-container [data-cy=image]');window.__eesHelperComposer=document.querySelector('#chat-input');true")
        question = self.open_guide()
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#messages-container img[alt=logo]')"))
        self.assertNotIn('Fixture AI', self.text('#messages-container'))
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesHelperComposer && document.querySelector('#message-input-container [data-cy=image]')===window.__eesHelperImage"))
        self.screenshot('helper-chat-empty-guide-image-preserved')
        self.click(QUESTION)
        self.wait_reply()
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertTrue(self.browser.evaluate("document.querySelector('#chat-input')===window.__eesHelperComposer && document.querySelector('#message-input-container [data-cy=image]')===window.__eesHelperImage && window.__eesHelperImage.naturalWidth>0"))
        self.assert_helper_request(question)
        self.screenshot('helper-chat-live-image-preserved')

    def test_helper_question_preserves_upload_in_flight_until_completion(self):
        original_post = NativeUIHandler.do_POST
        started, hold = threading.Event(), threading.Event()
        self.addCleanup(hold.set)

        def held_upload(handler):
            if urlsplit(handler.path).path == '/api/v1/files/':
                started.set()
                if not hold.wait(timeout=8):
                    raise AssertionError('Held upload was not released by the browser test')
            return original_post(handler)

        provider = patch.object(NativeUIHandler, 'do_POST', held_upload)
        provider.start()
        self.addCleanup(provider.stop)
        self.fill('#chat-input', '업로드 완료를 기다리는 개인 질문')
        sample = self.attach('uploading-personal.png', self.server.wheel.read('open_webui/frontend/static/user.png'), wait=False)
        self.assertTrue(started.wait(timeout=2))
        self.wait('window.__eesNativeDraftV1?.attachmentState().uploading')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        question = self.open_guide()
        self.click(QUESTION)
        self.wait_reply()
        during = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertEqual(during, before)
        self.assertTrue(self.browser.evaluate('window.__eesNativeDraftV1.attachmentState().uploading'))
        self.assert_helper_request(question)
        hold.set()
        self.wait("!window.__eesNativeDraftV1.attachmentState().uploading && document.querySelector('#message-input-container [data-cy=image]')?.naturalWidth>0")
        after = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.assertEqual({key: value for key, value in after.items() if key != 'files'},
                         {key: value for key, value in before.items() if key != 'files'})
        self.assertEqual(after['files'][0]['itemId'], before['files'][0]['itemId'])
        self.assertEqual(self.server.uploaded_file, (sample.read_bytes(), 'image/png'))
        self.screenshot('helper-chat-upload-in-flight-preserved')

    def test_busy_and_double_click_send_one_question_and_disable_other_requests(self):
        question = self.open_guide()
        self.server.delay_next_completion = True
        self.server.completion_response_hold.clear()
        point = self.browser.evaluate('(()=>{const r=document.querySelector(' + json.dumps(QUESTION) + ').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
        for count in (1, 2):
            for kind in ('mousePressed', 'mouseReleased'):
                self.browser.call('Input.dispatchMouseEvent', {'type': kind, **point,
                    'button': 'left', 'buttons': int(kind == 'mousePressed'), 'clickCount': count})
        self.assertTrue(self.server.completion_response_started.wait(timeout=3))
        self.wait("window.__eesSourceShellV1.helpState().busy && [...document.querySelectorAll('#ees-work-procedure-start [data-action=procedure_question]')].every(e=>e.disabled)")
        self.assertEqual(len(self.server.completions), 1)
        self.assertEqual(len(self.helper_status['requests']), 1)
        self.screenshot('helper-chat-pending-disabled')
        self.server.completion_response_hold.set()
        self.wait_reply()
        self.assert_helper_request(question)
        self.wait("[...document.querySelectorAll('#ees-work-procedure-start [data-action=procedure_question]')].every(e=>!e.disabled)")
        # A normal Native answer is also busy: helper actions must not enqueue
        # another request while the ordinary conversation is streaming.
        self.server.stream_started.clear()
        self.server.stream_hold.clear()
        self.fill('#chat-input', '일반 대화의 답변 중에는 기다립니다')
        self.click('#send-message-button')
        self.assertTrue(self.server.stream_started.wait(timeout=3))
        self.wait("[...document.querySelectorAll('#ees-work-procedure-start [data-action=procedure_question]')].every(e=>e.disabled)")
        self.assertEqual(len(self.server.completions), 2)
        self.server.stream_hold.set()
        self.wait('!window.__eesSourceShellV1.helpState().busy')
        self.assertEqual(len(self.server.completions), 2)

    def test_unavailable_and_revoked_helper_do_not_add_messages_or_send(self):
        self.fill('#chat-input', '권한 확인 실패에도 보존할 개인 질문')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        question = self.open_guide()
        history = deepcopy(self.server.chats['existing-chat']['chat']['history'])
        self.helper_status['available'] = False
        self.click(QUESTION)
        self.wait('document.querySelector(' + json.dumps(NOTICE) + ')?.textContent.trim() && !window.__eesSourceShellV1.helpState().busy')
        self.assertEqual(self.read(NOTICE, 'getAttribute("role")'), 'status')
        self.assertEqual(self.text('body').count(self.text(NOTICE).strip()), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#ew-procedure-name')?.checkVisibility({visibilityProperty:true})"))
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.server.chats['existing-chat']['chat']['history'], history)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.helper_status['available'] = True
        self.click(QUESTION)
        self.wait_reply()
        self.assert_helper_request(question)
        history = deepcopy(self.server.chats['existing-chat']['chat']['history'])
        self.helper_status.update(available=False, code='native_access_denied', message='현재 업무 도우미를 사용할 권한이 없습니다.')
        self.click(QUESTION)
        self.wait('document.querySelector(' + json.dumps(NOTICE) + ')?.textContent.includes("권한") && !window.__eesSourceShellV1.helpState().busy')
        self.assertEqual(len(self.server.completions), 1)
        self.assertEqual(self.server.chats['existing-chat']['chat']['history'], history)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(len(self.helper_status['requests']), 3)
        self.screenshot('helper-chat-revoked-no-send')

    def test_help_footer_sends_in_chat_with_term_reference_and_keeps_draft(self):
        self.fill('#chat-input', '도움말과 별개인 개인 질문')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-action=tools]')
        self.click('[data-author-action=tool_create]')
        self.click('[data-author-action=tool_example][data-id=jira-query]')
        self.click('[data-author-action=help][data-id=read_tool]')
        self.wait("document.querySelector('#ees-work-help [data-help-ask]')")
        self.click('#ees-work-help [data-help-ask]')
        self.wait_reply()
        body = self.server.completions[0]
        question = body['user_message']['content']
        self.assertNotIn('read_tool', question)
        self.assertNotIn('현재 화면:', question)
        self.assertNotIn(before['prompt'], question)
        reference = self.assert_helper_request(question)
        self.assertEqual(reference['term_id'], 'read_tool')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertEqual(len(self.helper_status['requests']), 1)
        self.screenshot('helper-chat-help-footer')

    def test_manual_send_on_help_screen_keeps_native_file_assets_and_features(self):
        self.fill('#chat-input', '직접 보내는 개인 질문과 첨부')
        self.attach('ordinary-help-screen.txt', b'ordinary native input')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        draft.update(selectedToolIds=['synthetic-personal-tool'],
                     selectedSkillIds=['synthetic-personal-skill'],
                     selectedFilterIds=['synthetic-personal-filter'])
        self.assertTrue(self.browser.evaluate('window.__eesNativeDraftV1.restore(' + json.dumps(json.dumps(draft, ensure_ascii=False)) + ')'))
        self.open_guide()
        self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference().kind'), 'help')
        self.click('#send-message-button')
        self.wait("document.querySelector('#messages-container')?.textContent.includes(" + json.dumps(ANSWER) + ") && !window.__eesSourceShellV1.helpState().busy")
        self.assertEqual(len(self.server.completions), 1)
        body = self.server.completions[0]
        self.assertEqual(body['user_message']['content'], draft['prompt'])
        self.assertEqual(body['user_message']['files'], draft['files'])
        self.assertEqual(body['files'], draft['files'])
        for outbound, selected in (('tool_ids', 'selectedToolIds'), ('skill_ids', 'selectedSkillIds'),
                                   ('filter_ids', 'selectedFilterIds')):
            self.assertEqual(body[outbound], draft[selected])
        self.assertIn('web_search', body['features'])
        self.assertIn('code_interpreter', body['features'])
        self.assertEqual(body['user_message']['meta']['ees_work_reference']['kind'], 'help')
        self.assertNotEqual(body['user_message']['meta'].get('ees_work_help'), 1)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-ees-helper-label]')"))
        self.assertEqual(self.helper_status['requests'], [])
        self.screenshot('helper-chat-ordinary-send-preserved')

    def test_english_question_sends_exact_visible_text_without_translation_keys(self):
        locale_script = self.browser.call('Page.addScriptToEvaluateOnNewDocument', {
            'source': "localStorage.setItem('locale','en-US');"})['identifier']
        self.addCleanup(lambda: self.browser.call('Page.removeScriptToEvaluateOnNewDocument',
                                                  {'identifier': locale_script}))
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeDraftV1?.ready() && document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.fill('#chat-input', 'A separate personal draft')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=create]')
        self.wait('document.querySelector(' + json.dumps(QUESTION) + ')?.textContent.includes("copy")')
        question = self.text(QUESTION).strip()
        self.assertRegex(question, r'[A-Za-z]')
        self.assertNotRegex(question, r'[가-힣]')
        self.assertNotRegex(self.text('#ees-work-procedure-start'), r'EES\.[A-Za-z]')
        self.click(QUESTION)
        self.wait_reply()
        self.assert_helper_request(question)
        self.assertIn('Work assistant', self.text('[data-ees-helper-label]'))
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.screenshot('helper-chat-english-visible-question')

    def test_late_denied_preflight_after_screen_change_does_not_add_stale_notice(self):
        self.fill('#chat-input', '화면 이동 중에도 유지할 개인 질문')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.open_guide()
        self.assertEqual(self.browser.evaluate('window.__eesNativeWorkV1.captureReference().kind'), 'help')
        history = deepcopy(self.server.chats['existing-chat']['chat']['history'])
        hold = threading.Event()
        self.addCleanup(hold.set)
        self.helper_status.update(available=False, hold=hold,
                                  message='이전 화면에서만 발생한 합성 접근 거절')
        self.click(QUESTION)
        self.assertTrue(self.helper_status['started'].wait(timeout=2))
        self.assertEqual(self.helper_status['requests'][0]['system_id'], 'EMS')
        self.click('#ees-work-system-trigger')
        self.click('[data-action=choose_system][data-system-id=APC]')
        # APC has no selected work/help item, so its valid reference is none.
        # Do not wait for an APC help token that this screen must not create.
        self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('APC') && window.__eesNativeWorkV1.captureReference()?.kind === 'none'")
        self.assertEqual(self.browser.evaluate('location.pathname'), '/c/existing-chat')
        self.assertTrue(self.browser.evaluate('window.__eesSourceShellV1.helpState().busy'))
        hold.set()
        self.wait('!window.__eesSourceShellV1.helpState().busy')
        self.assertEqual(self.browser.evaluate('window.__eesSourceShellV1.helpState().notice'), '')
        self.assertFalse(self.text(NOTICE).strip())
        self.assertNotIn('이전 화면에서만 발생한 합성 접근 거절', self.text('body'))
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.server.chats['existing-chat']['chat']['history'], history)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-ees-helper-reference],[data-ees-helper-label]')"))
        self.screenshot('helper-chat-late-preflight-context-changed')

    def test_revocation_after_preflight_removes_optimistic_messages_without_losing_draft(self):
        original_post = NativeUIHandler.do_POST
        rejected = []

        def revoked_completion(handler):
            if urlsplit(handler.path).path != '/api/chat/completions':
                return original_post(handler)
            handler.server.requests.append(('POST', '/api/chat/completions'))
            rejected.append(json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', '0')))))
            return handler.send_content({'detail': {'code': 'work_help_unavailable', 'persisted': False,
                'message': '현재 업무 도우미를 사용할 권한이 없습니다.'}}, status=409)

        provider = patch.object(NativeUIHandler, 'do_POST', revoked_completion)
        provider.start()
        self.addCleanup(provider.stop)
        self.fill('#chat-input', '보내기 직전 권한 변경에도 남을 개인 질문')
        self.attach('permission-race.txt', b'personal draft survives revocation')
        before = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        question = self.open_guide()
        history = deepcopy(self.server.chats['existing-chat']['chat']['history'])
        self.click(QUESTION)
        self.wait('document.querySelector(' + json.dumps(NOTICE) + ')?.textContent.includes("권한") && !window.__eesSourceShellV1.helpState().busy')
        self.assertEqual(self.text('body').count(self.text(NOTICE).strip()), 1)
        self.assertTrue(self.browser.evaluate("document.querySelector('#ew-procedure-name')?.checkVisibility({visibilityProperty:true})"))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]['user_message']['content'], question)
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.server.chats['existing-chat']['chat']['history'], history)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), before)
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-ees-helper-reference],[data-ees-helper-label]')"))
        self.assertNotIn(question, self.text('#messages-container'))
        self.assertEqual(len(self.helper_status['requests']), 1)
        self.screenshot('helper-chat-preflight-revoked-no-message')
