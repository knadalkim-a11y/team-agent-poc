"""Integrated UI contract entry for Python discovery.

Replaces the retired C/V4 renderer/controller interfaces. These execute the
current production JavaScript via the shared unit fixtures, not a Native app.
Old test-ID decisions and preserved protections are in ees_delivery_baseline.json.
Real browser layout and storage gates are separate required CI jobs.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IntegratedPanelTests(unittest.TestCase):
    def test_typed_draft_authoring_and_result_contracts(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Required Node contract runtime is unavailable")
        for filename in ['test_ees_v4_drafts.cjs', 'test_ees_work_authoring_ui.cjs', 'test_ees_execution_ui.cjs']:
            with self.subTest(script=filename):
                result = subprocess.run([node, "--test", "--test-reporter=tap", str(ROOT / "tests" / filename)],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                count = re.search(r"# pass (\d+)", output)
                self.assertIsNotNone(count, output)
                self.assertGreater(int(count.group(1)), 0, output)
                self.assertRegex(output, r"# fail 0(?:\n|$)")
                self.assertRegex(output, r"# skipped 0(?:\n|$)")
