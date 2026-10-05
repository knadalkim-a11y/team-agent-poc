"""Bounded CI suites with complete per-test results and a retained-ID audit.

Each module runs in its own Python process, as in the original workflow. This
avoids sharing Native fixture module replacements across unrelated suites.
The manifest audit rejects unclassified old test IDs; replacements must point
to an existing test and explain the retired behavior/protection carried over.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Executing this file directly sets sys.path[0] to tests/, unlike the original
# `python -m unittest discover` entry. Preserve repository package imports in
# every isolated child process without requiring inherited PYTHONPATH.
sys.path.insert(0, str(ROOT))
TESTS = ROOT / "tests"
BASELINE = TESTS / "ees_delivery_baseline.json"

# Every former workflow module remains selected. Newly implemented contracts
# use explicit prefixes below; an unmatched module is reported by --audit.
SUITES = {
    "services": ["test_confluence*.py", "test_jira_read.py", "test_jira_work_contract.py", "test_github_tool.py",
        "test_ees_work_controller.py", "test_ees_work_panel.py", "test_ees_work_v4.py",
        "test_ees_work_routes.py", "test_ees_work_designer.py", "test_wo_demo_tool.py",
        "test_ees_demo*.py", "test_ees_apply_demo.py", "test_ees_specialists_tool.py",
        "test_ees_execution_tool.py", "test_ees_workflow.py", "test_ees_workflow_contract.py",
        "test_ees_workflow_model.py", "test_ees_workflow_tool.py", "test_ees_integrated*.py",
        "test_ees_work_workspace.py", "test_ees_work_operations.py", "test_ees_delivery_artifacts.py",
        "test_ees_work_figma_authoring.py", "test_ees_work_figma_contracts.py",
        "test_ees_work_figma_schedule.py", "test_ees_work_history_reference.py"],
    "contracts": ["test_ees_workflow_execution.py", "test_ees_workflow_native.py",
        "test_ees_workflow_model_native.py",
        "test_ees_work_authoring.py"],
    "platform": ["test_ees_deploy_*.py", "test_manage_ees.py", "test_ees_upgrade.py",
        "test_ees_update_download.py",
        "test_ees_asset_guard.py", "test_ees_asset_native.py", "test_ees_branding_build.py",
        "test_demo_bundle.py", "test_ees_trial_*.py", "test_ees_delivery_suite.py",
        "test_check_docs.py", "test_openwebui_windows_launcher.py"],
    "program-install": ["test_ees_webui_customization.py"],
    "native-contracts": ["test_ees_workflow_examples_native.py"],
    "restore-ees10": ["test_ees_webui_customization.py"],
    "restore-ees11": ["test_ees_webui_customization.py"],
    "restore-ees12": ["test_ees_webui_customization.py"],
    "native-account": ["test_ees_work_authoring_native.py", "test_ees_work_authoring_account_switch.py",
        "test_ees_chat_theme.py"],
    "native-work": ["test_ees_work_demo.py"],
    "native-compose": ["test_ees_work_c_phase1_native.py", "test_ees_work_c_phase2_native.py",
        "test_ees_work_figma_authoring_native.py", "test_ees_work_figma_runtime_native.py",
        "test_ees_work_figma_layout_native.py"],
    "native-execution": ["test_ees_work_c_phase3_native.py", "test_ees_work_c_phase3_privacy.py"],
}
# Each real fixed-wheel Apply/Restore performs a full filesystem walk. On
# Windows one ees.10 case takes 157 seconds; isolate these cases without
# changing their assertions, artifact pins, or the overall required gate.
# The other 58 methods take 224 seconds on Windows and have their own job.
CASE_PARTITIONS = {
    "test_ees_webui_customization.py": {
        "program-install": None,  # Every remaining/currently added method stays here.
        "restore-ees10": ["test_ees_webui_customization.CustomizationTests.test_real_ees10_to_authoring_apply_restore_preserves_program_and_data"],
        "restore-ees11": ["test_ees_webui_customization.CustomizationTests.test_real_ees11_to_execution_apply_restore_preserves_program_and_data"],
        "restore-ees12": ["test_ees_webui_customization.CustomizationTests.test_real_ees12_visual_revision_apply_restore_preserves_prior_asset_inventory"],
    },
}


NODE_SCRIPTS = {
    "services": ["test_wo_demo_state.cjs", "test_ees_cooperation_panel.cjs", "test_ees_execution_ui.cjs",
                 "test_ees_work_authoring_ui.cjs", "test_ees_v4_layout.cjs", "test_ees_v4_drafts.cjs",
                 "test_ees_work_figma_runtime_ui.cjs"],
}


def selected(suite):
    return sorted(path.name for path in TESTS.glob("test_*.py")
                  if any(fnmatch.fnmatch(path.name, pattern) for pattern in SUITES[suite]))


def declared_ids(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {path.stem + "." + cls.name + "." + method.name
            for cls in tree.body if isinstance(cls, ast.ClassDef)
            for method in cls.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
            and method.name.startswith("test_")}


def partition_ids(filename, suite):
    """Complete disjoint assignment; no platform/runtime-dependent filtering."""
    all_ids = declared_ids(TESTS / filename)
    partitions = CASE_PARTITIONS.get(filename)
    if not partitions:
        return all_ids
    if suite not in partitions:
        raise ValueError("Unassigned module partition: " + filename + ": " + suite)
    assigned = partitions[suite]
    reserved = {item for ids in partitions.values() if ids is not None for item in ids}
    return all_ids - reserved if assigned is None else set(assigned)


def flatten_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten_tests(item)
        else:
            yield item



def audit():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = {identifier for path in TESTS.glob("test_*.py") for identifier in declared_ids(path)}
    assignments = {}
    for suite in SUITES:
        for filename in selected(suite):
            assignments.setdefault(filename, []).append(suite)
    errors, changes = [], []
    # selected() enumerates existing files, so a lost explicitly registered
    # module must be rejected here rather than silently absent from the suite.
    required_modules = {pattern for patterns in SUITES.values() for pattern in patterns
                        if pattern.endswith('.py') and not any(mark in pattern for mark in '*?[')}
    for filename in sorted(required_modules):
        if not (TESTS / filename).is_file():
            errors.append('Missing required Python test module: ' + filename)
    replacements = baseline["replacements"]
    for filename in sorted(path.name for path in TESTS.glob("test_*.py")):
        partitions = CASE_PARTITIONS.get(filename)
        if not partitions:
            if len(assignments.get(filename, [])) != 1:
                errors.append("Expected exactly one suite: " + filename)
            continue
        current_ids = declared_ids(TESTS / filename)
        if set(assignments.get(filename, [])) != set(partitions):
            errors.append("Partition suites differ from required module assignments: " + filename)
        assigned_ids = []
        for suite in partitions:
            ids = partition_ids(filename, suite)
            if not ids or not ids <= current_ids:
                errors.append("Empty or unknown test partition: " + filename + ": " + suite)
            assigned_ids.extend(ids)
        if set(assigned_ids) != current_ids or len(assigned_ids) != len(set(assigned_ids)):
            errors.append("Expected exactly one partition per test ID: " + filename)
    for filename, identifiers in baseline["modules"].items():
        for identifier in identifiers:
            if identifier in current:
                continue
            replacement = replacements.get(identifier)
            if (not replacement or not replacement.get("reason")
                    or replacement.get("classification") not in {"retired-feature", "replaced-ui", "preserved-protection"}
                    or not replacement.get("tests")
                    or any(test not in current for test in replacement["tests"])):
                errors.append("Unclassified removed test: " + identifier)
            else:
                scripts = replacement.get("node_scripts", [])
                names = replacement.get("node_tests", [])
                available_scripts = {name for values in NODE_SCRIPTS.values() for name in values}
                sources = []
                for script in scripts:
                    path = TESTS / script
                    if script not in available_scripts or not path.is_file():
                        errors.append("Unassigned mapped JavaScript script: " + script)
                    else:
                        sources.append(path.read_text(encoding="utf-8"))
                for name in names:
                    if not any(name in source for source in sources):
                        errors.append("Missing mapped JavaScript test: " + name)
                changes.append({"old": identifier, **replacement})
    for scripts in NODE_SCRIPTS.values():
        for filename in scripts:
            if not (TESTS / filename).is_file():
                errors.append("Missing required JavaScript test: " + filename)
    for original in baseline["node_scripts"]:
        if Path(original).name not in {name for names in NODE_SCRIPTS.values() for name in names}:
            errors.append("Unassigned original JavaScript test: " + original)
    for filename, names in baseline.get("javascript_migrations", {}).get("new", {}).items():
        path = TESTS / filename
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        for name in names:
            if name not in source:
                errors.append("Missing mapped JavaScript protection: " + filename + ": " + name)
    return {"baseline": baseline["source_commit"], "old_ids": sum(map(len, baseline["modules"].values())),
            "current_ids": len(current), "suites": {key: selected(key) for key in SUITES},
            "classified_replacements": changes, "case_partitions": {filename: {suite: sorted(partition_ids(filename, suite)) for suite in partitions} for filename, partitions in CASE_PARTITIONS.items() if (TESTS / filename).is_file()}, "errors": errors}


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = []

    def _record(self, test, status, detail=None):
        item = {"id": test.id(), "status": status}
        if detail:
            item["detail"] = detail
        self.outcomes.append(item)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "expected-failure", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected-success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._record(subtest, "failed" if issubclass(err[0], test.failureException) else "error",
                         self._exc_info_to_string(err, test))


def run_module(filename, output, partition=None):
    started = time.monotonic()
    suite = unittest.TestLoader().discover(str(TESTS), pattern=filename)
    selected_ids = None
    if partition:
        selected_ids = partition_ids(filename, partition)
        collected = list(flatten_tests(suite))
        found = [item for item in collected if item.id() in selected_ids]
        found_ids = [item.id() for item in found]
        if set(found_ids) != selected_ids or len(found_ids) != len(set(found_ids)) or not found:
            report = {"module": filename, "partition": partition, "status": "failed",
                      "error": "Runtime collection does not exactly match assigned test IDs",
                      "expected": sorted(selected_ids), "collected": [item.id() for item in collected]}
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return 1
        suite = unittest.TestSuite(found)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"module": filename, "partition": partition, "selected_ids": sorted(selected_ids) if selected_ids else None, "seconds": round(time.monotonic() - started, 3),
              "tests_run": result.testsRun, "no_test_failures": result.wasSuccessful(),
              "status": "failed" if not result.wasSuccessful() else "incomplete" if result.skipped or not result.testsRun else "passed",
              "counts": {status: sum(item["status"] == status for item in result.outcomes)
                         for status in ("passed", "failed", "error", "skipped", "expected-failure", "unexpected-success")},
              "outcomes": result.outcomes}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() and result.testsRun else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES)
    parser.add_argument("--module")
    parser.add_argument("--partition", choices=SUITES)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.browser_evidence:
        files = sorted(path for path in args.browser_evidence.glob("**/*") if path.is_file())
        screenshots = [path for path in files if path.suffix == ".png"]
        valid = bool(screenshots) and all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in screenshots)
        report = {"valid": valid, "screenshots": len(screenshots), "files": [
            {"path": path.relative_to(args.browser_evidence).as_posix(), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]}
        (args.output / "browser-evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Actual browser evidence:", len(screenshots), "PNG files; valid:", valid)
        return int(not valid)
    if args.module:
        return run_module(args.module, args.output / (Path(args.module).stem + ".json"), args.partition)
    if args.audit:
        report = audit()
        (args.output / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in ("baseline", "old_ids", "current_ids", "errors")}))
        return bool(report["errors"])
    if not args.suite:
        parser.error("--suite, --module or --audit is required")
    results = []
    for filename in selected(args.suite):
        command = [sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning",
                   str(Path(__file__).resolve()), "--module", filename, "--output", str(args.output)]
        if filename in CASE_PARTITIONS:
            command.extend(["--partition", args.suite])
        completed = subprocess.run(command, cwd=ROOT, check=False)
        results.append({"module": filename, "exit_code": completed.returncode})
    for filename in NODE_SCRIPTS.get(args.suite, []):
        completed = subprocess.run(["node", str(TESTS / filename)], cwd=ROOT, check=False)
        results.append({"node": filename, "exit_code": completed.returncode})
    (args.output / "suite.json").write_text(json.dumps({"suite": args.suite, "results": results}, indent=2) + "\n", encoding="utf-8")
    return int(any(item["exit_code"] for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
