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
        + b'<script src="/_app/immutable/entry/start.js"></script>\n' * 49
        + b'<link rel="stylesheet" href="/static/custom.css" />\n</head>\n',
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
        "open_webui/static/custom.css": b"/* existing user style stays intact */\n",
        "open_webui/frontend/static/custom.css": b"/* original frontend style stays intact */\n",
    }
    for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
        for name in builder.ASSET_NAMES:
            members[prefix + name] = b"old artwork " + name.encode()
    members["open_webui/frontend/favicon.png"] = b"old favicon"
    for name, (origin, _) in builder.FONT_SOURCES.items():
        members[origin] = b"unchanged upstream font " + name.encode()
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
        self.ui = self.root / "ui"
        self.ui.mkdir()
        for name in builder.UI_FILES:
            (self.ui / name).write_bytes(b"reviewed UI asset " + name.encode())
        self.members = fixture_members()
        self.write_fixture()

    def write_fixture(self):
        with ZipFile(self.wheel, "w") as archive:
            for name, content in self.members.items():
                archive.writestr(name, content)
        self.source_hash = builder.sha256_file(self.wheel)

    def build(self, directory="release"):
        fonts = {name: (origin, hashlib.sha256(b"unchanged upstream font " + name.encode()).hexdigest())
                 for name, (origin, _) in builder.FONT_SOURCES.items()}
        with mock.patch.object(builder, "SOURCE_SHA256", self.source_hash), mock.patch.object(builder, "FONT_SOURCES", fonts):
            return builder.build(self.wheel, self.root / directory, self.assets, self.ui)

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
            self.assertEqual(len(built.namelist()), len(self.members) + len(builder.THEME_FILES))
            for name, original in self.members.items():
                target = builder.target_name(name)
                if target not in manifest["changed_files"]:
                    self.assertEqual(built.read(target), original, name)
            self.assertEqual(built.read(builder.TARGET_INFO + "licenses/LICENSE"), LICENSE)
            self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                             self.members[builder.SOURCE_INFO + "METADATA"].replace(b"Version: 0.11.3\n", b"Version: 0.11.3+ees.4\n"))
            self.assertEqual(built.read("open_webui/env.py").count(NOTICE), 2)
            self.assertNotIn(b"WEBUI_NAME +=", built.read("open_webui/env.py"))
            self.assertIn(b"EES Portal", built.read("open_webui/frontend/index.html"))
            self.assertNotIn(b"/_app/", built.read("open_webui/frontend/index.html"))
            index = built.read("open_webui/frontend/index.html")
            self.assertEqual(index.count(builder.THEME_LINK), 1)
            self.assertLess(index.index(b"/static/custom.css"), index.index(builder.THEME_LINK))
            self.assertLess(index.index(builder.THEME_LINK), index.index(b"</head>"))
            for name, relative in builder.UI_FILES.items():
                self.assertEqual(built.read(builder.TARGET_APP + relative), (self.ui / name).read_bytes())
            for name, (origin, _) in builder.FONT_SOURCES.items():
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/" + name), self.members[origin])
            runtime = built.read(builder.TARGET_APP + "immutable/chunks/DKj2ZiCb.js")
            self.assertIn(b"/_ees4/version.json", runtime)
            self.assertEqual(json.loads(built.read(builder.TARGET_APP + "version.json"))["version"], builder.VERSION)
            for prefix in ("open_webui/static/", "open_webui/frontend/static/"):
                for name in builder.ASSET_NAMES:
                    self.assertEqual(built.read(prefix + name), (self.assets / name).read_bytes())

    def test_wrong_source_hash_fails_without_output(self):
        self.wheel.write_bytes(self.wheel.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "pinned official"):
            self.build()
        self.assertFalse((self.root / "release").exists())

    def test_portal_name_migrates_registered_assistant_and_preserves_custom_name(self):
        self.build()
        with ZipFile(self.root / "release" / builder.WHEEL_FILENAME) as built:
            synthetic_env = built.read("open_webui/env.py")
        for registered, expected in ((None, "EES Portal"), ("EES Assistant", "EES Portal"),
                                     ("EES Portal", "EES Portal"), ("Team Custom", "Team Custom")):
            with self.subTest(registered=registered):
                environment = {} if registered is None else {"WEBUI_NAME": registered}
                with mock.patch.dict(os.environ, environment, clear=True):
                    namespace = {"os": os}
                    exec(synthetic_env, namespace)
                    self.assertEqual(namespace["WEBUI_NAME"], expected)
                    self.assertEqual(dict(os.environ), environment)

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

    def test_incomplete_theme_changed_font_and_target_collision_fail_before_writing(self):
        cases = (("css", "EES UI asset"), ("license", "EES UI asset"),
                 ("font", "font hash differs"), ("missing-font", "Missing pinned upstream font"),
                 ("collision", "already contains an EES UI target"))
        for mode, error in cases:
            with self.subTest(mode=mode):
                self.setUp()
                origin = next(iter(builder.FONT_SOURCES.values()))[0]
                if mode in {"css", "license"}:
                    (self.ui / ("chat-theme.css" if mode == "css" else "font-licenses.txt")).unlink()
                elif mode == "font":
                    self.members[origin] += b"changed"
                elif mode == "missing-font":
                    del self.members[origin]
                else:
                    self.members[builder.SOURCE_APP + "chat-theme.css"] = b"unexpected upstream target"
                self.write_fixture()
                with self.assertRaisesRegex(ValueError, error):
                    self.build()
                self.assertFalse((self.root / "release").exists())


@unittest.skipUnless(os.environ.get("EES_TEST_UPSTREAM_WHEEL"), "Set EES_TEST_UPSTREAM_WHEEL for the offline official wheel audit.")
class OfficialWheelTests(unittest.TestCase):
    def test_real_pinned_wheel_patches_records_and_unrelated_content(self):
        source_path = Path(os.environ["EES_TEST_UPSTREAM_WHEEL"])
        with tempfile.TemporaryDirectory() as temporary:
            manifest = builder.build(source_path, temporary)
            built_path = Path(temporary) / builder.WHEEL_FILENAME
            assert_record(self, built_path)
            with ZipFile(source_path) as source, ZipFile(built_path) as built:
                self.assertEqual(len(source.namelist()) + len(builder.THEME_FILES), len(built.namelist()))
                changed = set(manifest["changed_files"])
                for name in source.namelist():
                    target = builder.target_name(name)
                    if target not in changed:
                        self.assertEqual(built.read(target), source.read(name), name)
                metadata = source.read(builder.SOURCE_INFO + "METADATA")
                self.assertEqual(built.read(builder.TARGET_INFO + "METADATA"),
                                 metadata.replace(b"\nVersion: 0.11.3\n", b"\nVersion: 0.11.3+ees.4\n"))
                for filename, (origin, expected) in builder.FONT_SOURCES.items():
                    copied = built.read(builder.TARGET_APP + "fonts/" + filename)
                    self.assertEqual(copied, source.read(origin))
                    self.assertEqual(hashlib.sha256(copied).hexdigest(), expected)
                self.assertEqual(built.read(builder.TARGET_APP + "chat-theme.css"),
                                 (builder.UI_DIR / "chat-theme.css").read_bytes())
                self.assertEqual(built.read(builder.TARGET_APP + "fonts/LICENSE.txt"),
                                 (builder.UI_DIR / "font-licenses.txt").read_bytes())
                for name in ("open_webui/env.py", "open_webui/frontend/index.html"):
                    self.assertEqual(source.read(name).count(b"LICENSE"), built.read(name).count(b"LICENSE"))


if __name__ == "__main__":
    unittest.main()
