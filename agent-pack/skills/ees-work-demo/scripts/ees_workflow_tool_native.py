"""Native settings identities and bounded authoring-trial process dispatch.

Native remains the only personal-token store. The identity is permanently inert;
draft and active business code are never registered as Native tool functions.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
from uuid import uuid4

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_native import _safe, environment_fingerprint

WORKER_TIMEOUT_SECONDS = 30
MAX_WORKER_INPUT_BYTES = 1024 * 1024
MAX_WORKER_RESULT_BYTES = 2 * 1024 * 1024
AUTHORED_ENVIRONMENT_FILES = (
    "ees_workflow_tool_native.py", "ees_workflow_tool_worker.py",
    "ees_workflow_tool_lifecycle.py", "ees_workflow_tool_draft_check.py", "ees_asset_guard.py",
)
IDENTITY_CONTENT = '''from pydantic import BaseModel, Field
class Tools:
    class Valves(BaseModel):
        pass
    class UserValves(BaseModel):
        PAT: str = Field(default="", description="현재 로그인 계정의 서비스 토큰", json_schema_extra={"input": {"type": "password"}})
'''


def _value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _fail(code, message="연결 설정의 현재 권한과 상태를 확인해 주세요."):
    raise WorkflowError(code, message)


def authored_environment_fingerprint():
    # A deployment may keep Native's version unchanged while changing authored
    # execution or validation. Read deployed bytes on every observation so an
    # existing trial never approves a changed worker, even in this process.
    directory = Path(__file__).resolve().parent
    try:
        from open_webui import ees_asset_guard
        modules = {name: hashlib.sha256((Path(ees_asset_guard.__file__) if name == "ees_asset_guard.py"
                                        else directory / name).read_bytes()).hexdigest()
                   for name in AUTHORED_ENVIRONMENT_FILES}
    except (ImportError, OSError, AttributeError, TypeError):
        _fail("tool_trial_environment_unavailable", "실행 환경을 확인할 수 없습니다. 설치 상태를 확인해 주세요.")
    return _hash({"authored_version": 1, "native": environment_fingerprint(), "modules": modules})


class AuthoredNative:
    def __init__(self, service):
        self.service = service
        with service._db(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_native_identities(tool_id TEXT PRIMARY KEY,native_id TEXT UNIQUE NOT NULL,owner_id TEXT NOT NULL,nonce TEXT NOT NULL,groups_json TEXT NOT NULL,state TEXT NOT NULL)")

    async def _admin(self, user):
        actor = await self.service._user(user)
        if _value(actor, "role") != "admin":
            _fail("admin_required", "관리자만 도구 연결과 시험을 설정할 수 있습니다.")
        return actor

    @staticmethod
    def _encryption():
        from open_webui import env
        from open_webui.utils import valves
        if not env.ENABLE_VALVE_ENCRYPTION or not env.WEBUI_SECRET_KEY or not valves.ENABLE_VALVE_ENCRYPTION:
            _fail("encryption_required", "개인 설정 암호화를 확인해 주세요.")
        return valves

    def _registry(self, native_id):
        with self.service._db() as db:
            row = db.execute("SELECT * FROM work_tool_native_identities WHERE native_id=?", (native_id,)).fetchone()
        if not row:
            _fail("tool_connection_identity_unavailable")
        return dict(row)

    @staticmethod
    def _meta(registry):
        return {"description": "작성 도구의 계정별 연결 설정 전용입니다.", "has_user_valves": True,
                "manifest": {"ees_authored_settings": {"version": 1, "tool_id": registry["tool_id"], "nonce": registry["nonce"]}}}

    @staticmethod
    def _grant_values(rows):
        return sorted((_value(row, "principal_type"), _value(row, "principal_id"), _value(row, "permission")) for row in rows)

    async def _identity(self, actor, registry, db):
        from sqlalchemy import select
        from open_webui.models.tools import Tool
        from open_webui.models.access_grants import AccessGrant, AccessGrants
        from open_webui.models.groups import Groups
        from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
        from open_webui.env import ENABLE_PLUGINS
        if not ENABLE_PLUGINS:
            _fail("native_plugins_disabled")
        row = (await db.execute(select(Tool).where(Tool.id == registry["native_id"]).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if row is None:
            _fail("tool_connection_identity_unavailable")
        grants = (await db.execute(select(AccessGrant).where(AccessGrant.resource_type == "tool", AccessGrant.resource_id == registry["native_id"]).with_for_update())).scalars().all()
        actual = self._grant_values(grants)
        expected = [("group", group, "read") for group in sorted(json.loads(registry["groups_json"]))]
        if (row.user_id != registry["owner_id"] or row.name != "EES 작성 도구 설정 " + registry["tool_id"]
                or row.content != IDENTITY_CONTENT or row.specs != [] or row.meta != self._meta(registry)
                or row.valves not in (None, {}) or actual != expected):
            _fail("tool_connection_identity_changed", "기존 연결용 도구가 변경되었습니다. 자동으로 덮어쓰지 않습니다.")
        if not (BYPASS_ADMIN_ACCESS_CONTROL and _value(actor, "role") == "admin") and row.user_id != _value(actor, "id"):
            groups = [_value(group, "id") for group in await Groups.get_groups_by_member_id(_value(actor, "id"))]
            if not await AccessGrants.has_access(user_id=_value(actor, "id"), resource_type="tool", resource_id=row.id,
                                                permission="read", user_group_ids=groups, db=db):
                _fail("native_access_denied")
        return _hash({"id": row.id, "owner": row.user_id, "content": row.content, "meta": row.meta, "groups": actual})

    async def _credentials(self, actor, native_id, db):
        from sqlalchemy import select
        from open_webui.models.users import User
        valves = self._encryption()
        row = (await db.execute(select(User.id, User.role, User.settings).where(User.id == _value(actor, "id")))).first()
        if row is None or row.role != "admin":
            _fail("admin_required")
        settings = row.settings
        if settings is None:
            settings = {}
        if not isinstance(settings, dict) or not isinstance(settings.get("tools", {}), dict) or not isinstance(settings.get("tools", {}).get("valves", {}), dict):
            _fail("native_settings_invalid")
        sealed = settings.get("tools", {}).get("valves", {}).get(native_id)
        personal = {}
        if sealed is not None:
            if not isinstance(sealed, str) or not sealed:
                _fail("tool_connection_credentials_unavailable")
            personal = valves.decrypt_valves(sealed)
            if not isinstance(personal, dict) or not isinstance(personal.get("PAT"), str):
                _fail("tool_connection_credentials_unavailable")
        return settings, personal, _hash({"native_id": native_id, "actor_id": row.id, "sealed": sealed}), row.settings

    async def _read(self, user, native_id):
        from open_webui.models.tools import get_async_db_context
        actor = await self._admin(user)
        registry = self._registry(native_id)
        async with get_async_db_context() as db:
            # Observe credentials after the final directory/role await. The
            # same final User SELECT also checks the current administrator role.
            actor = await self._admin(actor)
            identity = await self._identity(actor, registry, db)
            _, personal, stamp, _ = await self._credentials(actor, native_id, db)
        return actor, personal, {"native_id": native_id, "token_set": bool(personal.get("PAT")),
                                 "credential_stamp": stamp, "identity_stamp": identity, "environment": authored_environment_fingerprint(),
                                 "groups": sorted(json.loads(registry["groups_json"]))}

    async def inspect(self, user, native_id):
        return (await self._read(user, native_id))[2]

    async def save_connection(self, user, tool_id, native_id, token):
        from sqlalchemy import JSON, or_, select, update
        from sqlalchemy.exc import IntegrityError, OperationalError
        from open_webui.models.tools import Tool, get_async_db_context
        from open_webui.models.users import User
        actor = await self._admin(user)
        valves = self._encryption()
        if not isinstance(tool_id, str) or not re.fullmatch(r"draft-[a-f0-9]{32}", tool_id):
            _fail("tool_draft_invalid")
        if token is None:
            token = ""
        if not isinstance(token, str) or len(token) > 16384 or any(ord(char) < 32 for char in token):
            _fail("tool_connection_token_invalid")
        with self.service._db(write=True) as db:
            row = db.execute("SELECT * FROM work_tool_native_identities WHERE tool_id=?", (tool_id,)).fetchone()
            if row:
                registry = dict(row)
                if native_id not in (None, "", registry["native_id"]):
                    _fail("tool_connection_identity_changed")
            else:
                if native_id:
                    _fail("tool_connection_identity_unavailable")
                registry = {"tool_id": tool_id, "native_id": "ees-authored-" + tool_id[6:], "owner_id": _value(actor, "id"),
                            "nonce": uuid4().hex, "groups_json": "[]", "state": "creating"}
                db.execute("INSERT INTO work_tool_native_identities VALUES(:tool_id,:native_id,:owner_id,:nonce,:groups_json,:state)", registry)
        async with get_async_db_context() as db:
            existing = (await db.execute(select(Tool.id).where(Tool.id == registry["native_id"]))).first()
            if existing is None:
                if registry["state"] != "creating":
                    _fail("tool_connection_identity_unavailable")
                actor = await self._admin(actor)
                now = int(time.time())
                db.add(Tool(id=registry["native_id"], user_id=registry["owner_id"], name="EES 작성 도구 설정 " + tool_id,
                            content=IDENTITY_CONTENT, specs=[], meta=self._meta(registry), valves=None, created_at=now, updated_at=now))
                try:
                    await db.flush()
                except (IntegrityError, OperationalError):
                    _fail("tool_connection_conflict")
            await self._identity(actor, registry, db)
            settings, personal, _, original_settings = await self._credentials(actor, registry["native_id"], db)
            if token:
                new_personal = {**personal, "PAT": token}
                sealed = valves.encrypt_valves(new_personal)
                if not isinstance(sealed, str) or valves.decrypt_valves(sealed) != new_personal:
                    _fail("tool_connection_credentials_unavailable")
                modified = deepcopy(settings)
                modified.setdefault("tools", {}).setdefault("valves", {})[registry["native_id"]] = sealed
                # Never overwrite a different tool's concurrent settings edit.
                # This is the existing Native UserValves storage and encryption,
                # with an explicit full-settings compare-and-swap added here.
                expected = or_(User.settings.is_(None), User.settings == JSON.NULL) if original_settings is None else User.settings == original_settings
                try:
                    result = await db.execute(update(User).where(User.id == _value(actor, "id"), User.role == "admin",
                        expected).values(settings=modified))
                except (IntegrityError, OperationalError):
                    _fail("tool_connection_conflict")
                if result.rowcount != 1:
                    _fail("tool_connection_conflict", "개인 설정이 변경되었습니다. 입력을 유지하고 다시 저장해 주세요.")
            await self._identity(actor, registry, db)
            await self._admin(actor)
            await db.commit()
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_tool_native_identities SET state='ready' WHERE native_id=? AND nonce=?", (registry["native_id"], registry["nonce"]))
        return await self.inspect(actor, registry["native_id"])

    async def set_groups(self, user, native_id, groups, expected_stamp):
        from sqlalchemy import delete, select
        from open_webui.models.tools import get_async_db_context
        from open_webui.models.access_grants import AccessGrant
        from open_webui.models.groups import Group
        actor = await self._admin(user)
        if not isinstance(groups, list) or any(not isinstance(group, str) or not group for group in groups) or len(set(groups)) != len(groups):
            _fail("tool_draft_invalid")
        groups = sorted(groups)
        registry = self._registry(native_id)
        async with get_async_db_context() as db:
            if groups and set((await db.execute(select(Group.id).where(Group.id.in_(groups)))).scalars()) != set(groups):
                _fail("tool_draft_groups_invalid")
            stamp = await self._identity(actor, registry, db)
            if stamp != expected_stamp:
                _fail("tool_connection_conflict")
            await self._admin(actor)
            await db.execute(delete(AccessGrant).where(AccessGrant.resource_type == "tool", AccessGrant.resource_id == native_id))
            for group in groups:
                db.add(AccessGrant(id=str(uuid4()), resource_type="tool", resource_id=native_id,
                                   principal_type="group", principal_id=group, permission="read", created_at=int(time.time())))
            await db.flush()
            await self._identity(actor, {**registry, "groups_json": _json(groups)}, db)
            await self._admin(actor)
            await db.commit()
        with self.service._db(write=True) as db:
            updated = db.execute("UPDATE work_tool_native_identities SET groups_json=? WHERE native_id=? AND groups_json=?", (_json(groups), native_id, registry["groups_json"]))
            if updated.rowcount != 1:
                _fail("tool_connection_conflict")
        return await self.inspect(actor, native_id)

    async def redact(self, user, native_id, value):
        _, personal, _ = await self._read(user, native_id)
        return _safe(value, (personal.get("PAT", ""),))

    async def run(self, user, native_id, code, function, base_url, inputs, expected_metadata):
        actor, personal, metadata = await self._read(user, native_id)
        if metadata != expected_metadata:
            _fail("tool_trial_snapshot_changed")
        if not metadata["token_set"]:
            _fail("native_personal_connection_required")
        payload = {"native_id": native_id, "worker_id": "authored_trial_" + uuid4().hex, "code": code, "function": function,
                   "base_url": base_url, "inputs": inputs, "token": personal["PAT"],
                   "actor": {key: _value(actor, key, "") for key in ("id", "name", "email", "role")}}
        packed = _json(payload).encode("utf-8")
        if len(packed) > MAX_WORKER_INPUT_BYTES:
            _fail("tool_trial_input_too_large")
        started = time.monotonic()
        process = None
        temporary = tempfile.TemporaryDirectory(prefix="ees-tool-trial-")
        try:
            process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("ees_workflow_tool_worker.py")),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=os.name != "nt", env={**os.environ, "TMPDIR": temporary.name, "TMP": temporary.name, "TEMP": temporary.name})
            async def exchange():
                process.stdin.write(packed)
                await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while True:
                    chunk = await process.stdout.read(min(65536, MAX_WORKER_RESULT_BYTES + 1 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_WORKER_RESULT_BYTES:
                        return {"status": "failed", "error_code": "tool_trial_result_too_large", "raw_result": None}
                await process.wait()
                if process.returncode != 0:
                    return {"status": "unknown", "error_code": "tool_trial_worker_failed", "raw_result": None}
                return json.loads(output)
            result = await asyncio.wait_for(exchange(), timeout=WORKER_TIMEOUT_SECONDS)
            if not isinstance(result, dict) or result.get("status") not in {"succeeded", "failed", "unknown"}:
                raise ValueError("worker protocol")
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            result = {"status": "unknown", "error_code": "tool_trial_timeout", "raw_result": None}
        except Exception:
            result = {"status": "unknown", "error_code": "tool_trial_worker_failed", "raw_result": None}
        finally:
            if process is not None and process.returncode is None:
                try:
                    if os.name != "nt":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            temporary.cleanup()
        await self._admin(actor)
        latest = await self.inspect(actor, native_id)
        if latest != metadata:
            return {"status": "unknown", "error_code": "tool_trial_snapshot_changed", "raw_result": None,
                    "duration_ms": int((time.monotonic() - started) * 1000)}
        return {"status": result["status"], "raw_result": _safe(result.get("raw_result"), (personal["PAT"],)),
                **({"error_code": result["error_code"]} if result.get("error_code") else {}),
                "duration_ms": int((time.monotonic() - started) * 1000)}
