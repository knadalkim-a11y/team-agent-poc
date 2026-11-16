"""Read an OpenAPI document as data; local JSON pointers never perform I/O."""
from collections import Counter
import hashlib
import json
import math
import re
from urllib.parse import unquote, urljoin, urlsplit

from .ees_workflow_authoring import WorkflowError


VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
TYPES = {"string", "number", "integer", "boolean", "object", "array"}
SENSITIVE = re.compile(r"(^|[-_])(authorization|cookie|token|pat|secret|password|credential|api[-_]?key)([-_]|$)", re.I)


def invalid(message, code="api_invalid"):
    raise WorkflowError(code, message)


def string(value, limit=1024, *, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        invalid("필수 항목과 문자열 길이를 확인하세요.")
    return value.strip()


def http_url(raw, *, relative=False, query=False):
    raw = string(raw, 4096, required=True)
    if re.search(r"[\x00-\x20\\]", raw):
        invalid("공백과 계정 정보가 없는 HTTP(S) 주소를 입력하세요.")
    try:
        url = urlsplit(raw)
        _ = url.port
    except ValueError:
        invalid("서비스 주소와 포트를 확인하세요.")
    if url.fragment or url.username is not None or url.password is not None or (url.query and not query):
        invalid("주소의 계정 정보와 고정 쿼리를 제거하고 파라미터를 명세에서 지정하세요.")
    if url.query and any(SENSITIVE.search(key) for key in re.split(r"[&=]", unquote(url.query))):
        invalid("인증값이 포함된 URL을 명세에 저장할 수 없습니다.")
    if url.scheme in ("http", "https") and url.hostname and not re.search("[{}]", url.netloc):
        return raw
    if relative and not url.scheme and not url.netloc and raw.startswith("/") and not raw.startswith("//"):
        return raw
    invalid("HTTP(S) 서비스 주소를 확인하세요.")


def validate_json(value, *, maximum=100000, scrub=False):
    """Bound depth/expanded nodes and reject cycles, aliases and non-JSON data."""
    count = 0
    seen = set()

    def check(item, depth):
        nonlocal count
        count += 1
        if count > maximum or depth > 48:
            invalid("자료가 너무 크거나 중첩 단계가 깊습니다.")
        if type(item) in (dict, list):
            if id(item) in seen:
                invalid("순환 참조 또는 중복 YAML 별칭은 하나의 JSON 구조로 풀어 주세요.")
            seen.add(id(item))
            if isinstance(item, list):
                for val in item:
                    check(val, depth + 1)
            else:
                for key, val in item.items():
                    if not isinstance(key, str):
                        invalid("문서 속성 이름은 문자열이어야 합니다.")
                    if scrub and SENSITIVE.search(key) and val not in (None, "", "[redacted]"):
                        invalid("비밀값을 제거한 예시만 저장하세요.")
                    check(val, depth + 1)
        elif type(item) is float and not math.isfinite(item):
            invalid("유한한 JSON 숫자로 입력하세요.")
        elif item is not None and type(item) not in (str, int, float, bool):
            invalid("JSON 호환 입력을 사용하세요.")

    check(value, 0)


def read_doc(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 2_000_000:
        invalid("2 MB 이내의 OpenAPI JSON 또는 YAML 문서가 필요합니다.")
    try:
        doc = json.loads(text)
    except (ValueError, RecursionError):
        import yaml
        try:
            doc = yaml.safe_load(text)
        except (ValueError, yaml.YAMLError, RecursionError):
            invalid("JSON 또는 YAML 문법을 확인하세요.")
    if not isinstance(doc, dict) or not re.fullmatch(r"3\.[01]\.\d+(?:[-+].*)?", str(doc.get("openapi", ""))):
        invalid("OpenAPI 3.0 또는 3.1 문서를 입력하세요.")
    # OpenAPI response status codes are frequently unquoted in YAML.
    def yaml_keys(x, visited):
        if type(x) not in (dict, list) or id(x) in visited:
            return
        visited.add(id(x))
        if len(visited) > 100000:
            invalid("명세가 너무 큽니다.")
        if isinstance(x, dict):
            for key in list(x):
                if type(key) is int and 100 <= key <= 599:
                    if str(key) in x:
                        invalid("응답 코드가 중복되었습니다.")
                    x[str(key)] = x.pop(key)
            children = x.values()
        else:
            children = x
        for val in children:
            yaml_keys(val, visited)
    try:
        yaml_keys(doc, set())
    except RecursionError:
        invalid("명세의 중첩 단계가 너무 깊습니다.")
    validate_json(doc)
    if not isinstance(doc.get("info"), dict) or not isinstance(doc.get("paths"), dict):
        invalid("명세의 info와 paths를 확인하세요.")
    string(doc["info"].get("title"), 180, required=True)
    string(doc["info"].get("version"), 160, required=True)
    return doc


def _expand(value, doc, budget, trail=(), depth=0):
    budget[0] -= 1
    if depth > 40 or budget[0] < 0:
        invalid("명세의 참조 단계가 너무 많습니다.")
    if isinstance(value, list):
        return [_expand(v, doc, budget, trail, depth + 1) for v in value]
    if not isinstance(value, dict):
        return value
    ref = value.get("$ref")
    result = {}
    if ref is not None:
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in trail:
            invalid("순환 참조와 외부 참조는 먼저 한 문서로 정리하세요.")
        node = doc
        for part in unquote(ref[2:]).split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, list) and part.isdecimal() and int(part) < len(node):
                node = node[int(part)]
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                invalid("찾을 수 없는 문서 내부 참조입니다.")
        result = _expand(node, doc, budget, trail + (ref,), depth + 1)
        if not isinstance(result, dict):
            invalid("참조가 객체를 가리켜야 합니다.")
    for key, child in value.items():
        if key != "$ref":
            result[key] = _expand(child, doc, budget, trail, depth + 1)
    return result


def _schema_type(schema):
    kind = schema.get("type", "object" if "properties" in schema else "array" if "items" in schema else "string")
    if isinstance(kind, list):
        options = [k for k in kind if k != "null"]
        kind = options[0] if len(options) == 1 else None
    if kind not in TYPES or any(option in schema for option in ("oneOf", "anyOf", "allOf")):
        invalid("지원하지 않는 복합 자료형이 있습니다. 해당 API는 입력 형식을 확인한 뒤 직접 등록하세요.")
    return kind


def _json_media(content):
    if not isinstance(content, dict):
        invalid("요청·응답 content를 확인하세요.")
    for key in content:
        media = key.split(";")[0].lower().strip()
        if media == "application/json" or media.endswith("+json"):
            return content[key]
    return None


def _fields(schema, prefix=""):
    fields = []
    for key, prop in schema.get("properties", {}).items():
        if not isinstance(prop, dict):
            invalid("응답 필드 정의를 확인하세요.")
        path = prefix + key
        kind = _schema_type(prop)
        if kind == "object" and prop.get("properties"):
            fields.extend(_fields(prop, path + "."))
        else:
            fields.append({"path": path, "label": prop.get("title") or key, "type": kind})
    return fields


def _compile(doc, endpoint, method, item, op, source_url, budget):
    op = _expand(op, doc, budget)
    if not isinstance(op, dict) or not endpoint.startswith("/") or endpoint.startswith("//") or re.search(r"[?#]", endpoint):
        invalid("호출 경로를 확인하세요.")
    servers = op.get("servers") or item.get("servers") or doc.get("servers") or []
    server = servers[0] if servers else {"url": "/"}
    base = string(server["url"], 4096)
    for param in re.findall(r"\{([^{}]+)\}", base):
        base = base.replace("{" + param + "}", string(server["variables"][param]["default"], required=True))
    if base.startswith("//"):
        invalid("서버 주소에 프로토콜을 명시하세요.")
    if source_url:
        base = urljoin(source_url, base)
    url = http_url(base.rstrip("/") + endpoint, relative=True)
    params = {}
    for pool in [item.get("parameters", []), op.get("parameters", [])]:
        local = set()
        for p in pool:
            p = _expand(p, doc, budget)
            key = (p["in"], p["name"])
            if key in local:
                invalid("중복된 요청 파라미터가 있습니다.")
            local.add(key)
            params[key] = p
    inputs = []
    for (where, wire), p in params.items():
        if where not in ("path", "query", "header"):
            invalid("이 입력 위치는 직접 등록에서 확인하세요.")
        if where == "header" and SENSITIVE.search(wire):
            # Provider credentials are resolved by the trusted transport.
            continue
        if p.get("style", {"query":"form","path":"simple","header":"simple"}[where]) != {"query":"form","path":"simple","header":"simple"}[where] or p.get("allowReserved") or "content" in p:
            invalid("지원하지 않는 파라미터 직렬화 방식입니다.")
        if where == "path" and (not p.get("required") or "{" + wire + "}" not in endpoint):
            invalid("필수 경로 변수 정의를 확인하세요.")
        schema = p.get("schema", {})
        inputs.append({"name":wire, "wire_name":wire, "in":where, "type":_schema_type(schema), "label":schema.get("title") or p.get("description") or wire, "required":bool(p.get("required"))})
    if re.findall(r"\{([^{}]+)\}", endpoint) and set(re.findall(r"\{([^{}]+)\}", endpoint)) != {i["wire_name"] for i in inputs if i["in"] == "path"}:
        invalid("경로 변수의 파라미터 정의가 없습니다.")
    body = op.get("requestBody")
    if body:
        content = _json_media(body["content"])
        if not content:
            invalid("JSON 이외의 요청 본문 형식은 직접 등록에서 확인하세요.")
        schema = content.get("schema", {})
        if _schema_type(schema) == "object" and schema.get("properties"):
            for key, prop in schema["properties"].items():
                inputs.append({"name":key, "wire_name":key, "in":"body", "type":_schema_type(prop),
                               "label":prop.get("title") or key, "required":bool(body.get("required") and key in schema.get("required", []))})
        else:
            inputs.append({"name":"body", "wire_name":"body", "in":"body", "type":_schema_type(schema) if schema else "object",
                           "whole_body":True, "label":schema.get("title") or body.get("description") or "요청 본문",
                           "required":bool(body.get("required"))})
    frequency = Counter(i["name"] for i in inputs)
    for inp in inputs:
        if frequency[inp["name"]] > 1:
            inp["name"] = inp["in"] + "_" + inp["name"]
    responses = op.get("responses")
    if not isinstance(responses, dict) or not responses:
        invalid("응답 명세가 없습니다.")
    selected = None
    for code in sorted(responses):
        if re.fullmatch(r"2(?:[0-9][0-9]|XX)", code) and isinstance(responses[code], dict):
            selected = _json_media(responses[code].get("content", {}))
            if selected is not None:
                break
    schema = (selected or {}).get("schema", {})
    example = (selected or {}).get("example", schema.get("example"))
    if example is None:
        for ex in (selected or {}).get("examples", {}).values():
            if isinstance(ex, dict) and "value" in ex:
                example = ex["value"]
                break
    if example is None and schema.get("examples"):
        example = schema["examples"][0]
    validate_json(example, maximum=6000, scrub=True)
    root = ""
    if schema.get("type") == "array":
        schema = schema.get("items", {})
    elif isinstance(schema.get("properties"), dict):
        arrays = [(key,s) for key,s in schema["properties"].items() if s.get("type") == "array" and s.get("items",{}).get("properties")]
        if len(arrays) == 1:
            root, array = arrays[0]
            schema = array["items"]
    output_fields = _fields(schema)
    if schema and not output_fields and _schema_type(schema) != "object":
        output_fields = [{"path":"$", "type":_schema_type(schema), "root_value":True, "label":schema.get("title") or "결과"}]
    return {"name":op.get("summary") or op.get("operationId") or method+" "+endpoint,
            "purpose":op.get("description") or op.get("summary") or method+" "+endpoint,
            "method":method,"url":url,"inputs":inputs,"result_path":root,"fields":output_fields,
            "example":example,"state":"deprecated" if op.get("deprecated") else "active",
            "operation_key":op.get("operationId") or "", "source_path":endpoint}


def parse_document(text, source_url=""):
    doc = read_doc(text)
    operations = []
    ids = {}
    budget = [140000]
    for endpoint, item in doc["paths"].items():
        if endpoint.startswith("x-"):
            continue
        if not isinstance(item, dict):
            invalid("paths의 경로 항목을 확인하세요.")
        if "$ref" in item:
            item = _expand(item, doc, budget)
        for method, op in item.items():
            method = method.upper()
            if method not in VERBS | {"TRACE"}:
                continue
            key = method + " " + endpoint
            try:
                if method not in VERBS:
                    invalid("지원하지 않는 요청 방식입니다.")
                result = _compile(doc, endpoint, method, item, op, source_url, budget)
                if result["operation_key"]:
                    op_id = result["operation_key"]
                    if not isinstance(op_id, str):
                        invalid("operationId를 확인하세요.")
                    if op_id in ids:
                        ids[op_id]["error"] = "중복된 operationId입니다."
                        invalid("중복된 operationId입니다.")
                    ids[op_id] = result
            except WorkflowError as exc:
                result = {"error":str(exc), "method":method,"source_path":endpoint,"name":key}
            except (AttributeError, TypeError, ValueError, KeyError, IndexError, RecursionError):
                result = {"error":"이 기능의 파라미터·서버·응답 정의를 확인하세요.", "method":method,"source_path":endpoint,"name":key}
            result["key"] = key
            operations.append(result)
            if len(operations) > 1000:
                invalid("한 번에 1000개 이하의 API를 확인할 수 있습니다.")
    return {"service_name":doc["info"]["title"],"service_version":doc["info"]["version"],
            "document_hash":hashlib.sha256(text.encode("utf-8")).hexdigest(),"operations":operations}
