"""Pure draft checking: declarations are data and never executable code."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tool_draft_check_tests", ROOT / "agent-pack/skills/ees-work-demo/scripts/ees_workflow_tool_draft_check.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class ToolDraftCheckTests(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((ROOT / "tests/fixtures/tools_phase1_contract.json").read_text(encoding="utf-8"))["draft"]

    def check(self, draft=None):
        return CHECKER.check_draft(self.draft if draft is None else draft)

    def codes(self, result):
        return {error["code"] for error in result["errors"]}

    def ui(self, name="값", widget="text", **extra):
        return dict(label=name, question="어떤 값인가요?", widget=widget, option_labels={}, **extra)

    def test_shared_fixture_is_valid_and_private_injection_is_not_a_question(self):
        result = self.check()
        self.assertTrue(result["valid"], result)
        expected = {"type": "object", "properties": {"doc_types": {"type": "array", "items": {
            "type": "string", "enum": ["design_doc", "test_result", "deployment_plan"]}}}, "required": ["doc_types"]}
        self.assertEqual(result["input_schema"], expected)
        self.assertEqual(result["functions"], [{"name": "list_documents", "input_schema": expected}])

    def test_never_runs_top_level_class_body_or_function_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "must-not-exist"
            expression = "__import__('pathlib').Path(" + repr(str(marker)) + ").write_text('executed')"
            self.draft["code"] = expression + "\n" + self.draft["code"].replace("class Tools:", "class Tools:\n    marker = " + expression)
            result = self.check()
            self.assertTrue(result["valid"], result)
            self.assertFalse(marker.exists())
            self.draft["code"] = "class Tools:\n    def list_documents(self, target: str = " + expression + "):\n        pass\n"
            self.draft["input_ui"] = {"target": self.ui()}
            self.assertIn("input_declaration_unsupported", self.codes(self.check()))
            self.assertFalse(marker.exists())

    def test_syntax_error_reports_line_without_echoing_code(self):
        self.draft["code"] = "class Tools:\n    secret = 'do-not-echo-secret'\n    def broken(\n"
        result = self.check()
        self.assertFalse(result["valid"])
        self.assertIn("code_syntax", self.codes(result))
        self.assertTrue(next(item for item in result["errors"] if item["code"] == "code_syntax")["line"] >= 1)
        self.assertNotIn("do-not-echo-secret", json.dumps(result))

    def test_qualified_aliases_optional_and_literal_defaults(self):
        self.draft["code"] = """import typing as t
from typing import Optional as Maybe, Literal as Choice
Kind = Choice["a", "b"]
class Tools:
    class UserValves: pass
    def list_documents(self, labels: t.List[Kind], count: int = 2, enabled: bool = True, note: Maybe[str] = None, rate: float = -1.5, __event_emitter__=None):
        return {}
"""
        self.draft["input_ui"] = {"labels": self.ui(widget="multiselect", default=[]), "count": self.ui(widget="number", default=2),
                                  "enabled": self.ui(widget="boolean", default=True), "note": self.ui(default=None), "rate": self.ui(widget="number", default=-1.5)}
        result = self.check()
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["input_schema"]["required"], ["labels"])
        self.assertEqual(result["input_schema"]["properties"]["note"], {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None})

    def test_builtin_generic_and_forward_annotation(self):
        self.draft["code"] = "from typing import Literal\nclass Tools:\n    def list_documents(self, choices: \"list[Literal['x']]\"):\n        return {}\n"
        self.draft["input_ui"] = {"choices": self.ui(widget="multiselect", default=["x"])}
        self.assertTrue(self.check()["valid"])

    def test_unknown_input_enum_value_and_default_do_not_silently_change_code(self):
        original = deepcopy(self.draft)
        self.draft["input_ui"]["doc_types"]["option_labels"]["invented"] = "새 값"
        self.draft["input_ui"]["doc_types"]["default"] = ["invented"]
        result = self.check()
        self.assertIn("input_option_unknown", self.codes(result))
        self.assertIn("input_default_mismatch", self.codes(result))
        self.assertEqual(self.draft["code"], original["code"])

    def test_input_removed_from_code_has_a_located_diagnostic(self):
        self.draft["code"] = "class Tools:\n    def list_documents(self):\n        return {}\n"
        result = self.check()
        self.assertIn({"code": "input_unknown", "message": "기능에 없는 입력 질문입니다. 기능과 질문을 함께 확인해 주세요.", "field": "input_ui.doc_types"}, result["errors"])

    def test_missing_question_and_wrong_widget_are_diagnostics(self):
        self.draft["input_ui"]["doc_types"].update(question="", widget="number")
        self.assertTrue({"input_label_required", "input_widget_mismatch"} <= self.codes(self.check()))

    def test_dynamic_and_unimported_types_are_not_guessed(self):
        for prefix, annotation in [("", "Unknown"), ("", "List[str]"), ("from elsewhere import List\n", "List[str]"),
                                   ("str = make_type()\n", "str"), ("Alias = str\ndef Alias(): pass\n", "Alias")]:
            with self.subTest(annotation=annotation, prefix=prefix):
                self.draft["code"] = prefix + "class Tools:\n    def list_documents(self, value: " + annotation + "):\n        pass\n"
                self.draft["input_ui"] = {"value": self.ui()}
                self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def test_cycle_and_dynamic_annotation_are_safe_errors(self):
        for annotation, prefix in [("Loop", "Loop = Loop\n"), ("factory()", ""), ("dict[str, str]", "")]:
            with self.subTest(annotation=annotation):
                self.draft["code"] = prefix + "class Tools:\n    def list_documents(self, value: " + annotation + "):\n        pass\n"
                self.draft["input_ui"] = {"value": self.ui()}
                self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def test_decorated_rebound_and_variadic_methods_are_diagnosed(self):
        for code, expected in [("class Tools:\n    @decorate\n    def list_documents(self): pass\n", "function_dynamic"),
                               ("class Tools:\n    def list_documents(self): pass\n    list_documents = other\n", "function_dynamic"),
                               ("class Tools:\n    def list_documents(self, **kwargs): pass\n", "arguments_unsupported")]:
            with self.subTest(expected=expected):
                self.draft["code"] = code
                self.draft["input_ui"] = {}
                self.assertIn(expected, self.codes(self.check()))

    def test_inherited_or_decorated_tools_class_does_not_claim_static_success(self):
        for code in ["@decorate\nclass Tools:\n    def list_documents(self): pass", "class Tools(Base):\n    def list_documents(self): pass"]:
            with self.subTest(code=code):
                self.draft["code"] = code
                self.draft["input_ui"] = {}
                self.assertIn("tools_class_dynamic", self.codes(self.check()))

    def test_only_selected_public_function_declarations_determine_input_errors(self):
        self.draft["code"] += "    def unused(self, value: Unsupported): pass\n    def _private(self, value): pass\n"
        result = self.check()
        self.assertTrue(result["valid"], result)
        self.assertEqual([item["name"] for item in result["functions"]], ["list_documents", "unused"])
        self.draft["function"] = "unused"
        self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def test_missing_or_duplicate_function_is_diagnosed(self):
        self.draft["function"] = "not_found"
        self.assertIn("function_selection", self.codes(self.check()))
        self.draft["function"] = "list_documents"
        self.draft["code"] += "    def list_documents(self): pass\n"
        self.assertIn("function_duplicate", self.codes(self.check()))

    def test_output_definition_checks_paths_roles_and_duplicates(self):
        self.draft["output_ui"]["fields"] += [deepcopy(self.draft["output_ui"]["fields"][0])]
        self.draft["output_ui"]["fields"][1].update(path="documents[0]", role="html")
        self.assertTrue({"output_field_path", "output_field_display", "output_field_duplicate"} <= self.codes(self.check()))

    def test_output_is_not_assumed_to_be_a_real_runtime_response(self):
        self.draft["code"] = self.draft["code"].replace('return {"documents": []}', "return service_response()")
        result = self.check()
        self.assertTrue(result["valid"], result)
        self.assertNotIn("output_schema", result)

    def test_malformed_draft_fields_return_diagnostics_instead_of_throwing(self):
        self.assertFalse(self.check(["invalid"])["valid"])
        for change in [{"input_ui": []}, {"input_ui": {"doc_types": {"widget": [], "label": "값", "question": "질문"}}},
                       {"output_ui": {"kind": "list", "path": [], "fields": [{"path": "x", "label": "x", "role": {}, "hidden": True}]}},
                       {"code": "\x00"}, {"code": "x" * (CHECKER.MAX_CODE_CHARS + 1)}]:
            with self.subTest(change=list(change)):
                draft = deepcopy(self.draft)
                draft.update(change)
                self.assertFalse(self.check(draft)["valid"])

    def test_numeric_defaults_do_not_accept_boolean_as_integer_or_overflow(self):
        self.draft["code"] = "class Tools:\n    def list_documents(self, n: int): pass\n"
        self.draft["input_ui"] = {"n": self.ui(widget="number", default=True)}
        self.assertIn("input_default_mismatch", self.codes(self.check()))
        self.draft["input_ui"]["n"]["default"] = 10 ** 1000
        self.assertTrue(self.check()["valid"])

    def test_conditional_alias_rebinding_does_not_reuse_earlier_literal(self):
        for block in ["if True:\n    DocType = factory()\n", "for value in []:\n    DocType = factory()\n",
                      "try:\n    DocType = factory()\nexcept Exception:\n    pass\n",
                      "DocType, other = factory()\n"]:
            with self.subTest(block=block):
                draft = deepcopy(self.draft)
                draft["code"] = draft["code"].replace("class Tools:", block + "class Tools:")
                self.assertIn("input_declaration_unsupported", self.codes(self.check(draft)))

    def test_later_rebinding_and_class_local_types_are_not_assumed_global(self):
        for suffix, class_change in [("DocType = str\n", "class Tools:"), ("", "class Tools:\n    DocType = str")]:
            with self.subTest(suffix=suffix, class_change=class_change):
                draft = deepcopy(self.draft)
                draft["code"] = draft["code"].replace("class Tools:", class_change) + suffix
                self.assertIn("input_declaration_unsupported", self.codes(self.check(draft)))

    def test_typing_import_rebinding_and_unknown_star_import_are_diagnosed(self):
        for block in ["if True:\n    List = factory()\n", "if True:\n    Literal = factory()\n", "from elsewhere import *\n"]:
            with self.subTest(block=block):
                draft = deepcopy(self.draft)
                draft["code"] = draft["code"].replace("class Tools:", block + "class Tools:")
                self.assertFalse(self.check(draft)["valid"])

    def test_tools_replaced_after_definition_and_conditional_method_rebinding_are_diagnosed(self):
        for code in [self.draft["code"] + "Tools = object\n", self.draft["code"] + "if flag:\n    Tools = other\n",
                     self.draft["code"] + "    if flag:\n        list_documents = other\n"]:
            with self.subTest(code=code):
                draft = deepcopy(self.draft)
                draft["code"] = code
                self.assertTrue({"tools_class_dynamic", "function_dynamic"} & self.codes(self.check(draft)))

    def test_missing_self_cannot_be_treated_as_a_native_instance_method(self):
        self.draft["code"] = "class Tools:\n    def list_documents(value: str): pass\n"
        self.draft["input_ui"] = {"value": self.ui()}
        self.assertIn("function_receiver", self.codes(self.check()))

    def test_builtin_shadowing_in_module_blocks_tuples_and_class_scope_is_rejected(self):
        for prefix, class_prefix in [("if True:\n    str = dict\n", ""), ("str, other = dict, str\n", ""),
                                     ("", "    str = dict\n"), ("", "    def str(self): pass\n")]:
            with self.subTest(prefix=prefix, class_prefix=class_prefix):
                self.draft["code"] = prefix + "class Tools:\n" + class_prefix + "    def list_documents(self, q: str): pass\n"
                self.draft["input_ui"] = {"q": self.ui()}
                self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def test_typing_attribute_assignment_is_not_assumed_to_keep_original_type(self):
        self.draft["code"] = "import typing\ntyping.List = factory()\nclass Tools:\n    def list_documents(self, q: typing.List[str]): pass\n"
        self.draft["input_ui"] = {"q": self.ui(widget="multiselect")}
        self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def test_exception_and_pattern_capture_names_shadow_types(self):
        for block in ["try:\n    pass\nexcept Exception as str:\n    pass\n",
                      "match value:\n    case str:\n        pass\n",
                      "match value:\n    case [*str]:\n        pass\n",
                      "match value:\n    case {**str}:\n        pass\n"]:
            with self.subTest(block=block):
                self.draft["code"] = block + "class Tools:\n    def list_documents(self, q: str): pass\n"
                self.draft["input_ui"] = {"q": self.ui()}
                self.assertIn("input_declaration_unsupported", self.codes(self.check()))

    def assert_definition_limit(self, result):
        self.assertFalse(result["valid"])
        self.assertEqual(self.codes(result), {"definition_limit"})
        self.assertEqual(result["functions"], [])
        self.assertEqual(result["input_schema"], {"type": "object", "properties": {}, "required": []})
        self.assertLessEqual(len(json.dumps(result)), CHECKER.MAX_RESULT_BYTES)

    def test_reviewed_small_source_cannot_amplify_into_megabytes(self):
        choices = [str(index) + "x" * 60 for index in range(500)]
        arguments = ", ".join("arg" + str(index) + ": Choices" for index in range(100))
        self.draft["code"] = "from typing import Literal\nChoices = Literal[" + ", ".join(map(repr, choices)) + "]\nclass Tools:\n    def list_documents(self, " + arguments + "): pass\n"
        self.assertLess(len(self.draft["code"]), 40_000)
        self.assert_definition_limit(self.check())

    def test_function_argument_enum_and_identifier_limits_fail_without_partial_schemas(self):
        for code in ["class Tools:\n" + "".join("    def f" + str(index) + "(self): pass\n" for index in range(33)),
                     "class Tools:\n    def list_documents(self, " + ", ".join("v" + str(index) + ": str" for index in range(33)) + "): pass\n",
                     "from typing import Literal\nclass Tools:\n    def list_documents(self, q: Literal[" + ", ".join(map(str, range(65))) + "]): pass\n",
                     "from typing import Literal\nclass Tools:\n    def list_documents(self, q: Literal['" + "x" * 513 + "']): pass\n",
                     "class Tools:\n    def " + "f" * 129 + "(self): pass\n",
                     "class Tools:\n    def list_documents(self, " + "q" * 129 + ": str): pass\n"]:
            with self.subTest(code=code[:60]):
                self.draft["code"] = code
                self.assert_definition_limit(self.check())

    def test_repeated_aliases_share_a_cumulative_budget_across_functions(self):
        choices = [str(index) + "x" * 100 for index in range(64)]
        prefix = "from typing import Literal\nChoices = Literal[" + ", ".join(map(repr, choices)) + "]\nclass Tools:\n"
        self.draft["code"] = prefix + "".join("    def f" + str(index) + "(self, q: Choices): pass\n" for index in range(8))
        self.draft["function"] = "f0"
        self.draft["input_ui"] = {"q": self.ui(widget="select")}
        self.assertLess(len(self.draft["code"]), 10_000)
        self.assert_definition_limit(self.check())

    def test_large_literal_defaults_are_included_in_schema_budget(self):
        default = repr(["x" * 256] * 120)
        self.draft["code"] = "class Tools:\n    def list_documents(self, a: list[str] = " + default + ", b: list[str] = " + default + "): pass\n"
        self.assert_definition_limit(self.check())

    def test_diagnostic_fields_and_total_envelope_are_bounded(self):
        self.draft["input_ui"] = {"한" * 1_000: {}}
        result = self.check()
        self.assertTrue(all(len(error.get("field", "")) <= 256 for error in result["errors"]))
        self.draft["input_ui"] = {"한" * 256 + str(index): {} for index in range(100)}
        self.assert_definition_limit(self.check())

    def test_deep_binding_visits_return_diagnostics_instead_of_recursion_errors(self):
        expression = "+".join(["0"] * 1_000)
        for code in [expression + "\n" + self.draft["code"], self.draft["code"] + "    " + expression + "\n"]:
            with self.subTest(scope="module" if code.startswith("0") else "class"):
                CHECKER.ast.parse(code)
                self.draft["code"] = code
                self.assert_definition_limit(self.check())


if __name__ == "__main__":
    unittest.main()
