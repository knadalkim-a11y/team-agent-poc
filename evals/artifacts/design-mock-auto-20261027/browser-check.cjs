const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require('playwright');
const { createHash } = require('crypto');
const { pathToFileURL } = require('url');
// Run with Node and Playwright installed. Optional browser executable:
// EES_MOCK_CHROMIUM_PATH=/path/to/chromium node browser-check.cjs
const repo = path.resolve(__dirname, '../../..');
const out = path.join(repo, 'evals/artifacts/design-mock-auto-20261027');
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
  const openControls = async () => {
    if (!await page.locator('button[data-mock-mode="auto"]').isVisible()) await page.locator('[data-mock-controls-toggle]').click();
  };
  const chooseMode = async mode => {
    await openControls();
    await page.locator(`button[data-mock-mode="${mode}"]`).click();
  };
  const autoState = async key => {
    await openControls();
    const details = page.locator('.mock-state-picker');
    if (!await details.evaluate(el => el.open)) await details.locator('summary').click();
    await page.locator(`[data-auto-state="${key}"]`).click();
  };
  const context = () => page.evaluate(() => ({
    title: document.querySelector('.mock-chat-title').textContent,
    request: document.querySelector('.chat-user .whitespace-pre-wrap').textContent,
    response: document.querySelector('#response-content-container .markdown-prose').innerHTML,
    workflow: [...document.querySelectorAll('[data-action="workflow"]')].map(b => [b.textContent.trim(), b.getAttribute('aria-current')])
  }));
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
    await capture('mock-revision3-1920-full');
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
      if (['menu','ready','confirmed'].includes(key)) await capture('mock-revision3-1920-' + key, true);
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
      if (width === 1200 || width === 1095 || width === 480) await capture('mock-revision3-' + width + '-full');
    }
    await load(480, 900);
    const controls = await page.locator('[data-mock-controls]').boundingBox();
    const panelBox = await page.locator('.ees-panel-region').boundingBox();
    assert(controls.x + controls.width <= panelBox.x);
    await page.locator('[data-mock-controls-toggle]').click();
    await select('ready');
    assert.equal(await page.locator('[data-mock-controls]').getAttribute('data-expanded'), 'false');
    assert(await page.locator('[data-vd-confirm]').isEnabled());
    await capture('mock-revision3-480-ready');
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
    // The human rendering and choices remain independent of the synthetic automatic example.
    await load(1920);
    const humanContext = await context();
    await select('ready');
    const humanReady = await page.locator('#ees-work-panel').innerHTML();
    await chooseMode('auto');
    assert.equal(await page.locator('#mock-screen').innerText(), '자동-1 점검 중');
    assert.equal(await page.locator('.mock-chat-title').innerText(), '일일 시스템 점검');
    assert.equal(await page.locator('[data-action="workflow"][aria-current="page"]').innerText(), '일일 시스템 점검');
    assert.match(await page.locator('.ew-run-back').innerText(), /10\.27 정기 점검 회차/);
    assert.equal(await page.locator('[data-vd-pick],[data-vd-confirm]').count(), 0);
    assert.equal(await page.locator('#ees-work-panel button').filter({hasText:/승인|확정|완료 처리|다음 작업/}).count(),0);
    check('Automatic example has independent daily-check context and no human approval', await context());
    for (const [key, expected, counts] of [
      ['checking','자동-1 점검 중',{passed:2,checking:1,waiting:1,blocked:0}],
      ['success','자동-2 자동 완료',{passed:4,checking:0,waiting:0,blocked:0}],
      ['blocked','자동-3 조건 미충족',{passed:3,checking:0,waiting:0,blocked:1}]
    ]) {
      await autoState(key);
      assert.equal(await page.locator('#mock-screen').innerText(),expected);
      assert.equal(await page.locator(`[data-auto-state="${key}"]`).getAttribute('aria-current'),'true');
      for (const [status,count] of Object.entries(counts)) assert.equal(await page.locator(`.ew-auto-item[data-status="${status}"]`).count(),count);
      assert.equal(await page.locator('.ew-auto-values').count(),4);
      if (key==='checking') {
        assert.deepEqual(await page.locator('.ew-auto-item[data-status="checking"] dd,.ew-auto-item[data-status="waiting"] dd').allInnerTexts(),['—','80% 이하','—','—','24시간 이내','—']);
        assert.equal(await page.locator('.ew-auto-footer button').count(),0);
      } else if (key==='success') {
        assert.match(await page.locator('.ew-auto-footer').innerText(),/4개 조건 모두 충족/);
        assert.match(await page.locator('.ew-auto-summary').innerText(),/09:00:04/);
      } else {
        assert.match(await page.locator('[data-auto-check="disk"]').innerText(),/92%[\s\S]*80% 이하[\s\S]*09:00:03/);
        assert.match(await page.locator('.ew-auto-footer').innerText(),/미완료[\s\S]*공간을 확보한 뒤 다시 점검/);
        assert.equal(await page.locator('.ew-auto-footer button').count(),0);
        assert.match(await page.locator('#response-content-container .markdown-prose').innerText(),/92%[\s\S]*80%[\s\S]*아직 완료되지/);
      }
      check('Automatic state: '+key,{label:expected,counts});
      await capture('mock-revision3-1920-auto-'+key,true);
      if(key==='success') await capture('mock-revision3-1920-auto-full');
    }
    await autoState('log');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-기록 (초안)');
    assert.match(await page.locator('.ew-vd-log').innerText(),/미완료로 남김/);
    assert.doesNotMatch(await page.locator('.ew-vd-log').innerText(),/자동 완료 처리함/);
    await capture('mock-revision3-1920-auto-blocked-log',true);
    await autoState('rules');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-기준 (초안)');
    assert.equal(await page.locator('.ew-auto-rule-list>div').count(),4);
    assert.match(await page.locator('.ew-vd-rules').innerText(),/모두 통과[\s\S]*측정값을 확인하지 못하면 완료하지/);
    await capture('mock-revision3-1920-auto-rules',true);
    await page.locator('[data-auto-tab="work"]').click();
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-3 조건 미충족');
    check('Blocked log and explicit completion criteria preserve blocked state',{});
    await chooseMode('human');
    assert.deepEqual(await context(),humanContext);
    assert.equal(await page.locator('#ees-work-panel').innerHTML(),humanReady);
    await page.locator('[data-vd-confirm]').click();
    const humanConfirmed = await page.locator('#ees-work-panel').innerHTML();
    await chooseMode('auto');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-3 조건 미충족');
    await autoState('success');
    await page.locator('.ew-auto-footer [data-auto-tab="log"]').click();
    assert.match(await page.locator('.ew-vd-log').innerText(),/4개 조건 충족 · 서비스가 자동 완료 처리함/);
    assert.doesNotMatch(await page.locator('.ew-vd-log').innerText(),/미완료로 남김/);
    await chooseMode('human');
    assert.equal(await page.locator('#ees-work-panel').innerHTML(),humanConfirmed);
    await chooseMode('auto');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-기록 (초안)');
    check('Mode switches exactly restore human selections, confirmed markup, context, and automatic tab',{});
    await page.locator('[data-auto-tab="rules"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-기준 (초안)');
    assert.equal(await page.locator('[data-auto-tab="rules"]:focus').count(),1);
    await page.locator('button[data-mock-mode="human"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#ees-work-panel').getAttribute('data-mock-mode'),'human');
    assert.equal(await page.locator('#ees-work-panel:focus').count(),1);
    await page.locator('button[data-mock-mode="auto"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#ees-work-panel').getAttribute('data-mock-mode'),'auto');
    await page.locator('.mock-state-picker summary').focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab'); await page.keyboard.press('Enter');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-1 점검 중');
    check('Automatic modes, presets and content tabs are keyboard-operable',{});
    // Repeated preset selection is deterministic; there is no running timer or real recheck action.
    await autoState('blocked'); await autoState('blocked');
    await chooseMode('human'); await chooseMode('auto');
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-3 조건 미충족');
    assert.equal(await page.locator('[data-auto-check="disk"] [data-measured]').innerText(),'92%');
    check('Repeated state selection and mode switches do not complete a failed check',{});
    for(const width of [1920,1200,480]) {
      await load(width,width===1920?1080:900);
      await chooseMode('auto');
      for(const key of ['checking','success','blocked']) {
        await autoState(key);
        const value=await layout();
        const panelWidth=Math.min(480,width-56);
        assert.equal(value.panel.width,panelWidth);assert.equal(value.panel.x,width-panelWidth);assert.equal(value.overflow,0);
        assert.equal(await page.locator('#ees-work-panel').evaluate(el=>el.scrollWidth-el.clientWidth),0);
        const footer=await page.locator('.ew-auto-footer').boundingBox();
        assert(footer.y+footer.height<= (width===1920?1080:900));
        assert.equal(await page.locator('[data-vd-pick],[data-vd-confirm]').count(),0);
        if(width!==1920) await capture(`mock-revision3-${width}-auto-${key}`);
      }
      check('Automatic states fit responsive shell at '+width,await layout());
    }
    await page.setViewportSize({width:1920,height:1080});
    await page.goto('about:blank'); // A direct link loads the document, unlike same-document hash navigation.
    await page.goto(pathToFileURL(html).href+'#auto-complete');
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.locator('#mock-screen').innerText(),'자동-2 자동 완료');
    assert.equal(await page.locator('.ew-auto-item[data-status="passed"]').count(),4);
    assert.equal(await page.locator('button[data-mock-mode="auto"]').getAttribute('aria-pressed'),'true');
    check('Direct #auto-complete link opens the completed synthetic example',{});
    assert.equal(report.requests.filter(u=>/^https?:/i.test(u)).length,0);
    assert.deepEqual(report.consoleErrors,[]); assert.deepEqual(report.pageErrors,[]);
    check('Offline load and interactions', {externalRequests:0,consoleErrors:0,pageErrors:0});
    report.result='pass';
  } catch (error) {
    report.result='fail'; report.error=String(error.stack || error);
    await capture('mock-revision3-failure');
    process.exitCode=1;
  } finally {
    fs.writeFileSync(path.join(out,'ui-browser-report.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();
    console.log(JSON.stringify({result:report.result,checks:report.checks.length,screenshots:report.screenshots,error:report.error},null,2));
  }
})();
