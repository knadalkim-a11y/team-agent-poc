"""Optional Selector launcher for the existing Windows Open WebUI 0.11.3 POC.

Run with the existing cached WebUI Python, working directory and environment.
--check only inspects prerequisites; it does not import WebUI or start a server.
This avoids the Proactor accept path, not every cause of network disconnection.
Windows Selector does not support asyncio subprocesses/pipes and has a 512-socket
limit. Use only for the current single-worker, SQLite, read-only API setup.
"""

import argparse
import asyncio
import ipaddress
import os
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
import sys


EXPECTED_VERSIONS = {"open-webui": "0.11.3", "uvicorn": "0.51.0"}
DB_OVERRIDES = (
    "DATABASE_URL", "DATABASE_TYPE", "DATABASE_HOST", "DATABASE_PORT",
    "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD",
)


def check_environment():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 11):
        raise RuntimeError("This optional launcher requires Windows and Python 3.11.")
    for package, expected in EXPECTED_VERSIONS.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            raise RuntimeError(f"Run with the existing cached {package} environment.") from None
        if installed != expected:
            raise RuntimeError(f"This launcher was reviewed only for {package} {expected}.")
    if os.environ.get("UVICORN_WORKERS", "1") != "1":
        raise RuntimeError("Only the existing single-worker setup is supported.")
    if any(name in os.environ for name in DB_OVERRIDES):
        raise RuntimeError("Custom database settings need separate review; keep the current settings.")
    spec = find_spec("open_webui")
    if spec is None or not spec.origin:
        raise RuntimeError("The installed WebUI entry point could not be located.")
    # env.py loads BASE_DIR/.env after serve() has loaded the key. Do not import
    # env.py early or change that order. This small launcher supports the current
    # process-environment setup only, not hidden worker/DB overrides in that file.
    if (Path(spec.origin).resolve().parents[2] / ".env").exists():
        raise RuntimeError("A package .env needs separate review; keep the current settings.")

    raw_data_dir = os.environ.get("DATA_DIR", "")
    data_dir = Path(raw_data_dir)
    if not raw_data_dir or not data_dir.is_absolute():
        raise RuntimeError("Restore the existing absolute DATA_DIR before using this launcher.")
    database = data_dir / "webui.db"
    if not database.is_file() or database.stat().st_size == 0:
        raise RuntimeError("Existing webui.db was not found; no new database will be created here.")

    environment_key = os.environ.get("WEBUI_SECRET_KEY")
    if environment_key is not None:
        if not environment_key.strip():
            raise RuntimeError("WEBUI_SECRET_KEY is empty; restore the existing key configuration.")
    else:
        key_file = Path.cwd() / ".webui_secret_key"
        if not key_file.is_file() or key_file.stat().st_size == 0:
            raise RuntimeError("Use the original working directory containing the existing key file.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check prerequisites without starting WebUI")
    parser.add_argument("--host", help="The existing listen IP; no automatic change to LAN binding")
    parser.add_argument("--port", type=int, help="The existing listen port")
    args = parser.parse_args(argv)
    if not args.check and (args.host is None or args.port is None):
        parser.error("Starting the server requires the existing --host and --port.")
    if args.host is not None:
        try:
            ipaddress.ip_address(args.host)
        except ValueError:
            parser.error("--host must be the existing IPv4 or IPv6 listen address.")
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")

    try:
        check_environment()
    except (RuntimeError, OSError) as exc:
        # Filesystem exceptions can contain private paths. Do not echo them.
        message = str(exc) if isinstance(exc, RuntimeError) else "Could not inspect existing state files."
        print(f"PreflightFailed: {message}", file=sys.stderr)
        return 1
    print("PreflightPassed=true (prerequisites only; server health not checked)")
    if args.check:
        return 0

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from open_webui import serve

    print("EventLoop=WindowsSelectorEventLoop; starting the original WebUI serve entry point")
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
