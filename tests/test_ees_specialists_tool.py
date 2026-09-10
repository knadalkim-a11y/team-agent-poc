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
        return json.loads(await self.tool.consult_specialists(**args))

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
        self.assertTrue((await self.consult(("EMS", "APC", "FDC")))["ok"])
        fourth = await self.consult(("APC",))
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
        self.assertEqual(len(self.calls), 2)
        self.request = request()
        self.assertTrue((await self.consult())["ok"])

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
        async def slow(response, ctx):
            await self.response(response, ctx)
            if ctx["metadata"]["model_id"] == "ees_demo_apc":
                await asyncio.Event().wait()
        self.runtime.process_response = slow
        # Bypass only Pydantic assignment validation for a fast synthetic timeout.
        self.tool.valves.specialist_timeout_seconds = 0.02
        result = await self.consult(("EMS", "APC"))
        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual([r["status"] for r in result["results"]], ["completed", "partial"])
        self.assertEqual(result["results"][1]["error"], "timeout")
        self.assertEqual(len(result["results"][1]["evidence"]), 1)

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
        self.assertEqual(self.events[-1]["data"]["phase"], "cancelled")

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
            for node in ast.walk(ast.parse(PATH.read_text())):
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
