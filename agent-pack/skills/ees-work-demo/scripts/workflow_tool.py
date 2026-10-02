"""
title: EES Work
description: 허용된 업무 조회·절차 초안 제안·화면 안내. 저장·게시·실행·확정은 사용자 화면에서 수행합니다.
version: 1.0.0
required_open_webui_version: 0.11.3
"""

import asyncio
import json


def _error(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def _identifier(value, optional=True):
    return isinstance(value, str) and len(value) <= 200 and (optional or bool(value))


def _chat(metadata):
    value = metadata.get("chat_id") if isinstance(metadata, dict) else None
    return value if _identifier(value, optional=False) else None


def _reference(metadata):
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get("ees_work_reference")
    if value is None:
        message = metadata.get("user_message") or {}
        value = (message.get("meta") or {}).get("ees_work_reference") if isinstance(message, dict) else None
    if (not isinstance(value, dict) or value.get("kind") != "workspace"
            or not all(_identifier(value.get(key, "")) for key in ("workflow_id", "run_id", "job_id"))
            or not isinstance(value.get("context_id"), str) or not 0 < len(value["context_id"]) <= 4096
            or type(value.get("revision")) is not int or value["revision"] < 0):
        return {}
    return {key: value.get(key, "") for key in ("workflow_id", "run_id", "job_id", "revision", "context_id")}


async def _browser(event_call, chat_id, method, payload):
    if not callable(event_call) or not chat_id:
        return _error("browser_unavailable", "현재 대화의 업무 화면에서 제안을 확인해 주세요.")
    # Only reviewed fixed navigation/preview methods. No generated script,
    # auth token, intent, or command endpoint is accepted from a model.
    if method not in {"display", "propose"}:
        return _error("invalid_action", "지원하지 않는 화면 동작입니다.")
    code = ("const chatId=" + json.dumps(chat_id) + ";const payload=" + json.dumps(payload, ensure_ascii=True) + ";"
            "const api=window.__eesNativeWorkV1;return api?." + method +
            " ? await api." + method + "(chatId,payload) : {ok:false,code:'ui_unavailable'};")
    try:
        result = await asyncio.wait_for(event_call({"type": "execute", "data": {"code": code}}), timeout=8)
        return result if isinstance(result, dict) else _error("browser_unconfirmed", "화면 적용 여부를 확인하지 못했습니다.")
    except Exception:
        return _error("browser_unconfirmed", "화면 적용 여부를 확인하지 못했습니다. 저장된 것으로 간주하지 마세요.")


class Tools:
    async def ees_workflow_view(self, workflow_id: str = "", run_id: str = "", system_id: str = "",
                                factory_id: str = "", __user__=None, __metadata__=None) -> dict:
        """Read authorized procedures or one work run. Never starts, changes or completes work.

        :param workflow_id: Exact procedure identifier to read.
        :param run_id: Exact run identifier to read.
        :param system_id: Selected authorized system.
        :param factory_id: Selected authorized factory; empty means system scope, not ACL bypass.
        """
        if not all(_identifier(value) for value in (workflow_id, run_id, system_id, factory_id)):
            return _error("invalid_request", "조회 대상을 확인해 주세요.")
        try:
            from open_webui.ees_workflow import workspace_state
        except ImportError:
            return _error("program_upgrade_required", "EES Work 프로그램 업데이트가 필요합니다.")
        reference = _reference(__metadata__)
        if not any((workflow_id, run_id, system_id, factory_id)) and reference:
            workflow_id, run_id = reference["workflow_id"], reference["run_id"]
        result = await workspace_state(__user__, workflow_id, run_id, system_id, factory_id)
        if not result.get("ok"):
            return result
        # Personal UI state, approvals/intents, credentials and private chat
        # bodies do not belong in model context. The service filters scope and
        # result evidence access before this narrower projection.
        projection = {key: result[key] for key in ("ok", "workflows", "workflow", "run", "runs", "my_work", "capabilities") if key in result}
        selected = result.get("run") if run_id else result.get("workflow")
        if (reference and selected and reference["workflow_id"] == workflow_id
                and reference["run_id"] == run_id and reference["revision"] == selected.get("revision")):
            definition = selected.get("definition") or selected.get("draft") or {}
            if not reference["job_id"] or reference["job_id"] in definition.get("nodes", {}):
                projection["work_context"] = reference
        return projection

    async def ees_workflow_propose(self, workflow_id: str, base_revision: int, definition: dict = None,
                                   context_id: str = "", proposal_kind: str = "workflow", run_id: str = "", job_id: str = "", inputs: dict = None, __user__=None, __metadata__=None,
                                   __event_call__=None) -> dict:
        """Offer a local procedure or selected-job input draft for human review; never saves, publishes or executes.

        :param workflow_id: Exact existing procedure being edited.
        :param base_revision: Revision used when drafting the proposal.
        :param definition: Complete proposed editable definition object, not code/HTML/SQL.
        :param context_id: Editor context identifier returned by the current work surface.
        :param proposal_kind: workflow for a procedure definition, inputs for the current run/job input suggestion.
        :param run_id: Exact current run identifier for an inputs proposal.
        :param job_id: Exact selected job identifier for an inputs proposal.
        :param inputs: Proposed declared input values for local review only; never credentials.
        """
        if proposal_kind == "inputs":
            if (not _identifier(workflow_id, False) or not _identifier(run_id, False) or not _identifier(job_id, False)
                    or not isinstance(context_id, str) or not 0 < len(context_id) <= 4096 or type(base_revision) is not int or base_revision < 0
                    or not isinstance(inputs, dict)):
                return _error("invalid_proposal", "입력을 제안할 진행 건·작업·revision을 확인해 주세요.")
            try:
                from open_webui.ees_workflow import workspace_input_preview
            except ImportError:
                return _error("program_upgrade_required", "EES Work 프로그램 업데이트가 필요합니다.")
            preview = await workspace_input_preview(__user__, {"workflow_id": workflow_id, "run_id": run_id, "job_id": job_id,
                "expected_revision": base_revision, "context_id": context_id, "proposal": inputs})
            if not preview.get("ok"):
                return preview
            result = await _browser(__event_call__, _chat(__metadata__), "propose", preview)
            return {"ok": bool(result.get("ok")), "proposal": result, "proposal_kind": "inputs", "saved": False, "published": False, "executed": False,
                    "message": "입력 제안을 검토하고 개인 입력 초안에 반영한 뒤 별도로 저장해 주세요."}
        if proposal_kind != "workflow":
            return _error("invalid_proposal", "지원하지 않는 제안 종류입니다.")
        if (not _identifier(workflow_id, False) or not isinstance(context_id, str) or not 0 < len(context_id) <= 4096
                or type(base_revision) is not int or base_revision < 0 or not isinstance(definition, dict)):
            return _error("invalid_proposal", "제안 대상과 기준 revision을 확인해 주세요.")
        try:
            from open_webui.ees_workflow import workspace_state
            from open_webui.ees_workflow_workspace import definition_check, _public
            from open_webui.ees_workflow_authoring import WorkflowError
        except ImportError:
            return _error("program_upgrade_required", "EES Work 프로그램 업데이트가 필요합니다.")
        try:
            _public(definition)
            errors, _warnings = definition_check(definition, complete=False)
        except WorkflowError as error:
            return _error(error.code, error.message)
        if errors or definition.get("id") != workflow_id:
            return _error("invalid_proposal", "제안의 구조와 절차 식별자를 확인해 주세요.")
        state = await workspace_state(__user__, workflow_id=workflow_id)
        if not state.get("ok"):
            return state
        workflow = state.get("workflow") or {}
        if not workflow.get("can_manage"):
            return _error("workflow_manage_forbidden", "이 절차의 편집 권한을 확인해 주세요.")
        if workflow.get("revision") != base_revision:
            return _error("revision_conflict", "초안이 변경되었습니다. 최신 기준으로 다시 제안해 주세요.")
        result = await _browser(__event_call__, _chat(__metadata__), "propose", {
            "workflow_id": workflow_id, "base_revision": base_revision, "context_id": context_id,
            "definition": definition})
        return {"ok": bool(result.get("ok")), "proposal": result,
                "saved": False, "published": False,
                "message": "사용자가 편집 화면에서 제안을 검토하고 반영·저장해야 합니다."}

    async def ees_workflow_display(self, workflow_id: str = "", run_id: str = "", job_id: str = "",
                                   __user__=None, __metadata__=None, __event_call__=None) -> dict:
        """Navigate to an authorized procedure/run; never changes shared business state.

        :param workflow_id: Authorized procedure identifier.
        :param run_id: Authorized run identifier.
        :param job_id: Job identifier within that run.
        """
        if not all(_identifier(value) for value in (workflow_id, run_id, job_id)):
            return _error("invalid_request", "화면 대상을 확인해 주세요.")
        state = await self.ees_workflow_view(workflow_id, run_id, __user__=__user__, __metadata__=__metadata__)
        if not state.get("ok"):
            return state
        return await _browser(__event_call__, _chat(__metadata__), "display", {
            "workflow_id": workflow_id, "run_id": run_id, "job_id": job_id})
