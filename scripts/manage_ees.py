"""Operate one registered EES instance without replacing its data or credentials.

Use manage-ees.ps1 on Windows. Deployment changes program environments only;
Agent Pack API synchronization is a separate, not-yet-implemented operation.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
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
import ees_deploy_report as reports
import ees_deploy_state as states
import ees_webui_customization as customization

DEFAULT_HEALTH_TIMEOUT = 300


class DeploymentError(RuntimeError):
    def __init__(self, message, *, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics


FAILURE_STAGES = frozenset({
    "preflight", "select_program", "port_check", "process_start", "process_record",
    "health_check", "process_stop", "stop_record", "backup", "backup_record", "switch_record",
    "inspect_bundle", "apply", "restore",
})
ERROR_TYPES = frozenset({"launch_uncertain", "process", "state", "release", "deployment", "os_error", "unexpected"})
RECOVERY_STATES = frozenset({"not_attempted", "blocked", "failed", "succeeded"})
FAILURE_REASONS = ("health_timeout", "process_exited", "identity_unavailable", "identity_changed",
                   "launch_failed", "launch_unverified", "termination_failed", "termination_timeout",
                   "stop_signal_failed", "stop_helper_failed", "stop_helper_timeout", "stop_timeout", "accept_guard_incompatible")


def safe_log_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"server-[0-9a-f]{32}\.log", value) else None


def safe_seconds(value):
    return round(value, 3) if type(value) in (int, float) and 0 <= value <= 86400 and math.isfinite(value) else None


def safe_candidate(value):
    value = value if isinstance(value, dict) else {}
    kind, commit = value.get("kind"), value.get("source_commit")
    return {"kind": kind if kind in ("original", "release") else "unknown",
            "source_commit": commit if kind == "release" and isinstance(commit, str)
            and re.fullmatch(r"[0-9a-f]{40}", commit) else None}


def safe_failure_detail(value):
    """Project a saved diagnostic onto fixed labels and numeric codes only."""
    value = value if isinstance(value, dict) else {}
    return {
        "stage": value.get("stage") if value.get("stage") in tuple(FAILURE_STAGES) else "preflight",
        "error_type": value.get("error_type") if value.get("error_type") in tuple(ERROR_TYPES) else "unexpected",
        "operation": value.get("operation") if value.get("operation") in (
            "port_probe", "port_bind", "process_open", "process_inspect", "process_terminate", "process_wait",
            "console_attach", "console_signal", "stop_helper") else None,
        "errno": value.get("errno") if type(value.get("errno")) is int else None,
        "winerror": value.get("winerror") if type(value.get("winerror")) is int else None,
        "reason": value.get("reason") if value.get("reason") in FAILURE_REASONS else None,
        "elapsed_seconds": safe_seconds(value.get("elapsed_seconds")),
        "timeout_seconds": safe_seconds(value.get("timeout_seconds")),
        "exit_code": value.get("exit_code") if type(value.get("exit_code")) is int
        and -(2 ** 31) <= value["exit_code"] <= 2 ** 32 - 1 else None,
        "log_id": safe_log_id(value.get("log_id")),
    }


def failure_detail(progress, error):
    error_type = next((label for cls, label in (
        (processes.LaunchUncertain, "launch_uncertain"), (processes.ProcessError, "process"),
        (states.StateError, "state"), (releases.ReleaseError, "release"),
        (DeploymentError, "deployment"), (OSError, "os_error"),
    ) if isinstance(error, cls)), "unexpected")
    return safe_failure_detail({"stage": progress.get("stage"), "error_type": error_type,
                                "operation": getattr(error, "operation", None),
                                "errno": getattr(error, "errno", None), "winerror": getattr(error, "winerror", None),
                                "reason": getattr(error, "reason", None),
                                "elapsed_seconds": getattr(error, "elapsed_seconds", None),
                                "timeout_seconds": getattr(error, "timeout_seconds", None),
                                "exit_code": getattr(error, "exit_code", None),
                                "log_id": safe_log_id(getattr(error, "log_id", None)) or progress.get("log_id")})


def safe_last_failure(value):
    if not isinstance(value, dict):
        return None
    timestamp = value.get("failed_at")
    result = {
        "action": value.get("action") if value.get("action") in ("deploy", "rollback") else "unknown",
        "failed_at": timestamp if isinstance(timestamp, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp) else None,
        "switch": safe_failure_detail(value.get("switch")),
        "recovery": safe_failure_detail(value["recovery"]) if isinstance(value.get("recovery"), dict) else None,
        "recovery_status": value.get("recovery_status") if value.get("recovery_status") in tuple(RECOVERY_STATES) else "not_attempted",
    }
    if "evidence_version" in value:
        result.update(evidence_version=1 if type(value["evidence_version"]) is int and value["evidence_version"] == 1 else None,
                      candidate=safe_candidate(value.get("candidate")),
                      recovery_log_id=safe_log_id(value.get("recovery_log_id")))
    return result


def remember_failure(registry, event, progress, error, *, selected=None):
    registry["last_failure"] = {
        "evidence_version": 1, "candidate": safe_candidate(selected), "recovery_log_id": None,
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
        value = json.loads(states._regular(registry_path(config)).read_text(encoding="utf-8"))
        if (type(value["schema_version"]) is not int or value["schema_version"] not in (1, 2)
                or value["phase"] not in {"idle", "switching", "recovery_required"}):
            raise ValueError()
        customization.validate_registry(value)
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise DeploymentError("Deployment record is missing or invalid; inspect the local state before continuing.") from None


def lock_owner(value):
    return (isinstance(value, dict) and set(value) == {"pid", "executable", "created_at"}
            and type(value["pid"]) is int and 1 <= value["pid"] <= 0xFFFFFFFF
            and isinstance(value["executable"], str) and bool(value["executable"])
            and isinstance(value["created_at"], str) and bool(value["created_at"]))


@contextmanager
def locked(config, *, restore=False, track_owner=False):
    path = Path(config["state_root"]) / "deployment.lock"
    # Only file replacement has a resumable transaction owner. Preserve the
    # existing lock behavior for operations without such a transaction.
    owner = processes._identity(os.getpid()) if track_owner or restore else os.getpid()
    if (track_owner or restore) and not lock_owner(owner):
        raise DeploymentError("The operation owner could not be identified; no files were changed.")
    if restore and path.exists():
        # Only Restore may recover an exact, dead, recorded transaction owner.
        # PID reuse, inaccessible processes and old PID-only locks remain blocked.
        content = states._regular(path).read_bytes()
        try:
            saved = json.loads(content)
        except (ValueError, UnicodeError):
            saved = None
        registry = read_registry(config)
        pending = registry.get("customization", {}).get("pending") or {}
        if (not lock_owner(saved) or pending.get("owner") != saved
                or processes._identity(saved["pid"]) is not None):
            raise DeploymentError("The interrupted-operation lock cannot be safely reclaimed; it was preserved.")
        if states._regular(path).read_bytes() != content:
            raise DeploymentError("The operation lock changed; it was preserved.")
        path.unlink()
    try:
        handle = path.open("x", encoding="ascii")
    except FileExistsError:
        raise DeploymentError("Another operation or interrupted-operation lock exists; do not start a second deployment.") from None
    try:
        with handle:
            json.dump(owner, handle, ensure_ascii=True, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        yield owner
    finally:
        # Never remove a lock that was replaced by another operation.
        if path.exists() and json.loads(states._regular(path).read_bytes()) == owner:
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


def probe_imports(config, commit):
    """Compare the known import chain without starting either application."""
    import ees_deploy_imports as imports

    with locked(config):
        registry = read_registry(config)
        require_legacy(registry)
        require_idle(registry)
        if registry.get("pending") or registry.get("launch_uncertain"):
            raise DeploymentError("Resolve the unfinished deployment before comparing imports.")
        if registry["current"]["kind"] != "original":
            raise DeploymentError("Import comparison requires the original program to remain selected.")
        target = target_for(config, commit)
        candidate = target / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if any(releases._linked(parent) for parent in (candidate.parent, *candidate.parent.parents)):
            raise DeploymentError("Prepared import comparison paths cannot contain links.")
        metadata = json.loads(states._regular(target / "release.json").read_bytes())
        if (not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int
                or metadata.get("schema_version") != 1
                or metadata.get("state") != "prepared" or metadata.get("source_commit") != commit
                or metadata.get("webui_version") != releases.branding.VERSION
                or metadata.get("source_python") != config["source_python"]
                or metadata.get("venv_dir") != str(target / "venv")
                or metadata.get("target_python") != str(candidate)
                or metadata.get("python_executable") != str(candidate)
                or metadata.get("metadata_sha256") != releases._metadata_digest(metadata)
                or not candidate.is_file()):
            raise DeploymentError("Prepared import comparison metadata does not match this candidate.")
        # Static selection only: this is not a new inventory or deployment check.
        result = imports.compare(config["source_python"], str(candidate))
        result["source_commit"] = commit
        result["recorded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result["report_saved"] = True
        report_path = Path(config["state_root"]) / "last-import-probe.json"
        try:
            if report_path.exists() or report_path.is_symlink():
                states._regular(report_path)
            write_json(report_path, result)
        except (OSError, ValueError, TypeError, states.StateError):
            # Preserve this run's console evidence even if an older report remains.
            result["report_saved"] = False
        return result


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
        if "ca_bundle_sha256" in selected:
            raise DeploymentError("Windows CA selection is supported only for an EES release.")
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
    if "ca_bundle_sha256" in selected:
        ca_path = releases.windows_ca_path(target_for(config, commit), selected["ca_bundle_sha256"])
        child_env["REQUESTS_CA_BUNDLE"] = str(ca_path)
        child_env["SSL_CERT_FILE"] = str(ca_path)
    return metadata["target_python"], child_env


def require_idle(registry):
    if registry["phase"] != "idle":
        raise DeploymentError("A previous switch needs recovery; use status and stop before attempting another operation.")


def require_legacy(registry):
    if registry["schema_version"] != 1:
        raise DeploymentError("This instance uses Apply/Restore; the previous candidate workflow is disabled.")


def selected_program(config, registry):
    """Validate the app selection before even returning already_running."""
    if "runtime_ca_sha256" in registry:
        if registry["schema_version"] != 2:
            raise DeploymentError("Runtime Windows CA selection requires the Apply/Restore wrapper.")
        releases.windows_ca_path(Path(config["state_root"]), registry["runtime_ca_sha256"])
    if registry["schema_version"] == 1:
        return None
    customization.validate_registry(registry)
    selected = registry["current"]
    if selected != {"kind": "original", "source_commit": None, "python": config["source_python"]}:
        raise DeploymentError("The wrapper must use the registered original interpreter.")
    value = registry["customization"]
    if value["pending"]:
        if value["pending"]["action"] == "apply" and value["pending"]["stage"] == "promote":
            raise DeploymentError("Program promotion is incomplete; use Restore or, after manual promotion, Apply --resume before Start.")
        raise DeploymentError("Program file replacement is incomplete; use Restore before Start.")
    active = value["active"]
    if active:
        return customization.validate_program(Path(config["state_root"]) / "program", active)
    return None


def program_result(registry):
    value = registry.get("customization", {})
    active, pending = value.get("active"), value.get("pending")
    return {"source_commit": active["source_commit"] if active else registry["current"].get("source_commit"),
            "original_program": registry["current"]["kind"] == "original" and not active and not pending,
            "program_incomplete": bool(pending)}


def require_stopped(config, registry):
    if registry.get("launch_uncertain"):
        raise DeploymentError("The last process launch is unverified; no program files were changed.")
    if registry.get("process") and processes._identity(registry["process"].get("pid")) is not None:
        raise DeploymentError("Stop the registered server before changing program files.")
    require_free_port(config)


def customize(config, args):
    env = states.runtime_environment(config)
    check_only = getattr(args, "check_only", False)
    resume = getattr(args, "resume", False)
    if check_only:
        # Deliberately no lock creation, report write, app import or server stop.
        registry = read_registry(config)
        require_idle(registry)
        if registry.get("pending") or registry.get("launch_uncertain"):
            raise DeploymentError("The existing operation is incomplete; program changes are blocked.")
        if not resume:
            selected_program(config, registry)
            customization.check_applicability(config, registry, env)
        if (Path(config["state_root"]) / "deployment.lock").exists():
            raise DeploymentError("Another operation or interrupted-operation lock exists; CheckOnly was stopped.")
        if registry["current"] != {"kind": "original", "source_commit": None, "python": config["source_python"]}:
            raise DeploymentError("Apply requires the registered original interpreter and program baseline.")
        selection = customization.inspect_bundle(config, args.bundle, commit_id(args.commit), env)
        if resume:
            customization.check_resume(config, registry, env, selection)
        processes.check_accept_runtime(config["source_python"], config["cwd"])
        if read_registry(config) != registry or (Path(config["state_root"]) / "deployment.lock").exists():
            raise DeploymentError("The deployment changed during CheckOnly; no applicability result was accepted.")
        return {"checked": True, "changed": False, "source_commit": selection["source_commit"],
                "already_applied": registry.get("customization", {}).get("active") == selection,
                "requires_stopped_server": True, "data_changed": False}
    with locked(config, restore=args.action == "restore", track_owner=True) as owner:
        registry = read_registry(config)
        require_stopped(config, registry)
        if args.action == "apply":
            require_idle(registry)
            if resume:
                if registry["current"] != {"kind": "original", "source_commit": None, "python": config["source_python"]}:
                    raise DeploymentError("Apply requires the registered original interpreter and program baseline.")
                return customization.resume_apply(config, registry, args.bundle, commit_id(args.commit), env, record, owner)
            selected_program(config, registry)
            return customization.apply(config, registry, args.bundle, commit_id(args.commit), env, record, owner)
        return customization.restore(config, registry, record, owner)


def require_free_port(config):
    if not processes.port_is_free(config["host"], config["port"], raise_on_error=True):
        raise DeploymentError("The configured port is unavailable; no unrelated process was stopped.")


def start_selected(config, selected, env, registry, health_timeout=DEFAULT_HEALTH_TIMEOUT, *, progress=None):
    progress = progress if progress is not None else {}
    progress.pop("log_id", None)
    progress["stage"] = "select_program"
    executable, child_env = selected_environment(config, selected, env)
    program = selected_program(config, registry)
    if "runtime_ca_sha256" in registry:
        ca_path = releases.windows_ca_path(Path(config["state_root"]), registry["runtime_ca_sha256"])
        child_env["REQUESTS_CA_BUNDLE"] = str(ca_path)
        child_env["SSL_CERT_FILE"] = str(ca_path)
    progress["stage"] = "port_check"
    require_free_port(config)
    progress["stage"] = "process_start"
    try:
        identity = processes.start_server(executable, config["cwd"], child_env,
                                          config["host"], config["port"], Path(config["state_root"]) / "logs",
                                          **({"program_path": str(program),
                                              "program_version": registry["customization"]["active"]["webui_version"]}
                                             if program else {}))
    except processes.LaunchUncertain as error:
        progress["log_id"] = safe_log_id(getattr(error, "log_id", None))
        registry["phase"] = "recovery_required"
        registry["launch_uncertain"] = True
        try:
            record(config, registry, "process_identity_unavailable_after_launch")
        except (OSError, ValueError, TypeError):
            raise processes.LaunchUncertain("A server launch is unverified and its state could not be saved; "
                                            "inspect the local process before continuing.",
                                            reason="launch_unverified", log_id=progress["log_id"]) from None
        raise
    log_file = identity.get("log_file")
    progress["log_id"] = safe_log_id(Path(log_file).name) if isinstance(log_file, str) else None
    registry["process"] = identity
    # Persist identity before health probing, including startup failures.
    progress["stage"] = "process_record"
    record(config, registry, "process_started")
    progress["stage"] = "health_check"
    processes.wait_healthy(identity, timeout=health_timeout)
    progress["accept_guard"] = processes.accept_guard_status(identity)
    return identity


def stop_registered(config, registry, *, progress=None):
    progress = progress if progress is not None else {}
    progress["stage"] = "process_stop"
    if registry.get("launch_uncertain"):
        raise DeploymentError("A launched process could not be identified. Inspect and stop that process locally before recovering the deployment record.")
    if registry.get("process"):
        log_file = registry["process"].get("log_file")
        progress["log_id"] = safe_log_id(Path(log_file).name) if isinstance(log_file, str) else None
        try:
            processes.stop_server(registry["process"])
        except processes.ProcessError as error:
            error.stage = "process_stop"
            if not error.log_id:
                error.log_id = progress["log_id"]
            raise
        registry["process"] = None
        progress["stage"] = "stop_record"
        record(config, registry, "process_stopped")
    progress["stage"] = "port_check"
    require_free_port(config)


def plan(config, args):
    states.runtime_environment(config)
    registry = read_registry(config)
    require_legacy(registry)
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
        registry = read_registry(config)
        require_legacy(registry)
        require_idle(registry)
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


def switch(config, selected, event, health_timeout=DEFAULT_HEALTH_TIMEOUT, *, use_windows_ca=False):
    env = states.runtime_environment(config)
    with locked(config):
        registry = read_registry(config)
        require_legacy(registry)
        require_idle(registry)
        if selected is None:
            if not registry.get("previous"):
                raise DeploymentError("No previously active program has been recorded.")
            selected = dict(registry["previous"])
        old = dict(registry["current"])
        progress = {"stage": "select_program"}
        try:
            old_executable, _ = selected_environment(config, old, env)
            processes.check_accept_runtime(old_executable, config["cwd"])
            if use_windows_ca:
                if selected["kind"] != "release":
                    raise DeploymentError("Windows CA selection is supported only for an EES release.")
                executable, _ = selected_environment(config, selected, env)
                digest = releases.prepare_windows_ca(target_for(config, selected["source_commit"]), executable, env,
                                                     cwd=config["cwd"])
                selected = dict(selected, ca_bundle_sha256=digest)
            executable, _ = selected_environment(config, selected, env)
            processes.check_accept_runtime(executable, config["cwd"])
            if selected == old and registry.get("process") and processes.verify_identity(registry["process"]):
                progress["stage"] = "health_check"
                processes.wait_healthy(registry["process"], timeout=health_timeout)
                return {"already_current": True, "source_commit": selected.get("source_commit")}
            stop_registered(config, registry, progress=progress)
        except Exception as error:
            remember_failure(registry, event, progress, error, selected=selected)
            raise reported_failure(config, registry, "switch_preflight_failed",
                                   "Switch preflight failed; no replacement program was started. Inspect local state.") from None
        registry["phase"] = "switching"
        registry["pending"] = selected
        try:
            record(config, registry, "switch_started")
        except (OSError, ValueError, TypeError) as error:
            remember_failure(registry, event, {"stage": "switch_record"}, error, selected=selected)
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
            remember_failure(registry, event, progress, error, selected=selected)
            if registry.get("launch_uncertain"):
                registry["last_failure"]["recovery_status"] = "blocked"
                raise reported_failure(config, registry, "process_identity_unavailable_after_launch",
                                       "A process launch needs local inspection. Automatic recovery was blocked to avoid two servers using the same data.") from None
            # Never start the old server while the candidate still owns the DB/port.
            recovery_progress = {}
            try:
                stop_registered(config, registry, progress=recovery_progress)
                start_selected(config, old, env, registry, health_timeout=health_timeout, progress=recovery_progress)
            except Exception as recovery_error:
                registry["last_failure"]["recovery"] = failure_detail(recovery_progress, recovery_error)
                registry["last_failure"]["recovery_log_id"] = registry["last_failure"]["recovery"]["log_id"]
                registry["last_failure"]["recovery_status"] = "failed"
                registry["phase"] = "recovery_required"
                raise reported_failure(config, registry, "automatic_program_recovery_failed",
                                       "Switch failed and recovery needs attention. No database restore was attempted; inspect local state and server logs.") from None
            registry["phase"] = "idle"
            registry.pop("pending", None)
            registry["last_failure"]["recovery_status"] = "succeeded"
            registry["last_failure"]["recovery_log_id"] = safe_log_id(recovery_progress.get("log_id"))
            raise reported_failure(config, registry, "previous_program_recovered",
                                   "Switch failed; the previous program is running again. Existing data was not restored or replaced.") from None
        registry["previous"] = old
        registry["current"] = selected
        registry["phase"] = "idle"
        registry.pop("pending", None)
        try:
            record(config, registry, event)
        except (OSError, ValueError, TypeError) as error:
            remember_failure(registry, event, {**progress, "stage": "switch_record"}, error, selected=selected)
            raise DeploymentError("Program health succeeded but activation could not be recorded; "
                                  "no automatic recovery was attempted. Retain this diagnostic and inspect local state.",
                                  diagnostics=safe_last_failure(registry["last_failure"])) from None
    return {"active": True, "source_commit": selected.get("source_commit"), "data_restored": False}


def operate(args):
    if args.action == "init":
        return initialize(args)
    config = states.load_config(args.config)
    if args.action == "start" and getattr(args, "check_only", False):
        # This check is intentionally usable while the registered server is live.
        # No lock/report writes, health wait, socket bind, app import or Stop.
        registry = read_registry(config)
        require_idle(registry)
        lock = Path(config["state_root"]) / "deployment.lock"
        if registry.get("launch_uncertain") or lock.exists():
            raise DeploymentError("The deployment is busy or unverified; preflight stopped.")
        selected_program(config, registry)
        env = states.runtime_environment(config)
        executable, _ = selected_environment(config, registry["current"], env)
        try:
            guard = processes.check_accept_runtime(executable, config["cwd"])
        except processes.ProcessError as error:
            error.stage = "preflight"
            raise
        if read_registry(config) != registry or lock.exists():
            raise DeploymentError("The deployment changed during preflight; no result was accepted.")
        return {"checked": True, "changed": False, "stage": "preflight", "accept_guard": guard,
                **program_result(registry)}
    if args.action in ("apply", "restore"):
        return customize(config, args)
    if args.action in ("plan", "prepare", "deploy", "rollback", "probe-imports", "diagnose"):
        require_legacy(read_registry(config))
    if args.action == "probe-imports":
        return probe_imports(config, commit_id(args.commit))
    if args.action == "plan":
        return plan(config, args)
    if args.action == "prepare":
        return prepare(config, args)
    if args.action == "deploy":
        commit = commit_id(args.commit)
        env = states.runtime_environment(config)
        metadata = releases.validate_prepared(target_for(config, commit), commit, config["source_python"], env=env)
        return switch(config, {"kind": "release", "source_commit": commit, "python": metadata["target_python"]},
                      "deployed", health_timeout=args.health_timeout,
                      use_windows_ca=getattr(args, "use_windows_ca", False))
    if args.action == "rollback":
        return switch(config, None, "rolled_back_program", health_timeout=args.health_timeout)
    if args.action == "diagnose":
        states._regular(registry_path(config))
        registry = read_registry(config)
        candidate = reports.collect(config, registry)
        try:
            if registry.get("process"):
                running = processes.verify_identity(registry["process"])
                process_check = "identity_matched" if running else "identity_not_matched"
            else:
                running, process_check = False, "not_recorded"
        except (processes.ProcessError, OSError, ValueError, TypeError, KeyError):
            running, process_check = None, "inspection_unavailable"
        try:
            states._regular(registry_path(config))
            unchanged = read_registry(config) == registry and not (Path(config["state_root"]) / "deployment.lock").exists()
        except (DeploymentError, states.StateError, OSError, ValueError, TypeError):
            unchanged = False
        if not unchanged:
            candidate = {"status": "unavailable", "reason": "state_changed_or_busy"}
            running, process_check = None, "state_changed_or_busy"
        return {"report_version": 2, "phase": registry["phase"],
                "original_program": registry["current"]["kind"] == "original",
                "managed_process_running": running, "process_check": process_check,
                "last_failure": safe_last_failure(registry.get("last_failure")),
                "candidate": candidate}
    if args.action == "status":
        registry = read_registry(config)
        active = registry.get("customization", {}).get("active")
        pending = registry.get("customization", {}).get("pending")
        valid = None
        if registry["schema_version"] == 2:
            try:
                selected_program(config, registry)
                valid = True
            except (ValueError, OSError, DeploymentError, states.StateError):
                valid = False
        return {"phase": registry["phase"], "current_commit": active["source_commit"] if active else registry["current"].get("source_commit"),
                "original_program": registry["current"]["kind"] == "original" and not active and not pending,
                "managed_process_running": bool(registry.get("process") and processes.verify_identity(registry["process"])),
                "rollback_available": registry["schema_version"] == 1 and registry.get("previous") is not None,
                "restore_available": registry.get("customization", {}).get("previous") is not None or bool(pending),
                "program_valid": valid, "program_incomplete": bool(pending),
                "ca_mode": "windows_snapshot" if "ca_bundle_sha256" in registry["current"]
                or "runtime_ca_sha256" in registry else "registered",
                "last_failure": safe_last_failure(registry.get("last_failure"))}
    with locked(config):
        env = states.runtime_environment(config)
        registry = read_registry(config)
        if args.action == "stop":
            stop_registered(config, registry)
            if not registry.get("customization", {}).get("pending"):
                registry["phase"] = "idle"
                registry.pop("pending", None)
            record(config, registry, "stopped_by_operator")
            return {"stopped": True, "data_changed": False, **program_result(registry)}
        use_windows_ca = getattr(args, "use_windows_ca", False)
        if use_windows_ca and registry["schema_version"] != 2:
            raise DeploymentError("Start --use-windows-ca requires the Apply/Restore wrapper.")
        selected_program(config, registry)
        require_idle(registry)
        if registry.get("process") and processes.verify_identity(registry["process"]):
            if use_windows_ca:
                raise DeploymentError("Stop the existing server before changing runtime trust.")
            try:
                processes.wait_healthy(registry["process"], timeout=args.health_timeout)
            except processes.ProcessError as error:
                error.stage = "health_check"
                raise
            return {"already_running": True, **program_result(registry)}
        progress = {}
        try:
            if use_windows_ca:
                progress["stage"] = "select_program"
                executable, _ = selected_environment(config, registry["current"], env)
                progress["stage"] = "port_check"
                require_free_port(config)
                progress["stage"] = "select_program"
                digest = releases.prepare_windows_ca(Path(config["state_root"]), executable, env,
                                                     cwd=config["cwd"])
                releases.windows_ca_path(Path(config["state_root"]), digest)
                registry["runtime_ca_sha256"] = digest
                # Keep this selection for ordinary Start, including after a health timeout.
                record(config, registry, "runtime_windows_ca_selected")
            start_selected(config, registry["current"], env, registry, health_timeout=args.health_timeout, progress=progress)
        except (processes.ProcessError, DeploymentError, releases.ReleaseError, OSError) as error:
            error.stage = progress.get("stage", "start")
            raise
        record(config, registry, "started_by_operator")
        return {"started": True, "accept_guard": progress["accept_guard"], **program_result(registry)}


def render_diagnosis(result):
    """Keep the allowlisted report short enough to share as one result or photos."""
    failure = result["last_failure"] or {}
    detail = failure.get("switch") or {}
    candidate = result["candidate"]
    lines = ["EES diagnosis v2", json.dumps({key: result[key] for key in (
        "phase", "original_program", "managed_process_running", "process_check")}),
        "failure: " + json.dumps({"at": failure.get("failed_at"), "action": failure.get("action"),
            "stage": detail.get("stage"), "error_type": detail.get("error_type"),
            "reason": detail.get("reason"), "recovery": failure.get("recovery_status")}),
        "health: " + json.dumps({key: detail.get(key) for key in (
            "elapsed_seconds", "timeout_seconds", "exit_code")})]
    if failure.get("candidate"):
        lines.append("program: " + json.dumps(failure["candidate"]))
    if failure.get("recovery"):
        lines.append("recovery_failure: " + json.dumps({key: failure["recovery"].get(key) for key in (
            "stage", "error_type", "reason", "elapsed_seconds", "timeout_seconds", "exit_code")}))
    if candidate["status"] != "ok":
        return "\n".join(lines + ["candidate: " + json.dumps(candidate)])
    lines += ["candidate: " + json.dumps({key: candidate[key] for key in (
        "selection", "candidate_seconds", "recovery_seconds", "scan_scope", "log_bytes", "bytes_read")}),
        "signals: " + json.dumps(candidate["signals"]),
        "errors: " + json.dumps(candidate["error_types"]),
        "traceback: " + json.dumps({key: candidate.get(key) for key in (
            "tracebacks_seen", "last_traceback_header_seen", "frames_omitted", "unknown_frames",
            "first_error_type", "first_error_matches_last_traceback", "first_error_frames_omitted",
            "first_error_unknown_frames", "first_error_traceback_header_seen")})]
    if candidate.get("first_error_frames"):
        lines += ["first_error_in_read_scope:", *candidate["first_error_frames"]]
    return "\n".join(lines + ["last_traceback:", *candidate["frames"]])


LOCAL_ERROR_TYPES = frozenset({
    "OSError", "PermissionError", "FileNotFoundError", "FileExistsError", "NotADirectoryError",
    "IsADirectoryError", "ValueError", "KeyError", "TypeError", "UnicodeEncodeError",
    "UnicodeDecodeError", "JSONDecodeError",
    "ProcessError", "LaunchUncertain", "DeploymentError", "CustomizationError", "StateError", "ReleaseError",
})
LOCAL_ERROR_SOURCES = frozenset({
    "manage_ees.py", "ees_webui_customization.py", "ees_deploy_state.py",
    "ees_deploy_release.py", "ees_deploy_process.py", "ees_upgrade.py",
})


def safe_local_error(value):
    """Only fixed labels and bounded numbers; never exception text or file paths."""
    value = value if isinstance(value, dict) else {}
    kind, source, line = value.get("type"), value.get("source"), value.get("line")
    source = source if isinstance(source, str) and source in LOCAL_ERROR_SOURCES else None
    return {
        "type": kind if isinstance(kind, str) and kind in LOCAL_ERROR_TYPES else "unknown",
        "errno": value.get("errno") if type(value.get("errno")) is int and 0 <= value["errno"] <= 0xFFFFFFFF else None,
        "winerror": value.get("winerror") if type(value.get("winerror")) is int and 0 <= value["winerror"] <= 0xFFFFFFFF else None,
        "source": source,
        "line": line if source and type(line) is int and 1 <= line <= 1000000 else None,
    }


def local_error_detail(error):
    # Match complete checkout paths, then retain only the innermost known code
    # location. Traceback text, source lines, exception args and locals stay out.
    sources = {os.path.normcase(os.path.abspath(Path(__file__).with_name(name))): name
               for name in LOCAL_ERROR_SOURCES}
    source, line, frame = None, None, error.__traceback__
    while frame is not None:
        name = sources.get(os.path.normcase(os.path.abspath(frame.tb_frame.f_code.co_filename)))
        if name:
            source, line = name, frame.tb_lineno
        frame = frame.tb_next
    return safe_local_error({"type": type(error).__name__, "errno": getattr(error, "errno", None),
                             "winerror": getattr(error, "winerror", None), "source": source, "line": line})


def safe_program_rename(value):
    """Only fixed rename stages and bounded counters; never paths or error text."""
    if not isinstance(value, dict):
        return None
    stage, attempts, waited = value.get("stage"), value.get("attempts"), value.get("waited_seconds")
    if (not isinstance(stage, str) or stage not in {"move_active", "promote", "restore"}
            or type(attempts) is not int or not 1 <= attempts <= 5
            or type(waited) is not int or not 0 <= waited <= 15):
        return None
    return {"stage": stage, "attempts": attempts, "waited_seconds": waited}


def program_rename_detail(error):
    winerror = getattr(error, "winerror", None)
    if (not isinstance(error, OSError) or type(winerror) is not int or winerror not in (5, 32, 33)
            or getattr(error, "program_rename_failed", None) is not True):
        return None
    return safe_program_rename({"stage": getattr(error, "program_rename_stage", None),
                               "attempts": getattr(error, "program_rename_attempts", None),
                               "waited_seconds": getattr(error, "program_rename_wait_seconds", None)})


def failure_fields(result):
    """Safe one-line details shared by direct operations and Upgrade."""
    fields = ""
    process = safe_failure_detail(result.get("process"))
    number = lambda value: str(value) if value is not None else "-"
    if "local_error" in result:
        error = safe_local_error(result["local_error"])
        location = f"{error['source']}:{error['line']}" if error["source"] and error["line"] else "-"
        fields = (f" error={error['type']} errno={number(error['errno'])}"
                  f" winerror={number(error['winerror'])} at={location}")
    elif process["error_type"] == "process":
        fields = f" error=process errno={number(process['errno'])} winerror={number(process['winerror'])}"
    if process["error_type"] in ("process", "launch_uncertain"):
        fields += (f" operation={process['operation'] or '-'} reason={process['reason'] or '-'}"
                   f" seconds={number(process['elapsed_seconds'])} timeout={number(process['timeout_seconds'])}"
                   f" exit={number(process['exit_code'])}")
    rename = safe_program_rename(result.get("program_rename"))
    if rename:
        fields += (f" rename={rename['stage']} attempts={rename['attempts']}"
                   f" waited={rename['waited_seconds']}")
    return fields


def render_summary(action, result, *, failed=False):
    def flag(value):
        return "true" if value is True else "false" if value is False else "-"
    commit = result.get("source_commit") or result.get("current_commit")
    commit = commit[:12] if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) else "-"
    stage = result.get("stage", "complete")
    # Fixed labels only: never echo paths, environment, artifact payloads or logs.
    stages = {"complete", "preflight", "inspect_bundle", "apply", "restore", "start", "stop", "status",
              "select_program", "port_check", "process_start", "process_record", "health_check", "process_stop", "stop_record"}
    stage = stage if isinstance(stage, str) and stage in stages else action
    program = ("incomplete" if result.get("program_incomplete") else "invalid" if result.get("program_valid") is False
               else "original" if result.get("original_program") is True
               else "customized" if result.get("original_program") is False else "-")
    detail = failure_fields(result) if failed else ""
    if result.get("accept_guard") in ("compatible", "win64_retry", "not_applicable"):
        detail += f" guard={result['accept_guard']}"
    return (f"EES action={action} result={'failed' if failed else 'ok'} changed={flag(result.get('changed'))} "
            f"commit={commit} stage={stage} program={program} "
            f"running={flag(result.get('managed_process_running', result.get('started', result.get('already_running'))))}{detail}")


def save_operation(args, result, *, failed=False):
    """Keep the last result and retain the last failure across later successes."""
    if getattr(args, "check_only", False) or args.action == "status":
        return True
    try:
        config = states.load_config(args.config)
        target = Path(config["state_root"]) / "last-operation.json"
        failure = Path(config["state_root"]) / "last-failure.json"
        for path in (target, failure) if failed else (target,):
            if path.exists() or path.is_symlink():
                states._regular(path)
        payload = {"action": args.action, "failed": failed,
                   "at": datetime.now(timezone.utc).isoformat(), "result": result}
        if failed:
            write_json(failure, payload)
        write_json(target, payload)
        return True
    except (OSError, ValueError, TypeError, KeyError, states.StateError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "status", "diagnose", "probe-imports", "plan", "prepare", "deploy", "rollback", "start", "stop", "apply", "restore"])
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
    parser.add_argument("--check-only", action="store_true", help="Read-only Apply or Start preflight; never imports or stops the app.")
    parser.add_argument("--resume", action="store_true", help="Explicitly finish Apply after its staged program was manually renamed.")
    parser.add_argument("--summary", action="store_true", help="Print a single safe line for manual result handoff.")
    parser.add_argument("--health-timeout", type=health_timeout_arg, default=DEFAULT_HEALTH_TIMEOUT,
                        help="Seconds to wait for each server's health (default: 300; range: 1-900).")
    parser.add_argument("--use-windows-ca", action="store_true",
                        help="Select Windows CA trust for a stopped Apply/Restore Start or a legacy Deploy.")
    args = parser.parse_args(argv)
    if args.check_only and args.action not in ("apply", "start"):
        parser.error("--check-only is supported only with apply or start.")
    if args.check_only and args.use_windows_ca:
        parser.error("--check-only cannot change runtime trust.")
    if args.resume and args.action != "apply":
        parser.error("--resume is supported only with apply.")
    if args.summary and args.action not in ("apply", "restore", "start", "stop", "status"):
        parser.error("--summary is supported with Apply/Restore/Start/Stop/Status only.")
    if args.use_windows_ca and args.action not in ("deploy", "start"):
        parser.error("--use-windows-ca is supported only with deploy or start.")
    needed = {"init": ["source_python", "cwd", "data_dir", "listen_host", "port", "uv"],
              "plan": ["bundle", "commit"], "prepare": ["bundle", "commit"], "deploy": ["commit"],
              "probe-imports": ["commit"], "apply": ["bundle", "commit"]}
    if any(getattr(args, name) is None for name in needed.get(args.action, [])):
        parser.error("Missing arguments for the requested operation.")
    try:
        result = operate(args)
    except (DeploymentError, states.StateError, releases.ReleaseError, processes.ProcessError,
            customization.CustomizationError) as error:
        reason = getattr(error, "reason", None)
        result = {"stage": getattr(error, "stage", args.action), "changed": None,
                  "reason": reason if reason in FAILURE_REASONS else "operation_failed",
                  "process": failure_detail({"stage": getattr(error, "stage", args.action)}, error),
                  "local_error": local_error_detail(error)}
        saved = save_operation(args, result, failed=True)
        if args.summary:
            print(render_summary(args.action, result, failed=True) + (" report=unavailable" if not saved else ""))
            return 1
        if isinstance(error, processes.ProcessError):
            parser.exit(1, render_summary(args.action, result, failed=True)
                        + (" report=unavailable" if not saved else "") + "\n")
        # Module errors deliberately contain no settings, keys, API responses, or child logs.
        diagnostics = safe_last_failure(error.diagnostics) if isinstance(error, DeploymentError) else None
        detail = "\nDiagnostics: " + json.dumps(diagnostics) if diagnostics else ""
        parser.exit(1, f"Operation stopped: {error}{detail}" + ("\nReport unavailable." if not saved else "") + "\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        detail = local_error_detail(error)
        result = {"stage": args.action, "reason": "local_state_or_file_unavailable",
                  "changed": None, "local_error": detail}
        rename = program_rename_detail(error)
        if rename:
            result["program_rename"] = rename
        saved = save_operation(args, result, failed=True)
        if args.summary:
            print(render_summary(args.action, result, failed=True) + (" report=unavailable" if not saved else ""))
            return 1
        parser.exit(1, "Operation stopped: local state or a required file could not be inspected.\n"
                    + "Local error: " + json.dumps(detail) + ("\nReport unavailable." if not saved else "") + "\n")
    if args.summary:
        saved = save_operation(args, result)
        print(render_summary(args.action, result) + (" report=unavailable" if not saved else ""))
        return 0
    if args.action == "probe-imports":
        import ees_deploy_imports as imports
        print(imports.render(result))
    else:
        print(render_diagnosis(result) if args.action == "diagnose" else json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
