#!/usr/bin/env python3
"""Validate the standalone work-centered design mock; never touches product state.

Run with --static-only where browser execution is unavailable. Browser evidence
is recorded separately and is never inferred from HTML or JavaScript parsing.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys


class MockParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.resources = []
        self.scripts = []
        self.current_script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag in ('script', 'img', 'iframe', 'source', 'link'):
            for attr in ('src', 'href'):
                value = attrs.get(attr, '')
                if value.startswith(('http:', 'https:', '//')):
                    self.resources.append({'tag': tag, 'attribute': attr, 'url': value})
        if (tag == 'script' and not attrs.get('src')
                and attrs.get('type', '').lower() in ('', 'text/javascript', 'application/javascript', 'module')):
            self.current_script = []

    def handle_endtag(self, tag):
        if tag == 'script' and self.current_script is not None:
            self.scripts.append(''.join(self.current_script))
            self.current_script = None

    def handle_data(self, data):
        if self.current_script is not None:
            self.current_script.append(data)


def static_checks(path, output):
    content = path.read_text(encoding='utf-8')
    parser = MockParser()
    parser.feed(content)
    duplicate_ids = sorted(key for key, count in Counter(parser.ids).items() if count > 1)
    script_results = []
    for index, script in enumerate(parser.scripts):
        target = output / f'inline-{index + 1}.js'
        target.write_text(script, encoding='utf-8')
        checked = subprocess.run(['node', '--check', str(target)], capture_output=True, text=True)
        script_results.append({'index': index + 1, 'passed': checked.returncode == 0,
                               'error': checked.stderr.strip()})
    required = ['chat-draft', 'chat-resizer', 'operation-note', 'procedure-name',
                'procedure-description', 'tool-description']
    missing = [value for value in required if value not in parser.ids and value not in content]
    return {'passed': bool(parser.scripts) and not duplicate_ids and not parser.resources and not missing
            and all(row['passed'] for row in script_results),
            'duplicate_ids': duplicate_ids, 'external_resource_dependencies': parser.resources,
            'missing_required_ids': missing, 'script_parse': script_results,
            'limitations': 'Parsing does not prove visual layout, accessibility, click behavior, or draft preservation.'}


def browser_checks(path, output, executable, selectors):
    from playwright.sync_api import sync_playwright
    result = {'status': 'running', 'screens': [], 'checks': [], 'errors': [], 'screenshots': []}
    def check(name, actual, expected=True):
        passed = actual == expected
        result['checks'].append({'name': name, 'passed': passed, 'actual': actual, 'expected': expected})
    def close_chat(page):
        close = page.locator('#chat-panel button[data-action="hide-chat"]').filter(visible=True)
        if close.count():
            close.first.click()
        else:
            page.locator('[data-action="toggle-chat"]').filter(visible=True).first.click()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])
        for width, height in [(1920, 1080), (1366, 768), (480, 768)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.on('pageerror', lambda error: result['errors'].append(str(error)))
            page.goto(path.resolve().as_uri(), wait_until='load')
            page.locator('button[data-screen="operations"]').first.wait_for(state='attached')
            page.evaluate('document.fonts.ready')
            prefix = f'{width}x{height}'
            check(prefix + ': document does not overflow horizontally',
                  page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            geometry = page.evaluate('''selectors => Object.fromEntries(Object.entries(selectors).map(([name, selector]) => {
                const n = document.querySelector(selector), r = n?.getBoundingClientRect();
                return [name, r ? {x:r.x,y:r.y,width:r.width,height:r.height,visible:r.width>0&&r.height>0&&getComputedStyle(n).display!=="none"} : null];
            }))''', selectors)
            result['screens'].append({'viewport': [width, height], 'geometry': geometry})
            expected_widths = {1920: {'navigation': 256, 'work': 1104, 'chat': 560},
                               1366: {'navigation': 56, 'work': 830, 'chat': 480}}
            for region, expected in expected_widths.get(width, {}).items():
                box = geometry.get(region)
                check(prefix + ': ' + region + ' matches agreed width',
                      bool(box) and abs(box['width'] - expected) <= 1)
            obscured = page.evaluate('''() => [...document.querySelectorAll('button')].filter(n => {
                const r=n.getBoundingClientRect(), s=getComputedStyle(n);
                if (!r.width || !r.height || s.visibility==='hidden' || s.display==='none' || n.disabled) return false;
                const x=r.x+r.width/2, y=r.y+r.height/2;
                if (x<0 || x>=innerWidth || y<0 || y>=innerHeight) return false;
                const hit=document.elementFromPoint(x,y);
                return hit && !n.contains(hit);
            }).map(n => ({text:n.textContent.trim(),action:n.dataset.action||null,screen:n.dataset.screen||null}))''')
            check(prefix + ': visible button centers are clickable', obscured, [])
            shot = output / f'{prefix}-operations.png'
            page.screenshot(path=str(shot), full_page=True)
            result['screenshots'].append(str(shot))
            if not page.locator('#chat-draft').is_visible():
                page.locator('[data-action="toggle-chat"]').filter(visible=True).first.click()
            page.locator('#chat-draft').fill('채팅 초안 보존 검증')
            close_chat(page)
            check(prefix + ': chat closes', not page.locator('#chat-draft').is_visible())
            page.locator('[data-action="toggle-chat"]').filter(visible=True).first.click()
            check(prefix + ': chat draft survives close/open', page.locator('#chat-draft').input_value(), '채팅 초안 보존 검증')
            focus = page.locator('[data-action="toggle-chat-focus"]').filter(visible=True)
            if focus.count():
                focus.first.click()
                check(prefix + ': chat draft survives expansion', page.locator('#chat-draft').input_value(), '채팅 초안 보존 검증')
                shot = output / f'{prefix}-chat-expanded.png'
                page.screenshot(path=str(shot), full_page=True)
                result['screenshots'].append(str(shot))
                page.locator('[data-action="toggle-chat-focus"]').filter(visible=True).first.click()
            if width == 480 and page.locator('#chat-draft').is_visible():
                close_chat(page)
            page.locator('button[data-mode="workspace"]').first.click()
            check(prefix + ': chat draft survives mode switch', page.locator('#chat-draft').input_value(), '채팅 초안 보존 검증')
            page.locator('button[data-screen="procedure"]').first.click()
            page.locator('#procedure-description').fill('업무 절차 초안 보존 검증')
            page.locator('button[data-screen="tools"]').first.click()
            page.locator('#tool-description').fill('도구 초안 보존 검증')
            page.locator('button[data-screen="procedure"]').first.click()
            check(prefix + ': procedure draft survives route switch', page.locator('#procedure-description').input_value(), '업무 절차 초안 보존 검증')
            page.locator('button[data-screen="tools"]').first.click()
            check(prefix + ': tool draft survives route switch', page.locator('#tool-description').input_value(), '도구 초안 보존 검증')
            for screen in ['procedure', 'tools', 'documents']:
                page.locator(f'button[data-screen="{screen}"]').first.click()
                check(prefix + ': ' + screen + ' has no horizontal document overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                shot = output / f'{prefix}-{screen}.png'
                page.screenshot(path=str(shot), full_page=True)
                result['screenshots'].append(str(shot))
            check(prefix + ': chat draft survives all screens', page.locator('#chat-draft').input_value(), '채팅 초안 보존 검증')
            page.close()
        browser.close()
    result['status'] = 'passed' if all(row['passed'] for row in result['checks']) and not result['errors'] else 'failed'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('html', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent)
    parser.add_argument('--static-only', action='store_true')
    parser.add_argument('--browser', default='/usr/bin/chromium')
    parser.add_argument('--nav-selector', default='.wc-sidebar')
    parser.add_argument('--work-selector', default='#work-main')
    parser.add_argument('--chat-selector', default='#chat-panel')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'html': str(args.html.resolve()), 'static': static_checks(args.html, args.output),
              'browser': {'status': 'not_run', 'screenshots': []}}
    if not args.static_only:
        try:
            result['browser'] = browser_checks(args.html, args.output, args.browser,
                {'navigation': args.nav_selector, 'work': args.work_selector, 'chat': args.chat_selector})
        except Exception as error:
            result['browser'] = {'status': 'blocked_or_failed', 'error': str(error), 'screenshots': []}
    target = args.output / 'validation-report.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(target), 'static_passed': result['static']['passed'],
                      'browser_status': result['browser']['status']}, ensure_ascii=False))
    return 0 if result['static']['passed'] and (args.static_only or result['browser']['status'] == 'passed') else 1


if __name__ == '__main__':
    sys.exit(main())
