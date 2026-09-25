const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-view.js'),'utf8');
function subject(){const context={window:{},document:{querySelector:()=>null},Set,Map,JSON,FormData};vm.createContext(context);vm.runInContext(source,context);return context;}
test('durable run renders UNKNOWN and actual evidence without inventing a completion',()=>{
 const c=subject();c.execution={run:{id:'run',status:'unknown',revision:4,jobs:{j:{status:'unknown',kind:'fixed',checks:[{status:'unknown'}]}},calls:[{job_id:'j',id:'call',status:'unknown',reference:{function:'get_page',revision:2},arguments:{page_id:'42'},result:{complete:false,data:{title:'<script>bad</script>'}}}]}};c.options={nodeId:'j',definition:{nodes:{j:{name:'문서 확인',type:'j'}}}};
 const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',c);
 assert.match(html,/결과 미확정/);assert.match(html,/완료가 아닙니다/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/data-runtime-action="cancel"/);assert.match(html,/정규화 결과/);assert.doesNotMatch(html,/모의 점검 수행/);
});
test('read failure never renders a false empty history or exposes stale evidence',()=>{
 const c=subject();c.execution={run:{id:'stale-private',status:'succeeded'}};c.options={error:'기록 접근 권한을 확인할 수 없습니다.'};
 const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',c);assert.match(html,/lookup-failed/);assert.doesNotMatch(html,/stale-private|기록 없음|완료<\/strong>/);
});
test('scope chooses runtime only for new execution contracts and detects P/T descendants',()=>{
 const c=subject();c.definition={nodes:{p:{children:['t']},t:{children:['j']},j:{execution:{kind:'fixed'}},legacy:{mode:'tool',tools:['mock']}}};
 assert.equal(vm.runInContext('workHasExecution(definition,"p")',c),true);assert.equal(vm.runInContext('workHasExecution(definition,"t")',c),true);assert.equal(vm.runInContext('workHasExecution(definition,"legacy")',c),false);
});
test('public input form preserves boolean false, integer zero and typed enum values',()=>{
 const c=subject();c.schema={properties:{enabled:{type:'boolean'},page:{type:'integer'},choice:{enum:[0,false,'x']},label:{type:'string',title:'<unsafe>'}},required:['page']};c.values={enabled:false,page:0,choice:false};
 const html=vm.runInContext('workExecutionInputsHTML(schema,values)',c);assert.match(html,/value="false" selected/);assert.match(html,/value="0"/);assert.match(html,/name="page" data-execution-input required/);assert.match(html,/&lt;unsafe&gt;/);
});
test('status reads discard late account, navigation and route responses before rendering',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8');
 const start=launcher.indexOf('  async function refreshExecution() {'),end=launcher.indexOf('  async function startExecution(',start),fn=launcher.slice(start,end);
 for(const change of ['auth','generation','navigationRequest','route']){
  let resolve;const pending=new Promise(r=>resolve=r),s={executionTimer:null,executionSerial:0,execution:{run:{id:'old'}},executionError:'',available:()=>true,state:{},selectedCase:()=>({id:'case'}),workHasExecution:()=>true,definition:()=>({}),processId:()=> 'p',generation:1,navigationRequest:1,auth:'a',token:()=>s.auth,location:{pathname:'/c/a',search:''},chatId:()=> 'a',api:()=>pending,renderPanel:()=>{s.renders++},renders:0,clearTimeout,setTimeout,URLSearchParams};vm.createContext(s);vm.runInContext(fn,s);const waiting=s.refreshExecution();if(change==='auth')s.auth='b';else if(change==='route')s.location.pathname='/c/b';else s[change]++;resolve({ok:true,run:{id:'private-response',status:'succeeded'}});await waiting;assert.equal(s.renders,0);assert.equal(s.execution.run.id,'old');
 }
});
test('lost start response retries the identical accepted plan and receipt',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8');
 const from=launcher.indexOf('  async function startExecution('),to=launcher.indexOf('  async function executionControl(',from),fn=launcher.slice(from,to),sent=[];let plans=0,starts=0;
 const s={busy:false,generation:1,navigationRequest:1,token:()=> 'a',location:{pathname:'/c/a',search:''},available:()=>true,setBusy:()=>{},errorMessage:'',renderPanel:()=>{},selectedCase:()=>({id:'case'}),chatId:()=> 'chat',node:()=>({name:'작업'}),executionForm:async()=>({page_id:'42'}),executionStarts:new Map(),executionRequestId:body=>'stable-'+body.plan_id,execution:null,executionError:'',refresh:async()=>{},workUI:{esc:value=>String(value)},api:async(path,body)=>{if(path==='execution/plan'){plans++;return {plan:{id:'plan'+plans,hash:'hash'+plans,jobs:['j'],input_schema:{},inputs:{}}};}sent.push(JSON.parse(JSON.stringify(body)));starts++;if(starts===1)throw new Error('lost response');return {ok:true,run:{id:'run',case_id:'case'}};}};
 vm.createContext(s);vm.runInContext(fn,s);await s.startExecution('j');assert.match(s.errorMessage,/lost response/);assert.equal(s.executionStarts.size,1);await s.startExecution('j');assert.deepEqual(sent[0],sent[1]);assert.equal(starts,2);assert.equal(s.executionStarts.size,0);
});

test('definitive start rejection and late successful response retire the cached intent',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8'),from=launcher.indexOf('  async function startExecution('),to=launcher.indexOf('  async function executionControl(',from),fn=launcher.slice(from,to);
 for(const scenario of ['expired','late-success']){
  let plans=0,starts=0;const sent=[],s={busy:false,generation:1,navigationRequest:1,token:()=> 'a',location:{pathname:'/c/a',search:''},available:()=>true,setBusy:()=>{},errorMessage:'',renderPanel:()=>{},selectedCase:()=>({id:'case'}),chatId:()=> 'chat',node:()=>({name:'작업'}),executionForm:async()=>({page_id:'42'}),executionStarts:new Map(),executionRequestId:body=>'stable-'+body.plan_id,execution:null,executionError:'',refresh:async()=>{},workUI:{esc:value=>String(value)},api:async(path,body)=>{
   if(path==='execution/plan'){plans++;return {plan:{id:'plan'+plans,hash:'hash'+plans,jobs:['j'],input_schema:{},inputs:{}}};}
   starts++;sent.push({...body});if(starts===1&&scenario==='expired')throw Object.assign(new Error('plan expired'),{result:{ok:false,error:{code:'plan_expired'}},status:400});if(starts===1&&scenario==='late-success')s.navigationRequest++;return {ok:true,run:{id:'run',case_id:'case'}};
  }};vm.createContext(s);vm.runInContext(fn,s);await s.startExecution('j');assert.equal(s.executionStarts.size,0);await s.startExecution('j');assert.notEqual(sent[0].plan_id,sent[1].plan_id);assert.equal(sent[0].chat_id,'chat');assert.equal(s.executionStarts.size,0);
 }
});
test('runtime P and T summaries count fixed and AI work separately from legacy simulation',()=>{
 const c=subject(),n=(id,type,parent,children=[])=>({id,name:id,type,parent,children,mode:'tool',tools:[],skills:[],deps:[],enabled:true});
 c.definition={nodes:{p:n('p','p',null,['t']),t:n('t','t','p',['fixed','ai','legacy']),fixed:{...n('fixed','j','t'),execution:{kind:'fixed'}},ai:{...n('ai','j','t'),execution:{kind:'ai'}},legacy:{...n('legacy','j','t'),tools:['mock']}},tools:{mock:{adapter:'mock',input:'site'}},skills:{},sites:{},roots:{setup:['p']}};
 for(const id of ['p','t']){c.id=id;const html=vm.runInContext('workPanelNodeHTML(null,definition.nodes[id],{definition})',c);assert.match(html,/data-work-count="fixed">1</);assert.match(html,/data-work-count="ai">1</);assert.match(html,/data-work-count="simulation">1</);}
});
test('runtime polling adopts the matching case projection and ignores a changed selection during its read',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8'),start=launcher.indexOf('  async function refreshExecution() {'),end=launcher.indexOf('  async function startExecution(',start),fn=launcher.slice(start,end);
 for(const change of [false,true]){
  const currentCase={id:'case',revision:1,jobs:{j:{status:'pending'}}},s={busy:false,executionTimer:null,executionSerial:0,execution:{run:{id:'r',revision:1}},executionError:'',available:()=>true,state:{case:currentCase},selectedCase:()=>s.state.case,workHasExecution:()=>true,definition:()=>({}),processId:()=> 'p',generation:1,navigationRequest:1,token:()=> 'a',location:{pathname:'/c/a',search:''},chatId:()=> 'a',renderPanel:()=>{},accept:value=>{s.state=value;s.accepted++},accepted:0,clearTimeout,setTimeout,URLSearchParams,api:async(path)=>{if(path.startsWith('execution/'))return {ok:true,run:{id:'r',revision:2,status:'succeeded'}};if(change)s.navigationRequest++;return {ok:true,case:{id:'case',revision:2,jobs:{j:{status:'passed'}}}};}};
  vm.createContext(s);vm.runInContext(fn,s);await s.refreshExecution();assert.equal(s.accepted,change?0:1);assert.equal(s.state.case.jobs.j.status,change?'pending':'passed');
 }
});
