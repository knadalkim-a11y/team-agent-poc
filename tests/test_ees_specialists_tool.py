"""Specialist presets and recursion/budget machinery are retired; Native model ACL and transport remain in model service tests.

This is removal/re-registration coverage, not a claim that the old demo ran.
Native execution, model ACL and scoped-state protections have independent tests.
"""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RETIRED_SOURCE = 'agent-pack/skills/cross-system-analysis/scripts/specialists_tool.py'
IDENTIFIER = 'ees_specialists'
spec = importlib.util.spec_from_file_location("retired_bundle_ees_specialists", ROOT / "scripts/build_demo_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class RetiredSpecialistTests(unittest.TestCase):
    def test_retired_implementation_cannot_be_imported_or_shipped(self):
        self.assertFalse((ROOT / RETIRED_SOURCE).exists(), RETIRED_SOURCE)
        self.assertFalse(bundle.included_source(RETIRED_SOURCE))
        self.assertNotIn(RETIRED_SOURCE, bundle.source_files(ROOT))

    def test_default_registration_cannot_recreate_retired_tool_or_preset(self):
        manifest = json.loads((ROOT / "agent-pack/ees-demo.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["registration"], "retired")
        for field in ("tools", "models", "skills", "optional_existing_tools"):
            self.assertFalse(manifest.get(field), field)
        self.assertIn("Native model connections", manifest["preserve"])
        self.assertIn("ees_workflow", manifest["preserve"])

    def test_real_connectors_and_shared_runtime_remain_available(self):
        for family in ("github", "jira", "confluence"):
            path = "agent-pack/skills/" + family + "-read/scripts/" + family + "_tool.py"
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertTrue(bundle.included_source(path), path)
        common = ROOT / "agent-pack/skills/ees-work-demo/scripts"
        for name in ("ees_workflow.py", "ees_workflow_model.py", "ees_workflow_native.py"):
            self.assertTrue((common / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
