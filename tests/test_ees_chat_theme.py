"""Chrome cascade and trusted resize input on a native-DOM fixture, not the app.

Uses CSS/fonts from the built pinned wheel and the real panel styles/scripts.
No Open WebUI import, user data, npm dependency, or external page is involved.
EES_TEST_CHROME makes Chrome and EES_TEST_BRANDING_DIR mandatory in Linux CI.
"""

import functools
import html
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class ChromePipe:
    """Small Linux-only CDP client for this fixture's trusted input checks.

    Uses Chrome's local inherited pipes, not a debugging TCP port or an npm
    dependency. Every response has a deadline; browser/profile cleanup is local.
    """

    def __init__(self, chrome, profile):
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
                stdout=subprocess.DEVNULL, stderr=self.errors)
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


class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_result = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "pre" and dict(attrs).get("id") == "ees-theme-result":
            self.in_result = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_result = False

    def handle_data(self, data):
        if self.in_result:
            self.parts.append(data)


class FixtureHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, assets, **kwargs):
        self.assets = assets
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        content = self.assets.get(path)
        if content is None:
            self.send_error(404)
            return
        self.send_response(200)
        content_type = "text/html" if path == "/c/browser-check" else mimetypes.guess_type(path)[0]
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


def panel_styles():
    """Read real constant styles; do not duplicate their :host declarations."""
    paths = (
        ROOT / "agent-pack/skills/cross-system-analysis/ui/cooperation-panel.js",
        ROOT / "agent-pack/skills/ems-work-order/scripts/wo_demo_tool.py",
    )
    styles = []
    for path in paths:
        match = re.search(r"<style>(.*?)</style>", path.read_text(encoding="utf-8"), re.DOTALL)
        if match is None:
            raise AssertionError(f"Panel style template was not found: {path.name}")
        styles.append(match.group(1))
    return styles


# Classes and IDs below follow pinned 0.11.3 Chat, MessageInput and Messages
# templates. Only layout-bearing wrappers needed for cascade checks are included.
FIXTURE = """<!doctype html><html class="__MODE__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">__STYLES__</head>
<body><div id="layout-row" class="flex w-full" style="height:100vh">
<aside id="sidebar" class="hidden md:flex shrink-0" style="width:260px;flex-basis:260px"><span>대화 목록</span></aside>
<main id="chat-container" class="flex flex-col min-w-0 w-full">
<nav><div><button>EES 통합 Assistant</button></div><div class="flex-none items-center gap-2 self-center"><div><button aria-label="Controls">Controls</button></div></div><div id="navbar-bg-gradient-to-b"></div></nav>
<div id="chat-pane" class="flex flex-col flex-auto w-full overflow-auto">
<div id="messages-container" class="flex flex-col w-full max-w-full overflow-auto">
<div class="message-listitem flex flex-col px-3.5 mb-3 w-full max-w-[58rem] mx-auto">
<div class="chat-user"><div class="flex justify-end pb-1"><div id="user-bubble" class="rounded-3xl max-w-[90%] px-4 py-1.5 bg-gray-50 dark:bg-gray-850">
<div class="markdown-prose">조립 2라인의 개선 기회를 찾아줘.</div></div></div></div></div>
<div id="answer-row" class="message-listitem flex flex-col px-3.5 mb-3 w-full max-w-[58rem] mx-auto">
<div class="chat-assistant"><div id="answer" class="markdown-prose">
<h1 id="answer-heading">정비 후 재개 구간을 확인하세요.</h1>
<p id="answer-text">정비 이력과 운전 조건을 비교했습니다. <a id="answer-link" href="#evidence">판단 근거</a></p>
<pre><code id="answer-code">SELECT equipment_id FROM approved_view;</code></pre>
<span id="answer-math" class="katex">x + y</span>
</div></div></div></div>
<div class="w-full"><div class="mx-auto inset-x-0 bg-transparent flex justify-center"><div class="flex flex-col px-3 max-w-[58rem] w-full"><div class="relative"></div></div></div>
<div class="bg-transparent"><div id="composer-row" class="max-w-[58rem] px-2 mx-auto inset-x-0"><div><form class="w-full flex flex-col gap-1.5">
<div id="message-input-container" class="flex-1 flex flex-col relative w-full shadow-lg rounded-3xl border px-0.5 bg-gray-50">
<div class="px-2 relative"><div id="chat-input-container"><div class="relative w-full min-w-full input-prose min-h-fit h-full"><div id="chat-input" class="tiptap ProseMirror" contenteditable="true"><p>다음에 확인할 내용을 입력하세요.</p></div></div></div></div>
</div></form></div></div></div></div></div></main></div>
<aside id="ees-cooperation-panel" style="width:480px;max-width:100%"></aside>
<aside id="ees-wo-demo-panel"></aside>
<pre id="ees-theme-result" hidden></pre>
<script>
(async () => {
  const output = document.getElementById('ees-theme-result');
  try {
    const styles = __PANEL_STYLES__;
    const analysis = document.getElementById('ees-cooperation-panel').attachShadow({mode:'open'});
    analysis.innerHTML = '<style>' + styles[0] + '</style><section class="frame"><p id="text" class="reply">분석 결과</p><button id="button">판단 근거</button><p id="muted" class="muted">추가 확인</p><span id="accent" class="pill">진행 중</span></section>';
    const wo = document.getElementById('ees-wo-demo-panel').attachShadow({mode:'open'});
    wo.innerHTML = '<style>' + styles[1] + '</style><div class="panel"><p id="text">설비 조회</p><input id="input" value="조립 2라인"><p id="muted" class="eyebrow">작업 정보</p><span id="accent" class="origin">확인됨</span></div>';
    const loaded = await Promise.all([
      document.fonts.load('400 14px "EES Inter"', 'EES 0123'),
      document.fonts.load('500 14px "EES Noto Sans KR"', '조립 개선'),
    ]);
    await document.fonts.ready;
    const style = element => {
      const s = getComputedStyle(element);
      return {font:s.fontFamily, size:s.fontSize, line:s.lineHeight,
        color:s.color, background:s.backgroundColor, radius:s.borderTopLeftRadius,
        maxWidth:s.maxWidth, padding:s.paddingLeft};
    };
    const node = id => style(document.getElementById(id));
    const result = {
      width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
      fonts:loaded.map(list => list.map(face => ({family:face.family,status:face.status}))),
      chat:node('chat-container'), sidebar:node('sidebar'), answer:node('answer'),
      text:node('answer-text'), link:node('answer-link'), code:node('answer-code'),
      math:node('answer-math'), bubble:node('user-bubble'), heading:node('answer-heading'),
      row:node('answer-row'), composer:node('message-input-container'), input:node('chat-input'),
      analysis:{host:node('ees-cooperation-panel'), text:style(analysis.getElementById('text')),
        button:style(analysis.getElementById('button')), muted:style(analysis.getElementById('muted')),
        accent:style(analysis.getElementById('accent')), frame:style(analysis.querySelector('.frame'))},
      wo:{host:node('ees-wo-demo-panel'), text:style(wo.getElementById('text')),
        input:style(wo.getElementById('input')), muted:style(wo.getElementById('muted')),
        accent:style(wo.getElementById('accent'))},
    };
    document.documentElement.style.setProperty('--app-text-scale', '1.25');
    result.scaledAnswerSize = getComputedStyle(document.getElementById('answer')).fontSize;
    document.documentElement.style.removeProperty('--app-text-scale');
    output.textContent = JSON.stringify(result);
  } catch(error) { output.textContent = JSON.stringify({error:String(error)}); }
})();
</script></body></html>"""


def interaction_fixture(fixture):
    """Use the real coordinator and panel; only the surrounding app DOM is fake."""
    markup = fixture.split("<script>", 1)[0]
    markup = re.sub(r'<aside id="ees-(?:cooperation-panel|wo-demo-panel)"[^>]*></aside>', "", markup)
    update = {"version": 1, "kind": "plan", "chat_id": "browser-check",
              "message_id": "message-check", "call_id": "plan-check", "batch_id": "plan-check",
              "seq": 1, "phase": "planned", "title": "조립 2라인 개선 기회", "steps": []}
    panel = (ROOT / "agent-pack/skills/cross-system-analysis/ui/cooperation-panel.js").read_text(encoding="utf-8")
    shared = (ROOT / "agent-pack/skills/cross-system-analysis/ui/work-panel.js").read_text(encoding="utf-8")
    return (markup + "<script>" + shared + "\nwindow.eesFixtureReady=(function(eesPanelUpdate){\n"
            + panel + "\n})(" + json.dumps(update) + ");</script></body></html>")


MEASURE = """(() => {
  const rect = id => {
    const r = document.getElementById(id)?.getBoundingClientRect();
    return r ? {x:r.x,y:r.y,width:r.width,height:r.height} : null;
  };
  const divider = document.getElementById('ees-cooperation-resizer');
  const grip = divider?.querySelector('span');
  const outline = node => node ? {style:getComputedStyle(node).outlineStyle,
    width:getComputedStyle(node).outlineWidth,color:getComputedStyle(node).outlineColor} : null;
  return {viewport:{width:innerWidth,height:innerHeight}, scroll:document.documentElement.scrollWidth,
    sidebar:rect('sidebar'), chat:rect('chat-container'), row:rect('answer-row'),
    composer:rect('composer-row'), input:rect('message-input-container'), editor:rect('chat-input'),
    panel:rect('ees-cooperation-panel'), divider:rect('ees-cooperation-resizer'),
    grip:grip ? {height:grip.getBoundingClientRect().height,outline:outline(grip)} : null,
    outline:outline(divider), focused:document.activeElement?.id,
    focusVisible:divider?.matches(':focus-visible'), selection:document.body.style.userSelect,
    cursor:document.body.style.cursor, events:window.eesTrustedEvents || []};
})()"""


class ChatThemeBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get("EES_TEST_CHROME")
        cls.chrome = shutil.which(explicit) if explicit else next(
            (path for name in ("google-chrome", "chromium", "chromium-browser")
             if (path := shutil.which(name))), None)
        if not cls.chrome:
            if explicit:
                raise RuntimeError("EES_TEST_CHROME was set but its executable is unavailable.")
            raise unittest.SkipTest("Chrome is not installed; Linux CI runs this check explicitly.")
        directory = os.environ.get("EES_TEST_BRANDING_DIR")
        if not directory:
            if explicit:
                raise RuntimeError("EES_TEST_BRANDING_DIR is required with EES_TEST_CHROME.")
            raise unittest.SkipTest("Set EES_TEST_BRANDING_DIR to the built pinned EES wheel.")
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        cls.assets = {}
        with ZipFile(directory / manifest["wheel"]["filename"]) as wheel:
            prefix = "open_webui/frontend/"
            for name in wheel.namelist():
                if name.startswith(prefix) and name.endswith((".css", ".ttf", ".woff", ".woff2")):
                    cls.assets["/" + name[len(prefix):]] = wheel.read(name)
        theme = "/_ees5/chat-theme.css"
        if theme not in cls.assets:
            raise AssertionError("The built wheel does not contain the ees.5 theme.")
        # Use actual upstream global/chat/markdown/KaTeX styles. The theme is the
        # last initial index.html link; lazy chat styles may arrive afterward.
        css = sorted(path for path in cls.assets if path.endswith(".css")
                     and "/immutable/assets/" in path
                     and Path(path).name.startswith(("0.", "Chat.", "Messages.", "katex.")))
        if len(css) != 4:
            raise AssertionError("The pinned upstream style fixture selection changed.")
        links = "".join('<link rel="stylesheet" href="' + html.escape(path) + '">'
                        for path in css[:1] + [theme] + css[1:])
        fixture = FIXTURE.replace("__STYLES__", links).replace("__PANEL_STYLES__", json.dumps(panel_styles()))
        for mode in ("light", "dark"):
            cls.assets["/" + mode + ".html"] = fixture.replace("__MODE__", mode).encode()
        cls.assets["/c/browser-check"] = interaction_fixture(fixture).replace("__MODE__", "light").encode()
        handler = functools.partial(FixtureHandler, assets=cls.assets)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.addClassCleanup(cls.server.server_close)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.shutdown)

    def render(self, mode, width):
        with tempfile.TemporaryDirectory(prefix="ees-theme-chrome-") as profile:
            command = [self.chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                       "--disable-dev-shm-usage", "--disable-background-networking",
                       "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                       "--force-device-scale-factor=1", "--hide-scrollbars",
                       "--user-data-dir=" + profile, "--window-size=" + str(width) + ",1000",
                       "--virtual-time-budget=15000", "--dump-dom",
                       f"http://127.0.0.1:{self.server.server_port}/{mode}.html"]
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
        self.assertEqual(run.returncode, 0, run.stderr[-3000:])
        parser = ResultParser()
        parser.feed(run.stdout)
        self.assertTrue(parser.parts, "Chrome produced no completed font/cascade result. " + run.stderr[-1500:])
        result = json.loads("".join(parser.parts))
        self.assertNotIn("error", result, result.get("error"))
        return result

    def test_real_css_fonts_and_shadow_cascade_in_three_viewports(self):
        for mode, width in (("light", 1240), ("dark", 1240), ("light", 640)):
            with self.subTest(mode=mode, width=width):
                r = self.render(mode, width)
                try:
                    dark = mode == "dark"
                    paper = "rgb(25, 29, 35)" if dark else "rgb(255, 255, 255)"
                    ink = "rgb(232, 237, 245)" if dark else "rgb(32, 44, 62)"
                    side = "rgb(20, 24, 30)" if dark else "rgb(245, 247, 250)"
                    soft = "rgb(36, 44, 54)" if dark else "rgb(240, 244, 248)"
                    muted = "rgb(166, 178, 195)" if dark else "rgb(100, 113, 135)"
                    blue = "rgb(145, 189, 223)" if dark else "rgb(55, 101, 139)"
                    for loaded, family in zip(r["fonts"], ("EES Inter", "EES Noto Sans KR")):
                        self.assertTrue(any(face["family"].strip('"') == family and face["status"] == "loaded"
                                            for face in loaded), loaded)
                    self.assertEqual(r["chat"]["background"], paper)
                    self.assertEqual(r["sidebar"]["background"], side)
                    self.assertEqual(r["text"]["color"], ink)
                    self.assertEqual(r["link"]["color"], blue)
                    self.assertEqual(r["bubble"]["background"], soft)
                    self.assertEqual(r["composer"]["background"], paper)
                    self.assertEqual(r["composer"]["radius"], "12px")
                    self.assertEqual(r["answer"]["size"], "14px")
                    self.assertEqual(r["scaledAnswerSize"], "17.5px")
                    self.assertAlmostEqual(float(r["answer"]["line"].removesuffix("px")), 27.3, places=1)
                    self.assertEqual(r["input"]["size"], "13px")
                    self.assertIn("monospace", r["code"]["font"])
                    self.assertNotIn("EES", r["code"]["font"])
                    self.assertIn("KaTeX", r["math"]["font"])
                    self.assertNotIn("EES", r["math"]["font"])
                    for node in (r["answer"], r["input"], r["analysis"]["text"],
                                 r["analysis"]["button"], r["wo"]["text"], r["wo"]["input"]):
                        self.assertTrue(node["font"].startswith('"EES Inter"'), node["font"])
                        self.assertIn('"EES Noto Sans KR"', node["font"])
                    self.assertEqual(r["analysis"]["frame"]["background"], side)
                    for panel in (r["analysis"], r["wo"]):
                        self.assertEqual(panel["text"]["color"], ink)
                        self.assertEqual(panel["muted"]["color"], muted)
                        self.assertEqual(panel["accent"]["color"], blue)
                    self.assertEqual(r["wo"]["host"]["background"], paper)
                    self.assertEqual(r["row"]["maxWidth"], "1024px")
                    self.assertLessEqual(r["scrollWidth"], r["width"] + 1)
                    self.assertEqual(r["row"]["padding"], "18px" if width <= 700 else "28px")
                    self.assertEqual(r["heading"]["size"], "20px" if width <= 700 else "21px")
                    if width <= 700:
                        self.assertLessEqual(r["width"], 700)
                except AssertionError as error:
                    # One failed expectation must still expose every computed
                    # value, so a remote CI round can reveal all cascade clashes.
                    diagnostics = json.dumps(r, ensure_ascii=False, sort_keys=True)
                    raise self.failureException(str(error) + "\nComputed styles: " + diagnostics) from None

    def test_desktop_width_and_trusted_panel_resize_focus(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Inherited Chrome DevTools pipes are exercised in Linux CI.")
        with tempfile.TemporaryDirectory(prefix="ees-resize-chrome-") as profile:
            browser = ChromePipe(self.chrome, profile)
            try:
                browser.navigate(f"http://127.0.0.1:{self.server.server_port}/c/browser-check")
                self.assertEqual(browser.evaluate("window.eesFixtureReady"), {"ok": True, "updated": True})
                browser.evaluate("document.fonts.ready.then(() => true)")

                def measure():
                    browser.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))")
                    return browser.evaluate(MEASURE)

                def widths(result, panel_width=None):
                    details = json.dumps(result, ensure_ascii=False)
                    self.assertEqual(result["viewport"], {"width": 1920, "height": 1080}, details)
                    self.assertEqual(result["sidebar"]["width"], 260, details)
                    if panel_width is None:
                        self.assertIsNone(result["panel"], details)
                    else:
                        self.assertAlmostEqual(result["panel"]["width"], panel_width, delta=1, msg=details)
                    expected = min(1024, 1920 - 260 - (panel_width + 10 if panel_width else 0))
                    for key in ("row", "composer"):
                        self.assertAlmostEqual(result[key]["width"], expected, delta=1, msg=details)
                    # Pinned MessageInput has outer px-2, then border/px-0.5,
                    # inner px-2 and the theme's 6px editor-container padding.
                    # The max-width wrapper is wider than the composer/editor.
                    self.assertAlmostEqual(result["input"]["width"], expected - 16, delta=1, msg=details)
                    self.assertAlmostEqual(result["editor"]["width"], expected - 50, delta=1, msg=details)
                    self.assertLessEqual(result["scroll"], 1921, details)
                    self.assertAlmostEqual(result["row"]["x"], result["composer"]["x"], delta=1, msg=details)
                    self.assertAlmostEqual(result["input"]["x"], result["composer"]["x"] + 8, delta=1, msg=details)

                widths(measure(), 480)
                browser.evaluate("window.__eesWorkPanelV1.close('browser-check')")
                widths(measure())
                browser.evaluate("window.__eesWorkPanelV1.select('browser-check','analysis',{open:true,focus:false})")
                initial = measure()
                widths(initial, 480)
                browser.evaluate("window.eesTrustedEvents=[];['pointerdown','keydown'].forEach(type=>document.addEventListener(type,e=>window.eesTrustedEvents.push({type:e.type,key:e.key||'',trusted:e.isTrusted}),true))")
                x = initial["divider"]["x"] + initial["divider"]["width"] / 2
                y = initial["divider"]["y"] + initial["divider"]["height"] / 2
                browser.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                browser.call("Input.dispatchMouseEvent", {
                    "type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
                browser.call("Input.dispatchMouseEvent", {
                    "type": "mouseMoved", "x": x - 160, "y": y, "button": "left", "buttons": 1})
                dragging = measure()
                widths(dragging, 640)
                self.assertEqual(dragging["focused"], "ees-cooperation-resizer", dragging)
                # Chrome may retain :focus-visible after programmatic focus in
                # pointerdown. Assert the actual visible outline, not heuristics.
                self.assertEqual(dragging["outline"]["style"], "none", dragging)
                self.assertEqual(dragging["grip"]["outline"]["style"], "none", dragging)
                self.assertEqual(dragging["selection"], "none", dragging)
                browser.call("Input.dispatchMouseEvent", {
                    "type": "mouseReleased", "x": x - 160, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
                released = measure()
                self.assertEqual(released["selection"], "", released)
                self.assertEqual(released["cursor"], "", released)
                self.assertEqual(released["outline"]["style"], "none", released)
                self.assertEqual(released["grip"]["outline"]["style"], "none", released)

                # Put the starting focus in the last native chat control. The
                # following Tab and ArrowLeft go through Chrome's trusted input
                # pipeline, not dispatchEvent or direct separator.focus().
                browser.evaluate("document.getElementById('chat-input').focus()")
                for key, code in (("Tab", 9), ("ArrowLeft", 37)):
                    for event_type in ("keyDown", "keyUp"):
                        browser.call("Input.dispatchKeyEvent", {
                            "type": event_type, "key": key, "code": key,
                            "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code})
                    result = measure()
                    widths(result, 640 if key == "Tab" else 660)
                    self.assertEqual(result["focused"], "ees-cooperation-resizer", result)
                    self.assertTrue(result["focusVisible"], result)
                    self.assertEqual(result["outline"]["style"], "none", result)
                    self.assertEqual(result["grip"]["outline"]["style"], "solid", result)
                    self.assertEqual(result["grip"]["outline"]["width"], "2px", result)
                    self.assertEqual(result["grip"]["height"], 36, result)
                self.assertTrue(any(e["type"] == "pointerdown" for e in result["events"]), result)
                self.assertEqual([e["key"] for e in result["events"] if e["type"] == "keydown"], ["Tab", "ArrowLeft"], result)
                self.assertTrue(all(e["trusted"] for e in result["events"]), result)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
