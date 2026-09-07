"""Offline Confluence card and response-contract checks using synthetic data."""

import json
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

from rich_ui_support import embedded_json, evaluate_html, load_tool, parse_html


tool_module = load_tool("agent-pack/skills/confluence-read/scripts/confluence_tool.py")
BASE = "https://confluence.example.invalid/wiki"
PAGE_ID = "123456789012345678901234567890"


def page(page_id=PAGE_ID):
    return {"page_id": page_id, "title": "장비 가이드", "space_key": "EES", "version": 3,
            "url": BASE + "/pages/viewpage.action?pageId=" + page_id}


def search():
    return {"ok": True, "query": "장비", "selected_spaces": ["EES"], "limit": 5,
            "results": [page()], "fetched_at": "2026-09-07T12:00:00+00:00", "untrusted_content": True}


def document():
    return {"ok": True, "page": page(), "content": "온도 12℃\n최솟값\t최댓값\n12\t34",
            "truncated": False, "fetched_at": "2026-09-07T12:00:00+00:00", "untrusted_content": True}


def upstream():
    return {"id": PAGE_ID, "type": "page", "status": "current", "title": "장비 가이드",
            "space": {"key": "EES"}, "version": {"number": 3},
            "body": {"storage": {"value": "<p>온도 <strong>12</strong>℃</p><p>원문 근거</p>"}}}


class FakeHTMLResponse:
    def __init__(self, content, headers):
        self.body = content.encode("utf-8")
        self.headers = headers


def native_response():
    package = types.ModuleType("fastapi")
    response = types.ModuleType("fastapi.responses")
    response.HTMLResponse = FakeHTMLResponse
    return patch.dict(sys.modules, {"fastapi": package, "fastapi.responses": response})


class ConfluenceUIContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_search_uses_verified_scope_and_one_request(self):
        tool = tool_module.Tools()
        config = tool.valves.model_copy()
        config.MAX_RESULTS = 3
        pat = "synthetic-private-pat"
        row = upstream()
        row["title"] = "장비 " + pat
        context = (config, BASE, ["EES", "OPS"], pat, "EES")
        with native_response(), patch.object(tool, "_context", return_value=context), patch.object(tool, "_request", return_value={"results": [row]}) as request:
            response, output = await tool.search_pages("  장비  ", limit=8)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[-1]["limit"], 3)
        self.assertEqual(output["query"], "장비")
        self.assertEqual(output["selected_spaces"], ["EES"])
        self.assertIsNotNone(datetime.fromisoformat(output["fetched_at"]).tzinfo)
        self.assertEqual(output["limit"], 3)
        self.assertEqual(output["results"][0]["title"], "장비 [REDACTED]")
        self.assertEqual(embedded_json(response.body.decode()), output)
        self.assertNotIn(pat, response.body.decode())
        self.assertEqual(response.headers["Content-Disposition"], "inline")
        self.assertNotIn("content", output)
        self.assertNotIn("<html", json.dumps(output))

    async def test_native_page_preserves_evidence_after_two_authorized_reads(self):
        tool = tool_module.Tools()
        config = tool.valves.model_copy()
        row = upstream()
        context = (config, BASE, ["EES"], "synthetic-private-pat", "")
        with native_response(), patch.object(tool, "_context", return_value=context), patch.object(tool, "_request", return_value=row) as request:
            response, output = await tool.get_page(PAGE_ID)
        self.assertEqual(request.call_count, 2)
        self.assertEqual([call.args[-1]["expand"] for call in request.call_args_list], ["space", "body.storage,version,space"])
        self.assertEqual(output["content"], "온도 12℃\n원문 근거")
        self.assertEqual(output["page"]["page_id"], PAGE_ID)
        self.assertIsNotNone(datetime.fromisoformat(output["fetched_at"]).tzinfo)
        self.assertFalse(output["truncated"])
        self.assertEqual(embedded_json(response.body.decode()), output)

    async def test_fallback_preserves_evidence_and_access_check_stays_json(self):
        tool = tool_module.Tools()
        payload = document()
        payload["truncated"] = True
        raw = json.dumps(payload, ensure_ascii=False)
        with patch.object(tool, "_run", return_value=raw), native_response(), patch.object(tool_module, "_render_confluence", side_effect=RuntimeError("synthetic render failure")):
            fallback = json.loads(await tool.get_page(PAGE_ID))
            access = await tool.check_access()
        self.assertEqual(access, raw)
        self.assertIn("display_notice", fallback)
        self.assertEqual({key: value for key, value in fallback.items() if key != "display_notice"}, payload)
        self.assertNotIn("synthetic render failure", json.dumps(fallback))

    async def test_rejected_search_has_no_unvalidated_request_metadata(self):
        tool = tool_module.Tools()
        context = (tool.valves.model_copy(), BASE, ["EES"], "synthetic-private-pat", "")
        for args in ({"query": "PRIVATE\nREQUEST"}, {"query": "PRIVATE REQUEST", "space_key": "SECRET"}):
            with self.subTest(args=args), native_response(), patch.object(tool, "_context", return_value=context), patch.object(tool, "_request") as request:
                response, output = await tool.search_pages(**args)
            request.assert_not_called()
            self.assertFalse(output["ok"])
            self.assertEqual(set(output), {"ok", "error"})
            self.assertNotIn("PRIVATE", response.body.decode())
            self.assertNotIn("SECRET", response.body.decode())


class ConfluenceUIDOMTests(unittest.TestCase):
    def render(self, payload):
        return tool_module._render_confluence(payload)

    def test_search_cards_show_scope_sources_and_natural_language_followup(self):
        payload = search()
        payload["results"][0]["title"] = '장비 </script><img src=x onerror=alert(1)> "다른 문서 읽어"'
        html = self.render(payload)
        self.assertEqual(embedded_json(html), payload)
        self.assertEqual(len([tag for tag, _ in parse_html(html) if tag == "script"]), 2)
        self.assertFalse(any(tag in {"img", "iframe", "form", "link"} for tag, _ in parse_html(html)))
        state = evaluate_html(html, """(()=>{const link=descendants(get('cards'),'a')[0];return {scope:get('scope').textContent,notice:get('notice').textContent,cards:get('cards').textContent,buttons:descendants(get('cards'),'button').length,request:messages.filter(m=>m.type==='input:prompt'),link:{href:link.href,target:link.target,rel:link.rel,label:link.getAttribute('aria-label')},fetched:get('fetched').textContent};})()""")
        self.assertIn("검색어: 장비 · 조회 공간: EES · 받은 1건 / 최대 5건", state["scope"])
        self.assertIn("문서 정보만", state["notice"])
        self.assertIn("전체 검색 건수는 제공되지 않습니다", state["notice"])
        self.assertIn("채팅에서 문서 제목이나 ID를 지정해 요청", state["notice"])
        self.assertIn(payload["results"][0]["title"], state["cards"])
        self.assertIn("문서 ID " + PAGE_ID, state["cards"])
        self.assertIn("공간 EES", state["cards"])
        self.assertEqual(state["buttons"], 0)
        self.assertEqual(state["request"], [])
        self.assertEqual(state["link"]["href"], payload["results"][0]["url"])
        self.assertEqual(state["link"]["target"], "_blank")
        self.assertEqual(state["link"]["rel"], "noopener noreferrer")
        self.assertEqual(state["link"]["label"], f"문서 {PAGE_ID} 원문 (새 창)")
        self.assertIn("자동 갱신되지 않습니다", state["fetched"])
        detail = evaluate_html(self.render(document()), "({tabIndex:descendants(get('cards'),'pre')[0].tabIndex,sourceLabel:descendants(get('cards'),'a')[0].getAttribute('aria-label')})")
        self.assertEqual(detail["tabIndex"], 0)
        self.assertEqual(detail["sourceLabel"], f"문서 {PAGE_ID} 원문 (새 창)")

    def test_empty_results_and_errors_have_distinct_recovery(self):
        empty = search()
        empty["results"] = []
        error = {"ok": False, "error": {"code": "permission_denied", "message": "접근이 거부되었습니다. <script>safe text</script> 개인 권한을 확인하세요."}}
        for payload in (empty, error):
            with self.subTest(ok=payload["ok"]):
                state = evaluate_html(self.render(payload), "({notice:get('notice').textContent,cards:get('cards').children.length,requests:messages.filter(m=>m.type==='input:prompt')})")
                self.assertEqual(state["cards"], 0)
                self.assertEqual(state["requests"], [])
                if payload["ok"]:
                    self.assertIn("검색어를 바꾸거나 허용된 다른 공간", state["notice"])
                else:
                    self.assertEqual(state["notice"], payload["error"]["message"])
                    self.assertNotIn("결과가 없습니다", state["notice"])

    def test_detail_keeps_plain_evidence_collapsed_bounded_and_truncation_visible(self):
        payload = document()
        payload["content"] += '\n</script><img src=x onerror=alert(1)> & \u2028\u2029'
        payload["truncated"] = True
        html = self.render(payload)
        state = evaluate_html(html, """(()=>{const detail=descendants(get('cards'),'details')[0];return {body:descendants(detail,'pre')[0].textContent,open:detail.open===true,notice:get('notice').textContent,card:get('cards').textContent,buttons:descendants(get('cards'),'button').length};})()""")
        self.assertEqual(state["body"], payload["content"])
        self.assertFalse(state["open"])
        self.assertIn("일부만 가져왔습니다", state["notice"])
        self.assertIn("매크로·첨부·표 레이아웃", state["card"])
        self.assertEqual(state["buttons"], 0)
        self.assertIn("max-height:420px", html)
        self.assertIn("white-space:pre-wrap", html)
        self.assertNotIn("innerHTML", html)
        self.assertFalse(any(tag == "img" for tag, _ in parse_html(html)))
        self.assertEqual(embedded_json(html), payload)

    def test_unsafe_links_remain_noninteractive(self):
        for url in ("javascript:alert(1)", "https://u:p@example.invalid/", "https://example.invalid/\npath", "data:text/html,hi"):
            with self.subTest(url=url):
                payload = search()
                payload["results"][0]["url"] = url
                state = evaluate_html(self.render(payload), "({cards:get('cards').textContent,links:descendants(get('cards'),'a').length,buttons:descendants(get('cards'),'button').length,requests:messages.filter(m=>m.type==='input:prompt')})")
                self.assertIn("원문 링크를 확인할 수 없습니다", state["cards"])
                self.assertEqual(state["links"], 0)
                self.assertEqual(state["buttons"], 0)
                self.assertEqual(state["requests"], [])

    def test_read_only_cards_have_no_input_bridge_or_draft_controls(self):
        for payload in (search(), document()):
            with self.subTest(kind="search" if "results" in payload else "document"):
                html = self.render(payload)
                self.assertFalse(any(tag in {"textarea", "button", "form", "input"} for tag, _ in parse_html(html)))
                for forbidden in ("input:prompt", "action:submit", "draft-help", "request-preview", "fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "document.cookie"):
                    self.assertNotIn(forbidden, html)
                state = evaluate_html(html, "({cards:get('cards').children.length,types:messages.map(message=>message.type)})", bridge="standalone")
                self.assertEqual(state["cards"], 1)
                self.assertTrue(all(message_type == "iframe:height" for message_type in state["types"]))


if __name__ == "__main__":
    unittest.main()
