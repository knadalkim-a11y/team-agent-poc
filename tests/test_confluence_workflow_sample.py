"""Verify the shipped Confluence registration script with product HTTP routes and HTTPS."""
from contextlib import closing, contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
import json
import os
import sqlite3
from pathlib import Path
import asyncio
import sys
import tempfile
from threading import Thread
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
import httpx

from confluence_provider import CHILDREN, PAGE, PAGE_ID, confluence_provider

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'confluence'
sys.path.insert(0, str(EXAMPLE))
from register_confluence_demo import SetupError, TITLE, WORKING_TITLE, provision, session

package = ModuleType('ees_confluence_workflow_tests')
package.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
sys.modules[package.__name__] = package
workflow = import_module(package.__name__ + '.ees_workflow')


class EmptyNativeRegistry:
    async def invoke(self, *_args):
        raise AssertionError('An API-only workflow must use the registered HTTP transport')


@contextmanager
def workflow_server(database, client_users, *, confluence_guide=False):
    """Serve the product's routes; substitute only the signed-in identity and isolated DB."""
    service = workflow.WorkflowService(database, client_users.get, lambda _: None,
                                       native_bridge=EmptyNativeRegistry(), confluence_guide=confluence_guide)
    app = FastAPI()

    async def verified(authorization: str = Header(default='')):
        user = client_users.get(authorization.removeprefix('Bearer '))
        if not user:
            raise HTTPException(status_code=401)
        return user

    workflow.install(app, verified)
    class Router(BaseHTTPRequestHandler):
        # Forward the stdlib registration client across loopback to the real ASGI routes.
        def respond(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))

            async def dispatch():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url='http://work.test') as client:
                    return await client.request(self.command, self.path, content=body, headers=dict(self.headers))

            response = asyncio.run(dispatch())
            self.send_response(response.status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        do_GET = do_POST = respond

        def log_message(self, *_):
            pass

    with (patch.object(workflow, '_production_service', return_value=service),
          ThreadingHTTPServer(('127.0.0.1', 0), Router) as server):
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.025}, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            thread.join()


class ConfluenceWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.db = Path(temp) / 'work.sqlite3'
        self.provider = self.enterContext(confluence_provider(temp))
        self.users = {key: {'id': key, 'role': role} for key, role in
                      [('admin', 'admin'), ('operator', 'user')]}
        self.env = {'SSL_CERT_FILE': self.provider.ca, 'EES_CONFLUENCE_TEST_HEADER': self.provider.bearer,
                    'EES_WORK_API_SERVICES': json.dumps({'confluence-test': {
                        'base_url': self.provider.base_url, 'actor_ids': ['admin', 'operator'],
                        'credential_headers': {'Authorization': 'EES_CONFLUENCE_TEST_HEADER'},
                    }})}
        self.enterContext(patch.dict(os.environ, self.env))
        self.webui = self.enterContext(workflow_server(self.db, self.users))
        self.http = self.enterContext(httpx.Client(trust_env=False))
        spec = json.loads((EXAMPLE / 'confluence-readonly.openapi.json').read_text(encoding='utf-8'))
        spec['servers'][0]['url'] = self.provider.base_url
        self.spec = json.dumps(spec, ensure_ascii=False)

    def call(self, route, data=None, query=None, *, actor='admin', server=None, check=True):
        response = self.http.request('GET' if data is None else 'POST',
                (server or self.webui) + '/api/ees-work/' + route,
                params=query, json=data, headers={'Authorization': 'Bearer ' + actor})
        if check:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['ok'], response.text)
        return response.json()

    def command(self, route, action, revision=0, *, actor='operator', check=True, **values):
        return self.call(route, {'action': action, 'request_id': str(uuid4()), 'expected_revision': revision,
                                **values}, actor=actor, check=check)

    def create_run(self, page_id=PAGE_ID):
        with patch('register_confluence_demo.getpass.getpass', return_value='admin'):
            catalog = session(self.webui, email=None)
        self.record = provision(catalog, self.spec, 'EMS')
        again = provision(catalog, self.spec, 'EMS')
        self.assertEqual(again['status'], 'existing')
        self.assertEqual(again['workflow_id'], self.record['workflow_id'])
        self.workflow_id = self.record['workflow_id']
        authoring = self.call('workspace', query={'workflow_id': self.workflow_id})['workflow']
        self.assertIsNotNone(authoring['published_version'])
        jobs = authoring['published']['nodes']
        self.assertEqual(jobs['page']['result_block'], 'human_confirm')
        self.assertEqual(jobs['children']['result_block'], 'list_confirm')
        self.assertTrue(jobs['page']['human_confirmation'])
        self.assertTrue(jobs['children']['human_confirmation'])
        self.command('workspace/command', 'save_access', actor='admin', system_id='EMS', factory_id='*',
                     roles=['participant'], principal_kind='user', principal_id='operator')
        result = self.command('workspace/command', 'start_run', authoring['revision'],
                              workflow_id=self.workflow_id, inputs={'page-id': page_id})
        self.assertEqual([], self.provider.records, 'Registration, publication or starting dispatched an API')
        return result['run_id']

    def state(self, run_id, *, server=None):
        return self.call('workspace', query={'run_id': run_id}, actor='operator', server=server)['run']

    def run_step(self, run_id, job, *, check=True):
        revision = self.state(run_id)['revision']
        return self.command('operations', 'execute_job', revision, job_id=job, run_id=run_id, check=check)['attempt']

    def confirm(self, run_id, attempt, job):
        revision = self.state(run_id)['revision']
        if job == 'page':
            return self.command('workspace/command', 'decide', revision, job_id=job, run_id=run_id,
                                item_id='job', verdict='completed', result_revision=attempt['number'])
        items = [{'id': item['id'], 'title': item['title'], 'selected': True, 'required': True}
                 for item in attempt['result']['items']]
        return self.command('workspace/command', 'confirm_list', revision, job_id=job, run_id=run_id,
                items=items, attempt_id=attempt['id'], result_revision=attempt['number'],
                reason='' if items else '확인할 하위 문서가 없습니다.')

    def open_guide(self, database, previous_service=None):
        service = {'base_url': self.provider.base_url + '/content', 'actor_ids': ['operator'],
                   'user_credential_headers': {'operator': {'Authorization': 'EES_CONFLUENCE_TEST_HEADER'}}}
        registry = {'confluence-readonly-pilot': service}
        if previous_service:
            registry[previous_service] = service
        self.enterContext(patch.dict(os.environ, {'EES_WORK_API_SERVICES': json.dumps(registry),
                                                  'EES_WORK_GUIDE_SYSTEM': 'EMS'}))
        self.webui = self.enterContext(workflow_server(database, self.users, confluence_guide=True))

    def test_pinned_run_access_does_not_reopen_the_catalog(self):
        run_id = self.create_run()
        key = 'managed-get_page'
        reference = {'tool_id':'earlier-only-code', 'function':'get_page'}
        tool = {'id':key, 'version':2, 'state':'available', 'name':'기준 문서', 'function':'get_page',
                'group_ids':['readers'], 'reference':reference, 'private_marker':'must-never-be-in-the-summary'}
        with closing(sqlite3.connect(self.db)) as db, db:
            saved = json.loads(db.execute('SELECT snapshot FROM work_runs WHERE id=?', (run_id,)).fetchone()[0])
            node = saved['definition']['nodes']['page']
            node.pop('api_binding')
            node['shared_tool_id'] = key
            db.execute('UPDATE work_runs SET snapshot=? WHERE id=?', (json.dumps(saved),run_id))
            db.execute('INSERT INTO work_shared_tools VALUES(?,?,?)', (key,1,json.dumps(tool)))
            db.execute('INSERT INTO work_shared_tool_pins VALUES(?,?,?,?)',
                       ('work',run_id,key,json.dumps({'id':key,'version':1,'reference':reference})))
        self.open_guide(self.db)
        service = workflow._production_service()
        current = {field:tool[field] for field in ('id','version','reference')}
        query = {'system_id':'EMS','run_id':run_id}
        with patch.object(service,'group_lookup',return_value=[{'id':'readers'}]), patch.object(
                service.shared_tools,'resolve',new=AsyncMock(return_value=current)) as resolve:
            state = self.call('operations', query=query, actor='operator')
            access = state['shared_tool_access']['page']
            resolve.assert_awaited_once()
            self.assertEqual(state['shared_tools'], [])
            self.assertTrue(access['can_accept_version'])
            self.assertEqual(access['current_tool'], {
                'id':key, 'name':'기준 문서','version':2,'state':'available','function':'get_page','can_use':True})
            self.command('operations', 'shared_tool_accept_version', self.state(run_id)['revision'],
                         run_id=run_id, shared_tool_id=key, version=2)
            self.assertIn({'id':key, 'version':2}, self.state(run_id)['shared_tools'])
            self.assertEqual(self.call('operations', query=query, actor='operator')['shared_tools'], [])
            resolve.side_effect = workflow.WorkflowError('native_access_denied','detailed-private-message')
            unavailable = self.call('operations', query=query, actor='operator')['shared_tool_access']['page']
            self.assertEqual(unavailable['current_tool']['can_use'], False)
            self.assertNotIn('name', unavailable['current_tool'])
            self.assertNotIn('detailed-private-message', str(unavailable))
            self.assertFalse(unavailable['can_accept_version'])
        outside = self.call('operations', query=query, actor='operator')['shared_tool_access']['page']
        self.assertFalse(outside['can_use'])
        self.assertNotIn('current_tool', outside)

    def test_api_only_install_retires_old_authoring_controls(self):
        self.open_guide(self.db.with_name('api-only.sqlite3'))
        for actor in ('admin', 'operator'):
            with self.subTest(actor=actor):
                for action in ('tool_draft_get', 'tool_draft_save', 'tool_draft_check',
                               'tool_draft_connection_get', 'tool_draft_connection_save', 'tool_draft_trial_start',
                               'tool_draft_use_enable', 'shared_tool_access', 'shared_tool_review',
                               'tool_save', 'tool_submit', 'tool_review'):
                    response = self.command('operations', action, actor=actor, check=False)
                    self.assertEqual(response['error']['code'], 'tool_authoring_retired', action)
                state = self.call('operations', actor=actor)
                for key in ('tool_draft_phase', 'tool_scope_factories', 'shared_tool_messages', 'legacy_tool_authoring'):
                    self.assertNotIn(key, state)
                self.assertTrue(state['api_catalog']['apis'])
        self.assertFalse(self.call('authoring', check=False)['ok'])
        for query in ({}, {'process_id':'old'}, {'chat_id':'empty-chat'}):
            self.assertFalse(self.call('state', query=query, check=False)['ok'])
        self.assertTrue(self.call('legacy')['read_only'])
        self.assertEqual(self.call('execution/capability', check=False)['error']['code'], 'tool_authoring_retired')
        self.assertEqual(self.call('execution/capability/action', {'action':'approve'}, check=False)['error']['code'],
                         'tool_authoring_retired')
        guide = self.call('workspace', query={'workflow_id':'guide-confluence-documents'})['workflow']
        for old in ({'tool_contract_id':'old-code'}, {'shared_tool_id':'authored-new'},
                    {'tool_reference':{'tool_id':'earlier','function':'get_page'}},
                    {'execution':{'reference':{'tool_id':'earlier','function':'get_page'}}},
                    {'inputs':[{'id':'jira-field','type':'single','options_source':'tool'}]}):
            with self.subTest(connection=old):
                draft = deepcopy(guide['draft'])
                job = draft['nodes']['page']
                job.pop('api_binding')
                job.update(old)
                response = self.command('workspace/command', 'save_draft', guide['revision'], actor='admin',
                                        check=False, workflow_id=guide['id'], definition=draft)
                self.assertFalse(response['ok'])
                self.assertIn('입력 선택지' if 'inputs' in old else '사용할 API', response['error']['message'])
                self.assertEqual(self.call('workspace', query={'workflow_id':guide['id']})['workflow']['revision'],
                                 guide['revision'])

    def test_chat_rejects_retired_binding_before_browser_preview(self):
        self.open_guide(self.db.with_name('assistant-api-only.sqlite3'))
        native = import_module(package.__name__ + '.ees_workflow_native')
        from types import SimpleNamespace
        request = SimpleNamespace(state=SimpleNamespace(ees_work_tool_source_hash='verified'))
        actor = self.users['admin']
        native_tools = SimpleNamespace(Tools=SimpleNamespace(get_tool_by_id=AsyncMock(return_value='ees_workflow')))
        original = AsyncMock(return_value={'ok':True})
        functions = {'propose': {'tool_id':'ees_workflow','spec':{'name':'ees_workflow_propose'},'callable':original}}
        with patch.dict(sys.modules, {'open_webui.models.tools': native_tools}), patch.object(
                    native,'_chat_work_access',new=AsyncMock(return_value=(actor,'verified'))):
            guarded = native.wrap_chat_work_tools(request, actor, functions)['propose']['callable']
            rejected = asyncio.run(guarded(definition={'nodes':{'j':{'shared_tool_id':'old'}}}))
            self.assertEqual(rejected['error']['code'], 'invalid_proposal')
            original.assert_not_awaited()
            self.assertTrue(asyncio.run(guarded(definition={'nodes':{'j':{'api_binding':{'operation_id':'api'}}}}))['ok'])
            original.assert_awaited_once()

    def test_guide_catalog_without_confluence_or_model_connection(self):
        self.enterContext(patch.dict(os.environ, {'EES_WORK_API_SERVICES': '{}', 'EES_WORK_GUIDE_SYSTEM': 'EMS'}))
        self.webui = self.enterContext(workflow_server(self.db.with_name('unconfigured.sqlite3'),
                                       self.users, confluence_guide=True))
        service = workflow._production_service()
        self.enterContext(patch.object(service, 'group_list_lookup', return_value=[{'id': 'team', 'name': '팀'}]))
        self.command('operations', 'api_save', actor='admin', service_name='그룹 전용',
                     api={'name': '제한된 조회', 'purpose': '권한 확인', 'method': 'GET',
                          'url': 'https://restricted.example/status', 'group_ids': ['team']})
        model = AsyncMock()
        model.available.side_effect = workflow.WorkflowError('model_unavailable', '모델을 조회할 수 없습니다.')
        self.enterContext(patch.object(service.operations, 'model', model))
        self.assertEqual(self.call('operations', check=False)['error']['code'], 'model_unavailable')
        model.available.reset_mock()
        guide = self.call('workspace', query={'system_id': 'EMS'})['workflows']
        self.assertEqual([(w['id'], w['published_version']) for w in guide], [('guide-confluence-documents', 1)])
        catalog = self.call('api-catalog', actor='operator')['api_catalog']
        self.assertCountEqual([row['name'] for row in catalog['apis']], ['기준 문서 확인', '하위 문서 목록 조회'])
        self.assertEqual([row['id'] for row in catalog['services']], ['confluence-readonly-pilot'])
        self.assertFalse(catalog['can_manage'])
        self.assertEqual(len(self.call('api-catalog')['api_catalog']['apis']), 3)
        self.assertEqual(self.http.get(self.webui + '/api/ees-work/api-catalog').status_code, 401)
        model.available.assert_not_awaited()
        self.assertEqual(self.provider.records, [])

    def test_clean_deployment_publishes_runnable_guide_without_registration(self):
        database = self.db.with_name('fresh-guide.sqlite3')
        self.assertFalse(database.exists())
        self.users['unassigned'] = {'id': 'unassigned', 'role': 'user'}
        self.open_guide(database)
        workspace = self.call('workspace', query={'system_id': 'EMS'})
        self.assertEqual([w['id'] for w in workspace['workflows']], ['guide-confluence-documents'])
        self.assertEqual([p['id'] for p in workspace['procedure_examples']], ['confluence_documents'])
        def inspect_only(route, data=None, query=None):
            self.assertIsNone(data, 'The legacy installer must not write after the guide is installed')
            return self.call(route, query=query)

        for system in ('EMS', 'APC'):
            installed = provision(inspect_only, self.spec, system)
            self.assertEqual(installed['status'], 'built_in')
            self.assertEqual(installed['system_id'], 'EMS')
            self.assertEqual(installed['workflow_id'], 'guide-confluence-documents')
        operations = self.call('operations', query={'system_id': 'EMS'})
        self.assertTrue(operations['confluence_guide'])
        for key in ('tool_examples', 'tools', 'shared_tools', 'tool_drafts', 'tool_import_sources'):
            self.assertEqual(operations[key], [], key)
        catalog = operations['api_catalog']
        self.assertEqual({op['id'] for op in catalog['apis']}, {'guide-confluence-page', 'guide-confluence-children'})
        self.assertEqual({op['service_id'] for op in catalog['apis']}, {'confluence-readonly-pilot'})
        self.assertEqual({op['method'] for op in catalog['apis']}, {'GET'})
        for system in ('EMS', 'APC'):
            init = self.command('workspace/command', 'initialize_procedures', actor='admin', system_id=system)
            self.assertEqual(init['created_workflow_ids'], [])
        procedures = self.call('workspace')['workflows']
        self.assertEqual([wf['id'] for wf in procedures], ['guide-confluence-documents'])
        guide = workspace['workflows'][0]
        self.assertEqual(guide['published_version'], 1)
        args = {'workflow_id': guide['id'], 'inputs': {'page-id': PAGE_ID}}
        denied = self.command('workspace/command', 'start_run', guide['revision'], actor='unassigned', check=False, **args)
        self.assertFalse(denied['ok'])
        self.command('workspace/command', 'save_access', actor='admin', system_id='EMS', factory_id='*',
                     roles=['participant'], principal_kind='user', principal_id='operator')
        run = self.command('workspace/command', 'start_run', guide['revision'], **args)['run_id']
        self.assertEqual(self.provider.records, [])
        first = self.run_step(run, 'page')
        self.assertEqual(first['result']['items'][0]['row']['title'], PAGE['title'])
        denied = self.command('operations', 'execute_job', self.state(run)['revision'],
                              job_id='children', run_id=run, check=False)
        self.assertFalse(denied['ok'])
        self.assertEqual(len(self.provider.records), 1)
        self.confirm(run, first, 'page')
        children = self.run_step(run, 'children')
        self.assertEqual([item['row']['id'] for item in children['result']['items']], [p['id'] for p in CHILDREN])
        self.confirm(run, children, 'children')
        self.command('workspace/command', 'close_run', self.state(run)['revision'], run_id=run)
        self.open_guide(database)
        reopened = self.state(run)
        self.assertEqual(reopened['status'], 'completed')
        self.assertEqual([a['result']['http_status'] for a in reopened['attempts']], [200, 200])
        self.assertEqual(self.provider.records, [
            ('/rest/api/content/' + PAGE_ID, {}, True),
            ('/rest/api/content/' + PAGE_ID + '/child/page', {'limit': ['5']}, True),
        ])
        self.assertNotIn(self.provider.bearer, json.dumps(reopened))

    def test_upgrade_archives_old_catalog_and_preserves_runs_and_later_authoring(self):
        old = self.create_run()
        self.confirm(old, self.run_step(old, 'page'), 'page')
        self.confirm(old, self.run_step(old, 'children'), 'children')
        self.command('workspace/command', 'close_run', self.state(old)['revision'], run_id=old)
        old_attempts = self.state(old)['attempts']
        previous = self.call('workspace', query={'workflow_id': self.workflow_id})['workflow']
        active = self.command('workspace/command', 'start_run', previous['revision'],
                              workflow_id=self.workflow_id, inputs={'page-id': PAGE_ID})['run_id']
        old_catalog = self.call('operations', query={'system_id': 'EMS'})['api_catalog']
        previous_service = old_catalog['apis'][0]['service_id']
        self.open_guide(self.db, previous_service)
        catalog = self.call('operations', query={'system_id': 'EMS'})['api_catalog']
        self.assertEqual({op['id'] for op in catalog['apis']}, {'guide-confluence-page', 'guide-confluence-children'})
        self.assertNotIn(previous_service, [svc['id'] for svc in catalog['services']])
        visible = self.call('workspace', query={'system_id': 'EMS'})['workflows']
        self.assertEqual([wf['id'] for wf in visible], ['guide-confluence-documents'])
        denied = self.command('workspace/command', 'start_run', previous['revision'], check=False,
                              workflow_id=previous['id'], inputs={'page-id': PAGE_ID})
        self.assertFalse(denied['ok'])
        for run_id in (old, active):
            restored = self.call('workspace', query={'workflow_id': previous['id'], 'run_id': run_id},
                                 actor='operator')['run']
            self.assertEqual(restored['workflow_id'], previous['id'])
            if run_id == old:
                self.assertEqual(restored['status'], 'completed')
                self.assertEqual(restored['attempts'], old_attempts)
        created = self.command('workspace/command', 'create_workflow', actor='admin', name='신규 절차', system_id='EMS')
        op = self.command('operations', 'api_save', actor='admin', api={
            'name': '신규 API', 'purpose': '새 서비스 조회', 'method': 'GET', 'url': 'https://new.example/status',
            'inputs': [], 'fields': []})['api']
        self.open_guide(self.db, previous_service)
        catalog = self.call('operations', query={'system_id': 'EMS'})['api_catalog']
        self.assertEqual({row['id'] for row in catalog['apis']},
                         {'guide-confluence-page', 'guide-confluence-children', op['id']})
        visible = self.call('workspace', query={'system_id': 'EMS'})['workflows']
        self.assertEqual({wf['id'] for wf in visible}, {'guide-confluence-documents', created['workflow_id']})
        self.assertEqual(len(self.provider.records), 2, 'A restart or migration called Confluence')

    def test_upgrade_does_not_dispatch_older_queued_or_claimed_work(self):
        run_id = self.create_run()
        initial = self.state(run_id)
        scope = self.command('operations', 'execute_scope', initial['revision'], run_id=run_id)['scope']
        # A real queue lease shows that a worker might already have contacted the provider.
        worker = workflow._production_service().operations
        claimed = worker._claim_scope()
        self.assertEqual(claimed['id'], scope['id'])
        schedule = {'id': 'automatic', 'workflow_id': self.workflow_id, 'scope': 'EMS',
                    'system_id': 'EMS', 'factory_id': '', 'identity_user_id': 'operator',
                    'enabled': True, 'revision': 1, 'next_at': 1}
        states = ('queued', 'waiting', 'running')
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('INSERT INTO work_schedules VALUES(?,?,?,?,?,?,?,?)',
                       ('automatic', self.workflow_id, 'EMS', 'operator', 1, 1, 1, json.dumps(schedule)))
            # Simulate persisted due slots from a live scheduler immediately before the restart.
            for stamp, status in enumerate(states, 1):
                leased = ('prior-worker', 12345) if status == 'running' else (None, None)
                slot = {'id': 'slot-' + status, 'schedule': schedule, 'scheduled_at': stamp,
                        'next_due': stamp, 'run_id': run_id, 'state': status}
                db.execute('INSERT INTO work_schedule_slots VALUES(?,?,?,?,?,?,?,?,?)',
                           (slot['id'], 'automatic', self.workflow_id, 'EMS', stamp, status,
                            *leased, json.dumps(slot)))
        self.open_guide(self.db)
        denied = self.command('operations', 'execute_scope', initial['revision'], run_id=run_id, check=False)
        self.assertEqual(denied['error']['code'], 'workflow_archived')
        for _ in range(2):
            worker = workflow._production_service().operations
            self.assertFalse(asyncio.run(worker.process_once()))
            self.assertEqual(self.provider.records, [])
            self.assertEqual(self.state(run_id)['attempts'], [])
            with closing(sqlite3.connect(self.db)) as db:
                self.assertEqual(db.execute('SELECT enabled FROM work_schedules').fetchone(), (0,))
                self.assertEqual(db.execute('SELECT enabled FROM work_guide_archive_schedules').fetchone(), (1,))
                classified = db.execute("SELECT status,worker,lease,json_extract(data,'$.reason') "
                                        "FROM work_scope_runs WHERE id=?", (scope['id'],)).fetchone()
                self.assertEqual(classified, ('unknown', None, None, 'workflow_archived'))
                self.assertEqual(db.execute('SELECT status FROM work_guide_archive_scope_runs').fetchone(), ('running',))
                slots = list(db.execute('SELECT status,worker,lease FROM work_schedule_slots ORDER BY scheduled_at'))
                self.assertEqual(slots, [('blocked', None, None), ('blocked', None, None), ('unknown', None, None)])
                self.assertEqual([row[0] for row in db.execute('SELECT status FROM work_guide_archive_schedule_slots '
                                                               'ORDER BY scheduled_at')], list(states))
            self.open_guide(self.db)

    def test_retry_after_interrupted_save_resumes_same_draft(self):
        def interrupted(route, data=None, query=None):
            if data and data.get('action') == 'save_draft':
                raise OSError('interrupted')
            return self.call(route, data, query)

        with self.assertRaises(OSError):
            provision(interrupted, self.spec, 'EMS')
        drafts = self.call('workspace', query={'system_id': 'EMS'})['workflows']
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]['name'], WORKING_TITLE)
        self.assertIsNone(drafts[0]['published_version'])
        created = provision(self.call, self.spec, 'EMS')
        self.assertEqual(created['workflow_id'], drafts[0]['id'])
        self.assertEqual(provision(self.call, self.spec, 'EMS')['status'], 'existing')
        self.assertEqual(len(self.call('workspace', query={'system_id': 'EMS'})['workflows']), 1)

    def test_same_name_preserves_unrelated_draft_and_catalog(self):
        self.command('workspace/command', 'create_workflow', actor='admin', system_id='EMS', name=TITLE)
        with self.assertRaisesRegex(SetupError, '같은 이름'):
            provision(self.call, self.spec, 'EMS')
        drafts = self.call('workspace', query={'system_id': 'EMS'})['workflows']
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]['revision'], 1)
        self.assertIsNone(drafts[0]['published_version'])
        self.assertFalse(self.provider.records)
        with closing(sqlite3.connect(self.db)) as database:
            self.assertEqual(database.execute('SELECT COUNT(*) FROM work_api_operations').fetchone()[0], 0)

    def test_two_authenticated_gets_handoff_and_persistent_history(self):
        run = self.create_run()
        first = self.run_step(run, 'page')
        self.assertEqual(first['status'], 'succeeded', first)
        self.assertEqual(first['result']['items'][0]['row']['id'], PAGE_ID)
        self.assertEqual(first['result']['items'][0]['row']['title'], PAGE['title'])
        denied = self.command('operations', 'execute_job', self.state(run)['revision'], job_id='children',
                              run_id=run, check=False)
        self.assertFalse(denied['ok'])
        self.assertEqual(len(self.provider.records), 1)
        self.confirm(run, first, 'page')
        second = self.run_step(run, 'children')
        self.assertEqual(second['status'], 'succeeded', second)
        self.assertEqual([item['row']['title'] for item in second['result']['items']], [p['title'] for p in CHILDREN])
        self.assertEqual(self.provider.records, [
            ('/rest/api/content/' + PAGE_ID, {}, True),
            ('/rest/api/content/' + PAGE_ID + '/child/page', {'limit': ['5']}, True)])
        self.confirm(run, second, 'children')
        self.command('workspace/command', 'close_run', self.state(run)['revision'], run_id=run)
        with workflow_server(self.db, self.users) as reopened:
            state = self.state(run, server=reopened)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['attempts']), 2)
        self.assertEqual({a['result']['http_status'] for a in state['attempts']}, {200})
        self.assertNotIn(self.provider.bearer, json.dumps(state))
        self.assertEqual(len(self.provider.records), 2)

    def test_visible_parent_may_have_zero_visible_children(self):
        self.provider.children = []
        run = self.create_run()
        self.confirm(run, self.run_step(run, 'page'), 'page')
        children = self.run_step(run, 'children')
        result = children['result']
        self.assertEqual((result['http_status'], result['count'], result['items']), (200, 0, []))
        self.assertEqual(result['completeness'], 'empty')
        self.confirm(run, children, 'children')
        self.assertEqual(self.state(run)['jobs']['children']['status'], 'completed')

    def test_incorrect_bearer_is_an_upstream_401_without_second_call(self):
        run = self.create_run()
        with patch.dict(os.environ, {'EES_CONFLUENCE_TEST_HEADER': 'Bearer fixture-invalid'}):
            attempt = self.run_step(run, 'page', check=False)
        self.assertEqual(attempt['status'], 'failed')
        self.assertEqual(attempt['result']['http_status'], 401)
        self.assertEqual(self.provider.records, [('/rest/api/content/' + PAGE_ID, {}, False)])
        self.assertNotIn('private fixture diagnostic', json.dumps(self.state(run)))

    def test_confluence_denied_or_hidden_page_records_error_without_followup(self):
        run = self.create_run('404404')
        for status in (404, 403):
            with self.subTest(status=status):
                self.provider.upstream_status = status
                attempt = self.run_step(run, 'page', check=False)
                self.assertEqual(attempt['status'], 'failed')
                self.assertEqual(attempt['result']['http_status'], status)
        self.assertEqual(self.provider.records, [('/rest/api/content/404404', {}, True)] * 2)
        self.assertNotIn('private fixture diagnostic', json.dumps(self.state(run)))


    # ---- 2026-11-20 · design mock 20: the guide asks for a document's address ----
    def v1_guide_file(self, example=True):
        """The guide document as programs before 2026-11-20 shipped it, rebuilt from today's file: with the field
        example of 89bd377 or, as first shipped in b031cb6 (the in-house installs), without it."""
        document = json.loads(workflow.WorkflowService.GUIDE_FILE.read_text(encoding='utf-8'))
        guide = document['x-ees-procedure-example']
        guide['description'] = '페이지 ID를 한 번 입력해 기준 문서를 확인하고 직계 하위 문서를 최대 5건 조회합니다.'
        definition = guide['definition']
        del definition['description']
        page, children = definition['nodes']['page'], definition['nodes']['children']
        page['name'], children['name'] = '기준 문서 확인', '하위 문서 목록 조회'
        page['instructions'] = 'Confluence 페이지 정보의 페이지 ID를 입력하세요. 실행 결과의 제목과 ID가 기준 문서와 일치하면 확정하세요.'
        children['instructions'] = '확정한 기준 문서 바로 아래의 페이지를 최대 5건 조회합니다. 제목을 확인하고 목록을 확정하세요.'
        page['api_binding']['outputs'] = children['api_binding']['outputs'] = ['title', 'id', 'type']
        field = page['inputs'][0]
        field.update(name='페이지 ID', example='123456789')
        del field['accepts']
        if not example:
            del field['example']
        known = {True: '4574fc1dc2c0d0b134e1a3b889a7e44cd54d5112ae6c12d78c74d2d431d85abd',
                 False: 'd87bbfd4045033301282bbbad9c6636785ee9d733b32bd8353f77c0a7d760572'}
        self.assertEqual(workflow._hash(dict(definition, id='guide-confluence-documents')), known[example],
                         'the rebuilt v1 guide differs from what was shipped')
        self.assertIn(known[example], workflow.WorkflowService.CONFLUENCE_GUIDE_V1)
        path = self.db.with_name(f'guide-v1-{example}.json')
        path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        return path

    def open_v1_guide(self, database, example=True):
        """A database the earlier program set up: the v1 guide installed once, no later wording applied."""
        with patch.object(workflow.WorkflowService, 'GUIDE_FILE', self.v1_guide_file(example)):
            self.open_guide(database)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DELETE FROM work_product_guides WHERE id='confluence-documents-v2'")

    def guide(self):
        return self.call('workspace', query={'workflow_id': 'guide-confluence-documents'})['workflow']

    def test_guide_takes_the_address_a_person_copies(self):
        database = self.db.with_name('address-guide.sqlite3')
        self.open_guide(database)
        guide = self.guide()
        nodes = guide['published']['nodes']
        self.assertEqual(guide['published']['description'], '문서 주소를 넣으면 그 문서와 바로 아래 문서를 찾아 줍니다.')
        self.assertEqual((nodes['page']['name'], nodes['children']['name']), ('기준 문서 찾기', '하위 문서 찾기'))
        self.assertEqual({key: nodes['page']['inputs'][0][key] for key in ('name', 'accepts')},
                         {'name': '문서 주소', 'accepts': 'confluence_page'})
        self.command('workspace/command', 'save_access', actor='admin', system_id='EMS', factory_id='*',
                     roles=['participant'], principal_kind='user', principal_id='operator')
        for text, said in (('점검 기준서', 'Confluence 문서 주소가 아니에요'),
                           ('https://wiki.example.com/display/EMS/Inspection', '문서 번호가 없는 주소예요'),
                           ('https://wiki.example.com/pages/viewpage.action?pageId=12x', 'Confluence 문서 주소가 아니에요')):
            with self.subTest(text=text):
                refused = self.command('workspace/command', 'start_run', guide['revision'], check=False,
                                       workflow_id=guide['id'], inputs={'page-id': text})
                self.assertFalse(refused['ok'])
                self.assertIn('page-id: ' + said, json.dumps(refused, ensure_ascii=False))
        address = 'https://wiki.example.com/pages/viewpage.action?pageId=' + PAGE_ID
        run = self.command('workspace/command', 'start_run', guide['revision'], workflow_id=guide['id'],
                           inputs={'page-id': address})['run_id']
        # The run keeps what the person typed; the API is called with the page number in it.
        self.assertEqual(self.state(run)['inputs'], {'page-id': address})
        first = self.run_step(run, 'page')
        self.assertEqual(first['status'], 'succeeded')
        self.assertEqual(list(first['result']['items'][0]['row']), ['title', 'id'])
        self.confirm(run, first, 'page')
        children = self.run_step(run, 'children')
        self.confirm(run, children, 'children')
        self.command('workspace/command', 'close_run', self.state(run)['revision'], run_id=run)
        self.assertEqual(self.provider.records, [('/rest/api/content/' + PAGE_ID, {}, True),
                                                 ('/rest/api/content/' + PAGE_ID + '/child/page', {'limit': ['5']}, True)])
        # Another address form and a bare number reach the same page.
        for text in ('https://wiki.example.com/spaces/EMS/pages/' + PAGE_ID + '/Title', PAGE_ID):
            with self.subTest(text=text):
                again = self.command('workspace/command', 'start_run', self.guide()['revision'], workflow_id=guide['id'],
                                     inputs={'page-id': text})['run_id']
                self.assertEqual(self.run_step(again, 'page')['status'], 'succeeded')
                self.assertEqual(self.provider.records[-1], ('/rest/api/content/' + PAGE_ID, {}, True))
                self.command('workspace/command', 'cancel_run', self.state(again)['revision'], run_id=again, reason='시험')

    def test_input_kind_is_checked_when_a_procedure_is_saved(self):
        check = import_module(package.__name__ + '.ees_workflow_workspace').definition_check
        base = dict(workflow.WorkflowService._work_guide_example()['definition'], id='guide-copy', system_id='EMS')
        self.assertEqual(check(base)[0], [])
        for change, valid in ((('accepts', 'confluence_page'), True), (('accepts', 'web_page'), False),
                              (('type', 'number'), False)):
            with self.subTest(change=change):
                definition = deepcopy(base)
                definition['nodes']['page']['inputs'][0][change[0]] = change[1]
                errors = [error for error in check(definition)[0] if '받는 값의 종류' in error]
                self.assertEqual(errors, [] if valid else ['page-id: 받는 값의 종류를 확인해 주세요.'])

    def test_untouched_v1_guide_takes_the_new_wording_and_open_runs_keep_theirs(self):
        for example in (False, True):
            with self.subTest(example=example):
                self.check_v1_upgrade(self.db.with_name(f'v1-guide-{example}.sqlite3'), example)

    def check_v1_upgrade(self, database, example):
        self.open_v1_guide(database, example)
        guide = self.guide()
        self.assertEqual((guide['published_version'], guide['published']['nodes']['page']['name']), (1, '기준 문서 확인'))
        self.command('workspace/command', 'save_access', actor='admin', system_id='EMS', factory_id='*',
                     roles=['participant'], principal_kind='user', principal_id='operator')
        old_run = self.command('workspace/command', 'start_run', guide['revision'], workflow_id=guide['id'],
                               inputs={'page-id': PAGE_ID})['run_id']
        self.open_guide(database)
        guide = self.guide()
        self.assertEqual((guide['published_version'], guide['revision']), (2, 2))
        self.assertEqual(guide['published']['nodes']['page']['name'], '기준 문서 찾기')
        self.assertEqual(guide['draft']['nodes']['page']['inputs'][0]['accepts'], 'confluence_page')
        # The round started before keeps the version it started with and still runs.
        self.assertEqual(self.state(old_run)['definition']['nodes']['page']['name'], '기준 문서 확인')
        self.assertEqual(self.run_step(old_run, 'page')['status'], 'succeeded')
        # The wording is applied once: a later start changes nothing.
        self.open_guide(database)
        self.assertEqual((self.guide()['published_version'], self.guide()['revision']), (2, 2))
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual([row[0] for row in db.execute(
                "SELECT version FROM work_versions WHERE workflow_id='guide-confluence-documents' ORDER BY version")], [1, 2])

    def test_v1_guide_an_administrator_changed_keeps_its_content(self):
        for change in ('saved', 'unpublished'):
            with self.subTest(change=change):
                database = self.db.with_name(f'edited-guide-{change}.sqlite3')
                self.open_v1_guide(database)
                guide = self.guide()
                if change == 'saved':
                    draft = deepcopy(guide['draft'])
                    draft['nodes']['page']['name'] = '우리 팀 기준 문서'
                    self.command('workspace/command', 'save_draft', guide['revision'], actor='admin',
                                 workflow_id=guide['id'], definition=draft)
                else:
                    self.command('workspace/command', 'unpublish_workflow', guide['revision'], actor='admin',
                                 workflow_id=guide['id'])
                before = self.guide()
                self.open_guide(database)
                after = self.guide()
                self.assertEqual({key: after[key] for key in ('revision', 'published_version')},
                                 {key: before[key] for key in ('revision', 'published_version')})
                self.assertEqual(after['draft'], before['draft'])
                self.assertNotIn('accepts', after['draft']['nodes']['page']['inputs'][0])


if __name__ == '__main__':
    unittest.main()
