"""Administrator-authored, non-executable tool drafts.

Drafts are intentionally not part of SharedTools discovery or Native registration.
Saving code never imports it or replaces an active tool/reference.
"""
from copy import deepcopy
import json
import re
from uuid import uuid4

from .ees_workflow_authoring import WorkflowError
from .ees_workflow_tool_draft_check import check_draft


def _value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _fail(code="tool_draft_invalid", message="도구의 입력 내용을 확인해 주세요."):
    raise WorkflowError(code, message)


def normalize_draft(value):
    """Bound the storage envelope, retaining unfinished definitions for editing."""
    defaults = dict(name="", description="", target="", kind="read", code="", function="",
                    input_ui={}, output_ui={"kind": "list", "path": "", "fields": []})
    if not isinstance(value, dict) or set(value) - (set(defaults) | {"scope"}):
        _fail()
    draft = {**defaults, **value}
    if "scope" in draft:
        scope = draft["scope"]
        if (not isinstance(scope, dict) or set(scope) - {"system_id", "factory_id"}
                or any(not isinstance(v, str) or len(v) > 200 or "\x00" in v for v in scope.values())):
            _fail(message="도구의 공장·시스템 분류를 확인해 주세요.")
        draft["scope"] = {"system_id": "", "factory_id": "", **scope}
        if draft["scope"]["factory_id"] and not draft["scope"]["system_id"]:
            _fail(message="공장을 분류하려면 시스템도 선택해 주세요.")
    for key, limit in (("name", 160), ("description", 2000), ("target", 160),
                       ("code", 262144), ("function", 200)):
        if not isinstance(draft[key], str) or len(draft[key]) > limit or "\x00" in draft[key]:
            _fail(message="도구의 글자 형식이나 길이를 확인해 주세요.")
    if draft["kind"] != "read" or not isinstance(draft["input_ui"], dict) or not isinstance(draft["output_ui"], dict):
        _fail()
    inputs = {}
    for key, item in draft["input_ui"].items():
        if not isinstance(key, str) or not isinstance(item, dict) or set(item) - {"label", "question", "widget", "option_labels", "default"}:
            _fail()
        item = {"label": "", "question": "", "widget": "text", "option_labels": {}, **item}
        if any(not isinstance(item[field], str) for field in ("label", "question", "widget")):
            _fail()
        if not isinstance(item["option_labels"], dict) or any(not isinstance(option, str) or not isinstance(label, str) for option, label in item["option_labels"].items()):
            _fail()
        inputs[key] = item
    output = {"kind": "list", "path": "", "fields": [], **draft["output_ui"]}
    if set(output) - {"kind", "path", "fields"} or any(not isinstance(output[field], str) for field in ("kind", "path")) or not isinstance(output["fields"], list):
        _fail()
    fields = []
    for item in output["fields"]:
        if not isinstance(item, dict) or set(item) - {"path", "label", "role", "hidden"}:
            _fail()
        item = {"path": "", "label": "", "role": "text", "hidden": False, **item}
        if any(not isinstance(item[field], str) for field in ("path", "label", "role")) or type(item["hidden"]) is not bool:
            _fail()
        fields.append(item)
    draft["input_ui"], draft["output_ui"] = inputs, {**output, "fields": fields}
    try:
        packed = json.dumps(draft, ensure_ascii=False, allow_nan=False)
        if len(packed.encode("utf-8")) > 1024 * 1024:
            _fail(message="도구 내용이 너무 큽니다.")
        # This round trip also rejects unsupported non-JSON values.
        draft = json.loads(packed)
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _fail()
    return draft


def default_inputs(schema):
    result = {}
    for key, shape in schema.get("properties", {}).items():
        actual = next((item for item in shape.get("anyOf", []) if item.get("type") != "null"), shape)
        choices = actual.get("items", {}).get("enum") if actual.get("type") == "array" else actual.get("enum")
        widget = "multiselect" if actual.get("type") == "array" and choices else "select" if choices else {
            "integer": "number", "number": "number", "boolean": "boolean"}.get(actual.get("type"), "text")
        labels = {"true" if v is True else "false" if v is False else str(v): str(v) for v in (choices or [])}
        item = {"label": key, "question": key, "widget": widget, "option_labels": labels}
        if "default" in shape:
            item["default"] = deepcopy(shape["default"])
        elif widget == "multiselect":
            item["default"] = []
        result[key] = item
    return result


class ToolDrafts:
    def __init__(self, service):
        self.service = service
        with service._db(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS work_tool_drafts(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)")
        from .ees_workflow_tool_lifecycle import ToolLifecycle
        self.lifecycle = ToolLifecycle(self)

    async def _admin(self, user):
        actor = await self.service._user(user)
        if _value(actor, "role") != "admin":
            _fail("admin_required", "관리자만 도구를 작성할 수 있습니다.")
        return actor

    @staticmethod
    def _get(db, key):
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", key):
            _fail()
        row = db.execute("SELECT data FROM work_tool_drafts WHERE id=?", (key,)).fetchone()
        if not row:
            _fail("tool_draft_not_found", "작성한 도구를 찾을 수 없습니다. 목록을 다시 확인해 주세요.")
        return json.loads(row["data"])

    async def summaries(self, user):
        actor = await self.service._user(user)
        if _value(actor, "role") != "admin":
            return []
        with self.service._db() as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT data FROM work_tool_drafts ORDER BY id")]
            uses = {row[0]: json.loads(row[1]) for row in db.execute("SELECT tool_id,data FROM work_tool_uses")}
        return [{"id": item["id"], **{key: item["draft"][key] for key in ("name", "description", "target", "kind")},
                 "scope": deepcopy(item["draft"].get("scope", {})),
                 "revision": item["revision"], "active_version": item["active_version"],
                 "state": uses.get(item["id"], {}).get("state", "draft"), "updated_at": item["updated_at"]} for item in records]

    async def sources(self, user):
        actor = await self.service._user(user)
        if _value(actor, "role") != "admin":
            return []
        self.service.operations.configure()
        bridge = self.service.operations.bridge
        result = await bridge.tool_import_sources(actor) if hasattr(bridge, "tool_import_sources") else []
        return result if _value(await self.service._user(actor), "role") == "admin" else []

    async def command(self, user, body):
        actor = await self._admin(user)
        action = body.get("action")
        if action == "tool_draft_get":
            with self.service._db() as db:
                record = self._get(db, body.get("tool_id"))
            return {"ok": True, "tool_draft": await self.lifecycle.decorate(actor, record)}
        if action == "tool_draft_check":
            return {"ok": True, "check": check_draft(normalize_draft(body.get("draft")))}
        if action not in {"tool_draft_save", "tool_draft_import"}:
            return await self.lifecycle.command(actor, body)
        runtime = self.service.operations
        with self.service._db() as db:
            receipt = runtime._receipt(db, actor, body)
        if receipt is not None:
            return {**receipt, "tool_draft": await self.lifecycle.decorate(actor, receipt["tool_draft"])}
        if action == "tool_draft_import":
            runtime.configure()
            bridge = runtime.bridge
            if not hasattr(bridge, "read_tool_import_source"):
                _fail("tool_draft_source_unavailable", "가져올 도구를 확인할 수 없습니다.")
            try:
                source = await bridge.read_tool_import_source(actor, body.get("source_tool_id"), body.get("function"))
            except WorkflowError:
                _fail("tool_draft_source_unavailable", "가져올 도구의 현재 권한과 기능을 확인해 주세요.")
            draft = normalize_draft({"name": source["name"], "code": source["code"], "function": source["function"],
                                     **({"scope": body["scope"]} if "scope" in body else {})})
            parsed = check_draft(draft)
            draft["input_ui"] = default_inputs(parsed["input_schema"])
            key = None
        else:
            draft = normalize_draft(body.get("draft"))
            key = body.get("tool_id")
            if key is not None and not isinstance(key, str):
                _fail()
        checked = check_draft(draft)
        # Native reads may await: authorization is refreshed before the write.
        actor = await self._admin(actor)
        with self.service._db(write=True) as db:
            receipt = runtime._receipt(db, actor, body)
            if receipt is not None:
                return receipt
            old = self._get(db, key) if key is not None else None
            # Older clients do not send classification. Preserve it on update.
            if "scope" not in draft and old and "scope" in old["draft"]:
                draft["scope"] = deepcopy(old["draft"]["scope"])
            scope = draft.get("scope", {})
            if scope.get("system_id"):
                self.service._work_authorize_scope(db, actor, [], scope["system_id"], role="manager")
            if scope.get("factory_id"):
                factory = db.execute("SELECT system_id FROM work_factories WHERE id=?", (scope["factory_id"],)).fetchone()
                if not factory or factory["system_id"] != scope["system_id"]:
                    _fail(message="선택한 시스템의 공장으로 분류해 주세요.")
            revision = old["revision"] if old else 0
            if type(body.get("expected_revision")) is not int or body["expected_revision"] != revision:
                _fail("tool_draft_conflict", "다른 변경이 저장되었습니다. 입력은 유지하고 최신 저장본을 확인해 주세요.")
            now = runtime.clock()
            record = {"id": old["id"] if old else "draft-" + uuid4().hex, "revision": revision + 1,
                      "active_version": old["active_version"] if old else None,
                      "draft": draft, "check": checked, "created_by": old["created_by"] if old else _value(actor, "id"),
                      "updated_by": _value(actor, "id"), "created_at": old["created_at"] if old else now,
                      "updated_at": now}
            data = json.dumps(record, ensure_ascii=False, allow_nan=False)
            db.execute("INSERT INTO work_tool_drafts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data",
                       (record["id"], record["revision"], data))
            # Audit metadata excludes source code, settings and actual secrets.
            runtime._event(db, record["id"], actor, action, {"revision": record["revision"], "valid": checked["valid"]})
            result = runtime._remember(db, actor, body, {"ok": True, "tool_draft": record})
        return {**result, "tool_draft": await self.lifecycle.decorate(actor, record)}
