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
const renderer = input.detail ? 'workExecutionDetailHTML' : 'workPanelNodeHTML';
const html = vm.runInContext(`${renderer}(input.case,
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
        from workflow_fixture import publish_fixture_definition
        publish_fixture_definition(self.service, definition)

    def render(self, case, node_id, *, detail=False, **options):
        options = {"definition": case["definition"] if case else workflow._seed(), "readOnly": False,
                   "history": False, **options}
        result = subprocess.run(
            [shutil.which("node"), "-e", NODE_RENDER],
            input=json.dumps({"source": str(VIEW), "case": case, "node": node_id,
                              "options": options, "detail": detail}, ensure_ascii=False),
            capture_output=True, encoding="utf-8", timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertTrue(rendered["unchanged"], "Rendering must not mutate saved state or procedure definitions.")
        return PanelHTML(rendered["html"]).root, rendered["html"]

    def detail_content(self, html, tab):
        content = html.find(**{"data-work-detail-content": tab})
        self.assertEqual(len(content), 1, f"Expected one selected {tab} detail body")
        return content[0]

    async def test_execution_details_use_each_saved_attempt_and_effective_call_input(self):
        case = await self.ready(await self.create())
        first_target, retry_target = "FIRST-AP <public> & target", "SECOND-AP public target"
        case = await self.step(case, "update_inputs", "ap-j", {"inputs": {"ap": first_target}})
        case = await self.step(case, "run", "ap-j")
        first = deepcopy(case["jobs"]["ap-j"]["history"][0])
        case = await self.step(case, "update_inputs", "ap-j", {"inputs": {"ap": retry_target}})
        case = await self.step(case, "run", "ap-j")
        self.assertEqual(case["jobs"]["ap-j"]["history"][0], first)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(case["jobs"]["ap-j"]["history"][1]["status"], "passed")
        for attempt, expected, excluded in ((0, first_target, retry_target), (1, retry_target, first_target)):
            with self.subTest(attempt=attempt):
                html, source = self.render(case, "ap-j", detail=True, tab="input", attemptIndex=attempt, callIndex=2)
                content = self.detail_content(html, "input")
                self.assertIn(expected, content.text)
                self.assertNotIn(excluded, content.text)
                self.assertNotIn("<public>", source, "Saved input must be HTML escaped.")
                self.assert_no_mutation(html)
        failed, _ = self.render(case, "ap-j", detail=True, tab="output", attemptIndex=0, callIndex=2)
        output = self.detail_content(failed, "output")
        self.assertIn(first["checks"][2]["detail"], output.text)
        self.assertIn("실패", failed.text)
        self.assertIn("모의", failed.text)
        self.assertIn("형식", output.text)
        self.assertRegex(output.text, "미확인|미기록|검사하지")
        self.assertNotIn("형식 적합", output.text)

    async def test_synthetic_repeated_call_records_are_selected_by_index_not_tool_id(self):
        # Definition validation does not permit duplicate tool IDs. This tests
        # display compatibility only, not a new runtime repeated-call feature.
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "db-j")
        record = case["jobs"]["db-j"]["history"][0]
        record["checks"] = [
            {"id": "gateway", "name": "동일 도구", "status": "passed", "simulation": True,
             "input": "call-A actual target", "detail": "call-A recorded result", "at": "2026-09-22T01:00:00Z"},
            {"id": "gateway", "name": "동일 도구", "status": "failed", "simulation": True,
             "input": "call-B actual target", "detail": "call-B recorded failure", "at": "2026-09-22T01:00:01Z"},
        ]
        record["status"] = "failed"
        for index in (0, 1):
            for tab, field in (("input", "input"), ("output", "detail")):
                with self.subTest(index=index, tab=tab):
                    html, _ = self.render(case, "db-j", detail=True, tab=tab, attemptIndex=0, callIndex=index)
                    body = self.detail_content(html, tab)
                    self.assertIn(record["checks"][index][field], body.text)
                    self.assertNotIn(record["checks"][1 - index][field], body.text)
                    self.assert_no_mutation(html)

    async def test_unperformed_call_has_no_claimed_transmitted_input(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "ap-j")
        self.assertEqual(case["jobs"]["ap-j"]["history"][0]["checks"][3]["status"], "skipped")
        skipped, _ = self.render(case, "ap-j", detail=True, tab="input", attemptIndex=0, callIndex=3)
        self.assertIn("미수행", skipped.text)
        self.assertRegex(self.detail_content(skipped, "input").text, "전달.*없|수행하지|미수행")
        definition = workflow._seed()
        for tool_id in definition["nodes"]["db-j"]["tools"]:
            definition["tools"][tool_id].update(source="open_webui", adapter="unavailable", reference="synthetic-disconnected")
        await self.publish(definition)
        disconnected = await self.ready(await self.create())
        disconnected = await self.step(disconnected, "run", "db-j")
        html, _ = self.render(disconnected, "db-j", detail=True, tab="output", attemptIndex=0, callIndex=0)
        self.assertIn("미수행", html.text)
        self.assertIn("실행 연결", html.text)
        self.assertNotIn("정상 반환됨", html.text)
        self.assertNotIn("정상 반환 · 성공", html.text)
        self.assert_no_mutation(html)

    async def test_missing_legacy_call_values_do_not_fall_back_to_current_form_or_definition(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "db-j")
        record = case["jobs"]["db-j"]["history"][0]
        record["checks"] = [{"id": "gateway", "name": "과거 점검", "status": "passed"}]
        case["jobs"]["db-j"]["inputs"]["db"] = "CURRENT-FORM-MUST-NOT-BE-HISTORICAL-INPUT"
        case["definition"]["tools"]["gateway"]["version"] = "UNRECORDED-TOOL-VERSION"
        for tab in ("input", "output"):
            with self.subTest(tab=tab):
                html, _ = self.render(case, "db-j", detail=True, tab=tab, attemptIndex=0, callIndex=0)
                body = self.detail_content(html, tab)
                self.assertIn("미기록", body.text)
                self.assertNotIn("CURRENT-FORM-MUST-NOT-BE-HISTORICAL-INPUT", body.text)
                self.assertNotIn("UNRECORDED-TOOL-VERSION", body.text)
                self.assertNotIn("형식 적합", body.text)
        case["jobs"]["db-j"]["history"] = []
        missing, _ = self.render(case, "db-j", detail=True, tab="history")
        self.assertRegex(missing.text, "기록.*없|미기록")
        self.assertNotIn("조회 실패", missing.text)
        self.assertNotIn("권한 제한", missing.text)
        self.assert_no_mutation(missing)

    async def test_recorded_empty_result_is_distinct_from_missing_output(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "db-j")
        check = case["jobs"]["db-j"]["history"][0]["checks"][0]
        # Older saved records may contain an explicitly empty detail. Rendering
        # must distinguish that value from a property never recorded at all.
        check["detail"] = ""
        case["jobs"]["db-j"]["checks"][0]["detail"] = ""
        empty, _ = self.render(case, "db-j", detail=True, tab="output", callIndex=0)
        body = self.detail_content(empty, "output")
        self.assertRegex(body.text, "빈 결과|반환 내용 없음")
        self.assertNotIn("반환 내용 미기록", body.text)
        self.assertIn("미확인", body.text)
        self.assert_no_mutation(empty)
        current, _ = self.render(case, "db-j")
        self.assertRegex(self.section(current, "current-result").text, "빈 결과|반환 내용 없음")
        history, _ = self.render(case, "db-j", detail=True, tab="history")
        self.assertRegex(self.detail_content(history, "history").text, "빈 결과|반환 내용 없음")
        del check["detail"]
        absent, _ = self.render(case, "db-j", detail=True, tab="output", callIndex=0)
        body = self.detail_content(absent, "output")
        self.assertIn("반환 내용 미기록", body.text)
        self.assertNotIn("빈 결과", body.text)
        self.assert_no_mutation(absent)

    async def test_configuration_uses_frozen_case_and_does_not_claim_instruction_compliance(self):
        definition = workflow._seed()
        definition["nodes"]["db-j"]["description"] = "FROZEN-J business purpose"
        definition["tools"]["gateway"]["purpose"] = "FROZEN-TOOL role"
        await self.publish(definition)
        case = await self.ready(await self.create())
        latest = deepcopy(definition)
        latest["nodes"]["db-j"]["description"] = "LATEST-PUBLISHED must remain separate"
        latest["tools"]["gateway"]["purpose"] = "LATEST-TOOL must remain separate"
        await self.publish(latest)
        current = (await self.service.get_state(self.alice, case_id=case["id"]))["case"]
        html, _ = self.render(current, "db-j", detail=True, tab="config")
        self.assertIn("FROZEN-TOOL role", html.text)
        self.assertNotIn("LATEST-TOOL must remain separate", html.text)
        self.assertNotIn("LATEST-PUBLISHED must remain separate", html.text)
        self.assertIn(str(case["version"]), html.text)
        self.assertNotIn("지침 준수 완료", html.text)
        self.assert_no_mutation(html)

    async def test_detail_lookup_failure_and_restricted_access_never_show_stale_records(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "update_inputs", "db-j", {"inputs": {"db": "STALE-INPUT-REQUIRES-AUTHORIZED-READ"}})
        case = await self.step(case, "run", "db-j")
        for kind, text in (("failed", "조회 실패"), ("restricted", "접근 제한")):
            for tab in ("config", "history", "input", "output"):
                with self.subTest(kind=kind, tab=tab):
                    html, source = self.render(case, "db-j", detail=True, tab=tab,
                                               lookupError={"kind": kind, "message": "확인할 수 없는 <합성> 상태"})
                    self.assertIn(text, html.text)
                    self.assertTrue(html.find(**{"data-record-state": kind}))
                    self.assertNotIn("STALE-INPUT-REQUIRES-AUTHORIZED-READ", html.text)
                    self.assertNotIn("예시 응답: 정상입니다", html.text)
                    self.assertNotIn("<합성>", source)
                    self.assert_no_mutation(html)

    async def test_configuration_never_exposes_unavailable_external_skill_body(self):
        definition = workflow._seed()
        definition["skills"]["restricted"] = {
            "id": "restricted", "name": "비공개 합성 스킬", "type": "skill", "source": "open_webui",
            "reference": "private-skill", "body": "PRIVATE-BODY-MUST-NOT-BE-RENDERED",
        }
        definition["nodes"]["db-j"]["skills"] = ["restricted"]
        case = await self.create()
        case["definition"] = definition
        case["context"]["skills"] = []
        html, _ = self.render(case, "db-j", detail=True, tab="config")
        self.assertIn("비공개 합성 스킬", html.text)
        self.assertIn("현재 계정 사용 불가", html.text)
        self.assertNotIn("PRIVATE-BODY-MUST-NOT-BE-RENDERED", html.text)
        self.assertNotIn("assets_available", definition,
                         "A frozen case definition does not contain the current catalog lookup flag.")
        unavailable, _ = self.render(case, "db-j", detail=True, tab="config", assetsAvailable=False)
        self.assertIn("조회 실패", unavailable.text)
        self.assertNotIn("현재 계정 사용 불가", unavailable.text)
        self.assertNotIn("PRIVATE-BODY-MUST-NOT-BE-RENDERED", unavailable.text)

    def test_preview_configuration_uses_current_accessible_skill_list_without_exposing_body(self):
        for via_option in (False, True):
            for accessible in (False, True):
                with self.subTest(via_option=via_option, accessible=accessible):
                    definition = workflow._seed()
                    definition["skills"]["external"] = {
                        "id": "external", "name": "외부 합성 스킬", "type": "skill", "source": "open_webui",
                        "reference": "registered-skill", "body": "EXTERNAL-PREVIEW-BODY-NOT-PUBLIC",
                    }
                    definition["nodes"]["db-j"]["skills"] = ["external"]
                    available = [{"id": "registered-skill", "name": "현재 사용 가능한 스킬"}] if accessible else []
                    options = {"availableSkills": available} if via_option else {}
                    if not via_option:
                        definition["available_skills"] = available
                    html, _ = self.render(None, "db-j", definition=definition, detail=True, tab="config", **options)
                    external = [item for item in html.find("article") if "외부 합성 스킬" in item.text]
                    self.assertEqual(len(external), 1)
                    self.assertIn("등록됨" if accessible else "현재 계정 사용 불가", external[0].text)
                    if accessible:
                        self.assertNotIn("현재 계정 사용 불가", external[0].text)
                    self.assertNotIn("EXTERNAL-PREVIEW-BODY-NOT-PUBLIC", html.text)
                    self.assertNotIn("snapshot_updated_at", html.text)

    async def test_registered_conditions_and_recorded_failures_have_separate_open_controls(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "ap-j")
        html, _ = self.render(case, "install-t")
        for node_id in ("db-j", "ap-j"):
            with self.subTest(node=node_id):
                rows = html.find("tr", **{"data-work-job": node_id})
                self.assertEqual(len(rows), 1)
                open_job = rows[0].find("button", **{"data-action": "select", "data-node-id": node_id})
                condition = rows[0].find("button", **{"data-action": "job_condition", "data-node-id": node_id})
                self.assertEqual(len(open_job), 1)
                self.assertEqual(len(condition), 1)
                self.assertFalse(open_job[0].find("button"))
                self.assertFalse(condition[0].find("button"))
                self.assertIn("aria-expanded", condition[0].attrs)
        expanded, _ = self.render(case, "install-t", listView={"expanded": ["db-j", "ap-j"]})
        for node_id in ("db-j", "ap-j"):
            facts = expanded.find("tr", **{"data-work-condition": node_id})
            self.assertEqual(len(facts), 1)
            deps = workflow._dependencies(case["definition"]["nodes"], node_id)
            for prerequisite in deps:
                links = facts[0].find("button", **{"data-action": "select", "data-node-id": prerequisite})
                self.assertEqual(len(links), 1)
                self.assertIn(case["definition"]["nodes"][prerequisite]["rule"], facts[0].text)
        ap_facts = expanded.find("tr", **{"data-work-condition": "ap-j"})[0]
        self.assertIn(case["jobs"]["ap-j"]["checks"][2]["detail"], ap_facts.text)
        unconstrained = deepcopy(case)
        for ancestor in workflow._ancestors(unconstrained["definition"]["nodes"], "db-j"):
            ancestor["deps"] = []
            ancestor["condition"] = "all"
        ordinary, _ = self.render(unconstrained, "install-t")
        self.assertFalse(ordinary.find("button", **{"data-action": "job_condition", "data-node-id": "db-j"}))
        for node_id in ("setup-p", "install-t", "ap-j"):
            surface, _ = self.render(case, node_id)
            self.assertNotIn("지금 할 일", surface.text)
            self.assertNotIn("다음 할 일", surface.text)
            self.assertFalse(surface.find(**{"class": "ew-work-next"}))

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
        self.assertFalse([field for field in html.find("input") if field.attrs.get("type") != "search"])
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
                self.assertNotIn("예시 업무", html.text)
                if node["type"] != "j":
                    self.assertFalse(html.find("button", **{"data-action": "run"}))
                    self.assertNotIn("다음 작업 열기", html.text)
                    self.assertFalse(html.find("form"))
                    selected = {item.attrs["data-node-id"] for item in html.find(**{"data-action": "select"})}
                    self.assertTrue(set(node["children"]) <= selected)
                else:
                    self.run_button(html, node_id)
                    form = html.find("form", id="ees-work-inputs")[0]
                    self.assertEqual([field.attrs["name"] for field in form.find("input")], ["db"])
                    self.assertTrue(form.find("button", id="ees-work-inputs-save", type="submit"))
                    self.assertEqual(form.find("input")[0].attrs["value"], case["site"]["db"])
        case = await self.ready(case)
        process, _ = self.render(case, "setup-p")
        task, _ = self.render(case, "install-t")
        self.assertEqual(self.run_button(process, "setup-p").text, "범위 모의 점검 실행")
        self.assertEqual(self.run_button(task, "install-t").text, "범위 모의 점검 실행")
        self.assertIn("단계별 진행", " ".join(item.text for item in process.find("h3")))
        self.assertIn("작업 목록", " ".join(item.text for item in task.find("h3")))
        manual, _ = self.render(case, "scope-j")
        self.assertFalse(manual.find("button", **{"data-action": "run"}))
        pending, _ = self.render(await self.create(), "scope-j")
        self.assertEqual(self.run_button(pending, "scope-j").text, "확인 완료")
        self.assertIn("담당자의 확인이 필요합니다.", pending.text)
        self.assertIn("사람 확인", pending.text)
        self.assertFalse(manual.find("textarea"), "Manual confirmation has no persisted free-form note contract.")

    async def test_completed_task_preserves_parent_navigation_without_recommendation_or_mutation(self):
        case = await self.ready(await self.create())
        for node_id in ("db-j", "ap-j", "ap-j"):
            case = await self.step(case, "run", node_id)
        self.assertEqual(case["node_states"]["install-t"]["status"], "passed")
        for read_only in (False, True):
            html, _ = self.render(case, "install-t", readOnly=read_only)
            primary = [button for button in html.find("button")
                       if "ew-primary" in button.attrs.get("class", "").split()]
            self.assertFalse(primary)
            parent = html.find("button", **{"data-action": "select", "data-node-id": "setup-p"})
            self.assertEqual(len(parent), 1)
            self.assertIn(case["definition"]["nodes"]["setup-p"]["name"], parent[0].text)
            self.assertNotIn("다음 할 일", html.text)
            self.assert_no_mutation(html)
        history, _ = self.render(case, "install-t", history=True)
        self.assertFalse(history.find(**{"data-action": "select"}))

    async def test_preview_preserves_goals_and_criteria_without_fabricated_results(self):
        definition = (await self.service.get_state(self.alice))["catalog"]
        for node_id in ("setup-p", "install-t", "db-j"):
            with self.subTest(node=node_id):
                html, _ = self.render(None, node_id, definition=definition)
                node = definition["nodes"][node_id]
                self.assertIn(node["rule"], html.text)
                self.assertIn(node["description"], html.text)
                if node["type"] == "j":
                    self.assertTrue(html.find("form", id="ees-work-inputs"))
                    self.assertTrue(html.find("button", **{"data-action": "run"}))
                else:
                    self.assertFalse(html.find("form"))
                self.assertNotIn("이 공장에서 시작", html.text)
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
        detail, detail_source = self.render(case, "scope-j", detail=True, tab="input", attemptIndex=0)
        self.assertIn(target, detail.text)
        self.assertNotIn("<합성>", source, "Saved text must be escaped before HTML rendering.")
        self.assertNotIn("<합성>", detail_source)
        self.assertRegex(detail.text, "담당자|사람 확인")

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
        detail, _ = self.render(case, "ap-j", detail=True, tab="input", attemptIndex=0, callIndex=2)
        self.assertIn(first["checks"][2]["input"], self.detail_content(detail, "input").text)
        self.assertRegex(self.run_button(html, "ap-j").text, "다시|재시도")
        case = await self.step(case, "run", "ap-j")
        html, _ = self.render(case, "ap-j")
        current = self.section(html, "current-result")
        history, _ = self.render(case, "ap-j", detail=True, tab="history", attemptIndex=0)
        self.assertFalse(current.find(**{"data-status": "failed"}))
        self.assertFalse(current.find(**{"data-status": "skipped"}))
        self.assertTrue(history.find(**{"data-status": "failed"}))
        self.assertIn(first["at"], history.text)
        old_input, _ = self.render(case, "ap-j", detail=True, tab="input", attemptIndex=0, callIndex=2)
        self.assertIn(first["checks"][2]["input"], self.detail_content(old_input, "input").text)

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
                history, _ = self.render(case, node_id, detail=True, tab="history")
                self.assertTrue(history.find(**{"data-status": "passed"}))
        for node_id in ("db-j", "interface-j"):
            case = await self.step(case, "run", node_id)
        case = await self.step(case, "run", "db-j")
        self.assertEqual(case["jobs"]["interface-j"]["status"], "pending")
        html, _ = self.render(case, "interface-j")
        self.assertFalse(self.section(html, "current-result").find(**{"data-status": "passed"}))
        history, _ = self.render(case, "interface-j", detail=True, tab="history")
        self.assertTrue(history.find(**{"data-status": "passed"}))

    async def test_draft_edit_invalidates_old_confirmation_and_preserves_document_contract(self):
        definition = workflow._seed()
        definition["nodes"]["scope-j"]["mode"] = "draft"
        await self.publish(definition)
        case = await self.create()
        old, new = "검토한 초안 <합성 A>", "변경한 초안 <합성 B>"
        case = await self.step(case, "run", "scope-j", {"document": old})
        case = await self.step(case, "run", "scope-j", {"confirm": True})
        html, _ = self.render(case, "scope-j")
        confirmed, _ = self.render(case, "scope-j", detail=True, tab="input", attemptIndex=0)
        self.assertIn(old, confirmed.text)
        self.assertIn("초안 검토가 완료됐습니다.", self.section(html, "current-result").text)
        self.assertNotIn("검토가 필요", self.section(html, "current-result").text)
        case = await self.step(case, "run", "scope-j", {"document": new})
        html, _ = self.render(case, "scope-j")
        form = html.find("form", id="ees-work-document")[0]
        self.assertEqual(form.find("textarea", name="document")[0].text, new)
        self.assertTrue(form.find("button", type="submit", **{"data-mutation": None}))
        self.assertIn("검토 완료", self.run_button(html, "scope-j").text)
        self.assertFalse(self.section(html, "current-result").find(**{"data-status": "passed"}))
        previous, _ = self.render(case, "scope-j", detail=True, tab="input", attemptIndex=0)
        self.assertIn(old, previous.text)
        self.assertNotIn(new, self.detail_content(previous, "input").text)

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
        detail, _ = self.render(unavailable, "ap-j", detail=True, tab="output", attemptIndex=0, callIndex=2)
        self.assertIn("실제 실행 연결이 없어 수행하지 않았습니다", detail.text)
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
        restricted = (await self.service.get_state(self.alice, case_id=restricted["id"]))["case"]
        unavailable_html, _ = self.render(restricted, "db-j")
        self.assertIn("필수 스킬", unavailable_html.text)
        self.assertIn("disabled", self.run_button(unavailable_html, "db-j").attrs)
        restricted = await self.step(restricted, "run", "install-t")
        restricted = await self.step(restricted, "select", "db-j")
        html, _ = self.render(restricted, "db-j")
        self.assertIn(restricted["jobs"]["db-j"]["blocked_reason"], html.text)
        self.assertNotIn("권한 내에서만 제공하는 합성 본문", html.text)
        self.assertTrue(all("선행 작업 대기" not in badge.text for badge in html.find(**{"data-status": "blocked"})))

    async def test_preview_ignores_prerequisite_stage_with_all_jobs_excluded(self):
        definition = workflow._seed()
        definition["nodes"]["db-j"]["deps"] = ["interface-t"]
        html, _ = self.render(None, "db-j", definition=definition, site=definition["sites"]["hu-a"], system="FDC")
        self.assertNotIn("disabled", self.run_button(html, "db-j").attrs)

    async def test_unconnected_attempt_is_not_presented_as_a_simulated_execution(self):
        definition = workflow._seed()
        for tool_id in definition["nodes"]["db-j"]["tools"]:
            definition["tools"][tool_id].update(source="open_webui", adapter="unavailable", reference="synthetic-unconnected")
        await self.publish(definition)
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "db-j")
        self.assertEqual(case["jobs"]["db-j"]["history"][-1]["kind"], "execution_blocked")
        html, _ = self.render(case, "db-j")
        current = self.section(html, "current-result")
        self.assertIn("미수행 · 실행 연결 필요", current.text)
        self.assertNotIn("모의 점검", current.text)
        self.assertIn("disabled", self.run_button(html, "db-j").attrs)

    async def test_direct_child_table_counts_and_parent_failure_navigation(self):
        case = await self.ready(await self.create())
        process, _ = self.render(case, "setup-p")
        progress = self.section(process, "progress")
        counter = progress.find(**{"data-work-total": None})[0]
        self.assertEqual((counter.attrs["data-work-done"], counter.attrs["data-work-total"]), ("2", "4"))
        self.assertIn("단계 완료", progress.text)
        table = process.find("table")[0]
        selected = {element.attrs["data-node-id"] for element in table.find("button", **{"data-action": "select"})}
        self.assertEqual(selected, set(case["definition"]["nodes"]["setup-p"]["children"]))
        case = await self.step(case, "run", "ap-j")
        process, _ = self.render(case, "setup-p")
        task, _ = self.render(case, "install-t")
        distribution = process.find(**{"data-work-distribution": "install-t"})
        self.assertEqual(len(distribution), 1)
        self.assertIn("실패 1", distribution[0].text)
        self.assertNotIn("문제 있는 작업 보기", process.text)
        task_job = task.find("button", **{"data-action": "select", "data-node-id": "ap-j"})
        self.assertEqual(len(task_job), 1)
        self.assertEqual(task_job[0].text, case["definition"]["nodes"]["ap-j"]["name"])
        # Failed AP is opened for explicit retry; independent DB remains eligible
        # for the separate scope action, which must not retry AP automatically.
        self.run_button(process, "setup-p")
        self.run_button(task, "install-t")
        self.assertTrue(process.find("button", **{"data-node-id": "ap-j"}))
        hu = await self.ready(await self.create(site_id="hu-a", system="FDC"))
        process, _ = self.render(hu, "setup-p")
        counter = self.section(process, "progress").find(**{"data-work-total": None})[0]
        self.assertEqual(counter.attrs["data-work-total"], "3")
        self.assertIn("적용 제외 1개", self.section(process, "progress").text)

    async def test_integrated_metrics_count_leaf_jobs_and_do_not_count_human_wait_as_problem(self):
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "ap-j")
        html, _ = self.render(case, "setup-p")
        metrics = {item.attrs["data-work-metric"]: item.text
                   for item in html.find(**{"data-work-metric": None})}
        self.assertIn("3 / 6", metrics["jobs"])
        self.assertIn("2 / 4", metrics["stages"])
        self.assertIn("1", metrics["attention"])
        self.assertIn("3", metrics["incomplete"])
        self.assertEqual(self.run_button(html, "setup-p").text, "범위 모의 점검 실행")

    async def test_large_job_list_search_filter_and_pages_preserve_original_targets(self):
        case = await self.create()
        nodes = case["definition"]["nodes"]
        nodes["install-t"]["children"] = []
        for index in range(63):
            job_id = f"search-job-{index}"
            nodes[job_id] = {**deepcopy(nodes["db-j"]), "id": job_id,
                             "name": f"합성 작업 {index:02}", "parent": "install-t", "deps": []}
            nodes["install-t"]["children"].append(job_id)
            case["jobs"][job_id] = {"inputs": {"db": "합성 대상"}, "history": []}
            case["node_states"][job_id] = {"status": "passed" if index < 30 else "failed" if index < 33 else "pending",
                                            "applicable": index != 62, "missing": []}
        first, _ = self.render(case, "install-t")
        rows = first.find("tr", **{"data-work-job": None})
        self.assertEqual(len(rows), 25)
        self.assertEqual(len(first.find("button", **{"data-action": "job_page"})), 2)
        self.assertEqual(rows[0].attrs["data-work-job"], "search-job-0")
        second, _ = self.render(case, "install-t", listView={"page": 1})
        self.assertEqual(second.find("tr", **{"data-work-job": None})[0].attrs["data-work-job"], "search-job-25")
        selected, _ = self.render(case, "install-t", listView={"query": "작업 3", "filter": "attention"})
        filtered = selected.find("tr", **{"data-work-job": None})
        self.assertEqual([row.attrs["data-work-job"] for row in filtered], [f"search-job-{i}" for i in range(30, 33)])
        self.assertFalse(selected.find("button", **{"data-action": "job_page"}))
        for row in filtered:
            self.assertEqual(row.find("button", **{"data-action": "select"})[0].attrs["data-node-id"], row.attrs["data-work-job"])
        excluded, _ = self.render(case, "install-t", listView={"filter": "excluded"})
        self.assertEqual([row.attrs["data-work-job"] for row in excluded.find("tr", **{"data-work-job": None})], ["search-job-62"])
        empty, _ = self.render(case, "install-t", listView={"query": "<script>"})
        self.assertFalse(empty.find("tr", **{"data-work-job": None}))
        self.assertIn("일치하는 작업이 없습니다", empty.text)

    async def test_job_guidance_is_business_content_and_evidence_opens_read_only_detail(self):
        definition = workflow._seed()
        definition["nodes"]["ap-j"]["instructions"] = "점검 전 담당자에게 대상 서버를 확인하세요."
        definition["skills"]["setup"]["body"] = "PRIVATE_SKILL_SOURCE_MUST_NOT_APPEAR"
        await self.publish(definition)
        case = await self.ready(await self.create())
        case = await self.step(case, "run", "ap-j")
        html, source = self.render(case, "ap-j")
        self.assertIn(definition["nodes"]["ap-j"]["instructions"], html.text)
        self.assertNotIn("PRIVATE_SKILL_SOURCE_MUST_NOT_APPEAR", html.text)
        self.assertNotIn("적용 지침과 스킬", html.text)
        current = self.section(html, "current-result")
        details = self.section(html, "target").find("button", **{"data-action": "work_detail", "data-detail-tab": "output"})
        self.assertEqual(len(details), 1)
        self.assertNotIn("data-mutation", details[0].attrs)
        self.assertEqual(details[0].attrs["data-node-id"], "ap-j")
        self.assertLess(source.index('data-work-section="current-result"'), source.index('id="ees-work-inputs"'))
        self.assertIn(case["jobs"]["ap-j"]["history"][0]["checks"][2]["detail"], current.text)

    async def test_preview_scope_controls_forms_and_multiple_case_boundary(self):
        definition = workflow._seed()
        for blocked in (False, True):
            html, _ = self.render(None, "db-j", definition=definition, site=definition["sites"]["us-a"],
                                  system="EMS", previewBlocked=blocked)
            self.assertIn(definition["sites"]["us-a"]["name"], html.text)
            form = html.find("form", id="ees-work-inputs")[0]
            self.assertEqual(form.attrs["data-node-id"], "db-j")
            self.assertEqual(form.find("input", name="db")[0].attrs["value"], definition["sites"]["us-a"]["db"])
            save = form.find("button", type="submit")[0]
            self.assertEqual("disabled" in save.attrs, blocked)
            self.assertFalse(html.find(**{"data-status": "passed"}))
        excluded, _ = self.render(None, "interface-j", definition=definition,
                                  site=definition["sites"]["hu-a"], system="FDC")
        self.assertIn("적용 제외", excluded.text)
        self.assertIn("이 업무는 현재 범위에서 적용 제외입니다.", excluded.text)
        self.assertIn("현재 공장·시스템 조건에서는 실행 대상이 아닙니다.", excluded.text)
        self.assertFalse(excluded.find("form"))
        self.assertFalse(excluded.find("button", **{"data-action": "run"}))

    def evaluate_drafts(self, script):
        runner = """
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8')), scope = {};
vm.createContext(scope);
vm.runInContext(fs.readFileSync(input.source, 'utf8'), scope, {timeout: 2000});
const value = vm.runInContext(input.script, scope, {timeout: 2000});
process.stdout.write(JSON.stringify(value));
"""
        result = subprocess.run([shutil.which("node"), "-e", runner],
                                input=json.dumps({"source": str(VIEW), "script": script}),
                                capture_output=True, encoding="utf-8", timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_input_drafts_follow_target_and_revision_without_mutating_saved_state(self):
        result = self.evaluate_drafts("""(() => {
const drafts = createWorkInputDrafts();
const a = {key:'case-a/job-a',caseId:'case-a',nodeId:'job-a',version:1};
const b = {key:'case-a/job-b',caseId:'case-a',nodeId:'job-b',version:1};
const saved = {inputs:{ap:'saved AP'},document:'saved draft'};
const before = JSON.stringify(saved);
drafts.edit(a,saved,{inputs:{ap:'typed AP'},document:'typed draft'},4);
const selected = drafts.read(b,{inputs:{ap:'other AP'},document:''},5);
const restored = drafts.read(a,saved,6);
const changed = drafts.read(a,{inputs:{ap:'new server AP'},document:'saved draft'},7);
drafts.rebase(a,{inputs:{ap:'new server AP'},document:'saved draft'},7);
const rebased = drafts.read(a,{inputs:{ap:'new server AP'},document:'saved draft'},8);
const savedResponse = drafts.read(a,{inputs:{ap:'typed AP'},document:'typed draft'},9);
return {selected,restored,changed,rebased,savedResponse,unchanged:before===JSON.stringify(saved)};
})()""")
        self.assertTrue(result["unchanged"])
        self.assertFalse(result["selected"]["inputsChanged"])
        self.assertEqual(result["restored"]["inputs"]["ap"], "typed AP")
        self.assertEqual(result["restored"]["document"], "typed draft")
        self.assertEqual(result["restored"]["revision"], 6)
        self.assertFalse(result["restored"]["conflict"])
        self.assertTrue(result["changed"]["conflict"])
        self.assertEqual(result["changed"]["inputs"]["ap"], "typed AP")
        self.assertFalse(result["rebased"]["conflict"])
        self.assertEqual(result["rebased"]["revision"], 8)
        self.assertFalse(result["savedResponse"]["inputsChanged"])
        self.assertFalse(result["savedResponse"]["documentChanged"])

    def test_shared_workspace_tree_keeps_selected_job_without_runtime_navigation_changes(self):
        rendered = self.evaluate_drafts("""(() => {
const children=Array.from({length:80},(_,i)=>'job-'+i);
const nodes={p:{id:'p',type:'p',name:'합성 워크플로우',children:['t']},
  t:{id:'t',type:'t',name:'합성 단계',parent:'p',children}};
children.forEach(id=>nodes[id]={id,type:'j',name:id,parent:'t',children:[]});
const before=JSON.stringify(nodes);
return {editor:workUI.treeHTML({nodes},['p'],{editing:true,selectedId:'job-79'}),unchanged:before===JSON.stringify(nodes)};
})()""")
        self.assertTrue(rendered["unchanged"])
        editor = PanelHTML(rendered["editor"]).root
        selected_editor = editor.find("button", **{"data-action": "edit_node", "data-node-id": "job-79"})
        self.assertEqual(len(selected_editor), 1)
        self.assertEqual(selected_editor[0].attrs["aria-current"], "step")
        self.assertEqual(len(editor.find("button", **{"data-action": "edit_node"})), 29)

    def test_step_summary_uses_state_and_order_then_retains_completed_selection(self):
        result = self.evaluate_drafts("""(() => {
const jobs=Array.from({length:105},(_,i)=>({id:'j'+i})),states={};
jobs.forEach((job,i)=>states[job.id]={status:i<70?'passed':'pending',ready_for_run:i===70,attention:i===80});
const summaries=createWorkStepSummaries(),initial=summaries.choose('case-a/t',jobs,'j104',states);
states.j104.status='passed';states.j70.status='passed';states.j90.ready_for_run=true;
const refreshed=summaries.choose('case-a/t',jobs,'j104',states);
const selected=summaries.choose('case-a/t',jobs,'j50',states);
const other=summaries.choose('case-b/t',jobs,'j90',states);
return {initial,refreshed,selected,other};
})()""")
        self.assertEqual(result["initial"], ["j70", "j71", "j72", "j80", "j104"])
        self.assertEqual(result["refreshed"], result["initial"])
        self.assertEqual(len(result["selected"]), 5)
        self.assertIn("j50", result["selected"])
        self.assertEqual(result["selected"], sorted(result["selected"], key=lambda value: int(value[1:])))
        self.assertIn("j90", result["other"])

    def test_runtime_step_list_has_all_stages_only_selected_jobs_and_no_left_guidance(self):
        result = self.evaluate_drafts("""(() => {
const children=Array.from({length:105},(_,i)=>'j'+i),nodes={
 p:{id:'p',type:'p',name:'긴 한글 워크플로우',children:['t1','t2']},
 t1:{id:'t1',parent:'p',type:'t',name:'앞 단계',children:['hidden-j']},
 t2:{id:'t2',parent:'p',type:'t',name:'선택 단계',children},
 'hidden-j':{id:'hidden-j',parent:'t1',type:'j',name:'앞 단계 작업'}};
children.forEach(id=>nodes[id]={id,parent:'t2',type:'j',name:'작업 '+id,description:'점검할 대상을 선택하세요',instructions:'이전 결과를 확인하세요'});
const states={t1:{status:'passed',progress:{done:1,total:1}},t2:{status:'in_progress',progress:{done:80,total:105}},j104:{status:'passed'}};
const before=JSON.stringify(nodes),html=workStepProgressHTML({nodes},nodes.p,{run:{node_states:states},selectedId:'j104',selectedTaskId:'t2',summaryIds:['j70','j71','j72','j80','j104']});
return {html,unchanged:before===JSON.stringify(nodes)};
})()""")
        self.assertTrue(result["unchanged"])
        html = PanelHTML(result["html"]).root
        stages = html.find("li", **{"data-step-id": None})
        self.assertEqual([item.attrs["data-step-id"] for item in stages], ["t1", "t2"])
        self.assertEqual([item.attrs["data-expanded"] for item in stages], ["false", "true"])
        self.assertFalse(any("data-selected" in item.attrs for item in stages))
        self.assertIn("1 / 1 완료", stages[0].text)
        self.assertIn("80 / 105 완료", stages[1].text)
        jobs = html.find("button", **{"class": "ew-step-job"})
        self.assertEqual(len(jobs), 5)
        self.assertEqual(jobs[-1].attrs["aria-current"], "step")
        self.assertEqual(len(html.find("button", **{"aria-current": "step"})), 1,
                         "Expanded ancestors must not also become the selected item")
        self.assertEqual(jobs[-1].text, "작업 j104완료")
        self.assertFalse(html.find("button", **{"data-node-id": "hidden-j"}))
        self.assertTrue(any(item.text == "전체 105개 작업 보기" and item.attrs["data-node-id"] == "t2"
                            for item in html.find("button", **{"data-action": "select"})))
        for removed in ("이 단계에서 할 일", "지금 확인할 작업", "점검할 대상을 선택하세요", "이전 결과를 확인하세요"):
            self.assertNotIn(removed, html.text)
        self.assertFalse(html.find("button", **{"data-action": "expand"}))

    def test_navigation_states_keep_actual_failure_waiting_and_slim_review_distinct(self):
        result = self.evaluate_drafts("""(() => {
const data={nodes:{}},cases=[
 ['passed',{status:'passed',block_reason:'input_required'}],
 ['failed',{status:'failed',block_reason:'connection_required'}],
 ['input_required',{status:'blocked',block_reason:'input_required'}],
 ['connection_required',{status:'blocked',block_reason:'connection_required'}],
 ['skill_unavailable',{status:'blocked',block_reason:'skill_unavailable'}],
 ['waiting',{status:'blocked',block_reason:'prerequisite_required',missing:['before']}],
 ['ready',{status:'pending',ready_for_run:true}],['running',{status:'running'}],
 ['skipped',{status:'pending',applicable:false}],['review',{status:'review'}]];
return cases.map(([wanted,saved])=>({wanted,...workNavigationState(data,{id:'j',type:'j'}, {node_states:{j:saved}})}));
})()""")
        self.assertTrue(all(item["key"] == item["wanted"] for item in result))
        self.assertEqual(result[-1]["label"], "검토 대기", "Slim frozen-case data needs no current catalog mode.")
        parents = self.evaluate_drafts("""[0,1].map(attention_count=>workNavigationState({nodes:{}},{id:'t',type:'t'}, {node_states:{t:{status:'blocked',missing:['before'],attention_count}}}))""")
        self.assertEqual([item["key"] for item in parents], ["waiting", "blocked"])

    def test_preview_navigation_uses_effective_scope_input_connection_and_dependencies(self):
        result = self.evaluate_drafts("""(() => {
const p={id:'p',type:'p',children:['t']},t={id:'t',type:'t',parent:'p',children:['j']},j={id:'j',type:'j',parent:'t',mode:'tool',tools:['db'],deps:[]};
const data={nodes:{p,t,j},tools:{db:{id:'db',adapter:'mock',input:'db'}}},site={name:'합성 공장',db:'',interface:false};
const blank=workNavigationState(data,j,null,{site});site.db='synthetic';
const ready=workNavigationState(data,j,null,{site});j.condition='interface';
const excluded=workNavigationState(data,j,null,{site}),html=workStepProgressHTML(data,p,{site,selectedTaskId:'t',summaryIds:['j']});
j.condition='all';data.tools.db.adapter='unavailable';
const connection=workNavigationState(data,j,null,{site});data.tools.db.adapter='mock';
data.nodes.before={id:'before',type:'j',mode:'manual',name:'선행 작업'};j.deps=['before'];
const waiting=workNavigationState(data,j,null,{site});
return {blank,ready,excluded,html,connection,waiting};
})()""")
        self.assertEqual([result[key]["key"] for key in ("blank", "ready", "excluded", "connection", "waiting")],
                         ["input_required", "ready", "skipped", "connection_required", "waiting"])
        self.assertIn("0 / 0 완료 · 제외 1", PanelHTML(result["html"]).root.text)

    def test_preview_external_skill_permission_matches_navigation_counts_and_job_action(self):
        definition = {
            "nodes": {
                "p": {"id": "p", "type": "p", "name": "권한 확인 절차", "children": ["t"], "skills": ["private"]},
                "t": {"id": "t", "type": "t", "name": "점검 단계", "parent": "p", "children": ["j"]},
                "j": {"id": "j", "type": "j", "name": "읽기 점검", "parent": "t", "mode": "tool", "tools": ["ping"]},
            },
            "tools": {"ping": {"id": "ping", "name": "연결 점검", "input": "db", "adapter": "mock"}},
            "skills": {"private": {"id": "private", "source": "open_webui", "reference": "private"}},
            "available_skills": [],
        }
        site = {"id": "test", "name": "합성 공장", "country": "한국", "line": "합성 라인", "db": "synthetic-db"}
        for accessible in (False, True):
            with self.subTest(accessible=accessible):
                definition["available_skills"] = [{"id": "private"}] if accessible else []
                payload = json.dumps({"definition": definition, "site": site}, ensure_ascii=False)
                navigation = self.evaluate_drafts("(() => {const data=" + payload + ";return workNavigationState(data.definition,data.definition.nodes.j,null,{site:data.site});})()")
                self.assertEqual(navigation["ready"], accessible)
                for node_id in ("p", "t"):
                    parent, _ = self.render(None, node_id, definition=definition, site=site)
                    self.assertEqual(parent.find(**{"data-work-ready": None})[0].attrs["data-work-ready"], "1" if accessible else "0")
                    attention = parent.find(**{"data-work-metric": "attention"})[0]
                    self.assertIn("0개" if accessible else "1개", attention.text)
                job, _ = self.render(None, "j", definition=definition, site=site)
                self.assertEqual("disabled" in self.run_button(job, "j").attrs, not accessible)
                if not accessible:
                    self.assertIn("필수 스킬을 현재 계정으로 사용할 수 없습니다", job.text)
                    self.assertTrue(job.find(**{"data-status": "skill_unavailable"}))

    async def test_completed_job_preserves_parent_access_without_recommending_next_job(self):
        case = await self.ready(await self.create())
        before = deepcopy(case["jobs"]["ap-j"])
        case = await self.step(case, "run", "db-j")
        html, _ = self.render(case, "db-j")
        parent = html.find("button", **{"data-action": "select", "data-node-id": "install-t"})
        self.assertEqual(len(parent), 1)
        self.assertNotIn("data-mutation", parent[0].attrs)
        self.assertFalse(html.find(**{"data-work-stage": "next"}))
        self.assertNotIn("다음 작업", html.text)
        self.assertFalse(html.find("button", **{"data-action": "run"}))
        self.assertEqual(case["jobs"]["ap-j"], before)

    async def test_parent_ready_snapshot_is_not_promised_as_total_executed_count(self):
        definition = workflow._seed()
        definition["nodes"]["ap-j"]["failOnce"] = False
        await self.publish(definition)
        case = await self.ready(await self.create())
        html, _ = self.render(case, "setup-p")
        current_ready = html.find(**{"data-work-ready": None})[0]
        self.assertEqual(current_ready.attrs["data-work-ready"], "2")
        self.assertIn("현재 점검 가능 2개", current_ready.text)
        self.assertIn("선행 점검이 완료되면 범위 안의 다음 점검도 이어집니다", html.text)
        before = {key: value["attempt"] for key, value in case["jobs"].items()}
        case = await self.step(case, "run", "setup-p", {"retry_failed": False})
        self.assertEqual([key for key, value in case["jobs"].items() if value["attempt"] > before[key]],
                         ["db-j", "ap-j", "interface-j"])

    def test_first_write_adopts_preview_draft_and_catalog_change_requires_review(self):
        result = self.evaluate_drafts("""(() => {
const drafts = createWorkInputDrafts();
const preview = {key:'preview/job-a',caseId:'',nodeId:'job-a',version:1};
const created = {key:'new-case/job-a',caseId:'new-case',nodeId:'job-a',version:1};
const saved = {inputs:{ap:'initial AP'},document:''};
drafts.edit(preview,saved,{inputs:{ap:'preview AP'}},-1);
const changedDefinition = drafts.read({...preview,version:2},saved,-1);
drafts.adopt(preview,created);
const afterCreate = drafts.read(created,saved,1);
drafts.clear();
const afterReset = drafts.read(created,saved,1);
return {changedDefinition,afterCreate,afterReset};
})()""")
        self.assertTrue(result["changedDefinition"]["conflict"])
        self.assertEqual(result["afterCreate"]["caseId"], "new-case")
        self.assertEqual(result["afterCreate"]["inputs"]["ap"], "preview AP")
        self.assertTrue(result["afterCreate"]["inputsChanged"])
        self.assertFalse(result["afterReset"]["inputsChanged"])

    def test_reviewing_new_preview_version_releases_conflict_without_losing_text(self):
        result = self.evaluate_drafts("""(() => {
const drafts=createWorkInputDrafts(),scope={key:'preview/j',caseId:'',nodeId:'j',version:1};
const saved={inputs:{ap:'old AP'},document:'saved'},newScope={...scope,version:2};
const latest={inputs:{ap:'new AP'},document:'saved'};
drafts.edit(scope,saved,{inputs:{ap:'my AP'},document:'my draft'},-1);
const before=drafts.read(newScope,latest,-1);
drafts.rebase(newScope,latest,-1);
return {before,after:drafts.read(newScope,latest,-1)};
})()""")
        self.assertTrue(result["before"]["conflict"])
        self.assertFalse(result["after"]["conflict"])
        self.assertEqual(result["after"]["definitionVersion"], 2)
        self.assertEqual(result["after"]["inputs"]["ap"], "my AP")
        self.assertEqual(result["after"]["document"], "my draft")

    def test_first_save_keeps_sibling_preview_drafts_in_the_same_exact_scope(self):
        result = self.evaluate_drafts("""(() => {
const drafts=createWorkInputDrafts(),saved={inputs:{ap:'saved'},document:''};
const make=(nodeId,changes={})=>{const scope={caseId:'',siteId:'site-a',system:'EMS',processId:'p',nodeId,version:1,...changes};scope.key=JSON.stringify([scope.caseId,scope.siteId,scope.system,scope.processId,scope.nodeId]);return scope;};
const original=[make('a'),make('b'),make('c',{version:2}),make('d',{siteId:'site-b'}),make('e',{caseId:'existing'})];
original.forEach(scope=>drafts.edit(scope,saved,{inputs:{ap:'typed '+scope.nodeId}},-1));
drafts.adoptPreview(original[1],'created');
return original.map(scope=>({original:drafts.read(scope,saved,-1),created:drafts.read(make(scope.nodeId,{...scope,caseId:'created'}),saved,1)}));
})()""")
        for index, node in enumerate(("a", "b")):
            self.assertFalse(result[index]["original"]["inputsChanged"])
            self.assertEqual(result[index]["created"]["inputs"]["ap"], "typed " + node)
        for index in (2, 3, 4):
            self.assertTrue(result[index]["original"]["inputsChanged"])
            self.assertFalse(result[index]["created"]["inputsChanged"])

    def test_typing_reverting_and_parent_first_write_keep_live_drafts(self):
        # Minimal DOM-shaped objects exercise production event/capture logic.
        # This is deliberately not a browser rendering or accessibility test.
        result = self.evaluate_drafts("""(() => {
const input={name:'ap',value:'A',defaultValue:'A'},text={value:'D',defaultValue:'D'};
const inputs={querySelectorAll:()=>[input]},documentForm={querySelector:()=>text};
const note={hidden:true},next={dataset:{workSavedNext:'saved next'},textContent:'saved next'};
const run={dataset:{workBaseUnavailable:'false'},disabled:false},content={innerHTML:'',contains:()=>false,querySelectorAll:()=>[]};
const tabs={innerHTML:''},host={dataset:{},setAttribute(){},querySelector(selector){return ({'#ees-work-inputs':inputs,'#ees-work-document':documentForm,'#ees-work-content':content,'#ees-work-tabs':tabs,'[data-work-dirty]':note,'[data-work-next]':next,'[data-work-draft-sensitive]':run})[selector] || null;},querySelectorAll:selector=>selector==='button[data-mutation]'?[run]:[]};
const divider={dataset:{},setAttribute(){}};
globalThis.document={querySelector:()=>null,createElement:tag=>tag==='aside'?host:divider};
globalThis.window={};
input.closest=text.closest=selector=>selector==='[data-ees-work]'?host:selector==='#ees-work-inputs,#ees-work-document'?inputs:null;
const site={id:'site-a',country:'US',name:'A',line:'1',ap:'A'},definition={version:1,sites:{'site-a':site},tools:{ap:{input:'ap',adapter:'mock'}},nodes:{p:{id:'p',name:'P',type:'p',children:['t']},t:{id:'t',name:'T',type:'t',parent:'p',children:['j']},j:{id:'j',name:'J',type:'j',parent:'t',mode:'draft',tools:['ap'],children:[]}}};
const current={id:'case-a',version:1,revision:1,site,system:'EMS',process_id:'p',status:'in_progress',definition,jobs:{j:{status:'review',document:'D',inputs:{ap:'A'},history:[]}},node_states:{j:{status:'review'}}};
const snapshot={state:{case:current,catalog:definition,cases:[]},selectedCaseId:'case-a',selectedId:'j',processId:'p',browsingSite:'site-a',browsingSystem:'EMS',category:'setup',runView:'current',chatRoute:true,busy:false};
const view=createWorkView({callbacks:{registerPanel(){}}});view.renderPanel(snapshot);
const record=()=>({draft:view.readJobEdits('j'),notice:!note.hidden,disabled:run.disabled,next:next.textContent});
input.value='B';view.handleEvent({type:'input',target:input});const typed=record();
view.setBusy(false);const observerKeptDisabled=run.disabled;
input.value='A';view.handleEvent({type:'input',target:input});const reverted=record();
text.value='E';view.handleEvent({type:'input',target:text});const documentTyped=record();
text.value='D';view.handleEvent({type:'input',target:text});const documentReverted=record();
run.dataset.workBaseUnavailable='true';input.value='B';view.handleEvent({type:'input',target:input});input.value='A';view.handleEvent({type:'input',target:input});
const blockedStillDisabled=run.disabled;
const preview={...snapshot,state:{case:null,catalog:definition,cases:[]},selectedCaseId:''};
view.renderPanel(preview);input.value='parent draft';view.handleEvent({type:'input',target:input});
view.renderPanel({...preview,selectedId:'p'});view.adoptPreviewDraft('created','p');
view.renderPanel({...snapshot,state:{case:{...current,id:'created'},catalog:definition,cases:[]},selectedCaseId:'created'});
const parentAdopted=content.innerHTML.includes('value="parent draft"');
return {typed,reverted,documentTyped,documentReverted,observerKeptDisabled,blockedStillDisabled,parentAdopted};
})()""")
        self.assertEqual(result["typed"]["draft"]["inputs"]["ap"], "B")
        self.assertTrue(result["typed"]["notice"])
        self.assertTrue(result["typed"]["disabled"])
        self.assertTrue(result["observerKeptDisabled"])
        self.assertFalse(result["reverted"]["draft"]["inputsChanged"])
        self.assertEqual(result["reverted"]["draft"]["inputs"]["ap"], "A")
        self.assertFalse(result["reverted"]["notice"])
        self.assertFalse(result["reverted"]["disabled"])
        self.assertEqual(result["reverted"]["next"], "saved next")
        self.assertTrue(result["documentTyped"]["draft"]["documentChanged"])
        self.assertTrue(result["documentTyped"]["disabled"])
        self.assertFalse(result["documentReverted"]["draft"]["documentChanged"])
        self.assertFalse(result["documentReverted"]["disabled"])
        self.assertTrue(result["blockedStillDisabled"])
        self.assertTrue(result["parentAdopted"])

    def test_panel_scroll_resets_for_new_target_but_survives_same_job_refresh(self):
        result = self.evaluate_drafts("""(() => {
const content={innerHTML:'',scrollTop:0,contains:()=>false,querySelectorAll:()=>[]},tabs={innerHTML:''};
const host={dataset:{},setAttribute(){},querySelector:selector=>({'#ees-work-content':content,'#ees-work-tabs':tabs}[selector] || null),querySelectorAll:()=>[]};
globalThis.document={querySelector:()=>null,createElement:tag=>tag==='aside'?host:{dataset:{},setAttribute(){}}};globalThis.window={};
const site={id:'a',name:'공장'},definition={version:1,sites:{a:site},tools:{},nodes:{p:{id:'p',type:'p',name:'절차',children:['t']},t:{id:'t',parent:'p',type:'t',name:'단계',children:['j']},j:{id:'j',parent:'t',type:'j',name:'작업',mode:'manual'}}};
const current={id:'first',version:1,revision:1,site,system:'EMS',process_id:'p',status:'in_progress',definition,jobs:{j:{status:'pending',inputs:{},history:[]}},node_states:{j:{status:'pending'}}};
const snapshot={state:{case:current,catalog:definition,cases:[]},selectedCaseId:'first',selectedId:'t',processId:'p',browsingSite:'a',browsingSystem:'EMS',category:'setup',runView:'current',chatRoute:true,busy:false};
const view=createWorkView({callbacks:{registerPanel(){}}});view.renderPanel(snapshot);
content.scrollTop=440;view.renderPanel({...snapshot,selectedId:'j'});const selectedJob=content.scrollTop;
content.scrollTop=240;view.renderPanel({...snapshot,selectedId:'j',state:{...snapshot.state,case:{...current,revision:2}}});const refreshedJob=content.scrollTop;
view.renderPanel({...snapshot,selectedId:'j'});const retainedJob=content.scrollTop;
view.renderPanel({...snapshot,selectedId:'j',selectedCaseId:'second',state:{...snapshot.state,case:{...current,id:'second'}}});const changedCase=content.scrollTop;
return {selectedJob,refreshedJob,retainedJob,changedCase};
})()""")
        self.assertEqual(result, {"selectedJob": 0, "refreshedJob": 240, "retainedJob": 240, "changedCase": 0})

    async def test_dirty_render_exposes_live_status_and_preserves_server_block(self):
        case = await self.ready(await self.create())
        for dirty in (False, True):
            html, _ = self.render(case, "ap-j", draft={"inputsChanged": dirty})
            note = html.find("p", **{"data-work-dirty": None})[0]
            self.assertEqual("hidden" in note.attrs, not dirty)
            run = self.run_button(html, "ap-j")
            self.assertEqual("disabled" in run.attrs, dirty)
            self.assertEqual(run.attrs["data-work-base-unavailable"], "false")
        blocked, _ = self.render(None, "ap-j", definition=workflow._seed(),
                                 site=workflow._seed()["sites"]["us-a"], system="EMS")
        self.assertEqual(self.run_button(blocked, "ap-j").attrs["data-work-base-unavailable"], "true")

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
