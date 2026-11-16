// Browser check for design-mock-17-workspace.html, revision 2 (synthetic data only, no network).
// Usage: node check_mock.js <mock.html> <report.json> [capture-dir]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const [file, reportPath, captureDir] = process.argv.slice(2);
const IDS = ['WS1', 'WS2', 'WS3', 'WS4', 'WS5', 'WS6', 'WS7', 'WS8', 'WS9'];
const NAV = { WS1: '업무 절차', WS2: '업무 절차', WS3: '도구', WS4: '도구', WS5: '도구', WS6: '작업 지침', WS7: '작업 지침', WS8: '참고 문서', WS9: '참고 문서' };
// With the center 1264px or wider the list stays beside the opened item.
const WIDE = { WS1: ['WS1', 'WS2'], WS2: ['WS1', 'WS2'], WS3: ['WS3', 'WS4'], WS4: ['WS3', 'WS4'], WS5: ['WS3', 'WS5'], WS6: ['WS6', 'WS7'], WS7: ['WS6', 'WS7'], WS8: ['WS8', 'WS9'], WS9: ['WS8', 'WS9'] };
const checks = [];
const ok = (name, pass, detail) => checks.push({ name, pass: !!pass, ...(detail === undefined ? {} : { detail }) });
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const usage = [];

(async () => {
  const html = fs.readFileSync(file, 'utf8');
  ok('static: CSP blocks every network load', /Content-Security-Policy" content="default-src 'none'/.test(html));
  ok('static: no external resource reference', !/(?:src|href)\s*=\s*["']?\s*(?:https?:)?\/\/|url\(\s*["']?\s*(?:https?:)?\/\//i.test(html));
  ok('static: every screen has a pane', IDS.every(id => html.includes(`data-pane="${id}"`)));
  const browser = await chromium.launch();
  const errors = [];
  for (const [w, h, fold] of [[1920, 1080, false], [1920, 1080, true], [1366, 768, false], [480, 800, false]]) {
    const tag = w + (fold ? ' chat folded' : '');
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    page.on('pageerror', e => errors.push(`${tag}: ${e}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${tag}: ${m.text()}`); });
    page.on('request', r => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) errors.push(`${tag}: request ${r.url()}`); });
    await page.goto('file://' + path.resolve(file));
    if (fold) { await page.click('#mock-guide [data-guide-chat]'); await page.waitForFunction(() => document.getElementById('ees-work-wide').dataset.workLayout === 'split2'); await page.waitForTimeout(500); }
    for (const id of IDS) {
      await page.click(`#mock-guide [data-guide-step="${id}"]`);
      const s = await page.evaluate(() => {
        const root = document.getElementById('ees-work-wide'), seen = e => e.getClientRects().length > 0;
        const panes = [...root.querySelectorAll('.ws-pane')].filter(seen).map(e => e.dataset.pane);
        const current = [...root.querySelectorAll('[data-nav][aria-current="page"]')].map(e => e.title);
        const main = root.querySelector('#work-main').getBoundingClientRect(), scr = root.querySelector('.ww-screen:not([hidden])'), area = scr.getBoundingClientRect();
        const wide = [...scr.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return seen(e) && r.width > 0 && r.right > main.right + 1; }).length;
        // share of the work area covered by text lines and controls, on an 8px grid
        const cells = new Set(), G = 8;
        const mark = r => { for (let x = Math.max(area.left, r.left); x < Math.min(area.right, r.right); x += G) for (let y = Math.max(area.top, r.top); y < Math.min(area.bottom, r.bottom); y += G) cells.add(Math.floor(x / G) + ':' + Math.floor(y / G)); };
        const walker = document.createTreeWalker(scr, NodeFilter.SHOW_TEXT); let n;
        while ((n = walker.nextNode())) { if (!n.textContent.trim()) continue; const range = document.createRange(); range.selectNodeContents(n); for (const r of range.getClientRects()) if (r.width > 0) mark(r); }
        scr.querySelectorAll('input,textarea,select,img,.ws-tag').forEach(e => { const r = e.getBoundingClientRect(); if (r.width > 0) mark(r); });
        return { panes, current, badge: document.getElementById('mock-badge').textContent, area: root.querySelector('#area-label').textContent,
          ctx: root.querySelector('#chat-context').textContent, docOverflow: document.documentElement.scrollWidth > innerWidth, wide,
          layout: root.dataset.workLayout, overlay: root.dataset.overlay, compact: root.dataset.compact,
          work: Math.round(area.width), covered: Math.round(100 * cells.size * G * G / (area.width * area.height)),
          listTitles: [...root.querySelectorAll('.ws-listpane')].filter(seen).reduce((c, e) => c + e.querySelectorAll('h1,.ws-desc').length, 0),
          backToList: [...scr.querySelectorAll('[data-back="list"]')].filter(seen).length,
          currentRows: [...scr.querySelectorAll('.ww-trow[aria-current="true"]')].filter(seen).length };
      });
      const expected = fold ? WIDE[id] : [id];
      ok(`${tag} ${id}: panes in view are ${expected.join(' + ')}`, same(s.panes, expected), s.panes);
      ok(`${tag} ${id}: badge names the screens in view`, s.badge === `시안 2 · 저장·실행 안 됨 · ${expected.join(' + ')}`, s.badge);
      ok(`${tag} ${id}: menu and header band name the same place`, same(s.current, [NAV[id]]) && s.area === NAV[id], [s.current, s.area]);
      ok(`${tag} ${id}: chat reference follows the screen`, s.ctx.length > 0, s.ctx);
      ok(`${tag} ${id}: nothing runs past the work area or the window`, !s.docOverflow && s.wide === 0, { docOverflow: s.docOverflow, wide: s.wide });
      ok(`${tag} ${id}: a list carries no second title or description`, s.listTitles === 0, s.listTitles);
      if (fold) ok(`${tag} ${id}: the open row is marked and no link leads back to the list beside it`, s.currentRows === 1 && s.backToList === 0, { rows: s.currentRows, back: s.backToList });
      else ok(`${tag} ${id}: no row is marked while the list is alone`, s.currentRows === 0, s.currentRows);
      if (id === 'WS1') ok(`${tag}: layout for this width`, fold ? s.layout === 'split2' : w === 1920 ? s.layout === 'split1' && s.overlay === 'false' : w === 1366 ? s.layout === 'single' && s.overlay === 'false' : s.layout === 'single' && s.overlay === 'true' && s.compact === 'true', s);
      if (w === 1920) usage.push({ chat: fold ? 'folded' : 'open', screen: expected.join(' + '), work_px: s.work, covered_percent: s.covered });
      if (captureDir && w === 1920 && !fold) await page.screenshot({ path: path.join(captureDir, `${id}.png`) });
      if (captureDir && fold && ['WS2', 'WS4', 'WS5', 'WS7', 'WS9'].includes(id)) await page.screenshot({ path: path.join(captureDir, `${expected.join('-')}-wide.png`) });
      if (captureDir && w === 480 && (id === 'WS3' || id === 'WS7')) await page.screenshot({ path: path.join(captureDir, `${id}-480.png`) });
    }
    const root = '#ees-work-wide ';
    if (w === 1920 && !fold) {
      // lists: open a row, come back, search, empty state
      await page.click('#mock-guide [data-guide-step="WS1"]');
      await page.click(root + '[data-pane="WS1"] .ww-trow[data-go="WS2"]');
      ok('WS1 → WS2 by row', await page.isVisible(root + '[data-pane="WS2"]') && await page.isHidden(root + '[data-pane="WS1"]'));
      await page.click(root + '[data-pane="WS2"] .ww-back');
      ok('WS2 → WS1 by back link', await page.isVisible(root + '[data-pane="WS1"]'));
      await page.fill(root + '[data-filter="procedures"]', '점검');
      ok('WS1 search keeps matching rows and counts them', await page.locator(root + '[data-list="procedures"] .ww-trow:visible').count() === 2 && (await page.textContent(root + '[data-count="procedures"]')) === '5개 중 2개');
      await page.fill(root + '[data-filter="procedures"]', '없는 이름');
      ok('WS1 search shows the empty state', await page.isVisible(root + '[data-empty="procedures"]'));
      await page.fill(root + '[data-filter="procedures"]', '');
      ok('WS1 search clears', await page.locator(root + '[data-list="procedures"] .ww-trow:visible').count() === 5 && (await page.textContent(root + '[data-count="procedures"]')) === '5개');
      await page.click(root + '[data-action="open-create"]');
      ok('WS1 new procedure asks name and purpose', await page.isVisible('#new-procedure-name') && await page.isVisible('#new-procedure-purpose'));
      await page.click(root + '[data-action="close-create"]');
      ok('WS1 new procedure can be cancelled', await page.isHidden('#procedure-create'));
      // WS2: structure, tabs, unsaved marker
      await page.click('#mock-guide [data-guide-step="WS2"]');
      ok('WS2 shows no status text before a change', (await page.textContent(root + '[data-dirty-text="procedure"]')) === '' && await page.isHidden(root + '[data-dirty-dot="procedure"]'));
      await page.click(root + '.ww-item[data-item="t1"]');
      ok('WS2 task shows its linked tool', (await page.textContent('#procedure-editor')).includes('배포 문서 찾기'));
      await page.fill('#name-t1', '배포 문서 확인');
      ok('WS2 edit shows the unsaved marker', await page.isVisible(root + '[data-dirty-dot="procedure"]') && (await page.textContent(root + '[data-dirty-text="procedure"]')) === '저장하지 않은 변경 있음');
      await page.click(root + '[data-tab="procedure:history"]');
      ok('WS2 tab shows only its panel', await page.isVisible(root + '[data-tab-panel="procedure:history"]') && await page.isHidden(root + '[data-tab-panel="procedure:content"]'));
      await page.click(root + '[data-tab="procedure:content"]');
      ok('WS2 keeps the edited value across tabs', await page.inputValue('#name-t1') === '배포 문서 확인');
      // WS3: groups and search across service and address
      await page.click('#mock-guide [data-guide-step="WS3"]');
      await page.click(root + '[data-toggle-group="backup"]');
      ok('WS3 group folds', await page.locator(root + '[data-in-group="backup"]:visible').count() === 0 && await page.getAttribute(root + '[data-toggle-group="backup"]', 'aria-expanded') === 'false');
      await page.fill(root + '[data-filter="apis"]', 'retries');
      ok('WS3 search finds by address and opens its group', await page.locator(root + '[data-list="apis"] .ww-trow:visible').count() === 1 && await page.isHidden(root + '.ws-group[data-group="wiki"]') && (await page.textContent(root + '[data-count="apis"]')) === 'API 명세 3개 중 1개');
      await page.fill(root + '[data-filter="apis"]', '');
      await page.click(root + '[data-pane="WS3"] .ww-trow[data-go="WS4"]');
      await page.click(root + '[data-pane="WS4"] [data-go="WS5"]');
      ok('WS3 → WS4 → WS5', await page.isVisible(root + '[data-pane="WS5"]') && await page.isHidden(root + '[data-pane="WS4"]'));
      ok('WS5 save is off until something changes', await page.isDisabled(root + '[data-save="api"]'));
      await page.selectOption(root + '[aria-label="입력 2 필수 여부"]', '필수');
      ok('WS5 change turns save on and shows the unsaved marker', await page.isEnabled(root + '[data-save="api"]') && await page.isVisible(root + '[data-dirty-dot="api"]'));
      // WS7: body edit and access choice
      await page.click('#mock-guide [data-guide-step="WS7"]');
      ok('WS7 starts without 바뀜', await page.isHidden(root + '[data-dirty-tag="skill"]'));
      const body = await page.evaluate(() => { const t = document.getElementById('skill-body').getBoundingClientRect(), m = t && document.querySelector('#ees-work-wide [data-pane="WS7"] .ws-main').getBoundingClientRect(); return { text: Math.round(t.height), room: Math.round(m.height) }; });
      ok('WS7 body uses the height of its column', body.text > body.room * 0.7, body);
      await page.fill('#skill-body', '1. CR 번호를 먼저 확인합니다.');
      ok('WS7 body edit shows 바뀜 and the unsaved text', await page.isVisible(root + '[data-dirty-tag="skill"]') && (await page.textContent(root + '[data-dirty-text="skill"]')) === '바뀐 곳 있음 · 저장 전');
      await page.click(root + '[data-pane="WS7"] [role="radio"]:has-text("비공개")');
      ok('WS7 one access choice at a time', await page.locator(root + '[data-pane="WS7"] [aria-label="누가 쓸 수 있나요"] [aria-checked="true"]').count() === 1);
      // WS9: failed file offers retry, and a mock action only reports
      await page.click('#mock-guide [data-guide-step="WS9"]');
      await page.click(root + '[data-pane="WS9"] .ww-link:has-text("다시 처리")');
      ok('mock actions only show a notice', (await page.textContent('#mock-toast')).startsWith('시안입니다'));
      // chat folds and returns from the header band
      await page.click(root + '.wc-chat-toggle');
      ok('chat folds', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'false');
      await page.click(root + '.wc-chat-toggle');
      ok('chat opens again', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'true');
      ok('rows and menu items are buttons', await page.evaluate(() => [...document.querySelectorAll('#ees-work-wide [data-go]')].every(e => e.tagName === 'BUTTON')));
    }
    if (fold) {
      // list beside the opened item: the list stays, the edit screen keeps its own way back
      await page.click('#mock-guide [data-guide-step="WS3"]');
      const pane = await page.evaluate(() => Math.round(document.querySelector('#ees-work-wide [data-pane="WS3"]').getBoundingClientRect().width));
      ok('wide: the list pane keeps a fixed width', pane === 420, pane);
      await page.click(root + '[data-pane="WS4"] [data-go="WS5"]');
      ok('wide: edit opens beside the list', await page.isVisible(root + '[data-pane="WS3"]') && await page.isVisible(root + '[data-pane="WS5"]'));
      await page.click(root + '[data-pane="WS5"] .ww-back');
      ok('wide: ← API 상세 returns to the detail', await page.isVisible(root + '[data-pane="WS4"]') && await page.isHidden(root + '[data-pane="WS5"]'));
      await page.click(root + '.wc-chat-toggle');
      await page.waitForFunction(() => document.getElementById('ees-work-wide').dataset.workLayout === 'split1');
      ok('wide: opening the chat returns to one pane', await page.locator(root + '.ws-pane:visible').count() === 1);
    }
    if (w === 480) {
      await page.click('#ees-work-wide .wc-chat-toggle');
      ok('480 chat opens over the work area', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'true' && await page.isVisible('#ees-work-wide .wc-scrim'));
      await page.keyboard.press('Escape');
      ok('480 Escape closes the chat', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'false');
    }
    await page.close();
  }
  await browser.close();
  ok('no page error, console error or network request', errors.length === 0, errors.slice(0, 5));
  const failed = checks.filter(c => !c.pass);
  const report = { mock: path.basename(file), revision: 2, sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), bytes: fs.statSync(file).size,
    browser: 'Chromium (Playwright, headless)', views: ['1920x1080', '1920x1080 chat folded', '1366x768', '480x800'], total: checks.length, passed: checks.length - failed.length, failed, usage_1920: usage, checks };
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 1) + '\n');
  console.log(`${report.passed}/${report.total}`, failed.map(f => f.name + ' ' + JSON.stringify(f.detail || '')).join('\n'));
  console.table(usage);
  process.exit(failed.length ? 1 : 0);
})();
