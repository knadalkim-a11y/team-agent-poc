"""Prepare a pinned trial bundle with the registered Python, without installing.

Only the official pinned wheel is downloaded, once, into a verified local cache.
Git source is checked out separately with LF bytes; the running installation and
its dependencies, settings and data are never packaging inputs or destinations.
The caller holds the deployment lock and validates the bundle before stopping.
"""

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_ees_webui as branding
import ees_deploy_state as states


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/knadalkim-a11y/team-agent-poc"
METADATA_URL = "https://pypi.org/pypi/open-webui/0.11.3/json"
MAX_JSON_BYTES = 1024 * 1024
MAX_WHEEL_BYTES = 256 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 600
HEX40 = re.compile(r"[0-9a-f]{40}")
WINDOWS_PATHS = os.name == "nt"


class TrialBundleError(ValueError):
    """A fixed error code that cannot disclose proxy credentials or responses."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require_local_build_supported():
    """Never build a source-frontend release without its verified CI output."""
    if branding.SOURCE_FRONTEND_REQUIRED:
        raise TrialBundleError("ci_frontend_artifact_required")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _wheel_url(url):
    try:
        parts = urlsplit(url)
        valid = (isinstance(url, str) and parts.scheme == "https"
                 and parts.hostname == "files.pythonhosted.org" and parts.port in (None, 443)
                 and parts.netloc in ("files.pythonhosted.org", "files.pythonhosted.org:443")
                 and parts.username is None and parts.password is None and not parts.fragment and not parts.query
                 and parts.path.startswith("/packages/")
                 and parts.path.endswith("/" + branding.SOURCE_FILENAME)
                 and not any(ord(c) < 33 or ord(c) == 127 or c in "\\%" for c in url))
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise TrialBundleError("upstream_host_blocked")
    return url


def _opener(proxy):
    handlers = [_NoRedirect(), HTTPSHandler(context=ssl.create_default_context())]
    if proxy is not None:
        handlers.append(ProxyHandler({"https": proxy}))
    return build_opener(*handlers)


def _request(opener, url):
    request = Request(url, headers={"User-Agent": "EES-Trial-Builder", "Accept-Encoding": "identity"})
    try:
        response = opener.open(request, timeout=30)
        if response.status != 200:
            response.close()
            raise TrialBundleError("upstream_http_error")
        return response
    except TrialBundleError:
        raise
    except HTTPError as error:
        code = "upstream_redirect_blocked" if error.code in (301, 302, 303, 307, 308) else "upstream_http_error"
        error.close()
        raise TrialBundleError(code) from None
    except (OSError, URLError, http.client.HTTPException, ValueError):
        raise TrialBundleError("upstream_connection_failed") from None


def _metadata(opener):
    try:
        raw, started = bytearray(), time.monotonic()
        with _request(opener, METADATA_URL) as response:
            read = getattr(response, "read1", response.read)
            while chunk := read(16 * 1024):
                raw.extend(chunk)
                if len(raw) > MAX_JSON_BYTES:
                    raise TrialBundleError("upstream_metadata_too_large")
                if time.monotonic() - started > 60:
                    raise TrialBundleError("upstream_download_timeout")
        document = json.loads(raw)
        rows = document.get("urls") if isinstance(document, dict) else None
        matches = [row for row in rows if isinstance(row, dict)
                   and row.get("filename") == branding.SOURCE_FILENAME] if isinstance(rows, list) else []
        if len(matches) != 1:
            raise TrialBundleError("upstream_metadata_invalid")
        row = matches[0]
        if (row.get("packagetype") != "bdist_wheel" or row.get("yanked") is not False
                or not isinstance(row.get("digests"), dict)
                or row["digests"].get("sha256") != branding.SOURCE_SHA256
                or type(row.get("size")) is not int or not 0 < row["size"] <= MAX_WHEEL_BYTES):
            raise TrialBundleError("upstream_metadata_invalid")
        return _wheel_url(row.get("url")), row["size"]
    except TrialBundleError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError, http.client.HTTPException):
        raise TrialBundleError("upstream_metadata_invalid") from None


def _verified_wheel(path):
    states._regular(path)
    if not 0 < path.stat().st_size <= MAX_WHEEL_BYTES or branding.sha256_file(path) != branding.SOURCE_SHA256:
        raise TrialBundleError("upstream_cache_mismatch")
    return path


def _upstream(config, proxy, progress):
    directory = states._safe(Path(config["state_root"]) / "upstream", exists=False)
    directory.mkdir(exist_ok=True)
    states._safe(directory)
    target = directory / branding.SOURCE_FILENAME
    if target.exists() or target.is_symlink():
        progress["upstream_cached"] = True
        return _verified_wheel(target)
    progress["upstream_cached"] = False
    progress["stage"] = "upstream_download"
    opener = _opener(proxy)
    url, expected_size = _metadata(opener)
    with tempfile.TemporaryDirectory(prefix="download-", dir=directory) as temporary:
        partial = Path(temporary) / "wheel.part"
        digest, size, started = hashlib.sha256(), 0, time.monotonic()
        try:
            with _request(opener, url) as response, partial.open("xb") as stream:
                read = getattr(response, "read1", response.read)
                while chunk := read(1024 * 1024):
                    size += len(chunk)
                    if size > expected_size or size > MAX_WHEEL_BYTES:
                        raise TrialBundleError("upstream_too_large")
                    if time.monotonic() - started > MAX_DOWNLOAD_SECONDS:
                        raise TrialBundleError("upstream_download_timeout")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if size != expected_size or digest.hexdigest() != branding.SOURCE_SHA256:
                raise TrialBundleError("upstream_digest_mismatch")
            # Publish complete verified bytes exclusively, never overwrite cache.
            os.link(partial, target)
        except TrialBundleError:
            raise
        except (OSError, ValueError, http.client.HTTPException):
            raise TrialBundleError("upstream_download_failed") from None
    return _verified_wheel(target)


def _git(*arguments, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        options = (["-c", "core.autocrlf=false", "-c", "core.eol=lf"]
                   if arguments[:2] == ("worktree", "add") else [])
        result = subprocess.run(
            ["git", *options, "-C", str(cwd or ROOT), *arguments],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise TrialBundleError("trial_source_failed") from None


def _checkout(commit):
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise TrialBundleError("trial_commit_invalid")
    if (_git("remote", "get-url", "origin") not in (REPOSITORY, REPOSITORY + ".git")
            or _git("branch", "--show-current") != "main"
            or _git("status", "--porcelain", "--untracked-files=no")
            or _git("rev-parse", "HEAD") != commit or _git("rev-parse", "origin/main") != commit):
        raise TrialBundleError("trial_source_changed")


def _build(python, source, wheel, output):
    commands = (
        [str(python), "-I", "-B", str(source / "scripts" / "build_ees_webui.py"),
         "--wheel", str(wheel), "--output-dir", str(output / "branding")],
        [str(python), "-I", "-B", str(source / "scripts" / "build_demo_bundle.py"),
         "--branding-dir", str(output / "branding"), "--output-dir", str(output)],
    )
    try:
        for command in commands:
            subprocess.run(command, cwd=source, check=True, capture_output=True,
                           text=True, encoding="utf-8", timeout=600)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise TrialBundleError("trial_build_failed") from None


def _source_bytes(source, commit):
    """Reject checkout filters/EOL conversion even when Git considers it clean."""
    for entry in _git("ls-tree", "-r", "-z", "--full-tree", commit, cwd=source).split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, expected = metadata.split()
        if mode not in ("100644", "100755") or kind != "blob":
            raise TrialBundleError("trial_source_changed")
        path = states._regular(source / name)
        content = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
        if actual != expected:
            raise TrialBundleError("trial_source_changed")


def _check_source_paths(source, commit):
    """Keep checkout files/directories usable without Win32 long-path policy."""
    if not WINDOWS_PATHS:
        return
    units = lambda path: len(str(path).encode("utf-16-le")) // 2
    names = _git("ls-tree", "-r", "-z", "--name-only", commit).split("\0")
    for name in filter(None, names):
        path = source / name
        # MAX_PATH includes NUL. Directory creation also reserves 12 units.
        if units(path) >= 260 or any(units(parent) > 248 for parent in path.parents):
            raise TrialBundleError("trial_source_path_too_long")


def _remove_source(source):
    """Remove only this call's checked temporary path, including partial add."""
    states._safe(source, exists=False)
    entries = _git("worktree", "list", "--porcelain", "-z").split("\0")
    if any(entry.startswith("worktree ") and Path(entry[9:]) == source for entry in entries):
        _git("worktree", "remove", "--force", str(source))
    elif source.exists():
        shutil.rmtree(source)


def prepare(config, commit, proxy, progress):
    """Return a retained exact bundle; the caller must inspect before any Stop."""
    require_local_build_supported()
    _checkout(commit)
    states._safe(Path(config["state_root"]))
    parent = states._safe(ROOT.parent)
    progress["stage"] = "trial_build"
    # Source is short-lived beside the clone. Retained output stays in state_root.
    _check_source_paths(parent / "ees-00000000", commit)
    wheel = _upstream(config, proxy, progress)
    progress["stage"] = "trial_build"
    directory = Path(tempfile.mkdtemp(prefix="trial-build-", dir=config["state_root"]))
    source, output = None, directory
    completed = False
    try:
        source = Path(tempfile.mkdtemp(prefix="ees-", dir=parent))
        states._safe(source)
        _check_source_paths(source, commit)
        _git("worktree", "add", "--detach", str(source), commit)
        if (_git("rev-parse", "HEAD", cwd=source) != commit
                or _git("status", "--porcelain", "--untracked-files=no", cwd=source)):
            raise TrialBundleError("trial_source_changed")
        _source_bytes(source, commit)
        _build(config["source_python"], source, wheel, output)
        _source_bytes(source, commit)
        _checkout(commit)
        bundle = states._regular(output / ("EES-demo-" + commit[:12] + ".zip"))
        _remove_source(source)
        source = None
        shutil.rmtree(output / "branding")
        completed = True
        progress["bundle"] = str(bundle)
        return bundle
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            if source is not None:
                _remove_source(source)
            if not completed:
                states._safe(directory)
                shutil.rmtree(directory)
        except (OSError, ValueError, RuntimeError):
            # Do not replace the first failure with a secondary cleanup error.
            if not failed:
                raise
            progress["cleanup_failed"] = True


def cleanup(config, bundle):
    """Best-effort cleanup only after the caller completed the whole update."""
    try:
        root = states._safe(Path(config["state_root"]))
        bundle = states._regular(Path(bundle))
        parent = states._safe(bundle.parent)
        if (parent.parent != root or not parent.name.startswith("trial-build-")
                or not re.fullmatch(r"EES-demo-[0-9a-f]{12}\.zip", bundle.name)):
            return False
        shutil.rmtree(parent)
        return True
    except (OSError, ValueError, states.StateError):
        return False
