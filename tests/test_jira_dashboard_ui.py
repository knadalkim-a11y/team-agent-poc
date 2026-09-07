"""Synthetic offline renderer checks; these do not establish browser/WebUI behavior."""

import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


TOOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent-pack/skills/jira-read/scripts/jira_tool.py"
)
SPEC = importlib.util.spec_from_file_location("ees_jira_ui_test_target", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool_module)


def fixture():
    return {
        "ok": True, "status": "complete",
        "started_at": "2026-09-07T01:00:00Z", "fetched_at": "2026-09-07T01:00:03Z",
        "scope": {"project_keys": ["ALPHA", "BETA"], "visibility": "current_user"},
        "projects": [
            {"key": "ALPHA", "ok": True, "total": 200, "open": 120},
            {"key": "BETA", "ok": True, "total": 20, "open": 5},
        ],
        "summary": {"total": 220, "open": 125, "available_total": 220,
                    "available_open": 125, "complete": True},
        "issues": [
            {"key": "ALPHA-7", "project_key": "ALPHA", "summary": "Synthetic task",
             "status": "진행 중", "status_category": "indeterminate", "assignee": "테스트 A",
             "assignee_id": "test-user-a", "assignee_known": True,
             "priority": "Medium", "priority_known": True,
             "updated": "2026-09-07T01:00:00Z", "due_date": None, "due_date_known": True,
             "url": "https://jira.example.invalid/browse/ALPHA-7"},
            {"key": "ALPHA-6", "project_key": "ALPHA", "summary": "Synthetic second task",
             "status": "완료", "status_category": "done", "assignee": None,
             "assignee_id": None, "assignee_known": True,
             "priority": None, "priority_known": True,
             "updated": None, "due_date": None, "due_date_known": True,
             "url": "https://jira.example.invalid/browse/ALPHA-6"},
        ],
        "listing": {"ok": True, "total": 220, "returned": 2,
                    "start_at": 0, "next_start_at": 2},
        "notice": "합성 데이터", "untrusted_content": True,
    }


class ParsedHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


# A deliberately small DOM stub checks text/data flow and click filtering only.
# CSS, layout, iframe sandboxing and real events require browser/WebUI acceptance.
NODE_HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.value='';this.style={};this.attrs={};this.events={};this._text='';this.classList={add:()=>{}};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this._text='';}
  setAttribute(key,value){this.attrs[key]=value;}
  addEventListener(name,handler){this.events[name]=handler;}
  getBoundingClientRect(){return {height:900};}
  fire(name){this.events[name]();}
}
const elements={};
const get=id=>elements[id]||(elements[id]=new Element('div'));
get('jira-data').textContent=input.data;
const messages=[];
const context=vm.createContext({URL,Date,console,document:{getElementById:get,createElement:tag=>new Element(tag),querySelector:()=>get('main'),addEventListener:()=>{}},window:{parent:{postMessage:message=>messages.push(message)},addEventListener:()=>{}},requestAnimationFrame:handler=>handler(),get,messages});
vm.runInContext(input.script,context);
const result=vm.runInContext(input.action,context);
process.stdout.write(JSON.stringify(result));
"""


class JiraDashboardSafetyTests(unittest.TestCase):
    def test_untrusted_text_cannot_close_json_script(self):
        payload = fixture()
        hostile = '</script><img src=x onerror="alert(1)">&\u2028\u2029'
        payload["issues"][0]["summary"] = hostile
        payload["notice"] = hostile
        html = tool_module._render_dashboard(payload)
        self.assertNotIn(hostile, html)
        tags = ParsedHTML(html).tags
        self.assertEqual(sum(tag == "script" for tag, _ in tags), 2)
        self.assertFalse(any(tag in {"img", "iframe", "object", "embed"} for tag, _ in tags))
        embedded = re.search(r'id="jira-data">(.*?)</script>', html, re.S).group(1)
        self.assertEqual(json.loads(embedded), payload)
        self.assertNotRegex(embedded, r"[<>&\u2028\u2029]")

    def test_fixed_template_has_no_network_or_html_insertion(self):
        html = tool_module._render_dashboard(fixture())
        tags = ParsedHTML(html).tags
        for _, attrs in tags:
            self.assertFalse(any(name.startswith("on") for name in attrs))
            self.assertNotIn("src", attrs)
        self.assertNotRegex(html, r"\.innerHTML\s*=|document\.write\(|\bfetch\(|XMLHttpRequest|WebSocket")
        self.assertIn("default-src 'none'", html)
        self.assertIn(".textContent=", html)


@unittest.skipUnless(shutil.which("node"), "Node unavailable: offline JS behavior checks skipped")
class JiraDashboardDOMTests(unittest.TestCase):
    def evaluate(self, payload, action):
        html = tool_module._render_dashboard(payload)
        embedded = re.search(r'id="jira-data">(.*?)</script>', html, re.S).group(1)
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        result = subprocess.run(
            ["node", "-e", NODE_HARNESS],
            input=json.dumps({"data": embedded, "script": script, "action": action}),
            text=True, capture_output=True, timeout=10, check=True,
        )
        return json.loads(result.stdout)

    def test_exact_project_counts_are_independent_of_received_list(self):
        result = self.evaluate(fixture(), """({
            total:get('total').textContent,open:get('open').textContent,
            project:get('projects').children[0].textContent,
            listing:get('listing-meta').textContent,selection:get('selection').textContent,
            next:get('next').textContent,height:messages[0]
        })""")
        self.assertEqual(result["total"], "220건")
        self.assertEqual(result["open"], "125건")
        self.assertIn("전체 200건", result["project"])
        self.assertIn("미완료 120건", result["project"])
        self.assertIn("이번에 받은 2건", result["listing"])
        self.assertIn("화면에 2건", result["selection"])
        self.assertIn("시작 위치 2", result["next"])
        self.assertEqual(result["height"], {"type": "iframe:height", "height": 900})

    def test_failed_project_is_not_zero_or_complete_total(self):
        payload = fixture()
        payload["status"] = "partial"
        payload["projects"][1] = {"key": "BETA", "ok": False, "total": None, "open": None}
        payload["summary"] = {"total": None, "open": None, "available_total": 200,
                              "available_open": 120, "complete": False}
        result = self.evaluate(payload, """({total:get('total').textContent,
            note:get('total-note').textContent,project:get('projects').children[1].textContent})""")
        self.assertEqual(result["total"], "전체 집계 미완료")
        self.assertIn("집계 성공 프로젝트만: 200건", result["note"])
        self.assertIn("집계 실패", result["project"])
        self.assertIn("0건이 아닙니다", result["project"])

    def test_project_filter_does_not_claim_unloaded_project_is_empty(self):
        result = self.evaluate(fixture(), """get('projects').children[1].fire('click');
            ({issues:get('issues').textContent,total:get('total').textContent,title:get('list-title').textContent})""")
        self.assertIn("BETA 이슈가 이번 목록에 없습니다", result["issues"])
        self.assertIn("프로젝트에 이슈가 없다는 뜻은 아닙니다", result["issues"])
        self.assertEqual(result["total"], "220건")
        self.assertIn("BETA", result["title"])

    def test_status_assignee_filters_and_reset_use_only_received_data(self):
        result = self.evaluate(fixture(), """
            get('status').value=String(statuses.indexOf('완료'));get('status').fire('change');
            const afterStatus=get('issues').textContent;
            get('assignee').value=JSON.stringify(['none']);get('assignee').fire('change');
            const afterAssignee=get('issues').textContent;
            get('reset').fire('click');
            ({afterStatus,afterAssignee,reset:get('issues').textContent})""")
        self.assertIn("ALPHA-6", result["afterStatus"])
        self.assertNotIn("ALPHA-7", result["afterStatus"])
        self.assertIn("ALPHA-6", result["afterAssignee"])
        self.assertIn("ALPHA-7", result["reset"])
        self.assertIn("ALPHA-6", result["reset"])

    def test_same_display_name_keeps_distinct_assignee_filters(self):
        payload = fixture()
        for issue, user_id in zip(payload["issues"], ["test-user-a", "test-user-b"]):
            issue.update(assignee="같은 이름", assignee_id=user_id, assignee_known=True)
        result = self.evaluate(payload, """
            const labels=get('assignee').children.map(option=>option.textContent);
            get('assignee').value=JSON.stringify(['user','test-user-b']);get('assignee').fire('change');
            ({labels,issues:get('issues').textContent})""")
        self.assertIn("같은 이름 (test-user-a)", result["labels"])
        self.assertIn("같은 이름 (test-user-b)", result["labels"])
        self.assertIn("ALPHA-6", result["issues"])
        self.assertNotIn("ALPHA-7", result["issues"])

    def test_missing_metadata_is_distinct_from_explicit_null(self):
        payload = fixture()
        payload["issues"][0].update(
            assignee="검증되지 않은 표시 이름", assignee_id=None, assignee_known=False,
            priority=None, priority_known=False, due_date=None, due_date_known=False,
        )
        result = self.evaluate(payload, """
            const labels=get('assignee').children.map(option=>option.textContent);
            get('assignee').value=JSON.stringify(['unknown']);get('assignee').fire('change');
            const unknown=get('issues').textContent;
            get('assignee').value=JSON.stringify(['none']);get('assignee').fire('change');
            ({labels,unknown,unassigned:get('issues').textContent})""")
        self.assertIn("담당자 미확인", result["labels"])
        self.assertIn("담당자 없음", result["labels"])
        self.assertIn("ALPHA-7", result["unknown"])
        self.assertNotIn("ALPHA-6", result["unknown"])
        self.assertIn("담당자담당자 미확인", result["unknown"])
        self.assertIn("우선순위미확인", result["unknown"])
        self.assertIn("기한미확인", result["unknown"])
        self.assertNotIn("검증되지 않은 표시 이름", result["unknown"])
        self.assertIn("ALPHA-6", result["unassigned"])
        self.assertNotIn("ALPHA-7", result["unassigned"])
        self.assertIn("담당자담당자 없음", result["unassigned"])
        self.assertIn("우선순위없음", result["unassigned"])
        self.assertIn("기한없음", result["unassigned"])

    def test_link_protocol_and_url_credentials_are_rejected(self):
        result = self.evaluate(fixture(), """[
            safeUrl('javascript:alert(1)'),safeUrl('data:text/html,test'),
            safeUrl('//jira.example.invalid/browse/ALPHA-7'),
            safeUrl('https://user:secret@jira.example.invalid/browse/ALPHA-7'),
            safeUrl('https://jira.example.invalid/browse/ALPHA-7')
        ]""")
        self.assertEqual(result[:4], [None, None, None, None])
        self.assertEqual(result[4], "https://jira.example.invalid/browse/ALPHA-7")

    def test_listing_failure_is_distinct_from_successful_project_counts(self):
        payload = fixture()
        payload["issues"] = []
        payload["listing"] = {"ok": False, "total": None, "returned": 0, "next_start_at": None}
        result = self.evaluate(payload, """({total:get('total').textContent,
            meta:get('listing-meta').textContent,empty:get('issues').textContent})""")
        self.assertEqual(result["total"], "220건")
        self.assertIn("이슈 목록 조회 실패", result["meta"])
        self.assertIn("채팅에서 다시 조회", result["empty"])


if __name__ == "__main__":
    unittest.main()
