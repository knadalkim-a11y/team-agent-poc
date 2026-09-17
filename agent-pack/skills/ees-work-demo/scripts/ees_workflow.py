"""Persistent workflow state shared by the native work panel and the AI Tool.

This module runs inside the existing Open WebUI process. It never executes
arbitrary code, SQL, a business API, or a model. Example checks are explicitly
labelled simulations; an external tool reference without an adapter is blocked.
The separate SQLite file holds workflow definitions, user-owned cases and
additive request receipts that prevent repeated writes after a lost response.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4


# Keep the existing module as the public facade for callers and Tools.
from .ees_workflow_definition import (
    CATEGORIES, SYSTEMS, INPUTS, IDENTIFIER, MAX_DOCUMENT_BYTES,
    _dump, _seed, _ancestors, _leaves, _dependencies,
    _draft_shape_errors, validate_definition,
)
from .ees_workflow_view import _applicable, _finished, _missing, _view, _workflow

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
            # Additive receipts: older programs keep reading catalog/cases and
            # ignore this table. No saved definition, case or user asset migrates.
            db.execute("CREATE TABLE IF NOT EXISTS action_requests (owner TEXT NOT NULL, request_id TEXT NOT NULL, "
                       "fingerprint TEXT NOT NULL, case_id TEXT NOT NULL, outcome TEXT NOT NULL, "
                       "PRIMARY KEY(owner,request_id))")
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

    def _state(self, db, user, case_id="", chat_id="", assets=None, process_id=""):
        published, draft, revision, validated = self._catalog(db)
        case = self._case(db, _value(user, "id"), case_id, chat_id)
        cases = []
        for row in db.execute("SELECT data FROM cases WHERE owner=? ORDER BY rowid DESC", (_value(user, "id"),)):
            item = _view(json.loads(row["data"]))
            summary = {key: item[key] for key in ("id", "chat_id", "site", "system", "process_id",
                                                 "process_name", "category", "selected_id", "revision", "version",
                                                 "status", "progress", "created_at", "updated_at", "node_states")}
            summary["tree_nodes"] = {
                node_id: {key: node[key] for key in ("id", "name", "type", "parent", "children", "description", "category") if key in node}
                for node_id, node in item["definition"]["nodes"].items()
            }
            cases.append(summary)
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
        result = {"ok": True, "catalog": published, "cases": cases, "case": case_view,
                  "can_manage": _value(user, "role") == "admin",
                  "draft": draft if _value(user, "role") == "admin" else None,
                  "draft_revision": revision if _value(user, "role") == "admin" else None,
                  "validated_revision": validated if _value(user, "role") == "admin" else None}
        if process_id:
            process = published["nodes"].get(process_id)
            if not process or process.get("type") != "p" or process.get("parent") is not None:
                raise WorkflowError("process_not_found", "게시된 업무 절차의 프로세스를 선택해 주세요.")
            result["workflow"] = _workflow(published, process_id, assets)
        elif case_id and case:
            result["workflow"] = _workflow(case["definition"], case["process_id"], assets,
                                           case_id=case["id"], snapshots=case.get("_skill_snapshots", {}))
        return result

    async def _visible_cases(self, user, state):
        """The navigation list respects the same linked-chat access as a read.

        Keep inaccessible saved executions intact; only omit their summaries.
        Run lookups after the workflow transaction, without holding a write lock.
        """
        accessible = []
        for case in state["cases"]:
            try:
                await self._chat(user, case["chat_id"])
            except WorkflowError as error:
                if error.code == "chat_forbidden":
                    continue
                raise
            accessible.append(case)
        state["cases"] = accessible
        return state

    @staticmethod
    def _selection(published, value):
        required = {"site_id", "system", "process_id", "node_id", "version"}
        if (not isinstance(value, dict) or set(value) != required
                or type(value.get("version")) is not int
                or any(not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 200
                       for key in required - {"version"})):
            raise WorkflowError("invalid_selection", "조회할 공장·시스템·업무와 게시 버전을 확인해 주세요.")
        if value["version"] != published["version"]:
            raise WorkflowError("published_version_conflict", "게시 절차가 변경되었습니다. 최신 절차를 확인한 뒤 진행해 주세요.")
        nodes = published["nodes"]
        node, process = nodes.get(value["node_id"]), nodes.get(value["process_id"])
        if (value["site_id"] not in published["sites"] or value["system"] not in SYSTEMS
                or not process or process["type"] != "p" or not node
                or _ancestors(nodes, node["id"])[0]["id"] != process["id"]):
            raise WorkflowError("invalid_selection", "선택한 공장·시스템·업무의 소속을 확인해 주세요.")
        context = {"definition": published, "site": published["sites"][value["site_id"]],
                   "system": value["system"]}
        return dict(value), _applicable(context, node["id"])

    async def get_state(self, user, chat_id="", case_id="", process_id="", selection=None):
        try:
            current = await self._user(user)
            if (not isinstance(case_id, str) or len(case_id) > 200
                    or not isinstance(process_id, str) or len(process_id) > 200
                    or (case_id and process_id) or (selection is not None and (case_id or process_id))):
                raise WorkflowError("invalid_request", "진행 건 식별 정보를 확인해 주세요.")
            await self._chat(current, chat_id)
            assets = await self._assets(current)
            with self._db() as db:
                if selection is not None:
                    published = self._catalog(db)[0]
                    selected, applicable = self._selection(published, selection)
                    # Browsing does not adopt the unrelated case bound to this
                    # chat, create one, or manufacture execution results.
                    state = self._state(db, current, assets=assets, process_id=selected["process_id"])
                    state.update(selection=selected, selection_applicable=applicable, read_only=True)
                else:
                    state = self._state(db, current, case_id, chat_id, assets, process_id)
            if state["case"]:
                await self._chat(current, state["case"]["chat_id"])
            return await self._visible_cases(current, state)
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
            case["created_at"] = case["updated_at"]
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

    @staticmethod
    def _receipt(db, owner, request_id):
        return db.execute("SELECT * FROM action_requests WHERE owner=? AND request_id=?",
                          (owner, request_id)).fetchone()

    def _first_write(self, db, current, body, assets):
        scope = body["scope"]
        if (not isinstance(scope, dict) or set(scope) != {"site_id", "system", "process_id", "version"}
                or not body.get("node_id")):
            raise WorkflowError("invalid_selection", "처음 반영할 공장·시스템·업무와 게시 버전을 확인해 주세요.")
        published = self._catalog(db)[0]
        selection, applicable = self._selection(published, {**scope, "node_id": body["node_id"]})
        if not applicable:
            raise WorkflowError("not_applicable", "현장 조건에 따라 제외된 작업입니다.")
        if type(body.get("expected_revision")) is not int or body["expected_revision"] not in (-1, 0):
            raise WorkflowError("revision_conflict", "최초 반영할 업무 상태를 다시 확인해 주세요.")
        existing = []
        for row in db.execute("SELECT data FROM cases WHERE owner=?", (_value(current, "id"),)):
            case = json.loads(row["data"])
            if (case["site"]["id"] == selection["site_id"] and case["system"] == selection["system"]
                    and case["process_id"] == selection["process_id"]):
                existing.append(case["id"])
        if existing:
            # Linked-chat access filtering happens before returning this state.
            # Do not disclose a count or description of inaccessible candidates.
            state = self._state(db, current, assets=assets)
            state["cases"] = [item for item in state["cases"] if item["id"] in existing]
            state.update(ok=False, error={"code": "case_selection_required",
                "message": "진행 대상을 확인해 주세요. 새 실행이 필요하면 명시적으로 요청해 주세요."})
            return state
        chat_id = body.get("chat_id", "")
        if self._case(db, _value(current, "id"), "", chat_id):
            raise WorkflowError("chat_already_bound", "이 대화에는 다른 업무가 연결되어 있습니다. 대상 대화를 확인해 주세요.")
        case = self._new_case(published, scope, chat_id, assets)
        case["selected_id"] = selection["node_id"]
        self._save_case(db, current, case, new=True)
        action_body = dict(body, case_id=case["id"], expected_revision=0)
        try:
            return self._dispatch(db, current, action_body, assets)
        except WorkflowError as error:
            # Preserve the exact created case for recovery, without presenting
            # a failed action as success or silently creating another case.
            state = self._state(db, current, case["id"], chat_id, assets)
            state.update(ok=False, error={"code": error.code, "message": error.message})
            return state

    async def _protected_action(self, current, body, assets):
        request_id, scope = body.get("request_id"), body.get("scope")
        if request_id is not None and (not isinstance(request_id, str)
                or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id) is None):
            raise WorkflowError("invalid_request_id", "업무 요청 식별자를 확인해 주세요.")
        if scope is not None and (body["action"] not in {"update_inputs", "run"}
                or body.get("case_id") or not request_id):
            raise WorkflowError("invalid_request", "최초 입력·실행에는 확정 대상과 요청 식별자가 필요합니다.")
        if body["action"] in {"save_draft", "validate_draft", "publish"} and _value(current, "role") != "admin":
            raise WorkflowError("admin_required", "업무 절차 관리는 관리자만 사용할 수 있습니다.")
        owner = _value(current, "id")
        identity = {key: body.get(key, default) for key, default in (
            ("action", ""), ("case_id", ""), ("chat_id", ""), ("node_id", ""),
            ("expected_revision", None), ("payload", {}), ("scope", None))}
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode("utf-8")).hexdigest()
        if request_id:
            with self._db() as db:
                prior = self._receipt(db, owner, request_id)
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise WorkflowError("request_conflict", "같은 요청 식별자가 다른 내용에 사용되었습니다. 원래 요청 결과를 확인해 주세요.")
                    saved = self._case(db, owner, prior["case_id"]) if prior["case_id"] else None
            if prior and saved:
                await self._chat(current, saved["chat_id"])
        with self._db(write=True) as db:
            receipt = self._receipt(db, owner, request_id) if request_id else None
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise WorkflowError("request_conflict", "같은 요청 식별자가 다른 내용에 사용되었습니다. 원래 요청 결과를 확인해 주세요.")
                # Never run again after a lost response. Return current allowed
                # state separately from the original action outcome/revision.
                state = self._state(db, current, case_id=receipt["case_id"], assets=assets)
                outcome = json.loads(receipt["outcome"])
                state.update({key: value for key, value in outcome.items() if key != "revision"})
                state.update(request_id=request_id, replayed=True, request_outcome_revision=outcome["revision"])
                return state
            state = self._first_write(db, current, body, assets) if scope is not None else self._dispatch(db, current, body, assets)
            if request_id and (state.get("case") or state.get("ok")):
                case = state.get("case")
                outcome = {key: state[key] for key in ("ok", "error", "result") if key in state}
                outcome["revision"] = case["revision"] if case else state.get("draft_revision")
                db.execute("INSERT INTO action_requests VALUES(?,?,?,?,?)",
                           (owner, request_id, fingerprint, case["id"] if case else "", _dump(outcome)))
                state.update(request_id=request_id, replayed=False, request_outcome_revision=outcome["revision"])
            return state

    def _dispatch(self, db, current, body, assets):
        """Existing actions run once inside the caller's workflow transaction."""
        action, payload = body["action"], body.get("payload", {})
        chat_id, case_id = body.get("chat_id", ""), body.get("case_id", "")
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
            if "version" in payload and (type(payload["version"]) is not int or payload["version"] != published["version"]):
                raise WorkflowError("published_version_conflict", "게시 절차가 변경되었습니다. 최신 절차를 확인한 뒤 진행해 주세요.")
            case = self._new_case(published, payload, chat_id, assets)
            self._save_case(db, current, case, new=True)
            case_id = case["id"]
        else:
            case = self._case(db, _value(current, "id"), case_id, chat_id)
            if not case:
                raise WorkflowError("case_required", "진행할 업무를 먼저 선택해 주세요.")
            case_id = case["id"]
            self._revision(body, case["revision"])
            if action in {"update_inputs", "run"} and _finished(case, case["process_id"]):
                raise WorkflowError("case_completed", "완료된 실행의 결과는 변경할 수 없습니다. 새 실행을 시작해 주세요.")
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
                    if "retry_failed" in payload and type(payload["retry_failed"]) is not bool:
                        raise WorkflowError("invalid_request", "실패한 잡의 재시도 범위를 확인해 주세요.")
                    pending = _leaves(case["definition"]["nodes"], node["id"])
                    executed = []
                    while pending:
                        ready = [job_id for job_id in pending if _applicable(case, job_id)
                                 and not _missing(case, job_id) and case["jobs"][job_id]["status"] != "passed"
                                 and (payload.get("retry_failed", True) or case["jobs"][job_id]["status"] != "failed")
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
            state = await self._protected_action(current, body, assets)
            if state.get("case"):
                await self._chat(current, state["case"]["chat_id"])
            return await self._visible_cases(current, state) if "cases" in state else state
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


async def get_state(user, chat_id="", case_id="", process_id="", selection=None):
    return await _production_service().get_state(user, chat_id, case_id, process_id, selection)


async def handle_action(user, body):
    return await _production_service().handle_action(user, body)


def install(app, verified_user):
    from fastapi import Body, Depends
    from fastapi.responses import JSONResponse

    def response(value):
        code = value.get("error", {}).get("code")
        status = 200 if value.get("ok") else 401 if code == "unauthorized" else 403 if code in {
            "chat_forbidden", "admin_required"} else 409 if code in {
                "revision_conflict", "chat_already_bound", "chat_mismatch", "published_version_conflict",
                "request_conflict", "case_selection_required", "case_completed"} else 400
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    @app.get("/api/ees-work/state", include_in_schema=False)
    async def state_route(chat_id: str = "", case_id: str = "", process_id: str = "", selection: str = "", user=Depends(verified_user)):
        try:
            parsed = json.loads(selection) if selection else None
        except (ValueError, RecursionError):
            return response({"ok": False, "error": {"code": "invalid_selection", "message": "조회할 업무 선택을 확인해 주세요."}})
        return response(await get_state(user, chat_id, case_id, process_id, parsed))

    @app.post("/api/ees-work/action", include_in_schema=False)
    async def action_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await handle_action(user, body))
