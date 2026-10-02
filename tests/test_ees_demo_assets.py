"""Retired demo registration and retained asset/privacy invariants.

The former ApplyDemo creation/merge/partial-registration cases are superseded:
registration must now refuse before *any* transport or journal write. Conditional
write/backup/concurrency/ACL coverage lives in native asset and guard tests.
"""
import copy
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import sys
from types import SimpleNamespace
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "ees_demo_assets.py"
spec = importlib.util.spec_from_file_location("ees_demo_assets", MODULE)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class RetiredRegistrationTests(unittest.TestCase):
    def test_current_manifest_has_no_automatic_tools_models_or_skills(self):
        manifest = assets.load_manifest(MODULE.parents[1])
        self.assertEqual(manifest["registration"], "retired")
        for name in ("tools", "models", "optional_existing_tools", "skills"):
            self.assertFalse(manifest.get(name))
        self.assertIn("ees_workflow", manifest["preserve"])

    def test_new_restart_repeat_and_old_journal_never_recreate_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            journal = state / assets.STATE_FILE
            baseline = {"schema": 1, "pack": assets.PACK, "assets": {
                "model:ees_demo_ems": {"status": "pending", "before": {"personal": "keep"}}}}
            journal.write_text(json.dumps(baseline), encoding="utf-8")
            before = journal.read_bytes()
            client = Mock()
            for source in ("a" * 40, "b" * 40, "a" * 40):
                with self.assertRaises(assets.DemoAssetsError) as caught:
                    assets.apply_assets(client, MODULE.parents[1], state, "existing-base-model", source)
                self.assertEqual(caught.exception.code, "demo_registration_retired")
                self.assertEqual(caught.exception.changed, 0)
                self.assertFalse(caught.exception.pending)
            client.request.assert_not_called()
            self.assertEqual(journal.read_bytes(), before)

    def test_historical_manifest_cannot_reactivate_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent-pack").mkdir()
            (root / "agent-pack/ees-demo.json").write_text(json.dumps({
                "version": "0.2.14", "tools": [{"id": "ees_specialists"}],
                "models": [{"id": "ees_demo_ems"}]}), encoding="utf-8")
            with self.assertRaisesRegex(assets.DemoAssetsError, "demo_registration_retired"):
                assets.load_manifest(root)

    def test_backup_payload_preserves_user_metadata_grants_and_base_connection(self):
        model = {"id": "existing", "user_id": "owner", "name": "Personal model",
                 "base_model_id": "actual-native-connection", "is_active": True,
                 "meta": {"toolIds": ["jira_real"], "skillIds": ["private-skill"],
                          "custom": {"keep": True}}, "params": {"system": "User policy", "temperature": 0.2},
                 "access_grants": [{"principal_type": "user", "principal_id": "owner", "permission": "write"}]}
        before = copy.deepcopy(model)
        payload = assets._payload(model, "model")
        self.assertEqual(payload["base_model_id"], model["base_model_id"])
        self.assertEqual(payload["meta"], model["meta"])
        self.assertEqual(payload["params"], model["params"])
        self.assertEqual(payload["access_grants"], model["access_grants"])
        self.assertEqual(model, before)

    def test_asset_journal_rejects_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "personal.json"
            target.write_text("private fixture", encoding="utf-8")
            linked = root / assets.STATE_FILE
            linked.symlink_to(target)
            with self.assertRaisesRegex(assets.DemoAssetsError, "unsafe_journal_path"):
                assets._state_path(root)
            self.assertEqual(target.read_text(encoding="utf-8"), "private fixture")


class RetirementOperatorTests(unittest.TestCase):
    def test_preview_is_private_read_only_and_requires_exact_plan_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "private-plan.json"
            client = Mock()
            preview = {"eligible": True, "blocked_reasons": [], "kind": "model", "id": "ees_demo_ems",
                       "current_sha256": "a" * 64, "expected_token": "b" * 64}
            client.request.side_effect = [{"retirement": 1}, preview]
            class OperatorError(ValueError):
                pass
            operator = SimpleNamespace(DemoError=OperatorError,
                upgrade=SimpleNamespace(manager=SimpleNamespace(states=SimpleNamespace(load_config=Mock(return_value={})))),
                connection=Mock(return_value=(None, {"url": "http://127.0.0.1:8080", "ca_file": None})),
                load_token=Mock(return_value=("PRIVATE_SYNTHETIC_TOKEN", False)), WebUIClient=Mock(return_value=client))
            output, error = io.StringIO(), io.StringIO()
            with patch.dict(sys.modules, {"ees_apply_demo": operator}), redirect_stdout(output), redirect_stderr(error):
                result = assets.retirement_main(["preview", "--config", "synthetic.json", "--kind", "model",
                    "--id", "ees_demo_ems", "--baseline-sha256", "a" * 64, "--plan", str(plan)])
                self.assertEqual(result, 0, error.getvalue())
                self.assertEqual([call.args[1] for call in client.request.call_args_list],
                    [assets.ASSET_API + "/capabilities", assets.ASSET_API + "/retirement/preview"])
                self.assertNotIn("PRIVATE_SYNTHETIC_TOKEN", plan.read_text(encoding="utf-8") + output.getvalue())
                if sys.platform != "win32":
                    self.assertEqual(plan.stat().st_mode & 0o777, 0o600)
                client.request.reset_mock()
                client.request.side_effect = [{"retirement": 1}]
                self.assertEqual(assets.retirement_main(["apply", "--config", "synthetic.json", "--plan", str(plan),
                    "--approve-plan-sha256", "0" * 64]), 1)
                self.assertEqual(client.request.call_count, 1)
                self.assertIn("retirement_plan_changed", error.getvalue())
                body = json.loads(plan.read_text(encoding="utf-8"))
                client.request.reset_mock()
                client.request.side_effect = [{"retirement": 1}, {"status": "retired", "request_id": "retire-" + assets._hash(body)}]
                self.assertEqual(assets.retirement_main(["apply", "--config", "synthetic.json", "--plan", str(plan),
                    "--approve-plan-sha256", assets._hash(body)]), 0)
                submitted = client.request.call_args.args
                self.assertEqual(submitted[1], assets.ASSET_API + "/retirement/apply")
                self.assertEqual(submitted[2]["expected_token"], preview["expected_token"])
                self.assertEqual(submitted[2]["baseline_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
