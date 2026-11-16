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


if __name__ == '__main__':
    unittest.main()
