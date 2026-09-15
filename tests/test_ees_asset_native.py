"""Required release integration gate for conditional writes on the real wheel.

Run with EES_TEST_UPSTREAM_WHEEL=<pinned wheel> and EES_REQUIRE_ASSET_NATIVE=1.
The ordinary dependency-light suite reports this optional environment as
unavailable; setting the release-gate variable makes missing input a failure.
These tests execute the production builder output and native SQLAlchemy asset
tables/routers, rather than replacing persistence with a mock dictionary.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


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

    async def test_real_apply_client_and_shipped_manifest_are_idempotent_on_native_api(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("ees_native_client_contract", root / "scripts/ees_demo_assets.py")
        assets = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(assets)
        loop = asyncio.get_running_loop()
        fixture = self.fixture

        class NativeClient:
            def __init__(self):
                self.writes = []

            def request(self, method, path, body=None):
                # Provider discovery has no bearing on native asset persistence.
                if path == "/api/models":
                    return {"data": [{"id": "upstream"}]}
                response = asyncio.run_coroutine_threadsafe(
                    fixture.request(method, path, payload=body), loop,
                ).result(timeout=15)
                if method == "GET" and response.status_code == 404:
                    return None
                if response.status_code >= 400:
                    raise assets.DemoAssetsError(response.json().get("detail", "native_api_error"))
                if path == assets.ASSET_API + "/apply":
                    self.writes.append((body["kind"], body["id"]))
                return response.json()

        client = NativeClient()
        manifest = assets.load_manifest(root)
        state = fixture.directory / "deployment-journal"
        before = await fixture.tools.Tools.get_tool_by_id("fixture_tool")
        result = await asyncio.to_thread(
            assets.apply_assets, client, root, state, "fixture_model", "a" * 40,
        )
        expected = len(manifest["tools"]) + sum(bool(item.get("managed_valves")) for item in manifest["tools"]) + len(manifest["models"]) + 1
        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["changed"], expected)
        self.assertEqual(len(client.writes), expected)
        repeated = await asyncio.to_thread(
            assets.apply_assets, client, root, state, "fixture_model", "a" * 40,
        )
        self.assertEqual(repeated["result"], "ok")
        self.assertEqual(repeated["changed"], 0)
        self.assertEqual(len(client.writes), expected)
        journal = json.loads((state / assets.STATE_FILE).read_text())
        self.assertTrue(all(row["status"] == "applied" for row in journal["assets"].values()))
        for item in manifest["tools"]:
            if item.get("managed_valves"):
                valves = await fixture.tools.Tools.get_tool_valves_by_id(item["id"])
                self.assertEqual(valves["ees_model_id"], "fixture_model")
        after = await fixture.tools.Tools.get_tool_by_id("fixture_tool")
        self.assertEqual(before.model_dump(), after.model_dump())


@unittest.skipUnless(WHEEL or REQUIRED, "real pinned-wheel native integration environment not requested")
class NativeAssetsSharedSessionTests(NativeAssetCases, unittest.IsolatedAsyncioTestCase):
    sharing = True


@unittest.skipUnless(WHEEL or REQUIRED, "real pinned-wheel native integration environment not requested")
class NativeAssetsIndependentSessionTests(NativeAssetCases, unittest.IsolatedAsyncioTestCase):
    sharing = False


if __name__ == "__main__":
    unittest.main()
