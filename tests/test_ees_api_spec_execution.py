"""Exercise registered service APIs over HTTP through the product command lifecycle."""
from contextlib import contextmanager
from copy import deepcopy
import importlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread
from types import ModuleType
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("ees_registered_api_tests")
package.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[package.__name__] = package
workflow = importlib.import_module(package.__name__ + ".ees_workflow")


@contextmanager
def backup_service():
    """Serve a differently shaped response or a failure on the same real endpoint."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlsplit(self.path)
            self.server.requests.append((request.path, parse_qs(request.query)))
            if request.path != "/backups":
                self.send_error(404)
                return
            payload = json.dumps(self.server.payload).encode("utf-8")
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if self.path != "/backups":
                self.send_error(404)
                return
            size = int(self.headers["Content-Length"])
            self.server.requests.append((self.path, json.loads(self.rfile.read(size))))
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"backup":{"entries":[{"label":"backup-queued"}]}}')

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.requests = []
        server.status = 200
        server.payload = {"backup": {"entries": [{"label": "nightly-ok"}]}}
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


class RegisteredApiExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.http = self.enterContext(backup_service())
        self.base_url = f"http://127.0.0.1:{self.http.server_port}"
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.database = Path(self.temp) / "work.sqlite3"
        self.users = {
            "admin": {"id": "admin", "role": "admin"},
            "operator": {"id": "operator", "role": "user"},
            "outsider": {"id": "outsider", "role": "user"},
        }
        self.counter = 0
        self.service = self.open_service()

    def open_service(self):
        service = workflow.WorkflowService(self.database, self.users.get, lambda key: None)
        self.addAsyncCleanup(service.operations.stop)
        return service

    def command(self, action, **fields):
        self.counter += 1
        return {"action": action, "request_id": f"api-test-{self.counter}",
                "expected_revision": 0, **fields}

    async def workspace(self, action, actor="admin", **fields):
        response = await self.service.workspace_command(self.users[actor], self.command(action, **fields))
        self.assertTrue(response["ok"], response)
        return response

    async def register_backup(self, method="GET"):
        record = await self.service.operations.command(self.users["admin"], self.command(
            "api_service_save", service={"name": "Backup service"}))
        self.assertTrue(record["ok"], record)
        service_id = record["service"]["id"]
        config = {service_id: {"base_url": self.base_url}}
        self.enterContext(patch.dict(os.environ, {"EES_WORK_API_SERVICES": json.dumps(config)}))
        api = {
            "service_id": service_id, "name": "Backup history", "purpose": "Verify completion",
            "method": method, "url": self.base_url + "/backups",
            "inputs": [{"name": "line", "in": "query" if method == "GET" else "body", "type": "string",
                        "required": True, "label": "Line"}],
            "result_path": "backup.entries",
            "fields": [{"path": "label", "label": "Backup name", "type": "string"}],
            "example": {"backup": {"entries": [{"label": "registration-example-only"}]}},
        }
        saved = await self.service.operations.command(self.users["admin"], self.command("api_save", api=api))
        self.assertTrue(saved["ok"], saved)
        return saved["api"]

    async def start_workflow(self, api_record, *, handoff=False):
        created = await self.workspace("create_workflow", name="Backup verification", system_id="EMS")
        definition = created["workflow"]["draft"]
        root_id = next(iter(definition["nodes"]))
        definition["nodes"][root_id]["children"] = ["stage"]
        definition["nodes"]["stage"] = {
            "id": "stage", "type": "t", "name": "Check", "parent": root_id,
            "children": ["backup-job"], "deps": [],
        }
        definition["nodes"]["backup-job"] = {
            "id": "backup-job", "type": "j", "parent": "stage", "name": "Read backups",
            "children": [], "deps": [], "mode": "tool", "result_block": "human_confirm",
            "human_confirmation": True,
            "api_binding": {
                "operation_id": api_record["id"], "version": api_record["version"],
                "inputs": {"line": {"constant": "Line A/2"}}, "outputs": ["label"],
            },
        }
        if api_record["method"] == "POST":
            definition["nodes"]["backup-job"].update(result_block="change_request", approval_count=0,
                effect_criterion={"check": "inspect backup status"})
        if handoff:
            successor = deepcopy(definition["nodes"]["backup-job"])
            successor.update(id="follow-up", name="Follow up", deps=["backup-job"])
            source = {"job_id": "backup-job", "field": "label", "confirmed": True}
            successor["api_binding"]["inputs"] = {"line": {"result": source}}
            definition["nodes"]["stage"]["children"].append("follow-up")
            definition["nodes"]["follow-up"] = successor
        workflow_id = created["workflow_id"]
        await self.workspace("save_draft", workflow_id=workflow_id, expected_revision=1, definition=definition)
        saved = await self.service.workspace_state(self.users["admin"], workflow_id=workflow_id)
        self.assertTrue(saved["ok"], saved)
        saved_node = saved["workflow"]["draft"]["nodes"]["backup-job"]
        self.assertEqual(saved_node["api_binding"], definition["nodes"]["backup-job"]["api_binding"])
        await self.workspace("publish_workflow", workflow_id=workflow_id, expected_revision=2)
        await self.workspace("save_access", principal_kind="user", principal_id="operator",
                             system_id="EMS", factory_id="*", roles=["participant", "requester"])
        started = await self.workspace("start_run", actor="operator", workflow_id=workflow_id,
                                       expected_revision=3, inputs={})
        self.assertEqual(self.http.requests, [], "Authoring and opening a run dispatched HTTP")
        return started["run_id"]

    async def history(self, run_id, service=None):
        state = await (service or self.service).workspace_state(self.users["operator"], run_id=run_id)
        self.assertTrue(state["ok"], state)
        return state["run"]["attempts"]

    def execution_command(self, run_id):
        return self.command("execute_job", run_id=run_id, job_id="backup-job", expected_revision=1)

    async def test_get_maps_args_and_rows_and_persists_attempt_across_restart(self):
        api = await self.register_backup()
        run_id = await self.start_workflow(api)
        command = self.execution_command(run_id)
        response = await self.service.operations.command(self.users["operator"], command)
        attempt = response["attempt"]
        self.assertEqual(attempt["status"], "succeeded", attempt)
        self.assertEqual([item["row"] for item in attempt["result"]["items"]], [{"label": "nightly-ok"}])
        self.assertEqual(self.http.requests, [("/backups", {"line": ["Line A/2"]})])

        replay = await self.service.operations.command(self.users["operator"], command)
        self.assertEqual(replay["attempt"]["id"], attempt["id"])
        self.assertEqual(len(self.http.requests), 1)
        attempts = await self.history(run_id, self.open_service())
        self.assertEqual([row["id"] for row in attempts], [attempt["id"]])
        self.assertEqual(attempts[0]["result"]["items"], attempt["result"]["items"])

        config = {api["service_id"]: {"base_url": self.base_url, "actor_ids": ["admin"]}}
        with patch.dict(os.environ, {"EES_WORK_API_SERVICES": json.dumps(config)}):
            restricted = await self.history(run_id)
        self.assertEqual(restricted[0]["id"], attempt["id"])
        self.assertIsNone(restricted[0]["result"])
        self.assertNotIn("nightly-ok", json.dumps(restricted))

    async def test_forbidden_operator_cannot_dispatch_and_upstream_failure_is_recorded(self):
        api = await self.register_backup()
        run_id = await self.start_workflow(api)
        with self.assertRaises(workflow.WorkflowError):
            await self.service.operations.command(self.users["outsider"], self.execution_command(run_id))
        self.assertEqual(self.http.requests, [])
        self.assertEqual(await self.history(run_id), [])

        self.http.status = 503
        self.http.payload = {"message": "PRIVATE_PROVIDER_DETAIL"}
        response = await self.service.operations.command(self.users["operator"], self.execution_command(run_id))
        self.assertEqual(response["attempt"]["status"], "failed", response)
        self.assertEqual(len(self.http.requests), 1)
        attempts = await self.history(run_id)
        self.assertEqual([row["status"] for row in attempts], ["failed"])
        self.assertNotIn("PRIVATE_PROVIDER_DETAIL", json.dumps(attempts))

    async def test_mutation_waits_for_explicit_dispatch_and_refuses_double_delivery(self):
        api = await self.register_backup("POST")
        run_id = await self.start_workflow(api)
        actor = self.users["operator"]
        runtime = self.service.operations
        with self.assertRaises(workflow.WorkflowError):
            await runtime.command(actor, self.execution_command(run_id))
        self.assertEqual(self.http.requests, [])

        prepared = await runtime.command(actor, self.command(
            "request_prepare", run_id=run_id, job_id="backup-job", expected_revision=1))
        request = prepared["request"]
        request_fields = {"external_request_id": request["id"], "expected_revision": request["revision"]}
        with self.assertRaises(workflow.WorkflowError):
            await runtime.command(actor, self.command("request_dispatch", **request_fields))
        intent = await runtime.command(actor, self.command("request_intent", **request_fields))
        self.assertEqual(self.http.requests, [])

        command = self.command("request_dispatch", intent_token=intent["intent_token"], **request_fields)
        response = await runtime.command(actor, command)
        self.assertEqual(response["request"]["state"], "accepted", response)
        self.assertEqual(self.http.requests, [("/backups", {"line": "Line A/2"})])
        with self.assertRaises(workflow.WorkflowError):
            await runtime.command(actor, self.command("request_dispatch", intent_token=intent["intent_token"], **request_fields))
        self.assertEqual(len(self.http.requests), 1)

    async def test_successor_receives_only_the_confirmed_prior_result(self):
        api = await self.register_backup()
        run_id = await self.start_workflow(api, handoff=True)
        actor = self.users["operator"]
        runtime = self.service.operations
        first = await runtime.command(actor, self.execution_command(run_id))
        state = await self.service.workspace_state(actor, run_id=run_id)
        revision = state["run"]["revision"]
        with self.assertRaises(workflow.WorkflowError):
            await runtime.command(actor, self.command(
                "execute_job", run_id=run_id, job_id="follow-up", expected_revision=revision))
        self.assertEqual(len(self.http.requests), 1)

        confirmed = await self.workspace("decide", actor="operator", expected_revision=revision,
            run_id=run_id, job_id="backup-job", result_revision=first["attempt"]["number"],
            item_id="job", verdict="completed")
        self.assertEqual(confirmed["run"]["jobs"]["backup-job"]["status"], "completed")
        result = await runtime.command(actor, self.command(
            "execute_job", run_id=run_id, job_id="follow-up", expected_revision=confirmed["run"]["revision"]))
        self.assertEqual(result["attempt"]["status"], "succeeded", result)
        self.assertEqual(self.http.requests[-1], ("/backups", {"line": ["nightly-ok"]}))
