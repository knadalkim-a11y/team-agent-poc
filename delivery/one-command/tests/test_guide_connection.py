import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ship"))
import guide_connection as guide


BASE = "https://docs.example.test/wiki/rest/api"
PAGE = {"id": "52", "type": "page", "title": "Fixture title"}


def response(status=200, payload=None):
    reply = MagicMock()
    reply.status = status
    reply.read.return_value = json.dumps(payload).encode()
    return reply


class ConnectionTest(unittest.TestCase):
    def test_supplied_origin_and_context(self):
        self.assertEqual(guide.normalized_base(BASE + "/"), BASE)
        self.assertEqual(guide.normalized_base("https://DOCS.example.test:8443/wiki/rest/api"),
                         "https://docs.example.test:8443/wiki/rest/api")
        for bad in ("http://x.test/rest/api", "https://alice@x.test/rest/api", "https://x.test:/rest/api",
                    "https://x.test:65536/rest/api", "https://x.test:0/rest/api", BASE + "?", BASE + "#",
                    "https://x.test//rest/api", "https://x.test/%2e/rest/api", "https://x.test/../rest/api",
                    "https://x.test/rest/api\n", "https://x.test/rest/api?tenant=other"):
            with self.subTest(bad=bad), self.assertRaises(guide.GuideConnectionError):
                guide.normalized_base(bad)

    def test_two_fetches_and_child_environment_only(self):
        old = {"other": {"base_url": "https://second.example.test/tools"}}
        with patch.dict(os.environ, {guide.REGISTRY: json.dumps(old)}, clear=True), \
                patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", side_effect=["52", "member"]), \
                patch.object(guide, "getpass", return_value="example-pat"), patch.object(guide, "HTTPSConnection") as http, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            conn = http.return_value
            conn.getresponse.side_effect = [response(200, PAGE), response(200, {"results": []})]
            child = guide.connect(BASE, {"env_names": []})
            self.assertEqual(os.environ[guide.REGISTRY], json.dumps(old))
            self.assertNotIn(guide.AUTH, os.environ)
            self.assertEqual(child[guide.AUTH], "Bearer example-pat")
            self.assertIn(BASE, output.getvalue())
            self.assertNotIn("example-pat", output.getvalue())
            self.assertNotIn(PAGE["title"], output.getvalue())
            self.assertIn("HTTP 200", output.getvalue())
            self.assertEqual(json.loads(child[guide.REGISTRY])["other"], old["other"])
            service = json.loads(child[guide.REGISTRY])[guide.PILOT]
            self.assertEqual(service["base_url"], BASE + "/content")
            self.assertEqual(service["user_credential_headers"], {"member": {"Authorization": guide.AUTH}})
            self.assertEqual(service["actor_ids"], ["member"])
            self.assertEqual([call.args for call in conn.request.call_args_list],
                             [("GET", "/wiki/rest/api/content/52"), ("GET", "/wiki/rest/api/content/52/child/page?limit=5")])
            for request, connect in zip(conn.request.call_args_list, http.call_args_list):
                self.assertEqual(connect.args, ("docs.example.test", 443))
                self.assertTrue(connect.kwargs["context"].check_hostname)
                self.assertEqual(request.kwargs["headers"]["Authorization"], child[guide.AUTH])

    def test_stop_on_redirect_permission_or_invalid_response(self):
        for status in (302, 401, 403, 404):
            with self.subTest(status=status), patch.object(guide, "HTTPSConnection") as http:
                http.return_value.getresponse.return_value = response(status, "server secret")
                with self.assertRaisesRegex(guide.GuideConnectionError, "HTTP " + str(status)) as raised:
                    guide.probe(BASE, "52", "Bearer super-secret")
                self.assertNotIn("secret", str(raised.exception))
                self.assertEqual(http.return_value.request.call_count, 1)
                http.return_value.close.assert_called_once()
        for first, second in (({**PAGE, "id": "other"}, {}), (PAGE, {"results": [PAGE] * 6}),
                              (PAGE, {"results": [{**PAGE, "type": "comment"}]}), (PAGE, {})):
            with self.subTest(first=first, second=second), patch.object(guide, "fetch_page", side_effect=[first, second]):
                with self.assertRaises(guide.GuideConnectionError):
                    guide.probe(BASE, "52", "opaque")

    def test_registry_overlap_idempotence_and_saved_manager_settings(self):
        initial = guide.registry_entry("{}", BASE, "one")
        self.assertEqual(guide.registry_entry(initial, BASE, "one"), initial)
        with self.assertRaises(guide.GuideConnectionError):
            guide.registry_entry(initial, BASE, "two")
        for raw in ({"other": {"base_url": BASE}}, {"other": {"base_url": BASE + "/content/1"}},
                    {"other": {"base_url": BASE, "credential_headers": {"Authorization": guide.AUTH.lower()}}}):
            with self.assertRaises(guide.GuideConnectionError):
                guide.registry_entry(json.dumps(raw), BASE, "one")
        for key in (guide.REGISTRY.lower(), guide.AUTH):
            with patch("builtins.input", side_effect=AssertionError), self.assertRaises(guide.GuideConnectionError):
                guide.connect(BASE, {"env_names": [key]})
        with patch.dict(os.environ, {guide.AUTH: "existing secret"}, clear=True), patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", side_effect=["52", "member"]), patch.object(guide, "getpass", return_value="new-secret"), \
                patch.object(guide, "probe", side_effect=AssertionError), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(guide.GuideConnectionError):
            guide.connect(BASE, {"env_names": []})

    def test_unknown_actor_login_stays_on_loopback(self):
        with patch("builtins.input", return_value="test@example.test"), patch.object(guide, "getpass", return_value="test-input"), \
                patch.object(guide, "HTTPConnection") as http:
            http.return_value.getresponse.return_value = response(200, {"id": "member", "token": "example-session"})
            self.assertEqual(guide.login_actor({"host": "third.example.test", "port": 8080}), "member")
            self.assertEqual(http.call_args.args, ("127.0.0.1", 8080))
            args = http.return_value.request.call_args.args
            self.assertEqual(args[:2], ("POST", "/api/v1/auths/signin"))
            self.assertEqual(json.loads(args[2]), {"email": "test@example.test", "password": "test-input"})

    def test_noninteractive_or_invalid_page_stops_before_secret(self):
        with patch.object(sys.stdin, "isatty", return_value=False), patch.object(guide, "getpass", side_effect=AssertionError), \
                self.assertRaises(guide.GuideConnectionError):
            guide.connect(BASE, {"env_names": []})
        with patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="../../elsewhere"), \
                patch.object(guide, "getpass", side_effect=AssertionError), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(guide.GuideConnectionError):
            guide.connect(BASE, {"env_names": []})
