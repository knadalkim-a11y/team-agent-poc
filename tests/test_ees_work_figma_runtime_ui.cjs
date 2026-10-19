/* Reconstructed from recorded source reads and patches after workspace loss.
 * These are controller/renderer contracts, not Native product evidence. */
const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
const html=(source,values={})=>run(renderer(values),source);

test('procedure entry initializes once through POST then renders ordinary workflows',async()=>{
 const h=controller(),state={ok:true,capabilities:{actor_id:'a',can_author:true,managed_systems:['EMS']},systems:['EMS'],initial_procedures_ready:false,workflows:[],runs:[],ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'author',tab:'overview',system_id:'EMS'});
 h.setReply(call=>{if(call.body?.action==='initialize_procedures'){assert.equal(call.body.system_id,'EMS');assert.equal(call.body.expected_revision,0);state.initial_procedures_ready=true;state.workflows=[{id:'initial',name:'Initial procedure',system_id:'EMS'}];return {ok:true};}return call.url.includes('workspace?')?state:{ok:true};});
 await h.api.refresh();await h.api.refresh();
 assert.equal(h.calls.filter(call=>call.body?.action==='initialize_procedures').length,1);
 assert.equal(h.api.snapshot().state.workflows[0].id,'initial');
});

test('initial registration is not attempted by readers, tools pages or ordinary work views',async()=>{
 for(const [mode,tab,managed] of [['author','overview',[]],['author','tools',['EMS']],['work','my_work',['EMS']]]){
  const h=controller(),state={ok:true,capabilities:{actor_id:'a',can_author:!!managed.length,managed_systems:managed},systems:['EMS'],initial_procedures_ready:false,workflows:[],runs:[],ui_state:{revision:0,state:{}}};
  h.api.setState(state);h.api.setSelection({mode,tab,system_id:'EMS'});h.setReply(call=>call.url.includes('workspace?')?state:{ok:true});await h.api.refresh();
  assert.equal(h.calls.filter(call=>call.body?.action==='initialize_procedures').length,0);
 }
});

test('initial registration failure is reported without pretending procedures exist',async()=>{
 const h=controller(),state={ok:true,capabilities:{actor_id:'a',can_author:true,managed_systems:['EMS']},systems:['EMS'],initial_procedures_ready:false,workflows:[],runs:[],ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'author',tab:'overview',system_id:'EMS'});
 h.setReply(call=>call.body?.action==='initialize_procedures'?{ok:false,error:{message:'Registration failed'}}:call.url.includes('workspace?')?state:{ok:true});
 assert.equal(await h.api.refresh(),null);assert.match(h.api.snapshot().error,/Registration failed/);assert.equal(h.api.snapshot().state.workflows.length,0);
});

const nativeCapabilities=(overrides={})=>({actor_id:'a',is_admin:false,can_author:false,managed_systems:[],native_access_available:true,native_access:{models:false,knowledge:false,prompts:false,skills:false,tools:false,admin:false},...overrides});
function nativeNavigationHarness(capabilities=nativeCapabilities({is_admin:true,can_author:true,native_access:{models:true,knowledge:true,prompts:true,skills:true,tools:true,admin:true}})){
 const h=controller(),navigation=[],restores=[];let current={prompt:'대화 초안',files:[{id:'kept-file'}],selectedToolIds:['kept-tool'],selectedModels:['kept-model'],params:{temperature:.2}},ready=true;
 const state={capabilities,systems:['EMS'],workflows:[],runs:[],operations:{},ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'author',system_id:'EMS',workflow_id:'w',run_id:'',job_id:'j',tab:'overview',panel_width:620});h.context.location.pathname='/c/original';h.context.location.search='?keep=1';
 h.context.window.__eesSourceShellV1.navigate=path=>{navigation.push(path);const next=new URL(path,'http://native.test');h.context.location.pathname=next.pathname;h.context.location.search=next.search;};
 h.context.document.querySelector=selector=>selector==='#sidebar-search-button'?{}:selector==='#chat-container #chat-pane'&&!/^\/(workspace|admin)/.test(h.context.location.pathname)?{}:null;
 h.designer.canNavigate=()=>true;h.designer.readDraft=()=>({definition:{name:'미저장 작성'},dirty:true});
 h.context.window.__eesNativeDraftV1={persistent:true,ready:()=>ready,read:()=>JSON.parse(JSON.stringify(current)),flush:()=>true,restore:async serialized=>{current=JSON.parse(serialized);restores.push(current);return true;}};
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,...state}:{ok:true});
 return {...h,navigation,restores,state,setDraft:value=>{current=value;},readDraft:()=>current,setReady:value=>{ready=value;},async open(id='skills'){await h.api.handleClick({dataset:{action:'native_open',nativeId:id}});h.api.sync();await new Promise(setImmediate);},async back(action='procedures',extra={}){const target={dataset:{action,...extra},closest:selector=>['[data-ees-work]','#ees-work-entry','button[data-action]'].includes(selector)?target:null};h.api.handleEvent({type:'click',isTrusted:true,target,preventDefault(){},stopImmediatePropagation(){}});h.api.sync();await new Promise(setImmediate);}};
}

test('workspace menu uses server permissions for three groups and hides unavailable Native destinations',()=>{
 const admin=nativeCapabilities({is_admin:true,can_author:true,native_access:{models:true,knowledge:true,prompts:true,skills:true,tools:true,admin:true}});
 const rendered=html('workWorkspaceMenuHTML({capabilities}, {tab:"tools"})',{capabilities:admin});
 assert.equal((rendered.match(/class="ew-nav-group"/g)||[]).length,3);for(const label of ['업무 만들기','AI 설정','관리자만','스킬·지침','AI 도우미','참고 문서','빠른 문장','공장·접근 범위','관리자 설정'])assert.ok(rendered.includes(label),label);
 assert.doesNotMatch(rendered,/기능 연결|data-native-id="tools"/);
 assert.match(rendered,/<small class="ew-nav-native-name">모델<\/small>/);assert.doesNotMatch(rendered,/native_workspace|native_skills|Native 모델|Open WebUI에서 열기|native_return/);
 const nativeSelected=html('workWorkspaceMenuHTML({capabilities,workflows:[{id:"kept",name:"Previous draft",updated_at:"2026-10-11"}]}, {workflow_id:"kept",tab:"overview",native_id:"skills"})',{capabilities:admin});
 assert.equal((nativeSelected.match(/aria-current="page"/g)||[]).length,1);assert.match(nativeSelected,/data-native-id="skills"[^>]*aria-current="page"/);
 const groups=[...rendered.matchAll(/<section class="ew-nav-group"><h3 class="ew-nav-group-title">([^<]+)<\/h3><nav class="ew-nav-links">(.*?)<\/nav><\/section>/g)].map(match=>[match[1],match[2]]);
 assert.match(groups[0][1],/data-native-id="skills"/);assert.doesNotMatch(groups[0][1],/data-native-id="(?:models|knowledge|prompts)"/);for(const id of ['models','knowledge','prompts'])assert.ok(groups[1][1].includes('data-native-id="'+id+'"'));assert.doesNotMatch(groups[1][1],/data-native-id="skills"/);
 const author=nativeCapabilities({can_author:true,managed_systems:['EMS'],native_access:{skills:true,tools:true}}),authorHTML=html('workWorkspaceMenuHTML({capabilities}, {})',{capabilities:author});
 assert.match(authorHTML,/업무 만들기/);assert.match(authorHTML,/data-native-id="skills"/);assert.doesNotMatch(authorHTML,/AI 설정/);assert.doesNotMatch(authorHTML,/관리자만|기능 연결|공장·접근 범위|data-native-id="models"/);
 for(const cap of [nativeCapabilities(),{...admin,native_access_available:false},{...admin,native_access_available:undefined},{...admin,native_access:{skills:'true'}}]){
  const output=html('workWorkspaceMenuHTML({capabilities}, {})',{capabilities:cap});assert.doesNotMatch(output,/data-action="native_open"/);
 }
});
test('tools-only permission keeps D9 workspace access with an honest empty menu and no admin link',()=>{
 const capabilities=nativeCapabilities({native_access:{tools:true}});
 assert.equal(html('workCanWorkspace(capabilities)',{capabilities}),true);
 const output=html('workWorkspaceMenuHTML({capabilities}, {})',{capabilities});assert.match(output,/EES Workflow에서 열 수 있는 항목이 없습니다/);assert.doesNotMatch(output,/data-action=|기능 연결/);
 assert.equal(html('workCanWorkspace(capabilities)',{capabilities:nativeCapabilities()}),false);
 assert.equal(html('workCanWorkspace(capabilities)',{capabilities:nativeCapabilities({managed_systems:['OTHER']})}),true);
});
test('blocked Native navigation has a visible escaped authoring alert without replacing its editor',()=>{
 const error='첨부한 이미지는 먼저 보내거나 제거한 뒤 열어 주세요. <개인 글>';
 const output=html('workWorkspaceMenuHTML({capabilities}, {}, error)',{capabilities:nativeCapabilities({can_author:true}),error});assert.match(output,/role="alert" data-native-navigation-error/);assert.match(output,/첨부한 이미지는 먼저 보내거나 제거/);assert.match(output,/&lt;개인 글&gt;/);assert.doesNotMatch(output,/<개인 글>/);
});
test('forged denied Native and author actions do not navigate or mutate state',async()=>{
 const h=nativeNavigationHarness(nativeCapabilities());h.api.setSelection({mode:'work'});
 for(const nativeId of ['skills','tools','admin','https://foreign.invalid/','__proto__'])await h.api.handleClick({dataset:{action:'native_open',nativeId}});
 for(const action of ['procedures','tools','workspace_admin','native_skills','native_workspace'])await h.api.handleClick({dataset:{action}});
 await h.api.handleClick({dataset:{action:'mode',mode:'author'}});
 assert.equal(h.api.snapshot().selection.mode,'work');assert.equal(h.navigation.length,0);assert.equal(h.calls.length,0);
});
test('scope option labels never authorize a denied or undisclosed actual scope',async()=>{
 const h=controller(),state={capabilities:nativeCapabilities(),systems:['EMS','APC'],factories:[{id:'allowed-factory',name:'Allowed',system_id:'EMS'},{id:'revoked-factory',name:'Revoked',system_id:'EMS'}],scope_options:{systems:[{id:'EMS',name:'EMS',allowed:true},{id:'APC',name:'APC',allowed:false},{id:'FDC',name:'FDC',allowed:false}],factories:[{id:'allowed-factory',allowed:true},{id:'revoked-factory',allowed:false},{id:'hidden-factory',allowed:false}]},workflows:[],runs:[],ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'work',system_id:'EMS',factory_id:''});
 for(const systemId of ['APC','FDC','unknown'])await h.api.handleClick({dataset:{action:'choose_system',systemId}});
 for(const factoryId of ['revoked-factory','hidden-factory','unknown'])await h.api.handleClick({dataset:{action:'choose_factory',factoryId}});
 assert.equal(h.calls.length,0);assert.equal(h.api.snapshot().selection.system_id,'EMS');assert.equal(h.api.snapshot().selection.factory_id,'');
 state.scope_options.systems.push({id:'metadata-only',allowed:true});await h.api.handleClick({dataset:{action:'choose_system',systemId:'metadata-only'}});assert.equal(h.calls.length,0);
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,...state}:{ok:true});await h.api.handleClick({dataset:{action:'choose_factory',factoryId:'allowed-factory'}});
 assert.equal(h.api.snapshot().selection.factory_id,'allowed-factory');assert.ok(h.calls.some(call=>call.url.includes('factory_id=allowed-factory')));
});
test('factory-scoped user can select another allowed system with factory cleared and composer preserved',async()=>{
 const h=nativeNavigationHarness(nativeCapabilities()),draft=JSON.parse(JSON.stringify(h.readDraft()));
 h.state.systems=['EMS','APC'];h.state.factories=[{id:'ems-factory',name:'EMS factory',system_id:'EMS'}];
 h.state.scope_options={systems:[{id:'EMS',name:'EMS',allowed:true,role:'participant'},{id:'APC',name:'APC',allowed:true,role:'participant'},{id:'FDC',name:'FDC',allowed:false,role:''}],factories:[{id:'ems-factory',name:'EMS factory',system_id:'EMS',allowed:true,role:'participant'}]};
 h.api.setSelection({mode:'work',system_id:'EMS',factory_id:'ems-factory',workflow_id:'ems-work',run_id:'ems-run',job_id:'ems-job',collapsed:['ops']});
 await h.api.sourceAction({action:'choose_system',systemId:'APC'});
 const selection=h.api.snapshot().selection;
 assert.equal(selection.system_id,'APC');assert.equal(selection.factory_id,'');assert.equal(selection.workflow_id,'');assert.equal(selection.run_id,'');assert.equal(selection.job_id,'');assert.deepEqual(JSON.parse(JSON.stringify(selection.collapsed)),['ops']);
 const workspace=h.calls.find(call=>call.url.startsWith('/api/ees-work/workspace?')),query=new URL(workspace.url,'http://native.test').searchParams;
 assert.equal(query.get('system_id'),'APC');assert.equal(query.get('factory_id'),'');
 assert.deepEqual(h.readDraft(),draft);assert.deepEqual(h.restores,[]);assert.deepEqual(h.navigation,[]);assert.equal(h.context.location.pathname,'/c/original');
 const count=h.calls.length;await h.api.sourceAction({action:'choose_system',systemId:'FDC'});await h.api.sourceAction({action:'choose_system',systemId:'unknown'});assert.equal(h.calls.length,count);assert.equal(h.api.snapshot().selection.system_id,'APC');
});
test('Native scope preserves separate permission metadata and rejects disabled options without navigation',async()=>{
 const h=nativeNavigationHarness();h.state.scope_options={systems:[{id:'EMS',name:'EMS',allowed:true,role:'owner'},{id:'FDC',name:'FDC',allowed:false,role:''}],factories:[]};await h.open();
 assert.deepEqual(h.renders.at(-1).native_scope.scope_options,h.state.scope_options);
 const before=h.calls.length;await h.api.sourceAction({action:'choose_system',systemId:'FDC'});
 assert.equal(h.calls.length,before);assert.equal(h.context.location.pathname,'/workspace/skills');assert.equal(h.api.snapshot().selection.system_id,'EMS');
 assert.deepEqual(h.navigation,['/workspace/skills']);
});
test('all six allowed Native destinations use direct static routes without a sidebar link',async()=>{
 for(const id of ['skills','models','knowledge','prompts','tools','admin']){const h=nativeNavigationHarness();await h.open(id);assert.deepEqual(h.navigation,[id==='admin'?'/admin/settings':'/workspace/'+id]);assert.equal(h.renders.at(-1)?.native_shell,true);assert.equal(h.renders.at(-1)?.native_id,id);assert.equal(h.calls.filter(call=>call.body).length,0);}
});
test('same-section EES menu preserves selection and unsaved designer session plus the full composer without sending',async()=>{
 const h=nativeNavigationHarness(),before=JSON.parse(JSON.stringify(h.api.snapshot().selection)),draft=JSON.parse(JSON.stringify(h.readDraft()));let captures=0,designerCaptures=0,closed=0;
 h.view.capture=()=>captures++;h.designer.readDraft=()=>{designerCaptures++;return {dirty:true};};h.designer.closeStart=()=>closed++;
 await h.open();await h.back();
 assert.deepEqual(h.navigation,['/workspace/skills','/c/original?keep=1']);assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),before);assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);assert.equal(captures,2);assert.ok(designerCaptures>=2);assert.equal(closed,0);assert.equal(h.calls.filter(call=>call.body).length,0);
});
test('delayed first chat creation keeps Native open and returns root or folder drafts to the created chat',async()=>{
 for(const path of ['/','/folders/saved-folder']){
  const h=nativeNavigationHarness();h.context.location.pathname=path;h.context.location.search='';const draft=JSON.parse(JSON.stringify(h.readDraft()));
  const creation=h.api.beginChatCreation(),oldContext=h.api.context();assert.ok(creation);await h.open();
  h.api.finishChatCreation(creation,'created-during-native');assert.equal(h.context.window.__eesNativeWorkV1.chatCreated('created-during-native'),true);
  assert.equal(h.context.location.pathname,'/workspace/skills');assert.deepEqual(h.navigation,['/workspace/skills']);
  await h.back();assert.equal(h.navigation.at(-1),'/c/created-during-native');assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);
  assert.equal(h.api.acceptNativeProposal('created-during-native',{context_id:oldContext}).ok,true);
 }
});
test('late first chat signals cannot rewrite existing chat or another actor return tickets',async()=>{
 for(const kind of ['existing','actor','invalid']){
  const h=nativeNavigationHarness();if(kind!=='existing'){h.context.location.pathname='/';h.context.location.search='';}await h.open();
  if(kind==='actor')h.setAuth('another-token');
  assert.equal(h.context.window.__eesNativeWorkV1.chatCreated(kind==='invalid'?'foreign/chat':'new-chat'),false);assert.deepEqual(h.navigation,['/workspace/skills']);
 }
 const h=nativeNavigationHarness();h.context.location.pathname='/notes';assert.equal(h.api.beginChatCreation(),'');
});
test('Native loaded draft is not reimported and different nonempty content is never overwritten',async()=>{
 for(const different of [false,true]){const h=nativeNavigationHarness();await h.open();if(different)h.setDraft({prompt:'귀환한 대화의 새 글',files:[],selectedToolIds:['new']});await h.back();assert.equal(h.restores.length,0);if(different)assert.equal(h.readDraft().prompt,'귀환한 대화의 새 글');}
});
test('return waits for the persistent Native editor and never imports over new interaction state',async()=>{
 for(const type of ['input','change','click','keydown']){
  const h=nativeNavigationHarness();await h.open();h.setReady(false);await h.back();assert.equal(h.restores.length,0);
  // Source Chat retains interaction state; return never imports a snapshot.
  const next={prompt:'',files:[],selectedModels:['new-model'],selectedToolIds:['new-tool']};h.setDraft(next);h.setReady(true);h.api.sync();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.restores.length,0);assert.deepEqual(h.readDraft(),next);
 }
});
test('Native departure blocks busy editors and failed or changed draft flushes',async()=>{
 const busy=nativeNavigationHarness();busy.designer.canNavigate=()=>false;await assert.rejects(busy.open(),/저장 또는 화면 준비/);assert.equal(busy.navigation.length,0);
 const failed=nativeNavigationHarness();failed.context.window.__eesNativeDraftV1.flush=()=>false;await assert.rejects(failed.open(),/보존하지 못했습니다/);assert.equal(failed.navigation.length,0);
 const changed=nativeNavigationHarness(),pending=deferred();changed.context.window.__eesNativeDraftV1.flush=()=>pending.promise;const moving=changed.open();changed.setDraft({prompt:'flush 중 새 입력'});pending.resolve(true);await moving;assert.equal(changed.navigation.length,1);assert.equal(changed.readDraft().prompt,'flush 중 새 입력');
});
test('missing persistent source Chat refuses departure without reconstructing Native DOM',async()=>{
 const h=nativeNavigationHarness();h.context.window.__eesNativeDraftV1.persistent=false;await assert.rejects(h.open(),/대화 입력창을 준비/);assert.equal(h.navigation.length,0);assert.equal(h.restores.length,0);
});
test('pending Native navigation cannot cross an account or work context change',async()=>{
 for(const change of ['account','scope','route']){const h=nativeNavigationHarness(),pending=deferred();h.context.window.__eesNativeDraftV1.flush=()=>pending.promise;const moving=h.open();if(change==='account')h.setAuth('actor-b');else if(change==='scope')h.api.setSelection({system_id:'OTHER'});else h.context.location.pathname='/c/other';pending.resolve(true);await moving;assert.equal(h.navigation.length,0);assert.equal(h.restores.length,0);}
});
test('account reset releases an old pending Native flush without unlocking the new account operation',async()=>{
 const h=nativeNavigationHarness(),oldFlush=deferred(),newFlush=deferred();let flushing=0;
 h.context.window.__eesNativeDraftV1.flush=()=>{flushing++;return flushing===1?oldFlush.promise:newFlush.promise;};
 const old=h.api.handleClick({dataset:{action:'native_open',nativeId:'skills'}});h.setAuth('actor-b-token');h.api.reset();h.api.setIdentity();h.api.setState({...h.state,capabilities:{...h.state.capabilities,actor_id:'b'}});
 const next=h.api.handleClick({dataset:{action:'native_open',nativeId:'models'}});assert.equal(flushing,2);
 oldFlush.resolve(true);await old;await assert.rejects(h.api.handleClick({dataset:{action:'native_open',nativeId:'skills'}}),/저장 또는 화면 준비/);
 newFlush.resolve(true);await next;assert.deepEqual(h.navigation,['/workspace/models']);
});
test('removed native_return action cannot navigate or alter the saved selection',async()=>{
 const h=nativeNavigationHarness();await h.open();const before=JSON.parse(JSON.stringify(h.api.snapshot().selection));await h.api.handleClick({dataset:{action:'native_return'}});assert.deepEqual(h.navigation,['/workspace/skills']);assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),before);assert.equal(h.restores.length,0);
});
test('chat history menu publishes its own selection and never opens the separate search dialog',async()=>{
 const h=nativeNavigationHarness();let searches=0;h.context.window.__eesSourceShellV1.searchChats=()=>searches++;const before=JSON.parse(JSON.stringify(h.readDraft()));
 await h.api.sourceAction({action:'chats'});assert.equal(h.api.snapshot().selection.tab,'chats');assert.equal(h.api.snapshot().selection.mode,'work');assert.equal(searches,0);assert.deepEqual(h.readDraft(),before);assert.equal(h.navigation.length,0);
});
test('Native tickets cannot copy drafts across unrelated navigation logout actor or session changes',async()=>{
 for(const boundary of ['chat','unrelated','logout','actor','session']){const h=nativeNavigationHarness();await h.open();if(boundary==='chat')h.context.location.pathname='/c/other';if(boundary==='unrelated')h.context.location.pathname='/notes';if(boundary==='logout')h.context.location.pathname='/auth';if(boundary==='actor')h.api.setState({...h.state,capabilities:{...h.state.capabilities,actor_id:'b'}});if(boundary==='session')h.setAuth('actor-b-token');h.api.sync();await h.api.handleClick({dataset:{action:'native_return'}});assert.equal(h.navigation.length,1,boundary);assert.equal(h.restores.length,0,boundary);}
});
test('Browser Back preserves the exact live draft without importing a snapshot',async()=>{
 const h=nativeNavigationHarness(),before=JSON.parse(JSON.stringify(h.api.snapshot().selection)),draft=JSON.parse(JSON.stringify(h.readDraft()));await h.open();h.context.location.pathname='/c/original';h.context.location.search='?keep=1';h.api.sync();await new Promise(setImmediate);assert.deepEqual(h.navigation,['/workspace/skills']);assert.deepEqual(h.readDraft(),draft);assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),before);assert.equal(h.restores.length,0);
});
test('Native-to-Native menu navigation keeps the persistent Chat across all destinations',async()=>{
 const h=nativeNavigationHarness(),draft=JSON.parse(JSON.stringify(h.readDraft()));let flushes=0;h.context.window.__eesNativeDraftV1.flush=()=>{flushes++;return true;};await h.open('skills');h.setReady(false);await h.open('models');await h.open('knowledge');await h.open('prompts');assert.equal(flushes,1);assert.deepEqual(h.navigation,['/workspace/skills','/workspace/models','/workspace/knowledge','/workspace/prompts']);h.setReady(true);await h.back();assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);
});
test('same-section tools menu restores its exact authoring selection without closing the draft',async()=>{
 const h=nativeNavigationHarness();h.api.setSelection({mode:'author',tab:'tools',workflow_id:'',job_id:'',run_id:''});const before=JSON.parse(JSON.stringify(h.api.snapshot().selection));let closed=0;h.designer.closeStart=()=>closed++;await h.open();await h.back('tools');assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),before);assert.equal(closed,0);
});
test('a different EES menu destination is applied only after returning to the original chat',async()=>{
 for(const [action,extra,mode,tab] of [['mode',{mode:'work'},'work','my_work'],['tools',{},'author','tools']]){const h=nativeNavigationHarness(),draft=JSON.parse(JSON.stringify(h.readDraft()));await h.open();await h.back(action,extra);assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.equal(h.api.snapshot().selection.mode,mode);assert.equal(h.api.snapshot().selection.tab,tab);assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);}
});
test('Native return keeps the workspace visible but publishes a reference only after validation and Chat readiness',async()=>{
 for(const first of ['state','draft']){
  const h=nativeNavigationHarness(),stateRead=deferred(),draftRestore=deferred(),draft=JSON.parse(JSON.stringify(h.readDraft())),complete={...h.state,workflow:{id:'w',revision:7,published_version:3}};
  h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(h.context.location.pathname.startsWith('/workspace')?{ok:true,...h.state,workflow:null,run:null}:stateRead.promise):{ok:true});
  await h.open();const before=h.renders.length;
  h.setReady(false);
  await h.back();
  const assertWaiting=()=>{assert.equal(h.context.window.__eesNativeWorkV1.captureReference().kind,'none');assert.ok(h.renders.slice(before).filter(value=>!value.native_shell).every(value=>value.state?.capabilities.actor_id==='a'));};
  assertWaiting();
  if(first==='state')stateRead.resolve({ok:true,...complete});else {h.setReady(true);h.api.sync();}
  await new Promise(setImmediate);assertWaiting();
  if(first==='state'){h.setReady(true);h.api.sync();}else stateRead.resolve({ok:true,...complete});
  await new Promise(setImmediate);
  assert.deepEqual(h.readDraft(),draft);assert.equal(h.renders.at(-1).native_shell,false);assert.equal(h.renders.at(-1).state.workflow.revision,7);
  const reference=h.context.window.__eesNativeWorkV1.captureReference();assert.equal(reference.kind,'workspace');assert.equal(reference.revision,7);assert.equal(reference.version,3);
 }
});
test('a queued EES menu destination is visible immediately while its reference waits for full state',async()=>{
 const h=nativeNavigationHarness(),stateRead=deferred(),draft=JSON.parse(JSON.stringify(h.readDraft()));
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(h.context.location.pathname.startsWith('/workspace')?{ok:true,...h.state}:stateRead.promise):{ok:true});
 await h.open();await h.back('tools');assert.deepEqual(h.readDraft(),draft);assert.equal(h.api.snapshot().selection.tab,'tools');assert.equal(h.api.snapshot().selection.workflow_id,'');assert.equal(h.context.window.__eesNativeWorkV1.captureReference().kind,'none');
 stateRead.resolve({ok:true,...h.state});await new Promise(setImmediate);assert.equal(h.api.snapshot().selection.tab,'tools');assert.equal(h.api.snapshot().selection.workflow_id,'');
});
test('transient full state failure after Native return keeps the workspace and error without a work reference',async()=>{
 for(const delayedDraft of [false,true]){
  const h=nativeNavigationHarness(),draftRestore=deferred();h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(h.context.location.pathname.startsWith('/workspace')?{ok:true,...h.state}:{httpError:true,status:503,error:{message:'업무 조회 실패'}}):{ok:true});
  await h.open();if(delayedDraft)h.setReady(false);
  await h.back();h.setReady(true);h.api.sync();await new Promise(setImmediate);assert.equal(h.api.snapshot().state.capabilities.actor_id,'a');assert.match(h.api.snapshot().error,/업무 조회 실패/);assert.equal(h.context.window.__eesNativeWorkV1.captureReference().kind,'none');assert.equal(h.renders.at(-1).native_shell,false);assert.match(h.renders.at(-1).error,/업무 조회 실패/);
 }
});
test('explicit retry after a failed return finishes its ticket without a DOM observer lifecycle tick',async()=>{
 const h=nativeNavigationHarness();let fail=true;h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(h.context.location.pathname.startsWith('/workspace')?{ok:true,...h.state}:fail?{httpError:true,status:503,error:{message:'업무 조회 실패'}}:{ok:true,...h.state,workflow:{id:'w',revision:9,published_version:2}}):{ok:true});
 await h.open();h.setReady(false);await h.back();assert.equal(h.api.snapshot().state.capabilities.actor_id,'a');assert.equal(h.context.window.__eesNativeWorkV1.captureReference().kind,'none');
 h.setReady(true);fail=false;await h.api.handleClick({dataset:{action:'refresh'}});await new Promise(setImmediate);
 assert.equal(h.renders.at(-1).state.workflow.revision,9);assert.equal(h.context.window.__eesNativeWorkV1.captureReference().revision,9);assert.equal(h.restores.length,0);
});
test('direct Native entry loads capabilities with no chat pane and EES destinations use the chat root',async()=>{
 const h=nativeNavigationHarness(nativeCapabilities({can_author:true,native_access:{skills:true}}));h.context.location.pathname='/workspace/skills';h.context.location.search='';h.setReady(false);h.api.setState(null);h.api.sync();await new Promise(setImmediate);assert.ok(h.calls.some(call=>call.url.startsWith('/api/ees-work/workspace?')));assert.equal(h.renders.at(-1)?.native_shell,true);assert.equal(h.renders.at(-1)?.native_id,'skills');assert.equal(h.calls.some(call=>call.url.startsWith('/api/ees-work/operations?')),false);await h.api.handleClick({dataset:{action:'native_open',nativeId:'models'}});assert.equal(h.navigation.length,0);await h.back('tools');assert.equal(h.navigation.at(-1),'/');assert.equal(h.api.snapshot().selection.mode,'author');assert.equal(h.api.snapshot().selection.tab,'tools');assert.equal(h.restores.length,0);
});
test('a failed Native capability read hides actions but keeps the original draft until explicit same-actor retry',async()=>{
 const h=nativeNavigationHarness(),draft=JSON.parse(JSON.stringify(h.readDraft())),before=JSON.parse(JSON.stringify(h.api.snapshot().selection));let failed=true;
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(failed?{httpError:true,status:503,error:{message:'권한 조회 실패'}}:{ok:true,...h.state}):{ok:true});
 await h.open();h.api.sync();await new Promise(setImmediate);assert.equal(h.api.snapshot().state.capabilities.actor_id,'a');assert.deepEqual(Object.keys(h.api.snapshot().native_capabilities),[]);assert.match(h.api.snapshot().error,/권한 조회 실패/);
 const menu=html('workWorkspaceMenuHTML({}, {}, error)',{error:h.api.snapshot().error});assert.match(menu,/data-action="refresh">다시 확인/);assert.doesNotMatch(menu,/data-action="(?:native_open|procedures|tools|workspace_admin)"/);
 await h.back('procedures');await h.open('models');assert.deepEqual(h.navigation,['/workspace/skills']);assert.equal(h.restores.length,0);assert.deepEqual(h.readDraft(),draft);
 failed=false;await h.back('refresh');assert.deepEqual(h.navigation,['/workspace/skills']);assert.equal(h.api.snapshot().state.capabilities.actor_id,'a');assert.equal(h.api.snapshot().error,'');assert.ok(h.calls.filter(call=>call.url.startsWith('/api/ees-work/workspace?')).every(call=>call.url==='/api/ees-work/workspace?'),'Native capability reads exclude stale EES scope and run identifiers');
 await h.back();assert.deepEqual(h.navigation,['/workspace/skills','/c/original?keep=1']);assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);assert.deepEqual(JSON.parse(JSON.stringify(h.api.snapshot().selection)),before);
});
test('retry after a failed Native capability read never revives another actor or session return ticket',async()=>{
 for(const boundary of ['actor','session']){
  const h=nativeNavigationHarness();h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{httpError:true,status:503,error:{message:'권한 조회 실패'}}:{ok:true});await h.open();h.api.sync();await new Promise(setImmediate);assert.equal(h.api.snapshot().state.capabilities.actor_id,'a');assert.deepEqual(Object.keys(h.api.snapshot().native_capabilities),[]);
  if(boundary==='session')h.setAuth('actor-b-token');const next={...h.state,capabilities:{...h.state.capabilities,actor_id:'b'}};h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,...next}:{ok:true});await h.back('refresh');h.api.sync();await new Promise(setImmediate);assert.equal(h.api.snapshot().native_capabilities.actor_id,'b');assert.equal(h.api.snapshot().state,null);h.setDraft({prompt:'새 계정의 입력',files:[]});await h.back();assert.equal(h.navigation.at(-1),'/');assert.equal(h.navigation.includes('/c/original?keep=1'),false,boundary);assert.equal(h.restores.length,0,boundary);assert.equal(h.readDraft().prompt,'새 계정의 입력');
 }
});
test('source availability is independent of Native sidebar and chat DOM anchors',async()=>{
 const h=nativeNavigationHarness();h.context.location.pathname='/workspace/skills';h.context.location.search='';h.context.document.querySelector=()=>null;h.api.sync();await new Promise(setImmediate);assert.equal(h.calls.length,1);assert.equal(h.renders.at(-1)?.native_shell,true);assert.equal(h.navigation.length,0);
 h.sourceState.active=false;h.calls.length=0;h.api.sync();await new Promise(setImmediate);assert.equal(h.calls.length,0);
});
test('source admin state stays inside the shell and explicit close preserves original chat',async()=>{
 const h=nativeNavigationHarness();let closed=0;h.context.window.__eesSourceShellV1.closeSettings=()=>{h.sourceState.admin=false;closed++;};
 await h.open('admin');h.context.location.pathname='/';h.context.location.search='';h.sourceState.admin=true;h.api.sync();await new Promise(setImmediate);assert.equal(h.renders.at(-1)?.native_shell,true);assert.equal(h.restores.length,0);await h.back();assert.equal(closed,1);assert.deepEqual(h.navigation,['/admin/settings','/c/original?keep=1']);
});
test('source admin close returns to saved chat without inspecting Native modal nodes',async()=>{
 const h=nativeNavigationHarness();await h.open('admin');h.context.location.pathname='/';h.context.location.search='';h.sourceState.admin=true;h.api.sync();await new Promise(setImmediate);h.sourceState.admin=false;h.api.sync();await new Promise(setImmediate);assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);
});
test('source admin session may keep its Native personal tab open until explicitly closed',async()=>{
 const h=nativeNavigationHarness(),draft=JSON.parse(JSON.stringify(h.readDraft()));await h.open('admin');h.context.location.pathname='/';h.context.location.search='';h.sourceState.admin=true;h.api.sync();await new Promise(setImmediate);
 // The owning source component keeps the admin session across its modal tabs.
 h.api.sync();await new Promise(setImmediate);assert.deepEqual(h.navigation,['/admin/settings']);assert.equal(h.renders.at(-1)?.native_id,'admin');assert.deepEqual(h.readDraft(),draft);
 h.sourceState.admin=false;h.api.sync();await new Promise(setImmediate);assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.equal(h.restores.length,0);
});
test('ordinary source settings do not claim admin state or inspect Native modal markup',async()=>{
 const h=nativeNavigationHarness();h.context.document.querySelector=()=>{throw new Error('Native DOM inspection is forbidden');};h.sourceState.admin=false;h.api.sync();await new Promise(setImmediate);assert.equal(h.renders.at(-1)?.native_shell,false);
});
test('persistent source Chat keeps live images and uploads through Native without reimport',async()=>{
 const h=nativeNavigationHarness();h.context.window.__eesNativeDraftV1.persistent=true;h.context.window.__eesNativeDraftV1.attachmentState=()=>({images:true,uploading:true});const live={prompt:'미전송 이미지',files:[{id:'image',type:'image',status:'uploading'}]};h.setDraft(live);await h.open();await h.back();assert.equal(h.restores.length,0);assert.equal(h.readDraft(),live);assert.deepEqual(h.navigation,['/workspace/skills','/c/original?keep=1']);
});
test('runtime owns only supplied slots and registers no document-wide event hooks or observer',()=>{
 const {launcherSource,viewSource}=require('./ees_workspace_ui_fixture.cjs');assert.doesNotMatch(launcherSource,/MutationObserver|document\.addEventListener|sidebar-search-button|sidebar-new-chat-button|settings-tabs-container/);assert.doesNotMatch(viewSource,/MutationObserver|document\.addEventListener|insertAdjacentElement|pane\.parentElement|anchor\.parentElement/);
});

test('source help context is available outside work references and fails closed until chat is ready',()=>{
 const h=controller();h.api.setSelection({mode:'work',workflow_id:'',system_id:''});
 const bridge=h.context.window.__eesNativeWorkV1;assert.equal(bridge.captureReference().kind,'none');assert.deepEqual(JSON.parse(JSON.stringify(bridge.helpContext())),{context_id:h.api.context(),system_id:''});
 const captured=bridge.helpContext();h.api.setSelection({system_id:'EMS'});assert.equal(bridge.helpContext().system_id,'EMS');assert.notEqual(bridge.helpContext().context_id,captured.context_id);assert.equal(captured.system_id,'');
 h.sourceState.chatReady=false;assert.equal(bridge.helpContext(),null);h.sourceState.chatReady=true;h.context.location.pathname='/workspace/skills';assert.equal(bridge.helpContext(),null);
});
test('help question contains only visible question text and keeps context outside its content',()=>{
 const question=html('workUI.helpQuestion(term,context)',{term:{id:'read_tool',name:'정보 읽기'},context:{screen:'정보 읽기 도구',draftName:'점검 조회',kind:'read',secret:'not-visible'}});
 assert.equal(question,'EES Workflow 도움말 ‘정보 읽기’의 뜻과 지금 화면에서 쓰는 방법을 알려줘.');assert.doesNotMatch(question,/read_tool|현재 화면|점검 조회|not-visible/);
});
test('help sends through source once with a frozen reference and never reads or changes the composer',async()=>{
 const h=controller(),original={prompt:'이미 작성한 <검토> & "질문"\n둘째 줄',files:[{id:'upload-1',type:'image',status:'uploading'}],selectedToolIds:['tool-owned'],selectedModels:['model-a'],params:{temperature:.1}},kept=JSON.stringify(original),sent=[];
 h.context.window.__eesNativeDraftV1={read(){throw Error('must not read draft');},restore(){throw Error('must not replace draft');}};
 h.context.window.__eesSourceShellV1.askHelp=async payload=>{sent.push(payload);return {accepted:true};};h.api.setSelection({system_id:'EMS'});
 assert.equal(await h.designer.callbacks.askHelp('뜻을 알려줘 <그대로>',{screen:'도구 작성',term_id:'read_tool',draftName:'점검 조회',secret:'not-visible'}),true);
 assert.equal(sent.length,1);assert.equal(sent[0].question,'뜻을 알려줘 <그대로>');assert.deepEqual(JSON.parse(JSON.stringify(sent[0].reference)),{kind:'help',system_id:'EMS',context_id:h.api.context(),screen:'도구 작성',term_id:'read_tool',title:'점검 조회'});assert.equal(Object.isFrozen(sent[0].reference),true);assert.equal(JSON.stringify(original),kept);assert.equal(h.calls.length,0);
});
test('help refuses missing source or unready chat without a fallback send or composer mutation',async()=>{
 const h=controller();let sends=0;await assert.rejects(h.designer.callbacks.askHelp('질문'),/업무 도우미 연결/);
 h.context.window.__eesSourceShellV1.askHelp=async()=>{sends++;return {accepted:true};};h.sourceState.chatReady=false;
 await assert.rejects(h.designer.callbacks.askHelp('질문'),/업무 도우미 연결/);h.sourceState.chatReady=true;
 await assert.rejects(h.designer.callbacks.askHelp('질문',{screen:'x'.repeat(201)}),/참고 정보/);assert.equal(sends,0);assert.equal(h.calls.length,0);
});
test('help prevents duplicate requests through preflight and the full Native response then reports no-send failure',async()=>{
 const h=controller(),pending=deferred();let calls=0,busy=false;
 h.context.window.__eesSourceShellV1.helpState=()=>({busy});h.context.window.__eesSourceShellV1.askHelp=()=>{calls++;return pending.promise;};
 const first=h.designer.callbacks.askHelp('첫 질문');await assert.rejects(h.designer.callbacks.askHelp('둘째 질문'),/앞선 답변/);
 pending.resolve({accepted:true});busy=true;assert.equal(await first,true);await assert.rejects(h.designer.callbacks.askHelp('셋째 질문'),/앞선 답변/);assert.equal(calls,1);
 busy=false;h.context.window.__eesSourceShellV1.askHelp=async()=>({accepted:false,code:'help_unavailable',message:'도우미 권한을 확인해 주세요.'});
 assert.equal(await h.designer.callbacks.askHelp('다시 질문'),false);assert.equal(h.api.snapshot().error,'');assert.equal(h.calls.length,0);
});
test('help rejects an account change before dispatch and never copies a private draft to another actor',async()=>{
 const h=controller();let sends=0;h.context.window.__eesSourceShellV1.helpState=()=>{h.setAuth('actor-b-token');return {busy:false};};h.context.window.__eesSourceShellV1.askHelp=async()=>{sends++;return {accepted:true};};
 assert.equal(await h.designer.callbacks.askHelp('질문'),false);assert.equal(sends,0);
});
test('late help acceptance cannot focus or repaint another conversation and retains its submitted reference',async()=>{
 const h=controller(),pending=deferred();let payload,focused=0;h.context.window.__eesSourceShellV1.focusComposer=()=>focused++;
 h.context.window.__eesSourceShellV1.askHelp=body=>{payload=body;return pending.promise;};h.api.setSelection({system_id:'EMS'});const before=h.api.context();
 const sending=h.designer.callbacks.askHelp('질문',{screen:'새 절차',title:'원래 초안'});h.context.location.pathname='/c/other';h.api.setSelection({system_id:'OTHER'});pending.resolve({accepted:true});
 assert.equal(await sending,false);assert.equal(payload.reference.context_id,before);assert.equal(payload.reference.system_id,'EMS');assert.equal(payload.reference.title,'원래 초안');assert.equal(focused,0);assert.equal(h.calls.length,0);
});
test('author tools expose help-only metadata while workflow and historical references remain unchanged',()=>{
 const h=controller();h.api.setSelection({mode:'author',tab:'tools',system_id:'EMS',workflow_id:'old-work',run_id:'old-run'});
 const help=h.api.reference();assert.equal(help.kind,'help');assert.equal(help.system_id,'EMS');assert.ok(help.context_id);assert.equal(Object.hasOwn(help,'workflow_id'),false);assert.equal(Object.hasOwn(help,'run_id'),false);
 h.api.setSelection({tab:'overview'});assert.equal(h.api.reference().kind,'none');h.api.setState({capabilities:{actor_id:'a'},workflow:{id:'old-work',revision:7},run:{id:'old-run',workflow_id:'old-work',revision:11,version:3}});assert.equal(h.api.reference().kind,'workspace');assert.equal(h.api.reference().workflow_id,'old-work');assert.equal(h.api.reference().revision,11);
 h.api.setSelection({mode:'work',chat_reference:{kind:'workspace',reference_kind:'historical',workflow_id:'old-work',run_id:'old-run',attempt_id:'kept'}});h.api.setState({run:{id:'old-run'}});assert.equal(h.api.reference().attempt_id,'kept');
});

test('procedure starter questions send visible text with separate help metadata until the starter closes',async()=>{
 const h=controller();let sent,active={screen:'새 업무 절차',draftName:'시험 공장 절차',templateId:'factory_rollout'},synced;
 h.designer.readStartContext=()=>active;h.view.sync=value=>{synced=value;};h.api.setState({capabilities:{actor_id:'a'},workflow:{id:'existing-work',revision:1},run:{id:'existing-run',workflow_id:'existing-work',revision:1}});h.api.setSelection({mode:'author',tab:'overview',system_id:'EMS',workflow_id:'existing-work',run_id:'existing-run'});
 h.designer.callbacks.startContextChanged(active);assert.equal(synced.procedure_start.draftName,'시험 공장 절차');
 h.context.window.__eesSourceShellV1.askHelp=async value=>{sent=value;return {accepted:true};};
 const reference=h.api.reference();assert.equal(reference.kind,'help');assert.equal(Object.hasOwn(reference,'workflow_id'),false);
 await h.api.handleClick({dataset:{action:'procedure_question',questionIndex:'0'}});
 assert.equal(sent.question,'신규 공장 횡전개 예시를 복사해서 우리 공장에 맞게 고치고 싶어');assert.equal(sent.reference.title,'시험 공장 절차');assert.equal(sent.reference.screen,'새 업무 절차');assert.equal(sent.reference.kind,'help');assert.equal(Object.hasOwn(sent.reference,'workflow_id'),false);assert.equal(h.calls.length,0);
 active=null;h.designer.callbacks.startContextChanged(null);assert.equal(synced.procedure_start,null);assert.equal(h.api.reference().kind,'workspace');assert.equal(h.api.reference().workflow_id,'existing-work');
 sent=null;await h.api.handleClick({dataset:{action:'procedure_question',questionIndex:'1'}});assert.equal(sent,null);
});
test('procedure question sends the visible translation unchanged while preserving index and length guards',async()=>{
 const h=controller(),sent=[];h.designer.readStartContext=()=>({screen:'New procedure',draftName:'Factory guide'});h.api.setSelection({mode:'author',tab:'overview',system_id:'EMS'});
 h.context.window.__eesSourceShellV1.askHelp=async value=>{sent.push(value);return {accepted:true};};
 const question='What should I decide first when starting a blank procedure?';
 await h.api.handleClick({dataset:{action:'procedure_question',questionIndex:'2',question}});
 assert.equal(sent.length,1);assert.equal(sent[0].question,question);assert.equal(sent[0].reference.title,'Factory guide');assert.equal(sent[0].reference.screen,'New procedure');
 for(const questionIndex of ['-1','3','NaN'])await h.api.handleClick({dataset:{action:'procedure_question',questionIndex,question}});
 await assert.rejects(h.api.handleClick({dataset:{action:'procedure_question',questionIndex:'2',question:'x'.repeat(8001)}}),/질문을 확인/);assert.equal(sent.length,1);
});
test('procedure question choices reject unavailable or invalid context without dispatch',async()=>{
 const h=controller();let sends=0;h.designer.readStartContext=()=>({screen:'새 업무 절차'});h.api.setSelection({mode:'author',tab:'overview'});
 h.context.window.__eesSourceShellV1.askHelp=async()=>{sends++;return {accepted:true};};
 for(const questionIndex of ['-1','3','NaN'])await h.api.handleClick({dataset:{action:'procedure_question',questionIndex}});
 h.api.setSelection({mode:'work'});await h.api.handleClick({dataset:{action:'procedure_question',questionIndex:'0'}});assert.equal(sends,0);assert.equal(h.calls.length,0);
});
test('runtime keeps the three approved questions and has no old right-side introduction or fill-only copy',()=>{
 const {viewSource,launcherSource}=require('./ees_workspace_ui_fixture.cjs');assert.doesNotMatch(viewSource,/function workProcedureStartHTML|질문을 입력창에 채웁니다/);assert.doesNotMatch(launcherSource,/bridge\.restore|draft\.prompt/);
 const questions=html('workUI.procedureQuestions');assert.equal(questions.length,3);assert.equal(questions[2],'빈 절차로 시작하면 무엇부터 정하나요?');
});

test('input save keeps mutation controls busy until the acknowledged state finishes refreshing',async()=>{
 const h=controller(),pending=deferred(),reading=deferred(),busy=[];let dialogs=0,acknowledgements=0;
 h.api.setSelection({run_id:'r',job_id:'j'});h.api.setState({run:{id:'r',revision:1,definition:{nodes:{j:{mode:'human'}}},jobs:{j:{}}}});
 h.view.setBusy=value=>busy.push(value);h.view.readInputs=()=>({inputs:{note:'new'},revision:1,key:'r/j',serial:1});h.view.clearInputs=()=>acknowledgements++;
 h.setDialog(()=>{dialogs++;return Promise.resolve(false);});
 h.setReply(call=>call.body?.action==='save_inputs'?{ok:true,revision:2}:call.url.startsWith('/api/ees-work/workspace?')?(reading.resolve(),pending.promise):{ok:true});
 const saving=h.api.handleClick({dataset:{action:'save_inputs'}});await reading.promise;
 assert.equal(acknowledgements,1);assert.equal(busy.at(-1),true);await h.api.handleClick({dataset:{action:'confirm'}});assert.equal(dialogs,0);
 pending.resolve({ok:true,systems:[],workflows:[],runs:[],run:{id:'r',revision:2,inputs:{note:'new'},jobs:{j:{}}}});await saving;
 assert.equal(busy.at(-1),false);assert.equal(h.api.snapshot().state.run.revision,2);
});
test('review save cannot continue confirmation after its refresh loses the selected work context',async()=>{
 const h=controller(),pending=deferred(),reading=deferred();let dialogs=0;
 h.api.setSelection({run_id:'r',job_id:'j'});h.api.setState({run:{id:'r',revision:1,definition:{nodes:{j:{mode:'ai',result_block:'ai_review'}}},jobs:{j:{attempt_id:'a'}}}});
 h.view.readReview=()=>({dirty:true,inputs:{text:'edited'},attempt_id:'a',result_revision:1,revision:0,key:'r/j',serial:1});h.view.clearReview=()=>{};
 h.setDialog(()=>{dialogs++;return Promise.resolve(false);});
 h.setReply(call=>call.body?.action==='save_review_draft'?{ok:true,run:{jobs:{j:{review_draft:{revision:1,text:'edited'}}}}}:call.url.startsWith('/api/ees-work/workspace?')?(reading.resolve(),pending.promise):{ok:true});
 const confirming=h.api.handleClick({dataset:{action:'confirm'}});await reading.promise;h.api.setSelection({job_id:'other'});
 pending.resolve({ok:true,run:{id:'r',revision:2,jobs:{j:{}}}});await confirming;assert.equal(dialogs,0);
});
test('an explicit early navigation survives initial saved-selection restoration and late startup reads',async()=>{
 const h=controller(),startup=deferred();h.api.setRestored(false);let reads=0;
 const saved={ok:true,systems:['EMS'],workflows:[],runs:[],my_work:[],ui_state:{revision:5,state:{selection:{mode:'work',tab:'current',workflow_id:'old-work',run_id:'old-run',job_id:'old-job',system_id:'EMS'}}}};
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(++reads===1?startup.promise:saved):{ok:true});
 const first=h.api.refresh();await h.api.handleClick({dataset:{action:'my_work'}});startup.resolve(saved);await first;
 assert.equal(h.api.snapshot().selection.tab,'my_work');assert.equal(h.api.snapshot().selection.job_id,'');assert.equal(h.api.snapshot().selection.system_id,'EMS');
});
test('early selection patches are cleared on account reset and do not replace another account restoration',async()=>{
 const h=controller();h.api.setRestored(false);await h.api.select({system_id:'CHOICE',tab:'records'},{fetch:false});
 h.api.reset();h.setAuth('account-b');h.api.setIdentity();
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,systems:['OTHER'],workflows:[],runs:[],ui_state:{revision:8,state:{selection:{system_id:'OTHER',tab:'overview',workflow_id:'allowed-b'}}}}:{ok:true});
 await h.api.refresh();assert.equal(h.api.snapshot().selection.system_id,'OTHER');assert.equal(h.api.snapshot().selection.tab,'overview');assert.equal(h.api.snapshot().selection.workflow_id,'allowed-b');
});
test('history expansion restoration uses exact attempt keys and the current panel position',()=>{
 const details=[{dataset:{key:'history-old'},open:false},{dataset:{key:'history-other'},open:true}],content={scrollTop:0};
 const host={querySelectorAll:selector=>{assert.equal(selector,'details[data-key]');return details;},querySelector:selector=>{assert.equal(selector,'#ees-work-content');return content;}};
 html('workRestorePanelPosition(host,position)',{host,position:{expanded:['history-old','history-missing'],scroll:180}});
 assert.equal(details[0].open,true);assert.equal(details[1].open,false);assert.equal(content.scrollTop,180);
 html('workRestorePanelPosition(host,null)',{host});assert.equal(details[0].open,true);
 const out=html('workHistoryHTML(run)',{run:{attempts:[{id:'old',number:1},{id:'other',number:2}]}});
 assert.match(out,/data-key="history-old"/);assert.match(out,/data-key="history-other"/);
});
test('real view list reader returns an isolated snapshot without an undefined helper',()=>{
 const snapshot={state:{run:{id:'r',jobs:{j:{attempt_id:'a',result:{items:[{id:'one',selected:true}]}}}}},selection:{job_id:'j'}};
 const context=renderer({snapshot});run(context,'var view=createWorkView({callbacks:{}});view.sync(snapshot)');
 const first=run(context,'view.readList()');assert.equal(first.items[0].id,'one');first.items[0].selected=false;
 assert.equal(run(context,'view.readList().items[0].selected'),true);
});
test('assignment labels use only the permitted Native people list and preserve principal kind',()=>{
 const node={assignee:{kind:'group',id:'same'}},saved={claim_actor:'same'},people=[{label:'허용된 그룹',value:{kind:'group',id:'same'}}];
 const out=html('workAssignmentHTML(node,saved,people)',{node,saved,people});assert.match(out,/배정된 그룹 · 허용된 그룹/);assert.match(out,/현재 담당 · 이름 확인 필요/);assert.doesNotMatch(out,/same/);
 assert.match(html('workAssignmentHTML(node,saved,people)',{node:{assignee:{kind:'user',id:'unknown-id'}},saved:{},people}),/이름 확인 필요/);
});
test('new delivery effect and retry failures are translated without masking human explanations',()=>{
 for(const code of ['delivery_unconfigured','effect_criterion_not_met','effect_observation_unknown','read_retry_deadline','read_retry_source_changed','zero_selection_policy_required'])assert.notEqual(html('workReasonText(code)',{code}),code);
 assert.equal(html('workReasonText("담당자가 근거를 다시 확인합니다")'),'담당자가 근거를 다시 확인합니다');
 const out=html('workRequestHTML(request)',{request:{state:'failed',reported_complete:true,effect_verified:false,reason:'effect_criterion_not_met'}});assert.doesNotMatch(out,/effect_criterion_not_met/);assert.match(out,/효과 확인 실패/);
});
test('list inclusion is a local preview and candidates are never selected by default',()=>{
 const result={items:[{id:'CR-1',title:'actual'}],suggestions:[{id:'CR-2',title:'candidate',reason:'review required'}]};
 const items=html('workListItems(result)',{result});assert.equal(items[0].selected,true);assert.equal(items[1].selected,false);
 const out=html('workListHTML(saved)',{saved:{result}});assert.match(out,/data-list-include/);assert.match(out,/목록 확정 \(1건\)/);assert.match(out,/확인 후보 · 미확정/);
 assert.doesNotMatch(out,/data-item-id="CR-2"[^>]* checked/);
});
test('saved human additions retain their source label and never increase the immutable lookup count',()=>{
 const original={id:'original',job_id:'j',result:{items:[{id:'CR-1'},{id:'CR-2'}]}},amended={id:'amended',job_id:'j',result:{amendment:{previous_attempt:'original'},items:[{id:'CR-1'},{id:'MANUAL',source:{kind:'human_added'}}]}};
 const current=html('workListSourceAttempt(run,"amended")',{run:{attempts:[original,amended]}});assert.equal(current.id,'original');assert.equal(current.result.items.length,2);
 const out=html('workListHTML(saved,{sourceCount:2})',{saved:{result:amended.result,decisions:{'CR-1':{verdict:'completed'}}}});
 assert.match(out,/조회 2건/);assert.match(out,/포함 2 · 추가 1 · 제외 0/);assert.match(out,/사람이 추가 · 원본 조회 확인 전/);
 assert.equal(html('workListSourceAttempt(run,"amended")',{run:{attempts:[amended]}}),null);
 assert.equal(html('workListSourceAttempt(run,"amended")',{run:{attempts:[{...original,evidence_access:'requires_current_source_access'},amended]}}),null);
 assert.match(html('workListHTML(saved,{sourceCount:null})',{saved:{result:amended.result}}),/원본 조회 건수 확인 필요/);
});
test('failed lookup hides previous payload while partial keeps explicit incompleteness',()=>{
 const saved={status:'failed',result:{items:[{id:'private-old',name:'old value'}]}};
 const out=html('workListHTML(saved)',{saved});assert.doesNotMatch(out,/private-old|old value/);assert.match(out,/이전 결과는 보여주지 않습니다/);
 assert.match(html('workListHTML(saved)',{saved:{...saved,status:'partial'}}),/부분 결과 · 미확인/);
});
test('zero included items can be saved while completion policy remains explicitly unresolved',()=>{
 const out=html('workListHTML(saved)',{saved:{result:{items:[{id:'CR-1',selected:false}]}}});
 assert.match(out,/data-action="save_list_selection" data-mutation class="ew-secondary"/);assert.match(out,/data-action="confirm_list"[^>]* disabled/);assert.match(out,/완료 정책이 정해지지 않았습니다/);
});
test('a completed empty lookup permits explicit additions without pretending it was never executed',()=>{
 const out=html('workListHTML(saved)',{saved:{attempt_id:'empty',status:'awaiting_confirmation',result:{items:[],completeness:'complete'}}});
 assert.match(out,/조회 0건/);assert.match(out,/data-action="add_list_item"/);assert.match(out,/data-action="save_list_selection"/);assert.match(out,/data-action="confirm_list"[^>]* disabled/);assert.doesNotMatch(out,/아직 저장된 결과/);
 assert.match(html('workListHTML({})'),/아직 저장된 결과/);assert.doesNotMatch(html('workListHTML(saved)',{saved:{status:'failed',result:{items:[]}}}),/add_list_item|조회 0건/);
});
test('read-only report cannot edit or save and unavailable dispatch is never clickable',()=>{
 const saved={attempt_id:'a',result:{text:'original'},review_draft:{text:'human draft',revision:2}};
 const editable=html('workReviewDraftHTML({completion:{kind:"delivery"}},saved)',{saved});assert.match(editable,/human draft/);assert.match(editable,/data-action="send_review_draft" disabled/);
 const readonly=html('workReviewDraftHTML({},saved,{readOnly:true})',{saved});assert.match(readonly,/<textarea[^>]* readonly/);assert.doesNotMatch(readonly,/data-action="save_review_draft"/);
 const confirmed=html('workReviewDraftHTML({},saved)',{saved:{...saved,decisions:{job:{verdict:'completed'}}}});assert.doesNotMatch(confirmed,/data-action="save_review_draft"/);
});
test('revoked evidence never redisplays a locally preserved list or review draft',()=>{
 const saved={evidence_access:'requires_current_source_access'},listDraft={items:[{id:'private-item',name:'private-list',selected:true}]},reviewDraft={inputs:{text:'private-review'}};
 assert.doesNotMatch(html('workListHTML(saved,{listDraft})',{saved,listDraft}),/private-list|private-item|data-list-include/);
 assert.doesNotMatch(html('workReviewDraftHTML({},saved,{reviewDraft})',{saved,reviewDraft}),/private-review|textarea/);
});
test('request reviewer and requester controls use distinct current capabilities',()=>{
 const request={id:'request',actor:'requester',state:'approval_pending',approvals:[]};
 const reviewer=html('workRequestHTML(request,job)',{request,job:{actor_id:'reviewer',can_request:false,can_review_request:true,can_reconcile:false}});
 assert.match(reviewer,/data-action="approve_request"/);assert.doesNotMatch(reviewer,/data-action="reconcile_request"/);
 assert.doesNotMatch(html('workRequestHTML(request,job)',{request,job:{actor_id:'requester',can_review_request:true}}),/data-action="approve_request"/);
 assert.doesNotMatch(html('workRequestHTML(request,job)',{request:{...request,approvals:[{actor:'reviewer'}]},job:{actor_id:'reviewer',can_review_request:true}}),/data-action="approve_request"/);
});
test('failed or stale report never permits editing a previous result as current evidence',()=>{
 const saved={attempt_id:'a',result:{text:'previous body'}};
 const failed=html('workReviewDraftHTML({},saved)',{saved:{...saved,status:'failed'}});assert.doesNotMatch(failed,/previous body|textarea|save_review_draft/);
 const stale=html('workReviewDraftHTML({},saved)',{saved:{...saved,status:'review_required',result_stale:true}});assert.match(stale,/previous body/);assert.match(stale,/<textarea[^>]* readonly/);assert.doesNotMatch(stale,/save_review_draft/);assert.match(stale,/선행 근거가 바뀌었습니다/);
});
test('historical values compare only the stored shared input without replacing it',()=>{
 const attempt={inputs:{shared:'old',run:'prior-run'},snapshot:{job:{inputs:[{id:'shared',name:'공유 값',scope:'workflow'},{id:'run',scope:'run'}]}}};
 const out=html('workHistoricalValuesHTML(attempt,current)',{attempt,current:{shared:'new',run:'today'}});
 assert.match(out,/old/);assert.match(out,/prior-run/);assert.equal((out.match(/지금과 다름/g)||[]).length,1);assert.doesNotMatch(out,/new|today/);
 assert.doesNotMatch(html('workHistoricalValuesHTML(attempt,current)',{attempt:{...attempt,evidence_access:'requires_current_source_access'},current:{shared:'new'}}),/old|prior-run/);
});
test('records are scoped and put active runs first without inventing a date range',()=>{
 const runs=[{id:'old',workflow_id:'w',status:'completed',created_at:'2026-10-02',progress:{}},{id:'open',workflow_id:'w',status:'open',created_at:'2026-10-01',progress:{}},{id:'other',workflow_id:'x',status:'open',progress:{}}];
 const out=html('workRunRecordsHTML(runs,"w","Saved name")',{runs});assert.ok(out.indexOf('data-run-id="open"')<out.indexOf('data-run-id="old"'));assert.doesNotMatch(out,/data-run-id="other"|최근 3개월/);
});
test('empty work shows only the earliest real scheduled execution',()=>{
 const out=html('workMyWorkHTML([],operations)',{operations:{schedules:[{enabled:true,next_at:1791007200,name:'later'},{enabled:true,next_at:1791003600,name:'next'},{enabled:false,next_at:1791000000,name:'disabled'}]}});
 assert.match(out,/next/);assert.doesNotMatch(out,/later|disabled|추천/);assert.match(out,/63982.svg/);
});
test('asking about a historical record only changes private reference and never dispatches',async()=>{
 const h=controller();h.context.document.querySelector=()=>({focus(){}});h.api.setSelection({run_id:'r',workflow_id:'w'});h.api.setState({run:{id:'r',workflow_id:'w',version:1,attempts:[{id:'a',job_id:'j',number:2,created_at:'then'}]}});
 await h.api.handleClick({dataset:{action:'ask_record',jobId:'j'}});assert.equal(h.calls.length,0);assert.equal(h.api.reference().attempt_id,'a');assert.equal(h.api.reference().result_revision,2);
 await h.api.select({job_id:'other'},{fetch:false});assert.equal(h.api.snapshot().selection.chat_reference,null);
});
test('question from a historical row preserves its exact attempt instead of the newest row',async()=>{
 const h=controller();h.context.document.querySelector=()=>({focus(){}});h.api.setSelection({run_id:'r',workflow_id:'w'});h.api.setState({run:{id:'r',workflow_id:'w',version:1,revision:9,attempts:[{id:'old',job_id:'j',number:1,created_at:'2026-10-01'},{id:'new',job_id:'j',number:2,created_at:'2026-10-02'}]}});
 await h.api.handleClick({dataset:{action:'ask_record',jobId:'j',attemptId:'old'}});assert.equal(h.api.reference().attempt_id,'old');assert.equal(h.api.reference().reference_kind,'historical');assert.equal(h.api.reference().revision,9);assert.equal(h.calls.length,0);
 await assert.rejects(h.api.handleClick({dataset:{action:'ask_record',jobId:'j',attemptId:'missing'}}),/기록이 없습니다/);assert.equal(h.api.reference().attempt_id,'old');assert.equal(h.calls.length,0);
});
test('draft save sends immutable attempt and both revisions without executing or deciding',async()=>{
 const h=controller();h.api.setSelection({run_id:'r',workflow_id:'w',job_id:'j'});h.api.setState({run:{id:'r',revision:5,jobs:{j:{attempt_id:'a',can_decide:true}}}});
 h.view.readReview=()=>({dirty:true,inputs:{text:'edited'},attempt_id:'a',result_revision:2,revision:3,key:'draft-key',serial:4});let acknowledged;
 h.view.clearReview=(...args)=>{acknowledged=args;};h.setReply(call=>call.body?.action==='save_review_draft'?{ok:true,run:{jobs:{j:{review_draft:{revision:4,text:'edited'}}}}}:{ok:true,systems:[],workflows:[],runs:[],ui_state:{revision:0,state:{}}});
 await h.api.handleClick({dataset:{action:'save_review_draft'}});const writes=h.calls.filter(call=>call.body?.action);assert.equal(writes.length,1);assert.equal(writes[0].body.attempt_id,'a');assert.equal(writes[0].body.review_revision,3);assert.equal(writes[0].body.expected_revision,5);assert.equal(writes[0].body.result_revision,2);assert.deepEqual(acknowledged,['draft-key',4,4,'edited']);
});
test('late draft save cannot acknowledge or repaint after another work target is selected',async()=>{
 const h=controller(),pending=deferred();h.api.setSelection({run_id:'r',job_id:'j'});h.api.setState({run:{id:'r',revision:5,jobs:{j:{attempt_id:'a'}}}});
 h.view.readReview=()=>({dirty:true,inputs:{text:'kept'},attempt_id:'a',result_revision:2,revision:0});let acknowledgements=0;h.view.clearReview=()=>acknowledgements++;
 h.setReply(()=>pending.promise);const waiting=h.api.handleClick({dataset:{action:'save_review_draft'}});h.api.setSelection({job_id:'other'});pending.resolve({ok:true,run:{jobs:{j:{review_draft:{revision:1,text:'kept'}}}}});await waiting;assert.equal(acknowledgements,0);assert.equal(h.calls.length,1);
});

test('request fields follow native schema types and bindings, with reason outside EES values',()=>{
 const node={tool_contract_id:'restart',inputs:[{id:'wait',type:'text',name:'old'},{id:'stop',type:'text'},{id:'reason',type:'text'}],argument_bindings:{timeout:{input:'wait'},mode:{input:'stop'}}},tools=[{id:'restart',input_schema:{type:'object',required:['timeout'],properties:{timeout:{type:'integer',title:'종료 대기',minimum:0,maximum:300},mode:{type:'string',enum:['graceful','force']}}}}];
 const fields=html('workRequestFields(node,tools)',{node,tools});assert.equal(fields.length,2);assert.equal(fields[0].type,'number');assert.equal(fields[0].id,'wait');assert.equal(fields[1].type,'single');assert.equal(fields.some(field=>field.id==='reason'),false);
 const out=html('workInputHTML(field,60)',{field:fields[0]});assert.match(out,/type="number" step="1" min="0" max="300"/);
 assert.equal(html('workRequestFields(node,[])',{node}),null);
});
test('ad-hoc start lists active factories and disables only those with active work',()=>{
 const data={workflow:{id:'w',name:'Setup',published_version:2},factories:[{id:'a',name:'Alpha',system_id:'EMS'},{id:'b',name:'Beta',system_id:'EMS'}],workflow_active_runs:[{id:'existing',workflow_id:'w',factory_id:'a',status:'open',progress:{}}]},selection={system_id:'EMS',factory_id:'b'},definition={execution_scope:'factory',nodes:{}};
 const out=html('workAdhocStartHTML(data,selection,definition)',{data,selection,definition});assert.match(out,/data-run-id="existing"/);assert.match(out,/<option value="a" disabled>Alpha · 이미 진행 중/);assert.match(out,/<option value="b" selected>Beta/);assert.match(out,/data-action="start_run" data-start-inline/);assert.doesNotMatch(out,/김도윤|미국 공장|완료 0\/0/);
 data.workflow_active_runs[0].progress={completed:0,total:1};assert.match(html('workAdhocStartHTML(data,selection,definition)',{data,selection,definition}),/완료 0\/1/);
});
test('item verdict options stay pending and AI suggestions cannot enable final confirmation',()=>{
 const job={result_block:'item_verdict',judgments:[{id:'approved',label:'승인',status:'completed'},{id:'unknown',label:'판단 불가',status:'unknown'}]},saved={result:{items:[{id:'one',ai_suggestion:'completed'},{id:'two'}]}};
 const out=html('workResultHTML(job,saved,{verdictDraft:{one:{verdict:"completed",judgment_id:"approved"}}})',{job,saved});assert.match(out,/내 선택 · 확정 전 · 자동 저장/);assert.match(out,/data-action="confirm_verdicts"[^>]* disabled/);assert.match(out,/value="approved" data-verdict="completed" data-judgment-id="approved" selected>승인/);
 const ready=html('workResultHTML(job,saved,{verdictDraft:{one:{verdict:"completed",judgment_id:"approved"},two:{verdict:"unknown"}}})',{job,saved});assert.doesNotMatch(ready,/data-action="confirm_verdicts"[^>]* disabled/);
});
test('A7 has automatic save status and no save button, and basis cards expose actual time',()=>{
 const out=html('workReviewDraftHTML({},saved,{reviewDraft:{dirty:true,inputs:{text:"new"}}})',{saved:{attempt_id:'a',result:{text:'old'}}});assert.match(out,/자동 저장 대기 중/);assert.doesNotMatch(out,/data-action="save_review_draft"/);
 assert.match(html('workMessageReferenceHTML({kind:"workspace",workflow_id:"w",created_at:"2026-10-05T07:00:00Z"},"m")'),/기준 시각/);
 assert.match(html('workPartialSourceHTML({snapshot:{prerequisite_sources:{source:{status:"partial"}}}})'),/부분 결과에서 시작함/);
});
test('navigation flushes edits made while an older review autosave is still in flight',async()=>{
 const h=controller(),first=deferred(),started=deferred();let text='first',savedText='base',serial=1,revision=0,saves=0;
 h.api.setSelection({run_id:'r',job_id:'j'});const state={run:{id:'r',revision:1,definition:{nodes:{j:{result_block:'ai_review'}}},jobs:{j:{attempt_id:'a'}}}};h.api.setState(state);
 h.view.readReview=()=>({dirty:text!==savedText,inputs:{text},serial,revision,attempt_id:'a',result_revision:1,key:'key'});h.view.clearReview=(key,ack,rev,value)=>{savedText=value;revision=rev;};
 h.setReply(call=>{if(call.body?.action==='save_review_draft'){saves++;if(saves===1){started.resolve();return first.promise;}return {ok:true,run:{jobs:{j:{review_draft:{revision:2,text:call.body.text}}}}};}return {ok:true,...state,systems:[],workflows:[],runs:[]};});
 const saving=h.api.handleClick({dataset:{action:'save_review_draft'}});await started.promise;text='latest';serial++;
 const navigating=h.api.select({job_id:'next'},{fetch:false});first.resolve({ok:true,run:{jobs:{j:{review_draft:{revision:1,text:'first'}}}}});await saving;await navigating;
 assert.equal(saves,2);assert.equal(savedText,'latest');assert.equal(h.api.snapshot().selection.job_id,'next');
});
test('failed automatic review save keeps the current work and preserves its draft',async()=>{
 const h=controller();h.api.setSelection({run_id:'r',job_id:'j'});h.api.setState({run:{id:'r',revision:1,definition:{nodes:{j:{result_block:'ai_review'}}},jobs:{j:{attempt_id:'a'}}}});
 h.view.readReview=()=>({dirty:true,inputs:{text:'kept'},attempt_id:'a',result_revision:1,revision:0});h.setReply(()=>({ok:false,error:{message:'save failed'}}));
 assert.equal(await h.api.select({job_id:'next'},{fetch:false}),null);assert.equal(h.api.snapshot().selection.job_id,'j');assert.match(h.api.snapshot().error,/save failed/);
});
test('same-status custom words retain distinct pending IDs and final immutable wording',()=>{
 const job={result_block:'item_verdict',judgments:[{id:'accepted',label:'승인',status:'completed'},{id:'conditional',label:'조건부 승인',status:'completed'}]},saved={result:{items:[{id:'one'}]}};
 const out=html('workResultHTML(job,saved,{verdictDraft:{one:{judgment_id:"conditional",verdict:"completed"}}})',{job,saved});
 assert.match(out,/value="conditional" data-verdict="completed" data-judgment-id="conditional" selected>조건부 승인/);assert.doesNotMatch(out,/value="accepted"[^>]* selected/);
 const final=html('workResultHTML(job,saved)',{job,saved:{...saved,status:'completed',decisions:{one:{verdict:'completed',note:'선택한 판정: 조건부 승인 (conditional)'}}}});assert.match(final,/선택한 판정: 조건부 승인/);assert.doesNotMatch(final,/data-item-verdict|data-action="confirm_verdicts"/);
 const legacy=html('workResultHTML(job,saved)',{job,saved:{...saved,status:'completed',result:{items:[{id:'one'},{id:'optional',required:false}]},decisions:{one:{verdict:'completed'}}}});assert.doesNotMatch(legacy,/data-action="confirm_verdicts"/);
});
test('partial provenance survives a failed human verdict without changing its primary status',()=>{
 const attempt={snapshot:{prerequisite_sources:{source:{status:'failed',attempt_id:'source-attempt'}}}},run={attempts:[{id:'source-attempt',status:'partial',result:{completeness:'partial'}}]};
 assert.match(html('workPartialSourceHTML(attempt,run)',{attempt,run}),/부분 결과에서 시작함/);
 assert.match(html('workResultHTML({result_block:"item_verdict"},{status:"failed",result:{completeness:"partial",items:[]}})'),/부분 결과/);
});
test('private verdict autosave persists exact term without deciding and restores after reload',async()=>{
 const h=controller();h.api.setSelection({run_id:'r',job_id:'j'});h.api.setState({run:{id:'r',jobs:{j:{attempt_id:'a',decisions:{}}}}});
 const target={dataset:{itemId:'one'},value:'conditional',selectedOptions:[{dataset:{verdict:'completed',judgmentId:'conditional'}}],closest:selector=>selector==='[data-ees-work]'?{}:null,matches:selector=>selector==='[data-item-verdict]'};
 h.api.handleEvent({type:'change',target});for(const callback of [...h.timers.values()])callback();await new Promise(setImmediate);
 const writes=h.calls.filter(call=>call.body);assert.equal(writes.length,1);assert.equal(writes[0].body.action,'save_ui');assert.deepEqual(writes[0].body.state.selection.verdict_drafts['r/j/a'].one,{verdict:'completed',judgment_id:'conditional'});
 const other=controller();other.api.setRestored(false);other.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,ui_state:{revision:1,state:writes[0].body.state},systems:[],workflows:[],runs:[]}:{ok:true});await other.api.refresh();assert.equal(other.api.snapshot().selection.verdict_drafts['r/j/a'].one.judgment_id,'conditional');
});
test('private draft storage failure is visible and never discards pending selection',async()=>{
 const h=controller();h.api.setSelection({run_id:'r',job_id:'j',request_reasons:{'r/j':'x'.repeat(40000)}});h.api.setState({run:{id:'r',jobs:{j:{attempt_id:'a',decisions:{}}}}});
 await h.api.handleClick({dataset:{action:'retry_private_save'}});for(const callback of [...h.timers.values()])callback();await new Promise(setImmediate);
 assert.match(h.api.snapshot().error,/자동 저장 실패/);assert.equal(h.api.snapshot().selection.request_reasons['r/j'].length,40000);assert.equal(h.calls.length,0);
});
test('schema field ordering is not an edit while changed values retain save protection',()=>{
 const context=renderer();run(context,'var drafts=createWorkInputDrafts();var original={target:"AP",stop:"graceful",wait:0,nested:{b:false,a:""}};drafts.edit("request",{nested:{a:"",b:false},wait:0,stop:"graceful",target:"AP"},1,original)');
 assert.equal(run(context,'drafts.read("request",original,1).dirty'),false);
 run(context,'drafts.edit("request",{target:"AP",stop:"graceful",wait:1,nested:{a:"",b:false}},1,original)');assert.equal(run(context,'drafts.read("request",original,1).dirty'),true);
 assert.equal(run(context,'workValuesEqual({a:[1,2]},{a:[2,1]})'),false);assert.equal(run(context,'workValuesEqual({a:false},{a:0})'),false);assert.equal(run(context,'workValuesEqual({a:""},{})'),false);
});
test('missing evidence and external request URLs never become local undefined links',()=>{
 for(const value of [undefined,null,'','   ',{},false])assert.equal(html('workUI.safeURL(value)',{value}),'');
 assert.doesNotMatch(html('workChecklistHTML([{id:"a",name:"A"}],{})'),/근거 열기|href=/);
 assert.doesNotMatch(html('workRequestHTML({},{})'),/EES에서 보기|href=/);
 assert.match(html('workChecklistHTML([{id:"a",url:"https://example.invalid/evidence"}],{})'),/https:\/\/example.invalid\/evidence/);
});


const uuidV4=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const httpCrypto=()=>({getRandomValues:bytes=>crypto.webcrypto.getRandomValues(bytes)});
test('shared ID helper prefers the native randomUUID with its receiver',()=>{
 const expected='12345678-1234-4234-8234-123456789abc';let calls=0;
 const provider={randomUUID(){assert.equal(this,provider);calls++;return expected;},getRandomValues(){assert.fail('native UUID must be preferred');}};
 assert.equal(html('workUI.newId()',{crypto:provider}),expected);assert.equal(calls,1);
});
test('shared ID fallback sets UUID version and variant while preserving random bytes',()=>{
 for(const fill of [0,255]){
  let calls=0;const provider={getRandomValues(bytes){assert.equal(this,provider);assert.equal(bytes.constructor.name,'Uint8Array');assert.equal(bytes.length,16);calls++;bytes.fill(fill);return bytes;}};
  const id=html('workUI.newId()',{crypto:provider});assert.equal(id,fill?'ffffffff-ffff-4fff-bfff-ffffffffffff':'00000000-0000-4000-8000-000000000000');assert.equal(calls,1);
 }
 const context=renderer({crypto:httpCrypto()}),ids=Array.from({length:128},()=>run(context,'workUI.newId()'));
 ids.forEach(id=>assert.match(id,uuidV4));assert.equal(new Set(ids).size,ids.length);
});
test('shared ID generation refuses missing secure randomness',()=>{
 for(const unavailable of [undefined,{}, {randomUUID:null,getRandomValues:null}])assert.throws(()=>html('workUI.newId()',{crypto:unavailable}),/[가-힣]/);
 const failure=new Error('random source failed');assert.throws(()=>html('workUI.newId()',{crypto:{getRandomValues(){throw failure;}}}),error=>error===failure);
});
test('missing randomUUID preserves runtime command receipt and first-chat boundaries',async()=>{
 const h=controller();h.context.crypto=httpCrypto();let attempts=0;
 h.setReply(()=>{if(!attempts++)throw new Error('response lost');return {ok:true};});
 const body={action:'save_inputs',run_id:'r',expected_revision:4,inputs:{value:false}};
 await assert.rejects(h.api.command(body),/response lost/);await h.api.command(body);assert.match(h.calls[0].body.request_id,uuidV4);assert.deepEqual(h.calls[0].body,h.calls[1].body);
 await h.api.command({...body,inputs:{value:true}});assert.notEqual(h.calls[2].body.request_id,h.calls[0].body.request_id);
 h.api.setSelection({mode:'author',workflow_id:'w'});h.api.setState({workflow:{revision:2}});h.designer.readDraft=()=>({revision:2,definition:{id:'w',name:'draft'}});
 const source=h.api.context(),creation=h.api.beginChatCreation();assert.match(creation,uuidV4);h.api.finishChatCreation(creation,'native-new');h.context.location.pathname='/c/native-new';
 assert.equal(h.api.acceptNativeProposal('native-new',{context_id:source}).ok,true);h.setAuth('another-account');assert.equal(h.api.acceptNativeProposal('native-new',{context_id:source}).ok,false);
});

test('missing source API fails closed with no duplicate runtime transport',async()=>{
 const h=controller();delete h.context.window.__eesSourceShellV1.request;
 await assert.rejects(h.api.command({action:'save_inputs',run_id:'r',inputs:{value:'keep'}}),/업무 화면 연결/);assert.equal(h.calls.length,0);
 const source=require('./ees_workspace_ui_fixture.cjs').launcherSource;assert.doesNotMatch(source,/fetch\('\/api\/ees-work\//);
});
test('source API receives the original command contract and keeps runtime late-target guards',async()=>{
 const h=controller(),pending=deferred(),calls=[];
 h.context.window.__eesSourceShellV1.request=(path,body,signal)=>{calls.push({path,body,signal});return pending.promise;};
 h.api.setSelection({run_id:'r',job_id:'j'});const request=h.api.command({action:'save_inputs',run_id:'r',inputs:{value:'old'}});h.api.setSelection({job_id:'other'});pending.resolve({ok:true,revision:2});assert.equal(await request,null);assert.equal(calls.length,1);assert.equal(calls[0].path,'workspace/command');assert.equal(calls[0].body.inputs.value,'old');assert.equal(h.api.snapshot().state,null);
});

test('same shared-tool review leaves an ongoing run executable and changed versions require choice',()=>{
 const {viewSource}=require('./ees_workspace_ui_fixture.cjs'),context=renderer();
 // Expose the real render function only in this in-memory test copy.
 run(context,viewSource.slice(viewSource.indexOf('function createWorkView(')).replace('return Object.freeze({render,sync,','return Object.freeze({testJobPanel:jobPanel,render,sync,'));
 context.snapshot={selection:{job_id:'j',tab:'current'},state:{capabilities:{actor_id:'a'},operations:{shared_tools:[{id:'managed-search_pages',name:'페이지 찾기',version:1,state:'available',can_use:true}]},run:{id:'r',status:'running',revision:1,definition:{nodes:{j:{id:'j',name:'찾기',mode:'tool',shared_tool_id:'managed-search_pages',inputs:[],result_block:'human_confirm'}}},jobs:{j:{}},shared_tools:[{id:'managed-search_pages',version:1}],inputs:{}}}};
 run(context,'globalThis.sharedView=createWorkView({callbacks:{}});sharedView.sync(snapshot)');
 const panel=()=>run(context,'sharedView.testJobPanel()');
 assert.match(panel(),/data-action="execute"[^>]*>/);assert.doesNotMatch(panel(),/data-action="execute"[^>]*disabled/);
 context.snapshot.state.operations.shared_tools[0].revision=2; // evidence-only review
 run(context,'sharedView.sync(snapshot)');assert.doesNotMatch(panel(),/data-action="execute"[^>]*disabled/);
 context.snapshot.state.operations.shared_tools[0].version=2;
 run(context,'sharedView.sync(snapshot)');assert.match(panel(),/v2 버전으로 계속하기/);assert.match(panel(),/data-action="execute"[^>]*disabled/);
 context.snapshot.state.operations.shared_tools[0].state='unavailable';context.snapshot.state.operations.shared_tools[0].unavailable_message='Open WebUI 도구의 연결 설정을 확인해야 합니다.';
 run(context,'sharedView.sync(snapshot)');assert.match(panel(),/연결 설정을 확인해야/);assert.doesNotMatch(panel(),/버전으로 계속하기/);
});

test('scope frame monitor records delivered JSON before the consumer renders even when a clone lags',async()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
 const source=fs.readFileSync(path.join(__dirname,'ees_source_frame_monitor.py'),'utf8').split('FRAME_MONITOR = r"""')[1].split('"""')[0];
 const body={ok:true,workflows:[]},clone=deferred(),response={ok:true,json:async()=>body,clone:()=>({json:()=>clone.promise})};
 const window={fetch:async()=>response},context={window,URL,document:{addEventListener:()=>{}},location:{href:'http://native.test/c/chat'},performance:{now:()=>10},requestAnimationFrame:()=>1};
 vm.runInNewContext(source,context);
 window.__eesSourceFrameEvidence.scopeExpectation={label:'first',system:'APC',factory:'',unknown:true,endpoints:['workspace'],received:{}};
 const result=await (await window.fetch('/api/ees-work/workspace?system_id=APC')).json();
 assert.equal(result,body,'The observation must preserve the actual response body');
 assert.equal(window.__eesSourceFrameEvidence.scopeExpectation.received.workspace,true,'Body delivery must be observed before its consumer can render an empty result');
 clone.resolve(body);
});

test('cross-system tool use clears the previous factory and opens the target scope',async()=>{
 const h=controller();h.api.setState({capabilities:nativeCapabilities({is_admin:true,can_author:true,managed_systems:['EMS','FDC']}),systems:['EMS','FDC'],workflows:[],runs:[],operations:{},ui_state:{revision:0,state:{}}});
 h.api.setSelection({system_id:'EMS',factory_id:'ems-factory',workflow_id:'ems-workflow',run_id:'old-run',job_id:'old-job'});
 await h.designer.callbacks.openWorkflow('fdc-workflow','FDC');
 const selected=h.api.snapshot().selection;
 assert.equal(selected.system_id,'FDC');assert.equal(selected.factory_id,'');assert.equal(selected.workflow_id,'fdc-workflow');assert.equal(selected.run_id,'');assert.equal(selected.job_id,'');
 h.api.setSelection({factory_id:'fdc-factory'});await h.designer.callbacks.openWorkflow('other-fdc','FDC');assert.equal(h.api.snapshot().selection.factory_id,'fdc-factory');
});
