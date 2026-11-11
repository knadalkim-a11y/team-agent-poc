"""Check the review bundle against captures from the completed Native suite."""
import json
import struct
import sys
from pathlib import Path


CAPTURES = (
    "operations-stage-default-1920",
    "parity-records-selected-1920",
    "parity-b2-ems-procedure-1920",
    "tools-phase1-list-1920",
    "parity-b6-models-list-1920",
    "parity-b6-model-editor-1920",
    "parity-b7-knowledge-detail-1920",
    "parity-b8-skill-editor-1920",
)


def png_size(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid PNG header in {path}")
    return struct.unpack(">II", header[16:24])


def main():
    captures, output = map(Path, sys.argv[1:])
    for stem in CAPTURES:
        size = png_size(captures / (stem + ".png"))
        if size != (1920, 1080):
            raise ValueError(f"{stem}: expected 1920x1080, got {size}")
    shell = json.loads((captures / "q1-1920x1080.json").read_text(encoding="utf-8"))
    records = json.loads((captures / "parity-records-selected-1920.json").read_text(encoding="utf-8"))
    measured = {
        "navigation": shell["sidebar"]["width"],
        "work": shell["work"]["width"],
        "chat": shell["chat"]["width"],
        "records_list": records["list"]["width"],
        "records_gap": records["detail"]["left"] - records["list"]["right"],
        "records_detail": records["detail"]["width"],
    }
    expected = dict(navigation=256, work=1104, chat=560, records_list=470, records_gap=20, records_detail=470)
    differences = {key: round(measured[key] - value, 2) for key, value in expected.items()}
    report = {"viewport": [1920, 1080], "captured_scenes": list(CAPTURES),
              "figma": expected, "product": measured, "delta_px": differences}
    (output / "measured.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Measured 8 product captures; Figma vs product CSS dimensions:", json.dumps(report["product"]))
    if any(abs(value) > 1 for value in differences.values()):
        raise SystemExit("Fixed Figma boundary differs by more than 1 CSS px: " + json.dumps(differences))


if __name__ == "__main__":
    main()
