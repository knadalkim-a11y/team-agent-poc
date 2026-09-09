"""Synthetic GitHub responses exercise trust boundaries without a live token."""

import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
import warnings
import zipfile

from scripts import ees_update_download as download


HEAD = "a" * 40
OLDER = "b" * 40
TOKEN = "synthetic-token-do-not-use"
STORAGE = "https://productionresultssa1.blob.core.windows.net/archive?sig=synthetic-signed-url"


def run(commit=HEAD, run_id=10):
    return {"id": run_id, "workflow_id": 25, "path": download.WORKFLOW_PATH,
            "head_sha": commit, "head_branch": "main", "event": "push",
            "status": "completed", "conclusion": "success",
            "repository": {"id": 123, "full_name": download.REPOSITORY},
            "head_repository": {"id": 123, "full_name": download.REPOSITORY}}


def artifact(commit=HEAD, artifact_id=100, run_id=10):
    return {"id": artifact_id, "name": "ees-program-" + commit,
            "expired": False, "digest": "sha256:" + "0" * 64, "size_in_bytes": 1,
            "workflow_run": {"id": run_id, "head_sha": commit, "head_branch": "main",
                             "repository_id": 123, "head_repository_id": 123}}


class Api:
    def __init__(self, artifacts=None, head_run=None, runs=None):
        self.artifacts = [artifact()] if artifacts is None else artifacts
        self.head_run = run() if head_run is None else head_run
        self.runs = {10: run()} if runs is None else runs
        self.paths = []

    def json(self, path):
        self.paths.append(path)
        if path.endswith("/workflows/ees-delivery.yml"):
            return {"id": 25, "path": download.WORKFLOW_PATH}
        if "/workflows/ees-delivery.yml/runs?" in path:
            return {"workflow_runs": [self.head_run]}
        if "/actions/artifacts?" in path:
            page = int(path.rsplit("=", 1)[1])
            return {"artifacts": self.artifacts[(page - 1) * 100:page * 100]}
        return self.runs[int(path.rsplit("/", 1)[1])]


class Response(io.BytesIO):
    def __init__(self, content=b"", status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}


def inner_zip(commit=HEAD, branding=True):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"source_commit": commit,
                         "source_dirty": False, "branding": {} if branding else None}))
        if branding:
            archive.writestr("branding/manifest.json", "{}")
    return buffer.getvalue()


def outer_zip(inner=None, filename=None, mode=None, duplicate=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        entry = zipfile.ZipInfo(filename or "EES-demo-" + HEAD[:12] + ".zip")
        if mode is not None:
            entry.create_system = 3
            entry.external_attr = mode << 16
        archive.writestr(entry, inner if inner is not None else inner_zip())
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(entry, inner_zip())
    return buffer.getvalue()


class SelectionTests(unittest.TestCase):
    def test_selects_newest_compatible_trusted_main_program(self):
        recent = artifact(HEAD, 200, 10)
        old = artifact(OLDER, 150, 11)
        client = Api([old, recent], runs={10: run(), 11: run(OLDER, 11)})
        checked = []
        selected = download.select_program(client, HEAD, lambda sha: checked.append(sha) or sha == OLDER)
        self.assertEqual(selected["source_commit"], OLDER)
        self.assertEqual(checked, [HEAD, OLDER])

    def test_requires_successful_main_head_before_artifact_search(self):
        for field, value in (("status", "in_progress"), ("conclusion", "failure"),
                             ("event", "pull_request"), ("head_branch", "topic"),
                             ("head_sha", OLDER), ("workflow_id", 999),
                             ("path", ".github/workflows/untrusted.yml")):
            with self.subTest(field=field):
                bad = run()
                bad[field] = value
                client = Api(head_run=bad)
                with self.assertRaisesRegex(download.DownloadError, "main_checks_not_successful"):
                    download.select_program(client, HEAD, lambda _: True)
                self.assertFalse(any("/artifacts?" in p for p in client.paths))

    def test_head_repository_and_workflow_repository_must_match_fixed_repository(self):
        for field in ("repository", "head_repository"):
            for changed in ({"id": 321}, {"full_name": "fork/team-agent-poc"}):
                with self.subTest(field=field, changed=changed):
                    bad = run()
                    bad[field].update(changed)
                    with self.assertRaises(download.DownloadError):
                        download.require_successful_head(Api(head_run=bad), HEAD)

    def test_skips_expired_incompatible_and_untrusted_artifacts(self):
        variations = []
        for key, value in (("expired", True), ("name", "ees-demo-" + HEAD[:12]),
                           ("name", "ees-program-" + HEAD[:12])):
            row = artifact()
            row[key] = value
            variations.append(row)
        for key, value in (("head_branch", "topic"), ("head_sha", OLDER),
                           ("head_repository_id", 999), ("repository_id", 999)):
            row = artifact()
            row["workflow_run"][key] = value
            variations.append(row)
        for row in variations:
            with self.subTest(row=row):
                compatible = Mock(return_value=True)
                with self.assertRaisesRegex(download.DownloadError, "program_artifact_missing"):
                    download.select_program(Api([row]), HEAD, compatible)
                compatible.assert_not_called()
        with self.assertRaisesRegex(download.DownloadError, "program_artifact_missing"):
            download.select_program(Api(), HEAD, lambda _: False)

    def test_artifact_full_run_validated_not_only_list_summary(self):
        for key, value in (("event", "pull_request"), ("conclusion", "failure"),
                           ("workflow_id", 22), ("id", 55)):
            with self.subTest(key=key):
                bad = run()
                bad[key] = value
                with self.assertRaisesRegex(download.DownloadError, "program_artifact_missing"):
                    download.select_program(Api(runs={10: bad}), HEAD, lambda _: True)

    def test_search_bounded_to_three_pages(self):
        rows = [dict(artifact(artifact_id=n + 1), expired=True) for n in range(400)]
        client = Api(rows)
        with self.assertRaisesRegex(download.DownloadError, "program_artifact_missing"):
            download.select_program(client, HEAD, lambda _: True)
        self.assertEqual(sum("/artifacts?" in p for p in client.paths), 3)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.client = download.GithubClient(TOKEN)
        self.client._opener = Mock()

    def prepare(self, content=None):
        content = outer_zip() if content is None else content
        row = dict(artifact(), source_commit=HEAD, size_in_bytes=len(content),
                   digest="sha256:" + hashlib.sha256(content).hexdigest())
        self.client._opener.open.side_effect = [Response(status=302, headers={"Location": STORAGE}),
                                                 Response(content)]
        return row

    def test_download_verifies_digest_and_strips_api_auth_on_redirect(self):
        row = self.prepare()
        result = self.client.download_artifact(row, self.root)
        self.assertEqual(result.name, "EES-demo-" + HEAD[:12] + ".zip")
        self.assertEqual(result.read_bytes(), inner_zip())
        calls = self.client._opener.open.call_args_list
        first, second = calls[0].args[0], calls[1].args[0]
        self.assertEqual(first.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertIsNone(second.get_header("Authorization"))
        self.assertIsNone(second.get_header("X-github-api-version"))
        self.assertEqual(list(self.root.iterdir()), [result])

    def test_real_urllib_redirect_handler_does_not_follow_authenticated_request(self):
        self.assertIsNone(download._NoRedirect().redirect_request(None, None, 302, "", {}, STORAGE))
        self.client._opener.open.side_effect = HTTPError(
            "https://api.github.com/private", 302, "Found", {"Location": STORAGE}, io.BytesIO())
        with self.client._request("https://api.github.com" + download.API_PREFIX + "/actions/artifacts/1/zip", True) as response:
            self.assertEqual(response.status, 302)

    def test_host_and_scheme_limits_before_second_request(self):
        for url in ("https://evil.example/download", "http://productionresultssa1.blob.core.windows.net/a",
                    "https://productionresultssa1.blob.core.windows.net.evil.example/a",
                    "https://productionresultssa1.blob.core.windows.net:8443/a",
                    "https://user:pass@productionresultssa1.blob.core.windows.net/a",
                    "https://api.github.com/another-api?secret=value"):
            with self.subTest(url=url):
                row = self.prepare()
                self.client._opener.open.reset_mock()
                self.client._opener.open.side_effect = [Response(status=302, headers={"Location": url})]
                with self.assertRaisesRegex(download.DownloadError, "download_host_blocked"):
                    self.client.download_artifact(row, self.root)
                self.assertEqual(self.client._opener.open.call_count, 1)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_digest_mismatch_and_missing_digest_never_leave_deliverable(self):
        for digest in ("sha256:" + "f" * 64, None):
            with self.subTest(digest=digest):
                row = self.prepare()
                row["digest"] = digest
                with self.assertRaises(download.DownloadError):
                    self.client.download_artifact(row, self.root)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_zip_shape_traversal_links_duplicates_and_invalid_manifest_rejected(self):
        invalid = [b"not a zip", outer_zip(filename="../EES-demo-" + HEAD[:12] + ".zip"),
                   outer_zip(mode=stat.S_IFLNK | 0o777), outer_zip(duplicate=True),
                   outer_zip(inner=inner_zip(OLDER)), outer_zip(inner=inner_zip(branding=False))]
        for content in invalid:
            with self.subTest(size=len(content)):
                row = self.prepare(content)
                with self.assertRaises(download.DownloadError):
                    self.client.download_artifact(row, self.root)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_size_bound_checked_before_and_during_download(self):
        row = self.prepare()
        row["size_in_bytes"] = download.MAX_DOWNLOAD_BYTES + 1
        with self.assertRaisesRegex(download.DownloadError, "invalid_artifact"):
            self.client.download_artifact(row, self.root)
        self.client._opener.open.assert_not_called()
        row = self.prepare()
        row["size_in_bytes"] -= 1
        with self.assertRaisesRegex(download.DownloadError, "artifact_too_large"):
            self.client.download_artifact(row, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_destination_not_replaced(self):
        expected = self.root / ("EES-demo-" + HEAD[:12] + ".zip")
        expected.write_bytes(b"existing bundle")
        row = self.prepare()
        with self.assertRaises(download.DownloadError):
            self.client.download_artifact(row, self.root)
        self.assertEqual(expected.read_bytes(), b"existing bundle")

    def test_http_and_network_error_messages_do_not_contain_credentials_or_url(self):
        for error in (URLError(STORAGE + TOKEN), HTTPError(STORAGE, 403, TOKEN, {}, io.BytesIO())):
            with self.subTest(kind=type(error).__name__):
                self.client._opener.open.side_effect = error
                with self.assertRaises(download.DownloadError) as captured:
                    self.client.json(download.API_PREFIX + "/actions/artifacts")
                self.assertNotIn(TOKEN, str(captured.exception))
                self.assertNotIn("sig=", str(captured.exception))

    def test_api_json_is_bounded_and_does_not_follow_redirects(self):
        self.client._opener.open.side_effect = [Response(status=302, headers={"Location": STORAGE})]
        with self.assertRaisesRegex(download.DownloadError, "api_redirect_blocked"):
            self.client.json(download.API_PREFIX + "/actions/artifacts")
        self.client._opener.open.side_effect = [Response(b"123456")]
        with patch.object(download, "MAX_JSON_BYTES", 4):
            with self.assertRaisesRegex(download.DownloadError, "api_response_too_large"):
                self.client.json(download.API_PREFIX + "/actions/artifacts")
        for path in ("https://evil.example/", "/repos/another/project/actions", download.API_PREFIX + "/../other"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(download.DownloadError, "invalid_api_path"):
                    self.client.json(path)


if __name__ == "__main__":
    unittest.main()
