"""The split release gate must not silently lose old checks or failures."""
import importlib.util
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("delivery_suite_under_test", Path(__file__).with_name("ees_delivery_suite.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class DeliveryCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.baseline = self.root / "baseline.json"
        self.old_id = "test_old.Before.test_permission"
        self.current_id = "test_new.After.test_permission"
        (self.root / "test_new.py").write_text("class After:\n    def test_permission(self): pass\n", encoding="utf-8")
        self.data = {"source_commit": "synthetic-baseline", "modules": {"test_old.py": [self.old_id]},
                     "node_scripts": [], "replacements": {}}
        self.scope = patch.multiple(runner, TESTS=self.root, BASELINE=self.baseline,
                                    SUITES={"services": ["test_*.py"]}, NODE_SCRIPTS={})
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def audit(self):
        self.baseline.write_text(json.dumps(self.data), encoding="utf-8")
        return runner.audit()

    def test_deleted_protection_without_replacement_fails(self):
        self.assertEqual(self.audit()["errors"], ["Unclassified removed test: " + self.old_id])

    def test_named_replacement_must_exist_and_explain_retained_protection(self):
        self.data["replacements"][self.old_id] = {"classification": "replaced-ui",
            "reason": "Changed selectors; same cross-user access denial is asserted", "tests": [self.current_id]}
        self.assertEqual(self.audit()["errors"], [])
        self.data["replacements"][self.old_id]["tests"] = ["test_missing.No.test_fake"]
        self.assertTrue(self.audit()["errors"])

    def test_mapped_node_protection_must_exist_in_required_script(self):
        self.data["replacements"][self.old_id] = {"classification":"replaced-ui", "reason":"Retain the named isolation check",
            "tests":[self.current_id], "node_scripts":["test_contract.cjs"], "node_tests":["private isolation"]}
        (self.root / "test_contract.cjs").write_text("test('different check',()=>{});",encoding="utf-8")
        with patch.object(runner, "NODE_SCRIPTS", {"services":["test_contract.cjs"]}):
            self.assertIn("Missing mapped JavaScript test: private isolation", self.audit()["errors"])
            (self.root / "test_contract.cjs").write_text("test('private isolation',()=>{});",encoding="utf-8")
            self.assertEqual(self.audit()["errors"], [])

    def test_retained_module_must_run_in_exactly_one_shard(self):
        (self.root / "test_old.py").write_text("class Before:\n    def test_permission(self): pass\n", encoding="utf-8")
        with patch.object(runner, "SUITES", {"services": ["test_*.py"], "platform": ["test_old.py"]}):
            self.assertEqual(self.audit()["errors"], ["Expected exactly one suite: test_old.py"])

    def test_new_unassigned_module_is_rejected(self):
        self.data["modules"] = {}
        with patch.object(runner, "SUITES", {"services": ["test_old.py"]}):
            self.assertEqual(self.audit()["errors"], ["Expected exactly one suite: test_new.py"])

    def test_case_partitions_assign_every_current_id_once_and_reject_overlap_or_unknown(self):
        filename = "test_partition.py"
        self.write_partition(filename)
        self.data["modules"] = {}
        real = "test_partition.Check.test_real"
        partitions = {filename: {"services": None, "restore": [real]}}
        with patch.object(runner, "CASE_PARTITIONS", partitions), patch.object(runner, "SUITES", {
                "services": ["test_*.py"], "restore": [filename]}):
            self.assertEqual(self.audit()["errors"], [])
            self.assertEqual(runner.partition_ids(filename, "services"), {"test_partition.Check.test_general"})
            self.assertEqual(runner.partition_ids(filename, "restore"), {real})
            partitions[filename]["services"] = [real]
            self.assertIn("Expected exactly one partition per test ID: " + filename, self.audit()["errors"])
            partitions[filename]["services"] = None
            partitions[filename]["restore"] = [real + "_removed"]
            self.assertIn("Empty or unknown test partition: " + filename + ": restore", self.audit()["errors"])

    def write_partition(self, filename):
        (self.root / filename).write_text(
            "import unittest\nclass Check(unittest.TestCase):\n"
            "    def test_general(self): self.assertTrue(True)\n"
            "    def test_real(self): self.assertTrue(True)\n", encoding="utf-8")

    def test_partition_runtime_collection_is_exact_and_cannot_hide_missing_tests(self):
        filename = "test_partition_runtime.py"
        self.write_partition(filename)
        real = "test_partition_runtime.Check.test_real"
        partitions = {filename: {"services": None, "restore": [real]}}
        result_file = self.root / "partition.json"
        with patch.object(runner, "CASE_PARTITIONS", partitions), redirect_stderr(io.StringIO()):
            self.assertEqual(runner.run_module(filename, result_file, "restore"), 0)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(result["tests_run"], 1)
            self.assertEqual(result["outcomes"], [{"id": real, "status": "passed"}])
            partitions[filename]["restore"] = [real + "_missing"]
            self.assertEqual(runner.run_module(filename, result_file, "restore"), 1)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "failed")
            self.assertIn("does not exactly match", result["error"])

    def test_skipped_evidence_is_incomplete_not_passed(self):
        (self.root / "test_skip.py").write_text(
            "import unittest\nclass Check(unittest.TestCase):\n"
            "    @unittest.skip('synthetic unavailable platform')\n"
            "    def test_unavailable(self): pass\n", encoding="utf-8")
        result_file = self.root / "skip.json"
        with redirect_stderr(io.StringIO()):
            runner.run_module("test_skip.py", result_file)
        result = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["counts"]["skipped"], 1)
        self.assertEqual(result["counts"]["passed"], 0)

    def test_empty_runtime_collection_cannot_pass(self):
        (self.root / "test_empty.py").write_text("# No runtime tests\n", encoding="utf-8")
        result_file=self.root / "empty.json"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(runner.run_module("test_empty.py", result_file),1)
        result=json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["tests_run"],0)

    def test_subtest_failure_remains_failure_in_json_evidence(self):
        (self.root / "test_subtest.py").write_text(
            "import unittest\nclass Check(unittest.TestCase):\n"
            "    def test_checks(self):\n        with self.subTest(case='boundary'):\n            self.assertEqual(1, 2)\n",
            encoding="utf-8")
        result_file = self.root / "result.json"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(runner.run_module("test_subtest.py", result_file), 1)
        result = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertFalse(result["no_test_failures"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["outcomes"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
