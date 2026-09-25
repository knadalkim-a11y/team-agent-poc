"""Pinned Native model dispatch/payload tests; no provider or real user calls.

The generator, OpenAI route body and payload conversion functions execute the
unchanged upstream wheel source. Model rows, ACL decisions, connection config
and HTTP transport are synthetic. This is payload/dispatch integration evidence,
not a full app, Native model DB/ACL persistence or in-house model quality test.
"""

import ast
import collections
from copy import deepcopy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
from typing import Callable
import unittest
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from fastapi import Depends, HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ModuleType("ees_model_native_test")
PACKAGE.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[PACKAGE.__name__] = PACKAGE
subject = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_model")


class NativePayloadTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("EES_TEST_UPSTREAM_WHEEL")
        wheel = Path(configured) if configured else ROOT / "dist/upstream/open_webui-0.11.3-py3-none-any.whl"
        if not wheel.is_file():
            if os.environ.get("EES_REQUIRE_MODEL_NATIVE") == "1":
                raise AssertionError("Required model payload gate needs EES_TEST_UPSTREAM_WHEEL")
            raise unittest.SkipTest("Pinned Native wheel is unavailable")
        builder = ast.parse((ROOT / "scripts/build_ees_webui.py").read_text(encoding="utf-8"))
        expected = next(ast.literal_eval(node.value) for node in builder.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "SOURCE_SHA256"
                                for target in node.targets))
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
            raise AssertionError("Payload integration requires unchanged pinned upstream wheel")
        with ZipFile(wheel) as archive:
            cls.sources = {name: archive.read(name).decode("utf-8") for name in (
                "open_webui/utils/chat.py", "open_webui/routers/openai.py",
                "open_webui/utils/payload.py", "open_webui/utils/misc.py",
                "open_webui/utils/model_ids.py")}
        cls.wheel = wheel

    def definitions(self, path, names, namespace):
        """Keep exact function bodies; route registration is outside this gate."""
        selected = [node for node in ast.parse(self.sources[path]).body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        self.assertEqual({node.name for node in selected}, set(names))
        for node in selected:
            node.decorator_list = []
        tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                               *selected], type_ignores=[])
        exec(compile(ast.fix_missing_locations(tree), f"{self.wheel}!/{path}#exact-definitions", "exec"), namespace)

    async def asyncSetUp(self):
        self.user = SimpleNamespace(id="payload-user", role="user")
        self.configured_params = {"system": "UNRELATED_NATIVE_PRESET",
                                  "custom_params": {"max_completion_tokens": "999999"}}
        self.api_config = {"auth_type": "bearer"}
        self.provider_url = "https://synthetic-model.example.test/v1"
        self.sent = []
        self.acl_calls = []
        self.output = {"claims": [], "limitations": []}
        self.models = SimpleNamespace(get_model_by_id=AsyncMock(side_effect=self.model_info))
        self.app = SimpleNamespace(state=SimpleNamespace(
            MODELS={"permitted": {"id": "permitted", "owned_by": "openai"}},
            OPENAI_MODELS={"permitted": {"id": "permitted", "urlIdx": 0}}))

        self.payload = {"JSONCodec": json, "Callable": Callable, "collections": collections}
        self.definitions("open_webui/utils/misc.py", {"deep_update", "add_or_update_system_message",
                         "update_message_content", "replace_system_message_content"}, self.payload)
        self.payload.update({
            "render_chat_variables": lambda value, *_args, **_kwargs: value,
            "render_user_variables": lambda value, *_args: value,
            "prompt_variables_template": lambda value, *_args: value,
            "prompt_template": AsyncMock(side_effect=lambda value, _user: value),
        })
        self.definitions("open_webui/utils/payload.py", {
            "resolve_system_prompt", "apply_system_prompt_to_body", "remove_open_webui_params",
            "apply_model_params_to_body", "apply_model_params_to_body_openai",
            "apply_model_params_to_body_ollama", "convert_payload_openai_to_ollama",
            "convert_messages_openai_to_ollama"}, self.payload)

        self.route = {**self.payload, "re": re, "Request": Request, "Depends": Depends,
                      "get_verified_user": lambda: None, "Models": self.models,
                      "Config": SimpleNamespace(get=AsyncMock(return_value=True)),
                      "BYPASS_MODEL_ACCESS_CONTROL": False,
                      "check_model_access": self.route_acl, "get_openai_connection": self.connection,
                      "get_headers_and_cookies": AsyncMock(return_value=({}, {})),
                      "get_session": AsyncMock(return_value=SimpleNamespace(request=self.transport)),
                      "cleanup_response": AsyncMock(), "get_client_timeout": lambda **_kwargs: 10,
                      "AIOHTTP_CLIENT_SESSION_SSL": True, "JSONCodec": json,
                      "HTTPException": HTTPException, "JSONResponse": JSONResponse,
                      "PlainTextResponse": PlainTextResponse, "StreamingResponse": StreamingResponse,
                      "log": logging.getLogger("ees_native_model_payload"),
                      "ERROR_MESSAGES": SimpleNamespace(SERVER_CONNECTION_ERROR="synthetic transport failure")}
        self.definitions("open_webui/utils/model_ids.py", {"strip_provider_model_prefix"}, self.route)
        self.definitions("open_webui/routers/openai.py", {
            "generate_chat_completion", "convert_to_responses_payload", "convert_responses_result",
            "is_openai_new_model", "openai_reasoning_model_handler"}, self.route)
        self.chat = {"Request": Request, "BYPASS_MODEL_ACCESS_CONTROL": False,
                     "check_model_access": self.generator_acl,
                     "generate_openai_chat_completion": self.route["generate_chat_completion"],
                     "log": logging.getLogger("ees_native_model_generator")}
        self.definitions("open_webui/utils/chat.py", {"generate_chat_completion"}, self.chat)
        self.runtime = SimpleNamespace(Request=Request, Models=self.models, bypass_models=False,
                                       bypass_admin=False, check_access=AsyncMock(),
                                       connection=self.connection, generate=self.chat["generate_chat_completion"])
        self.adapter = subject.NativeModelAdapter(SimpleNamespace(_user=AsyncMock(return_value=self.user)), self.app)
        self.node = {"execution": {"kind": "ai", "model_id": "permitted",
                                   "evidence": [{"job_id": "docs", "call_id": "read"}]}}
        self.results = {"docs": {"read": {"status": "succeeded", "completeness": "complete",
                                             "data": {"title": "합성 자료"}}}}
        self.context = {"run_id": "synthetic-run", "limits": {"model_calls": 1}, "instructions": ["범위 확인"]}

    def model_info(self, _identifier):
        return SimpleNamespace(id="permitted", base_model_id=None,
                               params=SimpleNamespace(model_dump=lambda: deepcopy(self.configured_params)))

    async def connection(self, _index):
        return self.provider_url, "synthetic-key", deepcopy(self.api_config)

    async def generator_acl(self, user, model):
        self.acl_calls.append(("generator", user.id, model["id"]))

    async def route_acl(self, user, model, bypass):
        self.acl_calls.append(("route", user.id, model.id, bypass))

    async def transport(self, **kwargs):
        self.sent.append({"url": kwargs["url"], "payload": json.loads(kwargs["data"])})
        content = json.dumps(self.output)
        result = ({"output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]}
                  if self.api_config.get("api_type") == "responses"
                  else {"choices": [{"message": {"content": content}}]})
        return SimpleNamespace(status=200, headers={"Content-Type": "application/json"},
                               json=AsyncMock(return_value=result))

    async def invoke(self):
        with patch.object(subject, "_runtime", return_value=self.runtime):
            return await self.adapter.invoke(self.user, self.node, self.context, self.results, {})

    async def test_native_generator_route_enforce_token_cap_and_suppress_preset(self):
        result = await self.invoke()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(len(self.sent), 1)
        payload = self.sent[0]["payload"]
        self.assertEqual(payload["max_tokens"], 3000)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual(payload["messages"][0]["content"], subject.SYSTEM)
        self.assertNotIn("UNRELATED_NATIVE_PRESET", json.dumps(payload))
        self.assertEqual(self.acl_calls, [("generator", "payload-user", "permitted"),
                                          ("route", "payload-user", "permitted", False)])

    async def test_suppression_assertion_has_native_default_path_control(self):
        request = Request({"type": "http", "app": self.app, "headers": [], "state": {}})
        form = {"model": "permitted", "stream": False, "max_tokens": 3000,
                "messages": [{"role": "system", "content": "JOB_POLICY"}, {"role": "user", "content": "data"}]}
        await self.chat["generate_chat_completion"](request, form, self.user)
        self.assertEqual(self.sent[0]["payload"]["messages"][0]["content"],
                         "UNRELATED_NATIVE_PRESET\nJOB_POLICY")

    async def test_responses_conversion_overwrites_configured_output_token_override(self):
        self.api_config["api_type"] = "responses"
        self.configured_params["custom_params"]["max_output_tokens"] = "999999"
        await self.invoke()
        payload = self.sent[0]["payload"]
        self.assertTrue(self.sent[0]["url"].endswith("/responses"))
        self.assertEqual(payload["max_output_tokens"], 3000)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["instructions"], subject.SYSTEM)

    async def test_chat_completion_cannot_forward_configured_output_token_override(self):
        self.configured_params["custom_params"]["max_output_tokens"] = "999999"
        try:
            await self.invoke()
        except subject.WorkflowError as error:
            self.assertEqual(error.code, "headless_model_unsupported")
            self.assertEqual(self.sent, [])
        else:
            payload = self.sent[0]["payload"]
            self.assertLessEqual(payload.get("max_output_tokens", 3000), 3000)

    async def test_ollama_native_conversion_and_saved_params_keep_num_predict_bound(self):
        captured = []

        async def transform(_request, form, _user, **kwargs):
            self.assertEqual(kwargs, {"bypass_system_prompt": True})
            payload = self.payload["convert_payload_openai_to_ollama"](form)
            params = {"num_predict": 999999, "max_tokens": 999999,
                      "custom_params": {"num_predict": "999999"}}
            payload = self.payload["apply_model_params_to_body_ollama"](params, payload)
            captured.append(payload)
            return {"choices": [{"message": {"content": json.dumps(self.output)}}]}

        self.app.state.MODELS["permitted"]["owned_by"] = "ollama"
        self.runtime.generate = transform
        await self.invoke()
        self.assertEqual(captured[0]["options"]["num_predict"], 3000)


if __name__ == "__main__":
    unittest.main()
