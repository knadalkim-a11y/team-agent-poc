"""Bounded stop recovery guards with synthetic state; no actual server or network."""

import argparse
import copy
from contextlib import nullcontext, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import ees_deploy_stop_recovery as recovery


HEAD = "a" * 40
OLDER = "b" * 40
SECRET = "synthetic-private-value"


class RequestFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {"state_root": str(self.root), "source_python": "registered-python",
                       "host": "127.0.0.1", "port": 8080}
        self.bundle = self.root / "upgrade-example" / ("EES-demo-" + HEAD[:12] + ".zip")
        self.bundle.parent.mkdir()
        self.bundle.write_bytes(b"synthetic retained program")
        self.registry = {
            "schema_version": 2, "phase": "idle", "pending": None,
            "current": {"kind": "original", "source_commit": None, "python": "registered-python"},
            "process": {"pid": 4321, "group_id": 4321, "host": "127.0.0.1", "port": 8080,
                        "executable": "registered-python", "created": "synthetic-start"},
            "customization": {"active": {"source_commit": OLDER}, "previous": None, "pending": None},
        }
        self.request = {"registry": copy.deepcopy(self.registry), "failure": {
            "action": "upgrade", "failed": True, "result": {
                "stage": "process_stop", "changed": False, "wrapper_commit": HEAD,
                "process": {"error_type": "process"}, "bundle": str(self.bundle)}}}
        self.path = self.root / ("stop-recovery-" + "c" * 32 + ".json")
        self.write_request()

    def write_request(self):
        self.path.write_text(json.dumps(self.request), encoding="utf-8")


class RequestTests(RequestFixture):
    def test_reads_powershell_bom_and_retained_bundle(self):
        self.path.write_text(json.dumps(self.request), encoding="utf-8-sig")
        actual = recovery.read_request(self.config, self.path)
        self.assertEqual(actual, self.request)
        self.assertEqual(recovery.validate_failure(self.config, actual, HEAD), self.bundle)

    def test_rejects_bad_json_encoding_shape_size_and_name(self):
        for data in (b"{", b"\xff", b"[]", b"null", b'{}',
                     b'{"failure": {}, "registry": {}, "unexpected": true}', b" " * (1024 * 1024 + 1)):
            with self.subTest(data=data[:60]):
                self.path.write_bytes(data)
                with self.assertRaisesRegex(recovery.RecoveryError, "invalid_recovery_request"):
                    recovery.read_request(self.config, self.path)
        self.write_request()
        other = self.root / "last-operation.json"
        other.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(recovery.RecoveryError, "invalid_recovery_request"):
            recovery.read_request(self.config, other)
        nested = self.bundle.parent / self.path.name
        nested.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(recovery.RecoveryError, "invalid_recovery_request"):
            recovery.read_request(self.config, nested)

    def test_missing_and_nonregular_request_are_rejected(self):
        self.path.unlink()
        with self.assertRaises(recovery.manager.states.StateError):
            recovery.read_request(self.config, self.path)
        self.path.mkdir()
        with self.assertRaises(recovery.manager.states.StateError):
            recovery.read_request(self.config, self.path)

    def test_linked_request_and_bundle_are_rejected(self):
        for target in (self.path, self.bundle):
            with self.subTest(target=target.name):
                duplicate = target.with_suffix(".linked")
                try:
                    os.link(target, duplicate)
                except OSError as error:
                    self.skipTest("Hard links unavailable: " + type(error).__name__)
                try:
                    with self.assertRaises(recovery.manager.states.StateError):
                        if target == self.path:
                            recovery.read_request(self.config, self.path)
                        else:
                            recovery.validate_failure(self.config, self.request, HEAD)
                finally:
                    duplicate.unlink()

    def test_symlinked_bundle_is_rejected(self):
        source = self.root / "real.zip"
        self.bundle.rename(source)
        try:
            self.bundle.symlink_to(source)
        except OSError as error:
            self.skipTest("Symbolic links unavailable: " + type(error).__name__)
        with self.assertRaises(recovery.manager.states.StateError):
            recovery.validate_failure(self.config, self.request, HEAD)

    def test_only_approved_failure_shape_is_accepted(self):
        mutations = (
            ("failure", "action", "stop"), ("failure", "failed", False),
            ("result", "stage", "health_check"), ("result", "changed", True),
            ("result", "changed", 0), ("result", "wrapper_commit", OLDER),
            ("process", "error_type", "os_error"),
        )
        for section, field, value in mutations:
            with self.subTest(section=section, field=field, value=value):
                request = copy.deepcopy(self.request)
                target = request["failure"]
                if section != "failure":
                    target = target["result"]
                if section == "process":
                    target = target["process"]
                target[field] = value
                with self.assertRaisesRegex(recovery.RecoveryError, "not_the_approved_stop_failure"):
                    recovery.validate_failure(self.config, request, HEAD)

    def test_retained_bundle_must_match_commit_and_state_directory(self):
        candidates = (self.root / self.bundle.name,
                      self.root / "other" / self.bundle.name,
                      self.bundle.parent / "wrong.zip",
                      self.bundle.parent / "deeper" / self.bundle.name)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(b"synthetic unrelated file")
                request = copy.deepcopy(self.request)
                request["failure"]["result"]["bundle"] = str(candidate)
                with self.assertRaisesRegex(recovery.RecoveryError, "retained_bundle_mismatch"):
                    recovery.validate_failure(self.config, request, HEAD)
        self.request["failure"]["result"]["bundle"] = None
        with self.assertRaisesRegex(recovery.RecoveryError, "retained_bundle_missing"):
            recovery.validate_failure(self.config, self.request, HEAD)


class RecoveryFlowTests(RequestFixture):
    def setUp(self):
        super().setUp()
        self.args = argparse.Namespace(config=self.root / "config.json", request=self.path,
                                       commit=HEAD, terminate_recorded_process=True, health_timeout=120)
        self.progress = {"stage": "configuration", "changed": False, "terminated": False}
        self.events = []
        self.preflight = recovery.upgrade.preflight
        self.protected = {self.root / "webui.db": b"synthetic existing DB",
                          self.root / "secret.key": SECRET.encode(),
                          self.path: self.path.read_bytes(), self.bundle: self.bundle.read_bytes()}
        for path, data in self.protected.items():
            path.write_bytes(data)
        self.mock = {}

        def event(name, value=None):
            def invoke(*args, **kwargs):
                self.events.append(name)
                return value
            return invoke

        def record(config, registry, name):
            self.events.append(name)
            if name == "stop_recovered_by_operator":
                self.assertIsNone(registry["process"])
            self.registry = copy.deepcopy(registry)

        def apply(config, registry, bundle, commit, env, record, owner):
            self.events.append("apply")
            self.assertIsNone(registry["process"])
            self.assertEqual(bundle, self.bundle)
            self.assertEqual(commit, HEAD)
            registry["customization"]["active"] = {"source_commit": HEAD}

        def start(config, selected, env, registry, *, health_timeout, progress):
            self.events.append("start")
            self.assertEqual(health_timeout, 120)
            self.assertIsNone(registry["process"])
            registry["process"] = {"pid": 6789}
            progress["stage"] = "health_check"

        replacements = {
            "lock": patch.object(recovery.manager, "locked", return_value=nullcontext({"pid": 9})),
            "read": patch.object(recovery.manager, "read_registry", side_effect=lambda _: copy.deepcopy(self.registry)),
            "environment": patch.object(recovery.manager.states, "runtime_environment", side_effect=event("environment", {"DATA_DIR": "existing"})),
            "preflight": patch.object(recovery.upgrade, "preflight", side_effect=event("preflight")),
            "port": patch.object(recovery.manager, "require_free_port", side_effect=event("port")),
            "inspect": patch.object(recovery.manager.customization, "inspect_bundle", side_effect=event("inspect")),
            "terminate": patch.object(recovery.targets, "terminate_server_target", side_effect=event("terminate", True)),
            "stopped": patch.object(recovery.manager, "require_stopped", side_effect=event("stopped")),
            "record": patch.object(recovery.manager, "record", side_effect=record),
            "apply": patch.object(recovery.manager.customization, "apply", side_effect=apply),
            "start": patch.object(recovery.manager, "start_selected", side_effect=start),
            "stop": patch.object(recovery.manager, "stop_registered", side_effect=AssertionError("No graceful stop retry")),
            "network": patch("urllib.request.urlopen", side_effect=AssertionError("No network")),
        }
        for name, replacement in replacements.items():
            self.mock[name] = replacement.start()
            self.addCleanup(replacement.stop)

    def run_recovery(self):
        return recovery.recover(self.config, self.args, self.progress)

    def assert_preserved(self):
        for path, data in self.protected.items():
            self.assertEqual(path.read_bytes(), data, path.name)
        self.mock["stop"].assert_not_called()
        self.mock["network"].assert_not_called()

    def assert_not_terminated(self):
        for name in ("terminate", "stopped", "record", "apply", "start"):
            self.mock[name].assert_not_called()
        self.assert_preserved()

    def test_explicit_authorization_required_before_any_work(self):
        self.args.terminate_recorded_process = False
        with self.assertRaisesRegex(recovery.RecoveryError, "explicit_termination_authorization_required"):
            self.run_recovery()
        self.mock["lock"].assert_not_called()
        self.assert_not_terminated()

    def test_success_checks_before_termination_then_stops_records_applies_starts(self):
        result = self.run_recovery()
        self.assertEqual(self.events, ["environment", "preflight", "port", "inspect", "port",
                                      "terminate", "stopped", "stop_recovered_by_operator", "apply",
                                      "start", "stop_recovery_applied_by_operator"])
        self.mock["terminate"].assert_called_once_with(self.request["registry"]["process"], "registered-python")
        self.assertEqual(result["source_commit"], HEAD)
        self.assertTrue(result["changed"])
        self.assertTrue(result["started"])
        self.assertTrue(result["terminated"])
        self.assert_preserved()

    def test_changed_registry_before_preflight_never_terminates(self):
        self.registry["process"]["pid"] += 1
        with self.assertRaisesRegex(recovery.RecoveryError, "deployment_changed"):
            self.run_recovery()
        self.mock["preflight"].assert_not_called()
        self.assert_not_terminated()

    def test_changed_registry_during_inspection_never_terminates(self):
        self.mock["inspect"].side_effect = lambda *args: self.registry["process"].update(pid=9999)
        with self.assertRaisesRegex(recovery.RecoveryError, "deployment_changed"):
            self.run_recovery()
        self.assert_not_terminated()

    def test_changed_request_during_inspection_never_terminates(self):
        def changed(*args):
            self.request["failure"]["result"]["stage"] = "other"
            self.write_request()
            self.protected[self.path] = self.path.read_bytes()
        self.mock["inspect"].side_effect = changed
        with self.assertRaisesRegex(recovery.RecoveryError, "deployment_changed"):
            self.run_recovery()
        self.assert_not_terminated()

    def test_preflight_and_inspection_failures_never_terminate(self):
        for name in ("environment", "preflight", "inspect"):
            with self.subTest(name=name):
                original = self.mock[name].side_effect
                self.mock[name].side_effect = ValueError("synthetic check failure")
                try:
                    with self.assertRaisesRegex(ValueError, "synthetic check failure"):
                        self.run_recovery()
                    self.assert_not_terminated()
                finally:
                    self.mock[name].side_effect = original

    def test_actual_preflight_validates_selected_program_before_termination(self):
        self.mock["preflight"].side_effect = self.preflight
        with patch.object(recovery.manager, "selected_program", side_effect=ValueError("program invalid")), \
             patch.object(recovery.manager.customization, "check_applicability") as applicable:
            with self.assertRaisesRegex(ValueError, "program invalid"):
                self.run_recovery()
            applicable.assert_not_called()
        self.assert_not_terminated()

    def test_actual_preflight_rejects_different_interpreter(self):
        self.mock["preflight"].side_effect = self.preflight
        self.registry["current"]["python"] = "other-python"
        self.request["registry"] = copy.deepcopy(self.registry)
        self.write_request()
        self.protected[self.path] = self.path.read_bytes()
        with self.assertRaisesRegex(recovery.upgrade.UpgradeError, "original_interpreter_required"):
            self.run_recovery()
        self.assert_not_terminated()

    def test_port_occupied_initially_or_before_termination_blocks_action(self):
        for values in ((RuntimeError("listener returned"),), (None, RuntimeError("listener returned"))):
            with self.subTest(values=values):
                self.mock["port"].side_effect = values
                with self.assertRaisesRegex(RuntimeError, "listener returned"):
                    self.run_recovery()
                self.assert_not_terminated()

    def test_recorded_endpoint_or_group_mismatch_never_terminates(self):
        for field, value in (("host", "127.0.0.2"), ("port", 9999), ("group_id", 9999)):
            with self.subTest(field=field):
                original = self.registry["process"][field]
                self.registry["process"][field] = value
                self.request["registry"] = copy.deepcopy(self.registry)
                self.write_request()
                self.protected[self.path] = self.path.read_bytes()
                with self.assertRaisesRegex(recovery.RecoveryError, "recorded_server_mismatch"):
                    self.run_recovery()
                self.assert_not_terminated()
                self.registry["process"][field] = original

    def test_termination_failure_never_clears_process_or_changes_program(self):
        self.mock["terminate"].side_effect = recovery.manager.processes.ProcessError("synthetic error")
        with self.assertRaises(recovery.manager.processes.ProcessError):
            self.run_recovery()
        for name in ("stopped", "record", "apply", "start"):
            self.mock[name].assert_not_called()
        self.assertEqual(self.registry, self.request["registry"])
        self.assertFalse(self.progress["terminated"])
        self.assert_preserved()

    def test_remaining_process_after_termination_blocks_record_and_apply(self):
        self.mock["stopped"].side_effect = RuntimeError("still running")
        with self.assertRaisesRegex(RuntimeError, "still running"):
            self.run_recovery()
        self.assertTrue(self.progress["terminated"])
        for name in ("record", "apply", "start"):
            self.mock[name].assert_not_called()
        self.assertEqual(self.registry, self.request["registry"])
        self.assert_preserved()

    def test_record_failure_blocks_apply_and_start(self):
        self.mock["record"].side_effect = OSError("synthetic write failure")
        with self.assertRaises(OSError):
            self.run_recovery()
        self.assertEqual(self.progress["stage"], "stop_record")
        self.mock["apply"].assert_not_called()
        self.mock["start"].assert_not_called()
        self.assert_preserved()

    def test_apply_failure_retains_input_and_does_not_start_or_repeat(self):
        self.mock["apply"].side_effect = ValueError("synthetic apply failure")
        with self.assertRaises(ValueError):
            self.run_recovery()
        self.assertEqual(self.progress["stage"], "apply")
        self.assertIsNone(self.progress["changed"])
        self.mock["start"].assert_not_called()
        self.assertIsNone(self.registry["process"])
        self.assert_preserved()
        with self.assertRaisesRegex(recovery.RecoveryError, "deployment_changed"):
            self.run_recovery()
        self.mock["terminate"].assert_called_once()

    def test_health_failure_retains_new_program_without_stop_retry(self):
        original = self.mock["start"].side_effect
        def unhealthy(*args, **kwargs):
            original(*args, **kwargs)
            raise recovery.manager.processes.ProcessError("synthetic health timeout")
        self.mock["start"].side_effect = unhealthy
        with self.assertRaises(recovery.manager.processes.ProcessError):
            self.run_recovery()
        self.assertTrue(self.progress["changed"])
        self.assertEqual(self.progress["stage"], "health_check")
        self.assertEqual(self.mock["record"].call_count, 1)
        self.mock["terminate"].assert_called_once()
        self.assert_preserved()

    def test_saved_request_cannot_repeat_against_successful_new_registry(self):
        self.run_recovery()
        with self.assertRaisesRegex(recovery.RecoveryError, "deployment_changed"):
            self.run_recovery()
        self.mock["terminate"].assert_called_once()
        self.mock["apply"].assert_called_once()
        self.mock["start"].assert_called_once()
        self.assert_preserved()


class ReportTests(unittest.TestCase):
    def test_confirmed_termination_survives_later_process_failure(self):
        default_error = recovery.manager.processes.ProcessError("synthetic start failure")
        self.assertIsNone(default_error.terminated)
        # An ordinary ProcessError has no termination observation. An explicit
        # false observation about a later Start must not erase the earlier Stop.
        for stage in ("process_stop", "health_check"):
            for error in (default_error, recovery.manager.processes.ProcessError(
                    "synthetic later process failure", terminated=False)):
                with self.subTest(stage=stage, error_terminated=error.terminated):
                    def fail(config, args, progress):
                        progress.update(stage=stage, terminated=True, changed=stage == "health_check")
                        raise error
                    output = io.StringIO()
                    with patch.object(recovery.manager.states, "load_config", return_value={}), \
                         patch.object(recovery, "recover", side_effect=fail), \
                         patch.object(recovery.manager, "save_operation", return_value=True) as save, \
                         redirect_stdout(output):
                        code = recovery.main(["--config", "config.json", "--request", "request.json",
                                              "--commit", HEAD, "--terminate-recorded-process"])
                    self.assertEqual(code, 1)
                    self.assertIn("terminated=true", output.getvalue())
                    self.assertIn("stage=" + stage, output.getvalue())
                    self.assertIs(save.call_args.args[1]["terminated"], True)
                    self.assertEqual(save.call_args.args[1]["changed"], stage == "health_check")

    def test_main_preserves_numeric_error_diagnostic_without_private_text(self):
        error = recovery.manager.processes.ProcessError(SECRET + " C:\\private\\path")
        error.operation, error.errno, error.winerror = "process_terminate", 13, 5
        def fail(config, args, progress):
            progress["stage"] = "process_stop"
            raise error
        output = io.StringIO()
        with patch.object(recovery.manager.states, "load_config", return_value={}), \
             patch.object(recovery, "recover", side_effect=fail), \
             patch.object(recovery.manager, "save_operation", return_value=True) as save, \
             redirect_stdout(output):
            code = recovery.main(["--config", "config.json", "--request", "request.json", "--commit", HEAD])
        self.assertEqual(code, 1)
        self.assertIn("operation=process_terminate errno=13 winerror=5", output.getvalue())
        self.assertIn("stage=process_stop", output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn(SECRET, json.dumps(save.call_args.args[1]))

    def test_report_rejects_unstructured_values_and_preserves_save_failure(self):
        result = {"stage": SECRET + "\npath", "code": "https://private/token", "source_commit": SECRET,
                  "bundle": "C:\\private\\path", "process": {"operation": SECRET, "errno": SECRET, "winerror": True}}
        output = io.StringIO()
        with patch.object(recovery.manager, "save_operation", return_value=False), redirect_stdout(output):
            recovery.report(argparse.Namespace(config=Path("config.json")), result, failed=True)
        actual = output.getvalue()
        self.assertEqual(len(actual.splitlines()), 1)
        self.assertIn("stage=-", actual)
        self.assertIn("code=-", actual)
        self.assertIn("report=unavailable", actual)
        self.assertNotIn(SECRET, actual)
        self.assertNotIn("private", actual)


@unittest.skipUnless(os.name == "nt", "Recovery capture guide compatibility is Windows-only.")
class PowerShellCaptureTests(unittest.TestCase):
    def test_documented_capture_preserves_raw_json_in_windows_powershell_and_pwsh(self):
        shells = list(dict.fromkeys(path for name in ("powershell", "pwsh")
                                    if (path := shutil.which(name))))
        if not shells:
            self.skipTest("No PowerShell interpreter is installed.")
        guide = (Path(__file__).resolve().parents[1] / "docs" /
                 "03-openwebui-native-agent.md").read_text(encoding="utf-8")
        section = guide.split('<a id="ees-stop-recovery"></a>', 1)[1].split('<a id=', 1)[0]
        block = section.split("```powershell\n", 1)[1].split("```", 1)[0]
        update = "    & (Join-Path $repo 'scripts\\manage-ees.ps1') -Action Update"
        self.assertEqual(block.count(update), 1, "Capture boundary must be explicit and unique.")
        prefix = block.split(update, 1)[0] + "}\n"
        # Execute only the snapshot prefix. The full block is parsed as data;
        # neither the Update adapter nor any recovery/process code is invoked.
        self.assertNotIn("-Action", prefix)
        self.assertNotIn("source_python -I", prefix)
        self.assertNotIn("ees_deploy_stop_recovery.py", prefix)
        parser = (
            "[Console]::Error.WriteLine('ees_probe=powershell-entry version=' + $PSVersionTable.PSVersion.ToString()); [Console]::Error.Flush()\n"
            "$tokens = $null; $parseErrors = $null\n"
            "$full = [IO.File]::ReadAllText($env:EES_TEST_CAPTURE_GUIDE)\n"
            "[void][System.Management.Automation.Language.Parser]::ParseInput("
            "$full, [ref]$tokens, [ref]$parseErrors)\n"
            "if ($parseErrors.Count -ne 0) { throw 'Guide PowerShell syntax invalid.' }\n"
            "[Console]::Error.WriteLine('ees_probe=powershell-parsed'); [Console]::Error.Flush()\n"
        )
        for shell in shells:
            with self.subTest(shell=Path(shell).name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                profile, local, state = root / "profile", root / "local", root / "state"
                (profile / "team-agent-poc").mkdir(parents=True)
                deployment = local / "EES-Agent-POC" / "deployment"
                deployment.mkdir(parents=True)
                state.mkdir()
                failure = {"action": "upgrade", "failed": True,
                           "failed_at": "2026-09-10T08:09:10.123456+00:00",
                           "result": {"stage": "process_stop", "changed": False,
                                      "label": "한글 실패 보존", "nested": {"date": "2026-09-10T17:09:10+09:00"}}}
                registry = {"schema_version": 2, "process": {
                    "pid": 4321, "created": "134115653501234567",
                    "started_at": "2026-09-10T08:09:10.123456+00:00",
                    "nested": ["한글 데이터", {"date": "2026-09-10T00:00:00Z", "value": None}]}}
                config = {"state_root": str(state), "source_python": sys.executable}
                files = {deployment / "config.json": config,
                         state / "last-operation.json": failure, state / "deployment.json": registry}
                originals = {}
                for path, value in files.items():
                    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                    originals[path] = path.read_bytes()
                full_path = root / "full-guide.ps1"
                full_path.write_text(block, encoding="utf-8")
                env = dict(os.environ, USERPROFILE=str(profile), LOCALAPPDATA=str(local),
                           EES_TEST_CAPTURE_GUIDE=str(full_path))
                command = parser + prefix + "[Console]::Error.WriteLine('ees_probe=powershell-captured'); [Console]::Error.Flush()\n"
                try:
                    result = subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive",
                                             "-Command", command], env=env, cwd=root,
                                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
                except subprocess.TimeoutExpired as error:
                    stderr = error.stderr or ""
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    stages = [line for line in stderr.splitlines() if line.startswith("ees_probe=")]
                    raise AssertionError(Path(shell).name + " capture probe timed out after 20s; stderr stages: "
                                         + (", ".join(stages) or "entry not observed")) from None
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                captures = list(state.glob("stop-recovery-*.json"))
                self.assertEqual(len(captures), 1)
                self.assertEqual(json.loads(captures[0].read_bytes()), {"failure": failure, "registry": registry})
                for path, data in originals.items():
                    self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
