"""Read-only GitHub selection and bounded Actions artifact download.

Only the fixed repository's successful main delivery runs are eligible. GitHub
API credentials never follow storage redirects. Storage hosts follow GitHub's
documented Actions domains (HTTPS, default port only):
https://docs.github.com/en/actions/reference/runners/self-hosted-runners
The API digest covers the outer Actions ZIP. The existing release validator
must still validate the returned inner bundle before any program changes.
"""

import hashlib
import http.client
import json
from pathlib import Path
import re
import ssl
import stat
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
import zipfile
import zlib


REPOSITORY = "knadalkim-a11y/team-agent-poc"
API_PREFIX = "/repos/" + REPOSITORY
WORKFLOW = "ees-delivery.yml"
WORKFLOW_PATH = ".github/workflows/" + WORKFLOW
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 600
HEX40 = re.compile(r"[0-9a-f]{40}")
ARTIFACT_NAME = re.compile(r"ees-program-([0-9a-f]{40})")


class DownloadError(ValueError):
    """A fixed, credential-safe error code, without URLs or server response text."""

    def __init__(self, code):
        self.code = code
        super().__init__("GitHub update: " + code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _positive_id(value):
    return type(value) is int and value > 0


def _api_url(path):
    if (not isinstance(path, str) or not path.startswith(API_PREFIX + "/")
            or any(ord(c) < 32 or c in "\\#" for c in path)
            or ".." in path or "%" in path):
        raise DownloadError("invalid_api_path")
    return "https://api.github.com" + path


def _storage_url(url):
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        valid = (parts.scheme == "https" and parts.port in (None, 443)
                 and not parts.username and not parts.password and not parts.fragment
                 and (host == "results-receiver.actions.githubusercontent.com"
                      or re.fullmatch(r"[a-z0-9-]+\.blob\.core\.windows\.net", host)))
    except ValueError:
        valid = False
    if not valid or any(ord(c) < 32 or c == "\\" for c in url):
        raise DownloadError("download_host_blocked")
    return url


class GithubClient:
    def __init__(self, token, proxy=None):
        if (not isinstance(token, str) or not token or len(token) > 4096
                or not token.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in token)):
            raise DownloadError("credentials_missing")
        self._token = token
        handlers = [_NoRedirect(), HTTPSHandler(context=ssl.create_default_context())]
        if proxy is not None:
            handlers.append(ProxyHandler({"https": proxy}))
        self._opener = build_opener(*handlers)

    def _request(self, url, authenticated=False):
        headers = {"User-Agent": "EES-Updater", "Accept-Encoding": "identity"}
        if authenticated:
            if urlsplit(url).netloc != "api.github.com" or not url.startswith("https://api.github.com" + API_PREFIX + "/"):
                raise DownloadError("invalid_api_path")
            headers.update({"Authorization": "Bearer " + self._token,
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"})
        request = Request(url, headers=headers)
        try:
            return self._opener.open(request, timeout=30)
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                return error
            code = ("credentials_rejected" if error.code in (401, 403) else
                    "artifact_unavailable" if error.code in (404, 410) else "github_http_error")
            error.close()
            raise DownloadError(code) from None
        except (OSError, URLError, http.client.HTTPException, ValueError):
            raise DownloadError("github_connection_failed") from None

    def json(self, path):
        try:
            with self._request(_api_url(path), authenticated=True) as response:
                if response.status != 200:
                    raise DownloadError("api_redirect_blocked")
                raw = response.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise DownloadError("api_response_too_large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise DownloadError("invalid_api_response")
            return result
        except DownloadError:
            raise
        except (OSError, ValueError, UnicodeError, RecursionError, http.client.HTTPException):
            raise DownloadError("invalid_api_response") from None

    def download_artifact(self, artifact, destination):
        """Return a verified inner ZIP under destination; never extract code."""
        if not isinstance(artifact, dict):
            raise DownloadError("invalid_artifact")
        commit = artifact.get("source_commit")
        digest = artifact.get("digest")
        size = artifact.get("size_in_bytes")
        if (not isinstance(commit, str) or not HEX40.fullmatch(commit)
                or artifact.get("name") != "ees-program-" + commit
                or not _positive_id(artifact.get("id")) or artifact.get("expired") is not False
                or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                or type(size) is not int or not 0 < size <= MAX_DOWNLOAD_BYTES):
            raise DownloadError("invalid_artifact")
        try:
            destination = Path(destination)
            if destination.is_symlink():
                raise DownloadError("unsafe_destination")
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="ees-download-", dir=destination) as temporary:
                outer = Path(temporary) / "artifact.zip.part"
                self._download(artifact["id"], outer, digest[7:], size)
                inner = Path(temporary) / ("EES-demo-" + commit[:12] + ".zip")
                _extract_inner(outer, inner, commit)
                target = destination / inner.name
                # Exclusive creation does not overwrite an existing file or link.
                with target.open("xb") as stream:
                    try:
                        with inner.open("rb") as source:
                            while chunk := source.read(1024 * 1024):
                                stream.write(chunk)
                    except BaseException:
                        stream.close()
                        target.unlink(missing_ok=True)
                        raise
                return target
        except DownloadError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, zlib.error, http.client.HTTPException):
            raise DownloadError("artifact_download_failed") from None

    def _download(self, artifact_id, path, expected_digest, expected_size):
        url = _api_url(API_PREFIX + "/actions/artifacts/" + str(artifact_id) + "/zip")
        started = time.monotonic()
        for hop in range(6):
            with self._request(url, authenticated=(hop == 0)) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise DownloadError("invalid_download_redirect")
                    url = _storage_url(urljoin(url, location))
                    continue
                if response.status != 200:
                    raise DownloadError("artifact_download_failed")
                digest = hashlib.sha256()
                size = 0
                read = getattr(response, "read1", response.read)
                with path.open("xb") as stream:
                    while chunk := read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES or size > expected_size:
                            raise DownloadError("artifact_too_large")
                        if time.monotonic() - started > MAX_DOWNLOAD_SECONDS:
                            raise DownloadError("download_timeout")
                        digest.update(chunk)
                        stream.write(chunk)
                if size != expected_size or digest.hexdigest() != expected_digest:
                    raise DownloadError("artifact_digest_mismatch")
                return
        raise DownloadError("too_many_redirects")


def _regular(entry):
    mode = entry.external_attr >> 16
    return (not entry.is_dir() and entry.orig_filename == entry.filename
            and stat.S_IFMT(mode) in (0, stat.S_IFREG) and not entry.flag_bits & 1
            and not entry.external_attr & 0x10)


def _extract_inner(outer, destination, commit):
    with zipfile.ZipFile(outer) as archive:
        entries = archive.infolist()
        if (len(entries) != 1 or entries[0].filename != destination.name
                or not _regular(entries[0]) or not 0 < entries[0].file_size <= MAX_DOWNLOAD_BYTES):
            raise DownloadError("invalid_outer_zip")
        count = 0
        with archive.open(entries[0]) as source, destination.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_DOWNLOAD_BYTES:
                    raise DownloadError("invalid_outer_zip")
                target.write(chunk)
    with zipfile.ZipFile(destination) as archive:
        manifests = [entry for entry in archive.infolist() if entry.filename == "manifest.json"]
        if (len(manifests) != 1 or not _regular(manifests[0])
                or manifests[0].file_size > MAX_JSON_BYTES):
            raise DownloadError("invalid_inner_manifest")
        manifest = json.loads(archive.read(manifests[0]))
        if (not isinstance(manifest, dict) or manifest.get("source_commit") != commit
                or manifest.get("source_dirty") is not False
                or not isinstance(manifest.get("branding"), dict)
                or "branding/manifest.json" not in archive.namelist()):
            raise DownloadError("invalid_inner_manifest")


def _trusted_run(run, commit, workflow_id):
    if not isinstance(run, dict):
        return False
    repository = run.get("repository") or {}
    head_repository = run.get("head_repository") or {}
    return (isinstance(repository, dict) and isinstance(head_repository, dict)
            and _positive_id(run.get("id")) and run.get("workflow_id") == workflow_id
            and run.get("path") == WORKFLOW_PATH and run.get("head_sha") == commit
            and run.get("head_branch") == "main" and run.get("event") in ("push", "workflow_dispatch")
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and repository.get("full_name") == REPOSITORY and head_repository.get("full_name") == REPOSITORY
            and _positive_id(repository.get("id")) and repository.get("id") == head_repository.get("id"))


def require_successful_head(client, head):
    """Return one completed, successful delivery run for the exact main head."""
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise DownloadError("invalid_main_commit")
    workflow = client.json(API_PREFIX + "/actions/workflows/" + WORKFLOW)
    workflow_id = workflow.get("id")
    if not _positive_id(workflow_id) or workflow.get("path") != WORKFLOW_PATH:
        raise DownloadError("invalid_workflow")
    runs = client.json(API_PREFIX + "/actions/workflows/" + WORKFLOW
                       + "/runs?branch=main&head_sha=" + head + "&per_page=100").get("workflow_runs")
    if isinstance(runs, list):
        for run in runs:
            if _trusted_run(run, head, workflow_id):
                return run
    raise DownloadError("main_checks_not_successful")


def select_program(client, head, compatible):
    """Select a trusted program artifact; compatible checks Git ancestry/inputs.

    Search at most 300 recent artifacts. An absent/expired compatible build is a
    fixed failure, so an operator can explicitly run the main program workflow.
    """
    workflow_id = require_successful_head(client, head)["workflow_id"]
    artifacts = []
    for page in range(1, 4):
        rows = client.json(API_PREFIX + "/actions/artifacts?per_page=100&page=" + str(page)).get("artifacts")
        if not isinstance(rows, list):
            raise DownloadError("invalid_api_response")
        artifacts.extend(row for row in rows if isinstance(row, dict) and _positive_id(row.get("id")))
        if len(rows) < 100:
            break
    run_cache = {}
    for artifact in sorted(artifacts, key=lambda row: row["id"], reverse=True):
        name = artifact.get("name")
        match = ARTIFACT_NAME.fullmatch(name) if isinstance(name, str) else None
        summary = artifact.get("workflow_run")
        if not match or artifact.get("expired") is not False or not isinstance(summary, dict):
            continue
        commit = match.group(1)
        run_id = summary.get("id")
        if (not _positive_id(run_id) or summary.get("head_sha") != commit
                or summary.get("head_branch") != "main"
                or not _positive_id(summary.get("repository_id"))
                or summary.get("repository_id") != summary.get("head_repository_id")):
            continue
        if run_id not in run_cache:
            run_cache[run_id] = client.json(API_PREFIX + "/actions/runs/" + str(run_id))
        run = run_cache[run_id]
        if (not _trusted_run(run, commit, workflow_id) or run.get("id") != run_id
                or summary["repository_id"] != run["repository"]["id"]):
            continue
        if compatible(commit):
            return dict(artifact, source_commit=commit)
    raise DownloadError("program_artifact_missing")
