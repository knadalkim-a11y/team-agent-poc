"""Phase-one draft persistence and access boundaries with real SQLite."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("ees_tool_draft_tests")
package.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[package.__name__] = package
workflow = importlib.import_module(package.__name__ + ".ees_workflow")
FIXTURE = json.loads((ROOT / "tests/fixtures/tools_phase1_contract.json").read_text(encoding="utf-8"))["draft"]


class SourceBridge:
    def __init__(self):
        self.code = FIXTURE["code"]
        self.allowed = True
        self.calls = []

    async def tool_import_sources(self, actor):
        return [{"id": "existing", "name": "기존 도구", "functions": ["list_documents"]}] if self.allowed else []

    async def read_tool_import_source(self, actor, tool_id, function):
        self.calls.append((tool_id, function))
        if not self.allowed or tool_id != "existing" or function != "list_documents":
            raise workflow.WorkflowError("native_access_denied", "읽기 권한 없음")
        return {"name": "기존 도구", "code": self.code, "function": function}


class ToolDraftTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.users = {"admin": {"id": "admin", "role": "admin"},
                      "reader": {"id": "reader", "role": "user"}}
        self.bridge = SourceBridge()
        self.database = Path(self.temp.name) / "work.sqlite3"
        self.service = workflow.WorkflowService(self.database, self.users.get, lambda _: None, native_bridge=self.bridge)
        self.counter = 0

    def body(self, action, revision=0, **fields):
        self.counter += 1
        return {"action": action, "request_id": "draft-test-" + str(self.counter),
                "expected_revision": revision, **fields}

    async def call(self, action, revision=0, actor="admin", **fields):
        return await self.service.operations.command(self.users[actor], self.body(action, revision, **fields))

    async def assert_code(self, code, awaitable):
        with self.assertRaises(workflow.WorkflowError) as caught:
            await awaitable
        self.assertEqual(caught.exception.code, code)

    async def test_save_reload_and_update_without_owner_or_activation(self):
        saved = (await self.call("tool_draft_save", draft=FIXTURE))["tool_draft"]
        self.assertEqual(saved["draft"], FIXTURE)
        self.assertTrue(saved["check"]["valid"], saved["check"])
        self.assertIsNone(saved["active_version"])
        self.assertEqual((saved["created_by"], saved["updated_by"], saved["revision"]), ("admin", "admin", 1))
        restarted = workflow.WorkflowService(self.database, self.users.get, lambda _: None, native_bridge=self.bridge)
        read = await restarted.tool_drafts.command(self.users["admin"], {"action": "tool_draft_get", "tool_id": saved["id"]})
        self.assertEqual(read["tool_draft"], saved)
        changed = deepcopy(FIXTURE)
        changed["description"] = "다시 저장"
        updated = (await self.call("tool_draft_save", 1, tool_id=saved["id"], draft=changed))["tool_draft"]
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["created_at"], saved["created_at"])
        self.assertIsNone(updated["active_version"])

    async def test_all_draft_actions_reject_nonadmin_and_revoked_session(self):
        saved = (await self.call("tool_draft_save", draft=FIXTURE))["tool_draft"]
        for action, fields in [("tool_draft_get", {"tool_id": saved["id"]}),
                               ("tool_draft_check", {"draft": FIXTURE}),
                               ("tool_draft_save", {"draft": FIXTURE}),
                               ("tool_draft_import", {"source_tool_id": "existing", "function": "list_documents"})]:
            await self.assert_code("admin_required", self.call(action, actor="reader", **fields))
        self.assertEqual(await self.service.tool_drafts.summaries(self.users["reader"]), [])
        self.assertEqual(await self.service.tool_drafts.sources(self.users["reader"]), [])
        stale = dict(self.users["admin"])
        self.users["admin"]["role"] = "user"
        await self.assert_code("admin_required", self.service.tool_drafts.command(stale, self.body("tool_draft_get", tool_id=saved["id"])))

    async def test_revision_conflict_retains_saved_definition(self):
        saved = (await self.call("tool_draft_save", draft=FIXTURE))["tool_draft"]
        first, second = deepcopy(FIXTURE), deepcopy(FIXTURE)
        first["name"], second["name"] = "먼저 저장", "충돌한 저장"
        await self.call("tool_draft_save", 1, tool_id=saved["id"], draft=first)
        await self.assert_code("tool_draft_conflict", self.call("tool_draft_save", 1, tool_id=saved["id"], draft=second))
        read = (await self.call("tool_draft_get", tool_id=saved["id"]))["tool_draft"]
        self.assertEqual(read["draft"]["name"], "먼저 저장")
        self.assertEqual(read["revision"], 2)

    async def test_replay_is_idempotent_and_payload_changes_are_rejected(self):
        body = self.body("tool_draft_save", draft=deepcopy(FIXTURE))
        first = await self.service.operations.command(self.users["admin"], body)
        self.assertEqual(await self.service.operations.command(self.users["admin"], body), first)
        body["draft"]["name"] = "다른 내용"
        await self.assert_code("request_conflict", self.service.operations.command(self.users["admin"], body))
        self.assertEqual(len(await self.service.tool_drafts.summaries(self.users["admin"])), 1)

    async def test_source_is_copied_with_current_access_and_without_settings(self):
        self.assertEqual((await self.service.tool_drafts.sources(self.users["admin"]))[0]["id"], "existing")
        saved = (await self.call("tool_draft_import", source_tool_id="existing", function="list_documents"))["tool_draft"]
        self.assertEqual(saved["draft"]["code"], self.bridge.code)
        self.assertEqual(saved["draft"]["input_ui"]["doc_types"]["widget"], "multiselect")
        self.assertFalse(saved["check"]["valid"])  # Result mapping still needs authoring.
        self.bridge.code = "changed outside"
        self.assertEqual((await self.call("tool_draft_get", tool_id=saved["id"]))["tool_draft"]["draft"]["code"], FIXTURE["code"])
        self.bridge.allowed = False
        await self.assert_code("tool_draft_source_unavailable", self.call("tool_draft_import", source_tool_id="existing", function="list_documents"))
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM work_tool_drafts").fetchone()[0], 1)

    async def test_invalid_code_can_be_saved_and_check_does_not_save_or_execute(self):
        draft = deepcopy(FIXTURE)
        marker = Path(self.temp.name) / "must-not-exist"
        draft["code"] = "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('bad')\n" + draft["code"]
        result = await self.call("tool_draft_check", draft=draft)
        self.assertIn("valid", result["check"])
        self.assertEqual(await self.service.tool_drafts.summaries(self.users["admin"]), [])
        saved = (await self.call("tool_draft_save", draft=draft))["tool_draft"]
        self.assertFalse(marker.exists())
        draft["code"] = "class Tools:\n def broken("
        second = (await self.call("tool_draft_save", 1, tool_id=saved["id"], draft=draft))["tool_draft"]
        self.assertFalse(second["check"]["valid"])
        self.assertEqual(second["draft"]["code"], draft["code"])

    async def test_summary_and_audit_exclude_code_and_definitions(self):
        saved = (await self.call("tool_draft_save", draft=FIXTURE))["tool_draft"]
        summary = (await self.service.tool_drafts.summaries(self.users["admin"]))[0]
        self.assertEqual(set(summary), {"id", "name", "description", "target", "kind", "revision", "active_version", "state", "updated_at"})
        with self.service._db() as db:
            audit = json.loads(db.execute("SELECT data FROM work_operation_events WHERE target=?", (saved["id"],)).fetchone()[0])
        self.assertEqual(set(audit), {"revision", "valid"})

    async def test_drafts_cannot_resolve_as_shared_tools_and_existing_tables_untouched(self):
        with self.service._db() as db:
            before = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
                      for table in ("work_shared_tools", "work_shared_tool_versions", "work_shared_tool_pins", "work_tool_contracts", "work_definitions")}
        saved = (await self.call("tool_draft_save", draft=FIXTURE))["tool_draft"]
        await self.assert_code("shared_tool_review_required", self.service.shared_tools.resolve(self.users["admin"], saved["id"]))
        with self.service._db() as db:
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM " + table)], rows)

    async def test_structural_limits_and_unknown_fields_fail_before_write(self):
        for value in [[], {**FIXTURE, "active_version": 1}, {**FIXTURE, "code": "x" * 262145}, {**FIXTURE, "kind": "write"}]:
            await self.assert_code("tool_draft_invalid", self.call("tool_draft_save", draft=value))
        await self.assert_code("tool_draft_invalid", self.call("tool_draft_save", tool_id="", draft=FIXTURE))
        self.assertEqual(await self.service.tool_drafts.summaries(self.users["admin"]), [])

    async def test_wrong_ui_shapes_are_rejected_but_missing_fields_are_completed(self):
        for key, value in [("input_ui", {"q": 1}), ("input_ui", {"q": {"label": []}}),
                           ("input_ui", {"q": {"option_labels": []}}),
                           ("input_ui", {"q": {"option_labels": {"a": 1}}}),
                           ("output_ui", {"fields": "bad"}), ("output_ui", {"fields": [1]}),
                           ("output_ui", {"fields": [{"hidden": "false"}]}),
                           ("output_ui", {"fields": [{"path": []}]})]:
            await self.assert_code("tool_draft_invalid", self.call("tool_draft_save", draft={**FIXTURE, key: value}))
        self.assertEqual(await self.service.tool_drafts.summaries(self.users["admin"]), [])
        saved = (await self.call("tool_draft_save", draft={"input_ui": {"q": {}}, "output_ui": {}}))["tool_draft"]
        self.assertFalse(saved["check"]["valid"])
        self.assertEqual(saved["draft"]["output_ui"], {"kind": "list", "path": "", "fields": []})
        self.assertEqual(saved["draft"]["input_ui"]["q"], {"label": "", "question": "", "widget": "text", "option_labels": {}})

    async def test_import_preserves_optional_defaults_and_boolean_option_values(self):
        self.bridge.code = "from typing import Literal, Optional\nclass Tools:\n    def list_documents(self, q: Literal[True, False] = True, maybe: Optional[str] = 'kept'):\n        pass\n"
        saved = (await self.call("tool_draft_import", source_tool_id="existing", function="list_documents"))["tool_draft"]
        ui = saved["draft"]["input_ui"]
        self.assertEqual(set(ui["q"]["option_labels"]), {"true", "false"})
        self.assertIs(ui["q"]["default"], True)
        self.assertEqual(ui["maybe"]["default"], "kept")
        self.assertFalse(any(error["field"].startswith("input_ui") for error in saved["check"]["errors"] if "field" in error))

    async def test_source_candidates_are_hidden_when_role_is_revoked_during_lookup(self):
        await self.call("tool_draft_save", draft=FIXTURE)
        original = self.bridge.tool_import_sources

        async def revoke(actor):
            result = await original(actor)
            self.users["admin"]["role"] = "user"
            return result

        self.bridge.tool_import_sources = revoke
        state = await self.service.operations.state(dict(self.users["admin"]))
        self.assertEqual(state["tool_import_sources"], [])
        self.assertEqual(state["tool_drafts"], [])


if __name__ == "__main__":
    unittest.main()
