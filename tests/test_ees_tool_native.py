"""Authored settings over real pinned Native persistence; isolated worker trials."""
import ast
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
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
        """Supply exact pinned loader/binder definitions to a child interpreter.

        Native app/DB startup is deliberately absent in this process fixture.
        Business code, process IO, loader and binding execute for real; no
        external service or installed whole-app claim is made by these tests.
        """
        root = self.f.directory / "worker-package"
        package = root / "open_webui" / "utils"
        package.mkdir(parents=True)
        (root / "open_webui/__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        with ZipFile(WHEEL) as wheel:
            source = wheel.read("open_webui/utils/plugin.py").decode("utf-8")
            tree = ast.parse(source)
            selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name in {"extract_frontmatter", "load_tool_module_by_id"}]
            loader = "from __future__ import annotations\nimport asyncio, types, sys, tempfile, os, re, logging\nENABLE_PLUGINS=True\nlog=logging.getLogger('trial')\ndef install_frontmatter_requirements(value):\n    assert not value\n"
            (package / "plugin.py").write_text(loader + "\n".join(ast.get_source_segment(source, node) for node in selected), encoding="utf-8")
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
            with patch.object(self.module, "WORKER_TIMEOUT_SECONDS", 0.8):
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


if __name__ == "__main__":
    unittest.main()
