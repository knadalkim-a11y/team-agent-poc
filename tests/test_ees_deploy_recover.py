"""Synthetic cache recovery; no live server, package installation, or network."""

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import ees_deploy_recover as recovery


COMMIT = "a" * 40
FILENAME = "antlr4_python3_runtime-4.9.3-py3-none-any.whl"


def wheel_bytes(name="antlr4-python3-runtime", version="4.9.3", tag="py3-none-any", corrupt=False):
    info = recovery.INFO
    members = {
        info + "METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
        info + "WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n".encode(),
        "antlr4/__init__.py": b"raise RuntimeError('Cached packages must never be imported')\n",
    }
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for path, content in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow([path, "sha256=" + digest, str(len(content))])
    writer.writerow([info + "RECORD", "", ""])
    members[info + "RECORD"] = record.getvalue().encode()
    if corrupt:
        members["antlr4/__init__.py"] += b"# changed after RECORD\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in members.items():
            archive.writestr(path, content)
    return output.getvalue()


class CachedWheelRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config_path = self.root / "config.json"
        self.config = {
            "state_root": str(self.root), "releases_dir": str(self.root / "releases"),
            "source_python": str(self.root / "source-python.exe"), "uv_exe": str(self.root / "uv.exe"),
        }
        self.config_path.write_text(json.dumps(self.config))
        self.registry = {
            "schema_version": 1, "phase": "idle", "previous": None,
            "current": {"kind": "original", "source_commit": None, "python": self.config["source_python"]},
            "process": {"pid": 123, "executable": self.config["source_python"]},
        }
        self.write_registry()
        self.config_before = self.config_path.read_bytes()
        self.registry_before = recovery.manager.registry_path(self.config).read_bytes()
        self.original = self.root / "source-python.exe"
        self.original.write_bytes(b"Existing program stays unchanged")
        self.database = self.root / "webui.db"
        self.database.write_bytes(b"Existing users, conversations and memory")
        self.env = {"PATH": "synthetic-path", "WEBUI_SECRET_KEY": "synthetic-secret", "DATA_DIR": str(self.root)}
        self.target = self.root / "releases" / COMMIT
        (self.target / "bundle").mkdir(parents=True)
        self.manifest = {"source_commit": COMMIT, "source_dirty": False, "schema_version": 1}
        (self.target / "bundle" / "manifest.json").write_text(json.dumps(self.manifest))
        (self.target / "prepare.log").write_bytes(b"Original antlr no usable wheels failure\n")
        self.bundle = self.root / ("EES-demo-" + COMMIT[:12] + ".zip")
        self.bundle.write_bytes(b"Selected artifact checked by existing validator")
        self.cache = self.root / "cache"
        self.cached = self.cache / "sdists-v9" / "index" / "synthetic-build" / FILENAME
        self.cached.parent.mkdir(parents=True)
        self.cached.write_bytes(wheel_bytes())
        self.metadata = {
            "webui_version": "0.11.3+ees.1",
            "bundle_sha256": hashlib.sha256(self.bundle.read_bytes()).hexdigest(),
        }
        patches = {
            "load": mock.patch.object(recovery.states, "load_config", return_value=self.config),
            "env": mock.patch.object(recovery.states, "runtime_environment", return_value=self.env),
            "validate_bundle": mock.patch.object(recovery.releases, "validate_bundle", return_value=self.manifest),
            "probe": mock.patch.object(recovery.releases, "probe_python", return_value={
                "packages": {"antlr4-python3-runtime": "4.9.3", "open-webui": "0.11.3"}}),
            "cache": mock.patch.object(recovery.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, stdout=str(self.cache) + "\n", stderr="")),
            "prepare": mock.patch.object(recovery.releases, "prepare_release", side_effect=self.prepare),
            "validate_prepared": mock.patch.object(recovery.releases, "validate_prepared", return_value=self.metadata),
        }
        self.mocks = {}
        for name, patcher in patches.items():
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def write_registry(self):
        recovery.manager.write_json(recovery.manager.registry_path(self.config), self.registry)

    def prepare(self, bundle, commit, target, source_python, uv_exe, *, wheelhouse, env):
        self.assertTrue((self.root / "deployment.lock").is_file())
        self.assertFalse(target.exists())
        self.assertEqual((bundle, commit, target, source_python, uv_exe),
                         (self.bundle, COMMIT, self.target, self.config["source_python"], self.config["uv_exe"]))
        self.assertEqual(env, self.env)
        self.assertEqual((wheelhouse / FILENAME).read_bytes(), self.cached.read_bytes())
        target.mkdir()
        (target / "release.json").write_text(json.dumps(self.metadata))
        return self.metadata

    def recover(self):
        return recovery.recover(self.config_path, self.bundle, COMMIT)

    def preserved(self):
        return list((self.root / "releases").glob(COMMIT + ".failed-*"))

    def assert_untouched(self):
        self.assertEqual(self.original.read_bytes(), b"Existing program stays unchanged")
        self.assertEqual(self.database.read_bytes(), b"Existing users, conversations and memory")
        self.assertEqual(self.config_path.read_bytes(), self.config_before)
        self.assertEqual(recovery.manager.registry_path(self.config).read_bytes(), self.registry_before)
        self.assertFalse((self.root / "deployment.lock").exists())

    def test_recovery_preserves_failure_and_installs_only_into_new_candidate(self):
        result = self.recover()
        self.assertEqual(result, {"prepared": True, "source_commit": COMMIT,
                                  "server_changed": False, "webui_version": "0.11.3+ees.1"})
        self.assertEqual(len(self.preserved()), 1)
        self.assertEqual((self.preserved()[0] / "prepare.log").read_bytes(),
                         b"Original antlr no usable wheels failure\n")
        self.assert_untouched()
        args, kwargs = self.mocks["cache"].call_args
        self.assertEqual(args[0], [self.config["uv_exe"], "--no-config", "--offline", "cache", "dir"])
        self.assertNotIn("WEBUI_SECRET_KEY", kwargs["env"])
        self.mocks["prepare"].assert_called_once()

    def test_wrong_package_version_tags_and_record_fail_before_move(self):
        for changes in ({"name": "different-package"}, {"version": "4.9.2"},
                        {"tag": "cp311-cp311-win_amd64"}, {"corrupt": True}):
            with self.subTest(changes=changes):
                self.cached.write_bytes(wheel_bytes(**changes))
                with self.assertRaises(recovery.releases.ReleaseError):
                    self.recover()
                self.assertTrue((self.target / "prepare.log").is_file())
                self.assertEqual(self.preserved(), [])
                self.mocks["prepare"].assert_not_called()
        self.assert_untouched()

    def test_multiple_cached_wheels_are_not_chosen_arbitrarily(self):
        duplicate = self.cached.parent.parent / "another-build" / FILENAME
        duplicate.parent.mkdir()
        duplicate.write_bytes(self.cached.read_bytes())
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "exactly one"):
            self.recover()
        self.assertEqual(self.preserved(), [])
        self.assert_untouched()

    def test_existing_wheel_conflict_does_not_overwrite_or_move(self):
        directory = self.root / "wheelhouse-antlr-4.9.3"
        directory.mkdir()
        (directory / FILENAME).write_bytes(b"Different preexisting wheel")
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "differs"):
            self.recover()
        self.assertEqual((directory / FILENAME).read_bytes(), b"Different preexisting wheel")
        self.assertEqual(self.preserved(), [])
        self.assert_untouched()

    def test_same_existing_wheel_is_reused(self):
        directory = self.root / "wheelhouse-antlr-4.9.3"
        directory.mkdir()
        (directory / FILENAME).write_bytes(self.cached.read_bytes())
        self.assertTrue(self.recover()["prepared"])
        self.assert_untouched()

    def test_unrelated_wheels_are_not_supplied_to_offline_install(self):
        directory = self.root / "wheelhouse-antlr-4.9.3"
        directory.mkdir()
        unrelated = directory / "unrelated-package.whl"
        unrelated.write_bytes(b"Operator-owned file")
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "unrelated files"):
            self.recover()
        self.assertEqual(unrelated.read_bytes(), b"Operator-owned file")
        self.assertEqual(self.preserved(), [])
        self.mocks["prepare"].assert_not_called()
        self.assert_untouched()

    def test_active_or_uncertain_deployment_is_never_renamed(self):
        original_registry = json.loads(json.dumps(self.registry))
        cases = [
            {"phase": "switching"}, {"launch_uncertain": True},
            {"previous": {"kind": "release", "source_commit": COMMIT}},
            {"pending": {"kind": "release", "source_commit": COMMIT}},
            {"current": {"kind": "release", "source_commit": COMMIT}},
            {"process": {"executable": str(self.target / "venv" / "Scripts" / "python.exe")}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.registry = dict(original_registry, **changes)
                self.write_registry()
                with self.assertRaises(recovery.manager.DeploymentError):
                    self.recover()
                self.assertEqual(self.preserved(), [])
                self.mocks["prepare"].assert_not_called()
        self.registry = original_registry
        self.write_registry()
        self.assert_untouched()

    def test_existing_operation_lock_blocks_recovery(self):
        with recovery.manager.locked(self.config):
            with self.assertRaisesRegex(recovery.manager.DeploymentError, "lock exists"):
                self.recover()
        self.assertEqual(self.preserved(), [])
        self.assert_untouched()

    def test_manifest_mismatch_and_wrong_source_inventory_preserve_candidate(self):
        manifest_path = self.target / "bundle" / "manifest.json"
        manifest_path.write_text(json.dumps(dict(self.manifest, source_commit="b" * 40)))
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "manifest differs"):
            self.recover()
        manifest_path.write_text(json.dumps(self.manifest))
        self.mocks["probe"].return_value = {"packages": {"antlr4-python3-runtime": "4.13.2"}}
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "source runtime"):
            self.recover()
        self.assertEqual(self.preserved(), [])
        self.mocks["prepare"].assert_not_called()
        self.assert_untouched()

    def test_links_at_candidate_manifest_cache_and_wheelhouse_are_rejected(self):
        paths = [self.target, self.target / "bundle" / "manifest.json", self.cached,
                 self.root / "wheelhouse-antlr-4.9.3"]
        for index, path in enumerate(paths):
            with self.subTest(path=path.name):
                moved = self.root / ("link-target-" + str(index))
                existed = path.exists()
                if existed:
                    path.rename(moved)
                else:
                    moved.mkdir()
                try:
                    path.symlink_to(moved, target_is_directory=moved.is_dir())
                except OSError:
                    if existed:
                        moved.rename(path)
                    self.skipTest("Symlink creation is unavailable on this host")
                try:
                    with self.assertRaises(recovery.states.StateError):
                        self.recover()
                    self.assertEqual(self.preserved(), [])
                finally:
                    path.unlink()
                    if existed:
                        moved.rename(path)
        self.mocks["prepare"].assert_not_called()
        self.assert_untouched()

    def test_failed_retry_keeps_original_failure_and_original_runtime(self):
        def failed(*args, **kwargs):
            self.target.mkdir()
            (self.target / "prepare.log").write_bytes(b"Another dependency is missing")
            raise recovery.releases.ReleaseError("Offline preparation failed")
        self.mocks["prepare"].side_effect = failed
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "Offline preparation failed"):
            self.recover()
        self.assertEqual(len(self.preserved()), 1)
        self.assertEqual((self.target / "prepare.log").read_bytes(), b"Another dependency is missing")
        self.assert_untouched()

    def test_already_prepared_rechecks_without_duplicate_rename(self):
        self.recover()
        second = self.recover()
        self.assertTrue(second["prepared"])
        self.assertEqual(len(self.preserved()), 1)
        self.mocks["prepare"].assert_called_once()
        self.mocks["cache"].assert_called_once()
        self.mocks["validate_prepared"].assert_called_once()
        self.assert_untouched()

    def test_prepared_artifact_mismatch_is_not_replaced(self):
        self.recover()
        self.metadata["bundle_sha256"] = "b" * 64
        with self.assertRaisesRegex(recovery.releases.ReleaseError, "different artifact"):
            self.recover()
        self.assertEqual(len(self.preserved()), 1)
        self.mocks["prepare"].assert_called_once()
        self.assert_untouched()


if __name__ == "__main__":
    unittest.main()
