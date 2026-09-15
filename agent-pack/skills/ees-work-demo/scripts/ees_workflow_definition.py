"""Workflow definition loading and validation, independent of saved user state."""

import json
from pathlib import Path
import re


CATEGORIES = ("setup", "ops", "incident")
SYSTEMS = ("EMS", "APC", "FDC", "EGIS", "EPT")
INPUTS = ("db", "ap", "site", "interface")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
MAX_DOCUMENT_BYTES = 750_000


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _policy():
    return json.loads(Path(__file__).with_name("workflow_policy.json").read_text(encoding="utf-8"))


def _seed():
    definition = json.loads(Path(__file__).with_name("workflow_seed.json").read_text(encoding="utf-8"))
    definition["skills"] = {"common": _policy(), **definition["skills"]}
    return definition


def _ancestors(nodes, node_id):
    result, seen = [], set()
    while node_id and node_id not in seen and node_id in nodes:
        seen.add(node_id)
        result.append(nodes[node_id])
        node_id = nodes[node_id].get("parent")
    return list(reversed(result))


def _leaves(nodes, node_id):
    node = nodes[node_id]
    return [node_id] if node["type"] == "j" else [
        leaf for child in node["children"] for leaf in _leaves(nodes, child)
    ]


def _dependencies(nodes, node_id):
    return list(dict.fromkeys(dep for node in _ancestors(nodes, node_id) for dep in node["deps"]))


def _draft_shape_errors(definition):
    """Accept unfinished references, but never persist an unreadable editor."""
    if not isinstance(definition, dict):
        return ["업무 절차는 객체여야 합니다."]
    errors = []
    for key, maximum in (("nodes", 250), ("tools", 200), ("skills", 200), ("sites", 100)):
        entries = definition.get(key)
        if not isinstance(entries, dict) or not entries or len(entries) > maximum:
            errors.append(f"{key}: 기본 목록 형식과 항목 수를 확인해 주세요.")
            continue
        for item_id, item in entries.items():
            if (not isinstance(item_id, str) or not IDENTIFIER.fullmatch(item_id) or not isinstance(item, dict)
                    or item.get("id") != item_id or not isinstance(item.get("name"), str)
                    or not item["name"].strip() or len(item["name"]) > 160):
                errors.append(f"{key}: 각 항목의 ID와 이름이 필요합니다.")
                continue
            valid = True
            if key == "nodes":
                valid = (item.get("type") in ("p", "t", "j") and item.get("category") in CATEGORIES
                         and item.get("mode") in ("manual", "tool", "draft")
                         and "parent" in item and isinstance(item["parent"], (str, type(None))) and isinstance(item.get("bindings"), dict)
                         and all(isinstance(item.get(field), list) and all(isinstance(value, str) for value in item[field])
                                 for field in ("children", "tools", "skills", "deps"))
                         and all(isinstance(item.get(field, ""), str) for field in ("description", "instructions", "rule", "condition")))
            elif key == "tools":
                valid = item.get("input") in INPUTS and item.get("adapter", "unavailable") in ("mock", "unavailable")
            elif key == "skills":
                valid = item.get("type") in ("skill", "instruction") and isinstance(item.get("body", ""), str)
            elif key == "sites":
                valid = (all(isinstance(item.get(field), str) for field in ("country", "line", "zone", "db", "ap"))
                         and all(isinstance(item.get(field), bool) for field in ("reuse", "interface")))
            if key in ("tools", "skills") and item.get("source") == "open_webui":
                valid = valid and isinstance(item.get("reference"), str) and bool(item["reference"]) and len(item["reference"]) <= 200
            if key in ("tools", "skills") and item.get("source") not in (None, "example", "open_webui"):
                valid = False
            if not valid:
                errors.append(f"{item_id}: 편집 항목의 기본 형식을 확인해 주세요.")
    roots = definition.get("roots")
    if (not isinstance(roots, dict) or set(roots) != set(CATEGORIES)
            or any(not isinstance(ids, list) or any(not isinstance(item, str) for item in ids) for ids in roots.values())):
        errors.append("셋업·운영·장애대응의 최상위 목록을 확인해 주세요.")
    if definition.get("systems") != list(SYSTEMS):
        errors.append("지원 시스템 목록을 확인해 주세요.")
    if isinstance(definition.get("skills"), dict) and definition["skills"].get("common") != _policy():
        errors.append("공통 실행 지침은 변경하거나 해제할 수 없습니다.")
    return errors


def validate_definition(definition):
    """Validate editable P/T/J structure, inherited prerequisites and mappings."""
    errors = []

    def reject(message):
        errors.append(message)

    if not isinstance(definition, dict):
        return ["업무 절차는 객체여야 합니다."]
    try:
        if len(_dump(definition).encode("utf-8")) > MAX_DOCUMENT_BYTES:
            return ["업무 절차가 허용 크기를 초과했습니다."]
    except (TypeError, ValueError):
        return ["업무 절차를 JSON으로 저장할 수 없습니다."]
    shape_errors = _draft_shape_errors(definition)
    if shape_errors:
        return shape_errors
    limits = {"nodes": 250, "tools": 200, "skills": 200, "sites": 100}
    for field, maximum in limits.items():
        value = definition.get(field)
        if not isinstance(value, dict) or not value or len(value) > maximum:
            reject(f"{field}: 항목 수와 형식을 확인해 주세요.")
        elif any(not isinstance(key, str) or not IDENTIFIER.fullmatch(key)
                 or not isinstance(item, dict) or item.get("id") != key
                 or not isinstance(item.get("name"), str) or not item["name"].strip()
                 or len(item["name"]) > 160 for key, item in value.items()):
            reject(f"{field}: 항목의 ID와 이름을 확인해 주세요.")
    if errors:
        return errors
    nodes, tools, skills, sites = (definition[name] for name in limits)
    roots = definition.get("roots")
    if not isinstance(roots, dict) or set(roots) != set(CATEGORIES):
        return ["셋업·운영·장애대응의 최상위 목록을 확인해 주세요."]
    if definition.get("systems") != list(SYSTEMS):
        reject("지원 시스템 목록을 확인해 주세요.")
    if skills.get("common") != _policy():
        reject("공통 실행 지침은 변경하거나 해제할 수 없습니다.")
    for category, ids in roots.items():
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            reject(f"{category}: 최상위 목록에 중복 또는 잘못된 ID가 있습니다.")
            continue
        for node_id in ids:
            node = nodes.get(node_id, {})
            if node.get("type") != "p" or node.get("parent") is not None or node.get("category") != category:
                reject(f"{node_id}: 최상위 프로세스 연결을 확인해 주세요.")
    if errors:
        return list(dict.fromkeys(errors))
    for tool in tools.values():
        if tool.get("input") not in INPUTS or not isinstance(tool.get("enabled", True), bool):
            reject(f"{tool['id']}: 입력 종류와 사용 여부를 확인해 주세요.")
        if tool.get("adapter", "unavailable") not in ("mock", "unavailable"):
            reject(f"{tool['id']}: 지원하지 않는 실행 연결입니다.")
        if tool.get("mockResult", "success") not in ("success", "failure"):
            reject(f"{tool['id']}: 예시 응답을 확인해 주세요.")
        if tool.get("source") == "open_webui" and (not tool.get("reference") or tool.get("adapter") == "mock"):
            reject(f"{tool['id']}: 기존 도구를 예시 실행으로 바꿀 수 없습니다.")
    for skill in skills.values():
        if skill.get("type") not in ("skill", "instruction") or not isinstance(skill.get("body", ""), str):
            reject(f"{skill['id']}: 스킬·지침 내용을 확인해 주세요.")
    for site in sites.values():
        if (any(not isinstance(site.get(key), str) or not site[key].strip()
                for key in ("country", "line", "zone", "db", "ap"))
                or any(not isinstance(site.get(key), bool) for key in ("reuse", "interface"))):
            reject(f"{site['id']}: 현장 조건을 확인해 주세요.")
    for node_id, node in nodes.items():
        if node.get("type") not in ("p", "t", "j") or node.get("category") not in CATEGORIES:
            reject(f"{node_id}: 단계와 업무 분류를 확인해 주세요.")
            continue
        invalid_lists = [key for key in ("children", "tools", "skills", "deps")
                         if not isinstance(node.get(key), list)
                         or any(not isinstance(item, str) for item in node[key])
                         or len(set(node[key])) != len(node[key])]
        if invalid_lists:
            reject(f"{node_id}: 중복 또는 잘못된 목록이 있습니다.")
            continue
        if (not isinstance(node.get("parent"), (str, type(None)))
                or not isinstance(node.get("bindings"), dict)
                or any(not isinstance(node.get(key, ""), str) for key in ("description", "instructions", "rule"))):
            reject(f"{node_id}: 작업 내용과 입력 연결 형식을 확인해 주세요.")
            continue
        if node.get("mode") not in ("manual", "tool", "draft"):
            reject(f"{node_id}: 수행 방식을 확인해 주세요.")
        if not isinstance(node.get("enabled", True), bool) or not isinstance(node.get("failOnce", False), bool):
            reject(f"{node_id}: 사용 여부를 확인해 주세요.")
        if "systems" in node and (not isinstance(node["systems"], list) or not node["systems"]
                                  or any(system not in SYSTEMS for system in node["systems"])):
            reject(f"{node_id}: 적용 시스템을 확인해 주세요.")
        condition = node.get("condition", "all")
        conditions = {"all", "interface", "reuse", "new-infra"}
        conditions.update("country:" + site["country"] for site in sites.values() if isinstance(site.get("country"), str))
        conditions.update("factory:" + site_id for site_id in sites)
        conditions.update("line:" + site["line"] for site in sites.values() if isinstance(site.get("line"), str))
        if not isinstance(condition, str) or condition not in conditions:
            reject(f"{node_id}: 적용 조건을 확인해 주세요.")
        parent = nodes.get(node["parent"])
        expected_parent = {"p": None, "t": "p", "j": "t"}[node["type"]]
        if node["type"] == "p":
            if node["parent"] is not None or node_id not in roots.get(node["category"], []):
                reject(f"{node_id}: 최상위 목록에 등록해 주세요.")
        elif (not parent or parent.get("type") != expected_parent or parent.get("category") != node["category"]
              or not isinstance(parent.get("children"), list)
              or node_id not in parent.get("children", [])):
            reject(f"{node_id}: 상위 단계 연결을 확인해 주세요.")
        if node["type"] == "j" and node["children"]:
            reject(f"{node_id}: 잡에는 하위 단계를 추가할 수 없습니다.")
        if node["type"] != "j" and not node["children"]:
            reject(f"{node_id}: 하나 이상의 하위 작업이 필요합니다.")
        for child in node["children"]:
            if child not in nodes or nodes[child].get("parent") != node_id:
                reject(f"{node_id}: 하위 작업 연결이 일치하지 않습니다.")
        for field, available in (("tools", tools), ("skills", skills), ("deps", nodes)):
            if any(item not in available for item in node[field]):
                reject(f"{node_id}: 삭제되거나 없는 {field} 참조가 있습니다.")
        if node["type"] == "j" and node["mode"] == "tool" and not node["tools"]:
            reject(f"{node_id}: 실행할 도구를 연결해 주세요.")
        for tool_id in node["tools"]:
            if tool_id in tools and node["bindings"].get(tool_id, tools[tool_id].get("input")) != tools[tool_id].get("input"):
                reject(f"{node_id}: 도구가 요구하는 입력 종류와 연결이 다릅니다.")
    if errors:
        return list(dict.fromkeys(errors))
    # The P/T/J parent types prevent structural cycles; expanding inherited
    # prerequisites catches deadlocks such as a task depending on its own child.
    graph = {}
    for node_id, node in nodes.items():
        ancestors = _ancestors(nodes, node_id)
        for ancestor in ancestors[:-1]:
            if ancestor["tools"] and any(tool not in ancestor["tools"] for tool in node["tools"]):
                reject(f"{node_id}: 상위 단계가 허용한 도구 범위를 벗어났습니다.")
        deps = _dependencies(nodes, node_id)
        for dep in deps:
            if _ancestors(nodes, dep)[0]["id"] != ancestors[0]["id"]:
                reject(f"{node_id}: 다른 프로세스의 진행 결과를 선행 조건으로 사용할 수 없습니다.")
        if node["type"] == "j":
            graph[node_id] = {leaf for dep in deps for leaf in _leaves(nodes, dep)}
    visited, active = set(), set()

    def visit(node_id):
        if node_id in active:
            return False
        if node_id in visited:
            return True
        active.add(node_id)
        if any(not visit(dep) for dep in graph[node_id]):
            return False
        active.remove(node_id)
        visited.add(node_id)
        return True

    if any(not visit(node_id) for node_id in graph):
        reject("선행 작업이 순환합니다. 서로를 기다리는 의존 관계를 수정해 주세요.")
    return list(dict.fromkeys(errors))
