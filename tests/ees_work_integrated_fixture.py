"""Built Native browser + real integrated workflow SQLite fixture.

Native authentication/chat/model HTTP responses here are synthetic. The separate
Native account fixture and complete CLI app gate exercise real authentication.
Procedures are authored through the production command service, never seeded.
"""
import asyncio
import base64
from copy import deepcopy
import hashlib
import importlib
import inspect
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


class SyntheticAuthoredNative:
    """Synthetic Native settings and worker boundary for real lifecycle tests.

    HTTP, SQLite trial records, eligibility and versions remain production code.
    This adapter never executes authored source, starts a worker, encrypts real
    credentials or calls an external service. Native/worker tests cover those
    boundaries separately. Only metadata and redacted copies leave the adapter.
    Set failures[method] to an error code (or exception) to reject an operation;
    hold/started and run_calls expose deterministic in-flight request evidence.
    """
    def __init__(self, error_type=RuntimeError, *, result=None):
        self.error_type = error_type
        self.identities = {}
        self._tokens = {}
        self._credential_revisions = {}
        self.failures = {}
        self.inspect_error = None
        self.save_error = None
        self.groups_error = None
        self.allowed = True
        self.denied_users = set()
        self.environment = 'synthetic-native-0.11.3'
        self.run_calls = []
        self.execution_calls = []
        self.execution_actor_lookup = None
        self.save_calls = []
        self.group_calls = []
        self.started = threading.Event()
        self.hold = threading.Event(); self.hold.set()
        self.hold_timeout = 30
        if result is None:
            fixture = json.loads((ROOT / 'tests/fixtures/tools_phase2_contract.json').read_text(encoding='utf-8'))
            result = {'status': 'succeeded', 'raw_result': fixture['result'], 'duration_ms': 25}
        self.result = deepcopy(result)

    @property
    def tokens(self):
        """Private synthetic storage evidence; never included in API results."""
        return deepcopy(self._tokens)

    @staticmethod
    def _value(user, key, default=''):
        return user.get(key, default) if isinstance(user, dict) else getattr(user, key, default)

    def _fail(self, code):
        raise self.error_type(code, '합성 Native 연결을 확인해 주세요.')

    def _check(self, method, user):
        failure = self.failures.get(method)
        if failure is None:
            attribute = {'inspect': 'inspect_error', 'save_connection': 'save_error', 'set_groups': 'groups_error'}.get(method)
            failure = getattr(self, attribute, None) if attribute else None
        if isinstance(failure, BaseException):
            raise failure
        if failure:
            self._fail(failure)
        if self._value(user, 'role') != 'admin':
            self._fail('admin_required')
        if not self.allowed or self._value(user, 'id') in self.denied_users:
            self._fail('native_access_denied')

    def _metadata(self, user, native_id):
        identity = self.identities.get(native_id)
        if identity is None:
            self._fail('tool_connection_identity_unavailable')
        key = (native_id, self._value(user, 'id'))
        return {'native_id': native_id, 'token_set': bool(self._tokens.get(key)),
                'credential_stamp': 'synthetic-credential-' + key[1] + '-' + str(self._credential_revisions.get(key, 0)),
                'identity_stamp': 'synthetic-identity-' + str(identity['revision']),
                'environment': self.environment, 'groups': deepcopy(identity['groups'])}

    async def inspect(self, user, native_id):
        self._check('inspect', user)
        return deepcopy(self._metadata(user, native_id))

    async def save_connection(self, user, tool_id, native_id, token):
        self._check('save_connection', user)
        token = '' if token is None else token
        if not isinstance(token, str) or len(token) > 16000 or any(ord(char) < 32 for char in token):
            self._fail('tool_connection_token_invalid')
        if native_id:
            identity = self.identities.get(native_id)
            if identity is None:
                self._fail('tool_connection_identity_unavailable')
            if identity['tool_id'] != tool_id:
                self._fail('tool_connection_identity_changed')
        else:
            native_id = 'fixture-authored-' + tool_id
            self.identities.setdefault(native_id, {'tool_id': tool_id, 'revision': 1, 'groups': []})
        key = (native_id, self._value(user, 'id'))
        if token:
            self._tokens[key] = token
            self._credential_revisions[key] = self._credential_revisions.get(key, 0) + 1
        self.save_calls.append({'actor': key[1], 'tool_id': tool_id, 'native_id': native_id, 'token_supplied': bool(token)})
        return deepcopy(self._metadata(user, native_id))

    async def set_groups(self, user, native_id, groups, expected_stamp):
        self._check('set_groups', user)
        current = self._metadata(user, native_id)
        if current['identity_stamp'] != expected_stamp:
            self._fail('tool_connection_conflict')
        if not isinstance(groups, list) or any(not isinstance(group, str) or not group for group in groups) or len(set(groups)) != len(groups):
            self._fail('tool_draft_invalid')
        identity = self.identities[native_id]
        updated = sorted(groups)
        if updated != identity['groups']:
            identity['groups'] = updated
            identity['revision'] += 1
        self.group_calls.append({'actor': self._value(user, 'id'), 'native_id': native_id, 'groups': deepcopy(updated)})
        return deepcopy(self._metadata(user, native_id))

    async def redact(self, user, native_id, value):
        self._check('redact', user)
        self._metadata(user, native_id)
        token = self._tokens.get((native_id, self._value(user, 'id')), '')

        def clean(item):
            if isinstance(item, str):
                return item.replace(token, '[REDACTED]') if token else item
            if isinstance(item, list):
                return [clean(child) for child in item]
            if isinstance(item, dict):
                return {clean(key): clean(child) for key, child in item.items()}
            return deepcopy(item)

        return clean(value)

    async def run(self, user, native_id, code, function, base_url, inputs, expected_metadata):
        self._check('run', user)
        metadata = await self.inspect(user, native_id)
        if metadata != expected_metadata:
            self._fail('tool_trial_snapshot_changed')
        if not metadata['token_set']:
            self._fail('native_personal_connection_required')
        self.run_calls.append({'actor': self._value(user, 'id'), 'native_id': native_id,
                               'code': code, 'function': function, 'base_url': base_url,
                               'inputs': deepcopy(inputs), 'expected_metadata': deepcopy(expected_metadata)})
        result = deepcopy(self.result)
        self.started.set()
        if not await asyncio.to_thread(self.hold.wait, self.hold_timeout):
            result = {'status': 'unknown', 'raw_result': None, 'duration_ms': int(self.hold_timeout * 1000),
                      'error_code': 'tool_trial_timeout'}
        self._check('run', user)
        if await self.inspect(user, native_id) != metadata:
            return {'status': 'unknown', 'raw_result': None, 'duration_ms': result.get('duration_ms', 0),
                    'error_code': 'tool_trial_snapshot_changed'}
        result['raw_result'] = await self.redact(user, native_id, result.get('raw_result'))
        return deepcopy(result)

    def set_personal_token(self, user, native_id, token):
        """Only synthetic Native personal settings; never a Work credential API."""
        key = (native_id, self._value(user, 'id'))
        self._tokens[key] = token
        self._credential_revisions[key] = self._credential_revisions.get(key, 0) + 1

    def _execution_check(self, user):
        if self._value(user, 'role') not in ('admin', 'user'):
            self._fail('native_access_denied')
        if not self.allowed or self._value(user, 'id') in self.denied_users:
            self._fail('native_access_denied')
        failure = self.failures.get('inspect_execution')
        if failure:
            self._fail(failure)

    async def inspect_execution(self, user, native_id):
        self._execution_check(user)
        actor, groups = user, []
        if self.execution_actor_lookup:
            actor, _, groups = await self.execution_actor_lookup(user)
        self._execution_check(actor)
        metadata = deepcopy(self._metadata(actor, native_id))
        metadata['actor_stamp'] = hashlib.sha256(json.dumps([
            self._value(actor, 'id'), self._value(actor, 'role'), sorted(groups)
        ], sort_keys=True).encode('utf-8')).hexdigest()
        return metadata

    async def run_execution(self, user, snapshot, inputs, expected_metadata, context, dispatch_guard):
        native_id = snapshot['native_id']
        metadata = await self.inspect_execution(user, native_id)
        if metadata != expected_metadata:
            self._fail('tool_trial_snapshot_changed')
        if not metadata['token_set']:
            self._fail('native_personal_connection_required')
        final_guard = await dispatch_guard()
        if await self.inspect_execution(user, native_id) != expected_metadata:
            self._fail('tool_trial_snapshot_changed')
        def finish_guard(guard):
            if not callable(guard):
                self._fail('tool_trial_snapshot_changed')
            checked = guard()
            if inspect.isawaitable(checked):
                if hasattr(checked, 'close'):
                    checked.close()
                self._fail('tool_trial_snapshot_changed')
        finish_guard(final_guard)
        self.execution_calls.append({'actor': self._value(user, 'id'),
            'snapshot': deepcopy(snapshot), 'inputs': deepcopy(inputs),
            'context': deepcopy(context), 'metadata': deepcopy(metadata)})
        result = deepcopy(self.result)
        self.started.set()
        if not await asyncio.to_thread(self.hold.wait, self.hold_timeout):
            result = {'status': 'unknown', 'raw_result': None,
                      'duration_ms': int(self.hold_timeout * 1000), 'error_code': 'tool_trial_timeout'}
        try:
            final_guard = await dispatch_guard()
            current = await self.inspect_execution(user, native_id)
            finish_guard(final_guard)
            if current != metadata:
                self._fail('tool_trial_snapshot_changed')
        except self.error_type as error:
            return {'status': 'unknown', 'raw_result': None,
                    'duration_ms': result.get('duration_ms', 0), 'error_code': error.code}
        token = self._tokens.get((native_id, self._value(user, 'id')), '')
        def clean(value):
            if isinstance(value, str):
                return value.replace(token, '[REDACTED]') if token else value
            if isinstance(value, list):
                return [clean(child) for child in value]
            if isinstance(value, dict):
                return {clean(key): clean(child) for key, child in value.items()}
            return deepcopy(value)
        result['raw_result'] = clean(result.get('raw_result'))
        return result


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
        self.browser = ChromePipe(self.chrome, str(Path(self.temporary.name) / 'chrome'),
                                  hide_scrollbars=getattr(self, 'hide_scrollbars', True))
        self.addCleanup(self.close_browser)
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
        # A responsive collapse can still be wider than 200px mid-transition.
        # Require the source sidebar's expanded target before trusting geometry.
        opened = "(()=>{const e=document.querySelector('#sidebar'),r=e?.getBoundingClientRect();return !!e&&(e.hasAttribute('data-ees-source-sidebar')?e.dataset.compact==='false':e.getAttribute('aria-hidden')==='false')&&!e.inert&&r.width>200&&r.x>=0&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+50));})()"
        self.wait(opened + " || !!document.querySelector('[data-ees-sidebar-toggle],button[aria-label=\"사이드바 열기\"]')")
        if not self.browser.evaluate(opened):
            selector = '[data-ees-sidebar-toggle]' if self.browser.evaluate("!!document.querySelector('[data-ees-sidebar-toggle]')") else 'button[aria-label="사이드바 열기"]'
            self.click(selector)
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

    def phase3_command(self, action, revision=0, *, user=None, **values):
        result = asyncio.run(self.server.workflow.operations.command(user or self.server.user,
            dict(action=action, expected_revision=revision, request_id=str(uuid4()), **values)))
        self.assertTrue(result['ok'], result)
        return result

    def phase3_authored_tool(self, *, activate=True):
        """Real draft/lifecycle commands; only Native settings/worker are synthetic."""
        fixture = json.loads((ROOT / 'tests/fixtures/tools_phase3_contract.json').read_text(encoding='utf-8'))
        self.phase3_admin = self.server.user
        self.authored_native = SyntheticAuthoredNative(self.backend.WorkflowError,
            result={'status': 'succeeded', 'raw_result': fixture['result'], 'duration_ms': 25})
        self.server.workflow.tool_drafts.lifecycle.native = self.authored_native
        self.authored_native.execution_actor_lookup = self.server.workflow._work_actor
        self.addCleanup(self.authored_native.hold.set)
        self.authored_members = {'group-ems': {self.server.user['id'], 'other-user'},
                                'group-apc': {self.server.user['id']}}
        groups = [{'id': 'group-ems', 'name': 'EMS 운영'}, {'id': 'group-apc', 'name': 'APC 운영'}]
        self.server.workflow.group_lookup = lambda actor: [deepcopy(group) for group in groups
            if (actor if isinstance(actor, str) else SyntheticAuthoredNative._value(actor, 'id')) in self.authored_members[group['id']]]
        self.server.workflow.group_list_lookup = lambda: deepcopy(groups)
        record = self.phase3_command('tool_draft_save', draft=fixture['draft'])['tool_draft']
        key = record['id']
        self.assertTrue(record['check']['valid'], record['check'])
        record = self.phase3_command('tool_draft_connection_save', record['revision'],
            tool_id=key, expected_connection_revision=0, **fixture['connection'])['tool_draft']
        self.authored_native.set_personal_token(self.users['other-user'], record['connection']['native_id'],
                                               'fixture-phase3-other-personal-token')
        if activate:
            record = self.phase3_activate(fixture, key)
        return fixture, key, record

    def phase3_activate(self, fixture, key):
        record = self.phase3_command('tool_draft_get', user=self.phase3_admin, tool_id=key)['tool_draft']
        self.phase3_command('tool_draft_trial_start', record['revision'], user=self.phase3_admin, tool_id=key,
            expected_connection_revision=record['connection']['revision'], inputs=fixture['inputs'])
        tested = self.phase3_command('tool_draft_get', user=self.phase3_admin, tool_id=key)['tool_draft']
        self.assertTrue(tested['trial']['eligible_for_activation'], tested['trial'])
        return self.phase3_command('tool_draft_use_set', tested['revision'], user=self.phase3_admin, tool_id=key,
            expected_connection_revision=tested['connection']['revision'],
            expected_use_revision=tested['use']['revision'], trial_id=tested['trial']['id'],
            groups=fixture['groups'], evidence=fixture['evidence'])['tool_draft']

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

    def add_stage_ui(self, name):
        self.click('[data-author-action=add_stage]')
        self.wait("document.querySelector('#ew-stage-editor [name=name]')")
        self.fill('#ew-stage-editor [name=name]', name)
        self.click('[data-author-action=inline_apply]')
        self.wait("!document.querySelector('#ew-stage-editor') && document.querySelector('[data-author-action=add_job]')")

    def add_job_ui(self, name):
        self.click('[data-author-action=add_job]')
        self.wait("document.querySelector('#ew-stage-editor [name=name]')")
        self.fill('#ew-stage-editor [name=name]', name)
        self.click('[data-author-action=inline_apply]')
        self.wait("document.querySelector('#ew-author-node [name=job_guidance]')")

    def open_author_job_ui(self, job_id, stage_id='stage'):
        selector = '[data-author-action=node][data-id="' + job_id + '"]'
        if not self.browser.evaluate('!!document.querySelector(' + json.dumps(selector) + ')'):
            self.click('[data-author-action=stage_toggle][data-id="' + stage_id + '"]')
        self.click(selector)
        # The always-visible name and method identify a ready job detail.
        # Job guidance is now direct; hidden legacy settings remain preserved.
        self.wait("document.querySelector('.ew-job-detail #ew-author-node [name=name]') && document.querySelector('.ew-job-method [name=mode]:checked')")

    def start(self, key, **values):
        revision = self.state(workflow_id=key)['workflow']['revision']
        return self.command('start_run', workflow_id=key, expected_revision=revision, **values)['run']

    def open_run(self, key, run, job='job-0'):
        self.open_sidebar()
        # Existing runs are opened through the actual execution-record list.
        # A new workflow overview no longer embeds the removed active/start UI.
        self.click('[data-action="records"]')
        run_control = '#ees-work-panel [data-action="open_run"][data-run-id="' + run['id'] + '"][data-workflow-id="' + key + '"]'
        self.wait('document.querySelector(' + json.dumps(run_control) + ')')
        self.click(run_control)
        self.wait('window.__eesNativeWorkV1.captureReference()?.run_id === ' + json.dumps(run['id']) +
            ' && document.querySelector("#ees-work-panel .ew-vd-head,#ees-work-panel .ew-operation-overview")')
        if job:
            selector = '#ees-work-panel [data-action="job"][data-job-id="' + job + '"]'
            if not self.browser.evaluate('!!document.querySelector(' + json.dumps(selector) + ')'):
                if self.browser.evaluate("!!document.querySelector('.ew-operation-overview')"):
                    self.click('.ew-operation-stage[data-action=stage_open]')
                    self.wait("document.querySelector('#ees-work-panel .ew-run-nav [data-action=stage_details]')")
                self.click('[data-action=stage_details]')
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

    def open_workspace_assets(self):
        # The compact sidebar opens the assets group through its visible heading.
        if self.read('.ew-assets-toggle', 'getAttribute("aria-expanded")') == 'false':
            self.click('.ew-assets-toggle')
        self.wait("document.querySelector('#ees-assets-items')?.inert === false")

    def key(self, key, code, modifiers=0):
        for kind in ('keyDown', 'keyUp'):
            event = {'type': kind, 'key': key, 'code': key,
                'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code, 'modifiers': modifiers}
            # Chromium activates native buttons on Enter's keypress character.
            # A key code without text omits that event in the CDP transport.
            if kind == 'keyDown' and key == 'Enter' and not modifiers:
                event.update(text='\r', unmodifiedText='\r')
            self.browser.call('Input.dispatchKeyEvent', event)

    def fill(self, selector, value):
        self.click(selector); self.key('a', 65, 2)
        self.browser.call('Input.insertText', {'text': value}); self.key('Tab', 9)

    def choose(self, selector, value):
        index = self.browser.evaluate('[...document.querySelector(' + json.dumps(selector) + ').options].findIndex(o=>o.value===' + json.dumps(value) + ')')
        self.assertGreaterEqual(index, 0); self.click(selector); self.key('Home', 36)
        for _ in range(index): self.key('ArrowDown', 40)
        self.key('Enter', 13)

    def create_legacy_tool(self, system='EMS'):
        self.wait("document.querySelector('[data-author-action=tool_create]')")
        if self.browser.evaluate("!!document.querySelector('.ew-draft-legacy:not([open])')"):
            self.click('.ew-draft-legacy > summary')
        self.click('[data-author-action=tool_create]')
        self.wait("document.querySelector('#ees-work-dialog [name=system_id]')")
        self.choose('#ees-work-dialog [name=system_id]', system)
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')?.open && document.querySelector('[data-author-action=tool_example]') && !document.querySelector('#ew-tool-search')?.disabled")

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
        self.failure_evidence_path = directory / (label + '.json')
        report = {'test': self.id(), 'last_wait': getattr(self, 'last_wait', None),
                  'last_click': getattr(self, 'last_click', None), 'capture_errors': []}
        # A bootstrap failure has no page session. Preserve the original local
        # process/transport snapshot before cleanup instead of sending page CDP
        # commands that only obscure it with further protocol failures.
        report['browser'] = self.browser.diagnostics()
        if not self.browser.session:
            report['page_capture'] = 'unavailable_no_attached_session'
            (directory / (label + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return
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

    def close_browser(self):
        try:
            self.browser.close()
        finally:
            # capture_failure runs first, including when setUp never obtained a
            # page session. Keep its bytes untouched and save cleanup's passive
            # observation/final state beside it instead of losing late replies.
            path = getattr(self, 'failure_evidence_path', None)
            if path and hasattr(self.browser, 'final_diagnostics'):
                temporary = None
                try:
                    if path.exists():
                        report = {'initial_evidence': path.name,
                                  'browser_cleanup_diagnostics': self.browser.final_diagnostics}
                        target = path.with_name(path.stem + '-cleanup.json')
                        content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
                        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=target.name + '.', suffix='.tmp',
                                mode='w', encoding='utf-8', delete=False) as stream:
                            temporary = Path(stream.name)
                            stream.write(content)
                        os.replace(temporary, target)
                except (OSError, ValueError, TypeError) as error:
                    # Do not replace the original test/close exception with a
                    # secondary collection error; expose the missing evidence.
                    print('Native browser cleanup evidence save failed: ' + type(error).__name__, file=sys.stderr)
                finally:
                    if temporary:
                        try: temporary.unlink(missing_ok=True)
                        except OSError: pass
