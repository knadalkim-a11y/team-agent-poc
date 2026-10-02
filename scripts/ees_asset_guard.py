"""Conditional native asset writes for the pinned Open WebUI program.

This module is installed as ``open_webui.ees_asset_guard``.  It neither owns
user assets nor changes the database schema.  The builder patches native
routes and table entry points to use the same guard before accepting requests.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import hmac
import inspect
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any, Awaitable, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AssetGuardError(RuntimeError):
    """A static, non-sensitive code suitable for operational diagnostics."""


class ProcessLock:
    """Kernel-owned lifetime lock; never remove or steal an existing lock."""

    def __init__(self, data_dir: Path, database_path: Path):
        self.fd: int | None = None
        data_dir = self._canonical(data_dir)
        database_path = self._canonical(database_path)
        if database_path.parent != data_dir or not data_dir.is_dir():
            raise AssetGuardError("ees_asset_guard_unsupported_database")
        if database_path.exists():
            info = database_path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise AssetGuardError("ees_asset_guard_unsafe_path")
        self.path = data_dir / "ees-assets.lock"

    @staticmethod
    def _canonical(path: Path) -> Path:
        path = Path(os.path.abspath(path))
        for component in (path, *path.parents):
            if component.is_symlink():
                raise AssetGuardError("ees_asset_guard_unsafe_path")
            # Windows junctions are reparse points, not always is_symlink().
            try:
                attrs = getattr(component.lstat(), "st_file_attributes", 0)
            except FileNotFoundError:
                continue
            if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise AssetGuardError("ees_asset_guard_unsafe_path")
        return path.resolve()

    def acquire(self) -> None:
        if self.fd is not None:
            raise AssetGuardError("ees_asset_guard_already_started")
        self._canonical(self.path)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            info = os.fstat(fd)
            path_info = self.path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
            ):
                raise AssetGuardError("ees_asset_guard_unsafe_path")
            if os.name == "nt":
                import msvcrt

                if info.st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            os.close(fd)
            if isinstance(exc, AssetGuardError):
                raise
            raise AssetGuardError("ees_asset_guard_database_in_use") from None
        self.fd = fd

    def release(self) -> None:
        fd, self.fd = self.fd, None
        if fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


async def _finish_despite_cancellation(task: asyncio.Task) -> Any:
    """Wait for actual cleanup, including repeated disconnect cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    return task.result()


class TaskGuard:
    """One task owns lock acquisition, DB work and cleanup as a single unit."""

    def __init__(self, process_lock: ProcessLock | None = None):
        self.lock = asyncio.Lock()
        self.owner: asyncio.Task | None = None
        self.tasks: set[asyncio.Task] = set()
        self.process_lock = process_lock
        self.key = secrets.token_bytes(32)
        self.loop = asyncio.get_running_loop()
        self.closing = False

    def owned(self) -> bool:
        return asyncio.current_task() is self.owner

    async def run(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        if asyncio.get_running_loop() is not self.loop:
            raise AssetGuardError("ees_asset_guard_event_loop_mismatch")
        if self.owned():
            return await operation()
        if self.closing:
            raise HTTPException(503, "conditional_write_unavailable")
        started = asyncio.Event()

        async def worker():
            async with self.lock:
                self.owner = asyncio.current_task()
                started.set()
                try:
                    return await operation()
                finally:
                    self.owner = None

        task = asyncio.create_task(worker())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A waiter may be discarded safely.  An executing DB operation
            # must finish before its lock/session can be released.
            if not started.is_set():
                task.cancel()
            try:
                await _finish_despite_cancellation(task)
            except BaseException:
                pass
            raise

    async def close(self) -> None:
        self.closing = True

        async def drain():
            if self.tasks:
                await asyncio.gather(*tuple(self.tasks), return_exceptions=True)

        drain_task = asyncio.create_task(drain())
        try:
            await _finish_despite_cancellation(drain_task)
        finally:
            if self.process_lock:
                self.process_lock.release()


_guard: TaskGuard | None = None


def _active_guard() -> TaskGuard:
    if _guard is None:
        raise HTTPException(503, "conditional_write_unavailable")
    return _guard


def guard_operation(function):
    """Protect an audited caller before its first read; preserve its session."""
    @functools.wraps(function)
    async def protected(*args, **kwargs):
        return await _active_guard().run(lambda: function(*args, **kwargs))

    protected.__ees_asset_guard__ = True
    protected.__signature__ = inspect.signature(function, eval_str=True)
    return protected


def guard_table_method(function=None, *, asset_types_only=False):
    """Guard native writers and normalization reads, including direct callers.

    An independent caller must not carry an older transaction into the lock.
    Reusing such a session or discarding it silently would lose caller work.
    """
    if function is None:
        return lambda target: guard_table_method(target, asset_types_only=asset_types_only)
    signature = inspect.signature(function, eval_str=True)

    @functools.wraps(function)
    async def protected(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if asset_types_only and bound.arguments.get("resource_type") not in {"tool", "model"}:
            return await function(*args, **kwargs)
        guard = _active_guard()
        if guard.owned():
            return await function(*args, **kwargs)
        supplied = bound.arguments.get("db")
        if supplied is not None and supplied.in_transaction():
            raise AssetGuardError("ees_asset_guard_stale_session")

        async def operation():
            from open_webui.internal.db import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                bound.arguments["db"] = session
                return await function(*bound.args, **bound.kwargs)

        return await guard.run(operation)

    protected.__ees_asset_guard__ = True
    protected.__signature__ = signature
    return protected


class AssetGuardRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def guarded(request: Request):
            return await _active_guard().run(lambda: original(request))

        return guarded

    async def handle(self, scope, receive, send) -> None:
        # Keep FastAPI's dependency exit stacks and response cleanup inside
        # the same owning task, in addition to locking before Depends runs.
        original = super().handle
        await _active_guard().run(lambda: original(scope, receive, send))


TABLE_METHODS = {
    "tools": (
        "insert_new_tool", "update_tool_by_id", "update_tool_valves_by_id", "delete_tool_by_id",
    ),
    "models": (
        "insert_new_model", "update_model_by_id", "update_model_updated_at_by_id",
        "toggle_model_by_id", "sync_models", "delete_model_by_id", "delete_all_models",
        "get_all_models", "get_models", "get_base_models", "search_models",
        "get_model_by_id", "get_models_by_ids",
    ),
    "access_grants": (
        "grant_access", "revoke_access", "revoke_all_access", "set_access_control", "set_access_grants",
    ),
}

CALLER_HOOKS = {
    "open_webui.utils.plugin": ("load_tool_module_by_id", "get_tool_module_from_cache"),
    "open_webui.routers.knowledge": ("delete_knowledge_by_id",),
    "open_webui.utils.models": ("check_model_access",),
    "open_webui.routers.users": ("get_user_preview",),
    "open_webui.routers.ollama": ("get_filtered_models",),
    "open_webui.routers.openai": ("get_filtered_models",),
    "open_webui.routers.groups": ("preview_group_access",),
    "open_webui.utils.access_control": ("has_base_model_access",),
}


def verify_asset_guard_installation() -> None:
    from importlib import import_module

    from open_webui.models import access_grants, models, tools
    from open_webui.routers import models as model_routes, tools as tool_routes
    from open_webui.utils import tools as tool_loading, middleware

    tables = {"tools": tools.ToolsTable, "models": models.ModelsTable, "access_grants": access_grants.AccessGrantsTable}
    for name, table in tables.items():
        for method in TABLE_METHODS[name]:
            if not getattr(getattr(table, method, None), "__ees_asset_guard__", False):
                raise AssetGuardError("ees_asset_guard_incomplete_installation")
    for native in (model_routes, tool_routes):
        if native.router.route_class is not AssetGuardRoute or not native.router.routes:
            raise AssetGuardError("ees_asset_guard_incomplete_installation")
        if any(not isinstance(route, AssetGuardRoute) for route in native.router.routes):
            raise AssetGuardError("ees_asset_guard_incomplete_installation")
    if getattr(tool_routes, "EES_ASSET_CACHE_COMMIT_ORDER", None) != 1:
        raise AssetGuardError("ees_asset_guard_incomplete_installation")
    if getattr(tool_loading, "EES_ASSET_LOCAL_TOOL_GUARD", None) != 1:
        raise AssetGuardError("ees_asset_guard_incomplete_installation")
    if getattr(middleware, "EES_WORK_NATIVE_CHAT_CONTEXT", None) != 1:
        raise AssetGuardError("ees_asset_guard_incomplete_installation")
    for module_name, methods in CALLER_HOOKS.items():
        module = import_module(module_name)
        for method in methods:
            if not getattr(getattr(module, method, None), "__ees_asset_guard__", False):
                raise AssetGuardError("ees_asset_guard_incomplete_installation")


def _single_process_configuration() -> None:
    try:
        for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
            if int(os.environ.get(name, "1")) != 1:
                raise ValueError
        for name in ("UVICORN_RELOAD", "WEBUI_RELOAD"):
            if os.environ.get(name, "").lower() not in {"", "0", "false", "no", "off"}:
                raise ValueError
        for index, argument in enumerate(sys.argv[1:], start=1):
            if argument == "--reload" or argument.startswith("--reload="):
                raise ValueError
            if argument == "--workers" and int(sys.argv[index + 1]) != 1:
                raise ValueError
            if argument.startswith("--workers=") and int(argument.split("=", 1)[1]) != 1:
                raise ValueError
    except (ValueError, IndexError):
        raise AssetGuardError("ees_asset_guard_unsupported_process") from None


async def start_asset_guard(app) -> None:
    global _guard
    if _guard is not None:
        raise AssetGuardError("ees_asset_guard_already_started")
    verify_asset_guard_installation()
    from open_webui.env import DATA_DIR, DATABASE_URL
    from sqlalchemy.engine import make_url

    _single_process_configuration()
    try:
        url = make_url(DATABASE_URL)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:" or url.query:
            raise ValueError
    except (ValueError, TypeError):
        raise AssetGuardError("ees_asset_guard_unsupported_database") from None
    process_lock = ProcessLock(Path(DATA_DIR), Path(url.database))
    process_lock.acquire()
    try:
        _guard = TaskGuard(process_lock)
        app.state.ees_asset_guard = _guard
    except BaseException:
        process_lock.release()
        raise


async def stop_asset_guard(app) -> None:
    global _guard
    current = getattr(app.state, "ees_asset_guard", None)
    if current is None:
        return
    try:
        await current.close()
    finally:
        if _guard is current:
            _guard = None
        app.state.ees_asset_guard = None


class AssetTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tool", "model", "valves"]
    id: str = Field(min_length=1, max_length=1024)


class AssetApply(AssetTarget):
    operation: Literal["create", "update"]
    expected_token: str = Field(min_length=64, max_length=64)
    payload: dict


def _dump(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _grants(value):
    # IDs and creation timestamps are implementation records.  Ordering or
    # recreating the same grants does not alter the supported access state.
    return sorted({
        (grant.get("principal_type"), grant.get("principal_id"), grant.get("permission"))
        for grant in (value or [])
    }, key=lambda item: json.dumps(item, sort_keys=True))


def _state(kind: str, raw: dict | None, valves=None):
    if raw is None:
        return None
    fields = ("id", "user_id", "name", "base_model_id", "meta", "params", "is_active") if kind == "model" else (
        "id", "user_id", "name", "content", "meta",
    )
    result = {key: raw.get(key) for key in fields}
    result["access_grants"] = _grants(raw.get("access_grants"))
    if kind != "model":
        result["valves"] = valves
    return result


def _token(user_id: str, target: AssetTarget, state) -> str:
    payload = json.dumps(
        [1, user_id, target.kind, target.id, state is not None, state],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hmac.new(_active_guard().key, payload, hashlib.sha256).hexdigest()


def _validate_target(target: AssetTarget) -> None:
    if target.kind != "model" and (not target.id.isidentifier() or target.id != target.id.lower()):
        raise HTTPException(422, "invalid_asset_target")


async def _current_admin(user, session):
    from open_webui.models.users import Users

    current = await Users.get_user_by_id(user.id, db=session)
    if current is None or current.role != "admin":
        raise HTTPException(403, "asset_access_denied")
    return current


async def _snapshot(target: AssetTarget, user, session) -> dict:
    from open_webui.models.models import Models
    from open_webui.models.tools import Tools
    from open_webui.routers import models, tools

    _validate_target(target)
    if target.kind == "model":
        raw = await Models.get_model_by_id(target.id, db=session)
        visible = await models.get_model_by_id(target.id, user=user, db=session) if raw else None
        valves = None
    else:
        raw = await Tools.get_tool_by_id(target.id, db=session)
        visible = await tools.get_tools_by_id(target.id, user=user, db=session) if raw else None
        valves = await tools.get_tools_valves_by_id(target.id, user=user, db=session) if raw else None
    asset = _dump(visible)
    if raw is not None and (not asset or not asset.get("write_access")):
        raise HTTPException(403, "asset_access_denied")
    if raw is not None and target.kind != "model" and not isinstance(asset.get("content"), str):
        raise HTTPException(403, "asset_access_denied")
    result = {
        "asset": valves if target.kind == "valves" else asset,
        "exists": raw is not None,
        "token": _token(user.id, target, _state(target.kind, _dump(raw), valves)),
    }
    if target.kind == "valves":
        result["parent"] = asset
    return result


async def _apply(request: Request, form: AssetApply, user, session, *, restoring_retired=False) -> dict:
    if form.id in RETIRED_ASSETS.get(form.kind, ()) and not restoring_retired:
        raise HTTPException(410, "demo_registration_retired")
    before = await _snapshot(form, user, session)
    if not hmac.compare_digest(before["token"], form.expected_token):
        raise HTTPException(409, "concurrent_edit")
    if (form.operation == "create") == before["exists"]:
        raise HTTPException(409, "concurrent_edit")
    if form.kind == "valves" and form.operation != "update":
        raise HTTPException(422, "invalid_asset_operation")
    if form.kind != "valves" and form.payload.get("id") != form.id:
        raise HTTPException(422, "invalid_asset_target")

    from open_webui.models.models import ModelForm
    from open_webui.models.tools import ToolForm
    from open_webui.routers import models, tools

    try:
        if form.kind == "tool":
            native_form = ToolForm.model_validate(form.payload)
            if form.operation == "create":
                result = await tools.create_new_tools(request, native_form, user=user, db=session)
            else:
                result = await tools.update_tools_by_id(request, form.id, native_form, user=user, db=session)
        elif form.kind == "model":
            native_form = ModelForm.model_validate(form.payload)
            native = models.create_new_model if form.operation == "create" else models.update_model_by_id
            result = await native(request, native_form, user=user, db=session)
        else:
            result = await tools.update_tools_valves_by_id(request, form.id, form.payload, user=user, db=session)
    except ValidationError:
        raise HTTPException(422, "invalid_asset_payload") from None
    except HTTPException as exc:
        # Native errors can contain source text or valve values.  The local
        # journal needs a status, never those values in a remote error body.
        raise HTTPException(exc.status_code, "native_asset_rejected") from None
    if result is None:
        raise HTTPException(500, "asset_write_incomplete")

    # Native methods have their own commit policy; read the final state using
    # a new session, including when session sharing is disabled upstream.
    from open_webui.internal.db import AsyncSessionLocal

    async with AsyncSessionLocal() as current_session:
        current_user = await _current_admin(user, current_session)
        after = await _snapshot(form, current_user, current_session)
        if not after["exists"]:
            raise HTTPException(500, "asset_write_incomplete")
        if form.kind == "tool":
            after["valves_snapshot"] = await _snapshot(
                AssetTarget(kind="valves", id=form.id), current_user, current_session,
            )
        return after



# Explicit asset retirement uses the same Native ACL/serialization lock as normal writes.
# Nothing in this API is called automatically by installation, upgrade or startup.
RETIRED_ASSETS = {
    "tool": frozenset({"ees_specialists", "ees_demo_data"}),
    "model": frozenset({"ees_demo_ems", "ees_demo_apc", "ees_demo_fdc"}),
}


class AssetRetirement(AssetTarget):
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssetRetire(AssetRetirement):
    expected_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")


class AssetRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")
    backup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _retirement_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _retirement_path(request_id):
    from open_webui.env import DATA_DIR

    directory = ProcessLock._canonical(Path(DATA_DIR)) / "ees-asset-retirement"
    ProcessLock._canonical(directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (request_id + ".json")
    ProcessLock._canonical(path)
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise HTTPException(409, "unsafe_retirement_backup")
    return path


def _save_retirement(path, receipt):
    import tempfile

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                prefix=".retirement-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        ProcessLock._canonical(path)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_retirement(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise HTTPException(409, "invalid_retirement_backup")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["backup_sha256"] != _retirement_hash(value["backup"]):
            raise ValueError
        return value
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, "invalid_retirement_backup") from None


async def _retirement_preview(form, user, session):
    from open_webui.models.models import Models
    from open_webui.routers import tools

    if form.id not in RETIRED_ASSETS.get(form.kind, ()):
        raise HTTPException(422, "asset_not_in_retirement_inventory")
    before = await _snapshot(form, user, session)
    asset = before["asset"]
    valves = await tools.get_tools_valves_by_id(form.id, user=user, db=session) if asset and form.kind == "tool" else None
    state = _state(form.kind, asset, valves)
    digest = _retirement_hash(state)
    references = []
    for raw in await Models.get_all_models(db=session):
        model = _dump(raw)
        bound = (form.id in ((model.get("meta") or {}).get("toolIds") or [])
                 if form.kind == "tool" else model.get("base_model_id") == form.id)
        if bound:
            # Counts are enough; don't expose another user's private model name/content.
            references.append(model["id"])
    reasons = []
    if asset is None:
        reasons.append("absent")
    else:
        if digest != form.baseline_sha256:
            reasons.append("modified_or_unverified_asset")
        if asset.get("user_id") != user.id:
            reasons.append("owner_required_for_lossless_restore")
        marker = (asset.get("meta") or {}).get("ees_demo_pack") if form.kind == "model" else (
            (asset.get("meta") or {}).get("manifest") or {}).get("ees_demo_pack")
        if marker != "ees-demo-v1":
            reasons.append("management_marker_missing")
        if references:
            reasons.append("active_model_references")
    public = {"kind": form.kind, "id": form.id, "exists": before["exists"],
              "current_sha256": digest, "expected_token": before["token"],
              "eligible": not reasons, "blocked_reasons": reasons,
              "model_reference_count": len(references),
              "history": "Chats, workflow runs, attempts and attachments are preserved. Retired tools may no longer execute historical work.",
              "restore": "Explicit asset restore requires this private backup; program Restore does not restore assets or data."}
    return public, {"kind": form.kind, "id": form.id, "asset": asset, "valves": valves}


def _retirement_public(receipt):
    return {key: receipt[key] for key in ("request_id", "kind", "id", "status", "backup_sha256")}


async def _retire_asset(request, form, user, session):
    path = _retirement_path(form.request_id)
    fingerprint = _retirement_hash({"actor": user.id, "kind": form.kind, "id": form.id,
                                    "baseline_sha256": form.baseline_sha256})
    if path.exists():
        receipt = _read_retirement(path)
        if receipt.get("fingerprint") != fingerprint:
            raise HTTPException(409, "retirement_request_conflict")
        if receipt["status"] != "retired":
            raise HTTPException(409, "retirement_requires_reconciliation")
        current = await _snapshot(form, user, session)
        if current["exists"]:
            raise HTTPException(409, "retirement_target_recreated")
        return _retirement_public(receipt)
    preview, backup = await _retirement_preview(form, user, session)
    if not hmac.compare_digest(preview["expected_token"], form.expected_token):
        raise HTTPException(409, "concurrent_edit")
    if not preview["eligible"]:
        raise HTTPException(409, "retirement_preview_blocked")
    receipt = {"schema": 1, "request_id": form.request_id, "kind": form.kind,
               "id": form.id, "actor": user.id, "fingerprint": fingerprint,
               "backup": backup, "backup_sha256": _retirement_hash(backup), "status": "pending"}
    # Backup and intent reach disk before Native deletion; a crash stays uncertain.
    _save_retirement(path, receipt)
    from open_webui.routers import models, tools
    if form.kind == "model":
        result = await models.delete_model_by_id(request, models.ModelIdForm(id=form.id), user=user, db=session)
    else:
        result = await tools.delete_tools_by_id(request, form.id, user=user, db=session)
    if result is not True:
        raise HTTPException(500, "retirement_delete_incomplete")
    receipt["status"] = "retired"
    _save_retirement(path, receipt)
    return _retirement_public(receipt)


async def _restore_asset(request, form, user, session):
    path = _retirement_path(form.request_id)
    if not path.exists():
        raise HTTPException(404, "retirement_backup_missing")
    receipt = _read_retirement(path)
    if receipt.get("actor") != user.id or not hmac.compare_digest(receipt["backup_sha256"], form.backup_sha256):
        raise HTTPException(403, "retirement_backup_access_denied")
    backup = receipt["backup"]
    target = AssetTarget(kind=backup["kind"], id=backup["id"])
    before = await _snapshot(target, user, session)
    if receipt["status"] == "restored":
        from open_webui.routers import tools
        valves = await tools.get_tools_valves_by_id(target.id, user=user, db=session) if before["exists"] and target.kind == "tool" else None
        if _state(target.kind, before["asset"], valves) != _state(target.kind, backup["asset"], backup["valves"]):
            raise HTTPException(409, "restored_asset_changed")
        return _retirement_public(receipt)
    if receipt["status"] != "retired" or before["exists"]:
        raise HTTPException(409, "retirement_restore_conflict")
    raw = backup["asset"]
    fields = ("id", "name", "base_model_id", "meta", "params", "is_active", "access_grants") if target.kind == "model" else (
        "id", "name", "content", "meta", "access_grants")
    payload = {key: raw.get(key) for key in fields}
    receipt["status"] = "restore_pending"
    _save_retirement(path, receipt)
    after = await _apply(request, AssetApply(kind=target.kind, id=target.id, operation="create",
        expected_token=before["token"], payload=payload), user, session, restoring_retired=True)
    if target.kind == "tool" and backup["valves"] is not None:
        await _apply(request, AssetApply(kind="valves", id=target.id, operation="update",
            expected_token=after["valves_snapshot"]["token"], payload=backup["valves"]), user, session, restoring_retired=True)
    receipt["status"] = "restored"
    _save_retirement(path, receipt)
    return _retirement_public(receipt)


WORK_TOOL_ID = "ees_workflow"
WORK_TOOL_FUNCTIONS = frozenset({"ees_workflow_view", "ees_workflow_propose", "ees_workflow_display"})


def work_tool_source():
    """Exact program-owned source, never a DB row or a generated Tool body."""
    import ast

    source = Path(__file__).with_name("ees_workflow_tool.py")
    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 128 * 1024:
            raise ValueError
        raw = source.read_bytes()
        content = raw.decode("utf-8")
        tree = ast.parse(content)
        tool = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Tools")
        public = {node.name for node in tool.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")}
        if public != WORK_TOOL_FUNCTIONS:
            raise ValueError
        return content, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, ValueError, SyntaxError, StopIteration):
        raise HTTPException(503, "work_tool_source_unavailable") from None


class WorkToolSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: Literal["register_readonly_work_tool"]
    access_grants: list[dict] = Field(default_factory=list, max_length=100)


async def _work_tool_status(user, session):
    source, digest = work_tool_source()
    snapshot = await _snapshot(AssetTarget(kind="tool", id=WORK_TOOL_ID), user, session)
    asset = snapshot["asset"]
    state = "missing" if not snapshot["exists"] else "ready" if asset.get("content") == source else "blocked_existing"
    return {"id": WORK_TOOL_ID, "state": state, "source_sha256": digest,
            "expected_token": snapshot["token"], "functions": sorted(WORK_TOOL_FUNCTIONS),
            "reason": "existing_source_differs_export_and_review_native_update" if state == "blocked_existing" else None,
            "changed": False}, snapshot


async def _setup_work_tool(request, form, user, session):
    status, before = await _work_tool_status(user, session)
    if form.source_sha256 != status["source_sha256"]:
        raise HTTPException(409, "work_tool_program_changed")
    if not hmac.compare_digest(form.expected_token, status["expected_token"]):
        raise HTTPException(409, "concurrent_edit")
    if status["state"] == "blocked_existing":
        raise HTTPException(409, "work_tool_existing_source_requires_review")
    if status["state"] == "ready":
        # Repeating setup does not alter ownership, ACL or settings.
        return status
    for grant in form.access_grants:
        if (set(grant) != {"principal_type", "principal_id", "permission"}
                or grant["principal_type"] not in {"user", "group"}
                or not isinstance(grant["principal_id"], str) or not 0 < len(grant["principal_id"]) <= 200
                or grant["permission"] != "read"):
            raise HTTPException(422, "work_tool_read_grants_required")
    source, source_digest = work_tool_source()
    if not hmac.compare_digest(source_digest, form.source_sha256):
        raise HTTPException(409, "work_tool_program_changed")
    after = await _apply(request, AssetApply(kind="tool", id=WORK_TOOL_ID, operation="create",
        expected_token=before["token"], payload={"id": WORK_TOOL_ID, "name": "EES Work",
            "content": source, "meta": {"description": "허용된 업무 조회와 초안 제안. 저장·게시·실행·확정은 업무 화면에서 수행합니다.",
                                        "ees_work_source_sha256": status["source_sha256"]},
            "access_grants": form.access_grants}), user, session)
    if after["asset"].get("content") != source:
        raise HTTPException(500, "work_tool_registration_unconfirmed")
    return {**status, "state": "ready", "expected_token": after["token"], "changed": True}

def create_asset_router() -> APIRouter:
    # Import lazily: native table modules import our decorators while the
    # native auth module itself imports those tables.
    from open_webui.internal.db import AsyncSessionLocal
    from open_webui.utils.auth import get_admin_user

    router = APIRouter(route_class=AssetGuardRoute)

    @router.get("/capabilities")
    async def capabilities(user=Depends(get_admin_user)):
        guard = _active_guard()
        async with AsyncSessionLocal() as session:
            await _current_admin(user, session)
        if guard.closing:
            raise HTTPException(503, "conditional_write_unavailable")
        return {"version": 1, "conditional_apply": True, "process_scope": "single", "retirement": 1, "work_tool_setup": 1}

    @router.get("/work-tool/status")
    async def work_tool_status(user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            status, _ = await _work_tool_status(current_user, session)
            return status

    @router.post("/work-tool/setup")
    async def work_tool_setup(request: Request, form: WorkToolSetup, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            return await _setup_work_tool(request, form, current_user, session)

    @router.post("/snapshot")
    async def snapshot(form: AssetTarget, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            return await _snapshot(form, current_user, session)

    @router.post("/apply")
    async def apply(request: Request, form: AssetApply, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            return await _apply(request, form, current_user, session)

    @router.post("/retirement/preview")
    async def retirement_preview(form: AssetRetirement, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            preview, _ = await _retirement_preview(form, current_user, session)
            return preview

    @router.post("/retirement/apply")
    async def retirement_apply(request: Request, form: AssetRetire, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            return await _retire_asset(request, form, current_user, session)

    @router.post("/retirement/restore")
    async def retirement_restore(request: Request, form: AssetRestore, user=Depends(get_admin_user)):
        async with AsyncSessionLocal() as session:
            current_user = await _current_admin(user, session)
            return await _restore_asset(request, form, current_user, session)

    return router
