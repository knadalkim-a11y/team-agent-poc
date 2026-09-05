"""Offline contract/security tests for the Open WebUI Confluence read Tool.

No test may contact Confluence, DNS, or any other network service. Every token,
URL, document and user in this file is synthetic. These tests do not establish
that an installed Open WebUI encrypts its database or enforces real Confluence
permissions; those are separate onsite acceptance checks.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import io
import json
import re
import socket
import ssl
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch


TOOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent-pack/skills/confluence-read/scripts/confluence_tool.py"
)
SPEC = importlib.util.spec_from_file_location("ees_confluence_test_target", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool_module)

BASE_URL = "https://confluence.example.invalid/wiki"
TOKEN_A = "test-only-pat-user-a-do-not-use"
TOKEN_B = "test-only-pat-user-b-do-not-use"


def header_map(**values):
    headers = Message()
    for key, value in values.items():
        headers[key.replace("_", "-")] = str(value)
    return headers


class FakeResponse:
    def __init__(self, payload, *, status=200, content_type="application/json", url=""):
        if isinstance(payload, bytes):
            self.payload = payload
        else:
            self.payload = json.dumps(payload).encode("utf-8")
        self.status = status
        self.code = status
        self.headers = header_map(Content_Type=content_type)
        self.url = url
        self._body = io.BytesIO(self.payload)
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._body.close()

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self._body.read(size)


def page(page_id="123", space="EES", *, title="Synthetic equipment guide", body=True):
    data = {
        "id": str(page_id),
        "type": "page",
        "status": "current",
        "title": title,
        "space": {"key": space},
        "version": {"number": 3},
        "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
    }
    if body:
        data["body"] = {"storage": {"value": "<p>Synthetic safe content.</p>", "representation": "storage"}}
    return data


class ConfluenceReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = tool_module.Tools()
        self.tool.valves.ENABLED = True
        self.tool.valves.CONFLUENCE_BASE_URL = BASE_URL
        self.tool.valves.ALLOWED_SPACES = "EES,APC"
        self.calls = []
        self.openers = []
        self.call_lock = threading.Lock()
        self.responder = lambda request: FakeResponse({"type": "known", "username": "synthetic-a", "displayName": "Synthetic A"})

        self.encryption = patch.object(tool_module, "_encryption_enabled", return_value=True)
        self.encryption.start()
        self.addCleanup(self.encryption.stop)

        def intercept(_opener, request, *args, **kwargs):
            with self.call_lock:
                self.calls.append((request, args, kwargs))
                self.openers.append(_opener)
            return self.responder(request)

        self.open_patch = patch("urllib.request.OpenerDirector.open", autospec=True, side_effect=intercept)
        self.open_mock = self.open_patch.start()
        self.addCleanup(self.open_patch.stop)
        self.connect_patch = patch.object(socket.socket, "connect", side_effect=AssertionError("TEST FORBIDS NETWORK"))
        self.connect_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.dns_patch = patch.object(socket, "getaddrinfo", side_effect=AssertionError("TEST FORBIDS DNS"))
        self.dns_patch.start()
        self.addCleanup(self.dns_patch.stop)

    def user(self, token=TOKEN_A, user_id="user-a", **values):
        return {"id": user_id, "valves": self.tool.UserValves(PAT=token, **values)}

    def result(self, raw):
        self.assertIsInstance(raw, str, "Tool must return a JSON string")
        data = json.loads(raw)
        self.assertIsInstance(data.get("ok"), bool)
        for token in (TOKEN_A, TOKEN_B):
            self.assertNotIn(token, raw, "PAT must never appear in Tool output")
        return data

    def assert_error(self, raw):
        data = self.result(raw)
        self.assertFalse(data["ok"])
        self.assertIsInstance(data.get("error"), dict)
        self.assertTrue(data["error"].get("code"))
        self.assertTrue(data["error"].get("message"))
        return data

    def assert_no_calls(self):
        self.assertEqual(self.calls, [], "Rejected input must not create an HTTP request")

    def use_response(self, payload, **kwargs):
        self.responder = lambda _request: FakeResponse(payload, **kwargs)

    async def test_disabled_by_default(self):
        self.assertFalse(tool_module.Tools().valves.ENABLED)
        self.tool.valves.ENABLED = False
        self.assert_error(await self.tool.check_access(__user__=self.user()))
        self.assert_no_calls()

    async def test_missing_base_url_is_closed(self):
        self.tool.valves.CONFLUENCE_BASE_URL = ""
        self.assert_error(await self.tool.check_access(__user__=self.user()))
        self.assert_no_calls()

    async def test_empty_space_allowlist_is_closed(self):
        self.tool.valves.ALLOWED_SPACES = ""
        self.assert_error(await self.tool.search_pages("guide", __user__=self.user()))
        self.assert_no_calls()

    async def test_encryption_must_be_enabled(self):
        with patch.object(tool_module, "_encryption_enabled", return_value=False):
            self.assert_error(await self.tool.check_access(__user__=self.user()))
        self.assert_no_calls()

    async def test_user_and_token_are_required(self):
        for user in (None, {}, {"id": "user-a"}, self.user(token="")):
            with self.subTest(user_present=bool(user)):
                self.assert_error(await self.tool.check_access(__user__=user))
        self.assert_no_calls()

    async def test_anonymous_user_cannot_supply_token(self):
        self.assert_error(await self.tool.check_access(__user__={"valves": self.tool.UserValves(PAT=TOKEN_A)}))
        self.assert_no_calls()

    async def test_pat_cannot_inject_headers(self):
        self.assert_error(await self.tool.check_access(__user__=self.user(token="fake\r\nX-Injected: yes")))
        self.assert_no_calls()

    async def test_check_access_uses_fixed_get_and_request_scoped_pat(self):
        data = self.result(await self.tool.check_access(__user__=self.user()))
        self.assertTrue(data["ok"])
        self.assertEqual(len(self.calls), 1)
        request, _, kwargs = self.calls[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, BASE_URL + "/rest/api/user/current")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN_A)
        self.assertIsNone(request.data)
        self.assertNotIn(TOKEN_A, request.full_url)
        self.assertEqual(kwargs.get("timeout"), self.tool.valves.TIMEOUT_SECONDS)

    async def test_anonymous_upstream_identity_is_not_authenticated(self):
        self.use_response({"type": "anonymous"})
        self.assert_error(await self.tool.check_access(__user__=self.user()))

    async def test_tls_verification_and_no_redirect_handler_are_installed(self):
        self.assertTrue(self.result(await self.tool.check_access(__user__=self.user()))["ok"])
        handlers = self.openers[0].handlers
        https_handlers = [handler for handler in handlers if isinstance(handler, urllib.request.HTTPSHandler)]
        self.assertEqual(len(https_handlers), 1)
        context = https_handlers[0]._context
        self.assertIsNotNone(context)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        redirect_handlers = [handler for handler in handlers if isinstance(handler, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(redirect_handlers), 1)
        self.assertIsNot(type(redirect_handlers[0]), urllib.request.HTTPRedirectHandler)
        request = self.calls[0][0]
        redirect_body = FakeResponse(b"redirect")
        try:
            redirected = redirect_handlers[0].redirect_request(request, redirect_body, 302, "Found", {}, "https://evil.example.invalid/collect")
        except (urllib.error.HTTPError, tool_module._ToolError):
            redirected = None
        self.assertIsNone(redirected, "Redirect handler must refuse to forward credentials")

    async def test_proxy_environment_is_not_used_by_default(self):
        with patch.dict("os.environ", {"HTTPS_PROXY": "http://proxy.example.invalid:8080", "https_proxy": "http://proxy.example.invalid:8080", "NO_PROXY": "", "no_proxy": ""}):
            self.assertTrue(self.result(await self.tool.check_access(__user__=self.user()))["ok"])
        proxy_handlers = [handler for handler in self.openers[0].handlers if isinstance(handler, urllib.request.ProxyHandler)]
        self.assertTrue(all(not handler.proxies for handler in proxy_handlers))

    async def test_invalid_base_urls_are_rejected_before_network(self):
        urls = [
            "http://confluence.example.invalid/wiki",
            "file:///etc/passwd",
            "https://user:password@confluence.example.invalid/wiki",
            "https://confluence.example.invalid/wiki?target=other",
            "https://confluence.example.invalid/wiki#fragment",
            "https://confluence.example.invalid/wiki/../admin",
            "https://confluence.example.invalid/wiki\\admin",
            "https://confluence.example.invalid/wiki\nInjected",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.tool.valves.CONFLUENCE_BASE_URL = url
                self.assert_error(await self.tool.check_access(__user__=self.user()))
        self.assert_no_calls()

    async def test_search_uses_fixed_endpoint_and_bounded_limit(self):
        self.use_response({"results": [page(body=False)], "size": 1})
        raw = await self.tool.search_pages("equipment guide", space_key="EES", limit=5, __user__=self.user())
        self.assertTrue(self.result(raw)["ok"])
        self.assertIn("Synthetic equipment guide", raw)
        request = self.calls[0][0]
        parsed = urllib.parse.urlsplit(request.full_url)
        self.assertEqual(parsed.path, "/wiki/rest/api/content/search")
        self.assertEqual(parsed.netloc, "confluence.example.invalid")
        self.assertEqual(request.get_method(), "GET")
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(int(params["limit"][0]), 5)
        self.assertIn("EES", params["cql"][0])
        self.assertNotIn(TOKEN_A, request.full_url)

    async def test_invalid_search_input_never_issues_request(self):
        for query in ("", "   ", "x" * 5000, "guide\x00secret"):
            with self.subTest(query_length=len(query)):
                self.assert_error(await self.tool.search_pages(query, __user__=self.user()))
        self.assert_no_calls()

    async def test_search_cql_omits_unsupported_status_predicate(self):
        self.use_response({"results": [], "size": 0})
        self.assertTrue(self.result(await self.tool.search_pages("guide", __user__=self.user()))["ok"])
        cql = urllib.parse.parse_qs(urllib.parse.urlsplit(self.calls[0][0].full_url).query)["cql"][0]
        self.assertNotRegex(cql, r"(?i)\bstatus\s*(?:=|!=|IN\b)")
        self.assertRegex(cql, r"(?i)\btype\s*=\s*page\b")

    async def test_search_cql_injection_is_rejected_or_quoted_literal(self):
        self.use_response({"results": [], "size": 0})
        raw = await self.tool.search_pages('x" OR space="SECRET" OR text~"x', __user__=self.user())
        data = self.result(raw)
        if not data["ok"]:
            self.assert_no_calls()
            return
        cql = urllib.parse.parse_qs(urllib.parse.urlsplit(self.calls[0][0].full_url).query)["cql"][0]
        text_literals = re.findall(r'text\s*~\s*"((?:\\.|[^"\\])*)"', cql)
        self.assertEqual(len(text_literals), 1, "Search term must remain one CQL string literal")
        self.assertIn(r'\"SECRET\"', text_literals[0])
        outside_literals = re.sub(r'"(?:\\.|[^"\\])*"', '""', cql)
        self.assertNotIn("SECRET", outside_literals)

    async def test_unknown_space_never_issues_search(self):
        self.assert_error(await self.tool.search_pages("guide", space_key="SECRET", __user__=self.user()))
        self.assert_no_calls()

    async def test_invalid_space_cannot_modify_cql(self):
        for space in ('EES" OR space="SECRET', "EES) OR type=blogpost", "../SECRET"):
            with self.subTest(space=space):
                self.assert_error(await self.tool.search_pages("guide", space_key=space, __user__=self.user()))
        self.assert_no_calls()

    async def test_user_default_space_does_not_bypass_admin_allowlist(self):
        self.assert_error(await self.tool.search_pages("guide", __user__=self.user(DEFAULT_SPACE="SECRET")))
        self.assert_no_calls()

    async def test_page_id_rejects_urls_traversal_query_and_non_numeric(self):
        for page_id in ("", "abc", "../123", "123?expand=body.storage", "https://elsewhere.invalid/123", "123/456", "123\n"):
            with self.subTest(page_id=page_id):
                self.assert_error(await self.tool.get_page(page_id, __user__=self.user()))
        self.assert_no_calls()

    async def test_get_page_checks_metadata_before_loading_body(self):
        def respond(request):
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
            return FakeResponse(page(body=params.get("expand") != ["space"]))

        self.responder = respond
        raw = await self.tool.get_page("123", __user__=self.user())
        self.assertTrue(self.result(raw)["ok"])
        self.assertIn("Synthetic safe content", raw)
        self.assertEqual(len(self.calls), 2)
        expands = [urllib.parse.parse_qs(urllib.parse.urlsplit(call[0].full_url).query)["expand"][0] for call in self.calls]
        self.assertEqual(expands[0], "space")
        self.assertEqual(set(expands[1].split(",")), {"body.storage", "version", "space"})
        for request, _, _ in self.calls:
            self.assertEqual(urllib.parse.urlsplit(request.full_url).path, "/wiki/rest/api/content/123")
            self.assertEqual(request.get_method(), "GET")

    async def test_direct_page_id_in_forbidden_space_never_loads_body(self):
        self.use_response(page(space="SECRET", body=False))
        self.assert_error(await self.tool.get_page("123", __user__=self.user()))
        self.assertEqual(len(self.calls), 1)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.calls[0][0].full_url).query)
        self.assertEqual(params["expand"], ["space"])

    async def test_page_space_is_rechecked_on_body_response(self):
        counter = iter((page(space="EES", body=False), page(space="SECRET", title="DO NOT DISCLOSE")))
        self.responder = lambda _request: FakeResponse(next(counter))
        raw = await self.tool.get_page("123", __user__=self.user())
        self.assert_error(raw)
        self.assertNotIn("DO NOT DISCLOSE", raw)

    async def test_missing_page_space_is_closed(self):
        self.use_response({"id": "123", "type": "page", "title": "DO NOT DISCLOSE"})
        raw = await self.tool.get_page("123", __user__=self.user())
        self.assert_error(raw)
        self.assertNotIn("DO NOT DISCLOSE", raw)
        self.assertEqual(len(self.calls), 1)

    async def test_search_does_not_disclose_out_of_allowlist_results(self):
        self.use_response({"results": [page(space="SECRET", title="FORBIDDEN RESULT")], "size": 1})
        raw = await self.tool.search_pages("guide", __user__=self.user())
        self.result(raw)
        self.assertNotIn("FORBIDDEN RESULT", raw)

    async def test_remote_links_cannot_override_fixed_confluence_origin(self):
        data = page(body=False)
        data["_links"] = {"base": "https://evil.example.invalid", "webui": "https://evil.example.invalid/collect"}
        self.use_response({"results": [data], "size": 1})
        raw = await self.tool.search_pages("guide", __user__=self.user())
        self.result(raw)
        self.assertNotIn("evil.example.invalid", raw)

    async def test_upstream_http_errors_are_safe_and_not_retried(self):
        for status in (401, 403, 404, 429, 500, 502, 503):
            with self.subTest(status=status):
                self.calls.clear()

                def fail(request):
                    raise urllib.error.HTTPError(request.full_url, status, "private error " + TOKEN_A, header_map(Content_Type="text/html"), io.BytesIO(("private response " + TOKEN_A).encode()))

                self.responder = fail
                raw = await self.tool.check_access(__user__=self.user())
                self.assert_error(raw)
                self.assertNotIn("private response", raw)
                self.assertNotIn("private error", raw)
                self.assertEqual(len(self.calls), 1)

    async def test_redirect_is_not_followed_and_does_not_expose_location(self):
        def redirect(request):
            raise urllib.error.HTTPError(request.full_url, 302, "Found", header_map(Location="https://evil.example.invalid/?secret=" + TOKEN_A), io.BytesIO(b"redirect"))

        self.responder = redirect
        raw = await self.tool.check_access(__user__=self.user())
        self.assert_error(raw)
        self.assertNotIn("evil.example.invalid", raw)
        self.assertEqual(len(self.calls), 1)

    async def test_network_timeout_and_tls_failures_do_not_reflect_exception(self):
        for error in (TimeoutError(TOKEN_A), urllib.error.URLError("certificate failure " + TOKEN_A), ConnectionError(TOKEN_A)):
            with self.subTest(error_type=type(error).__name__):
                def fail(_request):
                    raise error

                self.responder = fail
                self.assert_error(await self.tool.check_access(__user__=self.user()))

    async def test_malformed_json_is_safe_failure(self):
        self.use_response(b'{"broken":')
        self.assert_error(await self.tool.check_access(__user__=self.user()))

    async def test_html_login_page_is_not_accepted_as_api_response(self):
        self.use_response(b"<html>Corporate login</html>", content_type="text/html")
        self.assert_error(await self.tool.check_access(__user__=self.user()))

    async def test_unexpected_json_shape_is_safe_failure(self):
        for payload in ([], None, "text"):
            with self.subTest(payload=payload):
                self.use_response(payload)
                self.assert_error(await self.tool.check_access(__user__=self.user()))

    async def test_response_bytes_are_bounded(self):
        self.tool.valves.MAX_RESPONSE_BYTES = 1024
        response = FakeResponse(b" " * 2048)
        self.responder = lambda _request: response
        self.assert_error(await self.tool.check_access(__user__=self.user()))
        self.assertTrue(response.read_sizes)
        self.assertTrue(all(0 < size <= 1025 for size in response.read_sizes), "Reads must be size-bounded")

    async def test_no_shared_pat_fallback_or_credential_cache(self):
        self.assertTrue(self.result(await self.tool.check_access(__user__=self.user()))["ok"])
        self.assert_error(await self.tool.check_access(__user__={"id": "user-b"}))
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(TOKEN_A, repr(self.tool.__dict__))

    async def test_concurrent_users_get_separate_request_headers(self):
        users = [self.user(TOKEN_A, "user-a"), self.user(TOKEN_B, "user-b")]
        raws = await asyncio.gather(*(self.tool.check_access(__user__=user) for user in users * 4))
        for raw in raws:
            self.assertTrue(self.result(raw)["ok"])
        authorizations = [call[0].get_header("Authorization") for call in self.calls]
        self.assertEqual(authorizations.count("Bearer " + TOKEN_A), 4)
        self.assertEqual(authorizations.count("Bearer " + TOKEN_B), 4)
        self.assertEqual(len({id(call[0]) for call in self.calls}), 8)
        self.assertNotIn(TOKEN_A, repr(self.tool.__dict__))
        self.assertNotIn(TOKEN_B, repr(self.tool.__dict__))

    async def test_concurrent_search_results_remain_user_specific(self):
        def respond(request):
            authorization = request.get_header("Authorization")
            if authorization == "Bearer " + TOKEN_A:
                data = page("111", title="USER_A_PRIVATE_DOCUMENT", body=False)
            elif authorization == "Bearer " + TOKEN_B:
                data = page("222", title="USER_B_PRIVATE_DOCUMENT", body=False)
            else:
                raise AssertionError("Unexpected authentication header")
            return FakeResponse({"results": [data], "size": 1})

        self.responder = respond
        users = [self.user(TOKEN_A, "user-a"), self.user(TOKEN_B, "user-b")] * 4
        results = await asyncio.gather(*(self.tool.search_pages("same search", __user__=user) for user in users))
        for user, raw in zip(users, results):
            self.assertTrue(self.result(raw)["ok"])
            if user["id"] == "user-a":
                self.assertIn("USER_A_PRIVATE_DOCUMENT", raw)
                self.assertNotIn("USER_B_PRIVATE_DOCUMENT", raw)
            else:
                self.assertIn("USER_B_PRIVATE_DOCUMENT", raw)
                self.assertNotIn("USER_A_PRIVATE_DOCUMENT", raw)
        self.assertEqual(len(self.calls), 8)

    async def test_repeat_reads_make_fresh_requests(self):
        self.use_response({"results": [page(body=False)], "size": 1})
        for _ in range(2):
            self.assertTrue(self.result(await self.tool.search_pages("guide", __user__=self.user()))["ok"])
        self.assertEqual(len(self.calls), 2, "No shared page/result cache is allowed in this POC")

    async def test_pat_reflected_by_upstream_is_not_returned(self):
        self.use_response({"results": [page(title="reflected " + TOKEN_A, body=False)], "size": 1})
        self.result(await self.tool.search_pages("guide", __user__=self.user()))

    async def test_title_boundary_does_not_reveal_partial_pat(self):
        self.use_response({"results": [page(title="x" * 490 + TOKEN_A, body=False)], "size": 1})
        raw = await self.tool.search_pages("guide", __user__=self.user())
        data = self.result(raw)
        self.assertTrue(data["ok"])
        self.assertNotIn(TOKEN_A[:10], raw, "Redaction must run before the 500-character title cutoff")
        self.assertLessEqual(len(data["results"][0]["title"]), 500)

    async def test_body_boundary_does_not_reveal_partial_pat(self):
        self.tool.valves.MAX_CONTENT_CHARS = 256
        data = page()
        data["body"]["storage"]["value"] = "<p>" + "x" * 246 + TOKEN_A + "</p>"
        self.use_response(data)
        raw = await self.tool.get_page("123", __user__=self.user())
        result = self.result(raw)
        self.assertTrue(result["ok"])
        self.assertNotIn(TOKEN_A[:10], raw, "Redaction must run before body truncation")
        self.assertLessEqual(len(result["content"]), 256)

    async def test_html_entity_encoded_pat_is_redacted_before_body_cutoff(self):
        self.tool.valves.MAX_CONTENT_CHARS = 256
        encoded_pat = "".join(f"&#{ord(character)};" for character in TOKEN_A)
        data = page()
        data["body"]["storage"]["value"] = "<p>" + "x" * 246 + encoded_pat + "</p>"
        self.use_response(data)
        raw = await self.tool.get_page("123", __user__=self.user())
        result = self.result(raw)
        self.assertTrue(result["ok"])
        self.assertNotIn(TOKEN_A[:10], raw, "HTML-decoded content must be redacted before truncation")
        self.assertLessEqual(len(result["content"]), 256)

    def test_only_three_read_functions_are_exposed(self):
        public = {name for name, _method in inspect.getmembers(tool_module.Tools, inspect.isfunction) if not name.startswith("_")}
        self.assertEqual(public, {"check_access", "search_pages", "get_page"})
        for name in public:
            parameters = inspect.signature(getattr(tool_module.Tools, name)).parameters
            self.assertFalse({"pat", "token", "url", "base_url", "http_method", "sql", "cql"} & set(parameters))

    def test_pat_field_is_ui_masked(self):
        schema = self.tool.UserValves.model_json_schema()
        self.assertEqual(schema["properties"]["PAT"].get("format"), "password")
        self.assertEqual(schema["properties"]["PAT"].get("input", {}).get("type"), "password")


if __name__ == "__main__":
    unittest.main()
