"""Synthetic state fixtures; DPAPI is mocked except its Windows-only roundtrip."""

import contextlib
import importlib.util
import importlib.metadata
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("ees_state", Path(__file__).resolve().parents[1] / "scripts/ees_deploy_state.py")
STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE)


class DeploymentStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ees-state-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = self.root / "profile"
        self.cwd = self.profile / "original"
        self.data = self.cwd / "data"
        self.data.mkdir(parents=True)
        self.db = self.data / "webui.db"
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("CREATE TABLE synthetic (value TEXT)")
            connection.execute("INSERT INTO synthetic VALUES ('initial')")
        self.key = self.cwd / ".webui_secret_key"
        self.key.write_text("SYNTHETIC_KEY_VALUE\n", encoding="utf-8")
        self.prefix = self.root / "python-environment"
        self.package = self.prefix / "Lib/site-packages/open_webui"
        self.package.mkdir(parents=True)
        self.python = self.prefix / "python.exe"
        self.python.write_bytes(b"synthetic-executable")
        self.uv = self.root / "uv.exe"
        self.uv.write_bytes(b"synthetic-executable")
        self.config_path = self.profile / "deployment/config.json"
        self.env_names = ["DATA_DIR", "CORS_ALLOW_ORIGIN", "OPENAI_API_KEY", "WEBUI_NAME", "NEW_APP_OPTION", "PATH", "LOCALAPPDATA",
                          "DATABASE_URL", "VECTOR_DB", "STORAGE_PROVIDER", "UVICORN_WORKERS"]
        self.info = {"source_prefix": str(self.prefix), "package_dir": str(self.package),
                     "python_version": [3, 11, 15], "platform": "win32", "open_webui_version": "0.11.3",
                     "env_names": self.env_names}
        self.enterContext(patch.object(STATE, "_inspect", side_effect=lambda path: dict(self.info)))
        self.enterContext(patch.object(STATE, "_protect", side_effect=lambda value: b"FAKE-DPAPI:" + bytes(byte ^ 0xA5 for byte in value)))
        self.enterContext(patch.object(STATE, "_unprotect", side_effect=lambda value: bytes(byte ^ 0xA5 for byte in value.removeprefix(b"FAKE-DPAPI:"))))
        self.enterContext(patch.dict(os.environ, {"LOCALAPPDATA": str(self.profile), "DATA_DIR": str(self.data),
            "CORS_ALLOW_ORIGIN": "http://synthetic.example.invalid:8080", "OPENAI_API_KEY": "SYNTHETIC_API_SECRET",
            "UV_INDEX_PRIVATE_PASSWORD": "SYNTHETIC_INDEX_SECRET", "UNRELATED_PC_SECRET": "SYNTHETIC_UNRELATED",
            "PATH": "synthetic-base-path"}, clear=True))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network access is forbidden")))

    def init(self, path=None):
        return STATE.init_config(path or self.config_path, self.python, self.cwd, self.data, "127.0.0.1", 8080, self.uv)

    def test_registration_preserves_existing_files_and_stores_only_encrypted_environment_values(self):
        original = {path: path.read_bytes() for path in (self.db, self.key, self.python)}
        config = self.init()
        serialized = self.config_path.read_bytes()
        encrypted = Path(config["environment_file"]).read_bytes()
        for secret in (b"SYNTHETIC_API_SECRET", b"SYNTHETIC_INDEX_SECRET", b"SYNTHETIC_KEY_VALUE", b"synthetic.example.invalid"):
            self.assertNotIn(secret, serialized)
            self.assertNotIn(secret, encrypted)
        snapshot = json.loads(STATE._unprotect(encrypted))
        self.assertNotIn("UNRELATED_PC_SECRET", snapshot["values"])
        self.assertNotIn("PATH", snapshot["values"])
        self.assertEqual(snapshot["values"]["OPENAI_API_KEY"], "SYNTHETIC_API_SECRET")
        self.assertEqual(STATE.load_config(self.config_path), config)
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)
        with self.assertRaisesRegex(STATE.StateError, "already exists"):
            self.init()

    def test_runtime_restores_snapshot_removes_app_drift_and_inherits_os_path(self):
        original_cache = str(self.data / "cache/embeddings")
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = original_cache
        config = self.init()
        os.environ.update({"CORS_ALLOW_ORIGIN": "changed-origin", "OPENAI_API_KEY": "changed-secret",
                           "NEW_APP_OPTION": "new-unsaved-value", "WEBUI_SECRET_KEY": "changed-key",
                           "UV_INDEX_NEW_PASSWORD": "new-secret", "PATH": "new-system-path",
                           "DATA_DIR": str(self.root / "wrong-data"), "SENTENCE_TRANSFORMERS_HOME": "changed-cache"})
        restored = STATE.runtime_environment(config)
        self.assertEqual(restored["CORS_ALLOW_ORIGIN"], "http://synthetic.example.invalid:8080")
        self.assertEqual(restored["OPENAI_API_KEY"], "SYNTHETIC_API_SECRET")
        self.assertEqual(restored["UV_INDEX_PRIVATE_PASSWORD"], "SYNTHETIC_INDEX_SECRET")
        self.assertEqual(restored["DATA_DIR"], str(self.data))
        self.assertEqual(restored["PATH"], "new-system-path")
        self.assertEqual(restored["SENTENCE_TRANSFORMERS_HOME"], original_cache)
        for name in ("NEW_APP_OPTION", "WEBUI_SECRET_KEY", "UV_INDEX_NEW_PASSWORD"):
            self.assertNotIn(name, restored)

    def test_dotenv_and_unsupported_overrides_fail_without_rewriting_them(self):
        for path in (self.cwd / ".env", self.package.parent.parent / ".env"):
            with self.subTest(path=path):
                path.write_text("SYNTHETIC_ENV_CONTENT", encoding="utf-8")
                with self.assertRaisesRegex(STATE.StateError, "existing .env"):
                    self.init()
                self.assertEqual(path.read_text(encoding="utf-8"), "SYNTHETIC_ENV_CONTENT")
                self.assertFalse(self.config_path.parent.exists())
                path.unlink()
        for name, value in (("DATABASE_URL", "synthetic-external-db"), ("VECTOR_DB", "qdrant"),
                            ("STORAGE_PROVIDER", "s3"), ("UVICORN_WORKERS", "2"),
                            ("FRONTEND_BUILD_DIR", ""), ("PYTHONPATH", "synthetic-import-path"),
                            ("HF_HOME", str(self.root / "external-model-cache")), ("TORCH_HOME", "relative-cache")):
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                with self.assertRaises(STATE.StateError) as caught:
                    self.init()
                if value:
                    self.assertNotIn(value, str(caught.exception))
                self.assertEqual(os.environ[name], value)
                self.assertFalse(self.config_path.parent.exists())

    def test_missing_db_or_key_never_creates_replacements(self):
        self.db.unlink()
        with self.assertRaises(STATE.StateError):
            self.init()
        self.assertFalse(self.db.exists())
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("CREATE TABLE synthetic (value TEXT)")
        self.key.unlink()
        with self.assertRaisesRegex(STATE.StateError, "existing key"):
            self.init()
        self.assertFalse(self.key.exists())
        with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "SYNTHETIC_ENV_KEY"}):
            config = self.init()
            self.assertIsNone(config["key_file"])
            self.assertEqual(STATE.runtime_environment(config)["WEBUI_SECRET_KEY"], "SYNTHETIC_ENV_KEY")
        self.assertFalse(self.key.exists())

    def test_overlapping_or_non_profile_state_directory_is_rejected_before_creation(self):
        for path in (self.data / "deploy/config.json", self.cwd / "deploy/config.json",
                     self.prefix / "deploy/config.json", self.root / "outside-profile/config.json"):
            with self.subTest(path=path), self.assertRaises(STATE.StateError):
                self.init(path)
            self.assertFalse(path.parent.exists())

    def test_config_key_and_ciphertext_drift_fail_closed(self):
        config = self.init()
        modified = dict(config, host="192.0.2.1")
        with self.assertRaisesRegex(STATE.StateError, "fingerprint changed"):
            STATE.runtime_environment(modified)
        original_config = self.config_path.read_bytes()
        self.config_path.write_text(json.dumps(modified), encoding="utf-8")
        with self.assertRaisesRegex(STATE.StateError, "fingerprint changed"):
            STATE.runtime_environment(config)
        self.config_path.write_bytes(original_config)
        original_key = self.key.read_bytes()
        self.key.write_bytes(b"SYNTHETIC_CHANGED_KEY")
        with self.assertRaisesRegex(STATE.StateError, "key file changed"):
            STATE.runtime_environment(config)
        self.key.write_bytes(original_key)
        snapshot = Path(config["environment_file"])
        snapshot.write_bytes(snapshot.read_bytes() + b"changed")
        with self.assertRaisesRegex(STATE.StateError, "snapshot changed"):
            STATE.runtime_environment(config)

    def test_symlinks_and_hardlinks_cannot_pull_external_state_into_backup(self):
        external = self.root / "outside.bin"
        external.write_bytes(b"SYNTHETIC_EXTERNAL_SECRET")
        link = self.data / "linked.bin"
        try:
            os.link(external, link)
        except OSError:
            self.skipTest("Hardlinks unavailable")
        with self.assertRaisesRegex(STATE.StateError, "multiply linked"):
            self.init()
        link.unlink()
        try:
            link.symlink_to(external)
        except (NotImplementedError, OSError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(STATE.StateError, "reparse points"):
            self.init()
        self.assertFalse(self.config_path.parent.exists())

    def test_cached_executable_hardlinks_are_accepted_without_relaxing_state_checks(self):
        for executable in (self.python, self.uv):
            try:
                os.link(executable, executable.with_suffix(".cached"))
            except OSError:
                self.skipTest("Hardlinks unavailable")
        self.assertEqual(self.init()["source_python"], str(self.python))

    def test_backup_preserves_all_files_wal_shm_and_verifiable_bytes(self):
        connection = sqlite3.connect(self.db)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO synthetic VALUES ('committed-in-wal')")
        connection.commit()
        # A stable crash-recovery fixture without a live database process.
        crash_files = {path: path.read_bytes() for path in self.data.glob("webui.db*")}
        connection.close()
        for path, content in crash_files.items():
            path.write_bytes(content)
        upload = self.data / "uploads/nested/document.txt"
        upload.parent.mkdir(parents=True)
        upload.write_text("SYNTHETIC_UPLOAD", encoding="utf-8")
        (self.data / "empty-cache").mkdir()
        config = self.init()
        originals = {path: path.read_bytes() for path in STATE._files(self.data)}
        original_key = self.key.read_bytes()
        metadata = STATE.backup_state(config)
        destination = Path(metadata["path"])
        manifest = json.loads((destination / "manifest.json").read_bytes())
        entries = {entry["path"]: entry for entry in manifest["files"]}
        self.assertEqual(metadata["database_check"], "ok")
        self.assertTrue((destination / "data/empty-cache").is_dir())
        for path, content in originals.items():
            name = "data/" + path.relative_to(self.data).as_posix()
            self.assertEqual((destination / name).read_bytes(), content)
            self.assertEqual(entries[name]["sha256"], STATE._sha(content))
            self.assertEqual(path.read_bytes(), content)
        for name in ("data/webui.db-wal", "data/webui.db-shm", "key/.webui_secret_key",
                     "configuration/config.json", "configuration/environment.dpapi"):
            self.assertIn(name, entries)
        self.assertEqual(self.key.read_bytes(), original_key)
        self.assertFalse(any(Path(config["backups_dir"]).glob("sqlite-check-*")))

    def test_invalid_sqlite_never_receives_a_success_manifest(self):
        self.db.write_bytes(b"SYNTHETIC_INVALID_DATABASE")
        config = self.init()
        with self.assertRaises(STATE.StateError):
            STATE.backup_state(config)
        self.assertEqual(list(Path(config["backups_dir"]).rglob("manifest.json")), [])

    def test_ast_inspector_collects_literal_names_without_importing_application(self):
        (self.package / "__init__.py").write_text("raise AssertionError('Application import forbidden')", encoding="utf-8")
        (self.package / "env.py").write_text("import os\na=os.getenv('LITERAL_ONE')\nb=os.environ.get('LITERAL_TWO')\nc=os.environ['LITERAL_THREE']\nd=os.getenv(dynamic_name)\n", encoding="utf-8")
        (self.package / "config.py").write_text("from os import getenv as env\nx=env('ALIASED_LITERAL')\n", encoding="utf-8")
        output = io.StringIO()
        spec = types.SimpleNamespace(origin=str(self.package / "__init__.py"))
        with patch.object(importlib.util, "find_spec", return_value=spec), \
                patch.object(importlib.metadata, "version", return_value="0.11.3"), contextlib.redirect_stdout(output):
            exec(STATE.INSPECT, {})
        result = json.loads(output.getvalue())
        self.assertEqual(result["env_names"], ["ALIASED_LITERAL", "LITERAL_ONE", "LITERAL_THREE", "LITERAL_TWO"])


class WindowsDpapiTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Real CurrentUser DPAPI requires Windows")
    def test_current_user_dpapi_roundtrip(self):
        plaintext = b"Synthetic DPAPI canary, never a real API key"
        protected = STATE._protect(plaintext)
        self.assertNotIn(plaintext, protected)
        self.assertEqual(STATE._unprotect(protected), plaintext)


if __name__ == "__main__":
    unittest.main()
