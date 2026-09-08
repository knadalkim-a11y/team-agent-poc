"""Transaction tests use synthetic state; never start or inspect a real server."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manage_ees", ROOT / "scripts" / "manage_ees.py")
MANAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MANAGER)
COMMIT = "a" * 40
WAIT_HEALTHY = MANAGER.processes.wait_healthy


class DeploymentTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {
            "state_root": str(self.root), "source_python": "original-python", "cwd": "original-cwd",
            "data_dir": "original-data", "host": "127.0.0.1", "port": 8080,
            "releases_dir": str(self.root / "releases"), "uv_exe": "existing-uv",
        }
        self.original = {"kind": "original", "source_commit": None, "python": "original-python"}
        self.candidate = {"kind": "release", "source_commit": COMMIT, "python": "candidate-python"}
        self.original_process = {"pid": 100, "executable": "original-python", "host": "127.0.0.1", "port": 8080}
        self.candidate_process = {"pid": 200, "executable": "candidate-python", "host": "127.0.0.1", "port": 8080}
        self.registry = {"schema_version": 1, "phase": "idle", "current": self.original,
                         "previous": None, "process": self.original_process}
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        self.events = []
        self.port_free = False
        self.latest_process = None

        def stopped(identity):
            self.events.append("stop:" + identity["executable"])
            self.port_free = True

        def start(executable, cwd, env, host, port, logs):
            self.events.append("start:" + executable)
            self.assertTrue(self.port_free)
            self.assertEqual((cwd, host, port), ("original-cwd", "127.0.0.1", 8080))
            self.assertEqual(env["DATA_DIR"], "original-data")
            self.assertEqual(env["WEBUI_SECRET_KEY"], "synthetic-key")
            self.assertEqual(env["CORS_ALLOW_ORIGIN"], "synthetic-origin")
            self.port_free = False
            self.latest_process = self.candidate_process if executable == "candidate-python" else self.original_process
            return self.latest_process

        def backup(config):
            self.events.append("backup")
            self.assertTrue(self.port_free)
            self.assertEqual(config, self.config)
            return {"verified": True, "path": "synthetic-backup"}

        overrides = [
            patch.object(MANAGER.states, "runtime_environment", return_value={
                "DATA_DIR": "original-data", "WEBUI_SECRET_KEY": "synthetic-key", "CORS_ALLOW_ORIGIN": "synthetic-origin"}),
            patch.object(MANAGER.releases, "validate_prepared", return_value={"target_python": "candidate-python"}),
            patch.object(MANAGER.processes, "port_is_free", side_effect=lambda *_, **kwargs: self.port_free),
            patch.object(MANAGER.processes, "verify_identity", return_value=True),
            patch.object(MANAGER.processes, "stop_server", side_effect=stopped),
            patch.object(MANAGER.processes, "start_server", side_effect=start),
            patch.object(MANAGER.processes, "wait_healthy", side_effect=lambda _, **kwargs: self.events.append("health")),
            patch.object(MANAGER.states, "backup_state", side_effect=backup),
        ]
        self.mocks = []
        for override in overrides:
            self.mocks.append(override.start())
            self.addCleanup(override.stop)

    def read(self):
        return MANAGER.read_registry(self.config)

    def test_diagnose_reads_report_without_server_or_state_operations(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        args = argparse.Namespace(action="diagnose", config="unused.json")
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.reports, "collect", return_value={"status": "unavailable", "reason": "no_failure"}) as collect, \
                patch.object(MANAGER, "locked", side_effect=AssertionError("must not lock")), \
                patch.object(MANAGER.states, "runtime_environment", side_effect=AssertionError("must not probe environment again")), \
                patch.object(MANAGER.releases, "validate_prepared", side_effect=AssertionError("must not probe packages")):
            result = MANAGER.operate(args)
        collect.assert_called_once_with(self.config, self.registry)
        self.assertTrue(result["original_program"])
        self.assertTrue(result["managed_process_running"])
        self.assertEqual(self.events, [])
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
        self.assertFalse((self.root / "deployment.lock").exists())

    def test_diagnose_cli_does_not_echo_persisted_failure_values(self):
        self.registry["last_failure"] = {
            "action": "private-action", "failed_at": "private-date",
            "switch": {"stage": "private-stage", "error_type": "private-error", "message": "private-token"},
            "recovery_status": "private-recovery"}
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        output = io.StringIO()
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.reports, "collect", return_value={"status": "unavailable", "reason": "no_failure"}), \
                redirect_stdout(output):
            self.assertEqual(MANAGER.main(["diagnose", "--config", "unused.json"]), 0)
        self.assertIn("EES diagnosis v1", output.getvalue())
        self.assertNotIn("private-", output.getvalue())

    def test_diagnose_discards_log_report_if_registry_changes_during_read(self):
        def changed(*_):
            self.registry["last_event"] = "started_by_operator"
            MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
            return {"status": "ok"}
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.reports, "collect", side_effect=changed):
            result = MANAGER.operate(argparse.Namespace(action="diagnose", config="unused.json"))
        self.assertEqual(result["candidate"], {"status": "unavailable", "reason": "state_changed_or_busy"})
        self.assertEqual(self.events, [])

    def test_switch_orders_shutdown_backup_start_then_commits_pointer(self):
        def health(_, *, timeout):
            self.assertEqual(self.read()["current"], self.original)
            self.assertEqual(self.read()["phase"], "switching")
            self.assertEqual(self.read()["process"], self.candidate_process)
            self.events.append("health")

        self.mocks[6].side_effect = health
        MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertEqual(self.events, ["stop:original-python", "backup", "start:candidate-python", "health"])
        current = self.read()
        self.assertEqual(current["current"], self.candidate)
        self.assertEqual(current["previous"], self.original)
        self.assertEqual(current["phase"], "idle")
        self.assertFalse((self.root / "deployment.lock").exists())

    def test_candidate_failure_recovers_original_without_restoring_database(self):
        probes = []

        def health(identity, *, timeout):
            probes.append((identity, timeout))
            if identity == self.candidate_process:
                raise MANAGER.processes.ProcessError("synthetic startup failure")

        self.mocks[6].side_effect = health
        marker = self.root / "synthetic-memory.txt"
        marker.write_bytes(b"New user memory is not rolled back")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "previous program is running"):
            MANAGER.switch(self.config, self.candidate, "deployed", health_timeout=125)
        self.assertEqual(probes, [(self.candidate_process, 125), (self.original_process, 125)])
        self.assertEqual(self.read()["current"], self.original)
        self.assertEqual(self.read()["process"], self.original_process)
        self.assertEqual(self.read()["phase"], "idle")
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["stage"], "health_check")
        self.assertEqual(failure["recovery_status"], "succeeded")
        self.assertIsNone(failure["recovery"])
        self.assertIn("stop:candidate-python", self.events)
        self.assertEqual(marker.read_bytes(), b"New user memory is not rolled back")

    def test_failed_candidate_shutdown_blocks_second_server_and_marks_recovery(self):
        self.mocks[6].side_effect = MANAGER.processes.ProcessError("startup failed")
        self.mocks[4].side_effect = [None, MANAGER.processes.ProcessError("shutdown timed out")]
        self.port_free = True
        with self.assertRaisesRegex(MANAGER.DeploymentError, "recovery needs attention"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertEqual(self.read()["phase"], "recovery_required")
        self.assertEqual(self.read()["process"], self.candidate_process)
        self.assertEqual(self.events.count("start:original-python"), 0)
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["stage"], "health_check")
        self.assertEqual(failure["recovery"]["stage"], "process_stop")
        self.assertEqual(failure["recovery_status"], "failed")

    def test_backup_failure_does_not_launch_candidate_and_recovers_original(self):
        self.mocks[7].side_effect = MANAGER.states.StateError("synthetic backup failed")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "previous program is running"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertNotIn("start:candidate-python", self.events)
        self.assertEqual(self.read()["current"], self.original)
        self.assertEqual(self.read()["last_failure"]["switch"]["stage"], "backup")

    def test_unidentified_launched_child_blocks_automatic_recovery_even_before_listen(self):
        self.mocks[5].side_effect = MANAGER.processes.LaunchUncertain("identity unavailable")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "Automatic recovery was blocked"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[5].assert_called_once()
        self.assertEqual(self.read()["phase"], "recovery_required")
        self.assertTrue(self.read()["launch_uncertain"])
        self.assertEqual(self.read()["last_failure"]["switch"]["error_type"], "launch_uncertain")
        self.assertEqual(self.read()["last_failure"]["recovery_status"], "blocked")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "could not be identified"):
            MANAGER.stop_registered(self.config, self.read())

    def test_unmanaged_listener_is_not_stopped_and_no_backup_is_started(self):
        self.registry["process"] = None
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        with self.assertRaisesRegex(MANAGER.DeploymentError, "preflight failed"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[4].assert_not_called()
        self.mocks[7].assert_not_called()
        self.assertEqual(self.read()["phase"], "idle")
        self.assertEqual(self.read()["last_failure"]["recovery_status"], "not_attempted")
        self.assertEqual(self.read()["last_failure"]["switch"]["stage"], "port_check")

    def test_process_identity_mismatch_never_advances_the_switch(self):
        self.mocks[4].side_effect = MANAGER.processes.ProcessError("identity changed")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "preflight failed"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[7].assert_not_called()
        self.mocks[5].assert_not_called()
        self.assertEqual(self.read()["last_failure"]["switch"]["stage"], "process_stop")

    def test_backup_and_recovery_bind_failures_keep_codes_without_private_text(self):
        private = "synthetic-key http://private.invalid C:\\private\\server.log"
        socket_error = OSError(10049, private)
        socket_error.winerror = 10049
        self.mocks[7].side_effect = MANAGER.states.StateError(private)
        bind_error = MANAGER.processes.ProcessError("The listen port is unavailable.",
                                                   cause=socket_error, operation="port_bind")
        self.mocks[2].side_effect = [True, bind_error]
        with self.assertRaises(MANAGER.DeploymentError) as caught:
            MANAGER.switch(self.config, self.candidate, "deployed")
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["stage"], "backup")
        self.assertEqual(failure["recovery"], {"stage": "port_check", "error_type": "process",
                                             "operation": "port_bind", "errno": 10049, "winerror": 10049})
        self.assertEqual(failure, caught.exception.diagnostics)
        self.mocks[5].assert_not_called()
        self.assertNotIn(private, json.dumps(failure) + str(caught.exception))
        self.assertEqual(self.read()["phase"], "recovery_required")

    def test_failed_recovery_launch_keeps_uncertainty_and_never_retries(self):
        self.mocks[7].side_effect = MANAGER.states.StateError("backup failed")
        self.mocks[5].side_effect = MANAGER.processes.LaunchUncertain("private launch detail")
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[5].assert_called_once()
        current = self.read()
        self.assertTrue(current["launch_uncertain"])
        self.assertEqual(current["phase"], "recovery_required")
        self.assertEqual(current["last_failure"]["switch"]["stage"], "backup")
        self.assertEqual(current["last_failure"]["recovery"]["error_type"], "launch_uncertain")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "could not be identified"):
            MANAGER.stop_registered(self.config, current)

    def test_cli_reports_distinct_failures_and_does_not_echo_exception_details(self):
        private = "SYNTHETIC-PAT C:\\private\\server.log http://private.invalid"
        first, second = OSError(13, private), OSError(98, private)
        first.winerror, second.winerror = "SYNTHETIC-PAT", 10048
        self.mocks[6].side_effect = [first, second]
        output = io.StringIO()
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                redirect_stderr(output), self.assertRaises(SystemExit) as caught:
            MANAGER.main(["deploy", "--config", "unused.json", "--commit", COMMIT])
        self.assertEqual(caught.exception.code, 1)
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["errno"], 13)
        self.assertIsNone(failure["switch"]["winerror"])
        self.assertEqual(failure["recovery"]["errno"], 98)
        self.assertEqual(failure["recovery"]["winerror"], 10048)
        self.assertEqual(json.loads(output.getvalue().split("Diagnostics: ")[1]), failure)
        self.assertNotIn(private, output.getvalue() + json.dumps(failure))

    def test_terminal_record_failure_keeps_diagnostics_after_recovery(self):
        original_record = MANAGER.record
        self.mocks[6].side_effect = [MANAGER.processes.ProcessError("private failure"), None]

        def record(config, registry, event):
            if event == "previous_program_recovered":
                raise OSError("private disk path")
            original_record(config, registry, event)

        with patch.object(MANAGER, "record", side_effect=record), \
                self.assertRaisesRegex(MANAGER.DeploymentError, "record could not be saved") as caught:
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertEqual(caught.exception.diagnostics["recovery_status"], "succeeded")
        self.assertEqual(caught.exception.diagnostics["switch"]["stage"], "health_check")
        self.assertIn("start:original-python", self.events)
        self.assertNotIn("private", str(caught.exception))

    def test_status_accepts_old_state_and_filters_persisted_failure_fields(self):
        args = argparse.Namespace(action="status", config="unused.json")
        with patch.object(MANAGER.states, "load_config", return_value=self.config):
            self.assertIsNone(MANAGER.operate(args)["last_failure"])
            self.registry["last_failure"] = {
                "action": "SYNTHETIC-PAT", "failed_at": "SYNTHETIC-PAT", "raw": "SYNTHETIC-PAT",
                "switch": {"stage": ["SYNTHETIC-PAT"], "error_type": "SYNTHETIC-PAT", "errno": True,
                           "winerror": "SYNTHETIC-PAT", "operation": "SYNTHETIC-PAT"},
                "recovery": {"stage": "port_check", "errno": 98}, "recovery_status": ["SYNTHETIC-PAT"],
            }
            MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
            result = MANAGER.operate(args)
        self.assertNotIn("SYNTHETIC-PAT", json.dumps(result))
        self.assertIsNone(result["last_failure"]["switch"]["errno"])
        self.assertEqual(result["last_failure"]["recovery"]["errno"], 98)

    def test_switch_record_failures_report_stage_without_extra_launches(self):
        original_record = MANAGER.record
        for failed_event in ("switch_started", "deployed"):
            with self.subTest(failed_event=failed_event):
                MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
                self.events.clear()
                self.port_free = False

                def record(config, registry, event):
                    if event == failed_event:
                        raise OSError(13, "private disk path")
                    original_record(config, registry, event)

                with patch.object(MANAGER, "record", side_effect=record), \
                        self.assertRaises(MANAGER.DeploymentError) as caught:
                    MANAGER.switch(self.config, self.candidate, "deployed")
                failure = caught.exception.diagnostics
                self.assertEqual(failure["switch"]["stage"], "switch_record")
                self.assertEqual(failure["switch"]["errno"], 13)
                self.assertEqual(failure["recovery_status"], "not_attempted")
                self.assertNotIn("private", str(caught.exception))
                self.assertEqual(self.events.count("start:candidate-python"), int(failed_event == "deployed"))
                self.assertNotIn("start:original-python", self.events)

    def test_uncertain_launch_record_failure_keeps_primary_failure_and_blocks_recovery(self):
        original_record = MANAGER.record
        self.mocks[5].side_effect = MANAGER.processes.LaunchUncertain("private inspection detail")

        def record(config, registry, event):
            if event == "process_identity_unavailable_after_launch":
                raise OSError(13, "private disk path")
            original_record(config, registry, event)

        with patch.object(MANAGER, "record", side_effect=record), \
                self.assertRaisesRegex(MANAGER.DeploymentError, "record could not be saved") as caught:
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertEqual(caught.exception.diagnostics["switch"]["error_type"], "launch_uncertain")
        self.assertEqual(caught.exception.diagnostics["recovery_status"], "blocked")
        self.mocks[5].assert_called_once()
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(self.read()["phase"], "switching")

    def test_later_success_keeps_timestamped_last_failure_as_history(self):
        self.mocks[6].side_effect = [MANAGER.processes.ProcessError("startup failed"), None]
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed")
        failure = self.read()["last_failure"]
        self.mocks[6].side_effect = None
        result = MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertTrue(result["active"])
        self.assertEqual(self.read()["last_failure"], failure)
        self.assertEqual(self.read()["last_event"], "deployed")

    def test_rollback_keeps_live_data_and_selects_previous_program(self):
        self.registry.update(current=self.candidate, previous=self.original, process=self.candidate_process)
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        marker = self.root / "synthetic-new-chat.txt"
        marker.write_text("Conversation added after deployment", encoding="utf-8")
        result = MANAGER.switch(self.config, None, "rolled_back_program")
        self.assertEqual(self.read()["current"], self.original)
        self.assertFalse(result["data_restored"])
        self.assertEqual(marker.read_text(encoding="utf-8"), "Conversation added after deployment")

    def test_lock_and_interrupted_state_refuse_a_second_mutation(self):
        with MANAGER.locked(self.config):
            with self.assertRaisesRegex(MANAGER.DeploymentError, "lock exists"):
                MANAGER.switch(self.config, self.candidate, "deployed")
        self.registry["phase"] = "recovery_required"
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        with self.assertRaisesRegex(MANAGER.DeploymentError, "needs recovery"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[4].assert_not_called()

    def test_default_start_waits_for_health_after_sixty_seconds_without_real_sleep(self):
        self.registry["process"] = None
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        self.port_free = True
        clock = [0.0]

        def advance(seconds):
            clock[0] += seconds

        self.mocks[6].side_effect = WAIT_HEALTHY
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.processes.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(MANAGER.processes.time, "sleep", side_effect=advance), \
                patch.object(MANAGER.processes, "_healthy", side_effect=lambda *_: clock[0] >= 75), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(MANAGER.main(["start", "--config", str(self.root / "config.json")]), 0)

        self.assertGreaterEqual(clock[0], 75)
        self.assertLess(clock[0], 76)
        self.mocks[6].assert_called_once_with(self.original_process, timeout=300)
        self.assertEqual(self.read()["last_event"], "started_by_operator")
        self.assertEqual(self.events, ["start:original-python"])

    def test_explicit_health_timeout_reaches_start_deploy_and_rollback(self):
        cases = [
            ("start", self.original, None, self.original_process),
            ("deploy", self.original, None, self.original_process),
            ("deploy", self.candidate, self.original, self.candidate_process),
            ("rollback", self.candidate, self.original, self.candidate_process),
        ]
        for action, current, previous, process in cases:
            with self.subTest(action=action, current=current["kind"]):
                self.registry.update(current=current, previous=previous, process=process)
                MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
                self.port_free = False
                self.mocks[6].reset_mock()
                args = argparse.Namespace(action=action, config=self.root / "config.json",
                                          commit=COMMIT, health_timeout=900)
                with patch.object(MANAGER.states, "load_config", return_value=self.config):
                    MANAGER.operate(args)
                expected = self.candidate_process if action == "deploy" else self.original_process
                self.mocks[6].assert_called_once_with(expected, timeout=900)

    def test_health_timeout_cli_rejects_invalid_values_before_any_operation(self):
        for value in ["0", "901", "-1", "1.5", "invalid"]:
            with self.subTest(value=value), patch.object(MANAGER, "operate") as operate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MANAGER.main(["start", "--config", "unused.json", "--health-timeout", value])
            self.assertEqual(error.exception.code, 2)
            operate.assert_not_called()
        for value in ["1", "900"]:
            with self.subTest(value=value), patch.object(MANAGER, "operate", return_value={}) as operate, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(MANAGER.main(["start", "--config", "unused.json", "--health-timeout", value]), 0)
            self.assertEqual(operate.call_args.args[0].health_timeout, int(value))

    def test_windows_ca_selection_survives_start_and_rollback_without_changing_original_env(self):
        digest = "b" * 64
        bundle = self.root / "synthetic-ca.pem"
        launched = []
        original_start = self.mocks[5].side_effect

        def start(executable, cwd, env, *rest):
            launched.append((executable, dict(env)))
            return original_start(executable, cwd, env, *rest)

        def prepare(*args, **kwargs):
            self.assertEqual(self.events, [])  # Trust material is ready before the first stop.
            self.assertEqual(args[1], "candidate-python")
            self.assertNotIn("REQUESTS_CA_BUNDLE", args[2])
            self.assertEqual(kwargs["cwd"], "original-cwd")
            return digest

        self.mocks[5].side_effect = start
        with patch.object(MANAGER.releases, "prepare_windows_ca", side_effect=prepare) as collect, \
                patch.object(MANAGER.releases, "windows_ca_path", return_value=bundle), \
                patch.object(MANAGER.states, "load_config", return_value=self.config):
            MANAGER.switch(self.config, self.candidate, "deployed", use_windows_ca=True)
            self.assertEqual(self.read()["current"]["ca_bundle_sha256"], digest)
            self.assertNotIn("ca_bundle_sha256", self.candidate)
            args = argparse.Namespace(action="status", config="unused.json", health_timeout=300)
            self.assertEqual(MANAGER.operate(args)["ca_mode"], "windows_snapshot")
            args.action = "stop"
            MANAGER.operate(args)
            args.action = "start"
            MANAGER.operate(args)
            MANAGER.switch(self.config, None, "rolled_back_program")
            self.assertEqual(self.read()["current"], self.original)
            MANAGER.switch(self.config, None, "rolled_back_program")
            self.assertEqual(self.read()["current"]["ca_bundle_sha256"], digest)
            collect.assert_called_once()
        self.assertEqual([exe for exe, _ in launched],
                         ["candidate-python", "candidate-python", "original-python", "candidate-python"])
        for exe, env in launched:
            for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
                if exe == "candidate-python":
                    self.assertEqual(env[name], str(bundle))
                else:
                    self.assertNotIn(name, env)

    def test_windows_ca_preparation_failure_keeps_current_server_running(self):
        with patch.object(MANAGER.releases, "prepare_windows_ca",
                          side_effect=MANAGER.releases.ReleaseError("Windows CA export failed.")), \
                self.assertRaises(MANAGER.DeploymentError) as caught:
            MANAGER.switch(self.config, self.candidate, "deployed", use_windows_ca=True)
        self.assertEqual(self.events, [])
        self.assertEqual(self.read()["current"], self.original)
        self.assertEqual(self.read()["process"], self.original_process)
        self.assertEqual(caught.exception.diagnostics["switch"]["stage"], "select_program")
        self.assertEqual(caught.exception.diagnostics["switch"]["error_type"], "release")

    def test_windows_ca_failed_candidate_recovery_uses_saved_original_ca(self):
        saved = self.mocks[0].return_value
        saved.update(REQUESTS_CA_BUNDLE="saved-requests-ca", SSL_CERT_FILE="saved-ssl-ca")
        original_start = self.mocks[5].side_effect
        launched = []

        def start(executable, cwd, env, *rest):
            launched.append((executable, dict(env)))
            return original_start(executable, cwd, env, *rest)

        def health(identity, **kwargs):
            if identity == self.candidate_process:
                raise MANAGER.processes.ProcessError("synthetic startup failure")

        self.mocks[5].side_effect = start
        self.mocks[6].side_effect = health
        with patch.object(MANAGER.releases, "prepare_windows_ca", return_value="b" * 64), \
                patch.object(MANAGER.releases, "windows_ca_path", return_value=Path("candidate-ca")), \
                self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed", use_windows_ca=True)
        self.assertEqual(launched[0][1]["REQUESTS_CA_BUNDLE"], "candidate-ca")
        self.assertEqual(launched[1][1], saved)
        self.assertEqual(self.read()["current"], self.original)
        self.assertEqual(self.read()["last_failure"]["recovery_status"], "succeeded")

    def test_windows_ca_cli_rejects_other_actions_and_forwards_deploy_option(self):
        for action in ("init", "status", "diagnose", "plan", "prepare", "rollback", "start", "stop"):
            with self.subTest(action=action), patch.object(MANAGER, "operate") as operate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MANAGER.main([action, "--config", "unused.json", "--use-windows-ca"])
            self.assertEqual(error.exception.code, 2)
            operate.assert_not_called()
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER, "switch", return_value={}) as switch, redirect_stdout(io.StringIO()):
            MANAGER.main(["deploy", "--config", "unused.json", "--commit", COMMIT, "--use-windows-ca"])
        self.assertTrue(switch.call_args.kwargs["use_windows_ca"])


if __name__ == "__main__":
    unittest.main()
