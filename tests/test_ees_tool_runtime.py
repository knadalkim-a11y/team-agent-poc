"""Authored shared-tool runtime with real lifecycle/Work SQLite and synthetic I/O."""
import asyncio
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest

import test_ees_tool_lifecycle as lifecycle_fixture
from test_ees_tool_lifecycle import SyntheticNative, workflow, life

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/tools_phase3_contract.json').read_text(encoding='utf-8'))


class RuntimeNative(SyntheticNative):
    def __init__(self):
        super().__init__()
        self.result = deepcopy(FIXTURE['result'])
        self.environment = 'synthetic-environment'
        self.executions = []
        self.before_dispatch = None

    async def inspect(self, user, native_id):
        value = await super().inspect(user, native_id)
        value['environment'] = self.environment
        return value

    async def inspect_execution(self, user, native_id):
        actor, _, groups = await self.service._work_actor(user)
        value = await self.inspect(actor, native_id)
        value['actor_stamp'] = life._digest({'id': actor['id'], 'role': actor['role'], 'groups': sorted(groups)})
        return value

    async def run_execution(self, user, snapshot, inputs, expected_metadata, context, dispatch_guard):
        final = await dispatch_guard()
        if self.before_dispatch:
            self.before_dispatch()
        if await self.inspect_execution(user, snapshot['native_id']) != expected_metadata:
            raise workflow.WorkflowError('tool_trial_snapshot_changed', '합성 변경')
        final()
        if not self.tokens.get(user['id']):
            raise workflow.WorkflowError('native_personal_connection_required', '합성 개인 설정 없음')
        self.executions.append((user['id'], deepcopy(inputs), deepcopy(snapshot), deepcopy(context)))
        self.started.set()
        if self.release:
            await self.release.wait()
        raw = deepcopy(self.result if inputs.get('doc_types', True) else {'documents': []})
        if self.after_run:
            await self.after_run()
        try:
            final = await dispatch_guard()
            latest = await self.inspect_execution(user, snapshot['native_id'])
            final()
            if latest != expected_metadata:
                raise workflow.WorkflowError('tool_trial_snapshot_changed', '합성 변경')
        except workflow.WorkflowError as error:
            return {'status': 'unknown', 'raw_result': None, 'error_code': error.code, 'duration_ms': 10}
        return {'status': self.status, 'raw_result': await self.redact(user, snapshot['native_id'], raw), 'duration_ms': 10}


class ManagedBridge:
    async def managed_tools(self):
        return []

    async def check(self, user, reference):
        raise AssertionError('Authored execution must not enter the managed dispatcher')

    async def invoke(self, *args):
        raise AssertionError('Authored execution must not enter the managed dispatcher')


class AuthoredRuntimeTests(unittest.IsolatedAsyncioTestCase):
    body = lifecycle_fixture.ToolLifecycleTests.body
    call = lifecycle_fixture.ToolLifecycleTests.call
    error = lifecycle_fixture.ToolLifecycleTests.error

    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.users = {key: {'id': key, 'role': 'admin' if key == 'admin' else 'user'} for key in ('admin', 'member', 'other')}
        self.memberships = {key: ['group-ems'] for key in self.users}
        self.service = workflow.WorkflowService(Path(temporary.name) / 'work.db', self.users.get, lambda _: None,
            group_lookup=lambda key: [{'id': group} for group in self.memberships.get(key, [])],
            group_list_lookup=lambda: [{'id': 'group-ems'}, {'id': 'group-fdc'}], native_bridge=ManagedBridge())
        self.native = RuntimeNative()
        self.native.service = self.service
        self.service.tool_drafts.lifecycle.native = self.native
        self.counter = 0
        self.addAsyncCleanup(self.service.operations.stop)
        for key in ('member', 'other'):
            result = await self.core('save_access', principal_kind='user', principal_id=key, system_id='EMS', factory_id='*', roles=['manager', 'participant'])
            self.assertTrue(result['ok'], result)
        self.key = (await self.call('tool_draft_save', draft=FIXTURE['draft'], expected_revision=0))['tool_draft']['id']
        await self.call('tool_draft_connection_save', tool_id=self.key, expected_revision=1, expected_connection_revision=0, **FIXTURE['connection'])
        trial = (await self.call('tool_draft_trial_start', tool_id=self.key, expected_revision=1, expected_connection_revision=1, inputs=FIXTURE['inputs']))['trial']
        await self.call('tool_draft_use_set', tool_id=self.key, trial_id=trial['id'], expected_revision=1, expected_connection_revision=1, expected_use_revision=0,
            groups=FIXTURE['groups'], evidence='합성 문서와 표시 확인')
        self.native.tokens['member'] = 'member-personal-pat'
        self.native.tokens['other'] = 'other-personal-pat'
        self.native.started.clear()

    async def core(self, action, actor='admin', **fields):
        return await self.service.workspace_command(self.users[actor], self.body(action, **{'expected_revision': 0, **fields}))

    async def make_workflow(self, *, fields=None, bindings=None, actor='admin'):
        created = await self.core('create_workflow', actor=actor, system_id='EMS', name='배포 산출물 점검')
        self.assertTrue(created['ok'], created)
        definition = created['workflow']['draft']
        root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['stage']
        definition['nodes']['stage'] = {'id': 'stage', 'type': 't', 'parent': root, 'name': '1차 점검', 'children': ['job'], 'deps': []}
        field = {'id': 'doc_types', 'type': 'multi', 'required': True, 'scope': 'run', 'options': ['design_doc', 'test_result', 'deployment_plan'],
                 'authored_schema': {'type': 'object'}, 'shared_tool_generated': self.key}
        definition['nodes']['job'] = {'id': 'job', 'type': 'j', 'parent': 'stage', 'name': '필수 문서 확인', 'children': [], 'deps': [], 'mode': 'tool',
            'shared_tool_id': self.key, 'argument_bindings': bindings if bindings is not None else {'doc_types': {'input': 'doc_types'}},
            'inputs': fields if fields is not None else [field], 'result_block': 'human_confirm', 'human_confirmation': True}
        saved = await self.core('save_draft', actor=actor, workflow_id=created['workflow_id'], expected_revision=1, definition=definition)
        self.assertTrue(saved['ok'], saved)
        published = await self.core('publish_workflow', actor=actor, workflow_id=created['workflow_id'], expected_revision=2)
        self.assertTrue(published['ok'], published)
        return created['workflow_id']

    async def start(self, wid=None, inputs=None, actor='member'):
        wid = wid or await self.make_workflow()
        response = await self.core('start_run', actor=actor, workflow_id=wid, expected_revision=3, inputs=FIXTURE['inputs'] if inputs is None else inputs)
        self.assertTrue(response['ok'], response)
        return response['run_id']

    def revision(self, run_id):
        with self.service._db() as db:
            return db.execute('SELECT revision FROM work_runs WHERE id=?', (run_id,)).fetchone()[0]

    async def execute(self, run_id, actor='member', body=None):
        return await self.service.operations.command(self.users[actor], body or self.body('execute_job', run_id=run_id, job_id='job', expected_revision=self.revision(run_id)))

    async def decide(self, run_id, result, actor='member'):
        return await self.core('decide', actor=actor, run_id=run_id, job_id='job', expected_revision=self.revision(run_id),
            result_revision=result['attempt']['number'], item_id='job', verdict='completed')

    async def upgrade(self):
        draft = deepcopy(FIXTURE['draft'])
        draft['name'] = '문서 조회 v2'
        draft['input_ui']['doc_types']['question'] = '새 버전에서 어떤 문서를 찾을까요?'
        await self.call('tool_draft_save', tool_id=self.key, expected_revision=1, draft=draft)
        trial = (await self.call('tool_draft_trial_start', tool_id=self.key, expected_revision=2, expected_connection_revision=1, inputs=FIXTURE['inputs']))['trial']
        await self.call('tool_draft_use_set', tool_id=self.key, trial_id=trial['id'], expected_revision=2, expected_connection_revision=1, expected_use_revision=1,
            groups=FIXTURE['groups'], evidence='새 표시 이름 확인')

    async def disable(self):
        await self.call('tool_draft_use_disable', tool_id=self.key, expected_use_revision=1)

    async def test_current_catalog_and_uses_do_not_expose_source_or_personal_settings(self):
        wid = await self.make_workflow()
        self.native.tokens.pop('member')
        catalog = await self.service.shared_tools.list(self.users['member'])
        tool = next(row for row in catalog if row['id'] == self.key)
        self.assertEqual((tool['source'], tool['state'], tool['version'], tool['can_use']), ('authored', 'available', 1, True))
        self.assertEqual({use['definition_state'] for use in tool['uses']}, {'draft', 'published'})
        self.assertTrue(all(use['workflow_id'] == wid and use['system_id'] == 'EMS' and use['stage_id'] == 'stage' for use in tool['uses']))
        encoded = json.dumps(tool)
        for private in ('credential_stamp', 'identity_stamp', 'fixture-phase3-personal-token', 'class Tools', 'native_id'):
            self.assertNotIn(private, encoded)
        self.memberships['member'] = []
        self.assertFalse(any(row['id'] == self.key for row in await self.service.shared_tools.list(self.users['member'])))

    async def test_member_dispatch_frozen_metadata_duplicate_and_whole_job_decision(self):
        run_id = await self.start()
        body = self.body('execute_job', run_id=run_id, job_id='job', expected_revision=1)
        response = await self.execute(run_id, body=body)
        self.assertEqual(response['attempt']['status'], 'succeeded')
        result = response['attempt']['result']
        self.assertEqual([item['row']['id'] for item in result['items']], ['101', '102', '103'])
        self.assertEqual([item['id'] for item in result['items']], ['row-1', 'row-2', 'row-3'])
        self.assertTrue(all(item['required'] is False for item in result['items']))
        self.assertEqual(response['attempt']['snapshot']['shared_tool']['output_ui'], FIXTURE['draft']['output_ui'])
        self.assertEqual(self.native.executions[0][0], 'member')
        self.assertEqual(await self.execute(run_id, body=body), response)
        self.assertEqual(len(self.native.executions), 1)
        decided = await self.decide(run_id, response)
        self.assertTrue(decided['ok'], decided)
        self.assertEqual(decided['run']['jobs']['job']['status'], 'completed')
        other = await self.service.workspace_state(self.users['other'], run_id=run_id)
        attempt = other['run']['attempts'][0]
        self.assertIsNone(attempt['result'])
        self.assertEqual(attempt['inputs'], {})
        self.assertNotIn('arguments', attempt['snapshot'])

    async def test_manual_publication_allows_missing_binding_or_personal_pat(self):
        self.native.tokens.pop('member')
        wid = await self.make_workflow(actor='member', fields=[], bindings={})
        run_id = await self.start(wid, inputs={})
        await self.error('native_personal_connection_required', self.execute(run_id))
        self.assertEqual(self.native.executions, [])
        self.native.tokens['member'] = 'member-personal-pat'
        await self.error('tool_trial_inputs_invalid', self.execute(run_id))
        self.assertEqual(self.native.executions, [])

    async def test_unsaved_draft_changes_preserve_active_code_and_input_ui(self):
        run_id = await self.start()
        changed = deepcopy(FIXTURE['draft'])
        changed['code'] = 'invalid draft code'
        changed['input_ui'] = {}
        await self.call('tool_draft_save', tool_id=self.key, expected_revision=1, draft=changed)
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'succeeded')
        self.assertEqual(self.native.executions[0][2]['draft'], FIXTURE['draft'])
        self.assertEqual(result['attempt']['snapshot']['shared_tool']['input_ui'], FIXTURE['draft']['input_ui'])

    async def test_upgrade_requires_acceptance_and_preserves_previous_attempt(self):
        run_id = await self.start()
        first = await self.execute(run_id)
        await self.upgrade()
        await self.error('shared_tool_version_changed', self.execute(run_id))
        state = await self.service.workspace_state(self.users['member'], run_id=run_id)
        self.assertEqual(state['run']['attempts'][0]['result'], first['attempt']['result'])
        accepted = await self.call('shared_tool_accept_version', actor='member', run_id=run_id, shared_tool_id=self.key, version=2, expected_revision=self.revision(run_id))
        self.assertTrue(accepted['ok'])
        second = await self.execute(run_id)
        self.assertEqual(second['attempt']['snapshot']['shared_tool']['version'], 2)
        with self.service._db() as db:
            old = json.loads(db.execute('SELECT snapshot FROM work_attempts WHERE id=?', (first['attempt']['id'],)).fetchone()[0])
        self.assertEqual(old['shared_tool']['version'], 1)
        self.assertEqual(old['shared_tool']['name'], FIXTURE['draft']['name'])

    async def test_empty_and_partial_are_explicit_human_decisions(self):
        run_id = await self.start(inputs={'doc_types': []})
        result = await self.execute(run_id)
        self.assertEqual((result['attempt']['result']['completeness'], result['attempt']['result']['count']), ('empty', 0))
        decided = await self.decide(run_id, result)
        self.assertTrue(decided['ok'], decided)
        self.assertEqual(decided['run']['jobs']['job']['status'], 'completed')
        run_id = await self.start()
        self.native.result['partial'] = True
        result = await self.execute(run_id)
        self.assertEqual((result['attempt']['status'], result['attempt']['result']['completeness']), ('partial', 'partial'))
        decided = await self.decide(run_id, result)
        self.assertTrue(decided['ok'], decided)
        self.assertEqual(decided['run']['jobs']['job']['status'], 'partial')
        with self.service._db() as db:
            run = db.execute('SELECT * FROM work_runs WHERE id=?', (run_id,)).fetchone()
            job = db.execute('SELECT * FROM work_jobs WHERE run_id=?', (run_id,)).fetchone()
            self.assertTrue(self.service._work_partial_confirmed(db, run, job))

    async def test_invalid_mapping_and_unknown_never_complete(self):
        run_id = await self.start()
        self.native.result = {'documents': [{'id': 'same', 'title': 'missing fields'}]}
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'failed')
        decided = await self.decide(run_id, result)
        self.assertEqual(decided['error']['code'], 'result_unconfirmed')
        self.native.status = 'unknown'
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'unknown')
        self.assertIsNone(result['attempt']['result']['raw_result'])
        self.assertEqual(len(self.native.executions), 2)

    async def test_disable_during_io_discards_late_result_but_keeps_attempt(self):
        run_id = await self.start()
        self.native.after_run = self.disable
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'unknown')
        self.assertIsNone(result['attempt']['result']['raw_result'])
        self.assertEqual(len(self.native.executions), 1)
        await self.error('shared_tool_disabled', self.execute(run_id))

    async def test_inputs_changed_during_io_discard_late_result(self):
        run_id = await self.start()
        async def changed():
            saved = await self.core('save_inputs', actor='member', run_id=run_id, expected_revision=self.revision(run_id), inputs={'doc_types': []})
            self.assertTrue(saved['ok'], saved)
        self.native.after_run = changed
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'unknown')
        self.assertIsNone(result['attempt']['result']['raw_result'])
        self.assertEqual(result['attempt']['inputs'], FIXTURE['inputs'])

    async def test_disabled_history_visible_until_current_permission_revoked(self):
        run_id = await self.start()
        first = await self.execute(run_id)
        await self.disable()
        state = await self.service.workspace_state(self.users['member'], run_id=run_id)
        self.assertEqual(state['run']['attempts'][0]['result'], first['attempt']['result'])
        self.native.available = False
        state = await self.service.workspace_state(self.users['member'], run_id=run_id)
        self.assertIsNone(state['run']['attempts'][0]['result'])

    async def test_environment_requires_reapproval_and_foreign_reference_never_dispatches(self):
        run_id = await self.start()
        self.native.environment = 'changed-worker-bytes'
        await self.error('shared_tool_review_required', self.execute(run_id))
        self.assertEqual(self.native.executions, [])
        self.native.environment = 'synthetic-environment'
        with self.service._db() as db:
            pin = json.loads(db.execute('SELECT data FROM work_shared_tool_pins').fetchone()[0])
        pin['reference']['snapshot_hash'] = 'forged'
        await self.error('shared_tool_plan_changed', self.service.shared_tools.authored.invoke(self.users['member'], pin['reference'], FIXTURE['inputs'],
            {'run_id': run_id, 'job_id': 'job', 'call_id': 'none', 'shared_run_kind': 'work'}))
        self.assertEqual(self.native.executions, [])

    async def test_duplicate_in_flight_uses_one_worker_and_blocks_version_acceptance(self):
        run_id = await self.start()
        self.native.release = asyncio.Event()
        body = self.body('execute_job', run_id=run_id, job_id='job', expected_revision=1)
        task = asyncio.create_task(self.execute(run_id, body=body))
        await self.native.started.wait()
        duplicate = await self.execute(run_id, body=body)
        self.assertEqual(duplicate['attempt']['status'], 'running')
        await self.error('execution_running', self.call('shared_tool_accept_version', actor='member', run_id=run_id, shared_tool_id=self.key, version=1, expected_revision=self.revision(run_id)))
        self.native.release.set()
        result = await task
        self.assertEqual(result['attempt']['status'], 'succeeded')
        self.assertEqual(len(self.native.executions), 1)


    async def test_typed_nullable_list_and_defaults_use_canonical_version_schema(self):
        draft = deepcopy(FIXTURE['draft'])
        draft['code'] = draft['code'].replace('from typing import List, Literal', 'from typing import List, Literal, Optional').replace(
            'doc_types: List[DocType], __user__: dict',
            'doc_types: List[DocType], nullable: Optional[str], flag: Literal[True, False], count: int, ratio: float, numbers: List[int], nested: List[List[bool]], blank: str, __user__: dict, optional: Optional[str] = "code-default"')
        kinds = {'nullable': 'text', 'flag': 'select', 'count': 'number', 'ratio': 'number', 'numbers': 'multiselect', 'nested': 'multiselect', 'blank': 'text', 'optional': 'text'}
        for name, widget in kinds.items():
            draft['input_ui'][name] = {'label': name, 'question': name, 'widget': widget, 'option_labels': {'true': '예', 'false': '아니오'} if name == 'flag' else {}}
        await self.call('tool_draft_save', tool_id=self.key, expected_revision=1, draft=draft)
        inputs = {**FIXTURE['inputs'], 'nullable': None, 'flag': False, 'count': 0, 'ratio': 1.25, 'numbers': [2, 2, 1], 'nested': [[False, True], []], 'blank': ''}
        trial = (await self.call('tool_draft_trial_start', tool_id=self.key, expected_revision=2, expected_connection_revision=1, inputs=inputs))['trial']
        self.assertEqual(trial['status'], 'succeeded', trial)
        await self.call('tool_draft_use_set', tool_id=self.key, trial_id=trial['id'], expected_revision=2, expected_connection_revision=1, expected_use_revision=1,
            groups=FIXTURE['groups'], evidence='여러 형식 확인')
        fields = [{'id': key, 'type': {'flag': 'single', 'count': 'number', 'ratio': 'number', 'numbers': 'list', 'nested': 'list', 'doc_types': 'multi'}.get(key, 'text'),
                   'scope': 'run', 'required': True, 'options': [True, False] if key == 'flag' else [], 'authored_schema': {'type': 'string'}} for key in [*inputs, 'optional']]
        wid = await self.make_workflow(fields=fields, bindings={key: {'input': key} for key in [*inputs, 'optional']})
        run_id = await self.start(wid, inputs=inputs)
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'succeeded', result)
        self.assertEqual(self.native.executions[-1][1], {**inputs, 'optional': 'code-default'})
        self.assertEqual(result['attempt']['snapshot']['effective_arguments'], self.native.executions[-1][1])
        self.assertNotIn('optional', result['attempt']['snapshot']['arguments'])
        inputs['optional'] = None
        saved = await self.core('save_inputs', actor='member', run_id=run_id, expected_revision=self.revision(run_id), inputs=inputs)
        self.assertTrue(saved['ok'], saved)
        result = await self.execute(run_id)
        self.assertIsNone(self.native.executions[-1][1]['optional'])
        for key, bad in [('flag', 0), ('count', 1.5), ('numbers', ['2']), ('nested', [[1]])]:
            changed = {**inputs, key: bad}
            saved = await self.core('save_inputs', actor='member', run_id=run_id, expected_revision=self.revision(run_id), inputs=changed)
            self.assertEqual(saved['error']['code'], 'invalid_inputs', (key, saved))
        absent = {key: value for key, value in inputs.items() if key != 'nullable'}
        saved = await self.core('save_inputs', actor='member', run_id=run_id, expected_revision=self.revision(run_id), inputs=absent)
        self.assertTrue(saved['ok'], saved)
        await self.error('argument_input_missing', self.execute(run_id))
        self.assertEqual(len(self.native.executions), 2)

    async def test_actor_group_and_native_acl_revocation_no_replay_leak(self):
        run_id = await self.start()
        body = self.body('execute_job', run_id=run_id, job_id='job', expected_revision=1)
        await self.execute(run_id, body=body)
        self.memberships['member'] = []
        await self.error('shared_tool_forbidden', self.execute(run_id, body=body))
        self.memberships['member'] = ['group-ems']
        self.native.available = False
        await self.error('native_access_denied', self.execute(run_id, body=body))
        self.assertEqual(len(self.native.executions), 1)

    async def test_work_scope_revoked_during_io_persists_only_unknown(self):
        run_id = await self.start()
        async def revoke():
            with self.service._db(write=True) as db:
                db.execute("UPDATE work_access SET active=0 WHERE principal_id='member'")
        self.native.after_run = revoke
        body = self.body('execute_job', run_id=run_id, job_id='job', expected_revision=1)
        await self.error('scope_forbidden', self.execute(run_id, body=body))
        with self.service._db() as db:
            attempt = db.execute('SELECT * FROM work_attempts WHERE run_id=?', (run_id,)).fetchone()
        self.assertEqual(attempt['status'], 'unknown')
        self.assertIsNone(json.loads(attempt['result'])['raw_result'])
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_access SET active=1 WHERE principal_id='member'")
        replay = await self.execute(run_id, body=body)
        self.assertEqual(replay['attempt']['status'], 'unknown')
        self.assertIsNone(replay['attempt']['result']['raw_result'])
        self.assertEqual(len(self.native.executions), 1)

    async def test_secret_values_in_worker_output_are_redacted(self):
        run_id = await self.start()
        self.native.result['documents'][0]['title'] = 'member-personal-pat'
        result = await self.execute(run_id)
        self.assertNotIn('member-personal-pat', json.dumps(result))
        with self.service._db() as db:
            self.assertNotIn('member-personal-pat', db.execute('SELECT result FROM work_attempts').fetchone()[0])



    async def legacy_run(self):
        from workflow_fixture import historical_facade, load_workflow_examples, arrange_legacy_catalog
        from test_ees_workflow_execution import publish, REFERENCES
        import importlib
        legacy = historical_facade('ees_lifecycle_tests').WorkflowService(self.service.database, self.users.get, lambda _: None, native_bridge=ManagedBridge())
        arrange_legacy_catalog(legacy)
        legacy.tool_drafts = self.service.tool_drafts
        legacy._work_actor = self.service._work_actor
        legacy.shared_tools = importlib.import_module('ees_lifecycle_tests.ees_workflow_shared_tools').SharedTools(legacy)
        self.addAsyncCleanup(legacy.execution.stop)
        fragment = load_workflow_examples('ees_lifecycle_tests').installation_docs_workflow(REFERENCES)
        call = fragment['nodes']['new-documents-search-j']['execution']['calls'][0]
        call.pop('reference')
        call.update(shared_tool_id=self.key, arguments={'doc_types': {'source': 'constant', 'value': FIXTURE['inputs']['doc_types']}})
        process = publish(legacy, fragment)
        with legacy._db() as db:
            version = legacy._catalog(db)[0]['version']
        plan = await legacy.execution_plan(self.users['member'], {'node_id': 'new-documents-search-j', 'inputs': {'query': 'guide', 'space_key': 'EMS'},
            'scope': {'site_id': 'us-a', 'system': 'EMS', 'process_id': process, 'version': version}})
        self.assertTrue(plan['ok'], plan)
        started = await legacy.execution_action(self.users['member'], {'action': 'start', 'plan_id': plan['plan']['id'], 'plan_hash': plan['plan']['hash'], 'request_id': 'authored-legacy-start'})
        self.assertTrue(started['ok'], started)
        return legacy, started['run']['id']

    async def test_existing_execution_calls_dispatch_and_historical_evidence(self):
        legacy, run_id = await self.legacy_run()
        for _ in range(4):
            await legacy.execution.process_once()
        state = await legacy.execution_state(self.users['member'], run_id=run_id)
        self.assertTrue(state['ok'], state)
        call = state['run']['calls'][0]
        self.assertEqual(call['result']['source'], 'authored')
        self.assertEqual(call['result']['count'], 3)
        self.assertEqual(call['effective_arguments'], FIXTURE['inputs'])
        self.assertEqual(call['shared_tool']['source'], 'authored')
        self.assertEqual(call['shared_tool']['output_ui'], FIXTURE['draft']['output_ui'])
        self.assertEqual(self.native.executions[0][0], 'member')
        await self.disable()
        state = await legacy.execution_state(self.users['member'], run_id=run_id)
        self.assertEqual(state['run']['calls'][0]['result'], call['result'])
        self.native.available = False
        state = await legacy.execution_state(self.users['member'], run_id=run_id)
        self.assertFalse(state['run']['evidence_available'])
        self.assertNotIn('result', state['run']['calls'][0])
        self.assertNotIn('effective_arguments', state['run']['calls'][0])

    async def test_existing_execution_calls_partial_preserves_evidence_without_success(self):
        legacy, run_id = await self.legacy_run()
        self.native.result['partial'] = True
        for _ in range(4):
            await legacy.execution.process_once()
        state = await legacy.execution_state(self.users['member'], run_id=run_id)
        self.assertTrue(state['ok'], state)
        call = state['run']['calls'][0]
        self.assertEqual((call['result']['status'], call['result']['completeness'], call['result']['count']), ('partial', 'partial', 3))
        self.assertNotEqual(state['run']['status'], 'succeeded')
        self.assertEqual(len(self.native.executions), 1)

    async def test_pat_rotation_during_heartbeat_cleanup_discards_result(self):
        run_id = await self.start()
        entered = asyncio.Event()
        original = self.service.operations._heartbeat
        async def heartbeat(*args):
            entered.set()
            try:
                await original(*args)
            finally:
                self.native.generations['member'] = self.native.generations.get('member', 0) + 1
                self.native.tokens['member'] = 'rotated-member-pat'
        self.service.operations._heartbeat = heartbeat
        self.native.release = asyncio.Event()
        task = asyncio.create_task(self.execute(run_id))
        await entered.wait()
        self.native.release.set()
        result = await task
        self.assertEqual(result['attempt']['status'], 'unknown')
        self.assertIsNone(result['attempt']['result']['raw_result'])
        with self.service._db() as db:
            saved = db.execute('SELECT status,result FROM work_attempts').fetchone()
        self.assertEqual(saved['status'], 'unknown')
        self.assertIsNone(json.loads(saved['result'])['raw_result'])



    async def test_role_and_membership_changes_between_work_gate_and_native_read_block_dispatch(self):
        run_id = await self.start(actor='admin')
        for change in ('role', 'groups'):
            self.users['admin'] = {'id': 'admin', 'role': 'admin'}
            self.memberships['admin'] = ['group-ems']
            def revoke():
                if change == 'role':
                    self.users['admin'] = {'id': 'admin', 'role': 'user'}
                else:
                    self.memberships['admin'] = []
            self.native.before_dispatch = revoke
            try:
                response = await self.execute(run_id, actor='admin')
            except workflow.WorkflowError as error:
                self.assertIn(error.code, {'scope_forbidden', 'shared_tool_forbidden'})
            else:
                self.assertEqual(response['attempt']['status'], 'blocked', response)
            self.assertEqual(self.native.executions, [])
        self.users['admin'] = {'id': 'admin', 'role': 'admin'}
        self.memberships['admin'] = ['group-ems']



    async def test_final_work_cas_is_inside_the_result_write_transaction(self):
        run_id = await self.start()
        armed = False
        original = self.service._db
        async def after_run():
            nonlocal armed
            armed = True
        @contextmanager
        def database(write=False):
            nonlocal armed
            with original(write=write) as db:
                if armed and write:
                    armed = False
                    saved = json.loads(db.execute('SELECT data FROM work_tool_uses WHERE tool_id=?', (self.key,)).fetchone()[0])
                    saved['state'] = 'disabled'
                    db.execute('UPDATE work_tool_uses SET data=? WHERE tool_id=?', (life._json(saved), self.key))
                yield db
        self.service._db = database
        self.native.after_run = after_run
        result = await self.execute(run_id)
        self.assertEqual(result['attempt']['status'], 'unknown')
        self.assertIsNone(result['attempt']['result']['raw_result'])
        with self.service._db() as db:
            saved = db.execute('SELECT status,result FROM work_attempts').fetchone()
        self.assertEqual(saved['status'], 'unknown')
        self.assertIsNone(json.loads(saved['result'])['raw_result'])


if __name__ == '__main__':
    unittest.main()
