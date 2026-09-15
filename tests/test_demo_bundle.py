"""Offline packaging contracts using disposable Git fixtures and synthetic inputs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_demo_bundle.py"
SPEC = importlib.util.spec_from_file_location("demo_bundle", SCRIPT)
BUNDLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUNDLE)


class DemoBundleTests(unittest.TestCase):
    def test_bundle_accepts_the_current_program_builder_version(self):
        from scripts import build_ees_webui as branding
        self.assertEqual(BUNDLE.BRANDING_VERSION, branding.VERSION)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="demo-bundle-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.git("init", "--quiet")
        for name in BUNDLE.GUIDES:
            self.write(name, "# Synthetic guide\n")
        self.write("agent-pack/system-prompts/assistant.md", "Synthetic instructions\n")
        self.write("agent-pack/skills/example/scripts/tool.py", "# Synthetic tool\n")
        self.commit()
        guard = patch("socket.socket.connect", side_effect=AssertionError("Network access is forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Synthetic fixture")

    def build(self, directory="output", **kwargs):
        return BUNDLE.build_bundle(self.root, self.base / directory, **kwargs)

    def contents(self, artifact):
        with zipfile.ZipFile(artifact) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    def test_clean_readonly_sources_are_unchanged_and_zip_is_reproducible(self):
        before = {name: (self.root / name).read_bytes() for name in self.git("ls-files").splitlines()}
        for name in before:
            (self.root / name).chmod(0o444)
        first, second = self.build("first"), self.build("second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "")
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content)
            self.assertEqual((self.root / name).stat().st_mode & 0o222, 0)
        contents = self.contents(first)
        manifest = json.loads(contents["manifest.json"])
        self.assertEqual(manifest["source_commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse(manifest["source_dirty"])
        self.assertIsNone(manifest["branding"])
        self.assertEqual(first.name, "EES-demo-" + manifest["source_commit"][:12] + ".zip")
        self.assertEqual({item["path"] for item in manifest["files"]}, set(contents) - {"manifest.json"})
        for item in manifest["files"]:
            self.assertEqual(item["size"], len(contents[item["path"]]))
            self.assertEqual(item["sha256"], hashlib.sha256(contents[item["path"]]).hexdigest())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertTrue(all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist()))

    def test_sensitive_runtime_untracked_and_unselected_files_are_excluded(self):
        excluded = ["agent-pack/.env", "agent-pack/.webui_secret_key", "agent-pack/private.key",
                    "agent-pack/webui.db", "agent-pack/secret.json", "agent-pack/user-pat.txt",
                    "agent-pack/credentials.md", "agent-pack/.venv/config.json",
                    "agent-pack/data/settings.json", "agent-pack/venv/activate.py",
                    "agent-pack/node_modules/example/index.js", "docs/unselected.md"]
        for name in excluded:
            self.write(name, "SYNTHETIC_EXCLUDED_VALUE")
        self.commit()
        self.write("agent-pack/skills/untracked.py", "SYNTHETIC_EXCLUDED_VALUE")
        artifact = self.build()
        contents = self.contents(artifact)
        self.assertFalse(set(excluded) & set(contents))
        self.assertNotIn("agent-pack/skills/untracked.py", contents)
        self.assertNotIn(b"SYNTHETIC_EXCLUDED_VALUE", artifact.read_bytes())
        self.assertFalse(json.loads(contents["manifest.json"])["source_dirty"])

    def test_dirty_sources_require_opt_in_and_record_actual_working_content(self):
        self.write("agent-pack/system-prompts/assistant.md", "Changed synthetic instructions\n")
        self.git("add", "agent-pack/system-prompts/assistant.md")
        for ending in (b"\n", b"\r\n"):
            with self.subTest(line_ending=ending):
                content = b"Working synthetic instructions" + ending
                (self.root / "agent-pack/system-prompts/assistant.md").write_bytes(content)
                with self.assertRaisesRegex(BUNDLE.BundleError, "Tracked sources have changes"):
                    self.build()
                self.assertFalse((self.base / "output").exists())
                contents = self.contents(self.build(directory=f"working-{len(ending)}", allow_dirty=True))
                manifest = json.loads(contents["manifest.json"])
                self.assertTrue(manifest["source_dirty"])
                self.assertEqual(manifest["source_commit"], self.git("rev-parse", "HEAD"))
                self.assertEqual(contents["agent-pack/system-prompts/assistant.md"], content)

    def test_existing_artifact_is_not_overwritten(self):
        artifact = self.build()
        before = artifact.read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(artifact.read_bytes(), before)

    def test_branding_is_optional_and_manifest_is_preserved(self):
        branding = self.base / "branding"
        branding.mkdir()
        wheel = b"Synthetic wheel bytes; not an install test"
        wheel_name = "open_webui-0.11.3+ees.9-py3-none-any.whl"
        (branding / wheel_name).write_bytes(wheel)
        manifest = {"schema_version": 1, "upstream_version": "0.11.3", "version": "0.11.3+ees.9",
                    "source": {"filename": "open_webui-0.11.3-py3-none-any.whl",
                               "sha256": "8436f9bb29c5accbdfd90d78470fcc917c882bd53f72ed88fed91b1ee97fa547"},
                    "wheel": {"filename": wheel_name, "size": len(wheel),
                              "sha256": hashlib.sha256(wheel).hexdigest()},
                    "changed_files": ["synthetic.txt"]}
        original = json.dumps(manifest, indent=2).encode()
        (branding / "manifest.json").write_bytes(original)
        (branding / ".env").write_text("SYNTHETIC_EXCLUDED_VALUE")
        contents = self.contents(self.build(branding_dir=branding))
        self.assertEqual(json.loads(contents["manifest.json"])["branding"], manifest)
        self.assertEqual(contents["branding/manifest.json"], original)
        self.assertEqual(contents["branding/" + wheel_name], wheel)
        self.assertNotIn("branding/.env", contents)
        (branding / wheel_name).write_bytes(wheel + b"changed")
        with self.assertRaisesRegex(BUNDLE.BundleError, "do not match"):
            self.build("changed-wheel", branding_dir=branding)
        (branding / wheel_name).write_bytes(wheel)
        for key, value in (("schema_version", True), ("upstream_version", "0.11.4"),
                           ("version", "0.11.3"), ("source", {}), ("wheel", {})):
            with self.subTest(key=key):
                (branding / "manifest.json").write_text(json.dumps(dict(manifest, **{key: value})))
                with self.assertRaisesRegex(BUNDLE.BundleError, "do not match"):
                    self.build("invalid-" + key, branding_dir=branding)
        (branding / "manifest.json").write_bytes(original)
        (branding / "second.whl").write_bytes(wheel)
        with self.assertRaisesRegex(BUNDLE.BundleError, "exactly one wheel"):
            self.build("ambiguous", branding_dir=branding)

    def test_tracked_symlink_cannot_import_an_external_file(self):
        outside = self.base / "outside.py"
        outside.write_text("SYNTHETIC_EXTERNAL_SECRET", encoding="utf-8")
        link = self.root / "agent-pack/linked.py"
        try:
            link.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlink creation is unavailable on this platform")
        self.commit()
        with self.assertRaisesRegex(BUNDLE.BundleError, "non-regular tracked source"):
            self.build()
        self.assertFalse((self.base / "output").exists())

    def test_source_state_change_during_build_is_rejected(self):
        original = BUNDLE.source_state(self.root)
        with patch.object(BUNDLE, "source_state", side_effect=[original, ("0" * 40, False)]):
            with self.assertRaisesRegex(BUNDLE.BundleError, "changed while building"):
                self.build()
        self.assertFalse((self.base / "output").exists())


if __name__ == "__main__":
    unittest.main()
