"""Arrange published synthetic procedures for runtime-only tests.

This deliberately is not an authoring API or evidence of authorized publishing.
Scoped authoring tests exercise save/validate/publish themselves. The helper
keeps older runtime fixtures usable after whole-catalog authoring is closed.
It must only receive each test's temporary WorkflowService database.
"""

from copy import deepcopy
import json
import hashlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from zipfile import ZipFile


def publish_fixture_definition(service, definition):
    prepared = deepcopy(definition)
    for key in ("available_tools", "available_skills", "assets_available"):
        prepared.pop(key, None)
    for skill in prepared.get("skills", {}).values():
        if skill.get("source") == "open_webui":
            skill["body"] = ""
    with service._db(write=True) as db:
        row = db.execute("SELECT published,revision FROM catalog WHERE id=1").fetchone()
        prepared["version"] = json.loads(row[0])["version"] + 1
        raw = json.dumps(prepared, ensure_ascii=False, separators=(",", ":"))
        db.execute("UPDATE catalog SET published=?,draft=?,revision=?,validated=NULL WHERE id=1",
                   (raw, raw, row[1] + 1))
    return prepared


def load_legacy_workflow(test):
    """Load real, pinned ees.10 code; never substitute a simulated old writer."""
    path = os.environ.get("EES_TEST_LEGACY_WORKFLOW_WHEEL")
    if not path or not Path(path).is_file():
        message = "EES_TEST_LEGACY_WORKFLOW_WHEEL must identify the supported ees.10 wheel."
        if os.environ.get("EES_REQUIRE_LEGACY_WORKFLOW"):
            test.fail(message)
        raise unittest.SkipTest(message + " Required in the release gate.")
    expected = "ad08078b9db2cf484a6af614b95bd4cf7c9910070d2505bc271065278d079ddd"
    test.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), expected,
                     "Restore must execute the supported real ees.10 artifact")
    temporary = tempfile.TemporaryDirectory(prefix="ees-real-old-wheel-")
    test.addCleanup(temporary.cleanup)
    source = Path(temporary.name)
    with ZipFile(path) as archive:
        for name in ("ees_workflow.py", "ees_workflow_definition.py", "ees_workflow_view.py",
                     "workflow_seed.json", "workflow_policy.json"):
            matches = [item for item in archive.namelist() if item.endswith("/" + name)]
            test.assertEqual(len(matches), 1, (name, matches))
            (source / name).write_bytes(archive.read(matches[0]))
    package = ModuleType("ees_restore_" + source.name.replace("-", "_"))
    package.__path__ = [str(source)]
    sys.modules[package.__name__] = package
    def cleanup_modules():
        for key in tuple(sys.modules):
            if key == package.__name__ or key.startswith(package.__name__ + "."):
                sys.modules.pop(key, None)
    test.addCleanup(cleanup_modules)
    return importlib.import_module(package.__name__ + ".ees_workflow")
