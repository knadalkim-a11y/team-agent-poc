"""Built Native browser + real integrated workflow SQLite fixture.

Native authentication/chat/model HTTP responses here are synthetic. The separate
Native account fixture and complete CLI app gate exercise real authentication.
Procedures are authored through the production command service, never seeded.
"""
import asyncio
import base64
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from uuid import uuid4

from native_ui_fixture import NativeUIServer
from test_ees_chat_theme import ChromePipe

ROOT = Path(__file__).resolve().parents[1]


class SyntheticReadBridge:
    """Only the external transport is synthetic; acceptance/history are real."""
    def __init__(self):
        self.calls = []
        self.result = {'status': 'succeeded', 'completeness': 'complete', 'items': [], 'data': {'summary': '합성 조회 근거'}}
        self.hold = threading.Event(); self.hold.set()
        self.started = threading.Event()
        self.allowed = True
        self.error_type = RuntimeError

    async def check(self, actor, reference):
        if not self.allowed:
            raise self.error_type('native_access_denied', '현재 자료 조회 권한이 없습니다.')
        return {'reference': reference, 'state': 'allowed'}

    async def invoke(self, actor, reference, arguments, context):
        await self.check(actor, reference)
        self.calls.append({'actor': actor['id'], 'arguments': deepcopy(arguments), 'context': deepcopy(context)})
        self.started.set()
        await asyncio.to_thread(self.hold.wait, 30)
        return deepcopy(self.result)


class IntegratedNativeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get('EES_TEST_CHROME')
        cls.chrome = shutil.which(explicit or 'google-chrome')
        directory = os.environ.get('EES_TEST_BRANDING_DIR')
        if not cls.chrome or not directory:
            if explicit or os.environ.get('CI'):
                raise RuntimeError('The Native browser gate requires Chrome and the built product')
            raise unittest.SkipTest('Native browser/wheel unavailable outside required CI gate')
        manifest = json.loads((Path(directory) / 'manifest.json').read_text(encoding='utf-8'))
        cls.wheel_path = Path(directory) / manifest['wheel']['filename']

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ees-integrated-native-')
        self.addCleanup(self.temporary.cleanup)
        self.server = NativeUIServer(self.wheel_path)
        self.addCleanup(self.server.server_close)
        name = 'ees_integrated_browser_' + uuid4().hex
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
        sys.modules[name] = package
        module = importlib.import_module(name + '.ees_workflow')
        self.backend = module
        self.bridge = SyntheticReadBridge(); self.bridge.error_type = module.WorkflowError
        self.users = {self.server.user['id']: self.server.user,
                      'other-user': {'id': 'other-user', 'role': 'user', 'name': 'Other synthetic user'}}
        self.server.workflow = module.WorkflowService(Path(self.temporary.name) / 'work.sqlite3',
            lambda key: self.users.get(key), lambda key: self.server.chats.get(key), native_bridge=self.bridge)
        module._service = self.server.workflow
        self.server.workflow_legacy = module.legacy_state
        self.addCleanup(self.bridge.hold.set)
        self.addCleanup(lambda: [sys.modules.pop(key, None) for key in list(sys.modules) if key == name or key.startswith(name + '.')])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.browser = ChromePipe(self.chrome, str(Path(self.temporary.name) / 'chrome'))
        self.addCleanup(self.browser.close)
        self.addCleanup(self.capture_failure)
        self.browser.navigate('about:blank')
        self.browser.call('Runtime.enable'); self.browser.call('Network.enable')
        # Explicit synthetic Native session fixture, not an authentication test.
        self.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source':
            "localStorage.setItem('token','fixture-token');localStorage.setItem('locale','ko-KR');localStorage.setItem('version','0.11.3');"})
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#chat-input.ProseMirror') && document.querySelector('#ees-work-entry')")
        self.open_sidebar()
        self.wait("document.querySelector('#ees-work-panel') && document.querySelector('#ees-work-system-trigger')?.getBoundingClientRect().height > 0")

    def open_sidebar(self):
        opened = "(()=>{const e=document.querySelector('#sidebar'),r=e?.getBoundingClientRect();return e?.getAttribute('aria-hidden')==='false'&&!e.inert&&r.width>200&&r.x>=0&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+50));})()"
        self.wait(opened + " || !!document.querySelector('button[aria-label=\"사이드바 열기\"]')")
        if not self.browser.evaluate(opened):
            self.click('button[aria-label="사이드바 열기"]')
        self.wait(opened)

    def tearDown(self):
        self.capture_failure()
        self.bridge.hold.set()
        for name in ('stream_hold', 'authoring_hold', 'workspace_response_hold', 'action_response_hold', 'completion_response_hold'):
            getattr(self.server, name).set()
        errors = [event['params']['exceptionDetails'].get('exception', {}).get('description')
                  or event['params']['exceptionDetails']['text'] for event in self.browser.events
                  if event.get('method') == 'Runtime.exceptionThrown']
        self.assertEqual(errors, [], errors)
        self.assertEqual(self.server.errors, [], self.server.errors)

    def command(self, action, expected_revision=0, user=None, **values):
        result = asyncio.run(self.server.workflow.workspace_command(user or self.server.user,
            dict(action=action, expected_revision=expected_revision, request_id=str(uuid4()), **values)))
        self.assertTrue(result['ok'], result)
        return result

    def state(self, **query):
        result = asyncio.run(self.server.workflow.workspace_state(self.server.user, **query))
        self.assertTrue(result['ok'], result)
        return result

    def author(self, name='합성 절차', fields=None, jobs=2, mode='human', block='human_confirm'):
        created = self.command('create_workflow', name=name, system_id='EMS')
        key = created['workflow_id']; definition = created['workflow']['draft']; root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['stage']
        definition['nodes']['stage'] = {'id': 'stage', 'type': 't', 'name': '검증 단계', 'parent': root,
            'children': ['job-' + str(index) for index in range(jobs)], 'deps': []}
        for index in range(jobs):
            job = 'job-' + str(index)
            definition['nodes'][job] = {'id': job, 'type': 'j', 'name': '합성 작업 ' + str(index), 'parent': 'stage',
                'children': [], 'deps': [], 'mode': mode, 'inputs': deepcopy(fields or []), 'result_block': block,
                'instructions': '합성 자료로 저장·판정 경계를 검증합니다.'}
            if mode == 'tool':
                definition['nodes'][job].update(tool_reference={'tool_id': 'synthetic-read', 'function': 'read',
                    'revision': 1, 'content_hash': 'a' * 64, 'schema_hash': 'b' * 64},
                    argument_bindings={field['id']: {'input': field['id']} for field in (fields or [])})
        self.command('save_draft', workflow_id=key, expected_revision=1, definition=definition)
        checked = self.command('validate_workflow', workflow_id=key, expected_revision=2)
        self.assertEqual(checked['validation']['errors'], [], checked)
        self.command('publish_workflow', workflow_id=key, expected_revision=2)
        return key

    def start(self, key, **values):
        revision = self.state(workflow_id=key)['workflow']['revision']
        return self.command('start_run', workflow_id=key, expected_revision=revision, **values)['run']

    def open_run(self, key, run, job='job-0'):
        self.open_sidebar()
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        control = '[data-action="workflow"][data-workflow-id="' + key + '"]'
        self.wait('document.querySelector(' + json.dumps(control) + ')')
        self.click(control)
        if job:
            selector = '#ees-work-panel [data-action="job"][data-job-id="' + job + '"]'
            self.wait('document.querySelector(' + json.dumps(selector) + ')')
            self.click(selector)
            self.wait("document.querySelector('#ees-work-panel h2')?.textContent === " + json.dumps(run['definition']['nodes'][job]['name']))

    def refresh(self):
        return self.browser.evaluate('window.__eesNativeWorkV1.refresh()')

    def navigate(self, path):
        self.browser.call('Page.navigate', {'url': self.server.url + path})

    def wait(self, expression, timeout=9000):
        self.last_wait = expression
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            try:
                if self.browser.evaluate('Boolean(' + expression + ')'):
                    return
            except AssertionError as error:
                if not any(fragment in str(error) for fragment in
                           ('navigated or closed', 'context was destroyed', 'Cannot find context', 'active page')):
                    raise
            time.sleep(.025)
        self.fail('Timed out: ' + expression + '\n' + self.text('body') + '\nUnknown routes:' + repr(self.server.unknown))

    def read(self, selector, prop='textContent'):
        return self.browser.evaluate('document.querySelector(' + json.dumps(selector) + ')?.' + prop)

    def text(self, selector):
        return self.read(selector, 'innerText') or ''

    def click(self, selector):
        self.last_click = selector
        # Readiness follows actual layout/visibility, not a longer fixed sleep.
        # Never enable, open, or click an element through DOM state mutation.
        point = self.browser.evaluate('new Promise(resolve=>{const end=performance.now()+5000;let previous="",stable=0;'
            'function check(){const e=[...document.querySelectorAll(' + json.dumps(selector) +
            ')].find(e=>e.getClientRects().length);e?.scrollIntoView({block:"center",inline:"nearest"});'
            'const r=e?.getBoundingClientRect(),x=r&&r.x+r.width/2,y=r&&r.y+r.height/2,key=r&&[r.x,r.y,r.width,r.height].join();'
            'const ready=r&&r.width>0&&r.height>0&&!e.disabled&&e.contains(document.elementFromPoint(x,y));'
            'stable=ready&&key===previous?stable+1:0;previous=key;'
            'if(stable>=2)return resolve({x,y});if(performance.now()>end)return resolve(null);requestAnimationFrame(check);}check();})')
        self.assertIsNotNone(point, 'Control not visibly ready for a physical click:' + selector)
        for kind in ('mousePressed', 'mouseReleased'):
            self.browser.call('Input.dispatchMouseEvent', {'type': kind, 'x': point['x'], 'y': point['y'],
                'button': 'left', 'buttons': int(kind == 'mousePressed'), 'clickCount': 1})

    def key(self, key, code, modifiers=0):
        for kind in ('keyDown', 'keyUp'):
            self.browser.call('Input.dispatchKeyEvent', {'type': kind, 'key': key, 'code': key,
                'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code, 'modifiers': modifiers})

    def fill(self, selector, value):
        self.click(selector); self.key('a', 65, 2)
        self.browser.call('Input.insertText', {'text': value}); self.key('Tab', 9)

    def choose(self, selector, value):
        index = self.browser.evaluate('[...document.querySelector(' + json.dumps(selector) + ').options].findIndex(o=>o.value===' + json.dumps(value) + ')')
        self.assertGreaterEqual(index, 0); self.click(selector); self.key('Home', 36)
        for _ in range(index): self.key('ArrowDown', 40)
        self.key('Enter', 13)

    def screenshot(self, label, *, wait_for_fonts=True):
        directory = Path(os.environ.get('EES_TEST_SCREENSHOT_DIR', ROOT / 'dist/ees-work-screenshots'))
        directory.mkdir(parents=True, exist_ok=True)
        if wait_for_fonts:
            self.browser.evaluate('document.fonts.ready.then(()=>true)')
        picture = self.browser.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})['data']
        (directory / (label + '.png')).write_bytes(base64.b64decode(picture))
        return directory

    def capture_failure(self):
        result = getattr(self._outcome, 'result', None)
        failures = list(getattr(result, 'failures', [])) + list(getattr(result, 'errors', []))
        if getattr(self, 'failure_evidence_captured', False) or not any(case is self or getattr(case, 'test_case', None) is self for case, _ in failures): return
        self.failure_evidence_captured = True
        label = 'integrated-' + self._testMethodName + '-failure'
        directory = Path(os.environ.get('EES_TEST_SCREENSHOT_DIR', ROOT / 'dist/ees-work-screenshots'))
        directory.mkdir(parents=True, exist_ok=True)
        report = {'test': self.id(), 'last_wait': getattr(self, 'last_wait', None),
                  'last_click': getattr(self, 'last_click', None), 'capture_errors': []}
        try:
            self.screenshot(label, wait_for_fonts=False)
        except Exception as error:
            report['capture_errors'].append('screenshot:' + type(error).__name__)
        try:
            report['dom'] = self.browser.evaluate("""(()=>({route:location.pathname,ready:document.readyState,fonts:document.fonts.status,
                controls:[...document.querySelectorAll('button,summary,[role=button]')].slice(0,300).map(e=>{const r=e.getBoundingClientRect();return {id:e.id,action:e.dataset.action,label:e.getAttribute('aria-label'),text:e.textContent.slice(0,100),disabled:!!e.disabled,rect:{x:r.x,y:r.y,width:r.width,height:r.height}}}),
                navigationAncestors:(()=>{let e=document.querySelector('#ees-work-entry'),values=[];while(e){const r=e.getBoundingClientRect(),s=getComputedStyle(e);values.push({tag:e.tagName,id:e.id,display:s.display,visibility:s.visibility,width:r.width,height:r.height});e=e.parentElement;}return values;})()}))()""")
        except Exception as error:
            report['capture_errors'].append('dom:' + type(error).__name__)
        (directory / (label + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
