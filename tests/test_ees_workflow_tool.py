"""Native model Tool -> shared workflow service contract, without a live LLM."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'agent-pack/skills/ees-work-demo/scripts/workflow_tool.py'
spec = importlib.util.spec_from_file_location('workflow_tool_under_test', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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


if __name__ == '__main__':
    unittest.main()
