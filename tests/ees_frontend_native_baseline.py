"""Compare the pinned official and pristine source-built Native frontend.

Both browsers use the same explicit loopback API/model fixture. This proves
observable frontend behavior, not in-house authentication or model quality.
The production EES fixture's packaged-launcher guard remains enabled by default.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_ui_fixture import NativeUIServer
from test_ees_chat_theme import ChromePipe
from scripts.build_ees_frontend import validate_frontend


def wait(browser, expression, *, seconds=15, retry_navigation=False):
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            value = browser.evaluate(expression, timeout=remaining)
        except AssertionError as error:
            # Page.reload can destroy the old execution context while CDP is
            # evaluating readiness. Retry only this protocol error, and retain
            # the original deadline for every request and polling interval.
            message = str(error)
            if not (retry_navigation and message.startswith("Runtime.evaluate: ")
                    and "'message': 'Inspected target navigated or closed'" in message):
                raise
            value = False
        if value and time.monotonic() < deadline:
            return value
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    raise AssertionError("Native baseline condition timed out: " + expression)


def click(browser, selector):
    point = browser.evaluate("(() => { const e=document.querySelector(" + json.dumps(selector)
        + "); if(!e) return null; e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect();"
          "return r.width && r.height ? {x:r.x+r.width/2,y:r.y+r.height/2}:null; })()")
    if not point:
        raise AssertionError("Native baseline control is not visible: " + selector)
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        browser.call("Input.dispatchMouseEvent", {"type": kind, **point, "button": "left", "clickCount": 1})


def screenshot(browser, path):
    browser.evaluate("document.fonts.ready.then(() => true)")
    wait(browser, "!document.getAnimations().some(animation => animation.playState === 'running' "
        "&& animation.effect?.getTiming().iterations !== Infinity)")
    path.write_bytes(base64.b64decode(browser.call("Page.captureScreenshot", {"format": "png"})["data"]))


def reload_page(browser):
    previous = browser.evaluate("performance.timeOrigin")
    browser.call("Page.reload", {"ignoreCache": True})
    wait(browser, "performance.timeOrigin !== " + json.dumps(previous)
        + " && document.readyState === 'complete'", retry_navigation=True)


def exercise(wheel, chrome, output, frontend=None):
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "checkpoints": []}
    with tempfile.TemporaryDirectory(prefix="ees-native-baseline-") as temporary:
        server = NativeUIServer(wheel, upstream_baseline=True, frontend_directory=frontend)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        browser = None
        try:
            browser = ChromePipe(chrome, str(Path(temporary) / "chrome"), font_wheel=wheel)
            browser.navigate("about:blank")
            browser.call("Runtime.enable")
            browser.call("Network.enable")
            browser.call("Page.addScriptToEvaluateOnNewDocument", {"source":
                "localStorage.setItem('locale','ko-KR');localStorage.setItem('version','0.11.3');"})
            browser.call("Page.navigate", {"url": server.url + "/auth"})
            wait(browser, "!!document.querySelector('#email') && !!document.querySelector('#password')")
            screenshot(browser, output / "01-native-login.png")
            report["checkpoints"].append({"name": "login", "email_password_controls": True})

            browser.evaluate("localStorage.setItem('token','fixture-token')")
            browser.call("Page.navigate", {"url": server.url + "/c/existing-chat"})
            wait(browser, "!!document.querySelector('#chat-input.ProseMirror') && document.body.textContent.includes('기존 대화 기록')")
            report["checkpoints"].append({"name": "existing-chat", "route": browser.evaluate("location.pathname"),
                "previous_user": browser.evaluate("document.body.textContent.includes('기존 질문')"),
                "previous_answer": True})
            click(browser, "#chat-input")
            browser.call("Input.insertText", {"text": "소스 빌드 대화 초안"})
            wait(browser, "document.querySelector('#chat-input')?.textContent === '소스 빌드 대화 초안'")
            # Native owns its debounce and draft serialization. Wait for its
            # observable storage write instead of introducing a fixed delay.
            wait(browser, "Object.values(sessionStorage).some(value => value.includes('소스 빌드 대화 초안'))")
            reload_page(browser)
            wait(browser, "document.querySelector('#chat-input')?.textContent === '소스 빌드 대화 초안'")
            report["checkpoints"].append({"name": "native-draft-reload", "preserved": True})

            attachment = Path(temporary) / "baseline-attachment.txt"
            attachment.write_text("Synthetic baseline attachment.\n", encoding="utf-8")
            root = browser.call("DOM.getDocument")["root"]["nodeId"]
            node = browser.call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})["nodeId"]
            if not node:
                raise AssertionError("Native file input is missing")
            browser.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(attachment)]})
            wait(browser, "document.body.textContent.includes('baseline-attachment.txt')")
            wait(browser, "!!document.querySelector('#send-message-button') && !document.querySelector('#send-message-button').disabled")
            screenshot(browser, output / "02-native-draft-attachment.png")
            assert server.uploaded_file == (b"Synthetic baseline attachment.\n", "text/plain")
            report["checkpoints"].append({"name": "attachment", "filename": attachment.name, "bytes": len(server.uploaded_file[0])})

            click(browser, "#send-message-button")
            wait(browser, "document.querySelector('#chat-input')?.textContent.trim() === ''")
            wait(browser, "document.body.textContent.includes('테스트 모델 응답: 실제 대화 입력이 전달되었습니다.')")
            assert len(server.completions) == 1, server.completions
            completion = server.completions[0]
            assert completion["user_message"]["content"] == "소스 빌드 대화 초안"
            assert completion["files"][0]["name"] == "baseline-attachment.txt", completion.get("files")
            report["checkpoints"].append({"name": "send-and-response", "sent_content": completion["user_message"]["content"],
                "attachment": completion["files"][0]["name"], "response": "테스트 모델 응답: 실제 대화 입력이 전달되었습니다."})
            reload_page(browser)
            wait(browser, "document.body.textContent.includes('테스트 모델 응답: 실제 대화 입력이 전달되었습니다.')")
            screenshot(browser, output / "03-native-saved-history.png")
            report["checkpoints"].append({"name": "saved-history-reload", "preserved": True})
            browser.call("Page.navigate", {"url": server.url + "/c/existing-chat?settings=about"})
            wait(browser, "!!document.querySelector('#tab-about')")
            version = browser.evaluate("document.querySelector('#tab-about').textContent")
            assert "v0.11.3" in version, "Native frontend About version is missing: " + version
            screenshot(browser, output / "04-native-about-version.png")
            report["checkpoints"].append({"name": "frontend-about-version", "version": "0.11.3"})
            assert not server.errors, server.errors
            report["status"] = "passed"
        except Exception as error:
            report["status"] = "failed"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
            if browser is not None:
                report["browser"] = browser.diagnostics()
                try:
                    screenshot(browser, output / "failure.png")
                    report["page"] = browser.evaluate("({path:location.pathname,text:document.body?.innerText?.slice(0,12000)})")
                except Exception:
                    pass
            raise
        finally:
            report["server_errors"] = server.errors
            report["unknown_requests"] = server.unknown
            if browser is not None:
                browser.close()
            server.shutdown()
            server.server_close()
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--frontend-dir", type=Path, required=True)
    parser.add_argument("--chrome", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # The frontend builder verifies the exact upstream checkout, lockfile and
    # output inventory before this separate browser gate consumes its bytes.
    validate_frontend(args.frontend_dir, mode="baseline")
    manifest = json.loads((args.frontend_dir / "manifest.json").read_text(encoding="utf-8"))
    official = exercise(args.wheel, args.chrome, args.output / "official")
    source = exercise(args.wheel, args.chrome, args.output / "source", args.frontend_dir / "build")
    assert official["checkpoints"] == source["checkpoints"], (official["checkpoints"], source["checkpoints"])
    result = {"status": "passed", "comparison": "unchanged Native frontend behavior",
        "official_wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        "source_frontend_manifest": manifest, "checkpoints": source["checkpoints"]}
    (args.output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("EES source baseline result=ok checkpoints=" + str(len(source["checkpoints"])))


if __name__ == "__main__":
    main()
