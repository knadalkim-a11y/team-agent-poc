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
 assert.match(html,/결과 미확정/);assert.match(html,/완료가 아닙니다/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.doesNotMatch(html,/data-runtime-action=/);assert.match(html,/정규화 결과/);assert.match(html,/자동 재실행하지 않습니다/);assert.doesNotMatch(html,/모의 점검 수행/);
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

function runtimeFixture(){
 const node=(id,type,parent,children=[])=>({id,type,parent,children,name:id+' 업무',rule:id+'의 등록 완료 조건',mode:'tool',tools:[],skills:[],deps:[],enabled:true});
 const definition={nodes:{p:node('p','p',null,['t','t2']),t:node('t','t','p',['j']),t2:node('t2','t','p',['ai']),j:{...node('j','j','t'),execution:{kind:'fixed'}},ai:{...node('ai','j','t2'),execution:{kind:'ai'}}},tools:{},skills:{},sites:{},roots:{setup:['p']}};
 definition.nodes.p.execution_inputs={properties:{query:{type:'string',title:'조회 대상'}},required:['query']};
 const run={id:'run-j',case_id:'case',node_id:'j',revision:3,status:'waiting_input',reason:'input_required',inputs:{query:'현재 값'},input_schema:definition.nodes.p.execution_inputs,jobs:{j:{kind:'fixed',status:'waiting_input',reason:'input_required'}},calls:[]};
 const c={id:'case',status:'in_progress',site:{name:'합성 공장'},system:'EMS',definition,jobs:{j:{inputs:{},history:[]},ai:{inputs:{},history:[]}},node_states:{p:{status:'in_progress'},t:{status:'blocked'},t2:{status:'pending'},j:{status:'blocked',block_reason:'input_required',attention:true},ai:{status:'pending'}}};
 return {definition,run,c};
}
test('every run state offers only supported mutations in one C action region',()=>{
 const mutations={queued:['pause','cancel'],running:['pause','cancel'],waiting_input:['inputs','resume','cancel'],waiting_authorization:['inputs','resume','cancel'],waiting_dependency:['inputs','resume','cancel'],paused:['inputs','resume','cancel'],unknown:[],succeeded:[],failed:[],cancelled:[]};
 for(const [status,expected] of Object.entries(mutations)){
  const context=subject(),{definition,run,c}=runtimeFixture();run.status=status;run.jobs.j.status=status;run.reason=status==='unknown'?'timeout':'';context.execution={run};context.options={nodeId:'j',definition,case:c,planButton:'<button data-action="run">계획 확인</button>'};
  const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context),actual=[...html.matchAll(/data-runtime-action="([^"]+)"/g)].map(match=>match[1]);
  assert.deepEqual(actual,expected,status);assert.ok((html.match(/ew-work-action-region/g)||[]).length<=1,status);
  if(status==='succeeded')assert.match(html,/data-action="panel_parent" data-node-id="t"/);
  if(status==='unknown')assert.doesNotMatch(html,/data-action="run"|data-action="panel_parent"/);
  context.options.readOnly=true;assert.doesNotMatch(vm.runInContext('workExecutionRuntimeHTML(execution,options)',context),/data-runtime-action=/,status+' read only');
 }
});
test('Native preview preserves typed input contract and no-schema work has no fake save',()=>{
 const context=subject(),{definition,c}=runtimeFixture();context.definition=definition;context.c=c;
 const preview=vm.runInContext('workPanelNodeHTML(null,definition.nodes.j,{definition})',context);
 assert.match(preview,/data-status="execution_plan_required"/);assert.match(preview,/data-runtime-record="unrecorded"/);assert.match(preview,/data-work-section="runtime-inputs"/);assert.match(preview,/data-action="run"/);assert.doesNotMatch(preview,/ees-work-inputs|입력 저장|실행 연결 필요/);
 delete definition.nodes.p.execution_inputs;
 const empty=vm.runInContext('workPanelNodeHTML(null,definition.nodes.j,{definition})',context);assert.doesNotMatch(empty,/data-work-section="runtime-inputs"|<form|입력 저장/);
 context.execution={run:{id:'human',revision:1,status:'waiting_input',jobs:{j:{kind:'human',status:'waiting_input',reason:'human_confirmation_required'}},calls:[]}};context.options={nodeId:'j',definition};
 const human=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(human,/data-runtime-action="confirm"/);assert.doesNotMatch(human,/data-runtime-action="inputs"|data-runtime-action="resume"/);
});
test('Native current input and call snapshot stay distinct and escaped in the detail',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();run.calls=[{job_id:'j',id:'c1',status:'succeeded',arguments:{query:'호출 당시 <값>'},result:{completeness:'partial',data:{title:'실제 반환'}}}];context.execution={run};context.options={nodeId:'j',definition,case:c};
 const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(html,/현재 실행 입력/);assert.match(html,/현재 값/);assert.match(html,/호출 당시 snapshot/);assert.match(html,/호출 당시 &lt;값&gt;/);assert.match(html,/일부 범위 결과/);assert.match(html,/data-runtime-run="run-j"/);assert.doesNotMatch(html,/data-work-criterion-status="passed"/);
});
test('call completeness and job validators remain separate for complete empty partial truncated and unknown results',()=>{
 for(const completeness of ['complete','empty','partial','truncated','unknown']){
  const context=subject(),{definition,run,c}=runtimeFixture(),verified=['complete','empty'].includes(completeness);run.status=verified?'succeeded':'unknown';run.jobs.j={kind:'fixed',status:run.status,validation:{status:run.status,scope_complete:verified},reason:verified?'verified_complete':'observed_limited'};run.calls=[{job_id:'j',status:'succeeded',result:{completeness,data:{value:'실제 반환'}}}];context.execution={run};context.options={nodeId:'j',definition,case:c};
  const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.equal(html.includes('data-work-criterion-status="passed"'),verified,completeness);assert.match(html,new RegExp(completeness));if(!verified)assert.doesNotMatch(html,/data-runtime-action=/,completeness);
 }
 const context=subject(),{definition,run,c}=runtimeFixture();run.status='succeeded';run.jobs.j={kind:'fixed',status:'succeeded',validation:{status:'succeeded',scope_complete:false},reason:'observed_limited'};context.execution={run};context.options={nodeId:'j',definition,case:c};
 const bounded=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(bounded,/data-work-criterion-status="passed"/);assert.match(bounded,/전체 범위 완료와 구분/);
});
test('selected job uses its matching run and never displays an unrelated newer result',()=>{
 const context=subject(),{definition,run}=runtimeFixture(),other={id:'new-ai',status:'succeeded',jobs:{ai:{kind:'ai',status:'succeeded',result:'다른 결과'}}};context.definition=definition;context.execution={run:other,runs:[other,run]};
 assert.equal(vm.runInContext('workExecutionForNode(execution,"j",definition).run.id',context),'run-j');assert.equal(vm.runInContext('workExecutionForNode(execution,"t2",definition).run.id',context),'new-ai');
 context.execution={run:other,runs:[other]};assert.equal(vm.runInContext('workExecutionForNode(execution,"j",definition)',context),null);
});
test('a succeeded child run leaves parent completion pending and its scope plan available',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();run.status='succeeded';run.node_id='t';run.jobs.j={kind:'fixed',status:'succeeded',validation:{status:'succeeded',scope_complete:true}};run.final_validation={status:'succeeded',scope_complete:true};c.node_states.j.status='passed';c.node_states.t.status='passed';context.c=c;context.execution={run};
 const html=vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.p,{execution})',context);assert.match(html,/data-action="run"/);assert.match(html,/ew-work-current-title" role="status">진행 중/);assert.match(html,/아직 판정하지 않음/);assert.doesNotMatch(html,/ew-work-current-title" role="status">완료/);
});
test('mixed P/T lists keep kinds separate and explain why there is no combined runtime plan',()=>{
 const context=subject(),{definition}=runtimeFixture();definition.nodes.legacy={id:'legacy',type:'j',parent:'t',children:[],name:'모의',mode:'tool',tools:['mock'],skills:[],deps:[]};definition.nodes.t.children.push('legacy');definition.tools.mock={adapter:'mock',input:'site'};context.definition=definition;
 const html=vm.runInContext('workPanelNodeHTML(null,definition.nodes.t,{definition})',context);assert.match(html,/data-runtime-mixed-scope/);assert.match(html,/전체를 한 실행으로 진행할 수 없습니다/);assert.match(html,/data-work-count="fixed">1</);assert.match(html,/data-work-count="simulation">1</);assert.doesNotMatch(html,/data-action="run"/);assert.match(html,/data-action="select" data-node-id="legacy"/);
 definition.nodes.j.enabled=false;const excluded=vm.runInContext('workPanelNodeHTML(null,definition.nodes.t,{definition})',context);assert.match(excluded,/data-runtime-mixed-scope/);assert.doesNotMatch(excluded,/data-action="run"/);
});
test('active Native execution preserves but blocks legacy input writes and run until terminal',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();definition.nodes.legacy={id:'legacy',type:'j',parent:'t',children:[],name:'모의',mode:'tool',tools:['mock'],skills:[],deps:[]};definition.tools.mock={adapter:'mock',input:'site'};definition.nodes.t.children.push('legacy');c.jobs.legacy={inputs:{site:'저장된 대상'},history:[]};c.node_states.legacy={status:'pending',ready_for_run:true};context.c=c;context.execution={run};
 for(const status of ['running','paused','waiting_input','unknown']){run.status=status;const html=vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.legacy,{execution,draft:{inputs:{site:"보존할 작성 값"},inputsChanged:true}})',context);assert.match(html,/보존할 작성 값/);assert.match(html,/id="ees-work-inputs-save"[^>]*disabled/);assert.match(html,/data-action="run"[^>]*disabled/);assert.match(html,/연결 실행이 종료되기 전/);}
 run.status='cancelled';const restored=vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.legacy,{execution})',context);assert.doesNotMatch(restored,/data-action="run"[^>]*disabled/);
});
test('P/T rows preserve Native unknown and waiting reasons instead of legacy generic labels',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();run.status='unknown';run.jobs.j={kind:'fixed',status:'unknown',reason:'timeout'};context.c=c;context.execution={run};
 const html=vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.t,{execution,listView:{expanded:["j"]}})',context);assert.match(html,/data-status="unknown">결과 미확정/);assert.match(html,/요청의 결과를 확정하지 못했습니다/);assert.doesNotMatch(html,/<p>timeout<\/p>/);
});
test('redacted runtime evidence stays hidden even if an older response still contains raw values',()=>{
 const context=subject(),{definition,run}=runtimeFixture();run.evidence_available=false;run.status='succeeded';run.jobs.j={kind:'fixed',status:'succeeded',result:{claims:[{value:'PRIVATE_MARKER'}]},validation:{status:'succeeded',output:'PRIVATE_MARKER'}};run.calls=[{job_id:'j',status:'succeeded',arguments:{secret:'PRIVATE_MARKER'},result:{data:'PRIVATE_MARKER'},evidence_available:false}];context.execution={run};context.options={nodeId:'j',definition};
 const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(html,/근거 접근 제한/);assert.doesNotMatch(html,/PRIVATE_MARKER|data-runtime-action=/);
});
test('control targets the selected older run and refreshes stale or unreadable evidence before mutation',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8'),start=launcher.indexOf('  async function executionControl('),end=launcher.indexOf('  async function runJob(',start),fn=launcher.slice(start,end);
 for(const scenario of ['older','revision','execution-error','record-error']){
  const old={id:'old',revision:3,status:'paused'},latest={id:'latest',revision:8,status:'running'},sent=[],s={busy:false,recordLookupError:scenario==='record-error'?{message:'failed'}:null,executionError:scenario==='execution-error'?'failed':'',execution:{run:latest,runs:[latest,old]},generation:1,navigationRequest:1,token:()=> 'auth',location:{pathname:'/c/x',search:''},available:()=>true,chatId:()=> 'x',setBusy:()=>{},renderPanel:()=>{},executionRequestId:()=> 'receipt',refresh:async()=>{s.refreshes++},refreshExecution:async()=>{s.refreshes++},refreshes:0,api:async(path,body)=>{sent.push(body);return {ok:true,run:old}}};
  vm.createContext(s);vm.runInContext(fn,s);await s.executionControl({runId:'old',revision:scenario==='revision'?'2':'3',runtimeAction:'resume'});
  assert.equal(sent.length,scenario==='older'?1:0,scenario);assert.equal(s.refreshes,1,scenario);if(sent.length){assert.equal(sent[0].run_id,'old');assert.equal(sent[0].expected_revision,3);}
 }
});
test('retry rereads each failed case independently, including an initial historical lookup failure',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8'),start=launcher.indexOf('  function retryExecutionRead() {'),end=launcher.indexOf('  async function refreshExecution()',start),fn=launcher.slice(start,end);
 for(const [runView,recordLookupError,historyCase,historyLookupError,expected] of [['current',{message:'read failed'},null,null,'state'],['current',null,null,null,'execution'],['history',{message:'current read failed'},{id:'old-case'},null,'history:old-case'],['history',null,null,{caseId:'initially-failed-case'},'history:initially-failed-case']]){
  const called=[],context={runView,recordLookupError,historyCase,historyLookupError,refresh:()=>called.push('state'),refreshExecution:()=>called.push('execution'),showHistory:id=>called.push('history:'+id)};vm.createContext(context);vm.runInContext(fn,context);await context.retryExecutionRead();assert.deepEqual(called,[expected]);assert.equal(context.recordLookupError,recordLookupError,'An unrelated successful lookup must not clear current failure');
 }
});

test('AI observations retain source and field context, typed values and limitations',()=>{
 const c=subject();c.definition={nodes:{j:{id:'j',type:'j',name:'근거 정리'},source:{id:'source',type:'j',name:'원본 <자료>'}}};
 c.execution={run:{id:'r',node_id:'j',status:'succeeded',jobs:{j:{kind:'ai',status:'succeeded',validation:{status:'succeeded'},result:{claims:[{source:{job_id:'source'},path:['data','pagination','has_next'],value:false},{source:{job_id:'source'},path:['data','summary','total'],value:0},{source:{job_id:'source'},path:['data','unfamiliar'],value:'<script>'}],limitations:['저장된 한 페이지 범위'],notice:'관찰값'}}},calls:[]}};
 const html=vm.runInContext('workExecutionRuntimeHTML(execution,{nodeId:"j",definition,readOnly:true})',c);
 assert.equal((html.match(/data-runtime-observation/g)||[]).length,3);
 assert.match(html,/원본 &lt;자료&gt;/);assert.match(html,/페이지 \/ 다음 페이지/);assert.match(html,/>아니요<\/p>/);assert.match(html,/집계 \/ 전체/);assert.match(html,/>0<\/p>/);assert.match(html,/unfamiliar/);assert.match(html,/&lt;script&gt;/);assert.match(html,/결과의 한계/);assert.match(html,/저장된 한 페이지 범위/);assert.doesNotMatch(html,/<script>/);
 c.execution.run.evidence_available=false;
 const hidden=vm.runInContext('workExecutionRuntimeHTML(execution,{nodeId:"j",definition,readOnly:true})',c);
 assert.doesNotMatch(hidden,/data-runtime-observation|원본 &lt;자료&gt;|저장된 한 페이지 범위/);
});


test('historical target validators retain saved scope and read-only evidence boundaries',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();
 definition.nodes.t.rule='이전 정의의 단계 완료 조건';run.node_id='t';run.jobs.j={kind:'fixed',status:'succeeded',validation:{status:'succeeded'}};run.calls=[{job_id:'j',status:'succeeded',arguments:{query:'실행 당시 값'},result:{completeness:'partial',data:'저장된 일부 근거'}}];c.node_states.p.status='in_progress';
 context.execution={run};context.options={nodeId:run.node_id,definition,case:c,readOnly:true,history:true};
 for(const status of ['succeeded','failed','unknown']){
  run.status=status;run.final_validation=status==='unknown'?null:{status,scope_complete:status==='succeeded'};
  const html=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);
  assert.match(html,/이전 정의의 단계 완료 조건/);assert.match(html,/실행 대상 · t 업무/);assert.match(html,/일부 범위 결과/);assert.match(html,/실행 당시 값/);
  assert.match(html,new RegExp('data-work-criterion-status="'+(status==='succeeded'?'passed':status==='failed'?'failed':'pending')+'"'));
  assert.doesNotMatch(html,/data-mutation|data-action="panel_parent"|data-action="execution_refresh"/);
 }
 run.status='succeeded';run.final_validation={status:'succeeded',scope_complete:true};context.options.nodeId='p';
 const parent=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(parent,/아직 판정하지 않음/);assert.match(parent,/실행 대상 · t 업무/);assert.doesNotMatch(parent,/data-work-criterion-status="passed"|실행 대상 · p 업무|아래 제어/);
 context.options.nodeId='t';run.evidence_available=false;
 const restricted=vm.runInContext('workExecutionRuntimeHTML(execution,options)',context);assert.match(restricted,/근거 접근 제한/);assert.doesNotMatch(restricted,/실행 당시 값|저장된 일부 근거/);
 run.evidence_available=true;run.final_validation=null;
 assert.match(vm.runInContext('workExecutionRuntimeHTML(execution,options)',context),/아직 판정하지 않음/);
});

test('legacy draft actions match same-case active runs while text remains editable and terminal prerequisites remain enforced',()=>{
 const context=subject(),{definition,run,c}=runtimeFixture();definition.nodes.draft={id:'draft',type:'j',parent:'t2',children:[],name:'검토 초안',mode:'draft',tools:[],skills:[],deps:[]};definition.nodes.t2.children.push('draft');c.jobs.draft={document:'저장된 초안',inputs:{},history:[]};c.node_states.draft={status:'review',missing:[]};context.c=c;context.execution={run};
 const render=()=>vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.draft,{execution,draft:{document:"보존할 미반영 초안",documentChanged:true}})',context);
 for(const status of ['queued','running','paused','waiting_input','waiting_authorization','waiting_dependency','unknown']){
  run.status=status;const html=render();assert.match(html,/<textarea[^>]*>보존할 미반영 초안<\/textarea>/,status);assert.match(html,/<form id="ees-work-document"[^>]*data-work-save-blocked="true"/,status);assert.match(html,/<button[^>]*form="ees-work-document"[^>]* disabled/,status);assert.match(html,/data-work-edit-locked="true"/,status);assert.match(html,/작성 중인 내용은 이 화면에 보존/,status);
 }
 for(const status of ['succeeded','failed','cancelled']){run.status=status;assert.doesNotMatch(render(),/<button[^>]*form="ees-work-document"[^>]* disabled/,status);}
 run.status='running';run.case_id='another-case';assert.doesNotMatch(render(),/<button[^>]*form="ees-work-document"[^>]* disabled/);
 run.case_id=c.id;context.execution={run:{...run,id:'new-terminal',status:'failed'},runs:[run]};assert.match(render(),/<button[^>]*form="ees-work-document"[^>]* disabled/);
 context.execution={run:{...run,status:'cancelled'}};
 for(const saved of [{status:'blocked',missing:['j']},{status:'blocked',missing:[],block_reason:'skill_unavailable'}]){c.node_states.draft=saved;assert.match(render(),/<button[^>]*form="ees-work-document"[^>]* disabled/);}
 c.node_states.draft={status:'review',missing:[]};
 assert.doesNotMatch(render(),/<button[^>]*form="ees-work-document"[^>]* disabled/);
 const conflict=vm.runInContext('workPanelNodeHTML(c,c.definition.nodes.draft,{execution,draft:{document:"보존할 미반영 초안",documentChanged:true,conflict:true}})',context);assert.match(conflict,/<button[^>]*form="ees-work-document"[^>]* disabled/);
});

test('legacy save submission rejects active Native and unmet document prerequisites without writes or draft loss',async()=>{
 const launcher=fs.readFileSync(path.join(root,'branding/ees/ui/ees-work-launcher.js'),'utf8'),start=launcher.indexOf('  function canWriteEdits('),end=launcher.indexOf('  async function executionForm(',start),fn=launcher.slice(start,end);
 const context=subject(),draft={nodeId:'draft',document:'작성 중인 초안\n내용 보존',documentChanged:true},saved={id:'case',node_states:{draft:{status:'review',missing:[]}}},sent=[];
 Object.assign(context,{view:{readJobEdits:()=>draft},selectedCase:()=>saved,selectedId:()=> 'draft',errorMessage:'',renderPanel:()=>{},action:async(...args)=>sent.push(args),execution:{run:{id:'r',case_id:'case',status:'running'}}});vm.runInContext(fn,context);
 const before=JSON.stringify(draft);
 for(const status of ['queued','running','paused','waiting_input','waiting_authorization','waiting_dependency','unknown']){
  context.execution.run.status=status;await context.saveDocument(draft.document,'draft');await context.saveInputs({site:'작성 중인 값'},'draft');assert.equal(sent.length,0,status);assert.equal(JSON.stringify(draft),before,status);assert.match(context.errorMessage,/연결 실행이 종료되기 전/);
 }
 context.execution.run.status='cancelled';
 for(const state of [{applicable:false},{status:'skipped'},{missing:['j']},{block_reason:'skill_unavailable'}]){saved.node_states.draft=state;await context.saveDocument(draft.document,'draft');assert.equal(sent.length,0);assert.equal(JSON.stringify(draft),before);}
 saved.node_states.draft={status:'review',missing:[]};
 for(const status of ['succeeded','failed','cancelled']){context.execution.run.status=status;await context.saveDocument(draft.document,'draft');}
 assert.deepEqual(sent.map(args=>JSON.parse(JSON.stringify(args))),Array.from({length:3},()=>['run',{document:draft.document},'draft']));assert.equal(JSON.stringify(draft),before);
 context.execution.run={id:'other',case_id:'another-case',status:'running'};await context.saveDocument(draft.document,'draft');assert.equal(sent.length,4);
});
