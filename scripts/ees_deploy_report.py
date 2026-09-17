"""Read one failed-startup log without running or changing the server.

Recorded log IDs bind new failures to their logs. Legacy creation times identify
only a likely log. Only fixed labels and public Python frame locations leave here.
"""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ees_deploy_state as states


MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_FRAMES = 20
MAX_LOG_FILES = 1000
_LOG_NAME = re.compile(r"server-[0-9a-f]{32}\.log\Z")
_FRAME = re.compile(r'\s*File "([^"\r\n]{1,2048})", line ([0-9]{1,8})(?:, in ([A-Za-z0-9_.<>]{1,80}))?\s*\Z')
_PUBLIC = frozenset("""
open_webui alembic sqlalchemy chromadb numpy scipy pandas sklearn sympy numba
torch torchvision torchaudio transformers sentence_transformers tokenizers
huggingface_hub safetensors langchain langchain_core langchain_community
langchain_classic langchain_text_splitters unstructured nltk playwright bs4
lxml requests urllib3 httpx httpcore aiohttp anyio sniffio fastapi starlette
uvicorn pydantic pydantic_core socketio engineio redis peewee onnxruntime
tiktoken sentencepiece PIL cv2 cryptography certifi jinja2 packaging tqdm
typing_extensions importlib_metadata fsspec filelock datasets accelerate
""".split())
_ERRORS = frozenset("""
KeyboardInterrupt SystemExit SyntaxError IndentationError TabError ImportError
ModuleNotFoundError FileNotFoundError PermissionError OSError IOError ValueError
TypeError KeyError AttributeError RuntimeError MemoryError RecursionError
TimeoutError ConnectionError ConnectionRefusedError ConnectionResetError
SSLError SSLCertVerificationError ProxyError ConnectTimeout ReadTimeout
ConnectTimeoutError ReadTimeoutError NewConnectionError NameResolutionError
MaxRetryError HTTPError HTTPStatusError HfHubHTTPError LocalEntryNotFoundError
OfflineModeIsEnabled RepositoryNotFoundError RevisionNotFoundError
EntryNotFoundError OperationalError DatabaseError ValidationError
""".split())
_SIGNALS = {
    "startup_complete": ("application startup complete",),
    "listening": ("uvicorn running on",),
    "cert_verify_failed": ("certificate_verify_failed", "certificate verify failed"),
    "proxy_error": ("proxyerror", "proxy error", "cannot connect to proxy"),
    "connect_timeout": ("connecttimeout", "connection timed out"),
    "read_timeout": ("readtimeout", "read timed out"),
    "dns_error": ("nameresolutionerror", "getaddrinfo failed", "temporary failure in name resolution"),
    "download_activity": ("downloading", "fetching files", "snapshot_download", "hf_hub_download"),
    "model_cache_missing": ("localentrynotfounderror", "cannot find the requested files in the local cache"),
}


def _created_at(path):
    """Windows ctime is creation time on supported Python 3.11; Unix is not."""
    if os.name != "nt":
        raise NotImplementedError()
    info = path.stat()
    return getattr(info, "st_birthtime", info.st_ctime)


def _unavailable(reason, *, ambiguous=False):
    return {"status": "ambiguous" if ambiguous else "unavailable", "reason": reason}


def _frame_label(path, number, function):
    path = path.replace("\\", "/")
    match = re.fullmatch(r"<frozen (importlib\.[A-Za-z_.]+|[A-Za-z_]+)>", path)
    if match and (match[1].startswith("importlib.") or match[1] in sys.stdlib_module_names):
        label = "frozen/" + match[1]
    else:
        match = re.search(r"/site-packages/([A-Za-z_][A-Za-z_0-9]*(?:/[A-Za-z_0-9]+)*\.py)\Z", path)
        if match:
            relative = match[1]
            if relative.split("/", 1)[0].removesuffix(".py") not in _PUBLIC:
                return "other"
            label = relative
        else:
            match = re.search(r"/[Ll]ib/(?:python[0-9.]+/)?([A-Za-z_][A-Za-z_0-9]*(?:/[A-Za-z_0-9]+)*\.py)\Z", path)
            if not match or match[1].split("/", 1)[0].removesuffix(".py") not in sys.stdlib_module_names:
                return "other"
            label = "stdlib/" + match[1]
    if len(label) > 160:
        return "other"
    return f"{label}:{number}:{function or '<syntax>'}"


def _summarize(payload, *, scope, log_bytes):
    text = payload.decode("utf-8", errors="replace")
    folded = text.lower()
    errors, tracebacks, sequence = [], 0, 0
    first_error = None

    def traceback_record(header=False):
        return {"id": sequence, "frames": deque(maxlen=MAX_FRAMES), "count": 0,
                "unknown": 0, "header": header, "completed": False, "error_type": None}

    current = traceback_record()
    for line in text.splitlines():
        if line == "Traceback (most recent call last):":
            sequence += 1
            current = traceback_record(header=True)
            tracebacks += 1
        match = _FRAME.fullmatch(line)
        if match:
            # SyntaxError may start a new location without a Traceback header.
            if current["completed"]:
                sequence += 1
                current = traceback_record()
            label = _frame_label(*match.groups())
            current["frames"].append(label)
            current["count"] += 1
            current["unknown"] += label == "other"
        match = re.match(r"^((?:[A-Za-z_][A-Za-z_0-9]*\.)*[A-Za-z_][A-Za-z_0-9]*)(?::|$)", line)
        if match:
            name = match[1].rsplit(".", 1)[-1]
            if name in _ERRORS or name.endswith(("Error", "Exception")):
                label = name if name in _ERRORS else "other"
                if label not in errors:
                    errors.append(label)
                current["completed"] = True
                current["error_type"] = label
                if first_error is None and name not in {"KeyboardInterrupt", "SystemExit"}:
                    first_error = {**current, "frames": list(current["frames"])}
    same_traceback = first_error is not None and first_error["id"] == current["id"]
    first_budget = min(MAX_FRAMES // 2, first_error["count"]) if first_error and not same_traceback else 0
    last_budget = MAX_FRAMES - first_budget
    first_frames = first_error["frames"][-first_budget:] if first_budget else []
    first_visible = last_budget if same_traceback else first_budget
    return {
        "scan_scope": scope, "log_bytes": log_bytes, "bytes_read": len(payload),
        "tracebacks_seen": tracebacks, "last_traceback_header_seen": current["header"],
        "error_types": errors,
        "signals": {key: any(marker in folded for marker in markers) for key, markers in _SIGNALS.items()},
        "frames": list(current["frames"])[-last_budget:],
        "frames_omitted": max(0, current["count"] - last_budget),
        "unknown_frames": current["unknown"],
        "first_error_type": first_error["error_type"] if first_error else None,
        "first_error_frames": first_frames,
        "first_error_frames_omitted": max(0, first_error["count"] - first_visible) if first_error else 0,
        "first_error_unknown_frames": first_error["unknown"] if first_error else 0,
        "first_error_traceback_header_seen": first_error["header"] if first_error else False,
        "first_error_matches_last_traceback": same_traceback,
    }


def _recorded_candidate(config, registry, failure):
    if (type(failure["evidence_version"]) is not int or failure["evidence_version"] != 1
            or not isinstance(failure.get("candidate"), dict)
            or not isinstance(failure.get("switch"), dict)):
        return _unavailable("invalid_recorded_evidence")
    candidate = failure["candidate"]
    kind, commit = candidate.get("kind"), candidate.get("source_commit")
    if (kind not in {"original", "release"} or "source_commit" not in candidate
            or (kind == "original" and commit is not None)
            or (kind == "release" and (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)))):
        return _unavailable("invalid_recorded_evidence")
    log_id = failure["switch"].get("log_id")
    if log_id is None:
        return _unavailable("recorded_log_missing")
    recovery_id = failure.get("recovery_log_id")
    if (not isinstance(log_id, str) or not _LOG_NAME.fullmatch(log_id)
            or (recovery_id is not None and (not isinstance(recovery_id, str) or not _LOG_NAME.fullmatch(recovery_id)))):
        return _unavailable("invalid_recorded_log_id")
    if log_id == recovery_id:
        return _unavailable("candidate_matches_recovery_log", ambiguous=True)
    if registry.get("phase") != "idle" or registry.get("pending") or registry.get("launch_uncertain"):
        return _unavailable("recorded_failure_not_idle")
    logs = states._safe(Path(config["state_root"]) / "logs")
    selected = states._regular(logs / log_id)
    process = registry.get("process")
    if process:
        if not isinstance(process, dict) or not isinstance(process.get("log_file"), str):
            return _unavailable("invalid_active_log_record")
        active = states._safe(process["log_file"], exists=False)
        if active == selected:
            return _unavailable("recorded_log_is_active", ambiguous=True)
    return selected, {"selection": "recorded_log_id", "candidate_seconds": None, "recovery_seconds": None}


def _inferred_candidate(config, registry, failure):
    if (registry.get("phase") != "idle" or registry.get("last_event") != "previous_program_recovered"
            or registry.get("current", {}).get("kind") != "original" or registry.get("pending")
            or registry.get("launch_uncertain") or failure.get("recovery_status") != "succeeded"
            or failure.get("switch", {}).get("stage") != "health_check"):
        return _unavailable("no_recovered_health_failure")
    failed = datetime.strptime(failure["failed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    updated = datetime.fromisoformat(registry["updated_at"])
    if updated.tzinfo is None:
        return _unavailable("invalid_timestamps")
    updated = updated.timestamp()
    logs = states._safe(Path(config["state_root"]) / "logs")
    active = states._regular(registry["process"]["log_file"])
    if active.parent != logs or not _LOG_NAME.fullmatch(active.name):
        return _unavailable("recovery_log_outside_managed_logs")
    active_created = _created_at(active)
    if not failed <= active_created <= updated:
        return _unavailable("inconsistent_recovery_time", ambiguous=True)
    candidates = []
    count = 0
    for entry in logs.iterdir():
        if not _LOG_NAME.fullmatch(entry.name):
            continue
        count += 1
        if count > MAX_LOG_FILES:
            return _unavailable("too_many_logs")
        entry = states._regular(entry)
        created = _created_at(entry)
        if entry == active:
            continue
        if created >= active_created:
            return _unavailable("later_or_tied_recovery_log", ambiguous=True)
        if created >= failed + 1:
            return _unavailable("log_between_failure_and_recovery", ambiguous=True)
        candidates.append((created, entry))
    if not candidates:
        return _unavailable("candidate_log_missing")
    candidates.sort(key=lambda item: item[0], reverse=True)
    created, candidate = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == created:
        return _unavailable("candidate_creation_time_tied", ambiguous=True)
    return candidate, {"selection": "inferred_from_creation_time",
                       "candidate_seconds": round(max(0, failed - created), 1),
                       "recovery_seconds": round(updated - active_created, 1)}


def collect(config, registry):
    """Return a sanitized summary, or a fixed reason it cannot be selected.

The caller should compare the registry before and after this unlocked read.
No URLs, exception messages, absolute paths or source lines are returned.
    """
    try:
        lock = Path(config["state_root"]) / "deployment.lock"
        if lock.exists() or lock.is_symlink():
            return {"status": "busy", "reason": "deployment_in_progress"}
        failure = registry.get("last_failure") or {}
        selected = (_recorded_candidate(config, registry, failure) if "evidence_version" in failure
                    else _inferred_candidate(config, registry, failure))
        if isinstance(selected, dict):
            return selected
        candidate, metadata = selected
        before = states._regular(candidate).stat()
        scope = "tail" if before.st_size > MAX_LOG_BYTES else "full"
        with candidate.open("rb") as handle:
            handle.seek(max(0, before.st_size - MAX_LOG_BYTES))
            payload = handle.read(MAX_LOG_BYTES)
        after = states._regular(candidate).stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            return _unavailable("candidate_log_changed", ambiguous=True)
        if scope == "tail":
            payload = payload.partition(b"\n")[2]
        result = _summarize(payload, scope=scope, log_bytes=before.st_size)
        return {"status": "ok", **metadata, **result}
    except NotImplementedError:
        return _unavailable("creation_time_unsupported")
    except states.StateError:
        return _unavailable("unsafe_or_missing_log_path")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return _unavailable("log_or_record_unavailable")


_RECOVERY_NAME = re.compile(r"stop-recovery-[0-9a-f]{32}\.json\Z")
_RECOVERY_COMMIT = "c099e427f62bcdb752fe4321e39223915cac035a"
_ACCEPT_MESSAGE = re.compile(
    r"(?:(?:ERROR|CRITICAL):(?:asyncio:)?\s*|[0-9][^\r\n]{0,200} - )?Accept failed on a socket\Z")


def _accept64_summary(payload):
    """Associate fixed labels within one complete traceback, never across errors."""
    pending, context_lines, current = False, 0, None
    listener, future = False, False
    for line in payload.decode("utf-8", errors="replace").splitlines():
        if _ACCEPT_MESSAGE.fullmatch(line):
            pending, context_lines, current = True, 0, None
            continue
        if line == "Traceback (most recent call last):":
            current = {"message": pending, "loop": False, "accept": False}
            pending = False
            continue
        if pending:
            # asyncio's default handler prints the socket context before exc_info.
            context_lines += 1
            if not line.startswith("socket: ") or context_lines > 8:
                pending = False
        if current is None:
            continue
        match = _FRAME.fullmatch(line)
        if match:
            label = _frame_label(*match.groups())
            current["loop"] |= bool(re.fullmatch(r"stdlib/asyncio/proactor_events\.py:[0-9]+:loop", label))
            current["accept"] |= bool(re.fullmatch(r"stdlib/asyncio/windows_events\.py:[0-9]+:accept_coro", label))
            continue
        if re.fullmatch(r"OSError: \[WinError 64\](?: .*)?", line):
            matched = current["message"] and current["loop"]
            listener |= matched
            future |= current["accept"] and not matched
            current = None
        elif line and not line[0].isspace():
            # An exception, chained traceback delimiter, or another log event
            # ends the association, including a different WinError in this trace.
            current = None
    return {"accept_listener64": listener, "accept_future64": future}


def _stamp(path):
    info = states._regular(path).stat()
    return info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev


def _recovery_json(path):
    before = _stamp(path)
    if before[0] > 1024 * 1024:
        raise ValueError()
    with path.open("rb") as handle:
        payload = handle.read(1024 * 1024 + 1)
    if len(payload) != before[0] or _stamp(path) != before:
        raise ValueError()
    try:
        return json.loads(payload.decode("utf-8-sig")), payload
    except RecursionError:
        # The byte limit does not bound JSON nesting. Keep parser failures out
        # of the operator output just like malformed or oversized evidence.
        raise ValueError() from None


def _recovery_paths(root):
    paths = []
    for count, path in enumerate(root.iterdir(), 1):
        if count > MAX_LOG_FILES:
            raise ValueError()
        if _RECOVERY_NAME.fullmatch(path.name):
            paths.append(path)
    return sorted(paths)


def inspect_recovery(config):
    """Read the recorded c099 stop-failure log; no server or state is changed.

    Multiple request copies may name the same log. Different recorded logs are
    ambiguous; timestamps never substitute a different server's log. This is
    the final Upgrade stop failure, not necessarily the earlier lost listener.
    """
    try:
        root = states._safe(config["state_root"])
        lock = root / "deployment.lock"
        if lock.exists() or lock.is_symlink():
            return {"status": "busy", "reason": "deployment_in_progress"}
        registry_path = root / "deployment.json"
        registry, registry_bytes = _recovery_json(registry_path)
        if (not isinstance(registry, dict) or registry.get("schema_version") != 2
                or registry.get("phase") != "idle" or registry.get("pending")
                or registry.get("launch_uncertain")
                or not isinstance(registry.get("customization"), dict)
                or registry["customization"].get("pending")):
            return _unavailable("deployment_not_idle")
        logs = states._safe(root / "logs")
        paths = _recovery_paths(root)
        snapshots, candidates = [], set()
        for path in paths:
            request, raw = _recovery_json(path)
            snapshots.append((path, raw))
            if not isinstance(request, dict) or set(request) != {"failure", "registry"}:
                return _unavailable("invalid_recovery_request")
            failure, recorded = request["failure"], request["registry"]
            if not isinstance(failure, dict) or not isinstance(recorded, dict):
                return _unavailable("invalid_recovery_request")
            result = failure.get("result")
            if (failure.get("action") != "upgrade" or failure.get("failed") is not True
                    or not isinstance(result, dict) or result.get("stage") != "process_stop"
                    or result.get("changed") is not False or result.get("wrapper_commit") != _RECOVERY_COMMIT
                    or not isinstance(result.get("process"), dict)
                    or result["process"].get("error_type") != "process"):
                continue
            process = recorded.get("process")
            if recorded.get("schema_version") != 2 or not isinstance(process, dict):
                return _unavailable("invalid_recovery_request")
            log_file = process.get("log_file")
            if not isinstance(log_file, str):
                return _unavailable("invalid_recorded_log_id")
            candidate = states._regular(log_file)
            if candidate.parent != logs or not _LOG_NAME.fullmatch(candidate.name):
                return _unavailable("recorded_log_outside_managed_logs")
            candidates.add(candidate)
        if not candidates:
            return _unavailable("recorded_stop_failure_missing")
        if len(candidates) != 1:
            return _unavailable("multiple_recorded_stop_logs", ambiguous=True)
        candidate = next(iter(candidates))
        active = registry.get("process")
        if active is not None:
            if not isinstance(active, dict) or not isinstance(active.get("log_file"), str):
                return _unavailable("invalid_active_log_record")
            if states._safe(active["log_file"], exists=False) == candidate:
                return _unavailable("recorded_log_is_active", ambiguous=True)
        before = _stamp(candidate)
        scope = "tail" if before[0] > MAX_LOG_BYTES else "full"
        with candidate.open("rb") as handle:
            handle.seek(max(0, before[0] - MAX_LOG_BYTES))
            payload = handle.read(MAX_LOG_BYTES)
        if scope == "tail":
            payload = payload.partition(b"\n")[2]
        if (lock.exists() or lock.is_symlink() or _recovery_paths(root) != paths
                or _recovery_json(registry_path)[1] != registry_bytes
                or any(_recovery_json(path)[1] != raw for path, raw in snapshots)
                or _stamp(candidate) != before):
            return _unavailable("evidence_changed", ambiguous=True)
        summary = _summarize(payload, scope=scope, log_bytes=before[0])
        return {"status": "ok", "scan_scope": scope, "bytes_read": len(payload),
                "truncated": scope == "tail", **_accept64_summary(payload),
                "tls_verify_failed": summary["signals"]["cert_verify_failed"],
                "startup_complete": summary["signals"]["startup_complete"]}
    except states.StateError:
        return _unavailable("unsafe_or_missing_evidence")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return _unavailable("evidence_unavailable")


def render_recovery(result):
    """One line containing fixed labels and bounded numbers only."""
    status = result.get("status")
    status = status if status in {"ok", "busy", "unavailable", "ambiguous"} else "unavailable"
    reasons = {"deployment_in_progress", "deployment_not_idle", "invalid_recovery_request",
               "invalid_recorded_log_id", "recorded_log_outside_managed_logs",
               "recorded_stop_failure_missing", "multiple_recorded_stop_logs",
               "invalid_active_log_record", "recorded_log_is_active", "evidence_changed",
               "unsafe_or_missing_evidence", "evidence_unavailable"}
    code = result.get("reason") if result.get("reason") in reasons else "-"
    scope = result.get("scan_scope") if result.get("scan_scope") in {"full", "tail"} else "-"
    size = result.get("bytes_read")
    size = size if type(size) is int and 0 <= size <= MAX_LOG_BYTES else "-"
    fields = " ".join(f"{key}={'true' if result.get(key) is True else 'false' if result.get(key) is False else '-'}"
                      for key in ("truncated", "accept_listener64", "accept_future64", "tls_verify_failed", "startup_complete"))
    return f"EES inspect=recovery source=stop_failure status={status} scope={scope} bytes={size} {fields} code={code}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect the saved stop-failure log without changing the server.")
    parser.add_argument("--inspect-recovery", action="store_true", required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_recovery(states.load_config(args.config))
    except (states.StateError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        result = _unavailable("evidence_unavailable")
    print(render_recovery(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
