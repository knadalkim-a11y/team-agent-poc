"""Real pinned Native Users/Groups/Tools/ACL/Valves/loader over temporary SQLite.

Accounts, HTTP responses and model transport are synthetic. Account/settings,
group membership, encrypted valve persistence, ACL, bindings and plugin source
are real wheel code. No sign-in/session claim is made by this fixture.
"""
import ast
import importlib
import inspect
from pathlib import Path
import sys
import time
import types
from typing import get_type_hints

from pydantic import BaseModel
from sqlalchemy import select

from ees_asset_native_fixture import NativeAssetFixture, ROOT


class NativeReadFixture(NativeAssetFixture):
    async def start(self):
        await super().start()
        # Replace the asset fixture's simple identity table with Native's full
        # schema before any test records exist; never touch a user's database.
        old = self.Base.metadata.tables["user"]
        async with self.engine.begin() as connection:
            await connection.run_sync(old.drop)
        self.Base.metadata.remove(old)
        env = sys.modules["open_webui.env"]
        env.VERSION = self.builder.VERSION
        env.DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL = 0
        env.DEFAULT_GROUP_SHARE_PERMISSION = False
        misc = sys.modules["open_webui.utils.misc"]
        tree = ast.parse(self.members["open_webui/utils/misc.py"])
        throttle = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "throttle"]
        exec(compile(ast.Module(body=throttle, type_ignores=[]), "pinned-native-throttle", "exec"), misc.__dict__)
        self.stub("open_webui.models.files", FileMetadataResponse=BaseModel)
        self.native_users = self.load("open_webui.models.users")
        self.native_groups = self.load("open_webui.models.groups")
        self.tools.Users = self.native_users.Users
        self.tools.Groups = self.native_groups.Groups
        self.binding.Groups = self.native_groups.Groups
        async with self.engine.begin() as connection:
            await connection.run_sync(self.Base.metadata.create_all)
        for identifier, role in (("admin", "admin"), ("owner", "user"), ("reader", "user"), ("outsider", "user")):
            self.users[identifier] = await self.native_users.Users.insert_new_user(identifier, identifier, identifier + "@example.invalid", role=role)
        package = ROOT / "agent-pack/skills/ees-work-demo/scripts"
        sys.modules["open_webui"].__path__.append(str(package))
        self.native = importlib.import_module("open_webui.ees_workflow_native")
        self.workflow = importlib.import_module("open_webui.ees_workflow")
        self.service = self.workflow.WorkflowService(self.directory / "ees-work.sqlite3", self.native_users.Users.get_user_by_id,
                                                     lambda identifier: None)
        self.bridge = self.native.NativeBridge(self.service, self.app)
        return self

    async def register_read_tool(self, family, *, identifier=None):
        identifier = identifier or "fixture_" + family
        source = (ROOT / f"agent-pack/skills/{family}-read/scripts/{family}_tool.py").read_text(encoding="utf-8")
        # Use the actual loader for these six existing code functions. Stored
        # schemas are fixture metadata derived from their real signatures;
        # this does not exercise Native's langchain schema generator.
        # Registration is fixture setup, never approval/inspection/dispatch.
        module, _ = await self.plugin.load_tool_module_by_id(identifier, content=source)
        funcs = {"confluence": ("search_pages", "get_page"), "jira": ("jira_dashboard", "jira_get_issue"),
                 "github": ("github_list_pull_requests", "github_get_pull_request")}[family]
        specs = []
        for name in funcs:
            properties, required = {}, []
            hints = get_type_hints(getattr(module, name))
            for parameter in inspect.signature(getattr(module, name)).parameters.values():
                if parameter.name.startswith("__"):
                    continue
                properties[parameter.name] = {"type": "integer" if hints.get(parameter.name) is int else "string"}
                if parameter.default is inspect.Parameter.empty:
                    required.append(parameter.name)
                else:
                    properties[parameter.name]["default"] = parameter.default
            specs.append({"name": name, "parameters": {"type": "object", "properties": properties, "required": required}})
        # Actual Native SQL table method, ACL and encrypted admin settings.
        form = self.tools.ToolForm(id=identifier, name=family, content=source, meta={"description": "Synthetic read fixture"},
                                   access_grants=[{"principal_type": "user", "principal_id": "reader", "permission": "read"}])
        tool = await self.tools.Tools.insert_new_tool("admin", form, specs)
        if tool is None:
            raise AssertionError("Native fixture tool persistence failed")
        config = {"ENABLED": True, "ALLOW_HTTP": False, "TIMEOUT_SECONDS": 2}
        config.update({"confluence": {"CONFLUENCE_BASE_URL": "https://confluence.invalid", "ALLOWED_SPACES": "EMS"},
                       "jira": {"JIRA_BASE_URL": "https://jira.invalid", "ALLOWED_PROJECTS": "EESEMS"},
                       "github": {"GITHUB_BASE_URL": "https://github.invalid", "ALLOWED_REPOSITORIES": "team/repo"}}[family])
        await self.tools.Tools.update_tool_valves_by_id(identifier, config)
        for actor in ("admin", "reader"):
            await self.tools.Tools.update_user_valves_by_id_and_user_id(identifier, actor, {"PAT": "synthetic-" + actor + "-pat"})
        refs = {}
        for name in funcs:
            inspected = await self.bridge.inspect(self.users["admin"], identifier, name)
            approved = await self.bridge.approval_action(self.users["admin"], {
                "action": "approve", "reference": inspected["reference"],
                "evidence": "synthetic-fixture: pinned existing read code, no live system claims",
            })
            refs[name] = approved["reference"]
        return refs
