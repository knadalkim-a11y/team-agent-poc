"""System-authorized, process-scoped editing in the existing workflow database.

Native users and group membership remain authoritative. The additive tables do
not contain a second user roster, Native secrets, code, or private skill bodies.
The only published source remains catalog.published; cases are never rewritten.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import json
import re
import sqlite3
from uuid import uuid4

from .ees_workflow_contract import validate_execution, remap_execution
from .ees_workflow_definition import (
    CATEGORIES, SYSTEMS, INPUTS, IDENTIFIER, MAX_DOCUMENT_BYTES, _dump,
    _ancestors, _leaves, _dependencies, _policy, validate_definition,
)


class WorkflowError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _value(item, key, default=None):
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _fail(code, message):
    raise WorkflowError(code, message)


def _subtree(definition, process_id):
    nodes = definition["nodes"]
    if process_id not in nodes or nodes[process_id].get("type") != "p":
        _fail("process_not_found", "접근할 수 있는 절차를 찾지 못했습니다.")
    included = {key for key in nodes if _ancestors(nodes, key)[0]["id"] == process_id}
    return {"process_id": process_id,
            "nodes": {key: deepcopy(value) for key, value in nodes.items() if key in included},
            "tools": {}, "skills": {}}


class AuthoringMixin:
    def _init_authoring(self, db):
        db.execute("CREATE TABLE IF NOT EXISTS authoring_meta (id INTEGER PRIMARY KEY CHECK(id=1), protocol INTEGER NOT NULL, mirror_hash TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS system_groups (system_id TEXT PRIMARY KEY, group_id TEXT NOT NULL, active INTEGER NOT NULL, revision INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS process_management (process_id TEXT PRIMARY KEY, owner_system TEXT NOT NULL, owner_revision INTEGER NOT NULL, draft TEXT NOT NULL, draft_revision INTEGER NOT NULL, base_fingerprint TEXT NOT NULL, validation TEXT, published_version INTEGER, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS authoring_ids (id TEXT PRIMARY KEY, process_id TEXT NOT NULL, kind TEXT NOT NULL, retired INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS authoring_legacy (id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT UNIQUE NOT NULL, published TEXT NOT NULL, draft TEXT NOT NULL, revision INTEGER NOT NULL, validated INTEGER, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS authoring_requests (actor TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, process_id TEXT NOT NULL, system_id TEXT NOT NULL, outcome TEXT NOT NULL, PRIMARY KEY(actor,request_id))")
        db.execute("CREATE TABLE IF NOT EXISTS authoring_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL, process_id TEXT NOT NULL, system_id TEXT NOT NULL, before_revision INTEGER, after_revision INTEGER, owner_revision INTEGER, before_hash TEXT, after_hash TEXT, outcome TEXT NOT NULL, request_id TEXT NOT NULL, created_at TEXT NOT NULL)")
        row = db.execute("SELECT * FROM catalog WHERE id=1").fetchone()
        marker = db.execute("SELECT * FROM authoring_meta WHERE id=1").fetchone()
        fingerprint = _hash({key: row[key] for key in ("published", "draft", "revision", "validated")})
        # A Restore can leave new legacy edits or an old-program publication.
        # Preserve exact original TEXT and revisions before replacing the mirror.
        if not marker or row["draft"] != row["published"] or marker["mirror_hash"] != _hash(row["published"]):
            db.execute("INSERT OR IGNORE INTO authoring_legacy(fingerprint,published,draft,revision,validated,created_at) VALUES(?,?,?,?,?,?)",
                       (fingerprint, row["published"], row["draft"], row["revision"], row["validated"], _now()))
            db.execute("UPDATE catalog SET draft=published,validated=NULL WHERE id=1")
            db.execute("INSERT INTO authoring_meta VALUES(1,1,?) ON CONFLICT(id) DO UPDATE SET mirror_hash=excluded.mirror_hash", (_hash(row["published"]),))
        published = json.loads(row["published"])
        for process in (node for node in published["nodes"].values() if node.get("type") == "p"):
            workflow = _subtree(published, process["id"])
            db.execute("INSERT OR IGNORE INTO process_management VALUES(?,?,0,?,0,?,NULL,?,'',?,0)",
                       (process["id"], "UNASSIGNED", _dump(workflow), _hash(workflow), published["version"], _now()))
            for node_id in workflow["nodes"]:
                db.execute("INSERT OR IGNORE INTO authoring_ids VALUES(?,?,?,0)", (node_id, process["id"], "nodes"))
        for kind in ("tools", "skills"):
            for item_id in published[kind]:
                db.execute("INSERT OR IGNORE INTO authoring_ids VALUES(?,?,?,0)", (item_id, "", kind))

    async def _authorizer(self, user):
        try:
            current = await self._user(user)
        except WorkflowError:
            raise
        except Exception:
            _fail("authoring_authorization_unavailable", "현재 계정의 권한을 확인하지 못했습니다.")
        admin = _value(current, "role") == "admin"
        groups = []
        try:
            if self.group_lookup is not None:
                groups = await _resolve(self.group_lookup(_value(current, "id")))
                if not isinstance(groups, (list, tuple)):
                    raise ValueError("group result")
            elif not admin:
                with self._db() as db:
                    if db.execute("SELECT 1 FROM system_groups WHERE active=1 LIMIT 1").fetchone():
                        raise ValueError("group source unavailable")
            group_ids = {_value(group, "id") for group in groups if isinstance(_value(group, "id"), str)}
        except Exception:
            _fail("authoring_authorization_unavailable", "담당 권한을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        with self._db() as db:
            systems = list(SYSTEMS) + ["COMMON", "UNASSIGNED"] if admin else [row["system_id"] for row in db.execute(
                "SELECT system_id,group_id FROM system_groups WHERE active=1 ORDER BY system_id") if row["group_id"] in group_ids]
        return current, {"ok": True, "actor_id": _value(current, "id"), "is_admin": admin,
                         "managed_systems": systems, "can_author": bool(systems), "protocol": 1}, group_ids

    async def authoring_capabilities(self, user):
        try:
            return (await self._authorizer(user))[1]
        except WorkflowError as error:
            return self._authoring_failure(error)
        except sqlite3.Error:
            return self._authoring_failure(WorkflowError("authoring_unavailable", "절차 관리 상태를 불러오지 못했습니다."))

    # Public name is intentionally distinct from runtime state/can_manage.
    capabilities = authoring_capabilities

    @staticmethod
    def _authoring_failure(error):
        return {"ok": False, "error": {"code": error.code, "message": error.message}}

    @staticmethod
    def _authorize_system(db, capabilities, group_ids, system_id):
        if system_id not in (*SYSTEMS, "COMMON", "UNASSIGNED"):
            _fail("workflow_manage_forbidden", "이 시스템의 절차를 관리할 권한이 없습니다.")
        if capabilities["is_admin"]:
            return
        row = db.execute("SELECT * FROM system_groups WHERE system_id=?", (system_id,)).fetchone()
        if not row or not row["active"] or row["group_id"] not in group_ids or system_id not in SYSTEMS:
            _fail("workflow_manage_forbidden", "이 시스템의 절차를 관리할 권한이 없습니다.")

    def _authorize_process(self, db, capabilities, group_ids, process_id):
        row = db.execute("SELECT * FROM process_management WHERE process_id=? AND deleted=0", (process_id,)).fetchone()
        if not row:
            _fail("process_not_found", "접근할 수 있는 절차를 찾지 못했습니다.")
        try:
            self._authorize_system(db, capabilities, group_ids, row["owner_system"])
        except WorkflowError:
            _fail("process_not_found", "접근할 수 있는 절차를 찾지 못했습니다.")
        return row

    @staticmethod
    def _metadata(row):
        workflow = json.loads(row["draft"])
        root = workflow["nodes"][row["process_id"]]
        return {"process_id": row["process_id"], "name": root["name"], "owner_system": row["owner_system"],
                "owner_revision": row["owner_revision"], "draft_revision": row["draft_revision"],
                "published_version": row["published_version"], "enabled": root.get("enabled", True),
                "updated_by": row["updated_by"], "updated_at": row["updated_at"]}

    async def _native_groups(self):
        if self.group_list_lookup is None:
            return []
        try:
            groups = await _resolve(self.group_list_lookup())
            if not isinstance(groups, (list, tuple)):
                raise ValueError("groups")
            return [{"id": _value(group, "id"), "name": _value(group, "name", "")}
                    for group in groups if isinstance(_value(group, "id"), str)]
        except Exception:
            _fail("authoring_authorization_unavailable", "담당 그룹 목록을 확인하지 못했습니다.")

    def _authoring_state(self, db, capabilities, group_ids, assets, system_id="", process_id="", native_groups=None, legacy_id=None):
        if process_id:
            selected = self._authorize_process(db, capabilities, group_ids, process_id)
            if system_id and system_id != selected["owner_system"]:
                _fail("workflow_manage_forbidden", "선택한 관리 시스템과 절차가 일치하지 않습니다.")
            system_id = selected["owner_system"]
        else:
            selected = None
            system_id = system_id or next(iter(capabilities["managed_systems"]), "")
        if system_id:
            self._authorize_system(db, capabilities, group_ids, system_id)
        elif not capabilities["can_author"]:
            _fail("workflow_manage_forbidden", "관리할 수 있는 시스템이 없습니다.")
        published = self._catalog(db)[0]
        # P-local definitions are not offered to other systems as global choices.
        local_ids = {row["id"] for row in db.execute("SELECT id FROM authoring_ids WHERE process_id<>'' AND kind IN ('tools','skills')")}
        references = {key: deepcopy(published[key]) for key in ("sites", "systems")}
        for kind in ("tools", "skills"):
            allowed = {item["id"] for item in assets.get(kind, [])}
            references[kind] = {key: deepcopy(value) for key, value in published[kind].items()
                                if key not in local_ids and (value.get("source") != "open_webui" or value.get("reference") in allowed)}
            for item in references[kind].values():
                if item.get("source") == "open_webui" and kind == "skills":
                    item["body"] = ""
        references.update(available_tools=assets.get("tools", []), available_skills=assets.get("skills", []),
                          assets_available=assets.get("available", True))
        rows = db.execute("SELECT * FROM process_management WHERE owner_system=? AND deleted=0 ORDER BY rowid", (system_id,)).fetchall()
        result = {"ok": True, "actor_id": capabilities["actor_id"], "capabilities": capabilities,
                  "system_id": system_id, "processes": [self._metadata(row) for row in rows],
                  "process": None, "references": references}
        if selected:
            workflow = json.loads(selected["draft"])
            validation = json.loads(selected["validation"]) if selected["validation"] else None
            valid = validation is not None and validation == self._validation_token(db, selected, workflow, published, assets)
            current_fingerprint = self._published_hash(db, published, selected["process_id"])
            baseline_changed = current_fingerprint != selected["base_fingerprint"]
            publication_state = ("changed" if baseline_changed else "unchanged") if current_fingerprint else (
                "removed" if selected["published_version"] is not None else "unpublished")
            result["process"] = {**self._metadata(selected), "workflow": workflow,
                "base_process_fingerprint": selected["base_fingerprint"], "draft_hash": _hash(workflow),
                "published_workflow": self._published_workflow(db, published, selected["process_id"]),
                "publication_reconciliation": {"required": baseline_changed,
                    "current_published_fingerprint": current_fingerprint, "state": publication_state,
                    "catalog_version": published["version"], "can_reconcile": capabilities["is_admin"] and baseline_changed},
                "validated_revision": selected["draft_revision"] if valid else None, "validation": validation if valid else None}
        if capabilities["is_admin"]:
            groups = native_groups or []
            ids = {group["id"] for group in groups}
            mappings = {row["system_id"]: dict(row) for row in db.execute("SELECT * FROM system_groups")}
            result["native_groups"] = groups
            result["system_groups"] = []
            for system in SYSTEMS:
                mapping = mappings.get(system, {"system_id": system, "group_id": "", "active": 0, "revision": 0})
                result["system_groups"].append({**mapping, "active": bool(mapping["active"]),
                    "status": "unlinked" if not mapping["group_id"] else "inactive" if not mapping["active"] else "ok" if mapping["group_id"] in ids else "missing"})
            result["legacy_snapshots"] = []
            for row in db.execute("SELECT id,draft,revision,created_at FROM authoring_legacy ORDER BY id DESC"):
                draft = json.loads(row["draft"])
                result["legacy_snapshots"].append({"id": row["id"], "revision": row["revision"], "created_at": row["created_at"],
                    "processes": [{"id": node["id"], "name": node["name"]} for node in draft.get("nodes", {}).values() if node.get("type") == "p"]})
            if legacy_id is not None:
                row = db.execute("SELECT * FROM authoring_legacy WHERE id=?", (legacy_id,)).fetchone()
                if not row:
                    _fail("process_not_found", "보존된 이전 초안을 찾지 못했습니다.")
                result["legacy_snapshot"] = {**dict(row), "published": json.loads(row["published"]), "draft": json.loads(row["draft"])}
        elif legacy_id is not None:
            _fail("workflow_manage_forbidden", "이전 전체 초안은 관리자만 확인할 수 있습니다.")
        return result

    async def get_authoring(self, user, system_id="", process_id="", legacy_id=None):
        try:
            current, capabilities, groups = await self._authorizer(user)
            if not isinstance(system_id, str) or not isinstance(process_id, str) or len(process_id) > 160:
                _fail("invalid_request", "조회할 절차를 확인해 주세요.")
            assets = await self._assets(current)
            native = await self._native_groups() if capabilities["is_admin"] else None
            with self._db() as db:
                return self._authoring_state(db, capabilities, groups, assets, system_id, process_id, native, legacy_id)
        except WorkflowError as error:
            return self._authoring_failure(error)
        except (sqlite3.Error, ValueError, TypeError):
            return self._authoring_failure(WorkflowError("authoring_unavailable", "절차 관리 상태를 불러오지 못했습니다."))

    @staticmethod
    def _authoring_revision(body, row):
        if type(body.get("expected_owner_revision")) is not int or body["expected_owner_revision"] != row["owner_revision"]:
            _fail("workflow_baseline_changed", "관리 범위가 변경되었습니다. 최신 절차를 다시 확인해 주세요.")
        if type(body.get("expected_draft_revision")) is not int or body["expected_draft_revision"] != row["draft_revision"]:
            _fail("draft_revision_conflict", "다른 담당자가 먼저 저장했습니다. 내 변경을 유지하고 최신 초안을 확인해 주세요.")

    @staticmethod
    def _fresh_id(db, process_id, kind):
        item_id = {"nodes": "ew", "tools": "ewtool", "skills": "ewskill"}[kind] + "-" + uuid4().hex
        db.execute("INSERT INTO authoring_ids VALUES(?,?,?,0)", (item_id, process_id or item_id, kind))
        return item_id

    @staticmethod
    def _blank_node(node_id, kind, name, category, parent=None):
        return {"id": node_id, "type": kind, "name": name, "parent": parent, "children": [],
                "description": "", "instructions": "", "rule": "", "condition": "all", "mode": "manual",
                "tools": [], "skills": [], "bindings": {}, "deps": [], "category": category, "enabled": True}

    def _published_workflow(self, db, published, process_id):
        if process_id not in published["nodes"]:
            return None
        workflow = _subtree(published, process_id)
        for row in db.execute("SELECT id,kind FROM authoring_ids WHERE process_id=? AND kind IN ('tools','skills')", (process_id,)):
            if row["id"] in published[row["kind"]]:
                workflow[row["kind"]][row["id"]] = deepcopy(published[row["kind"]][row["id"]])
        return workflow

    def _published_hash(self, db, published, process_id):
        value = self._published_workflow(db, published, process_id)
        return _hash(value) if value is not None else ""

    def _merge_workflow(self, db, published, workflow):
        merged = deepcopy(published)
        process_id = workflow["process_id"]
        old = self._published_workflow(db, published, process_id)
        if set(workflow["nodes"]) & (set(published["nodes"]) - set(old["nodes"] if old else {})):
            _fail("invalid_workflow_scope", "다른 게시 절차가 사용하는 항목은 덮어쓸 수 없습니다.")
        for kind in ("tools", "skills"):
            for item_id in set(workflow[kind]) | set(old[kind] if old else {}):
                if published[kind].get(item_id) != workflow[kind].get(item_id) and any(
                        node_id not in (old["nodes"] if old else {}) and item_id in node[kind]
                        for node_id, node in published["nodes"].items()):
                    _fail("invalid_workflow_scope", "다른 게시 절차가 참조하는 연결은 변경하거나 삭제할 수 없습니다.")
        if old:
            for node_id in old["nodes"]:
                merged["nodes"].pop(node_id, None)
            for kind in ("tools", "skills"):
                for item_id in old[kind]:
                    merged[kind].pop(item_id, None)
        category = workflow["nodes"][process_id]["category"]
        old_position = merged["roots"][category].index(process_id) if process_id in merged["roots"][category] else len(merged["roots"][category])
        for roots in merged["roots"].values():
            if process_id in roots:
                roots.remove(process_id)
        merged["roots"][category].insert(old_position, process_id)
        for kind in ("nodes", "tools", "skills"):
            merged[kind].update(deepcopy(workflow[kind]))
        return merged

    def _validation_token(self, db, row, workflow, published, assets):
        used = {kind: {item_id for node in workflow["nodes"].values() for item_id in node[kind]} for kind in ("tools", "skills")}
        definitions = {kind: {item_id: workflow[kind].get(item_id, published[kind].get(item_id)) for item_id in used[kind]} for kind in used}
        availability = {}
        for kind in used:
            accessible = {item["id"] for item in assets.get(kind, [])}
            availability[kind] = {item_id: bool(item and (item.get("source") != "open_webui" or (assets.get("available", True) and item.get("reference") in accessible))) for item_id, item in definitions[kind].items()}
        native_versions = {kind: {item_id: assets.get("tool_versions" if kind == "tools" else "skill_versions", {}).get(item.get("reference"))
                                  for item_id, item in definitions[kind].items() if item and item.get("source") == "open_webui"}
                           for kind in definitions}
        skill_hashes = {item_id: _hash(assets.get("skill_bodies", {}).get(item.get("reference")))
                        for item_id, item in definitions["skills"].items() if item and item.get("source") == "open_webui"}
        return {"process_id": row["process_id"], "draft_revision": row["draft_revision"], "draft_hash": _hash(workflow),
                "owner_revision": row["owner_revision"], "base_process_fingerprint": self._published_hash(db, published, row["process_id"]),
                "references_hash": _hash({"definitions": definitions, "policy": _policy(), "catalog_policy": published["skills"].get("common"), "sites": published["sites"], "systems": published["systems"]}),
                "execution_references_hash": _hash(self._execution_reference_state(workflow, assets)),
                "availability_hash": _hash(availability), "native_references_hash": _hash({"versions": native_versions, "skill_hashes": skill_hashes})}

    @staticmethod
    def _execution_reference_state(workflow, assets):
        capabilities = assets.get("execution_capabilities", [])
        state = []
        for node in workflow["nodes"].values():
            execution = node.get("execution", {})
            for call in execution.get("calls", []):
                reference = call["reference"]
                match = next((item for item in capabilities if item.get("reference") == reference), None)
                state.append({"reference": reference, "state": match.get("state") if match else "unavailable",
                              "schema": match.get("schema") if match else None})
            for ref in execution.get("skill_refs", []):
                body = assets.get("skill_bodies", {}).get(ref["skill_id"])
                accessible = ref["skill_id"] in {item["id"] for item in assets.get("skills", [])}
                state.append({"skill_id": ref["skill_id"], "content_hash": _hash(body) if body is not None and accessible else None,
                              "expected_hash": ref["content_hash"]})
        return state

    def _validate_execution_publication(self, workflow, assets):
        for reference in self._execution_reference_state(workflow, assets):
            if "skill_id" in reference:
                if reference["content_hash"] != reference["expected_hash"]:
                    _fail("skill_revalidation_required", "필수 스킬의 접근 권한이나 내용이 변경되었습니다. 다시 확인해 주세요.")
            elif reference["state"] != "allowed":
                _fail("native_revalidation_required", "자동 실행 기능의 정확한 버전 승인이 필요합니다. 초안은 보존했습니다.")

    def _validate_for_publication(self, db, row, workflow, published, assets):
        if self._published_hash(db, published, row["process_id"]) != row["base_fingerprint"]:
            _fail("workflow_baseline_changed", "게시본이 변경되었습니다. 최신 게시본과 초안을 비교해 주세요.")
        for kind in ("tools", "skills"):
            accessible = {item["id"] for item in assets.get(kind, [])}
            for item_id in {key for node in workflow["nodes"].values() for key in node[kind]}:
                item = workflow[kind].get(item_id, published[kind].get(item_id))
                if not item:
                    _fail("reference_unavailable", "삭제되거나 사용할 수 없는 참조가 있습니다. 초안은 보존했습니다.")
                if item.get("source") == "open_webui" and (not assets.get("available", True) or item.get("reference") not in accessible):
                    _fail("reference_unavailable", "현재 계정으로 필수 자산을 확인할 수 없어 게시하지 않았습니다.")
        self._validate_execution_publication(workflow, assets)
        merged = self._merge_workflow(db, published, workflow)
        errors = validate_definition(merged)
        if errors:
            _fail("invalid_definition", errors[0])
        return merged

    def _prepare_workflow(self, db, row, incoming, published, assets):
        if not isinstance(incoming, dict) or set(incoming) != {"process_id", "nodes", "tools", "skills"} or incoming["process_id"] != row["process_id"]:
            _fail("invalid_workflow_scope", "선택한 워크플로우 하나의 내용만 저장할 수 있습니다.")
        if len(_dump(incoming).encode("utf-8")) > MAX_DOCUMENT_BYTES:
            _fail("invalid_definition", "업무 절차가 허용 크기를 초과했습니다.")
        old = json.loads(row["draft"])
        workflow, id_map = deepcopy(incoming), {}
        all_ids = []
        for kind in ("nodes", "tools", "skills"):
            if isinstance(workflow.get(kind), dict):
                all_ids.extend(workflow[kind])
        if len(all_ids) != len(set(all_ids)):
            _fail("invalid_workflow_scope", "각 항목은 서로 다른 식별자를 사용해야 합니다.")
        for kind, maximum in (("nodes", 250), ("tools", 200), ("skills", 200)):
            items = workflow[kind]
            if not isinstance(items, dict) or len(items) > maximum:
                _fail("invalid_definition", "항목 수와 형식을 확인해 주세요.")
            for item_id, item in items.items():
                if not isinstance(item_id, str) or not IDENTIFIER.fullmatch(item_id) or not isinstance(item, dict) or item.get("id") != item_id:
                    _fail("invalid_definition", "항목 식별자를 확인해 주세요.")
                reservation = db.execute("SELECT * FROM authoring_ids WHERE id=?", (item_id,)).fetchone()
                if item_id.startswith("new-") and reservation is None:
                    id_map[item_id] = self._fresh_id(db, row["process_id"], kind)
                elif (not reservation or reservation["process_id"] != row["process_id"] or reservation["kind"] != kind or reservation["retired"]):
                    _fail("invalid_workflow_scope", "다른 절차의 항목이나 사용할 수 없는 식별자는 저장할 수 없습니다.")
        for kind in ("nodes", "tools", "skills"):
            workflow[kind] = {id_map.get(key, key): dict(item, id=id_map.get(key, key)) for key, item in workflow[kind].items()}
        for node in workflow["nodes"].values():
            for field in ("children", "deps", "tools", "skills"):
                if not isinstance(node.get(field), list) or any(not isinstance(item, str) for item in node[field]):
                    _fail("invalid_definition", "작업의 연결 목록을 확인해 주세요.")
                node[field] = [id_map.get(item, item) for item in node[field]]
            if not isinstance(node.get("bindings"), dict):
                _fail("invalid_definition", "입력 연결을 확인해 주세요.")
            node["bindings"] = {id_map.get(key, key): value for key, value in node["bindings"].items()}
            if node.get("parent") is not None and not isinstance(node.get("parent"), str):
                _fail("invalid_definition", "상위 단계를 확인해 주세요.")
            node["parent"] = id_map.get(node.get("parent"), node.get("parent"))
            remap_execution(node, id_map)
        self._check_workflow_shape(db, row, workflow, old, published, assets)
        for kind in ("nodes", "tools", "skills"):
            for removed in set(old[kind]) - set(workflow[kind]):
                db.execute("UPDATE authoring_ids SET retired=1 WHERE id=? AND process_id=?", (removed, row["process_id"]))
        return workflow, id_map

    def _check_workflow_shape(self, db, row, workflow, old, published, assets):
        nodes = workflow["nodes"]
        process_id = row["process_id"]
        root = nodes.get(process_id)
        if not root or root.get("type") != "p" or root.get("parent") is not None or root.get("category") not in CATEGORIES:
            _fail("invalid_workflow_scope", "선택한 최상위 워크플로우를 유지해 주세요.")
        node_fields = {"id", "name", "type", "parent", "children", "description", "instructions", "rule", "condition", "mode", "tools", "skills", "bindings", "deps", "category", "enabled", "failOnce", "systems", "execution", "execution_inputs", "execution_final"}
        for node_id, node in nodes.items():
            if set(node) - node_fields or node.get("type") not in ("p", "t", "j") or (node.get("type") == "p" and node_id != process_id):
                _fail("invalid_workflow_scope", "절차의 편집 가능한 항목만 저장해 주세요.")
            if not isinstance(node.get("name"), str) or not node["name"].strip() or len(node["name"]) > 160:
                _fail("invalid_definition", "작업 이름을 입력해 주세요.")
            if node.get("category") != root["category"] or node.get("mode") not in ("manual", "tool", "draft"):
                _fail("invalid_definition", "업무 분류와 수행 방식을 확인해 주세요.")
            if any(not isinstance(node.get(key, ""), str) for key in ("description", "instructions", "rule", "condition")) or any(type(node.get(key, False)) is not bool for key in ("enabled", "failOnce")):
                _fail("invalid_definition", "작업 설명과 사용 여부를 확인해 주세요.")
            if row["owner_system"] in SYSTEMS:
                if node_id == process_id and node.get("systems") != [row["owner_system"]]:
                    _fail("invalid_workflow_scope", "관리 시스템 하나에만 적용되는 절차를 저장해 주세요.")
                if "systems" in node and node["systems"] != [row["owner_system"]]:
                    _fail("invalid_workflow_scope", "적용 시스템을 다른 시스템으로 확대할 수 없습니다.")
            elif "systems" in node and (not isinstance(node["systems"], list) or not node["systems"] or any(system not in SYSTEMS for system in node["systems"])):
                _fail("invalid_definition", "적용 시스템을 확인해 주세요.")
            parent = nodes.get(node.get("parent"))
            if node_id != process_id and (not parent or parent.get("type") != {"t": "p", "j": "t"}.get(node["type"]) or node_id not in parent.get("children", [])):
                _fail("invalid_workflow_scope", "선택한 워크플로우 안의 단계 연결만 허용됩니다.")
            for field in ("children", "deps", "tools", "skills"):
                values = node.get(field)
                if not isinstance(values, list) or any(not isinstance(item, str) for item in values) or len(values) != len(set(values)):
                    _fail("invalid_definition", "중복 또는 잘못된 참조를 확인해 주세요.")
            if node["type"] == "j" and node["children"]:
                _fail("invalid_workflow_scope", "작업 아래에 다른 단계를 추가할 수 없습니다.")
            if any(child not in nodes or nodes[child].get("parent") != node_id for child in node["children"]) or any(dep not in nodes for dep in node["deps"]):
                _fail("invalid_workflow_scope", "다른 워크플로우와 교차 연결할 수 없습니다.")
            if not isinstance(node.get("bindings"), dict) or any(key not in node["tools"] or value not in INPUTS for key, value in node["bindings"].items()):
                _fail("invalid_definition", "공개 입력 항목의 연결을 확인해 주세요.")
        execution_definition = {**published, "nodes": {**published["nodes"], **nodes}}
        for node in nodes.values():
            errors = validate_execution(node, execution_definition)
            if errors:
                _fail("invalid_execution_contract", errors[0])
        # P/T/J types make the containment graph acyclic. Prerequisite cycles are
        # also refused at save time, including inherited self dependencies.
        graph = {key: {leaf for dep in _dependencies(nodes, key) for leaf in _leaves(nodes, dep)} for key, node in nodes.items() if node["type"] == "j"}
        seen, active = set(), set()
        def visit(key):
            if key in active:
                return False
            if key in seen:
                return True
            active.add(key)
            if any(not visit(dep) for dep in graph.get(key, ())):
                return False
            active.remove(key)
            seen.add(key)
            return True
        if any(not visit(key) for key in graph):
            _fail("invalid_definition", "선행 작업이 순환합니다. 서로를 기다리는 연결을 수정해 주세요.")
        for kind in ("tools", "skills"):
            accessible = {item["id"] for item in assets.get(kind, [])}
            allowed_fields = {"id", "name", "source", "reference", "input", "adapter", "enabled"} if kind == "tools" else {"id", "name", "source", "reference", "type", "body"}
            for item_id, item in workflow[kind].items():
                if (set(item) - allowed_fields or item.get("source") != "open_webui" or not isinstance(item.get("name"), str) or not item["name"].strip() or len(item["name"]) > 160
                        or not isinstance(item.get("reference"), str) or not item["reference"] or len(item["reference"]) > 200
                        or (kind == "tools" and (item.get("adapter") != "unavailable" or item.get("input") not in INPUTS or type(item.get("enabled", True)) is not bool))
                        or (kind == "skills" and (item.get("type") != "skill" or item.get("body", "") != ""))):
                    _fail("invalid_workflow_scope", "기존 자산의 참조만 연결할 수 있습니다. 코드·본문·인증정보는 저장하지 않습니다.")
                if old[kind].get(item_id) != item and (not assets.get("available", True) or item["reference"] not in accessible):
                    _fail("reference_unavailable", "현재 계정으로 선택할 수 있는 자산을 연결해 주세요.")
            old_refs = {key for node in old["nodes"].values() for key in node[kind]}
            for item_id in {key for node in nodes.values() for key in node[kind]}:
                if item_id in workflow[kind]:
                    continue
                reservation = db.execute("SELECT * FROM authoring_ids WHERE id=?", (item_id,)).fetchone()
                item = published[kind].get(item_id)
                if reservation and reservation["process_id"] and reservation["process_id"] != process_id:
                    _fail("invalid_workflow_scope", "다른 절차 전용 참조는 연결할 수 없습니다.")
                if not item and item_id not in old_refs:
                    _fail("reference_unavailable", "등록된 참조를 선택해 주세요.")
                if item and item.get("source") == "open_webui" and item_id not in old_refs and (not assets.get("available", True) or item.get("reference") not in accessible):
                    _fail("reference_unavailable", "현재 계정으로 사용할 수 있는 참조를 선택해 주세요.")

    @staticmethod
    def _audit(db, actor, action, process_id, system_id, request_id, before=None, after=None, outcome="ok", mapping_before=None, mapping_after=None):
        db.execute("INSERT INTO authoring_audit(actor,action,process_id,system_id,before_revision,after_revision,owner_revision,before_hash,after_hash,outcome,request_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (actor, action, process_id, system_id, before["draft_revision"] if before else mapping_before["revision"] if mapping_before else None,
                    after["draft_revision"] if after else mapping_after["revision"] if mapping_after else None, after["owner_revision"] if after else None,
                    (before["base_fingerprint"] if action == "reconcile_publication" else _hash(json.loads(before["draft"]))) if before else _hash(mapping_before) if mapping_before else None,
                    (after["base_fingerprint"] if action == "reconcile_publication" else _hash(json.loads(after["draft"]))) if after else _hash(mapping_after) if mapping_after else None,
                    outcome, request_id, _now()))

    def _write_publication(self, db, row, merged, workflow, actor):
        _, _, revision, _ = self._catalog(db)
        merged["version"] += 1
        encoded = _dump(merged)
        db.execute("UPDATE catalog SET published=?,draft=?,revision=?,validated=NULL WHERE id=1", (encoded, encoded, revision + 1))
        db.execute("UPDATE authoring_meta SET mirror_hash=? WHERE id=1", (_hash(encoded),))
        db.execute("UPDATE process_management SET draft=?,base_fingerprint=?,validation=NULL,published_version=?,updated_by=?,updated_at=? WHERE process_id=?",
                   (_dump(workflow), _hash(workflow), merged["version"], actor, _now(), row["process_id"]))
        return merged["version"]

    async def authoring_action(self, user, body):
        current = None
        audit_target = None
        try:
            current, capabilities, group_ids = await self._authorizer(user)
            if not isinstance(body, dict) or len(_dump(body).encode("utf-8")) > MAX_DOCUMENT_BYTES + 10000:
                _fail("invalid_request", "요청 내용과 크기를 확인해 주세요.")
            allowed = {"action", "system_id", "process_id", "expected_draft_revision", "expected_owner_revision", "expected_mapping_revision", "request_id", "payload"}
            if set(body) - allowed:
                _fail("invalid_request", "작성 요청에는 권한 주장이나 전체 절차를 포함할 수 없습니다.")
            action = body.get("action")
            actions = {"create", "save_draft", "validate_draft", "publish", "disable", "delete", "copy", "set_system_group", "transfer_owner", "import_legacy", "add_node", "reconcile_publication"}
            if not isinstance(action, str) or action not in actions:
                _fail("invalid_action", "지원하는 절차 관리 동작을 선택해 주세요.")
            request_id = body.get("request_id")
            if not isinstance(request_id, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id) is None:
                _fail("invalid_request_id", "절차 요청 식별자를 확인해 주세요.")
            process_id, system_id, payload = body.get("process_id", ""), body.get("system_id", ""), body.get("payload", {})
            if not isinstance(process_id, str) or len(process_id) > 160 or not isinstance(system_id, str) or not isinstance(payload, dict):
                _fail("invalid_request", "절차와 입력값을 확인해 주세요.")
            payload_fields = {"create": {"name", "category"}, "copy": {"source_process_id", "name"}, "save_draft": {"workflow"}, "validate_draft": set(), "publish": set(), "disable": set(), "delete": set(), "set_system_group": {"group_id", "active"}, "transfer_owner": {"owner_system"}, "import_legacy": {"snapshot_id", "source_process_id"}, "add_node": {"parent_id", "name"}, "reconcile_publication": {"expected_published_fingerprint"}}
            if set(payload) - payload_fields[action]:
                _fail("invalid_workflow_scope", "선택한 절차의 허용된 편집 내용만 요청해 주세요.")
            audit_target = (action, process_id if IDENTIFIER.fullmatch(process_id or "") else "", system_id if system_id in (*SYSTEMS, "COMMON", "UNASSIGNED") else "", request_id)
            native = await self._native_groups() if capabilities["is_admin"] else None
            # Fetch assets after the last authorization await, so ACL/version/body
            # changes during group lookup cannot reuse an earlier asset snapshot.
            # There is no await between this fetch and the local write transaction.
            # Native/EES databases are separate; this is not distributed atomicity.
            current, capabilities, group_ids = await self._authorizer(current)
            assets = await self._assets(current)
            actor = capabilities["actor_id"]
            fingerprint = _hash(body)
            with self._db(write=True) as db:
                if action in {"set_system_group", "transfer_owner", "import_legacy", "reconcile_publication"} and not capabilities["is_admin"]:
                    _fail("workflow_manage_forbidden", "이 관리 설정은 전체 관리자만 변경할 수 있습니다.")
                row = None
                if action in {"create", "copy", "set_system_group"}:
                    if process_id:
                        _fail("invalid_request", "새 절차의 식별자는 서버가 발급합니다.")
                    self._authorize_system(db, capabilities, group_ids, system_id)
                elif action == "import_legacy" and not process_id:
                    self._authorize_system(db, capabilities, group_ids, system_id or "UNASSIGNED")
                else:
                    row = self._authorize_process(db, capabilities, group_ids, process_id)
                    if system_id and system_id != row["owner_system"]:
                        _fail("workflow_manage_forbidden", "선택한 관리 시스템과 절차가 일치하지 않습니다.")
                    system_id = row["owner_system"]
                prior = db.execute("SELECT * FROM authoring_requests WHERE actor=? AND request_id=?", (actor, request_id)).fetchone()
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        _fail("request_conflict", "같은 요청 식별자를 다른 내용에 사용할 수 없습니다.")
                    if prior["process_id"]:
                        self._authorize_process(db, capabilities, group_ids, prior["process_id"])
                    result = self._authoring_state(db, capabilities, group_ids, assets, prior["system_id"], prior["process_id"], native)
                    result.update(result=json.loads(prior["outcome"]), request_id=request_id, replayed=True)
                    return result
                if row:
                    self._authoring_revision(body, row)
                before = row
                published = self._catalog(db)[0]
                outcome, id_map = {}, {}
                mapping_before = mapping_after = None
                if action == "set_system_group":
                    if system_id not in SYSTEMS:
                        _fail("workflow_manage_forbidden", "지원 시스템의 담당 그룹만 연결할 수 있습니다.")
                    group_id, active = payload.get("group_id", ""), payload.get("active", True)
                    if not isinstance(group_id, str) or len(group_id) > 200 or type(active) is not bool:
                        _fail("invalid_request", "담당 그룹과 활성 여부를 확인해 주세요.")
                    old = db.execute("SELECT * FROM system_groups WHERE system_id=?", (system_id,)).fetchone()
                    revision = old["revision"] if old else 0
                    mapping_before = dict(old) if old else {"system_id": system_id, "group_id": "", "active": 0, "revision": 0}
                    if type(body.get("expected_mapping_revision")) is not int or body["expected_mapping_revision"] != revision:
                        _fail("draft_revision_conflict", "담당 그룹 연결이 변경되었습니다. 최신 상태를 확인해 주세요.")
                    if group_id and group_id not in {group["id"] for group in native or []}:
                        _fail("group_not_found", "현재 존재하는 Native 그룹을 선택해 주세요.")
                    if group_id and db.execute("SELECT 1 FROM system_groups WHERE group_id=? AND system_id<>?", (group_id, system_id)).fetchone():
                        _fail("group_already_linked", "한 그룹은 한 시스템에만 연결할 수 있습니다.")
                    db.execute("INSERT INTO system_groups VALUES(?,?,?,?) ON CONFLICT(system_id) DO UPDATE SET group_id=excluded.group_id,active=excluded.active,revision=excluded.revision", (system_id, group_id, int(active and bool(group_id)), revision + 1))
                    mapping_after = {"system_id": system_id, "group_id": group_id, "active": int(active and bool(group_id)), "revision": revision + 1}
                    outcome = {"mapping_revision": revision + 1}
                elif action in {"create", "copy"}:
                    name = payload.get("name", "새 워크플로우")
                    category = payload.get("category", "setup")
                    if not isinstance(name, str) or not name.strip() or len(name) > 160 or category not in CATEGORIES:
                        _fail("invalid_definition", "절차 이름과 업무 분류를 확인해 주세요.")
                    if action == "copy":
                        source_id = payload.get("source_process_id")
                        if not isinstance(source_id, str):
                            _fail("invalid_request", "복사할 게시 절차를 선택해 주세요.")
                        source = self._published_workflow(db, published, source_id)
                        if not source:
                            _fail("process_not_found", "복사할 게시 절차를 찾지 못했습니다.")
                        process_id = self._fresh_id(db, "", "nodes")
                        id_map = {source_id: process_id}
                        for node_id in source["nodes"]:
                            if node_id != source_id:
                                id_map[node_id] = self._fresh_id(db, process_id, "nodes")
                        for kind in ("tools", "skills"):
                            for item_id in source[kind]:
                                id_map[item_id] = self._fresh_id(db, process_id, kind)
                        workflow = {"process_id": process_id, **{kind: {id_map[key]: dict(value, id=id_map[key]) for key, value in source[kind].items()} for kind in ("nodes", "tools", "skills")}}
                        for node in workflow["nodes"].values():
                            node["parent"] = id_map.get(node["parent"])
                            for field in ("children", "deps", "tools", "skills"):
                                node[field] = [id_map.get(key, key) for key in node[field]]
                            node["bindings"] = {id_map.get(key, key): value for key, value in node["bindings"].items()}
                            if system_id in SYSTEMS:
                                node["systems"] = [system_id]
                        for copied_node in workflow["nodes"].values():
                            remap_execution(copied_node, id_map)
                        workflow["nodes"][process_id]["name"] = name
                    else:
                        process_id = self._fresh_id(db, "", "nodes")
                        task_id, job_id = (self._fresh_id(db, process_id, "nodes") for _ in range(2))
                        p = self._blank_node(process_id, "p", name, category)
                        t = self._blank_node(task_id, "t", "새 단계", category, process_id)
                        j = self._blank_node(job_id, "j", "새 작업", category, task_id)
                        p["children"], t["children"] = [task_id], [job_id]
                        if system_id in SYSTEMS:
                            p["systems"] = [system_id]
                        workflow = {"process_id": process_id, "nodes": {node["id"]: node for node in (p, t, j)}, "tools": {}, "skills": {}}
                    db.execute("INSERT INTO process_management VALUES(?,?,0,?,1,'',NULL,NULL,?,?,0)", (process_id, system_id, _dump(workflow), actor, _now()))
                    outcome = {"created": True}
                elif action == "import_legacy":
                    snapshot_id, source_id = payload.get("snapshot_id"), payload.get("source_process_id")
                    if type(snapshot_id) is not int or not isinstance(source_id, str):
                        _fail("invalid_request", "가져올 보존본과 워크플로우를 선택해 주세요.")
                    snapshot = db.execute("SELECT * FROM authoring_legacy WHERE id=?", (snapshot_id,)).fetchone()
                    if not snapshot:
                        _fail("process_not_found", "보존된 이전 초안을 찾지 못했습니다.")
                    legacy = json.loads(snapshot["draft"])
                    imported = _subtree(legacy, source_id)
                    target = db.execute("SELECT * FROM process_management WHERE process_id=? AND deleted=0", (source_id,)).fetchone()
                    if target:
                        if not row or process_id != source_id:
                            _fail("workflow_baseline_changed", "기존 절차를 선택하고 현재 초안 revision을 확인한 뒤 가져와 주세요.")
                    else:
                        if row:
                            _fail("invalid_workflow_scope", "다른 절차로 이전 초안을 덮어쓸 수 없습니다.")
                        process_id, system_id = source_id, "UNASSIGNED"
                        if db.execute("SELECT 1 FROM authoring_ids WHERE id=?", (process_id,)).fetchone():
                            _fail("invalid_workflow_scope", "이미 사용된 식별자는 다시 가져올 수 없습니다.")
                        db.execute("INSERT INTO process_management VALUES(?,?,0,?,0,'',NULL,NULL,?,?,0)", (process_id, system_id, _dump(imported), actor, _now()))
                        row = db.execute("SELECT * FROM process_management WHERE process_id=?", (process_id,)).fetchone()
                    for node_id in imported["nodes"]:
                        reservation = db.execute("SELECT * FROM authoring_ids WHERE id=?", (node_id,)).fetchone()
                        if reservation and (reservation["process_id"] != process_id or reservation["retired"]):
                            _fail("invalid_workflow_scope", "이전 초안의 식별자가 다른 절차와 충돌합니다.")
                        db.execute("INSERT OR IGNORE INTO authoring_ids VALUES(?,?,?,0)", (node_id, process_id, "nodes"))
                    # Legacy shared definitions stay in the immutable snapshot;
                    # import never overwrites global policies/tools/skills/sites.
                    self._check_workflow_shape(db, row, imported, json.loads(row["draft"]), published, assets)
                    db.execute("UPDATE process_management SET draft=?,draft_revision=draft_revision+1,validation=NULL,updated_by=?,updated_at=? WHERE process_id=?", (_dump(imported), actor, _now(), process_id))
                    outcome = {"imported_snapshot_id": snapshot_id, "shared_definitions_preserved": True}
                elif action == "transfer_owner":
                    owner = payload.get("owner_system")
                    if owner not in (*SYSTEMS, "COMMON", "UNASSIGNED"):
                        _fail("invalid_request", "관리 시스템을 확인해 주세요.")
                    draft = json.loads(row["draft"])
                    existing = self._published_workflow(db, published, process_id)
                    if owner in SYSTEMS:
                        for value in (draft, existing):
                            if value and (value["nodes"][process_id].get("systems") != [owner] or any("systems" in node and node["systems"] != [owner] for node in value["nodes"].values())):
                                _fail("unsafe_owner_transfer", "게시본과 초안이 대상 시스템 전용이 아닙니다. 적용 범위를 유지하거나 새 절차로 복사해 주세요.")
                    db.execute("UPDATE process_management SET owner_system=?,owner_revision=owner_revision+1,validation=NULL,updated_by=?,updated_at=? WHERE process_id=?", (owner, actor, _now(), process_id))
                    system_id = owner
                elif action == "reconcile_publication":
                    expected = payload.get("expected_published_fingerprint")
                    if not isinstance(expected, str) or (expected and re.fullmatch(r"[0-9a-f]{64}", expected) is None):
                        _fail("invalid_request", "확인한 현재 게시본을 지정해 주세요.")
                    current_fingerprint = self._published_hash(db, published, process_id)
                    if expected != current_fingerprint:
                        _fail("workflow_baseline_changed", "확인하는 동안 게시본이 변경되었습니다. 다시 비교해 주세요.")
                    changed = current_fingerprint != row["base_fingerprint"]
                    if changed:
                        # Deliberately retain the exact saved draft TEXT, owner,
                        # and publication history, even if Restore removed the P.
                        db.execute("UPDATE process_management SET base_fingerprint=?,draft_revision=draft_revision+1,validation=NULL,updated_by=?,updated_at=? WHERE process_id=?",
                                   (current_fingerprint, actor, _now(), process_id))
                    outcome = {"reconciled": changed, "message": "저장한 초안을 유지하고 현재 게시본을 기준으로 채택했습니다. 다시 검사한 뒤 별도로 게시해 주세요." if changed else "현재 게시본 기준이 유지됩니다."}
                elif action in {"save_draft", "add_node"}:
                    incoming = payload.get("workflow")
                    if action == "add_node":
                        incoming = json.loads(row["draft"])
                        parent = incoming["nodes"].get(payload.get("parent_id"))
                        if not parent or parent["type"] == "j":
                            _fail("invalid_workflow_scope", "선택한 절차의 상위 단계를 확인해 주세요.")
                        temp_id = "new-" + uuid4().hex
                        incoming["nodes"][temp_id] = self._blank_node(temp_id, "t" if parent["type"] == "p" else "j", payload.get("name", "새 항목"), parent["category"], parent["id"])
                        parent["children"].append(temp_id)
                    workflow, id_map = self._prepare_workflow(db, row, incoming, published, assets)
                    db.execute("UPDATE process_management SET draft=?,draft_revision=draft_revision+1,validation=NULL,updated_by=?,updated_at=? WHERE process_id=?", (_dump(workflow), actor, _now(), process_id))
                elif action == "validate_draft":
                    workflow = json.loads(row["draft"])
                    self._validate_for_publication(db, row, workflow, published, assets)
                    validation = self._validation_token(db, row, workflow, published, assets)
                    db.execute("UPDATE process_management SET validation=? WHERE process_id=?", (_dump(validation), process_id))
                    outcome = {"valid": True, "message": "구조·참조·입력 연결을 확인했습니다. 실제 업무 실행 검증은 별도입니다."}
                elif action == "publish":
                    workflow = json.loads(row["draft"])
                    # Two independently identified duplicate publications of an
                    # unchanged saved draft must not issue another version.
                    if row["published_version"] is not None and self._published_hash(db, published, process_id) == _hash(workflow) == row["base_fingerprint"]:
                        self._validate_for_publication(db, row, workflow, published, assets)
                        outcome = {"version": row["published_version"], "already_published": True}
                    else:
                        validation = self._validation_token(db, row, workflow, published, assets)
                        if not row["validation"] or json.loads(row["validation"]) != validation:
                            _fail("validation_required", "저장한 최신 초안을 다시 확인한 뒤 게시해 주세요.")
                        merged = self._validate_for_publication(db, row, workflow, published, assets)
                        outcome = {"version": self._write_publication(db, row, merged, workflow, actor), "message": "게시했습니다. 새 진행 건부터 적용됩니다."}
                elif action == "disable":
                    existing = self._published_workflow(db, published, process_id)
                    if existing is None:
                        _fail("invalid_action", "미게시 절차는 명시적으로 삭제할 수 있습니다.")
                    if self._published_hash(db, published, process_id) != row["base_fingerprint"]:
                        _fail("workflow_baseline_changed", "게시본이 변경되었습니다. 최신 상태를 확인해 주세요.")
                    existing["nodes"][process_id]["enabled"] = False
                    draft = json.loads(row["draft"])
                    draft["nodes"][process_id]["enabled"] = False
                    merged = self._merge_workflow(db, published, existing)
                    errors = validate_definition(merged)
                    if errors:
                        _fail("invalid_definition", errors[0])
                    version = self._write_publication(db, row, merged, existing, actor)
                    # Unpublished edits remain unpublished when disabling.
                    db.execute("UPDATE process_management SET draft=?,draft_revision=draft_revision+1 WHERE process_id=?", (_dump(draft), process_id))
                    outcome = {"version": version, "disabled": True}
                elif action == "delete":
                    if row["published_version"] is not None or process_id in published["nodes"]:
                        _fail("published_process_requires_disable", "게시한 절차는 삭제 대신 사용 중지해 주세요.")
                    db.execute("UPDATE process_management SET deleted=1,validation=NULL WHERE process_id=?", (process_id,))
                    db.execute("UPDATE authoring_ids SET retired=1 WHERE process_id=?", (process_id,))
                    outcome = {"deleted": True}
                after = db.execute("SELECT * FROM process_management WHERE process_id=?", (process_id,)).fetchone() if process_id else None
                self._audit(db, actor, action, process_id, system_id, request_id, before, after, mapping_before=mapping_before, mapping_after=mapping_after)
                response_process = "" if action == "delete" else process_id
                db.execute("INSERT INTO authoring_requests VALUES(?,?,?,?,?,?)", (actor, request_id, fingerprint, response_process, system_id, _dump(outcome)))
                result = self._authoring_state(db, capabilities, group_ids, assets, system_id, response_process, native)
                result.update(result=outcome, id_map=id_map, request_id=request_id, replayed=False)
                return result
        except WorkflowError as error:
            if current is not None and audit_target:
                try:
                    with self._db(write=True) as db:
                        self._audit(db, _value(current, "id"), *audit_target[:3], audit_target[3], outcome=error.code)
                except sqlite3.Error:
                    pass
            return self._authoring_failure(error)
        except (sqlite3.Error, TypeError, ValueError, KeyError, RecursionError):
            return self._authoring_failure(WorkflowError("authoring_unavailable", "절차를 저장하지 못했습니다. 변경은 적용하지 않았습니다. 최신 상태를 확인해 주세요."))
