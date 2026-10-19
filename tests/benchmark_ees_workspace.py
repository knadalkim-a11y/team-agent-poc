#!/usr/bin/env python3
"""Synthetic, read-only workspace benchmark; no Native DB or network is used.

Loads baseline/candidate under separate package names and uses the same temporary
SQLite fixture for each pair. Public authoring creates one procedure and run;
direct fixture-only row duplication scales its pending human jobs. Both versions
must produce exactly equal complete JSON on every measured request. SELECT
counting runs separately from timing so the callback does not favor fewer reads.
"""
import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from types import ModuleType
from uuid import uuid4


FIXED = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)
USERS = {key: {'id': key, 'role': 'admin' if key == 'admin' else 'user'}
         for key in ('admin', 'a', 'b', 'c')}
GROUPS = {'a': ['g'], 'b': ['g']}


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


def load_service(repo, name):
    package = ModuleType(name)
    package.__path__ = [str(repo / 'agent-pack/skills/ees-work-demo/scripts')]
    sys.modules[name] = package
    module = importlib.import_module(name + '.ees_workflow')
    for suffix in ('ees_workflow', 'ees_workflow_workspace', 'ees_workflow_operations'):
        imported = importlib.import_module(name + '.' + suffix)
        if hasattr(imported, 'datetime'):
            imported.datetime = FrozenDatetime
    return module.WorkflowService


def service(cls, database):
    result = cls(database, lambda key: deepcopy(USERS.get(key)), lambda key: None,
                 group_lookup=lambda key: [{'id': item} for item in GROUPS.get(key, [])],
                 group_list_lookup=lambda: [{'id': 'g', 'name': 'Native group'}])
    result.operations.clock = lambda: FIXED.timestamp()
    return result


async def command(instance, action, actor='admin', expected_revision=0, **values):
    result = await instance.workspace_command(USERS[actor], dict(
        action=action, request_id=str(uuid4()), expected_revision=expected_revision, **values))
    assert result['ok'], result
    return result


async def fixture(instance, run_count, job_count):
    # Match the existing WorkspaceTests identity/ACL arrangement.
    for actor in ('a', 'b'):
        await command(instance, 'save_access', principal_kind='user', principal_id=actor,
                      system_id='EMS', factory_id='*', roles=['manager', 'participant'])
    created = await command(instance, 'create_workflow', name='합성 성능 검증 절차', system_id='EMS')
    workflow_id = created['workflow_id']
    definition = created['workflow']['draft']
    root = next(iter(definition['nodes']))
    job_ids = ['j' + str(i) for i in range(job_count)]
    definition['nodes'][root]['children'] = ['t']
    definition['nodes']['t'] = {'id': 't', 'type': 't', 'name': '합성 단계',
                                'parent': root, 'children': job_ids, 'deps': []}
    for job_id in job_ids:
        definition['nodes'][job_id] = {
            'id': job_id, 'type': 'j', 'name': '합성 작업 ' + job_id,
            'parent': 't', 'children': [], 'deps': [], 'mode': 'human',
            'inputs': [], 'result_block': 'human_confirm'}
    await command(instance, 'save_draft', workflow_id=workflow_id, definition=definition, expected_revision=1)
    validated = await command(instance, 'validate_workflow', workflow_id=workflow_id, expected_revision=2)
    assert not validated['validation']['errors'], validated
    published = await command(instance, 'publish_workflow', workflow_id=workflow_id, expected_revision=2)
    first = await command(instance, 'start_run', actor='a', workflow_id=workflow_id,
                          expected_revision=published['revision'])
    first_id = first['run']['id']
    # Duplicate only within this benchmark's TemporaryDirectory SQLite file.
    with instance._db(write=True) as db:
        source = dict(db.execute('SELECT * FROM work_runs WHERE id=?', (first_id,)).fetchone())
        jobs = [dict(row) for row in db.execute('SELECT * FROM work_jobs WHERE run_id=?', (first_id,))]
        for index in range(1, run_count):
            run_id = f'{index:08d}-0000-0000-0000-000000000000'
            row = dict(source, id=run_id)
            db.execute('INSERT INTO work_runs (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            for item in jobs:
                job = dict(item, run_id=run_id)
                db.execute('INSERT INTO work_jobs (' + ','.join(job) + ') VALUES (' + ','.join('?' for _ in job) + ')', tuple(job.values()))
    return dict(system_id='EMS', workflow_id=workflow_id, run_id=first_id)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


async def state(instance, query):
    result = await instance.workspace_state(USERS['a'], **query)
    assert result['ok'], result
    return result


async def measured(instance, query, expected, repeats):
    await state(instance, query)  # warm-up, excluded
    original = instance._db
    selects = []

    @contextmanager
    def counted(write=False):
        with original(write=write) as db:
            db.set_trace_callback(lambda sql: selects.append(sql) if sql.lstrip().upper().startswith('SELECT') else None)
            yield db

    instance._db = counted
    try:
        result = await state(instance, query)
    finally:
        instance._db = original
    assert encoded(result) == expected, 'Traced response differs from exact baseline'
    elapsed = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        result = await state(instance, query)
        elapsed.append((time.perf_counter_ns() - start) / 1_000_000)
        assert encoded(result) == expected, 'Timed response differs from exact baseline'
    return {'selects': len(selects), 'json_bytes': len(expected),
            'median_ms': round(statistics.median(elapsed), 3),
            'samples_ms': [round(value, 3) for value in elapsed]}


async def main(args):
    base = load_service(args.baseline, 'ees_benchmark_baseline')
    changed = load_service(args.candidate, 'ees_benchmark_candidate')
    output = {'python': platform.python_version(), 'baseline': str(args.baseline),
              'candidate': str(args.candidate), 'clock': FIXED.isoformat(),
              'timed_repeats': args.repeats, 'trace_in_timing': False,
              'limits': 'Synthetic pending human jobs, one procedure, no attempts/reviews/deadlines; local SQLite and in-process service only; no network/browser/Native integration.',
              'cases': []}
    for runs, jobs in ((1, 1), (10, 1), (100, 1), (500, 1), (100, 10)):
        with tempfile.TemporaryDirectory(prefix='ees-workspace-benchmark-') as temp:
            database = Path(temp) / 'synthetic-work.sqlite3'
            baseline = service(base, database)
            query = await fixture(baseline, runs, jobs)
            candidate = service(changed, database)
            before_db = hashlib.sha256(database.read_bytes()).hexdigest()
            reference = encoded(await state(baseline, query))
            before = await measured(baseline, query, reference, args.repeats)
            after = await measured(candidate, query, reference, args.repeats)
            assert hashlib.sha256(database.read_bytes()).hexdigest() == before_db, 'A state read modified the fixture DB'
            item = {'runs': runs, 'jobs_per_run': jobs, 'before': before, 'after': after,
                    'exact_json_equal': True, 'same_database_unchanged': True,
                    'response_sha256': hashlib.sha256(reference).hexdigest()}
            output['cases'].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    if args.output:
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    asyncio.run(main(args))
