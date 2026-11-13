"""Workspace service directory and versioned API contracts in workflow SQLite."""
import json
import os
import re
import sqlite3
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from .ees_workflow_api_openapi import SENSITIVE, TYPES, VERBS, http_url, invalid, parse_document, string, validate_json
from .ees_workflow_authoring import WorkflowError
from .ees_workflow_operations import dump


CORE = ("name","purpose","service_id","method","url","inputs","result_path","fields","example","state","group_ids")
ORIGIN = ("source_url","source_name","source_version","operation_key","source_path","provider_name","provider_purpose")
RESERVED_HEADERS = {"host","content-length","connection","transfer-encoding","proxy-authorization","accept-encoding","set-cookie"}
WIRE_NAME = re.compile(r"^[^\s{}?&#=/\\\x00-\x1f]{1,120}$")
FIELD_PATH = re.compile(r"^[^\s.\[\]/\\\x00-\x1f]+(\.[^\s.\[\]/\\\x00-\x1f]+)*$")


def list_of(value_, maximum=256):
    if not isinstance(value_, list) or len(value_) > maximum:
        invalid("목록 항목과 크기를 확인하세요.")
    return value_


def path(value_, empty=False):
    raw = string(value_, 256, required=not empty)
    if raw and not FIELD_PATH.fullmatch(raw):
        invalid("필드 경로는 점으로 구분한 속성 이름으로 입력하세요.")
    return raw


def normalize(api, service_id, old=None):
    if not isinstance(api, dict):
        invalid("API 명세를 입력하세요.")
    values = {**(old or {}), **api}
    method = string(values.get("method", "GET"), 10).upper()
    if method not in VERBS:
        invalid("지원하는 HTTP 요청 방식을 선택하세요.")
    url = http_url(values.get("url"), relative=bool(values.get("source_path")),query=True)
    inputs = []
    for item in list_of(values.get("inputs", [])):
        if not isinstance(item, dict):
            invalid("입력 정의를 확인하세요.")
        name = string(item.get("name"), 120, required=True)
        wire = string(item.get("wire_name", name), 120, required=True)
        loc = item.get("in","query")
        kind = item.get("type","string")
        required = item.get("required", loc == "path")
        if (not WIRE_NAME.fullmatch(name) or not WIRE_NAME.fullmatch(wire) or loc not in ("query","path","header","body")
                or not isinstance(kind, str) or kind not in TYPES or type(required) is not bool or loc == "path" and not required):
            invalid("입력 이름, 위치, 필수 여부와 자료형을 확인하세요.")
        if loc == "header" and (not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+",wire) or wire.lower() in RESERVED_HEADERS):
            invalid("서버 관리 헤더는 작업 입력으로 지정할 수 없습니다.")
        if SENSITIVE.search(wire):
            invalid("인증 정보는 서비스 연결 설정에서 관리하세요.")
        inputs.append({"name":name,"wire_name":wire,"in":loc,"label":string(item.get("label") or name, 1024),
                       "type":kind,"required":required})
        if item.get("whole_body"):
            if loc != "body" or item["whole_body"] is not True:
                invalid("전체 JSON 본문은 하나의 본문 입력으로 지정하세요.")
            inputs[-1]["whole_body"] = True
    body_inputs = [item for item in inputs if item["in"] == "body"]
    if (body_inputs and method in ("GET", "HEAD", "OPTIONS")
            or any(item.get("whole_body") for item in body_inputs) and len(body_inputs) != 1):
        invalid("요청 방식과 JSON 본문 입력 구성을 확인하세요.")
    if len({i["name"] for i in inputs}) != len(inputs) or len({(i["in"],i["wire_name"].lower() if i["in"]=="header" else i["wire_name"]) for i in inputs}) != len(inputs):
        invalid("입력 이름과 요청 위치가 중복되었습니다.")
    template = urlsplit(url).path
    if re.sub(r"\{[^{}]+\}", "", template).count("{") or "}" in re.sub(r"\{[^{}]+\}","",template):
        invalid("경로 변수 중괄호를 확인하세요.")
    if {i["wire_name"] for i in inputs if i["in"]=="path"} != set(re.findall(r"\{([^{}]+)\}", template)):
        invalid("주소의 각 경로 변수에 필수 입력을 지정하세요.")
    by_wire = {(i["in"], i["wire_name"]):i for i in inputs}
    for wire, qvalue in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if "{" in qvalue or "}" in qvalue:
            if not re.fullmatch(r"\{[^{}]+\}", qvalue) or not by_wire.get(("query",wire), {}).get("required"):
                invalid("주소의 쿼리 변수마다 필수 쿼리 입력을 지정하세요.")
    fields = []
    for f in list_of(values.get("fields", [])):
        if not isinstance(f, dict) or not isinstance(f.get("type", "string"), str) or f.get("type","string") not in TYPES:
            invalid("결과 필드 자료형을 확인하세요.")
        key = path(f.get("path"))
        fields.append({"path":key,"label":string(f.get("label") or key, 180),"type":f.get("type","string")})
        if f.get("root_value"):
            if key != "$" or f["root_value"] is not True:
                invalid("응답 값 전체는 필드 경로 $로 지정하세요.")
            fields[-1]["root_value"] = True
    if len({f["path"] for f in fields}) != len(fields):
        invalid("결과 필드 경로를 중복으로 등록할 수 없습니다.")
    group_ids = sorted({string(g,200,required=True) for g in list_of(values.get("group_ids", []))})
    example = values.get("example")
    validate_json(example, maximum=6000, scrub=True)
    if len(dump(example).encode("utf-8")) > 96_000:
        invalid("96 KB 이내의 응답 예시를 입력하세요.")
    state = values.get("state","active")
    if state not in ("active","withdrawn","deprecated"):
        invalid("API의 사용 상태를 확인하세요.")
    return {"name":string(values.get("name"),180,required=True),"purpose":string(values.get("purpose"),8192,required=True),
            "service_id":service_id,"method":method,"url":url,"inputs":inputs,"result_path":path(values.get("result_path",""), True),
            "fields":fields,"example":example,"state":state,"group_ids":group_ids}


def changes(old, new):
    if not old:
        return []
    result = []
    def difference(kind, key, before, after):
        if before != after:
            change = "added" if before is None else "removed" if after is None else "changed"
            result.append({"kind":kind,"path":key,"change":change,"before":before,"after":after})
    for field, kind, key in (("fields","field","path"),("inputs","input","name")):
        before = {a[key]:a for a in old.get(field, [])}
        after = {a[key]:a for a in new.get(field, [])}
        for prop in sorted(before.keys() | after.keys()):
            difference(kind,prop,before.get(prop),after.get(prop))
    for k in ("state","method","url","result_path","name","purpose","service_id","group_ids","example","source_version","operation_key","source_path"):
        difference("state" if k=="state" else "operation",k,old.get(k),new.get(k))
    return result


class ApiCatalog:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def init(db):
        # Individual statements retain the enclosing workflow startup transaction.
        for ddl in (
            "CREATE TABLE IF NOT EXISTS work_api_services(id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, revision INTEGER NOT NULL)",
            "CREATE TABLE IF NOT EXISTS work_api_operations(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, service_id TEXT NOT NULL, method TEXT NOT NULL, url TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(service_id, method, url))",
            "CREATE TABLE IF NOT EXISTS work_api_versions(api_id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(api_id,version))",
            "CREATE TRIGGER IF NOT EXISTS work_api_versions_immutable BEFORE UPDATE ON work_api_versions BEGIN SELECT RAISE(ABORT,'immutable API version'); END",
            "CREATE TRIGGER IF NOT EXISTS work_api_versions_retained BEFORE DELETE ON work_api_versions BEGIN SELECT RAISE(ABORT,'immutable API version'); END",
        ):
            db.execute(ddl)

    @staticmethod
    def _all(db):
        return [json.loads(row[0]) for row in db.execute("SELECT data FROM work_api_operations ORDER BY service_id,id")]

    @staticmethod
    def _get(db, key):
        key = string(key,160,required=True)
        row = db.execute("SELECT data FROM work_api_operations WHERE id=?",(key,)).fetchone()
        if not row:
            invalid("API를 찾을 수 없습니다.", "api_not_found")
        return json.loads(row[0])

    @staticmethod
    def _allowed(op, groups):
        return not op["group_ids"] or bool(set(op["group_ids"]).intersection(groups))

    def resolve(self, db, api_id, version=None, *, groups, for_new=False, evidence=False):
        current = self._get(db, api_id)
        if not self._allowed(current, groups):
            invalid("이 API를 사용할 권한이 없습니다.", "api_forbidden")
        if not evidence and (current["state"] == "withdrawn" or for_new and current["state"] != "active"):
            invalid("현재 연결할 수 없는 API입니다.", "api_unavailable")
        if version is None:
            return current
        if type(version) is not int or version < 1 or (for_new and version != current["version"]):
            invalid("API 버전을 다시 확인하세요.", "api_version_changed")
        row = db.execute("SELECT data FROM work_api_versions WHERE api_id=? AND version=?", (api_id,version)).fetchone()
        if not row:
            invalid("해당 버전의 API 명세를 찾을 수 없습니다.", "api_version_changed")
        return json.loads(row[0])

    async def state(self, user):
        _, caps, groups = await self.service._work_actor(user)
        admin = caps["is_admin"]
        with self.service._db() as db:
            apis = [dict(op, can_use=self._allowed(op,groups)) for op in self._all(db) if admin or self._allowed(op,groups)]
            visible_services = {a["service_id"] for a in apis}
            services = [dict(s) for s in db.execute("SELECT id,name,revision FROM work_api_services ORDER BY name COLLATE NOCASE,id")
                        if admin or s["id"] in visible_services]
        result = {"services":services,"apis":apis,"can_manage":admin}
        request_url = os.environ.get("EES_WORK_API_REQUEST_URL","")
        if request_url:
            try:
                result["development_url"] = http_url(request_url,query=True)
            except WorkflowError:
                pass
        return result

    @staticmethod
    def _service(db, key):
        row = db.execute("SELECT id,name,revision FROM work_api_services WHERE id=?",(string(key,160,required=True),)).fetchone()
        if not row:
            invalid("등록할 서비스를 확인하세요.", "api_service_not_found")
        return dict(row)

    def _destination(self, db, key, name="", *, create=False):
        if key:
            return self._service(db,key)["id"]
        if not name:
            return ""
        name = string(name,180,required=True)
        row = db.execute("SELECT id FROM work_api_services WHERE name=? COLLATE NOCASE",(name,)).fetchone()
        if row:
            return row[0]
        if not create:
            return ""
        key = "svc-"+uuid4().hex
        db.execute("INSERT INTO work_api_services VALUES(?,?,1)",(key,name))
        return key

    def _service_command(self, db, body):
        runtime = self.service.operations
        if body["action"] == "api_service_delete":
            rec = self._service(db,body.get("service_id"))
            runtime._revision(body,rec["revision"])
            if db.execute("SELECT 1 FROM work_api_operations WHERE service_id=?",(rec["id"],)).fetchone():
                invalid("서비스에 등록된 API를 먼저 이동하세요.", "api_service_in_use")
            db.execute("DELETE FROM work_api_services WHERE id=?",(rec["id"],))
            return {"ok":True,"service":rec}
        service = body.get("service")
        if not isinstance(service, dict):
            invalid("서비스 이름을 입력하세요.")
        name = string(service.get("name"),180,required=True)
        key = service.get("id")
        old = self._service(db,key) if key else None
        revision = old["revision"] if old else 0
        runtime._revision(body,revision)
        key = key or "svc-"+uuid4().hex
        try:
            db.execute("INSERT INTO work_api_services VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,revision=excluded.revision",(key,name,revision+1))
        except sqlite3.IntegrityError:
            invalid("같은 이름의 서비스가 있습니다.", "api_service_duplicate")
        return {"ok":True,"service":self._service(db,key)}

    def _persist(self, db, actor, old, data):
        if old and all(old.get(k) == data.get(k) for k in (*CORE,*ORIGIN)):
            return old
        version = old["version"]+1 if old else 1
        record = dict(data,id=old["id"] if old else "api-"+uuid4().hex,version=version,revision=version)
        encoded = dump(record)
        try:
            db.execute("INSERT INTO work_api_operations VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,service_id=excluded.service_id,method=excluded.method,url=excluded.url,data=excluded.data",
                       (record["id"],version,data["service_id"],data["method"],data["url"],encoded))
        except sqlite3.IntegrityError:
            invalid("같은 서비스에 이 주소와 요청 방식이 이미 등록되어 있습니다.", "api_duplicate")
        db.execute("INSERT INTO work_api_versions VALUES(?,?,?)",(record["id"],version,encoded))
        self.service.operations._event(db,record["id"],actor,"api_save",{"version":version})
        return record

    def _preview(self, db, actor, groups, old, data, key):
        from .ees_workflow_api_binding import api_uses
        delta = changes(old,data)
        mode = "new" if not old else "removed" if old["state"]!="withdrawn" and data["state"]=="withdrawn" else "changed" if delta else "same"
        uses = api_uses(self.service,db,actor,groups,old["id"]) if old and delta else []
        return {**data,**({"id":old["id"],"version":old["version"]} if old else {}),"key":key,"expected_revision":old["revision"] if old else 0,
                "mode":mode,"changes":delta,"uses":uses}

    def _direct(self, db, actor, groups, body, preview):
        raw = body.get("api")
        if not isinstance(raw, dict):
            invalid("등록할 API를 입력하세요.")
        old = self._get(db,raw["id"]) if raw.get("id") else None
        service_id = self._destination(db, raw.get("service_id", (old or {}).get("service_id")), body.get("service_name",""),create=not preview)
        data = normalize(raw, service_id, old)
        if old:
            data.update({k: old[k] for k in ORIGIN if k in old})
        if preview:
            return {"ok":True,"operation":self._preview(db,actor,groups,old,data,data["method"]+" "+data["url"])}
        self.service.operations._revision(body,old["revision"] if old else 0)
        record = self._persist(db,actor,old,data)
        if old and old["version"] != record["version"]:
            self._repair(db,actor,groups,old,record,body.get("repairs", []))
        return {"ok":True,"api":record}

    @staticmethod
    def _source_id(op):
        return op.get("source_url") or op.get("source_name")

    def _candidates(self, db, actor, groups, parsed, source_url, service_id):
        prior = [op for op in self._all(db) if op["service_id"]==service_id]
        identity = source_url or parsed["service_name"]
        owned = [op for op in prior if self._source_id(op)==identity]
        rows, present = [], set()
        for item in parsed["operations"]:
            key = item["key"]
            by_id = [op for op in owned if item.get("operation_key") and op.get("operation_key")==item["operation_key"]]
            by_path = [op for op in owned if op.get("source_path")==item["source_path"] and op["method"]==item["method"]]
            match = {op["id"]:op for op in by_id+by_path}
            present.update(match)
            if item.get("error") or len(match)>1:
                rows.append(dict(item,mode="blocked",error=item.get("error") or "기존 기능의 경로와 식별자가 충돌합니다."))
                continue
            old = next(iter(match.values()),None)
            if not old:
                old = next((op for op in prior if op["url"]==item["url"] and op["method"]==item["method"]),None)
            if old and self._source_id(old) not in (None, identity):
                rows.append(dict(item,mode="blocked",error="다른 원본의 API와 주소가 겹칩니다."))
                continue
            try:
                data = normalize(item,service_id,old)
                data.update(source_url=source_url,source_name=parsed["service_name"],source_version=parsed["service_version"],
                            source_path=item["source_path"],operation_key=item["operation_key"],provider_name=data["name"],provider_purpose=data["purpose"])
                if old:
                    present.add(old["id"])
                    for k in ("name","purpose"):
                        if old.get("provider_"+k) and old[k]!=old["provider_"+k]:
                            data[k]=old[k]
                rows.append(self._preview(db,actor,groups,old,data,key))
            except WorkflowError as exc:
                rows.append(dict(item,mode="blocked",error=exc.message))
        for op in owned:
            if op["id"] not in present and op["state"]!="withdrawn":
                data = {k:op[k] for k in (*CORE,*ORIGIN) if k in op}
                data.update(state="withdrawn",source_version=parsed["service_version"])
                rows.append(self._preview(db,actor,groups,op,data,"removed:"+op["id"]))
        return rows

    def _repair(self, db, actor, groups, old, new, repairs):
        if new["state"] != "withdrawn":
            from .ees_workflow_api_binding import apply_api_repairs
            apply_api_repairs(self.service,db,actor,groups,old,new,repairs)

    def _import(self, db, actor, groups, body, parsed, url, preview):
        service_id = self._destination(db, body.get("service_id"), body.get("service_name") or parsed["service_name"],create=not preview)
        rows = self._candidates(db,actor,groups,parsed,url,service_id)
        if preview:
            return {**parsed,"ok":True,"operations":rows}
        if body.get("document_hash") != parsed["document_hash"] and (url or "document_hash" in body):
            invalid("서비스 명세가 바뀌었습니다. 다시 확인하세요.","api_import_changed")
        selections = list_of(body.get("selections"),1000)
        if not selections:
            invalid("등록할 기능을 선택하세요.")
        chosen = set()
        lookup = {row["key"]:row for row in rows}
        result = []
        # Validate the selection before persisting any operation.
        for sel in selections:
            if not isinstance(sel,dict) or not isinstance(sel.get("key"),str) or sel["key"] in chosen:
                invalid("중복되지 않는 기능을 선택하세요.")
            row = lookup.get(sel["key"])
            if not row or row.get("error") or row["mode"]=="blocked":
                invalid("선택한 기능 또는 원본이 변경되었습니다.","api_import_changed")
            self.service.operations._revision(sel,row["expected_revision"])
            chosen.add(sel["key"])
        repairs = list_of(body.get("repairs", []))
        revision_cursors = {}
        selected_ids = {lookup[sel["key"]].get("id") for sel in selections}
        for repair in repairs:
            if (not isinstance(repair, dict) or not isinstance(repair.get("workflow_id"), str)
                    or "api_id" in repair and not isinstance(repair["api_id"], str)):
                invalid("다시 연결할 작업을 확인하세요.")
            if ((len(selections) > 1 and not repair.get("api_id"))
                    or (repair.get("api_id") and repair["api_id"] not in selected_ids)):
                invalid("재연결할 API를 선택하세요.")
            workflow = self.service._work_definition(db, actor, groups, repair["workflow_id"], True)
            self.service.operations._revision(repair, workflow["revision"])
            revision_cursors[repair["workflow_id"]] = workflow["revision"]
        for sel in selections:
            row = lookup[sel["key"]]
            old = self._get(db,row["id"]) if row.get("id") else None
            data = {k:row[k] for k in (*CORE,*ORIGIN) if k in row}
            record = self._persist(db,actor,old,data)
            if old and old["version"]!=record["version"]:
                selected = [dict(r, expected_revision=revision_cursors[r["workflow_id"]])
                            for r in repairs if r.get("api_id", record["id"]) == record["id"]]
                self._repair(db,actor,groups,old,record,selected)
                for repair in selected:
                    workflow = self.service._work_definition(db, actor, groups, repair["workflow_id"], True)
                    revision_cursors[repair["workflow_id"]] = workflow["revision"]
            result.append(record)
        return {"ok":True,"apis":result}

    async def command(self, user, body):
        actor, caps, groups = await self.service._work_actor(user)
        action = body.get("action")
        if action == "api_detail":
            from .ees_workflow_api_binding import api_uses
            with self.service._db() as db:
                item = self._get(db,body.get("api_id"))
                allowed = self._allowed(item,groups)
                if not allowed and not caps["is_admin"]:
                    invalid("이 API를 볼 권한이 없습니다.","api_forbidden")
                return {"ok":True,"api":dict(item,can_use=allowed),"uses":api_uses(self.service,db,actor,groups,item["id"])}
        if not caps["is_admin"]:
            invalid("관리자만 API 명세를 관리할 수 있습니다.","admin_required")
        actions = {"api_service_save","api_service_delete","api_save","api_change_preview","api_import_preview","api_import_apply"}
        if action not in actions:
            invalid("지원하지 않는 API 명세 작업입니다.")
        preview = action.endswith("_preview")
        runtime = self.service.operations
        if not preview:
            with self.service._db() as db:
                cached = runtime._receipt(db,actor,body)
                if cached is not None:
                    return cached
        if action in ("api_save", "api_change_preview") and isinstance(body.get("api"), dict) and body["api"].get("group_ids"):
            known = {g["id"] for g in await self.service._native_groups()}
            if any(not isinstance(group, str) or group not in known for group in list_of(body["api"]["group_ids"])):
                invalid("현재 존재하는 Native 사용자 그룹을 선택하세요.", "api_groups_invalid")
            actor, caps, groups = await self.service._work_actor(user)
            if not caps["is_admin"]:
                invalid("API 등록 권한이 변경됐습니다.","admin_required")
        parsed = None
        url = ""
        if action.startswith("api_import_"):
            if body.get("source_url") and body.get("source_text"):
                invalid("서비스 명세 URL과 붙여넣은 문서 중 하나를 선택하세요.")
            if body.get("source_url"):
                url = http_url(body["source_url"])
            if body.get("source_text") is not None and body.get("source_text") != "":
                source = body["source_text"]
            elif url:
                from .ees_workflow_api_http import fetch_spec
                source = await fetch_spec(url,body.get("service_id"),actor)
            else:
                invalid("명세 URL 또는 명세 문서가 필요합니다.")
            parsed = parse_document(source,url)
            actor,caps,groups = await self.service._work_actor(user)
            if not caps["is_admin"]:
                invalid("API 등록 권한이 변경됐습니다.","admin_required")
        with self.service._db(write=not preview) as db:
            if not preview:
                cached = runtime._receipt(db,actor,body)
                if cached is not None:
                    return cached
            if action in ("api_service_save","api_service_delete"):
                result = self._service_command(db,body)
            elif parsed is not None:
                result = self._import(db,actor,groups,body,parsed,url,preview)
            else:
                result = self._direct(db,actor,groups,body,preview)
            return result if preview else runtime._remember(db,actor,body,result)
