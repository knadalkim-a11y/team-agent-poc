"""Retry first preparation using the existing cached antlr 4.9.3 wheel.

This narrowly scoped offline recovery preserves failed candidates and their logs.
It never installs into the source runtime, starts a server, or updates its record.
"""

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manage_ees as manager

releases, states = manager.releases, manager.states
PACKAGE = "antlr4-python3-runtime"
VERSION = "4.9.3"
INFO = "antlr4_python3_runtime-4.9.3.dist-info/"
MAX_WHEEL_BYTES = 16 * 1024 * 1024


def _cached_wheel(config, env):
    try:
        result = subprocess.run(
            [config["uv_exe"], "--no-config", "--offline", "cache", "dir"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=releases._environment(env), timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise releases.ReleaseError("The registered uv cache could not be inspected offline.") from None
    cache = states._safe(Path(result.stdout.strip()))
    if not cache.is_dir():
        raise releases.ReleaseError("The registered uv cache is not a directory.")
    found = [path for bucket in cache.glob("sdists-*")
             for path in bucket.rglob("antlr4_python3_runtime-4.9.3-*.whl")
             if path.is_file() and zipfile.is_zipfile(path)]
    if len(found) != 1:
        raise releases.ReleaseError("Expected exactly one cached antlr 4.9.3 wheel; inspect the local cache.")
    source = states._regular(found[0], allow_hardlinks=True)
    if (source.name not in {"antlr4_python3_runtime-4.9.3-py3-none-any.whl",
                            "antlr4_python3_runtime-4.9.3-py2.py3-none-any.whl"}
            or source.stat().st_size > MAX_WHEEL_BYTES):
        raise releases.ReleaseError("The cached antlr wheel is outside the supported scope.")
    with source.open("rb") as handle:
        content = handle.read(MAX_WHEEL_BYTES + 1)
    if len(content) > MAX_WHEEL_BYTES:
        raise releases.ReleaseError("The cached antlr wheel exceeds the supported size.")
    _validate_wheel(content)
    return source.name, content


def _validate_wheel(content):
    with zipfile.ZipFile(io.BytesIO(content)) as wheel:
        entries = releases._entries(wheel, maximum_file=MAX_WHEEL_BYTES)
        required = {INFO + "METADATA", INFO + "WHEEL", INFO + "RECORD"}
        if not required.issubset(entries):
            raise releases.ReleaseError("The cached antlr wheel metadata is incomplete.")
        metadata = BytesParser().parsebytes(wheel.read(INFO + "METADATA"))
        name = re.sub(r"[-_.]+", "-", metadata.get("Name", "")).lower()
        if (len(metadata.get_all("Name", [])) != 1 or name != PACKAGE
                or metadata.get_all("Version", []) != [VERSION]):
            raise releases.ReleaseError("The cached wheel is not antlr4-python3-runtime 4.9.3.")
        details = BytesParser().parsebytes(wheel.read(INFO + "WHEEL"))
        tags = set(details.get_all("Tag", []))
        if (details.get("Wheel-Version") != "1.0" or details.get("Root-Is-Purelib") != "true"
                or "py3-none-any" not in tags or not tags <= {"py2-none-any", "py3-none-any"}):
            raise releases.ReleaseError("The cached antlr wheel is not a supported pure Python wheel.")
        recorded = set()
        for row in csv.reader(io.StringIO(wheel.read(INFO + "RECORD").decode("utf-8"))):
            if len(row) != 3 or row[0] not in entries or row[0] in recorded:
                raise releases.ReleaseError("The cached wheel RECORD is invalid.")
            name, digest, size = row
            recorded.add(name)
            if name == INFO + "RECORD":
                if digest or size:
                    raise releases.ReleaseError("The cached wheel RECORD self entry is invalid.")
                continue
            with wheel.open(name) as handle:
                actual, count = releases._digest(handle)
            encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).rstrip(b"=").decode()
            if digest != "sha256=" + encoded or size != str(count):
                raise releases.ReleaseError("The cached antlr wheel integrity check failed.")
        if recorded != set(entries):
            raise releases.ReleaseError("The cached wheel RECORD is incomplete.")


def _wheelhouse(config, filename, content):
    directory = states._safe(Path(config["state_root"]) / "wheelhouse-antlr-4.9.3", exists=False)
    directory.mkdir(exist_ok=True)
    if any(path.name != filename for path in directory.iterdir()):
        raise releases.ReleaseError("The recovery wheelhouse contains unrelated files; inspect it before retrying.")
    target = states._safe(directory / filename, exists=False)
    if target.exists():
        if states._file_sha(states._regular(target)) != hashlib.sha256(content).hexdigest():
            raise releases.ReleaseError("The saved antlr wheel differs; no file was overwritten.")
    else:
        with target.open("xb") as handle:
            handle.write(content)
    return directory


def _original_only(config, registry, target):
    manager.require_idle(registry)
    original = {"kind": "original", "source_commit": None, "python": config["source_python"]}
    if (registry.get("launch_uncertain") or registry.get("current") != original
            or registry.get("previous") is not None or registry.get("pending") is not None):
        raise manager.DeploymentError("This recovery only supports the first preparation with the original program selected.")
    process = registry.get("process")
    if process:
        executable = Path(process["executable"]).absolute()
        if executable == target or target in executable.parents:
            raise manager.DeploymentError("The candidate is referenced by a process; no files were moved.")


def recover(config_path, bundle, commit):
    commit = manager.commit_id(commit)
    config = states.load_config(config_path)
    env = states.runtime_environment(config)
    with manager.locked(config):
        target = states._safe(manager.target_for(config, commit), exists=False)
        _original_only(config, manager.read_registry(config), target)
        manifest = releases.validate_bundle(bundle, commit)
        if target.exists():
            if not target.is_dir():
                raise releases.ReleaseError("The candidate path is not a directory.")
            prepared = states._safe(target / "release.json", exists=False)
            if prepared.exists():
                metadata = releases.validate_prepared(target, commit, config["source_python"], env=env)
                if metadata["bundle_sha256"] != states._file_sha(Path(bundle)):
                    raise releases.ReleaseError("The prepared candidate belongs to a different artifact.")
                return _result(commit, metadata)
            old_manifest = releases._json(states._regular(target / "bundle" / "manifest.json").read_bytes())
            if old_manifest != manifest:
                raise releases.ReleaseError("The failed candidate manifest differs from the selected artifact.")
            states._regular(target / "prepare.log")
        else:
            raise releases.ReleaseError("No failed candidate exists; use the normal Prepare command.")
        inventory = releases.probe_python(config["source_python"], env=env)
        if inventory["packages"].get(PACKAGE) != VERSION:
            raise releases.ReleaseError("The source runtime does not require antlr4-python3-runtime 4.9.3.")
        filename, content = _cached_wheel(config, env)
        wheelhouse = _wheelhouse(config, filename, content)
        preserved = states._safe(target.with_name(commit + ".failed-" + uuid.uuid4().hex), exists=False)
        if preserved.exists():
            raise releases.ReleaseError("The failure preservation path already exists; no candidate was moved.")
        target.rename(preserved)
        metadata = releases.prepare_release(bundle, commit, target, config["source_python"],
                                            config["uv_exe"], wheelhouse=wheelhouse, env=env)
        return _result(commit, metadata)


def _result(commit, metadata):
    return {"prepared": True, "source_commit": commit, "server_changed": False,
            "webui_version": metadata["webui_version"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        result = recover(args.config, args.bundle, args.commit)
    except (manager.DeploymentError, states.StateError, releases.ReleaseError) as error:
        parser.exit(1, f"Recovery stopped: {error}\n")
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, csv.Error):
        parser.exit(1, "Recovery stopped: local state or a wheel could not be verified; inspect the local preparation files.\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
