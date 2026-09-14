"""Transaction tests use synthetic state; never start or inspect a real server."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manage_ees", ROOT / "scripts" / "manage_ees.py")
MANAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MANAGER)
COMMIT = "a" * 40
WAIT_HEALTHY = MANAGER.processes.wait_healthy
OPERATOR = {"pid": 4242, "executable": "synthetic-operator-python", "created_at": "1234"}


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
        self.original_process = {"pid": 100, "executable": "original-python", "host": "127.0.0.1", "port": 8080,
                                 "log_file": str(self.root / "logs" / ("server-" + "1" * 32 + ".log"))}
        self.candidate_process = {"pid": 200, "executable": "candidate-python", "host": "127.0.0.1", "port": 8080,
                                  "log_file": str(self.root / "logs" / ("server-" + "2" * 32 + ".log"))}
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
            patch.object(MANAGER.processes, "check_accept_runtime", return_value="compatible"),
            patch.object(MANAGER.processes, "accept_guard_status", return_value="win64_retry"),
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
        self.assertIn("EES diagnosis v2", output.getvalue())
        self.assertNotIn("private-", output.getvalue())

    def test_diagnose_keeps_log_evidence_when_process_inspection_fails(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        report = {"status": "unavailable", "reason": "candidate_log_missing"}
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.reports, "collect", return_value=report), \
                patch.object(MANAGER.processes, "verify_identity", side_effect=MANAGER.processes.ProcessError("private-inspection")):
            result = MANAGER.operate(argparse.Namespace(action="diagnose", config="unused"))
        self.assertIsNone(result["managed_process_running"])
        self.assertEqual(result["process_check"], "inspection_unavailable")
        self.assertEqual(result["candidate"], report)
        self.assertNotIn("private-inspection", MANAGER.render_diagnosis(result))
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
        self.assertEqual(self.events, [])

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

    def test_timeout_evidence_keeps_candidate_log_after_successful_recovery(self):
        self.mocks[6].side_effect = [MANAGER.processes.ProcessError(
            "private detail", reason="health_timeout", elapsed_seconds=125.1, timeout_seconds=125), None]
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed", health_timeout=125)
        failure = self.read()["last_failure"]
        self.assertEqual(failure["evidence_version"], 1)
        self.assertEqual(failure["candidate"], {"kind": "release", "source_commit": COMMIT})
        self.assertEqual(failure["switch"]["reason"], "health_timeout")
        self.assertEqual(failure["switch"]["timeout_seconds"], 125)
        self.assertEqual(failure["switch"]["elapsed_seconds"], 125.1)
        self.assertEqual(failure["switch"]["log_id"], Path(self.candidate_process["log_file"]).name)
        self.assertEqual(failure["recovery_log_id"], Path(self.original_process["log_file"]).name)
        self.assertIsNone(failure["switch"]["exit_code"])
        self.assertEqual(self.read()["process"], self.original_process)
        self.assertNotIn("private", json.dumps(failure))
        self.assertNotIn(str(self.root), json.dumps(failure))

    def test_candidate_and_recovery_failures_keep_separate_reasons_and_logs(self):
        self.mocks[6].side_effect = [
            MANAGER.processes.ProcessError("candidate", reason="process_exited", exit_code=7, elapsed_seconds=1.2, timeout_seconds=125),
            MANAGER.processes.ProcessError("recovery", reason="health_timeout", elapsed_seconds=125, timeout_seconds=125)]
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed", health_timeout=125)
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["reason"], "process_exited")
        self.assertEqual(failure["switch"]["exit_code"], 7)
        self.assertEqual(failure["switch"]["log_id"], Path(self.candidate_process["log_file"]).name)
        self.assertEqual(failure["recovery"]["reason"], "health_timeout")
        self.assertEqual(failure["recovery"]["log_id"], Path(self.original_process["log_file"]).name)
        self.assertEqual(failure["recovery_status"], "failed")

    def test_early_exit_uses_launch_error_log_and_never_recovery_log(self):
        log_id = "server-" + "3" * 32 + ".log"
        self.mocks[5].side_effect = [MANAGER.processes.ProcessError(
            "private early exit", reason="process_exited", exit_code=7, log_id=log_id), self.original_process]
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed")
        failure = self.read()["last_failure"]
        self.assertEqual(failure["switch"]["stage"], "process_start")
        self.assertEqual(failure["switch"]["log_id"], log_id)
        self.assertEqual(failure["switch"]["exit_code"], 7)
        self.assertEqual(failure["recovery_log_id"], Path(self.original_process["log_file"]).name)

    def test_recovered_attempt_then_stop_diagnoses_exact_log_and_both_errors(self):
        logs = self.root / "logs"
        logs.mkdir()
        Path(self.original_process["log_file"]).write_text("Application startup complete\n", encoding="utf-8")
        Path(self.candidate_process["log_file"]).write_text(
            'Traceback (most recent call last):\n'
            '  File "C:/venv/Lib/site-packages/open_webui/main.py", line 9, in startup\n'
            'ValueError: synthetic-private-error\n'
            'Traceback (most recent call last):\n'
            '  File "<frozen importlib._bootstrap>", line 10, in _find_and_load\n'
            'KeyboardInterrupt\n', encoding="utf-8")
        self.mocks[6].side_effect = [MANAGER.processes.ProcessError(
            "private", reason="health_timeout", elapsed_seconds=125, timeout_seconds=125), None]
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.switch(self.config, self.candidate, "deployed", health_timeout=125)
        with patch.object(MANAGER.states, "load_config", return_value=self.config):
            MANAGER.operate(argparse.Namespace(action="stop", config="unused"))
            before = MANAGER.registry_path(self.config).read_bytes()
            result = MANAGER.operate(argparse.Namespace(action="diagnose", config="unused"))
        self.assertEqual(result["candidate"]["selection"], "recorded_log_id")
        self.assertFalse(result["candidate"]["signals"]["startup_complete"])
        text = MANAGER.render_diagnosis(result)
        self.assertIn("first_error_in_read_scope:", text)
        self.assertIn("open_webui/main.py:9:startup", text)
        self.assertIn("frozen/importlib._bootstrap:10:_find_and_load", text)
        self.assertIn('"reason": "health_timeout"', text)
        self.assertNotIn("synthetic-private-error", text)
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)

    def test_new_diagnostic_fields_filter_private_or_nonfinite_persisted_values(self):
        raw = {"evidence_version": True, "candidate": {"kind": "release", "source_commit": "private"},
               "switch": {"reason": ["private"], "log_id": "../private.log", "elapsed_seconds": float("inf"),
                          "timeout_seconds": True, "exit_code": "private"}, "recovery_log_id": "private"}
        safe = MANAGER.safe_last_failure(raw)
        self.assertNotIn("private", json.dumps(safe))
        self.assertIsNone(safe["evidence_version"])
        self.assertIsNone(safe["switch"]["elapsed_seconds"])
        self.assertIsNone(safe["switch"]["timeout_seconds"])
        self.assertIsNone(safe["candidate"]["source_commit"])

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
                         "operation": "port_bind", "errno": 10049, "winerror": 10049,
                         "reason": None, "elapsed_seconds": None, "timeout_seconds": None,
                         "exit_code": None, "log_id": None})
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
        for action in ("init", "status", "diagnose", "probe-imports", "plan", "prepare", "rollback", "stop", "apply", "restore"):
            with self.subTest(action=action), patch.object(MANAGER, "operate") as operate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MANAGER.main([action, "--config", "unused.json", "--use-windows-ca"])
            self.assertEqual(error.exception.code, 2)
            operate.assert_not_called()
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER, "switch", return_value={}) as switch, redirect_stdout(io.StringIO()):
            MANAGER.main(["deploy", "--config", "unused.json", "--commit", COMMIT, "--use-windows-ca"])
        self.assertTrue(switch.call_args.kwargs["use_windows_ca"])

    def test_start_windows_ca_rejects_legacy_registry_without_export_or_launch(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        args = argparse.Namespace(action="start", config="unused", use_windows_ca=True, health_timeout=120)
        with patch.object(MANAGER.states, "load_config", return_value=self.config), \
                patch.object(MANAGER.releases, "prepare_windows_ca") as export, \
                self.assertRaisesRegex(MANAGER.DeploymentError, "Apply/Restore"):
            MANAGER.operate(args)
        export.assert_not_called()
        self.mocks[5].assert_not_called()
        self.mocks[6].assert_not_called()
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)


class ImportProbeIntegrationTests(unittest.TestCase):
    """Use static prepared files; an import probe must not reach app operations."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "original-python"
        self.source.write_bytes(b"synthetic interpreter, never executed")
        self.config = {
            "schema_version": 1, "config_path": str(self.root / "config.json"),
            "state_root": str(self.root), "source_python": str(self.source),
            "releases_dir": str(self.root / "releases"),
        }
        MANAGER.write_json(Path(self.config["config_path"]), self.config)
        self.registry = {
            "schema_version": 1, "phase": "idle",
            "current": {"kind": "original", "python": str(self.source), "source_commit": None},
            "process": {"pid": 123, "executable": str(self.source)},
            "last_failure": {"failed_at": "2026-09-08T07:35:31Z", "recovery_status": "succeeded"},
        }
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        self.target = Path(self.config["releases_dir"]) / COMMIT
        self.candidate = self.target / "venv" / (
            "Scripts/python.exe" if MANAGER.os.name == "nt" else "bin/python")
        self.candidate.parent.mkdir(parents=True)
        self.candidate.write_bytes(b"synthetic candidate, never executed")
        self.metadata = {
            "schema_version": 1, "state": "prepared", "source_commit": COMMIT,
            "webui_version": MANAGER.releases.branding.VERSION,
            "source_python": str(self.source), "venv_dir": str(self.target / "venv"),
            "target_python": str(self.candidate), "python_executable": str(self.candidate),
        }
        self.write_metadata(self.metadata)
        self.probe = ModuleType("ees_deploy_imports")
        self.probe.compare = Mock(return_value={"status": "complete"})
        self.probe.render = Mock(return_value="EES import comparison")
        module_patch = patch.dict("sys.modules", {"ees_deploy_imports": self.probe})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.forbidden = []
        for module, name in (
                (MANAGER.states, "runtime_environment"), (MANAGER.states, "backup_state"),
                (MANAGER.releases, "validate_prepared"), (MANAGER.processes, "start_server"),
                (MANAGER.processes, "stop_server"), (MANAGER.processes, "wait_healthy"),
                (MANAGER, "record"), (MANAGER, "switch")):
            override = patch.object(module, name, side_effect=AssertionError("app operation in import probe"))
            self.forbidden.append(override.start())
            self.addCleanup(override.stop)

    def write_metadata(self, metadata, *, corrupt_digest=False):
        value = dict(metadata)
        value["metadata_sha256"] = (
            "0" * 64 if corrupt_digest else MANAGER.releases._metadata_digest(value))
        MANAGER.write_json(self.target / "release.json", value)

    def assert_unmodified(self, registry_before):
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), registry_before)
        self.assertFalse((self.root / "deployment.lock").exists())
        for operation in self.forbidden:
            operation.assert_not_called()

    def test_probe_passes_only_registered_interpreters_and_preserves_failure_record(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        prepared_before = (self.target / "release.json").read_bytes()

        def compare(original, candidate):
            self.assertTrue((self.root / "deployment.lock").exists())
            self.assertEqual((original, candidate), (str(self.source), str(self.candidate)))
            return {"status": "complete"}

        self.probe.compare.side_effect = compare
        result = MANAGER.probe_imports(self.config, COMMIT)
        self.probe.compare.assert_called_once_with(str(self.source), str(self.candidate))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertTrue(result["report_saved"])
        self.assertRegex(result["recorded_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(json.loads((self.root / "last-import-probe.json").read_bytes()), result)
        self.assertEqual((self.target / "release.json").read_bytes(), prepared_before)
        self.assert_unmodified(before)

    def test_metadata_mismatch_blocks_both_imports_even_with_recomputed_digest(self):
        cases = {
            "schema": {"schema_version": 2}, "boolean_schema": {"schema_version": True},
            "unprepared": {"state": "preparing"}, "commit": {"source_commit": "b" * 40},
            "version": {"webui_version": "unexpected"},
            "source": {"source_python": str(self.candidate)},
            "venv": {"venv_dir": str(self.root)},
            "target": {"target_python": str(self.source)},
            "executable": {"python_executable": str(self.source)},
        }
        before = MANAGER.registry_path(self.config).read_bytes()
        for name, changed in cases.items():
            with self.subTest(field=name):
                self.write_metadata(dict(self.metadata, **changed))
                with self.assertRaises(MANAGER.DeploymentError):
                    MANAGER.probe_imports(self.config, COMMIT)
                self.probe.compare.assert_not_called()
                self.assert_unmodified(before)

    def test_changed_digest_or_missing_candidate_blocks_imports(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        self.write_metadata(self.metadata, corrupt_digest=True)
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.probe_imports(self.config, COMMIT)
        self.write_metadata(self.metadata)
        self.candidate.unlink()
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.probe_imports(self.config, COMMIT)
        self.probe.compare.assert_not_called()
        self.assert_unmodified(before)

    def test_incomplete_switch_or_active_candidate_blocks_imports(self):
        cases = (
            {"phase": "switching"}, {"phase": "recovery_required"},
            {"pending": {"kind": "release", "source_commit": COMMIT}},
            {"launch_uncertain": True},
            {"current": {"kind": "release", "source_commit": COMMIT, "python": str(self.candidate)}},
        )
        for changed in cases:
            with self.subTest(state=changed):
                MANAGER.write_json(MANAGER.registry_path(self.config), dict(self.registry, **changed))
                before = MANAGER.registry_path(self.config).read_bytes()
                with self.assertRaises(MANAGER.DeploymentError):
                    MANAGER.probe_imports(self.config, COMMIT)
                self.probe.compare.assert_not_called()
                self.assert_unmodified(before)

    def test_existing_operator_lock_is_preserved_and_blocks_imports(self):
        lock = self.root / "deployment.lock"
        lock.write_bytes(b"another operation")
        before = MANAGER.registry_path(self.config).read_bytes()
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.probe_imports(self.config, COMMIT)
        self.probe.compare.assert_not_called()
        self.assertEqual(lock.read_bytes(), b"another operation")
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)

    def test_probe_failure_releases_lock_without_recording_a_deployment_failure(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        self.probe.compare.side_effect = OSError("synthetic probe failure")
        with self.assertRaises(OSError):
            MANAGER.probe_imports(self.config, COMMIT)
        self.assert_unmodified(before)

    def test_report_save_failure_returns_current_result_and_preserves_old_file(self):
        report = self.root / "last-import-probe.json"
        report.write_bytes(b"old report")
        before = MANAGER.registry_path(self.config).read_bytes()
        with patch.object(MANAGER, "write_json", side_effect=OSError("private path")):
            result = MANAGER.probe_imports(self.config, COMMIT)
        self.assertFalse(result["report_saved"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(report.read_bytes(), b"old report")
        self.assertNotIn("private path", json.dumps(result))
        self.assert_unmodified(before)

    def test_report_save_does_not_replace_a_hardlinked_file(self):
        external = self.root / "unrelated.json"
        external.write_bytes(b"preserve")
        MANAGER.os.link(external, self.root / "last-import-probe.json")
        before = MANAGER.registry_path(self.config).read_bytes()
        result = MANAGER.probe_imports(self.config, COMMIT)
        self.assertFalse(result["report_saved"])
        self.assertEqual(external.read_bytes(), b"preserve")
        self.assert_unmodified(before)

    def test_cli_requires_commit_before_any_operation(self):
        with patch.object(MANAGER, "operate") as operate, redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as error:
            MANAGER.main(["probe-imports", "--config", self.config["config_path"]])
        self.assertEqual(error.exception.code, 2)
        operate.assert_not_called()
        self.probe.compare.assert_not_called()

    def test_cli_routes_probe_result_to_short_renderer(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        output = io.StringIO()
        with patch.object(MANAGER.states, "load_config", return_value=self.config), redirect_stdout(output):
            result = MANAGER.main([
                "probe-imports", "--config", self.config["config_path"], "--commit", COMMIT])
        self.assertEqual(result, 0)
        self.probe.compare.assert_called_once_with(str(self.source), str(self.candidate))
        self.probe.render.assert_called_once_with(
            json.loads((self.root / "last-import-probe.json").read_bytes()))
        self.assertEqual(output.getvalue().strip(), "EES import comparison")
        self.assert_unmodified(before)


class CustomizationIntegrationTests(unittest.TestCase):
    """Exercise operator boundaries without touching a real installation."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = {"state_root": str(self.root), "source_python": "original-python",
                       "cwd": "original-cwd", "data_dir": "original-data", "host": "127.0.0.1", "port": 8080}
        self.selection = {"source_commit": COMMIT, "wheel_sha256": "b" * 64,
                          "record_sha256": "c" * 64, "webui_version": MANAGER.releases.branding.VERSION}
        self.registry = {"schema_version": 2, "phase": "idle", "process": None,
            "current": {"kind": "original", "source_commit": None, "python": "original-python"},
            "previous": {"kind": "historical-release"}, "last_failure": {"action": "deploy"},
            "customization": {"active": self.selection, "previous": {"active": None}, "pending": None}}
        self.write()
        self.env = {"DATA_DIR": "original-data", "WEBUI_SECRET_KEY": "synthetic-key"}
        self.owner = dict(OPERATOR)
        self.mocks = {}
        for module, name, kw in (
            (MANAGER.states, "load_config", {"return_value": self.config}),
            (MANAGER.states, "runtime_environment", {"return_value": self.env}),
            (MANAGER.processes, "_identity", {"side_effect": lambda pid: self.owner if pid == MANAGER.os.getpid() else None}),
            (MANAGER.processes, "port_is_free", {"return_value": True}),
            (MANAGER.processes, "verify_identity", {"return_value": False}),
            (MANAGER.processes, "wait_healthy", {}),
            (MANAGER.processes, "start_server", {"return_value": {"pid": 123}}),
            (MANAGER.processes, "check_accept_runtime", {"return_value": "compatible"}),
            (MANAGER.processes, "accept_guard_status", {"return_value": "win64_retry"}),
            (MANAGER.processes, "stop_server", {}),
            (MANAGER.customization, "validate_program", {"return_value": self.root / "program"}),
            (MANAGER.customization, "inspect_bundle", {"return_value": self.selection}),
            (MANAGER.customization, "check_applicability", {}),
        ):
            override = patch.object(module, name, **kw)
            self.mocks[name] = override.start()
            self.addCleanup(override.stop)

    def write(self):
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)

    def args(self, action, **kw):
        return argparse.Namespace(action=action, config="unused", bundle="unused.zip", commit=COMMIT,
                                  check_only=kw.get("check_only", False), resume=kw.get("resume", False),
                                  use_windows_ca=kw.get("use_windows_ca", False), health_timeout=120)

    def pending(self):
        self.registry["customization"]["pending"] = {
            "action": "apply", "owner": dict(OPERATOR), "before": None, "target": self.selection,
            "old_previous": None, "stage": "promote"}
        self.write()

    def manual_promotion(self):
        self.registry["customization"] = {"active": None, "previous": None, "pending": None}
        self.pending()
        program = self.root / "program"
        program.mkdir()
        (program / "synthetic-payload").write_bytes(b"already manually renamed")
        return program, self.root / "program.previous", self.root / "program.staging"

    def test_resume_cli_is_explicit_apply_only_and_still_requires_bundle_and_commit(self):
        actions = ("init", "status", "diagnose", "probe-imports", "plan", "prepare", "deploy",
                   "rollback", "start", "stop", "restore")
        for action in actions:
            with self.subTest(action=action), patch.object(MANAGER, "operate") as operate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MANAGER.main([action, "--config", "unused", "--resume"])
            self.assertEqual(error.exception.code, 2)
            operate.assert_not_called()
        for supplied in ([], ["--bundle", "unused.zip"], ["--commit", COMMIT]):
            with self.subTest(supplied=supplied), patch.object(MANAGER, "operate") as operate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MANAGER.main(["apply", "--config", "unused", "--resume"] + supplied)
            self.assertEqual(error.exception.code, 2)
            operate.assert_not_called()
        for flags in ([], ["--resume"], ["--resume", "--check-only"]):
            with self.subTest(flags=flags), patch.object(MANAGER, "operate", return_value={}) as operate, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(MANAGER.main(["apply", "--config", "unused", "--bundle", "unused.zip",
                                               "--commit", COMMIT] + flags), 0)
            args = operate.call_args.args[0]
            self.assertEqual(args.resume, "--resume" in flags)
            self.assertEqual(args.check_only, "--check-only" in flags)

    def test_resume_finishes_record_without_repeating_apply_rename_or_server_actions(self):
        paths = self.manual_promotion()
        before = (paths[0] / "synthetic-payload").read_bytes()
        with patch.object(MANAGER.customization, "_paths", return_value=paths), \
                patch.object(MANAGER.customization, "_load_bundle", return_value=(self.selection, b"unused")) as load, \
                patch.object(MANAGER.customization, "apply") as apply, \
                patch.object(MANAGER.customization, "restore") as restore, \
                patch.object(Path, "rename") as rename:
            result = MANAGER.operate(self.args("apply", resume=True))
        self.assertTrue(result["changed"])
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertFalse(result["data_changed"])
        self.assertFalse(result["original_program"])
        load.assert_called_once_with(self.config, "unused.zip", COMMIT, self.env)
        apply.assert_not_called()
        restore.assert_not_called()
        rename.assert_not_called()
        self.mocks["check_applicability"].assert_not_called()
        for name in ("start_server", "stop_server", "wait_healthy"):
            self.mocks[name].assert_not_called()
        after = MANAGER.read_registry(self.config)
        self.assertEqual(after["customization"], {"active": self.selection, "previous": {"active": None}, "pending": None})
        for key in ("current", "previous", "last_failure"):
            self.assertEqual(after[key], self.registry[key])
        self.assertEqual(after["last_event"], "program_applied")
        self.assertEqual((paths[0] / "synthetic-payload").read_bytes(), before)
        self.assertFalse((self.root / "deployment.lock").exists())
        self.mocks["port_is_free"].assert_called_once_with("127.0.0.1", 8080, raise_on_error=True)

    def test_resume_check_only_is_read_only_even_with_summary_and_registered_server(self):
        paths = self.manual_promotion()
        self.registry["process"] = {"pid": 123}
        self.write()
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with patch.object(MANAGER.customization, "_paths", return_value=paths), \
                patch.object(MANAGER, "locked") as lock, \
                patch.object(MANAGER.customization, "resume_apply") as resume, \
                patch.object(MANAGER.customization, "apply") as apply, \
                patch.object(MANAGER.customization, "restore") as restore, \
                patch.object(Path, "rename") as rename, redirect_stdout(output):
            result = MANAGER.main(["apply", "--config", "unused", "--bundle", "unused.zip", "--commit", COMMIT,
                                   "--resume", "--check-only", "--summary"])
        self.assertEqual(result, 0)
        self.assertIn("result=ok", output.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        for mocked in (lock, resume, apply, restore, rename):
            mocked.assert_not_called()
        for name in ("start_server", "stop_server", "wait_healthy", "port_is_free", "check_applicability"):
            self.mocks[name].assert_not_called()
        self.mocks["inspect_bundle"].assert_called_once_with(self.config, Path("unused.zip"), COMMIT, self.env)
        self.mocks["validate_program"].assert_called_once_with(paths[0], self.selection)

    def test_resume_check_only_rejects_concurrent_registry_or_lock_change(self):
        paths = self.manual_promotion()
        lock = self.root / "deployment.lock"
        for kind in ("registry", "lock"):
            with self.subTest(kind=kind):
                def changed(*_):
                    if kind == "registry":
                        self.registry["last_event"] = "concurrent-operation"
                        self.write()
                    else:
                        lock.write_text(json.dumps(OPERATOR))
                    return self.selection
                self.mocks["inspect_bundle"].side_effect = changed
                with patch.object(MANAGER.customization, "_paths", return_value=paths), \
                        self.assertRaisesRegex(MANAGER.DeploymentError, "changed during CheckOnly"):
                    MANAGER.operate(self.args("apply", resume=True, check_only=True))
        self.assertEqual(lock.read_text(), json.dumps(OPERATOR))

    def test_resume_rejects_no_pending_and_default_apply_does_not_implicitly_resume(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        with self.assertRaisesRegex(MANAGER.customization.CustomizationError, "incomplete Apply"):
            MANAGER.operate(self.args("apply", resume=True, check_only=True))
        with patch.object(MANAGER.customization, "_load_bundle", return_value=(self.selection, b"unused")), \
                self.assertRaisesRegex(MANAGER.customization.CustomizationError, "incomplete Apply"):
            MANAGER.operate(self.args("apply", resume=True))
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
        self.pending()
        with patch.object(MANAGER.customization, "resume_apply") as resume, \
                self.assertRaisesRegex(MANAGER.DeploymentError, "incomplete"):
            MANAGER.operate(self.args("apply"))
        resume.assert_not_called()

    def test_resume_blocks_running_unknown_launch_or_occupied_port_without_auto_actions(self):
        self.pending()
        for kind in ("running", "uninspectable", "uncertain", "port", "port-error"):
            with self.subTest(kind=kind):
                self.registry["process"] = {"pid": 123}
                self.registry["launch_uncertain"] = kind == "uncertain"
                self.write()
                before = MANAGER.registry_path(self.config).read_bytes()
                def identify(pid):
                    if pid == MANAGER.os.getpid():
                        return self.owner
                    if kind == "uninspectable":
                        raise MANAGER.processes.ProcessError("unavailable")
                    return OPERATOR if kind == "running" else None
                self.mocks["_identity"].side_effect = identify
                self.mocks["port_is_free"].return_value = kind != "port"
                self.mocks["port_is_free"].side_effect = MANAGER.processes.ProcessError("port unavailable") if kind == "port-error" else None
                with patch.object(MANAGER.customization, "resume_apply") as resume, \
                        self.assertRaises((MANAGER.DeploymentError, MANAGER.processes.ProcessError)):
                    MANAGER.operate(self.args("apply", resume=True))
                resume.assert_not_called()
                self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
                self.assertFalse((self.root / "deployment.lock").exists())
        for name in ("start_server", "stop_server", "wait_healthy"):
            self.mocks[name].assert_not_called()

    def test_resume_never_reclaims_even_exact_dead_owner_lock(self):
        self.pending()
        lock = self.root / "deployment.lock"
        lock.write_text(json.dumps(OPERATOR))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for check_only in (False, True):
            with self.subTest(check_only=check_only), \
                    patch.object(MANAGER.customization, "resume_apply") as resume, \
                    self.assertRaisesRegex(MANAGER.DeploymentError, "lock"):
                MANAGER.operate(self.args("apply", resume=True, check_only=check_only))
            resume.assert_not_called()
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_resume_requires_exact_original_selection_before_recording(self):
        self.pending()
        self.registry["current"]["source_commit"] = COMMIT
        self.write()
        before = MANAGER.registry_path(self.config).read_bytes()
        for check_only in (False, True):
            with self.subTest(check_only=check_only), \
                    patch.object(MANAGER.customization, "resume_apply") as resume, \
                    self.assertRaisesRegex(MANAGER.DeploymentError, "baseline"):
                MANAGER.operate(self.args("apply", resume=True, check_only=check_only))
            resume.assert_not_called()
            self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)

    def test_legacy_schema_with_customization_cannot_bypass_guards(self):
        self.registry["schema_version"] = 1
        self.write()
        with self.assertRaises(MANAGER.DeploymentError):
            MANAGER.operate(self.args("start"))
        self.mocks["start_server"].assert_not_called()

    def test_status_summary_exposes_incomplete_program(self):
        self.pending()
        result = MANAGER.operate(self.args("status"))
        self.assertIn("program=incomplete", MANAGER.render_summary("status", result))

    def test_check_only_does_not_write_lock_report_stop_or_import_app(self):
        self.registry["process"] = {"pid": 123}
        self.write()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = MANAGER.operate(self.args("apply", check_only=True))
        self.assertTrue(result["checked"])
        self.assertTrue(result["already_applied"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        for name in ("start_server", "stop_server", "wait_healthy"):
            self.mocks[name].assert_not_called()

    def test_check_only_rejects_state_change_during_inspection(self):
        def changed(*_):
            self.registry["last_event"] = "concurrent-operation"
            self.write()
            return self.selection
        self.mocks["inspect_bundle"].side_effect = changed
        with self.assertRaisesRegex(MANAGER.DeploymentError, "changed during CheckOnly"):
            MANAGER.operate(self.args("apply", check_only=True))

    def test_start_check_only_preserves_live_server_state_and_has_no_health_wait(self):
        self.registry["process"] = {"pid": 123}
        self.write()
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.mocks["port_is_free"].side_effect = AssertionError("must not bind a live port")
        with patch.object(MANAGER, "locked", side_effect=AssertionError("must not lock")):
            result = MANAGER.operate(self.args("start", check_only=True))
        self.assertEqual(result["accept_guard"], "compatible")
        self.assertFalse(result["changed"])
        for name in ("start_server", "stop_server", "wait_healthy", "accept_guard_status"):
            self.mocks[name].assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()})
        self.assertIn("guard=compatible", MANAGER.render_summary("start", result))

    def test_start_check_only_runtime_failure_or_state_race_never_stops_server(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        self.mocks["check_accept_runtime"].side_effect = MANAGER.processes.ProcessError(
            "synthetic", reason="accept_guard_incompatible")
        with self.assertRaises(MANAGER.processes.ProcessError) as caught:
            MANAGER.operate(self.args("start", check_only=True))
        self.assertEqual(caught.exception.stage, "preflight")
        self.assertEqual(before, MANAGER.registry_path(self.config).read_bytes())
        def race(*args):
            (self.root / "deployment.lock").write_text("synthetic concurrent operation")
            return "compatible"
        self.mocks["check_accept_runtime"].side_effect = race
        with self.assertRaisesRegex(MANAGER.DeploymentError, "changed during preflight"):
            MANAGER.operate(self.args("start", check_only=True))
        self.mocks["stop_server"].assert_not_called()
        self.mocks["start_server"].assert_not_called()

    def test_guard_marker_failure_after_health_is_not_start_success(self):
        self.mocks["accept_guard_status"].side_effect = MANAGER.processes.ProcessError("missing guard")
        with self.assertRaises(MANAGER.processes.ProcessError):
            MANAGER.operate(self.args("start"))
        self.mocks["wait_healthy"].assert_called_once()
        self.mocks["stop_server"].assert_not_called()
        self.assertEqual(MANAGER.read_registry(self.config)["process"], {"pid": 123})

    def test_apply_refuses_running_unidentified_or_occupied_server(self):
        self.registry["process"] = {"pid": 123}
        self.write()
        with patch.object(MANAGER.customization, "apply") as apply:
            self.mocks["_identity"].side_effect = lambda pid: self.owner
            with self.assertRaisesRegex(MANAGER.DeploymentError, "Stop"):
                MANAGER.operate(self.args("apply"))
            self.mocks["_identity"].side_effect = lambda pid: self.owner if pid == MANAGER.os.getpid() else None
            self.mocks["port_is_free"].return_value = False
            with self.assertRaisesRegex(MANAGER.DeploymentError, "port"):
                MANAGER.operate(self.args("apply"))
            apply.assert_not_called()
        self.mocks["stop_server"].assert_not_called()

    def test_missing_program_blocks_already_running_before_health_wait(self):
        self.registry["process"] = {"pid": 123}
        self.write()
        self.mocks["verify_identity"].return_value = True
        self.mocks["validate_program"].side_effect = MANAGER.customization.CustomizationError("missing metadata")
        with self.assertRaisesRegex(ValueError, "missing metadata"):
            MANAGER.operate(self.args("start"))
        self.mocks["wait_healthy"].assert_not_called()
        self.mocks["start_server"].assert_not_called()

    def test_pending_blocks_start_and_survives_stop_with_history(self):
        self.pending()
        before = MANAGER.read_registry(self.config)
        with self.assertRaisesRegex(MANAGER.DeploymentError, "incomplete"):
            MANAGER.operate(self.args("start"))
        MANAGER.operate(self.args("stop"))
        after = MANAGER.read_registry(self.config)
        for key in ("customization", "previous", "last_failure"):
            self.assertEqual(after[key], before[key])
        with self.assertRaisesRegex(MANAGER.DeploymentError, "incomplete"):
            MANAGER.operate(self.args("start"))

    def test_wrapper_start_passes_registered_environment_and_selected_path(self):
        result = MANAGER.operate(self.args("start"))
        self.assertTrue(result["started"])
        call = self.mocks["start_server"].call_args
        self.assertEqual(call.args[:3], ("original-python", "original-cwd", self.env))
        self.assertEqual(call.kwargs, {"program_path": str(self.root / "program"),
                                       "program_version": self.selection["webui_version"]})
        self.mocks["wait_healthy"].assert_called_once_with({"pid": 123}, timeout=120)

    def test_start_windows_ca_persists_for_original_and_customized_child_only(self):
        digest = "d" * 64
        bundle = self.root / "trusted-ca" / (digest + ".pem")
        self.env.update(REQUESTS_CA_BUNDLE="registered-requests", SSL_CERT_FILE="registered-ssl")
        registered = dict(self.env)
        config_before = dict(self.config)
        for active in (None, self.selection):
            with self.subTest(customized=bool(active)):
                self.registry["customization"]["active"] = active
                self.write()
                self.mocks["start_server"].reset_mock()
                with patch.object(MANAGER.releases, "prepare_windows_ca", return_value=digest) as export, \
                        patch.object(MANAGER.releases, "windows_ca_path", return_value=bundle), \
                        patch.dict(MANAGER.os.environ, {"SSL_CERT_FILE": "parent-ssl", "REQUESTS_CA_BUNDLE": "parent-requests"}):
                    result = MANAGER.operate(self.args("start", use_windows_ca=True))
                    self.assertTrue(result["started"])
                    export.assert_called_once_with(self.root, "original-python", registered, cwd="original-cwd")
                    self.assertEqual(MANAGER.read_registry(self.config)["runtime_ca_sha256"], digest)
                    self.assertEqual(MANAGER.operate(self.args("status"))["ca_mode"], "windows_snapshot")
                    MANAGER.operate(self.args("stop"))
                    self.assertEqual(MANAGER.read_registry(self.config)["runtime_ca_sha256"], digest)
                    self.assertTrue(MANAGER.operate(self.args("start"))["started"])
                    export.assert_called_once()
                    self.assertEqual(MANAGER.os.environ["SSL_CERT_FILE"], "parent-ssl")
                    self.assertEqual(MANAGER.os.environ["REQUESTS_CA_BUNDLE"], "parent-requests")
                self.assertEqual(self.env, registered)
                self.assertEqual(self.config, config_before)
                self.assertEqual(self.mocks["start_server"].call_count, 2)
                for call in self.mocks["start_server"].call_args_list:
                    self.assertEqual(call.args[:2], ("original-python", "original-cwd"))
                    self.assertEqual(call.args[2], dict(registered, REQUESTS_CA_BUNDLE=str(bundle), SSL_CERT_FILE=str(bundle)))
                    self.assertIsNot(call.args[2], self.env)
                    self.assertEqual(call.kwargs, {"program_path": str(self.root / "program"),
                                                   "program_version": active["webui_version"]} if active else {})

    def test_start_windows_ca_selection_survives_health_timeout(self):
        digest = "d" * 64
        self.mocks["wait_healthy"].side_effect = MANAGER.processes.ProcessError("synthetic timeout", reason="health_timeout")
        with patch.object(MANAGER.releases, "prepare_windows_ca", return_value=digest), \
                patch.object(MANAGER.releases, "windows_ca_path", return_value=self.root / "synthetic-ca.pem"), \
                self.assertRaises(MANAGER.processes.ProcessError) as error:
            MANAGER.operate(self.args("start", use_windows_ca=True))
        self.assertEqual(error.exception.stage, "health_check")
        saved = MANAGER.read_registry(self.config)
        self.assertEqual(saved["runtime_ca_sha256"], digest)
        self.assertEqual(saved["process"], {"pid": 123})
        self.assertNotEqual(saved["last_event"], "started_by_operator")
        self.mocks["stop_server"].assert_not_called()

    def test_start_windows_ca_refuses_live_process_without_export_or_mutation(self):
        self.registry["process"] = {"pid": 123}
        self.write()
        before = MANAGER.registry_path(self.config).read_bytes()
        self.mocks["verify_identity"].return_value = True
        with patch.object(MANAGER.releases, "prepare_windows_ca") as export, \
                self.assertRaisesRegex(MANAGER.DeploymentError, "Stop"):
            MANAGER.operate(self.args("start", use_windows_ca=True))
        export.assert_not_called()
        for name in ("start_server", "stop_server", "wait_healthy"):
            self.mocks[name].assert_not_called()
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)

    def test_invalid_runtime_ca_blocks_start_but_does_not_block_stop(self):
        directory = self.root / "trusted-ca"
        directory.mkdir()
        payload = b"synthetic invalid certificate"
        invalid_digest = hashlib.sha256(payload).hexdigest()
        (directory / (invalid_digest + ".pem")).write_bytes(payload)
        tampered_digest = "d" * 64
        (directory / (tampered_digest + ".pem")).write_bytes(b"changed snapshot")
        for digest in (None, "not-a-digest", "e" * 64, tampered_digest, invalid_digest):
            with self.subTest(digest=digest):
                self.registry["runtime_ca_sha256"] = digest
                self.write()
                before = MANAGER.registry_path(self.config).read_bytes()
                with patch.object(MANAGER.releases, "prepare_windows_ca") as export, \
                        self.assertRaises(MANAGER.releases.ReleaseError):
                    MANAGER.operate(self.args("start"))
                export.assert_not_called()
                self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
                status = MANAGER.operate(self.args("status"))
                self.assertFalse(status["program_valid"])
                self.assertEqual(status["ca_mode"], "windows_snapshot")
                self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
                self.assertTrue(MANAGER.operate(self.args("stop"))["stopped"])
                self.assertEqual(MANAGER.read_registry(self.config)["runtime_ca_sha256"], digest)
        self.mocks["start_server"].assert_not_called()
        self.mocks["wait_healthy"].assert_not_called()

    def test_start_windows_ca_export_failure_or_busy_port_does_not_launch(self):
        before = MANAGER.registry_path(self.config).read_bytes()
        for busy in (False, True):
            with self.subTest(busy=busy):
                self.mocks["port_is_free"].return_value = not busy
                with patch.object(MANAGER.releases, "prepare_windows_ca", side_effect=MANAGER.releases.ReleaseError("synthetic export failure")) as export, \
                        self.assertRaises((MANAGER.releases.ReleaseError, MANAGER.DeploymentError)):
                    MANAGER.operate(self.args("start", use_windows_ca=True))
                self.assertEqual(export.call_count, int(not busy))
                self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
        for name in ("start_server", "stop_server", "wait_healthy"):
            self.mocks[name].assert_not_called()

    def test_start_windows_ca_cli_forwards_explicit_selection(self):
        with patch.object(MANAGER, "operate", return_value={}) as operate, redirect_stdout(io.StringIO()):
            self.assertEqual(MANAGER.main(["start", "--config", "unused", "--use-windows-ca"]), 0)
        self.assertTrue(operate.call_args.args[0].use_windows_ca)

    def test_health_failure_does_not_switch_or_start_original_automatically(self):
        self.mocks["wait_healthy"].side_effect = MANAGER.processes.ProcessError("synthetic health failure")
        with self.assertRaises(MANAGER.processes.ProcessError):
            MANAGER.operate(self.args("start"))
        self.mocks["start_server"].assert_called_once()
        self.mocks["stop_server"].assert_not_called()
        self.assertEqual(MANAGER.read_registry(self.config)["customization"]["active"], self.selection)

    def test_legacy_actions_refused_before_candidate_inventory_or_server_calls(self):
        for action in ("plan", "prepare", "deploy", "rollback", "probe-imports", "diagnose"):
            with self.subTest(action=action), self.assertRaisesRegex(MANAGER.DeploymentError, "Apply/Restore"):
                MANAGER.operate(self.args(action))
        self.mocks["inspect_bundle"].assert_not_called()
        self.mocks["start_server"].assert_not_called()

    def test_status_distinguishes_existing_python_from_customized_app(self):
        result = MANAGER.operate(self.args("status"))
        self.assertFalse(result["original_program"])
        self.assertEqual(result["current_commit"], COMMIT)
        self.assertTrue(result["program_valid"])
        self.assertTrue(result["restore_available"])
        self.assertFalse(result["rollback_available"])
        self.pending()
        result = MANAGER.operate(self.args("status"))
        self.assertFalse(result["program_valid"])
        self.assertTrue(result["program_incomplete"])
        self.assertFalse(result["original_program"])

    def test_restore_reclaims_only_exact_recorded_dead_owner(self):
        self.pending()
        lock = self.root / "deployment.lock"
        lock.write_text(json.dumps(OPERATOR))
        with patch.object(MANAGER.customization, "restore", return_value={"changed": True}) as restore:
            self.assertTrue(MANAGER.operate(self.args("restore"))["changed"])
        restore.assert_called_once()
        self.assertFalse(lock.exists())
        self.mocks["start_server"].assert_not_called()

    def test_restore_preserves_old_mismatched_live_or_uninspectable_lock(self):
        self.pending()
        lock = self.root / "deployment.lock"
        cases = [("4242", None), (json.dumps(dict(OPERATOR, created_at="other")), None),
                 (json.dumps(OPERATOR), OPERATOR),
                 (json.dumps(OPERATOR), MANAGER.processes.ProcessError("unavailable"))]
        for content, state in cases:
            with self.subTest(content=content, state=state):
                lock.write_text(content)
                def identify(pid):
                    if pid == MANAGER.os.getpid():
                        return self.owner
                    if isinstance(state, Exception):
                        raise state
                    return state
                self.mocks["_identity"].side_effect = identify
                with self.assertRaises((MANAGER.DeploymentError, MANAGER.processes.ProcessError)):
                    MANAGER.operate(self.args("restore"))
                self.assertEqual(lock.read_text(), content)

    def test_summary_is_one_line_and_check_only_leaves_no_report(self):
        output = io.StringIO()
        before = MANAGER.registry_path(self.config).read_bytes()
        with redirect_stdout(output):
            result = MANAGER.main(["apply", "--config", "unused", "--bundle", "unused.zip",
                                   "--commit", COMMIT, "--check-only", "--summary"])
        self.assertEqual(result, 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn("result=ok", output.getvalue())
        self.assertNotIn("synthetic-key", output.getvalue())
        self.assertEqual(MANAGER.registry_path(self.config).read_bytes(), before)
        self.assertFalse((self.root / "last-operation.json").exists())

    def test_summary_failure_is_short_and_saved_locally_without_raw_paths(self):
        self.mocks["validate_program"].side_effect = OSError(13, "synthetic-private-path")
        output = io.StringIO()
        with redirect_stdout(output):
            result = MANAGER.main(["start", "--config", "unused", "--summary"])
        self.assertEqual(result, 1)
        self.assertIn("result=failed", output.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertNotIn("synthetic-private", output.getvalue())
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        self.assertTrue(saved["failed"])
        self.assertNotIn("synthetic-private", json.dumps(saved))

    def test_apply_promotion_retry_exhaustion_preserves_codes_location_and_pending(self):
        self.registry["customization"] = {"active": None, "previous": None, "pending": None}
        self.write()
        self.mocks["check_applicability"].return_value = self.registry["customization"]
        program, previous, staged = (self.root / name for name in ("program", "program.previous", "program.staging"))
        private = "synthetic-private-PAT-and-path"
        error = PermissionError(13, private, private)
        error.winerror = 5
        error.stage = private
        output = io.StringIO()
        with patch.object(MANAGER.customization, "_paths", return_value=(program, previous, staged)), \
                patch.object(MANAGER.customization, "_load_bundle", return_value=(self.selection, b"unused")), \
                patch.object(MANAGER.customization, "_extract", side_effect=lambda _, path: path.mkdir()), \
                patch.object(MANAGER.customization.sys, "platform", "win32"), \
                patch.object(MANAGER.customization.time, "sleep") as sleep, \
                patch.object(Path, "rename", side_effect=error) as rename, \
                patch.object(MANAGER.customization, "restore") as restore, redirect_stdout(output):
            result = MANAGER.main(["apply", "--config", "unused", "--bundle", "unused.zip",
                                   "--commit", COMMIT, "--summary"])
        self.assertEqual(result, 1)
        self.assertEqual(rename.call_count, 5)
        self.assertTrue(all(call.args == (program,) for call in rename.call_args_list))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4, 8])
        restore.assert_not_called()
        self.mocks["start_server"].assert_not_called()
        self.assertTrue(staged.is_dir())
        self.assertFalse(program.exists())
        self.assertFalse((self.root / "deployment.lock").exists())
        self.assertEqual(MANAGER.read_registry(self.config)["customization"]["pending"]["stage"], "promote")
        saved = json.loads((self.root / "last-operation.json").read_bytes())
        detail = saved["result"]["local_error"]
        self.assertEqual((detail["type"], detail["errno"], detail["winerror"]), ("PermissionError", 13, 5))
        self.assertEqual(detail["source"], "ees_webui_customization.py")
        source = (ROOT / "scripts" / detail["source"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(source[detail["line"] - 1].strip(), "source.rename(destination)")
        self.assertEqual(saved["result"]["program_rename"],
                         {"stage": "promote", "attempts": 5, "waited_seconds": 15})
        self.assertIn("error=PermissionError errno=13 winerror=5 at=ees_webui_customization.py:", output.getvalue())
        self.assertIn("rename=promote attempts=5 waited=15", output.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertNotIn(private, output.getvalue() + json.dumps(saved))

    def test_direct_rename_error_keeps_safe_metadata_and_filters_malformed_metadata(self):
        private = "synthetic-private-PAT-and-path"
        for stage in ("move_active", "promote", "restore", private):
            with self.subTest(stage=stage):
                error = PermissionError(13, private, private)
                error.winerror = 32
                error.program_rename_failed = True
                error.program_rename_stage = stage
                error.program_rename_attempts = 5
                error.program_rename_wait_seconds = 15
                output = io.StringIO()
                with patch.object(MANAGER, "operate", side_effect=error), redirect_stdout(output):
                    self.assertEqual(MANAGER.main(["restore", "--config", "unused", "--summary"]), 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                if stage == private:
                    self.assertNotIn("program_rename", saved["result"])
                    self.assertNotIn(" rename=", output.getvalue())
                else:
                    self.assertEqual(saved["result"]["program_rename"],
                                     {"stage": stage, "attempts": 5, "waited_seconds": 15})
                    self.assertIn("rename=" + stage + " attempts=5 waited=15", output.getvalue())
                self.assertNotIn(private, output.getvalue() + json.dumps(saved))

    def test_local_error_filters_private_frames_classes_and_malformed_fields(self):
        private = "synthetic-private-PAT-and-path"
        for error in (ValueError(private), KeyError(private), type(private, (OSError,), {})(private)):
            error.errno, error.winerror = private, 2 ** 64
            namespace = {"error": error}
            # A matching basename outside the checkout must not be reported.
            code = compile("raise error", str(self.root / private / "manage_ees.py"), "exec")
            try:
                exec(code, namespace)
            except (OSError, ValueError, KeyError) as caught:
                detail = MANAGER.local_error_detail(caught)
            self.assertIsNone(detail["source"])
            self.assertIsNone(detail["line"])
            self.assertIsNone(detail["errno"])
            self.assertIsNone(detail["winerror"])
            self.assertNotIn(private, json.dumps(detail))
        result = {"local_error": {"type": [private], "source": private, "line": private,
                                  "errno": True, "winerror": private}}
        text = MANAGER.render_summary("apply", result, failed=True)
        self.assertIn("error=unknown errno=- winerror=- at=-", text)
        self.assertNotIn(private, text)

    def test_summary_retains_original_error_when_report_write_also_fails(self):
        error = PermissionError(13, "synthetic-private-PAT-and-path")
        error.winerror = 32
        output = io.StringIO()
        with patch.object(MANAGER, "operate", side_effect=error), \
                patch.object(MANAGER, "write_json", side_effect=OSError(28, "private report path")), \
                redirect_stdout(output):
            result = MANAGER.main(["restore", "--config", "unused", "--summary"])
        self.assertEqual(result, 1)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn("error=PermissionError errno=13 winerror=32", output.getvalue())
        self.assertIn("report=unavailable", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_failed_check_only_reports_error_codes_without_writing_state(self):
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.mocks["inspect_bundle"].side_effect = FileNotFoundError(2, "synthetic-private-path")
        output = io.StringIO()
        with redirect_stdout(output):
            result = MANAGER.main(["apply", "--config", "unused", "--bundle", "unused.zip",
                                   "--commit", COMMIT, "--check-only", "--summary"])
        self.assertEqual(result, 1)
        self.assertIn("error=FileNotFoundError errno=2", output.getvalue())
        self.assertNotIn("synthetic-private", output.getvalue())
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_direct_stop_failure_is_saved_with_log_id_in_summary_and_plain_modes(self):
        private = "synthetic-private-stop-exception"
        log_id = "server-" + "d" * 32 + ".log"
        self.registry["process"] = {"pid": 123, "log_file": str(self.root / log_id)}
        self.write()
        for summary in (False, True):
            with self.subTest(summary=summary):
                error = MANAGER.processes.ProcessError(private, operation="process_wait", reason="stop_timeout",
                    elapsed_seconds=30.25, timeout_seconds=30)
                self.mocks["stop_server"].side_effect = error
                output, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(stderr):
                    argv = ["stop", "--config", "unused"] + (["--summary"] if summary else [])
                    if summary:
                        self.assertEqual(MANAGER.main(argv), 1)
                    else:
                        with self.assertRaises(SystemExit) as caught:
                            MANAGER.main(argv)
                        self.assertEqual(caught.exception.code, 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                self.assertEqual(saved, json.loads((self.root / "last-operation.json").read_bytes()))
                self.assertEqual(saved["action"], "stop")
                self.assertTrue(saved["failed"])
                self.assertEqual(saved["result"]["stage"], "process_stop")
                self.assertEqual(saved["result"]["reason"], "stop_timeout")
                detail = saved["result"]["process"]
                self.assertEqual(detail["log_id"], log_id)
                self.assertEqual(detail["operation"], "process_wait")
                self.assertEqual(detail["reason"], "stop_timeout")
                self.assertEqual(detail["elapsed_seconds"], 30.25)
                self.assertEqual(detail["timeout_seconds"], 30)
                self.assertNotIn(private, json.dumps(saved))
                self.assertEqual(MANAGER.read_registry(self.config)["process"], self.registry["process"])
                if summary:
                    self.assertIn("operation=process_wait reason=stop_timeout seconds=30.25 timeout=30", output.getvalue())
                    self.assertNotIn(private, output.getvalue())

    def test_direct_apply_os_failure_is_saved_without_raw_text_in_both_modes(self):
        private = "synthetic-private-apply-PAT-and-path"
        for summary in (False, True):
            with self.subTest(summary=summary):
                error = PermissionError(13, private, private)
                error.winerror = 5
                output, stderr = io.StringIO(), io.StringIO()
                with patch.object(MANAGER.customization, "apply", side_effect=error), \
                        redirect_stdout(output), redirect_stderr(stderr):
                    argv = ["apply", "--config", "unused", "--bundle", "unused.zip", "--commit", COMMIT]
                    if summary:
                        self.assertEqual(MANAGER.main(argv + ["--summary"]), 1)
                    else:
                        with self.assertRaises(SystemExit) as caught:
                            MANAGER.main(argv)
                        self.assertEqual(caught.exception.code, 1)
                saved = json.loads((self.root / "last-failure.json").read_bytes())
                self.assertEqual(saved, json.loads((self.root / "last-operation.json").read_bytes()))
                self.assertEqual(saved["action"], "apply")
                self.assertTrue(saved["failed"])
                self.assertEqual(saved["result"]["stage"], "apply")
                detail = saved["result"]["local_error"]
                self.assertEqual((detail["type"], detail["errno"], detail["winerror"]), ("PermissionError", 13, 5))
                self.assertNotIn(private, output.getvalue() + stderr.getvalue() + json.dumps(saved))
                self.mocks["start_server"].assert_not_called()


class ProgramRenameSummaryTests(unittest.TestCase):
    def test_summary_retains_only_fixed_stage_and_bounded_integer_counters(self):
        private = "synthetic-private-PAT-and-path"
        for stage in ("move_active", "promote", "restore"):
            for attempts, waited in ((1, 0), (5, 15)):
                expected = {"stage": stage, "attempts": attempts, "waited_seconds": waited}
                value = dict(expected, private=private)
                self.assertEqual(MANAGER.safe_program_rename(value), expected)
                text = MANAGER.failure_fields({"program_rename": value})
                self.assertIn(f"rename={stage} attempts={attempts} waited={waited}", text)
                self.assertNotIn(private, text)

    def test_malformed_metadata_never_reaches_summary(self):
        private = "synthetic-private-PAT-and-path"
        valid = {"stage": "promote", "attempts": 5, "waited_seconds": 15}
        values = [None, [], private, {}, {"stage": "promote"}]
        for field, invalid in (("stage", [private, [], None, "apply"]),
                               ("attempts", [True, "5", 5.0, 0, 6, private]),
                               ("waited_seconds", [False, "15", 15.0, -1, 16, private])):
            values.extend(dict(valid, **{field: value}) for value in invalid)
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(MANAGER.safe_program_rename(value))
                text = MANAGER.failure_fields({"program_rename": value})
                self.assertNotIn("rename=", text)
                self.assertNotIn(private, text)

    def test_exception_metadata_requires_supported_windows_os_error(self):
        for kind, code, allowed in ((PermissionError, 5, True), (OSError, 32, True),
                                     (OSError, 33, True), (ValueError, 5, False),
                                     (OSError, None, False), (OSError, 13, False),
                                     (OSError, True, False), (OSError, "5", False),
                                     (OSError, 5.0, False)):
            with self.subTest(kind=kind, code=code):
                error = kind("synthetic-private-PAT-and-path")
                error.winerror = code
                error.program_rename_failed = True
                error.program_rename_stage = "promote"
                error.program_rename_attempts = 5
                error.program_rename_wait_seconds = 15
                expected = {"stage": "promote", "attempts": 5, "waited_seconds": 15} if allowed else None
                self.assertEqual(MANAGER.program_rename_detail(error), expected)

    def test_path_guard_errors_cannot_reuse_rename_counters_without_explicit_failure_marker(self):
        error = PermissionError(13, "synthetic-private-path")
        error.winerror = 5
        error.program_rename_stage = "promote"
        error.program_rename_attempts = 5
        error.program_rename_wait_seconds = 15
        self.assertIsNone(MANAGER.program_rename_detail(error))
        for marker in (False, None, 1, "true", "synthetic-private-path"):
            with self.subTest(marker=marker):
                error.program_rename_failed = marker
                self.assertIsNone(MANAGER.program_rename_detail(error))


class OperationFailureRetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = {"state_root": str(self.root)}
        self.args = argparse.Namespace(action="upgrade", config="synthetic.json", check_only=False)
        replacement = patch.object(MANAGER.states, "load_config", return_value=self.config)
        self.load = replacement.start()
        self.addCleanup(replacement.stop)
        self.failure = {"stage": "apply", "local_error": {"type": "PermissionError", "errno": 13,
                          "winerror": 5, "source": "ees_upgrade.py", "line": 277}}

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.root.iterdir()}

    def test_failure_is_retained_across_update_and_status_then_replaced_only_by_new_failure(self):
        protected = {self.root / "webui.db": b"synthetic DB bytes", self.root / "secret.key": b"synthetic key"}
        for path, data in protected.items():
            path.write_bytes(data)
        self.assertTrue(MANAGER.save_operation(self.args, self.failure, failed=True))
        retained = (self.root / "last-failure.json").read_bytes()
        self.assertEqual(json.loads(retained), json.loads((self.root / "last-operation.json").read_bytes()))
        self.args.action = "update"
        self.assertTrue(MANAGER.save_operation(self.args, {"stage": "complete", "changed": False}))
        self.assertEqual((self.root / "last-failure.json").read_bytes(), retained)
        self.assertEqual(json.loads((self.root / "last-operation.json").read_bytes())["action"], "update")
        before_status = self.snapshot()
        self.args.action = "status"
        self.assertTrue(MANAGER.save_operation(self.args, {"stage": "complete"}))
        self.assertEqual(self.snapshot(), before_status)
        self.args.action = "stop"
        newer = {"stage": "process_stop", "process": {"reason": "stop_timeout"}}
        self.assertTrue(MANAGER.save_operation(self.args, newer, failed=True))
        current = json.loads((self.root / "last-failure.json").read_bytes())
        self.assertEqual(current["action"], "stop")
        self.assertTrue(current["failed"])
        self.assertEqual(current["result"], newer)
        self.assertEqual(current, json.loads((self.root / "last-operation.json").read_bytes()))
        for path, data in protected.items():
            self.assertEqual(path.read_bytes(), data)

    def test_check_only_and_status_never_load_config_or_write_failure_history(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                if populated:
                    (self.root / "last-operation.json").write_bytes(b"synthetic previous result")
                    (self.root / "last-failure.json").write_bytes(b"synthetic previous failure")
                before = self.snapshot()
                for action, check_only in (("apply", True), ("status", False)):
                    args = argparse.Namespace(action=action, config="synthetic.json", check_only=check_only)
                    for failed in (True, False):
                        self.assertTrue(MANAGER.save_operation(args, self.failure, failed=failed))
                self.assertEqual(self.snapshot(), before)
                self.load.assert_not_called()

    def test_linked_report_destinations_reject_all_writes_and_preserve_both_records(self):
        self.assertTrue(MANAGER.save_operation(self.args, self.failure, failed=True))
        before = self.snapshot()
        for name in ("last-operation.json", "last-failure.json"):
            for kind in ("hard", "symbolic"):
                with self.subTest(name=name, kind=kind):
                    target, outside = self.root / name, self.root / "synthetic-unrelated.json"
                    if kind == "hard":
                        try:
                            os.link(target, outside)
                        except OSError:
                            self.skipTest("This volume cannot create a hard link for the guard check.")
                    else:
                        target.rename(outside)
                        try:
                            target.symlink_to(outside)
                        except OSError:
                            outside.rename(target)
                            self.skipTest("Symbolic link creation needs an unavailable platform privilege.")
                    try:
                        self.assertFalse(MANAGER.save_operation(self.args, {"new": "failure"}, failed=True))
                        for filename, data in before.items():
                            self.assertEqual((self.root / filename).read_bytes(), data)
                        self.assertEqual(outside.read_bytes(), before[name])
                    finally:
                        if kind == "symbolic":
                            target.unlink()
                            outside.rename(target)
                        else:
                            outside.unlink()
        self.assertEqual(self.snapshot(), before)


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell adapter execution requires pwsh")
class PowerShellResumeTests(unittest.TestCase):
    def test_documented_manual_apply_and_resume_blocks_parse_in_powershell(self):
        guide = (ROOT / "docs" / "03-openwebui-native-agent.md").read_text(encoding="utf-8")
        section = guide.split('<a id="ees-wrapper-manual-promote"></a>', 1)[1]
        blocks = re.findall(r"```powershell\n(.*?)\n```", section, re.DOTALL)[:2]
        self.assertEqual(len(blocks), 2)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parser = root / "parse.ps1"
            parser.write_text("""param([string]$SourcePath)
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) {
    $parseErrors | ForEach-Object { $_.Message }
    exit 1
}
""", encoding="utf-8")
            for name, block in zip(("manual-apply", "manual-resume"), blocks):
                with self.subTest(block=name):
                    self.assertLessEqual(len(block), 2500)
                    source = root / (name + ".ps1")
                    source.write_text(block, encoding="utf-8")
                    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(parser), str(source)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_adapter_forwards_resume_and_check_only_and_rejects_other_actions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            adapter = scripts / "manage-ees.ps1"
            shutil.copyfile(ROOT / "scripts" / "manage-ees.ps1", adapter)
            (scripts / "manage_ees.py").write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            config = root / "config.json"
            config.write_text(json.dumps({"source_python": sys.executable}), encoding="utf-8")
            command = [shutil.which("pwsh"), "-NoProfile", "-File", str(adapter)]
            result = subprocess.run(command + ["-Action", "Apply", "-Config", str(config), "-Bundle", "synthetic.zip",
                "-Commit", COMMIT, "-Resume", "-CheckOnly"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["apply", "--config", str(config), "--bundle", "synthetic.zip",
                                                        "--commit", COMMIT, "--check-only", "--resume"])
            result = subprocess.run(command + ["-Action", "Start", "-Config", str(config), "-UseWindowsCA",
                "-HealthTimeout", "120", "-Summary"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["start", "--config", str(config), "--health-timeout", "120",
                                                        "--use-windows-ca", "--summary"])
            result = subprocess.run(command + ["-Action", "Start", "-Config", str(config), "-CheckOnly", "-Summary"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["start", "--config", str(config), "--check-only", "--summary"])
            result = subprocess.run(command + ["-Action", "Apply", "-Config", str(config), "-UseWindowsCA"],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UseWindowsCA is supported only with Deploy or Start", result.stderr)
            self.assertEqual(result.stdout.strip(), "")
            for action in ("Start", "Restore", "Update"):
                with self.subTest(action=action):
                    result = subprocess.run(command + ["-Action", action, "-Config", str(config), "-Resume"],
                                            capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Resume is supported only with Apply", result.stderr)
                    self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
