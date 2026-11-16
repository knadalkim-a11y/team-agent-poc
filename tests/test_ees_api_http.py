"""HTTP wire contract, trust boundaries and independent mutation observations."""
import importlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
package = ModuleType('ees_http_tests')
package.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
sys.modules[package.__name__] = package
http = importlib.import_module(package.__name__ + '.ees_workflow_api_http')


class ApiHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = 'https://service.test:8443/api'
        self.config = {'base_url': self.base, 'actor_ids': ['u'],
                       'user_credential_headers': {'u': {'Authorization': 'TEST_SERVICE_TOKEN'}}}
        self.actor = {'id': 'u'}
        self.op = {'id':'op-1', 'service_id':'svc', 'method':'GET', 'url':self.base+'/rows/{id}?fixed=yes&range={period}',
                   'inputs':[{'name':'key','wire_name':'id','in':'path','type':'string','required':True},
                             {'name':'period','wire_name':'range','in':'query','type':'array','required':False}],
                   'result_path':'page.results','fields':[{'path':'meta.name','type':'string','label':'Name'}]}
        self.args = {'key':'열 A','period':['a b','b/c']}
        self.enterContext(patch.dict(os.environ, {'TEST_SERVICE_TOKEN':'Bearer actual-secret'}))
        self.install_config()

    def install_config(self):
        self.enterContext(patch.dict(os.environ, {'EES_WORK_API_SERVICES':json.dumps({'svc':self.config})}))

    async def test_wire_path_query_mapping_selection_redaction_and_service_auth(self):
        def exchange(origin, method, path, headers, body):
            self.assertEqual(origin, ('https','service.test',8443))
            self.assertEqual(method,'GET')
            self.assertEqual(path, '/api/rows/%EC%97%B4%20A?fixed=yes&range=a+b&range=b%2Fc')
            self.assertEqual(headers['Authorization'], 'Bearer actual-secret')
            self.assertIsNone(body)
            return 200, b'{"page":{"results":[{"meta":{"name":"actual-secret"},"unrelated":"private"}]}}'
        with patch.object(http, '_exchange', exchange):
            for wire_inputs in ((self.op['inputs'],self.args),
                                ([self.op['inputs'][0], {**self.op['inputs'][1],'name':'range'}], {'key':'열 A','range':['a b','b/c']})):
                response = await http.invoke_http({**self.op,'inputs':wire_inputs[0]}, wire_inputs[1], self.actor)
                self.assertEqual(response['field_labels'], {'meta.name':'Name'})
                self.assertEqual(response['items'][0]['row'], {'meta.name':'[가림]'})
                self.assertNotIn('private',json.dumps(response))

    async def test_foreign_address_traversal_credential_scope_and_read_method_override_block_io(self):
        with patch.object(http, '_exchange') as call:
            for address in ('https://other.test/api','https://service.test:8443/apix', self.base+'/%252e%252e/admin',
                            self.base+'/x%2f..%2fadmin', 'https://user@service.test:8443/api',self.base+'/x?access_token=private'):
                with self.subTest(address=address), self.assertRaises(http.WorkflowError):
                    await http.invoke_http({**self.op,'url':address}, self.args, self.actor)
            with self.assertRaises(http.WorkflowError):
                await http.invoke_http(self.op,self.args,{'id':'other'})
            for header in ('Host','X-HTTP-Method-Override','Authorization','Forwarded','X-Original-URL'):
                with self.subTest(header=header), self.assertRaises(http.WorkflowError):
                    operation={**self.op,'inputs':self.op['inputs']+[{'name':'custom','wire_name':header,'in':'header','type':'string'}]}
                    await http.invoke_http(operation,{**self.args,'custom':'POST'},self.actor)
            call.assert_not_called()

    async def test_trial_preview_and_independent_mutation_status_and_effect(self):
        self.op.update(method='POST', url=self.base+'/jobs',inputs=[{'name':'code','wire_name':'item.code','in':'body','type':'string','required':True}],
                       fields=[], result_path='')
        criterion={'check':'backup-complete'}
        self.config['observations']={'op-1':{'correlation_header':'X-Request-ID', 'job_number_field':'jobId',
            'status':{'url':self.base+'/jobs/{id}', 'field':'state', 'states':{'done':'reported_complete'}},
            'effect':{'url':self.base+'/evidence/{id}', 'field':'verified', 'equals':True, 'criterion':criterion}}}
        self.install_config()
        log=[]
        def exchange(origin,method,path,headers,body):
            log.append((method,path))
            if method=='POST':
                self.assertEqual(headers['X-Request-ID'],'request-correlation')
                self.assertEqual(json.loads(body),{'item':{'code':'A'}})
                return 202,b'{"jobId":"job-51"}'
            return 200,(b'{"state":"done"}' if path.startswith('/api/jobs/') else b'{"verified":true}')
        with patch.object(http,'_exchange',exchange):
            preview=await http.invoke_http(self.op,{'code':'A'},self.actor,preview=True)
            self.assertTrue(preview['preview'])
            self.assertFalse(log)
            response=await http.invoke_http(self.op,{'code':'A'},self.actor,correlation_id='request-correlation')
            self.assertEqual(response['job_number'],'job-51')
            request={'job_number':'job-51','effect_criterion':criterion}
            self.assertEqual(await http.observe_http(self.op,self.actor,request),{'state':'reported_complete'})
            self.assertTrue((await http.observe_http(self.op,self.actor,request,effect=True))['satisfied'])
            with self.assertRaises(http.WorkflowError):
                await http.observe_http(self.op,self.actor,{**request,'effect_criterion':{'check':'different'}},effect=True)
        self.assertEqual(log,[('POST','/api/jobs'),('GET','/api/jobs/job-51'),('GET','/api/evidence/job-51')])

    async def test_empty_missing_partial_and_http_error_are_distinct(self):
        expected=[(200,b'{"page":{"results":[]}}','succeeded','empty'),
                  (200,b'{"partial":true,"page":{"results":[]}}','partial','partial'),
                  (503,b'remote-secret','failed','unknown')]
        for status,body,outcome,completeness in expected:
            with patch.object(http,'_exchange',return_value=(status,body)):
                result=await http.invoke_http(self.op,self.args,self.actor)
                self.assertEqual((result['status'],result['completeness']), (outcome,completeness))
                self.assertNotIn('remote-secret', json.dumps(result))
        with patch.object(http,'_exchange',return_value=(200,b'{"page":{"results":[{"other":1}]}}')):
            with self.assertRaises(http.WorkflowError) as caught:
                await http.invoke_http(self.op,self.args,self.actor)
        self.assertEqual(caught.exception.code,'api_result_mapping_invalid')

    async def test_redirects_are_never_followed_and_specs_use_same_deployment_registry(self):
        from unittest.mock import MagicMock
        conn=MagicMock()
        conn.getresponse.return_value.status=307
        with patch.object(http.http.client,'HTTPSConnection',return_value=conn):
            with self.assertRaises(http.WorkflowError) as caught:
                await http.fetch_spec(self.base+'/openapi.json','svc',self.actor)
            self.assertEqual(caught.exception.code,'api_redirect_refused')
            self.assertEqual(conn.request.call_count,1)
            conn.close.assert_called_once()

    async def test_whole_json_body_and_scalar_result_keep_json_types(self):
        for kind, value in [('array',[]), ('object',{}), ('boolean',False), ('string',''), ('number',0), ('null',None)]:
            operation = {**self.op, 'method':'POST', 'url':self.base+'/value', 'result_path':'',
                         'fields':[{'path':'$', 'root_value':True, 'type':'string'}],
                         'inputs':[{'name':'body', 'in':'body','required':True,'whole_body':True,'type':kind}]}
            with self.subTest(kind=kind), patch.object(http,'_exchange',return_value=(200,b'"success"')) as send:
                result = await http.invoke_http(operation,{'body':value},self.actor)
                self.assertEqual(json.loads(send.call_args.args[-1]),value)
                self.assertEqual(result['items'][0]['row'],{'$':'success'})

    async def test_new_catalog_service_resolves_unique_approved_origin_and_prefix(self):
        op = {**self.op, 'service_id':'new-catalog-uuid'}
        with patch.object(http,'_exchange',return_value=(200,b'{"page":{"results":[]}}')) as send:
            result = await http.invoke_http(op,self.args,self.actor)
            self.assertEqual(result['completeness'],'empty')
            self.assertEqual(await http.fetch_spec(self.base+'/spec', 'new-catalog-uuid', self.actor), '{"page":{"results":[]}}')
            self.assertEqual(send.call_count,2)
            for args in send.call_args_list:
                self.assertEqual(args.args[3]['Authorization'],'Bearer actual-secret')

    async def test_explicit_service_and_ambiguous_or_denied_target_never_fallback(self):
        op = {**self.op, 'service_id':'catalog-id'}
        configs = [
            {'catalog-id':{'base_url':'https://other.test'},'approved':self.config},
            {'catalog-id':{**self.config,'actor_ids':['another']},'approved':self.config},
            {'catalog-id':{**self.config,'user_credential_headers':{}},'approved':self.config},
            {'old':self.config,'new':{**self.config,'actor_ids':['another']}},
            {'approved':{**self.config,'actor_ids':['another']}},
            {'different':{'base_url':self.base+'/different'}},
        ]
        with patch.object(http,'_exchange') as send:
            for config in configs:
                with self.subTest(keys=list(config)), patch.dict(os.environ,{'EES_WORK_API_SERVICES':json.dumps(config)}):
                    with self.assertRaises(http.WorkflowError):
                        await http.invoke_http(op,self.args,self.actor)
                    with self.assertRaises(http.WorkflowError):
                        await http.fetch_spec(self.base+'/spec','catalog-id', self.actor)
            send.assert_not_called()
