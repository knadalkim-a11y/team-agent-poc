"""Read-only UserValves canary check for Open WebUI 0.11.3.

Run with the existing WebUI Python environment (cryptography is required).
Does not import open_webui, migrate a DB, call an API, or print stored values.
This is a DB check only; logs and restart persistence remain separate gates.
No arguments retains the Confluence check; --jira and --github check their fixed
markers in the unique EES Jira Read or EES GitHub Read Tool respectively, using
the stored tool ID internally.
"""

import base64
import hashlib
import json
import os
import sqlite3
import sys
from importlib.metadata import version
from pathlib import Path


CANARY = "EES-CANARY-20260906-7F3A9C"  # Synthetic test value, never a real PAT.
JIRA_CANARY = "EES-JIRA-CANARY-20260907-B92F6A"
GITHUB_CANARY = "EES-GITHUB-CANARY-20260907-C43D8E"


def contains_canary(path, canary):
    patterns = [canary.encode(encoding) for encoding in ("utf-8", "utf-16-le", "utf-16-be")]
    overlap = max(map(len, patterns)) - 1
    tail = b""
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            block = tail + chunk
            if any(pattern in block for pattern in patterns):
                return True
            tail = block[-overlap:]
    return False


def check(root, *, jira=False, github=False):
    if jira and github:
        raise ValueError("Choose one fixed tool mode")
    from cryptography.fernet import Fernet, InvalidToken

    canary = GITHUB_CANARY if github else JIRA_CANARY if jira else CANARY
    target_name = "EES GitHub Read" if github else "EES Jira Read" if jira else None
    root = Path(root).resolve(strict=True)
    database = root / "data" / "webui.db"
    # Match open-webui serve: read the existing key without stripping whitespace.
    secret = (root / ".webui_secret_key").read_text(encoding="utf-8")
    if not secret or not database.is_file():
        raise ValueError("Required local files are unavailable")
    key = secret.encode()
    if len(secret) != 44:
        key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
    fernet = Fernet(key)

    encrypted_matches = 0
    plaintext_matches = 0
    target_ids = []
    target_encrypted_matches = 0
    # mode=ro never creates a missing DB. Do not use immutable=1: it ignores WAL.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        if target_name is not None:
            # v0.11.3 models/tools.py: tool.id keys settings.tools.valves.
            # One snapshot binds the exact label to its stored settings.
            connection.execute("BEGIN")
            target_ids = [row[0] for row in connection.execute(
                'SELECT id FROM "tool" WHERE name = ? COLLATE BINARY',
                (target_name,),
            )]
            if any(not isinstance(tool_id, str) or not tool_id for tool_id in target_ids):
                raise ValueError("Unexpected tool schema")
        for (raw_settings,) in connection.execute('SELECT settings FROM "user"'):
            settings = json.loads(raw_settings) if raw_settings else {}
            if settings is None:
                continue
            if not isinstance(settings, dict):
                raise ValueError("Unexpected settings schema")
            tools = settings.get("tools") or {}
            if not isinstance(tools, dict):
                raise ValueError("Unexpected tools schema")
            valves = tools.get("valves") or {}
            if not isinstance(valves, dict):
                raise ValueError("Unexpected valves schema")
            for tool_id, stored in valves.items():
                if isinstance(stored, dict):
                    plaintext_matches += stored.get("PAT") == canary
                elif isinstance(stored, str):
                    try:
                        decoded = json.loads(fernet.decrypt(stored.encode()))
                    except (InvalidToken, ValueError, UnicodeError):
                        continue
                    if isinstance(decoded, dict) and decoded.get("PAT") == canary:
                        encrypted_matches += 1
                        if target_name is not None and len(target_ids) == 1 and tool_id == target_ids[0]:
                            target_encrypted_matches += 1
    finally:
        connection.close()

    physical_plaintext = False
    files_checked = 0
    for suffix in ("", "-wal", "-journal"):
        path = Path(str(database) + suffix)
        if path.is_file():
            files_checked += 1
            physical_plaintext |= contains_canary(path, canary)
    result = {
        "CheckCompleted": True,
        "EncryptedCanaryMatches": encrypted_matches,
        "PlaintextCanaryMatches": plaintext_matches,
        "PlaintextInDatabaseFiles": physical_plaintext,
        "DatabaseFilesChecked": files_checked,
        "DatabaseCheckPassed": encrypted_matches == 1
        and plaintext_matches == 0
        and not physical_plaintext,
        "LogsChecked": False,
        "RestartPersistenceChecked": False,
    }
    if target_name is not None:
        result["TargetToolMatches"] = len(target_ids)
        result["TargetEncryptedCanaryMatches"] = target_encrypted_matches
        result["DatabaseCheckPassed"] &= len(target_ids) == 1 and target_encrypted_matches == 1
    return result


def main(argv=None):
    try:
        args = sys.argv[1:] if argv is None else argv
        if args not in ([], ["--jira"], ["--github"]):
            print(json.dumps({"CheckCompleted": False, "Error": "UNSUPPORTED_ARGUMENTS"}))
            return 2
        if version("open-webui") != "0.11.3":
            print(json.dumps({"CheckCompleted": False, "Error": "UNSUPPORTED_WEBUI_VERSION"}))
            return 2
        local_data = os.environ.get("LOCALAPPDATA")
        if not local_data:
            raise ValueError("LOCALAPPDATA is unavailable")
        root = Path(local_data) / "EES-Agent-POC" / "open-webui"
        result = check(root, github=True) if args == ["--github"] else check(root, jira=bool(args))
    except Exception:
        # Do not disclose exception text, stored values, user IDs, keys or paths.
        print(json.dumps({"CheckCompleted": False, "Error": "LOCAL_CHECK_FAILED"}))
        return 2
    print(json.dumps(result))
    return 0 if result["DatabaseCheckPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
