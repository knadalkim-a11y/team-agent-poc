"""Fixed import probes use standard-library fixtures, never the real app."""

import importlib.util
import io
import json
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
    def program(self, statement, timeout=2):
        with patch.object(PROBE, "WATCHDOG_SECONDS", timeout):
            return PROBE._program().replace("import nltk\n", statement + "\n")

    def test_real_standard_library_comparison_completes(self):
        with patch.object(PROBE, "_program", return_value=self.program("import json")), \
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
        self.assertNotIn(str(Path(sys.executable).parent), PROBE.render(report))

    def test_real_watchdog_exits_child_and_retains_deadline_stack(self):
        with patch.object(PROBE, "_program", return_value=self.program("import time; time.sleep(30)", timeout=1)), \
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

    def test_real_failure_reports_type_without_private_module_or_message(self):
        with patch.object(PROBE, "_program", return_value=self.program("import SYNTHETIC_SECRET_missing_module")), \
                patch.object(PROBE, "PARENT_SECONDS", 4):
            result = PROBE._measure(sys.executable)
        self.assertEqual(result["status"], "import_failed")
        self.assertIn("ModuleNotFoundError", result["error_types"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_environment_excludes_registered_values_proxies_and_python_hooks(self):
        source = {"SystemRoot": "C:/Windows", "PATH": "loader-path", "TEMP": "temp-directory",
                  "DATA_DIR": "SYNTHETIC_SECRET", "WEBUI_SECRET_KEY": "SYNTHETIC_SECRET",
                  "HTTP_PROXY": "SYNTHETIC_SECRET", "HTTPS_PROXY": "SYNTHETIC_SECRET",
                  "PYTHONPATH": "SYNTHETIC_SECRET", "HOME": "SYNTHETIC_SECRET",
                  "SSL_CERT_FILE": "SYNTHETIC_SECRET", "NLTK_DATA": "SYNTHETIC_SECRET"}
        with patch.dict(os.environ, source, clear=True):
            self.assertEqual(PROBE._environment(), {key: source[key] for key in ("SystemRoot", "PATH", "TEMP")})

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
