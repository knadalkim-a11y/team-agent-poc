"""Personal loopback development using the existing EES builders and process controller."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

try:
    from . import build_ees_frontend as frontend
    from . import build_ees_webui as branding
    from . import ees_deploy_process as processes
except ImportError:
    import build_ees_frontend as frontend
    import build_ees_webui as branding
    import ees_deploy_process as processes


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "local-dev"
RECEIPT = STATE / "installed.json"
PROCESS = STATE / "process.json"
DATA = Path(os.environ.get("LOCALAPPDATA", str(ROOT / "runtime"))) / "EES-Workflow-Dev"


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(arguments, cwd=ROOT, env=None):
    subprocess.run([str(value) for value in arguments], cwd=cwd, env=env, check=True)


def source_state():
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=ROOT).decode("utf-8").strip()
    return {"commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
            "diff_sha256": hashlib.sha256(subprocess.check_output(
                ["git", "diff", "HEAD", "--binary"], cwd=ROOT)).hexdigest()}


def stopped():
    identity = read(PROCESS)
    if identity and processes.verify_identity(identity):
        raise ValueError("Stop the local development server before installing or building.")
    if not processes.port_is_free("127.0.0.1", 8080):
        raise ValueError("Port 8080 is occupied; no existing process was stopped.")


def install(directory, provenance):
    stopped()
    manifest = read(directory / "manifest.json")
    wheel = directory / branding.WHEEL_FILENAME
    if not manifest or manifest.get("version") != branding.VERSION:
        raise ValueError("Expected an EES branding manifest.")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if manifest["wheel"] != {"filename": wheel.name, "sha256": digest, "size": wheel.stat().st_size}:
        raise ValueError("Wheel hash or size does not match its manifest.")
    run([sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", wheel])
    run([sys.executable, "-m", "pip", "check"])
    save(RECEIPT, {"source": provenance, "version": branding.VERSION,
                   "wheel": str(wheel.resolve()), "sha256": digest,
                   "installed_at": datetime.now(timezone.utc).isoformat()})


def build():
    stopped()
    before = source_state()
    config = frontend.configuration()
    node = ROOT / "dist" / "tools" / ("node-" + config["node"] + "-win-x64")
    env = dict(os.environ, PATH=str(node) + os.pathsep + os.environ["PATH"],
               CYPRESS_INSTALL_BINARY="0", ONNXRUNTIME_NODE_INSTALL_CUDA="skip",
               NODE_OPTIONS="--max-old-space-size=6144")
    build_root = Path(os.environ.get("EES_DEV_BUILD_ROOT", ROOT / "dist" / "local-builds")).expanduser().resolve()
    destination = build_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination.mkdir(parents=True)
    source = destination / "source"
    seed = ROOT / "dist" / "open-webui-source"
    run(["git", "clone", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "--no-hardlinks", seed, source])
    run(["git", "checkout", "--detach", config["commit"]], cwd=source)
    npm = shutil.which("npm", path=env["PATH"])
    if not npm:
        raise ValueError("Prepare the pinned local Node/npm before building.")
    run([npm, "ci", "--force", "--no-audit", "--no-fund"], cwd=source, env=env)
    wheel = ROOT / "dist" / "upstream" / config["wheel_filename"]
    output = destination / "frontend"
    run([sys.executable, ROOT / "scripts" / "build_ees_frontend.py", "--source-dir", source,
         "--wheel", wheel, "--output-dir", output], env=env)
    packaged = destination / "branding"
    run([sys.executable, ROOT / "scripts" / "build_ees_webui.py", "--wheel", wheel,
         "--frontend-dir", output, "--output-dir", packaged])
    if source_state() != before:
        raise ValueError("Sources changed during the build; preserved outputs were not installed.")
    install(packaged, before)


def start(health_timeout=600):
    stopped()
    receipt = read(RECEIPT)
    if not receipt or importlib.metadata.version("open-webui") != receipt["version"]:
        raise ValueError("Install a verified EES wheel before starting.")
    DATA.mkdir(parents=True, exist_ok=True)
    data = DATA / "data"
    data.mkdir(exist_ok=True)
    key_file = DATA / ".webui_secret_key"
    if (data / "webui.db").exists() and (not key_file.is_file() or not key_file.read_bytes().strip()):
        raise ValueError("Existing database has no usable key; restore its original key before starting.")
    inherited = {name: value for name, value in os.environ.items() if name.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "USERPROFILE", "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "USERNAME",
        "USERDOMAIN", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA"}}
    env = dict(inherited, DATA_DIR=str(data), WEBUI_NAME="EES Workflow",
               ENABLE_OLLAMA_API="false", ENABLE_OPENAI_API="false",
               ENABLE_VERSION_UPDATE_CHECK="false", HF_HUB_DISABLE_TELEMETRY="1",
               ANONYMIZED_TELEMETRY="false", ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS="false",
               CORS_ALLOW_ORIGIN="http://localhost:8080;http://127.0.0.1:8080",
               NO_PROXY="localhost,127.0.0.1,::1", PYTHONUTF8="1")
    identity = processes.start_server(sys.executable, DATA, env, "127.0.0.1", 8080, STATE / "logs")
    save(PROCESS, identity)
    print("Server launched. Log: " + identity["log_file"], flush=True)
    processes.wait_healthy(identity, timeout=health_timeout)
    print("Ready: http://127.0.0.1:8080")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "build", "install-main"))
    parser.add_argument("--health-timeout", type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.health_timeout <= 900:
        parser.error("Health timeout must be between 1 and 900 seconds.")
    expected = ROOT / ".venv" / "Scripts" / "python.exe"
    if Path(sys.executable).absolute() != expected:
        parser.error("Run with this repository's .venv\\Scripts\\python.exe.")
    if args.action == "start":
        start(args.health_timeout)
    elif args.action == "stop":
        identity = read(PROCESS)
        if identity:
            processes.stop_server(identity)
        print("Local development server stopped.")
    elif args.action == "status":
        identity = read(PROCESS)
        print(json.dumps({"installed": read(RECEIPT), "checkout": source_state(),
                          "running": bool(identity and processes.verify_identity(identity)),
                          "healthy": bool(identity and processes.verify_identity(identity)
                                          and processes._healthy("127.0.0.1", 8080, 2)),
                          "data": str(DATA), "log": identity.get("log_file") if identity else None}, indent=2))
    elif args.action == "build":
        build()
    else:
        install(ROOT / "dist" / "main-branding", {
            "commit": "0f4c905ea6cb277b0704af32c40dd198fab3f959", "dirty": False,
            "artifact_id": 12028799532, "workflow_run": 38858836722})


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, processes.ProcessError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
