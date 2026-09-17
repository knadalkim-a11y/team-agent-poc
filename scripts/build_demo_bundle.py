"""Build a deterministic, allowlisted demo ZIP; never install or change sources.

Requires only Python's standard library and Git. Untracked files, runtime data,
credentials and environments are excluded. This is packaging, not a secret
scanner: credentials must never be placed in tracked Agent Pack source files.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile


REPOSITORY_URL = "https://github.com/knadalkim-a11y/team-agent-poc"
GUIDES = frozenset({
    "README.md", "versions.md", "docs/01-openwebui-install.md",
    "docs/03-openwebui-native-agent.md", "docs/07-team-quickstart.md",
})
PROFILE_ASSETS = frozenset({"branding/ees/assets/favicon.png", "branding/ees/assets/favicon.svg"})
SOURCE_SUFFIXES = frozenset({".md", ".py", ".json", ".html", ".css", ".js", ".svg"})
EXCLUDED_PARTS = frozenset({
    "venv", "node_modules", "__pycache__", "data", "runtime", "logs",
    "credentials", "secrets", "tokens", "pat",
})
SENSITIVE_NAME = re.compile(r"(^|[._-])(env|key|secret|credentials?|tokens?|pat)([._-]|$)", re.I)
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
# Accepted output contract of build_ees_webui.py; update together on a version change.
BRANDING_VERSION = "0.11.3+ees.10"
BRANDING_UPSTREAM = "0.11.3"
BRANDING_SOURCE_SHA256 = "8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547"


class BundleError(ValueError):
    """A source or artifact cannot be included safely and honestly."""


def git(root, *arguments):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise BundleError("Git source inspection failed; use a checked-out repository.") from error


def source_state(root):
    commit = git(root, "rev-parse", "HEAD").decode("ascii").strip()
    dirty = bool(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=no"))
    return commit, dirty


def included_source(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if name in GUIDES or name in PROFILE_ASSETS:
        return True
    return (
        len(path.parts) > 1 and path.parts[0] == "agent-pack"
        and path.suffix.lower() in SOURCE_SUFFIXES
        and not any(part.startswith(".") or part.lower() in EXCLUDED_PARTS for part in path.parts)
        and not SENSITIVE_NAME.search(path.name)
    )


def read_regular(root, name):
    path = root / name
    current = path
    while current != root:
        if current.is_symlink():
            raise BundleError("Symlinks are not supported in demo inputs: " + name)
        current = current.parent
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise BundleError("Missing or non-regular demo input: " + name)
    return path.read_bytes()


def source_files(root):
    files = {}
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode("utf-8")
        if not included_source(name):
            continue
        mode, _, stage = metadata.decode("ascii").split()
        if stage != "0" or mode not in {"100644", "100755"}:
            raise BundleError("Unmerged or non-regular tracked source: " + name)
        files[name] = read_regular(root, name)
    if not GUIDES.issubset(files) or not any(name.startswith("agent-pack/") for name in files):
        raise BundleError("Tracked Agent Pack and required demo guides are missing.")
    return files


def branding_files(directory):
    directory = directory.resolve()
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise BundleError("Branding directory must contain exactly one wheel and manifest.json.")
    manifest_bytes = read_regular(directory, "manifest.json")
    try:
        manifest = json.loads(manifest_bytes)
    except (ValueError, UnicodeError) as error:
        raise BundleError("Branding manifest must be valid JSON.") from error
    if not isinstance(manifest, dict):
        raise BundleError("Branding manifest must be a JSON object.")
    wheel_name = "open_webui-" + BRANDING_VERSION + "-py3-none-any.whl"
    expected_source = {
        "filename": "open_webui-" + BRANDING_UPSTREAM + "-py3-none-any.whl",
        "sha256": BRANDING_SOURCE_SHA256,
    }
    wheel_bytes = read_regular(directory, wheels[0].name)
    expected_wheel = {"filename": wheel_name, "sha256": digest(wheel_bytes), "size": len(wheel_bytes)}
    if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or manifest.get("upstream_version") != BRANDING_UPSTREAM
            or manifest.get("version") != BRANDING_VERSION
            or manifest.get("source") != expected_source
            or wheels[0].name != wheel_name
            or manifest.get("wheel") != expected_wheel):
        raise BundleError("Branding wheel bytes/version do not match the supported builder manifest.")
    return {
        "branding/manifest.json": manifest_bytes,
        "branding/" + wheels[0].name: wheel_bytes,
    }, manifest


def digest(content):
    return hashlib.sha256(content).hexdigest()


def build_bundle(root, output_dir, branding_dir=None, allow_dirty=False):
    root = Path(root).resolve()
    state = source_state(root)
    commit, dirty = state
    if dirty and not allow_dirty:
        raise BundleError("Tracked sources have changes; commit them or use --allow-dirty for local development.")
    files = source_files(root)
    branding = None
    if branding_dir is not None:
        additions, branding = branding_files(Path(branding_dir))
        files.update(additions)
    source_url = REPOSITORY_URL + "/tree/" + commit
    files["BUNDLE-README.md"] = (
        "# EES 팀 시연 적용 묶음\n\n"
        "Agent Pack과 선택한 사용 안내를 담은 수동 적용 자료입니다.\n"
        "이 ZIP은 서버 설치·재시작·데이터 이전을 실행하지 않습니다.\n\n"
        "팀원 안내: docs/07-team-quickstart.md\n\n"
        "운영자 적용 안내: docs/03-openwebui-native-agent.md\n\n"
        "전체 문서와 이 묶음에 없는 상대 링크의 원본: [Git 원본](" + source_url + ")\n\n"
        "manifest.json에 실제 원본 커밋·변경 여부와 파일별 SHA-256을 기록했습니다. "
        "source_dirty가 true이면 미커밋 작업 파일이 포함된 개발용 묶음이며, "
        "Git 링크가 그 변경까지 담고 있지는 않습니다.\n"
    ).encode("utf-8")
    manifest = {
        "schema_version": 1, "source_commit": commit, "source_dirty": dirty,
        "source_url": source_url, "branding": branding,
        "files": [{"path": name, "size": len(content), "sha256": digest(content)}
                  for name, content in sorted(files.items())],
    }
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if source_state(root) != state:
        raise BundleError("Git source state changed while building; retry from a stable checkout.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / ("EES-demo-" + commit[:12] + ".zip")
    # Exclusive creation also protects an existing ZIP or symlink from replacement.
    with destination.open("xb") as target:
        try:
            # Stored entries avoid compression-library differences; wheels are already compressed.
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
                for name, content in sorted(files.items()):
                    entry = zipfile.ZipInfo(name, ZIP_TIME)
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(entry, content)
        except Exception:
            target.close()
            destination.unlink()
            raise
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--branding-dir", type=Path, help="Directory containing one prepared wheel and manifest.json")
    parser.add_argument("--allow-dirty", action="store_true", help="Local development only: include tracked working changes and mark source_dirty=true")
    args = parser.parse_args(argv)
    try:
        result = build_bundle(Path(__file__).resolve().parents[1], args.output_dir, args.branding_dir, args.allow_dirty)
    except (BundleError, OSError) as error:
        parser.exit(1, "Demo bundle not created: " + str(error) + "\n")
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
