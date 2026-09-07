"""Offline Jira contracts; all identities, credentials and content are synthetic.

Transport is intercepted and DNS/socket access is forbidden. Passing these tests
does not establish live Jira authorization, WebUI encryption, or UI integration.
"""

import inspect
import asyncio
import io
import importlib.util
import json
import socket
import ssl
import threading
import unittest
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "agent-pack/skills/jira-read/scripts/jira_tool.py"
SPEC = importlib.util.spec_from_file_location("ees_jira_tests", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
BASE = "https://jira.example.invalid/jira"
PAT_A, PAT_B = "synthetic-only-token-a", "synthetic-only-token-b"


class Response:
    def __init__(self, value, status=200, content_type="application/json"):
        payload = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.body = io.BytesIO(payload)
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.body.close()

    def getcode(self):
        return self.status

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self.body.read(size)


def issue(key="SYSA-1", project="SYSA"):
    return {"id": "10001", "key": key, "fields": {
        "project": {"key": project, "name": "Synthetic system"},
        "summary": "Synthetic maintenance issue", "description": "Synthetic details",
        "status": {"name": "Open", "statusCategory": {"key": "new", "name": "To Do"}},
        "assignee": {"key": "synthetic-a", "displayName": "Synthetic A"}, "priority": {"name": "Medium"},
        "updated": "2026-01-02T00:00:00.000+0000", "created": "2026-01-01T00:00:00.000+0000",
        "duedate": None,
    }}


def query(request):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)


class JiraReadTests(unittest.TestCase):
    def setUp(self):
        self.tool = module.Tools()
        self.tool.valves.ENABLED = True
        self.tool.valves.JIRA_BASE_URL = BASE
        self.tool.valves.ALLOWED_PROJECTS = "SYSA,SYSB"
        self.tool.valves.MAX_RESULTS = 30
        self.calls, self.openers = [], []
        self.lock = threading.Lock()
        self.responder = self.normal_response

        def intercept(opener, request, *args, **kwargs):
            with self.lock:
                self.calls.append(request)
                self.openers.append(opener)
            return self.responder(request)

        for guard in (
            patch.object(module, "_encryption_enabled", return_value=True),
            patch("urllib.request.OpenerDirector.open", autospec=True, side_effect=intercept),
            patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK FORBIDDEN")),
            patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS FORBIDDEN")),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def user(self, pat=PAT_A, user_id="synthetic-a"):
        return {"id": user_id, "valves": self.tool.UserValves(PAT=pat)}

    def normal_response(self, request):
        if request.full_url.endswith("/myself"):
            return Response({"name": "synthetic-a", "key": "synthetic-a", "active": True})
        params = query(request)
        if "/search?" in request.full_url:
            if params.get("maxResults") == ["0"]:
                return Response({"total": 20 if "statusCategory" in params["jql"][0] else 53})
            start = int(params.get("startAt", ["0"])[0])
            total = 106 if all(p in params["jql"][0] for p in ("SYSA", "SYSB")) else 53
            return Response({"startAt": start, "maxResults": 30, "total": total,
                             "issues": [issue(f"SYSA-{n + 1}") for n in range(start, min(start + 30, total))]})
        return Response(issue())

    def run_tool(self, op="show_dashboard", **args):
        if op == "show_dashboard":
            args = {"project_key": "", "start_at": 0, **args}
        result = self.tool._run(op, self.user(), **args)
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result.get("ok"), bool)
        self.assertNotIn(PAT_A, json.dumps(result))
        return result

    def test_public_inputs_cannot_supply_jql_url_or_pat(self):
        names = {name for name, value in inspect.getmembers(module.Tools, inspect.iscoroutinefunction)
                 if not name.startswith("_")}
        self.assertEqual(names, {"jira_check_access", "jira_dashboard", "jira_get_issue"})
        for name in names:
            inputs = set(inspect.signature(getattr(module.Tools, name)).parameters)
            self.assertFalse(inputs & {"jql", "query", "url", "base_url", "pat", "token"})

    def test_invalid_project_or_paging_stops_before_requests(self):
        for value in ("SYSA2", "sysa", 'SYSA\" OR project = OTHER', "SYSA,SYSB", 1):
            with self.subTest(value=value):
                self.assertFalse(self.run_tool(project_key=value)["ok"])
        for value in (-1, True, "1"):
            with self.subTest(start_at=value):
                self.assertFalse(self.run_tool(start_at=value)["ok"])
        self.assertEqual(self.calls, [])

    def test_auth_preflight_failure_does_not_fetch_issues_or_counts(self):
        self.responder = lambda request: Response({}, status=401)
        self.assertFalse(self.run_tool()["ok"])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0].full_url.endswith("/rest/api/2/myself"))

    def test_disabled_missing_secret_or_unencrypted_context_is_closed(self):
        self.assertFalse(module.Tools().valves.ENABLED)
        for user in (None, {}, {"id": "synthetic-a", "valves": {"PAT": PAT_A}}, self.user(""), self.user("x\r\ny")):
            self.assertFalse(self.tool._run("check_access", user)["ok"])
        with patch.object(module, "_encryption_enabled", return_value=False):
            self.assertFalse(self.run_tool("check_access")["ok"])
        self.tool.valves.ENABLED = False
        self.assertFalse(self.run_tool("check_access")["ok"])
        self.assertEqual(self.calls, [])

    def test_arbitrary_endpoints_cannot_receive_credentials(self):
        for path in ("/rest/api/2/issue/SYSA-1/comment", "/rest/api/2/user", "https://elsewhere.example.invalid"):
            with self.assertRaises(module._ToolError):
                self.tool._request(self.tool.valves, BASE, PAT_A, path)
        self.assertEqual(self.calls, [])

    def test_missing_or_anonymous_auth_identity_is_not_success(self):
        for identity in ({}, {"active": True}, {"name": "anonymous", "active": False}):
            self.calls.clear()
            self.responder = lambda request, value=identity: Response(value)
            self.assertFalse(self.run_tool("check_access")["ok"])
            self.assertEqual(len(self.calls), 1)

    def test_dashboard_counts_do_not_derive_totals_from_issue_page(self):
        self.assertTrue(self.run_tool()["ok"])
        self.assertTrue(self.calls[0].full_url.endswith("/myself"))
        counts = [query(r) for r in self.calls if query(r).get("maxResults") == ["0"]]
        self.assertEqual(len(counts), 4)
        for project in ("SYSA", "SYSB"):
            project_counts = [q for q in counts if '"' + project + '"' in q["jql"][0]]
            self.assertEqual(len(project_counts), 2)
            self.assertEqual(sum("statusCategory" in q["jql"][0] for q in project_counts), 1)
            self.assertTrue(any("Done" in q["jql"][0] and "!=" in q["jql"][0] for q in project_counts))
        pages = [query(r) for r in self.calls if query(r).get("maxResults") == ["30"]]
        self.assertEqual(len(pages), 1)
        self.assertNotIn("description", pages[0].get("fields", [""])[0])

    def test_selected_project_does_not_query_other_projects(self):
        self.assertTrue(self.run_tool(project_key="SYSA")["ok"])
        searches = [query(r)["jql"][0] for r in self.calls if "jql" in query(r)]
        self.assertTrue(searches)
        self.assertTrue(all("SYSB" not in jql and '"SYSA"' in jql for jql in searches))

    def test_page_limit_and_next_page_preserve_full_count(self):
        first = self.run_tool(project_key="SYSA")
        self.assertEqual(first["summary"]["total"], 53)
        self.assertEqual(first["summary"]["open"], 20)
        self.assertEqual((len(first["issues"]), first["listing"]["next_start_at"]), (30, 30))
        second = self.run_tool(project_key="SYSA", start_at=30)
        self.assertEqual((len(second["issues"]), second["listing"]["next_start_at"]), (23, None))
        self.assertEqual(second["listing"]["total"], 53)

    def test_failed_count_is_unknown_and_does_not_pollute_successful_projects(self):
        for payload in ({}, {"total": None}, {"total": True}, {"total": -1}, {"total": "53"}, {"total": 53.0}):
            def respond(request):
                params = query(request)
                if params.get("maxResults") == ["0"] and '"SYSB"' in params["jql"][0]:
                    return Response(payload)
                return self.normal_response(request)
            self.responder = respond
            result = self.run_tool()
            bad = next(row for row in result["projects"] if row["key"] == "SYSB")
            self.assertEqual((bad["ok"], bad["total"], bad["open"]), (False, None, None))
            self.assertEqual(result["status"], "partial")
            self.assertIsNone(result["summary"]["total"])
            self.assertEqual(result["summary"]["available_total"], 53)
            self.assertEqual(result["scope"]["listing_project_keys"], ["SYSA"])

    def test_partial_scope_suppresses_cursor_until_first_page_recovery(self):
        def respond(request):
            params = query(request)
            if params.get("maxResults") == ["0"] and '"SYSB"' in params["jql"][0]:
                return Response({}, status=403)
            return self.normal_response(request)
        self.responder = respond
        partial = self.run_tool()
        self.assertTrue(partial["ok"])
        self.assertTrue(partial["listing"]["ok"])
        self.assertEqual(len(partial["issues"]), 30)
        self.assertEqual(partial["listing"]["total"], 53)
        self.assertIsNone(partial["listing"]["next_start_at"])
        self.assertEqual(partial["summary"]["available_total"], 53)
        self.assertIsNone(partial["summary"]["total"])
        self.assertIn("처음부터 조회", partial["notice"])
        partial_pages = [query(r) for r in self.calls if query(r).get("maxResults") == ["30"]]
        self.assertEqual(len(partial_pages), 1)
        self.assertEqual(partial_pages[0]["startAt"], ["0"])
        self.assertNotIn("SYSB", partial_pages[0]["jql"][0])

        self.responder = self.normal_response
        self.calls.clear()
        recovered = self.run_tool(start_at=0)
        self.assertEqual(recovered["status"], "complete")
        self.assertEqual(recovered["scope"]["listing_project_keys"], ["SYSA", "SYSB"])
        self.assertEqual(recovered["listing"]["next_start_at"], 30)
        recovered_pages = [query(r) for r in self.calls if query(r).get("maxResults") == ["30"]]
        self.assertEqual(len(recovered_pages), 1)
        self.assertEqual(recovered_pages[0]["startAt"], ["0"])
        self.assertIn("SYSB", recovered_pages[0]["jql"][0])

    def test_later_page_failure_never_applies_offset_to_reduced_scope(self):
        first = self.run_tool()
        self.assertEqual(first["listing"]["next_start_at"], 30)
        def respond(request):
            params = query(request)
            if params.get("maxResults") == ["0"] and '"SYSB"' in params["jql"][0]:
                return Response({}, status=403)
            return self.normal_response(request)
        self.responder = respond
        self.calls.clear()
        result = self.run_tool(start_at=first["listing"]["next_start_at"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"]["available_total"], 53)
        self.assertEqual(result["issues"], [])
        self.assertFalse(result["listing"]["ok"])
        self.assertIsNone(result["listing"]["next_start_at"])
        self.assertEqual(result["listing"]["error"]["code"], "page_scope_changed")
        self.assertIn("처음부터 조회", result["listing"]["error"]["message"])
        self.assertFalse(any(query(r).get("maxResults") == ["30"] for r in self.calls))

    def test_zero_counts_are_successful_and_distinct_from_unavailable(self):
        def respond(request):
            params = query(request)
            if params.get("maxResults") == ["0"]:
                return Response({"total": 0}) if '"SYSA"' in params["jql"][0] else Response({}, status=403)
            if "/search?" in request.full_url:
                return Response({"total": 0, "startAt": 0, "issues": []})
            return self.normal_response(request)
        self.responder = respond
        result = self.run_tool()
        rows = {row["key"]: row for row in result["projects"]}
        self.assertEqual((rows["SYSA"]["ok"], rows["SYSA"]["total"]), (True, 0))
        self.assertEqual((rows["SYSB"]["ok"], rows["SYSB"]["total"]), (False, None))
        self.assertEqual(result["listing"]["returned"], 0)

    def test_invalid_listing_cannot_return_untrusted_page_rows(self):
        valid = {"total": 53, "startAt": 0, "issues": [issue()]}
        payloads = [{**valid, "total": True}, {**valid, "startAt": 1},
                    {**valid, "issues": [issue()] * 31}, {**valid, "issues": []},
                    {**valid, "issues": [issue("OTHER-1", "OTHER")]},
                    {**valid, "issues": [issue("SYSA-1", "SYSB")]},
                    {**valid, "issues": [issue(), issue()]}]
        for payload in payloads:
            def respond(request):
                if query(request).get("maxResults") == ["30"]:
                    return Response(payload)
                return self.normal_response(request)
            self.responder = respond
            result = self.run_tool(project_key="SYSA")
            self.assertFalse(result["listing"]["ok"])
            self.assertEqual(result["issues"], [])

    def test_public_issue_wrapper_reads_text_with_fixed_source(self):
        result = json.loads(asyncio.run(self.tool.jira_get_issue("SYSA-1", __user__=self.user())))
        self.assertTrue(result["ok"])
        self.assertEqual(result["description"], "Synthetic details")
        self.assertEqual(result["issue"]["url"], BASE + "/browse/SYSA-1")
        self.assertEqual(len(self.calls), 3)
        for present in (False, True):
            payload = issue()
            payload["fields"].pop("description")
            if present:
                payload["fields"]["description"] = None
            self.responder = lambda request: self.normal_response(request) if request.full_url.endswith("/myself") else Response(payload)
            result = self.run_tool("get_issue", issue_key="SYSA-1")
            self.assertEqual(result["ok"], present)
            self.assertEqual(result.get("description") if present else result["error"]["code"], "" if present else "unexpected_response")

    def test_field_availability_and_assignee_identity_do_not_guess(self):
        for source, target in (("assignee", "assignee"), ("priority", "priority"), ("duedate", "due_date")):
            for mode in ("missing", "null", "malformed"):
                payload = issue()
                payload["fields"].pop(source)
                if mode != "missing":
                    payload["fields"][source] = None if mode == "null" else 42
                result = self.tool._issue_info(payload, BASE, ["SYSA"])
                self.assertEqual(result[target + "_known"], mode == "null", (source, mode))
                self.assertIsNone(result[target])
        for identity, source in (("synthetic-a", "key"), ("synthetic-b", "key"), ("synthetic-c", "name")):
            payload = issue()
            payload["fields"]["assignee"] = {source: identity, "displayName": "Same synthetic name"}
            result = self.tool._issue_info(payload, BASE, ["SYSA"])
            self.assertTrue(result["assignee_known"])
            self.assertEqual(result["assignee_id"], identity)
            self.assertEqual(result["assignee"], "Same synthetic name")

    def test_moved_or_mismatched_issue_stops_before_description_fetch(self):
        for key, project in (("OTHER-1", "OTHER"), ("SYSA-2", "SYSA"), ("SYSA-1", "SYSB")):
            self.calls.clear()
            def respond(request):
                if request.full_url.endswith("/myself"):
                    return self.normal_response(request)
                return Response(issue(key, project))
            self.responder = respond
            self.assertFalse(self.run_tool("get_issue", issue_key="SYSA-1")["ok"])
            metadata = [r for r in self.calls if "/issue/" in r.full_url]
            self.assertEqual(len(metadata), 1)
            self.assertNotIn("description", query(metadata[0]).get("fields", [""])[0])

    def test_issue_scope_is_checked_before_and_after_metadata_request(self):
        for key in ("OTHER-1", "SYSA-0", "SYSA-1/../../myself", 1):
            self.assertFalse(self.run_tool("get_issue", issue_key=key)["ok"])
        self.assertEqual(self.calls, [])
        def respond(request):
            if "description" in query(request).get("fields", [""])[0]:
                return Response(issue("OTHER-1", "OTHER"))
            return self.normal_response(request)
        self.responder = respond
        result = self.run_tool("get_issue", issue_key="SYSA-1")
        self.assertFalse(result["ok"])
        self.assertNotIn("description", result)
        self.assertEqual(len(self.calls), 3)

    def test_request_fixed_get_tls_and_credential_scope(self):
        self.assertTrue(self.run_tool("check_access")["ok"])
        request = self.calls[0]
        self.assertEqual(request.full_url, BASE + "/rest/api/2/myself")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + PAT_A)
        self.assertNotIn(PAT_A, request.full_url)
        tls = next(h for h in self.openers[0].handlers if isinstance(h, urllib.request.HTTPSHandler))
        self.assertEqual(tls._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(tls._context.check_hostname)
        redirect = next(h for h in self.openers[0].handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
        with self.assertRaises(module._ToolError):
            redirect.redirect_request(request, Response(b""), 302, "Found", {}, "https://elsewhere.example.invalid")

    def test_nonjson_oversize_and_bad_payload_are_errors(self):
        responses = [Response(b"not-json"), Response([]), Response(None),
                     Response({}, content_type="text/html"),
                     Response(b"x" * (self.tool.valves.MAX_RESPONSE_BYTES + 1))]
        for response in responses:
            self.responder = lambda request, current=response: current
            self.assertFalse(self.run_tool("check_access")["ok"])
        self.assertEqual(responses[-1].read_sizes, [self.tool.valves.MAX_RESPONSE_BYTES + 1])

    def test_reflected_credential_is_removed_before_content_processing(self):
        self.responder = lambda request: Response({"summary": PAT_A, "fields": {"description": ["text " + PAT_A]}})
        result = self.tool._request(self.tool.valves, BASE, PAT_A, "/rest/api/2/issue/SYSA-1")
        self.assertNotIn(PAT_A, json.dumps(result))
        self.assertIn("text ", result["fields"]["description"][0])

    def test_connection_error_does_not_serialize_sensitive_exception(self):
        def fail(request):
            raise OSError("sensitive error " + PAT_A)
        self.responder = fail
        self.assertFalse(self.run_tool("check_access")["ok"])

    def test_concurrent_credentials_are_request_local_and_redacted(self):
        rendezvous = threading.Barrier(2)
        def respond(request):
            rendezvous.wait(timeout=5)
            pat = request.get_header("Authorization").split(" ", 1)[1]
            return Response({"name": "synthetic", "key": "synthetic", "active": True, "displayName": pat})
        self.responder = respond
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda pair: self.tool._run("check_access", self.user(*pair)),
                                     ((PAT_A, "synthetic-a"), (PAT_B, "synthetic-b"))))
        self.assertTrue(all(value["ok"] for value in outcomes))
        self.assertEqual({r.get_header("Authorization") for r in self.calls}, {"Bearer " + PAT_A, "Bearer " + PAT_B})
        for pat in (PAT_A, PAT_B):
            self.assertNotIn(pat, json.dumps(outcomes))
            self.assertNotIn(pat, repr(vars(self.tool)))
        self.assertEqual(set(vars(self.tool)), {"valves"})


if __name__ == "__main__":
    unittest.main()
