// Browser checks for design mock 16 (API tools, revision 1).
// Usage: node validate_mock.cjs [path/to/design-mock-16-api-tools.html]
// Needs Playwright with a Chromium build. Prints failures and the pass count; exits 1 on any failure.
const path = require('node:path');
const {chromium} = require('playwright');

const html = path.resolve(process.argv[2] || path.join(__dirname, '../../../docs/mockups/ees-work/design-mock-16-api-tools.html'));
const file = 'file://' + html;
const screens = ['AP1', 'AP2', 'AP3', 'AP4', 'AP5', 'AP6', 'AP7', 'AP8'];
const results = [];
const ok = (name, cond, info = '') => results.push([cond ? 'PASS' : 'FAIL', name, info]);
const screenOf = (page) => page.evaluate(() => document.getElementById('ees-api-tools').dataset.screen);

(async () => {
  const browser = await chromium.launch();
  for (const [w, h] of [[1920, 1080], [1366, 768], [480, 900]]) {
    const page = await browser.newPage({viewport: {width: w, height: h}});
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(m.text()); });
    await page.goto(file);
    await page.waitForTimeout(200);
    const go = (s) => page.evaluate((s) => { const el = document.getElementById('mock-screen'); el.value = s; el.dispatchEvent(new Event('change', {bubbles: true})); }, s);
    const layout = await page.evaluate(() => ({nav: document.querySelector('.wc-sidebar').getBoundingClientRect().width, work: document.getElementById('main-content').getBoundingClientRect().width, chatOpen: document.getElementById('ees-api-tools').dataset.chatOpen}));
    if (w === 1920) ok('1920 widths 256/1104/560', layout.nav === 256 && layout.work === 1104, JSON.stringify(layout));
    if (w === 1366) ok('1366 widths 56/830', layout.nav === 56 && layout.work === 830, JSON.stringify(layout));
    if (w === 480) ok('480 chat closed', layout.chatOpen === 'false', JSON.stringify(layout));
    for (const s of screens) {
      await go(s);
      await page.waitForTimeout(60);
      const m = await page.evaluate(() => {
        const c = document.getElementById('main-content').getBoundingClientRect(), over = [];
        for (const el of document.querySelectorAll('#ees-work-designer *')) {
          if (el.offsetParent === null) continue;
          const b = el.getBoundingClientRect();
          if (b.width && (b.right > c.right + 0.5 || b.left < c.left - 0.5)) over.push(el.className || el.tagName);
        }
        const ids = [...document.querySelectorAll('[id]')].map((e) => e.id);
        return {over, dup: ids.filter((v, i) => ids.indexOf(v) !== i), doc: document.documentElement.scrollWidth > innerWidth, badge: document.getElementById('mock-badge').textContent, state: !document.getElementById('mock-state').hidden, active: document.activeElement?.id};
      });
      ok(`${w} ${s} no overflow/dup`, !m.over.length && !m.dup.length && !m.doc, JSON.stringify({over: m.over.slice(0, 3), dup: m.dup}));
      ok(`${w} ${s} badge`, m.badge.includes(s) && m.badge.includes('시안 · 저장·실행 안 됨'));
      ok(`${w} ${s} state select only on AP6`, m.state === (s === 'AP6'));
      ok(`${w} ${s} focus stays on mock select`, m.active === 'mock-screen' || !m.active, m.active);
    }
    if (w === 1920) {
      await go('AP1');
      await page.fill('#ew-draft-search', '백업');
      ok('search filters to 1 row', await page.$$eval('.ew-draft-catalog>button:not([hidden])', (r) => r.length) === 1);
      await page.fill('#ew-draft-search', '');
      await page.click('.ew-draft-filters [data-id="request"]');
      ok('change filter shows empty message', await page.$eval('.ap-list-empty', (e) => !e.hidden));
      await page.click('.ew-draft-filters [data-id="all"]');
      await page.click('.ew-draft-catalog>button:first-child');
      ok('row opens AP2', await screenOf(page) === 'AP2');
      ok('heading focused after in-panel open', await page.evaluate(() => document.activeElement?.tagName) === 'H2');
      await page.click('[role="tab"][data-id="request"]');
      ok('tab opens AP3', await screenOf(page) === 'AP3');
      ok('tab focus kept', await page.evaluate(() => document.activeElement?.dataset.id) === 'request');
      await page.keyboard.press('ArrowRight');
      ok('arrow moves to next tab', await page.evaluate(() => document.activeElement?.dataset.id) === 'io');
      await page.keyboard.press('Enter');
      ok('enter opens AP4', await screenOf(page) === 'AP4');
      await go('AP3');
      await page.click('#ap-template-0');
      await page.keyboard.press('End');
      await page.click('[data-insert="{공간}"]');
      ok('chip inserts at cursor', (await page.inputValue('#ap-template-0')).endsWith('{검색어}{공간}'));
      ok('dirty status shown', (await page.textContent('[data-draft-status]')).includes('저장하지 않은 변경'));
      await go('AP6');
      for (const v of ['auth', 'format', 'ok']) {
        await page.selectOption('#mock-state', v);
        await page.waitForTimeout(30);
        const st = await page.evaluate(() => ({vis: [...document.querySelectorAll('[data-trial-variant]')].filter((e) => !e.hidden).map((e) => e.dataset.trialVariant), dis: document.querySelector('[data-author-action="draft_use_open"]').disabled}));
        ok(`AP6 ${v} variant`, st.vis.length >= 1 && st.vis.every((x) => x === v) && st.dis === (v !== 'ok'), JSON.stringify(st));
      }
      await page.click('.ew-draft-trial-row a');
      ok('result link shows toast, no navigation', !(await page.$eval('#mock-toast', (e) => e.hidden)) && page.url() === file);
      await page.click('[data-action="toggle-chat"]');
      await page.waitForTimeout(450);
      const closed = await page.evaluate(() => ({open: document.getElementById('ees-api-tools').dataset.chatOpen, work: document.getElementById('main-content').getBoundingClientRect().width}));
      ok('chat closes and work widens', closed.open === 'false' && closed.work === 1664, JSON.stringify(closed));
      await page.click('[data-action="toggle-chat"]');
      await go('AP7');
      await page.click('.ap-used-by .ew-author-link');
      ok('used-by opens AP2', await screenOf(page) === 'AP2');
      const sel = await page.evaluate(() => { const cs = getComputedStyle(document.querySelector('#ees-work-designer select[name="draft_system"]')); return {appearance: cs.appearance, bg: cs.backgroundImage}; });
      ok('product select cascade (appearance none, no background image)', sel.appearance === 'none' && sel.bg === 'none', JSON.stringify(sel));
    }
    ok(`${w} no page errors`, errors.length === 0, errors.join(' | '));
    await page.close();
  }
  await browser.close();
  const fails = results.filter((r) => r[0] === 'FAIL');
  for (const r of fails) console.log(r.join(' · '));
  console.log(`${results.length - fails.length}/${results.length} passed`);
  process.exit(fails.length ? 1 : 0);
})();
