"""Native EES workflow Chrome tests using the real pinned Svelte/Tiptap UI.

The built wheel frontend is unchanged. Only upstream server APIs and model
replies are synthetic; workflow actions and the registered AI Tool use the real
service and a temporary database. No live model, user database or business API
is used. Linux CI requires the browser and built wheel instead of skipping.
"""

import asyncio
import base64
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from native_ui_fixture import NativeUIServer, chat_record
from test_ees_chat_theme import ChromePipe

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agent-pack/skills/ees-work-demo/scripts"


def load_module(name, path):
    if path.name == "ees_workflow.py":
        package = types.ModuleType(name)
        package.__path__ = [str(path.parent)]
        with patch.dict(sys.modules, {name: package}):
            return importlib.import_module(f"{name}.ees_workflow")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EESWorkNativeBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get("EES_TEST_CHROME")
        cls.chrome = shutil.which(explicit) if explicit else next(
            (path for name in ("google-chrome", "chromium", "chromium-browser")
             if (path := shutil.which(name))), None)
        directory = os.environ.get("EES_TEST_BRANDING_DIR")
        if not cls.chrome or not directory:
            if explicit:
                raise RuntimeError("Native browser gate requires Chrome and EES_TEST_BRANDING_DIR.")
            raise unittest.SkipTest("Native Chrome/wheel unavailable; Linux CI requires both.")
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("Chrome DevTools pipe fixture requires Linux.")
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        cls.wheel_path = directory / manifest["wheel"]["filename"]

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ees-native-ui-")
        self.addCleanup(self.temporary.cleanup)
        self.server = NativeUIServer(self.wheel_path)
        self.addCleanup(self.server.server_close)
        backend = load_module("ees_workflow_browser_fixture", SCRIPTS / "ees_workflow.py")
        self.backend = backend
        self.server.workflow = backend.WorkflowService(
            Path(self.temporary.name) / "workflow.sqlite3",
            lambda user_id: self.server.user if user_id == self.server.user["id"] else None,
            lambda chat_id: self.server.chats.get(chat_id))
        backend._service = self.server.workflow
        modules = {"open_webui": types.ModuleType("open_webui"), "open_webui.ees_workflow": backend}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.workflow_tool = load_module("workflow_tool_browser_fixture", SCRIPTS / "workflow_tool.py").Tools()
        self.server.tool_call = self.call_workflow_tool
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.browser = ChromePipe(self.chrome, str(Path(self.temporary.name) / "chrome"))
        self.addCleanup(self.browser.close)
        self.browser.navigate("about:blank")
        self.browser.call("Runtime.enable")
        self.browser.call("Network.enable")
        # Synthetic login fixture only. No production token or user is read.
        self.browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('token','fixture-token');localStorage.setItem('locale','ko-KR');"
            "localStorage.setItem('version','0.11.3');"})
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#chat-input.ProseMirror') && !!document.querySelector('#ees-work-entry')")
        self.click('button[aria-label="사이드바 열기"]')
        self.wait("document.querySelector('#sidebar')?.getBoundingClientRect().width > 200")

    def tearDown(self):
        self.server.stream_hold.set()
        self.server.action_response_hold.set()
        self.server.completion_response_hold.set()
        self.browser.evaluate("document.readyState")
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        errors = [event["params"]["exceptionDetails"].get("exception", {}).get("description")
                  or event["params"]["exceptionDetails"]["text"]
                  for event in self.browser.events if event.get("method") == "Runtime.exceptionThrown"]
        if errors or self.server.errors or any(case is self or getattr(case, "test_case", None) is self
                                              for case, _ in failures):
            self.screenshot(self._testMethodName + "-failure")
        self.assertEqual(errors, [], errors)
        self.assertEqual(self.server.errors, [])
        requests = [e["params"]["request"] for e in self.browser.events if e.get("method") == "Network.requestWillBeSent"]
        for request in requests:
            parsed = urlsplit(request["url"])
            if parsed.scheme in {"http", "https", "ws", "wss"}:
                self.assertEqual(parsed.hostname, "127.0.0.1", request["url"])

    def call_workflow_tool(self, body):
        async def event_call(event):
            return await asyncio.to_thread(self.server.event_call, body, event)
        async def invoke():
            state = await self.workflow_tool.ees_workflow_view(
                __user__=self.server.user, __metadata__={"chat_id": body["chat_id"]}, __event_call__=event_call)
            case = state["case"]
            return await self.workflow_tool.ees_workflow_action("run", node_id=case["selected_id"],
                expected_revision=case["revision"], target=state["target"],
                request_id="native-run-" + body["id"], __user__=self.server.user,
                __metadata__={"chat_id": body["chat_id"]}, __event_call__=event_call)
        return asyncio.run(invoke())

    def current(self, chat_id="existing-chat"):
        return asyncio.run(self.server.workflow.get_state(self.server.user, chat_id=chat_id))

    def navigate(self, path):
        self.browser.call("Page.navigate", {"url": self.server.url + path})

    def wait(self, expression, timeout=9000):
        result = self.browser.evaluate("new Promise(resolve => { const end=performance.now()+" + str(timeout)
            + "; const check=()=>{if(" + expression + ")resolve(true);else if(performance.now()>end)resolve(false);"
            + "else setTimeout(check,25)};check()})")
        self.assertTrue(result, "Timed out: " + expression + "\n" + self.text("body")
                        + "\nUnknown fixture routes: " + repr(self.server.unknown))

    def read(self, selector, prop="textContent"):
        return self.browser.evaluate("document.querySelector(" + json.dumps(selector) + ")?." + prop)

    def text(self, selector):
        return self.read(selector, "innerText") or ""

    def click(self, selector, confirm=None):
        point = self.browser.evaluate("(() => {const e=[...document.querySelectorAll("
            + json.dumps(selector) + ")].find(e=>e.getClientRects().length);if(!e)return null;"
            + "e.scrollIntoView({block:'center',inline:'nearest'});const r=e.getBoundingClientRect();"
            + "const x=r.x+r.width/2,y=r.y+r.height/2;return {x,y,disabled:!!e.disabled,"
            + "hit:e.contains(document.elementFromPoint(x,y))};})()")
        self.assertIsNotNone(point, "Visible control missing: " + selector)
        self.assertFalse(point["disabled"], "Control disabled: " + selector)
        self.assertTrue(point["hit"], "Control is covered: " + selector)
        for event_type in ("mousePressed", "mouseReleased"):
            params = {"type": event_type, "x": point["x"], "y": point["y"],
                "button": "left", "buttons": 1 if event_type == "mousePressed" else 0, "clickCount": 1}
            if confirm is not None and event_type == "mouseReleased":
                # Chrome holds the input reply while a native confirm is open.
                # Handle its real dialog event, without replacing window.confirm.
                self.browser.counter += 1
                request = {"id": self.browser.counter, "sessionId": self.browser.session,
                           "method": "Input.dispatchMouseEvent", "params": params}
                os.write(self.browser.request_write, json.dumps(request).encode() + b"\0")
                deadline = time.monotonic() + 8
                while True:
                    event = self.browser.receive(deadline)
                    self.browser.events.append(event)
                    if event.get("method") == "Page.javascriptDialogOpening":
                        self.browser.call("Page.handleJavaScriptDialog", {"accept": confirm})
                        break
            else:
                self.browser.call("Input.dispatchMouseEvent", params)

    def key(self, key, code, modifiers=0):
        for event_type in ("keyDown", "keyUp"):
            self.browser.call("Input.dispatchKeyEvent", {"type": event_type, "key": key, "code": key,
                "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code, "modifiers": modifiers})

    def fill(self, selector, value):
        self.click(selector)
        self.key("a", 65, modifiers=2)
        self.browser.call("Input.insertText", {"text": value})
        self.key("Tab", 9)

    def wait_scope_ready(self, kind):
        trigger = '#ees-work-' + kind + '-trigger'
        self.wait("(() => {const controls=document.querySelector('#ees-work-entry .ew-scope-pickers');"
                  + "const trigger=document.querySelector(" + json.dumps(trigger) + ");"
                  + "return controls?.getAttribute('aria-busy') === 'false'"
                  + " && controls.dataset.readyRoute === location.pathname + location.search"
                  + " && trigger?.getClientRects().length > 0 && !trigger.disabled"
                  + " && window.__eesNativeDraftV1?.ready();})()")

    def select_scope(self, kind, value):
        # Exercise the visible picker with trusted mouse input. The old native
        # selects are gone, so draft/route tests also cover the shipped control.
        # The composer can survive an SPA route change while scope state and
        # native draft loading are still pending; DOM presence is not readiness.
        trigger = '#ees-work-' + kind + '-trigger'
        self.wait_scope_ready(kind)
        self.click(trigger)
        option = ('#ees-work-scope-popover [data-action="scope_choose"]'
                  '[data-picker="' + kind + '"][data-value="' + value + '"]')
        self.wait('!!document.querySelector(' + json.dumps(option) + ')')
        self.click(option)
        self.wait('document.querySelector(' + json.dumps(trigger) + ')?.value === ' + json.dumps(value)
                  + " && !document.querySelector('#ees-work-scope-popover')")

    def open_category(self, category):
        selector = '[data-work-category="' + category + '"]'
        if self.read(selector, "getAttribute('aria-expanded')") != "true":
            self.click(selector)
        self.wait("!!document.querySelector('#ees-work-entry #ees-work-tree')")

    def assert_draft_stays(self, expected):
        # Catch a late native load/restore overwriting the already visible
        # scope draft. Merely observing the desired text once misses this race.
        frames = self.browser.evaluate("""new Promise(resolve=>{
            const values=[];
            const check=()=>{
                values.push(document.querySelector('#chat-input')?.innerText);
                if(values.length===12)resolve(values);else requestAnimationFrame(check);
            };
            requestAnimationFrame(check);
        })""")
        self.assertEqual(set(frames), {expected}, frames)

    def choose(self, node_id, chat_id="existing-chat"):
        state = self.current(chat_id)
        definition = state["case"]["definition"] if state["case"] else state["catalog"]
        selected = definition["nodes"][node_id]
        self.open_category(selected["category"])
        ancestors = []
        ancestor = selected.get("parent")
        while ancestor:
            ancestors.insert(0, ancestor)
            ancestor = definition["nodes"][ancestor].get("parent")
        for ancestor in ancestors:
            control = '#ees-work-tree [data-action="expand"][data-node-id="' + ancestor + '"]'
            if self.read(control, "getAttribute('aria-expanded')") == "false":
                self.click(control)
        self.click('#ees-work-tree [data-action="select"][data-node-id="' + node_id + '"]')
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === "
                  + json.dumps(selected["name"])
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")

    def create_case(self, site="us-a", chat_id="existing-chat", system="EMS"):
        self.select_scope("site", site)
        self.select_scope("system", system)
        self.open_category("setup")
        self.assertIsNone(self.read("#ees-work-navigator"))
        self.assertIsNone(self.read('#ees-work-entry [data-action="pin"]'))
        cases_before = self.current(chat_id)["cases"]
        self.choose("setup-p", chat_id=chat_id)
        self.assertIsNone(self.read("#ees-work-case-start"))
        self.assertEqual(self.current(chat_id)["cases"], cases_before,
                         "Browsing a published procedure must not create a case")
        # First input save creates the case without running or confirming a J.
        # Return to P so the callers keep testing the same starting selection.
        self.choose("db-j", chat_id=chat_id)
        self.wait("!!document.querySelector('#ees-work-inputs-save')")
        self.assertEqual(self.read("#ees-work-inputs-save", "type"), "submit")
        self.click("#ees-work-inputs-save")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('" +
                  ("이 대화에 연결됨" if chat_id else "첫 메시지") + "')"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        created = next(case for case in self.current(chat_id)["cases"]
                       if case["id"] not in {item["id"] for item in cases_before})
        saved = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=created["id"]))["case"]
        self.assertTrue(all(job["attempt"] == 0 for job in saved["jobs"].values()))
        expanded_task = '#ees-work-tree [data-action="expand"][data-node-id="install-t"]'
        if self.read(expanded_task, "getAttribute('aria-expanded')") == "true":
            self.click(expanded_task)
        self.choose("setup-p", chat_id=chat_id)
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === '신규 공장 횡전개'"
                  + " && !document.querySelector('#ees-work-case-start')"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        if chat_id:
            self.assertEqual(self.current(chat_id)["case"]["chat_id"], chat_id)

    def run_job(self, node_id, status="passed"):
        self.choose(node_id)
        case = self.current()["case"]
        before = case["revision"]
        human = case["definition"]["nodes"][node_id]["mode"] in ("manual", "draft")
        self.click("#ees-work-run", confirm=True if human else None)
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        result = self.current()["case"]
        self.assertGreater(result["revision"], before)
        self.assertEqual(result["jobs"][node_id]["status"], status)

    def seed_case(self, chat_id, site="us-a", system="EMS", completed=False, ready=False):
        """Arrange past/current cases through the real service, not fake UI state."""
        if chat_id:
            record = chat_record(chat_id)
            record["chat"]["history"]["messages"]["previous-user"]["content"] = chat_id + "의 기존 질문"
            record["chat"]["history"]["messages"]["previous-answer"]["content"] = chat_id + "의 기존 대화"
            self.server.chats[chat_id] = record
        state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            "action": "create", "chat_id": chat_id,
            "payload": {"site_id": site, "system": system, "process_id": "setup-p"}}))
        self.assertTrue(state["ok"], state)
        jobs = ["scope-j", "infra-j", "install-j"] if ready or completed else []
        if completed:
            jobs += ["db-j", "ap-j", "ap-j"]
            if state["case"]["site"]["interface"]:
                jobs.append("interface-j")
        for node_id in jobs:
            case = state["case"]
            state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                "action": "run", "chat_id": chat_id, "case_id": case["id"],
                "expected_revision": case["revision"], "node_id": node_id, "payload": {"confirm": True}}))
            self.assertTrue(state["ok"], state)
        if completed:
            self.assertEqual(state["case"]["status"], "passed")
        return state["case"]

    def screenshot(self, name):
        directory = os.environ.get("EES_TEST_SCREENSHOT_DIR")
        if directory:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            data = self.browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]
            (directory / (name + ".png")).write_bytes(base64.b64decode(data))

    def attach_file(self):
        path = Path(self.temporary.name) / "attachment.txt"
        path.write_text("fixture file", encoding="utf-8")
        document = self.browser.call("DOM.getDocument")
        field = self.browser.call("DOM.querySelector", {"nodeId": document["root"]["nodeId"],
                                                        "selector": 'input[type="file"]'})
        self.browser.call("DOM.setFileInputFiles", {"nodeId": field["nodeId"], "files": [str(path)]})
        self.wait("document.querySelector('#chat-container')?.innerText.includes('attachment.txt')")

    def test_sidebar_expands_one_level_and_respects_collapse_after_selection_and_refresh(self):
        self.create_case()
        nodes = self.current()["case"]["definition"]["nodes"]
        expand = lambda node_id: '#ees-work-tree [data-action="expand"][data-node-id="' + node_id + '"]'
        visible_ids = lambda: self.browser.evaluate(
            "[...document.querySelectorAll('#ees-work-tree [data-action=select]')].map(e=>e.dataset.nodeId)")
        self.assertNotIn("P 프로세스", self.text("#ees-work-entry"))
        self.assertNotIn("T 태스크", self.text("#ees-work-entry"))
        self.assertNotIn("J 잡", self.text("#ees-work-entry"))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-entry .ew-type')"))
        if self.read(expand("setup-p"), "getAttribute('aria-expanded')") == "false":
            self.click(expand("setup-p"))
        self.assertEqual(set(visible_ids()), {"setup-p", *nodes["setup-p"]["children"]})
        for task_id in nodes["setup-p"]["children"]:
            self.assertEqual(self.read(expand(task_id), "getAttribute('aria-expanded')"), "false")

        # Selecting details must preserve an explicit collapse. A job still
        # becomes available when the user deliberately expands that task.
        self.click(expand("prep-t"))
        self.click(expand("prep-t"))
        self.choose("prep-t")
        self.assertEqual(self.read(expand("prep-t"), "getAttribute('aria-expanded')"), "false")
        self.assertNotIn("scope-j", visible_ids())
        self.choose("scope-j")
        self.assertIn("scope-j", visible_ids())
        self.click(expand("prep-t"))
        self.assertNotIn("scope-j", visible_ids())
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.assertEqual(self.read(expand("prep-t"), "getAttribute('aria-expanded')"), "false")
        self.assertEqual(self.text("#ees-work-content h2"), nodes["scope-j"]["name"])
        # An action response also passes through accept(); it must update the
        # result without reopening the ancestor the user deliberately closed.
        self.click("#ees-work-run", confirm=True)
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.current()["case"]["jobs"]["scope-j"]["status"], "passed")
        self.assertNotIn("scope-j", visible_ids())
        self.assertEqual(self.read(expand("prep-t"), "getAttribute('aria-expanded')"), "false")

        self.click(expand("prep-t"))
        self.click(expand("setup-p"))
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.assertEqual(visible_ids(), ["setup-p"])
        self.click('[data-work-category="setup"]')
        self.open_category("setup")
        self.assertEqual(visible_ids(), ["setup-p"])
        self.click(expand("setup-p"))
        self.assertEqual(set(visible_ids()), {"setup-p", *nodes["setup-p"]["children"]})
        for task_id in nodes["setup-p"]["children"]:
            self.assertEqual(self.read(expand(task_id), "getAttribute('aria-expanded')"), "false")

    def test_scope_picker_keyboard_and_outside_dismiss_preserve_current_work(self):
        self.create_case()
        self.fill("#chat-input", "선택창을 닫아도 유지할 초안")
        before = self.current()["case"]
        post_count = self.server.requests.count(("POST", "/api/ees-work/action"))
        completion_count = len(self.server.completions)
        new_chat_count = self.server.requests.count(("POST", "/api/v1/chats/new"))
        for kind in ("site", "system"):
            with self.subTest(picker=kind):
                trigger = "#ees-work-" + kind + "-trigger"
                self.click(trigger)
                self.assertEqual(self.read(trigger, "getAttribute('aria-expanded')"), "true")
                self.assertEqual(self.read("#ees-work-scope-popover", "getAttribute('role')"), "dialog")
                self.browser.evaluate("window.__eesPickerFocus = document.activeElement")
                self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
                self.assertTrue(self.browser.evaluate("document.activeElement === window.__eesPickerFocus && document.activeElement.isConnected"))
                self.key("End", 35)
                focused = self.browser.evaluate("document.activeElement?.dataset.value")
                last = self.browser.evaluate("[...document.querySelectorAll('#ees-work-scope-popover [data-action=scope_choose]')].at(-1)?.dataset.value")
                self.assertEqual(focused, last)
                self.key("Home", 36)
                self.assertEqual(self.browser.evaluate("document.activeElement?.dataset.value"),
                                 self.read('#ees-work-scope-popover [data-action="scope_choose"]', "dataset.value"))
                self.key("Escape", 27)
                self.assertIsNone(self.read("#ees-work-scope-popover"))
                self.assertEqual(self.browser.evaluate("document.activeElement?.id"), trigger[1:])
                self.assertEqual(self.read(trigger, "getAttribute('aria-expanded')"), "false")
                # ArrowDown reopens from the focused trigger; Enter on the
                # selected option should close without changing scope or draft.
                self.key("ArrowDown", 40)
                self.wait("!!document.querySelector('#ees-work-scope-popover')")
                self.assertEqual(self.browser.evaluate("document.activeElement?.getAttribute('aria-pressed')"), "true")
                self.key("Enter", 13)
                self.wait("!document.querySelector('#ees-work-scope-popover')")
                # Native WebUI has a global Enter shortcut. Picker activation
                # must be handled before it can send the existing chat draft.
                self.assertEqual(len(self.server.completions), completion_count)
                self.assertEqual(self.browser.evaluate("location.pathname"), "/c/existing-chat")
                self.key(" ", 32)
                self.wait("!!document.querySelector('#ees-work-scope-popover')")
                self.assertEqual(self.browser.evaluate("document.activeElement?.getAttribute('aria-pressed')"), "true")
                self.key(" ", 32)
                self.wait("!document.querySelector('#ees-work-scope-popover')")
                self.key("Enter", 13)
                self.wait("!!document.querySelector('#ees-work-scope-popover')")
                self.key("Escape", 27)
                self.click(trigger)
                self.click("#chat-input")
                self.assertIsNone(self.read("#ees-work-scope-popover"))
                self.assert_draft_stays("선택창을 닫아도 유지할 초안")
                self.assertEqual(len(self.server.completions), completion_count)
                self.assertEqual(self.server.requests.count(("POST", "/api/v1/chats/new")), new_chat_count)
                self.assertEqual(self.browser.evaluate("location.pathname"), "/c/existing-chat")
        self.assertEqual(self.current()["case"], before)
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/action")), post_count)

    def test_native_chat_sidebar_fonts_and_scope_layout_in_light_dark_and_narrow_view(self):
        self.server.chats["existing-chat"]["chat"]["history"]["messages"]["previous-answer"]["content"] = (
            "기존 대화와 업무 선택의 글꼴을 확인합니다.\n\n`scope_id`는 코드 글꼴을 유지합니다.")
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#chat-input.ProseMirror')"
                  + " && !!document.querySelector('#ees-work-site-trigger')"
                  + " && !!document.querySelector('#chat-container .chat-assistant code')")
        self.create_case()
        loaded = self.browser.evaluate("""(async()=>{
            const faces=await Promise.all([
                document.fonts.load('400 14px "EES Inter"','EES 0123'),
                document.fonts.load('400 14px "EES Noto Sans KR"','공장 업무')]);
            await document.fonts.ready;
            return faces.map(list=>list.map(face=>({family:face.family,status:face.status})));
        })()""")
        for faces, expected in zip(loaded, ("EES Inter", "EES Noto Sans KR")):
            self.assertTrue(faces, expected)
            self.assertTrue(all(face["family"] == expected and face["status"] == "loaded" for face in faces))
        for width, height in ((1920, 1080), (900, 900)):
            for theme in ("light", "dark"):
                with self.subTest(width=width, theme=theme):
                    self.browser.call("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                    self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                    self.browser.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
                    self.screenshot("ees-native-sidebar-" + theme + "-" + str(width))
                    measures = self.browser.evaluate("""(()=>{
                        const visible=s=>[...document.querySelectorAll(s)].find(e=>e.getClientRects().length);
                        const font=s=>getComputedStyle(visible(s)).fontFamily;
                        const rect=s=>visible(s).getBoundingClientRect().toJSON();
                        return {fonts:[font('#chat-input'),font('#chat-container .chat-assistant .markdown-prose > p'),
                            font('a#sidebar-new-chat-button'),font('#ees-work-site-trigger'),font('#ees-work-system-trigger'),
                            font('#ees-work-tree [data-action=select]'),font('#ees-work-content h2')],
                            code:font('#chat-container .chat-assistant code'),
                            site:rect('#ees-work-site-trigger'),system:rect('#ees-work-system-trigger'),
                            sidebar:visible('#ees-work-entry').closest('[role=navigation]').getBoundingClientRect().toJSON(),
                            scroll:document.documentElement.scrollWidth,width:innerWidth};
                    })()""")
                    self.assertEqual(len(set(measures["fonts"])), 1, measures["fonts"])
                    self.assertIn('"EES Inter"', measures["fonts"][0])
                    self.assertIn('"EES Noto Sans KR"', measures["fonts"][0])
                    self.assertIn("monospace", measures["code"])
                    self.assertNotIn("EES", measures["code"])
                    self.assertLessEqual(measures["scroll"], measures["width"] + 1)
                    self.assertAlmostEqual(measures["site"]["left"], measures["system"]["left"], delta=1)
                    self.assertAlmostEqual(measures["site"]["width"], measures["system"]["width"], delta=1)
                    self.assertLessEqual(measures["site"]["bottom"], measures["system"]["top"] + 1)
                    for key in ("site", "system"):
                        self.assertGreaterEqual(measures[key]["height"], 40)
                        self.assertGreaterEqual(measures[key]["left"], measures["sidebar"]["left"])
                        self.assertLessEqual(measures[key]["right"], measures["sidebar"]["right"] + 1)
                    self.click("#ees-work-site-trigger")
                    popover = self.read("#ees-work-scope-popover", "getBoundingClientRect().toJSON()")
                    self.screenshot("ees-native-sidebar-" + theme + "-" + str(width))
                    self.assertGreaterEqual(popover["left"], 0)
                    self.assertGreaterEqual(popover["top"], 0)
                    self.assertLessEqual(popover["right"], width + 1)
                    self.assertLessEqual(popover["bottom"], height + 1)
                    self.key("Escape", 27)

    def test_real_tiptap_chat_stream_and_sidebar_panel_share_one_screen(self):
        self.assertIn("기존 대화 기록", self.text("#chat-container"))
        self.fill("#chat-input", "작성 중인 실제 대화")
        self.attach_file()
        self.create_case()
        self.choose("db-j")
        self.assertEqual(self.text("#chat-input"), "작성 중인 실제 대화")
        self.assertIn("attachment.txt", self.text("#chat-container"))
        self.assertIn("기존 대화 기록", self.text("#chat-container"))
        self.assertEqual(self.read("#chat-input", "isContentEditable"), True)
        self.assertIsNone(self.read("#ees-work-demo-dialog"))
        self.assertIsNone(self.read("#m-chat"))
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["attempt"], 0)
        bounds = self.browser.evaluate("(()=>{const r=s=>document.querySelector(s).getBoundingClientRect();"
            "return {chat:r('#chat-pane').toJSON(),panel:r('#ees-work-panel').toJSON(),context:r('#ees-work-context').toJSON(),"
            "gradient:r('#navbar-bg-gradient-to-b').toJSON(),width:innerWidth,scroll:document.documentElement.scrollWidth}})()")
        self.assertLessEqual(bounds["chat"]["right"], bounds["panel"]["left"] + 1)
        self.assertGreater(bounds["chat"]["width"], 400)
        self.assertLessEqual(bounds["scroll"], bounds["width"] + 1)
        # The upstream gradient ignores pointer events: hit testing alone would
        # miss the opaque navbar background covering the workflow context text.
        self.assertLessEqual(bounds["gradient"]["bottom"], bounds["context"]["top"] + 1)
        self.click("#ees-work-close")
        self.assertFalse(self.read("#ees-work-panel", "getClientRects().length"))
        self.click("#ees-work-context-open")
        self.wait("!!document.querySelector('#ees-work-panel')?.getClientRects().length")
        self.assertEqual(self.text("#chat-input"), "작성 중인 실제 대화")
        self.screenshot("ees-native-chat-workflow-1920")
        self.fill("#chat-input", "기존 모델로 일반 질문을 보냅니다")
        self.server.stream_hold.clear()
        self.click("#send-message-button")
        self.wait("document.querySelector('#chat-container')?.innerText.includes('테스트 모델 응답:')")
        self.assertNotIn("실제 대화 입력이 전달되었습니다.", self.text("#chat-container"))
        self.choose("ap-j")
        self.assertIn("테스트 모델 응답:", self.text("#chat-container"))
        self.server.stream_hold.set()
        self.wait("document.querySelector('#chat-container')?.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        self.assertEqual(self.server.completions[-1]["model"], "fixture-model")
        self.assertEqual(self.server.completions[-1]["user_message"]["content"], "기존 모델로 일반 질문을 보냅니다")
        self.assertEqual(self.server.completions[-1]["user_message"]["files"][0]["id"], "fixture-file")
        self.assertEqual(self.server.tool_results, [])
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["attempt"], 0)
        self.assertIsNotNone(self.read("#model-selector-model-button"))
        self.assertIsNotNone(self.read('input[type="file"]'))

    def test_panel_and_ai_tool_run_same_persisted_case_with_retry_history(self):
        def assert_record_visible(selector, record):
            rendered = self.text(selector)
            self.assertIn("모의 점검", rendered)
            self.assertIn(record["at"], rendered)
            for check in record["checks"]:
                for field in ("name", "detail", "input", "at"):
                    self.assertIn(check[field], rendered)
            statuses = self.browser.evaluate("Array.from(document.querySelectorAll("
                + json.dumps(selector + " .ew-check [data-status]")
                + "), element => element.dataset.status)")
            self.assertEqual(statuses, [check["status"] for check in record["checks"]])

        self.create_case()
        self.run_job("scope-j")
        self.run_job("infra-j")
        self.run_job("install-j")
        self.choose("db-j")
        self.fill('#ees-work-inputs input[name="db"]', "fixture-db-target")
        self.click("#ees-work-inputs-save")
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["inputs"]["db"], "fixture-db-target")
        self.fill("#chat-input", "선택한 DB 연결을 점검해줘")
        self.click("#send-message-button")
        self.wait("document.querySelector('#chat-container')?.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        self.assertEqual(len(self.server.tool_results), 1)
        self.assertTrue(self.server.tool_results[0]["ok"], self.server.tool_results)
        db_job = self.current()["case"]["jobs"]["db-j"]
        self.assertEqual(db_job["status"], "passed")
        self.wait("document.querySelector('#ees-work-content .ew-work-current-title')?.innerText === '점검 결과가 저장되었습니다.'")
        evidence = '#ees-work-content [data-work-section="current-result"] details'
        self.click(evidence + " > summary")
        self.assertTrue(self.read(evidence, "open"))
        self.assertIn("fixture-db-target", self.text(evidence))
        assert_record_visible(evidence, db_job["history"][-1])
        self.run_job("ap-j", "failed")
        failed_job = self.current()["case"]["jobs"]["ap-j"]
        self.assertEqual([x["status"] for x in failed_job["checks"]],
                         ["passed", "passed", "failed", "skipped"])
        self.run_job("ap-j")
        retried_job = self.current()["case"]["jobs"]["ap-j"]
        self.assertEqual(len(retried_job["history"]), 2)
        self.assertEqual(retried_job["history"][0], failed_job["history"][-1])
        self.assertEqual(retried_job["history"][-1]["status"], "passed")
        previous = '#ees-work-content [data-work-section="history"]'
        self.click(previous + " > summary")
        self.assertTrue(self.read(previous, "open"))
        self.click(previous + " .ew-history-attempt > summary")
        self.assertTrue(self.read(previous + " .ew-history-attempt", "open"))
        self.assertIn("1차 · 실패", self.text(previous))
        assert_record_visible(previous + " .ew-history-attempt", failed_job["history"][-1])
        self.run_job("interface-j")
        case_id = self.current()["case"]["id"]
        self.navigate("/c/other-chat")
        self.wait("!!document.querySelector('#chat-input') && !document.querySelector('#ees-work-context')")
        self.assertIsNone(self.current("other-chat")["case"])
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.assertEqual(self.current()["case"]["id"], case_id)
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["status"], "passed")

    def test_cancelled_human_confirmation_keeps_saved_state(self):
        self.create_case()
        self.choose('scope-j')
        before = self.current()['case']
        self.click('#ees-work-run', confirm=False)
        self.assertEqual(self.current()['case'], before)
        self.assertIn('담당자의 확인이 필요합니다.', self.text('#ees-work-content'))
        self.run_job('scope-j')
        self.assertIn('담당자 확인이 완료됐습니다.', self.text('#ees-work-content'))

    def test_existing_workspace_editor_publication_and_user_denial(self):
        self.create_case()
        original_version = self.current()["case"]["version"]
        self.click('#sidebar a[href^="/workspace"]')
        self.wait("location.pathname === '/workspace/models'"
                  + " && document.querySelector('#ees-work-workspace-tab')?.getClientRects().length > 0")
        self.click("#ees-work-workspace-tab")
        self.wait("!!document.querySelector('#ees-work-designer')")
        self.assertIsNotNone(self.read('#workspace-container'))
        self.assertIn("업무 수행 안내", self.text("#ees-work-designer"))
        self.assertIn("완료 조건", self.text("#ees-work-designer"))
        self.assertIn("고급 설정", self.text("#ees-work-designer"))
        self.assertNotIn("프로세스 편집", self.text("#ees-work-designer"))
        self.assertNotIn("태스크 추가", self.text("#ees-work-designer"))
        self.assertNotIn("잡 추가", self.text("#ees-work-designer"))
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="db-j"]')
        writes_before = self.server.requests.count(("POST", "/api/ees-work/action"))
        self.fill('#ees-work-node-form input[name="name"]', "DB 연결 확인 개정")
        # Typing changes only the local editor draft, without a form submit. The designer
        # may detach during ordinary SPA navigation, but must retain that draft
        # and its dirty state until the explicit server save.
        for route in ("models", "knowledge"):
            self.click('nav a[href="/workspace/' + route + '"]')
            self.wait("location.pathname === " + json.dumps("/workspace/" + route)
                      + " && !location.search && !document.querySelector('#ees-work-designer')"
                      + " && !document.querySelector('.ees-work-native-hidden')")
            self.click("#ees-work-workspace-tab")
            self.wait("document.querySelector('#ees-work-node-form input[name=name]')?.value === 'DB 연결 확인 개정'"
                      + " && document.querySelector('.ew-designer-status')?.innerText.includes('저장하지 않은 변경')")
            self.assertEqual(self.browser.evaluate(
                "document.querySelectorAll('#ees-work-workspace-tab').length"), 1)
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.assertEqual(self.read('#ees-work-node-form input[name="name"]', "value"), "DB 연결 확인 개정")
        self.assertIn("저장하지 않은 변경", self.text(".ew-designer-status"))
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/action")), writes_before)
        self.assertEqual(self.current()["catalog"]["nodes"]["db-j"]["name"], "DB 연결 확인")
        self.click('#ees-work-designer [data-action="save_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('초안 1')")
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/action")), writes_before + 1)
        self.assertNotIn("저장하지 않은 변경", self.text(".ew-designer-status"))
        self.assertEqual(self.current()["draft"]["nodes"]["db-j"]["name"], "DB 연결 확인 개정")
        self.click('#ees-work-designer [data-action="validate_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 전 확인 완료')")
        self.click('#ees-work-designer [data-action="publish"]', confirm=True)
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes("
                  + json.dumps("게시 v" + str(original_version + 1)) + ")")
        self.assertEqual(self.current()["case"]["version"], original_version)
        self.assertEqual(self.current()["case"]["definition"]["nodes"]["db-j"]["name"], "DB 연결 확인")
        self.screenshot("ees-native-workspace")
        self.click('nav a[href="/workspace/models"]')
        self.wait("location.pathname === '/workspace/models' && !location.search"
                  + " && !document.querySelector('#ees-work-designer') && !document.querySelector('.ees-work-native-hidden')")
        self.server.user["role"] = "user"
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#ees-work-entry')")
        self.navigate("/workspace/models?ees=workflow")
        self.wait("document.readyState === 'complete'")
        self.assertIsNone(self.read("#ees-work-designer"))
        self.assertIsNone(self.read("#ees-work-workspace-tab"))
        self.assertFalse(self.current()["can_manage"])

    def test_workspace_tab_uses_native_type_and_does_not_flicker_on_idle_or_route_change(self):
        chat_font = self.browser.evaluate("getComputedStyle(document.querySelector('#chat-input')).fontFamily")
        self.navigate("/workspace/models")
        for path in ("models", "knowledge", "prompts", "workflow", "models"):
            if path == "workflow":
                self.click("#ees-work-workspace-tab")
                self.wait("!!document.querySelector('#ees-work-designer')")
            elif not self.browser.evaluate("location.pathname === " + json.dumps("/workspace/" + path)
                                           + " && !location.search"):
                self.click('nav a[href="/workspace/' + path + '"]')
            self.wait("!!document.querySelector('#ees-work-workspace-tab')"
                      + " && !!document.querySelector('#workspace-container')")
            # The old restoreWorkspace/MutationObserver loop detached and
            # recreated this tab even while the upstream nav remained mounted.
            # Observe real idle animation frames, not an implementation flag.
            observed = self.browser.evaluate("""new Promise(resolve => {
                const tab = document.querySelector('#ees-work-workspace-tab');
                const nav = tab.parentElement;
                let detached = 0, frames = 0, missingFrames = 0;
                const observer = new MutationObserver(records => {
                    for (const record of records) for (const removed of record.removedNodes)
                        if (removed === tab || removed.contains?.(tab)) detached++;
                });
                observer.observe(nav, {childList:true, subtree:true});
                const tick = () => {
                    if (!tab.isConnected || document.querySelector('#ees-work-workspace-tab') !== tab)
                        missingFrames++;
                    if (++frames < 32) {requestAnimationFrame(tick); return;}
                    observer.disconnect();
                    const native = nav.querySelector('a[href="/workspace/knowledge"]');
                    const properties = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight'];
                    const style = element => Object.fromEntries(properties.map(key => [key,getComputedStyle(element)[key]]));
                    resolve({detached,missingFrames,count:document.querySelectorAll('#ees-work-workspace-tab').length,
                        added:style(tab),native:style(native),text:tab.textContent});
                };
                requestAnimationFrame(tick);
            })""")
            self.assertEqual(observed["detached"], 0, (path, observed))
            self.assertEqual(observed["missingFrames"], 0, (path, observed))
            self.assertEqual(observed["count"], 1, (path, observed))
            self.assertEqual(observed["text"], "업무 절차")
            self.assertEqual(observed["added"], observed["native"], (path, observed))
            self.assertEqual(observed["added"]["fontFamily"], chat_font, (path, observed))
            if path == "workflow":
                self.assertEqual(self.browser.evaluate(
                    "getComputedStyle(document.querySelector('#ees-work-node-form input[name=name]')).fontFamily"), chat_font)
            if path != "workflow":
                self.assertIsNone(self.read("#ees-work-designer"))
                self.assertIsNone(self.read(".ees-work-native-hidden"))
        self.assertIn("EES Work", self.browser.evaluate("document.title"))

    def test_factory_system_scope_restores_chat_drafts_and_history_never_replaces_current_work(self):
        past = self.seed_case("history-chat", completed=True)
        self.seed_case("existing-chat", ready=True)
        self.seed_case("other-chat", site="hu-a", completed=True)
        self.seed_case("apc-chat", system="APC")
        self.server.chats["existing-chat"]["chat"]["params"] = {"tool_approval_mode": "ask"}
        self.server.chats["existing-chat"]["chat"]["history"]["messages"]["previous-answer"]["output"] = [{
            "type": "function_call", "id": "fixture-pending-call", "call_id": "fixture-pending-call",
            "name": "fixture_read", "arguments": "{}", "status": "requires_approval"}]
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-site-trigger')?.value === 'us-a'"
                  + " && !!document.querySelector('#chat-input.ProseMirror')")
        self.choose("db-j")
        self.assertIn("existing-chat의 기존 질문", self.text("#chat-container"))
        approval_requests_before = len(self.server.requests)
        # A stored draft is content, not consent. Exercise the bridge contract
        # with a legacy full-mode field while a real native approval is pending.
        restored = self.browser.evaluate("""(async()=>{
            const bridge=window.__eesNativeDraftV1;
            const snapshot=bridge.read();
            return {hasApproval:Object.hasOwn(snapshot,'toolApprovalMode'),
                restored:await bridge.restore(JSON.stringify({...snapshot,toolApprovalMode:'full'}))};
        })()""")
        self.assertFalse(restored["hasApproval"])
        self.assertTrue(restored["restored"])
        self.attach_file()
        self.fill("#chat-input", "미국 EMS에서 작성 중인 내용")
        collapsed_task = '#ees-work-tree [data-action="expand"][data-node-id="install-t"]'
        self.click(collapsed_task)
        self.assertEqual(self.read(collapsed_task, "getAttribute('aria-expanded')"), "false")
        self.select_scope("site", "hu-a")
        self.wait("location.pathname === '/c/other-chat'"
                  + " && document.querySelector('#ees-work-site-trigger')?.value === 'hu-a'"
                  + " && document.querySelector('#chat-container')?.innerText.includes('other-chat의 기존 대화')")
        self.assertNotIn("existing-chat의 기존 질문", self.text("#chat-container"))
        self.assertNotIn("미국 EMS에서 작성 중인 내용", self.text("#chat-input"))
        self.assertNotIn("attachment.txt", self.text("#chat-container"))
        self.assertIn("헝가리", self.text("#ees-work-context"))
        self.choose("interface-j", chat_id="other-chat")
        self.assertIn("적용 제외", self.text("#ees-work-tree"))
        self.assertEqual(self.current("other-chat")["case"]["progress"], {"done": 5, "total": 5})
        self.fill("#chat-input", "헝가리 공장에서 작성 중인 내용")
        self.select_scope("site", "us-a")
        self.wait("location.pathname === '/c/existing-chat'"
                  + " && document.querySelector('#chat-input')?.innerText === '미국 EMS에서 작성 중인 내용'")
        self.assert_draft_stays("미국 EMS에서 작성 중인 내용")
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["status"], "pending")
        self.assertEqual(self.read(collapsed_task, "getAttribute('aria-expanded')"), "false")
        self.assertIn("미국", self.text("#ees-work-context"))
        self.assertIn("attachment.txt", self.text("#chat-container"))
        self.select_scope("system", "APC")
        self.wait("location.pathname === '/c/apc-chat'"
                  + " && document.querySelector('#ees-work-system-trigger')?.value === 'APC'"
                  + " && document.querySelector('#chat-container')?.innerText.includes('apc-chat의 기존 대화')")
        self.assertNotIn("미국 EMS에서 작성 중인 내용", self.text("#chat-input"))
        self.assertNotIn("attachment.txt", self.text("#chat-container"))
        self.assertEqual(self.current("apc-chat")["case"]["jobs"]["scope-j"]["status"], "pending")
        self.fill("#chat-input", "미국 APC의 별도 초안")
        self.select_scope("system", "EMS")
        self.wait("location.pathname === '/c/existing-chat'"
                  + " && document.querySelector('#chat-input')?.innerText === '미국 EMS에서 작성 중인 내용'")
        self.assert_draft_stays("미국 EMS에서 작성 중인 내용")
        self.assertEqual(self.read(collapsed_task, "getAttribute('aria-expanded')"), "false")
        self.assertIn("attachment.txt", self.text("#chat-container"))
        self.choose("db-j")
        current = self.current()["case"]
        tree = self.text("#ees-work-tree")
        post_count = self.server.requests.count(("POST", "/api/ees-work/action"))
        self.click('#ees-work-run-view [data-action="history_view"]')
        history_selector = '[data-action="history_case"][data-case-id="' + past["id"] + '"]'
        self.wait("!!document.querySelector(" + json.dumps(history_selector) + ")")
        self.click(history_selector)
        self.wait("document.querySelector('#ees-work-content')?.innerText.includes('읽기 전용')")
        self.assertEqual(self.browser.evaluate("location.pathname"), "/c/existing-chat")
        self.assertEqual(self.text("#chat-input"), "미국 EMS에서 작성 중인 내용")
        self.assertEqual(self.current()["case"], current)
        self.assertEqual(self.text("#ees-work-tree"), tree)
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/action")), post_count)
        self.assertIsNone(self.read("#ees-work-run"))
        self.screenshot("ees-native-factory-history-1920")
        self.click('#ees-work-run-view [data-action="current_view"]')
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === 'DB 연결 확인'")
        self.assertEqual(self.current()["case"], current)
        self.select_scope("site", "hu-a")
        self.wait("location.pathname === '/c/other-chat'"
                  + " && document.querySelector('#chat-input')?.innerText === '헝가리 공장에서 작성 중인 내용'")
        approval_writes = [path for method, path in self.server.requests[approval_requests_before:]
                           if method == "POST" and (path == "/api/v1/users/user/settings/update"
                               or "/messages/" in path and path.endswith("/resolve"))]
        self.assertEqual(approval_writes, [], "Changing factory/draft must not change approval or resolve a pending call")
        self.assertEqual(self.server.chats["existing-chat"]["chat"]["params"]["tool_approval_mode"], "ask")

    def test_new_chat_binds_pending_case_and_rejects_old_chat_callback(self):
        self.click('a#sidebar-new-chat-button')
        self.wait("location.pathname === '/' && !!document.querySelector('#chat-input')")
        self.choose("setup-p", chat_id="")
        self.fill("#chat-input", "첫 미국 업무의 전송 전 초안")
        self.select_scope("site", "hu-a")
        self.wait("location.pathname === '/' && new URLSearchParams(location.search).get('ees_site') === 'hu-a'"
                  + " && document.querySelector('#chat-input')?.innerText !== '첫 미국 업무의 전송 전 초안'")
        self.fill("#chat-input", "첫 헝가리 업무의 전송 전 초안")
        self.select_scope("site", "us-a")
        self.wait("location.pathname === '/' && document.querySelector('#ees-work-site-trigger')?.value === 'us-a'"
                  + " && document.querySelector('#chat-input')?.innerText === '첫 미국 업무의 전송 전 초안'")
        self.assert_draft_stays("첫 미국 업무의 전송 전 초안")
        self.create_case(chat_id="")
        self.assertEqual(self.text("#chat-input"), "첫 미국 업무의 전송 전 초안")
        pending = [item for item in self.current("")["cases"] if not item["chat_id"]]
        self.assertEqual(len(pending), 1)
        pending_id = pending[0]["id"]
        # An asynchronous callback from an older chat cannot claim this case.
        # This is a bridge-contract probe, separate from trusted user input.
        result = self.browser.evaluate("window.__eesNativeWorkV1.ensureChat('other-chat')")
        self.assertFalse(result["ok"])
        self.assertIsNone(self.current("other-chat")["case"])
        self.fill("#chat-input", "이 공장의 업무 범위를 알려줘")
        self.click("#send-message-button")
        self.wait("location.pathname === '/c/fixture-new-chat'")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.assertEqual(self.current("fixture-new-chat")["case"]["id"], pending_id)
        self.assertEqual(self.current("fixture-new-chat")["case"]["chat_id"], "fixture-new-chat")
        self.wait("document.querySelector('#chat-container')?.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        self.assertEqual(self.server.completions[-1]["user_message"]["content"], "이 공장의 업무 범위를 알려줘")

    def test_delayed_action_response_cannot_replace_another_chat(self):
        self.create_case()
        self.choose("scope-j")
        self.server.delay_next_action = True
        self.server.action_response_hold.clear()
        before = self.browser.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/ees-work/action')).length")
        self.click("#ees-work-run", confirm=True)
        self.assertTrue(self.server.action_response_started.wait(timeout=2))
        self.click('a[href="/c/other-chat"]')
        self.wait("location.pathname === '/c/other-chat' && !document.querySelector('#ees-work-context')"
                  + " && !!document.querySelector('#chat-input.ProseMirror')")
        self.fill("#chat-input", "다른 대화에서 작성 중")
        self.server.action_response_hold.set()
        self.wait("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/ees-work/action')).length > " + str(before))
        self.assertEqual(self.text("#chat-input"), "다른 대화에서 작성 중")
        self.assertIsNone(self.current("other-chat")["case"])
        self.assertEqual(self.current()["case"]["jobs"]["scope-j"]["status"], "passed")
        self.assertFalse(self.read("#ees-work-panel", "getClientRects().length"))

    def test_delayed_action_cannot_replace_another_pending_case_at_the_same_url(self):
        first = self.seed_case("")
        second = self.seed_case("")
        self.click('a#sidebar-new-chat-button')
        self.wait("location.pathname === '/' && !!document.querySelector('#chat-input.ProseMirror')")
        self.wait("!!window.__eesNativeWorkV1")
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        result = self.browser.evaluate("window.__eesNativeWorkV1.display('',{case_id:"
                                       + json.dumps(first["id"]) + "})")
        self.assertTrue(result["ok"], result)
        self.choose("scope-j", chat_id="")
        self.fill("#chat-input", "첫 실행에서 작성 중인 내용")
        self.server.delay_next_action = True
        self.server.action_response_hold.clear()
        before = self.browser.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/ees-work/action')).length")
        self.click("#ees-work-run", confirm=True)
        self.assertTrue(self.server.action_response_started.wait(timeout=2))
        original_url = self.browser.evaluate("location.pathname+location.search")
        # This fixed display RPC is the same one available to the registered
        # workflow Tool. Both unbound executions deliberately share one URL.
        result = self.browser.evaluate("window.__eesNativeWorkV1.display('',{case_id:"
                                       + json.dumps(second["id"]) + "})")
        self.assertTrue(result["ok"], result)
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === '신규 공장 횡전개'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.browser.evaluate("location.pathname+location.search"), original_url)
        self.fill("#chat-input", "두 번째 실행의 별도 초안")
        current_tree = self.text("#ees-work-tree")
        self.server.action_response_hold.set()
        self.wait("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/ees-work/action')).length > " + str(before))
        self.assertEqual(self.text("#chat-input"), "두 번째 실행의 별도 초안")
        self.assertEqual(self.text("#ees-work-tree"), current_tree)
        self.assertEqual(self.text("#ees-work-content h2"), "신규 공장 횡전개")
        first_state = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=first["id"]))
        second_state = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=second["id"]))
        self.assertEqual(first_state["case"]["jobs"]["scope-j"]["status"], "passed")
        self.assertEqual(second_state["case"]["jobs"]["scope-j"]["status"], "pending")

    def test_empty_enter_does_not_bind_a_pending_case_to_an_existing_chat(self):
        requested, release = threading.Event(), threading.Event()
        original_get_state = self.server.workflow.get_state

        async def hold_new_chat_state(*args, **kwargs):
            if kwargs.get("chat_id") == "" and not kwargs.get("case_id"):
                requested.set()
                release.wait(timeout=8)
            return await original_get_state(*args, **kwargs)

        # Hold the real workflow response at the transition that previously
        # exposed clickable stale controls. No timing-only sleep or retry.
        with patch.object(self.server.workflow, "get_state", side_effect=hold_new_chat_state):
            try:
                self.click('a#sidebar-new-chat-button')
                self.wait("location.pathname === '/' && !!document.querySelector('#chat-input.ProseMirror')")
                self.assertTrue(requested.wait(timeout=2), "New-chat workflow state was not requested")
                self.assertEqual(self.read('#ees-work-entry .ew-scope-pickers', "getAttribute('aria-busy')"), "true")
                self.assertEqual(self.read('#ees-work-entry .ew-scope-pickers', "dataset.readyRoute"), "")
                self.assertTrue(self.read('#ees-work-site-trigger', "disabled"))
                self.assertTrue(self.read('#ees-work-system-trigger', "disabled"))
                self.assertIsNone(self.read('#ees-work-scope-popover'))
            finally:
                release.set()
            self.wait_scope_ready("site")
        self.create_case(chat_id="")
        pending = [case for case in self.current("")["cases"] if not case["chat_id"]]
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.text("#chat-input").strip(), "")
        self.click("#chat-input")
        self.key("Enter", 13)
        self.click('a[href="/c/other-chat"]')
        self.wait("location.pathname === '/c/other-chat'"
                  + " && !!document.querySelector('#chat-input.ProseMirror')"
                  + " && !document.querySelector('#ees-work-context')")
        self.assertEqual(self.server.completions, [])
        self.assertIsNone(self.current("other-chat")["case"])
        state = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=pending[0]["id"]))
        self.assertEqual(state["case"]["chat_id"], "")

    def test_first_completion_binds_its_original_factory_after_another_pending_case_is_opened(self):
        self.click('a#sidebar-new-chat-button')
        self.wait("location.pathname === '/' && !!document.querySelector('#chat-input.ProseMirror')")
        self.create_case(chat_id="")
        first = next(case for case in self.current("")["cases"] if not case["chat_id"])
        self.server.delay_next_completion = True
        self.server.completion_response_hold.clear()
        self.fill("#chat-input", "미국 공장의 셋업 범위를 설명해줘")
        self.click("#send-message-button")
        self.assertTrue(self.server.completion_response_started.wait(timeout=2))
        # Let Svelte finish the initial send render while its HTTP response is
        # deliberately held, then change the factory through the visible picker.
        self.browser.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
        self.select_scope("site", "hu-a")
        self.wait("location.pathname === '/' && new URLSearchParams(location.search).get('ees_site') === 'hu-a'"
                  + " && !!document.querySelector('#ees-work-content .ew-work-preview-note')")
        self.create_case(site="hu-a", chat_id="")
        second = next(case for case in self.current("")["cases"] if case["site"]["id"] == "hu-a")
        self.assertNotEqual(first["id"], second["id"])
        self.server.completion_response_hold.set()
        self.wait("location.pathname === '/c/fixture-new-chat'"
                  + " && document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.wait("document.querySelector('#chat-container')?.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        bound = self.current("fixture-new-chat")["case"]
        self.assertEqual(bound["id"], first["id"])
        self.assertEqual(bound["site"]["id"], "us-a")
        self.assertEqual(self.read("#ees-work-site-trigger", "value"), "us-a")
        self.assertIn("미국", self.text("#ees-work-context"))
        state = asyncio.run(self.server.workflow.get_state(self.server.user, case_id=second["id"]))
        self.assertEqual(state["case"]["chat_id"], "")
        self.assertEqual(self.server.completions[0]["user_message"]["content"], "미국 공장의 셋업 범위를 설명해줘")


if __name__ == "__main__":
    unittest.main()
