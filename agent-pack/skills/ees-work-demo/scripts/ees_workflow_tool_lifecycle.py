"""Explicit authored-tool trials and immutable use versions.

Native owns personal credentials. This database contains nonsecret connection
settings and bounded, actor-private trial evidence, never credential values.
"""
import asyncio
from copy import deepcopy
import hashlib
import inspect
import json
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_native import _safe
from .ees_workflow_tool_draft_check import check_draft, _matches
from .ees_workflow_tool_native import AuthoredNative


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _fail(code, message="저장된 수정본과 연결 상태를 다시 확인해 주세요."):
    raise WorkflowError(code, message)


def _issue(code, message, field=None):
    return {"code": code, "message": message, **({"field": field} if field else {})}


def _base_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or re.search(r"[\s\\\x00-\x1f]", value):
        _fail("tool_connection_invalid", "http 또는 https 기본 주소를 입력해 주세요.")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment or "?" in value or "#" in value
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise ValueError()
    except ValueError:
        _fail("tool_connection_invalid", "인증 정보·검색 조건·조각을 제외한 기본 주소를 입력해 주세요.")
    return value.rstrip("/")


def _inputs(schema, inputs):
    try:
        if not isinstance(inputs, dict) or len(_json(inputs).encode("utf-8")) > 65536:
            raise ValueError()
        properties = schema.get("properties", {})
        if set(inputs) - set(properties) or any(key not in inputs for key in schema.get("required", [])):
            raise ValueError()
        result = deepcopy(inputs)
        for key, shape in properties.items():
            if key not in result and "default" in shape:
                result[key] = deepcopy(shape["default"])
            if key in result and not _matches(result[key], shape):
                raise ValueError()
        return result
    except (ValueError, TypeError, RecursionError, OverflowError):
        _fail("tool_trial_inputs_invalid", "필수 입력과 값의 형식을 확인해 주세요.")


def _path(value, path):
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError()
        value = value[key]
    return value


def _result(raw, output):
    """Validate real values without replacing them with preview examples."""
    empty = {"rows": [], "raw_result": None, "count": 0, "completeness": "unknown", "fields_checked": False,
             "errors": [], "warnings": []}
    try:
        if isinstance(raw, str):
            if len(raw.encode("utf-8")) > 262144:
                raise ValueError()
            raw = json.loads(raw)
        if len(_json(raw).encode("utf-8")) > 262144:
            raise ValueError()
    except (ValueError, TypeError, RecursionError, OverflowError):
        return {**empty, "status": "failed", "errors": [_issue("tool_trial_result_invalid", "결과의 형식이나 크기를 확인할 수 없습니다.")]}
    safe = _safe(raw)
    if isinstance(safe, dict) and any(key in safe and not isinstance(safe[key], str) for key in ("status", "completeness")):
        return {**empty, "status": "failed", "errors": [_issue("tool_trial_result_invalid", "결과 상태의 형식을 확인할 수 없습니다.")]}
    if isinstance(safe, dict) and (safe.get("ok") is False or safe.get("status") in {"failed", "error"}):
        return {**empty, "status": "failed", "errors": [_issue("tool_trial_call_failed", "조회가 완료되지 않았습니다. 연결과 계정 권한을 확인해 주세요.")]}
    if isinstance(safe, dict) and (safe.get("status") == "unknown" or safe.get("completeness") == "unknown"):
        return {**empty, "status": "unknown", "errors": [_issue("tool_trial_result_unknown", "도구가 결과의 완료 여부를 확인하지 못했습니다.")]}
    partial = isinstance(safe, dict) and (safe.get("status") in {"partial", "truncated", "page", "incomplete"} or safe.get("completeness") in {"partial", "truncated", "page", "incomplete"}
                or safe.get("partial") is True or safe.get("truncated") is True or safe.get("has_more") is True)
    try:
        rows = _path(safe, output["path"])
        if not isinstance(rows, list) or len(rows) > 500 or any(not isinstance(row, dict) for row in rows):
            raise ValueError()
        for row in rows:
            for field in output["fields"]:
                value = _path(row, field["path"])
                if type(value) not in (str, int, float, bool):
                    raise ValueError()
                if field["role"] == "url":
                    parsed = urlsplit(value) if isinstance(value, str) else None
                    if (not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None
                            or re.search(r"[\s\\\x00-\x1f]", value) or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
                        raise ValueError()
        return {**empty, "status": "failed" if partial else "succeeded", "rows": rows, "raw_result": safe,
                "count": len(rows), "completeness": "partial" if partial else "complete" if rows else "empty",
                "fields_checked": bool(rows),
                "errors": [_issue("tool_trial_partial", "일부 결과만 받았습니다. 전체 결과를 확인한 뒤 다시 시험해 주세요.")] if partial else [],
                "warnings": [] if rows else [_issue("tool_trial_empty", "결과가 0건입니다. 개별 항목의 표시 형식은 확인하지 못했습니다.")]}
    except (ValueError, TypeError, KeyError, RecursionError):
        return {**empty, "status": "failed", "raw_result": safe,
                "errors": [_issue("tool_trial_mapping_invalid", "목록 경로·표시 항목·문서 주소가 실제 결과와 맞는지 확인해 주세요.", "output_ui")]}


class ToolLifecycle:
    def __init__(self, drafts):
        self.drafts, self.service = drafts, drafts.service
        self.native = AuthoredNative(self.service)
        self._locks = {}
        with self.service._db(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_connections(tool_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_trials(id TEXT PRIMARY KEY,tool_id TEXT NOT NULL,actor TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,data TEXT NOT NULL,UNIQUE(actor,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_uses(tool_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_use_observations(tool_id TEXT PRIMARY KEY,environment TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_authored_versions(tool_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(tool_id,version))")
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_connection_receipts(actor TEXT NOT NULL,request_id TEXT NOT NULL,tool_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(actor,request_id))")

    @staticmethod
    def _connection(db, key):
        row = db.execute("SELECT data FROM work_tool_connections WHERE tool_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else {"revision": 0, "base_url": "", "native_id": None}

    @staticmethod
    def _use(db, key):
        row = db.execute("SELECT data FROM work_tool_uses WHERE tool_id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else {"revision": 0, "active_version": None, "state": "draft", "groups": [],
            "evidence": "", "confirmed_by": None, "confirmed_at": None, "versions": []}

    @staticmethod
    def _revision(actual, expected):
        if type(expected) is not int or actual != expected:
            _fail("tool_draft_conflict", "다른 변경이 저장되었습니다. 입력은 유지하고 최신 저장본을 확인해 주세요.")

    @staticmethod
    def _request(body):
        key = body.get("request_id")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", key):
            _fail("tool_draft_invalid")
        return key

    async def connection(self, actor, key):
        with self.service._db() as db:
            item = self._connection(db, key)
        metadata = {}
        if item["native_id"]:
            try:
                metadata = await self.native.inspect(actor, item["native_id"])
            except WorkflowError:
                pass
        return {key: item[key] for key in ("revision", "base_url", "native_id")} | {
            "configured": bool(item["base_url"] and metadata.get("token_set")), "token_set": bool(metadata.get("token_set"))}

    async def decorate(self, actor, record):
        key = record["id"]
        connection = await self.connection(actor, key)
        with self.service._db() as db:
            use = self._use(db, key)
            row = db.execute("SELECT data FROM work_tool_trials WHERE tool_id=? AND actor=? ORDER BY rowid DESC LIMIT 1", (key, _get(actor, "id"))).fetchone()
        trial = await self.public_trial(actor, json.loads(row[0])) if row else None
        await self.drafts._admin(actor)
        return {**record, "phase": 2, "connection": connection, "trial": trial, "use": use}

    def _trial(self, db, actor, key, trial_id):
        row = db.execute("SELECT data FROM work_tool_trials WHERE id=? AND tool_id=? AND actor=?", (trial_id, key, _get(actor, "id"))).fetchone()
        if not row:
            _fail("tool_trial_not_found", "현재 계정의 시험 기록을 찾을 수 없습니다.")
        return json.loads(row[0])

    async def public_trial(self, actor, trial):
        if trial["actor"] != _get(actor, "id"):
            _fail("tool_trial_not_found")
        if trial["status"] == "running" and time.time() - trial["started_at"] > 60:
            # A previous process/request may have died. Never launch it again.
            trial.update(status="unknown", finished_at=time.time(), errors=[_issue("tool_trial_interrupted", "시험 완료 여부를 확인하지 못했습니다. 자동으로 다시 실행하지 않았습니다.")])
            with self.service._db(write=True) as db:
                current = self._trial(db, actor, trial["tool_id"], trial["id"])
                if current["status"] == "running":
                    db.execute("UPDATE work_tool_trials SET data=? WHERE id=?", (_json(trial), trial["id"]))
                else:
                    trial = current
        reasons = []
        if trial["status"] != "succeeded" or trial["completeness"] not in {"complete", "empty"}:
            reasons.append(_issue("tool_trial_not_successful", "현재 수정본의 시험을 완료해 주세요."))
        with self.service._db() as db:
            current = self.drafts._get(db, trial["tool_id"])
            connection = self._connection(db, trial["tool_id"])
        if current["revision"] != trial["draft_revision"]:
            reasons.append(_issue("tool_trial_draft_changed", "수정본이 바뀌었습니다. 저장한 내용으로 다시 시험해 주세요."))
        if connection["revision"] != trial["connection_revision"]:
            reasons.append(_issue("tool_trial_connection_changed", "연결이 바뀌었습니다. 다시 시험해 주세요."))
        readable = False
        try:
            metadata = await self.native.inspect(actor, connection["native_id"])
            readable = bool(metadata.get("token_set"))
            if not metadata.get("token_set") or any(metadata.get(key) != trial["_metadata"].get(key) for key in ("native_id", "credential_stamp", "environment")):
                reasons.append(_issue("tool_trial_credentials_changed", "계정 연결이나 실행 환경이 바뀌었습니다. 다시 시험해 주세요."))
        except WorkflowError:
            reasons.append(_issue("tool_trial_connection_unavailable", "현재 연결과 계정 권한을 확인해 주세요."))
        await self.drafts._admin(actor)
        allowed = ("id", "tool_id", "draft_revision", "connection_revision", "status", "started_at", "finished_at", "duration_ms",
                   "inputs", "rows", "raw_result", "count", "completeness", "fields_checked", "errors", "warnings")
        public = {key: deepcopy(trial[key]) for key in allowed}
        if not readable:
            public.update(inputs={}, rows=[], raw_result=None, count=0, fields_checked=False)
        return public | {"eligible_for_activation": not reasons, "activation_reasons": reasons}

    async def command(self, actor, body):
        actor = await self.drafts._admin(actor)
        action, key = body.get("action"), body.get("tool_id")
        with self.service._db() as db:
            self.drafts._get(db, key)
        if action == "tool_draft_connection_get":
            connection = await self.connection(actor, key)
            await self.drafts._admin(actor)
            return {"ok": True, "connection": connection}
        if action == "tool_draft_trial_get":
            with self.service._db() as db:
                trial = self._trial(db, actor, key, body.get("trial_id"))
            return {"ok": True, "trial": await self.public_trial(actor, trial)}
        self._request(body)
        if action == "tool_draft_trial_start":
            return await self.start_trial(actor, body)
        async with self._locks.setdefault(key, asyncio.Lock()):
            if action == "tool_draft_connection_save":
                return await self.save_connection(actor, body)
            if action in {"tool_draft_use_set", "tool_draft_use_access", "tool_draft_use_disable", "tool_draft_use_enable"}:
                return await self.save_use(actor, body)
        _fail("tool_draft_invalid")

    async def save_connection(self, actor, body):
        key, request = body["tool_id"], body["request_id"]
        with self.service._db() as db:
            receipt = db.execute("SELECT tool_id,data FROM work_tool_connection_receipts WHERE actor=? AND request_id=?", (_get(actor, "id"), request)).fetchone()
            if receipt:
                if receipt["tool_id"] != key:
                    _fail("request_conflict")
                replay = json.loads(receipt["data"])
            else:
                replay = None
            draft = self.drafts._get(db, key)
            connection = self._connection(db, key)
        if replay is not None:
            if "tool_draft" in replay:
                replay["tool_draft"] = await self.decorate(actor, replay["tool_draft"])
            return replay
        self._revision(draft["revision"], body.get("expected_revision"))
        self._revision(connection["revision"], body.get("expected_connection_revision"))
        address = _base_url(body.get("base_url"))
        token = body.get("token", "")
        if not isinstance(token, str) or len(token) > 16384 or any(ord(c) < 32 for c in token):
            _fail("tool_connection_invalid")
        # Reserve this request before crossing the Native store. A lost result
        # must not cause another credential write when the request is replayed.
        pending = {"ok": False, "error": {"code": "tool_connection_pending", "message": "연결 저장 결과를 확인 중입니다. 연결 상태를 다시 확인해 주세요."}}
        with self.service._db(write=True) as db:
            receipt = db.execute("SELECT tool_id,data FROM work_tool_connection_receipts WHERE actor=? AND request_id=?", (_get(actor, "id"), request)).fetchone()
            if receipt:
                if receipt["tool_id"] != key:
                    _fail("request_conflict")
                return json.loads(receipt["data"])
            db.execute("INSERT INTO work_tool_connection_receipts VALUES(?,?,?,?)", (_get(actor, "id"), request, key, _json(pending)))
        try:
            metadata = await self.native.save_connection(actor, key, connection["native_id"], token)
        except WorkflowError as error:
            result = {"ok": False, "error": {"code": error.code, "message": "연결을 저장하지 못했습니다. 현재 계정과 기존 도구 설정을 확인해 주세요."}}
            with self.service._db(write=True) as db:
                db.execute("UPDATE work_tool_connection_receipts SET data=? WHERE actor=? AND request_id=?", (_json(result), _get(actor, "id"), request))
            return result
        actor = await self.drafts._admin(actor)
        with self.service._db(write=True) as db:
            self._revision(self.drafts._get(db, key)["revision"], draft["revision"])
            self._revision(self._connection(db, key)["revision"], connection["revision"])
            connection = {"revision": connection["revision"] + 1, "base_url": address, "native_id": metadata["native_id"]}
            db.execute("INSERT INTO work_tool_connections VALUES(?,?,?) ON CONFLICT(tool_id) DO UPDATE SET revision=excluded.revision,data=excluded.data", (key, connection["revision"], _json(connection)))
            self.service.operations._event(db, key, actor, "tool_draft_connection_save", {"revision": connection["revision"]})
        public = {**connection, "configured": bool(metadata["token_set"]), "token_set": bool(metadata["token_set"])}
        result = {"ok": True, "connection": public, "tool_draft": draft}
        # The receipt intentionally has no payload hash: tokens must not enter
        # receipts even through a derived request fingerprint.
        with self.service._db(write=True) as db:
            db.execute("UPDATE work_tool_connection_receipts SET data=? WHERE actor=? AND request_id=?", (_json(result), _get(actor, "id"), request))
        result["tool_draft"] = await self.decorate(actor, draft)
        return result

    async def start_trial(self, actor, body):
        key, request = body["tool_id"], body["request_id"]
        fingerprint = _digest({k: body.get(k) for k in ("tool_id", "expected_revision", "expected_connection_revision", "inputs")})
        with self.service._db() as db:
            old = db.execute("SELECT fingerprint,data FROM work_tool_trials WHERE actor=? AND request_id=?", (_get(actor, "id"), request)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    _fail("request_conflict")
                trial = json.loads(old["data"])
            else:
                trial = None
            draft = self.drafts._get(db, key)
            connection = self._connection(db, key)
        if trial:
            return {"ok": True, "trial": await self.public_trial(actor, trial)}
        self._revision(draft["revision"], body.get("expected_revision"))
        self._revision(connection["revision"], body.get("expected_connection_revision"))
        checked = check_draft(draft["draft"])
        if not checked["valid"]:
            _fail("tool_trial_definition_invalid", "기능·입력·결과의 확인할 내용을 먼저 보완해 주세요.")
        if not connection["native_id"] or not connection["base_url"]:
            _fail("tool_connection_required", "연결 설정을 먼저 저장해 주세요.")
        inputs = _inputs(checked["input_schema"], body.get("inputs"))
        metadata = await self.native.inspect(actor, connection["native_id"])
        if not metadata.get("token_set"):
            _fail("native_personal_connection_required", "개인 PAT 필요 · 기존 도구의 개인 설정에 본인 PAT를 저장하세요. 채팅에 입력하지 마세요.")
        public_inputs = await self.native.redact(actor, connection["native_id"], inputs)
        actor = await self.drafts._admin(actor)
        trial = {"id": "trial-" + uuid4().hex, "tool_id": key, "actor": _get(actor, "id"), "draft_revision": draft["revision"],
            "connection_revision": connection["revision"], "status": "running", "started_at": time.time(), "finished_at": None,
            "duration_ms": 0, "inputs": public_inputs, "rows": [], "raw_result": None, "count": 0, "completeness": "unknown",
            "fields_checked": False, "errors": [], "warnings": [], "_metadata": metadata,
            "_snapshot": {"draft": draft["draft"], "input_schema": checked["input_schema"], "base_url": connection["base_url"], "native_id": connection["native_id"], "environment": metadata["environment"]}}
        with self.service._db(write=True) as db:
            old = db.execute("SELECT fingerprint,data FROM work_tool_trials WHERE actor=? AND request_id=?", (_get(actor, "id"), request)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    _fail("request_conflict")
                previous = json.loads(old["data"])
            else:
                previous = None
                self._revision(self.drafts._get(db, key)["revision"], draft["revision"])
                self._revision(self._connection(db, key)["revision"], connection["revision"])
                db.execute("INSERT INTO work_tool_trials VALUES(?,?,?,?,?,?)", (trial["id"], key, _get(actor, "id"), request, fingerprint, _json(trial)))
        if previous:
            return {"ok": True, "trial": await self.public_trial(actor, previous)}
        cancelled = False
        try:
            outcome = await self.native.run(actor, connection["native_id"], draft["draft"]["code"], draft["draft"]["function"], connection["base_url"], inputs, metadata)
            trial["duration_ms"] = outcome.get("duration_ms", int((time.time() - trial["started_at"]) * 1000))
            if outcome.get("status") == "succeeded":
                trial.update(_result(outcome.get("raw_result"), draft["draft"]["output_ui"]))
            else:
                trial["status"] = "unknown" if outcome.get("status") == "unknown" else "failed"
                trial["errors"] = [_issue(outcome.get("error_code", "tool_trial_failed"), "시험을 완료하지 못했습니다. 연결과 입력을 확인한 뒤 다시 시험해 주세요.")]
        except asyncio.CancelledError:
            cancelled = True
            trial.update(status="unknown", errors=[_issue("tool_trial_interrupted", "시험이 중단되었습니다. 외부 처리 여부는 확인되지 않았습니다.")])
        except Exception:
            trial.update(status="unknown", errors=[_issue("tool_trial_unavailable", "시험 결과를 확인하지 못했습니다. 자동으로 다시 실행하지 않았습니다.")])
        trial["finished_at"] = time.time()
        with self.service._db(write=True) as db:
            current = self._trial(db, actor, key, trial["id"])
            if current["status"] == "running":
                db.execute("UPDATE work_tool_trials SET data=? WHERE id=?", (_json(trial), trial["id"]))
            else:
                trial = current
            self.service.operations._event(db, key, actor, "tool_draft_trial_finish", {"trial_id": trial["id"], "status": trial["status"]})
        if cancelled:
            raise asyncio.CancelledError()
        actor = await self.drafts._admin(actor)
        return {"ok": True, "trial": await self.public_trial(actor, trial)}

    async def _groups(self, selected, *, empty=False):
        source = self.service.group_list_lookup() if self.service.group_list_lookup else []
        groups = await source if inspect.isawaitable(source) else source
        known = {_get(group, "id") for group in groups}
        if not isinstance(selected, list) or (not selected and not empty) or any(not isinstance(group, str) or group not in known for group in selected):
            _fail("tool_use_groups_invalid", "현재 존재하는 그룹을 선택해 주세요.")
        return sorted(set(selected))

    async def save_use(self, actor, body):
        key, action, runtime = body["tool_id"], body["action"], self.service.operations
        with self.service._db() as db:
            receipt = runtime._receipt(db, actor, body)
            record = self.drafts._get(db, key)
            connection, old = self._connection(db, key), self._use(db, key)
        if receipt is not None:
            if "tool_draft" in receipt:
                receipt["tool_draft"] = await self.decorate(actor, receipt["tool_draft"])
            return receipt
        self._revision(old["revision"], body.get("expected_use_revision"))
        item, snapshot, trial = deepcopy(old), None, None
        if action == "tool_draft_use_set":
            self._revision(record["revision"], body.get("expected_revision"))
            self._revision(connection["revision"], body.get("expected_connection_revision"))
            with self.service._db() as db:
                trial = self._trial(db, actor, key, body.get("trial_id"))
            if not (await self.public_trial(actor, trial))["eligible_for_activation"]:
                _fail("tool_trial_stale", "현재 수정본과 연결로 다시 시험해 주세요.")
            evidence = body.get("evidence")
            if (not isinstance(evidence, str) or not 8 <= len(evidence.strip()) <= 2000
                    or re.search(r"bearer\s|authorization|password\s*[:=]|token\s*[:=]|pat\s*[:=]|cookie\s*[:=]|[\x00-\x08\x0b-\x1f]", evidence, re.I)
                    or _safe(evidence) != evidence
                    or await self.native.redact(actor, connection["native_id"], evidence) != evidence):
                _fail("tool_use_evidence_invalid", "비밀값 없이 시험 확인 근거를 8~2,000자로 작성해 주세요.")
            item.update(groups=await self._groups(body.get("groups")), evidence=evidence.strip(), confirmed_by=_get(actor, "id"), confirmed_at=time.time(), state="disabled" if old["state"] == "disabled" else "active")
            snapshot = trial["_snapshot"]
        elif not old["active_version"]:
            _fail("tool_use_unconfirmed", "현재 수정본을 시험한 뒤 사용 설정해 주세요.")
        elif action == "tool_draft_use_access":
            item["groups"] = await self._groups(body.get("groups"), empty=True)
        elif action == "tool_draft_use_disable":
            item["state"] = "disabled"
        elif action == "tool_draft_use_enable":
            if not old["groups"]:
                _fail("tool_use_groups_invalid", "사용할 그룹을 먼저 선택해 주세요.")
            item["groups"] = await self._groups(old["groups"])
            item["state"] = "active"
        restrictive = action == "tool_draft_use_disable" or (action == "tool_draft_use_access" and set(item["groups"]) <= set(old["groups"]))
        metadata = None
        try:
            metadata = await self.native.inspect(actor, connection["native_id"])
        except WorkflowError:
            if not restrictive:
                raise
        if not restrictive:
            if not metadata.get("token_set"):
                _fail("native_personal_connection_required")
            if snapshot is None:
                with self.service._db() as db:
                    row = db.execute("SELECT data FROM work_tool_authored_versions WHERE tool_id=? AND version=?", (key, old["active_version"])).fetchone()
                    observation = db.execute("SELECT environment FROM work_tool_use_observations WHERE tool_id=?", (key,)).fetchone()
                if not row:
                    _fail("tool_use_snapshot_invalid", "현재 사용 버전을 확인할 수 없습니다.")
                active = json.loads(row[0])["snapshot"]
                checked = check_draft(active["draft"])
                if (not checked["valid"] or checked["input_schema"] != active["input_schema"]
                        or active["native_id"] != metadata["native_id"] or not observation or observation[0] != metadata["environment"]):
                    _fail("tool_use_snapshot_invalid", "현재 사용 버전과 실행 환경을 확인한 뒤 다시 시험해 주세요.")
                _base_url(active["base_url"])
        changed_native = None
        before_groups = list(metadata.get("groups", old["groups"])) if metadata else []
        try:
            # A failure to write Native ACL is not the same as an unavailable
            # identity: only the latter permits Work-only restrictive changes.
            if metadata and action != "tool_draft_use_disable" and item["groups"] != before_groups:
                changed_native = await self.native.set_groups(actor, connection["native_id"], item["groups"], metadata["identity_stamp"])
            actor = await self.drafts._admin(actor)
            if metadata:
                observed = await self.native.inspect(actor, connection["native_id"])
                expected = trial["_metadata"] if trial else metadata
                if not restrictive and (not observed.get("token_set") or any(observed.get(k) != expected.get(k) for k in ("native_id", "credential_stamp", "environment"))):
                    _fail("tool_trial_stale", "시험 뒤 계정 연결이나 실행 환경이 바뀌었습니다. 다시 시험해 주세요.")
            # No await between the final Native observation and Work CAS.
            result, record = self._commit_use(actor, body, old, item, record, connection, snapshot)
        except BaseException:
            if changed_native is not None:
                try:
                    await self.native.set_groups(actor, connection["native_id"], before_groups, changed_native["identity_stamp"])
                except Exception:
                    with self.service._db(write=True) as db:
                        runtime._event(db, key, actor, "tool_use_sync_required", {"request_id": body["request_id"], "use_revision": old["revision"]})
                    _fail("tool_use_sync_required", "사용 설정을 완료하지 못했습니다. 연결용 도구의 권한 상태를 다시 확인해 주세요.")
            raise
        if action == "tool_draft_use_set":
            result["tool_draft"] = await self.decorate(actor, record)
        return result

    def _commit_use(self, actor, body, old, item, record, connection, snapshot):
        key, runtime = body["tool_id"], self.service.operations
        with self.service._db(write=True) as db:
            receipt = runtime._receipt(db, actor, body)
            if receipt is not None:
                return receipt, record
            self._revision(self._use(db, key)["revision"], old["revision"])
            if snapshot is not None:
                self._revision(self.drafts._get(db, key)["revision"], record["revision"])
                self._revision(self._connection(db, key)["revision"], connection["revision"])
                previous = db.execute("SELECT data FROM work_tool_authored_versions WHERE tool_id=? AND version=?", (key, old["active_version"])).fetchone()
                previous = json.loads(previous[0]) if previous else None
                project = lambda s: {"code": s["draft"]["code"], "function": s["draft"]["function"], "input_ui": s["draft"]["input_ui"], "output_ui": s["draft"]["output_ui"], "input_schema": s["input_schema"], "base_url": s["base_url"], "native_id": s["native_id"]}
                if previous is None or project(previous["snapshot"]) != project(snapshot):
                    item["active_version"] = (old["active_version"] or 0) + 1
                    version = {"version": item["active_version"], "confirmed_by": item["confirmed_by"], "confirmed_at": item["confirmed_at"], "evidence": item["evidence"]}
                    item["versions"].append(version)
                    db.execute("INSERT INTO work_tool_authored_versions VALUES(?,?,?)", (key, item["active_version"], _json({**version, "snapshot": snapshot})))
                record = self.drafts._get(db, key)
                record["active_version"] = item["active_version"]
                db.execute("UPDATE work_tool_drafts SET data=? WHERE id=?", (_json(record), key))
                db.execute("INSERT INTO work_tool_use_observations VALUES(?,?) ON CONFLICT(tool_id) DO UPDATE SET environment=excluded.environment", (key, snapshot["environment"]))
            item["revision"] += 1
            db.execute("INSERT INTO work_tool_uses VALUES(?,?,?) ON CONFLICT(tool_id) DO UPDATE SET revision=excluded.revision,data=excluded.data", (key, item["revision"], _json(item)))
            runtime._event(db, key, actor, body["action"], {"revision": item["revision"], "active_version": item["active_version"]})
            result = {"ok": True, "use": item}
            if snapshot is not None:
                result["tool_draft"] = record
            runtime._remember(db, actor, body, result)
        return result, record
