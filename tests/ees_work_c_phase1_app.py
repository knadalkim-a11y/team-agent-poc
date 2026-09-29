"""Explicit complete-app C-phase gate; not loaded by unittest discovery.

Run with the repository's one Python test environment plus the full-app
dependencies required for startup. Both phases execute the official CLI and real temporary
Native databases. Chrome uses the packaged frontend and real HTTP endpoints.
Authentication is always real. Phase3/composer/visual modes use loopback
synthetic external HTTP/model responses; the other modes have no provider.
AP business results remain the product's declared legacy simulation.

Example: python tests/ees_work_c_phase1_app.py --wheel <candidate.whl>
  --baseline-wheel <official.whl> --chrome <chrome> --output <evidence-directory>
Only new temporary data is used. Reports and screenshots exclude auth tokens.
Use --navigation-only for the completed-J return regression on the real app;
the AP result is prepared through its existing simulation API, not revalidated.
Use --phase2 for actual browser manual/default-input and P/T scope actions.
Use --phase3 for the integrated Native gate. Only external HTTP/model responses
come from a loopback synthetic provider; Native auth/chat, tools, ACL, approval,
publication, execution and persistence remain the packaged product.
Use --composer-only for the focused real Native send-button/reload gate.
Use --visual-match-only for full-app C-view captures and measured geometry.
Add --visual-interactions for changed-surface Native/workflow interaction gates;
only external embedding vectors are synthetic during the real file-upload gate.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from zipfile import ZipFile

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--baseline-wheel', type=Path)
    parser.add_argument('--chrome', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--navigation-only', action='store_true')
    parser.add_argument('--phase2', action='store_true')
    parser.add_argument('--phase3', action='store_true')
    parser.add_argument('--composer-only', action='store_true')
    parser.add_argument('--visual-match-only', action='store_true')
    parser.add_argument('--visual-interactions', action='store_true')
    parser.add_argument('--visual-file-only', action='store_true')
    parser.add_argument('--visual-layout-check', action='store_true')
    parser.add_argument('--visual-authoring-only', action='store_true')
    parser.add_argument('--visual-detail-check', action='store_true')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--upstream-wheel', type=Path)
    args = parser.parse_args()
    ROOT = Path(__file__).resolve().parents[1]
    OUT = args.output.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.visual_match_only:
        from ees_work_c_visual_fullapp import audit_visual_source
        assert args.upstream_wheel, '--visual-match-only requires --upstream-wheel for source-byte verification'
        visual_source_audit = audit_visual_source(args.source_root or ROOT, args.upstream_wheel, args.wheel, OUT)
    LABEL = 'fullapp'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    BASE = f'http://127.0.0.1:{port}'
    temporary = tempfile.TemporaryDirectory(prefix='ees-c-phase1-app-')
    work = Path(temporary.name)
    credentials = {'name': 'C단계 합성 관리자', 'email': 'c-phase1-' + uuid4().hex + '@example.test',
                   'password': secrets.token_urlsafe(32)}
    # Do not inherit a developer's Native DB, provider, webhook, Redis, or
    # account settings. Only process/platform support variables are forwarded.
    process_environment = {key: value for key, value in os.environ.items() if key in {
        'PATH', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'TEMP', 'TMP', 'SYSTEMROOT',
        'WINDIR', 'LD_LIBRARY_PATH', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}}
    environment = dict(process_environment, DATA_DIR=str(work/'data'), DATABASE_URL='sqlite:///' + str(work/'data/webui.db'),
        WEBUI_SECRET_KEY=secrets.token_urlsafe(48), OFFLINE_MODE='true', HF_HUB_OFFLINE='1',
        HF_HUB_DISABLE_TELEMETRY='1', TRANSFORMERS_OFFLINE='1', ANONYMIZED_TELEMETRY='false',
        DO_NOT_TRACK='true', ENABLE_OLLAMA_API='false', ENABLE_OPENAI_API='false',
        RAG_EMBEDDING_ENGINE='openai', ENABLE_VERSION_UPDATE_CHECK='false',
        ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS='false', ENABLE_OTEL='false',
        OPENAI_API_KEY='', OLLAMA_API_KEY='', OPENAI_API_BASE_URL='http://127.0.0.1:1/v1',
        OLLAMA_BASE_URL='http://127.0.0.1:1', WEBUI_ADMIN_EMAIL='', WEBUI_ADMIN_PASSWORD='')
    provider = None
    if args.phase3 or args.composer_only or args.visual_match_only:
        from ees_work_c_phase3_fullapp import SyntheticProvider
        provider = SyntheticProvider()
        environment.update(ENABLE_OPENAI_API='true', OPENAI_API_BASE_URL=provider.base + '/v1',
                           OPENAI_API_BASE_URLS=provider.base + '/v1', OPENAI_API_KEY='synthetic-local-only',
                           OPENAI_API_KEYS='synthetic-local-only', ENABLE_VALVE_ENCRYPTION='true')
    if args.composer_only or args.visual_match_only:
        environment.update(DEFAULT_MODELS='c3-synthetic-model', ENABLE_TITLE_GENERATION='false',
                           ENABLE_TAGS_GENERATION='false', ENABLE_FOLLOW_UP_GENERATION='false')
    if args.visual_interactions or args.visual_file_only:
        assert args.visual_match_only, 'Visual interaction options require --visual-match-only'
        provider.allow_embeddings = True
        environment.update(RAG_OPENAI_API_BASE_URL=provider.base + '/v1',
                           RAG_OPENAI_API_KEY='synthetic-local-only', RAG_EMBEDDING_MODEL='synthetic-embedding')
    (work/'data').mkdir(mode=0o700)

    def unpack(wheel, name):
        destination = work/name
        with ZipFile(wheel) as archive:
            assert 'open_webui/main.py' in archive.namelist(), 'A complete Open WebUI wheel is required'
            for member in archive.infolist():
                assert (destination/member.filename).resolve().is_relative_to(destination.resolve()), 'Unsafe wheel path'
            archive.extractall(destination)
        return destination

    program = unpack(args.wheel.resolve(), 'candidate')
    baseline = unpack(args.baseline_wheel.resolve(), 'baseline') if args.baseline_wheel else program
    command = [sys.executable, '-c', 'from open_webui import app; app()', 'serve', '--host', '127.0.0.1', '--port', str(port)]

    def launch(program, output):
        return subprocess.Popen(command, cwd=work, env=dict(environment, PYTHONPATH=str(program)),
                                stdout=output, stderr=subprocess.STDOUT)

    def ready(client, process):
        deadline = time.monotonic() + 40
        while True:
            if process.poll() is not None:
                raise RuntimeError('Complete Native app exited: ' + str(process.returncode))
            try:
                if client.get('/ready').status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('Complete Native app readiness deadline exceeded')
            time.sleep(0.25)

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    report = {'scope': 'Full packaged Native/EES app with real Native auth/chat and EES SQLite APIs; legacy AP simulation, no live provider', 'steps': []}
    if args.visual_match_only:
        report['visual_source_audit'] = visual_source_audit
        report['visual_harness_sha256'] = {name: hashlib.sha256((ROOT/'tests'/name).read_bytes()).hexdigest()
            for name in ('ees_work_c_phase1_app.py', 'ees_work_c_phase3_fullapp.py',
                         'ees_work_c_visual_fullapp.py', 'ees_work_c_visual_interactions.py')}
    def record(name, **result):
        report['steps'].append({'name': name, **result})
        print(name, result, flush=True)

    report['programs'] = {label: {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                          for label, path in [('candidate', args.wheel), *([('baseline', args.baseline_wheel)] if args.baseline_wheel else [])]}
    report['startup'] = ('Official Open WebUI CLI, one Python environment, new temporary DATA_DIR, '
                         + ('loopback synthetic external HTTP/OpenAI responses' if provider else 'model/provider access disabled'))
    with (OUT/'baseline-server.log').open('w', encoding='utf-8') as baseline_log:
        server = launch(baseline, baseline_log)
        try:
            with httpx.Client(base_url=BASE, trust_env=False, timeout=10) as client:
                ready(client, server)
                response = client.post('/api/v1/auths/signup', json=credentials)
                response.raise_for_status()
                initial_session = response.json()
                assert initial_session['role'] == 'admin'
                response = client.post('/api/v1/chats/new', headers={'Authorization':'Bearer ' + initial_session['token']},
                    json={'chat': {'title':'C단계 실제 Native 저장 확인','models':[],'messages':[],
                                   'history':{'messages':{},'currentId':None},'params':{},'timestamp':int(time.time())}})
                response.raise_for_status()
                previous = {'session':initial_session, 'chat_id':response.json()['id']}
                record('Real Native signup and chat creation', role=initial_session['role'], status=response.status_code)
        finally:
            stop(server)

    log = (OUT / (LABEL + '-server.log')).open('w', encoding='utf-8')
    server = launch(program, log)
    browser = None
    try:
        with httpx.Client(base_url=BASE, trust_env=False, timeout=10) as client:
            ready(client, server)
            response = client.post('/api/v1/auths/signin', json={key:credentials[key] for key in ('email','password')})
            response.raise_for_status()
            session = response.json()
            assert session['id'] == previous['session']['id']
            headers = {'Authorization': 'Bearer ' + session['token']}
            chat_id = previous['chat_id']
            response = client.get('/api/v1/chats/' + chat_id, headers=headers)
            response.raise_for_status()
            assert response.json()['chat']['title'] == 'C단계 실제 Native 저장 확인'
            record('Program upgrade preserved real Native identity/chat' if args.baseline_wheel else
                   'Real Native session reconnected to its temporary chat', same_identity=True, same_chat=True)

            def current():
                response = client.get('/api/ees-work/state', params={'chat_id': chat_id}, headers=headers)
                response.raise_for_status()
                state = response.json()
                assert state['ok'], state
                return state

            def action(body):
                response = client.post('/api/ees-work/action', json=body, headers=headers)
                response.raise_for_status()
                state = response.json()
                assert state['ok'], state
                return state

            state = current()
            if not state.get('case') and not args.visual_match_only:
                state = action({'action': 'create', 'chat_id': chat_id, 'payload': {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p'}})
            for node_id in (() if args.phase2 or args.composer_only or args.visual_match_only else ('scope-j', 'infra-j', 'install-j')):
                if state['case']['jobs'][node_id]['status'] != 'passed':
                    case = state['case']
                    state = action({'action': 'run', 'chat_id': chat_id, 'case_id': case['id'], 'expected_revision': case['revision'], 'node_id': node_id, 'payload': {'confirm': True}})
                    assert state['case']['jobs'][node_id]['status'] == 'passed', state['case']['jobs'][node_id]
            if state.get('case'):
                record('Real EES case create/prerequisites', case_id=state['case']['id'], native_chat_bound=state['case']['chat_id'] == chat_id)
            if args.navigation_only:
                # Prepare only the existing declared simulation, through the
                # unmodified EES API. This is not live AP/tool execution.
                for _ in range(2):
                    case = state['case']
                    state = action({'action': 'run', 'chat_id': chat_id, 'case_id': case['id'],
                                    'expected_revision': case['revision'], 'node_id': 'ap-j',
                                    'payload': {'confirm': True}})
                assert state['case']['jobs']['ap-j']['status'] == 'passed'
                record('Navigation fixture prepared with existing AP simulation', status='passed')

            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / 'tests'))
            from test_ees_chat_theme import ChromePipe
            browser = ChromePipe(str(args.chrome.resolve()), str(work/'chrome'))
            browser.navigate('about:blank')
            browser.call('Runtime.enable')
            browser.call('Network.enable')
            browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': 'localStorage.setItem("token",' + json.dumps(session['token']) + ');localStorage.setItem("locale","ko-KR");localStorage.setItem("version","0.11.3+ees.12");'})
            browser.call('Page.navigate', {'url': BASE + '/c/' + chat_id})

            def wait(expression, timeout=12000):
                result = browser.evaluate('new Promise(resolve=>{const end=performance.now()+' + str(timeout) + ';function check(){if(' + expression + ')return resolve(true);if(performance.now()>end)return resolve(false);setTimeout(check,80)}check()})')
                assert result, expression + '\n' + browser.evaluate('document.body.innerText.slice(0,2200)')

            def click(selector, confirm=None):
                wait('!!document.querySelector(' + json.dumps(selector) + ')')
                stable = browser.evaluate('(async()=>{await document.fonts.ready;return await new Promise(resolve=>{let same=0,last="";const end=performance.now()+9000;function check(){const e=document.querySelector(' + json.dumps(selector) + ');e?.scrollIntoView({block:"center"});const r=e?.getBoundingClientRect();const p=r&&[r.x,r.y,r.width,r.height].join();same=p===last&&r.width>0&&r.height>0&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))?same+1:0;last=p;if(same>=8)return resolve(true);if(performance.now()>end)return resolve(false);requestAnimationFrame(check)}check()})})()')
                assert stable, 'Control is not visible/stable: ' + selector
                point = browser.evaluate('(()=>{const e=document.querySelector(' + json.dumps(selector) + ');if(!e)throw Error("Missing control");e.scrollIntoView({block:"center"});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2,hit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}})()')
                assert point['hit'], (selector, point)
                for kind in ('mousePressed', 'mouseReleased'):
                    params = {'type': kind, 'x': point['x'], 'y': point['y'], 'button': 'left', 'clickCount': 1}
                    if confirm is not None and kind == 'mouseReleased':
                        # The original legacy confirmation uses Chrome's real
                        # blocking dialog. Do not replace window.confirm.
                        browser.counter += 1
                        request = {'id': browser.counter, 'sessionId': browser.session,
                                   'method': 'Input.dispatchMouseEvent', 'params': params}
                        os.write(browser.request_write, json.dumps(request).encode() + b'\0')
                        deadline = time.monotonic() + 8
                        while True:
                            event = browser.receive(deadline)
                            browser.events.append(event)
                            if event.get('method') == 'Page.javascriptDialogOpening':
                                browser.call('Page.handleJavaScriptDialog', {'accept': confirm})
                                break
                    else:
                        browser.call('Input.dispatchMouseEvent', params)

            def shot(name):
                (OUT / (LABEL + '-' + name + '.png')).write_bytes(base64.b64decode(browser.call('Page.captureScreenshot', {'format': 'png'})['data']))

            if args.visual_match_only:
                from ees_work_c_visual_fullapp import authoring_only_gate, visual_gate
                report['scope'] = 'Official packaged Native app, real authentication/chat and synthetic workflow records in temporary DB; no fixture app or CSS overrides'
                if args.visual_authoring_only:
                    authoring_only_gate(out=OUT, client=client, headers=headers, browser=browser,
                                        base=BASE, chat_id=chat_id, click=click, wait=wait,
                                        shot=shot, record=record)
                    report['ok'] = True
                    return
                visual_gate(out=OUT, client=client, headers=headers, browser=browser,
                            base=BASE, chat_id=chat_id, provider=provider,
                            click=click, wait=wait, shot=shot, record=record,
                            interactions=args.visual_interactions, file_only=args.visual_file_only,
                            layout_check=args.visual_layout_check, detail_check=args.visual_detail_check)
                report['ok'] = True
                return

            if args.composer_only:
                from ees_work_c_phase3_fullapp import composer_gate
                report['scope'] = 'Real Native composer button with work panel; real auth/chat/EES/temporary DB; only external model is loopback synthesis'
                composer_gate(out=OUT, client=client, headers=headers, browser=browser,
                              base=BASE, chat_id=chat_id, provider=provider,
                              click=click, wait=wait, shot=shot, record=record)
                report['ok'] = True
                return

            def navigation_check():
                row = '#ees-work-content [data-work-job="ap-j"] [data-action="select"]'
                completion = '.ew-work-action-region button[data-node-id="install-t"]'

                def selected(title):
                    wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === ' +
                         json.dumps(title) + ' && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')

                def list_state():
                    return browser.evaluate('''(()=>{const body=document.querySelector('#ees-work-content');
                      return {query:body.querySelector('#ees-work-job-search')?.value,
                        filter:body.querySelector('[data-action=job_filter][aria-pressed=true]')?.dataset.filter,
                        page:body.querySelector('.ew-work-pagination')?.innerText,
                        expanded:!!body.querySelector('[data-work-condition="ap-j"]'),
                        scroll:body.scrollTop,
                        focusNode:document.activeElement?.dataset.nodeId ?? null,
                        focusAction:document.activeElement?.dataset.action ?? null};})()''')

                # Both sizes use the exact same saved AP result. No CSS or
                # DOM placement overrides force the action into either slot.
                for width, height, expected_layout in ((1920, 1440, 'inline'), (1366, 768, 'dock')):
                    browser.call('Emulation.setDeviceMetricsOverride', {
                        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                    selected('신규 공장 횡전개')
                    click('#ees-work-content .ew-work-list [data-action="select"][data-node-id="install-t"]')
                    selected('시스템 설치')
                    click('#ees-work-job-search')
                    browser.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'a', 'code': 'KeyA',
                                                           'modifiers': 2, 'windowsVirtualKeyCode': 65})
                    browser.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'a', 'code': 'KeyA',
                                                           'modifiers': 2, 'windowsVirtualKeyCode': 65})
                    browser.call('Input.insertText', {'text': 'AP'})
                    wait('document.querySelector("#ees-work-job-search")?.value === "AP"')
                    click('#ees-work-content [data-action="job_filter"][data-filter="completed"]')
                    if not browser.evaluate('!!document.querySelector("#ees-work-content [data-work-condition=ap-j]")'):
                        click('#ees-work-content [data-action="job_condition"][data-node-id="ap-j"]')
                    # Position the real row before capture. click() uses the
                    # same center positioning, so the saved departure offset
                    # is precisely the offset checked on return.
                    browser.evaluate('document.querySelector(' + json.dumps(row) + ').scrollIntoView({block:"center"})')
                    before = list_state()
                    assert before['query'] == 'AP' and before['filter'] == 'completed' and before['expanded'], before
                    click(row)
                    selected('AP 연결 확인')
                    wait('!!document.querySelector(' + json.dumps(completion) + ')')
                    layout = browser.evaluate('document.querySelector(' + json.dumps(completion) + ').closest("#ees-work-action-dock") ? "dock" : "inline"')
                    assert layout == expected_layout, {'expected': expected_layout, 'actual': layout}
                    assert browser.evaluate('document.querySelector(' + json.dumps(completion) + ').textContent') == '단계로 돌아가기'
                    shot('return-' + expected_layout + '-completed')
                    click(completion)  # The completed-area CTA, never the top path.
                    selected('시스템 설치')
                    after = list_state()
                    parent = browser.evaluate('document.querySelector("#ees-work-parent")?.innerText')
                    record('Completed CTA observed ' + expected_layout,
                           viewport=[width, height], before=before, after=after, parent=parent)
                    for key in ('query', 'filter', 'page', 'expanded'):
                        assert after[key] == before[key], (key, before, after)
                    assert abs(after['scroll'] - before['scroll']) <= 2, (before, after)
                    assert after['focusNode'] == 'ap-j' and after['focusAction'] == 'select', after
                    assert '신규 공장 횡전개' in parent and 'AP 연결 확인' not in parent, parent
                    shot('return-' + expected_layout + '-restored-t')
                    record('Completed CTA real app return ' + expected_layout,
                           viewport=[width, height], before=before, after=after, parent=parent)
                    click('#ees-work-parent [data-action="panel_back"]')
                    selected('신규 공장 횡전개')
                    assert browser.evaluate('document.activeElement?.dataset.nodeId') == 'install-t'
                    record('T to P preserved ' + expected_layout, focus='install-t')

                # Sidebar entry deliberately has no originating T row/trail.
                click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
                selected('시스템 설치')
                click('#ees-work-tree [data-action="select"][data-node-id="ap-j"]')
                selected('AP 연결 확인')
                click(completion)
                selected('시스템 설치')
                parent = browser.evaluate('document.querySelector("#ees-work-parent")?.innerText')
                assert '신규 공장 횡전개' in parent and 'AP 연결 확인' not in parent, parent
                click('#ees-work-close')
                wait('!document.querySelector("#ees-work-panel")?.getClientRects().length')
                click('#ees-work-context-open')
                selected('시스템 설치')
                assert '신규 공장 횡전개' in browser.evaluate('document.querySelector("#ees-work-parent")?.innerText')
                assert current()['case']['jobs']['ap-j']['status'] == 'passed'
                shot('return-sidebar-reopened-t')
                record('Sidebar direct return and close/reopen', parent='신규 공장 횡전개', saved_result='passed')

            wait('!!document.querySelector("#ees-work-entry") && !!document.querySelector("#chat-input.ProseMirror")')
            # Dismiss only the real first-run release-note dialog if present.
            browser.evaluate('[...document.querySelectorAll("button")].find(e=>/Okay, Let.s Go!|좋아요, 시작/.test(e.textContent))?.click()')
            if browser.evaluate('document.querySelector("#sidebar").getBoundingClientRect().width < 200'):
                click('button[aria-label="사이드바 열기"],button[aria-label="Open sidebar"]')
            wait('document.querySelector("#sidebar").getBoundingClientRect().width > 200')
            click('[data-work-category="setup"]')
            wait('!!document.querySelector("#ees-work-tree")')
            p_control = '#ees-work-entry [data-action="select"][data-node-id="setup-p"]'
            if browser.evaluate('!!document.querySelector(' + json.dumps(p_control) + ')?.closest("details:not([open])")'):
                click('#ees-work-entry .ew-workflow-picker > summary')
            click(p_control)
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "신규 공장 횡전개" && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
            shot('p-management')
            record('Real browser P management', title='신규 공장 횡전개', panel_level=browser.evaluate('document.querySelector("#ees-work-panel").dataset.workLevel'))
            if args.phase2:
                def selected(title):
                    wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === ' + json.dumps(title)
                         + ' && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')

                def single_action():
                    count = browser.evaluate('document.querySelectorAll("#ees-work-panel .ew-work-action-region").length')
                    assert count == 1, count

                click('#ees-work-content [data-action="select"][data-node-id="prep-t"]')
                selected('사전준비')
                click('#ees-work-content [data-work-job="scope-j"] [data-action="select"]')
                selected('셋업 범위 확인')
                single_action()
                assert not browser.evaluate('!!document.querySelector("#ees-work-inputs-save")')
                click('#ees-work-run', confirm=False)
                assert current()['case']['jobs']['scope-j']['attempt'] == 0
                click('#ees-work-run', confirm=True)
                wait('document.querySelector(".ew-work-action-region [data-action=panel_parent]")')
                assert current()['case']['jobs']['scope-j']['status'] == 'passed'
                shot('phase2-manual-completed')
                click('.ew-work-action-region [data-action="panel_parent"]')
                selected('사전준비')
                record('Phase2 manual real browser confirmation', cancelled_attempt=0, confirmed='passed', fake_input=False)
                click('#ees-work-tree [data-action="select"][data-node-id="infra-t"]')
                selected('AP, DB 인프라 준비')
                click('#ees-work-content [data-work-job="infra-j"] [data-action="select"]')
                selected('인프라 준비 확인')
                single_action()
                assert current()['case']['jobs']['infra-j']['inputs'] == {}
                assert not browser.evaluate('document.querySelector("#ees-work-run").disabled')
                click('#ees-work-run')  # Existing defaults remain executable without a save prerequisite.
                wait('document.querySelector(".ew-work-action-region [data-action=panel_parent]")')
                infra = current()['case']['jobs']['infra-j']
                assert infra['status'] == 'passed' and infra['attempt'] == 1
                assert infra['history'][-1]['simulation'] is True
                record('Phase2 default-input simulation', passed=True, persisted_inputs=infra['inputs'], external_calls=0)
                click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
                selected('시스템 설치')
                click('#ees-work-content [data-work-job="install-j"] [data-action="select"]')
                selected('설치·설정 확인')
                click('#ees-work-run', confirm=True)
                wait('document.querySelector(".ew-work-action-region [data-action=panel_parent]")')
                click('.ew-work-action-region [data-action="panel_parent"]')
                selected('시스템 설치')
                single_action()
                assert browser.evaluate('document.querySelector("#ees-work-run").textContent') == '범위 모의 점검 실행'
                click('#ees-work-run')
                wait('!document.querySelector("#ees-work-panel").matches("[aria-busy=true]") && document.querySelector("#ees-work-content").innerText.includes("실패")')
                case = current()['case']
                assert case['jobs']['db-j']['status'] == 'passed'
                assert case['jobs']['ap-j']['status'] == 'failed'
                assert case['jobs']['scope-j']['attempt'] == 1 and case['jobs']['install-j']['attempt'] == 1
                assert case['status'] != 'passed'
                shot('phase2-t-scope-partial')
                record('Phase2 real T scope simulation', db='passed', ap='failed', manual_not_replayed=True,
                       process_not_complete=True, progress=case['progress'])
                errors = [{'url': e['params']['response']['url'], 'status': e['params']['response']['status']}
                          for e in browser.events if e.get('method') == 'Network.responseReceived'
                          and e['params']['response']['status'] >= 400]
                assert not errors, errors
                record('Browser API responses', errors=errors)
                report['ok'] = True
                return
            if args.navigation_only:
                navigation_check()
                errors = [{'url': e['params']['response']['url'], 'status': e['params']['response']['status']}
                          for e in browser.events if e.get('method') == 'Network.responseReceived'
                          and e['params']['response']['status'] >= 400]
                record('Browser API responses', errors=errors)
                assert not errors, errors
                report['ok'] = True
                return
            click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "시스템 설치"')
            shot('t-management')
            click('#ees-work-tree [data-action="select"][data-node-id="ap-j"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "AP 연결 확인" && !!document.querySelector("#ees-work-run") && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
            input_control = '#ees-work-inputs input[name="ap"]'
            if browser.evaluate('!!document.querySelector(' + json.dumps(input_control) + ')?.closest("details:not([open])")'):
                click('.ew-work-edit > summary')
            click(input_control)
            browser.call('Input.dispatchKeyEvent', {'type':'keyDown','key':'a','code':'KeyA','modifiers':2,'windowsVirtualKeyCode':65})
            browser.call('Input.dispatchKeyEvent', {'type':'keyUp','key':'a','code':'KeyA','modifiers':2,'windowsVirtualKeyCode':65})
            target_value = 'C단계 합성 AP 대상 · 외부 호출 없음'
            browser.call('Input.insertText', {'text':target_value})
            click('#ees-work-inputs-save')
            deadline = time.monotonic() + 8
            while current()['case']['jobs']['ap-j']['inputs'].get('ap') != target_value:
                if time.monotonic() > deadline:
                    raise AssertionError('Browser input save did not reach the real API store')
                time.sleep(0.1)
            browser.events.clear()
            browser.call('Page.reload')
            deadline = time.monotonic() + 15
            while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
                browser.events.append(browser.receive(deadline))
            wait('!!document.querySelector("#ees-work-context-open") && !!document.querySelector("#chat-input.ProseMirror")')
            # Opening the panel is page-local UI state; stored job input and
            # the selected case/chat must survive a real reload independently.
            if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
                click('#ees-work-context-open')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "AP 연결 확인" && !!document.querySelector("#ees-work-run") && !document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]") && !!document.querySelector(' + json.dumps(input_control) + ')')
            assert current()['case']['id'] == state['case']['id']
            assert current()['case']['chat_id'] == chat_id
            assert current()['case']['jobs']['ap-j']['inputs']['ap'] == target_value
            assert browser.evaluate('document.querySelector(' + json.dumps(input_control) + ').value') == target_value
            assert current()['case']['jobs']['ap-j']['attempt'] == 0
            record('Browser input edit/save/reload', value_preserved=True, no_job_run=True)
            before = current()['case']['jobs']['ap-j']['attempt']
            click('#ees-work-run')
            wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]") && document.querySelector("#ees-work-panel")?.innerText.includes("실패")')
            failed = current()['case']['jobs']['ap-j']
            assert failed['status'] == 'failed' and failed['attempt'] == before + 1, failed
            shot('j-failed')
            record('Real browser AP simulation first failure', status=failed['status'], attempt=failed['attempt'])
            click('#ees-work-run')
            wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]") && document.querySelector("#ees-work-panel")?.innerText.includes("완료")')
            passed = current()['case']['jobs']['ap-j']
            assert passed['status'] == 'passed' and passed['attempt'] == before + 2, passed
            assert len(passed['history']) == 2 and passed['history'][0] == failed['history'][0]
            shot('j-passed')
            click('#ees-work-panel [data-action="work_detail"][data-detail-tab="history"]')
            wait('document.querySelectorAll("#ees-work-dialog [data-action=detail_attempt]").length === 2')
            click('#ees-work-dialog [data-action="detail_attempt"][data-attempt-index="0"]')
            wait('document.querySelector("#ees-work-dialog .ew-detail-outcome [data-status=failed]")')
            click('#ees-work-dialog [data-action="detail_tab"][data-detail-tab="input"]')
            wait('document.querySelector("#ees-work-dialog [data-work-detail-content=input]")?.innerText.includes(' + json.dumps(target_value) + ')')
            click('#ees-work-dialog [data-action="detail_tab"][data-detail-tab="output"]')
            wait('!!document.querySelector("#ees-work-dialog [data-work-detail-content=output]")')
            shot('history-input-output')
            browser.call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
            browser.call('Input.dispatchKeyEvent', {'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
            wait('!document.querySelector("#ees-work-dialog")?.open')
            record('Saved history and I/O', attempts=2, historical_failure=True, saved_input=True)
            click('#ees-work-close')
            wait('!document.querySelector("#ees-work-panel")?.getClientRects().length')
            assert browser.evaluate('document.querySelector("#chat-container").getClientRects().length > 0')
            click('#ees-work-context-open')
            wait('document.querySelector("#ees-work-panel")?.getClientRects().length > 0')
            assert current()['case']['jobs']['ap-j']['status'] == 'passed'
            record('Close/reopen preserves real Native chat and AP result', passed=True)
            browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            wait('document.querySelector("#ees-work-panel")?.getClientRects().length > 0')
            shot('j-1366')
            if args.phase3:
                from ees_work_c_phase3_fullapp import integrated_gate

                def restart(target=program, abrupt=False):
                    nonlocal server
                    if abrupt:
                        server.kill()
                        server.wait(timeout=5)
                    else:
                        stop(server)
                    server = launch(target, log)
                    ready(client, server)

                integrated_gate(root=ROOT, out=OUT, work=work, client=client, headers=headers,
                    browser=browser, base=BASE, chat_id=chat_id, session=session, provider=provider,
                    click=click, wait=wait, shot=shot, record=record, restart=restart,
                    navigation_check=navigation_check, baseline=baseline, candidate=program)
            errors = [{'url': e['params']['response']['url'], 'status': e['params']['response']['status']} for e in browser.events if e.get('method') == 'Network.responseReceived' and e['params']['response']['status'] >= 400]
            record('Browser API responses', errors=errors)
            assert not errors, errors
            report['ok'] = True
    except Exception as error:
        report['error'] = str(error)
        if browser:
            try:
                shot('failure')
                (OUT / (LABEL + '-failure-dom.txt')).write_text(browser.evaluate('document.body.innerText'), encoding='utf-8')
                report['failure_font_state'] = browser.evaluate('({status:document.fonts.status,faces:[...document.fonts].filter(f=>f.status!=="unloaded").map(f=>({family:f.family,status:f.status,weight:f.weight}))})')
            except Exception:
                pass
        raise
    finally:
        if browser:
            browser.close()
        stop(server)
        log.close()
        if provider:
            report['synthetic_provider'] = provider.evidence()
            provider.close()
        (OUT / (LABEL + '-result.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

        temporary.cleanup()


if __name__ == "__main__":
    main()
