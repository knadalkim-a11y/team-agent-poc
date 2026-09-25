"""Versioned, data-only execution contracts. Never evaluates code or templates.

Native is the source for code/auth/schema. This module validates references and
bounded public values, connects persisted results, and verifies business output.
"""
from copy import deepcopy
import hashlib
import json
import re

PROTOCOL = 1
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
REFERENCE_FIELDS = {"tool_id", "function", "revision", "content_hash", "schema_hash", "config_hash", "environment"}
RESERVED = {"user", "user_id", "role", "owner", "owner_id", "headers", "cookie", "cookies", "token", "pat", "password", "api_key", "authorization", "base_url", "url", "request", "metadata"}
FORMATS = {"page_id": r"[0-9]{1,30}", "issue_key": r"[A-Z][A-Z0-9_]{0,63}-[1-9][0-9]{0,18}", "repository": r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}"}
VALIDATORS = {"all_complete_v1", "observed_v1", "selection_v1", "grounded_summary_v1"}
COMPLETENESS = {"complete", "partial", "empty", "truncated", "unknown"}


class ContractError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _fail(code, message):
    raise ContractError(code, message)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _public_key(key):
    return isinstance(key, str) and bool(IDENTIFIER.fullmatch(key)) and not key.startswith("_") and key.lower() not in RESERVED


def _safe_data(value, depth=0):
    if depth > 8:
        return False
    if value is None or type(value) in (bool, int):
        return True
    if isinstance(value, str):
        return len(value) <= 20000
    if isinstance(value, list):
        return len(value) <= 100 and all(_safe_data(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= 64 and all(_public_key(key) and _safe_data(item, depth + 1) for key, item in value.items())
    return False


def schema_errors(schema, depth=0):
    if not isinstance(schema, dict) or depth > 5:
        return ["공개 입력의 형식을 확인해 주세요."]
    kind = schema.get("type")
    allowed = {"type", "title", "description", "enum", "default"}
    allowed |= {"string": {"minLength", "maxLength", "format"}, "integer": {"minimum", "maximum"}, "boolean": set(), "array": {"items", "minItems", "maxItems"}, "object": {"properties", "required", "additionalProperties"}}.get(kind, set())
    errors = []
    if kind not in ("string", "integer", "boolean", "array", "object") or set(schema) - allowed:
        return ["지원하는 제한된 공개 입력 형식만 사용해 주세요."]
    if any(not isinstance(schema[key], str) or len(schema[key]) > 500 for key in ("title", "description") if key in schema):
        errors.append("입력 설명을 확인해 주세요.")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not 1 <= len(schema["enum"]) <= 100 or any(type(v) not in (str, int, bool) for v in schema["enum"])):
        errors.append("선택값의 형식을 확인해 주세요.")
    if kind == "object":
        props = schema.get("properties")
        if not isinstance(props, dict) or len(props) > 64 or any(not _public_key(k) for k in props) or schema.get("additionalProperties") is not False:
            return errors + ["입력 객체는 공개 항목만 명시하고 추가 항목을 차단해야 합니다."]
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(k, str) or k not in props for k in required) or len(required) != len(set(required)):
            errors.append("필수 입력을 확인해 주세요.")
        for item in props.values():
            errors.extend(schema_errors(item, depth + 1))
    elif kind == "array":
        if type(schema.get("maxItems")) is not int or not 1 <= schema["maxItems"] <= 100:
            errors.append("배열의 최대 항목 수는 1~100이어야 합니다.")
        errors.extend(schema_errors(schema.get("items"), depth + 1))
    elif kind == "string":
        if type(schema.get("maxLength")) is not int or not 1 <= schema["maxLength"] <= 20000:
            errors.append("문자열의 최대 길이를 정해 주세요.")
        if "format" in schema and schema["format"] not in FORMATS:
            errors.append("지원하는 식별자 형식을 사용해 주세요.")
    for lower, upper in (("minLength", "maxLength"), ("minItems", "maxItems"), ("minimum", "maximum")):
        for key in (lower, upper):
            if key in schema and (type(schema[key]) is not int or abs(schema[key]) > 10**12):
                errors.append("입력 범위를 확인해 주세요.")
        if type(schema.get(lower)) is int and type(schema.get(upper)) is int and schema[lower] > schema[upper]:
            errors.append("최소 입력 범위가 최대 범위보다 큽니다.")
    if "default" in schema and not errors:
        errors.extend(_value_errors(schema, schema["default"], "default", False))
    return errors


def _value_errors(schema, value, path, partial):
    kind, errors = schema["type"], []
    types = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}
    if type(value) is not types[kind]:
        return [f"{path}: 입력 타입이 다릅니다."]
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        errors.append(f"{path}: 허용된 선택값이 아닙니다.")
    if kind == "object":
        props = schema["properties"]
        if any(key not in props or not _public_key(key) for key in value):
            errors.append(f"{path}: 정의하지 않은 입력이 있습니다.")
        if not partial and any(key not in value for key in schema.get("required", [])):
            errors.append(f"{path}: 필수 입력이 없습니다.")
        for key, child in value.items():
            if key in props:
                errors.extend(_value_errors(props[key], child, path + "." + key, False))
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema["maxItems"]:
            errors.append(f"{path}: 항목 수가 허용 범위를 벗어났습니다.")
        for index, child in enumerate(value[:100]):
            errors.extend(_value_errors(schema["items"], child, path + f"[{index}]", False))
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema["maxLength"]:
            errors.append(f"{path}: 글자 수가 허용 범위를 벗어났습니다.")
        if "format" in schema and not re.fullmatch(FORMATS[schema["format"]], value):
            errors.append(f"{path}: 식별자 형식이 다릅니다.")
    elif kind == "integer" and not schema.get("minimum", -10**12) <= value <= schema.get("maximum", 10**12):
        errors.append(f"{path}: 숫자가 허용 범위를 벗어났습니다.")
    return errors


def validate_inputs(schema, inputs, partial=True):
    errors = schema_errors(schema)
    if errors:
        return errors
    return _value_errors(schema, inputs, "inputs", partial)


def reference_errors(reference):
    if not isinstance(reference, dict) or set(reference) != REFERENCE_FIELDS:
        return ["실제 도구·함수의 승인 참조를 모두 지정해 주세요."]
    if (not all(isinstance(reference[k], str) and IDENTIFIER.fullmatch(reference[k]) for k in ("tool_id", "function", "environment"))
            or reference["function"].startswith("_") or type(reference["revision"]) is not int or reference["revision"] < 1
            or any(not isinstance(reference[k], str) or not HASH.fullmatch(reference[k]) for k in ("content_hash", "schema_hash", "config_hash"))):
        return ["실제 도구 참조의 함수·버전·해시를 확인해 주세요."]
    return []


def _path_ok(path):
    return isinstance(path, list) and len(path) <= 12 and all((type(key) is int and 0 <= key < 1000) or (isinstance(key, str) and _public_key(key)) for key in path)


def _root(nodes, node_id):
    seen = set()
    while node_id in nodes and node_id not in seen:
        seen.add(node_id)
        if nodes[node_id].get("parent") is None:
            return node_id
        node_id = nodes[node_id].get("parent")
    return None


def _prerequisite_jobs(nodes, node_id):
    """Expand declared dependencies only; binding paths never schedule work."""
    result, visited, pending = set(), set(), [node_id]
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        ancestor, ancestors = nodes.get(key), set()
        deps = []
        while isinstance(ancestor, dict) and ancestor.get("id") not in ancestors:
            ancestors.add(ancestor.get("id"))
            deps.extend(ancestor.get("deps", []))
            ancestor = nodes.get(ancestor.get("parent"))
        children, seen = list(deps), set()
        while children:
            dep_id = children.pop()
            if dep_id in seen or dep_id not in nodes:
                continue
            seen.add(dep_id)
            dep = nodes[dep_id]
            if dep.get("type") == "j":
                result.add(dep_id)
                pending.append(dep_id)
            else:
                children.extend(dep.get("children", []))
    return result


def _binding_errors(binding, node, definition, preceding=()):
    if not isinstance(binding, dict):
        return ["입력 연결 형식을 확인해 주세요."]
    source, errors = binding.get("source"), []
    allowed = {"source", "transform"}
    allowed |= {"input": {"key", "selection"}, "constant": {"value"}, "result": {"job_id", "call_id", "path"}}.get(source, set())
    if source not in ("input", "constant", "result") or set(binding) - allowed:
        return ["공개 입력·상수·저장된 결과만 연결할 수 있습니다."]
    if binding.get("transform", "identity") not in ("identity", "strip", "to_string", "to_integer"):
        errors.append("허용하지 않은 입력 변환입니다.")
    root = definition.get("nodes", {}).get(_root(definition.get("nodes", {}), node.get("id")), {})
    if source == "input" and binding.get("key") not in root.get("execution_inputs", {}).get("properties", {}):
        errors.append("정의된 공개 입력만 연결해 주세요.")
    if source == "constant" and ("value" not in binding or not _safe_data(binding["value"])):
        errors.append("공개 상수의 타입과 크기를 확인해 주세요.")
    references = [binding] if source == "result" else []
    if "selection" in binding:
        selection = binding["selection"]
        if not isinstance(selection, dict) or set(selection) != {"job_id", "call_id", "path", "value_path"} or not _path_ok(selection.get("value_path")):
            errors.append("검색 결과 선택 연결을 확인해 주세요.")
        else:
            references.append(selection)
    for ref in references:
        nodes = definition.get("nodes", {})
        other = nodes.get(ref.get("job_id"), {})
        calls = other.get("execution", {}).get("calls", [])
        if (other.get("type") != "j" or _root(nodes, ref.get("job_id")) != _root(nodes, node.get("id"))
                or ref.get("call_id") not in [call.get("id") for call in calls] or not _path_ok(ref.get("path"))):
            errors.append("같은 절차의 저장된 결과 경로만 연결해 주세요.")
        if ref.get("job_id") == node.get("id") and ref.get("call_id") not in preceding:
            errors.append("같은 작업의 앞 호출 결과만 연결할 수 있습니다.")
        elif ref.get("job_id") != node.get("id") and ref.get("job_id") not in _prerequisite_jobs(nodes, node.get("id")):
            errors.append("앞 결과를 사용하려면 해당 작업을 선행 조건에 연결해 주세요.")
    return errors


def validate_execution(node, definition):
    """Validate only the additive protocol; absence preserves legacy behavior."""
    errors = []
    if "execution_inputs" in node:
        if node.get("type") != "p":
            errors.append("공개 실행 입력은 최상위 절차에 정의해 주세요.")
        errors.extend(schema_errors(node["execution_inputs"]))
    if "execution_final" in node:
        final = node["execution_final"]
        if (node.get("type") not in ("p", "t") or not isinstance(final, dict)
                or set(final) != {"validator", "version", "require_complete"} or final.get("validator") != "all_required_v1"
                or final.get("version") != 1 or type(final.get("require_complete")) is not bool):
            errors.append("최종 업무 완료 기준을 확인해 주세요.")
    if "execution" not in node:
        return errors
    execution = node["execution"]
    if (node.get("type") != "j" or not isinstance(execution, dict)
            or set(execution) - {"protocol", "kind", "calls", "completion", "limits", "evidence", "skill_refs", "model_id"}
            or execution.get("protocol") != PROTOCOL or execution.get("kind") not in ("fixed", "ai", "human")):
        return errors + ["지원하는 작업 실행 계약을 사용해 주세요."]
    calls = execution.get("calls")
    if not isinstance(calls, list) or len(calls) > 8:
        return errors + ["작업의 도구 호출은 최대 8개까지 정의할 수 있습니다."]
    kind = execution["kind"]
    model_id = execution.get("model_id")
    if kind == "ai" and (not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 200 or "://" in model_id):
        errors.append("현재 계정으로 접근 가능한 모델을 선택해 주세요.")
    elif kind != "ai" and "model_id" in execution:
        errors.append("고정 실행과 사람 확인에는 모델을 지정하지 않습니다.")
    if (kind == "fixed" and not calls) or (kind in ("ai", "human") and calls):
        errors.append("1차 AI 작업은 저장 근거 요약만, 사람 확인은 입력 확인만 지원합니다.")
    limits = execution.get("limits", {})
    maximum = {"timeout_seconds": 120, "max_tool_calls": 8, "max_model_calls": 4, "max_retries": 1}
    if set(limits) != set(maximum) or any(type(limits.get(key)) is not int or not 0 <= limits[key] <= cap for key, cap in maximum.items()):
        errors.append("실행 시간·호출·재시도 한도를 확인해 주세요.")
    elif (limits["timeout_seconds"] < 1 or limits["max_tool_calls"] < len(calls)
          or (kind == "ai" and limits["max_model_calls"] < 1) or (kind != "ai" and limits["max_model_calls"] != 0)):
        errors.append("실행 방식에 맞는 한도를 지정해 주세요.")
    seen = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"id", "reference", "arguments"} or not isinstance(call.get("id"), str) or not IDENTIFIER.fullmatch(call["id"]) or call["id"] in seen:
            errors.append("호출 식별자와 기능 연결을 확인해 주세요.")
            continue
        errors.extend(reference_errors(call.get("reference")))
        arguments = call.get("arguments")
        if not isinstance(arguments, dict) or len(arguments) > 32 or any(not _public_key(key) for key in arguments):
            errors.append("예약 인자·계정·주소·인증정보는 실행 입력으로 지정할 수 없습니다.")
        else:
            for binding in arguments.values():
                errors.extend(_binding_errors(binding, node, definition, seen))
        seen.append(call["id"])
    completion = execution.get("completion")
    if not isinstance(completion, dict) or set(completion) - {"validator", "version", "input_key", "choices", "required_claims"} or completion.get("validator") not in VALIDATORS or completion.get("version") != 1:
        errors.append("완료 검증기와 버전을 지정해 주세요.")
    else:
        expected = {"fixed": {"all_complete_v1", "observed_v1"}, "ai": {"grounded_summary_v1"}, "human": {"selection_v1"}}[kind]
        if completion["validator"] not in expected:
            errors.append("수행 방식과 완료 검증기가 다릅니다.")
        required_claims = completion.get("required_claims", [])
        if not isinstance(required_claims, list) or len(required_claims) > 40 or (required_claims and kind != "ai"):
            errors.append("필수 요약 근거 경로를 확인해 주세요.")
        else:
            for required in required_claims:
                if not isinstance(required, dict) or set(required) != {"job_id", "call_id", "path"} or not _path_ok(required.get("path")) or len(required["path"]) < 2 or required["path"][0] != "data":
                    errors.append("필수 요약 근거는 구체적인 저장 값의 경로여야 합니다.")
                elif {"job_id": required["job_id"], "call_id": required["call_id"]} not in execution.get("evidence", []):
                    errors.append("필수 요약 근거는 선언된 자료 범위에 속해야 합니다.")
        if kind == "human":
            errors.extend(_binding_errors({"source": "input", "key": completion.get("input_key"), **({"selection": completion["choices"]} if "choices" in completion else {})}, node, definition))
    evidence = execution.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > 32 or (kind == "ai" and not evidence):
        errors.append("AI 작업의 저장 근거를 지정해 주세요.")
    else:
        for ref in evidence:
            if not isinstance(ref, dict) or set(ref) != {"job_id", "call_id"}:
                errors.append("근거 식별자를 확인해 주세요.")
                continue
            errors.extend(_binding_errors({"source": "result", **ref, "path": ["data"]}, node, definition))
    skill_refs = execution.get("skill_refs", [])
    if not isinstance(skill_refs, list) or len(skill_refs) > 16:
        errors.append("필요한 스킬 참조를 확인해 주세요.")
    else:
        inherited_native_skills, visited = set(), set()
        current = node
        while isinstance(current, dict) and current.get("id") not in visited:
            visited.add(current.get("id"))
            for skill_id in current.get("skills", []):
                skill = definition.get("skills", {}).get(skill_id, {})
                if skill.get("source") == "open_webui":
                    inherited_native_skills.add(skill.get("reference"))
            current = definition.get("nodes", {}).get(current.get("parent"))
        for ref in skill_refs:
            if (not isinstance(ref, dict) or set(ref) != {"skill_id", "content_hash"}
                    or not isinstance(ref.get("skill_id"), str) or not IDENTIFIER.fullmatch(ref["skill_id"])
                    or not isinstance(ref.get("content_hash"), str) or not HASH.fullmatch(ref["content_hash"])):
                errors.append("스킬 버전 해시를 확인해 주세요.")
            elif ref["skill_id"] not in inherited_native_skills:
                errors.append("해당 P/T/J에 연결한 기존 스킬의 검증 버전만 사용할 수 있습니다.")
    return list(dict.fromkeys(errors))


def _at(value, path):
    if not _path_ok(path):
        _fail("invalid_binding", "결과 연결 경로를 확인해 주세요.")
    try:
        for key in path:
            if not ((type(key) is int and isinstance(value, list)) or (isinstance(key, str) and isinstance(value, dict))):
                raise KeyError(key)
            value = value[key]
    except (KeyError, IndexError, TypeError):
        _fail("result_missing", "앞 작업 결과에 필요한 항목이 없습니다.")
    return deepcopy(value)


def _source(ref, stored_results):
    result = stored_results.get(ref.get("job_id"), {}).get(ref.get("call_id"))
    if not isinstance(result, dict) or result.get("status") != "succeeded":
        _fail("result_unavailable", "검증한 앞 작업 결과가 필요합니다.")
    return result


def resolve_arguments(call, inputs, stored_results):
    arguments = call.get("arguments", {})
    if not isinstance(arguments, dict) or any(not _public_key(key) for key in arguments):
        _fail("reserved_argument", "서버 예약 입력은 지정할 수 없습니다.")
    resolved = {}
    for key, binding in arguments.items():
        source = binding.get("source")
        if source == "constant":
            value = deepcopy(binding.get("value"))
        elif source == "result":
            value = _at(_source(binding, stored_results), binding.get("path"))
        elif source == "input":
            value = inputs.get(binding.get("key"))
            if "selection" in binding:
                selection = binding["selection"]
                rows = _at(_source(selection, stored_results), selection["path"])
                if not isinstance(rows, list) or len(rows) > 100:
                    _fail("invalid_selection", "확인한 검색 후보가 필요합니다.")
                candidates = [_at(row, selection["value_path"]) for row in rows]
                if value is None and len(candidates) == 1:
                    value = candidates[0]
                if value is not None and not any(type(value) is type(candidate) and value == candidate for candidate in candidates):
                    _fail("invalid_selection", "확인한 검색 후보 중에서 선택해 주세요.")
            if value is None:
                _fail("input_required", f"{binding.get('key', '')}: 필요한 입력을 보완해 주세요.")
        else:
            _fail("invalid_binding", "지원하는 입력 연결을 사용해 주세요.")
        transform = binding.get("transform", "identity")
        if transform == "strip" and isinstance(value, str):
            value = value.strip()
        elif transform == "to_string" and type(value) in (str, int):
            value = str(value)
        elif transform == "to_integer" and isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,12}", value):
            value = int(value)
        elif transform != "identity":
            _fail("invalid_binding", "입력 변환 타입이 다릅니다.")
        if not _safe_data(value):
            _fail("invalid_input", "공개 입력의 타입·크기·항목을 확인해 주세요.")
        resolved[key] = value
    return resolved


def _decision(status, validator, reason, evidence=None, output=None, scope_complete=False):
    return {"status": status, "validator": validator, "version": 1, "reason": reason,
            "evidence": evidence or [], "output": output or {}, "scope_complete": scope_complete}


def evaluate_completion(node, job_results, inputs=None, stored_results=None):
    execution = node.get("execution", {})
    completion = execution.get("completion", {})
    validator = completion.get("validator")
    stored_results, inputs = stored_results or {}, inputs or {}
    if validator == "selection_v1":
        binding = {"source": "input", "key": completion.get("input_key")}
        if "choices" in completion:
            binding["selection"] = completion["choices"]
        try:
            output = resolve_arguments({"arguments": {"selection": binding}}, inputs, stored_results)
        except ContractError as error:
            return _decision("waiting_input" if error.code == "input_required" else "failed", validator, error.code)
        if output.get("selection") is False:
            return _decision("failed", validator, "human_confirmation_declined", output=output)
        return _decision("succeeded", validator, "human_input_confirmed", output=output, scope_complete=True)
    if validator in ("all_complete_v1", "observed_v1"):
        evidence, complete, bounded = [], True, True
        for call in execution.get("calls", []):
            result = job_results.get(call["id"])
            if not isinstance(result, dict) or result.get("status") not in ("succeeded", "failed", "unknown"):
                return _decision("unknown", validator, "result_missing")
            if result["status"] != "succeeded":
                return _decision(result["status"], validator, "call_" + result["status"])
            if result.get("completeness") not in COMPLETENESS:
                return _decision("unknown", validator, "completeness_missing")
            complete = complete and result["completeness"] in ("complete", "empty")
            bounded = bounded and (result["completeness"] in ("complete", "empty") or (result["completeness"] == "partial" and result.get("scope") == "single_page"))
            evidence.extend(result.get("evidence", []))
        if not execution.get("calls"):
            return _decision("unknown", validator, "no_calls")
        return _decision("succeeded" if complete or (validator == "observed_v1" and bounded) else "unknown", validator,
                         "verified_complete" if complete else "observed_limited", evidence, scope_complete=complete)
    if validator == "grounded_summary_v1":
        return _evaluate_summary(execution, job_results.get("summary"), stored_results)
    return _decision("unknown", validator, "validator_unavailable")


def _evaluate_summary(execution, result, stored_results):
    validator = "grounded_summary_v1"
    if not isinstance(result, dict) or result.get("status") != "succeeded":
        return _decision("unknown", validator, "summary_missing")
    output = result.get("data")
    if not isinstance(output, dict) or set(output) != {"claims", "limitations"} or not isinstance(output["claims"], list) or not 1 <= len(output["claims"]) <= 40 or not isinstance(output["limitations"], list):
        return _decision("unknown", validator, "summary_schema")
    allowed = {(ref["job_id"], ref["call_id"]) for ref in execution.get("evidence", [])}
    observed, evidence, lines = set(), [], []
    try:
        for claim in output["claims"]:
            if not isinstance(claim, dict) or set(claim) != {"job_id", "call_id", "path", "value"} or (claim["job_id"], claim["call_id"]) not in allowed:
                raise ContractError("unsupported_claim", "")
            path = claim["path"]
            if not _path_ok(path) or len(path) < 2 or path[0] != "data":
                raise ContractError("unsupported_claim", "")
            source = _source(claim, stored_results)
            actual = _at(source, path)
            # Objects/lists may contain untrusted commands. Summary accepts only
            # bounded scalar observations, never their instructions or HTML.
            if type(actual) not in (str, int, bool, type(None)) or (isinstance(actual, str) and len(actual) > 2000):
                raise ContractError("unsupported_claim", "")
            if type(actual) is not type(claim["value"]) or actual != claim["value"]:
                raise ContractError("ungrounded_claim", "")
            observed.add((claim["job_id"], claim["call_id"]))
            evidence.extend(source.get("evidence", []))
            lines.append({"source": {"job_id": claim["job_id"], "call_id": claim["call_id"]}, "path": path, "value": actual})
        if observed != allowed:
            raise ContractError("missing_source", "")
        observed_paths = {(claim["job_id"], claim["call_id"], tuple(claim["path"])) for claim in output["claims"]}
        for required in execution.get("completion", {}).get("required_claims", []):
            if (required["job_id"], required["call_id"], tuple(required["path"])) not in observed_paths:
                raise ContractError("missing_required_claim", "")
        limitations = []
        for job_id, call_id in sorted(allowed):
            source = _source({"job_id": job_id, "call_id": call_id}, stored_results)
            completeness = source.get("completeness", "unknown")
            if completeness not in ("complete", "empty"):
                limitations.append({"job_id": job_id, "call_id": call_id, "completeness": completeness})
        if sorted(output["limitations"], key=lambda row: (row["job_id"], row["call_id"])) != limitations:
            raise ContractError("missing_limitation", "")
    except (ContractError, KeyError, TypeError, ValueError) as error:
        return _decision("unknown", validator, getattr(error, "code", "summary_schema"))
    return _decision("succeeded", validator, "grounded_observations", evidence,
                     {"claims": lines, "limitations": limitations, "notice": "저장 근거의 관찰값입니다. 문서 버전은 설치 버전이나 설치 완료를 뜻하지 않습니다."}, not limitations)


def evaluate_final(node, job_validations, required_jobs):
    final = node.get("execution_final", {})
    if final.get("validator") != "all_required_v1" or final.get("version") != 1:
        return _decision("unknown", "all_required_v1", "final_condition_missing")
    validations = [job_validations.get(key) for key in required_jobs]
    if not validations or any(not value or value.get("status") != "succeeded" for value in validations):
        return _decision("unknown", "all_required_v1", "required_jobs_incomplete")
    complete = all(value.get("scope_complete") is True for value in validations)
    return _decision("succeeded" if complete or not final.get("require_complete", True) else "unknown", "all_required_v1",
                     "required_jobs_verified" if complete else "source_scope_limited", scope_complete=complete)


def remap_execution(node, id_map):
    """Keep P-copy/save's temporary IDs consistent in data-only references."""
    execution = node.get("execution", {})
    for call in execution.get("calls", []):
        for binding in call.get("arguments", {}).values():
            for ref in (binding, binding.get("selection", {})):
                if "job_id" in ref:
                    ref["job_id"] = id_map.get(ref["job_id"], ref["job_id"])
    for ref in execution.get("evidence", []):
        ref["job_id"] = id_map.get(ref["job_id"], ref["job_id"])
    for ref in execution.get("completion", {}).get("required_claims", []):
        ref["job_id"] = id_map.get(ref["job_id"], ref["job_id"])
    choices = execution.get("completion", {}).get("choices", {})
    if "job_id" in choices:
        choices["job_id"] = id_map.get(choices["job_id"], choices["job_id"])
