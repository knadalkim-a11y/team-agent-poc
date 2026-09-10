"""Offline preservation, partial-write recovery and conflict tests for ApplyDemo."""
import ast
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "ees_demo_assets.py"
spec = importlib.util.spec_from_file_location("ees_demo_assets", MODULE)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def read_grant(principal="team"):
    return {"principal_type": "group", "principal_id": principal, "permission": "read"}


class FakeAPI:
    """Models API whole-field replacement + tools frontmatter/grant normalization."""
    def __init__(self):
        self.rows = {("model", "existing-ees"): {
            "id": "existing-ees", "user_id": "original-owner", "name": "EES 통합 Assistant",
            "base_model_id": "internal-llm", "is_active": True,
            "params": {"system": "사내 공통 정책\n사용자 추가 지침", "temperature": 0.2,
                       "function_calling": "legacy"},
            "meta": {"toolIds": ["jira_real", "wo_demo"], "skillIds": ["policy"],
                     "knowledge": [{"id": "manual"}], "custom": {"keep": True},
                     "capabilities": {"memory": True},
                     "suggestionPrompts": [{"title": ["기존", "업무"], "content": "기존 질문"}]},
            "access_grants": [read_grant(), {"principal_type": "user", "principal_id": "editor",
                                              "permission": "write"}]}}
        self.valves, self.calls = {}, []
        self.fail_before, self.fail_after, self.fail_read = None, None, None
        self.drop_grants = False
        self.hide_content = False
        self.redact_model = False
        self.concurrent = None
        self.valve_defaults = None

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
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
                reads = sum(1 for m, p, _ in self.calls if m == "GET" and p == path)
                if reads == 2:
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
        return [call for call in self.calls if call[0] == "POST"]


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
        model["meta"]["suggestionPrompts"].append({"title": ["사용자", "추가"], "content": "추가 질문"})
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
        self.assertIn("추가 질문", [s["content"] for s in model["meta"]["suggestionPrompts"]])
        self.assertEqual(150, self.api.valves["ees_demo_data"]["timeout_seconds"])

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
                    model["meta"]["suggestionPrompts"][-1]["title"] = ["수정", "제목"]
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
            if method == "POST":
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
        self.assertEqual("0.1.2", manifest["version"])
        self.assertEqual({"ees_specialists", "ees_demo_data"}, {t["id"] for t in manifest["tools"]})
        self.assertEqual({"ees_demo_ems", "ees_demo_apc", "ees_demo_fdc"},
                         {m["id"] for m in manifest["models"]})
        for tool in manifest["tools"]:
            script = (MODULE.parents[1] / tool["ui_script_path"]).read_text(encoding="utf-8")
            original = (MODULE.parents[1] / tool["path"]).read_text(encoding="utf-8")
            tree = ast.parse(tool["content"])
            panel = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "PANEL_SCRIPT"
                             for target in node.targets)]
            self.assertEqual([script], panel)
            self.assertEqual(ast.get_docstring(ast.parse(original), clean=False),
                             ast.get_docstring(tree, clean=False))
            compile(tool["content"], tool["path"], "exec")

    def test_concurrent_edit_not_overwritten(self):
        self.api.concurrent = ("model", "existing-ees")
        self.expect_error("concurrent_edit")
        self.assertTrue(self.api.rows[("model", "existing-ees")]["params"]["system"].endswith("동시 편집"))

    def test_untracked_region_is_not_adopted(self):
        self.api.rows[("model", "existing-ees")]["params"]["system"] += assets.BEGIN + assets.END
        self.expect_error("untracked_managed_region")
        self.assertEqual([], self.api.writes)

    def test_user_suggestion_with_same_content_is_not_silently_replaced(self):
        self.api.rows[("model", "existing-ees")]["meta"]["suggestionPrompts"].append(
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
