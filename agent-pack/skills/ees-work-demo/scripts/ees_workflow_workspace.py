"""Versioned work in the existing Native workflow database.

This module owns business state, not Native identities, conversations or secrets.
Definitions, published versions, cycles, attempts and decisions have independent
revisions. Legacy catalog/cases remain untouched and are readable via the legacy
history endpoint. All changes are transactional authenticated user commands.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import re
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ees_workflow_authoring import WorkflowError, _value, _resolve, _now, _hash, _fail
from .ees_workflow_definition import SYSTEMS, CATEGORIES, IDENTIFIER, MAX_DOCUMENT_BYTES, _dump
from .ees_workflow_view import workflow_help

INPUT_TYPES = ('text', 'number', 'datetime', 'single', 'multi', 'list', 'person', 'boolean')
BLOCKS = ('values', 'schedule', 'checklist', 'list_confirm', 'item_verdict', 'ai_review', 'human_confirm', 'change_request')
TERMINAL = {'completed', 'cancelled'}
SECRET_KEYS = re.compile(r'(^|_)(pat|password|secret|token|authorization|api_key|credential)(_|$)', re.I)
ROLES = ('viewer', 'participant', 'manager', 'requester', 'reviewer')


def _public(value, depth=0):
    if depth > 24:
        _fail('invalid_data', '입력 구조가 너무 깊습니다.')
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or SECRET_KEYS.search(key):
                _fail('secret_forbidden', '비밀정보는 Native 개인 설정에 보관해 주세요.')
            _public(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _public(child, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        _fail('invalid_data', '유한한 숫자를 입력해 주세요.')
    elif not isinstance(value, (str, int, float, bool, type(None))):
        _fail('invalid_data', 'JSON으로 저장할 수 없는 값입니다.')
    try:
        if len(_dump(value).encode()) > MAX_DOCUMENT_BYTES:
            _fail('invalid_data', '저장할 자료의 크기를 줄여 주세요.')
    except (ValueError, TypeError, OverflowError):
        _fail('invalid_data', 'JSON 값의 형식을 확인해 주세요.')


def _revision(body, current):
    expected = body.get('expected_revision')
    if isinstance(expected, bool) or not isinstance(expected, int) or expected != current:
        _fail('revision_conflict', '다른 변경이 있습니다. 최신 내용을 다시 확인해 주세요.')


def _id(value):
    return isinstance(value, str) and value not in {'__proto__', 'constructor', 'prototype'} and bool(IDENTIFIER.fullmatch(value))


def _condition(condition, attributes):
    """Three-valued, data-only factory predicate: None means needs checking."""
    if not condition:
        return True
    if 'all' in condition:
        values = [_condition(item, attributes) for item in condition['all']]
        return False if False in values else None if None in values else True
    if 'any' in condition:
        values = [_condition(item, attributes) for item in condition['any']]
        return True if True in values else None if None in values else False
    field = condition['field']
    if field not in attributes:
        return None
    left, right, op = attributes[field], condition['value'], condition['op']
    try:
        return {'eq': lambda: left == right, 'ne': lambda: left != right,
                'in': lambda: left in right, 'not_in': lambda: left not in right,
                'gt': lambda: left > right, 'gte': lambda: left >= right,
                'lt': lambda: left < right, 'lte': lambda: left <= right}[op]()
    except (TypeError, ValueError):
        return None


def _condition_valid(value, depth=0):
    if not value:
        return value in (None, {})
    if not isinstance(value, dict) or depth > 5:
        return False
    if set(value) in ({'all'}, {'any'}):
        items = next(iter(value.values()))
        return isinstance(items, list) and 0 < len(items) <= 20 and all(_condition_valid(item, depth + 1) for item in items)
    return (set(value) == {'field', 'op', 'value'} and _id(value['field']) and
            value['op'] in ('eq', 'ne', 'in', 'not_in', 'gt', 'gte', 'lt', 'lte') and
            (value['op'] not in ('in', 'not_in') or isinstance(value['value'], list)))


def definition_check(definition, complete=True):
    """Validation is independent of the editor and never evaluates expressions."""
    errors, warnings = [], []
    if not isinstance(definition, dict):
        return ['절차는 객체여야 합니다.'], warnings
    if not _id(definition.get('id')) or not isinstance(definition.get('name'), str) or not definition['name'].strip():
        errors.append('절차 ID와 이름이 필요합니다.')
    if definition.get('system_id') not in (*SYSTEMS, 'COMMON'):
        errors.append('관리 시스템을 선택해 주세요.')
    if definition.get('category', 'ops') not in CATEGORIES or definition.get('mode', 'on_demand') not in ('periodic', 'on_demand', 'emergency'):
        errors.append('업무 분류와 실행 방식을 확인해 주세요.')
    if definition.get('execution_scope') not in (None, 'factory', 'system'):
        errors.append('업무 범위는 공장 단위 또는 시스템 단위로 선택해 주세요.')
    for field, supported in (('completion_policy', 'all_required_approved'), ('unapproved_policy', 'hold'), ('delivery_policy', 'draft_only')):
        if definition.get(field) not in (None, '', supported):
            errors.append(f'{field}: 지원하는 정책을 선택하고 설명은 별도 메모에 기록해 주세요.')
    for judgment in definition.get('judgments', []):
        if not isinstance(judgment, dict) or not _id(judgment.get('id')) or not isinstance(judgment.get('label'), str) or judgment.get('status') not in ('completed', 'failed', 'unknown', 'action_required'):
            errors.append('판정 문구는 완료·실패·미확인·사람 조치 필요의 의미에 연결해 주세요.')
    nodes = definition.get('nodes')
    if not isinstance(nodes, dict) or len(nodes) > 250:
        return errors + ['P/T/J 구조를 확인해 주세요.'], warnings
    if complete and definition.get('mode') == 'periodic' and definition.get('schedule'):
        from .ees_workflow_operations import validate_schedule_definition
        try:
            validate_schedule_definition(definition['schedule'], nodes)
        except WorkflowError as error:
            errors.append(error.message)
    field_ids, jobs = {}, []
    for key, node in nodes.items():
        if not _id(key) or not isinstance(node, dict) or node.get('id') != key or node.get('type') not in ('p', 't', 'j'):
            errors.append(f'{key}: 작업 ID와 종류를 확인해 주세요.'); continue
        if not isinstance(node.get('name'), str) or not node['name'].strip():
            errors.append(f'{key}: 이름이 필요합니다.')
        if not _condition_valid(node.get('condition')):
            errors.append(f'{key}: 지원하지 않는 공장 조건입니다.')
        for field in ('children', 'deps'):
            refs = node.get(field, [])
            if not isinstance(refs, list) or any(not _id(ref) or ref not in nodes for ref in refs) or len(refs) != len(set(refs)):
                errors.append(f'{key}: 삭제되거나 중복된 {field} 참조입니다.')
        parent = node.get('parent')
        if node['type'] == 'p':
            if parent is not None:
                errors.append(f'{key}: 절차는 최상위여야 합니다.')
        elif parent not in nodes or nodes[parent].get('type') != ('p' if node['type'] == 't' else 't') or key not in nodes[parent].get('children', []):
            errors.append(f'{key}: 상위 구조와 연결을 확인해 주세요.')
        for child in node.get('children', []):
            if child in nodes and nodes[child].get('parent') != key:
                errors.append(f'{key}: 하위 구조가 일치하지 않습니다.')
        if node['type'] != 'j':
            if complete and not node.get('children'):
                errors.append(f'{key}: 하위 작업을 추가해 주세요.')
            continue
        jobs.append(node)
        judgments = node.get('judgments', definition.get('judgments', []))
        if not isinstance(judgments, list) or len(judgments) > 30 or any(not isinstance(item, dict) or not _id(item.get('id')) or not isinstance(item.get('label'), str) or not item['label'].strip() or item.get('status') not in ('completed', 'failed', 'unknown', 'action_required') or not isinstance(item.get('consequence', ''), str) for item in judgments):
            errors.append(f'{key}: 판정 문구와 기본 상태 연결을 확인해 주세요.')
            judgments = []
        judgment_ids = {item['id'] for item in judgments}
        if len(judgment_ids) != len(judgments):
            errors.append(f'{key}: 판정 ID는 중복될 수 없습니다.')
        if not isinstance(node.get('confirmation_notes', ''), str):
            errors.append(f'{key}: 사람 확인 안내는 글로 입력해 주세요.')
        suggestions = node.get('suggestion_rules')
        if suggestions is not None:
            valid = isinstance(suggestions, dict) and type(suggestions.get('provisional', False)) is bool and isinstance(suggestions.get('description', ''), str)
            rules = suggestions.get('rules', []) if isinstance(suggestions, dict) else None
            human_only = suggestions.get('human_only_judgment_ids', []) if isinstance(suggestions, dict) else None
            valid = valid and isinstance(rules, list) and len(rules) <= 50 and isinstance(human_only, list) and all(isinstance(item, str) and item in judgment_ids for item in human_only)
            if valid:
                valid = all(isinstance(rule, dict) and _id(rule.get('id')) and isinstance(rule.get('condition'), str) and rule.get('outcome') in ('none', 'judgment') and (rule.get('outcome') != 'judgment' or isinstance(rule.get('judgment_id'), str) and rule['judgment_id'] in judgment_ids and rule['judgment_id'] not in human_only) for rule in rules)
                valid = valid and len({rule['id'] for rule in rules}) == len(rules)
            if not valid:
                errors.append(f'{key}: AI 제안 규칙과 연결한 판정을 확인해 주세요.')
            elif complete and suggestions.get('provisional'):
                warnings.append(f'{key}: AI 판정 제안 규칙이 임시값입니다. 확인을 권장합니다.')
        if complete and node.get('result_block') == 'item_verdict' and definition.get('unapproved_policy') in (None, '', 'hold'):
            warnings.append(f'{key}: D-5 이후 미승인 CR 처리 방식이 정해지지 않았습니다. 게시는 가능하며 해당 처리는 확인 필요로 남습니다.')
        if complete and isinstance(node.get('completion'), dict) and node['completion'].get('kind') == 'delivery':
            warnings.append(f'{key}: 송부 방식이 연결되지 않았습니다. 게시는 가능하며 해당 작업의 보내기는 막힙니다.')
        if node.get('children'):
            errors.append(f'{key}: 작업에 하위 항목을 둘 수 없습니다.')
        dependency_policy = node.get('dependency_policy', 'all_completed')
        if dependency_policy not in ('all_completed', 'all_resolved') or (dependency_policy == 'all_resolved' and not (node.get('mode') == 'ai' and node.get('result_block') == 'ai_review')):
            errors.append(f'{key}: 판정 완료 근거의 사용은 AI 결과 초안에만 허용됩니다.')
        if node.get('mode', 'human') not in ('human', 'tool', 'ai') or node.get('result_block', 'human_confirm') not in BLOCKS:
            errors.append(f'{key}: 실행 방법과 주 결과 블록을 확인해 주세요.')
        if (node.get('result_block') == 'item_verdict' or node.get('mode') == 'ai' and node.get('result_block') == 'ai_review') and node.get('human_confirmation', True) is not True:
            errors.append(f'{key}: AI 제안과 항목 판정은 사람 확인이 필요합니다.')
        if not isinstance(node.get('human_confirmation', True), bool):
            errors.append(f'{key}: 사람 확인 조건을 확인해 주세요.')
        if complete and 'read_retry' in node:
            from .ees_workflow_operations import validate_read_retry
            try:
                validate_read_retry(node)
            except WorkflowError as error:
                errors.append(f'{key}: {error.message}')
        if complete:
            completion = node.get('completion', {})
            if not isinstance(completion, dict) or completion.get('kind') not in (None, 'review', 'delivery'):
                errors.append(f'{key}: 지원하는 완료 의미를 선택해 주세요.')
            elif completion.get('kind') == 'delivery' and (node.get('mode') != 'ai' or node.get('result_block') != 'ai_review'):
                errors.append(f'{key}: 송부 완료는 AI 결과 초안의 실제 송부 작업에만 사용할 수 있습니다.')
        if type(node.get('approval_count', 0)) is not int or node.get('approval_count', 0) not in (0, 1, 2):
            errors.append(f'{key}: 요청 승인 인원은 0, 1, 2명입니다.')
        deadline = node.get('deadline')
        if deadline:
            valid_deadline = isinstance(deadline, dict) and set(deadline) == {'input', 'offset_days', 'timezone', 'calendar'} and _id(deadline.get('input')) and type(deadline.get('offset_days')) is int and -366 <= deadline['offset_days'] <= 366 and deadline.get('calendar') in ('calendar', 'business')
            if valid_deadline:
                try: ZoneInfo(deadline['timezone'])
                except (ZoneInfoNotFoundError, TypeError, ValueError): valid_deadline = False
            if not valid_deadline: errors.append(f'{key}: 기준 날짜 입력·일수·시간대·달력 방식을 확인해 주세요.')
        trigger = node.get('trigger', {})
        if trigger:
            valid_trigger = isinstance(trigger, dict) and set(trigger) in ({'at'}, {'offset_seconds'})
            if valid_trigger and 'offset_seconds' in trigger:
                valid_trigger = type(trigger['offset_seconds']) is int and 0 <= trigger['offset_seconds'] <= 366 * 86400
            elif valid_trigger:
                try:
                    valid_trigger = datetime.fromisoformat(trigger['at'].replace('Z', '+00:00')).tzinfo is not None
                except (ValueError, AttributeError, TypeError):
                    valid_trigger = False
            if not valid_trigger:
                errors.append(f'{key}: 명시된 시간대의 예정 시각 또는 초 단위 지연을 입력해 주세요.')
        fields = node.get('inputs', [])
        if not isinstance(fields, list) or len(fields) > 100:
            errors.append(f'{key}: 입력 정의를 확인해 주세요.'); continue
        for field in fields:
            if not isinstance(field, dict) or not _id(field.get('id')) or field.get('type') not in INPUT_TYPES:
                errors.append(f'{key}: 입력 ID와 형식을 확인해 주세요.'); continue
            field_id = field['id']
            if SECRET_KEYS.search(field_id):
                errors.append(f'{field_id}: 비밀정보 입력은 업무에 저장할 수 없습니다.')
            if field_id in field_ids and field_ids[field_id] != field:
                errors.append(f'{field_id}: 같은 입력 ID의 정의가 다릅니다.')
            field_ids[field_id] = field
            if field.get('scope', 'run') not in ('run', 'workflow', 'factory') or not isinstance(field.get('required', False), bool):
                errors.append(f'{field_id}: 저장 범위와 필수 여부를 확인해 주세요.')
            if field.get('options_source', 'manual') not in ('manual', 'tool', 'common'):
                errors.append(f'{field_id}: 선택지 원본 종류를 확인해 주세요.')
            if complete and field.get('options_source', 'manual') != 'manual' and not _options_query_valid(field):
                errors.append(f'{field_id}: 현재 권한으로 조회하는 선택지 연결이 아직 구성되지 않았습니다.')
            if field['type'] in ('single', 'multi') and not isinstance(field.get('options', []), list):
                errors.append(f'{field_id}: 선택지 목록을 확인해 주세요.')
        if node.get('mode') == 'tool' and complete:
            ref = node.get('tool_reference')
            if not isinstance(ref, dict) or any(not isinstance(ref.get(f), str) or not ref[f] for f in ('tool_id', 'function')):
                errors.append(f'{key}: 검증된 Native 도구 참조가 필요합니다.')
            elif not (ref.get('content_hash') or ref.get('code_hash')):
                errors.append(f'{key}: Native 코드 지문이 필요합니다.')
            if not isinstance(node.get('argument_bindings', {}), dict):
                errors.append(f'{key}: 입력과 도구 인자 연결을 확인해 주세요.')
        for dep in node.get('deps', []):
            if dep == key:
                errors.append(f'{key}: 자기 자신을 선행 작업으로 지정할 수 없습니다.')
    if complete and (len([n for n in nodes.values() if n.get('type') == 'p']) != 1 or not jobs):
        errors.append('절차 하나와 하나 이상의 작업이 필요합니다.')
    for field_id, field in field_ids.items():
        dependencies = field.get('depends_on', [])
        if isinstance(dependencies, str):
            dependencies = [dependencies] if dependencies else []
        if not isinstance(dependencies, list) or any(dependency not in field_ids or dependency == field_id for dependency in dependencies):
            errors.append(f'{field_id}: 선택지의 선행 입력을 확인해 주세요.')
    for node in jobs:
        local_definitions = [field for field in node.get('inputs', []) if isinstance(field, dict) and 'id' in field] if isinstance(node.get('inputs', []), list) else []
        local_fields = {field['id'] for field in local_definitions}
        for field in local_definitions:
            dependencies = field.get('depends_on', [])
            dependencies = [dependencies] if isinstance(dependencies, str) and dependencies else dependencies
            if isinstance(dependencies, list) and any(dependency not in local_fields for dependency in dependencies):
                errors.append(f'{field["id"]}: 선택지 조회에 쓰는 선행 입력을 같은 작업에 선언해 주세요.')
        deadline = node.get('deadline')
        if deadline and isinstance(deadline, dict) and (deadline.get('input') not in field_ids or field_ids.get(deadline.get('input'), {}).get('type') != 'datetime'):
            errors.append(f'{node["id"]}: 기한의 기준은 선언된 날짜/시각 입력이어야 합니다.')
        for argument, binding in node.get('argument_bindings', {}).items():
            valid = _id(argument) and isinstance(binding, dict)
            if valid and set(binding) == {'input'}:
                valid = binding['input'] in local_fields
            elif valid and set(binding) == {'constant'}:
                valid = isinstance(binding['constant'], (str, int, float, bool, list, dict, type(None)))
            elif valid and set(binding) == {'result'}:
                source = binding['result']
                valid = (isinstance(source, dict) and set(source) == {'job_id', 'path', 'value_field', 'confirmed'} and source['confirmed'] is True and
                         source['job_id'] in WorkspaceMixin._work_prerequisite_jobs(definition, node['id']) and
                         isinstance(source['path'], list) and 0 < len(source['path']) <= 8 and all(_id(key) for key in source['path']) and _id(source['value_field']))
            else:
                valid = False
            if not valid:
                errors.append(f'{node["id"]}: 선언된 입력 또는 확정된 선행 작업 목록만 도구 인자에 연결할 수 있습니다.')
    def visit(key, path):
        if key in path:
            return True
        return any(visit(dep, path | {key}) for dep in nodes.get(key, {}).get('deps', []) if dep in nodes)
    if any(visit(key, set()) for key in nodes):
        errors.append('선행조건의 순환 참조를 제거해 주세요.')
    if not errors:
        effective = {node['id']: WorkspaceMixin._work_prerequisite_jobs(definition, node['id']) for node in jobs}
        def effective_cycle(key, path):
            return key in path or any(effective_cycle(dependency, path | {key}) for dependency in effective.get(key, ()))
        if any(effective_cycle(key, set()) for key in effective):
            errors.append('P/T에서 상속한 선행조건에 순환 참조가 있습니다. 작업 단위의 실행 순서를 확인해 주세요.')
    if jobs and sum(bool(n.get('condition')) for n in jobs) > len(jobs) / 2:
        warnings.append('작업 절반 이상에 공장별 차이가 있습니다. 별도 절차가 더 적합한지 확인해 주세요.')
    for key in definition.get('factory_overrides', {}):
        if key not in nodes:
            errors.append(f'{key}: 삭제된 작업의 공장별 설정이 남아 있습니다.')
    return list(dict.fromkeys(errors)), warnings


def _options_query_valid(field):
    source, query = field.get('options_source', 'manual'), field.get('options_query')
    if source == 'manual':
        return True
    if not isinstance(query, dict) or field.get('type') not in ('single', 'multi'):
        return False
    if source == 'common':
        return set(query) == {'kind'} and query['kind'] in ('factories', 'systems', 'groups')
    if source != 'tool' or not isinstance(query.get('reference'), dict):
        return False
    if not all(isinstance(query['reference'].get(key), str) and query['reference'][key] for key in ('tool_id', 'function', 'content_hash')):
        return False
    if not isinstance(query.get('argument_bindings', {}), dict):
        return False
    dependencies = field.get('depends_on', [])
    dependencies = [dependencies] if isinstance(dependencies, str) and dependencies else dependencies
    for key, binding in query.get('argument_bindings', {}).items():
        if not _id(key) or not isinstance(binding, dict) or set(binding) not in ({'input'}, {'constant'}):
            return False
        if 'input' in binding and binding['input'] not in dependencies:
            return False
    path = query.get('result_path', [])
    return isinstance(path, list) and len(path) <= 8 and all(_id(key) for key in path) and _id(query.get('value_field')) and _id(query.get('label_field'))


def input_errors(fields, values, complete=True, options_snapshot=None):
    errors = []
    by_id = {field['id']: field for field in fields}
    for key in values:
        if key not in by_id:
            errors.append(f'{key}: 선언되지 않은 입력입니다.')
    for key, field in by_id.items():
        if key not in values or values[key] is None:
            if complete and field.get('required'):
                errors.append(f'{key}: 필수값을 입력해 주세요.')
            continue
        options_record = (options_snapshot or {}).get(key)
        if field.get('options_source', 'manual') != 'manual' and not options_record:
            if complete:
                errors.append(f'{key}: 현재 권한으로 조회한 선택지가 필요합니다.')
                continue
        value, kind = values[key], field['type']
        valid = True
        if kind == 'text': valid = isinstance(value, str)
        elif kind == 'number': valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif kind == 'datetime':
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00')); valid = isinstance(value, str)
            except (ValueError, TypeError, AttributeError): valid = False
        elif kind == 'boolean': valid = isinstance(value, bool)
        elif kind == 'person': valid = isinstance(value, dict) and set(value) == {'kind', 'id'} and value['kind'] in ('user', 'group') and _id(value['id'])
        elif kind == 'list': valid = isinstance(value, list) and len(value) <= 1000
        elif kind in ('single', 'multi'):
            options = [entry.get('id') if isinstance(entry, dict) else entry for entry in (options_record['options'] if options_record else field.get('options', []))]
            if field.get('options_source', 'manual') != 'manual' and not options_record and not complete:
                options = value if isinstance(value, list) else [value]
            valid = (isinstance(value, (str, int)) and not isinstance(value, bool) and value in options if kind == 'single' else isinstance(value, list) and len(value) == len(set(map(str, value))) and all(isinstance(item, (str, int)) and not isinstance(item, bool) and item in options for item in value))
        if not valid:
            errors.append(f'{key}: {kind} 입력 형식과 선택지를 확인해 주세요.')
        if complete and field.get('required') and value in ('', []):
            errors.append(f'{key}: 필수값을 입력해 주세요.')
    return errors


class WorkspaceMixin:
    def _init_workspace(self, db):
        # Called inside the service initialization transaction. A partial schema
        # cannot silently reset to an empty database.
        db.execute('CREATE TABLE IF NOT EXISTS work_schema (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)')
        marker = db.execute('SELECT version FROM work_schema WHERE id=1').fetchone()
        if marker and marker['version'] not in (1, 2):
            _fail('workspace_upgrade_required', '업무 저장소 버전을 확인해 주세요.')
        definitions = {
            'work_definitions': 'id TEXT PRIMARY KEY, system_id TEXT NOT NULL, draft TEXT NOT NULL, revision INTEGER NOT NULL, published_version INTEGER, validation TEXT, created_by TEXT NOT NULL, updated_at TEXT NOT NULL',
            'work_versions': 'workflow_id TEXT NOT NULL, version INTEGER NOT NULL, definition TEXT NOT NULL, hash TEXT NOT NULL, publisher TEXT NOT NULL, published_at TEXT NOT NULL, PRIMARY KEY(workflow_id,version)',
            'work_factories': 'id TEXT PRIMARY KEY, system_id TEXT NOT NULL, name TEXT NOT NULL, attributes TEXT NOT NULL, revision INTEGER NOT NULL',
            'work_access': 'id TEXT PRIMARY KEY, system_id TEXT NOT NULL, factory_id TEXT NOT NULL, principal_kind TEXT NOT NULL, principal_id TEXT NOT NULL, roles TEXT NOT NULL, active INTEGER NOT NULL, revision INTEGER NOT NULL',
            'work_settings': 'workflow_id TEXT NOT NULL, factory_id TEXT NOT NULL, values_json TEXT NOT NULL, revision INTEGER NOT NULL, updated_by TEXT NOT NULL, PRIMARY KEY(workflow_id,factory_id)',
            'work_runs': 'id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, version INTEGER NOT NULL, system_id TEXT NOT NULL, factory_id TEXT NOT NULL, owner TEXT NOT NULL, sharing TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, inputs TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT',
            'work_jobs': 'run_id TEXT NOT NULL, job_id TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, current_attempt TEXT, claim_actor TEXT, reason TEXT NOT NULL DEFAULT \'\', PRIMARY KEY(run_id,job_id)',
            'work_attempts': 'id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL, number INTEGER NOT NULL, actor_id TEXT NOT NULL, inputs TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, finished_at TEXT, UNIQUE(run_id,job_id,number)',
            'work_decisions': 'id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL, item_id TEXT NOT NULL, attempt_id TEXT NOT NULL, result_revision INTEGER NOT NULL, verdict TEXT NOT NULL, note TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,job_id,item_id,attempt_id,result_revision)',
            'work_receipts': 'actor_id TEXT NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(actor_id,request_id)',
            'work_audit': 'id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, before_revision INTEGER, after_revision INTEGER, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL',
            'work_ui': 'actor_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL',
            'work_chat_links': 'actor_id TEXT NOT NULL, chat_id TEXT NOT NULL, run_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(actor_id,chat_id,run_id)',
        }
        if marker:
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not set(definitions) <= present:
                _fail('workspace_corrupt', '업무 저장소 일부가 없습니다. 백업과 복구 상태를 확인해 주세요.')
            if marker['version'] == 2 and 'work_review_revisions' not in present:
                _fail('workspace_corrupt', '검토 본문 이력이 없습니다. 백업과 복구 상태를 확인해 주세요.')
        for name, columns in definitions.items():
            db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({columns})')
        # A reviewed draft is editable evidence, never an overwrite of the AI
        # result. The surrounding initialization transaction upgrades v1 in place.
        db.execute('CREATE TABLE IF NOT EXISTS work_review_revisions (attempt_id TEXT NOT NULL, revision INTEGER NOT NULL, text TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL, decision_id TEXT, PRIMARY KEY(attempt_id,revision), UNIQUE(decision_id))')
        columns = [(item['name'], item['type'].upper(), item['notnull'], item['pk']) for item in db.execute('PRAGMA table_info(work_review_revisions)')]
        expected = [('attempt_id', 'TEXT', 1, 1), ('revision', 'INTEGER', 1, 2), ('text', 'TEXT', 1, 0), ('actor_id', 'TEXT', 1, 0), ('created_at', 'TEXT', 1, 0), ('decision_id', 'TEXT', 0, 0)]
        decision_unique = any(index['unique'] and not index['partial'] and [item['name'] for item in db.execute('SELECT name FROM pragma_index_info(?) ORDER BY seqno', (index['name'],))] == ['decision_id'] for index in db.execute('PRAGMA index_list(work_review_revisions)'))
        if columns != expected or not decision_unique:
            _fail('workspace_corrupt', '검토 본문 저장 구조가 완전하지 않습니다. 백업과 복구 상태를 확인해 주세요.')
        db.execute('INSERT OR IGNORE INTO work_schema VALUES(1,2)')
        db.execute('UPDATE work_schema SET version=2 WHERE id=1 AND version=1')
        db.execute('CREATE INDEX IF NOT EXISTS work_run_scope ON work_runs(system_id,factory_id,status)')
        db.execute('CREATE INDEX IF NOT EXISTS work_attempt_job ON work_attempts(run_id,job_id,number)')
        db.execute("CREATE TRIGGER IF NOT EXISTS work_attempt_finished_immutable BEFORE UPDATE ON work_attempts WHEN OLD.status <> 'running' BEGIN SELECT RAISE(ABORT,'immutable completed attempt'); END")
        db.execute("CREATE TRIGGER IF NOT EXISTS work_attempt_delete_immutable BEFORE DELETE ON work_attempts BEGIN SELECT RAISE(ABORT,'immutable attempt history'); END")
        # Published evidence and human decisions are append-only, including for
        # a later program version accidentally using an UPDATE.
        for table in ('work_versions', 'work_decisions', 'work_review_revisions'):
            for action in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()}_immutable BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable work evidence'); END")

    async def _work_actor(self, user):
        actor = await self._user(user)
        try:
            rows = await _resolve(self.group_lookup(_value(actor, 'id'))) if self.group_lookup else []
            if not isinstance(rows, (list, tuple)):
                raise ValueError('groups')
            groups = {_value(row, 'id') for row in rows if isinstance(_value(row, 'id'), str)}
        except Exception:
            _fail('authorization_unavailable', '현재 Native 그룹 권한을 확인하지 못했습니다.')
        return actor, {'actor_id': _value(actor, 'id'), 'is_admin': _value(actor, 'role') == 'admin'}, groups

    def _work_authorize_scope(self, db, actor, groups, system_id, factory_id='', role='participant'):
        if system_id not in (*SYSTEMS, 'COMMON'):
            _fail('scope_forbidden', '접근할 수 있는 작업 위치를 선택해 주세요.')
        if _value(actor, 'role') == 'admin':
            return
        actor_id = _value(actor, 'id')
        if role in ('manager', 'viewer', 'participant'):
            mapping = db.execute('SELECT group_id FROM system_groups WHERE system_id=? AND active=1', (system_id,)).fetchone()
            if mapping and mapping['group_id'] in groups:
                return
        for row in db.execute('SELECT * FROM work_access WHERE system_id=? AND active=1', (system_id,)):
            if row['principal_id'] not in ({actor_id} if row['principal_kind'] == 'user' else groups):
                continue
            if row['factory_id'] not in ('*', factory_id):
                continue
            roles = json.loads(row['roles'])
            if role in roles or (role == 'viewer' and set(roles) & set(ROLES)) or (role == 'participant' and 'manager' in roles):
                return
        _fail('scope_forbidden', '이 작업 위치의 권한이 없습니다.')

    def _work_system_visible(self, db, actor, groups, system_id):
        try:
            self._work_authorize_scope(db, actor, groups, system_id, '', 'viewer')
            return True
        except WorkflowError:
            for factory in db.execute('SELECT id FROM work_factories WHERE system_id=?', (system_id,)):
                try:
                    self._work_authorize_scope(db, actor, groups, system_id, factory['id'], 'viewer')
                    return True
                except WorkflowError:
                    pass
        return False

    def _work_definition(self, db, actor, groups, workflow_id, manage=False):
        row = db.execute('SELECT * FROM work_definitions WHERE id=?', (workflow_id,)).fetchone()
        if not row:
            _fail('workflow_not_found', '접근할 수 있는 절차가 없습니다.')
        try:
            self._work_authorize_scope(db, actor, groups, row['system_id'], '', 'manager' if manage else 'viewer')
        except WorkflowError:
            if manage:
                raise
            allowed = False
            for factory in db.execute('SELECT id FROM work_factories WHERE system_id=?', (row['system_id'],)):
                try:
                    self._work_authorize_scope(db, actor, groups, row['system_id'], factory['id'], 'viewer'); allowed = True; break
                except WorkflowError:
                    pass
            if not allowed:
                raise
        return row

    def _work_run(self, db, actor, groups, run_id, write=False):
        row = db.execute('SELECT * FROM work_runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            _fail('run_not_found', '접근할 수 있는 진행 건이 없습니다.')
        sharing = json.loads(row['sharing'])
        if row['owner'] != _value(actor, 'id') and not groups.intersection(sharing.get('group_ids', [])):
            _fail('run_not_found', '접근할 수 있는 진행 건이 없습니다.')
        self._work_authorize_scope(db, actor, groups, row['system_id'], row['factory_id'], 'participant' if write else 'viewer')
        if write and row['status'] in TERMINAL:
            _fail('run_closed', '종료된 진행 건은 기록으로 보존됩니다.')
        return row

    def _work_deadline(self, job, values):
        rule = job.get('deadline')
        if not rule:
            at = job.get('due_at')
            if not at: return {'at': None, 'calendar_status': 'unset', 'reason': 'deadline_unset'}
            try:
                due = datetime.fromisoformat(at.replace('Z', '+00:00'))
                if due.tzinfo is None: return {'at': None, 'calendar_status': 'unknown', 'reason': 'deadline_timezone_required'}
                now = datetime.fromtimestamp(self.operations.clock() if hasattr(self, 'operations') else datetime.now(timezone.utc).timestamp(), due.tzinfo)
                return {'at': due.isoformat(), 'days_remaining': (due.date() - now.date()).days, 'weekday': due.weekday(), 'calendar_status': 'configured', 'timezone': str(due.tzinfo)}
            except (ValueError, AttributeError, TypeError):
                return {'at': None, 'calendar_status': 'unknown', 'reason': 'deadline_invalid'}
        if rule.get('calendar') == 'business':
            return {'at': None, 'calendar_status': 'unknown', 'reason': 'business_calendar_unconfigured', 'timezone': rule.get('timezone'), 'input': rule.get('input')}
        raw = values.get(rule.get('input'))
        if not raw: return {'at': None, 'calendar_status': 'unknown', 'reason': 'deadline_input_required', 'input': rule.get('input')}
        try:
            zone = ZoneInfo(rule['timezone'])
            base = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            local = base.astimezone(zone) if base.tzinfo else base.replace(tzinfo=zone)
            due = local + timedelta(days=rule['offset_days'])
            now = datetime.fromtimestamp(self.operations.clock() if hasattr(self, 'operations') else datetime.now(timezone.utc).timestamp(), zone)
            return {'at': due.isoformat(), 'days_remaining': (due.date() - now.date()).days, 'weekday': due.weekday(), 'calendar_status': 'calendar_days', 'timezone': rule['timezone'], 'input': rule['input'], 'offset_days': rule['offset_days'], 'holidays_checked': False}
        except (ValueError, AttributeError, TypeError, ZoneInfoNotFoundError):
            return {'at': None, 'calendar_status': 'unknown', 'reason': 'deadline_invalid'}

    def _work_snapshot(self, db, run, job_id):
        saved = json.loads(run['snapshot'])
        definition = saved['definition']
        job = definition['nodes'].get(job_id)
        if not job or job.get('type') != 'j':
            _fail('job_not_found', '작업을 찾지 못했습니다.')
        values, sources = {}, {}
        for factory in ('', run['factory_id']):
            if factory == '' and '' in sources:
                continue
            setting = db.execute('SELECT * FROM work_settings WHERE workflow_id=? AND factory_id=?', (run['workflow_id'], factory)).fetchone()
            if setting:
                for key, value in json.loads(setting['values_json']).items():
                    values[key] = value
                    sources[key] = {'scope': 'factory' if factory else 'workflow', 'factory_id': factory, 'revision': setting['revision']}
        for key, value in json.loads(run['inputs']).items():
            values[key] = value; sources[key] = {'scope': 'run', 'revision': run['revision']}
        deadline = self._work_deadline(job, values)
        deadline_id = (job.get('deadline') or {}).get('input')
        deadline_source = {'input': deadline_id, 'value': deepcopy(values.get(deadline_id)), 'source': sources.get(deadline_id)} if deadline_id else None
        values = {field['id']: values[field['id']] for field in job.get('inputs', []) if field['id'] in values and (field.get('scope') != 'factory' or sources[field['id']]['scope'] == 'factory')}
        return {'job': deepcopy(job), 'definition': deepcopy(definition), 'version': run['version'],
                'definition_hash': saved['definition_hash'], 'factory': saved.get('factory'),
                'condition_results': saved.get('condition_results', {}), 'inputs': values,
                'settings_sources': {key: sources[key] for key in values},
                'tool_reference': deepcopy(job.get('tool_reference')), 'model_id': job.get('model_id'), 'deadline': deadline, 'deadline_source': deadline_source}

    @staticmethod
    def _work_dependent_ids(definition, job_id):
        nodes = definition['nodes']; impacted = {job_id}; changed = True
        while changed:
            changed = False
            for key, node in nodes.items():
                parents, parent = [], node.get('parent')
                while parent in nodes:
                    parents.append(parent); parent = nodes[parent].get('parent')
                deps = set(node.get('deps', []))
                for parent in parents:
                    deps.update(nodes[parent].get('deps', []))
                expanded = set(deps)
                for dep in deps:
                    stack = [dep]
                    while stack:
                        item = stack.pop(); expanded.add(item); stack.extend(nodes.get(item, {}).get('children', []))
                if key not in impacted and expanded & impacted:
                    impacted.add(key); changed = True
        return impacted - {job_id}

    def _work_dependencies_ready(self, db, run_id, definition, job_id):
        node = definition['nodes'][job_id]
        resolved_policy = node.get('dependency_policy') == 'all_resolved' and node.get('mode') == 'ai' and node.get('result_block') == 'ai_review'
        run = db.execute('SELECT * FROM work_runs WHERE id=?', (run_id,)).fetchone()
        for dependency in self._work_prerequisite_jobs(definition, job_id):
            job = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (run_id, dependency)).fetchone()
            if not job: return False
            if job['reason'] == 'delivery_unconfigured': return False
            if job['status'] == 'completed': continue
            if not resolved_policy or not job['current_attempt']: return False
            attempt = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
            current = self._work_snapshot(db, run, dependency)
            prior = json.loads(attempt['snapshot']) if attempt else {}
            if not attempt or attempt['status'] not in ('succeeded', 'partial', 'waiting_confirmation') or json.loads(attempt['inputs']) != current['inputs'] or (prior.get('deadline_source') or {}).get('value') != (current.get('deadline_source') or {}).get('value') or not self._work_sources_current(db, run, prior):
                return False
            result = json.loads(attempt['result']) if attempt['result'] else {}
            items = result.get('items', []) if isinstance(result, dict) else []
            required = {str(item['id']) for item in items if isinstance(item, dict) and 'id' in item and item.get('required', True)} or {'job'}
            decisions = {row['item_id'] for row in db.execute('SELECT item_id FROM work_decisions WHERE run_id=? AND job_id=? AND attempt_id=?', (run_id, dependency, attempt['id']))}
            if not required <= decisions: return False
        return True

    def _work_prerequisite_sources(self, db, run, job_id):
        """Bind every transitive prerequisite to the evidence used at start.

        A later upstream retry can happen while this job is in flight. Keep
        the actual result, but never let it confirm a newly changed source.
        Claim/release and unrelated run revisions do not change these values.
        """
        definition = json.loads(run['snapshot'])['definition']
        pending = list(self._work_prerequisite_jobs(definition, job_id)); sources = {}
        while pending:
            source_id = pending.pop()
            if source_id in sources: continue
            row = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (run['id'], source_id)).fetchone()
            if not row: continue
            snapshot = self._work_snapshot(db, run, source_id)
            decisions = [item['id'] for item in db.execute('SELECT id FROM work_decisions WHERE run_id=? AND job_id=? AND attempt_id=? ORDER BY id', (run['id'], source_id, row['current_attempt']))]
            sources[source_id] = {'attempt_id': row['current_attempt'], 'status': row['status'], 'decision_ids': decisions,
                                  'input_hash': _hash({'inputs': snapshot['inputs'], 'deadline_value': (snapshot.get('deadline_source') or {}).get('value')})}
            pending.extend(self._work_prerequisite_jobs(definition, source_id))
        return sources

    def _work_sources_current(self, db, run, snapshot):
        return snapshot.get('prerequisite_sources', {}) == self._work_prerequisite_sources(db, run, snapshot['job']['id'])

    def _work_job_due(self, db, run, job):
        trigger = job.get('trigger', {})
        if not trigger: return None
        if 'at' in trigger:
            return datetime.fromisoformat(trigger['at'].replace('Z', '+00:00')).timestamp()
        anchor = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')).timestamp()
        slot = db.execute("SELECT scheduled_at FROM work_schedule_slots WHERE json_extract(data,'$.run_id')=? ORDER BY scheduled_at LIMIT 1", (run['id'],)).fetchone()
        if slot: anchor = slot['scheduled_at']
        return anchor + trigger['offset_seconds']

    def _work_begin_attempt(self, db, actor, groups, run_id, job_id, expected_revision, inputs=None, options_snapshot=None):
        run = self._work_run(db, actor, groups, run_id, write=True)
        _revision({'expected_revision': expected_revision}, run['revision'])
        job_row = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (run_id, job_id)).fetchone()
        if not job_row or job_row['status'] == 'excluded':
            _fail('job_unavailable', '실행할 수 있는 작업이 아닙니다.')
        if job_row['status'] == 'running':
            _fail('execution_overlap', '이 작업의 실행 결과를 먼저 확인해 주세요.')
        if job_row['claim_actor'] and job_row['claim_actor'] != _value(actor, 'id'):
            _fail('task_claimed', '다른 담당자가 처리 중입니다.')
        snapshot = self._work_snapshot(db, run, job_id)
        if snapshot['condition_results'].get(job_id) is None:
            _fail('factory_condition_unknown', '공장 속성을 확인한 뒤 새 진행 건을 시작해 주세요.')
        if inputs is not None:
            _fail('input_save_required', '이번 입력을 먼저 저장한 뒤 실행해 주세요.')
        job = snapshot['job']
        if not self._work_dependencies_ready(db, run_id, snapshot['definition'], job_id):
            _fail('prerequisite_required', '필수 선행 작업과 필요한 판정을 먼저 해결해 주세요.')
        due = self._work_job_due(db, run, job)
        now_seconds = self.operations.clock() if hasattr(self, 'operations') else datetime.now(timezone.utc).timestamp()
        if due is not None and due > now_seconds:
            _fail('scheduled_time_required', '정해진 실행 시각이 되면 진행할 수 있습니다.')
        for field_id, record in (options_snapshot or {}).items():
            context = record.get('context', {})
            if context.get('run_id') != run_id or context.get('job_id') != job_id or context.get('revision') != run['revision'] or context.get('input_hash') != _hash(snapshot['inputs']) or context.get('authorization_hash') != self._work_options_authority(db, actor, groups, run['system_id']):
                _fail('options_context_changed', '입력이 바뀌었습니다. 선택지를 다시 확인해 주세요.')
        errors = input_errors(job.get('inputs', []), snapshot['inputs'], options_snapshot=options_snapshot)
        if errors:
            _fail('input_required', '\n'.join(errors))
        number = db.execute('SELECT COALESCE(MAX(number),0)+1 FROM work_attempts WHERE run_id=? AND job_id=?', (run_id, job_id)).fetchone()[0]
        attempt_id = str(uuid4()); actor_id = _value(actor, 'id'); now = _now()
        snapshot['actor_id'] = actor_id
        snapshot['options'] = deepcopy(options_snapshot or {})
        snapshot['prerequisite_sources'] = self._work_prerequisite_sources(db, run, job_id)
        db.execute('INSERT INTO work_attempts VALUES(?,?,?,?,?,?,?,?,NULL,?,NULL)',
                   (attempt_id, run_id, job_id, number, actor_id, _dump(snapshot['inputs']), _dump(snapshot), 'running', now))
        db.execute("UPDATE work_jobs SET status='running',revision=revision+1,current_attempt=?,claim_actor=?,reason='' WHERE run_id=? AND job_id=?", (attempt_id, actor_id, run_id, job_id))
        for dependent in self._work_dependent_ids(snapshot['definition'], job_id):
            db.execute("UPDATE work_jobs SET status='review_required',revision=revision+1,reason='선행 작업 재실행' WHERE run_id=? AND job_id=? AND status NOT IN ('excluded','running')", (run_id, dependent))
        db.execute('UPDATE work_runs SET revision=revision+1,updated_at=? WHERE id=?', (now, run_id))
        return {'id': attempt_id, 'run_id': run_id, 'job_id': job_id, 'number': number, 'actor_id': actor_id, 'inputs': snapshot['inputs'], 'snapshot': snapshot, 'status': 'running', 'revision': run['revision'] + 1}

    @staticmethod
    def _work_prerequisite_jobs(definition, job_id):
        nodes = definition['nodes']; deps = set(); current = job_id
        while current in nodes:
            deps.update(nodes[current].get('deps', [])); current = nodes[current].get('parent')
        jobs, seen = set(), set()
        while deps:
            key = deps.pop()
            if key in seen: continue
            seen.add(key)
            node = nodes.get(key, {})
            if node.get('type') == 'j': jobs.add(key)
            else: deps.update(node.get('children', []))
        return jobs

    def _work_finish_attempt(self, db, attempt_id, status, result):
        if status not in ('succeeded', 'failed', 'partial', 'unknown', 'blocked', 'waiting_confirmation', 'cancelled'):
            _fail('invalid_result', '실행 결과 상태를 확인해 주세요.')
        _public(result)
        row = db.execute('SELECT * FROM work_attempts WHERE id=?', (attempt_id,)).fetchone()
        if not row or row['status'] != 'running':
            _fail('attempt_finished', '이미 기록된 실행 결과는 바꿀 수 없습니다.')
        job = json.loads(row['snapshot'])['job']
        state = ('waiting_confirmation' if job.get('human_confirmation', True) or job.get('result_block') == 'item_verdict' or (job.get('mode') == 'ai' and job.get('result_block') == 'ai_review') else 'completed') if status == 'succeeded' else status
        run = db.execute('SELECT * FROM work_runs WHERE id=?', (row['run_id'],)).fetchone()
        current_snapshot = self._work_snapshot(db, run, row['job_id'])
        current_inputs = current_snapshot['inputs']
        prior_snapshot = json.loads(row['snapshot'])
        deadline_changed = (prior_snapshot.get('deadline_source') or {}).get('value') != (current_snapshot.get('deadline_source') or {}).get('value')
        if state in ('completed', 'waiting_confirmation') and (current_inputs != json.loads(row['inputs']) or deadline_changed or not self._work_sources_current(db, run, prior_snapshot)):
            state = 'review_required'
        now = _now()
        db.execute('UPDATE work_attempts SET status=?,result=?,finished_at=? WHERE id=? AND status=\'running\'', (status, _dump(result), now, attempt_id))
        db.execute('UPDATE work_jobs SET status=?,revision=revision+1 WHERE run_id=? AND job_id=? AND current_attempt=?', (state, row['run_id'], row['job_id'], attempt_id))
        db.execute('UPDATE work_runs SET revision=revision+1,updated_at=? WHERE id=?', (now, row['run_id']))
        return {'attempt_id': attempt_id, 'status': state, 'result': deepcopy(result)}

    @staticmethod
    def _work_evidence_references(snapshot):
        references = []
        if snapshot.get('tool_reference'):
            references.append(snapshot['tool_reference'])
        references.extend(record['source']['reference'] for record in snapshot.get('options', {}).values() if record.get('source', {}).get('kind') == 'tool')
        references.extend(snapshot.get('source_references', []))
        return references

    async def _work_check_evidence(self, actor, attempt):
        snapshot = json.loads(attempt['snapshot']) if isinstance(attempt['snapshot'], str) else attempt['snapshot']
        if attempt['actor_id'] != _value(actor, 'id'):
            _fail('evidence_access_required', '본인 권한으로 근거를 다시 조회해 주세요.')
        refs = self._work_evidence_references(snapshot)
        if snapshot['job'].get('mode') == 'ai' and self._work_prerequisite_jobs(snapshot['definition'], snapshot['job']['id']) and not snapshot.get('evidence_attempt_ids'):
            _fail('evidence_access_required', '근거의 권한을 다시 조회해 주세요.')
        bridge = getattr(getattr(self, 'operations', None), 'bridge', None) or getattr(getattr(self, 'execution', None), 'bridge', None)
        for ref in refs:
            if not bridge or not hasattr(bridge, 'check'):
                _fail('evidence_access_required', '현재 Native 원본 접근권한을 확인해 주세요.')
            reference = deepcopy(ref); reference.pop('contract_id', None)
            await bridge.check(actor, reference)

    async def _work_evidence_access(self, actor, groups, run_id=''):
        allowed, records = set(), []
        with self._db() as db:
            for run in db.execute('SELECT * FROM work_runs' + (' WHERE id=?' if run_id else ''), (run_id,) if run_id else ()):
                try: self._work_run(db, actor, groups, run['id'])
                except WorkflowError: continue
                records.extend(dict(row) for row in db.execute('SELECT * FROM work_attempts WHERE run_id=? AND actor_id=?', (run['id'], _value(actor, 'id'))))
        for attempt in records:
            try:
                await self._work_check_evidence(actor, attempt)
                allowed.add(attempt['id'])
            except Exception:
                pass
        return allowed

    def _work_run_view(self, db, actor, groups, row, evidence_access=None):
        value = dict(row)
        value['can_write'], value['permission_reason'] = True, ''
        try:
            self._work_run(db, actor, groups, row['id'], write=True)
        except WorkflowError as error:
            value['can_write'], value['permission_reason'] = False, error.code
        request_roles = {}
        for role in ('requester', 'reviewer'):
            try:
                self._work_authorize_scope(db, actor, groups, row['system_id'], row['factory_id'], role)
                request_roles[role] = True
            except WorkflowError:
                request_roles[role] = False
        value['sharing'] = json.loads(value['sharing']); value['inputs'] = json.loads(value['inputs'])
        snapshot = json.loads(value.pop('snapshot')); value.update(snapshot)
        jobs = {item['job_id']: dict(item) for item in db.execute('SELECT * FROM work_jobs WHERE run_id=?', (row['id'],))}
        attempts = []
        for attempt in db.execute('SELECT * FROM work_attempts WHERE run_id=? ORDER BY job_id,number', (row['id'],)):
            item = dict(attempt); item['snapshot'] = json.loads(item['snapshot']); item['inputs'] = json.loads(item['inputs'])
            item['result'] = json.loads(item['result']) if item['result'] else None
            # Native/external source permission is not inherited from sharing a
            # run. Until re-fetched as this actor, evidence stays actor-private.
            if (item['snapshot']['job'].get('mode') != 'human' or self._work_evidence_references(item['snapshot'])) and (item['actor_id'] != _value(actor, 'id') or item['id'] not in (evidence_access or set())):
                item['result'] = None; item['inputs'] = {}; item['snapshot'] = {'job': item['snapshot']['job']}
                item['evidence_access'] = 'requires_current_source_access'
            item['review_history'] = [] if item.get('evidence_access') else [dict(record) for record in db.execute('SELECT * FROM work_review_revisions WHERE attempt_id=? ORDER BY revision', (item['id'],))]
            attempts.append(item)
        for job in jobs.values():
            current = next((item for item in attempts if item['id'] == job['current_attempt']), None)
            node = value['definition']['nodes'][job['job_id']]
            job['can_execute'], job['permission_reason'] = value['can_write'], value['permission_reason']
            assignee = node.get('assignee')
            assigned = not assignee or assignee.get('id') in ({_value(actor, 'id')} if assignee.get('kind') == 'user' else groups)
            if node.get('mode', 'human') == 'human' and not assigned:
                job['can_execute'], job['permission_reason'] = False, 'assignee_required'
            if job['claim_actor'] and job['claim_actor'] != _value(actor, 'id'):
                job['can_execute'], job['permission_reason'] = False, 'task_claimed'
            job['can_decide'] = bool(job['can_execute'] and assigned and (not current or not current.get('evidence_access')))
            # Request preparation/approval/status lookup have distinct existing
            # server roles; an approver need not be the current job claimant.
            job['can_request'] = bool(value['can_write'] and request_roles['requester'])
            job['can_review_request'] = bool(value['can_write'] and request_roles['reviewer'])
            job['can_reconcile'] = request_roles['requester']
            job['can_manage_settings'] = True
            try:
                self._work_authorize_scope(db, actor, groups, row['system_id'], row['factory_id'], 'manager')
            except WorkflowError:
                job['can_manage_settings'] = False
            job['review_draft'] = deepcopy(current['review_history'][-1]) if current and current.get('review_history') else None
            job['result_revision'] = current['number'] if current else None
            effective = ({'inputs': current['inputs'], 'settings_sources': current.get('snapshot', {}).get('settings_sources', {}), 'deadline': current.get('snapshot', {}).get('deadline')} if row['status'] in TERMINAL and current else self._work_snapshot(db, row, job['job_id']))
            job['effective_inputs'] = effective['inputs']
            job['deadline'] = effective.get('deadline')
            job['settings_sources'] = effective['settings_sources']
            job['missing_inputs'] = input_errors(value['definition']['nodes'][job['job_id']].get('inputs', []), effective['inputs'], options_snapshot=(current or {}).get('snapshot', {}).get('options'))
            job['result_stale'] = bool(row['status'] not in TERMINAL and current and current['actor_id'] == _value(actor, 'id') and not current.get('evidence_access') and (current['inputs'] != effective['inputs'] or (current['snapshot'].get('deadline_source') or {}).get('value') != (effective.get('deadline_source') or {}).get('value') or not self._work_sources_current(db, row, current['snapshot'])))
            job['decisions'] = [dict(item) for item in db.execute('SELECT * FROM work_decisions WHERE run_id=? AND job_id=? ORDER BY created_at,id', (row['id'], job['job_id']))]
        for job in jobs.values():
            current_decisions = [item for item in job['decisions'] if item['attempt_id'] == job['current_attempt']]
            job['decision_summary'] = {'confirmed': len(current_decisions), 'all_approved': job['status'] == 'completed' and bool(current_decisions) and all(item['verdict'] == 'completed' for item in current_decisions)}
        value['jobs'], value['attempts'] = jobs, attempts
        value['progress'] = {'completed': sum(item['status'] == 'completed' for item in jobs.values()),
                             'total': sum(item['status'] != 'excluded' for item in jobs.values()),
                             'excluded': sum(item['status'] == 'excluded' for item in jobs.values())}
        value['chat_links'] = [item['chat_id'] for item in db.execute('SELECT chat_id FROM work_chat_links WHERE actor_id=? AND run_id=?', (_value(actor, 'id'), row['id']))]
        return value

    def _work_workflow_view(self, db, actor, groups, row):
        value = {key: row[key] for key in ('id', 'system_id', 'revision', 'published_version', 'created_by', 'updated_at')}
        try:
            self._work_authorize_scope(db, actor, groups, row['system_id'], '', 'manager')
            value['draft'] = json.loads(row['draft']); value['can_manage'] = True
            value['validation'] = json.loads(row['validation']) if row['validation'] else None
        except WorkflowError:
            value['can_manage'] = False
        versions = list(db.execute('SELECT * FROM work_versions WHERE workflow_id=? ORDER BY version DESC', (row['id'],)))
        value['versions'] = [{**{key: version[key] for key in ('version', 'hash', 'publisher', 'published_at')}, 'definition': json.loads(version['definition'])} for version in versions]
        value['published'] = json.loads(versions[0]['definition']) if versions else None
        value['name'] = (value.get('draft') or value['published'] or {}).get('name', '')
        value['mode'] = (value.get('draft') or value['published'] or {}).get('mode', 'on_demand')
        value['execution_scope'] = (value.get('draft') or value['published'] or {}).get('execution_scope')
        value['category'] = (value.get('draft') or value['published'] or {}).get('category', 'ops')
        value['settings'] = []
        for setting in db.execute('SELECT * FROM work_settings WHERE workflow_id=?', (row['id'],)):
            try:
                self._work_authorize_scope(db, actor, groups, row['system_id'], setting['factory_id'], 'viewer')
            except WorkflowError:
                continue
            value['settings'].append({'factory_id': setting['factory_id'], 'values': json.loads(setting['values_json']), 'revision': setting['revision']})
        return value

    def _work_my_work(self, db, actor, groups, runs):
        items = []; now = datetime.now(timezone.utc); today = now.date()
        for run in runs:
            if run['status'] in TERMINAL:
                continue
            definition = run['definition']
            for key, job in run['jobs'].items():
                if not job.get('can_execute', True):
                    continue
                node = definition['nodes'][key]
                if job['claim_actor'] and job['claim_actor'] != _value(actor, 'id'):
                    continue
                assigned = node.get('assignee')
                if assigned and assigned.get('id') not in ({_value(actor, 'id')} if assigned.get('kind') == 'user' else groups):
                    continue
                actionable = bool(job.get('missing_inputs') and job['status'] == 'pending') or job['status'] in ('waiting_input', 'waiting_confirmation', 'review_required', 'failed', 'partial', 'unknown', 'blocked', 'missed') or (node.get('mode', 'human') == 'human' and job['status'] == 'pending')
                if not actionable:
                    continue
                if not self._work_dependencies_ready(db, run['id'], definition, key):
                    continue
                due = (job.get('deadline') or {}).get('at'); bucket = 'incident' if run['mode'] == 'emergency' else 'undated'
                if due and bucket != 'incident':
                    try:
                        due_time = datetime.fromisoformat(due.replace('Z', '+00:00'))
                        local_today = datetime.fromtimestamp(self.operations.clock() if hasattr(self, 'operations') else now.timestamp(), due_time.tzinfo or timezone.utc).date()
                        date = due_time.date()
                        bucket = 'overdue' if date < local_today else 'today' if date == local_today else 'week' if date <= local_today + timedelta(days=6 - local_today.weekday()) else 'future'
                    except (ValueError, AttributeError):
                        bucket = 'undated'
                items.append({'id': run['id'] + ':' + key, 'run_id': run['id'], 'workflow_id': run['workflow_id'],
                              'job_id': key, 'name': node['name'], 'workflow_name': definition['name'], 'system_id': run['system_id'],
                              'factory_id': run['factory_id'], 'status': job['status'], 'bucket': bucket, 'due_at': due,
                              'order': list(definition['nodes']).index(key), 'claim_actor': job['claim_actor'], 'revision': run['revision']})
        priority = {key: index for index, key in enumerate(('incident', 'overdue', 'today', 'week', 'future', 'undated'))}
        return sorted(items, key=lambda item: (priority[item['bucket']], item['due_at'] or '9999', item['order'], item['id']))

    @staticmethod
    def _work_options_authority(db, actor, groups, system_id):
        grants = [dict(row) for row in db.execute('SELECT * FROM work_access WHERE system_id=? AND active=1 ORDER BY id', (system_id,)) if row['principal_id'] in ({_value(actor, 'id')} if row['principal_kind'] == 'user' else groups)]
        owners = [dict(row) for row in db.execute('SELECT * FROM system_groups WHERE system_id=? AND active=1', (system_id,)) if row['group_id'] in groups]
        return _hash({'actor': _value(actor, 'id'), 'role': _value(actor, 'role'), 'groups': sorted(groups), 'grants': grants, 'owners': owners})

    def _work_options_context(self, db, actor, groups, body):
        run_id, workflow_id, job_id, field_id = (body.get(key, '') for key in ('run_id', 'workflow_id', 'job_id', 'field_id'))
        if run_id:
            run = self._work_run(db, actor, groups, run_id)
            if workflow_id and workflow_id != run['workflow_id']:
                _fail('options_context_changed', '진행 건과 절차가 다릅니다.')
            snapshot = self._work_snapshot(db, run, job_id)
            definition, values = snapshot['definition'], snapshot['inputs']
            workflow_id, revision, factory_id = run['workflow_id'], run['revision'], run['factory_id']
        else:
            row = self._work_definition(db, actor, groups, workflow_id)
            try:
                self._work_authorize_scope(db, actor, groups, row['system_id'], '', 'manager')
                definition = json.loads(row['draft'])
            except WorkflowError:
                published = db.execute('SELECT definition FROM work_versions WHERE workflow_id=? AND version=?', (workflow_id, row['published_version'])).fetchone()
                if not published: _fail('publication_required', '게시된 절차를 선택해 주세요.')
                definition = json.loads(published['definition'])
            revision, factory_id, values = row['revision'], body.get('factory_id', ''), {}
            self._work_authorize_scope(db, actor, groups, row['system_id'], factory_id, 'viewer')
            for scope in ('', factory_id):
                setting = db.execute('SELECT values_json FROM work_settings WHERE workflow_id=? AND factory_id=?', (workflow_id, scope)).fetchone()
                if setting: values.update(json.loads(setting['values_json']))
        node = definition['nodes'].get(job_id)
        if not node or node.get('type') != 'j': _fail('job_not_found', '선택지를 조회할 작업을 확인해 주세요.')
        fields = {field['id']: field for field in node.get('inputs', [])}
        field = fields.get(field_id)
        if not field or field.get('type') not in ('single', 'multi'):
            _fail('field_not_found', '선택 입력을 확인해 주세요.')
        supplied = body.get('inputs', {})
        if not isinstance(supplied, dict) or any(key not in fields for key in supplied):
            _fail('invalid_inputs', '이 작업에 선언된 입력만 조회에 사용할 수 있습니다.')
        values.update(deepcopy(supplied))
        values = {key: value for key, value in values.items() if key in fields}
        errors = input_errors(list(fields.values()), values, complete=False)
        if errors: _fail('invalid_inputs', '\n'.join(errors))
        context = {'workflow_id': workflow_id, 'run_id': run_id, 'job_id': job_id, 'field_id': field_id,
                   'revision': revision, 'input_hash': _hash(values), 'system_id': definition['system_id'], 'factory_id': factory_id,
                   'authorization_hash': self._work_options_authority(db, actor, groups, definition['system_id'])}
        return field, values, context

    async def _work_input_options(self, user, body):
        actor, capabilities, groups = await self._work_actor(user)
        _public(body)
        with self._db() as db:
            field, values, context = self._work_options_context(db, actor, groups, body)
        source = field.get('options_source', 'manual')
        query = field.get('options_query', {})
        reference = None
        if source == 'manual':
            options = [{'id': item.get('id'), 'name': item.get('name', str(item.get('id')))} if isinstance(item, dict) else {'id': item, 'name': str(item)} for item in field.get('options', [])]
            provenance = {'kind': 'manual', 'definition_revision': context['revision']}
        elif not _options_query_valid(field):
            _fail('options_unconfigured', '현재 권한으로 조회하는 선택지 연결이 구성되지 않았습니다.')
        elif source == 'common':
            options = []
            if query['kind'] == 'groups':
                options = [{'id': group['id'], 'name': group['name']} for group in await self._native_groups() if capabilities['is_admin'] or group['id'] in groups]
            else:
                with self._db() as db:
                    if query['kind'] == 'systems':
                        options = [{'id': system, 'name': system} for system in (*SYSTEMS, 'COMMON') if self._work_system_visible(db, actor, groups, system)]
                    else:
                        for row in db.execute('SELECT id,name,system_id FROM work_factories WHERE system_id=? ORDER BY name,id', (context['system_id'],)):
                            try:
                                self._work_authorize_scope(db, actor, groups, row['system_id'], row['id'], 'viewer')
                                options.append({'id': row['id'], 'name': row['name']})
                            except WorkflowError: pass
            provenance = {'kind': 'common', 'registry': query['kind']}
        else:
            bridge = getattr(getattr(self, 'operations', None), 'bridge', None) or getattr(getattr(self, 'execution', None), 'bridge', None)
            if bridge is None or not hasattr(bridge, 'invoke'):
                _fail('options_unconfigured', 'Native 조회 연결이 준비되지 않았습니다.')
            reference, arguments = deepcopy(query['reference']), {}
            for name, binding in query.get('argument_bindings', {}).items():
                if 'constant' in binding:
                    arguments[name] = deepcopy(binding['constant'])
                elif binding['input'] not in values or values[binding['input']] in (None, '', []):
                    _fail('options_dependency_required', '선택지의 선행 입력을 먼저 선택해 주세요.')
                else:
                    arguments[name] = deepcopy(values[binding['input']])
            await bridge.check(actor, reference)
            result = await bridge.invoke(actor, reference, arguments, {'run_id': context['run_id'], 'job_id': context['job_id'], 'call_id': 'options-' + uuid4().hex})
            if not isinstance(result, dict) or result.get('status') != 'succeeded' or result.get('completeness') not in ('complete', 'empty'):
                _fail('options_unavailable', '선택지 조회가 실패하거나 일부만 반환되었습니다. 다시 확인해 주세요.')
            items = result.get('data')
            for key in query['result_path']:
                if not isinstance(items, dict) or key not in items:
                    _fail('options_contract_changed', '선택지 응답의 선언된 경로를 확인해 주세요.')
                items = items[key]
            if not isinstance(items, list) or len(items) > 1000:
                _fail('options_contract_changed', '선택지 목록 크기와 응답 형식을 확인해 주세요.')
            options = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get(query['value_field']), (str, int)) or isinstance(item.get(query['value_field']), bool) or not isinstance(item.get(query['label_field']), str):
                    _fail('options_contract_changed', '선택지 ID와 표시 이름을 확인해 주세요.')
                options.append({'id': item[query['value_field']], 'name': item[query['label_field']]})
            if len({str(item['id']) for item in options}) != len(options):
                _fail('options_contract_changed', '중복된 선택지 ID가 반환되었습니다.')
            provenance = {'kind': 'tool', 'reference': reference, 'arguments_hash': _hash(arguments), 'queried_at': _now()}
        # No private data or stale dependency response crosses a scope change.
        actor, capabilities, groups = await self._work_actor(actor)
        if reference:
            await bridge.check(actor, reference)
        with self._db() as db:
            _, _, latest = self._work_options_context(db, actor, groups, body)
            if latest != context:
                _fail('options_context_changed', '작업이나 입력이 바뀌었습니다. 선택지를 다시 조회해 주세요.')
        return {'ok': True, 'options': options, 'source': provenance, 'context': context}

    async def input_options(self, user, body):
        try:
            if not isinstance(body, dict): _fail('invalid_inputs', '선택지 조회 대상을 확인해 주세요.')
            return await self._work_input_options(user, body)
        except WorkflowError as error:
            return {'ok': False, 'error': {'code': error.code, 'message': error.message}}
        except Exception:
            return {'ok': False, 'error': {'code': 'options_unavailable', 'message': '선택지 조회를 완료하지 못했습니다.'}}

    async def _work_resolve_job_options(self, user, run_id, job_id):
        actor, _, groups = await self._work_actor(user)
        with self._db() as db:
            run = self._work_run(db, actor, groups, run_id)
            fields = self._work_snapshot(db, run, job_id)['job'].get('inputs', [])
        results = {}
        for field in fields:
            if field.get('options_source', 'manual') != 'manual':
                result = await self._work_input_options(actor, {'run_id': run_id, 'job_id': job_id, 'field_id': field['id']})
                results[field['id']] = {key: result[key] for key in ('options', 'source', 'context')}
        return results

    async def _work_people(self, actor, capabilities, groups):
        native_groups = await self._native_groups()
        native_groups = [group for group in native_groups if capabilities['is_admin'] or group['id'] in groups]
        user_ids = {_value(actor, 'id')}
        with self._db() as db:
            for row in db.execute("SELECT DISTINCT principal_id,system_id,factory_id FROM work_access WHERE active=1 AND principal_kind='user'"):
                try:
                    self._work_authorize_scope(db, actor, groups, row['system_id'], '' if row['factory_id'] == '*' else row['factory_id'], 'viewer')
                    user_ids.add(row['principal_id'])
                except WorkflowError:
                    pass
        people = []
        for user_id in sorted(user_ids):
            person = await _resolve(self.user_lookup(user_id))
            if person and _value(person, 'role') in ('admin', 'user'):
                name = _value(person, 'name', user_id)
                people.append({'id': user_id, 'name': name, 'label': name, 'value': {'kind': 'user', 'id': user_id}})
        people.extend({'id': group['id'], 'name': group['name'], 'label': group['name'], 'value': {'kind': 'group', 'id': group['id']}} for group in native_groups)
        return people, native_groups

    async def workspace_state(self, user, workflow_id='', run_id='', system_id='', factory_id=''):
        try:
            actor, capabilities, groups = await self._work_actor(user)
            people, native_groups = await self._work_people(actor, capabilities, groups)
            evidence_access = await self._work_evidence_access(actor, groups)
            actor, capabilities, groups = await self._work_actor(actor)
            with self._db() as db:
                if system_id:
                    if factory_id:
                        self._work_authorize_scope(db, actor, groups, system_id, factory_id, 'viewer')
                    elif not self._work_system_visible(db, actor, groups, system_id):
                        _fail('scope_forbidden', '이 작업 위치의 권한이 없습니다.')
                factories, systems, workflows, runs, workflow_active_runs = [], [], [], [], []
                for system in (*SYSTEMS, 'COMMON'):
                    try:
                        if factory_id:
                            self._work_authorize_scope(db, actor, groups, system, factory_id, 'viewer')
                        elif not self._work_system_visible(db, actor, groups, system):
                            continue
                        systems.append(system)
                    except WorkflowError:
                        pass
                for row in db.execute('SELECT * FROM work_factories ORDER BY name,id'):
                    try:
                        self._work_authorize_scope(db, actor, groups, row['system_id'], row['id'], 'viewer')
                    except WorkflowError:
                        continue
                    if system_id and row['system_id'] != system_id: continue
                    item = dict(row); item['attributes'] = json.loads(item['attributes']); factories.append(item)
                for row in db.execute('SELECT * FROM work_definitions ORDER BY updated_at DESC,id'):
                    if system_id and row['system_id'] != system_id: continue
                    try:
                        if factory_id:
                            self._work_authorize_scope(db, actor, groups, row['system_id'], factory_id, 'viewer')
                        elif not self._work_system_visible(db, actor, groups, row['system_id']):
                            continue
                        item = self._work_workflow_view(db, actor, groups, row)
                        if item['can_manage'] or item['published_version'] is not None: workflows.append(item)
                    except WorkflowError:
                        continue
                for row in db.execute('SELECT * FROM work_runs ORDER BY created_at DESC,id'):
                    if workflow_id and row['workflow_id'] == workflow_id and row['status'] not in TERMINAL:
                        try:
                            self._work_run(db, actor, groups, row['id'])
                            workflow_active_runs.append({key: row[key] for key in ('id', 'workflow_id', 'system_id', 'factory_id', 'owner', 'status', 'version', 'revision', 'created_at')})
                        except WorkflowError:
                            pass
                    system_scope = json.loads(row['snapshot'])['definition'].get('execution_scope') == 'system'
                    if system_id and row['system_id'] != system_id or factory_id and row['factory_id'] != factory_id and not system_scope: continue
                    try:
                        self._work_run(db, actor, groups, row['id'])
                    except WorkflowError:
                        continue
                    runs.append(self._work_run_view(db, actor, groups, row, evidence_access))
                selected_workflow = None
                if workflow_id:
                    selected_workflow = self._work_workflow_view(db, actor, groups, self._work_definition(db, actor, groups, workflow_id))
                selected_run = None
                if run_id:
                    selected_run = self._work_run_view(db, actor, groups, self._work_run(db, actor, groups, run_id), evidence_access)
                if (selected_workflow and system_id and selected_workflow['system_id'] != system_id
                        or selected_run and (workflow_id and selected_run['workflow_id'] != workflow_id
                                             or system_id and selected_run['system_id'] != system_id
                                             or factory_id and selected_run['factory_id'] != factory_id and selected_run['definition'].get('execution_scope') != 'system')):
                    _fail('target_mismatch', '선택한 절차·진행 건·작업 위치가 서로 다릅니다. 대상을 다시 선택해 주세요.')
                if factory_id and selected_workflow:
                    factory = db.execute('SELECT system_id FROM work_factories WHERE id=?', (factory_id,)).fetchone()
                    if not factory or factory['system_id'] != selected_workflow['system_id']:
                        _fail('target_mismatch', '선택한 공장과 절차의 시스템이 다릅니다. 작업 위치를 다시 선택해 주세요.')
                ui = db.execute('SELECT * FROM work_ui WHERE actor_id=?', (_value(actor, 'id'),)).fetchone()
                my_work = self._work_my_work(db, actor, groups, runs)
                capabilities['managed_systems'] = []
                for system in systems:
                    try:
                        self._work_authorize_scope(db, actor, groups, system, '', 'manager'); capabilities['managed_systems'].append(system)
                    except WorkflowError: pass
                capabilities['can_author'] = bool(capabilities['managed_systems'])
                access = [dict(row) | {'roles': json.loads(row['roles'])} for row in db.execute('SELECT * FROM work_access ORDER BY id')] if capabilities['is_admin'] else []
                return {'ok': True, 'protocol': 2, 'help': workflow_help(), 'capabilities': capabilities, 'systems': systems, 'factories': factories,
                        'workflows': workflows, 'runs': runs, 'workflow': selected_workflow, 'run': selected_run,
                        'workflow_active_runs': workflow_active_runs,
                        'my_work': my_work, 'my_work_count': len(my_work), 'access': access, 'people': people, 'native_groups': native_groups,
                        'ui_state': {'revision': ui['revision'], 'state': json.loads(ui['state'])} if ui else {'revision': 0, 'state': {}},
                        'legacy_count': db.execute('SELECT COUNT(*) FROM cases WHERE owner=?', (_value(actor, 'id'),)).fetchone()[0]}
        except WorkflowError as error:
            return {'ok': False, 'error': {'code': error.code, 'message': error.message}}
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return {'ok': False, 'error': {'code': 'workspace_unavailable', 'message': '업무 저장 상태를 확인하지 못했습니다. 기존 자료를 초기화하지 않았습니다.'}}

    async def workspace_export(self, user, run_id):
        if not isinstance(run_id, str) or not run_id:
            return {'ok': False, 'error': {'code': 'run_not_found', 'message': '내보낼 진행 건을 선택해 주세요.'}}
        state = await self.workspace_state(user, run_id=run_id)
        if not state.get('ok'):
            return state
        run = deepcopy(state['run'])
        run.pop('chat_links', None)
        return {'ok': True, 'format': 'ees-work-run', 'schema': 1, 'exported_at': _now(), 'run': run}

    async def _work_validate_people(self, value):
        if isinstance(value, list):
            for child in value:
                await self._work_validate_people(child)
        elif isinstance(value, dict):
            if set(value) == {'kind', 'id'} and value.get('kind') in ('user', 'group'):
                if value['kind'] == 'user':
                    person = await _resolve(self.user_lookup(value['id']))
                    if not person or _value(person, 'role') not in ('user', 'admin') or _value(person, 'id') != value['id']:
                        _fail('native_user_required', '현재 승인된 Native 사용자를 선택해 주세요.')
                else:
                    groups = await self._native_groups()
                    if value['id'] not in {group['id'] for group in groups}:
                        _fail('native_group_required', '현재 Native 그룹을 선택해 주세요.')
            else:
                for child in value.values():
                    await self._work_validate_people(child)

    def _work_receipt_authorize(self, db, actor, groups, body, response, evidence_access=None):
        if response.get('run_id'):
            run = self._work_run(db, actor, groups, response['run_id'])
            if response.get('run'):
                response['run'] = self._work_run_view(db, actor, groups, run, evidence_access)
        if response.get('workflow_id'):
            self._work_definition(db, actor, groups, response['workflow_id'], body.get('action') in {'create_workflow', 'copy_workflow', 'save_draft', 'validate_workflow', 'publish_workflow'})
            if body.get('action') == 'save_settings':
                definition = self._work_definition(db, actor, groups, response['workflow_id'])
                self._work_authorize_scope(db, actor, groups, definition['system_id'], body.get('factory_id', ''), 'manager')
        if body.get('action') in ('save_access', 'save_factory') and _value(actor, 'role') != 'admin':
            _fail('admin_required', '현재 관리자 권한을 확인해 주세요.')

    async def workspace_command(self, user, body):
        try:
            actor, capabilities, groups = await self._work_actor(user)
            if not isinstance(body, dict): _fail('invalid_command', '업무 명령을 확인해 주세요.')
            _public(body)
            await self._work_validate_people(body)
            action, request_id = body.get('action'), body.get('request_id')
            if not _id(request_id): _fail('request_id_required', '변경 요청 식별자가 필요합니다.')
            actor_id, fingerprint = _value(actor, 'id'), _hash(body)
            # Native lookups run outside the write transaction.
            native_groups = await self._native_groups() if action in ('save_access', 'start_run', 'run_start') else []
            if action == 'link_chat': await self._chat(actor, body.get('chat_id'))
            if action == 'save_access' and body.get('principal_kind') == 'user':
                target = await _resolve(self.user_lookup(body.get('principal_id')))
                if not target or _value(target, 'id') != body.get('principal_id') or _value(target, 'role') not in ('user', 'admin'):
                    _fail('native_user_required', '현재 승인된 Native 사용자 ID를 선택해 주세요.')
            evidence_access = await self._work_evidence_access(actor, groups, body.get('run_id', '')) if body.get('run_id') else set()
            if action in ('decide', 'confirm_verdicts', 'amend_items', 'confirm_list', 'save_review_draft'):
                with self._db() as db:
                    run = self._work_run(db, actor, groups, body.get('run_id'))
                    job = db.execute('SELECT current_attempt FROM work_jobs WHERE run_id=? AND job_id=?', (run['id'], body.get('job_id'))).fetchone()
                    attempt = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone() if job else None
                if attempt:
                    await self._work_check_evidence(actor, dict(attempt))
            options_snapshot = await self._work_resolve_job_options(actor, body.get('run_id'), body.get('job_id')) if action in ('human_confirm', 'amend_items', 'confirm_list') else {}
            publication_errors = []
            publication_resources = {'skills': {}}
            if action in ('validate_workflow', 'publish_workflow'):
                with self._db() as db:
                    prepared = self._work_definition(db, actor, groups, body.get('workflow_id'), True)
                    receipt = db.execute('SELECT * FROM work_receipts WHERE actor_id=? AND request_id=?', (actor_id, request_id)).fetchone()
                    if receipt:
                        if receipt['payload_hash'] != fingerprint:
                            _fail('request_conflict', '같은 요청 식별자에 다른 내용이 있습니다.')
                        previous = json.loads(receipt['response'])
                        self._work_receipt_authorize(db, actor, groups, body, previous, evidence_access)
                        return previous
                    _revision(body, prepared['revision'])
                    definition = json.loads(prepared['draft'])
                if any(node.get('skills') for node in definition.get('nodes', {}).values()):
                    assets = await self._assets(actor)
                    allowed_skills = {entry.get('id') if isinstance(entry, dict) else entry for entry in assets.get('skills', [])}
                    requested_ids = {key for node in definition.get('nodes', {}).values() for key in node.get('skills', []) if isinstance(key, str)}
                    publication_resources['skills'] = {key: {'revision': assets.get('skill_versions', {}).get(key), 'content_hash': hashlib.sha256(str(assets.get('skill_bodies', {}).get(key, '')).encode()).hexdigest()} for key in requested_ids if key in allowed_skills}
                    for node in definition.get('nodes', {}).values():
                        requested = node.get('skills', [])
                        if not isinstance(requested, list) or any(not isinstance(key, str) or key not in allowed_skills for key in requested):
                            publication_errors.append(node.get('id', '') + ': 현재 사용할 수 있는 Native 스킬을 선택해 주세요.')
                bridge = getattr(getattr(self, 'operations', None), 'bridge', None) or getattr(getattr(self, 'execution', None), 'bridge', None)
                option_references = [field['options_query']['reference'] for node in definition.get('nodes', {}).values() for field in node.get('inputs', []) if field.get('options_source') == 'tool' and _options_query_valid(field)]
                for reference in option_references:
                    try:
                        if not bridge or not hasattr(bridge, 'check'): raise ValueError('bridge unavailable')
                        await bridge.check(actor, reference)
                    except Exception:
                        publication_errors.append('선택지 Native 조회의 현재 권한과 지문을 확인하지 못했습니다.')
                for node in definition.get('nodes', {}).values():
                    if node.get('mode') != 'tool':
                        continue
                    ref = deepcopy(node.get('tool_reference') or {})
                    ref.pop('contract_id', None)
                    if not bridge or not hasattr(bridge, 'check'):
                        publication_errors.append(node.get('id', '') + ': Native 도구의 현재 권한과 지문을 확인할 수 없습니다.')
                        continue
                    try:
                        if node.get('result_block') == 'change_request':
                            observed = await bridge.inspect_registered(actor, ref.get('tool_id', ''), ref.get('function', ''))
                            if observed['reference'] != ref: raise ValueError('request reference changed')
                        else:
                            await bridge.check(actor, ref)
                    except Exception:
                        publication_errors.append(node.get('id', '') + ': Native 도구 계약이 변경되었거나 현재 사용할 권한이 없습니다.')
            # Native identity/group membership may change while registry checks await.
            actor, capabilities, groups = await self._work_actor(actor)
            with self._db(write=True) as db:
                receipt = db.execute('SELECT * FROM work_receipts WHERE actor_id=? AND request_id=?', (actor_id, request_id)).fetchone()
                if receipt:
                    if receipt['payload_hash'] != fingerprint: _fail('request_conflict', '같은 요청 식별자에 다른 내용이 있습니다.')
                    # Recheck authorization even for a lost-response retry.
                    previous = json.loads(receipt['response'])
                    self._work_receipt_authorize(db, actor, groups, body, previous, evidence_access)
                    return previous
                result = self._workspace_mutation(db, actor, capabilities, groups, body, native_groups, publication_errors, publication_resources, options_snapshot, evidence_access)
                result = {'ok': True, **result}
                db.execute('INSERT INTO work_receipts VALUES(?,?,?,?)', (actor_id, request_id, fingerprint, _dump(result)))
                db.execute('INSERT INTO work_audit(actor_id,action,target,before_revision,after_revision,request_id,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?)',
                           (actor_id, action, result.get('run_id') or result.get('workflow_id') or result.get('factory_id') or actor_id,
                            body.get('expected_revision'), result.get('revision'), request_id, fingerprint, _now()))
                return result
        except WorkflowError as error:
            return {'ok': False, 'error': {'code': error.code, 'message': error.message}}
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return {'ok': False, 'error': {'code': 'invalid_command', 'message': '업무 변경을 저장하지 못했습니다. 입력과 저장소 상태를 확인해 주세요.'}}

    def _workspace_mutation(self, db, actor, capabilities, groups, body, native_groups, publication_errors=(), publication_resources=None, options_snapshot=None, evidence_access=None):
        action, actor_id, now = body['action'], _value(actor, 'id'), _now()
        if action == 'save_ui':
            row = db.execute('SELECT revision FROM work_ui WHERE actor_id=?', (actor_id,)).fetchone()
            revision = row['revision'] if row else 0; _revision(body, revision)
            state = body.get('state', {})
            if not isinstance(state, dict) or len(_dump(state)) > 40000: _fail('invalid_ui_state', '개인 화면 상태 크기를 확인해 주세요.')
            db.execute('INSERT INTO work_ui VALUES(?,?,?) ON CONFLICT(actor_id) DO UPDATE SET revision=excluded.revision,state=excluded.state', (actor_id, revision + 1, _dump(state)))
            return {'revision': revision + 1, 'ui_state': state}
        if action == 'save_factory':
            if not capabilities['is_admin']: _fail('admin_required', '관리자만 공장 정보를 변경할 수 있습니다.')
            key = body.get('factory_id') or str(uuid4()); system = body.get('system_id')
            if not _id(key) or system not in (*SYSTEMS, 'COMMON') or not isinstance(body.get('name'), str) or not body['name'].strip(): _fail('invalid_factory', '공장 ID·시스템·이름을 확인해 주세요.')
            row = db.execute('SELECT * FROM work_factories WHERE id=?', (key,)).fetchone(); revision = row['revision'] if row else 0; _revision(body, revision)
            if row and row['system_id'] != system: _fail('factory_system_immutable', '기존 공장의 시스템을 바꿀 수 없습니다.')
            attributes = body.get('attributes', {})
            if not isinstance(attributes, dict): _fail('invalid_factory', '공장 속성을 확인해 주세요.')
            db.execute('INSERT INTO work_factories VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,attributes=excluded.attributes,revision=excluded.revision', (key, system, body['name'].strip(), _dump(attributes), revision + 1))
            return {'factory_id': key, 'revision': revision + 1}
        if action == 'save_access':
            if not capabilities['is_admin']: _fail('admin_required', '관리자만 접근 범위를 관리할 수 있습니다.')
            key = body.get('access_id') or str(uuid4()); system = body.get('system_id'); factory = body.get('factory_id', '*')
            principal_kind, principal_id, roles = body.get('principal_kind'), body.get('principal_id'), body.get('roles', [])
            if system not in (*SYSTEMS, 'COMMON') or principal_kind not in ('user', 'group') or not _id(principal_id) or not isinstance(roles, list) or any(role not in ROLES for role in roles): _fail('invalid_access', 'Native ID와 역할을 확인해 주세요.')
            if principal_kind == 'group' and principal_id not in {group['id'] for group in native_groups}: _fail('native_group_required', '현재 Native 그룹을 선택해 주세요.')
            if factory != '*' and not db.execute('SELECT 1 FROM work_factories WHERE id=? AND system_id=?', (factory, system)).fetchone(): _fail('invalid_factory', '해당 시스템의 공장을 선택해 주세요.')
            row = db.execute('SELECT revision FROM work_access WHERE id=?', (key,)).fetchone(); revision = row['revision'] if row else 0; _revision(body, revision)
            db.execute('INSERT INTO work_access VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET system_id=excluded.system_id,factory_id=excluded.factory_id,principal_kind=excluded.principal_kind,principal_id=excluded.principal_id,roles=excluded.roles,active=excluded.active,revision=excluded.revision', (key, system, factory, principal_kind, principal_id, _dump(roles), int(body.get('active', True)), revision + 1))
            return {'access_id': key, 'revision': revision + 1}
        if action in ('create_workflow', 'copy_workflow'):
            system = body.get('system_id'); source = None
            if action == 'copy_workflow':
                source = self._work_definition(db, actor, groups, body.get('workflow_id'), True); _revision(body, source['revision']); system = source['system_id']
            else: _revision(body, 0)
            self._work_authorize_scope(db, actor, groups, system, '', 'manager')
            key = str(uuid4()); root = 'p-' + uuid4().hex[:12]
            if source:
                definition = json.loads(source['draft']); mapping = {old: ('p-' if node['type'] == 'p' else 't-' if node['type'] == 't' else 'j-') + uuid4().hex[:12] for old, node in definition['nodes'].items()}
                definition['nodes'] = {mapping[old]: dict(node, id=mapping[old], parent=mapping.get(node.get('parent')), children=[mapping[child] for child in node.get('children', [])], deps=[mapping[dep] for dep in node.get('deps', [])]) for old, node in definition['nodes'].items()}
                # Only definition-owned references move. Native asset IDs,
                # input IDs, literal arguments and connector evidence remain
                # unchanged even when their string equals an old node ID.
                for node in definition['nodes'].values():
                    for field in ('result_source_job_id', 'effect_job_id'):
                        if node.get(field) in mapping:
                            node[field] = mapping[node[field]]
                    criterion = node.get('effect_criterion')
                    if isinstance(criterion, dict) and criterion.get('job_id') in mapping:
                        criterion['job_id'] = mapping[criterion['job_id']]
                    for binding in node.get('argument_bindings', {}).values():
                        result = binding.get('result') if isinstance(binding, dict) else None
                        if isinstance(result, dict) and result.get('job_id') in mapping:
                            result['job_id'] = mapping[result['job_id']]
                if isinstance(definition.get('factory_overrides'), dict):
                    definition['factory_overrides'] = {mapping.get(node_id, node_id): value for node_id, value in definition['factory_overrides'].items()}
                definition['id'] = key; definition['name'] = body.get('name') or definition['name'] + ' 복사'
            else:
                definition = {'id': key, 'name': body.get('name', '새 업무 절차'), 'system_id': system, 'category': body.get('category', 'ops'), 'mode': body.get('mode', 'on_demand'),
                              'nodes': {root: {'id': root, 'name': body.get('name', '새 업무 절차'), 'type': 'p', 'parent': None, 'children': [], 'deps': []}}}
                if body.get('execution_scope') is not None: definition['execution_scope'] = body['execution_scope']
            errors, _ = definition_check(definition, False)
            if errors: _fail('invalid_definition', '\n'.join(errors))
            db.execute('INSERT INTO work_definitions VALUES(?,?,?,1,NULL,NULL,?,?)', (key, system, _dump(definition), actor_id, now))
            return {'workflow_id': key, 'revision': 1, 'workflow': self._work_workflow_view(db, actor, groups, self._work_definition(db, actor, groups, key, True))}
        if action in ('save_draft', 'validate_workflow', 'publish_workflow', 'save_settings'):
            row = self._work_definition(db, actor, groups, body.get('workflow_id'), action != 'save_settings')
            definition = json.loads(row['draft'])
            if action == 'save_settings':
                factory = body.get('factory_id', ''); self._work_authorize_scope(db, actor, groups, row['system_id'], factory, 'manager')
                if factory and not db.execute('SELECT 1 FROM work_factories WHERE id=? AND system_id=?', (factory, row['system_id'])).fetchone(): _fail('invalid_factory', '공장 범위를 확인해 주세요.')
                saved = db.execute('SELECT * FROM work_settings WHERE workflow_id=? AND factory_id=?', (row['id'], factory)).fetchone(); revision = saved['revision'] if saved else 0; _revision(body, revision)
                values = body.get('values', {}); fields = {field['id']: field for node in definition['nodes'].values() for field in node.get('inputs', []) if field.get('scope', 'run') == 'workflow' or (factory and field.get('scope') == 'factory')}
                if not isinstance(values, dict): _fail('invalid_inputs', '업무 설정 형식을 확인해 주세요.')
                errors = input_errors(list(fields.values()), values, False)
                if errors: _fail('invalid_inputs', '\n'.join(errors))
                active_runs = list(db.execute("SELECT * FROM work_runs WHERE workflow_id=? AND status NOT IN ('completed','cancelled')", (row['id'],)))
                def evidence_values(run, job_id):
                    snapshot = self._work_snapshot(db, run, job_id)
                    return snapshot['inputs'], (snapshot.get('deadline_source') or {}).get('value')
                old_effective = {(run['id'], job['job_id']): evidence_values(run, job['job_id']) for run in active_runs for job in db.execute('SELECT job_id FROM work_jobs WHERE run_id=?', (run['id'],))}
                db.execute('INSERT INTO work_settings VALUES(?,?,?,?,?) ON CONFLICT(workflow_id,factory_id) DO UPDATE SET values_json=excluded.values_json,revision=excluded.revision,updated_by=excluded.updated_by', (row['id'], factory, _dump(values), revision + 1, actor_id))
                for run in active_runs:
                    changed_jobs = {job_id for (run_id, job_id), old in old_effective.items() if run_id == run['id'] and old != evidence_values(run, job_id)}
                    affected = set(changed_jobs)
                    for job_id in changed_jobs:
                        affected.update(self._work_dependent_ids(json.loads(run['snapshot'])['definition'], job_id))
                    for job_id in affected:
                        db.execute("UPDATE work_jobs SET status='review_required',revision=revision+1,reason='업무 설정 변경 후 재확인 필요' WHERE run_id=? AND job_id=? AND status IN ('completed','waiting_confirmation')", (run['id'], job_id))
                    if affected:
                        db.execute('UPDATE work_runs SET revision=revision+1,updated_at=? WHERE id=?', (now, run['id']))
                return {'workflow_id': row['id'], 'revision': revision + 1, 'settings': {'factory_id': factory, 'values': values, 'revision': revision + 1}}
            _revision(body, row['revision'])
            if action == 'save_draft':
                definition = body.get('definition'); errors, _ = definition_check(definition, False)
                if errors: _fail('invalid_definition', '\n'.join(errors))
                if definition['id'] != row['id'] or definition['system_id'] != row['system_id']: _fail('immutable_identity', '절차 ID와 관리 시스템은 바꿀 수 없습니다.')
                db.execute('UPDATE work_definitions SET draft=?,revision=revision+1,validation=NULL,updated_at=? WHERE id=?', (_dump(definition), now, row['id']))
                return {'workflow_id': row['id'], 'revision': row['revision'] + 1}
            errors, warnings = definition_check(definition)
            declared = {field['id']: field for node in definition['nodes'].values() for field in node.get('inputs', [])}
            for setting in db.execute('SELECT factory_id,values_json FROM work_settings WHERE workflow_id=?', (row['id'],)):
                for key in json.loads(setting['values_json']):
                    field = declared.get(key)
                    if not field or field.get('scope', 'run') == 'run' or (field.get('scope') == 'factory' and not setting['factory_id']):
                        errors.append(f'{key}: 삭제되거나 저장 범위가 바뀐 업무 설정을 먼저 정리해 주세요.')
            errors.extend(publication_errors)
            if hasattr(self, 'operations') and hasattr(self.operations, 'validate_publication'):
                errors.extend(self.operations.validate_publication(db, definition, actor, groups))
                warnings.extend(self.operations.publication_warnings(db, definition))
            validation = {'revision': row['revision'], 'definition_hash': _hash(definition), 'resource_versions': publication_resources or {'skills': {}}, 'errors': errors, 'warnings': warnings, 'checked_at': now,
                          'checks': ['P/T/J 구조·선행 연결·입력 형식', '현재 도구·지침 참조와 게시 권한'] if not errors else []}
            if action == 'validate_workflow':
                db.execute('UPDATE work_definitions SET validation=? WHERE id=?', (_dump(validation), row['id']))
                return {'workflow_id': row['id'], 'revision': row['revision'], 'validation': validation}
            prior = json.loads(row['validation']) if row['validation'] else {}
            if errors or prior.get('revision') != row['revision'] or prior.get('definition_hash') != _hash(definition) or prior.get('errors') or prior.get('resource_versions') != validation['resource_versions']:
                _fail('validation_required', '\n'.join(errors) or '현재 초안을 먼저 검사해 주세요.')
            version = (row['published_version'] or 0) + 1
            definition = {**definition, 'resource_versions': validation['resource_versions']}
            db.execute('INSERT INTO work_versions VALUES(?,?,?,?,?,?)', (row['id'], version, _dump(definition), _hash(definition), actor_id, now))
            db.execute('UPDATE work_definitions SET published_version=?,revision=revision+1,validation=NULL,updated_at=? WHERE id=?', (version, now, row['id']))
            return {'workflow_id': row['id'], 'revision': row['revision'] + 1, 'version': version}
        if action in ('start_run', 'run_start'):
            row = self._work_definition(db, actor, groups, body.get('workflow_id')); _revision(body, row['revision'])
            version = body.get('version', row['published_version'])
            published = db.execute('SELECT * FROM work_versions WHERE workflow_id=? AND version=?', (row['id'], version)).fetchone()
            if not published: _fail('publication_required', '게시된 절차 버전을 선택해 주세요.')
            definition = json.loads(published['definition']); factory_id = body.get('factory_id', '')
            if definition.get('execution_scope') == 'system': factory_id = ''
            if definition.get('execution_scope') == 'factory' and not factory_id:
                _fail('factory_required', '시작할 공장을 선택해 주세요.')
            self._work_authorize_scope(db, actor, groups, row['system_id'], factory_id, 'participant')
            factory = db.execute('SELECT * FROM work_factories WHERE id=? AND system_id=?', (factory_id, row['system_id'])).fetchone() if factory_id else None
            if factory_id and not factory: _fail('factory_not_found', '등록된 공장을 선택해 주세요.')
            if definition.get('mode', 'on_demand') == 'on_demand' and factory_id and db.execute("SELECT 1 FROM work_runs WHERE workflow_id=? AND factory_id=? AND status NOT IN ('completed','cancelled') LIMIT 1", (row['id'], factory_id)).fetchone():
                _fail('factory_run_active', '이 공장에서 같은 업무가 진행 중입니다. 기존 진행 건을 확인해 주세요.')
            sharing = body.get('sharing', {'group_ids': []})
            if not isinstance(sharing, dict) or set(sharing) != {'group_ids'} or not isinstance(sharing['group_ids'], list) or any(group not in {item['id'] for item in native_groups} for group in sharing['group_ids']): _fail('invalid_sharing', '현재 Native 참여 그룹을 선택해 주세요.')
            if sharing['group_ids'] and not capabilities['is_admin'] and not set(sharing['group_ids']) <= groups: _fail('sharing_forbidden', '참여 중인 그룹만 연결할 수 있습니다.')
            inputs = body.get('inputs', {}); fields = {field['id']: field for node in definition['nodes'].values() for field in node.get('inputs', []) if field.get('scope', 'run') == 'run'}
            if not isinstance(inputs, dict): _fail('invalid_inputs', '이번 입력 형식을 확인해 주세요.')
            errors = input_errors(list(fields.values()), inputs, False)
            if errors: _fail('invalid_inputs', '\n'.join(errors))
            attributes = json.loads(factory['attributes']) if factory else {}; attributes['factory_id'] = factory_id
            conditions = {}
            for key, node in definition['nodes'].items():
                values = [_condition(node.get('condition'), attributes)]; parent = node.get('parent')
                while parent in definition['nodes']:
                    ancestor = definition['nodes'][parent]; values.append(_condition(ancestor.get('condition'), attributes)); parent = ancestor.get('parent')
                conditions[key] = False if False in values else None if None in values else True
            snapshot = {'definition': definition, 'definition_hash': published['hash'], 'factory': dict(factory) | {'attributes': attributes} if factory else None, 'condition_results': conditions}
            key = str(uuid4()); mode = definition.get('mode', 'on_demand')
            if body.get('mode', mode) != mode: _fail('invalid_mode', '게시된 실행 방식을 사용해 주세요.')
            db.execute('INSERT INTO work_runs VALUES(?,?,?,?,?,?,?,?,\'open\',1,?,?,?,?,NULL)', (key, row['id'], version, row['system_id'], factory_id, actor_id, _dump(sharing), mode, _dump(inputs), _dump(snapshot), now, now))
            for job_id, node in definition['nodes'].items():
                if node['type'] == 'j':
                    condition = conditions[job_id]; status = 'excluded' if condition is False else 'blocked' if condition is None else 'pending'
                    db.execute('INSERT INTO work_jobs VALUES(?,?,?,0,NULL,NULL,?)', (key, job_id, status, '공장 조건 미충족' if condition is False else '공장 속성 확인 필요' if condition is None else ''))
            if mode == 'emergency' and hasattr(self, 'operations'):
                self.operations.enqueue_scope(db, actor, groups, key, expected_revision=1, request_id='emergency-' + key, emergency=True)
            run = self._work_run_view(db, actor, groups, self._work_run(db, actor, groups, key))
            return {'run_id': key, 'workflow_id': row['id'], 'revision': 1, 'run': run}
        if action in ('save_inputs', 'claim_task', 'human_confirm', 'decide', 'confirm_verdicts', 'close_run', 'cancel_run', 'link_chat', 'amend_items', 'release_task', 'confirm_list', 'save_review_draft'):
            row = self._work_run(db, actor, groups, body.get('run_id'), write=True); _revision(body, row['revision'])
            if action == 'link_chat':
                db.execute('INSERT OR IGNORE INTO work_chat_links VALUES(?,?,?,?)', (actor_id, body['chat_id'], row['id'], now))
                return {'run_id': row['id'], 'revision': row['revision']}
            if action == 'save_inputs':
                inputs = body.get('inputs', {}); definition = json.loads(row['snapshot'])['definition']
                fields = {field['id']: field for node in definition['nodes'].values() for field in node.get('inputs', []) if field.get('scope', 'run') == 'run'}
                if not isinstance(inputs, dict): _fail('invalid_inputs', '이번 입력 형식을 확인해 주세요.')
                errors = input_errors(list(fields.values()), inputs, False)
                if errors: _fail('invalid_inputs', '\n'.join(errors))
                before = json.loads(row['inputs']); changed = {key for key in set(before) | set(inputs) if key not in before or key not in inputs or before[key] != inputs[key]}
                db.execute('UPDATE work_runs SET inputs=? WHERE id=?', (_dump(inputs), row['id']))
                for key, node in definition['nodes'].items():
                    if changed.intersection({field['id'] for field in node.get('inputs', [])} | {(node.get('deadline') or {}).get('input')}):
                        for affected in {key} | self._work_dependent_ids(definition, key):
                            db.execute("UPDATE work_jobs SET status='review_required',revision=revision+1,reason='입력 변경 후 재확인 필요' WHERE run_id=? AND job_id=? AND status IN ('completed','waiting_confirmation')", (row['id'], affected))
            elif action in ('close_run', 'cancel_run'):
                unresolved = db.execute("SELECT 1 FROM work_external_requests WHERE run_id=? AND state IN ('requested','accepted','running','reported_complete','unknown') LIMIT 1", (row['id'],)).fetchone()
                if unresolved:
                    _fail('external_request_unresolved', '이전 EES 요청의 접수와 효과를 먼저 확인해 주세요. 종료는 요청 취소나 복구를 대신하지 않습니다.')
                jobs = list(db.execute('SELECT * FROM work_jobs WHERE run_id=?', (row['id'],)))
                if any(job['status'] == 'running' for job in jobs): _fail('execution_running', '실행 결과를 확인한 뒤 종료해 주세요.')
                if action == 'close_run' and any(job['status'] not in ('completed', 'excluded') for job in jobs): _fail('completion_required', '필수 작업의 판정을 먼저 해결해 주세요.')
                if action == 'cancel_run' and not str(body.get('reason', '')).strip(): _fail('reason_required', '취소 이유를 기록해 주세요.')
                db.execute('UPDATE work_runs SET status=?,closed_at=? WHERE id=?', ('completed' if action == 'close_run' else 'cancelled', now, row['id']))
            else:
                job_id = body.get('job_id'); job = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (row['id'], job_id)).fetchone()
                if not job or job['status'] == 'excluded': _fail('job_not_found', '처리할 작업을 찾지 못했습니다.')
                if job['claim_actor'] and job['claim_actor'] != actor_id: _fail('task_claimed', '다른 담당자가 처리 중입니다.')
                node = json.loads(row['snapshot'])['definition']['nodes'][job_id]; assignee = node.get('assignee')
                if assignee and assignee.get('id') not in ({actor_id} if assignee.get('kind') == 'user' else groups): _fail('assignee_required', '배정된 담당자 또는 그룹만 처리할 수 있습니다.')
                if action == 'confirm_verdicts':
                    current = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
                    if node.get('result_block') != 'item_verdict' or not current or current['id'] != body.get('attempt_id') or current['number'] != body.get('result_revision'):
                        _fail('result_revision_conflict', '확정할 현재 판정 근거를 다시 확인해 주세요.')
                    if job['status'] == 'completed':
                        _fail('decision_conflict', '이미 확정한 판정입니다. 새 근거 없이 변경할 수 없습니다.')
                    items = json.loads(current['result'] or '{}').get('items', [])
                    required = {str(item['id']) for item in items if isinstance(item, dict) and 'id' in item}
                    choices = body.get('verdicts')
                    existing = {item['item_id']: item['verdict'] for item in db.execute('SELECT item_id,verdict FROM work_decisions WHERE attempt_id=?', (current['id'],))}
                    if not required or not isinstance(choices, list) or any(not isinstance(item, dict) or set(item) - {'item_id', 'verdict', 'note', 'judgment_id'} or not isinstance(item.get('item_id'), str) or item.get('verdict') not in ('completed', 'failed', 'unknown', 'action_required') for item in choices) or len(choices) != len({item['item_id'] for item in choices}) or not {item['item_id'] for item in choices} <= required or required - existing.keys() - {item['item_id'] for item in choices}:
                        _fail('verdict_selection_required', '모든 항목의 판정을 선택한 뒤 확정해 주세요.')
                    if required <= existing.keys() or any(item['item_id'] in existing and existing[item['item_id']] != item['verdict'] for item in choices):
                        _fail('decision_conflict', '이미 확정한 판정입니다. 새 근거 없이 변경할 수 없습니다.')
                    for choice in choices:
                        if choice['item_id'] not in existing:
                            self._work_decide(db, actor, row, job, node, {**body, **choice})
                elif action == 'save_review_draft':
                    current = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
                    if node.get('result_block') != 'ai_review' or not current or current['id'] != body.get('attempt_id') or current['number'] != body.get('result_revision'):
                        _fail('result_revision_conflict', '편집할 현재 초안의 근거를 다시 확인해 주세요.')
                    if current['actor_id'] != actor_id or current['id'] not in (evidence_access or set()):
                        _fail('evidence_access_required', '본인 권한으로 생성한 초안과 현재 근거를 확인해 주세요.')
                    if current['status'] not in ('succeeded', 'waiting_confirmation', 'partial'):
                        _fail('result_unconfirmed', '편집할 초안이 아직 준비되지 않았습니다.')
                    actual_snapshot = self._work_snapshot(db, row, job_id)
                    saved_snapshot = json.loads(current['snapshot'])
                    if json.loads(current['inputs']) != actual_snapshot['inputs'] or (saved_snapshot.get('deadline_source') or {}).get('value') != (actual_snapshot.get('deadline_source') or {}).get('value') or not self._work_sources_current(db, row, saved_snapshot):
                        _fail('stale_result', '입력이나 선행 근거가 바뀌었습니다. 새 근거로 초안을 다시 생성해 주세요.')
                    if db.execute('SELECT 1 FROM work_decisions WHERE attempt_id=?', (current['id'],)).fetchone():
                        _fail('decision_conflict', '확정한 본문은 실행 기록으로 보존됩니다. 새 근거로 다시 실행해 주세요.')
                    latest = db.execute('SELECT * FROM work_review_revisions WHERE attempt_id=? ORDER BY revision DESC LIMIT 1', (current['id'],)).fetchone()
                    _revision({'expected_revision': body.get('review_revision')}, latest['revision'] if latest else 0)
                    text = body.get('text')
                    if not isinstance(text, str) or len(text) > 20000:
                        _fail('invalid_review_draft', '검토 본문은 20,000자 이내의 글로 입력해 주세요.')
                    db.execute('INSERT INTO work_review_revisions VALUES(?,?,?,?,?,NULL)', (current['id'], (latest['revision'] if latest else 0) + 1, text, actor_id, now))
                elif action == 'confirm_list':
                    current = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
                    if node.get('result_block') != 'list_confirm' or not current or current['id'] != body.get('attempt_id') or current['number'] != body.get('result_revision'):
                        _fail('result_revision_conflict', '확정할 현재 목록의 근거를 확인해 주세요.')
                    if current['actor_id'] != actor_id or current['id'] not in (evidence_access or set()):
                        _fail('evidence_access_required', '본인 권한으로 조회한 목록을 확인해 주세요.')
                    if db.execute('SELECT 1 FROM work_decisions WHERE attempt_id=?', (current['id'],)).fetchone():
                        _fail('decision_conflict', '이미 판정한 목록입니다. 새 근거로 다시 조회해 주세요.')
                    items = deepcopy(body.get('items'))
                    if not isinstance(items, list) or len(items) > 1000 or any(not isinstance(item, dict) or not _id(item.get('id')) or not isinstance(item.get('selected', True), bool) for item in items) or len({item['id'] for item in items}) != len(items):
                        _fail('invalid_amendment', '중복 없는 목록과 포함 여부를 확인해 주세요.')
                    for item in items:
                        item['selected'] = item.get('selected', True)
                        item['required'] = item['selected']
                    if not any(item['selected'] for item in items):
                        _fail('zero_selection_policy_required', '선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다. 확정을 보류합니다.')
                    original = json.loads(current['result']) or {}
                    previous = original.get('items', [])
                    fields = ('id', 'title', 'name', 'selected', 'required', 'note')
                    comparable = lambda item: {key: item.get(key, True if key in ('selected', 'required') else None) for key in fields}
                    previous_by_id = {item['id']: item for item in previous if isinstance(item, dict) and 'id' in item}
                    desired = [{**previous_by_id.get(item['id'], {}), **{key: item[key] for key in fields if key in item}} for item in items]
                    if [comparable(item) for item in desired] != [comparable(item) for item in previous]:
                        if not str(body.get('reason', '')).strip():
                            _fail('reason_required', '목록을 바꾼 이유를 기록해 주세요.')
                        self._workspace_mutation(db, actor, capabilities, groups, {**body, 'action': 'amend_items', 'items': items}, native_groups, publication_errors, publication_resources, options_snapshot, evidence_access)
                        row = self._work_run(db, actor, groups, row['id'], write=True)
                        job = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (row['id'], job_id)).fetchone()
                        current = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
                    for item in items:
                        if item['selected']:
                            self._work_decide(db, actor, row, job, node, {'result_revision': current['number'], 'item_id': item['id'], 'verdict': 'completed', 'note': str(body.get('reason', ''))})
                elif action == 'release_task':
                    if job['claim_actor'] != actor_id:
                        _fail('claim_owner_required', '현재 담당자 본인만 맡은 작업을 내려놓을 수 있습니다.')
                    unresolved = db.execute("SELECT 1 FROM work_external_requests WHERE run_id=? AND job_id=? AND state IN ('requested','accepted','running','reported_complete','unknown') LIMIT 1", (row['id'], job_id)).fetchone()
                    if job['status'] == 'running' or unresolved:
                        _fail('execution_unresolved', '진행 중인 실행과 EES 요청 결과를 먼저 확인해 주세요.')
                    db.execute('UPDATE work_jobs SET claim_actor=NULL,revision=revision+1 WHERE run_id=? AND job_id=?', (row['id'], job_id))
                elif action == 'amend_items':
                    current = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
                    if not current or current['number'] != body.get('result_revision') or current['status'] not in ('succeeded', 'partial', 'waiting_confirmation'):
                        _fail('result_revision_conflict', '수정할 현재 목록의 근거를 확인해 주세요.')
                    if current['actor_id'] != actor_id:
                        _fail('evidence_access_required', '본인 권한으로 조회한 목록을 수정해 주세요.')
                    prior_snapshot = json.loads(current['snapshot'])
                    effective_snapshot = self._work_snapshot(db, row, job_id)
                    if json.loads(current['inputs']) != effective_snapshot['inputs'] or (prior_snapshot.get('deadline_source') or {}).get('value') != (effective_snapshot.get('deadline_source') or {}).get('value') or not self._work_sources_current(db, row, prior_snapshot):
                        _fail('stale_result', '입력이나 선행 근거가 바뀌었습니다. 다시 조회한 목록을 확인해 주세요.')
                    items, reason = body.get('items'), body.get('reason', '')
                    if node.get('result_block') not in ('list_confirm', 'item_verdict', 'checklist') or not isinstance(items, list) or len(items) > 1000 or not isinstance(reason, str) or not reason.strip():
                        _fail('invalid_amendment', '수정할 목록과 변경 이유를 기록해 주세요.')
                    if any(not isinstance(item, dict) or not _id(item.get('id')) for item in items) or len({item['id'] for item in items}) != len(items):
                        _fail('invalid_amendment', '중복 없는 항목 ID를 확인해 주세요.')
                    original = json.loads(current['result']) or {}; old_items = {item['id']: item for item in original.get('items', []) if isinstance(item, dict) and 'id' in item}
                    amended = []
                    for item in items:
                        allowed = {field: item[field] for field in ('id', 'title', 'name', 'selected', 'required', 'note') if field in item}
                        if item['id'] in old_items:
                            allowed = {**old_items[item['id']], **allowed}
                        else:
                            allowed['source'] = {'kind': 'human_added', 'actor_id': actor_id, 'created_at': now}
                        amended.append(allowed)
                    attempt = self._work_begin_attempt(db, actor, groups, row['id'], job_id, row['revision'], options_snapshot=options_snapshot)
                    # Manual list edits retain the source/model evidence that
                    # justified the original result, including future ACL checks.
                    for field in ('source_references', 'evidence_attempt_ids', 'model', 'skills', 'argument_sources', 'arguments'):
                        if field in prior_snapshot:
                            attempt['snapshot'][field] = deepcopy(prior_snapshot[field])
                    db.execute("UPDATE work_attempts SET snapshot=? WHERE id=? AND status='running'", (_dump(attempt['snapshot']), attempt['id']))
                    result = {**original, 'items': amended, 'amendment': {'previous_attempt': current['id'], 'reason': reason.strip(), 'actor_id': actor_id, 'added_ids': [item['id'] for item in items if item['id'] not in old_items], 'removed_ids': sorted(set(old_items) - {item['id'] for item in items})}}
                    if evidence_access is not None: evidence_access.add(attempt['id'])
                    self._work_finish_attempt(db, attempt['id'], 'partial' if current['status'] == 'partial' else 'waiting_confirmation', result)
                elif action == 'claim_task':
                    db.execute('UPDATE work_jobs SET claim_actor=?,revision=revision+1 WHERE run_id=? AND job_id=?', (actor_id, row['id'], job_id))
                else:
                    if action == 'human_confirm':
                        if node.get('result_block') == 'change_request': _fail('request_confirmation_required', '등록된 EES 요청의 승인·확인·효과 확인 경로를 사용해 주세요.')
                        if node.get('mode', 'human') != 'human': _fail('result_confirmation_required', '현재 실행 결과의 revision을 확인해 판정해 주세요.')
                        attempt = self._work_begin_attempt(db, actor, groups, row['id'], job_id, row['revision'], options_snapshot=options_snapshot)
                        self._work_finish_attempt(db, attempt['id'], 'succeeded', {'human_input': attempt['inputs']})
                        if evidence_access is not None: evidence_access.add(attempt['id'])
                        job = db.execute('SELECT * FROM work_jobs WHERE run_id=? AND job_id=?', (row['id'], job_id)).fetchone()
                        body = {**body, 'result_revision': attempt['number'], 'item_id': 'job', 'verdict': body.get('verdict', 'completed')}
                    self._work_decide(db, actor, row, job, node, body)
            db.execute('UPDATE work_runs SET revision=revision+1,updated_at=? WHERE id=?', (now, row['id']))
            current = self._work_run(db, actor, groups, row['id'])
            return {'run_id': row['id'], 'revision': current['revision'], 'run': self._work_run_view(db, actor, groups, current, evidence_access)}
        _fail('unknown_command', '지원하지 않는 업무 명령입니다.')

    def _work_decide(self, db, actor, run, job, node, body):
        if not job['current_attempt']:
            _fail('result_revision_conflict', '현재 결과를 다시 확인한 뒤 판정해 주세요.')
        attempt = db.execute('SELECT * FROM work_attempts WHERE id=?', (job['current_attempt'],)).fetchone()
        if job['status'] == 'completed' and db.execute('SELECT 1 FROM work_decisions WHERE attempt_id=?', (attempt['id'],)).fetchone():
            _fail('decision_conflict', '이미 확정한 판정입니다. 새 근거 없이 변경할 수 없습니다.')
        if node.get('result_block') == 'change_request':
            external = db.execute("SELECT data FROM work_external_requests WHERE run_id=? AND job_id=? AND state='effect_verified'", (run['id'], job['job_id'])).fetchall()
            verified = any((record := json.loads(item['data'])).get('attempt_id') == attempt['id'] and record.get('reported_complete') is True and record.get('effect_verified') is True for item in external)
            if not verified:
                _fail('request_effect_unconfirmed', 'EES 완료 보고와 효과 확인을 먼저 받아야 합니다.')
        current_snapshot = self._work_snapshot(db, run, job['job_id'])
        prior_snapshot = json.loads(attempt['snapshot'])
        if json.loads(attempt['inputs']) != current_snapshot['inputs'] or (prior_snapshot.get('deadline_source') or {}).get('value') != (current_snapshot.get('deadline_source') or {}).get('value') or not self._work_sources_current(db, run, prior_snapshot):
            _fail('stale_result', '입력이나 선행 근거가 바뀌었습니다. 다시 실행한 근거를 확인해 주세요.')
        if body.get('result_revision') != attempt['number']:
            _fail('result_revision_conflict', '현재 근거 revision을 확인한 뒤 판정해 주세요.')
        if attempt['status'] not in ('succeeded', 'partial', 'waiting_confirmation'):
            _fail('result_unconfirmed', '실패하거나 결과가 불명인 실행을 성공으로 확정할 수 없습니다.')
        if node.get('mode') != 'human' and attempt['actor_id'] != _value(actor, 'id'):
            _fail('evidence_access_required', '본인 권한으로 근거를 다시 조회한 뒤 판정해 주세요.')
        verdict = body.get('verdict'); item_id = body.get('item_id', 'job')
        if verdict not in ('completed', 'failed', 'unknown', 'action_required') or not _id(item_id):
            _fail('invalid_verdict', '판정의 업무 의미와 항목 ID를 확인해 주세요.')
        note = str(body.get('note', ''))[:4000]
        if body.get('judgment_id') is not None:
            judgments = node.get('judgments', prior_snapshot['definition'].get('judgments', []))
            judgment = next((item for item in judgments if isinstance(item, dict) and item.get('id') == body['judgment_id']), None)
            if not judgment or judgment.get('status') != verdict or not isinstance(judgment.get('label'), str) or len(judgment['label']) > 160:
                _fail('invalid_judgment', '선택한 판정 문구와 기본 상태를 확인해 주세요.')
            suffix = '\n선택한 판정: ' + judgment['label'] + ' (' + judgment['id'] + ')'
            note = note[:4000-len(suffix)] + suffix
        result = json.loads(attempt['result']) if attempt['result'] else {}
        items = result.get('items', []) if isinstance(result, dict) else []
        required = {str(item['id']) for item in items if isinstance(item, dict) and 'id' in item and item.get('required', True)}
        if node.get('result_block') == 'list_confirm':
            required = {str(item['id']) for item in items if isinstance(item, dict) and 'id' in item and item.get('required', True) and item.get('selected', True)}
            if not required and verdict == 'completed':
                _fail('zero_selection_policy_required', '선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다. 확정을 보류합니다.')
        if node.get('result_block') == 'item_verdict' and items:
            if item_id not in {str(item['id']) for item in items if isinstance(item, dict) and 'id' in item}:
                _fail('item_not_found', '현재 결과의 항목을 선택해 주세요.')
        elif node.get('result_block') in ('checklist', 'list_confirm') and required:
            if item_id not in required: _fail('item_not_found', '현재 결과의 필수 항목을 선택해 주세요.')
        elif item_id != 'job': _fail('item_not_found', '현재 작업 결과를 확인해 주세요.')
        # Every decision is evidence-bound. A second click cannot override an
        # earlier verdict; changing evidence requires another attempt.
        if db.execute('SELECT 1 FROM work_decisions WHERE run_id=? AND job_id=? AND item_id=? AND attempt_id=?', (run['id'], job['job_id'], item_id, attempt['id'])).fetchone():
            _fail('decision_conflict', '이 근거에 대한 판정이 이미 저장되었습니다.')
        review = None
        if node.get('result_block') == 'ai_review':
            review = db.execute('SELECT * FROM work_review_revisions WHERE attempt_id=? ORDER BY revision DESC LIMIT 1', (attempt['id'],)).fetchone()
            # A confirmation cannot silently include a later autosave from a
            # second tab. With no edits, the original immutable result is used.
            if review:
                _revision({'expected_revision': body.get('review_revision')}, review['revision'])
        decision_id, decided_at = str(uuid4()), _now()
        db.execute('INSERT INTO work_decisions VALUES(?,?,?,?,?,?,?,?,?,?)', (decision_id, run['id'], job['job_id'], item_id, attempt['id'], attempt['number'], verdict, note, _value(actor, 'id'), decided_at))
        if node.get('result_block') == 'ai_review':
            text = review['text'] if review else next((result[key] for key in ('text', 'draft', 'summary') if isinstance(result.get(key), str)), '')
            db.execute('INSERT INTO work_review_revisions VALUES(?,?,?,?,?,?)', (attempt['id'], (review['revision'] if review else 0) + 1, text, _value(actor, 'id'), decided_at, decision_id))
        decisions = list(db.execute('SELECT item_id,verdict FROM work_decisions WHERE run_id=? AND job_id=? AND attempt_id=?', (run['id'], job['job_id'], attempt['id'])))
        resolved = not required or required <= {item['item_id'] for item in decisions}
        state = 'waiting_confirmation'
        if resolved:
            meanings = {item['verdict'] for item in decisions if not required or item['item_id'] in required}
            state = 'completed' if meanings == {'completed'} else 'failed' if 'failed' in meanings else 'unknown' if 'unknown' in meanings else 'waiting_input'
            if attempt['status'] == 'partial' and state == 'completed': state = 'partial'
        reason = job['reason']
        if state == 'completed' and isinstance(node.get('completion'), dict) and node['completion'].get('kind') == 'delivery':
            # Reviewing a draft is evidence of review, never evidence of send.
            # No delivery adapter or channel policy is configured by this UI.
            state, reason = 'blocked', 'delivery_unconfigured'
        db.execute('UPDATE work_jobs SET status=?,reason=?,revision=revision+1,claim_actor=? WHERE run_id=? AND job_id=?', (state, reason, _value(actor, 'id'), run['id'], job['job_id']))
