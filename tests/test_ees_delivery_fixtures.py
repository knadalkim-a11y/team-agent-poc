"""Cache reuse must preserve pinned sources, official input and built wheel bytes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("delivery_fixtures", Path(__file__).with_name("ees_delivery_fixtures.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class DeliveryFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.repository.cleanup)
        cls.repo = Path(cls.repository.name)
        (cls.repo / "scripts").mkdir()
        (cls.repo / ".github").mkdir()
        (cls.repo / ".github" / "preserved.txt").write_text("complete old source\n", encoding="utf-8")
        cls.official = b"synthetic official wheel"
        cls.official_hash = hashlib.sha256(cls.official).hexdigest()
        # A real subprocess builder ensures a miss runs exactly the archived code.
        (cls.repo / "scripts/build_ees_webui.py").write_text(
            "import argparse,hashlib,json\nfrom pathlib import Path\n"
            "VERSION='0.11.3+ees.10'\n"
            "p=argparse.ArgumentParser();p.add_argument('--wheel');p.add_argument('--output-dir');a=p.parse_args()\n"
            "source=Path(a.wheel);out=Path(a.output_dir);out.mkdir()\n"
            "data=b'archived builder result';name='open_webui-'+VERSION+'-py3-none-any.whl'\n"
            "(out/name).write_bytes(data)\n"
            "manifest={'schema_version':1,'upstream_version':'0.11.3','version':VERSION,"
            "'source':{'filename':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},"
            "'wheel':{'filename':name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}}\n"
            "(out/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(cls.repo)], check=True)
        subprocess.run(["git", "add", "."], cwd=cls.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], cwd=cls.repo, check=True)
        cls.pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cls.repo).decode("ascii").strip()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dist = Path(self.directory.name)
        self.wheel = self.dist / "official" / fixtures.SOURCE_FILENAME
        self.wheel.parent.mkdir()
        self.wheel.write_bytes(self.official)
        self.scope = patch.multiple(fixtures, ROOT=self.repo, SOURCE_PINS={"legacy": self.pin}, SOURCE_SHA256=self.official_hash)
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def build(self):
        self.assertEqual(fixtures.prepare("legacy", self.dist, self.wheel), "prepared")
        return self.dist / "legacy-branding/open_webui-0.11.3+ees.10-py3-none-any.whl"

    def test_miss_uses_archived_builder_and_hit_preserves_exact_bytes_without_rebuild(self):
        wheel = self.build()
        before = wheel.read_bytes()
        stamp = wheel.stat().st_mtime_ns
        self.assertEqual((self.dist / "legacy-source/.github/preserved.txt").read_text(encoding="utf-8"), "complete old source\n")
        run = subprocess.run
        def only_git(command, **kwargs):
            self.assertEqual(command[0], "git", "cache hit must not rebuild/download")
            return run(command, **kwargs)
        with patch.object(fixtures.subprocess, "run", side_effect=only_git):
            self.assertEqual(fixtures.prepare("legacy", self.dist, self.wheel), "verified-cache")
        self.assertEqual(wheel.read_bytes(), before)
        self.assertEqual(wheel.stat().st_mtime_ns, stamp)

    def test_tampered_wheel_and_missing_source_are_rejected_without_repair(self):
        wheel = self.build()
        wheel.write_bytes(b"changed wheel")
        with self.assertRaisesRegex(ValueError, "file hashes or inventory"):
            fixtures.prepare("legacy", self.dist, self.wheel)
        self.assertEqual(wheel.read_bytes(), b"changed wheel")
        wheel.write_bytes(b"archived builder result")
        (self.dist / "legacy-source/.github/preserved.txt").unlink()
        with self.assertRaisesRegex(ValueError, "file hashes or inventory"):
            fixtures.verify("legacy", self.dist)

    def test_source_is_anchored_to_git_even_if_cache_inventory_is_rewritten(self):
        self.build()
        (self.dist / "legacy-source/.github/preserved.txt").write_text("modified", encoding="utf-8")
        provenance = self.dist / "legacy-provenance.json"
        saved = json.loads(provenance.read_text(encoding="utf-8"))
        saved["files"] = fixtures.inventory("legacy", self.dist)
        provenance.write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source differs from Git"):
            fixtures.verify("legacy", self.dist)

    def test_missing_manifest_and_partial_cache_do_not_silently_rebuild(self):
        (self.dist / "legacy-source").mkdir()
        with patch.object(fixtures.subprocess, "run", side_effect=AssertionError("must not replace partial cache")):
            with self.assertRaisesRegex(ValueError, "provenance"):
                fixtures.prepare("legacy", self.dist, self.wheel)

    def test_changed_source_environment_official_pin_and_helper_invalidate_key(self):
        first = fixtures.cache_key("legacy")
        with patch.object(fixtures.platform, "python_version", return_value="9.9.9"):
            self.assertNotEqual(fixtures.cache_key("legacy"), first)
        with patch.object(fixtures, "SOURCE_SHA256", "0" * 64):
            self.assertNotEqual(fixtures.cache_key("legacy"), first)
        with patch.object(fixtures, "digest", return_value="1" * 64):
            self.assertNotEqual(fixtures.cache_key("legacy"), first)
        with patch.object(fixtures, "SOURCE_PINS", {"legacy": "HEAD"}):
            self.assertNotEqual(fixtures.cache_key("legacy"), first)
        self.assertLess(len(first), 512)

    def test_stale_generation_environment_rejected_as_cache_but_preserved_for_transfer(self):
        self.build()
        expected = fixtures.verify("legacy", self.dist)
        with patch.object(fixtures.platform, "system", return_value="DifferentConsumer"), patch.object(fixtures.platform, "python_version", return_value="9.9.9"):
            with self.assertRaisesRegex(ValueError, "key inputs differ"):
                fixtures.verify("legacy", self.dist)
            with patch.object(fixtures, "git", side_effect=AssertionError("consumer has no historical Git objects")):
                self.assertEqual(fixtures.verify("legacy", self.dist, transferred=True), expected)
        (self.dist / "legacy-source/.github/preserved.txt").unlink()
        with self.assertRaisesRegex(ValueError, "file hashes or inventory"):
            fixtures.verify("legacy", self.dist, transferred=True)

    def test_rewritten_inventory_cannot_hide_manifest_wheel_hash_mismatch(self):
        wheel = self.build()
        wheel.write_bytes(b"different bytes")
        provenance = self.dist / "legacy-provenance.json"
        saved = json.loads(provenance.read_text(encoding="utf-8"))
        saved["files"] = fixtures.inventory("legacy", self.dist)
        provenance.write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "builder manifest"):
            fixtures.verify("legacy", self.dist, transferred=True)

    def test_official_cache_uses_actual_pinned_hash_not_only_saved_manifest(self):
        upstream = self.dist / "upstream"
        upstream.mkdir()
        (upstream / fixtures.SOURCE_FILENAME).write_bytes(b"not the official wheel")
        saved = {"inputs": fixtures.key_inputs("upstream"), "files": fixtures.inventory("upstream", self.dist)}
        (self.dist / "upstream-provenance.json").write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pinned official"):
            fixtures.verify("upstream", self.dist)

    def test_key_cli_writes_github_output(self):
        output = self.dist / "github-output"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}):
            self.assertEqual(fixtures.main(["--fixture", "legacy", "--key"]), 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "cache_key=" + fixtures.cache_key("legacy") + "\n")


class OfficialPinTests(unittest.TestCase):
    def test_helper_uses_the_production_builder_official_wheel_pin(self):
        from scripts import build_ees_webui
        self.assertEqual(fixtures.SOURCE_FILENAME, build_ees_webui.SOURCE_FILENAME)
        self.assertEqual(fixtures.SOURCE_SHA256, build_ees_webui.SOURCE_SHA256)
        self.assertEqual(fixtures.UPSTREAM_VERSION, build_ees_webui.UPSTREAM_VERSION)
        wheel = os.environ.get("EES_TEST_UPSTREAM_WHEEL")
        if wheel:
            fixtures.verify_official(Path(wheel))


if __name__ == "__main__":
    unittest.main()
