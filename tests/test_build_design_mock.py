"""Design mockup builder: product CSS/icon inlining and offline-page guards.

The offline-page guards and committed font-format check run with the standard
library. An optional synthetic-font round trip verifies real WOFF2 encoding
when fontTools and Brotli are available, without downloading a product font.
"""

import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import struct
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_design_mock", ROOT / "scripts" / "build_design_mock.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

SOURCE = (
    "<!doctype html><html lang=\"ko\"><head>"
    "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data:\">"
    "<!--@mock:provenance--><!--@mock:fonts--><!--@mock:product-css--></head>"
    "<body><img class=\"ew-icon\" src=\"v4/1c98e.svg\" alt=\"\"><p>판정 선택</p>"
    "<!--@mock:font-licenses--></body></html>"
)


THEME = {(package, member): b"woff2 theme" for package, member, *_ in builder.THEME_FONTS}
THEME.update({(package, member): f"{package} license </script> text \r\nsecond line\t\r\n".encode("utf-8")
              for package, member in builder.THEME_LICENSES})


class DesignMockBuildTests(unittest.TestCase):
    def build(self, source, theme=None):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp, "mock-src.html"), Path(tmp, "mock.html")
            src.write_text(source, encoding="utf-8")
            with mock.patch.object(builder, "subset_font", return_value=(b"woff2", 3)) as subset:
                builder.build(src, out, {name: b"ttf" for name in builder.FONT_FAMILIES}, theme)
            return out.read_text(encoding="utf-8"), subset

    def test_inlines_product_css_icons_and_fonts_without_network_references(self):
        html, subset = self.build(SOURCE)
        self.assertNotIn("v4/1c98e.svg", html)
        self.assertNotIn("/_ees14/v4/", html)
        self.assertIn('src="data:image/svg+xml;base64,', html)
        for name in builder.PRODUCT_CSS:
            digest = hashlib.sha256((builder.UI_DIR / name).read_bytes()).hexdigest()
            self.assertIn(f'data-product-css="branding/ees/ui/{name}"', html)
            self.assertIn(f"{name} {digest}", html)
        self.assertNotIn("./fonts/", html)
        self.assertEqual(html.count("@font-face"), 2)
        self.assertIn('font-family:"EES Noto Sans KR"', html)
        self.assertIn('font-family:"EES Inter"', html)
        self.assertIn('id="font-licenses"', html)
        self.assertNotIn("<!--@mock:", html)
        self.assertEqual(subset.call_count, 2)
        self.assertTrue(all("판" in call.args[1] and "›" in call.args[1] for call in subset.call_args_list))

    def test_refuses_external_resources_missing_csp_and_unbalanced_markers(self):
        for source in (
            SOURCE.replace("<p>", '<link rel="stylesheet" href="https://example.com/a.css"><p>'),
            SOURCE.replace("<p>", '<img src="//example.com/a.png"><p>'),
            SOURCE.replace("default-src 'none'", "default-src 'self'"),
            SOURCE.replace("<!--@mock:fonts-->", ""),
            SOURCE.replace("<!--@mock:fonts-->", "<!--@mock:fonts--><!--@mock:fonts-->"),
            SOURCE.replace("v4/1c98e.svg", "v4/00000.svg"),
        ):
            with self.subTest(source=source[-120:]), self.assertRaises((SystemExit, FileNotFoundError)):
                self.build(source)

    def test_font_inputs_must_match_the_pinned_wheel_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in builder.FONT_FAMILIES:
                Path(tmp, name).write_bytes(b"not the pinned font")
            with self.assertRaises(SystemExit):
                builder.load_fonts(fonts_dir=tmp)

    def test_theme_fonts_are_opt_in_scoped_and_carry_their_licenses(self):
        source = SOURCE.replace("<!--@mock:fonts-->", "<!--@mock:fonts-->" + builder.THEME_MARKER)
        with self.assertRaises(SystemExit):
            self.build(source)
        html, subset = self.build(source, THEME)
        faces = re.findall(r"@font-face\s*\{[^}]*\}", html)
        self.assertEqual(len(faces), len(builder.FONT_FAMILIES) + len(builder.THEME_FONTS))
        latin = [face for face in faces if 'font-family:"EES Theme Latin"' in face]
        self.assertEqual(len(latin), 2)
        self.assertTrue(all(f"unicode-range:{builder.LATIN_RANGE};" in face for face in latin))
        self.assertEqual(sum('font-family:"EES Theme KR"' in face for face in faces), 3)
        self.assertNotIn("Plex", "".join(re.findall(r'font-family:"([^"]+)"', html)))
        self.assertNotIn("<!--@mock:", html)
        licenses = re.search(r'<script type="text/plain" id="font-licenses">(.*?)</script>', html, re.S).group(1)
        self.assertIn("Design mock theme fonts", licenses)
        self.assertIn(builder.THEME_PACKAGES[builder.PLEX], licenses)
        for package, _member in builder.THEME_LICENSES:
            # CRLF and trailing spaces are normalized so the page stays clean for `git diff --check`.
            self.assertIn(f"{package} license <\\/script> text\nsecond line\n", licenses)
        self.assertNotIn("\r", licenses)
        self.assertFalse([line for line in licenses.split("\n") if line != line.rstrip()])
        self.assertIn("Theme fonts: subsets of IBM Plex Sans KR", html)
        calls = subset.call_args_list[len(builder.FONT_FAMILIES):]
        self.assertEqual([call.args[2] for call in calls], [builder.PLEX_RENAME] * 3 + [()] * 2)
        self.assertEqual([call.args[1] for call in calls[3:]], [builder.LATIN_TEXT] * 2)
        # A page without the marker does not need or embed the theme fonts.
        html, _subset = self.build(SOURCE, THEME)
        self.assertEqual(html.count("@font-face"), len(builder.FONT_FAMILIES))
        self.assertNotIn("Design mock theme fonts", html)

    def test_theme_packages_must_match_the_pinned_npm_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            for package in builder.THEME_PACKAGES:
                with tarfile.open(Path(tmp, package), "w:gz") as archive:
                    info = tarfile.TarInfo("package/LICENSE")
                    info.size = 4
                    archive.addfile(info, io.BytesIO(b"fake"))
            with self.assertRaisesRegex(SystemExit, "npm integrity"):
                builder.load_theme_packages(tmp)

    def assert_committed_mock_fonts(self, pages):
        pages = sorted(pages)
        self.assertTrue(pages, "the checked-in design mock must be covered")
        theme_faces = [(family, str(weight), unicode_range) for _p, _m, family, weight, unicode_range in builder.THEME_FONTS]
        for page in pages:
            content = page.read_bytes()
            expected_formats = ["woff2"] * len(builder.FONT_FAMILIES)
            if page.name == "design-mock-08-workspace-authoring.html":
                # This approved HTML12 was imported byte-for-byte, not generated
                # by this builder: Inter is WOFF2 and Noto Sans KR is WOFF.
                # Pin that exception without weakening the generated pages'
                # two-WOFF2 contract or rewriting the accepted visual reference.
                # Git may check this text file out as CRLF on Windows. Compare
                # its canonical LF content; do not normalize any other bytes.
                self.assertEqual(hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest(),
                                 "d2aec2a3cf61f09ceb3915c778ef77b5a07b559b9fb57f545eb16cb11973079e")
                expected_formats = ["woff2", "woff"]
            all_faces = re.findall(r"@font-face\s*\{[^}]*\}", content.decode("utf-8"))
            faces = [face for face in all_faces if 'font-family:"EES Theme ' not in face]
            themed = [face for face in all_faces if 'font-family:"EES Theme ' in face]
            self.assertEqual(len(faces), len(builder.FONT_FAMILIES), page.name)
            if themed:
                # A theme mock embeds exactly the pinned theme faces, also as WOFF2.
                found = [(re.search(r'font-family:"([^"]+)"', face).group(1), re.search(r"font-weight:([^;]+);", face).group(1),
                          (re.search(r"unicode-range:([^;]+);", face) or [None, None])[1]) for face in themed]
                self.assertEqual(found, theme_faces, page.name)
                faces += themed
                expected_formats += ["woff2"] * len(themed)
            families = list(builder.FONT_FAMILIES.values()) + [family for family, *_ in theme_faces[:len(themed)]]
            for index, (face, family, expected) in enumerate(zip(faces, families, expected_formats)):
                with self.subTest(page=page.name, font=index):
                    self.assertIn(f'font-family:"{family}"', face)
                    self.assertIn(f'format("{expected}")', face)
                    fonts = re.findall(r"data:font/(woff2?);base64,([A-Za-z0-9+/=]+)", face)
                    self.assertEqual(len(fonts), 1)
                    declared, encoded = fonts[0]
                    self.assertEqual(declared, expected)
                    data = base64.b64decode(encoded, validate=True)
                    self.assertGreaterEqual(len(data), 48 if expected == "woff2" else 44)
                    self.assertEqual(data[:4], {"woff2": b"wOF2", "woff": b"wOFF"}[expected],
                                     "CSS font format and embedded bytes differ")
                    self.assertEqual(struct.unpack_from(">I", data, 8)[0], len(data))

    def test_committed_mock_fonts_have_the_declared_woff2_format(self):
        self.assert_committed_mock_fonts((ROOT / "docs/mockups/ees-work").glob("design-mock-*.html"))

    def test_frozen_mock_accepts_checkout_line_endings_but_rejects_content_changes(self):
        name = "design-mock-08-workspace-authoring.html"
        canonical = (ROOT / "docs/mockups/ees-work" / name).read_bytes().replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp, name)
            for content in (canonical, canonical.replace(b"\n", b"\r\n")):
                page.write_bytes(content)
                self.assert_committed_mock_fonts([page])
            # A visible content change must still invalidate the frozen source,
            # even when checkout line endings have also changed.
            changed = canonical.replace(b"<title>", b"<title>changed ", 1)
            self.assertNotEqual(changed, canonical)
            page.write_bytes(changed.replace(b"\n", b"\r\n"))
            with self.assertRaises(AssertionError):
                self.assert_committed_mock_fonts([page])

    def synthetic_font(self, names):
        try:
            from fontTools.fontBuilder import FontBuilder
            from fontTools.pens.ttGlyphPen import TTGlyphPen
            from fontTools.ttLib import woff2
        except ImportError:
            self.skipTest("real font-format round trip requires fontTools")
        if not woff2.haveBrotli:
            self.skipTest("real font-format round trip requires Brotli")
        font = FontBuilder(1000, isTTF=True)
        font.setupGlyphOrder([".notdef", "A", "B"])
        font.setupCharacterMap({ord("A"): "A", ord("B"): "B"})
        glyphs = {}
        for name in [".notdef", "A", "B"]:
            pen = TTGlyphPen(None)
            pen.moveTo((0, 0)); pen.lineTo((300, 0)); pen.lineTo((150, 700)); pen.closePath()
            glyphs[name] = pen.glyph()
        font.setupGlyf(glyphs)
        font.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
        font.setupHorizontalHeader(ascent=800, descent=-200)
        font.setupNameTable(names)
        font.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        font.setupPost()
        font.setupMaxp()
        original = io.BytesIO()
        font.save(original)
        return original.getvalue()

    def test_real_subset_renames_the_reserved_font_name_but_keeps_notices(self):
        data = self.synthetic_font({
            "copyright": "Copyright 2018 IBM Corp. with Reserved Font Name Plex", "familyName": "IBM Plex Sans KR",
            "styleName": "Regular", "uniqueFontIdentifier": "IBM;IBMPlexSansKR;1.003", "fullName": "IBM Plex Sans KR",
            "psName": "IBMPlexSansKR", "trademark": "IBM Plex is a trademark of IBM Corp", "typographicFamily": "IBM Plex Sans KR"})
        from fontTools.ttLib import TTFont
        encoded, _glyphs = builder.subset_font(data, "A", builder.PLEX_RENAME)
        names = {record.nameID: record.toUnicode() for record in TTFont(io.BytesIO(encoded))["name"].names}
        self.assertEqual([names[name_id] for name_id in (1, 3, 4, 6, 16)],
                         ["EES Theme KR", "IBM;EESThemeKR;1.003", "EES Theme KR", "EESThemeKR", "EES Theme KR"])
        self.assertIn("Plex", names[0])
        self.assertIn("Plex", names[7])
        with self.assertRaisesRegex(SystemExit, "reserved font name"):
            builder.subset_font(data, "A", (("Unrelated", "Name"),))

    def test_real_subset_keeps_requested_glyph_metrics_in_woff2(self):
        original = self.synthetic_font({"familyName": "Mock format test", "styleName": "Regular"})
        from fontTools.ttLib import TTFont, woff2

        encoded, glyph_count = builder.subset_font(original, "A")
        self.assertEqual(encoded[:4], b"wOF2")
        decoded = TTFont(io.BytesIO(encoded))
        self.assertEqual(decoded.flavor, "woff2")
        self.assertIn(ord("A"), decoded.getBestCmap())
        self.assertNotIn(ord("B"), decoded.getBestCmap())
        self.assertEqual(decoded["hmtx"][decoded.getBestCmap()[ord("A")]], (600, 0))
        self.assertEqual(decoded["maxp"].numGlyphs, glyph_count)
        with mock.patch.object(woff2, "haveBrotli", False), mock.patch.object(woff2, "log"):
            with self.assertRaisesRegex(SystemExit, "WOFF2 encoding requires brotli"):
                builder.subset_font(original, "A")


if __name__ == "__main__":
    unittest.main()
