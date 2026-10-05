"""Exact historical projections and public tool boundaries, reconstructed after workspace loss.

Real projection/public tool code, synthetic currently-authorized workspace response.
Native identity/loader and browser round trips are separate tests.
"""
from copy import deepcopy
import importlib
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_ees_workflow_tool import tool_module, SCRIPTS

package = ModuleType('ees_history_recovery')
package.__path__ = [str(SCRIPTS)]
sys.modules[package.__name__] = package
native = importlib.import_module(package.__name__ + '.ees_workflow_native')


class HistoricalReferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reference = dict(kind='workspace', reference_kind='historical', workflow_id='w',
            run_id='r', job_id='j', attempt_id='a1', version=1, result_revision=1,
            revision=2, context_id='history:exact')
        self.old = dict(id='a1', job_id='j', number=1, status='succeeded', created_at='2026-10-01T00:00:00Z',
            snapshot={'version':1, 'job':{'id':'j'}, 'inputs':{'project':'OLD'}}, result={'data':'OLD'})
        self.current = dict(id='a2',job_id='j',number=2,status='succeeded',
            snapshot={'version':1,'job':{'id':'j'},'inputs':{'project':'NEW'}},result={'data':'NEW'})
        self.state = {'ok':True,'ui_state':{'private':'secret'},'intent_token':'secret',
            'run':{'id':'r','workflow_id':'w','version':1,'revision':99,
                'attempts':[self.old,self.current], 'jobs':{'j':{'current_attempt':'a2','decisions':[
                    {'id':'d1','attempt_id':'a1','result_revision':1,'verdict':'completed'},
                    {'id':'d2','attempt_id':'a2','result_revision':2,'verdict':'completed'}]}}}}
        self.backend = ModuleType('open_webui.ees_workflow')
        self.backend.workspace_state = AsyncMock(return_value=self.state)
        self.backend.workspace_command = AsyncMock()
        self.backend.workspace_input_preview = AsyncMock()
        self.modules = patch.dict(sys.modules, {'open_webui.ees_workflow':self.backend,
            'open_webui.ees_workflow_native':native})
        self.modules.start(); self.addCleanup(self.modules.stop)
        self.tool = tool_module.Tools()
        self.metadata = {'chat_id':'chat-a','ees_work_reference':self.reference}
        self.user = {'id':'a','role':'user'}

    async def read(self, **values):
        return await self.tool.ees_workflow_view(__user__=self.user,__metadata__=self.metadata,**values)

    async def test_exact_old_attempt_no_current_settings_private_state_or_mutation(self):
        before=deepcopy(self.state)
        result=await self.read()
        self.assertTrue(result['ok'],result)
        self.assertTrue(result['work_context']['read_only'])
        self.assertEqual(result['historical']['attempt'],self.old)
        self.assertEqual([x['id'] for x in result['historical']['decisions']],['d1'])
        self.assertEqual(set(result),{'ok','work_context','historical'})
        result['historical']['attempt']['result']['data']='changed copy'
        self.assertEqual(self.state,before)
        self.backend.workspace_state.assert_awaited_once_with(self.user,'w','r','','')
        self.backend.workspace_command.assert_not_awaited()

    async def test_bad_identity_version_attempt_snapshot_never_falls_back(self):
        for key,value in [('workflow_id','other'),('run_id','other'),('job_id','other'),
                          ('attempt_id','missing'),('version',2),('result_revision',2),
                          ('version',True),('result_revision',0),('context_id','')]:
            with self.subTest(key=key,value=value):
                reference={**self.reference,key:value}
                result=native.historical_work_projection(self.state,reference)
                self.assertFalse(result['ok']); self.assertNotIn('historical',result)
        for change in [{'status':'running'},{'snapshot':{'version':2,'job':{'id':'j'}}}]:
            state=deepcopy(self.state);state['run']['attempts'][0].update(change)
            self.assertFalse(native.historical_work_projection(state,self.reference)['ok'])

    async def test_current_access_denial_and_evidence_revocation_hide_old_body(self):
        self.backend.workspace_state.return_value={'ok':False,'error':{'code':'scope_forbidden'}}
        self.assertEqual((await self.read())['error']['code'],'scope_forbidden')
        self.backend.workspace_state.return_value=self.state
        self.old['evidence_access']='native_access_denied'
        result=await self.read()
        self.assertEqual(result['error']['code'],'evidence_access_required')
        self.assertNotIn('historical',result)

    async def test_explicit_target_override_and_malformed_reference_fail_closed(self):
        for values in [{'workflow_id':'other'},{'run_id':'other'},{'system_id':'EMS'},{'factory_id':'f'}]:
            with self.subTest(values=values):
                self.assertFalse((await self.read(**values))['ok'])
        self.backend.workspace_state.assert_not_awaited()
        self.reference['revision']='invalid'
        self.assertFalse((await self.read())['ok'])
        self.backend.workspace_state.assert_not_awaited()

    async def test_historical_ai_cannot_propose_or_navigate_even_with_event_handler(self):
        event=AsyncMock()
        for kind in ['workflow','inputs']:
            result=await self.tool.ees_workflow_propose(workflow_id='w',base_revision=99,
                proposal_kind=kind,definition={},inputs={'project':'overwrite'},run_id='r',job_id='j',
                __user__=self.user,__metadata__=self.metadata,__event_call__=event)
            self.assertEqual(result['error']['code'],'historical_read_only')
        result=await self.tool.ees_workflow_display(workflow_id='w',run_id='r',job_id='j',
            __user__=self.user,__metadata__=self.metadata,__event_call__=event)
        self.assertEqual(result['error']['code'],'historical_read_only')
        event.assert_not_awaited(); self.backend.workspace_state.assert_not_awaited()
        self.backend.workspace_command.assert_not_awaited()
        self.backend.workspace_input_preview.assert_not_awaited()


if __name__ == '__main__': unittest.main()
