"""Synthetic local logs test selection and disclosure; no WebUI is imported."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("ees_deploy_report_test", SCRIPTS / "ees_deploy_report.py")
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class FailedStartupReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.config = {"state_root": str(self.root)}
        self.failed = datetime(2026, 9, 8, 7, 35, 31, tzinfo=timezone.utc).timestamp()
        self.created = {}
        self.candidate = self.log("a", self.failed - 600, b"candidate\n")
        self.active = self.log("b", self.failed + 1, b"Application startup complete\n")
        self.registry = {
            "phase": "idle", "last_event": "previous_program_recovered",
            "current": {"kind": "original"}, "process": {"log_file": str(self.active)},
            "updated_at": datetime.fromtimestamp(self.failed + 112, timezone.utc).isoformat(),
            "last_failure": {"failed_at": "2026-09-08T07:35:31Z", "recovery_status": "succeeded",
                             "switch": {"stage": "health_check"}},
        }
        fake_times = patch.object(REPORT, "_created_at", side_effect=lambda path: self.created[path])
        fake_times.start()
        self.addCleanup(fake_times.stop)

    def log(self, letter, created, content=b"older\n"):
        path = self.logs / ("server-" + letter * 32 + ".log")
        path.write_bytes(content)
        self.created[path] = created
        return path

    def collect(self):
        return REPORT.collect(self.config, self.registry)

    def recorded_failure(self):
        self.registry["last_failure"].update({
            "evidence_version": 1,
            "candidate": {"kind": "release", "source_commit": "a" * 40},
            "switch": {"stage": "health_check", "log_id": self.candidate.name,
                       "reason": "health_timeout", "elapsed_seconds": 600.1,
                       "timeout_seconds": 600, "exit_code": None},
            "recovery_log_id": self.active.name,
        })

    def test_recorded_log_is_selected_without_creation_time_or_log_enumeration(self):
        self.recorded_failure()
        self.log("c", self.failed + 5000, b"SyntaxError: unrelated later log\n")
        with patch.object(REPORT, "_created_at", side_effect=AssertionError("creation inference")), \
                patch.object(Path, "iterdir", side_effect=AssertionError("log enumeration")):
            result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selection"], "recorded_log_id")
        self.assertIsNone(result["candidate_seconds"])
        self.assertIsNone(result["recovery_seconds"])
        self.assertEqual(result["error_types"], [])

    def test_recorded_failure_remains_readable_after_start_stop_and_later_deploy(self):
        self.recorded_failure()
        for event, process, current in (
                ("started_by_operator", {"log_file": str(self.active)}, {"kind": "original"}),
                ("stopped_by_operator", None, {"kind": "original"}),
                ("program_deployed", {"log_file": str(self.active)}, {"kind": "release"})):
            with self.subTest(event=event):
                self.registry.update({"last_event": event, "process": process, "current": current,
                                      "updated_at": "not used for recorded log"})
                self.assertEqual(self.collect()["selection"], "recorded_log_id")

    def test_recorded_original_candidate_is_valid(self):
        self.recorded_failure()
        self.registry["last_failure"]["candidate"] = {"kind": "original", "source_commit": None}
        self.assertEqual(self.collect()["status"], "ok")

    def test_invalid_recorded_evidence_never_falls_back_to_legacy_inference(self):
        self.recorded_failure()
        baseline = deepcopy(self.registry)
        changes = [
            {"evidence_version": value} for value in (None, True, "1", 2)
        ] + [
            {"candidate": value} for value in (None, {}, {"kind": "unknown", "source_commit": None},
                {"kind": "release", "source_commit": None},
                {"kind": "release", "source_commit": "SYNTHETIC_SECRET"},
                {"kind": "original", "source_commit": "a" * 40})
        ] + [
            {"switch": value} for value in (None, {}, {"log_id": None},
                {"log_id": "../" + self.candidate.name}, {"log_id": str(self.candidate)},
                {"log_id": "SYNTHETIC_SECRET"})
        ] + [{"recovery_log_id": "SYNTHETIC_SECRET"}]
        for change in changes:
            with self.subTest(change=change):
                self.registry = deepcopy(baseline)
                self.registry["last_failure"].update(change)
                with patch.object(REPORT, "_created_at", side_effect=AssertionError("creation inference")):
                    result = self.collect()
                self.assertEqual(result["status"], "unavailable")
                self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_missing_recorded_log_does_not_select_an_existing_different_log(self):
        self.recorded_failure()
        self.candidate.unlink()
        self.log("c", self.failed - 20, b"ValueError: unrelated\n")
        with patch.object(REPORT, "_created_at", side_effect=AssertionError("creation inference")):
            result = self.collect()
        self.assertEqual(result, {"status": "unavailable", "reason": "unsafe_or_missing_log_path"})

    def test_recorded_candidate_current_process_log_is_never_read(self):
        self.recorded_failure()
        self.registry["process"] = {"log_file": str(self.candidate)}
        self.registry["last_event"] = "start_failed"
        with patch.object(Path, "open", side_effect=AssertionError("active log read")):
            self.assertEqual(self.collect(), {"status": "ambiguous", "reason": "recorded_log_is_active"})

    def test_recorded_recovery_log_cannot_be_selected_even_after_stop(self):
        self.recorded_failure()
        self.registry["last_failure"]["switch"]["log_id"] = self.active.name
        self.registry.update({"process": None, "last_event": "stopped_by_operator"})
        with patch.object(Path, "open", side_effect=AssertionError("recovery log read")), \
                patch.object(REPORT, "_created_at", side_effect=AssertionError("creation inference")):
            self.assertEqual(self.collect(), {"status": "ambiguous", "reason": "candidate_matches_recovery_log"})

    def test_recorded_selection_requires_idle_without_pending_or_uncertain_launch(self):
        self.recorded_failure()
        for change in ({"phase": "recovery_required"}, {"phase": "switching"},
                       {"pending": {"kind": "release"}}, {"launch_uncertain": True}):
            with self.subTest(change=change):
                registry = deepcopy(self.registry)
                registry.update(change)
                with patch.object(Path, "open", side_effect=AssertionError("log read")):
                    result = REPORT.collect(self.config, registry)
                self.assertEqual(result["reason"], "recorded_failure_not_idle")

    def test_selects_candidate_by_creation_not_current_log_or_mtime(self):
        self.log("c", self.failed - 1500)
        os.utime(self.candidate, (self.failed + 5000, self.failed + 5000))
        result = self.collect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selection"], "inferred_from_creation_time")
        self.assertEqual((result["candidate_seconds"], result["recovery_seconds"]), (600, 111))
        self.assertFalse(result["signals"]["startup_complete"])
        self.assertEqual(result["scan_scope"], "full")

    def test_same_second_start_is_not_a_negative_duration(self):
        self.created[self.candidate] = self.failed + 0.2
        self.assertEqual(self.collect()["candidate_seconds"], 0)

    def test_stale_failure_does_not_select_a_log(self):
        for change in ({"last_event": "started_by_operator"}, {"phase": "switching"},
                       {"current": {"kind": "release"}}, {"launch_uncertain": True}):
            with self.subTest(change=change):
                registry = deepcopy(self.registry)
                registry.update(change)
                result = REPORT.collect(self.config, registry)
                self.assertEqual(result["reason"], "no_recovered_health_failure")
        self.registry["last_failure"]["switch"]["stage"] = "backup"
        self.assertEqual(self.collect()["reason"], "no_recovered_health_failure")

    def test_existing_operation_lock_returns_busy_without_reading_logs(self):
        lock = self.root / "deployment.lock"
        lock.write_text("synthetic-private")
        with patch.object(REPORT, "_created_at", side_effect=AssertionError("log read")):
            self.assertEqual(self.collect(), {"status": "busy", "reason": "deployment_in_progress"})
            self.recorded_failure()
            self.assertEqual(self.collect(), {"status": "busy", "reason": "deployment_in_progress"})
        self.assertEqual(lock.read_text(), "synthetic-private")

    def test_tied_candidates_or_later_logs_are_ambiguous(self):
        tied = self.log("c", self.created[self.candidate])
        self.assertEqual(self.collect()["reason"], "candidate_creation_time_tied")
        self.created[tied] = self.created[self.active] + 1
        result = self.collect()
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "later_or_tied_recovery_log")

    def test_unexpected_log_between_failure_and_recovery_is_ambiguous(self):
        self.created[self.active] = self.failed + 5
        self.log("c", self.failed + 2)
        self.assertEqual(self.collect(), {"status": "ambiguous", "reason": "log_between_failure_and_recovery"})

    def test_missing_candidate_invalid_time_and_outside_recovery_are_unavailable(self):
        self.candidate.unlink()
        self.assertEqual(self.collect()["reason"], "candidate_log_missing")
        self.registry["updated_at"] = "2026-09-08T07:35:31"
        self.assertEqual(self.collect()["reason"], "invalid_timestamps")
        self.registry["updated_at"] = "2026-09-08T07:35:31+00:00"
        self.assertEqual(self.collect()["reason"], "inconsistent_recovery_time")
        outside = self.root / self.active.name
        outside.write_bytes(b"private")
        self.registry["process"]["log_file"] = str(outside)
        self.assertEqual(self.collect()["reason"], "recovery_log_outside_managed_logs")

    def test_public_nested_stdlib_and_frozen_frames_without_private_text(self):
        secret = "SYNTHETIC_SECRET_92EF"
        self.candidate.write_text(
            'Traceback (most recent call last):\n'
            f'  File "C:\\Users\\{secret}\\venv\\Lib\\site-packages\\open_webui\\retrieval\\web\\utils.py", line 33, in validate_url\n'
            f'    request("https://{secret}.internal/?token={secret}")\n'
            f'  File "C:\\Users\\{secret}\\Python\\Lib\\socket.py", line 100, in connect\n'
            '  File "<frozen importlib._bootstrap_external>", line 1634, in find_spec\n'
            f'  File "C:\\{secret}\\private.py", line 123, in {secret}\n'
            f'requests.exceptions.SSLError: CERTIFICATE_VERIFY_FAILED https://{secret}.internal\n'
            f'{secret}Error: token={secret}\n', encoding="utf-8")
        result = self.collect()
        encoded = json.dumps(result)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("https://", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertEqual(result["frames"], [
            "open_webui/retrieval/web/utils.py:33:validate_url", "stdlib/socket.py:100:connect",
            "frozen/importlib._bootstrap_external:1634:find_spec", "other"])
        self.assertEqual(result["error_types"], ["SSLError", "other"])
        self.assertTrue(result["signals"]["cert_verify_failed"])
        self.assertEqual(result["unknown_frames"], 1)
        self.assertEqual(result["first_error_type"], "SSLError")
        self.assertTrue(result["first_error_matches_last_traceback"])
        self.assertEqual(result["first_error_frames"], [])

    def test_last_traceback_frames_are_bounded_but_errors_cover_read_scope(self):
        text = 'Traceback (most recent call last):\n  File "C:/private.py", line 1, in private\nValueError: private\n'
        text += 'Traceback (most recent call last):\n'
        text += ''.join(f'  File "<frozen importlib._bootstrap>", line {n}, in _find_spec\n' for n in range(25))
        text += 'KeyboardInterrupt\n'
        self.candidate.write_text(text)
        result = self.collect()
        self.assertEqual(result["tracebacks_seen"], 2)
        self.assertEqual(result["error_types"], ["ValueError", "KeyboardInterrupt"])
        self.assertEqual(result["first_error_type"], "ValueError")
        self.assertEqual(result["first_error_frames"], ["other"])
        self.assertFalse(result["first_error_matches_last_traceback"])
        self.assertEqual(result["frames_omitted"], 6)
        self.assertEqual(len(result["frames"]), 19)
        self.assertTrue(result["frames"][0].endswith(":6:_find_spec"))
        self.assertEqual(result["unknown_frames"], 0)

    def test_both_tracebacks_share_the_twenty_frame_budget_and_mark_omissions(self):
        frames = ''.join(f'  File "<frozen importlib._bootstrap>", line {n}, in _find_spec\n' for n in range(25))
        self.candidate.write_text(
            'Traceback (most recent call last):\n' + frames + 'ImportError: private\n'
            'Traceback (most recent call last):\n' + frames + 'KeyboardInterrupt\n')
        result = self.collect()
        self.assertEqual(len(result["first_error_frames"]) + len(result["frames"]), 20)
        self.assertEqual(result["first_error_frames_omitted"], 15)
        self.assertEqual(result["frames_omitted"], 15)
        self.assertEqual(result["first_error_type"], "ImportError")

    def test_first_interrupt_traceback_is_skipped_before_error_and_later_interrupt(self):
        self.candidate.write_text(
            'Traceback (most recent call last):\n'
            '  File "<frozen importlib._bootstrap>", line 1, in _find_spec\nKeyboardInterrupt\n'
            'Traceback (most recent call last):\n'
            '  File "C:/Lib/site-packages/sqlalchemy/engine/base.py", line 2, in connect\n'
            'OperationalError: SYNTHETIC_SECRET\n'
            'Traceback (most recent call last):\n'
            '  File "C:/Lib/asyncio/runners.py", line 3, in run\nSystemExit: 1\n')
        result = self.collect()
        self.assertEqual(result["first_error_type"], "OperationalError")
        self.assertEqual(result["first_error_frames"], ["sqlalchemy/engine/base.py:2:connect"])
        self.assertEqual(result["frames"], ["stdlib/asyncio/runners.py:3:run"])
        self.assertEqual(result["error_types"], ["KeyboardInterrupt", "OperationalError", "SystemExit"])
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_interrupt_only_does_not_claim_an_earlier_error(self):
        self.candidate.write_text('Traceback (most recent call last):\n'
                                  '  File "<frozen importlib._bootstrap>", line 1, in _find_spec\nKeyboardInterrupt\n')
        result = self.collect()
        self.assertIsNone(result["first_error_type"])
        self.assertEqual(result["first_error_frames"], [])
        self.assertFalse(result["first_error_matches_last_traceback"])

    def test_syntax_error_preserves_public_location_without_function_or_source(self):
        self.candidate.write_text(
            '  File "C:/Users/private/venv/Lib/site-packages/torch/tests/example.py", line 15\n'
            '    SYNTHETIC_PRIVATE_SOURCE = (\n'
            'SyntaxError: private source message\n')
        result = self.collect()
        self.assertEqual(result["frames"], ["torch/tests/example.py:15:<syntax>"])
        self.assertEqual(result["error_types"], ["SyntaxError"])
        self.assertEqual(result["first_error_type"], "SyntaxError")
        self.assertTrue(result["first_error_matches_last_traceback"])
        self.assertFalse(result["first_error_traceback_header_seen"])
        self.assertNotIn("PRIVATE_SOURCE", json.dumps(result))

    def test_syntax_error_without_header_is_preserved_before_later_interrupt(self):
        self.candidate.write_text(
            '  File "C:/Lib/site-packages/torch/tests/example.py", line 15\n'
            '    SYNTHETIC_PRIVATE_SOURCE = (\nSyntaxError: private\n'
            'Traceback (most recent call last):\n'
            '  File "<frozen importlib._bootstrap>", line 5, in _find_spec\nKeyboardInterrupt\n')
        result = self.collect()
        self.assertEqual(result["first_error_frames"], ["torch/tests/example.py:15:<syntax>"])
        self.assertEqual(result["first_error_type"], "SyntaxError")
        self.assertFalse(result["first_error_traceback_header_seen"])
        self.assertNotIn("PRIVATE_SOURCE", json.dumps(result))
    def test_tail_scope_does_not_claim_full_log_or_complete_traceback(self):
        self.candidate.write_bytes(b"Application startup complete\n" + b"x" * 256 + b"\nKeyboardInterrupt\n")
        with patch.object(REPORT, "MAX_LOG_BYTES", 128):
            result = self.collect()
        self.assertEqual(result["scan_scope"], "tail")
        self.assertLessEqual(result["bytes_read"], 128)
        self.assertFalse(result["signals"]["startup_complete"])
        self.assertFalse(result["last_traceback_header_seen"])
        self.assertEqual(result["error_types"], ["KeyboardInterrupt"])

    def test_symlink_and_hardlink_log_paths_are_rejected(self):
        outside = self.root / "outside.log"
        outside.write_bytes(b"private")
        self.candidate.unlink()
        try:
            self.candidate.symlink_to(outside)
        except (OSError, NotImplementedError):
            pass
        else:
            self.assertEqual(self.collect()["reason"], "unsafe_or_missing_log_path")
            self.recorded_failure()
            self.assertEqual(self.collect()["reason"], "unsafe_or_missing_log_path")
            self.registry["last_failure"].pop("evidence_version")
            self.candidate.unlink()
        try:
            os.link(outside, self.candidate)
        except (OSError, NotImplementedError):
            self.skipTest("Hardlinks unavailable")
        self.assertEqual(self.collect()["reason"], "unsafe_or_missing_log_path")
        self.recorded_failure()
        self.assertEqual(self.collect()["reason"], "unsafe_or_missing_log_path")

    def test_collect_does_not_run_environment_probes_commands_or_change_files(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        with patch.object(REPORT.states, "runtime_environment", side_effect=AssertionError("environment probe")), \
                patch.object(REPORT.states, "backup_state", side_effect=AssertionError("backup")), \
                patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
                patch.object(subprocess, "run", side_effect=AssertionError("process")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("process")):
            self.assertEqual(self.collect()["status"], "ok")
            self.recorded_failure()
            self.assertEqual(self.collect()["status"], "ok")
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertNotIn("open_webui", sys.modules)

    def test_unsupported_creation_time_has_no_linux_ctime_fallback(self):
        with patch.object(REPORT, "_created_at", side_effect=NotImplementedError):
            self.assertEqual(self.collect()["reason"], "creation_time_unsupported")

    def test_file_change_during_read_invalidates_summary(self):
        original = Path.open

        def opened(path, *args, **kwargs):
            if path == self.candidate and args == ("rb",):
                with original(path, "ab") as handle:
                    handle.write(b"changed\n")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", opened):
            result = self.collect()
            self.recorded_failure()
            exact_result = self.collect()
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "candidate_log_changed")
        self.assertEqual(exact_result["status"], "ambiguous")
        self.assertEqual(exact_result["reason"], "candidate_log_changed")


class RecoveryIncidentReportTests(unittest.TestCase):
    SECRET = "SYNTHETIC_PRIVATE_65C9"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.config = {"state_root": str(self.root)}
        self.old_log = self.logs / ("server-" + "a" * 32 + ".log")
        self.active_log = self.logs / ("server-" + "b" * 32 + ".log")
        self.old_log.write_bytes(self.trace().encode())
        self.active_log.write_bytes(b"current server\n")
        self.registry = {"schema_version": 2, "phase": "idle", "pending": None,
                         "customization": {"pending": None},
                         "process": {"log_file": str(self.active_log)}}
        self.registry_path = self.root / "deployment.json"
        self.registry_path.write_text(json.dumps(self.registry), encoding="utf-8")
        self.request = {"failure": {"action": "upgrade", "failed": True,
            "at": "2026-09-10T12:00:00+00:00", "result": {"stage": "process_stop", "changed": False,
                "wrapper_commit": REPORT._RECOVERY_COMMIT, "process": {"error_type": "process"}}},
            "registry": {"schema_version": 2, "process": {"log_file": str(self.old_log)}}}
        self.request_path = self.root / ("stop-recovery-" + "c" * 32 + ".json")
        self.save_request()

    def save_request(self):
        self.request_path.write_text(json.dumps(self.request), encoding="utf-8-sig")

    @classmethod
    def trace(cls, *, message=True, loop=True, future=True, error=64):
        value = ("ERROR:    Accept failed on a socket\nsocket: " + cls.SECRET + "\n") if message else ""
        value += "Traceback (most recent call last):\n"
        if loop:
            value += f'  File "C:/Users/{cls.SECRET}/Python/Lib/asyncio/proactor_events.py", line 835, in loop\n'
            value += "    conn, addr = f.result()\n"
        if future:
            value += f'  File "C:/Users/{cls.SECRET}/Python/Lib/asyncio/windows_events.py", line 605, in accept_coro\n'
            value += "    await future\n"
        return value + f"OSError: [WinError {error}] {cls.SECRET}\n"

    def inspect(self):
        return REPORT.inspect_recovery(self.config)

    def test_exact_recorded_trace_is_read_without_process_or_network_calls_or_writes(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(subprocess, "Popen", side_effect=AssertionError("process call")), \
                patch.object(socket, "socket", side_effect=AssertionError("network call")):
            result = self.inspect()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scan_scope"], "full")
        self.assertTrue(result["accept_listener64"])
        self.assertFalse(result["accept_future64"])
        self.assertFalse(result["tls_verify_failed"])
        self.assertFalse(result["truncated"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        encoded = REPORT.render_recovery(result)
        self.assertEqual(len(encoded.splitlines()), 1)
        self.assertIn("source=stop_failure", encoded)
        for private in (self.SECRET, "C:/", str(self.root), "OSError:"):
            self.assertNotIn(private, encoded)

    def test_future_error_only_is_separate_lower_confidence_evidence(self):
        self.old_log.write_text(self.trace(message=False, loop=False), encoding="utf-8")
        result = self.inspect()
        self.assertFalse(result["accept_listener64"])
        self.assertTrue(result["accept_future64"])

    def test_common_fixed_logging_prefixes_preserve_message_association(self):
        for prefix in ("", "ERROR:asyncio:", "2026-09-10 12:00:00 | ERROR | asyncio.base_events - "):
            with self.subTest(prefix=prefix):
                text = self.trace().replace("ERROR:    Accept failed", prefix + "Accept failed")
                self.assertTrue(REPORT._accept64_summary(text.encode())["accept_listener64"])

    def test_tls_and_startup_signals_are_independent_from_accept_trace(self):
        self.old_log.write_text("SSLError: certificate verify failed " + self.SECRET + "\n"
                                "Application startup complete\n" + self.trace(), encoding="utf-8")
        result = self.inspect()
        self.assertTrue(result["tls_verify_failed"])
        self.assertTrue(result["startup_complete"])
        self.assertTrue(result["accept_listener64"])

    def test_message_and_frames_from_different_errors_do_not_match(self):
        for content in (
            self.trace(error=5) + self.trace(message=False, loop=False),
            self.trace(future=False, error=5) + self.trace(message=False, loop=False),
            "Accept failed on a socket\nUNRELATED EVENT\n" + self.trace(message=False),
            "Accept failed on a socket\n" + self.trace(message=False).split("OSError:")[0]
                + self.trace(message=False, loop=False),
            "Accept failed on a socket\nTraceback (most recent call last):\n"
                '  File "C:/private/proactor_events.py", line 10, in loop\nOSError: [WinError 64] private\n',
        ):
            with self.subTest(content=content):
                result = REPORT._accept64_summary(content.encode())
                self.assertFalse(result["accept_listener64"])

    def test_missing_header_or_exception_does_not_confirm_a_trace(self):
        for content in (self.trace().replace("Traceback (most recent call last):\n", ""),
                        self.trace().split("OSError:")[0],
                        self.trace(error=5), self.trace(future=False, loop=False)):
            with self.subTest(content=content):
                self.assertFalse(REPORT._accept64_summary(content.encode())["accept_listener64"])

    def test_tail_cut_does_not_join_a_missing_message_to_trace_and_signals_are_scoped(self):
        self.old_log.write_text("certificate verify failed\nAccept failed on a socket\n"
                                + "padding\n" * 50 + self.trace(message=False), encoding="utf-8")
        with patch.object(REPORT, "MAX_LOG_BYTES", 400):
            result = self.inspect()
        self.assertEqual(result["scan_scope"], "tail")
        self.assertTrue(result["truncated"])
        self.assertFalse(result["tls_verify_failed"])
        self.assertFalse(result["accept_listener64"])
        self.assertLessEqual(result["bytes_read"], 400)

    def test_duplicate_requests_select_same_log_without_timestamp_guessing(self):
        other = self.root / ("stop-recovery-" + "d" * 32 + ".json")
        other.write_bytes(self.request_path.read_bytes())
        unrelated = self.logs / ("server-" + "e" * 32 + ".log")
        unrelated.write_bytes(b"later unrelated log\n")
        with patch.object(REPORT, "_created_at", side_effect=AssertionError("creation inference")):
            self.assertTrue(self.inspect()["accept_listener64"])

    def test_multiple_distinct_recorded_logs_are_ambiguous(self):
        other_log = self.logs / ("server-" + "e" * 32 + ".log")
        other_log.write_bytes(b"another incident\n")
        other = deepcopy(self.request)
        other["registry"]["process"]["log_file"] = str(other_log)
        (self.root / ("stop-recovery-" + "d" * 32 + ".json")).write_text(json.dumps(other))
        self.assertEqual(self.inspect(), {"status": "ambiguous", "reason": "multiple_recorded_stop_logs"})

    def test_active_log_and_busy_deployment_are_not_read(self):
        self.registry["process"]["log_file"] = str(self.old_log)
        self.registry_path.write_text(json.dumps(self.registry))
        self.assertEqual(self.inspect()["reason"], "recorded_log_is_active")
        (self.root / "deployment.lock").write_bytes(b"busy")
        with patch.object(REPORT, "_recovery_json", side_effect=AssertionError("evidence read")):
            self.assertEqual(self.inspect()["status"], "busy")

    def test_nonmatching_incidents_and_changed_state_do_not_select_fallback_log(self):
        for key, value in (("stage", "health_check"), ("changed", True), ("wrapper_commit", "d" * 40)):
            original = self.request["failure"]["result"][key]
            self.request["failure"]["result"][key] = value
            self.save_request()
            self.assertEqual(self.inspect()["reason"], "recorded_stop_failure_missing")
            self.request["failure"]["result"][key] = original
        self.save_request()
        self.registry["customization"]["pending"] = {"action": "apply"}
        self.registry_path.write_text(json.dumps(self.registry))
        self.assertEqual(self.inspect()["reason"], "deployment_not_idle")

    def test_outside_relative_and_nonstandard_recorded_logs_are_rejected(self):
        outside = self.root / "outside.log"
        outside.write_bytes(b"private")
        for name in (str(outside), "logs/" + self.old_log.name, str(self.logs / "wrong.log")):
            self.request["registry"]["process"]["log_file"] = name
            self.save_request()
            self.assertEqual(self.inspect()["status"], "unavailable")

    def test_linked_recovery_log_is_rejected(self):
        other = self.root / "other.log"
        other.write_bytes(b"private")
        self.old_log.unlink()
        try:
            os.link(other, self.old_log)
        except (OSError, NotImplementedError):
            self.skipTest("Hardlinks unavailable")
        self.assertEqual(self.inspect()["reason"], "unsafe_or_missing_evidence")

    def test_request_limit_and_malformed_request_do_not_fallback(self):
        self.request_path.write_bytes(b"x" * (1024 * 1024 + 1))
        self.assertEqual(self.inspect()["status"], "unavailable")
        self.request_path.write_bytes(b"{}")
        self.assertEqual(self.inspect()["reason"], "invalid_recovery_request")
        self.save_request()
        with patch.object(REPORT, "MAX_LOG_FILES", 1):
            self.assertEqual(self.inspect()["status"], "unavailable")

    def test_deep_json_in_request_registry_and_cli_config_is_sanitized(self):
        payload = ("[" * 20000 + json.dumps(self.SECRET) + "]" * 20000).encode()
        self.assertLess(len(payload), 1024 * 1024)
        for path in (self.request_path, self.registry_path):
            with self.subTest(path=path.name):
                before = path.read_bytes()
                path.write_bytes(payload)
                try:
                    result = self.inspect()
                    self.assertEqual(result, {"status": "unavailable", "reason": "evidence_unavailable"})
                    self.assertNotIn(self.SECRET, REPORT.render_recovery(result))
                finally:
                    path.write_bytes(before)
        config_path = self.root / "deep-config.json"
        config_path.write_bytes(payload)
        completed = subprocess.run([sys.executable, "-I", "-B", str(SCRIPTS / "ees_deploy_report.py"),
                                    "--inspect-recovery", "--config", str(config_path)],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        self.assertIn("code=evidence_unavailable", completed.stdout)
        self.assertEqual(completed.stderr, "")
        self.assertNotIn(self.SECRET, completed.stdout)
        self.assertNotIn("Traceback", completed.stdout)

    def test_log_append_during_read_invalidates_all_signals(self):
        original = Path.open

        def opened(path, *args, **kwargs):
            if path == self.old_log and args == ("rb",):
                with original(path, "ab") as handle:
                    handle.write(b"later content\n")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", opened):
            result = self.inspect()
        self.assertEqual(result, {"status": "ambiguous", "reason": "evidence_changed"})
        self.assertNotIn("accept_listener64", result)

    def test_registry_request_or_request_set_change_during_log_read_is_rejected(self):
        original = Path.open
        for change in ("registry", "request", "new_request", "lock"):
            with self.subTest(change=change):
                def opened(path, *args, **kwargs):
                    if path == self.old_log and args == ("rb",):
                        target = {"registry": self.registry_path, "request": self.request_path,
                                  "new_request": self.root / ("stop-recovery-" + "d" * 32 + ".json"),
                                  "lock": self.root / "deployment.lock"}[change]
                        with original(target, "ab") as handle:
                            handle.write(b" ")
                    return original(path, *args, **kwargs)
                with patch.object(Path, "open", opened):
                    self.assertEqual(self.inspect()["reason"], "evidence_changed")
                for name in ("stop-recovery-" + "d" * 32 + ".json", "deployment.lock"):
                    (self.root / name).unlink(missing_ok=True)

    def test_cli_uses_only_read_only_config_load_and_prints_one_sanitized_line(self):
        with patch.object(REPORT.states, "load_config", return_value=self.config), \
                patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            result = REPORT.main(["--inspect-recovery", "--config", str(self.root / "config.json")])
        self.assertEqual(result, 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertNotIn(self.SECRET, output.getvalue())
        with patch.object(REPORT.states, "load_config", side_effect=OSError(self.SECRET)), \
                patch.object(sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(REPORT.main(["--inspect-recovery", "--config", str(self.root / "config.json")]), 1)
        self.assertNotIn(self.SECRET, output.getvalue())
        self.assertIn("code=evidence_unavailable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
