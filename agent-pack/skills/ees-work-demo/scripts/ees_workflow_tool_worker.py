"""One short-lived Native-compatible authoring trial, never a security sandbox.

The parent supplies exact saved content and one account's current credentials
over stdin. User output and tracebacks are discarded; only a bounded result is
written to the protocol descriptor. The parent cleans Native's temporary loader
files even when this process times out. Credentials are never written to them.
"""
import asyncio
from contextlib import contextmanager
import inspect
import json
import os
import sys

MAX_INPUT_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024


class TrialStageError(Exception):
    """Carry a fixed stage only; the parent never receives the raw cause."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@contextmanager
def _stage(name):
    try:
        yield
    except Exception as error:
        raise TrialStageError("tool_trial_worker_" + name + "_failed") from error


async def invoke(payload):
    with _stage("import"):
        from open_webui.utils.plugin import extract_frontmatter, load_tool_module_by_id
        from open_webui.utils.tools import get_async_tool_function_and_apply_extra_params
        from starlette.requests import Request

    code = payload["code"]
    frontmatter = extract_frontmatter(code)
    if any(str(key).lower() == "requirements" and str(value).strip() for key, value in frontmatter.items()):
        return {"status": "failed", "error_code": "native_requirements_unsupported", "raw_result": None}
    # Explicit content avoids Native's content-rewrite branch. The dedicated
    # process has no shared module instance or per-account plugin cache.
    with _stage("load"):
        instance, _ = await load_tool_module_by_id(payload["worker_id"], content=code)
    with _stage("configure"):
        if hasattr(instance, "Valves"):
            model = instance.Valves
            fields = getattr(model, "model_fields", None)
            if not isinstance(fields, dict):
                return {"status": "failed", "error_code": "tool_trial_configuration_invalid", "raw_result": None}
            values = {name: payload["base_url"] for name in fields
                      if name == "BASE_URL" or name.endswith("_BASE_URL")}
            # Every other field keeps the author's own default/validator. In
            # particular ENABLED and ALLOW_HTTP are never forced to true.
            instance.valves = model(**values)
        actor = dict(payload["actor"])
        if hasattr(instance, "UserValves"):
            actor["valves"] = instance.UserValves(PAT=payload["token"])
        else:
            from types import SimpleNamespace
            actor["valves"] = SimpleNamespace(PAT=payload["token"])
        function = getattr(instance, payload["function"])
        supported_reserved = {"__user__", "__id__", "__request__", "__metadata__"}
        if any(name.startswith("__") and name not in supported_reserved and parameter.default is inspect.Parameter.empty
               for name, parameter in inspect.signature(function).parameters.items()):
            return {"status": "failed", "error_code": "tool_trial_reserved_unsupported", "raw_result": None}
    with _stage("bind"):
        request = Request({"type": "http", "method": "POST", "path": "/api/ees-work/tool-trial",
                           "headers": [], "query_string": b""})
        bound = await get_async_tool_function_and_apply_extra_params(function, {
            "__user__": actor, "__id__": payload["native_id"], "__request__": request,
            "__metadata__": {"kind": "authored_tool_trial"},
        })
    with _stage("invoke"):
        raw = await bound(**payload["inputs"])
    # Native tools may return JSON text. Preserve other strings for the parent
    # to classify as a mapping error rather than inventing a successful result.
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_RESULT_BYTES:
            return {"status": "failed", "error_code": "tool_trial_result_too_large", "raw_result": None}
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    result = {"status": "succeeded", "raw_result": raw}
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {"status": "failed", "error_code": "tool_trial_result_invalid", "raw_result": None}
    if len(encoded) > MAX_RESULT_BYTES:
        return {"status": "failed", "error_code": "tool_trial_result_too_large", "raw_result": None}
    return result


def main():
    # Hide Python prints, logging, native-loader errors and direct writes to
    # stdout/stderr before importing Native or the administrator's code.
    protocol = os.dup(sys.stdout.fileno())
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
        os.dup2(sink.fileno(), sys.stderr.fileno())
    result = {"status": "unknown", "error_code": "tool_trial_worker_failed", "raw_result": None}
    try:
        packed = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(packed) > MAX_INPUT_BYTES:
            result = {"status": "failed", "error_code": "tool_trial_input_too_large", "raw_result": None}
        else:
            payload = json.loads(packed)
            result = asyncio.run(invoke(payload))
    except TrialStageError as error:
        result = {"status": "unknown", "error_code": error.code, "raw_result": None}
    except BaseException:
        # Raw exception values can contain credentials or returned documents.
        # An arbitrary user's module may already have performed external work.
        pass
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            encoded = b'{"status":"failed","error_code":"tool_trial_result_too_large","raw_result":null}'
        while encoded:
            encoded = encoded[os.write(protocol, encoded):]
    except BaseException:
        pass
    finally:
        os.close(protocol)


if __name__ == "__main__":
    main()
