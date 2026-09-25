"""Offline release integrity tests; real upstream wheel check is opt-in.

Set EES_TEST_UPSTREAM_WHEEL to the verified official wheel path to additionally
build and audit that wheel. The workflow probe imports emitted modules under
their public package name with the unrelated CLI initializer isolated; it never
installs or starts Open WebUI or accesses its user database.
"""

import ast
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ees_branding_build", ROOT / "scripts" / "build_ees_webui.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

NOTICE = b"# LICENSE: Open WebUI branding is governed by the bundled license.\n"
LICENSE = b"Synthetic license fixture; copyright and branding conditions must survive.\n"


def assert_workflow_package(test, wheel):
    """Resolve the actual emitted sibling imports/resources and native Tool API."""
    probe = r'''
import asyncio, hashlib, importlib, importlib.util, json, sys, types
from pathlib import Path
root = Path(sys.argv[1])
# The unchanged WebUI CLI initializer imports serving dependencies. Only that
# parent initializer is isolated; workflow imports resolve real wheel files.
package = types.ModuleType("open_webui")
package.__path__ = [str(root / "open_webui")]
sys.modules["open_webui"] = package
workflow = importlib.import_module("open_webui.ees_workflow")
for name in ("ees_workflow", "ees_workflow_definition", "ees_workflow_view", "ees_workflow_authoring",
             "ees_workflow_execution", "ees_workflow_native", "ees_workflow_contract",
             "ees_workflow_examples", "ees_workflow_model"):
    importlib.import_module("open_webui." + name)
    assert Path(sys.modules["open_webui." + name].__file__).parent == root / "open_webui"
seed = workflow._dump(workflow._seed()).encode("utf-8")
assert len(seed) == 11651
assert hashlib.sha256(seed).hexdigest() == "a68dda6dbcfa55184653816a0e4774ac7e4b60619cec962edbc26434e6200451"
assert workflow.validate_definition(workflow._seed()) == []
users = {key: {"id": key, "role": "user"} for key in ("alice", "bob")}
chats = {"chat-a": {"id": "chat-a", "user_id": "alice"}}
service = workflow.WorkflowService(root / "data" / "ees-work.sqlite3", users.get, chats.get)
workflow._service = service
spec = importlib.util.spec_from_file_location("installed_workflow_tool", sys.argv[2])
tool_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool_module)
tool = tool_module.Tools()
screen = {"kind": "published", "selection": {"site_id": "us-a", "system": "EMS",
    "process_id": "setup-p", "node_id": "db-j", "version": 1}}
async def event(value):
    if "__eesNativeWorkV1?.selection" in value["data"]["code"]:
        return {"ok": True, **screen}
    return {"ok": True, "notified": True}
async def run():
    args = {"__user__": users["alice"], "__metadata__": {"chat_id": "chat-a"}, "__event_call__": event}
    capabilities = await service.authoring_capabilities(users["alice"])
    assert capabilities["ok"] and not capabilities["can_author"]
    published = await tool.ees_workflow_view(**args)
    assert published["ok"] and published["case"] is None, published
    assert not (await workflow.get_state(users["alice"], chat_id="chat-a"))["cases"]
    write = {"target": published["target"], "request_id": "packaged-input-1",
             "payload": {"inputs": {"db": "synthetic package target"}}}
    created = await tool.ees_workflow_action("update_inputs", **write, **args)
    assert created["ok"], created
    before = created["case"]
    replayed = await tool.ees_workflow_action("update_inputs", **write, **args)
    assert replayed["ok"] and replayed["replayed"], replayed
    assert replayed["case"] == before
    screen.clear()
    screen.update(kind="case", case_id=before["id"], node_id="db-j", revision=before["revision"])
    seen = await tool.ees_workflow_view(**args)
    selected = await tool.ees_workflow_action("select", node_id="ap-j", expected_revision=before["revision"], target=seen["target"], **args)
    assert selected["ok"], selected
    screen.update(node_id="ap-j", revision=selected["case"]["revision"])
    seen = await tool.ees_workflow_view(**args)
    assert seen["case"] == selected["case"]
    assert seen["case"]["selected_id"] == "ap-j"
    assert seen["case"]["revision"] == before["revision"] + 1
    conflict = await tool.ees_workflow_action("select", node_id="db-j", expected_revision=before["revision"], target=seen["target"], **args)
    assert conflict["error"]["code"] == "revision_conflict", conflict
    forbidden = await workflow.get_state(users["bob"], case_id=before["id"])
    assert forbidden["error"]["code"] == "case_not_found", forbidden
    workflow._service = workflow.WorkflowService(service.database, users.get, chats.get)
    assert (await workflow.get_state(users["alice"], chat_id="chat-a"))["case"] == seen["case"]
    assert not (root / ".webui_secret_key").exists()
    assert not (root / "data" / "webui.db").exists()
asyncio.run(run())
print("installed_workflow_contract=pass")
'''
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with ZipFile(wheel) as archive:
            for name in ("ees_workflow.py", "ees_workflow_definition.py", "ees_workflow_view.py", "ees_workflow_authoring.py",
                         "ees_workflow_execution.py", "ees_workflow_native.py", "ees_workflow_contract.py",
                         "ees_workflow_examples.py", "ees_workflow_model.py",
                         "workflow_seed.json", "workflow_policy.json"):
                target = root / "open_webui" / name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(archive.read("open_webui/" + name))
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning",
             "-c", probe, str(root), str(builder.WORK_DIR / "scripts/workflow_tool.py")],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=20)
        test.assertEqual(result.returncode, 0, result.stderr)
        test.assertEqual(result.stdout.strip(), "installed_workflow_contract=pass")


# Independent expected writer/normalization boundary inventory. These minimal
# sources exercise patch structure without storing a copy of upstream Python.
GUARD_METHODS = {
    "open_webui/models/tools.py": ("ToolsTable", (
        "insert_new_tool", "update_tool_by_id", "update_tool_valves_by_id", "delete_tool_by_id")),
    "open_webui/models/models.py": ("ModelsTable", (
        "insert_new_model", "update_model_by_id", "update_model_updated_at_by_id", "toggle_model_by_id",
        "sync_models", "delete_model_by_id", "delete_all_models", "get_all_models", "get_models",
        "get_base_models", "search_models", "get_model_by_id", "get_models_by_ids")),
    "open_webui/models/access_grants.py": ("AccessGrantsTable", (
        "grant_access", "revoke_access", "revoke_all_access", "set_access_control", "set_access_grants")),
    "open_webui/utils/plugin.py": (None, ("load_tool_module_by_id", "get_tool_module_from_cache")),
    "open_webui/routers/knowledge.py": (None, ("delete_knowledge_by_id",)),
    "open_webui/utils/models.py": (None, ("check_model_access",)),
    "open_webui/routers/users.py": (None, ("get_user_preview",)),
    "open_webui/routers/ollama.py": (None, ("get_filtered_models",)),
    "open_webui/routers/openai.py": (None, ("get_filtered_models",)),
    "open_webui/routers/groups.py": (None, ("preview_group_access",)),
    "open_webui/utils/access_control/__init__.py": (None, ("has_base_model_access",)),
}


def guard_fixture_members():
    members = {}
    for filename, (class_name, methods) in GUARD_METHODS.items():
        indent = "    " if class_name else ""
        source = '\"\"\"Synthetic asset boundary.\"\"\"\nfrom __future__ import annotations\n'
        if class_name:
            source += "class " + class_name + ":\n"
        for method in methods:
            source += indent + "async def " + method + "(self=None, db=None):\n" + indent + "    return None\n"
        members[filename] = source.encode()
    members["open_webui/routers/models.py"] = b"router = APIRouter()\n"
    members["open_webui/routers/tools.py"] = b"router = APIRouter()\n"
    for function, key, nest in (("create_new_tools", "form_data.id", True), ("update_tools_by_id", "id", False)):
        source = "async def " + function + "(request, form_data, id=None):\n"
        if nest:
            source += "    if True:\n"
        indent = "        " if nest else "    "
        source += (indent + "try:\n" + indent + "    TOOLS[" + key + "] = tool_module\n"
                   + indent + "    specs = get_tool_specs(TOOLS[" + key + "])\n"
                   + indent + "    tools = await native_save(form_data, specs)\n"
                   + indent + "    if tools:\n" + indent + "        await publish_event(request)\n"
                   + indent + "except HTTPException:\n" + indent + "    raise\n"
                   + indent + "except Exception as e:\n" + indent + "    raise\n")
        if function == "update_tools_by_id":
            source = source.replace("        specs =", "        log.debug(updated)\n        specs =", 1)
        members["open_webui/routers/tools.py"] += source.encode()
    members["open_webui/utils/tools.py"] = b"""async def get_tools(request, user, tool_ids, extra_params):
    tools_dict = {}
    # Batch-fetch all DB tools in one query instead of one per tool_id
    tool_models = await Tools.get_tools_by_ids(tool_ids)
    for tool_id in tool_ids:
        tool = tool_models.get(tool_id)
        if tool:
            if not await has_access(tool, user):
                continue
            tools_cache = get_tools_cache(request)
            tools_cache[tool_id] = await load_tool_module_by_id(tool_id, content=tool.content)
        else:
            await get_tool_servers(request)
    return tools_dict
"""
    return members


def fixture_members():
    app = "open_webui/frontend/_app/"
    info = "open_webui-0.11.3.dist-info/"
    members = {
        "open_webui/main.py": b"# preserved upstream routes\nasync def lifespan(app):\n"
        b"    app.state.main_loop = asyncio.get_running_loop()\n    await existing_startup(app)\n    yield\n    await existing_shutdown(app)\n"
        b"app.include_router(tools.router, prefix='/api/v1/tools', tags=['tools'])\n"
        b"if os.path.exists(FRONTEND_BUILD_DIR):\n    app.mount('/', existing_spa)\n",
        "open_webui/env.py": NOTICE + b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
        b"if WEBUI_NAME != 'Open WebUI':\n    WEBUI_NAME += ' (Open WebUI)'\n" + NOTICE,
        "open_webui/frontend/index.html": b"<!-- Open WebUI license notice -->\n<title>Open WebUI</title>\n"
        + b'<script src="/_app/immutable/entry/start.js"></script>\n' * 49
        + b'<link rel="stylesheet" href="/static/custom.css" />\n</head>\n',
        app + "immutable/chunks/CHq18Uto.js": b'const ca="Open WebUI",other="Open WebUI documentation";',
        app + "immutable/nodes/0.CvnwnD8l.js": b'new Notification(`${title} / Open WebUI`);' * 3,
        app + "immutable/nodes/26.Ck8JdNW5.js": b'document.title=`${channel} / Open WebUI`;' * 2,
        app + "immutable/chunks/DKj2ZiCb.js": b'const an="0.11.3";fetch(`${base}/_app/version.json`);',
        app + "immutable/chunks/zKJlHFgk.js": b';'.join(
            before for before, _, _ in builder.PATCHES[app + "immutable/chunks/zKJlHFgk.js"]),
        app + "version.json": b'{"version":"0.11.3"}',
        app + "immutable/entry/start.js": b'import "../chunks/CHq18Uto.js";\n//# sourceMappingURL=start.js.map',
        app + "immutable/entry/start.js.map": b'{"file":"_app/immutable/entry/start.js","sourcesContent":["Open WebUI"]}',
        info + "METADATA": b"Metadata-Version: 2.4\nName: open-webui\nVersion: 0.11.3\n"
        b"Requires-Dist: example==1.2.3; python_version >= '3.11'\nLicense-File: LICENSE\n\nOpen WebUI original description\n",
        info + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        info + "RECORD": b"original fixture record\n",
        info + "licenses/LICENSE": LICENSE,
        "open_webui/static/BRANDING.md": NOTICE,
        "open_webui/backend_unrelated.py": b"unchanged_application = 'Open WebUI'\n",
        "open_webui/static/custom.css": b"/* existing user style stays intact */\n",
        "open_webui/frontend/static/custom.css": b"/* original frontend style stays intact */\n",
    }
    members.update(guard_fixture_members())
    for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
        for name in builder.ASSET_NAMES:
            members[prefix + name] = b"old artwork " + name.encode()
    members["open_webui/frontend/favicon.png"] = b"old favicon"
    for name, (origin, _) in builder.FONT_SOURCES.items():
        members[origin] = b"unchanged upstream font " + name.encode()
    return members


def assert_record(test, wheel):
    with ZipFile(wheel) as archive:
        record_path = builder.TARGET_INFO + "RECORD"
        rows = list(csv.reader(io.StringIO(archive.read(record_path).decode())))
        test.assertEqual(len(rows), len(archive.namelist()))
        test.assertEqual({row[0] for row in rows}, set(archive.namelist()))
        for path, digest, size in rows:
            if path == record_path:
                test.assertEqual((digest, size), ("", ""))
                continue
            content = archive.read(path)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            test.assertEqual(digest, "sha256=" + encoded, path)
            test.assertEqual(int(size), len(content), path)


def assert_asset_guard_patches(test, built):
    for filename, (class_name, methods) in GUARD_METHODS.items():
        tree = ast.parse(built.read(filename))
        nodes = tree.body
        if class_name:
            nodes = next(node for node in nodes if isinstance(node, ast.ClassDef) and node.name == class_name).body
        for name in methods:
            node = next(node for node in nodes if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
            decorators = [ast.unparse(value) for value in node.decorator_list]
            wanted = ("guard_operation" if filename == "open_webui/utils/plugin.py" else
                      "guard_table_method(asset_types_only=True)" if class_name == "AccessGrantsTable" else "guard_table_method")
            test.assertEqual(1, decorators.count(wanted), (filename, name))
    for filename in ("open_webui/routers/tools.py", "open_webui/routers/models.py"):
        text = built.read(filename).decode()
        test.assertEqual(1, text.count("router = APIRouter(route_class=AssetGuardRoute)"))
        compile(text, filename, "exec")
    tools = ast.parse(built.read("open_webui/routers/tools.py"))
    for name in ("create_new_tools", "update_tools_by_id"):
        node = next(node for node in tools.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
        assignments = [child for child in ast.walk(node) if isinstance(child, ast.Assign)
                       and any(isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                               and target.value.id == "TOOLS" for target in child.targets)]
        test.assertEqual(1, len(assignments), name)
        saves = [child for child in ast.walk(node) if isinstance(child, ast.Assign)
                 and isinstance(child.value, ast.Await)
                 and any(isinstance(target, ast.Name) and target.id == "tools" for target in child.targets)]
        test.assertTrue(saves and saves[-1].lineno < assignments[0].lineno, name)
        guarded = next(child for child in ast.walk(node) if isinstance(child, ast.If)
                       and isinstance(child.test, ast.Name) and child.test.id == "tools")
        test.assertIs(guarded.body[0], assignments[0])
        calls = [child for child in ast.walk(guarded) if isinstance(child, ast.Call)
                 and isinstance(child.func, ast.Name) and child.func.id == "publish_event"]
        test.assertTrue(calls and calls[0].lineno > assignments[0].lineno)
        evictions = [child for child in ast.walk(node) if isinstance(child, ast.Call)
                     and isinstance(child.func, ast.Attribute) and child.func.attr == "pop"
                     and isinstance(child.func.value, ast.Call) and isinstance(child.func.value.func, ast.Name)
                     and child.func.value.func.id == "get_tools_cache"]
        test.assertEqual(2, len(evictions), name)
        if name == "update_tools_by_id":
            test.assertFalse(any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                                 and child.func.attr == "debug" and any(isinstance(arg, ast.Name) and arg.id == "updated"
                                 for arg in child.args) for child in ast.walk(node)))
    loader_text = built.read("open_webui/utils/tools.py").decode()
    loader_tree = ast.parse(loader_text)
    loader = next(node for node in loader_tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_tools")
    test.assertFalse(loader.decorator_list)  # Remote preparation must not hold the asset guard.
    loop = next(node for node in loader.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == "tool_id")
    local = next(node for node in loop.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "ees_load_local_tool")
    test.assertEqual(["guard_operation"], [ast.unparse(value) for value in local.decorator_list])
    local_calls = [node for node in ast.walk(local) if isinstance(node, ast.Call)]
    tool_reads = [node for node in local_calls if isinstance(node.func, ast.Attribute) and node.func.attr == "get_tool_by_id"]
    loads = [node for node in local_calls if isinstance(node.func, ast.Name) and node.func.id == "load_tool_module_by_id"]
    test.assertEqual(1, len(tool_reads))
    test.assertTrue(loads and tool_reads[0].lineno < loads[0].lineno)
    test.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id in {"get_tool_servers", "execute_tool_server"}
                         for node in local_calls))
    test.assertFalse(any(isinstance(node, ast.Continue) for node in ast.walk(local)))
    remote_branch = next(node for node in loop.body if isinstance(node, ast.If) and node.orelse)
    test.assertEqual("await ees_load_local_tool()", ast.unparse(remote_branch.test))
    test.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_tool_servers"
                        for child in remote_branch.orelse for node in ast.walk(child)))
    test.assertNotIn("tool_models = await Tools.get_tools_by_ids(tool_ids)", loader_text)
    test.assertIn("EES_ASSET_LOCAL_TOOL_GUARD = 1", loader_text)
    main = built.read("open_webui/main.py").decode()
    tree = ast.parse(main)
    life = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan")
    start = next(node for node in life.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)
                 and isinstance(node.value.value, ast.Call) and isinstance(node.value.value.func, ast.Name)
                 and node.value.value.func.id == "start_asset_guard")
    protected = next(node for node in life.body if isinstance(node, ast.Try) and node.finalbody)
    test.assertLess(start.lineno, protected.lineno)
    test.assertIn("await stop_asset_guard(app)", ast.unparse(protected.finalbody[0]))
    test.assertTrue(any(isinstance(node, ast.Yield) for node in ast.walk(protected)))
    test.assertLess(main.index("app.include_router(create_asset_router()"), main.index("if os.path.exists(FRONTEND_BUILD_DIR):"))


class BrandingBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.wheel = self.root / builder.SOURCE_FILENAME
        self.assets = self.root / "assets"
        self.assets.mkdir()
        for name in builder.ASSET_NAMES:
            (self.assets / name).write_bytes(b"EES artwork " + name.encode())
        self.ui = self.root / "ui"
        self.ui.mkdir()
        for name in builder.UI_FILES:
            (self.ui / name).write_bytes(b"reviewed UI asset " + name.encode())
        for name, content in {
            "ees-work-view.js": b"function createWorkView() { return 'view'; }\n",
            "ees-work-designer.js": b"function createWorkDesigner() { return 'designer'; }\n",
            "ees-work-launcher.js": b"(() => { window.fixture = [createWorkView(), createWorkDesigner()]; })();\n",
        }.items():
            (self.ui / name).write_bytes(content)
        self.members = fixture_members()
        self.guard_hashes = {name: hashlib.sha256(self.members[name]).hexdigest()
                             for name in builder.ASSET_GUARD_SOURCE_HASHES}
        self.write_fixture()

    def write_fixture(self):
        with ZipFile(self.wheel, "w") as archive:
            for name, content in self.members.items():
                archive.writestr(name, content)
        self.source_hash = builder.sha256_file(self.wheel)

    def build(self, directory="release"):
        fonts = {name: (origin, hashlib.sha256(b"unchanged upstream font " + name.encode()).hexdigest())
                 for name, (origin, _) in builder.FONT_SOURCES.items()}
        with (mock.patch.object(builder, "SOURCE_SHA256", self.source_hash),
              mock.patch.object(builder, "FONT_SOURCES", fonts),
              mock.patch.object(builder, "ASSET_GUARD_SOURCE_HASHES", self.guard_hashes)):
            return builder.build(self.wheel, self.root / directory, self.assets, self.ui)

    def test_reproducible_wheel_manifest_and_record_preserve_original(self):
        first = self.build("first")
        second = self.build("second")
        self.assertEqual(first, second)
        self.assertEqual(builder.sha256_file(self.wheel), self.source_hash)
        for filename in (builder.WHEEL_FILENAME, "manifest.json"):
            self.assertEqual((self.root / "first" / filename).read_bytes(), (self.root / "second" / filename).read_bytes())
        assert_record(self, self.root / "first" / builder.WHEEL_FILENAME)
        self.assertEqual(first["source"]["sha256"], self.source_hash)
        self.assertEqual(first["wheel"]["sha256"], builder.sha256_file(self.root / "first" / builder.WHEEL_FILENAME))

    def test_same_version_ui_change_updates_only_its_content_cache_key(self):
        self.build("before")
        source = self.ui / "ees-work-designer.js"
        source.write_text(source.read_text(encoding="utf-8") + "\n// revised designer\n", encoding="utf-8")
        self.build("after")
        with (ZipFile(self.root / "before" / builder.WHEEL_FILENAME) as before,
              ZipFile(self.root / "after" / builder.WHEEL_FILENAME) as after):
            indexes = [archive.read("open_webui/frontend/index.html") for archive in (before, after)]
            for filename in ("ees-work-launcher.css", "ees-work-panel.js", "ees-work-launcher.js"):
                digests = [hashlib.sha256(archive.read(builder.TARGET_APP + filename)).hexdigest()
                           for archive in (before, after)]
                for index, digest in zip(indexes, digests):
                    self.assertIn(("/_ees12/" + filename + "?v=" + digest).encode("ascii"), index)
                self.assertEqual(digests[0] == digests[1], filename != "ees-work-launcher.js")
            self.assertEqual(before.read(builder.TARGET_INFO + "METADATA"),
                             after.read(builder.TARGET_INFO + "METADATA"))

    def test_packaged_workflow_and_managed_tool_share_public_contract(self):
        # Workflow files are actual shipped sources even when the surrounding
        # upstream wheel is a disposable fixture. This is not a native UI test.
        self.build()
        assert_workflow_package(self, self.root / "release" / builder.WHEEL_FILENAME)

    def test_launcher_assembly_order_is_private_and_has_one_runtime_asset(self):
        source = builder.assemble_work_launcher(self.ui)
        self.assertLess(source.index(b"function createWorkView"), source.index(b"function createWorkDesigner"))
        self.assertLess(source.index(b"function createWorkDesigner"), source.index(b"window.fixture"))
        manifest = self.build()
        self.assertEqual([name for name in manifest["changed_files"] if name.endswith((
            "ees-work-view.js", "ees-work-designer.js", "ees-work-launcher.js"))],
            [builder.TARGET_APP + "ees-work-launcher.js"])
        if shutil.which("node"):
            probe = """const vm=require('node:vm'),assert=require('node:assert/strict');
const scope={window:{}};vm.createContext(scope);vm.runInContext(process.argv[1],scope);
assert.equal(JSON.stringify(scope.window.fixture),'["view","designer"]');
assert.equal(scope.createWorkView,undefined);assert.equal(scope.createWorkDesigner,undefined);
assert.equal(scope.window.createWorkView,undefined);assert.equal(scope.window.createWorkDesigner,undefined);
"""
            result = subprocess.run([shutil.which("node"), "-e", probe, source.decode("utf-8")],
                                    capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_launcher_missing_empty_duplicate_and_swapped_units_fail_before_output(self):
        originals = {name: (self.ui / name).read_bytes() for name in builder.WORK_LAUNCHER_SOURCES}
        invalid = [(name, value) for name in originals for value in (None, b"", b" \r\n\t")]
        invalid += [("ees-work-view.js", originals["ees-work-view.js"] * 2),
                    ("ees-work-designer.js", originals["ees-work-view.js"]),
                    ("ees-work-launcher.js", originals["ees-work-launcher.js"] + originals["ees-work-designer.js"]),
                    ("ees-work-view.js", b"const createWorkView = () => {};\n")]
        for name, value in invalid:
            with self.subTest(name=name, value=value):
                path = self.ui / name
                path.unlink()
                if value is not None:
                    path.write_bytes(value)
                with self.assertRaisesRegex(ValueError, "launcher|UI asset"):
                    self.build()
                self.assertFalse((self.root / "release").exists())
                path.write_bytes(originals[name])
        with mock.patch.object(builder, "WORK_LAUNCHER_SOURCES", tuple(reversed(builder.WORK_LAUNCHER_SOURCES))):
            with self.assertRaisesRegex(ValueError, "source order"):
                self.build()
        self.assertFalse((self.root / "release").exists())

    def test_launcher_linked_source_or_directory_fails_before_output(self):
        target = self.root / "source.js"
        target.write_bytes((self.ui / "ees-work-view.js").read_bytes())
        linked = self.root / "linked-ui"
        try:
            linked.symlink_to(self.ui, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable for this account")
        with self.assertRaisesRegex(ValueError, "Linked"):
            builder.assemble_work_launcher(linked)
        # A symlink above ui_dir is equally unsupported.
        with self.assertRaisesRegex(ValueError, "Linked"):
            builder.assemble_work_launcher(linked / "child")
        (self.ui / "ees-work-view.js").unlink()
        (self.ui / "ees-work-view.js").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "linked"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_native_fixture_rejects_a_launcher_not_built_from_current_sources(self):
        fixture_spec = importlib.util.spec_from_file_location("native_ui_fixture", ROOT / "tests/native_ui_fixture.py")
        native_ui_fixture = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(native_ui_fixture)
        self.build()
        with mock.patch.object(native_ui_fixture, "assemble_work_launcher", return_value=b"new source revision"), \
                self.assertRaisesRegex(ValueError, "assembled sources"):
            native_ui_fixture.NativeUIServer(self.root / "release" / builder.WHEEL_FILENAME)

    def test_only_reviewed_content_changes_and_frontend_cache_namespace_moves(self):
        manifest = self.build()
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            self.assertFalse(any(name.startswith(builder.SOURCE_APP) for name in built.namelist()))
            self.assertEqual(len(built.namelist()), len(self.members) + (len(builder.THEME_FILES) + len(builder.WORK_FILES) + len(builder.ASSET_GUARD_FILES)))
            for name, original in self.members.items():
                target = builder.target_name(name)
                if target not in manifest["changed_files"]:
                    self.assertEqual(built.read(target), original, name)
            self.assertEqual(built.read(builder.TARGET_INFO + "licenses/LICENSE"), LICENSE)
            self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                             self.members[builder.SOURCE_INFO + "METADATA"].replace(b"Version: 0.11.3\n", b"Version: 0.11.3+ees.12\n"))
            self.assertEqual(built.read("open_webui/env.py").count(NOTICE), 2)
            self.assertNotIn(b"WEBUI_NAME +=", built.read("open_webui/env.py"))
            self.assertIn(b"EES Work", built.read("open_webui/frontend/index.html"))
            self.assertNotIn(b"/_app/", built.read("open_webui/frontend/index.html"))
            index = built.read("open_webui/frontend/index.html")
            self.assertEqual(index.count(builder.THEME_LINK), 1)
            for filename in ("ees-work-launcher.css", "ees-work-panel.js", "ees-work-launcher.js"):
                digest = hashlib.sha256(built.read(builder.TARGET_APP + filename)).hexdigest()
                self.assertIn(("/_ees12/" + filename + "?v=" + digest).encode("ascii"), index)
            main = built.read("open_webui/main.py")
            self.assertLess(main.index(b"install_ees_work_demo(app, get_verified_user)"), main.index(b"app.mount"))
            for relative, target in builder.WORK_ASSETS.items():
                self.assertEqual(built.read(target), (builder.WORK_DIR / relative).read_bytes())
                self.assertFalse(target.startswith("open_webui/frontend/"))
            self.assertLess(index.index(b"/static/custom.css"), index.index(builder.THEME_LINK))
            self.assertLess(index.index(builder.THEME_LINK), index.index(b"</head>"))
            for name, relative in builder.UI_FILES.items():
                expected = (builder.assemble_work_launcher(self.ui) if name == "ees-work-launcher.js"
                            else (self.ui / name).read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + relative), expected)
            self.assertNotIn(builder.TARGET_APP + "ees-work-view.js", built.namelist())
            self.assertNotIn(builder.TARGET_APP + "ees-work-designer.js", built.namelist())
            for name, (origin, _) in builder.FONT_SOURCES.items():
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/" + name), self.members[origin])
            runtime = built.read(builder.TARGET_APP + "immutable/chunks/DKj2ZiCb.js")
            self.assertIn(b"/_ees12/version.json", runtime)
            chat = built.read(builder.TARGET_APP + "immutable/chunks/zKJlHFgk.js")
            self.assertIn(builder.NATIVE_DRAFT_HOOK, chat)
            self.assertIn(b'if(window.__eesNativeDraftV1===eesNativeDraftApi)delete window.__eesNativeDraftV1;', chat)
            self.assertEqual(json.loads(built.read(builder.TARGET_APP + "version.json"))["version"], builder.VERSION)
            for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
                for name in builder.ASSET_NAMES:
                    self.assertEqual(built.read(prefix + name), (self.assets / name).read_bytes())

    def test_asset_guard_inventory_and_emitted_lifecycle_cache_order(self):
        self.assertEqual(GUARD_METHODS, builder.ASSET_GUARD_HOOKS)
        self.assertEqual(set(GUARD_METHODS) | {"open_webui/main.py", "open_webui/routers/tools.py", "open_webui/routers/models.py", "open_webui/utils/tools.py"},
                         set(builder.ASSET_GUARD_SOURCE_HASHES))
        self.assertEqual(15, len(builder.ASSET_GUARD_SOURCE_HASHES))
        manifest = self.build()
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            assert_asset_guard_patches(self, built)
            self.assertEqual(built.read(builder.ASSET_GUARD_FILES[0]), builder.ASSET_GUARD_SOURCE.read_bytes())
        self.assertTrue(set(builder.ASSET_GUARD_SOURCE_HASHES) | set(builder.ASSET_GUARD_FILES)
                        <= set(manifest["changed_files"]))

    def test_runtime_installation_inventory_matches_all_builder_hooks(self):
        tree = ast.parse(builder.ASSET_GUARD_SOURCE.read_bytes())
        inventory = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in {"TABLE_METHODS", "CALLER_HOOKS"}}
        expected_tables = {Path(filename).stem: methods for filename, (class_name, methods) in GUARD_METHODS.items()
                           if class_name}
        expected_callers = {filename.removesuffix(".py").replace("/", ".").removesuffix(".__init__"): methods
                            for filename, (class_name, methods) in GUARD_METHODS.items() if not class_name}
        self.assertEqual(expected_tables, inventory["TABLE_METHODS"])
        self.assertEqual(expected_callers, inventory["CALLER_HOOKS"])

    def test_asset_writer_hash_drift_fails_even_when_patch_anchor_remains(self):
        self.members["open_webui/models/tools.py"] += b"# unreviewed writer outside a hook\n"
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Pinned asset writer source differs"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_missing_required_hook_fails_after_whole_file_hash_check(self):
        filename = "open_webui/models/models.py"
        self.members[filename] = self.members[filename].replace(b"async def get_model_by_id(", b"async def renamed_reader(")
        self.guard_hashes[filename] = hashlib.sha256(self.members[filename]).hexdigest()
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Asset guard method differs"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_missing_asset_writer_member_fails_before_writing(self):
        del self.members["open_webui/utils/plugin.py"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Missing wheel entries"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_missing_empty_and_linked_asset_guard_runtime_fail_before_writing(self):
        missing = self.root / "missing-runtime.py"
        empty = self.root / "empty-runtime.py"
        empty.write_bytes(b"")
        candidates = [missing, empty]
        linked = self.root / "linked-runtime.py"
        try:
            linked.symlink_to(builder.ASSET_GUARD_SOURCE)
        except OSError:
            pass
        else:
            candidates.append(linked)
        for runtime in candidates:
            with self.subTest(runtime=runtime.name), mock.patch.object(builder, "ASSET_GUARD_SOURCE", runtime):
                with self.assertRaisesRegex(ValueError, "asset guard runtime"):
                    self.build()
                self.assertFalse((self.root / "release").exists())

    def test_missing_mock_runtime_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as empty:
            with ZipFile(self.wheel) as archive:
                with self.assertRaisesRegex(ValueError, "EES Work asset"):
                    builder.prepare_additions(archive, self.ui, Path(empty))

    def test_wrong_source_hash_fails_without_output(self):
        self.wheel.write_bytes(self.wheel.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "pinned official"):
            self.build()

    def test_incomplete_archive_is_rejected_before_manifest_publication(self):
        class IncompleteArchive(ZipFile):
            def __exit__(archive, *args):
                writing = archive.mode == 'w'
                result = super().__exit__(*args)
                if writing:
                    with open(archive.filename, 'r+b') as output:
                        output.truncate(100)
                return result

        with mock.patch.object(builder, 'ZipFile', IncompleteArchive):
            with self.assertRaisesRegex(ValueError, 'archive'):
                self.build('incomplete')
        self.assertFalse((self.root / 'incomplete' / builder.WHEEL_FILENAME).exists())
        self.assertFalse((self.root / 'incomplete' / 'manifest.json').exists())
        self.assertFalse((self.root / "release").exists())

    def test_work_name_migrates_registered_brand_names_and_preserves_custom_name(self):
        self.build()
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            synthetic_env = built.read("open_webui/env.py")
        for registered, expected in ((None, "EES Work"), ("EES Assistant", "EES Work"),
                                     ("EES Portal", "EES Work"), ("EES Work", "EES Work"),
                                     ("Team Custom", "Team Custom")):
            with self.subTest(registered=registered):
                environment = {} if registered is None else {"WEBUI_NAME": registered}
                with mock.patch.dict(os.environ, environment, clear=True):
                    namespace = {"os": os}
                    exec(synthetic_env, namespace)
                    self.assertEqual(namespace["WEBUI_NAME"], expected)
                    self.assertEqual(dict(os.environ), environment)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the native draft boundary probe.")
    def test_work_draft_hook_never_imports_or_persists_tool_approval_mode(self):
        # Run the exact emitted hook against the native qi/Ps boundary. The
        # import boundary simulates Ci's side effect if mode reaches it, so an
        # accidental restore of `full` is observable rather than a text check.
        probe = r'''
process.stderr.write('ees_probe=node-entry version=' + process.version + '\n', () => {
const assert = require('node:assert/strict');
let current = {prompt:'original', selectedToolIds:['existing'], toolApprovalMode:'ask'};
let approvalCalls = 0, imported = [], persisted = [], _r = null;
const window = {location:{pathname:'/'}}, ce = false, le = {}, r = value => value;
const j = () => false, g = () => false, Fr = () => 'native-chat',G=()=>'',d=()=>'';
const us = () => current;
const Ps = async (draft, chatId, debounce) => persisted.push({draft, chatId, debounce});
const qi = async serialized => {
  const incoming = JSON.parse(serialized);
  imported.push(incoming);
  if (incoming.toolApprovalMode) {
    approvalCalls += incoming.toolApprovalMode === 'full' ? 1 : 0;
    current.toolApprovalMode = incoming.toolApprovalMode;
  }
  current = {...current, ...incoming};
  return true;
};
'''+builder.NATIVE_DRAFT_LOAD_GUARD.decode()+builder.NATIVE_DRAFT_HOOK.decode()+r'''
(async () => {
  const hook = window.__eesNativeDraftV1;
  let finishFirst,finishSecond;
  const first=eesNativeDraftLoad(()=>new Promise(resolve=>{finishFirst=resolve;}));
  const second=eesNativeDraftLoad(()=>new Promise(resolve=>{finishSecond=resolve;}));
  assert.equal(hook.ready(),false);
  finishFirst();await first;assert.equal(hook.ready(),false);
  finishSecond();await second;assert.equal(hook.ready(),true);
  window.location.pathname='/c/other';assert.equal(hook.ready(),false);
  window.location.pathname='/';
  const draft = hook.read();
  assert.equal(Object.hasOwn(draft, 'toolApprovalMode'), false);
  assert.equal(current.toolApprovalMode, 'ask');
  await hook.flush();
  assert.equal(await hook.restore(JSON.stringify({prompt:'restored', selectedToolIds:['kept'], toolApprovalMode:'full'})), true);
  assert.equal(current.prompt, 'restored');
  assert.deepEqual(current.selectedToolIds, ['kept']);
  assert.equal(current.toolApprovalMode, 'ask');
  assert.equal(approvalCalls, 0);
  assert.equal(imported.length, 1);
  assert.equal(Object.hasOwn(imported[0], 'toolApprovalMode'), false);
  assert.equal(persisted.length, 2);
  assert.equal(persisted.every(item => !Object.hasOwn(item.draft, 'toolApprovalMode') && item.chatId === 'native-chat' && item.debounce === false), true);
  for (const invalid of ['{', 'null', '[]', '"text"', 'false']) assert.equal(await hook.restore(invalid), false);
  assert.equal(imported.length, 1);
  await new Promise(resolve => process.stderr.write('ees_probe=node-complete\n', resolve));
  console.log('draft_approval_boundary=pass');
})().catch(error => {console.error(error); process.exitCode = 1;});
});
'''
        try:
            result = subprocess.run([shutil.which("node"), "-e", probe], capture_output=True,
                                    text=True, encoding="utf-8", timeout=10)
        except subprocess.TimeoutExpired as error:
            stderr = error.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            stages = [line for line in stderr.splitlines() if line.startswith("ees_probe=")]
            raise AssertionError("Node draft probe timed out after 10s; stderr stages: "
                                 + (", ".join(stages) or "entry not observed")) from None
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "draft_approval_boundary=pass")

    def test_patch_drift_fails_before_writing(self):
        self.members["open_webui/env.py"] += self.members["open_webui/env.py"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Patch precondition failed"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_missing_asset_or_wheel_entry_fails_before_writing(self):
        (self.assets / "favicon.svg").unlink()
        with self.assertRaisesRegex(ValueError, "Missing or empty branding asset"):
            self.build()
        self.assertFalse((self.root / "release").exists())
        del self.members[builder.SOURCE_INFO + "WHEEL"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Missing wheel entries"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_output_collision_never_overwrites_existing_release(self):
        release = self.root / "release"
        release.mkdir()
        for filename in (builder.WHEEL_FILENAME, "manifest.json"):
            with self.subTest(filename=filename):
                path = release / filename
                path.write_bytes(b"previous release")
                with self.assertRaisesRegex(ValueError, "Output already exists"):
                    self.build()
                self.assertEqual(path.read_bytes(), b"previous release")
                self.assertEqual(list(release.iterdir()), [path])
                path.unlink()

    def test_incomplete_theme_changed_font_and_target_collision_fail_before_writing(self):
        cases = (("css", "EES UI asset"), ("license", "EES UI asset"),
                 ("font", "font hash differs"), ("missing-font", "Missing pinned upstream font"),
                 ("collision", "already contains an EES UI target"))
        for mode, error in cases:
            with self.subTest(mode=mode):
                self.setUp()
                origin = next(iter(builder.FONT_SOURCES.values()))[0]
                if mode in {"css", "license"}:
                    (self.ui / ("chat-theme.css" if mode == "css" else "font-licenses.txt")).unlink()
                elif mode == "font":
                    self.members[origin] += b"changed"
                elif mode == "missing-font":
                    del self.members[origin]
                else:
                    self.members[builder.SOURCE_APP + "chat-theme.css"] = b"unexpected upstream target"
                self.write_fixture()
                with self.assertRaisesRegex(ValueError, error):
                    self.build()
                self.assertFalse((self.root / "release").exists())


@unittest.skipUnless(os.environ.get("EES_TEST_UPSTREAM_WHEEL"), "Set EES_TEST_UPSTREAM_WHEEL for the offline official wheel audit.")
class OfficialWheelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for the pinned native Chat probe.")
    def test_native_chat_bridges_preserve_approval_and_bind_only_successful_main_creation(self):
        with ZipFile(Path(os.environ["EES_TEST_UPSTREAM_WHEEL"])) as source:
            name = builder.SOURCE_APP + "immutable/chunks/zKJlHFgk.js"
            chat = source.read(name)
        for before, after, count in builder.PATCHES[name]:
            self.assertEqual(chat.count(before), count)
            chat = chat.replace(before, after)
        chat = chat.decode()
        # Execute actual pinned native functions with only stores/API/UI
        # boundaries stubbed. In particular qi's real Ci(mode) branch remains.
        native_functions = []
        for start, end in ((",qi=async x=>", ",po=x=>"),
                           (",us=()=>", ",Ps=async"),
                           (",kt=async x=>", ",Ht=async")):
            index = chat.index(start)
            native_functions.append("const " + chat[index + 1:chat.index(end, index)] + ";")
        completion_start = chat.index("Ot&&(Ot.error?await Ko(Ot.error,me)")
        completion_end = chat.index(",await Ft(),rs()&&os()},Ko=async", completion_start)
        native_functions.append("const eesProbeCompletion=async response=>{const ue=d(),me={},Tt=true,"
            + builder.NATIVE_COMPLETION_CAPTURE.decode() + "Ot=await response;"
            + chat[completion_start:completion_end] + ";};")
        probe = r'''
const assert = require('node:assert/strict');
const state = value => ({value}), r = item => item.value, c = (item, value) => item.value = value;
const Qr=state('draft'),mr=state([]),Ut=state(['tool']),Qt=state([]),Lt=state([]),cr=state(false),Sr=state(false),$r=state(false),L=state('ask');
const ce=state(false),le=state({setText(){}}),Br=state(null),oe=state(['model']),Hr=state({}),ls=state({});
const Ae=state({state:{}}),Fn={update:callback=>callback({})},Ki=()=>{},Ko=async()=>{},Io=async()=>{};
let embedded=false,temporary=false,nativeId='',failCreation=false,approvalCalls=0,beginCalls=0,_r=null;
const j=()=>embedded,g=()=>temporary,d=()=>nativeId,G=()=>nativeId,H=()=>null,R=()=>null,Fr=()=>nativeId||null;
const Ci=async mode=>{approvalCalls++;c(L,mode);},Ps=async()=>{},Ft=async()=>{},fn=async()=>{},wl=async()=>{};
const xi={set:async id=>{nativeId=id;}},aa={set(){}},wu=()=> 'temporary',l=()=>({t:s=>s}),n=()=>({}),ti=()=>[];
const localStorage={token:'synthetic'},notifications=[];
const window={location:{pathname:'/'},history:{replaceState(state,title,path){window.location.pathname=path;}},__eesNativeWorkV1:{
  beginChatCreation(){if(window.location.pathname!=='/')return null;beginCalls++;return {sequence:beginCalls};},
  finishChatCreation(ticket,id){notifications.push({ticket,id});}
}};
const bu=async()=>{if(failCreation)throw Error('synthetic create failure');return {id:'server-created-chat'};};
'''+"\n".join(native_functions)+builder.NATIVE_DRAFT_LOAD_GUARD.decode()+builder.NATIVE_DRAFT_HOOK.decode()+r'''
(async()=>{
  assert.equal(await window.__eesNativeDraftV1.restore(JSON.stringify({prompt:'restored',selectedToolIds:['kept'],toolApprovalMode:'full'})),true);
  assert.equal(r(Qr),'restored');assert.deepEqual(r(Ut),['kept']);assert.equal(r(L),'ask');assert.equal(approvalCalls,0);
  assert.equal(Object.hasOwn(window.__eesNativeDraftV1.read(),'toolApprovalMode'),false);
  nativeId='provisional';failCreation=true;
  await assert.rejects(kt({currentId:'message',state:{}}),/synthetic create failure/);
  assert.equal(beginCalls,1);assert.equal(notifications.length,0);
  failCreation=false;
  assert.equal(await kt({currentId:'message',state:{}}),'server-created-chat');
  assert.equal(notifications.length,1);assert.equal(notifications[0].id,'server-created-chat');
  assert.equal(notifications[0].ticket.sequence,2);
  await kt({currentId:'message',state:{}});
  assert.equal(beginCalls,2);assert.equal(notifications.length,1);
  nativeId='';temporary=true;await kt({currentId:'message',state:{}});
  assert.equal(beginCalls,2);assert.equal(notifications.length,1);
  nativeId='';temporary=false;embedded=true;await kt({currentId:'message',state:{}});
  assert.equal(beginCalls,2);assert.equal(notifications.length,1);
  embedded=false;nativeId='provisional-2';window.location.pathname='/';
  await eesProbeCompletion({chat_id:'completion-created-chat'});
  assert.equal(notifications.length,2);assert.equal(notifications[1].id,'completion-created-chat');
  assert.equal(window.location.pathname,'/c/completion-created-chat');
  nativeId='provisional-3';window.location.pathname='/';
  await eesProbeCompletion({error:'synthetic response error',chat_id:'must-not-bind'});
  await eesProbeCompletion(null);
  assert.equal(notifications.length,2);
  temporary=true;await eesProbeCompletion({chat_id:'temporary-result'});
  temporary=false;embedded=true;await eesProbeCompletion({chat_id:'embedded-result'});
  assert.equal(notifications.length,2);
  embedded=false;nativeId='provisional-4';window.location.pathname='/';
  let finishResponse;
  const pending=eesProbeCompletion(new Promise(resolve=>{finishResponse=resolve;}));
  nativeId='another-chat';window.location.pathname='/c/another-chat';
  finishResponse({chat_id:'late-result'});await pending;
  assert.equal(notifications.length,2);
  console.log('pinned_native_bridges=pass');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([shutil.which("node"), "-e", probe], capture_output=True,
                                text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pinned_native_bridges=pass")

    def test_real_pinned_wheel_patches_records_and_unrelated_content(self):
        source_path = Path(os.environ["EES_TEST_UPSTREAM_WHEEL"])
        with tempfile.TemporaryDirectory() as temporary:
            manifest = builder.build(source_path, temporary)
            built_path = Path(temporary) / builder.WHEEL_FILENAME
            assert_record(self, built_path)
            with ZipFile(source_path) as source, ZipFile(built_path) as built:
                self.assertEqual(len(source.namelist()) + (len(builder.THEME_FILES) + len(builder.WORK_FILES) + len(builder.ASSET_GUARD_FILES)), len(built.namelist()))
                assert_asset_guard_patches(self, built)
                self.assertEqual(built.read(builder.ASSET_GUARD_FILES[0]), builder.ASSET_GUARD_SOURCE.read_bytes())
                changed = set(manifest["changed_files"])
                for name in source.namelist():
                    target = builder.target_name(name)
                    if target not in changed:
                        self.assertEqual(built.read(target), source.read(name), name)
                metadata = source.read(builder.SOURCE_INFO + "METADATA")
                self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                                 metadata.replace(b"\nVersion: 0.11.3\n", b"\nVersion: 0.11.3+ees.12\n"))
                for filename, (origin, expected) in builder.FONT_SOURCES.items():
                    copied = built.read(builder.TARGET_APP + "fonts/" + filename)
                    self.assertEqual(copied, source.read(origin))
                    self.assertEqual(hashlib.sha256(copied).hexdigest(), expected)
                self.assertEqual(built.read(builder.TARGET_APP + "chat-theme.css"),
                                 (builder.UI_DIR / "chat-theme.css").read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/LICENSE.txt"),
                                 (builder.UI_DIR / "font-licenses.txt").read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + "ees-work-launcher.js"),
                                 builder.assemble_work_launcher())
                for name in ("open_webui/env.py", "open_webui/frontend/index.html"):
                    self.assertEqual(source.read(name).count(b"LICENSE"), built.read(name).count(b"LICENSE"))
            assert_workflow_package(self, built_path)


if __name__ == "__main__":
    unittest.main()
