"""Bounded Native model adapter: real payload builder, synthetic model transport."""

from copy import deepcopy
import ast
import collections.abc
import os
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from typing import Callable
from zipfile import ZipFile

from starlette.requests import Request
from pydantic import BaseModel, ConfigDict


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ModuleType("ees_model_test")
PACKAGE.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[PACKAGE.__name__] = PACKAGE
subject = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_model")


class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = SimpleNamespace(id="alice", role="user", token="never-forward-this")
        self.service = SimpleNamespace(_user=AsyncMock(return_value=self.user))
        self.app = SimpleNamespace(state=SimpleNamespace(MODELS={"permitted": {"id": "permitted"}},
                                  OPENAI_MODELS={"permitted": {"id": "permitted", "urlIdx": 0}}))
        self.adapter = subject.NativeModelAdapter(self.service, self.app)
        self.output = {"claims": [{"job_id": "docs", "call_id": "read", "path": ["data", "title"], "value": "기준"}], "limitations": []}
        self.runtime = SimpleNamespace(Request=Request, bypass_admin=False, bypass_models=False,
                                       Models=SimpleNamespace(get_model_by_id=AsyncMock(return_value=SimpleNamespace(id="permitted"))),
                                       connection=AsyncMock(return_value=("https://synthetic.test", "synthetic-only", {"auth_type": "bearer"})),
                                       check_access=AsyncMock(), generate=AsyncMock(return_value={"choices": [{"message": {
                                           "content": json.dumps(self.output), "reasoning_content": "never-save-this"}}]}))
        self.node = {"id": "summary", "execution": {"kind": "ai", "model_id": "permitted",
                    "evidence": [{"job_id": "docs", "call_id": "read"}],
                    "completion": {"required_claims": [{"job_id": "docs", "call_id": "read", "path": ["data", "title"]}]}}}
        self.context = {"run_id": "run-a", "limits": {"max_model_calls": 1},
                        "instructions": ["범위와 미확인을 구분"], "skills": [{"id": "current-skill", "body": "현재 허용된 지침"}]}
        self.results = {"docs": {"read": {"status": "succeeded", "completeness": "complete", "data": {"title": "기준"}}},
                        "unrelated": {"secret": {"status": "succeeded", "data": "other-user-material"}}}
        self.patcher = patch.object(subject, "_runtime", return_value=self.runtime)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def invoke(self):
        return await self.adapter.invoke(self.user, self.node, self.context, self.results,
                                         {"arbitrary_input": "never-forward-input"})

    async def test_scoped_context_current_identity_and_reserved_request(self):
        result = await self.invoke()
        self.service._user.assert_awaited_once_with(self.user)
        self.runtime.check_access.assert_awaited_once()
        request, form, current = self.runtime.generate.await_args.args
        self.assertIs(current, self.user)
        self.assertEqual(list(request.headers), [])
        self.assertFalse(hasattr(request.state, "token"))
        self.assertIs(request.state.ees_workflow_headless, True)
        self.assertNotIn("ees_workflow_headless", form)
        self.assertEqual(form["tools"], [])
        self.assertEqual(self.runtime.generate.await_args.kwargs, {"bypass_system_prompt": True})
        self.assertEqual(form["max_tokens"], form["max_completion_tokens"])
        self.assertEqual(form["metadata"]["chat_id"], "")
        body = form["messages"][1]["content"]
        self.assertIn("현재 허용된 지침", body)
        self.assertIn("기준", body)
        self.assertEqual(json.loads(body)["required_claims"], self.node["execution"]["completion"]["required_claims"])
        for value in ("never-forward-this", "other-user-material", "never-forward-input"):
            self.assertNotIn(value, body)
        self.assertEqual(result["data"], self.output)
        self.assertNotIn("never-save-this", json.dumps(result))

    async def test_current_model_acl_revocation_stops_generation(self):
        self.runtime.check_access.side_effect = RuntimeError("sensitive-provider-response")
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "model_unavailable")
        self.assertNotIn("sensitive", str(error.exception))
        self.runtime.generate.assert_not_awaited()

    async def test_only_successful_declared_sources_and_size_budget(self):
        self.results["docs"]["read"]["status"] = "unknown"
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "evidence_required")
        self.runtime.generate.assert_not_awaited()
        self.results["docs"]["read"]["status"] = "succeeded"
        self.results["docs"]["read"]["data"] = "a" * 100_000
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "model_context_limit")

    async def test_tool_calls_free_prose_and_extra_keys_never_become_success(self):
        for message in ({"content": "done"}, {"content": json.dumps({**self.output, "summary": "CI passed"})},
                        {"content": json.dumps(self.output), "tool_calls": [{"function": {"name": "merge"}}]}):
            with self.subTest(message=message):
                self.runtime.generate.return_value = {"choices": [{"message": message}]}
                with self.assertRaises(subject.WorkflowError) as error:
                    await self.invoke()
                self.assertEqual(error.exception.code, "model_result_invalid")

    async def test_browser_or_code_models_are_explicitly_unsupported(self):
        for field in ("pipe", "arena", "direct", "pipeline"):
            self.app.state.MODELS["permitted"] = {"id": "permitted", field: True}
            with self.assertRaises(subject.WorkflowError) as error:
                await self.invoke()
            self.assertEqual(error.exception.code, "headless_model_unsupported")
        self.runtime.generate.assert_not_awaited()

    async def test_base_pipeline_and_session_auth_are_rejected_before_model_call(self):
        self.app.state.OPENAI_MODELS["permitted"]["pipeline"] = True
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "headless_model_unsupported")
        self.app.state.OPENAI_MODELS["permitted"].pop("pipeline")
        for auth in ("session", "system_oauth"):
            self.runtime.connection.return_value = ("https://synthetic.test", "", {"auth_type": auth})
            with self.assertRaises(subject.WorkflowError) as error:
                await self.invoke()
            self.assertEqual(error.exception.code, "headless_model_unsupported")
        self.runtime.generate.assert_not_awaited()

    async def test_context_model_endpoint_and_nested_overrides_are_rejected_for_both_providers(self):
        attacks = {"previous_response_id": "resp_foreign", "conversation": "conversation_foreign",
                   "prompt": {"id": "pmpt_unpinned"}, "input": "foreign context", "instructions": "other policy",
                   "messages": [{"role": "system", "content": "other policy"}], "model": "unapproved-model",
                   "base_url": "https://other.invalid", "url": "https://other.invalid", "endpoint": "https://other.invalid",
                   "tools": [{"type": "web_search"}], "tool_choice": "required", "functions": [{"name": "unapproved"}],
                   "extra_body": {"previous_response_id": "resp_foreign"}, "extra_headers": {"Authorization": "fake"},
                   "options": {"system": "other policy"}, "unknown_future_field": {"context": "other"}}
        for provider in ("openai", "ollama"):
            self.app.state.MODELS["permitted"]["owned_by"] = provider
            for key, value in attacks.items():
                for nested in (False, True):
                    params = {"custom_params": {key: json.dumps(value)}} if nested else {key: value}
                    self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params=params)
                    with self.subTest(provider=provider, key=key, nested=nested):
                        with self.assertRaises(subject.WorkflowError) as error:
                            await self.invoke()
                        self.assertEqual(error.exception.code, "headless_model_unsupported")
                        self.assertEqual(self.runtime.Models.get_model_by_id.return_value.params, params)
        self.runtime.generate.assert_not_awaited()

    async def test_supported_sampling_limits_and_reasoning_preserve_preset(self):
        params = {"system": "A preset prompt that Native must bypass", "temperature": .2,
                  "max_tokens": 12000, "stream_response": True,
                  "custom_params": {"top_p": "0.9", "reasoning": '{"effort":"high"}',
                                    "chat_template_kwargs": '{"enable_thinking":true}', "stop": '["STOP"]'}}
        self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params=params)
        before = deepcopy(params)
        await self.invoke()
        self.assertEqual(params, before)
        self.assertEqual(self.runtime.generate.await_args.kwargs, {"bypass_system_prompt": True})
        form = self.runtime.generate.await_args.args[1]
        self.assertEqual(form["max_tokens"], 3000)
        self.assertEqual(form["max_completion_tokens"], 3000)
        for custom in ({"system": "other policy"}, {"reasoning": {"encrypted_content": "foreign context"}},
                       {"chat_template_kwargs": {"system": "other policy"}}):
            self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params={"custom_params": custom})
            with self.assertRaises(subject.WorkflowError) as error:
                await self.invoke()
            self.assertEqual(error.exception.code, "headless_model_unsupported")

    async def test_exact_native_parameter_transforms_cannot_add_hidden_context(self):
        wheel = Path(os.environ.get("EES_TEST_UPSTREAM_WHEEL", ROOT / "dist/upstream/open_webui-0.11.3-py3-none-any.whl"))
        if not wheel.is_file():
            if os.environ.get("EES_REQUIRE_ASSET_NATIVE") == "1":
                self.fail("Pinned Native wheel unavailable")
            self.skipTest("Pinned Native wheel unavailable")
        namespace = {"Callable": Callable, "JSONCodec": json, "collections": collections}
        with ZipFile(wheel) as archive:
            for name, selected in (
                    ("open_webui/utils/misc.py", {"deep_update"}),
                    ("open_webui/utils/payload.py", {"remove_open_webui_params", "apply_model_params_to_body",
                     "apply_model_params_to_body_openai", "apply_model_params_to_body_ollama"}),
                    ("open_webui/routers/openai.py", {"convert_to_responses_payload"})):
                tree = ast.parse(archive.read(name).decode("utf-8"))
                nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in selected]
                self.assertEqual({node.name for node in nodes}, selected)
                exec(compile(ast.Module(body=nodes, type_ignores=[]), name, "exec"), namespace)
        await self.invoke()
        form = self.runtime.generate.await_args.args[1]
        malicious = {"custom_params": {"previous_response_id": "resp_other_conversation", "prompt": {"id": "pmpt_unpinned"}}}
        # Show the concrete pinned Native behavior that the adapter must guard:
        # bypass_system_prompt does not suppress provider context parameters.
        unsafe = namespace["apply_model_params_to_body_openai"](deepcopy(malicious), deepcopy(form))
        unsafe = namespace["convert_to_responses_payload"](unsafe)
        self.assertEqual(unsafe["previous_response_id"], "resp_other_conversation")
        self.assertEqual(unsafe["prompt"], {"id": "pmpt_unpinned"})
        self.runtime.generate.reset_mock()
        self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params=malicious)
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "headless_model_unsupported")
        self.runtime.generate.assert_not_awaited()
        safe = {"system": "unrelated preset", "temperature": .3, "max_tokens": 12000,
                "custom_params": {"top_p": "0.8", "reasoning": {"effort": "high"}}}
        subject._headless_parameters(SimpleNamespace(params=safe))
        transformed = namespace["apply_model_params_to_body_openai"](deepcopy(safe), deepcopy(form))
        transformed = namespace["convert_to_responses_payload"](transformed)
        self.assertNotIn("previous_response_id", transformed)
        self.assertNotIn("prompt", transformed)
        self.assertEqual(transformed["instructions"], subject.SYSTEM)
        self.assertEqual(transformed["max_output_tokens"], 3000)
        self.assertEqual(transformed["temperature"], .3)
        ollama = namespace["apply_model_params_to_body_ollama"](deepcopy(safe), {"messages": [], "options": {"num_predict": 3000}})
        self.assertEqual(ollama["options"]["num_predict"], 3000)
        self.assertNotIn("system", ollama["options"])
        self.assertNotIn("previous_response_id", ollama["options"])

    async def test_pinned_provider_routes_reject_preset_change_at_parameter_application(self):
        wheel = Path(os.environ.get("EES_TEST_UPSTREAM_WHEEL", ROOT / "dist/upstream/open_webui-0.11.3-py3-none-any.whl"))
        if not wheel.is_file():
            if os.environ.get("EES_REQUIRE_ASSET_NATIVE") == "1":
                self.fail("Pinned Native wheel unavailable")
            self.skipTest("Pinned Native wheel unavailable")
        spec = importlib.util.spec_from_file_location("ees_model_guard_builder", ROOT / "scripts/build_ees_webui.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        native_functions = {"Callable": Callable, "JSONCodec": json, "collections": collections}
        with ZipFile(wheel) as archive:
            for name, selected in (
                    ("open_webui/utils/misc.py", {"deep_update"}),
                    ("open_webui/utils/payload.py", {"remove_open_webui_params", "apply_model_params_to_body",
                     "apply_model_params_to_body_openai", "apply_model_params_to_body_ollama"}),
                    ("open_webui/routers/openai.py", {"convert_to_responses_payload"})):
                tree = ast.parse(archive.read(name).decode("utf-8"))
                nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in selected]
                exec(compile(ast.Module(body=nodes, type_ignores=[]), name, "exec"), native_functions)
            sources = {provider: archive.read("open_webui/routers/" + provider + ".py").decode("utf-8") for provider in ("openai", "ollama")}

        class Form(BaseModel):
            model_config = ConfigDict(extra="allow")
            model: str

        class ParameterApplied(Exception):
            pass

        package = ModuleType("open_webui")
        package.__path__ = []
        with patch.dict(sys.modules, {"open_webui": package, "open_webui.ees_workflow_model": subject}):
            for provider, source in sources.items():
                filename = "open_webui/routers/" + provider + ".py"
                # This is the actual builder's pinned route mutation, then the
                # actual full route body. Only unrelated serving surroundings
                # and the external transport endpoint are isolated.
                patched = builder._guard_headless_model_parameters(source, filename)
                route = next(node for node in ast.parse(patched).body if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_chat_completion")
                route.decorator_list = []
                applied, current_params = [], {}
                async def lookup(model_id):
                    return SimpleNamespace(base_model_id=None, params=SimpleNamespace(model_dump=lambda: deepcopy(current_params)))
                native_apply = native_functions["apply_model_params_to_body_" + provider]
                def apply(params, payload):
                    applied.append(native_apply(params, payload))
                    raise ParameterApplied()
                route_globals = {"Request": Request, "Depends": lambda value: None, "get_verified_user": lambda: None,
                                 "Config": SimpleNamespace(get=AsyncMock(return_value=True)), "Models": SimpleNamespace(get_model_by_id=lookup),
                                 "BYPASS_MODEL_ACCESS_CONTROL": False, "BaseModel": BaseModel, "GenerateChatCompletionForm": Form,
                                 "apply_model_params_to_body_" + provider: apply}
                exec(compile(ast.Module(body=[route], type_ignores=[]), filename, "exec"), route_globals)
                native_route = route_globals["generate_chat_completion"]
                async def dispatch(request, form, user, bypass_system_prompt=False):
                    request.state.bypass_system_prompt = bypass_system_prompt
                    try:
                        await native_route(request=request, form_data=deepcopy(form), user=user)
                    except ParameterApplied:
                        return {"choices": [{"message": {"content": json.dumps(self.output)}}]}
                    self.fail("Native route did not reach guarded parameter application")
                self.runtime.generate.side_effect = dispatch
                self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params={})
                self.app.state.MODELS["permitted"]["owned_by"] = provider
                for attack in ({"custom_params": {"previous_response_id": "resp_changed_after_preflight"}},
                               {"custom_params": {"extra_body": {"instructions": "changed context"}}}):
                    current_params = deepcopy(attack)
                    with self.subTest(provider=provider, params=attack):
                        with self.assertRaises(subject.WorkflowError) as error:
                            await self.invoke()
                        self.assertEqual(error.exception.code, "headless_model_unsupported")
                        self.assertEqual(applied, [])
                        self.assertEqual(current_params, attack)
                # Safe settings changed after preflight still work and cannot
                # override the job's already-supplied generation cap.
                current_params = {"temperature": .4, "max_tokens": 15000}
                await self.invoke()
                self.assertEqual(len(applied), 1)
                settings = applied[0]["options"] if provider == "ollama" else applied[0]
                self.assertEqual(settings["temperature"], .4)
                self.assertEqual(settings["num_predict" if provider == "ollama" else "max_tokens"], 3000)
                for cap_params in ({"temperature": .4, "max_output_tokens": 999999},
                                   {"temperature": .4, "custom_params": {"max_output_tokens": "999999"}}):
                    current_params = deepcopy(cap_params)
                    await self.invoke()
                    safe_body = applied[-1]
                    settings = safe_body["options"] if provider == "ollama" else safe_body
                    self.assertNotIn("max_output_tokens", settings)
                    self.assertEqual(settings["num_predict" if provider == "ollama" else "max_tokens"], 3000)
                    self.assertEqual(current_params, cap_params, "Native preset must remain unchanged")
                    if provider == "openai":
                        responses = native_functions["convert_to_responses_payload"](deepcopy(safe_body))
                        self.assertEqual(responses["max_output_tokens"], 3000)
                # No browser/client JSON flag activates this server-only path.
                current_params = {"custom_params": {"previous_response_id": "legacy-chat-value"}}
                ordinary = Request({"type": "http", "headers": [], "app": self.app})
                with self.assertRaises(ParameterApplied):
                    await native_route(request=ordinary, form_data={"model": "permitted", "messages": [], "ees_workflow_headless": True}, user=self.user)
                ordinary_settings = applied[-1]["options"] if provider == "ollama" else applied[-1]
                self.assertEqual(ordinary_settings["previous_response_id"], "legacy-chat-value")

    async def test_initial_chat_cap_field_remains_unsupported_and_responses_is_supported(self):
        for params in ({"max_output_tokens": 999999}, {"custom_params": {"max_output_tokens": "999999"}}):
            self.runtime.Models.get_model_by_id.return_value = SimpleNamespace(id="permitted", params=params)
            with self.assertRaises(subject.WorkflowError) as error:
                await self.invoke()
            self.assertEqual(error.exception.code, "headless_model_unsupported")
        self.runtime.generate.assert_not_awaited()
        self.runtime.connection.return_value = ("https://synthetic.test", "synthetic-only", {"api_type": "responses"})
        await self.invoke()
        self.runtime.generate.assert_awaited_once()

    async def test_no_model_budget_never_calls_native_path(self):
        self.context["limits"]["max_model_calls"] = 0
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "model_limit")
        self.runtime.generate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
