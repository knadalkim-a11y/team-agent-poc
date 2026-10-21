const test=require('node:test'),assert=require('node:assert/strict');
const {renderer,run,controller,deferred,launcherSource}=require('./ees_workspace_ui_fixture.cjs');
function html(source,values={}){const context=renderer(values);return run(context,source);}
test('controller fixture exercises the same command and read boundaries with LF and Windows CRLF',async()=>{for(const newline of ['\n','\r\n']){const source=launcherSource.replace(/\r?\n/g,newline),h=controller(source);h.api.setState({run:{revision:4}});await h.api.command({action:'save_inputs',run_id:'r',inputs:{value:false}});assert.equal(h.calls[0].body.expected_revision,4);assert.equal(h.calls[0].body.inputs.value,false);await h.api.refresh();assert.ok(h.calls.some(call=>call.url.startsWith('/api/ees-work/workspace?')));}});
test('controller fixture fails directly when its required injection marker is missing or duplicated',()=>{const marker='  schedule();\n})();',source=launcherSource.replace(/\r\n?/g,'\n');assert.throws(()=>controller(source.replace(marker,'  schedule();\n})() ;')),/exactly one injection marker/);assert.throws(()=>controller(source.replace(marker,marker+'\n'+marker)),/exactly one injection marker/);assert.throws(()=>controller(source.replace('dialog,closeDialog}=workUI;','dialog,closeDialog}=missingUI;')),/exactly one injection marker/);});
test('unknown partial failed and excluded states never render completion',()=>{for(const status of ['unknown','partial','failed','excluded','missed']){const out=html('workStatusHTML(status)',{status});assert.doesNotMatch(out,/>완료</);assert.match(out,new RegExp('data-status="'+status+'"'));}});
test('all eight declared input kinds render typed named accessible controls',()=>{for(const type of ['text','number','datetime','single','multi','list','person','boolean']){const out=html('workInputHTML(field,undefined)',{field:{id:'value',name:'입력',type,required:true,options:['x']}});assert.match(out,/name="value"/);assert.match(out,/required/);assert.match(out,/for="ew-run-value"/);}});
test('boolean false number zero and typed enum values survive input rendering',()=>{assert.match(html('workInputHTML({id:"b",type:"boolean"},false)'),/value="false" selected/);assert.match(html('workInputHTML({id:"n",type:"number"},0)'),/value="0"/);assert.match(html('workInputHTML({id:"s",type:"single",options:[0,false]},false)'),/value="false" selected/);});
test('form reading distinguishes unset from false zero and empty multiselect',()=>{const fields=[['b','boolean','false'],['n','number','0'],['s','single','false'],['empty','text','']].map(([name,type,value])=>({name,value,dataset:{inputType:type}}));fields.push({name:'multi',selectedOptions:[],dataset:{inputType:'multi'}});const value=html('workReadInputs(form)',{form:{querySelectorAll:()=>fields}});assert.equal(value.b,false);assert.equal(value.n,0);assert.equal(value.s,false);assert.equal(value.empty,undefined);assert.equal(value.multi.length,0);});
test('all eight result blocks render from the same job definition contract',()=>{for(const block of ['values','schedule','checklist','list_confirm','item_verdict','ai_review','human_confirm','change_request'])assert.match(html('workResultHTML(job)',{job:{result_block:block}}),new RegExp('data-result-block="'+block+'"'));});
test('untrusted job output and names are escaped and unsafe links omitted',()=>{const out=html('workResultHTML(job,saved)',{job:{result_block:'item_verdict'},saved:{result:{items:[{id:'a',name:'<script>bad</script>',url:'javascript:alert(1)',ai_suggestion:'<img onerror=x>'}]}}});assert.match(out,/&lt;script&gt;/);assert.doesNotMatch(out,/<script|<img onerror|javascript:/);});
test('per-item AI proposal is visibly unconfirmed and requires human verdict',()=>{const out=html('workResultHTML(job,saved)',{job:{result_block:'item_verdict'},saved:{result:{items:[{id:'a',ai_suggestion:'적합'}]}}});assert.match(out,/사람 미확정/);assert.match(out,/data-item-verdict/);assert.match(out,/판정 선택/);});
test('read-only historical result blocks never permit input decisions',()=>{const out=html('workResultHTML(job,saved,{readOnly:true})',{job:{result_block:'list_confirm'},saved:{result:{items:[{id:'a'}]}}});assert.match(out,/data-item-confirm[^>]* disabled/);});
test('evidence presence does not claim attachment content adequacy',()=>{const out=html('workResultHTML(job,saved)',{job:{result_block:'item_verdict'},saved:{result:{items:[{id:'a',evidence:[{status:'completed',name:'설계서',content_reviewed:false}]}]}}});assert.match(out,/내용 적정성 미검토/);});
test('request timeline preserves EES report and independent effect confirmation',()=>{const out=html('workRequestHTML(request)',{request:{state:'unknown',events:[{state:'requested',at:'time'}]}});assert.match(out,/완료 보고/);assert.match(out,/효과 확인/);assert.match(out,/자동으로 다시 요청하지 않습니다/);assert.match(out,/data-actor="EES Work">EES Workflow<\/span>/);assert.match(out,/data-actor="EES"/);
 const request={execution_actor:'EES Work',state:'unknown',events:[{state:'reported_complete',actor:'EES Work',at:'time'}]},before=JSON.stringify(request),direct=html('workRequestHTML(request)',{request});
 assert.match(direct,/실행 주체 EES Workflow/);assert.match(direct,/EES Workflow 완료 보고/);assert.doesNotMatch(direct,/>EES Work<\/span>/);assert.equal(JSON.stringify(request),before);
});
test('history uses immutable attempt inputs and result rather than current edited values',()=>{const out=html('workHistoryHTML(run)',{run:{version:1,inputs:{secret:'current-input'},attempts:[{id:'one',job_id:'j',number:1,status:'failed',inputs:{a:'historical'},result:{text:'old-result'}}]}});assert.match(out,/historical/);assert.match(out,/old-result/);assert.doesNotMatch(out,/current-input/);});
test('missing history is explicitly unexecuted and never a success fixture',()=>{assert.match(html('workHistoryHTML({attempts:[]})'),/미수행을 성공으로 표시하지 않습니다/);});
test('My Work uses actual tasks and incident-overdue-today-week-future-undated ordering',()=>{const items=['undated','week','overdue','today','future','incident'].map(bucket=>({id:bucket,bucket,name:bucket}));const out=html('workMyWorkHTML(items)',{items});const keys=['incident','overdue','today','week','future','undated'];for(let i=1;i<keys.length;i++)assert.ok(out.indexOf('data-task-id="'+keys[i-1]+'"')<out.indexOf('data-task-id="'+keys[i]+'"'));assert.equal((out.match(/data-action="open_task"/g)||[]).length,6);});
test('empty My Work does not invent an actionable task or normal execution',()=>{const out=html('workMyWorkHTML([])');assert.match(out,/지금 처리할 내 업무가 없습니다/);assert.doesNotMatch(out,/data-task-id|정상 실행/);});
test('late workspace reads are discarded after account change',async()=>{const h=controller(),pending=deferred();h.setReply(()=>pending.promise);const waiting=h.api.refresh();h.setAuth('other-token');pending.resolve({ok:true,private:'actor-a'});await waiting;assert.equal(h.renders.length,0);assert.equal(h.api.snapshot().state,null);});
test('late workspace reads are discarded after selected job changes',async()=>{const h=controller(),pending=deferred();h.setReply(()=>pending.promise);const waiting=h.api.refresh();h.api.setSelection({job_id:'other'});pending.resolve({ok:true,private:'old-job'});await waiting;assert.equal(h.renders.length,0);});
test('lookup failure clears stale private evidence and keeps an explicit read error',async()=>{const h=controller();h.api.setState({run:{private:'old'}});h.setReply(()=>({ok:false,error:{message:'access denied'},httpError:true,status:403}));await h.api.refresh();assert.equal(h.api.snapshot().state,null);assert.match(h.api.snapshot().error,/access denied/);});
test('lost mutation response reuses the exact request receipt and payload',async()=>{const h=controller();let n=0;h.setReply(()=>{if(!n++)throw new Error('connection lost');return {ok:true};});const body={action:'save_inputs',run_id:'r',expected_revision:4,inputs:{a:1}};await assert.rejects(h.api.command(body));await h.api.command(body);assert.deepEqual(h.calls[0].body,h.calls[1].body);});
test('definitive rejection retires its receipt instead of replaying invalid intent',async()=>{const h=controller();let n=0;h.setReply(()=>n++?{ok:true}:{ok:false,error:{message:'expired'},httpError:true,status:409});const body={action:'save_inputs',run_id:'r',inputs:{a:1}};await assert.rejects(h.api.command(body));await h.api.command(body);assert.notEqual(h.calls[0].body.request_id,h.calls[1].body.request_id);});
test('operations and workspace receipts are distinct authenticated command paths',async()=>{const h=controller();await h.api.command({action:'save_inputs'});await h.api.operationsCommand({action:'execute_job'});assert.equal(h.calls[0].url,'/api/ees-work/workspace/command');assert.equal(h.calls[1].url,'/api/ees-work/operations');assert.match(h.calls[1].options.headers.Authorization,/Bearer /);});
test('late successful mutation cannot repopulate another account or scope',async()=>{const h=controller(),pending=deferred();h.setReply(()=>pending.promise);const waiting=h.api.command({action:'save_inputs'});h.setAuth('actor-b');pending.resolve({ok:true,run:{private:'a'}});assert.equal(await waiting,null);assert.equal(h.api.snapshot().state,null);});
test('normalization selects the exact current attempt and preserves historical decisions',()=>{const h=controller();const result=h.api.normalized({run:{jobs:{j:{current_attempt:'old',result_revision:1,decisions:[{item_id:'one',attempt_id:'old',result_revision:1},{item_id:'two',attempt_id:'new',result_revision:2}]}},attempts:[{id:'old',job_id:'j',result:{name:'selected'}},{id:'new',job_id:'j',result:{name:'unrelated'}}]}});assert.equal(result.run.jobs.j.result.name,'selected');assert.equal(result.run.jobs.j.decision_history.length,2);assert.equal(result.run.jobs.j.decisions.two,undefined);});
test('redacted evidence stays null instead of substituting another readable attempt',()=>{const h=controller();const result=h.api.normalized({run:{jobs:{j:{current_attempt:'redacted',result_revision:2}},attempts:[{id:'previous',job_id:'j',result:{private:'old'}},{id:'redacted',job_id:'j',result:null,evidence_access:'requires_current_source_access'}]}});assert.equal(result.run.jobs.j.result,null);});
test('Native model list keeps actual allowed identities and excludes direct embedding routes',async()=>{const h=controller();h.setReply(()=>({data:[{id:'allowed',name:'Native name'},{id:'direct',direct:true},{id:'embedding',type:'embedding'}]}));const list=await h.api.models();assert.equal(list.length,1);assert.equal(list[0].name,'Native name');assert.equal(h.context.document.body.dataset.eesModelCount,'1');});
test('AI reference never contains Native authorization tokens or confirmation intents',()=>{const h=controller();h.api.setSelection({workflow_id:'workflow',run_id:'run',job_id:'job'});h.api.setState({capabilities:{actor_id:'a'},workflow:{id:'workflow',revision:7},run:{id:'run',workflow_id:'workflow',revision:9,version:3,authorization:'Bearer actor-a-token',intent_token:'private-intent'}});const reference=h.api.reference(),serialized=JSON.stringify(reference);assert.equal(reference.kind,'workspace');assert.equal(reference.revision,9);assert.doesNotMatch(serialized,/actor-a-token|Bearer|intent_token|private-intent/);assert.match(serialized,/workflow/);});

test('late confirmation is rejected after account or selected work context changes',async()=>{for(const change of ['account','job']){const h=controller(),pending=deferred();h.setDialog(()=>pending.promise);const waiting=h.api.confirmDialog({title:'확인'});if(change==='account')h.setAuth('other');else h.api.setSelection({job_id:'other'});pending.resolve(true);assert.equal(await waiting,false);assert.equal(h.calls.length,0);}});

test('first workspace read refetches after default system selection before accepting operations',async()=>{const h=controller();h.api.setRestored(false);h.setReply(call=>call.url.startsWith('/api/ees-work/operations')?{ok:true,models:[]}:{ok:true,capabilities:{actor_id:'a'},systems:['EMS'],workflows:[],runs:[],my_work:[],ui_state:{revision:0,state:{}}});const state=await h.api.refresh();assert.ok(state);assert.equal(h.api.snapshot().selection.system_id,'EMS');assert.equal(h.calls.filter(call=>call.url.startsWith('/api/ees-work/workspace?')).length,2);assert.equal(h.renders.length,1);});


test('allowed model count survives a work selection change but not account change',async()=>{for(const kind of ['work','account']){const h=controller(),pending=deferred();h.setReply(()=>pending.promise);const waiting=h.api.models();if(kind==='work')h.api.setSelection({system_id:'EMS'});else h.setAuth('new-account');pending.resolve({data:[{id:'one'}]});const result=await waiting;assert.equal(result.length,kind==='work'?1:0);assert.equal(h.context.document.body.dataset.eesModelCount,kind==='work'?'1':undefined);}});
test('read-only tab changes retain polling rather than stopping current execution observation',async()=>{const h=controller();await h.api.select({tab:'history'},{fetch:false});assert.equal(h.timers.size,2);assert.equal(h.calls.length,0);});
test('returning from a Native workspace page starts a fresh workspace read',async()=>{const h=controller();h.api.sync();await new Promise(resolve=>setImmediate(resolve));h.context.location.pathname='/workspace/models';h.context.document.querySelector=()=>null;h.api.sync();h.context.location.pathname='/';h.context.document.querySelector=()=>({});h.api.sync();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.calls.filter(call=>call.url.startsWith('/api/ees-work/workspace?')).length,3);});
function optionHarness(){const h=controller();h.api.setSelection({workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});h.api.setState({run:{id:'r',revision:2,definition:{nodes:{j:{id:'j',inputs:[{id:'project',type:'text'},{id:'cr',type:'single',options_source:'tool',options:['forbidden-static']}]}}},jobs:{j:{effective_inputs:{project:'old'}}}},settings:{values:{},revision:0}});let inputs={project:'old'};h.view.readInputs=()=>({inputs});return {...h,setInputs:values=>{inputs=values;}};}
test('dynamic options use authenticated current-job inputs and never send an execution command',async()=>{const h=optionHarness();h.setInputs({project:'new',unrelated:'do-not-send'});h.setReply(()=>({ok:true,options:[{id:'CR-1',name:'현재 CR'}],source:{kind:'tool'},context:{revision:2}}));await h.api.loadOptions();assert.equal(h.calls[0].url,'/api/ees-work/workspace/options');assert.deepEqual(h.calls[0].body.inputs,{project:'new'});assert.equal(h.calls[0].body.action,undefined);assert.match(h.calls[0].options.headers.Authorization,/Bearer/);assert.equal(h.api.snapshot().state.input_options.cr.status,'ready');});
test('closing a panel during option lookup preserves the result and reference on reopening',async()=>{
 for(const failed of [false,true]){
  const h=optionHarness(),pending=deferred(),focus=[];
  h.context.window.__eesSourceShellV1.focusPanel=open=>focus.push(open);
  h.api.setSelection({chat_reference:{kind:'workspace',reference_kind:'historical',workflow_id:'w',run_id:'r',job_id:'j',attempt_id:'kept-attempt',version:2}});
  h.setInputs({project:'typed project'});h.setReply(()=>pending.promise);
  const reference=JSON.stringify(h.api.reference()),context=h.api.context(),selection=JSON.stringify(h.api.snapshot().selection);
  assert.equal(h.api.reference().kind,'workspace');assert.equal(h.api.reference().attempt_id,'kept-attempt');
  const waiting=h.api.loadOptions();
  assert.equal(h.calls.length,1);assert.equal(h.api.snapshot().state.input_options.cr.status,'loading');
  await h.api.handleClick({dataset:{action:'close_panel'}});
  assert.equal(h.api.snapshot().selection.panel_open,false);
  assert.equal(h.api.context(),context);assert.equal(JSON.stringify(h.api.reference()),reference);
  await h.api.loadOptions();assert.equal(h.calls.length,1,'Hidden panels do not start more option requests');
  pending.resolve(failed?{ok:false,httpError:true,status:403,error:{message:'source access denied'}}:{ok:true,options:[{id:'CR-1',name:'현재 CR'}],source:{kind:'tool'},context:{revision:2}});
  await waiting;
  const lookup=h.api.snapshot().state.input_options.cr;
  assert.equal(lookup.status,failed?'failed':'ready','A hidden panel must settle an already requested lookup');
  if(failed)assert.match(lookup.error,/source access denied/);else assert.equal(lookup.options[0].id,'CR-1');
  await h.api.handleClick({dataset:{action:'open_panel'}});
  await h.api.loadOptions();
  assert.equal(h.api.snapshot().state.input_options.cr,lookup);
  assert.equal(h.calls.length,1,'Reopening reuses the settled lookup without duplicate reads or work commands');
  assert.equal(h.api.context(),context);assert.equal(JSON.stringify(h.api.reference()),reference);
  assert.equal(JSON.stringify(h.api.snapshot().selection),selection);
  assert.deepEqual(h.view.readInputs().inputs,{project:'typed project'});assert.deepEqual(focus,[false,true]);
 }
});
test('late option results cannot replace a changed input dependency or another job',async()=>{for(const change of ['input','job','account']){const h=optionHarness(),pending=deferred();h.setReply(()=>pending.promise);const waiting=h.api.loadOptions();if(change==='input')h.setInputs({project:'changed'});else if(change==='job')h.api.setSelection({job_id:'other'});else h.setAuth('other');pending.resolve({ok:true,options:[{id:'stale'}]});await waiting;assert.equal(h.api.snapshot().state.input_options.cr.status,'loading');assert.equal(h.api.snapshot().state.input_options.cr.options.length,0);}});
test('dynamic option failure disables selection without falling back to manual examples',async()=>{const h=optionHarness();h.setReply(()=>({ok:false,httpError:true,status:403,error:{message:'source access denied'}}));await h.api.loadOptions();const lookup=h.api.snapshot().state.input_options.cr;const out=html('workInputHTML(field,undefined,{lookup})',{field:{id:'cr',type:'single',options_source:'tool',options:['forbidden-static']},lookup});assert.match(out,/<select[^>]* disabled/);assert.match(out,/source access denied/);assert.doesNotMatch(out,/forbidden-static/);});
test('removed dynamic selection stays explicit and no returned option is automatically chosen',()=>{const out=html('workInputHTML(field,"removed",{lookup})',{field:{id:'cr',type:'single',options_source:'common'},lookup:{status:'ready',options:[{id:'allowed',name:'현재 값'}],source:{kind:'common'}}});assert.match(out,/이전 선택 · 현재 목록 확인 필요/);assert.match(out,/removed[^>]* selected/);assert.doesNotMatch(out,/allowed[^>]* selected/);});


test('held Enter or Space cannot repeat a mutation while its ordinary first click still runs',async()=>{const h=controller();let prevented=0,stopped=0;const target={dataset:{action:'execute'},closest:selector=>selector==='[data-mutation]'||selector==='[data-ees-work]'||selector==='button[data-action]'?target:null};for(const key of ['Enter',' '])h.api.handleEvent({type:'keydown',key,repeat:true,target,preventDefault:()=>prevented++,stopImmediatePropagation:()=>stopped++});assert.equal(prevented,2);assert.equal(stopped,2);assert.equal(h.calls.length,0);h.api.setState({run:{revision:2}});h.api.setSelection({run_id:'r',job_id:'j'});h.api.handleEvent({type:'click',target,preventDefault:()=>{}});await new Promise(resolve=>setImmediate(resolve));assert.equal(h.calls.filter(call=>call.body?.action==='execute_job').length,1);});
test('scope execution uses the selected P or T and refuses unsaved run drafts',async()=>{const h=controller();h.api.setState({run:{revision:4}});h.api.setSelection({run_id:'r'});h.view.hasPendingInputs=()=>true;await h.api.handleClick({dataset:{action:'execute_scope',nodeId:'t1'}});assert.equal(h.calls.length,0);h.view.hasPendingInputs=()=>false;await h.api.handleClick({dataset:{action:'execute_scope',nodeId:'t1'}});assert.equal(h.calls[0].url,'/api/ees-work/operations');assert.equal(h.calls[0].body.node_id,'t1');assert.equal(h.calls[0].body.expected_revision,4);});


test('admin management renders existing Native identities and is absent for ordinary participants',()=>{const data={capabilities:{is_admin:true},factories:[{id:'f',name:'실제 등록',system_id:'EMS',revision:1}],access:[{id:'a',system_id:'EMS',factory_id:'f',principal_kind:'group',principal_id:'native-id',roles:['manager'],active:1}],people:[{name:'현재 그룹',value:{kind:'group',id:'native-id'}}]};const out=html('workAdminHTML(data)',{data});assert.match(out,/현재 그룹/);assert.match(out,/native-id/);assert.match(out,/data-action="admin_factory"/);assert.match(out,/data-action="admin_access"/);assert.doesNotMatch(html('workAdminHTML({capabilities:{is_admin:false}})'),/data-action=/);});
test('admin dialog refuses nonadmin identity before any write or new dialog',async()=>{const h=controller();h.api.setState({capabilities:{is_admin:false}});await assert.rejects(h.api.adminDialog('access'),/관리자/);assert.equal(h.calls.length,0);});
test('text export formats only fetched run history and retains redacted-source notice',()=>{const out=html('workExportText(document)',{document:{exported_at:'now',ui_state:{secret:'never-export'},run:{id:'r',version:1,status:'open',attempts:[{job_id:'j',number:1,status:'failed',inputs:{v:'historic'},result:null,evidence_access:'requires_current_source_access'}],jobs:{j:{decisions:[{item_id:'job',result_revision:1,verdict:'unknown',actor_id:'a'}]}}}}});assert.match(out,/historic/);assert.match(out,/원본 접근 권한 확인 필요/);assert.match(out,/unknown/);assert.doesNotMatch(out,/never-export/);});
test('legacy records have readonly navigation and escaped values with no execution controls',()=>{const out=html('workLegacyHTML(legacy)',{legacy:{read_only:true,records:[{id:'old',process_name:'<script>name</script>',simulation:true,status:'failed'}]}});assert.match(out,/사용 중지/);assert.match(out,/시뮬레이션/);assert.match(out,/open_legacy/);assert.doesNotMatch(out,/<script|data-action="execute|data-action="confirm/);});
test('authenticated source navigation preserves private drafts and resets only for account change',async()=>{const h=controller();let reset=0,suspend=0;h.view.reset=()=>reset++;h.view.suspend=()=>suspend++;h.api.sync();await new Promise(resolve=>setImmediate(resolve));const before=suspend,selection=JSON.parse(JSON.stringify(h.api.snapshot().selection));h.context.location.pathname='/workspace/skills';h.context.document.querySelector=()=>null;h.api.sync();assert.equal(suspend-before,0);assert.equal(reset,0);assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),selection);h.setAuth('other-account');h.api.sync();assert.equal(reset,1);});


test('AI item badge disappears only when a saved decision for that item is present',()=>{const job={result_block:'item_verdict'},saved={result:{items:[{id:'a',ai_suggestion:'적합'},{id:'b',ai_suggestion:'미흡'}]},decisions:{a:{verdict:'completed'}}};const out=html('workResultHTML(job,saved)',{job,saved});assert.equal((out.match(/AI 제안 ·/g) || []).length,1);assert.match(out,/미흡 · 사람 미확정/);});
test('date-only and timezone-qualified saved inputs preserve their exact stored value',()=>{assert.match(html('workInputHTML({id:"day",type:"datetime"},"2026-10-02")'),/type="date"[^>]*value="2026-10-02"/);assert.match(html('workInputHTML({id:"time",type:"datetime"},"2026-10-02T09:00:00+09:00")'),/type="text"[^>]*value="2026-10-02T09:00:00\+09:00"/);});


test('first Native chat proposal accepts only the creation-bound old context without a DB write',()=>{const h=controller();h.api.setSelection({mode:'author',workflow_id:'w'});h.api.setState({workflow:{revision:2}});h.designer.readDraft=()=>({revision:2,definition:{id:'w',name:'draft'}});const source=h.api.context(),creation=h.api.beginChatCreation();h.api.finishChatCreation(creation,'native-new');h.context.location.pathname='/c/native-new';const result=h.api.acceptNativeProposal('native-new',{context_id:source});assert.equal(result.ok,true);assert.equal(h.calls.length,0);});
test('first-chat context alias rejects another chat account changed version draft or scope',()=>{for(const change of ['chat','account','version','draft','scope']){const h=controller();let name='draft';h.api.setSelection({mode:'author',workflow_id:'w'});h.api.setState({workflow:{revision:2}});h.designer.readDraft=()=>({revision:2,definition:{id:'w',name}});const source=h.api.context(),creation=h.api.beginChatCreation();h.api.finishChatCreation(creation,'native-new');h.context.location.pathname='/c/native-new';if(change==='chat')h.context.location.pathname='/c/unrelated';if(change==='account')h.setAuth('other');if(change==='version')h.api.setState({workflow:{revision:3}});if(change==='draft')name='changed';if(change==='scope')h.api.setSelection({factory_id:'other'});assert.equal(h.api.acceptNativeProposal(h.context.location.pathname.slice(3),{context_id:source}).ok,false);assert.equal(h.calls.length,0);}});
test('unmatched Native creation finish cannot bless an arbitrary old chat context',()=>{const h=controller();h.api.setSelection({workflow_id:'w'});const source=h.api.context();h.api.finishChatCreation('not-issued','native-new');h.context.location.pathname='/c/native-new';assert.equal(h.api.acceptNativeProposal('native-new',{context_id:source}).ok,false);assert.equal(h.api.beginChatCreation(),'');});


test('start-run mutation uses workflow revision rather than absent run revision',async()=>{const h=controller();h.api.setState({workflow:{revision:7}});await h.api.command({action:'start_run',workflow_id:'w',version:1});assert.equal(h.calls[0].body.expected_revision,7);});
test('start dialog retains its captured workflow revision across a concurrent refresh',async()=>{const h=controller(),pending=deferred();h.context.document.querySelector=()=>({addEventListener(){}});h.api.setState({workflow:{id:'w',revision:6,published_version:1,versions:[{version:1}]}});h.api.setSelection({workflow_id:'w'});h.setDialog(()=>pending.promise);const waiting=h.api.handleClick({dataset:{action:'start_run'}});h.api.setState({workflow:{id:'w',revision:7,published_version:2,versions:[{version:2}]}});pending.resolve(true);await waiting;assert.equal(h.calls.find(call=>call.body?.action==='start_run').body.expected_revision,6);assert.equal(h.calls.find(call=>call.body?.action==='start_run').body.version,1);});
test('successful read polling preserves command rejection until successful command or explicit context change',async()=>{const h=controller();h.api.setState({workflow:{revision:3}});h.setReply(call=>call.options.method==='POST'?{ok:false,httpError:true,status:409,error:{message:'revision conflict'}}:{ok:true,systems:[],workflows:[],runs:[],ui_state:{revision:0,state:{}}});await assert.rejects(h.api.command({action:'start_run'}));await h.api.refresh();assert.match(h.api.snapshot().error,/revision conflict/);h.setReply(()=>({ok:true}));await h.api.command({action:'save_inputs'});assert.equal(h.api.snapshot().error,'');});


test('first-chat alias is retired when navigating through another conversation',async()=>{const h=controller();h.api.setSelection({mode:'author',workflow_id:'w'});h.api.setState({workflow:{revision:2}});h.designer.readDraft=()=>({revision:2,definition:{id:'w'}});const source=h.api.context(),creation=h.api.beginChatCreation();h.api.finishChatCreation(creation,'first');h.context.location.pathname='/c/other';h.api.sync();await new Promise(resolve=>setImmediate(resolve));h.api.setState({workflow:{revision:2}});h.context.location.pathname='/c/first';assert.equal(h.api.acceptNativeProposal('first',{context_id:source}).ok,false);});


test('saving one factory setting never promotes unchanged inherited values to overrides',()=>{const settings={values:{own:0,inherited:'base',untouched:'default'},overrides:{own:0}},fields=[{id:'own',scope:'workflow'},{id:'inherited',scope:'workflow'},{id:'untouched',scope:'factory'}];const result=html('workSettingsOverrides(settings,draft,fields)',{settings,draft:{own:0,inherited:'edited',untouched:'default'},fields});assert.deepEqual(JSON.parse(JSON.stringify(result)),{own:0,inherited:'edited'});assert.deepEqual(JSON.parse(JSON.stringify(html('workSettingsOverrides(settings,settings.values,fields)',{settings,fields}))),{own:0});});
test('run settings target the run factory while viewing all factories and retain raw overrides',()=>{const h=controller();h.api.setSelection({factory_id:''});const result=h.api.normalized({workflow:{settings:[{factory_id:'',values:{shared:'base'},revision:1},{factory_id:'actual-run-factory',values:{specific:false},revision:3}]},run:{factory_id:'actual-run-factory',jobs:{},attempts:[]}});assert.equal(result.settings.factory_id,'actual-run-factory');assert.equal(result.settings.revision,3);assert.deepEqual(JSON.parse(JSON.stringify(result.settings.overrides)),{specific:false});assert.equal(result.settings.values.shared,'base');});
test('existing empty text and empty list stay distinct from never-assigned optional values',()=>{const fields=[{name:'text',value:'',dataset:{inputType:'text',valuePresent:'true'}},{name:'list',value:'',dataset:{inputType:'list',valuePresent:'true'}},{name:'unset',value:'',dataset:{inputType:'text',valuePresent:'false'}}];const result=html('workReadInputs(form)',{form:{querySelectorAll:()=>fields}});assert.equal(result.text,'');assert.equal(result.list.length,0);assert.equal(result.unset,undefined);});


test('readonly Work tool setup needs Native admin and cancelling preview never writes assets',async()=>{const h=controller();h.api.setState({capabilities:{is_admin:false}});await assert.rejects(h.api.setupWorkTool(),/관리자/);assert.equal(h.calls.length,0);h.api.setState({capabilities:{is_admin:true},people:[],native_groups:[]});h.context.document.querySelector=()=>({addEventListener(){}});h.setReply(()=>({state:'missing',id:'ees_workflow',source_sha256:'actual-source',expected_token:'preview-hash',functions:['list','propose']}));h.setDialog(()=>Promise.resolve(false));await h.api.setupWorkTool();assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/api/v1/ees/assets/work-tool/status');assert.equal(h.calls[0].options.method,'GET');});
test('explicit Work tool confirmation sends preview token source hash and no public grants',async()=>{const h=controller();h.api.setState({capabilities:{is_admin:true},people:[],native_groups:[]});h.context.document.querySelector=()=>({addEventListener(){}});h.setReply(call=>call.url.endsWith('/status')?{state:'missing',id:'ees_workflow',source_sha256:'source-hash',expected_token:'preview-token',functions:['propose']}:call.url.endsWith('/setup')?{ok:true,changed:true}:{ok:true,systems:[],workflows:[],runs:[],ui_state:{revision:0,state:{}}});h.setDialog(()=>Promise.resolve(true));await h.api.setupWorkTool();const post=h.calls.find(call=>call.url.endsWith('/setup'));assert.equal(post.body.expected_token,'preview-token');assert.equal(post.body.source_sha256,'source-hash');assert.equal(post.body.confirmation,'register_readonly_work_tool');assert.deepEqual(post.body.access_grants,[]);});


function workToolUpdateHarness(overrides={}){
 const h=controller(),dialogs=[],listeners={};
 h.api.setState({capabilities:{is_admin:true,actor_id:'admin'},people:[],native_groups:[]});
 h.context.document.querySelector=()=>({addEventListener:(type,fn)=>{listeners[type]=fn;}});
 const status={state:'update_available',id:'ees_workflow',source_sha256:'program-hash',registered_source_sha256:'previous-hash',expected_token:'review-token',known_source:true,registered_source:{sha256:'previous-hash',date:'2026-10-02',format:'original'},program_source:{sha256:'program-hash',date:'2026-10-13'},...overrides};
 h.setReply(call=>call.url.endsWith('/status')?status:call.url.endsWith('/setup')||call.url.endsWith('/restore')?{ok:true,changed:true}:{ok:true,capabilities:{is_admin:true,actor_id:'admin'},systems:[],workflows:[],runs:[],my_work:[],ui_state:{revision:0,state:{}}});
 h.setDialog(options=>{dialogs.push(options);return Promise.resolve(true);});
 return {...h,status,dialogs,listeners};
}
test('known prior Work source needs explicit dated update confirmation and sends no ACL changes',async()=>{
 const h=workToolUpdateHarness();await h.api.setupWorkTool();
 assert.equal(h.dialogs[0].confirmLabel,'지금 프로그램 원본으로 바꾸기');
 assert.match(h.dialogs[1].html,/2026-10-02.*→.*2026-10-13/);
 for(const text of ['이름·소유자·읽기 권한·설정','코드 원본','비공개 백업'])assert.ok(h.dialogs[1].html.includes(text));
 assert.doesNotMatch(h.dialogs[1].html,/data-work-grant/);
 const posts=h.calls.filter(call=>call.options.method==='POST'&&call.url.includes('/assets/'));
 assert.equal(posts.length,1);assert.equal(posts[0].url,'/api/v1/ees/assets/work-tool/setup');
 assert.deepEqual(posts[0].body,{expected_token:'review-token',source_sha256:'program-hash',confirmation:'update_readonly_work_tool'});
 assert.match(h.dialogs.at(-1).html,/원본으로 바꿨습니다/);
});
test('cancelling either Work update confirmation never writes and changed context cannot approve stale source',async()=>{
 for(const rejectAt of [0,1]){const h=workToolUpdateHarness();let count=0;h.setDialog(()=>Promise.resolve(count++!==rejectAt));await h.api.setupWorkTool();assert.equal(h.calls.length,1);}
 for(const change of ['account','scope']){const h=workToolUpdateHarness(),pending=deferred();let count=0;h.setDialog(()=>count++===0?Promise.resolve(true):pending.promise);const task=h.api.setupWorkTool();await new Promise(resolve=>setImmediate(resolve));if(change==='account')h.setAuth('another-user');else h.api.setSelection({system_id:'APC'});pending.resolve(true);await task;assert.equal(h.calls.length,1);}
});
test('unsupported Work source shows escaped hashes and support mismatch with no write controls',async()=>{
 const h=workToolUpdateHarness({state:'blocked_existing',known_source:false,registered_source:null,registered_source_sha256:'<not-supported>',reason:'unsupported_source_form',backup:{can_restore:true}});
 await h.api.setupWorkTool();assert.equal(h.calls.length,1);assert.equal(h.dialogs.length,1);assert.equal(h.dialogs[0].readOnlyDetail,true);
 assert.match(h.dialogs[0].html,/&lt;not-supported&gt;/);assert.match(h.dialogs[0].html,/program-hash/);assert.match(h.dialogs[0].title,/지원 형태와 다릅니다/);
 assert.doesNotMatch(h.dialogs[0].html,/data-work-tool-restore|data-work-grant|사용자 수정/);assert.equal(h.dialogs[0].confirmLabel,undefined);
});
test('unsupported Work source explains the mismatch and gives an eight-character support hash without exposing the reason code',async()=>{
 const registeredHash='deadc0de'+'0123456789abcdef'.repeat(3)+'01234567';
 const h=workToolUpdateHarness({state:'blocked_existing',known_source:false,registered_source:null,registered_source_sha256:registeredHash,reason:'unsupported_source_form',backup:{can_restore:true}});
 await h.api.setupWorkTool();
 assert.equal(h.dialogs.length,1);const dialog=h.dialogs[0];
 assert.match(dialog.html,/등록된 코드가 알려진 제품 원본과 다릅니다\./);
 assert.ok(dialog.html.includes('이 화면은 코드를 바꾸지 않습니다. 등록 해시 앞 8자리를 개발 담당에게 알려 주세요.'));
 assert.match(dialog.html,/등록 해시 앞 8자리 · <code>deadc0de<\/code>/);
 assert.doesNotMatch(dialog.html,/unsupported_source_form|data-work-tool-restore|data-work-grant|사용자 수정/);
 assert.equal(dialog.readOnlyDetail,true);assert.equal(dialog.confirmLabel,undefined);
 assert.deepEqual(h.calls.map(call=>[call.options.method,call.url]),[['GET','/api/v1/ees/assets/work-tool/status']]);
});
test('ready Work source restores only by separate backup action and explicit confirmation',async()=>{
 const backup={id:'backup-id',sha256:'backup-receipt-hash',created_at:'2026-10-14T01:00:00Z',from_source_sha256:'previous-hash',to_source_sha256:'program-hash',can_restore:true};
 for(const approve of [false,true]){const h=workToolUpdateHarness({state:'ready',backup}),initial=deferred();let count=0;
  h.setDialog(options=>{h.dialogs.push(options);return count++===0?initial.promise:Promise.resolve(approve);});
  const task=h.api.setupWorkTool();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.dialogs[0].readOnlyDetail,true);assert.match(h.dialogs[0].html,/data-work-tool-restore/);
  h.listeners.click({target:{closest:selector=>selector==='[data-work-tool-restore]'?{}:null}});initial.resolve(false);await task;
  assert.match(h.dialogs[1].html,/previous-hash/);assert.match(h.dialogs[1].html,/이름·소유자·읽기 권한·설정/);
  const posts=h.calls.filter(call=>call.options.method==='POST'&&call.url.includes('/assets/'));
  assert.equal(posts.length,approve?1:0);
  if(approve){assert.equal(posts[0].url,'/api/v1/ees/assets/work-tool/restore');assert.deepEqual(posts[0].body,{expected_token:'review-token',source_sha256:'program-hash',confirmation:'restore_previous_work_tool',backup_id:'backup-id',backup_sha256:'backup-receipt-hash'});}
 }
});
test('unrestorable backup never offers restore and concurrent edits do not claim update success',async()=>{
 const blocked=workToolUpdateHarness({state:'ready',backup:{id:'old-backup',can_restore:false}});await blocked.api.setupWorkTool();assert.doesNotMatch(blocked.dialogs[0].html,/data-work-tool-restore/);assert.equal(blocked.calls.length,1);
 for(const code of ['concurrent_edit','work_tool_program_changed']){const h=workToolUpdateHarness();h.setReply(call=>call.url.endsWith('/status')?h.status:{httpError:true,status:409,detail:code});await assert.rejects(h.api.setupWorkTool(),new RegExp(code));assert.equal(h.dialogs.length,2);assert.match(h.api.snapshot().error,new RegExp(code));assert.equal(h.calls.filter(call=>call.options.method==='POST').length,1);}
});

test('input AI proposal preview and apply modify only the private draft until explicit save',()=>{const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{inputs:[{id:'value',scope:'run',type:'text'}]}}}};h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j',tab:'current'});h.api.setState({run});h.view.readInputs=()=>({inputs:{old:'keep'},revision:2});let applied;h.view.applyInputValues=values=>{applied=values;};const preview=h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'suggested'}});assert.equal(preview.saved,false);assert.equal(preview.executed,false);assert.equal(applied,undefined);h.api.applyInputProposal();assert.equal(applied.value,'suggested');assert.equal(h.calls.length,0);});
test('AI input preview rejects unknown setting fields and stale apply after user typing',()=>{const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{inputs:[{id:'value',scope:'run'},{id:'system_setting',scope:'workflow'}]}}}};h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j',tab:'current'});h.api.setState({run});let inputs={value:'before'};h.view.readInputs=()=>({inputs,revision:2});assert.throws(()=>h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{system_setting:'forbidden'}}));h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'AI'}});inputs={value:'typed-later'};assert.throws(()=>h.api.applyInputProposal(),/바뀌었습니다/);assert.equal(h.calls.length,0);});


test('per-message reference records exact immutable attempt and version without chat body or secrets',()=>{const h=controller();h.api.setSelection({workflow_id:'w',run_id:'r',job_id:'j'});h.api.setState({run:{version:2,revision:9,system_id:'EMS',factory_id:'f',jobs:{j:{current_attempt:'attempt-old',result_revision:3}}}});const ref=h.api.reference();assert.equal(ref.attempt_id,'attempt-old');assert.equal(ref.version,2);assert.equal(ref.result_revision,3);assert.doesNotMatch(JSON.stringify(ref),/token|chat_body|intent/);});
test('historical message chip never substitutes latest evidence for an old or absent attempt',()=>{const run={id:'r',version:1,jobs:{},attempts:[{id:'a1',job_id:'j',number:1,result:{value:'old exact'}},{id:'a2',job_id:'j',number:2,result:{value:'newest unrelated'}}]};const out=html('workHistoricalReferenceHTML(run,reference)',{run,reference:{run_id:'r',job_id:'j',attempt_id:'a1',version:1,result_revision:1}});assert.match(out,/old exact/);assert.doesNotMatch(out,/newest unrelated/);assert.match(html('workHistoricalReferenceHTML(run,{run_id:"r",job_id:"j"})',{run}),/당시 실행 시도 식별자가 기록되지 않았습니다/);assert.doesNotMatch(html('workHistoricalReferenceHTML(run,{run_id:"r",job_id:"j",attempt_id:"missing"})',{run}),/old exact|newest unrelated/);});

test('execution names the sole currently authorized model and preserves explicit multi-model choice',async()=>{
 const cases=[{models:[{id:'sole'}],expected:'sole'},{models:[{id:'first'},{id:'arena-model'}]},{models:[{id:'first'},{id:'arena-model'}],selected:'arena-model',expected:'arena-model'}];
 for(const action of ['execute','execute_scope'])for(const {models,selected,expected} of cases){const h=controller();h.context.document.querySelector=()=>({value:selected});h.api.setState({run:{revision:4},operations:{models}});h.api.setSelection({run_id:'r',job_id:'j'});await h.api.handleClick({dataset:{action,nodeId:'p'}});assert.equal(h.calls[0].body.model_id,expected);}
});
test('single model label is visible while multiple actual models retain the chooser',()=>{const single=html('workExecutionModelHTML(operations)',{operations:{models:[{id:'only',name:'현재 모델'}]}});assert.match(single,/AI 모델 · 현재 모델/);assert.doesNotMatch(single,/<select/);const multi=html('workExecutionModelHTML(operations)',{operations:{models:[{id:'first'},{id:'arena-model'}]}});assert.match(multi,/id="ees-work-execution-model"/);assert.match(multi,/arena-model/);});
test('unavailable dynamic inputs explain why AI omitted them without adding values',()=>{const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{inputs:[{id:'value',scope:'run',type:'text'},{id:'cr',name:'CR',scope:'run',type:'single'}]}}}};h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j'});h.api.setState({run});h.view.readInputs=()=>({inputs:{},revision:2});h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'draft'},unresolved_fields:[{field_id:'cr',reason:'options_dependency_required'}]});const proposal=h.renders.at(-1).state.input_proposal;assert.match(proposal.warnings[0],/CR · 선행 입력/);assert.equal(proposal.values.cr,undefined);assert.equal(h.calls.length,0);});

test('cached workspace stays visible through delayed chat routes without accepting late old-route reads',async()=>{
 const h=controller(),original=deferred(),current=deferred();await h.api.refresh();const kept=h.api.snapshot().state;
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(h.context.location.pathname==='/c/old'?original.promise:current.promise):{ok:true});
 h.context.location.pathname='/c/old';const start=h.renders.length;h.api.sync();h.context.location.pathname='/c/current';h.api.sync();
 assert.ok(h.renders.slice(start).every(value=>value.state!==null));assert.equal(h.api.snapshot().state,kept);
 original.resolve({ok:true,capabilities:{actor_id:'a'},workflows:[{id:'late'}],runs:[]});await new Promise(setImmediate);assert.equal(h.api.snapshot().state,kept);
 current.resolve({ok:true,capabilities:{actor_id:'a'},workflows:[{id:'current'}],runs:[]});await new Promise(setImmediate);assert.equal(h.api.snapshot().state.workflows[0].id,'current');
});
test('Native capability refresh never replaces the retained selected workspace or its operations',async()=>{
 const h=controller();h.api.setSelection({system_id:'EMS',workflow_id:'w',run_id:'r'});
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},workflow:{id:'w'},run:{id:'r',jobs:{}},workflows:[{id:'w'}],runs:[{id:'r'}]}:{ok:true,requests:[{id:'kept'}]});await h.api.refresh();const kept=h.api.snapshot().state;
 h.context.location.pathname='/workspace/skills';h.setReply(()=>({ok:true,capabilities:{actor_id:'a',native_access_available:true,native_access:{skills:true}},workflow:null,run:null,workflows:[],runs:[]}));await h.api.refresh();
 assert.equal(h.api.snapshot().state,kept);assert.equal(h.api.snapshot().state.operations.requests[0].id,'kept');assert.equal(h.api.snapshot().native_capabilities.native_access.skills,true);
 assert.equal(h.calls.at(-1).url,'/api/ees-work/workspace?');
});
test('new target loads once while returning target uses only its own system and factory snapshot',async()=>{
 const h=controller(),reply=call=>call.url.startsWith('/api/ees-work/workspace?')?(()=>{const query=new URL(call.url,'http://native.test').searchParams,id=query.get('workflow_id'),system=query.get('system_id'),factory=query.get('factory_id');return {ok:true,capabilities:{actor_id:'a'},workflows:[{id,system_id:system}],runs:[],workflow:{id,system_id:system,private:factory},systems:['EMS','FDC']};})():{ok:true};
 h.setReply(reply);await h.api.select({system_id:'EMS',factory_id:'f1',workflow_id:'w1'});const first=h.api.snapshot().state;await h.api.select({workflow_id:'w2'});const pending=deferred();h.setReply(()=>pending.promise);
 const returning=h.api.select({workflow_id:'w1'});assert.equal(h.api.snapshot().state,first);assert.equal(h.api.snapshot().target_loading,false);assert.equal(h.renders.at(-1).state.workflow.private,'f1');
 const other=h.api.select({factory_id:'f2',workflow_id:'w1'});assert.equal(h.api.snapshot().state.workflow,null);assert.equal(h.api.snapshot().state.workflows.length,0);assert.equal(h.api.snapshot().target_loading,true);assert.equal(h.api.reference().kind,'none');
 pending.resolve({ok:true,capabilities:{actor_id:'a'},workflows:[],runs:[],workflow:{id:'w1',private:'f2'}});await Promise.all([returning,other]);assert.equal(h.api.snapshot().state.workflow.private,'f2');
});
test('first scope keeps its navigation catalog but marks lists unread until workspace and operations both arrive',async()=>{
 for(const destination of [{system_id:'APC',factory_id:''},{system_id:'EMS',factory_id:'unvisited'}]){
  const h=controller(),workspace=deferred(),operations=deferred(),catalog={systems:['EMS','APC'],factories:[{id:'unvisited',system_id:'EMS'}]};
  h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,...catalog,capabilities:{actor_id:'a'},workflows:[{id:'old',system_id:'EMS'}],runs:[],my_work:[]}:{ok:true});
  await h.api.select({system_id:'EMS',factory_id:'',workflow_id:'old',collapsed:['setup']});
  h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?workspace.promise:operations.promise);
  const changed=h.api.select({...destination,workflow_id:'',run_id:'',tab:'my_work'});
  let rendered=h.renders.at(-1);assert.equal(rendered.scope_loading,true);assert.notEqual(rendered.state,null);assert.deepEqual(Array.from(rendered.state.systems),catalog.systems);assert.deepEqual(Array.from(rendered.selection.collapsed),['setup']);
  workspace.resolve({ok:true,...catalog,capabilities:{actor_id:'a'},workflows:[],runs:[],my_work:[]});await new Promise(setImmediate);
  assert.equal(h.renders.at(-1).scope_loading,true,'workspace response alone cannot claim the combined lists are empty');
  operations.resolve({ok:true});await changed;assert.equal(h.renders.at(-1).scope_loading,false);assert.equal(h.api.snapshot().state.workflows.length,0);
 }
});
test('returning to a received scope reuses its lists even when its previous selected workflow differs',async()=>{
 const h=controller();h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},systems:['EMS','APC'],workflows:[{id:'kept',system_id:'EMS'}],runs:[],my_work:[{id:'task'}],workflow:{id:'kept'}}:{ok:true});
 await h.api.select({system_id:'EMS',workflow_id:'kept'});
 const pending=deferred();h.setReply(()=>pending.promise);const away=h.api.select({system_id:'APC',workflow_id:''});const back=h.api.select({system_id:'EMS',workflow_id:''});
 const rendered=h.renders.at(-1);assert.equal(rendered.scope_loading,false);assert.equal(rendered.state.workflows[0]?.id,'kept');assert.equal(rendered.state.my_work[0]?.id,'task');assert.equal(rendered.state.workflow,null);
 pending.resolve({ok:true,capabilities:{actor_id:'a'},systems:['EMS','APC'],workflows:[],runs:[]});await Promise.all([away,back]);
});
test('unreceived scope panels never render empty My Work or history before their first response',()=>{
 for(const tab of ['my_work','records']){
  const host={dataset:{},isConnected:true,querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){},innerHTML:''};
  const context=renderer({document:{activeElement:null,querySelector:()=>null}});context.window.__eesSourceShellV1={hosts:()=>({panel:host}),publish(){}};
  const view=run(context,'createWorkView({callbacks:{}})'),state={capabilities:{actor_id:'a'},workflows:[],runs:[],my_work:[]},selection={mode:'work',tab,system_id:'APC'};
  view.render({state,selection,scope_loading:true});assert.match(host.innerHTML,/data-ees-scope-loading="panel"[^>]*>받는 중/);assert.doesNotMatch(host.innerHTML,/지금 처리할 내 업무가 없습니다|저장된 진행 건이 없습니다/);
  run(context,'createWorkView({callbacks:{}})').render({state,selection,scope_loading:false});assert.match(host.innerHTML,tab==='my_work'?/지금 처리할 내 업무가 없습니다/:/저장된 진행 건이 없습니다/);
 }
});
test('denied target removes cached private evidence and cannot restore it on a later visit',async()=>{
 for(const status of [401,403,404]){const h=controller();h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},workflow:{id:'w',private:'protected'},workflows:[{id:'w'}],runs:[]}:{ok:true});await h.api.select({workflow_id:'w'});await h.api.select({workflow_id:''});
 h.setReply(()=>({httpError:true,status,error:{message:'access removed'}}));await h.api.select({workflow_id:'w'});assert.equal(h.api.snapshot().state,null);assert.match(h.api.snapshot().error,/access removed/);
 const pending=deferred();h.setReply(()=>pending.promise);const different=h.api.select({workflow_id:''}),returning=h.api.select({workflow_id:'w'});assert.equal(h.api.snapshot().state,null);assert.equal(h.api.snapshot().target_loading,true);pending.resolve({httpError:true,status,error:{message:'access removed'}});await Promise.all([different,returning]);}
});
test('transient background read failure retains last workspace and explicit error',async()=>{
 const h=controller();await h.api.refresh();const kept=h.api.snapshot().state;h.setReply(()=>({httpError:true,status:503,error:{message:'temporary outage'}}));await h.api.refresh();assert.equal(h.api.snapshot().state,kept);assert.match(h.api.snapshot().error,/temporary outage/);assert.equal(h.renders.at(-1).state.capabilities.actor_id,'a');
});
test('unchanged refresh preserves section identities while a changed section alone gets a new value',async()=>{
 const h=controller();let name='first';h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},systems:['EMS'],workflows:[{id:'w',name}],runs:[]}:{ok:true,models:[{id:'m'}]});await h.api.refresh();const first=h.api.snapshot().state;await h.api.refresh();assert.equal(h.api.snapshot().state.workflows,first.workflows);assert.equal(h.api.snapshot().state.operations,first.operations);
 name='changed';await h.api.refresh();assert.notEqual(h.api.snapshot().state.workflows,first.workflows);assert.equal(h.api.snapshot().state.systems,first.systems);assert.equal(h.api.snapshot().state.operations,first.operations);
});
test('token reset cannot render or restore a prior account cached workspace while new reads wait',async()=>{
 const h=controller();h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},workflow:{id:'w',private:'account-a'},workflows:[{id:'w'}],runs:[]}:{ok:true});await h.api.select({workflow_id:'w'});
 const pending=deferred();h.setReply(()=>pending.promise);h.setAuth('account-b-token');h.api.sync();assert.equal(h.api.snapshot().state,null);const selection=h.api.select({workflow_id:'w'});assert.equal(h.api.snapshot().state,null);pending.resolve({ok:true,capabilities:{actor_id:'b'},workflows:[],runs:[]});await selection;assert.doesNotMatch(JSON.stringify(h.api.snapshot().state),/account-a/);
});

test('semantic scope and target denial clears protected state even when a transport reports HTTP 200 or 400',async()=>{
 for(const status of [200,400])for(const code of ['scope_forbidden','run_not_found','workflow_not_found','access_denied']){
  const h=controller();h.api.setState({capabilities:{actor_id:'a'},run:{id:'r',attempts:[{private:'protected'}]}});h.setReply(()=>({ok:false,status,error:{code,message:'current access denied'}}));
  await h.api.refresh();assert.equal(h.api.snapshot().state,null,`${status}/${code}`);assert.deepEqual(Object.keys(h.api.snapshot().native_capabilities),[]);assert.match(h.api.snapshot().error,/current access denied/);
 }
});
test('failed work result or history lookup blocks evidence and references while preserving private form drafts and navigation state',async()=>{
 for(const tab of ['current','history','records','historical_reference']){
  const h=controller();let resets=0;h.view.reset=()=>resets++;
  h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},workflow:{id:'w',revision:1},run:{id:'r',workflow_id:'w',revision:1,jobs:{},attempts:[{id:'a',inputs:{note:'private-result'}}]},workflows:[{id:'w'}],runs:[]}:{ok:true});
  await h.api.select({mode:'work',tab,workflow_id:'w',run_id:'r'});const kept=h.api.snapshot().state;
  h.setReply(()=>({httpError:true,status:503,error:{code:'workspace_unavailable',message:'failed current lookup'}}));await h.api.refresh();
  assert.equal(h.api.snapshot().state,kept);assert.equal(h.api.snapshot().evidence_unavailable,true,tab);assert.equal(h.api.reference().kind,'none');assert.equal(resets,0);assert.equal(h.renders.at(-1).evidence_unavailable,true);
  h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},workflows:[{id:'w'}],runs:[]}:{ok:true});await h.api.select({mode:'author',tab:'overview',workflow_id:'',run_id:''});assert.equal(h.api.snapshot().evidence_unavailable,false);
  const pending=deferred();h.setReply(()=>pending.promise);const returning=h.api.select({mode:'work',tab,workflow_id:'w',run_id:'r'});assert.equal(h.api.snapshot().state.run,null);assert.equal(h.api.snapshot().target_loading,true);pending.resolve({httpError:true,status:503,error:{message:'still unavailable'}});await returning;
 }
});
test('ordinary author background read outage keeps the live editor and its cached state without the work evidence block',async()=>{
 const h=controller();h.api.setSelection({mode:'author',tab:'overview',workflow_id:'w'});h.api.setState({capabilities:{actor_id:'a',can_author:true},workflow:{id:'w',revision:2,draft:{name:'saved'}}});const kept=h.api.snapshot().state;let resets=0,rendered=0;h.view.reset=()=>resets++;h.designer.render=()=>rendered++;
 h.setReply(()=>({httpError:true,status:503,error:{message:'temporary author read outage'}}));await h.api.refresh();assert.equal(h.api.snapshot().state,kept);assert.equal(h.api.snapshot().evidence_unavailable,false);assert.equal(resets,0);assert.equal(rendered,1);
});

test('received scope fallback preserves common operations but removes prior run requests and scope runs',async()=>{
 const h=controller(),operations={ok:true,tools:[{id:'known-tool'}],schedules:[{id:'known-schedule',enabled:true,next_at:1792015200}],slots:[{id:'known-slot'}],automatic_statuses:[{workflow_id:'kept',status:'running'}],actionable:[],models:[{id:'known-model'}],requests:[{id:'private-request',inputs:{secret:'prior-run'}}],scope_runs:[{id:'private-execution',run_id:'old-run'}]};
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a'},systems:['EMS','APC'],workflows:[{id:'kept',system_id:'EMS'}],runs:[],my_work:[],workflow:{id:'kept'},run:{id:'old-run',jobs:{}}}:operations);
 await h.api.select({system_id:'EMS',workflow_id:'kept',run_id:'old-run'});
 const pending=deferred();h.setReply(()=>pending.promise);const away=h.api.select({system_id:'APC',workflow_id:'',run_id:''});assert.equal(Object.keys(h.renders.at(-1).state.operations).length,0);
 const back=h.api.select({system_id:'EMS',workflow_id:'',run_id:''}),rendered=h.renders.at(-1);
 assert.equal(rendered.scope_loading,false);for(const name of ['tools','schedules','slots','automatic_statuses','models']){assert.ok(Array.isArray(rendered.state.operations[name]),name+' list is retained');assert.deepEqual(JSON.parse(JSON.stringify(rendered.state.operations[name])),operations[name],name+' survives');}
 assert.equal(rendered.state.run,null);assert.deepEqual(Array.from(rendered.state.operations.requests),[]);assert.deepEqual(Array.from(rendered.state.operations.scope_runs),[]);assert.doesNotMatch(JSON.stringify(rendered.state.operations),/private-request|private-execution|prior-run/);
 pending.resolve({ok:true,capabilities:{actor_id:'a'},systems:['EMS','APC'],workflows:[],runs:[]});await Promise.all([away,back]);
});

function inputProposalPanel({proposal=null,applied=null}={}){
 const host={dataset:{},isConnected:true,querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){},innerHTML:''};
 const context=renderer({document:{activeElement:null,querySelector:()=>null}});context.window.__eesSourceShellV1={hosts:()=>({panel:host}),publish(){}};
 // This renderer-only host has no DOM tree; Native tests cover incremental patching.
 run(context,'workPatchContent=(host,html)=>{host.innerHTML=html;};');
 const view=run(context,'createWorkView({callbacks:{}})'),state={capabilities:{actor_id:'a'},run:{id:'r',workflow_id:'w',revision:2,status:'open',inputs:{first:'사람이 쓴 값',other:'유지'},jobs:{j:{can_execute:true}},definition:{nodes:{j:{id:'j',name:'입력 확인',type:'j',mode:'tool',result_block:'values',inputs:[{id:'first',name:'첫 칸',type:'text',scope:'run'},{id:'other',name:'다른 칸',type:'text',scope:'run'}]}}}},input_proposal:proposal,input_proposal_applied:applied},selection={mode:'work',tab:'current',system_id:'EMS',workflow_id:'w',run_id:'r',job_id:'j'};
 view.render({state,selection});return {host,view,state,selection,render:()=>view.render({state,selection})};
}
test('chat input preview highlights proposed fields without changing controls or exposing JSON',()=>{
 const h=inputProposalPanel({proposal:{values:{first:'제안한 값'},warnings:['선택 목록 확인 필요']}}),out=h.host.innerHTML;
 assert.match(out,/class="ew-input-row ew-input-proposed" data-proposal-field="first"/);assert.doesNotMatch(out,/data-proposal-field="other"/);
 assert.match(out,/name="first"[^>]*value="사람이 쓴 값"/);assert.match(out,/ew-input-proposal-value">제안 · 제안한 값/);assert.match(out,/name="other"[^>]*value="유지"/);
 assert.match(out,/업무 도우미 제안 · 반영 전/);assert.match(out,/업무 도우미 입력 제안 · 1칸 · 반영하거나 버린 뒤 저장합니다/);assert.match(out,/선택 목록 확인 필요/);
 assert.match(out,/data-action="discard_input_proposal"[^>]*>버리기</);assert.match(out,/data-action="apply_input_proposal"[^>]*>반영</);
 assert.doesNotMatch(out,/propose_inputs|AI 입력 초안|<pre>|data-action="save_inputs"|data-action="execute"/);
 assert.equal(h.view.readInputs().inputs.first,'사람이 쓴 값');assert.equal(h.view.readInputs().dirty,false);
});
test('applied input proposal displays unsaved state and both explicit input actions',()=>{
 const h=inputProposalPanel();h.view.applyInputValues({first:'반영한 값'});h.state.input_proposal_applied={values:{first:'반영한 값'},at:'2026-10-20T12:00:00Z'};h.render();
 assert.match(h.host.innerHTML,/ew-input-proposal-applied[^>]*>저장 전</);assert.doesNotMatch(h.host.innerHTML,/반영됨 · /);assert.match(h.host.innerHTML,/name="first"[^>]*value="반영한 값"/);assert.match(h.host.innerHTML,/ew-input-proposal-source">도우미/);
 assert.match(h.host.innerHTML,/ew-input-applied-bar/);assert.match(h.host.innerHTML,/저장해야 실행할 수 있습니다/);assert.match(h.host.innerHTML,/data-action="discard_inputs"[^>]*>최신 값으로 돌아가기</);assert.equal((h.host.innerHTML.match(/data-action="save_inputs"/g)||[]).length,1);assert.match(h.host.innerHTML,/data-action="save_inputs"[^>]*>입력 저장</);
 assert.doesNotMatch(h.host.innerHTML,/data-action="execute"|ew-input-proposed|apply_input_proposal/);assert.equal(h.view.readInputs().dirty,true);assert.equal(h.state.run.inputs.first,'사람이 쓴 값');
});
test('input proposal formatting keeps typed false zero choices and escaped text readable',()=>{
 assert.equal(html('workInputProposalValue({type:"boolean"},false)'),'아니요');assert.equal(html('workInputProposalValue({type:"number"},0)'),'0');
 assert.equal(html('workInputProposalValue({type:"single",options:[{value:"code",label:"표시 이름"}]},"code")'),'표시 이름');
 const out=html('workInputHTML({id:"value",type:"text"},"kept",{proposal:{value:"<script>bad</script>"}})');assert.match(out,/value="kept"/);assert.match(out,/&lt;script&gt;/);assert.doesNotMatch(out,/<script>/);
 assert.match(html('workInputProposalBar({values:{a:1,b:2}},{result_block:"change_request"})'),/2칸 · 반영하거나 버린 뒤 요청합니다/);
});
test('pending input proposal blocks save and execution until explicitly discarded or applied',async()=>{
 const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{inputs:[{id:'value',scope:'run',type:'text'}]}}}};h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j',tab:'current'});h.api.setState({run});h.view.readInputs=()=>({inputs:{value:'kept'},revision:2});
 h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'suggested'}});
 for(const action of ['save_inputs','execute','execute_scope','confirm','request_intent'])await h.api.handleClick({dataset:{action,nodeId:'j'}});
 assert.equal(h.calls.length,0);await h.api.handleClick({dataset:{action:'discard_input_proposal'}});assert.equal(h.renders.at(-1).state.input_proposal,null);assert.equal(h.view.readInputs().inputs.value,'kept');assert.equal(h.calls.length,0);
});
test('panel no longer exposes authoring or execution proposal request transports',async()=>{
 const h=controller();assert.equal(h.designer.callbacks.propose,undefined);await h.api.handleClick({dataset:{action:'propose_inputs'}});assert.equal(h.calls.length,0);assert.doesNotMatch(launcherSource,/workspace\/proposal|ees-input-proposal-prompt|function proposeInputs\(/);
});
test('input proposal application preserves account target and saved version rejection',()=>{
 for(const change of ['account','job','version']){const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{inputs:[{id:'value',scope:'run'}]}}}};h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j',tab:'current'});h.api.setState({run});h.view.readInputs=()=>({inputs:{value:'kept'},revision:2});let applied=false;h.view.applyInputValues=()=>{applied=true;};h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'suggested'}});
 if(change==='account')h.setAuth('another-account');else if(change==='job')h.api.setSelection({job_id:'different'});else h.api.setState({run:{...run,revision:3}});assert.throws(()=>h.api.applyInputProposal(),/바뀌었습니다/);assert.equal(applied,false);assert.equal(h.calls.length,0);}
});

for(const [block,mode,hint] of [['change_request','tool','저장해야 요청할 수 있습니다'],['human_confirm','human','저장해야 확인할 수 있습니다'],['values','tool','저장해야 실행할 수 있습니다']])test('A4a applied input footer explains the next '+block+' action',()=>{
 const h=inputProposalPanel();Object.assign(h.state.run.definition.nodes.j,{mode,result_block:block});h.view.applyInputValues({first:'반영한 값'});h.state.input_proposal_applied={values:{first:'반영한 값'},at:'2026-10-20T12:00:00Z'};h.render();
 assert.ok(h.host.innerHTML.includes(hint));assert.match(h.host.innerHTML,/data-action="discard_inputs"[^>]*>최신 값으로 돌아가기</);assert.match(h.host.innerHTML,/data-action="save_inputs"[^>]*>입력 저장</);
});
function inputProposalController(){
 const h=controller(),panel=inputProposalPanel();h.api.setSelection(panel.selection);h.api.setState(panel.state);
 for(const method of ['readInputs','applyInputValues','discardInputs','capture'])h.view[method]=panel.view[method];
 h.view.render=snapshot=>{h.renders.push(snapshot);panel.view.render(snapshot);};
 const preview=()=>h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{first:'제안한 값',other:'다른 제안'}});
 return {...h,panel,preview};
}
test('discarding applied inputs restores all saved values and removes proposal attribution without a save',async()=>{
 const h=inputProposalController();h.preview();h.api.applyInputProposal();assert.equal(h.view.readInputs().inputs.first,'제안한 값');
 await h.api.handleClick({dataset:{action:'discard_inputs'}});
 assert.equal(h.view.readInputs().inputs.first,'사람이 쓴 값');assert.equal(h.view.readInputs().inputs.other,'유지');assert.equal(h.view.readInputs().dirty,false);
 assert.equal(h.renders.at(-1).state.input_proposal_applied,null);assert.doesNotMatch(h.panel.host.innerHTML,/ew-input-proposal-applied|ew-input-proposal-source|ew-input-applied-bar/);assert.equal(h.calls.length,0);
});
test('same-job history and settings tab visits retain pending input proposal and permit a later apply',async()=>{
 const h=inputProposalController();h.preview();
 for(const tab of ['history','settings','current']){await h.api.select({tab},{fetch:false});assert.equal(h.renders.at(-1).state.input_proposal.values.first,'제안한 값');}
 assert.match(h.panel.host.innerHTML,/업무 도우미 입력 제안 · 2칸/);h.api.applyInputProposal();assert.equal(h.view.readInputs().inputs.first,'제안한 값');assert.equal(h.calls.length,0);
});
test('same-job history and settings tab visits retain applied input attribution and unsaved values',async()=>{
 const h=inputProposalController();h.preview();h.api.applyInputProposal();
 for(const tab of ['history','settings','current']){await h.api.select({tab},{fetch:false});assert.equal(h.renders.at(-1).state.input_proposal_applied.values.first,'제안한 값');}
 assert.equal(h.view.readInputs().inputs.first,'제안한 값');assert.match(h.panel.host.innerHTML,/ew-input-proposal-source">도우미/);assert.match(h.panel.host.innerHTML,/저장 전/);assert.equal(h.calls.length,0);
});
for(const kind of ['pending','applied'])test('changing input proposal task or scope clears '+kind+' state',async()=>{
 for(const patch of [{job_id:'other'},{run_id:'other'},{workflow_id:'other'},{system_id:'other'},{factory_id:'other'},{mode:'author'}]){
  const h=inputProposalController();h.preview();if(kind==='applied')h.api.applyInputProposal();await h.api.select(patch,{fetch:false});
  assert.equal(h.renders.at(-1).state?.input_proposal??null,null);assert.equal(h.renders.at(-1).state?.input_proposal_applied??null,null);
 }
});
test('an account change cannot retain input proposal state through tab navigation',async()=>{
 for(const applied of [false,true]){const h=inputProposalController();h.preview();if(applied)h.api.applyInputProposal();h.setAuth('account-b');await h.api.select({tab:'history'},{fetch:false});assert.equal(h.renders.at(-1).state?.input_proposal??null,null);assert.equal(h.renders.at(-1).state?.input_proposal_applied??null,null);}
});
for(const action of ['confirm_list','confirm','confirm_verdicts','request_intent','execute','execute_scope'])test('pending input proposal explains blocked result action '+action,async()=>{
 const h=inputProposalController();h.preview();await h.api.handleClick({dataset:{action,nodeId:'j'}});
 assert.equal(h.calls.length,0);assert.equal(h.renders.at(-1).error,'업무 도우미 입력 제안을 먼저 반영하거나 버려 주세요.');assert.match(h.panel.host.innerHTML,/업무 도우미 입력 제안을 먼저 반영하거나 버려 주세요\./);
});
for(const action of ['apply_input_proposal','discard_input_proposal'])test('resolving input proposal clears its blocked-action guidance via '+action,async()=>{
 const h=inputProposalController();h.preview();await h.api.handleClick({dataset:{action:'confirm_list'}});assert.match(h.renders.at(-1).error,/입력 제안을 먼저/);
 await h.api.handleClick({dataset:{action}});assert.equal(h.renders.at(-1).error,'');assert.doesNotMatch(h.panel.host.innerHTML,/업무 도우미 입력 제안을 먼저 반영하거나 버려 주세요\./);assert.equal(h.calls.length,0);
});

for(const factoryId of ['', 'factory-a'])test('pending run input proposal permits independent settings save for '+(factoryId||'workflow'),async()=>{
 const h=controller(),run={id:'r',workflow_id:'w',revision:2,definition:{nodes:{j:{id:'j',inputs:[{id:'value',scope:'run'},{id:'shared',scope:'workflow'}]}}}},settings={factory_id:factoryId,revision:4,values:{shared:'saved setting'}};
 h.api.setSelection({system_id:'EMS',factory_id:factoryId,run_id:'r',workflow_id:'w',job_id:'j',tab:'current'});h.api.setState({run,settings});h.view.readInputs=()=>({inputs:{value:'kept'},revision:2});
 h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{value:'suggested'}});await h.api.select({tab:'settings'},{fetch:false});
 h.view.readInputs=()=>({inputs:{shared:'edited setting'},revision:4,settings:true,key:'settings-key',serial:1});let saved;h.view.clearInputs=(...args)=>{saved=args;};
 h.setReply(call=>call.body?.action==='save_settings'?{ok:true,revision:5}:call.url.startsWith('/api/ees-work/workspace?')?{ok:true,run:{...run,revision:3},settings:{...settings,revision:5,values:{shared:'edited setting'}},capabilities:{actor_id:'a'}}:{ok:true});
 await h.api.handleClick({dataset:{action:'save_inputs'}});
 const writes=h.calls.filter(call=>call.body?.action);assert.equal(writes.length,1);assert.equal(writes[0].body.action,'save_settings');assert.equal(writes[0].body.factory_id,factoryId);assert.equal(writes[0].body.values.shared,'edited setting');assert.equal(writes[0].body.expected_revision,4);assert.equal(saved[0],'settings-key');assert.equal(h.renders.at(-1).state.input_proposal.values.value,'suggested');
 // Changed effective settings can increment the run revision; retaining the
 // proposal must not weaken its saved-version guard.
 await h.api.select({tab:'current'},{fetch:false});h.view.readInputs=()=>({inputs:{value:'kept'},revision:3});assert.throws(()=>h.api.applyInputProposal(),/바뀌었습니다/);assert.equal(h.calls.filter(call=>call.body?.action).length,1);
});
test('proposal received on settings snapshots the unsaved current inputs and applies after returning',async()=>{
 const h=inputProposalController();h.panel.state.settings={revision:4,values:{shared:'saved setting'}};h.panel.state.run.definition.nodes.j.inputs.push({id:'shared',name:'업무 값',type:'text',scope:'workflow'});
 h.view.applyInputValues({first:'직접 쓴 값',other:'직접 남긴 값'});await h.api.select({tab:'settings'},{fetch:false});assert.equal(h.view.readInputs().inputs.shared,'saved setting');
 h.api.previewInputProposal({proposal_kind:'inputs',run_id:'r',workflow_id:'w',job_id:'j',base_revision:2,proposal:{first:'제안한 값'}});
 assert.equal(h.view.readInputs().inputs.shared,'saved setting');await h.api.select({tab:'current'},{fetch:false});assert.equal(h.view.readInputs().inputs.first,'직접 쓴 값');
 h.api.applyInputProposal();assert.equal(h.view.readInputs().inputs.first,'제안한 값');assert.equal(h.view.readInputs().inputs.other,'직접 남긴 값');assert.equal(h.panel.state.run.inputs.first,'사람이 쓴 값');
 await h.api.select({tab:'settings'},{fetch:false});assert.equal(h.view.readInputs().inputs.shared,'saved setting');assert.equal(h.view.readInputs().inputs.first,undefined);assert.equal(h.calls.length,0);
});
test('settings-tab proposal still rejects later current-input changes',async()=>{
 const h=inputProposalController();h.panel.state.settings={revision:4,values:{shared:'saved setting'}};await h.api.select({tab:'settings'},{fetch:false});h.preview();await h.api.select({tab:'current'},{fetch:false});
 h.view.applyInputValues({first:'제안 뒤 직접 수정'});assert.throws(()=>h.api.applyInputProposal(),/바뀌었습니다/);assert.equal(h.view.readInputs().inputs.first,'제안 뒤 직접 수정');assert.equal(h.calls.length,0);
});
