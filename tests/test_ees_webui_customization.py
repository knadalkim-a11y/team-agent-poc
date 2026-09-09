"""App-only deployment tests; no Open WebUI application or dependencies imported."""

import base64
import copy
import csv
import hashlib
import importlib.machinery
import importlib.metadata
import io
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import ees_webui_customization as custom

release = custom.releases
branding = custom.branding
COMMIT = "a" * 40
OWNER = {"pid": 321, "executable": "registered-python", "created_at": "123.45"}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def make_wheel(extra=None, replacement=None):
    members = {
        branding.TARGET_INFO + "METADATA": ("Metadata-Version: 2.1\nName: open-webui\nVersion: " + branding.VERSION +
                                               "\nRequires-Dist: example==1.0\n").encode(),
        branding.TARGET_INFO + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        branding.TARGET_INFO + "licenses/LICENSE": b"synthetic license\n",
        "open_webui/__init__.py": b"raise RuntimeError('never import this application')\n",
        "open_webui/env.py": b"# synthetic env module\n",
        "open_webui/main.py": b"# synthetic main module\n",
        "open_webui/frontend/index.html": b"<title>EES Assistant</title>\n",
        branding.TARGET_APP + "version.json": json.dumps({"version": branding.VERSION}).encode(),
        branding.TARGET_APP + "immutable/chunks/test.js": b"const title = 'EES Assistant';\n",
    }
    members.update(extra or {})
    members.update(replacement or {})
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, content in members.items():
        writer.writerow([name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode(), str(len(content))])
    writer.writerow([custom.RECORD, "", ""])
    members[custom.RECORD] = record.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as wheel:
        for name, content in members.items():
            wheel.writestr(name, content)
    return output.getvalue()


class CustomizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("state", "original", "data", "cwd"):
            (self.root / name).mkdir()
        package = self.root / "original" / "open_webui"
        package.mkdir()
        self.python = self.root / "original" / "python.exe"
        self.python.write_bytes(b"preserved interpreter")
        (package / "__init__.py").write_bytes(b"preserved original package")
        (self.root / "original" / "example.py").write_bytes(b"preserved dependency")
        (self.root / "data" / "webui.db").write_bytes(b"preserved synthetic database")
        (self.root / "cwd" / ".webui_secret_key").write_bytes(b"preserved synthetic key")
        self.config = {"state_root": str(self.root / "state"), "source_prefix": str(self.root / "original"),
                       "source_python": str(self.python), "package_dir": str(package),
                       "data_dir": str(self.root / "data"), "cwd": str(self.root / "cwd")}
        self.env = {"DATA_DIR": self.config["data_dir"]}
        self.registry = {"schema_version": 1, "phase": "idle", "current": {"kind": "original", "python": str(self.python)},
                         "previous": {"kind": "release", "source_commit": "f" * 40}, "last_failure": {"historical": True}}
        self.saved = copy.deepcopy(self.registry)
        self.events = []
        self.bundle = self.root / ("EES-demo-" + COMMIT[:12] + ".zip")
        self.write_bundle()
        self.probe = mock.patch.object(release, "probe_python", return_value={"packages": {"open-webui": branding.UPSTREAM_VERSION, "example": "1.0"},
                                                                             "requires": ["example==1.0"],
                                                                             "app": {"package_dir": str(package), "metadata_root": str(package.parent)}})
        self.probe_mock = self.probe.start()
        self.addCleanup(self.probe.stop)

    def write_bundle(self, content=None, commit=COMMIT):
        content = content or make_wheel()
        built = {"schema_version": 1, "version": branding.VERSION, "upstream_version": branding.UPSTREAM_VERSION,
                 "source": {"filename": branding.SOURCE_FILENAME, "sha256": branding.SOURCE_SHA256},
                 "wheel": {"filename": branding.WHEEL_FILENAME, "size": len(content), "sha256": digest(content)}}
        members = {name: b"synthetic guide" for name in release.bundles.GUIDES}
        members.update({"agent-pack/test.md": b"synthetic asset", "BUNDLE-README.md": b"synthetic readme",
                        "branding/manifest.json": json.dumps(built).encode(), "branding/" + branding.WHEEL_FILENAME: content})
        manifest = {"schema_version": 1, "source_commit": commit, "source_dirty": False,
                    "source_url": release.bundles.REPOSITORY_URL + "/tree/" + commit, "branding": built,
                    "files": [{"path": name, "size": len(value), "sha256": digest(value)} for name, value in members.items()]}
        self.bundle = self.root / ("EES-demo-" + commit[:12] + ".zip")
        with zipfile.ZipFile(self.bundle, "w") as archive:
            for name, value in members.items():
                archive.writestr(name, value)
            archive.writestr("manifest.json", json.dumps(manifest).encode())

    def record(self, config, registry, event):
        self.events.append(event)
        self.saved = copy.deepcopy(registry)

    def apply(self, commit=COMMIT):
        return custom.apply(self.config, self.registry, self.bundle, commit, self.env, self.record, OWNER)

    def restore(self):
        return custom.restore(self.config, self.registry, self.record, OWNER)

    def tree(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    @property
    def program(self):
        return self.root / "state" / "program"

    def test_checkonly_reads_without_importing_or_writing(self):
        before = self.tree()
        result = custom.inspect_bundle(self.config, self.bundle, COMMIT, self.env)
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.events, [])
        self.probe_mock.assert_called_once_with(str(self.python), env=self.env)

    def test_apply_idempotence_first_restore_and_original_state_preserved(self):
        before = {name: value for name, value in self.tree().items() if not name.startswith("state/")}
        self.assertTrue(self.apply()["changed"])
        self.assertEqual(self.registry["schema_version"], 2)
        self.assertEqual(self.registry["last_failure"], {"historical": True})
        self.assertEqual(self.registry["previous"], {"kind": "release", "source_commit": "f" * 40})
        self.assertEqual(self.registry["customization"]["previous"], {"active": None})
        selected = self.registry["customization"]["active"]
        custom.validate_program(self.program, selected)
        events = list(self.events)
        self.assertFalse(self.apply()["changed"])
        self.assertEqual(self.events, events)
        self.assertTrue(self.restore()["original_program"])
        self.assertFalse(self.program.exists())
        self.assertFalse(self.restore()["changed"])
        after = {name: value for name, value in self.tree().items() if not name.startswith("state/")}
        self.assertEqual(before, after)
        self.assertFalse(any(path.name in {"venv", "dependencies.txt", "releases"} for path in (self.root / "state").iterdir()))

    def test_restore_returns_immediately_preceding_program_only_once(self):
        self.apply()
        first = copy.deepcopy(self.registry["customization"]["active"])
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"# next app\n"}), commit="b" * 40)
        self.apply("b" * 40)
        second = copy.deepcopy(self.registry["customization"]["active"])
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"# third app\n"}), commit="c" * 40)
        self.apply("c" * 40)
        self.assertEqual(self.registry["customization"]["previous"], {"active": second})
        result = self.restore()
        self.assertEqual(result["source_commit"], "b" * 40)
        self.assertEqual(self.registry["customization"]["active"], second)
        self.assertNotEqual(second, first)
        self.assertFalse(self.restore()["changed"])
        self.assertEqual([path.name for path in (self.root / "state").iterdir()], ["program"])

    def test_wheel_install_paths_hooks_metadata_frontend_and_record_rejected(self):
        variants = [make_wheel(extra={name: b"unexpected"}) for name in (
            "elsewhere.py", "open_webui-0.11.3+ees.1.data/scripts/start", "activate.pth",
            "open_webui/inject.pth", "open_webui/.env", "open_webui/__pycache__/cache.pyc", branding.SOURCE_APP + "old.js")]
        variants += [make_wheel(replacement={branding.TARGET_INFO + "WHEEL": value}) for value in (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-any\n",
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: cp311-win_amd64\n")]
        variants += [make_wheel(replacement={branding.TARGET_INFO + "METADATA": b"Name: open-webui\nVersion: 0.11.3\n"})]
        variants += [make_wheel(replacement={branding.TARGET_APP + "version.json": b'{"version":"0.11.3"}'})]
        for variant in variants:
            with self.subTest(sha=digest(variant)):
                self.write_bundle(variant)
                with self.assertRaises((custom.CustomizationError, release.ReleaseError)):
                    self.apply()
                self.assertEqual(self.registry["schema_version"], 1)
                self.assertFalse(self.program.exists())

    def test_identical_app_from_new_commit_restores_previous_commit(self):
        self.apply()
        self.write_bundle(commit="b" * 40)
        self.assertTrue(self.apply("b" * 40)["changed"])
        self.assertEqual(self.restore()["source_commit"], COMMIT)
        self.assertFalse(self.restore()["changed"])

    def test_original_app_and_metadata_must_match_registered_paths(self):
        for app in (None, {"package_dir": "elsewhere", "metadata_root": "elsewhere"},
                    {"package_dir": self.config["package_dir"], "metadata_root": "elsewhere"}):
            self.probe_mock.return_value["app"] = app
            with self.assertRaisesRegex(custom.CustomizationError, "location"):
                self.apply()
            self.assertFalse(self.program.exists())

    def test_readonly_applicability_checks_backup_and_unrecorded_staging(self):
        self.apply()
        stage = self.root / "state" / "program.staging"
        stage.mkdir()
        with self.assertRaisesRegex(custom.CustomizationError, "staging"):
            custom.check_applicability(self.config, self.registry, self.env)
        self.assertTrue(stage.is_dir())
        stage.rmdir()
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"next"}), commit="b" * 40)
        self.apply("b" * 40)
        previous = self.root / "state" / "program.previous" / "open_webui/main.py"
        previous.write_bytes(b"changed")
        before = self.tree()
        with self.assertRaises(custom.CustomizationError):
            custom.check_applicability(self.config, self.registry, self.env)
        self.assertEqual(self.tree(), before)

    def test_wrong_baseline_requirements_and_commit_do_not_write(self):
        for probe in ({"packages": {"open-webui": branding.VERSION}, "requires": ["example==1.0"]},
                      {"packages": {"open-webui": branding.UPSTREAM_VERSION}, "requires": ["example==2.0"]}):
            with self.subTest(probe=probe):
                self.probe_mock.return_value = probe
                with self.assertRaises(custom.CustomizationError):
                    self.apply()
                self.assertFalse(self.program.exists())
        with self.assertRaises(release.ReleaseError):
            self.apply("b" * 40)
        self.assertEqual(self.events, [])

    def test_data_path_interpreter_env_overlap_and_dotenv_fail_readonly(self):
        for changes, env in (({}, {}), ({"source_python": str(self.root / "missing")}, self.env),
                             ({"state_root": self.config["data_dir"]}, self.env),
                             ({}, dict(self.env, PYTHONPATH="unreviewed")), ({}, dict(self.env, WEB_CONCURRENCY="2"))):
            with self.subTest(changes=changes, env=env), self.assertRaises((custom.CustomizationError, custom.states.StateError)):
                custom.inspect_bundle(dict(self.config, **changes), self.bundle, COMMIT, env)
        path = self.root / "state" / ".env"
        path.write_bytes(b"secret placeholder")
        with self.assertRaisesRegex(custom.CustomizationError, "env"):
            self.apply()
        self.assertEqual(path.read_bytes(), b"secret placeholder")
        self.assertEqual(self.events, [])

    def test_missing_tampered_and_extra_active_files_block_apply_and_restore(self):
        self.apply()
        file = self.program / "open_webui/main.py"
        original = file.read_bytes()
        for action in (lambda: file.write_bytes(b"tampered"), file.unlink,
                       lambda: (self.program / "unexpected.txt").write_bytes(b"unknown")):
            action()
            for operation in (self.apply, self.restore):
                with self.assertRaises(custom.CustomizationError):
                    operation()
            file.write_bytes(original)
            (self.program / "unexpected.txt").unlink(missing_ok=True)
        custom.validate_program(self.program, self.registry["customization"]["active"])

    def test_backup_tampering_blocks_restore_without_changing_active(self):
        self.apply()
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"next"}), commit="b" * 40)
        self.apply("b" * 40)
        backup = self.root / "state" / "program.previous" / "open_webui/main.py"
        backup.write_bytes(b"unexpected changed backup")
        before = self.tree()
        with self.assertRaises(custom.CustomizationError):
            self.restore()
        self.assertEqual(before, self.tree())
        self.assertIsNone(self.registry["customization"]["pending"])

    def test_hardlinks_and_symlinks_are_not_applied_or_removed(self):
        self.apply()
        target = self.program / "open_webui/main.py"
        linked = self.root / "other"
        os.link(target, linked)
        with self.assertRaises(custom.states.StateError):
            self.restore()
        linked.unlink()
        with mock.patch.object(custom.states, "_safe", side_effect=custom.states.StateError("reparse point")):
            with self.assertRaises(custom.states.StateError):
                self.restore()
        custom.validate_program(self.program, self.registry["customization"]["active"])

    def test_interrupted_extract_is_pending_and_restore_discards_only_owned_stage(self):
        extract = custom._extract
        def interrupted(content, path):
            extract(content, path)
            (path / "open_webui/main.py").write_bytes(b"#")
            raise KeyboardInterrupt()
        with mock.patch.object(custom, "_extract", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.apply()
        self.assertEqual(self.saved["customization"]["pending"]["owner"], OWNER)
        self.assertFalse(self.program.exists())
        with self.assertRaisesRegex(custom.CustomizationError, "Restore"):
            self.apply()
        self.assertTrue(self.restore()["original_program"])
        self.assertEqual(list((self.root / "state").iterdir()), [])

    def test_all_apply_transition_failures_are_explicitly_restorable(self):
        for event in ("program_apply_started", "program_retire_previous", "program_move_active", "program_promote", "program_applied"):
            with self.subTest(event=event):
                # Start with a customized app so failures cover its preservation.
                if not self.registry.get("customization", {}).get("active"):
                    self.write_bundle()
                    self.apply()
                before = copy.deepcopy(self.registry["customization"]["active"])
                self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"next failed app"}), commit="b" * 40)
                record = self.record
                def interrupted(config, registry, current_event):
                    if current_event == event:
                        raise OSError("synthetic locked record")
                    record(config, registry, current_event)
                with mock.patch.object(self, "record", side_effect=interrupted), self.assertRaises(OSError):
                    self.apply("b" * 40)
                self.assertIsNotNone(self.registry["customization"]["pending"])
                self.restore()
                self.assertEqual(self.registry["customization"]["active"], before)
                custom.validate_program(self.program, before)

    def test_locked_directory_rename_preserves_previous_and_can_restore(self):
        self.apply()
        first = copy.deepcopy(self.registry["customization"]["active"])
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"new app"}), commit="b" * 40)
        original_rename = Path.rename
        def rename(path, target):
            if path == self.program:
                raise PermissionError("synthetic file lock")
            return original_rename(path, target)
        with mock.patch.object(Path, "rename", rename), self.assertRaises(PermissionError):
            self.apply("b" * 40)
        self.assertEqual(self.registry["customization"]["pending"]["stage"], "move_active")
        self.restore()
        self.assertEqual(self.registry["customization"]["active"], first)

    def test_interrupted_previous_retirement_preserves_intact_current_app(self):
        self.apply()
        self.write_bundle(commit="b" * 40)
        self.apply("b" * 40)
        self.write_bundle(commit="c" * 40)
        previous_dir = self.root / "state" / "program.previous"
        original_unlink = Path.unlink
        deleted = 0
        def unlink(path, *args, **kwargs):
            nonlocal deleted
            if previous_dir in path.parents:
                deleted += 1
                if deleted == 2:
                    raise KeyboardInterrupt()
            return original_unlink(path, *args, **kwargs)
        with mock.patch.object(Path, "unlink", unlink), self.assertRaises(KeyboardInterrupt):
            self.apply("c" * 40)
        self.assertEqual(self.restore()["source_commit"], "b" * 40)
        self.assertFalse(previous_dir.exists())
        self.assertFalse(self.restore()["changed"])

    def test_interrupted_restore_deletion_resumes_using_record_last(self):
        self.apply()
        original_unlink = Path.unlink
        deleted = 0
        def unlink(path, *args, **kwargs):
            nonlocal deleted
            if self.program in path.parents:
                deleted += 1
                if deleted == 2:
                    raise KeyboardInterrupt()
            return original_unlink(path, *args, **kwargs)
        with mock.patch.object(Path, "unlink", unlink), self.assertRaises(KeyboardInterrupt):
            self.restore()
        self.assertEqual(self.registry["customization"]["pending"]["action"], "restore")
        self.assertTrue((self.program / custom.RECORD).is_file())
        self.assertTrue(self.restore()["original_program"])
        self.assertFalse(self.program.exists())

    def test_final_record_failure_does_not_clear_pending_in_memory(self):
        self.apply()
        record = self.record
        def fail_complete(config, registry, event):
            if event == "program_restored":
                raise OSError("record unavailable")
            record(config, registry, event)
        with mock.patch.object(self, "record", side_effect=fail_complete), self.assertRaises(OSError):
            self.restore()
        self.assertIsNotNone(self.registry["customization"]["pending"])
        self.restore()
        self.assertIsNone(self.registry["customization"]["pending"])

    def test_legacy_or_malformed_record_is_rejected_before_mutation(self):
        for key, value in (("phase", "switching"), ("pending", {"kind": "release"}),
                           ("launch_uncertain", True), ("current", {"kind": "release", "python": str(self.python)})):
            previous = copy.deepcopy(self.registry)
            self.registry[key] = value
            with self.assertRaises(custom.CustomizationError):
                self.apply()
            self.registry = previous
        self.apply()
        value = copy.deepcopy(self.registry)
        value["customization"]["active"]["source_commit"] = "../escape"
        with self.assertRaises(custom.CustomizationError):
            custom.validate_registry(value)
        value = copy.deepcopy(self.registry)
        value["schema_version"] = 1
        with self.assertRaises(custom.CustomizationError):
            custom.validate_registry(value)

    def test_extracted_code_metadata_and_frontend_select_the_same_app(self):
        self.apply()
        spec = importlib.machinery.PathFinder.find_spec("open_webui", [str(self.program)])
        self.assertEqual(Path(spec.origin), self.program / "open_webui/__init__.py")
        distributions = list(importlib.metadata.distributions(path=[str(self.program)]))
        self.assertEqual(len(distributions), 1)
        self.assertEqual(distributions[0].metadata["Name"], "open-webui")
        self.assertEqual(distributions[0].version, branding.VERSION)
        self.assertEqual(Path(distributions[0].locate_file("")), self.program)
        self.assertEqual(json.loads((self.program / (branding.TARGET_APP + "version.json")).read_bytes())["version"], branding.VERSION)
        self.assertFalse((self.program / branding.SOURCE_APP).exists())


class RealBrandingWheelTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("EES_TEST_BRANDING_DIR"), "Real built wheel is supplied by the package CI job")
    def test_real_built_wheel_has_complete_purelib_app_metadata_and_frontend(self):
        root = Path(os.environ["EES_TEST_BRANDING_DIR"])
        content = (root / branding.WHEEL_FILENAME).read_bytes()
        manifest = json.loads((root / "manifest.json").read_bytes())
        release._wheel(content, manifest)
        layout = custom._wheel_layout(content)
        selection = {"source_commit": COMMIT, "wheel_sha256": digest(content),
                     "record_sha256": layout["record_sha256"], "webui_version": branding.VERSION}
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / "program"
            custom._extract(content, program)
            custom.validate_program(program, selection)
            spec = importlib.machinery.PathFinder.find_spec("open_webui", [str(program)])
            self.assertEqual(Path(spec.origin), program / "open_webui/__init__.py")
            distributions = list(importlib.metadata.distributions(path=[str(program)]))
            self.assertEqual(len(distributions), 1)
            self.assertEqual(distributions[0].version, branding.VERSION)
            self.assertEqual(Path(distributions[0].locate_file("")), program)
            self.assertEqual(json.loads((program / (branding.TARGET_APP + "version.json")).read_bytes())["version"], branding.VERSION)
            self.assertIn(b"EES Assistant", (program / "open_webui/frontend/index.html").read_bytes())
            # v0.11.3 config.py rewrites package/static from frontend/static
            # at startup. Reproduce those file operations without app imports.
            static = program / "open_webui/static"
            frontend_static = program / "open_webui/frontend/static"
            if static.exists():
                for item in static.iterdir():
                    if item.is_file() or item.is_symlink():
                        item.unlink()
            for source in frontend_static.glob("**/*"):
                if source.is_file():
                    target = static / source.relative_to(frontend_static)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            for name in ("favicon.png", "splash.png", "loader.js"):
                if (frontend_static / name).exists():
                    shutil.copyfile(frontend_static / name, static / name)
            custom.validate_program(program, selection)



if __name__ == "__main__":
    unittest.main()
