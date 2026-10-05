"""Recovered Figma contract regressions; fresh runs, not prior lost evidence.

Uses synthetic identities and temporary SQLite. Native connector trust is tested
separately with the pinned Native fixture in test_ees_workflow_native.
"""
import asyncio
from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_ees_work_workspace as base

workflow, workspace = base.workflow, base.workspace


class EvidenceBridge:
    def __init__(self):
        self.allowed = True

    async def check(self, actor, reference):
        if not self.allowed:
            raise workflow.WorkflowError('native_access_denied', 'Synthetic source revoked')
        return {'reference': deepcopy(reference)}


class FigmaWorkspaceContracts(unittest.IsolatedAsyncioTestCase):
    # Reuse setup helpers only: do not accidentally rerun the 48 inherited tests.
    new_service = base.WorkspaceTests.new_service
    command = base.WorkspaceTests.command
    create = base.WorkspaceTests.create
    start = base.WorkspaceTests.start
    state = base.WorkspaceTests.state

    async def asyncSetUp(self):
        await base.WorkspaceTests.asyncSetUp(self)
        self.bridge = EvidenceBridge()
        self.service.operations.bridge = self.bridge

    async def prepared(self, *, mode='ai', block='ai_review', result=None,
                       status='succeeded', fields=None, change=None, dependent=False):
        key, definition, revision = await self.create(mode=mode, block=block, fields=fields, dependent=dependent)
        if change:
            change(definition)
            saved = await self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition)
            self.assertTrue(saved['ok'], saved)
            checked = await self.command('validate_workflow', workflow_id=key, expected_revision=saved['revision'])
            self.assertFalse(checked['validation']['errors'], checked)
            published = await self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
            self.assertTrue(published['ok'], published)
            revision = published['revision']
        run = await self.start(key, revision, sharing={'group_ids': ['g']})
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', run['revision'])
            snapshot = deepcopy(attempt['snapshot'])
            snapshot['source_references'] = [{'tool_id': 'native', 'function': 'get_page', 'content_hash': 'sha'}]
            snapshot['model'] = {'id': 'synthetic-model', 'revision': 1}
            snapshot['skills'] = [{'id': 'synthetic-skill', 'revision': 1}]
            db.execute('UPDATE work_attempts SET snapshot=? WHERE id=?', (json.dumps(snapshot), attempt['id']))
            self.service._work_finish_attempt(db, attempt['id'], status, result if result is not None else {'text': 'Original AI draft'})
        return (await self.state(run_id=run['id']))['run']

    @staticmethod
    def current(run):
        return next(item for item in run['attempts'] if item['id'] == run['jobs']['j']['current_attempt'])

    async def save_review(self, run, text='Reviewed draft', review_revision=0, **changes):
        attempt = self.current(run)
        values = dict(run_id=run['id'], job_id='j', attempt_id=attempt['id'],
                      result_revision=attempt['number'], expected_revision=run['revision'],
                      review_revision=review_revision, text=text)
        values.update(changes)
        return await self.command('save_review_draft', actor='a', **values)

    async def confirm(self, run, items, **changes):
        attempt = self.current(run)
        values = dict(run_id=run['id'], job_id='j', attempt_id=attempt['id'],
                      result_revision=attempt['number'], expected_revision=run['revision'],
                      items=items, reason='Synthetic human review')
        values.update(changes)
        return await self.command('confirm_list', actor='a', **values)

    def rows(self, *tables):
        with self.service._db() as db:
            return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)] for table in tables}

    def make_v1(self):
        with self.service._db(write=True) as db:
            db.execute('DROP TABLE work_review_revisions')
            db.execute('UPDATE work_schema SET version=1')

    async def test_schema1_upgrade_preserves_versions_runs_attempts_and_legacy_data(self):
        run = await self.prepared()
        tables = ('catalog', 'cases', 'work_definitions', 'work_versions', 'work_runs', 'work_attempts', 'work_decisions')
        before = self.rows(*tables)
        self.make_v1()
        self.service = self.new_service()
        self.assertEqual(self.rows(*tables), before)
        self.assertEqual(self.rows('work_schema')['work_schema'], [(1, 2)])
        self.assertEqual(self.rows('work_review_revisions')['work_review_revisions'], [])
        self.assertEqual(self.rows('work_runs')['work_runs'][0][0], run['id'])

    async def test_schema1_concurrent_initialization_serializes_and_preserves_data(self):
        await self.prepared()
        before = self.rows('work_versions', 'work_runs', 'work_attempts')
        self.make_v1()
        first, second = await asyncio.gather(asyncio.to_thread(self.new_service), asyncio.to_thread(self.new_service))
        self.assertEqual(first.database, second.database)
        self.assertEqual(self.rows('work_schema')['work_schema'], [(1, 2)])
        self.assertEqual(self.rows(*before), before)

    async def test_schema_upgrade_exception_rolls_back_marker_and_table_creation(self):
        await self.prepared()
        before = self.rows('work_runs', 'work_attempts')
        self.make_v1()
        original = workspace.WorkspaceMixin._init_workspace
        def broken(service, db):
            original(service, db)
            raise sqlite3.OperationalError('synthetic failure after schema writes')
        with patch.object(workspace.WorkspaceMixin, '_init_workspace', broken):
            with self.assertRaises(sqlite3.OperationalError):
                self.new_service()
        self.assertEqual(self.rows('work_schema')['work_schema'], [(1, 1)])
        with self.service._db() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='work_review_revisions'").fetchone())
        self.assertEqual(self.rows(*before), before)

    async def test_schema_missing_or_malformed_review_table_is_not_silently_repaired(self):
        shapes = [None, 'attempt_id TEXT',
                  'attempt_id TEXT NOT NULL, revision INTEGER NOT NULL, text TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL, decision_id TEXT UNIQUE',
                  'attempt_id TEXT NOT NULL, revision INTEGER NOT NULL, text TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL, decision_id TEXT, PRIMARY KEY(attempt_id,revision)']
        for version in (1, 2):
            for shape in shapes:
                if version == 1 and shape is None:
                    continue  # This is the supported additive migration.
                with self.subTest(version=version, shape=shape):
                    with self.service._db(write=True) as db:
                        db.execute('DROP TABLE IF EXISTS work_review_revisions')
                        if shape:
                            db.execute('CREATE TABLE work_review_revisions (' + shape + ')')
                        db.execute('UPDATE work_schema SET version=?', (version,))
                        before = list(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
                    with self.assertRaises(workflow.WorkflowError) as raised:
                        self.new_service()
                    self.assertEqual(raised.exception.code, 'workspace_corrupt')
                    self.assertEqual(self.rows('work_schema')['work_schema'], [(1, version)])
                    with self.service._db() as db:
                        self.assertEqual([tuple(row) for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")], [tuple(row) for row in before])

    async def test_review_autosave_and_confirmation_preserve_original_and_append_only_text(self):
        run = await self.prepared()
        original = self.current(run)
        saved = await self.save_review(run)
        self.assertTrue(saved['ok'], saved)
        run = saved['run']
        self.assertEqual(run['jobs']['j']['review_draft']['revision'], 1)
        confirmed = await self.command('decide', actor='a', run_id=run['id'], job_id='j',
                                       expected_revision=run['revision'], result_revision=1,
                                       review_revision=1, item_id='job', verdict='completed')
        self.assertTrue(confirmed['ok'], confirmed)
        actual = self.current(confirmed['run'])
        self.assertEqual(actual['result'], original['result'])
        self.assertEqual([row['text'] for row in actual['review_history']], ['Reviewed draft', 'Reviewed draft'])
        self.assertEqual(actual['review_history'][-1]['decision_id'], confirmed['run']['jobs']['j']['decisions'][-1]['id'])
        self.assertEqual(confirmed['run']['jobs']['j']['status'], 'completed')
        denied = await self.save_review(confirmed['run'], text='Overwrite', review_revision=2)
        self.assertEqual(denied['error']['code'], 'decision_conflict')
        for operation in ('UPDATE work_review_revisions SET text=\'overwrite\'', 'DELETE FROM work_review_revisions'):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.service._db(write=True) as db:
                    db.execute(operation)

    async def test_review_exact_attempt_run_and_review_cas_are_independent(self):
        run = await self.prepared()
        for changes, code in [({'attempt_id': 'wrong'}, 'result_revision_conflict'),
                              ({'result_revision': 999}, 'result_revision_conflict'),
                              ({'expected_revision': run['revision'] - 1}, 'revision_conflict')]:
            denied = await self.save_review(run, **changes)
            self.assertEqual(denied['error']['code'], code)
        saved = await self.save_review(run)
        self.assertTrue(saved['ok'], saved)
        denied = await self.save_review(saved['run'], review_revision=0)
        self.assertEqual(denied['error']['code'], 'revision_conflict')
        denied = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=saved['revision'], result_revision=1, review_revision=0, verdict='completed')
        self.assertEqual(denied['error']['code'], 'revision_conflict')
        self.assertEqual(len(self.rows('work_review_revisions')['work_review_revisions']), 1)
        self.assertEqual(self.rows('work_decisions')['work_decisions'], [])

    async def test_review_current_access_revocation_redacts_state_export_and_receipt(self):
        run = await self.prepared()
        attempt = self.current(run)
        body = dict(action='save_review_draft', request_id=str(uuid4()), run_id=run['id'], job_id='j', expected_revision=run['revision'], attempt_id=attempt['id'], result_revision=1, review_revision=0, text='Private review text')
        saved = await self.service.workspace_command(self.users['a'], body)
        self.assertTrue(saved['ok'], saved)
        other = (await self.state(actor='b', run_id=run['id']))['run']
        self.assertNotIn('Private review text', json.dumps(other))
        self.assertIsNone(other['attempts'][0]['result'])
        self.bridge.allowed = False
        hidden = await self.state(run_id=run['id'])
        exported = await self.service.workspace_export(self.users['a'], run['id'])
        for value in (hidden, exported):
            self.assertNotIn('Private review text', json.dumps(value))
            self.assertNotIn('Original AI draft', json.dumps(value))
        retry = await self.service.workspace_command(self.users['a'], body)
        self.assertEqual(retry['error']['code'], 'native_access_denied')
        self.assertNotIn('Private review text', json.dumps(retry))

    async def test_stale_inputs_cannot_be_repackaged_as_review_or_list_amendment(self):
        for mode, block in (('ai', 'ai_review'), ('tool', 'list_confirm')):
            with self.subTest(block=block):
                run = await self.prepared(mode=mode, block=block, fields=[{'id': 'q', 'type': 'text'}], result={'items': [{'id': 'one'}], 'text': 'Initial'})
                saved = await self.command('save_inputs', actor='a', run_id=run['id'], expected_revision=run['revision'], inputs={'q': 'new'})
                self.assertTrue(saved['ok'], saved)
                if block == 'ai_review':
                    denied = await self.save_review(saved['run'])
                else:
                    denied = await self.command('amend_items', actor='a', run_id=run['id'], job_id='j', expected_revision=saved['revision'], result_revision=1, items=[{'id': 'one'}], reason='Cannot bless old evidence')
                self.assertEqual(denied['error']['code'], 'stale_result')
                self.assertEqual(len(saved['run']['attempts']), 1)

    async def test_confirm_list_changes_are_new_evidence_and_all_decisions_are_exact(self):
        run = await self.prepared(mode='tool', block='list_confirm', result={'items': [{'id': 'one', 'title': 'One'}, {'id': 'two', 'title': 'Two'}]})
        original = deepcopy(self.current(run))
        result = await self.confirm(run, [{'id': 'one', 'selected': False}, {'id': 'two', 'selected': True}, {'id': 'added', 'title': 'Human item', 'selected': True}])
        self.assertTrue(result['ok'], result)
        actual = self.current(result['run'])
        self.assertNotEqual(actual['id'], original['id'])
        self.assertEqual(result['run']['attempts'][0]['result'], original['result'])
        self.assertEqual(actual['result']['amendment']['previous_attempt'], original['id'])
        self.assertEqual(actual['result']['items'][-1]['source']['kind'], 'human_added')
        for field in ('source_references', 'model', 'skills'):
            self.assertEqual(actual['snapshot'][field], original['snapshot'][field])
        decisions = result['run']['jobs']['j']['decisions']
        self.assertEqual({item['item_id'] for item in decisions}, {'two', 'added'})
        self.assertEqual({item['attempt_id'] for item in decisions}, {actual['id']})
        self.assertEqual(result['run']['jobs']['j']['status'], 'completed')

    async def test_unchanged_list_confirmation_does_not_invent_another_attempt(self):
        items = [{'id': 'one'}, {'id': 'two'}]
        run = await self.prepared(mode='tool', block='list_confirm', result={'items': items})
        result = await self.confirm(run, items, reason='')
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['run']['attempts']), 1)
        self.assertEqual({row['attempt_id'] for row in result['run']['jobs']['j']['decisions']}, {self.current(run)['id']})

    async def test_confirm_list_second_decision_failure_rolls_back_all_writes(self):
        run = await self.prepared(mode='tool', block='list_confirm', result={'items': [{'id': 'one'}]})
        tables = ('work_runs', 'work_jobs', 'work_attempts', 'work_decisions', 'work_receipts', 'work_audit')
        before = self.rows(*tables)
        with self.service._db(write=True) as db:
            db.execute("CREATE TRIGGER fail_second_decision BEFORE INSERT ON work_decisions WHEN NEW.item_id='second' BEGIN SELECT RAISE(ABORT,'synthetic second decision failure'); END")
        result = await self.confirm(run, [{'id': 'one'}, {'id': 'second'}])
        self.assertEqual(result['error']['code'], 'invalid_command')
        self.assertEqual(self.rows(*tables), before)
        with self.service._db(write=True) as db:
            db.execute('DROP TRIGGER fail_second_decision')
        valid = await self.confirm(run, [{'id': 'one'}, {'id': 'second'}])
        self.assertTrue(valid['ok'], valid)
        self.assertEqual(len(valid['run']['jobs']['j']['decisions']), 2)

    async def test_invalid_or_stale_list_cannot_partially_write(self):
        run = await self.prepared(mode='tool', block='list_confirm', result={'items': [{'id': 'one'}]})
        before = self.rows('work_runs', 'work_attempts', 'work_decisions')
        for items, extra, code in [([{'id': 'one'}, {'id': 'one'}], {}, 'invalid_amendment'),
                                   ([{'id': 'one', 'selected': 'yes'}], {}, 'invalid_amendment'),
                                   ([{'id': 'one'}, {'id': 'new'}], {'reason': ''}, 'reason_required'),
                                   ([{'id': 'one'}], {'attempt_id': 'wrong'}, 'result_revision_conflict'),
                                   ([{'id': 'one'}], {'expected_revision': run['revision'] - 1}, 'revision_conflict')]:
            result = await self.confirm(run, items, **extra)
            self.assertEqual(result['error']['code'], code, result)
            self.assertEqual(self.rows(*before), before)

    async def test_partial_list_never_becomes_completed_or_closes_run(self):
        run = await self.prepared(mode='tool', block='list_confirm', result={'items': [{'id': 'one'}]}, status='partial')
        result = await self.confirm(run, [{'id': 'one'}, {'id': 'added'}])
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['run']['jobs']['j']['status'], 'partial')
        self.assertEqual(self.current(result['run'])['status'], 'partial')
        denied = await self.command('close_run', actor='a', run_id=run['id'], expected_revision=result['revision'])
        self.assertEqual(denied['error']['code'], 'completion_required')

    async def test_empty_and_fully_excluded_lists_cannot_bypass_completion_policy(self):
        for original, items in (([], []), ([{'id': 'one'}], [{'id': 'one', 'selected': False, 'required': False}])):
            run = await self.prepared(mode='tool', block='list_confirm', result={'items': original})
            denied = await self.confirm(run, items)
            self.assertEqual(denied['error']['code'], 'zero_selection_policy_required')
            saved = await self.command('amend_items', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'], result_revision=1, items=items, reason='Selection can be stored before policy decision')
            self.assertTrue(saved['ok'], saved)
            denied = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=saved['revision'], result_revision=2, item_id='job', verdict='completed')
            self.assertEqual(denied['error']['code'], 'zero_selection_policy_required')
            self.assertEqual((await self.state(run_id=run['id']))['run']['jobs']['j']['decisions'], [])

    async def test_explicit_delivery_preserves_review_but_blocks_all_successor_policies(self):
        def delivery(definition):
            definition['nodes']['j']['completion'] = {'kind': 'delivery'}
            definition['nodes']['next'].update(mode='ai', result_block='ai_review', dependency_policy='all_resolved')
        run = await self.prepared(change=delivery, dependent=True)
        saved = await self.save_review(run)
        self.assertTrue(saved['ok'], saved)
        result = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=saved['revision'], result_revision=1, review_revision=1, verdict='completed')
        self.assertTrue(result['ok'], result)
        run = result['run']
        self.assertEqual((run['jobs']['j']['status'], run['jobs']['j']['reason']), ('blocked', 'delivery_unconfigured'))
        self.assertEqual(self.current(run)['review_history'][-1]['text'], 'Reviewed draft')
        self.assertTrue(self.current(run)['review_history'][-1]['decision_id'])
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.assertRaises(workflow.WorkflowError) as raised:
            with self.service._db(write=True) as db:
                self.service._work_begin_attempt(db, actor, groups, run['id'], 'next', run['revision'])
        self.assertEqual(raised.exception.code, 'prerequisite_required')
        denied = await self.command('close_run', actor='a', run_id=run['id'], expected_revision=run['revision'])
        self.assertEqual(denied['error']['code'], 'completion_required')

    async def test_completion_and_read_retry_validation_retains_incomplete_draft(self):
        key, definition, revision = await self.create(mode='tool', block='list_confirm')
        definition['nodes']['j']['tool_reference']['function'] = 'get_page'
        definition['nodes']['j']['read_retry'] = {'count': 2, 'deadline_seconds': 30}
        self.assertFalse(workspace.definition_check(definition)[0])
        for policy in ({'count': True, 'deadline_seconds': 30}, {'count': 4, 'deadline_seconds': 30}, {'count': 1, 'deadline_seconds': 0}, {'count': 1, 'deadline_seconds': 301}, {'count': 1}, []):
            changed = deepcopy(definition); changed['nodes']['j']['read_retry'] = policy
            self.assertTrue(workspace.definition_check(changed)[0])
        changed = deepcopy(definition); changed['nodes']['j']['completion'] = {'kind': 'delivery'}
        self.assertTrue(workspace.definition_check(changed)[0])
        changed['nodes']['j']['completion'] = {'kind': 'invented'}
        self.assertTrue(workspace.definition_check(changed)[0])
        definition['nodes']['j']['read_retry'] = {'count': 2}
        saved = await self.command('save_draft', workflow_id=key, definition=definition, expected_revision=revision)
        self.assertTrue(saved['ok'], saved)
        checked = await self.command('validate_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.assertTrue(checked['validation']['errors'])
        denied = await self.command('publish_workflow', workflow_id=key, expected_revision=saved['revision'])
        self.assertFalse(denied['ok'])

    async def test_request_capabilities_follow_current_distinct_roles(self):
        run = await self.prepared(mode='human', block='human_confirm')
        job = run['jobs']['j']
        self.assertTrue(job['can_execute']); self.assertTrue(job['can_decide'])
        self.assertFalse(job['can_request']); self.assertFalse(job['can_review_request']); self.assertFalse(job['can_reconcile'])
        with self.service._db() as db:
            grant = db.execute("SELECT id,revision FROM work_access WHERE principal_id='a' AND system_id='EMS'").fetchone()
        result = await self.command('save_access', access_id=grant['id'], principal_kind='user', principal_id='a', system_id='EMS', factory_id='*', roles=['participant', 'reviewer'], expected_revision=grant['revision'])
        self.assertTrue(result['ok'], result)
        job = (await self.state(run_id=run['id']))['run']['jobs']['j']
        self.assertTrue(job['can_review_request']); self.assertFalse(job['can_request']); self.assertFalse(job['can_reconcile'])

    async def test_item_verdict_confirmation_is_complete_atomic_and_partial_stays_partial(self):
        for status in ('succeeded', 'partial'):
            with self.subTest(status=status):
                run = await self.prepared(block='item_verdict', status=status, result={'completeness': 'partial' if status == 'partial' else 'complete', 'items': [{'id': 'cr1'}, {'id': 'cr2'}]})
                attempt = self.current(run)
                body = {'run_id': run['id'], 'job_id': 'j', 'attempt_id': attempt['id'], 'expected_revision': run['revision'], 'result_revision': attempt['number']}
                choices = [{'item_id': key, 'verdict': 'completed'} for key in ('cr1', 'cr2')]
                for incomplete in (choices[:1], [choices[0], choices[0]], [choices[0], {'item_id': 'foreign', 'verdict': 'completed'}]):
                    rejected = await self.command('confirm_verdicts', actor='a', **body, verdicts=incomplete)
                    self.assertEqual(rejected['error']['code'], 'verdict_selection_required')
                    self.assertEqual((await self.state(run_id=run['id']))['run']['jobs']['j']['decisions'], [])
                confirmed = await self.command('confirm_verdicts', actor='a', **body, verdicts=choices)
                self.assertTrue(confirmed['ok'], confirmed)
                self.assertEqual(confirmed['run']['jobs']['j']['status'], 'partial' if status == 'partial' else 'completed')
                self.assertEqual(len(confirmed['run']['jobs']['j']['decisions']), 2)
                repeated = await self.command('confirm_verdicts', actor='a', **{**body, 'expected_revision': confirmed['revision']}, verdicts=choices)
                self.assertEqual(repeated['error']['code'], 'decision_conflict')

    async def test_item_verdict_confirmation_rolls_back_on_revoked_source(self):
        run = await self.prepared(block='item_verdict', result={'items': [{'id': 'cr1'}, {'id': 'cr2'}]})
        attempt = self.current(run); self.bridge.allowed = False
        result = await self.command('confirm_verdicts', actor='a', run_id=run['id'], job_id='j', attempt_id=attempt['id'], expected_revision=run['revision'], result_revision=attempt['number'], verdicts=[{'item_id': key, 'verdict': 'completed'} for key in ('cr1', 'cr2')])
        self.assertEqual(result['error']['code'], 'native_access_denied')
        with self.service._db() as db: self.assertEqual(db.execute('SELECT count(*) FROM work_decisions WHERE attempt_id=?', (attempt['id'],)).fetchone()[0], 0)

    async def test_item_verdict_batch_completes_legacy_partial_decisions_without_overwriting(self):
        run = await self.prepared(block='item_verdict', result={'items': [{'id': 'cr1'}, {'id': 'cr2'}, {'id': 'optional', 'required': False}]})
        attempt = self.current(run)
        first = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'], result_revision=attempt['number'], item_id='cr1', verdict='completed', note='기존 개별 확정')
        self.assertTrue(first['ok'], first)
        original = deepcopy(first['run']['jobs']['j']['decisions'][0])
        body = {'run_id': run['id'], 'job_id': 'j', 'attempt_id': attempt['id'], 'expected_revision': first['revision'], 'result_revision': attempt['number']}
        changed = await self.command('confirm_verdicts', actor='a', **body, verdicts=[{'item_id': 'cr1', 'verdict': 'failed'}, {'item_id': 'cr2', 'verdict': 'completed'}, {'item_id': 'optional', 'verdict': 'failed'}])
        self.assertEqual(changed['error']['code'], 'decision_conflict')
        self.assertEqual((await self.state(run_id=run['id']))['run']['jobs']['j']['decisions'], [original])
        finished = await self.command('confirm_verdicts', actor='a', **body, verdicts=[{'item_id': 'cr1', 'verdict': 'completed'}, {'item_id': 'cr2', 'verdict': 'completed'}, {'item_id': 'optional', 'verdict': 'failed'}])
        self.assertTrue(finished['ok'], finished)
        self.assertEqual(finished['run']['jobs']['j']['status'], 'completed')
        self.assertIn(original, finished['run']['jobs']['j']['decisions'])
        self.assertEqual(len(finished['run']['jobs']['j']['decisions']), 3)

    async def test_completed_legacy_optional_item_remains_final_after_upgrade(self):
        run = await self.prepared(block='item_verdict', result={'items': [{'id': 'required'}, {'id': 'optional', 'required': False}]})
        attempt = self.current(run)
        first = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=run['revision'], result_revision=attempt['number'], item_id='required', verdict='completed')
        self.assertEqual(first['run']['jobs']['j']['status'], 'completed')
        original = deepcopy(first['run']['jobs']['j']['decisions'])
        blocked = await self.command('confirm_verdicts', actor='a', run_id=run['id'], job_id='j', attempt_id=attempt['id'], expected_revision=first['revision'], result_revision=attempt['number'], verdicts=[{'item_id': 'optional', 'verdict': 'failed'}])
        self.assertEqual(blocked['error']['code'], 'decision_conflict')
        direct = await self.command('decide', actor='a', run_id=run['id'], job_id='j', expected_revision=first['revision'], result_revision=attempt['number'], item_id='optional', verdict='failed')
        self.assertEqual(direct['error']['code'], 'decision_conflict')
        current = (await self.state(run_id=run['id']))['run']
        self.assertEqual(current['jobs']['j']['status'], 'completed'); self.assertEqual(current['jobs']['j']['decisions'], original)

    async def test_custom_judgment_id_preserves_exact_same_status_term_in_immutable_note(self):
        def labels(definition):
            definition['nodes']['j']['judgments'] = [
                {'id': 'approved', 'label': '승인', 'status': 'completed', 'consequence': '검토 완료'},
                {'id': 'conditional', 'label': '조건부 승인', 'status': 'completed', 'consequence': '조건을 함께 기록'}]
        run = await self.prepared(block='item_verdict', change=labels, result={'items': [{'id': 'cr1'}]})
        attempt = self.current(run)
        body = {'run_id': run['id'], 'job_id': 'j', 'attempt_id': attempt['id'], 'expected_revision': run['revision'], 'result_revision': attempt['number']}
        rejected = await self.command('confirm_verdicts', actor='a', **body, verdicts=[{'item_id': 'cr1', 'verdict': 'failed', 'judgment_id': 'conditional'}])
        self.assertEqual(rejected['error']['code'], 'invalid_judgment')
        confirmed = await self.command('confirm_verdicts', actor='a', **body, verdicts=[{'item_id': 'cr1', 'verdict': 'completed', 'judgment_id': 'conditional', 'note': '점검 조건을 확인함'}])
        self.assertTrue(confirmed['ok'], confirmed)
        decision = confirmed['run']['jobs']['j']['decisions'][0]
        self.assertEqual(decision['note'], '점검 조건을 확인함\n선택한 판정: 조건부 승인 (conditional)')
        self.assertEqual(decision['verdict'], 'completed')
        self.assertEqual(confirmed['run']['definition']['nodes']['j']['judgments'][1]['consequence'], '조건을 함께 기록')

    async def test_tool_item_verdict_always_waits_for_explicit_human_confirmation(self):
        key, definition, revision = await self.create(mode='tool', block='item_verdict')
        definition['nodes']['j']['human_confirmation'] = False
        self.assertTrue(workspace.definition_check(definition)[0])
        run = await self.start(key, revision=revision)
        # Previously published flags remain readable, but cannot cause a new
        # tool result to become a human final decision without a command.
        with self.service._db(write=True) as db:
            snapshot = json.loads(db.execute('SELECT snapshot FROM work_runs WHERE id=?', (run['id'],)).fetchone()[0])
            snapshot['definition']['nodes']['j']['human_confirmation'] = False
            db.execute('UPDATE work_runs SET snapshot=? WHERE id=?', (json.dumps(snapshot), run['id']))
        actor, _, groups = await self.service._work_actor(self.users['a'])
        with self.service._db(write=True) as db:
            attempt = self.service._work_begin_attempt(db, actor, groups, run['id'], 'j', run['revision'])
            result = self.service._work_finish_attempt(db, attempt['id'], 'succeeded', {'items': [{'id': 'cr1'}], 'completeness': 'complete'})
            self.assertEqual(result['status'], 'waiting_confirmation')
            self.assertEqual(db.execute('SELECT count(*) FROM work_decisions WHERE attempt_id=?', (attempt['id'],)).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
