"""Validate a pinned demo bundle and prepare an offline, inactive environment.

Never imports Open WebUI, changes the source environment, or starts a server.
The caller authenticates the artifact's origin; hashes verify its integrity.
"""

import argparse
import base64
import csv
from email.parser import BytesParser
from functools import wraps
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import sys
import zipfile

try:
    from . import build_demo_bundle as bundles, build_ees_webui as branding
except ImportError:
    import build_demo_bundle as bundles
    import build_ees_webui as branding

MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PACKAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]*\Z")
RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
PROBE = """import importlib.metadata as m, importlib.util, json, pathlib, sys
items = []
metadata_root = None
for d in m.distributions():
    direct = json.loads(d.read_text('direct_url.json') or '{}')
    name = d.metadata.get('Name')
    if (name or '').lower().replace('_', '-') == 'open-webui':
        metadata_root = str(pathlib.Path(d.locate_file('')).absolute())
    items.append({'name': name, 'version': d.version,
                  'direct': bool(direct), 'archive': 'archive_info' in direct,
                  'editable': bool(direct.get('dir_info', {}).get('editable')),
                  'requires': (d.requires or []) if (name or '').lower().replace('_', '-') == 'open-webui' else []})
spec = importlib.util.find_spec('open_webui')
package_dir = str(pathlib.Path(spec.origin).absolute().parent) if spec and spec.origin else None
print(json.dumps({'python_version': sys.version, 'python_minor': list(sys.version_info[:2]),
                  'platform': sys.platform, 'packages': items,
                  'app': {'package_dir': package_dir, 'metadata_root': metadata_root}}))
"""
WINDOWS_CA_EXPORT = """import ssl, sys
if sys.platform != 'win32':
    raise RuntimeError('Windows certificate stores are required')
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.load_default_certs(ssl.Purpose.SERVER_AUTH)
certificates = context.get_ca_certs(binary_form=True)
if not certificates:
    raise RuntimeError('No trusted CA certificates were loaded')
sys.stdout.buffer.write(''.join(ssl.DER_cert_to_PEM_cert(c) for c in certificates).encode('ascii'))
"""
MAX_CA_BYTES = 4 * 1024 * 1024


class ReleaseError(ValueError):
    """Invalid input or an unprepared candidate; safe to display without raw logs."""


def _guarded(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, zipfile.BadZipFile, UnicodeError, KeyError, TypeError, csv.Error) as error:
            raise ReleaseError("Release input or local file operation is invalid; existing runtime was not activated or changed.") from error
    return checked


def _json(content):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseError("Duplicate JSON keys are not supported.")
            result[key] = value
        return result
    if len(content) > MAX_JSON_BYTES:
        raise ReleaseError("Manifest exceeds the supported size.")
    try:
        value = json.loads(content, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError) as error:
        raise ReleaseError("Invalid JSON manifest.") from error


def _entries(archive, maximum_entries=1000, maximum_file=MAX_BUNDLE_BYTES):
    entries, folded, total = {}, set(), 0
    for entry in archive.infolist():
        name = entry.filename
        parts = name.split("/")
        if (entry.is_dir() or name != entry.orig_filename or len(name) > 240 or PurePosixPath(name).is_absolute()
                or "\\" in name or any(ord(c) < 32 for c in name)
                or any(p in ("", ".", "..") or p.endswith((".", " ")) or ":" in p or RESERVED.fullmatch(p) for p in parts)
                or name.casefold() in folded
                or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                or entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise ReleaseError("ZIP contains an unsafe or duplicate entry.")
        total += entry.file_size
        if (len(entries) >= maximum_entries or entry.file_size > maximum_file
                or total > MAX_EXPANDED_BYTES or entry.file_size > max(entry.compress_size, 1) * 100):
            raise ReleaseError("ZIP exceeds supported extraction limits.")
        entries[name] = entry
        folded.add(name.casefold())
    for name in folded:
        if any("/".join(name.split("/")[:i]) in folded for i in range(1, name.count("/") + 1)):
            raise ReleaseError("ZIP contains conflicting file and directory paths.")
    return entries


def _digest(stream):
    result, size = hashlib.sha256(), 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
        size += len(chunk)
    return result.hexdigest(), size


def _wheel(content, expected):
    if (not isinstance(expected, dict) or type(expected.get("schema_version")) is not int
            or expected.get("schema_version") != 1 or expected.get("version") != branding.VERSION
            or expected.get("upstream_version") != branding.UPSTREAM_VERSION
            or expected.get("source") != {"filename": branding.SOURCE_FILENAME, "sha256": branding.SOURCE_SHA256}
            or expected.get("wheel") != {"filename": branding.WHEEL_FILENAME, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}):
        raise ReleaseError("Branding wheel does not match the supported build manifest.")
    with zipfile.ZipFile(io.BytesIO(content)) as wheel:
        names = _entries(wheel, maximum_entries=10000, maximum_file=64 * 1024 * 1024)
        record_name = branding.TARGET_INFO + "RECORD"
        metadata_name = branding.TARGET_INFO + "METADATA"
        if not {record_name, metadata_name, branding.TARGET_INFO + "WHEEL"}.issubset(names):
            raise ReleaseError("Required wheel metadata is missing.")
        metadata = BytesParser().parsebytes(wheel.read(metadata_name))
        if metadata.get("Name") != "open-webui" or metadata.get("Version") != branding.VERSION:
            raise ReleaseError("Wheel package identity is not the expected release.")
        recorded = set()
        for row in csv.reader(io.StringIO(wheel.read(record_name).decode("utf-8"))):
            if len(row) != 3 or row[0] not in names or row[0] in recorded:
                raise ReleaseError("Invalid wheel RECORD entry.")
            name, digest, size = row
            recorded.add(name)
            if name == record_name:
                if digest or size:
                    raise ReleaseError("Invalid wheel RECORD self entry.")
                continue
            with wheel.open(name) as stream:
                actual, count = _digest(stream)
            encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).rstrip(b"=").decode()
            if digest != "sha256=" + encoded or size != str(count):
                raise ReleaseError("Wheel RECORD integrity check failed.")
        if recorded != set(names):
            raise ReleaseError("Wheel RECORD does not cover every entry.")
        return sorted(metadata.get_all("Requires-Dist", []))


def _validate(archive, expected_commit):
    if not isinstance(expected_commit, str) or not HEX40.fullmatch(expected_commit):
        raise ReleaseError("Use the exact lowercase 40-character source commit.")
    names = _entries(archive)
    if "manifest.json" not in names or names["manifest.json"].file_size > MAX_JSON_BYTES:
        raise ReleaseError("Expected the inner EES demo ZIP with manifest.json at its root.")
    manifest = _json(archive.read("manifest.json"))
    if (type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1
            or manifest.get("source_commit") != expected_commit or manifest.get("source_dirty") is not False
            or manifest.get("source_url") != bundles.REPOSITORY_URL + "/tree/" + expected_commit
            or not isinstance(manifest.get("files"), list)):
        raise ReleaseError("Bundle is not the requested clean source commit.")
    declared = {}
    for row in manifest["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size"}:
            raise ReleaseError("Invalid file manifest entry.")
        name = row["path"]
        if (not isinstance(name, str) or name not in names or name in declared
                or not (bundles.included_source(name) or name in {"BUNDLE-README.md", "branding/manifest.json", "branding/" + branding.WHEEL_FILENAME})
                or type(row["size"]) is not int or row["size"] != names[name].file_size
                or not isinstance(row["sha256"], str) or not HEX64.fullmatch(row["sha256"])):
            raise ReleaseError("Unexpected or inconsistent bundle file.")
        with archive.open(name) as stream:
            actual, size = _digest(stream)
        if (actual, size) != (row["sha256"], row["size"]):
            raise ReleaseError("Bundle file integrity check failed.")
        declared[name] = row
    required = bundles.GUIDES | {"BUNDLE-README.md", "branding/manifest.json", "branding/" + branding.WHEEL_FILENAME}
    if (set(names) != set(declared) | {"manifest.json"} or not required.issubset(declared)
            or not any(n.startswith("agent-pack/") for n in declared)):
        raise ReleaseError("Bundle contains missing, extra, or unsupported files.")
    embedded = _json(archive.read("branding/manifest.json"))
    if embedded != manifest.get("branding"):
        raise ReleaseError("Nested branding manifests disagree.")
    requires = _wheel(archive.read("branding/" + branding.WHEEL_FILENAME), embedded)
    return manifest, requires


def _open_bundle(bundle):
    path = Path(bundle)
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES
            or not re.fullmatch(r"EES-demo-[0-9a-f]{12}\.zip", path.name)):
        raise ReleaseError("Select a regular, supported inner EES demo ZIP.")
    return zipfile.ZipFile(path)


def _linked(path):
    return path.is_symlink() or (path.exists() and bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400))


def _ca_directory(target_dir):
    target = Path(target_dir).absolute()
    directory = target / "trusted-ca"
    if (not target.is_dir() or any(_linked(path) for path in (directory, target, *target.parents))
            or (directory.exists() and not directory.is_dir())):
        raise ReleaseError("Trusted CA paths must be ordinary directories inside the prepared release.")
    return directory


def _validate_ca_payload(payload):
    try:
        if (not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_CA_BYTES
                or not re.fullmatch(rb"(?:-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*)+", payload)):
            raise ValueError()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=payload.decode("ascii"))
        if not context.get_ca_certs():
            raise ValueError()
    except (ValueError, UnicodeError, ssl.SSLError):
        raise ReleaseError("Trusted CA export must contain a nonempty, valid public CA bundle.") from None


def _collect_windows_ca(executable, env, *, cwd=None):
    try:
        child_env = {key: value for key, value in env.items() if key.upper() != "SSLKEYLOGFILE"}
        result = subprocess.run([str(executable), "-I", "-S", "-B", "-c", WINDOWS_CA_EXPORT],
                                env=child_env, stdin=subprocess.DEVNULL, capture_output=True,
                                check=True, timeout=30, cwd=cwd)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise ReleaseError("Windows CA export failed; the existing server was not stopped.") from None


@_guarded
def windows_ca_path(target_dir, digest):
    """Resolve only an intact public CA snapshot belonging to this release."""
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ReleaseError("The selected trusted CA fingerprint is invalid.")
    path = _ca_directory(target_dir) / (digest + ".pem")
    if (_linked(path) or not path.is_file() or path.stat().st_nlink != 1
            or not 0 < path.stat().st_size <= MAX_CA_BYTES):
        raise ReleaseError("The selected trusted CA snapshot is missing or is not a regular file.")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ReleaseError("The selected trusted CA snapshot changed; preserve and inspect the release.")
    _validate_ca_payload(payload)
    return path


@_guarded
def prepare_windows_ca(target_dir, executable, env, *, cwd=None):
    """Freeze candidate Windows/default trust without touching its packages or registration."""
    directory = _ca_directory(target_dir)
    payload = _collect_windows_ca(executable, env, cwd=cwd)
    _validate_ca_payload(payload)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / (digest + ".pem")
    directory.mkdir(exist_ok=True)
    # Content-addressed files are never replaced, including during a later Deploy.
    if not path.exists() and not _linked(path):
        created = False
        try:
            with path.open("xb") as handle:
                created = True
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            if created:
                path.unlink(missing_ok=True)
            raise
    windows_ca_path(target_dir, digest)
    return digest


@_guarded
def validate_bundle(bundle, expected_commit):
    try:
        with _open_bundle(bundle) as archive:
            return _validate(archive, expected_commit)[0]
    except (zipfile.BadZipFile, UnicodeError, KeyError) as error:
        raise ReleaseError("Bundle archive is corrupt or incomplete.") from error


def _empty_directory(target):
    target = Path(target).absolute()
    if any(_linked(parent) for parent in (target, *target.parents)):
        raise ReleaseError("Release paths cannot contain symlinks.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ReleaseError("Extraction requires a new or empty directory.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _extract(archive, directory):
    directory = _empty_directory(directory)
    for entry in archive.infolist():
        target = directory.joinpath(*entry.filename.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry) as source, target.open("xb") as destination:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                destination.write(chunk)


@_guarded
def extract_bundle(bundle, expected_commit, target_dir):
    with _open_bundle(bundle) as archive:
        manifest, _ = _validate(archive, expected_commit)
        _extract(archive, target_dir)
    return manifest


def _environment(env=None):
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP", "TMPDIR",
            "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG", "UV_CACHE_DIR",
            "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"}
    return {k: v for k, v in (os.environ if env is None else env).items() if k.upper() in keep}


def probe_python(executable, env=None):
    try:
        result = subprocess.run([str(executable), "-I", "-B", "-c", PROBE], check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=_environment(env), timeout=60)
        data = _json(result.stdout)
        packages, requires = {}, []
        for item in data["packages"]:
            name, version = item["name"], item["version"]
            if not isinstance(name, str) or not PACKAGE.fullmatch(name) or not isinstance(version, str) or not VERSION.fullmatch(version):
                raise ReleaseError("Installed package metadata cannot be reproduced safely.")
            name = re.sub(r"[-_.]+", "-", name).lower()
            if (name in packages or item.get("editable")
                    or (item["direct"] and (name != "open-webui" or not item.get("archive")))):
                raise ReleaseError("Duplicate, editable, or direct-URL dependencies require a reviewed wheel inventory.")
            packages[name] = version
            if name == "open-webui":
                requires = sorted(item["requires"])
        if data["python_minor"] != [3, 11] or packages.get("open-webui") not in {branding.UPSTREAM_VERSION, branding.VERSION}:
            raise ReleaseError("Expected the existing Python 3.11 and supported Open WebUI runtime.")
        return {"python_version": data["python_version"], "platform": data["platform"], "packages": packages, "requires": requires, "app": data.get("app")}
    except (OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        raise ReleaseError("Could not inspect the selected Python runtime without importing the application.") from error


@_guarded
def prepare_release(bundle, expected_commit, target_dir, source_python, uv_exe, wheelhouse=None, env=None):
    target_dir, source_python, uv_exe = Path(target_dir).absolute(), Path(source_python).absolute(), Path(uv_exe).absolute()
    if target_dir.exists() or target_dir.is_symlink() or not source_python.is_file() or not uv_exe.is_file():
        raise ReleaseError("Use an unused release directory and existing Python and uv executable paths.")
    if wheelhouse is not None:
        wheelhouse = Path(wheelhouse).absolute()
        if not wheelhouse.is_dir():
            raise ReleaseError("The optional wheelhouse must be an existing local directory.")
    with _open_bundle(bundle) as archive:
        manifest, requires = _validate(archive, expected_commit)
        before = probe_python(source_python, env=env)
        if requires != before["requires"]:
            raise ReleaseError("Candidate dependency declarations differ from the current application.")
        _empty_directory(target_dir)
        _extract(archive, target_dir / "bundle")
    venv = target_dir / "venv"
    target_python = venv / ("Scripts/python.exe" if before["platform"] == "win32" else "bin/python")
    pins = target_dir / "dependencies.txt"
    pins.write_text("".join(f"{name}=={version}\n" for name, version in sorted(before["packages"].items()) if name != "open-webui"), encoding="utf-8")
    common = [str(uv_exe), "--no-config", "--offline", "--no-python-downloads"]
    commands = [common + ["venv", "--no-project", "--python", str(source_python), str(venv)],
                common + ["pip", "install", "--python", str(target_python), "--no-deps", "--only-binary", ":all:",
                          "--no-sources", "--link-mode", "copy", "--requirements", str(pins),
                          str(target_dir / "bundle" / "branding" / branding.WHEEL_FILENAME)]]
    if wheelhouse:
        commands[1] += ["--find-links", str(wheelhouse)]
    commands.append(common + ["pip", "check", "--python", str(target_python)])
    try:
        with (target_dir / "prepare.log").open("wb") as log:
            for command in commands:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, env=_environment(env),
                               cwd=target_dir, timeout=1800)
        after = probe_python(target_python, env=env)
        expected = dict(before["packages"], **{"open-webui": branding.VERSION})
        if (after["packages"] != expected or after["python_version"] != before["python_version"]
                or after["platform"] != before["platform"] or after["requires"] != requires):
            raise ReleaseError("Candidate Python or installed inventory differs from the preserved baseline.")
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseError("Offline preparation failed; the source runtime is unchanged. Review the local prepare.log and supply missing wheels.") from error
    with Path(bundle).open("rb") as stream:
        bundle_sha, _ = _digest(stream)
    metadata = {"schema_version": 1, "state": "prepared", "source_commit": manifest["source_commit"],
                "bundle_sha256": bundle_sha, "source_python": str(source_python), "python_executable": str(target_python),
                "target_python": str(target_python), "source_python_version": before["python_version"],
                "webui_version": branding.VERSION, "venv_dir": str(venv),
                "packages": {"before": before["packages"], "after": after["packages"]}}
    metadata["metadata_sha256"] = _metadata_digest(metadata)
    (target_dir / "release.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def _metadata_digest(metadata):
    return hashlib.sha256(json.dumps({k: v for k, v in metadata.items() if k != "metadata_sha256"},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@_guarded
def validate_prepared(target_dir, expected_commit, source_python, env=None):
    target_dir, source_python = Path(target_dir).absolute(), Path(source_python).absolute()
    if any(_linked(parent) for parent in (target_dir, *target_dir.parents)):
        raise ReleaseError("Prepared release paths cannot contain symlinks.")
    metadata = _json((target_dir / "release.json").read_bytes())
    if (not isinstance(expected_commit, str) or not HEX40.fullmatch(expected_commit)
            or type(metadata.get("schema_version")) is not int or metadata.get("schema_version") != 1
            or metadata.get("state") != "prepared" or metadata.get("source_commit") != expected_commit
            or metadata.get("webui_version") != branding.VERSION
            or metadata.get("metadata_sha256") != _metadata_digest(metadata)
            or metadata.get("source_python") != str(source_python)
            or metadata.get("venv_dir") != str(target_dir / "venv")):
        raise ReleaseError("Prepared release metadata does not match the requested candidate.")
    before = probe_python(source_python, env=env)
    target_python = target_dir / "venv" / ("Scripts/python.exe" if before["platform"] == "win32" else "bin/python")
    if (metadata.get("target_python") != str(target_python) or metadata.get("python_executable") != str(target_python)
            or any(_linked(parent) for parent in target_python.parents if parent != target_dir and target_dir in parent.parents)
            or _linked(target_dir / "release.json")):
        raise ReleaseError("Prepared interpreter is outside the candidate environment.")
    after = probe_python(target_python, env=env)
    expected = dict(before["packages"], **{"open-webui": branding.VERSION})
    if (metadata.get("packages") != {"before": before["packages"], "after": after["packages"]}
            or after["packages"] != expected or before["python_version"] != after["python_version"]
            or metadata.get("source_python_version") != before["python_version"]
            or before["platform"] != after["platform"] or before["requires"] != after["requires"]):
        raise ReleaseError("Source or candidate inventory changed after preparation.")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "prepare"))
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--source-python", type=Path)
    parser.add_argument("--uv-exe", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "validate":
            validate_bundle(args.bundle, args.expected_commit)
        else:
            if not all((args.target_dir, args.source_python, args.uv_exe)):
                raise ReleaseError("Preparation requires target-dir, source-python, and uv-exe.")
            prepare_release(args.bundle, args.expected_commit, args.target_dir, args.source_python, args.uv_exe, args.wheelhouse)
    except (ReleaseError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, "Release operation stopped: " + (str(error) if isinstance(error, ReleaseError) else "Local file operation failed.") + "\n")
    print("Bundle validated." if args.action == "validate" else "Candidate prepared; no server or existing data was changed.")


if __name__ == "__main__":
    main()
