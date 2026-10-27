// Scoped copy check. Run with installed Playwright and EES_MOCK_CHROMIUM_PATH.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {createHash}=require('crypto'),{pathToFileURL}=require('url'),{chromium}=require('playwright');
const repo=path.resolve(__dirname,'../../..'),out=__dirname;
const source=path.join(repo,'docs/mockups/ees-work/design-mock-src/04-cr-verdict.html'),html=path.join(repo,'docs/mockups/ees-work/design-mock-04-cr-verdict.html');
const hash=f=>createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const report={checkedAt:new Date().toISOString(),source:path.relative(repo,source),sourceSha256:hash(source),artifact:path.relative(repo,html),artifactSha256:hash(html),artifactBytes:fs.statSync(html).size,checks:[],screenshots:[],externalRequests:[],errors:[]};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.EES_MOCK_CHROMIUM_PATH,headless:true,args:['--no-sandbox']});report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 page.on('request',r=>{if(/^https?:/.test(r.url()))report.externalRequests.push(r.url());});page.on('pageerror',e=>report.errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
 const check=name=>report.checks.push({name,result:'pass'}),row=id=>page.locator(`[data-vd-item="${id}"]`);
 const absent=async()=>assert.doesNotMatch(await page.locator('body').innerText(),/최종본/);
 const capture=async(name,panel=true)=>{const file=`mock-revision8-${name}.png`;await (panel?page.locator('.ees-panel-region'):page).screenshot({path:path.join(out,file)});report.screenshots.push(file);};
 const load=async(width,height)=>{await page.setViewportSize({width,height});await page.goto(pathToFileURL(html).href);await page.evaluate(()=>document.fonts.ready);};
 try{
  assert.doesNotMatch(fs.readFileSync(source,'utf8'),/최종본/);assert.doesNotMatch(fs.readFileSync(html,'utf8'),/최종본/);check('Removed final-version instructions are absent from source and generated artifact');
  await load(1920,1080);await absent();assert.match(await page.title(),/8판/);await capture('1920-panel');
  assert.equal(await row('CR-2207').locator('.ew-vd-file').innerText(),'test_v2_final.xlsx');assert.equal(await row('CR-2207').locator('[data-decision-status]').innerText(),'판정 선택 전');
  await page.locator('[data-vd-group]').click();assert.equal(await page.locator('[data-vd-item]').count(),12);assert.equal(await page.locator('[data-vd-pick]').count(),3);assert.equal(await page.locator('[data-handler="service"] [data-vd-pick]').count(),0);assert.match(await page.locator('[data-person]').innerText(),/선택 0\/3/);
  const serviceBefore=await page.locator('[data-handler="service"]').evaluateAll(els=>els.map(e=>e.outerHTML));check('Attachment example and three human selectors remain; nine service rows stay read-only');
  await row('CR-2207').locator('[data-vd-evidence]').click();await absent();assert.equal(await row('CR-2207').locator('[data-observation]').innerText(),'첨부 test_v2_final.xlsx는 있습니다.');assert.deepEqual(await row('CR-2207').locator('.ew-vd-evidence-observations dt').allTextContents(),['현재 근거']);
  await page.locator('.ew-scroll').evaluate(e=>e.scrollTop=0);await capture('1920-batch-evidence');await row('CR-2207').locator('[data-vd-evidence]').click();
  await row('CR-2210').locator('[data-vd-evidence]').click();assert.match(await row('CR-2210').locator('.ew-vd-evidence').innerText(),/추가 확인[\s\S]*배포 계획서의 상태는 이 근거에 기록되지/);await row('CR-2210').locator('[data-vd-evidence]').click();check('Batch evidence keeps only the attachment fact; unrelated missing-document guidance is unchanged');
  await row('CR-2207').locator('[data-vd-pick]').focus();await page.keyboard.press('ArrowDown');await absent();assert.deepEqual(await page.locator('.ew-vd-option b').allTextContents(),['승인','조건부 승인','미승인']);assert.equal(await page.locator('[data-vd-choose="cond"] small').innerText(),'추가 조건을 전제로 승인');
  await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');assert.equal(await row('CR-2207').locator('[data-decision-status]').innerText(),'선택: 조건부 승인');assert.equal(await page.locator('[data-vd-confirm]').count(),0);await absent();
  assert.deepEqual(await page.locator('[data-handler="service"]').evaluateAll(els=>els.map(e=>e.outerHTML)),serviceBefore);check('Existing three verdict options and keyboard selection remain; no final-version rule or confirmation action appears');
  for(const tab of ['log','rules']){await page.locator(`[data-vd-tab="${tab}"]`).click();await absent();}
  await page.locator('[data-mock-info]').click();await absent();await page.locator('[data-mock-close]').click();check('Removed copy does not reappear in records, rules, chat or mock help');
  for(const [width,height] of [[1920,1080],[480,900]]){await load(width,height);await absent();assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth),0);await row('CR-2207').locator('[data-vd-evidence]').click();assert.equal(await page.locator('#ees-work-panel').evaluate(e=>e.scrollWidth-e.clientWidth),0);await row('CR-2207').locator('[data-vd-evidence]').click();if(width===480)await capture('480-full',false);}
  check('Default and evidence views fit 1920px and 480px without horizontal overflow');
  assert.deepEqual(report.externalRequests,[]);assert.deepEqual(report.errors,[]);check('Offline smoke has no external requests or browser errors');report.result='pass';
 }catch(e){report.result='fail';report.error=String(e.stack||e);process.exitCode=1;await capture('failure',false);}
 finally{fs.writeFileSync(path.join(out,'ui-browser-report.json'),JSON.stringify(report,null,2)+'\n');await browser.close();console.log(JSON.stringify(report,null,2));}
})();
