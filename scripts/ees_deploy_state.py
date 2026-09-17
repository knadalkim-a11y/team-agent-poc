"""Preserve the registered Windows 0.11.3 local SQLite deployment state.

No application import, key/DB creation, server control or automatic restore.
The controller must stop the server and establish a free port before backup.
Returned configuration/metadata are internal state, never safe log payloads.
"""

import ctypes
from ctypes import wintypes
from contextlib import closing
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid


class StateError(RuntimeError):
    """A fixed, non-secret diagnostic suitable for controller error handling."""


EXTRA_ENV = frozenset({
    "DATA_DIR", "WEBUI_SECRET_KEY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PYTHONPATH", "PYTHONHOME", "WEB_CONCURRENCY",
    "UV_CACHE_DIR", "UV_OFFLINE", "UV_NO_PYTHON_DOWNLOADS", "UV_PYTHON_INSTALL_DIR",
    "UV_NATIVE_TLS", "UV_HTTP_TIMEOUT", "UV_DEFAULT_INDEX", "UV_INDEX", "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL", "UV_INDEX_STRATEGY", "UV_INSECURE_HOST",
})
BLOCKED_ENV = frozenset({
    "FRONTEND_BUILD_DIR", "STATIC_DIR", "FONTS_DIR", "CUSTOM_NAME", "PYTHONPATH", "PYTHONHOME",
    "CHROMA_HTTP_HOST", "CHROMA_HTTP_PORT", "REDIS_URL", "WEBSOCKET_REDIS_URL",
    "CHROMA_DATA_PATH", "UPLOAD_DIR", "CACHE_DIR", "TIKTOKEN_CACHE_DIR", "UV_INSECURE_HOST",
})
BLOCKED_PREFIXES = ("DATABASE", "S3_", "GCS_", "AZURE_STORAGE_", "PGVECTOR_", "QDRANT_",
                    "MILVUS_", "WEAVIATE_", "PINECONE_", "MONGODB_", "ORACLE_DB_", "MARIADB_")
MODEL_CACHE_ENV = frozenset({"HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE",
                            "SENTENCE_TRANSFORMERS_HOME", "TORCH_HOME", "XDG_CACHE_HOME"})
BASE_ENV = frozenset({"PATH", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SYSTEMROOT", "WINDIR",
                      "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERNAME", "USERDOMAIN", "HOMEDRIVE", "HOMEPATH",
                      "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "SHELL", "LANG", "LC_ALL"})
INSPECT = r'''
import ast, importlib.util, importlib.metadata, json, pathlib, sys
spec = importlib.util.find_spec("open_webui")
if spec is None or not spec.origin:
    raise RuntimeError("Installed package unavailable")
package = pathlib.Path(spec.origin).parent
names = set()
for source in package.rglob("*.py"):
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    aliases = {"os": "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "os": aliases[item.asname or "os"] = "os"
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for item in node.names: aliases[item.asname or item.name] = "os." + item.name
    def name(node):
        if isinstance(node, ast.Name): return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute): return name(node.value) + "." + node.attr
        return ""
    for node in ast.walk(tree):
        key = None
        if isinstance(node, ast.Call) and name(node.func) in ("os.getenv", "os.environ.get"):
            key = node.args[0] if node.args else next((item.value for item in node.keywords if item.arg == "key"), None)
        if isinstance(node, ast.Subscript) and name(node.value) == "os.environ": key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str): names.add(key.value)
print(json.dumps({"source_prefix": sys.prefix, "package_dir": str(package),
    "python_version": list(sys.version_info[:3]), "platform": sys.platform,
    "open_webui_version": importlib.metadata.version("open-webui"), "env_names": sorted(names)}))
'''


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _dpapi(value, decrypt=False):
    if os.name != "nt":
        raise StateError("Windows CurrentUser DPAPI is required.")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise StateError("Windows CurrentUser environment protection failed; review the original account.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def _protect(value):
    return _dpapi(value)


def _unprotect(value):
    return _dpapi(value, True)


def _safe(value, exists=True):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path).startswith("\\\\"):
        raise StateError("Use existing absolute local paths; network or relative paths need review.")
    if os.name == "nt":
        drive_type = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
        drive_type.argtypes, drive_type.restype = [wintypes.LPCWSTR], wintypes.UINT
        if drive_type(path.anchor) == 4:
            raise StateError("Mapped network drives are outside the local deployment scope.")
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise StateError("Links or Windows reparse points need review; keep the original state.")
    if exists and not path.exists():
        raise StateError("A registered path is missing; no replacement state will be created.")
    return path


def _regular(path, allow_hardlinks=False):
    path = _safe(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or (not allow_hardlinks and info.st_nlink != 1):
        raise StateError("Non-regular or multiply linked state files need review.")
    return path


def _files(root):
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders:
            _safe(Path(directory) / name)
        for name in files:
            yield _regular(Path(directory) / name)


def _inspect(source_python):
    try:
        result = subprocess.run([str(source_python), "-I", "-c", INSPECT], check=True,
                                capture_output=True, text=True, timeout=90)
        info = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise StateError("Existing Python package inspection failed; review the original environment.") from None
    if info.get("platform") != "win32" or info.get("python_version", [])[:2] != [3, 11] or info.get("open_webui_version") != "0.11.3":
        raise StateError("Initial registration supports the existing Windows Python 3.11 / WebUI 0.11.3 only.")
    return info


def _supported(values, data_dir):
    for name in MODEL_CACHE_ENV & values.keys():
        if not _safe(values[name], exists=False).is_relative_to(data_dir):
            raise StateError("A model cache override is outside managed DATA_DIR; review the original environment.")
    if any(name in values for name in {"FRONTEND_BUILD_DIR", "STATIC_DIR", "FONTS_DIR", "CHROMA_DATA_PATH", "UPLOAD_DIR", "CACHE_DIR", "TIKTOKEN_CACHE_DIR"}):
        raise StateError("Custom filesystem locations need original-environment review; keep them unchanged.")
    if any(value and (name in BLOCKED_ENV or name.startswith(BLOCKED_PREFIXES)) for name, value in values.items()):
        raise StateError("Custom paths or external database/storage settings need original-environment review; keep them unchanged.")
    for name, default in {"VECTOR_DB": "chroma", "STORAGE_PROVIDER": "local", "UVICORN_WORKERS": "1", "WEB_CONCURRENCY": "1"}.items():
        if name in values and values[name] != default:
            raise StateError("Only the existing local Chroma/storage and single-worker setup is supported.")
    if "DATA_DIR" in values and Path(values["DATA_DIR"]) != data_dir:
        raise StateError("DATA_DIR differs from the supplied existing data path; review the original settings.")


def _validate_paths(config, initial=False):
    root = _safe(config["state_root"], exists=not initial)
    data, cwd = (_safe(config[name]) for name in ("data_dir", "cwd"))
    profile = _safe(os.environ.get("LOCALAPPDATA", ""))
    if root == profile or not root.is_relative_to(profile):
        raise StateError("Deployment state must use a dedicated directory below this user's LOCALAPPDATA.")
    if not data.is_dir() or not cwd.is_dir() or (root.exists() and not root.is_dir()):
        raise StateError("Registered working, data and state paths must be directories.")
    for other in (data, cwd, _safe(config["source_prefix"]), _safe(config["package_dir"]), Path(__file__).resolve().parents[1]):
        if root.is_relative_to(other) or other.is_relative_to(root):
            raise StateError("Deployment state overlaps source, working directory or data; select a separate profile directory.")
    for key, name in (("releases_dir", "releases"), ("backups_dir", "backups"), ("environment_file", "environment.dpapi")):
        if Path(config[key]) != root / name:
            raise StateError("Registered state layout changed; review the original configuration.")
        _safe(config[key], exists=False)
    for name in ("source_python", "uv_exe"):
        _regular(config[name], allow_hardlinks=True)
    database = _regular(data / "webui.db")
    if database.stat().st_size == 0:
        raise StateError("Existing webui.db is empty; no new database will be created.")
    package = _safe(config["package_dir"])
    if any(path.exists() or path.is_symlink() for path in (cwd / ".env", package / ".env", package.parent.parent / ".env")):
        raise StateError("An existing .env needs original-environment review; do not remove or rewrite it.")
    if config.get("key_file"):
        if _sha(_regular(config["key_file"]).read_bytes()) != config["key_file_sha256"]:
            raise StateError("The registered key file changed; preserve and review the original key.")


def _fingerprint(config):
    return _sha(_json({name: value for name, value in config.items() if name != "environment_sha256"}))


def init_config(config_path, source_python, cwd, data_dir, host, port, uv_exe):
    try:
        config_path = _safe(config_path, exists=False)
        root = _safe(config_path.parent, exists=False)
        if config_path.exists() or (root / "environment.dpapi").exists():
            raise StateError("Deployment registration already exists; it will not be overwritten.")
        ipaddress.ip_address(host)
        if type(port) is not int or not 1 <= port <= 65535:
            raise StateError("Use the existing numeric listen port.")
        source_python, cwd, data_dir, uv_exe = (_safe(path) for path in (source_python, cwd, data_dir, uv_exe))
        info = _inspect(source_python)
        names = set(info.pop("env_names")) | EXTRA_ENV | BLOCKED_ENV | MODEL_CACHE_ENV | {name for name in os.environ if name.startswith("UV_INDEX_")}
        names = sorted(({name.upper() for name in names} if os.name == "nt" else names) - BASE_ENV)
        values = {name: os.environ[name] for name in names if name in os.environ}
        _supported(values, data_dir)
        key_file = cwd / ".webui_secret_key"
        if "WEBUI_SECRET_KEY" in values:
            if not values["WEBUI_SECRET_KEY"].strip():
                raise StateError("The existing environment key is empty; review its original configuration.")
        elif not key_file.exists() or not _regular(key_file).stat().st_size:
            raise StateError("An existing key is required; no key file will be generated.")
        config = dict(info, schema_version=1, config_path=str(config_path), state_root=str(root),
                      source_python=str(source_python), cwd=str(cwd), data_dir=str(data_dir), host=str(host), port=port,
                      uv_exe=str(uv_exe), releases_dir=str(root / "releases"), backups_dir=str(root / "backups"),
                      environment_file=str(root / "environment.dpapi"), env_names=names,
                      key_file=str(key_file) if key_file.exists() else None,
                      key_file_sha256=_sha(_regular(key_file).read_bytes()) if key_file.exists() else None)
        _validate_paths(config, initial=True)
        list(_files(data_dir))
        encrypted = _protect(_json({"config_sha256": _fingerprint(config), "values": values}))
        config["environment_sha256"] = _sha(encrypted)
        root_existed = root.exists()
        root.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            with (root / "environment.dpapi").open("xb") as target:
                created.append(root / "environment.dpapi")
                target.write(encrypted)
            with config_path.open("xb") as target:
                created.append(config_path)
                target.write(_json(config))
        except Exception:
            for path in created:
                path.unlink()
            if not root_existed and root.exists() and not any(root.iterdir()):
                root.rmdir()
            raise
        return config
    except StateError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise StateError("Registration failed without changing the existing deployment; review the original settings.") from None


def load_config(config_path):
    try:
        config = json.loads(_regular(config_path).read_bytes())
        if not isinstance(config, dict) or config.get("schema_version") != 1 or Path(config["config_path"]) != Path(config_path):
            raise StateError("Deployment configuration format or location changed.")
        runtime_environment(config)
        return config
    except StateError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise StateError("Registered deployment state could not be verified.") from None


def runtime_environment(config):
    try:
        _validate_paths(config)
        if json.loads(_regular(config["config_path"]).read_bytes()) != config:
            raise StateError("Registered configuration fingerprint changed; review the original state.")
        encrypted = _regular(config["environment_file"]).read_bytes()
        if _sha(encrypted) != config["environment_sha256"]:
            raise StateError("Registered environment snapshot changed; preserve the original state.")
        snapshot = json.loads(_unprotect(encrypted))
        if snapshot["config_sha256"] != _fingerprint(config):
            raise StateError("Registered configuration fingerprint changed; review the original state.")
        values = snapshot["values"]
        _supported(values, Path(config["data_dir"]))
        if not config["key_file"] and not values.get("WEBUI_SECRET_KEY", "").strip():
            raise StateError("The registered key is unavailable; no replacement key will be created.")
        environment = {name: value for name, value in os.environ.items() if name not in config["env_names"] and not name.startswith("UV_INDEX_")}
        environment.update(values)
        environment["DATA_DIR"] = config["data_dir"]
        return environment
    except StateError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise StateError("Registered environment could not be restored for this Windows account.") from None


def backup_state(config):
    """Copy verified local state after the controller stopped the server."""
    try:
        runtime_environment(config)
        data = Path(config["data_dir"])
        sources = {"data/" + path.relative_to(data).as_posix(): path for path in _files(data)}
        sources.update({"configuration/config.json": _regular(config["config_path"]),
                        "configuration/environment.dpapi": _regular(config["environment_file"])})
        if config["key_file"]:
            sources["key/.webui_secret_key"] = _regular(config["key_file"])
        destination = Path(config["backups_dir"]) / uuid.uuid4().hex
        _safe(destination, exists=False).mkdir(parents=True, exist_ok=False)
        directories = []
        for directory, _, _ in os.walk(data, followlinks=False):
            relative = "data" if Path(directory) == data else "data/" + _safe(directory).relative_to(data).as_posix()
            (destination / relative).mkdir(parents=True, exist_ok=True)
            directories.append(relative)
        entries = []
        for name, source in sorted(sources.items()):
            _regular(source)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            before = _file_sha(source)
            shutil.copy2(source, target)
            if _file_sha(target) != before or _file_sha(source) != before:
                raise StateError("State changed during backup; the incomplete backup must not be used.")
            entries.append({"path": name, "sha256": before, "size": target.stat().st_size})
        # WAL readers can update SHM read marks. Check a disposable DB/WAL/SHM copy,
        # keeping both the original state and verified backup byte-for-byte intact.
        with tempfile.TemporaryDirectory(prefix="sqlite-check-", dir=destination.parent) as temporary:
            check_db = Path(temporary) / "webui.db"
            for suffix in ("", "-wal", "-shm"):
                saved = destination / ("data/webui.db" + suffix)
                if saved.exists():
                    shutil.copy2(saved, Path(str(check_db) + suffix))
            with closing(sqlite3.connect(check_db.as_uri() + "?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise StateError("The copied SQLite database did not pass quick_check.")
        metadata = {"schema_version": 1, "backup_id": destination.name, "directories": sorted(directories),
                    "files": entries, "database_check": "ok"}
        (destination / "manifest.json").write_bytes(_json(metadata))
        return {"backup_id": destination.name, "path": str(destination), "files": len(entries),
                "manifest_sha256": _sha(_json(metadata)), "database_check": "ok"}
    except StateError:
        raise
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        raise StateError("Local state backup failed; keep the original data and review the incomplete backup.") from None
