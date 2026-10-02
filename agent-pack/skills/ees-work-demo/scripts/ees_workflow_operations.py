"""Schedules and reviewed requests inside the existing workflow SQLite service.

This module does not contain an EES connector. A reviewed Native function is a
contract, never an arbitrary URL/program. Without a configured server adapter,
requests are explicitly blocked. Test transports are injected only by tests.
"""
from __future__ import annotations

import asyncio
from calendar import monthrange
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ees_workflow_authoring import WorkflowError

INTENT_TTL = 120
LEASE_SECONDS = 30
REQUEST_STATES = {"prepared", "approval_pending", "ready", "requested", "accepted", "running", "reported_complete", "effect_verified", "failed", "rejected", "unknown", "blocked"}
SECRET_KEY = re.compile(r"(^|_)(pat|password|secret|token|cookie|authorization|headers)($|_)", re.I)


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(obj):
    return hashlib.sha256(dump(obj).encode()).hexdigest()


def fail(code, message="현재 권한·입력·버전을 다시 확인해 주세요."):
    raise WorkflowError(code, message)


def clean(value_, depth=0):
    """Reject secret fields, non-JSON numbers and unbounded input before storage."""
    if depth > 12:
        fail("input_too_deep")
    if isinstance(value_, dict):
        if any(not isinstance(key, str) or SECRET_KEY.search(key) for key in value_):
            fail("secret_input_forbidden", "비밀정보는 Native 개인 설정에 보관해 주세요.")
        return {key: clean(item, depth + 1) for key, item in value_.items()}
    if isinstance(value_, list):
        if len(value_) > 1000:
            fail("input_too_large")
        return [clean(item, depth + 1) for item in value_]
    if value_ is None or type(value_) in (str, bool, int, float):
        try:
            if len(dump(value_)) > 100_000:
                fail("input_too_large")
        except (ValueError, TypeError):
            fail("input_invalid")
        return value_
    fail("input_invalid")


def identifier(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", raw):
        fail("identifier_invalid")
    return raw


def schema_check(schema, inputs):
    """Bounded contract subset; no remote refs, executable predicates or coercion."""
    if not isinstance(schema, dict) or schema.get("type", "object") != "object" or not isinstance(inputs, dict):
        fail("request_schema_invalid")
    props = schema.get("properties", {})
    if not isinstance(props, dict) or set(inputs) - set(props):
        fail("request_arguments_invalid")
    if any(key not in inputs for key in schema.get("required", [])):
        fail("required_input", "필수 입력을 확인해 주세요.")
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
    for key, item in inputs.items():
        spec = props[key]
        kind = spec.get("type")
        if kind not in types or not isinstance(item, types[kind]) or (kind in ("integer", "number") and type(item) is bool):
            fail("request_arguments_invalid")
        if "enum" in spec and item not in spec["enum"]:
            fail("request_arguments_invalid")
        if isinstance(item, str) and (len(item) > spec.get("maxLength", 20000) or len(item) < spec.get("minLength", 0)):
            fail("request_arguments_invalid")
        if kind in ("integer", "number") and (item < spec.get("minimum", float("-inf")) or item > spec.get("maximum", float("inf"))):
            fail("request_arguments_invalid")
        if kind == "object":
            schema_check(spec, item)
        if kind == "array":
            if len(item) > spec.get("maxItems", 1000):
                fail("request_arguments_invalid")
            for element in item:
                schema_check({"properties": {"item": spec.get("items", {})}}, {"item": element})
    clean(inputs)


def validate_output_schema(schema, depth=0):
    """Validate the bounded JSON contract accepted by reviewed request tools."""
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "title", "description", "default"}
    kinds = {"object", "array", "string", "integer", "number", "boolean", "null"}
    if not isinstance(schema, dict) or depth > 12 or set(schema) - allowed or schema.get("type") not in kinds or depth == 0 and schema.get("type") != "object":
        fail("request_output_schema_invalid", "결과 형식은 지원하는 기본 JSON 객체 schema로 작성해 주세요.")
    clean(schema)
    kind = schema["type"]
    if any(key in schema and not isinstance(schema[key], str) for key in ("title", "description")):
        fail("request_output_schema_invalid")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        fail("request_output_schema_invalid")
    for low, high in (("minimum", "maximum"), ("minLength", "maxLength"), ("minItems", "maxItems")):
        for key in (low, high):
            if key in schema and (type(schema[key]) not in (int, float) or key not in ("minimum", "maximum") and (type(schema[key]) is not int or schema[key] < 0)):
                fail("request_output_schema_invalid")
        if low in schema and high in schema and schema[low] > schema[high]:
            fail("request_output_schema_invalid")
    if kind == "object":
        props, required = schema.get("properties", {}), schema.get("required", [])
        if not isinstance(props, dict) or len(props) > 100 or not isinstance(required, list) or any(not isinstance(key, str) or key not in props for key in required) or len(set(required)) != len(required) or "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
            fail("request_output_schema_invalid")
        for child in props.values():
            validate_output_schema(child, depth + 1)
    elif any(key in schema for key in ("properties", "required", "additionalProperties")):
        fail("request_output_schema_invalid")
    if kind == "array":
        validate_output_schema(schema.get("items"), depth + 1)
    elif "items" in schema:
        fail("request_output_schema_invalid")


def next_slot(rule, after):
    """Return the first local calendar slot strictly after a UTC timestamp.

    Ambiguous fall-back times use fold=0; nonexistent spring-forward local times
    are skipped. The time zone and calendar rule are explicit persisted values.
    """
    try:
        zone = ZoneInfo(rule["timezone"])
        anchor = datetime.fromisoformat(rule["anchor"])
        if anchor.tzinfo is not None:
            anchor = anchor.astimezone(zone).replace(tzinfo=None)
        frequency = rule["frequency"]
        interval = rule.get("interval", 1)
        if type(interval) is not int or not 1 <= interval <= 366:
            raise ValueError()
        if frequency not in ("daily", "weekly", "monthly"):
            raise ValueError()
        local_after = datetime.fromtimestamp(after, zone).replace(tzinfo=None)
        if frequency == "monthly":
            distance = (local_after.year - anchor.year) * 12 + local_after.month - anchor.month
            step = max(0, distance // interval - 1)
        else:
            days = interval * (7 if frequency == "weekly" else 1)
            step = max(0, (local_after - anchor).days // days - 1)
        for index in range(step, step + 400):
            if frequency == "monthly":
                month = anchor.year * 12 + anchor.month - 1 + interval * index
                year, month = divmod(month, 12)
                month += 1
                candidate = anchor.replace(year=year, month=month, day=min(anchor.day, monthrange(year, month)[1]))
            else:
                candidate = anchor + timedelta(days=days * index)
            aware = candidate.replace(tzinfo=zone, fold=0)
            stamp = aware.timestamp()
            if datetime.fromtimestamp(stamp, zone).replace(tzinfo=None) != candidate:
                continue
            if stamp > after:
                return stamp
    except (KeyError, TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
        fail("schedule_rule_invalid", "시간대·기준일·반복 주기를 확인해 주세요.")
    fail("schedule_rule_invalid")


def init_operations(db):
    required = {"work_tool_contracts", "work_operation_receipts", "work_operation_events", "work_external_requests", "work_request_intents", "work_schedules", "work_schedule_slots", "work_job_claims", "work_scope_runs"}
    existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = existing & required
    if present and present != required:
        fail("workspace_upgrade_required", "업무 실행 저장소 구조가 불완전합니다. 백업과 프로그램 버전을 확인해 주세요.")
    if "work_operations_schema" in existing:
        row = db.execute("SELECT version FROM work_operations_schema WHERE id=1").fetchone()
        if not row or row[0] != 1 or present != required:
            fail("workspace_upgrade_required", "지원하는 실행 저장소 버전과 백업을 확인해 주세요.")
    # Only a complete pre-marker development schema may be adopted. Missing
    # existing tables never become empty replacements or silent resets.
    db.execute("CREATE TABLE IF NOT EXISTS work_operations_schema(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL)")
    db.execute("INSERT OR IGNORE INTO work_operations_schema VALUES(1,1)")
    db.execute("CREATE TABLE IF NOT EXISTS work_tool_contracts(id TEXT PRIMARY KEY,system_id TEXT NOT NULL,revision INTEGER NOT NULL,state TEXT NOT NULL,data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS work_operation_receipts(actor TEXT NOT NULL,request_id TEXT NOT NULL,payload_hash TEXT NOT NULL,outcome TEXT NOT NULL,PRIMARY KEY(actor,request_id))")
    db.execute("CREATE TABLE IF NOT EXISTS work_operation_events(id INTEGER PRIMARY KEY AUTOINCREMENT,target TEXT NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,created_at REAL NOT NULL,data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS work_external_requests(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,job_id TEXT NOT NULL,actor TEXT NOT NULL,revision INTEGER NOT NULL,state TEXT NOT NULL,data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS work_request_intents(hash TEXT PRIMARY KEY,request_id TEXT NOT NULL,actor TEXT NOT NULL,binding TEXT NOT NULL,expires REAL NOT NULL,consumed INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS work_schedules(id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,scope TEXT NOT NULL,actor TEXT NOT NULL,revision INTEGER NOT NULL,enabled INTEGER NOT NULL,next_at REAL NOT NULL,data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS work_schedule_slots(id TEXT PRIMARY KEY,schedule_id TEXT NOT NULL,workflow_id TEXT NOT NULL,scope TEXT NOT NULL,scheduled_at REAL NOT NULL,status TEXT NOT NULL,worker TEXT,lease REAL,data TEXT NOT NULL,UNIQUE(workflow_id,scope,scheduled_at))")
    db.execute("CREATE INDEX IF NOT EXISTS work_schedule_due ON work_schedules(enabled,next_at)")
    db.execute("CREATE INDEX IF NOT EXISTS work_schedule_queue ON work_schedule_slots(status,lease)")
    db.execute("CREATE TABLE IF NOT EXISTS work_scope_runs(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,actor TEXT NOT NULL,status TEXT NOT NULL,worker TEXT,lease REAL,data TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS work_scope_queue ON work_scope_runs(status,lease)")
    db.execute("CREATE TABLE IF NOT EXISTS work_job_claims(attempt_id TEXT PRIMARY KEY,actor TEXT NOT NULL,worker TEXT,lease REAL,state TEXT NOT NULL)")


class OperationsRuntime:
    def __init__(self, service, bridge=None, model=None, *, connector=None, clock=time.time, lease_seconds=LEASE_SECONDS):
        self.service, self.bridge, self.model, self.connector = service, bridge, model, connector
        self.clock, self.lease_seconds = clock, lease_seconds
        self.worker = str(uuid4())
        self.task = None
        self._closing = False
        with service._db(write=True) as db:
            init_operations(db)

    def configure(self, app=None):
        if self.bridge is None:
            from .ees_workflow_native import NativeBridge
            self.bridge = NativeBridge(self.service, app)
        elif app is not None and hasattr(self.bridge, "app"):
            self.bridge.app = app
        if self.model is None and app is not None:
            from .ees_workflow_model import NativeModelAdapter
            self.model = NativeModelAdapter(self.service, app)

    async def _actor(self, user):
        return await self.service._work_actor(user)

    def _scope(self, db, actor, groups, system, factory="", role="participant"):
        return self.service._work_authorize_scope(db, actor, groups, system, factory, role={"owner": "manager", "approver": "reviewer"}.get(role, role))

    def _event(self, db, target, actor, kind, detail):
        db.execute("INSERT INTO work_operation_events(target,actor,kind,created_at,data) VALUES(?,?,?,?,?)", (target, value(actor, "id", actor), kind, self.clock(), dump(clean(detail))))

    def _receipt(self, db, actor, body):
        key = identifier(body.get("request_id"))
        row = db.execute("SELECT * FROM work_operation_receipts WHERE actor=? AND request_id=?", (value(actor, "id"), key)).fetchone()
        if row:
            if row["payload_hash"] != digest(body):
                fail("request_conflict", "같은 요청 번호의 내용이 달라졌습니다.")
            return json.loads(row["outcome"])
        return None

    def _remember(self, db, actor, body, outcome):
        # Confirmation tokens are returned once only and are never stored in a
        # generic receipt or exposed through state/history retrieval.
        saved = {key: val for key, val in outcome.items() if key != "intent_token"}
        db.execute("INSERT INTO work_operation_receipts VALUES(?,?,?,?)", (value(actor, "id"), body["request_id"], digest(body), dump(saved)))
        return outcome

    @staticmethod
    def _revision(body, current):
        if type(body.get("expected_revision")) is not int or body["expected_revision"] != current:
            fail("revision_conflict", "다른 변경이 저장되었습니다. 최신 내용을 다시 확인해 주세요.")

    def _tool(self, db, tool_id):
        row = db.execute("SELECT data FROM work_tool_contracts WHERE id=?", (identifier(tool_id),)).fetchone()
        if not row:
            fail("tool_not_found")
        return json.loads(row[0])

    def _request(self, db, actor, groups, key, *, write=False):
        row = db.execute("SELECT data FROM work_external_requests WHERE id=?", (identifier(key),)).fetchone()
        if not row:
            fail("request_not_found")
        request = json.loads(row[0])
        self.service._work_run(db, actor, groups, request["run_id"], write=write)
        return request

    def _save_request(self, db, request):
        db.execute("INSERT INTO work_external_requests VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state=excluded.state,data=excluded.data", (request["id"], request["run_id"], request["job_id"], request["actor"], request["revision"], request["state"], dump(request)))

    async def _inspect_reference(self, actor, reference, kind):
        self.configure()
        if kind == "read":
            result = await self.bridge.inspect(actor, reference.get("tool_id", ""), reference.get("function", ""))
        else:
            result = await self.bridge.inspect_registered(actor, reference.get("tool_id", ""), reference.get("function", ""))
        if result["reference"] != reference:
            fail("native_version_changed")
        return result

    async def command(self, user, body):
        if not isinstance(body, dict):
            fail("command_invalid")
        actor, caps, groups = await self._actor(user)
        action = body.get("action")
        if action == "execute_scope":
            return await self._scope_command(actor, groups, body)
        if action == "execute_job":
            return await self.execute(actor, body)
        if action == "request_dispatch":
            return await self._dispatch(actor, groups, body)
        if action == "request_reconcile":
            return await self._reconcile(actor, groups, body)
        if action in {"tool_save", "tool_submit", "tool_review"}:
            return await self._tool_command(actor, groups, body)
        if action in {"schedule_save", "schedule_disable", "schedule_check"}:
            return await self._schedule_command(actor, groups, body)
        if action not in {"request_prepare", "request_approve", "request_intent", "request_cancel"}:
            fail("command_invalid")
        # Read current Native contract outside the write transaction, then
        # compare its stored revision again inside the atomic command.
        with self.service._db() as db:
            if action == "request_prepare":
                run = self.service._work_run(db, actor, groups, identifier(body.get("run_id")), write=True)
                tool = self._tool(db, body.get("tool_contract_id"))
            else:
                request = self._request(db, actor, groups, body.get("external_request_id"), write=True)
                tool = self._tool(db, request["tool_contract_id"])
                run = self.service._work_run(db, actor, groups, request["run_id"], write=True)
            self._scope(db, actor, groups, run["system_id"], run["factory_id"], "requester" if action != "request_approve" else "approver")
        await self._inspect_reference(actor, tool["reference"], tool["kind"])
        actor, caps, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            current_run = self.service._work_run(db, actor, groups, run["id"], write=True)
            self._scope(db, actor, groups, current_run["system_id"], current_run["factory_id"], "approver" if action == "request_approve" else "requester")
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            current_tool = self._tool(db, tool["id"])
            if current_tool["revision"] != tool["revision"] or current_tool["state"] != "approved" or current_tool["kind"] != "request":
                fail("tool_review_required")
            run = self.service._work_run(db, actor, groups, run["id"], write=True)
            self._scope(db, actor, groups, run["system_id"], run["factory_id"], "approver" if action == "request_approve" else "requester")
            if action == "request_prepare":
                self._revision(body, run["revision"])
                job_id = identifier(body.get("job_id"))
                snapshot = self.service._work_snapshot(db, run, job_id)
                job = snapshot["job"]
                if (job.get("tool_contract_id") or (job.get("tool_reference") or {}).get("contract_id")) != tool["id"] or self._job_kind(job) != "request":
                    fail("request_job_mismatch")
                if job.get("tool_contract_revision") != tool["revision"]:
                    fail("tool_contract_changed", "게시된 도구 계약이 바뀌었습니다. 절차를 다시 검사·게시해 주세요.")
                required = job.get("approval_count", 0)
                if type(required) is not int or required not in (0, 1, 2):
                    fail("approval_count_invalid")
                inputs = self._arguments(job, snapshot.get("inputs", {})) if job.get("argument_bindings") else deepcopy(snapshot.get("inputs", {}))
                if "inputs" in body and digest(clean(body["inputs"])) != digest(inputs):
                    fail("request_input_mismatch", "저장된 이번 입력과 요청 대상이 다릅니다. 값을 먼저 저장해 주세요.")
                source_hash = digest({"inputs": snapshot.get("inputs", {}), "sources": snapshot.get("settings_sources", {})})
                schema_check(tool["input_schema"], inputs)
                previous = db.execute("SELECT data FROM work_external_requests WHERE run_id=? AND job_id=?", (run["id"], job_id)).fetchall()
                if any(json.loads(row[0])["state"] in {"requested", "accepted", "running", "reported_complete", "unknown"} for row in previous):
                    fail("previous_request_unresolved", "이전 요청의 접수·효과를 먼저 확인해 주세요. 자동 재요청하지 않습니다.")
                request = {"id": str(uuid4()), "run_id": run["id"], "job_id": job_id, "actor": value(actor, "id"), "revision": 1, "run_revision": run["revision"], "tool_contract_id": tool["id"], "tool_revision": tool["revision"], "reference": deepcopy(tool["reference"]), "input_hash": digest(inputs), "input_source_hash": source_hash, "inputs": inputs, "approval_count": required, "approvals": [], "state": "approval_pending" if required else "ready", "created_at": self.clock(), "effect_criterion": deepcopy(job.get("effect_criterion", {})), "correlation_id": str(uuid4()), "job_number": None, "reported_complete": False, "effect_verified": False, "connector_configured": self.connector is not None}
            else:
                request = self._request(db, actor, groups, request["id"], write=True)
                self._revision(body, request["revision"])
                current_snapshot = self.service._work_snapshot(db, run, request["job_id"])
                if request["input_source_hash"] != digest({"inputs": current_snapshot["inputs"], "sources": current_snapshot["settings_sources"]}) or request["tool_revision"] != tool["revision"] or request["run_revision"] != run["revision"]:
                    fail("request_stale", "입력·작업·도구가 바뀌었습니다. 요청과 승인을 다시 준비해 주세요.")
                if action == "request_cancel":
                    if request["actor"] != value(actor, "id") or request["state"] not in {"ready", "approval_pending", "prepared"}:
                        fail("request_not_cancellable")
                    request["state"] = "rejected"
                    request["revision"] += 1
                elif action == "request_approve":
                    if request["actor"] == value(actor, "id"):
                        fail("self_approval_forbidden")
                    if request["state"] not in {"approval_pending", "ready"}:
                        fail("request_not_approvable")
                    if len(request["approvals"]) >= request["approval_count"]:
                        fail("approval_already_satisfied")
                    if value(actor, "id") in {row["actor"] for row in request["approvals"]}:
                        fail("approval_duplicate")
                    request["approvals"].append({"actor": value(actor, "id"), "at": self.clock(), "input_hash": request["input_hash"], "tool_revision": tool["revision"]})
                    request["state"] = "ready" if len(request["approvals"]) >= request["approval_count"] else "approval_pending"
                    request["revision"] += 1
                else:
                    if request["actor"] != value(actor, "id") or request["state"] != "ready":
                        fail("request_confirmation_not_ready")
                    token = secrets.token_urlsafe(32)
                    binding = self._binding(request)
                    db.execute("INSERT INTO work_request_intents(hash,request_id,actor,binding,expires) VALUES(?,?,?,?,?)", (digest(token), request["id"], value(actor, "id"), digest(binding), self.clock() + INTENT_TTL))
                    outcome = {"ok": True, "request": self._public_request(request), "intent_token": token, "expires_at": self.clock() + INTENT_TTL}
                    return self._remember(db, actor, body, outcome)
            self._save_request(db, request)
            self._event(db, request["id"], actor, action, {"revision": request["revision"], "state": request["state"]})
            return self._remember(db, actor, body, {"ok": True, "request": self._public_request(request)})

    @staticmethod
    def _binding(request):
        return {"action": "request_dispatch", **{key: request[key] for key in ("id", "actor", "revision", "run_revision", "tool_revision", "input_hash", "input_source_hash", "approvals", "state")}}

    @staticmethod
    def _public_request(request):
        return {key: deepcopy(val) for key, val in request.items() if key not in {"inputs", "reference"}}

    async def _tool_command(self, actor, groups, body):
        action = body["action"]
        if action == "tool_save":
            data = clean(body.get("tool", {}))
            kind = data.get("kind", "read")
            if kind not in {"read", "request"}:
                fail("tool_kind_invalid")
            system = identifier(data.get("system_id"))
            with self.service._db() as db:
                self._scope(db, actor, groups, system, role="owner")
            reference = data.get("reference", {})
            data["reference"] = reference
            checked = await self._inspect_reference(actor, reference, kind) if reference else {"schema": {"type": "object", "properties": {}, "required": []}}
            # Input declarations always come from the registered function. The
            # editor cannot add an arbitrary URL/shell argument to the schema.
            schema = checked["schema"]
            if data.get("input_schema", schema) != schema:
                fail("native_schema_mismatch")
            data["input_schema"] = schema
        else:
            with self.service._db() as db:
                data = self._tool(db, body.get("tool_contract_id"))
                self._scope(db, actor, groups, data["system_id"], role="owner")
            checked = await self._inspect_reference(actor, data["reference"], data["kind"])
            if data["kind"] == "request" and data.get("status_function"):
                status_contract = await self.bridge.inspect_registered(actor, data["reference"]["tool_id"], data["status_function"])
                if action == "tool_review" and data.get("status_reference") != status_contract["reference"]:
                    fail("native_version_changed")
                data["status_reference"] = status_contract["reference"]
        actor, caps, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            self._scope(db, actor, groups, data["system_id"], role="owner")
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            key = identifier(data.get("id", body.get("tool_contract_id", str(uuid4()))))
            row = db.execute("SELECT data FROM work_tool_contracts WHERE id=?", (key,)).fetchone()
            previous = json.loads(row[0]) if row else None
            self._revision(body, previous["revision"] if previous else 0)
            if action == "tool_save":
                if previous and previous["system_id"] != data["system_id"]:
                    fail("tool_system_immutable")
                data = {**data, "id": key, "revision": (previous["revision"] if previous else 0) + 1, "state": "draft", "editor": value(actor, "id"), "updated_at": self.clock(), "reviewer": None}
            elif action == "tool_submit":
                data = previous
                guide = urlsplit(data.get("guide_url", ""))
                if guide.scheme not in {"https", "http"} or not guide.netloc or guide.username or guide.password:
                    fail("guide_required", "담당자가 확인할 기능 가이드 링크가 필요합니다.")
                if data["kind"] == "request" and (not data.get("status_function") or not data.get("output_schema") or not data.get("responsible_user_id")):
                    fail("request_contract_incomplete", "EES 기능·상태 조회·결과 형식·담당자를 확인해 주세요.")
                if data["kind"] == "request":
                    validate_output_schema(data["output_schema"])
                if data["state"] not in {"draft", "rejected"}:
                    fail("tool_state_conflict")
                data["state"] = "review_requested"
                if data["kind"] == "request":
                    data["status_reference"] = status_contract["reference"]
                data["revision"] += 1
            else:
                data = previous
                if data["state"] != "review_requested" or body.get("decision") not in {"approve", "reject"}:
                    fail("tool_state_conflict")
                if data["kind"] == "request" and data.get("responsible_user_id") != value(actor, "id"):
                    fail("responsible_reviewer_required")
                if data["kind"] == "request" and body["decision"] == "approve":
                    validate_output_schema(data.get("output_schema"))
                if data["kind"] == "read" and body["decision"] == "approve" and checked.get("state") != "allowed":
                    data["reference"] = self.bridge.store_approval(db, actor, data["reference"], body.get("evidence", ""))["reference"]
                data["state"] = "approved" if body["decision"] == "approve" else "rejected"
                data["reviewer"] = value(actor, "id")
                data["reviewed_at"] = self.clock()
                data["revision"] += 1
            db.execute("INSERT INTO work_tool_contracts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state=excluded.state,data=excluded.data", (key, data["system_id"], data["revision"], data["state"], dump(data)))
            self._event(db, key, actor, action, {"revision": data["revision"], "state": data["state"]})
            return self._remember(db, actor, body, {"ok": True, "tool": data})

    async def _approved_request(self, actor, groups, request_id):
        with self.service._db() as db:
            request = self._request(db, actor, groups, request_id, write=True)
            run = self.service._work_run(db, actor, groups, request["run_id"], write=True)
            self._scope(db, actor, groups, run["system_id"], run["factory_id"], "requester")
            tool = self._tool(db, request["tool_contract_id"])
            snapshot = self.service._work_snapshot(db, run, request["job_id"])
        if request["input_source_hash"] != digest({"inputs": snapshot["inputs"], "sources": snapshot["settings_sources"]}) or tool["state"] != "approved" or tool["revision"] != request["tool_revision"] or request["run_revision"] != run["revision"]:
            fail("request_stale")
        await self._inspect_reference(actor, request["reference"], "request")
        status_contract = await self.bridge.inspect_registered(actor, tool["reference"]["tool_id"], tool["status_function"])
        if status_contract["reference"] != tool.get("status_reference"):
            fail("native_version_changed")
        # Every approval must still be held by a distinct current approver.
        approvers = set()
        for approval in request["approvals"]:
            approver, _, members = await self._actor({"id": approval["actor"]})
            with self.service._db() as db:
                self._scope(db, approver, members, run["system_id"], run["factory_id"], "approver")
            if approval["actor"] == request["actor"] or approval["input_hash"] != request["input_hash"] or approval["tool_revision"] != request["tool_revision"]:
                fail("approval_stale")
            approvers.add(approval["actor"])
        if len(approvers) < request["approval_count"]:
            fail("approval_required")
        return request, tool

    async def _dispatch(self, actor, groups, body):
        request, tool = await self._approved_request(actor, groups, body.get("external_request_id"))
        if request["actor"] != value(actor, "id"):
            fail("request_actor_mismatch")
        options_snapshot = await self.service._work_resolve_job_options(actor, request["run_id"], request["job_id"])
        actor, _, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            current = self._request(db, actor, groups, request["id"], write=True)
            latest_tool = self._tool(db, request["tool_contract_id"])
            current_run = self.service._work_run(db, actor, groups, request["run_id"], write=True)
            self._scope(db, actor, groups, current_run["system_id"], current_run["factory_id"], "requester")
            self._revision(body, current["revision"])
            latest_snapshot = self.service._work_snapshot(db, current_run, request["job_id"])
            if request["input_source_hash"] != digest({"inputs": latest_snapshot["inputs"], "sources": latest_snapshot["settings_sources"]}) or latest_tool["state"] != "approved" or latest_tool["revision"] != request["tool_revision"] or current_run["revision"] != request["run_revision"] or current != request or current["state"] != "ready":
                fail("request_stale")
            intent = db.execute("SELECT * FROM work_request_intents WHERE hash=?", (digest(body.get("intent_token", "")),)).fetchone()
            if not intent or intent["consumed"] or intent["expires"] <= self.clock() or intent["request_id"] != request["id"] or intent["actor"] != value(actor, "id") or intent["binding"] != digest(self._binding(request)):
                fail("confirmation_expired", "요청 내용을 다시 확인해 주세요.")
            db.execute("UPDATE work_request_intents SET consumed=1 WHERE hash=?", (intent["hash"],))
            if self.connector is None:
                request.update(state="blocked", reason="ees_connector_unconfigured", revision=request["revision"] + 1)
                self._save_request(db, request)
                return self._remember(db, actor, body, {"ok": False, "request": self._public_request(request), "error": {"code": "ees_connector_unconfigured", "message": "실제 EES 기능·인증·상태 조회 연결을 설정한 뒤 요청할 수 있습니다."}})
            unresolved = db.execute("SELECT id FROM work_external_requests WHERE run_id=? AND job_id=? AND id<>? AND state IN ('requested','accepted','running','reported_complete','unknown')", (request["run_id"], request["job_id"], request["id"])).fetchone()
            if unresolved:
                fail("previous_request_unresolved")
            attempt = self.service._work_begin_attempt(db, actor, groups, request["run_id"], request["job_id"], request["run_revision"], options_snapshot=options_snapshot)
            request["attempt_id"] = attempt["id"]
            request.update(state="requested", requested_at=self.clock(), revision=request["revision"] + 1)
            self._save_request(db, request)
            self._event(db, request["id"], actor, "request_dispatch", {"state": "requested", "correlation_id": request["correlation_id"]})
            outcome = {"ok": True, "request": self._public_request(request)}
            self._remember(db, actor, body, outcome)
        # Durable request exists before network I/O. A timeout is UNKNOWN and
        # cannot enter this path again, even after a worker or browser restart.
        try:
            result = await self.connector.request(actor, deepcopy(tool), deepcopy(request["inputs"]), request["correlation_id"])
        except BaseException as error:
            self._observe(request["id"], "unknown", {"reason": "request_result_unknown"})
            if isinstance(error, asyncio.CancelledError):
                raise
        else:
            self._record_external(request["id"], result)
        with self.service._db() as db:
            result = self._request(db, actor, groups, request["id"])
        return {"ok": result["state"] not in {"failed", "rejected", "unknown"}, "request": self._public_request(result)}

    def _observe(self, request_id, state, details):
        if state not in REQUEST_STATES:
            fail("external_state_invalid")
        with self.service._db(write=True) as db:
            row = db.execute("SELECT data FROM work_external_requests WHERE id=?", (request_id,)).fetchone()
            request = json.loads(row[0])
            if request["state"] == "effect_verified":
                return  # A later stale poll cannot erase a verified receipt.
            request.update(clean(details))
            request["state"] = state
            request["revision"] += 1
            request["observed_at"] = self.clock()
            self._save_request(db, request)
            if request.get("attempt_id") and state in {"effect_verified", "failed", "rejected"}:
                attempt = db.execute("SELECT status FROM work_attempts WHERE id=?", (request["attempt_id"],)).fetchone()
                if attempt and attempt[0] == "running":
                    self.service._work_finish_attempt(db, request["attempt_id"], "succeeded" if state == "effect_verified" else "failed", {"status": "succeeded" if state == "effect_verified" else "failed", "completeness": "complete", "external_request_id": request_id, "reported_complete": request.get("reported_complete", False), "effect_verified": request.get("effect_verified", False), "effect_evidence": request.get("effect_evidence", [])})
            if request.get("attempt_id") and state == "unknown":
                db.execute("UPDATE work_jobs SET status='unknown',revision=revision+1,reason='EES 요청 결과 확인 필요' WHERE run_id=? AND job_id=? AND current_attempt=?", (request["run_id"], request["job_id"], request["attempt_id"]))
            self._event(db, request_id, "EES", "request_observed", {"state": state, "revision": request["revision"], "observation": clean(details), "correlation_id": request["correlation_id"]})

    def _record_external(self, request_id, result):
        # The connector may report completion; effect verification is a second
        # server observation and never inferred from a transport 200/success.
        if not isinstance(result, dict) or result.get("state") not in {"accepted", "running", "reported_complete", "failed", "rejected", "unknown"}:
            self._observe(request_id, "unknown", {"reason": "ees_response_invalid"})
            return
        details = {key: clean(result[key]) for key in ("job_number", "external_reference", "reason") if key in result}
        if result["state"] == "reported_complete":
            details["reported_complete"] = True
        self._observe(request_id, result["state"], details)

    async def _reconcile(self, actor, groups, body):
        # Reconciliation never calls connector.request and never claims rollback.
        with self.service._db() as db:
            request = self._request(db, actor, groups, body.get("external_request_id"))
            tool = self._tool(db, request["tool_contract_id"])
            run = self.service._work_run(db, actor, groups, request["run_id"])
            self._scope(db, actor, groups, run["system_id"], run["factory_id"], "requester")
        await self._inspect_reference(actor, request["reference"], "request")
        with self.service._db(write=True) as db:
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            current = self._request(db, actor, groups, request["id"])
            self._revision(body, current["revision"])
            if current != request:
                fail("request_stale")
            self._remember(db, actor, body, {"ok": True, "request": self._public_request(request)})
        if tool["state"] != "approved" or tool["revision"] != request["tool_revision"]:
            fail("tool_review_required")
        if self.connector is None:
            fail("ees_connector_unconfigured")
        try:
            actor, groups = await self._reconcile_access(actor, request, tool)
            result = await self.connector.status(actor, deepcopy(tool), request["correlation_id"], request.get("job_number"))
            self._record_external(request["id"], result)
            if isinstance(result, dict) and result.get("state") == "reported_complete":
                if not request.get("effect_criterion"):
                    self._observe(request["id"], "reported_complete", {"reason": "effect_criterion_required"})
                else:
                    actor, groups = await self._reconcile_access(actor, request, tool)
                    observed = await self.connector.effect(actor, deepcopy(tool), deepcopy(request["effect_criterion"]), request["correlation_id"])
                    if isinstance(observed, dict) and observed.get("satisfied") is True and observed.get("evidence"):
                        self._observe(request["id"], "effect_verified", {"reported_complete": True, "effect_verified": True, "effect_evidence": clean(observed["evidence"])})
        except asyncio.CancelledError:
            raise
        except WorkflowError:
            raise
        except Exception:
            self._observe(request["id"], "unknown", {"reason": "ees_status_unavailable"})
        with self.service._db() as db:
            return {"ok": True, "request": self._public_request(self._request(db, actor, groups, request["id"]))}

    async def _schedule_command(self, actor, groups, body):
        action = body["action"]
        if action == "schedule_save":
            supplied = clean(body.get("schedule", {}))
            key = identifier(supplied.get("id", str(uuid4())))
            workflow_id = identifier(supplied.get("workflow_id"))
            factory_id = str(supplied.get("factory_id", ""))
            rule = supplied.get("rule", {})
            first = next_slot(rule, self.clock() - 1)
            grace = supplied.get("grace_seconds", 300)
            if type(grace) is not int or not 0 <= grace <= 86400 or supplied.get("catch_up", "miss") != "miss":
                fail("schedule_rule_invalid")
            # A creator can authorize their own current Native identity only.
            # There is no administrator/shared credential fallback.
            if supplied.get("identity_user_id", value(actor, "id")) != value(actor, "id"):
                fail("schedule_identity_invalid")
            if type(supplied.get("delegated", False)) is not bool:
                fail("schedule_delegation_invalid")
            with self.service._db() as db:
                definition = db.execute("SELECT * FROM work_definitions WHERE id=?", (workflow_id,)).fetchone()
                if definition is None:
                    fail("workflow_not_found")
                system = definition["system_id"]
                self._scope(db, actor, groups, system, factory_id, "owner")
                version = supplied.get("version", definition["published_version"])
                version_row = db.execute("SELECT definition FROM work_versions WHERE workflow_id=? AND version=?", (workflow_id, version)).fetchone()
                if not version_row:
                    fail("published_version_required")
                definition_data = json.loads(version_row[0])
                if definition_data.get("mode") != "periodic":
                    fail("periodic_workflow_required")
            jobs = supplied.get("job_ids", [])
            if not isinstance(jobs, list) or len(jobs) > 100 or any(not isinstance(key, str) or key not in definition_data.get("nodes", {}) or definition_data["nodes"][key].get("type") != "j" for key in jobs) or len(set(jobs)) != len(jobs):
                fail("schedule_jobs_invalid")
            model_identity, model_reason = None, ""
            if any(self._job_kind(definition_data["nodes"][key]) == "ai" for key in jobs):
                self.configure()
                try:
                    if self.model is None or not hasattr(self.model, "resolve"):
                        fail("model_required")
                    model_identity = await self.model.resolve(actor, str(supplied.get("model_id", "")))
                except WorkflowError as error:
                    model_reason = error.code
            # Requests always need a fresh human intent. A schedule can create
            # the cycle and notify the person; it cannot confirm an EES change.
            data = {"id": key, "workflow_id": workflow_id, "version": version, "system_id": system, "factory_id": factory_id, "scope": digest({"system_id": system, "factory_id": factory_id}), "identity_user_id": value(actor, "id"), "delegated": supplied.get("delegated", False), "authorized_by": value(actor, "id"), "authorized_at": self.clock(), "rule": deepcopy(rule), "catch_up": "miss", "grace_seconds": grace, "inputs": clean(supplied.get("inputs", {})), "sharing": clean(supplied.get("sharing", {"group_ids": []})), "job_ids": jobs, "model_id": model_identity["id"] if model_identity else str(supplied.get("model_id", "")), "model_identity": model_identity, "model_reason": model_reason, "next_at": first, "enabled": True}
        else:
            key = identifier(body.get("schedule_id"))
            with self.service._db() as db:
                row = db.execute("SELECT data FROM work_schedules WHERE id=?", (key,)).fetchone()
                if not row:
                    fail("schedule_not_found")
                data = json.loads(row[0])
                self._scope(db, actor, groups, data["system_id"], data["factory_id"], "participant" if action == "schedule_check" else "owner")
        actor, _, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            self._scope(db, actor, groups, data["system_id"], data["factory_id"], "participant" if action == "schedule_check" else "owner")
            if action == "schedule_check" and data["identity_user_id"] != value(actor, "id") and not set(groups).intersection(data.get("sharing", {}).get("group_ids", [])):
                fail("schedule_not_found")
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            row = db.execute("SELECT data FROM work_schedules WHERE id=?", (key,)).fetchone()
            previous = json.loads(row[0]) if row else None
            self._revision(body, previous["revision"] if previous else 0)
            if action == "schedule_save":
                if previous and (previous["workflow_id"] != data["workflow_id"] or previous["scope"] != data["scope"]):
                    fail("schedule_scope_immutable")
                # Editing a rule cannot alter already materialized slots.
                data["revision"] = (previous["revision"] if previous else 0) + 1
            else:
                data = previous
                data["revision"] += 1
                if action == "schedule_disable":
                    data["enabled"] = False
                else:
                    slot_id = identifier(body.get("slot_id"))
                    slot = db.execute("SELECT data,status FROM work_schedule_slots WHERE id=? AND schedule_id=?", (slot_id, key)).fetchone()
                    if not slot or slot["status"] not in {"missed", "blocked", "failed", "unknown"}:
                        fail("schedule_check_unavailable")
                    if json.loads(slot["data"]).get("acknowledged_by"):
                        fail("task_claimed")
                    db.execute("UPDATE work_schedule_slots SET data=json_set(data,'$.acknowledged_by',?,'$.acknowledged_at',?) WHERE id=?", (value(actor, "id"), self.clock(), slot_id))
                    self._event(db, slot_id, actor, "schedule_checked", {"schedule_id": key})
            db.execute("INSERT INTO work_schedules VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,enabled=excluded.enabled,next_at=excluded.next_at,data=excluded.data", (key, data["workflow_id"], data["scope"], data["identity_user_id"], data["revision"], int(data["enabled"]), data["next_at"], dump(data)))
            self._event(db, key, actor, action, {"revision": data["revision"]})
            return self._remember(db, actor, body, {"ok": True, "schedule": data})

    def _materialize(self):
        now = self.clock()
        count = 0
        with self.service._db(write=True) as db:
            rows = db.execute("SELECT * FROM work_schedules WHERE enabled=1 AND next_at<=? ORDER BY next_at,id LIMIT 100", (now,)).fetchall()
            for row in rows:
                schedule = json.loads(row["data"])
                stamp = row["next_at"]
                # Bound one worker tick. A long outage is recorded in batches,
                # never silently collapsed into a new normal/success marker.
                for _ in range(100):
                    if stamp > now:
                        break
                    key = digest({"workflow": row["workflow_id"], "scope": row["scope"], "at": stamp})
                    status = "missed" if now - stamp > schedule["grace_seconds"] else "queued"
                    data = {"id": key, "schedule": deepcopy(schedule), "scheduled_at": stamp, "state": status, "run_id": None, "created_at": now, "workflow_id": row["workflow_id"], "schedule_id": row["id"], "reason": "scheduled_slot_missed" if status == "missed" else ""}
                    inserted = db.execute("INSERT OR IGNORE INTO work_schedule_slots VALUES(?,?,?,?,?,?,NULL,NULL,?)", (key, row["id"], row["workflow_id"], row["scope"], stamp, status, dump(data))).rowcount
                    count += inserted
                    if inserted:
                        self._event(db, key, "EES Work", "schedule_materialized", {"state": status, "scheduled_at": stamp, "schedule_id": row["id"]})
                    stamp = next_slot(schedule["rule"], stamp)
                schedule["next_at"] = stamp
                db.execute("UPDATE work_schedules SET next_at=?,data=? WHERE id=?", (stamp, dump(schedule), row["id"]))
        return count

    def _claim_slot(self):
        now = self.clock()
        with self.service._db(write=True) as db:
            # An interrupted running read may have reached the external system.
            # Keep the attempt unknown; never convert lease expiry into success
            # or automatic duplicate dispatch.
            for row in db.execute("SELECT * FROM work_schedule_slots WHERE status='running' AND lease<?", (now,)).fetchall():
                data = json.loads(row["data"])
                data.update(state="unknown", reason="worker_lease_expired")
                db.execute("UPDATE work_schedule_slots SET status='unknown',worker=NULL,lease=NULL,data=? WHERE id=?", (dump(data), row["id"]))
                self._event(db, row["id"], "EES Work", "schedule_recovery", {"state": "unknown", "reason": "worker_lease_expired"})
            for row in db.execute("SELECT * FROM work_job_claims WHERE state='running' AND lease<?", (now,)).fetchall():
                self.service._work_finish_attempt(db, row["attempt_id"], "unknown", {"error": {"code": "worker_lease_expired"}})
                db.execute("UPDATE work_job_claims SET state='unknown',worker=NULL,lease=NULL WHERE attempt_id=?", (row["attempt_id"],))
            row = db.execute("SELECT * FROM work_schedule_slots WHERE status='queued' OR (status='waiting' AND json_extract(data,'$.next_due')<=?) ORDER BY scheduled_at,id LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            data = json.loads(row["data"])
            data["state"] = "running"
            db.execute("UPDATE work_schedule_slots SET status='running',worker=?,lease=?,data=? WHERE id=?", (self.worker, now + self.lease_seconds, dump(data), row["id"]))
            self._event(db, row["id"], "EES Work", "schedule_claimed", {"state": "running"})
            return data

    def _finish_slot(self, key, status, **detail):
        with self.service._db(write=True) as db:
            row = db.execute("SELECT * FROM work_schedule_slots WHERE id=?", (key,)).fetchone()
            if not row or row["worker"] != self.worker or row["status"] != "running":
                return
            data = json.loads(row["data"])
            data.update(clean(detail))
            data.update(state=status, finished_at=self.clock())
            db.execute("UPDATE work_schedule_slots SET status=?,worker=NULL,lease=NULL,data=? WHERE id=?", (status, dump(data), key))
            self._event(db, key, "EES Work", "schedule_observed", {"state": status, "run_id": data.get("run_id"), "reason": data.get("reason", "")})

    async def _heartbeat(self, table, key_name, key):
        while True:
            await asyncio.sleep(max(.02, self.lease_seconds / 3))
            with self.service._db(write=True) as db:
                db.execute(f"UPDATE {table} SET lease=? WHERE {key_name}=? AND worker=?", (self.clock() + self.lease_seconds, key, self.worker))

    def enqueue_scope(self, db, actor, groups, run_id, node_id=None, expected_revision=None, request_id=None, model_identity=None, emergency=False):
        """Persist coordination only. All external calls reuse the J executor."""
        run = self.service._work_run(db, actor, groups, run_id, write=True)
        if expected_revision is not None and run["revision"] != expected_revision:
            fail("revision_conflict")
        definition = json.loads(run["snapshot"])["definition"]
        nodes = definition["nodes"]
        if node_id is None:
            roots = [key for key, node in nodes.items() if node.get("type") == "p" and not node.get("parent")]
            if len(roots) != 1:
                fail("scope_invalid")
            node_id = roots[0]
        if node_id not in nodes or nodes[node_id].get("type") not in {"p", "t"}:
            fail("scope_invalid")
        jobs, pending = [], [node_id]
        while pending:
            key = pending.pop(0)
            if nodes[key].get("type") == "j":
                jobs.append(key)
            else:
                pending[0:0] = nodes[key].get("children", [])
        if not jobs or len(jobs) > 200:
            fail("scope_invalid")
        for row in db.execute("SELECT data FROM work_scope_runs WHERE run_id=? AND status IN ('queued','running','waiting')", (run_id,)):
            existing = json.loads(row[0])
            if set(jobs).intersection(existing["job_ids"]):
                fail("scope_already_active", "같은 작업의 실행 조정이 이미 진행 중입니다.")
        key = "scope-" + str(uuid4())
        data = {"id": key, "run_id": run_id, "node_id": node_id, "actor_id": value(actor, "id"), "status": "queued", "job_ids": jobs, "emergency": bool(emergency), "model_identity": deepcopy(model_identity), "created_at": self.clock(), "observed_revision": run["revision"], "job_states": {}, "reason": ""}
        db.execute("INSERT INTO work_scope_runs VALUES(?,?,?,'queued',NULL,NULL,?)", (key, run_id, value(actor, "id"), dump(data)))
        self._event(db, key, actor, "scope_queued", {"run_id": run_id, "node_id": node_id, "emergency": bool(emergency)})
        return data

    async def _scope_command(self, actor, groups, body):
        self.configure()
        with self.service._db() as db:
            run = self.service._work_run(db, actor, groups, identifier(body.get("run_id")), write=True)
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
        model_identity = None
        # Explicit model choice/default is resolved now, never selected silently
        # by a later worker. No model does not block independent read jobs.
        if self.model is not None and hasattr(self.model, "resolve"):
            try:
                model_identity = await self.model.resolve(actor, str(body.get("model_id") or ""))
            except WorkflowError:
                if body.get("model_id"):
                    raise
        actor, _, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            self.service._work_run(db, actor, groups, run["id"], write=True)
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            self._revision(body, run["revision"])
            scope = self.enqueue_scope(db, actor, groups, run["id"], body.get("node_id"), body.get("expected_revision"), body["request_id"], model_identity)
            return self._remember(db, actor, body, {"ok": True, "scope": scope})

    def _claim_scope(self):
        now = self.clock()
        with self.service._db(write=True) as db:
            for row in db.execute("SELECT * FROM work_scope_runs WHERE status='running' AND lease<?", (now,)).fetchall():
                data = json.loads(row["data"])
                data.update(status="unknown", reason="worker_lease_expired")
                db.execute("UPDATE work_scope_runs SET status='unknown',worker=NULL,lease=NULL,data=? WHERE id=?", (dump(data), row["id"]))
                self._event(db, row["id"], "EES Work", "scope_recovery", {"state": "unknown", "reason": "worker_lease_expired"})
            row = db.execute("SELECT s.* FROM work_scope_runs s JOIN work_runs r ON r.id=s.run_id WHERE s.status='queued' OR (s.status='waiting' AND (r.revision!=json_extract(s.data,'$.observed_revision') OR json_extract(s.data,'$.next_due')<=?)) ORDER BY json_extract(s.data,'$.created_at'),s.id LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            data = json.loads(row["data"])
            data["status"] = "running"
            db.execute("UPDATE work_scope_runs SET status='running',worker=?,lease=?,data=? WHERE id=?", (self.worker, now+self.lease_seconds, dump(data), row["id"]))
            return data

    def _finish_scope(self, key, status, **detail):
        with self.service._db(write=True) as db:
            row = db.execute("SELECT * FROM work_scope_runs WHERE id=?", (key,)).fetchone()
            if not row or row["worker"] != self.worker or row["status"] != "running":
                return
            data = json.loads(row["data"])
            data.update(clean(detail))
            data.update(status=status, updated_at=self.clock())
            run = db.execute("SELECT revision FROM work_runs WHERE id=?", (row["run_id"],)).fetchone()
            data["observed_revision"] = run[0] if run else -1
            db.execute("UPDATE work_scope_runs SET status=?,worker=NULL,lease=NULL,data=? WHERE id=?", (status, dump(data), key))
            self._event(db, key, "EES Work", "scope_observed", {"state": status, "reason": data.get("reason", ""), "job_id": data.get("current_job_id")})

    async def _process_scope(self):
        scope = self._claim_scope()
        if scope is None:
            return False
        heartbeat = asyncio.create_task(self._heartbeat("work_scope_runs", "id", scope["id"]))
        try:
            actor, _, groups = await self._actor({"id": scope["actor_id"]})
            selected = None
            waiting, due_times, all_done = [], [], True
            with self.service._db() as db:
                run = self.service._work_run(db, actor, groups, scope["run_id"], write=True)
                for job_id in scope["job_ids"]:
                    row = db.execute("SELECT * FROM work_jobs WHERE run_id=? AND job_id=?", (run["id"], job_id)).fetchone()
                    if row["status"] in {"completed", "excluded"}:
                        continue
                    all_done = False
                    snapshot = self.service._work_snapshot(db, run, job_id)
                    job = snapshot["job"]
                    if row["status"] in {"failed", "partial", "unknown", "blocked"} or row["current_attempt"]:
                        waiting.append("human_result_required")
                        continue
                    kind = self._job_kind(job)
                    if kind in {"human", "request"} or (scope["emergency"] and kind == "ai"):
                        waiting.append("human_command_required")
                        continue
                    if not self.service._work_dependencies_ready(db, run["id"], snapshot["definition"], job_id):
                        waiting.append("prerequisite_required")
                        continue
                    due = self.service._work_job_due(db, run, job) or self.clock()
                    if due > self.clock():
                        due_times.append(due)
                        continue
                    if kind == "ai" and not scope.get("model_identity"):
                        waiting.append("model_required")
                        continue
                    selected = job_id
                    break
            if all_done:
                self._finish_scope(scope["id"], "completed", reason="", next_due=None)
            elif selected is None:
                self._finish_scope(scope["id"], "waiting", reason=waiting[0] if waiting else "scheduled_time_required", next_due=min(due_times) if due_times else None)
            else:
                model_id = (scope.get("model_identity") or {}).get("id", "")
                outcome = await self.execute(actor, {"action": "execute_job", "run_id": run["id"], "job_id": selected, "expected_revision": run["revision"], "request_id": "scope-job-" + digest([scope["id"], selected]), "model_id": model_id}, scope_guard=scope)
                states = {**scope.get("job_states", {}), selected: outcome["attempt"]["status"]}
                self._finish_scope(scope["id"], "queued", job_states=states, current_job_id=selected, reason="", next_due=None)
        except asyncio.CancelledError:
            self._finish_scope(scope["id"], "unknown", reason="worker_stopped")
            raise
        except WorkflowError as error:
            self._finish_scope(scope["id"], "blocked", reason=error.code)
        except Exception:
            self._finish_scope(scope["id"], "unknown", reason="scope_execution_unknown")
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        return True

    async def process_once(self):
        scope_worked = await self._process_scope()
        materialized = self._materialize()
        slot = self._claim_slot()
        if not slot:
            return bool(materialized) or scope_worked
        heartbeat = asyncio.create_task(self._heartbeat("work_schedule_slots", "id", slot["id"]))
        try:
            schedule = slot["schedule"]
            if not schedule["delegated"]:
                self._finish_slot(slot["id"], "blocked", reason="schedule_delegation_required")
                return True
            actor, _, groups = await self._actor({"id": schedule["identity_user_id"]})
            with self.service._db() as db:
                self._scope(db, actor, groups, schedule["system_id"], schedule["factory_id"], "participant")
                self._current_schedule(db, schedule)
                definition = db.execute("SELECT revision FROM work_definitions WHERE id=?", (schedule["workflow_id"],)).fetchone()
            run_id = slot.get("run_id")
            if not run_id:
                result = await self.service.workspace_command(actor, {"action": "start_run", "workflow_id": schedule["workflow_id"], "version": schedule["version"], "factory_id": schedule["factory_id"], "inputs": schedule["inputs"], "sharing": schedule["sharing"], "mode": "periodic", "expected_revision": definition[0], "request_id": "slot-" + slot["id"]})
                if not result.get("ok"):
                    fail(result.get("error", {}).get("code", "schedule_start_failed"))
                run_id = result.get("run_id") or result["run"]["id"]
                # Persist the association before the first job. Existing slots
                # always keep this cycle and its immutable published version.
                with self.service._db(write=True) as db:
                    db.execute("UPDATE work_schedule_slots SET data=json_set(data,'$.run_id',?) WHERE id=? AND worker=?", (run_id, slot["id"], self.worker))
            states = deepcopy(slot.get("job_states", {}))
            pending_times = []
            for job_id in schedule["job_ids"]:
                if job_id in states:
                    continue
                actor, _, groups = await self._actor(actor)
                with self.service._db() as db:
                    self._current_schedule(db, schedule)
                    run = self.service._work_run(db, actor, groups, run_id, write=True)
                    snap = self.service._work_snapshot(db, run, job_id)
                    job = snap["job"]
                    due = self._job_due(slot["scheduled_at"], job.get("trigger", {}))
                    if due > self.clock():
                        pending_times.append(due)
                        continue
                    if self.clock() - due > schedule["grace_seconds"]:
                        states[job_id] = "missed"
                        continue
                    if self._job_kind(job) in {"human", "request"}:
                        states[job_id] = "blocked"
                        continue
                    ready = self.service._work_dependencies_ready(db, run_id, snap["definition"], job_id)
                    if not ready:
                        pending_times.append(min(due + schedule["grace_seconds"] + .001, self.clock() + 5))
                        continue
                outcome = await self.execute(actor, {"action": "execute_job", "run_id": run_id, "job_id": job_id, "expected_revision": run["revision"], "model_id": schedule["model_id"], "request_id": "slot-job-" + digest([slot["id"], job_id])}, schedule_guard=schedule)
                states[job_id] = outcome["attempt"]["status"]
            if pending_times:
                self._finish_slot(slot["id"], "waiting", run_id=run_id, job_states=states, next_due=min(pending_times))
            else:
                statuses = list(states.values())
                status = "failed" if any(item in {"failed", "partial", "unknown"} for item in statuses) else "missed" if "missed" in statuses else "blocked" if "blocked" in statuses else "succeeded"
                if not statuses:
                    status = "cycle_started"
                self._finish_slot(slot["id"], status, run_id=run_id, job_states=states)
        except asyncio.CancelledError:
            self._finish_slot(slot["id"], "unknown", reason="worker_stopped")
            raise
        except WorkflowError as error:
            self._finish_slot(slot["id"], "blocked", reason=error.code)
        except Exception:
            self._finish_slot(slot["id"], "unknown", reason="schedule_execution_unknown")
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        return True

    async def execute(self, user, body, *, schedule_guard=None, scope_guard=None):
        actor, caps, groups = await self._actor(user)
        self.configure()
        with self.service._db() as db:
            run = self.service._work_run(db, actor, groups, identifier(body.get("run_id")), write=True)
            snapshot = self.service._work_snapshot(db, run, identifier(body.get("job_id")))
            job = snapshot["job"]
        options_snapshot = await self.service._work_resolve_job_options(actor, run["id"], job["id"])
        kind = self._job_kind(job)
        skill_snapshots = await self._skills(actor, job, snapshot["definition"])
        if kind in {"human", "request"}:
            fail("human_command_required", "사람 작업은 직접 확인하고, EES 요청은 요청 확인 창에서 진행해 주세요.")
        reference = deepcopy(job.get("tool_reference", job.get("execution", {}).get("reference", snapshot.get("tool_reference"))))
        if reference:
            reference.pop("contract_id", None)
        if kind == "tool":
            if not reference:
                fail("native_tool_required")
            await self.bridge.check(actor, reference)
            with self.service._db() as db:
                arguments, argument_sources, argument_records = self._resolve_arguments(db, run, job, snapshot["inputs"])
            for record in argument_records:
                await self.service._work_check_evidence(actor, record)
        elif kind == "ai":
            stored_results, evidence, records = {}, [], []
            source_references, source_decisions = [], {}
            with self.service._db() as db:
                # Include transitive declared prerequisites, never arbitrary
                # private jobs or another run's evidence.
                dependency_ids, todo = set(), list(self.service._work_prerequisite_jobs(snapshot["definition"], job["id"]))
                while todo:
                    dependency = todo.pop()
                    if dependency in dependency_ids:
                        continue
                    dependency_ids.add(dependency)
                    todo.extend(self.service._work_prerequisite_jobs(snapshot["definition"], dependency))
                for dependency in sorted(dependency_ids):
                    row = db.execute("SELECT a.* FROM work_jobs j JOIN work_attempts a ON a.id=j.current_attempt WHERE j.run_id=? AND j.job_id=?", (run["id"], dependency)).fetchone()
                    if row:
                        records.append(dict(row))
                        source_decisions[dependency] = [dict(item) for item in db.execute("SELECT item_id,verdict,note,actor_id,result_revision FROM work_decisions WHERE run_id=? AND job_id=? AND attempt_id=?", (run["id"], dependency, row["id"]))]
            for record in records:
                await self.service._work_check_evidence(actor, record)
                source_snapshot = json.loads(record["snapshot"])
                source_references.extend(self.service._work_evidence_references(source_snapshot))
                saved_result = json.loads(record["result"])
                if record["status"] != "succeeded" and not (record["status"] == "waiting_confirmation" and saved_result.get("amendment")) and not (record["status"] == "partial" and job.get("result_block") == "ai_review" and job.get("dependency_policy") == "all_resolved"):
                    fail("evidence_required")
                stored_results.setdefault(record["job_id"], {})[record["id"]] = saved_result
                evidence.append({"job_id": record["job_id"], "call_id": record["id"]})
            if self.model is None:
                fail("model_unavailable")
            if schedule_guard is not None and not schedule_guard.get("model_identity"):
                fail("schedule_model_required", "예약 당시 선택한 실행 모델을 확인해 주세요.")
            model_id = str(body.get("model_id") or snapshot.get("model_id") or "")
            if hasattr(self.model, "resolve"):
                model_identity = await self.model.resolve(actor, model_id)
            else:
                model_identity = {"id": model_id}
            if not model_identity["id"]:
                fail("model_required")
            if schedule_guard is not None and model_identity != schedule_guard["model_identity"]:
                fail("model_configuration_changed")
            if scope_guard is not None and model_identity != scope_guard.get("model_identity"):
                fail("model_configuration_changed")
        else:
            fail("execution_kind_invalid")
        actor, _, groups = await self._actor(actor)
        with self.service._db(write=True) as db:
            self.service._work_run(db, actor, groups, run["id"], write=True)
            if schedule_guard is not None:
                self._current_schedule(db, schedule_guard)
            if scope_guard is not None:
                guard = db.execute("SELECT * FROM work_scope_runs WHERE id=?", (scope_guard["id"],)).fetchone()
                if not guard or guard["status"] != "running" or guard["worker"] != self.worker or guard["lease"] < self.clock() or guard["actor"] != value(actor, "id"):
                    fail("scope_claim_lost")
            receipt = self._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            if kind == "tool":
                current_arguments, current_sources, _ = self._resolve_arguments(db, run, job, snapshot["inputs"])
                if current_arguments != arguments or current_sources != argument_sources:
                    fail("result_source_changed")
            attempt = self.service._work_begin_attempt(db, actor, groups, run["id"], job["id"], body.get("expected_revision"), inputs=body.get("inputs"), options_snapshot=options_snapshot)
            attempt["snapshot"]["skills"] = skill_snapshots
            if kind == "tool":
                attempt["snapshot"]["arguments"] = arguments
                attempt["snapshot"]["argument_sources"] = argument_sources
                attempt["snapshot"]["source_references"] = [ref for record in argument_records for ref in self.service._work_evidence_references(json.loads(record["snapshot"]))]
                attempt["snapshot"]["evidence_attempt_ids"] = [record["id"] for record in argument_records]
            db.execute("UPDATE work_attempts SET snapshot=? WHERE id=? AND status='running'", (dump(attempt["snapshot"]), attempt["id"]))
            if kind == "ai":
                # Model identity is immutable per attempt. A restarted worker
                # cannot choose a newly available model in place of this one.
                attempt["snapshot"]["model"] = model_identity
                attempt["snapshot"]["source_references"] = source_references
                attempt["snapshot"]["evidence_attempt_ids"] = [record["id"] for record in records]
                db.execute("UPDATE work_attempts SET snapshot=? WHERE id=? AND status='running'", (dump(attempt["snapshot"]), attempt["id"]))
            db.execute("INSERT INTO work_job_claims VALUES(?,?,?,?,?)", (attempt["id"], value(actor, "id"), self.worker, self.clock() + self.lease_seconds, "running"))
            outcome = {"ok": True, "attempt": deepcopy(attempt)}
            self._remember(db, actor, body, outcome)
        heartbeat = asyncio.create_task(self._heartbeat("work_job_claims", "attempt_id", attempt["id"]))
        status, result = "unknown", {"error": {"code": "execution_result_unknown"}}
        try:
            if await self._skills(actor, job, snapshot["definition"]) != skill_snapshots:
                fail("skill_changed", "연결된 Native 지침의 권한·내용이 바뀌었습니다.")
            for record in (argument_records if kind == "tool" else records):
                await self.service._work_check_evidence(actor, record)
            if kind == "tool":
                result = await self.bridge.invoke(actor, reference, arguments, {"run_id": run["id"], "job_id": job["id"], "call_id": attempt["id"]})
            elif job.get("result_block") in {"item_verdict", "ai_review"}:
                proposal_kind = "verdicts" if job["result_block"] == "item_verdict" else "report"
                principal = job.get("result_source_job_id")
                if proposal_kind == "verdicts" and principal not in stored_results:
                    fail("result_source_required")
                source_items = []
                if principal in stored_results:
                    source_items = next(iter(stored_results[principal].values())).get("items", [])
                if not isinstance(source_items, list) or any(not isinstance(item, dict) or "id" not in item for item in source_items):
                    fail("result_source_invalid")
                context = {"context_id": attempt["id"], "target_id": job["id"], "revision": attempt["number"], "kind": proposal_kind,
                           "model_identity": model_identity, "item_ids": [str(item["id"]) for item in source_items],
                           "source": {"results": stored_results, "human_decisions": source_decisions, "inputs": attempt["inputs"], "skills": skill_snapshots,
                                      "limitations": ["Attachment presence and access metadata do not prove document content or adequacy.", "This is an AI suggestion, not a human decision or a sent report."]}}
                proposed = await self.model.propose(actor, model_identity["id"], context, job.get("instructions") or "Review only the supplied current evidence; preserve unknowns and human decisions. Do not infer document adequacy from metadata.")
                expected_context = {key: context[key] for key in ("context_id", "target_id", "revision", "kind")}
                if not isinstance(proposed, dict) or proposed.get("ok") is not True or proposed.get("context") != expected_context:
                    fail("model_result_invalid")
                proposal = proposed.get("proposal")
                result = {"status": "succeeded", "completeness": "complete", "actor": "AI", "model": deepcopy(model_identity), "context": expected_context, "proposal": clean(proposal), "is_proposal": True, "saved_decision": False, "sent": False, "evidence": evidence}
                if proposal_kind == "verdicts":
                    if not isinstance(proposal, list) or len(proposal) != len(source_items):
                        fail("model_result_invalid")
                    suggestions = {}
                    for item in proposal:
                        if (not isinstance(item, dict) or set(item) != {"item_id", "verdict", "reason"} or item["item_id"] not in context["item_ids"] or item["item_id"] in suggestions or item["verdict"] not in {"approved", "failed", "unknown", "action_required"} or not isinstance(item["reason"], str)):
                            fail("model_result_invalid")
                        suggestions[item["item_id"]] = item
                    result["items"] = [{**deepcopy(item), "ai_suggestion": suggestions[str(item["id"])]["reason"], "ai_proposal": deepcopy(suggestions[str(item["id"])])} for item in source_items]
                elif not isinstance(proposal, str) or len(proposal) > 100_000:
                    fail("model_result_invalid")
                else:
                    result["summary"] = proposal
            else:
                node = {"id": job["id"], "execution": {**job.get("execution", {}), "kind": "ai", "model_id": model_identity["id"], "evidence": evidence}}
                results = stored_results
                result = await self.model.invoke(actor, node, {"run_id": run["id"], "model_identity": model_identity, "instructions": [job.get("instructions", "")], "skills": skill_snapshots}, results, attempt["inputs"])
                from .ees_workflow_contract import _evaluate_summary
                validation = _evaluate_summary(node["execution"], result, results)
                if validation["status"] != "succeeded":
                    result = {"status": "unknown", "completeness": "unknown", "error": {"code": "model_result_ungrounded"}}
            if not isinstance(result, dict):
                result = {"status": "unknown", "error": {"code": "result_invalid"}}
            status = result.get("status", "unknown")
            if status == "succeeded" and result.get("completeness") not in {"complete", "empty"}:
                status = "partial"
            if status not in {"succeeded", "failed", "partial", "unknown"}:
                status = "unknown"
        except asyncio.CancelledError:
            raise
        except WorkflowError as error:
            status, result = "blocked", {"error": {"code": error.code}}
        except Exception:
            status, result = "unknown", {"error": {"code": "execution_result_unknown"}}
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            with self.service._db(write=True) as db:
                claim = db.execute("SELECT * FROM work_job_claims WHERE attempt_id=?", (attempt["id"],)).fetchone()
                if claim["state"] == "running" and claim["worker"] == self.worker and claim["lease"] >= self.clock():
                    self.service._work_finish_attempt(db, attempt["id"], status, clean(result))
                    db.execute("UPDATE work_job_claims SET state=?,worker=NULL,lease=NULL WHERE attempt_id=?", (status, attempt["id"]))
                else:
                    status = "unknown"
        actor, _, groups = await self._actor(actor)
        await self.service._work_check_evidence(actor, {**attempt, "actor_id": value(actor, "id")})
        with self.service._db() as db:
            self.service._work_run(db, actor, groups, run["id"])
        outcome = {"ok": status == "succeeded", "attempt": {**attempt, "status": status, "result": result}}
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_operation_receipts SET outcome=? WHERE actor=? AND request_id=? AND payload_hash=?", (dump(outcome), value(actor, "id"), body["request_id"], digest(body)))
        return outcome

    def _resolve_arguments(self, db, run, job, inputs):
        bindings = job.get("argument_bindings", job.get("execution", {}).get("argument_bindings", {}))
        normal, sources, records = {}, {}, []
        definition = json.loads(run["snapshot"])["definition"]
        prerequisites = set(self.service._work_prerequisite_jobs(definition, job["id"]))
        for name, binding in bindings.items():
            if not isinstance(binding, dict) or set(binding) != {"result"}:
                normal[name] = binding
                continue
            spec = binding["result"]
            if (not isinstance(spec, dict) or set(spec) != {"job_id", "path", "value_field", "confirmed"} or spec["confirmed"] is not True or spec["job_id"] not in prerequisites or spec["path"] != ["items"] or spec["value_field"] != "id"):
                fail("result_binding_invalid")
            row = db.execute("SELECT a.*,j.status AS business_status FROM work_jobs j JOIN work_attempts a ON a.id=j.current_attempt WHERE j.run_id=? AND j.job_id=?", (run["id"], spec["job_id"])).fetchone()
            if not row or row["business_status"] != "completed":
                fail("confirmed_result_required")
            result = json.loads(row["result"])
            if row["status"] != "succeeded" and not (row["status"] == "waiting_confirmation" and result.get("amendment")):
                fail("confirmed_result_required")
            items = result.get("items")
            if result.get("completeness") not in {"complete", "empty"} or not isinstance(items, list):
                fail("complete_result_required")
            if json.loads(row["inputs"]) != self.service._work_snapshot(db, run, spec["job_id"])["inputs"]:
                fail("result_source_changed")
            selected = [item for item in items if isinstance(item, dict) and item.get("selected", True) is not False]
            ids = [str(item["id"]) for item in selected if "id" in item]
            if len(selected) != len([item for item in items if not isinstance(item, dict) or item.get("selected", True) is not False]) or len(ids) != len(selected) or len(set(ids)) != len(ids) or len(ids) > 50:
                fail("result_binding_invalid")
            normal[name] = {"constant": ids}
            decisions = [dict(item) for item in db.execute("SELECT item_id,verdict,result_revision FROM work_decisions WHERE run_id=? AND job_id=? AND attempt_id=? ORDER BY item_id", (run["id"], spec["job_id"], row["id"]))]
            sources[name] = {"job_id": spec["job_id"], "attempt_id": row["id"], "result_revision": row["number"], "result_hash": digest(result), "ids": ids, "decisions_hash": digest(decisions)}
            records.append(dict(row))
        return self._arguments({"argument_bindings": normal}, inputs), sources, records

    @staticmethod
    def _arguments(job, inputs):
        bindings = job.get("argument_bindings", job.get("execution", {}).get("argument_bindings", {}))
        if not isinstance(bindings, dict):
            fail("argument_bindings_invalid")
        arguments = {}
        for name, field in bindings.items():
            if isinstance(field, str) and field in inputs:
                arguments[name] = deepcopy(inputs[field])
            elif isinstance(field, dict) and set(field) == {"input"} and field["input"] in inputs:
                arguments[name] = deepcopy(inputs[field["input"]])
            elif isinstance(field, dict) and set(field) == {"constant"}:
                arguments[name] = deepcopy(field["constant"])
            else:
                fail("argument_input_missing")
        return arguments

    async def state(self, user, system_id="", run_id=""):
        actor, caps, groups = await self._actor(user)
        tools, schedules, slots, requests, scopes = [], [], [], [], []
        request_records = []
        reviewer_ids = {value(actor, "id")} if value(actor, "role") == "admin" else set()
        with self.service._db() as db:
            for row in db.execute("SELECT principal_id,roles FROM work_access WHERE principal_kind='user' AND active=1 AND (?='' OR system_id=?)", (system_id, system_id)):
                if "manager" in json.loads(row["roles"]):
                    reviewer_ids.add(row["principal_id"])
            for row in db.execute("SELECT data FROM work_tool_contracts ORDER BY id"):
                item = json.loads(row[0])
                if system_id and item["system_id"] != system_id:
                    continue
                try:
                    self._scope(db, actor, groups, item["system_id"])
                except WorkflowError:
                    continue
                tools.append(item)
            for row in db.execute("SELECT data FROM work_schedules ORDER BY next_at,id"):
                item = json.loads(row[0])
                if system_id and item["system_id"] != system_id:
                    continue
                if item["identity_user_id"] != value(actor, "id") and not set(groups).intersection(item.get("sharing", {}).get("group_ids", [])):
                    continue
                try:
                    self._scope(db, actor, groups, item["system_id"], item["factory_id"])
                except WorkflowError:
                    continue
                schedules.append(item)
                for slot in db.execute("SELECT data FROM work_schedule_slots WHERE schedule_id=? ORDER BY scheduled_at DESC LIMIT 100", (item["id"],)):
                    data = json.loads(slot[0])
                    slots.append({**{key: val for key, val in data.items() if key != "schedule"}, "factory_id": item["factory_id"], "workflow_id": item["workflow_id"]})
            if run_id:
                self.service._work_run(db, actor, groups, run_id)
                scopes = [json.loads(row[0]) for row in db.execute("SELECT data FROM work_scope_runs WHERE run_id=? ORDER BY id", (run_id,))]
                for scope in scopes:
                    scope.pop("model_identity", None)
                for row in db.execute("SELECT data FROM work_external_requests WHERE run_id=? ORDER BY id", (run_id,)):
                    record = json.loads(row[0])
                    public = self._public_request(record)
                    public["events"] = [{"state": json.loads(event["data"]).get("state", event["kind"]), "kind": event["kind"], "actor": event["actor"], "created_at": event["created_at"]} for event in db.execute("SELECT * FROM work_operation_events WHERE target=? ORDER BY id", (record["id"],))]
                    request_records.append((record, public))
        self.configure()
        for record, public in request_records:
            try:
                await self._inspect_reference(actor, record["reference"], "request")
                public["inputs"] = deepcopy(record["inputs"])
            except WorkflowError:
                public.pop("effect_evidence", None)
                public["evidence_access_required"] = True
            requests.append(public)
        reviewers = []
        for reviewer_id in sorted(reviewer_ids):
            try:
                reviewer, _, reviewer_groups = await self._actor({"id": reviewer_id})
                with self.service._db() as db:
                    if system_id:
                        self._scope(db, reviewer, reviewer_groups, system_id, role="owner")
                reviewers.append({"id": reviewer_id, "name": value(reviewer, "name", reviewer_id)})
            except WorkflowError:
                continue
        native_functions = []
        self.configure()
        if hasattr(self.bridge, "registered_capabilities"):
            native_functions = await self.bridge.registered_capabilities(actor)
        models = []
        if self.model is not None and hasattr(self.model, "available"):
            models = await self.model.available(actor)
        actionable = [{"id": item["id"], "kind": "schedule_attention", "state": item["state"], "run_id": item.get("run_id"), "scheduled_at": item["scheduled_at"], "reason": item.get("reason", ""), "schedule_id": item.get("schedule_id")} for item in slots if item["state"] in {"failed", "missed", "blocked", "unknown"} and not item.get("acknowledged_by")]
        automatic = {}
        for slot in sorted(slots, key=lambda row: row["scheduled_at"]):
            state = slot["state"]
            if state in {"cycle_started", "waiting"} and not slot.get("job_states"):
                continue
            state = "failed" if state in {"failed", "blocked", "unknown"} else "missed" if state == "missed" else "running" if state in {"queued", "running"} else "succeeded" if state == "succeeded" else None
            if state is not None:
                automatic[(slot["workflow_id"], slot["factory_id"])] = {"workflow_id": slot["workflow_id"], "factory_id": slot["factory_id"], "status": state, "scheduled_at": slot["scheduled_at"]}
        return {"ok": True, "scope_runs": scopes, "tools": tools, "native_functions": native_functions, "reviewers": reviewers, "schedules": schedules, "slots": slots, "automatic_statuses": list(automatic.values()), "actionable": actionable, "requests": requests, "models": models, "show_model_selector": len(models) > 1, "model_configured": bool(models), "ees_connector_configured": self.connector is not None}

    def start(self):
        self._closing = False
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop(), name="ees-work-schedules")

    async def _loop(self):
        while not self._closing:
            try:
                worked = await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                worked = False
            if not worked:
                await asyncio.sleep(.25)

    async def stop(self):
        self._closing = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        with self.service._db(write=True) as db:
            for row in db.execute("SELECT * FROM work_schedule_slots WHERE worker=? AND status='running'", (self.worker,)).fetchall():
                data = json.loads(row["data"])
                data.update(state="unknown", reason="worker_stopped")
                db.execute("UPDATE work_schedule_slots SET status='unknown',worker=NULL,lease=NULL,data=? WHERE id=?", (dump(data), row["id"]))

    @staticmethod
    def _job_kind(job):
        return "request" if job.get("result_block") == "change_request" else job.get("mode", job.get("kind", job.get("execution", {}).get("kind", "human")))

    def validate_publication(self, db, definition, actor, groups):
        errors = []
        for job in definition.get("nodes", {}).values():
            if job.get("type") != "j":
                continue
            key = job.get("tool_contract_id") or (job.get("tool_reference") or {}).get("contract_id")
            if self._job_kind(job) != "request" and not key:
                continue
            try:
                tool = self._tool(db, key)
                self._scope(db, actor, groups, tool["system_id"], role="manager")
                if tool["system_id"] != definition["system_id"] or tool["state"] != "approved":
                    fail("tool_review_required")
                if type(job.get("tool_contract_revision")) is not int or job["tool_contract_revision"] != tool["revision"]:
                    fail("tool_contract_changed")
                if self._job_kind(job) == "request" and tool["kind"] != "request":
                    fail("request_contract_required")
                if self._job_kind(job) == "request" and not job.get("effect_criterion"):
                    fail("effect_criterion_required")
            except WorkflowError as error:
                errors.append(job.get("id", "") + ": " + error.code)
        return errors

    async def _skills(self, actor, job, definition=None):
        refs = job.get("skills", [])
        if not refs:
            return []
        if not isinstance(refs, list) or any(not isinstance(key, str) for key in refs):
            fail("skill_reference_invalid")
        assets = await self.service._assets(actor)
        if not assets.get("available", True):
            fail("skill_unavailable")
        bodies, versions = assets.get("skill_bodies", {}), assets.get("skill_versions", {})
        result = []
        for key in refs:
            if key not in bodies:
                fail("skill_unavailable", "현재 계정으로 연결된 Native 지침을 읽을 수 없습니다.")
            observed = {"revision": versions.get(key), "content_hash": hashlib.sha256(str(bodies[key]).encode()).hexdigest()}
            expected = (definition or {}).get("resource_versions", {}).get("skills", {}).get(key)
            if expected != observed:
                fail("skill_version_changed", "게시된 Native 지침 버전이 바뀌었습니다. 다시 검사·게시해 주세요.")
            result.append({"id": key, "body": bodies[key], **observed})
        return result

    @staticmethod
    def _job_due(slot_time, trigger):
        if not trigger:
            return slot_time
        if not isinstance(trigger, dict) or set(trigger) - {"offset_seconds", "at"}:
            fail("job_trigger_invalid")
        if "at" in trigger:
            try:
                parsed = datetime.fromisoformat(trigger["at"])
                if parsed.tzinfo is None:
                    fail("job_trigger_timezone_required")
                return parsed.timestamp()
            except (ValueError, TypeError):
                fail("job_trigger_invalid")
        offset = trigger.get("offset_seconds", 0)
        if type(offset) is not int or not 0 <= offset <= 366 * 86400:
            fail("job_trigger_invalid")
        return slot_time + offset

    def _current_schedule(self, db, schedule):
        row = db.execute("SELECT enabled,data FROM work_schedules WHERE id=?", (schedule["id"],)).fetchone()
        if not row or not row["enabled"]:
            fail("schedule_disabled")
        current = json.loads(row["data"])
        if not current.get("delegated") or current["identity_user_id"] != schedule["identity_user_id"]:
            fail("schedule_delegation_revoked")
        return current

    async def _reconcile_access(self, actor, request, tool):
        actor, _, groups = await self._actor(actor)
        await self._inspect_reference(actor, request["reference"], "request")
        status_contract = await self.bridge.inspect_registered(actor, tool["reference"]["tool_id"], tool["status_function"])
        if status_contract["reference"] != tool.get("status_reference"):
            fail("native_version_changed")
        actor, _, groups = await self._actor(actor)
        with self.service._db() as db:
            run = self.service._work_run(db, actor, groups, request["run_id"])
            self._scope(db, actor, groups, run["system_id"], run["factory_id"], "requester")
            current = self._tool(db, tool["id"])
            if current["state"] != "approved" or current["revision"] != request["tool_revision"]:
                fail("tool_review_required")
        return actor, groups
