"""Native EES workflow Chrome tests using the real pinned Svelte/Tiptap UI.

The built wheel frontend is unchanged. Only upstream server APIs and model
replies are synthetic; workflow actions and the registered AI Tool use the real
service and a temporary database. No live model, user database or business API
is used. Linux CI requires the browser and built wheel instead of skipping.
"""

import asyncio
import base64
from copy import deepcopy
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
from workflow_fixture import publish_fixture_definition

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
        # Runs after setup/test/teardown failures are recorded, before Chrome
        # closes. Explicit helper users in the C suites need no new aliases.
        self.addCleanup(EESWorkNativeBrowserTests.capture_failure_evidence, self)
        self.browser.navigate("about:blank")
        self.browser.call("Runtime.enable")
        self.browser.call("Network.enable")
        # Synthetic login fixture only. No production token or user is read.
        self.browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('token','fixture-token');localStorage.setItem('locale','ko-KR');"
            "localStorage.setItem('version','0.11.3');"})
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#chat-input.ProseMirror') && !!document.querySelector('#ees-work-entry')")
        # C's unset preference starts expanded; historical/saved closed states
        # still use the real Native opener. Never force the store or DOM width.
        if not self.browser.evaluate("document.querySelector('#sidebar')?.getBoundingClientRect().width > 200"):
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

    def authoring_current(self, process_id="setup-p"):
        result = asyncio.run(self.server.workflow.get_authoring(self.server.user, process_id=process_id))
        self.assertTrue(result["ok"], result)
        return result

    def choose_native_option(self, selector, value):
        # Capability and the selected P arrive separately. Use the actual
        # control's settled enabled/hit-test boundary before one trusted click.
        ready = self.browser.evaluate("""(async()=>{
            await Promise.all([document.fonts.load('400 14px "EES Inter"','EES 0123'),
                document.fonts.load('400 14px "EES Noto Sans KR"','공장 업무')]);
            await document.fonts.ready;
            return await new Promise(resolve=>{let previous=null,stable=0;const end=performance.now()+9000;
                const check=()=>{const e=document.querySelector(SELECTOR);if(e)e.scrollIntoView({block:'center'});
                    const r=e?.getBoundingClientRect(),hit=r&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
                    stable=e&&!e.disabled&&hit&&e===previous?stable+1:0;previous=e;
                    if(stable>=8)return resolve(true);if(performance.now()>end)return resolve(false);requestAnimationFrame(check);};check();});
        })()""".replace('SELECTOR', json.dumps(selector)))
        self.assertTrue(ready, 'Authoring selector never became visible and ready: ' + selector)
        index = self.browser.evaluate("[...document.querySelector(" + json.dumps(selector)
            + ").options].findIndex(option=>option.value===" + json.dumps(value) + ")")
        self.assertGreaterEqual(index, 0, (selector, value))
        self.click(selector)
        self.key("Home", 36)
        for _ in range(index):
            self.key("ArrowDown", 40)
        self.key("Enter", 13)
        self.wait("document.querySelector(" + json.dumps(selector) + ")?.value === " + json.dumps(value))

    def select_authoring_process(self, process_id="setup-p"):
        self.wait("!!document.querySelector('#ees-work-manage-system') && !document.querySelector('#ees-work-manage-system').disabled")
        if self.read('#ees-work-manage-system', 'value') != 'UNASSIGNED':
            self.choose_native_option('#ees-work-manage-system', 'UNASSIGNED')
        self.wait("!!document.querySelector(" + json.dumps('#ees-work-manage-process option[value="' + process_id + '"]') + ")")
        if self.read('#ees-work-manage-process', 'value') != process_id:
            self.choose_native_option('#ees-work-manage-process', process_id)
        self.wait("!!document.querySelector('#ees-work-node-form') && !!document.querySelector('#ees-work-authoring')")

    def open_authoring(self, process_id="setup-p", path="/?ees=workflow"):
        self.navigate(path)
        self.select_authoring_process(process_id)

    def publish_runtime_fixture(self, definition):
        """Arrange runtime data, not evidence of passing the authoring API."""
        publish_fixture_definition(self.server.workflow, definition)
        with self.server.workflow._db(write=True) as db:
            self.server.workflow._init_authoring(db)

    def navigate(self, path):
        self.browser.call("Page.navigate", {"url": self.server.url + path})

    def wait(self, expression, timeout=9000):
        self.last_wait_expression = expression
        result = self.browser.evaluate("new Promise(resolve => { const end=performance.now()+" + str(timeout)
            + "; const check=()=>{if(" + expression + ")resolve(true);else if(performance.now()>end)resolve(false);"
            + "else setTimeout(check,25)};check()})")
        readiness = self.browser.evaluate("""(()=>({route:location.pathname+location.search,
            nativeReady:window.__eesNativeDraftV1?.ready(),
            pickerBusy:document.querySelector('#ees-work-entry .ew-scope-pickers')?.getAttribute('aria-busy'),
            readyRoute:document.querySelector('#ees-work-entry .ew-scope-pickers')?.dataset.readyRoute,
            pickerDisabled:document.querySelector('#ees-work-site-trigger')?.disabled}))()""") if not result else None
        self.assertTrue(result, "Timed out: " + expression + "\n" + self.text("body")
                        + "\nReadiness: " + repr(readiness)
                        + "\nUnknown fixture routes: " + repr(self.server.unknown))

    def read(self, selector, prop="textContent"):
        return self.browser.evaluate("document.querySelector(" + json.dumps(selector) + ")?." + prop)

    def text(self, selector):
        return self.read(selector, "innerText") or ""

    def click(self, selector, confirm=None):
        self.last_click_selector = selector
        point = self.browser.evaluate("(() => {const e=[...document.querySelectorAll("
            + json.dumps(selector) + ")].find(e=>e.getClientRects().length);if(!e)return null;"
            + "e.scrollIntoView({block:'center',inline:'nearest'});const r=e.getBoundingClientRect();"
            + "const x=r.x+r.width/2,y=r.y+r.height/2;return {x,y,disabled:!!e.disabled,"
            + "hit:e.contains(document.elementFromPoint(x,y)),workDialog:e.hasAttribute('data-work-confirm')};})()")
        self.assertIsNotNone(point, "Visible control missing: " + selector)
        self.assertFalse(point["disabled"], "Control disabled: " + selector)
        self.assertTrue(point["hit"], "Control is covered: " + selector)
        for event_type in ("mousePressed", "mouseReleased"):
            params = {"type": event_type, "x": point["x"], "y": point["y"],
                "button": "left", "buttons": 1 if event_type == "mousePressed" else 0, "clickCount": 1}
            if confirm is not None and event_type == "mouseReleased" and not point['workDialog']:
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
        if confirm is not None and point['workDialog']:
            self.wait("document.querySelector('#ees-work-dialog')?.open")
            self.click('#ees-work-dialog [data-dialog-confirm]' if confirm else '#ees-work-dialog [data-dialog-close]')

    def key(self, key, code, modifiers=0, text=None):
        for event_type in ("keyDown", "keyUp"):
            params = {"type": event_type, "key": key, "code": key,
                "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code, "modifiers": modifiers}
            if text is not None and event_type == "keyDown":
                params["text"] = text
            self.browser.call("Input.dispatchKeyEvent", params)

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

    def open_work_panel(self):
        # Reload preserves the case but does not promise an open panel. Use the
        # shipped toggle before requiring the panel's connected-chat context.
        self.wait_scope_ready("site")
        if not self.read('#ees-work-panel', 'isConnected'):
            self.click('#ees-work-panel-toggle')
        self.wait("!!document.querySelector('#ees-work-panel') && !document.querySelector('#ees-work-panel').matches('[aria-busy=true]')")

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
        self.wait('document.querySelector(' + json.dumps(trigger) + ')?.dataset.value === ' + json.dumps(value)
                  + " && !document.querySelector('#ees-work-scope-popover')")

    def open_category(self, category):
        selector = '[data-work-category="' + category + '"]'
        if self.read(selector, "getAttribute('aria-expanded')") != "true":
            self.click(selector)
        self.wait('document.querySelector(' + json.dumps(selector) + ')?.getAttribute("aria-expanded") === "true"'
                  + " && !!document.querySelector('#ees-work-entry .ew-v4-tree')")

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
        container = '#ees-work-content' if selected["type"] == "j" else '#ees-work-entry'
        control = container + ' [data-action="select"][data-node-id="' + node_id + '"]'
        if selected["type"] == "t" and not self.read(control, "getClientRects().length"):
            self.choose(selected["parent"], chat_id=chat_id)
            expansion = '#ees-work-entry [data-action="expand"][data-node-id="' + selected["parent"] + '"]'
            if self.read(expansion, "getAttribute('aria-expanded')") != "true":
                self.click(expansion)
            self.wait('!!document.querySelector(' + json.dumps(control) + ')?.getClientRects().length')
        if selected["type"] == "j":
            # P also contains a collapsed job index. Open the actual parent T
            # list before choosing its J, rather than hitting that hidden copy.
            self.choose(selected["parent"], chat_id=chat_id)
            control = '#ees-work-content [data-work-job="' + node_id + '"] button[data-action="select"]'
            if not self.read(control, "getClientRects().length"):
                self.fill('#ees-work-job-search', selected["name"])
                if not self.read('.ew-v4-filter-menu', 'open'):
                    self.click('.ew-v4-filter-menu > summary')
                self.click('[data-action="job_filter"][data-filter="all"]')
                if self.read('.ew-v4-filter-menu', 'open'):
                    self.click('.ew-v4-filter-menu > summary')
                # Completed/simulated/excluded groups start collapsed in V4.
                # Reveal the searched row with the same visible group controls.
                groups = self.browser.evaluate("[...document.querySelectorAll('#ees-work-content [data-action=job_group][aria-expanded=false]')].map(e=>e.dataset.group)")
                for group in groups:
                    if self.read(control, "getClientRects().length"):
                        break
                    self.click('#ees-work-content [data-action=job_group][data-group="' + group + '"]')
                self.wait('!!document.querySelector(' + json.dumps(control) + ')?.getClientRects().length')
        self.click(control)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === "
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
        self.choose("setup-p", chat_id=chat_id)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '신규 공장 횡전개'"
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
            self.browser.evaluate('document.fonts.ready.then(()=>true)')
            data = self.browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]
            (directory / (name + ".png")).write_bytes(base64.b64decode(data))

    def capture_failure_evidence(self):
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        if not any(case is self or getattr(case, "test_case", None) is self for case, _ in failures):
            return
        directory = Path(os.environ.get("EES_TEST_SCREENSHOT_DIR", ROOT / "dist/ees-work-screenshots"))
        evidence = {"test": self.id(), "boundary": "Packaged Native UI, real EES service and temporary SQLite; synthetic authentication/chat",
                    "last_wait": getattr(self, "last_wait_expression", None),
                    "last_click": getattr(self, "last_click_selector", None),
                    "requests": self.server.requests[-20:], "capture_errors": []}
        name = self._testMethodName + "-failure"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # A font-loading failure must still leave the actual failure image.
            data = self.browser.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]
            (directory / (name + ".png")).write_bytes(base64.b64decode(data))
        except Exception as error:
            evidence["capture_errors"].append("screenshot:" + type(error).__name__)
        try:
            # No input values, cookies, storage or authenticated bodies.
            evidence["dom"] = self.browser.evaluate("""(()=>({route:location.pathname+location.search,
                readyState:document.readyState,visibilityState:document.visibilityState,hasFocus:document.hasFocus(),
                nativeReady:window.__eesNativeDraftV1?.ready(),fontsStatus:document.fonts.status,
                controls:[...document.querySelectorAll('button,[role=button],summary,#sidebar,#chat-input,#ees-work-panel')]
                  .slice(0,250).map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                    return {tag:e.tagName,id:e.id,label:e.getAttribute('aria-label'),
                      text:e.matches('button,[role=button],summary')?e.textContent.trim().slice(0,200):null,
                      action:e.getAttribute('data-action'),node:e.getAttribute('data-node-id'),
                      disabled:!!e.disabled,hidden:e.hidden,inert:e.inert,display:s.display,visibility:s.visibility,
                      expanded:e.getAttribute('aria-expanded'),pressed:e.getAttribute('aria-pressed'),
                      rect:{x:r.x,y:r.y,width:r.width,height:r.height},
                      pointerHit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};})}))()""")
        except Exception as error:
            evidence["capture_errors"].append("dom:" + type(error).__name__)
        try:
            (directory / (name + ".json")).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as error:
            print("Native workflow failure evidence unavailable: " + type(error).__name__)

    def visual_style(self, selector):
        """Measure the actual cascade, composited background and text contrast."""
        return self.browser.evaluate("""(selector=>{
            const e=document.querySelector(selector),s=getComputedStyle(e),r=e.getBoundingClientRect();
            const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
            canvas.width=canvas.height=1;
            const rgba=value=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=value;ctx.fillRect(0,0,1,1);
                return [...ctx.getImageData(0,0,1,1).data].map((n,i)=>i===3?n/255:n)};
            const over=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3]));
            let bg=[255,255,255];
            const parents=[];for(let p=e;p;p=p.parentElement)parents.unshift(p);
            parents.forEach(p=>bg=over(rgba(getComputedStyle(p).backgroundColor),bg));
            const fg=over(rgba(s.color),bg),luminance=c=>c.map(n=>n/255)
                .map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4)
                .reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
            const a=luminance(fg),b=luminance(bg);
            return {color:s.color,background:s.backgroundColor,backgroundRGB:bg,foregroundRGB:fg,
                contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),
                fontSize:parseFloat(s.fontSize),fontWeight:parseFloat(s.fontWeight),
                x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,
                outline:s.outlineStyle,outlineWidth:parseFloat(s.outlineWidth),outlineOffset:parseFloat(s.outlineOffset),
                focusVisible:e.matches(':focus-visible'),node:e.dataset.nodeId};
        })(""" + json.dumps(selector) + ")")

    def hover(self, selector=None):
        point = self.browser.evaluate("""(selector=>{
            if(!selector)return {x:innerWidth-5,y:5};
            const e=document.querySelector(selector);e.scrollIntoView({block:'nearest'});
            const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};
        })(""" + json.dumps(selector) + ")")
        self.browser.call("Input.dispatchMouseEvent", {"type": "mouseMoved", **point})

    def save_visual_measurements(self, name, values):
        directory = os.environ.get("EES_TEST_SCREENSHOT_DIR")
        if directory:
            destination = Path(directory)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / (name + ".json")).write_text(
                json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def assert_native_korean_font(self, selector, name):
        """Verify actual rendered glyph font, not only the declared CSS stack."""
        self.browser.evaluate('document.fonts.ready')
        self.browser.call('DOM.enable')
        self.browser.call('CSS.enable')
        document = self.browser.call('DOM.getDocument')
        node = self.browser.call('DOM.querySelector', {'nodeId': document['root']['nodeId'], 'selector': selector})
        fonts = self.browser.call('CSS.getPlatformFontsForNode', {'nodeId': node['nodeId']})['fonts']
        self.save_visual_measurements(name, fonts)
        self.assertTrue(any('Noto Sans KR' in font['familyName'] and font['glyphCount'] > 0
                            for font in fonts), fonts)

    def assert_preserved_styles(self, name, selectors):
        """Compare real Native styles with an optional same-fixture before run.

        Geometry is intentionally excluded: the sidebar may grow when a long
        job wraps, but its scoped palette must not recolor other product areas.
        """
        # Native controls animate theme colors. Wait for their finite CSS
        # transitions so before/after captures compare the applied end style.
        self.browser.evaluate("""Promise.all(document.getAnimations()
            .filter(a=>a.effect?.getTiming().iterations!==Infinity)
            .map(a=>a.finished.catch(()=>{})))""")
        values = self.browser.evaluate("""(selectors=>Object.fromEntries(
            Object.entries(selectors).map(([name,selector])=>{
                const e=document.querySelector(selector);if(!e)return [name,null];
                const s=getComputedStyle(e),properties=['color','backgroundColor','borderTopColor',
                    'borderTopWidth','borderRadius','fontFamily','fontSize','fontWeight','lineHeight',
                    'paddingTop','paddingRight','paddingBottom','paddingLeft','boxShadow'];
                return [name,Object.fromEntries(properties.map(key=>[key,s[key]]))];
            })))""" + "(" + json.dumps(selectors) + ")")
        self.assertTrue(all(value is not None for value in values.values()), values)
        self.save_visual_measurements(name, values)
        baseline = os.environ.get("EES_TEST_STYLE_BASELINE_DIR")
        if baseline:
            expected = json.loads((Path(baseline) / (name + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(values, expected, "Sidebar styling changed an unrelated product area: " + name)

    def test_sidebar_scoped_styles_preserve_right_workspace_and_native_controls(self):
        self.seed_case("existing-chat")
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        for width, height in ((1920, 1080), (900, 900)):
            for theme in ("light", "dark"):
                self.browser.call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                for kind, node in (("p", "setup-p"), ("t", "install-t"), ("j", "db-j")):
                    self.choose(node)
                    self.hover()
                    selectors = {"panel": "#ees-work-panel", "title": "#ees-work-panel .ew-title",
                                 "site": "#ees-work-site-trigger", "system": "#ees-work-system-trigger",
                                 "nativeModel": "#model-selector-model-button", "chat": "#chat-input"}
                    if kind == "j":
                        selectors.update(run="#ees-work-run", save="#ees-work-inputs-save",
                                         input='#ees-work-inputs input[name="db"]')
                    self.assert_preserved_styles("unaffected-" + kind + "-" + theme + "-" + str(width), selectors)
                    self.screenshot("sidebar-comparison-" + kind + "-" + theme + "-" + str(width))
        self.open_authoring()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        for width, height in ((1920, 1080), (600, 900)):
            for theme in ("light", "dark"):
                self.browser.call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                self.hover()
                self.assert_preserved_styles("unaffected-workspace-" + theme + "-" + str(width), {
                    "editorTitle": "#ees-work-node-form h2", "aiTitle": "#ees-work-authoring h2",
                    "selected": '#ees-work-designer [data-action=edit_node][aria-current=step]',
                    "input": "#ees-work-node-form input[name=name]", "aiInput": "#ees-work-authoring-input",
                    "apply": "#ees-work-node-form > button[type=submit]", "model": "#ees-work-authoring-model"})
                self.screenshot("sidebar-comparison-workspace-" + theme + "-" + str(width))

    def seed_large_case(self, conditioned=False):
        """Arrange synthetic volume; execute it through the real runtime service.

        Counts and evidence come from real actions. Nothing here adds sample
        jobs, dates or success results to the production seed or browser DOM.
        """
        state = self.current()
        definition = deepcopy(state["catalog"])
        nodes = definition["nodes"]
        process = dict(deepcopy(nodes["setup-p"]), id="bulk-p", name="대량 작업 검증",
                       children=["bulk-t"], skills=[])
        stage = dict(deepcopy(nodes["prep-t"]), id="bulk-t", name="대량 검증 단계",
                     parent="bulk-p", children=[])
        nodes.update({"bulk-p": process, "bulk-t": stage})
        definition["roots"]["setup"].append("bulk-p")
        for number in range(105):
            node_id = f"bulk-{number:03d}-j"
            template = nodes["ap-j"] if number == 2 else nodes["db-j"] if number == 52 else nodes["scope-j"]
            node = dict(deepcopy(template), id=node_id, name=f"검증 작업 {number:03d}",
                        parent="bulk-t", deps=[])
            if conditioned and number in (30, 52):
                node["deps"] = ["bulk-000-j"]
            if number == 52:
                node["name"] += " · 생산설비 인터페이스 데이터베이스 연결과 현장 적용 대상 확인"
            if number == 3:
                node["mode"] = "draft"
            if number == 4:
                node["enabled"] = False
            if number == 5:
                tool = dict(deepcopy(definition["tools"]["gateway"]),
                            id="bulk-unavailable", name="미연결 진단", adapter="unavailable")
                definition["tools"][tool["id"]] = tool
                node.update(mode="tool", tools=[tool["id"]], bindings={tool["id"]: "db"})
            nodes[node_id] = node
            stage["children"].append(node_id)
        self.publish_runtime_fixture(definition)
        state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            "action": "create", "chat_id": "existing-chat",
            "payload": {"site_id": "us-a", "system": "EMS", "process_id": "bulk-p"}}))
        self.assertTrue(state["ok"], state)
        for number, payload in ((0, {"confirm": True}), (1, {"confirm": True}),
                                (2, {}), (3, {"document": "담당자가 검토할 합성 초안"})):
            case = state["case"]
            state = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                "action": "run", "chat_id": "existing-chat", "case_id": case["id"],
                "expected_revision": case["revision"], "node_id": f"bulk-{number:03d}-j",
                "payload": payload}))
            self.assertTrue(state["ok"], state)
        self.assertEqual(state["case"]["progress"], {"done": 2, "total": 104})
        return state["case"]

    def attach_file(self):
        path = Path(self.temporary.name) / "attachment.txt"
        path.write_text("fixture file", encoding="utf-8")
        document = self.browser.call("DOM.getDocument")
        field = self.browser.call("DOM.querySelector", {"nodeId": document["root"]["nodeId"],
                                                        "selector": 'input[type="file"]'})
        self.browser.call("DOM.setFileInputFiles", {"nodeId": field["nodeId"], "files": [str(path)]})
        self.wait("document.querySelector('#chat-container')?.innerText.includes('attachment.txt')")

    def test_sidebar_step_progress_keeps_all_stages_and_only_selected_stage_jobs(self):
        self.create_case()
        nodes = self.current()["case"]["definition"]["nodes"]
        stage_ids = lambda: self.browser.evaluate(
            "[...document.querySelectorAll('#ees-work-tree .ew-step-button')].map(e=>e.dataset.nodeId)")
        job_ids = lambda: self.browser.evaluate(
            "[...document.querySelectorAll('#ees-work-tree .ew-step-job')].map(e=>e.dataset.nodeId)")
        self.assertEqual(stage_ids(), nodes["setup-p"]["children"])
        self.assertEqual(self.browser.evaluate(
            "[...document.querySelectorAll('#ees-work-tree .ew-step-number')].map(e=>e.textContent)"),
            [str(index + 1) for index in range(len(nodes["setup-p"]["children"]))])
        self.assertIsNone(self.read('#ees-work-tree [data-action="expand"]'))
        for forbidden in ("P 프로세스", "T 태스크", "J 잡", "이 단계에서 할 일", "지금 확인할 작업",
                          "점검할 대상을 선택하세요", "이전 결과를 확인하세요"):
            self.assertNotIn(forbidden, self.text("#ees-work-entry"))
        self.choose("prep-t")
        self.assertEqual(job_ids(), nodes["prep-t"]["children"])
        self.assertTrue(self.browser.evaluate("""[...document.querySelectorAll('#ees-work-tree .ew-step-job')]
            .every(button=>button.children.length===2&&button.children[0].matches('.ew-step-job-name')
                &&button.children[1].matches('.ew-work-state')&&button.children[1].textContent.trim())"""))
        self.choose("scope-j")
        self.assertEqual(self.read('#ees-work-tree .ew-step[data-step-id="prep-t"]',
                                   "dataset.expanded"), "true")
        self.assertEqual(self.read('#ees-work-tree .ew-step-job[data-node-id="scope-j"]',
                                   "getAttribute('aria-current')"), "step")
        before = self.current()["case"]
        self.click("#ees-work-close")
        self.click("#ees-work-context-open")
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.assertEqual(job_ids(), nodes["prep-t"]["children"])
        self.assertEqual(self.current()["case"], before)
        self.click("#ees-work-run", confirm=True)
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.current()["case"]["jobs"]["scope-j"]["status"], "passed")
        self.assertEqual(self.current()["case"]["selected_id"], "scope-j")
        self.assertIn("완료", self.text('#ees-work-tree .ew-step-job[data-node-id="scope-j"]'))
        self.assertEqual(job_ids(), nodes["prep-t"]["children"],
                         "Finishing a job must keep its result and list position visible")
        self.choose("install-t")
        self.assertEqual(stage_ids(), nodes["setup-p"]["children"])
        self.assertEqual(job_ids(), nodes["install-t"]["children"])
        self.choose("setup-p")
        self.assertEqual(self.text('#ees-work-content .ew-work-level'), '워크플로우')
        self.assertIsNotNone(self.read('[data-work-metric="jobs"]'))
        self.assertEqual(stage_ids(), nodes["setup-p"]["children"])
        self.screenshot("ees-step-progress-workflow")

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
                            font('#ees-work-tree [data-action=select]'),font('#ees-work-panel .ew-title')],
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
                    self.assertAlmostEqual(measures["site"]["top"], measures["system"]["top"], delta=1)
                    self.assertAlmostEqual(measures["site"]["width"], measures["system"]["width"], delta=1)
                    self.assertLessEqual(measures["site"]["right"], measures["system"]["left"] + 1)
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
        saved_inputs = deepcopy(self.current()["case"]["jobs"]["db-j"]["inputs"])
        self.fill('#ees-work-inputs input[name="db"]', "아직 반영하지 않은 진단 대상")
        self.assertFalse(self.read('[data-work-dirty]', 'hidden'))
        self.assertTrue(self.read('#ees-work-run', 'disabled'))
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
        self.assertEqual(self.read('#ees-work-inputs input[name="db"]', 'value'), "아직 반영하지 않은 진단 대상")
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["inputs"], saved_inputs)
        self.assertEqual(self.current()["case"]["selected_id"], "db-j")
        self.assertIn("attachment.txt", self.text("#chat-container"))
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

    def test_integrated_large_job_browser_counts_filters_pages_and_selection(self):
        saved = self.seed_large_case()
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.choose('bulk-p')
        self.assertEqual(self.text('[data-work-metric="stages"] strong'), '0 / 1')
        self.assertEqual(self.text('[data-work-metric="jobs"] strong'), '2 / 104')
        self.assertEqual(self.text('[data-work-metric="incomplete"] strong'), '102개 작업')
        self.assertEqual(self.text('[data-work-metric="attention"] strong'), '2개 작업')
        self.assertIn('적용 제외 1개 작업', self.text('#ees-work-content'))
        self.choose('bulk-t')
        rows = "#ees-work-content [data-work-job]"
        self.assertEqual(self.browser.evaluate('document.querySelectorAll(' + json.dumps(rows) + ').length'), 25)
        self.assertIn('1–25 / 105개 작업', self.text('.ew-work-pagination'))
        self.click('[data-action="job_page"][data-page="1"]')
        self.assertIn('26–50 / 105개 작업', self.text('.ew-work-pagination'))
        self.fill('#ees-work-job-search', '작업 104')
        self.assertEqual(self.browser.evaluate('document.querySelectorAll(' + json.dumps(rows) + ').length'), 1)
        self.assertIn('1–1 / 1개 작업', self.text('.ew-work-pagination'))
        self.assertIsNone(self.read('[data-action="job_page"]'), "One page does not need disabled pagination")
        self.click('[data-work-job="bulk-104-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 104'")
        self.assertEqual(self.current()['case']['selected_id'], 'bulk-104-j')
        sidebar_jobs = lambda: self.browser.evaluate(
            "[...document.querySelectorAll('#ees-work-tree .ew-step-job')].map(e=>e.dataset.nodeId)")
        self.assertLessEqual(len(sidebar_jobs()), 5)
        self.assertIn('bulk-104-j', sidebar_jobs())
        self.assertIn('전체 105개 작업 보기', self.text('#ees-work-tree'))
        before_refresh = sidebar_jobs()
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.assertEqual(sidebar_jobs(), before_refresh)
        self.choose('bulk-t')
        self.assertEqual(self.read('#ees-work-job-search', 'value'), '작업 104')
        self.fill('#ees-work-job-search', '작업 000')
        self.click('[data-work-job="bulk-000-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 000'")
        self.assertIn('담당자 확인이 완료됐습니다.', self.text('#ees-work-content'))
        self.assertIn('bulk-000-j', sidebar_jobs())
        self.choose('bulk-t')
        self.fill('#ees-work-job-search', '작업 052')
        self.click('[data-work-job="bulk-052-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent.includes('검증 작업 052')")
        self.assertIn('bulk-052-j', sidebar_jobs())
        self.assertEqual(sidebar_jobs(), sorted(sidebar_jobs()), 'Summary preserves definition order')
        self.fill('#ees-work-inputs input[name="db"]', '중간 작업의 미반영 입력')
        self.fill('#chat-input', '대량 작업 탐색 중인 대화 초안')
        selected_summary = sidebar_jobs()
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.assertEqual(sidebar_jobs(), selected_summary)
        self.assertEqual(self.read('#ees-work-inputs input[name="db"]', 'value'), '중간 작업의 미반영 입력')
        self.choose('bulk-t')
        self.fill('#ees-work-job-search', '')
        for page in range(1, 5):
            self.click('[data-action="job_page"][data-page="' + str(page) + '"]')
        self.assertIn('101–105 / 105개 작업', self.text('.ew-work-pagination'))
        self.click('[data-work-job="bulk-104-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 104'")
        self.choose('bulk-052-j')
        self.assertEqual(self.read('#ees-work-inputs input[name="db"]', 'value'), '중간 작업의 미반영 입력')
        self.assertEqual(self.text('#chat-input'), '대량 작업 탐색 중인 대화 초안')
        self.screenshot('ees-step-progress-large-selected-middle')
        self.choose('bulk-t')
        self.fill('#ees-work-job-search', '')
        for status, expected in (("completed", ["bulk-000-j", "bulk-001-j"]),
                                 ("attention", ["bulk-002-j", "bulk-005-j"]),
                                 ("excluded", ["bulk-004-j"])):
            with self.subTest(filter=status):
                self.click('[data-action="job_filter"][data-filter="' + status + '"]')
                actual = self.browser.evaluate('Array.from(document.querySelectorAll(' + json.dumps(rows)
                                               + '), row => row.dataset.workJob)')
                self.assertEqual(actual, expected)
        self.assertIn('적용 제외', self.text(rows))
        self.click('[data-action="job_filter"][data-filter="incomplete"]')
        self.assertIn('1–25 / 102개 작업', self.text('.ew-work-pagination'))
        self.fill('#ees-work-job-search', '존재하지 않는 작업')
        self.assertIn('일치하는 작업이 없습니다.', self.text('#ees-work-content'))
        self.assertIn('0–0 / 0개 작업', self.text('.ew-work-pagination'))
        self.assertIsNone(self.read('[data-action="job_page"]'))
        self.assertEqual(self.current()['case']['jobs'], saved['jobs'],
                         'Browsing, filtering and selecting cannot execute or rewrite results')
        self.screenshot('ees-integrated-large-job-browser')

    def test_right_stage_condition_navigation_restores_list_page_scroll_and_edits(self):
        before = self.seed_large_case(conditioned=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.choose('bulk-052-j')
        self.fill('#ees-work-inputs input[name="db"]', '복귀 후에도 보존할 미반영 대상')
        self.fill('#chat-input', '조건을 확인하는 중인 대화 초안')
        self.choose('bulk-p')
        self.click('.ew-work-job-finder > summary')
        self.assertTrue(self.read('.ew-work-job-finder', 'open'))
        self.click('[data-work-job="bulk-000-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 000'")
        self.click('[data-action="panel_back"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 작업 검증'")
        self.assertTrue(self.read('.ew-work-job-finder', 'open'),
                        'Returning to P must preserve a manually expanded finder even with no query or filter')
        distribution = self.text('[data-work-distribution="bulk-t"]')
        self.assertIn('실패 1', distribution)
        self.assertIn('실행 연결 필요 1', distribution)
        self.assertEqual(self.text('[data-work-metric="attention"] strong'), '2개 작업')
        self.click('#ees-work-content [data-action="select"][data-node-id="bulk-t"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 검증 단계'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")

        def capture_expanded_condition(kind, selector):
            for width, height in ((1920, 1080), (900, 900)):
                for theme in ('light', 'dark'):
                    with self.subTest(condition=kind, width=width, theme=theme):
                        self.browser.call('Emulation.setDeviceMetricsOverride', {
                            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                        self.browser.evaluate("document.documentElement.classList.toggle('dark',"
                                              + str(theme == 'dark').lower() + ')')
                        self.browser.evaluate('document.querySelector(' + json.dumps(selector)
                                              + ').scrollIntoView({block:"center"})')
                        self.hover()
                        self.assertGreaterEqual(self.visual_style(selector + ' p')['contrast'], 4.5)
                        self.assertLessEqual(self.read('#ees-work-content', 'scrollWidth'),
                                             self.read('#ees-work-content', 'clientWidth') + 1)
                        self.assertEqual(self.current()['case']['selected_id'], 'bulk-t')
                        self.screenshot('ees-right-t-' + kind + '-' + theme + '-' + str(width))
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
            self.browser.evaluate("document.documentElement.classList.remove('dark')")

        self.click('[data-action="job_filter"][data-filter="attention"]')
        failed_toggle = '[data-action="job_condition"][data-node-id="bulk-002-j"]'
        self.browser.evaluate('document.querySelector(' + json.dumps(failed_toggle) + ').focus()')
        self.key('Enter', 13, text='\r')
        failed_condition = '[data-work-condition="bulk-002-j"]'
        self.assertEqual(self.read(failed_toggle, 'getAttribute("aria-expanded")'), 'true')
        failed_checks = [check for check in before['jobs']['bulk-002-j']['checks']
                         if check['status'] == 'failed']
        self.assertTrue(failed_checks, 'The displayed failure must come from a real saved execution')
        for check in failed_checks:
            self.assertIn(check['detail'], self.text(failed_condition))
        capture_expanded_condition('failure-expanded', failed_condition)
        self.click(failed_toggle)
        self.assertIsNone(self.read(failed_condition))
        self.fill('#ees-work-job-search', '검증 작업')
        self.click('[data-action="job_filter"][data-filter="incomplete"]')
        self.click('[data-action="job_page"][data-page="1"]')
        toggle = '[data-action="job_condition"][data-node-id="bulk-030-j"]'
        self.click(toggle)
        self.assertEqual(self.current()['case']['selected_id'], 'bulk-t', 'Expanding conditions must not open J')
        self.assertEqual(self.read(toggle, 'getAttribute("aria-expanded")'), 'true')
        condition = '[data-work-condition="bulk-030-j"]'
        self.assertIn('검증 작업 000', self.text(condition))
        self.assertIn('완료', self.text(condition))
        capture_expanded_condition('prerequisite-expanded', condition)
        dependency = condition + ' [data-action="select"][data-node-id="bulk-000-j"]'
        self.browser.evaluate('document.querySelector(' + json.dumps(dependency) + ').scrollIntoView({block:"center"})')
        scroll = self.read('#ees-work-content', 'scrollTop')
        self.assertGreater(scroll, 0)
        self.click(dependency)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 000'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.read('#ees-work-content', 'scrollTop'), 0)
        self.click('[data-action="panel_back"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 검증 단계'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.read('#ees-work-job-search', 'value'), '검증 작업')
        self.assertEqual(self.read('[data-action="job_filter"][data-filter="incomplete"]', 'getAttribute("aria-pressed")'), 'true')
        self.assertIn('26–50 / 102개 작업', self.text('.ew-work-pagination'))
        self.assertEqual(self.read(toggle, 'getAttribute("aria-expanded")'), 'true')
        self.assertAlmostEqual(self.read('#ees-work-content', 'scrollTop'), scroll, delta=2)
        self.assertTrue(self.browser.evaluate('document.activeElement?.matches(' + json.dumps(dependency) + ')'))
        self.hover()
        self.screenshot('ees-right-t-condition-return-preserved')
        self.click('[data-work-job="bulk-030-j"] [data-action="select"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '검증 작업 030'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.click('[data-action="panel_back"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 검증 단계'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.read(toggle, 'getAttribute("aria-expanded")'), 'true')
        self.choose('bulk-052-j')
        self.assertEqual(self.read('#ees-work-inputs input[name="db"]', 'value'), '복귀 후에도 보존할 미반영 대상')
        self.assertEqual(self.text('#chat-input'), '조건을 확인하는 중인 대화 초안')
        self.assertEqual(self.current()['case']['jobs'], before['jobs'])
        self.screenshot('ees-right-condition-return-preserved')

    def test_right_recorded_attempt_calls_and_inputs_do_not_mix_after_retry_or_publish(self):
        self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.run_job('ap-j', 'failed')
        first = deepcopy(self.current()['case']['jobs']['ap-j']['history'][0])
        self.fill('#ees-work-inputs input[name="ap"]', '두 번째 시도 합성 AP 대상')
        self.click('#ees-work-inputs-save')
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.run_job('ap-j')
        case = self.current()['case']
        records = deepcopy(case['jobs']['ap-j']['history'])
        self.assertEqual(records[0], first)
        self.assertNotEqual(records[0]['checks'][2]['input'], records[1]['checks'][2]['input'])
        state = self.current()
        definition = deepcopy(state['catalog'])
        definition['tools']['health']['name'] = '새 게시본만의 다른 도구 이름'
        self.publish_runtime_fixture(definition)
        self.click('[data-action="work_detail"][data-detail-tab="config"]')
        self.assertIn('진행 건에 고정된 절차 v' + str(case['version']), self.text('#ees-work-dialog'))
        self.assertNotIn('새 게시본만의 다른 도구 이름', self.text('#ees-work-dialog'))
        self.assertIn('개별 도구 버전', self.text('#ees-work-dialog'))
        self.click('[data-action="detail_tab"][data-detail-tab="output"]')
        self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="2"]')
        self.assertIn('업무 통과', self.text('.ew-detail-outcome'))
        self.assertEqual(self.text('[data-call-output]'), records[1]['checks'][2]['detail'])
        self.assertIn('미확인', self.text('[data-format-check]'))
        self.click('[data-action="detail_attempt"][data-attempt-index="0"]')
        self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="2"]')
        self.assertIn('업무 실패', self.text('.ew-detail-outcome'))
        self.assertEqual(self.text('[data-call-verdict]'), '점검 실패')
        self.assertEqual(self.text('[data-call-output]'), records[0]['checks'][2]['detail'])
        self.assertIn('미확인', self.text('[data-format-check]'))
        self.click('[data-action="detail_tab"][data-detail-tab="input"]')
        self.assertEqual(self.text('[data-call-input]'), records[0]['checks'][2]['input'])
        self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="3"]')
        self.assertIsNone(self.read('[data-call-input]'))
        self.assertIn('전달 입력 없음 · 미수행', self.text('#ees-work-dialog'))
        self.click('[data-action="detail_attempt"][data-attempt-index="1"]')
        self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="2"]')
        self.assertEqual(self.text('[data-call-input]'), records[1]['checks'][2]['input'])
        self.assert_native_korean_font('[data-call-input]', 'ees-right-input-rendered-font')
        self.browser.evaluate("document.querySelector('[data-call-input]').scrollIntoView({block:'center'})")
        self.screenshot('ees-right-recorded-call-input-after-retry')
        self.key('Escape', 27)
        self.assertEqual(self.current()['case']['jobs']['ap-j']['history'], records)
        self.assertEqual(self.current()['case']['definition']['tools']['health']['name'], case['definition']['tools']['health']['name'])

    def test_right_panels_and_details_keyboard_light_dark_narrow(self):
        self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.run_job('ap-j', 'failed')
        for width, height in ((1920, 1080), (1536, 960), (1366, 900), (900, 900)):
            for theme in ('light', 'dark'):
                with self.subTest(width=width, theme=theme):
                    self.browser.call('Emulation.setDeviceMetricsOverride', {
                        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                    self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == 'dark').lower() + ')')
                    for kind, node in (('p', 'setup-p'), ('t', 'install-t'), ('j', 'ap-j')):
                        self.choose(node)
                        self.hover()
                        self.assertIsNone(self.read('.ew-work-next'))
                        self.assertNotIn('지금 할 일', self.text('#ees-work-content'))
                        self.assertNotIn('다음 할 일', self.text('#ees-work-content'))
                        self.assertGreaterEqual(self.visual_style('#ees-work-panel .ew-title')['contrast'], 4.5)
                        self.screenshot('ees-right-' + kind + '-' + theme + '-' + str(width))
                    case = self.current()['case']
                    self.assertIn(case['jobs']['ap-j']['inputs'].get('ap', case['site']['ap']),
                                  self.text('[data-work-section="target"]'))
                    self.assertIsNone(self.read('[data-work-section="target"] input,[data-work-section="target"] select'))
                    self.click('[data-action="work_detail"][data-detail-tab="output"]')
                    self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="2"]')
                    self.hover()
                    self.assertGreaterEqual(self.visual_style('[data-call-output]')['contrast'], 4.5)
                    bounds = self.browser.evaluate("(()=>{const d=document.querySelector('#ees-work-dialog'),r=d.getBoundingClientRect();return {left:r.left,right:r.right,width:innerWidth,scroll:d.scrollWidth,client:d.clientWidth}})()")
                    self.assertGreaterEqual(bounds['left'], 0)
                    self.assertLessEqual(bounds['right'], bounds['width'])
                    self.assertLessEqual(bounds['scroll'], bounds['client'] + 1)
                    self.browser.evaluate("document.querySelector('[data-action=detail_tab][data-detail-tab=history]').focus()")
                    self.key('Tab', 9)
                    focus = self.browser.evaluate("(()=>{const e=document.activeElement,s=getComputedStyle(e);return {inside:!!e.closest('#ees-work-dialog'),visible:e.matches(':focus-visible'),width:parseFloat(s.outlineWidth)}})()")
                    self.assertTrue(focus['inside'])
                    self.assertTrue(focus['visible'])
                    self.assertGreaterEqual(focus['width'], 2)
                    self.screenshot('ees-right-detail-failure-' + theme + '-' + str(width))
                    self.assert_native_korean_font('[data-call-output]', 'ees-right-output-font-' + theme + '-' + str(width))
                    self.browser.evaluate("document.querySelector('[data-call-output]').scrollIntoView({block:'center'})")
                    self.screenshot('ees-right-detail-output-' + theme + '-' + str(width))
                    self.key('Escape', 27)
                    self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-action=work_detail][data-detail-tab=output]')"))
        self.choose('db-j')
        self.click('[data-action="work_detail"][data-detail-tab="history"]')
        self.assertEqual(self.read('[data-record-state]', 'dataset.recordState'), 'not-executed')
        self.assertIn('미수행 · 실행 기록 없음', self.text('#ees-work-dialog'))
        self.assertIsNone(self.read('[data-call-output]'))
        self.screenshot('ees-right-no-execution-record')

    def test_detail_keeps_opened_attempt_call_and_return_focus_after_new_result(self):
        case = self.seed_case('existing-chat', ready=True)
        # Arrange past attempts through the same real service. The browser
        # retry path is covered separately; this test isolates a fresh result
        # arriving while the user is reading an existing attempt.
        for action, payload in (('run', {}), ('update_inputs', {'inputs': {'ap': '두 번째 실행의 저장된 대상'}}), ('run', {})):
            result = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                'action': action, 'case_id': case['id'], 'chat_id': 'existing-chat',
                'node_id': 'ap-j', 'expected_revision': case['revision'], 'payload': payload}))
            self.assertTrue(result['ok'], result)
            case = result['case']
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.choose('ap-j')
        saved = deepcopy(self.current()['case']['jobs']['ap-j']['history'])
        self.assertEqual([record['status'] for record in saved], ['failed', 'passed'])
        self.click('[data-action="work_detail"][data-detail-tab="output"]')
        self.click('[data-action="detail_tab"][data-detail-tab="input"]')
        self.click('.ew-detail-calls [data-action="detail_call"][data-call-index="2"]')
        self.assertEqual(self.text('[data-call-input]'), saved[1]['checks'][2]['input'])
        case = self.current()['case']
        for action, payload in (('update_inputs', {'inputs': {'ap': '새로 완료된 세 번째 실행 대상'}}), ('run', {})):
            result = asyncio.run(self.server.workflow.handle_action(self.server.user, {
                'action': action, 'case_id': case['id'], 'chat_id': 'existing-chat',
                'node_id': 'ap-j', 'expected_revision': case['revision'], 'payload': payload}))
            self.assertTrue(result['ok'], result)
            case = result['case']
        self.assertEqual(len(case['jobs']['ap-j']['history']), 3)
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.assertEqual(self.read('[data-action="detail_attempt"][aria-pressed=true]', 'dataset.attemptIndex'), '1')
        self.assertEqual(self.read('[data-action="detail_call"][aria-pressed=true]', 'dataset.callIndex'), '2')
        self.assertEqual(self.text('[data-call-input]'), saved[1]['checks'][2]['input'])
        self.assertEqual(self.current()['case']['jobs']['ap-j']['history'][:2], saved)
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-action=work_detail][data-detail-tab=output]')"))

    def test_a_design_long_korean_panels_dialog_scroll_and_retained_user_width(self):
        # Publish real supported fields, then render the frozen case in the
        # packaged Native UI. No text or layout is injected into its DOM.
        state = self.current()
        definition = deepcopy(state['catalog'])
        targets = ('setup-p', 'install-t', 'db-j')
        for node_id in targets:
            node = definition['nodes'][node_id]
            node['name'] += ' · 해외 생산설비 인터페이스와 데이터베이스 연결 상태 및 현장 적용 대상 확인'
            node['description'] = '긴 한글 설명을 읽으며 공장과 시스템의 적용 범위, 작업 전제와 완료 기준을 확인합니다. ' * 10
            node['instructions'] = '등록된 업무 안내에 따라 담당자와 함께 입력값 및 저장된 결과를 확인합니다. ' * 35
        self.publish_runtime_fixture(definition)
        before = self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.open_work_panel()
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.wait_scope_ready('site')
        self.fill('#chat-input', '긴 업무 내용을 확인하는 동안 유지할 대화 초안')
        measurements = []
        for width, height in ((1920, 1080), (1536, 960), (1366, 900)):
            for theme in ('light', 'dark'):
                with self.subTest(width=width, theme=theme):
                    self.browser.call('Emulation.setDeviceMetricsOverride', {
                        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                    self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == 'dark').lower() + ')')
                    for node_id in targets:
                        self.choose(node_id)
                        self.hover()
                        self.assertEqual(self.text('#ees-work-panel .ew-title'), definition['nodes'][node_id]['name'])
                        layout = self.browser.evaluate("""(()=>{
                            const box=s=>document.querySelector(s).getBoundingClientRect().toJSON();
                            const title=document.querySelector('#ees-work-panel .ew-title'),content=document.querySelector('#ees-work-content');
                            return {chat:box('#chat-pane'),composer:box('#chat-input'),panel:box('#ees-work-panel'),
                                title:box('#ees-work-panel .ew-title'),titleHeight:title.clientHeight,titleScroll:title.scrollHeight,
                                titleWidth:title.clientWidth,titleScrollWidth:title.scrollWidth,
                                font:parseFloat(getComputedStyle(title).fontSize),contentHeight:content.clientHeight,
                                contentScroll:content.scrollHeight,pageWidth:document.documentElement.scrollWidth};})()""")
                        self.assertLessEqual(layout['pageWidth'], width + 1)
                        self.assertGreaterEqual(layout['chat']['width'], 420)
                        self.assertLessEqual(layout['chat']['right'], layout['panel']['left'] + 1)
                        self.assertLessEqual(layout['titleScroll'], layout['titleHeight'] + 1)
                        self.assertLessEqual(layout['titleScrollWidth'], layout['titleWidth'] + 1)
                        self.assertGreaterEqual(layout['font'], 28)
                        self.assertLessEqual(layout['font'], 30)
                        self.assertLessEqual(layout['composer']['bottom'], height)
                        self.assertGreater(layout['contentScroll'], layout['contentHeight'])
                        content = self.read('#ees-work-content', 'getBoundingClientRect().toJSON()')
                        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
                            'x': content['x'] + content['width'] / 2, 'y': content['y'] + content['height'] / 2,
                            'deltaX': 0, 'deltaY': 400})
                        self.wait("document.querySelector('#ees-work-content').scrollTop > 0")
                        self.assertAlmostEqual(self.read('#chat-input', 'getBoundingClientRect().y'),
                                               layout['composer']['y'], delta=1)
                        measurements.append({'width': width, 'theme': theme, 'node': node_id, **layout})
                        self.browser.evaluate("document.querySelector('#ees-work-content').scrollTop=0")
                        self.screenshot('ees-a-long-' + node_id + '-' + theme + '-' + str(width))
                    self.click('[data-action="work_detail"][data-detail-tab="config"]')
                    dialog = self.browser.evaluate("""(()=>{
                        const d=document.querySelector('#ees-work-dialog'),b=d.querySelector('.ew-dialog-body');
                        return {rect:d.getBoundingClientRect().toJSON(),scroll:d.scrollWidth,client:d.clientWidth,
                            bodyHeight:b.clientHeight,bodyScroll:b.scrollHeight,
                            headerY:d.querySelector('#ees-work-dialog-title').getBoundingClientRect().y};})()""")
                    self.assertGreaterEqual(dialog['rect']['top'], 8)
                    self.assertLessEqual(dialog['rect']['bottom'], height - 8)
                    self.assertGreaterEqual(dialog['rect']['left'], 8)
                    self.assertLessEqual(dialog['rect']['right'], width - 8)
                    self.assertLessEqual(dialog['scroll'], dialog['client'] + 1)
                    self.assertGreater(dialog['bodyScroll'], dialog['bodyHeight'])
                    body = self.read('#ees-work-dialog .ew-dialog-body', 'getBoundingClientRect().toJSON()')
                    self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel',
                        'x': body['x'] + body['width'] / 2, 'y': body['y'] + body['height'] / 2,
                        'deltaX': 0, 'deltaY': 700})
                    self.wait("document.querySelector('#ees-work-dialog .ew-dialog-body').scrollTop > 0")
                    self.assertAlmostEqual(self.read('#ees-work-dialog-title', 'getBoundingClientRect().y'),
                                           dialog['headerY'], delta=1)
                    close = self.read('#ees-work-dialog [data-dialog-close]', 'getBoundingClientRect().toJSON()')
                    self.assertGreaterEqual(close['top'], 8)
                    self.assertLessEqual(close['bottom'], height - 8)
                    focusables = "[...document.querySelectorAll('#ees-work-dialog button,#ees-work-dialog input,#ees-work-dialog textarea,#ees-work-dialog select,#ees-work-dialog a[href],#ees-work-dialog summary,#ees-work-dialog [tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length)"
                    self.browser.evaluate('(' + focusables + ').at(-1).focus()')
                    self.key('Tab', 9)
                    self.assertTrue(self.browser.evaluate('document.activeElement === (' + focusables + ')[0]'))
                    self.key('Tab', 9, modifiers=8)
                    self.assertTrue(self.browser.evaluate('document.activeElement === (' + focusables + ').at(-1)'))
                    self.screenshot('ees-a-long-dialog-' + theme + '-' + str(width))
                    self.key('Escape', 27)
                    self.wait("!document.querySelector('#ees-work-dialog')")
                    self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-action=work_detail][data-detail-tab=config]')"))
                    self.assertEqual(self.text('#chat-input'), '긴 업무 내용을 확인하는 동안 유지할 대화 초안')
        self.save_visual_measurements('ees-a-long-layouts', measurements)
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait("(() => {const p=document.querySelector('#ees-work-panel');return p&&!p.classList.contains('ew-narrow')"
                  + "&&p.getBoundingClientRect().width===parseFloat(p.style.width)})()")
        self.browser.evaluate("document.querySelector('#ees-work-resizer').focus()")
        original = self.read('#ees-work-panel', 'getBoundingClientRect().width')
        self.key('ArrowLeft', 37)
        chosen = self.read('#ees-work-panel', 'getBoundingClientRect().width')
        self.assertGreater(chosen, original)
        self.click('#ees-work-close')
        self.click('#ees-work-context-open')
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), chosen, delta=1)
        self.assertEqual(self.current()['case']['jobs'], before['jobs'])

    def test_a_design_pending_execution_is_not_completion_and_releases_only_one_result(self):
        # The published dependency is valid but intentionally differs from the
        # default demo: this scenario requires DB completion before AP is ready.
        state = self.current()
        definition = deepcopy(state['catalog'])
        definition['nodes']['ap-j']['deps'].append('db-j')
        self.publish_runtime_fixture(definition)
        self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.choose('db-j')
        before = deepcopy(self.current()['case'])
        self.assertFalse(before['node_states']['ap-j']['ready_for_run'])
        original = self.server.workflow.handle_action
        started, release = threading.Event(), threading.Event()

        async def held_execution(user, body):
            if body.get('action') == 'run' and body.get('node_id') == 'db-j':
                started.set()
                if not await asyncio.to_thread(release.wait, 12):
                    raise AssertionError('Execution hold was not released by the test')
            return await original(user, body)

        with patch.object(self.server.workflow, 'handle_action', held_execution):
            try:
                self.click('#ees-work-run')
                self.assertTrue(started.wait(timeout=2))
                self.wait("document.querySelector('#ees-work-panel')?.getAttribute('aria-busy') === 'true'")
                self.assertTrue(self.read('#ees-work-run', 'disabled'))
                self.assertTrue(self.read('#ees-work-inputs-save', 'disabled'))
                self.assertFalse(self.read('#ees-work-pending-status', 'hidden'))
                self.assertIn('결과를 기다리고', self.text('#ees-work-pending-status'))
                self.assertNotIn('완료 기준을 충족했습니다.', self.text('#ees-work-content'))
                self.assertEqual(self.current()['case']['jobs'], before['jobs'])
                requests = self.server.requests.count(('POST', '/api/ees-work/action'))
                point = self.read('#ees-work-run', 'getBoundingClientRect().toJSON()')
                for event_type in ('mousePressed', 'mouseReleased'):
                    self.browser.call('Input.dispatchMouseEvent', {'type': event_type,
                        'x': point['x'] + point['width'] / 2, 'y': point['y'] + point['height'] / 2,
                        'button': 'left', 'buttons': 1 if event_type == 'mousePressed' else 0, 'clickCount': 1})
                self.key('Enter', 13, text='\r')
                self.assertEqual(self.server.requests.count(('POST', '/api/ees-work/action')), requests)
                self.screenshot('ees-a-real-request-pending')
            finally:
                release.set()
            self.wait("document.querySelector('#ees-work-panel')?.getAttribute('aria-busy') === 'false'")
        after = self.current()['case']
        self.assertEqual(after['jobs']['db-j']['attempt'], before['jobs']['db-j']['attempt'] + 1)
        self.assertEqual(after['jobs']['db-j']['status'], 'passed')
        self.assertEqual(after['progress']['done'], before['progress']['done'] + 1)
        self.assertTrue(after['node_states']['ap-j']['ready_for_run'])
        self.assertEqual(after['jobs']['ap-j'], before['jobs']['ap-j'])
        self.assertTrue(self.read('#ees-work-pending-status', 'hidden'))
        for node_id in ('install-t', 'setup-p'):
            self.choose(node_id)
            progress = after['node_states'][node_id]['progress']
            self.assertEqual(self.text('[data-work-metric="jobs"] strong'),
                             f"{progress['done']} / {progress['total']}")

    def test_right_record_lookup_failure_and_restriction_do_not_show_stale_evidence(self):
        self.seed_case('existing-chat', ready=True)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.run_job('db-j')
        before = deepcopy(self.current()['case'])
        self.click('[data-action="work_detail"][data-detail-tab="output"]')
        self.assertIsNotNone(self.read('[data-call-output]'))
        for code, expected, label in (('state_read_failed', 'failed', '조회 실패'),
                                      ('chat_forbidden', 'restricted', '접근 제한')):
            with self.subTest(error=code):
                async def unavailable(*args, **kwargs):
                    return {'ok': False, 'error': {'code': code, 'message': '합성 조회 경계'}}
                with patch.object(self.server.workflow, 'get_state', unavailable):
                    self.browser.evaluate("window.dispatchEvent(new CustomEvent('ees-work-changed',{detail:{chat_id:'existing-chat'}}))")
                    self.wait("document.querySelector('#ees-work-dialog [data-record-state]')?.dataset.recordState === " + json.dumps(expected))
                    self.assertIn(label, self.text('#ees-work-dialog'))
                    self.assertIsNone(self.read('[data-call-output]'))
                    self.assertIsNone(self.read('.ew-detail-outcome'))
                    self.key('Escape', 27)
                    if not self.read('.ew-panel-menu', 'open'):
                        self.click('.ew-panel-menu > summary')
                    self.click('#ees-work-run-view [data-action="history_view"]')
                    if not self.read('.ew-panel-menu', 'open'):
                        self.click('.ew-panel-menu > summary')
                    self.click('#ees-work-run-view [data-action="current_view"]')
                    self.assertIsNone(self.read('[data-action="work_detail"][data-detail-tab="output"]'),
                                      'Changing display tabs cannot restore the failed case evidence')
                    self.assertIsNotNone(self.read('[data-action="execution_refresh"]'))
                    self.assertIsNone(self.read('[data-call-output]'))
                    self.screenshot('ees-right-record-' + expected)
                self.click('[data-action="execution_refresh"]')
                self.wait("!!document.querySelector('[data-action=work_detail][data-detail-tab=output]')")
                self.click('[data-action="work_detail"][data-detail-tab="output"]')
                self.wait("!!document.querySelector('#ees-work-dialog [data-call-output]')")
        self.assertEqual(self.current()['case']['jobs'], before['jobs'])

    def test_panel_and_ai_tool_run_same_persisted_case_with_retry_history(self):
        def assert_record_visible(selector, record):
            rendered = self.text(selector)
            self.assertIn("모의 점검", rendered)
            self.assertIn(record["at"], rendered)
            for check in record["checks"]:
                for field in ("name", "detail"):
                    self.assertIn(check[field], rendered)

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
        self.wait("document.querySelector('#ees-work-content .ew-work-current-title')?.innerText === '모의 점검을 통과했습니다. 실제 업무 완료는 확인하지 않았습니다.'")
        self.assertNotIn("완료 기준을 충족했습니다.", self.text('#ees-work-content .ew-work-current-title'))
        evidence = '#ees-work-content [data-work-section="target"] [data-action="work_detail"]'
        self.click(evidence)
        self.assertTrue(self.read('#ees-work-dialog', "open"))
        self.click('#ees-work-dialog [data-action="detail_tab"][data-detail-tab="input"]')
        self.assertEqual(self.text('[data-call-input]'), "fixture-db-target")
        self.click('#ees-work-dialog [data-action="detail_tab"][data-detail-tab="history"]')
        assert_record_visible('#ees-work-dialog', db_job["history"][-1])
        self.click('#ees-work-dialog [data-dialog-close]')
        self.run_job("ap-j", "failed")
        failed_job = self.current()["case"]["jobs"]["ap-j"]
        self.assertEqual([x["status"] for x in failed_job["checks"]],
                         ["passed", "passed", "failed", "skipped"])
        self.run_job("ap-j")
        retried_job = self.current()["case"]["jobs"]["ap-j"]
        self.assertEqual(len(retried_job["history"]), 2)
        self.assertEqual(retried_job["history"][0], failed_job["history"][-1])
        self.assertEqual(retried_job["history"][-1]["status"], "passed")
        previous = '#ees-work-content [data-action="work_detail"][data-detail-tab="history"]'
        self.click(previous)
        previous = '#ees-work-dialog'
        self.assertTrue(self.read(previous, "open"))
        self.click(previous + ' [data-action="detail_attempt"][data-attempt-index="0"]')
        self.assertIn("업무 실패", self.text(previous + ' .ew-detail-outcome'))
        assert_record_visible(previous, failed_job["history"][-1])
        self.click('#ees-work-dialog [data-dialog-close]')
        self.run_job("interface-j")
        case_id = self.current()["case"]["id"]
        self.navigate("/c/other-chat")
        self.wait("!!document.querySelector('#chat-input') && !document.querySelector('#ees-work-context')")
        self.assertIsNone(self.current("other-chat")["case"])
        self.navigate("/c/existing-chat")
        self.open_work_panel()
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.assertEqual(self.current()["case"]["id"], case_id)
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["status"], "passed")

    def test_input_save_double_click_and_held_enter_never_run_or_send_chat(self):
        self.seed_case("existing-chat", ready=True)
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        # A context strip can mount before the native draft and scope controls
        # finish hydration. Begin the gesture at the existing ready boundary.
        self.wait_scope_ready("site")
        self.choose("db-j")
        self.fill("#chat-input", "업무 입력 중 전송되면 안 되는 대화")
        before = self.current()["case"]["jobs"]["db-j"]
        for gesture, value in (("double_click", "두 번 클릭한 입력"), ("held_enter", "Enter로 반영한 입력"),
                               ("held_space", "Space로 반영한 입력")):
            with self.subTest(gesture=gesture):
                self.fill('#ees-work-inputs input[name="db"]', value)
                self.assertTrue(self.read("#ees-work-run", "disabled"))
                if gesture == "double_click":
                    point = self.browser.evaluate("""(()=>{
                        const e=document.querySelector('#ees-work-inputs-save');
                        e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();
                        return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
                    for count in (1, 2):
                        for event_type in ("mousePressed", "mouseReleased"):
                            self.browser.call("Input.dispatchMouseEvent", {
                                "type": event_type, **point, "button": "left",
                                "buttons": 1 if event_type == "mousePressed" else 0, "clickCount": count})
                elif gesture == "held_enter":
                    self.click('#ees-work-inputs input[name="db"]')
                    key = {"type": "keyDown", "key": "Enter", "code": "Enter",
                           "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                           "text": "\r", "unmodifiedText": "\r"}
                    self.browser.call("Input.dispatchKeyEvent", key)
                    self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
                    for _ in range(3):
                        self.browser.call("Input.dispatchKeyEvent", {**key, "autoRepeat": True})
                    self.browser.call("Input.dispatchKeyEvent", {**key, "type": "keyUp"})
                else:
                    # Space activates a focused button on keyup, not keydown.
                    # Repeats before release must neither submit nor reach chat.
                    self.browser.evaluate("document.querySelector('#ees-work-inputs-save').focus()")
                    key = {"type": "keyDown", "key": " ", "code": "Space",
                           "windowsVirtualKeyCode": 32, "nativeVirtualKeyCode": 32,
                           "text": " ", "unmodifiedText": " "}
                    self.browser.call("Input.dispatchKeyEvent", key)
                    for _ in range(3):
                        self.browser.call("Input.dispatchKeyEvent", {**key, "autoRepeat": True})
                    self.assertNotEqual(self.current()["case"]["jobs"]["db-j"]["inputs"]["db"], value)
                    self.browser.call("Input.dispatchKeyEvent", {**key, "type": "keyUp"})
                    self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
                    for _ in range(3):
                        self.browser.call("Input.dispatchKeyEvent", {**key, "autoRepeat": True})
                    self.browser.call("Input.dispatchKeyEvent", {**key, "type": "keyUp"})
                self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
                saved = self.current()["case"]["jobs"]["db-j"]
                self.assertEqual(saved["inputs"]["db"], value)
                self.assertEqual(saved["attempt"], before["attempt"])
                self.assertEqual(saved["history"], before["history"])
                self.assertEqual(self.server.completions, [])
                self.assertEqual(self.text("#chat-input"), "업무 입력 중 전송되면 안 되는 대화")
        self.screenshot("ees-step-input-saved-before-execution")
        self.click("#ees-work-run")
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        after = self.current()["case"]["jobs"]["db-j"]
        self.assertEqual(after["attempt"], before["attempt"] + 1)
        self.assertEqual(after["status"], "passed")
        self.assertEqual(self.current()["case"]["selected_id"], "db-j")
        self.screenshot("ees-step-job-completed-after-explicit-run")
        # The right panel records work facts; the approved follow-up removes
        # recommendation buttons. Continue from the preserved left navigator.
        self.assertIsNone(self.read('#ees-work-content [data-work-stage="next"]'))
        next_job = '#ees-work-tree [data-action="select"][data-node-id="ap-j"]'
        self.assertIsNotNone(self.read(next_job))
        self.click(next_job)
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === 'AP 연결 확인'")
        self.assertEqual(self.current()["case"]["jobs"]["ap-j"]["attempt"], 0)
        self.assertEqual(self.current()["case"]["jobs"]["db-j"], after)

    def test_management_scope_run_excludes_human_retry_and_marks_unconnected_unperformed(self):
        before = self.seed_large_case()
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        for node_id in ("bulk-p", "bulk-t"):
            with self.subTest(scope=node_id):
                self.choose(node_id)
                self.assertEqual(self.read("#ees-work-run", "classList.contains('ew-primary')"), True)
                self.assertEqual(self.text('#ees-work-run'), '범위 모의 점검 실행')
                self.assertIsNone(self.read('.ew-work-next'))
        self.assertIn("현재 점검 가능 1개", self.text('[data-work-ready="1"]'))
        self.click("#ees-work-run")
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        after = self.current()["case"]
        changed = [node_id for node_id in before["jobs"] if before["jobs"][node_id] != after["jobs"][node_id]]
        self.assertEqual(changed, ["bulk-005-j", "bulk-052-j"])
        self.assertEqual(after["jobs"]["bulk-052-j"]["status"], "passed")
        blocked = after["jobs"]["bulk-005-j"]
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["history"][:-1], before["jobs"]["bulk-005-j"]["history"])
        self.assertEqual(blocked["history"][-1]["kind"], "execution_blocked")
        self.assertFalse(blocked["history"][-1]["simulation"])
        self.assertTrue(all(check["status"] in {"blocked", "skipped"} for check in blocked["checks"]))
        self.assertEqual(after["progress"], {"done": 3, "total": 104})
        # Numeric/unit spans can wrap on a narrow panel; the saved quantities
        # and their visible labels must remain exact independently of wrapping.
        self.assertEqual(''.join(self.text('[data-work-metric="jobs"] strong').split()), "3/104")
        self.assertEqual(''.join(self.text('[data-work-metric="attention"] strong').split()), "2개작업")
        def scroll_panel():
            bounds = self.read('#ees-work-content', 'getBoundingClientRect().toJSON()')
            self.browser.call('Input.dispatchMouseEvent', {"type": "mouseWheel",
                "x": bounds["x"] + bounds["width"] / 2, "y": bounds["y"] + bounds["height"] / 2,
                "deltaX": 0, "deltaY": 350})
            self.wait("document.querySelector('#ees-work-content').scrollTop > 0")
        scroll_panel()
        self.choose("bulk-002-j")
        self.assertEqual(self.read('#ees-work-content', 'scrollTop'), 0,
                         'Choosing another job must show its title and current action from the top')
        self.assertIn("실행 이력 1건", self.text("#ees-work-content"))
        self.assertIn("완료 기준", self.text("#ees-work-content"))
        self.screenshot("ees-step-job-failed-retry")
        scroll_panel()
        same_job_scroll = self.read('#ees-work-content', 'scrollTop')
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.assertAlmostEqual(self.read('#ees-work-content', 'scrollTop'), same_job_scroll, delta=1,
                               msg='Refreshing the same job must not jump away from the evidence being read')
        self.choose("bulk-005-j")
        self.assertEqual(self.read('#ees-work-content', 'scrollTop'), 0)
        self.assertIn("실행 연결", self.text("#ees-work-content"))
        self.assertTrue(self.read("#ees-work-run", "disabled"))

    def test_missing_skill_preview_uses_same_permission_state_in_steps_and_management(self):
        assets = {"tools": [], "skills": [], "available": True,
                  "skill_bodies": {"private-required": "권한이 있을 때만 볼 수 있는 합성 지침"}}
        self.server.workflow.asset_lookup = lambda _: deepcopy(assets)
        state = self.current()
        definition = deepcopy(state["catalog"])
        definition["skills"]["private-required"] = {
            "id": "private-required", "name": "권한 확인용 지침", "type": "skill",
            "source": "open_webui", "reference": "private-required", "body": ""}
        nodes = definition["nodes"]
        nodes["private-p"] = dict(deepcopy(nodes["setup-p"]), id="private-p", name="권한 확인 절차",
                                  children=["private-t"], skills=["private-required"], deps=[])
        nodes["private-t"] = dict(deepcopy(nodes["prep-t"]), id="private-t", name="권한 확인 단계",
                                  parent="private-p", children=["private-j"], skills=[], deps=[])
        nodes["private-j"] = dict(deepcopy(nodes["db-j"]), id="private-j", name="권한이 필요한 점검",
                                  parent="private-t", skills=[], deps=[])
        definition["roots"]["setup"].append("private-p")
        self.publish_runtime_fixture(definition)
        assets["skill_bodies"].clear()
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#ees-work-entry [data-node-id=private-p]')"
                  + " && document.querySelector('#ees-work-entry .ew-scope-pickers')?.getAttribute('aria-busy') === 'false'")
        post_count = self.server.requests.count(("POST", "/api/ees-work/action"))
        for scope in ("private-p", "private-t"):
            with self.subTest(scope=scope):
                self.choose(scope)
                self.assertEqual(self.text('[data-work-metric="attention"] strong'), "1개 작업")
                self.assertIn("현재 점검 가능 0개", self.text('[data-work-ready="0"]'))
                self.assertIsNone(self.read("#ees-work-run"))
                self.assertIsNone(self.read('.ew-work-next'))
        self.choose("private-j")
        self.assertIn("권한 확인", self.text('.ew-step-job[data-node-id="private-j"]'))
        self.assertIn("필수 스킬", self.text("#ees-work-content"))
        self.assertTrue(self.read("#ees-work-run", "disabled"))
        self.assertNotIn("권한이 있을 때만 볼 수 있는 합성 지침", self.text("body"))
        self.assertEqual(self.current()["cases"], [])
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/action")), post_count)
        self.screenshot("ees-step-preview-permission-required")

    def test_borderless_step_styles_focus_and_long_name_in_native_light_dark_narrow(self):
        self.seed_large_case()
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.choose("bulk-052-j")
        self.fill('#ees-work-inputs input[name="db"]', "입력 반영을 확인할 대상")
        self.fill('#chat-input', "선택 중에도 보존할 미전송 대화")
        self.browser.evaluate("""(async()=>{
            await Promise.all([document.fonts.load('400 14px "EES Inter"','EES 0123'),
                document.fonts.load('400 14px "EES Noto Sans KR"','공장 업무')]);
            await document.fonts.ready;})()""")
        for width, height in ((1920, 1080), (900, 900)):
            for theme in ("light", "dark"):
                with self.subTest(width=width, theme=theme):
                    self.browser.call("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                    self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                    self.browser.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
                    selection_styles = {}
                    self.choose("bulk-t")
                    self.assertTrue(self.browser.evaluate("""(()=>{
                        const summary=document.querySelector('.ew-workflow-summary'),buttons=summary.querySelectorAll('button');
                        return buttons.length===1&&buttons[0].contains(summary.querySelector('.ew-step-meta'))
                            &&buttons[0].textContent.includes('2 / 104 작업 완료');})()"""))
                    # Click the count, then activate the same summary with the
                    # keyboard. Both must select P without creating/running work.
                    before = self.current()["case"]
                    self.click('.ew-workflow-summary .ew-step-meta')
                    self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 작업 검증'")
                    self.hover()
                    selection_styles["p"] = self.visual_style('.ew-workflow-summary > button')
                    if theme == "light":
                        self.assertEqual(selection_styles["p"]["background"], "rgb(220, 235, 247)")
                        self.assertEqual(selection_styles["p"]["color"], "rgb(55, 101, 139)")
                    self.assertEqual(self.browser.evaluate(
                        "document.querySelectorAll('#ees-work-entry button[aria-current=step]').length"), 1)
                    self.assertGreaterEqual(self.visual_style('.ew-workflow-summary .ew-step-meta')["contrast"], 4.5)
                    self.screenshot("ees-hierarchy-p-" + theme + "-" + str(width))
                    self.hover('.ew-workflow-summary > button')
                    self.assertEqual(self.visual_style('.ew-workflow-summary > button')["background"],
                                     selection_styles["p"]["background"])
                    self.hover('.ew-step-button')
                    self.assertNotEqual(self.visual_style('.ew-step-button')["backgroundRGB"],
                                        selection_styles["p"]["backgroundRGB"])
                    self.assertEqual(self.visual_style('.ew-workflow-summary > button')["background"],
                                     selection_styles["p"]["background"])
                    self.choose("bulk-t")
                    self.browser.evaluate("document.querySelector('.ew-workflow-summary > button').focus()")
                    # CDP needs the Enter character to produce the browser's
                    # native button activation, in addition to keydown/keyup.
                    self.key("Enter", 13, text="\r")
                    self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 작업 검증'")
                    self.assertEqual(self.current()["case"]["jobs"], before["jobs"])
                    self.choose("bulk-t")
                    self.browser.evaluate("document.querySelector('.ew-workflow-summary > button').focus()")
                    self.key(" ", 32)
                    self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '대량 작업 검증'")
                    self.assertEqual(self.text('#chat-input'), "선택 중에도 보존할 미전송 대화")
                    self.assertEqual(self.server.completions, [])
                    self.choose("bulk-t")
                    self.hover()
                    selection_styles["t"] = self.visual_style('.ew-step-button[aria-current=step]')
                    stage = self.visual_style('.ew-step[data-expanded=true]')
                    self.assertGreaterEqual(selection_styles["t"]["x"] - stage["x"], 8)
                    self.assertGreaterEqual(stage["right"] - selection_styles["t"]["right"], 8)
                    self.assertEqual(self.browser.evaluate(
                        "document.querySelectorAll('#ees-work-entry button[aria-current=step]').length"), 1)
                    self.assertGreaterEqual(self.visual_style('.ew-step-button[aria-current=step] strong')["contrast"], 4.5)
                    self.assertGreaterEqual(self.visual_style('.ew-step-button[aria-current=step] .ew-step-meta')["contrast"], 4.5)
                    self.assertGreaterEqual(self.visual_style('.ew-step-button[aria-current=step] .ew-work-state')["contrast"], 4.5)
                    self.assertNotEqual(selection_styles["t"]["background"], self.visual_style('.ew-step-jobs')["background"])
                    self.screenshot("ees-hierarchy-t-" + theme + "-" + str(width))
                    self.hover('.ew-step-button[aria-current=step]')
                    self.assertEqual(self.visual_style('.ew-step-button[aria-current=step]')["background"],
                                     selection_styles["t"]["background"])
                    self.hover('.ew-workflow-summary > button')
                    self.assertNotEqual(self.visual_style('.ew-workflow-summary > button')["backgroundRGB"],
                                        selection_styles["t"]["backgroundRGB"])
                    self.assertEqual(self.visual_style('.ew-step-button[aria-current=step]')["background"],
                                     selection_styles["t"]["background"])
                    self.choose("bulk-052-j")
                    self.hover()
                    measured = self.browser.evaluate("""(()=>{
                        const root=document.querySelector('#ees-work-panel'), css=getComputedStyle(root);
                        const color=value=>{const e=document.createElement('span');e.style.color=value;
                            root.append(e);const c=getComputedStyle(e).color;e.remove();return c};
                        const button=document.querySelector('#ees-work-inputs-save'), b=getComputedStyle(button);
                        const selected=document.querySelector('.ew-step-job[aria-current=step]'), s=getComputedStyle(selected);
                        const status=selected.querySelector('.ew-work-state');
                        const number=document.querySelector('.ew-step[data-expanded=true] .ew-step-number');
                        const target=document.querySelector('#ees-work-panel [data-work-section=target]');
                        const form=document.querySelector('#ees-work-inputs');
                        const boxes=['.ew-work-result','.ew-work-criterion'].map(selector=>{
                            const e=document.querySelector('#ees-work-panel '+selector);return e?getComputedStyle(e).borderTopWidth:null;});
                        return {blue:color(css.getPropertyValue('--ees-blue')), ewBlue:color(css.getPropertyValue('--ew-blue')),
                            paper:color(css.getPropertyValue('--ees-paper')),
                            primary:b.backgroundColor,border:b.borderTopWidth,
                            tint:color(css.getPropertyValue('--ees-tint')),selected:s.backgroundColor,
                            stateSize:parseFloat(getComputedStyle(status).fontSize),
                            state:status.textContent,buttonHeight:selected.getBoundingClientRect().height,
                            rowRight:selected.getBoundingClientRect().right,
                            activeNumber:getComputedStyle(number).backgroundColor,
                            targetBeforeInput:Boolean(target.compareDocumentPosition(form)&Node.DOCUMENT_POSITION_FOLLOWING),
                            actionWidth:button.getBoundingClientRect().width,actionHeight:button.getBoundingClientRect().height,
                            formWidth:form.getBoundingClientRect().width,
                            sidebarRight:document.querySelector('#ees-work-entry').getBoundingClientRect().right,
                            boxes,width:innerWidth,scroll:document.documentElement.scrollWidth};})()""")
                    self.assertEqual(measured["ewBlue"], measured["blue"])
                    if theme == "light":
                        self.assertEqual(measured["tint"], "rgb(238, 245, 250)")
                        self.assertEqual(measured["paper"], "rgb(255, 255, 255)")
                    self.assertEqual(measured["primary"], measured["blue"])
                    self.assertNotEqual(measured["activeNumber"], measured["blue"],
                                        "Expanded parent number must not compete with the selected job")
                    self.assertTrue(measured["targetBeforeInput"])
                    self.assertIsNone(self.read('.ew-work-next'))
                    self.assertGreaterEqual(measured["actionWidth"], 100)
                    self.assertLess(measured["actionWidth"], measured["formWidth"] / 2)
                    self.assertGreaterEqual(measured["actionHeight"], 40)
                    self.assertEqual(measured["border"], "0px")
                    self.assertEqual(measured["selected"], measured["tint"])
                    self.assertEqual(selection_styles["t"]["background"], measured["tint"])
                    self.assertNotEqual(selection_styles["p"]["background"], measured["tint"])
                    self.assertNotEqual(selection_styles["p"]["background"], measured["blue"])
                    self.assertNotEqual(selection_styles["p"]["background"], measured["paper"])
                    self.assertTrue(all(border == "0px" for border in measured["boxes"]))
                    self.assertGreaterEqual(measured["stateSize"], 13)
                    self.assertGreaterEqual(measured["buttonHeight"], 42)
                    self.assertLessEqual(measured["rowRight"], measured["sidebarRight"] + 1)
                    self.assertLessEqual(measured["scroll"], measured["width"] + 1)
                    selected_selector = '.ew-step-job[aria-current=step]'
                    selection_styles["j"] = self.visual_style(selected_selector)
                    selection_styles["jobName"] = self.visual_style(selected_selector + ' .ew-step-job-name')
                    selection_styles["status"] = self.visual_style(selected_selector + ' .ew-work-state')
                    selection_styles["parent"] = self.visual_style('.ew-step[data-expanded=true]')
                    selection_styles["parentHeader"] = self.visual_style('.ew-step[data-expanded=true] > .ew-step-button')
                    selection_styles["parentMeta"] = self.visual_style('.ew-step[data-expanded=true] .ew-step-meta')
                    self.assertLessEqual(selection_styles["jobName"]["right"], selection_styles["status"]["x"])
                    for key in ("jobName", "status"):
                        self.assertGreaterEqual(selection_styles[key]["y"], selection_styles["j"]["y"])
                        self.assertLessEqual(selection_styles[key]["bottom"], selection_styles["j"]["bottom"])
                    self.assertGreater(selection_styles["j"]["height"], 42,
                                       "The long Korean job name must grow instead of being clipped")
                    selection_styles["dividers"] = self.browser.evaluate("""(()=>{
                        const widths=s=>[...document.querySelectorAll(s)].map(e=>parseFloat(getComputedStyle(e).borderTopWidth));
                        return {jobs:widths('.ew-step-jobs > li'),all:widths('.ew-step-all,.ew-step-all > button')};})()""")
                    self.assertEqual(selection_styles["dividers"], {"jobs": [0, 1, 1, 1, 1], "all": [0, 0]})
                    selection_styles["category"] = self.visual_style('.ew-category[aria-pressed=true]')
                    selection_styles["categories"] = self.visual_style('.ew-category-tabs')
                    self.assertEqual(selection_styles["jobName"]["color"], measured["blue"])
                    for key in ("parent", "parentHeader", "category", "categories"):
                        self.assertEqual(selection_styles[key]["background"], measured["paper"], (key, selection_styles[key]))
                    underline = self.browser.evaluate("""(()=>{
                        const e=document.querySelector('.ew-category[aria-pressed=true]'),s=getComputedStyle(e,'::after');
                        return {color:s.backgroundColor,width:parseFloat(s.width),height:parseFloat(s.height),
                            tabWidth:e.getBoundingClientRect().width};})()""")
                    self.assertEqual(underline["color"], measured["blue"])
                    self.assertGreaterEqual(underline["height"], 2)
                    self.assertLess(underline["width"], underline["tabWidth"])
                    selection_styles["underline"] = underline
                    for key in ("jobName", "status"):
                        self.assertGreaterEqual(selection_styles[key]["contrast"], 4.5, (key, selection_styles[key]))
                    self.assertGreaterEqual(selection_styles["parentMeta"]["contrast"], 4.5)
                    self.assertGreaterEqual(selection_styles["j"]["x"] - selection_styles["parent"]["x"], 8)
                    self.assertGreaterEqual(selection_styles["parent"]["right"] - selection_styles["j"]["right"], 8)
                    self.assertEqual(selection_styles["parentHeader"]["background"], measured["paper"])
                    self.assertEqual(self.browser.evaluate(
                        "document.querySelectorAll('#ees-work-entry button[aria-current=step]').length"), 1)
                    self.screenshot("ees-hierarchy-j-" + theme + "-" + str(width))
                    self.hover('.ew-step-button')
                    for key, selector in (("parentMetaHover", ".ew-step-button .ew-step-meta"),
                                          ("parentStatusHover", ".ew-step-button .ew-work-state")):
                        selection_styles[key] = self.visual_style(selector)
                        self.assertGreaterEqual(selection_styles[key]["contrast"], 4.5, (key, selection_styles[key]))
                    self.hover('.ew-step-job[data-node-id="bulk-003-j"]')
                    selection_styles["warningHover"] = self.visual_style('.ew-step-job[data-node-id="bulk-003-j"] .ew-work-state')
                    self.assertGreaterEqual(selection_styles["warningHover"]["contrast"], 4.5)
                    selection_styles["connectionWordRects"] = self.browser.evaluate("""(()=>{
                        const text=document.querySelector('.ew-step-job[data-node-id="bulk-005-j"] .ew-work-state').firstChild;
                        const start=text.textContent.indexOf('필요'),range=document.createRange();
                        range.setStart(text,start);range.setEnd(text,start+2);
                        return [...range.getClientRects()].map(r=>({x:r.x,y:r.y,width:r.width,height:r.height}));})()""")
                    self.assertEqual(len(selection_styles["connectionWordRects"]), 1,
                                     "A wrapped connection status must keep 필요 on one line")
                    other = '.ew-step-job:not([aria-current=step])'
                    self.hover(other)
                    selection_styles["otherHover"] = self.visual_style(other)
                    paper = selection_styles["parentHeader"]["backgroundRGB"]
                    distance = lambda rgb: sum((a - b) ** 2 for a, b in zip(rgb, paper))
                    self.assertLess(distance(selection_styles["otherHover"]["backgroundRGB"]),
                                    distance(selection_styles["j"]["backgroundRGB"]))
                    self.assertEqual(self.visual_style(selected_selector)["background"], measured["tint"])
                    self.screenshot("ees-hierarchy-other-hover-" + theme + "-" + str(width))
                    self.hover(selected_selector)
                    self.assertEqual(self.visual_style(selected_selector)["background"], measured["tint"])
                    self.hover()
                    self.browser.evaluate("document.querySelector('.ew-step-button').focus()")
                    self.key("Tab", 9)
                    selection_styles["otherFocus"] = self.visual_style('.ew-step-job:focus')
                    self.assertNotEqual(selection_styles["otherFocus"]["node"], "bulk-052-j")
                    self.assertTrue(selection_styles["otherFocus"]["focusVisible"])
                    self.assertGreaterEqual(selection_styles["otherFocus"]["outlineWidth"], 2)
                    bounds = self.read('#ees-work-entry', 'getBoundingClientRect().toJSON()')
                    ring = selection_styles["otherFocus"]["outlineWidth"] + selection_styles["otherFocus"]["outlineOffset"]
                    self.assertGreaterEqual(selection_styles["otherFocus"]["x"] - ring, bounds["left"])
                    self.assertLessEqual(selection_styles["otherFocus"]["right"] + ring, bounds["right"])
                    self.assertEqual(self.visual_style(selected_selector)["background"], measured["tint"])
                    self.screenshot("ees-hierarchy-other-focus-" + theme + "-" + str(width))
                    self.save_visual_measurements("ees-hierarchy-" + theme + "-" + str(width), selection_styles)
                    self.browser.evaluate("document.querySelector('.ew-step-job[aria-current=step]').focus()")
                    self.key("Tab", 9, modifiers=8)
                    self.key("Tab", 9)
                    focus = self.browser.evaluate("""(()=>{const e=document.activeElement,s=getComputedStyle(e);
                        return {job:e.dataset.nodeId,visible:e.matches(':focus-visible'),style:s.outlineStyle,
                            width:parseFloat(s.outlineWidth),color:s.outlineColor};})()""")
                    self.assertEqual(focus["job"], "bulk-052-j")
                    self.assertTrue(focus["visible"])
                    self.assertEqual(focus["style"], "solid")
                    self.assertGreaterEqual(focus["width"], 2)
                    self.assertEqual(focus["color"], measured["blue"])
                    self.screenshot("ees-step-native-" + theme + "-" + str(width))
        self.browser.call("Emulation.setDeviceMetricsOverride", {
            "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
        self.wait("(() => {const p=document.querySelector('#ees-work-panel');return p&&!p.classList.contains('ew-narrow')"
                  + "&&p.getBoundingClientRect().width===parseFloat(p.style.width)})()")
        self.browser.evaluate("document.querySelector('#ees-work-resizer').focus()")
        before = self.read('#ees-work-panel', 'getBoundingClientRect().width')
        self.key("ArrowLeft", 37)
        after = self.read('#ees-work-panel', 'getBoundingClientRect().width')
        self.assertGreater(after, before)
        self.key("ArrowRight", 39)
        self.assertAlmostEqual(self.read('#ees-work-panel', 'getBoundingClientRect().width'), before, delta=1)
        self.assertEqual(self.read('#ees-work-inputs input[name="db"]', 'value'), "입력 반영을 확인할 대상")

    def test_selected_business_statuses_remain_readable_in_both_themes(self):
        self.seed_large_case()
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        measurements = {}

        def check_status(node_id, status, chat_id="existing-chat"):
            self.choose(node_id, chat_id=chat_id)
            selector = '.ew-step-job[aria-current=step] .ew-work-state'
            self.assertEqual(self.read(selector, "dataset.status"), status)
            for theme in ("light", "dark"):
                self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                self.hover()
                style = self.visual_style(selector)
                self.assertGreaterEqual(style["fontSize"], 13)
                self.assertGreaterEqual(style["contrast"], 4.5, (status, theme, style))
                self.assertNotEqual(style["background"], self.visual_style('.ew-step-job[aria-current=step]')["background"])
                measurements[status + "-" + theme] = style
                self.screenshot("ees-hierarchy-status-" + status + "-" + theme)

        check_status("bulk-000-j", "passed")
        check_status("bulk-002-j", "failed")
        check_status("bulk-003-j", "review")
        case = self.seed_case("status-chat")
        self.navigate("/c/status-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        check_status("db-j", "waiting", "status-chat")
        case = self.current("status-chat")["case"]
        changed = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            "action": "update_inputs", "chat_id": "status-chat", "case_id": case["id"],
            "expected_revision": case["revision"], "node_id": "db-j", "payload": {"inputs": {"db": ""}}}))
        self.assertTrue(changed["ok"], changed)
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.wait("document.querySelector('.ew-step-job[aria-current=step] .ew-work-state')?.dataset.status === 'input_required'")
        check_status("db-j", "input_required", "status-chat")
        self.save_visual_measurements("ees-hierarchy-statuses", measurements)

    def test_sidebar_internal_job_dividers_follow_visible_rows_without_outer_box(self):
        self.seed_case("existing-chat")
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        measurements = {}
        for node_id, count in (("prep-t", 1), ("install-t", 3)):
            self.choose(node_id)
            for theme in ("light", "dark"):
                self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == "dark").lower() + ")")
                self.hover()
                rows = self.browser.evaluate("""(()=>{
                    const step=document.querySelector('.ew-step[data-expanded=true]'),
                        list=step.querySelector('.ew-step-jobs'),bounds=list.getBoundingClientRect();
                    const borders=e=>{const s=getComputedStyle(e);return ['Top','Right','Bottom','Left']
                        .map(side=>parseFloat(s['border'+side+'Width']));};
                    return {listBorders:borders(list),stepBorders:borders(step),
                        collapsed:[...document.querySelectorAll('.ew-step[data-expanded=false]')]
                            .map(e=>({jobs:e.querySelectorAll('.ew-step-job').length,borders:borders(e)})),
                        rows:[...list.children].map(e=>({borders:borders(e),color:getComputedStyle(e).borderTopColor,
                            x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right,
                            listX:bounds.x,listRight:bounds.right,buttonBorders:borders(e.querySelector('button')),
                            height:e.querySelector('button').getBoundingClientRect().height}))};})()""")
                self.assertEqual(len(rows["rows"]), count)
                self.assertEqual(rows["listBorders"], [0, 0, 0, 0])
                self.assertEqual(rows["stepBorders"], [0, 0, 0, 0])
                self.assertTrue(rows["collapsed"])
                for collapsed in rows["collapsed"]:
                    self.assertEqual(collapsed, {"jobs": 0, "borders": [0, 0, 0, 0]})
                for index, row in enumerate(rows["rows"]):
                    self.assertEqual(row["borders"], [int(index > 0), 0, 0, 0])
                    self.assertEqual(row["buttonBorders"], [0, 0, 0, 0])
                    self.assertGreaterEqual(row["height"], 42)
                    self.assertGreaterEqual(row["x"], row["listX"])
                    self.assertLessEqual(row["right"], row["listRight"])
                    if theme == "light" and index:
                        self.assertEqual(row["color"], "rgb(228, 233, 239)")
                measurements[node_id + "-" + theme] = rows
                self.screenshot("sidebar-dividers-" + node_id + "-" + theme)
        self.save_visual_measurements("sidebar-internal-dividers", measurements)

    def test_cancelled_human_confirmation_keeps_saved_state(self):
        self.create_case()
        self.choose('scope-j')
        before = self.current()['case']
        self.click('#ees-work-run', confirm=False)
        self.assertEqual(self.current()['case'], before)
        self.assertIn('담당자의 확인이 필요합니다.', self.text('#ees-work-content'))
        self.run_job('scope-j')
        self.assertIn('담당자 확인이 완료됐습니다.', self.text('#ees-work-content'))

    def test_workspace_ai_authoring_keeps_changes_local_and_targeted(self):
        self.create_case()
        before = self.current()
        before_authoring = self.authoring_current()["process"]["workflow"]
        self.open_authoring()
        self.wait("!!document.querySelector('#ees-work-designer')")
        self.assertIsNotNone(self.read('#ees-work-authoring'))
        self.assertIn('AI에게 물어보기', self.text('#ees-work-authoring'))
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        writes = self.server.requests.count(('POST', '/api/ees-work/authoring/action'))
        self.fill('#ees-work-authoring-input', '이 업무를 설명해 줘')
        self.click('#ees-work-authoring-form button[type=submit]')
        self.wait("document.querySelector('#ees-work-authoring')?.innerText.includes('현재 업무의 목적과 완료 조건')")
        self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), before_authoring['nodes']['db-j'].get('instructions', ''))
        replacement = '1. 승인된 점검 대상을 확인합니다.\n2. 점검 결과를 검토합니다.'
        self.server.authoring_answer = json.dumps({'answer': '확인 순서를 나눴습니다.', 'instructions': replacement})
        self.fill('#ees-work-authoring-input', '수행 안내만 쉬운 두 단계로 바꿔 줘')
        self.click('#ees-work-authoring [data-action=ai_edit]')
        self.wait("document.querySelector('#ees-work-node-form [name=instructions]')?.value === " + json.dumps(replacement))
        self.assertIn('저장하지 않은 변경', self.text('.ew-designer-status'))
        self.click('.ew-authoring-comparison > summary')
        self.assertIn('수정 전', self.text('.ew-authoring-comparison'))
        self.assertIn(replacement, self.text('.ew-authoring-comparison'))
        self.assertEqual(self.server.requests.count(('POST', '/api/ees-work/authoring/action')), writes)
        self.assertEqual(self.authoring_current()['process']['workflow'], before_authoring)
        request = self.server.authoring_requests[-1]
        self.assertEqual(request['model'], 'fixture-model')
        self.assertEqual(request['tools'], [])
        self.assertEqual(request['tool_ids'], [])
        self.assertNotIn('chat_id', request)
        self.assertNotIn('parent_id', request)
        self.assertIn('DB 연결 확인', request['messages'][0]['content'])
        self.assertEqual(set(self.server.chats), {'existing-chat', 'other-chat'})
        self.fill('#ees-work-authoring-input', '아직 보내지 않은 질문')
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=ap-j]')
        self.assertNotIn('확인 순서를 나눴습니다.', self.text('#ees-work-authoring'))
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.assertEqual(self.read('#ees-work-authoring-input', 'value'), '아직 보내지 않은 질문')
        self.assertIn('확인 순서를 나눴습니다.', self.text('#ees-work-authoring'))
        self.click('#ees-work-authoring [data-action=ai_undo]')
        self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), before_authoring['nodes']['db-j'].get('instructions', ''))
        self.server.authoring_sse = True  # A model preset may force streaming.
        self.fill('#ees-work-authoring-input', '다시 안내를 수정해 줘')
        self.click('#ees-work-authoring [data-action=ai_edit]')
        self.wait("document.querySelector('#ees-work-node-form [name=instructions]')?.value === " + json.dumps(replacement))
        self.click('#ees-work-node-form .ew-designer-advanced > summary')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn('기존 스킬', self.text('#ees-work-dialog'))
        self.click('#ees-work-dialog [data-dialog-close]')
        self.assertFalse(self.read('.ew-designer-advanced', 'open'))
        self.click('#ees-work-designer [data-action=save_draft]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('초안 r1')")
        saved = self.current()
        expected = deepcopy(before_authoring)
        expected['nodes']['db-j']['instructions'] = replacement
        self.assertEqual(self.authoring_current()['process']['workflow'], expected)
        self.assertEqual(saved['case']['definition'], before['case']['definition'])
        self.assertEqual(saved['catalog'], before['catalog'])
        self.click('#ees-work-designer [data-action=validate_draft]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 전 확인 완료')")
        self.click('#ees-work-designer [data-action=publish]', confirm=False)
        self.assertEqual(self.current()['catalog']['version'], before['catalog']['version'])
        self.click('#ees-work-designer [data-action=publish]', confirm=True)
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 v2')")
        self.assertEqual(self.current()['catalog']['nodes']['db-j']['instructions'], replacement)
        self.assertEqual(self.current()['case']['definition'], before['case']['definition'])
        self.assertEqual(self.current()['case']['jobs'], before['case']['jobs'])
        self.screenshot('ees-workspace-ai-published')

    def test_workspace_ai_delayed_reply_does_not_overwrite_typing_or_another_target(self):
        self.open_authoring()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.wait("document.querySelector('#ees-work-designer [data-action=edit_node][aria-current=step]')?.dataset.nodeId === 'db-j'")
        self.server.authoring_answer = json.dumps({'answer': 'AI 응답', 'instructions': '늦게 도착한 안내'})
        for change in ('typing', 'selection'):
            with self.subTest(change=change):
                self.server.authoring_started.clear()
                self.server.authoring_hold.clear()
                self.fill('#ees-work-authoring-input', '안내를 수정해 줘')
                self.click('#ees-work-authoring [data-action=ai_edit]')
                self.assertTrue(self.server.authoring_started.wait(timeout=3))
                self.assertIn('DB 연결 확인', self.server.authoring_requests[-1]['messages'][0]['content'])
                if change == 'typing':
                    self.fill('#ees-work-node-form [name=instructions]', '응답 중 직접 작성한 안내')
                else:
                    self.click('#ees-work-designer [data-action=edit_node][data-node-id=ap-j]')
                    self.wait("document.querySelector('#ees-work-designer [data-action=edit_node][aria-current=step]')?.dataset.nodeId === 'ap-j'")
                    self.assertNotIn('AI 응답', self.text('#ees-work-authoring'))
                    # Return before the reply: matching the final node ID alone
                    # must not treat a changed selection as an unchanged request.
                    self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
                self.server.authoring_hold.set()
                self.wait("!document.querySelector('#ees-work-authoring [data-action=ai_cancel]')")
                self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), '응답 중 직접 작성한 안내')
                self.assertIn('적용하지 않았습니다', self.text('#ees-work-authoring'))

    def test_workspace_ai_rejects_unexpected_edits_and_preserves_request_on_failure(self):
        self.open_authoring()
        self.wait("!!document.querySelector('#ees-work-designer')")
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        original = self.read('#ees-work-node-form [name=instructions]', 'value')
        for answer, status in [('잘못된 JSON', 200),
                               (json.dumps({'answer': '완료', 'instructions': '바꾸면 안 됨', 'tools': []}), 200),
                               ('서버 오류', 503)]:
            with self.subTest(status=status, answer=answer):
                self.server.authoring_answer, self.server.authoring_status = answer, status
                self.fill('#ees-work-authoring-input', '안내만 바꿔 줘')
                self.click('#ees-work-authoring [data-action=ai_edit]')
                self.wait("!!document.querySelector('#ees-work-authoring [role=alert]') && !document.querySelector('#ees-work-authoring [data-action=ai_cancel]')")
                self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), original)
                self.assertEqual(self.read('#ees-work-authoring-input', 'value'), '안내만 바꿔 줘')
        self.assertEqual(self.server.requests.count(('POST', '/api/ees-work/authoring/action')), 0)

    def test_work_evidence_dialog_preserves_current_selection(self):
        self.create_case()
        self.run_job('scope-j')
        before = self.current()['case']
        self.click('#ees-work-content [data-work-section=target] [data-action=work_detail]')
        self.assertTrue(self.read('#ees-work-dialog', 'open'))
        self.assertIn('담당자의 명시적 확인 기록', self.text('#ees-work-dialog'))
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertIsNone(self.read('#ees-work-dialog'))
        self.assertEqual(self.current()['case'], before)
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('#ees-work-content [data-action=work_detail][data-detail-tab=output]')"))
        # J exposes its own attempt history; the unchanged case-wide record
        # dialog belongs to the P/T management view in the A layout.
        self.choose('setup-p')
        parent = deepcopy(self.current()['case'])
        self.click('#ees-work-content [data-action=work_records]')
        self.assertIn('담당자 확인', self.text('#ees-work-dialog'))
        self.assertNotIn('기존 대화 기록', self.text('#ees-work-dialog'))
        self.screenshot('ees-work-evidence-dialog')
        self.click('#ees-work-dialog [data-dialog-close]')
        self.assertEqual(self.current()['case'], parent)
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('[data-action=work_records]')"))
        self.assertIsNone(self.read('#ees-work-content [data-action=work_summary]'))
        self.choose('setup-p')
        self.assertEqual(self.text('#ees-work-panel .ew-title'), '신규 공장 횡전개')
        self.assertEqual(self.current()['case']['jobs'], before['jobs'])

    def test_workspace_ai_cancel_and_account_change_preserve_saved_assets(self):
        before = self.current()
        before_authoring = self.authoring_current()["process"]["workflow"]
        self.open_authoring()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.server.authoring_answer = json.dumps({'answer': '늦은 응답', 'instructions': '적용하면 안 되는 안내'})
        for changed_input in ('', '중단하기 전에 새로 작성한 질문'):
            with self.subTest(changed_input=changed_input):
                self.server.authoring_started.clear()
                self.server.authoring_hold.clear()
                self.fill('#ees-work-authoring-input', '중단할 작성 요청')
                self.click('#ees-work-authoring [data-action=ai_edit]')
                self.assertTrue(self.server.authoring_started.wait(timeout=3))
                if changed_input:
                    self.fill('#ees-work-authoring-input', changed_input)
                self.click('#ees-work-authoring [data-action=ai_cancel]')
                self.wait("!document.querySelector('#ees-work-authoring [data-action=ai_cancel]')")
                self.assertEqual(self.read('#ees-work-authoring-input', 'value'), changed_input or '중단할 작성 요청')
                self.server.authoring_hold.set()
                self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), '')
        self.server.authoring_started.clear()
        self.server.authoring_hold.clear()
        self.click('#ees-work-authoring [data-action=ai_edit]')
        self.assertTrue(self.server.authoring_started.wait(timeout=3))
        self.browser.evaluate("localStorage.setItem('token','fixture-second-session');window.dispatchEvent(new Event('storage'))")
        self.wait("!document.querySelector('#ees-work-authoring [data-action=ai_cancel]')")
        self.select_authoring_process()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model' && document.querySelector('#ees-work-authoring-input')?.value === ''")
        self.server.authoring_hold.set()
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        self.assertNotIn('중단할 작성 요청', self.text('#ees-work-authoring'))
        self.assertNotIn('늦은 응답', self.text('#ees-work-authoring'))
        self.assertEqual(self.authoring_current()['process']['workflow'], before_authoring)
        self.assertEqual(self.current()['catalog'], before['catalog'])
        self.assertEqual(self.server.requests.count(('POST', '/api/ees-work/authoring/action')), 0)

    def test_revision_conflict_dialog_keeps_unsaved_input_and_new_server_result(self):
        self.create_case()
        self.choose('db-j')
        before = self.current()['case']
        self.fill('#ees-work-inputs input[name=db]', '직접 작성 중인 대상')
        remote = asyncio.run(self.server.workflow.handle_action(self.server.user, {
            'action': 'update_inputs', 'chat_id': 'existing-chat', 'case_id': before['id'],
            'node_id': 'db-j', 'expected_revision': before['revision'],
            'payload': {'inputs': {'db': '먼저 저장된 다른 대상'}}}))
        self.assertTrue(remote['ok'], remote)
        self.click('#ees-work-inputs-save')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn('먼저 변경되었습니다', self.text('#ees-work-dialog'))
        self.assertEqual(self.read('#ees-work-inputs input[name=db]', 'value'), '직접 작성 중인 대상')
        self.assertEqual(self.current()['case']['jobs'], remote['case']['jobs'])
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertEqual(self.read('#ees-work-inputs input[name=db]', 'value'), '직접 작성 중인 대상')
        self.assertEqual(self.current()['case']['jobs'], remote['case']['jobs'])

    def test_workspace_authoring_and_dialog_layout_and_keyboard(self):
        self.open_authoring()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.click('#ees-work-designer [data-action=edit_node][data-node-id=db-j]')
        long_name = '해외 생산설비 인터페이스와 데이터베이스 연결 상태 및 현장 적용 대상과 담당자의 완료 기준을 함께 확인하는 업무'
        long_instructions = '신규 담당자도 따라 할 수 있도록 승인된 대상과 점검 순서, 실패 시 확인할 내용을 차례대로 기록합니다.\n' * 12
        self.fill('#ees-work-node-form [name="name"]', long_name)
        self.fill('#ees-work-node-form [name="instructions"]', long_instructions)
        self.click('#ees-work-node-form > button[type="submit"]')
        self.wait("document.querySelector('#ees-work-node-form h2')?.textContent === " + json.dumps(long_name))
        for width, height in ((1920, 1080), (900, 900), (600, 900)):
            for theme in ('light', 'dark'):
                with self.subTest(width=width, theme=theme):
                    self.browser.call('Emulation.setDeviceMetricsOverride', {
                        'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                    self.browser.evaluate("document.documentElement.classList.toggle('dark'," + str(theme == 'dark').lower() + ")")
                    self.browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                    # The dedicated view must retain Native's responsive
                    # sidebar width constraint even though the chat is hidden.
                    self.assertEqual(self.browser.evaluate("getComputedStyle(document.querySelector('#ees-work-designer')).maxWidth"),
                                     self.browser.evaluate("getComputedStyle(document.querySelector('#chat-container')).maxWidth"))
                    self.assertLessEqual(self.browser.evaluate('document.documentElement.scrollWidth'), width + 1)
                    self.assertLessEqual(self.browser.evaluate("document.querySelector('#ees-work-authoring').scrollWidth-document.querySelector('#ees-work-authoring').clientWidth"), 1)
                    styles = {key: self.visual_style(selector) for key, selector in {
                        "editorTitle": "#ees-work-node-form h2", "aiTitle": "#ees-work-authoring h2",
                        "input": "#ees-work-node-form input[name=name]", "aiInput": "#ees-work-authoring-input",
                        "apply": "#ees-work-node-form > button[type=submit]",
                    }.items()}
                    self.assertGreater(styles["editorTitle"]["fontSize"], styles["aiTitle"]["fontSize"])
                    self.assertGreaterEqual(styles["editorTitle"]["fontWeight"], styles["aiTitle"]["fontWeight"])
                    for key, style in styles.items():
                        self.assertGreaterEqual(style["contrast"], 4.5, (key, theme, width, style))
                    self.save_visual_measurements('ees-hierarchy-workspace-' + theme + '-' + str(width), styles)
                    self.browser.evaluate("document.querySelector('#ees-work-node-form').scrollIntoView({block:'start'})")
                    self.hover()
                    self.screenshot('ees-hierarchy-workspace-' + theme + '-' + str(width))
                    self.screenshot('ees-workspace-authoring-' + theme + '-' + str(width))
                    self.click('#ees-work-node-form .ew-designer-advanced > summary')
                    self.wait("document.querySelector('#ees-work-dialog')?.open")
                    self.key('Tab', 9)
                    self.assertTrue(self.browser.evaluate("!!document.activeElement?.closest('#ees-work-dialog')"))
                    self.assertLessEqual(self.browser.evaluate("document.querySelector('#ees-work-dialog').getBoundingClientRect().right"), width)
                    self.screenshot('ees-workspace-advanced-' + theme + '-' + str(width))
                    self.key('Escape', 27)
                    self.wait("!document.querySelector('#ees-work-dialog')")
                    self.assertTrue(self.browser.evaluate("document.activeElement?.matches('summary[data-work-advanced]')"))
                    self.assertFalse(self.read('.ew-designer-advanced', 'open'))

    def test_existing_workspace_editor_publication_and_user_denial(self):
        self.create_case()
        original_version = self.current()["case"]["version"]
        self.click('#sidebar a[href^="/workspace"]')
        self.wait("location.pathname === '/workspace/models'"
                  + " && document.querySelector('#ees-work-workspace-tab')?.getClientRects().length > 0")
        self.click("#ees-work-workspace-tab")
        self.select_authoring_process()
        self.assertEqual(self.browser.evaluate("location.pathname+location.search"), "/?ees=workflow")
        self.assertIsNotNone(self.read('#chat-container'))
        self.assertIn("수행 안내", self.text("#ees-work-designer"))
        self.assertIn("완료 조건", self.text("#ees-work-designer"))
        self.assertIn("고급 설정", self.text("#ees-work-designer"))
        self.assertNotIn("프로세스 편집", self.text("#ees-work-designer"))
        self.assertNotIn("태스크 추가", self.text("#ees-work-designer"))
        self.assertNotIn("잡 추가", self.text("#ees-work-designer"))
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="db-j"]')
        writes_before = self.server.requests.count(("POST", "/api/ees-work/authoring/action"))
        self.fill('#ees-work-node-form input[name="name"]', "DB 연결 확인 개정")
        # Typing changes only the local editor draft, without a form submit. The designer
        # may detach during ordinary SPA navigation, but must retain that draft
        # and its dirty state until the explicit server save.
        for route in ("models", "knowledge"):
            self.click('#sidebar a[href^="/workspace"]')
            self.wait("location.pathname === '/workspace/models' && !location.search")
            if route != 'models':
                self.click('nav a[href="/workspace/' + route + '"]')
            self.wait("location.pathname === " + json.dumps("/workspace/" + route)
                      + " && !location.search && !document.querySelector('#ees-work-designer')"
                      + " && !document.querySelector('.ees-work-native-hidden')")
            self.click("#ees-work-workspace-tab")
            self.wait("document.querySelector('#ees-work-node-form input[name=name]')?.value === 'DB 연결 확인 개정'"
                      + " && document.querySelector('.ew-designer-status')?.innerText.includes('저장하지 않은 변경')")
            self.assertEqual(self.browser.evaluate(
                "document.querySelectorAll('#ees-work-authoring-link').length"), 1)
        self.browser.evaluate("window.__eesNativeWorkV1.refresh()")
        self.assertEqual(self.read('#ees-work-node-form input[name="name"]', "value"), "DB 연결 확인 개정")
        self.assertIn("저장하지 않은 변경", self.text(".ew-designer-status"))
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/authoring/action")), writes_before)
        self.assertEqual(self.current()["catalog"]["nodes"]["db-j"]["name"], "DB 연결 확인")
        self.click('#ees-work-designer [data-action="save_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('초안 r1')")
        self.assertEqual(self.server.requests.count(("POST", "/api/ees-work/authoring/action")), writes_before + 1)
        self.assertNotIn("저장하지 않은 변경", self.text(".ew-designer-status"))
        self.assertEqual(self.authoring_current()['process']['workflow']["nodes"]["db-j"]["name"], "DB 연결 확인 개정")
        self.click('#ees-work-designer [data-action="validate_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 전 확인 완료')")
        self.click('#ees-work-designer [data-action="publish"]', confirm=True)
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes("
                  + json.dumps("게시 v" + str(original_version + 1)) + ")")
        self.assertEqual(self.current()["case"]["version"], original_version)
        self.assertEqual(self.current()["case"]["definition"]["nodes"]["db-j"]["name"], "DB 연결 확인")
        self.screenshot("ees-native-workspace")
        self.click('#sidebar a[href^="/workspace"]')
        self.wait("location.pathname === '/workspace/models' && !location.search"
                  + " && !document.querySelector('#ees-work-designer') && !document.querySelector('.ees-work-native-hidden')")
        self.server.user["role"] = "user"
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#ees-work-entry')")
        self.navigate("/?ees=workflow")
        self.wait("document.querySelector('#ees-work-designer')?.innerText.includes('권한')")
        self.assertIsNone(self.read("#ees-work-node-form"))
        self.assertIsNone(self.read("#ees-work-workspace-tab"))
        self.assertFalse(self.current()["can_manage"])

    def test_integrated_workspace_hierarchy_search_preserves_local_edits_and_old_case(self):
        original = self.seed_large_case()
        self.open_authoring('bulk-p')
        # Mounting precedes the asynchronous model-list render and font layout.
        # Wait for those existing ready boundaries before measuring a trusted
        # pointer target; do not retry a missed click or weaken child counts.
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.browser.evaluate("""(async()=>{
            await Promise.all([document.fonts.load('400 14px "EES Inter"','EES 0123'),
                document.fonts.load('400 14px "EES Noto Sans KR"','공장 업무')]);
            await document.fonts.ready;
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        })()""")
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="bulk-t"]')
        self.wait("document.querySelector('#ees-work-node-form h2')?.textContent === '대량 검증 단계'")
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-editor-child-list button').length"), 20)
        self.assertIn('전체 105개 · 검색 결과 105개', self.text('.ew-editor-children'))
        self.click('[data-action="child_page"][data-page="1"]')
        self.assertIn('21–40 표시', self.text('.ew-editor-children'))
        self.fill('#ees-work-child-search', '작업 104')
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-editor-child-list button').length"), 1)
        self.click('.ew-editor-child-list [data-node-id="bulk-104-j"]')
        self.fill('#ees-work-node-form [name="instructions"]', '게시 전까지 보존할 직접 작성 안내')
        self.fill('#ees-work-authoring-input', '아직 보내지 않은 작성 질문')
        self.click('#ees-work-node-form .ew-designer-advanced > summary')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertEqual(self.read('#ees-work-node-form [name="instructions"]', 'value'), '게시 전까지 보존할 직접 작성 안내')
        self.assertEqual(self.read('#ees-work-authoring-input', 'value'), '아직 보내지 않은 작성 질문')
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="bulk-t"]')
        self.assertEqual(self.read('#ees-work-child-search', 'value'), '작업 104')
        self.fill('#ees-work-child-search', '')
        # Trusted keyboard selection exercises the native select's change path.
        self.click('#ees-work-child-mode')
        self.key('End', 35)
        self.key('Enter', 13)
        self.wait("document.querySelector('#ees-work-child-mode')?.value === 'tool'")
        self.assertEqual(self.browser.evaluate("Array.from(document.querySelectorAll('.ew-editor-child-list button'), e=>e.dataset.nodeId)"),
                         ['bulk-002-j', 'bulk-005-j', 'bulk-052-j'])
        self.click('#ees-work-child-mode')
        self.key('Home', 36)
        self.key('Enter', 13)
        self.wait("document.querySelector('#ees-work-child-mode')?.value === 'all'")
        self.fill('#ees-work-child-search', '작업 104')
        self.click('.ew-editor-child-list [data-node-id="bulk-104-j"]')
        self.assertEqual(self.read('#ees-work-node-form [name="instructions"]', 'value'), '게시 전까지 보존할 직접 작성 안내')
        self.assertEqual(self.read('#ees-work-authoring-input', 'value'), '아직 보내지 않은 작성 질문')
        self.click('#ees-work-designer [data-action="save_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('초안 r1')")
        self.assertEqual(self.authoring_current('bulk-p')['process']['workflow']['nodes']['bulk-104-j']['instructions'], '게시 전까지 보존할 직접 작성 안내')
        self.assertEqual(self.current()['case']['definition'], original['definition'])
        self.assertEqual(self.current()['case']['jobs'], original['jobs'])
        self.screenshot('ees-integrated-workspace-hierarchy')

    def test_personal_settings_uses_native_controls_and_keeps_workspace_draft(self):
        self.open_authoring()
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="db-j"]')
        self.wait("document.querySelector('#ees-work-node-form h2')?.textContent === 'DB 연결 확인'")
        self.fill('#ees-work-node-form [name="instructions"]', '개인 설정을 열어도 보존할 미저장 안내')
        self.fill('#ees-work-authoring-input', '개인 설정에서 돌아온 뒤 보낼 질문')
        before = self.current()
        before_authoring = self.authoring_current()["process"]["workflow"]
        request_start = len(self.server.requests)
        original_session = self.browser.session
        selector = '#ees-work-node-form a[href="/?ees=tool-settings"]'
        self.assertEqual(self.read(selector, 'target'), '_blank')
        self.assertIn('noopener', self.read(selector, 'rel'))
        self.click(selector)
        targets = self.browser.call('Target.getTargets')['targetInfos']
        settings_target = next(target['targetId'] for target in targets
                               if target['url'] == self.server.url + '/?ees=tool-settings')
        try:
            self.browser.session = self.browser.call('Target.attachToTarget', {
                'targetId': settings_target, 'flatten': True})['sessionId']
            self.browser.call('Runtime.enable')
            self.browser.call('Network.enable')
            # CDP viewport overrides belong to a target, so the new tab needs
            # the same desktop viewport as the original Workspace target.
            self.browser.call('Emulation.setDeviceMetricsOverride', {
                'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait("document.querySelector('#controls-container')?.getBoundingClientRect().width > 0"
                      " && !!document.querySelector('#ees-personal-settings-guide')")
            self.assertIn('Valves', self.text('#ees-personal-settings-guide'))
            self.assertIsNone(self.read('#ees-work-designer'))
            self.browser.evaluate("""(async()=>{
                await document.fonts.load('400 14px "EES Noto Sans KR"', '공장 업무');
                await document.fonts.ready;
            })()""")
            self.screenshot('ees-integrated-native-personal-settings')
            # Opening is a one-time navigation convenience. User closure must
            # not be undone by the launcher's normal DOM observation.
            self.click('nav button[aria-label="Controls"]')
            self.wait("!document.querySelector('#controls-container')?.getBoundingClientRect().width")
            self.browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            self.assertFalse(self.read('#controls-container', 'getBoundingClientRect().width'))
            self.server.user.update(role='user', permissions={'chat': {'controls': False, 'valves': False}})
            self.navigate('/?ees=tool-settings')
            self.wait("!!document.querySelector('#chat-input.ProseMirror')")
            self.assertIsNone(self.read('nav button[aria-label="Controls"]'))
            self.assertIsNone(self.read('#ees-personal-settings-guide'))
        finally:
            self.server.user.update(role='admin', permissions={})
            self.browser.session = original_session
            self.browser.call('Target.closeTarget', {'targetId': settings_target})
        self.assertEqual(self.read('#ees-work-node-form [name="instructions"]', 'value'), '개인 설정을 열어도 보존할 미저장 안내')
        self.assertEqual(self.read('#ees-work-authoring-input', 'value'), '개인 설정에서 돌아온 뒤 보낼 질문')
        self.assertEqual(self.authoring_current()['process']['workflow'], before_authoring)
        writes = [path for method, path in self.server.requests[request_start:] if method == 'POST'
                  and (path in {'/api/ees-work/action', '/api/ees-work/authoring/action'} or path == '/api/v1/users/user/settings/update'
                       or path.startswith('/api/v1/tools/'))]
        self.assertEqual(writes, [], 'Opening native settings cannot write a draft, credentials or user preferences')

    def test_workspace_tab_uses_native_type_and_does_not_flicker_on_idle_or_route_change(self):
        chat_font = self.browser.evaluate("getComputedStyle(document.querySelector('#chat-input')).fontFamily")
        self.navigate("/workspace/models")
        for path in ("models", "knowledge", "prompts", "workflow", "models"):
            if path == "workflow":
                self.click("#ees-work-workspace-tab")
                self.select_authoring_process()
                self.assertEqual(self.browser.evaluate("location.pathname+location.search"), "/?ees=workflow")
                stable = self.browser.evaluate("""new Promise(resolve=>{
                    const entry=document.querySelector('#ees-work-authoring-link');let frames=0,missing=0;
                    const tick=()=>{if(!entry.isConnected||document.querySelector('#ees-work-authoring-link')!==entry)missing++;
                        if(++frames<32){requestAnimationFrame(tick);return;}resolve({missing,count:document.querySelectorAll('#ees-work-authoring-link').length});};requestAnimationFrame(tick);
                })""")
                self.assertEqual(stable, {"missing": 0, "count": 1})
                self.assertEqual(self.browser.evaluate("getComputedStyle(document.querySelector('#ees-work-node-form input[name=name]')).fontFamily"), chat_font)
                continue
            elif not self.browser.evaluate("location.pathname === " + json.dumps("/workspace/" + path)
                                           + " && !location.search"):
                if self.browser.evaluate("location.pathname === '/'"):
                    self.click('#sidebar a[href^="/workspace"]')
                    self.wait("location.pathname === '/workspace/models' && !location.search")
                if path != 'models':
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
        selected_stage = '#ees-work-tree .ew-step[data-step-id="install-t"]'
        self.assertEqual(self.read(selected_stage, "dataset.expanded"), "true")
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
        self.assertEqual(self.read(selected_stage, "dataset.expanded"), "true")
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
        self.assertEqual(self.read(selected_stage, "dataset.expanded"), "true")
        self.assertIn("attachment.txt", self.text("#chat-container"))
        self.choose("db-j")
        current = self.current()["case"]
        tree = self.text("#ees-work-tree")
        post_count = self.server.requests.count(("POST", "/api/ees-work/action"))
        if not self.read('.ew-panel-menu', 'open'):
            self.click('.ew-panel-menu > summary')
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
        if not self.read('.ew-panel-menu', 'open'):
            self.click('.ew-panel-menu > summary')
        self.click('#ees-work-run-view [data-action="current_view"]')
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === 'DB 연결 확인'")
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
        self.wait("document.querySelector('#ees-work-panel .ew-title')?.textContent === '신규 공장 횡전개'"
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        self.assertEqual(self.browser.evaluate("location.pathname+location.search"), original_url)
        self.fill("#chat-input", "두 번째 실행의 별도 초안")
        current_tree = self.text("#ees-work-tree")
        self.server.action_response_hold.set()
        self.wait("performance.getEntriesByType('resource').filter(e=>e.name.endsWith('/api/ees-work/action')).length > " + str(before))
        self.assertEqual(self.text("#chat-input"), "두 번째 실행의 별도 초안")
        self.assertEqual(self.text("#ees-work-tree"), current_tree)
        self.assertEqual(self.text("#ees-work-panel .ew-title"), "신규 공장 횡전개")
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

    def test_durable_runtime_panel_plan_real_service_and_browser_return(self):
        """Actual Native UI + durable service/DB; business bridge response is synthetic."""
        definition = deepcopy(self.current()["catalog"])
        # This fixture tests one independent real-contract J; legacy manual
        # records are deliberately not eligible durable dependency evidence.
        for item in definition["nodes"].values():
            item["deps"] = []
        reference = {"tool_id": "synthetic-existing-native", "function": "get_page", "revision": 1,
                     "content_hash": "a" * 64, "schema_hash": "b" * 64, "config_hash": "c" * 64,
                     "environment": "browser-synthetic"}
        definition["nodes"]["setup-p"]["execution_inputs"] = {"type": "object", "properties": {
            "page_id": {"type": "string", "maxLength": 30, "title": "문서 번호"}},
            "required": ["page_id"], "additionalProperties": False}
        definition["nodes"]["db-j"]["execution"] = {"protocol": 1, "kind": "fixed", "calls": [
            {"id": "read-page", "reference": reference, "arguments": {"page_id": {"source": "input", "key": "page_id"}}}],
            "completion": {"validator": "all_complete_v1", "version": 1}, "limits": {
                "timeout_seconds": 30, "max_tool_calls": 1, "max_model_calls": 0, "max_retries": 0},
            "evidence": [], "skill_refs": []}
        calls = []
        class SyntheticBridge:
            async def check(self, user, ref):
                return {"reference": ref, "executable": True}
            async def invoke(self, user, ref, arguments, context):
                calls.append((user["id"], deepcopy(arguments)))
                return {"version": "ees-native-result-v1", "status": "succeeded", "transport": "succeeded",
                        "completeness": "complete", "data": {"page": {"page_id": "42", "content": "합성 설치 문서"}},
                        "evidence": [{"kind": "confluence_page", "id": "42"}], "provenance": ref}
        self.server.workflow.execution.bridge = SyntheticBridge()
        self.publish_runtime_fixture(definition)
        case = self.seed_case("existing-chat")
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#ees-work-context')")
        self.choose("db-j")
        self.assertIn("실행 계획 확인", self.text("#ees-work-run"))
        self.click("#ees-work-run")
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.fill('#ees-runtime-input-form [name="page_id"]', "42")
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'queued'")
        self.assertEqual(calls, [])
        state = asyncio.run(self.server.workflow.execution_state(self.server.user, case_id=case["id"]))
        run_id = state["run"]["id"]
        if getattr(self, 'poll_same_page', False):
            self.fill('#chat-input', '실행 중에도 보존할 대화 초안')
        else:
            self.click('#ees-work-close')
            self.browser.navigate('about:blank')
        async def complete():
            for _ in range(8):
                if not await self.server.workflow.execution.process_once():
                    break
        asyncio.run(complete())
        completed = asyncio.run(self.server.workflow.execution_state(self.server.user, run_id=run_id))
        self.assertEqual(completed["run"]["status"], "succeeded", completed)
        self.assertEqual(calls, [(self.server.user["id"], {"page_id": "42"})])
        if getattr(self, 'poll_same_page', False):
            self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'succeeded'")
            self.wait("document.querySelector('.ew-work-identity [data-status]')?.dataset.status === 'passed'")
            self.assertIn('1 / 6 작업 완료', self.text('#ees-work-entry'))
            self.assertEqual(self.text('#chat-input'), '실행 중에도 보존할 대화 초안')
            self.assertEqual(self.current()['case']['selected_id'], 'db-j')
            self.screenshot('runtime-native-same-page-projection')
            return
        self.navigate("/c/existing-chat")
        self.wait("!!document.querySelector('#ees-work-context')")
        self.choose("db-j")
        self.wait("document.querySelector('[data-runtime-record]')?.dataset.runtimeRecord === 'succeeded'")
        self.assertIn("Windows 설치 완료를 의미하지 않습니다", self.text("#ees-work-content"))
        self.click('.ew-work-runtime-detail > summary[data-work-overlay]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertIn("실제 호출·반환 기록 1건", self.text("#ees-work-dialog"))
        self.assertIn('합성 설치 문서', self.text('#ees-work-dialog'))
        self.key('Escape', 27)
        self.assertNotIn("모의 점검 실행", self.text("#ees-work-content"))
        self.screenshot("runtime-native-panel-return")

    def test_durable_runtime_poll_updates_left_progress_and_job_header_without_navigation(self):
        self.poll_same_page = True
        self.test_durable_runtime_panel_plan_real_service_and_browser_return()


if __name__ == "__main__":
    unittest.main()
