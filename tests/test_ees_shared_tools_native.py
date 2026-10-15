"""#92 phase 1: real Native source/ACL/Valves and SQLite, synthetic Confluence HTTP."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from test_ees_workflow_native import Response, WHEEL


class SharedToolsNativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not WHEEL.is_file():
            if os.environ.get('EES_REQUIRE_ASSET_NATIVE') == '1': self.fail('Pinned Native wheel unavailable')
            self.skipTest('Pinned Native wheel unavailable')
        from ees_workflow_native_fixture import NativeReadFixture
        self.f = NativeReadFixture(WHEEL)
        self.addAsyncCleanup(self.f.close)
        await self.f.start()
        self.admin, self.reader = self.f.users['admin'], self.f.users['reader']
        self.group = await self.f.native_groups.Groups.insert_new_group('admin', self.f.native_groups.GroupForm(name='Readers', description='Synthetic test group'))
        await self.f.native_groups.Groups.add_users_to_group(self.group.id, ['admin', 'reader'])
        self.service = self.f.workflow.WorkflowService(self.f.directory/'shared.sqlite3', self.f.native_users.Users.get_user_by_id, lambda _: None,
            group_lookup=self.f.native_groups.Groups.get_groups_by_member_id, group_list_lookup=lambda: [self.group])
        self.f.service = self.service
        self.f.bridge = self.f.native.NativeBridge(self.service, self.f.app)
        self.service.operations.bridge = self.f.bridge
        self.service.execution.bridge = self.f.bridge
        self.tools = self.service.shared_tools
        self.key = 'managed-search_pages'
        self.counter = 0
        self.http_calls = []
        self.refs = await self.f.register_read_tool('confluence', identifier='installed-with-unpredictable-id')
        self.addAsyncCleanup(self.service.operations.stop)

    def body(self, action, revision=0, **fields):
        self.counter += 1
        return dict(action=action, expected_revision=revision, request_id='shared-test-'+str(self.counter), **fields)

    async def item(self, key=None, actor=None):
        return next(item for item in await self.tools.list(actor or self.admin) if item['id'] == (key or self.key))

    async def review(self, key=None):
        item = await self.item(key)
        result = await self.tools.command(self.admin, self.body('shared_tool_review', item['revision'], shared_tool_id=item['id'], reference=item['observed_reference'], group_ids=[self.group.id], responsible_user_id='admin', evidence='합성 Native 원본과 입력·결과·설정 확인 완료'))
        self.assertTrue(result['ok'], result)
        return await self.item(key)

    async def assert_code(self, code, operation):
        with self.assertRaises(self.f.native.WorkflowError) as raised: await operation
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    async def core(self, action, revision=0, actor=None, **fields):
        result = await self.service.workspace_command(actor or self.admin, self.body(action, revision, **fields))
        self.assertTrue(result['ok'], result)
        return result

    async def workflow(self, system='EMS', key=None, periodic=False, legacy=None):
        key = key or self.key
        created = await self.core('create_workflow', system_id=system, name=system+' 조회 절차', mode='periodic' if periodic else 'on_demand')
        wid = created['workflow_id']
        with self.service._db() as db: definition = json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?', (wid,)).fetchone()[0])
        parent = next(iter(definition['nodes']))
        definition['nodes'][parent]['children'] = ['t1']
        definition['nodes']['t1'] = dict(id='t1', type='t', name='조회', parent=parent, children=['j1'], deps=[])
        job = dict(id='j1', type='j', name='페이지 조회', parent='t1', children=[], deps=[], mode='tool', inputs=[], result_block='list_confirm' if key.endswith('search_pages') else 'human_confirm', human_confirmation=True,
                   shared_tool_id=key, argument_bindings={'query': {'constant': 'guide'}} if key.endswith('search_pages') else {'page_id': {'constant': '123'}})
        if legacy:
            job.pop('shared_tool_id')
            job.update(tool_reference=legacy['reference'], tool_contract_id=legacy['id'], tool_contract_revision=legacy['revision'])
        definition['nodes']['j1'] = job
        await self.core('save_draft', 1, workflow_id=wid, definition=definition)
        validated = await self.core('validate_workflow', 2, workflow_id=wid)
        self.assertEqual(validated['validation']['errors'], [])
        await self.core('publish_workflow', 2, workflow_id=wid)
        await self.core('save_access', system_id=system, factory_id='*', principal_kind='user', principal_id='reader', roles=['manager', 'participant'])
        return wid

    async def start(self, wid, actor=None):
        return await self.core('start_run', 3, actor=actor, workflow_id=wid, inputs={}, sharing={'group_ids':[self.group.id]})

    def http(self, request, timeout=None):
        self.http_calls.append(request.get_header('Authorization'))
        page = dict(id='123', title='Guide '+request.get_header('Authorization'), type='page', status='current', space={'key':'EMS'}, version={'number':1}, body={'storage':{'value':getattr(self, 'page_body', '<p>Guide</p>')}})
        return Response({'results':[page]} if request.full_url.split('?')[0].endswith('/search') else page)

    async def execute(self, run, revision=1, actor=None):
        with patch('urllib.request.OpenerDirector.open', side_effect=self.http):
            return await self.service.operations.command(actor or self.reader, self.body('execute_job', revision, run_id=run['run_id'], job_id='j1'))

    async def test_two_systems_share_action_with_real_native_pat_and_run_resolution(self):
        item = await self.review()
        self.assertEqual(item['version'], 1)
        self.assertEqual(item['reference']['tool_id'], 'installed-with-unpredictable-id')
        self.assertEqual(item['reference'], self.refs['search_pages']) # reuse Native approval
        for system in ('EMS', 'FDC'):
            wid = await self.workflow(system)
            run = await self.start(wid, self.reader)
            result = await self.execute(run)
            self.assertEqual(result['attempt']['status'], 'partial', result)
            with self.service._db() as db:
                saved = db.execute('SELECT * FROM work_attempts WHERE run_id=?', (run['run_id'],)).fetchone()
                snapshot, output = json.loads(saved['snapshot']), json.loads(saved['result'])
            self.assertEqual(snapshot['shared_tool']['version'], 1)
            self.assertEqual(snapshot['shared_tool']['reference'], item['reference'])
            self.assertEqual(output['items'][0]['id'], '123')
            self.assertEqual(set(output['items'][0]), {'id','title','url'})
            self.assertEqual(output['scope'], 'single_page')
            self.assertNotIn('synthetic-reader-pat', json.dumps(dict(saved)))
        self.assertTrue(self.http_calls)
        self.assertEqual(set(self.http_calls), {'Bearer synthetic-reader-pat'})

    async def test_groups_disable_enable_and_unknown_source_never_dispatch_or_write_native(self):
        item = await self.review()
        self.assertEqual(await self.tools.list(self.f.users['outsider'], usable_only=True), [])
        await self.f.native_users.Users.update_user_by_id('outsider', {'role':'admin'})
        admin_outside=await self.f.native_users.Users.get_user_by_id('outsider')
        self.assertFalse((await self.item(actor=admin_outside))['can_use'])
        self.assertEqual(await self.tools.list(admin_outside, usable_only=True, summary=True), [])
        await self.assert_code('shared_tool_forbidden', self.tools.resolve(self.f.users['outsider'], self.key))
        wid = await self.workflow()
        run = await self.start(wid, self.reader)
        await self.tools.command(self.admin, self.body('shared_tool_disable', item['revision'], shared_tool_id=self.key, reference=item['observed_reference']))
        await self.assert_code('shared_tool_disabled', self.execute(run))
        disabled = await self.item()
        await self.tools.command(self.admin, self.body('shared_tool_enable', disabled['revision'], shared_tool_id=self.key, reference=disabled['observed_reference']))
        result = await self.execute(run)
        self.assertEqual(result['attempt']['status'], 'partial')
        tool = await self.f.tools.Tools.get_tool_by_id(item['reference']['tool_id'])
        await self.f.tools.Tools.update_tool_by_id(tool.id, {'content': tool.content+'\n# locally modified unknown source\n'})
        unknown = await self.item()
        self.assertEqual(unknown['state'], 'unavailable')
        before = self.service.database.read_bytes()
        with patch.object(self.f.tools.Tools, 'update_tool_by_id', side_effect=AssertionError('No product Native writes')):
            await self.assert_code('shared_tool_unavailable', self.review())
            await self.assert_code('shared_tool_unavailable', self.tools.resolve(self.reader, self.key))
        self.assertEqual(self.service.database.read_bytes(), before)
        self.assertEqual((await self.f.tools.Tools.get_tool_by_id(tool.id)).content, tool.content+'\n# locally modified unknown source\n')

    async def test_configuration_drift_rereview_without_republication_and_human_run_upgrade(self):
        await self.review()
        wid = await self.workflow()
        old_run = await self.start(wid, self.reader)
        await self.f.tools.Tools.update_tool_valves_by_id('installed-with-unpredictable-id', {'ENABLED':True,'CONFLUENCE_BASE_URL':'https://confluence.invalid','ALLOWED_SPACES':'EMS,FDC','TIMEOUT_SECONDS':2})
        self.assertEqual((await self.item())['state'], 'review_required')
        await self.assert_code('shared_tool_review_required', self.execute(old_run))
        revised = await self.review()
        self.assertEqual(revised['version'], 2)
        await self.assert_code('shared_tool_version_changed', self.execute(old_run))
        new_run = await self.start(wid, self.reader)
        self.assertEqual((await self.execute(new_run))['attempt']['snapshot']['shared_tool']['version'], 2)
        await self.tools.accept_version(self.reader, self.body('shared_tool_accept_version', 1, run_id=old_run['run_id'], shared_tool_id=self.key, version=2))
        self.assertEqual((await self.execute(old_run, 2))['attempt']['snapshot']['shared_tool']['version'], 2)
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM work_versions WHERE workflow_id=?', (wid,)).fetchone()[0],1)

    async def test_all_managed_functions_have_separate_entries_without_auto_install(self):
        items=await self.tools.list(self.admin)
        self.assertEqual({item['function'] for item in items},set(self.f.native.FUNCTIONS))
        self.assertEqual(len({item['id'] for item in items}),10)
        self.assertEqual({item['target'] for item in items},{'Confluence','Jira','GitHub'})
        self.assertEqual(sum(item['state']=='unavailable' for item in items),8)
        installed=await self.f.bridge.managed_tools()
        self.assertEqual([item['id'] for item in installed],['installed-with-unpredictable-id'])

    async def test_review_requires_explicit_groups_and_evidence_and_replay_is_readonly(self):
        item=await self.item()
        base=dict(shared_tool_id=self.key,reference=item['observed_reference'],responsible_user_id='admin')
        await self.assert_code('shared_tool_forbidden',self.tools.command(self.admin,self.body('shared_tool_review',group_ids=[],evidence='충분한 합성 검토 근거',**base)))
        await self.assert_code('native_approval_evidence_required',self.tools.command(self.admin,self.body('shared_tool_review',group_ids=[self.group.id],evidence='',**base)))
        with self.service._db() as db:self.assertEqual(db.execute('SELECT count(*) FROM work_shared_tools').fetchone()[0],0)
        request=self.body('shared_tool_review',group_ids=[self.group.id],evidence='충분한 합성 검토 근거',**base)
        await self.tools.command(self.admin,request)
        before=self.service.database.read_bytes()
        await self.tools.command(self.admin,request)
        self.assertEqual(self.service.database.read_bytes(),before)

    async def test_required_shape_change_refused_missing_install_and_summary_allowlist(self):
        item = await self.review()
        tool = await self.f.tools.Tools.get_tool_by_id(item['reference']['tool_id'])
        specs = deepcopy(tool.specs)
        specs[0]['parameters']['required'].append('space_key')
        await self.f.tools.Tools.update_tool_by_id(tool.id, {'specs':specs})
        await self.assert_code('shared_tool_breaking_change', self.review())
        await self.f.tools.Tools.update_tool_by_id(tool.id, {'specs':tool.specs})
        summary = await self.tools.list(self.reader, usable_only=True, summary=True)
        self.assertEqual(set(summary[0]), {'id','name','target','description','input_schema','output_schema','state'})
        for forbidden in ('hash','reference','config','responsible_user','group_ids','synthetic-reader-pat','default'):
            self.assertNotIn(forbidden, json.dumps(summary))
        with patch.object(self.f.bridge, 'managed_tools', return_value=[]):
            await self.assert_code('shared_tool_unavailable', self.review())
        with self.service._db() as db: self.assertEqual(db.execute('SELECT count(*) FROM work_shared_tool_versions').fetchone()[0],1)

    async def test_get_page_evidence_truncation_and_pat_guidance(self):
        key = 'managed-get_page'
        item = await self.review(key)
        wid = await self.workflow(key=key)
        run = await self.start(wid, self.reader)
        result = await self.execute(run)
        self.assertEqual(result['attempt']['result']['result_kind'], 'evidence')
        self.assertNotIn('items', result['attempt']['result'])
        self.page_body = '<p>' + '가' * 13000 + '</p>'
        truncated_run = await self.execute(await self.start(wid, self.reader))
        self.assertEqual(truncated_run['attempt']['result']['completeness'], 'truncated')
        self.assertEqual(truncated_run['attempt']['result']['result_kind'], 'evidence')
        self.assertNotIn('items', truncated_run['attempt']['result'])
        for code in ('pat_required','encryption_required','authentication_failed'):
            result = self.f.native.normalize_result('get_page', {'ok':False,'error':{'code':code,'message':'synthetic-reader-pat'}}, item['reference'], {}, ('synthetic-reader-pat',))
            self.assertNotIn('synthetic-reader-pat', json.dumps(result))
            self.assertTrue(result['error']['message'])
        truncated = self.f.native.normalize_result('get_page', {'ok':True,'page':{'page_id':'123','url':'https://confluence.invalid/123'},'content':'Excerpt','truncated':True}, item['reference'], {})
        self.assertEqual(truncated['completeness'],'truncated')
        await self.f.tools.Tools.update_user_valves_by_id_and_user_id(item['reference']['tool_id'], 'reader', {'PAT':''})
        error = await self.assert_code('native_personal_connection_required', self.tools.resolve(self.reader,key))
        self.assertIn('개인 PAT', str(error))

    async def test_automatic_schedule_uses_delegating_identity_pat(self):
        await self.review()
        wid = await self.workflow(periodic=True)
        now = datetime(2026,10,15,10,tzinfo=timezone.utc).timestamp()
        self.service.operations.clock = lambda: now
        schedule = dict(workflow_id=wid, version=1, rule={'frequency':'daily','timezone':'UTC','anchor':'2026-10-15T10:00:00'}, inputs={}, job_ids=['j1'], delegated=True, sharing={'group_ids':[self.group.id]})
        result = await self.service.operations.command(self.reader, self.body('schedule_save', schedule=schedule))
        self.assertEqual(result['schedule']['identity_user_id'], 'reader')
        with patch('urllib.request.OpenerDirector.open', side_effect=self.http): await self.service.operations.process_once()
        self.assertEqual(set(self.http_calls), {'Bearer synthetic-reader-pat'})
        with self.service._db() as db:
            attempt = db.execute('SELECT snapshot FROM work_attempts').fetchone()
            self.assertEqual(json.loads(attempt[0])['shared_tool']['version'],1)

    async def test_legacy_contract_remains_system_scoped_and_revision_pinned(self):
        await self.review()
        runtime = self.service.operations
        tool = (await runtime.command(self.admin,self.body('tool_save',tool={'system_id':'EMS','kind':'read','name':'이전 방식 페이지 조회','reference':self.refs['search_pages'],'guide_url':'https://guide.invalid/read'})))['tool']
        tool = (await runtime.command(self.admin,self.body('tool_submit',tool['revision'],tool_contract_id=tool['id'])))['tool']
        tool = (await runtime.command(self.admin,self.body('tool_review',tool['revision'],tool_contract_id=tool['id'],decision='approve')))['tool']
        wid = await self.workflow(legacy=tool)
        run = await self.start(wid,self.reader)
        result = await self.execute(run)
        self.assertNotIn('shared_tool',result['attempt']['snapshot'])
        self.assertEqual(result['attempt']['snapshot']['job']['tool_contract_revision'],tool['revision'])
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM work_shared_tool_pins WHERE run_id=?',(run['run_id'],)).fetchone()[0],0)
            stored = runtime._tool(db,tool['id'])
            self.assertEqual(stored['system_id'],'EMS')
            self.assertEqual(stored['revision'],tool['revision'])

    async def test_environment_and_managed_program_update_need_new_review(self):
        import hashlib
        await self.review()
        wid = await self.workflow()
        # A trusted new program release changes the managed manifest; arbitrary
        # installed edits without this manifest remain unavailable (separate test).
        tool = await self.f.tools.Tools.get_tool_by_id('installed-with-unpredictable-id')
        source = tool.content+'\n# simulated next managed program release\n'
        await self.f.tools.Tools.update_tool_by_id(tool.id,{'content':source})
        with patch.dict(self.f.native.MANAGED_READ_SOURCE_HASHES,{'confluence':hashlib.sha256(source.encode('utf-8')).hexdigest()}):
            self.assertEqual((await self.item())['state'],'review_required')
            await self.assert_code('shared_tool_review_required',self.tools.resolve(self.reader,self.key))
            revised = await self.review()
            self.assertEqual(revised['version'],2)
            self.assertEqual((await self.execute(await self.start(wid,self.reader)))['attempt']['snapshot']['shared_tool']['version'],2)
            env = sys.modules['open_webui.env']
            with patch.object(env,'VERSION',env.VERSION+'.environment-change'):
                self.assertEqual((await self.item())['state'],'review_required')
                await self.assert_code('shared_tool_review_required',self.tools.resolve(self.reader,self.key))
                self.assertEqual((await self.review())['version'],3)

    async def test_real_native_authentication_error_and_encryption_gate_are_safe(self):
        from urllib.error import HTTPError
        item = await self.review('managed-get_page')
        reference = item['reference']
        env = sys.modules['open_webui.env']
        with patch.object(env,'ENABLE_VALVE_ENCRYPTION',False):
            response = await self.f.bridge.invoke(self.reader,reference,{'page_id':'123'}, {})
            self.assertEqual(response['error']['code'],'encryption_required')
            self.assertIn('암호화',response['error']['message'])
        item = await self.review(item['id'])
        with patch('urllib.request.OpenerDirector.open', side_effect=HTTPError('https://confluence.invalid',401,'synthetic-reader-pat',{},None)):
            response = await self.f.bridge.invoke(self.reader,item['reference'],{'page_id':'123'}, {})
        self.assertEqual(response['error']['code'],'authentication_failed')
        self.assertIn('만료',response['error']['message'])
        self.assertNotIn('synthetic-reader-pat',json.dumps(response))

    async def test_execution_calls_use_same_group_state_reference_and_pinned_version(self):
        from workflow_fixture import historical_facade, load_workflow_examples, arrange_legacy_catalog
        from test_ees_workflow_execution import publish
        await self.review()
        legacy = historical_facade('open_webui').WorkflowService(self.service.database,self.f.native_users.Users.get_user_by_id,lambda _:None,native_bridge=self.f.bridge)
        arrange_legacy_catalog(legacy)
        legacy.shared_tools = self.tools
        legacy._work_actor = self.service._work_actor
        examples = load_workflow_examples('open_webui')
        fragment = examples.installation_docs_workflow(self.refs)
        for node in fragment['nodes'].values():
            for call in node.get('execution',{}).get('calls',[]):
                if call['reference']['function']=='search_pages':
                    call.pop('reference');call['shared_tool_id']=self.key
        process = publish(legacy,fragment)
        with legacy._db() as db: version = legacy._catalog(db)[0]['version']
        plan = await legacy.execution_plan(self.reader,{'node_id':'new-documents-search-j','inputs':{'query':'guide','space_key':'EMS'},'scope':{'site_id':'us-a','system':'EMS','process_id':process,'version':version}})
        self.assertTrue(plan['ok'],plan)
        started = await legacy.execution_action(self.reader,{'action':'start','plan_id':plan['plan']['id'],'plan_hash':plan['plan']['hash'],'request_id':'shared-execution-start'})
        self.assertTrue(started['ok'],started)
        run = started['run']
        paused=await legacy.execution_action(self.reader,{'action':'pause','run_id':run['id'],'expected_revision':run['revision'],'request_id':'shared-execution-pause'})
        self.assertTrue(paused['ok'],paused)
        await self.f.tools.Tools.update_tool_valves_by_id('installed-with-unpredictable-id',{'ENABLED':True,'CONFLUENCE_BASE_URL':'https://confluence.invalid','ALLOWED_SPACES':'EMS,FDC'})
        revised=await self.review()
        # Keep the legacy page reference current independently; its contract
        # remains fixed and is not migrated to a shared ID.
        await self.assert_code('shared_tool_version_changed',legacy.execution._call_reference(self.reader,{'shared_tool_id':self.key},run['id']))
        accepted=await legacy.execution_action(self.reader,{'action':'accept_tool_version','run_id':run['id'],'expected_revision':paused['run']['revision'],'request_id':'shared-execution-accept','shared_tool_id':self.key,'version':2})
        self.assertTrue(accepted['ok'],accepted)
        resumed=await legacy.execution_action(self.reader,{'action':'resume','run_id':run['id'],'expected_revision':accepted['run']['revision'],'request_id':'shared-execution-resume'})
        self.assertTrue(resumed['ok'],resumed)
        with patch('urllib.request.OpenerDirector.open',side_effect=self.http):
            for _ in range(4): await legacy.execution.process_once()
        with legacy._db() as db:
            record=json.loads(db.execute("SELECT data FROM execution_calls WHERE run_id=? AND call_id='search'",(run['id'],)).fetchone()[0])
        self.assertIn('shared_tool',record,record)
        self.assertEqual(record['shared_tool']['version'],2)
        self.assertEqual(record['reference'],revised['reference'])
        call = {'shared_tool_id':self.key}
        await self.assert_code('shared_tool_forbidden',legacy.execution._call_reference(self.f.users['outsider'],call,run['id']))
        item=await self.item()
        await self.tools.command(self.admin,self.body('shared_tool_disable',item['revision'],shared_tool_id=self.key,reference=item['reference']))
        await self.assert_code('shared_tool_disabled',legacy.execution._call_reference(self.reader,call,run['id']))
        self.assertEqual(set(self.http_calls),{'Bearer synthetic-reader-pat'})

if __name__ == '__main__': unittest.main()
