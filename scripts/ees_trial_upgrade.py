"""Build and apply an explicitly reviewed local main without GitHub Actions."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ees_upgrade as upgrade
import ees_apply_demo as demo
import ees_trial_bundle as bundles

manager = upgrade.manager


def trial_checkout(commit):
    upgrade.checkout(commit)
    if upgrade.git("rev-parse", "origin/main")[1] != commit:
        raise upgrade.UpgradeError("trial_main_mismatch")
    return commit


def deploy(config, commit, timeout, progress):
    """Prepare fully before Stop; reuse the existing locked Apply/Start path."""
    with manager.locked(config, track_owner=True) as owner:
        progress["stage"] = "trial_source"
        trial_checkout(commit)
        progress["wrapper_commit"] = commit
        env = manager.states.runtime_environment(config)
        registry = manager.read_registry(config)
        progress["stage"] = "preflight"
        upgrade.preflight(config, registry, env)
        active = registry.get("customization", {}).get("active")
        if active and active["source_commit"] == commit:
            # A repeat of the exact applied source only needs program/health
            # validation before the independently idempotent managed assets.
            progress["stage"] = "health_check"
            upgrade.healthy_noop(registry, timeout)
            return {"changed": False, "prepared": False, "started": True,
                    "version": active["webui_version"], **manager.program_result(registry)}

        progress["stage"] = "prepare_bundle"
        _, proxy = upgrade.git("config", "--get-urlmatch", "http.proxy",
                               upgrade.REPOSITORY + ".git", optional=True)
        bundle = bundles.prepare(config, commit, proxy or None, progress)
        progress["bundle"] = str(bundle)
        progress["stage"] = "inspect_bundle"
        manager.customization.inspect_bundle(config, bundle, commit, env)
        progress["stage"] = "preflight"
        trial_checkout(commit)
        if manager.read_registry(config) != registry:
            raise upgrade.UpgradeError("deployment_changed")
        if manager.states.runtime_environment(config) != env:
            raise upgrade.UpgradeError("environment_changed")
        upgrade.preflight(config, registry, env)

        # The downloader, source, complete bundle, retained program and reused
        # interpreter checks have all succeeded before the server is stopped.
        trial_checkout(commit)
        print("EES upgrade step=stop", flush=True)
        manager.stop_registered(config, registry, progress=progress)
        manager.require_stopped(config, registry)
        progress["stage"] = "backup"
        print("EES upgrade step=backup", flush=True)
        saved = manager.states.backup_state(config)
        registry["last_backup"] = saved
        progress["stage"] = "backup_record"
        manager.record(config, registry, "data_backup_verified")
        progress["backup_verified"] = True

        progress["stage"] = "apply"
        progress["changed"] = None
        print("EES upgrade step=apply", flush=True)
        manager.customization.apply(config, registry, bundle, commit, env, manager.record, owner)
        progress["changed"] = True
        manager.start_selected(config, registry["current"], env, registry,
                               health_timeout=timeout, progress=progress)
        manager.record(config, registry, "trial_upgraded_by_operator")
        active = registry["customization"]["active"]
        return {"changed": True, "prepared": True, "started": True,
                "backup_verified": True, "version": active["webui_version"],
                **manager.program_result(registry)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--trial-commit", required=True,
                        help="Full lowercase SHA of the reviewed, updated canonical main checkout.")
    parser.add_argument("--health-timeout", type=manager.health_timeout_arg, default=120)
    args = parser.parse_args(argv)
    if not upgrade.HEX40.fullmatch(args.trial_commit):
        parser.error("Trial commit requires a full lowercase commit SHA.")
    progress = {"stage": "configuration", "changed": False}
    try:
        config = manager.states.load_config(args.config)
        result = deploy(config, args.trial_commit, args.health_timeout, progress)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, EOFError, KeyboardInterrupt) as error:
        code = getattr(error, "code", None) or getattr(error, "reason", None) or "operation_failed"
        stage = progress["stage"]
        rename = manager.program_rename_detail(error)
        if rename:
            code = "program_rename_blocked"
        next_step = ("update_reviewed_main" if stage == "trial_source"
                     else "check_status" if stage == "health_check" or code == "server_not_running"
                     else "inspect_apply" if stage == "apply"
                     else "check_download_access" if stage in {"prepare_bundle", "upstream_download"}
                     else "inspect_local_result")
        if stage == "apply" and rename and rename["stage"] == "promote" and upgrade.manual_promote_ready(config):
            next_step = "manual_promote"
        result = {"stage": stage, "code": code, "changed": progress.get("changed"),
                  "wrapper_commit": progress.get("wrapper_commit"), "wrapper_changed": False,
                  "source_verification": "local_trial", "next": next_step,
                  "backup_verified": progress.get("backup_verified", False),
                  "process": manager.failure_detail(progress, error),
                  "local_error": manager.local_error_detail(error)}
        if "bundle" in progress:
            result["bundle"] = progress["bundle"]
        if rename:
            result["program_rename"] = rename
        upgrade.report(args, result, failed=True)
        return 1

    result.update(wrapper_commit=args.trial_commit, wrapper_changed=False,
                  source_verification="local_trial", next="apply_demo", stage="complete")
    upgrade.report(args, result)
    # Release the program lock before the existing asset command takes its own
    # lock. Its report remains authoritative on partial asset failures.
    code = demo.main(["--config", str(args.config), "--trial-commit", args.trial_commit])
    if code == 0 and "bundle" in progress:
        bundles.cleanup(config, Path(progress["bundle"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
