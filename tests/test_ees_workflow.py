"""Shared workflow service: real persistence/auth boundaries, synthetic checks.

No Open WebUI user database, business endpoint, model or external network is used.
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agent-pack/skills/ees-work-demo/scripts/ees_workflow.py"
SPEC = importlib.util.spec_from_file_location("ees_workflow_test_subject", SOURCE)
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "ees-work.sqlite3"
        self.users = {key: {"id": key, "role": role} for key, role in
                      (("alice", "user"), ("bob", "user"), ("admin", "admin"))}
        self.chats = {"chat-a": {"id": "chat-a", "user_id": "alice"},
                      "chat-a2": {"id": "chat-a2", "user_id": "alice"},
                      "chat-b": {"id": "chat-b", "user_id": "bob"},
                      "chat-admin": {"id": "chat-admin", "user_id": "admin"}}
        self.lookup_user = AsyncMock(side_effect=lambda key: deepcopy(self.users.get(key)))
        self.lookup_chat = AsyncMock(side_effect=lambda key: deepcopy(self.chats.get(key)))
        self.service = workflow.WorkflowService(self.database, self.lookup_user, self.lookup_chat)
        self.alice, self.admin = self.users["alice"], self.users["admin"]

    async def create(self, *, user=None, **payload):
        result = await self.service.handle_action(user or self.alice, {"action": "create", "payload": payload})
        self.assertTrue(result["ok"], result)
        return result["case"]

    async def act(self, case, action, node_id="", payload=None, *, user=None, **extra):
        return await self.service.handle_action(user or self.alice, {
            "action": action, "case_id": case["id"], "node_id": node_id,
            "expected_revision": case["revision"], "payload": payload or {}, **extra,
        })

    async def step(self, case, action, node_id="", payload=None, **kwargs):
        result = await self.act(case, action, node_id, payload, **kwargs)
        self.assertTrue(result["ok"], result)
        return result["case"]

    async def ready(self, case):
        case = await self.step(case, "run", "scope-j", {"confirm": True})
        case = await self.step(case, "run", "infra-j")
        return await self.step(case, "run", "install-j", {"confirm": True})

    async def publish(self, definition):
        state = await self.service.get_state(self.admin)
        result = await self.service.handle_action(self.admin, {
            "action": "save_draft", "expected_revision": state["draft_revision"],
            "payload": {"definition": definition},
        })
        self.assertTrue(result["ok"], result)
        revision = result["draft_revision"]
        for action in ("validate_draft", "publish"):
            result = await self.service.handle_action(self.admin, {"action": action, "expected_revision": revision})
            self.assertTrue(result["ok"], result)
        return result

    async def test_initial_catalog_has_no_fabricated_progress_or_chat(self):
        result = await self.service.get_state(self.alice)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["case"])
        self.assertEqual(result["cases"], [])
        self.assertIsNone(result["draft"])
        self.assertFalse(result["can_manage"])
        self.assertEqual(result["catalog"]["systems"], list(workflow.SYSTEMS))
        self.assertEqual(workflow.validate_definition(result["catalog"]), [])
        case = await self.create()
        self.assertEqual(case["progress"], {"done": 0, "total": 6})
        self.assertTrue(all(job["attempt"] == 0 for job in case["jobs"].values()))
        self.assertEqual(case["chat_id"], "")

    async def test_pending_case_binds_after_chat_creation_and_survives_restart(self):
        case = await self.create()
        case = await self.step(case, "bind", chat_id="chat-a")
        case = await self.step(case, "select", "db-j")
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": "승인 진단 대상 A"}})
        restarted = workflow.WorkflowService(self.database, self.lookup_user, self.lookup_chat)
        restored = (await restarted.get_state(self.alice, chat_id="chat-a"))["case"]
        self.assertEqual(restored, case)
        self.assertEqual(restored["selected_id"], "db-j")
        self.assertEqual(restored["jobs"]["db-j"]["inputs"]["db"], "승인 진단 대상 A")

    async def test_case_summaries_keep_factory_history_and_snapshot_node_progress(self):
        american = await self.create(site_id="us-a", system="EMS")
        created_at = american["created_at"]
        self.assertIsNotNone(created_at)
        self.assertEqual(american["status"], "pending")
        with patch.object(workflow, "_now", return_value="2026-09-15T10:00:00.000+00:00"):
            american = await self.step(american, "run", "scope-j", {"confirm": True})
        self.assertEqual(american["status"], "in_progress")
        hungarian = await self.create(site_id="hu-a", system="FDC")
        summaries = {item["id"]: item for item in (await self.service.get_state(self.alice))["cases"]}
        summary = summaries[american["id"]]
        self.assertEqual(summary["created_at"], created_at)
        self.assertEqual(summary["updated_at"], "2026-09-15T10:00:00.000+00:00")
        self.assertEqual(summary["process_name"], american["definition"]["nodes"]["setup-p"]["name"])
        self.assertEqual(summary["category"], "setup")
        self.assertEqual(summary["node_states"], american["node_states"])
        self.assertEqual(summary["tree_nodes"]["setup-p"]["children"], american["definition"]["nodes"]["setup-p"]["children"])
        self.assertNotIn("instructions", summary["tree_nodes"]["setup-p"])
        self.assertNotIn("skills", summary["tree_nodes"]["setup-p"])
        self.assertEqual(summary["progress"], {"done": 1, "total": 6})
        other = summaries[hungarian["id"]]
        self.assertEqual(other["progress"], {"done": 0, "total": 5})
        self.assertEqual(other["node_states"]["setup-p"]["excluded_count"], 1)
        self.assertEqual(other["node_states"]["interface-j"]["status"], "skipped")
        self.assertNotIn("definition", summary)
        self.assertNotIn("jobs", summary)
        self.assertEqual((await self.service.get_state(self.users["bob"]))["cases"], [])

    async def test_case_tree_uses_frozen_structure_after_catalog_removes_a_job(self):
        old = await self.create()
        definition = workflow._seed()
        definition["nodes"].pop("db-j")
        definition["nodes"]["install-t"]["children"].remove("db-j")
        definition["nodes"]["interface-j"]["deps"].remove("db-j")
        await self.publish(definition)
        newer = await self.create()
        state = await self.service.get_state(self.alice)
        summaries = {item["id"]: item for item in state["cases"]}
        self.assertNotIn("db-j", state["catalog"]["nodes"])
        self.assertIn("db-j", summaries[old["id"]]["tree_nodes"])
        self.assertIn("db-j", summaries[old["id"]]["tree_nodes"]["install-t"]["children"])
        self.assertNotIn("db-j", summaries[newer["id"]]["tree_nodes"])

    async def test_history_read_does_not_change_current_selection_revision_or_timestamps(self):
        old = await self.step(await self.create(), "bind", chat_id="chat-a")
        old = await self.step(old, "select", "db-j")
        current = await self.step(await self.create(site_id="hu-a"), "bind", chat_id="chat-a2")
        current = await self.step(current, "select", "install-t")
        with self.service._db() as db:
            before = [tuple(row) for row in db.execute("SELECT id,data FROM cases ORDER BY id")]
        history = await self.service.get_state(self.alice, case_id=old["id"])
        self.assertEqual(history["case"], old)
        self.assertEqual((await self.service.get_state(self.alice, chat_id="chat-a2"))["case"], current)
        with self.service._db() as db:
            after = [tuple(row) for row in db.execute("SELECT id,data FROM cases ORDER BY id")]
        self.assertEqual(before, after)
        self.chats["chat-a"]["user_id"] = "bob"
        denied = await self.service.get_state(self.alice, case_id=old["id"])
        self.assertEqual(denied["error"]["code"], "chat_forbidden")

    async def test_inaccessible_linked_chats_are_omitted_from_read_and_action_summaries(self):
        inaccessible = await self.step(await self.create(), "bind", chat_id="chat-a")
        current = await self.step(await self.create(), "bind", chat_id="chat-a2")
        self.chats["chat-a"]["user_id"] = "bob"
        state = await self.service.get_state(self.alice, chat_id="chat-a2")
        self.assertEqual([item["id"] for item in state["cases"]], [current["id"]])
        state = await self.act(current, "select", "install-t")
        self.assertTrue(state["ok"])
        self.assertEqual([item["id"] for item in state["cases"]], [current["id"]])
        with self.service._db() as db:
            self.assertIsNotNone(self.service._case(db, "alice", inaccessible["id"]))
        del self.chats["chat-a2"]
        self.assertEqual((await self.service.get_state(self.alice))["cases"], [])

    async def test_legacy_creation_timestamp_stays_unknown_without_a_read_migration(self):
        case = await self.create()
        with self.service._db(write=True) as db:
            saved = self.service._case(db, "alice", case["id"])
            del saved["created_at"]
            raw = workflow._dump(saved)
            db.execute("UPDATE cases SET data=? WHERE id=?", (raw, case["id"]))
        state = await self.service.get_state(self.alice, case_id=case["id"])
        self.assertIsNone(state["case"]["created_at"])
        self.assertIsNone(state["cases"][0]["created_at"])
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT data FROM cases WHERE id=?", (case["id"],)).fetchone()[0], raw)

    async def test_current_identity_and_user_ownership_cannot_be_forged(self):
        case = await self.create()
        bob = self.users["bob"]
        self.assertEqual((await self.service.get_state(bob))["cases"], [])
        for result in (await self.service.get_state(bob, case_id=case["id"]),
                       await self.act(case, "select", "db-j", user=bob),
                       await self.act(case, "run", "scope-j", {"confirm": True}, user=self.admin)):
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "case_not_found")
        forged = {"id": "alice", "role": "admin"}
        result = await self.service.handle_action(forged, {"action": "publish", "expected_revision": 0})
        self.assertEqual(result["error"]["code"], "admin_required")
        self.users["admin"]["role"] = "user"
        self.assertFalse((await self.service.get_state({"id": "admin", "role": "admin"}))["can_manage"])
        self.users.pop("alice")
        self.assertEqual((await self.service.get_state(forged))["error"]["code"], "unauthorized")

    async def test_existing_chat_ownership_and_one_case_per_chat_are_enforced(self):
        result = await self.service.handle_action(self.alice, {"action": "create", "chat_id": "chat-b"})
        self.assertEqual(result["error"]["code"], "chat_forbidden")
        case = await self.create()
        case = await self.step(case, "bind", chat_id="chat-a")
        duplicate = await self.service.handle_action(self.alice, {"action": "create", "chat_id": "chat-a"})
        self.assertEqual(duplicate["error"]["code"], "chat_already_bound")
        other = await self.create(site_id="hu-a")
        self.assertEqual((await self.act(other, "bind", chat_id="chat-a"))["error"]["code"], "chat_already_bound")
        self.assertEqual((await self.act(case, "select", "ap-j", chat_id="chat-a2"))["error"]["code"], "chat_mismatch")
        self.chats["chat-a"]["user_id"] = "bob"
        self.assertEqual((await self.service.get_state(self.alice, case_id=case["id"]))["error"]["code"], "chat_forbidden")
        self.assertEqual((await self.act(case, "run", "scope-j", {"confirm": True}))["error"]["code"], "chat_forbidden")

    async def test_selection_does_not_execute_and_stale_revision_is_rejected(self):
        case = await self.create()
        selected = await self.step(case, "select", "install-t")
        self.assertEqual(selected["jobs"], case["jobs"])
        stale = await self.act(case, "select", "ap-j")
        self.assertEqual(stale["error"]["code"], "revision_conflict")
        missing = await self.service.handle_action(self.alice, {"action": "run", "case_id": case["id"], "node_id": "scope-j"})
        self.assertEqual(missing["error"]["code"], "revision_conflict")
        self.assertEqual((await self.service.get_state(self.alice, case_id=case["id"]))["case"]["selected_id"], "install-t")

    async def test_prerequisites_manual_confirmation_and_missing_input_do_not_fake_success(self):
        case = await self.create()
        for node, code in (("db-j", "prerequisite_required"), ("scope-j", "confirmation_required")):
            result = await self.act(case, "run", node)
            self.assertEqual(result["error"]["code"], code)
        case = await self.ready(case)
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": ""}})
        result = await self.act(case, "run", "db-j")
        self.assertEqual(result["error"]["code"], "input_required")
        self.assertEqual((await self.service.get_state(self.alice, case_id=case["id"]))["case"], case)
        self.assertEqual(case["jobs"]["scope-j"]["history"][0]["kind"], "human_confirmation")

    async def test_multiple_checks_failure_skip_retry_and_history_are_persistent(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "db-j")
        self.assertEqual([check["status"] for check in case["jobs"]["db-j"]["checks"]], ["passed"] * 3)
        case = await self.step(case, "run", "ap-j")
        first = deepcopy(case["jobs"]["ap-j"]["history"])
        self.assertEqual([check["status"] for check in first[0]["checks"]], ["passed", "passed", "failed", "skipped"])
        self.assertEqual(case["node_states"]["interface-j"]["status"], "blocked")
        self.assertEqual(case["status"], "failed")
        self.assertEqual(case["node_states"]["setup-p"]["failed_count"], 1)
        self.assertEqual(case["node_states"]["install-t"]["failed_count"], 1)
        case = await self.step(case, "select", "interface-t")
        case = await self.step(case, "run", "ap-j")
        self.assertEqual(case["selected_id"], "interface-t")
        self.assertEqual(case["jobs"]["ap-j"]["history"][:1], first)
        self.assertEqual(case["jobs"]["ap-j"]["attempt"], 2)
        self.assertTrue(all(check["simulation"] for check in case["jobs"]["ap-j"]["checks"]))
        case = await self.step(case, "run", "interface-j")
        self.assertEqual(case["status"], "passed")
        self.assertEqual(case["progress"], {"done": 6, "total": 6})
        self.assertEqual(case["node_states"]["setup-p"]["failed_count"], 0)

    async def test_input_change_invalidates_only_dependent_results_preserving_evidence(self):
        definition = workflow._seed()
        definition["nodes"]["handoff-j"] = {
            **deepcopy(definition["nodes"]["scope-j"]), "id": "handoff-j", "name": "최종 인계 확인",
            "parent": "interface-t", "deps": ["interface-j"],
        }
        definition["nodes"]["interface-t"]["children"].append("handoff-j")
        await self.publish(definition)
        case = await self.ready(await self.create())
        for job in ("db-j", "ap-j", "ap-j", "interface-j"):
            case = await self.step(case, "run", job)
        self.assertEqual(case["status"], "in_progress")
        before = deepcopy(case)
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": "다른 승인 진단 대상"}})
        for job in ("db-j", "interface-j"):
            self.assertEqual(case["jobs"][job]["status"], "pending")
            self.assertEqual(case["jobs"][job]["history"], before["jobs"][job]["history"])
        self.assertEqual(case["jobs"]["ap-j"], before["jobs"]["ap-j"])
        self.assertEqual(case["node_states"]["interface-j"]["status"], "blocked")

    async def test_completed_execution_blocks_result_changes_and_keeps_new_runs_separate(self):
        case = await self.ready(await self.create())
        for job in ("db-j", "ap-j", "ap-j", "interface-j"):
            case = await self.step(case, "run", job)
        self.assertEqual(case["status"], "passed")
        for action, node_id, payload in (
                ("run", "db-j", {}), ("run", "setup-p", {}),
                ("run", "scope-j", {"confirm": True}), ("run", "scope-j", {"document": "변경 초안"}),
                ("update_inputs", "db-j", {"inputs": {"db": "다른 대상"}})):
            denied = await self.act(case, action, node_id, payload)
            self.assertEqual(denied["error"]["code"], "case_completed")
            self.assertIn("새 실행", denied["error"]["message"])
            self.assertEqual((await self.service.get_state(self.alice, case_id=case["id"]))["case"], case)
        # Completion does not prevent inspecting another node or binding a
        # finished pending execution when its first real chat message is saved.
        bound = await self.step(case, "bind", chat_id="chat-a")
        selected = await self.step(bound, "select", "ap-j")
        self.assertEqual(selected["jobs"], case["jobs"])
        newer = await self.create(site_id=case["site"]["id"], system=case["system"], process_id=case["process_id"])
        self.assertNotEqual(newer["id"], case["id"])
        self.assertEqual(newer["status"], "pending")
        self.assertEqual((await self.service.get_state(self.alice, case_id=case["id"]))["case"], selected)

    async def test_parent_execution_never_bulk_confirms_manual_jobs(self):
        case = await self.create()
        result = await self.act(case, "run", "setup-p", {"confirm": True})
        self.assertEqual(result["error"]["code"], "no_ready_jobs")
        case = await self.step(case, "run", "scope-j", {"confirm": True})
        case = await self.step(case, "run", "setup-p")
        self.assertEqual(case["jobs"]["infra-j"]["status"], "passed")
        self.assertEqual(case["jobs"]["install-j"]["status"], "pending")
        case = await self.step(case, "run", "install-j", {"confirm": True})
        case = await self.step(case, "run", "install-t")
        self.assertEqual(case["jobs"]["db-j"]["status"], "passed")
        self.assertEqual(case["jobs"]["ap-j"]["status"], "failed")

    async def test_parent_execution_keeps_evidence_when_sibling_input_is_missing(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": ""}})
        case = await self.step(case, "run", "install-t")
        self.assertEqual(case["jobs"]["db-j"]["status"], "blocked")
        self.assertEqual(case["jobs"]["db-j"]["attempt"], 0)
        self.assertEqual(case["jobs"]["ap-j"]["status"], "failed")
        self.assertEqual(case["jobs"]["ap-j"]["attempt"], 1)
        self.assertEqual(len(case["jobs"]["ap-j"]["history"]), 1)
        self.assertEqual(case["node_states"]["interface-j"]["status"], "blocked")

    async def test_process_boundary_and_country_conditions(self):
        case = await self.create(site_id="hu-a", system="FDC")
        self.assertFalse(case["node_states"]["interface-j"]["applicable"])
        self.assertEqual(case["node_states"]["interface-j"]["status"], "skipped")
        self.assertEqual(case["progress"]["total"], 5)
        self.assertNotIn("ops-j", case["jobs"])
        self.assertEqual((await self.act(case, "run", "ops-j"))["error"]["code"], "node_not_found")
        self.assertEqual((await self.act(case, "run", "interface-j"))["error"]["code"], "not_applicable")
        definition = workflow._seed()
        definition["nodes"]["infra-j"]["condition"] = "new-infra"
        definition["nodes"]["install-t"]["condition"] = "country:한국"
        await self.publish(definition)
        korean = await self.create(site_id="kr-ca")
        american = await self.create(site_id="us-a")
        self.assertTrue(korean["node_states"]["infra-j"]["applicable"])
        self.assertFalse(american["node_states"]["infra-j"]["applicable"])
        self.assertFalse(american["node_states"]["ap-j"]["applicable"])

    async def test_publish_requires_current_validation_and_freezes_existing_case(self):
        old = await self.create()
        state = await self.service.get_state(self.admin)
        definition = state["draft"]
        definition["nodes"]["db-j"]["name"] = "새 DB 검증"
        definition["sites"]["us-a"]["line"] = "검증 3라인"
        saved = await self.service.handle_action(self.admin, {"action": "save_draft", "expected_revision": 0,
                                                            "payload": {"definition": definition}})
        rev = saved["draft_revision"]
        failure = await self.service.handle_action(self.admin, {"action": "publish", "expected_revision": rev})
        self.assertEqual(failure["error"]["code"], "validation_required")
        for action in ("validate_draft", "publish"):
            result = await self.service.handle_action(self.admin, {"action": action, "expected_revision": rev})
            self.assertTrue(result["ok"], result)
        updated = await self.create()
        self.assertEqual(updated["version"], old["version"] + 1)
        self.assertEqual(updated["site"]["line"], "검증 3라인")
        self.assertEqual(updated["definition"]["nodes"]["db-j"]["name"], "새 DB 검증")
        self.assertEqual((await self.service.get_state(self.alice, case_id=old["id"]))["case"], old)
        stale = await self.service.handle_action(self.admin, {"action": "publish", "expected_revision": rev})
        self.assertEqual(stale["error"]["code"], "revision_conflict")

    async def test_incomplete_draft_can_save_but_cannot_execute_or_publish(self):
        definition = workflow._seed()
        definition["nodes"]["db-j"]["deps"] = ["unfinished-job"]
        saved = await self.service.handle_action(self.admin, {"action": "save_draft", "expected_revision": 0,
                                                            "payload": {"definition": definition}})
        self.assertTrue(saved["ok"])
        for action in ("validate_draft", "publish"):
            result = await self.service.handle_action(self.admin, {"action": action, "expected_revision": 1})
            self.assertEqual(result["error"]["code"], "invalid_definition")
        self.assertEqual((await self.create())["version"], 1)

    async def test_malformed_action_create_and_unreadable_draft_are_rejected(self):
        bodies = [{"action": {}}, {"action": "create", "payload": {"process_id": {}}},
                  {"action": "create", "payload": {"site_id": []}},
                  {"action": "save_draft", "expected_revision": 0, "payload": {"definition": {}}}]
        for body in bodies:
            result = await self.service.handle_action(self.admin, body)
            self.assertFalse(result["ok"], body)
        for reference in ({"id": "skill"}, ["skill"]):
            definition = workflow._seed()
            definition["skills"]["connection"].update(source="open_webui", reference=reference)
            result = await self.service.handle_action(self.admin, {"action": "save_draft", "expected_revision": 0,
                                                                  "payload": {"definition": definition}})
            self.assertEqual(result["error"]["code"], "invalid_definition")
        self.assertEqual((await self.service.get_state(self.admin))["draft_revision"], 0)

    async def test_external_tool_reference_is_blocked_and_never_executed_as_mock(self):
        definition = workflow._seed()
        definition["tools"]["health"].update(source="open_webui", reference="actual-tool", adapter="unavailable")
        definition["nodes"]["ap-j"]["failOnce"] = False
        await self.publish(definition)
        case = await self.ready(await self.create())
        with patch("subprocess.run", side_effect=AssertionError("No scripts may be invoked")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("No business network calls")):
            case = await self.step(case, "run", "ap-j")
        self.assertEqual(case["jobs"]["ap-j"]["status"], "blocked")
        self.assertEqual([check["status"] for check in case["jobs"]["ap-j"]["checks"]], ["passed", "passed", "blocked", "skipped"])
        self.assertFalse(case["jobs"]["ap-j"]["checks"][2]["simulation"])
        self.assertEqual(case["jobs"]["ap-j"]["history"][0]["status"], "blocked")

    async def test_selected_context_inherits_instructions_and_current_accessible_skill(self):
        definition = workflow._seed()
        definition["nodes"]["setup-p"]["instructions"] = "공장 범위를 먼저 확인"
        definition["nodes"]["db-j"]["instructions"] = "DB 식별 결과를 설명"
        definition["skills"]["webui-skill:read"] = {"id": "webui-skill:read", "name": "기존 읽기 스킬",
            "type": "skill", "source": "open_webui", "reference": "read", "body": ""}
        definition["nodes"]["db-j"]["skills"] = ["webui-skill:read"]
        await self.publish(definition)
        assets = {"tools": [{"id": "allowed", "name": "기존 도구"}], "skills": [{"id": "read", "name": "기존 읽기 스킬"}],
                  "skill_bodies": {"read": "승인된 읽기 절차"}, "skill_versions": {"read": 100}}
        self.service.asset_lookup = AsyncMock(return_value=assets)
        case = await self.step(await self.create(), "select", "db-j")
        self.assertEqual(case["context"]["instructions"], ["공장 범위를 먼저 확인", "DB 식별 결과를 설명"])
        self.assertEqual([skill["id"] for skill in case["context"]["skills"]], ["common", "setup", "connection", "webui-skill:read"])
        self.assertEqual(case["context"]["skills"][-1]["body"], "승인된 읽기 절차")
        self.assertEqual(case["context"]["skills"][-1]["snapshot_updated_at"], 100)
        self.assertNotIn("_skill_snapshots", case)
        self.assertEqual(case["definition"]["skills"]["webui-skill:read"]["body"], "")
        assets["skill_bodies"]["read"] = "갱신된 스킬 본문"
        assets["skill_versions"]["read"] = 200
        state = await self.service.get_state(self.alice, case_id=case["id"])
        self.assertEqual(state["case"]["context"]["skills"][-1]["body"], "승인된 읽기 절차")
        self.assertNotIn("skill_bodies", state["catalog"])
        self.assertEqual(state["catalog"]["available_tools"], assets["tools"])
        case = await self.ready(case)
        self.service.asset_lookup = AsyncMock(return_value={"tools": [], "skills": [], "skill_bodies": {}})
        state = await self.service.get_state(self.alice, case_id=case["id"])
        self.assertFalse(state["case"]["context"]["skills"][-1]["available"])
        self.assertEqual(state["case"]["context"]["skills"][-1]["body"], "")
        self.assertNotIn("승인된 읽기 절차", workflow._dump(state))
        self.assertNotIn("_skill_snapshots", workflow._dump(state))
        failed = await self.act(case, "run", "db-j")
        self.assertEqual(failed["error"]["code"], "skill_unavailable")

    async def test_actual_draft_content_needs_review_before_completion(self):
        definition = workflow._seed()
        definition["nodes"]["scope-j"]["mode"] = "draft"
        await self.publish(definition)
        case = await self.create()
        self.assertEqual((await self.act(case, "run", "scope-j", {"confirm": True}))["error"]["code"], "draft_required")
        case = await self.step(case, "run", "scope-j", {"document": "대화에서 작성한 공장 A 셋업 범위"})
        self.assertEqual(case["jobs"]["scope-j"]["status"], "review")
        self.assertEqual(case["jobs"]["scope-j"]["attempt"], 0)
        case = await self.step(case, "run", "scope-j", {"confirm": True})
        self.assertEqual(case["jobs"]["scope-j"]["status"], "passed")
        self.assertIn("공장 A", case["jobs"]["scope-j"]["document"])


class DefinitionValidationTests(unittest.TestCase):
    def test_cycles_missing_references_wrong_parent_duplicates_and_common_policy(self):
        changes = [
            lambda d: d["nodes"]["scope-j"]["deps"].append("interface-j"),
            lambda d: d["nodes"]["install-t"]["deps"].append("db-j"),
            lambda d: d["nodes"]["db-j"]["deps"].append("deleted"),
            lambda d: d["nodes"]["db-j"].update(parent="setup-p"),
            lambda d: d["nodes"]["install-t"]["children"].append("db-j"),
            lambda d: d["roots"]["setup"].append("setup-p"),
            lambda d: d["skills"]["common"].update(body="공통 규칙 삭제"),
            lambda d: d["nodes"]["db-j"]["bindings"].update(gateway="ap"),
            lambda d: d["nodes"]["db-j"].update(condition="country:존재하지않음"),
            lambda d: d["nodes"]["setup-p"].update(tools=["network"]),
            lambda d: d["tools"]["gateway"].update(source="open_webui", reference="actual"),
            lambda d: d["nodes"]["scope-j"].update(deps=["ops-j"]),
        ]
        for mutate in changes:
            with self.subTest(change=changes.index(mutate)):
                definition = workflow._seed()
                mutate(definition)
                self.assertTrue(workflow.validate_definition(definition))

    def test_malformed_editor_fields_return_errors_instead_of_crashing(self):
        for field, bad in (("children", {}), ("deps", [None]), ("parent", []), ("bindings", []),
                           ("condition", {}), ("systems", "EMS"), ("name", 17), ("tools", [None]), ("mode", None)):
            with self.subTest(field=field):
                definition = workflow._seed()
                definition["nodes"]["db-j"][field] = bad
                self.assertTrue(workflow.validate_definition(definition))
        definition = workflow._seed()
        del definition["tools"]["gateway"]["input"]
        self.assertTrue(workflow.validate_definition(definition))
        definition = workflow._seed()
        del definition["nodes"]["db-j"]["parent"]
        self.assertTrue(workflow.validate_definition(definition))
        for group, key in (("tools", "gateway"), ("skills", "setup")):
            definition = workflow._seed()
            definition[group][key]["source"] = {"invalid": "object"}
            self.assertTrue(workflow.validate_definition(definition))

    def test_add_reorder_move_and_remove_nodes_with_correct_links_are_valid(self):
        definition = workflow._seed()
        additional = deepcopy(definition["nodes"]["scope-j"])
        additional.update(id="scope2-j", name="범위 추가 확인", parent="prep-t")
        definition["nodes"]["scope2-j"] = additional
        definition["nodes"]["prep-t"]["children"].insert(0, "scope2-j")
        self.assertEqual(workflow.validate_definition(definition), [])
        additional["parent"] = "install-t"
        definition["nodes"]["prep-t"]["children"].remove("scope2-j")
        definition["nodes"]["install-t"]["children"].append("scope2-j")
        self.assertEqual(workflow.validate_definition(definition), [])
        definition["nodes"].pop("scope2-j")
        definition["nodes"]["install-t"]["children"].remove("scope2-j")
        self.assertEqual(workflow.validate_definition(definition), [])


try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI = None


@unittest.skipIf(FastAPI is None, "FastAPI/httpx dependencies unavailable")
class WorkflowRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        users = {"alice": {"id": "alice", "role": "user"}, "admin": {"id": "admin", "role": "admin"}}
        self.service = workflow.WorkflowService(Path(temporary.name) / "ees-work.sqlite3", users.get,
            lambda chat_id: {"id": chat_id, "user_id": "alice"} if chat_id == "chat-a" else None)
        self.patch = patch.object(workflow, "_service", self.service)
        self.patch.start()
        self.addCleanup(self.patch.stop)

        async def verified(request: Request):
            user = users.get(request.headers.get("x-test-user"))
            if user is None:
                raise HTTPException(401, "Unauthenticated fixture")
            return user

        app = FastAPI()
        workflow.install(app, verified)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_routes_use_verified_identity_and_no_store(self):
        self.assertEqual(self.client.get("/api/ees-work/state").status_code, 401)
        self.assertEqual(self.client.post("/api/ees-work/action", json={"action": "create"}).status_code, 401)
        headers = {"x-test-user": "alice"}
        created = self.client.post("/api/ees-work/action", headers=headers, json={"action": "create", "chat_id": "chat-a",
                                                                                  "user": {"id": "admin", "role": "admin"}})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.headers["cache-control"], "no-store")
        case = created.json()["case"]
        actual = self.client.get("/api/ees-work/state?chat_id=chat-a", headers=headers)
        self.assertEqual(actual.json()["case"]["id"], case["id"])
        denied = self.client.post("/api/ees-work/action", headers=headers,
                                 json={"action": "publish", "expected_revision": 0, "role": "admin"})
        self.assertEqual(denied.status_code, 403)
        stale = self.client.post("/api/ees-work/action", headers=headers,
                                json={"action": "select", "case_id": case["id"], "node_id": "db-j", "expected_revision": 99})
        self.assertEqual(stale.status_code, 409)


if __name__ == "__main__":
    unittest.main()
