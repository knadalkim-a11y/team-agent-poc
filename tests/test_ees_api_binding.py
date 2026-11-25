"""Catalog revisions, workflow bindings and published/running snapshots share one transaction."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
pkg = ModuleType('ees_test_api_binding')
pkg.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
sys.modules[pkg.__name__] = pkg
runtime = importlib.import_module(pkg.__name__ + '.ees_workflow')


class WorkflowApiBindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.admin = {'id':'test-admin', 'role':'admin'}
        self.service = runtime.WorkflowService(Path(directory.name)/'workflow.db', lambda _:self.admin, lambda _:None)

    def request(self, action, **props):
        return {'action':action, 'request_id':str(uuid4()), 'expected_revision':0, **props}

    async def api(self, action, **props):
        return await self.service.api_catalog.command(self.admin, self.request(action, **props))

    async def work(self, action, **props):
        return await self.service.workspace_command(self.admin, self.request(action, **props))

    async def prepare(self):
        api = {'name':'알람 조회','purpose':'알람 정보 확인','method':'GET','url':'https://ems.example/alarms',
               'inputs':[], 'result_path':'records', 'fields':[{'path':'code','type':'string','label':'알람 코드'}]}
        query = (await self.api('api_save',api=api,service_name='EMS'))['api']
        command = (await self.api('api_save',api={**api,'name':'알람 등록','method':'POST','service_id':query['service_id'],
            'inputs':[{'name':'code','in':'body','label':'알람 코드','type':'string','required':True}]}))['api']
        wf = (await self.work('create_workflow',system_id='EMS',name='알람 처리'))['workflow']
        definition = wf['draft']
        nodes = definition['nodes']
        root = next(iter(nodes))
        nodes[root]['children'] = ['checks']
        nodes['checks'] = {'id':'checks','type':'t','name':'확인','parent':root,'children':['lookup','confirm'],'deps':[]}
        nodes['lookup'] = {'id':'lookup','type':'j','name':'조회','parent':'checks','children':[],'deps':[],
            'mode':'tool','result_block':'list_confirm','api_binding':{'operation_id':query['id'],'version':1,'inputs':{},'outputs':['code']}}
        nodes['confirm'] = deepcopy(nodes['lookup'])
        nodes['confirm'].update(id='confirm',name='등록',deps=['lookup'],result_block='change_request',
            api_binding={'operation_id':command['id'],'version':1,'inputs':{'code':{'result':{'confirmed':True,'job_id':'lookup','field':'code'}}},'outputs':[]})
        saved = await self.work('save_draft',workflow_id=wf['id'],expected_revision=1,definition=definition,publication_state='published')
        self.assertTrue(saved['ok'],saved)
        return query, wf['id'], definition

    async def test_apply_field_repair_atomically_and_keep_previous_publication_and_run(self):
        query, wf, definition = await self.prepare()
        run = await self.work('start_run',workflow_id=wf,expected_revision=2)
        self.assertTrue(run['ok'],run)
        changed = {**query,'fields':[{'path':'alarmCode','label':'알람 코드','type':'string'}]}
        preview = (await self.api('api_change_preview',api=changed))['operation']
        draft = next(u for u in preview['uses'] if u['kind']=='draft')
        self.assertEqual(draft['dependent_inputs'][0]['field'],'code')
        repair = {'workflow_id':wf,'expected_revision':2,'fields':{'code':'alarmCode'}}
        for repairs in ([], [{**repair,'expected_revision':1}], [{**repair,'fields':{'code':'missing'}}]):
            with self.assertRaises(runtime.WorkflowError):
                await self.api('api_save',api=changed,expected_revision=1,repairs=repairs)
            with self.service._db() as db:
                self.assertEqual(self.service.api_catalog.resolve(db,query['id'],groups=[])['version'],1)
        await self.api('api_save',api=changed,expected_revision=1,repairs=[repair])
        with self.service._db() as db:
            current = db.execute('SELECT * FROM work_definitions WHERE id=?',(wf,)).fetchone()
            updated = json.loads(current['draft'])['nodes']
            published = json.loads(db.execute('SELECT definition FROM work_versions WHERE workflow_id=? AND version=1',(wf,)).fetchone()[0])
            active = json.loads(db.execute('SELECT snapshot FROM work_runs WHERE id=?',(run['run_id'],)).fetchone()[0])['definition']
        self.assertEqual(current['revision'],3)
        self.assertEqual(updated['lookup']['api_binding']['outputs'],['alarmCode'])
        self.assertEqual(updated['confirm']['api_binding']['inputs']['code']['result']['field'],'alarmCode')
        self.assertEqual(updated['lookup']['api_binding']['version'],2)
        for snapshot in (published,active):
            self.assertEqual(snapshot['nodes']['lookup']['api_binding'],definition['nodes']['lookup']['api_binding'])
            self.assertEqual(snapshot['nodes']['confirm']['api_binding'],definition['nodes']['confirm']['api_binding'])

    async def test_reject_forged_source_and_copy_existing_job_references(self):
        _, wf, definition = await self.prepare()
        for key, value in [('confirmed',False),('job_id','confirm'),('field','not-a-field')]:
            bad = deepcopy(definition)
            bad['nodes']['confirm']['api_binding']['inputs']['code']['result'][key]=value
            failed = await self.work('save_draft',workflow_id=wf,expected_revision=2,definition=bad)
            self.assertFalse(failed['ok'])
        copied = await self.work('copy_workflow',workflow_id=wf,system_id='EMS',expected_revision=2)
        self.assertTrue(copied['ok'],copied)
        copied_nodes=copied['workflow']['draft']['nodes']
        source=next(n for n in copied_nodes.values() if n['name']=='조회')
        target=next(n for n in copied_nodes.values() if n['name']=='등록')
        self.assertNotEqual(source['id'],'lookup')
        self.assertEqual(source['id'],target['api_binding']['inputs']['code']['result']['job_id'])

    async def test_removing_a_field_can_move_dependent_inputs_to_runtime_prompt(self):
        query, wf, definition = await self.prepare()
        await self.api('api_save',api={**query,'fields':[]},expected_revision=1,repairs=[
            {'workflow_id':wf,'expected_revision':2,'fields':{'code':'@manual'}}])
        with self.service._db() as db:
            previous = json.loads(db.execute('SELECT definition FROM work_versions WHERE workflow_id=?',(wf,)).fetchone()[0])
            nodes = json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?',(wf,)).fetchone()[0])['nodes']
        self.assertEqual(previous['nodes']['confirm']['api_binding'],definition['nodes']['confirm']['api_binding'])
        self.assertEqual(nodes['lookup']['api_binding']['outputs'],[])
        field_id = nodes['confirm']['api_binding']['inputs']['code']['input']
        self.assertEqual([(f['id'],f['type'],f['scope']) for f in nodes['confirm']['inputs']],[(field_id,'text','run')])
