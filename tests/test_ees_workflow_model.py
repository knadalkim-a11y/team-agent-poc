"""Bounded Native model adapter: real payload builder, synthetic model transport."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request


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

    async def test_no_model_budget_never_calls_native_path(self):
        self.context["limits"]["max_model_calls"] = 0
        with self.assertRaises(subject.WorkflowError) as error:
            await self.invoke()
        self.assertEqual(error.exception.code, "model_limit")
        self.runtime.generate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
