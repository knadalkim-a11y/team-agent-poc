"""Bounded external provider and full-app C3 gate; never an EES executor.

Only a new loopback port and temporary real Native stores are used. The HTTP
response data and one model response are synthetic. Native registration, source
loading, secrets, ACL, model routing, auth and EES scheduling are unmodified.
"""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
import secrets
import sys
import threading
import time
from types import ModuleType
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


class SyntheticProvider:
    def __init__(self):
        self.calls, self.models = [], []
        self.hold = False
        self.fail_next = False
        self.entered, self.release = threading.Event(), threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, value, code=200):
                data = json.dumps(value, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # An intentionally killed app cannot receive a response.

            def do_GET(self):
                parsed = urlsplit(self.path)
                path, query = parsed.path, parse_qs(parsed.query)
                if path == '/v1/models':
                    return self.answer({'object': 'list', 'data': [{'id': 'c3-synthetic-model',
                        'object': 'model', 'created': 1, 'owned_by': 'openai'}]})
                owner.calls.append({'path': path, 'query': query})
                if owner.fail_next:
                    owner.fail_next = False
                    return self.answer({'error': 'Deliberate synthetic external outage'}, 503)
                if owner.hold:
                    owner.entered.set()
                    owner.release.wait(60)
                if path == '/rest/api/content/search':
                    return self.answer({'results': [owner.page('123'), owner.page('124')]})
                if path in ('/rest/api/content/123', '/rest/api/content/124'):
                    return self.answer(owner.page(path.rsplit('/', 1)[1]))
                if path == '/api/v3/user':
                    return self.answer({'login': 'synthetic', 'id': 42})
                if path == '/api/v3/repos/team/repo/pulls':
                    return self.answer([{'number': 7, 'title': '합성 변경', 'state': 'open',
                        'draft': False, 'merged_at': None, 'user': {'login': 'synthetic'},
                        'updated_at': '2026-09-29T00:00:00Z', 'body': '합성 변경 설명',
                        'base': {'ref': 'main', 'repo': {'full_name': 'team/repo', 'id': 1}},
                        'head': {'ref': 'phase3'}}])
                if path == '/rest/api/2/myself':
                    return self.answer({'name': 'synthetic', 'active': True})
                if path == '/rest/api/2/search':
                    return self.answer({'startAt': int(query.get('startAt', ['0'])[0]),
                        'maxResults': 30, 'total': 1, 'issues': [{'key': 'EESEMS-1',
                        'fields': {'project': {'key': 'EESEMS'}, 'summary': '합성 이슈',
                            'status': {'name': 'Open', 'statusCategory': {'key': 'new'}},
                            'description': '합성 본문', 'updated': '2026-09-29T00:00:00.000+0000',
                            'duedate': None, 'assignee': None, 'priority': None}}] if 'startAt' in query else []})
                return self.answer({'error': 'Unexpected synthetic route'}, 404)

            def do_POST(self):
                if urlsplit(self.path).path == '/v1/embeddings' and getattr(owner, 'allow_embeddings', False):
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    inputs = body.get('input', [])
                    if isinstance(inputs, str):
                        inputs = [inputs]
                    owner.calls.append({'path': '/v1/embeddings', 'count': len(inputs), 'synthetic': True})
                    return self.answer({'object': 'list', 'model': body.get('model'), 'data': [
                        {'object': 'embedding', 'index': index, 'embedding': [1.0, 0.5, 0.25]}
                        for index in range(len(inputs))], 'usage': {'prompt_tokens': 1, 'total_tokens': 1}})
                if urlsplit(self.path).path != '/v1/chat/completions':
                    return self.answer({'error': 'Unexpected synthetic route'}, 404)
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                user_text = next((m['content'] for m in reversed(body['messages']) if m['role'] == 'user'), '')
                try:
                    context = json.loads(user_text)
                except (TypeError, ValueError):
                    context = {}
                if 'required_claims' in context:
                    claims, limitations = [], []
                    for item in context['required_claims']:
                        value = context['untrusted_evidence'][item['job_id']][item['call_id']]
                        for key in item['path']:
                            value = value[key]
                        claims.append({**item, 'value': value})
                    for source in context['evidence_sources']:
                        value = context['untrusted_evidence'][source['job_id']][source['call_id']]
                        if value['completeness'] not in ('complete', 'empty'):
                            limitations.append({**source, 'completeness': value['completeness']})
                    content = json.dumps({'claims': claims, 'limitations': limitations}, ensure_ascii=False)
                    owner.models.append({'kind': 'workflow', 'claims': len(claims), 'tools': body.get('tools', []),
                                         'sources': len(context['evidence_sources'])})
                else:
                    content = getattr(owner, 'native_content', '합성 모델 응답: 실제 Native 대화 서비스 연결을 확인했습니다.')
                    owner.models.append({'kind': 'native_chat', 'tools': body.get('tools', []),
                                         'stream': bool(body.get('stream')), 'user_text': user_text})
                if body.get('stream'):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    identifier = 'synthetic-' + uuid4().hex
                    for delta, reason in (({'role': 'assistant', 'content': content}, None), ({}, 'stop')):
                        chunk = {'id': identifier, 'object': 'chat.completion.chunk',
                                 'created': int(time.time()), 'model': body['model'],
                                 'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
                        self.wfile.write(('data: ' + json.dumps(chunk, ensure_ascii=False) + '\n\n').encode('utf-8'))
                        self.wfile.flush()
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                    return
                self.answer({'id': 'synthetic-' + uuid4().hex, 'object': 'chat.completion',
                    'created': int(time.time()), 'model': body['model'], 'choices': [
                    {'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @staticmethod
    def page(identifier):
        return {'id': identifier, 'type': 'page', 'status': 'current',
                'title': '합성 운영·설치 문서 ' + identifier, 'space': {'key': 'EMS'},
                'version': {'number': 3}, 'body': {'storage': {'value': '<p>합성 검토 본문 · 운영 연결 없음</p>'}}}

    def evidence(self):
        return {'boundary': 'Loopback synthetic HTTP/OpenAI responses only; no production API/model/PAT',
                'http': self.calls, 'model': self.models}

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def composer_gate(*, out, client, headers, browser, base, chat_id, provider,
                  click, wait, shot, record):
    """Physical Native composer input/send; API use is setup or read-only evidence.

    No completion endpoint or chat-message save is called by this test. Native
    frontend owns those requests. Temporary user preferences disable background
    title/tag/follow-up generation to count only the three intentional sends.
    """
    def api(path, body=None, **params):
        response = client.request('POST' if body is not None else 'GET', path,
                                  headers=headers, json=body, params=params or None)
        response.raise_for_status()
        value = response.json()
        assert not isinstance(value, dict) or value.get('ok') is not False, value
        return value

    api('/api/v1/users/user/settings/update', {'ui': {'language': 'ko-KR',
         'showChangelog': False, 'models': ['c3-synthetic-model']}})
    api('/api/v1/models/create', {'id': 'c3-synthetic-model', 'name': 'C3 합성 모델',
                                 'meta': {}, 'params': {}, 'access_grants': []})
    assert any(model['id'] == 'c3-synthetic-model' for model in api('/api/models')['data'])
    existing_case = api('/api/ees-work/state', chat_id=chat_id)['case']
    initial_chat = api('/api/v1/chats/' + chat_id)['chat']
    assert initial_chat['history']['messages'] == {}
    evidence = {'boundary': 'Official Native CLI/auth/chat/composer/EES/temporary DB; loopback model response synthesis only',
                'program_test': 'physical CDP Input dispatch; no direct completion or injected message save',
                'cases': []}

    def navigate(path=None):
        browser.events.clear()
        browser.call('Page.navigate', {'url': base + path}) if path else browser.call('Page.reload')
        deadline = time.monotonic() + 20
        while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
            browser.events.append(browser.receive(deadline))
        wait('!!document.querySelector("#chat-input.ProseMirror") && !!document.querySelector("#ees-work-entry")')

    def open_process():
        if browser.evaluate('document.querySelector("#sidebar").getBoundingClientRect().width < 200'):
            click('button[aria-label="사이드바 열기"],button[aria-label="Open sidebar"]')
        click('[data-work-category="setup"]')
        selector = '#ees-work-entry [data-action="select"][data-node-id="setup-p"]'
        wait('!!document.querySelector(' + json.dumps(selector) + ')')
        if browser.evaluate('!!document.querySelector(' + json.dumps(selector) + ')?.closest("details:not([open])")'):
            click('#ees-work-entry .ew-workflow-picker > summary')
        click(selector)
        wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "신규 공장 횡전개" && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')

    def snapshot(identifier):
        chat = api('/api/v1/chats/' + identifier)['chat']
        return chat, api('/api/ees-work/state', chat_id=identifier)['case']

    def send_and_verify(label, question, expected_case, expected_chat=None, prior_questions=()):
        assert browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length')
        prior_history = snapshot(expected_chat)[0]['history'] if expected_chat else {'messages': {}}
        reply_visible = '(document.querySelector("#chat-container")?.innerText || "").split("합성 모델 응답: 실제 Native 대화 서비스 연결을 확인했습니다.").length - 1 === ' + str(len(prior_questions) + 1)
        # Capture trusted browser events without modifying application handlers.
        browser.evaluate('''window.c3ComposerEvents=[];
          document.addEventListener('input',e=>{if(e.target.closest?.('#chat-input'))window.c3ComposerEvents.push({type:e.type,trusted:e.isTrusted})},true);
          document.addEventListener('click',e=>{if(e.target.closest?.('#send-message-button'))window.c3ComposerEvents.push({type:e.type,trusted:e.isTrusted})},true);''')
        click('#chat-input')
        browser.call('Input.insertText', {'text': question})
        wait('document.querySelector("#chat-input")?.innerText === ' + json.dumps(question))
        wait('!!document.querySelector("#send-message-button") && !document.querySelector("#send-message-button").disabled')
        before = len(provider.models)
        browser.events.clear()
        click('#send-message-button')
        wait('location.pathname.startsWith("/c/") && !!document.querySelector("#chat-container") && document.querySelector("#chat-container").innerText.includes(' + json.dumps(question) + ')')
        wait(reply_visible)
        wait('document.querySelector("#ees-work-context")?.innerText.includes("이 대화에 연결됨")')
        identifier = browser.evaluate('location.pathname.split("/c/")[1]')
        assert not expected_chat or identifier == expected_chat, (identifier, expected_chat)
        assert expected_chat or identifier != chat_id
        deadline = time.monotonic() + 10
        while True:
            saved, case = snapshot(identifier)
            messages = list(saved['history']['messages'].values())
            expected_count = (len(prior_questions) + 1) * 2
            if len(messages) == expected_count and all(m.get('done') for m in messages if m['role'] == 'assistant'):
                break
            assert time.monotonic() < deadline, saved
            time.sleep(.1)
        assert [m['content'] for m in messages if m['role'] == 'user'] == [*prior_questions, question], messages
        assert [m['content'] for m in messages if m['role'] == 'assistant'] == ['합성 모델 응답: 실제 Native 대화 서비스 연결을 확인했습니다.'] * (len(prior_questions) + 1), messages
        for identifier_before, old_message in prior_history['messages'].items():
            new_message = saved['history']['messages'][identifier_before]
            assert {key: value for key, value in old_message.items() if key != 'childrenIds'} == {
                key: value for key, value in new_message.items() if key != 'childrenIds'}, 'Existing message fields changed'
        assert case['id'] == expected_case and case['chat_id'] == identifier, case
        assert len(provider.models) == before + 1, provider.models[before:]
        assert provider.models[-1]['user_text'] == question and provider.models[-1]['stream'] is True
        events = browser.evaluate('window.c3ComposerEvents')
        assert sum(item['type'] == 'click' for item in events) == 1 and all(item['trusted'] for item in events), events
        assert any(item['type'] == 'input' for item in events), events
        requests = [event['params'] for event in browser.events if event.get('method') == 'Network.requestWillBeSent']
        completions = [req for req in requests if urlsplit(req['request']['url']).path == '/api/chat/completions']
        assert len(completions) == 1, len(completions)
        completion_body = json.loads(completions[0]['request']['postData'])
        if expected_chat:
            assert completion_body['chat_id'] == identifier
        else:
            assert not completion_body.get('chat_id'), 'First send must not target the previous chat'
        assert completion_body['user_message']['content'] == question
        question_id = completion_body['user_message']['id']
        assert saved['history']['messages'][question_id]['content'] == question
        completion_response = json.loads(browser.call('Network.getResponseBody', {
            'requestId': completions[0]['requestId']})['body'])
        assert completion_response['chat_id'] == identifier and completion_response['status'] is True
        assert len(completion_response['task_ids']) == 1, completion_response
        errors = [{'path': urlsplit(event['params']['response']['url']).path,
                   'status': event['params']['response']['status']} for event in browser.events
                  if event.get('method') == 'Network.responseReceived' and event['params']['response']['status'] >= 400]
        assert not errors, errors
        shot('composer-' + label + '-response')
        navigate()
        wait('document.querySelector("#chat-container")?.innerText.includes(' + json.dumps(question) + ') && document.querySelector("#chat-container")?.innerText.includes("합성 모델 응답")')
        wait(reply_visible)
        open_process()
        reloaded, restored = snapshot(identifier)
        assert reloaded['history'] == saved['history']
        assert restored['id'] == case['id'] and restored['chat_id'] == identifier
        assert len(provider.models) == before + 1, 'Reload must not submit again'
        shot('composer-' + label + '-reload')
        result = {'kind': label, 'chat_id': identifier, 'case_id': case['id'],
                  'trusted_input_and_single_click': events, 'completion_requests': 1,
                  'external_model_calls': 1, 'saved_messages': len(messages),
                  'request_response_visible': True, 'same_history_after_reload': True,
                  'rendered_responses': len(prior_questions) + 1,
                  'previous_message_fields_preserved': True,
                  'case_bound_to_expected_chat': True, 'site_id': case['site']['id'], 'api_errors': errors}
        result['request_response_saved_message_correlation'] = {
            'request_chat_id': completion_body.get('chat_id'), 'response_chat_id': completion_response['chat_id'],
            'saved_user_message_id': question_id, 'single_native_task': True}
        evidence['cases'].append(result)
        record('Native composer ' + label + ' send/save/reload', **result)
        return identifier, saved, restored

    try:
        navigate('/c/' + chat_id)
        open_process()
        first_question = '기존 대화 보내기 경로를 확인해줘'
        send_and_verify('initial', first_question, existing_case['id'], chat_id)
        _, existing_saved, existing_after = send_and_verify('existing', '저장된 대화에서 두 번째 보내기를 확인해줘',
                                                            existing_case['id'], chat_id, (first_question,))
        click('a#sidebar-new-chat-button')
        wait('location.pathname === "/" && !!document.querySelector("#chat-input.ProseMirror")')
        # Selecting the same active factory/process intentionally resumes its
        # previous chat. Select a distinct factory through the visible picker
        # so this test explicitly starts new work rather than that resume path.
        wait('!!document.querySelector("#ees-work-site-trigger") && !document.querySelector("#ees-work-site-trigger").disabled')
        click('#ees-work-site-trigger')
        click('#ees-work-scope-popover [data-action="scope_choose"][data-picker="site"][data-value="hu-a"]')
        wait('location.pathname === "/" && document.querySelector("#ees-work-site-trigger")?.value === "hu-a" && !document.querySelector("#ees-work-scope-popover")')
        open_process()
        # First product input-save creates the pending work case, exactly as in
        # the established new-chat workflow. It does not submit a chat message.
        click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
        click('#ees-work-content [data-work-job="db-j"] [data-action="select"]')
        wait('!!document.querySelector("#ees-work-inputs-save") && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
        click('#ees-work-inputs-save')
        wait('document.querySelector("#ees-work-context")?.innerText.includes("첫 메시지") && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
        pending = [case for case in api('/api/ees-work/state', chat_id='')['cases'] if not case['chat_id']]
        assert len(pending) == 1 and pending[0]['id'] != existing_case['id'], pending
        new_id, new_saved, new_after = send_and_verify('new', '새 대화 보내기 경로를 확인해줘', pending[0]['id'])
        cases = api('/api/ees-work/state', chat_id=new_id)['cases']
        assert sum(case['id'] == pending[0]['id'] for case in cases) == 1
        assert not [case for case in cases if not case['chat_id']], cases
        assert {chat['id'] for chat in api('/api/v1/chats/', page=1)} == {chat_id, new_id}, 'Duplicate new Native chat'
        assert snapshot(chat_id)[0]['history'] == existing_saved['history']
        assert snapshot(chat_id)[1]['id'] == existing_after['id']
        assert snapshot(chat_id)[1]['jobs'] == existing_after['jobs']
        navigate('/c/' + chat_id)
        open_process()
        wait('document.querySelector("#chat-container")?.innerText.includes("기존 대화 보내기 경로를 확인해줘")')
        assert not browser.evaluate('document.querySelector("#chat-container")?.innerText.includes("새 대화 보내기 경로를 확인해줘")')
        assert len(provider.models) == 3
        evidence['cross_chat_isolation'] = {'existing_history_unchanged': True,
                                            'new_case_migrated_once': True,
                                            'pending_cases_remaining': 0, 'total_model_calls': 3}
        evidence['ok'] = True
        record('Native composer chat isolation and no duplicate submit', **evidence['cross_chat_isolation'])
    finally:
        (out/'composer-result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')


def integrated_gate(*, root, out, work, client, headers, browser, base, chat_id,
                    session, provider, click, wait, shot, record, restart,
                    navigation_check, baseline, candidate):
    """Execute on the existing real app/browser; no monkeypatch or DB rewrite."""
    package = ModuleType('c3_fullapp_examples')
    package.__path__ = [str(root / 'agent-pack/skills/ees-work-demo/scripts')]
    sys.modules[package.__name__] = package
    examples = importlib.import_module(package.__name__ + '.ees_workflow_examples')
    evidence = {'boundary': 'Official CLI+Native auth/chat/tool/approval/model/EES routes and temporary DB; loopback external response synthesis',
                'runs': [], 'history': [], 'assets': {}}
    node_ids = {}

    def api(path, body=None, actor=None, **params):
        response = client.request('POST' if body is not None else 'GET', path,
                                  headers=actor or headers, json=body, params=params or None)
        assert response.status_code < 400, (path, response.status_code, response.text[:1500])
        result = response.json()
        if isinstance(result, dict):
            assert result.get('ok') is not False, (path, result)
        return result

    def key(name, virtual_code, **extra):
        browser.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': name, 'windowsVirtualKeyCode': virtual_code, **extra})
        browser.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': name, 'windowsVirtualKeyCode': virtual_code, **extra})

    def fill(selector, value):
        click(selector)
        key('a', 65, code='KeyA', modifiers=2)
        browser.call('Input.insertText', {'text': value})

    def settle():
        wait('!!document.querySelector("#ees-work-panel") && !document.querySelector("#ees-work-panel").matches("[aria-busy=true]")')

    def reload_page():
        browser.events.clear()
        browser.call('Page.reload')
        deadline = time.monotonic() + 20
        while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
            browser.events.append(browser.receive(deadline))
        wait('!!document.querySelector("#ees-work-entry") && !!document.querySelector("#chat-input.ProseMirror")')

    def navigate_chat(identifier):
        browser.events.clear()
        browser.call('Page.navigate', {'url': base + '/c/' + identifier})
        deadline = time.monotonic() + 20
        while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
            browser.events.append(browser.receive(deadline))
        wait('location.pathname === ' + json.dumps('/c/' + identifier)
             + ' && !!document.querySelector("#ees-work-entry") && !!document.querySelector("#chat-input.ProseMirror")')
        wait('document.querySelector("#ees-work-context")?.innerText.includes("이 대화에 연결됨")')

    def choose(identifier):
        identifier = node_ids.get(identifier, identifier)
        # Selection first refreshes the linked case and then persists selected_id.
        # An old, idle panel is not proof that this newly clicked selection has
        # finished. Wait for the actual target before touching its run button.
        title = current()['catalog']['nodes'][identifier]['name']
        selector = '[data-action="select"][data-node-id=' + json.dumps(identifier) + ']'
        if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
            click('#ees-work-context-open')
        if not browser.evaluate('!!document.querySelector(' + json.dumps(selector) + ')?.getClientRects().length'):
            picker = '#ees-work-entry .ew-workflow-picker'
            if browser.evaluate('!!document.querySelector(' + json.dumps(picker + ':not([open])') + ')'):
                click(picker + ' > summary')
        click(selector)
        wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === ' + json.dumps(title)
             + ' && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
        selected = browser.evaluate('''(async()=>{const end=performance.now()+5000;
            while(performance.now()<end){
              const response=await fetch('/api/ees-work/state?'+new URLSearchParams({chat_id:location.pathname.split('/c/')[1]}),
                {headers:{Authorization:'Bearer '+localStorage.getItem('token')}});
              const state=await response.json();
              if(state.case?.selected_id===''' + json.dumps(identifier) + ''')return true;
              await new Promise(resolve=>setTimeout(resolve,80));
            }return false;})()''')
        assert selected, 'Selection was not persisted for the actual browser account: ' + identifier

    def current(case_id=None):
        return api('/api/ees-work/state', **({'case_id': case_id} if case_id else {'chat_id': chat_id}))

    def run_state(case_id):
        return api('/api/ees-work/execution/state', case_id=case_id)['run']

    def until_run(case_id, states, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = run_state(case_id)
            if run and run['status'] in states:
                return run
            time.sleep(.1)
        raise AssertionError(('Native run did not settle', states, run))

    def reflect(status):
        if browser.evaluate('!!document.querySelector("[data-action=execution_refresh]")'):
            click('[data-action="execution_refresh"]')
        wait('document.querySelector("[data-runtime-record]")?.dataset.runtimeRecord === ' + json.dumps(status))
        settle()

    def create_case(process_id):
        nonlocal chat_id
        chat = api('/api/v1/chats/new', {'chat': {'title': 'C3 합성 업무 대화', 'models': [], 'messages': [],
                   'history': {'messages': {}, 'currentId': None}, 'params': {}, 'timestamp': int(time.time())}})
        chat_id = chat['id']
        result = api('/api/ees-work/action', {'action': 'create', 'chat_id': chat_id,
                     'payload': {'site_id': 'us-a', 'system': 'EMS', 'process_id': process_id}})
        navigate_chat(chat_id)
        if browser.evaluate('document.querySelector("#sidebar").getBoundingClientRect().width < 200'):
            click('button[aria-label="사이드바 열기"],button[aria-label="Open sidebar"]')
        category = result['case']['definition']['nodes'][process_id]['category']
        click('[data-work-category=' + json.dumps(category) + ']')
        choose(process_id)
        return result['case']['id']

    def start(node, values=None):
        choose(node)
        wait('document.querySelector("#ees-work-run")?.dataset.nodeId === '
             + json.dumps(node_ids.get(node, node)) + ' && !document.querySelector("#ees-work-run").disabled')
        click('#ees-work-run')
        wait('document.querySelector("#ees-work-dialog")?.open')
        for name, value in (values or {}).items():
            fill('#ees-runtime-input-form [name=' + json.dumps(name) + ']', value)
        click('#ees-work-dialog [data-dialog-confirm]')
        wait('!document.querySelector("#ees-work-dialog")?.open')
        settle()

    def control(action):
        selector = '[data-runtime-action=' + json.dumps(action) + ']'
        wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]") && document.querySelector('
             + json.dumps(selector) + ')?.disabled === false')
        click(selector)
        if action == 'inputs':
            wait('document.querySelector("#ees-work-dialog")?.open')
            return
        if action in ('confirm', 'cancel'):
            wait('document.querySelector("#ees-work-dialog")?.open')
            click('#ees-work-dialog [data-dialog-confirm]')
            wait('!document.querySelector("#ees-work-dialog")?.open')
        settle()

    def history_record(run):
        selector = '[data-runtime-run=' + json.dumps(run['id']) + ']'
        wait('!!document.querySelector(' + json.dumps(selector) + ')')
        return browser.evaluate('''(()=>{let e=document.querySelector(''' + json.dumps(selector) + ''').closest('nav').previousElementSibling;
            while(e&&!e.matches('[data-runtime-record]'))e=e.previousElementSibling;
            e?.scrollIntoView({block:'start'});return {status:e?.dataset.runtimeRecord,
              criterion:e?.querySelector('[data-work-criterion-status]')?.dataset.workCriterionStatus,
              text:e?.innerText};})()''')

    def publish(fragment_factory):
        process = api('/api/ees-work/authoring/action', {'action': 'create', 'system_id': 'EMS',
                      'request_id': uuid4().hex, 'payload': {'name': 'C3 실제 앱 검수 절차', 'category': 'ops'}})['process']
        fragment = fragment_factory(process['process_id'])
        for action, payload in (('save_draft', {'workflow': fragment}), ('validate_draft', {}), ('publish', {})):
            result = api('/api/ees-work/authoring/action', {'action': action, 'request_id': uuid4().hex,
                         'system_id': process['owner_system'], 'process_id': process['process_id'],
                         'expected_draft_revision': process['draft_revision'],
                         'expected_owner_revision': process['owner_revision'], 'payload': payload})
            process = result['process']
            node_ids.update(result.get('id_map', {}))
        return process, fragment

    try:
        # Previous completion defect, using the official app and existing AP
        # result prepared in the calling gate, including direct sidebar entry.
        choose('setup-p')
        navigation_check()

        # Real Native endpoints create unmanaged temporary user artifacts.
        skill = api('/api/v1/skills/create', {'id': 'c3_personal_skill', 'name': '합성 개인 스킬',
                    'content': 'Git에 없는 합성 개인 스킬 원문', 'meta': {}, 'access_grants': []})
        prompt = api('/api/v1/prompts/create', {'command': 'c3-preserved', 'name': '합성 개인 프롬프트',
                     'content': 'Git에 없는 합성 개인 프롬프트', 'access_grants': []})
        api('/api/v1/users/user/settings/update', {'ui': {'language': 'ko-KR', 'theme': 'dark', 'showChangelog': False,
                                                    'c3_preservation': '합성 개인 설정'}})
        references, tool_ids = {}, []
        for family, functions in {'jira': ['jira_dashboard'], 'github': ['github_list_pull_requests'],
                                  'confluence': ['search_pages', 'get_page']}.items():
            identifier = 'c3_' + family
            source = (root / f'agent-pack/skills/{family}-read/scripts/{family}_tool.py').read_text(encoding='utf-8')
            api('/api/v1/tools/create', {'id': identifier, 'name': 'C3 ' + family,
                'content': source, 'meta': {'description': 'Synthetic local verification'}, 'access_grants': []})
            config = {'ENABLED': True, 'ALLOW_HTTP': True, 'TIMEOUT_SECONDS': 60 if family == 'confluence' else 30}
            config.update({'jira': {'JIRA_BASE_URL': provider.base, 'ALLOWED_PROJECTS': 'EESEMS'},
                           'github': {'GITHUB_BASE_URL': provider.base, 'ALLOWED_REPOSITORIES': 'team/repo'},
                           'confluence': {'CONFLUENCE_BASE_URL': provider.base, 'ALLOWED_SPACES': 'EMS'}}[family])
            api('/api/v1/tools/id/' + identifier + '/valves/update', config)
            api('/api/v1/tools/id/' + identifier + '/valves/user/update', {'PAT': 'synthetic-local-c3'})
            for function in functions:
                inspected = api('/api/ees-work/execution/capability', tool_id=identifier, function=function)['capability']
                references[function] = api('/api/ees-work/execution/capability/action', {
                    'action': 'approve', 'reference': inspected['reference'],
                    'evidence': 'C3 loopback synthetic external service, actual approved source/API path'})['capability']['reference']
            tool_ids.append(identifier)
        api('/api/v1/models/create', {'id': 'c3-synthetic-model', 'name': 'C3 합성 모델',
                                     'meta': {}, 'params': {}, 'access_grants': []})
        api('/api/models')
        native_question = 'Native 대화 서비스 연결을 확인해줘'
        chat_reply = api('/api/chat/completions', {'model': 'c3-synthetic-model', 'stream': False,
             'messages': [{'role': 'user', 'content': native_question}]})
        assert '합성 모델 응답' in chat_reply['choices'][0]['message']['content'], chat_reply
        native_answer = chat_reply['choices'][0]['message']['content']
        message_chat_id, question_id, answer_id = chat_id, uuid4().hex, uuid4().hex
        timestamp = int(time.time())
        question = {'id': question_id, 'parentId': None, 'childrenIds': [answer_id],
                    'role': 'user', 'content': native_question, 'timestamp': timestamp,
                    'models': ['c3-synthetic-model']}
        answer = {'id': answer_id, 'parentId': question_id, 'childrenIds': [],
                  'role': 'assistant', 'content': native_answer, 'timestamp': timestamp,
                  'model': 'c3-synthetic-model', 'modelName': 'C3 합성 모델', 'done': True}
        transcript = {'messages': {question_id: question, answer_id: answer}, 'currentId': answer_id}
        # Persist the actual Native completion response with the same Native
        # ChatForm endpoint used to save chat history; no chat fixture or DB write.
        api('/api/v1/chats/' + message_chat_id, {'chat': {'models': ['c3-synthetic-model'],
            'messages': [question, answer], 'history': transcript}})

        def message_visible():
            wait('document.body.innerText.includes(' + json.dumps(native_question) + ') && '
                 + 'document.body.innerText.includes(' + json.dumps(native_answer) + ')')
            stored = api('/api/v1/chats/' + message_chat_id)['chat']['history']
            assert stored['messages'] == transcript['messages'] and stored['currentId'] == answer_id

        navigate_chat(message_chat_id)
        message_visible()
        reload_page()
        message_visible()
        shot('phase3-native-conversation-restored')
        record('Phase3 actual Native tools/model/chat API', real_registration=3, approved_functions=4,
               synthetic_external_http=True, synthetic_model=True, real_chat_messages_saved=2,
               browser_display_and_reload=True, composer_send=False)

        ops, fragment = publish(lambda p: examples.operations_workflow(references, 'c3-synthetic-model', p))
        cid = create_case(ops['process_id'])
        inputs = {'project_key': 'EESEMS', 'repository': 'team/repo', 'ops_page_id': '123'}
        start('new-operations-read-t', inputs)
        fixed = until_run(cid, {'succeeded', 'failed', 'unknown', 'waiting_authorization'})
        assert fixed['status'] == 'succeeded', fixed
        assert len(fixed['calls']) == 3 and not any(m['kind'] == 'workflow' for m in provider.models), fixed
        reflect('succeeded')
        assert current()['case']['progress'] == {'done': 3, 'total': 4}
        shot('phase3-native-fixed-t')
        evidence['runs'].append({'label': 'fixed-t', 'run': fixed, 'case': current()['case']})
        start(ops['process_id'])
        complete = until_run(cid, {'succeeded', 'failed', 'unknown', 'waiting_authorization'})
        assert complete['status'] == 'succeeded', complete
        assert len(complete['calls']) == 1 and sum(m['kind'] == 'workflow' for m in provider.models) == 1
        reflect('succeeded')
        choose('new-operations-summary-t')
        choose('new-operations-summary-j')
        assert current()['case']['status'] == 'passed'
        assert browser.evaluate('document.querySelectorAll("[data-runtime-observation]").length') == 6
        shot('phase3-native-ai')
        evidence['runs'].append({'label': 'p-ai', 'run': complete, 'case': current()['case']})
        record('Phase3 actual Native fixed T then P AI', fixed_calls=3, fixed_models=0, ai_calls=1,
               case_status=current()['case']['status'], job_progress=current()['case']['progress'],
               run_status=complete['status'], scope_complete=complete['final_validation']['scope_complete'],
               scope_reason=complete['final_validation'].get('reason'), same_native_registered_sources=True)

        # Create another case to enter the previous one via the actual history
        # UI. The prior run target/definition/final record remains read-only.
        create_case(ops['process_id'])
        if not browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        click('#ees-work-run-view [data-action="history_view"]')
        click('[data-action="history_case"][data-case-id=' + json.dumps(cid) + ']')
        wait('document.querySelector("#ees-work-content")?.innerText.includes("읽기 전용")')
        wait('document.querySelector("[data-runtime-record]")?.dataset.runtimeRecord === "succeeded"')
        displayed = history_record(complete)
        assert complete['final_validation']['status'] == 'succeeded'
        assert complete['final_validation']['scope_complete'] is False
        assert displayed['criterion'] == 'failed' and '전체 범위 완료 아님' in displayed['text'], displayed
        fixed_display = history_record(fixed)
        assert fixed['final_validation']['scope_complete'] is False and fixed_display['criterion'] == 'failed'
        assert '일부 범위 결과' in fixed_display['text']
        past_definition = current(cid)['case']['definition']
        for saved, shown in ((complete, displayed), (fixed, fixed_display)):
            assert '실행 대상 · ' + past_definition['nodes'][saved['node_id']]['name'] in shown['text']
        assert browser.evaluate('document.querySelectorAll("#ees-work-content [data-mutation]").length') == 0
        if browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        history_record(complete)
        shot('phase3-native-past-succeeded')
        evidence['history'].append({'saved_run': complete, 'displayed': displayed,
                                    'saved_fixed_run': fixed, 'fixed_displayed': fixed_display, 'route': 'more/history/past-case'})
        record('Phase3 actual Native past-case saved partial final', saved='succeeded', scope_complete=False,
               displayed=displayed['criterion'], read_only=True)

        failed_case = create_case(ops['process_id'])
        provider.fail_next = True
        start('new-operations-read-t', inputs)
        failed_run = until_run(failed_case, {'failed', 'unknown', 'waiting_authorization'})
        assert failed_run['status'] == 'failed' and 'final_validation' not in failed_run, failed_run
        reflect('failed')
        create_case(ops['process_id'])
        if not browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        click('#ees-work-run-view [data-action="history_view"]')
        click('[data-action="history_case"][data-case-id=' + json.dumps(failed_case) + ']')
        wait('document.querySelector("#ees-work-content")?.innerText.includes("읽기 전용")')
        wait('document.querySelector("[data-runtime-record]")?.dataset.runtimeRecord === "failed"')
        failed_display = history_record(failed_run)
        assert failed_display['criterion'] == 'pending', (failed_display, failed_run)
        if browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        history_record(failed_run)
        shot('phase3-native-past-unrecorded-final')
        evidence['history'].append({'saved_run': failed_run, 'displayed_final': failed_display,
                                    'compatibility_fixture': False, 'route': 'more/history/past-case'})
        record('Phase3 actual worker failure has no saved final verdict', run='failed',
               saved_final=False, displayed=failed_display['criterion'], compatibility_fixture=False)

        def documents(p):
            result = examples.installation_docs_workflow(references, p)
            human = examples._node('new-c3-human-j', 'j', 'Native 사람 확인', 'new-documents-t', 'setup', deps=['new-documents-page-j'])
            human['execution'] = {'protocol': 1, 'kind': 'human', 'calls': [],
                'completion': {'validator': 'selection_v1', 'version': 1, 'input_key': 'page_id'},
                'limits': {'timeout_seconds': 30, 'max_tool_calls': 0, 'max_model_calls': 0, 'max_retries': 0}}
            draft = deepcopy(current()['catalog']['nodes']['install-j'])
            draft.update(id='new-c3-draft-j', name='기존 검토 초안', parent='new-documents-t', deps=[], mode='draft')
            result['nodes'].update({'new-c3-human-j': human, 'new-c3-draft-j': draft})
            result['nodes']['new-documents-t']['children'].extend(['new-c3-human-j', 'new-c3-draft-j'])
            return result

        docs, doc_fragment = publish(documents)
        draft_id = node_ids['new-c3-draft-j']
        doc_case = create_case(docs['process_id'])
        start('new-documents-search-j', {'query': '설치', 'space_key': 'EMS'})
        search = until_run(doc_case, {'succeeded', 'failed'})
        assert search['status'] == 'succeeded', search
        reflect('succeeded')
        start('new-documents-page-j')
        waiting = until_run(doc_case, {'waiting_input', 'failed'})
        assert waiting['status'] == 'waiting_input', waiting
        reflect('waiting_input')
        choose(draft_id)
        fill('#ees-work-document textarea', '실제 Native 입력 대기 중 작성한 보존 초안')
        before = deepcopy(current()['case']['jobs'][draft_id])
        browser.events.clear()
        click('button[form="ees-work-document"]')
        browser.evaluate('document.querySelector("button[form=ees-work-document]").focus()')
        key('Enter', 13)
        browser.evaluate('document.querySelector("#ees-work-document").requestSubmit()')
        settle()
        posts = [e for e in browser.events if e.get('method') == 'Network.requestWillBeSent'
                 and e['params']['request']['method'] == 'POST' and e['params']['request']['url'].endswith('/api/ees-work/action')]
        assert not posts and current()['case']['jobs'][draft_id] == before
        assert browser.evaluate('document.querySelector("button[form=ees-work-document]").disabled')
        shot('phase3-native-draft-blocked')
        click('#ees-work-close')
        click('#ees-work-context-open')
        assert browser.evaluate('document.querySelector("#ees-work-document textarea").value') == '실제 Native 입력 대기 중 작성한 보존 초안'
        choose('new-documents-page-j')
        control('inputs')
        wait('document.querySelector("#ees-work-dialog")?.open')
        fill('#ees-runtime-input-form [name="page_id"]', '124')
        click('#ees-work-dialog [data-dialog-confirm]')
        wait('!document.querySelector("#ees-work-dialog")?.open')
        settle()
        deadline = time.monotonic() + 8
        while run_state(doc_case)['inputs'].get('page_id') != '124':
            assert time.monotonic() < deadline, 'Runtime input was not saved by the actual UI'
            time.sleep(.1)
        assert run_state(doc_case)['status'] == 'waiting_input'
        control('resume')
        page_run = until_run(doc_case, {'succeeded', 'failed'})
        assert page_run['status'] == 'succeeded', page_run
        reflect('succeeded')
        saved_search = api('/api/ees-work/execution/state', run_id=search['id'])['run']
        assert saved_search['calls'][0]['arguments'] == search['calls'][0]['arguments']
        assert page_run['inputs']['page_id'] == '124' and 'page_id' not in search['inputs']
        choose(draft_id)
        assert not browser.evaluate('document.querySelector("button[form=ees-work-document]").disabled')
        assert browser.evaluate('document.querySelector("#ees-work-document textarea").value') == '실제 Native 입력 대기 중 작성한 보존 초안'
        click('button[form="ees-work-document"]')
        deadline = time.monotonic() + 8
        while current()['case']['jobs'][draft_id]['document'] != '실제 Native 입력 대기 중 작성한 보존 초안':
            assert time.monotonic() < deadline, 'Draft reflection did not reach the real store'
            time.sleep(.1)
        settle()
        assert current()['case']['jobs'][draft_id]['document'] == '실제 Native 입력 대기 중 작성한 보존 초안'
        click('#ees-work-run', confirm=True)
        wait('document.querySelector(".ew-work-action-region [data-action=panel_parent]")')
        assert current()['case']['jobs'][draft_id]['status'] == 'passed'
        shot('phase3-native-draft-restored')
        record('Phase3 real app candidate wait and legacy draft gate', blocked_posts=0,
               text_preserved=True, reflected_after_native_end=True, legacy_review='passed')
        start('new-c3-human-j')
        human_wait = until_run(doc_case, {'waiting_input', 'failed'})
        assert human_wait['status'] == 'waiting_input', human_wait
        reflect('waiting_input')
        restart()
        reload_page()
        choose('new-documents-t')
        choose('new-c3-human-j')
        reflect('waiting_input')
        assert run_state(doc_case)['id'] == human_wait['id']
        control('confirm')
        human_confirmed = until_run(doc_case, {'paused', 'succeeded', 'failed'})
        assert human_confirmed['jobs'][node_ids['new-c3-human-j']]['validation']['status'] == 'succeeded'
        assert human_confirmed['calls'] == []
        if human_confirmed['status'] == 'paused':
            reflect('paused')
            control('resume')
        human_done = until_run(doc_case, {'succeeded', 'failed'})
        assert human_done['status'] == 'succeeded', human_done
        reflect('succeeded')
        evidence['runs'].append({'label': 'candidate-and-human', 'search': search, 'page': page_run,
                                'human_before_restart': human_wait, 'human_after': human_done})
        shot('phase3-native-human-complete')
        record('Phase3 actual Native human restart/confirmation', same_run=True, status=human_done['status'],
               confirmation_status=human_confirmed['status'], explicit_resume=human_confirmed['status'] == 'paused', automatic_confirm=False)

        # A second real account remains a separate user. Native signup approval
        # does not confer EES authoring/other-user chat or execution access.
        # Native first-admin creation disables signup in its own persisted
        # configuration. Re-enable it through the supported Native admin API
        # only in this new temporary DB; retain and restore every original value.
        signup_config = api('/api/v1/auths/admin/config')
        signup_test_config = {**signup_config, 'ENABLE_SIGNUP': True, 'DEFAULT_USER_ROLE': 'pending'}
        configured = api('/api/v1/auths/admin/config', signup_test_config)
        assert configured['ENABLE_SIGNUP'] and configured['DEFAULT_USER_ROLE'] == 'pending'
        second_credentials = {'name': 'C3 합성 일반 사용자', 'email': 'c3-' + uuid4().hex + '@example.test',
                              'password': secrets.token_urlsafe(30)}
        try:
            second = api('/api/v1/auths/signup', second_credentials)
        finally:
            restored_config = api('/api/v1/auths/admin/config', signup_config)
            assert restored_config == signup_config, 'Temporary Native signup configuration was not restored'
        assert second['role'] == 'pending', second['role']
        approved = api('/api/v1/users/' + second['id'] + '/update', {'role': 'user'})
        assert approved['id'] == second['id'] and approved['role'] == 'user'
        signed = api('/api/v1/auths/signin', {k: second_credentials[k] for k in ('email', 'password')})
        assert signed['id'] == second['id'] and signed['role'] == 'user'
        second_headers = {'Authorization': 'Bearer ' + signed['token']}
        capabilities = api('/api/ees-work/authoring/capabilities', actor=second_headers)
        assert capabilities['actor_id'] == second['id'] and capabilities['is_admin'] is False
        assert capabilities['can_author'] is False and capabilities['managed_systems'] == []
        forbidden = client.get('/api/ees-work/state', params={'case_id': doc_case}, headers=second_headers)
        denied = forbidden.json()
        assert forbidden.status_code == 400 and denied.get('ok') is False, (forbidden.status_code, denied)
        assert denied['error']['code'] == 'case_not_found' and 'case' not in denied and 'workflow' not in denied
        old_chat = client.get('/api/v1/chats/' + chat_id, headers=second_headers)
        assert old_chat.status_code in (401, 403, 404)
        own_chat = api('/api/v1/chats/new', {'chat': {'title': 'C3 일반 사용자 대화', 'models': [], 'messages': [],
                   'history': {'messages': {}, 'currentId': None}, 'params': {}, 'timestamp': int(time.time())}}, actor=second_headers)
        own_case = api('/api/ees-work/action', {'action': 'create', 'chat_id': own_chat['id'],
                       'payload': {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p'}}, actor=second_headers)
        assert own_case['case']['id'] != doc_case
        api('/api/v1/users/user/settings/update', {'ui': {'showChangelog': False}}, actor=second_headers)
        account_script = browser.call('Page.addScriptToEvaluateOnNewDocument', {'source':
                         'localStorage.setItem("token",' + json.dumps(signed['token']) + ');'})['identifier']
        navigate_chat(own_chat['id'])
        assert '실제 Native 입력 대기 중 작성한 보존 초안' not in browser.evaluate('document.body.innerText')
        choose('prep-t')
        choose('scope-j')
        click('#ees-work-run', confirm=True)
        wait('document.querySelector(".ew-work-action-region [data-action=panel_parent]")')
        own_after = api('/api/ees-work/state', actor=second_headers, case_id=own_case['case']['id'])['case']
        assert own_after['jobs']['scope-j']['status'] == 'passed'
        shot('phase3-second-native-user')
        browser.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier': account_script})
        navigate_chat(chat_id)
        record('Phase3 second real Native signup approval and isolation', pending_to_user=True,
               signup_configuration='supported Native admin API; temporary DB only; original configuration restored',
               private_chat_status=old_chat.status_code, private_case_status=forbidden.status_code,
               own_case=True, browser_account_switch=True, own_panel_confirmation='passed',
               authoring_capabilities=capabilities)

        # Freeze native asset responses before a program-only restore. The EES
        # database is never restored or rewritten by this check.
        paths = ['/api/v1/tools/id/' + value for value in tool_ids]
        paths += ['/api/v1/skills/id/' + skill['id'], '/api/v1/prompts/id/' + prompt['id'],
                  '/api/v1/users/user/settings', '/api/v1/chats/' + chat_id,
                  '/api/v1/chats/' + message_chat_id]
        snapshots = {path: api(path) for path in paths}
        runtime_before = run_state(doc_case)
        restart(baseline)
        for path, saved in snapshots.items():
            assert api(path) == saved, ('Program Restore changed Native user asset', path)
        restart(candidate)
        for path, saved in snapshots.items():
            assert api(path) == saved, ('Candidate reapply changed Native user asset', path)
        assert run_state(doc_case) == runtime_before
        assert api('/api/v1/tools/id/c3_confluence/valves/user')['PAT'] == 'synthetic-local-c3'
        navigate_chat(message_chat_id)
        message_visible()
        shot('phase3-native-conversation-program-restore')
        navigate_chat(chat_id)
        evidence['assets'] = {'same_native_response_count': len(paths), 'tool_ids': tool_ids,
                              'skill_id': skill['id'], 'prompt_id': prompt['id'],
                              'program_restore_db_restore': False, 'user_valves_preserved': True,
                              'same_completed_run': runtime_before['id'], 'native_chat_messages': 2,
                              'message_history_exact': transcript, 'composer_send': False}
        record('Phase3 program-only Restore and reapply preserved Native/EES data', native_records=len(paths),
               same_completed_run=True, same_personal_key=True, db_or_asset_rollback=False,
               same_native_chat_messages=2, browser_display_after_program_restore=True)

        # Kill only this temporary official app during one held outbound read.
        # Production lease recovery must yield UNKNOWN without redispatch.
        cid_unknown = create_case(docs['process_id'])
        if not browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        click('#ees-work-run-view [data-action="history_view"]')
        click('[data-action="history_case"][data-case-id=' + json.dumps(doc_case) + ']')
        wait('document.querySelector("#ees-work-content")?.innerText.includes("읽기 전용")')
        complete_display = history_record(human_done)
        assert human_done['jobs'][node_ids['new-c3-human-j']]['validation']['status'] == 'succeeded'
        assert complete_display['criterion'] == 'passed', complete_display
        if browser.evaluate('document.querySelector(".ew-panel-menu")?.open'):
            click('.ew-panel-menu > summary')
        history_record(human_done)
        shot('phase3-native-past-complete-human')
        evidence['history'].append({'saved_run': human_done, 'displayed': complete_display,
                                    'route': 'more/history/past-case', 'compatibility_fixture': False})
        record('Phase3 actual Native completed human historical verdict', saved='succeeded', displayed='passed', read_only=True)
        choose(docs['process_id'])
        provider.hold = True
        provider.entered.clear()
        provider.release.clear()
        start('new-documents-search-j', {'query': '재기동 경계', 'space_key': 'EMS'})
        assert provider.entered.wait(8), 'Native external call did not reach the loopback provider'
        running = until_run(cid_unknown, {'running'})
        reflect('running')
        count_before = len(provider.calls)
        restart(abrupt=True)
        recovered = until_run(cid_unknown, {'unknown'}, timeout=38)
        provider.hold = False
        provider.release.set()
        assert recovered['id'] == running['id'] and len(provider.calls) == count_before
        assert len(recovered['calls']) == 1 and recovered['calls'][0]['status'] == 'unknown'
        reload_page()
        choose('new-documents-t')
        choose('new-documents-search-j')
        reflect('unknown')
        assert browser.evaluate('document.querySelectorAll("[data-runtime-action]").length') == 0
        shot('phase3-native-restart-unknown')
        evidence['runs'].append({'label': 'abrupt-restart', 'before': running, 'after': recovered,
                                'external_calls_before': count_before, 'external_calls_after': len(provider.calls)})
        record('Phase3 killed real app dispatch recovers UNKNOWN', same_run=True, dispatched_once=True,
               automatic_retry=False, status=recovered['status'])
        evidence['ok'] = True
    finally:
        (out / 'phase3-integrated.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
