"""Native model Tool -> shared workflow service contract, without a live LLM."""
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'agent-pack/skills/ees-work-demo/scripts/workflow_tool.py'
spec = importlib.util.spec_from_file_location('workflow_tool_under_test', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PACKAGE = types.ModuleType('ees_workflow_tool_integration_subject')
PACKAGE.__path__ = [str(SOURCE.parent)]
with patch.dict(sys.modules, {PACKAGE.__name__: PACKAGE}):
    workflow = importlib.import_module(f'{PACKAGE.__name__}.ees_workflow')


class WorkflowToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = module.Tools()
        self.user = {'id': 'u1', 'role': 'user'}
        self.metadata = {'chat_id': 'chat-a'}
        self.case = {'id': 'case-a', 'selected_id': 'db-j', 'revision': 7,
                     'jobs': {'db-j': {'inputs': {'target': 'sample-db'}, 'status': 'failed'}}}
        self.state = {'ok': True, 'case': self.case, 'can_manage': False,
                      'draft': {'private': 'not part of a runtime response'},
                      'cases': [{'id': 'unrelated-case'}]}
        self.backend = types.ModuleType('open_webui.ees_workflow')
        self.backend.get_state = AsyncMock(return_value=self.state)
        self.backend.handle_action = AsyncMock(return_value=self.state)
        self.patch = patch.dict(sys.modules, {'open_webui': types.ModuleType('open_webui'),
                                            'open_webui.ees_workflow': self.backend})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def test_view_reads_manual_panel_state_without_mutating_or_leaking_draft(self):
        result = await self.tool.ees_workflow_view(__user__=self.user, __metadata__=self.metadata)
        self.assertEqual(result['case']['jobs']['db-j']['inputs']['target'], 'sample-db')
        self.assertNotIn('draft', result)
        self.assertNotIn('cases', result)
        self.backend.get_state.assert_awaited_once_with(self.user, chat_id='chat-a')
        self.backend.handle_action.assert_not_awaited()

    async def test_action_uses_server_metadata_current_case_and_explicit_revision(self):
        events = AsyncMock(return_value={'ok': True})
        result = await self.tool.ees_workflow_action('run', expected_revision=7,
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(result['ok'])
        self.backend.handle_action.assert_awaited_once_with(self.user, {
            'action': 'run', 'chat_id': 'chat-a', 'case_id': 'case-a', 'node_id': 'db-j',
            'payload': {}, 'expected_revision': 7})
        self.assertEqual(events.await_count, 2)
        self.assertIn('ensureChat', events.await_args_list[0].args[0]['data']['code'])
        self.assertIn('ees-work-changed', events.await_args_list[1].args[0]['data']['code'])

    async def test_conflict_does_not_notify_as_success_or_retry(self):
        failure = {'ok': False, 'error': {'code': 'revision_conflict', 'message': 'refresh'}}
        self.backend.handle_action.return_value = failure
        events = AsyncMock(return_value={'ok': True})
        result = await self.tool.ees_workflow_action('run', expected_revision=6,
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result, failure)
        self.assertEqual(self.backend.handle_action.await_count, 1)
        self.assertEqual(events.await_count, 1)

    async def test_completed_case_exposes_selection_only_and_blocks_result_mutations(self):
        for status in ('passed', 'completed', 'success', 'skipped'):
            self.case['status'] = status
            view = await self.tool.ees_workflow_view(__user__=self.user, __metadata__=self.metadata)
            self.assertEqual(view['available_actions'], ['select'])
            self.assertIn('새 실행', view['message'])
            for action, payload in (('run', {}), ('run', {'document': 'replacement'}),
                                    ('run', {'confirm': True}), ('update_inputs', {'inputs': {'db': 'other'}})):
                result = await self.tool.ees_workflow_action(action, payload, expected_revision=7,
                    __user__=self.user, __metadata__=self.metadata)
                self.assertEqual(result['error']['code'], 'case_completed')
        self.backend.handle_action.assert_not_awaited()
        self.case['status'] = 'in_progress'
        result = await self.tool.ees_workflow_action('run', expected_revision=7,
            __user__=self.user, __metadata__=self.metadata)
        self.assertTrue(result['ok'])
        self.backend.handle_action.assert_awaited_once()

    async def test_missing_chat_and_unknown_action_never_execute(self):
        result = await self.tool.ees_workflow_action('run', __user__=self.user)
        self.assertEqual(result['error']['code'], 'chat_required')
        result = await self.tool.ees_workflow_action('shell', __metadata__=self.metadata)
        self.assertEqual(result['error']['code'], 'unsupported_action')
        self.backend.handle_action.assert_not_awaited()

    async def test_draft_is_explicit_and_admin_only(self):
        result = await self.tool.ees_workflow_view(True, __user__=self.user, __metadata__=self.metadata)
        self.assertEqual(result['error']['code'], 'admin_required')
        self.state['can_manage'] = True
        result = await self.tool.ees_workflow_view(True, __user__=self.user, __metadata__=self.metadata)
        self.assertEqual(result['draft'], self.state['draft'])

    async def test_process_detail_reports_legacy_server_without_breaking_navigation(self):
        calls = []

        async def legacy_get_state(user, chat_id='', case_id=''):
            calls.append((user, chat_id, case_id))
            return self.state

        self.backend.get_state = legacy_get_state
        events = AsyncMock(return_value={'ok': True})
        detail = await self.tool.ees_workflow_view(process_id='setup-p',
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(detail['error']['code'], 'program_upgrade_required')
        self.assertEqual(calls, [])
        navigation = await self.tool.ees_workflow_view(include_navigation=True,
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(navigation['ok'], navigation)
        self.assertEqual(calls, [(self.user, 'chat-a', '')])
        self.assertTrue(navigation['read_only'])
        events.assert_not_awaited()
        self.backend.handle_action.assert_not_awaited()

    async def test_browser_failure_does_not_reexecute_or_erase_recorded_result(self):
        events = AsyncMock(side_effect=RuntimeError('connection lost'))
        result = await self.tool.ees_workflow_action('run', expected_revision=7,
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(result['ok'])
        self.assertEqual(result['panel_notification']['code'], 'browser_unconfirmed')
        self.assertEqual(self.backend.handle_action.await_count, 1)

    async def test_failed_pending_binding_cannot_create_a_different_case(self):
        self.state['case'] = None
        events = AsyncMock(return_value={'ok': False, 'code': 'bind_failed'})
        result = await self.tool.ees_workflow_action('create',
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result['error']['code'], 'binding_unconfirmed')
        self.backend.handle_action.assert_not_awaited()

    async def test_display_only_calls_fixed_ui_code_and_checks_admin_role(self):
        events = AsyncMock(return_value={'ok': True})
        result = await self.tool.ees_workflow_display({'panel_open': False},
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(result['ok'])
        self.assertIn('display(chatId,options)', events.await_args.args[0]['data']['code'])
        self.backend.handle_action.assert_not_awaited()
        result = await self.tool.ees_workflow_display({'workspace': True},
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result['error']['code'], 'admin_required')
        result = await self.tool.ees_workflow_display({'category': '<script>'},
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result['error']['code'], 'invalid_display')

    async def test_navigation_is_explicit_and_does_not_copy_admin_draft(self):
        self.state['catalog'] = {'sites': {'us-a': {'name': '공장 A'}}, 'systems': ['EMS'],
                                 'roots': {'setup': ['setup-p']},
                                 'nodes': {'setup-p': {'type': 'p'}}, 'private': 'not navigation'}
        result = await self.tool.ees_workflow_view(include_navigation=True,
            __user__=self.user, __metadata__=self.metadata)
        self.assertEqual(result['navigation']['sites'], self.state['catalog']['sites'])
        self.assertEqual(result['cases'], self.state['cases'])
        self.assertNotIn('private', result['navigation'])
        self.assertNotIn('draft', result)
        self.backend.handle_action.assert_not_awaited()

    async def test_history_view_is_read_only_and_never_binds_or_switches_chat(self):
        events = AsyncMock(return_value={'ok': True})
        result = await self.tool.ees_workflow_view(case_id='case-history',
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.backend.get_state.assert_awaited_once_with(self.user, case_id='case-history')
        self.assertTrue(result['read_only'])
        self.assertEqual(result['available_actions'], [])
        events.assert_not_awaited()
        self.backend.handle_action.assert_not_awaited()
        self.backend.get_state.return_value = {'ok': False, 'error': {'code': 'case_not_found'}}
        denied = await self.tool.ees_workflow_view(case_id='someone-elses-case',
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(denied['error']['code'], 'case_not_found')
        self.assertNotIn('case', denied)
        events.assert_not_awaited()

    async def test_factory_and_history_display_validate_ids_before_notifying_browser(self):
        self.state['catalog'] = {'sites': {'us-a': {}},
                                 'nodes': {'setup-p': {'type': 'p'}, 'db-j': {'type': 'j'}}}
        events = AsyncMock(return_value={'ok': True})
        options = {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p', 'history_open': True}
        result = await self.tool.ees_workflow_display(options,
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(result['ok'])
        self.assertIn(json.dumps(options), events.await_args.args[0]['data']['code'])
        events.reset_mock()
        for invalid in ({'site_id': 'missing'}, {'process_id': 'db-j'}, {'case_id': {}},
                        {'history_open': 'yes'}, {'case_id': 'a', 'history_case_id': 'b'}):
            result = await self.tool.ees_workflow_display(invalid,
                __user__=self.user, __metadata__=self.metadata, __event_call__=events)
            self.assertEqual(result['error']['code'], 'invalid_display')
        events.assert_not_awaited()
        for key in ('case_id', 'history_case_id'):
            self.backend.get_state.reset_mock()
            result = await self.tool.ees_workflow_display({key: 'accessible-run'},
                __user__=self.user, __metadata__=self.metadata, __event_call__=events)
            self.assertTrue(result['ok'])
            self.backend.get_state.assert_awaited_with(self.user, case_id='accessible-run')
        events.reset_mock()
        self.backend.get_state.side_effect = [self.state, {'ok': False, 'error': {'code': 'case_not_found'}}]
        result = await self.tool.ees_workflow_display({'history_case_id': 'forbidden'},
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result['error']['code'], 'case_not_found')
        events.assert_not_awaited()
        self.backend.handle_action.assert_not_awaited()


class WorkflowToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Real SQLite/service actions; only WebUI identity/assets/browser are synthetic."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.users = {key: {'id': key, 'role': role} for key, role in
                      (('alice', 'user'), ('bob', 'user'), ('admin', 'admin'))}
        self.chats = {'chat-a': {'id': 'chat-a', 'user_id': 'alice'},
                      'chat-a2': {'id': 'chat-a2', 'user_id': 'alice'},
                      'chat-b': {'id': 'chat-b', 'user_id': 'bob'}}
        self.assets = {'tools': [], 'skills': [], 'skill_bodies': {}, 'skill_versions': {}}
        self.service = workflow.WorkflowService(
            Path(temporary.name) / 'ees-work.sqlite3',
            AsyncMock(side_effect=lambda key: deepcopy(self.users.get(key))),
            AsyncMock(side_effect=lambda key: deepcopy(self.chats.get(key))),
            AsyncMock(side_effect=lambda user: deepcopy(self.assets)))
        self.user = self.users['alice']
        self.events = AsyncMock(return_value={'ok': True})
        self.context = {'__user__': self.user, '__metadata__': {'chat_id': 'chat-a'},
                        '__event_call__': self.events}
        backend = types.ModuleType('open_webui.ees_workflow')
        backend.get_state = self.service.get_state
        backend.handle_action = self.service.handle_action
        patched = patch.dict(sys.modules, {'open_webui': types.ModuleType('open_webui'),
                                          'open_webui.ees_workflow': backend})
        patched.start()
        self.addCleanup(patched.stop)
        self.tool = module.Tools()

    def stored_rows(self):
        with self.service._db() as db:
            return ([tuple(row) for row in db.execute('SELECT * FROM catalog')],
                    [tuple(row) for row in db.execute('SELECT * FROM cases ORDER BY id')])

    async def publish(self, definition):
        admin = self.users['admin']
        state = await self.service.get_state(admin)
        saved = await self.service.handle_action(admin, {
            'action': 'save_draft', 'expected_revision': state['draft_revision'],
            'payload': {'definition': definition}})
        self.assertTrue(saved['ok'], saved)
        for action in ('validate_draft', 'publish'):
            result = await self.service.handle_action(admin, {
                'action': action, 'expected_revision': saved['draft_revision']})
            self.assertTrue(result['ok'], result)

    async def create(self, **payload):
        result = await self.tool.ees_workflow_action('create',
            {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p', **payload}, **self.context)
        self.assertTrue(result['ok'], result)
        return result['case']

    async def act(self, case, action, node_id, payload=None):
        return await self.tool.ees_workflow_action(action, payload,
            node_id=node_id, expected_revision=case['revision'], **self.context)

    async def test_discovery_does_not_create_bind_or_change_pending_and_current_cases(self):
        before = self.stored_rows()
        empty = await self.tool.ees_workflow_view(include_navigation=True, **self.context)
        self.assertTrue(empty['ok'], empty)
        self.assertEqual(empty['cases'], [])
        self.assertEqual(empty['available_actions'], [])
        self.assertTrue(empty['read_only'])
        self.assertEqual(self.stored_rows(), before)
        pending = await self.service.handle_action(self.user, {'action': 'create'})
        self.assertTrue(pending['ok'], pending)
        before = self.stored_rows()
        result = await self.tool.ees_workflow_view(include_navigation=True, **self.context)
        self.assertIsNone(result['case'])
        self.assertEqual([case['id'] for case in result['cases']], [pending['case']['id']])
        self.assertEqual(result['cases'][0]['chat_id'], '')
        self.assertEqual(self.stored_rows(), before)
        self.events.assert_not_awaited()
        bound = await self.service.handle_action(self.user, {
            'action': 'bind', 'case_id': pending['case']['id'], 'chat_id': 'chat-a',
            'expected_revision': pending['case']['revision']})
        self.assertTrue(bound['ok'], bound)
        before = self.stored_rows()
        current = await self.tool.ees_workflow_view(include_navigation=True, **self.context)
        self.assertEqual(current['case'], bound['case'])
        self.assertEqual(self.stored_rows(), before)
        self.events.assert_not_awaited()

    async def test_process_detail_exposes_required_steps_and_scopes_tools_and_instructions(self):
        definition = workflow._seed()
        definition['tools']['ops-only'] = {**deepcopy(definition['tools']['network']),
                                           'id': 'ops-only', 'name': '운영 전용 점검'}
        definition['nodes']['ops-j']['tools'] = ['ops-only']
        definition['skills']['ops-only'] = {'id': 'ops-only', 'name': '운영 전용 지침',
                                           'type': 'instruction', 'body': '운영 전용 본문'}
        definition['nodes']['ops-j']['skills'] = ['ops-only']
        definition['nodes']['setup-p']['instructions'] = '대상 공장과 시스템을 먼저 확인'
        definition['tools']['health'].update(source='open_webui', reference='real-health', adapter='unavailable')
        self.assets['tools'] = [{'id': 'real-health', 'name': '연결 전 점검 도구'}]
        await self.publish(definition)
        before = self.stored_rows()
        result = await self.tool.ees_workflow_view(process_id='setup-p', **self.context)
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['read_only'])
        self.assertEqual(result['available_actions'], [])
        plan = result['workflow']
        self.assertEqual((plan['source'], plan['process_id']), ('published', 'setup-p'))
        detail = plan['definition']
        self.assertEqual(detail['roots'], {'setup': ['setup-p'], 'ops': [], 'incident': []})
        self.assertNotIn('ops-j', detail['nodes'])
        self.assertNotIn('ops-only', detail['tools'])
        self.assertNotIn('ops-only', detail['skills'])
        self.assertIn('common', detail['skills'])
        self.assertEqual(detail['nodes']['setup-p']['instructions'], '대상 공장과 시스템을 먼저 확인')
        self.assertEqual(detail['nodes']['install-t']['deps'], definition['nodes']['install-t']['deps'])
        self.assertEqual(detail['nodes']['db-j']['bindings'], definition['nodes']['db-j']['bindings'])
        self.assertEqual(detail['tools']['gateway']['input'], 'db')
        self.assertEqual(detail['nodes']['scope-j']['mode'], 'manual')
        self.assertTrue(detail['tools']['health']['available'])
        self.assertFalse(detail['tools']['health']['executable'])
        self.assertFalse(detail['tools']['health']['simulation'])
        self.assertTrue(detail['tools']['gateway']['simulation'])
        self.assertNotIn('draft', result)
        self.assertEqual(self.stored_rows(), before)
        self.events.assert_not_awaited()

    async def test_history_planning_uses_frozen_definition_and_current_access_to_skill_snapshot(self):
        definition = workflow._seed()
        skill_id = 'webui-skill:read'
        definition['skills'][skill_id] = {'id': skill_id, 'name': '기존 사내 읽기 절차',
            'type': 'skill', 'source': 'open_webui', 'reference': 'read', 'body': ''}
        definition['nodes']['db-j']['skills'] = [skill_id]
        self.assets.update(skills=[{'id': 'read', 'name': '기존 사내 읽기 절차'}],
                           skill_bodies={'read': '진행 건 생성 당시의 허용된 읽기 절차'},
                           skill_versions={'read': 100})
        await self.publish(definition)
        case = await self.create()
        definition['nodes']['db-j']['name'] = '개정된 DB 점검'
        self.assets['skill_bodies']['read'] = '현재 게시된 읽기 절차'
        self.assets['skill_versions']['read'] = 200
        await self.publish(definition)
        self.events.reset_mock()
        before = self.stored_rows()
        published = await self.tool.ees_workflow_view(process_id='setup-p', **self.context)
        history = await self.tool.ees_workflow_view(case_id=case['id'], **self.context)
        self.assertEqual(published['workflow']['source'], 'published')
        self.assertEqual(history['workflow']['source'], 'case')
        self.assertGreater(published['workflow']['version'], history['workflow']['version'])
        current_definition = published['workflow']['definition']
        frozen_definition = history['workflow']['definition']
        self.assertEqual(current_definition['nodes']['db-j']['name'], '개정된 DB 점검')
        self.assertEqual(frozen_definition['nodes']['db-j']['name'], case['definition']['nodes']['db-j']['name'])
        self.assertEqual(current_definition['skills'][skill_id]['body'], '현재 게시된 읽기 절차')
        self.assertEqual(frozen_definition['skills'][skill_id]['body'], '진행 건 생성 당시의 허용된 읽기 절차')
        self.assertEqual(frozen_definition['skills'][skill_id]['snapshot_updated_at'], 100)
        self.assets['skills'] = []
        self.assets['skill_bodies'] = {}
        for arguments in ({'process_id': 'setup-p'}, {'case_id': case['id']}):
            denied = await self.tool.ees_workflow_view(**arguments, **self.context)
            skill = denied['workflow']['definition']['skills'][skill_id]
            self.assertFalse(skill['available'])
            self.assertEqual(skill['body'], '')
            self.assertNotIn('진행 건 생성 당시의 허용된 읽기 절차', json.dumps(denied, ensure_ascii=False))
            self.assertNotIn('현재 게시된 읽기 절차', json.dumps(denied, ensure_ascii=False))
        self.assertEqual(self.stored_rows(), before)
        self.events.assert_not_awaited()

    async def test_chat_actions_keep_shared_manual_input_dependency_and_revision_guards(self):
        await self.tool.ees_workflow_view(include_navigation=True, **self.context)
        await self.tool.ees_workflow_view(process_id='setup-p', **self.context)
        case = await self.create()
        for node, payload, code in (('db-j', {}, 'prerequisite_required'),
                                    ('scope-j', {}, 'confirmation_required'),
                                    ('setup-p', {'confirm': True}, 'no_ready_jobs')):
            before = self.stored_rows()
            self.events.reset_mock()
            blocked = await self.act(case, 'run', node, payload)
            self.assertEqual(blocked['error']['code'], code)
            self.assertEqual(self.stored_rows(), before)
            self.assertEqual(self.events.await_count, 1)  # Binding check; no success notification.
        for node, payload in (('scope-j', {'confirm': True}), ('infra-j', {}),
                              ('install-j', {'confirm': True})):
            result = await self.act(case, 'run', node, payload)
            self.assertTrue(result['ok'], result)
            case = result['case']
        self.assertEqual(case['jobs']['scope-j']['history'][0]['kind'], 'human_confirmation')
        cleared = await self.act(case, 'update_inputs', 'db-j', {'inputs': {'db': ''}})
        self.assertTrue(cleared['ok'], cleared)
        case = cleared['case']
        before = self.stored_rows()
        missing = await self.act(case, 'run', 'db-j')
        self.assertEqual(missing['error']['code'], 'input_required')
        self.assertEqual(self.stored_rows(), before)
        saved = await self.act(case, 'update_inputs', 'db-j', {'inputs': {'db': '승인된 진단 대상'}})
        self.assertTrue(saved['ok'], saved)
        before = self.stored_rows()
        stale = await self.act(case, 'run', 'db-j')
        self.assertEqual(stale['error']['code'], 'revision_conflict')
        self.assertEqual(self.stored_rows(), before)
        done = await self.act(saved['case'], 'run', 'db-j')
        self.assertTrue(done['ok'], done)
        self.assertTrue(done['simulation'])
        self.assertEqual(done['case']['jobs']['db-j']['status'], 'passed')
        panel_state = await self.service.get_state(self.user, chat_id='chat-a')
        self.assertEqual(panel_state['case'], done['case'])
        self.assertEqual(done['case']['jobs']['db-j']['attempt'], 1)

    async def test_planning_rejects_invalid_identifiers_and_foreign_execution_access(self):
        bob_case = await self.service.handle_action(self.users['bob'], {
            'action': 'create', 'chat_id': 'chat-b'})
        self.assertTrue(bob_case['ok'], bob_case)
        before = self.stored_rows()
        for arguments, code in (({'process_id': {}}, 'invalid_request'),
                                ({'process_id': 'setup-p', 'case_id': bob_case['case']['id']}, 'invalid_request'),
                                ({'process_id': 'db-j'}, 'process_not_found'),
                                ({'process_id': 'missing-process'}, 'process_not_found'),
                                ({'case_id': bob_case['case']['id']}, 'case_not_found')):
            denied = await self.tool.ees_workflow_view(**arguments, **self.context)
            self.assertEqual(denied['error']['code'], code)
            self.assertNotIn('workflow', denied)
            self.assertNotIn('case', denied)
        navigation = await self.tool.ees_workflow_view(include_navigation=True, **self.context)
        self.assertEqual(navigation['cases'], [])
        self.assertEqual(self.stored_rows(), before)
        self.events.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
