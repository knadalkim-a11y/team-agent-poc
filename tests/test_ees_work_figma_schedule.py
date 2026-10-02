"""Reconstructed after workspace loss from the frozen product contracts.

These are new semantic tests, not a claim to restore the unavailable original
test bytes/count. SQLite and public commands are real; Native IDs, clocks and
external transport observations are explicitly synthetic.
"""
import asyncio
from copy import deepcopy
import importlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_ees_work_operations as fixture

ops, workflow = fixture.ops, fixture.workflow
native = importlib.import_module(fixture.package.__name__ + '.ees_workflow_native')


class ScheduleContracts(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.RuntimeTests.asyncSetUp
    body = fixture.RuntimeTests.body
    core = fixture.RuntimeTests.core
    make_contract = fixture.RuntimeTests.make_contract
    make_workflow = fixture.RuntimeTests.make_workflow
    start = fixture.RuntimeTests.start
    prepare = fixture.RuntimeTests.prepare
    approve = fixture.RuntimeTests.approve
    intent = fixture.RuntimeTests.intent

    def rule(self, **change):
        return {'frequency': 'daily', 'interval': 1, 'timezone': 'UTC',
                'anchor': '2026-10-02T10:00:00', 'name_template': '{date} 회차',
                'opening': 'after_previous_closed', 'closing': 'after_last_stage',
                'non_working_days': 'notify_no_shift', 'catch_up': 'miss',
                'stage_deadlines': {'t1': {'offset_days': -1, 'end_offset_days': 1}}, **change}

    async def published(self, *, periodic=True, mode='human', retry=None, rule=None):
        created = await self.core('create_workflow', system_id='EMS', name='재구성 계약 검증', mode='periodic' if periodic else 'on_demand')
        wid, definition = created['workflow_id'], created['workflow']['draft']
        root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['t1']
        definition['nodes']['t1'] = {'id': 't1', 'type': 't', 'name': '단계', 'parent': root, 'children': ['j1'], 'deps': []}
        job = {'id': 'j1', 'type': 'j', 'name': '작업', 'parent': 't1', 'children': [], 'deps': [], 'mode': mode,
               'inputs': [{'id': 'target', 'type': 'text', 'scope': 'run', 'required': True}],
               'result_block': 'human_confirm', 'human_confirmation': True}
        if mode == 'tool':
            job.update(tool_reference=deepcopy(fixture.REF), argument_bindings={'target': {'input': 'target'}})
        if retry is not None:
            job['read_retry'] = deepcopy(retry)
        definition['nodes']['j1'] = job
        if periodic:
            definition['schedule'] = deepcopy(rule or self.rule())
        await self.core('save_draft', 1, workflow_id=wid, definition=definition)
        checked = await self.core('validate_workflow', 2, workflow_id=wid)
        self.assertEqual(checked['validation']['errors'], [])
        await self.core('publish_workflow', 2, workflow_id=wid)
        return wid, definition

    async def reserve(self, wid, definition, **change):
        schedule = {'workflow_id': wid, 'version': 1, 'rule': deepcopy(definition['schedule']),
                    'delegated': True, 'lifecycle_enabled': True, 'inputs': {'target': 'synthetic-target'},
                    'sharing': {'group_ids': ['team']}, 'job_ids': [], **change}
        result = await self.runtime.command(self.user, self.body('schedule_save', schedule=schedule))
        return result['schedule']

    async def state(self, run_id):
        result = await self.service.workspace_state(self.user, run_id=run_id)
        self.assertTrue(result['ok'], result)
        return result['run']

    def slots(self):
        with self.service._db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM work_schedule_slots ORDER BY scheduled_at,id')]

    async def test_preview_is_unsaved_authorized_and_never_reserves_or_shifts_holidays(self):
        wid, definition = await self.published()
        draft = deepcopy(definition); draft['schedule']['interval'] = 2
        result = await self.runtime.command(self.user, self.body('schedule_preview', workflow_id=wid, definition=draft, after='2026-10-02T09:59:00+00:00'))
        self.assertEqual([item['date'] for item in result['preview']], ['2026-10-02', '2026-10-04'])
        self.assertEqual(result['preview'][0]['stage_deadlines']['t1'], {'start': '2026-10-01', 'end': '2026-10-03'})
        self.assertFalse(result['preview'][0]['holidays_checked'])
        self.assertIn('stage_deadline_weekend', [item['code'] for item in result['preview'][0]['warnings']])
        self.assertFalse(result['activation']['reservation_created'])
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM work_schedules').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM work_runs').fetchone()[0], 0)
            self.assertEqual(json.loads(db.execute('SELECT draft FROM work_definitions WHERE id=?', (wid,)).fetchone()[0]), definition)
        self.users['alice']['role'] = 'user'
        with self.assertRaises(workflow.WorkflowError):
            await self.runtime.command(self.user, self.body('schedule_preview', workflow_id=wid, definition=draft))

    async def test_lifecycle_requires_exact_published_rule_and_explicit_delegation(self):
        wid, definition = await self.published()
        for change in ({'delegated': False}, {'rule': self.rule(interval=2)}, {'lifecycle_enabled': 'yes'}):
            with self.subTest(change=change), self.assertRaises(workflow.WorkflowError) as error:
                await self.reserve(wid, definition, **change)
            self.assertEqual(error.exception.code, 'schedule_lifecycle_invalid')
        self.assertEqual(self.slots(), [])
        schedule = await self.reserve(wid, definition, delegated=False, lifecycle_enabled=False)
        self.assertFalse(schedule['lifecycle_enabled'])
        await self.runtime.process_once()
        self.assertEqual(self.slots()[0]['reason'], 'schedule_delegation_required')
        self.assertEqual(self.bridge.calls, [])

    async def test_saved_cycle_keeps_version_rule_and_dates_after_new_publication(self):
        wid, definition = await self.published()
        schedule = await self.reserve(wid, definition)
        self.runtime._materialize()
        newer = deepcopy(definition); newer['name'] = '후속 게시 이름'; newer['schedule']['interval'] = 3
        await self.core('save_draft', 3, workflow_id=wid, definition=newer)
        await self.core('validate_workflow', 4, workflow_id=wid)
        await self.core('publish_workflow', 4, workflow_id=wid)
        await self.runtime.process_once()
        run = await self.state(self.slots()[0]['run_id'])
        self.assertEqual(run['version'], 1); self.assertEqual(run['definition']['name'], definition['name'])
        self.assertEqual(run['cycle']['rule'], schedule['rule']); self.assertEqual(run['cycle']['date'], '2026-10-02')
        self.assertEqual(run['cycle']['stage_deadlines']['t1']['end'], '2026-10-03')
        restarted = ops.OperationsRuntime(self.service, bridge=self.bridge, clock=lambda: self.now)
        await restarted.process_once()
        self.assertEqual((await self.state(run['id']))['cycle'], run['cycle'])
        self.assertEqual(len(self.slots()), 1)

    async def test_completed_predecessor_opens_next_cycle_early_only_after_human_confirmation(self):
        wid, definition = await self.published()
        await self.reserve(wid, definition)
        await self.runtime.process_once(); first = await self.state(self.slots()[0]['run_id'])
        await self.runtime.process_once()
        self.assertEqual(len(self.slots()), 1); self.assertEqual((await self.state(first['id']))['status'], 'open')
        await self.core('human_confirm', first['revision'], run_id=first['id'], job_id='j1')
        await self.runtime.process_once()
        self.assertEqual((await self.state(first['id']))['status'], 'completed')
        self.assertEqual(len(self.slots()), 2)
        second = await self.state(self.slots()[-1]['run_id'])
        self.assertGreater(self.slots()[-1]['scheduled_at'], self.now)
        self.assertEqual(second['cycle']['date'], '2026-10-03'); self.assertEqual(second['status'], 'open')
        self.assertEqual(second['attempts'], []); self.assertEqual(self.bridge.calls, [])

    async def test_queued_slot_rechecks_current_native_identity_and_delegation(self):
        wid, definition = await self.published()
        schedule = await self.reserve(wid, definition)
        self.runtime._materialize(); self.users['alice']['role'] = 'pending'
        await self.runtime.process_once()
        self.assertEqual(self.slots()[0]['state'], 'blocked'); self.assertIsNone(self.slots()[0]['run_id'])
        self.users['alice']['role'] = 'admin'
        wid2, definition2 = await self.published()
        schedule2 = await self.reserve(wid2, definition2)
        self.runtime._materialize()
        await self.runtime.command(self.user, self.body('schedule_save', schedule2['revision'], schedule={**schedule2, 'delegated': False, 'lifecycle_enabled': False}))
        await self.runtime.process_once()
        blocked = next(item for item in self.slots() if item['schedule_id'] == schedule2['id'])
        self.assertEqual(blocked['reason'], 'schedule_delegation_revoked'); self.assertIsNone(blocked['run_id'])
        self.assertEqual(self.bridge.calls, [])

    def clone_queue_head(self, schedule, slot, count, *, revoked=False):
        # Arrange an adversarial queue in this test's temporary DB. Each copied
        # row derives from a real reservation/run; no successful human outcome
        # is fabricated for the actual eligible tail run under test.
        with self.service._db(write=True) as db:
            for index in range(count):
                sid = 'blocked-schedule-' + str(index); scope = 'fixture-scope-' + str(index)
                data = deepcopy(schedule); data.update(id=sid, scope=scope, next_at=self.now-1000)
                if revoked: data['identity_user_id'] = 'revoked'
                db.execute('INSERT INTO work_schedules VALUES(?,?,?,?,?,?,?,?)', (sid, data['workflow_id'], scope, data['identity_user_id'], data['revision'], 1, data['next_at'], ops.dump(data)))
                prior = deepcopy(slot); prior.update(id='blocked-slot-' + str(index), schedule_id=sid, schedule=data, scheduled_at=self.now-1000+index)
                db.execute('INSERT INTO work_schedule_slots VALUES(?,?,?,?,?,?,NULL,NULL,?)', (prior['id'], sid, data['workflow_id'], scope, prior['scheduled_at'], prior['state'], ops.dump(prior)))

    async def test_open_cycle_queue_heads_do_not_starve_independent_due_reservation(self):
        wid, definition = await self.published()
        schedule = await self.reserve(wid, definition)
        await self.runtime.process_once(); slot = self.slots()[0]
        self.clone_queue_head(schedule, slot, 100)
        other, other_definition = await self.published()
        independent = await self.reserve(other, other_definition, lifecycle_enabled=False)
        self.assertEqual(self.runtime._materialize(), 1)
        self.assertEqual(sum(item['schedule_id'] == independent['id'] for item in self.slots()), 1)

    async def test_close_scanner_advances_past_100_revoked_native_identities(self):
        wid, definition = await self.published()
        schedule = await self.reserve(wid, definition)
        await self.runtime.process_once(); slot = self.slots()[0]; run = await self.state(slot['run_id'])
        await self.core('human_confirm', run['revision'], run_id=run['id'], job_id='j1')
        self.users['revoked'] = {'id': 'revoked', 'role': 'pending'}
        self.clone_queue_head(schedule, slot, 100, revoked=True)
        await self.runtime._close_cycles()
        self.assertEqual((await self.state(run['id']))['status'], 'open')
        await self.runtime._close_cycles()
        self.assertEqual((await self.state(run['id']))['status'], 'completed')

    def confirmed_failure(self, *, trusted=True, code='upstream_error'):
        return native.normalize_result('jira_dashboard', {'ok': False, 'failure_confirmed': True, 'error': {'code': code}}, fixture.REF, {}, trusted_read=trusted)

    async def retry_run(self, policy=None):
        wid, _ = await self.published(periodic=False, mode='tool', retry=policy)
        started = await self.start(wid)
        return started['run_id'], self.body('execute_job', started['revision'], run_id=started['run_id'], job_id='j1')

    async def test_retry_is_explicit_bounded_and_lost_response_receipt_never_restarts_budget(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 30})
        self.bridge.result = self.confirmed_failure()
        outcome = await self.runtime.command(self.user, body)
        run = await self.state(run_id)
        self.assertEqual([item['number'] for item in run['attempts']], [1, 2, 3, 4])
        self.assertEqual([item['status'] for item in run['attempts']], ['failed']*4)
        self.assertEqual(len(self.bridge.calls), 4)
        repeated = await self.runtime.command(self.user, body)
        self.assertEqual(repeated['attempt']['id'], outcome['attempt']['id']); self.assertEqual(len(self.bridge.calls), 4)
        self.assertEqual((await self.state(run_id))['attempts'], run['attempts'])
        for policy in (None, {'count': 0, 'deadline_seconds': 1}):
            run_id, body = await self.retry_run(policy)
            before = len(self.bridge.calls)
            await self.runtime.command(self.user, body)
            self.assertEqual(len(self.bridge.calls)-before, 1)
            self.assertEqual(len((await self.state(run_id))['attempts']), 1)

    async def test_retry_success_retains_failed_evidence_and_waits_for_human(self):
        run_id, body = await self.retry_run({'count': 1, 'deadline_seconds': 30})
        failure = self.confirmed_failure(); original = self.bridge.invoke
        async def invoke(*args):
            self.bridge.result = failure if not self.bridge.calls else {'status': 'succeeded', 'completeness': 'complete', 'data': {'count': 1}}
            return await original(*args)
        self.bridge.invoke = invoke
        result = await self.runtime.command(self.user, body); run = await self.state(run_id)
        self.assertTrue(result['ok']); self.assertEqual([a['status'] for a in run['attempts']], ['failed', 'succeeded'])
        self.assertEqual(run['attempts'][0]['result'], failure)
        self.assertEqual(run['jobs']['j1']['status'], 'waiting_confirmation'); self.assertEqual(run['jobs']['j1']['decisions'], [])

    async def test_unknown_partial_auth_rate_limit_and_untrusted_flags_never_retry(self):
        observations = [('unknown', {'status': 'unknown', 'transport': 'unknown'}),
                        ('partial', {'status': 'succeeded', 'completeness': 'partial'}),
                        ('untrusted', self.confirmed_failure(trusted=False)),
                        ('auth', self.confirmed_failure(code='authentication_failed')),
                        ('rate_limit', self.confirmed_failure(code='rate_limited'))]
        for label, result in observations:
            with self.subTest(label=label):
                run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 30})
                self.bridge.result = result; before = len(self.bridge.calls)
                await self.runtime.command(self.user, body)
                self.assertEqual(len(self.bridge.calls)-before, 1)
                self.assertEqual(len((await self.state(run_id))['attempts']), 1)

    def test_retry_schema_limits_and_read_only_function_allowlist(self):
        job = {'mode': 'tool', 'tool_reference': deepcopy(fixture.REF), 'read_retry': {'count': 3, 'deadline_seconds': 300}}
        self.assertEqual(ops.validate_read_retry(job), job['read_retry'])
        for policy in ({'count': -1, 'deadline_seconds': 1}, {'count': 4, 'deadline_seconds': 1}, {'count': True, 'deadline_seconds': 1}, {'count': 1, 'deadline_seconds': 0}, {'count': 1, 'deadline_seconds': 301}, {'count': 1, 'deadline_seconds': True}, {'count': 1}):
            with self.subTest(policy=policy), self.assertRaises(workflow.WorkflowError):
                ops.validate_read_retry({**job, 'read_retry': policy})
        for change in ({'mode': 'ai'}, {'result_block': 'change_request'}, {'tool_reference': {'function': 'unreviewed_write'}}):
            with self.subTest(change=change), self.assertRaises(workflow.WorkflowError):
                ops.validate_read_retry({**job, **change})

    async def test_monotonic_deadline_ends_retry_chain_without_wall_clock_extension(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 1})
        monotonic = [10.0]; original = self.bridge.invoke; self.bridge.result = self.confirmed_failure()
        async def invoke(*args):
            result = await original(*args); monotonic[0] = 11.1; self.now -= 86400
            return result
        self.bridge.invoke = invoke
        with patch.object(ops, 'time', SimpleNamespace(monotonic=lambda: monotonic[0])):
            await self.runtime.command(self.user, body)
        self.assertEqual(len(self.bridge.calls), 1); self.assertEqual(len((await self.state(run_id))['attempts']), 1)

    async def test_inflight_timeout_is_unknown_and_cannot_automatically_resend(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 1})
        entered = asyncio.Event(); release = asyncio.Event()
        async def invoke(*args):
            self.bridge.calls.append(args); entered.set(); await release.wait()
            return self.confirmed_failure()
        self.bridge.invoke = invoke
        outcome = await self.runtime.command(self.user, body)
        self.assertTrue(entered.is_set()); self.assertEqual(outcome['attempt']['status'], 'unknown')
        run = await self.state(run_id)
        self.assertEqual([a['status'] for a in run['attempts']], ['unknown'])
        await self.runtime.command(self.user, body)
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_input_change_between_attempts_stops_automatic_retry(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 30})
        self.bridge.result = self.confirmed_failure(); original = self.runtime._execute_once
        async def once(*args, **kwargs):
            result = await original(*args, **kwargs)
            run = await self.state(run_id)
            await self.core('save_inputs', run['revision'], run_id=run_id, inputs={'target': 'human-corrected'})
            return result
        self.runtime._execute_once = once
        await self.runtime.command(self.user, body)
        run = await self.state(run_id)
        self.assertEqual(len(self.bridge.calls), 1); self.assertEqual(len(run['attempts']), 1)
        self.assertEqual(run['inputs']['target'], 'human-corrected'); self.assertEqual(run['attempts'][0]['inputs']['target'], 'synthetic-target')

    async def test_interleaved_human_requested_new_attempt_is_not_retried_or_overwritten(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 30})
        self.bridge.result = self.confirmed_failure(); original = self.runtime._execute_once
        async def once(*args, **kwargs):
            failed = await original(*args, **kwargs)
            run = await self.state(run_id)
            self.bridge.result = {'status': 'succeeded', 'completeness': 'complete'}
            manual = await original(self.user, self.body('execute_job', run['revision'], run_id=run_id, job_id='j1'))
            self.assertTrue(manual['ok']); return failed
        self.runtime._execute_once = once
        await self.runtime.command(self.user, body)
        run = await self.state(run_id)
        self.assertEqual(len(self.bridge.calls), 2); self.assertEqual([a['status'] for a in run['attempts']], ['failed', 'succeeded'])
        self.assertEqual(run['jobs']['j1']['current_attempt'], run['attempts'][1]['id'])
        self.assertEqual(run['jobs']['j1']['status'], 'waiting_confirmation')

    async def test_current_source_revocation_between_retry_attempts_blocks_dispatch(self):
        run_id, body = await self.retry_run({'count': 3, 'deadline_seconds': 30})
        self.bridge.result = self.confirmed_failure(); original = self.runtime._execute_once
        async def once(*args, **kwargs):
            result = await original(*args, **kwargs); self.bridge.allowed = False
            return result
        self.runtime._execute_once = once
        with self.assertRaises(workflow.WorkflowError) as error:
            await self.runtime.command(self.user, body)
        self.assertEqual(error.exception.code, 'native_access_denied'); self.assertEqual(len(self.bridge.calls), 1)
        with self.service._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM work_attempts WHERE run_id=?', (run_id,)).fetchone()[0], 1)

    async def test_negative_effect_evidence_is_terminal_failure_not_unknown_or_later_success(self):
        run, request = await self.prepare(); connector = fixture.Connector(); connector.effect_ok = False
        self.runtime.connector = connector; intent = await self.intent(request)
        dispatched = await self.runtime.command(self.user, self.body('request_dispatch', request['revision'], external_request_id=request['id'], intent_token=intent['intent_token']))
        failed = await self.runtime.command(self.user, self.body('request_reconcile', dispatched['request']['revision'], external_request_id=request['id']))
        self.assertEqual(failed['request']['state'], 'failed'); self.assertEqual(failed['request']['reason'], 'effect_criterion_not_met')
        snapshot = await self.state(run['run_id']); self.assertEqual(snapshot['attempts'][0]['status'], 'failed')
        connector.effect_ok = True
        later = await self.runtime.command(self.user, self.body('request_reconcile', failed['request']['revision'], external_request_id=request['id']))
        self.assertEqual(later['request']['state'], 'failed'); self.assertEqual(len(connector.calls), 1)
        self.assertEqual((await self.state(run['run_id']))['attempts'], snapshot['attempts'])

    async def test_unknown_effect_keeps_unresolved_request_and_never_resends(self):
        run, request = await self.prepare(); connector = fixture.Connector(); self.runtime.connector = connector
        intent = await self.intent(request)
        dispatched = await self.runtime.command(self.user, self.body('request_dispatch', request['revision'], external_request_id=request['id'], intent_token=intent['intent_token']))
        unknown = await self.runtime.command(self.user, self.body('request_reconcile', dispatched['request']['revision'], external_request_id=request['id']))
        self.assertEqual(unknown['request']['state'], 'unknown'); self.assertEqual(unknown['request']['reason'], 'effect_observation_unknown')
        current = await self.state(run['run_id']); self.assertEqual(current['jobs']['j1']['status'], 'unknown')
        closed = await self.service.workspace_command(self.user, self.body('close_run', current['revision'], run_id=run['run_id']))
        self.assertFalse(closed['ok']); self.assertEqual(len(connector.calls), 1)


if __name__ == '__main__':
    unittest.main()
