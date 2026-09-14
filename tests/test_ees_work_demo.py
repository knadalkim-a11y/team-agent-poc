"""Native EES workflow Chrome tests using the real pinned Svelte/Tiptap UI.

The built wheel frontend is unchanged. Only upstream server APIs and model
replies are synthetic; workflow actions and the registered AI Tool use the real
service and a temporary database. No live model, user database or business API
is used. Linux CI requires the browser and built wheel instead of skipping.
"""

import asyncio
import base64
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

from native_ui_fixture import NativeUIServer
from test_ees_chat_theme import ChromePipe

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agent-pack/skills/ees-work-demo/scripts"


def load_module(name, path):
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
        self.browser.evaluate("document.readyState")
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        if any(case is self or getattr(case, "test_case", None) is self for case, _ in failures):
            self.screenshot(self._testMethodName + "-failure")
        errors = [e["params"] for e in self.browser.events if e.get("method") == "Runtime.exceptionThrown"]
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
                expected_revision=case["revision"], __user__=self.server.user,
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

    def click(self, selector, confirm=False):
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
            if confirm and event_type == "mouseReleased":
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
                        self.browser.call("Page.handleJavaScriptDialog", {"accept": True})
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

    def select(self, selector, value):
        index = self.browser.evaluate("[...document.querySelector(" + json.dumps(selector)
            + ").options].findIndex(o=>o.value===" + json.dumps(value) + ")")
        self.assertGreaterEqual(index, 0)
        self.click(selector)
        self.key("Home", 36)
        for _ in range(index):
            self.key("ArrowDown", 40)
        self.key("Enter", 13)
        self.key("Tab", 9)
        self.assertEqual(self.read(selector, "value"), value)

    def choose(self, node_id):
        if not self.read("#ees-work-navigator", "getClientRects().length"):
            self.click('[data-work-category="setup"]')
        self.click('#ees-work-tree [data-action="select"][data-node-id="' + node_id + '"]')
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === "
                  + json.dumps(self.current()["case"]["definition"]["nodes"][node_id]["name"])
                  + " && !document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")

    def create_case(self, site="us-a", chat_id="existing-chat"):
        self.click('[data-work-category="setup"]')
        self.wait("!!document.querySelector('#ees-work-case-start')")
        self.select("#ees-work-site", site)
        self.click("#ees-work-case-start")
        self.wait("document.querySelector('#ees-work-content h2')?.textContent === '신규 공장 횡전개'")
        if chat_id:
            self.assertEqual(self.current(chat_id)["case"]["chat_id"], chat_id)

    def run_job(self, node_id, status="passed"):
        self.choose(node_id)
        before = self.current()["case"]["revision"]
        self.click("#ees-work-run")
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        result = self.current()["case"]
        self.assertGreater(result["revision"], before)
        self.assertEqual(result["jobs"][node_id]["status"], status)

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

    def test_real_tiptap_chat_stream_and_sidebar_panel_share_one_screen(self):
        self.assertIn("기존 대화 기록", self.text("#chat-container"))
        self.fill("#chat-input", "작성 중인 실제 대화")
        self.attach_file()
        self.create_case()
        self.click('#ees-work-navigator [data-action="pin"]')
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
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["status"], "passed")
        self.wait("document.querySelector('#ees-work-content')?.innerText.includes('점검 결과')")
        self.run_job("ap-j", "failed")
        self.assertEqual([x["status"] for x in self.current()["case"]["jobs"]["ap-j"]["checks"]],
                         ["passed", "passed", "failed", "skipped"])
        self.run_job("ap-j")
        self.assertTrue(self.current()["case"]["jobs"]["ap-j"]["history"])
        self.run_job("interface-j")
        case_id = self.current()["case"]["id"]
        self.navigate("/c/other-chat")
        self.wait("!!document.querySelector('#chat-input') && !document.querySelector('#ees-work-context')")
        self.assertIsNone(self.current("other-chat")["case"])
        self.navigate("/c/existing-chat")
        self.wait("document.querySelector('#ees-work-context')?.innerText.includes('이 대화에 연결됨')")
        self.assertEqual(self.current()["case"]["id"], case_id)
        self.assertEqual(self.current()["case"]["jobs"]["db-j"]["status"], "passed")

    def test_existing_workspace_editor_publication_and_user_denial(self):
        self.create_case()
        original_version = self.current()["case"]["version"]
        self.click("#ees-work-admin-link")
        self.wait("!!document.querySelector('#ees-work-designer')")
        self.assertIsNotNone(self.read('#workspace-container'))
        self.click('#ees-work-designer [data-action="edit_node"][data-node-id="db-j"]')
        self.fill('#ees-work-node-form input[name="name"]', "DB 연결 확인 개정")
        self.click('#ees-work-node-form button[type="submit"]')
        self.click('#ees-work-designer [data-action="save_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('초안 1')")
        self.click('#ees-work-designer [data-action="validate_draft"]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('검증 완료')")
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
        self.assertIsNone(self.read("#ees-work-admin-link"))
        self.navigate("/workspace/models?ees=workflow")
        self.wait("document.readyState === 'complete'")
        self.assertIsNone(self.read("#ees-work-designer"))
        self.assertFalse(self.current()["can_manage"])

    def test_new_chat_binds_pending_case_and_rejects_old_chat_callback(self):
        self.click('a#sidebar-new-chat-button')
        self.wait("location.pathname === '/' && !!document.querySelector('#chat-input')")
        self.create_case(chat_id="")
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
        self.click("#ees-work-run")
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


if __name__ == "__main__":
    unittest.main()
