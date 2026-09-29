"""Temporary Native authentication integration, using the pinned wheel source.

Account, credential, config, group, membership, JWT and permission code below is
loaded unchanged from Open WebUI. Only unrelated model transports, telemetry,
OAuth providers and app startup are supplied by the surrounding test fixture.
No live database, environment key, membership or company endpoint is read.
"""

from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
import hashlib
import importlib
import json
from pathlib import Path
import sys
import threading
import types
from typing import Any, Self, TypeVar
from zipfile import ZipFile
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
import httpx
from pydantic import BaseModel
import sqlalchemy
from sqlalchemy import types as sql_types
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from native_ui_fixture import MODELS, NativeUIHandler, NativeUIServer, chat_record


ROOT = Path(__file__).resolve().parents[1]
PERMISSIONS = {
    "workspace": {key: False for key in ("models", "tools", "knowledge", "prompts", "skills",
                                          "models_import", "tools_import")},
    "sharing": {"public": False, "public_models": False, "public_tools": False},
    "chat": {"controls": True, "file_upload": True, "delete": True, "edit": True,
             "temporary": True, "regenerate_response": True, "multiple_models": True},
    "features": {"api_keys": False, "notes": False, "channels": False},
    "settings": {"interface": True},
}


class NativeAuthFixture:
    """Real Native persistence and HTTP handlers, in one loopback test process."""

    def __init__(self, wheel, directory):
        self.wheel = Path(wheel)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.saved_modules = {key: value for key, value in sys.modules.items()
                              if key == "open_webui" or key.startswith("open_webui.")}
        self.sources = {}
        self.events = []
        self.engine = None
        self.workflow = None
        self.chats = {}
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=30)

    def stub(self, name, **values):
        module = types.ModuleType(name)
        module.__dict__.update(values)
        module.__path__ = []
        sys.modules[name] = module
        parent, _, child = name.rpartition(".")
        if parent in sys.modules:
            setattr(sys.modules[parent], child, module)
        return module

    def load(self, name, path=None):
        path = path or name.replace(".", "/") + ".py"
        source = self.members[path]
        module = self.stub(name)
        module.__file__ = str(self.wheel) + "!/" + path
        self.sources[path] = hashlib.sha256(source).hexdigest()
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module

    async def start(self):
        with ZipFile(self.wheel) as wheel:
            self.members = {name: wheel.read(name) for name in wheel.namelist() if name.endswith(".py")}
            static = self.directory / "static"
            static.mkdir(exist_ok=True)
            (static / "user.png").write_bytes(wheel.read("open_webui/frontend/static/user.png"))
        for name in tuple(sys.modules):
            if name == "open_webui" or name.startswith("open_webui."):
                del sys.modules[name]
        for name in ("open_webui", "open_webui.internal", "open_webui.models", "open_webui.routers", "open_webui.utils"):
            self.stub(name)
        database_url = f"sqlite:///{self.directory / 'webui.db'}"
        self.stub("open_webui.env", DATA_DIR=self.directory, DATABASE_URL=database_url,
                  DATABASE_ENABLE_SESSION_SHARING=True, DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL=0,
                  DEFAULT_GROUP_SHARE_PERMISSION=False, ENABLE_OTEL=False, ENABLE_PASSWORD_VALIDATION=False,
                  LICENSE_BLOB="", OFFLINE_MODE=True, PASSWORD_HASH_ALGORITHM="bcrypt",
                  PASSWORD_VALIDATION_HINT="", PASSWORD_VALIDATION_REGEX_PATTERN="", REDIS_KEY_PREFIX="fixture",
                  STATIC_DIR=static, TRUSTED_SIGNATURE_KEY=b"synthetic-fixture-only",
                  WEBUI_SECRET_KEY="synthetic-auth-fixture-key-never-live", pk="", WEBUI_AUTH=True,
                  WEBUI_AUTH_TRUSTED_EMAIL_HEADER=None, WEBUI_AUTH_TRUSTED_GROUPS_HEADER=None,
                  WEBUI_AUTH_TRUSTED_NAME_HEADER=None, WEBUI_AUTH_TRUSTED_ROLE_HEADER=None,
                  WEBUI_AUTH_COOKIE_SAME_SITE="lax", WEBUI_AUTH_COOKIE_SECURE=False,
                  WEBUI_AUTH_SIGNOUT_REDIRECT_URL="", ENABLE_INITIAL_ADMIN_SIGNUP=True,
                  ENABLE_OAUTH_TOKEN_EXCHANGE=False, OAUTH_TOKEN_EXCHANGE_RATE_LIMIT=None,
                  OAUTH_TOKEN_EXCHANGE_RATE_LIMIT_WINDOW=60, OAUTH_TOKEN_EXCHANGE_TRUSTED_CLIENT_IDS=[],
                  AIOHTTP_CLIENT_SESSION_SSL=True, ENABLE_PROFILE_IMAGE_URL_FORWARDING=False,
                  PROFILE_IMAGE_ALLOWED_MIME_TYPES=["image/png", "image/jpeg"],
                  PROFILE_IMAGE_MAX_DATA_URI_SIZE=1024 * 1024, CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE=1024,
                  ENABLE_PLUGINS=True, ENABLE_VALVE_ENCRYPTION=True)
        self.stub("open_webui.config", DEFAULT_USER_PERMISSIONS=PERMISSIONS, ENABLE_PASSWORD_AUTH=True,
                  OAUTH_PROVIDERS={}, CACHE_DIR=self.directory / "cache", DATA_DIR=self.directory,
                  BYPASS_ADMIN_ACCESS_CONTROL=False)
        self.stub("open_webui.utils.json_codec", JSONCodec=json)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.directory / 'webui.db'}")
        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, autoflush=False, expire_on_commit=False)
        self.Base = declarative_base()
        self.db = self.stub("open_webui.internal.db", Base=self.Base, AsyncSession=AsyncSession,
                            AsyncSessionLocal=self.sessions, asynccontextmanager=asynccontextmanager,
                            DATABASE_ENABLE_SESSION_SHARING=True, types=sql_types, JSONCodec=json,
                            _T=TypeVar("_T"), Dialect=Dialect, Any=Any, Self=Self)
        db_tree = ast.parse(self.members["open_webui/internal/db.py"])
        definitions = [node for node in db_tree.body
                       if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name in {"JSONField", "get_async_session", "get_async_db", "get_async_db_context"}]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), "native-db-session-definitions", "exec"), self.db.__dict__)
        self.load("open_webui.constants")
        self.load("open_webui.utils.misc")
        self.load("open_webui.utils.validate")
        self.stub("open_webui.models.files", FileMetadataResponse=BaseModel)
        self.config = self.load("open_webui.models.config").Config
        self.users = self.load("open_webui.models.users")
        self.groups = self.load("open_webui.models.groups")
        channel_module = self.stub("open_webui.models.channels", **{
            **{name: getattr(sqlalchemy, name) for name in ("Column", "Text", "Boolean", "JSON", "BigInteger")},
            "Base": self.Base})
        channel_nodes = [node for node in ast.parse(self.members["open_webui/models/channels.py"]).body
                         if isinstance(node, ast.ClassDef) and node.name == "ChannelMember"]
        exec(compile(ast.Module(body=channel_nodes, type_ignores=[]), "native-channel-member-definition", "exec"), channel_module.__dict__)
        self.auths = self.load("open_webui.models.auths")
        if "open_webui/ees_asset_guard.py" in self.members:
            self.load("open_webui.ees_asset_guard")
        self.acl = self.load("open_webui.models.access_grants")
        self.permissions = self.load("open_webui.utils.access_control", "open_webui/utils/access_control/__init__.py")
        self.auth = self.load("open_webui.utils.auth")
        self.load("open_webui.utils.groups")
        self.load("open_webui.utils.chat_variables")
        self.load("open_webui.utils.rate_limit")
        self.stub("open_webui.utils.redis", get_redis_client=lambda: None)

        class EventNames:
            def __getattr__(self, name):
                return name

        async def publish_event(*args, **kwargs):
            # Metadata only, like the callers; test passwords/tokens are never captured.
            self.events.append({key: value for key, value in kwargs.items() if key != "actor"})

        self.stub("open_webui.events", EVENTS=EventNames(), publish_event=publish_event)
        # Unrelated asset/export/usage endpoints are not used by these tests.
        for module, attribute in (("knowledge", "Knowledges"), ("models", "Models"), ("tools", "Tools"),
                                  ("oauth_sessions", "OAuthSessions"), ("chats", "Chats"), ("chat_messages", "ChatMessages")):
            self.stub("open_webui.models." + module, **{attribute: types.SimpleNamespace()})
        self.auth_router = self.load("open_webui.routers.auths")
        self.user_router = self.load("open_webui.routers.users")
        self.group_router = self.load("open_webui.routers.groups")
        async with self.engine.begin() as connection:
            await connection.run_sync(self.Base.metadata.create_all)
        self.config.configure(defaults={"ui.enable_signup": True, "ui.enable_login_form": True,
            "ui.default_user_role": "pending", "ui.default_group_id": "", "auth.jwt_expiry": "1h",
            "user.permissions": PERMISSIONS, "ui.default_interface_settings": {"models": ["fixture-model"],
            "showChangelog": False, "version": "0.11.3", "autoFollowUps": False},
            "auth.admin.show": False, "auth.admin.email": "", "oauth.enable": False,
            "users.enable_status": False})
        self.app = FastAPI()
        self.app.state.redis = None
        self.app.state.config = types.SimpleNamespace(USER_PERMISSIONS=PERMISSIONS)
        self.app.include_router(self.auth_router.router, prefix="/api/v1/auths")
        self.app.include_router(self.user_router.router, prefix="/api/v1/users")
        self.app.include_router(self.group_router.router, prefix="/api/v1/groups")
        # There is already an administrator before any representative signup.
        existing = await self.users.Users.get_user_by_email("administrator@example.test")
        if existing is None:
            existing = await self.auths.Auths.insert_new_auth(email="administrator@example.test",
                password=await self.auth.get_password_hash("Fixture-admin-only-42!"),
                name="합성 기존 관리자", role="admin")
        self.admin_id = existing.id
        async with self.sessions() as db:
            # Synthetic common model only: genuine Native ACL lookup below,
            # with the response transport deliberately deterministic.
            if not await self.acl.AccessGrants.has_access(existing.id, "model", "fixture-model", "read"):
                db.add(self.acl.AccessGrant(id=str(uuid4()), resource_type="model", resource_id="fixture-model",
                    principal_type="user", principal_id="*", permission="read", created_at=1))
                await db.commit()
        return self

    async def install_workflow(self):
        """Load the installed wheel's public workflow module and real API guard."""
        package = self.directory / "workflow-module"
        package.mkdir(exist_ok=True)
        with ZipFile(self.wheel) as wheel:
            names = [name for name in wheel.namelist()
                     if name.startswith("open_webui/ees_workflow") and name.endswith(".py")]
            names.extend(("open_webui/workflow_seed.json", "open_webui/workflow_policy.json"))
            for name in names:
                (package / Path(name).name).write_bytes(wheel.read(name))
        sys.modules["open_webui"].__path__.append(str(package))
        self.backend = importlib.import_module("open_webui.ees_workflow")

        async def user_lookup(user_id):
            return await self.users.Users.get_user_by_id(user_id)

        async def chat_lookup(chat_id):
            return self.chats.get(chat_id)

        self.workflow = self.backend.WorkflowService(self.directory / "ees-work.sqlite3",
            user_lookup, chat_lookup, group_lookup=self.groups.Groups.get_groups_by_member_id,
            group_list_lookup=lambda: self.groups.Groups.get_groups({}))
        self.backend._service = self.workflow
        self.backend.install(self.app, self.auth.get_verified_user)
        return self.workflow

    async def request(self, method, path, *, token=None, payload=None, headers=None, content=None):
        values = dict(headers or {})
        if token:
            values["authorization"] = "Bearer " + token
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://fixture") as client:
            return await client.request(method, path, headers=values, json=payload, content=content)

    async def signin(self, email="administrator@example.test", password="Fixture-admin-only-42!"):
        response = await self.request("POST", "/api/v1/auths/signin", payload={"email": email, "password": password})
        if response.status_code != 200:
            raise AssertionError(f"Native signin failed: {response.status_code} {response.text}")
        return response.json()

    async def set_signup(self, enabled, admin_token):
        current = await self.request("GET", "/api/v1/auths/admin/config", token=admin_token)
        settings = current.json()
        for name, field in self.auth_router.AdminConfig.model_fields.items():
            if name not in settings and field.is_required():
                settings[name] = False if field.annotation is bool else ""
        settings["ENABLE_SIGNUP"] = enabled
        return await self.request("POST", "/api/v1/auths/admin/config", token=admin_token, payload=settings)

    async def close_async(self):
        # Native auth schedules last-active writes outside the request task.
        # Drain this fixture's private loop before disposing its DB/closing it;
        # otherwise a successful API assertion can leave a pending SQL task.
        current = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task is not current]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=2)
            for task in pending:
                task.cancel()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2)
        if self.engine:
            await self.engine.dispose()

    def close(self):
        if self.loop.is_closed():
            return
        self.run(self.close_async())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()
        for name in tuple(sys.modules):
            if name == "open_webui" or name.startswith("open_webui."):
                del sys.modules[name]
        sys.modules.update(self.saved_modules)


class NativeAuthUIServer(NativeUIServer):
    """Actual frontend + actual Native auth API; model replies stay synthetic."""

    def __init__(self, wheel_path, fixture):
        super().__init__(wheel_path)
        self.RequestHandlerClass = NativeAuthUIHandler
        self.native = fixture
        self.chats = fixture.chats
        self.workflow = fixture.workflow
        # Optional transport barriers: the real authenticated handler has
        # already produced its result before a delayed response is released.
        self.authoring_read_gate = None
        self.authoring_reply_finished = threading.Event()

    def server_close(self):
        if self.authoring_read_gate:
            self.authoring_read_gate["release"].set()
        super().server_close()


class NativeAuthUIHandler(NativeUIHandler):
    def current_user(self):
        token = self.headers.get("authorization", "").removeprefix("Bearer ")
        if not token:
            cookies = SimpleCookie()
            cookies.load(self.headers.get("cookie", ""))
            token = cookies["token"].value if "token" in cookies else ""
        return self.server.native.run(self.server.native.auth.get_verified_user_by_token(token))

    def bridge(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith(("/api/v1/auths", "/api/v1/users", "/api/v1/groups", "/api/ees-work")):
            return False
        raw = self.rfile.read(int(self.headers.get("content-length", 0))) if self.command != "GET" else None
        response = self.server.native.run(self.server.native.request(self.command, self.path,
            headers={key: value for key, value in self.headers.items() if key.lower() not in {"host", "content-length"}},
            content=raw))
        self.server.requests.append((self.command, path))
        gate = self.server.authoring_read_gate
        held_response = False
        if gate and self.command == "GET" and path == "/api/ees-work/authoring" and response.status_code == 200:
            body = response.json()
            if body.get("actor_id") == gate["actor_id"] and (body.get("process") or {}).get("process_id") == gate["process_id"]:
                held_response = True
                gate["started"].set()
                if not gate["release"].wait(timeout=30):
                    self.server.errors.append("Authoring response barrier timed out")
        self.send_response(response.status_code)
        for key, value in response.headers.multi_items():
            if key.lower() not in {"content-length", "transfer-encoding", "connection"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        try:
            self.wfile.write(response.content)
        except (BrokenPipeError, ConnectionResetError):
            pass
        if held_response:
            gate["finished"].set()
        return True

    def do_GET(self):
        if self.bridge():
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/config":
            signup = self.server.native.run(self.server.native.config.get("ui.enable_signup"))
            return self.send_content({"status": True, "name": "EES Work", "version": "0.11.3",
                "default_locale": "ko-KR", "default_models": "fixture-model", "default_prompt_suggestions": [],
                "oauth": {"providers": {}}, "features": {"auth": True, "enable_websocket": False,
                    "enable_signup": signup, "enable_login_form": True, "enable_folders": True,
                    "enable_version_update_check": False}, "permissions": PERMISSIONS,
                "audio": {"tts": {"engine": "", "voice": ""}, "stt": {"engine": ""}},
                "file": {"max_size": 10, "max_count": 5, "image_compression": {"width": 1920, "height": 1080}},
                "ui": {"default_interface_settings": {}}, "code": {"engine": "pyodide"}})
        if path.startswith("/admin"):
            return self.send_content(self.server.wheel.read("open_webui/frontend/index.html"), "text/html")
        if path == "/api/models" or path.startswith("/api/v1/chats/"):
            user = self.current_user()
            if user is None:
                return self.send_content({"detail": "Native verified user required"}, status=401)
            if path == "/api/models":
                allowed = self.server.native.run(self.server.native.acl.AccessGrants.has_access(
                    user.id, "model", "fixture-model", "read"))
                return self.send_content({"data": MODELS if allowed else []})
            if path == "/api/v1/chats/":
                self.server.new_chat_ready.set()
                if int(parse_qs(urlsplit(self.path).query).get("page", ["1"])[0]) > 1:
                    return self.send_content([])
                return self.send_content([record for record in self.server.chats.values() if record["user_id"] == user.id])
            suffix = path.removeprefix("/api/v1/chats/")
            if suffix in self.server.chats:
                record = self.server.chats[suffix]
                if record["user_id"] != user.id:
                    return self.send_content({"detail": "Chat unavailable"}, status=403)
                return self.send_content(record)
        super().do_GET()

    def do_POST(self):
        if self.bridge():
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/chat/completions" or path.startswith("/api/v1/chats/"):
            user = self.current_user()
            if user is None:
                return self.send_content({"detail": "Native verified user required"}, status=401)
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            if path == "/api/chat/completions":
                if not self.server.native.run(self.server.native.acl.AccessGrants.has_access(
                        user.id, "model", body.get("model", ""), "read")):
                    return self.send_content({"detail": "Model unavailable"}, status=403)
                self.server.completions.append(body)
                if body.get("stream") is False and "user_message" not in body:
                    self.server.authoring_requests.append(body)
                    answer = self.server.authoring_answer
                    self.server.authoring_started.set()
                    if not self.server.authoring_hold.wait(timeout=30):
                        self.server.errors.append("Authoring reply barrier timed out")
                    result = self.send_content({"choices": [{"message": {"role": "assistant", "content": answer}}]})
                    self.server.authoring_reply_finished.set()
                    return result
                reply = dict(body)
                reply["chat_id"] = body.get("chat_id") or str(uuid4())
                record = self.server.chats.get(reply["chat_id"])
                if record is not None and record["user_id"] != user.id:
                    return self.send_content({"detail": "Chat unavailable"}, status=403)
                if record is None:
                    self.server.new_chat_ready.clear()
                    reply["fixture_new_chat"] = True
                    record = chat_record(reply["chat_id"])
                    record["user_id"] = user.id
                    record["chat"]["history"] = {"messages": {}, "currentId": None}
                    self.server.chats[reply["chat_id"]] = record
                self.send_content({"task_id": "fixture-task", "chat_id": reply["chat_id"]})
                threading.Thread(target=self.server.model_reply, args=(reply,), daemon=True).start()
                return
            if path == "/api/v1/chats/new":
                identifier = body.get("chat", {}).get("id") or str(uuid4())
                record = chat_record(identifier)
                record["user_id"] = user.id
                record["chat"] = body["chat"]
                self.server.chats[identifier] = record
                return self.send_content(record)
            identifier = path.removeprefix("/api/v1/chats/").split("/")[0]
            if identifier in self.server.chats:
                record = self.server.chats[identifier]
                if record["user_id"] != user.id:
                    return self.send_content({"detail": "Chat unavailable"}, status=403)
                record["chat"].update(body)
                return self.send_content(record)
            if path == "/api/v1/chats/read":
                return self.send_content(body)
            return self.send_content({"detail": "Chat unavailable"}, status=404)
        super().do_POST()

    def do_DELETE(self):
        if not self.bridge():
            self.send_content({"detail": "Fixture route unavailable"}, status=404)
