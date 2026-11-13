"""Perform declared HTTP operations against deployment-owned service endpoints."""
import asyncio
from copy import deepcopy
import http.client
import json
import math
import os
import re
import socket
import ssl
import time
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from .ees_workflow_authoring import WorkflowError

READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
LIMIT = 1024 * 1024
TIMEOUT = 12
SECRET_NAME = re.compile(r'authorization|cookie|password|secret|token|credential|api[-_]?key|(^|_)pat($|_)', re.I)
HEADER_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,99}')
TRANSPORT_HEADERS = {'host', 'connection', 'content-length', 'content-type', 'transfer-encoding', 'expect', 'te', 'trailer', 'upgrade', 'forwarded', 'accept-encoding', 'x-http-method', 'x-http-method-override', 'x-method-override', 'x-http-method-override-original'}


def fail(code, message):
    raise WorkflowError(code, message)


def _registry():
    try:
        values = json.loads(os.environ.get('EES_WORK_API_SERVICES', '{}'))
        if isinstance(values, dict) and all(isinstance(config, dict) for config in values.values()):
            return values
    except (ValueError, TypeError):
        pass
    fail('api_service_config_invalid', '서버의 API 서비스 설정을 확인해 주세요.')


def _parts(address, *, allow_query=False):
    if not isinstance(address, str) or not address or re.search(r'[\x00-\x20\x7f\\]', address):
        fail('api_address_invalid', '유효한 서비스 주소를 입력해 주세요.')
    try:
        url = urlsplit(address)
        port = url.port
        if url.scheme not in ('https', 'http') or not url.hostname or url.username is not None or url.password is not None or url.fragment or port == 0:
            raise ValueError()
        if url.query:
            if not allow_query: raise ValueError()
            if any(SECRET_NAME.search(key) for key, _ in parse_qsl(url.query,keep_blank_values=True,max_num_fields=200)):
                raise ValueError()
        path = url.path or '/'
        # Check nested escaping before comparing a URL to the configured prefix.
        for _ in range(8):
            decoded = unquote(path)
            if re.search(r'[\x00-\x1f\x7f\\?#]', decoded) or any(s in ('.', '..') for s in decoded.split('/')) or '//' in decoded:
                raise ValueError()
            if decoded == path:
                return url, (url.scheme, url.hostname.lower(), port or (443 if url.scheme == 'https' else 80))
            if decoded.count('/') != path.count('/'):
                raise ValueError()
            path = decoded
    except (ValueError, UnicodeError):
        pass
    fail('api_address_invalid', '서비스 주소, 포트 또는 경로를 확인해 주세요.')


def _allowed(url, base):
    target, origin = _parts(url,allow_query=True)
    configured, allowed_origin = _parts(base)
    prefix = configured.path.rstrip('/')
    return origin == allowed_origin and ((target.path or '/') == prefix or (target.path or '/').startswith(prefix + '/'))


def _actor_id(actor):
    return actor.get('id') if isinstance(actor, dict) else getattr(actor, 'id', None)


def _service(config, actor):
    if not config or not config.get('base_url'):
        fail('api_service_unconfigured', '서버에 이 서비스의 허용 주소를 설정해 주세요.')
    allowed = config.get('actor_ids')
    if allowed is not None and (not isinstance(allowed, list) or _actor_id(actor) not in allowed):
        fail('access_denied', '현재 계정은 이 서비스에 접근할 수 없습니다.')
    return config


def _headers(config, actor, scheme):
    # Credentials are references to environment variables provisioned on the server.
    # A per-user mapping, when configured, must never fall back to another identity.
    references = config.get('credential_headers', {})
    if 'user_credential_headers' in config:
        by_user = config['user_credential_headers']
        if not isinstance(by_user, dict) or _actor_id(actor) not in by_user:
            fail('api_auth_required', '현재 사용자의 서비스 인증 설정을 확인해 주세요.')
        references = by_user[_actor_id(actor)]
    if not isinstance(references, dict):
        fail('api_service_config_invalid', '서비스 인증 헤더 설정을 확인해 주세요.')
    if references and scheme != 'https':
        fail('api_auth_requires_tls', '인증 정보를 전송하려면 HTTPS 서비스 주소가 필요합니다.')
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    for header, variable in references.items():
        if not isinstance(header, str) or not HEADER_NAME.fullmatch(header) or header.lower() in TRANSPORT_HEADERS or not isinstance(variable, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', variable):
            fail('api_service_config_invalid', '서비스 인증 헤더 설정을 확인해 주세요.')
        secret = os.environ.get(variable, '')
        if not secret or len(secret) > 12000 or not secret.isascii() or re.search(r'[\x00-\x1f\x7f]', secret):
            fail('api_auth_required', '서비스에서 요구하는 인증 정보를 확인해 주세요.')
        headers[header] = secret
    return headers, tuple(headers[k] for k in references)


def _matches(value, kind):
    return {'string': isinstance(value, str), 'integer': type(value) is int,
            'number': type(value) in (int,float) and (type(value) is int or math.isfinite(value)),
            'boolean': type(value) is bool, 'array': isinstance(value, list), 'object': isinstance(value, dict),
            'null': value is None, 'any': True}.get(kind, False)


def _wire(value):
    if isinstance(value, str): return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _path(value, path):
    for key in path.split('.') if path else ():
        if not isinstance(value, dict) or key not in value:
            fail('api_result_mapping_invalid', '실제 응답에서 연결한 결과 경로를 찾지 못했습니다.')
        value = value[key]
    return value


def _safe_output(value, secrets, depth=0):
    if depth > 12:
        fail('api_response_too_large', '응답 구조나 크기가 허용 범위를 초과했습니다.')
    if isinstance(value, dict):
        return {key: _safe_output(child, secrets, depth+1) for key, child in value.items() if not SECRET_NAME.search(key)}
    if isinstance(value, list):
        if len(value) > 500: fail('api_response_too_large', '응답 항목 수가 허용 범위를 초과했습니다.')
        return [_safe_output(child, secrets, depth+1) for child in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, '[가림]')
            parts = secret.split()
            if len(parts) > 1: value = value.replace(parts[-1], '[가림]')
    if isinstance(value, float) and not math.isfinite(value): fail('api_response_invalid', '응답 숫자 형식을 확인해 주세요.')
    return value


def _target(operation, arguments, config, actor):
    base = config['base_url']
    address = operation.get('url', '')
    if address.startswith('/') and not address.startswith('//'):
        address = base.rstrip('/') + address
    if not _allowed(address, base):
        fail('api_target_forbidden', '이 서비스에 허용된 주소와 경로만 호출할 수 있습니다.')
    target, origin = _parts(address,allow_query=True)
    headers, secrets = _headers(config, actor, origin[0])
    method = operation['method']
    if method not in READ_METHODS | WRITE_METHODS:
        fail('api_method_unsupported', '지원하는 HTTP 요청 방식을 선택해 주세요.')
    fields = {field['name']:field for field in operation['inputs']}
    if not isinstance(arguments, dict) or set(arguments) - set(fields):
        fail('api_arguments_invalid', '등록한 API 입력 항목을 확인해 주세요.')
    path, query, body = target.path or '/', [], {}
    supplied = {field.get('wire_name',field['name']) for field in fields.values() if field['in']=='query' and field['name'] in arguments}
    rendered = set()
    body_present = False
    has_whole_body = any(field.get('whole_body') for field in fields.values())
    if has_whole_body and sum(field['in'] == 'body' for field in fields.values()) != 1:
        fail('api_arguments_invalid', '전체 JSON 본문과 개별 본문 필드를 함께 보낼 수 없습니다.')
    for key, val in parse_qsl(target.query,keep_blank_values=True,max_num_fields=200):
        placeholder = re.fullmatch(r'\{([^{}]+)\}',val)
        if placeholder:
            mapped = next((field for field in fields.values() if field['in']=='query' and (placeholder[1] in (field['name'],field.get('wire_name',field['name'])) or key == field.get('wire_name',field['name']))),None)
            if not mapped: fail('api_arguments_invalid','쿼리 변수 정의를 확인해 주세요.')
            rendered.add(mapped['name'])
            if mapped['name'] in arguments:
                values = arguments[mapped['name']]
                query.extend((key,_wire(v)) for v in (values if isinstance(values,list) else [values]))
            continue
        if key not in supplied: query.append((key,val))
    for name, field in fields.items():
        if name not in arguments:
            if field.get('required'): fail('api_input_required', '필수 API 입력이 없습니다: ' + name)
            continue
        val, place, wire = arguments[name], field['in'], field.get('wire_name', name)
        if not _matches(val, field['type']): fail('api_input_type', 'API 입력 자료형을 확인해 주세요: ' + name)
        if place == 'path':
            if '{' + wire + '}' not in path or _wire(val) in ('', '.', '..') or re.search(r'[/\\%?#\x00-\x1f]', _wire(val)):
                fail('api_path_invalid', '주소 경로 입력을 확인해 주세요.')
            path = path.replace('{'+wire+'}', quote(_wire(val), safe=''))
        elif place == 'query':
            if wire in rendered or name in rendered: continue
            query.extend((wire, _wire(v)) for v in (val if isinstance(val, list) else [val]))
        elif place == 'header':
            if not HEADER_NAME.fullmatch(wire) or SECRET_NAME.search(wire) or wire.lower() in {h.lower() for h in headers} | TRANSPORT_HEADERS or wire.lower().startswith(('proxy-', 'x-forwarded-', 'x-original-', 'x-rewrite-')) or not _wire(val).isascii() or re.search(r'[\x00-\x1f\x7f]', _wire(val)):
                fail('api_header_forbidden', '전송할 수 없는 API 헤더입니다.')
            headers[wire] = _wire(val)
        elif place == 'body' and method in WRITE_METHODS:
            body_present = True
            if field.get('whole_body'):
                body = val
                continue
            node = body
            segments = field.get('body_path') or wire.split('.')
            for key in segments[:-1]:
                node = node.setdefault(key, {})
                if not isinstance(node, dict): fail('api_arguments_invalid', '요청 본문 필드 경로가 겹칩니다.')
            if segments[-1] in node: fail('api_arguments_invalid', '요청 본문 필드 경로가 겹칩니다.')
            node[segments[-1]] = deepcopy(val)
        else:
            fail('api_input_location_unsupported', '이 방식에서는 해당 입력 위치를 전송할 수 없습니다.')
    if '{' in path or '}' in path: fail('api_input_required', '주소 경로 입력을 확인해 주세요.')
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    if query: path += '?' + urlencode(query)
    data = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode() if body_present else None
    if data: headers['Content-Type'] = 'application/json'
    if len(path) > 16384 or data and len(data)>LIMIT:
        fail('api_input_too_large', '요청 크기를 줄여 주세요.')
    return origin, method, path, headers, data, secrets


def _exchange(origin, method, path, headers, body):
    deadline = time.monotonic() + TIMEOUT
    scheme, host, port = origin
    conn = (http.client.HTTPSConnection(host, port, context=ssl.create_default_context(), timeout=TIMEOUT) if scheme == 'https' else http.client.HTTPConnection(host, port, timeout=TIMEOUT))
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        if 300 <= response.status < 400:
            fail('api_redirect_refused', '서비스가 다른 주소로 이동을 요청했습니다. 등록된 주소를 확인해 주세요.')
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fail('api_io_unknown', '서비스 응답 제한 시간을 초과했습니다.')
            if conn.sock:
                conn.sock.settimeout(remaining)
            chunk = response.read1(min(64 * 1024, LIMIT + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > LIMIT:
                fail('api_response_too_large', '응답 크기가 허용 범위를 초과했습니다.')
        return response.status, bytes(raw)
    except (OSError, http.client.HTTPException, socket.timeout) as error:
        raise WorkflowError('api_io_unknown', '서비스 응답을 확인하지 못했습니다.') from error
    finally:
        conn.close()


def _configured_target(service_id, address, actor):
    """An explicit service identity always takes precedence, including an unusable one."""
    registry = _registry()
    if not isinstance(address, str) or not address:
        fail('api_address_invalid', '서비스 주소를 확인해 주세요.')
    if service_id in registry:
        config = _service(registry[service_id], actor)
        base = config['base_url']
        if address.startswith('/') and not address.startswith('//'):
            address = base.rstrip('/') + address
        if not _allowed(address,base):
            fail('api_target_forbidden', '이 서비스의 허용 주소와 등록 주소가 다릅니다.')
    else:
        # Relative URLs lack an origin; resolving against every credential set would guess an identity.
        if address.startswith('/'):
            fail('api_target_forbidden', '상대 경로에는 해당 서비스의 허용 주소가 필요합니다.')
        matches = [config for config in registry.values()
                   if config.get('base_url') and _allowed(address, config['base_url'])]
        if len(matches) != 1:
            fail('api_target_forbidden', '등록 주소와 일치하는 서버 허용 서비스를 하나 지정해 주세요.')
        config = _service(matches[0], actor)
    _headers(config, actor, _parts(address,allow_query=True)[1][0])
    return config, address


async def fetch_spec(url, service_id=None, actor=None):
    config, address = _configured_target(service_id, url, actor)
    target, origin = _parts(address)
    headers, _ = _headers(config, actor, origin[0])
    status, data = await asyncio.to_thread(_exchange, origin, 'GET', quote(target.path or '/', safe='/%:@-._~'), headers, None)
    if not 200 <= status < 300:
        fail('api_spec_fetch_failed', '서비스에서 명세를 읽지 못했습니다.')
    try:
        return data.decode('utf-8-sig')
    except UnicodeError:
        fail('api_spec_encoding_invalid', 'UTF-8 명세를 사용해 주세요.')


def authorize_service(operation, actor):
    config, _ = _configured_target(operation['service_id'], operation['url'], actor)
    return config


def prepare_request(operation, arguments, actor):
    return _target(operation,arguments,authorize_service(operation,actor),actor)


async def invoke_http(operation, arguments, actor, *, outputs=None, preview=False, correlation_id=None):
    origin, method, path, headers, data, secrets = prepare_request(operation, arguments, actor)
    if preview:
        return {'preview': True, 'method': method, 'path': urlsplit(operation['url']).path, 'argument_names': list(arguments), 'status':'preview', 'items':[], 'count':0}
    observation = {}
    if correlation_id and method in WRITE_METHODS:
        observation = authorize_service(operation, actor).get('observations', {}).get(operation['id'], {})
        header = observation.get('correlation_header')
        if header:
            if not HEADER_NAME.fullmatch(header) or SECRET_NAME.search(header) or header.lower() in TRANSPORT_HEADERS | {key.lower() for key in headers}:
                fail('api_service_config_invalid','서비스 추적 헤더 설정을 확인해 주세요.')
            headers[header] = correlation_id
    status, raw = await asyncio.to_thread(_exchange, origin, method, path, headers, data)
    result = {'source':'api', 'http_status':status, 'count':0, 'items':[], 'completeness':'unknown'}
    if not 200 <= status < 300:
        return {**result, 'status':'failed' if method in READ_METHODS or 400 <= status < 500 else 'unknown', 'error':{'code':'api_http_error'}}
    fields = operation.get('fields', [])
    chosen = {field['path'] for field in fields} if outputs is None else set(outputs)
    result['field_labels'] = {field['path']: field.get('label',field['path']) for field in fields if field['path'] in chosen}
    if chosen - {field['path'] for field in fields}: fail('api_result_mapping_invalid', '연결한 결과 필드를 확인해 주세요.')
    if status == 204 or method == 'HEAD' or not raw and not chosen:
        return {**result, 'status':'succeeded','completeness':'empty'}
    try: parsed = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError): fail('api_response_invalid','서비스 응답을 JSON으로 읽을 수 없습니다.')
    if observation.get('job_number_field'):
        number = _path(parsed, observation['job_number_field'])
        if type(number) not in (str,int) or not str(number) or len(str(number)) > 256:
            fail('api_observation_id_required','서비스 추적 번호를 확인할 수 없습니다.')
        result['job_number'] = _safe_output(str(number), secrets)
    root = _path(parsed, operation.get('result_path',''))
    rows = root if isinstance(root,list) else [root]
    if len(rows)>500: fail('api_response_too_large','결과 항목 수가 허용 범위를 초과했습니다.')
    items=[]
    for i, row in enumerate(rows):
        projected = {}
        for field in fields:
            key = field['path']
            if key not in chosen: continue
            if SECRET_NAME.search(key): fail('api_result_mapping_invalid','인증 정보는 결과로 표시할 수 없습니다.')
            val = row if key == '$' and field.get('root_value') is True else _path(row, key)
            if not _matches(val,field.get('type','any')): fail('api_result_mapping_invalid','실제 응답이 연결한 결과 자료형과 다릅니다.')
            projected[key] = _safe_output(val,secrets)
        items.append({'id':'row-'+str(i+1),'row':projected,'title':str(next(iter(projected.values()), '결과 '+str(i+1)))[:250]})
    partial = isinstance(parsed,dict) and any(parsed.get(key) is True for key in ('has_more','partial','truncated'))
    projection = {**result,'status':'partial' if partial else 'succeeded','completeness':'partial' if partial else 'complete' if items else 'empty','count':len(items),'items':items}
    if len(_wire(projection).encode()) > 256_000:
        fail('api_response_too_large','표시할 결과 크기가 허용 범위를 초과했습니다.')
    return projection


def observation_config(operation, actor):
    config = authorize_service(operation, actor)
    observations = config.get('observations', {})
    contract = observations.get(operation['id']) if isinstance(observations, dict) else None
    if not isinstance(contract, dict):
        fail('api_status_unconfigured', '서비스의 상태·효과 조회 계약을 설정해 주세요.')
    return contract


async def observe_http(operation, actor, request, *, effect=False):
    """Read a service's explicitly configured status/effect contract for this request."""
    contract = observation_config(operation, actor)
    spec = contract.get('effect' if effect else 'status')
    if not isinstance(spec, dict) or not isinstance(spec.get('url'), str) or not isinstance(spec.get('field'), str) or not spec['field']:
        fail('api_status_unconfigured', '서비스의 조회 주소와 응답 필드를 설정해 주세요.')
    source = spec.get('identifier', 'job_number')
    if source not in ('job_number', 'correlation_id') or '{id}' not in spec['url'] or not request.get(source):
        fail('api_observation_id_required', '이 요청의 서비스 추적 번호를 확인해 주세요.')
    if source == 'correlation_id' and not contract.get('correlation_header'):
        fail('api_status_unconfigured', '서비스에서 인식하는 추적 번호 계약이 필요합니다.')
    if effect and (not isinstance(spec.get('criterion'), dict) or not spec['criterion'] or spec['criterion'] != request.get('effect_criterion')):
        fail('api_effect_criterion_mismatch', '이 작업의 효과 확인 조건과 서비스 조회 조건이 다릅니다.')
    probe = {**operation, 'method':'GET', 'url':spec['url'], 'inputs':[{'name':'id','in':'path','required':True,'type':'string'}],
             'result_path':'', 'fields':[{'path':spec['field'],'type':'any','label':spec['field']}]}
    response = await invoke_http(probe, {'id':str(request[source])}, actor)
    if response['status'] != 'succeeded' or response['count'] != 1:
        fail('api_observation_unknown', '이 요청의 서비스 조회 응답을 확인하지 못했습니다.')
    actual = response['items'][0]['row'][spec['field']]
    if effect:
        if 'equals' not in spec: fail('api_status_unconfigured', '효과 확인 기준 값을 설정해 주세요.')
        return {'satisfied':type(actual) is type(spec['equals']) and actual == spec['equals'],
                'evidence':[{'field':spec['field'], 'observed': actual, 'http_status':response['http_status']}]}
    state = spec.get('states', {}).get(str(actual)) if isinstance(spec.get('states'), dict) else None
    if state not in ('accepted','running','reported_complete','rejected','failed','unknown'):
        return {'state':'unknown', 'reason':'api_observation_unknown'}
    return {'state':state}
