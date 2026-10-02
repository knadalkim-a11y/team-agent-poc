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
                self.errors.seek(0)
                raise AssertionError("Chrome DevTools pipe closed: " + self.errors.read().decode(errors="replace")[-2000:])
            self.buffer += chunk
        message, self.buffer = self.buffer.split(b"\0", 1)
        return json.loads(message)

    def call(self, method, params=None, timeout=15):
        self.counter += 1
        request = {"id": self.counter, "method": method, "params": params or {}}
        if self.session:
            request["sessionId"] = self.session
        payload = json.dumps(request).encode() + b"\0"
        while payload:
            payload = payload[os.write(self.request_write, payload):]
        deadline = time.monotonic() + timeout
        while True:
            response = self.receive(deadline)
            if response.get("id") == self.counter:
                if "error" in response:
                    raise AssertionError(f"{method}: {response['error']}")
                return response.get("result", {})
            self.events.append(response)

    def navigate(self, url):
        target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.session = self.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
        self.events.clear()
        self.call("Page.navigate", {"url": url})
        deadline = time.monotonic() + 15
        while not any(event.get("method") == "Page.loadEventFired" for event in self.events):
            self.events.append(self.receive(deadline))

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


if __name__ == "__main__":
    unittest.main()
