"""Package the verified source-built frontend with the pinned official Python wheel.

Requires only Python's standard library. No network, credentials, runtime data,
dependency resolution, or upstream code execution is involved. Branding use must
meet the upstream license; this builder preserves every bundled license notice.
"""

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo


UPSTREAM_VERSION = "0.11.3"
VERSION = "0.11.3+ees.14"
SOURCE_FRONTEND_REQUIRED = True
MAX_MANIFEST_BYTES = 1024 * 1024
PROGRAM_FRONTENDS = {"0.11.3+ees.1": "_ees1", "0.11.3+ees.2": "_ees2", "0.11.3+ees.3": "_ees3", "0.11.3+ees.4": "_ees4", "0.11.3+ees.5": "_ees5", "0.11.3+ees.6": "_ees6", "0.11.3+ees.7": "_ees7", "0.11.3+ees.8": "_ees8", "0.11.3+ees.9": "_ees9", "0.11.3+ees.10": "_ees10", "0.11.3+ees.11": "_ees11", "0.11.3+ees.12": "_ees12", "0.11.3+ees.13": "_ees13", "0.11.3+ees.14": "_ees14"}
SOURCE_FILENAME = "open_webui-0.11.3-py3-none-any.whl"
SOURCE_SHA256 = "8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547"
WHEEL_FILENAME = f"open_webui-{VERSION}-py3-none-any.whl"
SOURCE_INFO = f"open_webui-{UPSTREAM_VERSION}.dist-info/"
TARGET_INFO = f"open_webui-{VERSION}.dist-info/"
SOURCE_APP = "open_webui/frontend/_app/"
TARGET_APP = "open_webui/frontend/_ees14/"
ASSET_DIR = Path(__file__).resolve().parents[1] / "branding" / "ees" / "assets"
UI_DIR = ASSET_DIR.parent / "ui"
ASSET_NAMES = (
    "favicon.svg", "favicon.png", "favicon-96x96.png", "favicon.ico",
    "apple-touch-icon.png", "logo.png", "splash.png", "splash-dark.png",
)
UI_FILES = {"chat-theme.css": "chat-theme.css", "brand-layers.svg": "brand-layers.svg", "assistant-layers.svg": "assistant-layers.svg", "assistant-default.svg": "assistant-default.svg", "navigation-plus.svg": "navigation-plus.svg", "navigation-search.svg": "navigation-search.svg", "work-search.svg": "work-search.svg", "work-condition-collapsed.svg": "work-condition-collapsed.svg", "work-condition-expanded.svg": "work-condition-expanded.svg", "font-licenses.txt": "fonts/LICENSE.txt",
            "ees-work-launcher.js": "ees-work-launcher.js", "ees-work-launcher.css": "ees-work-launcher.css"}
V4_ICON_FILES = tuple("v4/" + name for name in (
    "07d31.svg", "093d6.svg", "126c7.svg", "2e769.svg", "34f85.svg", "40ef1.svg", "44a96.svg",
    "49833.svg", "4df0d.svg", "4fb09.svg", "522b5.svg", "69549.svg", "721d7.svg", "730b1.svg",
    "7bb4a.svg", "87d9b.svg", "88026.svg", "92ec5.svg", "9c63b.svg", "a9175.svg", "a953c.svg",
    "b8bc6.svg", "bddb4.svg", "c325d.svg", "cf77a.svg", "d448c.svg", "d553d.svg", "e1049.svg",
    "e1472.svg", "ea639.svg", "ead50.svg", "eb94a.svg", "f6bbc.svg",
))
V4_ICON_FILES += tuple("v4/" + name for name in ('40095.svg', 'f34f3.svg', 'c6340.svg', '7495b.svg', 'ed85e.svg', '08bf3.svg', '3b2d6.svg', 'fa106.svg', '1fc4e.svg', 'aee94.svg', 'cece5.svg', '8a225.svg', 'e8a37.svg', 'd1220.svg', 'f908d.svg', 'da025.svg', '7e98c.svg', 'ca02b.svg', 'd8f27.svg', 'cda5f.svg', '6611a.svg', '51602.svg', 'afcd5.svg', '0a1db.svg', '1f65b.svg', '2f929.svg', '7d31f.svg', '9d8d5.svg', '922a3.svg', '49c9b.svg', '31608.svg', 'f49d4.svg', '8fa06.svg', 'b8999.svg', 'd87d1.svg', '5f62e.svg', '1e4cf.svg', 'b944b.svg', '4723e.svg', 'ce467.svg', 'ae415.svg', '4d983.svg', '66cc7.svg',))
V4_ICON_FILES += ("v4/8f8a1.svg",)
V4_ICON_FILES += tuple("v4/" + name for name in (
    "35b2e.svg", "a28e3.svg", "b22ad.svg", "f1e53.svg", "b456d.svg",
    "52271.svg", "63982.svg", "6d84b.svg", "1c98e.svg", "478bf.svg",
))
V4_ICON_FILES += tuple("v4/" + name for name in (
    "f4cb1.svg", "3dae2.svg", "e9ac2.svg", "30679.svg", "2b3d1.svg",
    "1a06f.svg", "2fe77.svg", "2eb05.svg", "b355c.svg", "66c71.svg", "45242.svg",
))
UI_FILES.update({name: name for name in V4_ICON_FILES})
WORK_LAUNCHER_SOURCES = ("ees-work-view.js", "ees-work-designer.js", "ees-work-launcher.js")
WORK_DIR = ASSET_DIR.parents[2] / "agent-pack" / "skills" / "ees-work-demo"
WORK_ASSETS = {"scripts/ees_work_demo.py": "open_webui/ees_work_demo.py",
               **{"ui/" + name: "open_webui/ees_work_demo_ui/" + name
                  for name in ("index.html", "ees-work.css", "ees-work.js")}}
LEGACY_WORK_FILES = tuple(WORK_ASSETS.values()) + tuple("open_webui/frontend/_ees5/" + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
WORK_ASSETS.update({"scripts/ees_workflow.py": "open_webui/ees_workflow.py",
                    "scripts/workflow_seed.json": "open_webui/workflow_seed.json"})
WORK_BOOTSTRAP = WORK_DIR.parent / "cross-system-analysis" / "ui" / "work-panel.js"
WORK_BOOTSTRAP_TARGET = TARGET_APP + "ees-work-panel.js"
# ees.6 through ees.8 shipped the single-file workflow. Their backups must not
# acquire new required modules when this wrapper adds the split implementation.
WORK_FILES_V6 = (WORK_BOOTSTRAP_TARGET,) + tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
WORK_ASSETS.update({"scripts/ees_workflow_definition.py": "open_webui/ees_workflow_definition.py",
                    "scripts/ees_workflow_view.py": "open_webui/ees_workflow_view.py",
                    "scripts/workflow_policy.json": "open_webui/workflow_policy.json"})
# Freeze the shipped ees.9/ees.10 inventory before adding authoring modules.
WORK_FILES_V9 = (WORK_BOOTSTRAP_TARGET,) + tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
WORK_ASSETS.update({"scripts/ees_workflow_authoring.py": "open_webui/ees_workflow_authoring.py"})
# Keep ees.11's shipped inventory independent of the new execution runtime.
WORK_FILES_V11 = (WORK_BOOTSTRAP_TARGET,) + tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
WORK_ASSETS.update({"scripts/" + name: "open_webui/" + name for name in (
    "ees_workflow_execution.py", "ees_workflow_native.py", "ees_workflow_contract.py",
    "ees_workflow_examples.py", "ees_workflow_model.py",
)})
# Immutable previous inventory is required for program-only Restore.
WORK_FILES_V12 = (WORK_BOOTSTRAP_TARGET,) + tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
RETIRED_WORK_SOURCES = {"scripts/ees_work_demo.py", "scripts/workflow_seed.json", "scripts/ees_workflow_examples.py",
                        "ui/index.html", "ui/ees-work.css", "ui/ees-work.js"}
WORK_ASSETS = {source: target for source, target in WORK_ASSETS.items() if source not in RETIRED_WORK_SOURCES}
WORK_ASSETS.update({"scripts/" + name: "open_webui/" + name for name in (
    "ees_workflow_workspace.py", "ees_workflow_operations.py",
)})
# Common read/proposal Native Tool source is available for explicit admin setup;
# it is never a demo seed or an automatically registered user asset.
WORK_ASSETS["scripts/workflow_tool.py"] = "open_webui/ees_workflow_tool.py"
WORK_FILES = tuple(WORK_ASSETS.values()) + tuple(TARGET_APP + name for name in ("ees-work-launcher.js", "ees-work-launcher.css"))
# Current UI references must be present even when a truncated archive has a
# recomputed RECORD. Shipped prior-version inventories above stay unchanged.
WORK_FILES += tuple(TARGET_APP + name for name in V4_ICON_FILES)
# Already selected ees.13 programs and Restore backups predate these two
# assets. Freeze that inventory while requiring both for new incoming wheels.
WORK_FILES_V13 = WORK_FILES
EASY_AUTHORING_ASSETS = {"scripts/" + name: "open_webui/" + name for name in (
    "workflow_help.json", "workflow_tool_examples.json",
)}
WORK_ASSETS.update(EASY_AUTHORING_ASSETS)
WORK_FILES += tuple(EASY_AUTHORING_ASSETS.values())
# PR #75's installed ees.13 programs include the help/tool pair but predate
# procedure examples. Keep both shipped inventories independently restorable.
WORK_FILES_V13_EASY_AUTHORING = WORK_FILES
WORK_ASSETS["scripts/workflow_procedure_examples.json"] = "open_webui/workflow_procedure_examples.json"
WORK_FILES += (WORK_ASSETS["scripts/workflow_procedure_examples.json"],)
# PR #76 shipped procedure examples before the C18 menu icons. Preserve its
# exact inventory for selected programs and program-only Restore backups.
WORK_FILES_V13_PROCEDURE_EXAMPLES = WORK_FILES
MENU_ICON_FILES = tuple("v4/" + name for name in (
    "83565.svg", "54b2e.svg", "4d978.svg", "4308e.svg",
))
V4_ICON_FILES += MENU_ICON_FILES
UI_FILES.update({name: name for name in MENU_ICON_FILES})
WORK_FILES += tuple(TARGET_APP + name for name in MENU_ICON_FILES)
# Freeze the complete C18 ees.13 inventory before any ees.14 additions.
WORK_FILES_V13_COMPLETE = WORK_FILES
# Existing ees.14 programs predate shared tools. Their recorded inventory must
# stay restorable; new incoming wheels must include the new runtime module.
WORK_FILES_V14_PRE_SHARED = WORK_FILES
WORK_ASSETS["scripts/ees_workflow_shared_tools.py"] = "open_webui/ees_workflow_shared_tools.py"
WORK_FILES += (WORK_ASSETS["scripts/ees_workflow_shared_tools.py"],)
AUTHORING_ICON_FILES = tuple("v4/" + name for name in (
    "0a3bb.svg", "9acc8.svg", "cb8e2.svg", "7f185.svg", "f95ba.svg", "d73ca.svg",
    "41b38.svg", "676c3.svg", "f0554.svg", "9ce50.svg", "f17e6.svg",
))
V4_ICON_FILES += AUTHORING_ICON_FILES
UI_FILES.update({name: name for name in AUTHORING_ICON_FILES})
WORK_FILES += tuple(TARGET_APP + name for name in AUTHORING_ICON_FILES)
# Copy these already bundled upstream fonts byte-for-byte into the new cache
# namespace; no font download, transformation, or runtime dependency is needed.
FONT_SOURCES = {
    "Inter-Variable.ttf": ("open_webui/frontend/assets/fonts/Inter-Variable.ttf",
                           "cf3cb43b0366e2dc6df60e1132b1c9a4c15777f0cd8e5a53e0c15124003e9ed4"),
    "NotoSansKR-Variable.ttf": ("open_webui/static/fonts/NotoSansKR-Variable.ttf",
                                "2d2267a83d089cb1a517a4f901676d05d283346e650d1b1845d601cbd696a98e"),
}
THEME_FILES = ("chat-theme.css", "fonts/LICENSE.txt") + tuple("fonts/" + name for name in FONT_SOURCES)
# Frontend changes are reviewed source patches compiled before this packager.
# Only the existing Python integration and wheel metadata remain byte patches.
PATCHES = {
    "open_webui/routers/models.py": [(
        b"url='/static/favicon.png'",
        b"url='/_ees14/assistant-default.svg'", 2,
    )],
    "open_webui/main.py": [(
        b"if os.path.exists(FRONTEND_BUILD_DIR):",
        b"from open_webui.ees_workflow import install as install_ees_workflow\n"
        b"install_ees_workflow(app, get_verified_user)\n\n"
        b"if os.path.exists(FRONTEND_BUILD_DIR):", 1,
    )],
    "open_webui/env.py": [(
        b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
        b"if WEBUI_NAME != 'Open WebUI':\n    WEBUI_NAME += ' (Open WebUI)'",
        b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'EES Workflow')\n"
        b"if WEBUI_NAME in {'EES Assistant', 'EES Portal', 'EES Work'}:\n    WEBUI_NAME = 'EES Workflow'", 1,
    )],
    SOURCE_INFO + "METADATA": [(
        b"\nVersion: 0.11.3\n", b"\nVersion: 0.11.3+ees.14\n", 1,
    )],
}


# This inventory is audited against every Python file in the pinned wheel.
# Plugin import normalization and knowledge deletion also write assets; a
# table-only lock would start after their stale read and lose the user's edit.
ASSET_GUARD_FILES = ("open_webui/ees_asset_guard.py",)
ASSET_GUARD_SOURCE = Path(__file__).resolve().with_name("ees_asset_guard.py")
ASSET_GUARD_HOOKS = {
    "open_webui/models/tools.py": ("ToolsTable", (
        "insert_new_tool", "update_tool_by_id", "update_tool_valves_by_id", "delete_tool_by_id")),
    "open_webui/models/models.py": ("ModelsTable", (
        "insert_new_model", "update_model_by_id", "update_model_updated_at_by_id",
        "toggle_model_by_id", "sync_models", "delete_model_by_id", "delete_all_models",
        "get_all_models", "get_models", "get_base_models", "search_models",
        "get_model_by_id", "get_models_by_ids")),
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
ASSET_GUARD_SOURCE_HASHES = {
    "open_webui/utils/middleware.py": "3cdd77945d32f7df1461c24b729c0e37c3a5069712013b1619ce895d5957f0a4",
    "open_webui/utils/tools.py": 'fb9ac81cf7bb4dbc9eef06a0dc8a8fb2f7314cbf62f49a8cbc86dfe6020edd0e','open_webui/main.py': 'e5cbc9326266a7c0983061ecf8b792184f91e13a0e245c3e520549ec0a2978e1',
 'open_webui/models/access_grants.py': 'c034481518fa1cacf3fcba003c18692bbf8947395b8543a011ea7ab860b7e914',
 'open_webui/models/models.py': 'd07887f09d157062834798cb42f4fd6d2025fe3c39af1caeb2ad582d0b0e48ae',
 'open_webui/models/tools.py': '9d22ae68828f5285fe3f72d8297322dca536381b355262315bb0ac80ba868ba7',
 'open_webui/routers/groups.py': 'be2181a97cc371b1ebc67794a81ff4196b57c8aa4996a02b54424053af23b7ba',
 'open_webui/routers/knowledge.py': '242898318117c38c29327f9739d6cd751ffee1876d93861d4c0fd089de5b8258',
 'open_webui/routers/models.py': 'e1c157f6f441d2e862604e066de18081d89bd41dfad42ee437742815cc8c515b',
 'open_webui/routers/ollama.py': '2dcd5311688bc6ba6b6b4a4f976e4518cd399d68662ab54da77b37643a3594b1',
 'open_webui/routers/openai.py': '4d21f5b2e4bdf447199e5665c54408b41d3f60b64ad43402ce1e3f1bbf19c46f',
 'open_webui/routers/tools.py': '14988ae70f6621f9952452d34dd81fe29107d0e8821cb20508119cf9b582abf2',
 'open_webui/routers/users.py': '00ff1e38635a2058befcb92f955da0811ffae7ab85fd6ac50471e4ae55319c41',
 'open_webui/utils/access_control/__init__.py': 'af269f2055421e27f7268a4bd8238769f22c99c59059c5b153fdeeb6581fa8f7',
 'open_webui/utils/models.py': 'c699a22aba417aaa599364d19613d5ef87431db3bb58fd0c5e8edc2e6601fa9c',
 'open_webui/utils/plugin.py': '3c5d5c66cd81f242b595b4ab71b73fbf92c617b2c7b8655a9a4ffe46b1c1b83e'}


def _one_replace(text, before, after, filename):
    if text.count(before) != 1:
        raise ValueError(f"Asset guard patch precondition failed: {filename}")
    return text.replace(before, after, 1)


def _guard_import(text, statement):
    tree = ast.parse(text)
    futures = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "__future__"]
    if futures:
        at = futures[-1].end_lineno
    elif tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
        at = tree.body[0].end_lineno
    else:
        at = 0
    lines = text.splitlines(keepends=True)
    lines.insert(at, "\n" + statement + "\n")
    return "".join(lines)


def _guard_decorate(text, filename, class_name, functions):
    tree = ast.parse(text)
    nodes = tree.body
    if class_name:
        classes = [node for node in nodes if isinstance(node, ast.ClassDef) and node.name == class_name]
        if len(classes) != 1:
            raise ValueError(f"Asset guard class differs: {filename}")
        nodes = classes[0].body
    lines = text.splitlines(keepends=True)
    decorator = "guard_operation" if filename == "open_webui/utils/plugin.py" else "guard_table_method"
    found = []
    for name in functions:
        matches = [node for node in nodes if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
        if len(matches) != 1:
            raise ValueError(f"Asset guard method differs: {filename}:{name}")
        node = matches[0]
        # Place beneath existing route decorators so APIRoute receives the
        # guarded callable during registration, preserving its typed signature.
        option = "(asset_types_only=True)" if class_name == "AccessGrantsTable" else ""
        found.append((node.lineno - 1, " " * node.col_offset + "@" + decorator + option + "\n"))
    for at, line in sorted(found, reverse=True):
        lines.insert(at, line)
    return _guard_import("".join(lines), "from open_webui.ees_asset_guard import " + decorator)


def _guard_tool_cache(text, filename):
    # Prepare specs locally; only a confirmed native DB/ACL save can publish
    # the new module. Native permission checks and source compilation stay put.
    for name, key in (("create_new_tools", "form_data.id"), ("update_tools_by_id", "id")):
        node, = [n for n in ast.parse(text).body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
        lines = text.splitlines(keepends=True)
        body = "".join(lines[node.lineno - 1:node.end_lineno])
        body = _one_replace(body, f"TOOLS[{key}] = tool_module\n", "# Publish only after DB and ACL commit.\n", filename)
        body = _one_replace(body, f"get_tool_specs(TOOLS[{key}])", "get_tool_specs(tool_module)", filename)
        marker = "if tools:\n" + (" " * (16 if name == "create_new_tools" else 12)) + "await publish_event("
        indent = " " * (16 if name == "create_new_tools" else 12)
        body = _one_replace(body, marker, "if tools:\n" + indent + f"TOOLS[{key}] = tool_module\n" + indent + "await publish_event(", filename)
        for clause in ("except HTTPException:\n", "except Exception as e:\n"):
            indent = " " * (12 if name == "create_new_tools" else 8)
            body = _one_replace(body, clause, clause + indent + f"get_tools_cache(request).pop({key}, None)\n", filename)
        if name == "update_tools_by_id":
            body = _one_replace(body, "        log.debug(updated)\n", "        # Asset source and settings must not enter debug logs.\n", filename)
        lines[node.lineno - 1:node.end_lineno] = [body]
        text = "".join(lines)
    return text



def _guard_local_tool_loading(text, filename):
    # Only local Tool preparation owns the lock. Keep remote OpenAPI/MCP I/O
    # outside it and re-read each local Tool instead of publishing a cached
    # module from the earlier, unprotected batch snapshot.
    node, = [n for n in ast.parse(text).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_tools"]
    loop, = [n for n in node.body if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "tool_id"]
    if len(loop.body) != 2 or not isinstance(loop.body[1], ast.If) or not loop.body[1].orelse:
        raise ValueError("Local Tool loading boundary differs.")
    branch = loop.body[1]
    lines = text.splitlines(keepends=True)
    local = "".join(lines[branch.body[0].lineno - 1:branch.body[-1].end_lineno])
    local = _one_replace(local, "                continue\n", "                return True\n", filename)
    replacement = (
        "        @guard_operation\n"
        "        async def ees_load_local_tool():\n"
        "            tool = await Tools.get_tool_by_id(tool_id)\n"
        "            if tool is None:\n                return False\n"
        "            from open_webui.ees_workflow_native import check_chat_work_tool\n"
        "            await check_chat_work_tool(request, user, tool)\n"
        "            user_group_ids = {group.id for group in await Groups.get_groups_by_member_id(user.id)}\n" +
        local + "\n            return True\n\n"
        "        if await ees_load_local_tool():\n            pass\n"
    )
    lines[loop.body[0].lineno - 1:branch.body[-1].end_lineno] = [replacement]
    text = "".join(lines)
    text = _one_replace(text, "    # Batch-fetch all DB tools in one query instead of one per tool_id\n"
                        "    tool_models = await Tools.get_tools_by_ids(tool_ids)\n",
                        "    # Local assets are read and prepared together under the asset guard.\n", filename)
    text = _guard_import(text, "from open_webui.ees_asset_guard import guard_operation")
    return text + "\nEES_ASSET_LOCAL_TOOL_GUARD = 1\n"


def _guard_headless_model_parameters(text, filename):
    """Validate the exact preset read by either pinned provider route.

    Adapter preflight cannot freeze a preset across Native's later DB read.
    Recheck synchronously at parameter application for server-marked EES calls;
    ordinary Native chat settings and public request bodies remain unchanged.
    """
    nodes = [node for node in ast.parse(text).body
             if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_chat_completion"]
    if len(nodes) != 1:
        raise ValueError(f"Native model route differs: {filename}")
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    body = "".join(lines[node.lineno - 1:node.end_lineno])
    before = "        params = model_info.params.model_dump()\n"
    after = ("        if getattr(request.state, 'ees_workflow_headless', False):\n"
             "            from open_webui.ees_workflow_model import _headless_parameters\n"
             "            params, _ = _headless_parameters(model_info, request_limits=True)\n"
             "        else:\n" + "    " + before)
    body = _one_replace(body, before, after, filename)
    lines[node.lineno - 1:node.end_lineno] = [body]
    return "".join(lines)


def prepare_asset_guard_replacements(source, replacements):
    for filename, expected_hash in ASSET_GUARD_SOURCE_HASHES.items():
        raw = source.read(filename)
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError(f"Pinned asset writer source differs: {filename}")
        text = replacements.get(filename, raw).decode("utf-8")
        if filename in ASSET_GUARD_HOOKS:
            text = _guard_decorate(text, filename, *ASSET_GUARD_HOOKS[filename])
        if filename in {"open_webui/routers/tools.py", "open_webui/routers/models.py"}:
            text = _one_replace(text, "router = APIRouter()", "router = APIRouter(route_class=AssetGuardRoute)", filename)
            text = _guard_import(text, "from open_webui.ees_asset_guard import AssetGuardRoute")
        if filename == "open_webui/routers/tools.py":
            text = _guard_tool_cache(text, filename)
            text += "\nEES_ASSET_CACHE_COMMIT_ORDER = 1\n"
        if filename == "open_webui/utils/tools.py":
            text = _guard_local_tool_loading(text, filename)
        if filename == "open_webui/utils/middleware.py":
            text = _guard_import(text, "from open_webui.ees_workflow_native import enforce_chat_work_help")
            text = _one_replace(text, "    if is_saved_chat_id(chat_id) and user_message_id:\n        if getattr(request.state, 'direct', False)",
                "    if is_saved_chat_id(chat_id) and user_message_id and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n        if getattr(request.state, 'direct', False)", filename)
            text = _one_replace(text, "                if message.get('role') == 'user' and image_files:\n",
                "                if message.get('role') == 'user' and image_files and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    form_data = await convert_url_images_to_base64(form_data, user=user)\n",
                "    if getattr(request.state, 'ees_work_help_protocol', None) != 1:\n"
                "        form_data = await convert_url_images_to_base64(form_data, user=user)\n", filename)
            text = _one_replace(text, "        if use_builtin_tools:\n",
                "        if use_builtin_tools and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    features = form_data.pop('features', None) or {}\n",
                "    await enforce_chat_work_help(request, user, metadata, form_data)\n"
                "    features = form_data.pop('features', None) or {}\n", filename)
            text = _one_replace(text, "    if folder_id and user:\n",
                "    if folder_id and user and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    if model_knowledge and metadata.get('params', {}).get('function_calling') == 'legacy':\n",
                "    if model_knowledge and metadata.get('params', {}).get('function_calling') == 'legacy' and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    if model_knowledge:\n",
                "    if model_knowledge and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    available_skills = []\n",
                "    if getattr(request.state, 'ees_work_help_protocol', None) == 1:\n"
                "        skill_ids = []\n"
                "    available_skills = []\n", filename)
            text = _one_replace(text, "    if file_context_enabled:\n",
                "    if file_context_enabled and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n", filename)
            text = _one_replace(text, "    tool_ids = form_data.pop('tool_ids', None)\n",
                "    tool_ids = form_data.pop('tool_ids', None)\n"
                "    from open_webui.ees_workflow_native import select_chat_work_tools, wrap_chat_work_tools\n"
                "    tool_ids = await select_chat_work_tools(request, user, metadata, tool_ids, form_data, explicit_tools=payload_tools is not None)\n", filename)
            text = _one_replace(text, "        if tools_dict:\n",
                "        tools_dict = wrap_chat_work_tools(request, user, tools_dict)\n\n"
                "        if tools_dict:\n", filename)
            # Check both Native tool dispatch paths and each model continuation
            # after the retained policy request filters have run.
            text = _one_replace(text, "\n    tools = metadata.get('tools', {})\n",
                "\n    await enforce_chat_work_help(request, user, metadata, form_data, dispatch=True)\n"
                "    tools = metadata.get('tools', {})\n", filename)
            text = _one_replace(text, "\n                    tools = metadata.get('tools', {})\n",
                "\n                    await enforce_chat_work_help(request, user, metadata, form_data, dispatch=True)\n"
                "                    tools = metadata.get('tools', {})\n", filename)
            for indent in (" " * 24, " " * 28):
                before = "\n" + indent + "res = await generate_chat_completion(\n"
                text = _one_replace(text, before,
                    "\n" + indent + "await enforce_chat_work_help(request, user, metadata, new_form_data, dispatch=True)" + before, filename)
            text += "\nEES_WORK_NATIVE_CHAT_CONTEXT = 1\n"
        if filename in {"open_webui/routers/openai.py", "open_webui/routers/ollama.py"}:
            text = _guard_headless_model_parameters(text, filename)
        if filename == "open_webui/main.py":
            text = _one_replace(text, "        if is_new_chat:\n            metadata['chat_id'] = str(uuid4())\n",
                "        from open_webui.ees_workflow_native import prepare_chat_work_help\n"
                "        if await prepare_chat_work_help(request, user, metadata, form_data, is_new_chat=is_new_chat, message_ids=message_ids):\n"
                "            tasks = None\n"
                "        if is_new_chat:\n            metadata['chat_id'] = str(uuid4())\n", filename)
            text = _one_replace(text, "                                'models': [entry['model_id'] for entry in message_ids],\n",
                "                                'models': getattr(request.state, 'ees_work_help_composer_models', None) or [entry['model_id'] for entry in message_ids],\n", filename)
            text = _one_replace(text, "                    if chat_fields:\n                        await Chats.update_chat_by_id(chat_id, chat_fields, touch=False)\n",
                "                    if chat_fields and getattr(request.state, 'ees_work_help_protocol', None) != 1:\n"
                "                        await Chats.update_chat_by_id(chat_id, chat_fields, touch=False)\n", filename)
            text = _one_replace(text, "            response = await chat_completion_handler(request, form_data, user)\n",
                "            from open_webui.ees_workflow_native import enforce_chat_work_help\n"
                "            await enforce_chat_work_help(request, user, metadata, form_data, dispatch=True)\n"
                "            response = await chat_completion_handler(request, form_data, user)\n", filename)
            text = _one_replace(text, "                    and getattr(request.state, 'internal', False) is not True\n",
                "                    and getattr(request.state, 'internal', False) is not True\n"
                "                    and getattr(request.state, 'ees_work_help_protocol', None) != 1\n", filename)
            node, = [n for n in ast.parse(text).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"]
            lines = text.splitlines(keepends=True)
            body = "".join(lines[node.lineno - 1:node.end_lineno])
            start = "    app.state.main_loop = asyncio.get_running_loop()\n"
            if body.count(start) != 1:
                raise ValueError("Asset guard lifespan boundary differs.")
            before, after = body.split(start)
            body = (before + start + "    from open_webui.ees_asset_guard import start_asset_guard, stop_asset_guard\n"
                    "    await start_asset_guard(app)\n    try:\n" +
                    "".join("    " + line if line.strip() else line for line in after.splitlines(keepends=True)) +
                    "    finally:\n        await stop_asset_guard(app)\n")
            lines[node.lineno - 1:node.end_lineno] = [body]
            text = "".join(lines)
            text = _one_replace(text, "app.include_router(tools.router, prefix='/api/v1/tools', tags=['tools'])",
                                "app.include_router(tools.router, prefix='/api/v1/tools', tags=['tools'])\n"
                                "from open_webui.ees_asset_guard import create_asset_router\n"
                                "app.include_router(create_asset_router(), prefix='/api/v1/ees/assets', tags=['ees-assets'])", filename)
        compile(text, filename, "exec")
        replacements[filename] = text.encode("utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_name(name):
    if name.startswith(SOURCE_INFO):
        return TARGET_INFO + name[len(SOURCE_INFO):]
    return name


def prepare_replacements(source, asset_dir):
    """Validate every precondition before creating any output file."""
    names = source.namelist()
    if len(names) != len(set(names)):
        raise ValueError("The source wheel contains duplicate entries.")
    targets = [target_name(name) for name in names]
    if len(targets) != len(set(targets)):
        raise ValueError("The target wheel would contain duplicate entries.")
    if any(name.endswith(("/RECORD.jws", "/RECORD.p7s")) for name in names):
        raise ValueError("Signed wheels cannot be repacked by this builder.")
    required = set(PATCHES) | set(ASSET_GUARD_SOURCE_HASHES) | {SOURCE_INFO + "RECORD", SOURCE_INFO + "WHEEL"}
    asset_targets = {
        prefix + name: name
        for prefix in ("open_webui/static/",)
        for name in ASSET_NAMES
    }
    required.update(asset_targets)
    missing = required - set(names)
    if missing:
        raise ValueError("Missing wheel entries: " + ", ".join(sorted(missing)))

    replacements = {}
    for name, patches in PATCHES.items():
        content = source.read(name)
        for old, new, expected in patches:
            actual = content.count(old)
            if actual != expected:
                raise ValueError(f"Patch precondition failed: {name}: expected {expected}, got {actual}.")
            content = content.replace(old, new)
        replacements[name] = content
    prepare_asset_guard_replacements(source, replacements)
    assets = {}
    for name in ASSET_NAMES:
        path = Path(asset_dir) / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty branding asset: {name}")
        assets[name] = path.read_bytes()
    replacements.update({name: assets[asset] for name, asset in asset_targets.items()})
    return replacements


def zip_entry(name, attributes=0o100644 << 16):
    entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = attributes
    entry.compress_type = ZIP_DEFLATED
    return entry


def assemble_work_launcher(ui_dir=UI_DIR):
    """Build one private runtime scope in the reviewed dependency order.

    Factories are named declarations in their own source unit. Reject misplaced
    or duplicate declarations instead of shipping a partly assembled launcher.
    Bytes are preserved, including line endings; no loader or JS bundler runs.
    """
    expected = (("ees-work-view.js", "createWorkView"),
                ("ees-work-designer.js", "createWorkDesigner"),
                ("ees-work-launcher.js", None))
    if WORK_LAUNCHER_SOURCES != tuple(name for name, _ in expected):
        raise ValueError("EES Workflow launcher source order differs.")
    root = Path(ui_dir)
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("Linked EES Workflow launcher source directory.")
    parts = []
    declaration = re.compile(rb"\b(?:function\s+|(?:const|let|var)\s+)(createWorkView|createWorkDesigner)\b")
    for filename, factory in expected:
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or linked EES Workflow launcher source: {filename}")
        content = path.read_bytes()
        if not content.strip():
            raise ValueError(f"Empty EES Workflow launcher source: {filename}")
        wanted = [factory.encode("ascii")] if factory else []
        if declaration.findall(content) != wanted or (factory and not re.search(
                rb"\bfunction\s+" + factory.encode("ascii") + rb"\s*\(", content)):
            raise ValueError(f"EES Workflow launcher factory/order differs: {filename}")
        parts.append(content)
    assembled = b"(() => {\n'use strict';\n" + b"\n;\n".join(parts) + b"\n})();\n"
    for relative in V4_ICON_FILES:
        path = Path(ui_dir) / relative
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing, empty, or linked EES v4 icon: {relative}")
        name = path.name.encode("ascii")
        hashed = name + b"?v=" + hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
        assembled = assembled.replace(b'"' + name + b'"', b'"' + hashed + b'"')
    return assembled


def prepare_additions(source, ui_dir, work_dir=WORK_DIR):
    additions = {}
    for filename, relative in UI_FILES.items():
        path = Path(ui_dir) / filename
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing, empty, or linked EES UI asset: {filename}")
        additions[TARGET_APP + relative] = (assemble_work_launcher(ui_dir)
            if filename == "ees-work-launcher.js" else path.read_bytes())
    for relative in V4_ICON_FILES:
        url = ("/" + TARGET_APP.removeprefix("open_webui/frontend/") + relative).encode("ascii")
        digest = hashlib.sha256(additions[TARGET_APP + relative]).hexdigest().encode("ascii")
        for filename in ("chat-theme.css", "ees-work-launcher.css"):
            for source_url in (url, ("./" + relative).encode("ascii")):
                additions[TARGET_APP + filename] = additions[TARGET_APP + filename].replace(source_url, source_url + b"?v=" + digest)
    for relative, target in WORK_ASSETS.items():
        path = Path(work_dir) / relative
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing, empty, or linked EES Workflow asset: {relative}")
        additions[target] = path.read_bytes()
    if ASSET_GUARD_SOURCE.is_symlink() or not ASSET_GUARD_SOURCE.is_file() or not ASSET_GUARD_SOURCE.stat().st_size:
        raise ValueError("Missing, empty, or linked asset guard runtime.")
    additions[ASSET_GUARD_FILES[0]] = ASSET_GUARD_SOURCE.read_bytes()
    for filename, (origin, expected) in FONT_SOURCES.items():
        if origin not in source.namelist():
            raise ValueError(f"Missing pinned upstream font: {filename}")
        content = source.read(origin)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Pinned upstream font hash differs: {filename}")
        additions[TARGET_APP + "fonts/" + filename] = content
    if set(additions) & {target_name(name) for name in source.namelist()}:
        raise ValueError("The source wheel already contains an EES UI target.")
    return additions


def build(wheel, output_dir, asset_dir=ASSET_DIR, ui_dir=UI_DIR, frontend_dir=None):
    wheel, output_dir = Path(wheel), Path(output_dir)
    if wheel.name != SOURCE_FILENAME or sha256_file(wheel) != SOURCE_SHA256:
        raise ValueError("Expected the unchanged, pinned official Open WebUI 0.11.3 wheel.")
    wheel_target = output_dir / WHEEL_FILENAME
    manifest_target = output_dir / "manifest.json"
    if any(path.exists() or path.is_symlink() for path in (wheel_target, manifest_target)):
        raise ValueError("Output already exists; choose an empty release destination.")

    with ZipFile(wheel) as source:
        replacements = prepare_replacements(source, asset_dir)
        additions = prepare_additions(source, ui_dir)
        if frontend_dir is None:
            raise ValueError("A verified CI source frontend is required (--frontend-dir).")
        try:
            from build_ees_frontend import validate_frontend
        except ModuleNotFoundError:
            from scripts.build_ees_frontend import validate_frontend
        frontend = validate_frontend(frontend_dir, mode="ees")
        frontend_manifest = json.loads((Path(frontend_dir) / "manifest.json").read_text(encoding="utf-8"))
        prefix = "open_webui/frontend/"
        frontend_entries = {prefix + name: content for name, content in frontend.items()}
        # The source build already contains the reviewed binary branding.
        # Verify every copied image and preserve every frontend byte unchanged.
        for name in ASSET_NAMES:
            target = prefix + "static/" + name
            if target not in frontend_entries:
                raise ValueError("Missing source-built static branding target: " + name)
            if frontend_entries[target] != (Path(asset_dir) / name).read_bytes():
                raise ValueError("Source-built static branding differs: " + name)
        if frontend_entries.get(prefix + "favicon.png") != (Path(asset_dir) / "favicon.png").read_bytes():
            raise ValueError("Missing or mismatched source-built favicon target.")
        if set(frontend_entries) & set(additions):
            raise ValueError("Source frontend overlaps separately packaged EES assets.")
        # A source build cannot silently reference older EES runtime assets.
        # Verify the URLs produced before compilation; never edit built HTML.
        index = frontend_entries[prefix + "index.html"]
        for filename in ("chat-theme.css", "ees-work-launcher.css", "ees-work-launcher.js"):
            path = TARGET_APP + filename
            digest = hashlib.sha256(additions[path]).hexdigest()
            url = ("/" + path.removeprefix(prefix) + "?v=" + digest + '"').encode("ascii")
            if index.count(url) != 1:
                raise ValueError("Source frontend runtime asset hash differs: " + filename)
        additions.update(frontend_entries)
        entries = sorted((entry for entry in source.infolist()
                          if not entry.filename.startswith(prefix)), key=lambda entry: target_name(entry.filename))
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ees-build-", dir=output_dir) as temporary:
            built = Path(temporary) / WHEEL_FILENAME
            record = []
            with ZipFile(built, "w", compression=ZIP_DEFLATED, compresslevel=6) as destination:
                for entry in entries:
                    if entry.filename == SOURCE_INFO + "RECORD":
                        continue
                    name = target_name(entry.filename)
                    content = replacements.get(entry.filename)
                    if content is None:
                        content = source.read(entry)
                    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                    destination.writestr(zip_entry(name, entry.external_attr), content, compresslevel=6)
                    record.append((name, "sha256=" + digest, str(len(content))))
                for name, content in sorted(additions.items()):
                    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                    destination.writestr(zip_entry(name), content, compresslevel=6)
                    record.append((name, "sha256=" + digest, str(len(content))))
                record_name = TARGET_INFO + "RECORD"
                record.append((record_name, "", ""))
                csv_text = io.StringIO(newline="")
                csv.writer(csv_text, lineterminator="\n").writerows(record)
                destination.writestr(zip_entry(record_name), csv_text.getvalue().encode(), compresslevel=6)

            # A digest alone can describe an incomplete file. Verify the closed
            # archive before publishing either the wheel or its manifest.
            try:
                with ZipFile(built) as verified:
                    if sorted(verified.namelist()) != sorted(row[0] for row in record) or verified.testzip() is not None:
                        raise ValueError("Built archive is incomplete or corrupt.")
            except BadZipFile as error:
                raise ValueError("Built archive is incomplete or corrupt.") from error

            manifest = {
                "schema_version": 1,
                "upstream_version": UPSTREAM_VERSION,
                "version": VERSION,
                "source": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256},
                "wheel": {"filename": WHEEL_FILENAME, "sha256": sha256_file(built), "size": built.stat().st_size},
                "changed_files": sorted([target_name(name) for name in replacements] + list(additions) + [record_name]),
                "source_frontend": frontend_manifest,
            }
            manifest_file = Path(temporary) / "manifest.json"
            # Preserve the full provenance/inventory schema while staying under
            # the unchanged deployment parser bound. Reject before publishing.
            manifest_bytes = (json.dumps(manifest, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            if len(manifest_bytes) > MAX_MANIFEST_BYTES:
                raise ValueError("Branding manifest exceeds the supported 1 MiB size.")
            manifest_file.write_bytes(manifest_bytes)
            # Hard links publish complete files without overwriting a racing build.
            os.link(built, wheel_target)
            try:
                os.link(manifest_file, manifest_target)
            except OSError:
                wheel_target.unlink()
                raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--frontend-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = build(args.wheel, args.output_dir, frontend_dir=args.frontend_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build stopped: {error}\n")
    print(f"Prepared {manifest['wheel']['filename']}")
    print(f"SHA256={manifest['wheel']['sha256']}")
    print("No runtime installation or server changes were performed.")


if __name__ == "__main__":
    main()
