"""Design mockup builder: product CSS/icon inlining and offline-page guards.

Font subsetting needs fontTools and the pinned wheel fonts, which the fixed
test environment does not install; it is replaced by a stub here so the
inlining, marker and network guards run with the standard library only.
"""

import hashlib
import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
