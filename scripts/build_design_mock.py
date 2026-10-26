#!/usr/bin/env python3
"""Build a self-contained design mockup page from the product's own UI files.

A design mockup (AGENTS.md "화면이 바뀌는 기능의 개발 순서") is opened on an
in-house PC without a program Apply. To keep it as close to the program as
possible it reuses, unchanged:

* branding/ees/ui/chat-theme.css and ees-work-launcher.css (tokens and shared
  component styles), with their `/_ees14/v4/*.svg` icons inlined;
* the v4 icon SVGs referenced as `v4/<name>.svg` in the mock source;
* the two fonts bundled in the pinned Open WebUI wheel, checked against
  build_ees_webui.FONT_SOURCES. Fonts are subset to the characters the page
  uses (outlines, metrics, hinting and OpenType features kept) and embedded
  as WOFF2 under the product's family names.

The output loads nothing from the network: it carries a CSP of
`default-src 'none'` and the build refuses external resource references.

Usage (fontTools and brotli are needed only for this tool):
  python scripts/build_design_mock.py SOURCE.html OUT.html --fonts-dir DIR
  python scripts/build_design_mock.py SOURCE.html OUT.html --wheel open_webui-0.11.3-py3-none-any.whl
"""

import argparse
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "branding" / "ees" / "ui"
PRODUCT_CSS = ("chat-theme.css", "ees-work-launcher.css")
FONT_FAMILIES = {"Inter-Variable.ttf": "EES Inter", "NotoSansKR-Variable.ttf": "EES Noto Sans KR"}
ICON_REF = re.compile(r"(?:/_ees14/|(?<![\w/]))v4/([0-9a-f]{5})\.svg")
EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""", re.I)
# Typographic characters the product CSS or mock text may need besides the source text.
EXTRA_CHARS = "‘’“”…·–—›‹×→←↑↓✓"


def _builder():
    spec = importlib.util.spec_from_file_location("build_ees_webui", ROOT / "scripts" / "build_ees_webui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_fonts(fonts_dir=None, wheel=None):
    """Return {file name: bytes} for the two product fonts after hash checks."""
    builder = _builder()
    fonts = {}
    if wheel:
        data = Path(wheel).read_bytes()
        if _sha256(data) != builder.SOURCE_SHA256:
            raise SystemExit(f"wheel hash differs from {builder.SOURCE_FILENAME} pinned in build_ees_webui.py")
        with ZipFile(io.BytesIO(data)) as archive:
            for name, (path, _digest) in builder.FONT_SOURCES.items():
                fonts[name] = archive.read(path)
    else:
        for name in builder.FONT_SOURCES:
            fonts[name] = (Path(fonts_dir) / name).read_bytes()
    for name, (_path, digest) in builder.FONT_SOURCES.items():
        if _sha256(fonts[name]) != digest:
            raise SystemExit(f"{name} hash differs from build_ees_webui.FONT_SOURCES")
    return fonts


def subset_font(data, text):
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise SystemExit("fontTools and brotli are required: pip install fonttools brotli") from error
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.glyph_names = False
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes={ord(char) for char in text})
    subsetter.subset(font)
    output = io.BytesIO()
    font.save(output)
    return output.getvalue(), font["maxp"].numGlyphs


def icon_data_uri(name):
    svg = (UI_DIR / "v4" / f"{name}.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


def inline_icons(text):
    return ICON_REF.sub(lambda match: icon_data_uri(match.group(1)), text)


def product_css():
    blocks, digests = [], {}
    for name in PRODUCT_CSS:
        raw = (UI_DIR / name).read_bytes()
        digests[name] = _sha256(raw)
        css = raw.decode("utf-8")
        # The product's @font-face rules point at program-relative files; the
        # same families are declared once below with the embedded subsets.
        css = re.sub(r"@font-face\s*\{[^}]*\}", "", css)
        blocks.append(f'<style data-product-css="branding/ees/ui/{name}">\n{inline_icons(css)}\n</style>')
    return "\n".join(blocks), digests


def build(source, out, fonts):
    source_text = Path(source).read_text(encoding="utf-8")
    css_html, css_digests = product_css()
    text = "".join(sorted(set(source_text + css_html + EXTRA_CHARS + "".join(map(chr, range(0x20, 0x7F))))))
    faces, report = [], []
    for name, family in FONT_FAMILIES.items():
        data, glyphs = subset_font(fonts[name], text)
        faces.append(f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{base64.b64encode(data).decode("ascii")}) format("woff2");font-style:normal;font-weight:100 900;font-display:block;}}')
        report.append(f"{name}: {glyphs} glyphs, {len(data)} bytes")
    licenses = (UI_DIR / "font-licenses.txt").read_text(encoding="utf-8").replace("</", "<\\/")
    try:
        label = Path(source).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        label = Path(source).name
    provenance = (
        "<!-- Generated by scripts/build_design_mock.py from "
        + label
        + ". Do not edit by hand. Product CSS sha256: "
        + ", ".join(f"{name} {digest}" for name, digest in css_digests.items())
        + ". Fonts: pinned Open WebUI 0.11.3 wheel files (build_ees_webui.FONT_SOURCES), subset to this page's characters. -->"
    )
    html = inline_icons(source_text)
    for marker, value in (
        ("<!--@mock:provenance-->", provenance),
        ("<!--@mock:fonts-->", "<style data-mock-fonts>" + "".join(faces) + "</style>"),
        ("<!--@mock:product-css-->", css_html),
        ("<!--@mock:font-licenses-->", f'<script type="text/plain" id="font-licenses">\n{licenses}\n</script>'),
    ):
        if html.count(marker) != 1:
            raise SystemExit(f"source must contain {marker} exactly once")
        html = html.replace(marker, value)
    checked = re.sub(r'<script type="text/plain" id="font-licenses">.*?</script>', "", html, flags=re.S)
    if "default-src 'none'" not in checked or EXTERNAL.search(checked) or ICON_REF.search(checked):
        raise SystemExit("output must keep the CSP and reference no external or unresolved resources")
    Path(out).write_text(html, encoding="utf-8", newline="\n")
    return report + [f"{Path(out).name}: {len(html.encode('utf-8'))} bytes"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source")
    parser.add_argument("out")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fonts-dir")
    group.add_argument("--wheel")
    args = parser.parse_args()
    for line in build(args.source, args.out, load_fonts(args.fonts_dir, args.wheel)):
        print(line)


if __name__ == "__main__":
    sys.exit(main())
