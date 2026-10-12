"""Build the pinned Open WebUI source; never rewrite compiled frontend bytes.

CI installs the exact lockfile once, then builds pristine Native before EES.
The source checkout must be clean at entry. A failed patched build is not
silently reset or reused: preserve its diagnostics and provide a fresh checkout.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = ROOT / "frontend" / "open-webui-source.json"
SOURCE_PREFIX = "open_webui/frontend/"


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate frontend manifest key.")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def _plain(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Linked frontend path is not supported.")
    return path


def _relative(name):
    if not isinstance(name, str):
        raise ValueError("Unsafe frontend entry name.")
    path = PurePosixPath(name)
    if (not name or "\\" in name or
            path.is_absolute() or ":" in name or any(p in {"", ".", ".."} for p in name.split("/"))):
        raise ValueError("Unsafe frontend entry name.")
    return path


def _run(args, source, *, capture=True, env=None):
    result = subprocess.run(args, cwd=source, check=True, env=env,
                            stdout=subprocess.PIPE if capture else None,
                            text=True, encoding="utf-8")
    return result.stdout.strip() if capture else None


def configuration():
    config = _json(SOURCE_CONFIG)
    if config.get("schema") != 1:
        raise ValueError("Unsupported frontend source configuration.")
    for entry in config["patches"]:
        path = _plain(SOURCE_CONFIG.parent / _relative(entry["path"]))
        if _sha(path.read_bytes()) != entry["sha256"]:
            raise ValueError("Frontend source patch hash differs.")
    return config


def _inventory(directory):
    directory = _plain(directory)
    if not directory.is_dir():
        raise ValueError("Frontend build directory is missing.")
    files = {}
    for path in sorted(directory.rglob("*")):
        _plain(path)
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            _relative(name)
            files[name] = path.read_bytes()
        elif not path.is_dir():
            raise ValueError("Unsupported frontend build entry.")
    return files


def _digest_map(files):
    return {name: _sha(content) for name, content in sorted(files.items())}


def _source_inputs(mode="ees"):
    """Bind a frontend to its reviewed source patches and injected EES assets."""
    config = configuration()
    if mode == "baseline":
        pin = {key: config[key] for key in ("commit", "lock_sha256", "license_sha256", "node", "npm")}
        return {"upstream_pin": _sha(json.dumps(pin, sort_keys=True).encode("utf-8"))}
    files = {"frontend/open-webui-source.json": SOURCE_CONFIG.read_bytes()}
    for entry in config["patches"]:
        path = SOURCE_CONFIG.parent / entry["path"]
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for directory in (ROOT / "branding" / "ees" / "ui", ROOT / "branding" / "ees" / "assets"):
        for name, content in _inventory(directory).items():
            files[(directory.relative_to(ROOT) / name).as_posix()] = content
    # This source owns the assembled launcher order and cache-addressed icons.
    files["scripts/build_ees_webui.py"] = (ROOT / "scripts" / "build_ees_webui.py").read_bytes()
    files["scripts/build_ees_frontend.py"] = Path(__file__).read_bytes()
    return _digest_map(files)


def _verify_source(source, config):
    if _run(["git", "rev-parse", "HEAD"], source) != config["commit"]:
        raise ValueError("Expected the exact pinned Open WebUI source commit.")
    if _run(["git", "status", "--porcelain", "--untracked-files=all"], source):
        raise ValueError("Open WebUI checkout is not clean; preserve it and use a fresh checkout.")
    for name, expected in {**config["source_files"], **config["license_files"],
                           "package-lock.json": config["lock_sha256"]}.items():
        if _sha(_plain(source / _relative(name)).read_bytes()) != expected:
            raise ValueError("Pinned Open WebUI source file differs: " + name)
    if _run(["node", "--version"], source) != config["node"]:
        raise ValueError("Node version differs from the pinned frontend builder.")
    if _run(["npm", "--version"], source) != config["npm"]:
        raise ValueError("npm version differs from the pinned frontend builder.")
    if not (source / "node_modules" / "vite" / "bin" / "vite.js").is_file():
        raise ValueError("Run npm ci with the pinned Node and lockfile before building.")
    if (source / "build").exists() or (source / "build").is_symlink():
        raise ValueError("Source build output already exists; preserve it before another build.")


def _copy_official_pyodide(source, wheel, config):
    # Upstream's preparation script fetches moving PyPI package versions and
    # catches download errors. Reuse the complete, hash-pinned released payload.
    if wheel.name != config["wheel_filename"] or _sha(wheel.read_bytes()) != config["wheel_sha256"]:
        raise ValueError("Expected the unchanged pinned official Open WebUI wheel.")
    prefix = SOURCE_PREFIX + "pyodide/"
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate official wheel entry.")
        entries = {name[len(prefix):]: archive.read(name) for name in names
                   if name.startswith(prefix) and not name.endswith("/")}
    if not entries or "pyodide-lock.json" not in entries or "pyodide.js" not in entries:
        raise ValueError("Pinned official wheel lacks the Pyodide payload.")
    if _digest_map(entries) != config["pyodide_files"]:
        raise ValueError("Pinned Pyodide payload inventory differs.")
    target = _plain(source / "static" / "pyodide")
    # Read tracked bytes without text/newline normalization.
    original_lock = subprocess.check_output(
        ["git", "show", "HEAD:static/pyodide/pyodide-lock.json"], cwd=source)
    if target.exists():
        existing = _inventory(target)
        for name, content in existing.items():
            if content != entries.get(name) and not (name == "pyodide-lock.json" and content == original_lock):
                raise ValueError("Existing Pyodide payload differs; preserve it before building.")
    for name, content in entries.items():
        path = _plain(target / _relative(name))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return _digest_map(entries), original_lock


def _apply_ees(source, config, wheel):
    for entry in config["patches"]:
        path = SOURCE_CONFIG.parent / entry["path"]
        _run(["git", "apply", "--check", str(path)], source)
        _run(["git", "apply", "--whitespace=nowarn", str(path)], source)
    for name, expected in config["patched_files"].items():
        if _sha((source / name).read_bytes()) != expected:
            raise ValueError("Patched frontend source differs: " + name)
    # Import at call time: wheel packing imports only validate_frontend.
    try:
        import build_ees_webui as builder
    except ImportError:
        from scripts import build_ees_webui as builder
    ui = ROOT / "branding" / "ees" / "ui"
    with ZipFile(wheel) as archive:
        additions = builder.prepare_additions(archive, ui)
    tokens = {
        "EES_THEME_SHA256": _sha(additions[builder.TARGET_APP + "chat-theme.css"]),
        "EES_WORK_STYLE_SHA256": _sha(additions[builder.TARGET_APP + "ees-work-launcher.css"]),
        "EES_WORK_SCRIPT_SHA256": _sha(additions[builder.TARGET_APP + "ees-work-launcher.js"]),
    }
    template = source / "src" / "app.html"
    content = template.read_text(encoding="utf-8")
    for token, value in tokens.items():
        if content.count(token) != 1:
            raise ValueError("Frontend source cache token differs: " + token)
        content = content.replace(token, value)
    template.write_text(content, encoding="utf-8")
    for name in builder.ASSET_NAMES:
        path = _plain(source / "static" / "static" / name)
        path.write_bytes((ROOT / "branding" / "ees" / "assets" / name).read_bytes())
    (source / "static" / "favicon.png").write_bytes(
        (ROOT / "branding" / "ees" / "assets" / "favicon.png").read_bytes())


def _verify_output(files, config, mode):
    app_dir = config["app_dir"] if mode == "ees" else "_app"
    if not {"index.html", app_dir + "/version.json"}.issubset(files):
        raise ValueError("Frontend output lacks its entry page or version.")
    if mode == "ees" and json.loads(files[app_dir + "/version.json"].decode("utf-8")) != {"version": config["version"]}:
        raise ValueError("Frontend program version differs from the Apply/Restore contract.")
    if not any(name.startswith(app_dir + "/immutable/entry/") and name.endswith(".js") for name in files):
        raise ValueError("Frontend output lacks native Svelte entry modules.")
    if mode == "ees":
        if any(name.startswith("_app/") for name in files):
            raise ValueError("EES output retained the old Native cache namespace.")
        scripts = b"\n".join(content for name, content in files.items()
                             if name.startswith(app_dir + "/") and name.endswith(".js"))
        for marker in (b"__eesNativeDraftV1", b"__eesNativeWorkV1", b"ees_work_reference",
                       b"beginChatCreation", b"finishChatCreation", b"data-ees-native-sidebar"):
            if marker not in scripts:
                raise ValueError("Frontend output lost a Native integration hook.")
        if b"EES_THEME_SHA256" in files["index.html"]:
            raise ValueError("Frontend source cache tokens were not resolved.")


def build(source_dir, wheel, output_dir, *, baseline=False):
    source, wheel, output = map(_plain, (source_dir, wheel, output_dir))
    config = configuration()
    if output.exists():
        raise ValueError("Frontend destination already exists; choose a new output directory.")
    _verify_source(source, config)
    mode = "baseline" if baseline else "ees"
    inputs = _source_inputs(mode)
    pyodide, original_pyodide_lock = _copy_official_pyodide(source, wheel, config)
    if not baseline:
        _apply_ees(source, config, wheel)
    source_files = {name: _sha((source / name).read_bytes()) for name in config["source_files"]}
    env = os.environ.copy()
    # npm run build normally supplies this variable. We call Vite directly to
    # avoid the upstream moving Pyodide downloader, so preserve that input.
    package_version = _json(source / "package.json").get("version")
    if package_version != "0.11.3":
        raise ValueError("Pinned frontend package version differs.")
    env["npm_package_version"] = package_version
    if not baseline:
        env.update(EES_PROGRAM_VERSION=config["version"],
                   APP_BUILD_HASH=config["commit"])
    try:
        _run(["node", "node_modules/vite/bin/vite.js", "build"], source, capture=False, env=env)
    finally:
        # Only restore the known tracked lockfile overwritten by this call.
        # Preserve build failures and all source patches for inspection.
        (source / "static" / "pyodide" / "pyodide-lock.json").write_bytes(original_pyodide_lock)
    files = _inventory(source / "build")
    _verify_output(files, config, mode)
    # Ensure patch/source/asset edits during a long build cannot be published as
    # if they came from the original reviewed inputs.
    if inputs != _source_inputs(mode) or source_files != {
            name: _sha((source / name).read_bytes()) for name in config["source_files"]}:
        raise ValueError("Frontend inputs changed while building.")
    manifest = {"schema": 1, "mode": mode, "upstream_commit": config["commit"],
                "lock_sha256": config["lock_sha256"], "license_sha256": config["license_sha256"],
                "version": config["version"] if not baseline else "0.11.3",
                "app_dir": config["app_dir"] if not baseline else "_app",
                "node": config["node"], "npm": config["npm"], "source_inputs": inputs,
                "compiler_environment": {"npm_package_version": package_version},
                "source_files": config["source_files"] if baseline else config["patched_files"],
                "compiled_source_files": source_files,
                "pyodide_files": pyodide, "files": _digest_map(files)}
    output.mkdir(parents=True)
    shutil.move(str(source / "build"), str(output / "build"))
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    validate_frontend(output, mode=mode)
    return manifest


def validate_frontend(frontend_dir, mode="ees"):
    """Return exact validated build bytes, keyed by frontend-relative path."""
    if mode not in {"ees", "baseline"}:
        raise ValueError("Unknown frontend build mode.")
    directory = _plain(frontend_dir)
    manifest = _json(_plain(directory / "manifest.json"))
    config = configuration()
    expected = {"schema": 1, "mode": mode, "upstream_commit": config["commit"],
                "lock_sha256": config["lock_sha256"], "license_sha256": config["license_sha256"],
                "node": config["node"], "npm": config["npm"],
                "version": config["version"] if mode == "ees" else "0.11.3",
                "app_dir": config["app_dir"] if mode == "ees" else "_app",
                "source_files": config["patched_files"] if mode == "ees" else config["source_files"]}
    expected["compiler_environment"] = {"npm_package_version": "0.11.3"}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Frontend manifest provenance differs.")
    if manifest.get("source_inputs") != _source_inputs(mode):
        raise ValueError("Frontend inputs differ from this wrapper checkout; rebuild in CI.")
    compiled = manifest.get("compiled_source_files")
    sources = expected["source_files"]
    if (not isinstance(compiled, dict) or set(compiled) != set(sources) or
            any(not isinstance(value, str) or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value) for value in compiled.values()) or
            any(compiled[name] != digest for name, digest in sources.items()
                if mode == "baseline" or name != "src/app.html")):
        raise ValueError("Compiled frontend source fingerprints differ.")
    files = _inventory(directory / "build")
    if manifest.get("files") != _digest_map(files):
        raise ValueError("Frontend output inventory or hash differs.")
    pyodide = {name.removeprefix("pyodide/"): _sha(content) for name, content in files.items()
               if name.startswith("pyodide/")}
    if manifest.get("pyodide_files") != config["pyodide_files"] or pyodide != config["pyodide_files"]:
        raise ValueError("Frontend Pyodide payload differs from the pinned official release.")
    _verify_output(files, config, mode)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    manifest = build(args.source_dir, args.wheel, args.output_dir, baseline=args.baseline)
    print("EES frontend mode={mode} commit={upstream_commit} files={count}".format(
        **manifest, count=len(manifest["files"])))


if __name__ == "__main__":
    main()
