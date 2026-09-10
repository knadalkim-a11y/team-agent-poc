"""Specialist request isolation, exact budgets and pinned WebUI loop integration.

No production DB, model server, credentials or saved chats are used. If the
verified wheel is present, its actual native streaming handler is executed with
synthetic provider responses; this is not a real-model quality test.
"""

import ast
import asyncio
import copy
import importlib.util
import inspect
import json
import logging
import os
import re
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Awaitable, Callable, get_args, get_type_hints
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from functools import partial, update_wrapper

PATH = Path(__file__).resolve().parents[1] / "agent-pack/skills/cross-system-analysis/scripts/specialists_tool.py"
SPEC = importlib.util.spec_from_file_location("ees_specialists_tests", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
LOAD_RUNTIME = module._load_runtime


class State:
    def __init__(self, state):
        object.__setattr__(self, "_state", state)

    def __getattr__(self, name):
        if name not in self._state:
            raise AttributeError(name)
        return self._state[name]

    def __setattr__(self, name, value):
        self._state[name] = value


class Request:
    """Minimal Starlette interface; no dependency installation for repository CI."""
    def __init__(self, scope):
        self.scope = scope
        self.state = State(scope.setdefault("state", {}))
        self.app = scope["app"]


class StreamingResponse:
    def __init__(self, body_iterator, media_type="text/event-stream"):
        self.body_iterator = body_iterator
        self.headers = {"Content-Type": media_type}
        self.background = None
        self.status_code = 200


class FakeUser:
    id = "user-one"
    role = "user"

    def model_dump(self):
        return {"id": self.id, "role": self.role}


class FakeInfo:
    def __init__(self, system):
        self.id = module.SPECIALISTS[system]["model_id"]
        self.params = SimpleNamespace(model_dump=lambda: {"system": f"{system} domain prompt", "temperature": 0.2})
        self.base_model_id = "shared-internal-model"

    def model_dump(self):
        return {"id": self.id, "base_model_id": self.base_model_id, "meta": {
            "toolIds": [module.DATA_TOOL_ID], "skillIds": [], "capabilities": {"citations": False},
        }}


def request():
    return Request({"type": "http", "method": "POST", "path": "/api/chat/completions",
                    "headers": [], "state": {}, "app": SimpleNamespace(state=SimpleNamespace(
                        MODELS={v["model_id"]: {"id": v["model_id"], "owned_by": "openai"}
                                for v in module.SPECIALISTS.values()}, redis=None))})


def stream(chunks):
    async def body():
        for chunk in chunks:
            yield "data: " + json.dumps(chunk) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(body(), media_type="text/event-stream")


def tool_chunk(count=1):
    return {"choices": [{"delta": {"tool_calls": [
        {"index": i, "id": f"call-{i}", "type": "function", "function": {
            "name": "read_demo_data", "arguments": json.dumps({"dataset": "sample_a"})}}
        for i in range(count)]}, "finish_reason": "tool_calls"}]}


def answer_chunk(text="EMS-001에서 정비 이력을 확인했습니다."):
    return {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}


class SpecialistsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = module.Tools()
        self.tool.valves.ees_model_id = "existing-ees"
        self.request = request()
        self.metadata = {"model_id": "existing-ees", "chat_id": "parent-chat", "message_id": "parent-message"}
        self.events = []
        self.user = FakeUser()
        self.info = {v["model_id"]: FakeInfo(k) for k, v in module.SPECIALISTS.items()}
        self.calls = []
        self.data_calls = []
        self.runtime = SimpleNamespace(
            Request=Request, StreamingResponse=StreamingResponse,
            Config=SimpleNamespace(get=AsyncMock(return_value={})),
            Models=SimpleNamespace(get_model_by_id=AsyncMock(side_effect=lambda mid: self.info.get(mid))),
            Users=SimpleNamespace(get_user_by_id=AsyncMock(return_value=self.user)),
            check_access=AsyncMock(), bypass_admin=False, bypass_models=False,
            merge_params=lambda a, b: {**a, **b},
            process_payload=self.payload, process_response=self.response, generate=self.generate,
        )
        self.runtime_patch = patch.object(module, "_load_runtime", return_value=self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    async def emit(self, event):
        self.events.append(event)

    async def payload(self, child, form, user, metadata, model):
        self.calls.append((child, copy.deepcopy(form), user, metadata, model))
        async def data(**kwargs):
            metadata["ees_demo_data_calls"] += 1
            self.data_calls.append((metadata["model_id"], user.id, kwargs, metadata))
            return json.dumps({"ok": True, "demo": True, "records": [{"id": "EMS-001"}]})
        metadata["tools"] = {
            "read_demo_data": {"tool_id": "ees_demo_data", "callable": data, "spec": {
                "name": "read_demo_data", "parameters": {"type": "object", "properties": {"dataset": {"type": "string"}}},
            }},
            # A parent/global filter injection must not escape the demo allowlist.
            "delegate_task": {"tool_id": "unrelated", "callable": AsyncMock(), "spec": {"name": "delegate_task"}},
        }
        return form, metadata, []

    async def generate(self, child, form, user, **kwargs):
        return stream([answer_chunk()])

    async def response(self, response, ctx):
        data = await ctx["metadata"]["tools"]["read_demo_data"]["callable"](dataset="sample_a")
        self.assertIn("EMS-001", data)
        await ctx["event_emitter"]({"type": "chat:completion", "data": {"done": True, "output": [
            {"type": "reasoning", "content": [{"type": "output_text", "text": "private reasoning"}]},
            {"type": "message", "content": [{"type": "output_text", "text": "확인된 정비 근거 EMS-001"}]},
        ]}})

    async def consult(self, systems=("EMS",), **overrides):
        args = {"tasks": [{"system": s, "question": "sample_a의 개선 기회를 확인해줘"} for s in systems],
                "__user__": self.user.model_dump(), "__request__": self.request,
                "__metadata__": self.metadata, "__event_emitter__": self.emit}
        args.update(overrides)
        # These adapter/budget tests supply an already registered plan fixture.
        # Workflow registration and dependencies are exercised separately below.
        if (self.tool._authorized(args["__request__"], args["__metadata__"], args["__user__"])
                and isinstance(args["tasks"], list)):
            selected = copy.deepcopy(args["tasks"])
            plan = getattr(args["__request__"].state, "ees_analysis_plan", None)
            if plan is None:
                plan = {"identity": module._identity(args["__user__"], args["__metadata__"]), "snapshot": {
                    "version": 1, "kind": "plan", "plan_id": "adapter-plan", "call_id": "adapter-plan",
                    "batch_id": "adapter-plan", "seq": 0, "phase": "planned", "dataset": "sample_a",
                    "chat_id": args["__metadata__"].get("chat_id", ""),
                    "message_id": args["__metadata__"].get("message_id", ""), "steps": []}}
                args["__request__"].state.ees_analysis_plan = plan
            for task in selected:
                if isinstance(task, dict) and set(task) == {"system", "question"}:
                    step_id = str(uuid4())
                    task["step_id"] = step_id
                    plan["snapshot"]["steps"].append({"id": step_id, "type": "specialist",
                        "system": task["system"], "status": "pending", "depends_on": [],
                        "call_ids": [], "reason_before": "공개 확인 목적", "result_summary": "",
                        "judgment_after": "", "uncertainty": ""})
            args["tasks"] = selected
        return json.loads(await self.tool.consult_specialists(**args))

    def panel_updates(self, include_plans=False):
        updates = []
        for event in self.events:
            if event["type"] == "execute":
                code = event["data"]["code"]
                self.assertTrue(code.startswith("const eesPanelUpdate="))
                value, end = json.JSONDecoder().raw_decode(code[len("const eesPanelUpdate="):])
                self.assertEqual(code[len("const eesPanelUpdate=") + end:], ";\n" + module.PANEL_SCRIPT)
                if include_plans or value["kind"] != "plan":
                    updates.append(value)
        return updates

    async def test_panel_tracks_real_requests_queries_replies_and_followup_without_private_data(self):
        original = self.payload
        async def payload(child, form, user, metadata, model):
            result = await original(child, form, user, metadata, model)
            async def data(**kwargs):
                return {"ok": True, "record_count": 1, "records": [{
                    "event_id": "sample_a-01", "records": [{"secret": "DO-NOT-RETURN-RAW"}]}]}
            metadata["tools"]["read_demo_data"]["callable"] = data
            metadata["private"] = "DO-NOT-RETURN-METADATA"
            return result
        async def response(_, ctx):
            await ctx["metadata"]["tools"]["read_demo_data"]["callable"](
                dataset="sample_a", __user__={"pat": "DO-NOT-RETURN-VALVES"})
            await ctx["event_emitter"]({"type": "chat:completion", "data": {"output": [
                {"type": "reasoning", "content": [{"type": "output_text", "text": "DO-NOT-RETURN-REASONING"}]},
                {"type": "message", "content": [{"type": "output_text", "text": "확인한 회신"}]}]}})
        self.runtime.process_payload = payload
        self.runtime.process_response = response
        questions = [{"system": system, "question": f'{system}의 질문 "sample_a";\n상세 확인'}
                     for system in ("EMS", "APC", "FDC")]
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            first = await self.consult(tasks=questions)
            await self.consult(tasks=[{"system": "APC", "question": "sample_a 보완 질문"}])
            updates = self.panel_updates()
        self.assertTrue(first["ok"])
        self.assertEqual(len(self.calls), 4)
        grouped = {}
        for update in updates:
            grouped.setdefault(update["call_id"], []).append(update)
            self.assertEqual((update["chat_id"], update["message_id"]), ("parent-chat", "parent-message"))
            self.assertEqual((update["kind"], update["version"]), ("specialist", 1))
        self.assertEqual(len(grouped), 4)
        self.assertEqual(len({v[0]["batch_id"] for v in grouped.values()}), 2)
        for rows in grouped.values():
            self.assertEqual([r["seq"] for r in rows], [1, 2, 3, 4, 5])
            self.assertEqual([r["phase"] for r in rows], ["requested", "analyzing", "querying", "analyzing", "completed"])
            self.assertEqual(rows[0]["queries"], [])
            self.assertEqual(rows[2]["queries"][0]["status"], "querying")
            self.assertEqual(rows[-1]["queries"], [{"index": 1, "tool": "read_demo_data",
                "arguments": {"dataset": "sample_a"}, "status": "completed",
                "record_count": 1, "event_ids": ["sample_a-01"]}])
            self.assertEqual(rows[-1]["analysis"], "확인한 회신")
        final = [rows[-1] for rows in grouped.values()]
        self.assertEqual([r["request"] for r in final], [
            {"question": t["question"], "kind": "initial"} for t in questions
        ] + [{"question": "sample_a 보완 질문", "kind": "followup"}])
        self.assertNotIn("DO-NOT-RETURN", json.dumps(updates))
        self.assertNotIn('"evidence"', json.dumps(updates))

    async def test_panel_parallel_queries_keep_their_own_results_and_monotonic_snapshots(self):
        original = self.payload
        entered = {name: asyncio.Event() for name in ("sample_a-01", "sample_a-02")}
        release = {name: asyncio.Event() for name in entered}
        async def payload(child, form, user, metadata, model):
            result = await original(child, form, user, metadata, model)
            async def data(dataset, event_id):
                entered[event_id].set()
                await release[event_id].wait()
                return {"ok": True, "record_count": 1 if event_id == "sample_a-01" else 2,
                        "records": [{"event_id": event_id}]}
            metadata["tools"]["read_demo_data"]["callable"] = data
            metadata["tools"]["read_demo_data"]["spec"]["parameters"]["properties"]["event_id"] = {"type": "string"}
            return result
        async def response(_, ctx):
            function = ctx["metadata"]["tools"]["read_demo_data"]["callable"]
            jobs = [asyncio.create_task(function(dataset="sample_a", event_id=name)) for name in entered]
            await asyncio.gather(*(event.wait() for event in entered.values()))
            release["sample_a-02"].set()
            await jobs[1]
            release["sample_a-01"].set()
            await jobs[0]
            ctx["assistant_message"] = {"content": "두 자료 확인"}
        self.runtime.process_payload = payload
        self.runtime.process_response = response
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            await self.consult()
            updates = self.panel_updates()
        self.assertEqual([u["seq"] for u in updates], list(range(1, len(updates) + 1)))
        intermediate = next(u for u in updates if len(u["queries"]) == 2
                            and u["queries"][1]["status"] == "completed"
                            and u["queries"][0]["status"] == "querying")
        self.assertEqual(intermediate["phase"], "querying")
        self.assertEqual([q["record_count"] for q in updates[-1]["queries"]], [1, 2])
        self.assertEqual([q["event_ids"] for q in updates[-1]["queries"]], [["sample_a-01"], ["sample_a-02"]])

    async def test_panel_freezes_query_and_plan_snapshots_before_slow_plan_emission(self):
        # Force query 2 to enter while query 1 is waiting for its plan event.
        # Both packets must retain the sequence and data at their own boundary.
        first_plan = asyncio.Event()
        second_plan = asyncio.Event()
        release = asyncio.Event()
        step = {"id": "ems", "type": "specialist", "status": "pending", "call_ids": [],
                "result_summary": "first"}
        plan = {"snapshot": {"version": 1, "kind": "plan", "phase": "planned", "seq": 0,
                "chat_id": "chat", "message_id": "message", "call_id": "plan", "steps": [step]}}
        record = {"panel": {"version": 1, "kind": "specialist", "seq": 0,
                    "chat_id": "chat", "message_id": "message", "call_id": "ems-call"},
                  "plan": plan, "step": step, "request": {"question": "sample_a", "kind": "initial"},
                  "queries": [{"index": 1, "status": "querying"}], "analysis": "first",
                  "analysis_truncated": False}
        async def emit(event):
            payload, _ = json.JSONDecoder().raw_decode(event["data"]["code"][len("const eesPanelUpdate="):])
            self.events.append(event)
            if payload["kind"] == "plan":
                (first_plan if payload["seq"] == 1 else second_plan).set()
                await release.wait()
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            first = asyncio.create_task(module._panel(emit, record, "querying"))
            await first_plan.wait()
            record["queries"].append({"index": 2, "status": "querying"})
            record["analysis"] = "second"
            step["result_summary"] = "second"
            second = asyncio.create_task(module._panel(emit, record, "querying"))
            await second_plan.wait()
            release.set()
            await asyncio.gather(first, second)
            specialists = self.panel_updates()
            plans = [event for event in self.panel_updates(include_plans=True) if event["kind"] == "plan"]
        self.assertEqual([event["seq"] for event in specialists], [1, 2])
        self.assertEqual([len(event["queries"]) for event in specialists], [1, 2])
        self.assertEqual([event["analysis"] for event in specialists], ["first", "second"])
        self.assertEqual([event["seq"] for event in plans], [1, 2])
        self.assertEqual([event["steps"][0]["result_summary"] for event in plans], ["first", "second"])

    async def test_panel_denial_timeout_and_runtime_failure_are_terminal_without_fake_completion(self):
        async def allow(user, model, model_info):
            self.assertTrue(any(u["system"] == model_info.id.removeprefix("ees_demo_").upper()
                                and u["phase"] == "requested" for u in self.panel_updates()))
            if model_info.id == "ees_demo_fdc":
                raise PermissionError("DO-NOT-RETURN")
        async def response(response, ctx):
            await self.response(response, ctx)
            if ctx["metadata"]["model_id"] == "ees_demo_apc":
                await asyncio.Event().wait()
        self.runtime.check_access.side_effect = allow
        self.runtime.process_response = response
        self.tool.valves.specialist_timeout_seconds = 0.04
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            await self.consult(("EMS", "APC", "FDC"))
            updates = self.panel_updates()
            final = {system: [u for u in updates if u["system"] == system][-1]
                     for system in ("EMS", "APC", "FDC")}
            self.assertEqual([final[s]["phase"] for s in final], ["completed", "partial", "failed"])
            self.assertEqual(final["APC"]["error"], "timeout")
            self.assertEqual(final["APC"]["analysis"], "확인된 정비 근거 EMS-001")
            self.assertEqual(final["FDC"]["queries"], [])
            self.assertNotIn("DO-NOT-RETURN", json.dumps(updates))
            self.request = request()
            self.events.clear()
            with patch.object(module, "_load_runtime", side_effect=RuntimeError("DO-NOT-RETURN")):
                failed = await self.consult(("EMS", "APC"))
            self.assertEqual(failed["error"]["code"], "runtime_unavailable")
            for system in ("EMS", "APC"):
                rows = [u for u in self.panel_updates() if u["system"] == system]
                self.assertEqual([u["phase"] for u in rows], ["requested", "failed"])
                self.assertEqual(rows[-1]["error"], "runtime_unavailable")

    async def test_panel_cancellation_marks_inflight_query_and_retains_visible_partial(self):
        original = self.payload
        entered = asyncio.Event()
        async def payload(child, form, user, metadata, model):
            result = await original(child, form, user, metadata, model)
            async def data(**kwargs):
                entered.set()
                await asyncio.Event().wait()
            metadata["tools"]["read_demo_data"]["callable"] = data
            return result
        async def response(_, ctx):
            await ctx["event_emitter"]({"type": "chat:completion", "data": {"output": [
                {"type": "message", "content": [{"type": "output_text", "text": "부분 회신"}]}]}})
            await ctx["metadata"]["tools"]["read_demo_data"]["callable"](dataset="sample_a")
        self.runtime.process_payload = payload
        self.runtime.process_response = response
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            job = asyncio.create_task(self.consult())
            await entered.wait()
            job.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await job
            final = self.panel_updates()[-1]
        self.assertEqual(final["phase"], "cancelled")
        self.assertEqual(final["queries"][0]["status"], "cancelled")
        self.assertEqual(final["analysis"], "부분 회신")
        self.assertEqual(self.request.state.ees_specialist_partial_results[0]["error"], "cancelled")

    async def test_panel_unavailable_ui_is_bounded_and_missing_context_is_not_broadcast(self):
        async def unavailable(event):
            if event["type"] == "execute":
                await asyncio.Event().wait()
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"), patch.object(module, "PANEL_SEND_TIMEOUT", 0.002):
            result = await asyncio.wait_for(self.consult(__event_emitter__=unavailable), timeout=1)
            self.assertTrue(result["ok"])
            self.request = request()
            result = await self.consult(__metadata__={"model_id": "existing-ees"})
            self.assertTrue(result["ok"])
            self.assertEqual(self.panel_updates(), [])

    async def test_full_adapter_uses_child_identity_prompt_tools_and_evidence(self):
        self.request.state.metadata = self.metadata
        self.request.state.token = object()
        result = await self.consult()
        self.assertTrue(result["ok"])
        child, form, user, metadata, model = self.calls[0]
        self.assertIsNot(child.state, self.request.state)
        self.assertIsNot(child.scope["state"], self.request.scope["state"])
        self.assertIs(child.state.token, self.request.state.token)
        self.assertIs(user, self.user)
        self.assertEqual(form["model"], "ees_demo_ems")
        self.assertEqual(form["params"]["system"], "EMS domain prompt")
        self.assertEqual(form["tool_ids"], ["ees_demo_data"])
        self.assertEqual(set(metadata["tools"]), {"read_demo_data"})
        self.assertEqual(metadata["model_id"], "ees_demo_ems")
        self.assertEqual(metadata["chat_id"], "")
        self.assertIsNone(metadata["session_id"])
        self.assertIs(self.request.state.metadata, self.metadata)
        self.assertEqual(self.metadata["model_id"], "existing-ees")
        self.assertEqual(result["results"][0]["request"], {
            "question": form["messages"][0]["content"], "kind": "initial",
        })
        self.assertFalse(result["results"][0]["analysis_truncated"])
        self.assertEqual(result["results"][0]["evidence"][0]["result"]["records"][0]["id"], "EMS-001")
        self.assertNotIn("private reasoning", json.dumps(result))
        self.runtime.check_access.assert_awaited_once()
        self.assertEqual([e["data"]["phase"] for e in self.events], ["started", "querying", "completed"])

    async def test_runtime_accepts_official_and_existing_custom_versions(self):
        modules = {
            "starlette.requests": SimpleNamespace(Request=Request),
            "starlette.responses": SimpleNamespace(StreamingResponse=StreamingResponse),
            "open_webui.config": SimpleNamespace(BYPASS_ADMIN_ACCESS_CONTROL=False),
            "open_webui.env": SimpleNamespace(BYPASS_MODEL_ACCESS_CONTROL=False),
            "open_webui.models.config": SimpleNamespace(Config=self.runtime.Config),
            "open_webui.models.models": SimpleNamespace(Models=self.runtime.Models),
            "open_webui.models.users": SimpleNamespace(Users=self.runtime.Users),
            "open_webui.utils.chat": SimpleNamespace(generate_chat_completion=self.runtime.generate),
            "open_webui.utils.middleware": SimpleNamespace(process_chat_payload=self.runtime.process_payload,
                                                           process_chat_response=self.runtime.process_response),
            "open_webui.utils.misc": SimpleNamespace(merge_model_params=self.runtime.merge_params),
            "open_webui.utils.models": SimpleNamespace(check_model_access=self.runtime.check_access),
        }
        def imported(name, *args, **kwargs):
            return modules[name]
        for version in ("0.11.3", "0.11.3+ees.1", "0.11.3+ees.2"):
            with self.subTest(version=version), patch.object(module, "version", return_value=version):
                with patch("builtins.__import__", side_effect=imported):
                    runtime = LOAD_RUNTIME()
                self.assertIs(runtime.Request, Request)
                self.assertIs(runtime.process_response, self.runtime.process_response)
        with patch.object(module, "version", return_value="0.11.4"):
            with self.assertRaisesRegex(RuntimeError, "unsupported_webui_version"):
                LOAD_RUNTIME()

    async def test_list_is_permission_filtered_and_does_not_call_provider(self):
        async def allow(user, model, model_info):
            if model_info.id == "ees_demo_apc":
                raise PermissionError("private model")
        self.runtime.check_access.side_effect = allow
        result = json.loads(await self.tool.list_specialists(__user__=self.user.model_dump(),
                            __request__=self.request, __metadata__=self.metadata))
        self.assertEqual([s["system"] for s in result["specialists"]], ["EMS", "FDC"])
        self.assertEqual(self.calls, [])

    async def test_missing_or_denied_model_fails_without_llm_and_hides_details(self):
        self.runtime.check_access.side_effect = PermissionError("token=DO-NOT-RETURN")
        result = await self.consult()
        self.assertFalse(result["ok"])
        self.assertEqual(result["results"][0]["error"], "specialist_unavailable")
        self.assertNotIn("DO-NOT-RETURN", json.dumps(result))
        self.assertEqual(self.calls, [])

    async def test_three_initial_then_one_followup_only(self):
        tasks = [{"system": s, "question": f"sample_a에서 {s}의 개선 근거를 확인해줘"}
                 for s in ("EMS", "APC", "FDC")]
        first = await self.consult(tasks=tasks)
        self.assertTrue(first["ok"])
        self.assertEqual([r["request"] for r in first["results"]], [
            {"question": t["question"], "kind": "initial"} for t in tasks])
        followup_question = "sample_a의 APC 조건 변경 전후를 다시 비교해줘"
        fourth = await self.consult(tasks=[{"system": "APC", "question": followup_question}])
        self.assertEqual(fourth["results"][0]["request"], {
            "question": followup_question, "kind": "followup",
        })
        self.assertEqual(fourth["budget"], {"used": 4, "remaining": 0, "followup_remaining": 0})
        fifth = await self.consult(("EMS",))
        self.assertEqual(fifth["error"]["code"], "consultation_limit")
        self.assertEqual(len(self.calls), 4)

    async def test_repeating_one_specialist_cannot_consume_three_initial_slots(self):
        await self.consult()
        await self.consult()
        self.assertEqual((await self.consult())["error"]["code"], "consultation_limit")
        self.assertEqual(len(self.calls), 2)
        self.assertTrue((await self.consult(("APC", "FDC")))["ok"])

    async def test_budget_reserved_before_concurrent_calls_and_new_request_is_fresh(self):
        results = await asyncio.gather(self.consult(), self.consult(), self.consult())
        self.assertEqual(sum(r["ok"] for r in results), 2)
        self.assertEqual([r["results"][0]["request"]["kind"] for r in results if r["ok"]],
                         ["initial", "followup"])
        self.assertEqual(len(self.calls), 2)
        self.request = request()
        fresh = await self.consult()
        self.assertTrue(fresh["ok"])
        self.assertEqual(fresh["results"][0]["request"]["kind"], "initial")

    async def test_recursive_wrong_ees_and_missing_context_are_blocked(self):
        for metadata in [None, {}, {"model_id": "ees_demo_ems"}, {"model_id": "another-model"}]:
            self.assertEqual((await self.consult(__metadata__=metadata))["error"]["code"], "ees_only")
        self.request.state.ees_specialist = True
        self.assertEqual((await self.consult())["error"]["code"], "ees_only")
        self.assertEqual(self.calls, [])

    async def test_argument_validation_does_not_consume_budget(self):
        for tasks in [[], None, "EMS", [{}], [{"system": [], "question": "x"}],
                      [{"system": "EMS", "question": "x", "model": "other"}],
                      [{"system": "EMS", "question": ""}],
                      [{"system": "EMS", "question": "x"}] * 2]:
            with self.subTest(tasks=tasks):
                self.assertEqual((await self.consult(tasks=tasks))["error"]["code"], "invalid_tasks")
        self.assertFalse(hasattr(self.request.state, "ees_consultation_budget"))

    async def test_exact_data_budget_protects_parallel_calls_in_one_iteration(self):
        async def many(response, ctx):
            function = ctx["metadata"]["tools"]["read_demo_data"]["callable"]
            values = await asyncio.gather(*(function(dataset="sample_a") for _ in range(5)))
            self.assertEqual(sum(json.loads(v)["ok"] for v in values), 3)
            await ctx["event_emitter"]({"type": "chat:completion", "data": {"output": [
                {"type": "message", "content": [{"type": "output_text", "text": "부분 분석"}]}]}})
        self.runtime.process_response = many
        result = (await self.consult())["results"][0]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data_calls"], 3)
        self.assertEqual(result["error"], "data_call_limit")
        self.assertEqual(len(self.data_calls), 3)
        self.assertEqual(len(result["evidence"]), 3)

    async def test_timeout_preserves_evidence_and_other_specialist_success(self):
        # APC was already consulted; one batch now mixes an initial success, a
        # follow-up timeout and an initial access failure with different questions.
        await self.consult(("APC",))
        async def allow(user, model, model_info):
            if model_info.id == "ees_demo_fdc":
                raise PermissionError("token=DO-NOT-RETURN")
        async def slow(response, ctx):
            await self.response(response, ctx)
            if ctx["metadata"]["model_id"] == "ees_demo_apc":
                await asyncio.Event().wait()
        self.runtime.check_access.side_effect = allow
        self.runtime.process_response = slow
        # Bypass only Pydantic assignment validation for a fast synthetic timeout.
        self.tool.valves.specialist_timeout_seconds = 0.02
        tasks = [{"system": s, "question": f"sample_a의 {s} 상세 근거를 확인해줘"}
                 for s in ("EMS", "APC", "FDC")]
        result = await self.consult(tasks=tasks)
        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual([r["status"] for r in result["results"]], ["completed", "partial", "failed"])
        self.assertEqual(result["results"][1]["error"], "timeout")
        self.assertEqual(len(result["results"][1]["evidence"]), 1)
        self.assertEqual(result["results"][2]["error"], "specialist_unavailable")
        self.assertEqual([r["request"] for r in result["results"]], [
            {"question": t["question"], "kind": "followup" if t["system"] == "APC" else "initial"}
            for t in tasks])
        self.assertEqual(result["budget"]["used"], 4)
        self.assertNotIn("DO-NOT-RETURN", json.dumps(result))

    async def test_cancellation_propagates_and_preserves_completed_evidence(self):
        entered = asyncio.Event()
        async def slow(response, ctx):
            await self.response(response, ctx)
            if ctx["metadata"]["model_id"] == "ees_demo_apc":
                entered.set()
                await asyncio.Event().wait()
        self.runtime.process_response = slow
        job = asyncio.create_task(self.consult(("EMS", "APC")))
        await entered.wait()
        job.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await job
        partial = self.request.state.ees_specialist_partial_results
        self.assertEqual(len(partial), 2)
        self.assertTrue(all(r["evidence"] for r in partial))
        self.assertEqual(partial[1]["error"], "cancelled")
        self.assertEqual([r["request"] for r in partial], [
            {"question": "sample_a의 개선 기회를 확인해줘", "kind": "initial"}] * 2)
        self.assertEqual(self.events[-1]["data"]["phase"], "cancelled")

    async def test_returned_reply_truncation_tracks_final_output_without_reasoning(self):
        limit = module.MAX_ANALYSIS_CHARS
        long_text = "clipped-prefix:" + "가" * limit + "확인된 근거 EMS-001"
        private = "DO-NOT-RETURN-REASONING" * limit

        def output(text):
            return [
                {"type": "reasoning", "content": [{"type": "output_text", "text": private}]},
                {"type": "function_call", "arguments": "DO-NOT-RETURN-ARGUMENTS"},
                {"type": "message", "content": [{"type": "output_text", "text": text}]},
            ]

        cases = [
            ("streamed", long_text, None, long_text),
            ("final_output", "short partial", {"output": output(long_text)}, long_text),
            ("final_content", "short partial", {"content": long_text}, long_text),
            ("replaced_short", long_text, {"output": output("최종 짧은 회신")}, "최종 짧은 회신"),
            ("exact_limit", "나" * limit, None, "나" * limit),
        ]
        for name, streamed, final, expected in cases:
            with self.subTest(name=name):
                self.request = request()
                async def respond(response, ctx):
                    await self.response(response, ctx)
                    await ctx["event_emitter"]({"type": "chat:completion", "data": {
                        "output": output(streamed)}})
                    if final is not None:
                        ctx["assistant_message"] = final
                self.runtime.process_response = respond
                with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
                    result = await self.consult()
                    final_panel = self.panel_updates()[-1]
                returned = result["results"][0]
                self.assertEqual(returned["analysis"], expected[-limit:])
                self.assertEqual(returned["analysis_truncated"], len(expected) > limit)
                self.assertEqual(returned["status"], "completed")
                self.assertNotIn("DO-NOT-RETURN", json.dumps(result))
                self.assertEqual(final_panel["analysis"], returned["analysis"])
                self.assertEqual(final_panel["analysis_truncated"], returned["analysis_truncated"])
                self.assertNotIn("DO-NOT-RETURN", json.dumps(final_panel))

    async def test_non_stream_provider_never_claims_tool_execution(self):
        self.runtime.generate = AsyncMock(return_value={"choices": [{"message": {"content": "pretend answer"}}]})
        result = await self.consult()
        self.assertEqual(result["results"][0]["error"], "streaming_required")
        self.assertEqual(self.data_calls, [])

    async def test_answer_without_data_is_marked_unverified(self):
        async def unsupported(response, ctx):
            ctx["assistant_message"] = {"content": "확인하지 않은 분석"}
        self.runtime.process_response = unsupported
        result = await self.consult()
        self.assertEqual(result["results"][0]["error"], "data_not_queried")
        self.assertEqual(result["results"][0]["status"], "partial")

    async def test_tool_access_denial_prevents_model_call(self):
        async def no_tools(child, form, user, metadata, model):
            return form, metadata, []
        self.runtime.process_payload = no_tools
        provider = AsyncMock()
        self.runtime.generate = provider
        result = await self.consult()
        self.assertEqual(result["results"][0]["error"], "data_tool_unavailable")
        provider.assert_not_called()

    async def test_later_query_exception_marks_partial_and_redacts_error(self):
        original = self.payload
        async def failing_payload(child, form, user, metadata, model):
            result = await original(child, form, user, metadata, model)
            original_data = metadata["tools"]["read_demo_data"]["callable"]
            async def failing_data(**kwargs):
                if metadata["ees_demo_data_calls"]:
                    raise RuntimeError("token=DO-NOT-RETURN")
                return await original_data(**kwargs)
            metadata["tools"]["read_demo_data"]["callable"] = failing_data
            return result
        async def two_queries(response, ctx):
            await self.response(response, ctx)
            failed = await ctx["metadata"]["tools"]["read_demo_data"]["callable"](dataset="sample_a")
            self.assertEqual(json.loads(failed)["error"]["code"], "data_query_failed")
        self.runtime.process_payload = failing_payload
        self.runtime.process_response = two_queries
        result = await self.consult()
        self.assertTrue(result["partial"])
        self.assertEqual(result["results"][0]["status"], "partial")
        self.assertEqual(result["results"][0]["error"], "data_query_failed")
        self.assertEqual(len(result["results"][0]["evidence"]), 2)
        self.assertNotIn("DO-NOT-RETURN", json.dumps(result))

    async def test_evidence_never_contains_reserved_context_arguments(self):
        async def reserved(response, ctx):
            await ctx["metadata"]["tools"]["read_demo_data"]["callable"](
                dataset="sample_a", __user__={"valves": {"pat": "DO-NOT-RETURN"}},
                __request__=self.request, __metadata__=self.metadata)
            ctx["assistant_message"] = {"content": "자료 확인"}
        self.runtime.process_response = reserved
        result = await self.consult()
        arguments = result["results"][0]["evidence"][0]["arguments"]
        self.assertEqual(arguments, {"dataset": "sample_a"})
        self.assertNotIn("DO-NOT-RETURN", json.dumps(result))
        self.assertEqual(self.data_calls[0][2], {"dataset": "sample_a"})

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    """Actual registered-plan → specialist → comparison → summary contract."""

    setUp = SpecialistsTests.setUp
    emit = SpecialistsTests.emit
    payload = SpecialistsTests.payload
    generate = SpecialistsTests.generate
    response = SpecialistsTests.response
    panel_updates = SpecialistsTests.panel_updates

    @staticmethod
    def step(identifier, kind="specialist", system="EMS", dependencies=()):
        return {"id": identifier, "type": kind, "system": system, "title": identifier,
                "reason_before": "실행 전에 기록한 확인 목적", "depends_on": list(dependencies)}

    async def plan(self, action, **kwargs):
        return json.loads(await self.tool.manage_analysis_plan(action, __user__=self.user.model_dump(),
            __request__=self.request, __metadata__=self.metadata, __event_emitter__=self.emit, **kwargs))

    async def create(self, comparison=True):
        steps = [self.step("ems")]
        if comparison:
            steps.append(self.step("compare", "comparison", "EES", ["ems"]))
        steps.append(self.step("summary", "synthesis", "EES", [steps[-1]["id"]]))
        return await self.plan("create", title="조립 2라인 분석", steps=steps)

    async def execute(self, step_id="ems", system="EMS"):
        return json.loads(await self.tool.consult_specialists(
            tasks=[{"step_id": step_id, "system": system, "question": "sample_a의 정비 이력 확인"}],
            __user__=self.user.model_dump(), __request__=self.request,
            __metadata__=self.metadata, __event_emitter__=self.emit))

    async def compare(self):
        path = PATH.with_name("demo_data_tool.py")
        spec = importlib.util.spec_from_file_location("ees_workflow_comparison_tests", path)
        comparison = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(comparison)
        tool = comparison.Tools()
        tool.valves.ees_model_id = "existing-ees"
        with patch.object(comparison, "PANEL_SCRIPT", module.PANEL_SCRIPT):
            return await tool.compare_demo_data(step_id="compare", __user__=self.user.model_dump(),
                __request__=self.request, __metadata__=self.metadata, __event_emitter__=self.emit)

    def reviews(self):
        return [{"step_id": step["id"], "result_summary": "실제 반환된 자료를 확인함",
                 "judgment_after": "운영 원인은 아직 확정하지 않음", "uncertainty": "합성 자료 범위"}
                for step in self.request.state.ees_analysis_plan["snapshot"]["steps"]
                if step["type"] != "synthesis"]

    async def finish(self):
        return await self.plan("finish", reviews=self.reviews(), conclusion="합성 자료의 확인된 차이",
                               next_action="관련 조건을 추가 검증", limitations="실제 운영 원인은 미확정")

    async def test_plan_required_and_invalid_steps_cannot_claim_or_run_work(self):
        self.assertEqual((await self.execute())["error"]["code"], "plan_required")
        self.assertEqual((await self.compare())["error"]["code"], "plan_required")
        for patch_value in ({"status": "completed"}, {"depends_on": ["future"]}, {"system": []}):
            steps = [self.step("ems"), self.step("summary", "synthesis", "EES")]
            steps[0].update(patch_value)
            invalid = await self.plan("create", title="검사", steps=steps)
            self.assertEqual(invalid["error"]["code"], "invalid_plan")
        excessive = [self.step(f"ems{i}") for i in range(3)] + [self.step("summary", "synthesis", "EES")]
        self.assertEqual((await self.plan("create", title="검사", steps=excessive))["error"]["code"], "invalid_plan")
        self.assertFalse(hasattr(self.request.state, "ees_analysis_plan"))
        self.assertEqual(self.calls, [])

    async def test_complete_plan_uses_real_dependencies_and_public_reviews_without_rewriting_reason(self):
        with patch.object(module, "PANEL_SCRIPT", "/* fixed panel */"):
            created = await self.create()
            self.assertTrue(created["ok"])
            self.assertEqual((await self.compare())["error"]["code"], "step_not_ready")
            self.assertEqual((await self.plan("finish", conclusion="fake", next_action="fake"))["error"]["code"], "plan_unfinished")
            specialist = await self.execute()
            self.assertTrue(specialist["ok"])
            self.assertEqual((await self.execute())["error"]["code"], "step_not_ready")
            comparison = await self.compare()
            self.assertEqual(comparison["summary"]["total_events"], 15)
            state = self.request.state.ees_analysis_plan["snapshot"]
            self.assertEqual(state["phase"], "awaiting_summary")
            self.assertEqual(state["steps"][-1]["status"], "pending")
            self.assertTrue((await self.finish())["ok"])
            state = self.request.state.ees_analysis_plan["snapshot"]
            self.assertEqual([step["status"] for step in state["steps"]], ["completed"] * 3)
            self.assertTrue(all(step["reason_before"] == "실행 전에 기록한 확인 목적" for step in state["steps"]))
            self.assertEqual(len(state["steps"][-1]["call_ids"]), 2)
            self.assertEqual(state["steps"][0]["call_ids"], [specialist["results"][0]["call_id"]])
            events = self.panel_updates(include_plans=True)
        plans = [event for event in events if event["kind"] == "plan"]
        self.assertEqual([event["seq"] for event in plans], list(range(1, len(plans) + 1)))
        self.assertEqual(plans[0]["phase"], "planned")
        self.assertTrue(all(step["status"] == "pending" for step in plans[0]["steps"]))
        self.assertEqual(plans[-1]["phase"], "completed")
        self.assertNotIn("private reasoning", json.dumps(plans))
        for event in events:
            if event["kind"] != "plan":
                self.assertEqual(event["plan_id"], created["plan_id"])
                self.assertIn(event["step_id"], ("ems", "compare"))
        self.assertEqual((await self.plan("create", title="reset", steps=[]))["error"]["code"], "plan_exists")
        self.assertEqual((await self.plan("update", reviews=[]))["error"]["code"], "plan_closed")

    async def test_update_adds_real_followup_before_synthesis_and_cannot_forge_review_status(self):
        await self.create(comparison=False)
        premature = [{"step_id": "ems", "result_summary": "fake", "judgment_after": "fake", "uncertainty": ""}]
        self.assertEqual((await self.plan("update", reviews=premature))["error"]["code"], "step_not_reviewable")
        await self.execute()
        reviews = self.reviews()
        reviews[0]["status"] = "failed"
        self.assertEqual((await self.plan("update", reviews=reviews))["error"]["code"], "invalid_reviews")
        added = await self.plan("update", steps=[self.step("ems_more", dependencies=["ems"])],
                                change_reason="정비 회신에 없는 운전 재개 조건 확인")
        self.assertTrue(added["ok"])
        state = self.request.state.ees_analysis_plan["snapshot"]
        self.assertEqual([step["id"] for step in state["steps"]], ["ems", "ems_more", "summary"])
        self.assertEqual(state["steps"][-1]["depends_on"], ["ems", "ems_more"])
        self.assertEqual(state["changes"], ["정비 회신에 없는 운전 재개 조건 확인"])
        self.assertEqual((await self.finish())["error"]["code"], "step_not_reviewable")
        result = await self.execute("ems_more")
        self.assertEqual(result["results"][0]["request"]["kind"], "followup")
        self.assertTrue((await self.finish())["ok"])

    async def test_plan_identity_and_parallel_duplicate_step_do_not_bypass_execution_budget(self):
        await self.create(comparison=False)
        results = await asyncio.gather(self.execute(), self.execute())
        self.assertEqual(sum(result["ok"] for result in results), 1)
        self.assertEqual(len(self.calls), 1)
        original = dict(self.metadata)
        self.metadata["message_id"] = "another-message"
        self.assertEqual((await self.execute())["error"]["code"], "plan_required")
        self.assertEqual((await self.compare())["error"]["code"], "plan_required")
        self.metadata = original
        self.assertEqual(self.request.state.ees_consultation_budget["total"], 1)

    async def test_partial_failure_requires_visible_limits_and_keeps_real_failed_state(self):
        await self.create(comparison=False)
        self.runtime.check_access.side_effect = PermissionError("DO-NOT-RETURN")
        self.assertFalse((await self.execute())["ok"])
        state = self.request.state.ees_analysis_plan["snapshot"]
        self.assertEqual(state["steps"][0]["status"], "failed")
        result = await self.plan("finish", reviews=self.reviews(), conclusion="자료 확보 실패", next_action="접근 확인")
        self.assertEqual(result["error"]["code"], "limitations_required")
        self.assertTrue((await self.finish())["ok"])
        state = self.request.state.ees_analysis_plan["snapshot"]
        self.assertEqual(state["phase"], "partial")
        self.assertEqual(state["steps"][0]["status"], "failed")
        self.assertNotIn("DO-NOT-RETURN", json.dumps(state))

    async def test_plan_cancellation_and_scope_mismatch_never_become_completed(self):
        await self.create(comparison=False)
        async def mismatched(response, ctx):
            result = json.loads(await ctx["metadata"]["tools"]["read_demo_data"]["callable"](dataset="sample_b"))
            self.assertEqual(result["error"]["code"], "plan_dataset_mismatch")
            ctx["assistant_message"] = {"content": "다른 자료로 요청하여 조회하지 못함"}
        self.runtime.process_response = mismatched
        result = await self.execute()
        self.assertEqual(result["results"][0]["status"], "partial")
        self.assertEqual(self.data_calls, [])
        self.request = request()
        await self.create(comparison=False)
        entered = asyncio.Event()
        async def waiting(response, ctx):
            entered.set()
            await asyncio.Event().wait()
        self.runtime.process_response = waiting
        job = asyncio.create_task(self.execute())
        await entered.wait()
        self.assertEqual((await self.plan("update", reviews=[]))["error"]["code"], "plan_busy")
        job.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await job
        self.assertEqual(self.request.state.ees_analysis_plan["snapshot"]["steps"][0]["status"], "cancelled")
        self.assertEqual(self.request.state.ees_analysis_plan["snapshot"]["steps"][-1]["status"], "pending")


WHEEL = Path(os.environ.get("EES_TEST_UPSTREAM_WHEEL", "/tmp/ees-upstream-verification/open_webui-0.11.3-py3-none-any.whl"))


@unittest.skipUnless(WHEEL.is_file(), "Pinned 0.11.3 wheel is not present; runtime compatibility is a separate check")
class PinnedWebUILoopTests(unittest.IsolatedAsyncioTestCase):
    """Execute the wheel's unmodified streaming loop with fake external effects."""

    setUp = SpecialistsTests.setUp
    emit = SpecialistsTests.emit
    payload = SpecialistsTests.payload
    generate = SpecialistsTests.generate
    response = SpecialistsTests.response
    consult = SpecialistsTests.consult

    def load_wheel_loop(self):
        with zipfile.ZipFile(WHEEL) as wheel:
            source = wheel.read("open_webui/utils/middleware.py").decode()
            tool_source = wheel.read("open_webui/utils/tools.py").decode()
        tree = ast.parse(source)
        functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and node.name in {"streaming_chat_response_handler", "process_chat_response"}]
        self.assertEqual(len(functions), 2)

        async def nothing(*args, **kwargs):
            return None

        async def process_tool(request, name, result, tool_type, direct, metadata, user):
            return result, None, None

        def replay(output, **kwargs):
            return [{"role": "tool", "tool_call_id": i["call_id"],
                     "content": "".join(p.get("text", "") for p in i.get("output", []))}
                    for i in output if i.get("type") == "function_call_output"]

        namespace = {
            "asyncio": asyncio, "ast": ast, "re": re, "time": time, "uuid4": uuid4,
            "log": logging.getLogger("ees.pinned.loop.test"), "JSONCodec": json,
            "StreamingResponse": StreamingResponse, "UserModel": FakeUser,
            "Config": self.runtime.Config, "FilterContext": object,
            "ENABLE_PLUGINS": False, "ENABLE_RESPONSES_API_STATEFUL": False,
            "ENABLE_API_OUTLET_FILTERS": False, "ENABLE_CHAT_RESPONSE_BASE64_IMAGE_URL_CONVERSION": False,
            "CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS": 10, "CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE": 1,
            "DEFAULT_REASONING_TAGS": [("<think>", "</think>")], "DEFAULT_SOLUTION_TAGS": [],
            "is_saved_chat_id": lambda chat_id: bool(chat_id),
            "get_system_oauth_token": nothing, "outlet_filter_handler": nothing,
            "background_tasks_handler": nothing, "clear_response_stream": nothing,
            "publish_chat_finished_event": nothing, "terminal_event_handler": nothing,
            "process_tool_result": process_tool,
            "get_last_assistant_message": lambda messages: "",
            "get_last_user_message": lambda messages: next((m["content"] for m in reversed(messages) if m["role"] == "user"), ""),
            "get_system_message": lambda messages: next((m for m in messages if m["role"] == "system"), None),
            "get_content_from_message": lambda message: message.get("content", ""),
            "get_reasoning_format": lambda model: "deepseek",
            "get_reasoning_details": lambda obj: None,
            "output_id": lambda prefix: prefix + str(uuid4()),
            "get_output_text": module._visible_text,
            "get_response_completion_event_data": lambda data: data,
            "_split_tool_calls": lambda calls: calls,
            "stage_ask_user_tool_calls": lambda *args: (False, False),
            "build_terminal_file_tool_result": lambda *args: None,
            "tool_result_content": lambda result: result if isinstance(result, str) else json.dumps(result),
            "_is_tool_result_error": lambda result: False,
            "convert_output_to_messages": replay,
            "normalize_messages_for_model": lambda form: form,
        }
        tool_functions = [node for node in ast.parse(tool_source).body
                          if isinstance(node, ast.AsyncFunctionDef) and node.name in {
                              "get_async_tool_function_and_apply_extra_params", "get_updated_tool_function"}]
        namespace.update({"inspect": inspect, "get_type_hints": get_type_hints, "get_args": get_args,
                          "partial": partial, "update_wrapper": update_wrapper, "Callable": Callable,
                          "Awaitable": Awaitable})
        # This real upstream rebinder must not unwrap the execution budget guard.
        exec(compile(ast.Module(body=tool_functions, type_ignores=[]), "pinned-0.11.3/tools.py", "exec"), namespace)
        exec(compile(ast.Module(body=functions, type_ignores=[]), "pinned-0.11.3/middleware.py", "exec"), namespace)
        return namespace

    async def test_runtime_import_names_exist_in_fixed_wheel(self):
        with zipfile.ZipFile(WHEEL) as wheel:
            for node in ast.walk(ast.parse(PATH.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("open_webui."):
                    continue
                source = ast.parse(wheel.read(node.module.replace(".", "/") + ".py").decode())
                bindings = {item.id for item in ast.walk(source) if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)}
                bindings.update(item.name for item in source.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
                for item in ast.walk(source):
                    if isinstance(item, (ast.Import, ast.ImportFrom)):
                        bindings.update(alias.asname or alias.name.split(".")[0] for alias in item.names)
                for alias in node.names:
                    self.assertIn(alias.name, bindings, f"{node.module}.{alias.name}")

    async def test_actual_wheel_native_loop_calls_data_then_llm_continuation(self):
        namespace = self.load_wheel_loop()
        provider_calls = []

        async def provider(child, form, user, **kwargs):
            provider_calls.append(copy.deepcopy({"model": form["model"], "messages": form["messages"]}))
            if len(provider_calls) == 1:
                return stream([tool_chunk()])
            self.assertEqual(user.id, "user-one")
            self.assertTrue(kwargs.get("bypass_system_prompt"))
            self.assertIn("EMS-001", form["messages"][-1]["content"])
            return stream([answer_chunk()])

        namespace["generate_chat_completion"] = provider
        self.runtime.generate = provider
        self.runtime.process_response = namespace["process_chat_response"]
        result = await self.consult()
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(provider_calls), 2)
        self.assertEqual(len(self.data_calls), 1)
        self.assertIn("EMS-001", result["results"][0]["analysis"])
        self.assertEqual(result["results"][0]["data_calls"], 1)

    async def test_actual_wheel_parallel_tool_batch_stops_at_three_executions(self):
        namespace = self.load_wheel_loop()
        providers = []
        async def provider(child, form, user, **kwargs):
            providers.append(form)
            return stream([tool_chunk(5)]) if len(providers) == 1 else stream([answer_chunk()])
        namespace["generate_chat_completion"] = provider
        self.runtime.generate = provider
        self.runtime.process_response = namespace["process_chat_response"]
        result = (await self.consult())["results"][0]
        self.assertEqual(len(self.data_calls), 3)
        self.assertEqual(result["data_calls"], 3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["error"], "data_call_limit")


if __name__ == "__main__":
    unittest.main()
