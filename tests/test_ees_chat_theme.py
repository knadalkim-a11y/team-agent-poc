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
                "stderr_tail": stderr.decode(errors="replace"), "first_failure": self.first_failure,
                "browser_startup": getattr(self, "browser_startup", None),
                "bootstrap_observation": getattr(self, "bootstrap_observation", None)}

    def record_failure(self, error):
        if self.first_failure is None:
            snapshot = self.diagnostics()
            snapshot.pop("first_failure")
            snapshot["error_type"] = type(error).__name__
            snapshot["response_timeout"] = isinstance(error, AssertionError) and str(error) == "Chrome DevTools response timed out."
            self.first_failure = snapshot

    def observe_failed_bootstrap(self):
        """Observe the original timed-out reply without retrying or passing it.

        Only the first browser handshake qualifies. The test has already failed;
        this bounded cleanup observation never creates a target or resumes it.
        No request is written until the normal Browser.close below this method.
        """
        failure = self.first_failure or {}
        command = failure.get("last_command") or {}
        if (getattr(self, "bootstrap_observation", None) is not None
                or failure.get("stage") != "browser_handshake"
                or not failure.get("response_timeout")
                or command.get("method") != "Browser.getVersion"
                or command.get("id") != 1 or command.get("completed") is not False
                or failure.get("session_attached") or self.session):
            return
        observation = self.bootstrap_observation = {
            "status": "observing", "request_id": 1, "launch_cutoff_seconds": 30,
            "started_elapsed_ms": (time.monotonic() - self.started_at) * 1000,
            "received_ids": [], "other_messages": 0}
        deadline = self.started_at + 30
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    observation["status"] = "process_exited"
                    break
                try:
                    response = self.receive(deadline)
                except AssertionError as error:
                    if str(error) == "Chrome DevTools response timed out.":
                        observation["status"] = "no_original_reply_before_cutoff"
                    else:
                        observation["status"] = "transport_closed"
                    break
                except (ValueError, UnicodeError):
                    observation["status"] = "malformed_response"
                    break
                if not isinstance(response, dict):
                    observation["status"] = "malformed_response"
                    break
                reply_id = response.get("id")
                if isinstance(reply_id, int) and not isinstance(reply_id, bool):
                    observation["received_ids"] = (observation["received_ids"] + [reply_id])[-20:]
                if type(reply_id) is not int or reply_id != 1:
                    observation["other_messages"] += 1
                    continue
                result = response.get("result")
                if "error" in response:
                    observation["status"] = "original_error_reply"
                elif not isinstance(result, dict) or not all(
                        isinstance(result.get(key), str) and result[key]
                        for key in ("protocolVersion", "product")):
                    observation["status"] = "malformed_original_reply"
                else:
                    observation["status"] = "late_valid_original_reply"
                    observation["browser_version"] = {
                        key: result[key][:200] for key in ("protocolVersion", "product")}
                break
            else:
                observation["status"] = "no_original_reply_before_cutoff"
        except OSError as error:
            observation["status"] = "transport_error"
            observation["errno"] = error.errno
        finally:
            observation["finished_elapsed_ms"] = (time.monotonic() - self.started_at) * 1000
            observation["exit_code"] = self.process.poll()

    def close(self):
        try:
            try:
                self.observe_failed_bootstrap()
            except Exception as error:
                # The already-failed test must still close its owned browser if
                # optional observation cannot inspect the process/transport.
                self.bootstrap_observation = {"status": "observation_error", "error_type": type(error).__name__}
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
            try:
                # Normal cleanup may consume a delayed earlier response. Keep
                # that final local snapshot without adding a diagnostic command.
                self.final_diagnostics = self.diagnostics()
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
        # Browser process readiness is separate from product/page commands.
        # CI observed the same first reply at 15.35s with no retransmission.
        # Startup gets one absolute 30s budget from construction (including font
        # preparation); targets and all existing commands keep their 15s limit.
        try:
            if self.browser_version is None:
                self.stage = "browser_handshake"
                deadline = self.started_at + 30
                if self.process.poll() is not None:
                    raise AssertionError("Chrome exited before browser handshake.")
                version = self.call("Browser.getVersion", timeout=deadline - time.monotonic())
                ready_at = time.monotonic()
                if ready_at >= deadline:
                    raise AssertionError("Chrome DevTools response timed out.")
                if not isinstance(version, dict) or not all(
                        isinstance(version.get(key), str) and version[key]
                        for key in ("protocolVersion", "product")):
                    raise AssertionError("Chrome browser handshake did not return protocolVersion and product.")
                self.browser_version = {key: version.get(key) for key in ("protocolVersion", "product", "revision", "jsVersion")}
                self.browser_startup = {"budget_seconds": 30,
                    "ready_elapsed_ms": (ready_at - self.started_at) * 1000,
                    "product": self.browser_version["product"]}
                # Successful Native fixture cases do not have a failure JSON.
                # Keep their actual startup timing in the existing CI log too.
                print("Chrome startup: " + json.dumps(self.browser_startup), file=sys.stderr, flush=True)
            self.stage = "create_target"
            target = self.call("Target.createTarget", {"url": "about:blank"}, timeout=15)["targetId"]
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

    def test_one_startup_budget_accepts_delayed_reply_and_keeps_each_target_at_fifteen_seconds(self):
        for preparation_seconds in (0, 8):
            with self.subTest(preparation_seconds=preparation_seconds):
                browser, _, response_write = self.pipe()
                browser.started_at = 100.0
                clock, commands = [100.0 + preparation_seconds], []
                write = os.write
                def respond(descriptor, payload):
                    count = write(descriptor, payload)
                    if descriptor == browser.request_write:
                        request = json.loads(payload.rstrip(b'\0'))
                        method = request['method']
                        commands.append((method, browser.last_command['timeout_seconds']))
                        result = {}
                        if method == 'Browser.getVersion':
                            clock[0] = 115.35
                            result = {'protocolVersion': '1.3', 'product': 'Synthetic/1'}
                        elif method == 'Target.createTarget': result = {'targetId': 'target'}
                        elif method == 'Target.attachToTarget': result = {'sessionId': 'session'}
                        elif method == 'Page.navigate':
                            write(response_write, b'{"method":"Page.loadEventFired"}\0')
                        write(response_write, json.dumps({'id': request['id'], 'result': result}).encode() + b'\0')
                    return count
                with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(os, 'write', side_effect=respond), patch('builtins.print') as output:
                    browser.navigate('about:blank')
                    browser.navigate('about:blank')
                    startup = browser.diagnostics()['browser_startup']
                self.assertEqual([item for item in commands if item[0] == 'Browser.getVersion'],
                                 [('Browser.getVersion', 30 - preparation_seconds)])
                self.assertEqual([item for item in commands if item[0] == 'Target.createTarget'],
                                 [('Target.createTarget', 15), ('Target.createTarget', 15)])
                self.assertTrue(all(timeout == 15 for method, timeout in commands if method != 'Browser.getVersion'))
                self.assertEqual(browser.stage, 'ready')
                self.assertIsNone(browser.first_failure)
                self.assertAlmostEqual(startup['ready_elapsed_ms'], 15350)
                self.assertEqual(startup['budget_seconds'], 30)
                output.assert_called_once()

    def test_expired_startup_sends_nothing_and_cleanup_does_not_add_a_new_wait(self):
        browser, _, _ = self.pipe()
        browser.started_at = 100.0
        with patch.object(time, 'monotonic', return_value=131.0), \
                patch.object(os, 'write', side_effect=AssertionError('No request after startup cutoff')), \
                self.assertRaisesRegex(AssertionError, 'budget exhausted'):
            browser.navigate('about:blank')
        self.assertEqual(browser.first_failure['stage'], 'browser_handshake')
        self.assertIsNone(browser.browser_version)
        self.assertIsNone(browser.target_id)
        browser, _, _ = self.pipe()
        browser.started_at = 100.0
        clock = [100.0]
        def exhausted_wait(readers, writers, errors, timeout):
            self.assertEqual(timeout, 30.0)
            clock[0] = 130.0
            return [], [], []
        with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(select, 'select', side_effect=exhausted_wait), self.assertRaisesRegex(AssertionError, 'timed out'):
            browser.navigate('about:blank')
        self.assertEqual(browser.first_failure['last_command']['timeout_seconds'], 30.0)
        self.assertEqual(browser.counter, 1)
        with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(browser, 'receive', side_effect=AssertionError('No extra observation wait')) as read:
            browser.observe_failed_bootstrap()
        read.assert_not_called()
        self.assertEqual(browser.bootstrap_observation['status'], 'no_original_reply_before_cutoff')

    def test_buffered_events_cannot_extend_startup_deadline_or_accept_a_late_reply(self):
        browser, _, response_write = self.pipe()
        browser.started_at = 100.0
        clock = [100.0]
        original_receive = browser.receive
        calls = []
        def receive(deadline):
            calls.append(deadline)
            if len(calls) == 1:
                clock[0] = 129.9
                os.write(response_write, b'{"method":"Unknown.event","params":{"private":"synthetic-secret"}}\0'
                         b'{"id":1,"result":{"protocolVersion":"1.3","product":"Synthetic/1"}}\0')
            else:
                clock[0] = 130.1
            return original_receive(deadline)
        with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(browser, 'receive', side_effect=receive), self.assertRaisesRegex(AssertionError, 'timed out'):
            browser.navigate('about:blank')
        self.assertEqual(calls, [130.0, 130.0])
        self.assertIsNone(browser.browser_version)
        self.assertIsNone(browser.target_id)
        self.assertEqual(browser.counter, 1)

    def test_ready_browser_target_still_fails_at_fifteen_seconds_without_retry(self):
        browser, request_read, _ = self.pipe()
        browser.browser_version = {'protocolVersion': '1.3', 'product': 'Synthetic/1'}
        with patch.object(select, 'select', return_value=([], [], [])), self.assertRaisesRegex(AssertionError, 'timed out'):
            browser.navigate('about:blank')
        request = json.loads(os.read(request_read, 4096).rstrip(b'\0'))
        self.assertEqual(request['method'], 'Target.createTarget')
        self.assertEqual(browser.first_failure['last_command']['timeout_seconds'], 15)
        self.assertEqual(browser.first_failure['stage'], 'create_target')
        self.assertEqual(browser.counter, 1)

    def test_invalid_or_exited_startup_never_creates_a_target(self):
        for mode in ('empty', 'missing_product', 'wrong_result_type', 'protocol_error', 'exited'):
            with self.subTest(mode=mode):
                browser, request_read, response_write = self.pipe()
                results = {'empty': {}, 'missing_product': {'protocolVersion': '1.3'}, 'wrong_result_type': []}
                if mode == 'exited':
                    browser.process.poll = lambda: 9
                else:
                    response = ({'id': 1, 'error': {'code': -1, 'message': 'synthetic error'}}
                                if mode == 'protocol_error' else {'id': 1, 'result': results[mode]})
                    os.write(response_write, json.dumps(response).encode() + b'\0')
                with self.assertRaises(AssertionError):
                    browser.navigate('about:blank')
                self.assertIsNone(browser.browser_version)
                self.assertIsNone(browser.target_id)
                self.assertEqual(browser.counter, 0 if mode == 'exited' else 1)
                self.assertEqual(browser.first_failure['stage'], 'browser_handshake')
                if mode != 'exited':
                    request = json.loads(os.read(request_read, 4096).rstrip(b'\0'))
                    self.assertEqual(request['method'], 'Browser.getVersion')

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
        os.write(response_write, b'{"id":1,"result":{"targetId":"late"}}\0{"id":2,"result":{}}\0')
        browser.call("Browser.close")
        self.assertEqual(json.dumps(browser.first_failure, sort_keys=True), original)
        self.assertEqual(browser.first_failure["last_command"]["method"], "Target.createTarget")
        self.assertFalse(browser.first_failure["last_command"]["completed"])
        self.assertIn("synthetic startup diagnostic", browser.first_failure["stderr_tail"])
        self.assertEqual(browser.errors.tell(), original_offset)
        self.assertEqual([reply["id"] for reply in browser.diagnostics()["recent_responses"]], [1, 2])

    def test_normal_close_keeps_final_diagnostics_after_local_stderr_is_closed(self):
        browser, _, _ = self.pipe()
        browser.process.poll = lambda: 0
        browser.errors.write(b"synthetic final diagnostic\n");browser.errors.flush()
        with patch.object(os, "close"), patch.object(os, "killpg"):
            browser.close()
        self.assertTrue(browser.errors.closed)
        self.assertEqual(browser.final_diagnostics["exit_code"], 0)
        self.assertIn("synthetic final diagnostic", browser.final_diagnostics["stderr_tail"])

    def test_observation_error_does_not_prevent_owned_browser_cleanup(self):
        browser, _, _ = self.pipe()
        browser.process.poll = lambda: 0
        with patch.object(browser, "observe_failed_bootstrap", side_effect=RuntimeError("synthetic observer fault")), \
                patch.object(os, "close") as close, patch.object(os, "killpg") as kill:
            browser.close()
        kill.assert_called_once_with(123, signal.SIGKILL)
        self.assertEqual([call.args[0] for call in close.call_args_list], [browser.request_write, browser.response_read])
        self.assertTrue(browser.errors.closed)
        self.assertEqual(browser.final_diagnostics["bootstrap_observation"],
                         {"status": "observation_error", "error_type": "RuntimeError"})

    def timed_out_bootstrap(self):
        browser, _, response_write = self.pipe()
        browser.stage = "browser_handshake"
        with patch.object(select, "select", return_value=([], [], [])), self.assertRaisesRegex(AssertionError, "timed out"):
            browser.call("Browser.getVersion", timeout=.01)
        return browser, response_write

    def test_passive_late_bootstrap_reply_keeps_original_failure_without_writing_or_resuming(self):
        browser, response_write = self.timed_out_bootstrap()
        original = json.dumps(browser.first_failure, sort_keys=True)
        os.write(response_write, b'{"method":"Unknown.event","params":{"private":"synthetic-secret"}}\0'
                 b'{"id":1,"result":{"protocolVersion":"1.3","product":"Synthetic/1","private":"synthetic-secret"}}\0')
        with patch.object(os, "write", side_effect=AssertionError("Observer must not write a request")):
            browser.observe_failed_bootstrap()
        observation = browser.bootstrap_observation
        self.assertEqual(observation["status"], "late_valid_original_reply")
        self.assertEqual(observation["received_ids"], [1])
        self.assertEqual(observation["other_messages"], 1)
        self.assertEqual(observation["browser_version"], {"protocolVersion": "1.3", "product": "Synthetic/1"})
        self.assertEqual(json.dumps(browser.first_failure, sort_keys=True), original)
        self.assertNotIn("synthetic-secret", json.dumps(observation))
        self.assertEqual(browser.counter, 1)
        self.assertIsNone(browser.browser_version)
        self.assertIsNone(browser.session)
        self.assertEqual(browser.stage, "browser_handshake")

    def test_passive_bootstrap_has_absolute_cutoff_and_distinguishes_terminal_results(self):
        cases = (("expired", "no_original_reply_before_cutoff"), ("exited", "process_exited"),
                 ("eof", "transport_closed"), ("malformed", "malformed_response"),
                 ("no_reply", "no_original_reply_before_cutoff"))
        for mode, expected in cases:
            with self.subTest(mode=mode):
                browser, _ = self.timed_out_bootstrap()
                browser.started_at = 100.0
                browser.process.poll = lambda: 7 if mode == "exited" else None
                receive = lambda deadline: None
                if mode == "eof":
                    def receive(deadline): raise AssertionError("Chrome DevTools pipe closed: synthetic")
                elif mode == "malformed":
                    receive = lambda deadline: ["not a CDP object"]
                elif mode == "no_reply":
                    def receive(deadline): raise AssertionError("Chrome DevTools response timed out.")
                with patch.object(time, "monotonic", return_value=131.0 if mode == "expired" else 116.0), \
                        patch.object(browser, "receive", side_effect=receive) as read, \
                        patch.object(os, "write", side_effect=AssertionError("No diagnostic request")):
                    browser.observe_failed_bootstrap()
                self.assertEqual(browser.bootstrap_observation["status"], expected)
                self.assertEqual(browser.bootstrap_observation["launch_cutoff_seconds"], 30)
                if mode in ("expired", "exited"):
                    read.assert_not_called()
                else:
                    read.assert_called_once_with(130.0)

    def test_passive_bootstrap_is_not_used_for_page_failures_or_repeated_cleanup(self):
        browser, _ = self.timed_out_bootstrap()
        browser.first_failure["stage"] = "ready"
        browser.first_failure["last_command"].update(id=40, method="Runtime.evaluate")
        with patch.object(browser, "receive", side_effect=AssertionError("Page failure must not observe startup")):
            browser.observe_failed_bootstrap()
        self.assertIsNone(getattr(browser, "bootstrap_observation", None))
        browser, response_write = self.timed_out_bootstrap()
        os.write(response_write, b'{"id":1,"result":{"protocolVersion":"1.3","product":"Synthetic/1"}}\0')
        browser.observe_failed_bootstrap()
        original = json.dumps(browser.bootstrap_observation, sort_keys=True)
        with patch.object(browser, "receive", side_effect=AssertionError("Observe at most once")):
            browser.observe_failed_bootstrap()
        self.assertEqual(json.dumps(browser.bootstrap_observation, sort_keys=True), original)

    def test_native_fixture_saves_final_diagnostics_without_rewriting_first_evidence(self):
        from ees_work_integrated_fixture import IntegratedNativeCase
        case = IntegratedNativeCase("runTest")
        original = {"browser": {"first_failure": {"stage": "browser_handshake"}}, "page_capture": "unavailable_no_attached_session"}
        final = {"exit_code": 0, "bootstrap_observation": {"status": "late_valid_original_reply"}}
        closed = []
        case.browser = SimpleNamespace(close=lambda: closed.append(True), final_diagnostics=final)
        with tempfile.TemporaryDirectory(prefix="ees-final-bootstrap-evidence-") as directory:
            case.failure_evidence_path = Path(directory) / "failure.json"
            case.failure_evidence_path.write_text(json.dumps(original), encoding="utf-8")
            before = case.failure_evidence_path.read_bytes()
            case.close_browser()
            report = json.loads((Path(directory) / "failure-cleanup.json").read_text(encoding="utf-8"))
            self.assertEqual(case.failure_evidence_path.read_bytes(), before)
            def failed_close(): raise RuntimeError("original close failure")
            case.browser.close = failed_close
            with patch.object(os, "replace", side_effect=OSError("synthetic evidence failure")), \
                    patch("builtins.print") as output, self.assertRaisesRegex(RuntimeError, "original close failure"):
                case.close_browser()
            self.assertEqual(case.failure_evidence_path.read_bytes(), before)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            self.assertIn("OSError", output.call_args.args[0])
        self.assertEqual(closed, [True])
        self.assertEqual(report.pop("browser_cleanup_diagnostics"), final)
        self.assertEqual(report, {"initial_evidence": "failure.json"})

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

    def test_complete_product_and_native_chat_preserve_first_failure_before_page_capture(self):
        from ees_work_integrated_app import ProductGate
        from ees_work_native_chat import NativeChatGate
        self.assertIs(NativeChatGate.capture, ProductGate.capture)
        snapshot = {"stage": "browser_handshake", "first_failure": {
            "last_command": {"method": "Browser.getVersion"}, "stderr_tail": "synthetic diagnostic"}}
        for session in (None, "attached-session"):
            with self.subTest(session=session), tempfile.TemporaryDirectory(prefix="ees-product-diagnostic-") as directory:
                gate = ProductGate.__new__(ProductGate)
                gate.out, gate.report = Path(directory), {"status": "failed"}
                calls = []
                def evaluate(expression):
                    calls.append(expression)
                    raise AssertionError("synthetic page capture failure")
                gate.browser = SimpleNamespace(session=session, diagnostics=lambda: snapshot, evaluate=evaluate)
                if session:
                    with self.assertRaisesRegex(AssertionError, "page capture failure"):
                        gate.capture("failure")
                else:
                    gate.capture("failure")
                    self.assertEqual(calls, [])
                details = json.loads((gate.out / "failure.json").read_text(encoding="utf-8"))
                report = json.loads((gate.out / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(details["browser"], snapshot)
                self.assertEqual(report["browser_diagnostics"], snapshot)
                self.assertEqual(list(gate.out.glob("*.png")), [])

    def test_complete_product_navigation_rejects_old_document_and_wrong_loader(self):
        from ees_work_integrated_app import ProductGate
        gate = ProductGate.__new__(ProductGate)
        gate.base = 'http://127.0.0.1:8123'
        destination = gate.base + '/c/synthetic-chat'
        snapshots = [
            {'ready': 'complete', 'origin': 100, 'url': destination},
            {'ready': 'complete', 'origin': 200, 'url': gate.base + '/'},
            {'ready': 'loading', 'origin': 200, 'url': destination},
            {'ready': 'complete', 'origin': 200, 'url': destination},
        ]
        values, calls, reads = iter([100] + snapshots), [], []
        def evaluate(expression):
            reads.append(expression)
            return next(values)
        def call(method, params=None):
            calls.append((method, params))
            if method == 'Page.navigate':
                return {'loaderId': 'new-loader'}
            self.assertEqual(method, 'Page.getFrameTree')
            return {'frameTree': {'frame': {'loaderId': 'new-loader'}}}
        gate.browser = SimpleNamespace(evaluate=evaluate, call=call)
        with patch.object(time, 'sleep'):
            gate.navigate('/c/synthetic-chat')
        self.assertEqual(len(reads), 5)
        self.assertEqual(calls, [('Page.navigate', {'url': destination}), ('Page.getFrameTree', None)])

        for loader in (None, 'different-loader'):
            with self.subTest(loader=loader):
                values = iter([100, snapshots[-1]])
                gate.browser.evaluate = lambda expression: next(values)
                gate.browser.call = lambda method, params=None: (
                    {'loaderId': 'new-loader'} if method == 'Page.navigate' and loader else
                    {'frameTree': {'frame': {'loaderId': loader}}} if method == 'Page.getFrameTree' else {})
                with self.assertRaises(AssertionError):
                    gate.navigate('/c/synthetic-chat')

        clock, reads, calls = [0.0], [], []
        def stale_document(expression):
            reads.append(expression)
            return 100 if len(reads) == 1 else snapshots[0]
        gate.browser.evaluate = stale_document
        gate.browser.call = lambda method, params=None: calls.append(method) or {'loaderId': 'new-loader'}
        with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + 13)), \
                self.assertRaises(AssertionError):
            gate.navigate('/c/synthetic-chat')
        self.assertEqual(calls, ['Page.navigate'])

    def test_complete_product_typing_never_selects_page_after_input_loses_focus(self):
        from ees_work_integrated_app import ProductGate
        for focused in (False, True):
            with self.subTest(focused=focused):
                gate = ProductGate.__new__(ProductGate)
                clicks, calls, reads = [], [], []
                gate.click = lambda selector: clicks.append(selector)
                gate.browser = SimpleNamespace(
                    evaluate=lambda expression: reads.append(expression) or {'matches': focused},
                    call=lambda method, params=None: calls.append((method, params)))
                if focused:
                    gate.type('#synthetic-input', '입력 값')
                    self.assertEqual([method for method, params in calls], [
                        'Input.dispatchKeyEvent', 'Input.dispatchKeyEvent', 'Input.insertText'])
                    self.assertEqual([params['type'] for method, params in calls[:2]], ['keyDown', 'keyUp'])
                    self.assertTrue(all(params['modifiers'] == 2 and params['key'] == 'a'
                                        for method, params in calls[:2]))
                    self.assertEqual(calls[-1][1], {'text': '입력 값'})
                else:
                    with self.assertRaisesRegex(AssertionError, 'Physical click did not focus the current input'):
                        gate.type('#synthetic-input', '입력 값')
                    self.assertEqual(calls, [])
                self.assertEqual(clicks, ['#synthetic-input'])
                self.assertEqual(len(reads), 1)

    def test_work_panel_wait_requires_loaded_exact_reference_and_visible_control(self):
        from ees_work_integrated_app import ProductGate
        reference = {'workflow_id': 'workflow-one', 'run_id': 'run-one', 'attempt_id': 'attempt-one'}
        ready = {'loaded': True, 'busy': False, 'loading': False, 'error': None,
                 'reference': reference, 'selector_visible': True}
        incomplete = [
            {**ready, 'loaded': False}, {**ready, 'busy': True},
            {**ready, 'loading': True}, {**ready, 'error': 'Synthetic panel failure'},
            {**ready, 'selector_visible': False}, {**ready, 'reference': {}},
            *[{**ready, 'reference': {**reference, key: 'other'}} for key in reference],
        ]
        arguments = dict(reference, selector='#synthetic-control')
        gate = ProductGate.__new__(ProductGate)
        values, observed = iter(incomplete + [ready]), []
        def evaluate(expression):
            observed.append(expression)
            return next(values)
        gate.browser = SimpleNamespace(evaluate=evaluate)
        with patch.object(time, 'sleep'):
            self.assertEqual(gate.wait_work_ready(**arguments), ready)
        self.assertEqual(len(observed), len(incomplete) + 1)

        for index, snapshot in enumerate(incomplete):
            with self.subTest(incomplete=index):
                clock = [0.0]
                gate.browser.evaluate = lambda expression: snapshot
                with patch.object(time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + 13)), \
                        self.assertRaisesRegex(AssertionError, 'Work panel did not settle'):
                    gate.wait_work_ready(**arguments)

        # Omitting a reference constraint must not invent a selected run or
        # attempt, but the actual loaded panel still has to be ready.
        unselected = {**ready, 'reference': {}}
        gate.browser.evaluate = lambda expression: unselected
        self.assertEqual(gate.wait_work_ready(), unselected)

    def test_historical_request_route_keeps_main_guards_and_only_accepts_exact_retrieval_template(self):
        from ees_work_integrated_app import historical_request_route, WORK_REFERENCE_PREFIX
        question = '이 당시 조회 시도의 프로젝트와 결과만 설명해 줘.'
        template = 'Task: Generate retrieval queries.\nDate: {{CURRENT_DATE}}\nChat:\n{{MESSAGES:END:6}}\nReturn query JSON only.'
        content = template.replace('{{CURRENT_DATE}}', '2026-10-02').replace(
            '{{MESSAGES:END:6}}', 'USER: ' + question + '\nASSISTANT: synthetic previous answer')
        query = {'messages': [{'role': 'user', 'content': content}], 'stream': False}
        route = historical_request_route(query, question, template)
        self.assertEqual(route['kind'], 'native_retrieval_query')
        self.assertEqual(route['roles'], ['user'])
        self.assertEqual(route['message_count'], 1)
        self.assertFalse(route['exact_question'])
        self.assertFalse(route['has_historical_reference'])
        self.assertTrue(route['question_in_content'])
        self.assertEqual(route['contents'][0]['sha256'],
                         hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest())

        # Missing main reference stays in the strict main assertion path. It
        # must never become an allowed background request merely for lacking it.
        main_messages = [{'role': 'user', 'content': question}]
        reference_message = {'role': 'system', 'content': WORK_REFERENCE_PREFIX + '{"read_only":true}'}
        for messages in (main_messages, [reference_message] + main_messages,
                         main_messages + [{'role': 'assistant', 'content': None},
                                          {'role': 'tool', 'content': '{"ok":true}'}],
                         [reference_message, {'role': 'user', 'content': content}]):
            with self.subTest(messages=messages):
                result = historical_request_route({'messages': messages, 'stream': False}, question, template)
                self.assertEqual(result['kind'], 'historical_main')
        self.assertFalse(historical_request_route({'messages': main_messages}, question, template)
                         ['has_historical_reference'])

        unknown = [
            {'messages': [{'role': 'user', 'content': 'prefix\n' + content}], 'stream': False},
            {'messages': [{'role': 'user', 'content': content + '\nsuffix'}], 'stream': False},
            {'messages': [{'role': 'user', 'content': content.replace('2026-10-02', 'October 2')}], 'stream': False},
            {'messages': [{'role': 'user', 'content': content.replace('query JSON only', 'plain text')}], 'stream': False},
            {**query, 'stream': True},
            {**query, 'stream': None},
            {**query, 'tools': [{'type': 'function', 'function': {'name': 'synthetic-tool'}}]},
            {**query, 'messages': [{'role': 'system', 'content': content}]},
            {**query, 'messages': query['messages'] + [{'role': 'assistant', 'content': 'synthetic'}]},
            {**query, 'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': content}]}]},
            {'messages': [], 'stream': False},
        ]
        for index, payload in enumerate(unknown):
            with self.subTest(unknown=index):
                self.assertEqual(historical_request_route(payload, question, template)['kind'], 'unknown')


if __name__ == "__main__":
    unittest.main()
