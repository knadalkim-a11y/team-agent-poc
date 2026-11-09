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

A mock that tries a theme the product does not have yet may opt in with
`<!--@mock:theme-fonts-->`. Its fonts then come from the npm packages in
THEME_PACKAGES, checked against their npm integrity, subset the same way and
embedded under "EES Theme" family names. IBM Plex Sans KR reserves the font
name "Plex" (SIL OFL 1.1 condition 3), so its subsets are renamed; copyright,
trademark and license records stay, and the upstream license files are
embedded with the page. Product fonts are still embedded as the fallback.

The output loads nothing from the network: it carries a CSP of
`default-src 'none'` and the build refuses external resource references.

Usage (fontTools and brotli are needed only for this tool):
  python scripts/build_design_mock.py SOURCE.html OUT.html --fonts-dir DIR
  python scripts/build_design_mock.py SOURCE.html OUT.html --wheel open_webui-0.11.3-py3-none-any.whl
  ... --theme-packages DIR   (DIR holds the THEME_PACKAGES files from `npm pack`)
"""

import argparse
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import tarfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "branding" / "ees" / "ui"
PRODUCT_CSS = ("chat-theme.css", "ees-work-launcher.css")
FONT_FAMILIES = {"Inter-Variable.ttf": "EES Inter", "NotoSansKR-Variable.ttf": "EES Noto Sans KR"}
ICON_REF = re.compile(r"(?:/_ees14/|(?<![\w/]))v4/([0-9a-f]{5})\.svg")
EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""", re.I)
# Typographic characters the product CSS or mock text may need besides the source text.
EXTRA_CHARS = "‘’“”…·–—›‹×→←↑↓✓"
THEME_MARKER = "<!--@mock:theme-fonts-->"
# `npm pack <name>@<version>` file name -> npm dist.integrity of that version.
THEME_PACKAGES = {
    "ibm-plex-sans-kr-1.1.0.tgz": "sha512-oGwlBC7BYvcvOvs7d8SoumXJwNO3rjbplteyeYI7zgQmEWI+4qLdRhI/zBUO4Ioo55YymSMiMtRPqAAPZBrJqA==",
    "fontsource-b612-5.3.0.tgz": "sha512-2AQPrSFDI9K00w/lPlgfcqve+ZPdRSCttvVUxcmv+UrnwwaKLMym+/uXmM7+dgPCVBIV9omoXUabFoyBFpc1Vg==",
}
LATIN_RANGE = "U+0030-0039,U+0041-005A,U+0061-007A"
LATIN_TEXT = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PLEX = "ibm-plex-sans-kr-1.1.0.tgz"
B612 = "fontsource-b612-5.3.0.tgz"
PLEX_DIR = "package/fonts/complete/woff2/hinted/"
# (package, member, CSS family, weight, unicode-range). B612 covers only digits and
# Latin letters so spaces and punctuation come from the Korean face.
THEME_FONTS = (
    (PLEX, PLEX_DIR + "IBMPlexSansKR-Regular.woff2", "EES Theme KR", 400, None),
    (PLEX, PLEX_DIR + "IBMPlexSansKR-Medium.woff2", "EES Theme KR", 500, None),
    (PLEX, PLEX_DIR + "IBMPlexSansKR-SemiBold.woff2", "EES Theme KR", 600, None),
    (B612, "package/files/b612-latin-400-normal.woff2", "EES Theme Latin", 400, LATIN_RANGE),
    (B612, "package/files/b612-latin-700-normal.woff2", "EES Theme Latin", 700, LATIN_RANGE),
)
THEME_LICENSES = ((PLEX, "package/LICENSE.txt"), (B612, "package/LICENSE"))
# Name records that present the font name (family, unique id, full, PostScript,
# typographic family); copyright (0), trademark (7) and license (13, 14) stay.
RENAMED_NAME_IDS = (1, 3, 4, 6, 16)
RESERVED_NAME = "Plex"
PLEX_RENAME = (("IBM Plex Sans KR", "EES Theme KR"), ("IBMPlexSansKR", "EESThemeKR"))
THEME_NOTICE = """Design mock theme fonts (not part of the EES program)
=====================================================

This page tries a theme that the product does not have. Its two theme
families are subsets of fonts published under the SIL Open Font License 1.1,
read from npm packages checked against their npm integrity:

@ibm/plex-sans-kr 1.1.0 ({plex})
  package/fonts/complete/woff2/hinted/IBMPlexSansKR-Regular.woff2, -Medium, -SemiBold
@fontsource/b612 5.3.0 ({b612})
  package/files/b612-latin-400-normal.woff2, b612-latin-700-normal.woff2

"EES Theme KR" is a Modified Version (a subset) of IBM Plex Sans KR. Its
license reserves the font name "Plex", so the subsets' name records 1, 3, 4,
6 and 16 are renamed to EES Theme KR; the copyright, trademark and license
records are kept. "EES Theme Latin" is a subset of B612 limited to digits and
Latin letters, with its names unchanged. The complete upstream license files
follow. Only their line endings are normalized to LF and trailing spaces
removed; the text is otherwise unchanged."""


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


def load_theme_packages(directory):
    """Return {(package, member): bytes} for THEME_FONTS and THEME_LICENSES."""
    members = {}
    for package, integrity in THEME_PACKAGES.items():
        data = (Path(directory) / package).read_bytes()
        if "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") != integrity:
            raise SystemExit(f"{package} differs from the npm integrity pinned in build_design_mock.py")
        wanted = {member for name, member, *_ in THEME_FONTS if name == package}
        wanted |= {member for name, member in THEME_LICENSES if name == package}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in sorted(wanted):
                members[(package, member)] = archive.extractfile(member).read()
    return members


def subset_font(data, text, rename=()):
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise SystemExit("fontTools and brotli are required: pip install fonttools brotli") from error
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.glyph_names = False
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes={ord(char) for char in text})
    subsetter.subset(font)
    if rename:
        for record in font["name"].names:
            if record.nameID in RENAMED_NAME_IDS:
                value = record.toUnicode()
                for old, new in rename:
                    value = value.replace(old, new)
                record.string = value
        if any(RESERVED_NAME in record.toUnicode() for record in font["name"].names if record.nameID in RENAMED_NAME_IDS):
            raise SystemExit(f"subset font still presents the reserved font name {RESERVED_NAME}")
    # The serializer reads TTFont.flavor; subset.Options.flavor is only a CLI
    # option and does not change the bytes produced by font.save().
    font.flavor = "woff2"
    output = io.BytesIO()
    try:
        font.save(output)
    except ImportError as error:
        raise SystemExit("WOFF2 encoding requires brotli: pip install fonttools brotli") from error
    data = output.getvalue()
    if not data.startswith(b"wOF2"):
        raise SystemExit("font subsetting did not produce a WOFF2 file")
    return data, font["maxp"].numGlyphs


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


def license_text(data):
    """Upstream license text with LF line endings and no trailing spaces (Plex ships CRLF)."""
    return "\n".join(line.rstrip() for line in data.decode("utf-8").replace("\r\n", "\n").split("\n")).strip("\n")


def font_face(family, data, weight, unicode_range=None):
    face = (f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{base64.b64encode(data).decode("ascii")}) '
            f'format("woff2");font-style:normal;font-weight:{weight};font-display:block;')
    return face + (f"unicode-range:{unicode_range};" if unicode_range else "") + "}"


def build(source, out, fonts, theme=None):
    source_text = Path(source).read_text(encoding="utf-8")
    uses_theme = THEME_MARKER in source_text
    if uses_theme and theme is None:
        raise SystemExit(f"source uses {THEME_MARKER}: pass --theme-packages DIR")
    css_html, css_digests = product_css()
    text = "".join(sorted(set(source_text + css_html + EXTRA_CHARS + "".join(map(chr, range(0x20, 0x7F))))))
    faces, report = [], []
    for name, family in FONT_FAMILIES.items():
        data, glyphs = subset_font(fonts[name], text)
        faces.append(font_face(family, data, "100 900"))
        report.append(f"{name}: {glyphs} glyphs, {len(data)} bytes")
    licenses = (UI_DIR / "font-licenses.txt").read_text(encoding="utf-8")
    theme_faces, theme_note = [], ""
    if uses_theme:
        for package, member, family, weight, unicode_range in THEME_FONTS:
            rename = PLEX_RENAME if package == PLEX else ()
            data, glyphs = subset_font(theme[(package, member)], LATIN_TEXT if unicode_range else text, rename)
            theme_faces.append(font_face(family, data, weight, unicode_range))
            report.append(f"{member.rsplit('/', 1)[1]} -> {family} {weight}: {glyphs} glyphs, {len(data)} bytes")
        notice = THEME_NOTICE.format(plex=THEME_PACKAGES[PLEX], b612=THEME_PACKAGES[B612])
        upstream = [f"{package} {member}\n{'-' * len(package + member + ' ')}\n\n{license_text(theme[(package, member)])}"
                    for package, member in THEME_LICENSES]
        licenses += "\n\n" + notice + "\n\n" + "\n\n".join(upstream)
        theme_note = (" Theme fonts: subsets of IBM Plex Sans KR 1.1.0 (renamed EES Theme KR) and B612 (EES Theme Latin)"
                      " from the npm packages pinned in THEME_PACKAGES.")
    licenses = licenses.replace("</", "<\\/")
    try:
        label = Path(source).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        label = Path(source).name
    provenance = (
        "<!-- Generated by scripts/build_design_mock.py from "
        + label
        + ". Do not edit by hand. Product CSS sha256: "
        + ", ".join(f"{name} {digest}" for name, digest in css_digests.items())
        + ". Fonts: pinned Open WebUI 0.11.3 wheel files (build_ees_webui.FONT_SOURCES), subset to this page's characters."
        + theme_note + " -->"
    )
    html = inline_icons(source_text)
    replacements = [
        ("<!--@mock:provenance-->", provenance),
        ("<!--@mock:fonts-->", "<style data-mock-fonts>" + "".join(faces) + "</style>"),
        ("<!--@mock:product-css-->", css_html),
        ("<!--@mock:font-licenses-->", f'<script type="text/plain" id="font-licenses">\n{licenses}\n</script>'),
    ]
    if uses_theme:
        replacements.append((THEME_MARKER, "<style data-mock-theme-fonts>" + "".join(theme_faces) + "</style>"))
    for marker, value in replacements:
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
    parser.add_argument("--theme-packages", help="directory holding the THEME_PACKAGES files (only for theme mocks)")
    args = parser.parse_args()
    theme = load_theme_packages(args.theme_packages) if args.theme_packages else None
    for line in build(args.source, args.out, load_fonts(args.fonts_dir, args.wheel), theme):
        print(line)


if __name__ == "__main__":
    sys.exit(main())
