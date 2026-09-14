"""One operator command for verified main updates and program-only deployment."""

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manage_ees as manager
import ees_update_download as downloads

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/knadalkim-a11y/team-agent-poc"
HEX40 = re.compile(r"[0-9a-f]{40}")
# Keep in step with the workflow's program-change decision. Wrapper-only changes
# can reuse an earlier program artifact, but never one with different inputs.
PROGRAM_INPUTS = (
    "branding", "scripts/build_ees_webui.py", "scripts/build_demo_bundle.py",
    "scripts/render_ees_brand_assets.py", "tests/test_ees_branding_build.py",
    "tests/test_demo_bundle.py", ".github/workflows/ees-delivery.yml",
)


class UpgradeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def git(*arguments, optional=False, proxy=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        options = ["-c", "http.proxy=" + proxy] if proxy else []
        result = subprocess.run(["git", *options, "-C", str(ROOT), *arguments], env=env,
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise UpgradeError("git_unavailable") from None
    if result.returncode and not (optional and result.returncode == 1):
        raise UpgradeError("git_failed")
    return result.returncode, result.stdout.strip()


def checkout(expected=None):
    if git("remote", "get-url", "origin")[1] not in (REPOSITORY, REPOSITORY + ".git"):
        raise UpgradeError("wrong_repository")
    if git("branch", "--show-current")[1] != "main":
        raise UpgradeError("main_required")
    if git("status", "--porcelain", "--untracked-files=no")[1]:
        raise UpgradeError("local_changes")
    head = git("rev-parse", "HEAD")[1]
    if not HEX40.fullmatch(head) or (expected is not None and head != expected):
        raise UpgradeError("checkout_changed")
    return head


def compatible_program(commit, head):
    if not HEX40.fullmatch(commit) or not HEX40.fullmatch(head):
        return False
    code, _ = git("merge-base", "--is-ancestor", commit, head, optional=True)
    if code:
        return False
    code, _ = git("diff", "--quiet", commit, head, "--", *PROGRAM_INPUTS, optional=True)
    return code == 0


def token_for(config, reset=False):
    """Separate CurrentUser DPAPI file; never change the server environment."""
    path = Path(config["state_root"]) / "github-update.dpapi"
    if path.exists() or path.is_symlink():
        manager.states._regular(path)
    if path.exists() and not reset:
        if path.stat().st_size > 8192:
            raise UpgradeError("credentials_invalid")
        try:
            token = manager.states._unprotect(path.read_bytes()).decode("ascii")
        except (UnicodeError, ValueError):
            raise UpgradeError("credentials_invalid") from None
    else:
        if not sys.stdin.isatty():
            raise UpgradeError("credentials_required")
        token = getpass.getpass("GitHub Actions read token (hidden, saved for this Windows user): ")
        if not valid_token(token):
            raise UpgradeError("credentials_invalid")
        encrypted = manager.states._protect(token.encode("ascii"))
        # Atomic private-file replacement. No plaintext or token environment var.
        fd, temporary = tempfile.mkstemp(prefix="github-update-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
    if not valid_token(token):
        raise UpgradeError("credentials_invalid")
    return token


def valid_token(token):
    return isinstance(token, str) and 10 <= len(token) <= 512 and all(33 <= ord(c) <= 126 for c in token)


def github_client(config, reset=False):
    # The existing GitHub-scoped Git proxy also applies to the API/download.
    _, proxy = git("config", "--get-urlmatch", "http.proxy", REPOSITORY + ".git", optional=True)
    return downloads.GithubClient(token_for(config, reset), proxy=proxy or None)


def update_only(config, proxy=None):
    """Preserve manual Update semantics, sharing the program-operation lock."""
    with manager.locked(config, track_owner=True):
        before = checkout()
        git("fetch", "origin", "main", proxy=proxy)
        target = git("rev-parse", "origin/main")[1]
        if not HEX40.fullmatch(target):
            raise UpgradeError("checkout_changed")
        if git("merge-base", "--is-ancestor", before, target, optional=True)[0]:
            raise UpgradeError("local_main_ahead_or_diverged")
        checkout(before)
        git("merge", "--ff-only", target)
        checkout(target)
        return {"changed": False, "wrapper_changed": target != before,
                "wrapper_commit": target, "next": "upgrade"}


def bootstrap(config, args, client, progress, *, runner="ees_upgrade.py", runner_options=None):
    """Verify the fetched commit before updating, then execute the updated code."""
    before = checkout()
    progress.update(wrapper_commit=before, wrapper_changed=False)
    if args.prepared_head:
        checkout(args.prepared_head)
        if git("rev-parse", "origin/main")[1] != args.prepared_head:
            raise UpgradeError("checkout_changed")
        return None, args.prepared_head, args.wrapper_before
    progress["stage"] = "git_fetch"
    if (Path(config["state_root"]) / "deployment.lock").exists():
        raise UpgradeError("operation_busy")
    git("fetch", "origin", "main")
    target = git("rev-parse", "origin/main")[1]
    if not HEX40.fullmatch(target):
        raise UpgradeError("checkout_changed")
    if git("merge-base", "--is-ancestor", before, target, optional=True)[0]:
        raise UpgradeError("local_main_ahead_or_diverged")
    progress["stage"] = "ci_check"
    downloads.require_successful_head(client, target)
    if before == target:
        return None, target, before
    progress["stage"] = "wrapper_update"
    with manager.locked(config, track_owner=True):
        checkout(before)
        git("merge", "--ff-only", target)
        checkout(target)
        progress.update(wrapper_commit=target, wrapper_changed=True)
    # Do not continue a deployment using Python modules loaded before git merge.
    command = [sys.executable, "-I", "-B", str(ROOT / "scripts" / runner),
               "--config", str(args.config), "--prepared-head", target,
               "--wrapper-before", before]
    command += (["--health-timeout", str(args.health_timeout)]
                if runner_options is None else list(runner_options))
    try:
        child = subprocess.Popen(command)
    except OSError:
        raise UpgradeError("updated_runner_unavailable") from None
    progress["delegated"] = True
    try:
        code = child.wait()
    except KeyboardInterrupt:
        # The child receives the same console interrupt and owns its transaction
        # report/retained ZIP. Do not replace that report from this stale parent.
        try:
            code = child.wait(timeout=5)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            code = 130
    return code, target, before


def preflight(config, registry, env):
    manager.require_idle(registry)
    if registry.get("pending") or registry.get("launch_uncertain"):
        raise UpgradeError("operation_incomplete")
    if registry["current"] != {"kind": "original", "source_commit": None, "python": config["source_python"]}:
        raise UpgradeError("original_interpreter_required")
    manager.selected_program(config, registry)
    manager.customization.check_applicability(config, registry, env)
    manager.processes.check_accept_runtime(config["source_python"], config["cwd"])


def artifact_key(artifact):
    return {name: artifact[name] for name in ("id", "digest", "source_commit")}


def receipt_matches(config, artifact, active):
    path = Path(config["state_root"]) / "upgrade-receipt.json"
    if not path.exists() and not path.is_symlink():
        return False
    manager.states._regular(path)
    if path.stat().st_size > 8192:
        return False
    try:
        return json.loads(path.read_bytes()) == {"artifact": artifact_key(artifact), "installed": active}
    except (ValueError, UnicodeError):
        return False


def save_receipt(config, artifact, active):
    path = Path(config["state_root"]) / "upgrade-receipt.json"
    if path.exists() or path.is_symlink():
        manager.states._regular(path)
    manager.write_json(path, {"artifact": artifact_key(artifact), "installed": active})


def healthy_noop(registry, timeout):
    identity = registry.get("process")
    if not identity or not manager.processes.verify_identity(identity):
        raise UpgradeError("server_not_running")
    manager.processes.wait_healthy(identity, timeout=min(5, timeout))


def same_program(active, selected):
    return bool(active) and all(active.get(key) == selected[key]
                                for key in ("wheel_sha256", "record_sha256", "webui_version"))


def deploy(config, client, head, timeout, progress):
    progress["stage"] = "artifact_select"
    artifact = downloads.select_program(client, head, lambda sha: compatible_program(sha, head))
    with manager.locked(config, track_owner=True):
        checkout(head)
        env = manager.states.runtime_environment(config)
        baseline = manager.read_registry(config)
        progress["stage"] = "preflight"
        preflight(config, baseline, env)
        active = baseline.get("customization", {}).get("active")
        if active and receipt_matches(config, artifact, active):
            progress["stage"] = "health_check"
            healthy_noop(baseline, timeout)
            return {"changed": False, "downloaded": False, "started": True,
                    "version": active["webui_version"], **manager.program_result(baseline)}
    progress["stage"] = "download"
    print("EES upgrade step=download", flush=True)
    directory = Path(tempfile.mkdtemp(prefix="upgrade-", dir=config["state_root"]))
    completed = False
    try:
        bundle = client.download_artifact(artifact, Path(directory))
        progress["bundle"] = str(bundle)
        with manager.locked(config, track_owner=True) as owner:
            checkout(head)
            env = manager.states.runtime_environment(config)
            registry = manager.read_registry(config)
            if registry != baseline:
                raise UpgradeError("deployment_changed")
            progress["stage"] = "preflight"
            print("EES upgrade step=preflight", flush=True)
            preflight(config, registry, env)
            selected = manager.customization.inspect_bundle(config, bundle, artifact["source_commit"], env)
            active = registry.get("customization", {}).get("active")
            if same_program(active, selected):
                progress["stage"] = "health_check"
                healthy_noop(registry, timeout)
                changed = False
            else:
                # All network/identity/applicability checks finished before Stop.
                checkout(head)
                manager.stop_registered(config, registry, progress=progress)
                manager.require_stopped(config, registry)
                progress["stage"] = "apply"
                progress["changed"] = None
                print("EES upgrade step=apply", flush=True)
                manager.customization.apply(config, registry, bundle, artifact["source_commit"],
                                            env, manager.record, owner)
                progress["changed"] = True
                manager.start_selected(config, registry["current"], env, registry,
                                       health_timeout=timeout, progress=progress)
                manager.record(config, registry, "upgraded_by_operator")
                active = registry["customization"]["active"]
                changed = True
            progress["stage"] = "receipt"
            save_receipt(config, artifact, active)
            completed = True
            return {"changed": changed, "downloaded": True, "started": True,
                    "version": active["webui_version"], **manager.program_result(registry)}
    finally:
        # An interrupted Apply may require its exact ZIP for explicit Resume.
        # Preserve it with the local failure report; do not force a redownload.
        if completed or "bundle" not in progress:
            try:
                shutil.rmtree(directory)
            except OSError:
                pass


def report(args, result, failed=False):
    action = "update" if getattr(args, "update_only", False) else "upgrade"
    saved = manager.save_operation(argparse.Namespace(action=action, config=args.config), result, failed=failed)
    def sha(value):
        return value[:12] if isinstance(value, str) and HEX40.fullmatch(value) else "-"
    def word(value):
        return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9_.+-]{1,64}", value) else "-"
    version = result.get("version")
    version = version if version in manager.customization.branding.PROGRAM_FRONTENDS else "-"
    flag = lambda x: "true" if x is True else "false" if x is False else "-"
    print(f"EES action={action} result={'failed' if failed else 'ok'} "
          f"changed={flag(result.get('changed'))} wrapper_changed={flag(result.get('wrapper_changed'))} "
          f"wrapper={sha(result.get('wrapper_commit'))} commit={sha(result.get('source_commit'))} "
          f"version={version} stage={word(result.get('stage', 'complete'))} "
          f"running={flag(result.get('started'))} code={word(result.get('code'))} "
          f"next={word(result.get('next', 'refresh_browser'))}"
          + (manager.failure_fields(result) if failed else "")
          + (" report=unavailable" if not saved else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--health-timeout", type=manager.health_timeout_arg, default=120)
    parser.add_argument("--reset-token", action="store_true")
    parser.add_argument("--update-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--git-proxy", help=argparse.SUPPRESS)
    parser.add_argument("--prepared-head", help=argparse.SUPPRESS)
    parser.add_argument("--wrapper-before", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if (bool(args.prepared_head) != bool(args.wrapper_before)
            or any(value and not HEX40.fullmatch(value) for value in (args.prepared_head, args.wrapper_before))):
        parser.error("Invalid prepared update identity.")
    if (args.git_proxy and not args.update_only) or (args.update_only and (args.reset_token or args.prepared_head)):
        parser.error("Invalid manual Update options.")
    progress = {"stage": "configuration", "changed": False}
    head = before = None
    try:
        config = manager.states.load_config(args.config)
        checkout()
        if args.update_only:
            progress["stage"] = "wrapper_update"
            result = update_only(config, args.git_proxy)
            report(args, result)
            return 0
        progress["stage"] = "authentication"
        client = github_client(config, args.reset_token)
        print("EES upgrade step=check_release", flush=True)
        child, head, before = bootstrap(config, args, client, progress)
        if child is not None:
            return child
        result = deploy(config, client, head, args.health_timeout, progress)
        result.update(wrapper_commit=head, wrapper_changed=head != before)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, EOFError, KeyboardInterrupt) as error:
        if progress.get("delegated"):
            return 130
        code = getattr(error, "code", None) or getattr(error, "reason", None) or "operation_failed"
        stage = progress["stage"]
        next_step = ("reset_update_token" if stage == "authentication" or code in {"credentials_rejected", "credentials_missing"}
                     else "check_status" if stage == "health_check" or code == "server_not_running"
                     else "inspect_apply" if stage == "apply"
                     else "check_ci" if stage in {"ci_check", "artifact_select"}
                     else "check_download_access" if stage == "download" else "inspect_local_result")
        result = {"stage": stage, "code": code, "changed": progress.get("changed"),
                  "wrapper_commit": head or progress.get("wrapper_commit"),
                  "wrapper_changed": head != before if head and before else progress.get("wrapper_changed"),
                  "next": next_step, "process": manager.failure_detail(progress, error),
                  "local_error": manager.local_error_detail(error)}
        if "bundle" in progress:
            result["bundle"] = progress["bundle"]
        report(args, result, failed=True)
        return 1
    report(args, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
