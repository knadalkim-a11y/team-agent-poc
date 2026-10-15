"""Reproduce Git/Black Work Tool hashes and their EOL/edge-space recognition hashes.

Development-only: run in a full repository clone with Black==26.5.1.
Prints the literal for ees_asset_guard.WORK_TOOL_SOURCE_HISTORY unless --check.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path
import pprint
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'agent-pack/skills/ees-work-demo/scripts/workflow_tool.py'
FORMATTER = '26.5.1'


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True).stdout


def sources(ref='HEAD'):
    import black
    if black.__version__ != FORMATTER:
        raise ValueError('The pinned editor formatter Black 26.5.1 is required.')
    output = {}
    for line in git('log', '--reverse', '--format=%H %cs', ref, '--', SOURCE).decode('ascii').splitlines():
        commit, date = line.split()
        raw = git('show', commit + ':' + SOURCE)
        original = raw.decode('utf-8')
        formatted = black.format_str(original, mode=black.Mode())
        black.assert_equivalent(original, formatted)
        black.assert_stable(original, formatted, mode=black.Mode())
        before = ast.parse(original, type_comments=True)
        after = ast.parse(formatted, type_comments=True)
        if ast.dump(before) != ast.dump(after):
            raise ValueError('Formatting changed the full AST: ' + commit)
        strings = lambda tree: sorted(repr(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)))
        if strings(before) != strings(after) or black.format_str(formatted, mode=black.Mode()) != formatted:
            raise ValueError('Formatting changed a string or was not idempotent: ' + commit)
        for content, form in ((raw, 'git'), (formatted.encode('utf-8'), 'black-' + FORMATTER)):
            # Pinned Native plugin replace_imports performs these text replacements.
            # The reviewed sources must reach Native storage without another transform.
            if any(old in content for old in (b'from utils', b'from apps', b'from main', b'from config')):
                raise ValueError('Native import rewriting needs a separately reviewed form: ' + commit)
            digest = hashlib.sha256(content).hexdigest()
            normalized = content.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').strip()
            normalized_digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
            output.setdefault(digest, dict(date=date, commit=commit, format=form,
                                          normalized_sha256=normalized_digest))
    return output


def checked_in():
    tree = ast.parse((ROOT / 'scripts/ees_asset_guard.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                target.id == 'WORK_TOOL_SOURCE_HISTORY' for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('WORK_TOOL_SOURCE_HISTORY is missing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    history = sources(args.ref)
    if args.check:
        if history != checked_in():
            raise ValueError('Git/formatter source hashes differ from the shipped allowlist.')
        print(f'Work Tool source history: {len(history)} exact forms and EOL/edge-space hashes verified with Black {FORMATTER}.')
    else:
        print('WORK_TOOL_SOURCE_HISTORY = ' + pprint.pformat(history, sort_dicts=False, width=110))


if __name__ == '__main__':
    main()
