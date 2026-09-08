"""Bounded, sequential NLTK import measurements; never starts Open WebUI.

Imports execute installed code, including site hooks. This is an isolated import
comparison, not a sandbox or a reproduction of the registered server environment.
Raw child output stays in temporary files; only fixed/public labels leave here.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

from ees_deploy_report import _ERRORS, _PUBLIC, _frame_label


WATCHDOG_SECONDS = 60
PARENT_SECONDS = 70
MAX_BYTES = 4 * 1024 * 1024
_TIMING = re.compile(r"import time:\s*([0-9]{1,16})\s*\|\s*[0-9]{1,16}\s*\|\s*([A-Za-z_][A-Za-z_0-9.]*)\s*\Z")
_FRAME = re.compile(r'\s*File "([^"\r\n]{1,2048})", line ([0-9]{1,8})(?:,? in ([A-Za-z0-9_.<>]{1,80}))?\s*\Z')
_MARKERS = {"watchdog_armed": "EES_IMPORT_WATCHDOG_ARMED",
            "import_entered": "EES_IMPORT_ENTERED", "import_completed": "EES_IMPORT_COMPLETED"}


def _program():
    # Keep the watchdog armed through exception handling and interpreter exit.
    return f'''import faulthandler
faulthandler.dump_traceback_later({WATCHDOG_SECONDS!r}, exit=True)
print("EES_IMPORT_WATCHDOG_ARMED", flush=True)
import site
site.main()
print("EES_IMPORT_ENTERED", flush=True)
import nltk
print("EES_IMPORT_COMPLETED", flush=True)
'''


def _environment():
    keep = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC",
            "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"}
    return {key: value for key, value in os.environ.items() if key.upper() in keep}


def _module_label(name):
    if len(name) <= 160 and name.split(".", 1)[0] in _PUBLIC | sys.stdlib_module_names:
        return name
    return "other"


def _read(stream):
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(max(0, size - MAX_BYTES))
    payload = stream.read(MAX_BYTES)
    if size > MAX_BYTES:
        # A truncated first line must not be interpreted as a complete record.
        payload = payload.partition(b"\n")[2]
    return payload.decode("utf-8", errors="replace"), size


def _summarize(stdout, stderr, stdout_bytes, stderr_bytes):
    markers = {key: value in stdout.splitlines() for key, value in _MARKERS.items()}
    events, total_us, top, last, errors = 0, 0, [], None, []
    watchdog, threads, frame_count, frames = False, 0, 0, []
    traceback, error_count, error_frames = False, 0, []
    for line in stderr.splitlines():
        match = _TIMING.fullmatch(line)
        if match:
            micros, name = int(match[1]), _module_label(match[2])
            events, total_us, last = events + 1, total_us + micros, name
            top = sorted(top + [(micros, name)], reverse=True)[:5]
        if re.fullmatch(r"Timeout \([0-9:.]+\)!", line):
            watchdog = True
        if watchdog and re.fullmatch(r"(?:Current thread|Thread) 0x[0-9a-fA-F]+ \(most recent call first\):", line):
            threads += 1
        if line == "Traceback (most recent call last):":
            traceback, error_count, error_frames = True, 0, []
        match = _FRAME.fullmatch(line)
        if watchdog and threads == 1 and match:
            frame_count += 1
            if len(frames) < 10:
                frames.append(_frame_label(*match.groups()))
        elif traceback and not watchdog and match:
            error_count += 1
            error_frames = (error_frames + [_frame_label(*match.groups())])[-6:]
        match = re.match(r"^((?:[A-Za-z_][A-Za-z_0-9]*\.)*[A-Za-z_][A-Za-z_0-9]*)(?::|$)", line)
        if match:
            name = match[1].rsplit(".", 1)[-1]
            if name in _ERRORS or name.endswith(("Error", "Exception")):
                label = name if name in _ERRORS else "other"
                if label not in errors:
                    errors.append(label)
                traceback = False
    return {**markers, "watchdog_dump_seen": watchdog,
            "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes,
            "stdout_scope": "tail" if stdout_bytes > MAX_BYTES else "full",
            "stderr_scope": "tail" if stderr_bytes > MAX_BYTES else "full",
            "timed_import_events": events, "observed_self_seconds": round(total_us / 1e6, 6),
            "top_self": [{"module": name, "seconds": round(micros / 1e6, 6)} for micros, name in top],
            "last_timed_import": last, "error_types": errors,
            "watchdog_threads_seen": threads, "watchdog_first_thread_frames": frames,
            "watchdog_first_thread_frames_omitted": max(0, frame_count - 10),
            "last_error_frames": [] if watchdog else error_frames,
            "last_error_frames_omitted": 0 if watchdog else max(0, error_count - 6)}


def _measure(executable):
    started, interrupted, unverified = time.monotonic(), False, False
    # On Windows a venv launcher can own a second process. Killing the launcher
    # after the parent deadline cannot establish that the import child stopped.
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    with tempfile.TemporaryDirectory(prefix="ees-import-", ignore_cleanup_errors=True) as directory, \
            tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        try:
            child = subprocess.Popen([str(executable), "-I", "-S", "-B", "-X", "importtime", "-c", _program()],
                                     cwd=directory, env=_environment(), stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, **options)
        except OSError as error:
            return {"status": "launch_failed", "error_type": type(error).__name__ if type(error).__name__ in _ERRORS else "other",
                    "elapsed_seconds": round(time.monotonic() - started, 3), "cleanup_unverified": False}
        try:
            child.wait(timeout=max(0, PARENT_SECONDS - (time.monotonic() - started)))
        except KeyboardInterrupt:
            # Ctrl+C reaches the parent only. Let the child's existing watchdog
            # finish; do not remove its deadline or launch the second comparison.
            interrupted = True
            try:
                child.wait(timeout=max(0, PARENT_SECONDS - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                unverified = True
        except subprocess.TimeoutExpired:
            unverified = True
        if unverified:
            try:
                child.kill()
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        elapsed = round(time.monotonic() - started, 3)
        out, out_size = _read(stdout)
        err, err_size = _read(stderr)
        summary = _summarize(out, err, out_size, err_size)
        status = ("parent_timeout_cleanup_unverified" if unverified else "interrupted" if interrupted
                  else "watchdog_timeout" if summary["watchdog_dump_seen"]
                  else "completed" if child.returncode == 0 and all(summary[key] for key in _MARKERS)
                  else "import_failed" if summary["import_entered"] else "probe_incomplete")
        return {"status": status, "elapsed_seconds": elapsed, "exit_code": child.returncode,
                "cleanup_unverified": unverified, **summary}


def compare(original_python, candidate_python):
    results = []
    for label, executable in (("original", original_python), ("candidate", candidate_python)):
        if results and (results[-1]["cleanup_unverified"] or results[-1]["status"] == "interrupted"):
            results.append({"program": label, "status": "skipped_after_incomplete_probe"})
            break
        results.append({"program": label, **_measure(executable)})
    return {"report_version": 1, "target": "nltk", "watchdog_seconds": WATCHDOG_SECONDS,
            "parent_seconds": PARENT_SECONDS, "results": results}


def _handoff_status(result):
    status = result.get("status")
    if result.get("cleanup_unverified") is True or status in {"parent_timeout", "parent_timeout_cleanup_unverified"}:
        return "CLEANUP"
    if status == "watchdog_timeout":
        # A truncated marker stream cannot establish which phase was reached.
        if result.get("stdout_scope") == "tail":
            return "TIME-?"
        for marker, label in (("import_completed", "TIME-EXIT"), ("import_entered", "TIME-IMPORT"),
                              ("watchdog_armed", "TIME-SITE")):
            if result.get(marker) is True:
                return label
        return "TIME-?"
    return {"completed": "OK", "interrupted": "STOP", "import_failed": "ERROR",
            "launch_failed": "LAUNCH", "probe_incomplete": "UNKNOWN",
            "skipped_after_incomplete_probe": "SKIP"}.get(status, "UNKNOWN")


def _handoff_line(report):
    """One short, fixed-label line for an operator who can only retype results."""
    parts, errors, partial = ["SEND I1"], [], False
    rows = report.get("results", [])
    for program, label in (("original", "O"), ("candidate", "C")):
        result = next((row for row in rows if isinstance(row, dict) and row.get("program") == program), {})
        status, seconds = _handoff_status(result), result.get("elapsed_seconds")
        elapsed = (f"{seconds:.1f}" if type(seconds) in (int, float) and 0 <= seconds <= 86400 else "-")
        parts.append(f"{label}={status}/{elapsed}")
        partial = partial or result.get("stdout_scope") == "tail" or result.get("stderr_scope") == "tail"
        if status in {"ERROR", "LAUNCH"}:
            names = result.get("error_types", [])
            name = names[0] if isinstance(names, list) and names else result.get("error_type")
            if isinstance(name, str) and name in _ERRORS:
                errors.append(f"err{label}={name}")
            elif name is not None:
                errors.append(f"err{label}=OTHER")
    parts.append("saved=" + ("yes" if report.get("report_saved") is True else "no"))
    if partial:
        parts.append("partial=yes")
    return " ".join(parts + errors)


def render(report):
    commit = report.get("source_commit")
    source = commit[:12] if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) else "unknown"
    lines = ["EES import comparison v1",
             f"target: nltk; watchdog: {WATCHDOG_SECONDS}s; parent: {PARENT_SECONDS}s; source: {source}",
             "sequential; isolated environment; not a server startup test"]
    for result in report["results"]:
        main = {key: value for key, value in result.items()
                if key not in {"top_self", "watchdog_first_thread_frames", "last_error_frames"}}
        lines.append(json.dumps(main, ensure_ascii=True, separators=(",", ":")))
        if result.get("top_self"):
            lines.append("top_self: " + json.dumps(result["top_self"], separators=(",", ":")))
        if result.get("watchdog_first_thread_frames"):
            lines.append("watchdog_first_thread (most recent call first):")
            lines.extend(result["watchdog_first_thread_frames"])
        if result.get("last_error_frames"):
            lines.append("last_error_traceback (most recent call last):")
            lines.extend(result["last_error_frames"])
    lines.append(_handoff_line(report))
    return "\n".join(lines)
