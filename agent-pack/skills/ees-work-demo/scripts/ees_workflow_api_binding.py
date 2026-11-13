"""Typed workflow bindings to versioned service API operations."""
import json
from uuid import uuid4

from .ees_workflow_authoring import WorkflowError, _fail, _now
from .ees_workflow_definition import _dump


def _tokens(value, limit=240):
    return isinstance(value, str) and 0 < len(value) <= limit


def binding_shape(node, required_jobs):
    binding = node.get('api_binding')
    if (node.get('type') != 'j' or node.get('mode') != 'tool'
            or any(node.get(k) for k in ('tool_contract_id', 'tool_contract_revision', 'tool_reference',
                                          'shared_tool_id', 'argument_bindings', 'execution'))
            or not isinstance(binding, dict) or set(binding) != {'operation_id', 'version', 'inputs', 'outputs'}
            or not _tokens(binding['operation_id'], 160) or type(binding['version']) is not int or binding['version'] < 1):
        return '작업의 API 참조와 버전을 확인해 주세요.'
    fields, outputs = binding['inputs'], binding['outputs']
    if (not isinstance(fields, dict) or len(fields) > 100 or not isinstance(outputs, list)
            or len(outputs) > 100 or any(not _tokens(field) for field in outputs) or len(set(outputs)) != len(outputs)):
        return 'API의 입력과 사용할 결과 항목을 확인해 주세요.'
    local = {f.get('id') for f in node.get('inputs', []) if isinstance(f, dict) and isinstance(f.get('id'), str)}
    for name, source in fields.items():
        if not _tokens(name) or not isinstance(source, dict) or len(source) != 1:
            return '입력값마다 하나의 출처를 지정해 주세요.'
        if 'constant' in source:
            continue
        if 'input' in source and isinstance(source['input'], str) and source['input'] in local:
            continue
        if 'context' in source and source['context'] in ('factory_id', 'system_id'):
            continue
        result = source.get('result')
        if (isinstance(result, dict) and set(result) == {'job_id', 'field', 'confirmed'}
                and result['confirmed'] is True and _tokens(result['field'])
                and _tokens(result['job_id']) and result['job_id'] in required_jobs):
            continue
        return '현재 업무의 입력 또는 확정된 선행 작업의 결과를 선택해 주세요.'
    return ''


def _kind(value):
    return {str: 'string', int: 'integer', float: 'number', bool: 'boolean',
            list: 'array', dict: 'object', type(None): 'null'}.get(type(value), '')


def _compatible(actual, expected):
    return actual == expected or actual == 'integer' and expected == 'number'


def binding_errors(service, db, groups, definition, *, previous=None, for_new=False, overrides=None):
    """Resolve immutable contracts and current ACLs in the save/start transaction."""
    nodes = definition['nodes']
    errors = []
    catalog = getattr(service, 'api_catalog', None)
    ops = {}
    for job_id, node in nodes.items():
        if 'api_binding' not in node:
            continue
        b = node['api_binding']
        message = binding_shape(node, service._work_prerequisite_jobs(definition, job_id))
        if message:
            errors.append(f'{job_id}: {message}')
            continue
        previous_b = (previous or {}).get('nodes', {}).get(job_id, {}).get('api_binding', {})
        new_selection = for_new and (previous_b.get('operation_id'), previous_b.get('version')) != (b['operation_id'], b['version'])
        try:
            if not catalog:
                _fail('api_unavailable', 'API 명세를 조회할 수 없습니다.')
            op = (overrides or {}).get((b['operation_id'], b['version']))
            if op is None:
                op = catalog.resolve(db, b['operation_id'], b['version'], groups=groups, for_new=new_selection)
        except WorkflowError as exc:
            errors.append(f'{job_id}: {exc.message}')
            continue
        ops[job_id] = op
        read = op['method'] in ('GET', 'HEAD', 'OPTIONS')
        if (node.get('result_block') == 'change_request') == read:
            errors.append(f'{job_id}: 조회와 변경 요청의 처리 방식을 확인해 주세요.')
        if not read and node.get('read_retry'):
            errors.append(f'{job_id}: 변경 요청에는 조회 자동 재시도를 설정할 수 없습니다.')
        inputs = {field['name']: field for field in op['inputs']}
        if any(key not in inputs for key in b['inputs']) or any(f.get('required') and name not in b['inputs'] for name, f in inputs.items()):
            errors.append(f'{job_id}: API의 필수 입력과 불필요한 연결을 확인해 주세요.')
        if set(b['outputs']) - {f['path'] for f in op['fields']}:
            errors.append(f'{job_id}: 명세에서 사용할 수 있는 결과 항목을 선택해 주세요.')
    for job_id, op in ops.items():
        node = nodes[job_id]
        b = node['api_binding']
        local = {f['id']: f for f in node.get('inputs', [])}
        for f in op['inputs']:
            source = b['inputs'].get(f['name'], {})
            if not source:
                continue
            expected = f['type']
            if 'constant' in source:
                ok = _compatible(_kind(source['constant']), expected)
            elif 'context' in source:
                ok = expected == 'string'
            elif 'input' in source:
                declared = local[source['input']]['type']
                ok = declared in {'string': ('text', 'single','datetime'), 'number':('number',),
                                  'integer':('number',), 'array':('list','multi'), 'boolean':('boolean',), 'object':('json_object',)}.get(expected, ())
            else:
                ref = source['result']
                upstream = ops.get(ref['job_id'])
                selected = nodes[ref['job_id']].get('api_binding', {}).get('outputs', [])
                result_type = next((out['type'] for out in (upstream or {}).get('fields', []) if out['path'] == ref['field']), None)
                ok = ref['field'] in selected and result_type and (expected == 'array' or _compatible(result_type, expected))
            if not ok:
                errors.append(f"{node['name']} · {f.get('label') or f['name']}: 입력 형식과 연결한 값을 확인해 주세요.")
    return errors


def _uses_in(definition, api_id, state, row, *, selected=None):
    nodes = definition.get('nodes', {})
    for node in nodes.values():
        b = node.get('api_binding') or {}
        if b.get('operation_id') != api_id or selected is not None and node['id'] not in selected:
            continue
        deps = []
        for other in nodes.values():
            for name, source in (other.get('api_binding') or {}).get('inputs', {}).items():
                ref = source.get('result', {})
                if ref.get('job_id') == node['id']:
                    deps.append({'job_id': other['id'], 'job_name': other['name'], 'input': name, 'field': ref['field']})
        yield {'workflow_id': row['id'], 'workflow_name': definition['name'], 'revision': row['revision'],
               'stage_name': nodes.get(node.get('parent'), {}).get('name', ''), 'job_id': node['id'],
               'job_name': node['name'], 'kind': state, 'version': b['version'], 'fields': b['outputs'],
               'dependent_inputs': deps, 'editable': state == 'draft'}


def api_uses(service, db, actor, groups, api_id):
    uses = []
    for row in db.execute('SELECT * FROM work_definitions'):
        try:
            service._work_definition(db, actor, groups, row['id'])
        except WorkflowError:
            continue
        try:
            service._work_definition(db, actor, groups, row['id'], True)
        except WorkflowError:
            pass
        else:
            uses.extend(_uses_in(json.loads(row['draft']), api_id, 'draft', row))
        saved = db.execute('SELECT definition FROM work_versions WHERE workflow_id=? AND version=?',
                           (row['id'], row['published_version'])).fetchone()
        if saved:
            uses.extend(_uses_in(json.loads(saved[0]), api_id, 'published', row))
        for sched in db.execute('SELECT id,data FROM work_schedules WHERE workflow_id=?', (row['id'],)):
            cfg = json.loads(sched['data'])
            if not cfg.get('delegated'):
                continue
            try:
                service._work_authorize_scope(db, actor, groups, row['system_id'], cfg.get('factory_id', ''), 'viewer')
            except WorkflowError:
                continue
            version = db.execute('SELECT definition FROM work_versions WHERE workflow_id=? AND version=?',
                                 (row['id'], cfg['version'])).fetchone()
            if version:
                uses.extend(dict(u, schedule_id=sched['id']) for u in _uses_in(json.loads(version[0]), api_id, 'schedule', row, selected=cfg.get('job_ids', [])))
    return uses


def apply_api_repairs(service, db, actor, groups, old, new, repairs):
    """Update explicitly selected editable drafts, never versions, schedules or runs."""
    if not isinstance(repairs, list) or len(repairs) > 250:
        _fail('api_repairs_invalid', '작업 재연결 내용을 확인해 주세요.')
    old_fields = {f['path']: f['type'] for f in old['fields']}
    new_fields = {f['path']: f['type'] for f in new['fields']}
    broken = {k for k, typ in old_fields.items() if new_fields.get(k) != typ}
    uses = api_uses(service, db, actor, groups, old['id'])
    affected = {u['workflow_id'] for u in uses if u['editable'] and u['version'] == old['version'] and broken.intersection(u['fields'])}
    if any(not isinstance(item, dict) or not _tokens(item.get('workflow_id')) for item in repairs):
        _fail('api_repairs_invalid', '재연결할 절차를 확인해 주세요.')
    ids = [item['workflow_id'] for item in repairs]
    if len(set(ids)) != len(ids) or affected - set(ids):
        _fail('api_repairs_required', '영향을 받는 절차의 대체 결과 필드를 지정하세요.')
    plans = []
    for repair in repairs:
        row = service._work_definition(db, actor, groups, repair['workflow_id'], True)
        if type(repair.get('expected_revision')) is not int or row['revision'] != repair['expected_revision']:
            _fail('revision_conflict', '업무 절차가 변경되었습니다. 영향 범위를 다시 확인해 주세요.')
        mapping = repair.get('fields')
        if (not isinstance(mapping, dict) or any(k not in old_fields or not isinstance(v, str) or
                (v != '@manual' and (v not in new_fields or not _compatible(new_fields[v], old_fields[k])))
                for k, v in mapping.items())):
            _fail('api_repairs_invalid', '기존 입력과 호환되는 결과 필드를 지정해 주세요.')
        definition = json.loads(row['draft'])
        targets = set()
        for node in definition['nodes'].values():
            b = node.get('api_binding') or {}
            if b.get('operation_id') == old['id'] and b['version'] == old['version']:
                b['version'] = new['version']
                b['outputs'] = list(dict.fromkeys(mapping.get(p, p) for p in b['outputs'] if mapping.get(p) != '@manual'))
                targets.add(node['id'])
        if not targets:
            _fail('api_repairs_invalid', '재연결할 작업을 다시 확인해 주세요.')
        for node in definition['nodes'].values():
            binding = node.get('api_binding') or {}
            for name, source in binding.get('inputs', {}).items():
                ref = source.get('result', {})
                if ref.get('job_id') not in targets:
                    continue
                dest = mapping.get(ref['field'], ref['field'])
                if dest != '@manual':
                    ref['field'] = dest
                    continue
                op = new if (binding['operation_id'], binding['version']) == (new['id'], new['version']) else service.api_catalog.resolve(
                    db, binding['operation_id'], binding['version'], groups=groups)
                arg = next((f for f in op['inputs'] if f['name'] == name), None)
                kind = {'string':'text', 'integer':'number', 'number':'number', 'boolean':'boolean',
                        'array':'list', 'object':'json_object'}.get(arg['type']) if arg else None
                if not kind:
                    _fail('api_repairs_invalid', '다음 작업의 입력 형식을 확인해 주세요.')
                field_id = 'api-input-' + uuid4().hex
                node.setdefault('inputs', []).append({'id':field_id,'type':kind,'name':arg.get('label') or name,
                    'required':bool(arg.get('required')),'scope':'run','source':{'api_operation_id':op['id']}})
                binding['inputs'][name] = {'input':field_id}
        errs = binding_errors(service, db, groups, definition, overrides={(new['id'],new['version']):new})
        if errs:
            _fail('api_repairs_invalid', '\n'.join(errs))
        plans.append((row['id'], _dump(definition)))
    for workflow_id, data in plans:
        db.execute('UPDATE work_definitions SET draft=?,revision=revision+1,validation=NULL,updated_at=? WHERE id=?', (data,_now(),workflow_id))
