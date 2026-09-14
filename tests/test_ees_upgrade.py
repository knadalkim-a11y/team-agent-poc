"""Upgrade orchestration tests use synthetic state and no network or server."""

import argparse
import copy
from contextlib import contextmanager, nullcontext, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import ees_upgrade as upgrade


HEAD = "a" * 40
OLDER = "b" * 40
TOKEN = "synthetic-update-token"
ROOT = Path(__file__).resolve().parents[1]


class UpgradeDeploymentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {"state_root": str(self.root), "source_python": "registered-python", "cwd": "registered-cwd"}
        self.active = {"source_commit": OLDER, "wheel_sha256": "1" * 64,
                       "record_sha256": "2" * 64, "webui_version": "0.11.3+ees.2"}
        self.selected = dict(self.active, source_commit=HEAD, wheel_sha256="3" * 64)
        self.registry = {"schema_version": 2, "phase": "idle", "pending": None,
                         "current": {"kind": "original", "source_commit": None,
                                     "python": "registered-python"},
                         "process": {"pid": 123, "executable": "registered-python"},
                         "customization": {"active": self.active, "previous": None, "pending": None}}
        self.artifact = {"id": 10, "digest": "sha256:" + "4" * 64, "source_commit": HEAD}
        self.events = []
        self.progress = {}
        self.output = io.StringIO()
        self.mock = {}
        self.original_stop_registered = upgrade.manager.stop_registered

        def download(_, directory):
            self.events.append("download")
            bundle = directory / "synthetic.zip"
            bundle.write_bytes(b"synthetic program bundle")
            return bundle

        def stop(config, registry, *, progress):
            self.events.append("stop")
            registry["process"] = None

        def apply(config, registry, bundle, commit, env, record, owner):
            self.events.append("apply")
            self.assertEqual(commit, HEAD)
            registry["customization"]["active"] = copy.deepcopy(self.selected)

        def start(config, selected, env, registry, *, health_timeout, progress):
            self.events.append("start")
            self.assertEqual(health_timeout, 120)
            self.assertNotIn(TOKEN, env.values())
            registry["process"] = {"pid": 456, "executable": "registered-python"}
            progress["stage"] = "health_check"

        self.client = Mock()
        self.client.download_artifact.side_effect = download
        overrides = {
            "checkout": patch.object(upgrade, "checkout", return_value=HEAD),
            "artifact": patch.object(upgrade.downloads, "select_program", return_value=self.artifact),
            "lock": patch.object(upgrade.manager, "locked", side_effect=lambda *a, **k: nullcontext({"pid": 9})),
            "environment": patch.object(upgrade.manager.states, "runtime_environment", return_value={"DATA_DIR": "existing"}),
            "read": patch.object(upgrade.manager, "read_registry", side_effect=lambda _: copy.deepcopy(self.registry)),
            "validate": patch.object(upgrade.manager.customization, "validate_program", return_value=self.root / "program"),
            "applicability": patch.object(upgrade.manager.customization, "check_applicability"),
            "accept_check": patch.object(upgrade.manager.processes, "check_accept_runtime", return_value="compatible"),
            "inspect": patch.object(upgrade.manager.customization, "inspect_bundle", side_effect=lambda *a: self.selected),
            "stop": patch.object(upgrade.manager, "stop_registered", side_effect=stop),
            "stopped": patch.object(upgrade.manager, "require_stopped", side_effect=lambda *a: self.events.append("require_stopped")),
            "apply": patch.object(upgrade.manager.customization, "apply", side_effect=apply),
            "start": patch.object(upgrade.manager, "start_selected", side_effect=start),
            "record": patch.object(upgrade.manager, "record"),
            "identity": patch.object(upgrade.manager.processes, "verify_identity", return_value=True),
            "health": patch.object(upgrade.manager.processes, "wait_healthy"),
        }
        for name, override in overrides.items():
            self.mock[name] = override.start()
            self.addCleanup(override.stop)

    def deploy(self):
        with redirect_stdout(self.output):
            return upgrade.deploy(self.config, self.client, HEAD, 120, self.progress)

    def assert_no_server_changes(self):
        for name in ("stop", "stopped", "apply", "start"):
            self.mock[name].assert_not_called()

    def test_download_and_preflight_failures_never_stop_server(self):
        for failing in ("download", "applicability", "inspect"):
            with self.subTest(failing=failing):
                target = self.client.download_artifact if failing == "download" else self.mock[failing]
                original = target.side_effect
                target.side_effect = ValueError("synthetic failure")
                try:
                    with self.assertRaises(ValueError):
                        self.deploy()
                    self.assert_no_server_changes()
                finally:
                    target.side_effect = original

    def test_incompatible_runtime_is_rejected_before_download_and_stop(self):
        self.mock["accept_check"].side_effect = upgrade.manager.processes.ProcessError(
            "synthetic incompatible runtime", reason="accept_guard_incompatible")
        with self.assertRaises(upgrade.manager.processes.ProcessError):
            self.deploy()
        self.assert_no_server_changes()
        self.client.download_artifact.assert_not_called()

    def test_cached_noop_validates_program_process_and_health_without_download(self):
        upgrade.save_receipt(self.config, self.artifact, self.active)
        result = self.deploy()
        self.assertFalse(result["changed"])
        self.assertFalse(result["downloaded"])
        self.assertEqual(result["source_commit"], OLDER)
        self.mock["validate"].assert_called_once_with(self.root / "program", self.active)
        self.mock["applicability"].assert_called_once()
        self.mock["identity"].assert_called_once_with(self.registry["process"])
        self.mock["health"].assert_called_once_with(self.registry["process"], timeout=5)
        self.client.download_artifact.assert_not_called()
        self.assert_no_server_changes()

    def test_cached_receipt_cannot_hide_damaged_program_or_dead_process(self):
        upgrade.save_receipt(self.config, self.artifact, self.active)
        self.mock["validate"].side_effect = ValueError("program damaged")
        with self.assertRaisesRegex(ValueError, "program damaged"):
            self.deploy()
        self.mock["validate"].side_effect = None
        self.mock["identity"].return_value = False
        with self.assertRaisesRegex(upgrade.UpgradeError, "server_not_running"):
            self.deploy()
        self.mock["health"].assert_not_called()
        self.client.download_artifact.assert_not_called()
        self.assert_no_server_changes()

    def test_identical_downloaded_program_preserves_installed_source_commit(self):
        self.selected = dict(self.active, source_commit=HEAD)
        result = self.deploy()
        self.assertFalse(result["changed"])
        self.assertTrue(result["downloaded"])
        self.assertEqual(result["source_commit"], OLDER)
        self.assertTrue(upgrade.receipt_matches(self.config, self.artifact, self.active))
        self.assert_no_server_changes()
        self.mock["health"].assert_called_once()
        self.events.clear()
        self.client.download_artifact.reset_mock()
        self.assertFalse(self.deploy()["downloaded"])
        self.client.download_artifact.assert_not_called()

    def test_success_downloads_and_checks_before_stop_then_applies_and_starts(self):
        result = self.deploy()
        self.assertEqual(self.events, ["download", "stop", "require_stopped", "apply", "start"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["source_commit"], HEAD)
        self.assertEqual(self.mock["applicability"].call_count, 2)
        self.assertTrue(upgrade.receipt_matches(self.config, self.artifact, self.selected))
        self.mock["record"].assert_called_once()
        self.assertFalse(Path(self.progress["bundle"]).exists())

    def test_changed_deployment_during_download_blocks_stop(self):
        original = self.client.download_artifact.side_effect

        def changed(*args):
            self.registry["process"]["pid"] = 999
            return original(*args)

        self.client.download_artifact.side_effect = changed
        with self.assertRaisesRegex(upgrade.UpgradeError, "deployment_changed"):
            self.deploy()
        self.assert_no_server_changes()

    def test_apply_failure_does_not_start_or_write_success_receipt(self):
        self.mock["apply"].side_effect = ValueError("apply failed")
        with self.assertRaisesRegex(ValueError, "apply failed"):
            self.deploy()
        self.mock["stop"].assert_called_once()
        self.mock["stopped"].assert_called_once()
        self.mock["start"].assert_not_called()
        self.assertEqual(self.progress["stage"], "apply")
        self.assertFalse((self.root / "upgrade-receipt.json").exists())
        self.assertEqual(Path(self.progress["bundle"]).read_bytes(), b"synthetic program bundle")

    def test_health_failure_preserves_new_process_without_cleanup_or_retry(self):
        start = self.mock["start"].side_effect
        observed = []

        def unhealthy(*args, **kwargs):
            start(*args, **kwargs)
            observed.append(args[3])
            raise upgrade.manager.processes.ProcessError("synthetic health timeout")

        self.mock["start"].side_effect = unhealthy
        with self.assertRaises(upgrade.manager.processes.ProcessError):
            self.deploy()
        self.assertEqual(self.events, ["download", "stop", "require_stopped", "apply", "start"])
        self.assertEqual(observed[0]["process"]["pid"], 456)
        self.assertEqual(observed[0]["customization"]["active"], self.selected)
        self.assertEqual(self.progress["stage"], "health_check")
        self.assertTrue(self.progress["changed"])
        self.assertFalse((self.root / "upgrade-receipt.json").exists())

    def test_main_apply_permission_error_retains_codes_and_actual_upgrade_frame(self):
        private = "synthetic-private-PAT-and-exception-path"
        error = PermissionError(13, private, private)
        error.winerror = 5
        self.mock["apply"].side_effect = error
        with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                patch.object(upgrade, "github_client", return_value=self.client), \
                patch.object(upgrade, "bootstrap", return_value=(None, HEAD, OLDER)), \
                redirect_stdout(self.output):
            self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        retained = json.loads((self.root / "last-failure.json").read_bytes())
        self.assertEqual(retained, saved)
        self.assertEqual(saved["result"]["stage"], "apply")
        self.assertEqual(saved["result"]["code"], "operation_failed")
        self.assertEqual(saved["result"]["next"], "inspect_apply")
        self.assertNotIn("program_rename", saved["result"])
        detail = saved["result"]["local_error"]
        self.assertEqual((detail["type"], detail["errno"], detail["winerror"]), ("PermissionError", 13, 5))
        self.assertEqual(detail["source"], "ees_upgrade.py")
        source = (ROOT / "scripts" / detail["source"]).read_text(encoding="utf-8").splitlines()
        self.assertTrue(source[detail["line"] - 1].strip().startswith("manager.customization.apply(config"))
        summary = self.output.getvalue().splitlines()[-1]
        self.assertIn("error=PermissionError errno=13 winerror=5 at=ees_upgrade.py:", summary)
        self.assertNotIn(str(self.root), summary)
        self.assertNotIn(private, self.output.getvalue() + json.dumps(saved))
        self.assertNotIn("Traceback", self.output.getvalue())
        self.mock["start"].assert_not_called()

    def test_main_hints_manual_promotion_only_for_eligible_exhausted_promotion(self):
        private = "synthetic-private-PAT-and-path"
        for rename_stage, ready, expected in (("promote", True, "manual_promote"),
                                               ("promote", False, "inspect_apply"),
                                               ("move_active", True, "inspect_apply"),
                                               ("restore", True, "inspect_apply"),
                                               (private, True, "inspect_apply")):
            with self.subTest(rename_stage=rename_stage, ready=ready):
                error = PermissionError(13, private, private)
                error.winerror = 5
                error.program_rename_failed = True
                error.program_rename_stage = rename_stage
                error.program_rename_attempts = 5
                error.program_rename_wait_seconds = 15
                self.mock["apply"].side_effect = error
                self.output = io.StringIO()
                with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                        patch.object(upgrade, "github_client", return_value=self.client), \
                        patch.object(upgrade, "bootstrap", return_value=(None, HEAD, OLDER)), \
                        patch.object(upgrade, "manual_promote_ready", return_value=ready) as check, \
                        redirect_stdout(self.output):
                    self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                result = saved["result"]
                self.assertEqual(result["next"], expected)
                self.assertEqual(result["stage"], "apply")
                self.assertEqual(Path(result["bundle"]).read_bytes(), b"synthetic program bundle")
                summary = self.output.getvalue().splitlines()[-1]
                self.assertIn("next=" + expected, summary)
                if rename_stage == private:
                    self.assertEqual(result["code"], "operation_failed")
                    self.assertNotIn("program_rename", result)
                    self.assertNotIn(" rename=", summary)
                else:
                    self.assertEqual(result["code"], "program_rename_blocked")
                    self.assertEqual(result["program_rename"],
                                     {"stage": rename_stage, "attempts": 5, "waited_seconds": 15})
                    self.assertIn("rename=" + rename_stage + " attempts=5 waited=15", summary)
                self.assertEqual(check.call_count, int(rename_stage == "promote"))
                self.assertNotIn(private, self.output.getvalue() + json.dumps(saved))
                self.assertNotIn(str(self.root), summary)
                self.mock["start"].assert_not_called()

    def test_main_non_apply_rename_failure_cannot_hint_manual_promotion(self):
        error = PermissionError(13, "synthetic-private-path")
        error.winerror = 32
        error.program_rename_failed = True
        error.program_rename_stage = "promote"
        error.program_rename_attempts = 5
        error.program_rename_wait_seconds = 15
        self.client.download_artifact.side_effect = error
        with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                patch.object(upgrade, "github_client", return_value=self.client), \
                patch.object(upgrade, "bootstrap", return_value=(None, HEAD, OLDER)), \
                patch.object(upgrade, "manual_promote_ready", return_value=True) as check, \
                redirect_stdout(self.output):
            self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
        result = json.loads((self.root / "last-failure.json").read_bytes())["result"]
        self.assertEqual(result["stage"], "download")
        self.assertEqual(result["code"], "program_rename_blocked")
        self.assertEqual(result["next"], "check_download_access")
        check.assert_not_called()
        self.assert_no_server_changes()

    def test_main_path_guard_error_with_stale_counters_cannot_hint_manual_promotion(self):
        private = "synthetic-private-path"
        for marker in (None, False):
            with self.subTest(marker=marker):
                error = PermissionError(13, private)
                error.winerror = 5
                if marker is not None:
                    error.program_rename_failed = marker
                error.program_rename_stage = "promote"
                error.program_rename_attempts = 5
                error.program_rename_wait_seconds = 15
                self.mock["apply"].side_effect = error
                self.output = io.StringIO()
                with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                        patch.object(upgrade, "github_client", return_value=self.client), \
                        patch.object(upgrade, "bootstrap", return_value=(None, HEAD, OLDER)), \
                        patch.object(upgrade, "manual_promote_ready", return_value=True) as check, \
                        redirect_stdout(self.output):
                    self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                self.assertEqual(saved["result"]["code"], "operation_failed")
                self.assertEqual(saved["result"]["next"], "inspect_apply")
                self.assertNotIn("program_rename", saved["result"])
                self.assertNotIn("rename=", self.output.getvalue())
                self.assertNotIn(private, self.output.getvalue() + json.dumps(saved))
                check.assert_not_called()
                self.mock["start"].assert_not_called()

    def test_main_preserves_structured_stop_failures_and_registered_log_id(self):
        log_id = "server-" + "e" * 32 + ".log"
        self.registry["process"]["log_file"] = str(self.root / log_id)
        self.mock["stop"].side_effect = self.original_stop_registered
        cases = (("stop_timeout", "process_wait", 32.125, 30, None),
                 ("stop_helper_timeout", "stop_helper", 8.125, 8, None),
                 ("stop_signal_failed", "console_signal", 0.125, 8, 3))
        for reason, operation, elapsed, timeout, exit_code in cases:
            with self.subTest(reason=reason):
                private = "synthetic-private-stop-exception"
                error = upgrade.manager.processes.ProcessError(private, reason=reason, operation=operation,
                    elapsed_seconds=elapsed, timeout_seconds=timeout, exit_code=exit_code)
                self.output = io.StringIO()
                with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                        patch.object(upgrade, "github_client", return_value=self.client), \
                        patch.object(upgrade, "bootstrap", return_value=(None, HEAD, OLDER)), \
                        patch.object(upgrade.manager.processes, "stop_server", side_effect=error), \
                        redirect_stdout(self.output):
                    self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                detail = saved["result"]["process"]
                self.assertEqual(detail["stage"], "process_stop")
                self.assertEqual(detail["error_type"], "process")
                self.assertEqual(detail["reason"], reason)
                self.assertEqual(detail["operation"], operation)
                self.assertEqual(detail["elapsed_seconds"], elapsed)
                self.assertEqual(detail["timeout_seconds"], timeout)
                self.assertEqual(detail["exit_code"], exit_code)
                self.assertEqual(detail["log_id"], log_id)
                summary = self.output.getvalue().splitlines()[-1]
                self.assertIn("operation=" + operation + " reason=" + reason, summary)
                self.assertIn("seconds=" + str(elapsed) + " timeout=" + str(timeout), summary)
                self.assertIn("exit=" + (str(exit_code) if exit_code is not None else "-"), summary)
                self.assertNotIn(private, self.output.getvalue() + json.dumps(saved))
                self.assertNotIn(str(self.root), summary)
                self.mock["apply"].assert_not_called()
                self.mock["start"].assert_not_called()


class ManualPromotionReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / "state"
        paths = {"state_root": self.root, "source_prefix": base / "python",
                 "package_dir": base / "python" / "site-packages",
                 "data_dir": base / "data", "cwd": base / "work"}
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        executable = paths["source_prefix"] / "python.exe"
        executable.write_bytes(b"synthetic executable")
        self.config = {key: str(path) for key, path in paths.items()}
        self.config["source_python"] = str(executable)
        self.active = {"source_commit": OLDER, "wheel_sha256": "1" * 64,
                       "record_sha256": "2" * 64, "webui_version": "0.11.3+ees.2"}
        self.selected = dict(self.active, source_commit=HEAD, wheel_sha256="3" * 64)
        self.pending = {"action": "apply", "stage": "promote", "before": self.active,
                        "target": self.selected, "old_previous": None,
                        "owner": {"pid": 123, "executable": "synthetic-python", "created_at": "1234"}}
        self.registry = {"schema_version": 2, "phase": "idle", "process": None, "pending": None,
                         "current": {"kind": "original", "source_commit": None, "python": str(executable)},
                         "customization": {"active": self.active, "previous": None, "pending": self.pending}}
        self.program = self.root / "program"
        self.previous = self.root / "program.previous"
        self.staged = self.root / "program.staging"
        self.previous.mkdir()
        self.staged.mkdir()
        override = patch.object(upgrade.manager, "read_registry", side_effect=lambda _: copy.deepcopy(self.registry))
        self.read = override.start()
        self.addCleanup(override.stop)

    def test_stopped_customized_state_is_eligible_but_first_install_is_not(self):
        before = copy.deepcopy(self.registry)
        snapshot = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        with patch.object(upgrade.manager, "record") as record, \
                patch.object(upgrade.manager, "stop_registered") as stop, \
                patch.object(upgrade.manager, "start_selected") as start:
            self.assertTrue(upgrade.manual_promote_ready(self.config))
        self.assertEqual(self.registry, before)
        self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")), snapshot)
        for mutation in (record, stop, start):
            mutation.assert_not_called()
        self.pending["before"] = None
        self.registry["customization"]["active"] = None
        for previous_exists in (True, False):
            with self.subTest(previous_exists=previous_exists):
                if not previous_exists:
                    self.previous.rmdir()
                before = copy.deepcopy(self.registry)
                snapshot = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
                with patch.object(upgrade.manager, "record") as record, \
                        patch.object(upgrade.manager, "stop_registered") as stop, \
                        patch.object(upgrade.manager, "start_selected") as start:
                    self.assertFalse(upgrade.manual_promote_ready(self.config))
                self.assertEqual(self.registry, before)
                self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")), snapshot)
                for mutation in (record, stop, start):
                    mutation.assert_not_called()

    def test_running_uncertain_or_inconsistent_registry_does_not_offer_manual_rename(self):
        original = copy.deepcopy(self.registry)
        cases = (((), "phase", "recovery_required"), ((), "process", {"pid": 321}),
                 ((), "pending", {"action": "start"}), ((), "launch_uncertain", True),
                 ((), "current", None), ((), "current", []),
                 (("current",), "kind", "release"), (("current",), "source_commit", HEAD),
                 (("current",), "python", "synthetic-unregistered-python"),
                 (("customization", "pending"), "action", "restore"),
                 (("customization", "pending"), "stage", "move_active"),
                 (("customization", "pending"), "before", None),
                 (("customization", "pending"), "old_previous", {"active": None}),
                 (("customization",), "pending", None),
                 (("customization", "pending"), "target", None),
                 (("customization", "pending"), "owner", {"pid": 123}))
        for path, key, value in cases:
            with self.subTest(path=path, key=key):
                self.registry = copy.deepcopy(original)
                selected = self.registry
                for name in path:
                    selected = selected[name]
                selected[key] = value
                self.assertFalse(upgrade.manual_promote_ready(self.config))

    def test_missing_staging_previous_or_existing_program_blocks_manual_rename(self):
        self.staged.rmdir()
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        self.staged.mkdir()
        self.previous.rmdir()
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        self.previous.mkdir()
        self.program.mkdir()
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        self.program.rmdir()
        self.program.write_bytes(b"unexpected file")
        self.assertFalse(upgrade.manual_promote_ready(self.config))

    def test_lock_and_dangling_lock_link_are_preserved_and_block_manual_rename(self):
        lock = self.root / "deployment.lock"
        lock.write_bytes(b"synthetic-owner")
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        self.assertEqual(lock.read_bytes(), b"synthetic-owner")
        lock.unlink()
        try:
            lock.symlink_to(self.root / "missing-lock-target")
        except (OSError, NotImplementedError):
            self.skipTest("This platform cannot create the dangling lock link guard fixture.")
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        self.assertTrue(lock.is_symlink())

    def test_unsafe_or_uninspectable_paths_never_offer_manual_rename(self):
        (self.staged / ".env").write_bytes(b"synthetic-private-environment")
        self.assertFalse(upgrade.manual_promote_ready(self.config))
        (self.staged / ".env").unlink()
        overlapping = dict(self.config, data_dir=str(self.root / "program"))
        self.assertFalse(upgrade.manual_promote_ready(overlapping))
        for error in (PermissionError("synthetic-private-path"), ValueError("malformed registry"),
                      TypeError("malformed registry"), KeyError("missing registry")):
            with self.subTest(error=type(error)):
                self.read.side_effect = error
                self.assertFalse(upgrade.manual_promote_ready(self.config))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = {"state_root": temporary.name}
        self.args = argparse.Namespace(config=Path(temporary.name) / "config.json", prepared_head=None,
                                       wrapper_before=None, health_timeout=120, reset_token=False)
        self.head = OLDER
        self.target = HEAD
        self.branch = "main"
        self.origin = upgrade.REPOSITORY + ".git"
        self.dirty = ""
        self.ancestry = 0
        self.events = []

        def git(*args, optional=False, proxy=None):
            if args == ("remote", "get-url", "origin"):
                return 0, self.origin
            if args == ("branch", "--show-current"):
                return 0, self.branch
            if args[:2] == ("status", "--porcelain"):
                return 0, self.dirty
            if args == ("rev-parse", "HEAD"):
                return 0, self.head
            if args == ("rev-parse", "origin/main"):
                return 0, self.target
            self.events.append(args[0])
            if args[0] == "merge-base":
                return self.ancestry, ""
            if args[0] == "merge":
                self.assertEqual(args, ("merge", "--ff-only", HEAD))
                self.head = HEAD
            return 0, ""

        self.process = Mock()
        self.process.wait.return_value = 7
        overrides = [patch.object(upgrade, "git", side_effect=git),
                     patch.object(upgrade.manager, "locked", side_effect=lambda *a, **k: nullcontext()),
                     patch.object(upgrade.downloads, "require_successful_head", side_effect=lambda *a: self.events.append("ci")),
                     patch.object(upgrade.subprocess, "Popen", side_effect=lambda *a, **k: self.events.append("child") or self.process)]
        self.git, self.lock, self.ci, self.child = [item.start() for item in overrides]
        for item in overrides:
            self.addCleanup(item.stop)

    def test_checks_exact_fetched_head_then_merges_and_reexecutes_updated_runner(self):
        client = object()
        result = upgrade.bootstrap(self.config, self.args, client, {})
        self.assertEqual(result, (7, HEAD, OLDER))
        self.assertEqual(self.events, ["fetch", "merge-base", "ci", "merge", "child"])
        self.ci.assert_called_once_with(client, HEAD)
        self.child.assert_called_once_with([
            sys.executable, "-I", "-B", str(upgrade.ROOT / "scripts" / "ees_upgrade.py"),
            "--config", str(self.args.config), "--prepared-head", HEAD,
            "--wrapper-before", OLDER, "--health-timeout", "120"])
        self.process.wait.assert_called_once_with()

    def test_failed_ci_prevents_wrapper_merge_and_child(self):
        self.ci.side_effect = upgrade.downloads.DownloadError("main_checks_not_successful")
        with self.assertRaises(upgrade.downloads.DownloadError):
            upgrade.bootstrap(self.config, self.args, object(), {})
        self.assertNotIn("merge", self.events)
        self.child.assert_not_called()
        self.assertEqual(self.head, OLDER)

    def test_asset_runner_uses_same_verified_update_without_program_options(self):
        del self.args.health_timeout
        options = ["--ees-model-id", "existing", "--reset-token"]
        result = upgrade.bootstrap(self.config, self.args, object(), {},
                                   runner="ees_apply_demo.py", runner_options=options)
        self.assertEqual(result, (7, HEAD, OLDER))
        command = self.child.call_args.args[0]
        self.assertIn(str(upgrade.ROOT / "scripts" / "ees_apply_demo.py"), command)
        self.assertEqual(command[-3:], options)
        self.assertNotIn("--health-timeout", command)
        self.assertEqual(self.events, ["fetch", "merge-base", "ci", "merge", "child"])

    def test_wrong_repository_branch_dirty_and_ahead_or_diverged_main_rejected(self):
        for attribute, value, code in (("origin", "https://github.com/another/repo", "wrong_repository"),
                                       ("branch", "feature", "main_required"),
                                       ("dirty", " M scripts/ees_upgrade.py", "local_changes"),
                                       ("ancestry", 1, "local_main_ahead_or_diverged")):
            with self.subTest(code=code):
                before = getattr(self, attribute)
                setattr(self, attribute, value)
                try:
                    with self.assertRaisesRegex(upgrade.UpgradeError, code):
                        upgrade.bootstrap(self.config, self.args, object(), {})
                    self.child.assert_not_called()
                    self.ci.assert_not_called()
                finally:
                    setattr(self, attribute, before)

    def test_existing_lock_blocks_fetch_and_prepared_head_must_still_match(self):
        lock = Path(self.config["state_root"]) / "deployment.lock"
        lock.touch()
        with self.assertRaisesRegex(upgrade.UpgradeError, "operation_busy"):
            upgrade.bootstrap(self.config, self.args, object(), {})
        self.assertEqual(self.events, [])
        self.args.prepared_head, self.args.wrapper_before = OLDER, OLDER
        with self.assertRaisesRegex(upgrade.UpgradeError, "checkout_changed"):
            upgrade.bootstrap(self.config, self.args, object(), {})
        self.child.assert_not_called()

    def test_current_wrapper_still_requires_successful_ci_without_reexec(self):
        self.head = HEAD
        self.assertEqual(upgrade.bootstrap(self.config, self.args, object(), {}), (None, HEAD, HEAD))
        self.ci.assert_called_once()
        self.child.assert_not_called()

    def test_parent_interrupt_leaves_operation_report_to_updated_child(self):
        self.process.wait.side_effect = [KeyboardInterrupt(), 1]
        with patch.object(upgrade.manager.states, "load_config", return_value=self.config), \
                patch.object(upgrade, "github_client"), patch.object(upgrade, "report") as report, \
                patch.object(upgrade, "deploy") as deploy, redirect_stdout(io.StringIO()):
            self.assertEqual(upgrade.main(["--config", str(self.args.config)]), 1)
            report.assert_not_called()
            deploy.assert_not_called()
        self.assertEqual([call.kwargs for call in self.process.wait.call_args_list], [{}, {"timeout": 5}])
        self.process.kill.assert_not_called()
        self.process.terminate.assert_not_called()

    def test_interrupted_parent_does_not_kill_slow_child_or_clear_delegation(self):
        self.process.wait.side_effect = [KeyboardInterrupt(), subprocess.TimeoutExpired("updated runner", 5)]
        progress = {}
        self.assertEqual(upgrade.bootstrap(self.config, self.args, object(), progress), (130, HEAD, OLDER))
        self.assertTrue(progress["delegated"])
        self.process.kill.assert_not_called()
        self.process.terminate.assert_not_called()

    def test_manual_update_holds_deployment_lock_through_git_operations(self):
        held = []

        @contextmanager
        def locked(*args, **kwargs):
            held.append(True)
            try:
                yield
            finally:
                held.pop()

        git = self.git.side_effect

        def check_lock(*args, **kwargs):
            self.assertEqual(held, [True])
            return git(*args, **kwargs)

        self.lock.side_effect = locked
        self.git.side_effect = check_lock
        result = upgrade.update_only(self.config, proxy="http://synthetic-proxy:8080")
        self.assertTrue(result["wrapper_changed"])
        self.assertFalse(result["changed"])
        self.assertEqual(result["wrapper_commit"], HEAD)
        self.git.assert_any_call("fetch", "origin", "main", proxy="http://synthetic-proxy:8080")
        self.ci.assert_not_called()
        self.child.assert_not_called()

    def test_busy_deployment_blocks_manual_update_before_any_git_call(self):
        self.lock.side_effect = upgrade.UpgradeError("operation_busy")
        with self.assertRaisesRegex(upgrade.UpgradeError, "operation_busy"):
            upgrade.update_only(self.config)
        self.git.assert_not_called()
        self.ci.assert_not_called()
        self.child.assert_not_called()


@unittest.skipUnless(shutil.which("git"), "Git compatibility integration requires git")
class RealGitCompatibilityTests(unittest.TestCase):
    def test_program_reuse_checks_real_ancestry_inputs_and_clean_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*arguments):
                return subprocess.run([shutil.which("git"), "-C", str(root), *arguments],
                                      check=True, capture_output=True, text=True, timeout=10).stdout.strip()

            def commit(message):
                git("add", ".")
                git("commit", "-m", message)
                return git("rev-parse", "HEAD")

            git("init", "--initial-branch=main", "--template=")
            git("config", "user.name", "Synthetic Upgrade Test")
            git("config", "user.email", "upgrade-test@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("config", "core.hooksPath", str(root / "unused-hooks"))
            git("remote", "add", "origin", upgrade.REPOSITORY + ".git")
            (root / "branding").mkdir()
            program = root / "branding" / "program.txt"
            notes = root / "notes.txt"
            program.write_text("first program\n", encoding="utf-8")
            notes.write_text("initial notes\n", encoding="utf-8")
            initial = commit("program release")
            with patch.object(upgrade, "ROOT", root):
                self.assertEqual(upgrade.checkout(), initial)
                notes.write_text("updated notes\n", encoding="utf-8")
                notes_only = commit("notes only")
                self.assertTrue(upgrade.compatible_program(initial, notes_only))
                program.write_text("changed program\n", encoding="utf-8")
                changed = commit("program changed")
                self.assertFalse(upgrade.compatible_program(initial, changed))
                work = root / "agent-pack" / "skills" / "ees-work-demo" / "ui" / "ees-work.js"
                work.parent.mkdir(parents=True)
                work.write_text("const demo = true;\n", encoding="utf-8")
                work_changed = commit("work demonstration changed")
                self.assertFalse(upgrade.compatible_program(changed, work_changed))
                unrelated = git("commit-tree", "HEAD^{tree}", "-m", "unrelated history")
                self.assertFalse(upgrade.compatible_program(unrelated, work_changed))
                self.assertEqual(upgrade.checkout(work_changed), work_changed)
                notes.write_text("uncommitted local notes\n", encoding="utf-8")
                with self.assertRaisesRegex(upgrade.UpgradeError, "local_changes"):
                    upgrade.checkout()


class CredentialsTests(unittest.TestCase):
    def test_token_is_dpapi_only_and_does_not_change_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = {"state_root": temporary}
            encrypted = b"synthetic-DPAPI-ciphertext"
            environment = dict(os.environ)
            with patch.object(upgrade.sys.stdin, "isatty", return_value=True), \
                    patch.object(upgrade.getpass, "getpass", return_value=TOKEN) as prompt, \
                    patch.object(upgrade.manager.states, "_protect", return_value=encrypted) as protect, \
                    patch.object(upgrade.manager.states, "_unprotect", return_value=TOKEN.encode()) as unprotect:
                self.assertEqual(upgrade.token_for(config), TOKEN)
                self.assertEqual(upgrade.token_for(config), TOKEN)
                path = Path(temporary) / "github-update.dpapi"
                self.assertEqual(path.read_bytes(), encrypted)
                self.assertNotIn(TOKEN.encode(), path.read_bytes())
                self.assertEqual(list(Path(temporary).iterdir()), [path])
                prompt.assert_called_once()
                protect.assert_called_once_with(TOKEN.encode())
                unprotect.assert_called_once_with(encrypted)
                self.assertEqual(dict(os.environ), environment)

    def test_noninteractive_missing_token_and_invalid_token_leave_no_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = {"state_root": temporary}
            with patch.object(upgrade.sys.stdin, "isatty", return_value=False):
                with self.assertRaisesRegex(upgrade.UpgradeError, "credentials_required"):
                    upgrade.token_for(config)
            with patch.object(upgrade.sys.stdin, "isatty", return_value=True), \
                    patch.object(upgrade.getpass, "getpass", return_value=TOKEN + "\n"), \
                    patch.object(upgrade.manager.states, "_protect") as protect:
                with self.assertRaisesRegex(upgrade.UpgradeError, "credentials_invalid"):
                    upgrade.token_for(config)
                protect.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_reset_replaces_encrypted_token_without_decrypting_old_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "github-update.dpapi"
            path.write_bytes(b"old ciphertext")
            with patch.object(upgrade.sys.stdin, "isatty", return_value=True), \
                    patch.object(upgrade.getpass, "getpass", return_value=TOKEN), \
                    patch.object(upgrade.manager.states, "_protect", return_value=b"new ciphertext"), \
                    patch.object(upgrade.manager.states, "_unprotect") as unprotect:
                self.assertEqual(upgrade.token_for({"state_root": temporary}, reset=True), TOKEN)
                self.assertEqual(path.read_bytes(), b"new ciphertext")
                unprotect.assert_not_called()


class UpgradeEntryPointTests(unittest.TestCase):
    def test_manual_update_never_requests_github_client_or_token(self):
        result = {"changed": False, "wrapper_changed": True, "wrapper_commit": HEAD}
        with patch.object(upgrade.manager.states, "load_config", return_value={}), \
                patch.object(upgrade, "checkout"), patch.object(upgrade, "github_client") as client, \
                patch.object(upgrade, "token_for") as token, \
                patch.object(upgrade, "update_only", return_value=result) as update, \
                patch.object(upgrade, "deploy") as deploy, patch.object(upgrade, "report"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(upgrade.main(["--config", "synthetic.json", "--update-only"]), 0)
            update.assert_called_once_with({}, None)
            client.assert_not_called()
            token.assert_not_called()
            deploy.assert_not_called()

    def test_bootstrap_child_result_never_runs_deployment_in_stale_parent(self):
        with patch.object(upgrade.manager.states, "load_config", return_value={}), \
                patch.object(upgrade, "checkout"), patch.object(upgrade, "github_client"), \
                patch.object(upgrade, "bootstrap", return_value=(7, HEAD, OLDER)), \
                patch.object(upgrade, "deploy") as deploy, patch.object(upgrade, "report") as report, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 7)
            deploy.assert_not_called()
            report.assert_not_called()

    def test_api_rejected_token_gives_reset_instruction_without_raw_exception(self):
        def rejected(config, args, client, progress):
            progress["stage"] = "ci_check"
            raise upgrade.downloads.DownloadError("credentials_rejected")

        output = io.StringIO()
        with patch.object(upgrade.manager.states, "load_config", return_value={}), \
                patch.object(upgrade, "checkout"), patch.object(upgrade, "github_client"), \
                patch.object(upgrade, "bootstrap", side_effect=rejected), \
                patch.object(upgrade, "deploy") as deploy, \
                patch.object(upgrade.manager, "save_operation", return_value=True), redirect_stdout(output):
            self.assertEqual(upgrade.main(["--config", "synthetic.json"]), 1)
            deploy.assert_not_called()
        self.assertIn("code=credentials_rejected next=reset_update_token", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell adapter execution requires pwsh")
class PowerShellUpgradeTests(unittest.TestCase):
    def test_adapter_runs_demo_with_saved_environment_and_separate_auth_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            adapter = scripts / "manage-ees.ps1"
            shutil.copyfile(ROOT / "scripts" / "manage-ees.ps1", adapter)
            (scripts / "ees_apply_demo.py").write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            config = root / "config.json"
            config.write_text(json.dumps({"source_python": sys.executable}), encoding="utf-8")
            command = [shutil.which("pwsh"), "-NoProfile", "-File", str(adapter),
                       "-Action", "ApplyDemo", "-Config", str(config)]
            result = subprocess.run(command + ["-ResetDemoToken", "-ResetUpdateToken",
                                    "-WebUIUrl", "http://127.0.0.1:8080", "-EesModelId", "existing", "-Summary"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["--config", str(config), "--reset-token",
                            "--reset-update-token", "--webui-url", "http://127.0.0.1:8080", "--ees-model-id", "existing"])
            result = subprocess.run(command + ["-Bundle", "untrusted.zip"], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_adapter_runs_upgrade_entrypoint_and_forwards_only_upgrade_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            adapter = scripts / "manage-ees.ps1"
            shutil.copyfile(ROOT / "scripts" / "manage-ees.ps1", adapter)
            (scripts / "ees_upgrade.py").write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            config = root / "config.json"
            config.write_text(json.dumps({"source_python": sys.executable}), encoding="utf-8")
            command = [shutil.which("pwsh"), "-NoProfile", "-File", str(adapter),
                       "-Action", "Upgrade", "-Config", str(config)]
            result = subprocess.run(command + ["-HealthTimeout", "90", "-ResetUpdateToken", "-Summary"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["--config", str(config), "--health-timeout", "90", "--reset-token"])
            result = subprocess.run(command + ["-Bundle", "untrusted.zip"], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")
            result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(adapter),
                                     "-Action", "Update", "-Config", str(config),
                                     "-GitProxy", "http://synthetic-proxy:8080"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["--config", str(config), "--update-only",
                                                        "--git-proxy", "http://synthetic-proxy:8080"])


if __name__ == "__main__":
    unittest.main()
