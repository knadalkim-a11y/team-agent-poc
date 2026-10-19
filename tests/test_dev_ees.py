"""Personal development must preserve existing processes, data and credentials."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import dev_ees as development


class PersonalDevelopmentTests(unittest.TestCase):
    def test_build_root_can_move_temporary_artifacts_without_moving_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            data = development.DATA
            with patch.dict(development.os.environ, {"EES_DEV_BUILD_ROOT": directory}), \
                    patch.object(development, "stopped"), \
                    patch.object(development, "source_state", return_value={"commit": "test"}), \
                    patch.object(development, "run", side_effect=RuntimeError("build probe")) as run:
                with self.assertRaisesRegex(RuntimeError, "build probe"):
                    development.build()
            destination = Path(run.call_args.args[0][-1])
            self.assertEqual(destination.parent.parent, Path(directory).resolve())
            self.assertEqual(destination.name, "source")
            self.assertEqual(development.DATA, data)

    def test_running_process_prevents_installation(self):
        with patch.object(development, "read", return_value={"pid": 42}):
            with patch.object(development.processes, "verify_identity", return_value=True):
                with self.assertRaisesRegex(ValueError, "Stop the local"):
                    development.stopped()

    def test_unrelated_listener_is_not_stopped(self):
        with patch.object(development, "read", return_value=None):
            with patch.object(development.processes, "port_is_free", return_value=False):
                with self.assertRaisesRegex(ValueError, "occupied"):
                    development.stopped()

    def test_start_is_loopback_only_and_does_not_inherit_external_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.multiple(development, DATA=Path(directory), STATE=Path(directory)), \
                    patch.object(development, "stopped"), \
                    patch.object(development, "read", return_value={"version": "0.11.3+ees.14"}), \
                    patch.object(development.importlib.metadata, "version", return_value="0.11.3+ees.14"), \
                    patch.object(development, "save") as save, \
                    patch.object(development.processes, "start_server", return_value={"log_file": "local.log"}) as launch, \
                    patch.object(development.processes, "wait_healthy"), \
                    patch.dict(development.os.environ, {"OPENAI_API_KEY": "unrelated-test-key",
                                                       "DATABASE_URL": "unrelated-test-db",
                                                       "WEBUI_SECRET_KEY": "unrelated-test-secret"}):
                development.start()
            environment = launch.call_args.args[2]
            self.assertEqual(launch.call_args.args[3:5], ("127.0.0.1", 8080))
            for name in ("OPENAI_API_KEY", "DATABASE_URL", "WEBUI_SECRET_KEY"):
                self.assertNotIn(name, environment)
            self.assertEqual(environment["ENABLE_OPENAI_API"], "false")
            self.assertEqual(environment["DATA_DIR"], str(Path(directory) / "data"))
            save.assert_called_once()

    def test_receipt_write_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            development.save(target, {"version": 1})
            development.save(target, {"version": 2})
            self.assertEqual(development.read(target), {"version": 2})
            self.assertFalse(target.with_suffix(".tmp").exists())

    def test_existing_database_cannot_generate_a_replacement_key(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "data"
            data.mkdir()
            (data / "webui.db").write_bytes(b"existing-test-database")
            with patch.object(development, "DATA", Path(directory)), \
                    patch.object(development, "stopped"), \
                    patch.object(development, "read", return_value={"version": "0.11.3+ees.14"}), \
                    patch.object(development.importlib.metadata, "version", return_value="0.11.3+ees.14"), \
                    patch.object(development.processes, "start_server") as launch:
                with self.assertRaisesRegex(ValueError, "restore its original key"):
                    development.start()
            launch.assert_not_called()
            self.assertEqual((data / "webui.db").read_bytes(), b"existing-test-database")


if __name__ == "__main__":
    unittest.main()
