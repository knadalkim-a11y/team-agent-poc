"""
title: EES Specialists
description: Consult EMS, APC and FDC demo Assistants with the current user's access.
version: 0.2.2
required_open_webui_version: 0.11.3
ees_demo_pack: ees-demo-v1
"""

import asyncio
import copy
import json
import re
from importlib.metadata import version
from types import SimpleNamespace
from uuid import uuid4

from pydantic import BaseModel, Field


SPECIALISTS = {
    "EMS": {"model_id": "ees_demo_ems", "capability": "합성 정비·부품 교체·작업 이력과 생산 재개 시각 분석"},
    "APC": {"model_id": "ees_demo_apc", "capability": "합성 레시피·설정·보정 이력과 조건별 차이 분석"},
    "FDC": {"model_id": "ees_demo_fdc", "capability": "합성 설비 신호·변동·시간별 변화와 비교 구간 분석"},
}
DATA_TOOL_ID = "ees_demo_data"
MAX_CONSULTATIONS = 4
MAX_DATA_CALLS = 3
MAX_QUESTION_CHARS = 5000
MAX_ANALYSIS_CHARS = 16000
SUPPORTED_WEBUI_VERSIONS = {"0.11.3", "0.11.3+ees.1", "0.11.3+ees.2", "0.11.3+ees.3", "0.11.3+ees.4", "0.11.3+ees.5", "0.11.3+ees.6"}
PANEL_SCRIPT = ""  # ApplyDemo embeds the reviewed, fixed cooperation panel script.
PANEL_SEND_TIMEOUT = 0.25


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _failure(code, message):
    return {"ok": False, "demo": True, "error": {"code": code, "message": message}}


TERMINAL_STEPS = {"completed", "partial", "failed", "cancelled"}


def _identity(user, metadata):
    return (user.get("id"), metadata.get("model_id"), metadata.get("chat_id"), metadata.get("message_id"))


def _active_plan(request, user, metadata):
    plan = getattr(request.state, "ees_analysis_plan", None)
    if not isinstance(plan, dict) or plan.get("identity") != _identity(user, metadata):
        return None
    return plan


async def _plan_panel(emitter, plan):
    state = plan["snapshot"]
    state["seq"] += 1
    if not PANEL_SCRIPT or not emitter or not state["chat_id"] or not state["message_id"]:
        return
    try:
        code = "const eesPanelUpdate=" + json.dumps(state, ensure_ascii=True) + ";\n" + PANEL_SCRIPT
        async with asyncio.timeout(PANEL_SEND_TIMEOUT):
            await emitter({"type": "execute", "data": {"code": code}})
    except Exception:
        pass


def _validate_steps(values, existing=()):
    if not isinstance(values, list) or not values or len(values) + len(existing) > 8:
        return None
    known = {step["id"] for step in existing}
    steps = []
    for value in values:
        if (not isinstance(value, dict) or set(value) != {
                "id", "type", "title", "system", "reason_before", "depends_on"}
                or not isinstance(value["id"], str)
                or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,39}", value["id"])
                or value["id"] in known
                or value["type"] not in ("specialist", "comparison", "synthesis")
                or any(not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > limit
                       for key, limit in (("title", 100), ("reason_before", 600)))
                or not isinstance(value["system"], str)
                or value["system"] not in (SPECIALISTS if value["type"] == "specialist" else {"EES"})
                or not isinstance(value["depends_on"], list)
                or any(not isinstance(dep, str) or dep not in known for dep in value["depends_on"])
                or len(set(value["depends_on"])) != len(value["depends_on"])):
            return None
        step = copy.deepcopy(value)
        step.update({"status": "pending", "result_summary": "", "judgment_after": "",
                     "uncertainty": "", "call_ids": []})
        steps.append(step)
        known.add(step["id"])
    return steps


def _within_plan_budget(steps):
    specialists = [step["system"] for step in steps if step["type"] == "specialist"]
    return (len(specialists) <= MAX_CONSULTATIONS and len(specialists) - len(set(specialists)) <= 1
            and sum(step["type"] == "comparison" for step in steps) <= 3)


def _step_ready(plan, step_id, kind, system=None):
    state = plan["snapshot"]
    step = next((item for item in state["steps"] if item["id"] == step_id), None)
    by_id = {item["id"]: item for item in state["steps"]}
    if (state["phase"] in {"completed", "partial"} or not step or step["type"] != kind
            or step["status"] != "pending" or (system and step["system"] != system)
            or any(by_id[dep]["status"] not in TERMINAL_STEPS for dep in step["depends_on"])):
        return None
    return step


def _step_phase(plan, step, phase, call_id):
    if plan["snapshot"]["phase"] in {"completed", "partial"}:
        return
    step["status"] = phase if phase in TERMINAL_STEPS else "running"
    if call_id not in step["call_ids"]:
        step["call_ids"].append(call_id)
    state = plan["snapshot"]
    state["phase"] = ("awaiting_summary" if all(
        item["status"] in TERMINAL_STEPS for item in state["steps"] if item["type"] != "synthesis") else "running")


def _load_runtime():
    """Import only when invoked; registering this Tool never imports the WebUI DB."""
    if version("open-webui") not in SUPPORTED_WEBUI_VERSIONS:
        raise RuntimeError("unsupported_webui_version")
    from starlette.requests import Request
    from starlette.responses import StreamingResponse
    from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
    from open_webui.env import BYPASS_MODEL_ACCESS_CONTROL
    from open_webui.models.config import Config
    from open_webui.models.models import Models
    from open_webui.models.users import Users
    from open_webui.utils.chat import generate_chat_completion
    from open_webui.utils.middleware import process_chat_payload, process_chat_response
    from open_webui.utils.misc import merge_model_params
    from open_webui.utils.models import check_model_access

    return SimpleNamespace(
        Request=Request, StreamingResponse=StreamingResponse, Config=Config,
        Models=Models, Users=Users, generate=generate_chat_completion,
        process_payload=process_chat_payload, process_response=process_chat_response,
        merge_params=merge_model_params, check_access=check_model_access,
        bypass_admin=BYPASS_ADMIN_ACCESS_CONTROL, bypass_models=BYPASS_MODEL_ACCESS_CONTROL,
    )


def _child_request(source, runtime):
    # Separate scope/state: never overwrite the parent chat, metadata, tools or token.
    scope = dict(source.scope)
    scope.update({"type": "http", "method": "POST", "path": "/api/chat/completions",
                  "raw_path": b"/api/chat/completions", "query_string": b"", "state": {}})
    child = runtime.Request(scope)
    for name in ("token", "enable_api_keys"):
        if hasattr(source.state, name):
            setattr(child.state, name, getattr(source.state, name))
    child.state.internal = True
    child.state.ees_specialist = True
    # One iteration may contain several calls. The callable wrapper below enforces
    # the exact execution budget separately from this upstream loop ceiling.
    child.state.max_tool_call_iterations = MAX_DATA_CALLS
    return child


async def _model(runtime, request, user, model_id):
    model_info = await runtime.Models.get_model_by_id(model_id)
    cached = request.app.state.MODELS.get(model_id)
    if not model_info or not cached:
        raise RuntimeError("model_unavailable")
    if not runtime.bypass_models and (user.role != "admin" or not runtime.bypass_admin):
        await runtime.check_access(user, cached, model_info=model_info)
    # Use the current row's Prompt/meta with the provider's cached routing fields.
    model = copy.deepcopy(cached)
    model["info"] = model_info.model_dump()
    return model, model_info


async def _status(emitter, system, phase, description, done=False):
    if emitter:
        try:
            # Direct await preserves parent cancellation when an emitter finishes
            # in the same loop turn (Python 3.11 wait_for can lose that race).
            async with asyncio.timeout(3):
                await emitter({"type": "status", "data": {
                    "action": "ees_specialist", "system": system, "phase": phase,
                    "description": description, "done": done,
                }})
        except Exception:
            # An unavailable UI must not turn a successful analysis into a failure.
            pass


async def _panel(emitter, record, phase, error=None):
    """Send a read-only snapshot; a missing browser never blocks analysis."""
    state = record["panel"]
    state["seq"] += 1
    state["phase"] = phase
    plan = record["plan"]
    step = record["step"]
    _step_phase(plan, step, phase, state["call_id"])
    code = None
    if PANEL_SCRIPT and emitter and state["chat_id"] and state["message_id"]:
        try:
            # Freeze before ANY await, including the plan event: another query
            # can change this same record while either UI emission is waiting.
            # Never include child metadata, raw records or reasoning.
            snapshot = {**state, "request": record["request"], "queries": record["queries"],
                        "analysis": record["analysis"],
                        "analysis_truncated": record["analysis_truncated"], "error": error}
            code = "const eesPanelUpdate=" + json.dumps(snapshot, ensure_ascii=True) + ";\n" + PANEL_SCRIPT
        except Exception:
            pass
    await _plan_panel(emitter, plan)
    if code is None:
        return
    try:
        async with asyncio.timeout(PANEL_SEND_TIMEOUT):
            await emitter({"type": "execute", "data": {"code": code}})
    except Exception:
        # CancelledError is deliberately not swallowed (it is a BaseException).
        pass


def _panel_arguments(kwargs):
    # Only known public filter strings belong in the browser, even when a tool
    # spec or rebinder accidentally includes a reserved or nested argument.
    return {key: value for key, value in kwargs.items()
            if key in {"dataset", "group_by", "equipment_id", "recipe_id", "event_id", "event_ids"}
            and isinstance(value, str) and len(value) <= (1000 if key == "event_ids" else 80)}


def _query_summary(query, result):
    query["status"] = "failed" if isinstance(result, dict) and result.get("ok") is False else "completed"
    if not isinstance(result, dict):
        return
    count = result.get("record_count")
    if type(count) is int and 0 <= count <= 1000:
        query["record_count"] = count
    records = result.get("records")
    if isinstance(records, list):
        query["event_ids"] = [row["event_id"] for row in records[:30]
                              if isinstance(row, dict) and isinstance(row.get("event_id"), str)
                              and len(row["event_id"]) <= 80]


def _visible_text(output):
    # Deliberately exclude reasoning blocks and tool call arguments from analysis.
    return "\n".join(
        part.get("text", "")
        for item in output if isinstance(item, dict) and item.get("type") == "message"
        for part in (item.get("content") or [])
        if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str)
    )


def _record_analysis(record, text):
    # A final outlet response can replace a streamed partial. The flag describes
    # the returned text, not whether an earlier partial happened to be longer.
    record["analysis"] = text[-MAX_ANALYSIS_CHARS:]
    record["analysis_truncated"] = len(text) > MAX_ANALYSIS_CHARS


def _result(system, record, error=None):
    analysis = record.get("analysis", "")
    evidence = record["evidence"]
    code = error or record.get("error")
    if not code and not analysis.strip():
        code = "empty_response"
    if not code and not evidence:
        code = "data_not_queried"
    return {
        "system": system, "model_id": SPECIALISTS[system]["model_id"], "demo": True,
        "status": "partial" if code and (analysis or evidence) else "failed" if code else "completed",
        "request": record["request"], "analysis": analysis,
        "analysis_truncated": record["analysis_truncated"],
        "evidence": evidence, "data_calls": record["data_calls"],
        "step_id": record["step"]["id"], "call_id": record["panel"]["call_id"],
        "error": code,
    }


async def _run_specialist(runtime, source, user, system, question, record, emitter):
    model_id = SPECIALISTS[system]["model_id"]
    model, info = await _model(runtime, source, user, model_id)
    if DATA_TOOL_ID not in (model["info"].get("meta") or {}).get("toolIds", []):
        raise RuntimeError("data_tool_not_connected")
    child = _child_request(source, runtime)
    params = runtime.merge_params(
        copy.deepcopy(await runtime.Config.get("models.default_params", {}) or {}),
        info.params.model_dump() if info.params else {},
    )
    # The registered demo models use native calling; never silently fall back to
    # the legacy task-model selector (which would make the budget unpredictable).
    params["function_calling"] = "native"
    params["stream_response"] = True
    child_id = str(uuid4())
    metadata = {
        "user_id": user.id, "model_id": model_id, "model": model,
        "chat_id": "", "message_id": child_id, "session_id": None,
        "internal": True, "tool_ids": [DATA_TOOL_ID], "skill_ids": [],
        "filter_ids": [], "features": {}, "files": [], "variables": {},
        "ees_demo_data_calls": 0,
        "params": {"function_calling": "native", "tool_approval_mode": "full"},
    }
    # Empty chat ID prevents DB history reads/writes. A local collector passed to
    # process_chat_response below activates the real native tool loop without
    # creating a saved chat or broadcasting the child answer into the parent.
    child.state.metadata = metadata
    form = {"model": model_id, "stream": True, "params": params,
            "messages": [{"role": "user", "content": question}],
            "tool_ids": [DATA_TOOL_ID], "skill_ids": [], "features": {},
            "files": [], "metadata": metadata}
    form, metadata, events = await runtime.process_payload(child, form, user, metadata, model)
    child.state.metadata = metadata

    # get_tools() above performs normal per-user Tool/UserValves access checks.
    # Do not accept injected tools, inherited browser capabilities or delegation.
    resolved = {name: tool for name, tool in metadata.get("tools", {}).items()
                if name == "read_demo_data" and tool.get("tool_id") == DATA_TOOL_ID and not tool.get("direct")}
    if not resolved:
        raise RuntimeError("data_tool_unavailable")

    def guard(function, name, allowed_params):
        # No functools.wraps: WebUI's get_updated_tool_function must not unwrap
        # this budget guard and rebind the original callable around it.
        async def guarded(**kwargs):
            kwargs = {key: value for key, value in kwargs.items() if key in allowed_params}
            if kwargs.get("dataset", "sample_a") != record["plan"]["snapshot"]["dataset"]:
                record["error"] = "plan_dataset_mismatch"
                return _json(_failure("plan_dataset_mismatch", "계획에 등록된 합성 자료 ID로만 확인해 주세요."))
            if record["data_calls"] >= MAX_DATA_CALLS:
                record["error"] = "data_call_limit"
                return _json(_failure("data_call_limit", "전문 분석의 자료 확인 한도에 도달했습니다."))
            record["data_calls"] += 1
            query = {"index": record["data_calls"], "tool": name,
                     "arguments": _panel_arguments(kwargs), "status": "querying"}
            record["queries"].append(query)
            await _panel(emitter, record, "querying")
            await _status(emitter, system, "querying", f"{system}: 합성 자료 확인 {record['data_calls']}/{MAX_DATA_CALLS}")
            try:
                result = await function(**kwargs)
            except asyncio.CancelledError:
                query["status"] = "cancelled"
                raise
            except Exception:
                record["error"] = "data_query_failed"
                result = _json(_failure("data_query_failed", "합성 자료 확인에 실패했습니다. 확보된 근거만 사용하세요."))
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                # Copy data only; do not retain functions/request/UserValves.
                safe_result = json.loads(json.dumps(parsed, ensure_ascii=False))
            except (TypeError, ValueError):
                safe_result = {"ok": False, "error": {"code": "invalid_data_result"}}
            record["evidence"].append({"tool": name, "arguments": dict(kwargs), "result": safe_result})
            if isinstance(safe_result, dict) and safe_result.get("ok") is False:
                record["error"] = "data_query_failed"
            _query_summary(query, safe_result)
            phase = "querying" if any(q["status"] == "querying" for q in record["queries"]) else "analyzing"
            await _panel(emitter, record, phase)
            return result
        return guarded

    for name, tool in resolved.items():
        public_params = {key for key in tool["spec"].get("parameters", {}).get("properties", {})
                         if not key.startswith("__")}
        resolved[name] = {**tool, "callable": guard(tool["callable"], name, public_params)}
    metadata["tools"] = resolved
    form["tools"] = [{"type": "function", "function": tool["spec"]} for tool in resolved.values()]

    async def collect(event):
        data = event.get("data") or {}
        if event.get("type") == "chat:completion":
            if isinstance(data.get("output"), list):
                _record_analysis(record, _visible_text(data["output"]))
            if data.get("error"):
                record["error"] = "model_response_failed"
        elif event.get("type") == "chat:message:error":
            record["error"] = "model_response_failed"

    await _panel(emitter, record, "analyzing")
    response = await runtime.generate(child, form, user)
    if not isinstance(response, runtime.StreamingResponse):
        # 0.11.3's non-streaming response handler does not execute tool calls.
        # Never claim the specialist ran when the provider ignored stream=True.
        raise RuntimeError("streaming_required")
    context = {"request": child, "form_data": form, "user": user, "model": model,
               "metadata": metadata, "tasks": {}, "events": events,
               "event_emitter": collect, "event_caller": None}
    await runtime.process_response(response, context)
    # Outlet filters may legitimately transform the final answer; read it after
    # the complete response path as well as collecting intermediate partials.
    final = context.get("assistant_message") or {}
    if isinstance(final.get("output"), list):
        _record_analysis(record, _visible_text(final["output"]))
    elif isinstance(final.get("content"), str):
        _record_analysis(record, final["content"])
    return _result(system, record)


class Tools:
    class Valves(BaseModel):
        ees_model_id: str = Field(default="", description="ApplyDemo가 연결한 기존 EES 모델 ID")
        specialist_timeout_seconds: int = Field(
            default=120, ge=5, le=600,
            description="전문 분석 한 번의 제한 시간. 첫 사내 시연 지연에 따라 조정합니다.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _authorized(self, request, metadata, user):
        return bool(
            request is not None and isinstance(metadata, dict) and isinstance(user, dict)
            and user.get("id") and self.valves.ees_model_id
            and metadata.get("model_id") == self.valves.ees_model_id
            and metadata.get("model_id") not in {v["model_id"] for v in SPECIALISTS.values()}
            and not getattr(request.state, "ees_specialist", False)
        )

    async def list_specialists(self, __user__: dict = None, __request__=None,
                               __metadata__: dict = None) -> str:
        """현재 사용자가 호출할 수 있는 시연 전문 Assistant와 역량을 확인합니다."""
        if not self._authorized(__request__, __metadata__, __user__):
            return _json(_failure("ees_only", "연결된 EES 통합 Assistant에서 전문 분석을 요청해 주세요."))
        try:
            runtime = _load_runtime()
            user = await runtime.Users.get_user_by_id(__user__["id"])
            if not user:
                raise RuntimeError("user_unavailable")
            available = []
            for system, details in SPECIALISTS.items():
                try:
                    await _model(runtime, __request__, user, details["model_id"])
                    available.append({"system": system, **details})
                except Exception:
                    continue
            return _json({"ok": True, "demo": True, "specialists": available,
                          "max_consultations": MAX_CONSULTATIONS,
                          "message": "필요한 전문 분야만 선택하세요. 기본 자료는 sample_a이며 다른 자료를 쓰면 질문에 자료 ID를 전달하세요."})
        except Exception:
            return _json(_failure("runtime_unavailable", "전문 Assistant 등록·버전·사용자 연결을 확인해 주세요."))

    async def manage_analysis_plan(self, action: str, title: str = "", steps: list[dict] = None,
                                   reviews: list[dict] = None, change_reason: str = "",
                                   conclusion: str = "", next_action: str = "", limitations: str = "",
                                   dataset: str = "sample_a", __user__: dict = None,
                                   __request__=None, __metadata__: dict = None,
                                   __event_emitter__=None) -> str:
        """실행 전 계획을 등록하고, 실제 근거를 받은 뒤 사용자용 판단 요약을 기록합니다.

        :param action: create(분석 전 1회), update(필요한 보완 단계 추가·공개 요약), finish(실제 실행 후 정리).
        :param title: create의 짧은 분석 제목.
        :param steps: create의 전체 단계 또는 update의 추가 단계. 각 항목 {"id":"ems", "type":"specialist|comparison|synthesis", "title":"정비 이력 확인", "system":"EMS|APC|FDC|EES", "reason_before":"확인 목적과 선택 이유", "depends_on":[]} . 앞에 등록된 단계만 의존 가능. create 마지막 단계는 synthesis 하나. 총 8단계까지.
        :param reviews: update/finish에서 실제 종료된 단계의 공개 설명 목록. {"step_id":"ems", "result_summary":"결과 한 줄", "judgment_after":"근거를 보고 내린 판단·변화", "uncertainty":"미확인·한계"}. 내부 사고 원문을 넣지 않습니다. 상태와 실행 전 이유는 바꿀 수 없습니다.
        :param change_reason: update에서 보완 단계가 필요한 실제 근거와 변경 이유.
        :param conclusion: finish의 핵심 결론, 최대 600자. 수치는 실제 조회·계산 근거만 사용합니다.
        :param next_action: finish의 추천 행동, 최대 400자.
        :param limitations: finish의 자료 부족·부분 실패·가설 수준 등 한계, 최대 600자.
        :param dataset: create의 합성 자료 ID sample_a 또는 sample_b. 실제 운영 자료가 아닙니다.
        """
        if not self._authorized(__request__, __metadata__, __user__):
            return _json(_failure("ees_only", "연결된 EES에서 분석 계획을 등록해 주세요."))
        if action not in ("create", "update", "finish"):
            return _json(_failure("invalid_plan_action", "create, update, finish 중 선택해 주세요."))
        if any(not isinstance(value, str) or len(value) > maximum for value, maximum in (
                (title, 120), (change_reason, 600), (conclusion, 600), (next_action, 400), (limitations, 600))):
            return _json(_failure("invalid_plan_text", "계획과 판단은 짧은 사용자용 요약으로 입력해 주세요."))
        plan = _active_plan(__request__, __user__, __metadata__)
        if action == "create":
            normalized = _validate_steps(steps)
            if (plan is not None or getattr(__request__.state, "ees_analysis_plan", None) is not None):
                return _json(_failure("plan_exists", "현재 요청의 계획을 유지하고 필요한 경우 update로 보완해 주세요."))
            if (not normalized or not title.strip() or dataset not in ("sample_a", "sample_b")
                    or len(normalized) < 2 or not _within_plan_budget(normalized) or normalized[-1]["type"] != "synthesis"
                    or sum(step["type"] == "synthesis" for step in normalized) != 1
                    or reviews or conclusion or next_action or limitations):
                return _json(_failure("invalid_plan", "실행할 단계와 마지막 종합 단계, 선택 이유·선행 단계를 확인해 주세요."))
            normalized[-1]["depends_on"] = [step["id"] for step in normalized[:-1]]
            plan_id = str(uuid4())
            ids = {key: value if isinstance(value, str) and len(value) <= 200 else ""
                   for key, value in ((key, __metadata__.get(key)) for key in ("chat_id", "message_id"))}
            plan = {"identity": _identity(__user__, __metadata__), "snapshot": {
                "version": 1, "kind": "plan", **ids, "call_id": plan_id, "batch_id": plan_id,
                "plan_id": plan_id, "seq": 0, "phase": "planned", "title": title,
                "dataset": dataset, "steps": normalized, "conclusion": "", "next_action": "",
                "limitations": "", "changes": [],
            }}
            __request__.state.ees_analysis_plan = plan
        else:
            if plan is None:
                return _json(_failure("plan_required", "같은 요청에서 실행 계획을 먼저 등록해 주세요."))
            current = plan["snapshot"]
            if current["phase"] in {"completed", "partial"}:
                return _json(_failure("plan_closed", "정리된 분석은 변경할 수 없습니다. 새 질문에서 다시 분석해 주세요."))
            if any(step["status"] == "running" for step in current["steps"]):
                return _json(_failure("plan_busy", "실행 중인 단계의 결과를 받은 뒤 계획을 보완·정리해 주세요."))
            candidate = copy.deepcopy(current)
            if steps:
                added = _validate_steps(steps, candidate["steps"])
                if (action != "update" or not change_reason.strip() or not added
                        or not _within_plan_budget([*candidate["steps"], *added])
                        or any(step["type"] == "synthesis" for step in added)
                        or any(candidate["steps"][-1]["id"] in step["depends_on"] for step in added)):
                    return _json(_failure("invalid_plan_change", "보완 근거와 실행 단계만 추가해 주세요."))
                candidate["steps"][-1:-1] = added
                candidate["steps"][-1]["depends_on"] = [step["id"] for step in candidate["steps"][:-1]]
                candidate["changes"].append(change_reason)
                candidate["phase"] = "running"
            if reviews is not None:
                if not isinstance(reviews, list) or len(reviews) > 8:
                    return _json(_failure("invalid_reviews", "종료된 단계별 결과·판단·한계를 입력해 주세요."))
                reviewed_ids = set()
                for review in reviews:
                    if (not isinstance(review, dict) or set(review) != {
                            "step_id", "result_summary", "judgment_after", "uncertainty"}
                            or any(not isinstance(review[key], str) or len(review[key]) > 600 for key in review)):
                        return _json(_failure("invalid_reviews", "단계별 공개 요약만 입력할 수 있습니다."))
                    step = next((item for item in candidate["steps"] if item["id"] == review["step_id"]), None)
                    if (not step or step["type"] == "synthesis" or step["status"] not in TERMINAL_STEPS
                            or step["id"] in reviewed_ids):
                        return _json(_failure("step_not_reviewable", "실제 종료된 실행 단계만 요약할 수 있습니다."))
                    reviewed_ids.add(step["id"])
                    for key in ("result_summary", "judgment_after", "uncertainty"):
                        step[key] = review[key]
            if action == "finish":
                executed = candidate["steps"][:-1]
                if any(step["status"] not in TERMINAL_STEPS for step in executed):
                    return _json(_failure("plan_unfinished", "미실행·진행 중인 단계가 남아 있습니다. 실제 결과를 확인한 후 정리해 주세요."))
                if (not conclusion.strip() or not next_action.strip()
                        or any(not step["result_summary"].strip() or not step["judgment_after"].strip()
                               for step in executed)):
                    return _json(_failure("summary_required", "종료된 단계의 결과·판단과 핵심 결론·다음 행동을 기록해 주세요."))
                partial = any(step["status"] != "completed" for step in executed)
                if partial and (not limitations.strip() or any(not step["uncertainty"].strip()
                        for step in executed if step["status"] != "completed")):
                    return _json(_failure("limitations_required", "부분·실패·취소 단계의 미확인 사항을 결론과 함께 밝혀 주세요."))
                candidate.update({"conclusion": conclusion, "next_action": next_action,
                                  "limitations": limitations, "phase": "partial" if partial else "completed"})
                candidate["steps"][-1].update({"status": candidate["phase"], "result_summary": conclusion,
                    "judgment_after": "확보된 결과와 미확인 사항을 구분해 분석을 정리했습니다.",
                    "uncertainty": limitations,
                    "call_ids": [cid for step in executed for cid in step["call_ids"]]})
            plan["snapshot"] = candidate
        await _plan_panel(__event_emitter__, plan)
        return _json({"ok": True, "demo": True, "plan_id": plan["snapshot"]["plan_id"],
                      "phase": plan["snapshot"]["phase"],
                      "steps": [{key: step[key] for key in ("id", "type", "system", "status", "depends_on")}
                                for step in plan["snapshot"]["steps"]],
                      "message": "계획에 연결된 실제 실행만 상태를 변경합니다. 본문에는 짧은 결론·한계·다음 행동만 남기고 상세는 업무 패널에서 확인하도록 안내하세요."})

    async def consult_specialists(self, tasks: list[dict], __user__: dict = None,
                                  __request__=None, __metadata__: dict = None,
                                  __event_emitter__=None) -> str:
        """필요한 전문 Assistant에 분석을 요청합니다. 독립된 요청은 함께 실행합니다.

        :param tasks: 1~3개 항목. 실행 계획 등록 후 각 항목은 {"step_id":"계획의 단계 ID", "system":"EMS 또는 APC 또는 FDC", "question":"확인 목적·설비·기간·자료 ID(sample_a/sample_b)를 포함한 질문"}. 최초 분야별 1회와 전체 추가 보완 1회까지 가능합니다.
        """
        if not self._authorized(__request__, __metadata__, __user__):
            return _json(_failure("ees_only", "연결된 EES 통합 Assistant에서 전문 분석을 요청해 주세요."))
        if (not isinstance(tasks, list) or not 1 <= len(tasks) <= 3
                or any(not isinstance(t, dict) or set(t) != {"step_id", "system", "question"}
                       or not isinstance(t.get("step_id"), str)
                       or not isinstance(t.get("system"), str) or t.get("system") not in SPECIALISTS
                       or not isinstance(t.get("question"), str) or not t["question"].strip()
                       or len(t["question"]) > MAX_QUESTION_CHARS for t in tasks)
                or len({t["system"] for t in tasks}) != len(tasks)):
            return _json(_failure("invalid_tasks", "서로 다른 EMS/APC/FDC와 확인 질문을 1~3개 입력해 주세요."))
        plan = _active_plan(__request__, __user__, __metadata__)
        if plan is None:
            return _json(_failure("plan_required", "전문 분석 전에 실행 계획을 등록해 주세요."))
        identity = _identity(__user__, __metadata__)
        budget = getattr(__request__.state, "ees_consultation_budget", None)
        if budget is None:
            budget = {"identity": identity, "counts": {}, "followups": 0, "total": 0}
            __request__.state.ees_consultation_budget = budget
        if budget["identity"] != identity:
            return _json(_failure("request_context_changed", "새 대화 요청에서 다시 분석해 주세요."))
        repeats = sum(t["system"] in budget["counts"] for t in tasks)
        if budget["total"] + len(tasks) > MAX_CONSULTATIONS or budget["followups"] + repeats > 1:
            return _json(_failure("consultation_limit", "전문 분석 한도에 도달했습니다. 확보한 근거와 남은 확인 사항을 종합해 주세요."))
        selected_steps = [_step_ready(plan, task["step_id"], "specialist", task["system"]) for task in tasks]
        if any(step is None for step in selected_steps) or len({task["step_id"] for task in tasks}) != len(tasks):
            return _json(_failure("step_not_ready", "계획의 대기 중인 해당 전문 단계와 선행 실행 결과를 확인해 주세요."))
        batch_id = str(uuid4())
        parent_ids = {key: value if isinstance(value, str) and len(value) <= 200 else ""
                      for key, value in ((key, __metadata__.get(key)) for key in ("chat_id", "message_id"))}
        records = [{"request": {"question": task["question"],
                                "kind": "followup" if task["system"] in budget["counts"] else "initial"},
                    "evidence": [], "data_calls": 0, "analysis": "", "analysis_truncated": False,
                    "queries": [], "plan": plan, "step": step, "panel": {"version": 1, "kind": "specialist", **parent_ids,
                        "plan_id": plan["snapshot"]["plan_id"], "step_id": step["id"],
                        "call_id": str(uuid4()), "seq": 0, "batch_id": batch_id, "system": task["system"]}}
                   for task, step in zip(tasks, selected_steps)]
        for record in records:
            _step_phase(plan, record["step"], "requested", record["panel"]["call_id"])
        # Reserve before the first await, so concurrent calls on this request
        # cannot both pass the same budget check. Failures also consume calls.
        budget["total"] += len(tasks)
        budget["followups"] += repeats
        for task in tasks:
            budget["counts"][task["system"]] = budget["counts"].get(task["system"], 0) + 1
        async def run(task, record):
            system = task["system"]
            await _status(__event_emitter__, system, "started", f"{system}: {task['question'][:160]}")
            try:
                async with asyncio.timeout(self.valves.specialist_timeout_seconds):
                    result = await _run_specialist(
                        runtime, __request__, user, system, task["question"], record, __event_emitter__)
            except asyncio.TimeoutError:
                result = _result(system, record, "timeout")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                safe_codes = {"model_unavailable", "data_tool_not_connected", "data_tool_unavailable", "streaming_required"}
                code = str(exc) if str(exc) in safe_codes else "specialist_unavailable"
                result = _result(system, record, code)
            # A timeout cancels in-flight queries, including a query interrupted
            # while its optional UI update was being sent.
            for query in record["queries"]:
                if query["status"] == "querying":
                    query["status"] = "cancelled"
            record["final_result"] = result
            phase = result["status"]
            label = {"completed": "분석 완료", "partial": "부분 결과 확보", "failed": "분석 미완료"}[phase]
            await _panel(__event_emitter__, record, phase, result["error"])
            await _status(__event_emitter__, system, phase, f"{system}: {label}", done=True)
            return result

        jobs = []
        try:
            await asyncio.gather(*(_panel(__event_emitter__, record, "requested") for record in records))
            try:
                runtime = _load_runtime()
                user = await runtime.Users.get_user_by_id(__user__["id"])
                if not user:
                    raise RuntimeError("user_unavailable")
            except Exception:
                await asyncio.gather(*(_panel(__event_emitter__, record, "failed", "runtime_unavailable")
                                       for record in records))
                return _json(_failure("runtime_unavailable", "전문 Assistant 등록·버전·사용자 연결을 확인해 주세요."))
            jobs = [asyncio.create_task(run(task, record)) for task, record in zip(tasks, records)]
            results = await asyncio.gather(*jobs)
        except asyncio.CancelledError:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            # Preserve evidence for request-local diagnostics without restarting a
            # cancelled parent generation or claiming all specialists completed.
            partial_results = []
            for task, record in zip(tasks, records):
                result = record.get("final_result")
                if result is None:
                    for query in record["queries"]:
                        if query["status"] == "querying":
                            query["status"] = "cancelled"
                    result = _result(task["system"], record, "cancelled")
                    await _panel(__event_emitter__, record, "cancelled", "cancelled")
                else:
                    # A completed computation may have been interrupted while
                    # sending its final UI update. Re-send that real outcome.
                    await _panel(__event_emitter__, record, result["status"], result["error"])
                partial_results.append(result)
            __request__.state.ees_specialist_partial_results = partial_results
            await _status(__event_emitter__, "EES", "cancelled", "전문 분석이 중단됐습니다. 완료된 결과만 보존했습니다.", done=True)
            raise
        return _json({"ok": any(r["status"] == "completed" for r in results), "demo": True,
                      "partial": any(r["status"] != "completed" for r in results), "results": results,
                      "budget": {"used": budget["total"], "remaining": MAX_CONSULTATIONS - budget["total"],
                                 "followup_remaining": 1 - budget["followups"]},
                      "message": "합성 자료의 실제 전문 분석 결과입니다. 실제 회신·조회 근거와 교차 계산을 대조하고 부분·실패·잘린 회신을 구분하세요. 단계별 공개 판단은 finish에 모아 기록하고, 본문에는 핵심 결론·한계·다음 행동만 짧게 설명하세요. 긴 전문 회신·원시 자료는 업무 패널에서 확인합니다."})
