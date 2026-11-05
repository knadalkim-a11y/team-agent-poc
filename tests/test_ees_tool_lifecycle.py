"""Real authored lifecycle SQLite with explicitly synthetic Native I/O."""
import asyncio
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("ees_lifecycle_tests")
package.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[package.__name__] = package
workflow = importlib.import_module(package.__name__ + ".ees_workflow")
life = importlib.import_module(package.__name__ + ".ees_workflow_tool_lifecycle")
FIXTURE = json.loads((ROOT / "tests/fixtures/tools_phase2_contract.json").read_text(encoding="utf-8"))


class SyntheticNative:
    def __init__(self):
        self.tokens, self.generations = {}, {}
        self.groups = []
        self.identity = "identity-0"
        self.calls = 0
        self.saves = 0
        self.available = True
        self.result = deepcopy(FIXTURE["result"])
        self.status = "succeeded"
        self.started = asyncio.Event()
        self.release = None
        self.after_run = None
        self.after_groups = None

    async def inspect(self, user, native_id):
        if not self.available or not native_id:
            raise workflow.WorkflowError("native_access_denied", "합성 접근 제한")
        actor = user["id"]
        return {"native_id": native_id, "identity_stamp": self.identity, "credential_stamp": str(self.generations.get(actor, 0)),
                "environment": "synthetic-environment", "token_set": bool(self.tokens.get(actor)), "groups": list(self.groups)}

    async def save_connection(self, user, tool_id, native_id, token):
        self.saves += 1
        if token:
            self.tokens[user["id"]] = token
            self.generations[user["id"]] = self.generations.get(user["id"], 0) + 1
        return await self.inspect(user, native_id or "synthetic-" + tool_id)

    async def set_groups(self, user, native_id, groups, expected_stamp):
        if expected_stamp != self.identity:
            raise workflow.WorkflowError("tool_connection_conflict", "합성 충돌")
        self.groups = list(groups)
        self.identity += "-changed"
        if self.after_groups:
            await self.after_groups()
        return await self.inspect(user, native_id)

    async def redact(self, user, native_id, value):
        return life._safe(value, [self.tokens.get(user["id"], "")])

    async def run(self, user, native_id, code, function, base_url, inputs, expected_metadata):
        if await self.inspect(user, native_id) != expected_metadata:
            raise workflow.WorkflowError("tool_trial_snapshot_changed", "합성 상태 변경")
        self.calls += 1
        self.started.set()
        if self.release:
            await self.release.wait()
        if self.after_run:
            await self.after_run()
        raw = self.result if inputs["doc_types"] else {"documents": []}
        return {"status": self.status, "raw_result": await self.redact(user, native_id, raw), "duration_ms": 10,
                "error_code": "tool_trial_timeout" if self.status == "unknown" else "tool_trial_failed"}


class ToolLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.users = {key: {"id": key, "role": "user" if key == "reader" else "admin"} for key in ("admin", "other", "reader")}
        self.service = workflow.WorkflowService(Path(temporary.name) / "work.db", self.users.get, lambda _: None,
            group_list_lookup=lambda: [{"id": "group-ems"}, {"id": "group-fdc"}])
        self.native = SyntheticNative()
        self.service.tool_drafts.lifecycle.native = self.native
        self.counter = 0
        self.draft = (await self.call("tool_draft_save", draft=FIXTURE["draft"], expected_revision=0))["tool_draft"]
        self.key = self.draft["id"]

    def body(self, action, **fields):
        self.counter += 1
        return {"action": action, "request_id": "lifecycle-" + str(self.counter), **fields}

    async def call(self, action, actor="admin", **fields):
        return await self.service.operations.command(self.users[actor], self.body(action, **fields))

    async def error(self, code, awaitable):
        with self.assertRaises(workflow.WorkflowError) as caught:
            await awaitable
        self.assertEqual(caught.exception.code, code)

    async def connect(self, actor="admin", revision=0, **fields):
        return await self.call("tool_draft_connection_save", actor=actor, tool_id=self.key, expected_revision=1,
            expected_connection_revision=revision, **{**FIXTURE["connection"], **fields})

    async def trial(self, revision=1, connection=1, **fields):
        return (await self.call("tool_draft_trial_start", tool_id=self.key, expected_revision=revision,
            expected_connection_revision=connection, inputs=fields.pop("inputs", FIXTURE["inputs"]), **fields))["trial"]

    async def use(self, trial, revision=0, **fields):
        return await self.call("tool_draft_use_set", tool_id=self.key, trial_id=trial["id"], expected_revision=trial["draft_revision"],
            expected_connection_revision=trial["connection_revision"], expected_use_revision=revision,
            **{**{"groups": FIXTURE["groups"], "evidence": FIXTURE["evidence"]}, **fields})

    async def test_save_connect_trial_use_and_new_draft_preserve_active_snapshot(self):
        self.assertEqual(self.draft["phase"], 2)
        self.assertFalse(self.draft["connection"]["configured"])
        connected = await self.connect()
        self.assertTrue(connected["connection"]["configured"])
        trial = await self.trial()
        self.assertEqual((trial["status"], trial["count"], trial["fields_checked"]), ("succeeded", 2, True))
        self.assertTrue(trial["eligible_for_activation"])
        used = (await self.use(trial))["use"]
        self.assertEqual((used["active_version"], used["revision"], used["state"]), (1, 1, "active"))
        changed = deepcopy(FIXTURE["draft"])
        changed["code"] += "\n# 새 수정본\n"
        saved = (await self.call("tool_draft_save", tool_id=self.key, expected_revision=1, draft=changed))["tool_draft"]
        self.assertEqual(saved["active_version"], 1)
        self.assertFalse(saved["trial"]["eligible_for_activation"])
        with self.service._db() as db:
            active = json.loads(db.execute("SELECT data FROM work_tool_authored_versions").fetchone()[0])
        self.assertEqual(active["snapshot"]["draft"]["code"], FIXTURE["draft"]["code"])
        new_trial = await self.trial(revision=2)
        second = (await self.use(new_trial, revision=1))["use"]
        self.assertEqual(second["active_version"], 2)
        self.assertEqual([version["version"] for version in second["versions"]], [1, 2])

    async def test_connection_receipt_has_no_token_or_token_derived_fingerprint(self):
        body = self.body("tool_draft_connection_save", tool_id=self.key, expected_revision=1, expected_connection_revision=0, **FIXTURE["connection"])
        first = await self.service.operations.command(self.users["admin"], body)
        body["token"] = "replacement-that-must-not-write"
        self.assertEqual(await self.service.operations.command(self.users["admin"], body), first)
        self.assertEqual(self.native.saves, 1)
        self.assertEqual(self.native.tokens["admin"], FIXTURE["connection"]["token"])
        with self.service._db() as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(work_tool_connection_receipts)")]
            receipts = " ".join(row[0] for row in db.execute("SELECT data FROM work_tool_connection_receipts"))
        self.assertNotIn("fingerprint", columns)
        self.assertNotIn(FIXTURE["connection"]["token"], receipts)
        await self.connect(revision=1, token="")
        self.assertEqual(self.native.tokens["admin"], FIXTURE["connection"]["token"])

    async def test_address_validation_and_invalid_inputs_do_not_start_worker(self):
        for address in ["ftp://x.invalid", "https://user:secret@x.invalid", "https://x.invalid?q=1", "https://x.invalid#p", "https://x.invalid?"]:
            await self.error("tool_connection_invalid", self.connect(base_url=address))
        self.assertEqual(self.native.saves, 0)
        await self.connect()
        for inputs in [{}, {"doc_types": "design_doc"}, {"doc_types": ["unknown"]}, {"doc_types": [], "__user__": {}}]:
            await self.error("tool_trial_inputs_invalid", self.trial(inputs=inputs))
        self.assertEqual(self.native.calls, 0)

    async def test_empty_is_success_without_claiming_field_check_and_can_activate(self):
        await self.connect()
        trial = await self.trial(inputs=FIXTURE["empty_inputs"])
        self.assertEqual((trial["status"], trial["completeness"], trial["count"], trial["fields_checked"]), ("succeeded", "empty", 0, False))
        self.assertTrue(trial["warnings"])
        self.assertEqual((await self.use(trial))["use"]["active_version"], 1)

    async def test_partial_mapping_error_and_timeout_never_activate(self):
        await self.connect()
        variants = [{**FIXTURE["result"], "truncated": True}, {**FIXTURE["result"], "completeness": "truncated"}, {"documents": [{"title": "missing fields"}]},
                    {"documents": [{**FIXTURE["result"]["documents"][0], "url": "javascript:alert(1)"}]}, {"ok": False}]
        for raw in variants:
            self.native.result = deepcopy(raw)
            trial = await self.trial()
            self.assertEqual(trial["status"], "failed")
            self.assertFalse(trial["eligible_for_activation"])
            await self.error("tool_trial_stale", self.use(trial))
        self.native.status = "unknown"
        trial = await self.trial()
        self.assertEqual(trial["status"], "unknown")
        self.assertEqual(trial["inputs"], FIXTURE["inputs"])
        self.native.status, self.native.result = "succeeded", {"documents": [], "status": "unknown"}
        self.assertEqual((await self.trial())["status"], "unknown")

    async def test_inflight_duplicate_executes_once_and_payload_change_conflicts(self):
        await self.connect()
        self.native.release = asyncio.Event()
        body = self.body("tool_draft_trial_start", tool_id=self.key, expected_revision=1, expected_connection_revision=1, inputs=FIXTURE["inputs"])
        first = asyncio.create_task(self.service.operations.command(self.users["admin"], body))
        await asyncio.wait_for(self.native.started.wait(), 2)
        pending = (await self.service.operations.command(self.users["admin"], body))["trial"]
        self.assertEqual(pending["status"], "running")
        await self.error("request_conflict", self.service.operations.command(self.users["admin"], {**body, "inputs": {"doc_types": []}}))
        self.native.release.set()
        finished = (await first)["trial"]
        replay = (await self.service.operations.command(self.users["admin"], body))["trial"]
        self.assertEqual((pending["id"], finished["id"]), (replay["id"], replay["id"]))
        self.assertEqual(self.native.calls, 1)
        self.assertEqual(replay["status"], "succeeded")

    async def test_role_revocation_completion_has_no_response_and_actor_private_trial(self):
        await self.connect()
        async def revoke():
            self.users["admin"]["role"] = "user"
        self.native.after_run = revoke
        await self.error("admin_required", self.trial())
        self.users["admin"]["role"] = "admin"
        record = (await self.call("tool_draft_get", tool_id=self.key))["tool_draft"]
        self.assertEqual(record["trial"]["status"], "succeeded")
        other = (await self.call("tool_draft_get", actor="other", tool_id=self.key))["tool_draft"]
        self.assertIsNone(other["trial"])
        await self.error("tool_trial_not_found", self.call("tool_draft_trial_get", actor="other", tool_id=self.key, trial_id=record["trial"]["id"]))
        await self.error("admin_required", self.call("tool_draft_connection_get", actor="reader", tool_id=self.key))

    async def test_native_direct_credential_change_stales_trial_without_connection_revision(self):
        await self.connect()
        trial = await self.trial()
        self.native.generations["admin"] += 1
        current = (await self.call("tool_draft_trial_get", tool_id=self.key, trial_id=trial["id"]))["trial"]
        self.assertFalse(current["eligible_for_activation"])
        self.assertIn("tool_trial_credentials_changed", [issue["code"] for issue in current["activation_reasons"]])
        await self.error("tool_trial_stale", self.use(trial))

    async def test_activation_rechecks_credentials_after_native_acl_await(self):
        await self.connect()
        trial = await self.trial()
        async def change():
            self.native.generations["admin"] += 1
        self.native.after_groups = change
        await self.error("tool_trial_stale", self.use(trial))
        self.assertIsNone((await self.call("tool_draft_get", tool_id=self.key))["tool_draft"]["active_version"])

    async def test_disabled_survives_reconfirmation_and_restrictive_management_during_outage(self):
        await self.connect()
        trial = await self.trial()
        await self.use(trial)
        disabled = (await self.call("tool_draft_use_disable", tool_id=self.key, expected_use_revision=1))["use"]
        self.assertEqual(disabled["state"], "disabled")
        confirmed = (await self.use(trial, revision=2))["use"]
        self.assertEqual((confirmed["state"], confirmed["active_version"]), ("disabled", 1))
        self.native.available = False
        reduced = (await self.call("tool_draft_use_access", tool_id=self.key, expected_use_revision=3, groups=[]))["use"]
        self.assertEqual(reduced["groups"], [])
        await self.error("native_access_denied", self.call("tool_draft_use_access", tool_id=self.key, expected_use_revision=4, groups=["group-ems", "group-fdc"]))
        await self.error("tool_use_groups_invalid", self.call("tool_draft_use_enable", tool_id=self.key, expected_use_revision=4))
        await self.error("tool_draft_conflict", self.call("tool_draft_use_disable", tool_id=self.key, expected_use_revision=1))

    async def test_cancel_preserves_unknown_and_never_reexecutes(self):
        await self.connect()
        self.native.release = asyncio.Event()
        body = self.body("tool_draft_trial_start", tool_id=self.key, expected_revision=1, expected_connection_revision=1, inputs=FIXTURE["inputs"])
        task = asyncio.create_task(self.service.operations.command(self.users["admin"], body))
        await asyncio.wait_for(self.native.started.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        replay = (await self.service.operations.command(self.users["admin"], body))["trial"]
        self.assertEqual(replay["status"], "unknown")
        self.assertEqual(self.native.calls, 1)

    async def test_trial_public_and_audit_do_not_expose_token_or_private_stamps(self):
        await self.connect()
        self.native.result["documents"][0]["title"] = FIXTURE["connection"]["token"]
        trial = await self.trial()
        encoded = json.dumps(trial)
        self.assertNotIn(FIXTURE["connection"]["token"], encoded)
        self.assertNotIn("credential_stamp", encoded)
        self.assertNotIn("_snapshot", encoded)
        with self.service._db() as db:
            audit = " ".join(row[0] for row in db.execute("SELECT data FROM work_operation_events"))
        self.assertNotIn(FIXTURE["connection"]["token"], audit)
        self.assertNotIn("credential_stamp", audit)

    async def test_access_revoked_hides_trial_inputs_and_evidence(self):
        await self.connect()
        trial = await self.trial()
        self.native.available = False
        visible = (await self.call("tool_draft_trial_get", tool_id=self.key, trial_id=trial["id"]))["trial"]
        self.assertEqual(visible["inputs"], {})
        self.assertEqual(visible["rows"], [])
        self.assertIsNone(visible["raw_result"])
        self.assertEqual(visible["status"], "succeeded")
        self.assertFalse(visible["eligible_for_activation"])

    async def test_connection_replay_rechecks_access_and_never_stores_trial_evidence(self):
        await self.connect()
        await self.trial()
        body = self.body("tool_draft_connection_save", tool_id=self.key, expected_revision=1, expected_connection_revision=1,
                         base_url=FIXTURE["connection"]["base_url"], token="")
        saved = await self.service.operations.command(self.users["admin"], body)
        self.assertTrue(saved["tool_draft"]["trial"]["rows"])
        with self.service._db() as db:
            receipt = json.loads(db.execute("SELECT data FROM work_tool_connection_receipts WHERE request_id=?", (body["request_id"],)).fetchone()[0])
        self.assertNotIn("trial", receipt["tool_draft"])
        self.native.available = False
        replay = await self.service.operations.command(self.users["admin"], body)
        self.assertEqual(replay["tool_draft"]["trial"]["inputs"], {})
        self.assertEqual(replay["tool_draft"]["trial"]["rows"], [])
        self.assertIsNone(replay["tool_draft"]["trial"]["raw_result"])

    async def test_secrets_in_evidence_and_malformed_result_urls_are_rejected(self):
        await self.connect()
        trial = await self.trial()
        for evidence in [FIXTURE["connection"]["token"], "password: synthetic-secret", '"token":"synthetic-secret"', "확인 https://docs.invalid?token=secret"]:
            await self.error("tool_use_evidence_invalid", self.use(trial, evidence=evidence))
        for url in ["https://docs.invalid:bad/a", "https://docs.invalid:99999/a", "https://docs.invalid/a b"]:
            self.native.result["documents"][0]["url"] = url
            self.assertEqual((await self.trial())["status"], "failed")

    async def test_failed_activation_restores_exact_native_groups(self):
        await self.connect()
        trial = await self.trial()
        original = deepcopy(FIXTURE["draft"])
        async def edit():
            self.native.after_groups = None
            original["description"] = "동시 수정"
            await self.call("tool_draft_save", tool_id=self.key, expected_revision=1, draft=original)
        self.native.after_groups = edit
        await self.error("tool_draft_conflict", self.use(trial))
        self.assertEqual(self.native.groups, [])
        record = (await self.call("tool_draft_get", tool_id=self.key))["tool_draft"]
        self.assertEqual(record["use"]["state"], "draft")
        self.assertIsNone(record["active_version"])

    async def test_acl_write_failure_is_not_reported_as_successful_reduction(self):
        await self.connect()
        trial = await self.trial()
        await self.use(trial, groups=["group-ems", "group-fdc"])
        async def conflict(*args):
            raise workflow.WorkflowError("tool_connection_conflict", "합성 변경 실패")
        self.native.set_groups = conflict
        await self.error("tool_connection_conflict", self.call("tool_draft_use_access", tool_id=self.key, expected_use_revision=1, groups=["group-ems"]))
        record = (await self.call("tool_draft_get", tool_id=self.key))["tool_draft"]
        self.assertEqual(record["use"]["groups"], ["group-ems", "group-fdc"])

    async def test_enable_checks_stored_active_snapshot_and_use_replay_is_stable(self):
        await self.connect()
        trial = await self.trial()
        body = self.body("tool_draft_use_set", tool_id=self.key, trial_id=trial["id"], expected_revision=1, expected_connection_revision=1,
            expected_use_revision=0, groups=FIXTURE["groups"], evidence=FIXTURE["evidence"])
        first = await self.service.operations.command(self.users["admin"], body)
        self.assertEqual(await self.service.operations.command(self.users["admin"], body), first)
        await self.call("tool_draft_use_disable", tool_id=self.key, expected_use_revision=1)
        with self.service._db(write=True) as db:
            stored = json.loads(db.execute("SELECT data FROM work_tool_authored_versions").fetchone()[0])
            stored["snapshot"]["draft"]["code"] = "class Broken: pass"
            db.execute("UPDATE work_tool_authored_versions SET data=?", (json.dumps(stored),))
        await self.error("tool_use_snapshot_invalid", self.call("tool_draft_use_enable", tool_id=self.key, expected_use_revision=2))

    async def test_enable_rejects_deleted_native_groups(self):
        await self.connect()
        await self.use(await self.trial())
        await self.call("tool_draft_use_disable", tool_id=self.key, expected_use_revision=1)
        self.service.group_list_lookup = lambda: []
        await self.error("tool_use_groups_invalid", self.call("tool_draft_use_enable", tool_id=self.key, expected_use_revision=2))
        self.assertEqual((await self.call("tool_draft_get", tool_id=self.key))["tool_draft"]["use"]["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
