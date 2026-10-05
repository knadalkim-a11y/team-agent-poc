"""Persistent workflow state shared by the native work panel and the AI Tool.

This public facade preserves legacy records and delegates versioned Native
execution to the durable execution module. Arbitrary code/SQL is never accepted;
only approved Native function references are dispatched for the current user.
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
from .ees_workflow_view import _applicable, _finished, _missing, _inputs, _view, _workflow
from .ees_workflow_authoring import AuthoringMixin, WorkflowError
from .ees_workflow_execution import ExecutionRuntime, init_execution
from .ees_workflow_contract import validate_inputs
from .ees_workflow_workspace import WorkspaceMixin
from .ees_workflow_operations import OperationsRuntime

_service = None


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class WorkflowService(WorkspaceMixin, AuthoringMixin):
    """The injected lookups use the same current user and chat store as WebUI."""

    def __init__(self, database, user_lookup, chat_lookup, asset_lookup=None, group_lookup=None, group_list_lookup=None, *, native_bridge=None, model_executor=None):
        self.database = Path(database)
        self.user_lookup, self.chat_lookup = user_lookup, chat_lookup
        self.asset_lookup = asset_lookup
        self.group_lookup, self.group_list_lookup = group_lookup, group_list_lookup
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._db(write=True) as db:
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
            self._init_authoring(db, preserve_catalog=True)
            init_execution(db)
            self._init_workspace(db)
        self.execution = ExecutionRuntime(self, native_bridge, model_executor)
        self.operations = OperationsRuntime(self, bridge=native_bridge, model=model_executor)

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
            assets = await _resolve(self.asset_lookup(user))
            if "execution_capabilities" not in assets:
                try:
                    if self.asset_lookup is _registered_assets or self.execution.bridge is not None:
                        self.execution.configure()
                    if self.execution.bridge is not None and hasattr(self.execution.bridge, "capabilities"):
                        assets["execution_capabilities"] = await self.execution.bridge.capabilities(user)
                except Exception:
                    assets["execution_capabilities"] = []
                    assets["execution_metadata_available"] = False
            return assets
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
        assets = assets or {"tools": [], "skills": [], "available": True}
        cases = []
        for row in db.execute("SELECT data FROM cases WHERE owner=? ORDER BY rowid DESC", (_value(user, "id"),)):
            item = _view(json.loads(row["data"]), assets)
            summary = {key: item[key] for key in ("id", "chat_id", "site", "system", "process_id",
                                                 "process_name", "category", "selected_id", "revision", "version",
                                                 "status", "progress", "created_at", "updated_at", "node_states")}
            summary["tree_nodes"] = {
                node_id: {key: node[key] for key in ("id", "name", "type", "parent", "children", "description", "category") if key in node}
                for node_id, node in item["definition"]["nodes"].items()
            }
            cases.append(summary)
        for definition in (published, draft):
            definition["available_tools"] = assets["tools"]
            definition["available_skills"] = assets["skills"]
            definition["assets_available"] = assets.get("available", True)
        case_view = _view(case, assets)
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
                raise WorkflowError("process_not_found", "게시된 업무 절차의 워크플로우를 선택해 주세요.")
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
        if state.get("case"):
            await self.execution.redact_case(user, state["case"])
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
















    async def execution_state(self, user, case_id="", run_id="", chat_id=""):
        return await self.execution.state(user, case_id, run_id, chat_id)


def _production_service():
    global _service
    if _service is None:
        from open_webui.env import DATA_DIR
        from open_webui.models.chats import Chats
        from open_webui.models.users import Users
        from open_webui.models.groups import Groups

        _service = WorkflowService(Path(DATA_DIR) / "ees-work.sqlite3", Users.get_user_by_id,
                                   Chats.get_chat_by_id, _registered_assets,
                                   Groups.get_groups_by_member_id, lambda: Groups.get_groups({}))
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
        "tool_versions": {tool.id: _value(tool, "updated_at") for tool in registered_tools},
        "skills": [{"id": skill.id, "name": skill.name} for skill in registered_skills if skill.is_active],
        "skill_bodies": {skill.id: skill.content for skill in registered_skills if skill.is_active},
        "skill_versions": {skill.id: skill.updated_at for skill in registered_skills if skill.is_active},
        "available": True,
    }


async def get_state(user, chat_id="", case_id="", process_id="", selection=None):
    return await _production_service().get_state(user, chat_id, case_id, process_id, selection)


async def handle_action(user, body):
    return await _retired_for(user)


def _retired_action():
    return {"ok": False, "error": {"code": "legacy_execution_retired", "message":
        "이전 시연 절차는 실행이 중지되었습니다. 기록은 보존되며 새 업무 절차에서 진행해 주세요."}}


async def _retired_for(user):
    try:
        await _production_service()._user(user)
        return _retired_action()
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}


async def workspace_state(user, workflow_id="", run_id="", system_id="", factory_id=""):
    return await _production_service().workspace_state(user, workflow_id=workflow_id,
        run_id=run_id, system_id=system_id, factory_id=factory_id)


async def workspace_command(user, body):
    return await _production_service().workspace_command(user, body)


async def operations_state(user, system_id="", run_id=""):
    try:
        return await _production_service().operations.state(user, system_id=system_id, run_id=run_id)
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}


async def operations_command(user, body):
    try:
        return await _production_service().operations.command(user, body)
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}
    except sqlite3.Error:
        return {"ok": False, "error": {"code": "operations_unavailable", "message":
            "실행 기록을 확인하지 못했습니다. 결과를 다시 조회하고 미확인 변경 요청을 재전송하지 마세요."}}


async def _workspace_input_context(service, user, body):
    """Read a current, writable J context; never start an attempt or save input."""
    from .ees_workflow_workspace import _public, _revision, input_errors
    actor, _caps, groups = await service._work_actor(user)
    _public(body)
    if (not isinstance(body.get("context_id"), str) or not 0 < len(body["context_id"]) <= 4096
            or not isinstance(body.get("run_id"), str) or not isinstance(body.get("job_id"), str)):
        raise WorkflowError("invalid_proposal", "제안 대상과 현재 작업 위치를 확인해 주세요.")
    with service._db() as db:
        run = service._work_run(db, actor, groups, body["run_id"], write=True)
        _revision(body, run["revision"])
        if body.get("workflow_id", run["workflow_id"]) != run["workflow_id"]:
            raise WorkflowError("invalid_proposal", "진행 건의 절차를 확인해 주세요.")
        snapshot = service._work_snapshot(db, run, body["job_id"])
        node = snapshot["job"]
        job = db.execute("SELECT * FROM work_jobs WHERE run_id=? AND job_id=?", (run["id"], node["id"])).fetchone()
        actor_id = _value(actor, "id")
        if job is None or job["status"] == "excluded":
            raise WorkflowError("job_not_found", "입력을 제안할 현재 작업을 확인해 주세요.")
        if job["claim_actor"] and job["claim_actor"] != actor_id:
            raise WorkflowError("task_claimed", "현재 담당자의 입력 작업을 확인해 주세요.")
        assigned = node.get("assignee")
        if assigned and assigned.get("id") not in ({actor_id} if assigned.get("kind") == "user" else groups):
            raise WorkflowError("assignee_required", "배정된 담당자 또는 그룹만 입력 제안을 요청할 수 있습니다.")
        fields = [deepcopy(field) for field in node.get("inputs", []) if field.get("scope", "run") == "run"]
        registered_reference = None
        contract_id = node.get("tool_contract_id") or (node.get("tool_reference") or {}).get("contract_id")
        if contract_id:
            contract = service.operations._tool(db, contract_id)
            if contract["system_id"] != run["system_id"] or contract["state"] != "approved" or contract["revision"] != node.get("tool_contract_revision"):
                raise WorkflowError("tool_review_required", "현재 작업의 등록 도구 계약을 다시 확인해 주세요.")
            registered_reference = contract["reference"]
    if not fields:
        raise WorkflowError("proposal_fields_unavailable", "이번 진행 건에 제안할 입력 항목이 없습니다.")
    declared = {field["id"] for field in fields}
    draft = body.get("inputs", {key: val for key, val in snapshot["inputs"].items() if key in declared})
    if not isinstance(draft, dict) or input_errors(fields, draft, complete=False):
        raise WorkflowError("invalid_proposal_inputs", "선택 작업의 선언된 입력만 전달해 주세요.")
    await service._work_validate_people(draft)
    service.operations.configure()
    reference = deepcopy(snapshot.get("tool_reference") or registered_reference)
    if reference:
        reference.pop("contract_id", None)
        await service.operations._inspect_reference(actor, reference, "request" if node.get("result_block") == "change_request" else "read")
    available, unresolved, options = [], [], {}
    for field in fields:
        if field.get("options_source", "manual") == "manual":
            available.append(field)
            continue
        try:
            result = await service._work_input_options(actor, {"run_id": run["id"], "job_id": node["id"], "field_id": field["id"], "inputs": draft})
            options[field["id"]] = {**result, "source": {key: val for key, val in result.get("source", {}).items() if key != "queried_at"}}
            available.append({**field, "options_source": "manual", "options": result["options"]})
        except WorkflowError as error:
            if error.code not in {"options_dependency_required", "options_unconfigured", "options_unavailable"}:
                raise
            unresolved.append({"field_id": field["id"], "reason": error.code})
    if not available:
        raise WorkflowError("proposal_fields_unavailable", "현재 권한의 선택지를 먼저 조회하거나 선행 입력을 보완해 주세요.")
    actor, _caps, groups = await service._work_actor(actor)
    with service._db() as db:
        current = service._work_run(db, actor, groups, run["id"], write=True)
        _revision(body, current["revision"])
        if service._work_snapshot(db, current, node["id"]) != snapshot:
            raise WorkflowError("revision_conflict", "업무 설정이나 입력이 바뀌었습니다. 최신 상태로 다시 제안해 주세요.")
    return {"actor": actor, "workflow_id": run["workflow_id"], "run_id": run["id"], "job_id": node["id"], "revision": run["revision"],
            "context_id": body["context_id"], "fields": available, "declared_fields": fields, "unresolved_fields": unresolved,
            "source": {"job": {key: node.get(key) for key in ("id", "name", "instructions")}, "fields": available, "current_inputs": deepcopy(draft)},
            "snapshot_signature": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            "signature": json.dumps({"snapshot": snapshot, "fields": available, "options": options}, ensure_ascii=False, sort_keys=True)}


async def _workspace_check_input_suggestion(service, context, body, proposal):
    from .ees_workflow_workspace import _public, input_errors
    _public(proposal)
    if not isinstance(proposal, dict) or input_errors(context["declared_fields"], proposal, complete=False):
        raise WorkflowError("model_result_invalid", "선택 작업의 선언된 입력 형식과 현재 선택지를 확인하지 못했습니다.")
    # Parent and child values may be proposed together. Resolve choices using
    # the merged candidate, never the saved run or the model's old choices.
    candidate_body = {**body, "inputs": {**context["source"]["current_inputs"], **deepcopy(proposal)}}
    candidate = await _workspace_input_context(service, context["actor"], candidate_body)
    if candidate["snapshot_signature"] != context["snapshot_signature"]:
        raise WorkflowError("revision_conflict", "입력 근거가 변경되었습니다. 최신 상태로 다시 제안해 주세요.")
    if input_errors(candidate["fields"], proposal, complete=False):
        raise WorkflowError("model_result_invalid", "제안한 선행 입력에 맞는 현재 선택지를 확인하지 못했습니다.")
    await service._work_validate_people(proposal)
    current = await _workspace_input_context(service, candidate["actor"], candidate_body)
    if current["signature"] != candidate["signature"]:
        raise WorkflowError("revision_conflict", "입력 선택지가 변경되었습니다. 최신 상태로 다시 제안해 주세요.")
    await service._work_validate_people(proposal)
    return deepcopy(proposal)


def _workspace_input_preview_result(context, proposal):
    return {"ok": True, "proposal_kind": "inputs", "workflow_id": context["workflow_id"], "run_id": context["run_id"],
            "job_id": context["job_id"], "base_revision": context["revision"], "context_id": context["context_id"], "proposal": proposal,
            "inputs": deepcopy(proposal), "unresolved_fields": context["unresolved_fields"], "saved": False, "executed": False}


async def workspace_input_preview(user, body):
    """Validate a Native-chat suggestion for local review, with no mutation API."""
    try:
        service = _production_service()
        context = await _workspace_input_context(service, user, body)
        proposal = await _workspace_check_input_suggestion(service, context, body, body.get("proposal"))
        current = await _workspace_input_context(service, context["actor"], body)
        if current["signature"] != context["signature"]:
            raise WorkflowError("revision_conflict", "입력 근거가 변경되었습니다. 최신 상태로 다시 제안해 주세요.")
        return _workspace_input_preview_result(current, proposal)
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}


async def workspace_proposal(user, body):
    """Model output remains an unsaved suggestion, bound to current access/revision."""
    from .ees_workflow_workspace import definition_check, _public, _revision
    service = _production_service()
    try:
        actor, _capabilities, groups = await service._work_actor(user)
        if not isinstance(body, dict):
            raise WorkflowError("invalid_proposal", "제안할 편집 대상을 확인해 주세요.")
        if body.get("proposal_kind", "workflow") not in {"workflow", "inputs"}:
            raise WorkflowError("invalid_proposal", "지원하지 않는 제안 종류입니다.")
        if body.get("proposal_kind") == "inputs":
            context = await _workspace_input_context(service, actor, body)
            model = service.operations.model
            if model is None:
                raise WorkflowError("model_unavailable", "사용 가능한 Native 모델 연결을 설정해 주세요.")
            expected = {"context_id": context["context_id"], "target_id": context["job_id"], "revision": context["revision"], "kind": "inputs"}
            available_ids = {field["id"] for field in context["fields"]}
            # The adapter checks declaration shape. Resolved choices remain in
            # model evidence; the candidate gate checks changed dependencies.
            declared_fields = [field for field in context["declared_fields"] if field["id"] in available_ids]
            result = await model.propose(context["actor"], body.get("model_id", ""), {**expected, "fields": declared_fields, "source": context["source"]}, body.get("prompt"))
            if not isinstance(result, dict) or result.get("ok") is not True or result.get("context") != expected:
                raise WorkflowError("model_result_invalid", "입력 제안의 대상과 형식을 확인하지 못했습니다.")
            proposal = await _workspace_check_input_suggestion(service, context, body, result.get("proposal"))
            current = await _workspace_input_context(service, context["actor"], body)
            if context["signature"] != current["signature"]:
                raise WorkflowError("revision_conflict", "입력 근거가 변경되었습니다. 최신 상태로 다시 제안해 주세요.")
            return {**result, **_workspace_input_preview_result(current, proposal)}
        workflow_id = body.get("workflow_id")
        with service._db() as db:
            row = service._work_definition(db, actor, groups, workflow_id, manage=True)
            _revision(body, row["revision"])
            revision = row["revision"]
            source = deepcopy(body.get("definition", json.loads(row["draft"])))
        _public(source)
        errors, _warnings = definition_check(source, complete=False)
        if errors or source.get("id") != workflow_id:
            raise WorkflowError("invalid_proposal", "초안의 구조와 대상 식별자를 확인해 주세요.")
        model = service.operations.model
        if model is None:
            raise WorkflowError("model_unavailable", "사용 가능한 Native 모델 연결을 설정해 주세요.")
        result = await model.propose(actor, body.get("model_id", ""), {
            "context_id": body.get("context_id"), "target_id": workflow_id,
            "revision": revision, "kind": "workflow", "source": source}, body.get("prompt"))
        actor, _capabilities, groups = await service._work_actor(user)
        with service._db() as db:
            row = service._work_definition(db, actor, groups, workflow_id, manage=True)
            _revision(body, row["revision"])
        return {**result, "workflow_id": workflow_id, "base_revision": revision,
                "context_id": body["context_id"], "definition": result["proposal"], "saved": False}
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}




def _input_draft_receipt(target, receipt):
    """Accept only the small public receipt shape, never arbitrary message data."""
    if not isinstance(target, dict) or not isinstance(receipt, dict):
        return None
    cleaned_target = {key: value for key, value in target.items() if key != "draft_version"}
    if "draft_version" in target and (type(target["draft_version"]) is not int or target["draft_version"] < 0):
        return None
    kind = target.get("kind")
    if kind == "case":
        if (set(cleaned_target) != {"kind", "case_id", "node_id", "revision"}
                or type(target.get("revision")) is not int or target["revision"] < 0
                or any(not isinstance(target.get(key), str) or not target[key] or len(target[key]) > 200
                       for key in ("case_id", "node_id"))):
            return None
        node_id, case_id = target["node_id"], target["case_id"]
    elif kind == "published":
        selection = target.get("selection")
        if (set(cleaned_target) != {"kind", "selection"} or not isinstance(selection, dict)
                or set(selection) != {"site_id", "system", "process_id", "node_id", "version"}
                or type(selection.get("version")) is not int or selection["version"] < 1
                or any(not isinstance(selection.get(key), str) or not selection[key] or len(selection[key]) > 200
                       for key in ("site_id", "system", "process_id", "node_id"))):
            return None
        node_id, case_id = selection["node_id"], ""
    else:
        return None
    fields, source, proposal_id = receipt.get("fields"), receipt.get("source"), receipt.get("id")
    if (not isinstance(proposal_id, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", proposal_id) is None
            or receipt.get("status") not in {"applied", "undone"}
            or receipt.get("persisted") is not False or receipt.get("executed") is not False
            or not isinstance(source, str) or not source.strip() or len(source) > 500
            or not isinstance(fields, list) or not fields or len(fields) > 64
            or any(not isinstance(field, str) or not field or len(field) > 200 for field in fields)
            or receipt.get("node_id", node_id) != node_id or receipt.get("case_id", case_id) != case_id):
        return None
    return {"target": deepcopy(target), "action_record": {
        "id": proposal_id, "status": receipt["status"], "node_id": node_id, "case_id": case_id,
        "fields": list(dict.fromkeys(fields)), "source": source, "persisted": False, "executed": False}}


async def _input_draft_record_access(service, current, target):
    """Historical receipts keep their original revision; recheck current access."""
    with service._db() as db:
        if target["kind"] == "case":
            case = service._case(db, _value(current, "id"), target["case_id"])
            definition, node_id, process_id = case["definition"], target["node_id"], case["process_id"]
        else:
            definition = service._catalog(db)[0]
            selection = target["selection"]
            node_id, process_id = selection["node_id"], selection["process_id"]
            if selection["site_id"] not in definition["sites"] or selection["system"] not in SYSTEMS:
                raise WorkflowError("invalid_selection", "과거 입력의 현재 접근 범위를 확인하지 못했습니다.")
            case = None
        node = definition["nodes"].get(node_id)
        if not node or node.get("type") != "j" or _ancestors(definition["nodes"], node_id)[0]["id"] != process_id:
            raise WorkflowError("invalid_selection", "과거 입력의 현재 작업 접근을 확인하지 못했습니다.")
    if case:
        await service._chat(current, case.get("chat_id", ""))
    assets = await service._assets(current)
    if assets.get("available") is False:
        raise WorkflowError("assets_unavailable", "현재 자료 접근을 확인하지 못했습니다.")
    references = {skill.get("reference") for ancestor in _ancestors(definition["nodes"], node_id)
                  for key in ancestor.get("skills", [])
                  for skill in [definition.get("skills", {}).get(key, {})]
                  if skill.get("source") == "open_webui"}
    references.update(item.get("skill_id") for item in node.get("execution", {}).get("skill_refs", []))
    # This is historical chat evidence, not permission to execute a frozen plan.
    # Current access is required; a still-readable Skill edit does not erase history.
    bodies = assets.get("skill_bodies", {})
    if any(not isinstance(ref, str) or ref not in bodies for ref in references):
        raise WorkflowError("skill_unavailable", "현재 작업 자료 접근 권한을 확인하지 못했습니다.")


async def input_draft_records(user, chat_id):
    """Read actual Native message status history; this creates no receipt store."""
    try:
        from open_webui.models.chats import Chats
        service = _production_service()
        current = await service._user(user)
        if not isinstance(chat_id, str) or not chat_id or len(chat_id) > 200:
            raise WorkflowError("invalid_chat", "입력 기록을 조회할 대화를 확인해 주세요.")
        await service._chat(current, chat_id)
        chat = await Chats.get_chat_by_id(chat_id)
        if not chat or _value(chat, "user_id") != _value(current, "id"):
            raise WorkflowError("chat_forbidden", "본인의 대화 기록만 조회할 수 있습니다.")
        assets = await service._assets(current)
        if assets.get("available") is False:
            raise WorkflowError("assets_unavailable", "현재 자료 접근을 확인하지 못했습니다.")
        messages = _value(chat, "chat", {}).get("history", {}).get("messages", {})
        if not isinstance(messages, dict):
            raise WorkflowError("records_unavailable", "저장된 입력 기록을 확인하지 못했습니다.")
        records, permitted = [], {}
        for message_id, message in messages.items():
            if (not isinstance(message_id, str) or not message_id or len(message_id) > 200
                    or not isinstance(message, dict) or message.get("role") != "assistant"
                    or not isinstance(message.get("statusHistory", []), list)):
                continue
            seen = set()
            for status in reversed(message.get("statusHistory", [])):
                if not isinstance(status, dict):
                    continue
                receipt = status.get("ees_work_action")
                proposal_id = receipt.get("id") if isinstance(receipt, dict) else None
                if not isinstance(proposal_id, str) or proposal_id in seen:
                    continue
                seen.add(proposal_id)
                record = _input_draft_receipt(status.get("ees_work_target"), receipt)
                if not record:
                    continue
                identity = _dump({key: value for key, value in record["target"].items() if key != "draft_version"})
                if identity not in permitted:
                    try:
                        await _input_draft_record_access(service, current, record["target"])
                        permitted[identity] = True
                    except WorkflowError:
                        permitted[identity] = False
                if permitted[identity]:
                    records.append({"message_id": message_id, **record})
        return {"ok": True, "records": records}
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}
    except Exception:
        return {"ok": False, "error": {"code": "records_unavailable", "message": "저장된 입력 기록을 조회하지 못했습니다."}}






async def execution_plan(user, body):
    return await _retired_for(user)


async def execution_action(user, body):
    return await _retired_for(user)


async def execution_state(user, case_id="", run_id="", chat_id=""):
    return await _production_service().execution_state(user, case_id, run_id, chat_id)


async def legacy_state(user, case_id=""):
    """Read-only, owner/chat/source-authorized projection of pre-upgrade records."""
    service = _production_service()
    state = await service.get_state(user, case_id=case_id)
    if not state.get("ok"):
        return state
    try:
        await service._user(user)  # Rights may change while Native evidence is read.
    except WorkflowError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}
    from .ees_workflow_workspace import SECRET_KEYS
    def public(value):
        if isinstance(value, dict):
            return {key: public(child) for key, child in value.items()
                    if not key.startswith("_") and not SECRET_KEYS.search(key)}
        if isinstance(value, list):
            return [public(child) for child in value]
        return value
    fields = {"id", "site", "system", "process_id", "process_name", "category", "version",
              "revision", "status", "progress", "created_at", "updated_at", "node_states", "tree_nodes"}
    records = [{key: public(value) for key, value in item.items() if key in fields}
               for item in state.get("cases", [])]
    selected = state.get("case")
    record = None
    if selected:
        record = {key: public(value) for key, value in selected.items() if key in fields | {"jobs", "inputs"}}
        record["simulation"] = selected.get("context", {}).get("simulation")
    return {"ok": True, "read_only": True, "generation": "legacy", "records": records, "record": record,
            "notice": "이전 진행 기록입니다. 기존 실행은 중지되었으며 다시 실행할 수 없습니다. 합성 기록은 실제 업무 성공으로 전환하지 않습니다."}


def install(app, verified_user):
    from fastapi import Body, Depends
    from fastapi.responses import JSONResponse

    def response(value):
        code = value.get("error", {}).get("code")
        status = 200 if value.get("ok") else 401 if code == "unauthorized" else 403 if code in {
            "chat_forbidden", "admin_required", "workflow_manage_forbidden", "scope_forbidden", "run_forbidden",
            "approval_forbidden", "access_denied"} else 409 if code in {
                "revision_conflict", "chat_already_bound", "chat_mismatch", "published_version_conflict",
                "request_conflict", "case_selection_required", "case_completed", "authoring_upgrade_required",
                "execution_overlap", "execution_service_required", "result_confirmation_required", "run_completed",
                "draft_revision_conflict", "workflow_baseline_changed", "validation_required",
                "legacy_execution_retired", "intent_expired", "intent_changed", "already_claimed"} else 404 if code in {"process_not_found", "workflow_not_found", "run_not_found"} else 503 if code in {
                    "authoring_authorization_unavailable", "authoring_unavailable"} else 400
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    @app.get("/api/ees-work/workspace", include_in_schema=False)
    async def workspace_route(workflow_id: str = "", run_id: str = "", system_id: str = "",
                              factory_id: str = "", user=Depends(verified_user)):
        return response(await workspace_state(user, workflow_id, run_id, system_id, factory_id))

    @app.post("/api/ees-work/workspace", include_in_schema=False)
    @app.post("/api/ees-work/workspace/command", include_in_schema=False)
    async def workspace_command_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await workspace_command(user, body))

    @app.post("/api/ees-work/workspace/proposal", include_in_schema=False)
    async def workspace_proposal_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await workspace_proposal(user, body))

    @app.post("/api/ees-work/workspace/options", include_in_schema=False)
    async def workspace_options_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await _production_service().input_options(user, body))

    @app.get("/api/ees-work/resources", include_in_schema=False)
    async def resources_route(user=Depends(verified_user)):
        try:
            service = _production_service()
            actor = await service._user(user)
            assets = await service._assets(actor)
            return response({"ok": True, "available": assets.get("available", False), "skills": [
                {"id": skill["id"], "name": skill["name"], "revision": assets.get("skill_versions", {}).get(skill["id"])}
                for skill in assets.get("skills", [])]})
        except WorkflowError as error:
            return response({"ok": False, "error": {"code": error.code, "message": error.message}})

    @app.get("/api/ees-work/operations", include_in_schema=False)
    async def operations_route(system_id: str = "", run_id: str = "", user=Depends(verified_user)):
        return response(await operations_state(user, system_id, run_id))

    @app.get("/api/ees-work/legacy", include_in_schema=False)
    async def legacy_route(case_id: str = "", user=Depends(verified_user)):
        return response(await legacy_state(user, case_id))

    @app.get("/api/ees-work/export", include_in_schema=False)
    async def export_route(run_id: str = "", user=Depends(verified_user)):
        return response(await _production_service().workspace_export(user, run_id))

    @app.post("/api/ees-work/operations", include_in_schema=False)
    async def operations_command_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await operations_command(user, body))

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

    @app.post("/api/ees-work/input-draft/validate", include_in_schema=False)
    async def input_draft_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await _retired_for(user))

    @app.post("/api/ees-work/input-draft/undo-record", include_in_schema=False)
    async def input_draft_undo_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await _retired_for(user))

    @app.get("/api/ees-work/input-draft/records", include_in_schema=False)
    async def input_draft_records_route(chat_id: str = "", user=Depends(verified_user)):
        return response(await input_draft_records(user, chat_id))


    @app.get("/api/ees-work/authoring/capabilities", include_in_schema=False)
    async def authoring_capabilities_route(user=Depends(verified_user)):
        return response(await _production_service().authoring_capabilities(user))

    @app.get("/api/ees-work/authoring", include_in_schema=False)
    async def authoring_state_route(system_id: str = "", process_id: str = "", legacy_id: int | None = None, user=Depends(verified_user)):
        return response(await _production_service().get_authoring(user, system_id, process_id, legacy_id))

    @app.post("/api/ees-work/authoring/action", include_in_schema=False)
    async def authoring_action_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await _retired_for(user))

    @app.post("/api/ees-work/execution/plan", include_in_schema=False)
    async def execution_plan_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await execution_plan(user, body))

    @app.post("/api/ees-work/execution/action", include_in_schema=False)
    async def execution_action_route(body: dict = Body(...), user=Depends(verified_user)):
        return response(await execution_action(user, body))

    @app.get("/api/ees-work/execution/state", include_in_schema=False)
    async def execution_state_route(case_id: str = "", run_id: str = "", chat_id: str = "", user=Depends(verified_user)):
        return response(await execution_state(user, case_id, run_id, chat_id))

    @app.get("/api/ees-work/execution/capability", include_in_schema=False)
    async def execution_capability_route(tool_id: str = "", function: str = "", user=Depends(verified_user)):
        try:
            service = _production_service()
            current = await service._user(user)
            service.execution.configure(app)
            return response({"ok": True, "capability": await service.execution.bridge.inspect(current, tool_id, function)})
        except WorkflowError as error:
            return response({"ok": False, "error": {"code": error.code, "message": error.message}})

    @app.post("/api/ees-work/execution/capability/action", include_in_schema=False)
    async def execution_capability_action_route(body: dict = Body(...), user=Depends(verified_user)):
        try:
            service = _production_service()
            current = await service._user(user)
            service.execution.configure(app)
            approved = await service.execution.bridge.approval_action(current, body)
            return response({"ok": True, "capability": approved})
        except WorkflowError as error:
            return response({"ok": False, "error": {"code": error.code, "message": error.message}})

    # WebUI owns an async lifespan; startup event handlers alone are ignored by
    # FastAPI when a lifespan is supplied. Wrap and preserve the original one.
    from contextlib import asynccontextmanager
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def execution_lifespan(application):
        async with original_lifespan(application) as state:
            service = _production_service()
            service.execution.configure(application)
            service.operations.configure(application)
            service.operations.start()
            try:
                yield state
            finally:
                await service.operations.stop()

    app.router.lifespan_context = execution_lifespan
