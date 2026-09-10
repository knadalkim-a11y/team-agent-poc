"""Actual Chrome cascade checks on a native-DOM fixture, not a WebUI app test.

Uses CSS/fonts from the built pinned wheel and the existing panel style blocks.
No Open WebUI import, user data, npm dependency, or external page is involved.
EES_TEST_CHROME makes Chrome and EES_TEST_BRANDING_DIR mandatory in Linux CI.
"""

import functools
import html
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_result = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "pre" and dict(attrs).get("id") == "ees-theme-result":
            self.in_result = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_result = False

    def handle_data(self, data):
        if self.in_result:
            self.parts.append(data)


class FixtureHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, assets, **kwargs):
        self.assets = assets
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        content = self.assets.get(path)
        if content is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


def panel_styles():
    """Read real constant styles; do not duplicate their :host declarations."""
    paths = (
        ROOT / "agent-pack/skills/cross-system-analysis/ui/cooperation-panel.js",
        ROOT / "agent-pack/skills/ems-work-order/scripts/wo_demo_tool.py",
    )
    styles = []
    for path in paths:
        match = re.search(r"<style>(.*?)</style>", path.read_text(encoding="utf-8"), re.DOTALL)
        if match is None:
            raise AssertionError(f"Panel style template was not found: {path.name}")
        styles.append(match.group(1))
    return styles


# Classes and IDs below follow pinned 0.11.3 Chat, MessageInput and Messages
# templates. Only layout-bearing wrappers needed for cascade checks are included.
FIXTURE = """<!doctype html><html class="__MODE__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">__STYLES__</head>
<body><div class="flex w-full">
<aside id="sidebar" class="hidden md:flex w-64 shrink-0"><span>대화 목록</span></aside>
<main id="chat-container" class="flex flex-col min-w-0 w-full">
<nav><div><button>EES 통합 Assistant</button></div><div id="navbar-bg-gradient-to-b"></div></nav>
<div id="chat-pane" class="flex flex-col flex-auto w-full overflow-auto">
<div id="messages-container" class="flex flex-col w-full max-w-full overflow-auto">
<div class="message-listitem flex flex-col px-3.5 mb-3 w-full max-w-[58rem] mx-auto">
<div class="chat-user"><div class="flex justify-end pb-1"><div id="user-bubble" class="rounded-3xl max-w-[90%] px-4 py-1.5 bg-gray-50 dark:bg-gray-850">
<div class="markdown-prose">조립 2라인의 개선 기회를 찾아줘.</div></div></div></div></div>
<div id="answer-row" class="message-listitem flex flex-col px-3.5 mb-3 w-full max-w-[58rem] mx-auto">
<div class="chat-assistant"><div id="answer" class="markdown-prose">
<h1 id="answer-heading">정비 후 재개 구간을 확인하세요.</h1>
<p id="answer-text">정비 이력과 운전 조건을 비교했습니다. <a id="answer-link" href="#evidence">판단 근거</a></p>
<pre><code id="answer-code">SELECT equipment_id FROM approved_view;</code></pre>
<span id="answer-math" class="katex">x + y</span>
</div></div></div></div>
<div class="w-full max-w-[58rem] mx-auto"><div id="message-input-container" class="border rounded-3xl bg-gray-50">
<div class="px-2 relative"><div id="chat-input-container"><div id="chat-input" contenteditable="true">다음에 확인할 내용을 입력하세요.</div></div></div>
</div></div></div></main></div>
<aside id="ees-cooperation-panel" style="width:480px;max-width:100%"></aside>
<aside id="ees-wo-demo-panel"></aside>
<pre id="ees-theme-result" hidden></pre>
<script>
(async () => {
  const output = document.getElementById('ees-theme-result');
  try {
    const styles = __PANEL_STYLES__;
    const analysis = document.getElementById('ees-cooperation-panel').attachShadow({mode:'open'});
    analysis.innerHTML = '<style>' + styles[0] + '</style><section class="frame"><p id="text" class="reply">분석 결과</p><button id="button">판단 근거</button><p id="muted" class="muted">추가 확인</p><span id="accent" class="pill">진행 중</span></section>';
    const wo = document.getElementById('ees-wo-demo-panel').attachShadow({mode:'open'});
    wo.innerHTML = '<style>' + styles[1] + '</style><div class="panel"><p id="text">설비 조회</p><input id="input" value="조립 2라인"><p id="muted" class="eyebrow">작업 정보</p><span id="accent" class="origin">확인됨</span></div>';
    const loaded = await Promise.all([
      document.fonts.load('400 14px "EES Inter"', 'EES 0123'),
      document.fonts.load('500 14px "EES Noto Sans KR"', '조립 개선'),
    ]);
    await document.fonts.ready;
    const style = element => {
      const s = getComputedStyle(element);
      return {font:s.fontFamily, size:s.fontSize, line:s.lineHeight,
        color:s.color, background:s.backgroundColor, radius:s.borderTopLeftRadius,
        maxWidth:s.maxWidth, padding:s.paddingLeft};
    };
    const node = id => style(document.getElementById(id));
    const result = {
      width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
      fonts:loaded.map(list => list.map(face => ({family:face.family,status:face.status}))),
      chat:node('chat-container'), sidebar:node('sidebar'), answer:node('answer'),
      text:node('answer-text'), link:node('answer-link'), code:node('answer-code'),
      math:node('answer-math'), bubble:node('user-bubble'), heading:node('answer-heading'),
      row:node('answer-row'), composer:node('message-input-container'), input:node('chat-input'),
      analysis:{host:node('ees-cooperation-panel'), text:style(analysis.getElementById('text')),
        button:style(analysis.getElementById('button')), muted:style(analysis.getElementById('muted')),
        accent:style(analysis.getElementById('accent')), frame:style(analysis.querySelector('.frame'))},
      wo:{host:node('ees-wo-demo-panel'), text:style(wo.getElementById('text')),
        input:style(wo.getElementById('input')), muted:style(wo.getElementById('muted')),
        accent:style(wo.getElementById('accent'))},
    };
    output.textContent = JSON.stringify(result);
  } catch(error) { output.textContent = JSON.stringify({error:String(error)}); }
})();
</script></body></html>"""


class ChatThemeBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get("EES_TEST_CHROME")
        cls.chrome = shutil.which(explicit) if explicit else next(
            (path for name in ("google-chrome", "chromium", "chromium-browser")
             if (path := shutil.which(name))), None)
        if not cls.chrome:
            if explicit:
                raise RuntimeError("EES_TEST_CHROME was set but its executable is unavailable.")
            raise unittest.SkipTest("Chrome is not installed; Linux CI runs this check explicitly.")
        directory = os.environ.get("EES_TEST_BRANDING_DIR")
        if not directory:
            if explicit:
                raise RuntimeError("EES_TEST_BRANDING_DIR is required with EES_TEST_CHROME.")
            raise unittest.SkipTest("Set EES_TEST_BRANDING_DIR to the built pinned EES wheel.")
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        cls.assets = {}
        with ZipFile(directory / manifest["wheel"]["filename"]) as wheel:
            prefix = "open_webui/frontend/"
            for name in wheel.namelist():
                if name.startswith(prefix) and name.endswith((".css", ".ttf", ".woff", ".woff2")):
                    cls.assets["/" + name[len(prefix):]] = wheel.read(name)
        theme = "/_ees3/chat-theme.css"
        if theme not in cls.assets:
            raise AssertionError("The built wheel does not contain the ees.3 theme.")
        # Use actual upstream global/chat/markdown/KaTeX styles. The theme is the
        # last initial index.html link; lazy chat styles may arrive afterward.
        css = sorted(path for path in cls.assets if path.endswith(".css")
                     and "/immutable/assets/" in path
                     and Path(path).name.startswith(("0.", "Chat.", "Messages.", "katex.")))
        if len(css) != 4:
            raise AssertionError("The pinned upstream style fixture selection changed.")
        links = "".join('<link rel="stylesheet" href="' + html.escape(path) + '">'
                        for path in css[:1] + [theme] + css[1:])
        fixture = FIXTURE.replace("__STYLES__", links).replace("__PANEL_STYLES__", json.dumps(panel_styles()))
        for mode in ("light", "dark"):
            cls.assets["/" + mode + ".html"] = fixture.replace("__MODE__", mode).encode()
        handler = functools.partial(FixtureHandler, assets=cls.assets)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.addClassCleanup(cls.server.server_close)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.shutdown)

    def render(self, mode, width):
        with tempfile.TemporaryDirectory(prefix="ees-theme-chrome-") as profile:
            command = [self.chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                       "--disable-dev-shm-usage", "--disable-background-networking",
                       "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                       "--force-device-scale-factor=1", "--hide-scrollbars",
                       "--user-data-dir=" + profile, "--window-size=" + str(width) + ",1000",
                       "--virtual-time-budget=15000", "--dump-dom",
                       f"http://127.0.0.1:{self.server.server_port}/{mode}.html"]
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
        self.assertEqual(run.returncode, 0, run.stderr[-3000:])
        parser = ResultParser()
        parser.feed(run.stdout)
        self.assertTrue(parser.parts, "Chrome produced no completed font/cascade result. " + run.stderr[-1500:])
        result = json.loads("".join(parser.parts))
        self.assertNotIn("error", result, result.get("error"))
        return result

    def test_real_css_fonts_and_shadow_cascade_in_three_viewports(self):
        for mode, width in (("light", 1240), ("dark", 1240), ("light", 640)):
            with self.subTest(mode=mode, width=width):
                r = self.render(mode, width)
                dark = mode == "dark"
                paper = "rgb(25, 29, 35)" if dark else "rgb(255, 255, 255)"
                ink = "rgb(232, 237, 245)" if dark else "rgb(32, 44, 62)"
                side = "rgb(20, 24, 30)" if dark else "rgb(245, 247, 250)"
                soft = "rgb(36, 44, 54)" if dark else "rgb(240, 244, 248)"
                muted = "rgb(166, 178, 195)" if dark else "rgb(100, 113, 135)"
                blue = "rgb(145, 189, 223)" if dark else "rgb(55, 101, 139)"
                for loaded, family in zip(r["fonts"], ("EES Inter", "EES Noto Sans KR")):
                    self.assertTrue(any(face["family"].strip('"') == family and face["status"] == "loaded"
                                        for face in loaded), loaded)
                self.assertEqual(r["chat"]["background"], paper)
                self.assertEqual(r["sidebar"]["background"], side)
                self.assertEqual(r["text"]["color"], ink)
                self.assertEqual(r["link"]["color"], blue)
                self.assertEqual(r["bubble"]["background"], soft)
                self.assertEqual(r["composer"]["background"], paper)
                self.assertEqual(r["composer"]["radius"], "12px")
                self.assertEqual(r["answer"]["size"], "14px")
                self.assertAlmostEqual(float(r["answer"]["line"].removesuffix("px")), 27.3, places=1)
                self.assertEqual(r["input"]["size"], "13px")
                self.assertIn("monospace", r["code"]["font"])
                self.assertNotIn("EES", r["code"]["font"])
                self.assertIn("KaTeX", r["math"]["font"])
                self.assertNotIn("EES", r["math"]["font"])
                for node in (r["answer"], r["input"], r["analysis"]["text"],
                             r["analysis"]["button"], r["wo"]["text"], r["wo"]["input"]):
                    self.assertTrue(node["font"].startswith('"EES Inter"'), node["font"])
                    self.assertIn('"EES Noto Sans KR"', node["font"])
                self.assertEqual(r["analysis"]["frame"]["background"], side)
                for panel in (r["analysis"], r["wo"]):
                    self.assertEqual(panel["text"]["color"], ink)
                    self.assertEqual(panel["muted"]["color"], muted)
                    self.assertEqual(panel["accent"]["color"], blue)
                self.assertEqual(r["wo"]["host"]["background"], paper)
                self.assertEqual(r["row"]["maxWidth"], "672px")
                self.assertLessEqual(r["scrollWidth"], r["width"] + 1)
                self.assertEqual(r["row"]["padding"], "18px" if width <= 700 else "28px")
                self.assertEqual(r["heading"]["size"], "20px" if width <= 700 else "21px")
                if width <= 700:
                    self.assertLessEqual(r["width"], 700)


if __name__ == "__main__":
    unittest.main()
