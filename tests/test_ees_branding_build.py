"""Offline release integrity tests; real upstream wheel check is opt-in.

Set EES_TEST_UPSTREAM_WHEEL and EES_TEST_FRONTEND_DIR to the verified official
wheel and source frontend paths to additionally build and audit that wheel. The workflow probe imports emitted modules under
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
import re
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


def assert_css_icon_cache_keys(test, original, built, icons):
    """Audit only reviewed icon URLs; preserve every byte outside their values."""
    # Parse URL boundaries independently of prepare_additions' byte replacement.
    # icons comes from reviewed source files, never from the builder's additions.
    pattern = rb'''url\(\s*(?P<quote>["']?)(?P<url>[^"'\s)]+)(?P=quote)\s*\)'''
    original_urls = list(re.finditer(pattern, original))
    built_urls = list(re.finditer(pattern, built))
    test.assertEqual(len(built_urls), len(original_urls), "CSS URL inventory changed")
    original_end = built_end = 0
    seen = set()
    for before, after in zip(original_urls, built_urls):
        test.assertEqual(built[built_end:after.start("url")],
                         original[original_end:before.start("url")],
                         "CSS bytes outside URL values changed")
        url = expected = before.group("url")
        for relative, content in icons.items():
            if url in (b"./" + relative.encode("ascii"), b"/" + builder.PROGRAM_FRONTENDS[builder.VERSION].encode("ascii") + b"/" + relative.encode("ascii")):
                expected += b"?v=" + hashlib.sha256(content).hexdigest().encode("ascii")
                seen.add(relative)
                break
        test.assertEqual(after.group("url"), expected, "CSS URL or icon digest differs")
        original_end, built_end = before.end("url"), after.end("url")
    test.assertEqual(built[built_end:], original[original_end:],
                     "CSS trailing bytes changed")
    test.assertEqual(seen, set(icons), "Reviewed icon reference missing from source CSS")


LAUNCHER_ASSEMBLY_PROBE = r"""
const fs=require('node:fs');
const stage = name => fs.writeSync(2, 'ees_probe=' + name + '\n');
stage('launcher-node-entry version=' + process.version);
const vm=require('node:vm'),assert=require('node:assert/strict');
const scope={window:{}};vm.createContext(scope);
stage('launcher-vm-entry');
vm.runInContext(process.argv[1],scope,{timeout:1000});
stage('launcher-vm-complete');
assert.equal(JSON.stringify(scope.window.fixture),'["view","designer"]');
assert.equal(scope.createWorkView,undefined);assert.equal(scope.createWorkDesigner,undefined);
assert.equal(scope.window.createWorkView,undefined);assert.equal(scope.window.createWorkDesigner,undefined);
stage('launcher-assertions-complete');
fs.writeSync(1, 'launcher_assembly_boundary=pass\n');
"""


def run_launcher_assembly_probe(node, source):
    """Keep startup/VM/exit timeouts observable without retrying or hiding failure."""
    # Windows CI 36956218460 exceeded communicate's deadline for the tiny
    # synchronous fixture. That log had no entry evidence, so it cannot tell
    # whether Node startup, the VM, or process/pipe completion stalled. Do not
    # infer a launcher defect or a successful assertion from an absent marker.
    try:
        return subprocess.run([node, "-e", LAUNCHER_ASSEMBLY_PROBE, source.decode("utf-8")],
                              capture_output=True, text=True, encoding="utf-8", timeout=10)
    except subprocess.TimeoutExpired as error:
        stderr = error.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stages = [line for line in stderr.splitlines() if line.startswith("ees_probe=")]
        raise AssertionError(
            "Node launcher probe timed out after 10s; stderr stages: "
            + (", ".join(stages) or "entry not observed")
            + f"; fixture_bytes={len(source)}; fixture_sha256={hashlib.sha256(source).hexdigest()}"
        ) from None


class LauncherProbeDiagnosticsTests(unittest.TestCase):
    def test_timeout_retains_observed_stages_and_never_reports_assertion_success(self):
        source = b"synthetic fixture"
        for stderr in (None, b"ees_probe=launcher-node-entry version=v-test\n"
                       b"ees_probe=launcher-vm-entry\n"):
            with self.subTest(stderr=stderr), mock.patch.object(subprocess, "run") as run:
                run.side_effect = subprocess.TimeoutExpired(["node"], 10, stderr=stderr)
                with self.assertRaises(AssertionError) as raised:
                    run_launcher_assembly_probe("node", source)
                message = str(raised.exception)
                self.assertIn("timed out after 10s", message)
                self.assertIn("fixture_sha256=" + hashlib.sha256(source).hexdigest(), message)
                self.assertIn("launcher-vm-entry" if stderr else "entry not observed", message)
                self.assertNotIn("launcher-assertions-complete", message)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.kwargs["timeout"], 10)
                self.assertEqual(run.call_args.args[0][-1], source.decode("utf-8"))


class CssCacheIntegrityTests(unittest.TestCase):
    def test_accepts_only_reviewed_relative_absolute_and_repeated_icon_urls(self):
        icons = {"v4/721d7.svg": b"reviewed icon"}
        original = (b'.a{background:url("./v4/721d7.svg")}\r\n'
                    b".b{mask:url( '/_ees14/v4/721d7.svg' )}"
                    b'.c{mask:url(./v4/721d7.svg)}'
                    b'.font{src:url("./fonts/unchanged.ttf?v=keep")}\n/* keep */')
        # A fixed fixture digest keeps the successful sample independent of the
        # assertion helper and of the product's URL-rewriting implementation.
        query = b"?v=dd6e48bbcd151debcfa953a8b9d4f7bdb32e6ab0552f57e761268f937a97393f"
        built = original.replace(b"721d7.svg", b"721d7.svg" + query)
        assert_css_icon_cache_keys(self, original, built, icons)
        mutations = {
            "wrong hash": built.replace(query, b"?v=" + b"0" * 64, 1),
            "missing hash": built.replace(query, b"", 1),
            "missing URL": built.replace(b'url("./v4/721d7.svg' + query + b'")', b"none", 1),
            "duplicate query": built.replace(query, query + query, 1),
            "unrelated query": built.replace(b"?v=keep", b"?v=changed"),
            "unrelated bytes": built.replace(b"/* keep */", b"/* changed */"),
            "URL punctuation": built.replace(b"url( '", b"url('", 1),
        }
        for label, corrupted in mutations.items():
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                assert_css_icon_cache_keys(self, original, corrupted, icons)


def assert_workflow_package(test, wheel):
    """Resolve the actual emitted sibling imports/resources and native Tool API."""
    probe = r'''
import asyncio, importlib, importlib.util, json, sys, types
from pathlib import Path
root = Path(sys.argv[1])
# Only the unrelated CLI parent initializer is isolated. All workflow modules
# and migrations below are extracted production-wheel bytes.
package = types.ModuleType("open_webui")
package.__path__ = [str(root / "open_webui")]
sys.modules["open_webui"] = package
workflow = importlib.import_module("open_webui.ees_workflow")
for name in ("ees_workflow", "ees_workflow_definition", "ees_workflow_view", "ees_workflow_authoring",
             "ees_workflow_execution", "ees_workflow_native", "ees_workflow_contract",
             "ees_workflow_workspace", "ees_workflow_operations", "ees_workflow_shared_tools", "ees_workflow_model"):
    module = importlib.import_module("open_webui." + name)
    assert Path(module.__file__).parent == root / "open_webui"
seed = workflow._seed()
assert all(seed[key] == {} for key in ("nodes", "tools", "skills", "sites")), seed
assert all(not values for values in seed["roots"].values())
assert workflow.validate_definition(seed), "An empty catalog is not a publishable procedure"
users = {key: {"id": key, "role": "admin" if key == "admin" else "user"} for key in ("admin", "alice", "bob")}
chats = {"chat-a": {"id": "chat-a", "user_id": "alice"}}
def new_service():
    return workflow.WorkflowService(root / "data" / "ees-work.sqlite3", users.get, chats.get,
                                    group_lookup=lambda _: [], group_list_lookup=lambda: [])
service = new_service()
workflow._service = service
spec = importlib.util.spec_from_file_location("installed_workflow_tool", sys.argv[2])
tool_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool_module)
tool = tool_module.Tools()
assert not hasattr(tool, "ees_workflow_action"), "AI Tool cannot mutate shared work"
events = []
async def event(value):
    events.append(value)
    return {"ok": True, "notified": True}
async def run():
    args = {"__user__": users["alice"], "__metadata__": {"chat_id": "chat-a"}}
    empty = await tool.ees_workflow_view(**args)
    assert empty["ok"] and empty["workflows"] == [] and empty["runs"] == [], empty
    assert not empty["capabilities"]["can_author"]
    ui_state = await service.workspace_state(users["alice"])
    source_help = json.loads((root / "open_webui/workflow_help.json").read_text(encoding="utf-8"))
    assert ui_state["help"]["terms"][0]["summary"] == source_help["terms"][0]["summary"]
    assert "도움말에 없는 내용" in ui_state["help"]["answer_guidance"]["unknown"]
    examples = json.loads((root / "open_webui/workflow_tool_examples.json").read_text(encoding="utf-8"))
    assert len(examples) == 4
    procedure_source = (root / "open_webui/workflow_procedure_examples.json").read_bytes()
    procedures = json.loads(procedure_source)
    summaries = ui_state["procedure_examples"]
    assert {item["id"] for item in procedures} == {item["id"] for item in summaries}
    assert {item["id"]: (item["stage_count"], item["job_count"]) for item in summaries} == {
        "delivery_review": (4, 9), "factory_rollout": (4, 6), "daily_check": (1, 1)}
    assert all("definition" not in item for item in summaries)
    # This is an emitted-package persistence contract, not an HTTP approval
    # test. Arrange explicit synthetic work through the internal service;
    # the LLM-visible Tool only reads or offers a local review proposal.
    grant = await service.workspace_command(users["admin"], {"action": "save_access", "request_id": "grant", "expected_revision": 0,
        "principal_kind": "user", "principal_id": "alice", "system_id": "EMS", "factory_id": "*", "roles": ["manager", "participant"]})
    assert grant["ok"], grant
    created = await service.workspace_command(users["alice"], {"action": "create_workflow", "request_id": "create", "expected_revision": 0, "system_id": "EMS", "name": "Synthetic packaged contract"})
    assert created["ok"], created
    key = created["workflow_id"]
    draft = created["workflow"]["draft"]
    draft["name"] = "Persisted packaged contract"
    command = {"action": "save_draft", "request_id": "save", "workflow_id": key, "expected_revision": 1, "definition": draft}
    saved = await service.workspace_command(users["alice"], command)
    assert saved["ok"], saved
    assert await service.workspace_command(users["alice"], command) == saved
    stale = await service.workspace_command(users["alice"], dict(command, request_id="stale"))
    assert stale["error"]["code"] == "revision_conflict", stale
    seen = await tool.ees_workflow_view(workflow_id=key, **args)
    assert seen["workflow"]["draft"] == draft and seen["workflow"]["revision"] == 2, seen
    assert "ui_state" not in seen and "access" not in seen
    denied = await tool.ees_workflow_view(workflow_id=key, __user__=users["bob"])
    assert not denied["ok"], denied
    before = service.database.read_bytes()
    proposal = await tool.ees_workflow_propose(key, 2, draft, "packaged-context", __event_call__=event, **args)
    assert proposal["ok"] and proposal["saved"] is False and proposal["published"] is False, proposal
    assert len(events) == 1 and "api?.propose" in events[0]["data"]["code"]
    assert service.database.read_bytes() == before
    workflow._service = new_service()
    restored = await tool.ees_workflow_view(workflow_id=key, **args)
    assert restored["workflow"] == seen["workflow"], restored
    retired = await workflow.handle_action(users["alice"], {"action": "create_case"})
    assert not retired["ok"] and retired["error"]["code"] == "legacy_execution_retired", retired
    assert not (root / ".webui_secret_key").exists()
    assert not (root / "data" / "webui.db").exists()
    assert (root / "open_webui/workflow_procedure_examples.json").read_bytes() == procedure_source
asyncio.run(run())
print("installed_workflow_contract=pass")
'''
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with ZipFile(wheel) as archive:
            retired = {"open_webui/ees_work_demo.py", "open_webui/workflow_seed.json",
                       "open_webui/ees_workflow_examples.py", "open_webui/frontend/_ees14/ees-work-panel.js"}
            test.assertFalse(retired.intersection(archive.namelist()))
            test.assertFalse(any(name.startswith("open_webui/ees_work_demo_ui/") for name in archive.namelist()))
            test.assertEqual(archive.read("open_webui/ees_workflow_tool.py"),
                             (builder.WORK_DIR / "scripts/workflow_tool.py").read_bytes())
            for name in ("workflow_help.json", "workflow_tool_examples.json", "workflow_procedure_examples.json"):
                test.assertEqual(archive.read("open_webui/" + name),
                                 (builder.WORK_DIR / "scripts" / name).read_bytes())
            for name in ("ees_workflow.py", "ees_workflow_definition.py", "ees_workflow_view.py", "ees_workflow_authoring.py",
                         "ees_workflow_execution.py", "ees_workflow_native.py", "ees_workflow_contract.py",
                         "ees_workflow_workspace.py", "ees_workflow_operations.py", "ees_workflow_shared_tools.py", "ees_workflow_model.py",
                         "ees_workflow_tool.py", "workflow_policy.json", "workflow_help.json", "workflow_tool_examples.json",
                         "workflow_procedure_examples.json"):
                target = root / "open_webui" / name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(archive.read("open_webui/" + name))
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning",
             "-c", probe, str(root), str(root / "open_webui/ees_workflow_tool.py")],
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
    for provider in ("openai", "ollama"):
        members["open_webui/routers/" + provider + ".py"] += (
            b"async def generate_chat_completion(request, form_data=None, user=None):\n"
            b"    model_info = await Models.get_model_by_id(form_data['model'])\n"
            b"    if model_info:\n        params = model_info.params.model_dump()\n"
            b"        return apply_model_params(params, form_data)\n")
    # Keep both reviewed program-owned fallback branches and the custom-image
    # branch distinct, as in the official model-image route. No user metadata
    # is rewritten by this fixture or by the guarded branding replacements.
    members["open_webui/routers/models.py"] = b"""router = APIRouter()
async def get_model_image(image_url=None, media_type=None):
    if image_url:
        if image_url.startswith('data:'):
            if media_type not in PROFILE_IMAGE_ALLOWED_MIME_TYPES:
                return RedirectResponse(
                    url='/static/favicon.png',
                    status_code=status.HTTP_302_FOUND,
                )
        elif image_url.startswith('/static/'):
            safe_static = image_url
            return RedirectResponse(url=safe_static, status_code=status.HTTP_302_FOUND)
    return RedirectResponse(
        url='/static/favicon.png',
        status_code=status.HTTP_302_FOUND,
    )
"""
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
        app + "immutable/entry/start.js": b'import "../chunks/untouched.js";',
        app + "immutable/chunks/untouched.js": b'const oldFrontend = "original upstream";',
        app + "version.json": b'{"version":"0.11.3"}',
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
    # Minimal pinned control-flow boundaries; assertions below verify policy
    # ordering, pre-persistence checks, and both Native dispatch paths.
    members["open_webui/main.py"] += b"""
async def chat_completion(request, form_data, user):
    try:
        metadata = {}
        if is_new_chat:
            metadata['chat_id'] = str(uuid4())
        await Chats.insert_new_chat(user.id, {
                                'models': [entry['model_id'] for entry in message_ids],
        })
        if existing_chat:
            if valid:
                if owner:
                    if chat_fields:
                        await Chats.update_chat_by_id(chat_id, chat_fields, touch=False)
        await Chats.upsert_message_to_chat_by_id_and_message_id(chat_id, user_message_id, user_message)
    except HTTPException:
        raise
    async def process_chat(request, form_data, user, metadata, model, tasks=None):
        try:
            form_data, metadata, events = await process_chat_payload(request, form_data, user, metadata, model)
            response = await chat_completion_handler(request, form_data, user)
        finally:
            if (
                    chat_id
                    and getattr(request.state, 'internal', False) is not True
            ):
                await process_pending_internal_messages(request, chat_id, user.id, {})
"""
    members["open_webui/utils/middleware.py"] = b"""async def process_chat_payload(request, form_data, user, metadata, model):
    if is_saved_chat_id(chat_id) and user_message_id:
        if db_messages:
            for message in form_data['messages']:
                if message.get('role') == 'user' and image_files:
                    message['content'] = image_files
    if is_saved_chat_id(chat_id) and user_message_id:
        if getattr(request.state, 'direct', False):
            compaction_models = models
        await compact_messages_for_request(request)
    form_data = await convert_url_images_to_base64(form_data, user=user)
    if folder_id and user:
        folder = await get_folder(folder_id)
    if model_knowledge and metadata.get('params', {}).get('function_calling') == 'legacy':
        await read_model_knowledge(model_knowledge)
    payload_tools = form_data.get('tools', None)
    form_data = await process_pipeline_inlet_filter(request, form_data, user, models)
    filter_functions = await get_filter_functions(request, model, metadata.get('filter_ids', []))
    form_data, flags = await process_filter_functions(request, form_data=form_data)
    features = form_data.pop('features', None) or {}
    await handle_features(features)
    tool_ids = form_data.pop('tool_ids', None)
    skill_ids = list(set(selected_skill_ids) | set(model_skill_ids))
    available_skills = []
    tools_dict = {}
    if payload_tools is None:
        if tool_ids:
            tools_dict = await get_tools(request, tool_ids, user, {})
            if mcp_tools_dict:
                tools_dict.update(mcp_tools_dict)
        if use_builtin_tools:
            form_data['messages'] = await add_file_context(form_data.get('messages', []), chat_id, user)
            tools_dict.update(await get_builtin_tools(request))
        if tools_dict:
            metadata['tools'] = tools_dict
    if file_context_enabled:
        await read_files(form_data)
    if model_knowledge:
        await read_model_knowledge(model_knowledge)
    return form_data, tools_dict

async def execute_tool_call_for_output(request, form_data, user, metadata):
    tools = metadata.get('tools', {})
    await tools[function_name]['callable'](**params)

async def process_chat_response(request, form_data, user, metadata):
    if response:
        async def stream():
            try:
                if tool_calls:
                    tools = metadata.get('tools', {})
                    if tools:
                        new_form_data = await process_filter_functions(request, form_data=form_data)
                        res = await generate_chat_completion(
                            request, new_form_data, user)
                        if pending:
                            new_form_data = await process_filter_functions(request, form_data=form_data)
                            res = await generate_chat_completion(
                                request, new_form_data, user)
            finally:
                await finish()
"""
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
    test.assertIn("await check_chat_work_tool(request, user, tool)", loader_text)
    middleware = built.read("open_webui/utils/middleware.py").decode()
    ast.parse(middleware)
    test.assertIn("EES_WORK_NATIVE_CHAT_CONTEXT = 1", middleware)
    test.assertLess(middleware.index("await select_chat_work_tools"), middleware.index("await get_tools("))
    test.assertGreater(middleware.index("wrap_chat_work_tools(request, user, tools_dict)"), middleware.index("await get_tools("))
    test.assertGreater(middleware.index("wrap_chat_work_tools(request, user, tools_dict)"), middleware.index("await get_builtin_tools("))
    test.assertLess(middleware.index("wrap_chat_work_tools(request, user, tools_dict)"), middleware.index("metadata['tools'] = tools_dict"))
    test.assertIn("explicit_tools=payload_tools is not None", middleware)
    test.assertLess(middleware.index("await process_filter_functions"), middleware.index("await enforce_chat_work_help"))
    test.assertLess(middleware.index("await enforce_chat_work_help"), middleware.index("features = form_data.pop"))
    test.assertEqual(middleware.count("dispatch=True)"), 4)
    test.assertIn("get_filter_functions(request, model, metadata.get('filter_ids', []))", middleware)
    for boundary in ("if folder_id and user", "if file_context_enabled", "if use_builtin_tools", "if model_knowledge"):
        for line in middleware.splitlines():
            if line.lstrip().startswith(boundary):
                test.assertIn("ees_work_help_protocol", line)
    test.assertIn("if getattr(request.state, 'ees_work_help_protocol', None) == 1:\n        skill_ids = []", middleware)

    main = built.read("open_webui/main.py").decode()
    test.assertLess(main.index("await prepare_chat_work_help"), main.index("await Chats.insert_new_chat"))
    test.assertLess(main.index("await prepare_chat_work_help"), main.index("await Chats.upsert_message_to_chat_by_id_and_message_id"))
    test.assertLess(main.index("await enforce_chat_work_help"), main.index("await chat_completion_handler"))
    test.assertIn("and getattr(request.state, 'ees_work_help_protocol', None) != 1", main)
    test.assertIn("if chat_fields and getattr(request.state, 'ees_work_help_protocol', None) != 1:", main)
    test.assertIn("'models': getattr(request.state, 'ees_work_help_composer_models', None)", main)
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
            (self.ui / name).parent.mkdir(parents=True, exist_ok=True)
            (self.ui / name).write_bytes(b"reviewed UI asset " + name.encode())
        for name, content in {
            "ees-work-view.js": b"function createWorkView() { return 'view'; }\n",
            "ees-work-designer.js": b"function createWorkDesigner() { return 'designer'; }\n",
            "ees-work-launcher.js": b"(() => { window.fixture = [createWorkView(), createWorkDesigner()]; })();\n",
        }.items():
            (self.ui / name).write_bytes(content)
        self.frontend_dir = self.root / "source-frontend"
        self.frontend_dir.mkdir()
        self.frontend_files = None
        self.members = fixture_members()
        self.guard_hashes = {name: hashlib.sha256(self.members[name]).hexdigest()
                             for name in builder.ASSET_GUARD_SOURCE_HASHES}
        self.write_fixture()
        self.prepare_frontend()

    def write_fixture(self):
        with ZipFile(self.wheel, "w") as archive:
            for name, content in self.members.items():
                archive.writestr(name, content)
        self.source_hash = builder.sha256_file(self.wheel)

    def prepare_frontend(self):
        """Synthetic validated bytes isolate packing from the source compiler.

        Provenance verification, patch application and source-hook behavior run
        in test_ees_frontend_build; the optional real-wheel audit below invokes
        that real validator. This fixture never claims to be a Native build.
        """
        app_dir = builder.PROGRAM_FRONTENDS[builder.VERSION]
        links = []
        for filename in ("chat-theme.css", "ees-work-launcher.css", "ees-work-launcher.js"):
            content = (builder.assemble_work_launcher(self.ui) if filename.endswith(".js")
                       else (self.ui / filename).read_bytes())
            if filename.endswith(".css"):
                for relative in builder.V4_ICON_FILES:
                    digest = hashlib.sha256((self.ui / relative).read_bytes()).hexdigest().encode("ascii")
                    for url in (("/" + app_dir + "/" + relative).encode("ascii"), ("./" + relative).encode("ascii")):
                        content = content.replace(url, url + b"?v=" + digest)
            digest = hashlib.sha256(content).hexdigest()
            links.append('<link href="/' + app_dir + '/' + filename + '?v=' + digest + '" />')
        self.frontend_files = {
            "index.html": ('<!-- LICENSE synthetic source build -->\n<title>EES Workflow</title>\n'
                '<link href="/static/custom.css" />\n' + "\n".join(links)
                + '\n<script src="/' + app_dir + '/immutable/entry/start.source.js"></script>\n</head>\n').encode(),
            app_dir + "/version.json": json.dumps({"version": builder.VERSION}).encode(),
            app_dir + "/immutable/entry/start.source.js": b'import "../chunks/a.source.js";\n//# sourceMappingURL=start.source.js.map',
            app_dir + "/immutable/entry/start.source.js.map": b'{"sourcesContent":["Open WebUI / exact source map"]}',
            app_dir + "/immutable/chunks/a.source.js": b'import "./b.source.js"; export const original = "Open WebUI";',
            app_dir + "/immutable/chunks/b.source.js": b'import "./a.source.js"; export const unchanged = 1;',
            "static/custom.css": b"/* original frontend style stays intact */\n",
            "favicon.png": (self.assets / "favicon.png").read_bytes(),
            **{"static/" + name: (self.assets / name).read_bytes() for name in builder.ASSET_NAMES},
        }
        self.write_frontend_manifest()

    def write_frontend_manifest(self):
        self.frontend_manifest = {
            "schema": 1, "mode": "ees", "upstream_commit": "2a960a59fe1dbbd35282f0556b3666d81102e781",
            "version": builder.VERSION, "app_dir": builder.PROGRAM_FRONTENDS[builder.VERSION],
            "source_inputs": {"synthetic-packing-unit-fixture": "f" * 64},
            "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(self.frontend_files.items())},
        }
        (self.frontend_dir / "manifest.json").write_text(json.dumps(self.frontend_manifest), encoding="utf-8")

    def build(self, directory="release", *, refresh_frontend=True):
        fonts = {name: (origin, hashlib.sha256(b"unchanged upstream font " + name.encode()).hexdigest())
                 for name, (origin, _) in builder.FONT_SOURCES.items()}
        # Do not run the compiler for synthetic packaging fixtures. The real
        # validator is exercised independently and in OfficialWheelTests.
        from scripts import build_ees_frontend
        with (mock.patch.object(builder, "SOURCE_SHA256", self.source_hash),
              mock.patch.object(builder, "FONT_SOURCES", fonts),
              mock.patch.object(builder, "ASSET_GUARD_SOURCE_HASHES", self.guard_hashes)):
            if refresh_frontend:
                try:
                    self.prepare_frontend()
                except (OSError, ValueError):
                    # A broken authored asset cannot be compiled. Retain the
                    # last fixture so the real packer must reject that asset.
                    # Do not call or mock its validation guards here.
                    pass
            with mock.patch.object(build_ees_frontend, "validate_frontend", return_value=self.frontend_files) as validate:
                result = builder.build(self.wheel, self.root / directory, self.assets, self.ui,
                                       frontend_dir=self.frontend_dir)
                validate.assert_called_once_with(self.frontend_dir, mode="ees")
                return result

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

    def test_manifest_byte_budget_preserves_nested_inventory_before_publication(self):
        from scripts import ees_deploy_release as release
        self.assertEqual(builder.MAX_MANIFEST_BYTES, release.MAX_JSON_BYTES)
        self.assertEqual(builder.MAX_MANIFEST_BYTES, 1024 * 1024)
        self.frontend_manifest["note"] = "한" + "x" * 1000000
        manifest_path = self.frontend_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self.frontend_manifest, ensure_ascii=False), encoding="utf-8")
        measured = self.build("measure-limit", refresh_frontend=False)
        size = (self.root / "measure-limit" / "manifest.json").stat().st_size
        self.frontend_manifest["note"] += "x" * (builder.MAX_MANIFEST_BYTES - size)
        manifest_path.write_text(json.dumps(self.frontend_manifest, ensure_ascii=False), encoding="utf-8")
        expected = self.build("at-limit", refresh_frontend=False)
        raw = (self.root / "at-limit" / "manifest.json").read_bytes()
        self.assertEqual(len(raw), builder.MAX_MANIFEST_BYTES)
        self.assertEqual(release._json(raw), expected)
        self.assertEqual(expected["source_frontend"], self.frontend_manifest)
        self.assertEqual(expected["changed_files"], measured["changed_files"])
        assert_record(self, self.root / "at-limit" / builder.WHEEL_FILENAME)
        self.frontend_manifest["note"] += "x"
        manifest_path.write_text(json.dumps(self.frontend_manifest, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Branding manifest exceeds"):
            self.build("over-limit", refresh_frontend=False)
        self.assertEqual(list((self.root / "over-limit").iterdir()), [])

    def test_added_figma_icons_are_packaged_and_missing_source_fails_closed(self):
        # Independent approved Figma inventory: do not derive the expectation
        # from the builder list whose omission caused the original failure.
        added = ('1c98e', '35b2e', '478bf', '52271', '63982',
                 '6d84b', 'a28e3', 'b22ad', 'b456d', 'f1e53',
                 'f4cb1', '3dae2', 'e9ac2', '30679', '2b3d1',
                 '1a06f', '2fe77', '2eb05', 'b355c', '66c71', '45242',
                 '83565', '54b2e', '4d978', '4308e', 'f17e6')
        self.build('figma-icons')
        with ZipFile(self.root / 'figma-icons' / builder.WHEEL_FILENAME) as archive:
            for name in added:
                relative = 'v4/' + name + '.svg'
                self.assertIn(relative, builder.UI_FILES)
                self.assertEqual(archive.read(builder.TARGET_APP + relative),
                                 (self.ui / relative).read_bytes())
        assert_record(self, self.root / 'figma-icons' / builder.WHEEL_FILENAME)
        for name in added:
            with self.subTest(icon=name):
                source = self.ui / ('v4/' + name + '.svg')
                original = source.read_bytes()
                source.unlink()
                try:
                    with self.assertRaises(ValueError):
                        self.build('missing-' + name)
                    self.assertFalse((self.root / ('missing-' + name)).exists())
                finally:
                    source.write_bytes(original)

    def test_same_version_ui_change_updates_only_its_content_cache_key(self):
        first = self.build("before")
        source = self.ui / "ees-work-designer.js"
        source.write_text(source.read_text(encoding="utf-8") + "\n// revised designer\n", encoding="utf-8")
        second = self.build("after")
        self.assertEqual(first["version"], second["version"])
        with (ZipFile(self.root / "before" / builder.WHEEL_FILENAME) as before,
              ZipFile(self.root / "after" / builder.WHEEL_FILENAME) as after):
            indexes = [archive.read("open_webui/frontend/index.html") for archive in (before, after)]
            for filename in ("ees-work-launcher.css", "ees-work-launcher.js"):
                digests = [hashlib.sha256(archive.read(builder.TARGET_APP + filename)).hexdigest()
                           for archive in (before, after)]
                for index, digest in zip(indexes, digests):
                    self.assertIn(("/_ees14/" + filename + "?v=" + digest).encode("ascii"), index)
                self.assertEqual(digests[0] == digests[1], filename != "ees-work-launcher.js")
            self.assertEqual(before.read(builder.TARGET_INFO + "METADATA"),
                             after.read(builder.TARGET_INFO + "METADATA"))

    def test_v4_icon_hash_updates_dynamic_map_and_relative_and_absolute_css_urls(self):
        relative = builder.V4_ICON_FILES[0]
        name = Path(relative).name
        (self.ui / "ees-work-view.js").write_text('function createWorkView() { return "' + name + '"; }\n', encoding="utf-8")
        (self.ui / "ees-work-launcher.css").write_text('.relative{background:url("./' + relative + '")} .absolute{background:url("/_ees14/' + relative + '")}', encoding="utf-8")
        hashes = []
        for directory in ("icon-before", "icon-after"):
            if directory == "icon-after":
                with (self.ui / relative).open("ab") as icon:
                    icon.write(b" changed icon")
            digest = hashlib.sha256((self.ui / relative).read_bytes()).hexdigest()
            hashes.append(digest)
            self.build(directory)
            with ZipFile(self.root / directory / builder.WHEEL_FILENAME) as archive:
                source = archive.read(builder.TARGET_APP + "ees-work-launcher.js")
                css = archive.read(builder.TARGET_APP + "ees-work-launcher.css")
                self.assertIn((name + "?v=" + digest).encode(), source)
                self.assertIn(("./" + relative + "?v=" + digest).encode(), css)
                self.assertIn(("/_ees14/" + relative + "?v=" + digest).encode(), css)
                self.assertNotIn(b"?v=" + digest.encode() + b"?v=", css)
                assert_css_icon_cache_keys(self, (self.ui / "ees-work-launcher.css").read_bytes(),
                                           css, {relative: (self.ui / relative).read_bytes()})
        self.assertNotEqual(*hashes)

    def test_source_built_cyclic_modules_and_source_maps_are_copied_without_rewriting(self):
        self.prepare_frontend()
        app_dir = builder.PROGRAM_FRONTENDS[builder.VERSION]
        original = dict(self.frontend_files)
        self.build("before", refresh_frontend=False)
        changed = app_dir + "/immutable/chunks/a.source.js"
        self.frontend_files[changed] += b"\n// revised source output\n"
        self.write_frontend_manifest()
        second = self.build("after", refresh_frontend=False)
        with (ZipFile(self.root / "before" / builder.WHEEL_FILENAME) as before,
              ZipFile(self.root / "after" / builder.WHEEL_FILENAME) as after):
            for relative, content in original.items():
                name = "open_webui/frontend/" + relative
                self.assertEqual(before.read(name), content)
                self.assertEqual(after.read(name), self.frontend_files[relative])
                if relative != changed:
                    self.assertEqual(before.read(name), after.read(name))
            self.assertFalse(any(name.startswith(builder.SOURCE_APP) for name in after.namelist()))
        self.assertEqual(second["source_frontend"], self.frontend_manifest)
        assert_record(self, self.root / "after" / builder.WHEEL_FILENAME)

    def test_frontend_is_required_and_runtime_hash_mismatch_fails_before_output(self):
        self.prepare_frontend()
        # A previously validated source build becomes unusable if its runtime
        # assets change. Repacking may not silently edit compiled HTML to hide it.
        (self.ui / "ees-work-designer.js").write_bytes(b"function createWorkDesigner() { return 'changed'; }\n")
        with self.assertRaisesRegex(ValueError, "runtime asset hash differs"):
            self.build("stale", refresh_frontend=False)
        self.assertFalse((self.root / "stale").exists())
        with mock.patch.object(builder, "SOURCE_SHA256", self.source_hash), \
                mock.patch.object(builder, "prepare_replacements", return_value={}), \
                mock.patch.object(builder, "prepare_additions", return_value={}):
            with self.assertRaisesRegex(ValueError, "source frontend is required"):
                builder.build(self.wheel, self.root / "missing-frontend")
        self.assertFalse((self.root / "missing-frontend").exists())

    def test_source_frontend_asset_overlap_or_missing_target_is_rejected(self):
        cases = ((builder.PROGRAM_FRONTENDS[builder.VERSION] + "/ees-work-launcher.js", "overlaps"),
                 ("static/favicon.svg", "Missing source-built static branding"),
                 ("favicon.png", "Missing or mismatched source-built favicon"))
        for relative, reason in cases:
            with self.subTest(relative=relative):
                self.prepare_frontend()
                if "overlaps" == reason:
                    self.frontend_files[relative] = b"unreviewed duplicate runtime"
                else:
                    del self.frontend_files[relative]
                self.write_frontend_manifest()
                with self.assertRaisesRegex(ValueError, reason):
                    self.build("bad-source-frontend", refresh_frontend=False)
                self.assertFalse((self.root / "bad-source-frontend").exists())

    def test_source_frontend_branding_mismatch_is_not_silently_rewritten(self):
        for relative in ("static/favicon.svg", "favicon.png"):
            with self.subTest(relative=relative):
                self.prepare_frontend()
                self.frontend_files[relative] = b"stale source-built branding"
                self.write_frontend_manifest()
                with self.assertRaisesRegex(ValueError, "branding differs|mismatched source-built favicon"):
                    self.build("bad-branding", refresh_frontend=False)
                self.assertFalse((self.root / "bad-branding").exists())

    def test_frontend_validator_failure_cannot_publish_a_wheel(self):
        from scripts import build_ees_frontend
        with mock.patch.object(builder, "SOURCE_SHA256", self.source_hash), \
                mock.patch.object(builder, "prepare_replacements", return_value={}), \
                mock.patch.object(builder, "prepare_additions", return_value={}), \
                mock.patch.object(build_ees_frontend, "validate_frontend", side_effect=ValueError("provenance differs")) as validate:
            with self.assertRaisesRegex(ValueError, "provenance differs"):
                builder.build(self.wheel, self.root / "untrusted", frontend_dir=self.frontend_dir)
            validate.assert_called_once_with(self.frontend_dir, mode="ees")
        self.assertFalse((self.root / "untrusted").exists())

    def test_theme_content_change_gets_new_url_without_readdressing_native_modules(self):
        first = self.build("before")
        source = self.ui / "chat-theme.css"
        source.write_bytes(source.read_bytes() + b"\n/* revised shell */\n")
        second = self.build("after")
        self.assertEqual(first["version"], second["version"])
        digests = []
        for directory in ("before", "after"):
            with ZipFile(self.root / directory / builder.WHEEL_FILENAME) as archive:
                digest = hashlib.sha256(archive.read(builder.TARGET_APP + "chat-theme.css")).hexdigest()
                digests.append(digest)
                self.assertIn(("/_ees14/chat-theme.css?v=" + digest).encode("ascii"),
                              archive.read("open_webui/frontend/index.html"))
        self.assertNotEqual(*digests)

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
            result = run_launcher_assembly_probe(shutil.which("node"), source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "launcher_assembly_boundary=pass")
            self.assertIn("ees_probe=launcher-assertions-complete", result.stderr)

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

    def test_only_reviewed_backend_changes_and_whole_source_frontend_are_packaged(self):
        manifest = self.build()
        prefix = "open_webui/frontend/"
        self.assertFalse(any(name.startswith(prefix) for name in builder.PATCHES),
                         "Compiled frontend substitutions must not return")
        self.assertEqual(manifest["source_frontend"], self.frontend_manifest)
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            self.assertFalse(any(name.startswith(builder.SOURCE_APP) for name in built.namelist()))
            for name, original in self.members.items():
                if name.startswith(prefix):
                    continue
                target = builder.target_name(name)
                if target not in manifest["changed_files"]:
                    self.assertEqual(built.read(target), original, name)
            for relative, content in self.frontend_files.items():
                self.assertEqual(built.read(prefix + relative), content, relative)
            self.assertEqual(built.read(builder.TARGET_INFO + "licenses/LICENSE"), LICENSE)
            self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                             self.members[builder.SOURCE_INFO + "METADATA"].replace(b"Version: 0.11.3\n", ("Version: " + builder.VERSION + "\n").encode()))
            self.assertEqual(built.read("open_webui/env.py").count(NOTICE), 2)
            self.assertNotIn(b"WEBUI_NAME +=", built.read("open_webui/env.py"))
            main = built.read("open_webui/main.py")
            self.assertLess(main.index(b"install_ees_workflow(app, get_verified_user)"), main.index(b"app.mount"))
            for relative, target in builder.WORK_ASSETS.items():
                self.assertEqual(built.read(target), (builder.WORK_DIR / relative).read_bytes())
                self.assertFalse(target.startswith(prefix))
            for name, relative in builder.UI_FILES.items():
                expected = (builder.assemble_work_launcher(self.ui) if name == "ees-work-launcher.js"
                            else (self.ui / name).read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + relative), expected)
            self.assertNotIn(builder.TARGET_APP + "ees-work-view.js", built.namelist())
            self.assertNotIn(builder.TARGET_APP + "ees-work-designer.js", built.namelist())
            for name, (origin, _) in builder.FONT_SOURCES.items():
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/" + name), self.members[origin])
            self.assertEqual(json.loads(built.read(builder.TARGET_APP + "version.json"))["version"], builder.VERSION)
            for image_prefix in ("open_webui/static/", prefix + "static/"):
                for name in builder.ASSET_NAMES:
                    self.assertEqual(built.read(image_prefix + name), (self.assets / name).read_bytes())
        assert_record(self, self.root / "release" / builder.WHEEL_FILENAME)

    def test_asset_guard_inventory_and_emitted_lifecycle_cache_order(self):
        self.assertEqual(GUARD_METHODS, builder.ASSET_GUARD_HOOKS)
        self.assertEqual(set(GUARD_METHODS) | {"open_webui/main.py", "open_webui/routers/tools.py", "open_webui/routers/models.py", "open_webui/utils/tools.py", "open_webui/utils/middleware.py"},
                         set(builder.ASSET_GUARD_SOURCE_HASHES))
        self.assertEqual(16, len(builder.ASSET_GUARD_SOURCE_HASHES))
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
                with self.assertRaisesRegex(ValueError, "EES Workflow asset"):
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
        for registered, expected in ((None, "EES Workflow"), ("EES Assistant", "EES Workflow"),
                                     ("EES Portal", "EES Workflow"), ("EES Work", "EES Workflow"),
                                     ("EES Workflow", "EES Workflow"), ("Team Custom", "Team Custom")):
            with self.subTest(registered=registered):
                environment = {} if registered is None else {"WEBUI_NAME": registered}
                with mock.patch.dict(os.environ, environment, clear=True):
                    namespace = {"os": os}
                    exec(synthetic_env, namespace)
                    self.assertEqual(namespace["WEBUI_NAME"], expected)
                    self.assertEqual(dict(os.environ), environment)




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
        cases = (("css", "EES UI asset"), ("license", "EES UI asset"), ("brand", "EES UI asset"),
                 ("font", "font hash differs"), ("missing-font", "Missing pinned upstream font"),
                 ("collision", "already contains an EES UI target"))
        for mode, error in cases:
            with self.subTest(mode=mode):
                self.setUp()
                origin = next(iter(builder.FONT_SOURCES.values()))[0]
                if mode in {"css", "license", "brand"}:
                    names = {"css": "chat-theme.css", "license": "font-licenses.txt", "brand": "brand-layers.svg"}
                    (self.ui / names[mode]).unlink()
                elif mode == "font":
                    self.members[origin] += b"changed"
                elif mode == "missing-font":
                    del self.members[origin]
                else:
                    self.members[builder.TARGET_APP + "chat-theme.css"] = b"unexpected upstream target"
                self.write_fixture()
                with self.assertRaisesRegex(ValueError, error):
                    self.build()
                self.assertFalse((self.root / "release").exists())


@unittest.skipUnless(os.environ.get("EES_TEST_UPSTREAM_WHEEL") and os.environ.get("EES_TEST_FRONTEND_DIR"),
                     "Set EES_TEST_UPSTREAM_WHEEL and EES_TEST_FRONTEND_DIR for the offline official wheel audit.")
class OfficialWheelTests(unittest.TestCase):

    def test_real_pinned_wheel_patches_records_and_unrelated_content(self):
        source_path = Path(os.environ["EES_TEST_UPSTREAM_WHEEL"])
        with tempfile.TemporaryDirectory() as temporary:
            manifest = builder.build(source_path, temporary, frontend_dir=Path(os.environ["EES_TEST_FRONTEND_DIR"]))
            built_path = Path(temporary) / builder.WHEEL_FILENAME
            assert_record(self, built_path)
            with ZipFile(source_path) as source, ZipFile(built_path) as built:
                assert_asset_guard_patches(self, built)
                self.assertEqual(built.read(builder.ASSET_GUARD_FILES[0]), builder.ASSET_GUARD_SOURCE.read_bytes())
                changed = set(manifest["changed_files"])
                for name in source.namelist():
                    if name.startswith("open_webui/frontend/"):
                        continue
                    target = builder.target_name(name)
                    if target not in changed:
                        self.assertEqual(built.read(target), source.read(name), name)
                metadata = source.read(builder.SOURCE_INFO + "METADATA")
                self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                                 metadata.replace(b"\nVersion: 0.11.3\n", ("\nVersion: " + builder.VERSION + "\n").encode()))
                for filename, (origin, expected) in builder.FONT_SOURCES.items():
                    copied = built.read(builder.TARGET_APP + "fonts/" + filename)
                    self.assertEqual(copied, source.read(origin))
                    self.assertEqual(hashlib.sha256(copied).hexdigest(), expected)
                # Independently reviewed CSS references, not the builder's icon
                # list or prepared output. The C18 menu masks and E1 chevron use
                # CSS URLs; font URLs and bytes outside icon values must survive.
                # The independent fixed/mutated URL fixtures above still verify
                # allowed rewriting, wrong/missing hashes and unrelated drift.
                for filename, references in {
                    "chat-theme.css": (),
                    "ees-work-launcher.css": (
                        "v4/83565.svg", "v4/54b2e.svg", "v4/4d978.svg", "v4/4308e.svg", "v4/f0554.svg", "v4/f17e6.svg",
                    ),
                }.items():
                    icons = {relative: (builder.UI_DIR / relative).read_bytes() for relative in references}
                    for relative, content in icons.items():
                        self.assertEqual(built.read(builder.TARGET_APP + relative), content)
                    assert_css_icon_cache_keys(self, (builder.UI_DIR / filename).read_bytes(),
                                               built.read(builder.TARGET_APP + filename), icons)
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/LICENSE.txt"),
                                 (builder.UI_DIR / "font-licenses.txt").read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + "ees-work-launcher.js"),
                                 builder.assemble_work_launcher())
                # The complete frontend is the validated compiler output;
                # original frontend file counts and minified offsets are not
                # packaging invariants after a source rebuild.
                from scripts.build_ees_frontend import validate_frontend
                frontend = validate_frontend(Path(os.environ["EES_TEST_FRONTEND_DIR"]))
                for relative, content in frontend.items():
                    self.assertEqual(built.read("open_webui/frontend/" + relative), content, relative)
                for name in ("open_webui/env.py",):
                    self.assertEqual(source.read(name).count(b"LICENSE"), built.read(name).count(b"LICENSE"))
            assert_workflow_package(self, built_path)


if __name__ == "__main__":
    unittest.main()
