"""Apply only the pinned Open WebUI app and metadata using its existing Python.

The controller owns the process/port checks and deployment lock. This module
never installs dependencies, imports Open WebUI, or starts/stops a server.
"""

import base64
import copy
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

try:
    from . import ees_deploy_release as releases, ees_deploy_state as states
except ImportError:
    import ees_deploy_release as releases
    import ees_deploy_state as states

branding = releases.branding
RECORD = branding.TARGET_INFO + "RECORD"
# Present in the pinned upstream wheel: Docker reference text, never app files.
PACKAGING_FILES = frozenset({"requirements-min.txt", "data/readme.txt"})


class CustomizationError(ValueError):
    """A fixed diagnostic safe for the operator's short report."""


def _selection(value):
    if value is None:
        return
    if (not isinstance(value, dict) or set(value) != {"source_commit", "wheel_sha256", "record_sha256", "webui_version"}
            or not isinstance(value["webui_version"], str) or value["webui_version"] not in branding.PROGRAM_FRONTENDS
            or not isinstance(value["source_commit"], str) or not releases.HEX40.fullmatch(value["source_commit"])
            or any(not isinstance(value[key], str) or not releases.HEX64.fullmatch(value[key])
                   for key in ("wheel_sha256", "record_sha256"))):
        raise CustomizationError("The saved program selection is invalid; preserve the deployment record.")


def _version_paths(version):
    return f"open_webui-{version}.dist-info/", f"open_webui/frontend/{branding.PROGRAM_FRONTENDS[version]}/"


def _previous(value):
    if value is not None:
        if not isinstance(value, dict) or set(value) != {"active"}:
            raise CustomizationError("The saved previous program selection is invalid.")
        _selection(value["active"])


def _owner(value):
    if (not isinstance(value, dict) or set(value) != {"pid", "executable", "created_at"}
            or type(value["pid"]) is not int or value["pid"] <= 0
            or any(not isinstance(value[key], str) or not value[key] for key in ("executable", "created_at"))):
        raise CustomizationError("The operation owner cannot be verified.")


def validate_registry(registry):
    """Validate v2 customization state; leave all historical deployment fields intact."""
    if registry.get("schema_version") == 1:
        if "customization" in registry:
            raise CustomizationError("Legacy deployment state contains an unexpected program selection.")
        return {"active": None, "previous": None, "pending": None}
    value = registry.get("customization")
    if registry.get("schema_version") != 2 or not isinstance(value, dict) or set(value) != {"active", "previous", "pending"}:
        raise CustomizationError("The customization record is missing or invalid.")
    _selection(value["active"])
    _previous(value["previous"])
    pending = value["pending"]
    if pending is not None:
        if (not isinstance(pending, dict) or set(pending) != {"action", "owner", "before", "target", "old_previous", "stage"}
                or pending["action"] not in {"apply", "restore"}
                or pending["stage"] not in {"staging", "retire_previous", "move_active", "promote", "restore"}):
            raise CustomizationError("The incomplete program operation record is invalid.")
        _owner(pending["owner"])
        _selection(pending["before"])
        _selection(pending["target"])
        _previous(pending["old_previous"])
        if pending["target"] is None:
            raise CustomizationError("The incomplete program operation has no target identity.")
    return value


def _allowed_name(name, info=branding.TARGET_INFO):
    # Reuse the ZIP path rules, also when validating an extracted RECORD.
    parts = name.split("/")
    return (isinstance(name, str) and 0 < len(name) <= 240
            and not any(ord(char) < 32 for char in name) and "\\" not in name
            and not any(part in {"", ".", ".."} or part.endswith((".", " "))
                        or ":" in part or releases.RESERVED.fullmatch(part) for part in parts)
            and (name.startswith("open_webui/") or name.startswith(info))
            and not any(part.lower().endswith((".pth", ".data")) or part in {"__pycache__", ".env"} for part in parts)
            and not name.lower().endswith((".pyc", ".pyo")))


def _record_rows(content, *, allow_packaging=False, version=branding.VERSION):
    info, app = _version_paths(version)
    record_name = info + "RECORD"
    required = {record_name, info + "METADATA", info + "WHEEL", "open_webui/__init__.py",
                "open_webui/env.py", "open_webui/main.py", "open_webui/frontend/index.html", app + "version.json"}
    if version in {"0.11.3+ees.3", "0.11.3+ees.4", "0.11.3+ees.5", "0.11.3+ees.6", "0.11.3+ees.7"}:
        required.update(app + name for name in branding.THEME_FILES)
    if version == "0.11.3+ees.5":
        required.update(branding.LEGACY_WORK_FILES)
    if version in {"0.11.3+ees.6", "0.11.3+ees.7"}:
        # Previous installations keep their own frontend namespace after the
        # wrapper upgrades. Validate their files before Apply/Restore as well.
        required.update(app + name[len(branding.TARGET_APP):] if name.startswith(branding.TARGET_APP)
                        else name for name in branding.WORK_FILES)
    rows = {}
    folded = set()
    try:
        for row in csv.reader(io.StringIO(content.decode("utf-8"))):
            if (len(row) != 3 or (not _allowed_name(row[0], info)
                                 and not (allow_packaging and row[0] in PACKAGING_FILES))
                    or row[0].casefold() in folded):
                raise CustomizationError("Program RECORD contains an unsupported or duplicate path.")
            name, digest, size = row
            if name == record_name:
                if digest or size:
                    raise CustomizationError("Program RECORD self entry is invalid.")
            elif (not digest.startswith("sha256=") or len(digest) != 50
                  or not size.isascii() or not size.isdecimal() or str(int(size)) != size
                  or int(size) > 64 * 1024 * 1024):
                raise CustomizationError("Program RECORD requires exact SHA256 hashes and file sizes.")
            rows[name] = (digest, size)
            folded.add(name.casefold())
        if not required.issubset(rows) or len(rows) > 10000:
            raise CustomizationError("The complete app, frontend and metadata must be present together.")
        if any(name.startswith(branding.SOURCE_APP) for name in rows):
            raise CustomizationError("The selected wheel still contains the original frontend location.")
        if any(name.startswith(f"open_webui/frontend/{namespace}/")
               for item, namespace in branding.PROGRAM_FRONTENDS.items() if item != version for name in rows):
            raise CustomizationError("The selected program contains another release's frontend.")
        for name in folded:
            if any("/".join(name.split("/")[:i]) in folded for i in range(1, name.count("/") + 1)):
                raise CustomizationError("Program RECORD contains conflicting paths.")
        return rows
    except (UnicodeError, csv.Error, ValueError) as error:
        if isinstance(error, CustomizationError):
            raise
        raise CustomizationError("Program RECORD is invalid.") from None


def _metadata(read, version=branding.VERSION):
    info, app = _version_paths(version)
    metadata = BytesParser().parsebytes(read(info + "METADATA"))
    wheel = BytesParser().parsebytes(read(info + "WHEEL"))
    if (metadata.get_all("Name") != ["open-webui"] or metadata.get_all("Version") != [version]
            or wheel.get_all("Wheel-Version") != ["1.0"] or wheel.get_all("Root-Is-Purelib") != ["true"]
            or wheel.get_all("Tag") != ["py3-none-any"]):
        raise CustomizationError("Only the supported purelib Open WebUI app wheel is allowed.")
    try:
        frontend = json.loads(read(app + "version.json"))
    except (ValueError, UnicodeError):
        raise CustomizationError("The selected frontend version metadata is invalid.") from None
    if not isinstance(frontend, dict) or frontend.get("version") != version:
        raise CustomizationError("The selected app and frontend versions differ.")
    return sorted(metadata.get_all("Requires-Dist", []))


def _wheel_layout(content):
    """Extra app-only constraints after the existing release hash/RECORD validator."""
    with zipfile.ZipFile(io.BytesIO(content)) as wheel:
        names = releases._entries(wheel, maximum_entries=10000, maximum_file=64 * 1024 * 1024)
        if any(not _allowed_name(name) and name not in PACKAGING_FILES for name in names):
            raise CustomizationError("The wheel contains unsupported install paths or executable path hooks.")
        record = wheel.read(RECORD)
        rows = _record_rows(record, allow_packaging=True)
        if set(rows) != set(names):
            raise CustomizationError("The app RECORD and wheel file list differ.")
        _metadata(wheel.read)
        if PACKAGING_FILES.intersection(rows):
            # The complete original wheel/RECORD was verified by releases._wheel.
            # Retain only app+metadata and derive an exact RECORD for that subset;
            # the saved wheel SHA still identifies the unchanged input artifact.
            rows = {name: row for name, row in rows.items() if name not in PACKAGING_FILES}
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            for name in sorted(set(rows) - {RECORD}):
                writer.writerow([name, *rows[name]])
            writer.writerow([RECORD, "", ""])
            record = output.getvalue().encode("utf-8")
        return {"record_sha256": hashlib.sha256(record).hexdigest(), "record": record, "rows": rows}


def _paths(config, env=None):
    root = states._safe(config["state_root"])
    if not root.is_dir():
        raise CustomizationError("The registered wrapper directory is unavailable.")
    for key in ("source_prefix", "package_dir", "data_dir", "cwd"):
        other = states._safe(config[key])
        if root.is_relative_to(other) or other.is_relative_to(root):
            raise CustomizationError("The program directory overlaps the original environment or preserved data.")
    paths = tuple(states._safe(root / name, exists=False) for name in ("program", "program.previous", "program.staging"))
    for path in paths:
        if path.exists() and not path.is_dir():
            raise CustomizationError("The program location is not an ordinary directory.")
        for candidate in (path / ".env", path / "open_webui" / ".env", root / ".env", root.parent / ".env"):
            if candidate.exists() or candidate.is_symlink():
                raise CustomizationError("An unexpected program .env needs review; it was not changed.")
    if env is not None:
        if env.get("DATA_DIR") != config["data_dir"]:
            raise CustomizationError("Explicit preserved DATA_DIR is required before program selection.")
        if any(env.get(name) for name in ("PYTHONPATH", "PYTHONHOME")) or any(
                env.get(name, "1") != "1" for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS")):
            raise CustomizationError("Only the registered single-worker Python configuration is supported.")
    states._regular(config["source_python"], allow_hardlinks=True)
    return paths


def _load_bundle(config, bundle, commit, env):
    _paths(config, env)
    with releases._open_bundle(bundle) as archive:
        manifest, requires = releases._validate(archive, commit)
        content = archive.read("branding/" + branding.WHEEL_FILENAME)
    layout = _wheel_layout(content)
    if os.name == "nt" and any(len(str(Path(config["state_root"]) / "program.staging" / name)) >= 260
                                for name in layout["rows"]):
        raise CustomizationError("The complete program paths exceed the supported Windows path length.")
    baseline = releases.probe_python(config["source_python"], env=env)
    if baseline["packages"].get("open-webui") != branding.UPSTREAM_VERSION or baseline["requires"] != requires:
        raise CustomizationError("The original Open WebUI version or dependency requirements differ; no packages were changed.")
    if baseline.get("app") != {"package_dir": config["package_dir"],
                                "metadata_root": str(Path(config["package_dir"]).parent)}:
        raise CustomizationError("The existing Python selects a different app or metadata location than registered.")
    selection = {"source_commit": manifest["source_commit"], "wheel_sha256": hashlib.sha256(content).hexdigest(),
                 "record_sha256": layout["record_sha256"], "webui_version": branding.VERSION}
    return selection, content


def inspect_bundle(config, bundle, commit, env):
    """Read-only package metadata and bundle check; no application import or write."""
    return _load_bundle(config, bundle, commit, env)[0]


def _files(path):
    result = {}
    if not path.exists():
        return result
    for directory, folders, names in os.walk(path, followlinks=False):
        for folder in folders:
            states._safe(Path(directory) / folder)
        for name in names:
            target = states._regular(Path(directory) / name)
            result[target.relative_to(path).as_posix()] = target
    return result


def _check_tree(path, selection, *, partial=False, staging=False):
    _selection(selection)
    if selection is None:
        raise CustomizationError("An original app has no wrapper program directory.")
    version = selection["webui_version"]
    record_name = _version_paths(version)[0] + "RECORD"
    path = states._safe(path)
    if not path.is_dir():
        raise CustomizationError("The selected program directory is missing.")
    files = _files(path)
    if record_name not in files:
        if partial and not files:
            return {}
        # An interrupted first RECORD write cannot contain any app files yet.
        if staging and set(files) <= {".record.part"}:
            return files
        raise CustomizationError("The selected program metadata is missing; fallback is disabled.")
    record = files[record_name].read_bytes()
    if hashlib.sha256(record).hexdigest() != selection["record_sha256"]:
        raise CustomizationError("The selected program RECORD changed; preserve it for review.")
    rows = _record_rows(record, version=version)
    if (not set(files).issubset(rows) or (not partial and set(files) != set(rows))):
        raise CustomizationError("The selected program has missing or unexpected files.")
    for name, target in files.items():
        if name == record_name:
            continue
        digest, size = rows[name]
        if staging:
            if target.stat().st_size > int(size):
                raise CustomizationError("An incomplete staged file exceeds its declared size.")
            continue
        with target.open("rb") as source:
            actual, count = releases._digest(source)
        encoded = base64.urlsafe_b64encode(bytes.fromhex(actual)).rstrip(b"=").decode()
        if digest != "sha256=" + encoded or size != str(count):
            raise CustomizationError("A selected program file changed; preserve it for review.")
    if not partial:
        _metadata(lambda name: files[name].read_bytes(), version)
    return files


def validate_program(path, selection):
    """Verify app, static files and metadata against the recorded complete wheel."""
    _check_tree(Path(path), selection)
    return Path(path)


def _remove(path, selection, *, partial=False, staging=False):
    if not path.exists():
        return
    files = _check_tree(path, selection, partial=partial, staging=staging)
    record_name = _version_paths(selection["webui_version"])[0] + "RECORD"
    # Keep RECORD until all app files are removed so interrupted deletion remains
    # verifiable. No traversal follows links or deletes unknown file contents.
    for name in sorted(files, key=lambda name: name == record_name):
        files[name].unlink()
    for directory, _, _ in os.walk(path, topdown=False, followlinks=False):
        Path(directory).rmdir()


def _extract(content, path):
    layout = _wheel_layout(content)
    path.mkdir()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        record = path / RECORD
        record.parent.mkdir(parents=True)
        temporary = path / ".record.part"
        with temporary.open("xb") as output:
            output.write(layout["record"])
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(record)
        for name in layout["rows"]:
            if name == RECORD:
                continue
            target = path.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("xb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())


def _result(active, changed, action):
    return {"action": action, "changed": changed, "source_commit": active["source_commit"] if active else None,
            "original_program": active is None, "data_changed": False}


def _save(config, registry, record, stage):
    registry["customization"]["pending"]["stage"] = stage
    record(config, registry, "program_" + stage)


def _complete(config, registry, record, *, active, previous, event):
    incomplete = copy.deepcopy(registry["customization"])
    registry["customization"] = {"active": active, "previous": previous, "pending": None}
    try:
        record(config, registry, event)
    except BaseException:
        registry["customization"] = incomplete
        raise


def check_applicability(config, registry, env):
    """Check both retained app states and unused staging before asking to stop."""
    current = validate_registry(registry)
    if current["pending"]:
        raise CustomizationError("An incomplete program operation requires explicit Restore before Apply or Start.")
    if registry.get("phase") != "idle" or registry.get("pending") or registry.get("launch_uncertain"):
        raise CustomizationError("The existing deployment must be idle before adopting app-only management.")
    if (registry.get("current", {}).get("kind") != "original"
            or registry["current"].get("python") != config["source_python"]):
        raise CustomizationError("App-only management requires the registered original interpreter selection.")
    program, previous, staged = _paths(config, env)
    if current["active"]:
        validate_program(program, current["active"])
    elif program.exists():
        raise CustomizationError("An unrecorded program directory exists; it will not be replaced.")
    old_previous = current["previous"]
    if old_previous and old_previous["active"]:
        validate_program(previous, old_previous["active"])
    elif previous.exists():
        raise CustomizationError("An unrecorded previous program directory exists.")
    if staged.exists():
        raise CustomizationError("An unrecorded staging directory exists; preserve it for review.")
    return current


def apply(config, registry, bundle, commit, env, record, owner):
    """Apply a complete app while stopped; leave an explicit pending record on error."""
    _owner(owner)
    current = check_applicability(config, registry, env)
    program, previous, staged = _paths(config, env)
    selected, content = _load_bundle(config, bundle, commit, env)
    before, old_previous = current["active"], current["previous"]
    if before == selected:
        return _result(before, False, "apply")
    registry["schema_version"] = 2
    registry["customization"] = {"active": before, "previous": old_previous,
        "pending": {"action": "apply", "owner": dict(owner), "before": before, "target": selected,
                    "old_previous": old_previous, "stage": "staging"}}
    record(config, registry, "program_apply_started")
    _extract(content, staged)
    validate_program(staged, selected)
    _save(config, registry, record, "retire_previous")
    if old_previous and old_previous["active"]:
        _remove(previous, old_previous["active"])
    _save(config, registry, record, "move_active")
    if before:
        program.rename(previous)
    _save(config, registry, record, "promote")
    staged.rename(program)
    validate_program(program, selected)
    _complete(config, registry, record, active=selected, previous={"active": before}, event="program_applied")
    return _result(selected, True, "apply")


def check_resume(config, registry, env, selected):
    """Read-only validation of an operator-completed pending promotion."""
    current = validate_registry(registry)
    pending = current["pending"]
    if not pending or pending["action"] != "apply" or pending["stage"] != "promote":
        raise CustomizationError("Resume requires an incomplete Apply at the promote stage.")
    if (registry.get("phase") != "idle" or registry.get("pending") or registry.get("launch_uncertain")
            or registry.get("current", {}).get("kind") != "original"
            or registry["current"].get("python") != config["source_python"]):
        raise CustomizationError("Resume requires the idle registered original interpreter selection.")
    if (pending["before"] != current["active"] or pending["old_previous"] != current["previous"]
            or pending["target"] != selected):
        raise CustomizationError("The pending Apply, prior selection and supplied bundle must match exactly.")
    program, previous, staged = _paths(config, env)
    if staged.exists():
        raise CustomizationError("The staged program has not been manually promoted; no program files were moved.")
    validate_program(program, selected)
    if pending["before"]:
        validate_program(previous, pending["before"])
    elif previous.exists():
        raise CustomizationError("An unexpected previous program directory prevents Resume.")
    return current


def resume_apply(config, registry, bundle, commit, env, record, owner):
    """Explicitly finish a validated manual rename; never move or install files."""
    _owner(owner)
    selected, _ = _load_bundle(config, bundle, commit, env)
    current = check_resume(config, registry, env, selected)
    pending = dict(current["pending"], owner=dict(owner))
    registry["customization"] = dict(current, pending=pending)
    record(config, registry, "program_apply_resumed")
    _complete(config, registry, record, active=selected, previous={"active": pending["before"]},
              event="program_applied")
    return _result(selected, True, "apply")


def restore(config, registry, record, owner):
    """Restore the state immediately before Apply once, including interrupted Apply."""
    _owner(owner)
    current = validate_registry(registry)
    program, previous, staged = _paths(config)
    pending = current["pending"]
    resuming_restore = pending is not None and pending["action"] == "restore"
    if pending is None:
        if current["previous"] is None:
            if current["active"]:
                validate_program(program, current["active"])
            elif program.exists():
                raise CustomizationError("An unrecorded program directory exists.")
            if previous.exists() or staged.exists():
                raise CustomizationError("Unexpected program remnants need review.")
            return _result(current["active"], False, "restore")
        if current["active"] is None:
            raise CustomizationError("A restore record has no current customized program.")
        validate_program(program, current["active"])
        pending = {"action": "restore", "owner": dict(owner), "before": current["previous"]["active"],
                   "target": current["active"], "old_previous": None, "stage": "restore"}
    else:
        pending = dict(pending, action="restore", owner=dict(owner), stage="restore")
    desired, discarded = pending["before"], pending["target"]
    # Determine where the verified previous app is before deleting any app file.
    desired_in_program = False
    if desired is not None:
        if program.exists():
            try:
                validate_program(program, desired)
                desired_in_program = True
            except CustomizationError:
                pass
        if (desired_in_program and previous.exists()
                and desired["record_sha256"] == discarded["record_sha256"]):
            # Two source commits may contain identical app bytes. The saved
            # predecessor still wins when both directory identities match.
            try:
                validate_program(previous, desired)
                desired_in_program = False
            except CustomizationError:
                # An older, obsolete copy may be only partly retired. The
                # still-complete active app remains the restore source.
                pass
        if not desired_in_program:
            validate_program(previous, desired)
    if program.exists() and not desired_in_program:
        _check_tree(program, discarded, partial=resuming_restore)
    if previous.exists() and (desired is None or desired_in_program):
        obsolete = pending["old_previous"]
        if not obsolete or not obsolete["active"]:
            raise CustomizationError("An unexpected previous program would be overwritten.")
        _check_tree(previous, obsolete["active"], partial=True)
    if staged.exists():
        _check_tree(staged, discarded, partial=True, staging=True)
    registry["schema_version"] = 2
    registry["customization"] = dict(current, pending=pending)
    record(config, registry, "program_restore_started")
    if program.exists() and not desired_in_program:
        _remove(program, discarded, partial=True)
    if desired is not None and not desired_in_program:
        previous.rename(program)
    elif previous.exists():
        _remove(previous, pending["old_previous"]["active"], partial=True)
    if staged.exists():
        _remove(staged, discarded, partial=True, staging=True)
    if desired:
        validate_program(program, desired)
    _complete(config, registry, record, active=desired, previous=None, event="program_restored")
    return _result(desired, True, "restore")
