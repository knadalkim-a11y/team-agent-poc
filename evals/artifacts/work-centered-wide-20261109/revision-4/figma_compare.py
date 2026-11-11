"""Compare the Figma frames of the revision-4 review with renders of the HTML mock (figma_compare_render.cjs).

Usage: python figma_compare.py <mock render dir> <figma capture dir> <report.json>

For each screen it reports, per region, the share of pixels whose luminance differs by more than 48 (glyph
rendering differs between Chromium and Figma, so this is never 0) and the rows/columns of structural lines
(long runs of non-white pixels: borders, dividers, selected rows) in both images. Equal line positions mean
the boxes sit on the same pixels. Requires Pillow.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

FIGMA = {
    'W1': 'figma-r4-w1-run-summary.png',
    'W2': 'figma-r4-w2-stage.png',
    'W3': 'figma-r4-w3-task-chat-open.png',
    'W4': 'figma-r4-w4-task-chat-collapsed.png',
    'W5': 'figma-r4-w5-procedure-authoring.png',
}
OPEN = {'nav': (0, 256), 'tree': (288, 628), 'detail': (628, 1328), 'chat': (1360, 1920)}
REGIONS = {'W1': OPEN, 'W2': OPEN, 'W3': OPEN, 'W5': OPEN,
           'W4': {'nav': (0, 256), 'tree': (288, 648), 'evidence': (648, 1448), 'verdict': (1448, 1888)}}


def lines(image, x0, x1, vertical=False):
    pixels, (width, height) = image.load(), image.size
    found = []
    outer, inner = (range(x0, x1), range(height)) if vertical else (range(height), range(x0, x1))
    need = height * 0.5 if vertical else (x1 - x0) * 0.5
    for a in outer:
        run = best = 0
        for b in inner:
            value = pixels[a, b] if vertical else pixels[b, a]
            run = run + 1 if value < 245 else 0
            best = max(best, run)
        if best >= need:
            found.append(a)
    return found


def compare(mock_path, figma_path, regions):
    mock, figma = Image.open(mock_path).convert('L'), Image.open(figma_path).convert('L')
    if mock.size != figma.size:
        raise SystemExit(f'size differs: {mock_path} {mock.size} / {figma_path} {figma.size}')
    diff = ImageChops.difference(mock, figma).load()
    height = mock.size[1]
    result = {'regions': {}, 'vertical_lines': {'mock': lines(mock, 0, mock.size[0], True),
                                                'figma': lines(figma, 0, figma.size[0], True)}}
    for name, (x0, x1) in regions.items():
        changed = sum(1 for x in range(x0, x1) for y in range(height) if diff[x, y] > 48)
        mock_rows, figma_rows = lines(mock, x0 + 8, x1 - 8), lines(figma, x0 + 8, x1 - 8)
        result['regions'][name] = {'differing_pixels_percent': round(changed / ((x1 - x0) * height) * 100, 2),
                                   'horizontal_lines_equal': mock_rows == figma_rows,
                                   'horizontal_lines': mock_rows if mock_rows == figma_rows else {'mock': mock_rows, 'figma': figma_rows}}
    result['vertical_lines_equal'] = result['vertical_lines']['mock'] == result['vertical_lines']['figma']
    return result


def main():
    mock_dir, figma_dir, report = (Path(p) for p in sys.argv[1:4])
    screens = {no: compare(mock_dir / f'mock-{no}.png', figma_dir / name, REGIONS[no]) for no, name in FIGMA.items()}
    passed = all(s['vertical_lines_equal'] and all(r['horizontal_lines_equal'] for r in s['regions'].values())
                 for s in screens.values())
    report.write_text(json.dumps({'structural_lines_equal': passed, 'threshold': 48, 'screens': screens},
                                 ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('structural lines equal on all screens:', passed)
    for no, s in screens.items():
        print(no, {k: v['differing_pixels_percent'] for k, v in s['regions'].items()})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
