"""App-only deployment tests; never start WebUI or open its user database.

The optional current/previous-wheel gate imports each selected WorkflowService
to verify new saves remain reusable after Restore, using a fresh test database.
"""

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
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import ees_webui_customization as custom

release = custom.releases
branding = custom.branding
COMMIT = "a" * 40
OWNER = {"pid": 321, "executable": "registered-python", "created_at": "123.45"}
# Frozen shipped inventory, independent of the builder's current list.
PRE_SPLIT_WORK_FILES = (
    "open_webui/ees_work_demo.py", "open_webui/ees_work_demo_ui/index.html",
    "open_webui/ees_work_demo_ui/ees-work.css", "open_webui/ees_work_demo_ui/ees-work.js",
    "open_webui/ees_workflow.py", "open_webui/workflow_seed.json",
    branding.TARGET_APP + "ees-work-panel.js", branding.TARGET_APP + "ees-work-launcher.js",
    branding.TARGET_APP + "ees-work-launcher.css",
)

PRE_AUTHORING_WORK_FILES = PRE_SPLIT_WORK_FILES + (
    "open_webui/ees_workflow_definition.py", "open_webui/ees_workflow_view.py",
    "open_webui/workflow_policy.json",
)

PRE_EXECUTION_WORK_FILES = PRE_AUTHORING_WORK_FILES + (
    "open_webui/ees_workflow_authoring.py",
)


PRE_INTEGRATED_WORK_FILES = PRE_EXECUTION_WORK_FILES + tuple(
    "open_webui/ees_workflow_" + name + ".py" for name in ("execution", "native", "contract", "examples", "model"))

# The 112 paths shipped before easy authoring, frozen independently of the
# builder's live inventory. The digest uses sorted paths joined with LF.
PRE_EASY_TOOLS_INVENTORY_SHA256 = "b577f1a5a04a33a808998d5a6b2908eb2af0735b5aa98bd0cbfbc9f38d2fde47"
EASY_TOOLS_FILES = ("open_webui/workflow_help.json", "open_webui/workflow_tool_examples.json")


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
        "open_webui/frontend/index.html": b"<title>EES Work</title>\n",
        app + "version.json": json.dumps({"version": version}).encode(),
        app + "immutable/chunks/test.js": b"const title = 'EES Work';\n",
    }
    if version in {"0.11.3+ees.3", "0.11.3+ees.4", "0.11.3+ees.5", "0.11.3+ees.6", "0.11.3+ees.7", "0.11.3+ees.8", "0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11", "0.11.3+ees.12", "0.11.3+ees.13"}:
        members.update({app + name: b"synthetic checked theme asset\n" for name in branding.THEME_FILES})
    if version == "0.11.3+ees.5":
        members.update({name: b"synthetic checked work asset\n" for name in branding.LEGACY_WORK_FILES})
    if version in {"0.11.3+ees.6", "0.11.3+ees.7", "0.11.3+ees.8", "0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11", "0.11.3+ees.12", "0.11.3+ees.13"}:
        if version == "0.11.3+ees.13":
            work_files = branding.WORK_FILES
        elif version == "0.11.3+ees.12":
            work_files = PRE_INTEGRATED_WORK_FILES
        elif version == "0.11.3+ees.11":
            work_files = PRE_EXECUTION_WORK_FILES
        elif version in {"0.11.3+ees.9", "0.11.3+ees.10"}:
            work_files = PRE_AUTHORING_WORK_FILES
        else:
            work_files = PRE_SPLIT_WORK_FILES
        members.update({app + name[len(branding.TARGET_APP):] if name.startswith(branding.TARGET_APP) else name:
                        b"synthetic checked work asset\n" for name in work_files})
    if version in {"0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11", "0.11.3+ees.12", "0.11.3+ees.13"}:
        members.update({name: b"# synthetic checked asset guard\n" for name in branding.ASSET_GUARD_FILES})
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


def rename_denied(winerror=5):
    error = PermissionError(13, "synthetic Windows directory denial")
    error.winerror = winerror
    return error


class ProgramRenameTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "program.staging"
        self.destination = self.root / "program"
        self.source.mkdir()
        (self.source / "owned.txt").write_bytes(b"owned program")

    def move(self):
        custom._rename_program(self.source, self.destination, "promote")

    def test_transient_windows_denials_retry_only_the_same_fixed_move(self):
        original = Path.rename
        for stage, names in (("move_active", ("program", "program.previous")),
                             ("promote", ("program.staging", "program")),
                             ("restore", ("program.previous", "program"))):
            for winerror in (5, 32, 33):
                with self.subTest(stage=stage, winerror=winerror):
                    directory = self.root / (stage + str(winerror))
                    directory.mkdir()
                    source, destination = (directory / name for name in names)
                    source.mkdir()
                    (source / "owned.txt").write_bytes(b"owned")
                    attempts = []
                    def rename(path, target):
                        attempts.append((path, target))
                        if len(attempts) < 3:
                            raise rename_denied(winerror)
                        return original(path, target)
                    with mock.patch.object(custom.sys, "platform", "win32"), \
                            mock.patch.object(Path, "rename", rename), \
                            mock.patch.object(custom.time, "sleep") as sleep:
                        custom._rename_program(source, destination, stage)
                    self.assertEqual(attempts, [(source, destination)] * 3)
                    self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2)])
                    self.assertFalse(source.exists())
                    self.assertEqual((destination / "owned.txt").read_bytes(), b"owned")

    def test_exhaustion_preserves_original_error_and_owned_directory(self):
        denied = rename_denied()
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=denied) as rename, \
                mock.patch.object(custom.time, "sleep") as sleep, self.assertRaises(PermissionError) as caught:
            self.move()
        self.assertIs(caught.exception, denied)
        self.assertEqual((denied.errno, denied.winerror), (13, 5))
        self.assertEqual((denied.program_rename_stage, denied.program_rename_attempts,
                          denied.program_rename_wait_seconds), ("promote", 5, 15))
        self.assertIs(denied.program_rename_failed, True)
        self.assertEqual(rename.call_count, 5)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2), mock.call(4), mock.call(8)])
        self.assertFalse(self.destination.exists())
        self.assertEqual((self.source / "owned.txt").read_bytes(), b"owned program")

    def test_non_windows_and_other_errors_do_not_wait_or_retry(self):
        cases = (("linux", rename_denied()), ("win32", PermissionError(13, "plain errno")),
                 ("win32", rename_denied(2)), ("win32", rename_denied(145)),
                 ("win32", OSError(5, "unrelated filesystem failure")))
        for platform, denied in cases:
            with self.subTest(platform=platform, winerror=getattr(denied, "winerror", None)), \
                    mock.patch.object(custom.sys, "platform", platform), \
                    mock.patch.object(Path, "rename", side_effect=denied) as rename, \
                    mock.patch.object(custom.time, "sleep") as sleep, self.assertRaises(OSError) as caught:
                self.move()
            self.assertIs(caught.exception, denied)
            self.assertEqual(rename.call_count, 1)
            self.assertEqual((denied.program_rename_attempts, denied.program_rename_wait_seconds), (1, 0))
            sleep.assert_not_called()

    def test_destination_created_during_wait_is_never_replaced(self):
        def appeared(_delay):
            self.destination.mkdir()
            (self.destination / "unowned.txt").write_bytes(b"preserved outsider")
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=rename_denied()) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=appeared), \
                self.assertRaisesRegex(custom.CustomizationError, "destination appeared") as caught:
            self.move()
        self.assertEqual(rename.call_count, 1)
        self.assertEqual(caught.exception.program_rename_attempts, 1)
        self.assertEqual((self.destination / "unowned.txt").read_bytes(), b"preserved outsider")
        self.assertEqual((self.source / "owned.txt").read_bytes(), b"owned program")

    def test_dangling_destination_link_is_rejected_before_any_rename(self):
        try:
            self.destination.symlink_to(self.root / "missing", target_is_directory=True)
        except OSError as exc:
            self.skipTest("This test account cannot create symlinks: " + type(exc).__name__)
        with mock.patch.object(Path, "rename") as rename, mock.patch.object(custom.time, "sleep") as sleep, \
                self.assertRaises(custom.states.StateError):
            self.move()
        rename.assert_not_called()
        sleep.assert_not_called()
        self.assertTrue(self.destination.is_symlink())

    def test_replaced_source_identity_stops_after_wait(self):
        original = Path.rename
        retained = self.root / "retained"
        def replaced(_delay):
            original(self.source, retained)
            self.source.mkdir()
            (self.source / "unowned.txt").write_bytes(b"new directory")
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=rename_denied()) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=replaced), \
                self.assertRaisesRegex(custom.CustomizationError, "source changed"):
            self.move()
        self.assertEqual(rename.call_count, 1)
        self.assertFalse(self.destination.exists())
        self.assertEqual((retained / "owned.txt").read_bytes(), b"owned program")
        self.assertEqual((self.source / "unowned.txt").read_bytes(), b"new directory")

    def test_external_promotion_is_not_adopted_as_success(self):
        original = Path.rename
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=rename_denied()) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=lambda _: original(self.source, self.destination)), \
                self.assertRaises(custom.states.StateError):
            self.move()
        self.assertEqual(rename.call_count, 1)
        self.assertEqual((self.destination / "owned.txt").read_bytes(), b"owned program")

    def test_path_safety_is_rechecked_after_wait(self):
        safe = custom.states._safe
        moved = False
        def checked(path, *args, **kwargs):
            if moved:
                raise custom.states.StateError("synthetic newly introduced reparse point")
            return safe(path, *args, **kwargs)
        def changed(_delay):
            nonlocal moved
            moved = True
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(custom.states, "_safe", side_effect=checked), \
                mock.patch.object(Path, "rename", side_effect=rename_denied()) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=changed), \
                self.assertRaises(custom.states.StateError):
            self.move()
        self.assertEqual(rename.call_count, 1)
        self.assertFalse(self.destination.exists())

    def test_cancellation_during_wait_stops_without_retry(self):
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=rename_denied()) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=KeyboardInterrupt()) as sleep, \
                self.assertRaises(KeyboardInterrupt) as caught:
            self.move()
        self.assertEqual(rename.call_count, 1)
        sleep.assert_called_once_with(1)
        self.assertEqual((caught.exception.program_rename_attempts,
                          caught.exception.program_rename_wait_seconds), (1, 0))
        self.assertIs(caught.exception.program_rename_failed, False)
        self.assertTrue(self.source.is_dir())
        self.assertFalse(self.destination.exists())

    def test_path_denial_after_wait_is_not_misreported_as_a_rename_failure(self):
        denied = rename_denied()
        safe = custom.states._safe
        after_wait = False
        def checked(path, *args, **kwargs):
            if after_wait:
                # Reuse even the same exception object as the first rename.
                raise denied
            return safe(path, *args, **kwargs)
        def waited(_delay):
            nonlocal after_wait
            after_wait = True
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(custom.states, "_safe", side_effect=checked), \
                mock.patch.object(Path, "rename", side_effect=denied) as rename, \
                mock.patch.object(custom.time, "sleep", side_effect=waited), \
                self.assertRaises(PermissionError) as caught:
            self.move()
        self.assertIs(caught.exception, denied)
        self.assertIs(denied.program_rename_failed, False)
        self.assertEqual((denied.program_rename_attempts, denied.program_rename_wait_seconds), (1, 1))
        self.assertEqual(rename.call_count, 1)
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(sys.platform == "win32", "Requires an actual Windows directory sharing lock")
    def test_real_windows_directory_lock_released_during_wait_then_promotes(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL
        # Use a real read handle: a zero-access metadata handle did not block
        # rename on Windows CI. Share reads/writes, but omit FILE_SHARE_DELETE.
        handle = create(str(self.source), 0x80000000, 0x1 | 0x2, None, 3, 0x02000000, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value, ctypes.get_last_error())
        def release_lock(_delay):
            nonlocal handle
            self.assertTrue(close(handle), ctypes.get_last_error())
            handle = None
        try:
            with self.assertRaises(OSError) as blocked:
                self.source.rename(self.destination)
            self.assertIn(getattr(blocked.exception, "winerror", None), (5, 32, 33))
            self.assertTrue(self.source.is_dir())
            self.assertFalse(self.destination.exists())
            with mock.patch.object(custom.time, "sleep", side_effect=release_lock) as sleep:
                self.move()
            sleep.assert_called_once_with(1)
        finally:
            if handle is not None:
                close(handle)
        self.assertFalse(self.source.exists())
        self.assertEqual((self.destination / "owned.txt").read_bytes(), b"owned program")


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

    def install_legacy_program(self, *, replacement=None, extra=None, version="0.11.3+ees.1", missing=()):
        content = make_wheel(version=version, replacement=replacement, extra=extra, missing=missing)
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

    def test_real_ees10_to_authoring_apply_restore_preserves_program_and_data(self):
        self._real_previous_apply_restore(
            "EES_TEST_LEGACY_WORKFLOW_WHEEL", "EES_REQUIRE_LEGACY_WORKFLOW",
            "0.11.3+ees.10", "a443d30c6694df0e1cbe082a0b99aa5f2d566917",
            "ad08078b9db2cf484a6af614b95bd4cf7c9910070d2505bc271065278d079ddd")

    def test_real_ees11_to_execution_apply_restore_preserves_program_and_data(self):
        self._real_previous_apply_restore(
            "EES_TEST_PREVIOUS_WORKFLOW_WHEEL", "EES_REQUIRE_PREVIOUS_WORKFLOW",
            "0.11.3+ees.11", "991cdb1d80ae07471fb50594831d74fe602b1ef7",
            "27f6a1c37264d4f205bedb6635c9eaae8a36a5d023d36d1dd595e34728c8b8d3")

    def test_ees12_inventory_is_frozen_and_frontend_namespaces_cannot_be_interchanged(self):
        self.assertEqual(set(branding.WORK_FILES_V12), set(PRE_INTEGRATED_WORK_FILES))
        previous = "0.11.3+ees.12"
        previous_app = "open_webui/frontend/_ees12/"
        new_app = "open_webui/frontend/_ees13/"
        self.assertEqual(custom._version_paths(previous)[1], previous_app)
        self.assertEqual(branding.TARGET_APP, new_app)
        for version in (previous, branding.VERSION):
            with zipfile.ZipFile(io.BytesIO(make_wheel(version=version))) as wheel:
                rows = custom._record_rows(wheel.read("open_webui-" + version + ".dist-info/RECORD"), version=version)
                namespace = previous_app if version == previous else new_app
                other = new_app if version == previous else previous_app
                self.assertTrue(any(name.startswith(namespace) for name in rows))
                self.assertFalse(any(name.startswith(other) for name in rows))
                self.assertEqual("open_webui/ees_workflow_examples.py" in rows, version == previous)
                self.assertEqual("open_webui/ees_workflow_workspace.py" in rows, version == branding.VERSION)
                missing = "open_webui/ees_workflow_examples.py" if version == previous else "open_webui/ees_workflow_workspace.py"
            # Recomputed RECORD after omission must still fail required-inventory validation.
            with zipfile.ZipFile(io.BytesIO(make_wheel(version=version, missing=(missing,)))) as broken:
                with self.assertRaisesRegex(custom.CustomizationError, "complete app"):
                    custom._record_rows(broken.read("open_webui-" + version + ".dist-info/RECORD"), version=version)

    def test_real_ees12_visual_revision_apply_restore_preserves_prior_asset_inventory(self):
        self._real_previous_apply_restore(
            "EES_TEST_PREVIOUS_C_WHEEL", "EES_REQUIRE_PREVIOUS_C",
            "0.11.3+ees.12", "8027aaf2e654778f052a966e5a49feed0fc54f69",
            "d35bc2bb4adc789cc93752b49550a47446461f1e54ba0015a3952e6af78ca254", exercise_resume=True)

    def _real_previous_apply_restore(self, previous_env, required_env, version, commit, wheel_hash, *, exercise_resume=False):
        current_dir = os.environ.get("EES_TEST_BRANDING_DIR")
        previous_file = os.environ.get(previous_env)
        if not current_dir or not previous_file:
            if os.environ.get(required_env) == "1":
                self.fail("Actual program Restore needs current and fixed previous wheels")
            self.skipTest("Supply current and fixed " + version + " wheels for program Restore")
        old = Path(previous_file).read_bytes()
        self.assertEqual(digest(old), wheel_hash)
        with zipfile.ZipFile(io.BytesIO(old)) as wheel:
            old_record_name = "open_webui-" + version + ".dist-info/RECORD"
            rows = custom._record_rows(wheel.read(old_record_name),
                                       allow_packaging=True, version=version)
            # Reproduce the existing app-only installation inventory: packaging
            # readmes/requirements are never part of the selected program.
            rows = {name: row for name, row in rows.items() if name not in custom.PACKAGING_FILES}
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            for name in sorted(set(rows) - {old_record_name}):
                writer.writerow([name, *rows[name]])
                target = self.program / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(wheel.read(name))
            writer.writerow([old_record_name, "", ""])
            old_record = output.getvalue().encode("utf-8")
            (self.program / old_record_name).write_bytes(old_record)
            old_selection = {"source_commit": commit,
                "wheel_sha256": digest(old), "webui_version": version,
                "record_sha256": digest(old_record)}
        self.registry.update(schema_version=2, customization={
            "active": old_selection, "previous": {"active": None}, "pending": None})
        custom.validate_program(self.program, old_selection)
        def program_hashes():
            return {str(path.relative_to(self.program)): digest(path.read_bytes())
                    for path in self.program.rglob("*") if path.is_file()}
        before = program_hashes()
        preserved = {path: path.read_bytes() for path in (
            self.root / "data/webui.db", self.root / "cwd/.webui_secret_key", self.python)}
        current = (Path(current_dir) / branding.WHEEL_FILENAME).read_bytes()
        layout = custom._wheel_layout(current)
        selected = {"source_commit": COMMIT, "webui_version": branding.VERSION,
            "wheel_sha256": digest(current), "record_sha256": layout["record_sha256"]}
        # Only the pre-existing runtime dependency inspection is isolated.
        # Staging, fixed inventories, promotion and Restore use actual wheels.
        with mock.patch.object(custom, "_load_bundle", return_value=(selected, current)):
            if exercise_resume:
                # Inject a promotion failure, not a claimed Windows lock. The
                # entire staged candidate/old inventory is real, and explicit
                # Resume still validates their RECORDs and exact transaction.
                self.interrupt_promotion()
                self.assertEqual(self.registry["customization"]["active"], old_selection)
                self.assertEqual(self.registry["customization"]["pending"]["target"], selected)
                self.assertTrue(self.resume()["changed"])
                self.assertIsNone(self.registry["customization"]["pending"])
            else:
                self.assertTrue(self.apply()["changed"])
        custom.validate_program(self.program, selected)
        if version == "0.11.3+ees.12":
            self.assertTrue((self.program / branding.TARGET_APP / "brand-layers.svg").is_file())
            self.assertFalse((self.program / branding.TARGET_APP / "immutable").exists())
            self.assertTrue(any((self.program / branding.TARGET_APP).glob("immutable-c*")))
        self.assertTrue((self.program / "open_webui/ees_workflow_authoring.py").is_file())
        for name in ("execution", "native", "contract", "model", "workspace", "operations"):
            self.assertTrue((self.program / ("open_webui/ees_workflow_" + name + ".py")).is_file())
        self.assertFalse((self.program / "open_webui/ees_workflow_examples.py").exists())
        self.assertFalse((self.program / "open_webui/workflow_seed.json").exists())
        self.assertEqual(self.restore()["source_commit"], old_selection["source_commit"])
        custom.validate_program(self.program, old_selection)
        self.assertEqual(program_hashes(), before)
        self.assertEqual((self.program / "open_webui/ees_workflow_authoring.py").exists(),
                         version in {"0.11.3+ees.11", "0.11.3+ees.12", "0.11.3+ees.13"})
        for name in ("execution", "native", "contract", "examples", "model"):
            self.assertEqual((self.program / ("open_webui/ees_workflow_" + name + ".py")).exists(),
                             version == "0.11.3+ees.12")
        if version == "0.11.3+ees.12":
            old_app = custom._version_paths(version)[1]
            self.assertFalse((self.program / branding.TARGET_APP).exists(), "Restore removes the new frontend namespace")
            self.assertFalse((self.program / old_app / "brand-layers.svg").exists())
            self.assertTrue((self.program / old_app / "immutable").is_dir())
        for path, value in preserved.items():
            self.assertEqual(path.read_bytes(), value)

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

    def test_previous_theme_versions_pending_can_resume_and_restore(self):
        for version in ("0.11.3+ees.2", "0.11.3+ees.3", "0.11.3+ees.4", "0.11.3+ees.5", "0.11.3+ees.6", "0.11.3+ees.7", "0.11.3+ees.8", "0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11"):
            with self.subTest(version=version):
                legacy = self.install_legacy_program(version=version)
                self.interrupt_promotion()
                pending = self.registry["customization"]["pending"]
                self.assertEqual(pending["before"], legacy)
                self.assertEqual(pending["target"]["webui_version"], branding.VERSION)
                custom.validate_registry(self.registry)
                self.assertTrue(self.resume()["changed"])
                self.assertEqual(self.restore()["source_commit"], legacy["source_commit"])
                custom.validate_program(self.program, legacy)
                self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)
                shutil.rmtree(self.program)

    def test_previous_theme_versions_checkonly_apply_and_restore_preserve_runtime(self):
        for version in ("0.11.3+ees.2", "0.11.3+ees.3", "0.11.3+ees.4", "0.11.3+ees.5", "0.11.3+ees.6", "0.11.3+ees.7", "0.11.3+ees.8", "0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11"):
            with self.subTest(version=version):
                previous = self.install_legacy_program(version=version)
                for name in ("ees_workflow_definition.py", "ees_workflow_view.py", "workflow_policy.json"):
                    self.assertEqual((self.program / "open_webui" / name).exists(), version in {"0.11.3+ees.9", "0.11.3+ees.10", "0.11.3+ees.11"})
                self.assertEqual((self.program / "open_webui/ees_workflow_authoring.py").exists(), version == "0.11.3+ees.11")
                before = self.tree()
                self.assertEqual(custom.inspect_bundle(self.config, self.bundle, COMMIT, self.env)["webui_version"],
                                 branding.VERSION)
                self.assertEqual(before, self.tree())
                self.assertTrue(self.apply()["changed"])
                selected = self.registry["customization"]["active"]
                custom.validate_program(self.program, selected)
                for relative in branding.THEME_FILES:
                    self.assertTrue((self.program / branding.TARGET_APP / relative).is_file())
                self.assertFalse((self.program / "open_webui/frontend" / branding.PROGRAM_FRONTENDS[version]).exists())
                self.assertFalse(self.apply()["changed"])
                self.assertEqual(self.restore()["source_commit"], previous["source_commit"])
                custom.validate_program(self.program, previous)
                self.assertEqual(before, self.tree())
                self.assertEqual(self.registry["runtime_ca_sha256"], "d" * 64)
                shutil.rmtree(self.program)

    def test_theme_assets_missing_from_otherwise_valid_record_stop_before_changes(self):
        for relative in branding.THEME_FILES:
            with self.subTest(relative=relative):
                self.write_bundle(make_wheel(missing=(branding.TARGET_APP + relative,)))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    self.apply()
                self.assertEqual(before, self.tree())
                self.assertEqual(self.events, [])

    def test_work_files_missing_from_otherwise_valid_record_stop_before_changes(self):
        for name in branding.WORK_FILES:
            with self.subTest(name=name):
                self.write_bundle(make_wheel(missing=(name,)))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    self.apply()
                self.assertEqual(before, self.tree())
                self.assertEqual(self.events, [])

    def test_ees13_previous_inventory_is_frozen_and_old_incoming_bundle_is_rejected(self):
        previous = sorted(branding.WORK_FILES_V13)
        self.assertEqual(len(previous), 112)
        self.assertEqual(digest("\n".join(previous).encode("utf-8")), PRE_EASY_TOOLS_INVENTORY_SHA256)
        self.assertEqual(set(branding.WORK_FILES) - set(previous), set(EASY_TOOLS_FILES))
        self.write_bundle(make_wheel(missing=EASY_TOOLS_FILES))
        before = self.tree()
        with self.assertRaisesRegex(custom.CustomizationError, "complete app"):
            self.apply()
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.events, [])

    def test_pre_easy_tools_ees13_apply_restore_preserves_its_verified_inventory(self):
        previous = self.install_legacy_program(version="0.11.3+ees.13", missing=EASY_TOOLS_FILES)
        custom.validate_program(self.program, previous)
        before = self.tree()
        self.assertTrue(self.apply()["changed"])
        current = self.registry["customization"]["active"]
        custom.validate_program(self.program, current)
        for name in EASY_TOOLS_FILES:
            self.assertTrue((self.program / name).is_file())
        self.assertEqual(self.restore()["source_commit"], previous["source_commit"])
        custom.validate_program(self.program, previous)
        self.assertEqual(self.tree(), before)
        self.assertFalse(self.restore()["changed"])

    def test_ees13_inventory_compatibility_never_allows_current_json_or_record_tampering(self):
        self.apply()
        selected = copy.deepcopy(self.registry["customization"]["active"])
        record_path = self.program / custom.RECORD
        original_record = record_path.read_bytes()
        originals = {name: (self.program / name).read_bytes() for name in EASY_TOOLS_FILES}
        for missing in ((EASY_TOOLS_FILES[0],), (EASY_TOOLS_FILES[1],), EASY_TOOLS_FILES):
            with self.subTest(missing=missing):
                for name in missing:
                    (self.program / name).unlink()
                for operation in (self.apply, self.restore):
                    before = self.tree()
                    with self.assertRaisesRegex(custom.CustomizationError, "missing or unexpected"):
                        operation()
                    self.assertEqual(self.tree(), before)
                    self.assertEqual(self.registry["customization"]["active"], selected)
                # Recomputing a smaller RECORD cannot convert a current
                # selection to an older inventory: its saved hash is fixed.
                output = io.StringIO()
                writer = csv.writer(output, lineterminator="\n")
                writer.writerows(row for row in csv.reader(io.StringIO(original_record.decode("utf-8"))) if row[0] not in missing)
                record_path.write_bytes(output.getvalue().encode("utf-8"))
                for operation in (self.apply, self.restore):
                    before = self.tree()
                    with self.assertRaisesRegex(custom.CustomizationError, "RECORD changed"):
                        operation()
                    self.assertEqual(self.tree(), before)
                    self.assertEqual(self.registry["customization"]["active"], selected)
                record_path.write_bytes(original_record)
                for name in missing:
                    (self.program / name).write_bytes(originals[name])
        custom.validate_program(self.program, selected)

    def test_ees13_legacy_inventory_rejects_a_half_present_help_asset_pair(self):
        for missing in EASY_TOOLS_FILES:
            with self.subTest(missing=missing):
                previous = self.install_legacy_program(version="0.11.3+ees.13", missing=(missing,))
                with self.assertRaisesRegex(custom.CustomizationError, "complete app"):
                    custom.validate_program(self.program, previous)
                shutil.rmtree(self.program)

    def test_current_ees13_partial_cleanup_uses_its_complete_record_inventory(self):
        self.apply()
        selected = self.registry["customization"]["active"]
        (self.program / EASY_TOOLS_FILES[0]).unlink()
        self.assertTrue((self.program / EASY_TOOLS_FILES[1]).is_file())
        # An interrupted removal still has a complete, verified RECORD even
        # when one JSON file is already gone. Finish only that selected tree.
        custom._remove(self.program, selected, partial=True)
        self.assertFalse(self.program.exists())

    def test_asset_guard_missing_from_current_program_stops_before_changes(self):
        for name in branding.ASSET_GUARD_FILES:
            with self.subTest(name=name):
                self.write_bundle(make_wheel(missing=(name,)))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    self.apply()
                self.assertEqual(before, self.tree())
                self.assertEqual(self.events, [])

    def test_installed_current_program_requires_guard_but_ees8_backup_does_not(self):
        previous = self.install_legacy_program(version="0.11.3+ees.8")
        for name in branding.ASSET_GUARD_FILES:
            self.assertFalse((self.program / name).exists())
        custom.validate_program(self.program, previous)
        self.assertTrue(self.apply()["changed"])
        selected = self.registry["customization"]["active"]
        for name in branding.ASSET_GUARD_FILES:
            guard = self.program / name
            content = guard.read_bytes()
            guard.unlink()
            with self.assertRaises(custom.CustomizationError):
                custom.validate_program(self.program, selected)
            guard.write_bytes(content)
        self.assertEqual(self.restore()["source_commit"], previous["source_commit"])
        custom.validate_program(self.program, previous)
        for name in branding.ASSET_GUARD_FILES:
            self.assertFalse((self.program / name).exists())

    def test_installed_ees3_still_requires_theme_assets_after_wrapper_update(self):
        for relative in branding.THEME_FILES:
            with self.subTest(relative=relative):
                previous = self.install_legacy_program(version="0.11.3+ees.3",
                    missing=("open_webui/frontend/_ees3/" + relative,))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    custom.validate_program(self.program, previous)
                self.assertEqual(before, self.tree())
                shutil.rmtree(self.program)

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

    def test_installed_ees6_still_requires_its_own_work_assets_after_wrapper_update(self):
        for name in PRE_SPLIT_WORK_FILES:
            previous_name = name.replace(branding.TARGET_APP, "open_webui/frontend/_ees6/", 1)
            with self.subTest(name=previous_name):
                previous = self.install_legacy_program(version="0.11.3+ees.6", missing=(previous_name,))
                before = self.tree()
                with self.assertRaises(custom.CustomizationError):
                    custom.validate_program(self.program, previous)
                self.assertEqual(before, self.tree())
                shutil.rmtree(self.program)

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

    def test_exhausted_windows_promote_preserves_pending_and_can_manually_resume(self):
        before = self.install_legacy_program()
        preserved = {name: value for name, value in self.tree().items() if Path(name).parts[0] != "state"}
        staged, previous = (self.root / "state" / name for name in ("program.staging", "program.previous"))
        original = Path.rename
        attempts = []
        def rename(path, target):
            attempts.append((path, target))
            if path == staged:
                raise rename_denied()
            return original(path, target)
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", rename), mock.patch.object(custom.time, "sleep") as sleep, \
                self.assertRaises(PermissionError) as caught:
            self.apply()
        self.assertEqual(caught.exception.program_rename_attempts, 5)
        self.assertEqual(attempts, [(self.program, previous)] + [(staged, self.program)] * 5)
        self.assertEqual(sleep.call_count, 4)
        pending = self.saved["customization"]["pending"]
        self.assertEqual((pending["action"], pending["stage"], pending["before"]), ("apply", "promote", before))
        self.assertEqual(self.events.count("program_apply_started"), 1)
        self.assertFalse(self.program.exists())
        custom.validate_program(previous, before)
        custom.validate_program(staged, pending["target"])
        self.assertEqual(preserved, {name: value for name, value in self.tree().items() if Path(name).parts[0] != "state"})
        staged.rename(self.program)
        self.assertTrue(self.resume()["changed"])
        self.assertIsNone(self.saved["customization"]["pending"])
        self.assertEqual(self.restore()["source_commit"], before["source_commit"])

    def test_exhausted_windows_restore_retains_verified_previous_for_explicit_retry(self):
        before = self.install_legacy_program()
        self.apply()
        previous = self.root / "state" / "program.previous"
        denied = rename_denied(32)
        with mock.patch.object(custom.sys, "platform", "win32"), \
                mock.patch.object(Path, "rename", side_effect=denied), \
                mock.patch.object(custom.time, "sleep"), self.assertRaises(PermissionError) as caught:
            self.restore()
        self.assertIs(caught.exception, denied)
        self.assertEqual((denied.program_rename_stage, denied.program_rename_attempts), ("restore", 5))
        pending = self.saved["customization"]["pending"]
        self.assertEqual((pending["action"], pending["stage"]), ("restore", "restore"))
        custom.validate_program(previous, before)
        self.assertFalse(self.program.exists())
        self.assertEqual(self.restore()["source_commit"], before["source_commit"])
        custom.validate_program(self.program, before)

    def test_successful_and_noop_apply_restore_never_wait(self):
        with mock.patch.object(custom.time, "sleep") as sleep:
            self.assertTrue(self.apply()["changed"])
            self.assertFalse(self.apply()["changed"])
            self.assertTrue(self.restore()["changed"])
            self.assertFalse(self.restore()["changed"])
        sleep.assert_not_called()

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
    @unittest.skipUnless(os.environ.get("EES_TEST_BRANDING_DIR") and os.environ.get("EES_TEST_PREVIOUS_BRANDING_DIR"),
                         "Supply current and previous shipped wheels for the reverse-compatibility gate")
    def test_saved_workflow_survives_real_upgrade_then_previous_program_restore(self):
        current = Path(os.environ["EES_TEST_BRANDING_DIR"])
        previous = Path(os.environ["EES_TEST_PREVIOUS_BRANDING_DIR"])
        old_manifest = json.loads((previous / "manifest.json").read_text(encoding="utf-8"))
        version = old_manifest["version"]
        self.assertIn(version, {"0.11.3+ees.7", "0.11.3+ees.8"})
        self.assertEqual(old_manifest["source"]["sha256"], branding.SOURCE_SHA256)
        old_bytes = (previous / old_manifest["wheel"]["filename"]).read_bytes()
        self.assertEqual(digest(old_bytes), old_manifest["wheel"]["sha256"])
        content = (current / branding.WHEEL_FILENAME).read_bytes()
        release._wheel(content, json.loads((current / "manifest.json").read_text(encoding="utf-8")))
        layout = custom._wheel_layout(content)
        selection = {"source_commit": COMMIT, "wheel_sha256": digest(content),
                     "record_sha256": layout["record_sha256"], "webui_version": branding.VERSION}
        # Import each actual selected program in a fresh interpreter. Only the
        # unrelated WebUI CLI initializer and user/chat lookup surroundings are
        # isolated; persistence, API validation and read/reuse run real code.
        probe = r'''
import asyncio, importlib, json, sys, types
from pathlib import Path
program, data, phase = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
package = types.ModuleType("open_webui")
package.__path__ = [str(program / "open_webui")]
sys.modules["open_webui"] = package
workflow = importlib.import_module("open_webui.ees_workflow")
assert Path(workflow.__file__).parent == program / "open_webui"
user = {"id": "fixture-admin", "role": "admin"}
users = {user["id"]: user, "other": {"id": "other", "role": "user"}}
chats = {name: {"id": name, "user_id": user["id"]} for name in ("before-chat", "after-chat")}
service = workflow.WorkflowService(data / "ees-work.sqlite3", users.get, chats.get)
async def state():
    result = {}
    for chat in chats:
        value = await service.get_state(user, chat_id=chat)
        assert value["ok"], value
        result[chat] = value
    return result
async def run():
    expected_file = data.parent / "expected-workflow.json"
    if phase != "before":
        assert await state() == json.loads(expected_file.read_text(encoding="utf-8"))
    chat = "before-chat" if phase == "before" else "after-chat"
    if phase != "restore":
        value = await service.handle_action(user, {"action": "create", "chat_id": chat, "payload": {}})
        assert value["ok"], value
        case = value["case"]
        actions = [("run", "scope-j", {"confirm": True}),
                   ("update_inputs", "db-j", {"inputs": {"db": phase + "-target"}})]
        for action, node, payload in actions:
            value = await service.handle_action(user, {"action": action, "chat_id": chat,
                "case_id": case["id"], "node_id": node, "expected_revision": case["revision"], "payload": payload})
            assert value["ok"], value
            case = value["case"]
        definition = value["draft"]
        definition["nodes"]["setup-p"]["name"] = phase + "-saved-user-draft"
        saved = await service.handle_action(user, {"action": "save_draft",
            "expected_revision": value["draft_revision"], "payload": {"definition": definition}})
        assert saved["ok"], saved
        expected_file.write_text(json.dumps(await state(), ensure_ascii=False), encoding="utf-8")
    else:
        value = await service.get_state(user, chat_id=chat)
        case = value["case"]
        assert value["draft"]["nodes"]["setup-p"]["name"] == "after-saved-user-draft"
        assert case["jobs"]["scope-j"]["history"]
        assert case["jobs"]["db-j"]["inputs"]["db"] == "after-target"
        denied = await service.get_state(users["other"], case_id=case["id"])
        assert denied["error"]["code"] == "case_not_found"
        # The restored old code can continue a new-version save, not just read
        # bytes. The original case revision/history remain available as well.
        continued = await service.handle_action(user, {"action": "select", "chat_id": chat,
            "case_id": case["id"], "node_id": "db-j", "expected_revision": case["revision"]})
        assert continued["ok"], continued
        assert continued["case"]["revision"] == case["revision"] + 1
asyncio.run(run())
print("workflow_" + phase + "=pass")
'''
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            for name in ("state/program", "original/open_webui", "data", "cwd"):
                (fixture / name).mkdir(parents=True)
            program = fixture / "state/program"
            info = f"open_webui-{version}.dist-info/"
            record_name = info + "RECORD"
            # Reconstruct the already-installed predecessor using the same
            # app-only inventory: upstream packaging references stay outside.
            with zipfile.ZipFile(io.BytesIO(old_bytes)) as wheel:
                rows = custom._record_rows(wheel.read(record_name), allow_packaging=True, version=version)
                rows = {name: values for name, values in rows.items() if name not in custom.PACKAGING_FILES}
                record = io.StringIO()
                writer = csv.writer(record, lineterminator="\n")
                for name in sorted(set(rows) - {record_name}):
                    writer.writerow([name, *rows[name]])
                    target = program / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(wheel.read(name))
                writer.writerow([record_name, "", ""])
                (program / record_name).write_text(record.getvalue(), encoding="utf-8", newline="\n")
            old_selection = {"source_commit": "e" * 40, "wheel_sha256": digest(old_bytes),
                             "record_sha256": digest((program / record_name).read_bytes()), "webui_version": version}
            custom.validate_program(program, old_selection)
            config = {"state_root": str(fixture / "state"), "source_prefix": str(fixture / "original"),
                      "source_python": str(fixture / "original/python.exe"), "package_dir": str(fixture / "original/open_webui"),
                      "data_dir": str(fixture / "data"), "cwd": str(fixture / "cwd")}
            registry = {"schema_version": 2, "phase": "idle",
                "current": {"kind": "original", "python": config["source_python"]}, "customization": {
                "active": old_selection, "previous": {"active": None}, "pending": None}}
            preserved = {"original/python.exe": b"registered-original-interpreter",
                         "original/open_webui/__init__.py": b"original-application",
                         "data/webui.db": b"unrelated-user-assets-and-chat", "cwd/.webui_secret_key": b"fixture-key"}
            for name, value in preserved.items():
                (fixture / name).write_bytes(value)
            def run_phase(phase):
                result = subprocess.run([sys.executable, "-I", "-B", "-X", "warn_default_encoding",
                    "-W", "error::EncodingWarning", "-c", probe, str(program), config["data_dir"], phase],
                    cwd=fixture, capture_output=True, text=True, encoding="utf-8", timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "workflow_" + phase + "=pass")
            run_phase("before")
            database = fixture / "data/ees-work.sqlite3"
            before = database.read_bytes()
            with mock.patch.object(custom, "_load_bundle", return_value=(selection, content)):
                self.assertTrue(custom.apply(config, registry, None, COMMIT,
                    {"DATA_DIR": config["data_dir"]}, lambda *_: None, OWNER)["changed"])
            self.assertEqual(database.read_bytes(), before)
            custom.validate_program(program, selection)
            run_phase("after")
            after = database.read_bytes()
            self.assertNotEqual(after, before)
            self.assertEqual(custom.restore(config, registry, lambda *_: None, OWNER)["source_commit"], old_selection["source_commit"])
            self.assertEqual(database.read_bytes(), after)
            custom.validate_program(program, old_selection)
            self.assertFalse((program / "open_webui/ees_workflow_definition.py").exists())
            run_phase("restore")
            for name, value in preserved.items():
                self.assertEqual((fixture / name).read_bytes(), value)

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
            self.assertIn(b"EES Work", (program / "open_webui/frontend/index.html").read_bytes())
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
