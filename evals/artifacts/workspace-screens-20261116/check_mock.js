// Browser check for design-mock-17-workspace.html (synthetic data only, no network).
// Usage: node check_mock.js <mock.html> <report.json> [capture-dir]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const [file, reportPath, captureDir] = process.argv.slice(2);
const IDS = ['WS1', 'WS2', 'WS3', 'WS4', 'WS5', 'WS6', 'WS7', 'WS8', 'WS9'];
const NAV = { WS1: '업무 절차', WS2: '업무 절차', WS3: '도구', WS4: '도구', WS5: '도구', WS6: '작업 지침', WS7: '작업 지침', WS8: '참고 문서', WS9: '참고 문서' };
const checks = [];
const ok = (name, pass, detail) => checks.push({ name, pass: !!pass, ...(detail === undefined ? {} : { detail }) });

(async () => {
  const html = fs.readFileSync(file, 'utf8');
  ok('static: CSP blocks every network load', /Content-Security-Policy" content="default-src 'none'/.test(html));
  ok('static: no external resource reference', !/(?:src|href)\s*=\s*["']?\s*(?:https?:)?\/\/|url\(\s*["']?\s*(?:https?:)?\/\//i.test(html));
  ok('static: every screen has a section', IDS.every(id => html.includes(`data-page="${id}"`)));
  const browser = await chromium.launch();
  const errors = [];
  for (const [w, h] of [[1920, 1080], [1366, 768], [480, 800]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    page.on('pageerror', e => errors.push(`${w}: ${e}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${w}: ${m.text()}`); });
    page.on('request', r => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) errors.push(`${w}: request ${r.url()}`); });
    await page.goto('file://' + path.resolve(file));
    for (const id of IDS) {
      await page.click(`#mock-guide [data-guide-step="${id}"]`);
      const s = await page.evaluate(() => {
        const root = document.getElementById('ees-work-wide');
        const shown = [...root.querySelectorAll('.ww-screen')].filter(e => !e.hidden).map(e => e.dataset.page);
        const current = [...root.querySelectorAll('[data-nav][aria-current="page"]')].map(e => e.title);
        const main = root.querySelector('#work-main').getBoundingClientRect();
        const wide = [...root.querySelectorAll('.ww-screen:not([hidden]) *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > main.right + 1; }).length;
        return { shown, current, badge: document.getElementById('mock-badge').textContent, area: root.querySelector('#area-label').textContent,
          ctx: root.querySelector('#chat-context').textContent, docOverflow: document.documentElement.scrollWidth > innerWidth, wide,
          layout: root.dataset.workLayout, overlay: root.dataset.overlay, compact: root.dataset.compact };
      });
      ok(`${w} ${id}: only this screen is shown`, s.shown.length === 1 && s.shown[0] === id, s.shown);
      ok(`${w} ${id}: badge says 시안 · 저장·실행 안 됨 · ${id}`, s.badge === `시안 1 · 저장·실행 안 됨 · ${id}`, s.badge);
      ok(`${w} ${id}: menu and header name the same place`, s.current.length === 1 && s.current[0] === NAV[id] && s.area === NAV[id], [s.current, s.area]);
      ok(`${w} ${id}: chat reference follows the screen`, s.ctx.length > 0, s.ctx);
      ok(`${w} ${id}: nothing runs past the work area or the window`, !s.docOverflow && s.wide === 0, { docOverflow: s.docOverflow, wide: s.wide });
      if (id === 'WS1') ok(`${w}: layout for this width`, w === 1920 ? s.layout === 'split1' && s.overlay === 'false' : w === 1366 ? s.layout === 'single' && s.overlay === 'false' : s.layout === 'single' && s.overlay === 'true' && s.compact === 'true', s);
      if (captureDir && w === 1920) await page.screenshot({ path: path.join(captureDir, `${id}.png`) });
      if (captureDir && w === 480 && (id === 'WS3' || id === 'WS7')) await page.screenshot({ path: path.join(captureDir, `${id}-480.png`) });
    }
    if (w === 1920) {
      const root = '#ees-work-wide ';
      // lists: open a row, come back, search, empty state
      await page.click('#mock-guide [data-guide-step="WS1"]');
      await page.click(root + '[data-page="WS1"] .ww-trow[data-go="WS2"]');
      ok('WS1 → WS2 by row', await page.isVisible(root + '[data-page="WS2"]'));
      await page.click(root + '[data-page="WS2"] .ww-back');
      ok('WS2 → WS1 by back link', await page.isVisible(root + '[data-page="WS1"]'));
      await page.fill(root + '[data-filter="procedures"]', '점검');
      ok('WS1 search keeps matching rows', await page.locator(root + '[data-list="procedures"] .ww-trow:visible').count() === 2 && (await page.textContent(root + '[data-filter-count="procedures"]')) === '2개 표시');
      await page.fill(root + '[data-filter="procedures"]', '없는 이름');
      ok('WS1 search shows the empty state', await page.isVisible(root + '[data-empty="procedures"]'));
      await page.fill(root + '[data-filter="procedures"]', '');
      ok('WS1 search clears', await page.locator(root + '[data-list="procedures"] .ww-trow:visible').count() === 5);
      await page.click(root + '[data-action="open-create"]');
      ok('WS1 new procedure asks name and purpose', await page.isVisible('#new-procedure-name') && await page.isVisible('#new-procedure-purpose'));
      await page.click(root + '[data-action="close-create"]');
      ok('WS1 new procedure can be cancelled', await page.isHidden('#procedure-create'));
      // WS2: structure, tabs, unsaved marker
      await page.click('#mock-guide [data-guide-step="WS2"]');
      await page.click(root + '.ww-item[data-item="t1"]');
      ok('WS2 task shows its linked tool', (await page.textContent('#procedure-editor')).includes('배포 문서 찾기'));
      ok('WS2 starts without an unsaved marker', await page.isHidden(root + '[data-dirty-dot="procedure"]'));
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
      ok('WS3 search finds by address and opens its group', await page.locator(root + '[data-list="apis"] .ww-trow:visible').count() === 1 && await page.isHidden(root + '.ws-group[data-group="wiki"]'));
      await page.fill(root + '[data-filter="apis"]', '');
      await page.click(root + '[data-page="WS3"] .ww-trow[data-go="WS4"]');
      await page.click(root + '[data-page="WS4"] [data-go="WS5"]');
      ok('WS3 → WS4 → WS5', await page.isVisible(root + '[data-page="WS5"]'));
      await page.selectOption('#api-method', 'POST');
      ok('WS5 edit shows the unsaved marker', await page.isVisible(root + '[data-dirty-dot="api"]'));
      // WS7: body edit and access choice
      await page.click('#mock-guide [data-guide-step="WS7"]');
      ok('WS7 starts without 바뀜', await page.isHidden(root + '[data-dirty-tag="skill"]'));
      await page.fill('#skill-body', '1. CR 번호를 먼저 확인합니다.');
      ok('WS7 body edit shows 바뀜 and the unsaved text', await page.isVisible(root + '[data-dirty-tag="skill"]') && (await page.textContent(root + '[data-dirty-text="skill"]')) === '바뀐 곳 있음 · 저장 전');
      await page.click(root + '[data-page="WS7"] [role="radio"]:has-text("비공개")');
      ok('WS7 one access choice at a time', await page.locator(root + '[data-page="WS7"] [aria-label="누가 쓸 수 있나요"] [aria-checked="true"]').count() === 1);
      // WS9: failed file offers retry, and a mock action only reports
      await page.click('#mock-guide [data-guide-step="WS9"]');
      await page.click(root + '[data-page="WS9"] .ww-link:has-text("다시 처리")');
      ok('mock actions only show a notice', (await page.textContent('#mock-toast')).startsWith('시안입니다'));
      // chat folds and returns
      await page.click(root + '.wc-chat-toggle');
      ok('chat folds', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'false');
      await page.click(root + '.wc-chat-toggle');
      ok('chat opens again', await page.getAttribute('#ees-work-wide', 'data-chat-open') === 'true');
      // keyboard: rows and menu are buttons
      ok('rows and menu items are buttons', await page.evaluate(() => [...document.querySelectorAll('#ees-work-wide [data-go]')].every(e => e.tagName === 'BUTTON')));
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
  const report = { mock: path.basename(file), sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), bytes: fs.statSync(file).size,
    browser: 'Chromium (Playwright, headless)', widths: ['1920x1080', '1366x768', '480x800'], total: checks.length, passed: checks.length - failed.length, failed, checks };
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 1) + '\n');
  console.log(`${report.passed}/${report.total}`, failed.map(f => f.name + ' ' + JSON.stringify(f.detail || '')).join('\n'));
  process.exit(failed.length ? 1 : 0);
})();
