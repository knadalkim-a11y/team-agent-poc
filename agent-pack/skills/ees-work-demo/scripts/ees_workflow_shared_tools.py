"""Shared managed read actions. Native owns code, settings, ACL and personal PAT.

This additive registry never migrates system-scoped, revision-pinned contracts.
A published job stores only shared_tool_id; runs separately freeze resolutions.
"""
from copy import deepcopy
import hashlib
import json
import time

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_native import MANAGED_READ_SOURCE_HASHES, init_native, _get, _json

NAMES = {
    'search_pages': ('Confluence', '페이지 찾기', '찾을 말과 공간으로 페이지 목록을 찾습니다.'),
    'get_page': ('Confluence', '페이지 읽기', '페이지 번호로 본문과 출처를 읽습니다.'),
    'jira_dashboard': ('Jira', '대시보드 보기', '프로젝트의 이슈 현황을 조회합니다.'),
    'jira_get_issue': ('Jira', '이슈 읽기', '이슈 번호로 내용을 읽습니다.'),
    'jira_project_metadata': ('Jira', '프로젝트 정보 보기', '프로젝트의 상태와 기본 정보를 읽습니다.'),
    'jira_search_crs': ('Jira', 'CR 찾기', '조건에 맞는 CR 목록을 찾습니다.'),
    'jira_issue_attachments': ('Jira', '이슈 첨부 조회', '이슈의 첨부 목록을 읽습니다.'),
    'jira_cr_attachments': ('Jira', 'CR 첨부 조회', 'CR별 첨부 현황을 확인합니다.'),
    'github_list_pull_requests': ('GitHub', 'PR 목록 보기', '저장소의 PR 목록을 찾습니다.'),
    'github_get_pull_request': ('GitHub', 'PR 읽기', 'PR 번호로 내용을 읽습니다.'),
}
OUTPUTS = {name: {'kind': 'evidence', 'fields': ['data', 'evidence'], 'completeness': 'partial_possible'} for name in NAMES}
OUTPUTS['search_pages'] = {'kind': 'list', 'fields': ['id', 'title', 'url'], 'completeness': 'page'}
OUTPUTS['get_page'] = {'kind': 'evidence', 'fields': ['data', 'evidence'], 'completeness': 'partial_possible'}
MESSAGES = {
    'shared_tool_unavailable': '기본 제공 도구가 설치되어 있지 않거나 원본이 다릅니다. 관리자에게 확인을 요청하세요.',
    'shared_tool_review_required': '도구 확인 필요 · 관리자에게 입력·결과와 연결 설정 확인을 요청하세요.',
    'shared_tool_disabled': '도구 사용 중지 · 관리자에게 다시 켜기를 요청하세요.',
    'shared_tool_forbidden': '이 도구를 쓸 수 있는 그룹 권한이 없습니다. 관리자에게 확인을 요청하세요.',
    'shared_tool_version_changed': '회차 시작 뒤 도구 버전이 바뀌었습니다. 새 버전으로 계속할지 직접 확인해 주세요.',
    'shared_tool_breaking_change': '입력·결과 모양이 호환되지 않아 같은 도구로 확인할 수 없습니다. 개발 담당자에게 새 도구를 요청하세요.',
}


def fail(code):
    raise WorkflowError(code, MESSAGES.get(code, '도구의 현재 권한·입력·버전을 확인해 주세요.'))


def init_shared(db):
    db.execute('CREATE TABLE IF NOT EXISTS work_shared_tools(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS work_shared_tool_versions(tool_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(tool_id,version))')
    db.execute('CREATE TABLE IF NOT EXISTS work_shared_tool_pins(run_kind TEXT NOT NULL,run_id TEXT NOT NULL,tool_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(run_kind,run_id,tool_id))')


def compatible(before, after):
    old, new = before['input_schema'], after['input_schema']
    if set(new.get('required', [])) - set(old.get('required', [])):
        return False
    for key, schema in old.get('properties', {}).items():
        candidate = new.get('properties', {}).get(key)
        # Descriptions/defaults may change; structural constraints may not.
        shape = lambda item: {k: v for k, v in item.items() if k not in ('description', 'title', 'default')}
        if not isinstance(candidate, dict) or shape(schema) != shape(candidate):
            return False
    return (before['output_schema']['kind'] == after['output_schema']['kind']
            and set(before['output_schema']['fields']) <= set(after['output_schema']['fields']))


class SharedTools:
    def __init__(self, service):
        self.service = service
        with service._db(write=True) as db:
            init_shared(db)
            init_native(db)

    @property
    def bridge(self):
        self.service.operations.configure()
        return self.service.operations.bridge

    def get(self, db, key):
        if not isinstance(key, str):
            fail('shared_tool_unavailable')
        row = db.execute('SELECT data FROM work_shared_tools WHERE id=?', (key,)).fetchone()
        if not row:
            fail('shared_tool_review_required')
        return json.loads(row[0])

    @staticmethod
    def authorize(item, actor, groups, *, management=False):
        if management and _get(actor, 'role') == 'admin':
            return
        if not set(item.get('group_ids', [])).intersection(groups):
            fail('shared_tool_forbidden')

    async def discover(self, actor):
        # Discovery reads installed content. Function names alone are not trust.
        tools = await self.bridge.managed_tools() if hasattr(self.bridge, "managed_tools") else []
        result = []
        for function, (target, label, description) in NAMES.items():
            family = target.lower()
            matches = [tool for tool in tools if hashlib.sha256(str(_get(tool, 'content', '')).encode('utf-8')).hexdigest() == MANAGED_READ_SOURCE_HASHES[family]]
            item = {'id': 'managed-' + function, 'function': function, 'name': target + ' ' + label,
                    'target': target, 'description': description, 'kind': 'read', 'auth': '개인 PAT(기존 방식)',
                    'state': 'unavailable', 'revision': 0, 'version': 0, 'group_ids': [], 'responsible_user_id': '',
                    'input_schema': {}, 'output_schema': deepcopy(OUTPUTS[function])}
            # Ambiguous registrations cannot silently pick a new source.
            if len(matches) == 1:
                try:
                    checked = await self.bridge.inspect(actor, _get(matches[0], 'id'), function)
                    item.update(reference=checked['reference'], input_schema=checked['schema'], state='review_required')
                except WorkflowError:
                    pass
            result.append(item)
        return result

    async def list(self, user, *, usable_only=False, summary=False):
        actor, _, groups = await self.service._work_actor(user)
        admin = _get(actor, 'role') == 'admin'
        available = await self.discover(actor)
        result = []
        with self.service._db() as db:
            saved = {row['id']: json.loads(row['data']) for row in db.execute('SELECT * FROM work_shared_tools')}
        for observed in available:
            item = deepcopy(saved.get(observed['id'], observed))
            if not admin and not set(item.get('group_ids', [])).intersection(groups):
                continue
            if observed['state'] == 'unavailable':
                item['state'] = 'unavailable'
            elif item.get('reference') != observed.get('reference'):
                item['state'] = 'review_required'
            item['can_use'] = bool(set(item.get('group_ids', [])).intersection(groups))
            if usable_only and (item['state'] != 'available' or not item['can_use']):
                continue
            if summary:
                safe = {key: deepcopy(item[key]) for key in ('id', 'name', 'target', 'description', 'output_schema', 'state')}
                safe['input_schema'] = {'type': 'object', 'required': item['input_schema'].get('required', []), 'properties': {key: {'type': spec.get('type', 'string')} for key, spec in item['input_schema'].get('properties', {}).items()}}
                result.append(safe)
                continue
            item['observed_reference'] = observed.get('reference') if admin else None
            item['observed_input_schema'] = observed['input_schema'] if admin else None
            with self.service._db() as db:
                versions = [json.loads(row[0]) for row in db.execute('SELECT data FROM work_shared_tool_versions WHERE tool_id=? ORDER BY version DESC', (item['id'],))]
                item['versions'] = [{k: v for k, v in version.items() if admin or k not in ('reference', 'actor', 'evidence')} for version in versions]
                uses = []
                for row in db.execute('SELECT * FROM work_definitions WHERE published_version IS NOT NULL'):
                    try:
                        self.service._work_authorize_scope(db, actor, groups, row['system_id'], role='viewer')
                    except WorkflowError:
                        continue
                    published = db.execute('SELECT definition FROM work_versions WHERE workflow_id=? AND version=?', (row['id'], row['published_version'])).fetchone()
                    definition = json.loads(published[0]) if published else {}
                    for node in definition.get('nodes', {}).values():
                        if node.get('shared_tool_id') == item['id']:
                            automated = db.execute('SELECT 1 FROM work_schedules WHERE workflow_id=? AND enabled=1', (row['id'],)).fetchone() is not None
                            uses.append({'workflow_id': row['id'], 'workflow_name': definition.get('name', ''), 'job_id': node['id'], 'job_name': node['name'], 'system_id': row['system_id'], 'automatic': automated})
                item['uses'] = uses
            if not admin:
                item.pop('reference', None)
            result.append(item)
        return result

    async def command(self, user, body):
        actor, _, groups = await self.service._work_actor(user)
        if _get(actor, 'role') != 'admin':
            fail('admin_required')
        action, key = body.get('action'), body.get('shared_tool_id')
        if action not in ('shared_tool_review', 'shared_tool_disable', 'shared_tool_enable', 'shared_tool_access'):
            fail('invalid_request')
        with self.service._db() as db:
            receipt = self.service.operations._receipt(db, actor, body)
            if receipt is not None:
                return receipt
        discovered = {item['id']: item for item in await self.discover(actor)}
        observed = discovered.get(key)
        if not observed or observed['state'] == 'unavailable':
            fail('shared_tool_unavailable')
        if body.get('reference') != observed['reference']:
            fail('shared_tool_review_required')
        from .ees_workflow import _resolve
        native_groups = await _resolve(self.service.group_list_lookup()) if self.service.group_list_lookup else []
        if action in ('shared_tool_review', 'shared_tool_access'):
            await self.service._user({'id': body.get('responsible_user_id', '')})
        actor, _, groups = await self.service._work_actor(actor)
        if _get(actor, 'role') != 'admin':
            fail('admin_required')
        with self.service._db(write=True) as db:
            runtime = self.service.operations
            receipt = runtime._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            row = db.execute('SELECT data FROM work_shared_tools WHERE id=?', (key,)).fetchone()
            old = json.loads(row[0]) if row else None
            runtime._revision(body, old['revision'] if old else 0)
            item = deepcopy(old or observed)
            if action in ('shared_tool_review', 'shared_tool_access'):
                selected = body.get('group_ids')
                known = {_get(group, 'id') for group in native_groups}
                if not isinstance(selected, list) or not selected or any(not isinstance(g, str) or g not in known for g in selected):
                    fail('shared_tool_forbidden')
                owner = body.get('responsible_user_id')
                if not isinstance(owner, str) or not owner:
                    fail('invalid_request')
                item.update(group_ids=sorted(set(selected)), responsible_user_id=owner)
            if action == 'shared_tool_review':
                if old and not compatible(old, observed):
                    fail('shared_tool_breaking_change')
                # Evidence is checked even when reusing an existing approval.
                evidence = body.get('evidence', '')
                import re
                if not isinstance(evidence, str) or not 8 <= len(evidence.strip()) <= 2000 or re.search(r'(bearer\s|authorization|password\s*=|token\s*=|pat\s*=|cookie\s*=|[\x00-\x08\x0b-\x1f])', evidence, re.I):
                    fail('native_approval_evidence_required')
                reference = observed['reference']
                approval = db.execute('SELECT reference,state FROM native_approvals WHERE tool_id=? AND function=?', (reference['tool_id'], reference['function'])).fetchone()
                if not approval or approval['state'] != 'allowed' or json.loads(approval['reference']) != reference:
                    reference = self.bridge.store_approval(db, actor, reference, evidence)['reference']
                item.update(reference=reference, input_schema=observed['input_schema'], output_schema=observed['output_schema'], state='available', version=item['version'] + 1)
                version = {k: deepcopy(item[k]) for k in ('version', 'reference', 'input_schema', 'output_schema')}
                version.update(actor=_get(actor, 'id'), evidence=evidence.strip(), at=time.time())
                db.execute('INSERT INTO work_shared_tool_versions VALUES(?,?,?)', (key, item['version'], _json(version)))
            elif not old:
                fail('shared_tool_review_required')
            elif action == 'shared_tool_disable':
                item['state'] = 'disabled'
            elif action == 'shared_tool_enable':
                if item['reference'] != observed['reference']:
                    fail('shared_tool_review_required')
                item['state'] = 'available'
            item['revision'] += 1
            db.execute('INSERT INTO work_shared_tools VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data', (key, item['revision'], _json(item)))
            runtime._event(db, key, actor, action, {'version': item['version'], 'revision': item['revision']})
            return runtime._remember(db, actor, body, {'ok': True, 'shared_tool_id': key})

    def pin(self, db, actor, groups, kind, run_id, definition):
        keys = {node['shared_tool_id'] for node in definition.get('nodes', {}).values() if node.get('shared_tool_id')}
        keys.update(call['shared_tool_id'] for node in definition.get('nodes', {}).values() for call in (node.get('execution') or {}).get('calls', []) if call.get('shared_tool_id'))
        for key in keys:
            item = self.get(db, key)
            self.authorize(item, actor, groups)
            if item['state'] != 'available':
                fail('shared_tool_disabled' if item['state'] == 'disabled' else 'shared_tool_review_required')
            pin = {k: deepcopy(item[k]) for k in ('id', 'version', 'reference')}
            db.execute('INSERT INTO work_shared_tool_pins VALUES(?,?,?,?)', (kind, run_id, key, _json(pin)))

    async def resolve(self, user, key, *, kind=None, run_id=None):
        actor, _, groups = await self.service._work_actor(user)
        with self.service._db() as db:
            item = self.get(db, key)
            self.authorize(item, actor, groups)
            if item['state'] != 'available':
                fail('shared_tool_disabled' if item['state'] == 'disabled' else 'shared_tool_review_required')
            pin = {k: deepcopy(item[k]) for k in ('id', 'version', 'reference')}
            if run_id:
                row = db.execute('SELECT data FROM work_shared_tool_pins WHERE run_kind=? AND run_id=? AND tool_id=?', (kind, run_id, key)).fetchone()
                if not row:
                    fail('shared_tool_review_required')
                pin = json.loads(row[0])
        family = NAMES[item['function']][0].lower()
        checked = await self.bridge.inspect(actor, item['reference']['tool_id'], item['function'])
        if checked['reference']['content_hash'] != MANAGED_READ_SOURCE_HASHES[family]:
            fail('shared_tool_unavailable')
        if checked['reference'] != item['reference'] or checked['state'] != 'allowed':
            fail('shared_tool_review_required')
        if pin['reference'] != checked['reference']:
            fail('shared_tool_version_changed')
        await self.bridge.check(actor, pin['reference'])
        actor, _, groups = await self.service._work_actor(actor)
        with self.service._db() as db:
            latest = self.get(db, key)
            self.authorize(latest, actor, groups)
            if latest["state"] != "available" or latest["reference"] != item["reference"]:
                fail("shared_tool_review_required")
        return pin


    async def accept_version(self, user, body):
        actor, _, groups = await self.service._work_actor(user)
        key, run_id = body.get('shared_tool_id'), body.get('run_id')
        with self.service._db() as db:
            self.service._work_run(db, actor, groups, run_id, write=True)
        pin = await self.resolve(actor, key)
        actor, _, groups = await self.service._work_actor(actor)
        with self.service._db(write=True) as db:
            receipt = self.service.operations._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            run = self.service._work_run(db, actor, groups, run_id, write=True)
            self.service.operations._revision(body, run['revision'])
            latest = self.get(db, key)
            self.authorize(latest, actor, groups)
            if latest['state'] != 'available' or latest['version'] != pin['version']:
                fail('shared_tool_review_required')
            previous = db.execute('SELECT data FROM work_shared_tool_pins WHERE run_kind=? AND run_id=? AND tool_id=?', ('work', run_id, key)).fetchone()
            if not previous or body.get('version') != pin['version'] or self.get(db, key)['reference'] != pin['reference']:
                fail('shared_tool_version_changed')
            if db.execute("SELECT 1 FROM work_jobs WHERE run_id=? AND status='running'", (run_id,)).fetchone():
                fail('execution_running')
            db.execute('UPDATE work_shared_tool_pins SET data=? WHERE run_kind=? AND run_id=? AND tool_id=?', (_json(pin), 'work', run_id, key))
            db.execute('UPDATE work_runs SET revision=revision+1 WHERE id=?', (run_id,))
            self.service.operations._event(db, run_id, actor, 'shared_tool_accept_version', {'before': json.loads(previous[0]), 'after': pin})
            return self.service.operations._remember(db, actor, body, {'ok': True, 'run_id': run_id})
