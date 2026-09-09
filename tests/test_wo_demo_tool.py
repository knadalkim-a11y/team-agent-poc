"""WO demo Tool contracts with a synthetic browser callback.

No browser, LLM, EMS endpoint or production data is used. These tests cover
argument validation and the Python/execute-event boundary, not WebUI rendering.
"""

import ast
import asyncio
import importlib.util
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "agent-pack/skills/ems-work-order/scripts/wo_demo_tool.py"
SPEC = importlib.util.spec_from_file_location("ees_wo_demo_tests", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

METADATA = {"chat_id": "sample-chat"}
LIMITS = {
    "corporation": 100, "site": 100, "shop": 100, "line": 100,
    "process": 100, "query": 100, "equipment_id": 100, "title": 100,
    "type": 100, "priority": 100, "description": 2500,
}


class WODemoToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = module.Tools()
        self.events = []
        self.browser_result = {"ok": True, "revision": 3, "draft": {"title": "샘플 점검"}}

    async def browser(self, event):
        self.events.append(event)
        return self.browser_result

    def result(self, value):
        if isinstance(value, str):
            value = json.loads(value)
        self.assertIsInstance(value, dict)
        self.assertIs(type(value.get("ok")), bool)
        self.assertIs(value.get("demo"), True)
        return value

    def failure(self, value):
        data = self.result(value)
        self.assertIs(data["ok"], False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertIsInstance(data["error"].get("code"), str)
        self.assertTrue(data["error"]["code"])
        self.assertIsInstance(data["error"].get("message"), str)
        self.assertTrue(data["error"]["message"])
        return data

    def request(self):
        event = self.events[-1]
        self.assertEqual(event.get("type"), "execute")
        code = event["data"]["code"]
        self.assertIsInstance(code, str)
        match = re.search(r"\bconst\s+request\s*=\s*", code)
        self.assertIsNotNone(match)
        data, end = json.JSONDecoder().raw_decode(code[match.end():])
        self.assertEqual(code[match.end() + end:].lstrip()[0], ";")
        self.assertIsInstance(data, dict)
        return data, code[:match.end()] + code[match.end() + end:]

    async def view(self, **overrides):
        args = {"__event_call__": self.browser, "__metadata__": METADATA, **overrides}
        return await self.tool.wo_demo_view(**args)

    async def update(self, changes, revision=3, **overrides):
        args = {"__event_call__": self.browser, "__metadata__": METADATA, **overrides}
        return await self.tool.wo_demo_update(expected_revision=revision, changes=changes, **args)

    async def test_source_parses_and_view_reads_current_browser_snapshot(self):
        ast.parse(PATH.read_text(encoding="utf-8"))
        data = self.result(await self.view())
        self.assertTrue(data["ok"])
        self.assertEqual(data["revision"], 3)
        self.assertEqual(data["draft"]["title"], "샘플 점검")
        self.assertEqual(len(self.events), 1)
        request, _ = self.request()
        self.assertEqual(request["chat_id"], METADATA["chat_id"])

    async def test_update_keeps_untrusted_content_in_json_data(self):
        text = '사용자 입력 " ; globalThis.EES_TEST_INJECTION = true; //\n</script>\u2028'
        changes = {"description": text, "priority": "긴급"}
        data = self.result(await self.update(changes, revision=7))
        self.assertTrue(data["ok"])
        request, executable = self.request()
        self.assertEqual(request["chat_id"], METADATA["chat_id"])
        self.assertEqual(request["expected_revision"], 7)
        self.assertEqual(request["changes"], changes)
        self.assertNotIn("EES_TEST_INJECTION", executable)

    async def test_empty_unknown_nested_and_non_string_changes_never_reach_browser(self):
        invalid = [None, [], "title", {}, {"execute": "alert(1)"},
                   {"title": "allowed", "unknown": "extra"},
                   {"description": {"text": "nested"}}, {"title": ["nested"]},
                   {"priority": True}, {"query": 1}, {"title": None}]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.failure(await self.update(changes))
        self.assertEqual(self.events, [])

    async def test_allowed_fields_accept_limit_and_reject_one_character_over(self):
        for field, limit in LIMITS.items():
            with self.subTest(field=field):
                accepted = self.result(await self.update({field: "가" * limit}))
                self.assertTrue(accepted["ok"])
                request, _ = self.request()
                self.assertEqual(request["changes"], {field: "가" * limit})
                before = len(self.events)
                self.failure(await self.update({field: "가" * (limit + 1)}))
                self.assertEqual(len(self.events), before)

    async def test_revision_requires_nonnegative_integer_excluding_bool(self):
        for revision in [None, -1, True, False, 1.0, "1", [], {}]:
            with self.subTest(revision=revision):
                self.failure(await self.update({"title": "수정"}, revision=revision))
        self.assertEqual(self.events, [])
        self.assertTrue(self.result(await self.update({"title": "수정"}, revision=0))["ok"])

    async def test_missing_metadata_or_callback_fails_without_execution(self):
        for metadata in [None, [], "sample-chat", {}, {"chat_id": None},
                         {"chat_id": ""}, {"chat_id": 42}, {"chat_id": True}]:
            with self.subTest(metadata=metadata):
                self.failure(await self.view(__metadata__=metadata))
                self.failure(await self.update({"title": "수정"}, __metadata__=metadata))
        for callback in [None, 42]:
            with self.subTest(callback=callback):
                self.failure(await self.view(__event_call__=callback))
                self.failure(await self.update({"title": "수정"}, __event_call__=callback))
        self.assertEqual(self.events, [])

    async def test_distinct_chat_metadata_is_forwarded_per_call(self):
        for chat_id in ["sample-chat-a", "sample-chat-b"]:
            self.result(await self.view(__metadata__={"chat_id": chat_id}))
            request, _ = self.request()
            self.assertEqual(request["chat_id"], chat_id)

    async def test_malformed_browser_responses_do_not_claim_success_or_leak_details(self):
        marker = "SYNTHETIC_PRIVATE_TRANSPORT_DETAIL"
        for response in [None, [], "success", {}, {"ok": "true"}, {"ok": 1},
                         {"error": marker}]:
            with self.subTest(response=response):
                self.browser_result = response
                data = self.failure(await self.view())
                self.assertNotIn(marker, json.dumps(data))

    async def test_browser_conflict_is_preserved_and_demo_is_always_true(self):
        self.browser_result = {
            "ok": False, "demo": False, "revision": 4,
            "error": {"code": "revision_conflict", "message": "최신 화면을 다시 확인하세요."},
        }
        result = self.failure(await self.update({"title": "수정"}))
        self.assertEqual(result["revision"], 4)
        self.assertEqual(result["error"], self.browser_result["error"])
        self.browser_result = {"ok": True, "demo": False}
        self.assertTrue(self.result(await self.view())["ok"])

    async def test_callback_exception_is_sanitized(self):
        marker = "SYNTHETIC_PRIVATE_EXCEPTION_DETAIL"

        async def broken(_event):
            raise RuntimeError(marker)

        for operation in [lambda: self.view(__event_call__=broken),
                          lambda: self.update({"title": "수정"}, __event_call__=broken)]:
            data = self.failure(await operation())
            self.assertNotIn(marker, json.dumps(data))

    async def test_timeout_cancels_wait_and_returns_failure(self):
        cancelled = asyncio.Event()

        async def unavailable(_event):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        with patch.object(module, "EVENT_TIMEOUT_SECONDS", 0.001):
            self.failure(await self.view(__event_call__=unavailable))
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
