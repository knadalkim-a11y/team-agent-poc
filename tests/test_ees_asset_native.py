"""Required release integration gate for conditional writes on the real wheel.

Run with EES_TEST_UPSTREAM_WHEEL=<pinned wheel> and EES_REQUIRE_ASSET_NATIVE=1.
The ordinary dependency-light suite reports this optional environment as
unavailable; setting the release-gate variable makes missing input a failure.
These tests execute the production builder output and native SQLAlchemy asset
tables/routers, rather than replacing persistence with a mock dictionary.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch
from zipfile import ZipFile


WHEEL = os.environ.get("EES_TEST_UPSTREAM_WHEEL")
REQUIRED = os.environ.get("EES_REQUIRE_ASSET_NATIVE") == "1"


class NativeAssetCases:
    sharing = True

    async def asyncSetUp(self):
        if not WHEEL or not Path(WHEEL).is_file():
            self.fail("The required native asset gate needs EES_TEST_UPSTREAM_WHEEL")
        from ees_asset_native_fixture import NativeAssetFixture
        self.fixture = NativeAssetFixture(WHEEL, sharing=self.sharing)
        self.addAsyncCleanup(self.fixture.close)
        await self.fixture.start()
        self.assertEqual((await self.fixture.create_tool()).status_code, 200)
        self.assertEqual((await self.fixture.create_model()).status_code, 200)

    async def snapshot(self, kind="tool", identifier=None, user="admin"):
        identifier = identifier or ("fixture_model" if kind == "model" else "fixture_tool")
        response = await self.fixture.request(
            "POST", "/api/v1/ees/assets/snapshot", user=user,
            payload={"kind": kind, "id": identifier},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def apply(self, snapshot, payload, *, kind="tool", identifier=None, operation="update"):
        return await self.fixture.request("POST", "/api/v1/ees/assets/apply", payload={
            "kind": kind, "id": identifier or ("fixture_model" if kind == "model" else "fixture_tool"),
            "operation": operation, "expected_token": snapshot["token"], "payload": payload,
        })

    @staticmethod
    def tool_payload(snapshot, description):
        data = deepcopy(snapshot["asset"])
        data["meta"]["description"] = description
        return {name: data[name] for name in ("id", "name", "content", "meta", "access_grants")}

    @staticmethod
    def model_payload(snapshot, prompt):
        data = deepcopy(snapshot["asset"])
        data["params"]["system"] = prompt
        return {name: data[name] for name in (
            "id", "name", "base_model_id", "meta", "params", "access_grants", "is_active",
        )}

    async def test_missing_native_chat_installation_marker_is_rejected(self):
        middleware = sys.modules["open_webui.utils.middleware"]
        self.fixture.guard.verify_asset_guard_installation()
        with patch.object(middleware, "EES_WORK_NATIVE_CHAT_CONTEXT", 0):
            with self.assertRaisesRegex(self.fixture.guard.AssetGuardError, "incomplete_installation"):
                self.fixture.guard.verify_asset_guard_installation()
        self.fixture.guard.verify_asset_guard_installation()

    async def test_native_ui_description_race_rejects_old_payload(self):
        before = await self.snapshot()
        old_payload = self.tool_payload(before, "deployment")
        response = await self.fixture.request(
            "POST", "/api/v1/tools/id/fixture_tool/update",
            payload=self.tool_payload(before, "new UI description"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        conflict = await self.apply(before, old_payload)
        self.assertEqual((conflict.status_code, conflict.json()), (409, {"detail": "concurrent_edit"}))
        current = await self.snapshot()
        self.assertEqual(current["asset"]["meta"]["description"], "new UI description")
        self.assertNotEqual(current["token"], before["token"])

    async def test_native_tool_and_valves_share_conflict_scope(self):
        tool = await self.snapshot()
        valves = await self.snapshot("valves")
        response = await self.fixture.request(
            "POST", "/api/v1/tools/id/fixture_tool/valves/update", payload={"label": "UI valve"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.apply(tool, self.tool_payload(tool, "deployment"))).status_code, 409)
        self.assertEqual((await self.snapshot("valves"))["asset"], {"label": "UI valve"})

        valves = await self.snapshot("valves")
        tool = await self.snapshot()
        changed = self.tool_payload(tool, "UI source")
        changed["content"] += "\n# UI source edit\n"
        self.assertEqual((await self.fixture.request(
            "POST", "/api/v1/tools/id/fixture_tool/update", payload=changed,
        )).status_code, 200)
        self.assertEqual((await self.apply(valves, {"label": "deployment"}, kind="valves")).status_code, 409)

    async def test_native_model_params_and_acl_changes_invalidate_token(self):
        before = await self.snapshot("model")
        response = await self.fixture.request(
            "POST", "/api/v1/models/model/update", payload=self.model_payload(before, "new UI prompt"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.apply(
            before, self.model_payload(before, "deployment"), kind="model",
        )).status_code, 409)
        current = await self.snapshot("model")
        self.assertEqual(current["asset"]["params"]["system"], "new UI prompt")
        # Exercise a direct native ACL writer, bypassing the HTTP route.
        await self.fixture.acl.AccessGrants.grant_access("model", "fixture_model", "user", "reader", "read")
        self.assertEqual((await self.apply(
            current, self.model_payload(current, "deployment"), kind="model",
        )).status_code, 409)
        self.assertTrue(await self.fixture.acl.AccessGrants.has_access("reader", "model", "fixture_model", "read"))

    async def test_create_collision_and_target_mismatch_do_not_write(self):
        before = await self.snapshot(identifier="fixture_new")
        self.assertFalse(before["exists"])
        self.assertEqual((await self.fixture.create_tool("fixture_new")).status_code, 200)
        template = self.tool_payload(await self.snapshot(), "deployment")
        template["id"] = "fixture_new"
        self.assertEqual((await self.apply(
            before, template, identifier="fixture_new", operation="create",
        )).status_code, 409)
        current = await self.snapshot()
        template["id"] = "fixture_other"
        self.assertEqual((await self.apply(current, template)).status_code, 422)
        self.assertFalse((await self.snapshot(identifier="fixture_other"))["exists"])

    async def test_native_permissions_and_admin_read_redaction_are_preserved(self):
        self.assertEqual((await self.fixture.create_tool("fixture_private", owner="owner")).status_code, 200)
        for user in ("reader", "outsider"):
            response = await self.fixture.request(
                "POST", "/api/v1/ees/assets/snapshot", user=user,
                payload={"kind": "tool", "id": "fixture_private"},
            )
            self.assertEqual(response.status_code, 403)
        # Native WebUI may expose admin read metadata while withholding source.
        # The conditional API must not turn that into permission to overwrite.
        response = await self.fixture.request(
            "POST", "/api/v1/ees/assets/snapshot",
            payload={"kind": "tool", "id": "fixture_private"},
        )
        self.assertEqual(response.status_code, 403, response.text)
        native = await self.fixture.request("GET", "/api/v1/tools/id/fixture_private")
        self.assertEqual(native.status_code, 200)
        self.assertFalse(native.json()["write_access"])
        self.assertNotIn("content", native.json())
        await self.fixture.acl.AccessGrants.grant_access("tool", "fixture_private", "user", "reader", "read")
        native = await self.fixture.request("GET", "/api/v1/tools/id/fixture_private", user="reader")
        self.assertEqual(native.status_code, 200)
        self.assertNotIn("content", native.json())

    async def test_success_receipt_is_fresh_and_preserves_unmanaged_asset(self):
        self.assertEqual((await self.fixture.create_tool("fixture_unmanaged", owner="owner")).status_code, 200)
        unmanaged = await self.fixture.tools.Tools.get_tool_by_id("fixture_unmanaged")
        before = await self.snapshot()
        applied = await self.apply(before, self.tool_payload(before, "deployment"))
        self.assertEqual(applied.status_code, 200, applied.text)
        receipt = applied.json()
        self.assertEqual(receipt["asset"]["meta"]["description"], "deployment")
        self.assertEqual(receipt["token"], (await self.snapshot())["token"])
        self.assertIn("valves_snapshot", receipt)
        valves = await self.apply(receipt["valves_snapshot"], {"label": "deployed"}, kind="valves")
        self.assertEqual(valves.status_code, 200, valves.text)
        self.assertEqual(valves.json()["asset"], {"label": "deployed"})
        after = await self.fixture.tools.Tools.get_tool_by_id("fixture_unmanaged")
        self.assertEqual(unmanaged.model_dump(), after.model_dump())
        module, _ = await self.fixture.plugin.get_tool_module_from_cache(
            self.request_object(), "fixture_unmanaged",
        )
        self.assertEqual(module.echo("retained"), "retained")

    def request_object(self):
        from starlette.requests import Request
        return Request({"type": "http", "app": self.fixture.app, "headers": []})

    async def test_pending_commit_cancellation_keeps_native_writer_serialized(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        before = await self.snapshot()
        commit_entered, release_commit = asyncio.Event(), asyncio.Event()
        original_commit = AsyncSession.commit
        blocked_once = False

        async def blocked_commit(session):
            nonlocal blocked_once
            if not blocked_once:
                blocked_once = True
                commit_entered.set()
                await release_commit.wait()
            return await original_commit(session)

        with patch.object(AsyncSession, "commit", blocked_commit):
            first = asyncio.create_task(self.apply(before, self.tool_payload(before, "deployment")))
            second = None
            try:
                await asyncio.wait_for(commit_entered.wait(), 3)
                first.cancel()
                second = asyncio.create_task(self.fixture.request(
                    "POST", "/api/v1/tools/id/fixture_tool/update",
                    payload=self.tool_payload(before, "following UI edit"),
                ))
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(second), 0.05)
                self.assertFalse(first.done(), "Cancellation released the operation before its DB commit finished")
            finally:
                release_commit.set()
                outcomes = await asyncio.wait_for(asyncio.gather(
                    *[task for task in (first, second) if task is not None], return_exceptions=True,
                ), 5)
            self.assertIsInstance(outcomes[0], asyncio.CancelledError)
            self.assertEqual(outcomes[1].status_code, 200, outcomes[1].text)
        self.assertEqual((await self.snapshot())["asset"]["meta"]["description"], "following UI edit")

    async def test_native_chat_binding_cannot_republish_an_older_tool_module(self):
        before = await self.snapshot()
        entered, release = asyncio.Event(), asyncio.Event()
        original_read = self.fixture.tools.Tools.get_tool_by_id
        once = False

        async def pause_after_read(identifier, *args, **kwargs):
            nonlocal once
            value = await original_read(identifier, *args, **kwargs)
            if identifier == "fixture_tool" and not once:
                once = True
                entered.set()
                await release.wait()
            return value

        changed = self.tool_payload(before, "new executable source")
        changed["content"] = changed["content"].replace("return value", "return 'updated:' + value")
        with patch.object(self.fixture.tools.Tools, "get_tool_by_id", pause_after_read):
            binding = asyncio.create_task(self.fixture.binding.get_tools(
                self.request_object(), ["fixture_tool"], self.fixture.users["admin"], {"__user__": {"id": "admin"}},
            ))
            writer = None
            try:
                await asyncio.wait_for(entered.wait(), 3)
                writer = asyncio.create_task(self.fixture.request(
                    "POST", "/api/v1/tools/id/fixture_tool/update", payload=changed,
                ))
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(writer), 0.05)
            finally:
                release.set()
                values = await asyncio.wait_for(asyncio.gather(*[task for task in (binding, writer) if task]), 5)
        self.assertIn("echo", values[0])
        self.assertEqual(values[1].status_code, 200, values[1].text)
        self.assertEqual(self.fixture.app.state.TOOLS["fixture_tool"].echo("check"), "updated:check")
        newly_bound = await self.fixture.binding.get_tools(
            self.request_object(), ["fixture_tool"], self.fixture.users["admin"], {"__user__": {"id": "admin"}},
        )
        self.assertEqual(await newly_bound["echo"]["callable"](value="check"), "updated:check")

    async def test_partial_native_acl_failure_does_not_publish_cache_or_fake_rollback(self):
        before = await self.snapshot()
        await self.fixture.plugin.get_tool_module_from_cache(self.request_object(), "fixture_tool")
        self.assertIn("fixture_tool", self.fixture.app.state.TOOLS)

        async def fail_acl(*args, **kwargs):
            raise RuntimeError("synthetic ACL commit failure")

        with patch.object(self.fixture.acl.AccessGrants, "set_access_grants", fail_acl):
            response = await self.apply(before, self.tool_payload(before, "committed before ACL failed"))
        self.assertGreaterEqual(response.status_code, 400, response.text)
        current = await self.snapshot()
        self.assertEqual(current["asset"]["meta"]["description"], "committed before ACL failed")
        self.assertEqual(current["asset"]["access_grants"], before["asset"]["access_grants"])
        self.assertNotIn("fixture_tool", self.fixture.app.state.TOOLS)
        self.assertEqual((await self.apply(before, self.tool_payload(before, "stale retry"))).status_code, 409)

    async def test_normalization_read_holds_guard_before_read_and_commit(self):
        from sqlalchemy import select, update
        from sqlalchemy.ext.asyncio import AsyncSession
        # Construct an old-version model row containing duplicated text; the
        # native GET is allowed to normalize it and commits that normalization.
        legacy_meta = {"description": "legacy", "knowledge": [{"id": "k", "data": {"content": "duplicated"}}]}
        async with self.fixture.sessions() as session:
            await session.execute(update(self.fixture.models.Model).where(
                self.fixture.models.Model.id == "fixture_model",
            ).values(meta=legacy_meta))
            await session.commit()
        entered, release = asyncio.Event(), asyncio.Event()
        original_commit = AsyncSession.commit
        once = False

        async def pause_normalization(session):
            nonlocal once
            if not once:
                once = True
                self.assertTrue(self.fixture.app.state.ees_asset_guard.owned())
                entered.set()
                await release.wait()
            return await original_commit(session)

        with patch.object(AsyncSession, "commit", pause_normalization):
            reader = asyncio.create_task(self.fixture.models.Models.get_model_by_id("fixture_model"))
            writer = None
            try:
                await asyncio.wait_for(entered.wait(), 3)
                writer = asyncio.create_task(self.fixture.acl.AccessGrants.grant_access(
                    "model", "fixture_model", "user", "reader", "read",
                ))
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(writer), 0.05)
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(*[task for task in (reader, writer) if task]), 5)
        async with self.fixture.sessions() as session:
            value = (await session.execute(select(self.fixture.models.Model.meta).where(
                self.fixture.models.Model.id == "fixture_model",
            ))).scalar_one()
        self.assertEqual(value["knowledge"], [{"id": "k", "data": {}}])
        self.assertTrue(await self.fixture.acl.AccessGrants.has_access("reader", "model", "fixture_model", "read"))

    async def test_direct_stale_session_cannot_silently_replace_transaction(self):
        from sqlalchemy import select
        before = await self.snapshot()
        async with self.fixture.sessions() as stale_session:
            await stale_session.execute(select(self.fixture.tools.Tool).where(
                self.fixture.tools.Tool.id == "fixture_tool",
            ))
            with self.assertRaisesRegex(self.fixture.guard.AssetGuardError, "stale_session"):
                await self.fixture.tools.Tools.update_tool_by_id(
                    "fixture_tool", {"name": "stale overwrite"}, db=stale_session,
                )
        self.assertEqual((await self.snapshot())["token"], before["token"])

    async def test_audited_caller_keeps_normalization_in_its_own_fresh_session(self):
        from sqlalchemy import select
        users_module = sys.modules["open_webui.routers.users"]
        native_users = sys.modules["open_webui.models.users"].Users
        original_user_read = native_users.get_user_by_id
        observed = []

        async def read_user_with_transaction(user_id, db=None):
            self.assertTrue(self.fixture.app.state.ees_asset_guard.owned())
            await db.execute(select(self.fixture.models.Model.id))
            observed.append(db)
            return await original_user_read(user_id, db=db)

        async def no_knowledge(db=None):
            return []

        users_module.Knowledges = types.SimpleNamespace(get_knowledge_bases=no_knowledge)
        with patch.object(native_users, "get_user_by_id", read_user_with_transaction):
            async with self.fixture.sessions() as not_started:
                response = await users_module.get_user_preview(
                    "admin", user=self.fixture.users["admin"], db=not_started,
                )
                self.assertFalse(not_started.in_transaction())
        self.assertEqual(response["models"]["items"], [{"id": "fixture_model", "name": "Synthetic model"}])
        self.assertEqual(response["tools"]["items"], [{"id": "fixture_tool", "name": "Synthetic tool"}])
        self.assertEqual(len(observed), 1)
        await sys.modules["open_webui.utils.models"].check_model_access(
            self.fixture.users["admin"], {"id": "fixture_model"},
        )

    async def retirement_preview(self, kind, identifier, baseline="0" * 64):
        response = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/preview",
            payload={"kind": kind, "id": identifier, "baseline_sha256": baseline})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_common_work_tool_explicit_registration_exact_source_and_grants(self):
        status = await self.fixture.request("GET", "/api/v1/ees/assets/work-tool/status")
        self.assertEqual(status.status_code, 200, status.text)
        status = status.json()
        self.assertEqual(status["state"], "missing")
        self.assertIsNone(await self.fixture.tools.Tools.get_tool_by_id("ees_workflow"))
        payload = {"source_sha256": status["source_sha256"], "expected_token": status["expected_token"],
                   "confirmation": "register_readonly_work_tool", "access_grants": [
                       {"principal_type": "user", "principal_id": "reader", "permission": "read"}]}
        rejected = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload={**payload, "source_sha256": "0" * 64})
        self.assertEqual(rejected.status_code, 409)
        rejected = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload={**payload, "access_grants": [
            {"principal_type": "user", "principal_id": "reader", "permission": "write"}]})
        self.assertEqual(rejected.status_code, 422)
        forbidden = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", user="reader", payload=payload)
        self.assertEqual(forbidden.status_code, 403)
        self.assertIsNone(await self.fixture.tools.Tools.get_tool_by_id("ees_workflow"))
        created = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload=payload)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["changed"])
        tool = await self.fixture.tools.Tools.get_tool_by_id("ees_workflow")
        self.assertEqual(tool.content.encode(), self.fixture.members["open_webui/ees_workflow_tool.py"])
        self.assertEqual({entry["name"] for entry in tool.specs},
                         {"ees_workflow_view", "ees_workflow_propose", "ees_workflow_display"})
        seen = await self.fixture.request("GET", "/api/v1/tools/id/ees_workflow", user="reader")
        self.assertEqual(seen.status_code, 200, seen.text)
        denied = await self.fixture.request("GET", "/api/v1/tools/id/ees_workflow", user="owner")
        self.assertEqual(denied.status_code, 401, denied.text)
        before = tool.model_dump()
        current = (await self.fixture.request("GET", "/api/v1/ees/assets/work-tool/status")).json()
        replay = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload={
            **payload, "expected_token": current["expected_token"], "access_grants": []})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertFalse(replay.json()["changed"])
        self.assertEqual((await self.fixture.tools.Tools.get_tool_by_id("ees_workflow")).model_dump(), before)
        self.assertIsNotNone(await self.fixture.tools.Tools.get_tool_by_id("fixture_tool"))

    async def test_common_work_tool_program_change_after_confirmation_does_not_register(self):
        status = (await self.fixture.request("GET", "/api/v1/ees/assets/work-tool/status")).json()
        original = self.fixture.guard.work_tool_source()
        changed = original[0] + "\n# synthetic concurrent program source change\n"
        with patch.object(self.fixture.guard, "work_tool_source", side_effect=[
                original, (changed, hashlib.sha256(changed.encode()).hexdigest())]):
            result = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload={
                "source_sha256": status["source_sha256"], "expected_token": status["expected_token"],
                "confirmation": "register_readonly_work_tool", "access_grants": []})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json()["detail"], "work_tool_program_changed")
        self.assertIsNone(await self.fixture.tools.Tools.get_tool_by_id("ees_workflow"))

    async def test_common_work_tool_existing_user_source_is_not_overwritten(self):
        await self.fixture.create_tool("ees_workflow", owner="admin")
        before = (await self.fixture.tools.Tools.get_tool_by_id("ees_workflow")).model_dump()
        status = (await self.fixture.request("GET", "/api/v1/ees/assets/work-tool/status")).json()
        self.assertEqual(status["state"], "blocked_existing")
        result = await self.fixture.request("POST", "/api/v1/ees/assets/work-tool/setup", payload={
            "source_sha256": status["source_sha256"], "expected_token": status["expected_token"],
            "confirmation": "register_readonly_work_tool", "access_grants": []})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json()["detail"], "work_tool_existing_source_requires_review")
        self.assertEqual((await self.fixture.tools.Tools.get_tool_by_id("ees_workflow")).model_dump(), before)

    async def test_retirement_preview_delete_retry_restore_preserves_unrelated_native_assets(self):
        # Create synthetic historical registration through the ordinary Native API,
        # not the retired installer. No real user data is involved.
        created = await self.fixture.request("POST", "/api/v1/models/create", payload={
            "id": "ees_demo_ems", "name": "Synthetic former preset", "base_model_id": "upstream",
            "params": {"system": "historical synthetic policy", "temperature": 0.2},
            "meta": {"ees_demo_pack": "ees-demo-v1"}, "access_grants": []})
        self.assertEqual(created.status_code, 200, created.text)
        existing = (await self.fixture.models.Models.get_model_by_id("fixture_model")).model_dump()
        before = await self.snapshot("model", "ees_demo_ems")
        first = await self.retirement_preview("model", "ees_demo_ems")
        self.assertFalse(first["eligible"])
        self.assertIn("modified_or_unverified_asset", first["blocked_reasons"])
        accepted = await self.retirement_preview("model", "ees_demo_ems", first["current_sha256"])
        self.assertTrue(accepted["eligible"])
        self.assertIsNotNone(await self.fixture.models.Models.get_model_by_id("ees_demo_ems"))
        command = {"kind": "model", "id": "ees_demo_ems", "baseline_sha256": first["current_sha256"],
                   "expected_token": accepted["expected_token"], "request_id": "synthetic-retire-001"}
        for _ in range(2):
            result = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/apply", payload=command)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["status"], "retired")
        self.assertIsNone(await self.fixture.models.Models.get_model_by_id("ees_demo_ems"))
        receipt = result.json()
        backup = self.fixture.directory / "ees-asset-retirement/synthetic-retire-001.json"
        self.assertTrue(backup.is_file())
        self.assertNotIn("historical synthetic policy", result.text)
        changed = dict(command, baseline_sha256="a" * 64)
        conflict = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/apply", payload=changed)
        self.assertEqual(conflict.status_code, 409)
        restored = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/restore", payload={
            "request_id": command["request_id"], "backup_sha256": receipt["backup_sha256"]})
        self.assertEqual(restored.status_code, 200, restored.text)
        after = await self.snapshot("model", "ees_demo_ems")
        self.assertEqual(self.fixture.guard._state("model", before["asset"]),
                         self.fixture.guard._state("model", after["asset"]))
        self.assertEqual((await self.fixture.models.Models.get_model_by_id("fixture_model")).model_dump(), existing)
        # The old installer cannot resurrect or overwrite even after explicit restore.
        rejected = await self.apply(after, self.model_payload(after, "resurrected"),
                                    kind="model", identifier="ees_demo_ems")
        self.assertEqual(rejected.status_code, 410)

    async def test_retired_preset_remains_when_a_user_model_references_it(self):
        created = await self.fixture.request("POST", "/api/v1/models/create", payload={
            "id": "ees_demo_fdc", "name": "Historical synthetic preset", "base_model_id": "upstream",
            "params": {}, "meta": {"ees_demo_pack": "ees-demo-v1"}, "access_grants": []})
        self.assertEqual(created.status_code, 200, created.text)
        baseline = await self.retirement_preview("model", "ees_demo_fdc")
        bound = await self.fixture.request("POST", "/api/v1/models/create", payload={
            "id": "private_user_model", "name": "Private synthetic user name", "base_model_id": "ees_demo_fdc",
            "params": {"system": "Private synthetic user policy"}, "meta": {}, "access_grants": []})
        self.assertEqual(bound.status_code, 200, bound.text)
        before = (await self.fixture.models.Models.get_model_by_id("private_user_model")).model_dump()
        preview = await self.retirement_preview("model", "ees_demo_fdc", baseline["current_sha256"])
        self.assertFalse(preview["eligible"])
        self.assertEqual(preview["model_reference_count"], 1)
        self.assertIn("active_model_references", preview["blocked_reasons"])
        self.assertNotIn("private_user_model", json.dumps(preview))
        self.assertNotIn("Private synthetic", json.dumps(preview))
        result = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/apply", payload={
            "kind": "model", "id": "ees_demo_fdc", "baseline_sha256": baseline["current_sha256"],
            "expected_token": preview["expected_token"], "request_id": "synthetic-bound-001"})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertIsNotNone(await self.fixture.models.Models.get_model_by_id("ees_demo_fdc"))
        self.assertEqual((await self.fixture.models.Models.get_model_by_id("private_user_model")).model_dump(), before)
        self.assertFalse((self.fixture.directory / "ees-asset-retirement/synthetic-bound-001.json").exists())

    async def test_retired_tool_reference_blocks_delete_and_restore_retains_valves_and_personal_settings(self):
        from ees_asset_native_fixture import TOOL_CONTENT
        body = {"id": "ees_demo_data", "name": "Historical synthetic tool",
                "content": '\"\"\"\nees_demo_pack: ees-demo-v1\n\"\"\"\n' + TOOL_CONTENT,
                "meta": {"description": "historical"}, "access_grants": []}
        created = await self.fixture.request("POST", "/api/v1/tools/create", payload=body)
        self.assertEqual(created.status_code, 200, created.text)
        valve = await self.fixture.request("POST", "/api/v1/tools/id/ees_demo_data/valves/update", payload={"label": "SYNTHETIC_LOCAL_SETTING"})
        self.assertEqual(valve.status_code, 200, valve.text)
        self.fixture.users["reader"].settings = {"tools": {"valves": {"ees_demo_data": {"personal": "SYNTHETIC_PERSONAL_VALUE"},
                                                                    "jira_real": {"personal": "PRESERVE_REAL_CONNECTOR"}}}}
        settings = deepcopy(self.fixture.users["reader"].settings)
        model = await self.snapshot("model", "fixture_model")
        bound = self.model_payload(model, "initial")
        bound["meta"]["toolIds"] = ["ees_demo_data"]
        self.assertEqual((await self.fixture.request("POST", "/api/v1/models/model/update", payload=bound)).status_code, 200)
        first = await self.retirement_preview("tool", "ees_demo_data")
        preview = await self.retirement_preview("tool", "ees_demo_data", first["current_sha256"])
        self.assertIn("active_model_references", preview["blocked_reasons"])
        self.assertEqual(preview["model_reference_count"], 1)
        bound["meta"]["toolIds"] = []
        self.assertEqual((await self.fixture.request("POST", "/api/v1/models/model/update", payload=bound)).status_code, 200)
        preview = await self.retirement_preview("tool", "ees_demo_data", first["current_sha256"])
        self.assertTrue(preview["eligible"], preview)
        command = {"kind": "tool", "id": "ees_demo_data", "baseline_sha256": first["current_sha256"],
                   "expected_token": preview["expected_token"], "request_id": "synthetic-tool-001"}
        retired = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/apply", payload=command)
        self.assertEqual(retired.status_code, 200, retired.text)
        restore = {"request_id": command["request_id"], "backup_sha256": retired.json()["backup_sha256"]}
        for _ in range(2):
            restored = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/restore", payload=restore)
            self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(await self.fixture.tools.Tools.get_tool_valves_by_id("ees_demo_data"), {"label": "SYNTHETIC_LOCAL_SETTING"})
        self.assertEqual(self.fixture.users["reader"].settings, settings)
        tampered = self.fixture.directory / "ees-asset-retirement/synthetic-tool-001.json"
        value = json.loads(tampered.read_text(encoding="utf-8"))
        value["backup"]["asset"]["content"] += "# changed"
        tampered.write_text(json.dumps(value), encoding="utf-8")
        denied = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/restore", payload=restore)
        self.assertEqual(denied.status_code, 409)

    async def test_retirement_rejects_current_edit_unknown_id_and_nonadmin(self):
        await self.fixture.request("POST", "/api/v1/models/create", payload={
            "id": "ees_demo_apc", "name": "Synthetic former preset", "base_model_id": "upstream",
            "params": {"system": "baseline"}, "meta": {"ees_demo_pack": "ees-demo-v1"}, "access_grants": []})
        baseline = await self.retirement_preview("model", "ees_demo_apc")
        before = await self.snapshot("model", "ees_demo_apc")
        changed = self.model_payload(before, "User modified content must survive")
        edit = await self.fixture.request("POST", "/api/v1/models/model/update", payload=changed)
        self.assertEqual(edit.status_code, 200)
        result = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/apply", payload={
            "kind": "model", "id": "ees_demo_apc", "baseline_sha256": baseline["current_sha256"],
            "expected_token": baseline["expected_token"], "request_id": "synthetic-conflict-001"})
        self.assertEqual(result.status_code, 409)
        self.assertEqual((await self.snapshot("model", "ees_demo_apc"))["asset"]["params"]["system"],
                         "User modified content must survive")
        unknown = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/preview", payload={
            "kind": "model", "id": "fixture_model", "baseline_sha256": "0" * 64})
        self.assertEqual(unknown.status_code, 422)
        denied = await self.fixture.request("POST", "/api/v1/ees/assets/retirement/preview", user="reader", payload={
            "kind": "model", "id": "ees_demo_apc", "baseline_sha256": baseline["current_sha256"]})
        self.assertEqual(denied.status_code, 403)

    async def test_real_apply_client_and_shipped_manifest_never_recreate_retired_content(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("ees_native_client_contract", root / "scripts/ees_demo_assets.py")
        assets = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(assets)
        before_tool = await self.fixture.tools.Tools.get_tool_by_id("fixture_tool")
        before_model = await self.fixture.models.Models.get_model_by_id("fixture_model")
        class NoTransport:
            def request(self, *args, **kwargs):
                raise AssertionError("Retired registration must not contact the server")
        for _ in range(2):
            with self.assertRaisesRegex(assets.DemoAssetsError, "demo_registration_retired"):
                await asyncio.to_thread(assets.apply_assets, NoTransport(), root,
                    self.fixture.directory / "deployment-journal", "fixture_model", "a" * 40)
        self.assertEqual((await self.fixture.tools.Tools.get_tool_by_id("fixture_tool")).model_dump(), before_tool.model_dump())
        self.assertEqual((await self.fixture.models.Models.get_model_by_id("fixture_model")).model_dump(), before_model.model_dump())
        for model_id in ("ees_demo_ems", "ees_demo_apc", "ees_demo_fdc"):
            self.assertIsNone(await self.fixture.models.Models.get_model_by_id(model_id))


@unittest.skipUnless(WHEEL or REQUIRED, "real pinned-wheel native integration environment not requested")
class NativeAssetsSharedSessionTests(NativeAssetCases, unittest.IsolatedAsyncioTestCase):
    sharing = True


@unittest.skipUnless(WHEEL or REQUIRED, "real pinned-wheel native integration environment not requested")
class NativeAssetsIndependentSessionTests(NativeAssetCases, unittest.IsolatedAsyncioTestCase):
    sharing = False


@unittest.skipUnless(WHEEL or REQUIRED, "real pinned-wheel native integration environment not requested")
class NativeAuthoringAssetReadTests(unittest.IsolatedAsyncioTestCase):
    """Real Native asset tables/ACL + shipped authoring, synthetic user/groups.

    This extends the asset integration fixture, not the Native sign-in fixture.
    Tools, Skills, AccessGrants, permission checks and registry reads execute
    pinned upstream code; account/group lookups are explicitly synthetic.
    """

    async def asyncSetUp(self):
        if not WHEEL or not Path(WHEEL).is_file():
            self.fail("The required native asset gate needs EES_TEST_UPSTREAM_WHEEL")
        from ees_asset_native_fixture import NativeAssetFixture
        self.fixture = NativeAssetFixture(WHEEL)
        self.addAsyncCleanup(self.fixture.close)
        await self.fixture.start()
        fixture = self.fixture
        self.skills = fixture.load("open_webui.models.skills")
        async with fixture.engine.begin() as connection:
            await connection.run_sync(fixture.Base.metadata.create_all)
        for scope in ("public", "private"):
            tool_id, skill_id = "authoring_" + scope + "_tool", "authoring_" + scope + "_skill"
            response = await fixture.create_tool(tool_id, owner="owner")
            self.assertEqual(response.status_code, 200, response.text)
            skill = await self.skills.Skills.insert_new_skill("owner", self.skills.SkillForm(
                id=skill_id, name="합성 " + scope + " 스킬", content="NATIVE-" + scope.upper() + "-SKILL-BODY",
                access_grants=[]))
            self.assertIsNotNone(skill)
            await fixture.tools.Tools.update_tool_valves_by_id(tool_id, {"label": "기존 연결 설정 " + scope})
        for kind in ("tool", "skill"):
            await fixture.acl.AccessGrants.grant_access(kind, "authoring_public_" + kind, "user", "*", "read")
        # The permission object is also used by the fixture's Config.get path.
        # Native has_permission and the actual create route enforce these zeros.
        fixture.app.state.config.USER_PERMISSIONS["workspace"].update(
            {key: False for key in ("tools", "tools_import", "models", "skills", "knowledge", "prompts")})
        fixture.users["reader"].settings = {"tools": {"valves": {"authoring_public_tool": {
            "synthetic_personal_value": "retain-existing-user-settings"}}}}

        # Materialize exactly the same production-builder additions used by
        # this fixture's patched wheel, including JSON read relative to modules.
        with ZipFile(WHEEL) as archive:
            additions = fixture.builder.prepare_additions(archive, fixture.builder.UI_DIR)
        package = fixture.directory / "authoring-module"
        package.mkdir()
        for name, content in additions.items():
            if name.startswith("open_webui/ees_workflow") and name.endswith(".py") or name in (
                    "open_webui/workflow_seed.json", "open_webui/workflow_policy.json"):
                (package / Path(name).name).write_bytes(content)
                if name.endswith(".py"):
                    self.assertEqual(content, fixture.members[name])
        sys.modules["open_webui"].__path__.append(str(package))
        self.backend = importlib.import_module("open_webui.ees_workflow")

        async def current_user(key):
            return fixture.users.get(key)

        async def groups(key):
            return [{"id": "synthetic-ems-group", "name": "EMS 담당"}] if key == "reader" else []

        from workflow_fixture import historical_facade
        history = historical_facade("open_webui")
        self.service = history.WorkflowService(fixture.directory / "ees-work.sqlite3", current_user,
            lambda _: None, self.backend._registered_assets, group_lookup=groups,
            group_list_lookup=lambda: [{"id": "synthetic-ems-group", "name": "EMS 담당"}])
        from workflow_fixture import arrange_legacy_catalog
        arrange_legacy_catalog(self.service)
        self.backend._service = self.service
        self.backend.install(fixture.app, fixture.auth.get_verified_user)
        self.request_id = 0
        before_group_mapping = self.native_digest()
        linked = await self.action("set_system_group", user="admin", system_id="EMS", expected_mapping_revision=0,
            payload={"group_id": "synthetic-ems-group", "active": True})
        self.assertTrue(linked["ok"], linked)
        self.assertEqual(self.native_digest(), before_group_mapping, "EES group mapping must not mutate Native assets or users")

    async def action(self, action, process=None, *, user="reader", **extra):
        self.request_id += 1
        body = {"action": action, "request_id": "native-assets-" + str(self.request_id), "payload": {}}
        if process:
            body.update(system_id=process["owner_system"], process_id=process["process_id"],
                        expected_draft_revision=process["draft_revision"], expected_owner_revision=process["owner_revision"])
        body.update(extra)
        # Arrange/mutate an explicit historical definition through the retained
        # internal service; the retired public mutation endpoint stays closed.
        return await self.service.authoring_action(self.fixture.users[user], body)

    async def create_with_public_references(self):
        created = await self.action("create", system_id="EMS", payload={"name": "등록 자산 읽기 경계 점검", "category": "ops"})
        self.assertTrue(created["ok"], created)
        process = created["process"]
        document = deepcopy(process["workflow"])
        document["tools"]["new-native-tool"] = {"id": "new-native-tool", "name": "공개 도구 참조",
            "source": "open_webui", "reference": "authoring_public_tool", "adapter": "unavailable", "input": "db", "enabled": True}
        document["skills"]["new-native-skill"] = {"id": "new-native-skill", "name": "공개 스킬 참조", "type": "skill",
            "source": "open_webui", "reference": "authoring_public_skill", "body": ""}
        job = next(node for node in document["nodes"].values() if node["type"] == "j")
        job.update(mode="tool", tools=["new-native-tool"], skills=["new-native-skill"], bindings={"new-native-tool": "db"})
        saved = await self.action("save_draft", process, payload={"workflow": document})
        self.assertTrue(saved["ok"], saved)
        checked = await self.action("validate_draft", saved["process"])
        self.assertTrue(checked["ok"], checked)
        published = await self.action("publish", checked["process"])
        self.assertTrue(published["ok"], published)
        return published["process"]

    def native_digest(self):
        """Hash all logical Native rows, including source, valves, ACL and owners."""
        with closing(sqlite3.connect(self.fixture.directory / "webui.db")) as db, db:
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            rows = {name: sorted(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                    for name in names if not name.startswith("sqlite_")}
        serialized = json.dumps({"rows": rows, "users": {key: value.model_dump() for key, value in self.fixture.users.items()}},
                                ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    async def test_sa12_actual_native_public_asset_references_do_not_grant_workspace_or_write_assets(self):
        fixture = self.fixture
        before = self.native_digest()
        blocked = await fixture.request("POST", "/api/ees-work/authoring/action", user="reader", payload={"action": "create"})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "legacy_execution_retired")
        reader = fixture.users["reader"]
        self.assertEqual(reader.role, "user")
        permissions = await sys.modules["open_webui.models.config"].Config.get("user.permissions")
        for permission in ("workspace.tools", "workspace.models", "workspace.skills"):
            self.assertFalse(await sys.modules["open_webui.utils.access_control"].has_permission(reader.id, permission, permissions))
        self.assertEqual((await fixture.create_tool("must_not_be_created", owner="reader")).status_code, 401)
        with patch.object(fixture.plugin, "load_tool_module_by_id", side_effect=AssertionError("Authoring must not load Native tool code")):
            assets = await self.backend._registered_assets(reader)
            self.assertEqual({item["id"] for item in assets["tools"]}, {"authoring_public_tool"})
            self.assertEqual({item["id"] for item in assets["skills"]}, {"authoring_public_skill"})
            self.assertEqual(assets["skill_bodies"], {"authoring_public_skill": "NATIVE-PUBLIC-SKILL-BODY"})
            process = await self.create_with_public_references()
            selected = await fixture.request("GET", "/api/ees-work/authoring?system_id=EMS&process_id=" + process["process_id"], user="reader")
            self.assertEqual(selected.status_code, 200, selected.text)
            for secret in ("authoring_private_tool", "authoring_private_skill", "NATIVE-PRIVATE-SKILL-BODY", "NATIVE-PUBLIC-SKILL-BODY"):
                self.assertNotIn(secret, selected.text)
            for kind in ("tools", "skills"):
                document = deepcopy(process["workflow"])
                reference = next(iter(document[kind].values()))
                reference["reference"] = "authoring_private_" + ("tool" if kind == "tools" else "skill")
                refused = await self.action("save_draft", process, payload={"workflow": document})
                self.assertFalse(refused["ok"], refused)
                self.assertEqual(refused["error"]["code"], "reference_unavailable")
                self.assertNotIn("NATIVE-PRIVATE-SKILL-BODY", json.dumps(refused))
        self.assertEqual(self.native_digest(), before)
        self.assertEqual(reader.role, "user")

    async def test_sa12_18_actual_native_acl_revocation_keeps_opaque_draft_but_blocks_publication(self):
        before = self.native_digest()
        process = await self.create_with_public_references()
        self.assertEqual(self.native_digest(), before)
        for kind in ("tool", "skill"):
            changed = await self.fixture.acl.AccessGrants.revoke_access(kind, "authoring_public_" + kind, "user", "*", "read")
            self.assertTrue(changed)
        after_authorized_revoke = self.native_digest()
        self.assertNotEqual(after_authorized_revoke, before)
        assets = await self.backend._registered_assets(self.fixture.users["reader"])
        self.assertEqual(assets["tools"], [])
        self.assertEqual(assets["skills"], [])
        selected = await self.fixture.request("GET", "/api/ees-work/authoring?system_id=EMS&process_id=" + process["process_id"], user="reader")
        self.assertEqual(selected.status_code, 200, selected.text)
        current = selected.json()["process"]
        self.assertEqual(current["workflow"], process["workflow"], "Existing reference IDs remain in the saved draft")
        self.assertIsNone(current["validated_revision"])
        self.assertEqual(selected.json()["references"]["available_tools"], [])
        self.assertEqual(selected.json()["references"]["available_skills"], [])
        self.assertNotIn("NATIVE-PUBLIC-SKILL-BODY", selected.text)
        document = deepcopy(current["workflow"])
        document["nodes"][current["process_id"]]["description"] = "권한 회복 전 작업 메모 보존"
        saved = await self.action("save_draft", current, payload={"workflow": document})
        self.assertTrue(saved["ok"], saved)
        for action in ("validate_draft", "publish"):
            refused = await self.action(action, saved["process"])
            self.assertFalse(refused["ok"], refused)
            self.assertIn(refused["error"]["code"], ("reference_unavailable", "validation_required"))
        self.assertEqual(self.native_digest(), after_authorized_revoke)
        self.assertEqual(self.fixture.users["reader"].role, "user")


if __name__ == "__main__":
    unittest.main()
