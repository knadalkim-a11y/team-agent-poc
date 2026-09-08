"""Transaction tests use synthetic state; never start or inspect a real server."""

import argparse
import importlib.util
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
        self.original_process = {"pid": 100, "executable": "original-python"}
        self.candidate_process = {"pid": 200, "executable": "candidate-python"}
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
            patch.object(MANAGER.processes, "port_is_free", side_effect=lambda *_: self.port_free),
            patch.object(MANAGER.processes, "verify_identity", return_value=True),
            patch.object(MANAGER.processes, "stop_server", side_effect=stopped),
            patch.object(MANAGER.processes, "start_server", side_effect=start),
            patch.object(MANAGER.processes, "wait_healthy", side_effect=lambda _: self.events.append("health")),
            patch.object(MANAGER.states, "backup_state", side_effect=backup),
        ]
        self.mocks = []
        for override in overrides:
            self.mocks.append(override.start())
            self.addCleanup(override.stop)

    def read(self):
        return MANAGER.read_registry(self.config)

    def test_switch_orders_shutdown_backup_start_then_commits_pointer(self):
        def health(_):
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
        def health(identity):
            if identity == self.candidate_process:
                raise MANAGER.processes.ProcessError("synthetic startup failure")

        self.mocks[6].side_effect = health
        marker = self.root / "synthetic-memory.txt"
        marker.write_bytes(b"New user memory is not rolled back")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "previous program is running"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertEqual(self.read()["current"], self.original)
        self.assertEqual(self.read()["process"], self.original_process)
        self.assertEqual(self.read()["phase"], "idle")
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

    def test_backup_failure_does_not_launch_candidate_and_recovers_original(self):
        self.mocks[7].side_effect = MANAGER.states.StateError("synthetic backup failed")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "previous program is running"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.assertNotIn("start:candidate-python", self.events)
        self.assertEqual(self.read()["current"], self.original)

    def test_unidentified_launched_child_blocks_automatic_recovery_even_before_listen(self):
        self.mocks[5].side_effect = MANAGER.processes.LaunchUncertain("identity unavailable")
        with self.assertRaisesRegex(MANAGER.DeploymentError, "Automatic recovery was blocked"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[5].assert_called_once()
        self.assertEqual(self.read()["phase"], "recovery_required")
        self.assertTrue(self.read()["launch_uncertain"])
        with self.assertRaisesRegex(MANAGER.DeploymentError, "could not be identified"):
            MANAGER.stop_registered(self.config, self.read())

    def test_unmanaged_listener_is_not_stopped_and_no_backup_is_started(self):
        self.registry["process"] = None
        MANAGER.write_json(MANAGER.registry_path(self.config), self.registry)
        with self.assertRaisesRegex(MANAGER.DeploymentError, "port is in use"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[4].assert_not_called()
        self.mocks[7].assert_not_called()
        self.assertEqual(self.read()["phase"], "idle")

    def test_process_identity_mismatch_never_advances_the_switch(self):
        self.mocks[4].side_effect = MANAGER.processes.ProcessError("identity changed")
        with self.assertRaisesRegex(MANAGER.processes.ProcessError, "identity changed"):
            MANAGER.switch(self.config, self.candidate, "deployed")
        self.mocks[7].assert_not_called()
        self.mocks[5].assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
