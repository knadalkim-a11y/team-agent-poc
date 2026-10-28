const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require('playwright');
const { createHash } = require('crypto');
const { pathToFileURL } = require('url');
// Run with Node and Playwright installed. Optional browser executable:
// EES_MOCK_CHROMIUM_PATH=/path/to/chromium node browser-check.cjs
const repo = path.resolve(__dirname, '../../..');
const out = path.join(repo, 'evals/artifacts/design-mock-review-20261027');
const html = path.join(repo, 'docs/mockups/ees-work/design-mock-04-cr-verdict.html');
fs.mkdirSync(out, { recursive: true });
const sha256 = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const source = path.join(repo, 'docs/mockups/ees-work/design-mock-src/04-cr-verdict.html');
const report = { source: path.relative(repo, source), sourceSha256: sha256(source), artifactSha256: sha256(html), artifact: path.relative(repo, html), checkedAt: new Date().toISOString(), checks: [], screenshots: [], requests: [], consoleErrors: [], pageErrors: [] };
(async () => {
  const executablePath = process.env.EES_MOCK_CHROMIUM_PATH || process.argv[2];
  const browser = await chromium.launch({ ...(executablePath ? { executablePath } : {}), headless: true, args: ['--no-sandbox'] });
  report.browser = browser.version();
  const page = await browser.newPage({ viewport: {width: 1920, height: 1080}, deviceScaleFactor: 1 });
  page.on('request', r => { if (!r.url().startsWith('data:')) report.requests.push(r.url().startsWith('file:') ? 'file:' + path.relative(repo, html) : r.url()); });
  page.on('pageerror', e => report.pageErrors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') report.consoleErrors.push(m.text()); });
  const check = (name, details) => report.checks.push({ name, result: 'pass', details });
  const capture = async (name, panelOnly = false) => {
    const file = name + '.png';
    if (panelOnly) await page.locator('.ees-panel-region').screenshot({ path: path.join(out, file) });
    else await page.screenshot({ path: path.join(out, file), fullPage: true });
    report.screenshots.push(file);
  };
  const load = async (width, height = 1080) => {
    await page.setViewportSize({width, height});
    await page.goto(pathToFileURL(html).href);
    await page.evaluate(() => document.fonts.ready);
  };
  const select = async key => {
    const details = page.locator('.mock-state-picker');
    if (!await details.evaluate(el => el.open)) await details.locator('summary').click();
    await page.locator(`[data-mock-state="${key}"]`).click();
    await page.waitForTimeout(230);
  };
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const layout = () => page.evaluate(() => ({
    width: innerWidth,
    sidebar: document.querySelector('.mock-sidebar').getBoundingClientRect().width,
    compact: document.querySelector('.mock-sidebar').dataset.compact,
    overlay: document.querySelector('.ees-panel-region').dataset.overlay,
    panel: {x: document.querySelector('.ees-panel-region').getBoundingClientRect().x, width: document.querySelector('.ees-panel-region').getBoundingClientRect().width},
    toggle: document.querySelector('[data-sidebar-toggle]').getAttribute('aria-expanded'),
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth
  }));
  try {
    await load(1920);
    const fonts = await page.evaluate(() => [...document.fonts].map(f => ({family: f.family, status: f.status})));
    assert(fonts.length === 2 && fonts.every(f => f.status === 'loaded'));
    check('Embedded product fonts loaded', fonts);
    await capture('mock-revision2-1920-full');
    for (const [key, expected] of [['initial', '④-1 고르는 중'], ['menu', '④-1a 판정 고르기'], ['ready', '④-2 확정 준비'], ['confirmed', '④-3 확정됨'], ['log', '④-기록 (초안)'], ['rules', '④-기준 (초안)']]) {
      await select(key);
      const label = await page.locator('#mock-screen').innerText();
      assert.equal(label, expected);
      assert.equal(await page.locator(`[data-mock-state="${key}"]`).getAttribute('aria-current'), 'true');
      if (key === 'initial') assert(await page.locator('.ew-vd-footer button').isDisabled());
      if (key === 'ready') assert(await page.locator('[data-vd-confirm]').isEnabled());
      if (key === 'confirmed') {
        assert.equal(await page.locator('[data-vd-pick]').count(), 0);
        assert.match(await page.locator('.ew-vd-meta').innerText(), /10\.27 14:25/);
      }
      check('Review state: ' + key, {label});
      if (['menu','ready','confirmed'].includes(key)) await capture('mock-revision2-1920-' + key, true);
    }
    await select('initial');
    await page.locator('[data-vd-pick="CR-2207"]').focus();
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('.ew-vd-option:focus').getAttribute('data-vd-choose'), 'ok');
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('.ew-vd-option:focus').getAttribute('data-vd-choose'), 'cond');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#mock-screen').innerText(), '④-2 확정 준비');
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(), 1);
    check('Keyboard verdict choice updates state and restores focus', {chosen:'cond', state:'ready'});
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.ew-vd-menu').count(), 0);
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(), 1);
    await page.locator('[data-vd-confirm]').click();
    assert.equal(await page.locator('#mock-screen').innerText(), '④-3 확정됨');
    check('Menu Escape restores trigger; confirmation reaches completed state', {});
    for (const [width, compact, overlay] of [[1920,false,false],[1440,false,false],[1439,true,false],[1366,true,false],[1200,true,false],[1096,true,false],[1095,true,true],[480,true,true]]) {
      await load(width, width < 1440 ? 900 : 1080);
      const value = await layout();
      assert.equal(value.compact, String(compact));
      assert.equal(value.sidebar, compact ? 56 : 256);
      assert.equal(value.overlay, String(overlay));
      assert.equal(value.overflow, 0);
      const panelWidth = Math.min(480, width - 56);
      assert.equal(value.panel.width, panelWidth);
      assert.equal(value.panel.x, width - panelWidth);
      if (compact) assert.equal(await page.locator('.ew-workflows details>button:visible').count(),0);
      check('Default responsive shell at ' + width, value);
      if (width === 1200 || width === 1095 || width === 480) await capture('mock-revision2-' + width + '-full');
    }
    await load(480, 900);
    const controls = await page.locator('[data-mock-controls]').boundingBox();
    const panelBox = await page.locator('.ees-panel-region').boundingBox();
    assert(controls.x + controls.width <= panelBox.x);
    await page.locator('[data-mock-controls-toggle]').click();
    await select('ready');
    assert.equal(await page.locator('[data-mock-controls]').getAttribute('data-expanded'), 'false');
    assert(await page.locator('[data-vd-confirm]').isEnabled());
    await capture('mock-revision2-480-ready');
    check('Narrow review controls keep footer clear and can select a state', {controls, panel:panelBox});
    await load(1200, 900);
    await page.locator('[data-sidebar-toggle]').click();
    let value = await layout();
    assert.equal(value.compact, 'false'); assert.equal(value.overlay, 'true');
    await page.setViewportSize({width:1250,height:900}); await settle();
    value = await layout();
    assert.equal(value.compact, 'false'); assert.equal(value.overlay, 'true');
    await page.setViewportSize({width:1500,height:900}); await settle();
    value = await layout();
    assert.equal(value.compact, 'false'); assert.equal(value.overlay, 'false');
    await page.locator('[data-sidebar-toggle]').click();
    await page.setViewportSize({width:1510,height:900}); await settle();
    value = await layout(); assert.equal(value.compact,'true');
    await page.setViewportSize({width:1200,height:900}); await settle();
    value = await layout(); assert.equal(value.compact,'true'); assert.equal(value.overlay,'false');
    check('Manual sidebar state persists within breakpoint, defaults reset on crossing', value);
    await page.setViewportSize({width:1095,height:900}); await settle();
    await page.locator('#ees-work-panel').focus();
    await page.keyboard.press('Escape');
    assert(await page.locator('.ees-panel-region').isHidden());
    assert.equal(await page.locator('#ees-work-panel-toggle:focus').count(),1);
    await page.locator('#ees-work-panel-toggle').click();
    assert(await page.locator('.ees-panel-region').isVisible());
    check('Overlay Escape closes panel and toggle restores it',{});
    assert.equal(report.requests.filter(u=>/^https?:/i.test(u)).length,0);
    assert.deepEqual(report.consoleErrors,[]); assert.deepEqual(report.pageErrors,[]);
    check('Offline load and interactions', {externalRequests:0,consoleErrors:0,pageErrors:0});
    report.result='pass';
  } catch (error) {
    report.result='fail'; report.error=String(error.stack || error);
    await capture('mock-revision2-failure');
    process.exitCode=1;
  } finally {
    fs.writeFileSync(path.join(out,'ui-browser-report.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();
    console.log(JSON.stringify({result:report.result,checks:report.checks.length,screenshots:report.screenshots,error:report.error},null,2));
  }
})();
