"""Refuse retired ApplyDemo and retain the fixed-origin Native API transport.

The compatibility CLI stops before credentials, configuration, Git or API calls.
Transport/private credential helpers serve explicit reviewed retirement; shared
trial-source/report helpers remain used by the existing deployment wrapper.
"""

import argparse
import getpass
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ees_upgrade as upgrade
import ees_demo_assets as assets

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE = 8 * 1024 * 1024


class DemoError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DemoError("redirect_blocked")


def base_url(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        raise DemoError("webui_url_invalid") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value or "%" in parsed.netloc
            or any(p in {".", ".."} for p in parsed.path.split("/"))
            or (port is not None and not 1 <= port <= 65535)):
        raise DemoError("webui_url_invalid")
    return value.rstrip("/")


def configured_url(config):
    host = config["host"]
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1" if host == "0.0.0.0" else "::1"
    if ":" in host:
        host = "[" + host + "]"
    return base_url(f"http://{host}:{config['port']}")


class WebUIClient:
    """Fixed-origin JSON client. No proxy inheritance, redirects, or raw errors."""
    def __init__(self, url, token="", ca_file=None, timeout=30):
        self.url = base_url(url)
        self.token = token
        self.timeout = timeout
        try:
            context = ssl.create_default_context(cafile=ca_file)
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))
        except (OSError, ValueError, ssl.SSLError):
            raise DemoError("ca_file_invalid") from None

    def request(self, method, path, body=None):
        if (method not in {"GET", "POST"} or not path.startswith("/api/")
                or urlsplit(path).netloc or "\\" in path or "#" in path
                or any(ord(c) < 32 for c in path)
                or any(p in {".", ".."} for p in urlsplit(path).path.split("/"))):
            raise DemoError("api_path_invalid")
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except HTTPError as error:
            code = error.code
            error.close()
            if code == 404 and method == "GET":
                return None
            if path.startswith(assets.ASSET_API + "/"):
                if code == 409:
                    raise DemoError("concurrent_edit") from None
                if code in {404, 405, 503}:
                    raise DemoError("conditional_write_unavailable") from None
            category = {401: "webui_authentication_failed", 403: "webui_permission_denied",
                        409: "api_conflict", 429: "api_rate_limited"}.get(code, "api_request_failed")
            raise DemoError(category) from None
        except (URLError, OSError, TimeoutError, HTTPException):
            raise DemoError("webui_connection_failed") from None
        if len(raw) > MAX_RESPONSE:
            raise DemoError("api_response_too_large")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise DemoError("api_response_invalid") from None


def read_private(path, limit=65536):
    if not path.exists() and not path.is_symlink():
        return None
    upgrade.manager.states._regular(path)
    if path.stat().st_size > limit:
        raise DemoError("local_state_invalid")
    try:
        return json.loads(path.read_bytes())
    except (ValueError, UnicodeError):
        raise DemoError("local_state_invalid") from None


def connection(config, args):
    path = Path(config["state_root"]) / "demo-connection.json"
    saved = read_private(path) or {}
    if not isinstance(saved, dict):
        raise DemoError("local_state_invalid")
    url = base_url(args.webui_url or saved.get("url") or configured_url(config))
    if saved.get("url") and url != saved["url"]:
        # Explicitly changing the endpoint must not carry its target-model ID.
        saved = {}
    return path, {"schema_version": 1, "url": url,
                  "ees_model_id": args.ees_model_id or saved.get("ees_model_id"),
                  "ca_file": args.ca_file or saved.get("ca_file")}


def token_path(config, url):
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    return Path(config["state_root"]) / f"webui-demo-{digest}.dpapi"


def valid_token(token):
    return (isinstance(token, str) and 10 <= len(token) <= 4096
            and all(33 <= ord(c) <= 126 for c in token))


def load_token(config, url, reset=False):
    path = token_path(config, url)
    if (path.exists() or path.is_symlink()) and not reset:
        upgrade.manager.states._regular(path)
        if path.stat().st_size > 16384:
            raise DemoError("webui_credentials_invalid")
        try:
            saved = json.loads(upgrade.manager.states._unprotect(path.read_bytes()))
            if saved.get("url") != url or not valid_token(saved.get("token")):
                raise ValueError()
            return saved["token"], False
        except (ValueError, UnicodeError, AttributeError):
            raise DemoError("webui_credentials_invalid") from None
    if not sys.stdin.isatty():
        raise DemoError("webui_credentials_required")
    token = getpass.getpass("Open WebUI administrator API key (hidden; separate from GitHub PAT): ")
    if not valid_token(token):
        raise DemoError("webui_credentials_invalid")
    return token, True


def save_token(config, url, token):
    path = token_path(config, url)
    if path.exists() or path.is_symlink():
        upgrade.manager.states._regular(path)
    data = json.dumps({"url": url, "token": token}).encode()
    encrypted = upgrade.manager.states._protect(data)
    # Persist only the DPAPI ciphertext, using an atomic private-file replacement.
    import os
    import tempfile
    fd, temp = tempfile.mkstemp(prefix="webui-demo-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def safe_label(value):
    return "".join(c for c in str(value) if c.isprintable())[:100]


def select_ees(client, chosen=None):
    if chosen:
        if not isinstance(chosen, str) or not 1 <= len(chosen) <= 255 or any(ord(c) < 32 for c in chosen):
            raise DemoError("ees_model_invalid")
        return chosen
    candidates = []
    seen = 0
    for page in range(1, 21):
        value = client.request("GET", "/api/v1/models/list?" + urlencode({"page": page}))
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise DemoError("model_list_invalid")
        candidates.extend(m for m in value["items"] if isinstance(m, dict) and m.get("base_model_id")
                          and m.get("id") not in {"ees_demo_ems", "ees_demo_apc", "ees_demo_fdc"})
        seen += len(value["items"])
        total = value.get("total")
        if not value["items"] or (isinstance(total, int) and seen >= total):
            break
    else:
        raise DemoError("model_list_too_large")
    exact = [m for m in candidates if m.get("name") == "EES 통합 Assistant"]
    if len(exact) == 1:
        return exact[0]["id"]
    if not candidates:
        raise DemoError("existing_ees_model_required")
    if not sys.stdin.isatty():
        raise DemoError("ees_model_selection_required")
    print("Select the existing EES Assistant once:")
    for number, model in enumerate(candidates, 1):
        print(f"  {number}. {safe_label(model.get('name', 'Unnamed model'))}")
    try:
        number = int(input("Existing EES number: "))
        if not 1 <= number <= len(candidates):
            raise ValueError()
        return candidates[number - 1]["id"]
    except (ValueError, EOFError):
        raise DemoError("ees_model_selection_required") from None


def trial_checkout(commit):
    """Verify the explicitly chosen local main without selecting/fetching a release."""
    upgrade.checkout(commit)
    if upgrade.git("rev-parse", "origin/main")[1] != commit:
        raise DemoError("trial_main_mismatch")
    return commit


def apply(config, args, commit, progress):
    """Old operator entry points cannot recreate removed demo content."""
    progress.update(stage="retired", changed=0)
    raise DemoError("demo_registration_retired")


def report(config_path, result, failed=False):
    def word(value):
        return value if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.+-]{1,80}", value) else "-"
    commit = result.get("source_commit")
    commit = commit[:12] if isinstance(commit, str) and upgrade.HEX40.fullmatch(commit) else "-"
    changed = result.get("changed")
    changed = changed if type(changed) is int and changed >= 0 else "-"
    pending = result.get("pending") is True
    if pending:
        changed = "-"
    saved = upgrade.manager.save_operation(argparse.Namespace(action="apply_demo", config=config_path),
                                            result, failed=failed)
    print(f"EES action=apply_demo result={'failed' if failed else 'ok'} changed={changed} "
          f"commit={commit} stage={word(result.get('stage'))} code={word(result.get('code'))} "
          f"next={word(result.get('next'))}" + (" pending=true" if pending else "")
          + (" report=unavailable" if not saved else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--webui-url")
    parser.add_argument("--ees-model-id")
    parser.add_argument("--ca-file")
    parser.add_argument("--reset-token", action="store_true")
    parser.add_argument("--reset-update-token", action="store_true")
    parser.add_argument("--trial-commit", help=("Apply a reviewed full commit from the clean canonical main "
                                               "checkout; origin/main and the installed program must match. "
                                               "Does not check GitHub Actions."))
    parser.add_argument("--prepared-head", help=argparse.SUPPRESS)
    parser.add_argument("--wrapper-before", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if (bool(args.prepared_head) != bool(args.wrapper_before)
            or any(v and not upgrade.HEX40.fullmatch(v) for v in (args.prepared_head, args.wrapper_before))):
        parser.error("Invalid prepared update identity.")
    if args.trial_commit is not None and (not upgrade.HEX40.fullmatch(args.trial_commit)
                              or args.prepared_head or args.wrapper_before or args.reset_update_token):
        parser.error("Trial commit requires a full lowercase commit SHA and cannot use release-bootstrap options.")
    # Refuse before configuration, credentials, GitHub, product or Native API reads.
    print("EES action=apply_demo result=blocked changed=0 stage=retired "
          "code=demo_registration_retired next=asset_retirement_preview")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
