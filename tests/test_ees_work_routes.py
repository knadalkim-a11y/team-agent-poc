"""Integrated authenticated HTTP boundary and revision-bound unsaved model output."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException
from test_ees_work_workspace import workflow


class WorkRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.users={'admin':{'id':'admin','role':'admin'},'reader':{'id':'reader','role':'user'}}
        self.service=workflow.WorkflowService(Path(self.temp.name)/'work.db',self.users.get,lambda _:None)
        self.patch=patch.object(workflow,'_production_service',return_value=self.service)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.app=FastAPI()
        async def verified(authorization: str = Header(default='')):
            user=self.users.get(authorization.removeprefix('Bearer '))
            if not user: raise HTTPException(status_code=401)
            return user
        workflow.install(self.app,verified)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://native.test')
        self.addAsyncCleanup(self.client.aclose)
        result=await self.command('create_workflow',name='HTTP 합성 절차',system_id='EMS')
        self.identifier=result.json()['workflow_id']; self.revision=result.json()['revision']

    async def command(self, action, actor='admin', **body):
        return await self.client.post('/api/ees-work/workspace',headers={'Authorization':'Bearer '+actor},
            json={'action':action,'expected_revision':0,'request_id':str(uuid4()),**body})

    async def proposal(self, **extra):
        return await self.client.post('/api/ees-work/workspace/proposal',headers={'Authorization':'Bearer admin'},json={
            'workflow_id':self.identifier,'expected_revision':self.revision,'context_id':'editor-context','model_id':'native-model',
            'prompt':'명확한 합성 절차로 제안해 줘',**extra})

    async def test_current_authenticated_actor_scope_applies_to_read_and_write(self):
        for headers,code in [({},401),({'Authorization':'Bearer reader'},403)]:
            result=await self.client.get('/api/ees-work/workspace?workflow_id='+self.identifier,headers=headers)
            self.assertEqual(result.status_code,code,result.text)
        result=await self.command('save_draft',actor='reader',workflow_id=self.identifier,definition={})
        self.assertNotEqual(result.status_code,200)

    async def test_retired_routes_reject_instead_of_recreate_demo_or_mutate_old_records(self):
        for path in ('action','authoring/action','execution/plan','execution/action','input-draft/validate','input-draft/undo-record'):
            with self.subTest(path=path):
                response=await self.client.post('/api/ees-work/'+path,headers={'Authorization':'Bearer admin'},json={'action':'create','source':'panel','confirmed':True})
                self.assertEqual(response.status_code,409,response.text)
                self.assertEqual(response.json()['error']['code'],'legacy_execution_retired')
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_runs').fetchone()[0],0)

    async def test_legacy_history_read_preserves_database_and_enforces_owner(self):
        from workflow_fixture import historical_facade, arrange_legacy_catalog
        historical = historical_facade(workflow.__package__)
        old = historical.WorkflowService(self.service.database, self.users.get, lambda _: None)
        arrange_legacy_catalog(old)
        created = await old.handle_action(self.users['admin'], {'action':'create','payload':{}})
        self.assertTrue(created['ok'], created)
        case_id = created['case']['id']
        with self.service._db() as db:
            before = [tuple(row) for row in db.execute('SELECT * FROM cases')]
        response = await self.client.get('/api/ees-work/legacy?case_id='+case_id,
            headers={'Authorization':'Bearer admin'})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertTrue(result['read_only']); self.assertTrue(result['record']['simulation'])
        self.assertEqual(result['record']['id'],case_id)
        self.assertNotIn('catalog',result); self.assertNotIn('definition',result['record'])
        other = await self.client.get('/api/ees-work/legacy?case_id='+case_id,
            headers={'Authorization':'Bearer reader'})
        self.assertNotEqual(other.status_code,200)
        with self.service._db() as db:
            self.assertEqual(before,[tuple(row) for row in db.execute('SELECT * FROM cases')])

    async def test_unsaved_proposal_exact_context_server_source_and_no_database_write(self):
        async def propose(actor, model_id, context, instruction):
            self.assertEqual(context['target_id'],self.identifier)
            self.assertEqual(context['revision'],self.revision)
            return {'ok':True,'proposal':context['source'],'context':{key:context[key] for key in ('context_id','target_id','revision','kind')},'saved':False}
        self.service.operations.model=SimpleNamespace(propose=propose)
        with self.service._db() as db: before=[tuple(row) for row in db.execute('SELECT * FROM work_definitions')]
        response=await self.proposal()
        self.assertEqual(response.status_code,200,response.text); self.assertFalse(response.json()['saved'])
        with self.service._db() as db: self.assertEqual(before,[tuple(row) for row in db.execute('SELECT * FROM work_definitions')])

    async def test_revoked_actor_during_model_call_does_not_receive_proposal(self):
        async def propose(actor, model_id, context, instruction):
            self.users['admin']['role']='pending'
            return {'ok':True,'proposal':context['source']}
        self.service.operations.model=SimpleNamespace(propose=propose)
        response=await self.proposal()
        self.assertEqual(response.status_code,401,response.text)
        self.assertNotIn('definition',response.json())

    async def test_concurrent_draft_change_during_model_call_requires_new_context(self):
        async def propose(actor, model_id, context, instruction):
            result=await self.command('save_draft',workflow_id=self.identifier,expected_revision=self.revision,definition={**context['source'],'name':'현재 작성자의 변경'})
            self.assertEqual(result.status_code,200,result.text)
            return {'ok':True,'proposal':context['source']}
        self.service.operations.model=SimpleNamespace(propose=propose)
        response=await self.proposal()
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['error']['code'],'revision_conflict')

    async def test_unavailable_model_and_secret_or_cross_target_proposal_fail_before_call(self):
        response=await self.proposal(); self.assertEqual(response.json()['error']['code'],'model_unavailable')
        mock=AsyncMock(); self.service.operations.model=SimpleNamespace(propose=mock)
        for definition in ({'id':self.identifier,'name':'secret','nodes':{},'system_id':'EMS','pat':'forbidden'},
                           {'id':'elsewhere','name':'wrong','nodes':{},'system_id':'EMS'}):
            response=await self.proposal(definition=definition)
            self.assertNotEqual(response.status_code,200)
        mock.assert_not_awaited()


if __name__=='__main__': unittest.main()
