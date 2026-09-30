"""Trial orchestration preserves the registered instance and stops only after preparation."""

import copy
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import ees_trial_upgrade as trial
from scripts import ees_deploy_stop_recovery as recovery


HEAD = "a" * 40
OLDER = "b" * 40
ROOT = Path(__file__).resolve().parents[1]


class TrialUpgradeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {"state_root": str(self.root), "source_python": "registered-python", "cwd": "registered-cwd"}
        self.environment = {"DATA_DIR": "existing-data", "WEBUI_SECRET_KEY": "synthetic-preserved-key"}
        self.active = {"source_commit": OLDER, "wheel_sha256": "1" * 64,
                       "record_sha256": "2" * 64, "webui_version": "0.11.3+ees.9"}
        self.selected = dict(self.active, source_commit=HEAD, wheel_sha256="3" * 64)
        self.registry = {"schema_version": 2, "phase": "idle", "pending": None,
                         "current": {"kind": "original", "source_commit": None, "python": "registered-python"},
                         "process": {"pid": 123, "executable": "registered-python"},
                         "customization": {"active": self.active, "previous": None, "pending": None}}
        self.events = []
        self.progress = {}
        self.output = io.StringIO()
        self.lock_held = False
        self.mock = {}
        self.bundle = self.root / "trial-build-synthetic" / ("EES-demo-" + HEAD[:12] + ".zip")
        self.bundle.parent.mkdir()
        self.bundle.write_bytes(b"synthetic exact reviewed bundle")

        @contextmanager
        def locked(*args, **kwargs):
            self.assertFalse(self.lock_held)
            self.assertTrue(kwargs.get("track_owner"))
            self.lock_held = True
            self.events.append("lock")
            try:
                yield {"pid": 9, "executable": "registered-python", "created_at": "1"}
            finally:
                self.lock_held = False
                self.events.append("unlock")

        def prepare(config, commit, proxy, progress):
            self.assertTrue(self.lock_held)
            self.assertEqual((config, commit, proxy), (self.config, HEAD, "http://saved-proxy:8080"))
            self.events.append("prepare")
            return self.bundle

        def inspect(*args):
            self.assertTrue(self.lock_held)
            self.events.append("inspect")
            return self.selected

        def stop(config, registry, *, progress):
            self.events.append("stop")
            progress["stage"] = "process_stop"
            registry["process"] = None

        def backup(config):
            self.assertTrue(self.lock_held)
            self.events.append("backup")
            return {"id": "synthetic-backup", "verified": True}

        def record(config, registry, event):
            self.events.append("record:" + event)

        def apply(config, registry, bundle, commit, env, callback, owner):
            self.assertTrue(self.lock_held)
            self.assertEqual((bundle, commit, env), (self.bundle, HEAD, self.environment))
            self.assertEqual(registry["last_backup"], {"id": "synthetic-backup", "verified": True})
            self.events.append("apply")
            registry["customization"]["active"] = copy.deepcopy(self.selected)

        def start(config, selected, env, registry, *, health_timeout, progress):
            self.assertEqual(selected, self.registry["current"])
            self.assertEqual(env, self.environment)
            self.assertEqual(health_timeout, 120)
            self.events.append("start")
            registry["process"] = {"pid": 456, "executable": "registered-python"}
            progress["stage"] = "health_check"

        def demo_main(arguments):
            self.assertFalse(self.lock_held)
            self.assertEqual(arguments, ["--config", str(self.root / "config.json"), "--trial-commit", HEAD])
            self.events.append("demo")
            return 0

        overrides = {
            "checkout": patch.object(trial, "trial_checkout", return_value=HEAD),
            "git": patch.object(trial.upgrade, "git", return_value=(0, "http://saved-proxy:8080")),
            "lock": patch.object(trial.manager, "locked", side_effect=locked),
            "environment": patch.object(trial.manager.states, "runtime_environment", side_effect=lambda _: dict(self.environment)),
            "load": patch.object(trial.manager.states, "load_config", return_value=self.config),
            "read": patch.object(trial.manager, "read_registry", side_effect=lambda _: copy.deepcopy(self.registry)),
            "validate": patch.object(trial.manager.customization, "validate_program", return_value=self.root / "program"),
            "applicability": patch.object(trial.manager.customization, "check_applicability"),
            "accept": patch.object(trial.manager.processes, "check_accept_runtime", return_value="compatible"),
            "prepare": patch.object(trial.bundles, "prepare", side_effect=prepare),
            "inspect": patch.object(trial.manager.customization, "inspect_bundle", side_effect=inspect),
            "stop": patch.object(trial.manager, "stop_registered", side_effect=stop),
            "stopped": patch.object(trial.manager, "require_stopped", side_effect=lambda *a: self.events.append("require_stopped")),
            "backup": patch.object(trial.manager.states, "backup_state", side_effect=backup),
            "record": patch.object(trial.manager, "record", side_effect=record),
            "apply": patch.object(trial.manager.customization, "apply", side_effect=apply),
            "start": patch.object(trial.manager, "start_selected", side_effect=start),
            "identity": patch.object(trial.manager.processes, "verify_identity", return_value=True),
            "health": patch.object(trial.manager.processes, "wait_healthy"),
            "demo": patch.object(trial.demo, "main", side_effect=demo_main),
            "cleanup": patch.object(trial.bundles, "cleanup", side_effect=lambda *a: self.events.append("cleanup")),
            "ci": patch.object(trial.upgrade.downloads, "require_successful_head"),
            "github": patch.object(trial.upgrade, "github_client"),
        }
        for name, override in overrides.items():
            self.mock[name] = override.start()
            self.addCleanup(override.stop)

    def deploy(self):
        with redirect_stdout(self.output):
            return trial.deploy(self.config, HEAD, 120, self.progress)

    def run_main(self):
        with redirect_stdout(self.output):
            return trial.main(["--config", str(self.root / "config.json"), "--trial-commit", HEAD])

    def assert_no_server_changes(self):
        for name in ("stop", "stopped", "backup", "apply", "start", "demo"):
            self.mock[name].assert_not_called()

    def test_entire_preparation_and_program_transaction_share_lock_then_demo_once(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.events, ["lock", "prepare", "inspect", "stop", "require_stopped", "backup",
                                      "record:data_backup_verified", "apply", "start",
                                      "record:trial_upgraded_by_operator", "unlock", "demo", "cleanup"])
        self.mock["ci"].assert_not_called()
        self.mock["github"].assert_not_called()
        self.mock["demo"].assert_called_once()
        self.mock["cleanup"].assert_called_once_with(self.config, self.bundle)
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        self.assertEqual(saved["result"]["source_commit"], HEAD)
        self.assertTrue(saved["result"]["backup_verified"])
        self.assertEqual(saved["result"]["source_verification"], "local_trial")
        self.assertNotIn("synthetic-preserved-key", self.output.getvalue() + json.dumps(saved))

    def test_preparation_and_full_inspection_failure_never_stop_or_call_demo(self):
        for failing in ("prepare", "inspect"):
            with self.subTest(failing=failing):
                original = self.mock[failing].side_effect
                self.mock[failing].side_effect = ValueError("synthetic failure")
                try:
                    self.assertEqual(self.run_main(), 1)
                    self.assert_no_server_changes()
                    self.mock["cleanup"].assert_not_called()
                finally:
                    self.mock[failing].side_effect = original

    def test_protected_program_and_reused_environment_checked_before_preparation(self):
        for failing in ("validate", "applicability", "accept"):
            with self.subTest(failing=failing):
                self.mock[failing].side_effect = ValueError("synthetic incompatible state")
                try:
                    self.assertEqual(self.run_main(), 1)
                    self.mock["prepare"].assert_not_called()
                    self.assert_no_server_changes()
                finally:
                    self.mock[failing].side_effect = None

    def test_incomplete_operation_and_nonoriginal_interpreter_block_before_preparation(self):
        original = copy.deepcopy(self.registry)
        for mutation in (lambda r: r.update(phase="recovery_required"),
                         lambda r: r.update(pending={"action": "switch"}),
                         lambda r: r.update(launch_uncertain=True),
                         lambda r: r["current"].update(kind="release", source_commit=OLDER),
                         lambda r: r["customization"].update(pending={"action": "apply"})):
            self.registry = copy.deepcopy(original)
            mutation(self.registry)
            self.assertEqual(self.run_main(), 1)
            self.mock["prepare"].assert_not_called()
            self.assert_no_server_changes()

    def test_source_mismatch_before_or_after_prepare_blocks_stop(self):
        for calls in ([trial.upgrade.UpgradeError("checkout_changed")],
                      [HEAD, trial.upgrade.UpgradeError("checkout_changed")]):
            self.mock["checkout"].side_effect = calls
            self.assertEqual(self.run_main(), 1)
            self.assert_no_server_changes()

    def test_registry_or_environment_changed_during_prepare_blocks_stop(self):
        prepare = self.mock["prepare"].side_effect
        for changed in ("registry", "environment"):
            with self.subTest(changed=changed):
                def changed_prepare(*args):
                    value = prepare(*args)
                    if changed == "registry":
                        self.registry["process"]["pid"] += 1
                    else:
                        self.environment["DATA_DIR"] += "-changed"
                    return value
                self.mock["prepare"].side_effect = changed_prepare
                self.assertEqual(self.run_main(), 1)
                self.assert_no_server_changes()

    def test_stop_or_backup_failure_never_applies_or_restarts(self):
        for failing in ("stop", "stopped", "backup"):
            with self.subTest(failing=failing):
                original = self.mock[failing].side_effect
                self.mock[failing].side_effect = ValueError("synthetic failure")
                try:
                    self.assertEqual(self.run_main(), 1)
                    for later in ("apply", "start", "demo", "cleanup"):
                        self.mock[later].assert_not_called()
                    self.assertTrue(self.bundle.exists())
                finally:
                    self.mock[failing].side_effect = original

    def test_saved_trial_stop_failure_is_consumable_by_explicit_recovery(self):
        original_registry = copy.deepcopy(self.registry)

        def failed_stop(config, registry, *, progress):
            progress["stage"] = "process_stop"
            raise trial.manager.processes.ProcessError(
                "synthetic stop timeout", operation="process_wait", reason="stop_timeout",
                elapsed_seconds=32.25, timeout_seconds=30)

        self.mock["stop"].side_effect = failed_stop
        self.assertEqual(self.run_main(), 1)
        for name in ("backup", "apply", "start", "demo", "cleanup"):
            self.mock[name].assert_not_called()
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        self.assertEqual(saved["action"], "upgrade")
        self.assertTrue(saved["failed"])
        self.assertEqual(saved["result"]["source_verification"], "local_trial")
        self.assertEqual(saved["result"]["process"]["reason"], "stop_timeout")
        self.assertFalse(saved["result"]["backup_verified"])
        request_path = self.root / ("stop-recovery-" + "c" * 32 + ".json")
        request_path.write_text(json.dumps({"failure": saved, "registry": original_registry}),
                                encoding="utf-8-sig")
        request = recovery.read_request(self.config, request_path)
        self.assertEqual(recovery.validate_failure(self.config, request, HEAD), self.bundle)
        self.assertEqual(request["registry"], original_registry)
        self.assertEqual(self.bundle.read_bytes(), b"synthetic exact reviewed bundle")

    def test_backup_record_failure_stops_before_apply_and_retains_bundle(self):
        self.mock["record"].side_effect = OSError("synthetic backup record failure")
        self.assertEqual(self.run_main(), 1)
        self.mock["backup"].assert_called_once()
        for name in ("apply", "start", "demo", "cleanup"):
            self.mock[name].assert_not_called()
        failure = json.loads((self.root / "last-failure.json").read_bytes())
        self.assertEqual(failure["result"]["stage"], "backup_record")
        self.assertEqual(failure["result"]["bundle"], str(self.bundle))

    def test_apply_failure_preserves_bundle_for_explicit_resume_without_restart(self):
        self.mock["apply"].side_effect = PermissionError(13, "synthetic-private-path")
        self.assertEqual(self.run_main(), 1)
        for name in ("start", "demo", "cleanup"):
            self.mock[name].assert_not_called()
        failure = json.loads((self.root / "last-failure.json").read_bytes())["result"]
        self.assertEqual((failure["stage"], failure["next"]), ("apply", "inspect_apply"))
        self.assertEqual(failure["bundle"], str(self.bundle))
        self.assertIsNone(failure["changed"])
        self.assertTrue(failure["backup_verified"])
        self.assertNotIn("synthetic-private-path", self.output.getvalue() + json.dumps(failure))

    def test_start_failure_retains_changed_program_and_never_applies_assets(self):
        original = self.mock["start"].side_effect
        def unhealthy(*args, **kwargs):
            original(*args, **kwargs)
            raise trial.manager.processes.ProcessError("synthetic health failure")
        self.mock["start"].side_effect = unhealthy
        self.assertEqual(self.run_main(), 1)
        self.mock["start"].assert_called_once()
        self.mock["demo"].assert_not_called()
        self.mock["cleanup"].assert_not_called()
        failure = json.loads((self.root / "last-failure.json").read_bytes())["result"]
        self.assertTrue(failure["changed"])
        self.assertEqual((failure["stage"], failure["next"]), ("health_check", "check_status"))

    def test_same_source_checks_program_health_then_assets_without_download_or_restart(self):
        self.registry["customization"]["active"] = dict(self.active, source_commit=HEAD)
        self.assertEqual(self.run_main(), 0)
        for name in ("prepare", "inspect", "stop", "backup", "apply", "start", "cleanup"):
            self.mock[name].assert_not_called()
        self.mock["validate"].assert_called_once()
        self.mock["health"].assert_called_once_with(self.registry["process"], timeout=5)
        self.mock["demo"].assert_called_once()
        self.assertEqual(self.events, ["lock", "unlock", "demo"])

    def test_same_source_dead_process_is_reported_without_restart_or_assets(self):
        self.registry["customization"]["active"] = dict(self.active, source_commit=HEAD)
        self.mock["identity"].return_value = False
        self.assertEqual(self.run_main(), 1)
        self.mock["prepare"].assert_not_called()
        self.assert_no_server_changes()
        self.assertIn("code=server_not_running", self.output.getvalue())

    def test_same_wheel_from_new_source_uses_existing_apply_to_record_exact_source(self):
        self.selected = dict(self.active, source_commit=HEAD)
        result = self.deploy()
        self.mock["apply"].assert_called_once()
        self.assertEqual(result["source_commit"], HEAD)
        self.assertTrue(result["changed"])

    def test_partial_asset_failure_keeps_its_report_and_does_not_retry_or_cleanup(self):
        def failed_demo(args):
            self.assertFalse(self.lock_held)
            trial.demo.report(self.root / "config.json", {"stage": "apply_assets", "code": "synthetic_conflict",
                                                           "source_commit": HEAD, "next": "inspect_local_result"}, True)
            return 1
        self.mock["demo"].side_effect = failed_demo
        self.assertEqual(self.run_main(), 1)
        self.mock["demo"].assert_called_once()
        self.mock["cleanup"].assert_not_called()
        self.mock["start"].assert_called_once()
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        self.assertEqual(saved["action"], "apply_demo")
        self.assertEqual(saved["result"]["code"], "synthetic_conflict")
        self.assertTrue(self.bundle.exists())

    def test_cli_rejects_empty_short_uppercase_and_extra_ci_options_before_loading_config(self):
        for value in ("", "a" * 39, "A" * 40, HEAD + "\n"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                trial.main(["--config", "synthetic.json", "--trial-commit", value])
            self.assertEqual(raised.exception.code, 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            trial.main(["--config", "synthetic.json", "--trial-commit", HEAD, "--reset-token"])
        self.mock["load"].assert_not_called()
        self.assert_no_server_changes()


class TrialCheckoutTests(unittest.TestCase):
    def test_exact_source_and_origin_main_required_without_fetch_or_ci(self):
        with patch.object(trial.upgrade, "checkout", return_value=HEAD) as checkout, \
                patch.object(trial.upgrade, "git", return_value=(0, HEAD)) as git:
            self.assertEqual(trial.trial_checkout(HEAD), HEAD)
            checkout.assert_called_once_with(HEAD)
            git.assert_called_once_with("rev-parse", "origin/main")
            git.return_value = (0, OLDER)
            with self.assertRaisesRegex(trial.upgrade.UpgradeError, "trial_main_mismatch"):
                trial.trial_checkout(HEAD)


class TrialPowerShellTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is unavailable")
    def test_public_trial_routes_and_invalid_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(ROOT / "scripts" / "manage-ees.ps1", scripts / "manage-ees.ps1")
            for name in ("ees_upgrade.py", "ees_trial_upgrade.py", "ees_apply_demo.py"):
                (scripts / name).write_text("import json,sys; print(json.dumps({'runner': __file__, 'args': sys.argv[1:]}))", encoding="utf-8")
            config = root / "config.json"
            config.write_text(json.dumps({"source_python": sys.executable}), encoding="utf-8")
            base = [shutil.which("pwsh"), "-NoProfile", "-File", str(scripts / "manage-ees.ps1"), "-Config", str(config)]
            for action, trial_options, expected in (("Upgrade", [], "ees_upgrade.py"),
                                                   ("Upgrade", ["-TrialCommit", HEAD], "ees_trial_upgrade.py"),
                                                   ("ApplyDemo", ["-TrialCommit", HEAD], "ees_apply_demo.py")):
                result = subprocess.run([*base, "-Action", action, *trial_options], capture_output=True,
                                        text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                observed = json.loads(result.stdout.strip())
                self.assertEqual(Path(observed["runner"]).name, expected)
                self.assertEqual("--trial-commit" in observed["args"], bool(trial_options))
            for options in (["-Action", "Upgrade", "-TrialCommit", ""],
                            ["-Action", "Upgrade", "-TrialCommit", "A" * 40],
                            ["-Action", "Stop", "-TrialCommit", HEAD],
                            ["-Action", "Upgrade", "-TrialCommit", HEAD, "-ResetUpdateToken"],
                            ["-Action", "Upgrade", "-TrialCommit", HEAD, "-Bundle", "unexpected.zip"]):
                result = subprocess.run([*base, *options], capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('"runner"', result.stdout)


if __name__ == "__main__":
    unittest.main()
