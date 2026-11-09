#!/usr/bin/env node
// Validate the standalone wide work-screen design mock (revision 2). Never touches product state.
// Usage: node validate_mock.cjs <design-mock-15-work-centered-wide.html> [--output DIR] [--static-only]
// Browser evidence is recorded only from a real Chromium run; parsing alone never counts as visual proof.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const args = process.argv.slice(2);
const html = path.resolve(args.find(a => !a.startsWith('--')) || '');
const outIndex = args.indexOf('--output');
const output = path.resolve(outIndex >= 0 ? args[outIndex + 1] : __dirname);
const staticOnly = args.includes('--static-only');
fs.mkdirSync(output, { recursive: true });

function staticChecks(file) {
  const content = fs.readFileSync(file, 'utf8');
  const ids = [...content.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
  const duplicateIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))].sort();
  const external = [...content.matchAll(/(?:src|href)\s*=\s*["']?\s*(?:https?:)?\/\/[^"'\s>]+/gi)].map(m => m[0]);
  const scripts = [...content.matchAll(/<script(?![^>]*type="text\/plain")[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  const scriptParse = scripts.map((code, index) => {
    try { new vm.Script(code, { filename: `inline-${index + 1}.js` }); return { index: index + 1, passed: true }; }
    catch (error) { return { index: index + 1, passed: false, error: String(error.message) }; }
  });
  const required = ['chat-draft', 'chat-resizer', 'task-list', 'detail-slot', 'overview-table', 'procedure-tree', 'procedure-editor', 'mock-screen', 'mock-badge'];
  const missing = required.filter(id => !ids.includes(id));
  const markers = {
    csp: content.includes("default-src 'none'"),
    mockLabel: content.includes('시안 2 · 저장·실행 안 됨'),
    newScreenCss: content.includes('data-new-screen="work-centered-wide"'),
    productCss: content.includes('data-product-css="branding/ees/ui/chat-theme.css"') && content.includes('data-product-css="branding/ees/ui/ees-work-launcher.css"'),
    unresolvedIcons: /(?:^|[^\w/])v4\/[0-9a-f]{5}\.svg/.test(content.replace(/<script type="text\/plain"[\s\S]*?<\/script>/, '')),
  };
  const passed = scripts.length > 0 && !duplicateIds.length && !external.length && !missing.length && scriptParse.every(r => r.passed)
    && markers.csp && markers.mockLabel && markers.newScreenCss && markers.productCss && !markers.unresolvedIcons;
  return { passed, duplicateIds, externalResources: external, missingRequiredIds: missing, scriptParse, markers,
    limitations: 'Parsing does not prove layout, click behaviour, accessibility or draft preservation.' };
}

async function browserChecks(file) {
  const { chromium } = require('playwright');
  const result = { status: 'running', checks: [], errors: [], screenshots: [], measurements: [] };
  const check = (name, actual, expected = true) => {
    const passed = JSON.stringify(actual) === JSON.stringify(expected);
    result.checks.push({ name, passed, actual, expected });
    return passed;
  };
  const browser = await chromium.launch();
  const shot = async (page, name) => { const target = path.join(output, name); await page.screenshot({ path: target }); result.screenshots.push(path.relative(process.cwd(), target)); };
  const state = page => page.evaluate(() => window.eesWorkWideMock.state());
  const box = (page, selector) => page.evaluate(s => { const n = document.querySelector(s); if (!n) return null; const r = n.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) }; }, selector);
  const settle = page => page.waitForTimeout(450);
  // The review selector lives in the expanded navigation. With the navigation folded (56px) the
  // reviewer reaches the same screens through the product routes: mode buttons and the breadcrumb.
  const go = async (page, no) => {
    if (await page.isVisible('#mock-screen')) { await page.selectOption('#mock-screen', no); await settle(page); }
    else if (no === 'W4') { await page.click('button[data-mode="workspace"]'); await settle(page); }
    else { await page.click('button[data-mode="work"]'); await settle(page); if (no === 'W3') { await page.click('.ww-crumb [data-screen="overview"]'); await settle(page); } }
    const s = await state(page);
    if (s.overlay && s.chatOpen) { await page.keyboard.press('Escape'); await settle(page); }
  };
  const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  const obscured = page => page.evaluate(() => [...document.querySelectorAll('#ees-work-wide button')].filter(n => {
    const r = n.getBoundingClientRect(), s = getComputedStyle(n);
    if (!r.width || !r.height || s.visibility === 'hidden' || s.display === 'none' || n.disabled || n.closest('[inert]')) return false;
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    if (x < 0 || x >= innerWidth || y < 0 || y >= innerHeight) return false;
    const hit = document.elementFromPoint(x, y);
    return hit && !n.contains(hit) && !hit.closest('.wc-toast');
  }).map(n => n.textContent.trim().slice(0, 30)));
  const expected = { 1920: { nav: 256, work: 1104, chat: 560, open: 'split1', closed: 'split2', closedWork: 1664 },
                     1366: { nav: 56, work: 830, chat: 480, open: 'single', closed: 'split2', closedWork: 1310 },
                     480:  { nav: 56, work: 424, chat: null, open: 'single', closed: 'single', closedWork: 424 } };
  for (const [width, height] of [[1920, 1080], [1366, 768], [480, 768]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    page.on('pageerror', e => result.errors.push(`${width}: ${e}`));
    page.on('console', m => { if (m.type() === 'error') result.errors.push(`${width} console: ${m.text()}`); });
    await page.goto('file://' + file, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    await settle(page);
    const p = `${width}x${height}`, e = expected[width];
    let s = await state(page);
    const nav = await box(page, '.wc-sidebar'), work = await box(page, '#work-main'), chat = await box(page, '#chat-panel');
    result.measurements.push({ viewport: p, nav, work, chat, state: s });
    check(`${p}: navigation width`, nav.width, e.nav);
    check(`${p}: work width`, work.width, e.work);
    if (e.chat) check(`${p}: docked chat width`, chat.width, e.chat);
    check(`${p}: layout with chat as opened at start`, s.layout, e.open);
    check(`${p}: screen number shown`, (await page.textContent('#mock-badge')).includes(s.screenNo), true);
    check(`${p}: no horizontal document overflow (W1)`, await noOverflow(page));
    check(`${p}: visible button centers are clickable (W1)`, await obscured(page), []);
    // list beside detail, or detail under its row
    const list = await box(page, '.ww-list'), detail = await box(page, '#detail-t2');
    if (s.layout === 'single') {
      check(`${p}: single layout puts the detail right after the selected row`, await page.evaluate(() => document.querySelector('.ww-task[data-task="t2"]').nextElementSibling?.id), 'detail-t2');
    } else {
      check(`${p}: detail sits to the right of the list`, detail.x >= list.x + list.width, true);
    }
    await shot(page, `${p}-W1.png`);
    // select another task: list stays, detail follows
    await page.click('.ww-task[data-task="t5"]');
    s = await state(page);
    check(`${p}: selecting a task updates the selection`, s.task, 't5');
    check(`${p}: preset verdict shows as chosen, not confirmed`, (await page.textContent('#detail-t5 [data-verdict-state]')).trim(), '선택됨 · 확정 전');
    if (s.layout !== 'single') check(`${p}: list keeps its position while a task is selected`, (await box(page, '.ww-list')).y, list.y);
    // reason draft survives task switches
    await page.click('.ww-task[data-task="t2"]');
    await page.fill('#reason-t2', '사유 초안 보존 검증');
    await page.click('.ww-task[data-task="t6"]');
    await page.click('.ww-task[data-task="t2"]');
    if ((await state(page)).layout === 'single' && !(await state(page)).expanded) await page.click('.ww-task[data-task="t2"]');
    check(`${p}: verdict reason draft survives task switches`, await page.inputValue('#reason-t2'), '사유 초안 보존 검증');
    await page.click('#detail-t2 [data-verdict="승인"]');
    check(`${p}: choosing a verdict marks it`, await page.getAttribute('#detail-t2 [data-verdict="승인"]', 'aria-checked'), 'true');
    // chat draft through close / open / expand
    if (!(await page.isVisible('#chat-draft'))) { await page.click('.wc-main-header [data-action="toggle-chat"]'); await settle(page); }
    await page.fill('#chat-draft', '채팅 초안 보존 검증');
    if ((await state(page)).overlay) { await page.keyboard.press('Escape'); await settle(page); check(`${p}: Escape closes the overlay chat`, (await state(page)).chatOpen, false); }
    else { await page.click('#chat-panel [data-action="hide-chat"]'); await settle(page); }
    s = await state(page);
    check(`${p}: chat closes`, s.chatOpen, false);
    check(`${p}: layout with chat closed`, s.layout, e.closed);
    check(`${p}: work width with chat closed`, Math.round(s.workWidth), e.closedWork);
    check(`${p}: no horizontal document overflow (chat closed)`, await noOverflow(page));
    if (width === 1920) { await page.click('.ww-task[data-task="t2"]'); await settle(page); await shot(page, `${p}-W2.png`); check(`${p}: screen number becomes W2`, (await state(page)).screenNo, 'W2'); }
    await page.click('.wc-main-header [data-action="toggle-chat"]'); await settle(page);
    check(`${p}: chat draft survives close/open`, await page.inputValue('#chat-draft'), '채팅 초안 보존 검증');
    if (!(await state(page)).overlay) {
      await page.click('#chat-panel [data-action="toggle-chat-focus"]'); await settle(page);
      check(`${p}: chat draft survives expansion`, await page.inputValue('#chat-draft'), '채팅 초안 보존 검증');
      await page.click('#chat-panel [data-action="toggle-chat-focus"]'); await settle(page);
      check(`${p}: layout returns after expansion`, (await state(page)).layout, e.open);
      const before = (await state(page)).workWidth;
      await page.focus('#chat-resizer'); await page.keyboard.press('ArrowLeft'); await settle(page);
      check(`${p}: keyboard resize widens chat by 16px`, Math.round(before - (await state(page)).workWidth), 16);
      await page.keyboard.press('ArrowRight'); await settle(page);
    } else {
      await page.keyboard.press('Escape'); await settle(page);
    }
    // W3 overview
    await go(page, 'W3');
    check(`${p}: W3 opens`, (await state(page)).screenNo, 'W3');
    check(`${p}: no horizontal document overflow (W3)`, await noOverflow(page));
    check(`${p}: visible button centers are clickable (W3)`, await obscured(page), []);
    await shot(page, `${p}-W3.png`);
    await page.click('.ww-next [data-open-task="t2"]'); await settle(page);
    s = await state(page);
    check(`${p}: next action opens the task in the stage screen`, [s.screen, s.task], ['stage', 't2']);
    // W4 authoring
    await go(page, 'W4');
    check(`${p}: W4 opens`, (await state(page)).screenNo, 'W4');
    check(`${p}: no horizontal document overflow (W4)`, await noOverflow(page));
    check(`${p}: visible button centers are clickable (W4)`, await obscured(page), []);
    await shot(page, `${p}-W4.png`);
    await page.fill('#task-criteria-t2', '확인 기준 초안 보존 검증');
    await page.click('.ww-item[data-item="info"]');
    await page.fill('#procedure-description', '업무 설명 초안 보존 검증');
    await page.click('.ww-item[data-item="p-t4"]');
    check(`${p}: a person-check task hides the tool block`, await page.isHidden('[data-editor="p-t4"] [data-tool-block]'), true);
    await page.click('[data-editor="p-t4"] [data-seg-option="도구로 처리"]');
    check(`${p}: switching to a tool shows the tool block`, await page.isVisible('[data-editor="p-t4"] [data-tool-block]'), true);
    await go(page, 'W1');
    await go(page, 'W4');
    await page.click('.ww-item[data-item="p-t2"]');
    check(`${p}: task editor draft survives item and screen switches`, await page.inputValue('#task-criteria-t2'), '확인 기준 초안 보존 검증');
    await page.click('.ww-item[data-item="info"]');
    check(`${p}: basic info draft survives item switches`, await page.inputValue('#procedure-description'), '업무 설명 초안 보존 검증');
    check(`${p}: chat draft survives all screens`, await page.inputValue('#chat-draft'), '채팅 초안 보존 검증');
    await page.close();
  }
  await browser.close();
  result.status = result.checks.every(c => c.passed) && !result.errors.length ? 'passed' : 'failed';
  return result;
}

(async () => {
  const report = { html: path.relative(process.cwd(), html), static: staticChecks(html), browser: { status: 'not_run' } };
  if (!staticOnly) {
    try { report.browser = await browserChecks(html); }
    catch (error) { report.browser = { status: 'blocked_or_failed', error: String(error && error.stack || error) }; }
  }
  const target = path.join(output, 'validation-report.json');
  fs.writeFileSync(target, JSON.stringify(report, null, 2) + '\n', 'utf8');
  const failed = report.browser.checks ? report.browser.checks.filter(c => !c.passed) : [];
  console.log(JSON.stringify({ report: path.relative(process.cwd(), target), static: report.static.passed, browser: report.browser.status,
    checks: report.browser.checks ? report.browser.checks.length : 0, failed: failed.map(f => ({ name: f.name, actual: f.actual, expected: f.expected })), errors: report.browser.errors || report.browser.error }, null, 1));
  process.exit(report.static.passed && (staticOnly || report.browser.status === 'passed') ? 0 : 1);
})();
