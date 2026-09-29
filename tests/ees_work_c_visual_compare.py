"""Preserve C-view originals and emit unscaled visual comparison evidence.

The reference is 1920x1080, including its 32px review notice. The actual
1920x1080 original is retained; alignment uses a separately rendered actual
1920x1048 viewport, never a resized or cropped product screenshot. No image
score or matching fields establish visual acceptance.

Optional contract schema: node_id, elements[{name, figma_node_id,
actual_target, rect:{x,y,width,height}, styles:{computedStyleName:value}}].
Reference rectangles are frame-local and include the notice. Actual targets
come from ees_work_c_visual_fullapp.py; raw values are retained in the report.
"""

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image


FULL_SIZE = (1920, 1080)
NOTICE_HEIGHT = 32
APP_SIZE = (1920, 1048)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_png(path, expected_size):
    data = path.read_bytes()
    with Image.open(BytesIO(data)) as source:
        if source.format != 'PNG' or source.size != expected_size:
            raise ValueError(f'{path.name}: expected PNG {expected_size}; no rescaling is permitted')
        source.load()
        image = source.convert('RGBA')
        info = {'path': str(path.resolve()), 'sha256': digest(data),
                'size': list(source.size), 'mode': source.mode, 'bytes': len(data)}
    return data, image, info


def read_json(path):
    data = path.read_bytes()
    return json.loads(data.decode('utf-8')), {'path': str(path.resolve()), 'sha256': digest(data)}


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r'-?\d+(?:\.\d+)?(?:px)?', value):
        return float(value.removesuffix('px'))
    return None


def difference(field, reference, expected, actual):
    row = {'field': field, 'reference_raw': reference, 'reference_aligned': expected,
           'actual_raw': actual}
    if expected is None or actual is None:
        row['comparison'] = 'unmeasured'
    else:
        left, right = number(expected), number(actual)
        if left is not None and right is not None:
            row['delta_actual_minus_reference'] = round(right - left, 6)
            row['comparison'] = 'equal' if right == left else 'different'
        else:
            row['comparison'] = 'equal' if expected == actual else 'different'
    return row


def compare_elements(contract, measurement):
    results = []
    for element in contract.get('elements', []):
        target = element['actual_target']
        actual = measurement['targets'].get(target)
        fields = []
        for key in ('x', 'y', 'width', 'height'):
            reference = element.get('rect', {}).get(key)
            expected = reference - NOTICE_HEIGHT if key == 'y' and reference is not None else reference
            value = actual.get('rect', {}).get(key) if actual else None
            fields.append(difference('rect.' + key, reference, expected, value))
        for key, reference in element.get('styles', {}).items():
            fields.append(difference(key, reference, reference, actual.get(key) if actual else None))
        results.append({'name': element['name'], 'figma_node_id': element.get('figma_node_id'),
                        'actual_target': target, 'actual_visible': actual.get('visible') if actual else None,
                        'reference_element': element, 'actual_element': actual, 'fields': fields})
    return results


def side_by_side(reference, actual):
    result = Image.new('RGBA', (reference.width * 2, reference.height))
    result.paste(reference, (0, 0))
    result.paste(actual, (reference.width, 0))
    return result


def create_evidence(*, reference, actual_original, actual_aligned, measurement,
                    reference_node, output, contract=None):
    reference_bytes, reference_image, reference_info = read_png(reference, FULL_SIZE)
    original_bytes, original_image, original_info = read_png(actual_original, FULL_SIZE)
    aligned_bytes, aligned_image, aligned_info = read_png(actual_aligned, APP_SIZE)
    observed, measurement_info = read_json(measurement)
    if observed.get('viewport') != {'width': 1920, 'height': 1048, 'dpr': 1}:
        raise ValueError('Actual measurements must be from the separate 1920x1048, DPR 1 render')
    if observed.get('reference_node') != reference_node:
        raise ValueError('Actual measurement reference node does not match the requested view')
    alignment = observed.get('alignment', {})
    if (alignment.get('kind') != 'app-aligned' or alignment.get('pixel_scale') != 1
            or alignment.get('css_or_dom_overrides') is not False
            or alignment.get('reference_app_origin') != {'x': 0, 'y': 32}
            or alignment.get('product_app_origin') != {'x': 0, 'y': 0}):
        raise ValueError('Actual evidence must declare unscaled app-aligned rendering without CSS/DOM overrides')
    reference_contract, contract_info, elements = None, None, []
    if contract is not None:
        reference_contract, contract_info = read_json(contract)
        if reference_contract.get('node_id') != reference_node:
            raise ValueError('Contract reference node does not match the requested view')
        elements = compare_elements(reference_contract, observed)
    # A new directory preserves every prior comparison and prevents replacement
    # of an input, including one that happens to share an output filename.
    output.mkdir(parents=True, exist_ok=False)
    raw_outputs = {'reference-original.png': reference_bytes,
                   'actual-original.png': original_bytes,
                   'actual-app.png': aligned_bytes}
    for name, content in raw_outputs.items():
        (output / name).write_bytes(content)
    reference_app = reference_image.crop((0, NOTICE_HEIGHT, *FULL_SIZE))
    derived = {'reference-app.png': reference_app,
               'side-by-side-original.png': side_by_side(reference_image, original_image),
               'side-by-side-app.png': side_by_side(reference_app, aligned_image),
               'overlay-app-50.png': Image.blend(reference_app, aligned_image, 0.5)}
    for name, image in derived.items():
        image.save(output / name)
    artifacts = {}
    for name in (*raw_outputs, *derived):
        path = output / name
        with Image.open(path) as image:
            artifacts[name] = {'sha256': digest(path.read_bytes()), 'size': list(image.size)}
    report = {
        'schema_version': 1, 'reference_node': reference_node,
        'sources': {'reference': reference_info, 'actual_original': original_info,
                    'actual_aligned': aligned_info, 'actual_measurements': measurement_info,
                    'reference_contract': contract_info},
        'alignment': {'reference_crop_xyxy': [0, 32, 1920, 1080],
                      'reference_translation_xy': [0, -32], 'actual_translation_xy': [0, 0],
                      'comparison_size': list(APP_SIZE), 'pixel_scale': 1,
                      'actual_crop': None, 'actual_render': 'separate 1920x1048 viewport',
                      'side_by_side_order': ['reference', 'actual'],
                      'masks': [], 'overlay_alpha': 0.5, 'css_or_dom_overrides': False,
                      'browser_chrome': 'not present in either capture',
                      'color_conversion': 'RGBA only for composites; source PNG bytes preserved'},
        'artifacts': artifacts, 'elements': elements,
        'reference_contract_notes': ({key: value for key, value in reference_contract.items()
                                      if key != 'elements'} if reference_contract else None),
        'actual_capture_alignment': alignment,
        'field_counts': dict(Counter(row['comparison'] for element in elements for row in element['fields'])),
        'unmapped_actual_targets': sorted(set(observed['targets']) - {e['actual_target'] for e in elements}),
        'visual_verdict': 'not_assigned_requires_visual_review',
        'limits': ['Image generation and equal fields do not establish visual PASS.',
                   'No resizing, broad mask, image similarity threshold or test CSS is used.',
                   'Only contract-mapped fields are compared; missing fields remain unmeasured.',
                   'Style strings are preserved; only numeric/px values receive numeric deltas.'],
    }
    (output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'actual-original', 'actual-aligned', 'measurement', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reference-node', required=True)
    parser.add_argument('--contract', type=Path)
    args = parser.parse_args()
    result = create_evidence(**vars(args))
    print(json.dumps({'comparison': str(args.output / 'comparison.json'),
                      'field_counts': result['field_counts'], 'visual_verdict': result['visual_verdict']}))


if __name__ == '__main__':
    main()
