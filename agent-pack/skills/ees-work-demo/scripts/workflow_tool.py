"""
title: EES Workflow
description: 기존 대화와 업무 패널이 공유하는 공장별 업무 진행 및 절차 관리
version: 0.3.0
required_open_webui_version: 0.11.3
ees_demo_pack: ees-demo-v1
"""

import asyncio
import inspect
import json
import re


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


async def _selection(event_call, chat_id):
    """Read display context without creating, binding or selecting a case."""
    result = await _browser(event_call, chat_id,
        "return window.__eesNativeWorkV1?.selection ? await window.__eesNativeWorkV1.selection(chatId) : {ok:false,code:'ui_unavailable'};")
    if not result.get("ok"):
        if result.get("code") == "ui_unavailable":
            return _error("program_upgrade_required", "업무 선택 조회를 지원하는 EES Work 화면 업데이트가 필요합니다.")
        return _error("selection_unconfirmed", "현재 화면의 업무 대상을 확인하지 못했습니다. 업무를 다시 조회해 주세요.")
    target = {key: value for key, value in result.items() if key != "ok"}
    if not _valid_target(target, allow_none=True):
        return _error("selection_unconfirmed", "현재 화면의 업무 대상 정보가 올바르지 않습니다. 다시 조회해 주세요.")
    return {"ok": True, "target": target}


def _valid_target(target, allow_none=False):
    if not isinstance(target, dict):
        return False
    kind = target.get("kind")
    if kind == "none":
        return allow_none and set(target) == {"kind"}
    if kind == "published":
        selection = target.get("selection")
        return (set(target) == {"kind", "selection"} and isinstance(selection, dict)
                and set(selection) == {"site_id", "system", "process_id", "node_id", "version"}
                and all(isinstance(selection[key], str) and 0 < len(selection[key]) <= 200
                        for key in ("site_id", "system", "process_id", "node_id"))
                and type(selection["version"]) is int and selection["version"] > 0)
    return (kind in {"case", "history"} and set(target) == {"kind", "case_id", "node_id", "revision"}
            and all(isinstance(target[key], str) and 0 < len(target[key]) <= 200 for key in ("case_id", "node_id"))
            and type(target["revision"]) is int and target["revision"] >= 0)


def _supports(function, parameter):
    parameters = inspect.signature(function).parameters
    return parameter in parameters or any(item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values())


async def _selected_state(get_state, user, chat_id, target):
    if target["kind"] == "published":
        return await get_state(user, chat_id=chat_id, selection=target["selection"])
    if target["kind"] in {"case", "history"}:
        state = await get_state(user, case_id=target["case_id"])
        if state.get("ok"):
            definition = state.get("workflow", {}).get("definition") or (state.get("case") or {}).get("definition", {})
            node = definition.get("nodes", {}).get(target["node_id"])
            seen = set()
            while node and node.get("parent") and node.get("id") not in seen:
                seen.add(node["id"])
                node = definition["nodes"].get(node["parent"])
            if not node or node.get("id") != (state.get("case") or {}).get("process_id"):
                return _error("selection_changed", "선택한 단계가 해당 진행 건에 속하지 않습니다. 대상을 다시 조회해 주세요.")
        return state
    return _error("selection_required", "현재 선택한 업무가 없습니다. 업무 목록에서 대상을 확인해 주세요.")


def _same_selection(left, right):
    if left["kind"] != right["kind"]:
        return False
    if left["kind"] == "published":
        return left["selection"] == right["selection"]
    return left.get("case_id") == right.get("case_id") and left.get("node_id") == right.get("node_id")


def _scope_matches_case(target, case, node_id):
    selection = target["selection"]
    return (selection["site_id"] == case.get("site", {}).get("id")
            and selection["system"] == case.get("system")
            and selection["process_id"] == case.get("process_id")
            and selection["version"] == case.get("version")
            and selection["node_id"] == node_id)


async def _notify(event_call, chat_id, case, node_id):
    context = {"case_id": (case or {}).get("id", ""), "node_id": node_id, "open_requested": False}
    return await _browser(event_call, chat_id,
        "const resultContext = " + json.dumps(context, ensure_ascii=True) + ";\n"
        "window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:chatId,...resultContext}})); return {ok:true,notified:true};")


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
        completed = case.get("status") in {"passed", "completed", "success", "skipped"}
        result["available_actions"] = ["select"] if completed else ["select", "update_inputs", "run"]
        if completed:
            result["message"] += " 완료된 실행의 결과는 보존합니다. 다시 수행하려면 새 실행을 시작해 주세요."
    else:
        catalog = state.get("catalog", {})
        result["catalog"] = {key: catalog.get(key, []) for key in ("systems", "sites", "nodes")}
        result["available_actions"] = ["create"]
    if state.get("can_manage"):
        result["draft_revision"] = state.get("draft_revision")
        result["validated_revision"] = state.get("validated_revision")
    for key in ("validation", "message", "action", "result", "workflow", "selection", "selection_applicable", "read_only", "request_id", "replayed"):
        if key in state:
            result[key] = state[key]
    return result


class Tools:
    async def ees_workflow_view(self, include_draft: bool = False,
                                case_id: str = "", include_navigation: bool = False,
                                process_id: str = "",
                                __user__=None, __metadata__=None, __event_call__=None) -> dict:
        """Read the screen's latest selected process/task/job, factory, inputs,
        tools, effective instructions and execution results. Call this BEFORE
        answering a workflow question or modifying/running its job; manual panel
        edits may have changed it. General conversation/document search needs no
        workflow call. For a new work goal, discover candidates with
        include_navigation=True, then read process_id before creating anything.
        Discovery/details are read-only and need no sidebar selection. Ask only
        missing scope/inputs, explain the plan, then use the existing actions.
        Default reads obtain a read-only browser selection and verify it on the
        service. They NEVER create/bind/select a case. Published selections use
        the published workflow; case/history selections use the frozen case.
        Keep the returned target with any proposed input/document draft. Pass
        that exact target on a later explicit apply/run request; do not retarget
        a draft when the user moves to another job. DB/AP results are simulations.

        :param include_draft: Admin only: include the editable procedure draft and its revision when the user asks to edit procedures.
        :param case_id: Optional exact case ID from navigation for read-only execution history and its frozen workflow plan. Does not switch the current chat or selected job. Do not combine with process_id. Read the current view again before an action.
        :param include_navigation: Read-only published factory/system/process navigation and this user's accessible execution summaries. Does not create/bind work or change the sidebar; use to find a workflow for the user's goal.
        :param process_id: Exact published process ID from navigation. Return its workflow definition, ordered children/dependencies/conditions, inputs via tool.input and node.bindings, and accessible Skill instructions without creating/selecting/running work. Read source/version: an existing case must use its frozen case_id plan instead. Missing Skill bodies and non-executable tools cannot be treated as available. Read the current view again before an action.
        """
        if (not isinstance(case_id, str) or len(case_id) > 200
                or not isinstance(process_id, str) or len(process_id) > 200
                or (case_id and process_id)):
            return _error("invalid_request", "조회할 진행 건 또는 절차 정보를 확인해 주세요.")
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 업무를 선택해 주세요.")
        try:
            from open_webui.ees_workflow import get_state
        except ImportError:
            return _error("program_upgrade_required", "업무 기능을 포함한 EES Work 프로그램 업데이트가 필요합니다.")
        target = None
        if case_id:
            # Historical reads must not bind a pending case or move the live
            # conversation. The service checks case and linked-chat ownership.
            state = await get_state(__user__, case_id=case_id)
        elif process_id:
            if not _supports(get_state, "process_id"):
                return _error("program_upgrade_required", "업무 절차 상세 조회를 지원하는 EES Work 프로그램 업데이트가 필요합니다.")
            state = await get_state(__user__, chat_id=chat_id, process_id=process_id)
        elif include_navigation or include_draft:
            # Candidate discovery is independent of a pending sidebar choice.
            # Neither discovery nor procedure-admin reads bind that choice.
            state = await get_state(__user__, chat_id=chat_id)
        else:
            if not _supports(get_state, "selection"):
                return _error("program_upgrade_required", "업무 선택 조회를 지원하는 EES Work 프로그램 업데이트가 필요합니다.")
            selection = await _selection(__event_call__, chat_id)
            if not selection.get("ok"):
                return selection
            target = selection["target"]
            state = await _selected_state(get_state, __user__, chat_id, target)
        result = _compact(state)
        if target and state.get("ok"):
            if target["kind"] in {"case", "history"}:
                target = {**target, "revision": state["case"]["revision"]}
            result["target"] = target
            node_id = target["selection"]["node_id"] if target["kind"] == "published" else target["node_id"]
            definition = state.get("workflow", {}).get("definition") or (state.get("case") or {}).get("definition", {})
            result["selected_node"] = definition.get("nodes", {}).get(node_id)
            if target["kind"] == "published":
                result["available_actions"] = ["update_inputs", "run"] if state.get("selection_applicable", True) else []
                result["message"] += " 게시 절차 기준입니다. 질문·초안 제안만으로 진행 건을 만들거나 입력을 저장하지 않습니다."
            if target["kind"] == "history":
                result["read_only"] = True
                result["available_actions"] = []
        if (case_id or process_id or include_navigation) and state.get("ok"):
            result["read_only"] = True
            result["available_actions"] = []
        if include_navigation and state.get("ok"):
            catalog = state.get("catalog", {})
            result["navigation"] = {key: catalog.get(key, {}) for key in ("systems", "sites", "roots", "nodes")}
            result["cases"] = state.get("cases", [])
        if include_draft and state.get("ok"):
            if not state.get("can_manage"):
                return _error("admin_required", "업무 절차 편집은 관리자 권한이 필요합니다.")
            result["draft"] = state.get("draft")
            result["catalog"] = state.get("catalog")
        return result

    async def ees_workflow_action(self, action: str, payload: dict = None,
                                  node_id: str = "", expected_revision: int = -1,
                                  target: dict = None, request_id: str = "",
                                  __user__=None, __metadata__=None, __event_call__=None) -> dict:
        """Perform the explicitly requested workflow button operation.
        Read ees_workflow_view first. Keep its exact target with any proposed
        input/document draft; offering a draft NEVER saves it. Only apply after
        the user requests applying/saving. Reject a changed screen target rather
        than putting the old draft into the new job. A first published-workflow
        input/run request creates and connects its process case in the service.
        Reads never create or bind anything. Existing cases keep their revisions.
        Keep one request_id for the SAME write attempt, including retries after
        a lost response. A new explicit user operation needs a new request_id.
        After a conflict or unclear response, READ first; never blindly rerun.
        A failed panel notification does not mean the saved action failed.
        History and completed results cannot receive new inputs or execution.

        :param action: create, select, update_inputs, run, save_draft, validate_draft, or publish. UI and this tool share the same service. Parent runs only continue unfinished non-failed jobs; explicitly retry a failed individual job instead.
        :param payload: create: explicit site_id, system, process_id, optional title. update_inputs: inputs object with only requested fields. save_draft: full definition read with include_draft. run tool mode: empty. Manual completion: {confirm:true} ONLY after the user explicitly states they checked/completed the job. Draft save: {document:actual_draft_text} ONLY on an apply/save request; this stores a review draft, not a successful check. Draft completion: {confirm:true} ONLY after explicit review confirmation. Never infer confirmation, retry consent or publish approval from a broad automation request.
        :param node_id: Exact target process/task/job from the verified definition; empty uses target's node. Never invent IDs. Selection may point to another node in that same case.
        :param expected_revision: Copy target.revision for case actions, draft_revision for procedure admin actions. For a published first write or explicit create use -1. Preserve the original revision on same-request replay; reread on conflict.
        :param target: Exact target object returned by the latest view, retained with the proposed draft. Required for select/update_inputs/run. Published target includes site_id/system/process_id/node_id/version under selection. Case target includes kind/case_id/node_id/revision. A history target is never writable. Do not rebuild it from guesses or swap it to another screen target.
        :param request_id: Stable identifier for update_inputs/run, 1-128 ASCII letters, digits, dot, underscore, colon or hyphen. Use a new unique value for a new user-authorized operation, and reuse the EXACT value, original target/revision and payload if the same request must be resent. Do not use a new ID to bypass an unclear result or a conflict.
        """
        admin = action in {"save_draft", "validate_draft", "publish"} if isinstance(action, str) else False
        if not isinstance(action, str) or action not in {"create", "select", "update_inputs", "run", "save_draft", "validate_draft", "publish"}:
            return _error("unsupported_action", "지원되는 업무 동작을 선택해 주세요.")
        if payload is not None and not isinstance(payload, dict):
            return _error("invalid_payload", "업무 입력 형식을 확인해 주세요.")
        if not isinstance(node_id, str) or len(node_id) > 200 or type(expected_revision) is not int:
            return _error("invalid_request", "업무 대상과 기준 상태를 확인해 주세요.")
        if not isinstance(request_id, str) or (request_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id)):
            return _error("invalid_request_id", "같은 요청을 구분할 식별자를 확인해 주세요.")
        if not admin and action != "create" and not _valid_target(target):
            return _error("target_required", "업무를 먼저 조회하고 반환된 대상 정보를 그대로 사용해 주세요.")
        if action in {"update_inputs", "run"} and not request_id:
            return _error("request_id_required", "같은 저장·실행 요청의 재전송을 구분할 식별자가 필요합니다.")
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 업무를 시작해 주세요.")
        try:
            from open_webui.ees_workflow import get_state, handle_action
        except ImportError:
            return _error("program_upgrade_required", "업무 기능을 포함한 EES Work 프로그램 업데이트가 필요합니다.")
        payload = dict(payload or {})
        if admin:
            state = await get_state(__user__, chat_id=chat_id)
            body = {"action": action, "chat_id": chat_id, "case_id": "", "node_id": node_id,
                    "payload": payload, "expected_revision": expected_revision}
        else:
            if not _supports(get_state, "selection"):
                return _error("program_upgrade_required", "업무 선택·첫 저장을 지원하는 EES Work 프로그램 업데이트가 필요합니다.")
            selected = await _selection(__event_call__, chat_id)
            if not selected.get("ok"):
                return selected
            current = selected["target"]
            if current["kind"] == "history" or (target or {}).get("kind") == "history":
                return _error("history_read_only", "이전 실행은 읽기 전용입니다. 현재 업무를 선택한 뒤 다시 확인해 주세요.")
            if action == "create":
                keys = ("site_id", "system", "process_id")
                if any(not isinstance(payload.get(key), str) or not payload[key] for key in keys):
                    return _error("scope_required", "새 실행의 공장·시스템·프로세스를 명확히 지정해 주세요.")
                if current["kind"] == "case" or (current["kind"] == "published" and any(
                        payload[key] != current["selection"][key] for key in keys)):
                    return _error("selection_changed", "현재 화면과 새 실행 대상이 다릅니다. 대상을 다시 확인해 주세요.")
                state = await get_state(__user__, chat_id=chat_id)
                body = {"action": action, "chat_id": chat_id, "case_id": "", "node_id": node_id,
                        "payload": payload, "expected_revision": expected_revision}
            else:
                if current["kind"] == "none":
                    return _error("selection_required", "현재 선택한 업무가 없습니다. 대상을 다시 확인해 주세요.")
                replay_transition = target["kind"] == "published" and current["kind"] == "case"
                if not _same_selection(target, current) and not replay_transition:
                    return _error("selection_changed", "초안을 작성하거나 실행을 요청한 뒤 업무 대상이 바뀌었습니다. 원래 대상과 최신 상태를 다시 확인해 주세요.")
                state = await _selected_state(get_state, __user__, chat_id, current if replay_transition else target)
                if not state.get("ok"):
                    return state
                case = state.get("case") or {}
                if replay_transition and not _scope_matches_case(target, case, current["node_id"]):
                    return _error("selection_changed", "처음 요청한 범위와 현재 진행 건이 다릅니다. 기존 결과를 조회해 주세요.")
                target_node = target["selection"]["node_id"] if target["kind"] == "published" else target["node_id"]
                effective_node = node_id or target_node
                if action in {"update_inputs", "run"} and effective_node != target_node:
                    return _error("selection_changed", "입력·실행 대상이 조회한 업무와 다릅니다. 대상 업무를 다시 조회해 주세요.")
                body = {"action": action, "chat_id": chat_id, "case_id": case.get("id", ""),
                        "node_id": effective_node, "payload": payload, "expected_revision": expected_revision}
                if target["kind"] == "published":
                    if action not in {"update_inputs", "run"}:
                        return _error("case_required", "게시 절차의 선택은 화면에서 이동합니다. 입력 반영 또는 실행을 요청할 때 진행 건을 만듭니다.")
                    body["case_id"] = ""
                    body["scope"] = {key: target["selection"][key] for key in ("site_id", "system", "process_id", "version")}
                else:
                    if expected_revision != target["revision"]:
                        return _error("revision_conflict", "조회한 업무의 기준 상태와 요청이 다릅니다. 최신값과 초안을 비교해 주세요.")
                    if action in {"update_inputs", "run"} and case.get("status") in {"passed", "completed", "success", "skipped"}:
                        # Same-request replays on a newly completed case must be
                        # decided by the service receipt before mutation guards.
                        body["case_id"] = target["case_id"]
                definition = state.get("workflow", {}).get("definition") or case.get("definition", {})
                node = definition.get("nodes", {}).get(effective_node, {})
                if action == "run" and node.get("type") in {"p", "t"}:
                    if payload.get("retry_failed") is True:
                        return _error("retry_job_required", "실패한 잡의 결과를 확인하고 해당 잡에서 재시도를 요청해 주세요.")
                    payload["retry_failed"] = False
        if not state.get("ok"):
            return state
        if request_id:
            body["request_id"] = request_id
        result = await handle_action(__user__, body)
        response = _compact(result)
        if request_id:
            response["request_id"] = request_id
        if result.get("ok") or result.get("case"):
            response["panel_notification"] = await _notify(__event_call__, chat_id, result.get("case"), body["node_id"])
            response["result_target"] = {"case_id": (result.get("case") or {}).get("id", ""), "node_id": body["node_id"]}
            # A notification acknowledgement is not proof that the panel rendered.
            # A failed notification never triggers another service action.
        return response

    async def ees_workflow_display(self, options: dict, __user__=None,
                                   __metadata__=None, __event_call__=None) -> dict:
        """Adjust workflow navigation or the existing right panel when requested.
        This only changes presentation; it never runs a job or changes inputs.

        :param options: Any of panel_open, navigator_open, pinned, history_open as booleans; category as setup/ops/incident; system as EMS/APC/FDC/EGIS/EPT; site_id and process_id from navigation to browse work; node_id to open a verified process/task/job in the published or current scope without creating a case; case_id to resume an accessible execution in its own conversation; history_case_id to inspect a past execution read-only without changing the current conversation; workspace:true to open procedure editing (admin only). Do not combine case_id and history_case_id or node_id with history navigation. After display, read the current view again before applying a draft or running anything.
        """
        identifiers = {"site_id", "process_id", "node_id", "case_id", "history_case_id"}
        allowed = {"panel_open", "navigator_open", "pinned", "category", "system", "workspace", "history_open", *identifiers}
        if (not isinstance(options, dict) or not options or set(options) - allowed
                or any(type(value) is not bool for key, value in options.items() if key not in {"category", "system", *identifiers})
                or any(not isinstance(options[key], str) or not 0 < len(options[key]) <= 200 for key in identifiers if key in options)
                or ("case_id" in options and "history_case_id" in options)
                or ("node_id" in options and ("history_case_id" in options or options.get("history_open") is True))
                or ("category" in options and (not isinstance(options["category"], str) or options["category"] not in {"setup", "ops", "incident"}))
                or ("system" in options and (not isinstance(options["system"], str) or options["system"] not in {"EMS", "APC", "FDC", "EGIS", "EPT"}))):
            return _error("invalid_display", "표시할 업무 화면과 탐색 조건을 확인해 주세요.")
        chat_id = _chat(__metadata__)
        if not chat_id:
            return _error("chat_required", "기존 대화창에서 요청해 주세요.")
        try:
            from open_webui.ees_workflow import get_state
        except ImportError:
            return _error("program_upgrade_required", "EES Work 프로그램 업데이트가 필요합니다.")
        state = await get_state(__user__, chat_id=chat_id)
        if not state.get("ok"):
            return state
        if options.get("workspace") and not state.get("can_manage"):
            return _error("admin_required", "업무 절차 편집은 관리자 권한이 필요합니다.")
        catalog = state.get("catalog", {})
        if (("site_id" in options and options["site_id"] not in catalog.get("sites", {}))
                or ("process_id" in options and catalog.get("nodes", {}).get(options["process_id"], {}).get("type") != "p")):
            return _error("invalid_display", "등록된 공장과 프로세스를 선택해 주세요.")
        execution = None
        for key in ("case_id", "history_case_id"):
            if key in options:
                execution = await get_state(__user__, case_id=options[key])
                if not execution.get("ok"):
                    return execution
        if "node_id" in options:
            definitions = [catalog, (state.get("case") or {}).get("definition", {})]
            if execution:
                definitions = [(execution.get("case") or {}).get("definition", {})]
            matched = False
            for definition in definitions:
                node = definition.get("nodes", {}).get(options["node_id"])
                if node and "process_id" not in options:
                    matched = True
                    break
                seen = set()
                while node and node.get("parent") and node.get("id") not in seen:
                    seen.add(node.get("id"))
                    node = definition["nodes"].get(node["parent"])
                if node and node.get("id") == options.get("process_id"):
                    matched = True
                    break
            if not matched:
                return _error("invalid_display", "조회한 업무 범위에 속한 단계를 선택해 주세요.")
        return await _browser(__event_call__, chat_id,
            "const options = " + json.dumps(options, ensure_ascii=True) + ";\n"
            "return window.__eesNativeWorkV1?.display ? await window.__eesNativeWorkV1.display(chatId,options) : {ok:false,code:'ui_unavailable'};")
