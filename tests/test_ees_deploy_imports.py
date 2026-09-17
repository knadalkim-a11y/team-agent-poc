"""Import probes use stdlib fixtures plus an opt-in real NLTK check, never the app."""

import importlib.util
import io
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import venv


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("ees_deploy_imports_test", SCRIPTS / "ees_deploy_imports.py")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class ImportProbeTests(unittest.TestCase):
    def program(self, statement, pre_arm_delay=0):
        original_program = PROBE._program

        def generate(started, watchdog_deadline):
            body = original_program(started, watchdog_deadline).replace("import nltk\n", statement + "\n")
            return f"import time; time.sleep({pre_arm_delay!r})\n" + body if pre_arm_delay else body

        return generate

    def test_real_standard_library_comparison_completes(self):
        with patch.object(PROBE, "_program", side_effect=self.program("import json")), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 2), \
                patch.object(PROBE, "PARENT_SECONDS", 4):
            report = PROBE.compare(sys.executable, sys.executable)
        self.assertEqual([row["program"] for row in report["results"]], ["original", "candidate"])
        for row in report["results"]:
            self.assertEqual(row["status"], "completed")
            self.assertEqual(row["exit_code"], 0)
            self.assertTrue(row["watchdog_armed"] and row["import_entered"] and row["import_completed"])
            self.assertGreater(row["timed_import_events"], 0)
            self.assertEqual(row["last_timed_import"], "json")
            self.assertFalse(row["cleanup_unverified"])
            self.assertAlmostEqual(row["watchdog_arm_seconds"] + row["watchdog_budget_seconds"], 2, places=5)
        self.assertNotIn(str(Path(sys.executable).parent), PROBE.render(report))

    def test_real_watchdog_exits_child_and_retains_deadline_stack(self):
        with patch.object(PROBE, "_program", side_effect=self.program("import time; time.sleep(30)")), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 1), \
                patch.object(PROBE, "PARENT_SECONDS", 5):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "watchdog_timeout")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertFalse(result["cleanup_unverified"])
        self.assertTrue(result["watchdog_armed"] and result["import_entered"])
        self.assertFalse(result["import_completed"])
        self.assertEqual(result["watchdog_threads_seen"], 1)
        self.assertEqual(result["watchdog_first_thread_frames"], ["other"])
        self.assertLess(result["elapsed_seconds"], 5)

    def test_delayed_bootstrap_shortens_watchdog_before_parent_deadline(self):
        # With the old relative timer, a two-second bootstrap followed by a
        # three-second watchdog exceeds the four-second parent deadline.
        with patch.object(PROBE, "_program", side_effect=self.program("time.sleep(30)", pre_arm_delay=2)), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 3), patch.object(PROBE, "PARENT_SECONDS", 4):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "watchdog_timeout", result)
        self.assertFalse(result["cleanup_unverified"])
        self.assertTrue(result["watchdog_armed"] and result["import_entered"] and result["watchdog_dump_seen"])
        self.assertFalse(result["import_completed"])
        self.assertGreaterEqual(result["watchdog_arm_seconds"], 2)
        self.assertGreater(result["watchdog_budget_seconds"], 0)
        self.assertLess(result["watchdog_budget_seconds"], 1)
        self.assertAlmostEqual(result["watchdog_arm_seconds"] + result["watchdog_budget_seconds"], 3, places=5)
        self.assertLess(result["elapsed_seconds"], 4)

    def test_expired_bootstrap_budget_does_not_initialize_site_or_import(self):
        generate = self.program("raise AssertionError('NLTK must not start')", pre_arm_delay=0.2)

        def guarded_program(started, watchdog_deadline):
            return generate(started, watchdog_deadline).replace("import site\n", "raise AssertionError('site must not start')\nimport site\n")

        with patch.object(PROBE, "_program", side_effect=guarded_program), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 0.1), patch.object(PROBE, "PARENT_SECONDS", 3):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "startup_budget_exhausted", result)
        self.assertEqual(result["exit_code"], 124)
        self.assertEqual(result["error_types"], [])
        self.assertFalse(any(result[key] for key in PROBE._MARKERS))
        self.assertFalse(result["watchdog_dump_seen"] or result["cleanup_unverified"])
        self.assertGreaterEqual(result["watchdog_arm_seconds"], 0.2)
        self.assertEqual(result["watchdog_budget_seconds"], 0)
        self.assertEqual(PROBE._handoff_status(result), "TIME-BOOT")

    def test_real_failure_reports_type_without_private_module_or_message(self):
        with patch.object(PROBE, "_program", side_effect=self.program("import SYNTHETIC_SECRET_missing_module")), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 2), \
                patch.object(PROBE, "PARENT_SECONDS", 4):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "import_failed")
        self.assertIn("ModuleNotFoundError", result["error_types"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_environment_excludes_registered_values_proxies_and_python_hooks(self):
        source = {"SystemRoot": "C:/Windows", "PATH": "loader-path", "TEMP": "temp-directory",
                  "HOME": "profile-home", "USERPROFILE": "profile-directory", "APPDATA": "profile-roaming",
                  "LOCALAPPDATA": "profile-local", "HOMEDRIVE": "C:", "HOMEPATH": "/Users/ees-profile",
                  "DATA_DIR": "SYNTHETIC_SECRET", "WEBUI_SECRET_KEY": "SYNTHETIC_SECRET",
                  "HTTP_PROXY": "SYNTHETIC_SECRET", "HTTPS_PROXY": "SYNTHETIC_SECRET",
                  "PYTHONPATH": "SYNTHETIC_SECRET", "PYTHONHOME": "SYNTHETIC_SECRET",
                  "SSL_CERT_FILE": "SYNTHETIC_SECRET", "NLTK_DATA": "SYNTHETIC_SECRET"}
        with patch.dict(os.environ, source, clear=True):
            # Windows normalizes os.environ keys to uppercase.
            self.assertEqual({key.upper(): value for key, value in PROBE._environment().items()},
                             {key.upper(): source[key] for key in (
                                 "SystemRoot", "PATH", "TEMP", "HOME", "USERPROFILE", "APPDATA",
                                 "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH")})

    def test_windows_home_expansion_survives_profile_filtering(self):
        # ntpath exercises the Windows expansion rules on either test platform.
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ntpath.expanduser("~/"), "~/")
        for profile in ({"USERPROFILE": "C:/Users/ees-profile"},
                        {"HOMEDRIVE": "C:", "HOMEPATH": "/Users/ees-profile"}):
            with self.subTest(profile_fields=tuple(profile)):
                with patch.dict(os.environ, profile, clear=True):
                    filtered = PROBE._environment()
                with patch.dict(os.environ, filtered, clear=True):
                    self.assertEqual(ntpath.normpath(ntpath.expanduser("~/")),
                                     ntpath.normpath("C:/Users/ees-profile"))

    @unittest.skipUnless(os.environ.get("EES_RUN_REAL_NLTK_TEST") == "1", "opt-in real NLTK dependency check")
    def test_real_nltk_import_completes_with_profile_environment(self):
        with patch.object(PROBE, "WATCHDOG_SECONDS", 10), patch.object(PROBE, "PARENT_SECONDS", 15):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["import_completed"])
        self.assertFalse(result["cleanup_unverified"])

    @unittest.skipUnless(os.name == "nt" and os.environ.get("EES_RUN_REAL_NLTK_TEST") == "1",
                         "Windows real NLTK profile regression")
    def test_real_nltk_downloader_without_profile_reproduces_value_error(self):
        # First import normally, then remove both profile and existing corpus
        # directory fallbacks. This exercises NLTK's own implementation without
        # requiring a particular runner's corpus installation or copying source.
        statement = '''import nltk
import os
nltk.data.path.clear()
for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH"):
    os.environ.pop(key, None)
nltk.downloader.Downloader()'''
        with patch.object(PROBE, "_program", side_effect=self.program(statement)), \
                patch.object(PROBE, "WATCHDOG_SECONDS", 10), \
                patch.object(PROBE, "PARENT_SECONDS", 15):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "import_failed", result)
        self.assertIn("ValueError", result["error_types"])
        self.assertTrue(any(frame.startswith("nltk/downloader.py:") for frame in result["last_error_frames"]))
        self.assertFalse(result["cleanup_unverified"])

    def test_only_self_times_are_summed_and_unknown_names_are_hidden(self):
        stderr = "\n".join([
            "import time: self [us] | cumulative | imported package",
            "import time: 100 | 4000000 | json",
            "import time: 300 | 9000000 |   pandas.core.api",
            "import time: 500 | 9999999 |   SYNTHETIC_SECRET.module",
            "import time: 200 | 9000000 |   nltk",
            "SYNTHETIC_SECRET.VendorError: internal URL and token",
            "ModuleNotFoundError: SYNTHETIC_SECRET",
        ])
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["timed_import_events"], 4)
        self.assertEqual(result["observed_self_seconds"], 0.0011)
        self.assertEqual(result["top_self"][0], {"module": "other", "seconds": 0.0005})
        self.assertEqual(result["last_timed_import"], "nltk")
        self.assertEqual(result["error_types"], ["other", "ModuleNotFoundError"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_budget_report_requires_one_complete_bounded_numeric_record(self):
        valid = "EES_IMPORT_BUDGET 12.300000 47.700000\n"
        result = PROBE._summarize(valid, "", len(valid), 0)
        self.assertEqual((result["watchdog_arm_seconds"], result["watchdog_budget_seconds"]), (12.3, 47.7))
        for stdout, size in ((valid, PROBE.MAX_BYTES + 1), (valid + valid, len(valid) * 2),
                             ("", 0), ("EES_IMPORT_BUDGET nan 60.000000", 36),
                             ("EES_IMPORT_BUDGET 0.000000 99999.000000", 40),
                             ("EES_IMPORT_BUDGET SYNTHETIC_SECRET 1.000000", 45)):
            with self.subTest(stdout=stdout, size=size):
                result = PROBE._summarize(stdout, "", size, 0)
                self.assertIsNone(result["watchdog_arm_seconds"])
                self.assertIsNone(result["watchdog_budget_seconds"])
                self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_watchdog_first_thread_is_limited_and_not_claimed_as_main_thread(self):
        lines = ["Timeout (0:01:00)!", "Thread 0xabc123 (most recent call first):"]
        lines += ['  File "C:/SYNTHETIC_SECRET/Lib/site-packages/nltk/data.py", line 12 in load'] * 11
        lines += ["Thread 0xdef456 (most recent call first):",
                  '  File "C:/SYNTHETIC_SECRET/private.py", line 123 in token',
                  "PermissionError: SYNTHETIC_SECRET"]
        stderr = "\n".join(lines)
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["watchdog_threads_seen"], 2)
        self.assertEqual(result["watchdog_first_thread_frames"], ["nltk/data.py:12:load"] * 10)
        self.assertEqual(result["watchdog_first_thread_frames_omitted"], 1)
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_unknown_frames_hide_paths_and_functions(self):
        stderr = ('Timeout (0:01:00)!\nThread 0xabc123 (most recent call first):\n'
                  '  File "C:/SYNTHETIC_SECRET/private.py", line 123 in SYNTHETIC_SECRET\n'
                  '  File "<frozen importlib._bootstrap>", line 1176 in _find_and_load\n')
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["watchdog_first_thread_frames"], ["other", "frozen/importlib._bootstrap:1176:_find_and_load"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_last_error_traceback_retains_six_safe_frames_and_no_messages(self):
        lines = ["Traceback (most recent call last):",
                 '  File "C:/SYNTHETIC_SECRET/earlier.py", line 42, in SYNTHETIC_SECRET',
                 "ValueError: SYNTHETIC_SECRET", "Traceback (most recent call last):"]
        lines += ['  File "C:/SYNTHETIC_SECRET/Lib/site-packages/nltk/data.py", line 12, in load'] * 6
        lines += ['  File "C:/SYNTHETIC_SECRET/private.py", line 123, in SYNTHETIC_SECRET',
                  "    print('SYNTHETIC_SECRET')", "ImportError: SYNTHETIC_SECRET"]
        stderr = "\n".join(lines)
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["last_error_frames"], ["nltk/data.py:12:load"] * 5 + ["other"])
        self.assertEqual(result["last_error_frames_omitted"], 1)
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))
        stderr += '\nTimeout (0:01:00)!\nThread 0xabc (most recent call first):\n  File "<string>", line 1 in <module>\n'
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["last_error_frames"], [])
        self.assertEqual(result["watchdog_first_thread_frames"], ["other"])

    def test_render_has_fixed_deadlines_and_validated_short_commit(self):
        text = PROBE.render({"source_commit": "a" * 40, "results": []})
        self.assertIn("watchdog: 60s; parent: 70s; source: " + "a" * 12, text)
        for value in (None, 1, "SYNTHETIC_SECRET", "a" * 40 + "\nSYNTHETIC_SECRET"):
            with self.subTest(value=value):
                text = PROBE.render({"source_commit": value, "results": []})
                self.assertIn("source: unknown", text)
                self.assertNotIn("SYNTHETIC_SECRET", text)

    def test_handoff_is_last_two_lines_with_fixed_program_order(self):
        report = {"report_saved": True, "results": [
            {"program": "candidate", "status": "watchdog_timeout", "import_entered": True, "elapsed_seconds": 60.123,
             "watchdog_arm_seconds": 12.3, "watchdog_budget_seconds": 47.7},
            {"program": "original", "status": "completed", "elapsed_seconds": 1.678,
             "watchdog_arm_seconds": 0.05, "watchdog_budget_seconds": 59.95},
        ]}
        rendered = PROBE.render(report)
        self.assertTrue(rendered.startswith("EES import comparison v1\n"))
        self.assertIn('"program":"candidate"', rendered)
        self.assertEqual(rendered.splitlines()[-2:], ["SEND I1 O=OK/1.7 C=TIME-IMPORT/60.1 saved=yes",
                                                    "SEND T1 O=0.1/60.0 C=12.3/47.7"])

    def test_handoff_timeout_phase_uses_markers_and_partial_stdout(self):
        for fields, expected in (
            ({"watchdog_armed": True}, "TIME-SITE"),
            ({"watchdog_armed": True, "import_entered": True}, "TIME-IMPORT"),
            ({"watchdog_armed": True, "import_entered": True, "import_completed": True}, "TIME-EXIT"),
            ({}, "TIME-?"),
            ({"import_entered": True, "stdout_scope": "tail"}, "TIME-?"),
            ({"import_entered": True, "stderr_scope": "tail"}, "TIME-IMPORT"),
        ):
            with self.subTest(fields=fields):
                result = {"program": "original", "status": "watchdog_timeout", **fields}
                line = PROBE._handoff_line({"results": [result]})
                self.assertIn(f"O={expected}/-", line)
                self.assertEqual("partial=yes" in line, "tail" in fields.values())

    def test_handoff_cleanup_takes_precedence_and_known_states_remain_distinct(self):
        for status, fields, expected in (
            ("completed", {}, "OK"),
            ("completed", {"cleanup_unverified": True}, "CLEANUP"),
            ("parent_timeout_cleanup_unverified", {}, "CLEANUP"),
            ("parent_timeout", {}, "CLEANUP"),
            ("watchdog_timeout", {"cleanup_unverified": True, "import_entered": True}, "CLEANUP"),
            ("interrupted", {}, "STOP"),
            ("import_failed", {}, "ERROR"),
            ("launch_failed", {}, "LAUNCH"),
            ("startup_budget_exhausted", {}, "TIME-BOOT"),
            ("startup_budget_exhausted", {"stdout_scope": "tail"}, "TIME-?"),
            ("probe_incomplete", {}, "UNKNOWN"),
            ("skipped_after_incomplete_probe", {}, "SKIP"),
        ):
            with self.subTest(status=status, fields=fields):
                self.assertEqual(PROBE._handoff_status({"status": status, **fields}), expected)

    def test_handoff_missing_rows_and_invalid_times_do_not_invent_results(self):
        self.assertEqual(PROBE._handoff_line({}), "SEND I1 O=UNKNOWN/- C=UNKNOWN/- saved=no")
        for seconds in (None, True, False, -1, 86401, float("nan"), float("inf"), -float("inf"), "1.7"):
            with self.subTest(seconds=seconds):
                line = PROBE._handoff_line({"report_saved": "yes", "results": [
                    {"program": "original", "status": "completed", "elapsed_seconds": seconds}]})
                self.assertEqual(line, "SEND I1 O=OK/- C=UNKNOWN/- saved=no")
        for seconds, expected in ((0, "0.0"), (86400, "86400.0")):
            line = PROBE._handoff_line({"results": [
                {"program": "original", "status": "completed", "elapsed_seconds": seconds}]})
            self.assertIn(f"O=OK/{expected}", line)

    def test_timing_handoff_handles_old_partial_and_invalid_reports(self):
        self.assertEqual(PROBE._handoff_timing_line({}), "SEND T1 O=-/- C=-/-")
        for seconds in (None, True, False, -1, 86401, float("nan"), float("inf"), "SYNTHETIC_SECRET"):
            report = {"results": [{"program": "original", "watchdog_arm_seconds": seconds,
                                   "watchdog_budget_seconds": seconds}]}
            self.assertEqual(PROBE._handoff_timing_line(report), "SEND T1 O=-/- C=-/-")
        for scope, expected in (("full", "SEND T1 O=0.0/86400.0 C=86400.0/0.0"),
                                ("tail", "SEND T1 O=-/- C=-/-")):
            report = {"results": [
                {"program": "candidate", "watchdog_arm_seconds": 86400, "watchdog_budget_seconds": 0, "stdout_scope": scope},
                {"program": "original", "watchdog_arm_seconds": 0, "watchdog_budget_seconds": 86400, "stdout_scope": scope}]}
            line = PROBE._handoff_timing_line(report)
            self.assertEqual(line, expected)
            self.assertLessEqual(len(line), 180)
            self.assertEqual(len(line.splitlines()), 1)

    def test_handoff_error_types_are_allowlisted_first_only_and_length_is_bounded(self):
        for error_type in PROBE._ERRORS:
            report = {"report_saved": True, "results": [
                {"program": "original", "status": "import_failed", "elapsed_seconds": 86400,
                 "error_types": [error_type, "ValueError"], "stderr_scope": "tail"},
                {"program": "candidate", "status": "launch_failed", "elapsed_seconds": 86400,
                 "error_type": error_type},
            ]}
            with self.subTest(error_type=error_type):
                line = PROBE._handoff_line(report)
                self.assertTrue(line.endswith(f"errO={error_type} errC={error_type}"))
                self.assertLessEqual(len(line), 180)
                self.assertEqual(len(line.splitlines()), 1)

    def test_cleanup_handoff_keeps_error_evidence_and_length_bound(self):
        for error_type in PROBE._ERRORS:
            report = {"report_saved": True, "results": [
                {"program": program, "status": "parent_timeout_cleanup_unverified", "elapsed_seconds": 86400,
                 "error_types": [error_type], "stdout_scope": "tail"}
                for program in ("original", "candidate")]}
            line = PROBE._handoff_line(report)
            self.assertIn("O=CLEANUP/86400.0 C=CLEANUP/86400.0", line)
            self.assertTrue(line.endswith(f"errO={error_type} errC={error_type}"))
            self.assertLessEqual(len(line), 180)

    def test_handoff_never_echoes_unknown_labels_paths_or_errors(self):
        for name in ("other", "SYNTHETIC_SECRET\nhttps://internal/path?token=private", {"private": "value"}):
            line = PROBE._handoff_line({"source_commit": "SYNTHETIC_SECRET", "results": [
                {"program": "original", "status": "import_failed", "error_types": [name]},
                {"program": "candidate", "status": "SYNTHETIC_SECRET", "elapsed_seconds": "SYNTHETIC_SECRET"},
                {"program": "SYNTHETIC_SECRET", "status": "completed"},
            ]})
            self.assertEqual(line, "SEND I1 O=ERROR/- C=UNKNOWN/- saved=no errO=OTHER")

    def test_syntax_error_location_without_function_hides_source_and_message(self):
        stderr = ('Traceback (most recent call last):\n'
                  '  File "C:/SYNTHETIC_SECRET/Lib/site-packages/nltk/data.py", line 12\n'
                  '    SYNTHETIC_SECRET(\n'
                  'SyntaxError: SYNTHETIC_SECRET\n')
        result = PROBE._summarize("", stderr, 0, len(stderr))
        self.assertEqual(result["error_types"], ["SyntaxError"])
        self.assertEqual(result["last_error_frames"], ["nltk/data.py:12:<syntax>"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_oversized_output_uses_bounded_tail_and_marks_partial_measurement(self):
        payload = b"x" * 100 + b"\nimport time: 1 | 99 | json\n"
        with patch.object(PROBE, "MAX_BYTES", 40):
            text, size = PROBE._read(io.BytesIO(payload))
            result = PROBE._summarize("", text, 0, size)
        self.assertEqual(size, len(payload))
        self.assertLessEqual(len(text), 40)
        self.assertEqual(result["stderr_scope"], "tail")
        self.assertEqual(result["timed_import_events"], 1)
        self.assertEqual(result["observed_self_seconds"], 0.000001)

    def test_parent_timeout_marks_cleanup_unverified_and_skips_candidate(self):
        child = Mock(returncode=-9)
        child.wait.side_effect = [subprocess.TimeoutExpired("private", 70), -9]
        with patch.object(PROBE.subprocess, "Popen", return_value=child) as spawn:
            report = PROBE.compare("private-original", "private-candidate")
        self.assertEqual(spawn.call_count, 1)
        child.kill.assert_called_once_with()
        self.assertEqual(report["results"][0]["status"], "parent_timeout_cleanup_unverified")
        self.assertTrue(report["results"][0]["cleanup_unverified"])
        self.assertEqual(report["results"][1]["status"], "skipped_after_incomplete_probe")
        self.assertNotIn("private", PROBE.render(report))

    def test_keyboard_interrupt_preserves_child_watchdog_and_skips_candidate(self):
        child = Mock(returncode=1)
        child.wait.side_effect = [KeyboardInterrupt(), 1]
        with patch.object(PROBE.subprocess, "Popen", return_value=child) as spawn:
            report = PROBE.compare("original", "candidate")
        self.assertEqual(spawn.call_count, 1)
        child.kill.assert_not_called()
        self.assertEqual(report["results"][0]["status"], "interrupted")
        self.assertFalse(report["results"][0]["cleanup_unverified"])
        self.assertEqual(report["results"][1]["status"], "skipped_after_incomplete_probe")
        self.assertEqual(child.wait.call_count, 2)
        options = spawn.call_args.kwargs
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertEqual(options["creationflags"], subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            self.assertTrue(options["start_new_session"])

    def test_launch_error_does_not_disclose_executable_or_message(self):
        with patch.object(PROBE.subprocess, "Popen", side_effect=FileNotFoundError("SYNTHETIC_SECRET")):
            result = PROBE._measure("SYNTHETIC_SECRET")
        self.assertEqual(result["status"], "launch_failed")
        self.assertEqual(result["error_type"], "FileNotFoundError")
        self.assertFalse(result["cleanup_unverified"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    @unittest.skipUnless(os.name == "nt" and sys.version_info[:2] == (3, 11), "Windows Python 3.11 venv launcher")
    def test_windows_venv_site_initialization_and_watchdog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv.EnvBuilder(with_pip=False).create(root)
            executable = root / "Scripts" / "python.exe"
            (root / "Lib" / "site-packages" / "nltk.py").write_text("import json\n", encoding="utf-8")
            with patch.object(PROBE, "WATCHDOG_SECONDS", 3), patch.object(PROBE, "PARENT_SECONDS", 5):
                result = PROBE._measure(executable)
            self.assertEqual(result["status"], "completed")
            (root / "Lib" / "site-packages" / "nltk.py").write_text("import time; time.sleep(30)\n", encoding="utf-8")
            with patch.object(PROBE, "WATCHDOG_SECONDS", 1), patch.object(PROBE, "PARENT_SECONDS", 4):
                result = PROBE._measure(executable)
            self.assertEqual(result["status"], "watchdog_timeout")
            self.assertFalse(result["cleanup_unverified"])
            self.assertTrue(any(frame.startswith("nltk.py:") for frame in result["watchdog_first_thread_frames"]))


if __name__ == "__main__":
    unittest.main()
