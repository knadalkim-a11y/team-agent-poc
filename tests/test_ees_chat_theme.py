"""Reusable ChromePipe and pinned Korean font integrity validation.

Retired demo shadow-DOM/drag-resizer tests are explicitly mapped in the
delivery baseline to actual packaged Native geometry and control tests.
"""

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from xml.sax.saxutils import escape

from scripts import build_ees_webui as branding

ROOT = Path(__file__).resolve().parents[1]


def chrome_font_environment(profile, wheel=None):
    """Give this Linux browser a Korean fallback without changing OS or CSS.

    Native auth/pending screens intentionally keep the upstream font stack.
    Minimal runners may have no Korean platform font, even after fonts.ready.
    Reuse the already pinned wheel font through a profile-local fontconfig.
    The caller owns the temporary profile and its font/cache cleanup.
    """
    environment = os.environ.copy()
    if not sys.platform.startswith("linux"):
        return environment
    if wheel is None and (directory := environment.get("EES_TEST_BRANDING_DIR")):
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        wheel = directory / manifest["wheel"]["filename"]
    if wheel is None:
        return environment
    member, expected_hash = branding.FONT_SOURCES["NotoSansKR-Variable.ttf"]
    with ZipFile(wheel) as archive:
        content = archive.read(member)
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise AssertionError("Pinned Native Korean fallback font hash mismatch")
    profile = Path(profile).resolve()
    directory = profile / "fixture-fonts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "NotoSansKR-Variable.ttf").write_bytes(content)
    cache = profile / "fixture-font-cache"
    cache.mkdir(exist_ok=True)
    config = profile / "fixture-fonts.conf"
    inherited = environment.get("FONTCONFIG_FILE", "/etc/fonts/fonts.conf")
    config.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        '<cachedir>' + escape(str(cache)) + '</cachedir>'
        '<include ignore_missing="yes">' + escape(inherited) + '</include>'
        '<dir>' + escape(str(directory)) + '</dir>'
        '</fontconfig>\n', encoding="utf-8")
    environment["FONTCONFIG_FILE"] = str(config)
    return environment


class ChromePipe:
    """Small Linux-only CDP client for this fixture's trusted input checks.

    Uses Chrome's local inherited pipes, not a debugging TCP port or an npm
    dependency. Every response has a deadline; browser/profile cleanup is local.
    """

    def __init__(self, chrome, profile, *, font_wheel=None):
        self.started_at = time.monotonic()
        self.stage, self.browser_version, self.target_id = "launch", None, None
        self.last_command, self.first_failure, self.response_summary = None, None, []
        environment = chrome_font_environment(profile, font_wheel)
        request_read, self.request_write = os.pipe()
        self.response_read, response_write = os.pipe()
        self.errors = tempfile.TemporaryFile()
        command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--disable-dev-shm-usage", "--disable-background-networking",
                   "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                   "--hide-scrollbars", "--remote-debugging-pipe", "--user-data-dir=" + profile]
        # dup2 runs in a fresh helper process: do not alter the HTTP server's
        # descriptors or use preexec_fn in this multithreaded test process.
        launch = "import os,sys;os.dup2(int(sys.argv[1]),3);os.dup2(int(sys.argv[2]),4);os.execv(sys.argv[3],sys.argv[3:])"
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-c", launch, str(request_read), str(response_write)] + command,
                pass_fds=(request_read, response_write), start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=self.errors, env=environment)
        finally:
            os.close(request_read)
            os.close(response_write)
        self.counter, self.buffer, self.events, self.session = 0, b"", [], None

    def diagnostics(self):
        """Read local process/pipe state without issuing another CDP command."""
        size = os.fstat(self.errors.fileno()).st_size
        stderr = os.pread(self.errors.fileno(), min(size, 8192), max(0, size - 8192))
        return {"stage": self.stage, "elapsed_ms": (time.monotonic() - self.started_at) * 1000,
                "pid": self.process.pid, "exit_code": self.process.poll(),
                "browser_version": self.browser_version, "target_id": self.target_id,
                "session_attached": bool(self.session), "buffer_bytes": len(self.buffer),
                "last_command": dict(self.last_command) if self.last_command else None,
                "recent_responses": list(self.response_summary),
                "stderr_tail": stderr.decode(errors="replace"), "first_failure": self.first_failure}

    def record_failure(self, error):
        if self.first_failure is None:
            snapshot = self.diagnostics()
            snapshot.pop("first_failure")
            snapshot["error_type"] = type(error).__name__
            self.first_failure = snapshot

    def close(self):
        try:
            # Let Chrome finish its profile writes before TemporaryDirectory
            # removes them. SIGTERM on the parent alone leaves writers behind.
            self.session = None
            if self.process.poll() is None:
                try:
                    self.call("Browser.close", timeout=5)
                except (AssertionError, OSError):
                    # Chrome can close the pipe before returning this response.
                    pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(self.process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        self.process.wait(timeout=5)
            # This test starts a dedicated session, so only its own leftover
            # Chrome subprocesses can belong to this process group.
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        finally:
            os.close(self.request_write)
            os.close(self.response_read)
            self.errors.close()

    def receive(self, deadline):
        while b"\0" not in self.buffer:
            timeout = deadline - time.monotonic()
            if timeout <= 0 or not select.select([self.response_read], [], [], timeout)[0]:
                raise AssertionError("Chrome DevTools response timed out.")
            chunk = os.read(self.response_read, 65536)
            if not chunk:
                raise AssertionError("Chrome DevTools pipe closed: " + self.diagnostics()["stderr_tail"][-2000:])
            self.buffer += chunk
        message, self.buffer = self.buffer.split(b"\0", 1)
        return json.loads(message)

    def call(self, method, params=None, timeout=15):
        self.counter += 1
        request = {"id": self.counter, "method": method, "params": params or {}}
        if self.session:
            request["sessionId"] = self.session
        self.last_command = {"id": request["id"], "method": method,
                             "session_attached": bool(self.session), "timeout_seconds": timeout}
        started = time.monotonic()
        try:
            if timeout <= 0:
                raise AssertionError("Chrome DevTools response budget exhausted before command.")
            payload = json.dumps(request).encode() + b"\0"
            while payload:
                payload = payload[os.write(self.request_write, payload):]
            deadline = started + timeout
            while True:
                response = self.receive(deadline)
                self.response_summary.append({key: response[key] for key in ("id", "method", "sessionId") if key in response})
                self.response_summary = self.response_summary[-20:]
                if response.get("id") == request["id"]:
                    if "error" in response:
                        raise AssertionError(f"{method}: {response['error']}")
                    self.last_command["elapsed_ms"] = (time.monotonic() - started) * 1000
                    self.last_command["completed"] = True
                    return response.get("result", {})
                self.events.append(response)
        except (AssertionError, OSError) as error:
            self.last_command["elapsed_ms"] = (time.monotonic() - started) * 1000
            self.last_command["completed"] = False
            self.record_failure(error)
            raise

    def navigate(self, url):
        # Confirm browser-level transport readiness before creating a renderer.
        # Both commands share the original 15s target-creation budget: no retry.
        deadline = time.monotonic() + 15
        try:
            if self.browser_version is None:
                self.stage = "browser_handshake"
                version = self.call("Browser.getVersion", timeout=deadline - time.monotonic())
                if not all(isinstance(version.get(key), str) and version[key] for key in ("protocolVersion", "product")):
                    raise AssertionError("Chrome browser handshake did not return protocolVersion and product.")
                self.browser_version = {key: version.get(key) for key in ("protocolVersion", "product", "revision", "jsVersion")}
            self.stage = "create_target"
            target = self.call("Target.createTarget", {"url": "about:blank"}, timeout=deadline - time.monotonic())["targetId"]
        except (AssertionError, OSError) as error:
            self.record_failure(error)
            raise
        self.target_id, self.stage = target, "attach_target"
        self.session = self.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        self.stage = "page_setup"
        self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
        self.events.clear()
        self.stage = "initial_navigation"
        self.call("Page.navigate", {"url": url})
        deadline = time.monotonic() + 15
        while not any(event.get("method") == "Page.loadEventFired" for event in self.events):
            self.events.append(self.receive(deadline))
        self.stage = "ready"

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"])
        return result["result"].get("value")


class ChromeFontEnvironmentTests(unittest.TestCase):
    def test_changed_pinned_font_is_rejected_before_launch_or_profile_write(self):
        before = os.environ.copy()
        with tempfile.TemporaryDirectory(prefix="ees-font-integrity-") as temporary:
            wheel = Path(temporary) / "changed.whl"
            with ZipFile(wheel, "w") as archive:
                archive.writestr(branding.FONT_SOURCES["NotoSansKR-Variable.ttf"][0], b"changed font bytes")
            profile = Path(temporary) / "chrome"
            with patch.object(sys, "platform", "linux"), self.assertRaisesRegex(AssertionError, "font hash mismatch"):
                chrome_font_environment(profile, wheel)
            self.assertFalse(profile.exists())
        self.assertEqual(os.environ, before)


class ChromePipeBootstrapTests(unittest.TestCase):
    def pipe(self):
        browser = ChromePipe.__new__(ChromePipe)
        browser.started_at = time.monotonic()
        browser.stage, browser.browser_version, browser.target_id = "launch", None, None
        browser.last_command, browser.first_failure, browser.response_summary = None, None, []
        browser.counter, browser.buffer, browser.events, browser.session = 0, b"", [], None
        request_read, browser.request_write = os.pipe()
        browser.response_read, response_write = os.pipe()
        for descriptor in (request_read, browser.request_write, browser.response_read, response_write):
            self.addCleanup(os.close, descriptor)
        browser.errors = tempfile.TemporaryFile()
        self.addCleanup(browser.errors.close)
        browser.process = SimpleNamespace(pid=123, poll=lambda: None)
        return browser, request_read, response_write

    def test_interleaved_pipe_event_does_not_replace_handshake_response_or_leak_params(self):
        browser, request_read, response_write = self.pipe()
        event = {"method": "Target.targetCreated", "params": {"private": "synthetic-secret"}}
        reply = {"id": 1, "result": {"protocolVersion": "1.3", "product": "Synthetic/1"}}
        os.write(response_write, (json.dumps(event) + '\0' + json.dumps(reply) + '\0').encode())
        self.assertEqual(browser.call("Browser.getVersion"), reply["result"])
        self.assertEqual(browser.events, [event])
        self.assertEqual(json.loads(os.read(request_read, 4096).rstrip(b'\0'))["method"], "Browser.getVersion")
        self.assertNotIn("synthetic-secret", json.dumps(browser.diagnostics()))

    def test_handshake_and_target_creation_share_original_budget_without_retry(self):
        browser, _, _ = self.pipe()
        clock, calls = [10.0], []
        def call(method, params=None, timeout=15):
            calls.append((method, timeout))
            if method == "Browser.getVersion":
                clock[0] += 6
                return {"protocolVersion": "1.3", "product": "Synthetic/1"}
            if method == "Target.createTarget": return {"targetId": "target"}
            if method == "Target.attachToTarget": return {"sessionId": "session"}
            if method == "Page.navigate": browser.events.append({"method": "Page.loadEventFired"})
            return {}
        browser.call = call
        with patch.object(time, "monotonic", side_effect=lambda: clock[0]):
            browser.navigate("about:blank")
        self.assertEqual(calls[:2], [("Browser.getVersion", 15.0), ("Target.createTarget", 9.0)])
        self.assertEqual(browser.stage, "ready")
        self.assertEqual(browser.browser_version["product"], "Synthetic/1")

    def test_invalid_browser_handshake_fails_before_any_target_is_created(self):
        browser, _, _ = self.pipe()
        calls = []
        browser.call = lambda method, **kwargs: calls.append(method) or {}
        with self.assertRaisesRegex(AssertionError, "handshake"):
            browser.navigate("about:blank")
        self.assertEqual(calls, ["Browser.getVersion"])
        self.assertEqual(browser.first_failure["stage"], "browser_handshake")
        self.assertFalse(browser.first_failure["session_attached"])

    def test_first_timeout_preserves_stderr_and_request_before_later_cleanup_response(self):
        browser, _, response_write = self.pipe()
        browser.stage = "create_target"
        browser.errors.write(b"synthetic startup diagnostic\n"); browser.errors.flush()
        original_offset = browser.errors.tell()
        with patch.object(select, "select", return_value=([], [], [])), self.assertRaisesRegex(AssertionError, "timed out"):
            browser.call("Target.createTarget", {"url": "about:blank"}, timeout=.01)
        original = json.dumps(browser.first_failure, sort_keys=True)
        os.write(response_write, b'{"id":2,"result":{}}\0')
        browser.call("Browser.close")
        self.assertEqual(json.dumps(browser.first_failure, sort_keys=True), original)
        self.assertEqual(browser.first_failure["last_command"]["method"], "Target.createTarget")
        self.assertFalse(browser.first_failure["last_command"]["completed"])
        self.assertIn("synthetic startup diagnostic", browser.first_failure["stderr_tail"])
        self.assertEqual(browser.errors.tell(), original_offset)

    def test_bootstrap_failure_capture_saves_local_diagnostics_without_page_commands(self):
        from ees_work_integrated_fixture import IntegratedNativeCase
        browser, _, _ = self.pipe()
        browser.stage = "browser_handshake"
        browser.record_failure(AssertionError("synthetic bootstrap failure"))
        case = IntegratedNativeCase("runTest")
        case.browser = browser
        case._outcome = SimpleNamespace(result=SimpleNamespace(failures=[(case, "failure")], errors=[]))
        case.screenshot = lambda *args, **kwargs: self.fail("No page command before a session attaches")
        with tempfile.TemporaryDirectory(prefix="ees-bootstrap-evidence-") as directory:
            with patch.dict(os.environ, {"EES_TEST_SCREENSHOT_DIR": directory}):
                case.capture_failure()
            report = json.loads((Path(directory) / "integrated-runTest-failure.json").read_text(encoding="utf-8"))
        self.assertEqual(report["page_capture"], "unavailable_no_attached_session")
        self.assertEqual(report["browser"]["first_failure"]["stage"], "browser_handshake")
        self.assertEqual(report["capture_errors"], [])


if __name__ == "__main__":
    unittest.main()
