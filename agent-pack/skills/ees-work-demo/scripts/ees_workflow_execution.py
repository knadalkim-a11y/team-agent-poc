"""Durable, bounded read execution inside the existing WebUI application.

SQLite records intent before I/O; a lost lease never authorizes redispatch of
an uncertain call. No credentials, user impersonation list or tool code lives
in this store. Native remains the code/ACL/personal configuration authority.
"""

import asyncio
from copy import deepcopy
import hashlib
import json
import re
import sqlite3
import time
from uuid import uuid4

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_definition import _ancestors, _dependencies, _dump, _leaves
from .ees_workflow_view import _applicable
from .ees_workflow_contract import (
    ContractError, evaluate_completion, evaluate_final, resolve_arguments,
    validate_execution, validate_inputs,
)

TERMINAL = {"succeeded", "failed", "cancelled"}
BUSY = {"queued", "running", "paused", "waiting_input", "waiting_authorization", "waiting_dependency", "unknown"}
PLAN_TTL = 600
RUN_TTL = 1800
LEASE_SECONDS = 30
AUTH_ERRORS = {"authentication_failed", "permission_denied", "not_found_or_denied", "pat_required", "encryption_required", "configuration_required", "disabled", "user_required"}


def _value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _error(error):
    return {"ok": False, "error": {"code": error.code, "message": error.message}}


def init_execution(db):
    db.execute("CREATE TABLE IF NOT EXISTS execution_plans (id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS execution_runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, case_id TEXT NOT NULL, "
               "status TEXT NOT NULL, worker TEXT, lease REAL, data TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS execution_queue ON execution_runs(status,lease)")
    db.execute("CREATE TABLE IF NOT EXISTS execution_requests (owner TEXT NOT NULL, request_id TEXT NOT NULL, "
               "fingerprint TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(owner,request_id))")
    db.execute("CREATE TABLE IF NOT EXISTS execution_calls (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL, "
               "call_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL, worker TEXT NOT NULL, "
               "data TEXT NOT NULL, UNIQUE(run_id,job_id,call_id,attempt))")
    db.execute("CREATE TABLE IF NOT EXISTS execution_events (run_id TEXT NOT NULL, sequence INTEGER NOT NULL, "
               "data TEXT NOT NULL, PRIMARY KEY(run_id,sequence))")
    # Old programs can read new evidence but cannot run their mock writer over
    # a protocol-1 case. This guard is additive and does not touch legacy cases.
    db.execute("CREATE TRIGGER IF NOT EXISTS execution_case_insert_guard BEFORE INSERT ON cases "
               "WHEN EXISTS(SELECT 1 FROM json_each(NEW.data,'$.definition.nodes') WHERE json_extract(value,'$.execution.protocol')=1) "
               "AND json_extract(NEW.data,'$._execution_write_nonce') IS NULL "
               "BEGIN SELECT RAISE(ABORT,'execution protocol writer required'); END")
    db.execute("CREATE TRIGGER IF NOT EXISTS execution_case_update_guard BEFORE UPDATE ON cases "
               "WHEN EXISTS(SELECT 1 FROM json_each(OLD.data,'$.definition.nodes') WHERE json_extract(value,'$.execution.protocol')=1) "
               "AND (json_extract(NEW.data,'$._execution_write_nonce') IS NULL OR "
               "json_extract(NEW.data,'$._execution_write_nonce')=json_extract(OLD.data,'$._execution_write_nonce')) "
               "BEGIN SELECT RAISE(ABORT,'execution protocol writer required'); END")



class ExecutionRuntime:
    def __init__(self, service, bridge=None, model=None, *, lease_seconds=LEASE_SECONDS, poll_seconds=.2):
        self.service, self.bridge, self.model = service, bridge, model
        self.worker_id = str(uuid4())
        self.lease_seconds, self.poll_seconds = lease_seconds, poll_seconds
        self.task = None
        self._pending = set()
        self._closing = False

    def configure(self, app=None):
        if self.bridge is None:
            from .ees_workflow_native import NativeBridge
            self.bridge = NativeBridge(self.service, app)
        elif app is not None and hasattr(self.bridge, "app"):
            self.bridge.app = app
        if self.model is None and app is not None:
            from .ees_workflow_model import NativeModelAdapter
            self.model = NativeModelAdapter(self.service, app)

    def start(self):
        self._closing = False
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop(), name="ees-workflow-durable-worker")

    async def stop(self):
        self._closing = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        # Cancellation cannot prove an underlying Native thread stopped. The
        # persisted dispatch intention is retained as UNKNOWN for reconciliation.
        with self.service._db(write=True) as db:
            rows = db.execute("SELECT * FROM execution_runs WHERE worker=?", (self.worker_id,)).fetchall()
            for row in rows:
                self._recover_row(db, row, "worker_stopped")
        for task in tuple(self._pending):
            task.cancel()
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    async def _loop(self):
        while not self._closing:
            try:
                worked = await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Dispatch intent is durable, and lease recovery is the only
                # retry after unexpected failure. Raw exception text is secret.
                worked = False
            if not worked:
                await asyncio.sleep(self.poll_seconds)

    async def _access(self, user, case_id="", chat_id=""):
        current = await self.service._user(user)
        await self.service._chat(current, chat_id)
        case = None
        if case_id:
            with self.service._db() as db:
                case = self.service._case(db, _value(current, "id"), case_id, chat_id)
            await self.service._chat(current, case["chat_id"])
        return current, case

    async def _skills(self, user, case, job_id):
        assets = await self.service._assets(user)
        if not assets.get("available", True):
            raise WorkflowError("skill_unavailable", "현재 업무 지침 권한을 확인하지 못했습니다.")
        skills, instructions = [], []
        definition = case["definition"]
        if "common" in definition["skills"]:
            skills.append({"id": "common", "body": definition["skills"]["common"].get("body", "")})
        for node in _ancestors(definition["nodes"], job_id):
            if node.get("instructions"):
                instructions.append(node["instructions"])
            for key in node.get("skills", []):
                skill = definition["skills"][key]
                body = skill.get("body", "")
                if skill.get("source") == "open_webui":
                    ref = skill["reference"]
                    snapshot = case.get("_skill_snapshots", {}).get(ref)
                    if not snapshot or ref not in assets.get("skill_bodies", {}):
                        raise WorkflowError("skill_unavailable", "필수 업무 지침을 현재 계정으로 사용할 수 없습니다.")
                    if (_hash(snapshot["body"]) != _hash(assets["skill_bodies"][ref])
                            or snapshot.get("updated_at") != assets.get("skill_versions", {}).get(ref)):
                        raise WorkflowError("skill_changed", "업무 지침이 변경되었습니다. 새 계획을 검토해 주세요.")
                    body = snapshot["body"]
                if key not in {item["id"] for item in skills}:
                    skills.append({"id": key, "body": body})
        for reference in definition["nodes"][job_id].get("execution", {}).get("skill_refs", []):
            ref = reference["skill_id"]
            body = assets.get("skill_bodies", {}).get(ref)
            if body is None or _hash(body) != reference["content_hash"]:
                raise WorkflowError("skill_changed", "검증된 업무 지침의 현재 권한·내용을 다시 확인해 주세요.")
        return {"skills": skills, "instructions": instructions}

    async def _ready(self, user, case, jobs):
        self.configure()
        for job_id in jobs:
            node = case["definition"]["nodes"][job_id]
            errors = validate_execution(node, case["definition"])
            if not node.get("execution") or errors:
                raise WorkflowError("execution_contract_required", "자동 실행 계약을 검사하고 게시해 주세요.")
            await self._skills(user, case, job_id)
            await self._source_access(user, case, node)
            for call in node["execution"].get("calls", []):
                await self.bridge.check(user, call["reference"])

    async def _source_access(self, user, case, node, visiting=None, checked=None):
        """Recheck every source behind a stored value, including human choices."""
        visiting, checked = (set() if visiting is None else visiting), (set() if checked is None else checked)
        node_id = node["id"]
        if node_id in visiting:
            raise WorkflowError("result_reference_cycle", "저장 근거의 순환 연결을 확인해 주세요.")
        if node_id in checked:
            return
        visiting.add(node_id)
        try:
            refs = list(node["execution"].get("evidence", []))
            choices = node["execution"].get("completion", {}).get("choices")
            if choices:
                refs.append(choices)
            for call in node["execution"].get("calls", []):
                for binding in call.get("arguments", {}).values():
                    if binding.get("source") == "result":
                        refs.append(binding)
                    if binding.get("selection"):
                        refs.append(binding["selection"])
            for ref in refs:
                source = case["definition"]["nodes"].get(ref["job_id"])
                if not source or not source.get("execution"):
                    raise WorkflowError("result_unavailable", "선행 실행 근거를 확인해 주세요.")
                await self._skills(user, case, source["id"])
                call = next((item for item in source["execution"].get("calls", []) if item["id"] == ref["call_id"]), None)
                if call:
                    await self.bridge.check(user, call["reference"])
                elif source["execution"]["kind"] != "ai" or ref["call_id"] != "summary":
                    raise WorkflowError("result_unavailable", "허용된 선행 호출을 확인해 주세요.")
                # Earlier calls in this same J are validated by the contract;
                # their bindings are already in refs. Every cross-J source,
                # whether fixed, AI or human, must also recheck its ancestors.
                if source["id"] != node_id:
                    await self._source_access(user, case, source, visiting, checked)
            checked.add(node_id)
        finally:
            visiting.remove(node_id)

    @staticmethod
    def _inputs(schema, values):
        if not isinstance(values, dict) or len(_dump(values).encode("utf-8")) > 32_000:
            raise WorkflowError("invalid_inputs", "공개 업무 입력값과 크기를 확인해 주세요.")
        errors = validate_inputs(schema, values, partial=True)
        if errors:
            raise WorkflowError("invalid_inputs", "공개 업무 입력의 이름과 자료형을 확인해 주세요.")
        return deepcopy(values)

    async def plan(self, user, body):
        try:
            if not isinstance(body, dict) or set(body) - {"case_id", "scope", "node_id", "chat_id", "inputs"}:
                raise WorkflowError("invalid_request", "계획할 대상과 공개 입력만 전달해 주세요.")
            current, case = await self._access(user, body.get("case_id", ""), body.get("chat_id", ""))
            if case and body.get("scope"):
                raise WorkflowError("invalid_request", "진행 건 또는 새 실행 대상 하나를 선택해 주세요.")
            if not case:
                assets = await self.service._assets(current)
                with self.service._db() as db:
                    published = self.service._catalog(db)[0]
                scope = body.get("scope")
                if not isinstance(scope, dict):
                    raise WorkflowError("case_required", "실행할 현장·시스템·워크플로우를 선택해 주세요.")
                self.service._selection(published, {**scope, "node_id": body.get("node_id")})
                case = self.service._new_case(published, scope, body.get("chat_id", ""), assets)
            node = self.service._node(case, body.get("node_id"))
            jobs = [key for key in _leaves(case["definition"]["nodes"], node["id"]) if _applicable(case, key)]
            if not jobs:
                raise WorkflowError("not_applicable", "선택 대상에는 적용할 작업이 없습니다.")
            await self._ready(current, case, jobs)
            root = case["definition"]["nodes"][case["process_id"]]
            schema = root.get("execution_inputs", {"type": "object", "properties": {}, "additionalProperties": False})
            previous_inputs = case.get("execution_inputs", {})
            supplied_inputs = body.get("inputs", {})
            if not isinstance(supplied_inputs, dict):
                raise WorkflowError("invalid_inputs", "공개 입력을 확인해 주세요.")
            if any(key in previous_inputs and previous_inputs[key] != value for key, value in supplied_inputs.items()):
                raise WorkflowError("input_change_requires_new_plan", "대상이 달라진 입력은 새 진행 건에서 실행해 주세요.")
            if body.get("case_id"):
                with self.service._db() as db:
                    self._fresh_results(db, case["id"])
            values = self._inputs(schema, {**previous_inputs, **supplied_inputs})
            data = {"id": str(uuid4()), "protocol": 1, "owner": _value(current, "id"),
                    "case_id": body.get("case_id", ""), "case_snapshot": case, "node_id": node["id"],
                    "jobs": jobs, "inputs": values, "input_schema": schema, "created_at": time.time(),
                    "expires_at": time.time() + PLAN_TTL, "limits": {"duration_seconds": RUN_TTL},
                    "missing_inputs": [key for key in schema.get("required", []) if key not in values]}
            data["hash"] = _hash(data)
            with self.service._db(write=True) as db:
                db.execute("INSERT INTO execution_plans VALUES(?,?,?)", (data["id"], data["owner"], _dump(data)))
            return {"ok": True, "plan": self._public_plan(data)}
        except (WorkflowError, ContractError) as error:
            return _error(error)
        except (sqlite3.Error, TypeError, ValueError):
            return _error(WorkflowError("execution_unavailable", "실행 계획을 저장하지 못했습니다. 입력과 상태를 다시 확인해 주세요."))

    @staticmethod
    def _public_plan(plan):
        return {key: deepcopy(value) for key, value in plan.items() if key not in {"owner", "case_snapshot"}}

    def _load_run(self, db, owner, run_id):
        row = db.execute("SELECT * FROM execution_runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
        if not row:
            raise WorkflowError("run_not_found", "접근할 수 있는 실행을 찾지 못했습니다.")
        return row, json.loads(row["data"])

    def _event(self, db, run, kind, detail=None):
        seq = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM execution_events WHERE run_id=?", (run["id"],)).fetchone()[0]
        event = {"sequence": seq, "at": time.time(), "kind": kind, "status": run["status"]}
        if detail:
            event["detail"] = detail
        db.execute("INSERT INTO execution_events VALUES(?,?,?)", (run["id"], seq, _dump(event)))

    def _save(self, db, run, *, release=False):
        run["revision"] += 1
        run["updated_at"] = time.time()
        db.execute("UPDATE execution_runs SET status=?,data=?" + (",worker=NULL,lease=NULL" if release else "") + " WHERE id=?",
                   (run["status"], _dump(run), run["id"]))
        case = self.service._case(db, run["owner"], run["case_id"])
        changed = case.get("execution_status") != run["status"] or case.get("execution_node_id") != run["node_id"]
        case["execution_status"], case["execution_node_id"] = run["status"], run["node_id"]
        for job_id, item in run["jobs"].items():
            projected = ("passed" if item["status"] == "succeeded" else "running" if item["status"] == "running"
                         else "pending" if item["status"] == "pending" else "failed" if item["status"] == "failed" else "blocked")
            job = case["jobs"][job_id]
            if job["status"] != projected:
                job["status"] = projected
                changed = True
            reason = item.get("reason", "") if projected in {"blocked", "failed"} else ""
            if reason and job.get("blocked_reason") != reason:
                job["blocked_reason"] = reason
                changed = True
            elif not reason and "blocked_reason" in job:
                job.pop("blocked_reason")
                changed = True
        if changed:
            self.service._save_case(db, {"id": run["owner"]}, case)


    def _public_run(self, db, run):
        result = {key: deepcopy(value) for key, value in run.items() if key not in {"owner", "case_snapshot"}}
        result["calls"] = [json.loads(row["data"]) for row in db.execute("SELECT data FROM execution_calls WHERE run_id=? ORDER BY rowid", (run["id"],))]
        result["history"] = [json.loads(row["data"]) for row in db.execute("SELECT data FROM execution_events WHERE run_id=? ORDER BY sequence", (run["id"],))]
        return result

    async def state(self, user, case_id="", run_id="", chat_id=""):
        try:
            current, _ = await self._access(user, case_id, chat_id)
            owner = _value(current, "id")
            with self.service._db() as db:
                rows = db.execute("SELECT data FROM execution_runs WHERE owner=?" + (" AND case_id=?" if case_id else "") + " ORDER BY rowid DESC", (owner, case_id) if case_id else (owner,)).fetchall()
                runs = [json.loads(row["data"]) for row in rows]
                selected = self._load_run(db, owner, run_id)[1] if run_id else None
            visible = []
            for run in runs:
                try:
                    await self._access(current, run["case_id"], chat_id)
                except WorkflowError:
                    continue
                with self.service._db() as db:
                    public = self._public_run(db, run)
                visible.append(await self.redact_run(current, public))
            if selected:
                await self._access(current, selected["case_id"], chat_id)
                with self.service._db() as db:
                    selected = self._public_run(db, selected)
                selected = await self.redact_run(current, selected)
            return {"ok": True, "runs": visible, "run": selected or (visible[0] if case_id and visible else None)}
        except (WorkflowError, ContractError) as error:
            return _error(error)
        except sqlite3.Error:
            return _error(WorkflowError("execution_unavailable", "실행 상태를 불러오지 못했습니다."))

    async def action(self, user, body):
        try:
            if not isinstance(body, dict) or len(_dump(body).encode("utf-8")) > 40_000:
                raise WorkflowError("invalid_request", "실행 요청을 확인해 주세요.")
            allowed = {"action", "plan_id", "plan_hash", "request_id", "run_id", "expected_revision", "inputs", "job_id", "chat_id"}
            if set(body) - allowed:
                raise WorkflowError("invalid_request", "실행 요청에 허용되지 않은 값이 있습니다.")
            request_id = body.get("request_id")
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
                raise WorkflowError("invalid_request_id", "실행 요청 식별자를 확인해 주세요.")
            current, _ = await self._access(user, chat_id=body.get("chat_id", ""))
            owner, fingerprint = _value(current, "id"), _hash(body)
            with self.service._db() as db:
                receipt = db.execute("SELECT * FROM execution_requests WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
                if receipt:
                    if receipt["fingerprint"] != fingerprint:
                        raise WorkflowError("request_conflict", "같은 요청 식별자가 다른 내용에 사용되었습니다.")
                    prior = self._load_run(db, owner, receipt["run_id"])[1]
            if receipt:
                await self._access(current, prior["case_id"], body.get("chat_id", ""))
                with self.service._db() as db:
                    public = self._public_run(db, self._load_run(db, owner, prior["id"])[1])
                return {"ok": True, "run": await self.redact_run(current, public), "replayed": True}
            if body.get("action") == "start":
                result = await self._start(current, body, fingerprint)
            else:
                result = await self._control(current, body, fingerprint)
            return {"ok": True, "run": await self.redact_run(current, result), "replayed": False}
        except (WorkflowError, ContractError) as error:
            return _error(error)
        except (sqlite3.Error, TypeError, ValueError):
            return _error(WorkflowError("execution_unavailable", "실행 요청을 저장하지 못했습니다. 현재 상태를 확인해 주세요."))

    async def _start(self, user, body, fingerprint):
        owner = _value(user, "id")
        with self.service._db() as db:
            row = db.execute("SELECT data FROM execution_plans WHERE id=? AND owner=?", (body.get("plan_id"), owner)).fetchone()
        if not row:
            raise WorkflowError("plan_not_found", "접근할 수 있는 실행 계획을 찾지 못했습니다.")
        plan = json.loads(row["data"])
        if plan["hash"] != body.get("plan_hash") or plan["expires_at"] < time.time():
            raise WorkflowError("plan_expired", "실행 계획이 만료되거나 변경되었습니다. 다시 확인해 주세요.")
        planned_chat, current_chat = plan["case_snapshot"]["chat_id"], body.get("chat_id", "")
        if current_chat and planned_chat and current_chat != planned_chat:
            raise WorkflowError("chat_mismatch", "이 실행 계획을 요청한 대화에서 계속해 주세요.")
        _, case = await self._access(user, plan["case_id"], current_chat or planned_chat)
        case = case or deepcopy(plan["case_snapshot"])
        if _hash(case) != _hash(plan["case_snapshot"]):
            raise WorkflowError("revision_conflict", "진행 건이 변경되었습니다. 새 계획을 확인해 주세요.")
        await self._ready(user, case, plan["jobs"])
        with self.service._db(write=True) as db:
            receipt = db.execute("SELECT * FROM execution_requests WHERE owner=? AND request_id=?", (owner, body["request_id"])).fetchone()
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise WorkflowError("request_conflict", "같은 요청 식별자가 다른 내용에 사용되었습니다.")
                return self._public_run(db, self._load_run(db, owner, receipt["run_id"])[1])
            if plan["case_id"]:
                for previous in db.execute("SELECT data FROM execution_runs WHERE case_id=?", (case["id"],)).fetchall():
                    self._require_resolved(db, json.loads(previous["data"]))
                self._fresh_results(db, case["id"])
                latest = self.service._case(db, owner, plan["case_id"])
                if _hash(latest) != _hash(case):
                    raise WorkflowError("revision_conflict", "진행 건이 변경되었습니다. 새 계획을 확인해 주세요.")
                active = db.execute("SELECT id FROM execution_runs WHERE case_id=? AND status NOT IN ('succeeded','failed','cancelled')", (case["id"],)).fetchone()
                if active:
                    raise WorkflowError("execution_overlap", "같은 진행 건의 기존 실행을 먼저 확인해 주세요.")
            else:
                if self.service._catalog(db)[0]["version"] != case["version"]:
                    raise WorkflowError("published_version_conflict", "게시 절차가 변경되었습니다. 새 계획을 확인해 주세요.")
                if self.service._case(db, owner, "", case["chat_id"]):
                    raise WorkflowError("chat_already_bound", "이 대화에는 진행 건이 연결되어 있습니다.")
                self.service._save_case(db, user, case, new=True)
            run = {"id": str(uuid4()), "protocol": 1, "owner": owner, "case_id": case["id"],
                   "node_id": plan["node_id"], "plan_id": plan["id"], "plan_hash": plan["hash"],
                   "inputs": plan["inputs"], "input_schema": plan["input_schema"], "missing_inputs": plan["missing_inputs"],
                   "status": "queued", "revision": 0, "created_at": time.time(), "updated_at": time.time(),
                   "deadline": time.time() + RUN_TTL, "reason": "", "jobs": {}}
            for job_id in plan["jobs"]:
                saved = case["jobs"][job_id]
                valid = saved.get("execution_validation")
                run["jobs"][job_id] = {"status": "succeeded" if valid and valid["status"] == "succeeded" else "pending",
                                       "kind": case["definition"]["nodes"][job_id]["execution"]["kind"],
                                       "checks": [], "validation": valid}
            case["execution_inputs"] = deepcopy(run["inputs"])
            case["execution_run_id"] = run["id"]
            case["execution_status"], case["execution_node_id"] = run["status"], run["node_id"]
            self.service._save_case(db, user, case)
            db.execute("INSERT INTO execution_runs VALUES(?,?,?,?,NULL,NULL,?)", (run["id"], owner, case["id"], run["status"], _dump(run)))
            db.execute("INSERT INTO execution_requests VALUES(?,?,?,?)", (owner, body["request_id"], fingerprint, run["id"]))
            self._event(db, run, "accepted", {"plan_hash": plan["hash"]})
            return self._public_run(db, run)

    @staticmethod
    def _require_resolved(db, run):
        """UI status changes never reconcile an uncertain call or validation."""
        uncertain = (run["status"] == "unknown"
            or (run.get("final_validation") or {}).get("status") == "unknown"
            or any(job["status"] == "unknown" or (job.get("validation") or {}).get("status") == "unknown"
                   for job in run["jobs"].values())
            or db.execute("SELECT 1 FROM execution_calls WHERE run_id=? AND state='unknown' LIMIT 1", (run["id"],)).fetchone())
        if uncertain:
            raise WorkflowError("result_confirmation_required", "이전 호출과 판정의 결과 확인이 필요합니다. 기록을 변경하거나 재실행하지 않았습니다.")

    async def _control(self, user, body, fingerprint):
        owner = _value(user, "id")
        with self.service._db() as db:
            _, run = self._load_run(db, owner, body.get("run_id"))
        _, case = await self._access(user, run["case_id"], body.get("chat_id", ""))
        with self.service._db() as db:
            _, run = self._load_run(db, owner, body.get("run_id"))
            self._require_resolved(db, run)
        action = body.get("action")
        if action not in {"pause", "cancel", "resume", "inputs", "confirm"}:
            raise WorkflowError("invalid_action", "실행의 지원 동작을 선택해 주세요.")
        if action in {"resume", "inputs", "confirm"}:
            await self._ready(user, case, list(run["jobs"]))
        with self.service._db(write=True) as db:
            receipt = db.execute("SELECT * FROM execution_requests WHERE owner=? AND request_id=?", (owner, body["request_id"])).fetchone()
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise WorkflowError("request_conflict", "같은 요청 식별자가 다른 내용에 사용되었습니다.")
                return self._public_run(db, self._load_run(db, owner, receipt["run_id"])[1])
            row, run = self._load_run(db, owner, body.get("run_id"))
            self.service._revision(body, run["revision"])
            self._require_resolved(db, run)
            if run["status"] in TERMINAL:
                raise WorkflowError("run_completed", "종료된 실행 기록은 변경하지 않습니다.")
            inflight = db.execute("SELECT id FROM execution_calls WHERE run_id=? AND state='running'", (run["id"],)).fetchone()
            if action == "pause":
                run["status"], run["reason"] = "paused", "pause_requested"
            elif action == "cancel":
                run["status"] = "unknown" if inflight else "cancelled"
                run["reason"] = "cancellation_unconfirmed" if inflight else "cancelled_before_dispatch"
                if inflight:
                    self._unknown_calls(db, run, "cancellation_unconfirmed")
            elif action == "resume":
                if run["status"] == "unknown" or inflight:
                    raise WorkflowError("result_confirmation_required", "이전 호출의 종료를 확인하기 전에는 재실행하지 않습니다.")
                if run["deadline"] < time.time():
                    raise WorkflowError("execution_expired", "실행 허용 시간이 만료되었습니다. 새 계획을 확인해 주세요.")
                run["status"], run["reason"] = "queued", ""
                if run.get("resume_generation", 0) >= 8:
                    raise WorkflowError("resume_limit_reached", "이 실행의 재개 한도에 도달했습니다. 기존 기록을 확인한 뒤 새 계획으로 진행해 주세요.")
                run["resume_generation"] = run.get("resume_generation", 0) + 1
                run["plan_hash"] = _hash({"previous": run["plan_hash"], "resume_generation": run["resume_generation"]})
                for job in run["jobs"].values():
                    if job["status"] in {"waiting_input", "waiting_authorization", "waiting_dependency"}:
                        job["status"] = "pending"
                        job.pop("reason", None)
            elif action == "inputs":
                if inflight or run["status"] in {"queued", "running", "unknown"}:
                    raise WorkflowError("pause_required", "실행을 멈춘 뒤 필요한 입력을 보완해 주세요.")
                values = self._inputs(run["input_schema"], {**run["inputs"], **body.get("inputs", {})})
                # Supplementation keeps proven success; changing a bound value
                # after any dispatch requires a separately reviewed new case.
                changed = {key for key in run["inputs"] if values.get(key) != run["inputs"][key]}
                if changed:
                    raise WorkflowError("input_change_requires_new_plan", "기존 입력 변경은 새 실행 계획으로 진행해 주세요. 저장된 결과는 보존합니다.")
                run["inputs"] = values
                run["missing_inputs"] = [key for key in run["input_schema"].get("required", []) if key not in values]
                run["plan_hash"] = _hash({"previous": run["plan_hash"], "inputs": values, "revision": run["revision"] + 1})
                latest = self.service._case(db, owner, run["case_id"])
                latest["execution_inputs"] = deepcopy(values)
                self.service._save_case(db, user, latest)
            elif action == "confirm":
                job_id = body.get("job_id")
                if inflight or job_id not in run["jobs"] or run["jobs"][job_id]["kind"] != "human":
                    raise WorkflowError("confirmation_forbidden", "담당자 확인이 필요한 작업만 확인할 수 있습니다.")
                node = case["definition"]["nodes"][job_id]
                if any(not self._dependency_complete(case, dep) for dep in _dependencies(case["definition"]["nodes"], job_id)):
                    raise WorkflowError("prerequisite_required", "선행 작업을 먼저 완료해 주세요.")
                validation = evaluate_completion(node, {}, run["inputs"], self._results(db, run["case_id"]))
                if validation["status"] != "succeeded":
                    raise WorkflowError("input_required", "확인에 필요한 공개 입력을 먼저 보완해 주세요.")
                self._job_result(db, run, job_id, validation, kind="human_confirmation")
                run["status"], run["reason"] = "paused", "human_confirmed"
            self._save(db, run, release=not inflight)
            self._event(db, run, action, {"plan_hash": run["plan_hash"]})
            db.execute("INSERT INTO execution_requests VALUES(?,?,?,?)", (owner, body["request_id"], fingerprint, run["id"]))
            return self._public_run(db, run)

    def _unknown_calls(self, db, run, reason):
        for row in db.execute("SELECT * FROM execution_calls WHERE run_id=? AND state='running'", (run["id"],)).fetchall():
            call = json.loads(row["data"])
            call.update(status="unknown", ended_at=time.time(), reason=reason)
            db.execute("UPDATE execution_calls SET state='unknown',data=? WHERE id=?", (_dump(call), call["id"]))
            run["jobs"][call["job_id"]]["status"] = "unknown"

    def _recover_row(self, db, row, reason):
        run = json.loads(row["data"])
        inflight = db.execute("SELECT id FROM execution_calls WHERE run_id=? AND state='running'", (run["id"],)).fetchone()
        if inflight:
            self._unknown_calls(db, run, reason)
            run["status"], run["reason"] = "unknown", reason
        elif run["status"] == "running":
            run["status"], run["reason"] = "queued", "recovered_before_dispatch"
        self._save(db, run, release=True)
        self._event(db, run, "recovered", {"reason": reason})

    def _claim(self):
        with self.service._db(write=True) as db:
            for row in db.execute("SELECT * FROM execution_runs WHERE worker IS NOT NULL AND lease<?", (time.time(),)).fetchall():
                self._recover_row(db, row, "lease_expired")
            row = db.execute("SELECT * FROM execution_runs WHERE status='queued' AND worker IS NULL "
                             "AND COALESCE(json_extract(data,'$.not_before'),0)<=? ORDER BY rowid LIMIT 1", (time.time(),)).fetchone()
            if not row:
                return None
            run = json.loads(row["data"])
            try:
                self._require_resolved(db, run)
            except WorkflowError as error:
                # A prior program may already have queued an unsafe resume.
                # Recovery still cannot turn unknown evidence into permission.
                run["status"], run["reason"] = "unknown", error.code
                for call in db.execute("SELECT job_id FROM execution_calls WHERE run_id=? AND state='unknown'", (run["id"],)):
                    run["jobs"][call["job_id"]].update(status="unknown", reason=error.code)
                self._save(db, run, release=True)
                self._event(db, run, "recovered", {"reason": error.code})
                return None
            if run["deadline"] < time.time():
                run["status"], run["reason"] = "failed", "execution_expired"
                self._save(db, run, release=True)
                self._event(db, run, "expired")
                return None
            run["status"] = "running"
            db.execute("UPDATE execution_runs SET worker=?,lease=? WHERE id=?", (self.worker_id, time.time() + self.lease_seconds, run["id"]))
            self._save(db, run)
            return run

    async def _heartbeat(self, run_id):
        while True:
            await asyncio.sleep(max(.02, self.lease_seconds / 3))
            with self.service._db(write=True) as db:
                db.execute("UPDATE execution_runs SET lease=? WHERE id=? AND worker=?", (time.time() + self.lease_seconds, run_id, self.worker_id))

    @staticmethod
    def _dependency_complete(case, node_id):
        return all(not _applicable(case, key) or case["jobs"][key].get("execution_validation", {}).get("status") == "succeeded"
                   for key in _leaves(case["definition"]["nodes"], node_id))

    @staticmethod
    def _fresh_results(db, case_id):
        rows = db.execute("SELECT c.data FROM execution_calls c JOIN execution_runs r ON r.id=c.run_id "
                          "WHERE r.case_id=? AND c.state='succeeded'", (case_id,))
        if any(json.loads(row["data"]).get("ended_at", 0) < time.time() - RUN_TTL for row in rows):
            raise WorkflowError("stale_results", "이전 조회 결과의 재사용 시간이 지났습니다. 새 진행 건에서 다시 확인해 주세요.")

    def _results(self, db, case_id):
        results = {}
        rows = db.execute("SELECT c.data FROM execution_calls c JOIN execution_runs r ON r.id=c.run_id "
                          "WHERE r.case_id=? AND c.state='succeeded' ORDER BY c.rowid", (case_id,))
        for row in rows:
            call = json.loads(row["data"])
            results.setdefault(call["job_id"], {})[call["call_id"]] = call["result"]
        return results

    def _wait(self, run_id, status, reason, job_id=None):
        with self.service._db(write=True) as db:
            row = db.execute("SELECT * FROM execution_runs WHERE id=? AND worker=?", (run_id, self.worker_id)).fetchone()
            if not row:
                return
            run = json.loads(row["data"])
            if run["status"] == "running":
                run["status"], run["reason"] = status, reason
                if job_id:
                    run["jobs"][job_id].update(status=status, reason=reason)
            self._save(db, run, release=True)
            self._event(db, run, "waiting", {"reason": reason, "job_id": job_id})

    async def process_once(self):
        run = self._claim()
        if not run:
            return False
        heartbeat = asyncio.create_task(self._heartbeat(run["id"]))
        job_id = None
        try:
            current, case = await self._access({"id": run["owner"]}, run["case_id"])
            nodes = case["definition"]["nodes"]
            unfinished = [key for key, job in run["jobs"].items() if job["status"] != "succeeded"]
            if not unfinished:
                with self.service._db(write=True) as db:
                    row, latest = self._load_run(db, run["owner"], run["id"])
                    if row["worker"] != self.worker_id or latest["status"] != "running":
                        return True
                    validations = {key: value.get("validation") for key, value in latest["jobs"].items()}
                    final_checks = {}
                    for parent in sorted(nodes.values(), key=lambda item: len(_ancestors(nodes, item["id"])), reverse=True):
                        leaves = [key for key in _leaves(nodes, parent["id"]) if _applicable(case, key)]
                        if parent["type"] not in {"p", "t"} or not leaves or not set(leaves).issubset(latest["jobs"]):
                            continue
                        checked = evaluate_final(parent, validations, leaves)
                        if any(final_checks[child]["status"] != "succeeded" for child in parent["children"] if child in final_checks):
                            checked = {**checked, "status": "unknown", "reason": "child_final_incomplete", "scope_complete": False}
                        final_checks[parent["id"]] = checked
                    final = (validations[latest["node_id"]] if nodes[latest["node_id"]]["type"] == "j"
                             else final_checks[latest["node_id"]])
                    latest["final_validation"] = final
                    saved_case = self.service._case(db, run["owner"], run["case_id"])
                    saved_case.setdefault("execution_final_validations", {}).update(final_checks)
                    self.service._save_case(db, {"id": run["owner"]}, saved_case)
                    latest["status"], latest["reason"] = final["status"], final.get("reason", "")
                    self._save(db, latest, release=True)
                    self._event(db, latest, "finished")
                return True
            ready = [key for key in unfinished if all(self._dependency_complete(case, dep) for dep in _dependencies(nodes, key))]
            if not ready:
                self._wait(run["id"], "waiting_dependency", "prerequisite_required")
                return True
            job_id = ready[0]
            node, job = nodes[job_id], run["jobs"][job_id]
            context = await self._skills(current, case, job_id)
            await self._source_access(current, case, node)
            if job["kind"] == "human":
                self._wait(run["id"], "waiting_input", "human_confirmation_required", job_id)
                return True
            with self.service._db() as db:
                results = self._results(db, run["case_id"])
            calls = node["execution"].get("calls", [])
            if job["kind"] == "ai":
                calls = [{"id": "summary"}]
            pending = [call for call in calls if call["id"] not in results.get(job_id, {})]
            if not pending:
                with self.service._db(write=True) as db:
                    row, latest = self._load_run(db, run["owner"], run["id"])
                    if row["worker"] != self.worker_id or latest["status"] != "running":
                        return True
                    validation = evaluate_completion(node, results.get(job_id, {}), latest["inputs"], results)
                    self._job_result(db, latest, job_id, validation)
                    latest["status"] = "queued" if validation["status"] == "succeeded" else validation["status"]
                    latest["reason"] = validation.get("reason", "")
                    self._save(db, latest, release=True)
                    self._event(db, latest, "job_validated", {"job_id": job_id})
                return True
            call = pending[0]
            arguments = {} if job["kind"] == "ai" else resolve_arguments(call, run["inputs"], results)
            self.configure()
            if job["kind"] != "ai":
                await self.bridge.check(current, call["reference"])
            context.update(run_id=run["id"], case_id=run["case_id"], job_id=job_id, call_id=call["id"], plan_hash=run["plan_hash"],
                           limits=node["execution"].get("limits", {}), untrusted_results=True)
            with self.service._db(write=True) as db:
                row, latest = self._load_run(db, run["owner"], run["id"])
                if row["worker"] != self.worker_id or row["lease"] < time.time() or latest["status"] != "running":
                    if row["worker"] == self.worker_id:
                        self._save(db, latest, release=True)
                    return True
                attempt = db.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM execution_calls WHERE run_id=? AND job_id=? AND call_id=?",
                                     (run["id"], job_id, call["id"])).fetchone()[0]
                previous = [json.loads(item["data"]) for item in db.execute(
                    "SELECT data FROM execution_calls WHERE run_id=? AND job_id=?", (run["id"], job_id))]
                generation = latest.get("resume_generation", 0)
                dispatched = [item for item in previous if item.get("generation", 0) == generation and item["status"] != "rejected"]
                limit_key = "max_model_calls" if job["kind"] == "ai" else "max_tool_calls"
                if len(dispatched) >= node["execution"]["limits"][limit_key]:
                    latest["status"], latest["reason"] = "failed", "call_limit_reached"
                    self._save(db, latest, release=True)
                    return True
                record = {"id": str(uuid4()), "run_id": run["id"], "job_id": job_id, "call_id": call["id"],
                          "attempt": attempt, "job_attempt": case["jobs"][job_id]["attempt"] + 1,
                          "status": "running", "kind": job["kind"], "reference": call.get("reference"),
                          "arguments": arguments, "arguments_hash": _hash(arguments), "started_at": time.time(),
                          "worker": self.worker_id, "generation": generation, "input_sources": deepcopy(call.get("arguments", {}))}
                context["attempt"] = attempt
                db.execute("INSERT INTO execution_calls VALUES(?,?,?,?,?,?,?,?)", (record["id"], run["id"], job_id, call["id"], attempt, "running", self.worker_id, _dump(record)))
                latest["jobs"][job_id]["status"] = "running"
                self._save(db, latest)
                self._event(db, latest, "dispatch", {"job_id": job_id, "call_id": call["id"], "attempt": attempt})
            if job["kind"] == "ai":
                if self.model is None:
                    raise WorkflowError("model_unavailable", "요약에 사용할 모델 연결을 확인해 주세요.")
                operation = self.model.invoke(current, node, context, results, run["inputs"])
            else:
                operation = self.bridge.invoke(current, call["reference"], arguments, context)
            task = asyncio.create_task(operation)
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            timeout = min(120, max(.01, node["execution"].get("limits", {}).get("timeout_seconds", 60)), max(.01, run["deadline"] - time.time()))
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                self._finish(record, node, None, "timeout")
                task.add_done_callback(lambda completed: self._late(record["id"], completed))
            else:
                try:
                    result = task.result()
                except (WorkflowError, ContractError) as error:
                    self._finish(record, node, None, error.code, authorization=error.code != "model_result_invalid")
                except Exception:
                    self._finish(record, node, None, "call_result_unavailable")
                else:
                    self._finish(record, node, result)
            return True
        except (WorkflowError, ContractError) as error:
            with self.service._db() as db:
                active = db.execute("SELECT id FROM execution_calls WHERE run_id=? AND state='running'", (run["id"],)).fetchone()
            if active:
                self._finish(record, node, None, error.code, authorization=error.code != "model_result_invalid")
            else:
                status = "waiting_input" if error.code in {"input_required", "invalid_inputs", "invalid_selection", "result_reference_missing"} else "waiting_authorization"
                self._wait(run["id"], status, error.code, job_id)
            return True
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    def _job_result(self, db, run, job_id, validation, kind=None):
        run["jobs"][job_id].update(status=validation["status"], validation=validation,
                                   reason=validation.get("reason", ""), result=validation.get("output"))
        case = self.service._case(db, run["owner"], run["case_id"])
        job = case["jobs"][job_id]
        calls = [json.loads(row["data"]) for row in db.execute("SELECT data FROM execution_calls WHERE run_id=? AND job_id=? ORDER BY rowid", (run["id"], job_id))]
        checks = [{"id": call["call_id"], "name": call["reference"]["function"] if call.get("reference") else "근거 요약",
                   "status": "passed" if call["status"] == "succeeded" else "blocked", "simulation": False,
                   "at": call.get("ended_at"), "detail": call.get("result", {}).get("completeness", call["status"]),
                   "call_id": call["id"], "run_id": run["id"]} for call in calls]
        run["jobs"][job_id]["checks"] = checks
        status = "passed" if validation["status"] == "succeeded" else "failed" if validation["status"] == "failed" else "blocked"
        job.update(status=status, checks=checks, execution_validation=validation, execution_run_id=run["id"],
                   document=_dump(validation.get("output", {})), attempt=job["attempt"] + 1)
        job["history"].append({"at": time.time(), "attempt": job["attempt"], "status": status,
                               "kind": kind or ("ai_grounded" if run["jobs"][job_id]["kind"] == "ai" else "native_execution"),
                               "simulation": False, "run_id": run["id"], "checks": checks, "validation": validation})
        self.service._save_case(db, {"id": run["owner"]}, case)

    def _finish(self, record, node, result, reason="", authorization=False):
        with self.service._db(write=True) as db:
            row = db.execute("SELECT * FROM execution_calls WHERE id=?", (record["id"],)).fetchone()
            call = json.loads(row["data"])
            runrow, run = self._load_run(db, self._owner(db, record["run_id"]), record["run_id"])
            if row["state"] != "running" or runrow["worker"] != self.worker_id or runrow["lease"] < time.time():
                if result is not None:
                    call["late_result"] = result
                    call["late_at"] = time.time()
                    db.execute("UPDATE execution_calls SET data=? WHERE id=?", (_dump(call), call["id"]))
                return
            call.update(ended_at=time.time(), reason=reason)
            if result is None:
                call["status"] = "rejected" if authorization else "unknown"
            else:
                call["result"] = result
                call["status"] = ("failed" if result.get("status") in {"error", "failed"} else
                                  "succeeded" if result.get("status") == "succeeded" else "unknown")
            db.execute("UPDATE execution_calls SET state=?,data=? WHERE id=?", (call["status"], _dump(call), call["id"]))
            if run["status"] not in {"running", "paused"}:
                self._save(db, run, release=True)
                return
            was_paused = run["status"] == "paused"
            if call["status"] != "succeeded":
                code = reason or ((result or {}).get("error") or {}).get("code", "call_failed")
                status = "waiting_authorization" if authorization or code in AUTH_ERRORS else "unknown" if call["status"] == "unknown" else "failed"
                run["jobs"][call["job_id"]].update(status=status, reason=code)
                run["status"], run["reason"] = status, run["jobs"][call["job_id"]]["reason"]
                previous = [json.loads(item["data"]) for item in db.execute(
                    "SELECT data FROM execution_calls WHERE run_id=? AND job_id=?", (run["id"], call["job_id"]))]
                same_generation = [item for item in previous if item.get("generation", 0) == call.get("generation", 0)]
                same_call = [item for item in same_generation if item["call_id"] == call["call_id"]]
                limits = node["execution"]["limits"]
                # 429 is the one unambiguous transient classification exposed
                # by these approved read-only functions. Unknown upstream/network
                # failures never become a blind automatic retry.
                if (not was_paused and call["kind"] == "fixed" and code == "rate_limited"
                        and len(same_call) <= limits["max_retries"]
                        and len(same_generation) < limits["max_tool_calls"]):
                    run["status"], run["reason"] = "queued", "retry_wait"
                    run["not_before"] = time.time() + 1
                    run["jobs"][call["job_id"]]["status"] = "pending"
            else:
                run["jobs"][call["job_id"]]["status"] = "pending"
                run["status"] = "paused" if was_paused else "queued"
            self._save(db, run, release=True)
            self._event(db, run, "call_recorded", {"job_id": call["job_id"], "call_id": call["call_id"], "attempt": call["attempt"], "status": call["status"]})

    @staticmethod
    def _owner(db, run_id):
        return db.execute("SELECT owner FROM execution_runs WHERE id=?", (run_id,)).fetchone()[0]

    def _late(self, call_id, task):
        if task.cancelled():
            return
        try:
            result = task.result()
        except Exception:
            return
        try:
            with self.service._db(write=True) as db:
                row = db.execute("SELECT data FROM execution_calls WHERE id=?", (call_id,)).fetchone()
                if row:
                    call = json.loads(row["data"])
                    call["late_result"], call["late_at"] = result, time.time()
                    db.execute("UPDATE execution_calls SET data=? WHERE id=?", (_dump(call), call_id))
        except sqlite3.Error:
            pass

    async def _can_read_evidence(self, user, case):
        try:
            self.configure()
            for job_id, node in case["definition"]["nodes"].items():
                if not node.get("execution"):
                    continue
                await self._skills(user, case, job_id)
                for call in node["execution"].get("calls", []):
                    await self.bridge.check(user, call["reference"])
            return True
        except (WorkflowError, ContractError):
            return False

    async def redact_run(self, user, public):
        with self.service._db() as db:
            case = self.service._case(db, _value(user, "id"), public["case_id"])
        if await self._can_read_evidence(user, case):
            return public
        public["evidence_available"] = False
        for call in public.get("calls", []):
            for key in ("result", "late_result", "arguments"):
                call.pop(key, None)
            call["evidence_available"] = False
        for job in public["jobs"].values():
            for key in ("result", "validation"):
                job.pop(key, None)
        public.pop("final_validation", None)
        return public

    async def redact_case(self, user, public):
        if not public.get("execution_run_id"):
            return
        with self.service._db() as db:
            case = self.service._case(db, _value(user, "id"), public["id"])
        if await self._can_read_evidence(user, case):
            return
        public["evidence_available"] = False
        public.pop("execution_final_validations", None)
        for job in public["jobs"].values():
            if job.get("execution_run_id"):
                job["document"] = ""
                job.pop("execution_validation", None)
                for event in job["history"]:
                    event.pop("validation", None)
                job["evidence_available"] = False

    def blocks_legacy(self, db, case, node_id, action):
        if action not in {"run", "update_inputs"}:
            return False
        nodes = case["definition"]["nodes"]
        if any(nodes[key].get("execution") for key in _leaves(nodes, node_id)):
            return True
        return db.execute("SELECT id FROM execution_runs WHERE case_id=? AND status NOT IN ('succeeded','failed','cancelled')", (case["id"],)).fetchone() is not None
