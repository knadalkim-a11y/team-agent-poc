"""Durable service tests with real SQLite and processes, synthetic Native I/O.

These tests prove scheduling/storage boundaries, not in-house API authorization.
Native loader and assembled wheel coverage is in test_ees_workflow_native.
"""
import asyncio
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import ModuleType
import unittest
from unittest.mock import patch

from workflow_fixture import publish_fixture_definition

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agent-pack/skills/ees-work-demo/scripts"
PACKAGE = ModuleType("ees_execution_tests")
PACKAGE.__path__ = [str(SOURCE)]
sys.modules[PACKAGE.__name__] = PACKAGE
workflow = importlib.import_module(PACKAGE.__name__ + ".ees_workflow")
execution = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_execution")
examples = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_examples")
USER = {"id": "alice", "role": "user"}
REFERENCES = {function: {"tool_id": "confluence" if function in {"search_pages", "get_page"} else function,
    "function": function, "revision": 1, "content_hash": "a" * 64, "schema_hash": "b" * 64,
    "config_hash": "c" * 64, "environment": "d" * 64}
    for function in ("jira_dashboard", "github_list_pull_requests", "get_page", "search_pages")}


def envelope(data=None, completeness="complete", status="succeeded"):
    return {"version": 1, "status": status, "transport": "succeeded", "completeness": completeness,
            "data": data or {"count": 2, "summary": {"total": 2, "open": 2}, "pagination": {"returned": 2, "has_next": False}, "page": {"title": "운영 문서", "version": 2}}, "evidence": [{"id": "42", "url": "http://fixture.invalid/42"}],
            "provenance": {"simulation": True}}


class Bridge:
    def __init__(self):
        self.calls = []
        self.allowed = True
        self.delay = 0
        self.started = asyncio.Event()
        self.results = {}

    async def check(self, user, reference):
        if not self.allowed:
            raise workflow.WorkflowError("native_access_denied", "권한이 없습니다.")
        return {"reference": reference, "state": "allowed"}

    async def invoke(self, user, reference, arguments, context):
        await self.check(user, reference)
        self.calls.append({"user": user["id"], "function": reference["function"], "arguments": arguments,
                           "context": context})
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        return deepcopy(self.results.get(reference["function"], envelope()))


class Model:
    def __init__(self):
        self.calls = []
        self.forge = False

    async def invoke(self, user, node, context, stored_results, inputs):
        self.calls.append(context)
        claims = []
        for required in node["execution"]["completion"].get("required_claims", []):
            value = stored_results[required["job_id"]][required["call_id"]]
            for key in required["path"]:
                value = value[key]
            claims.append({**required, "value": 999 if self.forge else value})
        if not claims:
            claims = [{"job_id": ref["job_id"], "call_id": ref["call_id"], "path": ["data", "count"], "value": 999 if self.forge else 2}
                      for ref in node["execution"]["evidence"]]
        return envelope({"claims": claims, "limitations": []})


def build_service(database, bridge=None, model=None):
    return workflow.WorkflowService(database, lambda key: {"id": key, "role": "user"},
        lambda key: {"id": key, "user_id": "alice"}, native_bridge=bridge or Bridge(), model_executor=model or Model())


def publish(service, fragment):
    definition = workflow._seed()
    definition["nodes"].update(fragment["nodes"])
    definition["tools"].update(fragment.get("tools", {}))
    definition["skills"].update(fragment.get("skills", {}))
    root = fragment["nodes"][fragment["process_id"]]
    definition["roots"][root["category"]].append(root["id"])
    publish_fixture_definition(service, definition)
    return root["id"]


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "work.sqlite3"
        self.bridge, self.model = Bridge(), Model()
        self.service = build_service(self.database, self.bridge, self.model)
        self.runtime = self.service.execution
        self.addAsyncCleanup(self.runtime.stop)
        self.p = publish(self.service, examples.operations_workflow(REFERENCES, "fixture-model"))
        self.inputs = {"project_key": "TEST", "repository": "team/example", "ops_page_id": "42"}

    async def plan(self, node_id=None, inputs=None, case_id="", p=None):
        body = {"node_id": node_id or p or self.p, "inputs": self.inputs if inputs is None else inputs}
        if case_id:
            body["case_id"] = case_id
        else:
            with self.service._db() as db:
                version = self.service._catalog(db)[0]["version"]
            body["scope"] = {"site_id": "us-a", "system": "EMS", "process_id": p or self.p, "version": version}
        result = await self.service.execution_plan(USER, body)
        self.assertTrue(result["ok"], result)
        return result["plan"]

    async def start(self, plan=None, request_id="request1"):
        plan = plan or await self.plan()
        result = await self.service.execution_action(USER, {"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": request_id})
        self.assertTrue(result["ok"], result)
        return result["run"]

    async def state(self, run):
        result = await self.service.execution_state(USER, run_id=run["id"])
        self.assertTrue(result["ok"], result)
        return result["run"]

    async def drain(self, run, cap=30):
        for _ in range(cap):
            if not await self.runtime.process_once():
                break
        return await self.state(run)

    async def control(self, run, action, **values):
        return await self.service.execution_action(USER, {"action": action, "run_id": run["id"], "expected_revision": run["revision"], "request_id": f"{action}-{run['id']}-{run['revision']}", **values})

    async def test_plan_is_metadata_only_start_receipt_and_real_projection(self):
        plan = await self.plan()
        self.assertEqual(self.bridge.calls, [])
        with self.service._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)
        run = await self.start(plan)
        duplicate = await self.start(plan)
        self.assertEqual(run["id"], duplicate["id"])
        result = await self.drain(run)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(len(self.bridge.calls), 3)
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.model.calls[0]["skills"][0]["id"], "common")
        self.assertEqual(len(result["calls"]), 4)
        case = (await self.service.get_state(USER, case_id=run["case_id"]))["case"]
        self.assertEqual(case["status"], "passed")
        self.assertTrue(all(item["status"] == "passed" for item in case["node_states"].values()))
        self.assertFalse(case["context"]["simulation"])
        self.assertTrue(all(not job["history"][0]["simulation"] for job in case["jobs"].values()))

    async def test_request_content_conflict_and_owner_isolation(self):
        plan = await self.plan()
        run = await self.start(plan)
        changed = await self.service.execution_action(USER, {"action": "start", "plan_id": plan["id"], "plan_hash": "forged", "request_id": "request1"})
        self.assertEqual(changed["error"]["code"], "request_conflict")
        self.assertFalse((await self.service.execution_state({"id": "bob"}, run_id=run["id"]))["ok"])
        other = await self.service.execution_action({"id": "bob"}, {"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": "request1"})
        self.assertEqual(other["error"]["code"], "plan_not_found")

    async def test_scope_t_then_p_reuses_completed_reads_and_summary_only_p(self):
        run = await self.start(await self.plan("new-operations-read-t"))
        run = await self.drain(run)
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(len(self.model.calls), 0)
        p_run = await self.start(await self.plan(case_id=run["case_id"]), "request2")
        p_run = await self.drain(p_run)
        self.assertEqual(p_run["status"], "succeeded", p_run)
        self.assertEqual(len(self.bridge.calls), 3)
        self.assertEqual(len(self.model.calls), 1)

    async def test_t_outside_dependencies_waits_without_call_and_j_scope_completes(self):
        run = await self.start(await self.plan("new-operations-summary-t"))
        run = await self.drain(run)
        self.assertEqual(run["status"], "waiting_dependency")
        self.assertEqual(self.bridge.calls, [])
        j = await self.start(await self.plan("new-operations-jira-j"), "jrequest")
        j = await self.drain(j)
        self.assertEqual(j["status"], "succeeded")
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_b_candidates_supplement_resume_preserves_search(self):
        p = publish(self.service, examples.installation_docs_workflow(REFERENCES))
        self.bridge.results["search_pages"] = envelope({"results": [{"page_id": "41"}, {"page_id": "42"}]})
        run = await self.start(await self.plan(p=p, inputs={"query": "install", "space_key": "TEAM"}))
        run = await self.drain(run)
        self.assertEqual(run["status"], "waiting_input", run)
        self.assertEqual(len(self.bridge.calls), 1)
        result = await self.control(run, "inputs", inputs={"page_id": "42"})
        self.assertTrue(result["ok"], result)
        result = await self.control(result["run"], "resume")
        self.assertTrue(result["ok"], result)
        run = await self.drain(result["run"])
        self.assertEqual(run["status"], "succeeded", run)
        self.assertEqual([call["function"] for call in self.bridge.calls], ["search_pages", "get_page"])
        self.assertEqual(self.bridge.calls[-1]["arguments"]["page_id"], "42")

    async def test_unknown_result_does_not_advance(self):
        self.bridge.results["jira_dashboard"] = envelope(status="unknown")
        run = await self.drain(await self.start())
        self.assertEqual(run["status"], "unknown")
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertEqual(len(self.model.calls), 0)

    async def test_forged_model_claim_rejected(self):
        self.model.forge = True
        run = await self.drain(await self.start())
        self.assertEqual(run["status"], "unknown")
        self.assertEqual(run["jobs"]["new-operations-summary-j"]["validation"]["reason"], "ungrounded_claim")

    async def test_current_acl_revoked_next_dispatch_and_read_redaction(self):
        run = await self.start()
        await self.runtime.process_once()
        self.bridge.allowed = False
        await self.runtime.process_once()
        run = await self.drain(run)
        self.assertEqual(run["status"], "waiting_authorization")
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertFalse(run["evidence_available"])
        self.assertNotIn("result", run["calls"][0])
        self.bridge.allowed = True
        result = await self.control(run, "resume")
        self.assertTrue(result["ok"], result)
        run = await self.drain(result["run"])
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(len(self.bridge.calls), 3)

    async def test_source_acl_revoked_after_start_blocks_ai_and_result_binding(self):
        run = await self.drain(await self.start(await self.plan("new-operations-read-t")))
        follow = await self.start(await self.plan("new-operations-summary-t", case_id=run["case_id"]), "follow")
        self.bridge.allowed = False
        follow = await self.drain(follow)
        self.assertEqual(follow["status"], "waiting_authorization")
        self.assertEqual(len(self.model.calls), 0)
        self.assertEqual(len(self.bridge.calls), 3)

    async def test_predispatch_rejection_and_native_auth_error_resume_with_evidence(self):
        original = self.bridge.invoke
        calls = 0
        async def reject_once(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise workflow.WorkflowError("native_access_denied", "권한 확인 필요")
            return await original(*args)
        self.bridge.invoke = reject_once
        run = await self.drain(await self.start(await self.plan("new-operations-jira-j")))
        self.assertEqual(run["status"], "waiting_authorization")
        self.assertEqual(run["calls"][0]["status"], "rejected")
        resumed = await self.control(run, "resume")
        run = await self.drain(resumed["run"])
        self.assertEqual(run["status"], "succeeded", run)
        self.assertEqual(len(run["calls"]), 2)
        self.assertEqual(len(self.bridge.calls), 1)
        self.bridge.results["jira_dashboard"] = {**envelope(status="failed"), "error": {"code": "authentication_failed"}}
        failed = await self.drain(await self.start(await self.plan("new-operations-jira-j"), "native-auth"))
        self.assertEqual(failed["status"], "waiting_authorization")
        self.bridge.results.clear()
        resumed = await self.control(failed, "resume")
        recovered = await self.drain(resumed["run"])
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["calls"][0]["status"], "failed")

    async def test_slow_io_does_not_hold_database_write_transaction_and_two_workers(self):
        self.bridge.delay = .12
        run = await self.start()
        competing = build_service(self.database, self.bridge, self.model).execution
        self.addAsyncCleanup(competing.stop)
        first = asyncio.create_task(self.runtime.process_once())
        await self.bridge.started.wait()
        with self.service._db(write=True) as db:
            db.execute("CREATE TABLE concurrent_write (value TEXT)")
            db.execute("INSERT INTO concurrent_write VALUES('unrelated')")
        self.assertFalse(await competing.process_once())
        await first
        run = await self.drain(run)
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(len(self.bridge.calls), 3)

    async def test_pause_during_io_retains_result_and_stops_next_dispatch(self):
        self.bridge.delay = .08
        run = await self.start()
        task = asyncio.create_task(self.runtime.process_once())
        await self.bridge.started.wait()
        run = await self.state(run)
        paused = await self.control(run, "pause")
        self.assertTrue(paused["ok"], paused)
        await task
        run = await self.drain(run)
        self.assertEqual(run["status"], "paused")
        self.assertEqual(len(self.bridge.calls), 1)
        resumed = await self.control(run, "resume")
        run = await self.drain(resumed["run"])
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(len(self.bridge.calls), 3)

    async def test_timeout_late_result_original_attempt_no_resume(self):
        self.bridge.delay = 1.1
        # Definition's supported minimum timeout is one second.
        with self.service._db(write=True) as db:
            catalog = self.service._catalog(db)[0]
            catalog["nodes"]["new-operations-jira-j"]["execution"]["limits"]["timeout_seconds"] = 1
            db.execute("UPDATE catalog SET published=?", (workflow._dump(catalog),))
        run = await self.start()
        await self.runtime.process_once()
        run = await self.state(run)
        self.assertEqual(run["status"], "unknown")
        await asyncio.sleep(.15)
        run = await self.state(run)
        self.assertEqual(run["calls"][0]["status"], "unknown")
        self.assertIn("late_result", run["calls"][0])
        self.assertEqual(len(self.bridge.calls), 1)
        resume = await self.control(run, "resume")
        self.assertEqual(resume["error"]["code"], "result_confirmation_required")

    async def test_cancel_inflight_is_unknown_and_late_result_never_changes_state(self):
        self.bridge.delay = .08
        run = await self.start()
        task = asyncio.create_task(self.runtime.process_once())
        await self.bridge.started.wait()
        result = await self.control(await self.state(run), "cancel")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["run"]["status"], "unknown")
        await task
        run = await self.state(run)
        self.assertEqual(run["status"], "unknown")
        self.assertIn("late_result", run["calls"][0])
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_overlap_and_legacy_bypass_denied(self):
        run = await self.start()
        plan = await self.plan(case_id=run["case_id"])
        other = await self.service.execution_action(USER, {"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": "other"})
        self.assertEqual(other["error"]["code"], "execution_overlap")
        case = (await self.service.get_state(USER, case_id=run["case_id"]))["case"]
        legacy = await self.service.handle_action(USER, {"action": "run", "case_id": case["id"], "node_id": self.p, "expected_revision": case["revision"]})
        self.assertEqual(legacy["error"]["code"], "execution_service_required")
        self.assertEqual(self.bridge.calls, [])

    async def test_changed_inputs_and_expired_results_require_new_case(self):
        run = await self.drain(await self.start(await self.plan("new-operations-read-t")))
        changed = await self.service.execution_plan(USER, {"case_id": run["case_id"], "node_id": self.p, "inputs": {**self.inputs, "ops_page_id": "99"}})
        self.assertEqual(changed["error"]["code"], "input_change_requires_new_plan")
        with self.service._db(write=True) as db:
            row = db.execute("SELECT id,data FROM execution_calls LIMIT 1").fetchone()
            call = json.loads(row["data"])
            call["ended_at"] = time.time() - 1900
            db.execute("UPDATE execution_calls SET data=? WHERE id=?", (workflow._dump(call), row["id"]))
        stale = await self.service.execution_plan(USER, {"case_id": run["case_id"], "node_id": self.p})
        self.assertEqual(stale["error"]["code"], "stale_results")

    async def test_only_classified_rate_limit_retries_once_within_declared_budget(self):
        with self.service._db(write=True) as db:
            catalog = self.service._catalog(db)[0]
            limits = catalog["nodes"]["new-operations-jira-j"]["execution"]["limits"]
            limits.update(max_retries=1, max_tool_calls=2)
            db.execute("UPDATE catalog SET published=?", (workflow._dump(catalog),))
        self.bridge.results["jira_dashboard"] = {**envelope(status="failed"), "error": {"code": "rate_limited"}}
        run = await self.start(await self.plan("new-operations-jira-j"))
        await self.runtime.process_once()
        run = await self.state(run)
        self.assertEqual(run["reason"], "retry_wait")
        self.assertFalse(await self.runtime.process_once())
        await asyncio.sleep(1.02)
        run = await self.drain(run)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(len(run["calls"]), 2)
        self.assertEqual([row["status"] for row in run["calls"]], ["failed", "failed"])

    async def test_plan_hash_expiry_and_skill_change_fail_before_dispatch(self):
        plan = await self.plan()
        forged = await self.service.execution_action(USER, {"action": "start", "plan_id": plan["id"], "plan_hash": "forged", "request_id": "forged-plan"})
        self.assertEqual(forged["error"]["code"], "plan_expired")
        with patch.object(execution.time, "time", return_value=plan["expires_at"] + 1):
            expired = await self.service.execution_action(USER, {"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": "expired-plan"})
        self.assertEqual(expired["error"]["code"], "plan_expired")
        assets = {"tools": [], "skills": [{"id": "native-skill", "name": "native skill"}], "skill_bodies": {"native-skill": "original policy"}, "skill_versions": {"native-skill": 1}, "available": True}
        self.service.asset_lookup = lambda user: deepcopy(assets)
        with self.service._db(write=True) as db:
            catalog = self.service._catalog(db)[0]
            catalog["skills"]["company"] = {"id": "company", "name": "회사 지침", "type": "instruction", "body": "", "source": "open_webui", "reference": "native-skill"}
            catalog["nodes"][self.p]["skills"] = ["company"]
            catalog["nodes"]["new-operations-jira-j"]["execution"]["skill_refs"] = [{"skill_id": "native-skill", "content_hash": execution._hash("original policy")}]
            db.execute("UPDATE catalog SET published=?", (workflow._dump(catalog),))
        run = await self.start(await self.plan("new-operations-jira-j"), "skill-change")
        assets["skill_bodies"]["native-skill"] = "changed policy"
        run = await self.drain(run)
        self.assertEqual(run["status"], "waiting_authorization")
        self.assertEqual(run["reason"], "skill_changed")
        self.assertEqual(self.bridge.calls, [])

    async def test_result_commit_failure_rolls_back_and_recovers_unknown(self):
        self.runtime.lease_seconds = .1
        run = await self.start(await self.plan("new-operations-jira-j"))
        original_event = self.runtime._event
        def fail_result_commit(db, state, kind, detail=None):
            if kind == "call_recorded":
                raise sqlite3.OperationalError("synthetic disk write failure")
            return original_event(db, state, kind, detail)
        with patch.object(self.runtime, "_event", side_effect=fail_result_commit):
            with self.assertRaises(sqlite3.OperationalError):
                await self.runtime.process_once()
        with self.service._db() as db:
            call = db.execute("SELECT state FROM execution_calls WHERE run_id=?", (run["id"],)).fetchone()
            self.assertEqual(call["state"], "running")
        await asyncio.sleep(.13)
        await self.runtime.process_once()
        recovered = await self.state(run)
        self.assertEqual(recovered["status"], "unknown")
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertNotIn("result", recovered["calls"][0])

    async def test_http_lifespan_worker_continues_after_acceptance_response(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        with patch.object(workflow, "_service", self.service):
            workflow.install(app, lambda: USER)
            with TestClient(app) as client:
                with self.service._db() as db:
                    version = self.service._catalog(db)[0]["version"]
                response = client.post("/api/ees-work/execution/plan", json={"scope": {"site_id": "us-a", "system": "EMS", "process_id": self.p, "version": version}, "node_id": "new-operations-jira-j", "inputs": self.inputs})
                self.assertEqual(response.status_code, 200, response.text)
                plan = response.json()["plan"]
                accepted = client.post("/api/ees-work/execution/action", json={"action": "start", "plan_id": plan["id"], "plan_hash": plan["hash"], "request_id": "lifespan"})
                self.assertEqual(accepted.status_code, 200, accepted.text)
                run_id = accepted.json()["run"]["id"]
                # No client polling drives execution. The server lifespan does.
                for _ in range(30):
                    await asyncio.sleep(.03)
                    with self.service._db() as db:
                        saved = json.loads(db.execute("SELECT data FROM execution_runs WHERE id=?", (run_id,)).fetchone()[0])
                    if saved["status"] == "succeeded":
                        break
                self.assertEqual(saved["status"], "succeeded")
                reconnected = client.get("/api/ees-work/execution/state", params={"run_id": run_id})
                self.assertEqual(reconnected.json()["run"]["id"], run_id)
                self.assertEqual(len(self.bridge.calls), 1)

    async def test_protocol_writer_guard_rejects_actual_previous_program(self):
        previous = ROOT / "dist/previous-source/agent-pack/skills/ees-work-demo/scripts"
        if not previous.exists():
            self.skipTest("pinned previous main source fixture unavailable")
        package = ModuleType("ees_previous_execution_test")
        package.__path__ = [str(previous)]
        sys.modules[package.__name__] = package
        old = importlib.import_module(package.__name__ + ".ees_workflow")
        run = await self.drain(await self.start(await self.plan("new-operations-jira-j")))
        old_service = old.WorkflowService(self.database, lambda key: USER, lambda key: None)
        read = await old_service.get_state(USER, case_id=run["case_id"])
        self.assertTrue(read["ok"], read)
        case = read["case"]
        result = await old_service.handle_action(USER, {"action": "run", "case_id": case["id"], "node_id": "new-operations-pr-j", "expected_revision": case["revision"], "payload": {"confirm": True}})
        self.assertEqual(result["error"]["code"], "state_unavailable")
        with self.service._db() as db:
            saved = self.service._case(db, USER["id"], case["id"])
        self.assertEqual(saved["jobs"]["new-operations-pr-j"]["status"], "pending")

    async def test_real_subprocess_queued_work_recovers_and_killed_dispatch_stays_unknown(self):
        run = await self.start(await self.plan("new-operations-jira-j"))
        program = """
import asyncio,sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'tests'))
from test_ees_workflow_execution import build_service,Bridge
async def main():
    bridge=Bridge()
    service=build_service(sys.argv[1],bridge)
    service.execution.lease_seconds=.15
    if sys.argv[2]=='slow':
        original=bridge.invoke
        async def slow(*args):
            Path(sys.argv[3]).write_text('dispatched',encoding='utf-8')
            await asyncio.sleep(60)
            return await original(*args)
        bridge.invoke=slow
    for _ in range(12):
        if not await service.execution.process_once(): break
asyncio.run(main())
"""
        # New OS process (not object reconstruction) drains a persisted queue.
        completed = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", program, str(self.database), "fast", ""], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = await self.state(run)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(len(result["calls"]), 1)
        next_run = await self.start(await self.plan("new-operations-jira-j"), "process2")
        marker = Path(self.temp.name) / "dispatched.txt"
        process = subprocess.Popen([sys.executable, "-c", program, str(self.database), "slow", str(marker)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            for _ in range(100):
                if marker.exists():
                    break
                await asyncio.sleep(.02)
            self.assertTrue(marker.exists())
            process.kill()
            await asyncio.to_thread(process.communicate, timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                await asyncio.to_thread(process.communicate, timeout=5)
        await asyncio.sleep(.2)
        await self.runtime.process_once()
        recovered = await self.state(next_run)
        self.assertEqual(recovered["status"], "unknown", recovered)
        self.assertEqual(recovered["reason"], "lease_expired")
        self.assertEqual(len(recovered["calls"]), 1)
        self.assertEqual(self.bridge.calls, [])


class NativeCapabilityRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_native_approval_disable_endpoints_return_success_after_commit(self):
        wheel = Path(os.environ.get("EES_TEST_UPSTREAM_WHEEL", ROOT / "dist/upstream/open_webui-0.11.3-py3-none-any.whl"))
        if not wheel.is_file():
            self.skipTest("pinned Native wheel unavailable")
        from ees_workflow_native_fixture import NativeReadFixture
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        fixture = NativeReadFixture(wheel)
        self.addAsyncCleanup(fixture.close)
        await fixture.start()
        refs = await fixture.register_read_tool("confluence")
        fixture.service.execution.bridge = fixture.bridge
        app = FastAPI()
        async def identity():
            return fixture.users["admin"]
        with patch.object(fixture.workflow, "_service", fixture.service):
            fixture.workflow.install(app, identity)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
                inspected = await client.get("/api/ees-work/execution/capability", params={"tool_id": refs["get_page"]["tool_id"], "function": "get_page"})
                self.assertEqual(inspected.status_code, 200, inspected.text)
                disabled = await client.post("/api/ees-work/execution/capability/action", json={"action": "disable", "reference": inspected.json()["capability"]["reference"], "evidence": "test: disable approved code"})
                self.assertEqual(disabled.status_code, 200, disabled.text)
                self.assertTrue(disabled.json()["ok"])
                self.assertEqual(disabled.json()["capability"]["state"], "disabled")
                current = await fixture.bridge.inspect(fixture.users["admin"], refs["get_page"]["tool_id"], "get_page")
                self.assertEqual(current["state"], "disabled")
                approved = await client.post("/api/ees-work/execution/capability/action", json={"action": "approve", "reference": current["reference"], "evidence": "test: reapprove pinned code"})
                self.assertEqual(approved.status_code, 200, approved.text)
                self.assertEqual(approved.json()["capability"]["state"], "allowed")
                self.assertEqual(approved.json()["capability"]["reference"]["revision"], refs["get_page"]["revision"] + 2)


if __name__ == "__main__":
    unittest.main()
