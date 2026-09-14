"""Apply the small EES demo pack through Open WebUI 0.11.3 APIs.

The caller supplies authenticated transport, endpoint/version checks, a private local
state directory and an exclusive deployment lock. No WebUI imports or DB access.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from urllib.parse import quote

PACK = "ees-demo-v1"
BEGIN = "<!-- EES-DEMO:BEGIN -->"
END = "<!-- EES-DEMO:END -->"
STATE_FILE = "ees-demo-assets.json"
TRANSPORT_CODES = frozenset({"webui_authentication_failed", "webui_permission_denied",
    "webui_connection_failed", "redirect_blocked", "api_conflict", "api_rate_limited",
    "api_request_failed", "api_response_too_large", "api_response_invalid", "api_path_invalid"})


class DemoAssetsError(RuntimeError):
    """Safe error code; never embeds an API response, prompt or credential."""

    def __init__(self, code: str, asset: str = "", changed: int = 0, pending: bool = False):
        super().__init__(code)
        self.code, self.asset, self.changed = code, asset, changed
        self.pending = self.unknown = pending


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _dict(value, code="invalid_asset"):
    if not isinstance(value, dict):
        raise DemoAssetsError(code)
    return copy.deepcopy(value)


def _read_source(root, relative):
    if not isinstance(relative, str):
        raise DemoAssetsError("invalid_manifest")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise DemoAssetsError("invalid_source_path")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise DemoAssetsError("empty_source")
    return content


def _suggestions(value, *, unique_content=True):
    if not isinstance(value, list):
        raise DemoAssetsError("invalid_suggestions")
    contents = []
    for row in value:
        if (not isinstance(row, dict) or not isinstance(row.get("content"), str)
                or not row["content"].strip() or not isinstance(row.get("title"), list)
                or len(row["title"]) != 2 or not all(isinstance(x, str) for x in row["title"])):
            raise DemoAssetsError("invalid_suggestions")
        # Retirement matches whole historical rows; title revisions may share
        # content. Active prompts still require unique content for ownership.
        contents.append(row["content"] if unique_content else _hash(row))
    if len(contents) != len(set(contents)):
        raise DemoAssetsError("duplicate_suggestions")
    return copy.deepcopy(value)


def _embed_panel_script(content, tree, script, asset, slot="PANEL_SCRIPT"):
    """Fill the one module-level panel literal without rewriting tool frontmatter."""
    bindings = [node for node in ast.walk(tree) if isinstance(node, ast.Name)
                and node.id == slot and isinstance(node.ctx, ast.Store)]
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == slot]
    if (len(bindings) != 1 or len(assignments) != 1
            or not isinstance(assignments[0].value, ast.Constant)
            or assignments[0].value.value != ""):
        raise DemoAssetsError("invalid_panel_script_slot", asset)
    value = assignments[0].value
    # AST columns are UTF-8 byte offsets, including when a line contains Korean.
    encoded = content.encode("utf-8")
    lines = encoded.splitlines(keepends=True)
    start = sum(map(len, lines[:value.lineno - 1])) + value.col_offset
    end = sum(map(len, lines[:value.end_lineno - 1])) + value.end_col_offset
    return (encoded[:start] + repr(script).encode("utf-8") + encoded[end:]).decode("utf-8")


def _load_tool_source(root, item, asset):
    content = _read_source(root, item["path"])
    tree = ast.parse(content)
    if "ui_script_path" in item and "ui_script_paths" in item:
        raise DemoAssetsError("invalid_manifest", asset)
    if "ui_script_path" in item or "ui_script_paths" in item:
        paths = item.get("ui_script_paths", [item.get("ui_script_path")])
        if not isinstance(paths, list) or not 1 <= len(paths) <= 2:
            raise DemoAssetsError("invalid_manifest", asset)
        script = "\n".join(_read_source(root, path) for path in paths)
        slot = item.get("ui_script_slot", "PANEL_SCRIPT")
        if slot not in ("PANEL_SCRIPT", "WORK_PANEL_SCRIPT"):
            raise DemoAssetsError("invalid_panel_script_slot", asset)
        content = _embed_panel_script(content, tree, script, asset, slot)
        tree = ast.parse(content)
    frontmatter = ast.get_docstring(tree, clean=False) or ""
    if not re.search(r"(?m)^ees_demo_pack:\s*" + re.escape(PACK) + r"\s*$", frontmatter):
        raise DemoAssetsError("tool_marker_missing", asset)
    return content


def _source_digest(content):
    # Pasting a complete source in the editor may change line endings or the
    # final blank line. All substantive text, including comments, must match.
    return hashlib.sha256(content.replace("\r\n", "\n").replace("\r", "\n").strip().encode("utf-8")).hexdigest()


def load_manifest(root: Path):
    """Read and statically validate every source before any remote mutation."""
    manifest = _dict(json.loads(_read_source(root, "agent-pack/ees-demo.json")), "invalid_manifest")
    if not isinstance(manifest.get("version"), (str, int)):
        raise DemoAssetsError("invalid_manifest")
    count = len(manifest.get("tools", []))
    if count not in {2, 3} or len(manifest.get("models", [])) != 3:
        raise DemoAssetsError("invalid_manifest_scope")
    if count == 3 and not any(item.get("id") == "ees_workflow" for item in manifest["tools"]):
        raise DemoAssetsError("invalid_manifest_scope")
    identifiers = []
    for item in manifest["tools"]:
        if not re.fullmatch(r"ees_[a-z0-9_]+", item.get("id", "")) or not item.get("name"):
            raise DemoAssetsError("invalid_tool_id")
        identifiers.append(item["id"])
        item["content"] = _load_tool_source(root, item, item["id"])
        valves = item.get("managed_valves", {})
        if valves not in ({}, {"ees_model_id": "$EES_MODEL_ID"}):
            raise DemoAssetsError("invalid_managed_valves", item["id"])
    optional = manifest.get("optional_existing_tools", [])
    if not isinstance(optional, list) or len(optional) > 1:
        raise DemoAssetsError("invalid_manifest_scope")
    for item in optional:
        if not isinstance(item, dict) or item.get("kind") != "work_order":
            raise DemoAssetsError("invalid_manifest_scope")
        digests = item.get("accepted_source_sha256")
        if (not isinstance(digests, list) or not digests
                or any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                       for digest in digests)):
            raise DemoAssetsError("invalid_legacy_source_hashes")
        # The current raw source is also safe to adopt after an initial manual
        # Tool registration. Runtime UI assets are then embedded by this apply.
        digests.append(_source_digest(_read_source(root, item["path"])))
        item["content"] = _load_tool_source(root, item, "work_order")
    tool_ids = set(identifiers)
    for item in [*manifest["models"], manifest.get("ees", {})]:
        item["prompt"] = _read_source(root, item["prompt_path"]).strip()
        if BEGIN in item["prompt"] or END in item["prompt"]:
            raise DemoAssetsError("reserved_prompt_marker")
        if "suggestions_path" in item:
            if item is not manifest["ees"] or "suggestions" in item:
                raise DemoAssetsError("invalid_manifest")
            item["suggestions"] = json.loads(_read_source(root, item["suggestions_path"]))
        item["suggestions"] = _suggestions(item.get("suggestions", []))
        if "retired_suggestions" in item:
            if item is not manifest["ees"]:
                raise DemoAssetsError("invalid_manifest")
            item["retired_suggestions"] = _suggestions(item["retired_suggestions"], unique_content=False)
        if (not isinstance(item.get("tool_ids"), list) or not set(item["tool_ids"]) <= tool_ids
                or len(item["tool_ids"]) != len(set(item["tool_ids"]))):
            raise DemoAssetsError("invalid_tool_binding")
    for item in manifest["models"]:
        if not re.fullmatch(r"ees[-_a-z0-9]+", item.get("id", "")) or not item.get("name"):
            raise DemoAssetsError("invalid_model_id")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise DemoAssetsError("duplicate_asset_id")
    return manifest


def _grants(value):
    if not isinstance(value, list):
        raise DemoAssetsError("invalid_access_grants")
    result = []
    for grant in value:
        if (not isinstance(grant, dict) or grant.get("principal_type") not in ("user", "group", "anyone")
                or not isinstance(grant.get("principal_id"), str) or not grant["principal_id"]
                or grant.get("permission") not in ("read", "write")):
            raise DemoAssetsError("invalid_access_grants")
        if grant["principal_type"] == "anyone" and (grant["principal_id"] != "*" or grant["permission"] != "read"):
            raise DemoAssetsError("invalid_access_grants")
        result.append({key: grant[key] for key in ("principal_type", "principal_id", "permission")})
    return sorted({json.dumps(g, sort_keys=True): g for g in result}.values(),
                  key=lambda g: (g["principal_type"], g["principal_id"], g["permission"]))


def _read_grants(ees):
    grants = [g for g in _grants(ees["access_grants"]) if g["permission"] == "read"]
    if ees.get("user_id"):
        grants.append({"principal_type": "user", "principal_id": ees["user_id"], "permission": "read"})
    return _grants(grants)


def _block(system):
    if not isinstance(system, str):
        raise DemoAssetsError("invalid_system_prompt")
    count = (system.count(BEGIN), system.count(END))
    if count == (0, 0):
        return None
    if count != (1, 1) or system.index(BEGIN) > system.index(END):
        raise DemoAssetsError("invalid_prompt_markers")
    return system[system.index(BEGIN):system.index(END) + len(END)]


def _spec(item, kind, ees=False):
    if kind == "valves":
        return {"keys": sorted(item)}
    if kind == "tool":
        return {"existing_only": True} if item.get("kind") == "work_order" else {}
    return {"ees": ees, "tool_ids": item["tool_ids"], "suggestions": item["suggestions"],
            "suggestion_key": "suggestion_prompts"}


def _projection(asset, kind, spec):
    if asset is None:
        return None
    if kind == "valves":
        return {key: asset.get(key) for key in spec["keys"]}
    meta = _dict(asset.get("meta"))
    if kind == "tool":
        result = {"content": asset.get("content"),
                  "marker": (meta.get("manifest") or {}).get("ees_demo_pack")}
        if not spec.get("existing_only"):
            result["name"] = asset.get("name")
        return result
    params = _dict(asset.get("params"))
    tools = meta.get("toolIds") or []
    # Journals through v0.2.4 tracked the wrong camelCase metadata field. Check
    # those records against that field before migrating; do not claim ownership
    # of the independent, visible UI suggestions from a legacy record.
    suggestions = meta.get(spec.get("suggestion_key", "suggestionPrompts")) or []
    if not isinstance(tools, list) or not isinstance(suggestions, list):
        raise DemoAssetsError("invalid_model_lists")
    selected = []
    for expected in spec["suggestions"]:
        selected.append([row for row in suggestions if isinstance(row, dict)
                         and row.get("content") == expected["content"]])
    projection = {"block": _block(params.get("system", "")),
                  "native": params.get("function_calling"),
                  "tools": {tid: tools.count(tid) for tid in spec["tool_ids"]},
                  "suggestions": selected, "marker": meta.get("ees_demo_pack")}
    if not spec["ees"]:
        projection.update(name=asset.get("name"), memory=(meta.get("capabilities") or {}).get("memory"))
    return projection


def _payload(asset, kind):
    if kind == "valves":
        return _dict(asset)
    keys = ("id", "name", "content", "meta", "access_grants") if kind == "tool" else (
        "id", "name", "base_model_id", "meta", "params", "access_grants", "is_active")
    result = {key: copy.deepcopy(asset.get(key)) for key in keys}
    result["access_grants"] = _grants(asset.get("access_grants"))
    if kind == "model":
        if not isinstance(result["is_active"], bool):
            raise DemoAssetsError("invalid_model_active")
        result["params"] = _dict(result["params"])
    result["meta"] = _dict(result["meta"])
    return result


def _view(asset, kind):
    """Compare semantic fields, ignoring server timestamps and generated grant IDs."""
    if asset is None:
        return None
    result = _payload(asset, kind)
    if kind != "valves":
        if kind == "model":
            for key in ("profile_image_url", "description", "capabilities", "knowledge"):
                result["meta"].setdefault(key, None)
        else:
            # Frontmatter/specs are regenerated by the server from the checked source.
            result["meta"] = {"description": result["meta"].get("description"),
                              "marker": (result["meta"].get("manifest") or {}).get("ees_demo_pack")}
        if asset.get("user_id") is not None:
            result["user_id"] = asset["user_id"]
    return result


def _merge_model(current, item, ees, previous):
    result = _payload(current, "model")
    meta, params = result["meta"], result["params"]
    system = params.get("system", "")
    existing = _block(system)
    wanted = BEGIN + "\n" + item["prompt"] + "\n" + END
    params["system"] = system.replace(existing, wanted, 1) if existing else (
        system + ("\n\n" if system else "") + wanted)
    params["function_calling"] = "native"
    old_tools = (previous or {}).get("tool_ids", [])
    tools = meta.get("toolIds") or []
    suggestions = meta.get("suggestion_prompts") or []
    if not isinstance(tools, list) or not isinstance(suggestions, list):
        raise DemoAssetsError("invalid_model_lists")
    meta["toolIds"] = [x for x in tools if x not in old_tools and x not in item["tool_ids"]] + item["tool_ids"]
    # Retire only exact, formerly shipped starter rows; preserve local edits.
    retired = item.get("retired_suggestions", []) if ees else []
    suggestions = [row for row in suggestions if row not in retired]
    previous_key = (previous or {}).get("suggestion_key", "suggestionPrompts")
    previous_suggestions = (previous or {}).get("suggestions", [])
    old_content = ({x["content"] for x in previous_suggestions}
                   if previous_key == "suggestion_prompts" else set())
    new_content = {x["content"] for x in item["suggestions"]}
    for proposed in item["suggestions"]:
        if proposed["content"] not in old_content:
            matches = [row for row in suggestions if isinstance(row, dict)
                       and row.get("content") == proposed["content"]]
            if matches and matches != [proposed]:
                raise DemoAssetsError("suggestion_collision")
    meta["suggestion_prompts"] = [x for x in suggestions if not (isinstance(x, dict)
        and x.get("content") in old_content | new_content)] + item["suggestions"]
    if previous and previous_key == "suggestionPrompts" and "suggestionPrompts" in meta:
        # The legacy projection has already verified its managed rows. Remove
        # only those exact rows and preserve any unrelated camelCase metadata.
        remaining = [row for row in (meta["suggestionPrompts"] or [])
                     if row not in previous_suggestions]
        if remaining:
            meta["suggestionPrompts"] = remaining
        else:
            meta.pop("suggestionPrompts")
    meta["ees_demo_pack"] = PACK
    if not ees:
        result["name"] = item["name"]
        meta["capabilities"] = _dict(meta.get("capabilities") or {})
        meta["capabilities"]["memory"] = False
    return result


def _get_path(kind, identifier):
    encoded = quote(identifier, safe="")
    if kind == "model":
        return "/api/v1/models/model?id=" + encoded
    return "/api/v1/tools/id/" + encoded + ("/valves" if kind == "valves" else "")


def _write_path(kind, identifier, create):
    if kind == "model":
        return "/api/v1/models/" + ("create" if create else "model/update")
    if kind == "valves":
        return _get_path(kind, identifier) + "/update"
    return "/api/v1/tools/create" if create else _get_path(kind, identifier) + "/update"


def _is_work_order_tool(current):
    """Identify a candidate, never authorize its replacement from its name alone."""
    meta = current.get("meta") or {}
    if isinstance(meta, dict) and (meta.get("manifest") or {}).get("title") == "EES WO Demo":
        return True
    content = current.get("content")
    if not isinstance(content, str):
        return False
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return bool(re.search(r"(?m)^title:\s*EES WO Demo\s*$", content))
    if re.search(r"(?m)^title:\s*EES WO Demo\s*$", ast.get_docstring(tree, clean=False) or ""):
        return True
    methods = {node.name for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == "Tools"
               for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {"ems_demo_find_equipment", "wo_demo_view", "wo_demo_update"} <= methods


def _existing_work_order(client, ees, item, state, reserved_ids):
    """Adopt only an exact known source already bound to this EES model."""
    bound = (ees.get("meta") or {}).get("toolIds") or []
    if not isinstance(bound, list) or any(not isinstance(identifier, str) for identifier in bound):
        raise DemoAssetsError("invalid_model_lists")
    for key, record in state["assets"].items():
        if (key.startswith("tool:") and record.get("spec", {}).get("existing_only")
                and record.get("status") == "pending" and key[5:] not in bound):
            raise DemoAssetsError("pending_work_order_unbound", key[5:])
    matches = []
    for identifier in dict.fromkeys(bound):
        if identifier in reserved_ids:
            continue
        current = client.request("GET", _get_path("tool", identifier))
        record = state["assets"].get("tool:" + identifier)
        tracked = bool(record and record.get("spec", {}).get("existing_only"))
        if current is None:
            if tracked:
                raise DemoAssetsError("managed_field_conflict", identifier)
            continue
        if not tracked and not _is_work_order_tool(current):
            continue
        if current.get("id") != identifier:
            raise DemoAssetsError("response_id_mismatch", identifier)
        if not isinstance(current.get("content"), str):
            raise DemoAssetsError("tool_source_not_readable", identifier)
        if not tracked and _source_digest(current["content"]) not in item["accepted_source_sha256"]:
            raise DemoAssetsError("unrecognized_existing_wo_source", identifier)
        matches.append(("tool", identifier, item, current, False))
    if len(matches) > 1:
        raise DemoAssetsError("ambiguous_existing_work_order")
    return matches


def _regular(path, directory=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise DemoAssetsError("unsafe_journal_path")


def _state_path(state_dir):
    state_dir = Path(state_dir).absolute()
    for parent in (state_dir, *state_dir.parents):
        _regular(parent, directory=True)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    _regular(state_dir, directory=True)
    path = state_dir.resolve() / STATE_FILE
    _regular(path)
    return path


def _save(path, state):
    _regular(path.parent, directory=True)
    _regular(path)
    temp = None
    try:
        # mkstemp creates a new unpredictable private file; an old *.tmp link is
        # never opened. Replace changes the directory entry, not a link target.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                prefix=".ees-demo-assets-", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _regular(path.parent, directory=True)
        _regular(path)
        _regular(temp)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def apply_assets(client, root: Path, state_dir: Path, ees_model_id: str, source_commit: str):
    """Apply analysis assets and a recognized existing WO tool, then existing EES.

    client.request(method, path, body=None) returns decoded JSON; missing GETs
    return None only for HTTP 404. Other errors propagate as safe generic codes.
    """
    changed, active, pending = 0, "", set()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise DemoAssetsError("invalid_source_commit")
        manifest = load_manifest(root)
        if ees_model_id in {m["id"] for m in manifest["models"]}:
            raise DemoAssetsError("ees_id_collision")
        path = _state_path(state_dir)
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "schema": 1, "pack": PACK, "ees_model_id": ees_model_id, "assets": {}}
        if (state.get("schema") != 1 or state.get("pack") != PACK
                or state.get("ees_model_id") != ees_model_id or not isinstance(state.get("assets"), dict)):
            raise DemoAssetsError("state_scope_mismatch")
        pending = {key for key, row in state["assets"].items() if row.get("status") == "pending"}
        ees = client.request("GET", _get_path("model", ees_model_id))
        if not ees or ees.get("id") != ees_model_id or not ees.get("base_model_id"):
            raise DemoAssetsError("existing_ees_required", ees_model_id)
        # The GET route can redact params even for an administrator while the
        # update route still allows writes. Never merge from a redacted model.
        if ees.get("write_access") is not True:
            raise DemoAssetsError("model_write_access_required", ees_model_id)
        if not ees.get("is_active"):
            raise DemoAssetsError("ees_inactive", ees_model_id)
        grants = _read_grants(ees)
        candidates = []
        for item in manifest["tools"]:
            active = item["id"]
            current = client.request("GET", _get_path("tool", active))
            candidates.append(("tool", active, item, current, False))
            if item.get("managed_valves"):
                current_valves = client.request("GET", _get_path("valves", active)) if current else None
                candidates.append(("valves", active, {"ees_model_id": ees_model_id}, current_valves or {}, False))
        for item in manifest.get("optional_existing_tools", []):
            candidates.extend(_existing_work_order(client, ees, item, state,
                                                  {tool["id"] for tool in manifest["tools"]}))
        for item in manifest["models"]:
            active = item["id"]
            candidates.append(("model", active, item, client.request("GET", _get_path("model", active)), False))
        candidates.append(("model", ees_model_id, manifest["ees"], ees, True))
        new_tools = {identifier for kind, identifier, _, current, _ in candidates
                     if kind == "tool" and current is None}
        plan = []
        for kind, identifier, item, current, is_ees in candidates:
            active = identifier
            key = kind + ":" + identifier
            record = state["assets"].get(key)
            if current is not None and kind != "valves" and current.get("id") != identifier:
                raise DemoAssetsError("response_id_mismatch", identifier)
            if kind == "tool" and current is not None and not isinstance(current.get("content"), str):
                raise DemoAssetsError("tool_source_not_readable", identifier)
            if kind == "model" and current is not None and current.get("write_access") is not True:
                raise DemoAssetsError("model_write_access_required", identifier)
            spec = _spec(item, kind, is_ees)
            previous = None
            if record:
                if record.get("status") not in ("applied", "pending"):
                    raise DemoAssetsError("invalid_journal", identifier)
                # A lost write response is accepted only if the intended managed fields match.
                got = _projection(current, kind, record["spec"])
                pending_view = _view(current, kind)
                if record["status"] == "pending" and record.get("before") is None and pending_view:
                    pending_view.pop("user_id", None)
                if got == record["desired"] and (record["status"] == "applied"
                        or pending_view == record.get("desired_value")):
                    previous = record["spec"]
                elif record["status"] == "pending" and _view(current, kind) == record["before"]:
                    previous = record.get("previous_spec")
                else:
                    raise DemoAssetsError("managed_field_conflict", identifier)
            elif current is not None and kind != "valves":
                if not is_ees and not spec.get("existing_only"):
                    raise DemoAssetsError("asset_id_collision", identifier)
                if is_ees and (_block((current.get("params") or {}).get("system", "")) is not None or (
                        current.get("meta") or {}).get("ees_demo_pack") is not None):
                    raise DemoAssetsError("untracked_managed_region", identifier)
            if kind == "valves":
                if not record and current.get("ees_model_id") not in (None, "", ees_model_id):
                    raise DemoAssetsError("managed_field_conflict", identifier)
                desired = {**current, **item}
            elif kind == "tool":
                desired = _payload(current, kind) if current else {
                    "id": identifier, "name": item["name"], "content": item["content"],
                    "meta": {"description": "EES 합성 데이터 시연", "manifest": {"ees_demo_pack": PACK}},
                    "access_grants": grants}
                desired["content"] = item["content"]
                if not spec.get("existing_only"):
                    desired["name"] = item["name"]
                desired["meta"].setdefault("manifest", {})["ees_demo_pack"] = PACK
            else:
                template = current or {"id": identifier, "name": item["name"], "base_model_id": ees["base_model_id"],
                    "params": {k: copy.deepcopy(v) for k, v in ees["params"].items() if k != "system"},
                    "meta": {}, "is_active": True, "access_grants": grants}
                desired = _merge_model(template, item, is_ees, previous)
            plan.append({"kind": kind, "id": identifier, "key": key, "current": current,
                         "body": desired, "spec": spec, "previous_spec": previous})
        # Everything above is read-only. Persist intent before each non-transactional API write.
        for step in plan:
            active = step["id"]
            kind, body, current = step["kind"], step["body"], step["current"]
            fresh = client.request("GET", _get_path(kind, active))
            if kind == "valves":
                fresh = fresh or {}
                if active in new_tools:
                    # The newly created Tools.Valves may expose defaults which
                    # did not exist at preflight. Preserve them as the baseline.
                    if fresh.get("ees_model_id") not in (None, "", ees_model_id):
                        raise DemoAssetsError("managed_field_conflict", active)
                    current = _dict(fresh)
                    body = {**current, **body}
            if _view(fresh, kind) != _view(current, kind):
                raise DemoAssetsError("concurrent_edit", active)
            record = {"status": "pending", "source_commit": source_commit,
                      "version": manifest["version"], "spec": step["spec"],
                      "previous_spec": step["previous_spec"], "before": _view(current, kind),
                      "previous_value": _payload(current, kind) if current is not None else None,
                      "desired": _projection(body, kind, step["spec"]),
                      "source_hash": _hash(body)}
            wanted = _view(body, kind)
            actual = _view(current, kind)
            if actual is not None:
                wanted["user_id"] = actual["user_id"] if "user_id" in actual else None
                if "user_id" not in actual:
                    wanted.pop("user_id", None)
            record["desired_value"] = wanted
            if actual != wanted:
                state["assets"][step["key"]] = record
                _save(path, state)
                pending.add(step["key"])
                client.request("POST", _write_path(kind, active, current is None), body)
                changed += 1
                fresh = client.request("GET", _get_path(kind, active))
                if fresh is None:
                    raise DemoAssetsError("verification_failed", active)
                result = _view(fresh, kind)
                # New objects obtain their owner from authenticated API creation.
                if current is None:
                    result.pop("user_id", None)
                if result != wanted or _projection(fresh, kind, step["spec"]) != record["desired"]:
                    raise DemoAssetsError("verification_failed", active)
            else:
                # Preserve the last mutation's prior values, including a lost-response
                # write recovered by re-read. An idempotent run is not a new backup.
                old_record = state["assets"].get(step["key"])
                if old_record:
                    for field in ("before", "previous_value", "previous_spec"):
                        record[field] = copy.deepcopy(old_record.get(field))
            record["status"] = "applied"
            state["assets"][step["key"]] = record
            _save(path, state)
            pending.discard(step["key"])
        client.request("GET", "/api/models")
        state.update(source_commit=source_commit, version=manifest["version"], result="ok")
        _save(path, state)
        return {"result": "ok", "changed": changed, "assets": len(plan), "source_commit": source_commit}
    except KeyboardInterrupt:
        # A cancelled POST may already have committed on the server. Keep the
        # persisted intent and expose uncertainty to the operator's retry flow.
        raise DemoAssetsError("operation_interrupted", active, changed, bool(pending)) from None
    except DemoAssetsError as exc:
        exc.changed = changed
        exc.pending = exc.unknown = bool(pending)
        if not exc.asset:
            exc.asset = active
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        if not isinstance(code, str) or code not in TRANSPORT_CODES:
            code = "asset_apply_failed"
        raise DemoAssetsError(code, active, changed, bool(pending)) from None
