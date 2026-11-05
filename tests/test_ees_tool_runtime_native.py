"""Authored execution uses real Native ACL/encrypted actor settings and worker.

Authentication identities and surrounding app startup are fixture seams. The
HTTP handlers, SQLite models, patched loader/binder and child process are real;
no live external service or browser sign-in is claimed by this suite.
"""
import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import test_ees_tool_native as trial_tests


class AuthoredRuntimeNativeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = trial_tests.AuthoredNativeTests.asyncSetUp
    assert_code = trial_tests.AuthoredNativeTests.assert_code
    save = trial_tests.AuthoredNativeTests.save
    raw_settings = trial_tests.AuthoredNativeTests.raw_settings
    worker_package = trial_tests.AuthoredNativeTests.worker_package

    async def provision(self, *, tokens=True):
        metadata = await self.save("synthetic-admin-private")
        self.native_id = metadata["native_id"]
        self.group = await self.f.native_groups.Groups.insert_new_group("admin",
            self.f.native_groups.GroupForm(name="Execution readers", description="Synthetic execution group"))
        await self.f.native_groups.Groups.add_users_to_group(self.group.id, ["reader", "owner"])
        await self.adapter.set_groups(self.actor, self.native_id, [self.group.id], metadata["identity_stamp"])
        if tokens:
            for name in ("reader", "owner"):
                await self.f.tools.Tools.update_user_valves_by_id_and_user_id(self.native_id, name, {"PAT": "synthetic-" + name + "-private"})
        self.reader = self.f.users["reader"]
        self.snapshot = {"native_id": self.native_id, "base_url": "https://docs.invalid",
            "environment": "historical-first-confirmation-environment", "input_schema": {"type": "object", "properties": {}},
            "draft": {"function": "run", "code": "class Tools:\n    def run(self): return {'documents': [{'title': 'visible'}]}\n"}}
        return await self.adapter.inspect_execution(self.reader, self.native_id)

    async def execute(self, metadata, *, actor=None, guard=None, snapshot=None):
        return await self.adapter.run_execution(actor or self.reader, snapshot or self.snapshot, {}, metadata,
            {"run_id": "run-1", "job_id": "job-1", "call_id": "attempt-1", "case_id": "case-1", "plan_hash": "plan-1",
             "token": "must-not-be-forwarded", "arbitrary": "must-not-be-forwarded", "kind": "must-not-be-forwarded"},
            guard or AsyncMock(return_value=lambda: None))

    async def test_existing_native_user_settings_route_lists_inert_identity_and_preserves_other_accounts(self):
        await self.provision(tokens=False)
        # NativeReadFixture replaces Groups after router import; use the same
        # real model here too. Remote tool servers are outside this local path.
        self.f.tool_router.Groups = self.f.native_groups.Groups
        async def empty_remote_config(key, default=None, **kwargs):
            return default
        with patch.object(self.f.tool_router.Config, "get", side_effect=empty_remote_config):
            listed = await self.f.request("GET", "/api/v1/tools/", user="reader")
        self.assertEqual(listed.status_code, 200)
        identity = next(item for item in listed.json() if item["id"] == self.native_id)
        self.assertTrue(identity["has_user_valves"])
        base = "/api/v1/tools/id/" + self.native_id + "/valves/user"
        spec = await self.f.request("GET", base + "/spec", user="reader")
        self.assertEqual(spec.status_code, 200)
        self.assertEqual(set(spec.json()["properties"]), {"PAT"})
        self.assertEqual(spec.json()["properties"]["PAT"]["input"], {"type": "password"})
        saved = await self.f.request("POST", base + "/update", user="reader", payload={"PAT": "synthetic-reader-private"})
        self.assertEqual(saved.status_code, 200)
        own = await self.f.request("GET", base, user="reader")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json(), {"PAT": "synthetic-reader-private"})
        sealed = (await self.raw_settings("reader"))["tools"]["valves"][self.native_id]
        self.assertIsInstance(sealed, str)
        self.assertNotIn("synthetic-reader-private", sealed)
        self.assertEqual(await self.f.tools.Tools.get_user_valves_by_id_and_user_id(self.native_id, "admin"), {"PAT": "synthetic-admin-private"})
        denied = await self.f.request("POST", base + "/update", user="outsider", payload={"PAT": "synthetic-outsider-private"})
        self.assertEqual(denied.status_code, 401)
        original = await self.f.tools.Tools.get_tool_by_id(self.native_id)
        self.assertEqual(original.content, self.module.IDENTITY_CONTENT)
        self.assertEqual(original.specs, [])

    async def test_execution_accounts_are_isolated_and_only_server_context_reaches_exact_worker(self):
        reader_metadata = await self.provision()
        owner_metadata = await self.adapter.inspect_execution(self.f.users["owner"], self.native_id)
        self.assertNotEqual(reader_metadata["credential_stamp"], owner_metadata["credential_stamp"])
        self.snapshot["draft"]["code"] = '''from pydantic import BaseModel
class Tools:
    class UserValves(BaseModel):
        PAT: str = ''
    def run(self, __user__: dict, __metadata__: dict, __request__, __id__: str):
        token = __user__['valves'].PAT
        return {'actor': __user__['id'], 'correct_account': token == 'synthetic-' + __user__['id'] + '-private',
                'echo': token, 'metadata': __metadata__, 'path': __request__.url.path,
                'clean_request': len(__request__.headers) == 0, 'identity': __id__}
'''
        reader_guard, owner_guard = AsyncMock(return_value=lambda: None), AsyncMock(return_value=lambda: None)
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            results = await asyncio.gather(self.execute(reader_metadata, guard=reader_guard),
                self.execute(owner_metadata, actor=self.f.users["owner"], guard=owner_guard))
        for actor, result in zip(("reader", "owner"), results):
            self.assertEqual(result["status"], "succeeded", result)
            data = result["raw_result"]
            self.assertEqual(data["actor"], actor)
            self.assertTrue(data["correct_account"])
            self.assertEqual(data["echo"], "[REDACTED]")
            self.assertEqual(data["identity"], self.native_id)
            self.assertEqual(data["path"], "/api/ees-work/execution/worker")
            self.assertTrue(data["clean_request"])
            self.assertEqual(data["metadata"], {"kind": "authored_tool_execution", "run_id": "run-1", "job_id": "job-1",
                "call_id": "attempt-1", "case_id": "case-1", "plan_hash": "plan-1"})
            self.assertNotIn("synthetic-" + actor + "-private", json.dumps(result))
        self.assertEqual(reader_guard.await_count, 2)
        self.assertEqual(owner_guard.await_count, 2)
        # Runtime did not register the business function or modify credentials.
        self.assertEqual((await self.f.tools.Tools.get_tool_by_id(self.native_id)).content, self.module.IDENTITY_CONTENT)

    async def test_management_and_trial_methods_remain_admin_only(self):
        metadata = await self.provision()
        with patch("asyncio.create_subprocess_exec") as spawn:
            await self.assert_code("admin_required", self.adapter.inspect(self.reader, self.native_id))
            await self.assert_code("admin_required", self.adapter.run(self.reader, self.native_id, "", "run", "", {}, metadata))
            await self.assert_code("admin_required", self.adapter.save_connection(self.reader, self.tool_id, self.native_id, "replacement"))
            await self.assert_code("admin_required", self.adapter.set_groups(self.reader, self.native_id, [], metadata["identity_stamp"]))
        spawn.assert_not_called()

    async def test_missing_or_other_accounts_credentials_and_revoked_acl_block_before_dispatch(self):
        metadata = await self.provision(tokens=False)
        self.assertFalse(metadata["token_set"])
        with patch("asyncio.create_subprocess_exec") as spawn:
            await self.assert_code("native_personal_connection_required", self.execute(metadata))
            await self.f.tools.Tools.update_user_valves_by_id_and_user_id(self.native_id, "reader", {"PAT": "synthetic-reader-private"})
            own = await self.adapter.inspect_execution(self.reader, self.native_id)
            admin = await self.adapter.inspect(self.actor, self.native_id)
            await self.assert_code("tool_trial_snapshot_changed", self.execute(admin))
            await self.f.native_groups.Groups.remove_users_from_group(self.group.id, ["reader"])
            await self.assert_code("native_access_denied", self.execute(own))
        spawn.assert_not_called()

    async def test_pre_dispatch_work_gate_and_changes_during_it_never_spawn_worker(self):
        metadata = await self.provision()
        with patch("asyncio.create_subprocess_exec") as spawn:
            blocked = AsyncMock(side_effect=self.module.WorkflowError("shared_tool_version_changed", "private detail"))
            await self.assert_code("shared_tool_version_changed", self.execute(metadata, guard=blocked))
            async def rotate_token():
                await self.f.tools.Tools.update_user_valves_by_id_and_user_id(self.native_id, "reader", {"PAT": "rotated-private"})
                return lambda: None
            await self.assert_code("tool_trial_snapshot_changed", self.execute(metadata, guard=rotate_token))
        spawn.assert_not_called()

    async def test_post_dispatch_work_gate_failure_discards_result_and_preserves_unknown(self):
        metadata = await self.provision()
        guard = AsyncMock(side_effect=[lambda: None, self.module.WorkflowError("shared_tool_disabled", "private-secret-detail")])
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            result = await self.execute(metadata, guard=guard)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_code"], "shared_tool_disabled")
        self.assertIsNone(result["raw_result"])
        self.assertNotIn("private-secret-detail", json.dumps(result))
        self.assertEqual(guard.await_count, 2)

    async def test_post_dispatch_native_token_acl_role_and_environment_changes_hide_results(self):
        await self.provision()
        package = self.worker_package()
        async def change_token():
            await self.f.tools.Tools.update_user_valves_by_id_and_user_id(self.native_id, "reader", {"PAT": "rotated-private"})
        async def remove_membership():
            await self.f.native_groups.Groups.remove_users_from_group(self.group.id, ["reader"])
        async def revoke_role():
            await self.f.native_users.Users.update_user_by_id("reader", {"role": "pending"})
        for mutate, expected in ((change_token, "tool_trial_snapshot_changed"), (remove_membership, "native_access_denied"), (revoke_role, "unauthorized")):
            with self.subTest(change=mutate.__name__):
                await self.f.native_users.Users.update_user_by_id("reader", {"role": "user"})
                await self.f.native_groups.Groups.add_users_to_group(self.group.id, ["reader"])
                metadata = await self.adapter.inspect_execution(self.reader, self.native_id)
                calls = 0
                async def guard():
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        await mutate()
                    return lambda: None
                with patch.dict(os.environ, {"PYTHONPATH": package}):
                    result = await self.execute(metadata, guard=guard)
                self.assertEqual((result["status"], result["error_code"], result["raw_result"]), ("unknown", expected, None))
        await self.f.native_users.Users.update_user_by_id("reader", {"role": "user"})
        metadata = await self.adapter.inspect_execution(self.reader, self.native_id)
        calls = 0
        with patch.object(self.module, "authored_environment_fingerprint", return_value=metadata["environment"]) as environment:
            async def guard():
                nonlocal calls
                calls += 1
                if calls == 2:
                    environment.return_value = "new-runtime-environment"
                return lambda: None
            with patch.dict(os.environ, {"PYTHONPATH": package}):
                result = await self.execute(metadata, guard=guard)
        self.assertEqual((result["status"], result["error_code"], result["raw_result"]), ("unknown", "tool_trial_snapshot_changed", None))

    async def test_final_synchronous_work_gate_catches_changes_during_native_reads(self):
        metadata = await self.provision()
        # The minimal historical Native fixture does not create lifecycle
        # tables until the current tool-draft service is attached.
        self.f.workflow.ToolDrafts(self.f.service)
        def state(value):
            with self.f.service._db(write=True) as db:
                db.execute("INSERT INTO work_tool_uses VALUES(?,1,?) ON CONFLICT(tool_id) DO UPDATE SET data=excluded.data",
                    (self.tool_id, json.dumps({"state": value})))
        def current():
            with self.f.service._db() as db:
                value = json.loads(db.execute("SELECT data FROM work_tool_uses WHERE tool_id=?", (self.tool_id,)).fetchone()[0])
            if value["state"] != "active":
                raise self.module.WorkflowError("shared_tool_disabled", "사용 중지")
        async def guard():
            current()
            return current
        state("active")
        original_read, calls = self.adapter._read, 0
        async def disable_during_final_read(*args, **kwargs):
            nonlocal calls
            result = await original_read(*args, **kwargs)
            calls += 1
            if calls == 2:
                state("disabled")
            return result
        with patch.object(self.adapter, "_read", side_effect=disable_during_final_read), patch("asyncio.create_subprocess_exec") as spawn:
            await self.assert_code("shared_tool_disabled", self.execute(metadata, guard=guard))
        spawn.assert_not_called()
        state("active")
        original_inspect = self.adapter.inspect_execution
        async def disable_during_completion_read(*args, **kwargs):
            result = await original_inspect(*args, **kwargs)
            state("disabled")
            return result
        with patch.object(self.adapter, "inspect_execution", side_effect=disable_during_completion_read), \
                patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            result = await self.execute(metadata, guard=guard)
        self.assertEqual((result["status"], result["error_code"], result["raw_result"]), ("unknown", "shared_tool_disabled", None))

    async def test_missing_or_asynchronous_final_guard_fails_closed(self):
        metadata = await self.provision()
        with patch("asyncio.create_subprocess_exec") as spawn:
            await self.assert_code("tool_trial_snapshot_changed", self.execute(metadata, guard=AsyncMock(return_value=None)))
            await self.assert_code("tool_trial_snapshot_changed", self.execute(metadata, guard=AsyncMock(return_value=AsyncMock())))
        spawn.assert_not_called()

    async def test_native_role_change_during_acl_observation_does_not_use_stale_admin_bypass(self):
        await self.provision()
        original = self.adapter._identity
        async def demote(actor, registry, db):
            result = await original(actor, registry, db)
            await self.f.native_users.Users.update_user_by_id("admin", {"role": "user"})
            return result
        with patch.object(self.adapter, "_identity", side_effect=demote):
            await self.assert_code("unauthorized", self.adapter.inspect_execution(self.actor, self.native_id))

    async def test_actor_stamp_blocks_role_and_admin_group_changes_after_work_gate_before_dispatch(self):
        await self.provision()
        await self.f.native_groups.Groups.add_users_to_group(self.group.id, ["admin"])
        admin_metadata = await self.adapter.inspect_execution(self.actor, self.native_id)
        self.assertEqual(len(admin_metadata["actor_stamp"]), 64)
        self.assertNotIn("actor_stamp", await self.adapter.inspect(self.actor, self.native_id))
        async def remove_group():
            await self.f.native_groups.Groups.remove_users_from_group(self.group.id, ["admin"])
            return lambda: None
        with patch("asyncio.create_subprocess_exec") as spawn:
            await self.assert_code("tool_trial_snapshot_changed", self.execute(admin_metadata, actor=self.actor, guard=remove_group))
            # The Native owner still has read access and the PAT is unchanged;
            # only the current actor observation detects the Work-group loss.
            changed = await self.adapter.inspect_execution(self.actor, self.native_id)
            self.assertEqual(changed["credential_stamp"], admin_metadata["credential_stamp"])
            self.assertEqual(changed["identity_stamp"], admin_metadata["identity_stamp"])
            self.assertNotEqual(changed["actor_stamp"], admin_metadata["actor_stamp"])
            async def demote():
                await self.f.native_users.Users.update_user_by_id("admin", {"role": "user"})
                return lambda: None
            await self.assert_code("tool_trial_snapshot_changed", self.execute(changed, actor=self.actor, guard=demote))
        spawn.assert_not_called()

    async def test_actor_stamp_hides_completed_result_after_admin_role_or_membership_change(self):
        await self.provision()
        package = self.worker_package()
        async def remove_group():
            await self.f.native_groups.Groups.remove_users_from_group(self.group.id, ["admin"])
        async def demote():
            await self.f.native_users.Users.update_user_by_id("admin", {"role": "user"})
        for mutate in (remove_group, demote):
            with self.subTest(change=mutate.__name__):
                await self.f.native_users.Users.update_user_by_id("admin", {"role": "admin"})
                await self.f.native_groups.Groups.add_users_to_group(self.group.id, ["admin"])
                metadata = await self.adapter.inspect_execution(self.actor, self.native_id)
                calls = 0
                async def guard():
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        await mutate()
                    return lambda: None
                with patch.dict(os.environ, {"PYTHONPATH": package}):
                    result = await self.execute(metadata, actor=self.actor, guard=guard)
                self.assertEqual((result["status"], result["error_code"], result["raw_result"]),
                                 ("unknown", "tool_trial_snapshot_changed", None))


if __name__ == "__main__":
    unittest.main()
