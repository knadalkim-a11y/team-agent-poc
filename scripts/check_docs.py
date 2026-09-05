"""Read-only, offline Markdown hygiene checks for this small repository.

Checks common inline/reference Markdown links, ATX/setext heading anchors and
explicit HTML ids. This is not a full CommonMark renderer or a semantic review.
Review candidates are warnings, never deletion instructions. No files are written,
no external URLs are requested, and Git/Python packages are not required.
"""

import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "runtime", "logs", ".uv-cache", ".idea", ".vscode"}
MAX_DOCUMENT_BYTES = 1024 * 1024
REFERENCE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*(.*)$")
LABEL = re.compile(r"(?<!\\)\[([^\]\n]*)\]")


def _blank(match):
    return re.sub(r"[^\n]", " ", match.group(0))


def _visible(text):
    text = re.sub(r"<!--[\s\S]*?-->", _blank, text)
    output, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + r"{" + str(fence[1]) + r",}\s*$", line):
                fence = None
            output.append(re.sub(r"[^\n]", " ", line))
        elif marker:
            fence = (marker[1][0], len(marker[1]))
            output.append(re.sub(r"[^\n]", " ", line))
        elif line.startswith("    ") or line.startswith("\t"):
            # Indented code is ignored. Links nested this deeply in lists are
            # outside this lightweight checker's supported Markdown subset.
            output.append(re.sub(r"[^\n]", " ", line))
        else:
            output.append(line)
    return "".join(output)


def _anchors(text):
    visible = _visible(text)
    html_source = re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", _blank, visible)
    ids = set(re.findall(r"<[^>]*?\s(?:id|name)\s*=\s*['\"]([^'\"]+)['\"]", html_source))
    lines, generated = visible.splitlines(), set()
    for index, line in enumerate(lines):
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        heading = match[1] if match else None
        if heading is None and index + 1 < len(lines) and line.strip() and re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1]):
            heading = line.strip()
        if heading is None:
            continue
        heading = html.unescape(re.sub(r"<[^>]+>", "", heading))
        heading = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        base = re.sub(r"[^\w\-\s]", "", heading.lower()).replace(" ", "-")
        candidate, suffix = base, 0
        while candidate in generated:
            suffix += 1
            candidate = base + "-" + str(suffix)
        generated.add(candidate)
    return ids | generated


def _destination(text, start):
    """Return a destination and end index; support escaped/balanced parentheses."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i] == "<":
        end = text.find(">", i + 1)
        return (text[i + 1:end], end + 1) if end >= 0 else (None, i)
    chars, depth = [], 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            chars.append(text[i + 1])
            i += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif char.isspace() and depth == 0:
            break
        chars.append(char)
        i += 1
    return ("".join(chars), i) if depth == 0 else (None, i)


def _reference_key(label):
    return " ".join(label.split()).casefold()


def _links(text):
    # Keep code in headings for slug generation, but mask it during link parsing.
    visible = re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", _blank, _visible(text))
    definitions, body = {}, []
    for line in visible.splitlines():
        definition = REFERENCE.match(line)
        if definition and not definition[1].startswith("^"):
            target, _ = _destination(definition[2], 0)
            if target is not None:
                definitions[_reference_key(definition[1])] = target
            body.append("")
        else:
            body.append(line)
    for number, line in enumerate(body, 1):
        consumed = 0
        for label in LABEL.finditer(line):
            if label.start() < consumed or label[1].startswith("^"):
                continue
            end = label.end()
            if line[end:end + 1] == "(":
                target, stop = _destination(line, end + 1)
                if target is not None:
                    yield number, target, None
                consumed = stop + 1
            elif line[end:end + 1] == "[":
                stop = line.find("]", end + 1)
                if stop < 0:
                    continue
                key = _reference_key(line[end + 1:stop] or label[1])
                yield number, definitions.get(key), key
                consumed = stop + 1
            else:
                key = _reference_key(label[1])
                if key in definitions:
                    yield number, definitions[key], key


def check_repository(root):
    report = {"files_checked": 0, "links_checked": 0, "errors": [], "warnings": []}

    def issue(level, code, file, message, **extra):
        report[level].append({"code": code, "file": file, "message": message, **extra})

    try:
        root = Path(root).resolve()
        valid_root = root.is_dir()
    except (OSError, RuntimeError, ValueError):
        valid_root = False
    if not valid_root:
        issue("errors", "invalid_root", ".", "Repository root must be an existing directory.")
        return report
    documents = {}

    def walk_error(error):
        issue("errors", "scan_failed", ".", "A directory could not be scanned.")

    def safe_scan_path(location):
        # Windows junctions need not be symlinks. Check before descent/open,
        # and skip aliases inside the root too so junction cycles cannot loop.
        try:
            resolved = location.resolve()
            resolved.relative_to(root)
            if resolved == location:
                return True
        except (OSError, RuntimeError, ValueError):
            pass
        issue("warnings", "scan_path_skipped", location.relative_to(root).as_posix(), "Redirected or unresolvable paths are not scanned.")
        return False

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        allowed = []
        for name in sorted(dirs):
            location = Path(directory) / name
            if name in IGNORED_DIRS:
                continue
            if location.is_symlink():
                issue("warnings", "symlink_skipped", location.relative_to(root).as_posix(), "Symlink directories are not scanned.")
                continue
            if safe_scan_path(location):
                allowed.append(name)
        dirs[:] = allowed
        for name in sorted(names):
            if not name.lower().endswith(".md"):
                continue
            location = Path(directory) / name
            relative = location.relative_to(root).as_posix()
            if location.is_symlink():
                issue("warnings", "symlink_skipped", relative, "Symlink documents are not read.")
                continue
            if not safe_scan_path(location):
                continue
            try:
                with location.open("rb") as stream:
                    data = stream.read(MAX_DOCUMENT_BYTES + 1)
                if len(data) > MAX_DOCUMENT_BYTES:
                    issue("errors", "document_too_large", relative, "Document exceeds the 1 MiB scan limit.")
                    continue
                documents[relative] = data.decode("utf-8-sig")
            except (OSError, UnicodeError):
                issue("errors", "read_failed", relative, "Document could not be read as UTF-8.")
    report["files_checked"] = len(documents)
    anchors = {name: _anchors(text) for name, text in documents.items()}
    graph = {name: set() for name in documents}

    for source, text in sorted(documents.items()):
        for line, target, reference in _links(text):
            if target is None:
                issue("errors", "undefined_reference", source, "Link reference has no definition.", line=line, target=reference)
                continue
            try:
                url = urlsplit(html.unescape(target))
            except ValueError:
                issue("errors", "invalid_link", source, "Link could not be parsed.", line=line)
                continue
            if url.scheme or url.netloc:
                continue  # Offline: do not request or validate external URLs.
            report["links_checked"] += 1
            relative = unquote(url.path)
            if relative.startswith("/") or "\\" in relative or "\x00" in relative:
                issue("errors", "invalid_local_path", source, "Use repository-relative Markdown paths.", line=line, target=target)
                continue
            lexical = root / source if not relative else (root / source).parent / relative
            try:
                destination = lexical.resolve()
                destination.relative_to(root)
            except (ValueError, OSError, RuntimeError):
                issue("errors", "outside_root", source, "Link escapes the repository or has a resolution error.", line=line, target=target)
                continue
            if not destination.exists():
                issue("errors", "missing_target", source, "Local link target does not exist.", line=line, target=target)
                continue
            if destination.is_dir():
                # A folder link makes its README reachable, not every descendant.
                destination = destination / "README.md"
            key = destination.relative_to(root).as_posix()
            if key in documents:
                graph[source].add(key)
                if url.fragment and unquote(url.fragment) not in anchors[key]:
                    issue("errors", "missing_anchor", source, "Markdown heading or explicit id was not found.", line=line, target=target)
            elif url.fragment and destination.suffix.lower() == ".md":
                issue("warnings", "anchor_not_checked", source, "Target document was not scanned; review the anchor manually.", line=line, target=target)

    entries = {name for name in documents if name in {"README.md", "AGENTS.md"} or Path(name).name == "SKILL.md"}
    reachable, pending = set(), list(entries)
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(graph[name] - reachable)
    for name in sorted(documents):
        managed = "/" not in name or name.startswith(("docs/", "evals/"))
        if managed and name not in reachable:
            issue("warnings", "unlinked_document", name, "No link path from README/AGENTS/SKILL entrypoints. Review, do not auto-delete; evidence may need preservation.")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report; do not create a file.")
    args = parser.parse_args(argv)
    report = check_repository(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print("DOCS {status} | files={files} links={links} errors={errors} review_candidates={warnings}".format(
            status="FAIL" if report["errors"] else "OK", files=report["files_checked"], links=report["links_checked"],
            errors=len(report["errors"]), warnings=len(report["warnings"])))
        for level in ("errors", "warnings"):
            for item in report[level]:
                fields = {**item, "level": level.upper(), "line": item.get("line", 0)}
                print("{level}: {file}:{line} {code} - {message}".format(**fields))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
