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
    const file='mock-revision6-'+name+'.png';
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
  const evidenceButton=id=>row(id).locator('button[data-vd-evidence]');
  const openEvidence=async id=>{if(await evidenceButton(id).getAttribute('aria-expanded')!=='true') await evidenceButton(id).click();};
  const closeEvidence=async id=>{if(await evidenceButton(id).getAttribute('aria-expanded')==='true') await evidenceButton(id).click();};
  const label=id=>row(id).locator('.ew-vd-origin>span').innerText();
  const actor=id=>row(id).locator('[data-decision-actor]').innerText();
  const status=id=>row(id).locator('[data-decision-status]').innerText();
  const recommendation=id=>row(id).locator('[data-ai-reference]').innerText();
  const selectVerdict=async(id,value)=>{await row(id).locator('[data-vd-pick]').click();await page.locator(`[data-vd-choose="${value}"]`).click();};
  try {
    await load();
    const fonts=await page.evaluate(()=>[...document.fonts].map(f=>({family:f.family,status:f.status})));
    assert.equal(fonts.length,2);assert(fonts.every(f=>f.status==='loaded'));
    check('Embedded product fonts load',fonts);
    assert.match(await page.title(),/6판/);
    assert.match(await page.locator('[data-person]').innerText(),/선택 0\/3/);
    assert.match(await page.locator('[data-service]').innerText(),/서비스 판정 완료 9\/9[\s\S]*승인 8 · 미승인 1/);
    for(const id of ['CR-2203','CR-2207','CR-2210']) {
      assert.equal(await actor(id),'사람 판정');assert.equal(await status(id),'판정 선택 전');
      assert.equal(await row(id).locator('[data-vd-pick]').innerText(),'판정 선택');
      assert.equal(await row(id).getAttribute('data-decision-state'),null);
    }
    assert.equal(await recommendation('CR-2203'),'AI 추천: 승인');
    assert.equal(await recommendation('CR-2210'),'AI 추천: 미승인');
    assert.equal(await row('CR-2207').locator('[data-ai-reference]').count(),0);
    assert.equal(await page.locator('.ew-vd-label[data-verdict="none"]').textContent(),'결정 필요3');
    assert.equal(await page.locator('.ew-vd-label[data-verdict="ok"]').textContent(),'승인8');
    assert.equal(await page.locator('.ew-vd-label[data-verdict="bad"]').textContent(),'미승인1');
    check('All three human choices start empty; two AI recommendations are separate and excluded from decision counts');
    await capture('1920-full');await capture('1920-panel',true);
    await page.locator('[data-vd-group]').click();
    assert.equal(await page.locator('[data-vd-item]').count(),12);
    assert.equal(await page.locator('[data-handler="human"]').count(),3);assert.equal(await page.locator('[data-handler="service"]').count(),9);
    assert.equal(await page.locator('button[data-vd-evidence]').count(),12);
    const alignment=await page.locator('[data-vd-item]').evaluateAll(els=>els.map(el=>({id:el.dataset.vdItem,label:el.querySelector('[data-vd-evidence]').textContent.trim(),parent:el.querySelector('[data-vd-evidence]').parentElement.className,right:el.querySelector('[data-vd-evidence]').getBoundingClientRect().right-el.getBoundingClientRect().right})));
    assert(alignment.every(v=>v.label==='판정 근거'&&v.parent==='ew-vd-origin'&&v.right===alignment[0].right));
    check('All twelve rows retain common evidence controls at the same horizontal position',alignment);
    const src=fs.readFileSync(source,'utf8');
    assert.doesNotMatch(src,/사람 3건 확정|AI 제안 · 확인 필요|직접 선택 · 확정 전|confirmVerdicts|data-vd-confirm|S\.confirmed|data-human-confirmation|data-mock-state="(?:ready|confirmed)"/);
    assert.equal(await page.locator('#ees-work-panel .ew-vd-footer').count(),0);
    check('Batch finalization control, handler, preview and claims are removed without replacement save or finalize actions');
    const observations={},originalProposals={};
    for(const id of ['CR-2203','CR-2207','CR-2210']) {
      await openEvidence(id);
      observations[id]=await row(id).locator('[data-observation]').innerText();
      assert.equal(await row(id).locator('table').count(),0);
      assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/근거 확인 시각 · 미기록[\s\S]*아직 판정을 선택하지 않았습니다/);
      if(id==='CR-2207') assert.match(observations[id],/test_v2_final\.xlsx는 있습니다[\s\S]*최종본 여부는 확인되지/);
      else {
        originalProposals[id]=await row(id).locator('[data-original-proposal]').innerText();
        assert.match(originalProposals[id],id==='CR-2210'?/AI 추천: 미승인/:/AI 추천: 승인/);
      }
      if(id==='CR-2210') {
        assert.equal(observations[id],'설계서와 테스트 결과가 없습니다.');
        assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/배포 계획서의 상태는 이 근거에 기록되지/);
        await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);await capture('1920-rights-evidence',true);
      }
      if(id==='CR-2203') assert.match(observations[id],/AI 추천의 구체적인 근거가 확인되지/);
      await closeEvidence(id);
    }
    check('Human evidence preserves missing/unverified facts and separately records the correct original recommendations');
    for(const [id,result] of [['CR-2204','미승인'],['CR-2201','승인']]) {
      await openEvidence(id);assert.equal(await actor(id),'서비스 판정');assert.equal(await status(id),'자동 판정 완료');
      assert.equal(await row(id).locator('button[data-vd-pick]').count(),0);assert.equal(await row(id).getAttribute('data-decision-state'),'complete');
      assert.equal(await row(id).locator('.ew-vd-final').innerText(),result);assert.equal(await row(id).locator('tbody tr').count(),3);
      assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/판정 주체 · 서비스[\s\S]*10\.27 14:20/);
      if(id==='CR-2204') {assert.equal(await row(id).locator('[data-missing]').innerText(),'없음');assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/미승인. 판정은 완료/);}
      await closeEvidence(id);
    }
    check('Service approval and rejection remain completed, read-only and linked to unchanged conditions and observations');
    const automaticBefore=await allAuto();
    for(const id of ['CR-2210','CR-2204']) {
      await evidenceButton(id).focus();await page.keyboard.press('Enter');
      assert.equal(await evidenceButton(id).innerText(),'판정 근거');assert.equal(await evidenceButton(id).getAttribute('aria-expanded'),'true');
      assert.equal(await evidenceButton(id).getAttribute('aria-controls'),'evidence-'+id);assert.equal(await row(id).locator('button[data-vd-evidence]:focus').count(),1);
      await page.keyboard.press('Enter');assert.equal(await evidenceButton(id).getAttribute('aria-expanded'),'false');assert.equal(await row(id).locator('.ew-vd-evidence').count(),0);
      assert.equal(await row(id).locator('button[data-vd-evidence]:focus').count(),1);
    }
    check('Evidence Enter toggle keeps its name, expanded state and keyboard focus');
    await openEvidence('CR-2210');await selectVerdict('CR-2210','ok');
    assert.equal(await actor('CR-2210'),'사람 판정');assert.equal(await status('CR-2210'),'선택: 승인');
    assert.equal(await recommendation('CR-2210'),'AI 추천: 미승인');assert.equal(await row('CR-2210').locator('[data-original-proposal]').innerText(),originalProposals['CR-2210']);
    assert.match(await row('CR-2210').locator('[data-human-selection]').innerText(),/10\.27 14:24 · 김광재가 승인 선택/);
    assert.equal(await row('CR-2210').locator('[data-observation]').innerText(),observations['CR-2210']);assert.equal(await row('CR-2210').getAttribute('data-decision-state'),null);
    assert.match(await page.locator('[data-person]').innerText(),/선택 1\/3/);
    await row('CR-2210').scrollIntoViewIfNeeded();await capture('1920-selected',true);await closeEvidence('CR-2210');
    check('Human approval can differ from the rights-group AI rejection without rewriting recommendation, evidence or finalization state');
    await selectVerdict('CR-2203','bad');await openEvidence('CR-2203');
    assert.equal(await status('CR-2203'),'선택: 미승인');assert.equal(await recommendation('CR-2203'),'AI 추천: 승인');
    assert.equal(await row('CR-2203').locator('[data-original-proposal]').innerText(),originalProposals['CR-2203']);assert.equal(await row('CR-2203').locator('[data-observation]').innerText(),observations['CR-2203']);
    await closeEvidence('CR-2203');check('Opposite human selection preserves the original AI approval and unverified supporting evidence');
    await row('CR-2207').locator('[data-vd-pick]').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(),1);
    await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    assert.equal(await status('CR-2207'),'선택: 조건부 승인');assert.match(await page.locator('[data-person]').innerText(),/선택 3\/3/);
    assert.equal(await page.locator('[data-vd-pick]').count(),3);assert.equal(await page.locator('[data-handler="human"][data-decision-state]').count(),0);
    assert.equal(await page.locator('[data-vd-confirm], [data-human-confirmation]').count(),0);
    await openEvidence('CR-2207');assert.equal(await row('CR-2207').locator('[data-observation]').innerText(),observations['CR-2207']);await closeEvidence('CR-2207');
    check('Keyboard menu works after footer removal; selecting all three does not create or imply a finalization action');
    assert.deepEqual(await allAuto(),automaticBefore);check('All nine service rows remain byte-for-byte unchanged after human choices');
    await page.locator('[data-vd-tab="log"]').click();
    assert.match(await page.locator('.ew-vd-log').innerText(),/AI 추천 · CR-2203 승인, CR-2210 미승인 · 사람의 선택과 별도/);
    assert.match(await page.locator('.ew-vd-log').innerText(),/김광재가 CR-2210을 승인 선택/);assert.doesNotMatch(await page.locator('.ew-vd-log').innerText(),/확정/);
    await page.locator('[data-vd-tab="rules"]').click();assert.match(await page.locator('.ew-vd-rules').innerText(),/‘AI 추천’은 참고 정보이며 사람의 선택과 별개/);assert.doesNotMatch(await page.locator('.ew-vd-rules').innerText(),/확정/);
    check('Log and rules distinguish reference recommendations from human selections without extra workflow claims');
    for(const [key,name] of [['initial','④-1 항목별 판정'],['menu','④-1a 사람 판정 고르기'],['evidence','④-1b 판정 근거'],['log','④-기록 (초안)'],['rules','④-기준 (초안)']]) {
      await select(key);assert.equal(await page.locator('#mock-screen').innerText(),name);assert.equal(await page.locator(`button[data-mock-state="${key}"]`).getAttribute('aria-current'),'true');
    }
    assert.equal(await page.locator('button[data-mock-state]').count(),5);check('Five retained review presets work; arbitrary ready and confirmed presets are absent');
    await page.locator('[data-mock-info]').click();assert.match(await page.locator('.mock-info').innerText(),/저장·최종 확정하는 방법은 아직 정하지 않았습니다/);
    await page.locator('[data-mock-reset]').click();
    assert.match(await page.locator('[data-person]').innerText(),/선택 0\/3/);assert.equal(await recommendation('CR-2210'),'AI 추천: 미승인');
    await openEvidence('CR-2210');assert.equal(await row('CR-2210').locator('[data-human-selection]').count(),0);await closeEvidence('CR-2210');
    check('Mock help leaves actual finalization undecided; reset clears selections while preserving recommendations');
    for(const width of [1920,1200,480]) {
      await load(width,width===1920?1080:900);
      const value=await layout(),panelWidth=Math.min(480,width-56);
      assert.equal(value.sidebar,width===1920?256:56);assert.equal(value.panel.width,panelWidth);assert.equal(value.panel.x,width-panelWidth);assert.equal(value.overflow,0);assert.equal(value.overlay,String(width===480));
      for(const id of ['CR-2203','CR-2207','CR-2210','CR-2204','CR-2201']) {
        const button=await evidenceButton(id).boundingBox(),origin=await row(id).locator('.ew-vd-origin>span').boundingBox();
        assert(origin.x+origin.width<=button.x);assert(button.x+button.width<=width);assert.equal(await evidenceButton(id).innerText(),'판정 근거');
      }
      assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);
      if(width===480) await capture('480-full');
      check('Stable actor, state, reference and common evidence fit at '+width,value);
    }
    await openEvidence('CR-2210');await row('CR-2210').scrollIntoViewIfNeeded();await capture('480-rights-evidence');
    assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);await closeEvidence('CR-2210');
    await row('CR-2210').locator('[data-vd-pick]').click();
    const menuBox=await page.locator('.ew-vd-menu').boundingBox(),panelBox=await page.locator('#ees-work-panel').boundingBox();
    assert(menuBox.x>=panelBox.x&&menuBox.y>=panelBox.y&&menuBox.x+menuBox.width<=panelBox.x+panelBox.width&&menuBox.y+menuBox.height<=panelBox.y+panelBox.height);
    await page.keyboard.press('Escape');check('Narrow rights evidence and dropdown fit the panel without the removed footer');
    await page.locator('#ees-work-panel').focus();await page.keyboard.press('Escape');assert(await page.locator('.ees-panel-region').isHidden());assert.equal(await page.locator('#ees-work-panel-toggle:focus').count(),1);
    await page.keyboard.press('Enter');assert(await page.locator('.ees-panel-region').isVisible());check('Overlay keyboard close and reopen remain functional');
    await load(1920,1080,'#auto-evidence');assert.equal(await row('CR-2204').locator('.ew-vd-evidence').count(),1);check('Existing service-evidence deep link remains valid');
    assert.equal(report.requests.filter(u=>/^https?:/i.test(u)).length,0);assert.deepEqual(report.consoleErrors,[]);assert.deepEqual(report.pageErrors,[]);
    check('Offline load and interactions have no external requests or console/page errors');report.result='pass';
  } catch(error) {
    report.result='fail';report.error=String(error.stack||error);process.exitCode=1;await capture('failure');
  } finally {
    const reportPath=path.join(out,'ui-browser-report.json');
    if(fs.existsSync(reportPath)) {const previous=JSON.parse(fs.readFileSync(reportPath,'utf8'));if(previous.result==='fail') fs.copyFileSync(reportPath,path.join(out,'ui-browser-report-failure-'+previous.checkedAt.replace(/[:.]/g,'-')+'.json'));}
    fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');await browser.close();
    console.log(JSON.stringify({result:report.result,checks:report.checks.length,screenshots:report.screenshots,error:report.error},null,2));
  }
})();
