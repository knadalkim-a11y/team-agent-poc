"""Operate one registered EES instance without replacing its data or credentials.

Use manage-ees.ps1 on Windows. Deployment changes program environments only;
Agent Pack API synchronization is a separate, not-yet-implemented operation.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import sys
from datetime import datetime, timezone

# Allow only this checked-out script directory when launched with Python -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ees_deploy_process as processes
import ees_deploy_release as releases
import ees_deploy_state as states

DEFAULT_HEALTH_TIMEOUT = 300


class DeploymentError(RuntimeError):
    def __init__(self, message, *, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics


FAILURE_STAGES = frozenset({
    "preflight", "select_program", "port_check", "process_start", "process_record",
    "health_check", "process_stop", "stop_record", "backup", "backup_record", "switch_record",
})
ERROR_TYPES = frozenset({"launch_uncertain", "process", "state", "release", "deployment", "os_error", "unexpected"})
RECOVERY_STATES = frozenset({"not_attempted", "blocked", "failed", "succeeded"})


def safe_failure_detail(value):
    """Project a saved diagnostic onto fixed labels and numeric codes only."""
    value = value if isinstance(value, dict) else {}
    return {
        "stage": value.get("stage") if value.get("stage") in tuple(FAILURE_STAGES) else "preflight",
        "error_type": value.get("error_type") if value.get("error_type") in tuple(ERROR_TYPES) else "unexpected",
        "operation": value.get("operation") if value.get("operation") in ("port_probe", "port_bind") else None,
        "errno": value.get("errno") if type(value.get("errno")) is int else None,
        "winerror": value.get("winerror") if type(value.get("winerror")) is int else None,
    }


def failure_detail(progress, error):
    error_type = next((label for cls, label in (
        (processes.LaunchUncertain, "launch_uncertain"), (processes.ProcessError, "process"),
        (states.StateError, "state"), (releases.ReleaseError, "release"),
        (DeploymentError, "deployment"), (OSError, "os_error"),
    ) if isinstance(error, cls)), "unexpected")
    return safe_failure_detail({"stage": progress.get("stage"), "error_type": error_type,
                                "operation": getattr(error, "operation", None),
                                "errno": getattr(error, "errno", None), "winerror": getattr(error, "winerror", None)})


def safe_last_failure(value):
    if not isinstance(value, dict):
        return None
    timestamp = value.get("failed_at")
    return {
        "action": value.get("action") if value.get("action") in ("deploy", "rollback") else "unknown",
        "failed_at": timestamp if isinstance(timestamp, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp) else None,
        "switch": safe_failure_detail(value.get("switch")),
        "recovery": safe_failure_detail(value["recovery"]) if isinstance(value.get("recovery"), dict) else None,
        "recovery_status": value.get("recovery_status") if value.get("recovery_status") in tuple(RECOVERY_STATES) else "not_attempted",
    }


def remember_failure(registry, event, progress, error):
    registry["last_failure"] = {
        "action": "rollback" if event == "rolled_back_program" else "deploy",
        "failed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "switch": failure_detail(progress, error), "recovery": None, "recovery_status": "not_attempted",
    }


def reported_failure(config, registry, event, message):
    # Only the existing terminal record is written. A diagnostic write failure
    # must not erase the two captured failures from the operator's output.
    try:
        record(config, registry, event)
    except (OSError, ValueError, TypeError):
        message += " The failure record could not be saved; retain this diagnostic."
    return DeploymentError(message, diagnostics=safe_last_failure(registry.get("last_failure")))


def health_timeout_arg(value):
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError("Health timeout must be an integer from 1 to 900 seconds.") from None
    if not 1 <= seconds <= 900:
        raise argparse.ArgumentTypeError("Health timeout must be an integer from 1 to 900 seconds.")
    return seconds


def write_json(path, value):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".ees-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def registry_path(config):
    return Path(config["state_root"]) / "deployment.json"


def read_registry(config):
    try:
        value = json.loads(registry_path(config).read_text(encoding="utf-8"))
        if value["schema_version"] != 1 or value["phase"] not in {"idle", "switching", "recovery_required"}:
            raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise DeploymentError("Deployment record is missing or invalid; inspect the local state before continuing.") from None


@contextmanager
def locked(config):
    path = Path(config["state_root"]) / "deployment.lock"
    try:
        handle = path.open("x", encoding="ascii")
    except FileExistsError:
        raise DeploymentError("Another operation or interrupted-operation lock exists; do not start a second deployment.") from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def record(config, registry, event):
    registry["last_event"] = event
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(registry_path(config), registry)


def commit_id(value):
    if not value or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise DeploymentError("Use the complete 40-character commit from the selected CI artifact.")
    return value


def target_for(config, commit):
    return Path(config["releases_dir"]) / commit_id(commit)


def initialize(args):
    config = states.init_config(args.config, args.source_python, args.cwd, args.data_dir,
                                args.listen_host, args.port, args.uv)
    registry = {
        "schema_version": 1, "phase": "idle", "process": None, "previous": None,
        "current": {"kind": "original", "source_commit": None, "python": config["source_python"]},
    }
    record(config, registry, "registered_existing_environment")
    return {"registered": True, "server_changed": False, "data_changed": False}


def selected_environment(config, selected, env):
    if selected["kind"] == "original":
        if selected["python"] != config["source_python"]:
            raise DeploymentError("Original interpreter does not match the registered environment.")
        return selected["python"], dict(env)
    if selected["kind"] != "release":
        raise DeploymentError("Selected program kind is invalid; inspect the local deployment record.")
    commit = commit_id(selected["source_commit"])
    metadata = releases.validate_prepared(target_for(config, commit), commit, config["source_python"], env=env)
    if selected["python"] != metadata["target_python"]:
        raise DeploymentError("Selected release interpreter does not match its prepared record.")
    child_env = dict(env)
    child_env["WEBUI_NAME"] = "EES Assistant"
    return metadata["target_python"], child_env


def require_idle(registry):
    if registry["phase"] != "idle":
        raise DeploymentError("A previous switch needs recovery; use status and stop before attempting another operation.")


def require_free_port(config):
    if not processes.port_is_free(config["host"], config["port"], raise_on_error=True):
        raise DeploymentError("The configured port is unavailable; no unrelated process was stopped.")


def start_selected(config, selected, env, registry, health_timeout=DEFAULT_HEALTH_TIMEOUT, *, progress=None):
    progress = progress if progress is not None else {}
    progress["stage"] = "select_program"
    executable, child_env = selected_environment(config, selected, env)
    progress["stage"] = "port_check"
    require_free_port(config)
    progress["stage"] = "process_start"
    try:
        identity = processes.start_server(executable, config["cwd"], child_env,
                                          config["host"], config["port"], Path(config["state_root"]) / "logs")
    except processes.LaunchUncertain:
        registry["phase"] = "recovery_required"
        registry["launch_uncertain"] = True
        try:
            record(config, registry, "process_identity_unavailable_after_launch")
        except (OSError, ValueError, TypeError):
            raise processes.LaunchUncertain("A server launch is unverified and its state could not be saved; "
                                            "inspect the local process before continuing.") from None
        raise
    registry["process"] = identity
    # Persist identity before health probing, including startup failures.
    progress["stage"] = "process_record"
    record(config, registry, "process_started")
    progress["stage"] = "health_check"
    processes.wait_healthy(identity, timeout=health_timeout)
    return identity


def stop_registered(config, registry, *, progress=None):
    progress = progress if progress is not None else {}
    progress["stage"] = "process_stop"
    if registry.get("launch_uncertain"):
        raise DeploymentError("A launched process could not be identified. Inspect and stop that process locally before recovering the deployment record.")
    if registry.get("process"):
        processes.stop_server(registry["process"])
        registry["process"] = None
        progress["stage"] = "stop_record"
        record(config, registry, "process_stopped")
    progress["stage"] = "port_check"
    require_free_port(config)


def plan(config, args):
    states.runtime_environment(config)
    registry = read_registry(config)
    require_idle(registry)
    manifest = releases.validate_bundle(args.bundle, commit_id(args.commit))
    return {
        "source_commit": manifest["source_commit"], "has_program": manifest.get("branding") is not None,
        "current_commit": registry["current"].get("source_commit"),
        "program_restart_required": manifest.get("branding") is not None,
        "preserve_existing_data": True, "agent_pack_applied": False,
        "note": "Only program deployment is implemented; bundled Agent Pack items are not synchronized.",
    }


def prepare(config, args):
    env = states.runtime_environment(config)
    commit = commit_id(args.commit)
    target = target_for(config, commit)
    with locked(config):
        require_idle(read_registry(config))
        if target.exists():
            metadata = releases.validate_prepared(target, commit, config["source_python"], env=env)
            releases.validate_bundle(args.bundle, commit)
            with Path(args.bundle).open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if metadata["bundle_sha256"] != digest:
                raise DeploymentError("This commit already has a different prepared artifact; inspect it before continuing.")
        else:
            metadata = releases.prepare_release(args.bundle, commit, target, config["source_python"],
                                                 config["uv_exe"], wheelhouse=args.wheelhouse, env=env)
    return {"prepared": True, "source_commit": commit, "server_changed": False,
            "webui_version": metadata["webui_version"]}


def switch(config, selected, event, health_timeout=DEFAULT_HEALTH_TIMEOUT):
    env = states.runtime_environment(config)
    with locked(config):
        registry = read_registry(config)
        require_idle(registry)
        if selected is None:
            if not registry.get("previous"):
                raise DeploymentError("No previously active program has been recorded.")
            selected = dict(registry["previous"])
        old = dict(registry["current"])
        progress = {"stage": "select_program"}
        try:
            selected_environment(config, old, env)
            selected_environment(config, selected, env)
            if selected == old and registry.get("process") and processes.verify_identity(registry["process"]):
                progress["stage"] = "health_check"
                processes.wait_healthy(registry["process"], timeout=health_timeout)
                return {"already_current": True, "source_commit": selected.get("source_commit")}
            stop_registered(config, registry, progress=progress)
        except Exception as error:
            remember_failure(registry, event, progress, error)
            raise reported_failure(config, registry, "switch_preflight_failed",
                                   "Switch preflight failed; no replacement program was started. Inspect local state.") from None
        registry["phase"] = "switching"
        registry["pending"] = selected
        try:
            record(config, registry, "switch_started")
        except (OSError, ValueError, TypeError) as error:
            remember_failure(registry, event, {"stage": "switch_record"}, error)
            raise DeploymentError("Switch state could not be saved; no replacement program was started. "
                                  "Retain this diagnostic and inspect local state.",
                                  diagnostics=safe_last_failure(registry["last_failure"])) from None
        try:
            progress["stage"] = "backup"
            backup = states.backup_state(config)
            registry["last_backup"] = backup
            progress["stage"] = "backup_record"
            record(config, registry, "backup_verified")
            start_selected(config, selected, env, registry, health_timeout=health_timeout, progress=progress)
        except Exception as error:
            remember_failure(registry, event, progress, error)
            if registry.get("launch_uncertain"):
                registry["last_failure"]["recovery_status"] = "blocked"
                raise reported_failure(config, registry, "process_identity_unavailable_after_launch",
                                       "A process launch needs local inspection. Automatic recovery was blocked to avoid two servers using the same data.") from None
            # Never start the old server while the candidate still owns the DB/port.
            try:
                stop_registered(config, registry, progress=progress)
                start_selected(config, old, env, registry, health_timeout=health_timeout, progress=progress)
            except Exception as recovery_error:
                registry["last_failure"]["recovery"] = failure_detail(progress, recovery_error)
                registry["last_failure"]["recovery_status"] = "failed"
                registry["phase"] = "recovery_required"
                raise reported_failure(config, registry, "automatic_program_recovery_failed",
                                       "Switch failed and recovery needs attention. No database restore was attempted; inspect local state and server logs.") from None
            registry["phase"] = "idle"
            registry.pop("pending", None)
            registry["last_failure"]["recovery_status"] = "succeeded"
            raise reported_failure(config, registry, "previous_program_recovered",
                                   "Switch failed; the previous program is running again. Existing data was not restored or replaced.") from None
        registry["previous"] = old
        registry["current"] = selected
        registry["phase"] = "idle"
        registry.pop("pending", None)
        try:
            record(config, registry, event)
        except (OSError, ValueError, TypeError) as error:
            remember_failure(registry, event, {"stage": "switch_record"}, error)
            raise DeploymentError("Program health succeeded but activation could not be recorded; "
                                  "no automatic recovery was attempted. Retain this diagnostic and inspect local state.",
                                  diagnostics=safe_last_failure(registry["last_failure"])) from None
    return {"active": True, "source_commit": selected.get("source_commit"), "data_restored": False}


def operate(args):
    if args.action == "init":
        return initialize(args)
    config = states.load_config(args.config)
    if args.action == "plan":
        return plan(config, args)
    if args.action == "prepare":
        return prepare(config, args)
    if args.action == "deploy":
        commit = commit_id(args.commit)
        env = states.runtime_environment(config)
        metadata = releases.validate_prepared(target_for(config, commit), commit, config["source_python"], env=env)
        return switch(config, {"kind": "release", "source_commit": commit, "python": metadata["target_python"]},
                      "deployed", health_timeout=args.health_timeout)
    if args.action == "rollback":
        return switch(config, None, "rolled_back_program", health_timeout=args.health_timeout)
    if args.action == "status":
        registry = read_registry(config)
        return {"phase": registry["phase"], "current_commit": registry["current"].get("source_commit"),
                "original_program": registry["current"]["kind"] == "original",
                "managed_process_running": bool(registry.get("process") and processes.verify_identity(registry["process"])),
                "rollback_available": registry.get("previous") is not None,
                "last_failure": safe_last_failure(registry.get("last_failure"))}
    with locked(config):
        env = states.runtime_environment(config)
        registry = read_registry(config)
        if args.action == "stop":
            stop_registered(config, registry)
            registry["phase"] = "idle"
            registry.pop("pending", None)
            record(config, registry, "stopped_by_operator")
            return {"stopped": True, "data_changed": False}
        require_idle(registry)
        if registry.get("process") and processes.verify_identity(registry["process"]):
            processes.wait_healthy(registry["process"], timeout=args.health_timeout)
            return {"already_running": True}
        start_selected(config, registry["current"], env, registry, health_timeout=args.health_timeout)
        record(config, registry, "started_by_operator")
        return {"started": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "status", "plan", "prepare", "deploy", "rollback", "start", "stop"])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--source-python", type=Path)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--listen-host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--health-timeout", type=health_timeout_arg, default=DEFAULT_HEALTH_TIMEOUT,
                        help="Seconds to wait for each server's health (default: 300; range: 1-900).")
    args = parser.parse_args(argv)
    needed = {"init": ["source_python", "cwd", "data_dir", "listen_host", "port", "uv"],
              "plan": ["bundle", "commit"], "prepare": ["bundle", "commit"], "deploy": ["commit"]}
    if any(getattr(args, name) is None for name in needed.get(args.action, [])):
        parser.error("Missing arguments for the requested operation.")
    try:
        result = operate(args)
    except (DeploymentError, states.StateError, releases.ReleaseError, processes.ProcessError) as error:
        # Module errors deliberately contain no settings, keys, API responses, or child logs.
        diagnostics = safe_last_failure(error.diagnostics) if isinstance(error, DeploymentError) else None
        detail = "\nDiagnostics: " + json.dumps(diagnostics) if diagnostics else ""
        if not diagnostics and isinstance(error, processes.ProcessError):
            detail = "\nDiagnostics: " + json.dumps(failure_detail({}, error))
        parser.exit(1, f"Operation stopped: {error}{detail}\n")
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Operation stopped: local state or a required file could not be inspected. No secrets were printed.\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
