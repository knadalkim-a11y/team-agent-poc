"""Real Chrome UI flows for the isolated EES Work demonstration assets.

This local fixture serves the shipped HTML/CSS/JS, without importing Open WebUI,
opening a user database, or registering tools. Authentication and wheel routes
have separate wrapper tests. UI mutations use trusted Chrome mouse/key input;
DOM evaluation only locates controls and reads visible results. No npm package
or runtime dependency is required. Linux CI sets EES_TEST_CHROME explicitly so
an unavailable browser fails that gate instead of silently skipping it.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ast
import base64
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
from zipfile import ZipFile

from test_ees_chat_theme import ChromePipe


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "agent-pack/skills/ees-work-demo/ui"


NATIVE_FIXTURE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link rel="stylesheet" href="/_ees5/ees-work-launcher.css">
<script defer src="/_ees5/ees-work-launcher.js"></script></head><body>
<aside id="sidebar"><button id="sidebar-new-chat-button">새 대화</button>
<button id="sidebar-search-button">대화 검색</button><a href="/workspace/models">모델 설정</a>
<a href="/workspace/tools">도구 설정</a><a href="/workspace/knowledge">지식 설정</a></aside>
<main><article id="native-history">기존 대화와 Confluence · Jira · GitHub 조회 기록</article>
<label for="native-input">새 메시지</label><textarea id="native-input"></textarea></main>
</body></html>"""


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        content = self.server.assets.get(path)
        if content is None:
            self.send_error(404)
            return
        self.send_response(200)
        content_type = "text/html" if path in {"/ees-work-demo/", "/c/existing-chat", "/auth"} else mimetypes.guess_type(path)[0]
        self.send_header("Content-Type", (content_type or "text/plain") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        headers = self.server.demo_headers if path.startswith("/ees-work-demo/") else {"Cache-Control": "no-store"}
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


class EESWorkDemoBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get("EES_TEST_CHROME")
        cls.chrome = shutil.which(explicit) if explicit else next(
            (path for name in ("google-chrome", "chromium", "chromium-browser")
             if (path := shutil.which(name))), None)
        if not cls.chrome:
            if explicit:
                raise RuntimeError("EES_TEST_CHROME executable is unavailable.")
            raise unittest.SkipTest("Chrome unavailable; Linux CI runs the required browser gate.")
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("The inherited Chrome DevTools pipe fixture requires Linux.")
        names = ("index.html", "ees-work.css", "ees-work.js")
        directory = os.environ.get("EES_TEST_BRANDING_DIR")
        if directory:
            directory = Path(directory)
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            with ZipFile(directory / manifest["wheel"]["filename"]) as wheel:
                assets = {name: wheel.read("open_webui/ees_work_demo_ui/" + name) for name in names}
                route_source = wheel.read("open_webui/ees_work_demo.py").decode("utf-8")
                launcher = {name: wheel.read("open_webui/frontend/_ees5/" + name)
                            for name in ("ees-work-launcher.js", "ees-work-launcher.css")}
        else:
            assets = {name: (UI / name).read_bytes() for name in names}
            route_source = (UI.parent / "scripts/ees_work_demo.py").read_text(encoding="utf-8")
            launcher = {name: (ROOT / "branding/ees/ui" / name).read_bytes()
                        for name in ("ees-work-launcher.js", "ees-work-launcher.css")}
        # Use the actual route's CSP without importing FastAPI/Open WebUI.
        route_ast = ast.parse(route_source)
        headers = next(ast.literal_eval(node.value) for node in route_ast.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "HEADERS" for target in node.targets))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
        cls.server.demo_headers = headers
        cls.server.assets = {"/ees-work-demo/" + name: data for name, data in assets.items()}
        cls.server.assets["/ees-work-demo/"] = assets["index.html"]
        cls.server.assets.update({"/_ees5/" + name: data for name, data in launcher.items()})
        cls.server.assets.update({path: NATIVE_FIXTURE.encode() for path in ("/c/existing-chat", "/auth")})
        cls.addClassCleanup(cls.server.server_close)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.shutdown)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/ees-work-demo/"

    def setUp(self):
        self.profile = tempfile.TemporaryDirectory(prefix="ees-work-chrome-")
        self.addCleanup(self.profile.cleanup)
        self.browser = ChromePipe(self.chrome, self.profile.name)
        self.addCleanup(self.browser.close)
        self.browser.navigate("about:blank")
        self.browser.call("Network.enable")
        self.browser.call("Runtime.enable")
        self.browser.call("Log.enable")
        self.browser.events.clear()
        self.browser.call("Page.navigate", {"url": self.url})
        self.wait("document.querySelector('#m-work-content h2')?.textContent === '신규 공장 횡전개'")

    def tearDown(self):
        # Capture a failed scenario's last visible state before protocol cleanup.
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        if any(case is self or getattr(case, "test_case", None) is self for case, _ in failures):
            self.screenshot(self._testMethodName + "-failure")
        # Flush pending protocol events before examining every page request.
        self.browser.evaluate("document.readyState")
        requests = [e["params"]["request"] for e in self.browser.events
                    if e.get("method") == "Network.requestWillBeSent"]
        self.assertTrue(requests, "No network events captured by the real browser.")
        for request in requests:
            parsed = urlsplit(request["url"])
            self.assertEqual(parsed.hostname, "127.0.0.1", request["url"])
            self.assertEqual(request["method"], "GET", request)
            self.assertIn(parsed.path, set(self.server.assets) | {"/favicon.ico"}, request)
        errors = [e["params"] for e in self.browser.events if e.get("method") == "Runtime.exceptionThrown"]
        self.assertEqual(errors, [], errors)
        security_errors = [e["params"]["entry"] for e in self.browser.events
                           if e.get("method") == "Log.entryAdded"
                           and e["params"]["entry"].get("source") == "security"
                           and e["params"]["entry"].get("level") == "error"]
        self.assertEqual(security_errors, [], security_errors)

    def screenshot(self, name):
        directory = os.environ.get("EES_TEST_SCREENSHOT_DIR")
        if not directory:
            return
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        data = self.browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]
        (directory / (name + ".png")).write_bytes(base64.b64decode(data))

    def wait(self, expression, timeout=6000):
        # Bounded polling in the browser avoids fixed animation sleeps.
        result = self.browser.evaluate("new Promise(resolve => { const end=performance.now()+" + str(timeout)
            + "; const check=()=>{if(" + expression + ")resolve(true);else if(performance.now()>end)resolve(false);"
            + "else setTimeout(check,25)};check()})")
        self.assertTrue(result, "Timed out: " + expression + "\n" + self.text("body"))

    def read(self, selector, prop="textContent"):
        return self.browser.evaluate("document.querySelector(" + json.dumps(selector) + ")?." + prop)

    def text(self, selector):
        return self.read(selector, "innerText") or ""

    def click(self, selector):
        point = self.browser.evaluate("(() => {const e=[...document.querySelectorAll("
            + json.dumps(selector) + ")].find(e=>e.getClientRects().length);if(!e)return null;"
            + "e.scrollIntoView({block:'center',inline:'nearest'});const r=e.getBoundingClientRect();"
            + "return {x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!e.disabled};})()")
        self.assertIsNotNone(point, "Visible control missing: " + selector)
        self.assertFalse(point["disabled"], "Control disabled: " + selector)
        for event_type in ("mousePressed", "mouseReleased"):
            self.browser.call("Input.dispatchMouseEvent", {
                "type": event_type, "x": point["x"], "y": point["y"],
                "button": "left", "buttons": 1 if event_type == "mousePressed" else 0, "clickCount": 1})

    def key(self, key, code, modifiers=0):
        for event_type in ("keyDown", "keyUp"):
            self.browser.call("Input.dispatchKeyEvent", {
                "type": event_type, "key": key, "code": key,
                "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code, "modifiers": modifiers})

    def fill(self, selector, text):
        self.click(selector)
        self.key("a", 65, modifiers=2)
        self.browser.call("Input.insertText", {"text": text})
        self.key("Tab", 9)
        self.assertEqual(self.read(selector, "value"), text)

    def select(self, selector, value):
        index = self.browser.evaluate("[...document.querySelector(" + json.dumps(selector)
            + ").options].findIndex(o=>o.value===" + json.dumps(value) + ")")
        self.assertGreaterEqual(index, 0, selector + " missing option " + value)
        self.click(selector)
        self.key("Home", 36)
        for _ in range(index):
            self.key("ArrowDown", 40)
        self.key("Enter", 13)
        self.key("Tab", 9)
        self.assertEqual(self.read(selector, "value"), value)

    def choose(self, node):
        self.click('[data-node="' + node + '"]')

    def chat(self, text):
        self.fill("#m-input", text)
        self.click('#m-chat button[type="submit"]')

    def run_job(self, expected="완료"):
        self.click('#m-work-content [data-action="run"]')
        self.wait("document.querySelector('#m-work-content .panel-meta .m-state')?.textContent === "
                  + json.dumps(expected))

    def checks(self):
        return self.browser.evaluate("[...document.querySelectorAll('#m-work-content .m-check .m-state')].map(e=>e.textContent)")

    def progress(self, done, total):
        self.choose("setup-p")
        self.assertEqual(self.read('progress[aria-label="필수 잡 완료"]', "value"), done)
        self.assertEqual(self.read('progress[aria-label="필수 잡 완료"]', "max"), total or 1)
        self.assertIn(f"필수 잡 {done} / {total} 완료", self.text("#m-work-content .section-row"))

    def test_launcher_preserves_native_chat_and_is_absent_on_auth_route(self):
        # Only the surrounding native-shaped DOM is a fixture. The launcher,
        # iframe document, simulation, styles and route CSP are shipped assets.
        self.browser.call("Page.navigate", {"url": self.url.replace("/ees-work-demo/", "/c/existing-chat")})
        self.wait("!!document.querySelector('#ees-work-demo-open')")
        self.fill("#native-input", "기존 대화에서 작성 중인 문장")
        history = self.text("#native-history")
        self.click("#ees-work-demo-open")
        self.wait("document.querySelector('#ees-work-demo-dialog iframe')?.contentDocument?.querySelector('#m-work-content h2')?.textContent === '신규 공장 횡전개'")
        self.assertEqual(self.read("#ees-work-demo-dialog iframe", "getAttribute('src')"), "/ees-work-demo/")
        self.assertTrue(self.read("#ees-work-demo-dialog", "open"))
        self.click("#ees-work-demo-dialog > header button")
        self.assertIsNone(self.read("#ees-work-demo-dialog"))
        self.assertEqual(self.read("#native-input", "value"), "기존 대화에서 작성 중인 문장")
        self.assertEqual(self.text("#native-history"), history)
        self.assertEqual(self.browser.evaluate("document.activeElement.id"), "ees-work-demo-open")
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('#sidebar a')].map(e=>e.getAttribute('href'))"),
                         ["/workspace/models", "/workspace/tools", "/workspace/knowledge"])
        # The visible in-demo return link closes only its own parent overlay.
        self.click("#ees-work-demo-open")
        self.wait("!!document.querySelector('#ees-work-demo-dialog iframe')?.contentDocument?.querySelector('.m-return')")
        point = self.browser.evaluate("(() => {const f=document.querySelector('#ees-work-demo-dialog iframe'),e=f.contentDocument.querySelector('.m-return'),r=e.getBoundingClientRect(),p=f.getBoundingClientRect();return {x:p.x+r.x+r.width/2,y:p.y+r.y+r.height/2}})()")
        for event_type in ("mousePressed", "mouseReleased"):
            self.browser.call("Input.dispatchMouseEvent", {"type":event_type,"x":point["x"],"y":point["y"],
                              "button":"left","buttons":1 if event_type=="mousePressed" else 0,"clickCount":1})
        self.wait("!document.querySelector('#ees-work-demo-dialog')")
        self.assertEqual(self.read("#native-input", "value"), "기존 대화에서 작성 중인 문장")
        self.browser.call("Page.navigate", {"url": self.url.replace("/ees-work-demo/", "/auth")})
        self.wait("location.pathname === '/auth' && document.readyState === 'complete'")
        self.assertIsNone(self.read("#ees-work-demo-open"))

    def test_setup_failure_retry_summary_and_downstream_invalidation(self):
        self.assertIn("실제 시스템 미연결", self.text("body"))
        self.progress(3, 6)
        self.screenshot("ees-work-desktop-1920")
        # Selecting a task and its breadcrumb does not conflate selection with expansion.
        self.choose("install-t")
        self.assertEqual(self.text("#m-work-content h2"), "시스템 설치")
        self.choose("db-j")
        self.assertEqual(self.text("#m-work-content h2"), "DB 연결 확인")
        self.run_job()
        self.assertEqual(self.checks(), ["통과"] * 3)
        self.progress(4, 6)
        self.choose("interface-t")
        self.choose("interface-j")
        self.assertTrue(self.read('[data-action="run"]', "disabled"))
        self.assertIn("AP 연결 확인", self.text("#m-work-content .notice"))
        self.choose("ap-j")
        self.run_job("실패")
        self.assertEqual(self.checks(), ["통과", "통과", "실패", "미수행"])
        self.assertIn("응답 시간 초과", self.text("#m-work-content"))
        self.progress(4, 6)
        self.choose("ap-j")
        # Chat and the button enter the same real run transition.
        self.chat("AP 연결 확인 재시도해줘")
        self.wait("document.querySelector('#m-work-content .panel-meta .m-state')?.textContent === '완료'")
        self.assertEqual(self.checks(), ["통과"] * 4)
        self.click("#m-work-content details summary")
        self.assertIn("1회차 · 실패", self.text("#m-work-content"))
        self.assertIn("기능 응답 확인 · 미수행", self.text("#m-work-content"))
        self.choose("interface-j")
        self.run_job()
        self.progress(6, 6)
        self.click('[data-action="summary"]')
        self.assertIn("필수 잡 6 / 6 완료", self.text("#m-work-content"))
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.summary-line .m-state.pass').length"), 6)
        # Re-running an upstream job invalidates its previous downstream success.
        self.choose("db-j")
        self.click('[data-action="run"]')
        self.choose("interface-j")
        self.assertTrue(self.read('[data-action="run"]', "disabled"))
        self.wait("!document.querySelector('#m-work-content [data-action=run]').disabled")
        self.assertEqual(self.text("#m-work-content .panel-meta .m-state"), "준비 전")
        self.progress(5, 6)

    def test_navigation_keeps_draft_popup_examples_and_reset_during_run(self):
        original = self.text("#m-messages")
        self.fill("#m-input", "입력 중인 문장은 유지")
        self.click('#m-run-tree [data-expand="install-t"]')
        self.assertEqual(self.text("#m-work-content h2"), "신규 공장 횡전개")
        self.click('#m-run-tree [data-expand="install-t"]')
        self.choose("db-j")
        self.assertEqual(self.read("#m-input", "value"), "입력 중인 문장은 유지")
        self.assertEqual(self.text("#m-messages"), original)
        self.click("#m-pin")
        self.choose("ap-j")
        self.assertTrue(self.read("#m-navigator", "hidden"))
        self.click('#m-breadcrumb [data-show-nav]')
        self.assertFalse(self.read("#m-navigator", "hidden"))
        self.choose("db-j")
        self.assertTrue(self.read("#m-navigator", "hidden"))
        self.click('#m-breadcrumb [data-show-nav]')
        self.click("#m-pin")
        self.click("#m-toggle-nav")
        self.assertIn("nav-collapsed", self.read("#m-app", "className"))
        self.click("#m-toggle-nav")
        self.click('[data-category="ops"]')
        self.choose("ops-t")
        self.choose("ops-j")
        self.run_job()
        self.click('[data-category="incident"]')
        self.choose("recovery-t")
        self.choose("recovery-j")
        self.assertTrue(self.read('[data-action="manual"]', "disabled"))
        self.choose("incident-p")
        self.choose("incident-t")
        self.choose("incident-j")
        self.run_job()
        self.choose("recovery-j")
        self.click('[data-action="manual"]')
        self.assertEqual(self.text("#m-work-content .panel-meta .m-state"), "완료")
        self.click('[data-category="setup"]')
        self.choose("db-j")
        self.click('[data-action="run"]')
        self.assertEqual(self.text("#m-work-content .panel-meta .m-state"), "실행 중")
        self.click("#m-reset")
        # Wait beyond the former run's completion window; reset must cancel it.
        self.browser.evaluate("new Promise(resolve=>setTimeout(()=>resolve(true),1100))")
        self.progress(3, 6)
        self.assertEqual(self.read("#m-input", "value"), "")
        self.assertEqual(self.text("#m-messages"), original)
        self.choose("db-j")
        self.assertEqual(self.checks(), ["준비 전"] * 3)
        self.chat("지원하지 않는 임의 업무 요청")
        self.assertIn("DB 연결 확인 실행해줘", self.text("#m-messages"))
        self.browser.call("Page.reload")
        self.wait("document.querySelector('#m-work-content h2')?.textContent === '신규 공장 횡전개'")
        self.progress(3, 6)

    def test_designer_validation_retest_publish_and_case_version_pin(self):
        malicious_name = '공장 A</small><img src="/api/v1/chats/"><small>'
        self.choose("db-j")
        self.run_job()
        self.click("#m-design-mode")
        self.fill('[data-kind="node"][data-field="name"]', "DB 연결 확인 개정")
        self.click('[data-bind-skill="handoff"]')
        self.select("#m-tool-to-add", "logs")
        self.click('[data-action="add-tool-binding"]')
        self.assertIn("진단 로그 조회", self.text("#m-preview-content"))
        self.select('[data-map-input="gateway"]', "ap")
        self.click("#m-save-draft")
        self.click("#m-test-draft")
        self.assertIn("도구에 맞는 입력값 종류", self.text("#m-preview-content"))
        self.click("#m-review-publish")
        self.assertIn("시험 실행을 먼저", self.text("#m-design-status"))
        self.select('[data-map-input="gateway"]', "db")
        # A cycle is detected from the same dependency form used by administrators.
        self.click("#m-designer-content details summary")
        self.click('[data-bind-dep="interface-j"]')
        self.click("#m-test-draft")
        self.assertIn("순환", self.text("#m-preview-content"))
        self.click('[data-bind-dep="interface-j"]')
        self.click('[data-section="tools"]')
        self.select('[data-select-tool]', "gateway")
        self.click('[data-kind="tool"][data-field="enabled"]')
        self.click('[data-action="test-tool"]')
        self.assertIn("연결", self.text("#m-design-status"))
        self.click("#m-test-draft")
        self.assertIn("미연결", self.text("#m-preview-content"))
        self.click('[data-kind="tool"][data-field="enabled"]')
        self.click('[data-action="test-tool"]')
        self.assertIn("통과", self.text("#m-design-status"))
        self.click('[data-section="skills"]')
        self.click('[data-action="new-skill"]')
        self.fill('[data-kind="skill"][data-field="name"]', "셋업 검토 보조")
        self.click('[data-action="skill-draft"]')
        self.assertIn("목표: 셋업 검토 보조", self.read('[data-kind="skill"][data-field="body"]', "value"))
        self.click('[data-section="sites"]')
        self.select('[data-select-site]', "us-a")
        # Administrator-entered text stays text through preview, option labels,
        # case snapshots and later publication review; it cannot issue API GETs.
        self.fill('[data-kind="site"][data-field="name"]', malicious_name)
        self.assertIn(malicious_name, self.text("#m-preview-content"))
        self.assertIsNone(self.read('img[src="/api/v1/chats/"]'))
        self.fill('[data-kind="site"][data-field="line"]', "조립 3라인")
        self.click("#m-save-draft")
        self.click("#m-test-draft")
        self.assertNotIn("수정 필요", self.text("#m-preview-content"))
        # Any later edit invalidates the passing test before review/publication.
        self.fill('[data-kind="site"][data-field="line"]', "조립 4라인")
        self.click("#m-save-draft")
        self.click("#m-review-publish")
        self.assertIn("시험 실행을 먼저", self.text("#m-design-status"))
        self.click("#m-test-draft")
        self.click("#m-review-publish")
        self.assertIn("게시 전 변경 확인", self.text("#m-preview-title"))
        self.click('[data-action="confirm-publish"]')
        self.assertIn("v1.4 게시됨", self.text("#m-preview-content"))
        self.click('[data-action="new-case-after-publish"]')
        self.assertIn("적용 절차 v1.4", self.text("#m-site-plan"))
        self.click('[data-action="create-case"]')
        self.assertIn("조립 4라인", self.text("#m-work-content"))
        self.assertIn(malicious_name, self.text("#m-work-content"))
        self.assertIn(malicious_name, self.read("#m-case option:checked"))
        self.assertIsNone(self.read('img[src="/api/v1/chats/"]'))
        self.choose("install-t")
        self.choose("db-j")
        self.assertEqual(self.text("#m-work-content h2"), "DB 연결 확인 개정")
        self.assertTrue(self.read('[data-action="run"]', "disabled"))
        self.click("#m-design-mode")
        self.fill('[data-kind="node"][data-field="description"]', "현장 이름의 안전한 표시 확인")
        self.click("#m-save-draft")
        self.click("#m-test-draft")
        self.click("#m-review-publish")
        self.assertIn("게시 전 변경 확인", self.text("#m-preview-title"))
        self.assertIn(malicious_name, self.text("#m-preview-content"))
        self.assertIsNone(self.read('img[src="/api/v1/chats/"]'))
        self.click("#m-run-mode")
        # Old case retains its original procedure, site and successful run.
        self.select("#m-case", "case-1")
        self.choose("db-j")
        self.assertEqual(self.text("#m-work-content h2"), "DB 연결 확인")
        self.assertIn("적용 절차 v1.3", self.text("#m-work-content"))
        self.assertIn("조립 2라인", self.text("#m-work-content"))
        self.assertEqual(self.checks(), ["통과"] * 3)

    def test_hungary_exclusion_new_country_preview_and_responsive_layout(self):
        self.click("#m-new-case")
        self.select("#m-start-site", "kr-ca")
        self.assertIn("신규 인프라 준비", self.text("#m-site-plan"))
        self.select("#m-start-site", "hu-a")
        self.assertIn("인터페이스 검증 제외", self.text("#m-site-plan"))
        self.click('[data-action="create-case"]')
        self.progress(0, 5)
        self.choose("interface-t")
        self.choose("interface-j")
        self.assertIn("이 현장은 시스템 간 연계를 사용하지 않음", self.text("#m-work-content"))
        self.assertIsNone(self.read('[data-action="run"]'))
        for width, height in ((1920, 1080), (1280, 800), (960, 720), (640, 900)):
            with self.subTest(width=width):
                self.browser.call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                self.browser.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))")
                bounds = self.browser.evaluate("(() => {const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}}; return {width:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth,chat:rect('.chat-pane'),work:rect('.work-pane'),top:rect('.topbar')}})()")
                if width == 640:
                    self.screenshot("ees-work-compact-640")
                self.assertLessEqual(bounds["scroll"], width + 1, bounds)
                self.assertLessEqual(bounds["body"], width + 1, bounds)
                self.assertGreater(bounds["chat"]["width"], 200, bounds)
                self.assertGreater(bounds["work"]["width"], 200, bounds)
                a, b = bounds["chat"], bounds["work"]
                self.assertTrue(a["right"] <= b["x"] + 1 or a["bottom"] <= b["y"] + 1, bounds)
                self.click("#m-design-mode")
                self.assertLessEqual(self.browser.evaluate("document.documentElement.scrollWidth"), width + 1)
                self.assertTrue(self.read("#m-preview-content", "getClientRects().length"))
                if width in (1920, 640):
                    self.screenshot("ees-work-designer-" + str(width))
                self.click("#m-run-mode")


if __name__ == "__main__":
    unittest.main()
