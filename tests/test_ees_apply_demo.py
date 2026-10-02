"""Operator entry tests use a local synthetic HTTP API; no WebUI or credentials."""

import argparse
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts import ees_apply_demo as demo


TOKEN = "synthetic-webui-token"
HEAD = "a" * 40


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization"), data))
        if self.path == "/api/redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/api/secret")
            self.end_headers()
            return
        status = 404 if self.path == "/api/missing" else 500 if self.path == "/api/fail" else 200
        if self.path.startswith(demo.assets.ASSET_API + "/"):
            status = getattr(self.server, "asset_status", 503)
        payload = ({"version": "0.11.3+ees.12"} if self.path == "/api/version"
                   else {"role": "admin"} if self.path == "/api/v1/auths/"
                   else {"id": "existing", "base_model_id": "base", "params": {"system": "user text"}, "write_access": True}
                   if self.path == "/api/v1/models/model?id=existing"
                   else {"private": TOKEN} if status >= 400
                   else {"received": json.loads(data) if data else None})
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class WebUIHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.seen = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.server.seen.clear()
        self.server.asset_status = 503
        self.client = demo.WebUIClient(self.url, TOKEN, timeout=2)

    def test_retired_apply_refuses_before_transport_credentials_git_or_server_control(self):
        progress = {}
        with (patch.object(demo, "load_token") as token,
              patch.object(demo.upgrade, "checkout") as checkout,
              patch.object(demo.upgrade.manager, "stop_registered") as stop,
              patch.object(demo.assets, "apply_assets") as core):
            with self.assertRaisesRegex(demo.DemoError, "demo_registration_retired"):
                demo.apply({}, argparse.Namespace(), HEAD, progress)
            token.assert_not_called()
            checkout.assert_not_called()
            stop.assert_not_called()
            core.assert_not_called()
        self.assertEqual(self.server.seen, [])
        self.assertEqual(progress, {"stage": "retired", "changed": 0})

    def test_retired_main_does_not_load_user_config_or_request_credentials(self):
        output = io.StringIO()
        with (patch.object(demo.upgrade.manager.states, "load_config") as config,
              patch.object(demo, "load_token") as token, redirect_stdout(output)):
            self.assertEqual(demo.main(["--config", "not-read.json"]), 1)
            config.assert_not_called()
            token.assert_not_called()
        self.assertIn("demo_registration_retired", output.getvalue())
        self.assertIn("changed=0", output.getvalue())

    def test_json_utf8_and_bearer_request(self):
        value = {"params": {"system": "기존 지침\n추가 지침"}, "id": "existing"}
        self.assertEqual(self.client.request("POST", "/api/echo", value), {"received": value})
        self.assertEqual(self.server.seen[0][2], "Bearer " + TOKEN)

    def test_redirect_never_follows_or_exposes_credentials(self):
        with self.assertRaisesRegex(demo.DemoError, "redirect_blocked"):
            self.client.request("GET", "/api/redirect")
        self.assertEqual(len(self.server.seen), 1)

    def test_only_get_404_means_absent_and_raw_error_stays_private(self):
        self.assertIsNone(self.client.request("GET", "/api/missing"))
        for method, path in [("POST", "/api/missing"), ("GET", "/api/fail")]:
            with self.assertRaises(demo.DemoError) as raised:
                self.client.request(method, path, {} if method == "POST" else None)
            self.assertNotIn(TOKEN, str(raised.exception))

    def test_conditional_conflict_and_unavailable_are_safe_typed_errors(self):
        for status, code in ((409, "concurrent_edit"), (404, "conditional_write_unavailable"),
                             (405, "conditional_write_unavailable"), (503, "conditional_write_unavailable")):
            with self.subTest(status=status):
                self.server.asset_status = status
                with self.assertRaisesRegex(demo.DemoError, code) as raised:
                    self.client.request("POST", demo.assets.ASSET_API + "/apply", {"kind": "tool", "id": "test"})
                self.assertNotIn(TOKEN, str(raised.exception))
        self.assertTrue(all(path == demo.assets.ASSET_API + "/apply" for _, path, _, _ in self.server.seen))

    def test_response_size_and_url_boundaries(self):
        with patch.object(demo, "MAX_RESPONSE", 4):
            with self.assertRaisesRegex(demo.DemoError, "api_response_too_large"):
                self.client.request("GET", "/api/version")
        for path in ["https://example.invalid/api", "//example.invalid/api", "/api/../secret"]:
            with self.assertRaisesRegex(demo.DemoError, "api_path_invalid"):
                self.client.request("GET", path)
        for url in ["http://user:secret@example.invalid", "http://localhost?x=1", "file:///tmp/demo"]:
            with self.assertRaisesRegex(demo.DemoError, "webui_url_invalid"):
                demo.base_url(url)




class OperatorTests(unittest.TestCase):
    def test_token_storage_is_dpapi_and_scoped_to_webui_url(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"state_root": directory}
            url = "http://127.0.0.1:8080"
            with patch.object(demo.upgrade.manager.states, "_protect", return_value=b"CIPHERTEXT") as protect:
                demo.save_token(config, url, TOKEN)
            plaintext = json.loads(protect.call_args.args[0])
            self.assertEqual(plaintext, {"url": url, "token": TOKEN})
            self.assertEqual(demo.token_path(config, url).read_bytes(), b"CIPHERTEXT")
            with patch.object(demo.upgrade.manager.states, "_unprotect", return_value=json.dumps(plaintext).encode()):
                self.assertEqual(demo.load_token(config, url), (TOKEN, False))
            self.assertNotEqual(demo.token_path(config, url), demo.token_path(config, url + "/other"))
            self.assertFalse((Path(directory) / "github-update.dpapi").exists())

    def test_model_list_pagination_and_unique_existing_ees(self):
        client = Mock()
        client.request.side_effect = [
            {"items": [{"id": "a", "name": "A", "base_model_id": "base"},
                       {"id": "b", "name": "B", "base_model_id": "base"}], "total": 3},
            {"items": [{"id": "kept", "name": "EES 통합 Assistant", "base_model_id": "base"}], "total": 3}]
        self.assertEqual(demo.select_ees(client), "kept")
        self.assertEqual(client.request.call_count, 2)

    def test_ambiguous_models_require_one_selection(self):
        client = Mock()
        client.request.return_value = {"items": [
            {"id": "a", "name": "EES 통합 Assistant", "base_model_id": "base"},
            {"id": "b", "name": "EES 통합 Assistant", "base_model_id": "base"}], "total": 2}
        with patch.object(demo.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(demo.DemoError, "ees_model_selection_required"):
                demo.select_ees(client)

    def test_connection_override_does_not_reuse_other_servers_model(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"state_root": directory, "host": "127.0.0.1", "port": 8080}
            Path(directory, "demo-connection.json").write_text(json.dumps({"url": "http://127.0.0.1:8080", "ees_model_id": "old"}), encoding="utf-8")
            _, value = demo.connection(config, argparse.Namespace(webui_url="https://example.invalid", ees_model_id=None, ca_file=None))
            self.assertIsNone(value["ees_model_id"])



    def test_error_report_contains_only_short_labels(self):
        output = io.StringIO()
        with patch.object(demo.upgrade.manager, "save_operation", return_value=True), redirect_stdout(output):
            demo.report(Path("synthetic.json"), {"source_commit": HEAD, "changed": 2,
                        "stage": "apply_assets", "code": "api_request_failed", "next": "inspect_local_result"}, failed=True)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn("changed=2", output.getvalue())
        self.assertNotIn(TOKEN, output.getvalue())

    def test_unconfirmed_write_is_not_reported_as_zero_changes(self):
        output = io.StringIO()
        with patch.object(demo.upgrade.manager, "save_operation", return_value=True), redirect_stdout(output):
            demo.report(Path("synthetic.json"), {"source_commit": HEAD, "changed": 0,
                        "pending": True, "stage": "apply_assets", "code": "webui_connection_failed",
                        "next": "inspect_local_result"}, failed=True)
        self.assertIn("changed=-", output.getvalue())
        self.assertIn("pending=true", output.getvalue())


@unittest.skipUnless(shutil.which("git"), "Git is required for canonical checkout boundaries")
class TrialSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("remote", "add", "origin", demo.upgrade.REPOSITORY + ".git")
        (self.repo / "source.txt").write_text("reviewed source\n", encoding="utf-8")
        self.git("add", "source.txt")
        self.git("commit", "-m", "synthetic [skip ci]")
        self.head = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.head)
        self.root_patch = patch.object(demo.upgrade, "ROOT", self.repo)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.repo), *arguments], capture_output=True,
                              text=True, encoding="utf-8", check=True, timeout=10).stdout.strip()

    def assert_trial_stops(self, code, commit=None):
        # Shared canonical-source helper still protects deployment operations;
        # retired ApplyDemo itself now refuses before inspecting any checkout.
        with self.assertRaises((demo.DemoError, demo.upgrade.UpgradeError)) as caught:
            demo.trial_checkout(commit or self.head)
        self.assertEqual(caught.exception.code, code)


    def test_trial_rejects_other_repository(self):
        self.git("remote", "set-url", "origin", "https://github.com/another/repo.git")
        self.assert_trial_stops("wrong_repository")

    def test_trial_rejects_non_main_checkout(self):
        self.git("checkout", "-b", "local-feature")
        self.assert_trial_stops("main_required")

    def test_trial_rejects_dirty_tracked_source(self):
        (self.repo / "source.txt").write_text("unreviewed edit\n", encoding="utf-8")
        self.assert_trial_stops("local_changes")

    def test_trial_rejects_wrong_pinned_commit(self):
        self.assert_trial_stops("checkout_changed", HEAD)

    def test_trial_rejects_locally_committed_main_not_matching_fetched_main(self):
        (self.repo / "source.txt").write_text("local commit\n", encoding="utf-8")
        self.git("commit", "-am", "local [skip ci]")
        self.assert_trial_stops("trial_main_mismatch", self.git("rev-parse", "HEAD"))


    def test_trial_argument_rejects_abbreviation_and_release_bootstrap_mixing(self):
        for options in (["--trial-commit", self.head[:12]], ["--trial-commit", self.head.upper()],
                        ["--trial-commit", ""], ["--trial-commit", " "],
                        ["--trial-commit", self.head, "--reset-update-token"],
                        ["--trial-commit", self.head, "--prepared-head", self.head, "--wrapper-before", self.head]):
            with self.subTest(options=options), patch.object(demo.upgrade.manager.states, "load_config") as load:
                with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                    demo.main(["--config", "synthetic.json", *options])
                self.assertEqual(raised.exception.code, 2)
                load.assert_not_called()






if __name__ == "__main__":
    unittest.main()
