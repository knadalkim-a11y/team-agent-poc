"""V4 rendering contracts using production pure helpers and saved-state fixtures.

These tests cover data/permission boundaries; Native layout and real actions are
verified separately and are never inferred from this generated markup.
"""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "branding/ees/ui/ees-work-view.js"
NODE = r"""
const fs=require('node:fs'), vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8')),scope={input};
vm.createContext(scope);vm.runInContext(fs.readFileSync(input.source,'utf8'),scope);
const before=JSON.stringify(input);
const html=vm.runInContext('workPanelNodeHTML(input.case,input.options.definition.nodes[input.node],input.options)',scope);
process.stdout.write(JSON.stringify({html,unchanged:JSON.stringify(input)===before}));
"""


class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def matching(self, tag=None, **attrs):
        return [item for kind, item in self.tags if (tag is None or kind == tag)
                and all(item.get(key) == value for key, value in attrs.items())]


@unittest.skipUnless(shutil.which("node"), "Node is required")
class V4RenderingTests(unittest.TestCase):
    def test_layout_lifecycle_regressions(self):
        # Include the production-view transition fixture in unittest discovery.
        # Its synthetic geometry is not a Native visual acceptance result.
        result = subprocess.run(
            [shutil.which("node"), "--test", str(ROOT / "tests/test_ees_v4_layout.cjs")],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def fixture(self):
        nodes = {
            "p": {"id": "p", "name": "실제 게시 절차", "type": "p", "parent": None, "children": ["t"]},
            "t": {"id": "t", "name": "검수 단계", "type": "t", "parent": "p", "children": ["a", "b", "r", "wait1", "wait2", "wait3"]},
            "a": {"id": "a", "name": "현장 확인", "type": "j", "parent": "t", "mode": "manual", "rule": "담당자 확인"},
            "b": {"id": "b", "name": "합성 연결 점검", "type": "j", "parent": "t", "mode": "tool", "tools": ["mock"], "bindings": {"mock": "db"}, "rule": "모의 응답 통과"},
            "r": {"id": "r", "name": "공개 자료 조회", "type": "j", "parent": "t", "mode": "tool", "execution": {"kind": "fixed", "calls": []}, "rule": "저장된 결과 검증"},
        }
        for name in ("wait1", "wait2", "wait3"):
            nodes[name] = {"id": name, "name": name, "type": "j", "parent": "t", "mode": "manual", "deps": ["a"]}
        definition = {"version": 7, "nodes": nodes, "tools": {"mock": {"id": "mock", "name": "모의 연결", "adapter": "mock", "input": "db", "purpose": "모의 결과 확인"}}, "skills": {}}
        states = {key: {"status": "pending", "applicable": True} for key in nodes}
        states["b"]["block_reason"] = "input_required"
        for key in ("wait1", "wait2", "wait3"):
            states[key]["missing"] = ["a"]
        case = {"id": "case", "status": "in_progress", "version": 7, "definition": definition,
                "node_states": states, "jobs": {}, "execution_inputs": {}, "site": {"name": "합성 공장"}, "system": "EMS"}
        return case

    def render(self, case, node, **options):
        result = subprocess.run([shutil.which("node"), "-e", NODE],
                                input=json.dumps({"source": str(VIEW), "case": case, "node": node,
                                                  "options": {"definition": case["definition"], **options}}, ensure_ascii=False),
                                encoding="utf-8", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertTrue(rendered["unchanged"])
        return rendered["html"], Tags(rendered["html"])

    def test_list_real_groups_single_recommendation_and_waiting_expansion(self):
        case = self.fixture()
        html, tags = self.render(case, "t")
        self.assertEqual(html.count('class="ew-v4-first"'), 1)
        rows = tags.matching("tr", **{"class": "ew-v4-job-row"})
        self.assertEqual([row["data-node-id"] for row in rows if row["data-group"] == "waiting"], ["wait1", "wait2"])
        self.assertEqual(len(tags.matching("button", **{"data-action": "job_more", "data-group": "waiting"})), 1)
        expanded, tags = self.render(case, "t", listView={"moreWaiting": True})
        self.assertEqual(len([row for row in tags.matching("tr", **{"class": "ew-v4-job-row"}) if row["data-group"] == "waiting"]), 3)
        self.assertIn("임시 기준", html)
        self.assertNotIn('name="urgency"', html)

    def test_simulation_does_not_increase_actual_completion(self):
        case = self.fixture()
        case["node_states"]["b"]["status"] = "passed"
        case["jobs"]["b"] = {"status": "passed", "attempt": 1, "inputs": {"db": "synthetic"},
                                     "checks": [{"id": "mock", "status": "passed"}],
                                     "history": [{"kind": "simulation", "simulation": True, "status": "passed", "attempt": 1, "checks": [{"id": "mock", "status": "passed"}]}]}
        html, tags = self.render(case, "t")
        progress = tags.matching("progress", **{"aria-label": "실제 작업 완료 수"})
        self.assertEqual(progress[0]["value"], "0")
        self.assertIn("모의 통과 · 실제 미확인", html)
        self.assertEqual(tags.matching("button", **{"data-action": "job_group", "data-group": "simulation"})[0]["aria-expanded"], "false")
        detail, _ = self.render(case, "b")
        self.assertIn("실제 업무 완료는 확인하지 않았습니다", detail)

    def test_process_mock_pass_preserves_record_contract_without_real_completion(self):
        case = self.fixture()
        case["definition"]["nodes"]["t"]["children"] = ["b"]
        case["status"] = "passed"
        for key in ("p", "t", "b"):
            case["node_states"][key]["status"] = "passed"
        case["jobs"]["b"] = {"status": "passed", "attempt": 1,
                                     "history": [{"kind": "simulation", "simulation": True, "status": "passed"}]}
        html, tags = self.render(case, "p")
        self.assertEqual(tags.matching("span", **{"data-work-total": "1"})[0]["data-work-done"], "0")
        self.assertEqual(tags.matching("progress", **{"aria-label": "작업 완료 수"})[0]["value"], "0")
        self.assertTrue(tags.matching("div", **{"data-work-metric": "simulation"}))
        self.assertIn("모의 통과 포함 · 실제 미확인", html)
        self.assertIn("미완료 <strong>1개 작업", html)
        self.assertFalse(tags.matching("span", **{"data-status": "passed"}))
        self.assertFalse(tags.matching("button", **{"data-action": "run"}),
                         "A closed simulation record must not become runnable")
        completed, filtered = self.render(case, "p", listView={"filter": "completed"})
        self.assertFalse(filtered.matching("tr", **{"data-work-job": "b"}))
        case["definition"]["nodes"]["b"]["mode"] = "manual"
        case["jobs"]["b"]["history"] = [{"kind": "human_confirmation", "status": "passed"}]
        actual, tags = self.render(case, "p")
        self.assertEqual(tags.matching("span", **{"data-work-total": "1"})[0]["data-work-done"], "1")
        self.assertEqual(tags.matching("progress", **{"aria-label": "작업 완료 수"})[0]["value"], "1")
        self.assertFalse(tags.matching("div", **{"data-work-metric": "simulation"}))

    def test_native_schema_fields_and_save_are_not_an_execution(self):
        case = self.fixture()
        properties = {"text": {"type": "string", "title": "검색어"}, "limit": {"type": "integer"},
                      "accepted": {"type": "boolean"}, "items": {"type": "array"}, "scope": {"type": "object"},
                      "choice": {"type": "string", "enum": ["one", "two"]}}
        case["definition"]["nodes"]["p"]["execution_inputs"] = {"type": "object", "properties": properties, "required": ["text"]}
        case["execution_inputs"] = {"text": "public", "limit": 2, "accepted": False, "items": ["a"], "scope": {"key": "value"}, "choice": "two"}
        html, tags = self.render(case, "r")
        for key in properties:
            self.assertEqual(len(tags.matching(name=key)), 1, key)
        self.assertEqual(len(tags.matching("form", id="ees-work-inputs")), 1)
        save = tags.matching("button", id="ees-work-inputs-save")[0]
        self.assertEqual(save["type"], "submit")
        self.assertNotIn("data-action", save)
        self.assertNotIn("저장하고 점검", html)
        self.assertIn("점검 시작", html)
        self.assertIn("실행 계획 확인은 조회", html)

    def test_unknown_only_refreshes_and_failed_lookup_hides_saved_data(self):
        case = self.fixture()
        case["definition"]["nodes"]["p"]["execution_inputs"] = {"type": "object", "properties": {"text": {"type": "string"}}}
        execution = {"run": {"id": "run", "revision": 2, "status": "unknown", "node_id": "r", "inputs": {"text": "retained-private-value"},
                             "jobs": {"r": {"status": "unknown", "kind": "fixed", "validation": {"status": "unknown"}}}, "calls": []}}
        html, tags = self.render(case, "r", execution=execution)
        self.assertFalse(tags.matching("button", **{"data-action": "run"}))
        self.assertFalse(tags.matching("button", **{"data-action": "execution_control"}))
        self.assertTrue(tags.matching("button", **{"data-action": "execution_refresh"}))
        self.assertIn("판정 미확인", html)
        failed, tags = self.render(case, "r", execution=execution, executionError="조회 실패")
        self.assertNotIn("retained-private-value", failed)
        self.assertNotIn("ew-v4-info", failed)
        self.assertFalse(tags.matching("form"))

    def test_ai_receipt_is_draft_scoped_and_escaped(self):
        case = self.fixture()
        draft = {"inputs": {"db": "public-target"}, "inputsChanged": True,
                 "aiReceipt": {"proposalId": "p1", "source": "<registered source>", "changedFields": ["db"], "undone": False}}
        html, tags = self.render(case, "b", draft=draft)
        self.assertIn("저장 필요", html)
        self.assertIn("&lt;registered source&gt;", html)
        self.assertEqual(len(tags.matching("button", **{"data-action": "undo_ai_draft", "data-proposal-id": "p1"})), 1)
        draft["aiReceipt"]["undone"] = True
        undone, tags = self.render(case, "b", draft=draft)
        self.assertFalse(tags.matching("button", **{"data-action": "undo_ai_draft"}))

    def test_search_and_group_state_are_applied_without_mutating_records(self):
        case = self.fixture()
        original = deepcopy(case)
        html, tags = self.render(case, "t", listView={"query": "현장", "sort": "procedure", "assignee": "unassigned", "groups": {"todo": False}})
        self.assertEqual(tags.matching("input", id="ees-work-job-search")[0]["value"], "현장")
        self.assertFalse(tags.matching("tr", **{"class": "ew-v4-job-row"}))
        self.assertEqual(tags.matching("button", **{"data-action": "job_group", "data-group": "todo"})[0]["aria-expanded"], "false")
        self.assertEqual(case, original)


if __name__ == "__main__":
    unittest.main()
