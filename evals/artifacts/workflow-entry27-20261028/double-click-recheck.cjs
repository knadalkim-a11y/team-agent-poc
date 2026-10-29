const fs=require('fs'),path=require('path'),crypto=require('crypto');
const{chromium}=require((process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||'/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules')+'/playwright');
(async()=>{
 const root=path.resolve(__dirname,'../../..'),file=path.join(root,'docs/mockups/ees-work/design-mock-07-workflow-entry.html'),source=path.join(root,'docs/mockups/ees-work/design-mock-src/07-workflow-entry.html');
 const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'),r={scope:'Focused physical click/keyboard regression for mock navigation only; initial failure retained separately.',html_sha256:sha(file),source_sha256:sha(source),checks:[]};
 const b=await chromium.launch({executablePath:'/tmp/mock-browser-runtime/bin/chromium',headless:true,args:['--no-sandbox']});const p=await b.newPage({viewport:{width:1920,height:1080}});
 const read=()=>p.evaluate(()=>({rows:document.querySelectorAll('[data-vd-item]').length,running:[...document.querySelectorAll('[data-vd-item]')].filter(e=>e.innerText.includes('실행 중')).length,automatic:document.querySelectorAll('[data-vd-run]').length,human:document.querySelectorAll('[data-vd-pick]').length,stageButton:document.querySelector('[data-stage-run]')?.innerText,head:document.querySelector('.ew-vd-head')?.innerText,focusedBack:document.activeElement.matches('[data-entry-back]')}));
 const check=(name,passed,value)=>r.checks.push({name,status:passed?'passed':'failed',observed:value});
 try{
  await p.goto('file://'+file);await p.evaluate(()=>document.fonts.ready);await p.locator('[data-work-start]').dblclick({delay:50});let v=await read();check('50ms double click only starts workflow',v.rows===12&&v.running===0&&v.automatic===9&&v.human===3&&v.head.includes('0/3')&&v.head.includes('0/9'),v);await p.screenshot({path:path.join(__dirname,'double-click-transition-fixed.png')});
  await p.locator('[data-stage-run]').click();v=await read();check('Later intentional single stage click still executes',v.running===9&&v.stageButton==='실행 중',v);
  await p.goto('file://'+file);await p.locator('[data-work-start]').press('Enter');await p.locator('[data-stage-run]').press('Enter');v=await read();check('Intentional keyboard stage execution still works',v.running===9&&v.stageButton==='실행 중',v);
 }catch(e){r.failure=e.stack;}finally{await b.close();r.status=!r.failure&&r.checks.length===3&&r.checks.every(x=>x.status==='passed')?'passed':'failed';fs.writeFileSync(path.join(__dirname,'double-click-transition-fixed.json'),JSON.stringify(r,null,2)+'\n');console.log(JSON.stringify(r));process.exitCode=r.status==='passed'?0:1;}
})().catch(e=>{console.error(e);process.exitCode=1});
