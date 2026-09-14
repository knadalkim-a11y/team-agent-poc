"""Persistent workflow state shared by the native work panel and the AI Tool.

This module runs inside the existing Open WebUI process. It never executes
arbitrary code, SQL, a business API, or a model. Example checks are explicitly
labelled simulations; an external tool reference without an adapter is blocked.
The separate SQLite file only holds workflow definitions and user-owned cases.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


CATEGORIES = ("setup", "ops", "incident")
SYSTEMS = ("EMS", "APC", "FDC", "EGIS", "EPT")
INPUTS = ("db", "ap", "site", "interface")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
MAX_DOCUMENT_BYTES = 750_000
_service = None


class WorkflowError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _seed():
    return json.loads(Path(__file__).with_name("workflow_seed.json").read_text(encoding="utf-8"))


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


def _applicable(case, node_id):
    site = case["site"]
    for node in _ancestors(case["definition"]["nodes"], node_id):
        condition = node.get("condition", "all")
        if not node.get("enabled", True) or case["system"] not in node.get("systems", SYSTEMS):
            return False
        if condition == "interface" and not site["interface"]:
            return False
        if condition == "reuse" and not site["reuse"]:
            return False
        if condition == "new-infra" and site["reuse"]:
            return False
        for prefix, key in (("country:", "country"), ("factory:", "id"), ("line:", "line")):
            if condition.startswith(prefix) and condition[len(prefix):] != site[key]:
                return False
    return True


def _finished(case, node_id):
    return all(not _applicable(case, leaf) or case["jobs"][leaf]["status"] == "passed"
               for leaf in _leaves(case["definition"]["nodes"], node_id))


def _missing(case, node_id):
    return [dep for dep in _dependencies(case["definition"]["nodes"], node_id)
            if not _finished(case, dep)]


def _view(case):
    """Derive displayed parent state without persisting a second truth."""
    if case is None:
        return None
    case = deepcopy(case)
    case.pop("_skill_snapshots", None)
    nodes = case["definition"]["nodes"]
    node_states = {}
    for node_id in nodes:
        relevant = [leaf for leaf in _leaves(nodes, node_id) if _applicable(case, leaf)]
        statuses = [case["jobs"][leaf]["status"] for leaf in relevant]
        done = sum(status == "passed" for status in statuses)
        missing = _missing(case, node_id)
        if not relevant:
            status = "skipped"
        elif done == len(relevant):
            status = "passed"
        elif "failed" in statuses:
            status = "failed"
        elif "review" in statuses:
            status = "review"
        elif "blocked" in statuses or all(_missing(case, leaf) for leaf in relevant):
            status = "blocked"
        else:
            status = "pending"
        node_states[node_id] = {"status": status, "applicable": _applicable(case, node_id),
                                "missing": missing, "progress": {"done": done, "total": len(relevant)}}
    case["node_states"] = node_states
    case["status"] = node_states[case["process_id"]]["status"]
    case["progress"] = node_states[case["process_id"]]["progress"]
    selected = _ancestors(nodes, case["selected_id"])
    skill_ids = list(dict.fromkeys(["common", *(skill for node in selected for skill in node["skills"])]))
    case["context"] = {
        "breadcrumb": [{"id": node["id"], "name": node["name"], "type": node["type"]} for node in selected],
        "skills": [deepcopy(case["definition"]["skills"][key]) for key in skill_ids],
        "instructions": [node.get("instructions", "") for node in selected if node.get("instructions")],
        "simulation": True,
    }
    return case


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
    if isinstance(definition.get("skills"), dict) and definition["skills"].get("common") != _seed()["skills"]["common"]:
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
    if skills.get("common") != _seed()["skills"]["common"]:
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


class WorkflowService:
    """The injected lookups use the same current user and chat store as WebUI."""

    def __init__(self, database, user_lookup, chat_lookup, asset_lookup=None):
        self.database = Path(database)
        self.user_lookup, self.chat_lookup = user_lookup, chat_lookup
        self.asset_lookup = asset_lookup
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS catalog (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "published TEXT NOT NULL, draft TEXT NOT NULL, revision INTEGER NOT NULL, validated INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                       "chat_id TEXT, data TEXT NOT NULL)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS case_chat ON cases(owner,chat_id) WHERE chat_id IS NOT NULL")
            seed = _dump(_seed())
            db.execute("INSERT OR IGNORE INTO catalog VALUES(1,?,?,0,NULL)", (seed, seed))

    @contextmanager
    def _db(self, write=False):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _user(self, user):
        user_id = _value(user, "id")
        if not isinstance(user_id, str) or not user_id or len(user_id) > 200:
            raise WorkflowError("unauthorized", "로그인한 사용자 정보를 확인해 주세요.")
        current = await _resolve(self.user_lookup(user_id))
        if not current or _value(current, "id") != user_id or _value(current, "role") not in ("user", "admin"):
            raise WorkflowError("unauthorized", "현재 계정으로 업무를 사용할 수 없습니다.")
        return current

    async def _chat(self, user, chat_id):
        if not isinstance(chat_id, str) or len(chat_id) > 200:
            raise WorkflowError("invalid_chat", "대화 정보를 확인해 주세요.")
        if chat_id:
            chat = await _resolve(self.chat_lookup(chat_id))
            if not chat or _value(chat, "user_id") != _value(user, "id"):
                raise WorkflowError("chat_forbidden", "본인의 저장된 대화에만 업무를 연결할 수 있습니다.")

    async def _assets(self, user):
        if self.asset_lookup is None:
            return {"tools": [], "skills": [], "available": True}
        try:
            return await _resolve(self.asset_lookup(user))
        except Exception:
            # Availability failure must not bypass access filtering or expose
            # raw registry errors to the browser/model.
            return {"tools": [], "skills": [], "available": False}

    def _catalog(self, db):
        row = db.execute("SELECT * FROM catalog WHERE id=1").fetchone()
        return json.loads(row["published"]), json.loads(row["draft"]), row["revision"], row["validated"]

    def _case(self, db, user_id, case_id="", chat_id=""):
        row = None
        if case_id:
            row = db.execute("SELECT * FROM cases WHERE id=? AND owner=?", (case_id, user_id)).fetchone()
            if not row:
                raise WorkflowError("case_not_found", "접근할 수 있는 진행 건을 찾지 못했습니다.")
            if chat_id and row["chat_id"] and row["chat_id"] != chat_id:
                raise WorkflowError("chat_mismatch", "이 진행 건에 연결된 대화에서 계속해 주세요.")
        elif chat_id:
            row = db.execute("SELECT * FROM cases WHERE chat_id=? AND owner=?", (chat_id, user_id)).fetchone()
        return json.loads(row["data"]) if row else None

    def _state(self, db, user, case_id="", chat_id="", assets=None):
        published, draft, revision, validated = self._catalog(db)
        case = self._case(db, _value(user, "id"), case_id, chat_id)
        cases = []
        for row in db.execute("SELECT data FROM cases WHERE owner=? ORDER BY rowid DESC", (_value(user, "id"),)):
            item = _view(json.loads(row["data"]))
            cases.append({key: item[key] for key in ("id", "chat_id", "site", "system", "process_id",
                                                    "selected_id", "revision", "version", "status", "progress")})
        assets = assets or {"tools": [], "skills": [], "available": True}
        for definition in (published, draft):
            definition["available_tools"] = assets["tools"]
            definition["available_skills"] = assets["skills"]
            definition["assets_available"] = assets.get("available", True)
        case_view = _view(case)
        if case_view:
            bodies = assets.get("skill_bodies", {})
            snapshots = case.get("_skill_snapshots", {})
            for skill in case_view["context"]["skills"]:
                if skill.get("source") == "open_webui":
                    reference = skill.get("reference")
                    available = reference in bodies and reference in snapshots
                    skill["body"] = snapshots[reference]["body"] if available else ""
                    skill["available"] = available
                    if available:
                        skill["snapshot_updated_at"] = snapshots[reference].get("updated_at")
                    else:
                        skill["message"] = "진행 건에 고정된 스킬을 현재 계정으로 사용할 수 없습니다. 권한·사용 여부를 확인해 주세요."
        return {"ok": True, "catalog": published, "cases": cases, "case": case_view,
                "can_manage": _value(user, "role") == "admin",
                "draft": draft if _value(user, "role") == "admin" else None,
                "draft_revision": revision if _value(user, "role") == "admin" else None,
                "validated_revision": validated if _value(user, "role") == "admin" else None}

    async def get_state(self, user, chat_id="", case_id=""):
        try:
            current = await self._user(user)
            if not isinstance(case_id, str) or len(case_id) > 200:
                raise WorkflowError("invalid_request", "진행 건 식별 정보를 확인해 주세요.")
            await self._chat(current, chat_id)
            assets = await self._assets(current)
            with self._db() as db:
                state = self._state(db, current, case_id, chat_id, assets)
            if state["case"]:
                await self._chat(current, state["case"]["chat_id"])
            return state
        except WorkflowError as error:
            return {"ok": False, "error": {"code": error.code, "message": error.message}}
        except sqlite3.Error:
            return {"ok": False, "error": {"code": "state_unavailable", "message": "업무 상태를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}}

    @staticmethod
    def _revision(body, expected):
        if type(body.get("expected_revision")) is not int or body["expected_revision"] != expected:
            raise WorkflowError("revision_conflict", "다른 화면에서 변경되었습니다. 최신 상태를 불러온 뒤 다시 시도해 주세요.")

    @staticmethod
    def _save_case(db, user, case, new=False):
        case["updated_at"] = _now()
        if new:
            db.execute("INSERT INTO cases VALUES(?,?,?,?)", (case["id"], _value(user, "id"), case["chat_id"] or None, _dump(case)))
        else:
            case["revision"] += 1
            db.execute("UPDATE cases SET chat_id=?,data=? WHERE id=? AND owner=?",
                       (case["chat_id"] or None, _dump(case), case["id"], _value(user, "id")))

    @staticmethod
    def _new_case(published, payload, chat_id, assets):
        site_id, system, process_id = payload.get("site_id", "us-a"), payload.get("system", "EMS"), payload.get("process_id", "setup-p")
        if not all(isinstance(value, str) for value in (site_id, system, process_id)):
            raise WorkflowError("invalid_case", "대상 현장·시스템·프로세스 식별값을 확인해 주세요.")
        process = published["nodes"].get(process_id)
        if site_id not in published["sites"] or system not in SYSTEMS or not process or process["type"] != "p":
            raise WorkflowError("invalid_case", "대상 현장·시스템·프로세스를 확인해 주세요.")
        case = {"id": str(uuid4()), "chat_id": chat_id, "site": deepcopy(published["sites"][site_id]),
                "system": system, "process_id": process_id, "selected_id": process_id,
                "version": published["version"], "revision": 0, "definition": deepcopy(published), "jobs": {}}
        if not _applicable(case, process_id):
            raise WorkflowError("not_applicable", "이 현장·시스템에는 해당 프로세스가 적용되지 않습니다.")
        # A case contains only its process. Other processes cannot affect its
        # progress or be accidentally executed through a forged node ID.
        included = {node_id for node_id in published["nodes"] if _ancestors(published["nodes"], node_id)[0]["id"] == process_id}
        case["definition"]["nodes"] = {key: value for key, value in case["definition"]["nodes"].items() if key in included}
        case["definition"]["roots"] = {category: [process_id] if category == process["category"] else [] for category in CATEGORIES}
        references = {published["skills"][skill_id]["reference"]
                      for node_id in included for skill_id in published["nodes"][node_id]["skills"]
                      if published["skills"][skill_id].get("source") == "open_webui"}
        bodies = assets.get("skill_bodies", {})
        versions = assets.get("skill_versions", {})
        case["_skill_snapshots"] = {reference: {"body": bodies[reference], "updated_at": versions.get(reference)}
                                    for reference in references if reference in bodies}
        for node_id in _leaves(case["definition"]["nodes"], process_id):
            case["jobs"][node_id] = {"status": "pending", "checks": [], "attempt": 0,
                                     "inputs": {}, "history": [], "document": ""}
        return case

    @staticmethod
    def _node(case, node_id):
        node_id = node_id or case["selected_id"]
        node = case["definition"]["nodes"].get(node_id)
        if not node:
            raise WorkflowError("node_not_found", "현재 진행 건의 작업을 선택해 주세요.")
        return node

    @staticmethod
    def _invalidate(case, node_id):
        """Keep old evidence but invalidate results depending on changed input."""
        nodes = case["definition"]["nodes"]
        invalidated = {node_id}
        while True:
            additional = {job for job in case["jobs"] if any(
                invalidated.intersection(_leaves(nodes, dep)) for dep in _dependencies(nodes, job))}
            if additional <= invalidated:
                break
            invalidated.update(additional)
        for job_id in invalidated:
            job = case["jobs"][job_id]
            job["status"], job["checks"], job["document"] = "pending", [], ""
            job.pop("blocked_reason", None)

    @staticmethod
    def _inputs(case, job):
        site = case["site"]
        values = {"db": site["db"], "ap": site["ap"], "site": f"{site['country']} · {site['name']} · {site['line']}",
                  "interface": f"{case['system']} · {site['name']} 시스템 간 연계 · 예시" if site["interface"] else ""}
        values.update(job["inputs"])
        return values

    def _run_job(self, case, node, payload, assets):
        node_id = node["id"]
        job = case["jobs"][node_id]
        if not _applicable(case, node_id):
            raise WorkflowError("not_applicable", "현장 조건에 따라 제외된 작업입니다.")
        if _missing(case, node_id):
            raise WorkflowError("prerequisite_required", "선행 작업을 완료한 뒤 진행해 주세요.")
        for ancestor in _ancestors(case["definition"]["nodes"], node_id):
            for skill_id in ancestor["skills"]:
                skill = case["definition"]["skills"][skill_id]
                if skill.get("source") == "open_webui" and (
                        skill["reference"] not in assets.get("skill_bodies", {})
                        or skill["reference"] not in case.get("_skill_snapshots", {})):
                    raise WorkflowError("skill_unavailable", "필수 스킬을 현재 계정으로 사용할 수 없습니다. 권한·사용 여부를 확인해 주세요.")
        if node["mode"] in ("manual", "draft"):
            if node["mode"] == "draft" and "document" in payload:
                document = payload["document"]
                if not isinstance(document, str) or not document.strip() or len(document) > 16_000:
                    raise WorkflowError("invalid_document", "검토할 초안 내용을 입력해 주세요.")
                self._invalidate(case, node_id)
                job["document"], job["status"] = document, "review"
                return {"node_id": node_id, "status": "review", "message": "작성한 초안을 저장했습니다. 담당자 검토가 필요합니다."}
            if payload.get("confirm") is not True:
                raise WorkflowError("confirmation_required", "담당자가 확인한 뒤 완료를 기록해 주세요.")
            if node["mode"] == "draft" and not job["document"]:
                raise WorkflowError("draft_required", "검토할 초안을 먼저 작성해 주세요.")
            document = job["document"]
            self._invalidate(case, node_id)
            job["document"] = document
            job["attempt"] += 1
            job["status"] = "passed"
            record = {"attempt": job["attempt"], "status": "passed", "checks": [], "at": _now(),
                      "kind": "human_confirmation", "document": document, "inputs": self._inputs(case, job),
                      "detail": "담당자 완료 확인을 기록했습니다. 자동 점검 결과가 아닙니다."}
            job["history"].append(record)
            return {"node_id": node_id, "status": "passed", "message": record["detail"]}
        tools = case["definition"]["tools"]
        values = self._inputs(case, job)
        for tool_id in node["tools"]:
            tool = tools[tool_id]
            if not str(values.get(node["bindings"].get(tool_id, tool["input"]), "")).strip():
                raise WorkflowError("input_required", "실행에 필요한 입력값을 먼저 채워 주세요.")
        self._invalidate(case, node_id)
        job["attempt"] += 1
        stopped, blocked = False, False
        for tool_id in node["tools"]:
            tool = tools[tool_id]
            if stopped:
                status, detail = "skipped", "앞선 필수 점검을 완료하지 못해 미수행입니다."
            elif tool.get("adapter") != "mock" or tool.get("source") == "open_webui" or not tool.get("enabled", True):
                status, detail, stopped, blocked = "blocked", "실제 실행 연결이 없어 수행하지 않았습니다.", True, True
            elif tool.get("mockResult") == "failure" or (node.get("failOnce") and job["attempt"] == 1 and tool_id == "health"):
                status, detail, stopped = "failed", "예시 응답: 제한 시간 내 정상 응답이 없습니다.", True
            else:
                status, detail = "passed", "예시 응답: 정상입니다. 실제 업무 시스템은 조회하지 않았습니다."
            job["checks"].append({"id": tool_id, "name": tool["name"], "status": status, "detail": detail,
                                   "simulation": tool.get("adapter") == "mock" and tool.get("source") != "open_webui",
                                   "input": values[node["bindings"].get(tool_id, tool["input"])], "at": _now()})
        job["status"] = "blocked" if blocked else "failed" if stopped else "passed"
        job["history"].append({"attempt": job["attempt"], "status": job["status"], "checks": deepcopy(job["checks"]),
                                "inputs": values, "at": _now(), "kind": "simulation", "simulation": True})
        return {"node_id": node_id, "status": job["status"], "simulation": True,
                "message": "예시 점검 결과를 저장했습니다. 실제 DB·AP에는 접근하지 않았습니다."}

    async def handle_action(self, user, body):
        try:
            current = await self._user(user)
            if not isinstance(body, dict) or len(_dump(body).encode("utf-8")) > MAX_DOCUMENT_BYTES + 10_000:
                raise WorkflowError("invalid_request", "요청 내용과 크기를 확인해 주세요.")
            action = body.get("action")
            if not isinstance(action, str) or action not in {"create", "bind", "select", "update_inputs", "run", "save_draft", "validate_draft", "publish"}:
                raise WorkflowError("invalid_action", "지원하는 업무 동작을 선택해 주세요.")
            payload = body.get("payload", {})
            if not isinstance(payload, dict):
                raise WorkflowError("invalid_request", "작업 입력값을 확인해 주세요.")
            chat_id, case_id = body.get("chat_id", ""), body.get("case_id", "")
            if not isinstance(case_id, str) or len(case_id) > 200 or not isinstance(body.get("node_id", ""), str):
                raise WorkflowError("invalid_request", "작업 식별 정보를 확인해 주세요.")
            await self._chat(current, chat_id)
            assets = await self._assets(current)
            if action != "create" and (case_id or chat_id):
                with self._db() as db:
                    existing = self._case(db, _value(current, "id"), case_id, chat_id)
                if existing:
                    await self._chat(current, existing["chat_id"])
            with self._db(write=True) as db:
                result = None
                if action in {"save_draft", "validate_draft", "publish"}:
                    if _value(current, "role") != "admin":
                        raise WorkflowError("admin_required", "업무 절차 관리는 관리자만 사용할 수 있습니다.")
                    published, draft, revision, validated = self._catalog(db)
                    self._revision(body, revision)
                    if action == "save_draft":
                        definition = payload.get("definition")
                        if not isinstance(definition, dict) or len(_dump(definition).encode("utf-8")) > MAX_DOCUMENT_BYTES:
                            raise WorkflowError("invalid_definition", "저장할 업무 절차를 확인해 주세요.")
                        # Drafts may be structurally incomplete while editing;
                        # validation/publishing is the strict executable gate.
                        definition = deepcopy(definition)
                        for key in ("available_tools", "available_skills", "assets_available"):
                            definition.pop(key, None)
                        # Keep a reference to existing skills, never a copied
                        # private body whose grants could later change.
                        skills = definition.get("skills", {})
                        if isinstance(skills, dict):
                            for skill in skills.values():
                                if isinstance(skill, dict) and skill.get("source") == "open_webui":
                                    skill["body"] = ""
                        shape_errors = _draft_shape_errors(definition)
                        if shape_errors:
                            raise WorkflowError("invalid_definition", shape_errors[0])
                        definition["version"] = published["version"] + 1
                        db.execute("UPDATE catalog SET draft=?,revision=?,validated=NULL WHERE id=1", (_dump(definition), revision + 1))
                    else:
                        errors = validate_definition(draft)
                        if errors:
                            return {"ok": False, "error": {"code": "invalid_definition", "message": errors[0], "details": errors}}
                        if action == "validate_draft":
                            db.execute("UPDATE catalog SET validated=? WHERE id=1", (revision,))
                            result = {"valid": True, "revision": revision, "message": "구조·참조·입력 연결을 확인했습니다. 실제 업무 실행 검증은 별도입니다."}
                        else:
                            if validated != revision:
                                raise WorkflowError("validation_required", "저장한 최신 초안을 검증한 뒤 게시해 주세요.")
                            draft["version"] = published["version"] + 1
                            db.execute("UPDATE catalog SET published=?,draft=?,revision=?,validated=NULL WHERE id=1",
                                       (_dump(draft), _dump(draft), revision + 1))
                            result = {"version": draft["version"], "message": "게시했습니다. 새 진행 건부터 적용됩니다."}
                elif action == "create":
                    if self._case(db, _value(current, "id"), "", chat_id):
                        raise WorkflowError("chat_already_bound", "이 대화에는 이미 진행 중인 업무가 연결되어 있습니다.")
                    published = self._catalog(db)[0]
                    case = self._new_case(published, payload, chat_id, assets)
                    self._save_case(db, current, case, new=True)
                    case_id = case["id"]
                else:
                    case = self._case(db, _value(current, "id"), case_id, chat_id)
                    if not case:
                        raise WorkflowError("case_required", "진행할 업무를 먼저 선택해 주세요.")
                    case_id = case["id"]
                    self._revision(body, case["revision"])
                    if action == "bind":
                        if not chat_id:
                            raise WorkflowError("chat_required", "저장된 대화가 생긴 뒤 연결해 주세요.")
                        bound = self._case(db, _value(current, "id"), "", chat_id)
                        if bound and bound["id"] != case_id:
                            raise WorkflowError("chat_already_bound", "이 대화에는 다른 진행 건이 연결되어 있습니다.")
                        if case["chat_id"] and case["chat_id"] != chat_id:
                            raise WorkflowError("chat_mismatch", "기존 대화와 진행 건의 연결을 유지해 주세요.")
                        case["chat_id"] = chat_id
                    else:
                        node = self._node(case, body.get("node_id", ""))
                        if action == "select":
                            case["selected_id"] = node["id"]
                        elif action == "update_inputs":
                            values = payload.get("inputs")
                            if node["type"] != "j" or not isinstance(values, dict) or any(
                                    key not in INPUTS or not isinstance(value, str) or len(value) > 500 for key, value in values.items()):
                                raise WorkflowError("invalid_inputs", "잡의 공개 점검 대상만 입력해 주세요. 인증정보는 입력하지 않습니다.")
                            if any(case["jobs"][node["id"]]["inputs"].get(key) != value for key, value in values.items()):
                                self._invalidate(case, node["id"])
                                case["jobs"][node["id"]]["inputs"].update(values)
                        elif node["type"] == "j":
                            result = self._run_job(case, node, payload, assets)
                        else:
                            # Parent execution advances available automatic
                            # jobs; a bulk action never confirms human checks.
                            pending = _leaves(case["definition"]["nodes"], node["id"])
                            executed = []
                            while pending:
                                ready = [job_id for job_id in pending if _applicable(case, job_id)
                                         and not _missing(case, job_id) and case["jobs"][job_id]["status"] != "passed"
                                         and case["definition"]["nodes"][job_id]["mode"] == "tool"]
                                if not ready:
                                    break
                                for job_id in ready:
                                    try:
                                        executed.append(self._run_job(case, case["definition"]["nodes"][job_id], {}, assets))
                                    except WorkflowError as error:
                                        if error.code not in {"input_required", "skill_unavailable", "prerequisite_required"}:
                                            raise
                                        # A blocked sibling must not discard
                                        # evidence already produced by others.
                                        case["jobs"][job_id]["status"] = "blocked"
                                        case["jobs"][job_id]["blocked_reason"] = error.message
                                        executed.append({"node_id": job_id, "status": "blocked",
                                                         "code": error.code, "message": error.message})
                                    pending.remove(job_id)
                            if not executed:
                                raise WorkflowError("no_ready_jobs", "먼저 담당자 확인과 선행 작업을 완료해 주세요.")
                            result = {"jobs": executed, "simulation": True, "message": "요청한 예시 점검의 결과와 대기 사유를 기록했습니다."}
                    self._save_case(db, current, case)
                state = self._state(db, current, case_id, chat_id, assets)
                if result is not None:
                    state["result"] = result
                return state
        except WorkflowError as error:
            return {"ok": False, "error": {"code": error.code, "message": error.message}}
        except sqlite3.Error:
            return {"ok": False, "error": {"code": "state_unavailable", "message": "업무 상태를 저장하지 못했습니다. 최신 상태를 확인한 뒤 다시 시도해 주세요."}}


def _production_service():
    global _service
    if _service is None:
        from open_webui.env import DATA_DIR
        from open_webui.models.chats import Chats
        from open_webui.models.users import Users

        _service = WorkflowService(Path(DATA_DIR) / "ees-work.sqlite3", Users.get_user_by_id,
                                   Chats.get_chat_by_id, _registered_assets)
    return _service


async def _registered_assets(user):
    """Use pinned WebUI's access-filtered local registries; never load code.

    Tool server discovery is deliberately not invoked here: the workflow editor
    must not probe remote MCP/OpenAPI servers just to display its navigation.
    """
    from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
    from open_webui.env import ENABLE_PLUGINS
    from open_webui.models.skills import Skills
    from open_webui.models.tools import Tools

    user_id = None if _value(user, "role") == "admin" and BYPASS_ADMIN_ACCESS_CONTROL else _value(user, "id")
    registered_tools = await Tools.get_tools(defer_content=True, user_id=user_id, permission="read") if ENABLE_PLUGINS else []
    registered_skills = await Skills.get_skills(user_id=user_id)
    return {
        "tools": [{"id": tool.id, "name": tool.name} for tool in registered_tools],
        "skills": [{"id": skill.id, "name": skill.name} for skill in registered_skills if skill.is_active],
        "skill_bodies": {skill.id: skill.content for skill in registered_skills if skill.is_active},
        "skill_versions": {skill.id: skill.updated_at for skill in registered_skills if skill.is_active},
        "available": True,
    }


async def get_state(user, chat_id="", case_id=""):
    return await _production_service().get_state(user, chat_id, case_id)


async def handle_action(user, body):
    return await _production_service().handle_action(user, body)


def install(app, verified_user):
    from fastapi import Body, Depends
    from fastapi.responses import JSONResponse

    def response(value):
        code = value.get("error", {}).get("code")
        status = 200 if value.get("ok") else 401 if code == "unauthorized" else 403 if code in {
            "chat_forbidden", "admin_required"} else 409 if code in {"revision_conflict", "chat_already_bound", "chat_mismatch"} else 400
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    @app.get("/api/ees-work/state", include_in_schema=False)
    async def state_route(chat_id: str = "", case_id: str = "", user=Depends(verified_user)):
        return response(await get_state(user, chat_id, case_id))

    @app.post("/api/ees-work/action", include_in_schema=False)
    async def action_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await handle_action(user, body))
