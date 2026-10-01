"""NU-05 / SA-26: actual Native account switch with late authoring responses.

The pinned compiled frontend, Auths/Users/Groups/JWT/ACL routes and EES
persistence are real. Temporary accounts/databases and deterministic model
transport are synthetic. HTTP barriers delay already authenticated responses;
no token, storage event, DOM input event or account role is forged.
"""
import json
import os
from pathlib import Path
import threading
import unittest
from uuid import uuid4

import test_ees_work_authoring_native as native


class NativeAuthoringAccountSwitchTests(unittest.TestCase):
    setUpClass = classmethod(native.NativeAuthoringBrowserTests.setUpClass.__func__)
    setUp = native.NativeAuthoringBrowserTests.setUp
    tearDown = native.NativeAuthoringBrowserTests.tearDown
    evidence_directory = native.NativeAuthoringBrowserTests.evidence_directory
    screenshot = native.NativeAuthoringBrowserTests.screenshot
    capture_failure_evidence = native.NativeAuthoringBrowserTests.capture_failure_evidence
    api = native.NativeAuthoringBrowserTests.api
    wait = native.NativeAuthoringBrowserTests.wait
    eventually = native.NativeAuthoringBrowserTests.eventually
    browser_api = native.NativeAuthoringBrowserTests.browser_api
    click_text = native.NativeAuthoringBrowserTests.click_text
    login_ui = native.NativeAuthoringBrowserTests.login_ui
    logout_ui = native.NativeAuthoringBrowserTests.logout_ui
    select_native = native.NativeAuthoringBrowserTests.select_native
    assert_user_workspace_zero = native.NativeAuthoringBrowserTests.assert_user_workspace_zero

    def authoring_content(self):
        # innerText omits textarea/input values: verify both rendered messages
        # and current editor buffers when checking account-private contents.
        return self.browser.evaluate("(()=>{const root=document.querySelector('#ees-work-designer');return [root?.textContent||'',...[...(root?.querySelectorAll('input,textarea')||[])].map(e=>e.value)].join('\\n')})()")

    def arrange_account(self, suffix, system):
        email = f"switch.{suffix.lower()}@example.test"
        result = self.api("POST", "/api/v1/auths/signup", {
            "name": "합성 계정 " + suffix, "email": email,
            "password": "Fixture-person-only-42!"})
        self.assertEqual(result.status_code, 200, result.text)
        account = result.json()
        self.assertEqual(account["role"], "pending")
        result = self.api("POST", "/api/v1/users/" + account["id"] + "/update",
                          {"role": "user"}, self.admin["token"])
        self.assertEqual(result.status_code, 200, result.text)
        group = self.api("POST", "/api/v1/groups/create", {
            "name": system + " account switch fixture", "permissions": {},
            "description": "Temporary Native membership fixture"}, self.admin["token"])
        self.assertEqual(group.status_code, 200, group.text)
        result = self.api("POST", "/api/v1/groups/id/" + group.json()["id"] + "/users/add",
                          {"user_ids": [account["id"]]}, self.admin["token"])
        self.assertEqual(result.status_code, 200, result.text)
        result = self.api("POST", "/api/ees-work/authoring/action", {
            "action": "set_system_group", "system_id": system,
            "expected_mapping_revision": 0, "request_id": str(uuid4()),
            "payload": {"group_id": group.json()["id"], "active": True}}, self.admin["token"])
        self.assertEqual(result.status_code, 200, result.text)
        signed = self.fixture.run(self.fixture.signin(email, "Fixture-person-only-42!"))
        settings = self.api("POST", "/api/v1/users/user/settings/update", {
            "ui": {"params": {"system": "NU05 private Native setting " + suffix},
                   "chatBubble": suffix == "B"}}, signed["token"])
        self.assertEqual(settings.status_code, 200, settings.text)
        created = self.api("POST", "/api/ees-work/authoring/action", {
            "action": "create", "system_id": system, "request_id": str(uuid4()),
            "payload": {"name": suffix + " 전용 합성 절차", "category": "setup"}}, signed["token"])
        self.assertEqual(created.status_code, 200, created.text)
        return signed, created.json()["process"]

    def open_process(self, system, process_id):
        self.navigate("/?ees=workflow")
        self.wait("document.querySelector('#ees-work-manage-system:not(:disabled)')?.value === " + json.dumps(system))
        self.select_native("#ees-work-manage-process", process_id)
        self.wait("!!document.querySelector('#ees-work-node-form') && document.querySelector('#ees-work-manage-process')?.value === " + json.dumps(process_id))
        self.assert_user_workspace_zero()

    def test_same_profile_native_logout_login_discards_late_a_read_and_ai(self):
        account_a, process_a = self.arrange_account("A", "EMS")
        account_b, process_b = self.arrange_account("B", "FDC")
        # Chat storage/transport is deliberately synthetic; ownership is
        # checked against the current actual Native verified user.
        from native_ui_fixture import chat_record
        chat_a, chat_b = "private-account-a-chat", "private-account-b-chat"
        for identifier, account, title in ((chat_a, account_a, "NU05 A private chat title"),
                                            (chat_b, account_b, "NU05 B current chat title")):
            record = chat_record(identifier)
            record["user_id"] = account["id"]
            record["title"] = record["chat"]["title"] = title
            self.fixture.chats[identifier] = record
        a_text = "SA26 계정 A만의 저장하지 않은 수행 안내"
        a_question = "SA26 계정 A의 비공개 작성 질문"
        a_answer = "SA26 늦게 도착한 계정 A 전용 응답"
        b_text = "NU05 계정 B가 현재 직접 작성한 수행 안내"
        self.login_ui(account_a["email"], "Fixture-person-only-42!")
        self.open_process("EMS", process_a["process_id"])
        self.wait("document.querySelector('#ees-work-authoring-model')?.value === 'fixture-model'")
        self.fill('#ees-work-node-form [name=instructions]', a_text)
        self.fill('#ees-work-authoring-input', a_question)
        self.server.authoring_answer = json.dumps({"answer": a_answer, "instructions": a_answer})
        self.server.authoring_hold.clear()
        self.addCleanup(self.server.authoring_hold.set)
        self.click('#ees-work-authoring [data-action=ai_edit]')
        self.assertTrue(self.server.authoring_started.wait(timeout=5), "A model request did not begin")
        self.assertIn(a_text, self.server.authoring_requests[-1]["messages"][0]["content"])
        gate = {"actor_id": account_a["id"], "process_id": process_a["process_id"],
                "started": threading.Event(), "release": threading.Event(), "finished": threading.Event()}
        self.server.authoring_read_gate = gate
        self.addCleanup(gate["release"].set)
        self.click('#ees-work-designer [data-action=authoring_refresh]')
        self.assertTrue(gate["started"].wait(timeout=5), "Authenticated A P read did not reach the response barrier")
        old_session = self.browser.session

        # Another CDP target in the same Chrome profile shares actual Native
        # cookies/localStorage. Native logout/signin produce the storage events.
        self.browser.navigate("about:blank")
        self.browser.call("Runtime.enable")
        self.browser.call("Network.enable")
        self.navigate("/")
        self.wait("!!document.querySelector('#chat-input.ProseMirror')")
        self.logout_ui(account_a["name"])
        self.login_ui(account_b["email"], "Fixture-person-only-42!")
        self.open_process("FDC", process_b["process_id"])
        self.fill('#ees-work-node-form [name=instructions]', b_text)
        new_session = self.browser.session
        self.assertEqual(self.browser_api("GET", "/api/v1/auths/")["data"]["id"], account_b["id"])
        settings_b = self.browser_api("GET", "/api/v1/users/user/settings")["data"]
        self.assertEqual(settings_b["ui"]["params"]["system"], "NU05 private Native setting B")
        self.assertNotIn("NU05 private Native setting A", json.dumps(settings_b))
        chats_b = self.browser_api("GET", "/api/v1/chats/?page=1")["data"]
        self.assertEqual([record["id"] for record in chats_b], [chat_b])
        self.assertEqual(self.browser_api("GET", "/api/v1/chats/" + chat_a)["status"], 403)
        self.assertEqual(self.browser_api("GET", "/api/v1/chats/" + chat_b)["status"], 200)
        self.assertNotIn("NU05 A private chat title", self.browser.evaluate("document.body.textContent"))
        self.assertNotIn(a_text, self.authoring_content())

        # Release actual A-authorized responses only after B is editing.
        gate["release"].set()
        self.server.authoring_hold.set()
        self.assertTrue(gate["finished"].wait(timeout=5))
        self.assertTrue(self.server.authoring_reply_finished.wait(timeout=5))
        self.wait("document.querySelector('#ees-work-node-form [name=instructions]')?.value === " + json.dumps(b_text))
        for secret in (a_text, a_question, a_answer):
            self.assertNotIn(secret, self.authoring_content())
        self.screenshot("sa26-b-after-late-a-responses")

        # The former A tab must also be a B-scoped UI with no A draft/cache.
        self.browser.session = old_session
        self.wait("document.querySelector('#ees-work-manage-system:not(:disabled)')?.value === 'FDC'")
        self.assertEqual(self.browser_api("GET", "/api/v1/auths/")["data"]["id"], account_b["id"])
        self.select_native('#ees-work-manage-process', process_b["process_id"])
        self.wait("!!document.querySelector('#ees-work-node-form')")
        for secret in (a_text, a_question, a_answer):
            self.assertNotIn(secret, self.authoring_content())
        self.assertEqual(self.browser_api("GET", "/api/v1/users/user/settings")["data"]["ui"]["params"]["system"],
                         "NU05 private Native setting B")
        self.assertNotEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), a_text)
        self.screenshot("nu05-former-a-tab-now-b")

        # B's subsequent authoring request contains only B's current context.
        self.browser.session = new_session
        self.server.authoring_answer = "계정 B 안내에 대한 합성 응답"
        self.fill('#ees-work-authoring-input', '현재 B 절차에 대해 설명해 줘')
        self.click('#ees-work-authoring-form button[type=submit]')
        self.wait("document.querySelector('#ees-work-authoring')?.innerText.includes('계정 B 안내에 대한 합성 응답')")
        context = json.dumps(self.server.authoring_requests[-1]["messages"], ensure_ascii=False)
        self.assertIn(b_text, context)
        for secret in (a_text, a_question, a_answer):
            self.assertNotIn(secret, context)
        self.assertEqual(self.read('#ees-work-node-form [name=instructions]', 'value'), b_text)
        for account, process, system in ((account_a, process_a, "EMS"), (account_b, process_b, "FDC")):
            stored = self.api("GET", "/api/ees-work/authoring?system_id=" + system + "&process_id=" + process["process_id"], token=account["token"])
            self.assertEqual(stored.status_code, 200, stored.text)
            self.assertEqual(stored.json()["process"]["draft_revision"], process["draft_revision"])
        if directory := os.environ.get("EES_TEST_SCREENSHOT_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "sa26-nu05-account-switch.json").write_text(json.dumps({
                "same_profile": True, "native_logout_and_login_ui": True,
                "a_pending_read_after_authentication": True, "a_pending_ai_transport": True,
                "b_workspace_permissions_zero": True, "b_draft_preserved": True,
                "former_a_tab_scoped_to_b": True, "b_ai_context_excludes_a": True,
                "native_user_settings_api_scoped_to_b": True,
                "native_settings_dialog_tested": False,
                "synthetic_chat_list_scoped_and_a_detail_denied": True,
                "native_sidebar_a_chat_title_absent": True,
                "automatic_persistence": False,
                "synthetic_boundary": "Temporary accounts/data; model completion and HTTP response delays are deterministic. Native Auths/Users/Groups/JWT/ACL and compiled frontend are actual pinned code."
            }, ensure_ascii=False, indent=2), encoding="utf-8")
