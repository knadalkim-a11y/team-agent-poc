"""Verify the shipped Confluence registration script with product HTTP routes and HTTPS."""
from contextlib import contextmanager
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
from unittest.mock import patch
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


@contextmanager
def workflow_server(database, client_users):
    """Serve the product's routes; substitute only the signed-in identity and isolated DB."""
    service = workflow.WorkflowService(database, client_users.get, lambda _: None)
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
        with sqlite3.connect(self.db) as database:
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
