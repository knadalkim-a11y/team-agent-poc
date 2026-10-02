"""Isolated, real-wheel asset persistence fixture (never imports the WebUI app).

Only service/config/auth surroundings are supplied here. Asset table classes,
native routers, ACL checks, plugin loading, JSON fields and session-context
functions execute the pinned wheel source after the production builder patch.
The database is a new temporary SQLite file, never a user's DATA_DIR.
"""

from __future__ import annotations

import ast
import asyncio
import copy
from contextlib import asynccontextmanager
import hashlib
import importlib.util
import inspect
import json
import logging
from pathlib import Path
import re
import sys
import tempfile
import types
from functools import partial, update_wrapper
from typing import Any, Awaitable, Callable, Self, TypeVar, get_args, get_type_hints
from zipfile import ZipFile

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
import httpx
from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy import Column, String, types as sql_types
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


ROOT = Path(__file__).resolve().parents[1]
TOOL_CONTENT = """from pydantic import BaseModel
class Tools:
    class Valves(BaseModel):
        label: str = 'initial'
    def echo(self, value: str) -> str:
        return value
"""


class NativeAssetFixture:
    def __init__(self, wheel: str | Path, *, sharing: bool = True):
        self.wheel = Path(wheel)
        self.sharing = sharing
        self.temporary = tempfile.TemporaryDirectory(prefix="ees-native-assets-")
        self.directory = Path(self.temporary.name)
        self.saved_modules = {
            key: value for key, value in sys.modules.items()
            if key == "open_webui" or key.startswith("open_webui.")
        }
        self.users = {}
        self.events = []
        self.loaded_sources = {}
        self.engine = None
        self.client = None
        self.started = False

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
        module.__package__ = name.rpartition(".")[0]
        module.__file__ = f"{self.wheel}!/{path}"
        self.loaded_sources[path] = hashlib.sha256(source).hexdigest()
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module

    def load_caller_definitions(self):
        """Compile audited callers without importing their unrelated services.

        These are real patched function definitions, including the production
        guard decorator, not dummy functions carrying a verification marker.
        Their unrelated model-serving/vector-store surroundings are not an
        integration claim of this asset persistence fixture.
        """
        for name, methods in self.guard.CALLER_HOOKS.items():
            existing = sys.modules.get(name)
            if existing is not None and all(hasattr(existing, method) for method in methods):
                continue
            path = name.replace(".", "/") + ".py"
            source = self.members[path]
            tree = ast.parse(source)
            definitions = [
                node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name in methods
            ]
            if {node.name for node in definitions} != set(methods):
                raise AssertionError(f"Missing native caller definitions: {name}")
            module = existing or self.stub(name)
            module.__dict__.update({
                "router": APIRouter(), "Depends": Depends, "Request": Request,
                "AsyncSession": AsyncSession, "get_async_session": self.db.get_async_session,
                "get_admin_user": self.auth.get_admin_user,
                "get_verified_user": self.auth.get_verified_user,
                "guard_table_method": self.guard.guard_table_method,
                "guard_operation": self.guard.guard_operation,
                "Models": self.models.Models, "Tools": self.tools.Tools,
                "AccessGrants": self.acl.AccessGrants,
                "Users": sys.modules["open_webui.models.users"].Users,
                "Groups": sys.modules["open_webui.models.groups"].Groups,
                "has_access": sys.modules["open_webui.utils.access_control"].has_access,
                "has_base_model_access": sys.modules["open_webui.utils.access_control"].has_base_model_access,
            })
            module.__file__ = f"{self.wheel}!/{path}#audited-definitions"
            self.loaded_sources[path] = hashlib.sha256(source).hexdigest()
            exec(compile(ast.Module(body=definitions, type_ignores=[]), module.__file__, "exec"), module.__dict__)

    def load_tool_binding(self):
        """Execute the local native binding path; remote providers stay unused."""
        path = "open_webui/utils/tools.py"
        tree = ast.parse(self.members[path])
        definitions = [
            node for node in tree.body
            if (
                isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and (node.name in {"get_tools", "get_async_tool_function_and_apply_extra_params", "parse_description", "parse_docstring", "clean_properties", "get_functions_from_tool", "convert_function_to_pydantic_model", "clean_openai_tool_schema", "get_tool_specs"} or node.name.startswith("_ees_"))
            ) or (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id.startswith("EES_") for target in node.targets)
            )
        ]
        module = sys.modules["open_webui.utils.tools"]
        module.__dict__.update({
            "Request": Request, "UserModel": self.UserModel,
            "ENABLE_PLUGINS": True, "BYPASS_ADMIN_ACCESS_CONTROL": False,
            "Groups": sys.modules["open_webui.models.groups"].Groups,
            "Tools": self.tools.Tools, "AccessGrants": self.acl.AccessGrants,
            "get_tools_cache": self.plugin.get_tools_cache,
            "get_tool_contents_cache": self.plugin.get_tool_contents_cache,
            "load_tool_module_by_id": self.plugin.load_tool_module_by_id,
            "guard_operation": self.guard.guard_operation,
            "log": logging.getLogger("ees_native_fixture.binding"),
            "inspect": inspect, "get_type_hints": get_type_hints, "get_args": get_args,
            "re": re, "partial": partial, "update_wrapper": update_wrapper,
            "Callable": Callable, "Awaitable": Awaitable, "Any": Any,
            "BaseModel": BaseModel, "Field": Field, "create_model": create_model, "copy": copy,
            "convert_pydantic_model_to_openai_function_spec": self.schema_adapter,
        })
        module.__file__ = f"{self.wheel}!/{path}#binding-definitions"
        self.loaded_sources[path] = hashlib.sha256(self.members[path]).hexdigest()
        exec(compile(ast.Module(body=definitions, type_ignores=[]), module.__file__, "exec"), module.__dict__)
        self.binding = module

    @staticmethod
    def schema_adapter(model):
        """Dependency-light schema adapter; Native introspection above is real.

        This persistence fixture does not execute LangChain's schema converter.
        The full product Native chat gate verifies its complete emitted specs.
        """
        schema = model.model_json_schema()
        name = schema.pop("title")
        description = schema.pop("description", "")
        return {"name": name, "description": description, "parameters": schema}

    def load_chat_installation_marker(self):
        path = "open_webui/utils/middleware.py"
        definitions = [node for node in ast.parse(self.members[path]).body
                       if isinstance(node, ast.Assign) and any(
                           isinstance(target, ast.Name) and target.id == "EES_WORK_NATIVE_CHAT_CONTEXT"
                           for target in node.targets)]
        if len(definitions) != 1:
            raise AssertionError("Missing production middleware installation marker")
        module = self.stub("open_webui.utils.middleware")
        module.__file__ = f"{self.wheel}!/{path}#installation-marker-only"
        exec(compile(ast.Module(body=definitions, type_ignores=[]), module.__file__, "exec"), module.__dict__)

    async def start(self):
        spec = importlib.util.spec_from_file_location(
            "ees_native_fixture_builder", ROOT / "scripts/build_ees_webui.py"
        )
        self.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)
        actual_hash = hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        if actual_hash != self.builder.SOURCE_SHA256:
            raise AssertionError("Native integration requires the unchanged pinned wheel")
        with ZipFile(self.wheel) as source:
            replacements = self.builder.prepare_replacements(source, self.builder.ASSET_DIR)
            additions = self.builder.prepare_additions(source, self.builder.UI_DIR)
            self.members = {
                name: replacements.get(name, source.read(name))
                for name in source.namelist() if name.endswith(".py")
            }
            self.members.update({name: value for name, value in additions.items() if name.endswith(".py")})
        if "open_webui/ees_asset_guard.py" not in self.members:
            raise AssertionError("Production wheel additions must include the asset guard")

        for name in tuple(sys.modules):
            if name == "open_webui" or name.startswith("open_webui."):
                del sys.modules[name]
        for name in ("open_webui", "open_webui.internal", "open_webui.models", "open_webui.routers", "open_webui.utils"):
            self.stub(name)

        database_url = f"sqlite:///{self.directory / 'webui.db'}"
        self.stub(
            "open_webui.env", DATA_DIR=self.directory, DATABASE_URL=database_url,
            DATABASE_ENABLE_SESSION_SHARING=self.sharing, ENABLE_PLUGINS=True,
            ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=False, OFFLINE_MODE=True,
            PIP_OPTIONS=[], PIP_PACKAGE_INDEX_OPTIONS=[],
            ENABLE_VALVE_ENCRYPTION=True, WEBUI_SECRET_KEY="synthetic-fixture-only",
            AIOHTTP_CLIENT_SESSION_SSL=True, AIOHTTP_CLIENT_TIMEOUT=10,
            ENABLE_PROFILE_IMAGE_URL_FORWARDING=False,
            PROFILE_IMAGE_ALLOWED_MIME_TYPES=["image/png"],
        )
        permissions = {
            "workspace": {"tools": True, "tools_import": True, "models": True},
            "sharing": {"public_tools": True, "public_models": True, "public": True},
        }
        self.stub(
            "open_webui.config", BYPASS_ADMIN_ACCESS_CONTROL=False,
            DEFAULT_USER_PERMISSIONS=permissions, CACHE_DIR=self.directory / "cache",
            DATA_DIR=self.directory,
        )
        self.stub("open_webui.utils.json_codec", JSONCodec=json)

        class UserModel(BaseModel):
            model_config = ConfigDict(from_attributes=True)
            id: str
            role: str = "user"
            name: str = "Synthetic user"
            email: str = "fixture@example.invalid"
            settings: dict = Field(default_factory=dict)

        self.UserModel = UserModel
        self.users["admin"] = UserModel(id="admin", role="admin")
        self.users["owner"] = UserModel(id="owner")
        self.users["reader"] = UserModel(id="reader")
        self.users["outsider"] = UserModel(id="outsider")

        async def get_user_by_id(user_id, db=None):
            return self.users.get(user_id)

        async def get_user_by_token(token, **kwargs):
            return self.users.get(token)

        async def get_users_by_user_ids(user_ids, db=None):
            return [self.users[user_id] for user_id in user_ids if user_id in self.users]

        async def get_verified_user(request: Request):
            user_id = request.headers.get("authorization", "").removeprefix("Bearer ")
            user = self.users.get(user_id)
            if user is None:
                raise HTTPException(401, "unauthorized")
            return user

        async def get_admin_user(request: Request):
            user = await get_verified_user(request)
            if user.role != "admin":
                raise HTTPException(403, "admin_required")
            return user

        self.auth = self.stub(
            "open_webui.utils.auth", get_verified_user=get_verified_user,
            get_admin_user=get_admin_user, get_verified_user_by_token=get_user_by_token,
        )
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.directory / 'webui.db'}")
        self.sessions = async_sessionmaker(
            self.engine, class_=AsyncSession, autoflush=False, expire_on_commit=False,
        )
        self.Base = declarative_base()
        self.db = self.stub(
            "open_webui.internal.db", Base=self.Base,
            AsyncSession=AsyncSession, AsyncSessionLocal=self.sessions,
            asynccontextmanager=asynccontextmanager,
            DATABASE_ENABLE_SESSION_SHARING=self.sharing, DATABASE_URL=database_url,
            SQLALCHEMY_DATABASE_URL=database_url, async_engine=self.engine,
            types=sql_types, JSONCodec=json, _T=TypeVar("_T"), Dialect=Dialect,
            Any=Any, Self=Self,
        )
        # Execute these definitions unchanged, without app startup/migrations.
        db_tree = ast.parse(self.members["open_webui/internal/db.py"])
        selected = [
            node for node in db_tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"JSONField", "get_async_session", "get_async_db", "get_async_db_context"}
        ]
        exec(compile(ast.Module(body=selected, type_ignores=[]), "pinned-native-db-definitions", "exec"), self.db.__dict__)

        class User(self.Base):
            __tablename__ = "user"
            id = Column(String, primary_key=True)
            name = Column(String)
            email = Column(String)

        self.stub(
            "open_webui.models.users", User=User, UserModel=UserModel,
            UserResponse=UserModel, Users=types.SimpleNamespace(
                get_user_by_id=get_user_by_id, get_users_by_user_ids=get_users_by_user_ids,
            ),
        )

        async def groups_by_user(user_id, db=None):
            return []

        self.stub("open_webui.models.groups", Groups=types.SimpleNamespace(get_groups_by_member_id=groups_by_user))

        async def config_get(key, *args, **kwargs):
            return json.loads(json.dumps(permissions)) if key == "user.permissions" else None

        self.stub("open_webui.models.config", Config=types.SimpleNamespace(get=config_get))
        self.stub("open_webui.models.oauth_sessions", OAuthSessions=object())
        self.stub("open_webui.models.functions", FunctionModel=BaseModel, Functions=object())
        self.stub("open_webui.utils.misc", json_text_variants=lambda value: [json.dumps(value)])
        self.stub("open_webui.utils.validate", validate_profile_image_url=lambda value: value)
        self.load("open_webui.utils.valves")

        class ErrorMessages:
            def __getattr__(self, name):
                return name.lower()

            def DEFAULT(self, *args):
                return "native_operation_failed"

        self.stub("open_webui.constants", ERROR_MESSAGES=ErrorMessages())

        async def publish_event(*args, **kwargs):
            self.events.append(kwargs)

        self.stub("open_webui.events", EVENTS=ErrorMessages(), publish_event=publish_event)
        self.guard = self.load("open_webui.ees_asset_guard")
        # Materialize the exact shipped common Tool source beside the guard,
        # as in the installed wheel. This fixture otherwise compiles ZIP bytes.
        (self.directory / "ees_workflow_tool.py").write_bytes(self.members["open_webui/ees_workflow_tool.py"])
        self.guard.__file__ = str(self.directory / "ees_asset_guard.py")
        self.acl = self.load("open_webui.models.access_grants")
        self.tools = self.load("open_webui.models.tools")
        self.models = self.load("open_webui.models.models")
        self.plugin = self.load("open_webui.utils.plugin")
        self.load("open_webui.utils.access_control", "open_webui/utils/access_control/__init__.py")

        async def file_access(*args, **kwargs):
            return False

        async def get_all_models(*args, **kwargs):
            return []

        self.stub("open_webui.utils.access_control.files", has_access_to_file=file_access)
        self.stub("open_webui.utils.models", get_all_models=get_all_models)
        self.stub("open_webui.utils.chat_variables", get_chat_variables_schema=lambda value: None)
        # Actual pinned Native function discovery/Pydantic introspection, with
        # the explicitly scoped schema adapter above (no model/provider IO).
        self.stub("open_webui.utils.tools", get_tool_servers=get_all_models)
        self.load_tool_binding()
        self.load_chat_installation_marker()
        # Local get_tools now calls the real common Work source/ACL guard for
        # the reserved ID; ordinary tools must continue through it unchanged.
        for name in ("ees_workflow_contract", "ees_workflow_definition", "ees_workflow_authoring", "ees_workflow_native"):
            member = "open_webui/" + name + ".py"
            target = self.directory / (name + ".py")
            target.write_bytes(self.members[member])
            self.load("open_webui." + name).__file__ = str(target)
        # The exact emitted definition reads policy relative to its module.
        (self.directory / "workflow_policy.json").write_bytes(additions["open_webui/workflow_policy.json"])
        self.tool_router = self.load("open_webui.routers.tools")
        self.model_router = self.load("open_webui.routers.models")
        self.load_caller_definitions()

        async with self.engine.begin() as connection:
            await connection.run_sync(self.Base.metadata.create_all)
        self.app = FastAPI()
        self.app.state.TOOLS = {}
        self.app.state.TOOL_CONTENTS = {}
        self.app.state.config = types.SimpleNamespace(USER_PERMISSIONS=permissions)
        self.app.include_router(self.tool_router.router, prefix="/api/v1/tools")
        self.app.include_router(self.model_router.router, prefix="/api/v1/models")
        self.app.include_router(self.guard.create_asset_router(), prefix="/api/v1/ees/assets")
        await self.guard.start_asset_guard(self.app)
        self.started = True
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://fixture")
        return self

    async def close(self):
        if self.client:
            await self.client.aclose()
        if self.started:
            await self.guard.stop_asset_guard(self.app)
        if self.engine:
            await self.engine.dispose()
        for name in tuple(sys.modules):
            if name == "open_webui" or name.startswith("open_webui.") or name.startswith("tool_fixture_"):
                del sys.modules[name]
        sys.modules.update(self.saved_modules)
        self.temporary.cleanup()

    async def request(self, method, path, *, user="admin", payload=None):
        return await self.client.request(
            method, path, headers={"authorization": f"Bearer {user}"}, json=payload,
        )

    async def create_tool(self, identifier="fixture_tool", owner="admin"):
        return await self.request("POST", "/api/v1/tools/create", user=owner, payload={
            "id": identifier, "name": "Synthetic tool", "content": TOOL_CONTENT,
            "meta": {"description": "initial"}, "access_grants": [],
        })

    async def create_model(self, identifier="fixture_model", owner="admin"):
        return await self.request("POST", "/api/v1/models/create", user=owner, payload={
            "id": identifier, "name": "Synthetic model", "base_model_id": "upstream",
            "params": {"system": "initial"}, "meta": {"description": "initial"},
            "access_grants": [],
        })
