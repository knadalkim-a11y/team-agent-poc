"""Integrated work contract tests using temporary SQLite and Native ID fixtures."""
import asyncio
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ModuleType('ees_workspace_test_subject')
PACKAGE.__path__ = [str(ROOT / 'agent-pack/skills/ees-work-demo/scripts')]
sys.modules[PACKAGE.__name__] = PACKAGE
workflow = importlib.import_module(PACKAGE.__name__ + '.ees_workflow')
workspace = importlib.import_module(PACKAGE.__name__ + '.ees_workflow_workspace')


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'work.sqlite3'
        self.users = {key: {'id': key, 'role': 'admin' if key == 'admin' else 'user'} for key in ('admin', 'a', 'b', 'c')}
        self.memberships = {'a': ['g'], 'b': ['g']}
        self.chats = {'chat-a': {'user_id': 'a'}, 'chat-b': {'user_id': 'b'}}
        self.service = self.new_service()
        for actor in ('a', 'b'):
            result = await self.command('save_access', principal_kind='user', principal_id=actor, system_id='EMS', factory_id='*', roles=['manager', 'participant'])
            self.assertTrue(result['ok'], result)

    def new_service(self):
        return workflow.WorkflowService(self.database, lambda key: self.users.get(key), lambda key: self.chats.get(key),
            group_lookup=lambda key: [{'id': item} for item in self.memberships.get(key, [])],
            group_list_lookup=lambda: [{'id': 'g', 'name': 'Native group'}])

    async def command(self, action, actor='admin', expected_revision=0, **values):
        return await self.service.workspace_command(self.users[actor], dict(action=action, request_id=str(uuid4()), expected_revision=expected_revision, **values))

    async def create(self, mode='human', fields=None, block='human_confirm', dependent=False):
        result = await self.command('create_workflow', name='검증 절차', system_id='EMS')
        self.assertTrue(result['ok'], result)
        definition = result['workflow']['draft']; root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['t']
        definition['nodes']['t'] = {'id': 't', 'type': 't', 'name': '단계', 'parent': root, 'children': ['j'], 'deps': []}
        definition['nodes']['j'] = {'id': 'j', 'type': 'j', 'name': '작업', 'parent': 't', 'children': [], 'deps': [], 'mode': mode, 'inputs': fields or [], 'result_block': block}
        if mode == 'tool': definition['nodes']['j']['tool_reference'] = {'tool_id': 'native', 'function': 'read', 'content_hash': 'sha'}
        if dependent:
            for key, deps in (('next', ['j']), ('independent', [])):
                definition['nodes']['t']['children'].append(key)
                definition['nodes'][key] = {'id': key, 'type': 'j', 'name': key, 'parent': 't', 'children': [], 'deps': deps, 'mode': 'human'}
        saved = await self.command('save_draft', workflow_id=result['workflow_id'], definition=definition, expected_revision=1)
        self.assertTrue(saved['ok'], saved)
        validated = await self.command('validate_workflow', workflow_id=result['workflow_id'], expected_revision=2)
        self.assertTrue(validated['ok'], validated)
        self.assertFalse(validated['validation']['errors'], validated)
        published = await self.command('publish_workflow', workflow_id=result['workflow_id'], expected_revision=2)
        self.assertTrue(published['ok'], published)
        return result['workflow_id'], definition, published['revision']

    async def start(self, workflow_id, revision=3, actor='a', **values):
        result = await self.command('start_run', actor=actor, workflow_id=workflow_id, expected_revision=revision, **values)
        self.assertTrue(result['ok'], result)
        return result['run']

    async def state(self, actor='a', **query):
        result = await self.service.workspace_state(self.users[actor], **query)
        self.assertTrue(result['ok'], result)
        return result

    async def test_empty_initializer_restart_and_no_implicit_native_access(self):
        self.assertEqual((await self.state())['workflows'], [])
        with self.service._db() as db:
            catalog = json.loads(db.execute('SELECT published FROM catalog').fetchone()[0])
            self.assertEqual(catalog['nodes'], {}); self.assertEqual(catalog['skills'], {})
        self.service = self.new_service()
        self.assertEqual((await self.state())['runs'], [])
        self.assertEqual((await self.state('c'))['systems'], [])
        denied = await self.command('create_workflow', actor='c', system_id='EMS', name='무권한')
        self.assertEqual(denied['error']['code'], 'scope_forbidden')

    async def test_help_reads_the_shipped_single_source_without_persisting_a_copy(self):
        view = importlib.import_module(PACKAGE.__name__ + '.ees_workflow_view')
        source = ROOT / 'agent-pack/skills/ees-work-demo/scripts/workflow_help.json'
        expected = json.loads(source.read_text(encoding='utf-8'))
        actual = (await self.state())['help']
        self.assertEqual(actual['source'], expected['source'])
        self.assertEqual([{key: value for key, value in term.items() if key != 'evidence'}
                          for term in actual['terms']], expected['terms'])
        ids = [term['id'] for term in actual['terms']]
        self.assertEqual(len(ids), len(set(ids)))
        for term in actual['terms']:
            self.assertTrue(set(term['related']) <= set(ids))
            self.assertEqual(term['evidence'], f"근거 · EES Work 도움말 ‘{term['name']}’")
        self.assertIn('도움말에 없는 내용', actual['answer_guidance']['unknown'])
        # Move the canonical source for this test only. The response must read
        # the changed file, not a duplicated hard-coded explanation or DB row.
        expected['terms'][0]['summary'] = '시험용 원본 변경'
        (Path(self.temp.name) / 'workflow_help.json').write_text(json.dumps(expected), encoding='utf-8')
        before = self.database.read_bytes()
        with patch.object(view, '__file__', str(Path(self.temp.name) / 'ees_workflow_view.py')):
            changed = await self.state()
        self.assertEqual(changed['help']['terms'][0]['summary'], '시험용 원본 변경')
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual((await self.state())['help'], actual)

    async def test_procedure_examples_are_public_summaries_from_one_shipped_source(self):
        source = ROOT / 'agent-pack/skills/ees-work-demo/scripts/workflow_procedure_examples.json'
        examples = json.loads(source.read_text(encoding='utf-8'))
        before = self.database.read_bytes()
        state = await self.state('c')
        self.assertFalse(state['capabilities']['can_author'])
        self.assertEqual(state['workflows'], [])
        self.assertEqual(self.database.read_bytes(), before)
        summaries = state['procedure_examples']
        self.assertEqual([(item['id'], item['stage_count'], item['job_count']) for item in summaries],
            [('delivery_review', 4, 9), ('factory_rollout', 4, 6), ('daily_check', 1, 1)])
        self.assertTrue(all('definition' not in item and 'nodes' not in item for item in summaries))
        self.assertEqual([item['name'] for item in summaries], [item['name'] for item in examples])
        # A program-data edit must reach both the public summary and the draft
        # created by ID. Client-provided or duplicated template bodies cannot.
        examples[1]['name'] = '변경된 합성 예시'
        root = next(node for node in examples[1]['definition']['nodes'].values() if node['type'] == 'p')
        stage = examples[1]['definition']['nodes'][root['children'][0]]
        stage['name'] = '변경된 합성 단계'
        (Path(self.temp.name) / source.name).write_text(json.dumps(examples), encoding='utf-8')
        with patch.object(workspace, '__file__', str(Path(self.temp.name) / 'ees_workflow_workspace.py')):
            self.assertEqual((await self.state())['procedure_examples'][1]['stages'][0]['name'], '변경된 합성 단계')
            created = await self.command('create_workflow', system_id='EMS', template_id='factory_rollout')
        self.assertTrue(created['ok'], created)
        self.assertEqual(created['workflow']['draft']['name'], '변경된 합성 예시')
        self.assertIn('변경된 합성 단계', [node['name'] for node in created['workflow']['draft']['nodes'].values()])
        self.assertEqual((await self.state())['procedure_examples'], summaries)

    async def test_procedure_examples_create_fresh_unpublished_unconnected_drafts_only(self):
        existing_id, existing_definition, _ = await self.create()
        granted = await self.command('save_access', principal_kind='user', principal_id='c',
            system_id='EMS', factory_id='*', roles=['viewer'])
        self.assertTrue(granted['ok'], granted)
        protected = ('work_versions', 'work_runs', 'work_settings', 'work_schedules',
                     'work_schedule_slots', 'work_factories', 'work_tool_contracts')
        def snapshot():
            with self.service._db() as db:
                return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)] for table in protected}
        before = snapshot()
        source = ROOT / 'agent-pack/skills/ees-work-demo/scripts/workflow_procedure_examples.json'
        original = source.read_bytes(); canonical = json.loads(original)
        used_ids, created_ids = set(), set()
        for example, counts, category, mode, scope in zip(canonical, [(4, 9), (4, 6), (1, 1)],
                ['ops', 'setup', 'ops'], ['periodic', 'on_demand', 'periodic'], [None, 'factory', None]):
            for attempt in range(2):
                name = example['name'] + ' 합성 초안 ' + str(attempt)
                result = await self.command('create_workflow', actor='a', system_id='EMS',
                    template_id=example['id'], name=name)
                self.assertTrue(result['ok'], result)
                record, key = result['workflow'], result['workflow_id']; definition = record['draft']
                self.assertIsNone(record['published_version'])
                self.assertEqual(result['revision'], 1)
                self.assertNotIn(key, created_ids); created_ids.add(key)
                nodes = definition['nodes']; self.assertTrue(set(nodes).isdisjoint(used_ids)); used_ids.update(nodes)
                self.assertTrue(set(nodes).isdisjoint(example['definition']['nodes']))
                self.assertEqual((sum(n['type'] == 't' for n in nodes.values()), sum(n['type'] == 'j' for n in nodes.values())), counts)
                self.assertEqual((definition['category'], definition['mode'], definition.get('execution_scope')), (category, mode, scope))
                self.assertEqual(definition['system_id'], 'EMS')
                self.assertEqual(next(n['name'] for n in nodes.values() if n['type'] == 'p'), name)
                self.assertNotIn('schedule', definition)
                self.assertEqual(workspace.definition_check(definition, False)[0], [])
                tools = [node for node in nodes.values() if node.get('mode') == 'tool']
                self.assertTrue(tools)
                self.assertTrue(all(not node.get('tool_reference') and not node.get('tool_contract_id') for node in nodes.values()))
                self.assertTrue(all(not node.get('model_id') for node in nodes.values()))
                checked = await self.command('validate_workflow', actor='a', workflow_id=key, expected_revision=1)
                self.assertTrue(checked['ok'], checked)
                self.assertTrue(any('도구 참조' in error for error in checked['validation']['errors']))
                blocked = await self.command('publish_workflow', actor='a', workflow_id=key, expected_revision=1)
                self.assertEqual(blocked['error']['code'], 'validation_required')
        self.assertEqual(snapshot(), before)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(created_ids.isdisjoint({item['id'] for item in (await self.state('c'))['workflows']}))
        self.assertEqual((await self.state(workflow_id=existing_id))['workflow']['draft'], existing_definition)

    async def test_procedure_example_identifier_overrides_and_manager_scope_are_checked(self):
        for invalid in ('missing', '../workflow_help.json', '', None, False, {'id': 'daily_check'}):
            with self.subTest(template_id=invalid):
                result = await self.command('create_workflow', actor='a', system_id='EMS', template_id=invalid)
                self.assertEqual(result['error']['code'], 'procedure_example_not_found')
        for field, value in (('definition', {'nodes': {}}), ('nodes', {}), ('category', 'incident'),
                             ('mode', 'emergency'), ('execution_scope', 'system'), ('schedule', {})):
            result = await self.command('create_workflow', actor='a', system_id='EMS', template_id='daily_check', **{field: value})
            self.assertEqual(result['error']['code'], 'procedure_example_override')
        for actor, system in (('c', 'EMS'), ('a', 'FDC')):
            result = await self.command('create_workflow', actor=actor, system_id=system, template_id='daily_check')
            self.assertEqual(result['error']['code'], 'scope_forbidden')
        bad_revision = await self.command('create_workflow', actor='a', system_id='EMS',
            template_id='daily_check', expected_revision=1)
        self.assertEqual(bad_revision['error']['code'], 'revision_conflict')
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_definitions').fetchone()[0], 0)
        blank = await self.command('create_workflow', actor='a', system_id='EMS', name='이름만 정한 절차')
        self.assertTrue(blank['ok'], blank)
        definition = blank['workflow']['draft']
        self.assertEqual((definition['category'], definition['mode']), ('ops', 'on_demand'))
        self.assertNotIn('execution_scope', definition)
        self.assertEqual(len(definition['nodes']), 1)

    async def test_procedure_example_retry_keeps_one_draft_and_rechecks_manager_permission(self):
        body = {'action': 'create_workflow', 'system_id': 'EMS', 'template_id': 'factory_rollout',
                'name': '재시도 합성 초안', 'expected_revision': 0, 'request_id': 'example-retry'}
        first = await self.service.workspace_command(self.users['a'], body)
        self.assertTrue(first['ok'], first)
        self.assertEqual(await self.service.workspace_command(self.users['a'], body), first)
        changed = await self.service.workspace_command(self.users['a'], {**body, 'template_id': 'daily_check'})
        self.assertEqual(changed['error']['code'], 'request_conflict')
        grant = next(item for item in (await self.state('admin'))['access'] if item['principal_id'] == 'a')
        revoked = await self.command('save_access', access_id=grant['id'], system_id='EMS', factory_id='*',
            principal_kind='user', principal_id='a', roles=['viewer'], expected_revision=grant['revision'])
        self.assertTrue(revoked['ok'], revoked)
        replay = await self.service.workspace_command(self.users['a'], body)
        self.assertEqual(replay['error']['code'], 'scope_forbidden')
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_definitions').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM work_audit WHERE action='create_workflow'").fetchone()[0], 1)

    async def test_versions_are_immutable_and_open_run_uses_original(self):
        key, definition, revision = await self.create()
        run = await self.start(key)
        definition['name'] = '변경된 이름'
        self.assertTrue((await self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition))['ok'])
        self.assertTrue((await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1))['ok'])
        self.assertTrue((await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1))['ok'])
        actual = (await self.state(run_id=run['id']))['run']
        self.assertEqual(actual['definition']['name'], '검증 절차'); self.assertEqual(actual['version'], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.service._db(write=True) as db:
                db.execute("UPDATE work_versions SET hash='tampered'")

    async def test_copy_delivery_pipeline_remaps_only_definition_owned_references(self):
        key, definition, revision = await self.create(block='list_confirm', dependent=True)
        next_job = definition['nodes']['next']
        next_job.update(mode='ai', result_block='item_verdict', result_source_job_id='j', effect_job_id='j',
                        effect_criterion={'job_id': 'j', 'native_record': 'j'}, tool_contract_id='j',
                        tool_reference={'tool_id': 'j', 'function': 'j', 'content_hash': 'pinned'},
                        inputs=[{'id': 'j', 'type': 'text'}],
                        argument_bindings={'issues': {'result': {'job_id': 'j', 'path': ['items'], 'value_field': 'id', 'confirmed': True}},
                                           'field': {'input': 'j'}, 'literal': {'constant': {'job_id': 'j'}}})
        definition['factory_overrides'] = {'j': {'factory_id': 'j', 'note': 'j'}}
        definition['mode'] = 'periodic'
        definition['schedule'] = {'frequency': 'weekly', 'interval': 2, 'timezone': 'UTC',
            'anchor': '2026-10-06T09:00:00', 'weekday': 1,
            'stage_deadlines': {'t': {'offset_days': -8, 'end_offset_days': -6}}}
        saved = await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        copied = await self.command('copy_workflow', workflow_id=key, expected_revision=saved['revision'], name='Copied pipeline')
        self.assertTrue(copied['ok'], copied)
        actual = copied['workflow']['draft']; nodes = {node['name']: node for node in actual['nodes'].values()}
        source_id, target = nodes['작업']['id'], nodes['next']
        self.assertTrue(set(actual['nodes']).isdisjoint(definition['nodes']))
        self.assertEqual(target['deps'], [source_id])
        self.assertEqual(target['result_source_job_id'], source_id)
        self.assertEqual(target['effect_job_id'], source_id)
        self.assertEqual(target['effect_criterion'], {'job_id': source_id, 'native_record': 'j'})
        self.assertEqual(target['argument_bindings']['issues']['result']['job_id'], source_id)
        self.assertEqual(target['argument_bindings']['field'], {'input': 'j'})
        self.assertEqual(target['argument_bindings']['literal'], {'constant': {'job_id': 'j'}})
        self.assertEqual(target['inputs'][0]['id'], 'j'); self.assertEqual(target['tool_contract_id'], 'j')
        self.assertEqual(target['tool_reference'], next_job['tool_reference'])
        self.assertEqual(actual['factory_overrides'], {source_id: {'factory_id': 'j', 'note': 'j'}})
        self.assertEqual(actual['schedule']['stage_deadlines'], {nodes['단계']['id']: {'offset_days': -8, 'end_offset_days': -6}})
        self.assertEqual(actual['schedule']['anchor'], definition['schedule']['anchor'])
        self.assertEqual(workspace.definition_check(actual)[0], [])
        with self.service._db() as db:
            original = json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?', (key,)).fetchone()[0])
            versions = db.execute('SELECT COUNT(*) FROM work_versions WHERE workflow_id=?', (actual['id'],)).fetchone()[0]
        self.assertEqual(original, definition); self.assertEqual(versions, 0)

    async def test_draft_conflict_receipt_and_atomic_invalid_publish(self):
        result = await self.command('create_workflow', system_id='EMS', name='초안')
        body = {'action': 'save_draft', 'workflow_id': result['workflow_id'], 'definition': result['workflow']['draft'], 'expected_revision': 1, 'request_id': str(uuid4())}
        a = await self.service.workspace_command(self.users['admin'], body)
        b = await self.service.workspace_command(self.users['admin'], body)
        self.assertEqual(a, b)
        bad = await self.service.workspace_command(self.users['admin'], dict(body, definition={**body['definition'], 'name': '충돌'}))
        self.assertEqual(bad['error']['code'], 'request_conflict')
        stale = await self.command('save_draft', workflow_id=result['workflow_id'], definition=body['definition'], expected_revision=1)
        self.assertEqual(stale['error']['code'], 'revision_conflict')
        failed = await self.command('publish_workflow', workflow_id=result['workflow_id'], expected_revision=2)
        self.assertEqual(failed['error']['code'], 'validation_required')
        with self.service._db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM work_versions').fetchone()[0], 0)

    async def test_setting_precedence_false_zero_empty_and_attempt_snapshot(self):
        fields = [{'id': 'amount', 'type': 'number', 'scope': 'workflow', 'required': True}, {'id': 'enabled', 'type': 'boolean', 'scope': 'workflow'}, {'id': 'note', 'type': 'text', 'scope': 'run'}]
        key, _, revision = await self.create(fields=fields)
        factory = await self.command('save_factory', factory_id='factory-1', system_id='EMS', name='합성 공장', attributes={'line': 1})
        self.assertTrue(factory['ok'], factory)
        self.assertTrue((await self.command('save_settings', workflow_id=key, values={'amount': 5, 'enabled': True}))['ok'])
        self.assertTrue((await self.command('save_settings', workflow_id=key, factory_id='factory-1', values={'amount': 0, 'enabled': False}))['ok'])
        run = await self.start(key, factory_id='factory-1', inputs={'note': ''})
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
        self.assertEqual(attempt['inputs'], {'amount': 0, 'enabled': False, 'note': ''})
        self.assertEqual(attempt['snapshot']['settings_sources']['amount']['scope'], 'factory')
        await self.command('save_settings', workflow_id=key, factory_id='factory-1', values={'amount': 99}, expected_revision=1)
        with self.service._db() as db:
            saved = json.loads(db.execute('SELECT snapshot FROM work_attempts WHERE id=?', (attempt['id'],)).fetchone()[0])
        self.assertEqual(saved['inputs']['amount'], 0)
        forbidden = await self.command('save_inputs', actor='a', run_id=run['id'], expected_revision=2, inputs={'pat': 'not-a-real-secret'})
        self.assertEqual(forbidden['error']['code'], 'secret_forbidden')

    async def test_human_confirmation_retry_invalidates_only_dependents_and_history(self):
        key, _, _ = await self.create(dependent=True)
        run = await self.start(key)
        for job in ('j', 'next', 'independent'):
            result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id=job, expected_revision=run['revision'])
            self.assertTrue(result['ok'], result); run = result['run']
        self.assertEqual(run['progress']['completed'], 3)
        rerun = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'])
        self.assertTrue(rerun['ok'], rerun); run = rerun['run']
        self.assertEqual(run['jobs']['next']['status'], 'review_required')
        self.assertEqual(run['jobs']['independent']['status'], 'completed')
        self.assertEqual(len([attempt for attempt in run['attempts'] if attempt['job_id'] == 'j']), 2)
        self.assertEqual(len(run['jobs']['j']['decisions']), 2)

    async def test_private_runs_chat_links_and_ui_state_are_isolated(self):
        key, _, _ = await self.create()
        run = await self.start(key)
        self.assertEqual((await self.state('b'))['runs'], [])
        denied = await self.service.workspace_state(self.users['b'], run_id=run['id'])
        self.assertEqual(denied['error']['code'], 'run_not_found')
        bad_chat = await self.command('link_chat', actor='a', run_id=run['id'], chat_id='chat-b', expected_revision=1)
        self.assertEqual(bad_chat['error']['code'], 'chat_forbidden')
        good = await self.command('link_chat', actor='a', run_id=run['id'], chat_id='chat-a', expected_revision=1)
        self.assertTrue(good['ok'], good)
        self.assertTrue((await self.command('save_ui', actor='a', state={'selection': {'run_id': run['id']}, 'scroll': 23}))['ok'])
        self.assertEqual((await self.state('b'))['ui_state']['state'], {})

    async def test_selected_workflow_run_and_scope_must_describe_same_target(self):
        first, _, _ = await self.create(); second, _, _ = await self.create()
        for key in ('f1', 'f2'):
            await self.command('save_factory', factory_id=key, system_id='EMS', name=key, attributes={})
        await self.command('save_factory', factory_id='fdc', system_id='FDC', name='fdc', attributes={})
        run = await self.start(first, actor='admin', factory_id='f1')
        for query in ({'workflow_id': second, 'run_id': run['id']},
                      {'workflow_id': first, 'system_id': 'FDC'},
                      {'run_id': run['id'], 'system_id': 'FDC'},
                      {'run_id': run['id'], 'factory_id': 'f2'},
                      {'workflow_id': first, 'factory_id': 'fdc'}):
            with self.subTest(query=query):
                result = await self.service.workspace_state(self.users['admin'], **query)
                self.assertEqual(result['error']['code'], 'target_mismatch', result)
                self.assertNotIn('run', result); self.assertNotIn('workflow', result)
        same = await self.state('admin', workflow_id=first, run_id=run['id'], system_id='EMS', factory_id='f1')
        self.assertEqual(same['run']['workflow_id'], same['workflow']['id'])

    async def test_upstream_retry_while_dependent_runs_preserves_result_but_requires_review(self):
        key, definition, revision = await self.create(dependent=True)
        definition['nodes']['next']['human_confirmation'] = False
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        run = await self.start(key, revision=revision+2)
        done = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'])
        run = done['run']; old_source = run['jobs']['j']['current_attempt']
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            downstream = self.service._work_begin_attempt(db, actor, groups, run['id'], 'next', run['revision'])
        retry = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=downstream['revision'])
        self.assertTrue(retry['ok'], retry)
        self.assertNotEqual(retry['run']['jobs']['j']['current_attempt'], old_source)
        with self.service._db(write=True) as db:
            finished = self.service._work_finish_attempt(db, downstream['id'], 'succeeded', {'observed': 'old evidence'})
        self.assertEqual(finished['status'], 'review_required')
        actual = (await self.state(run_id=run['id']))['run']
        saved = next(item for item in actual['attempts'] if item['id'] == downstream['id'])
        self.assertEqual(saved['status'], 'succeeded'); self.assertEqual(saved['result'], {'observed': 'old evidence'})
        self.assertEqual(saved['snapshot']['prerequisite_sources']['j']['attempt_id'], old_source)
        self.assertTrue(actual['jobs']['next']['result_stale'])
        denied = await self.command('decide', actor='a', run_id=run['id'], job_id='next', result_revision=1, verdict='completed', expected_revision=actual['revision'])
        self.assertEqual(denied['error']['code'], 'stale_result')

    async def test_old_waiting_result_cannot_be_confirmed_after_upstream_retry(self):
        key, _, _ = await self.create(dependent=True); run = await self.start(key)
        done = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            downstream = self.service._work_begin_attempt(db, actor, groups, run['id'], 'next', done['revision'])
            self.service._work_finish_attempt(db, downstream['id'], 'succeeded', {'old': 'unconfirmed'})
        before = (await self.state(run_id=run['id']))['run']
        retry = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=before['revision'])
        denied = await self.command('decide', actor='a', run_id=run['id'], job_id='next', result_revision=1, verdict='completed', expected_revision=retry['revision'])
        self.assertEqual(denied['error']['code'], 'stale_result')
        current = (await self.state(run_id=run['id']))['run']
        self.assertEqual(current['jobs']['next']['decisions'], [])
        self.assertEqual(current['jobs']['next']['status'], 'review_required')

    async def test_transitive_source_retry_keeps_inflight_unknown_as_unknown(self):
        key, definition, revision = await self.create(dependent=True)
        definition['nodes']['independent']['deps'] = ['next']
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        run = await self.start(key, revision=revision+2)
        for job in ('j', 'next'):
            result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id=job, expected_revision=run['revision'])
            self.assertTrue(result['ok'], result); run = result['run']
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'independent', run['revision'])
        self.assertEqual(set(attempt['snapshot']['prerequisite_sources']), {'j', 'next'})
        retry = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=attempt['revision'])
        self.assertTrue(retry['ok'], retry)
        with self.service._db(write=True) as db:
            finished = self.service._work_finish_attempt(db, attempt['id'], 'unknown', {'error': {'code': 'response_lost'}})
        self.assertEqual(finished['status'], 'unknown')
        current = (await self.state(run_id=run['id']))['run']
        self.assertEqual(current['jobs']['independent']['status'], 'unknown')
        self.assertTrue(current['jobs']['independent']['result_stale'])

    async def test_inherited_stage_dependencies_cannot_publish_a_job_cycle(self):
        key, definition, _ = await self.create(dependent=True)
        root = next(node for node in definition['nodes'].values() if node['type'] == 'p')
        root['children'].append('stage2')
        definition['nodes']['stage2'] = {'id': 'stage2', 'type': 't', 'name': 'stage2', 'parent': root['id'], 'children': ['next'], 'deps': []}
        definition['nodes']['t']['children'].remove('next')
        definition['nodes']['t']['deps'] = ['stage2']
        definition['nodes']['next']['parent'] = 'stage2'
        # Raw edges t -> stage2 and next -> j have no literal cycle, but
        # expanding stages makes j -> next -> j and must fail publication.
        errors, _ = workspace.definition_check(definition)
        self.assertTrue(any('P/T' in error and '순환' in error for error in errors), errors)

    async def test_group_task_claim_is_atomic_and_membership_revocation_blocks(self):
        key, _, _ = await self.create()
        run = await self.start(key, sharing={'group_ids': ['g']})
        self.assertEqual(len((await self.state('b'))['my_work']), 1)
        self.assertIsNone((await self.state('b', run_id=run['id']))['run']['jobs']['j']['claim_actor'])
        claimed = await self.command('claim_task', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertTrue(claimed['ok'], claimed)
        conflict = await self.command('claim_task', actor='b', run_id=run['id'], job_id='j', expected_revision=claimed['revision'])
        self.assertEqual(conflict['error']['code'], 'task_claimed')
        self.memberships['b'] = []
        self.assertEqual((await self.state('b'))['runs'], [])

    async def test_factory_unknown_is_blocked_not_excluded_and_conditions_safe(self):
        key, definition, revision = await self.create()
        definition['nodes']['j']['condition'] = {'field': 'tier', 'op': 'eq', 'value': 'production'}
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        run = await self.start(key, revision=revision + 2)
        self.assertEqual(run['jobs']['j']['status'], 'blocked')
        self.assertEqual(run['progress']['excluded'], 0)
        result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertEqual(result['error']['code'], 'factory_condition_unknown')
        definition['nodes']['j']['condition'] = {'eval': '__import__("os")'}
        self.assertTrue(workspace.definition_check(definition)[0])

    async def test_partial_result_item_decisions_cannot_create_success(self):
        key, _, _ = await self.create(block='item_verdict')
        run = await self.start(key)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
            self.service._work_finish_attempt(db, attempt['id'], 'partial', {'items': [{'id': 'cr-1'}, {'id': 'cr-2'}]})
        run = (await self.state(run_id=run['id']))['run']
        for item in ('cr-1', 'cr-2'):
            result = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id=item, verdict='completed', expected_revision=run['revision'], result_revision=run['jobs']['j']['result_revision'])
            self.assertTrue(result['ok'], result); run = result['run']
        self.assertEqual(run['jobs']['j']['status'], 'partial')
        close = await self.command('close_run', actor='a', run_id=run['id'], expected_revision=run['revision'])
        self.assertEqual(close['error']['code'], 'completion_required')

    async def test_closed_run_is_read_only_and_historical_progress_survives_restart(self):
        key, _, _ = await self.create()
        run = await self.start(key)
        result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertTrue(result['ok'], result)
        closed = await self.command('close_run', actor='a', run_id=run['id'], expected_revision=result['revision'])
        self.assertTrue(closed['ok'], closed)
        self.service = self.new_service()
        saved = (await self.state(run_id=run['id']))['run']; self.assertEqual(saved['progress']['completed'], 1)
        fail = await self.command('save_inputs', actor='a', run_id=run['id'], inputs={}, expected_revision=saved['revision'])
        self.assertEqual(fail['error']['code'], 'run_closed')

    async def test_missing_schema_is_not_silently_initialized(self):
        with self.service._db(write=True) as db: db.execute('DROP TABLE work_ui')
        with self.assertRaises(workflow.WorkflowError) as failure: self.new_service()
        self.assertEqual(failure.exception.code, 'workspace_corrupt')

    async def test_factory_specific_members_do_not_gain_all_factory_authority(self):
        key, _, _ = await self.create()
        for factory in ('f1', 'f2'):
            self.assertTrue((await self.command('save_factory', factory_id=factory, system_id='EMS', name=factory, attributes={}))['ok'])
        self.assertTrue((await self.command('save_access', principal_kind='user', principal_id='c', system_id='EMS', factory_id='f1', roles=['participant']))['ok'])
        state = await self.state('c', system_id='EMS')
        self.assertEqual([item['id'] for item in state['factories']], ['f1'])
        self.assertEqual([item['id'] for item in state['workflows']], [key])
        denied = await self.command('start_run', actor='c', workflow_id=key, factory_id='', expected_revision=3)
        self.assertEqual(denied['error']['code'], 'scope_forbidden')
        run = await self.start(key, actor='c', factory_id='f1')
        self.assertEqual(run['factory_id'], 'f1')
        denied = await self.command('start_run', actor='c', workflow_id=key, factory_id='f2', expected_revision=3)
        self.assertEqual(denied['error']['code'], 'scope_forbidden')

    async def test_input_change_during_execution_preserves_snapshot_and_requires_recheck(self):
        key, _, _ = await self.create(fields=[{'id': 'text', 'type': 'text', 'scope': 'run'}])
        run = await self.start(key, inputs={'text': 'before'})
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
        saved = await self.command('save_inputs', actor='a', run_id=run['id'], inputs={'text': 'after'}, expected_revision=2)
        self.assertTrue(saved['ok'], saved)
        with self.service._db(write=True) as db:
            result = self.service._work_finish_attempt(db, attempt['id'], 'succeeded', {'answer': 'old evidence'})
        self.assertEqual(result['status'], 'review_required')
        run = (await self.state(run_id=run['id']))['run']
        self.assertTrue(run['jobs']['j']['result_stale'])
        self.assertEqual(run['attempts'][0]['inputs']['text'], 'before')
        failure = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id='job', verdict='completed', result_revision=1, expected_revision=run['revision'])
        self.assertEqual(failure['error']['code'], 'stale_result')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.service._db(write=True) as db:
                db.execute("UPDATE work_attempts SET result='{}' WHERE id=?", (attempt['id'],))

    async def test_native_id_validation_and_corrupt_draft_are_not_replaced(self):
        nonexistent = await self.command('save_access', principal_kind='user', principal_id='not-native', system_id='EMS', factory_id='*', roles=['participant'])
        self.assertEqual(nonexistent['error']['code'], 'native_user_required')
        key, _, _ = await self.create()
        with self.service._db(write=True) as db: db.execute("UPDATE work_definitions SET draft='broken json' WHERE id=?", (key,))
        self.service = self.new_service()
        state = await self.service.workspace_state(self.users['admin'], workflow_id=key)
        self.assertFalse(state['ok'])
        with self.service._db() as db: self.assertEqual(db.execute('SELECT draft FROM work_definitions WHERE id=?', (key,)).fetchone()[0], 'broken json')

    async def test_stale_per_item_decision_cannot_confirm_new_attempt(self):
        key, _, _ = await self.create(block='item_verdict')
        run = await self.start(key)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        for version in (1, 2):
            run = (await self.state(run_id=run['id']))['run']
            with self.service._db(write=True) as db:
                attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', run['revision'])
                self.service._work_finish_attempt(db, attempt['id'], 'succeeded', {'items': [{'id': 'cr-1'}]})
        run = (await self.state(run_id=run['id']))['run']
        stale = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id='cr-1', verdict='completed', expected_revision=run['revision'], result_revision=1)
        self.assertEqual(stale['error']['code'], 'result_revision_conflict')
        good = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id='cr-1', verdict='completed', expected_revision=run['revision'], result_revision=2)
        self.assertTrue(good['ok'], good)

    async def test_list_amendment_creates_new_evidence_preserves_original_and_reason(self):
        key, _, _ = await self.create(block='list_confirm')
        run = await self.start(key)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
            self.service._work_finish_attempt(db, attempt['id'], 'succeeded', {'items': [{'id': 'cr-1', 'title': 'original'}]})
        run = (await self.state(run_id=run['id']))['run']
        result = await self.command('amend_items', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'], result_revision=1, items=[{'id': 'cr-2', 'title': '추가'}], reason='누락 건 보완')
        self.assertTrue(result['ok'], result)
        attempts = result['run']['attempts']; self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['result']['items'][0]['id'], 'cr-1')
        self.assertEqual(attempts[1]['result']['amendment']['removed_ids'], ['cr-1'])
        self.assertEqual(attempts[1]['result']['amendment']['added_ids'], ['cr-2'])
        self.assertEqual(attempts[1]['result']['items'][0]['source']['kind'], 'human_added')
        self.assertEqual(result['run']['jobs']['j']['status'], 'waiting_confirmation')

    async def test_person_field_requires_actual_native_id(self):
        key, _, _ = await self.create(fields=[{'id': 'person', 'type': 'person', 'scope': 'run'}])
        invalid = await self.command('start_run', actor='a', workflow_id=key, expected_revision=3, inputs={'person': {'kind': 'user', 'id': 'not-native'}})
        self.assertEqual(invalid['error']['code'], 'native_user_required')
        run = await self.start(key, inputs={'person': {'kind': 'group', 'id': 'g'}})
        self.assertEqual(run['inputs']['person']['id'], 'g')

    async def test_settings_change_reopens_active_only_and_frozen_history_uses_old_value(self):
        key, _, _ = await self.create(fields=[{'id': 'n', 'type': 'number', 'scope': 'workflow', 'required': True}])
        await self.command('save_settings', workflow_id=key, values={'n': 1})
        closed = await self.start(key)
        done = await self.command('human_confirm', actor='a', run_id=closed['id'], job_id='j', expected_revision=1)
        await self.command('close_run', actor='a', run_id=closed['id'], expected_revision=done['revision'])
        active = await self.start(key)
        done = await self.command('human_confirm', actor='a', run_id=active['id'], job_id='j', expected_revision=1)
        await self.command('save_settings', workflow_id=key, values={'n': 2}, expected_revision=1)
        history = (await self.state(run_id=closed['id']))['run']; current = (await self.state(run_id=active['id']))['run']
        self.assertEqual(history['jobs']['j']['effective_inputs']['n'], 1)
        self.assertEqual(history['jobs']['j']['status'], 'completed')
        self.assertEqual(current['jobs']['j']['status'], 'review_required')
        self.assertEqual(current['jobs']['j']['effective_inputs']['n'], 2)

    async def test_two_connections_compete_for_one_group_task_without_double_claim(self):
        from concurrent.futures import ThreadPoolExecutor
        key, _, _ = await self.create(); run = await self.start(key, sharing={'group_ids': ['g']})
        second = self.new_service()
        def claim(service, actor):
            return asyncio.run(service.workspace_command(self.users[actor], {'action': 'claim_task', 'request_id': str(uuid4()), 'expected_revision': 1, 'run_id': run['id'], 'job_id': 'j'}))
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(claim, self.service, 'a'); other = pool.submit(claim, second, 'b')
            results = [first.result(), other.result()]
        self.assertEqual(sum(result['ok'] for result in results), 1, results)
        self.assertEqual([result['error']['code'] for result in results if not result['ok']], ['revision_conflict'])

    async def test_migration_preserves_legacy_bytes_and_rolls_back_partial_failure(self):
        from unittest.mock import patch
        published = '{"version":1,"nodes":{},"tools":{},"skills":{},"sites":{},"roots":{"setup":[],"ops":[],"incident":[]},"systems":["EMS","APC","FDC","EGIS","EPT"]}'
        draft = published.replace('"version":1', '"version":2')
        case = '{"id":"historical-private","owner":"a","mock":true,"record":"원본 보존"}'
        with self.service._db(write=True) as db:
            db.execute('UPDATE catalog SET published=?,draft=?,revision=7,validated=6 WHERE id=1', (published, draft))
            db.execute('INSERT INTO cases VALUES(?,?,NULL,?)', ('historical-private', 'a', case))
            db.execute('CREATE TABLE user_extension(id TEXT PRIMARY KEY,data TEXT)')
            db.execute('INSERT INTO user_extension VALUES(?,?)', ('keep', 'user owned'))
        self.service = self.new_service()
        with self.service._db() as db:
            self.assertEqual(tuple(db.execute('SELECT published,draft,revision,validated FROM catalog').fetchone()), (published, draft, 7, 6))
            self.assertEqual(db.execute('SELECT data FROM cases WHERE id=?', ('historical-private',)).fetchone()[0], case)
            archived = db.execute('SELECT published,draft,revision,validated FROM authoring_legacy WHERE revision=7').fetchone()
            self.assertEqual(tuple(archived), (published, draft, 7, 6))
            self.assertEqual(db.execute('SELECT data FROM user_extension').fetchone()[0], 'user owned')
        def fail_migration(subject, db):
            db.execute('CREATE TABLE incomplete_upgrade(id TEXT)')
            db.execute('UPDATE catalog SET revision=99')
            raise RuntimeError('synthetic migration failure')
        with patch.object(workspace.WorkspaceMixin, '_init_workspace', fail_migration):
            with self.assertRaisesRegex(RuntimeError, 'synthetic migration failure'):
                self.new_service()
        with self.service._db() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='incomplete_upgrade'").fetchone())
            self.assertEqual(tuple(db.execute('SELECT published,draft,revision,validated FROM catalog').fetchone()), (published, draft, 7, 6))
            self.assertEqual(db.execute('SELECT data FROM cases WHERE id=?', ('historical-private',)).fetchone()[0], case)

    async def test_publish_lost_response_replay_after_revision_changed_is_idempotent(self):
        key, definition, revision = await self.create()
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        body = {'action': 'publish_workflow', 'workflow_id': key, 'request_id': str(uuid4()), 'expected_revision': revision + 1}
        first = await self.service.workspace_command(self.users['admin'], body)
        second = await self.service.workspace_command(self.users['admin'], body)
        self.assertTrue(first['ok'], first)
        self.assertEqual(first, second)
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_versions WHERE workflow_id=?', (key,)).fetchone()[0], 2)

    async def test_native_skill_revision_is_checked_at_publication_and_body_not_copied(self):
        assets = {'tools': [], 'skills': [{'id': 'native-skill', 'name': '사용자 지침'}], 'skill_bodies': {'native-skill': 'private instruction one'}, 'skill_versions': {'native-skill': 1}, 'available': True}
        self.service.asset_lookup = lambda actor: deepcopy(assets)
        key, definition, revision = await self.create()
        definition['nodes']['j']['skills'] = ['native-skill']
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        checked = await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        self.assertFalse(checked['validation']['errors'], checked)
        assets['skill_versions']['native-skill'] = 2
        assets['skill_bodies']['native-skill'] = 'private instruction two'
        stale = await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        self.assertEqual(stale['error']['code'], 'validation_required')
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        published = await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        self.assertTrue(published['ok'], published)
        state = await self.state(workflow_id=key)
        ref = state['workflow']['published']['resource_versions']['skills']['native-skill']
        self.assertEqual(ref['revision'], 2)
        self.assertNotIn('private instruction', json.dumps(state['workflow']['published']))

    async def test_native_authority_revoked_during_registry_await_cannot_publish(self):
        assets = {'tools': [], 'skills': [{'id': 'native-skill', 'name': '지침'}], 'skill_bodies': {'native-skill': 'instruction'}, 'skill_versions': {'native-skill': 1}, 'available': True}
        self.service.asset_lookup = lambda actor: deepcopy(assets)
        key, definition, revision = await self.create()
        definition['nodes']['j']['skills'] = ['native-skill']
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        async def revoked(actor):
            self.users['admin']['role'] = 'pending'
            return deepcopy(assets)
        self.service.asset_lookup = revoked
        result = await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        self.assertEqual(result['error']['code'], 'unauthorized')
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_versions WHERE workflow_id=?', (key,)).fetchone()[0], 1)

    async def dynamic_fixture(self):
        class ChoiceBridge:
            def __init__(inner):
                inner.calls = []; inner.allowed = True; inner.partial = False; inner.after_call = None
            async def check(inner, actor, reference):
                if not inner.allowed: raise workflow.WorkflowError('native_access_denied', '권한이 없습니다.')
                return {'reference': reference}
            async def invoke(inner, actor, reference, arguments, context):
                inner.calls.append((actor['id'], deepcopy(arguments)))
                if inner.after_call: inner.after_call()
                return {'status': 'succeeded', 'completeness': 'partial' if inner.partial else 'complete', 'data': {'statuses': [{'id': '1', 'name': '검토', 'private_extra': 'must not leak'}, {'id': '2', 'name': '승인'}]}}
        bridge = ChoiceBridge(); self.service.operations.bridge = bridge
        fields = [{'id': 'project', 'type': 'single', 'options': ['ALLOWED'], 'required': True},
                  {'id': 'status', 'type': 'single', 'required': True, 'options_source': 'tool', 'depends_on': ['project'],
                   'options_query': {'reference': {'tool_id': 'native', 'function': 'metadata', 'content_hash': 'pinned'}, 'argument_bindings': {'project_key': {'input': 'project'}}, 'result_path': ['statuses'], 'value_field': 'id', 'label_field': 'name'}}]
        key, definition, revision = await self.create(fields=fields)
        run = await self.start(key, inputs={'project': 'ALLOWED', 'status': '1'})
        return bridge, key, definition, run

    async def test_dynamic_native_choices_bind_dependencies_and_snapshot_actual_options(self):
        bridge, key, definition, run = await self.dynamic_fixture()
        result = await self.service.input_options(self.users['a'], {'run_id': run['id'], 'job_id': 'j', 'field_id': 'status'})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['options'], [{'id': '1', 'name': '검토'}, {'id': '2', 'name': '승인'}])
        self.assertEqual(bridge.calls[-1], ('a', {'project_key': 'ALLOWED'}))
        self.assertNotIn('private_extra', json.dumps(result))
        finished = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'])
        self.assertTrue(finished['ok'], finished)
        choices = finished['run']['attempts'][0]['snapshot']['options']['status']
        self.assertEqual(choices['options'], result['options'])
        self.assertEqual(choices['source']['reference']['content_hash'], 'pinned')

    async def test_dynamic_invalid_choice_partial_and_revocation_never_fall_back_static(self):
        bridge, _, _, run = await self.dynamic_fixture()
        saved = await self.command('save_inputs', actor='a', run_id=run['id'], inputs={'project': 'ALLOWED', 'status': 'not-allowed'}, expected_revision=run['revision'])
        self.assertTrue(saved['ok'], saved)
        failed = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=saved['revision'])
        self.assertEqual(failed['error']['code'], 'input_required')
        bridge.partial = True
        partial = await self.service.input_options(self.users['a'], {'run_id': run['id'], 'job_id': 'j', 'field_id': 'status'})
        self.assertEqual(partial['error']['code'], 'options_unavailable')
        bridge.partial = False; bridge.allowed = False
        denied = await self.service.input_options(self.users['a'], {'run_id': run['id'], 'job_id': 'j', 'field_id': 'status'})
        self.assertEqual(denied['error']['code'], 'native_access_denied')
        with self.service._db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM work_attempts').fetchone()[0], 0)

    async def test_dynamic_choice_late_response_cannot_cross_input_revision(self):
        bridge, _, _, run = await self.dynamic_fixture()
        def changed():
            with self.service._db(write=True) as db:
                db.execute('UPDATE work_runs SET revision=revision+1 WHERE id=?', (run['id'],))
        bridge.after_call = changed
        result = await self.service.input_options(self.users['a'], {'run_id': run['id'], 'job_id': 'j', 'field_id': 'status'})
        self.assertEqual(result['error']['code'], 'options_context_changed')
        self.assertNotIn('options', result)

    async def test_common_options_use_current_factory_acl(self):
        for factory in ('f1', 'f2'):
            await self.command('save_factory', factory_id=factory, system_id='EMS', name=factory, attributes={})
        await self.command('save_access', principal_kind='user', principal_id='c', system_id='EMS', factory_id='f1', roles=['participant'])
        key, _, _ = await self.create(fields=[{'id': 'target', 'type': 'single', 'options_source': 'common', 'options_query': {'kind': 'factories'}}])
        run = await self.start(key, actor='c', factory_id='f1')
        result = await self.service.input_options(self.users['c'], {'run_id': run['id'], 'job_id': 'j', 'field_id': 'target'})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['options'], [{'id': 'f1', 'name': 'f1'}])

    async def test_native_source_permission_revocation_redacts_owned_history_and_blocks_decision(self):
        bridge, _, _, run = await self.dynamic_fixture()
        result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertTrue(result['ok'], result)
        visible = (await self.state(run_id=run['id']))['run']
        self.assertIsNotNone(visible['attempts'][0]['result'])
        bridge.allowed = False
        hidden = (await self.state(run_id=run['id']))['run']
        self.assertIsNone(hidden['attempts'][0]['result'])
        self.assertEqual(hidden['attempts'][0]['evidence_access'], 'requires_current_source_access')
        self.assertNotIn('options', hidden['attempts'][0]['snapshot'])
        denied = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id='job', verdict='completed', expected_revision=hidden['revision'], result_revision=1)
        self.assertEqual(denied['error']['code'], 'native_access_denied')

    async def test_factory_manager_updates_only_own_override(self):
        await self.command('save_factory', factory_id='f1', system_id='EMS', name='f1', attributes={})
        await self.command('save_access', principal_kind='user', principal_id='c', system_id='EMS', factory_id='f1', roles=['manager'])
        key, _, _ = await self.create(fields=[{'id': 'n', 'type': 'number', 'scope': 'workflow'}])
        own = await self.command('save_settings', actor='c', workflow_id=key, factory_id='f1', values={'n': 0})
        self.assertTrue(own['ok'], own)
        default = await self.command('save_settings', actor='c', workflow_id=key, values={'n': 2})
        self.assertEqual(default['error']['code'], 'scope_forbidden')

    async def test_manual_execution_cannot_bypass_published_trigger(self):
        key, definition, revision = await self.create()
        definition['nodes']['j']['trigger'] = {'offset_seconds': 60}
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        run = await self.start(key, revision=revision + 2)
        start = __import__('datetime').datetime.fromisoformat(run['created_at']).timestamp()
        self.service.operations.clock = lambda: start + 59
        early = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertEqual(early['error']['code'], 'scheduled_time_required')
        self.service.operations.clock = lambda: start + 60
        on_time = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertTrue(on_time['ok'], on_time)

    async def test_concurrent_initialization_preserves_one_empty_schema(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        path = Path(self.temp.name) / 'concurrent-new.sqlite3'
        barrier = Barrier(3)
        def initialize():
            barrier.wait()
            return workflow.WorkflowService(path, self.users.get, lambda key: None)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(initialize) for _ in range(3)]
            services = [future.result() for future in futures]
        with services[0]._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM catalog').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_schema').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM work_definitions').fetchone()[0], 0)

    async def test_factory_scoped_field_never_accepts_default_or_run_values(self):
        await self.command('save_factory', factory_id='f1', system_id='EMS', name='f1', attributes={})
        key, _, _ = await self.create(fields=[{'id': 'threshold', 'type': 'number', 'scope': 'factory', 'required': True}])
        default = await self.command('save_settings', workflow_id=key, values={'threshold': 1})
        self.assertEqual(default['error']['code'], 'invalid_inputs')
        own = await self.command('save_settings', workflow_id=key, factory_id='f1', values={'threshold': 0})
        self.assertTrue(own['ok'], own)
        run = await self.start(key, factory_id='f1')
        self.assertEqual(run['jobs']['j']['effective_inputs']['threshold'], 0)
        overridden = await self.command('save_inputs', actor='a', run_id=run['id'], expected_revision=1, inputs={'threshold': 9})
        self.assertEqual(overridden['error']['code'], 'invalid_inputs')
        done = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        self.assertEqual(done['run']['attempts'][0]['snapshot']['settings_sources']['threshold']['scope'], 'factory')

    async def test_deadline_timezone_boundary_calendar_offset_and_attempt_snapshot(self):
        from datetime import datetime, timezone
        key, definition, revision = await self.create(fields=[{'id': 'date', 'type': 'datetime', 'scope': 'run', 'required': True}])
        definition['nodes']['j']['deadline'] = {'input': 'date', 'offset_days': -1, 'timezone': 'Asia/Seoul', 'calendar': 'calendar'}
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        self.service.operations.clock = lambda: datetime(2026,10,1,15,30,tzinfo=timezone.utc).timestamp()
        run = await self.start(key, revision=revision+2, inputs={'date': '2026-10-03'})
        self.assertEqual(run['jobs']['j']['deadline']['at'], '2026-10-02T00:00:00+09:00')
        self.assertEqual(run['jobs']['j']['deadline']['days_remaining'], 0)
        state = await self.state(run_id=run['id'])
        self.assertEqual(state['my_work'][0]['bucket'], 'today')
        done = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        snapshot = done['run']['attempts'][0]['snapshot']['deadline']
        self.assertEqual(snapshot['at'], '2026-10-02T00:00:00+09:00')
        await self.command('save_inputs', actor='a', run_id=run['id'], expected_revision=done['revision'], inputs={'date': '2026-10-05'})
        state = await self.state(run_id=run['id'])
        self.assertEqual(state['run']['jobs']['j']['deadline']['at'], '2026-10-04T00:00:00+09:00')
        self.assertEqual(state['run']['attempts'][0]['snapshot']['deadline'], snapshot)

    async def test_business_calendar_missing_does_not_invent_earlier_date(self):
        key, definition, revision = await self.create(fields=[{'id': 'date', 'type': 'datetime'}])
        definition['nodes']['j']['deadline'] = {'input': 'date', 'offset_days': -2, 'timezone': 'Asia/Seoul', 'calendar': 'business'}
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        run = await self.start(key, revision=revision+2, inputs={'date': '2026-10-03'})
        deadline = run['jobs']['j']['deadline']
        self.assertIsNone(deadline['at']); self.assertEqual(deadline['reason'], 'business_calendar_unconfigured')

    async def test_cross_job_deadline_setting_invalidates_decision_and_downstream(self):
        key, definition, revision = await self.create(dependent=True)
        definition['nodes']['independent']['inputs'] = [{'id': 'date', 'type': 'datetime', 'scope': 'workflow'}]
        definition['nodes']['j']['deadline'] = {'input': 'date', 'offset_days': -1, 'timezone': 'Asia/Seoul', 'calendar': 'calendar'}
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('save_settings', workflow_id=key, values={'date': '2026-10-03'})
        run = await self.start(key, revision=revision+2)
        for job in ('j', 'next'):
            result = await self.command('human_confirm', actor='a', run_id=run['id'], job_id=job, expected_revision=run['revision'])
            self.assertTrue(result['ok'], result); run = result['run']
        before = deepcopy(run['attempts'])
        changed = await self.command('save_settings', workflow_id=key, values={'date': '2026-10-04'}, expected_revision=1)
        self.assertTrue(changed['ok'], changed)
        actual = (await self.state(run_id=run['id']))['run']
        self.assertEqual(actual['jobs']['j']['status'], 'review_required')
        self.assertEqual(actual['jobs']['next']['status'], 'review_required')
        self.assertTrue(actual['jobs']['j']['result_stale'])
        self.assertEqual(actual['attempts'], before)
        with self.service._db() as db:
            self.assertFalse(self.service._work_dependencies_ready(db, run['id'], definition, 'next'))

    async def test_option_and_tool_input_bindings_require_current_job_declaration(self):
        key, definition, _ = await self.create(dependent=True, fields=[{'id': 'project', 'type': 'text'}])
        target = definition['nodes']['independent']
        target['inputs'] = [{'id': 'status', 'type': 'single', 'options_source': 'tool', 'depends_on': ['project'], 'options_query': {'reference': {'tool_id': 'native', 'function': 'metadata', 'content_hash': 'pinned'}, 'argument_bindings': {'project_key': {'input': 'project'}}, 'result_path': ['statuses'], 'value_field': 'id', 'label_field': 'name'}}]
        target['argument_bindings'] = {'project': {'input': 'project'}}
        errors, _ = workspace.definition_check(definition)
        self.assertTrue(any('같은 작업' in error for error in errors), errors)
        self.assertTrue(any('도구 인자' in error for error in errors), errors)
        target['inputs'].append(deepcopy(definition['nodes']['j']['inputs'][0]))
        self.assertEqual(workspace.definition_check(definition)[0], [])

    async def test_report_all_resolved_requires_actual_current_decisions_and_never_approves_source(self):
        key, definition, revision = await self.create(block='item_verdict', dependent=True)
        definition['nodes']['next'].update(mode='ai', result_block='ai_review', dependency_policy='all_resolved')
        await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        run = await self.start(key, revision=revision+2)
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
            self.service._work_finish_attempt(db, attempt['id'], 'succeeded', {'items': [{'id': 'cr-1'}, {'id': 'cr-2'}]})
            self.assertFalse(self.service._work_dependencies_ready(db, run['id'], definition, 'next'))
        run = (await self.state(run_id=run['id']))['run']
        for item, verdict in (('cr-1', 'completed'), ('cr-2', 'unknown')):
            result = await self.command('decide', actor='a', run_id=run['id'], job_id='j', item_id=item, verdict=verdict, result_revision=1, expected_revision=run['revision'])
            self.assertTrue(result['ok'], result); run = result['run']
            self.assertFalse(run['jobs']['j']['decision_summary']['all_approved'])
        self.assertEqual(run['jobs']['j']['status'], 'unknown')
        with self.service._db(write=True) as db:
            self.assertTrue(self.service._work_dependencies_ready(db, run['id'], definition, 'next'))
            report = self.service._work_begin_attempt(db, actor, groups, run['id'], 'next', run['revision'])
            self.service._work_finish_attempt(db, report['id'], 'succeeded', {'draft': '미확인 항목 존재'})
        state = await self.state(run_id=run['id'])
        self.assertEqual(state['run']['jobs']['next']['status'], 'waiting_confirmation')
        self.assertEqual(state['run']['jobs']['j']['status'], 'unknown')

    async def test_export_excludes_personal_ui_and_private_chat_links(self):
        key, _, _ = await self.create(); run = await self.start(key)
        await self.command('save_ui', actor='a', state={'draft': 'private editor draft'})
        await self.command('link_chat', actor='a', run_id=run['id'], chat_id='chat-a', expected_revision=1)
        result = await self.service.workspace_export(self.users['a'], run['id'])
        self.assertTrue(result['ok']); self.assertNotIn('chat_links', result['run'])
        self.assertNotIn('private editor draft', json.dumps(result))
        forbidden = await self.service.workspace_export(self.users['b'], run['id'])
        self.assertEqual(forbidden['error']['code'], 'run_not_found')

    async def test_explicit_claimant_release_preserves_evidence_and_allows_group_reclaim(self):
        key, _, _ = await self.create(); run = await self.start(key, sharing={'group_ids': ['g']})
        done = await self.command('human_confirm', actor='a', run_id=run['id'], job_id='j', expected_revision=1)
        before = done['run']; attempts = deepcopy(before['attempts']); decisions = deepcopy(before['jobs']['j']['decisions'])
        other = await self.command('release_task', actor='b', run_id=run['id'], job_id='j', expected_revision=before['revision'])
        self.assertEqual(other['error']['code'], 'task_claimed')
        released = await self.command('release_task', actor='a', run_id=run['id'], job_id='j', expected_revision=before['revision'])
        self.assertTrue(released['ok'], released)
        self.assertEqual(released['run']['attempts'], attempts)
        self.assertEqual(released['run']['jobs']['j']['decisions'], decisions)
        self.assertEqual(released['run']['jobs']['j']['status'], 'completed')
        self.assertIsNone(released['run']['jobs']['j']['claim_actor'])
        reclaimed = await self.command('claim_task', actor='b', run_id=run['id'], job_id='j', expected_revision=released['revision'])
        self.assertTrue(reclaimed['ok'], reclaimed)
        self.assertEqual(reclaimed['run']['jobs']['j']['claim_actor'], 'b')

    async def test_claimant_cannot_release_running_or_unresolved_external_request(self):
        key, _, _ = await self.create(); run = await self.start(key, sharing={'group_ids': ['g']})
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', 1)
        denied = await self.command('release_task', actor='a', run_id=run['id'], job_id='j', expected_revision=2)
        self.assertEqual(denied['error']['code'], 'execution_unresolved')
        with self.service._db(write=True) as db:
            self.service._work_finish_attempt(db, attempt['id'], 'unknown', {})
            db.execute('INSERT INTO work_external_requests VALUES(?,?,?,?,?,?,?)', ('synthetic-request', run['id'], 'j', 'a', 1, 'unknown', '{}'))
        run = (await self.state(run_id=run['id']))['run']
        denied = await self.command('release_task', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'])
        self.assertEqual(denied['error']['code'], 'execution_unresolved')


    async def test_on_demand_factory_start_is_atomic_and_other_scopes_remain_available(self):
        for factory in ('f1', 'f2'):
            await self.command('save_factory', factory_id=factory, system_id='EMS', name=factory)
        key, definition, revision = await self.create()
        definition['execution_scope'] = 'factory'
        await self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        published = await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        required = await self.command('start_run', actor='a', workflow_id=key, expected_revision=published['revision'])
        self.assertEqual(required['error']['code'], 'factory_required')
        outcomes = await asyncio.gather(*(self.command('start_run', actor=actor, workflow_id=key, factory_id='f1', expected_revision=published['revision']) for actor in ('a', 'b')))
        self.assertEqual(sum(item['ok'] for item in outcomes), 1)
        self.assertEqual(next(item for item in outcomes if not item['ok'])['error']['code'], 'factory_run_active')
        first = next(item['run'] for item in outcomes if item['ok'])
        second = await self.start(key, revision=published['revision'], factory_id='f2')
        # Each authorized active scope is discoverable for the selected workflow,
        # while normal displayed runs remain filtered by the current factory.
        visible = await self.state(workflow_id=key, factory_id='f1')
        self.assertEqual({item['factory_id'] for item in visible['workflow_active_runs']}, {'f1', 'f2'})
        self.assertEqual({item['factory_id'] for item in visible['runs']}, {'f1'})
        cancelled = await self.command('cancel_run', actor=first['owner'], run_id=first['id'], expected_revision=first['revision'], reason='합성 검사 종료')
        self.assertTrue(cancelled['ok'])
        replacement = await self.start(key, revision=published['revision'], factory_id='f1')
        self.assertNotEqual(replacement['id'], first['id']); self.assertNotEqual(second['id'], replacement['id'])

    async def test_system_scope_is_visible_across_factory_selection_without_broadening_acl(self):
        await self.command('save_factory', factory_id='f1', system_id='EMS', name='f1')
        key, definition, revision = await self.create()
        definition['execution_scope'] = 'system'
        await self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition)
        await self.command('validate_workflow', workflow_id=key, expected_revision=revision+1)
        published = await self.command('publish_workflow', workflow_id=key, expected_revision=revision+1)
        run = await self.start(key, revision=published['revision'], factory_id='f1', sharing={'group_ids': ['g']})
        self.assertEqual(run['factory_id'], '')
        visible = await self.state(workflow_id=key, run_id=run['id'], factory_id='f1')
        self.assertEqual(visible['run']['id'], run['id']); self.assertIn(run['id'], [item['id'] for item in visible['runs']])
        await self.command('save_access', principal_kind='user', principal_id='c', system_id='EMS', factory_id='f1', roles=['participant'])
        denied = await self.command('start_run', actor='c', workflow_id=key, factory_id='f1', expected_revision=published['revision'])
        self.assertFalse(denied['ok'])
        self.assertNotIn(run['id'], [item['id'] for item in (await self.state('c', workflow_id=key, factory_id='f1'))['runs']])

    async def test_judgment_rules_are_validated_and_missing_operational_policies_are_advisory(self):
        key, definition, revision = await self.create(mode='ai', block='item_verdict', dependent=True)
        node = definition['nodes']['j']
        node['judgments'] = [{'id': 'approve', 'label': '승인', 'status': 'completed', 'consequence': '필수 확인 후 완료'}, {'id': 'unknown', 'label': '미확인', 'status': 'unknown'}]
        node['suggestion_rules'] = {'provisional': True, 'description': '사람이 최종 확정', 'rules': [{'id': 'r1', 'condition': '근거가 부족함', 'outcome': 'none', 'judgment_id': ''}], 'human_only_judgment_ids': ['approve']}
        node['confirmation_notes'] = '승인 근거를 직접 확인합니다.'
        definition['unapproved_policy'] = 'hold'
        definition['nodes']['next'].update(mode='ai', result_block='ai_review', completion={'kind': 'delivery'})
        saved = await self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition)
        self.assertTrue(saved['ok'], saved)
        checked = await self.command('validate_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.assertEqual(checked['validation']['errors'], [])
        for term in ('D-5', '송부 방식', '임시값'):
            self.assertTrue(any(term in text for text in checked['validation']['warnings']))
        self.assertTrue(checked['validation']['checks'])
        published = await self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.assertTrue(published['ok'], published)
        run = await self.start(key, revision=published['revision'])
        self.assertEqual(run['definition']['nodes']['j']['suggestion_rules'], node['suggestion_rules'])
        invalid = deepcopy(definition); invalid['nodes']['j']['suggestion_rules']['human_only_judgment_ids'] = ['missing']
        self.assertTrue(workspace.definition_check(invalid)[0])


class DefinitionTests(unittest.TestCase):
    def test_all_eight_types_valid_and_invalid(self):
        values = {'text': '', 'number': 0, 'datetime': '2026-10-02T12:00:00+09:00', 'single': 'a', 'multi': ['a'], 'list': ['x'], 'person': {'kind': 'group', 'id': 'native-id'}, 'boolean': False}
        fields = [{'id': kind, 'type': kind, 'options': ['a', 'b']} for kind in workspace.INPUT_TYPES]
        self.assertEqual(workspace.input_errors(fields, values), [])
        for kind in values:
            with self.subTest(kind=kind):
                self.assertTrue(workspace.input_errors(fields, {**values, kind: None if False else {'invalid': True}}))

    def test_condition_three_valued_logic(self):
        self.assertIsNone(workspace._condition({'field': 'missing', 'op': 'eq', 'value': 1}, {}))
        self.assertFalse(workspace._condition({'all': [{'field': 'a', 'op': 'eq', 'value': 1}, {'field': 'b', 'op': 'eq', 'value': 2}]}, {'a': 0}))
        self.assertTrue(workspace._condition({'any': [{'field': 'a', 'op': 'eq', 'value': 1}, {'field': 'b', 'op': 'eq', 'value': 2}]}, {'a': 1}))



if __name__ == '__main__': unittest.main()
