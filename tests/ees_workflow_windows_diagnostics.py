"""Bounded, independent Windows failure capture; never relax release checks.

The two original test methods execute unchanged in separate Python processes.
The same read-only wheel inventory can run on Linux for payload/ZIP comparison.
Only synthetic test stores are used; no installed program or user DB is read.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import time
import traceback
from zipfile import ZipFile
import zlib


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA256 = "8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547"
LEGACY_SOURCE_COMMIT = "a443d30c6694df0e1cbe082a0b99aa5f2d566917"
LEGACY_SHA256 = "ad08078b9db2cf484a6af614b95bd4cf7c9910070d2505bc271065278d079ddd"
PREVIOUS_SOURCE_COMMIT = "991cdb1d80ae07471fb50594831d74fe602b1ef7"
PREVIOUS_SHA256 = "27f6a1c37264d4f205bedb6635c9eaae8a36a5d023d36d1dd595e34728c8b8d3"
TESTS = (
    "test_ees_workflow.WorkflowPreservationTests."
    "test_existing_published_drafts_history_and_skill_snapshot_survive_start_and_reads",
    "test_ees_workflow_contract.ContractAuthoringTests."
    "test_p_save_publish_exact_approval_and_reference_remapping",
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def inspect_wheel(path, expected_sha256):
    """Preserve bytes, order, RECORD and both central/local ZIP metadata."""
    path = Path(path)
    archive_bytes = path.read_bytes()
    result = {"filename": path.name, "size": len(archive_bytes),
              "sha256": sha256(archive_bytes), "expected_sha256": expected_sha256,
              "matches_expected_archive": sha256(archive_bytes) == expected_sha256,
              "members": [], "record_issues": []}
    digests = {}
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        result["archive_comment_hex"] = archive.comment.hex()
        infos = archive.infolist()
        result["central_directory_and_trailer_sha256"] = sha256(archive_bytes[archive.start_dir:])
        names = [info.filename for info in infos]
        result["duplicate_names"] = sorted(name for name, count in Counter(names).items() if count > 1)
        for info in infos:
            content = archive.read(info)
            digest = sha256(content)
            digests[info.filename] = (digest, len(content))
            header = struct.unpack_from("<4s5H3I2H", archive_bytes, info.header_offset)
            if header[0] != b"PK\x03\x04":
                raise ValueError("Invalid local ZIP header: " + info.filename)
            start = info.header_offset + 30 + header[-2] + header[-1]
            compressed = archive_bytes[start:start + info.compress_size]
            if len(compressed) != info.compress_size:
                raise ValueError("Truncated compressed member: " + info.filename)
            local_name_start = info.header_offset + 30
            result["members"].append({
                "name": info.filename, "sha256": digest, "size": len(content),
                "compressed_sha256": sha256(compressed), "compressed_size": info.compress_size,
                "crc32": f"{info.CRC:08x}", "compression": info.compress_type,
                "date_time": list(info.date_time), "create_system": info.create_system,
                "create_version": info.create_version, "extract_version": info.extract_version,
                "flag_bits": info.flag_bits, "volume": info.volume,
                "internal_attr": info.internal_attr, "external_attr": info.external_attr,
                "extra_hex": info.extra.hex(), "comment_hex": info.comment.hex(),
                "header_offset": info.header_offset,
                "local_header_hex": archive_bytes[info.header_offset:start].hex(),
                "local_name_hex": archive_bytes[local_name_start:local_name_start + header[-2]].hex(),
            })
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        result["record_names"] = record_names
        if len(record_names) != 1:
            result["record_issues"].append("Expected exactly one RECORD")
        else:
            record_name = record_names[0]
            record = archive.read(record_name)
            rows = list(csv.reader(io.StringIO(record.decode("utf-8"), newline="")))
            result["record_sha256"] = sha256(record)
            result["record_rows"] = rows
            seen = set()
            for row in rows:
                if len(row) != 3:
                    result["record_issues"].append("Invalid RECORD row: " + repr(row))
                    continue
                name, digest, size = row
                if name in seen:
                    result["record_issues"].append("Duplicate RECORD row: " + name)
                seen.add(name)
                if name not in digests:
                    result["record_issues"].append("Missing RECORD member: " + name)
                    continue
                actual, count = digests[name]
                if name == record_name:
                    if digest or size:
                        result["record_issues"].append("RECORD self-hash must be empty")
                    continue
                encoded = "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(actual)).rstrip(b"=").decode("ascii")
                if digest != encoded or size != str(count):
                    result["record_issues"].append("Hash/size mismatch: " + name)
            result["record_issues"].extend("Unrecorded member: " + name for name in names
                                           if not name.endswith("/") and name not in seen)
    result["member_count"] = len(result["members"])
    result["payload_inventory_sha256"] = sha256(json.dumps(
        [(row["name"], row["sha256"], row["size"]) for row in result["members"]],
        separators=(",", ":"), ensure_ascii=True).encode("ascii"))
    return result


def inspect_legacy_source(directory, commit=LEGACY_SOURCE_COMMIT):
    """Compare extracted historical source bytes with every pinned Git blob."""
    directory = Path(directory)
    tree = subprocess.run(["git", "ls-tree", "-rz", "--full-tree", commit],
                          cwd=ROOT, check=True, capture_output=True, timeout=30).stdout
    rows, issues = [], []
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        row = {"name": name, "mode": mode, "kind": kind, "expected_git_blob": expected}
        target = directory / name
        if kind != "blob" or target.is_symlink() or not target.is_file():
            row["matches"] = False
            issues.append("Missing/nonregular historical source: " + name)
        else:
            content = target.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
            row.update(sha256=sha256(content), size=len(content), actual_git_blob=actual,
                       matches=actual == expected)
            if actual != expected:
                issues.append("Historical source bytes differ: " + name)
        rows.append(row)
    return {"declared_source_commit": commit,
            "git_object_format": "sha1", "files": rows, "issues": issues}


def run_test(test_name, output, index, environment):
    command = [sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning",
               "-m", "unittest", "-v", test_name]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=ROOT, env=environment,
                                   capture_output=True, timeout=120)
        stdout, stderr = completed.stdout, completed.stderr
        returncode, timed_out = completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b"", error.stderr or b""
        returncode, timed_out = None, True
    name = f"test-{index}"
    (output / (name + ".stdout.log")).write_bytes(stdout)
    (output / (name + ".stderr.log")).write_bytes(stderr)
    result = {"test": test_name, "command": command, "returncode": returncode,
              "timed_out": timed_out, "timeout_seconds": 120,
              "seconds": round(time.monotonic() - started, 3),
              "stdout": name + ".stdout.log", "stderr": name + ".stderr.log"}
    summary = stderr.decode("utf-8", errors="replace")
    result["ran_exactly_one_test"] = bool(re.search(r"(?m)^Ran 1 test in ", summary))
    result["skipped"] = bool(re.search(r"(?m)^OK \(skipped=", summary))
    print(json.dumps(result, ensure_ascii=True), flush=True)
    # Emit the complete independent unittest summary before the next process.
    for data in (stdout, stderr):
        if data:
            print(data.decode("utf-8", errors="replace"), end="", flush=True)
    return result


def main():
    # Preserve full UTF-8 child tracebacks on the Windows console without changing
    # the child interpreter's locale/default-file-encoding test conditions.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "--output-dir", dest="output_dir", type=Path, required=True)
    parser.add_argument("--upstream-wheel", type=Path,
                        default=Path("dist/upstream/open_webui-0.11.3-py3-none-any.whl"))
    parser.add_argument("--legacy-wheel", type=Path,
                        default=Path("dist/legacy-branding/open_webui-0.11.3+ees.10-py3-none-any.whl"))
    parser.add_argument("--legacy-source", type=Path, default=Path("dist/legacy-source"))
    parser.add_argument("--previous-wheel", type=Path,
                        help="Also inventory the already-built ees.11 Restore fixture; no extra test is run.")
    parser.add_argument("--previous-source", type=Path)
    parser.add_argument("--inventory-only", action="store_true",
                        help="Collect the same package/source evidence without running tests (Linux comparison).")
    args = parser.parse_args()
    if not args.inventory_only and sys.platform != "win32":
        parser.error("The isolated test diagnostic must run on Windows; use --inventory-only for comparison.")
    if bool(args.previous_wheel) != bool(args.previous_source):
        parser.error("Provide --previous-wheel and --previous-source together.")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Refusing to overwrite existing diagnostic evidence.")
    output.mkdir(parents=True, exist_ok=True)
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": sys.version,
              "zlib_compile": zlib.ZLIB_VERSION, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
              "inventory_only": args.inventory_only, "tests": [], "evidence": {}, "errors": []}
    report["test_source_sha256"] = {name: sha256((ROOT / "tests" / name).read_bytes()) for name in (
        "test_ees_workflow.py", "test_ees_workflow_contract.py", "test_ees_work_authoring.py",
        "workflow_fixture.py", "ees_workflow_windows_diagnostics.py")}
    wheels = [("upstream", args.upstream_wheel, UPSTREAM_SHA256),
              ("legacy", args.legacy_wheel, LEGACY_SHA256)]
    sources = [("legacy", args.legacy_source, LEGACY_SOURCE_COMMIT)]
    if args.previous_wheel:
        wheels.append(("previous", args.previous_wheel, PREVIOUS_SHA256))
        sources.append(("previous", args.previous_source, PREVIOUS_SOURCE_COMMIT))
    for key, path, expected in wheels:
        try:
            inventory = inspect_wheel(path, expected)
            filename = key + "-wheel-inventory.json"
            write_json(output / filename, inventory)
            report["evidence"][key] = {"file": filename, "sha256": inventory["sha256"],
                "matches_expected_archive": inventory["matches_expected_archive"],
                "member_count": inventory["member_count"], "record_issues": inventory["record_issues"],
                "duplicate_names": inventory["duplicate_names"],
                "payload_inventory_sha256": inventory["payload_inventory_sha256"]}
            if not inventory["matches_expected_archive"] or inventory["record_issues"] or inventory["duplicate_names"]:
                report["errors"].append(key + " wheel differs from the unchanged pin or has invalid RECORD/duplicates")
        except Exception:
            report["errors"].append(key + ": " + traceback.format_exc())
    for key, directory, commit in sources:
        try:
            source = inspect_legacy_source(directory, commit)
            filename = key + "-source-inventory.json"
            write_json(output / filename, source)
            report["evidence"][key + "_source"] = {"file": filename,
                "commit": commit, "issues": source["issues"], "file_count": len(source["files"])}
            report["errors"].extend(source["issues"])
        except Exception:
            report["errors"].append(key + " source: " + traceback.format_exc())
    # Inventory failure must not suppress the independently requested error capture.
    if not args.inventory_only:
        environment = dict(os.environ, PYTHONIOENCODING="utf-8",
            EES_TEST_LEGACY_WORKFLOW_WHEEL=str(args.legacy_wheel.resolve()), EES_REQUIRE_LEGACY_WORKFLOW="1")
        environment["PYTHONPATH"] = str(ROOT / "tests") + (os.pathsep + environment["PYTHONPATH"]
                                                           if environment.get("PYTHONPATH") else "")
        for index, name in enumerate(TESTS, start=1):
            report["tests"].append(run_test(name, output, index, environment))
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["ok"] = not report["errors"] and all(row["returncode"] == 0 and not row["timed_out"]
        and row["ran_exactly_one_test"] and not row["skipped"] for row in report["tests"])
    write_json(output / "result.json", report)
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
