"""Chat controls use the durable public facade, never browser execution callbacks."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'agent-pack/skills/ees-work-demo/scripts/workflow_tool.py'
spec = importlib.util.spec_from_file_location('execution_chat_tool_subject', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExecutionChatToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = types.ModuleType('open_webui.ees_workflow')
        for name in ('execution_plan', 'execution_action', 'execution_state'):
            setattr(self.backend, name, AsyncMock(return_value={'ok': True, 'run': {'id': 'r', 'status': 'queued'}}))
        self.patch = patch.dict(sys.modules, {'open_webui': types.ModuleType('open_webui'), 'open_webui.ees_workflow': self.backend})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.tool = module.Tools()
        self.user = {'id': 'current', 'role': 'user'}

    async def test_headless_plan_keeps_server_user_and_exact_published_scope(self):
        scope = {'site_id': 'factory', 'system': 'EMS', 'process_id': 'p', 'version': 4}
        await self.tool.ees_execution_plan('t', scope=scope, inputs={'repository': 'org/repo'}, __user__=self.user)
        self.backend.execution_plan.assert_awaited_once_with(self.user, {
            'node_id': 't', 'case_id': '', 'scope': scope, 'chat_id': '', 'inputs': {'repository': 'org/repo'}})
        self.backend.execution_action.assert_not_awaited()

    async def test_start_replay_forwards_exact_same_receipt_and_no_browser(self):
        for _ in range(2):
            await self.tool.ees_execution_action('start', 'request:one', plan_id='plan', plan_hash='hash', __user__=self.user)
        self.assertEqual(self.backend.execution_action.await_args_list[0], self.backend.execution_action.await_args_list[1])
        self.assertEqual(self.backend.execution_action.await_args.args[1], {'action': 'start', 'request_id': 'request:one', 'plan_id': 'plan', 'plan_hash': 'hash'})

    async def test_human_confirmation_cannot_be_fabricated_by_chat(self):
        result = await self.tool.ees_execution_action('confirm', 'confirm', run_id='run', expected_revision=2, __user__=self.user)
        self.assertFalse(result['ok'])
        self.backend.execution_action.assert_not_awaited()

    async def test_control_and_input_are_distinct_revision_bound_requests(self):
        for action in ('pause', 'cancel', 'resume', 'inputs'):
            result = await self.tool.ees_execution_action(action, action, run_id='run', expected_revision=3,
                inputs={'page_id': '42'} if action == 'inputs' else None, __user__=self.user)
            self.assertTrue(result['ok'])
            body = self.backend.execution_action.await_args.args[1]
            self.assertEqual(body['expected_revision'], 3)
            self.assertEqual('inputs' in body, action == 'inputs')

    async def test_state_read_cannot_start_or_retry_execution(self):
        self.backend.execution_state.return_value = {'ok': True, 'run': {'status': 'unknown', 'calls': [{'status': 'unknown'}]}}
        result = await self.tool.ees_execution_state(run_id='run', __user__=self.user)
        self.assertEqual(result['run']['status'], 'unknown')
        self.backend.execution_action.assert_not_awaited()
        self.backend.execution_state.assert_awaited_once_with(self.user, run_id='run', case_id='', chat_id='')

    async def test_malformed_or_mixed_request_does_not_reach_service(self):
        for kwargs in ({'plan_id': 'p'}, {'plan_id': 'p', 'plan_hash': 'h', 'run_id': 'r'}, {'plan_id': 'p', 'plan_hash': 'h', 'inputs': {'__user__': {}}}):
            self.assertFalse((await self.tool.ees_execution_action('start', 'one', **kwargs))['ok'])
        self.assertFalse((await self.tool.ees_execution_plan('j', case_id='case', scope={'x': 1}))['ok'])
        self.backend.execution_action.assert_not_awaited()
        self.backend.execution_plan.assert_not_awaited()

    def test_real_contract_view_never_claims_simulation_or_actual_completion(self):
        result = module._compact({'ok': True, 'case': {'definition': {'nodes': {'j': {'execution': {'kind': 'fixed'}}}}}})
        self.assertFalse(result['simulation'])
        self.assertIn('UNKNOWN', result['message'])
        self.assertNotIn('모의 실행입니다', result['message'])
