"""Real workflow SQLite tests for service APIs, versioned imports and permissions."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import ModuleType
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("ees_api_catalog_tests")
package.__path__ = [str(ROOT / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[package.__name__] = package
workflow = importlib.import_module(package.__name__+".ees_workflow")
compiler = importlib.import_module(package.__name__+".ees_workflow_api_openapi")


def alarms():
    return {"openapi":"3.1.0","info":{"title":"EMS","version":"1.0"},
            "servers":[{"url":"https://ems.example/api"}],
            "paths":{"/equipment/{id}/alarms":{"parameters":[{"$ref":"#/components/parameters/Equipment"}],
                     "get":{"operationId":"alarmList","summary":"알람 조회","responses":{"200":{"content":{"application/json":{
                            "schema":{"type":"array","items":{"$ref":"#/components/schemas/Alarm"}},"example":[{"code":"F01"}]}}}}},
                     "post":{"summary":"알람 등록","requestBody":{"required":True,"content":{"application/json":{"schema":{
                             "type":"object","required":["code"],"properties":{"code":{"type":"string","title":"알람 코드"}}}}}},
                             "responses":{"202":{"content":{"application/json":{"schema":{"type":"object","properties":{"receipt":{"type":"string"}}}}}}}}}},
            "components":{"parameters":{"Equipment":{"in":"path","name":"id","required":True,"schema":{"type":"string"}}},
                          "schemas":{"Alarm":{"type":"object","properties":{"code":{"type":"string","title":"알람 코드"}}}}}}


class CatalogTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.users = {k:{"id":k,"role":"admin" if k=="admin" else "user"} for k in ("admin","karin","kim")}
        self.groups={"karin":[{"id":"operations"}]}
        self.db=Path(tmp.name)/"work.sqlite"
        self.service=self.new_service()
        self.catalog=self.service.api_catalog
        self.api={"name":"백업 조회","purpose":"성공 여부를 확인합니다.","method":"GET","url":"https://backup.example/jobs",
                  "inputs":[],"result_path":"items","fields":[{"path":"id","type":"string","label":"작업"}],"example":{"items":[{"id":"bk1"}]}}
        self.req=0

    def new_service(self):
        return workflow.WorkflowService(self.db,self.users.get,lambda _:None,group_lookup=lambda uid:self.groups.get(uid,[]),group_list_lookup=lambda:[{"id":"operations"}])

    def body(self, action, **fields):
        self.req+=1
        return {"action":action,"request_id":"api-test-"+str(self.req),"expected_revision":0,**fields}

    async def call(self, action, actor="admin", **fields):
        return await self.catalog.command(self.users[actor],self.body(action,**fields))

    async def assert_error(self, code, future):
        with self.assertRaises(workflow.WorkflowError) as err:
            await future
        self.assertEqual(code,err.exception.code)

    async def test_register_edit_restart_immutable_versions_and_service_rename(self):
        registered=await self.call("api_save",api=self.api,service_name="사내 백업")
        op=registered["api"]
        rows=await self.catalog.state(self.users["admin"])
        self.assertEqual(rows["services"],[{"name":"사내 백업","revision":1,"id":op["service_id"]}])
        updated=(await self.call("api_save",api={**op,"purpose":"변경한 용도"},expected_revision=1))["api"]
        await self.call("api_service_save",service={"id":op["service_id"],"name":"백업 플랫폼"},expected_revision=1)
        other=self.new_service()
        catalog=other.api_catalog
        with other._db() as db:
            self.assertEqual(catalog.resolve(db,op["id"],1,groups=set())["purpose"],self.api["purpose"])
            self.assertEqual(catalog.resolve(db,op["id"],2,groups=set())["purpose"],"변경한 용도")
        with self.assertRaises(sqlite3.IntegrityError),other._db(write=True) as db:
            db.execute("UPDATE work_api_versions SET data='{}' WHERE version=1")
        state=await catalog.state(self.users["karin"])
        self.assertEqual((state["services"][0]["name"],state["apis"][0]["id"],updated["revision"]),("백업 플랫폼",op["id"],2))
        await self.assert_error("api_service_in_use",self.call("api_service_delete",service_id=op["service_id"],expected_revision=2))
        empty=(await self.call("api_service_save",service={"name":"프로젝트"}))["service"]
        await self.call("api_service_delete",service_id=empty["id"],expected_revision=1)
        self.assertFalse(any(s["id"]==empty["id"] for s in (await self.catalog.state(self.users["admin"]))["services"]))

    async def test_idempotency_conflict_and_rejected_implicit_service_rollback(self):
        body=self.body("api_save",api=self.api,service_name="기본")
        first=await self.catalog.command(self.users["admin"],body)
        self.assertEqual(first,await self.catalog.command(self.users["admin"],deepcopy(body)))
        await self.assert_error("request_conflict",self.catalog.command(self.users["admin"],{**body,"api":{**self.api,"name":"다른 요청"}}))
        await self.assert_error("revision_conflict",self.call("api_save",api={**first["api"],"name":"늦은 저장"}))
        await self.assert_error("api_duplicate",self.call("api_save",api={**self.api,"service_id":first["api"]["service_id"]}))
        await self.assert_error("api_invalid",self.call("api_save",api={**self.api,"url":"https://a:b@invalid.example/"},service_name="취소"))
        self.assertEqual([s["name"] for s in (await self.catalog.state(self.users["admin"]))["services"]],["기본"])

    async def test_detail_and_query_template_keep_original_address(self):
        raw = dict(self.api, url="https://backup.example/jobs?system=EMS&range={period}", inputs=[
            {"name":"range","wire_name":"range","in":"query","type":"string","required":True,"label":"기간"}])
        api = (await self.call("api_save",api=raw))["api"]
        detail = await self.catalog.command(self.users["karin"],{"action":"api_detail","api_id":api["id"]})
        self.assertEqual((detail["api"]["url"],detail["uses"]),(raw["url"],[]))
        await self.assert_error("api_groups_invalid",self.call("api_save",api=dict(api,group_ids=["missing"]),expected_revision=1))
        await self.assert_error("api_invalid",self.call("api_save",api=dict(raw,inputs=[])))

    async def test_revoked_authorizations_and_old_versions(self):
        op=(await self.call("api_save",api={**self.api,"group_ids":["operations"]},service_name="운영 전용"))["api"]
        self.assertTrue((await self.catalog.state(self.users["karin"]))["apis"][0]["can_use"])
        self.assertFalse((await self.catalog.state(self.users["admin"]))["apis"][0]["can_use"])
        other=await self.catalog.state(self.users["kim"])
        self.assertFalse(other["can_manage"])
        self.assertEqual((other["services"],other["apis"]),([],[]))
        self.groups.clear()
        with self.assertRaises(workflow.WorkflowError),self.service._db() as db:
            self.catalog.resolve(db,op["id"],1,groups=[])
        for action in ("api_service_save","api_save","api_change_preview","api_import_preview","api_import_apply"):
            await self.assert_error("admin_required",self.call(action,actor="kim"))
        await self.call("api_save",api={**op,"state":"deprecated"},expected_revision=1)
        with self.service._db() as db:
            self.assertEqual(self.catalog.resolve(db,op["id"],1,groups=["operations"])["version"],1)
            with self.assertRaises(workflow.WorkflowError):
                self.catalog.resolve(db,op["id"],1,groups=["operations"],for_new=True)
        await self.call("api_save",api={**op,"state":"withdrawn"},expected_revision=2)
        with self.service._db() as db:
            with self.assertRaises(workflow.WorkflowError):
                self.catalog.resolve(db,op["id"],1,groups=["operations"])
            self.assertEqual(self.catalog.resolve(db,op["id"],1,groups=["operations"],evidence=True)["example"],op["example"])

    async def test_selective_import_change_impact_removal_replay_and_rename(self):
        doc=alarms()
        source=json.dumps(doc)
        preview=await self.call("api_import_preview",source_text=source)
        self.assertEqual([x["mode"] for x in preview["operations"]],["new","new"])
        row=preview["operations"][0]
        self.assertEqual([row["inputs"][0]["wire_name"],row["fields"][0]["path"]],["id","code"])
        def sel(record):
            return {"key":record["key"],"expected_revision":record["expected_revision"]}
        saved=(await self.call("api_import_apply",source_text=source,service_name="EMS",selections=[sel(row)]))["apis"][0]
        saved=(await self.call("api_save",api={**saved,"name":"우리 팀 알람 조회"},expected_revision=1))["api"]
        del doc["components"]["schemas"]["Alarm"]["properties"]["code"]
        doc["components"]["schemas"]["Alarm"]["properties"]["alarmCode"]={"type":"string"}
        doc["info"]["version"]="2.0"
        args={"source_text":json.dumps(doc),"service_id":saved["service_id"]}
        changed=(await self.call("api_import_preview",**args))["operations"][0]
        self.assertEqual(changed["name"],"우리 팀 알람 조회")
        self.assertTrue(any(x["path"]=="code" and x["change"]=="removed" for x in changed["changes"]))
        body=self.body("api_import_apply",selections=[sel(changed)],**args)
        upgraded=(await self.catalog.command(self.users["admin"],body))["apis"][0]
        self.assertEqual((upgraded["id"],upgraded["version"]),(saved["id"],3))
        self.assertEqual((await self.catalog.command(self.users["admin"],body))["apis"][0],upgraded)
        self.assertEqual((await self.call("api_import_preview",**args))["operations"][0]["mode"],"same")
        del doc["paths"]["/equipment/{id}/alarms"]["get"]
        args["source_text"]=json.dumps(doc)
        gone=next(x for x in (await self.call("api_import_preview",**args))["operations"] if x["mode"]=="removed")
        retired=(await self.call("api_import_apply",selections=[sel(gone)],**args))["apis"][0]
        self.assertEqual(retired["state"],"withdrawn")
        with self.service._db() as db:
            self.assertEqual(self.catalog.resolve(db,saved["id"],1,groups=[],evidence=True)["fields"][0]["path"],"code")

    async def test_field_change_repairs_editable_draft_atomically_preserving_publication(self):
        source = json.dumps(alarms())
        preview = await self.call("api_import_preview",source_text=source)
        selection = {"key":preview["operations"][0]["key"],"expected_revision":0}
        op = (await self.call("api_import_apply",source_text=source,selections=[selection]))["apis"][0]
        async def workspace(action, **fields):
            return await self.service.workspace_command(self.users["admin"],self.body(action,**fields))
        created = await workspace("create_workflow",name="알람 점검",system_id="EMS")
        workflow_id = created["workflow_id"]
        definition = created["workflow"]["draft"]
        nodes = definition["nodes"]
        root = next(iter(nodes))
        nodes[root]["children"] = ["stage"]
        nodes["stage"] = {"id":"stage","name":"확인","type":"t","parent":root,"children":["job"],"deps":[]}
        nodes["job"] = {"id":"job","name":"알람 조회","type":"j","parent":"stage","children":[],"deps":[],
                        "mode":"tool","human_confirmation":True,"result_block":"human_confirm",
                        "api_binding":{"operation_id":op["id"],"version":1,"inputs":{"id":{"constant":"A1"}},"outputs":["code"]}}
        self.assertTrue((await workspace("save_draft",workflow_id=workflow_id,expected_revision=1,definition=definition))["ok"])
        self.assertTrue((await workspace("publish_workflow",workflow_id=workflow_id,expected_revision=2))["ok"])
        doc = alarms()
        fields = doc["components"]["schemas"]["Alarm"]["properties"]
        fields["alarmCode"] = fields.pop("code")
        updated = json.dumps(doc)
        preview = await self.call("api_import_preview",source_text=updated)
        operation = preview["operations"][0]
        self.assertEqual({u["kind"] for u in operation["uses"]},{"draft","published"})
        use = next(u for u in operation["uses"] if u["kind"] == "draft")
        kwargs = {"source_text":updated,"selections":[{"key":operation["key"],"expected_revision":1}]}
        await self.assert_error("api_repairs_required",self.call("api_import_apply",**kwargs))
        repair = {"workflow_id":workflow_id,"expected_revision":use["revision"]-1,"fields":{"code":"alarmCode"}}
        await self.assert_error("revision_conflict",self.call("api_import_apply",**kwargs,repairs=[repair]))
        with self.service._db() as db:
            self.assertEqual(self.catalog.resolve(db,op["id"],groups=[])["version"],1)
        repair["expected_revision"]=use["revision"]
        self.assertEqual((await self.call("api_import_apply",**kwargs,repairs=[repair]))["apis"][0]["version"],2)
        with self.service._db() as db:
            draft = db.execute("SELECT draft FROM work_definitions WHERE id=?",(workflow_id,)).fetchone()[0]
            published = db.execute("SELECT definition FROM work_versions WHERE workflow_id=?",(workflow_id,)).fetchone()[0]
        self.assertEqual(json.loads(draft)["nodes"]["job"]["api_binding"]["outputs"],["alarmCode"])
        self.assertEqual(json.loads(published)["nodes"]["job"]["api_binding"]["outputs"],["code"])

    async def test_url_import_document_hash_checks_and_refreshes_admin(self):
        address="https://ems.example/api/openapi.json"
        original=json.dumps(alarms())
        with patch(package.__name__+".ees_workflow_api_http.fetch_spec",new=AsyncMock(return_value=original)) as fetch:
            preview=await self.call("api_import_preview",source_url=address)
            fetch.assert_awaited_once_with(address,None,self.users["admin"])
            fields={"source_url":address,"selections":[{"key":preview["operations"][0]["key"],"expected_revision":0}],
                    "service_name":"EMS","document_hash":preview["document_hash"]}
            fetch.return_value=original+" "
            await self.assert_error("api_import_changed",self.call("api_import_apply",**fields))
            self.assertEqual((await self.catalog.state(self.users["admin"]))["apis"],[])
            async def revoke(*_):
                self.users["admin"]["role"]="user"
                return original
            fetch.side_effect=revoke
            await self.assert_error("admin_required",self.call("api_import_apply",**fields))

    async def test_direct_preview_has_no_side_effects_and_unsupported_input_is_rejected(self):
        result=await self.call("api_change_preview",api=self.api,service_name="백업")
        self.assertEqual(result["operation"]["mode"],"new")
        self.assertEqual((await self.catalog.state(self.users["admin"]))["services"],[])
        bad=[
            {"url":"http://server/jobs?token=abcd"},
            {"inputs":[{"name":"Host","in":"header"}]},
            {"inputs":[{"name":"Authorization","in":"header"}]},
            {"inputs":[{"name":"id","in":"path"}]},
            {"url":"http://server/{id}","inputs":[]},
            {"example":{"nested":{"api_key":"should never persist"}}},
            {"fields":[{"path":"foo","type":"date"}]},
        ]
        for change in bad:
            with self.subTest(change=change):
                await self.assert_error("api_invalid",self.call("api_save",api={**self.api,**change}))
        self.assertEqual((await self.catalog.state(self.users["admin"]))["apis"],[])


class ApiAssistantReferenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_help_keeps_the_offer_id_and_rejects_scope_or_permission_changes(self):
        from fastapi import HTTPException
        from types import SimpleNamespace
        native = importlib.import_module(package.__name__ + ".ees_workflow_native")
        reference = {"kind":"help", "term_id":"api_specification", "system_id":"EMS",
                     "context_id":"editor-1", "api_draft_request":"offer-1", "screen":"API 명세 등록"}
        meta = {"chat_id":"chat-1", "user_message":{"id":"question","content":"용도 설명 제안",
                "meta":{"ees_work_help":1,"ees_work_reference":reference}}}
        form = {"model":"fixture-model"}
        request = SimpleNamespace(state=SimpleNamespace())
        with patch.object(native,"_help_access",AsyncMock(return_value=("owner","current"))):
            self.assertTrue(await native.prepare_chat_work_help(request,{},meta,form))
            self.assertEqual(meta["ees_work_reference"]["api_draft_request"],"offer-1")
            self.assertEqual(form["tool_ids"],["ees_workflow"])
            meta["ees_work_reference"]["api_draft_request"]="different-offer"
            with self.assertRaises(HTTPException) as stale:
                await native.enforce_chat_work_help(request,{},meta,form)
            self.assertEqual(stale.exception.detail["reason"],"work_chat_context_changed")
        meta["ees_work_reference"]["api_draft_request"]="offer-1"
        with patch.object(native,"_help_access",AsyncMock(side_effect=native.WorkflowError(
                "work_chat_forbidden","편집 권한이 변경되었습니다."))):
            with self.assertRaises(HTTPException) as forbidden:
                await native.enforce_chat_work_help(request,{},meta,form)
            self.assertEqual(forbidden.exception.detail["reason"],"work_chat_forbidden")
        for bad in (dict(reference,term_id="read_tool"),dict(reference,api_draft_request="x"*41)):
            with self.subTest(reference=bad), self.assertRaises(native.WorkflowError):
                native._help_reference(bad)


class CompilerTest(unittest.TestCase):
    def test_yaml_and_local_refs_standalone_errors(self):
        import yaml
        doc=alarms()
        doc["paths"]["/bad"]={"get":{"responses":{"200":{"$ref":"https://other.example/response"}}}}
        doc["paths"]["/badDuplicate"]={"get":{"operationId":"bad","responses":{"204":{"description":"ok"}}},
                                      "delete":{"operationId":"bad","responses":{"204":{"description":"ok"}}}}
        rows=compiler.parse_document(yaml.safe_dump(doc,allow_unicode=True,sort_keys=False))["operations"]
        self.assertEqual(rows[1]["inputs"][1]["name"],"code")
        self.assertFalse(rows[0].get("error"))
        self.assertTrue(all(r.get("error") for r in rows[2:]))

    def test_parameter_override_and_location_name_collision(self):
        doc=alarms()
        doc["paths"]["/equipment/{id}/alarms"]["get"]["parameters"]=[
            {"in":"query","name":"id","schema":{"type":"string"}}, {"in":"path","name":"id","required":True,"schema":{"type":"integer"}}]
        result=compiler.parse_document(json.dumps(doc))["operations"][0]
        self.assertEqual([(f["name"],f["wire_name"],f["type"]) for f in result["inputs"]],[("path_id","id","integer"),("query_id","id","string")])

    def test_whole_json_body_and_scalar_result(self):
        doc=alarms()
        create = doc["paths"]["/equipment/{id}/alarms"]["post"]
        create["requestBody"]["content"]["application/json"]["schema"] = {"type":"array","items":{"type":"string"}}
        create["responses"]["202"]["content"]["application/json"]["schema"] = {"type":"string"}
        result=compiler.parse_document(json.dumps(doc))["operations"][1]
        self.assertTrue(result["inputs"][-1]["whole_body"])
        self.assertEqual(result["inputs"][-1]["type"],"array")
        self.assertEqual(result["fields"],[{"path":"$","label":"결과","root_value":True,"type":"string"}])

    def test_source_relative_server_and_envelope_result_paths(self):
        doc=alarms()
        doc["servers"]=[{"url":"/rest"}]
        doc["paths"]["/equipment/{id}/alarms"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]={
            "type":"object","properties":{"rows":{"type":"array","items":{"$ref":"#/components/schemas/Alarm"}}}}
        result=compiler.parse_document(json.dumps(doc),"https://ems.example/spec/openapi.json")["operations"][0]
        self.assertEqual((result["result_path"],result["url"]),("rows","https://ems.example/rest/equipment/{id}/alarms"))


if __name__=="__main__":
    unittest.main()
