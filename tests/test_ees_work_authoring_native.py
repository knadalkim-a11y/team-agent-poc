"""SA/NU integration against pinned Native accounts, groups, tokens and UI.

All users, passwords, keys, models and databases are synthetic. The tested
authentication/approval/group routes and persistence are actual Open WebUI
0.11.3 code, not role/group JSON response fixtures. Redis/SSO and live LLMs are
outside this fixture; session limitations are explicit assertions below.
"""

import json
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
        linked = self.request("POST", "/api/ees-work/authoring/action", {
            "action": "set_system_group", "system_id": "EMS", "expected_mapping_revision": 0, "request_id": str(uuid4()),
            "payload": {"group_id": group_id, "active": True}}, self.admin["token"])
        self.assertEqual(linked.status_code, 200, linked.text)
        for method, path, body in (
            ("GET", "/api/ees-work/authoring/capabilities", None),
            ("GET", "/api/ees-work/authoring?system_id=EMS", None),
            ("POST", "/api/ees-work/authoring/action", {"action": "create", "system_id": "EMS", "payload": {"name": "denied", "category": "setup"}}),
            ("POST", "/api/ees-work/action", {"action": "create", "payload": {"site_id": "us-a", "system": "EMS", "process_id": "setup-p"}}),
        ):
            response = self.request(method, path, body, pending["token"])
            self.assertIn(response.status_code, {401, 403}, response.text)
        self.approve(pending)
        self.assertTrue(self.request("GET", "/api/ees-work/authoring/capabilities", token=pending["token"]).json()["can_author"])
        recalled = self.request("POST", "/api/v1/users/" + pending["id"] + "/update", {"role": "pending"}, self.admin["token"])
        self.assertEqual(recalled.status_code, 200, recalled.text)
        self.assertIn(self.request("GET", "/api/ees-work/state", token=pending["token"]).status_code, {401, 403})


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
        for name in ("read", "text", "click", "key", "fill", "screenshot", "navigate",
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
        self.browser.navigate("about:blank")
        self.browser.call("Runtime.enable")
        self.browser.call("Network.enable")
        self.browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
            "localStorage.setItem('locale','ko-KR');localStorage.setItem('version','0.11.3');"})
        self.navigate("/auth")
        self.wait("!!document.querySelector('#email')")

    def tearDown(self):
        result = getattr(self._outcome, "result", None)
        failures = list(getattr(result, "failures", ())) + list(getattr(result, "errors", ()))
        if any(case is self for case, _ in failures):
            self.screenshot(self._testMethodName + "-failure")
        self.assertEqual(self.server.errors, [])

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
        self.browser.evaluate("document.querySelectorAll('[data-native-test-target]').forEach(e=>e.removeAttribute('data-native-test-target'))")
        found = self.browser.evaluate("(()=>{const e=[...document.querySelectorAll(" + json.dumps(selector)
            + ")].find(e=>e.getClientRects().length&&"
            + ("e.textContent.trim()===" if exact else "e.textContent.includes(") + json.dumps(text)
            + ("" if exact else ")") + ");if(!e)return false;e.setAttribute('data-native-test-target','true');return true;})()")
        self.assertTrue(found, "Missing native control: " + text + "\n" + self.text("body"))
        self.click("[data-native-test-target]")

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

    def test_native_new_signup_and_approval_ui(self):
        account = self.signup_ui()
        self.wait("document.body.innerText.includes('계정 활성화 대기')")
        self.assertIn(self.browser_api("GET", "/api/ees-work/state")["status"], {401, 403})
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
        self.navigate("/c/" + self.first_chat)
        self.wait("!!document.querySelector('#chat-input')")
        self.click('button[aria-label="사이드바 열기"]')
        self.wait("document.querySelector('#sidebar')?.getBoundingClientRect().width > 200")
        self.select_scope("site", "us-a")
        self.select_scope("system", "EMS")
        self.choose("scope-j", chat_id=self.first_chat)
        self.click("#ees-work-run", confirm=True)
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        first_case = self.current(self.first_chat)["case"]
        self.assertEqual(first_case["jobs"]["scope-j"]["status"], "passed")
        self.logout_ui(account.name)
        self.login_ui("administrator@example.test", "Fixture-admin-only-42!")
        created = self.api("POST", "/api/v1/groups/create", {"name": "EES · EMS 절차 담당",
            "description": "합성 업무 절차 담당 그룹", "permissions": {}, "data": {"config": {"share": False}}}, self.admin["token"])
        self.assertEqual(created.status_code, 200, created.text)
        group_id = created.json()["id"]
        self.group_member_ui(group_id, account, True)
        self.assertEqual([g.id for g in self.fixture.run(self.fixture.groups.Groups.get_groups_by_member_id(account.id))], [group_id])
        self.navigate("/?ees=workflow")
        self.wait("!!document.querySelector('#ees-work-manage-system:not(:disabled)') && !!document.querySelector('#ees-work-designer [data-action=system_settings]')")
        self.click('#ees-work-designer [data-action="system_settings"]')
        group_form = '.ew-system-group[data-system-id="EMS"]'
        self.wait("!!document.querySelector(" + json.dumps(group_form) + ")")
        self.select_native(group_form + ' select[name="group_id"]', group_id)
        if not self.read(group_form + ' input[name="active"]', "checked"):
            self.click(group_form + ' input[name="active"]')
        self.click(group_form + ' button[type="submit"]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.eventually(lambda: any(item["system_id"] == "EMS" and item["group_id"] == group_id
            for item in self.api("GET", "/api/ees-work/authoring?system_id=EMS", token=self.admin["token"]).json()["system_groups"]))
        self.wait("!!document.querySelector('#ees-work-manage-system:not(:disabled)')")
        self.click('#ees-work-designer [data-action="system_settings"]')
        self.wait("document.querySelector('.ew-system-group[data-system-id=EMS]')?.innerText.includes('정상')")
        self.logout_ui("합성 기존 관리자")
        self.login_ui(account.email, "Fixture-person-only-42!")
        self.navigate("/?ees=workflow")
        self.wait("document.querySelector('#ees-work-manage-system:not(:disabled)')?.value === 'EMS'")
        self.assertEqual(self.read('#ees-work-manage-system', 'value'), 'EMS')
        self.assert_user_workspace_zero()
        self.assertEqual(self.fixture.run(self.fixture.groups.Groups.get_group_by_id(group_id)).permissions, {})
        self.screenshot("sa-user-authoring-entry")
        self.click('#ees-work-designer [data-action="add_process"]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        for _ in range(8):
            self.key("Tab", 9)
            self.assertTrue(self.browser.evaluate("document.querySelector('#ees-work-dialog').contains(document.activeElement)"))
        self.key("Escape", 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertEqual(self.browser.evaluate("document.activeElement?.dataset.action"), "add_process")
        self.click('#ees-work-designer [data-action="add_process"]')
        self.wait("document.querySelector('#ees-work-dialog')?.open")
        process_name = "EMS 설비 교대 인수인계 및 전산 변경 확인 절차"
        self.fill('#ees-work-dialog input[name="name"]', process_name)
        self.click('#ees-work-dialog [data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-node-form [name=name]')?.value === " + json.dumps(process_name))
        process_id = self.read('#ees-work-manage-process', 'value')
        path = "/api/ees-work/authoring?system_id=EMS&process_id=" + process_id
        scoped = self.browser_api("GET", path)["data"]
        nodes = scoped["process"]["workflow"]["nodes"]
        task_id = next(key for key, node in nodes.items() if node["type"] == "t")
        job_id = next(key for key, node in nodes.items() if node["type"] == "j")
        for identifier, name, instructions in (
            (process_id, process_name, "교대 전 EMS 변경 내용과 전산 기록을 순서대로 확인합니다."),
            (task_id, "현장 변경 내역 대조", "담당자의 기록을 확인하고 다음 교대에 인계합니다."),
            (job_id, "변경 내역과 교대 인계 확인", "전산 기록과 인계 내용을 사람이 직접 확인합니다."),
        ):
            self.click('#ees-work-designer [data-action="edit_node"][data-node-id="' + identifier + '"]')
            self.fill('#ees-work-node-form [name=name]', name)
            self.fill('#ees-work-node-form [name=instructions]', instructions)
            self.click('#ees-work-node-form > button[type=submit]')
        self.click('#ees-work-designer [data-action=save_draft]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('저장된 초안')")
        self.click('#ees-work-designer [data-action=validate_draft]')
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 전 확인 완료')")
        self.click('#ees-work-designer [data-action=publish]', confirm=True)
        self.wait("document.querySelector('.ew-designer-status')?.innerText.includes('게시 v')")
        self.assert_user_workspace_zero()
        published = self.browser_api("GET", path)["data"]["process"]
        self.assertEqual(published["published_workflow"]["nodes"][job_id]["name"], "변경 내역과 교대 인계 확인")
        original_case = self.browser_api("GET", "/api/ees-work/state?case_id=" + first_case["id"])["data"]["case"]
        self.assertEqual(original_case["definition"], first_case["definition"])
        self.assertEqual(original_case["jobs"]["scope-j"]["status"], "passed")
        self.screenshot("sa-user-published-procedure")
        self.navigate("/?ees=workflow")
        self.wait("!!document.querySelector('#ees-work-manage-process:not(:disabled)')")
        self.assert_user_workspace_zero()
        for system in ("APC", "COMMON"):
            denied = self.browser_api("POST", "/api/ees-work/authoring/action", {
                "action": "create", "system_id": system, "request_id": "forbidden-" + system,
                "payload": {"name": "forbidden process", "category": "setup"}})
            self.assertEqual(denied["status"], 403, denied)
        author_browser = self.browser
        author_token = self.browser.evaluate("localStorage.token")
        self.select_native('#ees-work-manage-process', process_id)
        self.wait("!!document.querySelector('#ees-work-node-form')")
        self.fill('#ees-work-node-form [name=instructions]', "권한 회수 중 보존할 미저장 작성 내용")

        # A second real signup and approval uses independent browser storage.
        ordinary_browser = self.new_browser("chrome-ordinary")
        ordinary = self.signup_ui("ordinary.b@example.test", "합성 일반 사용자 B")
        self.wait("document.body.innerText.includes('계정 활성화 대기')")
        self.click_text("로그아웃")
        self.login_ui("administrator@example.test", "Fixture-admin-only-42!")
        self.open_user_editor(ordinary.email)
        self.select_native('select[aria-label]', 'user')
        self.click('button[type="submit"]')
        self.wait("!document.querySelector('select[aria-label]')")
        self.logout_ui("합성 기존 관리자")
        self.login_ui(ordinary.email, "Fixture-person-only-42!")
        self.wait("!!document.querySelector('#chat-input')")
        self.assert_user_workspace_zero()
        self.assertFalse(self.browser_api("GET", "/api/ees-work/authoring/capabilities")["data"]["can_author"])
        self.fill("#chat-input", "다른 일반 사용자도 게시된 EMS 업무 절차를 이용합니다")
        self.click("#send-message-button")
        self.wait("location.pathname.startsWith('/c/')")
        ordinary_chat = self.browser.evaluate("location.pathname.split('/')[2]")
        self.eventually(lambda: any(message.get("role") == "assistant" and message.get("done")
            for message in self.server.chats.get(ordinary_chat, {}).get("chat", {}).get("history", {}).get("messages", {}).values()))
        self.navigate("/c/" + ordinary_chat)
        self.wait("!!document.querySelector('#chat-input') && document.body.innerText.includes('실제 대화 입력이 전달되었습니다.')")
        self.click('button[aria-label="사이드바 열기"]')
        self.wait("document.querySelector('#sidebar')?.getBoundingClientRect().width > 200")
        self.select_scope("site", "us-a")
        self.select_scope("system", "EMS")
        self.choose(process_id, chat_id=ordinary_chat)
        self.choose(task_id, chat_id=ordinary_chat)
        self.choose(job_id, chat_id=ordinary_chat)
        self.assertEqual(self.read("#ees-work-content h2"), "변경 내역과 교대 인계 확인")
        self.click("#ees-work-run", confirm=True)
        self.wait("!document.querySelector('#ees-work-panel')?.matches('[aria-busy=true]')")
        ordinary_case = self.current(ordinary_chat)["case"]
        self.assertEqual(ordinary_case["jobs"][job_id]["status"], "passed")
        self.assertEqual(ordinary_case["definition"]["nodes"][job_id]["name"], "변경 내역과 교대 인계 확인")
        self.assertEqual(ordinary_case["definition"]["nodes"][job_id]["instructions"], "전산 기록과 인계 내용을 사람이 직접 확인합니다.")
        self.screenshot("sa-ordinary-user-published-a-panel")

        admin_browser = self.new_browser("chrome-admin-recall")
        self.login_ui("administrator@example.test", "Fixture-admin-only-42!")
        self.group_member_ui(group_id, account, False)
        self.browser = author_browser
        self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), "권한 회수 중 보존할 미저장 작성 내용")
        self.click('#ees-work-designer [data-action=save_draft]')
        self.wait("!!document.querySelector('#ees-work-designer [data-action=save_draft]:disabled')")
        self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), "권한 회수 중 보존할 미저장 작성 내용")
        for action in ("save_draft", "validate_draft", "publish"):
            rejected = self.api("POST", "/api/ees-work/authoring/action", {
                "action": action, "system_id": "EMS", "process_id": process_id,
                "expected_owner_revision": published["owner_revision"],
                "expected_draft_revision": published["draft_revision"], "request_id": str(uuid4()),
                "payload": {"workflow": published["workflow"]} if action == "save_draft" else {}}, author_token)
            self.assertEqual(rejected.status_code, 404, rejected.text)
            self.assertEqual(rejected.json()["error"]["code"], "process_not_found")
        self.assert_user_workspace_zero()
        self.assertFalse(self.browser_api("GET", "/api/ees-work/authoring/capabilities")["data"]["can_author"])
        self.screenshot("sa-recalled-author-preserved-local-draft")
        saved = self.api("GET", path, token=self.admin["token"]).json()["process"]
        self.assertEqual(saved["draft_revision"], published["draft_revision"])
        self.assertNotIn("권한 회수 중", json.dumps(saved, ensure_ascii=False))
        # Removing authorship leaves approved personal runtime available.
        self.assertEqual(self.api("GET", "/api/ees-work/state?case_id=" + first_case["id"], token=author_token).status_code, 200)
        self.browser = admin_browser
        self.open_user_editor(account.email)
        self.select_native('select[aria-label]', 'pending')
        self.click('button[type="submit"]')
        self.wait("!document.querySelector('select[aria-label]')")
        self.assertEqual(self.fixture.run(self.fixture.users.Users.get_user_by_id(account.id)).role, "pending")
        self.assertIn(self.api("GET", "/api/ees-work/state", token=author_token).status_code, {401, 403})
        self.browser = ordinary_browser
        self.assertEqual(self.browser_api("GET", "/api/ees-work/state?case_id=" + ordinary_case["id"])["status"], 200)

        # Recreate the Native ASGI app, DB engines, workflow service and HTTP
        # listener with the same Native/EES database files. Chat transport is
        # explicitly synthetic memory, so only copy it for case ownership.
        from native_auth_fixture import NativeAuthFixture, NativeAuthUIServer
        old_fixture, old_server = self.fixture, self.server
        chats = dict(old_fixture.chats)
        directory = old_fixture.directory
        old_server.shutdown()
        old_server.server_close()
        old_fixture.close()
        self.fixture = NativeAuthFixture(self.wheel_path, directory)
        self.addCleanup(self.fixture.close)
        self.fixture.run(self.fixture.start())
        self.fixture.chats.update(chats)
        self.fixture.run(self.fixture.install_workflow())
        self.server = NativeAuthUIServer(self.wheel_path, self.fixture)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.browser = ordinary_browser
        self.login_ui(ordinary.email, "Fixture-person-only-42!")
        self.assert_user_workspace_zero()
        self.assertEqual(self.fixture.run(self.fixture.users.Users.get_user_by_id(account.id)).role, "pending")
        self.assertEqual(self.fixture.run(self.fixture.groups.Groups.get_groups_by_member_id(account.id)), [])
        self.assertEqual(self.fixture.run(self.fixture.groups.Groups.get_group_by_id(group_id)).permissions, {})
        restored = self.api("GET", path, token=self.admin["token"]).json()
        self.assertTrue(any(item["system_id"] == "EMS" and item["group_id"] == group_id and item["active"]
            for item in restored["system_groups"]))
        after = restored["process"]
        self.assertEqual(after, saved)
        state = self.browser_api("GET", "/api/ees-work/state?case_id=" + ordinary_case["id"])
        self.assertEqual(state["status"], 200, state)
        self.assertEqual(state["data"]["case"]["jobs"][job_id]["status"], "passed")
        self.navigate("/c/" + ordinary_chat)
        self.wait("!!document.querySelector('#chat-input')")
        self.screenshot("sa-same-db-reinitialized-ordinary-user")


if __name__ == "__main__":
    unittest.main()
