"""Real contract/authoring code, synthetic approved references and SQLite only."""
from copy import deepcopy
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest
from test_ees_work_authoring import AuthoringFixture
from workflow_fixture import legacy_definition

PACKAGE = ModuleType("ees_contract_test_subject")
PACKAGE.__path__ = [str(Path(__file__).resolve().parents[1] / "agent-pack/skills/ees-work-demo/scripts")]
sys.modules[PACKAGE.__name__] = PACKAGE
contract = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_contract")
examples = __import__("workflow_fixture").load_workflow_examples(PACKAGE.__name__)
definition = importlib.import_module(PACKAGE.__name__ + ".ees_workflow_definition")


def refs():
    return {name: {"tool_id": "confluence-existing" if name in ("search_pages", "get_page") else name + "-existing",
                   "function": name, "revision": 1, "content_hash": "a" * 64, "schema_hash": "b" * 64,
                   "config_hash": "c" * 64, "environment": "synthetic-test"}
            for name in ("jira_dashboard", "github_list_pull_requests", "search_pages", "get_page")}


def catalog(workflow):
    value = legacy_definition()
    value["nodes"].update(deepcopy(workflow["nodes"]))
    root = workflow["nodes"][workflow["process_id"]]
    value["roots"][root["category"]].append(root["id"])
    return value


def envelope(data, completeness="complete"):
    return {"status": "succeeded", "completeness": completeness, "data": data,
            "evidence": [{"kind": "test", "id": "1"}], "provenance": {"environment": "synthetic-test"}}


class ContractTests(unittest.TestCase):
    def test_two_reusable_workflows_validate_and_do_not_mutate_seed(self):
        before = definition._seed()
        for wf in (examples.operations_workflow(refs(), "synthetic-model"), examples.installation_docs_workflow(refs())):
            self.assertEqual(definition.validate_definition(catalog(wf)), [])
            self.assertEqual(wf["tools"], {})
            self.assertEqual(wf["skills"], {})
        self.assertEqual(before, definition._seed())
        self.assertFalse(any("execution" in node for node in before["nodes"].values()))

    def test_typed_inputs_enforce_boolean_integer_object_and_identifier_boundaries(self):
        schema = {"type": "object", "additionalProperties": False, "required": ["page_id", "count"], "properties": {
            "page_id": {"type": "string", "maxLength": 30, "format": "page_id"},
            "repo": {"type": "string", "maxLength": 201, "format": "repository"},
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
            "filters": {"type": "array", "maxItems": 2, "items": {"type": "object", "additionalProperties": False,
                        "properties": {"active": {"type": "boolean"}}, "required": ["active"]}}}}
        valid = {"page_id": "123", "count": 3, "repo": "team/project", "filters": [{"active": True}]}
        self.assertEqual(contract.validate_inputs(schema, valid, False), [])
        for patch in ({"count": True}, {"count": 6}, {"page_id": "http://untrusted/1"}, {"repo": "../a/b"},
                      {"role": "admin"}, {"filters": [{"active": "true"}]}, {"filters": [{"active": True, "headers": {}}]}):
            self.assertTrue(contract.validate_inputs(schema, {**valid, **patch}), patch)
        self.assertEqual(contract.validate_inputs(schema, {}, True), [])
        self.assertTrue(contract.validate_inputs(schema, {}, False))

    def test_arbitrary_schema_code_and_reserved_arguments_rejected(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        node = wf["nodes"]["new-operations-jira-j"]
        for key, value in (("__user__", {"source": "constant", "value": {"role": "admin"}}),
                           ("headers", {"source": "constant", "value": "x"}),
                           ("project_key", {"source": "eval", "value": "open('/secret')"})):
            changed = deepcopy(node)
            changed["execution"]["calls"][0]["arguments"][key] = value
            self.assertTrue(contract.validate_execution(changed, catalog(wf)))
        changed = deepcopy(node)
        changed["execution"]["calls"][0]["reference"]["function"] = "_private"
        self.assertTrue(contract.validate_execution(changed, catalog(wf)))
        self.assertTrue(contract.schema_errors({"type": "string", "maxLength": 30, "pattern": "(a+)+$"}))

    def test_result_links_require_declared_preceding_job(self):
        wf = examples.installation_docs_workflow(refs())
        node = wf["nodes"]["new-documents-page-j"]
        node["deps"] = []
        self.assertTrue(contract.validate_execution(node, catalog(wf)))
        node["deps"] = ["new-documents-search-j"]
        self.assertEqual(contract.validate_execution(node, catalog(wf)), [])

    def test_bindings_use_stored_results_and_only_explicit_transform(self):
        stored = {"j1": {"read": envelope({"page_id": "12", "count": 3})}}
        call = {"arguments": {"page_id": {"source": "result", "job_id": "j1", "call_id": "read", "path": ["data", "page_id"]},
                               "count": {"source": "input", "key": "number", "transform": "to_integer"}}}
        self.assertEqual(contract.resolve_arguments(call, {"number": "5"}, stored), {"page_id": "12", "count": 5})
        for mutation in ("missing", "__class__"):
            broken = deepcopy(call)
            broken["arguments"]["page_id"]["path"] = ["data", mutation]
            with self.assertRaises(contract.ContractError):
                contract.resolve_arguments(broken, {"number": "5"}, stored)
        stored["j1"]["read"]["status"] = "unknown"
        with self.assertRaises(contract.ContractError):
            contract.resolve_arguments(call, {"number": "5"}, stored)

    def test_multiple_candidates_wait_and_only_actual_selection_resumes(self):
        wf = examples.installation_docs_workflow(refs())
        call = wf["nodes"]["new-documents-page-j"]["execution"]["calls"][0]
        stored = {"new-documents-search-j": {"search": envelope({"results": [{"page_id": "12"}, {"page_id": "13"}]}, "partial")}}
        with self.assertRaises(contract.ContractError) as caught:
            contract.resolve_arguments(call, {}, stored)
        self.assertEqual(caught.exception.code, "input_required")
        self.assertEqual(contract.resolve_arguments(call, {"page_id": "13"}, stored), {"page_id": "13"})
        with self.assertRaises(contract.ContractError) as caught:
            contract.resolve_arguments(call, {"page_id": "99"}, stored)
        self.assertEqual(caught.exception.code, "invalid_selection")
        stored["new-documents-search-j"]["search"]["data"]["results"].pop()
        self.assertEqual(contract.resolve_arguments(call, {}, stored), {"page_id": "12"})

    def test_transport_success_is_distinct_from_business_and_final_completion(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        node = wf["nodes"]["new-operations-jira-j"]
        for completeness in ("partial", "truncated", "unknown"):
            result = contract.evaluate_completion(node, {"dashboard": envelope({"total": 2}, completeness)})
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["scope_complete"])
            self.assertEqual(contract.evaluate_final(wf["nodes"][wf["process_id"]], {"j": result}, ["j"])["status"], "unknown")
            strict = deepcopy(node)
            strict["execution"]["completion"]["validator"] = "all_complete_v1"
            self.assertEqual(contract.evaluate_completion(strict, {"dashboard": envelope({}, completeness)})["status"], "unknown")
        self.assertTrue(contract.evaluate_completion(node, {"dashboard": envelope({"results": []}, "empty")})["scope_complete"])
        self.assertEqual(contract.evaluate_completion(node, {"dashboard": {"status": "failed"}})["status"], "failed")

    def test_bounded_page_completion_and_real_missing_data_are_distinct(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        node = wf["nodes"]["new-operations-jira-j"]
        page = {**envelope({"total": 4}, "partial"), "scope": "single_page"}
        result = contract.evaluate_completion(node, {"dashboard": page})
        self.assertEqual(result["status"], "succeeded")
        self.assertFalse(result["scope_complete"])
        final = contract.evaluate_final(wf["nodes"][wf["process_id"]], {"j": result}, ["j"])
        self.assertEqual(final["status"], "succeeded")
        self.assertFalse(final["scope_complete"])
        docs = examples.installation_docs_workflow(refs())
        body = docs["nodes"]["new-documents-page-j"]
        self.assertEqual(contract.evaluate_completion(body, {"page": {**page, "completeness": "truncated"}})["status"], "unknown")
        self.assertEqual(contract.evaluate_completion(body, {"page": envelope({"content": "confirmed"})})["status"], "succeeded")

    def summary_fixture(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        node = wf["nodes"]["new-operations-summary-j"]
        node["execution"]["completion"].pop("required_claims", None)
        stored, claims = {}, []
        for ref in node["execution"]["evidence"]:
            stored[ref["job_id"]] = {ref["call_id"]: envelope({"count": 2})}
            claims.append({**ref, "path": ["data", "count"], "value": 2})
        return node, stored, {"claims": claims, "limitations": []}

    def test_summary_accepts_exact_claims_and_rejects_fabrication_and_prose(self):
        node, stored, data = self.summary_fixture()
        verified = contract.evaluate_completion(node, {"summary": envelope(data)}, stored_results=stored)
        self.assertEqual(verified["status"], "succeeded")
        for mutate in (lambda d: d["claims"][0].update(value=999), lambda d: d["claims"][0].update(label="CI passed"),
                       lambda d: d.update(summary="Windows installation complete"),
                       lambda d: d["claims"][0].update(path=["data", "ci_status"], value="passed"),
                       lambda d: d["claims"].pop(), lambda d: d["claims"][0].update(path=["data"], value={"count": 2})):
            changed = deepcopy(data)
            mutate(changed)
            self.assertEqual(contract.evaluate_completion(node, {"summary": envelope(changed)}, stored_results=stored)["status"], "unknown")

    def test_summary_requires_useful_business_observations_not_only_ok(self):
        node, stored, data = self.summary_fixture()
        required = {**node["execution"]["evidence"][0], "path": ["data", "summary", "total"]}
        node["execution"]["completion"]["required_claims"] = [required]
        stored[required["job_id"]][required["call_id"]]["data"]["summary"] = {"total": 7}
        verified = contract.evaluate_completion(node, {"summary": envelope(data)}, stored_results=stored)
        self.assertEqual(verified["reason"], "missing_required_claim")
        data["claims"].append({**required, "value": 7})
        self.assertEqual(contract.evaluate_completion(node, {"summary": envelope(data)}, stored_results=stored)["status"], "succeeded")

    def test_summary_requires_exact_limited_scope_and_does_not_claim_full_completion(self):
        node, stored, data = self.summary_fixture()
        ref = node["execution"]["evidence"][1]
        stored[ref["job_id"]][ref["call_id"]]["completeness"] = "partial"
        self.assertEqual(contract.evaluate_completion(node, {"summary": envelope(data)}, stored_results=stored)["status"], "unknown")
        data["limitations"] = [{**ref, "completeness": "partial"}]
        verified = contract.evaluate_completion(node, {"summary": envelope(data)}, stored_results=stored)
        self.assertEqual(verified["status"], "succeeded")
        self.assertFalse(verified["scope_complete"])

    def test_negative_human_confirmation_does_not_complete(self):
        node = {"execution": {"completion": {"validator": "selection_v1", "version": 1, "input_key": "confirmed"}}}
        self.assertEqual(contract.evaluate_completion(node, {}, {"confirmed": False})["status"], "failed")
        self.assertEqual(contract.evaluate_completion(node, {}, {"confirmed": True})["status"], "succeeded")
        self.assertEqual(contract.evaluate_completion(node, {}, {})["status"], "waiting_input")

    def test_skills_and_fixed_execution_model_boundaries(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        node = deepcopy(wf["nodes"]["new-operations-jira-j"])
        node["execution"]["limits"]["max_model_calls"] = 1
        self.assertTrue(contract.validate_execution(node, catalog(wf)))
        summary = deepcopy(wf["nodes"]["new-operations-summary-j"])
        summary["execution"]["skill_refs"] = [{"skill_id": "registered-skill", "content_hash": "not-a-hash"}]
        self.assertTrue(contract.validate_execution(summary, catalog(wf)))

    def test_skill_reference_must_belong_to_inherited_native_skill(self):
        wf = examples.operations_workflow(refs(), "synthetic-model")
        value = catalog(wf)
        node = value["nodes"]["new-operations-summary-j"]
        node["execution"]["skill_refs"] = [{"skill_id": "native-policy", "content_hash": "d" * 64}]
        self.assertTrue(contract.validate_execution(node, value))
        value["skills"]["local-policy"] = {"id": "local-policy", "name": "Policy", "type": "skill", "source": "open_webui", "reference": "native-policy", "body": ""}
        value["nodes"][wf["process_id"]]["skills"] = ["local-policy"]
        self.assertEqual(contract.validate_execution(node, value), [])

    def test_copy_remaps_evidence_and_candidate_binding(self):
        wf = examples.installation_docs_workflow(refs())
        node = wf["nodes"]["new-documents-page-j"]
        contract.remap_execution(node, {"new-documents-search-j": "saved-search"})
        self.assertEqual(node["execution"]["calls"][0]["arguments"]["page_id"]["selection"]["job_id"], "saved-search")


class ContractAuthoringTests(AuthoringFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async def capabilities(user):
            return deepcopy(self.assets.get("execution_capabilities", []))
        self.service.execution.configure()
        self.service.execution.bridge.capabilities = capabilities
        self.assets["execution_capabilities"] = [{"reference": ref, "schema": {"type": "object"}, "state": "allowed", "executable": False,
                                                   "reason": "native_personal_connection_required"} for ref in refs().values()]

    async def test_p_save_publish_exact_approval_and_reference_remapping(self):
        process = await self.create()
        document = examples.operations_workflow(refs(), "synthetic-model", process_id=process["process_id"])
        saved = await self.save("ems-a", process, document)
        self.assertFalse(any(key.startswith("new-") for key in saved["workflow"]["nodes"]))
        await self.publish("ems-a", saved)
        old = self.catalog()[0]
        self.assets["execution_capabilities"][0]["state"] = "disabled"
        result = await self.action("ems-a", "validate_draft", saved)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "native_revalidation_required")
        self.assertEqual(old, self.catalog()[0])

    async def test_approval_change_between_validation_and_publish_preserves_draft(self):
        process = await self.create()
        document = examples.installation_docs_workflow(refs(), process_id=process["process_id"])
        saved = await self.save("ems-a", process, document)
        checked = await self.action("ems-a", "validate_draft", saved)
        self.assertTrue(checked["ok"], checked)
        self.assets["execution_capabilities"][2]["reference"]["revision"] = 2
        result = await self.action("ems-a", "publish", checked["process"])
        self.assertFalse(result["ok"], result)
        self.assertEqual((await self.read("ems-a", saved))["process"]["workflow"], saved["workflow"])
