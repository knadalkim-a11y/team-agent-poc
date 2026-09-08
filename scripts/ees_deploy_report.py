"""Read one inferred failed-startup log without running or changing the server.

Only fixed labels and public Python frame locations leave this module. Creation
times identify a likely log, not a durable association with a deployment attempt.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys

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
    frames, errors, tracebacks = [], [], 0
    for line in text.splitlines():
        if line == "Traceback (most recent call last):":
            frames = []
            tracebacks += 1
        match = _FRAME.fullmatch(line)
        if match:
            frames.append(_frame_label(*match.groups()))
        match = re.match(r"^((?:[A-Za-z_][A-Za-z_0-9]*\.)*[A-Za-z_][A-Za-z_0-9]*)(?::|$)", line)
        if match:
            name = match[1].rsplit(".", 1)[-1]
            if name in _ERRORS or name.endswith(("Error", "Exception")):
                label = name if name in _ERRORS else "other"
                if label not in errors:
                    errors.append(label)
    return {
        "scan_scope": scope, "log_bytes": log_bytes, "bytes_read": len(payload),
        "tracebacks_seen": tracebacks, "last_traceback_header_seen": tracebacks > 0,
        "error_types": errors,
        "signals": {key: any(marker in folded for marker in markers) for key, markers in _SIGNALS.items()},
        "frames": frames[-MAX_FRAMES:], "frames_omitted": max(0, len(frames) - MAX_FRAMES),
        "unknown_frames": frames.count("other"),
    }


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
        before = candidate.stat()
        scope = "tail" if before.st_size > MAX_LOG_BYTES else "full"
        with candidate.open("rb") as handle:
            handle.seek(max(0, before.st_size - MAX_LOG_BYTES))
            payload = handle.read(MAX_LOG_BYTES)
        after = candidate.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            return _unavailable("candidate_log_changed", ambiguous=True)
        if scope == "tail":
            payload = payload.partition(b"\n")[2]
        result = _summarize(payload, scope=scope, log_bytes=before.st_size)
        return {"status": "ok", "selection": "inferred_from_creation_time",
                "candidate_seconds": round(max(0, failed - created), 1),
                "recovery_seconds": round(updated - active_created, 1), **result}
    except NotImplementedError:
        return _unavailable("creation_time_unsupported")
    except states.StateError:
        return _unavailable("unsafe_or_missing_log_path")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return _unavailable("log_or_record_unavailable")
