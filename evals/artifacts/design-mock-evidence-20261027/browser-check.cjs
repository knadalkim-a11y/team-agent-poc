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
    const file='mock-revision5-'+name+'.png';
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
  try {
    await load();
    const fonts=await page.evaluate(()=>[...document.fonts].map(f=>({family:f.family,status:f.status})));
    assert.equal(fonts.length,2);assert(fonts.every(f=>f.status==='loaded'));
    check('Embedded product fonts load',fonts);
    assert.equal(await page.locator('#mock-screen').innerText(),'④-1 항목별 판정');
    assert.equal(await label('CR-2207'),'직접 판정 필요');
    assert.equal(await label('CR-2210'),'AI 제안 · 확인 필요');
    assert.equal(await label('CR-2204'),'자동 판정 완료');
    assert.equal(await label('CR-2201'),'자동 판정 완료');
    assert.match(await page.locator('[data-person]').innerText(),/사람 미확정 3건[\s\S]*판정 선택 2\/3/);
    assert.match(await page.locator('[data-service]').innerText(),/자동 판정 완료 9\/9/);
    assert(await page.locator('.ew-vd-footer button').isDisabled());
    check('Default view distinguishes direct decision, unconfirmed AI proposal, and automatic completion');
    await capture('1920-full');await capture('1920-panel',true);
    await page.locator('[data-vd-group]').click();
    assert.equal(await page.locator('[data-vd-item]').count(),12);
    assert.equal(await page.locator('[data-handler="human"]').count(),3);
    assert.equal(await page.locator('[data-handler="service"]').count(),9);
    assert.equal(await page.locator('button[data-vd-evidence]').count(),12);
    const alignment=await page.locator('[data-vd-item]').evaluateAll(els=>els.map(el=>({id:el.dataset.vdItem,label:el.querySelector('[data-vd-evidence]').textContent.trim(),parent:el.querySelector('[data-vd-evidence]').parentElement.className,right:el.querySelector('[data-vd-evidence]').getBoundingClientRect().right-el.getBoundingClientRect().right})));
    assert(alignment.every(v=>v.label==='판정 근거'&&v.parent==='ew-vd-origin'&&v.right===alignment[0].right));
    check('All twelve rows use the same evidence button label, structure and horizontal position',alignment);
    assert.doesNotMatch(await page.locator('body').innerText(),/대화에서 채움|파란 말풍선/);
    assert.doesNotMatch(fs.readFileSync(source,'utf8'),/대화에서 채움|대화에서 채운|대화에서 초안|말풍선|icon\(ICON\.chat\)/);
    check('Ambiguous chat-filled labels and icon-only source indicators are removed');
    const observations={};
    await openEvidence('CR-2207');
    observations['CR-2207']=await row('CR-2207').locator('[data-observation]').innerText();
    assert.match(observations['CR-2207'],/test_v2_final\.xlsx는 있습니다[\s\S]*최종본 여부는 확인되지/);
    assert.equal(await row('CR-2207').locator('table').count(),0);
    assert.match(await row('CR-2207').locator('.ew-vd-evidence').innerText(),/근거 확인 시각 · 미기록[\s\S]*아직 판정을 선택하지/);
    assert.equal(await row('CR-2207').locator('.ew-vd-file').count(),1);
    await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);
    await capture('1920-human-evidence',true);
    await closeEvidence('CR-2207');
    check('Unselected human item preserves attachment existence and unresolved final-version check');
    await openEvidence('CR-2210');
    observations['CR-2210']=await row('CR-2210').locator('[data-observation]').innerText();
    assert.equal(observations['CR-2210'],'설계서와 테스트 결과가 없습니다.');
    assert.match(await row('CR-2210').locator('.ew-vd-evidence').innerText(),/배포 계획서의 상태는 이 근거에 기록되지/);
    assert.match(await row('CR-2210').locator('[data-original-proposal]').innerText(),/AI 제안: 미승인/);
    assert.equal(await row('CR-2210').locator('table').count(),0);
    await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);
    await capture('1920-ai-evidence',true);
    await closeEvidence('CR-2210');
    check('AI rejection evidence states known missing documents without inventing unknown document status');
    await openEvidence('CR-2203');
    observations['CR-2203']=await row('CR-2203').locator('[data-observation]').innerText();
    assert.match(observations['CR-2203'],/AI 제안의 구체적인 근거가 확인되지 않았습니다/);
    assert.match(await row('CR-2203').locator('[data-original-proposal]').innerText(),/AI 제안: 승인/);
    assert.equal(await row('CR-2203').locator('table').count(),0);
    assert.equal(await label('CR-2203'),'AI 제안 · 확인 필요');
    await closeEvidence('CR-2203');
    check('AI approval remains a proposal with explicitly unverified supporting evidence');
    for(const [id,result] of [['CR-2204','미승인'],['CR-2201','승인']]) {
      await openEvidence(id);
      assert.equal(await row(id).locator('button[data-vd-pick]').count(),0);
      assert.equal(await row(id).getAttribute('data-decision-state'),'complete');
      assert.equal(await row(id).locator('.ew-vd-final').innerText(),result);
      assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/판정 주체 · 서비스[\s\S]*10\.27 14:20/);
      assert.equal(await row(id).locator('tbody tr').count(),3);
      if(id==='CR-2204') {
        assert.equal(await row(id).locator('[data-missing]').innerText(),'없음');
        assert.match(await row(id).locator('.ew-vd-evidence').innerText(),/미승인. 판정은 완료/);
        await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);await capture('1920-auto-evidence',true);
      } else assert.equal(await row(id).locator('[data-missing]').count(),0);
      await closeEvidence(id);
    }
    check('Automatic approval/rejection retain read-only results, conditions, observations, service actor and time');
    for(const id of ['CR-2207','CR-2204']) {
      await evidenceButton(id).focus();await page.keyboard.press('Enter');
      assert.equal(await evidenceButton(id).innerText(),'판정 근거');
      assert.equal(await evidenceButton(id).getAttribute('aria-expanded'),'true');
      assert.equal(await evidenceButton(id).getAttribute('aria-controls'),'evidence-'+id);
      assert.equal(await row(id).locator('button[data-vd-evidence]:focus').count(),1);
      await page.keyboard.press('Enter');
      assert.equal(await evidenceButton(id).getAttribute('aria-expanded'),'false');
      assert.equal(await evidenceButton(id).innerText(),'판정 근거');
      assert.equal(await row(id).locator('.ew-vd-evidence').count(),0);
      assert.equal(await row(id).locator('button[data-vd-evidence]:focus').count(),1);
    }
    check('Common evidence control keeps its name and keyboard focus through opening and closing');
    await openEvidence('CR-2203');
    await page.locator('[data-vd-pick="CR-2203"]').click();await page.locator('[data-vd-choose="bad"]').click();
    assert.equal(await label('CR-2203'),'직접 선택 · 확정 전');
    assert.match(await row('CR-2203').locator('[data-original-proposal]').innerText(),/AI 제안: 승인/);
    assert.match(await row('CR-2203').locator('[data-human-selection]').innerText(),/10\.27 14:24 · 김광재가 미승인 선택 · 확정 전/);
    assert.equal(await row('CR-2203').locator('[data-observation]').innerText(),observations['CR-2203']);
    await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);
    await capture('1920-ai-to-human',true);
    await closeEvidence('CR-2203');
    check('Changing AI approval to human rejection preserves the original approval proposal and unverified evidence');
    const automaticBefore=await allAuto();
    await page.locator('[data-vd-pick="CR-2207"]').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-vd-pick="CR-2207"]:focus').count(),1);
    await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    assert.equal(await label('CR-2207'),'직접 선택 · 확정 전');
    assert.equal(await page.locator('#mock-screen').innerText(),'④-2 사람 판정 확정 준비');
    assert(await page.locator('[data-vd-confirm]').isEnabled());
    await openEvidence('CR-2207');
    assert.equal(await row('CR-2207').locator('[data-observation]').innerText(),observations['CR-2207']);
    assert.match(await row('CR-2207').locator('[data-human-selection]').innerText(),/조건부 승인 선택 · 확정 전/);
    await closeEvidence('CR-2207');
    assert.deepEqual(await allAuto(),automaticBefore);
    check('Keyboard human selection enables human-only confirmation while preserving original observation and automatic items');
    await page.locator('[data-vd-confirm]').click();
    for(const id of ['CR-2203','CR-2207','CR-2210']) assert.equal(await label(id),'김광재가 확정');
    assert.equal(await page.locator('[data-vd-pick]').count(),0);
    assert.deepEqual(await allAuto(),automaticBefore);
    check('Confirmation labels all three human decisions by name and leaves all nine service entries unchanged');
    for(const id of ['CR-2203','CR-2207','CR-2210']) {
      await openEvidence(id);
      assert.equal(await row(id).locator('[data-observation]').innerText(),observations[id]);
      assert.match(await row(id).locator('[data-human-confirmation]').innerText(),/10\.27 14:25 · 김광재가 확정/);
      if(id==='CR-2203') {
        assert.match(await row(id).locator('[data-original-proposal]').innerText(),/AI 제안: 승인/);
        assert.match(await row(id).locator('[data-human-confirmation]').innerText(),/미승인/);
      }
      await closeEvidence(id);
    }
    check('Confirmed evidence preserves all unknown/missing observations and separates original AI proposal from final human result');
    await page.locator('.ew-vd-footer [data-vd-tab="log"]').click();
    assert.match(await page.locator('.ew-vd-log').innerText(),/AI가 사람 대상 CR-2203에 승인[\s\S]*사람 확인 필요/);
    assert.match(await page.locator('.ew-vd-log').innerText(),/사람 대상 3건의 판정을 확정함/);
    await page.locator('[data-vd-tab="rules"]').click();
    assert.match(await page.locator('.ew-vd-rules').innerText(),/선택하거나 확정해도 원래 근거가 검증된 것으로 바뀌지는/);
    check('Log and rules explain AI proposal, human confirmation, and unchanged evidence');
    for(const [key,name] of [['initial','④-1 항목별 판정'],['menu','④-1a 사람 판정 고르기'],['evidence','④-1b 판정 근거'],['ready','④-2 사람 판정 확정 준비'],['confirmed','④-3 사람 판정 확정됨'],['log','④-기록 (초안)'],['rules','④-기준 (초안)']]) {
      await select(key);assert.equal(await page.locator('#mock-screen').innerText(),name);
      assert.equal(await page.locator(`button[data-mock-state="${key}"]`).getAttribute('aria-current'),'true');
      if(key==='confirmed') {await openEvidence('CR-2207');await capture('1920-human-confirmed',true);}
    }
    check('Review presets use a shared evidence screen and preserve existing decision states');
    await page.locator('[data-mock-info]').click();await page.locator('[data-mock-reset]').click();
    assert.equal(await label('CR-2207'),'직접 판정 필요');assert.equal(await label('CR-2210'),'AI 제안 · 확인 필요');
    assert.equal(await page.locator('.ew-vd-evidence').count(),0);assert(await page.locator('.ew-vd-footer button').isDisabled());
    await openEvidence('CR-2207');assert.equal(await row('CR-2207').locator('[data-human-selection],[data-human-confirmation]').count(),0);
    check('Reset restores pending and AI proposal labels and clears only mock decision history');
    for(const width of [1920,1200,480]) {
      await load(width,width===1920?1080:900);
      const value=await layout(),panelWidth=Math.min(480,width-56);
      assert.equal(value.sidebar,width===1920?256:56);assert.equal(value.panel.width,panelWidth);assert.equal(value.panel.x,width-panelWidth);assert.equal(value.overflow,0);
      assert.equal(value.overlay,String(width===480));
      const footer=await page.locator('.ew-vd-footer').boundingBox();
      for(const id of ['CR-2207','CR-2204','CR-2201']) {
        const button=await evidenceButton(id).boundingBox();assert(button.y>=0&&button.y+button.height<=footer.y);
        const origin=await row(id).locator('.ew-vd-origin>span').boundingBox();assert(origin.x+origin.width<=button.x);
      }
      assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);
      if(width===480) await capture('480-full');
      check('Common labels and evidence buttons fit without overlap at '+width,value);
    }
    for(const id of ['CR-2207','CR-2210','CR-2204']) {
      await openEvidence(id);
      assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);
      assert.equal(await evidenceButton(id).innerText(),'판정 근거');
      if(id==='CR-2207') {await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);await capture('480-human-evidence');}
      await closeEvidence(id);
    }
    check('Narrow human, AI and service evidence expands without horizontal overflow');
    await page.locator('#ees-work-panel').focus();await page.keyboard.press('Escape');
    assert(await page.locator('.ees-panel-region').isHidden());assert.equal(await page.locator('#ees-work-panel-toggle:focus').count(),1);
    await page.keyboard.press('Enter');assert(await page.locator('.ees-panel-region').isVisible());
    check('Narrow overlay keyboard close and reopen remains functional');
    await load(1920,1080,'#auto-evidence');
    assert.equal(await page.locator('#mock-screen').innerText(),'④-1b 판정 근거');
    assert.equal(await row('CR-2204').locator('.ew-vd-evidence').count(),1);
    check('Existing evidence deep link opens the common evidence view');
    assert.equal(report.requests.filter(u=>/^https?:/i.test(u)).length,0);assert.deepEqual(report.consoleErrors,[]);assert.deepEqual(report.pageErrors,[]);
    check('Offline load and interactions have no external requests or console/page errors');
    report.result='pass';
  } catch(error) {
    report.result='fail';report.error=String(error.stack||error);process.exitCode=1;await capture('failure');
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
