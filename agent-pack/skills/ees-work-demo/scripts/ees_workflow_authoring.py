"""Read and preserve legacy authoring history and shared Native authorization.

New authoring lives in WorkspaceMixin. The retained legacy tables/read helpers
support inspection and migration; retired catalog writers are not executable.
Native users and groups remain authoritative, with no duplicate user roster,
secrets, code or private skill bodies stored here.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import json
import sqlite3

from .ees_workflow_definition import (
    SYSTEMS, _dump, _ancestors, _policy,
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
    def _init_authoring(self, db, preserve_catalog=False):
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
            if not preserve_catalog:
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
