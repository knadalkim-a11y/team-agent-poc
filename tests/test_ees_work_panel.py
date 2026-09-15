"""Saved synthetic workflow states rendered by the production panel helpers.

Uses the actual SQLite service and Node without a browser, live business system,
model, or Open WebUI user database. HTML parsing checks content/action boundaries;
these checks do not establish visual layout or browser interaction correctness.
"""

from copy import deepcopy
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "branding/ees/ui/ees-work-view.js"
PACKAGE = ModuleType("ees_work_panel_test_subject")
PACKAGE.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
with patch.dict(sys.modules, {PACKAGE.__name__: PACKAGE}):
    workflow = importlib.import_module(f"{PACKAGE.__name__}.ees_workflow")


class Element:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def text(self):
        return "".join(child.text if isinstance(child, Element) else child for child in self.children)

    def find(self, tag=None, **attrs):
        result = []
        for child in self.children:
            if isinstance(child, Element):
                if (tag is None or child.tag == tag) and all(
                        key in child.attrs and (value is None or child.attrs[key] == value)
                        for key, value in attrs.items()):
                    result.append(child)
                result.extend(child.find(tag, **attrs))
        return result


class PanelHTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


NODE_RENDER = """
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const scope = {input};
vm.createContext(scope);
vm.runInContext(fs.readFileSync(input.source, 'utf8'), scope, {timeout: 2000});
const before = JSON.stringify(input);
const html = vm.runInContext(`workPanelNodeHTML(input.case,
  input.options.definition.nodes[input.node], input.options)`, scope, {timeout: 2000});
process.stdout.write(JSON.stringify({html, unchanged: JSON.stringify(input) === before}));
"""


@unittest.skipUnless(shutil.which("node"), "Node is required for production panel rendering.")
class WorkPanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.users = {"alice": {"id": "alice", "role": "user"}, "admin": {"id": "admin", "role": "admin"}}
        self.alice, self.admin = self.users["alice"], self.users["admin"]
        self.service = workflow.WorkflowService(
            Path(temporary.name) / "ees-work.sqlite3",
            AsyncMock(side_effect=lambda key: deepcopy(self.users.get(key))),
            AsyncMock(return_value=None),
        )

    async def create(self, **payload):
        result = await self.service.handle_action(self.alice, {"action": "create", "payload": payload})
        self.assertTrue(result["ok"], result)
        return result["case"]

    async def step(self, case, action, node_id="", payload=None):
        result = await self.service.handle_action(self.alice, {
            "action": action, "case_id": case["id"], "node_id": node_id,
            "expected_revision": case["revision"], "payload": payload or {},
        })
        self.assertTrue(result["ok"], result)
        return result["case"]

    async def ready(self, case):
        for node_id, payload in (("scope-j", {"confirm": True}), ("infra-j", {}), ("install-j", {"confirm": True})):
            case = await self.step(case, "run", node_id, payload)
        return case

    async def publish(self, definition):
        state = await self.service.get_state(self.admin)
        result = await self.service.handle_action(self.admin, {
            "action": "save_draft", "expected_revision": state["draft_revision"],
            "payload": {"definition": definition},
        })
        self.assertTrue(result["ok"], result)
        revision = result["draft_revision"]
        for action in ("validate_draft", "publish"):
            result = await self.service.handle_action(self.admin, {"action": action, "expected_revision": revision})
            self.assertTrue(result["ok"], result)

    def render(self, case, node_id, **options):
        options = {"definition": case["definition"] if case else workflow._seed(), "readOnly": False,
                   "history": False, **options}
        result = subprocess.run(
            [shutil.which("node"), "-e", NODE_RENDER],
            input=json.dumps({"source": str(VIEW), "case": case, "node": node_id, "options": options}, ensure_ascii=False),
            capture_output=True, encoding="utf-8", timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertTrue(rendered["unchanged"], "Rendering must not mutate saved state or procedure definitions.")
        return PanelHTML(rendered["html"]).root, rendered["html"]

    def section(self, html, name):
        matches = html.find(**{"data-work-section": name})
        self.assertEqual(len(matches), 1, f"Expected one {name} section")
        return matches[0]

    def run_button(self, html, node_id):
        buttons = html.find("button", id="ees-work-run", **{"data-action": "run", "data-node-id": node_id})
        self.assertEqual(len(buttons), 1)
        self.assertIn("data-mutation", buttons[0].attrs)
        return buttons[0]

    def assert_no_mutation(self, html):
        self.assertFalse(html.find(**{"data-mutation": None}))
        self.assertFalse(html.find("form"))
        self.assertFalse(html.find("input"))
        self.assertFalse(html.find("textarea"))
        self.assertFalse(html.find(**{"data-action": "run"}))

    async def test_layers_preserve_distinct_purpose_parent_run_and_job_form_contracts(self):
        case = await self.create()
        for node_id in ("setup-p", "install-t", "db-j"):
            with self.subTest(node=node_id):
                html, _ = self.render(case, node_id)
                node = case["definition"]["nodes"][node_id]
                self.assertIn(node["name"], html.text)
                self.assertIn(node["rule"], html.text)
                self.assertIn(node["description"], html.text)
                self.assertIn("예시", html.text)
                button = self.run_button(html, node_id)
                if node["type"] != "j":
                    self.assertIn("하위 예시 점검 실행", button.text)
                    self.assertFalse(html.find("form"))
                    selected = {item.attrs["data-node-id"] for item in html.find(**{"data-action": "select"})}
                    self.assertTrue(set(node["children"]) <= selected)
                else:
                    form = html.find("form", id="ees-work-inputs")[0]
                    self.assertEqual([field.attrs["name"] for field in form.find("input")], ["db"])
                    self.assertTrue(form.find("button", id="ees-work-inputs-save", type="submit"))
                    self.assertEqual(form.find("input")[0].attrs["value"], case["site"]["db"])
        process, _ = self.render(case, "setup-p")
        task, _ = self.render(case, "install-t")
        self.assertIn("태스크", " ".join(item.text for item in process.find("h3")))
        self.assertIn("잡", " ".join(item.text for item in task.find("h3")))
        manual, _ = self.render(case, "scope-j")
        self.assertIn("확인 완료", self.run_button(manual, "scope-j").text)
        self.assertFalse(manual.find("textarea"), "Manual confirmation has no persisted free-form note contract.")

    async def test_preview_preserves_goals_and_criteria_without_fabricated_results(self):
        definition = (await self.service.get_state(self.alice))["catalog"]
        for node_id in ("setup-p", "install-t", "db-j"):
            with self.subTest(node=node_id):
                html, _ = self.render(None, node_id, definition=definition)
                node = definition["nodes"][node_id]
                self.assertIn(node["rule"], html.text)
                self.assertIn(node["description"], html.text)
                self.assert_no_mutation(html)
                self.assertFalse(html.find(**{"data-status": "passed"}))
                self.assertFalse(html.find(**{"data-work-section": "history"}))

    async def test_human_confirmation_uses_saved_time_and_inputs_not_case_update_time(self):
        case = await self.create()
        target = '공장 <합성> & "범위 확인"'
        case = await self.step(case, "update_inputs", "scope-j", {"inputs": {"site": target}})
        confirmed_at = "2026-09-15T10:15:00.000+00:00"
        changed_at = "2026-09-15T11:30:00.000+00:00"
        with patch.object(workflow, "_now", return_value=confirmed_at):
            case = await self.step(case, "run", "scope-j", {"confirm": True})
        with patch.object(workflow, "_now", return_value=changed_at):
            case = await self.step(case, "select", "scope-j")
        self.assertEqual(case["updated_at"], changed_at)
        html, source = self.render(case, "scope-j")
        current = self.section(html, "current-result")
        self.assertRegex(current.text, "사람|담당자")
        self.assertIn(confirmed_at, current.text)
        self.assertNotIn(changed_at, current.text)
        self.assertIn(target, current.text)
        self.assertNotIn("<합성>", source, "Saved text must be escaped before HTML rendering.")
        self.assertIn(case["jobs"]["scope-j"]["history"][-1]["detail"], current.text)

    async def test_failed_check_skips_are_unperformed_and_retry_preserves_failure_history(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "ap-j")
        first = deepcopy(case["jobs"]["ap-j"]["history"][0])
        self.assertEqual([check["status"] for check in first["checks"]], ["passed", "passed", "failed", "skipped"])
        html, source = self.render(case, "ap-j")
        current = self.section(html, "current-result")
        self.assertLess(source.index('data-work-section="current-result"'), source.index('id="ees-work-inputs"'))
        self.assertTrue(current.find(**{"data-status": "failed"}))
        skipped = current.find(**{"data-status": "skipped"})
        self.assertTrue(skipped)
        self.assertTrue(all("미수행" in item.text and "적용 제외" not in item.text for item in skipped))
        self.assertIn(first["checks"][2]["detail"], current.text)
        self.assertIn(first["checks"][2]["input"], current.text)
        self.assertRegex(self.run_button(html, "ap-j").text, "다시|재시도")
        case = await self.step(case, "run", "ap-j")
        html, _ = self.render(case, "ap-j")
        current, history = self.section(html, "current-result"), self.section(html, "history")
        self.assertFalse(current.find(**{"data-status": "failed"}))
        self.assertFalse(current.find(**{"data-status": "skipped"}))
        self.assertTrue(history.find(**{"data-status": "failed"}))
        self.assertIn(first["at"], history.text)
        self.assertIn(first["checks"][2]["input"], history.text)

    async def test_input_change_and_dependency_rerun_keep_success_only_in_history(self):
        definition = workflow._seed()
        definition["nodes"]["handoff-j"] = {**deepcopy(definition["nodes"]["scope-j"]),
            "id": "handoff-j", "name": "최종 인계 확인", "parent": "interface-t", "deps": ["interface-j"]}
        definition["nodes"]["interface-t"]["children"].append("handoff-j")
        await self.publish(definition)
        case = await self.ready(await self.create())
        for node_id in ("db-j", "ap-j", "ap-j", "interface-j"):
            case = await self.step(case, "run", node_id)
        before = deepcopy(case)
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": "다른 합성 진단 대상"}})
        for node_id in ("db-j", "interface-j"):
            with self.subTest(invalidation="input", node=node_id):
                self.assertEqual(case["jobs"][node_id]["history"], before["jobs"][node_id]["history"])
                html, _ = self.render(case, node_id)
                self.assertFalse(self.section(html, "current-result").find(**{"data-status": "passed"}))
                self.assertTrue(self.section(html, "history").find(**{"data-status": "passed"}))
        for node_id in ("db-j", "interface-j"):
            case = await self.step(case, "run", node_id)
        case = await self.step(case, "run", "db-j")
        self.assertEqual(case["jobs"]["interface-j"]["status"], "pending")
        html, _ = self.render(case, "interface-j")
        self.assertFalse(self.section(html, "current-result").find(**{"data-status": "passed"}))
        self.assertTrue(self.section(html, "history").find(**{"data-status": "passed"}))

    async def test_draft_edit_invalidates_old_confirmation_and_preserves_document_contract(self):
        definition = workflow._seed()
        definition["nodes"]["scope-j"]["mode"] = "draft"
        await self.publish(definition)
        case = await self.create()
        old, new = "검토한 초안 <합성 A>", "변경한 초안 <합성 B>"
        case = await self.step(case, "run", "scope-j", {"document": old})
        case = await self.step(case, "run", "scope-j", {"confirm": True})
        html, _ = self.render(case, "scope-j")
        self.assertIn(old, self.section(html, "current-result").text)
        case = await self.step(case, "run", "scope-j", {"document": new})
        html, _ = self.render(case, "scope-j")
        form = html.find("form", id="ees-work-document")[0]
        self.assertEqual(form.find("textarea", name="document")[0].text, new)
        self.assertTrue(form.find("button", type="submit", **{"data-mutation": None}))
        self.assertIn("검토 완료", self.run_button(html, "scope-j").text)
        self.assertFalse(self.section(html, "current-result").find(**{"data-status": "passed"}))
        self.assertIn(old, self.section(html, "history").text)

    async def test_excluded_zero_total_is_not_shown_as_all_passed(self):
        case = await self.create(site_id="hu-a", system="FDC")
        self.assertEqual(case["node_states"]["interface-t"]["progress"], {"done": 0, "total": 0})
        for node_id in ("interface-t", "interface-j"):
            with self.subTest(node=node_id):
                html, _ = self.render(case, node_id)
                self.assertIn("적용 제외", html.text)
                self.assertFalse(html.find(**{"data-status": "passed"}))
                self.assertNotIn("전체 통과", html.text)
                self.assertNotIn("100%", html.text)
                for control in html.find("button", **{"data-action": "run"}):
                    self.assertIn("disabled", control.attrs)

    async def test_parent_counts_are_unfinished_applicable_composition_not_ready_queue(self):
        definition = workflow._seed()
        definition["tools"]["health"].update(source="open_webui", reference="synthetic-health", adapter="unavailable")
        await self.publish(definition)
        case = await self.create(site_id="hu-a", system="FDC")
        for progressed, expected in ((False, {"simulation": 2, "human": 2, "unavailable": 1}),
                                     (True, {"simulation": 1, "human": 0, "unavailable": 1})):
            if progressed:
                case = await self.ready(case)
            html, _ = self.render(case, "setup-p")
            actual = {item.attrs["data-work-count"]: int(item.text) for item in html.find(**{"data-work-count": None})}
            self.assertEqual(actual, expected)
            self.assertIn("이번 실행 예정 수가 아닙니다", html.text)
        self.assertEqual(case["node_states"]["interface-j"]["status"], "skipped")

    async def test_input_unavailable_and_skill_blocks_explain_actual_progress_condition(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": ""}})
        case = await self.step(case, "run", "install-t")
        self.assertEqual(case["node_states"]["db-j"]["missing"], [])
        html, _ = self.render(case, "db-j")
        self.assertIn(case["jobs"]["db-j"]["blocked_reason"], html.text)
        self.assertTrue(all("선행 작업 대기" not in badge.text for badge in html.find(**{"data-status": "blocked"})))

        definition = workflow._seed()
        definition["tools"]["health"].update(source="open_webui", reference="synthetic-health", adapter="unavailable")
        await self.publish(definition)
        unavailable = await self.ready(await self.create())
        unavailable = await self.step(unavailable, "run", "ap-j")
        html, _ = self.render(unavailable, "ap-j")
        self.assertIn("실제 실행 연결이 없어 수행하지 않았습니다", html.text)
        self.assertTrue(all("선행 작업 대기" not in badge.text for badge in html.find(**{"data-status": "blocked"})))

        definition = workflow._seed()
        definition["skills"]["private-read"] = {"id": "private-read", "name": "합성 읽기 지침", "type": "skill",
            "source": "open_webui", "reference": "private-read", "body": ""}
        definition["nodes"]["db-j"]["skills"] = ["private-read"]
        await self.publish(definition)
        assets = {"tools": [], "skills": [{"id": "private-read", "name": "합성 읽기 지침"}],
                  "skill_bodies": {"private-read": "권한 내에서만 제공하는 합성 본문"}, "skill_versions": {"private-read": 1}}
        self.service.asset_lookup = AsyncMock(return_value=assets)
        restricted = await self.ready(await self.create())
        self.service.asset_lookup = AsyncMock(return_value={"tools": [], "skills": [], "skill_bodies": {}})
        restricted = await self.step(restricted, "run", "install-t")
        restricted = await self.step(restricted, "select", "db-j")
        html, _ = self.render(restricted, "db-j")
        self.assertIn(restricted["jobs"]["db-j"]["blocked_reason"], html.text)
        self.assertNotIn("권한 내에서만 제공하는 합성 본문", html.text)
        self.assertTrue(all("선행 작업 대기" not in badge.text for badge in html.find(**{"data-status": "blocked"})))

    async def test_completed_current_keeps_child_navigation_history_expands_all_evidence(self):
        definition = workflow._seed()
        definition["nodes"]["scope-j"]["mode"] = "draft"
        await self.publish(definition)
        case = await self.create()
        document = "승인한 합성 셋업 초안"
        case = await self.step(case, "run", "scope-j", {"document": document})
        case = await self.ready(case)
        for node_id in ("db-j", "ap-j", "ap-j", "interface-j"):
            case = await self.step(case, "run", node_id)
        self.assertEqual(case["status"], "passed")
        for node_id in ("setup-p", "install-t"):
            with self.subTest(node=node_id):
                html, _ = self.render(case, node_id, readOnly=True)
                self.assert_no_mutation(html)
                selected = {item.attrs["data-node-id"] for item in html.find(**{"data-action": "select"})}
                self.assertTrue(set(case["definition"]["nodes"][node_id]["children"]) <= selected)
        current, _ = self.render(case, "scope-j", readOnly=True)
        self.assert_no_mutation(current)
        self.assertIn(document, current.text)
        html, _ = self.render(case, "setup-p", history=True)
        self.assert_no_mutation(html)
        self.assertFalse(html.find(**{"data-action": "select"}))
        self.assertTrue(html.find("details"))
        self.assertIn(document, html.text)
        for node_id, job in case["jobs"].items():
            self.assertIn(case["definition"]["nodes"][node_id]["rule"], html.text)
            for record in job["history"]:
                self.assertIn(record["at"], html.text)
                for check in record["checks"]:
                    self.assertIn(check["input"], html.text)
                    self.assertIn(check["detail"], html.text)
        self.assertTrue(all("미수행" in item.text for item in html.find(**{"data-status": "skipped"})))


if __name__ == "__main__":
    unittest.main()
