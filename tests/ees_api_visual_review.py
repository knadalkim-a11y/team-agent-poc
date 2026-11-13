"""Pair six pinned v11 frames with unscaled product captures from the Native suite."""
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import struct
import sys


SCENES = {
    'tools-list': ('서비스별 API 목록', 'c15edb06aa4db04591221c4b0c7f57ffee0030254c73b3737dfbfb6aea08ce4d'),
    'tools-create-empty': ('API 명세 등록 · 빈 양식', '46de874bcc836031243c0ff94b2430bdb79ab552de64a7e6f7b0b5358590ae35'),
    'tools-create': ('API 명세 등록 · 작성 중', '5d2774366b77d64aff72e59e0a4bf266f11bd4a077067d2d340c7cada26ed028'),
    'tools-edit': ('API 명세 편집', 'e4b5e07a07ddbfcd7dae3b5377b043c47d90c7aeec7a941ca39aeaf455b84af5'),
    'task-connection': ('작업 연결 전', 'a3c8cfa3beab78cc4c29eeb09035be3f3c66cba8c9ac2b5d4e36a6cef00fd39a'),
    'task-mapped': ('작업 연결 및 결과 전달 설정 후', 'b66b7bc5868d27d178e517c9ac8476f632f611f8bdd1b1f78fde379cfdc6c7e0'),
}
REFERENCE_DIR = Path(__file__).resolve().parents[1] / 'docs/mockups/ees-work/api-tools-20261113'


def check_png(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR' or struct.unpack('>II', data[16:24]) != (1920, 1080):
        raise ValueError(f'Expected a 1920 × 1080 PNG at {path}')
    return hashlib.sha256(data).hexdigest()


def write_review(captures, output):
    output.mkdir(parents=True, exist_ok=True)
    sections = []
    for scene, (title, expected_hash) in SCENES.items():
        reference = REFERENCE_DIR / f'figma-{scene}.png'
        product = captures / f'api-v11-{scene}.png'
        measurements = captures / f'api-v11-{scene}.json'
        if check_png(reference) != expected_hash:
            raise ValueError(f'Figma v11 reference changed: {reference}')
        check_png(product)
        evidence = json.loads(measurements.read_text(encoding='utf-8'))
        if evidence['scene'] != scene or evidence['viewport'] != [1920, 1080] or evidence['dpr'] != 1:
            raise ValueError(f'Unexpected browser capture state: {measurements}')
        for item in (reference, product, measurements):
            shutil.copy2(item, output / item.name)
        sections.append(f'<section><h2>{escape(title)}</h2><p><a href="{measurements.name}">DOM 실측값</a></p><div>'
                        f'<figure><figcaption>Figma v11</figcaption><a href="{reference.name}"><img src="{reference.name}" alt="Figma"></a></figure>'
                        f'<figure><figcaption>제품</figcaption><a href="{product.name}"><img src="{product.name}" alt="제품"></a></figure></div></section>')
    html = ('<!doctype html><html lang="ko"><meta charset="utf-8"><title>워크 · 도구 v11 제품 비교</title>'
            '<style>body{font:16px system-ui;margin:1.5rem;color:#24272a}section{margin:2.5rem 0}section div{display:flex;gap:1rem}'
            'figure{margin:0;min-width:0;flex:1}img{max-width:100%;border:1px solid #aaa}figcaption{margin-bottom:.5rem}</style>'
            '<h1>워크 · 도구 v11 제품 비교</h1><p>이미지를 선택하면 1920 × 1080 원본을 엽니다.</p>'
            + ''.join(sections) + '</html>')
    (output / 'index.html').write_text(html, encoding='utf-8')


if __name__ == '__main__':
    write_review(*map(Path, sys.argv[1:]))
