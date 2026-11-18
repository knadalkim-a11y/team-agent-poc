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
        with patch.object(runner, "SUITES", {"services": ["test_old*.py"]}):
            self.assertEqual(self.audit()["errors"], ["Expected exactly one suite: test_new.py"])

    def test_missing_explicit_module_fails_even_without_baseline_ids(self):
        self.data['modules'] = {}
        filename = 'test_required.py'
        required = self.root / filename
        with patch.object(runner, 'SUITES', {'services': ['test_new.py', filename, 'test_optional*.py']}):
            expected = ['Missing required Python test module: ' + filename]
            self.assertEqual(self.audit()['errors'], expected)
            required.mkdir()
            # An unreadable module path already fails during source parsing;
            # it must not be mistaken for a runnable module or a passing audit.
            with self.assertRaises(OSError):
                self.audit()
            required.rmdir()
            required.write_text('class Required:\n    def test_protection(self): pass\n', encoding='utf-8')
            self.assertEqual(self.audit()['errors'], [])
            self.assertIn(filename, runner.selected('services'))

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


class DeliveryPlanTests(unittest.TestCase):
    """Which jobs a run executes, and when a run may count as the release gate."""

    def test_pull_request_runs_only_the_quick_source_checks(self):
        result = runner.plan("full", "native-compose", event="pull_request", ref="refs/pull/7/merge")
        self.assertEqual(result["scope"], "quick")
        self.assertEqual([job for job, value in result["runs"].items() if value], ["quick"])
        self.assertEqual(result["expected"]["quick"], "success")
        self.assertEqual(set(result["expected"].values()), {"success", "skipped"})
        self.assertEqual(result["check"], {"os": [runner.LINUX]})
        self.assertFalse(result["package"])

    def test_full_scope_keeps_every_suite_on_both_systems_and_alone_packages(self):
        result = runner.plan("full", ref="refs/heads/main")
        self.assertTrue(result["package"])
        self.assertEqual(result["check"], {"os": [runner.LINUX, runner.WINDOWS]})
        self.assertEqual(result["expected"], dict.fromkeys(runner.JOBS, "success") | {"quick": "skipped"})
        rows = result["service"]["include"]
        self.assertEqual({(row["os"], row["suite"]) for row in rows},
                         {(system, suite) for system in (runner.LINUX, runner.WINDOWS) for suite in runner.SERVICE_FIXTURES})
        self.assertEqual(len(rows), 14)
        by_key = {(row["os"], row["suite"]): row for row in rows}
        self.assertEqual(by_key[(runner.WINDOWS, "platform")]["fixtures"], "upstream legacy")
        self.assertEqual(by_key[(runner.LINUX, "platform")]["fixtures"], "upstream")
        self.assertEqual(by_key[(runner.WINDOWS, "contracts")]["timeout"], 15)
        self.assertEqual({row["timeout"] for key, row in by_key.items() if key != (runner.WINDOWS, "contracts")}, {10})
        self.assertEqual(result["native"], {"suite": list(runner.NATIVE_SUITES)})
        self.assertEqual(result["audit"], {"os": [runner.LINUX, runner.WINDOWS]})

    def test_every_suite_is_reachable_and_every_fixture_is_declared(self):
        scheduled = set(runner.SERVICE_FIXTURES) | set(runner.NATIVE_SUITES)
        self.assertEqual(scheduled, set(runner.SUITES))
        for fixtures in list(runner.SERVICE_FIXTURES.values()) + list(runner.WINDOWS_FIXTURES.values()):
            self.assertIn("upstream", fixtures.split())
            self.assertLessEqual(set(fixtures.split()), {"upstream", "legacy", "previous"})
        for name in runner.QUICK_SUITES:
            self.assertIn(name, runner.SUITES)
        for filename in runner.QUICK_MODULES:
            self.assertTrue((Path(__file__).parent / filename).is_file(), filename)

    def test_partial_scopes_never_package_and_run_only_their_part(self):
        browser = runner.plan("browser")
        self.assertEqual([job for job, value in browser["runs"].items() if value],
                         ["source-frontend", "upstream-fixture", "fixtures", "native", "native-product"])
        windows = runner.plan("windows")
        self.assertEqual({row["os"] for row in windows["service"]["include"]}, {runner.WINDOWS})
        self.assertFalse(windows["runs"]["native"] or windows["runs"]["native-product"])
        self.assertEqual(windows["audit"], {"os": [runner.WINDOWS]})
        linux = runner.plan("linux")
        self.assertEqual({row["os"] for row in linux["service"]["include"]}, {runner.LINUX})
        self.assertTrue(linux["runs"]["native"] and linux["runs"]["native-product"])
        for result in (browser, windows, linux, runner.plan("quick"), runner.plan("full", "platform")):
            self.assertFalse(result["package"])
            self.assertEqual(result["check"], {"os": [runner.LINUX]})

    def test_named_suites_narrow_a_scope_and_unknown_or_absent_names_are_refused(self):
        result = runner.plan("linux", "native-compose program-install")
        self.assertEqual([(row["os"], row["suite"]) for row in result["service"]["include"]], [(runner.LINUX, "program-install")])
        self.assertEqual(result["native"], {"suite": ["native-compose"]})
        self.assertFalse(result["runs"]["native-product"] or result["runs"]["audit"])
        self.assertTrue(result["runs"]["historical-fixtures"])
        only_product = runner.plan("browser", "native-product")
        self.assertTrue(only_product["runs"]["native-product"])
        self.assertFalse(only_product["runs"]["native"] or only_product["runs"]["historical-fixtures"])
        for scope, suites in (("windows", "native-compose"), ("browser", "platform"), ("full", "typo"),
                              ("quick", "services"), ("everything", "")):
            with self.assertRaises(runner.PlanError, msg=(scope, suites)):
                runner.plan(scope, suites)

    def test_main_refuses_partial_runs_so_a_success_there_is_always_the_full_gate(self):
        for scope, suites in (("quick", ""), ("browser", ""), ("linux", ""), ("windows", ""), ("full", "platform")):
            with self.assertRaises(runner.PlanError, msg=(scope, suites)):
                runner.plan(scope, suites, ref="refs/heads/main")
        self.assertEqual(runner.plan("browser", ref="refs/heads/topic")["scope"], "browser")

    def test_outputs_are_single_lines_and_idle_matrices_stay_well_formed(self):
        lines = dict(line.split("=", 1) for line in runner.plan_outputs(runner.plan("quick")))
        self.assertEqual(lines["run_quick"], "true")
        self.assertEqual(lines["run_native_product"], "false")
        self.assertEqual(lines["package"], "false")
        for name in ("service", "native", "audit", "check", "expected"):
            self.assertNotIn("\n", lines[name])
            self.assertTrue(json.loads(lines[name]))
        self.assertEqual(json.loads(lines["native"]), {"suite": ["none"]})
        self.assertEqual(json.loads(lines["service"])["include"][0]["suite"], "none")
        full = dict(line.split("=", 1) for line in runner.plan_outputs(runner.plan("full")))
        self.assertEqual(len(json.loads(full["service"])["include"]), 14)

    def test_result_check_requires_exactly_the_planned_outcome(self):
        expected = runner.plan("browser")["expected"]
        needs = {job: {"result": outcome} for job, outcome in expected.items()} | {"plan": {"result": "success"}}
        self.assertEqual(runner.check_results(expected, needs), [])
        for job, outcome in (("native", "failure"), ("native", "cancelled"), ("native", "skipped"),
                             ("service", "success"), ("plan", "failure")):
            changed = dict(needs, **{job: {"result": outcome}})
            self.assertTrue(runner.check_results(expected, changed), (job, outcome))
        self.assertTrue(runner.check_results(expected, {key: value for key, value in needs.items() if key != "fixtures"}))
        self.assertTrue(runner.check_results({}, needs))
        self.assertTrue(runner.check_results({"quick": "success"}, needs))

    def test_packaging_states_its_required_results_because_quick_is_skipped_in_full(self):
        # Run 583: every check passed but the ZIP job was skipped. GitHub skips
        # a job that relies on the default success check when any ancestor,
        # here the quick job behind the final check, was skipped.
        workflow = (Path(__file__).parents[1] / ".github/workflows/ees-delivery.yml").read_text(encoding="utf-8")
        package = workflow.split("\n  package:\n", 1)[1]
        condition = next(line.strip() for line in package.splitlines() if line.strip().startswith("if:"))
        for required in ("!cancelled()", "needs.plan.outputs.package == 'true'", "needs.check.result == 'success'"):
            self.assertIn(required, condition)
        self.assertEqual(runner.plan("full")["expected"]["quick"], "skipped")
        # Every other job only follows jobs that run whenever it runs.
        ancestors = {"quick": [], "audit": [], "source-frontend": [], "upstream-fixture": [],
                     "historical-fixtures": ["upstream-fixture"], "fixtures": ["source-frontend", "upstream-fixture"],
                     "service": ["fixtures", "historical-fixtures"], "native": ["fixtures"], "native-product": ["fixtures"]}
        self.assertEqual(set(ancestors), set(runner.JOBS))
        for job, needed in ancestors.items():
            line = "\n  " + job + ":\n"
            self.assertIn(line, workflow)
            declared = workflow.split(line, 1)[1].split("\n    needs: ", 1)[1].splitlines()[0]
            self.assertEqual(declared.strip("[]").replace(" ", "").split(","), (["plan"] + needed) if needed else ["plan"], job)
        for scope, suites in (("quick", ""), ("browser", ""), ("browser", "native-product"), ("linux", ""),
                              ("linux", "program-install"), ("windows", ""), ("full", ""), ("full", "native-work")):
            runs = runner.plan(scope, suites)["runs"]
            for job, needed in ancestors.items():
                if runs[job]:
                    self.assertTrue(all(runs[name] for name in needed), (scope, suites, job))


if __name__ == "__main__":
    unittest.main()
