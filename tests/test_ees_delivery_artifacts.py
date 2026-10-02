"""Authored delivery flow on SQLite + real synthetic Jira HTTP, no company calls.

The service command methods are those used by the product JSON API. A synthetic
Native authorization/reference fixture and model isolate external dependencies;
actual browser/Native identity verification is a separate product test.
"""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_ees_work_operations import workflow
from tests import test_jira_work_contract as jira_http
from tests.ees_delivery_artifacts_fixture import definition_from_draft

native = importlib.import_module(workflow.__package__ + '.ees_workflow_native')


class HTTPJiraBridge:
    def __init__(self, transport):
        self.transport = transport; self.allowed = True; self.calls = []
        self.references = {name: {'tool_id': 'native-jira-fixture', 'function': name, 'revision': 1,
            'content_hash': 'a'*64, 'schema_hash': 'b'*64, 'config_hash': 'c'*64, 'environment': 'd'*64}
            for name in ('jira_project_metadata', 'jira_search_crs', 'jira_issue_attachments', 'jira_cr_attachments')}
    async def check(self, actor, reference):
        if not self.allowed or reference != self.references.get(reference.get('function')):
            raise workflow.WorkflowError('native_access_denied', '현재 권한과 참조 불일치')
        return {'reference': deepcopy(reference), 'state': 'allowed'}
    async def invoke(self, actor, reference, arguments, context):
        await self.check(actor, reference)
        self.calls.append((actor['id'], deepcopy(reference), deepcopy(arguments)))
        raw = await getattr(self.transport.tool, reference['function'])(**arguments, __user__=self.transport.user)
        return native.normalize_result(reference['function'], raw, reference, context, ('synthetic-private-pat',))


class ProposalModel:
    def __init__(self): self.calls = []
    async def resolve(self, actor, model_id):
        if model_id != 'synthetic-model': raise workflow.WorkflowError('model_required', '시험 모델 필요')
        return {'id': model_id, 'name': '합성 계약 시험 모델', 'revision': 'fixed'}
    async def propose(self, actor, model_id, context, instruction):
        self.calls.append(deepcopy(context))
        bound = {key: context[key] for key in ('context_id', 'target_id', 'revision', 'kind')}
        proposal = ([{'item_id': id, 'verdict': 'unknown', 'reason': '첨부의 존재·접근만 확인, 내용 적정성 미검토'} for id in context['item_ids']]
                    if context['kind'] == 'verdicts' else '결과 초안: 현재 사람 판정과 저장 근거를 기록함. 미승인 CR 포함/제외 미결정. 송부 채널 미구성.')
        return {'ok': True, 'context': bound, 'proposal': proposal, 'model': await self.resolve(actor, model_id), 'saved': False, 'executed': False}


class DeliveryArtifactsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.http = jira_http.JiraWorkHTTPTests(); self.http.setUp(); self.addCleanup(self.http.doCleanups)
        self.http.total = 3
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.user = {'id': 'author', 'name': '합성 작성자', 'role': 'admin'}
        self.bridge = HTTPJiraBridge(self.http)
        self.service = workflow.WorkflowService(Path(self.temp.name)/'work.db', lambda id: self.user if id=='author' else None,
            lambda id: None, group_lookup=lambda actor: [], native_bridge=self.bridge)
        self.runtime = self.service.operations; self.model = ProposalModel(); self.runtime.model = self.model
        self.addAsyncCleanup(self.runtime.stop); self.counter = 0
    def body(self, action, revision=0, **values):
        self.counter += 1
        return {'action': action, 'expected_revision': revision, 'request_id': 'delivery-'+str(self.counter), **values}
    async def core(self, action, revision=0, **values):
        result = await self.service.workspace_command(self.user, self.body(action, revision, **values))
        self.assertTrue(result['ok'], result)
        return result
    async def state(self):
        result = await self.service.workspace_state(self.user, run_id=self.run_id)
        self.assertTrue(result['ok'], result)
        return result['run']
    async def execute(self, job):
        run = await self.state()
        result = await self.runtime.command(self.user, self.body('execute_job',run['revision'],run_id=self.run_id,job_id=job,model_id='synthetic-model'))
        self.assertEqual(result['attempt']['status'],'succeeded',result)
        return result['attempt']
    async def decide(self, job, verdict='completed', note='합성 담당자가 현재 근거를 확인'):
        run = await self.state(); row = run['jobs'][job]
        attempt = next(item for item in run['attempts'] if item['id']==row['current_attempt'])
        for item in attempt['result'].get('items',[]) or [{'id':'job'}]:
            if item.get('selected') is False:
                current = await self.state()
                denied = await self.service.workspace_command(self.user, self.body('decide',current['revision'],run_id=self.run_id,job_id=job,result_revision=row['result_revision'],item_id=item['id'],verdict=verdict,note=note))
                self.assertFalse(denied['ok'], denied)
                self.assertEqual(denied['error']['code'], 'item_not_found')
                continue
            current = await self.state()
            await self.core('decide',current['revision'],run_id=self.run_id,job_id=job,result_revision=row['result_revision'],item_id=item['id'],verdict=verdict,note=note)
    async def author(self):
        empty = await self.service.workspace_state(self.user)
        self.assertEqual(empty['workflows'],[])
        created = await self.core('create_workflow',system_id='EMS',name='명시적 시험 작성')
        self.workflow_id = created['workflow_id']
        state = await self.service.workspace_state(self.user,workflow_id=self.workflow_id)
        draft = definition_from_draft(state['workflow']['draft'],self.bridge.references)
        self.assertIsNone(state['workflow']['published_version'])
        await self.core('save_draft',1,workflow_id=self.workflow_id,definition=draft)
        check = await self.core('validate_workflow',2,workflow_id=self.workflow_id)
        self.assertEqual(check['validation']['errors'],[])
        await self.core('publish_workflow',2,workflow_id=self.workflow_id)
        self.inputs={'project':'APPX','statuses':['11'],'date_field':'customfield_12001','from_date':'2026-10-01','to_date':'2026-10-02','required_filenames':['design.txt']}
        started = await self.core('start_run',3,workflow_id=self.workflow_id,inputs=self.inputs)
        self.run_id = started['run_id']
    async def test_authored_real_http_recheck_preserves_unknown_verdict_and_report_draft(self):
        await self.author()
        for field, expected in [('project','APPX'),('statuses','11'),('date_field','customfield_12001')]:
            result=await self.service.input_options(self.user,{'run_id':self.run_id,'job_id':'cr-list','field_id':field})
            self.assertTrue(result['ok'],result); self.assertIn(expected,[item['id'] for item in result['options']])
        listing=await self.execute('cr-list'); self.assertEqual([item['id'] for item in listing['result']['items']],['APPX-1','APPX-2','APPX-3'])
        self.assertEqual(listing['snapshot']['options']['project']['options'],[{'id':'APPX','name':'Actual project'}])
        self.assertEqual((await self.state())['jobs']['cr-list']['status'],'waiting_confirmation')
        await self.decide('cr-list')
        attachments=await self.execute('documents')
        self.assertEqual(attachments['snapshot']['arguments']['issue_keys'],['APPX-1','APPX-2','APPX-3'])
        self.assertEqual(attachments['snapshot']['argument_sources']['issue_keys']['attempt_id'],listing['id'])
        self.assertEqual(len(attachments['result']['data']['document_checks']),3)
        self.assertFalse(attachments['result']['data']['content_reviewed'])
        self.assertEqual(attachments['result']['data']['attachments'][0]['accessibility'],'readable')
        await self.decide('documents',note='합성 첨부 존재·접근 확인만 완료; 내용 적정성 승인이 아님')
        proposal=await self.execute('verdict')
        self.assertEqual((await self.state())['jobs']['verdict']['decisions'],[])
        await self.decide('verdict','action_required','내용 적정성 미검토로 보완 요청')
        first=deepcopy(await self.state())
        again=await self.execute('documents')
        self.assertNotEqual(again['id'],attachments['id'])
        await self.decide('documents',note='재접근 가능; 문서 적정성 판단은 별도')
        await self.execute('verdict')
        await self.decide('verdict','unknown','검토되지 않은 내용은 판단 불가로 보존')
        report=await self.execute('report')
        self.assertIn('송부 채널 미구성',json.dumps(report['result'],ensure_ascii=False))
        await self.decide('report',note='결과 초안만 검토; 배포 승인·송부가 아님')
        final=await self.state()
        self.assertEqual(final['jobs']['verdict']['status'],'unknown')
        self.assertEqual(final['jobs']['report']['status'],'completed')
        self.assertEqual(final['definition']['delivery_policy'],'draft_only')
        self.assertEqual(final['definition']['unapproved_policy'],'hold')
        blocked=await self.service.workspace_command(self.user,self.body('close_run',final['revision'],run_id=self.run_id))
        self.assertFalse(blocked['ok']); self.assertEqual(blocked['error']['code'],'completion_required')
        self.assertEqual([a for a in final['attempts'] if a['id']==attachments['id']],[a for a in first['attempts'] if a['id']==attachments['id']])
        self.assertEqual(len([a for a in final['attempts'] if a['job_id']=='verdict']),2)
        self.assertEqual([d['verdict'] for d in final['jobs']['verdict']['decisions']],['action_required']*3+['unknown']*3)
        self.assertTrue(any(call['path'].endswith('/search') for call in self.http.calls))
        self.assertTrue(any(call['range']=='bytes=0-0' for call in self.http.calls))
        exported=await self.service.workspace_export(self.user,self.run_id)
        self.assertTrue(exported['ok']); self.assertEqual(exported['run']['jobs']['verdict']['status'],'unknown')
        self.assertNotIn('synthetic-private-pat',json.dumps(exported))
        self.assertTrue(all(context['source']['human_decisions'] for context in self.model.calls))
        self.assertNotIn('synthetic-private-pat',json.dumps(final))
        self.bridge.allowed=False
        with self.assertRaises(workflow.WorkflowError): await self.execute('documents')

    async def test_confirmed_list_reorder_exclusion_and_source_recheck_preserve_exact_binding(self):
        await self.author(); original=await self.execute('cr-list')
        run=await self.state(); before=len(self.bridge.calls)
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('execute_job',run['revision'],run_id=self.run_id,job_id='documents'))
        self.assertEqual(len(self.bridge.calls),before)
        await self.decide('cr-list'); first=await self.execute('documents'); await self.decide('documents')
        run=await self.state()
        items=[deepcopy(original['result']['items'][2]),deepcopy(original['result']['items'][0])]
        items[1]['selected']=False
        await self.core('amend_items',run['revision'],run_id=self.run_id,job_id='cr-list',result_revision=run['jobs']['cr-list']['result_revision'],items=items,reason='합성 목록 재정렬·APPX-2 삭제·APPX-1 제외를 사람이 명시')
        changed=await self.state()
        self.assertEqual(changed['jobs']['documents']['status'],'review_required')
        self.assertEqual(next(a for a in changed['attempts'] if a['id']==first['id'])['snapshot']['arguments']['issue_keys'],['APPX-1','APPX-2','APPX-3'])
        await self.decide('cr-list')
        second=await self.execute('documents')
        self.assertEqual(second['snapshot']['arguments']['issue_keys'],['APPX-3'])
        source=second['snapshot']['argument_sources']['issue_keys']
        self.assertNotEqual(source['attempt_id'],original['id']); self.assertEqual(source['result_revision'],2)
        await self.execute('cr-list')
        current=await self.state(); self.assertEqual(current['jobs']['documents']['status'],'review_required')
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('execute_job',current['revision'],run_id=self.run_id,job_id='documents'))

    async def test_partial_list_cannot_authorize_attachment_batch_or_hide_missing_crs(self):
        await self.author(); self.http.tool.valves.MAX_CR_PAGES=1
        run=await self.state()
        partial=await self.runtime.command(self.user,self.body('execute_job',run['revision'],run_id=self.run_id,job_id='cr-list'))
        self.assertEqual(partial['attempt']['status'],'partial')
        self.assertEqual(partial['attempt']['result']['data']['listing']['total'],3)
        await self.decide('cr-list')
        current=await self.state(); self.assertEqual(current['jobs']['cr-list']['status'],'partial')
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user,self.body('execute_job',current['revision'],run_id=self.run_id,job_id='documents'))
        self.assertFalse(any(call[1]['function']=='jira_cr_attachments' for call in self.bridge.calls))
