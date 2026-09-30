"""Explicit operator recovery of one saved Upgrade process_stop failure.

No network, graceful-stop retry, tree kill, dependency install, or data restore.
The operator must authorize termination and capture the failure/registry before
updating the wrapper. The ordinary Stop and Upgrade never invoke this command.
"""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manage_ees as manager
import ees_upgrade as upgrade
import ees_deploy_stop_target as targets


class RecoveryError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_request(config, path):
    path = manager.states._regular(path)
    root = Path(config["state_root"]).resolve()
    if (path.resolve().parent != root
            or not re.fullmatch(r"stop-recovery-[0-9a-f]{32}\.json", path.name)
            or path.stat().st_size > 1024 * 1024):
        raise RecoveryError("invalid_recovery_request")
    try:
        value = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise RecoveryError("invalid_recovery_request") from None
    if not isinstance(value, dict) or set(value) != {"failure", "registry"}:
        raise RecoveryError("invalid_recovery_request")
    return value


def validate_failure(config, request, commit):
    failure = request["failure"]
    result = failure.get("result", {}) if isinstance(failure, dict) else {}
    detail = result.get("process", {}) if isinstance(result, dict) else {}
    if (not isinstance(failure, dict) or failure.get("action") != "upgrade"
            or failure.get("failed") is not True or not isinstance(result, dict)
            or result.get("stage") != "process_stop" or result.get("changed") is not False
            or not isinstance(detail, dict) or detail.get("error_type") != "process"
            or result.get("wrapper_commit") != commit):
        raise RecoveryError("not_the_approved_stop_failure")
    bundle = result.get("bundle")
    if not isinstance(bundle, str):
        raise RecoveryError("retained_bundle_missing")
    bundle = manager.states._regular(Path(bundle))
    root = Path(config["state_root"]).resolve()
    manager.states._safe(bundle.parent)
    # Local trial Upgrade retains its prepared ZIP under trial-build- rather
    # than the release downloader's upgrade- directory. Require its saved
    # source marker before accepting that additional producer-owned location.
    allowed_parent = (bundle.parent.name.startswith("upgrade-")
                      or (result.get("source_verification") == "local_trial"
                          and bundle.parent.name.startswith("trial-build-")))
    if (bundle.resolve().parent.parent != root
            or not allowed_parent
            or bundle.name != "EES-demo-" + commit[:12] + ".zip"):
        raise RecoveryError("retained_bundle_mismatch")
    return bundle


def recover(config, args, progress):
    if not args.terminate_recorded_process:
        raise RecoveryError("explicit_termination_authorization_required")
    commit = manager.commit_id(args.commit)
    request = read_request(config, args.request)
    bundle = validate_failure(config, request, commit)
    progress["bundle"] = str(bundle)
    with manager.locked(config, track_owner=True) as owner:
        registry = manager.read_registry(config)
        if registry != request["registry"]:
            raise RecoveryError("deployment_changed")
        env = manager.states.runtime_environment(config)
        progress["stage"] = "preflight"
        upgrade.preflight(config, registry, env)
        identity = registry.get("process")
        if (registry.get("schema_version") != 2 or not isinstance(identity, dict)
                or identity.get("host") != config["host"]
                or identity.get("port") != config["port"]
                or identity.get("group_id") != identity.get("pid")
                or not registry.get("customization", {}).get("active")):
            raise RecoveryError("recorded_server_mismatch")
        # The approved incident has no listener. Do not terminate a recovered
        # service or any process after the recorded deployment has changed.
        manager.require_free_port(config)
        manager.customization.inspect_bundle(config, bundle, commit, env)
        if (manager.read_registry(config) != registry
                or read_request(config, args.request) != request):
            raise RecoveryError("deployment_changed")
        manager.require_free_port(config)
        progress["stage"] = "process_stop"
        progress["terminated"] = None
        progress["terminated"] = targets.terminate_server_target(identity, config["source_python"])
        # The target helper verifies that any redirector exited naturally and
        # that no server descendants remain before this point.
        manager.require_stopped(config, registry)
        registry["process"] = None
        progress["stage"] = "stop_record"
        manager.record(config, registry, "stop_recovered_by_operator")
        # Keep the same data/key/settings protection as the ordinary trial
        # Upgrade. A completed termination does not authorize skipping backup.
        progress["stage"] = "backup"
        saved = manager.states.backup_state(config)
        registry["last_backup"] = saved
        progress["stage"] = "backup_record"
        manager.record(config, registry, "data_backup_verified")
        progress["backup_verified"] = True
        progress["stage"] = "apply"
        progress["changed"] = None
        manager.customization.apply(config, registry, bundle, commit, env, manager.record, owner)
        progress["changed"] = True
        manager.start_selected(config, registry["current"], env, registry,
                               health_timeout=args.health_timeout, progress=progress)
        manager.record(config, registry, "stop_recovery_applied_by_operator")
        return {"stage": "complete", "changed": True, "started": True,
                "backup_verified": True,
                "terminated": progress["terminated"], **manager.program_result(registry)}


def report(args, result, failed=False):
    saved = manager.save_operation(argparse.Namespace(action="recover_stop", config=args.config),
                                   result, failed=failed)
    flag = lambda value: "true" if value is True else "false" if value is False else "-"
    def word(value):
        return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9_.+-]{1,80}", value) else "-"
    commit = result.get("source_commit")
    commit = commit[:12] if isinstance(commit, str) and upgrade.HEX40.fullmatch(commit) else "-"
    detail = manager.safe_failure_detail(result.get("process"))
    diagnostics = (f" operation={word(detail['operation'])} errno={detail['errno']}"
                   f" winerror={detail['winerror']}" if failed else "")
    backup = "verified" if result.get("backup_verified") is True else "unverified"
    print(f"EES action=recover_stop result={'failed' if failed else 'ok'} "
          f"changed={flag(result.get('changed'))} terminated={flag(result.get('terminated'))} "
          f"backup={backup} "
          f"commit={commit} stage={word(result.get('stage'))} "
          f"running={flag(result.get('started'))} code={word(result.get('code'))}" + diagnostics
          + (" report=unavailable" if not saved else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--terminate-recorded-process", action="store_true")
    parser.add_argument("--health-timeout", type=manager.health_timeout_arg, default=120)
    args = parser.parse_args(argv)
    progress = {"stage": "configuration", "changed": False, "terminated": False,
                "backup_verified": False}
    try:
        config = manager.states.load_config(args.config)
        result = recover(config, args, progress)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, KeyboardInterrupt) as error:
        if (progress["stage"] == "process_stop" and progress["terminated"] is None
                and hasattr(error, "terminated")):
            progress["terminated"] = error.terminated if type(error.terminated) is bool else None
        result = dict(progress, code=getattr(error, "code", None)
                      or getattr(error, "reason", None) or "recovery_failed",
                      process=manager.failure_detail(progress, error))
        report(args, result, failed=True)
        return 1
    report(args, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
