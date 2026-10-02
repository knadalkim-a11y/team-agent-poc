"""Scoped authoring service/API acceptance with real temporary SQLite stores.

User/group and registry lookups are synthetic; no Native login, production
account, business endpoint or secret is used. Native membership/UI acceptance
is a separate gate. Restore coverage requires the captured supported old module.
"""

import asyncio
from contextlib import closing
from copy import deepcopy
import importlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from workflow_fixture import load_legacy_workflow, arrange_legacy_catalog


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agent-pack/skills/ees-work-demo/scripts"
PACKAGE = ModuleType("ees_authoring_test_subject")
PACKAGE.__path__ = [str(SOURCE)]
sys.modules[PACKAGE.__name__] = PACKAGE
workflow = importlib.import_module(PACKAGE.__name__ + ".ees_workflow")
historical = __import__("workflow_fixture").historical_facade(PACKAGE.__name__)


class AuthoringFixture:
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ees-authoring-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "ees-work.sqlite3"
        self.users = {key: {"id": key, "role": role} for key, role in (
            ("admin", "admin"), ("ems-a", "user"), ("ems-b", "user"),
            ("apc", "user"), ("dual", "user"), ("ordinary", "user"), ("pending", "pending"))}
        self.groups = {"g-ems": {"id": "g-ems", "name": "EMS 담당"},
                       "g-apc": {"id": "g-apc", "name": "APC 담당"},
                       "g-fdc": {"id": "g-fdc", "name": "FDC 담당"}}
        self.memberships = {"ems-a": {"g-ems"}, "ems-b": {"g-ems"}, "apc": {"g-apc"},
                            "dual": {"g-ems", "g-fdc"}, "pending": {"g-ems"}}
        self.assets = {"tools": [], "skills": [], "skill_bodies": {}, "skill_versions": {}, "available": True}
        self.fail_groups = False
        self.requests = 0
        self.chats = {"chat-ems": {"id": "chat-ems", "user_id": "ems-a"}}
        self.service = self.new_service()
        arrange_legacy_catalog(self.service)
        for system, group in (("EMS", "g-ems"), ("APC", "g-apc"), ("FDC", "g-fdc")):
            result = await self.action("admin", "set_system_group", system_id=system,
                                       expected_mapping_revision=0, payload={"group_id": group, "active": True})
            self.assertTrue(result["ok"], result)

    async def user_lookup(self, key):
        return deepcopy(self.users.get(key))

    async def group_lookup(self, key):
        if self.fail_groups:
            raise RuntimeError("PRIVATE-GROUP-STORE-ERROR")
        return [deepcopy(self.groups[group]) for group in self.memberships.get(key, ()) if group in self.groups]

    async def group_list_lookup(self):
        if self.fail_groups:
            raise RuntimeError("PRIVATE-GROUP-STORE-ERROR")
        return list(deepcopy(self.groups).values())

    def new_service(self):
        return historical.WorkflowService(self.database, self.user_lookup,
            lambda key: deepcopy(self.chats.get(key)), lambda _: deepcopy(self.assets),
            group_lookup=self.group_lookup, group_list_lookup=self.group_list_lookup)

    def principal(self, actor):
        return {"id": actor, "role": "admin" if actor == "admin" else "user"}

    def body(self, action, process=None, **extra):
        self.requests += 1
        body = {"action": action, "request_id": "authoring-test-" + str(self.requests), "payload": {}}
        if process:
            body.update(process_id=process["process_id"], system_id=process["owner_system"],
                        expected_draft_revision=process["draft_revision"],
                        expected_owner_revision=process["owner_revision"])
        body.update(extra)
        return body

    async def action(self, actor, action, process=None, **extra):
        return await self.service.authoring_action(self.principal(actor), self.body(action, process, **extra))

    async def read(self, actor, process=None, system="EMS"):
        return await self.service.get_authoring(self.principal(actor),
            system_id=process["owner_system"] if process else system,
            process_id=process["process_id"] if process else "")

    async def create(self, actor="ems-a", system="EMS", name="교대 시작 설비 점검"):
        result = await self.action(actor, "create", system_id=system,
                                   payload={"name": name, "category": "ops"})
        self.assertTrue(result["ok"], result)
        return result["process"]

    async def save(self, actor, process, document):
        result = await self.action(actor, "save_draft", process, payload={"workflow": document})
        self.assertTrue(result["ok"], result)
        return result["process"]

    async def publish(self, actor, process):
        checked = await self.action(actor, "validate_draft", process)
        self.assertTrue(checked["ok"], checked)
        result = await self.action(actor, "publish", checked["process"])
        self.assertTrue(result["ok"], result)
        return result["process"]

    def assert_denied(self, result, *codes):
        self.assertFalse(result.get("ok"), result)
        if codes:
            self.assertIn(result["error"]["code"], codes, result)
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("PRIVATE-GROUP-STORE-ERROR", rendered)
        self.assertNotIn("FOREIGN-UNPUBLISHED-TEXT", rendered)

    def catalog(self):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute("SELECT published,draft,revision,validated FROM catalog WHERE id=1").fetchone()
        return row

    def business_rows(self):
        """Audit rejection rows may grow; protected data must stay unchanged."""
        with closing(sqlite3.connect(self.database)) as db:
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: sorted(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                    for name in names if not any(word in name for word in ("audit", "sqlite_"))}

    def audit_table(self):
        with closing(sqlite3.connect(self.database)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='authoring_audit'")]
        self.assertEqual(len(tables), 1, tables)
        return tables[0]

    def audit_rows(self):
        table = self.audit_table()
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]


class SystemAuthoringTests(AuthoringFixture, unittest.IsolatedAsyncioTestCase):
    async def test_fixture_read_helpers_release_sqlite_connections(self):
        # sqlite3's transaction context does not close the connection. Holding
        # each returned object makes leaks observable on Linux too, before a
        # Windows TemporaryDirectory cleanup attempts to remove the open file.
        original_connect = sqlite3.connect
        for helper in (self.catalog, self.business_rows, self.audit_table, self.audit_rows):
            connections = []

            def tracked_connect(*args, **kwargs):
                connection = original_connect(*args, **kwargs)
                connections.append(connection)
                return connection

            with self.subTest(helper=helper.__name__):
                try:
                    with patch.object(sqlite3, "connect", side_effect=tracked_connect):
                        helper()
                    self.assertTrue(connections, "The real SQLite read must run")
                    for connection in connections:
                        with self.assertRaises(sqlite3.ProgrammingError):
                            connection.execute("SELECT 1")
                finally:
                    for connection in connections:
                        connection.close()

    async def test_sa01_02_current_groups_grant_systems_without_changing_native_role(self):
        for actor, expected in (("ordinary", []), ("ems-a", ["EMS"]), ("ems-b", ["EMS"]),
                                ("dual", ["EMS", "FDC"]), ("apc", ["APC"])):
            with self.subTest(actor=actor):
                result = await self.service.capabilities(self.principal(actor))
                self.assertTrue(result["ok"], result)
                capabilities = result.get("capabilities", result)
                self.assertEqual(set(capabilities["managed_systems"]), set(expected))
                self.assertFalse(capabilities["is_admin"])
                self.assertEqual(self.users[actor]["role"], "user")
        process = await self.create()
        current = (await self.read("ems-b", process))["process"]
        document = deepcopy(current["workflow"])
        document["nodes"][current["process_id"]]["description"] = "같은 시스템의 다른 담당자 변경"
        changed = await self.save("ems-b", current, document)
        self.assertEqual((await self.read("ems-a", process))["process"]["workflow"], changed["workflow"])
        state = await self.service.get_state(self.principal("ems-a"))
        self.assertFalse(state["can_manage"])
        self.assertIsNone(state["draft"])

    async def test_sa03_group_identity_rename_delete_and_same_name_replacement(self):
        process = await self.create()
        self.groups["g-ems"]["name"] = "이름만 바뀐 담당 그룹"
        self.assertTrue((await self.read("ems-a", process))["ok"])
        del self.groups["g-ems"]
        self.groups["replacement"] = {"id": "replacement", "name": "이름만 바뀐 담당 그룹"}
        self.memberships["ems-a"] = {"replacement"}
        self.assert_denied(await self.read("ems-a", process))
        self.assert_denied(await self.action("ems-a", "save_draft", process,
                                             payload={"workflow": process["workflow"]}))

    async def test_sa04_invalid_account_and_group_failure_fail_closed_only_for_authoring(self):
        process = await self.create()
        self.assert_denied(await self.read("pending", process), "unauthorized")
        del self.users["ems-b"]
        self.assert_denied(await self.read("ems-b", process), "unauthorized")
        self.fail_groups = True
        self.assert_denied(await self.read("ems-a", process), "authoring_authorization_unavailable")
        self.assert_denied(await self.action("ems-a", "save_draft", process,
            payload={"workflow": process["workflow"]}), "authoring_authorization_unavailable")
        runtime = await self.service.get_state(self.principal("ordinary"))
        self.assertTrue(runtime["ok"], runtime)
        self.assertIn("setup-p", runtime["catalog"]["nodes"])

    async def test_sa05_06_07_forged_authority_and_foreign_draft_never_cross_server_scope(self):
        foreign = await self.create("apc", "APC", "APC 비공개 초안")
        document = deepcopy(foreign["workflow"])
        document["nodes"][foreign["process_id"]]["instructions"] = "FOREIGN-UNPUBLISHED-TEXT"
        foreign = await self.save("apc", foreign, document)
        own = await self.create()
        before = self.business_rows()
        self.assert_denied(await self.action("ordinary", "create", system_id="EMS",
                                            payload={"name": "권한 없는 생성", "category": "ops"}))
        self.assert_denied(await self.action("dual", "create", system_id="APC",
                                            payload={"name": "겸임 범위 밖 생성", "category": "ops"}))
        for actor in ("ordinary", "ems-a"):
            for action in ("save_draft", "validate_draft", "publish", "transfer_owner", "delete", "disable"):
                with self.subTest(actor=actor, action=action):
                    body = self.body(action, foreign, system_id="EMS", user_id="admin", role="admin",
                                     managed_systems=["APC"], is_admin=True,
                                     payload={"workflow": document, "owner_system": "EMS"})
                    self.assert_denied(await self.service.authoring_action(self.principal(actor), body))
                    # Also submit a syntactically valid request. Rejecting extra
                    # authority fields alone does not prove process ownership.
                    payload = {"workflow": document} if action == "save_draft" else {
                        "owner_system": "EMS"} if action == "transfer_owner" else {}
                    self.assert_denied(await self.action(actor, action, foreign, payload=payload))
            self.assert_denied(await self.read(actor, foreign))
        listing = await self.read("ems-a")
        self.assertTrue(listing["ok"], listing)
        self.assertNotIn(foreign["process_id"], json.dumps(listing, ensure_ascii=False))
        for action, payload in (("set_system_group", {"group_id": "g-ems", "active": True}),
                                ("transfer_owner", {"owner_system": "APC"})):
            self.assert_denied(await self.action("ems-a", action, own, payload=payload))
        self.assertEqual(self.business_rows(), before)

    async def test_sa08_entire_payload_is_rejected_for_cross_process_and_shared_data_injection(self):
        own, other = await self.create(), await self.create(name="같은 시스템의 다른 절차")
        baseline = self.business_rows()
        base = own["workflow"]
        mutations = []
        for key, value in (("roots", {"ops": [other["process_id"]]}), ("sites", {"us-a": {"name": "바뀐 공장"}}),
                           ("owner_system", "APC"), ("systems", ["EMS", "APC"])):
            document = deepcopy(base)
            document[key] = value
            mutations.append((key, document))
        document = deepcopy(base)
        document["nodes"].update(deepcopy(other["workflow"]["nodes"]))
        mutations.append(("foreign nodes", document))
        document = deepcopy(base)
        document["nodes"][own["process_id"]]["parent"] = other["process_id"]
        mutations.append(("reparent root", document))
        document = deepcopy(base)
        job_id = next(key for key, node in document["nodes"].items() if node["type"] == "j")
        document["nodes"][job_id]["deps"] = [next(key for key, node in other["workflow"]["nodes"].items() if node["type"] == "j")]
        mutations.append(("cross process prerequisite", document))
        document = deepcopy(base)
        document["skills"]["common"] = {"id": "common", "name": "변경한 공통 정책", "body": "forged"}
        mutations.append(("common policy", document))
        for label, document in mutations:
            with self.subTest(payload=label):
                self.assert_denied(await self.action("ems-a", "save_draft", own, payload={"workflow": document}))
                self.assertEqual(self.business_rows(), baseline)

    async def test_sa09_10_revocation_rechecks_reads_writes_and_receipt_replay(self):
        process = await self.create()
        checked = await self.action("ems-a", "validate_draft", process)
        self.assertTrue(checked["ok"], checked)
        request = self.body("publish", checked["process"])
        first = await self.service.authoring_action(self.principal("ems-a"), request)
        self.assertTrue(first["ok"], first)
        published = self.catalog()
        replay = await self.service.authoring_action(self.principal("ems-a"), request)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(self.catalog(), published)
        self.memberships["ems-a"].clear()
        self.assert_denied(await self.service.authoring_action(self.principal("ems-a"), request))
        self.assert_denied(await self.read("ems-a", process))
        for action in ("save_draft", "validate_draft", "publish"):
            self.assert_denied(await self.action("ems-a", action, first["process"],
                                                payload={"workflow": process["workflow"]}))
        self.assertEqual(self.catalog(), published)
        self.assertTrue((await self.service.get_state(self.principal("ems-a")))["ok"])
        self.memberships["ems-a"].add("g-ems")
        self.users["ems-a"]["role"] = "pending"
        self.assert_denied(await self.service.authoring_action(self.principal("ems-a"), request), "unauthorized")

    async def test_sa13_14_new_authoring_publishes_for_other_user_without_sharing_cases(self):
        process = await self.publish("ems-a", await self.create(name="교대조 신규 설비 인수 확인"))
        self.assertNotIn(process["process_id"], ("setup-p", "ops-p", "incident-p"))
        created = await self.service.handle_action(self.principal("ordinary"), {
            "action": "create", "payload": {"site_id": "us-a", "system": "EMS", "process_id": process["process_id"]}})
        self.assertTrue(created["ok"], created)
        case = created["case"]
        self.assertEqual(case["process_id"], process["process_id"])
        self.assertTrue(all(job["attempt"] == 0 for job in case["jobs"].values()))
        hidden = await self.service.get_state(self.principal("ems-a"), case_id=case["id"])
        self.assert_denied(hidden, "case_not_found")
        job_id = next(key for key, node in process["workflow"]["nodes"].items() if node["type"] == "j")
        confirmed = await self.service.handle_action(self.principal("ordinary"), {
            "action": "run", "case_id": case["id"], "node_id": job_id,
            "expected_revision": case["revision"], "payload": {"confirm": True}})
        self.assertTrue(confirmed["ok"], confirmed)
        record = confirmed["case"]["jobs"][job_id]["history"][-1]
        self.assertEqual(record["kind"], "human_confirmation")
        self.assertEqual(record.get("checks", []), [])

    async def test_sa15_same_process_concurrent_saves_have_one_winner(self):
        process = await self.create()
        requests = []
        for actor, description in (("ems-a", "첫 담당자 입력"), ("ems-b", "두 번째 담당자 입력")):
            document = deepcopy(process["workflow"])
            document["nodes"][process["process_id"]]["description"] = description
            requests.append((actor, self.body("save_draft", process, payload={"workflow": document})))
        async def threaded(actor, body):
            return await asyncio.to_thread(lambda: asyncio.run(self.service.authoring_action(self.principal(actor), body)))
        results = await asyncio.gather(*(threaded(actor, body) for actor, body in requests))
        self.assertEqual(sum(result["ok"] for result in results), 1, results)
        rejected = next(result for result in results if not result["ok"])
        self.assert_denied(rejected, "draft_revision_conflict")
        current = (await self.read("ems-a", process))["process"]
        winner = next(result["process"] for result in results if result["ok"])
        self.assertEqual(current["workflow"], winner["workflow"])
        self.assertEqual(current["draft_revision"], process["draft_revision"] + 1)

    async def test_sa16_17_different_process_publications_merge_latest_catalog(self):
        processes = [("ems-a", await self.create(name="EMS 첫 번째")),
                     ("ems-b", await self.create("ems-b", name="EMS 두 번째")),
                     ("apc", await self.create("apc", "APC", "APC 첫 번째"))]
        requests = []
        for actor, process in processes:
            checked = await self.action(actor, "validate_draft", process)
            self.assertTrue(checked["ok"], checked)
            requests.append((actor, self.body("publish", checked["process"])))
        initial = json.loads(self.catalog()[0])
        async def threaded(actor, body):
            return await asyncio.to_thread(lambda: asyncio.run(self.service.authoring_action(self.principal(actor), body)))
        results = await asyncio.gather(*(threaded(actor, body) for actor, body in requests))
        self.assertTrue(all(result["ok"] for result in results), results)
        current = json.loads(self.catalog()[0])
        self.assertEqual(current["version"], initial["version"] + 3)
        for actor, process in processes:
            self.assertIn(process["process_id"], current["roots"]["ops"])
            for node_id, node in process["workflow"]["nodes"].items():
                self.assertEqual(current["nodes"][node_id], node)
        for key in ("tools", "skills", "sites", "systems"):
            self.assertEqual(current[key], initial[key])

    async def test_sa18_exact_validation_is_invalid_after_draft_or_owner_changes(self):
        process = await self.create()
        checked = await self.action("ems-a", "validate_draft", process)
        self.assertTrue(checked["ok"], checked)
        document = deepcopy(process["workflow"])
        document["nodes"][process["process_id"]]["description"] = "검사 후 한 글자 수정"
        changed = await self.save("ems-a", checked["process"], document)
        self.assert_denied(await self.action("ems-a", "publish", changed), "validation_required")
        checked = await self.action("ems-a", "validate_draft", changed)
        self.assertTrue(checked["ok"], checked)
        transferred = await self.action("admin", "transfer_owner", checked["process"], payload={"owner_system": "COMMON"})
        self.assertTrue(transferred["ok"], transferred)
        self.assert_denied(await self.action("ems-a", "publish", checked["process"]))
        self.assert_denied(await self.action("admin", "publish", transferred["process"]), "validation_required")

    async def test_sa19_publish_and_audit_failure_roll_back_one_transaction(self):
        process = await self.create()
        checked = await self.action("ems-a", "validate_draft", process)
        self.assertTrue(checked["ok"], checked)
        before = self.business_rows()
        audit_before = self.audit_rows()
        audit = self.audit_table()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TRIGGER test_reject_audit BEFORE INSERT ON "' + audit + '" '
                       "BEGIN SELECT RAISE(ABORT,'SYNTHETIC-AUDIT-WRITE-FAILURE'); END")
        try:
            result = await self.action("ems-a", "publish", checked["process"])
            self.assert_denied(result)
            self.assertNotIn("SYNTHETIC-AUDIT-WRITE-FAILURE", json.dumps(result))
            self.assertEqual(self.business_rows(), before)
            self.assertEqual(self.audit_rows(), audit_before)
        finally:
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute("DROP TRIGGER test_reject_audit")
        published = await self.action("ems-a", "publish", checked["process"])
        self.assertTrue(published["ok"], published)
        self.assertIn(process["process_id"], json.loads(self.catalog()[0])["nodes"])

    async def test_sa19_invalid_merged_document_does_not_partially_publish(self):
        process = await self.create()
        document = deepcopy(process["workflow"])
        job_id = next(key for key, node in document["nodes"].items() if node["type"] == "j")
        document["nodes"][job_id]["mode"] = "tool"
        document["nodes"][job_id]["tools"] = []
        stored = await self.save("ems-a", process, document)
        before = self.catalog()
        checked = await self.action("ems-a", "validate_draft", stored)
        self.assert_denied(checked)
        self.assert_denied(await self.action("ems-a", "publish", stored))
        self.assertEqual(self.catalog(), before)

    async def test_sa20_system_scope_and_unassigned_processes_cannot_be_self_assigned(self):
        process = await self.create()
        for scope in ([], ["EMS", "APC"], ["APC"]):
            document = deepcopy(process["workflow"])
            document["nodes"][process["process_id"]]["systems"] = scope
            self.assert_denied(await self.action("ems-a", "save_draft", process, payload={"workflow": document}))
        self.assert_denied(await self.service.get_authoring(self.principal("ems-a"), system_id="EMS", process_id="setup-p"))
        admin = await self.service.get_authoring(self.principal("admin"), system_id="UNASSIGNED", process_id="setup-p")
        self.assertTrue(admin["ok"], admin)
        self.assertEqual(admin["process"]["owner_system"], "UNASSIGNED")
        before = self.business_rows()
        resolved = await self.service.get_authoring(self.principal("admin"), process_id="setup-p")
        self.assertTrue(resolved["ok"], resolved)
        self.assertEqual(resolved["system_id"], "UNASSIGNED")
        self.assertEqual(resolved["process"], admin["process"])
        self.assert_denied(await self.service.get_authoring(self.principal("ems-a"), process_id="setup-p"))
        self.assertEqual(self.business_rows(), before, "Owner lookup is read-only and still checks process authorization")
        self.assert_denied(await self.action("admin", "transfer_owner", admin["process"], payload={"owner_system": "EMS"}))
        self.assertEqual(self.business_rows(), before, "Assigning an existing multi-system P cannot silently narrow its scope")

    async def test_sa21_copy_uses_new_ids_and_keeps_source_and_frozen_case(self):
        original = await self.publish("ems-a", await self.create())
        created = await self.service.handle_action(self.principal("ordinary"), {"action": "create", "payload": {
            "site_id": "us-a", "system": "EMS", "process_id": original["process_id"]}})
        self.assertTrue(created["ok"], created)
        old_case = deepcopy(created["case"])
        result = await self.action("ems-b", "copy", system_id="EMS",
            payload={"source_process_id": original["process_id"], "name": "복사한 새 점검 절차"})
        self.assertTrue(result["ok"], result)
        copied = result["process"]
        self.assertTrue(set(copied["workflow"]["nodes"]).isdisjoint(original["workflow"]["nodes"]))
        copied_ids = set(copied["workflow"]["nodes"])
        for node in copied["workflow"]["nodes"].values():
            self.assertTrue(set(node["children"] + node["deps"]) <= copied_ids)
            self.assertTrue(node["parent"] is None or node["parent"] in copied_ids)
        self.assertEqual((await self.read("ems-a", original))["process"]["workflow"], original["workflow"])
        self.assertEqual((await self.service.get_state(self.principal("ordinary"), case_id=old_case["id"]))["case"], old_case)

    async def test_sa22_disable_prevents_new_cases_without_rewriting_existing_snapshots(self):
        process = await self.publish("ems-a", await self.create())
        payload = {"site_id": "us-a", "system": "EMS", "process_id": process["process_id"]}
        old = await self.service.handle_action(self.principal("ordinary"), {"action": "create", "payload": payload})
        self.assertTrue(old["ok"], old)
        disabled = await self.action("ems-a", "disable", process)
        self.assertTrue(disabled["ok"], disabled)
        refused = await self.service.handle_action(self.principal("ordinary"), {"action": "create", "payload": payload})
        self.assert_denied(refused)
        restored = await self.service.get_state(self.principal("ordinary"), case_id=old["case"]["id"])
        self.assertEqual(restored["case"], old["case"])
        self.assert_denied(await self.action("ems-a", "delete", disabled["process"]))
        draft = await self.create(name="삭제할 미게시 초안")
        catalog = self.catalog()
        deleted = await self.action("ems-a", "delete", draft)
        self.assertTrue(deleted["ok"], deleted)
        self.assertEqual(self.catalog(), catalog)
        self.assert_denied(await self.read("ems-a", draft))

    async def test_sa24_legacy_whole_catalog_writes_are_closed_even_to_admin(self):
        before = self.business_rows()
        for actor in ("ordinary", "ems-a", "admin"):
            for action in ("save_draft", "validate_draft", "publish"):
                with self.subTest(actor=actor, action=action):
                    result = await self.service.handle_action(self.principal(actor), {
                        "action": action, "expected_revision": 0, "payload": {"definition": workflow._seed()}})
                    self.assert_denied(result)
                    if actor == "admin":
                        self.assertEqual(result["error"]["code"], "authoring_upgrade_required")
        self.assertEqual(self.business_rows(), before)
        self.assertTrue((await self.service.handle_action(self.principal("ordinary"), {"action": "create"}))["ok"])

    async def test_sa28_audit_uses_verified_actor_revisions_and_never_copies_document(self):
        process = await self.create()
        document = deepcopy(process["workflow"])
        document["nodes"][process["process_id"]]["instructions"] = "SYNTHETIC-PRIVATE-DOCUMENT-NOT-FOR-AUDIT"
        stored = await self.save("ems-a", process, document)
        published = await self.publish("ems-b", stored)
        rows = self.audit_rows()
        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertIn("ems-a", serialized)
        self.assertIn("ems-b", serialized)
        self.assertIn(process["process_id"], serialized)
        self.assertIn("EMS", serialized)
        self.assertNotIn("SYNTHETIC-PRIVATE-DOCUMENT-NOT-FOR-AUDIT", serialized)
        self.assertNotIn("FOREIGN-UNPUBLISHED-TEXT", serialized)
        record = next(row for row in rows if row["action"] == "publish")
        self.assertEqual((record["actor"], record["process_id"], record["system_id"]),
                         ("ems-b", process["process_id"], "EMS"))
        self.assertEqual(record["before_revision"], stored["draft_revision"])
        self.assertEqual(record["after_revision"], published["draft_revision"])
        self.assertEqual(record["owner_revision"], published["owner_revision"])
        self.assertRegex(record["after_hash"], r"^[a-f0-9]{64}$")
        self.assertTrue(record["request_id"] and record["created_at"])
        restored = self.new_service()
        current = await restored.get_authoring(self.principal("ems-a"), system_id="EMS", process_id=process["process_id"])
        self.assertEqual(current["process"], published)

    async def test_sa03_28_mapping_revision_audit_and_revoked_receipt_are_enforced(self):
        process = await self.create()
        body = self.body("set_system_group", system_id="EMS", expected_mapping_revision=1,
                         payload={"group_id": "g-ems", "active": False})
        changed = await self.service.authoring_action(self.principal("admin"), body)
        self.assertTrue(changed["ok"], changed)
        self.assert_denied(await self.read("ems-a", process))
        row = [item for item in self.audit_rows() if item["request_id"] == body["request_id"]][-1]
        self.assertEqual((row["actor"], row["system_id"], row["before_revision"], row["after_revision"]),
                         ("admin", "EMS", 1, 2))
        self.assertNotEqual(row["before_hash"], row["after_hash"])
        self.assertRegex(row["after_hash"], r"^[a-f0-9]{64}$")
        before = self.business_rows()
        self.assert_denied(await self.action("admin", "set_system_group", system_id="EMS", expected_mapping_revision=1,
                                             payload={"group_id": "g-ems", "active": True}))
        self.assertEqual(self.business_rows(), before)
        replay = await self.service.authoring_action(self.principal("admin"), body)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(self.business_rows(), before)
        self.users["admin"]["role"] = "user"
        self.assert_denied(await self.service.authoring_action(self.principal("admin"), body))
        self.assertEqual(self.business_rows(), before)

    async def test_sa12_18_native_reference_revocation_and_content_change_require_revalidation(self):
        self.assets.update(skills=[{"id": "native-skill", "name": "개인 등록 스킬"}],
            skill_bodies={"native-skill": "NATIVE-PRIVATE-BODY-V1"}, skill_versions={"native-skill": 1})
        process = await self.create()
        document = deepcopy(process["workflow"])
        document["skills"]["new-skill"] = {"id": "new-skill", "name": "읽기 전용 연결", "type": "skill",
            "source": "open_webui", "reference": "native-skill", "body": ""}
        job = next(node for node in document["nodes"].values() if node["type"] == "j")
        job["skills"] = ["new-skill"]
        process = await self.save("ems-a", process, document)
        for change in ("version", "body", "revoke", "lookup_failure"):
            with self.subTest(change=change):
                self.assets["skills"] = [{"id": "native-skill", "name": "개인 등록 스킬"}]
                self.assets["available"] = True
                checked = await self.action("ems-a", "validate_draft", process)
                self.assertTrue(checked["ok"], checked)
                process = checked["process"]
                before = self.catalog()
                if change == "version":
                    self.assets["skill_versions"]["native-skill"] += 1
                elif change == "body":
                    self.assets["skill_bodies"]["native-skill"] = "NATIVE-PRIVATE-BODY-V2"
                elif change == "revoke":
                    self.assets["skills"] = []
                else:
                    self.assets["available"] = False
                assets_before = deepcopy(self.assets)
                self.assert_denied(await self.action("ems-a", "publish", process))
                self.assertEqual(self.catalog(), before)
                opaque = (await self.read("ems-a", process))["process"]
                self.assertEqual(opaque["workflow"], process["workflow"])
                document = deepcopy(opaque["workflow"])
                document["nodes"][opaque["process_id"]]["description"] = "권한 회복 전 초안 보존 " + change
                process = await self.save("ems-a", opaque, document)
                self.assertEqual(self.assets, assets_before, "Asset registries are read-only")
                self.assertNotIn("NATIVE-PRIVATE-BODY", json.dumps(self.business_rows()) + json.dumps(self.audit_rows()))

    async def test_sa08_new_ids_are_server_issued_and_cycles_and_native_code_are_rejected(self):
        process = await self.create()
        task = next(node for node in process["workflow"]["nodes"].values() if node["type"] == "t")
        added = await self.action("ems-a", "add_node", process, payload={"parent_id": task["id"], "name": "두 번째 작업"})
        self.assertTrue(added["ok"], added)
        process = added["process"]
        jobs = [node for node in process["workflow"]["nodes"].values() if node["type"] == "j"]
        cyclic = deepcopy(process["workflow"])
        cyclic["nodes"][jobs[0]["id"]]["deps"] = [jobs[1]["id"]]
        cyclic["nodes"][jobs[1]["id"]]["deps"] = [jobs[0]["id"]]
        code = deepcopy(process["workflow"])
        code["skills"]["new-script"] = {"id": "new-script", "name": "사용자 코드 변경", "type": "skill",
            "source": "open_webui", "reference": "private-native", "body": "DO-NOT-WRITE-NATIVE"}
        before = self.business_rows()
        for document in (cyclic, code):
            self.assert_denied(await self.action("ems-a", "save_draft", process, payload={"workflow": document}))
            self.assertEqual(self.business_rows(), before)

    async def test_sa18_asset_changes_during_final_authorization_cannot_use_an_earlier_snapshot(self):
        scenarios = (("validate_draft", "revoke"), ("validate_draft", "unavailable"),
                     ("publish", "revoke"), ("publish", "tool_version"),
                     ("publish", "skill_version"), ("publish", "skill_body"))
        for action, change in scenarios:
            with self.subTest(action=action, change=change):
                self.assets = {"tools": [{"id": "native-tool", "name": "등록 도구"}],
                    "skills": [{"id": "native-skill", "name": "등록 스킬"}],
                    "tool_versions": {"native-tool": 1}, "skill_versions": {"native-skill": 1},
                    "skill_bodies": {"native-skill": "현재 승인 본문"}, "available": True}
                process = await self.create(name="최종 참조 검사 " + action + " " + change)
                document = deepcopy(process["workflow"])
                document["tools"]["new-tool"] = {"id": "new-tool", "name": "기존 도구 연결", "source": "open_webui",
                    "reference": "native-tool", "adapter": "unavailable", "input": "db", "enabled": True}
                document["skills"]["new-skill"] = {"id": "new-skill", "name": "기존 스킬 연결", "type": "skill",
                    "source": "open_webui", "reference": "native-skill", "body": ""}
                job = next(node for node in document["nodes"].values() if node["type"] == "j")
                job.update(mode="tool", tools=["new-tool"], skills=["new-skill"], bindings={"new-tool": "db"})
                process = await self.save("ems-a", process, document)
                if action == "publish":
                    checked = await self.action("ems-a", "validate_draft", process)
                    self.assertTrue(checked["ok"], checked)
                    process = checked["process"]
                before = self.business_rows()
                authorization_reads = 0
                original_lookup = self.service.group_lookup

                async def change_after_initial_asset_read(user_id):
                    nonlocal authorization_reads
                    authorization_reads += 1
                    groups = await original_lookup(user_id)
                    if authorization_reads == 2:
                        if change == "revoke":
                            self.assets["tools"] = []
                            self.assets["skills"] = []
                        elif change == "unavailable":
                            self.assets["available"] = False
                        elif change == "tool_version":
                            self.assets["tool_versions"]["native-tool"] = 2
                        elif change == "skill_version":
                            self.assets["skill_versions"]["native-skill"] = 2
                        else:
                            self.assets["skill_bodies"]["native-skill"] = "검사 이후 수정된 본문"
                    return groups

                with patch.object(self.service, "group_lookup", change_after_initial_asset_read):
                    result = await self.action("ems-a", action, process)
                self.assertGreaterEqual(authorization_reads, 2, "The race must occur at the final authorization boundary")
                self.assert_denied(result, "reference_unavailable", "validation_required")
                self.assertEqual(self.business_rows(), before, "No validation, publication, or receipt may commit with stale assets")


class AuthoringRestoreTests(AuthoringFixture, unittest.IsolatedAsyncioTestCase):
    async def old_action(self, service, body, actor="admin"):
        result = await service.handle_action(self.principal(actor), body)
        self.assertTrue(result["ok"], result)
        return result

    async def old_publish_change(self, old, process, *, remove=False, description="이전 프로그램에서 새로 게시한 내용", mutate=None):
        """Sequentially run the real supported old writer, then re-upgrade."""
        legacy = old.WorkflowService(self.database, self.user_lookup, lambda _: None, lambda _: deepcopy(self.assets))
        state = await legacy.get_state(self.principal("admin"))
        definition = deepcopy(state["draft"])
        if mutate:
            mutate(definition)
        elif remove:
            for node_id in process["workflow"]["nodes"]:
                definition["nodes"].pop(node_id)
            for roots in definition["roots"].values():
                if process["process_id"] in roots:
                    roots.remove(process["process_id"])
        else:
            definition["nodes"][process["process_id"]]["description"] = description
        saved = await self.old_action(legacy, {"action": "save_draft", "expected_revision": state["draft_revision"],
            "payload": {"definition": definition}})
        await self.old_action(legacy, {"action": "validate_draft", "expected_revision": saved["draft_revision"]})
        await self.old_action(legacy, {"action": "publish", "expected_revision": saved["draft_revision"]})
        self.service = self.new_service()

    @staticmethod
    def observed_publication(process):
        published = process["published_workflow"]
        return "" if published is None else hashlib.sha256(json.dumps(
            published, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    async def test_sa25_explicit_admin_reconciliation_resumes_changed_or_removed_publication(self):
        old = load_legacy_workflow(self)
        for removed in (False, True):
            with self.subTest(removed=removed):
                process = await self.publish("ems-a", await self.create(name="Restore 조정 대상 " + str(removed)))
                other = await self.publish("ems-b", await self.create(name="변경하지 않을 별도 절차 " + str(removed)))
                created = await self.service.handle_action(self.principal("ordinary"), {"action": "create", "payload": {
                    "process_id": process["process_id"], "site_id": "us-a", "system": "EMS"}})
                self.assertTrue(created["ok"], created)
                draft = deepcopy(process["workflow"])
                draft["nodes"][process["process_id"]]["description"] = "신형에서 따로 보존한 미게시 초안"
                process = await self.save("ems-a", process, draft)
                with closing(sqlite3.connect(self.database)) as db, db:
                    draft_bytes = db.execute("SELECT draft FROM process_management WHERE process_id=?", (process["process_id"],)).fetchone()[0]
                    other_row = db.execute("SELECT * FROM process_management WHERE process_id=?", (other["process_id"],)).fetchone()
                    case_rows = db.execute("SELECT * FROM cases ORDER BY id").fetchall()
                await self.old_publish_change(old, process, remove=removed)
                current = (await self.read("admin", process))["process"]
                self.assertEqual(current["workflow"], draft)
                ordinary_editor = (await self.read("ems-a", process))["process"]
                self.assertFalse(ordinary_editor["publication_reconciliation"]["can_reconcile"])
                self.assert_denied(await self.read("apc", process), "process_not_found")
                self.assert_denied(await self.action("ems-a", "validate_draft", current), "workflow_baseline_changed")
                catalog_before = self.catalog()
                observed = self.observed_publication(current)
                payload = {"expected_published_fingerprint": observed}
                self.assert_denied(await self.action("ems-a", "reconcile_publication", current, payload=payload))
                request = self.body("reconcile_publication", current, payload=payload)
                result = await self.service.authoring_action(self.principal("admin"), request)
                self.assertTrue(result["ok"], result)
                reconciled = result["process"]
                metadata = current["publication_reconciliation"]
                self.assertTrue(metadata["required"])
                self.assertTrue(metadata["can_reconcile"])
                self.assertEqual(metadata["state"], "removed" if removed else "changed")
                self.assertEqual(metadata["current_published_fingerprint"], observed)
                self.assertEqual(reconciled["base_process_fingerprint"], observed)
                self.assertFalse(reconciled["publication_reconciliation"]["required"])
                self.assertIsNone(reconciled["validated_revision"])
                self.assertEqual(reconciled["draft_revision"], current["draft_revision"] + 1)
                self.assertEqual(reconciled["owner_revision"], current["owner_revision"])
                self.assertEqual(reconciled["published_version"], current["published_version"])
                self.assertEqual(self.catalog(), catalog_before, "Reconciliation does not publish")
                with closing(sqlite3.connect(self.database)) as db, db:
                    self.assertEqual(db.execute("SELECT draft FROM process_management WHERE process_id=?", (process["process_id"],)).fetchone()[0], draft_bytes)
                    self.assertEqual(db.execute("SELECT * FROM process_management WHERE process_id=?", (other["process_id"],)).fetchone(), other_row)
                    self.assertEqual(db.execute("SELECT * FROM cases ORDER BY id").fetchall(), case_rows)
                audit = next(item for item in self.audit_rows() if item["request_id"] == request["request_id"])
                self.assertEqual((audit["actor"], audit["action"], audit["process_id"]), ("admin", "reconcile_publication", process["process_id"]))
                self.assertEqual((audit["before_revision"], audit["after_revision"]), (current["draft_revision"], reconciled["draft_revision"]))
                self.assertEqual((audit["before_hash"], audit["after_hash"]), (current["base_process_fingerprint"], observed))
                before_replay = self.business_rows(), self.audit_rows()
                replay = await self.service.authoring_action(self.principal("admin"), request)
                self.assertTrue(replay["ok"] and replay["replayed"], replay)
                self.assertEqual((self.business_rows(), self.audit_rows()), before_replay)
                if removed:
                    self.assertEqual(reconciled["publication_reconciliation"]["state"], "removed")
                    self.assert_denied(await self.action("admin", "delete", reconciled), "published_process_requires_disable")
                checked = await self.action("ems-a", "validate_draft", reconciled)
                self.assertTrue(checked["ok"], checked)
                with closing(sqlite3.connect(self.database)) as db, db:
                    validated_row = db.execute("SELECT * FROM process_management WHERE process_id=?", (process["process_id"],)).fetchone()
                noop = await self.action("admin", "reconcile_publication", checked["process"], payload=payload)
                self.assertTrue(noop["ok"], noop)
                self.assertEqual(noop["process"], checked["process"], "A new request for the same baseline preserves validation")
                with closing(sqlite3.connect(self.database)) as db, db:
                    self.assertEqual(db.execute("SELECT * FROM process_management WHERE process_id=?", (process["process_id"],)).fetchone(), validated_row)
                published_result = await self.action("ems-a", "publish", noop["process"])
                self.assertTrue(published_result["ok"], published_result)
                resumed = published_result["process"]
                published = json.loads(self.catalog()[0])
                prior = json.loads(catalog_before[0])
                self.assertEqual(resumed["workflow"], draft)
                self.assertEqual(published["nodes"][process["process_id"]]["description"], "신형에서 따로 보존한 미게시 초안")
                for key in ("tools", "skills", "sites", "systems"):
                    self.assertEqual(published[key], prior[key], key)
                self.assertEqual({key: value for key, value in published["nodes"].items() if key not in draft["nodes"]},
                                 {key: value for key, value in prior["nodes"].items() if key not in draft["nodes"]})
                with closing(sqlite3.connect(self.database)) as db, db:
                    self.assertEqual(db.execute("SELECT * FROM cases ORDER BY id").fetchall(), case_rows)

    async def test_sa25_reconciliation_rejects_stale_publication_and_rolls_back_failed_audit(self):
        old = load_legacy_workflow(self)
        deleted = await self.create(name="삭제한 미게시 절차")
        self.assertTrue((await self.action("ems-a", "delete", deleted))["ok"])
        self.assert_denied(await self.action("admin", "reconcile_publication", deleted,
            payload={"expected_published_fingerprint": ""}), "process_not_found")
        process = await self.publish("ems-a", await self.create(name="게시본 CAS 조정 검사"))
        await self.old_publish_change(old, process, description="관리자가 확인한 이전 게시 변경")
        observed = (await self.read("admin", process))["process"]
        stale_body = self.body("reconcile_publication", observed,
            payload={"expected_published_fingerprint": self.observed_publication(observed)})
        await self.old_publish_change(old, process, description="확인 이후에 또 변경된 게시본")
        before = self.business_rows()
        self.assert_denied(await self.service.authoring_action(self.principal("admin"), stale_body), "workflow_baseline_changed")
        self.assertEqual(self.business_rows(), before)
        current = (await self.read("admin", process))["process"]
        request = self.body("reconcile_publication", current,
            payload={"expected_published_fingerprint": self.observed_publication(current)})
        for field in ("expected_draft_revision", "expected_owner_revision"):
            stale_revision = self.body("reconcile_publication", current,
                payload=request["payload"], **{field: current[field.removeprefix("expected_")] + 1})
            self.assert_denied(await self.service.authoring_action(self.principal("admin"), stale_revision),
                               "draft_revision_conflict", "workflow_baseline_changed")
            self.assertEqual(self.business_rows(), before)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TRIGGER deny_reconciliation_audit BEFORE INSERT ON authoring_audit BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
        audit_before = self.audit_rows()
        self.assert_denied(await self.service.authoring_action(self.principal("admin"), request), "authoring_unavailable")
        self.assertEqual(self.business_rows(), before)
        self.assertEqual(self.audit_rows(), audit_before)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("DROP TRIGGER deny_reconciliation_audit")
        reconciled = await self.service.authoring_action(self.principal("admin"), request)
        self.assertTrue(reconciled["ok"], reconciled)
        protected = self.business_rows()
        self.users["admin"]["role"] = "user"
        self.assert_denied(await self.service.authoring_action(self.principal("admin"), request))
        self.assertEqual(self.business_rows(), protected, "Receipt replay must reauthorize the reconciler")

    async def test_sa25_reconciliation_cannot_overwrite_node_moved_to_another_process_by_restore(self):
        old = load_legacy_workflow(self)
        first = await self.create(name="원래 작업 소유 절차")
        first_task = next(node["id"] for node in first["workflow"]["nodes"].values() if node["type"] == "t")
        added = await self.action("ems-a", "add_node", first, payload={"parent_id": first_task, "name": "유지할 두 번째 작업"})
        self.assertTrue(added["ok"], added)
        first = await self.publish("ems-a", added["process"])
        second = await self.publish("ems-a", await self.create(name="구형 프로그램에서 작업을 받은 절차"))
        second_task = next(node["id"] for node in second["workflow"]["nodes"].values() if node["type"] == "t")
        moved = first["workflow"]["nodes"][first_task]["children"][0]
        def move_job(definition):
            definition["nodes"][first_task]["children"].remove(moved)
            definition["nodes"][second_task]["children"].append(moved)
            definition["nodes"][moved]["parent"] = second_task
        await self.old_publish_change(old, first, mutate=move_job)
        current = (await self.read("admin", first))["process"]
        reconciled = await self.action("admin", "reconcile_publication", current,
            payload={"expected_published_fingerprint": self.observed_publication(current)})
        self.assertTrue(reconciled["ok"], reconciled)
        protected = self.business_rows()
        self.assert_denied(await self.action("ems-a", "validate_draft", reconciled["process"]), "invalid_workflow_scope")
        self.assert_denied(await self.action("ems-a", "publish", reconciled["process"]))
        self.assertEqual(self.business_rows(), protected)
        self.assertEqual(json.loads(self.catalog()[0])["nodes"][moved]["parent"], second_task)

    async def test_sa23_exact_legacy_archive_and_explicit_partial_import(self):
        old = load_legacy_workflow(self)
        # A separate legacy database starts before the additive authoring protocol.
        self.database = self.database.with_name("pre-upgrade.sqlite3")
        legacy = old.WorkflowService(self.database, self.user_lookup, lambda _: None)
        state = await legacy.get_state(self.principal("admin"))
        draft = state["draft"]
        draft["nodes"]["setup-p"]["description"] = "가져올 P의 미게시 변경"
        draft["nodes"]["ops-p"]["description"] = "다른 P의 보관할 미게시 변경"
        draft["skills"]["connection"]["body"] = "공유 스킬 보관 변경"
        legacy_body = {"action": "save_draft", "expected_revision": 0, "request_id": "legacy-save-receipt",
                       "payload": {"definition": draft}}
        saved = await self.old_action(legacy, legacy_body)
        await self.old_action(legacy, {"action": "validate_draft", "expected_revision": saved["draft_revision"]})
        before = self.catalog()
        self.service = self.new_service()
        with closing(sqlite3.connect(self.database)) as db, db:
            archive = db.execute("SELECT id,published,draft,revision,validated FROM authoring_legacy").fetchone()
        self.assertEqual(archive[1:], before, "Exact original strings and revisions must survive migration")
        self.assertEqual(self.catalog()[0], before[0])
        self.assertEqual(self.catalog()[1], before[0], "Legacy draft becomes only a published mirror")
        protected = self.business_rows()
        self.assert_denied(await self.service.handle_action(self.principal("admin"), legacy_body), "authoring_upgrade_required")
        self.assertEqual(self.business_rows(), protected, "Old receipts cannot reopen whole-catalog authoring")
        read = await self.service.get_authoring(self.principal("admin"), system_id="UNASSIGNED", process_id="setup-p")
        process = read["process"]
        imported = await self.action("admin", "import_legacy", process,
            payload={"snapshot_id": archive[0], "source_process_id": "setup-p"})
        self.assertTrue(imported["ok"], imported)
        self.assertEqual(imported["process"]["workflow"]["nodes"]["setup-p"]["description"], "가져올 P의 미게시 변경")
        self.assertNotIn("ops-p", imported["process"]["workflow"]["nodes"])
        self.assertEqual(imported["process"]["workflow"]["skills"], {})
        self.assertEqual(self.catalog()[0], before[0], "Import must not publish any changes")
        self.assert_denied(await self.service.get_authoring(self.principal("ems-a"), legacy_id=archive[0]))
        restarted = self.new_service()
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute("SELECT published,draft,revision,validated FROM authoring_legacy WHERE id=?",
                                       (archive[0],)).fetchone(), before)
        reread = await restarted.get_authoring(self.principal("admin"), "UNASSIGNED", "setup-p")
        self.assertEqual(reread["process"], imported["process"])

    async def test_sa25_real_previous_program_restore_and_reupgrade_preserve_new_and_old_state(self):
        old = load_legacy_workflow(self)
        before_case = await self.service.handle_action(self.principal("ordinary"), {"action": "create"})
        self.assertTrue(before_case["ok"], before_case)
        process = await self.publish("ems-a", await self.create())
        published_case = await self.service.handle_action(self.principal("ordinary"), {"action": "create", "payload": {
            "site_id": "us-a", "system": "EMS", "process_id": process["process_id"]}})
        self.assertTrue(published_case["ok"], published_case)
        document = deepcopy(process["workflow"])
        document["nodes"][process["process_id"]]["description"] = "신형에서 저장한 미게시 초안"
        process = await self.save("ems-a", process, document)
        with closing(sqlite3.connect(self.database)) as db, db:
            metadata_before = {table: db.execute("SELECT * FROM " + table).fetchall() for table in
                ("system_groups", "process_management", "authoring_ids", "authoring_requests", "authoring_audit")}
        # Sequential fallback, with the exact supported wheel's service operating
        # on the same SQLite file. This does not claim simultaneous-version support.
        legacy = old.WorkflowService(self.database, self.user_lookup, lambda _: None, lambda _: deepcopy(self.assets))
        for original in (before_case["case"], published_case["case"]):
            read = await legacy.get_state(self.principal("ordinary"), case_id=original["id"])
            self.assertEqual(read["case"], original)
        fallback_case = await self.old_action(legacy, {"action": "create"}, "ordinary")
        state = await legacy.get_state(self.principal("admin"))
        fallback = state["draft"]
        fallback["nodes"]["setup-p"]["description"] = "Restore 중 구형 프로그램이 저장한 전체 초안"
        saved = await self.old_action(legacy, {"action": "save_draft", "expected_revision": state["draft_revision"],
                                               "payload": {"definition": fallback}})
        await self.old_action(legacy, {"action": "validate_draft", "expected_revision": saved["draft_revision"]})
        fallback_bytes = self.catalog()
        self.service = self.new_service()
        with closing(sqlite3.connect(self.database)) as db, db:
            for table, expected in metadata_before.items():
                self.assertEqual(db.execute("SELECT * FROM " + table).fetchall(), expected, table)
            rows = db.execute("SELECT published,draft,revision,validated FROM authoring_legacy").fetchall()
            self.assertIn(fallback_bytes, rows)
        self.assertEqual(self.catalog()[0], fallback_bytes[0])
        self.assertEqual((await self.read("ems-a", process))["process"], process)
        for original in (before_case["case"], published_case["case"], fallback_case["case"]):
            self.assertEqual((await self.service.get_state(self.principal("ordinary"), case_id=original["id"]))["case"], original)

    async def test_sa25_old_publication_shared_reference_cannot_be_changed_through_one_process(self):
        old = load_legacy_workflow(self)
        self.assets.update(skills=[{"id": "native-existing", "name": "등록된 스킬"}],
                           skill_bodies={"native-existing": "기존 스킬 내용"}, skill_versions={"native-existing": 7})
        first = await self.create(name="참조 소유 절차")
        document = deepcopy(first["workflow"])
        document["skills"]["new-local"] = {"id": "new-local", "name": "기존 스킬 연결", "type": "skill",
            "source": "open_webui", "reference": "native-existing", "body": ""}
        next(node for node in document["nodes"].values() if node["type"] == "j")["skills"] = ["new-local"]
        first = await self.publish("ems-a", await self.save("ems-a", first, document))
        second = await self.publish("ems-a", await self.create(name="Restore에서 참조한 다른 절차"))
        local_id = next(iter(first["workflow"]["skills"]))
        old_service = old.WorkflowService(self.database, self.user_lookup, lambda _: None, lambda _: deepcopy(self.assets))
        state = await old_service.get_state(self.principal("admin"))
        fallback = deepcopy(state["draft"])
        second_job = next(key for key, node in second["workflow"]["nodes"].items() if node["type"] == "j")
        fallback["nodes"][second_job]["skills"] = [local_id]
        saved = await self.old_action(old_service, {"action": "save_draft", "expected_revision": state["draft_revision"],
            "payload": {"definition": fallback}})
        await self.old_action(old_service, {"action": "validate_draft", "expected_revision": saved["draft_revision"]})
        await self.old_action(old_service, {"action": "publish", "expected_revision": saved["draft_revision"]})
        old_published = self.catalog()
        self.service = self.new_service()
        self.assertEqual(self.catalog()[0], old_published[0])
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertIn(old_published, db.execute("SELECT published,draft,revision,validated FROM authoring_legacy").fetchall())
        first = (await self.read("ems-a", first))["process"]
        for operation in ("change", "remove"):
            with self.subTest(operation=operation):
                document = deepcopy(first["workflow"])
                if operation == "change":
                    document["skills"][local_id]["name"] = "타 절차까지 변경하려는 연결"
                else:
                    del document["skills"][local_id]
                    for node in document["nodes"].values():
                        node["skills"] = []
                # Safe draft storage remains possible; publication cannot mutate
                # the other published P that the real fallback writer linked.
                first = await self.save("ems-a", first, document)
                protected = self.business_rows()
                checked = await self.action("ems-a", "validate_draft", first)
                self.assert_denied(checked, "invalid_workflow_scope")
                self.assert_denied(await self.action("ems-a", "publish", first))
                self.assertEqual(self.business_rows(), protected)
                self.assertEqual(self.catalog()[0], old_published[0])


class AuthoringRouteTests(AuthoringFixture, unittest.IsolatedAsyncioTestCase):
    async def test_sa05_http_routes_use_verified_dependency_and_server_scope(self):
        from fastapi import FastAPI, HTTPException, Request
        import httpx
        async def verified(request: Request):
            user = self.users.get(request.headers.get("x-test-user", ""))
            if not user:
                raise HTTPException(401, "Synthetic unauthenticated request")
            return deepcopy(user)
        app = FastAPI()
        workflow.install(app, verified)
        for route in app.routes:
            if route.path.startswith("/api/ees-work/authoring"):
                self.assertIs(route.dependant.dependencies[0].call, verified)
        with patch.object(workflow, "_service", self.service):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
                for path in ("/capabilities", ""):
                    self.assertEqual((await client.get("/api/ees-work/authoring" + path)).status_code, 401)
                self.assertEqual((await client.post("/api/ees-work/authoring/action", json={})).status_code, 401)
                headers = {"x-test-user": "ems-a"}
                process = await self.create()
                for actor, status in (("ordinary", 403), ("ems-a", 200)):
                    response = await client.get("/api/ees-work/authoring?system_id=EMS", headers={"x-test-user": actor})
                    self.assertEqual(response.status_code, status, response.text)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                forbidden = await client.get("/api/ees-work/authoring", params={"system_id": "EMS", "process_id": process["process_id"]},
                                             headers={"x-test-user": "apc"})
                self.assertEqual(forbidden.status_code, 404, forbidden.text)
                forged = self.body("publish", process, user_id="admin", role="admin")
                retired = await client.post("/api/ees-work/authoring/action", headers=headers, json=forged)
                self.assertEqual(retired.status_code, 409)
                self.assertEqual(retired.json()["error"]["code"], "legacy_execution_retired")
                stale = self.body("save_draft", process, expected_draft_revision=999, payload={"workflow": process["workflow"]})
                self.assertEqual((await client.post("/api/ees-work/authoring/action", headers=headers, json=stale)).status_code, 409)
                self.fail_groups = True
                failed = await client.get("/api/ees-work/authoring/capabilities", headers=headers)
                self.assertEqual(failed.status_code, 503, failed.text)
                self.assertNotIn("PRIVATE-GROUP-STORE-ERROR", failed.text)


if __name__ == "__main__":
    unittest.main()
