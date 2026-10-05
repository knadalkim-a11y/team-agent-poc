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


def arrange_legacy_catalog(service):
    """Explicit test-only historical snapshot, never a product initializer.

    Preserve its version/revision just as importing a historical database does;
    publish_fixture_definition separately models a subsequent publication.
    """
    definition = legacy_definition()
    raw = json.dumps(definition, ensure_ascii=False, separators=(",", ":"))
    with service._db(write=True) as db:
        db.execute("UPDATE catalog SET published=?,draft=?,revision=0,validated=NULL WHERE id=1", (raw, raw))
        service._init_authoring(db)
    return definition


def load_workflow_examples(package_name):
    """Load explicit historical definitions for contract regression, never registration."""
    import importlib.util
    name = package_name + ".ees_workflow_examples"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "fixtures/ees_workflow_examples.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def legacy_definition():
    """Fresh historical content for explicit regression fixtures only."""
    definition = json.loads((Path(__file__).parent / "fixtures/workflow_seed.json").read_text(encoding="utf-8"))
    policy = Path(__file__).resolve().parents[1] / "agent-pack/skills/ees-work-demo/scripts/workflow_policy.json"
    definition["skills"] = {"common": json.loads(policy.read_text(encoding="utf-8")), **definition["skills"]}
    return definition


def historical_facade(package_name):
    """Pinned b41e239 facade for retired writer regression fixtures.

    This is intentionally a hybrid test arrangement: the old writer facade
    and authoring mixin are fixed; relative validators/Native adapters are current.
    It is never shipped and is not evidence of an old complete product. The
    load_legacy_workflow helper still loads the actual ees.10 wheel for Restore.
    """
    import importlib.util
    path = Path(__file__).parent / "fixtures/legacy_workflow_b41e239.py"
    expected = "3080e5767ce0d767bb6f6789fe25bbfff959bfbb107b3d45ad3b897a73ab77a5"
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise AssertionError("Historical writer fixture differs from b41e239")
    name = package_name + "._historical_workflow_b41e239"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        authoring_path = path.with_name("legacy_authoring_b41e239.py")
        if hashlib.sha256(authoring_path.read_bytes()).hexdigest() != "0ea0bd1229c8d751ac1b2c67c8128b08fca27ba5bb34439312e99c871ee2d55a":
            raise AssertionError("Historical authoring fixture differs from b41e239")
        authoring_name = package_name + "._historical_authoring_b41e239"
        authoring_spec = importlib.util.spec_from_file_location(authoring_name, authoring_path)
        authoring = importlib.util.module_from_spec(authoring_spec)
        sys.modules[authoring_name] = authoring
        authoring_spec.loader.exec_module(authoring)
        # Current Native adapters and historical writers share only the error
        # type. Production classes never inherit or import these old writers.
        authoring.WorkflowError = module.WorkflowError
        module.WorkflowService.__bases__ = (authoring.AuthoringMixin,)
    return sys.modules[name]
