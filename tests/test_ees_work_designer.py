"""Scoped production authoring contracts using a synthetic DOM, not browser E2E.

The Node suite shares one harness for the pre-existing editor preservation checks
and the system/P authorization, CAS, response-race and Native-reference checks.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node is required for authoring contracts.")
class WorkDesignerTests(unittest.TestCase):
    def test_scoped_authoring_state_and_form_contracts(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(ROOT / "tests/test_ees_work_authoring_ui.cjs")],
            capture_output=True, encoding="utf-8", timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
