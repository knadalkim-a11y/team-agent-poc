"""Prepare and verify immutable delivery inputs; never trust an unchecked cache hit.

Historical source trees remain complete Git archives, including hidden files.
Only these fixed inputs are cached; the current candidate wheel is always built.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_ees_webui import SOURCE_FILENAME, SOURCE_SHA256, UPSTREAM_VERSION

# The single source of historical pins formerly repeated in the workflow.
SOURCE_PINS = {
    "legacy": "a443d30c6694df0e1cbe082a0b99aa5f2d566917",
    "previous": "991cdb1d80ae07471fb50594831d74fe602b1ef7",
    "previous12": "8027aaf2e654778f052a966e5a49feed0fc54f69",
    "previous-v4": "3a51f9d2bc604e768a59a522d6f34a34c2cb05d3",
    "previous13": "1c6ddaa04f05b2eea02bbf15155b8602f1e4a1a8",
}


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", *arguments], cwd=ROOT)


def key_inputs(fixture):
    pin = SOURCE_PINS[fixture] if fixture != "upstream" else None
    return {
        "schema": 1, "fixture": fixture, "source_commit": pin,
        "source_builder": git("rev-parse", pin + ":scripts/build_ees_webui.py").decode("ascii").strip() if pin else None,
        "official_wheel": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256},
        "helper_sha256": digest(Path(__file__)),
        "environment": {
            "os": platform.system(), "machine": platform.machine(),
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "libc": list(platform.libc_ver()), "zlib": zlib.ZLIB_VERSION,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "runner_image": {name: os.environ.get(name, "") for name in ("ImageOS", "ImageVersion", "RUNNER_OS", "RUNNER_ARCH")},
        },
    }


def cache_key(fixture):
    encoded = json.dumps(key_inputs(fixture), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "ees-pinned-" + fixture + "-" + hashlib.sha256(encoded).hexdigest()


def paths(fixture, dist):
    names = ["upstream"] if fixture == "upstream" else [fixture + "-source", fixture + "-branding"]
    return [Path(dist) / name for name in names]


def inventory(fixture, dist):
    result = {}
    for directory in paths(fixture, dist):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Missing or unsafe fixture directory: " + str(directory))
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError("Unsafe fixture member: " + str(path))
            if path.is_file():
                result[path.relative_to(dist).as_posix()] = {"sha256": digest(path), "size": path.stat().st_size}
    if not result:
        raise ValueError("Empty fixture inventory")
    return result


def verify_official(wheel):
    wheel = Path(wheel)
    if wheel.is_symlink() or not wheel.is_file() or wheel.name != SOURCE_FILENAME or digest(wheel) != SOURCE_SHA256:
        raise ValueError("Expected the unchanged, pinned official Open WebUI wheel")


def verify_source(fixture, source):
    """Anchor cached source bytes to Git, independently of the cache manifest."""
    entries = git("ls-tree", "-rz", SOURCE_PINS[fixture]).split(b"\0")
    expected = {}
    for entry in filter(None, entries):
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("Unsupported pinned source entry")
        expected[name.decode("utf-8")] = blob
    actual = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if not p.is_dir() or p.is_symlink()}
    if set(actual) != set(expected):
        raise ValueError("Pinned source inventory differs from Git")
    for name, path in actual.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError("Unsafe pinned source member: " + name)
        data = path.read_bytes()
        value = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if value != expected[name]:
            raise ValueError("Pinned source differs from Git: " + name)


def verify_branding(fixture, dist, *, transferred=False):
    source, branding = paths(fixture, dist)
    if not transferred:
        verify_source(fixture, source)
    # Read the literal version from the verified old builder without importing it.
    tree = ast.parse((source / "scripts/build_ees_webui.py").read_text(encoding="utf-8"))
    version = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets))
    wheel_name = "open_webui-" + version + "-py3-none-any.whl"
    if {path.name for path in branding.iterdir()} != {wheel_name, "manifest.json"}:
        raise ValueError("Historical branding inventory differs")
    manifest = json.loads((branding / "manifest.json").read_text(encoding="utf-8"))
    wheel = branding / wheel_name
    if (manifest.get("schema_version") != 1 or manifest.get("version") != version
            or manifest.get("upstream_version") != UPSTREAM_VERSION
            or manifest.get("source") != {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256}
            or manifest.get("wheel") != {"filename": wheel_name, "sha256": digest(wheel), "size": wheel.stat().st_size}):
        raise ValueError("Historical wheel differs from its pinned builder manifest")


def verify(fixture, dist, *, transferred=False):
    dist = Path(dist)
    provenance = dist / (fixture + "-provenance.json")
    if provenance.is_symlink() or not provenance.is_file():
        raise ValueError("Missing or unsafe fixture provenance")
    saved = json.loads(provenance.read_text(encoding="utf-8"))
    if transferred:
        # A same-run artifact was already checked against Git on its producer.
        # Consumers may be Windows and must not relabel Linux build provenance.
        inputs = saved.get("inputs", {})
        expected = {"schema": 1, "fixture": fixture, "source_commit": SOURCE_PINS.get(fixture),
                    "official_wheel": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256},
                    "helper_sha256": digest(Path(__file__))}
        if (any(inputs.get(name) != value for name, value in expected.items())
                or not isinstance(inputs.get("environment"), dict)
                or not inputs["environment"].get("python") or not inputs["environment"].get("os")
                or (fixture != "upstream" and not inputs.get("source_builder"))):
            raise ValueError("Transferred fixture provenance differs")
    elif saved.get("inputs") != key_inputs(fixture):
        raise ValueError("Fixture cache key inputs differ")
    if saved.get("files") != inventory(fixture, dist):
        raise ValueError("Fixture cache file hashes or inventory differ")
    if fixture == "upstream":
        if set(saved["files"]) != {"upstream/" + SOURCE_FILENAME}:
            raise ValueError("Unexpected official wheel inventory")
        verify_official(dist / "upstream" / SOURCE_FILENAME)
    else:
        verify_branding(fixture, dist, transferred=transferred)
    return saved


def prepare(fixture, dist, wheel=None):
    dist = Path(dist).resolve()
    provenance = dist / (fixture + "-provenance.json")
    targets = paths(fixture, dist)
    if provenance.exists() or provenance.is_symlink() or any(p.exists() or p.is_symlink() for p in targets):
        # A partial/tampered hit is an error, not an invisible cache miss.
        verify(fixture, dist)
        return "verified-cache"
    dist.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ees-fixture-", dir=dist) as temporary:
        stage = Path(temporary)
        if fixture == "upstream":
            (stage / "upstream").mkdir()
            subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
                            "--dest", str(stage / "upstream"), "open-webui==" + UPSTREAM_VERSION], check=True)
            verify_official(stage / "upstream" / SOURCE_FILENAME)
        else:
            wheel = Path(wheel).resolve() if wheel else dist / "upstream" / SOURCE_FILENAME
            verify_official(wheel)
            source, branding = paths(fixture, stage)
            archive = stage / "source.tar"
            git("archive", "--format=tar", "--output=" + str(archive), SOURCE_PINS[fixture])
            with tarfile.open(archive) as stream:
                stream.extractall(source, filter="data")
            verify_source(fixture, source)
            subprocess.run([sys.executable, str(source / "scripts/build_ees_webui.py"), "--wheel", str(wheel),
                            "--output-dir", str(branding)], check=True, cwd=ROOT,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            verify_branding(fixture, stage)
        saved = {"inputs": key_inputs(fixture), "files": inventory(fixture, stage)}
        (stage / provenance.name).write_text(json.dumps(saved, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        verify(fixture, stage)
        for original, target in zip(paths(fixture, stage), targets):
            original.rename(target)
        (stage / provenance.name).rename(provenance)
    return "prepared"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=["upstream", *SOURCE_PINS], required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--key", action="store_true")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--verify-transfer", action="store_true", help="Verify a same-run artifact already checked by the cache producer")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.key:
            key = cache_key(args.fixture)
            print(key)
            if os.environ.get("GITHUB_OUTPUT"):
                with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
                    output.write("cache_key=" + key + "\n")
        elif args.prepare:
            print(args.fixture + ": " + prepare(args.fixture, args.dist, args.wheel))
        else:
            verify(args.fixture, args.dist, transferred=args.verify_transfer)
            print(args.fixture + ": verified")
    except (OSError, ValueError, StopIteration, subprocess.CalledProcessError, tarfile.TarError) as error:
        parser.exit(1, "Pinned fixture rejected: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    main()
