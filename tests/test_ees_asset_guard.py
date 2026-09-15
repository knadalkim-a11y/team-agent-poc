"""Concurrency/lifetime tests; real pinned native routes are tested separately."""

import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "ees_asset_guard.py"
spec = importlib.util.spec_from_file_location("ees_asset_guard_test_subject", SOURCE)
guard_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard_module
spec.loader.exec_module(guard_module)


class TaskGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.guard = guard_module.TaskGuard()
        self.previous = guard_module._guard
        guard_module._guard = self.guard

    async def asyncTearDown(self):
        await self.guard.close()
        guard_module._guard = self.previous

    async def test_nested_calls_reenter_same_task_and_other_task_waits(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        trace = []

        async def outer():
            trace.append("start")
            owner = asyncio.current_task()

            async def nested():
                self.assertIs(asyncio.current_task(), owner)
                trace.append("nested")

            await self.guard.run(nested)
            entered.set()
            await finish.wait()
            trace.append("finish")

        first = asyncio.create_task(self.guard.run(outer))
        await entered.wait()

        async def competing():
            trace.append("other")

        second = asyncio.create_task(self.guard.run(competing))
        await asyncio.sleep(0)
        self.assertEqual(trace, ["start", "nested"])
        finish.set()
        await asyncio.gather(first, second)
        self.assertEqual(trace, ["start", "nested", "finish", "other"])

    async def test_cancelling_waiter_does_not_write(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        writes = []

        async def hold():
            entered.set()
            await finish.wait()

        async def write():
            writes.append("unexpected")

        first = asyncio.create_task(self.guard.run(hold))
        await entered.wait()
        waiter = asyncio.create_task(self.guard.run(write))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        finish.set()
        await first
        self.assertEqual(writes, [])

    async def test_cancelled_writer_keeps_lock_until_commit_and_cleanup(self):
        entered, commit = asyncio.Event(), asyncio.Event()
        trace = []

        async def write():
            entered.set()
            try:
                await commit.wait()
                trace.append("commit")
            finally:
                trace.append("session-close")

        writer = asyncio.create_task(self.guard.run(write))
        await entered.wait()
        writer.cancel()
        await asyncio.sleep(0)
        writer.cancel()  # A second server disconnect must not shorten cleanup.

        async def next_write():
            trace.append("next")

        next_writer = asyncio.create_task(self.guard.run(next_write))
        await asyncio.sleep(0)
        self.assertEqual(trace, [])
        self.assertFalse(writer.done())
        commit.set()
        with self.assertRaises(asyncio.CancelledError):
            await writer
        await next_writer
        self.assertEqual(trace, ["commit", "session-close", "next"])

    async def test_failed_write_releases_lock_after_cleanup(self):
        trace = []

        async def fail():
            try:
                raise ValueError("synthetic database failure")
            finally:
                trace.append("close")

        with self.assertRaises(ValueError):
            await self.guard.run(fail)

        async def next_write():
            trace.append("next")

        await self.guard.run(next_write)
        self.assertEqual(trace, ["close", "next"])

    async def test_child_task_cannot_inherit_owner(self):
        async def outer():
            async def child():
                return self.guard.owned()

            self.assertFalse(await asyncio.create_task(child()))

        await self.guard.run(outer)

    async def test_shutdown_drains_before_process_unlock(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        trace = []
        self.guard.process_lock = types.SimpleNamespace(release=lambda: trace.append("unlock"))

        async def write():
            entered.set()
            await finish.wait()
            trace.append("commit")

        writer = asyncio.create_task(self.guard.run(write))
        await entered.wait()
        closing = asyncio.create_task(self.guard.close())
        await asyncio.sleep(0)
        self.assertFalse(closing.done())
        with self.assertRaises(guard_module.HTTPException) as error:
            await self.guard.run(write)
        self.assertEqual(error.exception.status_code, 503)
        finish.set()
        await asyncio.gather(writer, closing)
        self.assertEqual(trace, ["commit", "unlock"])
        self.guard.process_lock = None

    async def test_token_covers_all_supported_fields_and_parent_valves(self):
        target = guard_module.AssetTarget(kind="tool", id="synthetic_tool")
        tool = {
            "id": target.id, "user_id": "admin", "name": "Example", "content": "class Tools: pass",
            "meta": {"description": "baseline", "manifest": {}, "has_user_valves": False},
            "access_grants": [{"id": "a", "created_at": 1, "principal_type": "user", "principal_id": "*", "permission": "read"}],
        }

        def token(raw=tool, valves=None, user="admin", token_target=target):
            return guard_module._token(user, token_target, guard_module._state(token_target.kind, raw, valves))

        baseline = token()
        self.assertEqual(baseline, token())
        self.assertNotEqual(baseline, token(user="another-admin"))
        self.assertNotEqual(baseline, token(valves={"endpoint": "synthetic"}))
        self.assertNotEqual(baseline, token(token_target=guard_module.AssetTarget(kind="valves", id=target.id)))
        for key, replacement in {
            "content": "class Tools: changed = True", "name": "Changed", "user_id": "other",
            "meta": {"description": "someone edited here"}, "access_grants": [],
        }.items():
            self.assertNotEqual(baseline, token({**tool, key: replacement}), key)
        recreated = json.loads(json.dumps(tool))
        recreated["access_grants"][0].update(id="different-row", created_at=99)
        recreated.update(updated_at=99, user_valves={"private": "never-in-token"})
        self.assertEqual(baseline, token(recreated))
        old_key = self.guard.key
        self.guard.key = b"a different process key"
        self.assertNotEqual(baseline, token())
        self.guard.key = old_key

    async def test_model_token_covers_params_active_and_dynamic_meta(self):
        target = guard_module.AssetTarget(kind="model", id="synthetic-model")
        model = {"id": target.id, "user_id": "admin", "params": {"system": "draft"}, "meta": {"custom": "kept"}, "is_active": True}
        baseline = guard_module._token("admin", target, guard_module._state("model", model))
        for key, value in {"params": {"system": "changed"}, "meta": {"custom": "changed"}, "is_active": False}.items():
            state = guard_module._state("model", {**model, key: value})
            self.assertNotEqual(baseline, guard_module._token("admin", target, state))

    async def test_table_entry_uses_fresh_session_and_rejects_live_transaction(self):
        opened = []

        class Session:
            def __init__(self, in_transaction=False):
                self.transaction = in_transaction

            def in_transaction(self):
                return self.transaction

            async def __aenter__(self):
                opened.append(self)
                return self

            async def __aexit__(self, *args):
                self.closed = True

        db_module = types.ModuleType("open_webui.internal.db")
        db_module.AsyncSessionLocal = Session
        with patch.dict(sys.modules, {"open_webui.internal.db": db_module}):
            @guard_module.guard_table_method
            async def write(*, db=None):
                self.assertTrue(self.guard.owned())
                return db

            supplied = Session()
            actual = await write(db=supplied)
            self.assertIsNot(actual, supplied)
            self.assertTrue(actual.closed)
            self.assertFalse(hasattr(supplied, "closed"))
            with self.assertRaisesRegex(guard_module.AssetGuardError, "stale_session"):
                await write(db=Session(True))

            async def nested():
                self.assertIs(await write(db=supplied), supplied)

            await self.guard.run(nested)
            self.assertEqual(len(opened), 1)

    async def test_non_asset_grants_do_not_require_asset_guard(self):
        @guard_module.guard_table_method(asset_types_only=True)
        async def grant(resource_type, *, db=None):
            return resource_type

        guard_module._guard = None
        self.assertEqual(await grant("knowledge"), "knowledge")
        with self.assertRaises(guard_module.HTTPException):
            await grant("model")
        guard_module._guard = self.guard


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_dependencies_execute_and_close_inside_owner(self):
        from fastapi import Depends, FastAPI
        import httpx

        active = guard_module.TaskGuard()
        previous, guard_module._guard = guard_module._guard, active
        trace = []
        app = FastAPI()
        router = guard_module.APIRouter(route_class=guard_module.AssetGuardRoute)

        async def db_dependency():
            self.assertTrue(active.owned())
            trace.append("open")
            try:
                yield "session"
            finally:
                self.assertTrue(active.owned())
                trace.append("close")

        @router.get("/test")
        async def endpoint(db=Depends(db_dependency)):
            self.assertTrue(active.owned())
            trace.append("read-write")
            return {"ok": True}

        app.include_router(router)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic.test") as client:
                response = await client.get("/test")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(trace, ["open", "read-write", "close"])
        finally:
            await active.close()
            guard_module._guard = previous


class ProcessLockTests(unittest.TestCase):
    def test_unsupported_worker_and_reload_settings_fail_closed(self):
        safe = {"WEB_CONCURRENCY": "1", "UVICORN_WORKERS": "1", "UVICORN_RELOAD": "false", "WEBUI_RELOAD": "0"}
        with patch.dict(os.environ, safe), patch.object(sys, "argv", ["open-webui", "serve"]):
            guard_module._single_process_configuration()
            for name, value in {"WEB_CONCURRENCY": "2", "UVICORN_WORKERS": "3", "UVICORN_RELOAD": "true"}.items():
                with patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(guard_module.AssetGuardError, "unsupported_process"):
                        guard_module._single_process_configuration()
            for argv in (["uvicorn", "--reload"], ["uvicorn", "--workers", "2"], ["uvicorn", "--workers=3"]):
                with patch.object(sys, "argv", argv):
                    with self.assertRaisesRegex(guard_module.AssetGuardError, "unsupported_process"):
                        guard_module._single_process_configuration()

    def test_second_process_refused_and_release_allows_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            first = guard_module.ProcessLock(data, data / "webui.db")
            first.acquire()
            code = """import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('lock_subject', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
data = pathlib.Path(sys.argv[2])
lock = module.ProcessLock(data, data / 'webui.db')
try:
    lock.acquire()
except module.AssetGuardError as error:
    print(str(error))
    sys.exit(23)
lock.release()
print('released')
"""
            command = [sys.executable, "-c", code, str(SOURCE), str(data)]
            try:
                blocked = subprocess.run(command, capture_output=True, text=True, timeout=20)
                self.assertEqual(blocked.returncode, 23, blocked.stderr)
                self.assertEqual(blocked.stdout.strip(), "ees_asset_guard_database_in_use")
            finally:
                first.release()
            restarted = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(restarted.returncode, 0, restarted.stderr)
            self.assertEqual(restarted.stdout.strip(), "released")
            self.assertTrue((data / "ees-assets.lock").is_file())

    def test_rejects_database_outside_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with self.assertRaisesRegex(guard_module.AssetGuardError, "unsupported_database"):
                guard_module.ProcessLock(data, data.parent / "webui.db")

    def test_rejects_symbolic_lock_file(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            target = data / "another-file"
            target.write_text("untouched")
            try:
                (data / "ees-assets.lock").symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("symbolic links unavailable on this platform")
            lock = guard_module.ProcessLock(data, data / "webui.db")
            with self.assertRaisesRegex(guard_module.AssetGuardError, "unsafe_path"):
                lock.acquire()
            self.assertEqual(target.read_text(), "untouched")

    def test_rejects_hard_linked_database(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            original = data / "webui.db"
            original.write_bytes(b"synthetic file")
            try:
                os.link(original, data / "same-db.db")
            except (NotImplementedError, OSError):
                self.skipTest("hard links unavailable on this platform")
            with self.assertRaisesRegex(guard_module.AssetGuardError, "unsafe_path"):
                guard_module.ProcessLock(data, original)


if __name__ == "__main__":
    unittest.main()
