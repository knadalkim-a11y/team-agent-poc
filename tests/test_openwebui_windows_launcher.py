"""Linux mock checks only; no Windows runtime or real Open WebUI state is used."""

import asyncio
import builtins
import contextlib
import importlib.metadata
import importlib.util
import io
import os
import socket
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "windows_launcher",
    Path(__file__).resolve().parents[1] / "scripts/serve_openwebui_windows.py",
)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.database = self.data / "webui.db"
        self.database.write_bytes(b"synthetic-existing-database")
        self.key_file = self.root / ".webui_secret_key"
        self.secret = "synthetic-existing-secret-never-print-this\n"
        self.key_file.write_text(self.secret, encoding="utf-8")
        original_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original_cwd)
        self.enterContext(patch.dict(os.environ, {
            "DATA_DIR": str(self.data),
            "HTTP_PROXY": "http://synthetic-proxy.example:8080",
            "NO_PROXY": "localhost,127.0.0.1",
            "ENABLE_VALVE_ENCRYPTION": "true",
        }, clear=True))
        self.enterContext(patch.object(sys, "platform", "win32"))
        self.enterContext(patch.object(sys, "version_info", (3, 11, 15, "final", 0)))
        self.package_versions = {"open-webui": "0.11.3", "uvicorn": "0.51.0"}
        self.enterContext(patch.object(launcher, "version", side_effect=self.version))
        self.package_root = self.root / "installed-package"
        self.package_root.mkdir()
        package_spec = types.SimpleNamespace(
            origin=str(self.package_root / "backend/open_webui/__init__.py"),
        )
        self.enterContext(patch.object(launcher, "find_spec", return_value=package_spec))
        self.policy = object()
        self.policy_factory = self.enterContext(patch.object(
            asyncio, "WindowsSelectorEventLoopPolicy", return_value=self.policy, create=True,
        ))
        self.set_policy = self.enterContext(patch.object(asyncio, "set_event_loop_policy"))
        self.bind_args = ["--host", "0.0.0.0", "--port", "8080"]
        self.output = io.StringIO()
        self.errors = io.StringIO()

    def version(self, package):
        if package not in self.package_versions:
            raise importlib.metadata.PackageNotFoundError(package)
        return self.package_versions[package]

    def invoke(self, args):
        with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.errors):
            return launcher.main(args)

    @contextlib.contextmanager
    def forbid_application_import(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "open_webui" or name.startswith("open_webui."):
                raise AssertionError("Open WebUI must not be imported")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=guarded_import):
            yield

    def assert_rejected(self, args):
        try:
            result = self.invoke(args)
        except SystemExit as error:
            result = error.code
        self.assertIsInstance(result, int)
        self.assertNotEqual(result, 0)
        self.set_policy.assert_not_called()

    def test_check_does_not_import_app_read_contents_connect_or_select_a_loop(self):
        files_before = set(self.root.rglob("*"))
        environment_before = dict(os.environ)
        with self.forbid_application_import(), \
                patch.object(socket, "socket", side_effect=AssertionError("network access")), \
                patch.object(socket, "create_connection", side_effect=AssertionError("network access")), \
                patch.object(sqlite3, "connect", side_effect=AssertionError("database access")), \
                patch.object(builtins, "open", side_effect=AssertionError("file content access")), \
                patch.object(io, "open", side_effect=AssertionError("file content access")):
            self.assertEqual(self.invoke(["--check"]), 0)
        self.assertEqual(files_before, set(self.root.rglob("*")))
        self.assertEqual(environment_before, dict(os.environ))
        self.policy_factory.assert_not_called()
        self.set_policy.assert_not_called()
        self.assertNotIn(self.secret.strip(), self.output.getvalue() + self.errors.getvalue())

    def test_serve_sets_policy_before_import_and_preserves_state_and_bindings(self):
        app = types.ModuleType("open_webui")
        calls = []
        environment_before = dict(os.environ)
        bytes_before = (self.database.read_bytes(), self.key_file.read_bytes())
        original_import = builtins.__import__

        def serve(*, host, port):
            self.set_policy.assert_called_once_with(self.policy)
            self.assertEqual(Path.cwd(), self.root)
            self.assertEqual(dict(os.environ), environment_before)
            calls.append((host, port))

        def ordered_import(name, *args, **kwargs):
            if name == "open_webui":
                self.set_policy.assert_called_once_with(self.policy)
            return original_import(name, *args, **kwargs)

        app.serve = serve
        with patch.dict(sys.modules, {"open_webui": app}), \
                patch.object(builtins, "__import__", side_effect=ordered_import):
            self.assertEqual(self.invoke(self.bind_args), 0)
        self.assertEqual(calls, [("0.0.0.0", 8080)])
        self.assertEqual(bytes_before, (self.database.read_bytes(), self.key_file.read_bytes()))
        self.assertEqual(dict(os.environ), environment_before)
        self.assertNotIn(self.secret.strip(), self.output.getvalue() + self.errors.getvalue())

    def test_missing_state_stops_before_app_import_without_creating_files(self):
        for missing in (self.database, self.key_file):
            with self.subTest(missing=missing.name):
                contents = missing.read_bytes()
                missing.unlink()
                files_before = set(self.root.rglob("*"))
                with self.forbid_application_import():
                    self.assert_rejected(self.bind_args)
                self.assertEqual(files_before, set(self.root.rglob("*")))
                self.assertFalse(missing.exists())
                missing.write_bytes(contents)

    def test_environment_key_is_preserved_without_creating_a_key_file(self):
        self.key_file.unlink()
        os.environ["WEBUI_SECRET_KEY"] = self.secret
        app = types.ModuleType("open_webui")
        calls = []

        def serve(*, host, port):
            self.assertEqual(os.environ["WEBUI_SECRET_KEY"], self.secret)
            self.assertFalse(self.key_file.exists())
            calls.append((host, port))

        app.serve = serve
        with patch.dict(sys.modules, {"open_webui": app}):
            self.assertEqual(self.invoke(self.bind_args), 0)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.key_file.exists())
        self.assertNotIn(self.secret.strip(), self.output.getvalue() + self.errors.getvalue())

    def test_empty_environment_key_cannot_silently_override_the_existing_key_file(self):
        for value in ("", " \n"):
            with self.subTest(value=repr(value)), patch.dict(os.environ, {"WEBUI_SECRET_KEY": value}), \
                    self.forbid_application_import():
                self.assert_rejected(self.bind_args)

    def test_workers_platform_python_and_distribution_versions_block_before_import(self):
        cases = [
            ("workers", patch.dict(os.environ, {"UVICORN_WORKERS": "2"})),
            ("invalid-workers", patch.dict(os.environ, {"UVICORN_WORKERS": "invalid"})),
            ("linux", patch.object(sys, "platform", "linux")),
            ("python-312", patch.object(sys, "version_info", (3, 12, 10, "final", 0))),
            ("other-webui", patch.dict(self.package_versions, {"open-webui": "0.11.4"})),
            ("other-uvicorn", patch.dict(self.package_versions, {"uvicorn": "0.52.0"})),
            ("missing-webui", patch.dict(self.package_versions, {"uvicorn": "0.51.0"}, clear=True)),
        ]
        for name, replacement in cases:
            with self.subTest(case=name), replacement, self.forbid_application_import():
                self.assert_rejected(self.bind_args)

    def test_custom_database_configuration_is_rejected_and_not_erased_or_printed(self):
        for key, value in (
            ("DATABASE_URL", "postgresql://synthetic-user:synthetic-db-secret@invalid/db"),
            ("DATABASE_TYPE", "sqlite"),
        ):
            with self.subTest(setting=key), patch.dict(os.environ, {key: value}), \
                    self.forbid_application_import():
                environment_before = dict(os.environ)
                self.assert_rejected(self.bind_args)
                self.assertEqual(environment_before, dict(os.environ))
                self.assertNotIn(value, self.output.getvalue() + self.errors.getvalue())

    def test_package_dotenv_is_not_read_or_silently_overridden(self):
        dotenv = self.package_root / ".env"
        private_value = "WEBUI_SECRET_KEY=synthetic-dotenv-secret"
        dotenv.write_text(private_value, encoding="utf-8")
        environment_before = dict(os.environ)
        with self.forbid_application_import(), \
                patch.object(builtins, "open", side_effect=AssertionError("file content access")), \
                patch.object(io, "open", side_effect=AssertionError("file content access")):
            self.assert_rejected(["--check"])
        self.assertEqual(dotenv.read_text(encoding="utf-8"), private_value)
        self.assertEqual(dict(os.environ), environment_before)
        self.assertNotIn(private_value, self.output.getvalue() + self.errors.getvalue())

    def test_relative_data_directory_and_implicit_bindings_cannot_start(self):
        with patch.dict(os.environ, {"DATA_DIR": "data"}), self.forbid_application_import():
            self.assert_rejected(self.bind_args)
        for args in ([], ["--host", "0.0.0.0"], ["--port", "8080"]):
            with self.subTest(args=args), self.forbid_application_import():
                self.assert_rejected(args)

    def test_original_application_exception_is_not_swallowed(self):
        app = types.ModuleType("open_webui")
        failure = RuntimeError("synthetic application failure")

        def serve(*, host, port):
            raise failure

        app.serve = serve
        with patch.dict(sys.modules, {"open_webui": app}):
            with self.assertRaises(RuntimeError) as caught:
                self.invoke(self.bind_args)
        self.assertIs(caught.exception, failure)


if __name__ == "__main__":
    unittest.main()
