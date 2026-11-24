"""Trying a saved draft before publication (mock 21) and separate save and publish.

Synthetic identities, temporary SQLite and a local HTTP service only. A try is a
work_runs row with mode='try' that the previous program sees as a cancelled
record; only the browser window holding its key can read or change it.
"""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException

import test_ees_work_workspace as base

workflow, workspace = base.workflow, base.workspace

WINDOW = 'window-a-' + 'a' * 32
OTHER = 'window-b-' + 'b' * 32
ITEMS = [{'id': 'leak', 'name': '누설 없음'}, {'id': 'valve', 'name': '밸브 정상'}]
CHECK = {'id': 'check', 'name': '설비 점검', 'mode': 'human', 'inputs': [], 'result_block': 'checklist', 'confirmation_items': ITEMS}
TOOL = {'id': 'tool', 'name': '문서 조회', 'mode': 'tool', 'result_block': 'human_confirm', 'human_confirmation': True,
        'inputs': [{'id': 'page', 'type': 'text', 'scope': 'run', 'required': True}],
        'tool_reference': {'tool_id': 'native', 'function': 'read', 'content_hash': 'sha'}, 'argument_bindings': {'id': {'input': 'page'}}}
CONFIRM = {'id': 'confirm', 'name': '결과 확인', 'mode': 'human', 'inputs': [], 'result_block': 'human_confirm'}
# Everything a run owns; the try deletion and the sweep must empty each one.
OWNED = ('work_runs', 'work_jobs', 'work_attempts', 'work_decisions', 'work_review_revisions', 'work_job_claims',
         'work_scope_runs', 'work_shared_tool_pins', 'work_chat_links', 'work_receipts', 'work_audit',
         'work_operation_receipts', 'work_operation_events')


class Bridge:
    """A Native read tool whose call can be held open to keep a job running."""
    def __init__(self):
        self.calls, self.hold = [], None

    async def check(self, user, reference):
        return {'reference': deepcopy(reference), 'state': 'allowed'}

    async def invoke(self, user, reference, arguments, context):
        self.calls.append((arguments, context))
        if self.hold:
            await self.hold.wait()
        return {'status': 'succeeded', 'completeness': 'complete', 'data': {'count': 1}}


@contextmanager
def page_service():
    """GET /pages?id=… answers a page, or 404 for 'missing'; POST is recorded and refused."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlsplit(self.path)
            page = (parse_qs(request.query).get('id') or [''])[0]
            self.server.requests.append(('GET', request.path, page))
            if request.path != '/pages' or page == 'missing':
                self.send_error(404)
                return
            payload = json.dumps({'results': [{'title': 'Page ' + page, 'id': page}]}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            self.server.requests.append(('POST', self.path, ''))
            self.send_error(500)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        server.requests = []
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


class TryTests(unittest.IsolatedAsyncioTestCase):
    # Reuse the workspace fixture's helpers only, not its tests.
    new_service = base.WorkspaceTests.new_service
    command = base.WorkspaceTests.command
    create = base.WorkspaceTests.create
    start = base.WorkspaceTests.start
    state = base.WorkspaceTests.state

    async def asyncSetUp(self):
        await base.WorkspaceTests.asyncSetUp(self)
        self.bridge = Bridge()
        self.service.operations.bridge = self.bridge
        self.now = datetime.now(timezone.utc).timestamp()
        self.service.operations.clock = lambda: self.now
        self.addAsyncCleanup(self.service.operations.stop)

    async def procedure(self, jobs=(CHECK,), *, publish=False, category=None, mode=None, name='시험할 절차'):
        created = await self.command('create_workflow', name=name, system_id='EMS', **({'mode': mode} if mode else {}))
        self.assertTrue(created['ok'], created)
        key, definition = created['workflow_id'], created['workflow']['draft']
        root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['t']
        definition['nodes']['t'] = {'id': 't', 'type': 't', 'name': '점검', 'parent': root, 'children': [], 'deps': []}
        for job in jobs:
            definition['nodes']['t']['children'].append(job['id'])
            definition['nodes'][job['id']] = {'type': 'j', 'parent': 't', 'children': [], 'deps': [], **deepcopy(job)}
        if category:
            definition['category'] = category
        saved = await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=1)
        self.assertTrue(saved['ok'], saved)
        revision = saved['revision']
        if publish:
            published = await self.command('publish_workflow', workflow_id=key, expected_revision=revision)
            self.assertTrue(published['ok'], published)
            revision = published['revision']
        return key, definition, revision

    async def try_open(self, key, window=WINDOW, actor='a', **values):
        return await self.command('try_open', actor=actor, workflow_id=key, system_id='EMS', try_window=window, **values)

    async def opened(self, key, window=WINDOW, actor='a', **values):
        result = await self.try_open(key, window, actor, **values)
        self.assertTrue(result['ok'], result)
        return result['run']

    async def try_state(self, key, window=WINDOW, actor='a', **values):
        return await self.service.try_state(self.users[actor], {'workflow_id': key, 'system_id': 'EMS', 'try_window': window, **values})

    async def on_try(self, action, run, window=WINDOW, actor='a', **values):
        values.setdefault('expected_revision', run['revision'])
        return await self.command(action, actor=actor, run_id=run['id'], try_window=window, **values)

    async def execute(self, run, job_id='tool', window=WINDOW, actor='a', **values):
        body = {'action': 'execute_job', 'run_id': run['id'], 'job_id': job_id, 'expected_revision': run['revision'],
                'request_id': str(uuid4()), 'try_window': window, **values}
        return await self.service.operations.command(self.users[actor], body)

    def row(self, run_id):
        with self.service._db() as db:
            return dict(db.execute('SELECT * FROM work_runs WHERE id=?', (run_id,)).fetchone() or {})

    def owned(self, run_id):
        """Rows of every table that belong to one run."""
        mark = '"run_id":"' + run_id + '"'
        with self.service._db() as db:
            attempts = [row[0] for row in db.execute('SELECT id FROM work_attempts WHERE run_id=?', (run_id,))]
            marks = ','.join('?' * len(attempts)) or "''"
            count = lambda sql, *args: db.execute(sql, args).fetchone()[0]
            return {
                'work_runs': count('SELECT COUNT(*) FROM work_runs WHERE id=?', run_id),
                'work_jobs': count('SELECT COUNT(*) FROM work_jobs WHERE run_id=?', run_id),
                'work_attempts': len(attempts),
                'work_decisions': count('SELECT COUNT(*) FROM work_decisions WHERE run_id=?', run_id),
                'work_review_revisions': count(f'SELECT COUNT(*) FROM work_review_revisions WHERE attempt_id IN ({marks})', *attempts),
                'work_job_claims': count(f'SELECT COUNT(*) FROM work_job_claims WHERE attempt_id IN ({marks})', *attempts),
                'work_scope_runs': count('SELECT COUNT(*) FROM work_scope_runs WHERE run_id=?', run_id),
                'work_shared_tool_pins': count("SELECT COUNT(*) FROM work_shared_tool_pins WHERE run_kind='work' AND run_id=?", run_id),
                'work_chat_links': count('SELECT COUNT(*) FROM work_chat_links WHERE run_id=?', run_id),
                'work_receipts': count('SELECT COUNT(*) FROM work_receipts WHERE instr(response,?)>0', mark),
                'work_audit': count('SELECT COUNT(*) FROM work_audit WHERE target=?', run_id),
                'work_operation_receipts': count('SELECT COUNT(*) FROM work_operation_receipts WHERE instr(outcome,?)>0', mark),
                'work_operation_events': count(f'SELECT COUNT(*) FROM work_operation_events WHERE target=? OR target IN ({marks})', run_id, *attempts),
            }

    def fill(self, run_id):
        """Add synthetic rows to the tables a simple procedure does not reach."""
        with self.service._db(write=True) as db:
            attempt = db.execute('SELECT id FROM work_attempts WHERE run_id=? ORDER BY created_at LIMIT 1', (run_id,)).fetchone()[0]
            db.execute("INSERT INTO work_review_revisions VALUES(?,1,'synthetic draft','a','2026-11-24T00:00:00.000+00:00',NULL)", (attempt,))
            db.execute("INSERT INTO work_scope_runs VALUES(?,?,'a','completed',NULL,NULL,'{}')", ('scope-' + run_id, run_id))
            db.execute("INSERT INTO work_shared_tool_pins VALUES('work',?,'synthetic-tool','{}')", (run_id,))
            db.execute("INSERT INTO work_chat_links VALUES('a','chat-a',?,'2026-11-24T00:00:00.000+00:00')", (run_id,))
            db.execute("INSERT INTO work_operation_events(target,actor,kind,created_at,data) VALUES(?,'a','read_retry_timeout',0,'{}')", (attempt,))

    async def worked_try(self, key, window=WINDOW):
        """A try with ticks, a tool result and a verdict in it."""
        run = await self.opened(key, window)
        ticked = await self.on_try('human_confirm', run, window, job_id='check', item_id='leak')
        self.assertTrue(ticked['ok'], ticked)
        saved = await self.on_try('save_inputs', ticked['run'], window, inputs={'page': '42'})
        self.assertTrue(saved['ok'], saved)
        executed = await self.execute(saved['run'], window=window)
        self.assertEqual(executed['attempt']['status'], 'succeeded', executed)
        current = (await self.try_state(key, window))['try']
        decided = await self.on_try('decide', current, window, job_id='tool', item_id='job', verdict='completed',
                                    result_revision=executed['attempt']['number'])
        self.assertTrue(decided['ok'], decided)
        return decided['run']

    # ---- Save and publish are separate ----

    async def test_save_keeps_the_published_version_and_publish_uses_the_saved_draft(self):
        key, definition, revision = await self.procedure(publish=True)
        before = (await self.state('a', workflow_id=key))['workflow']
        self.assertEqual((before['published_version'], before['unpublished_changes']), (1, False))
        changed = deepcopy(definition)
        changed['nodes']['check']['confirmation_items'].append({'id': 'gauge', 'name': '압력계 정상'})
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=changed, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        self.assertEqual(saved['draft_hash'], workspace._draft_hash(changed))
        self.assertNotIn('published_version', saved)
        after = (await self.state('a', workflow_id=key))['workflow']
        self.assertEqual(after['published_version'], 1)
        self.assertEqual(after['versions'], before['versions'])
        self.assertEqual(after['published'], before['published'])
        self.assertEqual((after['draft_hash'], after['unpublished_changes']), (saved['draft_hash'], True))
        published = await self.command('publish_workflow', actor='a', workflow_id=key, expected_revision=saved['revision'])
        self.assertEqual((published['version'], published['draft_hash']), (2, saved['draft_hash']))
        state = (await self.state('a', workflow_id=key))['workflow']
        self.assertEqual({key: value for key, value in state['published'].items() if key != 'resource_versions'}, changed)
        self.assertFalse(state['unpublished_changes'])
        hidden = await self.command('unpublish_workflow', actor='a', workflow_id=key, expected_revision=published['revision'])
        state = (await self.state('a', workflow_id=key))['workflow']
        self.assertIsNone(state['published_version'])
        self.assertEqual([item['version'] for item in state['versions']], [2, 1])
        self.assertFalse(state['unpublished_changes'], 'an unpublished procedure has nothing published to differ from')
        # 게시 with unsaved edits saves and publishes in one transaction (kept for that and for old tabs).
        changed['name'] = '저장과 게시를 한 번에'
        atomic = await self.command('save_draft', actor='a', workflow_id=key, definition=changed,
                                    expected_revision=hidden['revision'], publication_state='published')
        self.assertEqual((atomic['published_version'], atomic['draft_hash']), (3, workspace._draft_hash(changed)))

    async def test_draft_hash_ignores_key_order_and_resource_versions(self):
        draft = {'id': 'w', 'name': '절차', 'nodes': {'p': {'id': 'p', 'type': 'p'}}, 'system_id': 'EMS'}
        reordered = {key: draft[key] for key in reversed(list(draft))}
        published = {**draft, 'resource_versions': {'skills': {'s': {'revision': 3, 'content_hash': 'x'}}}}
        self.assertEqual(len({workspace._draft_hash(draft), workspace._draft_hash(reordered), workspace._draft_hash(published)}), 1)
        self.assertNotEqual(workspace._draft_hash(draft), workspace._draft_hash({**draft, 'name': '바뀐 절차'}))
        key, definition, revision = await self.procedure(publish=True)
        reordered = {name: definition[name] for name in reversed(list(definition))}
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=reordered, expected_revision=revision)
        state = (await self.state('a', workflow_id=key))['workflow']
        self.assertEqual(state['draft_hash'], saved['draft_hash'])
        self.assertFalse(state['unpublished_changes'], 'key order and resource_versions are not content changes')

    async def test_draft_saved_at_is_the_last_content_save_not_a_publication(self):
        key, definition, revision = await self.procedure()
        with self.service._db() as db:
            saved_at = db.execute("SELECT MAX(created_at) FROM work_audit WHERE target=? AND action='save_draft'", (key,)).fetchone()[0]
        self.assertEqual((await self.state('a', workflow_id=key))['workflow']['draft_saved_at'], saved_at)
        published = await self.command('publish_workflow', actor='a', workflow_id=key, expected_revision=revision)
        hidden = await self.command('unpublish_workflow', actor='a', workflow_id=key, expected_revision=published['revision'])
        self.assertTrue(hidden['ok'], hidden)
        state = (await self.state('a', workflow_id=key))['workflow']
        self.assertEqual(state['draft_saved_at'], saved_at)
        self.assertNotEqual(state['updated_at'], saved_at)
        created = await self.command('create_workflow', actor='a', name='새 절차', system_id='EMS')
        fresh = (await self.state('a', workflow_id=created['workflow_id']))['workflow']
        with self.service._db() as db:
            made = db.execute("SELECT created_at FROM work_audit WHERE target=? AND action='create_workflow'", (created['workflow_id'],)).fetchone()[0]
        self.assertEqual(fresh['draft_saved_at'], made)

    async def test_work_list_shows_published_values_until_the_rename_is_published(self):
        await self.command('save_access', principal_kind='user', principal_id='c', system_id='EMS', factory_id='*', roles=['participant'])
        key, definition, revision = await self.procedure(publish=True, name='게시한 이름')
        renamed = deepcopy(definition)
        renamed.update(name='저장만 한 이름', category='incident')
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=renamed, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        for actor in ('a', 'c'):
            listed = next(item for item in (await self.state(actor))['workflows'] if item['id'] == key)
            self.assertEqual((listed['name'], listed['category']), ('게시한 이름', 'ops'), actor)
        manager = next(item for item in (await self.state('a'))['workflows'] if item['id'] == key)
        self.assertEqual(manager['draft']['name'], '저장만 한 이름')
        self.assertTrue(manager['unpublished_changes'])
        member = next(item for item in (await self.state('c'))['workflows'] if item['id'] == key)
        self.assertFalse({'draft', 'draft_hash', 'draft_saved_at', 'unpublished_changes'} & set(member))
        unpublished, _, _ = await self.procedure(name='게시 전 절차')
        draft_only = next(item for item in (await self.state('a'))['workflows'] if item['id'] == unpublished)
        self.assertEqual(draft_only['name'], '게시 전 절차')
        published = await self.command('publish_workflow', actor='a', workflow_id=key, expected_revision=saved['revision'])
        self.assertTrue(published['ok'], published)
        listed = next(item for item in (await self.state('c'))['workflows'] if item['id'] == key)
        self.assertEqual((listed['name'], listed['category']), ('저장만 한 이름', 'incident'))

    async def test_real_start_naming_the_published_version_is_not_blocked_by_a_draft_save(self):
        key, definition, revision = await self.procedure([CONFIRM], publish=True, category='incident')
        shown = revision
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition={**definition, 'description': '다른 창의 저장'}, expected_revision=revision)
        started = await self.command('start_run', actor='a', workflow_id=key, expected_revision=shown, version=1)
        self.assertTrue(started['ok'], started)
        self.assertEqual(started['run']['version'], 1)
        old_client = await self.command('start_run', actor='a', workflow_id=key, expected_revision=shown)
        self.assertEqual(old_client['error']['code'], 'revision_conflict')
        published = await self.command('publish_workflow', actor='a', workflow_id=key, expected_revision=saved['revision'])
        stale = await self.command('start_run', actor='a', workflow_id=key, expected_revision=saved['revision'], version=1)
        self.assertEqual(stale['error'], {'code': 'publication_changed', 'message': '게시된 판이 바뀌었습니다. 화면을 새로 고친 뒤 다시 시작해 주세요.'})
        older = await self.command('start_run', actor='a', workflow_id=key, expected_revision=published['revision'], version=1)
        self.assertEqual(older['run']['version'], 1, 'an explicit earlier version with the current revision still starts')
        current = await self.command('start_run', actor='a', workflow_id=key, expected_revision=shown, version=2)
        self.assertEqual(current['run']['version'], 2)
        hidden = await self.command('unpublish_workflow', actor='a', workflow_id=key, expected_revision=published['revision'])
        for expected in (shown, hidden['revision']):
            blocked = await self.command('start_run', actor='a', workflow_id=key, expected_revision=expected, version=2)
            self.assertEqual(blocked['error']['code'], 'publication_required')

    async def test_scheduled_start_survives_a_draft_save_between_its_two_reads(self):
        key, definition, revision = await self.procedure([CONFIRM], publish=True, mode='periodic')
        self.now = datetime(2026, 10, 2, 10, tzinfo=timezone.utc).timestamp()
        schedule = {'workflow_id': key, 'version': 1, 'rule': {'frequency': 'daily', 'timezone': 'UTC', 'anchor': '2026-10-02T10:00:00'},
                    'inputs': {}, 'job_ids': [], 'delegated': True}
        saved = await self.service.operations.command(self.users['a'], {'action': 'schedule_save', 'request_id': str(uuid4()), 'expected_revision': 0, 'schedule': schedule})
        self.assertTrue(saved['ok'], saved)
        original = self.service.workspace_command

        async def save_first(user, body):
            if body.get('action') == 'start_run':
                with self.service._db() as db:
                    current = db.execute('SELECT revision FROM work_definitions WHERE id=?', (key,)).fetchone()[0]
                edited = await original(self.users['a'], {'action': 'save_draft', 'request_id': str(uuid4()), 'workflow_id': key,
                                                          'expected_revision': current, 'definition': {**definition, 'description': '예약 사이의 저장'}})
                self.assertTrue(edited['ok'], edited)
            return await original(user, body)

        with patch.object(self.service, 'workspace_command', save_first):
            await self.service.operations.process_once()
        with self.service._db() as db:
            slot = json.loads(db.execute('SELECT data FROM work_schedule_slots').fetchone()[0])
            runs = db.execute("SELECT version FROM work_runs WHERE mode<>'try'").fetchall()
        self.assertEqual(slot['state'], 'cycle_started', slot)
        self.assertEqual([row[0] for row in runs], [1])

    async def test_work_settings_serve_the_published_version_and_the_saved_draft(self):
        # Independent review 2026-11-24 (R5): saving no longer publishes, so the two differ.
        limit = {'id': 'limit', 'type': 'number', 'scope': 'workflow'}
        message = 'limit: 삭제되거나 저장 범위가 바뀐 업무 설정을 먼저 정리해 주세요.'
        # A field only the saved draft declares: its default blocks no start, schedule or try of v1.
        key, definition, revision = await self.procedure([CONFIRM], publish=True, mode='periodic')
        self.now = datetime(2026, 10, 2, 10, tzinfo=timezone.utc).timestamp()
        schedule = {'workflow_id': key, 'version': 1, 'rule': {'frequency': 'daily', 'timezone': 'UTC', 'anchor': '2026-10-02T10:00:00'},
                    'inputs': {}, 'job_ids': [], 'delegated': True}
        scheduled = await self.service.operations.command(self.users['a'], {'action': 'schedule_save', 'request_id': str(uuid4()), 'expected_revision': 0, 'schedule': schedule})
        self.assertTrue(scheduled['ok'], scheduled)
        draft = deepcopy(definition)
        draft['nodes']['confirm']['inputs'] = [limit]
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=draft, expected_revision=revision)
        stored = await self.command('save_settings', actor='a', workflow_id=key, values={'limit': 3}, expected_revision=0)
        self.assertTrue(stored['ok'], stored)
        await self.service.operations.process_once()
        with self.service._db() as db:
            slot = json.loads(db.execute('SELECT data FROM work_schedule_slots').fetchone()[0])
        self.assertEqual(slot['state'], 'cycle_started', slot)
        cancelled = await self.command('cancel_run', actor='a', run_id=slot['run_id'], expected_revision=self.row(slot['run_id'])['revision'], reason='정리')
        self.assertTrue(cancelled['ok'], cancelled)
        started = await self.command('start_run', actor='a', workflow_id=key, expected_revision=saved['revision'], version=1)
        self.assertTrue(started['ok'], started)
        self.assertEqual(started['run']['jobs']['confirm']['effective_inputs'], {})
        self.assertEqual((await self.opened(key))['jobs']['confirm']['effective_inputs'], {'limit': 3})
        # A field only the published version declares: still set from the work side, checked
        # against that declaration, and a try of the draft is not refused for it.
        key, definition, revision = await self.procedure([{**CONFIRM, 'inputs': [limit]}], publish=True, name='게시판의 설정')
        draft = deepcopy(definition)
        draft['nodes']['confirm']['inputs'] = []
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=draft, expected_revision=revision)
        stored = await self.command('save_settings', actor='a', workflow_id=key, values={'limit': 3}, expected_revision=0)
        self.assertTrue(stored['ok'], stored)
        for values, refusal in (({'limit': '셋'}, 'limit: number 입력 형식과 선택지를 확인해 주세요.'),
                                ({'limit': 3, 'nowhere': 1}, 'nowhere: 선언되지 않은 입력입니다.')):
            refused = await self.command('save_settings', actor='a', workflow_id=key, values=values, expected_revision=stored['revision'])
            self.assertEqual(refused['error'], {'code': 'invalid_inputs', 'message': refusal}, values)
        started = await self.command('start_run', actor='a', workflow_id=key, expected_revision=saved['revision'], version=1)
        self.assertEqual(started['run']['jobs']['confirm']['effective_inputs'], {'limit': 3})
        tried = await self.opened(key)
        self.assertEqual(tried['jobs']['confirm']['effective_inputs'], {})
        # Checking for publication stays strict (advisory): it names the setting the draft leaves unused.
        validated = await self.command('validate_workflow', actor='a', workflow_id=key, expected_revision=saved['revision'])
        self.assertIn(message, validated['validation']['errors'])
        # A key the run's own definition declares with another scope still blocks it.
        draft['nodes']['confirm']['inputs'] = [{**limit, 'scope': 'run'}]
        resaved = await self.command('save_draft', actor='a', workflow_id=key, definition=draft, expected_revision=saved['revision'])
        self.assertTrue(resaved['ok'], resaved)
        refused = await self.on_try('try_restart', tried)
        self.assertEqual(refused['error']['code'], 'execution_not_ready')
        self.assertIn(message, refused['error']['message'].split('\n'))

    # ---- Trying a draft ----

    async def test_try_open_makes_a_try_of_an_unpublished_draft_stored_for_rollback(self):
        key, definition, revision = await self.procedure([CHECK, TOOL])
        result = await self.try_open(key)
        self.assertTrue(result['ok'], result)
        run = result['run']
        self.assertEqual((result['run_id'], result['workflow_id'], result['revision']), (run['id'], key, 1))
        self.assertEqual((run['mode'], run['status'], run['version'], run['closed_at']), ('try', 'open', 0, None))
        self.assertEqual({name: value for name, value in run['definition'].items() if name != 'resource_versions'}, definition)
        self.assertEqual(run['definition']['resource_versions'], {'skills': {}})
        workflow_state = (await self.try_state(key))['workflow']
        self.assertEqual(run['try'], {'draft_hash': workflow_state['draft_hash'], 'saved_at': workflow_state['draft_saved_at'], 'changed': [], 'started': False})
        self.assertEqual({job_id: job['status'] for job_id, job in run['jobs'].items()}, {'check': 'pending', 'tool': 'pending'})
        self.assertTrue(run['can_write'])
        stored = self.row(run['id'])
        self.assertEqual((stored['mode'], stored['status'], stored['version'], stored['closed_at'], stored['owner']), ('try', 'cancelled', 0, None, 'a'))
        self.assertEqual((json.loads(stored['sharing']), json.loads(stored['inputs'])), ({'group_ids': []}, {}))
        binding = json.loads(stored['snapshot'])['try']
        self.assertEqual(binding['window'], hashlib.sha256(WINDOW.encode()).hexdigest())
        self.assertNotIn('window', json.dumps(run))
        with sqlite3.connect(self.database) as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn(WINDOW, dump, 'only the hash of the window key is stored')
        self.assertEqual(dump.count(binding['window']), 1, 'the hash stays in the try row, never in receipts')
        # The previous program lists only status NOT IN ('completed','cancelled') as open work.
        with self.service._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM work_runs WHERE status NOT IN ('completed','cancelled')").fetchone())

    async def test_try_open_returns_the_same_try_for_the_window_until_it_starts_over(self):
        key, definition, revision = await self.procedure()
        first = await self.opened(key)
        again = await self.opened(key)
        self.assertEqual(again['id'], first['id'])
        changed = deepcopy(definition)
        changed['nodes']['check']['confirmation_items'].append({'id': 'gauge', 'name': '압력계 정상'})
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=changed, expected_revision=revision)
        kept = await self.opened(key)
        self.assertEqual((kept['id'], kept['try']['draft_hash']), (first['id'], first['try']['draft_hash']))
        state = await self.try_state(key)
        self.assertEqual(state['try']['id'], first['id'])
        self.assertNotEqual(state['try']['try']['draft_hash'], state['workflow']['draft_hash'])
        self.assertEqual(state['workflow']['draft_hash'], saved['draft_hash'])
        self.assertEqual(set(state['workflow']), {'id', 'revision', 'published_version', 'draft_hash', 'draft_saved_at', 'unpublished_changes'})
        self.assertTrue(state['operations']['ok'])
        self.assertEqual(state['operations']['scope_runs'], [])
        empty = await self.try_state(key, window='window-c-' + 'c' * 32)
        self.assertEqual((empty['ok'], empty['try']), (True, None))

    async def test_a_try_follows_the_draft_between_system_wide_and_per_factory(self):
        # Independent review 2026-11-24 (R2): a system-wide try used to match every factory.
        await self.command('save_factory', factory_id='f1', system_id='EMS', name='1공장')
        key, definition, revision = await self.procedure([CHECK])
        definition = deepcopy(definition)
        definition['execution_scope'] = 'system'
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=definition, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        old = await self.opened(key, factory_id='f1')
        other = await self.opened(key, OTHER)
        self.assertEqual((old['factory_id'], other['factory_id']), ('', ''), 'a system-wide try has no factory')
        definition['execution_scope'] = 'factory'
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=definition, expected_revision=saved['revision'])
        self.assertTrue(saved['ok'], saved)
        # The system-wide try is not this draft's try in any factory.
        self.assertIsNone((await self.try_state(key, factory_id='f1'))['try'])
        self.assertIsNone((await self.try_state(key))['try'])
        self.assertEqual((await self.try_open(key))['error']['code'], 'factory_required')
        fresh = await self.opened(key, factory_id='f1')
        self.assertNotEqual(fresh['id'], old['id'])
        self.assertEqual((fresh['factory_id'], fresh['try']['draft_hash']), ('f1', saved['draft_hash']))
        self.assertEqual((await self.try_state(key, factory_id='f1'))['try']['id'], fresh['id'])
        # '처음부터' takes the factory from the current draft and the request. An earlier
        # screen sends none: the try keeps its own factory, and fails without losing the try.
        kept = await self.on_try('try_restart', other, OTHER)
        self.assertEqual(kept['error']['code'], 'factory_required')
        self.assertEqual(self.row(other['id'])['mode'], 'try')
        mismatch = await self.on_try('try_restart', other, OTHER, workflow_id='other-procedure', system_id='EMS', factory_id='f1')
        self.assertEqual(mismatch['error']['code'], 'target_mismatch')
        restarted = await self.on_try('try_restart', other, OTHER, workflow_id=key, system_id='EMS', factory_id='f1')
        self.assertTrue(restarted['ok'], restarted)
        self.assertEqual((restarted['run']['factory_id'], self.row(other['id'])), ('f1', {}))
        self.assertEqual((await self.try_state(key, OTHER, factory_id='f1'))['try']['id'], restarted['run_id'])
        # And back: a per-factory try is not the try of a system-wide draft, while this
        # window's earlier system-wide try is again (stale, so the screen offers to start over).
        definition['execution_scope'] = 'system'
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=definition, expected_revision=saved['revision'])
        self.assertIsNone((await self.try_state(key, OTHER, factory_id='f1'))['try'])
        self.assertEqual((await self.try_state(key, factory_id='f1'))['try']['id'], old['id'])
        back = await self.on_try('try_restart', restarted['run'], OTHER, workflow_id=key, system_id='EMS', factory_id='f1')
        self.assertTrue(back['ok'], back)
        self.assertEqual(back['run']['factory_id'], '')
        self.assertEqual((await self.try_state(key, OTHER, factory_id='f1'))['try']['id'], back['run_id'])

    async def test_try_open_refuses_a_draft_that_cannot_run_and_requires_a_window_key(self):
        unconnected = {**TOOL, 'id': 'loose', 'name': '도구 고르기 전'}
        unconnected.pop('tool_reference'); unconnected.pop('argument_bindings')
        key, _, _ = await self.procedure([CHECK, unconnected])
        refused = await self.try_open(key)
        self.assertEqual(refused['error']['code'], 'execution_not_ready')
        self.assertIn('loose: 도구가 연결되지 않았습니다.', refused['error']['message'].split('\n'))
        empty, _, _ = await self.procedure([], name='작업 없는 절차')
        refused = await self.try_open(empty)
        self.assertEqual(refused['error']['code'], 'execution_not_ready')
        await self.command('save_factory', factory_id='f1', system_id='EMS', name='1공장')
        created = await self.command('create_workflow', actor='a', name='공장 절차', system_id='EMS', execution_scope='factory')
        factory_key = created['workflow_id']
        definition = created['workflow']['draft']; root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['t']
        definition['nodes']['t'] = {'id': 't', 'type': 't', 'name': '점검', 'parent': root, 'children': ['check'], 'deps': []}
        definition['nodes']['check'] = {'type': 'j', 'parent': 't', 'children': [], 'deps': [], **deepcopy(CHECK)}
        await self.command('save_draft', actor='a', workflow_id=factory_key, definition=definition, expected_revision=1)
        self.assertEqual((await self.try_open(factory_key))['error']['code'], 'factory_required')
        self.assertEqual((await self.try_open(factory_key, factory_id='nowhere'))['error']['code'], 'factory_not_found')
        self.assertEqual((await self.opened(factory_key, factory_id='f1'))['factory_id'], 'f1')
        for window in (None, '', 'short', 'x' * 300):
            values = {} if window is None else {'try_window': window}
            result = await self.command('try_open', actor='a', workflow_id=key, system_id='EMS', **values)
            self.assertEqual(result['error']['code'], 'try_window_required', window)
        denied = await self.try_open(key, actor='c')
        self.assertFalse(denied['ok'])
        self.assertFalse((await self.try_state(key, actor='c'))['ok'], 'the draft is manager-only, so is its try')
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM work_runs WHERE workflow_id IN (?,?)", (key, empty)).fetchone()[0], 0)

    async def test_a_try_stays_with_the_procedures_managers(self):
        key, _, _ = await self.procedure([CHECK, TOOL])
        run = await self.opened(key)
        access = next(item for item in (await self.state('admin'))['access'] if item['principal_id'] == 'a')
        demoted = await self.command('save_access', access_id=access['id'], principal_kind='user', principal_id='a', system_id='EMS',
                                     factory_id='*', roles=['participant'], expected_revision=access['revision'])
        self.assertTrue(demoted['ok'], demoted)
        refused = await self.on_try('human_confirm', run, job_id='check', item_id='leak')
        self.assertEqual(refused['error']['code'], 'scope_forbidden', 'the key alone is not enough without the draft right')
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.execute(run)
        self.assertEqual(error.exception.code, 'scope_forbidden')
        options = await self.service.input_options(self.users['a'], {'run_id': run['id'], 'job_id': 'tool', 'field_id': 'page', 'try_window': WINDOW})
        self.assertEqual(options['error']['code'], 'scope_forbidden')
        self.assertEqual((await self.try_state(key))['error']['code'], 'scope_forbidden')
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_decisions WHERE run_id=?', (run['id'],)).fetchone()[0], 0)

    async def test_skill_versions_are_pinned_the_way_publication_pins_them(self):
        assets = {'skills': [{'id': 'guide', 'name': '지침'}], 'skill_bodies': {'guide': '점검 지침'}, 'skill_versions': {'guide': 7}}
        self.service = workflow.WorkflowService(self.database, lambda key: self.users.get(key), lambda key: self.chats.get(key),
                                                lambda user: deepcopy(assets), group_lookup=lambda key: [{'id': item} for item in self.memberships.get(key, [])],
                                                group_list_lookup=lambda: [{'id': 'g', 'name': 'Native group'}])
        self.service.operations.bridge = self.bridge
        key, _, _ = await self.procedure([{**TOOL, 'skills': ['guide']}])
        run = await self.opened(key)
        expected = {'guide': {'revision': 7, 'content_hash': hashlib.sha256('점검 지침'.encode()).hexdigest()}}
        self.assertEqual(run['definition']['resource_versions'], {'skills': expected})
        actor, _, _ = await self.service._work_actor(self.users['a'])
        pinned = await self.service.operations._skills(actor, run['definition']['nodes']['tool'], run['definition'])
        self.assertEqual([item['id'] for item in pinned], ['guide'])

    async def test_each_window_has_its_own_try_that_no_other_window_can_reach(self):
        key, _, _ = await self.procedure([CHECK, TOOL])
        mine = await self.opened(key)
        theirs = await self.opened(key, OTHER)
        self.assertNotEqual(mine['id'], theirs['id'])
        self.assertEqual((await self.try_state(key, OTHER))['try']['id'], theirs['id'])
        ticked = await self.on_try('human_confirm', mine, job_id='check', item_id='leak')
        self.assertTrue(ticked['ok'], ticked)
        self.assertEqual((await self.try_state(key, OTHER))['try']['jobs']['check']['decisions'], [])
        not_found = {'code': 'run_not_found', 'message': '접근할 수 있는 진행 건이 없습니다.'}
        for window in (OTHER, None):
            values = {'run_id': mine['id'], 'expected_revision': ticked['revision']}
            if window:
                values['try_window'] = window
            for action, extra in (('human_confirm', {'job_id': 'check', 'item_id': 'valve'}), ('save_inputs', {'inputs': {'page': '1'}}),
                                  ('claim_task', {'job_id': 'tool'}), ('try_restart', {}), ('close_run', {}), ('link_chat', {'chat_id': 'chat-a'})):
                refused = await self.command(action, actor='a', **values, **extra)
                self.assertEqual(refused['error'], not_found, (window, action))
            with self.assertRaises(workflow.WorkflowError) as error:
                await self.service.operations.command(self.users['a'], {'action': 'execute_job', 'run_id': mine['id'], 'job_id': 'tool',
                    'expected_revision': ticked['revision'], 'request_id': str(uuid4()), **({'try_window': window} if window else {})})
            self.assertEqual(error.exception.code, 'run_not_found')
            options = await self.service.input_options(self.users['a'], {'run_id': mine['id'], 'job_id': 'tool', 'field_id': 'page', **({'try_window': window} if window else {})})
            self.assertEqual(options['error'], not_found)
        # A lost response is replayed for its own window only.
        body = {'action': 'human_confirm', 'request_id': str(uuid4()), 'run_id': mine['id'], 'job_id': 'check', 'item_id': 'valve',
                'expected_revision': ticked['revision'], 'try_window': WINDOW}
        first = await self.service.workspace_command(self.users['a'], body)
        self.assertEqual(await self.service.workspace_command(self.users['a'], body), first)
        replay = await self.service.workspace_command(self.users['a'], {**body, 'try_window': OTHER})
        self.assertEqual(replay['error'], not_found)
        # GET routes, exports and chat have no key: a try does not exist for them.
        self.assertEqual((await self.service.workspace_state(self.users['a'], workflow_id=key, run_id=mine['id']))['error'], not_found)
        self.assertEqual((await self.service.workspace_export(self.users['a'], mine['id']))['error'], not_found)
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.service.operations.state(self.users['a'], system_id='EMS', run_id=mine['id'])
        self.assertEqual(error.exception.code, 'run_not_found')
        with self.assertRaises(workflow.WorkflowError) as error:
            await workflow._workspace_input_context(self.service, self.users['a'], {'context_id': 'chat', 'run_id': mine['id'], 'job_id': 'tool', 'expected_revision': first['revision']})
        self.assertEqual(error.exception.code, 'run_not_found')

    async def test_a_lost_reply_to_opening_or_restarting_a_try_is_replayed(self):
        # Independent review 2026-11-24 (R1): a retried try_restart read the try it had deleted.
        key, _, _ = await self.procedure([CHECK])
        opening = {'action': 'try_open', 'request_id': str(uuid4()), 'workflow_id': key, 'system_id': 'EMS', 'try_window': WINDOW}
        first = await self.service.workspace_command(self.users['a'], deepcopy(opening))
        self.assertTrue(first['ok'], first)
        self.assertEqual(await self.service.workspace_command(self.users['a'], deepcopy(opening)), first)
        restart = {'action': 'try_restart', 'request_id': str(uuid4()), 'run_id': first['run_id'], 'workflow_id': key,
                   'system_id': 'EMS', 'factory_id': '', 'try_window': WINDOW}
        restarted = await self.service.workspace_command(self.users['a'], deepcopy(restart))
        self.assertTrue(restarted['ok'], restarted)
        # The stored reply comes back although the try the request names is gone, and no second try is made.
        self.assertEqual(await self.service.workspace_command(self.users['a'], deepcopy(restart)), restarted)
        with self.service._db() as db:
            self.assertEqual([row[0] for row in db.execute("SELECT id FROM work_runs WHERE mode='try'")], [restarted['run_id']])
        # The same request id with other content is a conflict, not a replay.
        for changed in ({'factory_id': 'f1'}, {'try_window': OTHER}, {'action': 'try_open'}):
            conflict = await self.service.workspace_command(self.users['a'], {**restart, **changed})
            self.assertEqual(conflict['error']['code'], 'request_conflict', changed)
        # A replay is authorized again: the try is for the procedure's managers.
        access = next(item for item in (await self.state('admin'))['access'] if item['principal_id'] == 'a')
        demoted = await self.command('save_access', access_id=access['id'], principal_kind='user', principal_id='a', system_id='EMS',
                                     factory_id='*', roles=['participant'], expected_revision=access['revision'])
        self.assertTrue(demoted['ok'], demoted)
        self.assertEqual((await self.service.workspace_command(self.users['a'], deepcopy(restart)))['error']['code'], 'scope_forbidden')

    async def test_a_try_is_never_real_work_and_never_blocks_or_is_blocked_by_it(self):
        key, _, revision = await self.procedure([CHECK, TOOL], publish=True)
        tried = await self.worked_try(key)
        real = await self.start(key, revision)
        listed = await self.state('a', workflow_id=key)
        self.assertEqual([item['id'] for item in listed['runs']], [real['id']])
        self.assertEqual([item['id'] for item in listed['workflow_active_runs']], [real['id']])
        blocked = await self.command('start_run', actor='a', workflow_id=key, expected_revision=revision, version=1)
        self.assertEqual(blocked['error']['code'], 'system_run_active', 'the one-open-run rule still holds for real work')
        other = await self.opened(key, OTHER)
        self.assertNotIn(other['id'], [item['id'] for item in (await self.state('a'))['runs']])
        actor, _, groups = await self.service._work_actor(self.users['a'])
        everything = await self.service._work_evidence_access(actor, groups)
        with self.service._db() as db:
            try_attempts = {row[0] for row in db.execute('SELECT id FROM work_attempts WHERE run_id=?', (tried['id'],))}
        self.assertTrue(try_attempts)
        self.assertFalse(everything & try_attempts)
        self.assertEqual(await self.service._work_evidence_access(actor, groups, tried['id']), try_attempts)
        # The account-wide screen state never points at a try.
        saved = await self.command('save_ui', actor='a', expected_revision=0, state={'selection': {'run_id': tried['id'], 'workflow_id': key}})
        self.assertEqual(saved['ui_state']['selection'], {'run_id': '', 'workflow_id': key})
        self.assertEqual((await self.state('a'))['ui_state']['state']['selection'], {'run_id': '', 'workflow_id': key})
        kept = await self.command('save_ui', actor='a', expected_revision=saved['revision'], state={'selection': {'run_id': real['id']}})
        self.assertEqual(kept['ui_state']['selection'], {'run_id': real['id']})

    async def test_saving_work_settings_rechecks_real_open_runs_only(self):
        job = {**CONFIRM, 'inputs': [{'id': 'limit', 'type': 'number', 'scope': 'workflow'}]}
        key, _, revision = await self.procedure([job], publish=True)
        real = await self.start(key, revision)
        done = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='confirm', expected_revision=real['revision'])
        self.assertEqual(done['run']['jobs']['confirm']['status'], 'completed')
        tried = await self.on_try('human_confirm', await self.opened(key), job_id='confirm')
        self.assertEqual(tried['run']['jobs']['confirm']['status'], 'completed')
        saved = await self.command('save_settings', actor='a', workflow_id=key, values={'limit': 3}, expected_revision=0)
        self.assertTrue(saved['ok'], saved)
        self.assertEqual((await self.state('a', run_id=real['id']))['run']['jobs']['confirm']['status'], 'review_required')
        after = (await self.try_state(key))['try']
        self.assertEqual((after['revision'], after['jobs']['confirm']['status']), (tried['run']['revision'], 'completed'))
        self.assertTrue(after['jobs']['confirm']['result_stale'], 'a try reads settings live, so its result goes stale')

    async def test_rules_for_open_work_skip_a_try_even_if_its_row_reads_open(self):
        # A try is stored as cancelled; these filters are the second line of defense.
        job = {**CONFIRM, 'inputs': [{'id': 'limit', 'type': 'number', 'scope': 'workflow'}]}
        key, _, revision = await self.procedure([job], publish=True)
        tried = await self.on_try('human_confirm', await self.opened(key), job_id='confirm')
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_runs SET status='open' WHERE id=?", (tried['run_id'],))
        real = await self.start(key, revision)
        self.assertEqual([item['id'] for item in (await self.state('a', workflow_id=key))['workflow_active_runs']], [real['id']])
        saved = await self.command('save_settings', actor='a', workflow_id=key, values={'limit': 3}, expected_revision=0)
        self.assertTrue(saved['ok'], saved)
        after = self.row(tried['run_id'])
        self.assertEqual(after['revision'], tried['revision'])
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT status FROM work_jobs WHERE run_id=?', (tried['run_id'],)).fetchone()[0], 'completed')

    async def test_try_restart_deletes_the_old_try_whole_and_marks_changed_jobs(self):
        key, definition, revision = await self.procedure([CHECK, TOOL, CONFIRM], publish=True)
        real = await self.start(key, revision)
        ticked = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='check', item_id='leak', expected_revision=real['revision'])
        self.assertTrue(ticked['ok'], ticked)
        old = await self.worked_try(key)
        self.fill(old['id'])
        before = self.owned(old['id'])
        self.assertTrue(all(before.values()), before)
        real_rows = self.owned(real['id'])
        changed = deepcopy(definition)
        changed['nodes']['check']['confirmation_items'].append({'id': 'gauge', 'name': '압력계 정상'})
        changed['nodes']['t']['children'] = ['check', 'tool', 'added']
        changed['nodes'].pop('confirm')
        changed['nodes']['added'] = {**deepcopy(CONFIRM), 'id': 'added', 'name': '새 작업', 'type': 'j', 'parent': 't', 'children': [], 'deps': []}
        saved = await self.command('save_draft', actor='a', workflow_id=key, definition=changed, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        restarted = await self.on_try('try_restart', old)
        self.assertTrue(restarted['ok'], restarted)
        fresh = restarted['run']
        self.assertNotEqual(fresh['id'], old['id'])
        self.assertEqual(self.owned(old['id']), dict.fromkeys(OWNED, 0))
        self.assertEqual(self.owned(real['id']), real_rows, 'real work is untouched')
        self.assertEqual(fresh['try'], {'draft_hash': saved['draft_hash'], 'saved_at': (await self.try_state(key))['workflow']['draft_saved_at'],
                                        'changed': ['added', 'check'], 'started': False})
        self.assertEqual(sorted(fresh['jobs']), ['added', 'check', 'tool'])
        self.assertEqual((fresh['attempts'], fresh['inputs']), ([], {}))
        self.assertEqual((await self.try_state(key))['try']['id'], fresh['id'])
        # '처음부터' with the same saved draft clears the try and marks nothing.
        again = await self.on_try('try_restart', fresh)
        self.assertEqual(again['run']['try']['changed'], [])
        self.assertEqual(self.owned(fresh['id'])['work_runs'], 0)
        # A draft that cannot run keeps the try it would replace.
        broken = deepcopy(changed)
        broken['nodes']['tool'].pop('tool_reference'); broken['nodes']['tool'].pop('argument_bindings')
        await self.command('save_draft', actor='a', workflow_id=key, definition=broken, expected_revision=saved['revision'])
        refused = await self.on_try('try_restart', again['run'])
        self.assertEqual(refused['error']['code'], 'execution_not_ready')
        self.assertEqual(self.row(again['run']['id'])['mode'], 'try')
        # A real run is never deleted as a try.
        with self.service._db(write=True) as db:
            with self.assertRaises(workflow.WorkflowError) as error:
                workspace.WorkspaceMixin._work_delete_try(db, real['id'])
        self.assertEqual(error.exception.code, 'try_required')
        self.assertEqual((await self.command('try_restart', actor='a', run_id=real['id'], try_window=WINDOW))['error']['code'], 'run_not_found')

    async def test_a_read_retry_timeout_receipt_goes_with_its_try(self):
        # Independent review 2026-11-24 (R4): the timeout outcome lost the run id that deletion looks for.
        job = {**TOOL, 'tool_reference': {'tool_id': 'native', 'function': 'get_page', 'content_hash': 'sha'},
               'argument_bindings': {'page_id': {'input': 'page'}}, 'read_retry': {'count': 1, 'deadline_seconds': 1}}
        key, _, _ = await self.procedure([job])
        run = await self.opened(key)
        saved = await self.on_try('save_inputs', run, inputs={'page': '42'})
        self.assertTrue(saved['ok'], saved)
        self.bridge.hold = asyncio.Event()
        request_id = str(uuid4())
        timed_out = await self.execute(saved['run'], request_id=request_id)
        self.bridge.hold.set()
        self.assertEqual((timed_out['attempt']['status'], timed_out['attempt']['run_id']), ('unknown', run['id']))
        receipt = "SELECT outcome FROM work_operation_receipts WHERE actor='a' AND request_id=?"
        with self.service._db() as db:
            self.assertEqual(json.loads(db.execute(receipt, (request_id,)).fetchone()[0])['attempt']['run_id'], run['id'])
        # An outcome naming only its attempt goes too, however many attempts the try has;
        # receipts of other work stay. (The synthetic attempts are rows only, never shown.)
        current = (await self.try_state(key))['try']
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_operation_receipts SET outcome=json_remove(outcome,'$.attempt.run_id') WHERE actor='a' AND request_id=?", (request_id,))
            for number in range(2, 2 * workspace.TRY_RECEIPT_CHUNK + 7):
                attempt_id = f'synthetic-attempt-{number}'
                db.execute("INSERT INTO work_attempts VALUES(?,?,'tool',?,'synthetic','{}','{}','failed','{}','2026-11-24T00:00:00.000+00:00','2026-11-24T00:00:00.000+00:00')",
                           (attempt_id, run['id'], number))
                db.execute("INSERT INTO work_operation_receipts VALUES('a',?,'h',?)", ('synthetic-' + str(number), json.dumps({'attempt': {'id': attempt_id}})))
            db.execute("INSERT INTO work_operation_receipts VALUES('a','real-work','h',?)", (json.dumps({'attempt': {'id': 'real-attempt', 'run_id': 'real-run'}}),))
        restarted = await self.on_try('try_restart', current)
        self.assertTrue(restarted['ok'], restarted)
        self.assertEqual(self.owned(run['id']), dict.fromkeys(OWNED, 0))
        with self.service._db() as db:
            self.assertEqual([row[0] for row in db.execute("SELECT request_id FROM work_operation_receipts WHERE actor='a'")], ['real-work'])

    async def test_restart_and_sweep_wait_while_a_job_runs(self):
        key, _, _ = await self.procedure([TOOL])
        run = await self.opened(key)
        saved = await self.on_try('save_inputs', run, inputs={'page': '42'})
        self.bridge.hold = asyncio.Event()
        running = asyncio.create_task(self.execute(saved['run']))
        for _ in range(500):
            if self.bridge.calls:
                break
            await asyncio.sleep(0.01)
        self.assertTrue(self.bridge.calls, 'the tool call is in flight')
        refused = await self.on_try('try_restart', saved['run'])
        self.assertEqual(refused['error'], {'code': 'try_running', 'message': '실행 중인 작업이 끝난 뒤 다시 해 주세요.'})
        # Old enough to be swept, but its job still runs. (Moving the clock instead
        # would also expire the running call's lease.)
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_runs SET snapshot=json_set(snapshot,'$.try.touched_at','2000-01-01T00:00:00.000+00:00') WHERE id=?", (run['id'],))
        self.assertEqual(self.service.operations._sweep_tries(), [])
        self.bridge.hold.set()
        self.assertEqual((await running)['attempt']['status'], 'succeeded')
        current = (await self.try_state(key))['try']
        self.assertTrue((await self.on_try('try_restart', current))['ok'])

    async def test_untouched_tries_are_swept_after_a_day_and_running_ones_are_kept(self):
        key, _, _ = await self.procedure([CHECK, TOOL])
        stale = await self.worked_try(key)
        fresh = await self.opened(key, OTHER)
        busy = await self.opened(key, 'window-c-' + 'c' * 32)
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_jobs SET status='running' WHERE run_id=? AND job_id='tool'", (busy['id'],))
        self.now += 23 * 3600
        touched = await self.on_try('human_confirm', fresh, OTHER, job_id='check', item_id='leak')
        self.assertTrue(touched['ok'], touched)
        self.now += 2 * 3600
        swept = self.service.operations._sweep_tries()
        self.assertEqual(swept, [stale['id']])
        self.assertEqual(self.owned(stale['id']), dict.fromkeys(OWNED, 0))
        self.assertEqual(self.row(fresh['id'])['mode'], 'try')
        self.assertEqual(self.row(busy['id'])['mode'], 'try')
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_jobs SET status='pending' WHERE run_id=? AND job_id='tool'", (busy['id'],))
        self.now += 5 * 60
        self.assertEqual(self.service.operations._sweep_tries(), [], 'the sweep runs at most every ten minutes')
        self.now += 5 * 60
        self.assertEqual(self.service.operations._sweep_tries(), [busy['id']])
        # try_open sweeps too, then opens a new try for a window whose try expired.
        self.now += 25 * 3600
        reopened = await self.opened(key, OTHER)
        self.assertNotEqual(reopened['id'], fresh['id'])
        self.assertEqual(self.row(fresh['id']), {})
        # The background loop runs the sweep on its own.
        self.now += 25 * 3600
        await self.service.operations.process_once()
        self.assertEqual(self.row(reopened['id']), {})

    async def test_sweeps_are_bounded_and_a_failing_sweep_never_stops_opening_a_try(self):
        # Independent review 2026-11-24: the sweep runs inside other commands' transactions.
        key, _, _ = await self.procedure([CHECK])
        idle = await self.opened(key, OTHER)
        with self.service._db(write=True) as db:  # 26 idle tries in all
            for number in range(25):
                db.execute('INSERT INTO work_runs SELECT ?,workflow_id,version,system_id,factory_id,owner,sharing,mode,status,revision,inputs,snapshot,created_at,updated_at,closed_at FROM work_runs WHERE id=?',
                           (f'idle-copy-{number:02d}', idle['id']))

        def tries():
            with self.service._db() as db:
                return {row[0] for row in db.execute("SELECT id FROM work_runs WHERE mode='try'")}
        idle_ids = tries()
        self.now += 25 * 3600
        # A deletion failing halfway undoes the whole sweep and is logged; the try still opens.
        real_delete, calls = workspace.WorkspaceMixin._work_delete_try, []

        def failing(db, run_id):
            calls.append(run_id)
            real_delete(db, run_id)
            if len(calls) == 2:
                raise sqlite3.OperationalError('synthetic failure')
        with patch.object(self.service, '_work_delete_try', side_effect=failing), self.assertLogs(workspace.__name__, 'WARNING') as logged:
            first = await self.try_open(key, 'window-d-' + 'd' * 32)
        self.assertTrue(first['ok'], first)
        self.assertEqual(set(first), {'ok', 'run_id', 'workflow_id', 'revision', 'run'}, 'nothing about the sweep reaches the screen')
        self.assertEqual((len(calls), logged.output), (2, [f'WARNING:{workspace.__name__}:try_sweep_failed: OperationalError']))
        self.assertEqual(tries(), idle_ids | {first['run_id']})
        # try_open deletes at most five, the background sweep at most twenty, every ten minutes.
        second = await self.opened(key, 'window-e-' + 'e' * 32)
        self.assertEqual(len(idle_ids - tries()), 5)
        self.assertEqual(len(self.service.operations._sweep_tries()), 20)
        self.assertEqual(len(idle_ids & tries()), 1)
        self.now += 600
        self.assertEqual(len(self.service.operations._sweep_tries()), 1)
        self.assertEqual(tries(), {first['run_id'], second['id']})

    async def test_verdicts_change_in_place_in_a_try_but_stay_append_only_in_real_work(self):
        key, _, revision = await self.procedure([CHECK, TOOL], publish=True)
        run = await self.opened(key)
        saved = await self.on_try('save_inputs', run, inputs={'page': '42'})
        executed = await self.execute(saved['run'])
        current = (await self.try_state(key))['try']
        verdicts = []
        for verdict in ('failed', 'unknown', 'completed', 'action_required'):
            decided = await self.on_try('decide', current, job_id='tool', item_id='job', verdict=verdict, result_revision=executed['attempt']['number'])
            self.assertTrue(decided['ok'], (verdict, decided))
            current = decided['run']
            verdicts.append((current['jobs']['tool']['status'], [item['verdict'] for item in current['jobs']['tool']['decisions']]))
        self.assertEqual(verdicts, [('failed', ['failed']), ('unknown', ['unknown']), ('completed', ['completed']), ('waiting_input', ['action_required'])])
        again = await self.on_try('human_confirm', current, job_id='check', item_id='leak')
        twice = await self.on_try('human_confirm', again['run'], job_id='check', item_id='leak')
        self.assertTrue(twice['ok'], twice)
        self.assertEqual([item['item_id'] for item in twice['run']['jobs']['check']['decisions']], ['leak'])
        real = await self.start(key, revision)
        saved = await self.command('save_inputs', actor='a', run_id=real['id'], inputs={'page': '42'}, expected_revision=real['revision'])
        body = {'action': 'execute_job', 'run_id': real['id'], 'job_id': 'tool', 'expected_revision': saved['revision'], 'request_id': str(uuid4())}
        attempt = (await self.service.operations.command(self.users['a'], body))['attempt']
        latest = (await self.state('a', run_id=real['id']))['run']
        first = await self.command('decide', actor='a', run_id=real['id'], job_id='tool', item_id='job', verdict='failed', result_revision=attempt['number'], expected_revision=latest['revision'])
        self.assertTrue(first['ok'], first)
        second = await self.command('decide', actor='a', run_id=real['id'], job_id='tool', item_id='job', verdict='completed', result_revision=attempt['number'], expected_revision=first['revision'])
        self.assertEqual(second['error']['code'], 'decision_conflict')
        ticked = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='check', item_id='leak', expected_revision=first['revision'])
        repeated = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='check', item_id='leak', expected_revision=ticked['revision'])
        self.assertEqual(repeated['error']['code'], 'decision_conflict')

    async def test_real_attempts_decisions_and_review_revisions_stay_undeletable(self):
        key, _, revision = await self.procedure([CHECK, TOOL], publish=True)
        real = await self.start(key, revision)
        ticked = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='check', item_id='leak', expected_revision=real['revision'])
        self.assertTrue(ticked['ok'], ticked)
        with self.service._db(write=True) as db:
            attempt = db.execute('SELECT id FROM work_attempts WHERE run_id=?', (real['id'],)).fetchone()[0]
            db.execute("INSERT INTO work_review_revisions VALUES(?,1,'kept','a','2026-11-24T00:00:00.000+00:00',NULL)", (attempt,))
        for statement in ('DELETE FROM work_attempts WHERE run_id=?', 'DELETE FROM work_decisions WHERE run_id=?',
                          'DELETE FROM work_review_revisions WHERE attempt_id IN (SELECT id FROM work_attempts WHERE run_id=?)'):
            with self.assertRaises(sqlite3.DatabaseError, msg=statement) as error:
                with self.service._db(write=True) as db:
                    db.execute(statement, (real['id'],))
            self.assertIn('immutable', str(error.exception))
        for statement in ("UPDATE work_decisions SET verdict='failed'", "UPDATE work_attempts SET status='failed'", "DELETE FROM work_versions"):
            with self.assertRaises(sqlite3.DatabaseError, msg=statement):
                with self.service._db(write=True) as db:
                    db.execute(statement)
        with self.service._db() as db:
            triggers = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertFalse({'work_attempt_delete_immutable', 'work_decisions_delete_immutable', 'work_review_revisions_delete_immutable'} & triggers)
        self.assertTrue({'work_attempt_delete_keep_work', 'work_decisions_delete_keep_work', 'work_review_revisions_delete_keep_work',
                         'work_attempt_finished_immutable', 'work_versions_delete_immutable', 'work_decisions_update_immutable'} <= triggers)
        # A previous program re-creates its strict trigger on start; the next start drops it again.
        with self.service._db(write=True) as db:
            db.execute("CREATE TRIGGER work_attempt_delete_immutable BEFORE DELETE ON work_attempts BEGIN SELECT RAISE(ABORT,'immutable attempt history'); END")
        self.service = self.new_service()
        self.service.operations.bridge = self.bridge
        self.service.operations.clock = lambda: self.now
        with self.service._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='work_attempt_delete_immutable'").fetchone())
            self.assertEqual(db.execute('SELECT version FROM work_schema').fetchone()[0], 2)
        tried = await self.worked_try(key)
        restarted = await self.on_try('try_restart', tried)
        self.assertTrue(restarted['ok'], restarted)
        self.assertEqual(self.owned(tried['id']), dict.fromkeys(OWNED, 0))

    async def test_try_refuses_what_belongs_to_real_work(self):
        key, _, _ = await self.procedure([CHECK, TOOL])
        run = await self.opened(key)
        refused = {'code': 'try_not_supported', 'message': '시험에서는 할 수 없어요.'}
        for action, extra in (('close_run', {}), ('cancel_run', {'reason': '시험 정리'}), ('link_chat', {'chat_id': 'chat-a'})):
            self.assertEqual((await self.on_try(action, run, **extra))['error'], refused, action)
        for action in ('execute_scope', 'shared_tool_accept_version'):
            with self.assertRaises(workflow.WorkflowError) as error:
                await self.service.operations.command(self.users['a'], {'action': action, 'run_id': run['id'], 'expected_revision': run['revision'],
                    'request_id': str(uuid4()), 'try_window': WINDOW, 'shared_tool_id': 'managed-get_page', 'version': 1})
            self.assertEqual((error.exception.code, error.exception.message), (refused['code'], refused['message']), action)
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_scope_runs').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_chat_links').fetchone()[0], 0)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            with self.assertRaises(workflow.WorkflowError) as error:
                self.service.operations.enqueue_scope(db, actor, groups, run['id'])
        self.assertEqual(error.exception.code, 'try_not_supported')
        self.assertEqual(self.row(run['id'])['status'], 'cancelled')

    async def test_job_trigger_offsets_apply_to_real_work_only(self):
        later = {**CONFIRM, 'trigger': {'offset_seconds': 3600}}
        key, _, revision = await self.procedure([later], publish=True)
        real = await self.start(key, revision)
        waiting = await self.command('human_confirm', actor='a', run_id=real['id'], job_id='confirm', expected_revision=real['revision'])
        self.assertEqual(waiting['error']['code'], 'scheduled_time_required')
        run = await self.opened(key)
        confirmed = await self.on_try('human_confirm', run, job_id='confirm')
        self.assertTrue(confirmed['ok'], confirmed)
        self.assertEqual(confirmed['run']['jobs']['confirm']['status'], 'completed')

    async def test_writes_postpone_the_cleanup_and_marks_started(self):
        key, _, _ = await self.procedure([CHECK, TOOL])
        run = await self.opened(key)
        touched = lambda: json.loads(self.row(run['id'])['snapshot'])['try']['touched_at']
        opened_at = touched()
        self.now += 60
        reopened = await self.opened(key)
        self.assertGreater(touched(), opened_at)
        self.assertFalse(reopened['try']['started'])
        before = touched()
        self.now += 60
        saved = await self.on_try('save_inputs', reopened, inputs={'page': '7'})
        self.assertTrue(saved['run']['try']['started'], 'a saved input starts the try')
        self.assertGreater(touched(), before)
        before = touched()
        self.now += 60
        await self.execute(saved['run'])
        self.assertGreater(touched(), before)

    # ---- Tool jobs and EES change requests in a try (local HTTP service) ----

    async def register_api(self, server, methods=('GET',)):
        """One registered service reachable at the local server, with one API per method."""
        runtime = self.service.operations
        admin = self.users['admin']
        record = await runtime.command(admin, {'action': 'api_service_save', 'request_id': str(uuid4()), 'expected_revision': 0, 'service': {'name': '사내 Confluence'}})
        service_id = record['service']['id']
        base_url = f'http://127.0.0.1:{server.server_port}'
        self.enterContext(patch.dict(os.environ, {'EES_WORK_API_SERVICES': json.dumps({service_id: {'base_url': base_url}})}))
        apis = []
        for method in methods:
            api = {'service_id': service_id, 'name': '페이지 조회' if method == 'GET' else '페이지 바꾸기', 'purpose': '시험', 'method': method,
                   'url': base_url + '/pages', 'inputs': [{'name': 'id', 'in': 'query' if method == 'GET' else 'body', 'type': 'string', 'required': True, 'label': '페이지 ID'}],
                   'result_path': 'results', 'fields': [{'path': 'title', 'label': '제목', 'type': 'string'}], 'example': {'results': [{'title': 'example'}]}}
            saved = await runtime.command(admin, {'action': 'api_save', 'request_id': str(uuid4()), 'expected_revision': 0, 'api': api})
            self.assertTrue(saved['ok'], saved)
            apis.append(saved['api'])
        return record['service'], *apis

    @staticmethod
    def api_job(api, job_id='page', **change):
        job = {'id': job_id, 'name': '기준 문서 확인', 'mode': 'tool', 'result_block': 'human_confirm', 'human_confirmation': True,
               'inputs': [{'id': 'page-id', 'name': '페이지 ID', 'type': 'text', 'scope': 'run', 'required': True}],
               'api_binding': {'operation_id': api['id'], 'version': api['version'], 'inputs': {'id': {'input': 'page-id'}}, 'outputs': ['title']}}
        return {**job, **change}

    async def test_tool_jobs_run_as_in_real_work_and_failures_reach_the_row(self):
        with page_service() as server:
            service, api = await self.register_api(server)
            key, _, _ = await self.procedure([self.api_job(api)])
            run = await self.opened(key)
            saved = await self.on_try('save_inputs', run, inputs={'page-id': '42'})
            executed = await self.execute(saved['run'], 'page')
            self.assertEqual(executed['attempt']['status'], 'succeeded', executed)
            self.assertEqual(server.requests, [('GET', '/pages', '42')])
            state = await self.try_state(key)
            self.assertEqual(state['try']['jobs']['page']['status'], 'waiting_confirmation')
            self.assertEqual(state['try']['attempts'][0]['result']['items'][0]['row'], {'title': 'Page 42'})
            # T11: an upstream 404 is a recorded failed attempt the row can explain.
            saved = await self.on_try('save_inputs', state['try'], inputs={'page-id': 'missing'})
            failed = await self.execute(saved['run'], 'page')
            self.assertEqual((failed['ok'], failed['attempt']['status']), (False, 'failed'))
            state = await self.try_state(key)
            latest = next(item for item in state['try']['attempts'] if item['id'] == state['try']['jobs']['page']['current_attempt'])
            self.assertEqual((latest['result']['error'], latest['result']['http_status']), ({'code': 'api_http_error'}, 404))
            # The row names the service: the job's API → its service → the service name.
            catalog = state['operations']['api_catalog']
            used = next(item for item in catalog['apis'] if item['id'] == state['try']['definition']['nodes']['page']['api_binding']['operation_id'])
            self.assertEqual(next(item['name'] for item in catalog['services'] if item['id'] == used['service_id']), service['name'])
            # T10: without this account's credential the call stops before any attempt, with its code.
            requests = len(server.requests)
            with patch.dict(os.environ, {'EES_WORK_API_SERVICES': json.dumps({service['id']: {'base_url': f'http://127.0.0.1:{server.server_port}', 'user_credential_headers': {}}})}):
                with self.assertRaises(workflow.WorkflowError) as error:
                    await self.execute(state['try'], 'page')
            self.assertEqual(error.exception.code, 'api_auth_required')
            self.assertEqual(len(server.requests), requests)
            self.assertEqual(len((await self.try_state(key))['try']['attempts']), 2)

    async def test_change_requests_are_never_prepared_or_sent_from_a_try(self):
        with page_service() as server:
            _, read, write = await self.register_api(server, ('GET', 'POST'))
            change = self.api_job(write, 'change', name='페이지 바꾸기', result_block='change_request', approval_count=0,
                                  effect_criterion={'check': '페이지 상태 확인'})
            change.pop('human_confirmation')
            change['api_binding']['outputs'] = []
            key, _, _ = await self.procedure([self.api_job(read), change])
            run = await self.opened(key)
            self.assertFalse(run['jobs']['change']['can_request'])
            saved = await self.on_try('save_inputs', run, inputs={'page-id': '42'})
            with self.service._db() as db:
                receipts = db.execute('SELECT COUNT(*) FROM work_operation_receipts').fetchone()[0]
            prepare = {'action': 'request_prepare', 'run_id': run['id'], 'job_id': 'change', 'expected_revision': saved['revision'], 'request_id': str(uuid4())}
            for body, code in (({**prepare, 'try_window': WINDOW}, 'try_request_blocked'), ({**prepare, 'try_window': OTHER}, 'run_not_found'), (prepare, 'run_not_found')):
                with self.assertRaises(workflow.WorkflowError) as error:
                    await self.service.operations.command(self.users['a'], body)
                self.assertEqual(error.exception.code, code)
            self.assertEqual(error.exception.message, '접근할 수 있는 진행 건이 없습니다.')
            with self.service._db(write=True) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM work_external_requests').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM work_operation_receipts').fetchone()[0], receipts)
                # Defense in depth: even a forged ready request of a try is never approved, confirmed or sent.
                forged = {'id': 'forged-request', 'run_id': run['id'], 'job_id': 'change', 'actor': 'a', 'revision': 1, 'state': 'ready',
                          'tool_contract_id': write['id'], 'reference': {'kind': 'api', 'tool_id': write['id'], 'version': write['version']},
                          'approvals': [], 'approval_count': 0, 'inputs': {'id': '42'}}
                db.execute('INSERT INTO work_external_requests VALUES(?,?,?,?,?,?,?)', ('forged-request', run['id'], 'change', 'a', 1, 'ready', json.dumps(forged)))
            for action in ('request_approve', 'request_intent', 'request_dispatch'):
                with self.assertRaises(workflow.WorkflowError) as error:
                    await self.service.operations.command(self.users['a'], {'action': action, 'external_request_id': 'forged-request', 'expected_revision': 1,
                                                                             'request_id': str(uuid4()), 'intent_token': 'x' * 40})
                self.assertEqual((error.exception.code, error.exception.message), ('try_request_blocked', '시험에서는 변경 요청을 보내지 않아요.'), action)
            self.assertEqual([item for item in server.requests if item[0] == 'POST'], [])
            with self.service._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM work_attempts WHERE run_id=? AND job_id='change'", (run['id'],)).fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM work_request_intents').fetchone()[0], 0)
            # execute_job already refuses change requests, in a try as in real work.
            with self.assertRaises(workflow.WorkflowError) as error:
                await self.execute(saved['run'], 'change')
            self.assertEqual(error.exception.code, 'human_command_required')


class TryRouteTests(unittest.IsolatedAsyncioTestCase):
    """The window key travels in POST bodies; GET routes never reach a try."""

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.users = {'admin': {'id': 'admin', 'role': 'admin'}}
        self.service = workflow.WorkflowService(Path(self.temp.name) / 'work.db', self.users.get, lambda _: None)
        self.service.operations.bridge = Bridge()
        patcher = patch.object(workflow, '_production_service', return_value=self.service)
        patcher.start(); self.addCleanup(patcher.stop)
        app = FastAPI()

        async def verified(authorization: str = Header(default='')):
            user = self.users.get(authorization.removeprefix('Bearer '))
            if not user:
                raise HTTPException(status_code=401)
            return user

        workflow.install(app, verified)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://native.test', headers={'Authorization': 'Bearer admin'})
        self.addAsyncCleanup(self.client.aclose)

    async def post(self, path, **body):
        return await self.client.post('/api/ees-work/' + path, json=body)

    async def test_try_route_commands_and_status_codes(self):
        created = (await self.post('workspace/command', action='create_workflow', name='경로 시험', system_id='EMS', expected_revision=0, request_id=str(uuid4()))).json()
        key, definition = created['workflow_id'], created['workflow']['draft']
        root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['t']
        definition['nodes']['t'] = {'id': 't', 'type': 't', 'name': '점검', 'parent': root, 'children': ['check'], 'deps': []}
        definition['nodes']['check'] = {'type': 'j', 'parent': 't', 'children': [], 'deps': [], **deepcopy(CHECK)}
        saved = await self.post('workspace/command', action='save_draft', workflow_id=key, definition=definition, expected_revision=1, request_id=str(uuid4()))
        self.assertEqual(saved.status_code, 200, saved.text)
        missing = await self.post('workspace/try', workflow_id=key, system_id='EMS', try_window=WINDOW)
        self.assertEqual((missing.status_code, missing.json()['try']), (200, None))
        self.assertEqual(missing.headers['cache-control'], 'no-store')
        opened = await self.post('workspace/command', action='try_open', workflow_id=key, system_id='EMS', try_window=WINDOW, request_id=str(uuid4()))
        self.assertEqual(opened.status_code, 200, opened.text)
        run_id = opened.json()['run_id']
        state = await self.post('workspace/try', workflow_id=key, system_id='EMS', try_window=WINDOW)
        self.assertEqual((state.status_code, state.json()['try']['id'], state.json()['try']['status']), (200, run_id, 'open'))
        for path in ('workspace?run_id=' + run_id, 'operations?run_id=' + run_id, 'export?run_id=' + run_id):
            response = await self.client.get('/api/ees-work/' + path)
            self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'run_not_found'), path)
        wrong = await self.post('workspace/command', action='human_confirm', run_id=run_id, job_id='check', item_id='leak', expected_revision=1, try_window=OTHER, request_id=str(uuid4()))
        self.assertEqual(wrong.status_code, 404)
        closed = await self.post('workspace/command', action='close_run', run_id=run_id, expected_revision=1, try_window=WINDOW, request_id=str(uuid4()))
        self.assertEqual((closed.status_code, closed.json()['error']['code']), (400, 'try_not_supported'))
        # A failure before any attempt keeps its code in the response; a wrong key is a missing run.
        for window, status, code in ((WINDOW, 400, 'human_command_required'), (OTHER, 404, 'run_not_found')):
            executed = await self.post('operations', action='execute_job', run_id=run_id, job_id='check', expected_revision=1, try_window=window, request_id=str(uuid4()))
            self.assertEqual((executed.status_code, executed.json()['error']['code']), (status, code))
        unkeyed = await self.post('workspace/try', workflow_id=key, system_id='EMS')
        self.assertEqual((unkeyed.status_code, unkeyed.json()['error']['code']), (400, 'try_window_required'))


if __name__ == '__main__':
    unittest.main()
