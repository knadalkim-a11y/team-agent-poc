"""Offline preservation, partial-write recovery and conflict tests for ApplyDemo."""
import ast
import copy
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "ees_demo_assets.py"
spec = importlib.util.spec_from_file_location("ees_demo_assets", MODULE)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def read_grant(principal="team"):
    return {"principal_type": "group", "principal_id": principal, "permission": "read"}


class FakeAPI:
    """Models API replacement; visible prompts use meta.suggestion_prompts.

    Unknown metadata, including the broken suggestionPrompts field, persists in
    API round trips but is not the field read by the Open WebUI placeholder.
    """
    def __init__(self):
        self.rows = {("model", "existing-ees"): {
            "id": "existing-ees", "user_id": "original-owner", "name": "EES 통합 Assistant",
            "base_model_id": "internal-llm", "is_active": True,
            "params": {"system": "사내 공통 정책\n사용자 추가 지침", "temperature": 0.2,
                       "function_calling": "legacy"},
            "meta": {"toolIds": ["jira_real", "wo_demo"], "skillIds": ["policy"],
                     "knowledge": [{"id": "manual"}], "custom": {"keep": True},
                     "capabilities": {"memory": True},
                     "suggestion_prompts": [{"title": ["기존", "업무"], "content": "기존 질문"}]},
            "access_grants": [read_grant(), {"principal_type": "user", "principal_id": "editor",
                                              "permission": "write"}]}}
        self.valves, self.calls = {}, []
        self.fail_before, self.fail_after, self.fail_read = None, None, None
        self.drop_grants = False
        self.hide_content = False
        self.redact_model = False
        self.concurrent = None
        self.valve_defaults = None
        self.capabilities = {"version": 1, "conditional_apply": True, "process_scope": "single"}
        self.before_conditional_write = None
        self.after_conditional_write = None

    def snapshot(self, kind, identifier, *, read=True):
        asset = (self._native("GET", self.native_path(kind, identifier)) if read else
                 copy.deepcopy(self.valves.get(identifier, self.valve_defaults)
                 if kind == "valves" and ("tool", identifier) in self.rows else self.rows.get((kind, identifier))))
        parent = copy.deepcopy(self.rows.get(("tool", identifier))) if kind == "valves" else None
        if kind == "valves" and parent is None:
            asset = None
        state = {"kind": kind, "id": identifier, "asset": asset, "parent": parent}
        if kind == "tool":
            state["valves"] = copy.deepcopy(self.valves.get(identifier, self.valve_defaults))
        token = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        value = {"asset": asset, "exists": parent is not None if kind == "valves" else asset is not None, "token": token}
        if kind == "valves":
            value["parent"] = parent
        return value

    @staticmethod
    def native_path(kind, identifier, *, operation=None):
        if operation == "create":
            return "/api/v1/models/create" if kind == "model" else "/api/v1/tools/create"
        if kind == "model":
            return "/api/v1/models/model/update" if operation else "/api/v1/models/model?id=" + identifier
        return "/api/v1/tools/id/" + identifier + ("/valves" if kind == "valves" else "") + ("/update" if operation else "")

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path == assets.ASSET_API + "/capabilities":
            return copy.deepcopy(self.capabilities)
        if path == assets.ASSET_API + "/snapshot":
            return self.snapshot(body["kind"], body["id"])
        if path == assets.ASSET_API + "/apply":
            kind, identifier = body["kind"], body["id"]
            if self.before_conditional_write:
                self.before_conditional_write(kind, identifier)
            baseline = self.snapshot(kind, identifier, read=False)
            # Include native read-derived values consistently in fake signed state.
            if kind == "model" and baseline["asset"]:
                baseline = self.snapshot(kind, identifier)
            if body["expected_token"] != baseline["token"]:
                raise assets.DemoAssetsError("concurrent_edit", identifier)
            self._native("POST", self.native_path(kind, identifier, operation=body["operation"]), body["payload"])
            if self.after_conditional_write:
                self.after_conditional_write(kind, identifier)
            result = self.snapshot(kind, identifier)
            if kind == "tool":
                result["valves_snapshot"] = self.snapshot("valves", identifier)
            return result
        return self._native(method, path, body)

    def _native(self, method, path, body=None):
        if path == "/api/models":
            return {"data": [{"id": "internal-llm"}]}
        if "/models/" in path:
            kind = "model"
            identifier = (body or {}).get("id") or parse_qs(urlsplit(path).query)["id"][0]
        else:
            kind = "valves" if "/valves" in path else "tool"
            identifier = ((body or {}).get("id") if path.endswith("/create") else
                          unquote(path.split("/id/", 1)[1].split("/", 1)[0]))
        key = (kind, identifier)
        if method == "GET":
            if self.fail_read == key:
                raise TimeoutError("private API response must never leak")
            if self.concurrent == key:
                reads = sum(1 for m, p, b in self.calls if p == assets.ASSET_API + "/snapshot"
                            and b == {"kind": kind, "id": identifier})
                if reads == 2:
                    if kind == "tool":
                        self.rows[key]["content"] += "\n# concurrent edit\n"
                    else:
                        self.rows[key]["params"]["system"] += "\n동시 편집"
            row = self.valves.get(identifier) if kind == "valves" else self.rows.get(key)
            if kind == "valves" and row is None and ("tool", identifier) in self.rows:
                row = self.valve_defaults
            result = copy.deepcopy(row)
            if kind == "model" and result:
                result["write_access"] = not self.redact_model
                if self.redact_model:
                    result["params"] = {}
            if self.hide_content and kind == "tool" and result:
                result.pop("content", None)
            return result
        if self.fail_before == key:
            raise TimeoutError("private API response must never leak")
        if kind == "valves":
            self.valves[identifier] = copy.deepcopy(body)
        else:
            existing = self.rows.get(key, {})
            row = copy.deepcopy(body)
            row["user_id"] = existing.get("user_id", "deployment-admin")
            row["updated_at"] = len(self.calls)
            if kind == "model":
                for name in ("profile_image_url", "description", "capabilities", "knowledge"):
                    row["meta"].setdefault(name, None)
            else:
                row["meta"]["manifest"] = {"title": "Tool title", "version": "0.1.0",
                                             "ees_demo_pack": assets.PACK}
                row["meta"]["has_user_valves"] = False
                row["specs"] = [{"name": "query"}]
            if self.drop_grants:
                row["access_grants"] = []
            else:
                row["access_grants"] = [{**g, "id": str(i), "resource_type": kind,
                                          "resource_id": identifier, "created_at": len(self.calls)}
                                         for i, g in enumerate(reversed(row["access_grants"]))]
            self.rows[key] = row
        if self.fail_after == key:
            raise TimeoutError("private API response must never leak")
        return copy.deepcopy(self.valves.get(identifier) if kind == "valves" else self.rows[key])

    @property
    def writes(self):
        # Preserve old native payload assertions while recording actual HTTP
        # requests in calls for separate no-fallback/conditional contract checks.
        return [("POST", self.native_path(body["kind"], body["id"], operation=body["operation"]), body["payload"])
                for method, path, body in self.calls if path == assets.ASSET_API + "/apply"]


class ApplyAssetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "agent-pack").mkdir()
        self.state = self.root / "private-state"
        self.api = FakeAPI()
        tools = []
        for name in ("data", "delegate"):
            path = f"agent-pack/{name}.py"
            (self.root / path).write_text('"""\ntitle: Demo\nees_demo_pack: ees-demo-v1\n"""\nclass Tools:\n    pass\n', encoding="utf-8")
            tools.append({"id": "ees_demo_" + name, "name": name, "path": path,
                          "managed_valves": {"ees_model_id": "$EES_MODEL_ID"}})
        models = []
        for name in ("ems", "apc", "fdc", "ees"):
            path = f"agent-pack/{name}.md"
            (self.root / path).write_text(f"{name} 전문 분석 지침", encoding="utf-8")
            item = {"id": "ees-demo-" + name, "name": name.upper(), "prompt_path": path,
                    "tool_ids": ["ees_demo_data"],
                    "suggestions": [{"title": [name, "시연"], "content": name + " 분석해줘"}]}
            if name == "ees":
                item["tool_ids"].append("ees_demo_delegate")
                ees = item
            else:
                models.append(item)
        self.manifest = {"version": "1", "tools": tools, "models": models, "ees": ees}
        self.write_manifest()

    def write_manifest(self):
        (self.root / "agent-pack/ees-demo.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def apply(self, commit="a" * 40):
        return assets.apply_assets(self.api, self.root, self.state, "existing-ees", commit)

    def expect_error(self, code):
        with self.assertRaises(assets.DemoAssetsError) as caught:
            self.apply()
        self.assertEqual(code, caught.exception.code)
        self.assertNotIn("private API", str(caught.exception))
        return caught.exception

    def use_shipped_starter_suggestions(self):
        shipped = json.loads((MODULE.parents[1] / "agent-pack/ees-demo.json").read_text(encoding="utf-8"))["ees"]
        relative = shipped["suggestions_path"]
        source = (MODULE.parents[1] / relative).read_text(encoding="utf-8")
        (self.root / relative).write_text(source, encoding="utf-8")
        self.manifest["ees"].pop("suggestions", None)
        for key in ("suggestions_path", "retired_suggestions"):
            self.manifest["ees"][key] = copy.deepcopy(shipped[key])
        self.write_manifest()
        return json.loads(source), copy.deepcopy(shipped["retired_suggestions"])

    def install_v024_state(self):
        """Represent the shipped API/journal shape without invoking a legacy merge."""
        expected, retired = self.use_shipped_starter_suggestions()
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"] = retired
        self.apply()
        path = self.state / assets.STATE_FILE
        state = json.loads(path.read_text(encoding="utf-8"))
        for key, record in state["assets"].items():
            record["version"] = "0.2.4"
            if not key.startswith("model:"):
                continue
            identifier = key.split(":", 1)[1]
            row = self.api.rows[("model", identifier)]
            row["meta"]["suggestionPrompts"] = copy.deepcopy(record["spec"]["suggestions"])
            row["meta"].pop("suggestion_prompts")
            if identifier == "existing-ees":
                row["meta"]["suggestion_prompts"] = copy.deepcopy(retired)
            record["spec"].pop("suggestion_key")
            record["desired_value"] = assets._view(row, "model")
            record["source_hash"] = assets._hash(assets._payload(row, "model"))
        state["version"] = "0.2.4"
        path.write_text(json.dumps(state), encoding="utf-8")
        self.api.calls.clear()
        return expected, retired

    def test_v024_journal_migrates_visible_starters_and_reapplies_without_writes(self):
        expected, retired = self.install_v024_state()
        old = copy.deepcopy(self.api.rows[("model", "existing-ees")])
        self.assertEqual(retired, old["meta"]["suggestion_prompts"])
        self.assertEqual(expected, old["meta"]["suggestionPrompts"])
        self.assertEqual(4, self.apply("b" * 40)["changed"])
        new = self.api.rows[("model", "existing-ees")]
        self.assertEqual(expected, new["meta"]["suggestion_prompts"])
        for key in ("name", "base_model_id", "is_active", "params", "user_id"):
            self.assertEqual(old[key], new[key])
        self.assertEqual(assets._grants(old["access_grants"]), assets._grants(new["access_grants"]))
        for key in ("toolIds", "skillIds", "knowledge", "custom", "capabilities"):
            self.assertEqual(old["meta"][key], new["meta"][key])
        for (kind, _), row in self.api.rows.items():
            if kind == "model":
                self.assertNotIn("suggestionPrompts", row["meta"])
                self.assertIn("suggestion_prompts", row["meta"])
        state = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        for key, record in state["assets"].items():
            if key.startswith("model:"):
                self.assertEqual("suggestion_prompts", record["spec"]["suggestion_key"])
        count = len(self.api.writes)
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        self.assertEqual(count, len(self.api.writes))

    def test_v024_migration_preserves_user_rows_in_both_metadata_fields(self):
        expected, retired = self.install_v024_state()
        meta = self.api.rows[("model", "existing-ees")]["meta"]
        edited = copy.deepcopy(retired[1])
        edited["title"] = ["내 설비 검색", "현장 편집"]
        extras = [edited, {"title": ["사용자", "추가"], "content": "현장 추가 질문"}]
        meta["suggestion_prompts"].extend(copy.deepcopy(extras))
        legacy_extra = {"title": ["이전 사용자", "추가"], "content": "별도 저장 질문"}
        meta["suggestionPrompts"].append(legacy_extra)
        self.apply()
        meta = self.api.rows[("model", "existing-ees")]["meta"]
        self.assertEqual(extras + expected, meta["suggestion_prompts"])
        self.assertEqual([legacy_extra], meta["suggestionPrompts"])
        self.assertEqual(0, self.apply()["changed"])

    def test_v024_migration_stops_on_managed_legacy_edit_or_visible_collision(self):
        for key, code in (("suggestionPrompts", "managed_field_conflict"),
                          ("suggestion_prompts", "suggestion_collision")):
            with self.subTest(key=key):
                self.setUp()
                expected, _ = self.install_v024_state()
                meta = self.api.rows[("model", "existing-ees")]["meta"]
                edited = copy.deepcopy(expected[0])
                edited["title"] = ["사용자 지정", "보존할 제목"]
                if key == "suggestionPrompts":
                    meta[key][0] = edited
                else:
                    meta[key].append(edited)
                before = copy.deepcopy(self.api.rows)
                self.expect_error(code)
                self.assertEqual([], self.api.writes)
                self.assertEqual(before, self.api.rows)

    def test_v024_migration_recovers_old_pending_and_new_write_response_loss(self):
        for mode in ("legacy-pending", "before", "after"):
            with self.subTest(mode=mode):
                self.setUp()
                expected, _ = self.install_v024_state()
                if mode == "legacy-pending":
                    path = self.state / assets.STATE_FILE
                    state = json.loads(path.read_text(encoding="utf-8"))
                    state["assets"]["model:existing-ees"]["status"] = "pending"
                    path.write_text(json.dumps(state), encoding="utf-8")
                    self.assertEqual(4, self.apply()["changed"])
                else:
                    setattr(self.api, "fail_" + mode, ("model", "existing-ees"))
                    error = self.expect_error("asset_apply_failed")
                    self.assertTrue(error.pending)
                    setattr(self.api, "fail_" + mode, None)
                    self.assertEqual(1 if mode == "before" else 0, self.apply()["changed"])
                self.assertEqual(expected,
                                 self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"])
                self.assertEqual(0, self.apply()["changed"])

    def test_v025_starters_replace_equipment_entry_with_connector_briefing(self):
        # Exact previously shipped UI rows: exercise ownership across the release.
        previous = [
            {
                "title": [
                    "생산 손실 줄이기",
                    "조립 2라인 개선 기회 분석"
                ],
                "content": "조립 2라인을 분석해서 생산 손실을 줄일 수 있는 개선 기회를 찾아줘. 우선 확인할 항목도 정리해줘."
            },
            {
                "title": [
                    "라인 설비 한눈에 보기",
                    "천안 조립 1라인 설비 조회"
                ],
                "content": "시연용으로 한국 천안 사업장의 조립 SHOP, 조립 1라인 설비를 찾아줘."
            },
            {
                "title": [
                    "점검 WO 초안 작성",
                    "권취 설비 이상 소음 점검"
                ],
                "content": "시연용으로 한국 천안 사업장의 조립 SHOP, 조립 1라인, 권취 공정의 권취 설비 1호에서 평소보다 큰 소음이 나고 있어. 점검 WO 초안을 작성해줘. 작업 구분은 점검, 우선순위는 일반으로 해줘."
            }
        ]
        expected, _ = self.use_shipped_starter_suggestions()
        self.manifest["ees"].pop("suggestions_path")
        self.manifest["ees"].pop("retired_suggestions")
        self.manifest["ees"]["suggestions"] = previous
        self.write_manifest()
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"] = []
        self.apply()
        self.use_shipped_starter_suggestions()
        self.assertEqual(1, self.apply("b" * 40)["changed"])
        self.assertEqual(expected, self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"])
        count = len(self.api.writes)
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        self.assertEqual(count, len(self.api.writes))

    def test_canonical_starters_replace_old_manual_and_managed_questions_once(self):
        # A later release must also replace questions already managed in the UI field.
        previous = [
            {"title": ["개선 기회 찾기", "조립 2라인 · 시연"],
             "content": "조립 2라인을 분석해서 생산 손실을 줄일 수 있는 개선 기회를 찾아줘."},
            {"title": ["다른 사례 분석하기", "조립 2라인 · 시연"],
             "content": "조립 2라인의 다른 시연 사례에서도 개선 기회가 있는지 확인해줘."},
            {"title": ["반복 정비 줄이기", "조립 2라인 · 시연"],
             "content": "조립 2라인에서 반복 정비를 줄일 수 있는 부분을 찾아줘."},
        ]
        expected, retired = self.use_shipped_starter_suggestions()
        self.manifest["ees"].pop("suggestions_path")
        self.manifest["ees"].pop("retired_suggestions")
        self.manifest["ees"]["suggestions"] = previous
        self.write_manifest()
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"] = retired
        self.apply()
        self.assertEqual(len(retired) + len(previous), len(self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"]))

        self.use_shipped_starter_suggestions()
        self.assertEqual(1, self.apply("b" * 40)["changed"])
        self.assertEqual(expected, self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"])
        count = len(self.api.writes)
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        self.assertEqual(count, len(self.api.writes))

    def test_retiring_starters_preserves_edited_rows_and_user_questions(self):
        expected, retired = self.use_shipped_starter_suggestions()
        edited_title = copy.deepcopy(retired[-1])
        edited_title["title"] = ["내 설비 검색", "현장 편집"]
        edited_content = copy.deepcopy(retired[3])
        edited_content["content"] += " 조립 2라인부터 찾아줘."
        extras = [edited_title, edited_content, {"title": ["사용자", "추가"], "content": "추가 질문"}]
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"] = retired + copy.deepcopy(extras)
        self.apply()
        self.assertEqual(extras + expected,
                         self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"])
        count = len(self.api.writes)
        self.assertEqual(0, self.apply()["changed"])
        self.assertEqual(count, len(self.api.writes))

    def test_user_title_colliding_with_new_starter_stops_before_writes(self):
        expected, retired = self.use_shipped_starter_suggestions()
        edited = copy.deepcopy(expected[0])
        edited["title"] = ["내가 수정한", "업무 질문"]
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"] = retired + [edited]
        before = copy.deepcopy(self.api.rows)
        self.expect_error("suggestion_collision")
        self.assertEqual([], self.api.writes)
        self.assertEqual(before, self.api.rows)

    def test_active_starters_with_same_content_still_stop_before_api_calls(self):
        expected, _ = self.use_shipped_starter_suggestions()
        duplicate = copy.deepcopy(expected[0])
        duplicate["title"] = ["같은 질문", "다른 제목"]
        source = self.root / self.manifest["ees"]["suggestions_path"]
        source.write_text(json.dumps(expected + [duplicate]), encoding="utf-8")
        self.expect_error("duplicate_suggestions")
        self.assertEqual([], self.api.calls)
        self.assertEqual([], self.api.writes)

    def test_starter_path_errors_and_duplicate_source_stop_before_api_calls(self):
        cases = (("missing", "invalid_source_path"), ("escape", "invalid_source_path"),
                 ("duplicate", "invalid_manifest"))
        for mode, code in cases:
            with self.subTest(mode=mode):
                self.setUp()
                expected, _ = self.use_shipped_starter_suggestions()
                if mode == "missing":
                    self.manifest["ees"]["suggestions_path"] = "agent-pack/missing.json"
                elif mode == "escape":
                    self.manifest["ees"]["suggestions_path"] = str(MODULE.parents[1] / "agent-pack/ees-prompt-suggestions.json")
                else:
                    self.manifest["ees"]["suggestions"] = expected
                self.write_manifest()
                self.expect_error(code)
                self.assertEqual([], self.api.calls)

    def test_creates_then_reapplies_without_mutation_and_preserves_ees(self):
        old = copy.deepcopy(self.api.rows[("model", "existing-ees")])
        result = self.apply()
        self.assertEqual(8, result["changed"])
        new = self.api.rows[("model", "existing-ees")]
        for key in ("name", "user_id", "base_model_id", "is_active"):
            self.assertEqual(old[key], new[key])
        self.assertEqual(assets._grants(old["access_grants"]), assets._grants(new["access_grants"]))
        self.assertTrue(new["params"]["system"].startswith(old["params"]["system"]))
        self.assertEqual(0.2, new["params"]["temperature"])
        self.assertEqual("native", new["params"]["function_calling"])
        for key in ("skillIds", "knowledge", "custom", "capabilities"):
            self.assertEqual(old["meta"][key], new["meta"][key])
        self.assertEqual(old["meta"]["toolIds"], new["meta"]["toolIds"][:2])
        for name in ("ems", "apc", "fdc"):
            child = self.api.rows[("model", "ees-demo-" + name)]
            self.assertFalse(child["meta"]["capabilities"]["memory"])
            self.assertNotIn("skillIds", child["meta"])
            self.assertTrue(all(g["permission"] == "read" for g in child["access_grants"]))
        count = len(self.api.writes)
        state_before = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(0, self.apply()["changed"])
        self.assertEqual(count, len(self.api.writes))
        state_after = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state_before["assets"]["model:existing-ees"]["previous_value"],
                         state_after["assets"]["model:existing-ees"]["previous_value"])
        self.assertFalse(any("jira_real" in path or "/valves/user" in path for _, path, _ in self.api.calls))

    def test_new_version_preserves_ui_extras_and_unmanaged_valves(self):
        self.apply()
        model = self.api.rows[("model", "existing-ees")]
        model["params"]["system"] += "\n현장 추가 규칙"
        model["params"]["temperature"] = 0.4
        model["meta"]["toolIds"].append("new-real-tool")
        model["meta"]["suggestion_prompts"].append({"title": ["사용자", "추가"], "content": "추가 질문"})
        self.api.valves["ees_demo_data"]["timeout_seconds"] = 150
        (self.root / "agent-pack/ees.md").write_text("개선한 시연 지침", encoding="utf-8")
        (self.root / "agent-pack/data.py").write_text((self.root / "agent-pack/data.py").read_text(encoding="utf-8") + "# version 2\n", encoding="utf-8")
        self.manifest["ees"]["suggestions"][0]["title"] = ["새 제목", "시연"]
        self.write_manifest()
        self.assertEqual(2, self.apply("b" * 40)["changed"])
        model = self.api.rows[("model", "existing-ees")]
        self.assertTrue(model["params"]["system"].endswith("현장 추가 규칙"))
        self.assertIn("개선한 시연 지침", model["params"]["system"])
        self.assertEqual(0.4, model["params"]["temperature"])
        self.assertIn("new-real-tool", model["meta"]["toolIds"])
        self.assertIn("추가 질문", [s["content"] for s in model["meta"]["suggestion_prompts"]])
        self.assertEqual(150, self.api.valves["ees_demo_data"]["timeout_seconds"])

    def prepare_editor_formatted_upgrade(self, lost_response=False):
        """A tiny approved formatting pair; real release hashes are checked separately."""
        header = '"""\ntitle: Demo\nees_demo_pack: ees-demo-v1\n"""\n'
        raw = header + 'class Tools:\n    def query(self): return {"count":1}  # keep comment\n'
        formatted = (header + '\n\nclass Tools:\n    def query(self):\n'
                     '        return {"count": 1}  # keep comment\n')
        source = self.root / "agent-pack/data.py"
        source.write_text(raw, encoding="utf-8")
        if lost_response:
            self.api.fail_after = ("tool", "ees_demo_data")
            self.assertTrue(self.expect_error("asset_apply_failed").pending)
            self.api.fail_after = None
        else:
            self.apply()
        row = self.api.rows[("tool", "ees_demo_data")]
        row["content"] = formatted
        source.write_text(raw + "\n# newer managed version\n", encoding="utf-8")
        allowlist = mock.patch.dict(assets._APPLIED_TOOL_EDITOR_FORMATS, {
            "ees_demo_data": {assets._source_digest(raw): assets._source_digest(formatted)}
        }, clear=True)
        allowlist.start()
        self.addCleanup(allowlist.stop)
        self.api.calls.clear()
        return row, raw, formatted, source

    def test_known_editor_format_upgrades_and_preserves_live_backup_and_settings(self):
        row, _, formatted, source = self.prepare_editor_formatted_upgrade()
        row["content"] = formatted.replace("\n", "\r\n") + "\r\n"
        row["user_id"] = "original-tool-owner"
        row["meta"]["custom"] = {"keep": True}
        row["meta"]["description"] = "현장 설명"
        row["access_grants"] = [read_grant("factory"), {
            "principal_type": "user", "principal_id": "editor", "permission": "write"}]
        self.api.valves["ees_demo_data"]["timeout_seconds"] = 150
        before, valves = copy.deepcopy(row), copy.deepcopy(self.api.valves)

        self.assertEqual(1, self.apply("b" * 40)["changed"])
        self.assertEqual(["/api/v1/tools/id/ees_demo_data/update"],
                         [path for _, path, _ in self.api.writes])
        after = self.api.rows[("tool", "ees_demo_data")]
        self.assertEqual(source.read_text(encoding="utf-8"), after["content"])
        for key in ("name", "user_id"):
            self.assertEqual(before[key], after[key])
        for key in ("custom", "description"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        self.assertEqual(assets._grants(before["access_grants"]),
                         assets._grants(after["access_grants"]))
        self.assertEqual(valves, self.api.valves)
        journal = self.state / assets.STATE_FILE
        record = json.loads(journal.read_text(encoding="utf-8"))["assets"]["tool:ees_demo_data"]
        self.assertEqual(before["content"], record["previous_value"]["content"])
        self.assertEqual(before["meta"]["custom"], record["previous_value"]["meta"]["custom"])
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        self.assertEqual(1, len(self.api.writes))
        again = json.loads(journal.read_text(encoding="utf-8"))["assets"]["tool:ees_demo_data"]
        self.assertEqual(record["previous_value"], again["previous_value"])

    def test_editor_format_does_not_adopt_edits_other_fields_or_unknown_sources(self):
        for mutation in ("behavior", "comment", "literal-style", "name", "marker",
                         "managed-valve", "unknown-baseline", "wrong-tool-id"):
            with self.subTest(mutation=mutation):
                self.setUp()
                row, raw, formatted, _ = self.prepare_editor_formatted_upgrade()
                journal = self.state / assets.STATE_FILE
                if mutation == "behavior":
                    row["content"] = formatted.replace('"count": 1', '"count": 2')
                elif mutation in ("comment", "literal-style"):
                    row["content"] = (formatted.replace("keep comment", "my local comment")
                                      if mutation == "comment" else
                                      formatted.replace('"count"', "'count'"))
                    self.assertEqual(ast.dump(ast.parse(raw)), ast.dump(ast.parse(row["content"])))
                elif mutation == "name":
                    row["name"] = "현장에서 바꾼 이름"
                elif mutation == "marker":
                    row["meta"]["manifest"]["ees_demo_pack"] = "another-pack"
                elif mutation == "managed-valve":
                    self.api.valves["ees_demo_data"]["ees_model_id"] = "another-model"
                elif mutation == "unknown-baseline":
                    state = json.loads(journal.read_text(encoding="utf-8"))
                    state["assets"]["tool:ees_demo_data"]["desired"]["content"] = raw + "# local baseline\n"
                    journal.write_text(json.dumps(state), encoding="utf-8")
                    row["content"] += "# local baseline\n"
                else:
                    assets._APPLIED_TOOL_EDITOR_FORMATS["another-tool"] = (
                        assets._APPLIED_TOOL_EDITOR_FORMATS.pop("ees_demo_data"))
                before, saved = copy.deepcopy(self.api.rows), journal.read_text(encoding="utf-8")
                self.assertEqual(0, self.expect_error("managed_field_conflict").changed)
                self.assertEqual([], self.api.writes)
                self.assertEqual(before, self.api.rows)
                self.assertEqual(saved, journal.read_text(encoding="utf-8"))

    def test_editor_format_cannot_confirm_a_pending_lost_creation_response(self):
        self.prepare_editor_formatted_upgrade(lost_response=True)
        journal = self.state / assets.STATE_FILE
        saved = journal.read_text(encoding="utf-8")
        self.assertTrue(self.expect_error("managed_field_conflict").pending)
        self.assertEqual([], self.api.writes)
        self.assertEqual(saved, journal.read_text(encoding="utf-8"))

    def test_editor_format_upgrade_lost_response_recovers_exact_written_value(self):
        _, _, formatted, _ = self.prepare_editor_formatted_upgrade()
        self.api.fail_after = ("tool", "ees_demo_data")
        self.assertTrue(self.expect_error("asset_apply_failed").pending)
        self.api.fail_after = None
        self.assertEqual(0, self.apply()["changed"])
        self.assertEqual(1, len(self.api.writes))
        record = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))["assets"]["tool:ees_demo_data"]
        self.assertEqual("applied", record["status"])
        self.assertEqual(formatted, record["previous_value"]["content"])

    def test_editor_format_preflight_still_rejects_a_later_concurrent_edit(self):
        self.prepare_editor_formatted_upgrade()
        self.api.concurrent = ("tool", "ees_demo_data")
        self.expect_error("concurrent_edit")
        self.assertEqual([], self.api.writes)
        self.assertTrue(self.api.rows[("tool", "ees_demo_data")]["content"].endswith("# concurrent edit\n"))

    def test_editor_format_never_relaxes_post_write_verification_or_pending_retry(self):
        _, _, formatted, source = self.prepare_editor_formatted_upgrade()
        newer_raw = source.read_text(encoding="utf-8")
        newer_formatted = formatted + "\n# newer managed version\n"
        assets._APPLIED_TOOL_EDITOR_FORMATS["ees_demo_data"][assets._source_digest(newer_raw)] = (
            assets._source_digest(newer_formatted))
        request = self.api.request
        def format_after_write(method, path, body=None):
            result = request(method, path, body)
            if method == "POST" and path == assets.ASSET_API + "/apply" and body["id"] == "ees_demo_data":
                self.api.rows[("tool", "ees_demo_data")]["content"] = newer_formatted
            return result
        self.api.request = format_after_write
        error = self.expect_error("verification_failed")
        self.assertEqual(1, error.changed)
        self.assertTrue(error.pending)
        self.api.request = request
        self.expect_error("managed_field_conflict")
        self.assertEqual(1, len(self.api.writes))
        record = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))["assets"]["tool:ees_demo_data"]
        self.assertEqual("pending", record["status"])
        self.assertEqual(newer_raw, record["desired"]["content"])

    def add_panel_script(self, script="(() => { const title = '협업 과정'; })();\n"):
        relative = "agent-pack/cooperation-panel.js"
        (self.root / relative).write_text(script, encoding="utf-8")
        for tool in self.manifest["tools"]:
            tool["ui_script_path"] = relative
            path = self.root / tool["path"]
            path.write_text(path.read_text(encoding="utf-8") + '\nPANEL_SCRIPT = ""  # fixed UI\n',
                            encoding="utf-8")
        self.write_manifest()
        return script

    def test_panel_is_embedded_in_registered_standalone_tools(self):
        script = self.add_panel_script("const title = `협업 '과정'`;\nconst text = '\\\\n</script>';\n")
        before = [(self.root / tool["path"]).read_text(encoding="utf-8")
                  for tool in self.manifest["tools"]]
        self.assertEqual(8, self.apply()["changed"])
        # The API receives one standalone Python file. No sibling JS is needed at runtime.
        (self.root / self.manifest["tools"][0]["ui_script_path"]).unlink()
        for tool, original in zip(self.manifest["tools"], before):
            registered = self.api.rows[("tool", tool["id"])]["content"]
            scope = {}
            exec(compile(registered, "<registered-tool>", "exec"), scope)
            self.assertEqual(script, scope["PANEL_SCRIPT"])
            self.assertEqual(ast.get_docstring(ast.parse(original), clean=False),
                             scope["__doc__"])
            self.assertEqual(original.replace('PANEL_SCRIPT = ""',
                                             "PANEL_SCRIPT = " + repr(script)), registered)

    def test_panel_source_and_slot_errors_stop_before_any_write(self):
        cases = (("missing", "invalid_source_path"), ("escape", "invalid_source_path"),
                 ("nonstring", "invalid_manifest"), ("empty", "empty_source"),
                 ("no-slot", "invalid_panel_script_slot"),
                 ("duplicate", "invalid_panel_script_slot"),
                 ("nonempty", "invalid_panel_script_slot"),
                 ("nested", "invalid_panel_script_slot"))
        for mode, code in cases:
            with self.subTest(mode=mode):
                self.setUp()
                self.add_panel_script()
                tool = self.manifest["tools"][-1]
                if mode in ("missing", "escape", "nonstring"):
                    tool["ui_script_path"] = {"missing": "agent-pack/missing.js",
                                              "escape": "../outside.js", "nonstring": None}[mode]
                    self.write_manifest()
                elif mode == "empty":
                    (self.root / tool["ui_script_path"]).write_text(" \n", encoding="utf-8")
                else:
                    path = self.root / tool["path"]
                    source = path.read_text(encoding="utf-8")
                    replacements = {"no-slot": "OTHER_SCRIPT = ''",
                                    "duplicate": 'PANEL_SCRIPT = ""\nPANEL_SCRIPT = ""',
                                    "nonempty": "PANEL_SCRIPT = 'already filled'",
                                    "nested": 'if True:\n    PANEL_SCRIPT = ""'}
                    path.write_text(source.replace('PANEL_SCRIPT = ""', replacements[mode]),
                                    encoding="utf-8")
                self.expect_error(code)
                self.assertEqual([], self.api.writes)

    def test_panel_upgrade_changes_only_tools_and_prompt_and_is_idempotent(self):
        self.manifest["version"] = "0.1.1"
        self.write_manifest()
        self.apply()
        ees = self.api.rows[("model", "existing-ees")]
        ees["params"]["system"] += "\n현장 추가 규칙"
        ees["params"]["temperature"] = 0.4
        ees["meta"]["toolIds"].insert(0, "additional-tool")
        ees["meta"]["skillIds"].append("additional-skill")
        ees["meta"]["knowledge"].append({"id": "additional-manual"})
        before = copy.deepcopy(self.api.rows)
        for tool in self.manifest["tools"]:
            self.api.valves[tool["id"]]["specialist_timeout_seconds"] = 77
            self.api.rows[("tool", tool["id"])]["meta"]["user_extra"] = {"keep": True}
        before_valves = copy.deepcopy(self.api.valves)
        script = self.add_panel_script()
        self.manifest["version"] = "0.1.2"
        self.write_manifest()
        (self.root / "agent-pack/ees.md").write_text("실시간 협업 패널 사용 지침", encoding="utf-8")
        writes = len(self.api.writes)
        self.assertEqual(3, self.apply("b" * 40)["changed"])
        changed = {body["id"] for _, _, body in self.api.writes[writes:]}
        self.assertEqual({"existing-ees", "ees_demo_data", "ees_demo_delegate"}, changed)
        updated = self.api.rows[("model", "existing-ees")]
        self.assertEqual(before[("model", "existing-ees")]["meta"], updated["meta"])
        self.assertEqual(0.4, updated["params"]["temperature"])
        self.assertTrue(updated["params"]["system"].startswith("사내 공통 정책\n사용자 추가 지침"))
        self.assertTrue(updated["params"]["system"].endswith("현장 추가 규칙"))
        for key in ("name", "user_id", "base_model_id", "is_active"):
            self.assertEqual(before[("model", "existing-ees")][key], updated[key])
        self.assertEqual(assets._grants(before[("model", "existing-ees")]["access_grants"]),
                         assets._grants(updated["access_grants"]))
        self.assertEqual(before_valves, self.api.valves)
        for name in ("ems", "apc", "fdc"):
            key = ("model", "ees-demo-" + name)
            self.assertEqual(before[key], self.api.rows[key])
        for tool in self.manifest["tools"]:
            row = self.api.rows[("tool", tool["id"])]
            self.assertEqual({"keep": True}, row["meta"]["user_extra"])
            self.assertIn(repr(script), row["content"])
        writes = len(self.api.writes)
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        self.assertEqual(writes, len(self.api.writes))
        script_path = self.root / self.manifest["tools"][0]["ui_script_path"]
        script_path.write_text(script + "// updated panel\n", encoding="utf-8")
        self.assertEqual(2, self.apply("c" * 40)["changed"])
        self.assertEqual({"ees_demo_data", "ees_demo_delegate"},
                         {body["id"] for _, _, body in self.api.writes[writes:]})
        self.assertEqual(0, self.apply("c" * 40)["changed"])

    def add_existing_work_order(self, identifier="wo_demo", bind=True):
        old_source = ('"""\ntitle: EES WO Demo\nversion: 0.1.6\n"""\n'
                      'class Tools:\n'
                      '    async def ems_demo_find_equipment(self): pass\n'
                      '    async def wo_demo_view(self): pass\n'
                      '    async def wo_demo_update(self): pass\n')
        new_source = old_source.replace('version: 0.1.6',
                                        'version: 0.2.0\nees_demo_pack: ees-demo-v1')
        new_source += '\nWORK_PANEL_SCRIPT = ""\nPANEL_SCRIPT = "existing WO panel"\n'
        (self.root / "agent-pack/wo.py").write_text(new_source, encoding="utf-8")
        (self.root / "agent-pack/work-panel.js").write_text("/* shared work panel */\n", encoding="utf-8")
        self.manifest["optional_existing_tools"] = [{
            "kind": "work_order", "path": "agent-pack/wo.py",
            "ui_script_path": "agent-pack/work-panel.js", "ui_script_slot": "WORK_PANEL_SCRIPT",
            "accepted_source_sha256": [assets._source_digest(old_source)]}]
        self.write_manifest()
        row = {"id": identifier, "name": "현장 설비·WO", "user_id": "wo-owner",
               "content": old_source, "meta": {"description": "현장 설명", "custom": {"keep": True},
                                                    "manifest": {"title": "EES WO Demo"}},
               "access_grants": [read_grant("wo-team")]}
        self.api.rows[("tool", identifier)] = row
        self.api.valves[identifier] = {"private_setting": "preserve-me"}
        bound = self.api.rows[("model", "existing-ees")]["meta"]["toolIds"]
        if bind and identifier not in bound:
            bound.append(identifier)
        if not bind and identifier in bound:
            bound.remove(identifier)
        return row

    def test_two_scripts_are_embedded_in_order_without_runtime_file_dependencies(self):
        first = self.add_panel_script()
        (self.root / "agent-pack/work-panel.js").write_text("/* shared coordinator */\n", encoding="utf-8")
        for item in self.manifest["tools"]:
            item["ui_script_paths"] = ["agent-pack/work-panel.js", item.pop("ui_script_path")]
        self.write_manifest()
        self.apply()
        for item in self.manifest["tools"]:
            scope = {}
            exec(self.api.rows[("tool", item["id"])]["content"], scope)
            self.assertEqual("/* shared coordinator */\n\n" + first, scope["PANEL_SCRIPT"])

    def test_invalid_script_lists_or_slot_cannot_write_assets(self):
        for mode in ("both", "empty", "non-list", "too-many", "invalid-slot"):
            with self.subTest(mode=mode):
                self.setUp()
                self.add_panel_script()
                item = self.manifest["tools"][0]
                path = item["ui_script_path"]
                if mode == "invalid-slot":
                    item["ui_script_slot"] = "USER_CONFIG"
                else:
                    item["ui_script_paths"] = {"both": [path], "empty": [],
                                               "non-list": path, "too-many": [path] * 3}[mode]
                    if mode != "both":
                        item.pop("ui_script_path")
                self.write_manifest()
                self.expect_error("invalid_panel_script_slot" if mode == "invalid-slot" else "invalid_manifest")
                self.assertEqual([], self.api.writes)

    def test_existing_wo_is_updated_in_place_and_preserves_name_grants_and_valves(self):
        row = self.add_existing_work_order("custom-wo-registration")
        # Editing line endings/final blank lines does not change approved source.
        row["content"] = row["content"].replace("\n", "\r\n") + "\r\n"
        before = copy.deepcopy(row)
        valves = copy.deepcopy(self.api.valves)
        self.assertEqual(9, self.apply()["changed"])
        after = self.api.rows[("tool", row["id"])]
        for key in ("id", "name", "user_id"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(assets._grants(before["access_grants"]), assets._grants(after["access_grants"]))
        self.assertEqual(before["meta"]["description"], after["meta"]["description"])
        self.assertEqual(before["meta"]["custom"], after["meta"]["custom"])
        self.assertEqual(valves[row["id"]], self.api.valves[row["id"]])
        scope = {}
        exec(after["content"], scope)
        self.assertEqual("/* shared work panel */\n", scope["WORK_PANEL_SCRIPT"])
        self.assertEqual("existing WO panel", scope["PANEL_SCRIPT"])
        self.assertFalse(any("/valves" in path and row["id"] in path for _, path, _ in self.api.calls))
        self.assertEqual(["/api/v1/tools/id/custom-wo-registration/update"],
                         [path for _, path, body in self.api.writes if body.get("id") == row["id"]])
        after["name"] = "새 현장 이름"
        self.assertEqual(0, self.apply()["changed"])
        self.assertEqual("새 현장 이름", self.api.rows[("tool", row["id"])]["name"])

    def test_optional_wo_is_not_created_or_connected_when_absent(self):
        self.add_existing_work_order("unbound-wo", bind=False)
        before = copy.deepcopy(self.api.rows[("tool", "unbound-wo")])
        self.assertEqual(8, self.apply()["changed"])
        self.assertEqual(before, self.api.rows[("tool", "unbound-wo")])
        self.assertFalse(any("unbound-wo" in path for _, path, _ in self.api.calls))
        self.assertNotIn("unbound-wo", self.api.rows[("model", "existing-ees")]["meta"]["toolIds"])

    def test_new_manual_wo_registration_gets_shared_script_without_new_registration(self):
        row = self.add_existing_work_order()
        row["content"] = (self.root / "agent-pack/wo.py").read_text(encoding="utf-8")
        self.assertEqual(9, self.apply()["changed"])
        scope = {}
        exec(self.api.rows[("tool", "wo_demo")]["content"], scope)
        self.assertEqual("/* shared work panel */\n", scope["WORK_PANEL_SCRIPT"])
        self.assertFalse(any(path.endswith("/create") and body.get("id") == "wo_demo"
                             for _, path, body in self.api.writes))

    def test_unrecognized_or_edited_wo_source_stops_before_any_write(self):
        for tracked in (False, True):
            with self.subTest(tracked=tracked):
                self.setUp()
                self.add_existing_work_order()
                if tracked:
                    self.apply()
                self.api.rows[("tool", "wo_demo")]["content"] += "\n# User customization\n"
                before = len(self.api.writes)
                self.expect_error("managed_field_conflict" if tracked else "unrecognized_existing_wo_source")
                self.assertEqual(before, len(self.api.writes))

    def test_ambiguous_wo_and_unreadable_wo_stop_preflight(self):
        self.add_existing_work_order()
        second = copy.deepcopy(self.api.rows[("tool", "wo_demo")])
        second["id"] = "another-wo"
        self.api.rows[("tool", "another-wo")] = second
        self.api.rows[("model", "existing-ees")]["meta"]["toolIds"].append("another-wo")
        self.expect_error("ambiguous_existing_work_order")
        self.assertEqual([], self.api.writes)
        del self.api.rows[("tool", "another-wo")]
        self.api.hide_content = True
        self.expect_error("tool_source_not_readable")
        self.assertEqual([], self.api.writes)

    def test_similar_user_tool_is_left_untouched(self):
        row = self.add_existing_work_order()
        row["meta"]["manifest"]["title"] = "My WO Helper"
        row["content"] = '"""title: My WO Helper"""\nclass Tools:\n    def wo_demo_view(self): pass\n'
        before = copy.deepcopy(row)
        self.assertEqual(8, self.apply()["changed"])
        self.assertEqual(before, self.api.rows[("tool", "wo_demo")])

    def test_existing_wo_lost_response_recovers_without_duplicate_write(self):
        self.add_existing_work_order()
        self.api.fail_after = ("tool", "wo_demo")
        error = self.expect_error("asset_apply_failed")
        self.assertTrue(error.pending)
        self.api.fail_after = None
        self.assertEqual(4, self.apply()["changed"])
        self.assertEqual(1, len([body for _, _, body in self.api.writes if body.get("id") == "wo_demo"]))

    def test_existing_wo_concurrent_edit_and_unbound_pending_are_preserved(self):
        self.add_existing_work_order()
        self.api.concurrent = ("tool", "wo_demo")
        self.expect_error("concurrent_edit")
        self.assertTrue(self.api.rows[("tool", "wo_demo")]["content"].endswith("# concurrent edit\n"))
        self.assertFalse(any(body.get("id") == "wo_demo" for _, _, body in self.api.writes))
        self.setUp()
        self.add_existing_work_order()
        self.api.fail_after = ("tool", "wo_demo")
        self.expect_error("asset_apply_failed")
        self.api.rows[("model", "existing-ees")]["meta"]["toolIds"].remove("wo_demo")
        count = len(self.api.writes)
        self.expect_error("pending_work_order_unbound")
        self.assertEqual(count, len(self.api.writes))

    def test_conflicts_stop_before_any_write(self):
        for mutation in ("prompt", "tool", "suggestion", "native", "valves"):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.apply()
                model = self.api.rows[("model", "existing-ees")]
                if mutation == "prompt":
                    model["params"]["system"] = model["params"]["system"].replace("ees 전문", "수정된 전문")
                elif mutation == "tool":
                    model["meta"]["toolIds"].remove("ees_demo_data")
                elif mutation == "suggestion":
                    model["meta"]["suggestion_prompts"][-1]["title"] = ["수정", "제목"]
                elif mutation == "native":
                    model["params"]["function_calling"] = "legacy"
                else:
                    self.api.valves["ees_demo_data"]["ees_model_id"] = "another-model"
                count = len(self.api.writes)
                self.expect_error("managed_field_conflict")
                self.assertEqual(count, len(self.api.writes))

    def test_collision_and_invalid_source_preflight_before_writes(self):
        self.api.rows[("model", "ees-demo-fdc")] = copy.deepcopy(self.api.rows[("model", "existing-ees")])
        self.api.rows[("model", "ees-demo-fdc")]["id"] = "ees-demo-fdc"
        self.expect_error("asset_id_collision")
        self.assertEqual([], self.api.writes)
        del self.api.rows[("model", "ees-demo-fdc")]
        self.manifest["models"][-1]["prompt_path"] = "../outside.txt"
        self.write_manifest()
        self.expect_error("invalid_source_path")
        self.assertEqual([], self.api.writes)

    def test_response_loss_recovers_without_duplicate_creation(self):
        self.api.fail_after = ("model", "ees-demo-apc")
        self.expect_error("asset_apply_failed")
        self.assertEqual("legacy", self.api.rows[("model", "existing-ees")]["params"]["function_calling"])
        self.api.fail_after = None
        result = self.apply()
        self.assertEqual(2, result["changed"])
        paths = [p for m, p, body in self.api.writes if body.get("id") == "ees-demo-apc"]
        self.assertEqual(["/api/v1/models/create"], paths)
        state = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        self.assertTrue(all(r["status"] == "applied" for r in state["assets"].values()))

    def test_failure_before_write_can_retry_same_intent(self):
        self.api.fail_before = ("valves", "ees_demo_data")
        self.expect_error("asset_apply_failed")
        self.api.fail_before = None
        self.assertEqual(7, self.apply()["changed"])

    def test_first_lost_write_response_is_reported_unknown_and_recovers(self):
        self.api.fail_after = ("tool", "ees_demo_data")
        error = self.expect_error("asset_apply_failed")
        self.assertEqual(0, error.changed)
        self.assertTrue(error.pending)
        self.assertTrue(error.unknown)
        self.api.fail_after = None
        self.assertEqual(7, self.apply()["changed"])

    def test_interrupt_after_first_write_keeps_pending_intent_for_retry(self):
        request = self.api.request
        def interrupted(method, path, body=None):
            response = request(method, path, body)
            if method == "POST" and path == assets.ASSET_API + "/apply":
                raise KeyboardInterrupt()
            return response
        self.api.request = interrupted
        error = self.expect_error("operation_interrupted")
        self.assertEqual(0, error.changed)
        self.assertTrue(error.pending)
        self.assertTrue(error.unknown)
        self.api.request = request
        self.assertEqual(7, self.apply()["changed"])

    def test_new_tool_valve_defaults_are_merged_without_false_concurrent_edit(self):
        self.api.valve_defaults = {"ees_model_id": "", "specialist_timeout_seconds": 120}
        self.assertEqual(8, self.apply()["changed"])
        self.assertEqual({"ees_model_id": "existing-ees", "specialist_timeout_seconds": 120},
                         self.api.valves["ees_demo_data"])
        self.assertEqual(0, self.apply()["changed"])

    def test_valve_default_other_model_is_not_overwritten(self):
        self.api.valve_defaults = {"ees_model_id": "another-model"}
        self.expect_error("managed_field_conflict")
        self.assertFalse(any("/valves/update" in path for _, path, _ in self.api.writes))

    def test_noop_refreshes_current_hash_and_expectation_but_keeps_prior_values(self):
        self.apply()
        state_path = self.state / assets.STATE_FILE
        before = json.loads(state_path.read_text(encoding="utf-8"))["assets"]["model:existing-ees"]
        self.api.rows[("model", "existing-ees")]["params"]["temperature"] = 0.5
        self.assertEqual(0, self.apply("b" * 40)["changed"])
        after = json.loads(state_path.read_text(encoding="utf-8"))["assets"]["model:existing-ees"]
        self.assertEqual(before["before"], after["before"])
        self.assertEqual(before["previous_value"], after["previous_value"])
        self.assertNotEqual(before["source_hash"], after["source_hash"])
        self.assertEqual(0.5, after["desired_value"]["params"]["temperature"])
        self.assertEqual("b" * 40, after["source_commit"])

    def test_transport_error_codes_are_preserved_only_from_static_allowlist(self):
        class TransportError(Exception):
            def __init__(self, code):
                self.code = code
                super().__init__("private API response must never leak")
        for code in ("webui_permission_denied", "webui_authentication_failed", "redirect_blocked",
                     "webui_connection_failed", "secret-other-code"):
            with self.subTest(code=code):
                def failed(*args, **kwargs):
                    raise TransportError(code)
                self.api.request = failed
                error = self.expect_error(code if code in assets.TRANSPORT_CODES else "asset_apply_failed")
                self.assertFalse(error.pending)
                self.assertEqual(0, error.changed)

    def test_journal_symlink_is_rejected_and_fixed_temp_link_is_never_opened(self):
        self.state.mkdir()
        outside = self.root / "keep-private.txt"
        outside.write_text("untouched", encoding="utf-8")
        journal = self.state / assets.STATE_FILE
        try:
            journal.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.expect_error("unsafe_journal_path")
        self.assertEqual([], self.api.writes)
        journal.unlink()
        old_temp = journal.with_suffix(".tmp")
        old_temp.symlink_to(outside)
        self.apply()
        self.assertEqual("untouched", outside.read_text(encoding="utf-8"))
        self.assertTrue(old_temp.is_symlink())
        self.assertEqual([], list(self.state.glob(".ees-demo-assets-*.tmp")))

    def test_journal_directory_symlink_is_rejected(self):
        outside = self.root / "outside-dir"
        outside.mkdir()
        try:
            self.state.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.expect_error("unsafe_journal_path")
        self.assertEqual([], self.api.writes)
        self.assertEqual([], list(outside.iterdir()))

    def test_journal_parent_link_cannot_redirect_private_directory(self):
        outside = self.root / "outside-parent"
        outside.mkdir()
        parent_link = self.root / "linked-parent"
        try:
            parent_link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.state = parent_link / "private-state"
        self.expect_error("unsafe_journal_path")
        self.assertEqual([], list(outside.iterdir()))

    def test_verification_failure_preserves_partial_journal(self):
        self.api.drop_grants = True
        self.expect_error("verification_failed")
        state = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual("pending", state["assets"]["tool:ees_demo_data"]["status"])
        self.assertNotIn(("tool", "ees_demo_delegate"), self.api.rows)
        count = len(self.api.writes)
        self.api.drop_grants = False
        self.expect_error("managed_field_conflict")
        self.assertEqual(count, len(self.api.writes))

    def test_real_manifest_sources_pass_preflight(self):
        manifest = assets.load_manifest(MODULE.parents[1])
        self.assertEqual("0.2.11", manifest["version"])
        suggestions = json.loads((MODULE.parents[1] / "agent-pack/ees-prompt-suggestions.json").read_text(encoding="utf-8"))
        self.assertEqual(3, len(suggestions))
        self.assertEqual(suggestions, manifest["ees"]["suggestions"])
        self.assertEqual(5, len(manifest["ees"]["retired_suggestions"]))
        self.assertEqual({"ees_specialists", "ees_demo_data", "ees_workflow"}, {t["id"] for t in manifest["tools"]})
        self.assertEqual({"ees_demo_ems", "ees_demo_apc", "ees_demo_fdc"},
                         {m["id"] for m in manifest["models"]})
        for tool in manifest["tools"]:
            if "ui_script_paths" not in tool:
                self.assertEqual("ees_workflow", tool["id"])
                compile(tool["content"], tool["path"], "exec")
                self.assertIn("ees_workflow", tool["content"])
                continue
            script = "\n".join((MODULE.parents[1] / path).read_text(encoding="utf-8")
                               for path in tool["ui_script_paths"])
            original = (MODULE.parents[1] / tool["path"]).read_text(encoding="utf-8")
            tree = ast.parse(tool["content"])
            panel = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "PANEL_SCRIPT"
                             for target in node.targets)]
            self.assertEqual([script], panel)
            self.assertEqual(ast.get_docstring(ast.parse(original), clean=False),
                             ast.get_docstring(tree, clean=False))
            compile(tool["content"], tool["path"], "exec")
        self.assertEqual(1, len(manifest["optional_existing_tools"]))
        wo = manifest["optional_existing_tools"][0]
        scope = {}
        exec(compile(wo["content"], wo["path"], "exec"), scope)
        self.assertEqual((MODULE.parents[1] / wo["ui_script_path"]).read_text(encoding="utf-8"),
                         scope["WORK_PANEL_SCRIPT"])

    def test_missing_or_incomplete_guard_refuses_before_writes(self):
        for capability in (None, {}, {"version": 1, "conditional_apply": False, "process_scope": "single"},
                           {"version": True, "conditional_apply": True, "process_scope": "single"},
                           {"version": 1, "conditional_apply": True, "process_scope": "multi"}):
            with self.subTest(capability=capability):
                self.api.capabilities = capability
                original = copy.deepcopy(self.api.rows)
                error = self.expect_error("conditional_write_unavailable")
                self.assertEqual(0, error.changed)
                self.assertFalse(error.pending)
                self.assertEqual([], self.api.writes)
                self.assertEqual(original, self.api.rows)
                self.assertFalse((self.state / assets.STATE_FILE).exists())

    def test_guard_unavailable_keeps_earlier_unconfirmed_intent(self):
        self.api.fail_after = ("tool", "ees_demo_data")
        self.expect_error("asset_apply_failed")
        journal = self.state / assets.STATE_FILE
        before = journal.read_bytes()
        self.api.capabilities = None
        error = self.expect_error("conditional_write_unavailable")
        self.assertTrue(error.pending)
        self.assertEqual(before, journal.read_bytes())

    def test_all_mutations_use_conditional_api_and_keep_tokens_out_of_journal(self):
        self.apply()
        posts = [(path, body) for method, path, body in self.api.calls if method == "POST"]
        self.assertTrue(posts)
        self.assertTrue(all(path in {assets.ASSET_API + "/snapshot", assets.ASSET_API + "/apply"}
                            for path, _ in posts))
        journal = (self.state / assets.STATE_FILE).read_text(encoding="utf-8")
        for path, body in posts:
            if path.endswith("/apply"):
                self.assertNotIn(body["expected_token"], journal)
                self.assertNotIn("UserValves", body)
        self.assertNotIn("expected_token", journal)

    def test_supported_description_change_after_final_snapshot_is_never_overwritten(self):
        self.apply()
        source = self.root / "agent-pack/data.py"
        source.write_text(source.read_text(encoding="utf-8") + "\n# next source\n", encoding="utf-8")
        before = json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))
        self.api.calls.clear()
        def edit(kind, identifier):
            if (kind, identifier) == ("tool", "ees_demo_data"):
                self.api.rows[(kind, identifier)]["meta"]["description"] = "현장 수정 최신 설명"
        self.api.before_conditional_write = edit
        error = self.expect_error("concurrent_edit")
        self.assertEqual(0, error.changed)
        self.assertFalse(error.pending)
        self.assertEqual("현장 수정 최신 설명", self.api.rows[("tool", "ees_demo_data")]["meta"]["description"])
        self.assertEqual(before, json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8")))
        self.assertEqual(1, len(self.api.writes))  # One rejected request; no token refresh/retry.
        self.assertEqual("EES 합성 데이터 시연", self.api.writes[0][2]["meta"]["description"])
        self.assertFalse(any(path.endswith("/update") for _, path, _ in self.api.calls))

    def test_new_id_collision_after_snapshot_is_not_adopted_or_overwritten(self):
        inserted = {"id": "ees_demo_data", "name": "현장 자산", "content": "local source",
                    "meta": {"description": "keep"}, "access_grants": [], "user_id": "local-owner"}
        def create(kind, identifier):
            if (kind, identifier) == ("tool", "ees_demo_data"):
                self.api.rows[(kind, identifier)] = copy.deepcopy(inserted)
        self.api.before_conditional_write = create
        error = self.expect_error("concurrent_edit")
        self.assertFalse(error.pending)
        self.assertEqual(0, error.changed)
        self.assertEqual(inserted, self.api.rows[("tool", "ees_demo_data")])
        self.assertNotIn("tool:ees_demo_data", json.loads((self.state / assets.STATE_FILE).read_text(encoding="utf-8"))["assets"])

    def test_parent_tool_change_after_own_success_cannot_refresh_valve_token(self):
        def edit(kind, identifier):
            if (kind, identifier) == ("valves", "ees_demo_data"):
                self.api.rows[("tool", identifier)]["content"] += "\n# local parent edit\n"
        self.api.before_conditional_write = edit
        error = self.expect_error("concurrent_edit")
        self.assertEqual(1, error.changed)
        self.assertFalse(error.pending)
        self.assertNotIn("ees_demo_data", self.api.valves)
        self.assertTrue(self.api.rows[("tool", "ees_demo_data")]["content"].endswith("# local parent edit\n"))
        self.assertEqual(2, len(self.api.writes))

    def test_common_valves_edit_conflicts_with_parent_tool_update(self):
        self.apply()
        source = self.root / "agent-pack/data.py"
        source.write_text(source.read_text(encoding="utf-8") + "\n# new version\n", encoding="utf-8")
        original = self.api.rows[("tool", "ees_demo_data")]["content"]
        def edit(kind, identifier):
            if (kind, identifier) == ("tool", "ees_demo_data"):
                self.api.valves[identifier]["timeout_seconds"] = 999
        self.api.before_conditional_write = edit
        self.assertEqual(0, self.expect_error("concurrent_edit").changed)
        self.assertEqual(999, self.api.valves["ees_demo_data"]["timeout_seconds"])
        self.assertEqual(original, self.api.rows[("tool", "ees_demo_data")]["content"])

    def test_own_tool_snapshot_does_not_refresh_other_targets(self):
        self.apply()
        (self.root / "agent-pack/data.py").write_text((self.root / "agent-pack/data.py").read_text(encoding="utf-8") + "\n# update\n", encoding="utf-8")
        (self.root / "agent-pack/apc.md").write_text("새 APC 지침", encoding="utf-8")
        def edit(kind, identifier):
            if (kind, identifier) == ("tool", "ees_demo_data"):
                self.api.rows[("model", "ees-demo-apc")]["params"]["temperature"] = 0.9
        self.api.after_conditional_write = edit
        error = self.expect_error("concurrent_edit")
        self.assertEqual(1, error.changed)
        self.assertEqual(0.9, self.api.rows[("model", "ees-demo-apc")]["params"]["temperature"])
        self.assertNotIn("새 APC 지침", self.api.rows[("model", "ees-demo-apc")]["params"]["system"])

    def test_unknown_assets_and_supported_links_remain_available_after_update(self):
        custom = {"id": "jira_real", "name": "현장 조회", "content": "def query(): return 'local'",
                  "meta": {"description": "사용자 작성 도구"}, "access_grants": [read_grant()], "user_id": "local-owner"}
        self.api.rows[("tool", "jira_real")] = copy.deepcopy(custom)
        self.api.valves["jira_real"] = {"timeout_seconds": 23}
        self.api.rows[("skill", "policy")] = {"id": "policy", "content": "사용자 정책"}
        untouched = copy.deepcopy(self.api.rows[("skill", "policy")])
        self.apply()
        self.assertEqual(custom, self.api.request("GET", "/api/v1/tools/id/jira_real"))
        self.assertEqual({"timeout_seconds": 23}, self.api.request("GET", "/api/v1/tools/id/jira_real/valves"))
        self.assertEqual(untouched, self.api.rows[("skill", "policy")])
        model = self.api.request("GET", "/api/v1/models/model?id=existing-ees")
        self.assertIn("jira_real", model["meta"]["toolIds"])
        self.assertIn("policy", model["meta"]["skillIds"])
        self.assertTrue(all(body["id"] != "jira_real" for _, path, body in self.api.calls
                            if path == assets.ASSET_API + "/apply"))

    def test_concurrent_edit_not_overwritten(self):
        self.api.concurrent = ("model", "existing-ees")
        self.expect_error("concurrent_edit")
        self.assertTrue(self.api.rows[("model", "existing-ees")]["params"]["system"].endswith("동시 편집"))

    def test_untracked_region_is_not_adopted(self):
        self.api.rows[("model", "existing-ees")]["params"]["system"] += assets.BEGIN + assets.END
        self.expect_error("untracked_managed_region")
        self.assertEqual([], self.api.writes)

    def test_user_suggestion_with_same_content_is_not_silently_replaced(self):
        self.api.rows[("model", "existing-ees")]["meta"]["suggestion_prompts"].append(
            {"title": ["내가 만든", "제목"], "content": self.manifest["ees"]["suggestions"][0]["content"]})
        self.expect_error("suggestion_collision")
        self.assertEqual([], self.api.writes)

    def test_tool_source_not_visible_stops_before_changes(self):
        self.apply()
        count = len(self.api.writes)
        self.api.hide_content = True
        self.expect_error("tool_source_not_readable")
        self.assertEqual(count, len(self.api.writes))

    def test_redacted_admin_model_response_cannot_erase_existing_prompt(self):
        previous = copy.deepcopy(self.api.rows[("model", "existing-ees")])
        self.api.redact_model = True
        self.expect_error("model_write_access_required")
        self.assertEqual([], self.api.writes)
        self.assertEqual(previous, self.api.rows[("model", "existing-ees")])

    def test_public_anyone_grant_is_preserved_without_write_expansion(self):
        self.api.rows[("model", "existing-ees")]["access_grants"] = [
            {"principal_type": "anyone", "principal_id": "*", "permission": "read"}]
        self.apply()
        grants = assets._grants(self.api.rows[("model", "ees-demo-ems")]["access_grants"])
        self.assertIn({"principal_type": "anyone", "principal_id": "*", "permission": "read"}, grants)
        self.assertTrue(all(g["permission"] == "read" for g in grants))


if __name__ == "__main__":
    unittest.main()
