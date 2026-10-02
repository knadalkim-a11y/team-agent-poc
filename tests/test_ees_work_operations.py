"""Actual SQLite runtime/command contracts with synthetic Native transports."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType('ees_operations_tests')
package.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
sys.modules[package.__name__] = package
workflow = importlib.import_module(package.__name__ + '.ees_workflow')
ops = importlib.import_module(package.__name__ + '.ees_workflow_operations')
REF = {'tool_id': 'jira', 'function': 'jira_dashboard', 'revision': 1, 'content_hash': 'a'*64, 'schema_hash': 'b'*64, 'config_hash': 'c'*64, 'environment': 'd'*64}
REQUEST_REF = {'tool_id': 'ees-reviewed', 'function': 'service_restart', 'revision': 1, 'content_hash': 'a'*64, 'schema_hash': 'b'*64}
SCHEMA = {'type': 'object', 'properties': {'target': {'type': 'string'}}, 'required': ['target']}


class Bridge:
    def __init__(self):
        self.allowed = True
        self.calls = []
        self.result = {'status': 'succeeded', 'completeness': 'complete', 'data': {'count': 1}}
        self.delay = 0
    async def check(self, user, ref):
        if not self.allowed: ops.fail('native_access_denied')
        return {'reference': ref, 'state': 'allowed'}
    async def inspect(self, user, tool, function):
        await self.check(user, REF)
        return {'reference': deepcopy(REF), 'schema': deepcopy(SCHEMA)}
    async def inspect_registered(self, user, tool, function):
        await self.check(user, REQUEST_REF)
        return {'reference': deepcopy(REQUEST_REF), 'schema': deepcopy(SCHEMA)}
    async def invoke(self, user, ref, arguments, context):
        await self.check(user, ref)
        self.calls.append((user['id'], arguments, context))
        if self.delay: await asyncio.sleep(self.delay)
        return deepcopy(self.result)


class Connector:
    def __init__(self): self.calls = []; self.lost = False; self.effect_ok = None
    async def request(self, actor, tool, inputs, correlation):
        self.calls.append(correlation)
        if self.lost: raise TimeoutError('not persisted')
        return {'state': 'accepted', 'job_number': 'synthetic-job-1'}
    async def status(self, actor, tool, correlation, number):
        return {'state': 'reported_complete', 'job_number': number}
    async def effect(self, actor, tool, criterion, correlation):
        return {'satisfied': self.effect_ok, 'evidence': [{'check': 'synthetic-probe', 'ok': self.effect_ok}]}


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.users = {name: {'id': name, 'name': name, 'role': 'admin'} for name in ('alice', 'bob', 'carol')}
        self.bridge = Bridge()
        self.service = workflow.WorkflowService(Path(self.temp.name)/'work.db', self.users.get, lambda key: None,
            group_lookup=lambda actor: [{'id': 'team'}], group_list_lookup=lambda: [{'id': 'team', 'name': 'Team'}], native_bridge=self.bridge)
        self.runtime = self.service.operations
        self.user = self.users['alice']
        self.counter = 0
        self.now = datetime(2026, 10, 2, 10, tzinfo=timezone.utc).timestamp()
        self.runtime.clock = lambda: self.now
        self.addAsyncCleanup(self.runtime.stop)
    def body(self, action, revision=0, **kwargs):
        self.counter += 1
        return {'action': action, 'expected_revision': revision, 'request_id': 'test-'+str(self.counter), **kwargs}
    async def core(self, action, revision=0, **kwargs):
        result = await self.service.workspace_command(self.user, self.body(action, revision, **kwargs))
        self.assertTrue(result['ok'], result)
        return result
    async def make_workflow(self, mode='tool', periodic=False, contract=None, approvals=0, fields=None):
        created = await self.core('create_workflow', system_id='EMS', name='시험 절차', mode='periodic' if periodic else 'on_demand')
        wid = created['workflow_id']
        with self.service._db() as db:
            definition = json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?',(wid,)).fetchone()[0])
        p = next(iter(definition['nodes']))
        definition['nodes'][p]['children']=['t1']
        definition['nodes']['t1']={'id':'t1','type':'t','name':'단계','parent':p,'children':['j1'],'deps':[]}
        job={'id':'j1','type':'j','name':'작업','parent':'t1','children':[],'deps':[], 'mode': mode, 'inputs':[{'id':'target','type':'text','required':True,'scope':'run'}], 'result_block':'human_confirm','human_confirmation':True}
        if fields is not None: job['inputs']=deepcopy(fields)
        if mode=='tool': job.update(tool_reference=deepcopy(REF),argument_bindings={'target':{'input':'target'}})
        if contract: job.update(result_block='change_request',tool_contract_id=contract['id'],tool_contract_revision=contract['revision'],approval_count=approvals,effect_criterion={'check':'registered-status'})
        definition['nodes']['j1']=job
        await self.core('save_draft',1,workflow_id=wid,definition=definition)
        validated=await self.core('validate_workflow',2,workflow_id=wid)
        self.assertEqual(validated['validation']['errors'],[])
        await self.core('publish_workflow',2,workflow_id=wid)
        return wid
    async def start(self,wid):
        return await self.core('start_run',3,workflow_id=wid,inputs={'target':'synthetic-target'},sharing={'group_ids':['team']})
    async def make_contract(self):
        body=self.body('tool_save',tool={'system_id':'EMS','kind':'request','name':'등록된 기능','reference':deepcopy(REQUEST_REF),'guide_url':'https://guide.invalid/function','responsible_user_id':'bob','status_function':'service_status','output_schema':{'type':'object'}})
        tool=(await self.runtime.command(self.user,body))['tool']
        tool=(await self.runtime.command(self.user,self.body('tool_submit',tool['revision'],tool_contract_id=tool['id'])))['tool']
        return (await self.runtime.command(self.users['bob'],self.body('tool_review',tool['revision'],tool_contract_id=tool['id'],decision='approve')))['tool']
    async def prepare(self, approvals=0):
        tool=await self.make_contract(); wid=await self.make_workflow('human',contract=tool,approvals=approvals); run=await self.start(wid)
        request=(await self.runtime.command(self.user,self.body('request_prepare',run['revision'],run_id=run['run_id'],job_id='j1',tool_contract_id=tool['id'],inputs={'target':'synthetic-target'})))['request']
        return run,request
    async def approve(self,request,who):
        return (await self.runtime.command(self.users[who],self.body('request_approve',request['revision'],external_request_id=request['id'])))['request']
    async def intent(self,request):
        return await self.runtime.command(self.user,self.body('request_intent',request['revision'],external_request_id=request['id']))
    async def test_tool_draft_schema_review_and_current_reference(self):
        saved=await self.runtime.command(self.user,self.body('tool_save',tool={'system_id':'EMS','kind':'request','name':'미완성'}))
        self.assertEqual(saved['tool']['state'],'draft')
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('tool_submit',1,tool_contract_id=saved['tool']['id']))
        contract=await self.make_contract();self.assertEqual(contract['state'],'approved')
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('tool_save',contract['revision'],tool={**contract,'input_schema':{'type':'object','properties':{'shell':{'type':'string'}}}}))
        self.assertEqual(error.exception.code,'native_schema_mismatch')
    async def test_read_attempt_snapshot_real_dispatch_and_human_completion(self):
        wid=await self.make_workflow();run=await self.start(wid)
        body=self.body('execute_job',1,run_id=run['run_id'],job_id='j1')
        result=await self.runtime.command(self.user,body)
        self.assertEqual(result['attempt']['status'],'succeeded')
        self.assertEqual(self.bridge.calls[0][1],{'target':'synthetic-target'})
        with self.service._db() as db:
            job=db.execute('SELECT * FROM work_jobs').fetchone(); attempt=db.execute('SELECT * FROM work_attempts').fetchone()
            self.assertEqual(job['status'],'waiting_confirmation')
            self.assertEqual(json.loads(attempt['inputs']),{'target':'synthetic-target'})
        await self.runtime.command(self.user,body)
        self.assertEqual(len(self.bridge.calls),1)
        self.bridge.allowed=False
        with self.assertRaises(workflow.WorkflowError): await self.runtime.command(self.user,body)
    async def test_partial_never_success_and_retry_keeps_previous_attempt(self):
        wid=await self.make_workflow();run=await self.start(wid)
        self.bridge.result['completeness']='partial'
        result=await self.runtime.command(self.user,self.body('execute_job',1,run_id=run['run_id'],job_id='j1'))
        self.assertEqual(result['attempt']['status'],'partial')
        self.bridge.result['completeness']='complete'
        await self.runtime.command(self.user,self.body('execute_job',3,run_id=run['run_id'],job_id='j1'))
        with self.service._db() as db:
            rows=db.execute('SELECT status FROM work_attempts ORDER BY number').fetchall()
        self.assertEqual([row[0] for row in rows],['partial','succeeded'])
    async def test_zero_approval_still_requires_short_lived_actor_bound_intent(self):
        run,request=await self.prepare()
        connector=Connector();self.runtime.connector=connector
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],confirmed=True,source='panel'))
        intent=await self.intent(request)
        self.now += ops.INTENT_TTL+1
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        self.assertEqual(error.exception.code,'confirmation_expired');self.assertEqual(connector.calls,[])
        state=await self.runtime.state(self.user,run_id=run['run_id'])
        self.assertNotIn(intent['intent_token'],json.dumps(state))
    async def test_two_distinct_current_approvers_and_content_change_invalidates(self):
        run,request=await self.prepare(2)
        with self.assertRaises(workflow.WorkflowError) as error: await self.approve(request,'alice')
        self.assertEqual(error.exception.code,'self_approval_forbidden')
        request=await self.approve(request,'bob')
        with self.assertRaises(workflow.WorkflowError):await self.approve(request,'bob')
        with self.assertRaises(workflow.WorkflowError):await self.intent(request)
        request=await self.approve(request,'carol');self.assertEqual(request['state'],'ready')
        intent=await self.intent(request)
        await self.core('save_inputs',1,run_id=run['run_id'],inputs={'target':'changed'})
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        self.assertEqual(error.exception.code,'request_stale')
    async def test_unconfigured_connector_explicit_block_and_no_fake_success(self):
        run,request=await self.prepare();intent=await self.intent(request)
        result=await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        self.assertFalse(result['ok']);self.assertEqual(result['request']['state'],'blocked')
        self.assertEqual(result['error']['code'],'ees_connector_unconfigured')
    async def test_unknown_not_redispatched_reconciliation_and_effect_separate(self):
        run,request=await self.prepare();connector=Connector();connector.lost=True;self.runtime.connector=connector
        intent=await self.intent(request);body=self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token'])
        result=await self.runtime.command(self.user,body);self.assertEqual(result['request']['state'],'unknown')
        with self.assertRaises(workflow.WorkflowError):await self.runtime.command(self.user,body)
        self.assertEqual(len(connector.calls),1)
        result=await self.runtime.command(self.user,self.body('request_reconcile',result['request']['revision'],external_request_id=request['id']))
        self.assertEqual(result['request']['state'],'unknown');self.assertEqual(result['request']['reason'],'effect_observation_unknown');self.assertFalse(result['request']['effect_verified'])
        connector.effect_ok=True
        result=await self.runtime.command(self.user,self.body('request_reconcile',result['request']['revision'],external_request_id=request['id']))
        self.assertEqual(result['request']['state'],'effect_verified');self.assertEqual(len(connector.calls),1)
    async def test_daily_schedule_unique_across_two_workers_and_no_delegation_block(self):
        wid=await self.make_workflow(periodic=True)
        schedule={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','interval':1,'timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':False}
        saved=await self.runtime.command(self.user,self.body('schedule_save',schedule=schedule))
        other=ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await asyncio.gather(self.runtime.process_once(),other.process_once())
        with self.service._db() as db:
            rows=db.execute('SELECT * FROM work_schedule_slots').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'blocked');self.assertEqual(self.bridge.calls,[])
        self.now += 86400+1000
        await self.runtime.process_once()
        with self.service._db() as db: states=[r[0] for r in db.execute('SELECT status FROM work_schedule_slots ORDER BY scheduled_at')]
        self.assertEqual(states,['blocked','missed'])
    async def test_delegated_schedule_actual_worker_pins_version_and_does_not_repeat(self):
        wid=await self.make_workflow(periodic=True)
        await self.runtime.command(self.user,self.body('schedule_save',schedule={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':True}))
        self.runtime.start()
        for _ in range(100):
            with self.service._db() as db: row=db.execute('SELECT status FROM work_schedule_slots').fetchone()
            if row and row[0] != 'running' and row[0] != 'queued': break
            await asyncio.sleep(.01)
        await self.runtime.stop()
        self.assertEqual(row[0],'succeeded');self.assertEqual(len(self.bridge.calls),1)
        restarted=ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await restarted.process_once();self.assertEqual(len(self.bridge.calls),1)
    async def test_one_approval_revoked_identity_blocks_final_dispatch(self):
        run,request=await self.prepare(1)
        request=await self.approve(request,'bob')
        intent=await self.intent(request)
        self.users['bob']['role']='pending'
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT consumed FROM work_request_intents').fetchone()[0],0)

    async def test_two_prepared_requests_cannot_dispatch_same_job_twice(self):
        run,request=await self.prepare()
        with self.service._db() as db:
            original=json.loads(db.execute('SELECT data FROM work_external_requests').fetchone()[0])
        duplicate=(await self.runtime.command(self.user,self.body('request_prepare',1,run_id=run['run_id'],job_id='j1',tool_contract_id=original['tool_contract_id'],inputs={'target':'synthetic-target'})))['request']
        intent1,intent2=await self.intent(request),await self.intent(duplicate)
        self.runtime.connector=Connector()
        await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent1['intent_token']))
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('request_dispatch',duplicate['revision'],external_request_id=duplicate['id'],intent_token=intent2['intent_token']))
        self.assertEqual(len(self.runtime.connector.calls),1)

    async def test_request_id_different_payload_atomic_conflict(self):
        body=self.body('tool_save',tool={'system_id':'EMS','kind':'request','name':'draft'})
        await self.runtime.command(self.user,body)
        changed=deepcopy(body);changed['tool']['name']='different'
        with self.assertRaises(workflow.WorkflowError) as error:await self.runtime.command(self.user,changed)
        self.assertEqual(error.exception.code,'request_conflict')
        with self.service._db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM work_tool_contracts').fetchone()[0],1)

    async def test_scheduled_read_lease_loss_never_redispatches(self):
        wid=await self.make_workflow(periodic=True)
        await self.runtime.command(self.user,self.body('schedule_save',schedule={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':True}))
        self.runtime._materialize();slot=self.runtime._claim_slot()
        self.now+=self.runtime.lease_seconds+1
        second=ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await second.process_once()
        with self.service._db() as db:self.assertEqual(db.execute('SELECT status FROM work_schedule_slots').fetchone()[0],'unknown')
        self.assertEqual(self.bridge.calls,[])

    async def test_future_job_time_and_same_cycle_restore(self):
        wid=await self.make_workflow(periodic=True)
        with self.service._db() as db: definition=json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?',(wid,)).fetchone()[0])
        definition['nodes']['j1']['trigger']={'offset_seconds':60}
        await self.core('save_draft',3,workflow_id=wid,definition=definition)
        await self.core('validate_workflow',4,workflow_id=wid)
        await self.core('publish_workflow',4,workflow_id=wid)
        await self.runtime.command(self.user,self.body('schedule_save',schedule={'workflow_id':wid,'version':2,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':True}))
        await self.runtime.process_once()
        with self.service._db() as db:
            slot=json.loads(db.execute('SELECT data FROM work_schedule_slots').fetchone()[0])
            self.assertEqual(slot['state'],'waiting');run_id=slot['run_id']
        self.assertEqual(self.bridge.calls,[])
        self.now+=60
        second=ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await second.process_once()
        with self.service._db() as db:
            slot=json.loads(db.execute('SELECT data FROM work_schedule_slots').fetchone()[0])
            self.assertEqual(slot['state'],'succeeded');self.assertEqual(slot['run_id'],run_id)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_runs').fetchone()[0],1)
        self.assertEqual(len(self.bridge.calls),1)

    async def test_schedule_identity_and_current_tool_revocation(self):
        wid=await self.make_workflow(periodic=True)
        base={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':True}
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('schedule_save',schedule={**base,'identity_user_id':'bob'}))
        self.assertEqual(error.exception.code,'schedule_identity_invalid')
        await self.runtime.command(self.user,self.body('schedule_save',schedule=base))
        self.bridge.allowed=False
        await self.runtime.process_once()
        with self.service._db() as db:self.assertEqual(db.execute('SELECT status FROM work_schedule_slots').fetchone()[0],'blocked')
        self.assertEqual(self.bridge.calls,[])
        state=await self.runtime.state(self.user)
        self.assertEqual(len(state['actionable']),1)

    async def test_private_schedule_not_visible_to_other_system_admin(self):
        wid=await self.make_workflow(periodic=True)
        await self.runtime.command(self.user,self.body('schedule_save',schedule={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'private-target'},'job_ids':[],'delegated':False}))
        self.assertEqual((await self.runtime.state(self.users['bob']))['schedules'],[])

    async def test_secret_inputs_rejected_before_storage(self):
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('tool_save',tool={'system_id':'EMS','kind':'request','name':'draft','PAT':'not-a-real-secret'}))
        self.assertEqual(error.exception.code,'secret_input_forbidden')
        with self.service._db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM work_tool_contracts').fetchone()[0],0)

    async def test_request_target_cannot_override_saved_inputs(self):
        run,request=await self.prepare()
        with self.service._db() as db: original=json.loads(db.execute('SELECT data FROM work_external_requests').fetchone()[0])
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('request_prepare',1,run_id=run['run_id'],job_id='j1',tool_contract_id=original['tool_contract_id'],inputs={'target':'hidden-other-target'}))
        self.assertEqual(error.exception.code,'request_input_mismatch')
        with self.service._db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM work_external_requests').fetchone()[0],1)

    async def test_queued_schedule_delegation_revocation_is_current(self):
        wid=await self.make_workflow(periodic=True)
        schedule={'workflow_id':wid,'version':1,'rule':{'frequency':'daily','timezone':'UTC','anchor':'2026-10-02T10:00:00'},'inputs':{'target':'synthetic-target'},'job_ids':['j1'],'delegated':True}
        saved=(await self.runtime.command(self.user,self.body('schedule_save',schedule=schedule)))['schedule']
        self.runtime._materialize()
        await self.runtime.command(self.user,self.body('schedule_save',saved['revision'],schedule={**saved,'delegated':False}))
        await self.runtime.process_once()
        with self.service._db() as db:
            slot=json.loads(db.execute('SELECT data FROM work_schedule_slots').fetchone()[0])
            self.assertEqual(slot['state'],'blocked');self.assertEqual(slot['reason'],'schedule_delegation_revoked')
        self.assertEqual(self.bridge.calls,[])

    async def test_receipt_read_rechecks_group_after_native_await(self):
        wid=await self.make_workflow();run=await self.start(wid)
        body=self.body('execute_job',1,run_id=run['run_id'],job_id='j1')
        await self.runtime.command(self.users['bob'],body)
        check=self.bridge.check
        async def revoke_after_check(user,ref):
            result=await check(user,ref)
            self.service.group_lookup=lambda actor: []
            return result
        self.bridge.check=revoke_after_check
        with self.assertRaises(workflow.WorkflowError) as error:await self.runtime.command(self.users['bob'],body)
        self.assertEqual(error.exception.code,'run_not_found')
        self.assertEqual(len(self.bridge.calls),1)

    async def test_effect_probe_rechecks_access_after_status_read(self):
        run,request=await self.prepare();connector=Connector();self.runtime.connector=connector
        intent=await self.intent(request)
        result=await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        status=connector.status;effect_calls=[]
        async def revoke_after_status(*args):
            result=await status(*args);self.bridge.allowed=False;return result
        async def effect(*args):effect_calls.append(args);return {'satisfied':True,'evidence':['never']}
        connector.status=revoke_after_status;connector.effect=effect
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('request_reconcile',result['request']['revision'],external_request_id=request['id']))
        self.assertEqual(error.exception.code,'native_access_denied');self.assertEqual(effect_calls,[])

    async def test_change_request_cannot_use_generic_human_completion(self):
        run,request=await self.prepare()
        result=await self.service.workspace_command(self.user,self.body('human_confirm',1,run_id=run['run_id'],job_id='j1'))
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'request_confirmation_required')
        connector=Connector();connector.lost=True;self.runtime.connector=connector
        intent=await self.intent(request)
        observed=await self.runtime.command(self.user,self.body('request_dispatch',request['revision'],external_request_id=request['id'],intent_token=intent['intent_token']))
        with self.service._db() as db: revision=db.execute('SELECT revision FROM work_runs').fetchone()[0]
        decision=await self.service.workspace_command(self.user,self.body('decide',revision,run_id=run['run_id'],job_id='j1',result_revision=1,verdict='completed'))
        self.assertFalse(decision['ok']);self.assertEqual(decision['error']['code'],'request_effect_unconfirmed')
        cancel=await self.service.workspace_command(self.user,self.body('cancel_run',revision,run_id=run['run_id'],reason='test cancellation'))
        self.assertFalse(cancel['ok']);self.assertEqual(cancel['error']['code'],'external_request_unresolved')
        connector.effect_ok=True
        await self.runtime.command(self.user,self.body('request_reconcile',observed['request']['revision'],external_request_id=request['id']))
        with self.service._db() as db: revision=db.execute('SELECT revision FROM work_runs').fetchone()[0]
        decision=await self.service.workspace_command(self.user,self.body('decide',revision,run_id=run['run_id'],job_id='j1',result_revision=1,verdict='completed'))
        self.assertTrue(decision['ok'],decision)
        with self.service._db() as db:self.assertEqual(db.execute('SELECT status FROM work_jobs').fetchone()[0],'completed')

    async def test_actual_native_normalizer_drives_common_items_and_completion(self):
        native=importlib.import_module(package.__name__+'.ees_workflow_native')
        ref={**REF,'function':'jira_search_crs'}
        raw={'ok':True,'status':'complete','issues':[{'key':'SYN-1','summary':'변경 검토','url':'https://jira.invalid/browse/SYN-1'}], 'listing':{'ok':True,'start_at':0,'total':1,'returned':1,'next_start_at':None}}
        self.bridge.result=native.normalize_result('jira_search_crs',raw,ref,{})
        self.assertEqual(self.bridge.result['status'],'succeeded')
        self.assertEqual(self.bridge.result['items'][0]['id'],'SYN-1')
        wid=await self.make_workflow();run=await self.start(wid)
        result=await self.runtime.command(self.user,self.body('execute_job',1,run_id=run['run_id'],job_id='j1'))
        self.assertEqual(result['attempt']['status'],'succeeded')
        self.assertEqual(result['attempt']['result']['items'][0]['label'],'변경 검토')
        raw['listing'].update(total=2,next_start_at=1)
        partial=native.normalize_result('jira_search_crs',raw,ref,{})
        self.assertEqual(partial['completeness'],'partial')

    async def chain(self, emergency=False, second_mode='tool', block='human_confirm', result_binding=False):
        wid = await self.make_workflow()
        with self.service._db() as db:
            definition = json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?', (wid,)).fetchone()[0])
        definition['mode'] = 'emergency' if emergency else 'on_demand'
        definition['nodes']['t1']['children'].append('j2')
        second = deepcopy(definition['nodes']['j1'])
        second.update(id='j2', name='후속 작업', deps=['j1'], mode=second_mode, result_block=block)
        if second_mode == 'ai':
            second.pop('tool_reference'); second.pop('argument_bindings')
            second['result_source_job_id'] = 'j1'
            second['instructions'] = '제공된 현재 근거만 검토하고 미확인을 유지하세요.'
        if result_binding:
            second['argument_bindings'] = {'issue_keys': {'result': {'job_id':'j1','path':['items'],'value_field':'id','confirmed':True}}}
        if second_mode == 'ai' or result_binding:
            definition['nodes']['j1']['result_block'] = 'list_confirm'
        definition['nodes']['j2'] = second
        await self.core('save_draft',3,workflow_id=wid,definition=definition)
        checked = await self.core('validate_workflow',4,workflow_id=wid)
        self.assertEqual(checked['validation']['errors'], [])
        await self.core('publish_workflow',4,workflow_id=wid)
        run = await self.core('start_run',5,workflow_id=wid,inputs={'target':'synthetic-target'},sharing={'group_ids':['team']})
        return run

    async def confirm_current(self, run_id, job_id='j1', item_id='job', verdict='completed'):
        with self.service._db() as db:
            revision = db.execute('SELECT revision FROM work_runs WHERE id=?', (run_id,)).fetchone()[0]
            number = db.execute('SELECT a.number FROM work_jobs j JOIN work_attempts a ON a.id=j.current_attempt WHERE j.run_id=? AND j.job_id=?', (run_id,job_id)).fetchone()[0]
        return await self.core('decide',revision,run_id=run_id,job_id=job_id,item_id=item_id,verdict=verdict,result_revision=number)

    async def test_scope_restarts_and_waits_for_human_then_same_dependency_executor(self):
        run = await self.chain()
        body = self.body('execute_scope',1,run_id=run['run_id'],node_id='t1')
        accepted = await self.runtime.command(self.user,body)
        duplicate = await self.runtime.command(self.user,body)
        self.assertEqual(accepted['scope']['id'],duplicate['scope']['id'])
        await self.runtime.process_once(); await self.runtime.process_once()
        self.assertEqual(len(self.bridge.calls),1)
        state = await self.runtime.state(self.user,run_id=run['run_id'])
        self.assertEqual(state['scope_runs'][0]['status'],'waiting')
        restarted = ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await restarted.process_once(); self.assertEqual(len(self.bridge.calls),1)
        await self.confirm_current(run['run_id'])
        await restarted.process_once(); self.assertEqual(len(self.bridge.calls),2)
        await self.confirm_current(run['run_id'],'j2')
        await restarted.process_once()
        state = await restarted.state(self.user,run_id=run['run_id'])
        self.assertEqual(state['scope_runs'][0]['status'],'completed')

    async def test_scope_current_identity_and_lost_lease_never_dispatch(self):
        run = await self.chain()
        accepted = await self.runtime.command(self.user,self.body('execute_scope',1,run_id=run['run_id'],node_id='t1'))
        self.runtime._claim_scope(); self.now += self.runtime.lease_seconds+1
        restarted = ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await restarted.process_once()
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT status FROM work_scope_runs').fetchone()[0],'unknown')
        self.assertEqual(self.bridge.calls,[])
        await restarted.command(self.user,self.body('execute_scope',1,run_id=run['run_id'],node_id='t1'))
        self.users['alice']['role']='pending'
        await restarted.process_once()
        self.assertEqual(self.bridge.calls,[])
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM work_scope_runs WHERE status='blocked'").fetchone()[0],1)

    async def test_emergency_start_enqueues_read_and_never_replays_on_restart(self):
        run = await self.chain(emergency=True)
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM work_scope_runs').fetchone()[0],1)
        await self.runtime.process_once(); await self.runtime.process_once()
        self.assertEqual(len(self.bridge.calls),1)
        restarted=ops.OperationsRuntime(self.service,bridge=self.bridge,clock=lambda:self.now)
        await restarted.process_once(); self.assertEqual(len(self.bridge.calls),1)

    async def test_confirmed_list_binding_freezes_actual_ids_and_denies_unconfirmed(self):
        run = await self.chain(result_binding=True)
        self.bridge.result={'status':'succeeded','completeness':'complete','items':[{'id':'SYN-1','required':True},{'id':'SYN-2','required':True}]}
        await self.runtime.command(self.user,self.body('execute_job',1,run_id=run['run_id'],job_id='j1'))
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user,self.body('execute_job',3,run_id=run['run_id'],job_id='j2'))
        self.assertEqual(error.exception.code,'confirmed_result_required')
        await self.confirm_current(run['run_id'],item_id='SYN-1')
        await self.confirm_current(run['run_id'],item_id='SYN-2')
        with self.service._db() as db: revision=db.execute('SELECT revision FROM work_runs').fetchone()[0]
        result=await self.runtime.command(self.user,self.body('execute_job',revision,run_id=run['run_id'],job_id='j2'))
        self.assertEqual(self.bridge.calls[-1][1],{'issue_keys':['SYN-1','SYN-2']})
        self.assertEqual(result['attempt']['snapshot']['argument_sources']['issue_keys']['ids'],['SYN-1','SYN-2'])
        self.assertTrue(result['attempt']['snapshot']['evidence_attempt_ids'])

    async def test_ai_per_item_suggestions_are_not_human_decisions_and_keep_source_acl(self):
        run=await self.chain(second_mode='ai',block='item_verdict')
        self.bridge.result={'status':'succeeded','completeness':'complete','items':[{'id':'SYN-1','required':True,'content_reviewed':False}]}
        await self.runtime.command(self.user,self.body('execute_job',1,run_id=run['run_id'],job_id='j1'))
        await self.confirm_current(run['run_id'],item_id='SYN-1')
        class Model:
            async def resolve(self,actor,selected): return {'id':'synthetic','name':'합성 검증 모델','actor':'AI','parameters':{}}
            async def propose(self,actor,model_id,context,instruction):
                return {'ok':True,'context':{k:context[k] for k in ('context_id','target_id','revision','kind')},'proposal':[{'item_id':'SYN-1','verdict':'unknown','reason':'본문 검토 근거 없음'}]}
        self.runtime.model=Model()
        with self.service._db() as db: revision=db.execute('SELECT revision FROM work_runs').fetchone()[0]
        result=await self.runtime.command(self.user,self.body('execute_job',revision,run_id=run['run_id'],job_id='j2',model_id='synthetic'))
        self.assertEqual(result['attempt']['status'],'succeeded',result)
        self.assertFalse(result['attempt']['result']['items'][0]['content_reviewed'])
        self.assertEqual(result['attempt']['result']['items'][0]['ai_proposal']['verdict'],'unknown')
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM work_decisions WHERE job_id='j2'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT status FROM work_jobs WHERE job_id='j2'").fetchone()[0],'waiting_confirmation')
        self.bridge.allowed=False
        with self.assertRaises(workflow.WorkflowError):
            await self.service._work_check_evidence(self.user,{**result['attempt'],'actor_id':'alice'})

    async def test_request_output_schema_draft_is_preserved_but_invalid_submit_rejected(self):
        for schema in ('{}', {'type':'object','properties':[]}, {'type':'object','required':['missing']}, {'type':'object','properties':{'x':{'type':'shell'}}}, {'type':'object','$ref':'https://external.invalid/schema'}):
            with self.subTest(schema=schema):
                saved=await self.runtime.command(self.user,self.body('tool_save',tool={'system_id':'EMS','kind':'request','name':'검토 초안','reference':deepcopy(REQUEST_REF),'guide_url':'https://guide.invalid/function','responsible_user_id':'bob','status_function':'service_status','output_schema':schema}))
                self.assertEqual(saved['tool']['output_schema'],schema)
                with self.assertRaises(workflow.WorkflowError) as error:
                    await self.runtime.command(self.user,self.body('tool_submit',saved['tool']['revision'],tool_contract_id=saved['tool']['id']))
                self.assertEqual(error.exception.code,'request_output_schema_invalid')
        valid={'type':'object','properties':{'state':{'type':'string','enum':['accepted','failed']},'items':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'}}}}},'required':['state'],'additionalProperties':False}
        ops.validate_output_schema(valid)

    async def test_input_ai_preview_is_declared_scoped_and_never_saved(self):
        wid=await self.make_workflow();run=await self.start(wid)
        class Model:
            async def propose(self,actor,model_id,context,instruction):
                self.context=context
                return {'ok':True,'context':{key:context[key] for key in ('context_id','target_id','revision','kind')},'proposal':{'target':'suggested-only'}}
        model=Model();self.runtime.model=model
        body={'proposal_kind':'inputs','workflow_id':wid,'run_id':run['run_id'],'job_id':'j1','expected_revision':1,'context_id':'scope-a','inputs':{'target':'private-draft'},'prompt':'입력 초안 제안','model_id':'synthetic'}
        with patch.object(workflow,'_production_service',return_value=self.service):
            result=await workflow.workspace_proposal(self.user,body)
        self.assertTrue(result['ok'],result);self.assertFalse(result['saved']);self.assertFalse(result['executed'])
        self.assertEqual(result['proposal'],{'target':'suggested-only'})
        self.assertEqual(model.context['source']['current_inputs'],{'target':'private-draft'})
        self.assertEqual([field['id'] for field in model.context['fields']],['target'])
        with self.service._db() as db:
            stored=db.execute('SELECT * FROM work_runs').fetchone()
            self.assertEqual(stored['revision'],1);self.assertEqual(json.loads(stored['inputs']),{'target':'synthetic-target'})
            self.assertEqual(db.execute('SELECT count(*) FROM work_attempts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM work_request_intents').fetchone()[0],0)
        with patch.object(workflow,'_production_service',return_value=self.service):
            invalid=await workflow.workspace_input_preview(self.user,{**body,'proposal':{'undeclared':'x'}})
        self.assertFalse(invalid['ok'])

    async def test_input_ai_acl_or_revision_change_rejects_late_suggestion(self):
        wid=await self.make_workflow();run=await self.start(wid)
        body={'proposal_kind':'inputs','workflow_id':wid,'run_id':run['run_id'],'job_id':'j1','expected_revision':1,'context_id':'scope-a','prompt':'입력 제안','model_id':'synthetic'}
        runtime=self.runtime
        class Revoked:
            async def propose(self,actor,model_id,context,instruction):
                runtime.bridge.allowed=False
                return {'ok':True,'context':{key:context[key] for key in ('context_id','target_id','revision','kind')},'proposal':{'target':'late'}}
        self.runtime.model=Revoked()
        with patch.object(workflow,'_production_service',return_value=self.service):
            denied=await workflow.workspace_proposal(self.user,body)
        self.assertEqual(denied['error']['code'],'native_access_denied')
        self.bridge.allowed=True
        service=self.service
        class Changed:
            async def propose(self,actor,model_id,context,instruction):
                result=await service.workspace_command(actor,{'action':'save_inputs','run_id':run['run_id'],'expected_revision':1,'request_id':'during-proposal','inputs':{'target':'new'}})
                assert result['ok'],result
                return {'ok':True,'context':{key:context[key] for key in ('context_id','target_id','revision','kind')},'proposal':{'target':'late'}}
        self.runtime.model=Changed()
        with patch.object(workflow,'_production_service',return_value=self.service):
            stale=await workflow.workspace_proposal(self.user,body)
        self.assertEqual(stale['error']['code'],'revision_conflict')
        with self.service._db() as db:self.assertEqual(db.execute('SELECT count(*) FROM work_attempts').fetchone()[0],0)

    async def test_input_ai_dynamic_choices_use_private_draft_and_merged_proposal(self):
        fields=[{'id':'target','type':'text','scope':'run','required':True},
                {'id':'choice','type':'single','scope':'run','options_source':'tool','depends_on':['target'],
                 'options_query':{'reference':deepcopy(REF),'argument_bindings':{'target':{'input':'target'}},
                                  'result_path':['choices'],'value_field':'id','label_field':'name'}}]
        wid=await self.make_workflow(fields=fields);run=await self.start(wid)
        calls=[]
        async def choices(actor,reference,arguments,context):
            await self.bridge.check(actor,reference)
            calls.append(arguments['target'])
            return {'status':'succeeded','completeness':'complete','data':{'choices':[{'id':arguments['target'],'name':arguments['target']}]}}
        self.bridge.invoke=choices
        model_module=importlib.import_module(package.__name__+'.ees_workflow_model')
        class Model(model_module.NativeModelAdapter):
            proposal={'choice':'private-project'}
            async def resolve(self,actor,selected):
                return {'id':'synthetic','name':'Synthetic model transport','actor':'AI','parameters':{}}
            async def propose(self,actor,model_id,context,instruction):
                self.context=context
                return await super().propose(actor,model_id,context,instruction)
        model=Model(self.service,SimpleNamespace());self.runtime.model=model
        async def generate(request,form,actor,**kwargs):
            context=json.loads(form['messages'][-1]['content'])['context']
            return {'choices':[{'message':{'content':json.dumps({'context':context,'proposal':model.proposal})}}]}
        model_runtime=SimpleNamespace(Request=lambda scope:SimpleNamespace(state=SimpleNamespace()),generate=generate)
        body={'proposal_kind':'inputs','workflow_id':wid,'run_id':run['run_id'],'job_id':'j1','expected_revision':1,
              'context_id':'private-choice','inputs':{'target':'private-project'},'model_id':'synthetic','prompt':'현재 입력 초안을 제안해 주세요.'}
        with patch.object(workflow,'_production_service',return_value=self.service), patch.object(model_module,'_runtime',return_value=model_runtime):
            preview=await workflow.workspace_proposal(self.user,body)
            self.assertTrue(preview['ok'],preview)
            self.assertEqual(model.context['fields'][1]['options_source'],'tool')
            self.assertEqual(model.context['source']['fields'][1]['options'],[{'id':'private-project','name':'private-project'}])
            self.assertTrue(calls);self.assertEqual(set(calls),{'private-project'})
            model.proposal={'target':'proposed-project','choice':'proposed-project'}
            changed=await workflow.workspace_proposal(self.user,body)
            self.assertTrue(changed['ok'],changed)
            self.assertIn('proposed-project',calls)
            model.proposal={'target':'proposed-project','choice':'private-project'}
            wrong=await workflow.workspace_proposal(self.user,body)
            self.assertEqual(wrong['error']['code'],'model_result_invalid')
            # Native-chat suggestions pass the same candidate contract gate.
            wrong=await workflow.workspace_input_preview(self.user,{**body,'proposal':model.proposal})
            self.assertEqual(wrong['error']['code'],'model_result_invalid')
        self.assertNotIn('synthetic-target',calls)
        with self.service._db() as db:
            row=db.execute('SELECT inputs,revision FROM work_runs').fetchone()
            self.assertEqual(json.loads(row['inputs']),{'target':'synthetic-target'});self.assertEqual(row['revision'],1)
            self.assertEqual(db.execute('SELECT count(*) FROM work_attempts').fetchone()[0],0)

    async def test_input_ai_person_preview_requires_current_native_identity(self):
        fields=[{'id':'target','type':'text','scope':'run','required':True},{'id':'reviewer','type':'person','scope':'run'}]
        wid=await self.make_workflow(fields=fields);run=await self.start(wid)
        class Model:
            proposal={}
            async def propose(self,actor,model_id,context,instruction):
                return {'ok':True,'context':{key:context[key] for key in ('context_id','target_id','revision','kind')},'proposal':deepcopy(self.proposal)}
        model=Model();self.runtime.model=model
        body={'proposal_kind':'inputs','workflow_id':wid,'run_id':run['run_id'],'job_id':'j1','expected_revision':1,'context_id':'person-preview','model_id':'synthetic'}
        self.users['carol']['role']='pending'
        with patch.object(workflow,'_production_service',return_value=self.service):
            for person,code in (({'kind':'user','id':'invented'},'native_user_required'),({'kind':'user','id':'carol'},'native_user_required'),({'kind':'group','id':'missing'},'native_group_required')):
                with self.subTest(person=person):
                    model.proposal={'reviewer':person}
                    rejected=await workflow.workspace_proposal(self.user,body)
                    self.assertEqual(rejected['error']['code'],code)
                    rejected=await workflow.workspace_input_preview(self.user,{**body,'proposal':model.proposal})
                    self.assertEqual(rejected['error']['code'],code)
            model.proposal={'reviewer':{'kind':'user','id':'bob'}}
            accepted=await workflow.workspace_proposal(self.user,body)
            self.assertTrue(accepted['ok'],accepted);self.assertFalse(accepted['saved'])
        with self.service._db() as db:
            self.assertEqual(json.loads(db.execute('SELECT inputs FROM work_runs').fetchone()[0]),{'target':'synthetic-target'})
            self.assertEqual(db.execute('SELECT count(*) FROM work_request_intents').fetchone()[0],0)

    def test_operations_partial_schema_never_recreates_lost_history(self):
        with self.service._db(write=True) as db:
            db.execute('DROP TABLE work_operation_events')
        with self.assertRaises(workflow.WorkflowError) as error:
            ops.OperationsRuntime(self.service,bridge=self.bridge)
        self.assertEqual(error.exception.code,'workspace_upgrade_required')
        with self.service._db() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='work_operation_events'").fetchone())

    def test_calendar_timezones_month_end_and_dst_are_explicit(self):
        after=datetime(2026,1,31,10,tzinfo=timezone.utc).timestamp()
        result=ops.next_slot({'frequency':'monthly','timezone':'UTC','anchor':'2026-01-31T10:00:00'},after)
        self.assertEqual(datetime.fromtimestamp(result,timezone.utc).isoformat(),'2026-02-28T10:00:00+00:00')
        with self.assertRaises(workflow.WorkflowError):ops.next_slot({'frequency':'daily','timezone':'invented','anchor':'2026-01-31T10:00:00'},after)


if __name__=='__main__':unittest.main()
