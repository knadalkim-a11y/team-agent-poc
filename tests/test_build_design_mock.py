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


class DesignMockBuildTests(unittest.TestCase):
    def build(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp, "mock-src.html"), Path(tmp, "mock.html")
            src.write_text(source, encoding="utf-8")
            with mock.patch.object(builder, "subset_font", return_value=(b"woff2", 3)) as subset:
                builder.build(src, out, {name: b"ttf" for name in builder.FONT_FAMILIES})
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

    def test_committed_mock_fonts_have_the_declared_woff2_format(self):
        pages = sorted((ROOT / "docs/mockups/ees-work").glob("design-mock-*.html"))
        self.assertTrue(pages, "the checked-in design mock must be covered")
        for page in pages:
            fonts = re.findall(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", page.read_text(encoding="utf-8"))
            self.assertEqual(len(fonts), len(builder.FONT_FAMILIES), page.name)
            for index, encoded in enumerate(fonts):
                with self.subTest(page=page.name, font=index):
                    data = base64.b64decode(encoded, validate=True)
                    self.assertGreaterEqual(len(data), 48)
                    self.assertEqual(data[:4], b"wOF2", "CSS says WOFF2 but the bytes use a different format")
                    self.assertEqual(struct.unpack_from(">I", data, 8)[0], len(data))

    def test_real_subset_keeps_requested_glyph_metrics_in_woff2(self):
        try:
            from fontTools.fontBuilder import FontBuilder
            from fontTools.pens.ttGlyphPen import TTGlyphPen
            from fontTools.ttLib import TTFont, woff2
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
        font.setupNameTable({"familyName": "Mock format test", "styleName": "Regular"})
        font.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        font.setupPost()
        font.setupMaxp()
        original = io.BytesIO()
        font.save(original)

        encoded, glyph_count = builder.subset_font(original.getvalue(), "A")
        self.assertEqual(encoded[:4], b"wOF2")
        decoded = TTFont(io.BytesIO(encoded))
        self.assertEqual(decoded.flavor, "woff2")
        self.assertIn(ord("A"), decoded.getBestCmap())
        self.assertNotIn(ord("B"), decoded.getBestCmap())
        self.assertEqual(decoded["hmtx"][decoded.getBestCmap()[ord("A")]], (600, 0))
        self.assertEqual(decoded["maxp"].numGlyphs, glyph_count)
        with mock.patch.object(woff2, "haveBrotli", False), mock.patch.object(woff2, "log"):
            with self.assertRaisesRegex(SystemExit, "WOFF2 encoding requires brotli"):
                builder.subset_font(original.getvalue(), "A")


if __name__ == "__main__":
    unittest.main()
