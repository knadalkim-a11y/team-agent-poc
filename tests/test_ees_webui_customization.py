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


def make_wheel(extra=None, replacement=None, *, version=branding.VERSION, missing=()):
    info = f"open_webui-{version}.dist-info/"
    app = f"open_webui/frontend/{branding.PROGRAM_FRONTENDS[version]}/"
    record_name = info + "RECORD"
    members = {
        info + "METADATA": ("Metadata-Version: 2.1\nName: open-webui\nVersion: " + version +
                                               "\nRequires-Dist: example==1.0\n").encode(),
        info + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        info + "licenses/LICENSE": b"synthetic license\n",
        "open_webui/__init__.py": b"raise RuntimeError('never import this application')\n",
        "open_webui/env.py": b"# synthetic env module\n",
        "open_webui/main.py": b"# synthetic main module\n",
        "open_webui/frontend/index.html": b"<title>EES Portal</title>\n",
        app + "version.json": json.dumps({"version": version}).encode(),
        app + "immutable/chunks/test.js": b"const title = 'EES Portal';\n",
    }
    if version == "0.11.3+ees.3":
        members.update({app + name: b"synthetic checked theme asset\n" for name in branding.THEME_FILES})
    members.update(extra or {})
    members.update(replacement or {})
    for name in missing:
        members.pop(name)
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, content in members.items():
        writer.writerow([name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode(), str(len(content))])
    writer.writerow([record_name, "", ""])
    members[record_name] = record.getvalue().encode()
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

    def install_legacy_program(self, *, replacement=None, extra=None, version="0.11.3+ees.1"):
        content = make_wheel(version=version, replacement=replacement, extra=extra)
        with zipfile.ZipFile(io.BytesIO(content)) as wheel:
            wheel.extractall(self.program)
            selection = {"source_commit": "e" * 40, "wheel_sha256": digest(content),
                         "record_sha256": digest(wheel.read(f"open_webui-{version}.dist-info/RECORD")),
                         "webui_version": version}
        self.registry["schema_version"] = 2
        self.registry["customization"] = {"active": selection, "previous": {"active": None}, "pending": None}
        self.registry["runtime_ca_sha256"] = "d" * 64
        return selection

    def interrupt_promotion(self, commit=COMMIT, *, manually_promote=True):
        staged = self.root / "state" / "program.staging"
        original_rename = Path.rename
        def rename(path, target):
            if path == staged:
                raise PermissionError(13, "synthetic promotion lock")
            return original_rename(path, target)
        with mock.patch.object(Path, "rename", rename), self.assertRaises(PermissionError):
            self.apply(commit)
        self.assertEqual(self.saved["customization"]["pending"]["stage"], "promote")
        if manually_promote:
            staged.rename(self.program)
        return copy.deepcopy(self.registry["customization"]["pending"]["target"])

    def resume(self, commit=COMMIT, *, owner=None):
        return custom.resume_apply(self.config, self.registry, self.bundle, commit, self.env,
                                   self.record, owner or dict(OWNER, pid=654, created_at="456.78"))

    def assert_resume_rejected_unchanged(self, commit=COMMIT):
        files, registry, saved, events = self.tree(), copy.deepcopy(self.registry), copy.deepcopy(self.saved), list(self.events)
        with self.assertRaises((custom.CustomizationError, release.ReleaseError, custom.states.StateError)):
            self.resume(commit)
        self.assertEqual(self.tree(), files)
        self.assertEqual(self.registry, registry)
        self.assertEqual(self.saved, saved)
        self.assertEqual(self.events, events)

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

    def test_installed_legacy_apply_portal_restore_preserves_original_runtime_and_ca(self):
        legacy = self.install_legacy_program()
        files = self.tree()
        custom.validate_registry(self.registry)
        custom.validate_program(self.program, legacy)
        self.assertEqual(custom.inspect_bundle(self.config, self.bundle, COMMIT, self.env)["webui_version"], branding.VERSION)
        self.assertTrue(self.apply()["changed"])
        self.assertEqual(self.registry["customization"]["active"]["webui_version"], branding.VERSION)
        self.assertEqual(self.registry["customization"]["previous"]["active"], legacy)
        self.assertFalse((self.program / "open_webui/frontend/_ees1").exists())
        self.assertEqual(self.restore()["source_commit"], legacy["source_commit"])
        custom.validate_program(self.program, legacy)
        self.assertEqual(self.tree(), files)
        self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)
        self.assertFalse(self.restore()["changed"])

    def test_ees2_before_theme_pending_can_resume_and_restore(self):
        legacy = self.install_legacy_program(version="0.11.3+ees.2")
        self.interrupt_promotion()
        pending = self.registry["customization"]["pending"]
        self.assertEqual(pending["before"], legacy)
        self.assertEqual(pending["target"]["webui_version"], branding.VERSION)
        custom.validate_registry(self.registry)
        self.assertTrue(self.resume()["changed"])
        self.assertEqual(self.restore()["source_commit"], legacy["source_commit"])
        custom.validate_program(self.program, legacy)
        self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)

    def test_ees2_theme_upgrade_checkonly_apply_and_restore_preserve_runtime(self):
        previous = self.install_legacy_program(version="0.11.3+ees.2")
        before = self.tree()
        self.assertEqual(custom.inspect_bundle(self.config, self.bundle, COMMIT, self.env)["webui_version"],
                         "0.11.3+ees.3")
        self.assertEqual(before, self.tree())
        self.assertTrue(self.apply()["changed"])
        selected = self.registry["customization"]["active"]
        custom.validate_program(self.program, selected)
        for relative in branding.THEME_FILES:
            self.assertTrue((self.program / branding.TARGET_APP / relative).is_file())
        self.assertFalse((self.program / "open_webui/frontend/_ees2").exists())
        self.assertFalse(self.apply()["changed"])
        self.assertEqual(self.restore()["source_commit"], previous["source_commit"])
        custom.validate_program(self.program, previous)
        self.assertEqual(before, self.tree())
        self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)

    def test_theme_assets_missing_from_otherwise_valid_record_stop_before_changes(self):
        for relative in branding.THEME_FILES:
            with self.subTest(relative=relative):
                self.write_bundle(make_wheel(missing=(branding.TARGET_APP + relative,)))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    self.apply()
                self.assertEqual(before, self.tree())
                self.assertEqual(self.events, [])

    def test_interrupted_legacy_restore_keeps_legacy_record_until_cleanup(self):
        legacy = self.install_legacy_program()
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
        self.assertEqual(self.registry["customization"]["pending"]["target"], legacy)
        self.assertTrue((self.program / "open_webui-0.11.3+ees.1.dist-info/RECORD").is_file())
        self.assertTrue(self.restore()["original_program"])
        self.assertFalse(self.program.exists())
        self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)

    def test_legacy_selection_rejects_mixed_metadata_and_frontend(self):
        variants = (
            ({"open_webui-0.11.3+ees.1.dist-info/METADATA": b"Name: open-webui\nVersion: 0.11.3+ees.2\n"}, None),
            ({"open_webui/frontend/_ees1/version.json": b'{"version":"0.11.3+ees.2"}'}, None),
            (None, {"open_webui/frontend/_ees2/extra.js": b"mixed release"}),
        )
        for replacement, extra in variants:
            with self.subTest(replacement=replacement):
                legacy = self.install_legacy_program(replacement=replacement, extra=extra)
                with self.assertRaises(custom.CustomizationError):
                    custom.validate_program(self.program, legacy)
                shutil.rmtree(self.program)
        self.write_bundle(make_wheel(version="0.11.3+ees.1"))
        with self.assertRaises(release.ReleaseError):
            custom.inspect_bundle(self.config, self.bundle, COMMIT, self.env)

    def test_wheel_install_paths_hooks_metadata_frontend_and_record_rejected(self):
        variants = [make_wheel(extra={name: b"unexpected"}) for name in (
            "elsewhere.py", "data/another.txt", "requirements.txt", "open_webui-0.11.3+ees.1.data/scripts/start", "activate.pth",
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

    def test_original_packaging_docs_are_verified_but_not_installed(self):
        content = make_wheel(extra={"requirements-min.txt": b"Minimal Docker dependency reference",
                                    "data/readme.txt": b"Docker data directory description"})
        self.write_bundle(content)
        self.apply()
        selected = self.registry["customization"]["active"]
        self.assertEqual(selected["wheel_sha256"], digest(content))
        with zipfile.ZipFile(io.BytesIO(content)) as source:
            original_record = source.read(custom.RECORD)
            projected_record = (self.program / custom.RECORD).read_bytes()
            self.assertNotEqual(original_record, projected_record)
            self.assertEqual(selected["record_sha256"], digest(projected_record))
            for name in custom._record_rows(projected_record):
                if name != custom.RECORD:
                    self.assertEqual((self.program / name).read_bytes(), source.read(name))
        for name in custom.PACKAGING_FILES:
            self.assertFalse((self.program / name).exists())
        custom.validate_program(self.program, selected)
        self.assertFalse(self.apply()["changed"])
        self.assertTrue(self.restore()["original_program"])
        # Excluding packaging text from installation never exempts it from the
        # original wheel RECORD integrity check performed before extraction.
        with zipfile.ZipFile(io.BytesIO(content)) as source:
            damaged = io.BytesIO()
            with zipfile.ZipFile(damaged, "w") as destination:
                for name in source.namelist():
                    destination.writestr(name, b"tampered" if name == "data/readme.txt" else source.read(name))
        self.write_bundle(damaged.getvalue())
        with self.assertRaisesRegex(release.ReleaseError, "RECORD"):
            self.apply()
        self.assertFalse(self.program.exists())

    def test_packaging_doc_only_change_keeps_app_identity_and_restores_prior_commit(self):
        self.write_bundle(make_wheel(extra={"data/readme.txt": b"first packaging reference"}))
        self.apply()
        first = copy.deepcopy(self.registry["customization"]["active"])
        self.write_bundle(make_wheel(extra={"data/readme.txt": b"second packaging reference"}), commit="b" * 40)
        self.assertTrue(self.apply("b" * 40)["changed"])
        second = self.registry["customization"]["active"]
        self.assertNotEqual(first["wheel_sha256"], second["wheel_sha256"])
        self.assertEqual(first["record_sha256"], second["record_sha256"])
        self.assertEqual(self.restore()["source_commit"], COMMIT)
        self.assertFalse(self.restore()["changed"])
        custom.validate_program(self.program, first)

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

    def test_failed_first_program_promotion_requires_restore_and_preserves_original(self):
        before = self.tree()
        staged = self.root / "state" / "program.staging"
        attempts = []
        original_rename = Path.rename
        def rename(path, target):
            attempts.append((path, target))
            if path == staged:
                raise PermissionError(13, "synthetic promotion lock")
            return original_rename(path, target)
        with mock.patch.object(Path, "rename", rename), self.assertRaises(PermissionError):
            self.apply()
        self.assertEqual(attempts, [(staged, self.program)])
        pending = self.saved["customization"]["pending"]
        self.assertEqual(pending["stage"], "promote")
        self.assertEqual(pending["owner"], OWNER)
        self.assertIsNone(pending["before"])
        self.assertIsNone(self.saved["customization"]["active"])
        self.assertEqual(self.events[-1], "program_promote")
        self.assertNotIn("program_applied", self.events)
        self.assertFalse(self.program.exists())
        custom.validate_program(staged, pending["target"])
        self.assertEqual(before, {name: value for name, value in self.tree().items() if Path(name).parts[0] != "state"})
        with self.assertRaisesRegex(custom.CustomizationError, "Restore"):
            self.apply()
        self.assertTrue(self.restore()["original_program"])
        self.assertIsNone(self.registry["customization"]["pending"])
        self.assertEqual(list((self.root / "state").iterdir()), [])
        self.assertEqual(self.tree(), before)
        self.assertFalse(self.restore()["changed"])

    def test_resume_manual_first_promotion_commits_without_moving_files_and_restores_original(self):
        preserved = self.tree()
        selection = self.interrupt_promotion()
        files, events, registry = self.tree(), list(self.events), copy.deepcopy(self.registry)
        self.assertEqual(custom.check_resume(self.config, self.registry, self.env, selection),
                         self.registry["customization"])
        self.assertEqual((self.tree(), self.events, self.registry), (files, events, registry))
        with mock.patch.object(Path, "rename", side_effect=AssertionError("Resume must not rename")), \
                mock.patch.object(custom, "_extract", side_effect=AssertionError("Resume must not extract")), \
                mock.patch.object(custom, "_remove", side_effect=AssertionError("Resume must not remove")):
            result = self.resume()
        self.assertTrue(result["changed"])
        self.assertFalse(result["original_program"])
        self.assertFalse(result["data_changed"])
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertEqual(self.registry["customization"],
                         {"active": selection, "previous": {"active": None}, "pending": None})
        self.assertEqual(self.tree(), files)
        self.assertEqual(self.registry["last_failure"], {"historical": True})
        self.assert_resume_rejected_unchanged()
        self.assertFalse(self.apply()["changed"])
        self.assertTrue(self.restore()["original_program"])
        self.assertEqual(self.tree(), preserved)

    def test_resume_updated_and_identical_bytes_preserves_exact_predecessor(self):
        self.apply()
        previous = copy.deepcopy(self.registry["customization"]["active"])
        for commit, content in (("b" * 40, make_wheel(replacement={"open_webui/main.py": b"# next app\n"})),
                                ("c" * 40, make_wheel())):
            with self.subTest(commit=commit):
                self.write_bundle(content, commit=commit)
                selected = self.interrupt_promotion(commit)
                files = self.tree()
                self.assertEqual(self.resume(commit)["source_commit"], commit)
                self.assertEqual(self.registry["customization"]["active"], selected)
                self.assertEqual(self.registry["customization"]["previous"], {"active": previous})
                self.assertEqual(self.tree(), files)
                self.assertEqual(self.restore()["source_commit"], COMMIT)
                custom.validate_program(self.program, previous)

    def test_resume_rejects_missing_pending_and_premature_or_duplicate_staging(self):
        self.assert_resume_rejected_unchanged()
        self.interrupt_promotion(manually_promote=False)
        self.assert_resume_rejected_unchanged()
        staged = self.root / "state" / "program.staging"
        staged.rename(self.program)
        staged.mkdir()
        self.assert_resume_rejected_unchanged()
        staged.rmdir()
        previous = self.root / "state" / "program.previous"
        previous.mkdir()
        self.assert_resume_rejected_unchanged()
        previous.rmdir()
        self.assertTrue(self.resume()["changed"])

    def test_resume_rejects_wrong_bundle_target_and_inconsistent_transaction_readonly(self):
        selected = self.interrupt_promotion()
        self.assert_resume_rejected_unchanged("b" * 40)
        original_bundle = self.bundle.read_bytes()
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"# changed under same commit\n"}))
        self.assert_resume_rejected_unchanged()
        self.bundle.write_bytes(original_bundle)
        original = copy.deepcopy(self.registry)
        changes = [
            ("pending", "action", "restore"),
            *(("pending", "stage", stage) for stage in ("staging", "retire_previous", "move_active", "restore")),
            ("pending", "before", selected),
            ("pending", "old_previous", {"active": None}),
            ("pending", "target", dict(selected, source_commit="b" * 40)),
            ("customization", "active", selected),
            ("customization", "previous", {"active": None}),
            ("registry", "phase", "switching"),
            ("registry", "pending", {"kind": "release"}),
            ("registry", "launch_uncertain", True),
            ("registry", "current", {"kind": "release", "python": str(self.python)}),
            ("registry", "current", {"kind": "original", "python": "another-python"}),
        ]
        for location, key, value in changes:
            with self.subTest(location=location, key=key, value=value):
                self.registry = copy.deepcopy(original)
                target = (self.registry if location == "registry" else self.registry["customization"]
                          if location == "customization" else self.registry["customization"]["pending"])
                target[key] = value
                self.assert_resume_rejected_unchanged()
        self.registry = original
        self.assertTrue(self.resume()["changed"])

    def test_resume_rejects_incomplete_changed_extra_or_linked_program_files(self):
        self.interrupt_promotion()
        target = self.program / "open_webui/main.py"
        original = target.read_bytes()
        for value in (b"modified", None):
            with self.subTest(value=value):
                target.write_bytes(value) if value is not None else target.unlink()
                self.assert_resume_rejected_unchanged()
                target.write_bytes(original)
        extra = self.program / "unexpected.txt"
        extra.write_bytes(b"unowned")
        self.assert_resume_rejected_unchanged()
        extra.unlink()
        linked = self.root / "linked.py"
        os.link(target, linked)
        self.assert_resume_rejected_unchanged()
        linked.unlink()
        self.assertTrue(self.resume()["changed"])

    def test_resume_rejects_missing_or_changed_previous_before_recording(self):
        self.apply()
        self.write_bundle(make_wheel(replacement={"open_webui/main.py": b"# next app\n"}), commit="b" * 40)
        self.interrupt_promotion("b" * 40)
        previous = self.root / "state" / "program.previous"
        hidden = self.root / "state" / "retained-for-test"
        previous.rename(hidden)
        self.assert_resume_rejected_unchanged("b" * 40)
        hidden.rename(previous)
        target = previous / "open_webui/main.py"
        original = target.read_bytes()
        target.write_bytes(b"changed predecessor")
        self.assert_resume_rejected_unchanged("b" * 40)
        target.write_bytes(original)
        self.assertTrue(self.resume("b" * 40)["changed"])

    def test_resume_final_record_failure_retains_new_owner_and_remains_restorable(self):
        preserved = self.tree()
        self.interrupt_promotion()
        files = self.tree()
        owner = dict(OWNER, pid=654, created_at="456.78")
        record = self.record
        def fail_complete(config, registry, event):
            if event == "program_applied":
                raise OSError("synthetic final record failure")
            record(config, registry, event)
        with mock.patch.object(self, "record", side_effect=fail_complete), self.assertRaises(OSError):
            self.resume(owner=owner)
        self.assertEqual(self.tree(), files)
        for registry in (self.registry, self.saved):
            self.assertEqual(registry["customization"]["pending"]["owner"], owner)
            self.assertEqual(registry["customization"]["pending"]["stage"], "promote")
            self.assertIsNone(registry["customization"]["active"])
        self.registry = copy.deepcopy(self.saved)
        self.assertTrue(self.restore()["original_program"])
        self.assertEqual(self.tree(), preserved)

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
    @unittest.skipUnless(os.environ.get("EES_TEST_BRANDING_DIR"), "Real built wheel is supplied by Windows/Linux delivery CI")
    def test_real_built_wheel_has_complete_purelib_app_metadata_and_frontend(self):
        root = Path(os.environ["EES_TEST_BRANDING_DIR"])
        content = (root / branding.WHEEL_FILENAME).read_bytes()
        manifest = json.loads((root / "manifest.json").read_bytes())
        release._wheel(content, manifest)
        with zipfile.ZipFile(io.BytesIO(content)) as wheel:
            unsupported = sorted(name for name in wheel.namelist()
                                 if not custom._allowed_name(name) and name not in custom.PACKAGING_FILES)
            self.assertEqual(unsupported, [], "Unsupported real-wheel paths: " + repr(unsupported[:20]))
        layout = custom._wheel_layout(content)
        selection = {"source_commit": COMMIT, "wheel_sha256": digest(content),
                     "record_sha256": layout["record_sha256"], "webui_version": branding.VERSION}
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            for name in ("state", "original/open_webui", "data", "cwd"):
                (fixture / name).mkdir(parents=True)
            preserved = {"original/python.exe": b"original interpreter", "original/open_webui/__init__.py": b"original app",
                         "original/example.py": b"original dependency", "data/webui.db": b"synthetic database",
                         "cwd/.webui_secret_key": b"synthetic secret key"}
            for name, value in preserved.items():
                (fixture / name).write_bytes(value)
            config = {"state_root": str(fixture / "state"), "source_prefix": str(fixture / "original"),
                      "source_python": str(fixture / "original/python.exe"), "package_dir": str(fixture / "original/open_webui"),
                      "data_dir": str(fixture / "data"), "cwd": str(fixture / "cwd")}
            registry = {"schema_version": 1, "phase": "idle", "current": {"kind": "original", "python": config["source_python"]}}
            events = []
            def record(config, registry, event):
                events.append(event)
            # The wheel is already verified above. Supply that exact content at
            # the environment-inspection boundary, then exercise real staging,
            # directory promotion and Restore without importing the application.
            with mock.patch.object(custom, "_load_bundle", return_value=(selection, content)):
                result = custom.apply(config, registry, None, COMMIT, {"DATA_DIR": config["data_dir"]}, record, OWNER)
            self.assertTrue(result["changed"])
            self.assertEqual(events[-2:], ["program_promote", "program_applied"])
            program = fixture / "state/program"
            self.assertFalse((fixture / "state/program.staging").exists())
            self.assertEqual(registry["customization"]["active"], selection)
            self.assertIsNone(registry["customization"]["pending"])
            custom.validate_program(program, selection)
            spec = importlib.machinery.PathFinder.find_spec("open_webui", [str(program)])
            self.assertEqual(Path(spec.origin), program / "open_webui/__init__.py")
            distributions = list(importlib.metadata.distributions(path=[str(program)]))
            self.assertEqual(len(distributions), 1)
            self.assertEqual(distributions[0].version, branding.VERSION)
            self.assertEqual(Path(distributions[0].locate_file("")), program)
            self.assertEqual(json.loads((program / (branding.TARGET_APP + "version.json")).read_bytes())["version"], branding.VERSION)
            self.assertIn(b"EES Portal", (program / "open_webui/frontend/index.html").read_bytes())
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
            self.assertTrue(custom.restore(config, registry, record, OWNER)["original_program"])
            self.assertEqual(list((fixture / "state").iterdir()), [])
            self.assertFalse(custom.restore(config, registry, record, OWNER)["changed"])
            # Exercise the same real payload after a simulated promotion denial.
            # The separate rename below represents the operator's completed move;
            # CI does not claim to reproduce the company PC's Explorer behavior.
            staged = fixture / "state/program.staging"
            with mock.patch.object(custom, "_load_bundle", return_value=(selection, content)):
                with mock.patch.object(Path, "rename", side_effect=PermissionError(13, "synthetic denial")), \
                        self.assertRaises(PermissionError):
                    custom.apply(config, registry, None, COMMIT, {"DATA_DIR": config["data_dir"]}, record, OWNER)
                self.assertEqual(registry["customization"]["pending"]["stage"], "promote")
                self.assertFalse(program.exists())
                custom.validate_program(staged, selection)
                staged.rename(program)
                with mock.patch.object(Path, "rename", side_effect=AssertionError("Resume must not rename")), \
                        mock.patch.object(custom, "_extract", side_effect=AssertionError("Resume must not extract")), \
                        mock.patch.object(custom, "_remove", side_effect=AssertionError("Resume must not remove")):
                    resumed = custom.resume_apply(config, registry, None, COMMIT,
                                                  {"DATA_DIR": config["data_dir"]}, record, OWNER)
            self.assertTrue(resumed["changed"])
            self.assertEqual(registry["customization"],
                             {"active": selection, "previous": {"active": None}, "pending": None})
            self.assertEqual(events[-2:], ["program_apply_resumed", "program_applied"])
            custom.validate_program(program, selection)
            self.assertTrue(custom.restore(config, registry, record, OWNER)["original_program"])
            self.assertEqual(list((fixture / "state").iterdir()), [])
            for name, value in preserved.items():
                self.assertEqual((fixture / name).read_bytes(), value, name)



if __name__ == "__main__":
    unittest.main()
