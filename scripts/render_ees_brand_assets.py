"""Render the repository's vector icon; never needed by the running server.

Development only: CairoSVG 2.8.2 and Pillow 12.3.0, plus system Cairo.
The generated assets are committed so wheel packaging needs only Python stdlib.
Run from any directory with a separate development Python environment.
"""

from io import BytesIO
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "branding" / "ees" / "assets"


def main():
    import cairosvg
    from PIL import Image

    source = (ASSETS / "favicon.svg").read_bytes()
    sizes = {
        "favicon.png": 256,
        "favicon-96x96.png": 96,
        "apple-touch-icon.png": 180,
        "logo.png": 500,
        "splash.png": 256,
        "splash-dark.png": 256,
    }
    for name, size in sizes.items():
        png = cairosvg.svg2png(bytestring=source, output_width=size, output_height=size)
        (ASSETS / name).write_bytes(png)
    image = Image.open(BytesIO((ASSETS / "favicon.png").read_bytes()))
    image.save(ASSETS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("Rendered 7 assets from favicon.svg")


if __name__ == "__main__":
    main()
