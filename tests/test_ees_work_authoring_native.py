"""SA/NU integration against pinned Native accounts, groups, tokens and UI.

All users, passwords, keys, models and databases are synthetic. The tested
authentication/approval/group routes and persistence are actual Open WebUI
0.11.3 code, not role/group JSON response fixtures. Redis/SSO and live LLMs are
outside this fixture; session limitations are explicit assertions below.
"""

import base64
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = os.environ.get("EES_TEST_UPSTREAM_WHEEL")
REQUIRED = os.environ.get("EES_REQUIRE_AUTHORING_NATIVE") == "1"


class NativeAccountAPITests(unittest.TestCase):
    def setUp(self):
        if not UPSTREAM or not Path(UPSTREAM).is_file():
            if REQUIRED:
                self.fail("Required Native account gate needs EES_TEST_UPSTREAM_WHEEL")
            self.skipTest("Pinned Native wheel is unavailable")
        from native_auth_fixture import NativeAuthFixture
        self.temporary = tempfile.TemporaryDirectory(prefix="ees-native-account-")
        self.addCleanup(self.temporary.cleanup)
        wheel = Path(UPSTREAM)
        if directory := os.environ.get("EES_TEST_BRANDING_DIR"):
            manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
            wheel = Path(directory) / manifest["wheel"]["filename"]
        self.fixture = NativeAuthFixture(wheel, self.temporary.name)
        self.addCleanup(self.fixture.close)
        self.fixture.run(self.fixture.start())
        self.admin = self.fixture.run(self.fixture.signin())

    def request(self, method, path, payload=None, token=None):
        return self.fixture.run(self.fixture.request(method, path, token=token, payload=payload))

    def signup(self, email="new.person@example.test"):
        result = self.request("POST", "/api/v1/auths/signup", {
            "name": "합성 신규 담당자", "email": email, "password": "Fixture-person-only-42!",
            "role": "admin", "system": "EMS", "department": "administrator",
        })
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["role"], "pending")
        return result.json()

    def approve(self, account):
        result = self.request("POST", "/api/v1/users/" + account["id"] + "/update",
                              {"role": "user"}, self.admin["token"])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["role"], "user")

    def test_native_signup_pending_no_membership_and_closed_registration(self):
        """NU-01/02: actual signup ignores client role; closed API rejects."""
        account = self.signup()
        self.assertNotEqual(account["id"], self.admin["id"])
        groups = self.fixture.run(self.fixture.groups.Groups.get_groups_by_member_id(account["id"]))
        self.assertEqual(groups, [])
        users = self.request("GET", "/api/v1/users/", token=account["token"])
        self.assertIn(users.status_code, {401, 403})
        role = self.request("POST", "/api/v1/users/" + account["id"] + "/update",
                            {"role": "admin"}, account["token"])
        self.assertIn(role.status_code, {401, 403})
        closed = self.fixture.run(self.fixture.set_signup(False, self.admin["token"]))
        self.assertEqual(closed.status_code, 200, closed.text)
        denied = self.request("POST", "/api/v1/auths/signup", {
            "name": "Closed signup", "email": "closed@example.test", "password": "Fixture-closed-only-42!"})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertIsNone(self.fixture.run(self.fixture.users.Users.get_user_by_email("closed@example.test")))
        self.assertEqual(self.fixture.run(self.fixture.users.Users.get_user_by_id(self.admin["id"])).role, "admin")

    def test_native_password_change_reset_and_existing_token_without_redis(self):
        """NU-06: password changes block old credentials; token revocation needs Redis."""
        account = self.signup()
        self.approve(account)
        second = self.fixture.run(self.fixture.signin(account["email"], "Fixture-person-only-42!"))
        wrong = self.request("POST", "/api/v1/auths/update/password", {
            "password": "wrong-current-password", "new_password": "Fixture-changed-only-42!"}, account["token"])
        self.assertEqual(wrong.status_code, 400, wrong.text)
        changed = self.request("POST", "/api/v1/auths/update/password", {
            "password": "Fixture-person-only-42!", "new_password": "Fixture-changed-only-42!"}, account["token"])
        self.assertEqual((changed.status_code, changed.json()), (200, True))
        old_login = self.request("POST", "/api/v1/auths/signin", {
            "email": account["email"], "password": "Fixture-person-only-42!"})
        self.assertEqual(old_login.status_code, 400)
        fresh = self.fixture.run(self.fixture.signin(account["email"], "Fixture-changed-only-42!"))
        self.assertEqual(fresh["role"], "user")
        self.assertEqual(self.request("GET", "/api/v1/auths/", token=second["token"]).status_code, 200,
                         "Redis-free Native deployment retains existing JWTs until expiry")
        reset = self.request("POST", "/api/v1/users/" + account["id"] + "/update",
            {"password": "Fixture-reset-only-42!"}, self.admin["token"])
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.request("POST", "/api/v1/auths/signin", {
            "email": account["email"], "password": "Fixture-changed-only-42!"}).status_code, 400)
        self.assertEqual(self.fixture.run(self.fixture.signin(account["email"], "Fixture-reset-only-42!"))["id"], account["id"])
        self.assertEqual(self.request("GET", "/api/v1/auths/", token=second["token"]).status_code, 200)
        self.assertEqual(self.request("POST", "/api/v1/auths/signout", token=fresh["token"]).status_code, 200)
        self.assertEqual(self.request("GET", "/api/v1/auths/", token=second["token"]).status_code, 200)

    def test_pending_group_member_cannot_author_or_use_protected_runtime(self):
        """NU-02/08: group membership never bypasses current Native approval."""
        if not os.environ.get("EES_TEST_BRANDING_DIR"):
            self.skipTest("Built EES wheel is required")
        self.fixture.run(self.fixture.install_workflow())
        pending = self.signup()
        group = self.request("POST", "/api/v1/groups/create", {
            "name": "Pending is not approval", "description": "synthetic", "permissions": {}}, self.admin["token"])
        self.assertEqual(group.status_code, 200, group.text)
        group_id = group.json()["id"]
        assigned = self.request("POST", "/api/v1/groups/id/" + group_id + "/users/add", {
            "user_ids": [pending["id"]]}, self.admin["token"])
        self.assertEqual(assigned.status_code, 200, assigned.text)
        linked = self.request("POST", "/api/ees-work/workspace/command", {
            "action": "save_access", "system_id": "EMS", "factory_id": "*", "expected_revision": 0,
            "request_id": str(uuid4()), "principal_kind": "group", "principal_id": group_id,
            "roles": ["manager", "participant"]}, self.admin["token"])
        self.assertEqual(linked.status_code, 200, linked.text)
        for method, path, body in (
            ("GET", "/api/ees-work/workspace?system_id=EMS", None),
            ("GET", "/api/ees-work/operations?system_id=EMS", None),
            ("POST", "/api/ees-work/workspace/command", {"action":"create_workflow","system_id":"EMS","name":"denied","expected_revision":0,"request_id":str(uuid4())}),
            ("POST", "/api/ees-work/operations", {"action":"execute_job","run_id":"missing","job_id":"missing","expected_revision":0,"request_id":str(uuid4())}),
        ):
            response = self.request(method, path, body, pending["token"])
            self.assertIn(response.status_code, {401, 403}, response.text)
        self.approve(pending)
        permitted=self.request("GET", "/api/ees-work/workspace", token=pending["token"])
        self.assertEqual(permitted.status_code,200,permitted.text)
        self.assertTrue(permitted.json()["capabilities"]["can_author"])
        recalled = self.request("POST", "/api/v1/users/" + pending["id"] + "/update", {"role": "pending"}, self.admin["token"])
        self.assertEqual(recalled.status_code, 200, recalled.text)
        self.assertIn(self.request("GET", "/api/ees-work/workspace", token=pending["token"]).status_code, {401, 403})


class NativeAuthoringBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_ees_work_demo import EESWorkNativeBrowserTests
        cls.chrome = os.environ.get("EES_TEST_CHROME")
        directory = os.environ.get("EES_TEST_BRANDING_DIR")
        if not cls.chrome or not directory:
            if REQUIRED:
                raise RuntimeError("Required Native authoring browser gate needs Chrome and built wheel")
            raise unittest.SkipTest("Native Chrome/wheel unavailable")
        cls.chrome = shutil.which(cls.chrome)
        manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
        cls.wheel_path = Path(directory) / manifest["wheel"]["filename"]
        # Reuse trusted-pointer/keyboard and bounded-wait helpers, not its
        # synthetic user setup or inherited test methods.
        for name in ("read", "text", "click", "key", "fill", "navigate",
                     "select_scope", "wait_scope_ready", "open_category", "select_node", "choose"):
            if hasattr(EESWorkNativeBrowserTests, name):
                setattr(cls, name, getattr(EESWorkNativeBrowserTests, name))

    def setUp(self):
        from native_auth_fixture import NativeAuthFixture, NativeAuthUIServer
        from test_ees_chat_theme import ChromePipe
        self.temporary = tempfile.TemporaryDirectory(prefix="ees-native-authoring-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = NativeAuthFixture(self.wheel_path, Path(self.temporary.name) / "data")
        self.addCleanup(self.fixture.close)
        self.fixture.run(self.fixture.start())
        self.fixture.run(self.fixture.install_workflow())
        self.admin = self.fixture.run(self.fixture.signin())
        self.server = NativeAuthUIServer(self.wheel_path, self.fixture)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.browser = ChromePipe(self.chrome, str(Path(self.temporary.name) / "chrome"))
        self.addCleanup(self.browser.close)
        # unittest records setup/test/teardown failures before cleanups. Collect
        # while this fixture's browser is still alive, even if setup failed.
        self.addCleanup(self.capture_failure_evidence)
        self.browser.navigate("about:blank")
        self.browser.call("Runtime.enable")
        self.browser.call("Network.enable")
        self.browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('locale','ko-KR');localStorage.setItem('version','0.11.3');"})
        self.navigate("/auth")
        self.wait("!!document.querySelector('#email')")

    def tearDown(self):
        self.capture_failure_evidence()
        self.assertEqual(self.server.errors, [])

    def evidence_directory(self):
        # This is already uploaded by the existing Linux workflow. The account
        # gate did not set EES_TEST_SCREENSHOT_DIR, so failures had no artifact.
        directory = Path(os.environ.get("EES_TEST_SCREENSHOT_DIR", ROOT / "dist/ees-work-screenshots"))
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def screenshot(self, name, *, wait_for_fonts=True):
        if wait_for_fonts:
            self.browser.evaluate('document.fonts.ready.then(()=>true)')
        data = self.browser.call("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": False})["data"]
        (self.evidence_directory() / (name + ".png")).write_bytes(base64.b64decode(data))

    def capture_failure_evidence(self):
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        if getattr(self, "failure_evidence_captured", False) or not any(
                case is self or getattr(case, "test_case", None) is self for case, _ in failures):
            return
        self.failure_evidence_captured = True
        name = self._testMethodName + "-failure"
        evidence = {"test": self.id(), "boundary": "Synthetic Native authentication fixture",
                    "last_wait": getattr(self, "last_wait_expression", None),
                    "requests": self.server.requests[-20:], "capture_errors": []}
        try:
            # Preserve the failure as observed even if a font request stalled.
            self.screenshot(name, wait_for_fonts=False)
        except Exception as error:
            evidence["capture_errors"].append("screenshot:" + type(error).__name__)
        try:
            # Record an allowlisted DOM projection, never input values, cookies,
            # storage, tokens, or the authenticated request/response bodies.
            evidence["dom"] = self.browser.evaluate("""(()=>({
                route:location.pathname+location.search,readyState:document.readyState,
                visibilityState:document.visibilityState,hasFocus:document.hasFocus(),
                nativeReady:window.__eesNativeDraftV1?.ready(),
                controls:[...document.querySelectorAll('button,[role=button],#email,#name,#sidebar,#chat-input')]
                  .slice(0,180).map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                    return {tag:e.tagName,id:e.id,type:e.getAttribute('type'),role:e.getAttribute('role'),
                      label:e.getAttribute('aria-label'),text:e.matches('button,[role=button]')?e.textContent.trim().slice(0,200):null,
                      disabled:!!e.disabled,hidden:e.hidden,inert:e.inert,ariaHidden:e.getAttribute('aria-hidden'),
                      dataValue:e.getAttribute('data-value'),display:s.display,visibility:s.visibility,
                      rect:{x:r.x,y:r.y,width:r.width,height:r.height},
                      pointerHit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};})
            }))()""")
        except Exception as error:
            evidence["capture_errors"].append("dom:" + type(error).__name__)
        try:
            (self.evidence_directory() / (name + ".json")).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as error:
            # Diagnostics must never replace the original test failure.
            print("Native failure evidence unavailable: " + type(error).__name__)

    def api(self, method, path, payload=None, token=None):
        return self.fixture.run(self.fixture.request(method, path, payload=payload, token=token))

    def eventually(self, callback, timeout=9):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if callback():
                return
            time.sleep(.025)
        self.fail("Native persistence did not settle\n" + self.text("body") + repr(self.server.requests[-12:]))

    def current(self, chat_id=None):
        if chat_id is None:
            chat_id = self.browser.evaluate("location.pathname.startsWith('/c/')?location.pathname.split('/')[2]:''")
        result = self.browser_api("GET", "/api/ees-work/state?chat_id=" + chat_id)
        self.assertEqual(result["status"], 200, result)
        return result["data"]

    def assert_user_workspace_zero(self):
        session = self.browser_api("GET", "/api/v1/auths/")["data"]
        self.assertEqual(session["role"], "user")
        self.assertFalse(any(session["permissions"]["workspace"].values()), session["permissions"])

    def group_member_ui(self, group_id, account, member):
        self.navigate("/admin/users/groups?id=" + group_id)
        self.wait("!!document.querySelector('#admin-settings-tabs-container')")
        self.click_text("사용자", selector="#admin-settings-tabs-container button")
        selector = '[role="checkbox"][aria-label="' + account.name + '"]'
        self.wait("!!document.querySelector(" + json.dumps(selector) + ")")
        self.assertEqual(self.read(selector, "getAttribute('aria-checked')"), "false" if member else "true")
        self.click(selector)
        # Native checkbox is optimistic. Verify its real membership commit.
        self.eventually(lambda: (group_id in [g.id for g in self.fixture.run(
            self.fixture.groups.Groups.get_groups_by_member_id(account.id))]) == member)
        self.wait("document.querySelector(" + json.dumps(selector) + ")?.getAttribute('aria-checked') === " + json.dumps("true" if member else "false"))

    def new_browser(self, name):
        from test_ees_chat_theme import ChromePipe
        browser = ChromePipe(self.chrome, str(Path(self.temporary.name) / name))
        self.addCleanup(browser.close)
        self.addCleanup(self.capture_failure_evidence)
        browser.navigate("about:blank")
        browser.call("Runtime.enable")
        browser.call("Network.enable")
        browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('locale','ko-KR');localStorage.setItem('version','0.11.3');"})
        self.browser = browser
        self.navigate("/auth")
        self.wait("!!document.querySelector('#email')")
        return browser

    def wait(self, expression, timeout=9000):
        self.last_wait_expression = expression
        # Native signout performs a full navigation, destroying the old JS
        # context. Do not keep a Promise running inside that dying context.
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            try:
                if self.browser.evaluate("Boolean(" + expression + ")"):
                    return
            except AssertionError as error:
                if not any(fragment in str(error) for fragment in
                           ("navigated or closed", "context was destroyed", "Cannot find context", "active page")):
                    raise
            time.sleep(0.025)
        readiness = self.browser.evaluate("({route:location.pathname+location.search,nativeReady:window.__eesNativeDraftV1?.ready(),pickerBusy:document.querySelector('#ees-work-entry .ew-scope-pickers')?.getAttribute('aria-busy'),readyRoute:document.querySelector('#ees-work-entry .ew-scope-pickers')?.dataset.readyRoute,pickerDisabled:document.querySelector('#ees-work-site-trigger')?.disabled})")
        self.fail("Timed out: " + expression + "\n" + self.text("body") + "\nReadiness: " + repr(readiness) + "\nUnknown: " + repr(self.server.unknown))

    def browser_api(self, method, path, payload=None):
        return self.browser.evaluate("(async()=>{const r=await fetch(" + json.dumps(path) + ","
            + "{method:" + json.dumps(method)
            + ",headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.token},"
            + "body:" + (json.dumps(json.dumps(payload)) if payload is not None else "undefined")
            + "});return {status:r.status,data:await r.json()};})()")

    def click_text(self, text, selector="button", exact=True):
        # The auth fields can mount before the signup/config/i18n branch. Wait
        # for the actual localized, enabled pointer target, not merely #email.
        match = "e.textContent.trim()===" + json.dumps(text) if exact else "e.textContent.includes(" + json.dumps(text) + ")"
        actionable = ("e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return " + match
            + "&&!e.disabled&&r.width>0&&r.height>0&&s.visibility==='visible'"
            + "&&r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight"
            + "&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}")
        candidates = "[...document.querySelectorAll(" + json.dumps(selector) + ")]"
        self.wait(candidates + ".some(" + actionable + ")")
        self.browser.evaluate("document.querySelectorAll('[data-native-test-target]').forEach(e=>e.removeAttribute('data-native-test-target'))")
        found = self.browser.evaluate("(()=>{const e=" + candidates + ".find(" + actionable
            + ");if(!e)return false;e.setAttribute('data-native-test-target','true');return true;})()")
        self.assertTrue(found, "Missing native control: " + text + "\n" + self.text("body"))
        self.click("[data-native-test-target]")

    def open_sidebar(self):
        # Native restores its own sidebar preference after navigation. A chat
        # composer can be ready with the sidebar already open; do not toggle it.
        opened = """(()=>{const e=document.querySelector('#sidebar'),r=e?.getBoundingClientRect();
            return e?.getAttribute('aria-hidden')==='false'&&!e.inert&&r.width>200&&r.x>=0
                &&r.right<=innerWidth&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+50));})()"""
        opening = """[...document.querySelectorAll('button[aria-label="사이드바 열기"]')].some(e=>{
            const r=e.getBoundingClientRect();return !e.disabled&&r.width>0&&r.height>0
                &&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})"""
        self.wait(opened + " || " + opening)
        if not self.browser.evaluate(opened):
            self.click('button[aria-label="사이드바 열기"]')
        self.wait(opened)

    def login_ui(self, email, password):
        self.navigate("/auth")
        self.wait("!!document.querySelector('#email')")
        self.fill("#email", email)
        self.fill("#password", password)
        self.click('button[type="submit"]')
        self.wait("location.pathname !== '/auth'")

    def select_native(self, selector, value):
        position = self.browser.evaluate("(()=>{const e=document.querySelector(" + json.dumps(selector)
            + ");return e?[...e.options].findIndex(o=>o.value===" + json.dumps(value) + "):-1})()")
        self.assertGreaterEqual(position, 0)
        # Open the native picker so intermediate Arrow keys do not dispatch
        # onchange/load for every option before the intended selection commits.
        self.click(selector)
        self.key("Home", 36)
        for _ in range(position):
            self.key("ArrowDown", 40)
        self.key("Enter", 13)
        self.key("Tab", 9)
        self.wait("document.querySelector(" + json.dumps(selector) + ")?.value === " + json.dumps(value))

    def open_user_editor(self, email):
        self.navigate("/admin/users/overview")
        self.wait("[...document.querySelectorAll('tr')].some(e=>e.innerText.includes(" + json.dumps(email) + "))")
        self.browser.evaluate("[...document.querySelectorAll('tr')].find(e=>e.innerText.includes("
            + json.dumps(email) + ")).setAttribute('data-native-test-user','true')")
        self.click('[data-native-test-user] td:nth-child(2) button')
        self.wait("!!document.querySelector('select[aria-label]')")

    def logout_ui(self, name):
        # Both collapsed and expanded Native sidebars can remain mounted; only
        # the control actually on screen is a valid trusted-pointer target.
        self.wait("[...document.querySelectorAll('button[aria-label=\"사용자 메뉴\"]')].some(e=>{const r=e.getBoundingClientRect();return r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})")
        self.browser.evaluate("document.querySelectorAll('[data-native-menu]').forEach(e=>e.removeAttribute('data-native-menu'));[...document.querySelectorAll('button[aria-label=\"사용자 메뉴\"]')].find(e=>{const r=e.getBoundingClientRect();return r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}).setAttribute('data-native-menu','true')")
        self.click('[data-native-menu]')
        self.click_text("로그아웃", selector='button,[role="menuitem"]', exact=False)
        self.wait("location.pathname === '/auth'")

    def signup_ui(self, email="author.a@example.test", name="합성 EMS 담당자 A"):
        self.click_text("가입")
        self.wait("!!document.querySelector('#name')")
        self.fill("#name", name)
        self.fill("#email", email)
        self.fill("#password", "Fixture-person-only-42!")
        self.click('button[type="submit"]')
        self.wait("location.pathname !== '/auth'")
        account = self.fixture.run(self.fixture.users.Users.get_user_by_email(email))
        self.assertIsNotNone(account)
        self.assertEqual(account.role, "pending")
        self.assertEqual(self.fixture.run(self.fixture.groups.Groups.get_groups_by_member_id(account.id)), [])
        return account

    def test_closed_native_signup_ui_and_direct_api(self):
        result = self.fixture.run(self.fixture.set_signup(False, self.admin["token"]))
        self.assertEqual(result.status_code, 200, result.text)
        self.navigate("/auth")
        self.wait("!!document.querySelector('#email')")
        self.assertFalse(self.browser.evaluate("[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='가입')"))
        denied = self.api("POST", "/api/v1/auths/signup", {
            "name": "Closed browser signup", "email": "closed.browser@example.test", "password": "Fixture-closed-only-42!"})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.screenshot("nu-closed-native-signup")

    def work_command(self, action, expected_revision=0, **values):
        body={"action":action,"expected_revision":expected_revision,"request_id":str(uuid4()),**values}
        result=self.browser_api("POST","/api/ees-work/workspace/command",body)
        self.assertEqual(result["status"],200,result);self.assertTrue(result["data"]["ok"],result)
        return result["data"]

    def enter_authoring(self):
        self.wait("document.querySelector('#ees-work-entry')")
        self.open_sidebar();self.click('[data-action="mode"][data-mode="author"]')
        self.wait("document.querySelector('#ees-work-designer')")

    def create_ui_procedure(self,name):
        self.enter_authoring()
        self.wait("document.querySelector('[data-author-action=create]') && !document.querySelector('[data-author-action=create]').disabled")
        self.click('[data-author-action="create"]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.assertTrue(self.browser.evaluate("document.activeElement?.hasAttribute('data-dialog-close')"))
        self.fill('#ees-work-dialog [name="name"]',name);self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('[data-author-action=add_stage]')")
        state=self.browser_api("GET","/api/ees-work/workspace")["data"]
        return next(item["id"] for item in state["workflows"] if item["name"]==name)

    def test_native_authoring_conflict_keeps_unsaved_draft_and_published_version(self):
        self.login_ui("administrator@example.test","Fixture-admin-only-42!")
        key=self.create_ui_procedure("동시 편집 검증")
        self.click('[data-author-action="add_stage"]');self.fill('#ew-author-node [name="name"]','아직 저장하지 않은 단계')
        prior=self.browser_api("GET","/api/ees-work/workspace?workflow_id="+key)["data"]["workflow"]
        changed=deepcopy(prior["draft"]);changed["name"]='다른 요청의 저장'
        saved=self.work_command('save_draft',expected_revision=prior['revision'],workflow_id=key,definition=changed)
        self.click('[data-author-action="save"]')
        self.wait("document.querySelector('#ees-work-designer [role=alert]')")
        self.assertEqual(self.read('#ew-author-node [name="name"]','value'),'아직 저장하지 않은 단계')
        after=self.browser_api("GET","/api/ees-work/workspace?workflow_id="+key)["data"]["workflow"]
        self.assertEqual(after['draft']['name'],'다른 요청의 저장');self.assertEqual(after['revision'],saved['revision'])
        self.assertIsNone(after['published_version']);self.screenshot('integrated-native-authoring-conflict')


    def test_native_ai_proposal_requires_apply_save_and_cancel_preserves_draft(self):
        self.login_ui("administrator@example.test", "Fixture-admin-only-42!")
        key=self.create_ui_procedure("제안 경계 검증")
        self.click('[data-author-action=add_stage]')
        self.fill('#ew-author-node [name=instructions]', '직접 편집한 미저장 값')
        self.click('[data-author-action=node][data-id=""]')
        self.click('.ew-author-ai > summary'); self.fill('[name=ai_prompt]', '설명 제안')
        self.wait("!document.querySelector('[data-author-action=ai_propose]')?.disabled")
        self.server.proposal_answer='반영 전 합성 제안'
        self.click('[data-author-action=ai_propose]')
        self.wait("document.querySelector('[data-author-action=ai_apply]')")
        self.click('.ew-author-stage [data-author-action=node]')
        self.assertEqual(self.read('#ew-author-node [name=instructions]','value'),'직접 편집한 미저장 값')
        before=self.browser_api('GET','/api/ees-work/workspace?workflow_id='+key)['data']['workflow']
        self.assertEqual(before['revision'],1); self.assertNotEqual(before['draft'].get('description'),'반영 전 합성 제안')
        self.click('[data-author-action=ai_apply]')
        self.assertEqual(self.read('#ew-author-node [name=instructions]','value'),'반영 전 합성 제안')
        self.assertEqual(self.browser_api('GET','/api/ees-work/workspace?workflow_id='+key)['data']['workflow'],before)
        gate={'workflow_id':key,'started':threading.Event(),'release':threading.Event(),'finished':threading.Event()}
        self.server.proposal_gate=gate;self.addCleanup(gate['release'].set)
        self.click('[data-author-action=node][data-id=""]')
        if not self.read('.ew-author-ai','open'):
            self.click('.ew-author-ai > summary')
        self.fill('[name=ai_prompt]','취소할 추가 제안'); self.click('[data-author-action=ai_propose]')
        self.assertTrue(gate['started'].wait(5)); self.click('[data-author-action=ai_cancel]'); gate['release'].set()
        self.assertTrue(gate['finished'].wait(5))
        self.wait("!document.querySelector('[data-author-action=ai_apply]')")
        self.click('.ew-author-stage [data-author-action=node]')
        self.assertEqual(self.read('#ew-author-node [name=instructions]','value'),'반영 전 합성 제안')
        self.assertEqual(self.browser_api('GET','/api/ees-work/workspace?workflow_id='+key)['data']['workflow'],before)
        self.click('[data-author-action=save]')
        self.wait("document.querySelector('#ees-work-designer')?.innerText.includes('초안 r2')")
        after=self.browser_api('GET','/api/ees-work/workspace?workflow_id='+key)['data']['workflow']
        self.assertEqual(after['draft']['description'],'반영 전 합성 제안');self.assertIsNone(after['published_version'])
        self.screenshot('integrated-native-ai-proposal-not-auto-save')

    def test_native_new_signup_and_approval_ui(self):
        account = self.signup_ui()
        self.wait("document.body.innerText.includes('계정 활성화 대기')")
        self.assertIn(self.browser_api("GET", "/api/ees-work/state")["status"], {401, 403})
        # A settled FontFaceSet does not prove that a runner can render Korean.
        # Observe the visible Native heading's actual glyph font before capture.
        self.browser.evaluate('document.fonts.ready.then(()=>true)')
        selector = '.text-center.text-2xl'
        measured = self.browser.evaluate("""(selector=>{const e=document.querySelector(selector),s=getComputedStyle(e);
            return {readyState:document.readyState,fontStatus:document.fonts.status,
                text:e.textContent,fontFamily:s.fontFamily,
                koreanCharacters:(e.textContent.match(/[가-힣]/g)||[]).length};})(""" + json.dumps(selector) + ")")
        self.browser.call('DOM.enable')
        self.browser.call('CSS.enable')
        document = self.browser.call('DOM.getDocument')
        node = self.browser.call('DOM.querySelector', {'nodeId': document['root']['nodeId'], 'selector': selector})
        measured['platformFonts'] = self.browser.call('CSS.getPlatformFontsForNode', {'nodeId': node['nodeId']})['fonts']
        (self.evidence_directory() / 'sa-signup-pending-fonts.json').write_text(
            json.dumps(measured, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertGreater(measured['koreanCharacters'], 0, measured)
        self.assertGreaterEqual(sum(font['glyphCount'] for font in measured['platformFonts']
                                    if font['familyName'] in {'Noto Sans KR', 'Noto Sans KR Thin'}),
                                measured['koreanCharacters'], measured)
        self.screenshot("sa-signup-pending")
        self.click_text("로그아웃")
        self.login_ui("administrator@example.test", "Fixture-admin-only-42!")
        self.open_user_editor(account.email)
        self.select_native('select[aria-label]', 'user')
        self.click('button[type="submit"]')
        self.wait("!document.querySelector('select[aria-label]')")
        self.assertEqual(self.fixture.run(self.fixture.users.Users.get_user_by_id(account.id)).role, 'user')
        self.screenshot("sa-native-approved-user")
        self.logout_ui("합성 기존 관리자")
        self.login_ui(account.email, "Fixture-person-only-42!")
        self.wait("!!document.querySelector('#chat-input.ProseMirror')")
        capabilities = self.browser_api("GET", "/api/ees-work/authoring/capabilities")
        self.assertFalse(capabilities["data"]["can_author"], capabilities)
        self.assertEqual(capabilities["data"]["managed_systems"], [])
        session = self.browser_api("GET", "/api/v1/auths/")["data"]
        self.assertEqual(session["role"], "user")
        self.assertFalse(any(session["permissions"]["workspace"].values()))
        self.fill("#chat-input", "승인받은 일반 사용자로 처음 질문합니다")
        self.click("#send-message-button")
        self.wait("document.body.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        self.first_chat = self.browser.evaluate("location.pathname.split('/')[2]")
        self.screenshot("sa-approved-first-chat")
        self.assertTrue(self.server.completions)
        self.assertEqual(self.server.chats[self.first_chat]["user_id"], account.id)
        # Native approval alone grants no EES scope and no Native workspace permission.
        empty=self.browser_api("GET","/api/ees-work/workspace")["data"]
        self.assertEqual(empty['workflows'],[]);self.assertFalse(empty['capabilities']['can_author'])
        forbidden=self.browser_api('POST','/api/ees-work/workspace/command',{'action':'create_workflow','system_id':'EMS','name':'권한 없는 생성','expected_revision':0,'request_id':str(uuid4())})
        self.assertEqual(forbidden['status'],403,forbidden)
        group=self.api('POST','/api/v1/groups/create',{'name':'이름으로 권한을 얻지 않는 합성 그룹','description':'synthetic','permissions':{}},self.admin['token']).json()
        membership=self.api('POST','/api/v1/groups/id/'+group['id']+'/users/add',{'user_ids':[account.id]},self.admin['token'])
        self.assertEqual(membership.status_code,200,membership.text)
        unmapped=self.browser_api('GET','/api/ees-work/workspace')['data'];self.assertFalse(unmapped['capabilities']['can_author'])
        grant=self.api('POST','/api/ees-work/workspace/command',{'action':'save_access','system_id':'EMS','factory_id':'*','principal_kind':'group','principal_id':group['id'],'roles':['manager','participant'],'expected_revision':0,'request_id':str(uuid4())},self.admin['token'])
        self.assertEqual(grant.status_code,200,grant.text)
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        # A new authorization scope does not silently choose a workplace.
        self.click('#ees-work-system-trigger')
        self.wait("document.querySelector('[data-action=choose_system][data-system-id=EMS]')")
        self.click('[data-action=choose_system][data-system-id=EMS]')
        key=self.create_ui_procedure('합성 담당자 작성 절차')
        self.click('[data-author-action="add_stage"]');self.fill('#ew-author-node [name="name"]','현장 확인')
        self.click('[data-author-action="node"][data-id=""]');self.click('[data-author-action="add_job"]')
        self.fill('#ew-author-node [name="name"]','사람의 명시적 판정')
        self.click('[data-author-action="save"]');self.wait("document.querySelector('[data-author-status]')?.textContent.includes('저장 초안 r2')")
        self.click('[data-author-action="validate"]');self.wait("document.querySelector('[data-author-action=publish]')")
        self.click('[data-author-action="publish"]');self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-designer')?.innerText.includes('게시 v1')")
        published=self.browser_api('GET','/api/ees-work/workspace?workflow_id='+key)['data']['workflow']
        self.assertEqual(published['published_version'],1);self.assert_user_workspace_zero()
        self.assertEqual(self.fixture.run(self.fixture.groups.Groups.get_group_by_id(group['id'])).permissions,{})
        self.assertEqual(self.server.chats[self.first_chat]['user_id'],account.id)
        self.screenshot('integrated-native-group-author-published')
        removed=self.api('POST','/api/v1/groups/id/'+group['id']+'/users/remove',{'user_ids':[account.id]},self.admin['token'])
        self.assertEqual(removed.status_code,200,removed.text)
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        denied=self.browser_api('POST','/api/ees-work/workspace/command',{'action':'save_draft','workflow_id':key,'definition':published['draft'],'expected_revision':published['revision'],'request_id':str(uuid4())})
        self.assertEqual(denied['status'],403,denied)
        self.assert_user_workspace_zero()


if __name__ == "__main__":
    unittest.main()
