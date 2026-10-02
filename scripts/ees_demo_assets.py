"""Read historical asset journals and prevent retired demo registration.

The caller supplies authenticated transport, endpoint/version checks, a private local
state directory and an exclusive deployment lock. No WebUI imports or DB access.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from pathlib import Path

PACK = "ees-demo-v1"
BEGIN = "<!-- EES-DEMO:BEGIN -->"
END = "<!-- EES-DEMO:END -->"
STATE_FILE = "ees-demo-assets.json"
ASSET_API = "/api/v1/ees/assets"


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


def load_manifest(root: Path):
    """Return the empty registration contract; historical packs cannot reactivate it."""
    manifest = _dict(json.loads(_read_source(root, "agent-pack/ees-demo.json")), "invalid_manifest")
    if manifest.get("registration") != "retired" or any(manifest.get(key) for key in ("tools", "models", "optional_existing_tools")):
        raise DemoAssetsError("demo_registration_retired")
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


def apply_assets(client, root: Path, state_dir: Path, ees_model_id: str, source_commit: str):
    """Compatibility stop: never authenticate, read a DB, or resurrect retired content."""
    raise DemoAssetsError("demo_registration_retired", changed=0)


def retirement_main(argv=None):
    """Explicit operator API entry; ordinary installation never calls this function.

    Plans contain only IDs, hashes and readiness, and must be reviewed before apply.
    Full restoration bytes are saved privately on the Native server before deletion.
    """
    import argparse
    import sys
    import ees_apply_demo as operator

    parser = argparse.ArgumentParser(description="Preview, explicitly retire or restore known managed demo assets. Program Restore does not restore assets.")
    parser.add_argument("action", choices=("preview", "apply", "restore"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--webui-url")
    parser.add_argument("--ca-file")
    parser.add_argument("--kind", choices=("tool", "model"))
    parser.add_argument("--id")
    parser.add_argument("--baseline-sha256", help="Full managed asset state hash verified against the historical registration/backup; not a guessed current value")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--approve-plan-sha256")
    parser.add_argument("--request-id")
    parser.add_argument("--backup-sha256")
    args = parser.parse_args(argv)
    try:
        if args.action == "preview" and (not args.kind or not args.id or not args.plan
                or not re.fullmatch(r"[0-9a-f]{64}", args.baseline_sha256 or "")):
            raise DemoAssetsError("retirement_preview_arguments_required")
        if args.action == "apply" and (not args.plan or not re.fullmatch(r"[0-9a-f]{64}", args.approve_plan_sha256 or "")):
            raise DemoAssetsError("retirement_plan_approval_required")
        if args.action == "restore" and (not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", args.request_id or "")
                or not re.fullmatch(r"[0-9a-f]{64}", args.backup_sha256 or "")):
            raise DemoAssetsError("retirement_restore_arguments_required")
        config = operator.upgrade.manager.states.load_config(args.config)
        settings_args = argparse.Namespace(webui_url=args.webui_url, ca_file=args.ca_file, ees_model_id=None)
        _, settings = operator.connection(config, settings_args)
        token, _ = operator.load_token(config, settings["url"])
        client = operator.WebUIClient(settings["url"], token, settings["ca_file"])
        capability = client.request("GET", ASSET_API + "/capabilities")
        if not isinstance(capability, dict) or capability.get("retirement") != 1:
            raise DemoAssetsError("retirement_unavailable")
        if args.action == "preview":
            preview = client.request("POST", ASSET_API + "/retirement/preview", {
                "kind": args.kind, "id": args.id, "baseline_sha256": args.baseline_sha256})
            plan = {"schema": 1, "endpoint_sha256": _hash(settings["url"]),
                    "baseline_sha256": args.baseline_sha256, "preview": preview}
            if args.plan.exists() or args.plan.is_symlink():
                raise DemoAssetsError("retirement_plan_already_exists")
            _regular(args.plan.parent, directory=True)
            # Plan files are private and must not be placed in Git or shared evidence.
            fd = os.open(args.plan, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(plan, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            result = {"eligible": preview["eligible"], "blocked_reasons": preview["blocked_reasons"],
                      "plan_sha256": _hash(plan), "changed": 0}
        elif args.action == "apply":
            _regular(args.plan)
            if args.plan.stat().st_size > 65536:
                raise DemoAssetsError("invalid_retirement_plan")
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if _hash(plan) != args.approve_plan_sha256 or plan.get("endpoint_sha256") != _hash(settings["url"]):
                raise DemoAssetsError("retirement_plan_changed")
            preview = plan["preview"]
            if preview.get("eligible") is not True:
                raise DemoAssetsError("retirement_preview_blocked")
            result = client.request("POST", ASSET_API + "/retirement/apply", {
                "kind": preview["kind"], "id": preview["id"], "baseline_sha256": plan["baseline_sha256"],
                "expected_token": preview["expected_token"], "request_id": "retire-" + args.approve_plan_sha256})
        else:
            result = client.request("POST", ASSET_API + "/retirement/restore", {
                "request_id": args.request_id, "backup_sha256": args.backup_sha256})
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (DemoAssetsError, operator.DemoError, OSError, ValueError, KeyError, TypeError) as error:
        code = getattr(error, "code", "retirement_failed")
        if not re.fullmatch(r"[a-z_]{1,80}", code):
            code = "retirement_failed"
        print(json.dumps({"result": "blocked", "code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(retirement_main())
