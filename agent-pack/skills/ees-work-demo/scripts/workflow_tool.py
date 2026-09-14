"""
title: EES Workflow
description: 기존 대화와 업무 패널이 공유하는 공장별 업무 진행 및 절차 관리
version: 0.1.0
required_open_webui_version: 0.11.3
ees_demo_pack: ees-demo-v1
"""

import asyncio
import json


def _error(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def _chat(metadata):
    value = metadata.get("chat_id") if isinstance(metadata, dict) else None
    return value if isinstance(value, str) and 0 < len(value) <= 128 else None


async def _browser(event_call, chat_id, operation):
    if not callable(event_call):
        return {"ok": False, "code": "browser_unavailable"}
    # Fixed code plus JSON data: no generated JavaScript and no token copying.
    code = "const chatId = " + json.dumps(chat_id) + ";\n" + operation
    try:
        result = await asyncio.wait_for(event_call({"type": "execute", "data": {"code": code}}), timeout=8)
        return result if isinstance(result, dict) else {"ok": False, "code": "browser_unconfirmed"}
    except Exception:
        return {"ok": False, "code": "browser_unconfirmed"}


async def _ensure_chat(event_call, chat_id):
    return await _browser(event_call, chat_id,
        "return window.__eesNativeWorkV1?.ensureChat ? await window.__eesNativeWorkV1.ensureChat(chatId) : {ok:false,code:'ui_unavailable'};")


def _compact(state):
    """Return the active execution context, without every admin draft/case body."""
    if not state.get("ok"):
        return state
    case = state.get("case")
    result = {"ok": True, "can_manage": state.get("can_manage", False), "case": case,
              "simulation": True, "message": "DB/AP 점검은 모의 실행입니다. 실제 운영 시스템의 결과가 아닙니다."}
    if case:
        # Snapshot definitions contain the effective instructions, mappings and
        # field constraints. Keep those; never copy unrelated users/drafts.
        result["available_actions"] = ["select", "update_inputs", "run"]
    else:
        catalog = state.get("catalog", {})
        result["catalog"] = {key: catalog.get(key, []) for key in ("systems", "sites", "nodes")}
        result["available_actions"] = ["create"]
    if state.get("can_manage"):
        result["draft_revision"] = state.get("draft_revision")
        result["validated_revision"] = state.get("validated_revision")
    for key in ("validation", "message", "action", "result"):
        if key in state:
            result[key] = state[key]
    return result


class Tools:
    async def ees_workflow_view(self, include_draft: bool = False,
                                __user__=None, __metadata__=None, __event_call__=None) -> dict:
        """Read the current chat's latest selected process/task/job, factory, inputs,
        tools, effective instructions and execution results. Call this BEFORE
        answering a workflow question or modifying/running its job; manual panel
        edits may have changed it. General conversation/document search needs no
        workflow call. DB/AP results are simulations, never real connectivity.

        :param include_draft: Admin only: include the editable procedure draft and its revision when the user asks to edit procedures.
        """
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 업무를 선택해 주세요.")
        binding = await _ensure_chat(__event_call__, chat_id)
        try:
            from open_webui.ees_workflow import get_state
        except ImportError:
            return _error("program_upgrade_required", "업무 기능을 포함한 EES Portal 프로그램 업데이트가 필요합니다.")
        state = await get_state(__user__, chat_id=chat_id)
        if state.get("ok") and not state.get("case") and not binding.get("ok"):
            return _error("binding_unconfirmed", "선택한 업무와 대화 연결을 확인하지 못했습니다. 현재 화면에서 연결 상태를 확인해 주세요.")
        result = _compact(state)
        if include_draft and state.get("ok"):
            if not state.get("can_manage"):
                return _error("admin_required", "업무 절차 편집은 관리자 권한이 필요합니다.")
            result["draft"] = state.get("draft")
            result["catalog"] = state.get("catalog")
        return result

    async def ees_workflow_action(self, action: str, payload: dict = None,
                                  node_id: str = "", expected_revision: int = -1,
                                  __user__=None, __metadata__=None, __event_call__=None) -> dict:
        """Perform the same operation as a workflow UI button in this actual chat.
        Read ees_workflow_view first and use its case revision. Only do the action
        the user requested; viewing/selecting does not run tools. On conflicts
        reread; do not overwrite newer input or rerun blindly. Failed/blocked jobs
        remain failed/blocked. No live DB/AP, SQL, shell or publishing to business
        systems exists. Procedure publish is a separate explicit admin action.

        :param action: create, select, update_inputs, run, save_draft, validate_draft, or publish. Run uses node_id; process/task runs follow dependencies. UI and this tool share the same service.
        :param payload: Fields documented in view's current definition. create: site_id, system, process_id, optional title. update_inputs: inputs object. save_draft: definition object from include_draft view. run with tool mode: empty; manual completion: {confirm:true} ONLY when the user explicitly states they checked/completed it; draft save: {document:actual_draft_text}; draft completion: {confirm:true} ONLY after the user confirms review. Empty for selection/validation/publish. Never infer human confirmation from a request to automate the process.
        :param node_id: Exact process/task/job ID returned by view, or empty for the selected node. Never invent IDs.
        :param expected_revision: Current case revision, or draft_revision for admin draft actions. Use -1 only when creating a new case.
        """
        if not isinstance(action, str) or action not in {"create", "select", "update_inputs", "run", "save_draft", "validate_draft", "publish"}:
            return _error("unsupported_action", "지원되는 업무 동작을 선택해 주세요.")
        if payload is not None and not isinstance(payload, dict):
            return _error("invalid_payload", "업무 입력 형식을 확인해 주세요.")
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 업무를 시작해 주세요.")
        binding = await _ensure_chat(__event_call__, chat_id)
        try:
            from open_webui.ees_workflow import get_state, handle_action
        except ImportError:
            return _error("program_upgrade_required", "업무 기능을 포함한 EES Portal 프로그램 업데이트가 필요합니다.")
        state = await get_state(__user__, chat_id=chat_id)
        if not state.get("ok"):
            return state
        if not state.get("case") and not binding.get("ok"):
            return _error("binding_unconfirmed", "선택한 업무와 대화 연결을 확인하지 못했습니다. 현재 화면에서 연결 상태를 확인해 주세요.")
        case = state.get("case") or {}
        body = {"action": action, "chat_id": chat_id, "case_id": case.get("id", ""),
                "node_id": node_id or case.get("selected_id", ""), "payload": payload or {},
                "expected_revision": expected_revision}
        result = await handle_action(__user__, body)
        response = _compact(result)
        if result.get("ok"):
            panel = await _browser(__event_call__, chat_id,
                "window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:chatId,open_requested:true}})); return {ok:true,notified:true};")
            # A notification acknowledgement is not proof that the panel rendered.
            response["panel_notification"] = panel
        return response

    async def ees_workflow_display(self, options: dict, __user__=None,
                                   __metadata__=None, __event_call__=None) -> dict:
        """Adjust workflow navigation or the existing right panel when requested.
        This only changes presentation; it never runs a job or changes inputs.

        :param options: Any of panel_open, navigator_open, pinned as booleans; category as setup/ops/incident; system as EMS/APC/FDC/EGIS/EPT; workspace:true to open procedure editing (admin only). Use ees_workflow_action(select) for a particular process/task/job.
        """
        allowed = {"panel_open", "navigator_open", "pinned", "category", "system", "workspace"}
        if (not isinstance(options, dict) or not options or set(options) - allowed
                or any(type(value) is not bool for key, value in options.items() if key not in {"category", "system"})
                or ("category" in options and (not isinstance(options["category"], str) or options["category"] not in {"setup", "ops", "incident"}))
                or ("system" in options and (not isinstance(options["system"], str) or options["system"] not in {"EMS", "APC", "FDC", "EGIS", "EPT"}))):
            return _error("invalid_display", "표시할 업무 화면과 탐색 조건을 확인해 주세요.")
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 요청해 주세요.")
        try:
            from open_webui.ees_workflow import get_state
        except ImportError:
            return _error("program_upgrade_required", "EES Portal 프로그램 업데이트가 필요합니다.")
        state = await get_state(__user__, chat_id=chat_id)
        if not state.get("ok"):
            return state
        if options.get("workspace") and not state.get("can_manage"):
            return _error("admin_required", "업무 절차 편집은 관리자 권한이 필요합니다.")
        return await _browser(__event_call__, chat_id,
            "const options = " + json.dumps(options, ensure_ascii=True) + ";\n"
            "return window.__eesNativeWorkV1?.display ? await window.__eesNativeWorkV1.display(chatId,options) : {ok:false,code:'ui_unavailable'};")
