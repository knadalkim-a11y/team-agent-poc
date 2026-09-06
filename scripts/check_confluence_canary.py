"""Read-only UserValves canary check for Open WebUI 0.11.3.

Run with the existing WebUI Python environment (cryptography is required).
Does not import open_webui, migrate a DB, call an API, or print stored values.
This is a DB check only; logs and restart persistence remain separate gates.
"""

import base64
import hashlib
import json
import os
import sqlite3
from importlib.metadata import version
from pathlib import Path


CANARY = "EES-CANARY-20260906-7F3A9C"  # Synthetic test value, never a real PAT.


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


def check(root):
    from cryptography.fernet import Fernet, InvalidToken

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
    # mode=ro never creates a missing DB. Do not use immutable=1: it ignores WAL.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
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
            for stored in valves.values():
                if isinstance(stored, dict):
                    plaintext_matches += stored.get("PAT") == CANARY
                elif isinstance(stored, str):
                    try:
                        decoded = json.loads(fernet.decrypt(stored.encode()))
                    except (InvalidToken, ValueError, UnicodeError):
                        continue
                    if isinstance(decoded, dict) and decoded.get("PAT") == CANARY:
                        encrypted_matches += 1
    finally:
        connection.close()

    physical_plaintext = False
    files_checked = 0
    for suffix in ("", "-wal", "-journal"):
        path = Path(str(database) + suffix)
        if path.is_file():
            files_checked += 1
            physical_plaintext |= contains_canary(path, CANARY)
    return {
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


def main():
    try:
        if version("open-webui") != "0.11.3":
            print(json.dumps({"CheckCompleted": False, "Error": "UNSUPPORTED_WEBUI_VERSION"}))
            return 2
        local_data = os.environ.get("LOCALAPPDATA")
        if not local_data:
            raise ValueError("LOCALAPPDATA is unavailable")
        result = check(Path(local_data) / "EES-Agent-POC" / "open-webui")
    except Exception:
        # Do not disclose exception text, stored values, user IDs, keys or paths.
        print(json.dumps({"CheckCompleted": False, "Error": "LOCAL_CHECK_FAILED"}))
        return 2
    print(json.dumps(result))
    return 0 if result["DatabaseCheckPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
