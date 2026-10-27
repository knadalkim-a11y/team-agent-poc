const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { createHash } = require('crypto');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');
// Run with Node + Playwright; optional installed Chromium path via env or first argument.
// EES_MOCK_CHROMIUM_PATH=/path/to/chromium node browser-check.cjs
const repo = path.resolve(__dirname, '../../..');
const out = __dirname;
const source = path.join(repo, 'docs/mockups/ees-work/design-mock-src/04-cr-verdict.html');
const html = path.join(repo, 'docs/mockups/ees-work/design-mock-04-cr-verdict.html');
const sha = f => createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const report = { source:path.relative(repo,source), sourceSha256:sha(source), artifact:path.relative(repo,html), artifactSha256:sha(html), artifactBytes:fs.statSync(html).size, checkedAt:new Date().toISOString(), checks:[], screenshots:[], requests:[], consoleErrors:[], pageErrors:[] };
(async () => {
  const executablePath = process.env.EES_MOCK_CHROMIUM_PATH || process.argv[2];
  const browser = await chromium.launch({...(executablePath ? {executablePath} : {}),headless:true,args:['--no-sandbox']});
  report.browser = browser.version();
  const page = await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  page.on('request',r => {if(!r.url().startsWith('data:')) report.requests.push(r.url().startsWith('file:') ? 'file:'+path.relative(repo,html) : r.url());});
  page.on('console',m => {if(m.type()==='error') report.consoleErrors.push(m.text());});
  page.on('pageerror',e => report.pageErrors.push(String(e)));
  const check=(name,details={})=>report.checks.push({name,result:'pass',details});
  const capture=async(name,panel=false)=>{
    const file='mock-revision4-'+name+'.png';
    if(panel) await page.locator('.ees-panel-region').screenshot({path:path.join(out,file)});
    else await page.screenshot({path:path.join(out,file),fullPage:true});
    report.screenshots.push(file);
  };
  const load=async(width=1920,height=1080,hash='')=>{
    await page.setViewportSize({width,height});
    await page.goto('about:blank');
    await page.goto(pathToFileURL(html).href+hash);
    await page.evaluate(()=>document.fonts.ready);
  };
  const openControls=async()=>{if(!await page.locator('[data-mock-info]').isVisible()) await page.locator('[data-mock-controls-toggle]').click();};
  const select=async key=>{
    await openControls();
    const picker=page.locator('.mock-state-picker');
    if(!await picker.evaluate(e=>e.open)) await picker.locator('summary').click();
    await page.locator(`button[data-mock-state="${key}"]`).click();
  };
  const row=id=>page.locator(`[data-vd-item="${id}"]`);
  const allAuto=()=>page.locator('[data-handler="service"]').evaluateAll(els=>els.map(e=>e.outerHTML));
  const layout=()=>page.evaluate(()=>{
    const box=document.querySelector('.ees-panel-region').getBoundingClientRect();
    return {width:innerWidth,sidebar:document.querySelector('.mock-sidebar').getBoundingClientRect().width,compact:document.querySelector('.mock-sidebar').dataset.compact,overlay:document.querySelector('.ees-panel-region').dataset.overlay,panel:{x:box.x,width:box.width},overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};
  });
  const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  try {
    await load();
    const fonts=await page.evaluate(()=>[...document.fonts].map(f=>({family:f.family,status:f.status})));
    assert.equal(fonts.length,2);assert(fonts.every(f=>f.status==='loaded'));
    check('Embedded product fonts load',fonts);
    assert.equal(await page.locator('#mock-screen').innerText(),'④-1 항목별 판정');
    assert.equal(await page.locator('button[data-mock-mode]').count(),0);
    assert.match(await page.locator('.ew-run-back').innerText(),/10\.13 배포 회차/);
    assert.equal(await row('CR-2207').getAttribute('data-handler'),'human');
    assert.equal(await row('CR-2204').getAttribute('data-handler'),'service');
    assert.equal(await row('CR-2201').getAttribute('data-handler'),'service');
    assert.match(await page.locator('#response-content-container').innerText(),/서비스 자동 판정 대상 9건[\s\S]*사람 판정 대상 3건/);
    check('Default view combines human and automatic CRs in the same workflow');
    assert.match(await page.locator('[data-person]').innerText(),/사람 미확정 3건[\s\S]*판정 선택 2\/3/);
    assert.match(await page.locator('[data-service]').innerText(),/자동 판정 완료 9\/9[\s\S]*승인 8 · 미승인 1/);
    assert(await page.locator('.ew-vd-footer button').isDisabled());
    assert.equal(await page.locator('.ew-vd-footer button').innerText(),'사람 3건 확정');
    check('Separate human pending and automatic completed counts; human-only disabled confirmation');
    for(const [id,result] of [['CR-2204','미승인'],['CR-2201','승인']]) {
      assert.equal(await row(id).getAttribute('data-decision-state'),'complete');
      assert.equal(await row(id).locator('button[data-vd-pick]').count(),0);
      assert.equal(await row(id).locator('.ew-vd-final').innerText(),result);
      assert.match(await row(id).innerText(),/서비스 자동 판정 · 판정 완료/);
    }
    assert.match(await row('CR-2204').innerText(),/테스트 없음/);
    check('Automatic approval and rejection are read-only completed decisions');
    await capture('1920-full');await capture('1920-panel',true);
    await row('CR-2204').locator('button[data-vd-evidence]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await row('CR-2204').locator('button').getAttribute('aria-expanded'),'true');
    assert.equal(await row('CR-2204').locator('button:focus').count(),1);
    assert.deepEqual(await row('CR-2204').locator('tbody tr').allInnerTexts(),['설계서\t있음\t있음','테스트 결과\t있음\t없음','배포 계획서\t있음\t있음']);
    assert.match(await row('CR-2204').locator('.ew-vd-evidence').innerText(),/10\.27 14:20[\s\S]*미승인. 판정은 완료/);
    await capture('1920-auto-evidence',true);
    await page.keyboard.press('Enter');
    assert.equal(await row('CR-2204').locator('.ew-vd-evidence').count(),0);
    assert.equal(await row('CR-2204').locator('button:focus').count(),1);
    check('Rejection evidence exposes condition, observation and timestamp; keyboard expands and collapses');
    await row('CR-2201').locator('button[data-vd-evidence]').click();
    assert.equal(await row('CR-2201').locator('[data-missing]').count(),0);
    assert.match(await row('CR-2201').locator('.ew-vd-evidence').innerText(),/필수 문서 모두 있음 → 승인/);
    await row('CR-2201').locator('button[data-vd-evidence]').click();
    check('Approved automatic item exposes corresponding successful evidence');
    await page.locator('[data-vd-group]').click();
    assert.equal(await page.locator('[data-vd-item]').count(),12);
    assert.equal(await page.locator('[data-handler="human"]').count(),3);
    assert.equal(await page.locator('[data-handler="service"]').count(),9);
    assert.equal(await page.locator('button[data-vd-pick]').count(),3);
    const automaticBefore=await allAuto();
    check('Expanded list contains exactly three editable human and nine automatic items');
    await page.locator('[data-vd-pick="CR-2207"]').focus();await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('.ew-vd-option:focus').getAttribute('data-vd-choose'),'ok');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.ew-vd-menu').count(),0);
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(),1);
    check('Human verdict menu keyboard opening and Escape restore focus');
    await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    assert.equal(await page.locator('#mock-screen').innerText(),'④-2 사람 판정 확정 준비');
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(),1);
    assert(await page.locator('[data-vd-confirm]').isEnabled());
    assert.match(await page.locator('.ew-vd-footer').innerText(),/사람 대상 3건만 확정/);
    assert.deepEqual(await allAuto(),automaticBefore);
    check('Choosing the remaining human verdict enables human-only confirmation without changing automatic items');
    await page.locator('[data-vd-confirm]').click();
    assert.equal(await page.locator('#mock-screen').innerText(),'④-3 사람 판정 확정됨');
    assert.equal(await page.locator('button[data-vd-pick]').count(),0);
    assert.match(await page.locator('[data-person]').innerText(),/사람 3건 확정/);
    await page.locator('.ew-vd-footer [data-vd-tab="log"]').click();
    const log=await page.locator('.ew-vd-log').innerText();
    assert.match(log,/사람 대상 3건의 판정을 확정함 \(CR-2203, CR-2207, CR-2210\)/);
    assert.doesNotMatch(log,/12건 판정을 확정|자동.*확정함/);
    assert.match(log,/서비스가 자동 대상 9건의 판정을 완료/);
    check('Confirmation log attributes only three human items to the person');
    await page.locator('[data-vd-tab="work"]').click();
    assert.deepEqual(await allAuto(),automaticBefore);
    assert.equal(await row('CR-2204').locator('.ew-vd-final').innerText(),'미승인');
    check('Human confirmation preserves all nine automatic results and evidence');
    await page.locator('[data-vd-tab="rules"]').click();
    assert.match(await page.locator('.ew-vd-rules').innerText(),/자동 결과는 여기서 수정하거나 사람 확정에 포함하지 않습니다/);
    check('Rules explain separate human confirmation and automatic decision completion');
    for(const [key,label] of [['initial','④-1 항목별 판정'],['menu','④-1a 사람 판정 고르기'],['evidence','④-1b 자동 판정 근거'],['ready','④-2 사람 판정 확정 준비'],['confirmed','④-3 사람 판정 확정됨'],['log','④-기록 (초안)'],['rules','④-기준 (초안)']]) {
      await select(key);
      assert.equal(await page.locator('#mock-screen').innerText(),label);
      assert.equal(await page.locator(`button[data-mock-state="${key}"]`).getAttribute('aria-current'),'true');
      if(key==='ready') await capture('1920-human-ready',true);
      if(key==='confirmed') await capture('1920-human-confirmed',true);
    }
    check('Seven review presets describe the same mixed CR list');
    await page.locator('[data-mock-info]').click();await page.locator('[data-mock-reset]').click();
    assert.equal(await page.locator('#mock-screen').innerText(),'④-1 항목별 판정');
    assert(await page.locator('.ew-vd-footer button').isDisabled());
    assert.equal(await page.locator('.ew-vd-evidence').count(),0);
    assert.equal(await row('CR-2204').locator('.ew-vd-final').innerText(),'미승인');
    check('Reset restores pending human selection while preserving seeded automatic decisions');
    for(const width of [1920,1200,480]) {
      await load(width,width===1920?1080:900);
      const value=await layout(), panelWidth=Math.min(480,width-56);
      assert.equal(value.sidebar,width===1920?256:56);assert.equal(value.panel.width,panelWidth);assert.equal(value.panel.x,width-panelWidth);assert.equal(value.overflow,0);
      assert.equal(value.overlay,String(width===480));
      const footer=await page.locator('.ew-vd-footer').boundingBox();
      for(const id of ['CR-2207','CR-2204','CR-2201']) { const box=await row(id).boundingBox();assert(box.y>=0 && box.y+box.height<=footer.y); }
      assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);
      if(width!==1920) await capture(width+'-full');
      check('Default mixed list and automatic results visible at '+width,value);
    }
    await row('CR-2204').locator('button[data-vd-evidence]').click();
    assert.equal(await row('CR-2204').locator('.ew-vd-evidence').count(),1);
    assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);
    const controls=await page.locator('[data-mock-controls]').boundingBox(), narrowPanel=await page.locator('.ees-panel-region').boundingBox();
    assert(controls.x+controls.width<=narrowPanel.x);
    await capture('480-auto-evidence');
    check('Narrow evidence opens without horizontal overflow or mock-control footer obstruction');
    await load(1200,900);await page.locator('[data-sidebar-toggle]').click();
    assert.equal((await layout()).overlay,'true');assert.equal((await layout()).sidebar,256);
    await page.setViewportSize({width:1250,height:900});await settle();assert.equal((await layout()).compact,'false');
    await page.setViewportSize({width:1500,height:900});await settle();assert.equal((await layout()).overlay,'false');
    check('Manual sidebar and breakpoint-dependent panel overlay remain aligned with product shell');
    const handle=page.locator('.ees-panel-resize');await handle.focus();await page.keyboard.press('ArrowLeft');
    assert.equal((await layout()).panel.width,496);await page.keyboard.press('Home');assert.equal((await layout()).panel.width,400);
    check('Keyboard panel resizing preserves the product width bounds');
    await load(480,900);await page.locator('#ees-work-panel').focus();await page.keyboard.press('Escape');
    assert(await page.locator('.ees-panel-region').isHidden());assert.equal(await page.locator('#ees-work-panel-toggle:focus').count(),1);
    await page.keyboard.press('Enter');assert(await page.locator('.ees-panel-region').isVisible());
    check('Narrow overlay closes with Escape and reopens from focused toggle');
    await load(1920,1080,'#auto-evidence');
    assert.equal(await page.locator('#mock-screen').innerText(),'④-1b 자동 판정 근거');
    assert.equal(await row('CR-2204').locator('.ew-vd-evidence').count(),1);
    assert.equal(await row('CR-2207').getAttribute('data-handler'),'human');
    check('Direct evidence link opens within the same mixed list');
    assert.equal(report.requests.filter(u=>/^https?:/i.test(u)).length,0);assert.deepEqual(report.consoleErrors,[]);assert.deepEqual(report.pageErrors,[]);
    check('Offline load and interactions have no external requests or console/page errors');
    report.result='pass';
  } catch(error) {
    report.result='fail';report.error=String(error.stack||error);process.exitCode=1;
    await capture('failure');
  } finally {
    const reportPath=path.join(out,'ui-browser-report.json');
    if(fs.existsSync(reportPath)) {
      const previous=JSON.parse(fs.readFileSync(reportPath,'utf8'));
      if(previous.result==='fail') fs.copyFileSync(reportPath,path.join(out,'ui-browser-report-failure-'+previous.checkedAt.replace(/[:.]/g,'-')+'.json'));
    }
    fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');await browser.close();
    console.log(JSON.stringify({result:report.result,checks:report.checks.length,screenshots:report.screenshots,error:report.error},null,2));
  }
})();
