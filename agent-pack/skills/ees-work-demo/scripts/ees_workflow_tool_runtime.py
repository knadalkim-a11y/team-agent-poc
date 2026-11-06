"""Authored use versions in the existing shared-tool execution paths.

The lifecycle tables remain canonical. Public pins identify immutable versions;
only this server boundary resolves their source and the actor's Native settings.
"""
from copy import deepcopy
from contextlib import nullcontext
import json
import time

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_tool_lifecycle import _digest, _get, _inputs, _path, _result


def is_authored_reference(reference):
    return isinstance(reference, dict) and reference.get("kind") == "authored"


def _fail(code, message="도구의 현재 사용 설정·권한·입력을 확인해 주세요."):
    from .ees_workflow_shared_tools import message_for
    raise WorkflowError(code, message_for(code, message))


class AuthoredResult(dict):
    """JSON result with a process-local final CAS; never serialized as data."""
    def __init__(self, values, check_current, seal):
        super().__init__(values)
        self.check_current = check_current
        self.seal = seal


class AuthoredToolRuntime:
    def __init__(self, service):
        self.service = service

    is_authored_reference = staticmethod(is_authored_reference)

    @staticmethod
    def is_key(key):
        return isinstance(key, str) and key.startswith("draft-")

    @property
    def native(self):
        return self.service.tool_drafts.lifecycle.native

    def _version(self, db, key, version):
        row = db.execute("SELECT data FROM work_tool_authored_versions WHERE tool_id=? AND version=?", (key, version)).fetchone()
        if not row:
            _fail("shared_tool_review_required")
        return json.loads(row[0])["snapshot"]

    @staticmethod
    def _reference(key, version, snapshot):
        return {"kind": "authored", "tool_id": key, "version": version, "snapshot_hash": _digest(snapshot)}

    def snapshot(self, db, reference):
        if not is_authored_reference(reference):
            _fail("shared_tool_review_required")
        snapshot = self._version(db, reference.get("tool_id"), reference.get("version"))
        if reference != self._reference(reference["tool_id"], reference["version"], snapshot):
            _fail("shared_tool_plan_changed")
        return snapshot

    def get(self, db, key):
        use = self.service.tool_drafts.lifecycle._use(db, key)
        if not use.get("active_version"):
            _fail("shared_tool_review_required")
        snapshot = self._version(db, key, use["active_version"])
        draft = snapshot["draft"]
        return {"id": key, "source": "authored", "version": use["active_version"], "revision": use["revision"],
                "name": draft["name"], "description": draft["description"], "target": draft["target"],
                "function": draft["function"], "kind": "read", "auth": "개인 PAT(기존 방식)",
                "state": "available" if use["state"] == "active" else "disabled",
                "group_ids": deepcopy(use["groups"]), "input_schema": deepcopy(snapshot["input_schema"]),
                "input_ui": deepcopy(draft["input_ui"]), "output_ui": deepcopy(draft["output_ui"]),
                "output_schema": {"kind": "list", "fields": [field["path"] for field in draft["output_ui"]["fields"]], "completeness": "partial_possible"},
                "reference": self._reference(key, use["active_version"], snapshot)}

    def describe_pin(self, db, pin):
        snapshot = self.snapshot(db, pin["reference"])
        return {**deepcopy(pin), "source": "authored", "name": snapshot["draft"]["name"],
                "input_schema": deepcopy(snapshot["input_schema"]),
                "input_ui": deepcopy(snapshot["draft"]["input_ui"]), "output_ui": deepcopy(snapshot["draft"]["output_ui"])}

    def validate_arguments(self, reference, arguments):
        with self.service._db() as db:
            schema = self.snapshot(db, reference)["input_schema"]
        return _inputs(schema, arguments)

    def _current(self, db, actor, groups, pin, *, kind=None, run_id=None, environment=None):
        item = self.get(db, pin["id"])
        self.service.shared_tools.authorize(item, actor, groups)
        if item["state"] != "available":
            _fail("shared_tool_disabled")
        if item["version"] != pin["version"] or item["reference"] != pin["reference"]:
            from .ees_workflow_shared_tools import fail
            fail("shared_tool_version_changed", pinned=pin["version"], current=item["version"])
        if run_id:
            row = db.execute("SELECT data FROM work_shared_tool_pins WHERE run_kind=? AND run_id=? AND tool_id=?", (kind, run_id, pin["id"])).fetchone()
            if not row or json.loads(row[0]) != pin:
                _fail("shared_tool_plan_changed")
        if environment is not None:
            row = db.execute("SELECT environment FROM work_tool_use_observations WHERE tool_id=?", (pin["id"],)).fetchone()
            if not row or row[0] != environment:
                _fail("shared_tool_review_required")
        return item

    async def resolve(self, user, key, *, kind=None, run_id=None):
        actor, _, groups = await self.service._work_actor(user)
        with self.service._db() as db:
            item = self.get(db, key)
            pin = {key: deepcopy(item[key]) for key in ("id", "version", "reference")}
            if run_id:
                row = db.execute("SELECT data FROM work_shared_tool_pins WHERE run_kind=? AND run_id=? AND tool_id=?", (kind, run_id, key)).fetchone()
                if not row:
                    _fail("shared_tool_review_required")
                pin = json.loads(row[0])
            self._current(db, actor, groups, pin, kind=kind, run_id=run_id)
            snapshot = self.snapshot(db, pin["reference"])
        metadata = await self.native.inspect_execution(actor, snapshot["native_id"])
        if not metadata.get("token_set"):
            _fail("native_personal_connection_required")
        actor, _, groups = await self.service._work_actor(actor)
        with self.service._db() as db:
            latest = self._current(db, actor, groups, pin, kind=kind, run_id=run_id, environment=metadata["environment"])
            if sorted(latest["group_ids"]) != sorted(metadata.get("groups", [])):
                _fail("shared_tool_review_required")
        return pin

    async def evidence_access(self, user, pin):
        actor, _, groups = await self.service._work_actor(user)
        with self.service._db() as db:
            self.service.shared_tools.authorize(self.get(db, pin["id"]), actor, groups)
            snapshot = self.snapshot(db, pin["reference"])
        metadata = await self.native.inspect_execution(actor, snapshot["native_id"])
        if not metadata.get("token_set"):
            _fail("native_personal_connection_required")
        actor, _, groups = await self.service._work_actor(actor)
        with self.service._db() as db:
            self.service.shared_tools.authorize(self.get(db, pin["id"]), actor, groups)

    def _uses(self, db, actor, groups, key):
        uses = []
        for row in db.execute("SELECT * FROM work_definitions"):
            try:
                self.service._work_definition(db, actor, groups, row["id"])
            except WorkflowError:
                continue
            versions = []
            try:
                self.service._work_definition(db, actor, groups, row["id"], True)
                versions.append(("draft", json.loads(row["draft"])))
            except WorkflowError:
                pass
            published = db.execute("SELECT definition FROM work_versions WHERE workflow_id=? AND version=?", (row["id"], row["published_version"])).fetchone()
            if published:
                versions.append(("published", json.loads(published[0])))
            for state, definition in versions:
                nodes = definition.get("nodes", {})
                for node in nodes.values():
                    if node.get("shared_tool_id") != key and not any(call.get("shared_tool_id") == key for call in (node.get("execution") or {}).get("calls", [])):
                        continue
                    stage = nodes.get(node.get("parent"), {})
                    uses.append({"workflow_id": row["id"], "workflow_name": definition.get("name", ""), "system_id": row["system_id"],
                                 "stage_id": stage.get("id", ""), "stage_name": stage.get("name", ""), "job_id": node["id"], "job_name": node["name"],
                                 "definition_state": state, "automatic": False})
            for scheduled in db.execute("SELECT * FROM work_schedules WHERE workflow_id=?", (row["id"],)):
                schedule = json.loads(scheduled["data"])
                if not schedule.get("delegated"):
                    continue
                try:
                    self.service._work_authorize_scope(db, actor, groups, row['system_id'], schedule.get('factory_id', ''), 'viewer')
                except WorkflowError:
                    continue
                version = db.execute("SELECT definition FROM work_versions WHERE workflow_id=? AND version=?", (row["id"], schedule["version"])).fetchone()
                nodes = json.loads(version[0]).get("nodes", {}) if version else {}
                for job_id in schedule.get("job_ids", []):
                    node = nodes.get(job_id, {})
                    if node.get("shared_tool_id") != key:
                        continue
                    stage = nodes.get(node.get("parent"), {})
                    uses.append({"workflow_id": row["id"], "workflow_name": json.loads(version[0]).get("name", ""), "system_id": row["system_id"],
                                 "stage_id": stage.get("id", ""), "stage_name": stage.get("name", ""), "job_id": job_id, "job_name": node["name"],
                                 "definition_state": "schedule", "automatic": True, "schedule_id": scheduled["id"], "schedule_state": "enabled" if scheduled["enabled"] else "disabled"})
        return uses

    async def list(self, user, *, usable_only=False, summary=False):
        actor, _, groups = await self.service._work_actor(user)
        with self.service._db() as db:
            keys = [row[0] for row in db.execute("SELECT tool_id FROM work_tool_uses WHERE json_extract(data,'$.active_version') IS NOT NULL")]
        result = []
        for key in keys:
            with self.service._db() as db:
                item = self.get(db, key)
                snapshot = self.snapshot(db, item["reference"])
            if _get(actor, "role") != "admin" and not set(item["group_ids"]).intersection(groups):
                continue
            reason = "shared_tool_disabled" if item["state"] == "disabled" else ""
            try:
                metadata = await self.native.inspect_execution(actor, snapshot["native_id"])
                with self.service._db() as db:
                    observed = db.execute("SELECT environment FROM work_tool_use_observations WHERE tool_id=?", (key,)).fetchone()
                if not observed or observed[0] != metadata["environment"] or sorted(item["group_ids"]) != sorted(metadata.get("groups", [])):
                    reason = "shared_tool_review_required"
            except WorkflowError as error:
                reason = error.code
            actor, _, groups = await self.service._work_actor(actor)
            with self.service._db() as db:
                latest = self.get(db, key)
                if latest != item:
                    item, reason = latest, "shared_tool_review_required"
                if _get(actor, "role") != "admin" and not set(item["group_ids"]).intersection(groups):
                    continue
                item["uses"] = self._uses(db, actor, groups, key) if not summary else []
                # Classification is a catalog filter, not an execution grant or
                # part of the immutable version pinned by an existing run.
                item["scope"] = deepcopy(self.service.tool_drafts._get(db, key)["draft"].get("scope", {}))
            if reason:
                item["state"] = "disabled" if reason == "shared_tool_disabled" else "review_required" if reason == "shared_tool_review_required" else "unavailable"
            from .ees_workflow_shared_tools import message_for
            item.update(can_use=bool(set(item["group_ids"]).intersection(groups)), unavailable_reason=reason,
                        unavailable_message=message_for(reason) if reason else "")
            item.pop("reference", None)
            if not usable_only or item["state"] == "available" and item["can_use"]:
                result.append(item)
        return result

    def _context_current(self, db, actor, groups, context, arguments):
        """No awaits: final Work-side CAS immediately beside Native dispatch."""
        kind = context.get("shared_run_kind")
        if kind == "work":
            run = self.service._work_run(db, actor, groups, context["run_id"], write=True)
            row = db.execute("SELECT * FROM work_attempts WHERE id=? AND run_id=? AND job_id=?", (context["call_id"], run["id"], context["job_id"])).fetchone()
            claim = db.execute("SELECT * FROM work_job_claims WHERE attempt_id=?", (context["call_id"],)).fetchone()
            job = db.execute("SELECT * FROM work_jobs WHERE run_id=? AND job_id=?", (run["id"], context["job_id"])).fetchone()
            if (not row or row["status"] != "running" or row["actor_id"] != _get(actor, "id") or not job
                    or job["current_attempt"] != row["id"] or job["status"] != "running" or not claim
                    or claim["state"] != "running" or claim["worker"] != self.service.operations.worker
                    or claim["lease"] < self.service.operations.clock()):
                _fail("execution_result_unknown")
            prior = json.loads(row["snapshot"])
            current = self.service._work_snapshot(db, run, row["job_id"])
            if (json.loads(row["inputs"]) != current["inputs"] or prior.get("arguments") != arguments
                    or (prior.get("deadline_source") or {}).get("value") != (current.get("deadline_source") or {}).get("value")
                    or not self.service._work_sources_current(db, run, prior)):
                _fail("result_source_changed")
        elif kind == "execution":
            row, run = self.service.execution._load_run(db, _get(actor, "id"), context["run_id"])
            self.service._case(db, _get(actor, "id"), run["case_id"])
            record = db.execute("SELECT data FROM execution_calls WHERE run_id=? AND job_id=? AND call_id=? AND attempt=? AND state='running'", (run["id"], context["job_id"], context["call_id"], context["attempt"])).fetchone()
            if (run["status"] != "running" or run["plan_hash"] != context["plan_hash"] or row["worker"] != self.service.execution.worker_id
                    or row["lease"] < time.time() or not record or json.loads(record[0])["arguments"] != arguments):
                _fail("execution_result_unknown")
        else:
            _fail("shared_tool_plan_changed")

    async def invoke(self, user, reference, arguments, context):
        key, kind, run_id = reference.get("tool_id"), context.get("shared_run_kind"), context.get("run_id")
        pin = await self.resolve(user, key, kind=kind, run_id=run_id)
        if pin["reference"] != reference:
            _fail("shared_tool_plan_changed")
        with self.service._db() as db:
            snapshot = self.snapshot(db, reference)
        inputs = _inputs(snapshot["input_schema"], arguments)
        metadata = await self.native.inspect_execution(user, snapshot["native_id"])
        final_check = None

        async def dispatch_guard():
            nonlocal final_check
            actor, _, groups = await self.service._work_actor(user)
            if kind == "execution":
                await self.service.execution._access(actor, context["case_id"])
            def current(transaction=None):
                with (nullcontext(transaction) if transaction is not None else self.service._db()) as db:
                    latest = self._current(db, actor, groups, pin, kind=kind, run_id=run_id, environment=metadata["environment"])
                    if sorted(latest["group_ids"]) != sorted(metadata.get("groups", [])):
                        _fail("shared_tool_review_required")
                    self._context_current(db, actor, groups, context, arguments)
            current()
            final_check = current
            return current

        async def seal():
            # Caller invokes this after heartbeat/task cleanup awaits. Re-read
            # this actor's current Native settings, then synchronously check
            # Work state immediately before attaching the result.
            current = await dispatch_guard()
            latest = await self.native.inspect_execution(user, snapshot['native_id'])
            if latest != metadata:
                _fail('tool_trial_snapshot_changed')
            current()

        outcome = await self.native.run_execution(user, snapshot, inputs, metadata, context, dispatch_guard)
        if outcome.get("status") != "succeeded":
            return {"source": "authored", "status": outcome.get("status", "unknown"), "completeness": "unknown", "items": [], "count": 0,
                    "fields_checked": False, "raw_result": None, "duration_ms": outcome.get("duration_ms", 0), "error": {"code": outcome.get("error_code", "execution_result_unknown")}}
        result = _result(outcome.get("raw_result"), snapshot["draft"]["output_ui"])
        if result["completeness"] == "partial" and all(issue["code"] == "tool_trial_partial" for issue in result["errors"]):
            result.update(status="partial", errors=[], warnings=[{"code": "tool_result_partial", "message": "일부 결과입니다. 이 한계를 확인한 뒤 작업 전체를 판정해 주세요."}])
        items = []
        for index, row in enumerate(result.pop("rows")):
            item = {"id": "row-" + str(index + 1), "row": deepcopy(row), "required": False}
            for field in snapshot["draft"]["output_ui"]["fields"]:
                if not field.get("hidden") and field["role"] in {"title", "category", "url"}:
                    item.setdefault(field["role"], _path(row, field["path"]))
            items.append(item)
        return AuthoredResult({**result, "source": "authored", "items": items, "duration_ms": outcome.get("duration_ms", 0)}, lambda transaction=None: final_check(transaction), seal)
