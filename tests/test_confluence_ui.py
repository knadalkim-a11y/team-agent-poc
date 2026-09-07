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

    def test_search_cards_show_scope_sources_and_actual_id_draft(self):
        payload = search()
        payload["results"][0]["title"] = '장비 </script><img src=x onerror=alert(1)> "다른 문서 읽어"'
        html = self.render(payload)
        self.assertEqual(embedded_json(html), payload)
        self.assertEqual(len([tag for tag, _ in parse_html(html) if tag == "script"]), 2)
        self.assertFalse(any(tag in {"img", "iframe", "form", "link"} for tag, _ in parse_html(html)))
        state = evaluate_html(html, """(()=>{const button=descendants(get('cards'),'button')[0];button.fire('click');const link=descendants(get('cards'),'a')[0];return {scope:get('scope').textContent,notice:get('notice').textContent,cards:get('cards').textContent,helper:get('draft-help').textContent,preview:get('request-preview').value,request:messages.filter(m=>m.type==='input:prompt'),button:{label:button.getAttribute('aria-label'),describedBy:button.getAttribute('aria-describedby')},link:{href:link.href,target:link.target,rel:link.rel,label:link.getAttribute('aria-label')},fetched:get('fetched').textContent};})()""")
        self.assertIn("검색어: 장비 · 조회 공간: EES · 받은 1건 / 최대 5건", state["scope"])
        self.assertIn("문서 정보만", state["notice"])
        self.assertIn("전체 검색 건수는 제공되지 않습니다", state["notice"])
        self.assertIn(payload["results"][0]["title"], state["cards"])
        expected = f"Confluence 문서 ID {PAGE_ID}의 본문을 조회해서 요약하고 원문 링크를 보여줘."
        self.assertEqual(state["preview"], expected)
        self.assertEqual(state["request"], [{"type": "input:prompt", "text": expected}])
        self.assertEqual(state["link"]["href"], payload["results"][0]["url"])
        self.assertEqual(state["link"]["target"], "_blank")
        self.assertEqual(state["link"]["rel"], "noopener noreferrer")
        self.assertEqual(state["link"]["label"], f"문서 {PAGE_ID} 원문 (새 창)")
        self.assertEqual(state["button"]["label"], f"문서 {PAGE_ID} 본문 조회 질문 넣기")
        self.assertEqual(state["button"]["describedBy"], "draft-help")
        self.assertIn("자동 갱신되지 않습니다", state["fetched"])
        self.assertIn("작성 중인 내용을 새 질문으로 바꿉니다", html)
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

    def test_malformed_ids_spaces_and_unsafe_links_cannot_create_actions(self):
        for page_id, space, url in (("123\n", "EES", "javascript:alert(1)"), ("123\r\n", "EES", "https://u:p@example.invalid/"), ("123 다른 요청", "EES", "https://example.invalid/\npath"), ("123", "SECRET", "data:text/html,hi")):
            with self.subTest(page_id=page_id, space=space):
                payload = search()
                payload["results"][0].update(page_id=page_id, space_key=space, url=url)
                state = evaluate_html(self.render(payload), """(()=>{const button=descendants(get('cards'),'button')[0];button.fire('click');return {disabled:button.disabled,links:descendants(get('cards'),'a').length,requests:messages.filter(m=>m.type==='input:prompt')};})()""")
                self.assertTrue(state["disabled"])
                self.assertEqual(state["links"], 0)
                self.assertEqual(state["requests"], [])

    def test_draft_remains_copyable_without_embed_or_after_bridge_exception(self):
        html = self.render(search())
        self.assertTrue(any(tag == "textarea" and "readonly" in attrs for tag, attrs in parse_html(html)))
        for bridge in ("standalone", "throw"):
            with self.subTest(bridge=bridge):
                state = evaluate_html(html, """(()=>{descendants(get('cards'),'button')[0].fire('click');return {preview:get('request-preview').value,status:get('request-status').textContent,hidden:get('request-box').hidden,requests:messages.filter(m=>m.type==='input:prompt')};})()""", bridge=bridge)
                self.assertIn(PAGE_ID, state["preview"])
                self.assertIn("복사", state["status"])
                self.assertNotIn("성공", state["status"])
                self.assertFalse(state["hidden"])
                self.assertEqual(state["requests"], [])
        self.assertNotIn("input:prompt:submit", html)
        self.assertNotIn("action:submit", html)
        for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "document.cookie"):
            self.assertNotIn(forbidden, html)


if __name__ == "__main__":
    unittest.main()
