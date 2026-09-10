"""Operator entry tests use a local synthetic HTTP API; no WebUI or credentials."""

import argparse
from contextlib import nullcontext, redirect_stdout
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
        payload = ({"version": "0.11.3+ees.2"} if self.path == "/api/version"
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
        self.client = demo.WebUIClient(self.url, TOKEN, timeout=2)

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

    def test_apply_uses_version_then_admin_then_core_without_server_control(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"host": "127.0.0.1", "port": self.server.server_port, "state_root": directory}
            args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
            progress = {}
            with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade, "checkout"),
                  patch.object(demo, "load_token", return_value=(TOKEN, False)),
                  patch.object(demo.assets, "apply_assets", return_value={"changed": 8, "source_commit": HEAD}) as core,
                  patch.object(demo.upgrade.manager, "stop_registered") as stop,
                  patch.object(demo.upgrade.manager, "start_selected") as start):
                result = demo.apply(config, args, HEAD, progress)
            self.assertEqual(result["next"], "new_chat")
            self.assertEqual([v[1] for v in self.server.seen], ["/api/version", "/api/v1/auths/", "/api/v1/models/model?id=existing"])
            self.assertIsNone(self.server.seen[0][2])
            self.assertEqual(core.call_args.args[3:], ("existing", HEAD))
            saved = json.loads((Path(directory) / "demo-connection.json").read_text(encoding="utf-8"))
            self.assertNotIn(TOKEN, json.dumps(saved))
            stop.assert_not_called()
            start.assert_not_called()

    def test_first_application_failure_keeps_validated_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"host": "127.0.0.1", "port": self.server.server_port, "state_root": directory}
            args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
            with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                  patch.object(demo.upgrade, "checkout"),
                  patch.object(demo, "load_token", return_value=(TOKEN, False)),
                  patch.object(demo.assets, "apply_assets", side_effect=demo.DemoError("api_request_failed"))):
                with self.assertRaises(demo.DemoError):
                    demo.apply(config, args, HEAD, {})
            saved = json.loads(Path(directory, "demo-connection.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["ees_model_id"], "existing")
            self.assertEqual(saved["url"], self.url)


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

    def test_version_or_admin_failure_cannot_write_assets(self):
        for responses, code in [([{"version": "9.0"}], "unsupported_webui_version"),
                                ([{"version": "0.11.3"}, {"role": "user"}], "webui_administrator_required")]:
            with tempfile.TemporaryDirectory() as directory:
                config = {"state_root": directory, "host": "127.0.0.1", "port": 8080}
                args = argparse.Namespace(webui_url=None, ees_model_id="existing", ca_file=None, reset_token=False)
                client = Mock()
                client.request.side_effect = responses
                with (patch.object(demo.upgrade.manager, "locked", return_value=nullcontext()),
                      patch.object(demo.upgrade, "checkout"),
                      patch.object(demo, "WebUIClient", return_value=client),
                      patch.object(demo, "load_token", return_value=(TOKEN, False)),
                      patch.object(demo.assets, "apply_assets") as core):
                    with self.assertRaisesRegex(demo.DemoError, code):
                        demo.apply(config, args, HEAD, {})
                core.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
