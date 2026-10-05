"""TR-22/23: real Native sources/persistence/ACL/Valves and EES publication/runs.

HTTP and model transport/metadata are synthetic. No production account, tool
registration, service, model-quality or Windows installation claim is made.
"""
import asyncio
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from starlette.requests import Request
import test_ees_workflow_native as read_fixture

ROOT = Path(__file__).resolve().parents[1]
WHEEL = Path(os.environ.get("EES_TEST_UPSTREAM_WHEEL", ROOT / "dist/upstream/open_webui-0.11.3-py3-none-any.whl"))


class NativeWorkflowExamplesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not WHEEL.is_file():
            if os.environ.get("EES_REQUIRE_ASSET_NATIVE") == "1":
                self.fail("Pinned Native wheel unavailable")
            self.skipTest("Pinned Native wheel unavailable")
        from ees_workflow_native_fixture import NativeReadFixture
        self.fixture = NativeReadFixture(WHEEL)
        self.addAsyncCleanup(self.fixture.close)
        await self.fixture.start()
        self.service, self.bridge = self.fixture.service, self.fixture.bridge
        self.service.execution.bridge = self.bridge
        self.addAsyncCleanup(self.service.execution.stop)
        self.examples = __import__("workflow_fixture").load_workflow_examples("open_webui")
        self.model_module = importlib.import_module("open_webui.ees_workflow_model")
        self.refs = {}
        for family in ("confluence", "jira", "github"):
            self.refs.update(await self.fixture.register_read_tool(family))
        self.service.asset_lookup = self.assets
        self.admin, self.reader = self.fixture.users["admin"], self.fixture.users["reader"]
        self.serial, self.http_calls, self.model_calls = 0, [], []
        self.ambiguous, self.truncated, self.fabricate = False, False, None
        self.fixture.app.state.MODELS = {"synthetic-model": {"id": "synthetic-model", "owned_by": "ollama"}}
        self.service.execution.model = self.model_module.NativeModelAdapter(self.service, self.fixture.app)
        runtime = SimpleNamespace(Request=Request, Models=SimpleNamespace(get_model_by_id=lambda _: SimpleNamespace(params={})),
                                  generate=self.generate, check_access=self.model_access, bypass_admin=False, bypass_models=False)
        self.model_patch = patch.object(self.model_module, "_runtime", return_value=runtime)
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)
        self.http_patch = patch("urllib.request.OpenerDirector.open", side_effect=self.http)
        self.http_patch.start()
        self.addCleanup(self.http_patch.stop)

    async def assets(self, user):
        tools = [await self.fixture.tools.Tools.get_tool_by_id("fixture_" + family) for family in ("confluence", "jira", "github")]
        return {"available": True, "tools": [{"id": tool.id, "name": tool.name} for tool in tools], "skills": [],
                "tool_versions": {tool.id: tool.updated_at for tool in tools}, "skill_bodies": {}, "skill_versions": {}}

    async def model_access(self, user, model, model_info=None):
        self.assertEqual(user.id, "reader")
        self.assertEqual(model["id"], "synthetic-model")

    async def generate(self, request, form, user, bypass_system_prompt=False):
        self.assertTrue(bypass_system_prompt)
        self.assertEqual(form["tools"], [])
        self.assertEqual(user.id, "reader")
        context = json.loads(form["messages"][1]["content"])
        self.model_calls.append(deepcopy(context))
        self.assertTrue(context["skills"], "Common policy must reach the actual model input")
        self.assertTrue(any(skill["id"] == "common" for skill in context["skills"]))
        self.assertEqual(len(context["untrusted_evidence"]), 3)
        self.assertEqual(len(context["required_claims"]), 6)
        self.assertNotIn("synthetic-reader-pat", json.dumps(context))
        claims, limitations = [], []
        for ref in context["evidence_sources"]:
            result = context["untrusted_evidence"][ref["job_id"]][ref["call_id"]]
            paths = {"dashboard": [["data", "summary", "total"], ["data", "summary", "open"]],
                     "pull_requests": [["data", "pagination", "returned"], ["data", "pagination", "has_next"]],
                     "page": [["data", "page", "title"], ["data", "page", "version"]]}[ref["call_id"]]
            for path in paths:
                value = result
                for key in path:
                    value = value[key]
                claims.append({**ref, "path": path, "value": value})
            if result["completeness"] not in ("complete", "empty"):
                limitations.append({**ref, "completeness": result["completeness"]})
        if self.fabricate == "count":
            claims[0].update(path=["data", "summary", "total"], value=99999)
        elif self.fabricate == "ci":
            claims[2].update(path=["data", "ci_status"], value="passed")
        elif self.fabricate == "evidence":
            claims[0]["job_id"] = "foreign-job"
        output = {"claims": claims, "limitations": limitations}
        return {"choices": [{"message": {"content": json.dumps(output)}}]}

    page = staticmethod(read_fixture.NativeReadBridgeTests.page)
    issue = staticmethod(read_fixture.NativeReadBridgeTests.issue)
    pull = staticmethod(read_fixture.NativeReadBridgeTests.pull)

    def http(self, request, timeout=None):
        if "/rest/api/content/search" in request.full_url and self.ambiguous:
            self.http_calls.append((request.full_url, request.get_header("Authorization")))
            other = self.page("synthetic-reader-pat")
            other["id"], other["title"] = "124", "Other installation guide"
            return read_fixture.Response({"results": [self.page("synthetic-reader-pat"), other]})
        if "/rest/api/content/124" in request.full_url:
            self.http_calls.append((request.full_url, request.get_header("Authorization")))
            other = self.page("synthetic-reader-pat")
            other["id"] = "124"
            return read_fixture.Response(other)
        if "/rest/api/content/123" in request.full_url and self.truncated:
            self.http_calls.append((request.full_url, request.get_header("Authorization")))
            other = self.page("synthetic-reader-pat")
            other["body"]["storage"]["value"] = "<p>" + "data " * 20000 + "</p>"
            return read_fixture.Response(other)
        return read_fixture.NativeReadBridgeTests.http(self, request, timeout)

    def request_id(self):
        self.serial += 1
        return "native-example-" + str(self.serial)

    async def author(self, action, process=None, payload=None, **extra):
        body = {"action": action, "request_id": self.request_id(), "payload": payload or {}, **extra}
        if process:
            body.update(process_id=process["process_id"], system_id=process["owner_system"],
                        expected_draft_revision=process["draft_revision"], expected_owner_revision=process["owner_revision"])
        result = await self.service.authoring_action(self.admin, body)
        self.assertTrue(result["ok"], result)
        return result["process"]

    async def publish_example(self, kind):
        process = await self.author("create", payload={"name": "Native integration " + kind, "category": "ops"}, system_id="EMS")
        if kind == "A":
            document = self.examples.operations_workflow(self.refs, "synthetic-model", process["process_id"])
        else:
            document = self.examples.installation_docs_workflow(self.refs, process["process_id"])
        process = await self.author("save_draft", process, {"workflow": document})
        process = await self.author("validate_draft", process)
        return await self.author("publish", process)

    async def start(self, process, node=None, inputs=None, case_id=None):
        workflow = process["workflow"]
        root = workflow["nodes"][process["process_id"]]
        body = {"node_id": node or process["process_id"], "inputs": inputs or {}}
        if case_id:
            body["case_id"] = case_id
        else:
            body["scope"] = {"site_id": "us-a", "system": "EMS", "version": process["published_version"], "process_id": process["process_id"]}
        result = await self.service.execution.plan(self.reader, body)
        self.assertTrue(result["ok"], result)
        plan = result["plan"]
        started = await self.service.execution.action(self.reader, {"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": self.request_id()})
        self.assertTrue(started["ok"], started)
        return started["run"]

    async def settle(self, run):
        for _ in range(25):
            await self.service.execution.process_once()
            with self.service._db() as db:
                current = json.loads(db.execute("SELECT data FROM execution_runs WHERE id=?", (run["id"],)).fetchone()[0])
            if current["status"] not in ("queued", "running"):
                state = await self.service.execution.state(self.reader, run_id=run["id"], case_id=current["case_id"])
                self.assertTrue(state["ok"], state)
                return state["run"]
        self.fail("Synthetic native run did not settle")

    async def control(self, run, action, **extra):
        result = await self.service.execution.action(self.reader, {"action": action, "run_id": run["id"],
            "expected_revision": run["revision"], "request_id": self.request_id(), **extra})
        self.assertTrue(result["ok"], result)
        return result["run"]

    async def test_a_t_only_then_p_three_native_functions_and_grounded_summary(self):
        process = await self.publish_example("A")
        root = process["workflow"]["nodes"][process["process_id"]]
        inputs = {"project_key": "EESEMS", "repository": "team/repo", "ops_page_id": "123"}
        t_run = await self.settle(await self.start(process, root["children"][0], inputs))
        self.assertEqual(t_run["status"], "succeeded", t_run)
        self.assertEqual(len(t_run["calls"]), 3)
        self.assertEqual(self.model_calls, [])
        self.assertEqual({call["reference"]["function"] for call in t_run["calls"]}, {"jira_dashboard", "github_list_pull_requests", "get_page"})
        p_run = await self.settle(await self.start(process, inputs=inputs, case_id=t_run["case_id"]))
        self.assertEqual(p_run["status"], "succeeded", p_run)
        self.assertEqual(len(p_run["calls"]), 1, "Stored successful reads must be reused")
        self.assertEqual(len(self.model_calls), 1)
        self.assertTrue(p_run["jobs"])
        with self.service._db() as db:
            stored = [json.loads(row["data"]) for row in db.execute("SELECT data FROM execution_calls")]
            case = json.loads(db.execute("SELECT data FROM cases WHERE id=?", (p_run["case_id"],)).fetchone()[0])
        self.assertEqual(len(stored), 4)
        self.assertEqual(case["execution_run_id"], p_run["id"])
        self.assertNotIn("synthetic-reader-pat", json.dumps(stored))
        self.assertTrue(all(header == "Bearer synthetic-reader-pat" for _, header in self.http_calls))
        self.assertTrue(any(call["result"]["completeness"] == "partial" for call in stored if call["kind"] == "fixed"))
        fresh = await self.settle(await self.start(process, inputs=inputs))
        self.assertEqual(fresh["status"], "succeeded", fresh)
        self.assertEqual(len(fresh["calls"]), 4)
        self.assertEqual(len(self.model_calls), 2)

    async def test_a_t2_scope_waits_without_dispatching_outside_dependencies(self):
        process = await self.publish_example("A")
        root = process["workflow"]["nodes"][process["process_id"]]
        run = await self.settle(await self.start(process, root["children"][1], {"project_key": "EESEMS", "repository": "team/repo", "ops_page_id": "123"}))
        self.assertEqual(run["status"], "waiting_dependency", run)
        self.assertEqual(run["calls"], [])
        self.assertEqual(self.http_calls, [])
        self.assertEqual(self.model_calls, [])

    async def test_b_same_confluence_search_candidate_wait_resume_and_body(self):
        self.ambiguous = True
        process = await self.publish_example("B")
        run = await self.settle(await self.start(process, inputs={"query": "install", "space_key": "EMS"}))
        self.assertEqual(run["status"], "waiting_input", run)
        self.assertEqual(len(run["calls"]), 1)
        wrong = await self.control(run, "inputs", inputs={"page_id": "999"})
        wrong = await self.control(wrong, "resume")
        rejected = await self.settle(wrong)
        self.assertNotEqual(rejected["status"], "succeeded")
        self.assertEqual(len(rejected["calls"]), 1)
        # A separate case demonstrates permitted selection without changing a
        # previously submitted input or overwriting the rejected evidence.
        valid = await self.settle(await self.start(process, inputs={"query": "install", "space_key": "EMS"}))
        valid = await self.control(valid, "inputs", inputs={"page_id": "124"})
        valid = await self.control(valid, "resume")
        valid = await self.settle(valid)
        self.assertEqual(valid["status"], "succeeded", valid)
        self.assertEqual(len(valid["calls"]), 2)
        self.assertEqual({call["reference"]["tool_id"] for call in valid["calls"]}, {self.refs["get_page"]["tool_id"]})
        self.assertEqual({call["reference"]["content_hash"] for call in valid["calls"]}, {self.refs["get_page"]["content_hash"]})
        self.assertEqual(self.model_calls, [])
        self.assertNotIn("Windows 설치 완료", json.dumps(valid, ensure_ascii=False))

    async def test_model_invented_counts_ci_and_foreign_evidence_never_complete(self):
        process = await self.publish_example("A")
        for fabricated in ("count", "ci", "evidence"):
            self.fabricate = fabricated
            run = await self.settle(await self.start(process, inputs={"project_key": "EESEMS", "repository": "team/repo", "ops_page_id": "123"}))
            self.assertEqual(run["status"], "unknown", (fabricated, run))
            self.assertEqual(len(run["calls"]), 4)
            self.assertEqual(sum(job["status"] == "succeeded" for job in run["jobs"].values()), 3)

    async def test_truncated_document_stops_and_does_not_run_summary(self):
        self.truncated = True
        process = await self.publish_example("A")
        run = await self.settle(await self.start(process, inputs={"project_key": "EESEMS", "repository": "team/repo", "ops_page_id": "123"}))
        self.assertEqual(run["status"], "unknown", run)
        self.assertEqual(self.model_calls, [])
        self.assertEqual(len(run["calls"]), 3)
