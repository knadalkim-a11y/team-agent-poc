"""Offline release integrity tests; real upstream wheel check is opt-in.

Set EES_TEST_UPSTREAM_WHEEL to the verified official wheel path to additionally
build and audit that wheel. Tests never install or import Open WebUI.
"""

import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ees_branding_build", ROOT / "scripts" / "build_ees_webui.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

NOTICE = b"# LICENSE: Open WebUI branding is governed by the bundled license.\n"
LICENSE = b"Synthetic license fixture; copyright and branding conditions must survive.\n"


def fixture_members():
    app = "open_webui/frontend/_app/"
    info = "open_webui-0.11.3.dist-info/"
    members = {
        "open_webui/env.py": NOTICE + b"WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
        b"if WEBUI_NAME != 'Open WebUI':\n    WEBUI_NAME += ' (Open WebUI)'\n" + NOTICE,
        "open_webui/frontend/index.html": b"<!-- Open WebUI license notice -->\n<title>Open WebUI</title>\n"
        + b'<script src="/_app/immutable/entry/start.js"></script>\n' * 49,
        app + "immutable/chunks/CHq18Uto.js": b'const ca="Open WebUI",other="Open WebUI documentation";',
        app + "immutable/nodes/0.CvnwnD8l.js": b'new Notification(`${title} / Open WebUI`);' * 3,
        app + "immutable/nodes/26.Ck8JdNW5.js": b'document.title=`${channel} / Open WebUI`;' * 2,
        app + "immutable/chunks/DKj2ZiCb.js": b'const an="0.11.3";fetch(`${base}/_app/version.json`);',
        app + "version.json": b'{"version":"0.11.3"}',
        app + "immutable/entry/start.js": b'import "../chunks/CHq18Uto.js";\n//# sourceMappingURL=start.js.map',
        app + "immutable/entry/start.js.map": b'{"file":"_app/immutable/entry/start.js","sourcesContent":["Open WebUI"]}',
        info + "METADATA": b"Metadata-Version: 2.4\nName: open-webui\nVersion: 0.11.3\n"
        b"Requires-Dist: example==1.2.3; python_version >= '3.11'\nLicense-File: LICENSE\n\nOpen WebUI original description\n",
        info + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        info + "RECORD": b"original fixture record\n",
        info + "licenses/LICENSE": LICENSE,
        "open_webui/static/BRANDING.md": NOTICE,
        "open_webui/backend_unrelated.py": b"unchanged_application = 'Open WebUI'\n",
    }
    for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
        for name in builder.ASSET_NAMES:
            members[prefix + name] = b"old artwork " + name.encode()
    members["open_webui/frontend/favicon.png"] = b"old favicon"
    return members


def assert_record(test, wheel):
    with ZipFile(wheel) as archive:
        record_path = builder.TARGET_INFO + "RECORD"
        rows = list(csv.reader(io.StringIO(archive.read(record_path).decode())))
        test.assertEqual(len(rows), len(archive.namelist()))
        test.assertEqual({row[0] for row in rows}, set(archive.namelist()))
        for path, digest, size in rows:
            if path == record_path:
                test.assertEqual((digest, size), ("", ""))
                continue
            content = archive.read(path)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            test.assertEqual(digest, "sha256=" + encoded, path)
            test.assertEqual(int(size), len(content), path)


class BrandingBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.wheel = self.root / builder.SOURCE_FILENAME
        self.assets = self.root / "assets"
        self.assets.mkdir()
        for name in builder.ASSET_NAMES:
            (self.assets / name).write_bytes(b"EES artwork " + name.encode())
        self.members = fixture_members()
        self.write_fixture()

    def write_fixture(self):
        with ZipFile(self.wheel, "w") as archive:
            for name, content in self.members.items():
                archive.writestr(name, content)
        self.source_hash = builder.sha256_file(self.wheel)

    def build(self, directory="release"):
        with mock.patch.object(builder, "SOURCE_SHA256", self.source_hash):
            return builder.build(self.wheel, self.root / directory, self.assets)

    def test_reproducible_wheel_manifest_and_record_preserve_original(self):
        first = self.build("first")
        second = self.build("second")
        self.assertEqual(first, second)
        self.assertEqual(builder.sha256_file(self.wheel), self.source_hash)
        for filename in (builder.WHEEL_FILENAME, "manifest.json"):
            self.assertEqual((self.root / "first" / filename).read_bytes(), (self.root / "second" / filename).read_bytes())
        assert_record(self, self.root / "first" / builder.WHEEL_FILENAME)
        self.assertEqual(first["source"]["sha256"], self.source_hash)
        self.assertEqual(first["wheel"]["sha256"], builder.sha256_file(self.root / "first" / builder.WHEEL_FILENAME))

    def test_only_reviewed_content_changes_and_frontend_cache_namespace_moves(self):
        manifest = self.build()
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            self.assertFalse(any(name.startswith(builder.SOURCE_APP) for name in built.namelist()))
            self.assertEqual(len(built.namelist()), len(self.members))
            for name, original in self.members.items():
                target = builder.target_name(name)
                if target not in manifest["changed_files"]:
                    self.assertEqual(built.read(target), original, name)
            self.assertEqual(built.read(builder.TARGET_INFO + "licenses/LICENSE"), LICENSE)
            self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                             self.members[builder.SOURCE_INFO + "METADATA"].replace(b"Version: 0.11.3\n", b"Version: 0.11.3+ees.1\n"))
            self.assertEqual(built.read("open_webui/env.py").count(NOTICE), 2)
            self.assertNotIn(b"WEBUI_NAME +=", built.read("open_webui/env.py"))
            self.assertIn(b"EES Assistant", built.read("open_webui/frontend/index.html"))
            self.assertNotIn(b"/_app/", built.read("open_webui/frontend/index.html"))
            runtime = built.read(builder.TARGET_APP + "immutable/chunks/DKj2ZiCb.js")
            self.assertIn(b"/_ees1/version.json", runtime)
            self.assertEqual(json.loads(built.read(builder.TARGET_APP + "version.json"))["version"], builder.VERSION)
            for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
                for name in builder.ASSET_NAMES:
                    self.assertEqual(built.read(prefix + name), (self.assets / name).read_bytes())

    def test_wrong_source_hash_fails_without_output(self):
        self.wheel.write_bytes(self.wheel.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "pinned official"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_patch_drift_fails_before_writing(self):
        self.members["open_webui/env.py"] += self.members["open_webui/env.py"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Patch precondition failed"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_missing_asset_or_wheel_entry_fails_before_writing(self):
        (self.assets / "favicon.svg").unlink()
        with self.assertRaisesRegex(ValueError, "Missing or empty branding asset"):
            self.build()
        self.assertFalse((self.root / "release").exists())
        del self.members[builder.SOURCE_INFO + "WHEEL"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "Missing wheel entries"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_output_collision_never_overwrites_existing_release(self):
        release = self.root / "release"
        release.mkdir()
        for filename in (builder.WHEEL_FILENAME, "manifest.json"):
            with self.subTest(filename=filename):
                path = release / filename
                path.write_bytes(b"previous release")
                with self.assertRaisesRegex(ValueError, "Output already exists"):
                    self.build()
                self.assertEqual(path.read_bytes(), b"previous release")
                self.assertEqual(list(release.iterdir()), [path])
                path.unlink()


@unittest.skipUnless(os.environ.get("EES_TEST_UPSTREAM_WHEEL"), "Set EES_TEST_UPSTREAM_WHEEL for the offline official wheel audit.")
class OfficialWheelTests(unittest.TestCase):
    def test_real_pinned_wheel_patches_records_and_unrelated_content(self):
        source_path = Path(os.environ["EES_TEST_UPSTREAM_WHEEL"])
        with tempfile.TemporaryDirectory() as temporary:
            manifest = builder.build(source_path, temporary)
            built_path = Path(temporary) / builder.WHEEL_FILENAME
            assert_record(self, built_path)
            with ZipFile(source_path) as source, ZipFile(built_path) as built:
                self.assertEqual(len(source.namelist()), len(built.namelist()))
                changed = set(manifest["changed_files"])
                for name in source.namelist():
                    target = builder.target_name(name)
                    if target not in changed:
                        self.assertEqual(built.read(target), source.read(name), name)
                metadata = source.read(builder.SOURCE_INFO + "METADATA")
                self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                                 metadata.replace(b"\nVersion: 0.11.3\n", b"\nVersion: 0.11.3+ees.1\n"))
                for name in ("open_webui/env.py", "open_webui/frontend/index.html"):
                    self.assertEqual(source.read(name).count(b"LICENSE"), built.read(name).count(b"LICENSE"))


if __name__ == "__main__":
    unittest.main()
