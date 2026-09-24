"""Loopback-only API fixture for the *actual* pinned Open WebUI frontend.

The upstream Svelte/Tiptap bundles are served unchanged from the built wheel.
Authentication, chat storage, attachment metadata and model responses are
explicitly synthetic. Workflow HTTP actions use the real WorkflowService on a
temporary database. This is not a live-model or in-house authentication test.
"""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import queue
import threading
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

from scripts.build_ees_webui import TARGET_APP, assemble_work_launcher


USER = {"id": "fixture-admin", "name": "Fixture Administrator", "email": "fixture@example.invalid",
        "role": "admin", "profile_image_url": "/static/user.png", "permissions": {}, "settings": {}}
MODELS = [{"id": "fixture-model", "name": "Fixture AI", "object": "model", "owned_by": "openai",
           "info": {"id": "fixture-model", "name": "Fixture AI", "params": {},
                    "meta": {"capabilities": {"vision": True, "file_upload": True}}}}]


def chat_record(chat_id="existing-chat"):
    messages = {
        "previous-user": {"id": "previous-user", "role": "user", "content": "기존 질문",
                          "parentId": None, "childrenIds": ["previous-answer"], "models": ["fixture-model"]},
        "previous-answer": {"id": "previous-answer", "role": "assistant", "content": "기존 대화 기록",
                            "parentId": "previous-user", "childrenIds": [], "model": "fixture-model", "done": True}}
    return {"id": chat_id, "user_id": USER["id"], "title": "기존 대화", "updated_at": 1, "created_at": 1,
            "pinned": False, "archived": False, "folder_id": None,
            "chat": {"id": chat_id, "title": "기존 대화", "models": ["fixture-model"], "params": {},
                     "history": {"messages": messages, "currentId": "previous-answer"},
                     "messages": list(messages.values()), "files": [], "tags": []}}


class NativeUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, wheel_path):
        # Use the production builder contract while continuing to serve the
        # actual wheel. A stale wheel must fail instead of silently testing a
        # source overlay that was never packaged for deployment.
        with ZipFile(wheel_path) as wheel:
            if wheel.read(TARGET_APP + "ees-work-launcher.js") != assemble_work_launcher():
                raise ValueError("Native UI wheel launcher differs from the current assembled sources.")
        super().__init__(("127.0.0.1", 0), NativeUIHandler)
        self.wheel = ZipFile(wheel_path)
        self.assets = set(self.wheel.namelist())
        self.requests = []
        self.unknown = []
        self.errors = []
        self.user = dict(USER)
        self.chats = {"existing-chat": chat_record(), "other-chat": chat_record("other-chat")}
        self.workflow = None
        self.tool_call = None
        self.completions = []
        self.authoring_requests = []
        self.authoring_answer = '현재 업무의 목적과 완료 조건을 확인한 뒤 안내를 작성하세요.'
        self.authoring_status = 200
        self.authoring_sse = False
        self.authoring_hold = threading.Event()
        self.authoring_hold.set()
        self.authoring_started = threading.Event()
        self.tool_results = []
        self.stream_hold = threading.Event()
        self.stream_hold.set()
        self.stream_started = threading.Event()
        self.sockets = {}
        self.sockets_lock = threading.Lock()
        self.rpc_counter = 0
        self.rpc_pending = {}
        self.new_chat_ready = threading.Event()
        self.delay_next_action = False
        self.action_response_started = threading.Event()
        self.action_response_hold = threading.Event()
        self.action_response_hold.set()
        self.delay_next_completion = False
        self.completion_response_started = threading.Event()
        self.completion_response_hold = threading.Event()
        self.completion_response_hold.set()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"

    def emit(self, name, value):
        packet = "42" + json.dumps([name, value], ensure_ascii=False)
        with self.sockets_lock:
            targets = list(self.sockets.values())
        for target in targets:
            target.put(packet)

    def event_call(self, body, event):
        """Use native Socket.IO acknowledgements for the Tool's fixed UI RPC."""
        with self.sockets_lock:
            self.rpc_counter += 1
            number = str(self.rpc_counter)
            pending = self.rpc_pending[number] = queue.Queue()
            targets = list(self.sockets.values())
        packet = "42" + number + json.dumps(["events", {"chat_id": body["chat_id"],
            "message_id": body["id"], "data": event}], ensure_ascii=False)
        for target in targets:
            target.put(packet)
        try:
            return pending.get(timeout=8)
        finally:
            self.rpc_pending.pop(number, None)

    def model_reply(self, body):
        """Deterministic synthetic model transport through real socket events."""
        try:
            chat_id = body.get("chat_id") or "fixture-new-chat"
            message_id = body["id"]
            user_message = body.get("user_message", {})
            content = user_message.get("content", "")
            if body.get("fixture_new_chat"):
                self.new_chat_ready.wait(timeout=5)
            if self.tool_call and "점검" in content:
                result = self.tool_call(body)
                self.tool_results.append(result)
            for chunk in ("테스트 모델 응답: ", "실제 대화 입력이 전달되었습니다."):
                self.emit("events", {"chat_id": chat_id, "message_id": message_id,
                          "data": {"type": "chat:completion", "data": {"choices": [{"delta": {"content": chunk}}]}}})
                self.stream_started.set()
                self.stream_hold.wait(timeout=8)
            record = self.chats[chat_id]["chat"]
            user_message = dict(user_message)
            user_message["childrenIds"] = [message_id]
            assistant = {"id": message_id, "role": "assistant", "content": "테스트 모델 응답: 실제 대화 입력이 전달되었습니다.",
                         "done": True, "model": body["model"], "parentId": user_message["id"], "childrenIds": []}
            record["history"]["messages"].update({user_message["id"]: user_message, message_id: assistant})
            record["history"]["currentId"] = message_id
            self.emit("events", {"chat_id": chat_id, "message_id": message_id,
                      "data": {"type": "chat:completion", "data": {"done": True}}})
            self.emit("events", {"chat_id": chat_id, "message_id": message_id,
                      "data": {"type": "chat:active", "data": {"active": False}}})
        except Exception as error:
            self.errors.append(repr(error))

    def server_close(self):
        self.authoring_hold.set()
        self.stream_hold.set()
        self.action_response_hold.set()
        self.completion_response_hold.set()
        super().server_close()
        self.wheel.close()


class NativeUIHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_content(self, data, content_type="application/json", status=200):
        if not isinstance(data, bytes):
            data = data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_workflow(self, value):
        code = value.get("error", {}).get("code")
        status = 200 if value.get("ok") else 401 if code == "unauthorized" else 403 if code in {
            "workflow_manage_forbidden", "chat_forbidden", "admin_required"} else 409 if code in {
            "draft_revision_conflict", "workflow_baseline_changed", "validation_required", "request_conflict",
            "authoring_upgrade_required"} else 404 if code == "process_not_found" else 503 if code in {
            "authoring_unavailable", "authoring_authorization_unavailable"} else 400
        return self.send_content(value, status=status)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        self.server.requests.append(("GET", path))
        try:
            if path == "/ws/socket.io/":
                if "sid" not in query:
                    with self.server.sockets_lock:
                        sid = "fixture" + str(len(self.server.sockets))
                        self.server.sockets[sid] = queue.Queue()
                    return self.send_content("0" + json.dumps({"sid": sid, "upgrades": [], "pingInterval": 20000,
                                                               "pingTimeout": 10000, "maxPayload": 1000000}), "text/plain")
                target = self.server.sockets.get(query["sid"][0])
                if target is None:
                    return self.send_content({}, status=400)
                try:
                    packet = target.get(timeout=2)
                except queue.Empty:
                    packet = "2"
                return self.send_content(packet, "text/plain")
            if path == "/api/config":
                return self.send_content({"status": True, "name": "EES Work", "version": "0.11.3",
                    "default_locale": "ko-KR", "default_models": "fixture-model", "default_prompt_suggestions": [],
                    "oauth": {"providers": {}}, "features": {"auth": True, "enable_websocket": False,
                    "enable_login_form": True, "enable_folders": True, "enable_version_update_check": False},
                    "permissions": {}, "audio": {"tts": {"engine": "", "voice": ""}, "stt": {"engine": ""}},
                    "file": {"max_size": 10, "max_count": 5, "image_compression": {"width": 1920, "height": 1080}},
                    "ui": {"default_interface_settings": {}}, "code": {"engine": "pyodide"}})
            if path == "/api/v1/auths/":
                return self.send_content(self.server.user)
            if path in {"/api/v1/users/fixture-admin/profile/image", "/api/v1/models/model/profile/image"}:
                return self.send_content(self.server.wheel.read("open_webui/frontend/static/user.png"), "image/png")
            if path == "/api/v1/files/fixture-file/process/status":
                return self.send_content('data: {"status":"completed"}\n\ndata: [DONE]\n\n', "text/event-stream")
            if path == "/api/version":
                return self.send_content({"version": "0.11.3", "deployment_id": "fixture"})
            if path == "/api/version/updates":
                return self.send_content({"current": "0.11.3", "latest": "0.11.3"})
            if path == "/api/models":
                return self.send_content({"data": MODELS})
            if path == "/api/v1/users/user/settings":
                return self.send_content({"ui": {"models": ["fixture-model"], "showChangelog": False,
                                                 "version": "0.11.3", "autoFollowUps": False}})
            if path in {"/api/v1/models/list", "/api/v1/knowledge/list", "/api/v1/tools/list",
                        "/api/v1/knowledge/search", "/api/v1/prompts/list", "/api/v1/skills/list"}:
                return self.send_content({"items": [], "total": 0})
            if path == "/api/ees-work/authoring/capabilities" and self.server.workflow:
                return self.send_workflow(asyncio.run(self.server.workflow.authoring_capabilities(self.server.user)))
            if path == "/api/ees-work/authoring" and self.server.workflow:
                return self.send_workflow(asyncio.run(self.server.workflow.get_authoring(self.server.user,
                    system_id=query.get("system_id", [""])[0], process_id=query.get("process_id", [""])[0],
                    legacy_id=int(query["legacy_id"][0]) if "legacy_id" in query else None)))
            if path == "/api/ees-work/state" and self.server.workflow:
                selection = query.get("selection", [""])[0]
                response = asyncio.run(self.server.workflow.get_state(self.server.user,
                    chat_id=query.get("chat_id", [""])[0], case_id=query.get("case_id", [""])[0],
                    process_id=query.get("process_id", [""])[0],
                    selection=json.loads(selection) if selection else None))
                return self.send_content(response)
            if path == "/api/v1/chats/":
                self.server.new_chat_ready.set()
                return self.send_content([] if int(query.get("page", ["1"])[0]) > 1 else list(self.server.chats.values()))
            if path in {"/api/v1/chats/all/tags", "/api/v1/chats/tags", "/api/v1/chats/pinned",
                        "/api/v1/configs/banners", "/api/v1/tools/", "/api/v1/functions/", "/api/v1/skills/",
                        "/api/v1/prompts/", "/api/v1/folders/", "/api/v1/terminals/", "/api/v1/users/groups",
                        "/api/v1/models/tags", "/api/v1/models/base/tags", "/api/v1/channels/", "/api/v1/folders/shared",
                        "/api/v1/groups/"}:
                return self.send_content([])
            if path.startswith("/api/tasks/chat/"):
                return self.send_content({"task_ids": []})
            if path.startswith("/api/v1/chats/"):
                rest = path.removeprefix("/api/v1/chats/")
                if rest.endswith("/tags"):
                    return self.send_content([])
                if rest.endswith("/pinned"):
                    return self.send_content(False)
                if rest in self.server.chats:
                    return self.send_content(self.server.chats[rest])
            if path in {"/api/v1/users/user/info", "/api/v1/users/user/variables"}:
                return self.send_content({})
            if path.endswith("/info") and path.startswith("/api/v1/users/"):
                return self.send_content(self.server.user)
            name = "open_webui/frontend" + path
            if path in {"/", "/auth", "/workspace"} or path.startswith(("/c/", "/workspace/")):
                name = "open_webui/frontend/index.html"
            if name in self.server.assets:
                return self.send_content(self.server.wheel.read(name), mimetypes.guess_type(name)[0] or "application/octet-stream")
            self.server.unknown.append(("GET", path))
            self.send_content({"detail": "Explicit fixture route unavailable"}, status=404)
        except Exception as error:
            self.server.errors.append(repr(error))
            self.send_content({"detail": "Fixture failed"}, status=500)

    def do_POST(self):
        path = urlsplit(self.path).path
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append(("POST", path))
        try:
            if path == "/ws/socket.io/":
                query = parse_qs(urlsplit(self.path).query)
                target = self.server.sockets.get(query.get("sid", [""])[0])
                if target is not None and raw.startswith(b"40"):
                    target.put('40{"sid":"fixture-socket"}')
                for packet in raw.decode().split("\x1e"):
                    if packet.startswith("43") and "[" in packet:
                        index = packet.index("[")
                        pending = self.server.rpc_pending.get(packet[2:index])
                        if pending:
                            values = json.loads(packet[index:])
                            pending.put(values[0] if values else None)
                return self.send_content("ok", "text/plain")
            if path == "/api/v1/files/":
                return self.send_content({"id": "fixture-file", "user_id": self.server.user["id"],
                    "filename": "attachment.txt", "meta": {"name": "attachment.txt", "content_type": "text/plain", "size": 12},
                    "data": {"status": "completed"}, "created_at": 1})
            body = json.loads(raw or b"{}")
            if path == "/api/ees-work/authoring/action" and self.server.workflow:
                return self.send_workflow(asyncio.run(self.server.workflow.authoring_action(self.server.user, body)))
            if path == "/api/ees-work/action" and self.server.workflow:
                result = asyncio.run(self.server.workflow.handle_action(self.server.user, body))
                if self.server.delay_next_action:
                    self.server.delay_next_action = False
                    self.server.action_response_started.set()
                    self.server.action_response_hold.wait(timeout=8)
                return self.send_content(result)
            if path == "/api/chat/completions":
                if body.get('stream') is False and 'user_message' not in body:
                    self.server.authoring_requests.append(body)
                    self.server.authoring_started.set()
                    answer = self.server.authoring_answer
                    status = self.server.authoring_status
                    self.server.authoring_hold.wait(timeout=12)
                    if self.server.authoring_sse:
                        chunks = [json.dumps({'choices': [{'delta': {'content': part}}]}, ensure_ascii=False)
                                  for part in (answer[:len(answer)//2], answer[len(answer)//2:])]
                        return self.send_content(''.join('data: ' + item + '\n\n' for item in chunks)
                                                 + 'data: [DONE]\n\n', 'text/event-stream', status=status)
                    return self.send_content({'choices': [{'message': {'role': 'assistant', 'content': answer}}]}, status=status)
                self.server.completions.append(body)
                reply_body = dict(body)
                reply_body["chat_id"] = body.get("chat_id") or "fixture-new-chat"
                if reply_body["chat_id"] not in self.server.chats:
                    self.server.new_chat_ready.clear()
                    reply_body["fixture_new_chat"] = True
                    record = chat_record(reply_body["chat_id"])
                    user_message = dict(body["user_message"])
                    user_message["childrenIds"] = [body["id"]]
                    assistant = {"id": body["id"], "role": "assistant", "content": "", "done": False,
                                 "parentId": user_message["id"], "childrenIds": [], "model": body["model"]}
                    record["chat"]["history"] = {"currentId": body["id"],
                        "messages": {user_message["id"]: user_message, body["id"]: assistant}}
                    self.server.chats[reply_body["chat_id"]] = record
                if self.server.delay_next_completion:
                    self.server.delay_next_completion = False
                    self.server.completion_response_started.set()
                    self.server.completion_response_hold.wait(timeout=8)
                self.send_content({"task_id": "fixture-task", "chat_id": reply_body["chat_id"]})
                threading.Thread(target=self.server.model_reply, args=(reply_body,), daemon=True).start()
                return
            if path == "/api/v1/chats/new":
                chat_id = body.get("chat", {}).get("id") or "fixture-new-chat"
                record = chat_record(chat_id)
                record["chat"] = body["chat"]
                self.server.chats[chat_id] = record
                return self.send_content(record)
            if path.startswith("/api/v1/chats/"):
                chat_id = path.removeprefix("/api/v1/chats/").split("/")[0]
                if chat_id in self.server.chats:
                    self.server.chats[chat_id]["chat"].update(body)
                    return self.send_content(self.server.chats[chat_id])
            if path in {"/api/v1/users/user/settings/update", "/api/v1/users/user/info/update",
                        "/api/v1/auths/update/timezone", "/api/v1/chats/read", "/api/chat/completed"}:
                return self.send_content(body)
            self.server.unknown.append(("POST", path))
            self.send_content({"detail": "Explicit fixture route unavailable"}, status=404)
        except Exception as error:
            self.server.errors.append(repr(error))
            self.send_content({"detail": "Fixture failed"}, status=500)
