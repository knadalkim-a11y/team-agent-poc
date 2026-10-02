"""AI may read/propose/navigate; authenticated human commands own all mutations."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'agent-pack/skills/ees-work-demo/scripts'
spec = importlib.util.spec_from_file_location('ees_integrated_tool', SCRIPTS/'workflow_tool.py')
tool_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool_module)


class WorkflowToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = tool_module.Tools()
        self.user = {'id': 'alice', 'role': 'user'}
        self.backend = ModuleType('open_webui.ees_workflow')
        self.backend.workspace_state = AsyncMock(return_value={'ok': True, 'workflow': {'id': 'p', 'revision': 3, 'can_manage':True},
            'ui_state': {'private': 'not model context'}, 'intent_token': 'not model context'})
        self.backend.workspace_command = AsyncMock()
        self.backend.workspace_input_preview = AsyncMock(return_value={"ok":True,"proposal_kind":"inputs","run_id":"r","job_id":"j","base_revision":3,"context_id":"context:1","proposal":{"target":"draft"},"saved":False,"executed":False})
        # Load actual definition validator without Native imports or a fake
        # validator that merely agrees with the implementation.
        package = ModuleType('ees_tool_validation'); package.__path__ = [str(SCRIPTS)]
        sys.modules[package.__name__] = package
        import importlib
        validation = importlib.import_module(package.__name__ + '.ees_workflow_workspace')
        authoring = importlib.import_module(package.__name__ + '.ees_workflow_authoring')
        self.modules = patch.dict(sys.modules, {'open_webui.ees_workflow': self.backend,
            'open_webui.ees_workflow_workspace': validation, 'open_webui.ees_workflow_authoring': authoring})
        self.modules.start(); self.addCleanup(self.modules.stop)
        self.definition = {'id': 'p', 'name': '합성 작성 초안', 'system_id': 'EMS', 'nodes': {}}
        self.event = AsyncMock(return_value={'ok': True, 'preview': True})

    async def propose(self, **change):
        values = dict(workflow_id='p', base_revision=3, definition=self.definition, context_id='context:1',
            __user__=self.user, __metadata__={'chat_id': 'chat-a'}, __event_call__=self.event)
        values.update(change)
        return await self.tool.ees_workflow_propose(**values)

    async def test_input_preview_uses_server_gate_and_only_local_preview(self):
        result=await self.propose(proposal_kind='inputs',run_id='r',job_id='j',definition=None,inputs={'target':'draft'})
        self.assertTrue(result['ok']);self.assertFalse(result['saved']);self.assertFalse(result['executed'])
        self.backend.workspace_input_preview.assert_awaited_once()
        payload=self.backend.workspace_input_preview.await_args.args[1]
        self.assertEqual(payload['proposal'],{'target':'draft'});self.assertEqual(payload['expected_revision'],3)
        self.backend.workspace_command.assert_not_awaited()
        self.assertIn('"proposal_kind": "inputs"',self.event.await_args.args[0]['data']['code'])
        self.event.reset_mock();self.backend.workspace_input_preview.return_value={'ok':False,'error':{'code':'revision_conflict'}}
        denied=await self.propose(proposal_kind='inputs',run_id='r',job_id='j',inputs={'target':'draft'})
        self.assertFalse(denied['ok']);self.event.assert_not_awaited()

    async def test_access_filtered_read_has_no_private_ui_or_intent(self):
        result = await self.tool.ees_workflow_view('p', __user__=self.user)
        self.assertEqual(set(result), {'ok', 'workflow'})
        self.backend.workspace_state.assert_awaited_once_with(self.user, 'p', '', '', '')
        self.backend.workspace_command.assert_not_awaited()

    async def test_denied_read_cannot_navigate_or_disclose(self):
        self.backend.workspace_state.return_value = {'ok': False, 'error': {'code': 'workflow_not_found'}}
        result = await self.tool.ees_workflow_display('p', __user__=self.user,
            __metadata__={'chat_id': 'chat-a'}, __event_call__=self.event)
        self.assertFalse(result['ok']); self.event.assert_not_awaited()

    async def test_current_chat_reference_is_only_a_scoped_hint_checked_against_server(self):
        reference={'kind':'workspace','workflow_id':'p','run_id':'','job_id':'','revision':3,
            'context_id':'context:'+('x'*250),'intent_token':'never disclose'}
        result=await self.tool.ees_workflow_view(__user__=self.user,
            __metadata__={'user_message':{'meta':{'ees_work_reference':reference}}})
        self.backend.workspace_state.assert_awaited_once_with(self.user,'p','','','')
        self.assertEqual(result['work_context']['context_id'],reference['context_id'])
        self.assertNotIn('intent_token',result['work_context'])
        reference['revision']=2
        stale=await self.tool.ees_workflow_view(__user__=self.user,__metadata__={'ees_work_reference':reference})
        self.assertNotIn('work_context',stale)
        other=await self.tool.ees_workflow_view('other',__user__=self.user,__metadata__={'ees_work_reference':reference})
        self.assertNotIn('work_context',other)

    async def test_read_access_does_not_grant_edit_proposal_permission(self):
        self.backend.workspace_state.return_value['workflow']['can_manage']=False
        result=await self.propose()
        self.assertEqual(result['error']['code'],'workflow_manage_forbidden')
        self.event.assert_not_awaited()

    async def test_preview_never_saves_publishes_or_executes(self):
        result = await self.propose()
        self.assertTrue(result['ok']); self.assertFalse(result['saved']); self.assertFalse(result['published'])
        self.backend.workspace_command.assert_not_awaited()
        event = self.event.await_args.args[0]
        self.assertEqual(event['type'], 'execute')
        self.assertIn('api.propose(chatId,payload)', event['data']['code'])
        self.assertNotIn('fetch(', event['data']['code'])
        self.assertIn('"chat-a"', event['data']['code'])

    async def test_stale_revision_rejected_before_browser(self):
        result = await self.propose(base_revision=2)
        self.assertEqual(result['error']['code'], 'revision_conflict'); self.event.assert_not_awaited()

    async def test_cross_target_malformed_secret_and_bool_revision_rejected(self):
        for change in ({'definition': dict(self.definition, id='other')},
                       {'definition': dict(self.definition, nodes=[])},
                       {'definition': dict(self.definition, pat='must not persist')},
                       {'base_revision': True}):
            with self.subTest(change=list(change)):
                result = await self.propose(**change)
                self.assertFalse(result['ok']); self.event.assert_not_awaited()
        self.backend.workspace_command.assert_not_awaited()

    async def test_missing_native_chat_and_late_ui_refusal_are_not_success(self):
        missing = await self.propose(__metadata__={})
        self.assertFalse(missing['ok']); self.event.assert_not_awaited()
        self.event.return_value = {'ok': False, 'code': 'context_changed'}
        stale = await self.propose()
        self.assertFalse(stale['ok']); self.assertFalse(stale['saved'])

    async def test_model_strings_are_serialized_data_not_javascript(self):
        dangerous = dict(self.definition, name='";fetch("/bad"); //')
        result = await self.propose(definition=dangerous)
        self.assertTrue(result['ok'])
        import json
        code = self.event.await_args.args[0]['data']['code']
        self.assertIn(json.dumps(dangerous['name']), code)
        self.assertEqual(code.count('api.propose('), 1)


if __name__ == '__main__':
    unittest.main()
