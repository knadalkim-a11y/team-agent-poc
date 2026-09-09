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

    async def find_equipment(self, **filters):
        args = {"__event_call__": self.browser, "__metadata__": METADATA, **filters}
        return await self.tool.ems_demo_find_equipment(**args)

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
                if field == "equipment_id":
                    # The length is allowed, but an invented ID must not select equipment.
                    rejected = self.failure(await self.update({field: "가" * limit}))
                    self.assertEqual(rejected["error"]["code"], "unknown_equipment")
                else:
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

    async def test_equipment_lookup_is_independent_and_never_selects_first_match(self):
        all_items = self.result(module._find_demo_equipment({}))
        self.assertTrue(all_items["ok"])
        self.assertEqual(all_items["matches_count"], 32)
        self.assertEqual(len(all_items["matches"]), 8)
        self.assertTrue(all_items["matches_truncated"])
        self.assertNotIn("equipment", all_items)
        missing = self.result(module._find_demo_equipment({"query": "없는 샘플 설비"}))
        self.assertTrue(missing["ok"])
        self.assertEqual(missing["matches"], [])
        self.assertEqual(missing["matches_count"], 0)
        self.assertEqual(self.events, [])

    async def test_equipment_lookup_scope_exact_id_and_shared_panel_catalog(self):
        found = self.result(module._find_demo_equipment(
            {"site": "천안", "shop": "조립", "line": "조립 1라인", "process": "권취", "query": "kr-ca"}))
        self.assertEqual(found["matches_count"], 1)
        self.assertFalse(found["matches_truncated"])
        self.assertEqual(found["matches"][0]["id"], "KR-CA-211")
        self.assertEqual(found["available_options"]["process"], ["권취", "조립"])
        scoped_out = self.result(module._find_demo_equipment(
            {"equipment_id": "KR-CA-211", "site": "울산"}))
        self.assertEqual(scoped_out["matches_count"], 0)
        partial_id = self.result(module._find_demo_equipment({"equipment_id": "KR-CA"}))
        self.assertEqual(partial_id["matches_count"], 0)
        self.assertEqual(self.events, [])
        await self.view()
        code = self.events[-1]["data"]["code"]
        start = code.index("const equipmentCatalog = ") + len("const equipmentCatalog = ")
        catalog, _ = json.JSONDecoder().raw_decode(code[start:])
        self.assertEqual(len(catalog), 32)
        self.assertEqual(next(item for item in catalog if item["id"] == "KR-CA-211"), found["matches"][0])
        found["matches"][0]["name"] = "caller changed copy"
        again = module._find_demo_equipment({"equipment_id": "KR-CA-211"})
        self.assertEqual(again["matches"][0]["name"], "권취 설비 1호")

    async def test_equipment_lookup_opens_search_panel_with_filters_as_json_only(self):
        self.browser_result = {"ok": True, "opened": True, "screen": "equipment",
                               "fields": {"description": "unrelated current WO"}, "matches_count": 32}
        found = self.result(await self.find_equipment(site="  천안 ", equipment_id="KR-CA-211"))
        self.assertTrue(found["ok"])
        self.assertEqual(found["matches_count"], 1)
        self.assertEqual(found["panel"], {"ok": True, "demo": True, "opened": True, "screen": "equipment"})
        request, _ = self.request()
        self.assertEqual(request["action"], "equipment")
        self.assertEqual(request["chat_id"], METADATA["chat_id"])
        self.assertEqual(request["filters"], found["filters"])
        self.assertEqual(request["filters"]["site"], "천안")
        self.assertNotIn("changes", request)
        self.assertNotIn("expected_revision", request)

        query = '\"; globalThis.EES_SEARCH_INJECTION = true; //\n</script>'
        empty = self.result(await self.find_equipment(query=query))
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["matches_count"], 0)
        self.assertTrue(empty["panel"]["opened"])
        request, executable = self.request()
        self.assertEqual(request["filters"]["query"], query)
        self.assertNotIn("EES_SEARCH_INJECTION", executable)

    async def test_equipment_lookup_retains_results_when_browser_is_unavailable(self):
        for overrides, code in (({"__metadata__": None}, "chat_required"),
                                ({"__event_call__": None}, "browser_required")):
            with self.subTest(overrides=overrides):
                found = self.result(await self.find_equipment(equipment_id="KR-CA-211", **overrides))
                self.assertTrue(found["ok"])
                self.assertEqual(found["matches"][0]["id"], "KR-CA-211")
                panel = self.failure(found["panel"])
                self.assertEqual(panel["error"]["code"], code)
                self.assertIsNot(panel.get("opened"), True)
        self.assertEqual(self.events, [])

    async def test_equipment_lookup_does_not_claim_opened_for_malformed_panel_status(self):
        marker = "SYNTHETIC_PRIVATE_PANEL_DETAIL"
        for response in (None, [], marker, {}, {"ok": "true"}, {"ok": True},
                         {"ok": True, "opened": False, "screen": "equipment"},
                         {"ok": True, "opened": 1, "screen": "equipment"},
                         {"ok": True, "opened": True, "screen": "wo"}):
            with self.subTest(response=response):
                self.browser_result = response
                found = self.result(await self.find_equipment(equipment_id="KR-CA-211"))
                self.assertTrue(found["ok"])
                self.assertEqual(found["matches_count"], 1)
                panel = self.failure(found["panel"])
                self.assertIsNot(panel.get("opened"), True)
                self.assertNotIn(marker, json.dumps(found))

    async def test_equipment_lookup_sanitizes_transport_failure_and_cancels_timeout(self):
        marker = "SYNTHETIC_PRIVATE_SEARCH_EXCEPTION"
        cancelled = asyncio.Event()

        async def broken(_event):
            raise RuntimeError(marker)

        async def unavailable(_event):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        with patch.object(module, "EVENT_TIMEOUT_SECONDS", 0.001):
            for callback in (broken, unavailable):
                found = self.result(await self.find_equipment(equipment_id="KR-CA-211", __event_call__=callback))
                self.assertTrue(found["ok"])
                self.assertEqual(found["matches_count"], 1)
                panel = self.failure(found["panel"])
                self.assertEqual(panel["error"]["code"], "browser_response_unconfirmed")
                self.assertIsNot(panel.get("opened"), True)
                self.assertNotIn(marker, json.dumps(found))
        self.assertTrue(cancelled.is_set())

    async def test_equipment_lookup_rejects_bad_filters_without_browser(self):
        for field in ("corporation", "site", "shop", "line", "process", "query", "equipment_id"):
            for value in (None, 42, True, [], {}, "가" * 101):
                with self.subTest(field=field, value=value):
                    result = self.failure(await self.find_equipment(**{field: value}))
                    self.assertEqual(result["error"]["code"], "invalid_filters")
        self.assertEqual(self.events, [])

    async def test_wo_resolves_equipment_path_and_rejects_wrong_scope_before_editing(self):
        for changes, error in (({"equipment_id": "INVENTED", "title": "must not apply"}, "unknown_equipment"),
                               ({"equipment_id": "   ", "title": "must not select first equipment"}, "unknown_equipment"),
                               ({"equipment_id": "KR-CA-211", "site": "울산"}, "equipment_scope_mismatch")):
            self.assertEqual(self.failure(await self.update(changes))["error"]["code"], error)
        self.assertEqual(self.events, [])
        fields = {"title": "권취 설비 소음 점검", "type": "점검", "priority": "일반", "description": "사용자 보고: 소음 발생"}
        self.assertTrue(self.result(await self.update({"equipment_id": "KR-CA-211", "process": "권취", **fields}))["ok"])
        request, _ = self.request()
        self.assertEqual(request["changes"], {"equipment_id": "KR-CA-211", "corporation": "한국", "site": "천안",
                                             "shop": "조립", "line": "조립 1라인", "process": "권취", **fields})
        self.assertEqual(request["expected_revision"], 3)

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
