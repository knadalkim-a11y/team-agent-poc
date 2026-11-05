"""Authored settings over real pinned Native persistence; isolated worker trials."""
import ast
import asyncio
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from test_ees_workflow_native import WHEEL


class AuthoredNativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not WHEEL.is_file():
            if os.environ.get("EES_REQUIRE_ASSET_NATIVE") == "1":
                self.fail("Pinned Native wheel unavailable")
            self.skipTest("Pinned Native wheel unavailable")
        from ees_workflow_native_fixture import NativeReadFixture
        self.f = NativeReadFixture(WHEEL)
        self.addAsyncCleanup(self.f.close)
        await self.f.start()
        self.module = importlib.import_module("open_webui.ees_workflow_tool_native")
        self.adapter = self.module.AuthoredNative(self.f.service)
        self.actor = self.f.users["admin"]
        self.tool_id = "draft-" + "a" * 32

    async def assert_code(self, code, operation):
        with self.assertRaises(self.module.WorkflowError) as caught:
            await operation
        self.assertEqual(caught.exception.code, code)

    async def save(self, token="synthetic-personal-pat"):
        return await self.adapter.save_connection(self.actor, self.tool_id, None, token)

    async def raw_settings(self, actor="admin"):
        from sqlalchemy import select
        async with self.f.sessions() as db:
            return (await db.execute(select(self.f.native_users.User.settings).where(self.f.native_users.User.id == actor))).scalar_one()

    def worker_package(self):
        """Supply the actually patched loader/guard and pinned binder to a child.

        Native app/DB startup is deliberately absent in this process fixture.
        Business code, process IO, installed loader guard and binding execute for real; no
        external service or installed whole-app claim is made by these tests.
        """
        root = self.f.directory / "worker-package"
        package = root / "open_webui" / "utils"
        package.mkdir(parents=True)
        (root / "open_webui/__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        (root / "open_webui/ees_asset_guard.py").write_bytes(self.f.members["open_webui/ees_asset_guard.py"])
        with ZipFile(WHEEL) as wheel:
            source = self.f.members["open_webui/utils/plugin.py"].decode("utf-8")
            tree = ast.parse(source)
            selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name in {"extract_frontmatter", "load_tool_module_by_id"}]
            loader = "from __future__ import annotations\nimport asyncio, types, sys, tempfile, os, re, logging\nfrom open_webui.ees_asset_guard import guard_operation, guard_plugin_loader\nENABLE_PLUGINS=True\nlog=logging.getLogger('trial')\ndef install_frontmatter_requirements(value):\n    assert not value\n"
            definitions = ["\n".join(source.splitlines()[min([node.lineno] + [item.lineno for item in node.decorator_list]) - 1:node.end_lineno]) for node in selected]
            (package / "plugin.py").write_text(loader + "\n".join(definitions), encoding="utf-8")
            source = wheel.read("open_webui/utils/tools.py").decode("utf-8")
            node = next(node for node in ast.parse(source).body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_async_tool_function_and_apply_extra_params")
            binding = "from __future__ import annotations\nimport inspect\nfrom functools import partial, update_wrapper\nfrom typing import Callable, Awaitable, get_type_hints, get_args\n"
            (package / "tools.py").write_text(binding + ast.get_source_segment(source, node), encoding="utf-8")
        return str(root)

    async def test_identity_is_inert_and_native_encrypted_personal_storage_is_preserved(self):
        before = {"ui": {"theme": "dark"}, "tools": {"valves": {"unrelated": "existing-sealed-value"}}, "other": {"keep": [1, 2]}}
        await self.f.native_users.Users.update_user_by_id("admin", {"settings": before})
        with patch.object(self.f.plugin, "load_tool_module_by_id", side_effect=AssertionError("settings must not execute source")):
            meta = await self.save()
            again = await self.save("")
        self.assertEqual(meta, again)
        self.assertNotIn("synthetic-personal-pat", json.dumps(meta))
        tool = await self.f.tools.Tools.get_tool_by_id(meta["native_id"])
        self.assertEqual(tool.content, self.module.IDENTITY_CONTENT)
        self.assertEqual(tool.specs, [])
        self.assertEqual(tool.access_grants, [])
        settings = await self.raw_settings()
        self.assertEqual(settings["ui"], before["ui"])
        self.assertEqual(settings["other"], before["other"])
        self.assertEqual(settings["tools"]["valves"]["unrelated"], before["tools"]["valves"]["unrelated"])
        sealed = settings["tools"]["valves"][meta["native_id"]]
        self.assertIsInstance(sealed, str)
        self.assertNotIn("synthetic-personal-pat", sealed)
        personal = await self.f.tools.Tools.get_user_valves_by_id_and_user_id(meta["native_id"], "admin")
        self.assertEqual(personal, {"PAT": "synthetic-personal-pat"})
        self.assertNotIn(meta["native_id"], (await self.raw_settings("reader") or {}).get("tools", {}).get("valves", {}))

    async def test_user_changes_and_preexisting_native_collision_are_never_overwritten(self):
        identifier = "ees-authored-" + self.tool_id[6:]
        form = self.f.tools.ToolForm(id=identifier, name="Existing", content="class Tools: pass", meta={})
        await self.f.tools.Tools.insert_new_tool("owner", form, [])
        await self.assert_code("tool_connection_identity_changed", self.save())
        tool = await self.f.tools.Tools.get_tool_by_id(identifier)
        self.assertEqual(tool.content, "class Tools: pass")
        self.assertEqual(tool.user_id, "owner")

    async def test_identity_changes_and_current_acl_fail_closed(self):
        meta = await self.save()
        await self.f.tools.Tools.update_tool_by_id(meta["native_id"], {"content": "class Tools: pass"})
        await self.assert_code("tool_connection_identity_changed", self.adapter.inspect(self.actor, meta["native_id"]))
        await self.assert_code("tool_connection_identity_changed", self.save("replacement"))

    async def test_encryption_gate_bad_ciphertext_and_nonadmin_are_rejected(self):
        with patch.object(sys.modules["open_webui.env"], "ENABLE_VALVE_ENCRYPTION", False):
            await self.assert_code("encryption_required", self.save())
        meta = await self.save()
        settings = await self.raw_settings()
        settings["tools"]["valves"][meta["native_id"]] = "not-valid-ciphertext"
        await self.f.native_users.Users.update_user_by_id("admin", {"settings": settings})
        await self.assert_code("tool_connection_credentials_unavailable", self.adapter.inspect(self.actor, meta["native_id"]))
        await self.assert_code("admin_required", self.adapter.inspect(self.f.users["reader"], meta["native_id"]))

    async def test_concurrent_other_settings_edit_is_not_overwritten(self):
        meta = await self.save()
        original = self.adapter._credentials
        first = True
        async def concurrent(actor, native_id, db):
            nonlocal first
            value = await original(actor, native_id, db)
            if first:
                first = False
                changed = deepcopy(value[0])
                changed["ui"] = {"theme": "concurrent"}
                await self.f.native_users.Users.update_user_by_id("admin", {"settings": changed})
            return value
        with patch.object(self.adapter, "_credentials", side_effect=concurrent):
            await self.assert_code("tool_connection_conflict", self.save("new-secret"))
        self.assertEqual((await self.raw_settings())["ui"], {"theme": "concurrent"})
        self.assertEqual((await self.adapter.inspect(self.actor, meta["native_id"]))["credential_stamp"], meta["credential_stamp"])

    async def test_identity_change_during_token_save_rolls_back_the_personal_write(self):
        meta = await self.save()
        before = await self.raw_settings()
        original = self.adapter._credentials
        async def changed(actor, native_id, db):
            value = await original(actor, native_id, db)
            await self.f.tools.Tools.update_tool_by_id(native_id, {"content": "class Tools: pass"})
            return value
        with patch.object(self.adapter, "_credentials", side_effect=changed):
            await self.assert_code("tool_connection_identity_changed", self.save("must-not-persist"))
        self.assertEqual(await self.raw_settings(), before)
        self.assertEqual((await self.f.tools.Tools.get_tool_by_id(meta["native_id"])).content, "class Tools: pass")

    async def test_last_role_lookup_token_rotation_is_observed_in_returned_metadata(self):
        meta = await self.save()
        original = self.adapter._admin
        calls = 0
        async def rotate(user):
            nonlocal calls
            actor = await original(user)
            calls += 1
            if calls == 2:
                await self.f.tools.Tools.update_user_valves_by_id_and_user_id(meta["native_id"], "admin", {"PAT": "rotated-after-role-check"})
            return actor
        with patch.object(self.adapter, "_admin", side_effect=rotate):
            observed = await self.adapter.inspect(self.actor, meta["native_id"])
        self.assertNotEqual(observed["credential_stamp"], meta["credential_stamp"])
        self.assertEqual(observed, await self.adapter.inspect(self.actor, meta["native_id"]))

    async def test_group_update_uses_identity_cas_and_does_not_change_personal_credentials(self):
        meta = await self.save()
        group = await self.f.native_groups.Groups.insert_new_group("admin", self.f.native_groups.GroupForm(name="Trial readers", description="Synthetic trial group"))
        new = await self.adapter.set_groups(self.actor, meta["native_id"], [group.id], meta["identity_stamp"])
        self.assertNotEqual(new["identity_stamp"], meta["identity_stamp"])
        self.assertEqual(new["credential_stamp"], meta["credential_stamp"])
        await self.assert_code("tool_connection_conflict", self.adapter.set_groups(self.actor, meta["native_id"], [], meta["identity_stamp"]))
        tool = await self.f.tools.Tools.get_tool_by_id(meta["native_id"])
        self.assertEqual([(grant.principal_type, grant.principal_id, grant.permission) for grant in tool.access_grants], [("group", group.id, "read")])

    async def test_connection_first_read_and_nested_save_use_the_existing_native_guard(self):
        observed = []
        original = self.adapter._admin
        async def observe(user):
            observed.append(self.f.guard._active_guard().owned())
            return await original(user)
        with patch.object(self.adapter, "_admin", side_effect=observe):
            first = await self.save()
            second = await self.f.guard._active_guard().run(lambda: self.save("synthetic-rotated-pat"))
        self.assertTrue(observed)
        self.assertTrue(all(observed), "The initial read and final inspect must stay in the Native guard's owning task")
        self.assertEqual(first["native_id"], second["native_id"])
        self.assertNotEqual(first["credential_stamp"], second["credential_stamp"])

    async def test_native_acl_writer_waits_for_authored_save_and_its_committed_change_survives(self):
        meta = await self.save()
        settings = await self.raw_settings()
        requested = await self.f.native_groups.Groups.insert_new_group("admin", self.f.native_groups.GroupForm(name="Authored access", description="Synthetic authored group"))
        concurrent = await self.f.native_groups.Groups.insert_new_group("admin", self.f.native_groups.GroupForm(name="Native editor access", description="Synthetic concurrent group"))
        entered, release, writer_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = self.adapter._admin
        calls = 0
        async def pause_after_identity(user):
            nonlocal calls
            actor = await original(user)
            calls += 1
            if calls == 2:
                entered.set()
                await release.wait()
            return actor
        async def native_edit():
            writer_started.set()
            return await self.f.acl.AccessGrants.grant_access("tool", meta["native_id"], "group", concurrent.id, "read")
        with patch.object(self.adapter, "_admin", side_effect=pause_after_identity):
            authored = asyncio.create_task(self.adapter.set_groups(self.actor, meta["native_id"], [requested.id], meta["identity_stamp"]))
            writer = None
            try:
                await asyncio.wait_for(entered.wait(), 3)
                writer = asyncio.create_task(native_edit())
                await asyncio.wait_for(writer_started.wait(), 3)
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(writer), 0.05)
            finally:
                release.set()
                outcomes = await asyncio.wait_for(asyncio.gather(*[task for task in (authored, writer) if task], return_exceptions=True), 5)
        self.assertFalse(any(isinstance(value, BaseException) for value in outcomes), outcomes)
        self.assertEqual(outcomes[0]["groups"], [requested.id])
        self.assertTrue(outcomes[1])
        tool = await self.f.tools.Tools.get_tool_by_id(meta["native_id"])
        grants = {(grant.principal_type, grant.principal_id, grant.permission) for grant in tool.access_grants}
        expected = {("group", requested.id, "read"), ("group", concurrent.id, "read")}
        self.assertEqual(grants, expected)
        # Once the queued Native edit has committed, an authored save carrying
        # the earlier identity must fail before deleting that user's change.
        await self.assert_code("tool_connection_identity_changed", self.adapter.set_groups(self.actor, meta["native_id"], [], outcomes[0]["identity_stamp"]))
        preserved = await self.f.tools.Tools.get_tool_by_id(meta["native_id"])
        self.assertEqual({(grant.principal_type, grant.principal_id, grant.permission) for grant in preserved.access_grants}, expected)
        self.assertEqual(await self.raw_settings(), settings)

    async def test_worker_uses_exact_source_native_binding_defaults_and_redacts_all_outputs(self):
        meta = await self.save()
        code = '''from pydantic import BaseModel
import os
class Tools:
    class Valves(BaseModel):
        BASE_URL: str = ''
        CONFLUENCE_BASE_URL: str = ''
        ENABLED: bool = False
        ALLOW_HTTP: bool = False
        untouched: int = 7
    class UserValves(BaseModel):
        PAT: str = ''
    def list_documents(self, q: str, __user__: dict, __id__: str, __metadata__: dict):
        print(__user__['valves'].PAT)
        os.write(2, __user__['valves'].PAT.encode())
        return {'documents': [{'title': __user__['valves'].PAT, 'url': self.valves.BASE_URL + '/doc'}], 'actor': __user__['id'], 'identity': __id__, 'service': self.valves.CONFLUENCE_BASE_URL, 'enabled': self.valves.ENABLED, 'allow_http': self.valves.ALLOW_HTTP, 'untouched': self.valves.untouched, 'q': q, 'kind': __metadata__['kind']}
'''
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            result = await self.adapter.run(self.actor, meta["native_id"], code, "list_documents", "https://docs.invalid", {"q": "synthetic"}, meta)
        self.assertEqual(result["status"], "succeeded", result)
        data = result["raw_result"]
        self.assertEqual(data["documents"][0]["title"], "[REDACTED]")
        self.assertEqual(data["service"], "https://docs.invalid")
        self.assertEqual(data["actor"], "admin")
        self.assertEqual(data["identity"], meta["native_id"])
        self.assertEqual(data["kind"], "authored_tool_trial")
        self.assertFalse(data["enabled"])
        self.assertFalse(data["allow_http"])
        self.assertEqual(data["untouched"], 7)
        self.assertNotIn("synthetic-personal-pat", json.dumps(result))
        self.assertEqual(await self.adapter.redact(self.actor, meta["native_id"], {"q": "synthetic-personal-pat"}), {"q": "[REDACTED]"})

    async def test_worker_rejects_requirements_times_out_and_never_retries(self):
        meta = await self.save()
        package = self.worker_package()
        requirement = '"""\nrequirements: definitely-not-installed\n"""\nclass Tools: pass\n'
        with patch.dict(os.environ, {"PYTHONPATH": package}):
            result = await self.adapter.run(self.actor, meta["native_id"], requirement, "anything", "https://docs.invalid", {}, meta)
            self.assertEqual(result["error_code"], "native_requirements_unsupported")
            marker = self.f.directory / "once.txt"
            code = "from pathlib import Path\nimport time\nclass Tools:\n    def run(self):\n        p=Path(" + repr(str(marker)) + ")\n        p.write_text(p.read_text(encoding='utf-8')+'x' if p.exists() else 'x',encoding='utf-8')\n        time.sleep(30)\n"
            # Include the real installed guard's FastAPI/Pydantic import time.
            with patch.object(self.module, "WORKER_TIMEOUT_SECONDS", 3):
                result = await self.adapter.run(self.actor, meta["native_id"], code, "run", "https://docs.invalid", {}, meta)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["error_code"], "tool_trial_timeout")
            self.assertEqual(marker.read_text(encoding="utf-8"), "x")

    async def test_worker_changed_credentials_and_missing_pat_never_dispatch(self):
        meta = await self.save()
        await self.save("rotated")
        with patch("asyncio.create_subprocess_exec", side_effect=AssertionError("must not dispatch")):
            await self.assert_code("tool_trial_snapshot_changed", self.adapter.run(self.actor, meta["native_id"], "", "f", "", {}, meta))
        self.tool_id = "draft-" + "b" * 32
        meta = await self.save("")
        with patch("asyncio.create_subprocess_exec", side_effect=AssertionError("must not dispatch")):
            await self.assert_code("native_personal_connection_required", self.adapter.run(self.actor, meta["native_id"], "", "f", "", {}, meta))

    async def test_worker_result_limits_exceptions_and_post_dispatch_revocation_hide_results(self):
        meta = await self.save()
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            oversized = "class Tools:\n    def run(self):\n        return {'documents': [{'title': 'x' * 2200000}]}\n"
            result = await self.adapter.run(self.actor, meta["native_id"], oversized, "run", "https://docs.invalid", {}, meta)
            self.assertEqual(result["error_code"], "tool_trial_result_too_large")
            exception = "class Tools:\n    def run(self, __user__: dict):\n        raise ValueError(__user__['valves'].PAT)\n"
            result = await self.adapter.run(self.actor, meta["native_id"], exception, "run", "https://docs.invalid", {}, meta)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["error_code"], "tool_trial_worker_invoke_failed")
            self.assertNotIn("synthetic-personal-pat", json.dumps(result))
            original = self.adapter._admin
            calls = 0
            async def revoked(user):
                nonlocal calls
                calls += 1
                # _read checks twice; the first post-process check revokes.
                if calls == 3:
                    await self.f.native_users.Users.update_user_by_id("admin", {"role": "user"})
                return await original(user)
            with patch.object(self.adapter, "_admin", side_effect=revoked):
                await self.assert_code("admin_required", self.adapter.run(self.actor, meta["native_id"], "class Tools:\n    def run(self): return {'documents': []}\n", "run", "https://docs.invalid", {}, meta))

    async def test_worker_required_unsupported_reserved_parameters_are_explicit_failures(self):
        meta = await self.save()
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            for reserved in ("__event_emitter__", "__event_call__", "__files__", "__messages__"):
                code = "class Tools:\n    def run(self, " + reserved + "):\n        raise AssertionError('must not dispatch')\n"
                result = await self.adapter.run(self.actor, meta["native_id"], code, "run", "https://docs.invalid", {}, meta)
                self.assertEqual(result["status"], "failed", reserved)
                self.assertEqual(result["error_code"], "tool_trial_reserved_unsupported", reserved)

    async def test_worker_import_failure_reports_only_a_fixed_stage_without_exception_secrets(self):
        meta = await self.save()
        root = Path(self.worker_package())
        (root / "open_webui/utils/plugin.py").write_text("raise RuntimeError('synthetic-personal-pat')\n", encoding="utf-8")
        with patch.dict(os.environ, {"PYTHONPATH": str(root)}):
            result = await self.adapter.run(self.actor, meta["native_id"], "class Tools:\n    def run(self): return []\n",
                                            "run", "https://docs.invalid", {}, meta)
        self.assertEqual((result["status"], result["error_code"]), ("unknown", "tool_trial_worker_import_failed"))
        self.assertIsNone(result["raw_result"])
        self.assertNotIn("synthetic-personal-pat", json.dumps(result))
        self.assertNotIn("RuntimeError", json.dumps(result))

    async def test_patched_native_loader_allows_exact_content_without_opening_writers_or_cache(self):
        from fastapi import HTTPException
        source = "class Tools:\n    def read(self): return {'documents': []}\n"
        with patch.object(self.f.guard, "_guard", None), \
                patch.object(self.f.tools.Tools, "get_tool_by_id", AsyncMock(side_effect=AssertionError("No Native asset read"))) as read:
            instance, _ = await self.f.plugin.load_tool_module_by_id("standalone-synthetic", content=source)
            self.assertEqual(instance.read(), {"documents": []})
            read.assert_not_awaited()
            for values in ({}, {"content": None}, {"content": b"source"}, {"content": 1}):
                with self.assertRaises(HTTPException) as caught:
                    await self.f.plugin.load_tool_module_by_id("stored-tool", **values)
                self.assertEqual((caught.exception.status_code, caught.exception.detail), (503, "conditional_write_unavailable"))
            with self.assertRaises(HTTPException):
                await self.f.plugin.get_tool_module_from_cache(None, "stored-tool")
            with self.assertRaises(HTTPException):
                await self.f.tools.Tools.update_tool_by_id("stored-tool", {"content": source})
            read.assert_not_awaited()

    async def test_real_workflow_connection_worker_and_use_activation_round_trip(self):
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads((root / "tests/fixtures/tools_phase2_contract.json").read_text(encoding="utf-8"))
        group = await self.f.native_groups.Groups.insert_new_group("admin", self.f.native_groups.GroupForm(name="Authored lifecycle", description="Synthetic group"))
        service = self.f.workflow.WorkflowService(self.f.directory / "authored-integration.sqlite3",
            self.f.native_users.Users.get_user_by_id, lambda _: None,
            group_lookup=self.f.native_groups.Groups.get_groups_by_member_id, group_list_lookup=lambda: [group])
        async def command(action, request_id, **values):
            return await service.operations.command(self.actor, {"action": action, "request_id": request_id, **values})
        draft = (await command("tool_draft_save", "native-roundtrip-save", expected_revision=0, draft=fixture["draft"]))["tool_draft"]
        connected = await command("tool_draft_connection_save", "native-roundtrip-connect", tool_id=draft["id"],
                                  expected_revision=1, expected_connection_revision=0, **fixture["connection"])
        self.assertTrue(connected["ok"], connected)
        with patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            trial = (await command("tool_draft_trial_start", "native-roundtrip-trial", tool_id=draft["id"],
                                   expected_revision=1, expected_connection_revision=1, inputs=fixture["inputs"]))["trial"]
        self.assertEqual((trial["status"], trial["count"], trial["eligible_for_activation"]), ("succeeded", 2, True), trial)
        self.assertEqual(trial["raw_result"], fixture["result"])
        activated = await command("tool_draft_use_set", "native-roundtrip-use", tool_id=draft["id"], trial_id=trial["id"],
                                  expected_revision=1, expected_connection_revision=1, expected_use_revision=0,
                                  groups=[group.id], evidence=fixture["evidence"])
        self.assertEqual((activated["use"]["state"], activated["use"]["active_version"]), ("active", 1))
        carrier = await self.f.tools.Tools.get_tool_by_id(connected["connection"]["native_id"])
        self.assertEqual(carrier.content, self.module.IDENTITY_CONTENT)
        self.assertEqual(carrier.specs, [])
        with service._db() as db:
            stored = " ".join(row[0] for table in ("work_tool_trials", "work_tool_connections", "work_tool_authored_versions", "work_tool_connection_receipts")
                              for row in db.execute("SELECT data FROM " + table))
        self.assertNotIn(fixture["connection"]["token"], stored)

    async def test_deployed_worker_bytes_invalidate_trial_activation_and_resume(self):
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads((root / "tests/fixtures/tools_phase2_contract.json").read_text(encoding="utf-8"))
        deployed = self.f.directory / "deployed-authored"
        deployed.mkdir()
        source = Path(self.module.__file__).parent
        originals = {name: (Path(self.f.guard.__file__) if name == "ees_asset_guard.py" else source / name).read_bytes()
                     for name in self.module.AUTHORED_ENVIRONMENT_FILES}
        for name, content in originals.items():
            (deployed / name).write_bytes(content)
        group = await self.f.native_groups.Groups.insert_new_group("admin", self.f.native_groups.GroupForm(name="Deployment readers", description="Synthetic group"))
        service = self.f.workflow.WorkflowService(self.f.directory / "deployment.sqlite3",
            self.f.native_users.Users.get_user_by_id, lambda _: None,
            group_lookup=self.f.native_groups.Groups.get_groups_by_member_id, group_list_lookup=lambda: [group])
        async def command(action, request_id, **values):
            return await service.operations.command(self.actor, {"action": action, "request_id": request_id, **values})
        with patch.object(self.module, "__file__", str(deployed / Path(self.module.__file__).name)), \
                patch.object(self.f.guard, "__file__", str(deployed / "ees_asset_guard.py")), \
                patch.dict(os.environ, {"PYTHONPATH": self.worker_package()}):
            native_environment = self.module.environment_fingerprint()
            authored_environment = self.module.authored_environment_fingerprint()
            for name, content in originals.items():
                (deployed / name).write_bytes(content + b"\n# deployed module changed\n")
                self.assertNotEqual(self.module.authored_environment_fingerprint(), authored_environment, name)
                self.assertEqual(self.module.environment_fingerprint(), native_environment)
                (deployed / name).write_bytes(content)
            worker = deployed / "ees_workflow_tool_worker.py"
            worker.unlink()
            with self.assertRaises(self.module.WorkflowError) as caught:
                self.module.authored_environment_fingerprint()
            self.assertEqual(caught.exception.code, "tool_trial_environment_unavailable")
            worker.write_bytes(originals[worker.name])
            draft = (await command("tool_draft_save", "deployment-save", expected_revision=0, draft=fixture["draft"]))["tool_draft"]
            fields = {"tool_id": draft["id"], "expected_revision": 1, "expected_connection_revision": 1}
            await command("tool_draft_connection_save", "deployment-connect", **{**fields, "expected_connection_revision": 0}, **fixture["connection"])
            trial = (await command("tool_draft_trial_start", "deployment-trial", **fields, inputs=fixture["inputs"]))["trial"]
            self.assertTrue(trial["eligible_for_activation"], trial)
            await command("tool_draft_use_set", "deployment-use", **fields, trial_id=trial["id"], expected_use_revision=0,
                          groups=[group.id], evidence=fixture["evidence"])
            await command("tool_draft_use_disable", "deployment-disable", tool_id=draft["id"], expected_use_revision=1)
            worker.write_bytes(originals[worker.name] + b"\n# new deployed worker revision\n")
            stale = (await command("tool_draft_trial_get", "deployment-get", tool_id=draft["id"], trial_id=trial["id"]))["trial"]
            self.assertFalse(stale["eligible_for_activation"])
            self.assertIn("tool_trial_credentials_changed", [item["code"] for item in stale["activation_reasons"]])
            await self.assert_code("tool_trial_stale", command("tool_draft_use_set", "deployment-stale-use", **fields,
                trial_id=trial["id"], expected_use_revision=2, groups=[group.id], evidence=fixture["evidence"]))
            await self.assert_code("tool_use_snapshot_invalid", command("tool_draft_use_enable", "deployment-stale-enable",
                tool_id=draft["id"], expected_use_revision=2))
            fresh = (await command("tool_draft_trial_start", "deployment-fresh-trial", **fields, inputs=fixture["inputs"]))["trial"]
            self.assertTrue(fresh["eligible_for_activation"], fresh)
            confirmed = (await command("tool_draft_use_set", "deployment-confirm", **fields, trial_id=fresh["id"],
                expected_use_revision=2, groups=[group.id], evidence=fixture["evidence"]))["use"]
            self.assertEqual((confirmed["active_version"], confirmed["state"]), (1, "disabled"))
            enabled = (await command("tool_draft_use_enable", "deployment-enable", tool_id=draft["id"], expected_use_revision=3))["use"]
            self.assertEqual((enabled["active_version"], enabled["state"]), (1, "active"))


if __name__ == "__main__":
    unittest.main()
