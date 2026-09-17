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
                     'site': {'id': 'us-a'}, 'system': 'EMS', 'process_id': 'setup-p',
                     'version': 1, 'definition': workflow._seed(),
                     'jobs': {'db-j': {'inputs': {'target': 'sample-db'}, 'status': 'failed'}}}
        self.target = {'kind': 'case', 'case_id': 'case-a', 'node_id': 'db-j', 'revision': 7}
        self.browser = {'ok': True, **self.target}
        self.events = AsyncMock(side_effect=lambda event: deepcopy(self.browser)
                                if 'selection(chatId)' in event['data']['code'] else {'ok': True})
        self.context = {'__user__': self.user, '__metadata__': self.metadata, '__event_call__': self.events}
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
        result = await self.tool.ees_workflow_view(**self.context)
        self.assertEqual(result['case']['jobs']['db-j']['inputs']['target'], 'sample-db')
        self.assertNotIn('draft', result)
        self.assertNotIn('cases', result)
        self.backend.get_state.assert_awaited_once_with(self.user, case_id='case-a')
        self.assertEqual(result['target'], self.target)
        self.assertEqual(self.events.await_count, 1)
        self.assertNotIn('ensureChat', self.events.await_args.args[0]['data']['code'])
        self.backend.handle_action.assert_not_awaited()

    async def test_action_uses_server_metadata_current_case_and_explicit_revision(self):
        result = await self.tool.ees_workflow_action('run', expected_revision=7, target=self.target,
            request_id='case-run:1', **self.context)
        self.assertTrue(result['ok'])
        self.backend.handle_action.assert_awaited_once_with(self.user, {
            'action': 'run', 'chat_id': 'chat-a', 'case_id': 'case-a', 'node_id': 'db-j',
            'payload': {}, 'expected_revision': 7, 'request_id': 'case-run:1'})
        self.assertEqual(self.events.await_count, 2)
        self.assertIn('selection(chatId)', self.events.await_args_list[0].args[0]['data']['code'])
        self.assertIn('ees-work-changed', self.events.await_args_list[1].args[0]['data']['code'])

    async def test_conflict_does_not_notify_as_success_or_retry(self):
        failure = {'ok': False, 'error': {'code': 'revision_conflict', 'message': 'refresh'}}
        self.backend.handle_action.return_value = failure
        result = await self.tool.ees_workflow_action('run', expected_revision=7, target=self.target,
            request_id='case-conflict:1', **self.context)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], failure['error'])
        self.assertEqual(self.backend.handle_action.await_count, 1)
        self.assertEqual(self.events.await_count, 1)

    async def test_completed_case_exposes_selection_only_and_blocks_result_mutations(self):
        completed = {'ok': False, 'error': {'code': 'case_completed', 'message': '새 실행을 시작해 주세요.'}}
        self.backend.handle_action.return_value = completed
        for status in ('passed', 'completed', 'success', 'skipped'):
            self.case['status'] = status
            view = await self.tool.ees_workflow_view(**self.context)
            self.assertEqual(view['available_actions'], ['select'])
            self.assertIn('새 실행', view['message'])
            for action, payload in (('run', {}), ('run', {'document': 'replacement'}),
                                    ('run', {'confirm': True}), ('update_inputs', {'inputs': {'db': 'other'}})):
                result = await self.tool.ees_workflow_action(action, payload, expected_revision=7,
                    target=self.target, request_id='completed-check:1', **self.context)
                self.assertEqual(result['error']['code'], 'case_completed')
        self.assertEqual(self.backend.handle_action.await_count, 16)
        self.backend.handle_action.reset_mock()
        self.backend.handle_action.return_value = self.state
        self.case['status'] = 'in_progress'
        result = await self.tool.ees_workflow_action('run', expected_revision=7, target=self.target,
            request_id='in-progress:1', **self.context)
        self.assertTrue(result['ok'])
        self.backend.handle_action.assert_awaited_once()

    async def test_missing_chat_and_unknown_action_never_execute(self):
        result = await self.tool.ees_workflow_action('run', target=self.target, request_id='missing-chat:1', __user__=self.user)
        self.assertEqual(result['error']['code'], 'chat_required')
        result = await self.tool.ees_workflow_action('shell', __metadata__=self.metadata)
        self.assertEqual(result['error']['code'], 'unsupported_action')
        self.backend.handle_action.assert_not_awaited()

    async def test_draft_is_explicit_and_admin_only(self):
        result = await self.tool.ees_workflow_view(True, **self.context)
        self.assertEqual(result['error']['code'], 'admin_required')
        self.state['can_manage'] = True
        result = await self.tool.ees_workflow_view(True, **self.context)
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
        events = AsyncMock(side_effect=[deepcopy(self.browser), RuntimeError('connection lost')])
        result = await self.tool.ees_workflow_action('run', expected_revision=7,
            target=self.target, request_id='notify-lost:1', __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertTrue(result['ok'])
        self.assertEqual(result['panel_notification']['code'], 'browser_unconfirmed')
        self.assertEqual(self.backend.handle_action.await_count, 1)

    async def test_unconfirmed_selection_cannot_create_a_different_case(self):
        self.state['case'] = None
        events = AsyncMock(return_value={'ok': False, 'code': 'selection_unconfirmed'})
        result = await self.tool.ees_workflow_action('create', {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p'},
            __user__=self.user, __metadata__=self.metadata, __event_call__=events)
        self.assertEqual(result['error']['code'], 'selection_unconfirmed')
        self.backend.handle_action.assert_not_awaited()

    async def test_selection_contract_requires_upgrade_without_falling_back_to_chat(self):
        calls = []

        async def legacy_get_state(user, chat_id='', case_id='', process_id=''):
            calls.append((user, chat_id, case_id, process_id))
            return self.state

        self.backend.get_state = legacy_get_state
        selection = {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p', 'node_id': 'db-j', 'version': 1}
        self.browser = {'ok': True, 'kind': 'published', 'selection': selection}
        result = await self.tool.ees_workflow_view(**self.context)
        self.assertEqual(result['error']['code'], 'program_upgrade_required')
        self.assertEqual(calls, [])
        result = await self.tool.ees_workflow_action('update_inputs', {'inputs': {'db': '합성 대상'}},
            target={'kind': 'published', 'selection': selection}, request_id='legacy-first-write', **self.context)
        self.assertEqual(result['error']['code'], 'program_upgrade_required')
        self.assertEqual(calls, [])
        self.backend.handle_action.assert_not_awaited()

    async def test_case_identity_node_and_revision_are_pinned_before_mutation(self):
        for changes in ({'case_id': 'other-case'}, {'node_id': 'ap-j'}, {'kind': 'history'}):
            with self.subTest(changes=changes):
                self.browser = {'ok': True, **self.target, **changes}
                result = await self.tool.ees_workflow_action('run', expected_revision=7,
                    target=self.target, request_id='changed-target:1', **self.context)
                self.assertIn(result['error']['code'], {'selection_changed', 'history_read_only'})
        self.browser = {'ok': True, **self.target, 'revision': 999}
        # Browser revision is advisory; the service supplies the current revision.
        result = await self.tool.ees_workflow_view(**self.context)
        self.assertEqual(result['target']['revision'], 7)
        stale = await self.tool.ees_workflow_action('run', expected_revision=6,
            target=self.target, request_id='stale-revision:1', **self.context)
        self.assertEqual(stale['error']['code'], 'revision_conflict')
        self.backend.handle_action.assert_not_awaited()

    async def test_missing_target_and_invalid_first_write_request_id_never_execute(self):
        result = await self.tool.ees_workflow_action('run', expected_revision=7, **self.context)
        self.assertEqual(result['error']['code'], 'target_required')
        selection = {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p', 'node_id': 'db-j', 'version': 1}
        self.browser = {'ok': True, 'kind': 'published', 'selection': selection}
        self.state.update(case=None, selection=selection)
        for request_id, code in (('', 'request_id_required'), ('has spaces', 'invalid_request_id'),
                                 ('x' * 129, 'invalid_request_id'), ({}, 'invalid_request_id')):
            result = await self.tool.ees_workflow_action('update_inputs', {'inputs': {'db': '합성 대상'}},
                target={'kind': 'published', 'selection': selection}, request_id=request_id, **self.context)
            self.assertEqual(result['error']['code'], code)
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
        self.browser = {'ok': True, 'kind': 'none'}
        self.action_number = 0
        self.events = AsyncMock(side_effect=self.browser_event)
        self.context = {'__user__': self.user, '__metadata__': {'chat_id': 'chat-a'},
                        '__event_call__': self.events}
        backend = types.ModuleType('open_webui.ees_workflow')
        backend.get_state = self.service.get_state
        backend.handle_action = self.service.handle_action
        self.backend = backend
        patched = patch.dict(sys.modules, {'open_webui': types.ModuleType('open_webui'),
                                          'open_webui.ees_workflow': backend})
        patched.start()
        self.addCleanup(patched.stop)
        self.tool = module.Tools()

    async def browser_event(self, event):
        code = event['data']['code']
        if 'selection(chatId)' in code:
            return deepcopy(self.browser)
        return {'ok': True}

    def choose_case(self, case, node_id=None, kind='case'):
        target = {'kind': kind, 'case_id': case['id'], 'node_id': node_id or case['selected_id'],
                  'revision': case['revision']}
        self.browser = {'ok': True, **target}
        return target

    async def choose_published(self, node_id='scope-j', **changes):
        state = await self.service.get_state(self.user)
        selection = {'site_id': 'us-a', 'system': 'EMS', 'process_id': 'setup-p', 'node_id': node_id,
                     'version': state['catalog']['version'], **changes}
        self.browser = {'ok': True, 'kind': 'published', 'selection': selection}
        return {'kind': 'published', 'selection': deepcopy(selection)}

    def stored_rows(self):
        with self.service._db() as db:
            return tuple([tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                         for table in ('catalog', 'cases', 'action_requests'))

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
        self.choose_case(result['case'])
        return result['case']

    async def act(self, case, action, node_id, payload=None):
        target = self.choose_case(case, node_id)
        self.action_number += 1
        return await self.tool.ees_workflow_action(action, payload,
            node_id=node_id, expected_revision=case['revision'], target=target,
            request_id=f'test-action:{self.action_number}', **self.context)

    async def test_default_view_reads_published_case_and_history_without_any_storage_change(self):
        current = await self.service.handle_action(self.user, {'action': 'create', 'chat_id': 'chat-a'})
        pending = await self.service.handle_action(self.user, {'action': 'create', 'payload': {'site_id': 'hu-a'}})
        self.assertTrue(current['ok'], current)
        self.assertTrue(pending['ok'], pending)
        published_target = await self.choose_published('db-j', site_id='hu-a', system='FDC')
        before = self.stored_rows()
        published = await self.tool.ees_workflow_view(**self.context)
        self.assertTrue(published['ok'], published)
        self.assertIsNone(published['case'], 'A displayed definition must not adopt the unrelated chat-bound case.')
        self.assertEqual(published['target'], published_target)
        self.assertEqual(published['workflow']['source'], 'published')
        self.assertEqual(self.stored_rows(), before)
        for kind in ('case', 'history'):
            target = self.choose_case(pending['case'], 'db-j', kind)
            read = await self.tool.ees_workflow_view(**self.context)
            self.assertTrue(read['ok'], read)
            self.assertEqual(read['case']['id'], pending['case']['id'])
            self.assertEqual(read['case']['chat_id'], '')
            self.assertEqual(read['target'], target)
            if kind == 'history':
                self.assertTrue(read['read_only'])
                self.assertEqual(read['available_actions'], [])
            self.assertEqual(self.stored_rows(), before)
        for call in self.events.await_args_list:
            self.assertIn('selection(chatId)', call.args[0]['data']['code'])
            self.assertNotIn('ensureChat', call.args[0]['data']['code'])

    async def test_missing_or_unconfirmed_selection_never_uses_chat_case_as_fallback(self):
        await self.create()
        before = self.stored_rows()
        for response, code in (({'ok': True, 'kind': 'none'}, 'selection_required'),
                               ({'ok': False, 'code': 'browser_unconfirmed'}, 'selection_unconfirmed')):
            self.browser = response
            result = await self.tool.ees_workflow_view(**self.context)
            self.assertEqual(result['error']['code'], code)
            self.assertNotIn('case', result)
            self.assertEqual(self.stored_rows(), before)

    async def test_first_input_write_and_published_to_case_replay_save_once(self):
        target = await self.choose_published('db-j')
        read = await self.tool.ees_workflow_view(**self.context)
        self.assertTrue(read['ok'], read)
        self.assertEqual(read['target'], target)
        payload = {'inputs': {'db': '합성 승인 진단 대상'}}
        first = await self.tool.ees_workflow_action('update_inputs', payload,
            target=read['target'], request_id='first-input:1', **self.context)
        self.assertTrue(first['ok'], first)
        case = first['case']
        self.assertEqual(case['selected_id'], 'db-j')
        self.assertEqual(case['jobs']['db-j']['inputs'], payload['inputs'])
        self.assertEqual(case['jobs']['db-j']['attempt'], 0)
        self.assertEqual(case['chat_id'], 'chat-a')
        self.assertEqual(len((await self.service.get_state(self.user))['cases']), 1)
        stored = self.stored_rows()
        for browser_target in (target, self.choose_case(case, 'db-j')):
            self.browser = {'ok': True, **browser_target}
            replay = await self.tool.ees_workflow_action('update_inputs', payload,
                target=target, request_id='first-input:1', **self.context)
            self.assertTrue(replay['ok'], replay)
            self.assertEqual(replay['case']['id'], case['id'])
            self.assertEqual(replay['case']['revision'], case['revision'])
            self.assertEqual(self.stored_rows(), stored)
        conflict = await self.tool.ees_workflow_action('update_inputs', {'inputs': {'db': '다른 합성 대상'}},
            target=target, request_id='first-input:1', **self.context)
        self.assertEqual(conflict['error']['code'], 'request_conflict')
        self.assertEqual(self.stored_rows(), stored)
        self.choose_case(case, 'ap-j')
        wrong_node = await self.tool.ees_workflow_action('update_inputs', payload,
            target=target, request_id='first-input:1', **self.context)
        self.assertEqual(wrong_node['error']['code'], 'selection_changed')
        self.assertEqual(self.stored_rows(), stored)

    async def test_first_run_notification_failure_and_replay_do_not_duplicate_confirmation(self):
        target = await self.choose_published('scope-j')

        async def lose_notification(event):
            if 'selection(chatId)' in event['data']['code']:
                return deepcopy(self.browser)
            raise RuntimeError('synthetic disconnected browser')

        self.events.side_effect = lose_notification
        first = await self.tool.ees_workflow_action('run', {'confirm': True},
            target=target, request_id='first-confirm:1', **self.context)
        self.assertTrue(first['ok'], first)
        self.assertEqual(first['panel_notification']['code'], 'browser_unconfirmed')
        case = first['case']
        self.assertEqual(case['jobs']['scope-j']['attempt'], 1)
        self.assertEqual(case['jobs']['scope-j']['history'][0]['kind'], 'human_confirmation')
        stored = self.stored_rows()
        self.events.side_effect = self.browser_event
        self.choose_case(case, 'scope-j')
        replay = await self.tool.ees_workflow_action('run', {'confirm': True},
            target=target, request_id='first-confirm:1', **self.context)
        self.assertTrue(replay['ok'], replay)
        self.assertEqual(replay['case']['jobs']['scope-j']['attempt'], 1)
        self.assertEqual(len(replay['case']['jobs']['scope-j']['history']), 1)
        self.assertEqual(self.stored_rows(), stored)

    async def test_first_run_failure_retains_created_case_and_replays_original_failure(self):
        target = await self.choose_published('db-j')
        first = await self.tool.ees_workflow_action('run', target=target,
            request_id='first-blocked:1', **self.context)
        self.assertFalse(first['ok'])
        self.assertEqual(first['error']['code'], 'prerequisite_required')
        self.assertIn('case', first, 'A failed first action must identify the retained case for recovery.')
        case = first['case']
        self.assertEqual(case['selected_id'], 'db-j')
        self.assertEqual(case['jobs']['db-j']['attempt'], 0)
        self.assertEqual(len((await self.service.get_state(self.user))['cases']), 1)
        before = self.stored_rows()
        self.choose_case(case, 'db-j')
        retry = await self.tool.ees_workflow_action('run', target=target,
            request_id='first-blocked:1', **self.context)
        self.assertFalse(retry['ok'])
        self.assertEqual(retry['error']['code'], 'prerequisite_required')
        self.assertEqual(retry['case']['id'], case['id'])
        self.assertEqual(self.stored_rows(), before)

    async def test_existing_case_replay_keeps_original_revision_without_rerunning(self):
        case = await self.create()
        target = self.choose_case(case, 'scope-j')
        result = await self.tool.ees_workflow_action('run', {'confirm': True}, expected_revision=case['revision'],
            target=target, request_id='existing-confirm:1', **self.context)
        self.assertTrue(result['ok'], result)
        self.choose_case(result['case'], 'scope-j')
        stored = self.stored_rows()
        replay = await self.tool.ees_workflow_action('run', {'confirm': True}, expected_revision=case['revision'],
            target=target, request_id='existing-confirm:1', **self.context)
        self.assertTrue(replay['ok'], replay)
        self.assertEqual(replay['case']['jobs']['scope-j']['attempt'], 1)
        self.assertEqual(self.stored_rows(), stored)

    async def test_changed_published_scope_or_version_cannot_redirect_a_prepared_write(self):
        target = await self.choose_published('db-j')
        before = self.stored_rows()
        for changes in ({'site_id': 'hu-a'}, {'system': 'FDC'}, {'node_id': 'ap-j'},
                        {'version': target['selection']['version'] + 1},
                        {'process_id': 'ops-p', 'node_id': 'ops-j'}):
            with self.subTest(changes=changes):
                self.browser = {'ok': True, 'kind': 'published', 'selection': {**target['selection'], **changes}}
                blocked = await self.tool.ees_workflow_action('update_inputs', {'inputs': {'db': '합성 대상'}},
                    target=target, request_id='pinned-input:1', **self.context)
                self.assertEqual(blocked['error']['code'], 'selection_changed')
                self.assertEqual(self.stored_rows(), before)
        self.browser = {'ok': True, **target}
        definition = workflow._seed()
        definition['nodes']['db-j']['rule'] = '게시 후 달라진 합성 검증 기준'
        await self.publish(definition)
        before = self.stored_rows()
        for call in ('view', 'write'):
            result = (await self.tool.ees_workflow_view(**self.context) if call == 'view' else
                await self.tool.ees_workflow_action('update_inputs', {'inputs': {'db': '합성 대상'}},
                    target=target, request_id='pinned-input:1', **self.context))
            self.assertEqual(result['error']['code'], 'published_version_conflict')
            self.assertEqual(self.stored_rows(), before)

    async def test_history_target_cannot_save_or_execute_in_current_chat(self):
        case = await self.create()
        target = self.choose_case(case, 'scope-j', 'history')
        before = self.stored_rows()
        for action, payload in (('run', {'confirm': True}), ('update_inputs', {'inputs': {'site': '변경'}}),
                                ('select', {})):
            result = await self.tool.ees_workflow_action(action, payload,
                target=target, expected_revision=case['revision'], request_id='history-write:1', **self.context)
            self.assertEqual(result['error']['code'], 'history_read_only')
            self.assertEqual(self.stored_rows(), before)

    async def test_explicit_node_override_cannot_redirect_a_pinned_input_or_run(self):
        target = await self.choose_published('scope-j')
        before = self.stored_rows()
        for action, payload in (('update_inputs', {'inputs': {'site': '합성 범위'}}), ('run', {'confirm': True})):
            result = await self.tool.ees_workflow_action(action, payload, node_id='install-j',
                target=target, request_id=f'published-override:{action}', **self.context)
            self.assertFalse(result['ok'], result.get('result_target'))
            self.assertEqual(result['error']['code'], 'selection_changed')
            self.assertEqual(self.stored_rows(), before)
        case = await self.create()
        target = self.choose_case(case, 'scope-j')
        before = self.stored_rows()
        for action, payload in (('update_inputs', {'inputs': {'site': '합성 범위'}}), ('run', {'confirm': True})):
            result = await self.tool.ees_workflow_action(action, payload, node_id='install-j',
                target=target, expected_revision=case['revision'], request_id=f'override:{action}', **self.context)
            self.assertFalse(result['ok'], result.get('result_target'))
            self.assertEqual(result['error']['code'], 'selection_changed')
            self.assertEqual(self.stored_rows(), before)
        # Selection is a navigation intent and may name a child in this case.
        selected = await self.tool.ees_workflow_action('select', node_id='db-j',
            target=target, expected_revision=case['revision'], **self.context)
        self.assertTrue(selected['ok'], selected)
        self.assertEqual(selected['case']['selected_id'], 'db-j')
        self.assertEqual(selected['case']['jobs'], case['jobs'])

    async def test_completed_case_blocks_new_writes_but_returns_saved_completion_on_replay(self):
        case = await self.create()
        for node_id, payload in (('scope-j', {'confirm': True}), ('infra-j', {}), ('install-j', {'confirm': True}),
                                 ('db-j', {}), ('ap-j', {}), ('ap-j', {})):
            result = await self.act(case, 'run', node_id, payload)
            self.assertTrue(result['ok'], result)
            case = result['case']
        target = self.choose_case(case, 'interface-j')
        completed = await self.tool.ees_workflow_action('run', expected_revision=case['revision'],
            target=target, request_id='complete:1', **self.context)
        self.assertTrue(completed['ok'], completed)
        self.assertEqual(completed['case']['status'], 'passed')
        current_target = self.choose_case(completed['case'], 'interface-j')
        before = self.stored_rows()
        replay = await self.tool.ees_workflow_action('run', expected_revision=case['revision'],
            target=target, request_id='complete:1', **self.context)
        self.assertTrue(replay['ok'], replay)
        self.assertEqual(replay['case']['jobs']['interface-j']['attempt'], 1)
        self.assertEqual(self.stored_rows(), before)
        for action, payload in (('run', {}), ('update_inputs', {'inputs': {'interface': '다른 합성 대상'}})):
            denied = await self.tool.ees_workflow_action(action, payload,
                expected_revision=current_target['revision'], target=current_target,
                request_id=f'completed-new:{action}', **self.context)
            self.assertEqual(denied['error']['code'], 'case_completed')
            self.assertEqual(self.stored_rows(), before)

    async def test_parent_continue_does_not_retry_failure_or_bulk_confirm_people(self):
        case = await self.create()
        for node_id, payload in (('scope-j', {'confirm': True}), ('infra-j', {}), ('install-j', {'confirm': True}),
                                 ('ap-j', {})):
            result = await self.act(case, 'run', node_id, payload)
            self.assertTrue(result['ok'], result)
            case = result['case']
        self.assertEqual(case['jobs']['ap-j']['status'], 'failed')
        result = await self.act(case, 'run', 'install-t')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['case']['jobs']['ap-j']['attempt'], 1)
        self.assertEqual(result['case']['jobs']['ap-j']['status'], 'failed')
        self.assertEqual(result['case']['jobs']['db-j']['status'], 'passed')
        self.assertEqual(result['case']['jobs']['install-j']['attempt'], 1)
        stored = self.stored_rows()
        denied = await self.act(result['case'], 'run', 'install-t', {'retry_failed': True})
        self.assertEqual(denied['error']['code'], 'retry_job_required')
        self.assertEqual(self.stored_rows(), stored)

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
            self.assertEqual(self.events.await_count, 1)  # Selection read; no success notification.
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
