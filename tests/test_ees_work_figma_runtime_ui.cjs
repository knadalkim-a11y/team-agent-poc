/* Reconstructed from recorded source reads and patches after workspace loss.
 * These are controller/renderer contracts, not Native product evidence. */
const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
const html=(source,values={})=>run(renderer(values),source);

test('handled author Escape keeps focus local without swallowing unrelated Native keys',()=>{
 const harness=controller();
 harness.designer.handleEvent=()=>({handled:true,preventDefault:true});
 for(const key of ['Escape','Enter']){
  let prevented=0,stopped=0;
  harness.api.handleEvent({type:'keydown',key,target:{},preventDefault(){prevented++;},stopPropagation(){stopped++;}});
  assert.equal(prevented,1);assert.equal(stopped,key==='Escape'?1:0);
 }
 harness.designer.handleEvent=()=>({handled:false});
 harness.api.handleEvent({type:'keydown',key:'Escape',target:{closest:()=>null},preventDefault(){assert.fail('Native key prevented');},stopPropagation(){assert.fail('Native key stopped');}});
});

test('procedure entry initializes once through POST then renders ordinary workflows',async()=>{
 const h=controller(),state={ok:true,capabilities:{actor_id:'a',can_author:true,managed_systems:['EMS']},systems:['EMS'],initial_procedures_ready:false,workflows:[],runs:[],ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'author',tab:'overview',system_id:'EMS'});
 h.setReply(call=>{if(call.body?.action==='initialize_procedures'){assert.equal(call.body.system_id,'EMS');assert.equal(call.body.expected_revision,0);state.initial_procedures_ready=true;state.workflows=[{id:'initial',name:'Initial procedure',system_id:'EMS'}];return {ok:true};}return call.url.includes('workspace?')?state:{ok:true};});
 await h.api.refresh();await h.api.refresh();
 assert.equal(h.calls.filter(call=>call.body?.action==='initialize_procedures').length,1);
 assert.equal(h.api.snapshot().state.workflows[0].id,'initial');
});

test('initial registration is not attempted by readers, tools pages or ordinary work views',async()=>{
 for(const [mode,tab,managed] of [['author','overview',[]],['author','tools',['EMS']],['work','overview',['EMS']]]){
  const h=controller(),state={ok:true,capabilities:{actor_id:'a',can_author:!!managed.length,managed_systems:managed},systems:['EMS'],initial_procedures_ready:false,workflows:[],runs:[],ui_state:{revision:0,state:{}}};
  h.api.setState(state);h.api.setSelection({mode,tab,system_id:'EMS'});h.setReply(call=>call.url.includes('workspace?')?state:{ok:true});await h.api.refresh();
  assert.equal(h.calls.filter(call=>call.body?.action==='initialize_procedures').length,0);
 }
});

test('the product Tools tab reads the registered catalog without operational dependencies', async()=>{
 const h=controller(), catalog={services:[{id:'confluence'}],apis:[{id:'page'},{id:'children'}],can_manage:true};
 const state={ok:true,confluence_guide:true,capabilities:{actor_id:'a',is_admin:true},systems:['EMS'],workflows:[],runs:[],ui_state:{revision:0,state:{}}};
 h.api.setState(state);h.api.setSelection({mode:'author',tab:'tools',system_id:'EMS'});
 h.setReply(call=>{
  if(call.url.includes('workspace?'))return state;
  if(call.url.endsWith('/api-catalog'))return {ok:true,api_catalog:catalog};
  return {httpError:true,status:500,error:{message:'Execution state unavailable'}};
 });
 await h.api.refresh();
 assert.deepEqual([...h.api.snapshot().state.operations.api_catalog.apis].map(api=>api.id),['page','children']);
 assert.equal(h.calls.filter(call=>call.url.includes('/operations?')).length,0);
 h.api.setSelection({tab:'overview'});
 await h.api.refresh();
 assert.equal(h.api.snapshot().state.operations.error,'Execution state unavailable');
 assert.deepEqual([...h.api.snapshot().state.operations.api_catalog.apis].map(api=>api.id),['page','children']);
 h.setReply(call=>call.url.includes('workspace?')?state:{httpError:true,status:403,error:{message:'Denied'}});
 const before=h.calls.length;
 await h.api.refresh();
 assert.equal(h.api.snapshot().state,null);
 assert.ok(!h.calls.slice(before).some(call=>call.url.endsWith('/api-catalog')));
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

test('workspace assets and settings retain server permissions without duplicate prompt or Native labels',()=>{
 const admin=nativeCapabilities({is_admin:true,can_author:true,native_access:{models:true,knowledge:true,prompts:true,skills:true,tools:true,admin:true}});
 const rendered=html('workWorkspaceMenuHTML({capabilities}, {tab:"tools"})',{capabilities:admin});
 assert.equal(html("workNativeAllowed(capabilities,'tools')",{capabilities:admin}),false);
 assert.equal((rendered.match(/class="ew-nav-group ew-assets-group"/g)||[]).length,1);
 for(const label of ['업무 절차','도구·자료','작업 지침','AI 도우미 설정','참고 문서','관리자 설정'])assert.ok(rendered.includes(label),label);
 assert.doesNotMatch(rendered,/공장·접근 범위|workspace_admin|admin_factory|admin_access|업무 만들기|AI 설정|관리자만|스킬·지침|빠른 문장|data-native-id="(?:tools|prompts)"|ew-nav-native-name/);
 const assets=rendered.match(/<section class="ew-nav-group ew-assets-group">(.*?)<\/section>/)[1];
 assert.match(assets,/data-action="tools"/);for(const id of ['skills','knowledge'])assert.ok(assets.includes('data-native-id="'+id+'"'));assert.doesNotMatch(assets,/data-native-id="(?:models|admin)"/);
 const nativeSelected=html('workWorkspaceMenuHTML({capabilities,workflows:[{id:"kept",name:"Previous draft",updated_at:"2026-10-11"}]}, {workflow_id:"kept",tab:"overview",native_id:"skills"})',{capabilities:admin});
 assert.equal((nativeSelected.match(/aria-current="page"/g)||[]).length,1);assert.match(nativeSelected,/data-native-id="skills"[^>]*aria-current="page"/);
 const collapsed=html('workWorkspaceMenuHTML({capabilities}, {collapsed:["assets"]})',{capabilities:admin});assert.match(collapsed,/aria-expanded="false"/);assert.match(collapsed,/id="ees-assets-items" inert aria-hidden="true"/);
 const author=nativeCapabilities({can_author:true,managed_systems:['EMS'],native_access:{skills:true,tools:true}}),authorHTML=html('workWorkspaceMenuHTML({capabilities}, {})',{capabilities:author});
 assert.match(authorHTML,/data-native-id="skills"/);assert.doesNotMatch(authorHTML,/data-native-id="(?:models|admin|knowledge)"/);
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
test('authoring factory scope preserves the open definition and unfinished creation without writing work',async()=>{
 const h=nativeNavigationHarness(),draft={definition:{name:'미저장 작성',execution_scope:'system',nodes:{j:{name:'보존할 작업'}}},dirty:true};
 h.state.factories=[{id:'factory-a',name:'공장 A',system_id:'EMS'},{id:'factory-denied',name:'권한 없는 공장',system_id:'EMS'}];
 h.state.scope_options={systems:[{id:'EMS',allowed:true}],factories:[{id:'factory-a',allowed:true},{id:'factory-denied',allowed:false}]};
 h.state.workflows=[{id:'w',system_id:'EMS',name:'기존 절차'}];
 h.state.workflow={id:'w',revision:1,draft:draft.definition};
 let captured=0,closed=0;h.designer.readDraft=()=>{captured++;return draft;};h.designer.closeStart=()=>closed++;
 const composer=JSON.parse(JSON.stringify(h.readDraft())),definition=JSON.stringify(draft);
 await h.api.sourceAction({action:'choose_factory',factoryId:'factory-denied'});
 await h.api.sourceAction({action:'choose_factory',factoryId:'unknown'});
 assert.equal(h.calls.length,0);assert.equal(captured,0);
 await h.api.sourceAction({action:'choose_factory',factoryId:'factory-a'});
 const selected=h.api.snapshot().selection;
 assert.equal(selected.mode,'author');assert.equal(selected.system_id,'EMS');assert.equal(selected.factory_id,'factory-a');
 assert.equal(selected.workflow_id,'w');assert.equal(selected.job_id,'j');assert.equal(selected.tab,'overview');
 assert.ok(captured>0);assert.equal(closed,0,'Changing view scope must not close the unfinished new-procedure form');
 assert.equal(JSON.stringify(draft),definition);assert.deepEqual(h.readDraft(),composer);
 assert.ok(h.calls.some(call=>call.url.includes('factory_id=factory-a')));
 assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);
 const count=h.calls.length,reads=captured;
 await h.api.sourceAction({action:'choose_factory',factoryId:'factory-a'});
 assert.equal(h.calls.length,count);assert.equal(captured,reads,'Choosing the same factory is a no-op');
 await h.api.sourceAction({action:'choose_factory',factoryId:''});
 assert.equal(h.api.snapshot().selection.factory_id,'');assert.equal(h.api.snapshot().selection.workflow_id,'w');
 assert.equal(JSON.stringify(draft),definition);assert.equal(closed,0);
});
test('factory scope stays available in tools and unavailable in Native management',async()=>{
 const tools=nativeNavigationHarness();tools.state.factories=[{id:'factory-a',system_id:'EMS'}];tools.api.setSelection({mode:'author',tab:'tools',system_id:'EMS',factory_id:''});await tools.api.sourceAction({action:'choose_factory',factoryId:'factory-a'});assert.equal(tools.api.snapshot().selection.factory_id,'factory-a');assert.equal(tools.api.snapshot().selection.tab,'tools');assert.equal(tools.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);
 const h=nativeNavigationHarness();h.state.factories=[{id:'factory-a',system_id:'EMS'}];await h.open();const before=h.calls.length;
 await h.api.handleClick({dataset:{action:'choose_factory',factoryId:'factory-a'}});
 assert.equal(h.api.snapshot().selection.factory_id,'');assert.equal(h.calls.length,before);assert.equal(h.context.location.pathname,'/workspace/skills');
});
test('allowed Native destinations use static routes and the retired tool shortcut stays closed',async()=>{
 const old=nativeNavigationHarness();await old.open('tools');assert.deepEqual(old.navigation,[]);
 for(const id of ['skills','models','knowledge','prompts','admin']){const h=nativeNavigationHarness();await h.open(id);assert.deepEqual(h.navigation,[id==='admin'?'/admin/settings':'/workspace/'+id]);assert.equal(h.renders.at(-1)?.native_shell,true);assert.equal(h.renders.at(-1)?.native_id,id);assert.equal(h.calls.filter(call=>call.body).length,0);}
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
 for(const [action,extra,mode,tab] of [['mode',{mode:'work'},'work','overview'],['tools',{},'author','tools']]){const h=nativeNavigationHarness(),draft=JSON.parse(JSON.stringify(h.readDraft()));await h.open();await h.back(action,extra);assert.equal(h.navigation.at(-1),'/c/original?keep=1');assert.equal(h.api.snapshot().selection.mode,mode);assert.equal(h.api.snapshot().selection.tab,tab);assert.deepEqual(h.readDraft(),draft);assert.equal(h.restores.length,0);assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);}
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
 const saved={ok:true,systems:['EMS'],workflows:[],runs:[],ui_state:{revision:5,state:{selection:{mode:'work',tab:'current',workflow_id:'old-work',run_id:'old-run',job_id:'old-job',system_id:'EMS'}}}};
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?(++reads===1?startup.promise:saved):{ok:true});
 const first=h.api.refresh();await h.api.handleClick({dataset:{action:'mode',mode:'work'}});startup.resolve(saved);await first;
 assert.equal(h.api.snapshot().selection.tab,'overview');assert.equal(h.api.snapshot().selection.job_id,'');assert.equal(h.api.snapshot().selection.system_id,'EMS');
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
function requestProposalFixture(){
 const node={id:'j',type:'j',result_block:'change_request',tool_contract_id:'restart',inputs:[{id:'wait',scope:'run'},{id:'stop',scope:'run'},{id:'target'},{id:'hidden',scope:'run'},{id:'fixed',scope:'run'},{id:'setting',scope:'workflow'},{id:'factory',scope:'factory'}],argument_bindings:{timeout:{input:'wait'},mode:'stop',fixed:{constant:false}}};
 const tools=[{id:'restart',input_schema:{type:'object',properties:{timeout:{type:'integer'},mode:{type:'string',enum:['graceful','force']},target:{type:'string'},fixed:{type:'boolean'},setting:{type:'string'},factory:{type:'string'}}}}];
 const runState={id:'r',workflow_id:'w',revision:2,inputs:{wait:60,stop:'graceful',target:'kept',hidden:'private kept'},definition:{nodes:{j:node}}};
 const payload=values=>({proposal_kind:'inputs',workflow_id:'w',run_id:'r',job_id:'j',base_revision:2,proposal:values});
 return {node,tools,runState,payload};
}
for(const [kind,values,missingTools] of [['unbound',{wait:30,hidden:'unseen suggestion'},false],['constant',{fixed:true},false],['unavailable schema',{wait:30},true]])test('change request proposal rejects '+kind+' inputs before review',()=>{
 const {tools,runState,payload}=requestProposalFixture();
 assert.throws(()=>html('workInputProposal(payload,runState,"j",tools)',{payload:payload(values),runState,tools:missingTools?[]:tools}),/현재 진행 건·작업·저장 버전과 다른 입력 제안/);
 assert.equal(runState.inputs.hidden,'private kept');assert.equal(runState.inputs.wait,60);
});
test('change request proposal preserves visible bindings typed values and setting scope boundaries',()=>{
 const {node,tools,runState,payload}=requestProposalFixture(),values={wait:0,stop:'force',target:'new target'};
 const accepted=html('workInputProposal(payload,runState,"j",tools)',{payload:payload(values),runState,tools});assert.deepEqual(JSON.parse(JSON.stringify(accepted)),values);
 const fields=html('workRequestFields(node,tools)',{node,tools}).filter(field=>!field.constant&&(field.scope || 'run')==='run');assert.deepEqual(Array.from(fields,field=>field.id),Object.keys(values));
 assert.match(html('workInputProposalBar({values},node)',{values:accepted,node}),/3칸/);
 for(const name of ['setting','factory'])assert.throws(()=>html('workInputProposal(payload,runState,"j",tools)',{payload:payload({[name]:'do not change'}),runState,tools}),/다른 입력 제안/);
 node.result_block='values';assert.equal(html('workInputProposal(payload,runState,"j",[])',{payload:payload({hidden:'ordinary input'}),runState}).hidden,'ordinary input');
});
test('request proposal controller rejects hidden values before preview and applies only reviewed fields',()=>{
 const h=controller(),{tools,runState,payload}=requestProposalFixture();let inputs={...runState.inputs},applied=0;
 h.api.setSelection({mode:'work',system_id:'EMS',workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});h.api.setState({run:runState,operations:{tools}});
 h.view.readInputs=()=>({inputs,revision:2});h.view.applyInputValues=values=>{applied++;inputs={...inputs,...values};};
 assert.throws(()=>h.api.previewInputProposal(payload({wait:30,hidden:'unseen suggestion'})),/다른 입력 제안/);assert.equal(h.renders.length,0);assert.equal(applied,0);
 h.api.previewInputProposal(payload({wait:30,stop:'force'}));assert.deepEqual(Object.keys(h.renders.at(-1).state.input_proposal.values),['wait','stop']);h.api.applyInputProposal();
 assert.equal(applied,1);assert.equal(inputs.wait,30);assert.equal(inputs.stop,'force');assert.equal(inputs.hidden,'private kept');assert.equal(runState.inputs.wait,60);assert.equal(h.calls.length,0);
});
test('request proposal cannot apply a field hidden by a later schema refresh',()=>{
 const h=controller(),{tools,runState,payload}=requestProposalFixture();let applied=0;
 h.api.setSelection({mode:'work',system_id:'EMS',workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});h.api.setState({run:runState,operations:{tools}});
 h.view.readInputs=()=>({inputs:{...runState.inputs},revision:2});h.view.applyInputValues=()=>{applied++;};
 h.api.previewInputProposal(payload({wait:30}));const timeout=tools[0].input_schema.properties.timeout;delete tools[0].input_schema.properties.timeout;
 assert.throws(()=>h.api.applyInputProposal(),/다른 입력 제안/);assert.equal(applied,0);assert.equal(runState.inputs.wait,60);assert.equal(h.calls.length,0);
 tools[0].input_schema.properties.timeout=timeout;h.api.applyInputProposal();assert.equal(applied,1);assert.equal(h.calls.length,0);
});
test('execution preparation keeps declared inputs and groups while using only the left selected target',()=>{
 const data={workflow:{id:'w',name:'Setup',published_version:2},factories:[{id:'b',name:'Beta',system_id:'EMS'}],native_groups:[{id:'g',name:'운영 담당'}]},selection={system_id:'EMS',factory_id:'b',start_inputs:{w:{note:'보존할 <값>'}},start_groups:{w:['g']}},definition={execution_scope:'factory',nodes:{p:{inputs:[{id:'note',name:'입력 근거',type:'text',scope:'run',required:true}]}}};
 const out=html('workRunStartFieldsHTML(data,selection,definition)',{data,selection,definition});assert.match(out,/적용 대상 · Beta · EMS/);assert.match(out,/id="ees-work-start"/);assert.match(out,/보존할 &lt;값&gt;/);assert.doesNotMatch(out,/data-start-group|함께 처리할 Native 그룹|개인 진행 건/);assert.match(out,/진행 상태를 함께 봅니다/);assert.match(out,/required/);assert.doesNotMatch(out,/새로 시작|진행 중|ees-start-factory|ew-adhoc-start|data-action="start_run"/);
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
 run(context,viewSource.slice(viewSource.indexOf('function createWorkView(')).replace('return Object.freeze({render,sync,','return Object.freeze({testJobPanel:jobPanel,testRunOverview:runOverview,render,sync,'));
 context.snapshot={selection:{job_id:'j',tab:'current'},state:{capabilities:{actor_id:'a'},operations:{shared_tools:[{id:'managed-search_pages',name:'페이지 찾기',version:1,state:'available',can_use:true}],shared_tool_access:{j:{can_use:true,can_accept_version:true}}},run:{id:'r',status:'running',revision:1,definition:{nodes:{j:{id:'j',name:'찾기',mode:'tool',shared_tool_id:'managed-search_pages',inputs:[],result_block:'human_confirm'}}},jobs:{j:{}},shared_tools:[{id:'managed-search_pages',version:1}],inputs:{}}}};
 run(context,'globalThis.sharedView=createWorkView({callbacks:{}});sharedView.sync(snapshot)');
 const panel=()=>run(context,'sharedView.testJobPanel()');
 assert.match(panel(),/data-action="execute"[^>]*>/);assert.doesNotMatch(panel(),/data-action="execute"[^>]*disabled/);
 context.snapshot.state.operations.shared_tools[0].revision=2; // evidence-only review
 run(context,'sharedView.sync(snapshot)');assert.doesNotMatch(panel(),/data-action="execute"[^>]*disabled/);
 const ops=context.snapshot.state.operations,tool=ops.shared_tools[0];
 ops.shared_tools=[];ops.shared_tool_access.j.current_tool=tool;
 run(context,'sharedView.sync(snapshot)');assert.match(panel(),/페이지 찾기/);assert.doesNotMatch(panel(),/개인 PAT|data-action="execute"[^>]*disabled/);
 tool.version=2;
 run(context,'sharedView.sync(snapshot)');assert.match(panel(),/v2 버전으로 계속하기/);assert.match(panel(),/data-action="execute"[^>]*disabled/);
 tool.state='unavailable';tool.unavailable_message='Open WebUI 도구의 연결 설정을 확인해야 합니다.';
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


function sharedRuntimeFixture(){
 const {viewSource}=require('./ees_workspace_ui_fixture.cjs'),context=renderer();
 run(context,viewSource.slice(viewSource.indexOf('function createWorkView(')).replace('return Object.freeze({render,sync,','return Object.freeze({testJobPanel:jobPanel,testRunOverview:runOverview,render,sync,'));
 const snapshot={selection:{job_id:'j',tab:'current'},state:{capabilities:{actor_id:'a'},operations:{shared_tools:[{id:'shared',name:'페이지 찾기',target:'Confluence',version:2,state:'available',can_use:true,function:'search_pages'}],shared_tool_access:{j:{can_use:true,can_accept_version:true}},shared_tool_messages:{shared_tool_review_required:'확인 문구 원본',shared_tool_version_changed:'회차 시작 뒤 도구가 v{pinned}에서 v{current} 버전으로 바뀌었습니다. 이 회차를 새 버전으로 계속할지 고르세요.'}},run:{id:'r',status:'open',can_write:true,revision:1,definition:{nodes:{j:{id:'j',name:'찾기',mode:'tool',shared_tool_id:'shared',inputs:[{id:'query',name:'찾을 말',type:'text',scope:'run'}],result_block:'list_confirm'}}},jobs:{j:{can_execute:true}},shared_tools:[{id:'shared',version:1}],inputs:{}}}};
 context.snapshot=snapshot;run(context,'globalThis.sharedView=createWorkView({callbacks:{}});');
 return {snapshot,panel(){run(context,'sharedView.sync(snapshot)');return run(context,'sharedView.testJobPanel()');},overview(){run(context,'sharedView.sync(snapshot)');return run(context,'sharedView.testRunOverview()');}};
}
test('a preserved run can accept its displayed shared tool version with an empty authoring catalog', async () => {
 const h = controller();
 const {state} = sharedRuntimeFixture().snapshot;
 const access = state.operations.shared_tool_access.j;
 const tool = state.operations.shared_tools.pop();
 access.current_tool = tool;
 h.api.setState(state);
 h.api.setSelection({mode:'work', tab:'current', run_id:state.run.id, job_id:'j'});
 const dialogs = [];
 h.setDialog(async options => { dialogs.push(options.title); return true; });
 const dataset = {action:'shared_accept_version', sharedId:tool.id, version:String(tool.version)};
 const commands = () => h.calls.filter(call => call.body?.action === 'shared_tool_accept_version');
 await h.api.handleClick({dataset:{...dataset, version:'1'}});
 access.can_accept_version = false;
 await h.api.handleClick({dataset});
 assert.equal(dialogs.length, 0);
 assert.equal(commands().length, 0);

 access.can_accept_version = true;
 await h.api.handleClick({dataset});
 assert.equal(dialogs.length, 1);
 assert.match(dialogs[0], /v2/);
 assert.equal(commands().length, 1);
 const {run_id, shared_tool_id, version, expected_revision} = commands()[0].body;
 assert.deepEqual([run_id, shared_tool_id, version, expected_revision], [state.run.id, tool.id, 2, state.run.revision]);
});

test('shared execution uses canonical server wording and hides version changes while any job runs or automatic work is not stopped',()=>{
 const h=sharedRuntimeFixture(),state=h.snapshot.state;assert.ok(h.panel().includes('회차 시작 뒤 도구가 v1에서 v2 버전으로 바뀌었습니다. 이 회차를 새 버전으로 계속할지 고르세요.'));assert.match(h.panel(),/data-action="shared_accept_version"/);
 state.operations.shared_tool_messages.shared_tool_version_changed='버전 원본 {pinned} → {current}';assert.match(h.panel(),/버전 원본 1 → 2/);
 state.run.jobs.other={status:'running'};assert.doesNotMatch(h.panel(),/data-action="shared_accept_version"/);
 delete state.run.jobs.other;state.operations.shared_tool_access.j.can_accept_version=false;assert.doesNotMatch(h.panel(),/data-action="shared_accept_version"/);
 delete state.operations.shared_tool_access.j.can_accept_version;assert.doesNotMatch(h.panel(),/data-action="shared_accept_version"/);
 state.operations.shared_tools[0].state='review_required';assert.match(h.panel(),/확인 문구 원본/);assert.match(h.panel(),/data-action="execute"[^>]*disabled/);
});
test('shared group outsiders see allowed groups and current assignee with read-only inputs and no execution button',()=>{
 const h=sharedRuntimeFixture(),state=h.snapshot.state;state.operations.shared_tools=[];state.operations.shared_tool_access.j={can_use:false,group_names:['운영 담당 <그룹>'],assignee_name:'담당 <이름>',can_accept_version:false};
 const out=h.panel();assert.match(out,/보기 전용/);assert.match(out,/이 도구로 실행할 수 있는 사람 · 운영 담당 &lt;그룹&gt;/);assert.match(out,/지금 담당 · 담당 &lt;이름&gt;/);
 assert.doesNotMatch(out,/data-action="execute"|data-action="shared_accept_version"|data-action="propose_inputs"|data-action="save_inputs"/);assert.match(out,/id="ew-run-query"[^>]*(?:disabled|readonly)/);
});
test('confirmed partial prerequisites appear on the next job heading before its first attempt',()=>{
 const h=sharedRuntimeFixture();h.snapshot.state.run.jobs.j.partial_prerequisites=[{job_id:'prior',name:'앞쪽 문서 조회',attempt_id:'a'}];
 assert.match(h.panel(),/부분 결과에서 시작함/);assert.ok(h.panel().indexOf('부분 결과에서 시작함')<h.panel().indexOf('aria-label="작업 보기"'));
 h.snapshot.state.run.jobs.j.partial_prerequisites=[];assert.doesNotMatch(h.panel(),/부분 결과에서 시작함/);
});
test('shared search result cards allow zero confirmations while legacy lists stay blocked',()=>{
 const partial={status:'partial',result:{scope:'single_page',completeness:'partial',items:[{id:'1',name:'문서'}]}};
 const out=html('workResultHTML({shared_tool_id:"shared",result_block:"list_confirm"},saved)',{saved:partial});
 assert.match(out,/찾은 문서 앞쪽 1건/);assert.match(out,/더 있을 수 있습니다. 필요한 문서를 골라 확정하면 다음 작업으로 넘어갑니다. 이 작업은 기록에 ‘부분 결과’로 남습니다./);assert.doesNotMatch(out,/완결성 · 한 쪽|이번 검색에서 받은 페이지 목록입니다/);
 const empty={status:'awaiting_confirmation',result:{scope:'single_page',completeness:'empty',items:[]}};
 const shared=html('workResultHTML({shared_tool_id:"shared",result_block:"list_confirm"},saved)',{saved:empty});
 assert.match(shared,/결과 없음/);assert.match(shared,/찾은 문서가 없습니다./);assert.match(shared,/data-action="confirm_list"[^>]*>찾은 문서 없음 확인/);assert.doesNotMatch(shared,/data-action="confirm_list"[^>]*disabled|완료 정책|완결성 · 한 쪽|이번 검색에서 받은 페이지 목록입니다/);
 const noSelection=html('workResultHTML({shared_tool_id:"shared",result_block:"list_confirm"},saved,{listDraft:{items:[{id:"1",selected:false}]}})',{saved:partial});assert.match(noSelection,/data-action="confirm_list"[^>]*>목록 확정 \(0건\)/);assert.doesNotMatch(noSelection,/data-action="confirm_list"[^>]*disabled/);
 const legacy=html('workResultHTML({result_block:"list_confirm"},saved)',{saved:empty});assert.match(legacy,/data-action="confirm_list"[^>]*disabled/);assert.match(legacy,/완료 정책/);assert.match(legacy,/완결성 · 한 쪽 — 이번 검색에서 받은 페이지 목록입니다/);
});
function sharedListController(items,shared=true){
 const h=controller(),state={capabilities:{actor_id:'a'},systems:['EMS'],operations:{},run:{id:'r',revision:1,status:'open',definition:{nodes:{j:{id:'j',result_block:'list_confirm',...(shared?{shared_tool_id:'shared'}:{})}}}},ui_state:{revision:0,state:{}}};
 state.run.jobs={j:{can_decide:true,attempt_id:'attempt',result_revision:1,result:{scope:'single_page',items}}};state.run.attempts=[{id:'attempt',job_id:'j',result:{scope:'single_page',items}}];
 h.api.setState(state);h.api.setSelection({system_id:'EMS',run_id:'r',job_id:'j'});h.view.readList=()=>({attempt_id:'attempt',result_revision:1,items:items.map(item=>({...item,selected:false}))});h.setReply(call=>call.body?{ok:true}:{ok:true,...state});return h;
}
test('shared zero results confirm directly and zero selected asks exactly once while legacy zero stays rejected',async()=>{
 const empty=sharedListController([]);let emptyDialogs=0;empty.setDialog(()=>{emptyDialogs++;return Promise.resolve(true);});await empty.api.handleClick({dataset:{action:'confirm_list'}});
 const emptyCommand=empty.calls.find(call=>call.body?.action==='confirm_list');assert.ok(emptyCommand);assert.equal(emptyCommand.body.reason,'0건 확인');assert.equal(emptyDialogs,0);
 const found=sharedListController([{id:'1',name:'문서'}]);const prompts=[];found.setDialog(options=>{prompts.push(options);return Promise.resolve(true);});await found.api.handleClick({dataset:{action:'confirm_list'}});
 assert.equal(prompts.length,1);assert.equal(prompts[0].title,'맞는 문서가 없는 것으로 확정할까요?');assert.doesNotMatch(prompts[0].html,/input/);assert.equal(found.calls.find(call=>call.body?.action==='confirm_list').body.reason,'맞는 문서 없음 · 0개 선택');
 const cancelled=sharedListController([{id:'1'}]);cancelled.setDialog(()=>Promise.resolve(false));await cancelled.api.handleClick({dataset:{action:'confirm_list'}});assert.equal(cancelled.calls.length,0);
 const legacy=sharedListController([],false);await assert.rejects(legacy.api.handleClick({dataset:{action:'confirm_list'}}),/빈 목록의 완료 정책/);assert.equal(legacy.calls.length,0);
});


test('shared search failure without result scope uses the known function and never displays stale rows',()=>{
 const h=sharedRuntimeFixture();h.snapshot.state.run.jobs.j={status:'failed',result:{result_kind:'structured',summary:'조회 실패',error:{code:'request_failed',message:'요청 실패'}}};
 const out=h.panel();assert.match(out,/Confluence에서 결과를 받지 못했습니다/);assert.match(out,/지난 회차 목록이나 이전 결과는 보여주지 않습니다/);assert.doesNotMatch(out,/ew-list-table|data-action="confirm_list"/);
 const legacy=html('workResultHTML({result_block:"list_confirm"},saved)',{saved:h.snapshot.state.run.jobs.j});assert.match(legacy,/조회 결과를 확인하지 못했습니다/);assert.doesNotMatch(legacy,/Confluence에서/);
});
test('finished run separates confirmed partial count and keeps a partial stage badge with zero remaining work',()=>{
 const h=sharedRuntimeFixture(),runState=h.snapshot.state.run;h.snapshot.selection.tab='run_details';
 runState.status='completed';runState.definition.nodes={p:{id:'p',type:'p'},t:{id:'t',type:'t',parent:'p',name:'문서 확인'},j:{id:'j',type:'j',parent:'t',name:'문서 찾기',mode:'tool'},next:{id:'next',type:'j',parent:'t',name:'후속 확인',mode:'human'},skip:{id:'skip',type:'j',parent:'t',name:'적용 제외'}};
 runState.jobs={j:{status:'partial',partial_confirmed:true},next:{status:'completed'},skip:{status:'excluded'}};runState.progress={completed:1,total:2,confirmed_partial:1,remaining:0};
 let out=h.overview();assert.match(out,/완료 1 · 부분 결과 확정 1 · 남은 작업 0/);assert.match(out,/<h3><button type="button" data-action="stage_open" data-node-id="t" class="ew-text">문서 확인<\/button><\/h3><span class="ew-status" data-status="partial">/);assert.match(out,/data-status="partial"[^>]*>[\s\S]*문서 찾기/);
 delete runState.progress.confirmed_partial;delete runState.progress.excluded;delete runState.progress.remaining;out=h.overview();assert.match(out,/남은 작업 0/);
 runState.status='open';runState.jobs.j.partial_confirmed=false;out=h.overview();assert.match(out,/남은 작업 1/);assert.doesNotMatch(out,/부분 결과 확정 1/);assert.match(out,/<h3><button type="button" data-action="stage_open" data-node-id="t" class="ew-text">문서 확인<\/button><\/h3><span class="ew-status" data-status="in_progress">/);
});


test('run editors can accept a shared version even when another person has claimed the displayed job',()=>{
 const h=sharedRuntimeFixture();h.snapshot.state.run.jobs.j={can_execute:false,permission_reason:'task_claimed',claim_actor:'another-user'};
 assert.match(h.panel(),/data-action="shared_accept_version"/);assert.doesNotMatch(h.panel(),/data-action="execute"/);
 h.snapshot.state.operations.shared_tool_access.j.can_accept_version=false;assert.doesNotMatch(h.panel(),/data-action="shared_accept_version"/);
});

function stageRuntimeFixture(){
 const judgments=[{id:'yes',label:'승인',status:'completed'},{id:'conditional',label:'조건부 승인',status:'completed'},{id:'no',label:'미승인',status:'failed'}];
 const nodes={p:{id:'p',type:'p'},t:{id:'t',type:'t',parent:'p',name:'1차 점검'},h:{id:'h',type:'j',parent:'t',name:'직접 확인',mode:'human',result_block:'human_confirm',judgments},a:{id:'a',type:'j',parent:'t',name:'실제 도구',mode:'tool',human_confirmation:false,result_block:'values',tool_reference:{tool_id:'native',function:'read',content_hash:'synthetic'}},other:{id:'other',type:'j',parent:'p',name:'다른 단계 작업',mode:'human'}};
 const state={ok:true,capabilities:{actor_id:'actor'},workflow:{id:'w',name:'배포 산출물 점검'},run:{id:'r',workflow_id:'w',status:'open',revision:8,name:'10.27 배포 회차',definition:{name:'배포 산출물 점검',nodes},jobs:{h:{status:'ready',can_decide:true,can_execute:true},a:{status:'ready',can_execute:true}},attempts:[]},operations:{},ui_state:{revision:0,state:{}}};
 const h=controller();h.api.setState(state);h.api.setSelection({mode:'work',workflow_id:'w',run_id:'r',job_id:'',tab:'overview',stage_id:'t'});
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true});
 return {...h,state,mutations:()=>h.calls.filter(call=>['human_confirm','decide','execute_job'].includes(call.body?.action))};
}

test('stage and job execution buttons use the current tool of a preserved run', () => {
 const {state} = stageRuntimeFixture();
 const job = state.run.definition.nodes.a;
 delete job.tool_reference;
 job.shared_tool_id = 'managed-read';
 const tool = {id:job.shared_tool_id, version:1, state:'available', can_use:true};
 const access = {can_use:true, current_tool:tool};
 state.run.shared_tools = [{id:tool.id, version:tool.version}];
 state.operations = {shared_tools:[], shared_tool_access:{a:access}};

 function assertButtonsEnabled(expected) {
  const body = html('workStageHTML(state, {}, state.run.definition.nodes.t).body', {state});
  for (const action of ['stage_execute', 'execute_scope']) {
   const button = body.match(new RegExp('<button\\b[^>]*data-action="' + action + '"[^>]*>'));
   assert.ok(button, action);
   assert.equal(!/\sdisabled\b/.test(button[0]), expected, action);
  }
 }

 assertButtonsEnabled(true);
 delete access.current_tool;
 assertButtonsEnabled(false);
 state.operations.shared_tools = [tool];
 assertButtonsEnabled(true);
 access.current_tool = {...tool, version:2};
 assertButtonsEnabled(false);
 access.current_tool = {...tool, state:'unavailable', can_use:false};
 assertButtonsEnabled(false);
 access.current_tool = tool;
 access.can_use = false;
 assertButtonsEnabled(false);
});

test('centered stage separates the published breadcrumb, stage title and actual run scope from the shared toolbar',()=>{
 const {state}=stageRuntimeFixture(),stage=state.run.definition.nodes.t;
 state.run.system_id='EMS';state.run.factory_id='f';state.factories=[{id:'f',name:'운영 공장'}];
 const render=(selection={})=>html('workStageHTML(state,selection,stage).body',{state,stage,selection});
 let body=render();
 assert.match(body,/data-action="stage_back">배포 산출물 점검<\/button>/);
 assert.match(body,/<span aria-current="page">1차 점검<\/span>/);assert.match(body,/<h2>1차 점검<\/h2>/);
 assert.match(body,/<p class="ew-center-scope">10.27 배포 회차 · 운영 공장 · EMS<\/p>/);
 assert.deepEqual([...body.matchAll(/data-action="stage_tab" data-tab="([^"]+)" aria-pressed="([^"]+)">([^<]+)</g)].map(m=>m.slice(1,4)),[['work','true','업무 내용'],['log','false','실행 기록'],['rules','false','판정 기준']]);
 assert.doesNotMatch(body,/업무절차|직접 시작|자동실행 예약 없음|수시|ew-panel-header|close_panel/);
 delete state.run.name;body=render();assert.match(body,/<p class="ew-center-scope">운영 공장 · EMS<\/p>/);assert.doesNotMatch(body,/회차|ew-stage-context/);
 state.run.name='접근 권한 신청 A';assert.match(render({stage_tab:'rules'}),/<p class="ew-center-scope">접근 권한 신청 A · 운영 공장 · EMS<\/p>/);
});

test('stage rows use Jobs, preserve configured judgment meaning and distinguish failed execution',()=>{
 const {state}=stageRuntimeFixture();state.run.jobs.a={status:'failed',result:{items:[{id:'CR-1',name:'도구의 내부 항목'}]}};
 const rows=html('workStageRows(state,state.run.definition.nodes.t)',{state});assert.equal(rows.length,2);assert.equal(rows.find(row=>row.node.id==='a').label,'실행 실패');assert.equal(rows.find(row=>row.node.id==='a').decision,null);
 // Theme step 1 (2026-11-20): a failed run is red like any other failure, not grey like 실행 필요.
 assert.equal(rows.find(row=>row.node.id==='a').tone,'bad');
 state.run.jobs.h={status:'completed',decisions:{job:{id:10,verdict:'completed',note:'검토 근거\n선택한 판정: 조건부 승인 (conditional)',actor_id:'actor'}}};
 const decision=html('workStageDecision(state.run.definition.nodes.h,state.run.jobs.h,state.run.definition)',{state});assert.equal(decision.label,'조건부 승인');assert.equal(decision.judgment_id,'conditional');assert.equal(decision.note,'검토 근거');
 const previous={snapshot:{job:{judgments:[{id:'old',label:'이전 정의',status:'completed'}]}}};
 state.run.jobs.h.decisions.job.note='\n선택한 판정: 이전 정의 (old)';assert.equal(html('workStageDecision(state.run.definition.nodes.h,state.run.jobs.h,state.run.definition,previous)',{state,previous}).label,'이전 정의');
});

test('stage actions mutate the exact row Job using existing execution and judgment contracts',async()=>{
 let h=stageRuntimeFixture();await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.equal(h.mutations().length,1);assert.equal(h.mutations()[0].body.action,'execute_job');assert.equal(h.mutations()[0].body.job_id,'a');assert.equal(h.mutations()[0].body.expected_revision,8);
 h=stageRuntimeFixture();await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'conditional',verdict:'completed'}});
 assert.equal(h.mutations().length,1);assert.equal(h.mutations()[0].body.action,'human_confirm');assert.equal(h.mutations()[0].body.judgment_id,'conditional');assert.equal(h.mutations()[0].body.verdict,'completed');
});

test('2026-11-02 an unconnected tool job shows a reason and disables its run and the whole stage run',async()=>{
 const connected=stageRuntimeFixture(),connectedStage=html('workStageHTML(state,{stage_tab:"work"},stage)',{state:connected.state,stage:connected.state.run.definition.nodes.t});
 assert.doesNotMatch(connectedStage.body,/도구 연결 필요|data-tool-connection-required/);assert.match(connectedStage.body,/data-action="execute_scope"[^>]*aria-label="1차 점검 단계 실행">/);
 const h=stageRuntimeFixture(),nodes=h.state.run.definition.nodes;delete nodes.a.tool_reference;
 h.state.run.jobs.a={status:'pending',can_execute:false,permission_reason:'tool_connection_required',tool_connection_required:true};h.api.setState(h.state);
 const rendered=html('workStageHTML(state,{stage_tab:"work"},stage)',{state:h.state,stage:nodes.t});
 assert.match(rendered.body,/data-tool-connection-required>도구 연결 필요 1개 · 워크스페이스에서 연결해 다시 게시해야 실행됩니다</);
 assert.match(rendered.body,/aria-label="1차 점검 단계 실행" disabled data-own-disabled="true" title="도구가 연결되지 않은 작업이 있어 이 단계를 실행할 수 없습니다"/);
 assert.match(rendered.body,/aria-label="실제 도구 실행" data-mutation disabled data-own-disabled="true" data-run-blocked title="도구가 연결되지 않아 실행할 수 없습니다"/);
 assert.match(rendered.body,/도구 연결 필요/);
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});assert.equal(h.mutations().length,0);
 // A shared tool or a contract counts as connected; only a missing tool blocks.
 for(const connection of [{shared_tool_id:'managed-read'},{tool_contract_id:'contract'},{execution:{reference:{tool_id:'native',function:'read'}}}])
  assert.equal(html('workToolConnectionRequired(node)',{node:{mode:'tool',...connection}}),false);
 assert.equal(html('workToolConnectionRequired(node)',{node:{mode:'tool',result_block:'change_request'}}),false);
 assert.equal(html('workToolConnectionRequired(node)',{node:{mode:'human'}}),false);
});

test('2026-11-03 a run that cannot start keeps the text-button shape while running keeps the designed muted box',()=>{
 // Figma 업무 · 운영 and the stage mocks draw only 실행 중 as the muted box; the user asked that a blocked 실행 match 다시 실행.
 const css=require('node:fs').readFileSync(require('node:path').join(__dirname,'../branding/ees/ui/ees-work-launcher.css'),'utf8');
 assert.match(css,/#ees-work-panel\.ew-vd \.ew-vd-run:disabled\{color:var\(--ees-text-tertiary\);background:var\(--ees-surface-muted\);cursor:default\}/);
 assert.match(css,/#ees-work-panel\.ew-vd \.ew-vd-run\[data-run-blocked\]:disabled\{background:transparent\}/);
 const runButton=job=>{const h=stageRuntimeFixture(),nodes=h.state.run.definition.nodes;job(h.state.run);const body=html('workStageHTML(state,{stage_tab:"work"},stage)',{state:h.state,stage:nodes.t}).body;return body.match(/<button type="button" class="ew-vd-run"[^>]*data-job-id="a"[^>]*>/)?.[0] || '';};
 const running=runButton(run=>{run.jobs.a={status:'running',can_execute:false};});
 assert.match(running,/ disabled /);assert.doesNotMatch(running,/data-run-blocked/);
 const claimed=runButton(run=>{run.jobs.a={status:'ready',can_execute:false,permission_reason:'task_claimed'};});
 assert.match(claimed,/ disabled data-own-disabled="true" data-run-blocked>/);
 const viewer=runButton(run=>{run.can_write=false;});
 assert.match(viewer,/ disabled data-own-disabled="true" data-run-blocked>/);
 const ready=runButton(()=>{});
 assert.doesNotMatch(ready,/disabled|data-run-blocked/);
});

test('2026-11-02 run details keep stage and procedure runs disabled across busy updates while a tool is unconnected',()=>{
 // setBusy() re-enables every data-mutation control unless data-own-disabled="true" marks it.
 const h=sharedRuntimeFixture(),runState=h.snapshot.state.run;h.snapshot.selection.tab='run_details';
 runState.definition.nodes={p:{id:'p',type:'p',name:'절차'},t:{id:'t',type:'t',parent:'p',name:'문서 확인'},j:{id:'j',type:'j',parent:'t',name:'문서 찾기',mode:'tool',shared_tool_id:'shared',inputs:[],result_block:'list_confirm'},missing:{id:'missing',type:'j',parent:'t',name:'설정 조회',mode:'tool'}};
 runState.jobs={j:{can_execute:true},missing:{status:'pending',can_execute:false,permission_reason:'tool_connection_required'}};
 let out=h.overview();
 for(const id of ['t','p'])assert.match(out,new RegExp(`data-action="execute_scope" data-node-id="${id}" data-mutation class="ew-secondary" disabled data-own-disabled="true" title="도구가 연결되지 않은 작업이 있어 실행할 수 없습니다"`),id);
 runState.jobs.missing.status='excluded';out=h.overview();
 assert.match(out,/data-action="execute_scope" data-node-id="t" data-mutation class="ew-secondary">/);assert.doesNotMatch(out,/data-action="execute_scope"[^>]*disabled/);
});

test('2026-11-02 operations overview lists only reservations made earlier, without an execution-mode row',()=>{
 const h=stagePreviewFixture();h.state.workflow.published.mode='periodic';
 h.state.operations={schedules:[{id:'s1',workflow_id:h.state.workflow.id,enabled:true},{id:'s2',workflow_id:h.state.workflow.id,enabled:false},{id:'s3',workflow_id:'other',enabled:true}]};
 const out=html('workOperationOverviewHTML(state,{})',{state:h.state});
 assert.match(out,/<dt>자동 실행<\/dt><dd>이전에 맡긴 예약 1개<\/dd><dt>적용 대상<\/dt>/);assert.doesNotMatch(out,/<dt>주기<\/dt>|예약 없음/);
 const cycle=html('workCycleBarHTML(run,definition)',{run:{mode:'emergency',name:'14:20 장애',created_at:'2026-11-02T00:00:00Z'},definition:{nodes:{}}});
 assert.match(cycle,/<span>진행 건<\/span>/);assert.match(cycle,/다른 진행 건/);assert.doesNotMatch(cycle,/진행 중인 대응|다른 대응|이번 회차|지난 회차/);
});

test('stage view-only actions never execute tools or change judgments',async()=>{
 const h=stageRuntimeFixture();
 for(const dataset of [{action:'stage_evidence',jobId:'a'},{action:'stage_tool',jobId:'a',toolKey:'current'},{action:'stage_tab',tab:'log'},{action:'stage_approved'},{action:'stage_back'}])await h.api.handleClick({dataset});
 assert.equal(h.mutations().length,0);assert.equal(h.api.snapshot().selection.stage_overview,true);
});

test('forged, stale-policy, automatic, readonly and dirty-input stage actions do not mutate',async()=>{
 for(const kind of ['foreign','automatic','mismatched','readonly','closed','denied','dirty']){
  const h=stageRuntimeFixture();let dataset={action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'};
  if(kind==='foreign')dataset.jobId='other';if(kind==='automatic')dataset.jobId='a';if(kind==='mismatched')dataset.verdict='failed';if(kind==='readonly')h.state.run.can_write=false;if(kind==='closed')h.state.run.status='completed';if(kind==='denied')h.state.run.jobs.h.can_decide=false;if(kind==='dirty')h.view.readInputs=()=>({dirty:true});
  await h.api.handleClick({dataset});assert.equal(h.mutations().length,0,kind);
 }
});

test('legacy human choices retain the existing verdict API and never invent a conditional policy',async()=>{
 const h=stageRuntimeFixture();delete h.state.run.definition.nodes.h.judgments;
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',verdict:'completed'}});
 assert.equal(h.mutations().length,1);assert.equal(h.mutations()[0].body.verdict,'completed');assert.equal(h.mutations()[0].body.judgment_id,undefined);
});

test('execution history keeps the picker available for running and access-masked attempts',()=>{
 const {state}=stageRuntimeFixture();state.run.jobs.a={status:'running',attempt_id:'a2'};
 state.run.attempts=[{id:'a1',job_id:'a',number:1,status:'succeeded',evidence_access:'requires_current_source_access',snapshot:{arguments:{private:'hidden'}},result:{summary:'hidden-output'}},{id:'a2',job_id:'a',number:2,status:'running'}];
 for(const id of ['a1','a2']){const out=html('workStageHTML(state,{stage_evidence:"a",stage_attempts:{a:id}},state.run.definition.nodes.t).body',{state,id});assert.match(out,/data-stage-attempt/);assert.doesNotMatch(out,/hidden-output|>hidden</);}
});

test('prior tool evidence never combines a newer job judgment with the selected attempt',()=>{
 const {state}=stageRuntimeFixture();state.run.definition.nodes.a.judgments=state.run.definition.nodes.h.judgments;
 state.run.attempts=[{id:'a1',job_id:'a',number:1,status:'succeeded',result:{summary:'first'}},{id:'a2',job_id:'a',number:2,status:'succeeded',result:{summary:'second'}}];
 const old={item_id:'job',attempt_id:'a1',verdict:'failed',note:'\n선택한 판정: 미승인 (no)'},current={item_id:'job',attempt_id:'a2',verdict:'completed',note:'\n선택한 판정: 승인 (yes)'};
 state.run.jobs.a={status:'completed',attempt_id:'a2',decisions:{job:current},decision_history:[old,current]};
 const out=html('workStageHTML(state,{stage_evidence:"a",stage_attempts:{a:"a1"}},state.run.definition.nodes.t).body',{state});
 assert.match(out,/당시 작업 판정 · 미승인/);assert.doesNotMatch(out,/작업 판정 · 승인/);
});

test('stage log does not promote result item decisions to whole Job judgments',()=>{
 const {state}=stageRuntimeFixture();state.run.jobs.a.decision_history=[{item_id:'inner-item',verdict:'failed',actor_id:'item-actor',note:'inner item result'}];
 const out=html('workStageHTML(state,{stage_tab:"log"},state.run.definition.nodes.t).body',{state});assert.doesNotMatch(out,/item-actor|inner item result/);
});

test('queued stage execution is visible and prevents a second stage start',()=>{
 const {state}=stageRuntimeFixture();state.operations.scope_runs=[{id:'scope1',run_id:'r',node_id:'t',status:'queued'}];
 const out=html('workStageHTML(state,{},state.run.definition.nodes.t).body',{state});
 assert.match(out,/data-action="execute_scope"[^>]* disabled/);assert.match(out,/실행 대기/);
});

test('history link selects only an attempt belonging to its actual row and opens that evidence',async()=>{
 const h=stageRuntimeFixture();h.state.run.attempts=[{id:'a1',job_id:'a',number:1,status:'succeeded'},{id:'h1',job_id:'h',number:1,status:'succeeded'}];
 await h.api.handleClick({dataset:{action:'stage_tab',tab:'log'}});await h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a',attemptId:'h1'}});
 assert.equal(h.api.snapshot().selection.stage_tab,'log');
 await h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a',attemptId:'a1'}});
 const selection=h.api.snapshot().selection;assert.equal(selection.stage_tab,'work');assert.equal(selection.stage_evidence,'a');assert.equal(selection.stage_attempts.a,'a1');assert.equal(h.mutations().length,0);
});

test('explicit run overview and closed-run history remain reachable after entering a singleton stage',async()=>{
 const h=stageRuntimeFixture();await h.api.handleClick({dataset:{action:'overview'}});
 const selection=h.api.snapshot().selection;assert.equal(selection.stage_overview,true);assert.equal(selection.stage_id,'');
 assert.equal(html('workStageTarget(state,selection)',{state:h.state,selection}),null);
 h.state.run.status='completed';assert.equal(html('workStageTarget(state,{mode:"work",tab:"overview"})',{state:h.state}),null);
 assert.equal(html('workStageTarget(state,{mode:"work",tab:"overview",stage_id:"t"}).id',{state:h.state}),'t');
});

// 2026-11-18 first-user review: a run of human checks showed the sentence about running tool and AI work.
test('run details explain tool and AI execution only when such work can be run',()=>{
 const h=sharedRuntimeFixture(),runState=h.snapshot.state.run;h.snapshot.selection.tab='run_details';
 runState.definition.nodes={p:{id:'p',type:'p',name:'절차'},t:{id:'t',type:'t',parent:'p',name:'점검'},j:{id:'j',type:'j',parent:'t',name:'사람 확인',mode:'human',inputs:[],result_block:'human_confirm'}};
 runState.jobs={j:{status:'ready'}};
 let out=h.overview();
 assert.doesNotMatch(out,/ew-scope-execution|도구·AI 작업을 진행합니다|data-action="execute_scope"/);
 runState.definition.nodes.j={id:'j',type:'j',parent:'t',name:'문서 찾기',mode:'tool',shared_tool_id:'shared',inputs:[],result_block:'list_confirm'};runState.jobs={j:{can_execute:true}};out=h.overview();
 assert.match(out,/class="ew-scope-execution">.*data-action="execute_scope".*도구·AI 작업을 진행합니다/);
});

// 2026-11-18 first-user review: the log printed the account id of whoever judged a job.
test('stage log names the person who judged a job the way the judgment record does',()=>{
 const {state}=stageRuntimeFixture();state.people=[{id:'actor',name:'김담당',label:'김담당',value:{kind:'user',id:'actor'}}];
 state.run.jobs.h.decision_history=[{item_id:'job',judgment_id:'yes',verdict:'completed',actor_id:'actor',created_at:'2026-10-27T14:21:00Z'}];
 const named=html('workStageHTML(state,{stage_tab:"log"},state.run.definition.nodes.t).body',{state});
 assert.match(named,/직접 확인 · [^<·]+ · 김담당</);assert.doesNotMatch(named,/· actor</);
 state.people=[];
 assert.match(html('workStageHTML(state,{stage_tab:"log"},state.run.definition.nodes.t).body',{state}),/직접 확인 · [^<·]+ · actor</);
});

// Before a run exists the stage button only starts one. "실행" is kept for tool work in a started run.
test('stage button reads 시작 until a run exists and 지금 실행 afterwards',()=>{
 const started=stageRuntimeFixture().state,nodes=started.run.definition.nodes;
 const running=html('workStageHTML(state,{stage_tab:"work"},stage).body',{state:started,stage:nodes.t});
 assert.match(running,/data-action="execute_scope"[^>]*aria-label="1차 점검 단계 실행"[^>]*>(?:<svg[\s\S]*?<\/svg>)?<span>지금 실행<\/span>/);
 const idle={...started,run:null,workflow:{...started.workflow,published_version:1,published:{name:'배포 산출물 점검',nodes}}};
 const waiting=html('workStageHTML(state,{stage_tab:"work"},stage).body',{state:idle,stage:nodes.t});
 assert.match(waiting,/data-action="stage_start"[^>]*aria-label="1차 점검 단계 시작"[^>]*>(?:<svg[\s\S]*?<\/svg>)?<span>시작<\/span>/);assert.doesNotMatch(waiting,/지금 실행/);
});

test('stage log keeps its compact time column and retains the full timestamp accessibly',()=>{
 const {state}=stageRuntimeFixture();state.run.attempts=[{id:'a1',job_id:'a',number:1,status:'succeeded',created_at:'2026-10-27T14:20:00Z'}];
 const out=html('workStageHTML(state,{stage_tab:"log"},state.run.definition.nodes.t).body',{state});
 assert.match(out,/<time datetime="2026-10-27T14:20:00Z" title="[^"]*2026[^\"]*" aria-label="[^"]+">\d{2}:\d{2}<\/time>/);
});

function stagePreviewFixture(){
 const h=stageRuntimeFixture();h.state.workflow.published_version=3;h.state.workflow.system_id='EMS';h.state.workflow.published=h.state.run.definition;h.state.workflow.draft={nodes:{secret:{id:'secret',type:'t',name:'비공개 초안'}}};delete h.state.run;
 h.api.setSelection({run_id:'',stage_id:'',stage_overview:false});return h;
}
test('operations31 preview reads only published stages without a run or factory',async()=>{
 const h=stagePreviewFixture();
 assert.equal(html('workStageTarget(state,selection)',{state:h.state,selection:h.api.snapshot().selection}),null);
 const overview=html('workOperationOverviewHTML(state,{})',{state:h.state});assert.match(overview,/업무 단계/);assert.match(overview,/작업 2개/);assert.match(overview,/전체 공장 · EMS/);assert.doesNotMatch(overview,/비공개 초안|진행 건 시작|ew-adhoc-start/);
 await h.api.handleClick({dataset:{action:'stage_open',nodeId:'secret'}});assert.equal(h.api.snapshot().selection.stage_id,'');
 await h.api.handleClick({dataset:{action:'stage_open',nodeId:'t'}});assert.equal(h.api.snapshot().selection.stage_id,'t');
 for(const action of ['stage_evidence','stage_tab','stage_decide','stage_execute'])await h.api.handleClick({dataset:{action,jobId:'h',tab:'rules',verdict:'completed',judgmentId:'yes'}});
 await h.api.handleClick({dataset:{action:'execute_scope',nodeId:'t'}});
 assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);
 const body=html('workStageHTML(state,selection,workPublishedDefinition(state).nodes.t).body',{state:h.state,selection:h.api.snapshot().selection});assert.match(body,/판정 단어/);
});
function stageStartDialog(h){
 // The start form opens only for a procedure that asks something at the start.
 const root=Object.values(h.state.workflow?.published?.nodes || {}).find(node=>node.type==='p');if(root)root.inputs=[...(root.inputs || []),{id:'note',name:'시작 메모',type:'text',scope:'run'}];
 const pending=deferred(),options=[],listeners=new Map(),fields=[{name:'note',value:'입력한 근거',dataset:{inputType:'text'}}],groups=[{value:'ops-group'}];
 const form={querySelectorAll:selector=>selector==='[data-work-input]'?fields:selector==='[data-start-group]:checked'?groups:[]};
 const element={querySelector:selector=>selector==='#ees-work-start'?form:selector==='#ees-start-version'?{value:'3'}:null,querySelectorAll:selector=>selector==='[data-start-group]:checked'?groups:[],addEventListener:(kind,fn)=>listeners.set(kind,fn)};
 h.context.document.querySelector=selector=>selector==='#ees-work-dialog'?element:null;h.setDialog(value=>{options.push(value);return pending.promise;});
 return {pending,options,fields,groups,confirm(){listeners.get('click')?.({target:{closest:selector=>selector==='[data-dialog-confirm]'?{}:null}});pending.resolve(true);}};
}
test('preview execution opens preparation over the same stage and cancel creates no run',async()=>{
 const h=stagePreviewFixture(),dialog=stageStartDialog(h);await h.api.handleClick({dataset:{action:'stage_open',nodeId:'t'}});
 const body=html('workStageHTML(state,selection,workPublishedDefinition(state).nodes.t).body',{state:h.state,selection:h.api.snapshot().selection});assert.match(body,/data-action="stage_start"/);assert.doesNotMatch(body,/data-action="execute_scope"|data-action="stage_decide"/);assert.ok([...body.matchAll(/<button[^>]*data-action="stage_start"[^>]*>/g)].every(match=>!match[0].includes('aria-haspopup')&&!match[0].includes('aria-controls')));const emptyRecord=html('workStageHTML(state,{stage_id:"t",stage_evidence:"h"},workPublishedDefinition(state).nodes.t).body',{state:h.state});assert.match(emptyRecord,/title="읽기 전용 판정 사유"/);assert.doesNotMatch(emptyRecord,/title="저장된 판정 사유"/);
 await h.api.handleClick({dataset:{action:'stage_start',jobId:'other'}});assert.equal(dialog.options.length,0);
 const action=h.api.handleClick({dataset:{action:'stage_start',nodeId:'t'}});assert.equal(dialog.options[0].title,'실행 준비');assert.equal(h.api.snapshot().selection.tab,'overview');assert.equal(h.api.snapshot().selection.stage_id,'t');dialog.pending.resolve(false);await action;
 assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);assert.equal(h.api.snapshot().selection.stage_id,'t');
});
test('unpublished workflows never expose author drafts to operations preview',()=>{
 const h=stagePreviewFixture();delete h.state.workflow.published;delete h.state.workflow.published_version;
 assert.deepEqual(JSON.parse(JSON.stringify(html('workPublishedDefinition(state)',{state:h.state}))),{});
 assert.equal(html('workStageTarget(state,{stage_id:"secret"})',{state:h.state}),null);
});
test('unpublished operation entry and saved start tabs keep the new empty overview for every mode',()=>{
 for(const mode of ['on_demand','periodic','emergency'])for(const tab of ['overview','start','run_details']){
  const h=sharedRuntimeFixture();delete h.snapshot.state.run;
  h.snapshot.state.workflow={id:'w',name:'미게시 절차',mode,system_id:'EMS',can_manage:true,draft:{nodes:{secret:{id:'secret',type:'t',name:'초안 전용 단계'}}}};
  h.snapshot.selection={mode:'work',workflow_id:'w',job_id:'',stage_id:'secret',tab};
  const out=h.overview();assert.match(out,/ew-operation-overview/,mode+'/'+tab);assert.match(out,/게시되지 않은 업무 절차/);assert.doesNotMatch(out,/초안 전용 단계|새로 시작|진행 건 시작|ew-adhoc-start|data-action="(?:start_run|stage_start|stage_open|execute_scope)"/);
 }
});
test('operations overview shows no execution mode and uses the published name ahead of author draft metadata',()=>{
 const h=stagePreviewFixture();h.state.workflow.name='미게시 이름';h.state.workflow.mode='on_demand';
 for(const mode of ['periodic','emergency','on_demand',undefined]){
  h.state.workflow.published.mode=mode;const out=html('workOperationOverviewHTML(state,{})',{state:h.state});assert.doesNotMatch(out,/<dt>주기<\/dt>|예약 없음|수시|비상|자동 실행/);assert.match(out,/<dt>적용 대상<\/dt>/);assert.match(out,/<h2>배포 산출물 점검<\/h2>/);assert.doesNotMatch(out,/미게시 이름/);
  const stage=html('workStageHTML(state,{},workPublishedDefinition(state).nodes.t)',{state:h.state});assert.match(stage.body,/data-action="stage_back">배포 산출물 점검<\/button>/);assert.doesNotMatch(stage.body,/미게시 이름/);
 }
});
test('restored unpublished operations selections return to my work while author drafts and existing runs remain selected',async()=>{
 for(const mode of ['on_demand','periodic','emergency'])for(const tab of ['overview','start','run_details'])for(const target of ['unpublished','author','published','run']){
  const h=controller(),workflow={id:'w',system_id:'EMS',mode,published_version:target==='published'?1:null,draft:{name:'kept draft',nodes:{}}};
  const saved={mode:target==='author'?'author':'work',system_id:'EMS',workflow_id:'w',run_id:target==='run'?'r':'',job_id:'',stage_id:'old-stage',tab,start_inputs:{w:{note:'kept input'}}};
  const state={ok:true,capabilities:{actor_id:'a',can_author:true},systems:['EMS'],workflows:[workflow],runs:[],ui_state:{revision:1,state:{selection:saved}}};
  h.api.setRestored(false);h.setReply(call=>call.url.includes('workspace?')?{...state,workflow:new URL(call.url,'http://native.test').searchParams.get('workflow_id')?workflow:null,...(target==='run'?{run:{id:'r',workflow_id:'w',definition:{name:'fixed version',nodes:{}},jobs:{}}}:{})}:{ok:true});
  await h.api.refresh();const actual=h.api.snapshot();
  assert.equal(actual.selection.workflow_id,target==='unpublished'?'':'w',mode+'/'+tab+'/'+target);
  assert.equal(actual.selection.tab,target==='unpublished'?'overview':tab);
  assert.equal(actual.state.workflows[0].draft.name,'kept draft');assert.equal(actual.selection.start_inputs.w.note,'kept input');
  if(target==='unpublished'){assert.equal(actual.state.workflow,null);assert.equal(actual.selection.stage_id,'');}
  if(target==='run'){assert.equal(actual.selection.run_id,'r');assert.equal(actual.state.run.definition.name,'fixed version');}
  assert.equal(h.calls.some(call=>call.body),false);
 }
});
test('stale workflow actions are blocked in operations but drafts still open in authoring',async()=>{
 for(const mode of ['work','author'])for(const published of [false,true]){
  const h=controller(),workflow={id:'w',system_id:'EMS',published_version:published?1:null,draft:{name:'kept'}};
  const state={ok:true,capabilities:{actor_id:'a',can_author:true},systems:['EMS'],workflows:[workflow],workflow,runs:[]};
  h.api.setState(state);h.api.setSelection({mode,system_id:'EMS',workflow_id:'',run_id:'',tab:'overview'});
  h.setReply(call=>call.url.includes('workspace?')?state:{ok:true});
  await h.api.handleClick({dataset:{action:'workflow',workflowId:'w'}});
  assert.equal(h.api.snapshot().selection.workflow_id,mode==='author'||published?'w':'');
  if(mode==='work'&&!published)assert.equal(h.calls.length,0);
  assert.equal(h.calls.some(call=>call.body),false);
 }
});
test('all explicit start dialogs return to their selected stage without automatically executing it',async()=>{
 for(const mode of ['on_demand','periodic','emergency']){
  const h=stagePreviewFixture(),definition=h.state.workflow.published,dialog=stageStartDialog(h);definition.mode=mode;definition.execution_scope='factory';definition.nodes.t2={id:'t2',parent:'p',type:'t',name:'후속 단계'};
  h.api.setSelection({system_id:'EMS',factory_id:'factory',stage_id:'t2'});
  h.setReply(call=>{if(call.body?.action==='start_run'){h.state.run={id:'new-run',workflow_id:'w',factory_id:'factory',definition,status:'open',jobs:{},attempts:[],revision:1};return {ok:true,run:h.state.run};}return call.url.includes('workspace?')?h.state:{ok:true};});
  const action=h.api.handleClick({dataset:{action:'stage_start',nodeId:'t2'}});dialog.fields[0].value='확정 직전 입력';dialog.confirm();await action;
  const starts=h.calls.filter(call=>call.body?.action==='start_run');assert.equal(starts.length,1);assert.equal(starts[0].body.factory_id,'factory');assert.equal(starts[0].body.version,3);assert.equal(Object.hasOwn(starts[0].body,'sharing'),false);assert.deepEqual(starts[0].body.inputs,{note:'확정 직전 입력'},'2026-11-02: every start uses the start-input form');
  assert.equal(h.api.snapshot().selection.run_id,'new-run',mode);assert.equal(h.api.snapshot().selection.stage_id,'t2',mode);assert.equal(h.api.snapshot().selection.start_stage_id,'',mode);assert.equal(h.calls.filter(call=>['execute_scope','execute_job'].includes(call.body?.action)).length,0);
 }
});
test('unpublished and changed-account preparation never creates a run',async()=>{
 const unpublished=stagePreviewFixture(),blocked=stageStartDialog(unpublished);delete unpublished.state.workflow.published_version;delete unpublished.state.workflow.published;
 await unpublished.api.handleClick({dataset:{action:'start_run'}});assert.equal(blocked.options.length,0);assert.equal(unpublished.calls.length,0);
 const h=stagePreviewFixture(),dialog=stageStartDialog(h);h.api.setSelection({stage_id:'t'});const action=h.api.handleClick({dataset:{action:'stage_start',nodeId:'t'}});h.setAuth('different-account');dialog.confirm();await action;assert.equal(h.calls.filter(call=>call.body?.action==='start_run').length,0);
});
test('missing left factory and an active run show a notice without a second picker or start action',async()=>{
 for(const duplicate of [false,true]){
  const h=stagePreviewFixture(),dialog=stageStartDialog(h);h.state.workflow.published.execution_scope='factory';h.state.workflow.published.mode='on_demand';h.api.setSelection({stage_id:'t',factory_id:duplicate?'factory':''});if(duplicate)h.state.workflow_active_runs=[{id:'kept',workflow_id:h.state.workflow.id,factory_id:'factory',status:'open'}];
  const action=h.api.handleClick({dataset:{action:'stage_start',nodeId:'t'}});if(duplicate){await action;assert.equal(dialog.options.length,0);assert.equal(h.api.snapshot().selection.run_id,'kept');}else{assert.equal(dialog.options[0].readOnlyDetail,true);assert.doesNotMatch(dialog.options[0].html,/ees-work-start|ees-start-factory/);dialog.pending.resolve(false);await action;}assert.equal(h.calls.filter(call=>call.body?.action==='start_run').length,0);
 }
});
test('workflow entry resumes the selected unit for every category and uses published scope',async()=>{
 for(const scope of ['factory','system'])for(const category of ['ops','incident']){
  const h=stagePreviewFixture(),workflow=h.state.workflow;workflow.published.execution_scope=scope;workflow.published.category=category;
  workflow.execution_scope=scope==='factory'?'system':'factory';workflow.draft.execution_scope=workflow.execution_scope;
  h.state.workflows=[workflow];h.state.runs=[{id:'other-factory',workflow_id:'w',factory_id:'f2',status:'open'},{id:'closed',workflow_id:'w',factory_id:scope==='system'?'':'f1',status:'completed'},{id:'shared',workflow_id:'w',system_id:'EMS',factory_id:scope==='system'?'':'f1',owner:'another-user',status:'open'},{id:'other-workflow',workflow_id:'else',factory_id:'f1',status:'open'}];
  h.api.setSelection({mode:'work',system_id:'EMS',factory_id:'f1',stage_id:'old-stage',job_id:'old-job'});
  await h.api.handleClick({dataset:{action:'workflow',workflowId:'w'}});
  const selection=h.api.snapshot().selection;assert.equal(selection.run_id,'shared',scope+'/'+category);assert.equal(selection.stage_id,'');assert.equal(selection.job_id,'');assert.equal(selection.tab,'overview');
  assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0);
 }
});
test('legacy duplicate runs open a chooser and ordinary work cannot start another unit run',async()=>{
 for(const scope of ['factory','system']){
  const h=stagePreviewFixture(),workflow=h.state.workflow,dialog=stageStartDialog(h);workflow.published.execution_scope=scope;workflow.published.category='ops';delete workflow.published.mode;workflow.mode='emergency';workflow.category='incident';
  h.state.workflows=[workflow];h.state.runs=['first','second'].map(id=>({id,workflow_id:'w',system_id:'EMS',factory_id:scope==='system'?'':'f1',status:'open',progress:{completed:2,total:3}}));
  h.state.workflow_active_runs=[...h.state.runs,{id:'elsewhere',workflow_id:'w',system_id:'EMS',factory_id:'f2',status:'open'}];h.api.setSelection({mode:'work',system_id:'EMS',factory_id:'f1'});
  await h.api.handleClick({dataset:{action:'workflow',workflowId:'w'}});const selection=h.api.snapshot().selection;assert.equal(selection.tab,'active_runs');assert.equal(selection.run_id,'');
  const out=html('workActiveRunsHTML(state,selection)',{state:h.state,selection});assert.match(out,/data-run-id="first"/);assert.match(out,/data-run-id="second"/);assert.doesNotMatch(out,/elsewhere|data-action="start_run"/);assert.match(out,/완료 2\/3/);
  await h.api.handleClick({dataset:{action:'start_run'}});assert.equal(dialog.options.length,0);assert.equal(h.api.snapshot().selection.tab,'active_runs');assert.equal(h.calls.filter(call=>call.body?.action==='start_run').length,0);
  for(const mode of [null,'periodic','emergency']){workflow.published.category=mode?'ops':'incident';workflow.published.mode=mode;assert.match(html('workActiveRunsHTML(state,selection)',{state:h.state,selection}),/data-action="start_run"/);}
 }
});
test('a system common start ignores the left factory and never sends remembered sharing',async()=>{
 const h=stagePreviewFixture(),dialog=stageStartDialog(h);h.state.workflow.published.execution_scope='system';h.state.runs=[{id:'elsewhere',workflow_id:'w',factory_id:'f1',status:'open'}];
 h.api.setSelection({system_id:'EMS',factory_id:'f1',start_groups:{w:['old-group']}});
 h.setReply(call=>call.body?.action==='start_run'?{ok:true,run_id:'system-run'}:call.url.includes('workspace?')?h.state:{ok:true});
 const action=h.api.handleClick({dataset:{action:'start_run'}});dialog.confirm();await action;
 const start=h.calls.find(call=>call.body?.action==='start_run');assert.equal(start.body.factory_id,'');assert.equal(Object.hasOwn(start.body,'sharing'),false);assert.equal(h.api.snapshot().selection.start_groups,undefined);
});
function typeStageNote(h,value,readonly=false){const target={dataset:{jobId:'h'},value,readOnly:readonly,closest:selector=>selector==='[data-ees-work]'?{}:null,matches:selector=>selector==='[data-stage-note]'};h.api.handleEvent({type:'input',target});}
test('stage reason is an unsaved local draft and persists only with its explicit judgment',async()=>{
 const h=stageRuntimeFixture(),pendingTimers=h.timers.size;typeStageNote(h,'배치 변경 확인');assert.equal(h.calls.length,0);assert.equal(h.timers.size,pendingTimers);assert.equal(h.api.snapshot().selection.stage_notes,undefined);
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'conditional',verdict:'completed'}});
 assert.equal(h.mutations()[0].body.note,'배치 변경 확인');
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});assert.equal(h.mutations()[1].body.note,undefined);
});
test('failed judgment retains its reason while changed attempts and accounts cannot reuse that draft',async()=>{
 const h=stageRuntimeFixture();typeStageNote(h,'실패 뒤 보존');let fail=true;
 h.setReply(call=>call.body?.action==='human_confirm'&&fail?{ok:false,error:{message:'revision conflict'}}:call.url.includes('workspace?')?h.state:{ok:true});
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});fail=false;
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});assert.equal(h.mutations()[1].body.note,'실패 뒤 보존');
 typeStageNote(h,'이전 근거 초안');h.state.run.jobs.h.attempt_id='new-attempt';h.state.run.jobs.h.result_revision=2;
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});assert.equal(h.mutations()[2].body.note,undefined);
 typeStageNote(h,'이전 계정 초안');h.api.reset();h.api.setState(h.state);h.api.setSelection({mode:'work',workflow_id:'w',run_id:'r',job_id:'',tab:'overview',stage_id:'t'});
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});assert.equal(h.mutations()[3].body.note,undefined);
});
test('saved human reasons render read-only and retain previous judgments as history',()=>{
 const {state}=stageRuntimeFixture();state.run.jobs.h={status:'completed',decisions:{job:{item_id:'job',verdict:'completed',note:'기존 사유\n선택한 판정: 승인 (yes)',actor_id:'actor'}}};
 const body=html('workStageHTML(state,{stage_evidence:"h"},state.run.definition.nodes.t).body',{state});assert.match(body,/승인 선택/);assert.match(body,/<textarea[^>]*data-stage-note[^>]* readonly aria-readonly="true"[^>]*>기존 사유<\/textarea>/);assert.doesNotMatch(body,/선택한 판정: 승인/);
});
test('reason input reserves the existing judgment marker and rejects oversize text without truncating or saving it',async()=>{
 const h=stageRuntimeFixture(),definition=h.state.run.definition,node=definition.nodes.h,marker='\n선택한 판정: 조건부 승인 (conditional)',limit=4000-Array.from(marker).length;
 const body=html('workStageHTML(state,{stage_evidence:"h"},state.run.definition.nodes.t).body',{state:h.state});assert.match(body,new RegExp('maxlength="'+limit+'"'));
 typeStageNote(h,'가'.repeat(limit+1));await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'conditional',verdict:'completed'}});
 assert.equal(h.mutations().length,0);assert.match(h.api.snapshot().error,/아직 저장하지 않았습니다/);
 typeStageNote(h,'가'.repeat(limit));await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'conditional',verdict:'completed'}});assert.equal(h.mutations()[0].body.note,'가'.repeat(limit));
});
test('folding completed work keeps the failed execution visible and never submits another verdict',async()=>{
 const h=stageRuntimeFixture();h.state.run.jobs.a={status:'failed'};h.state.run.jobs.h={status:'completed',decisions:{job:{item_id:'job',verdict:'completed',note:'확인 근거\n선택한 판정: 승인 (yes)',actor_id:'actor'}}};
 const render=()=>html('workStageHTML(state,selection,state.run.definition.nodes.t).body',{state:h.state,selection:h.api.snapshot().selection});
 let out=render();assert.match(out,/data-action="stage_approved" aria-expanded="true"/);assert.match(out,/data-stage-job="h"/);assert.match(out,/실행 실패/);
 await h.api.handleClick({dataset:{action:'stage_evidence',jobId:'h'}});out=render();assert.match(out,/stage-evidence-h/);assert.match(out,/확인 근거/);
 await h.api.handleClick({dataset:{action:'stage_approved'}});out=render();assert.equal(h.api.snapshot().selection.stage_evidence,'');assert.match(out,/data-action="stage_approved" aria-expanded="false"/);assert.doesNotMatch(out,/data-stage-job="h"/);assert.match(out,/data-stage-job="a"/);
 await h.api.handleClick({dataset:{action:'stage_approved'}});out=render();assert.match(out,/data-action="stage_approved" aria-expanded="true"/);assert.match(out,/data-stage-job="h"/);assert.equal(h.mutations().length,0);
});
test('published job order survives changing decisions, with successful execution distinct from approval',()=>{
 const {state}=stageRuntimeFixture(),{nodes}=state.run.definition;
 nodes.p.children=['t'];nodes.t.children=['a','h']; // Opposite to the insertion order in nodes.
 state.run.jobs.a={status:'completed'};state.run.jobs.h={status:'completed',decisions:{job:{item_id:'job',verdict:'completed',note:'\n선택한 판정: 승인 (yes)',actor_id:'actor'}}};
 const render=selection=>html('workStageHTML(state,selection,state.run.definition.nodes.t).body',{state,selection});
 const ids=out=>[...out.matchAll(/data-stage-job="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(ids(render({})),['a','h']);assert.deepEqual(ids(render({stage_approved_expanded:false})),['a']);
 const out=render({stage_approved_expanded:false,stage_evidence:'h'});assert.deepEqual(ids(out),['a','h']);assert.match(out,/stage-evidence-h/);
 assert.match(out,/2 \/ 2 완료/);assert.match(out,/실행 완료 1<\/span>/);assert.match(out,/승인 1<\/span>/);
 nodes.t.children.reverse();state.run.jobs.a={status:'failed'};const revised=render({});assert.deepEqual(ids(revised),['h','a']);assert.match(revised,/1 \/ 2 완료/);assert.match(revised,/<i class="ew-vd-dot" data-verdict="bad"><\/i>실행 실패 1<\/span>/);
});

test('stage tabs restore their own scroll and the note caret survives chat layout changes',()=>{
 const {state}=stageRuntimeFixture();
 state.run.definition.nodes.next={id:'next',type:'t',parent:'p',children:[],name:'다음 단계'};
 const document={activeElement:null,querySelector:()=>null,createElement:()=>({})};
 let content=null,controls=[];
 function control(tagName,attrs){
  return {tagName,selectionStart:0,selectionEnd:0,selectionDirection:'none',getAttribute:key=>attrs[key] ?? null,hasAttribute:key=>Object.hasOwn(attrs,key),
   focus(){document.activeElement=this;},setSelectionRange(start,end,direction){this.selectionStart=start;this.selectionEnd=end;this.selectionDirection=direction;}};
 }
 const host={dataset:{},isConnected:true,classList:{toggle(){}},setAttribute(){},contains:el=>controls.includes(el),querySelector:selector=>selector==='#ees-work-content'?content:null,
  querySelectorAll:selector=>selector==='button,input,select,textarea,a,summary'?controls:[],
  set innerHTML(value){content={scrollTop:0};controls=value.includes('data-stage-note')?[control('BUTTON',{'data-action':'job','data-job-id':'h'}),control('TEXTAREA',{'data-job-id':'h','data-stage-note':''})]:[];document.activeElement=null;}};
 const context=renderer({document,window:{__eesSourceShellV1:{hosts:()=>({panel:host}),publish(){}}}}),view=run(context,'createWorkView({callbacks:{}})');
 const render=(stage_id,stage_tab,layout={})=>view.render({state,selection:{mode:'work',workflow_id:'w',run_id:'r',tab:'overview',stage_id,stage_tab,stage_evidence:'h',stage_notes:{'actor/r/h//0':'개인 메모'},...layout}});
 const initial=structuredClone(state);
 render('t','work');content.scrollTop=215;const original=controls[1];original.focus();original.setSelectionRange(1,3,'forward');
 render('t','work',{chat_open:false,chat_width:400});
 assert.equal(content.scrollTop,215);assert.notEqual(controls[1],original);
 assert.equal(document.activeElement,controls[1]);assert.deepEqual([controls[1].selectionStart,controls[1].selectionEnd,controls[1].selectionDirection],[1,3,'forward']);
 render('t','log');assert.equal(content.scrollTop,0);content.scrollTop=88;
 render('next','work');assert.equal(content.scrollTop,0);content.scrollTop=29;
 render('t','work');assert.equal(content.scrollTop,215);
 render('t','log');assert.equal(content.scrollTop,88);
 render('next','work');assert.equal(content.scrollTop,29);
 assert.deepEqual(state,initial);
});

test('the API assistant applies one matching Native reply to the open editor and waits for an explicit Save',async()=>{
 const fs=require('node:fs'),path=require('node:path');
 const h=controller(),requests=[],replies=[];
 const source=fs.readFileSync(path.join(__dirname,'../branding/ees/ui/ees-work-api-catalog.js'),'utf8');
 run(h.context,source);
 const catalog={apis:[],services:[],can_manage:true};
 const editor=run(h.context,'createWorkApiCatalog')({catalog:()=>catalog,paint(){},newId:crypto.randomUUID,legacyAvailable:()=>true,
   contextChanged:()=>h.designer.callbacks.apiContextChanged(),command:async msg=>{requests.push(JSON.parse(JSON.stringify(msg)));return {ok:true,api:{id:'result'}};}});
 h.api.setState({capabilities:{actor_id:'a'}});h.api.setSelection({mode:'author',tab:'tools',system_id:'EMS'});
 h.designer.readApiContext=()=>editor.context();h.designer.applyApiSuggestion=(values,expected)=>editor.suggest(values,expected);
 h.context.window.__eesSourceShellV1.askHelp=async payload=>{replies.push(JSON.parse(JSON.stringify(payload)));return {accepted:true};};
 const field=(name,value)=>editor.handle({type:'input',target:{name:'api-'+name,value,dataset:{},closest:selector=>selector==='[data-api-catalog]'?{}:null}});
 const ask=async()=>{await h.api.handleClick({dataset:{action:'api_question',question:'용도 설명 제안'}});return replies.at(-1).reference.api_draft_request;};
 const apply=(requestId,purpose)=>h.api.handleClick({dataset:{action:'api_apply_purpose',requestId,purpose}});
 editor.start();field('name','알람 조회');field('url','https://private.example/api/alarms?key=concealed');
 let request=await ask();
 assert.doesNotMatch(replies[0].question,/private\.example|concealed/);assert.match(replies[0].question,/알람 조회/);assert.match(replies[0].question,/api\/alarms/);
 assert.equal(replies[0].reference.kind,'help');assert.equal(replies[0].reference.title,'알람 조회');
 field('name','수정한 이름');assert.equal(await apply(request,'다른 편집 상태의 제안'),false);
 request=await ask();h.api.setSelection({tab:'overview'});assert.equal(await apply(request,'다른 화면의 제안'),false);
 h.api.setSelection({tab:'tools'});request=await ask();catalog.can_manage=false;
 assert.equal(await apply(request,'권한 회수 후 제안'),false);catalog.can_manage=true;
 h.designer.callbacks.apiContextChanged();request=await ask();
 assert.equal(await apply('wrong-request','무관한 답변'),false);
 const sentence='설비에서 최근에 발생한 알람 목록을 조회합니다.';
 assert.equal(await apply(request,sentence),true);assert.match(editor.html(),/name="api-purpose" value="설비에서 최근에 발생한 알람 목록을 조회합니다\."/);
 assert.equal(await apply(request,'중복 반영'),false);assert.deepEqual(requests,[]);assert.equal(h.calls.length,0);
 const target={dataset:{apiAction:'save'},closest:s=>s==='[data-api-catalog]'?{}:s==='[data-api-action]'?target:null};
 editor.handle({type:'click',target});await new Promise(resolve=>setImmediate(resolve));assert.equal(requests.length,1);assert.equal(requests[0].api.purpose,sentence);
});

// First-user flow (2026-11-18, mock 18 revision 2), work side.
test("first-user: a person's check is confirmed with one click and the other answers stay behind the arrow",async()=>{
 const h=stageRuntimeFixture(),view=part=>html('workStageHTML(state,selection,state.run.definition.nodes.t).'+part,{state:h.state,selection:h.api.snapshot().selection});
 const row=view('body').match(/<section class="ew-vd-entry[^>]*data-stage-job="h"[\s\S]*?<\/section>/)[0];
 assert.match(row,/<span class="ew-vd-confirm"><button type="button" class="ew-vd-confirm-main" data-action="stage_decide" data-job-id="h" data-judgment-id="yes" data-verdict="completed" data-mutation aria-label="직접 확인 승인">승인<\/button><button type="button" class="ew-vd-confirm-more" data-action="stage_verdict" data-job-id="h" aria-haspopup="menu" aria-expanded="false" aria-controls="ees-stage-verdict-menu" aria-label="직접 확인 다른 판정">/);
 assert.doesNotMatch(row,/ew-vd-pick|판정 필요/);assert.match(view('body'),/<\/i>확인 필요 1<\/span>/);
 await h.api.handleClick({dataset:{action:'stage_verdict',jobId:'h'}});
 assert.deepEqual([...view('menu').matchAll(/data-judgment-id="([^"]+)"/g)].map(match=>match[1]),['conditional','no']);
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'h',judgmentId:'yes',verdict:'completed'}});
 const sent=h.mutations();assert.equal(sent.length,1);assert.equal(sent[0].body.action,'human_confirm');assert.equal(sent[0].body.verdict,'completed');assert.equal(sent[0].body.judgment_id,'yes');
 // once decided, the answer stays a control that opens every word so it can be changed
 h.state.run.jobs.h={status:'completed',can_decide:true,decisions:{job:{verdict:'completed',note:'\n선택한 판정: 승인 (yes)',actor_id:'actor',created_at:'2026-11-18T00:00:00Z'}}};
 const decided=view('body').match(/<section class="ew-vd-entry[^>]*data-stage-job="h"[\s\S]*?<\/section>/)[0];assert.match(decided,/class="ew-vd-pick" data-action="stage_verdict" data-job-id="h" data-verdict="ok"/);assert.doesNotMatch(decided,/ew-vd-confirm/);
 h.api.setState(h.state);h.api.setSelection({stage_verdict_job:'h'});assert.deepEqual([...view('menu').matchAll(/data-judgment-id="([^"]+)"/g)].map(match=>match[1]),['yes','conditional','no']);
});
test('first-user: before a run a row shows its state and only the start control starts the run',()=>{
 const h=stagePreviewFixture(),body=html('workStageHTML(state,selection,workPublishedDefinition(state).nodes.t).body',{state:h.state,selection:{stage_id:'t'}});
 const row=body.match(/<section class="ew-vd-entry[^>]*data-stage-job="h"[\s\S]*?<\/section>/)[0];
 assert.match(row,/<span class="ew-vd-state" data-decision-status><span>확인 필요<\/span><\/span>/);assert.doesNotMatch(row,/stage_start|ew-vd-pick|ew-vd-confirm/);
 assert.match(body,/class="ew-secondary ew-stage-run-button" data-action="stage_start"[^>]*>[\s\S]*?<span>시작<\/span>/);
});
test('first-user: a stage of human checks shows no run control during a run, then 끝내기 once every job is settled',async()=>{
 const h=stageRuntimeFixture(),nodes=h.state.run.definition.nodes;delete nodes.a;delete nodes.other;delete h.state.run.jobs.a;
 const body=()=>html('workStageHTML(state,selection,state.run.definition.nodes.t).body',{state:h.state,selection:h.api.snapshot().selection});
 assert.doesNotMatch(body(),/ew-stage-run-button|지금 실행|data-action="execute_scope"|data-action="finish_run"/);
 h.state.run.jobs.h={status:'failed',can_decide:true,decisions:{job:{verdict:'failed',note:'\n선택한 판정: 미승인 (no)',actor_id:'actor',created_at:'2026-11-18T00:00:00Z'}}};
 assert.doesNotMatch(body(),/data-action="finish_run"/,'the server does not close a run with an unsettled job');
 h.state.run.jobs.h={status:'completed',can_decide:true,decisions:{job:{verdict:'completed',note:'\n선택한 판정: 승인 (yes)',actor_id:'actor',created_at:'2026-11-18T00:00:00Z'}}};
 assert.match(body(),/<button type="button" class="ew-secondary ew-stage-run-button" data-action="finish_run" data-mutation><span>끝내기<\/span><\/button>/);
 assert.match(html('workOperationOverviewHTML(state,selection)',{state:h.state,selection:{}}),/data-action="finish_run"/);
 let dialogs=0;h.setDialog(()=>{dialogs++;return Promise.resolve(true);});h.api.setState(h.state);
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true});
 await h.api.handleClick({dataset:{action:'finish_run'}});
 const closes=h.calls.filter(call=>call.body?.action==='close_run');assert.equal(closes.length,1);assert.equal(closes[0].body.run_id,'r');assert.equal(closes[0].body.expected_revision,8);assert.equal(dialogs,0);
 assert.equal(h.api.snapshot().selection.run_id,'');assert.equal(h.api.snapshot().selection.stage_id,'');assert.equal(h.api.snapshot().selection.tab,'overview');
});
test('first-user: finishing is refused while a job is unsettled',async()=>{
 const h=stageRuntimeFixture();await h.api.handleClick({dataset:{action:'finish_run'}});assert.equal(h.calls.filter(call=>call.body?.action==='close_run').length,0);
});
test('first-user: with nothing to ask, start creates the run at once from the first screen and from a stage',async()=>{
 for(const from of ['overview','stage']){
  const h=stagePreviewFixture(),definition=h.state.workflow.published;let dialogs=0;h.setDialog(()=>{dialogs++;return Promise.resolve(false);});
  h.setReply(call=>{if(call.body?.action==='start_run'){h.state.run={id:'new-run',workflow_id:'w',definition,status:'open',jobs:{},attempts:[],revision:1};return {ok:true,run:h.state.run};}return call.url.includes('workspace?')?h.state:{ok:true};});
  if(from==='stage')h.api.setSelection({stage_id:'t'});
  await h.api.handleClick({dataset:from==='stage'?{action:'stage_start',nodeId:'t'}:{action:'overview_start'}});
  assert.equal(dialogs,0,from);const starts=h.calls.filter(call=>call.body?.action==='start_run');assert.equal(starts.length,1,from);assert.deepEqual(starts[0].body.inputs,{},from);assert.equal(starts[0].body.version,3,from);
  assert.equal(h.api.snapshot().selection.run_id,'new-run',from);assert.equal(h.api.snapshot().selection.stage_id,from==='stage'?'t':'',from);
 }
});
test('first-user: the first screen of a procedure shows its purpose, one start control and the last finished run',()=>{
 const h=stagePreviewFixture(),view=()=>html('workOperationOverviewHTML(state,selection)',{state:h.state,selection:{system_id:'EMS'}});h.state.workflow.published.description='매주 설비를 점검합니다.';
 assert.match(view(),/<div class="ew-overview-head"><div><h2>배포 산출물 점검<\/h2><p class="ew-overview-purpose">매주 설비를 점검합니다.<\/p><\/div><button type="button" class="ew-secondary ew-stage-run-button" data-action="overview_start" aria-label="배포 산출물 점검 시작">/);assert.doesNotMatch(view(),/ew-last-run/);
 h.state.runs=[{id:'old',workflow_id:'w',status:'completed',factory_id:'',closed_at:'2026-11-17T05:41:00Z'},{id:'older',workflow_id:'w',status:'cancelled',factory_id:'',closed_at:'2026-11-10T05:41:00Z'},{id:'x',workflow_id:'other',status:'completed',factory_id:'',closed_at:'2026-11-18T00:00:00Z'},{id:'open',workflow_id:'w',status:'open',factory_id:''}];
 assert.equal([...view().matchAll(/<p class="ew-last-run"><i aria-hidden="true"><\/i>지난 회차 · [^<]+ 끝남<\/p>/g)].length,1);
 h.state.runs=[h.state.runs[1]];assert.match(view(),/지난 회차 · [^<]+ 취소<\/p>/);
 const running=stageRuntimeFixture();assert.doesNotMatch(html('workOperationOverviewHTML(state,selection)',{state:running.state,selection:{}}),/overview_start|finish_run|ew-last-run/);
});
test('first-user: the work side opens with a way to make a procedure and lists the ones not published yet',()=>{
 const view=(state,selection={system_id:'EMS'})=>html('workHomeHTML(state,selection)',{state,selection}),author={actor_id:'a',can_author:true};
 assert.equal(view({capabilities:author,workflows:[]}),'<div class="ew-empty ew-work-home"><h3>아직 업무가 없습니다</h3><button type="button" class="ew-primary" data-action="procedure_new">새 업무 절차</button></div>');
 assert.equal(view({capabilities:{actor_id:'b'},workflows:[]}),'<div class="ew-empty ew-work-home"><h3>아직 업무가 없습니다</h3></div>');
 const draft={id:'d',name:'일일 펌프 점검',system_id:'EMS',published_version:null,can_manage:true,draft:{nodes:{p:{id:'p',type:'p'},t:{id:'t',type:'t'},j:{id:'j',type:'j'}}}},elsewhere={id:'o',name:'다른 시스템 초안',system_id:'APC',published_version:null};
 const pending=view({capabilities:author,workflows:[draft,elsewhere]});
 assert.match(pending,/<h3>아직 업무가 없습니다<\/h3><button type="button" class="ew-primary" data-action="procedure_new">새 업무 절차<\/button><div class="ew-home-pending"><h4>게시 전<\/h4><button type="button" data-action="pending_open" data-workflow-id="d"><strong>일일 펌프 점검<\/strong><small>단계 1 · 작업 1<\/small>/);assert.doesNotMatch(pending,/다른 시스템 초안/);
 assert.doesNotMatch(view({capabilities:{actor_id:'b'},workflows:[draft]}),/게시 전|일일 펌프 점검/,'drafts are for accounts that may author');
 const mixed=view({capabilities:author,workflows:[draft,{id:'p1',name:'게시된 절차',system_id:'EMS',published_version:1}]});assert.match(mixed,/업무 절차를 선택해 주세요/);assert.match(mixed,/data-action="pending_open" data-workflow-id="d"/);assert.doesNotMatch(mixed,/procedure_new/);
});
test('first-user: a draft opens in the workspace and the new-procedure control opens the form there',async()=>{
 const h=stagePreviewFixture();h.state.capabilities.can_author=true;h.state.workflows=[{id:'d',name:'초안',system_id:'EMS',published_version:null,can_manage:true}];h.api.setState(h.state);h.api.setSelection({system_id:'EMS',workflow_id:'',stage_id:''});
 await h.api.handleClick({dataset:{action:'pending_open',workflowId:'missing'}});assert.equal(h.api.snapshot().selection.mode,'work');
 await h.api.handleClick({dataset:{action:'pending_open',workflowId:'d'}});assert.equal(h.api.snapshot().selection.mode,'author');assert.equal(h.api.snapshot().selection.workflow_id,'d');
 let started=0;h.designer.startProcedure=()=>{started++;};h.api.setSelection({mode:'work',workflow_id:''});
 await h.api.handleClick({dataset:{action:'procedure_new'}});assert.equal(h.api.snapshot().selection.mode,'author');assert.equal(h.api.snapshot().selection.workflow_id,'');assert.equal(started,1);
});

// Check items (2026-11-18): a person's check list is ticked on the job row.
function checkListFixture(){
 const h=stageRuntimeFixture(),nodes=h.state.run.definition.nodes;delete nodes.a;delete nodes.other;delete h.state.run.jobs.a;
 Object.assign(nodes.h,{result_block:'checklist',confirmation_items:[{id:'pump',name:'펌프 누수 없음'},{id:'valve',name:'밸브 개폐 정상'}]});h.state.people=[{id:'actor',name:'담당자'}];
 const row=()=>html('workStageHTML(state,selection,state.run.definition.nodes.t).body',{state:h.state,selection:h.api.snapshot().selection}).match(/<section class="ew-vd-entry[^>]*data-stage-job="h"[\s\S]*?<\/section>/)[0];
 const tick=item=>h.api.handleEvent({type:'change',target:{checked:true,dataset:{jobId:'h',itemId:item},matches:selector=>selector==='[data-stage-check]',closest:selector=>selector==='[data-ees-work]'?{}:null}});
 return {...h,row,tick,sent:()=>h.calls.filter(call=>call.body?.action==='human_confirm')};
}
test("check items: a person's list shows under its job with a count, and each item is ticked in place",async()=>{
 const h=checkListFixture();
 assert.match(h.row(),/<span class="ew-vd-count" data-decision-status>0 \/ 2<\/span>/);assert.doesNotMatch(h.row(),/ew-vd-confirm|ew-vd-pick/);
 assert.deepEqual([...h.row().matchAll(/<label><input type="checkbox" data-stage-check data-job-id="h" data-item-id="([^"]+)" data-mutation><span>([^<]+)<\/span><\/label>/g)].map(match=>[match[1],match[2]]),[['pump','펌프 누수 없음'],['valve','밸브 개폐 정상']]);
 h.api.setState(h.state);h.tick('pump');await new Promise(setImmediate);
 assert.equal(h.sent().length,1);assert.deepEqual({job:h.sent()[0].body.job_id,item:h.sent()[0].body.item_id,verdict:h.sent()[0].body.verdict,revision:h.sent()[0].body.expected_revision},{job:'h',item:'pump',verdict:'completed',revision:8});
 // a recorded tick is shown with who and when, and is no longer a control
 h.state.run.jobs.h={status:'waiting_confirmation',can_decide:true,can_execute:true,decisions:{pump:{item_id:'pump',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T01:00:00Z'}}};
 assert.match(h.row(),/<li data-done="true"><span class="ew-vd-check-done" role="img" aria-label="확인함">[\s\S]*?<\/span><span>펌프 누수 없음<\/span><small>[^<]+ · 담당자<\/small><\/li>/);
 assert.match(h.row(),/<span class="ew-vd-count" data-decision-status>1 \/ 2<\/span>/);assert.equal([...h.row().matchAll(/data-stage-check/g)].length,1);
 assert.doesNotMatch(h.row(),/data-action="stage_evidence"/,'each item carries its own record');
 assert.match(html('workStageLogHTML(workStageRows(state,state.run.definition.nodes.t),state)',{state:h.state}),/직접 확인 · 펌프 누수 없음 확인 · 담당자/);
 h.api.setState(h.state);h.tick('pump');await new Promise(setImmediate);assert.equal(h.sent().length,1,'an item that is already recorded is not sent again');
 h.tick('other');await new Promise(setImmediate);assert.equal(h.sent().length,1,'only items of the list are sent');
 // all ticked: the job is complete and the run can be finished
 h.state.run.jobs.h={status:'completed',can_decide:true,can_execute:true,decisions:{pump:{item_id:'pump',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T01:00:00Z'},valve:{item_id:'valve',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T01:01:00Z'}}};
 assert.doesNotMatch(h.row(),/data-stage-check|ew-vd-count/);assert.match(h.row(),/class="ew-vd-final" data-decision-status><i class="ew-vd-dot" data-verdict="ok"><\/i><span>완료<\/span>/);
 assert.match(html('workStageHTML(state,selection,state.run.definition.nodes.t).body',{state:h.state,selection:h.api.snapshot().selection}),/data-action="finish_run"/);
});
test('check items: after an input or an earlier job changes, the list is ticked again and the earlier ticks stay in the record',async()=>{
 // 2026-11-19 (PR #152 review): the earlier ticks stayed shown as done, so nothing was left to tick and the round could not be finished.
 const h=checkListFixture(),ticked={pump:{item_id:'pump',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T01:00:00Z',result_revision:1},valve:{item_id:'valve',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T01:01:00Z',result_revision:1}};
 for(const stale of [{status:'review_required'},{status:'waiting_confirmation',result_stale:true}]){
  h.state.run.jobs.h={can_decide:true,can_execute:true,decisions:ticked,decision_history:Object.values(ticked),...stale};
  assert.equal([...h.row().matchAll(/<label><input type="checkbox" data-stage-check data-job-id="h" data-item-id="[^"]+" data-mutation>/g)].length,2,JSON.stringify(stale));
  assert.doesNotMatch(h.row(),/ew-vd-check-done/);
  assert.match(h.row(),/<span class="ew-vd-state" data-recheck>다시 검토 필요<\/span><span class="ew-vd-count" data-decision-status>0 \/ 2<\/span>/);
  const log=html('workStageLogHTML(workStageRows(state,state.run.definition.nodes.t),state)',{state:h.state});assert.match(log,/펌프 누수 없음 확인 · 담당자/);assert.match(log,/밸브 개폐 정상 확인 · 담당자/);
  assert.doesNotMatch(html('workResultHTML(state.run.definition.nodes.h,state.run.jobs.h,state)',{state:h.state}),/확인 · actor/,'the job panel does not show the earlier ticks as current');
 }
 h.api.setState(h.state);h.tick('pump');await new Promise(setImmediate);
 assert.equal(h.sent().length,1,'a tick that no longer counts can be made again');assert.equal(h.sent()[0].body.item_id,'pump');
 // the new ticks are on a new result: only they count
 h.state.run.jobs.h={status:'waiting_confirmation',can_decide:true,can_execute:true,decisions:{pump:{item_id:'pump',verdict:'completed',actor_id:'actor',created_at:'2026-11-18T02:00:00Z',result_revision:2}}};
 assert.match(h.row(),/<span class="ew-vd-count" data-decision-status>1 \/ 2<\/span>/);assert.doesNotMatch(h.row(),/data-recheck/);
});
// ---- Values of a job under its row (2026-11-19, design mock 19 revision 3) ----
function askFixture({started=true}={}){
 const h=stageRuntimeFixture(),nodes=h.state.run.definition.nodes;delete nodes.h;delete nodes.other;delete h.state.run.jobs.h;
 delete nodes.a.tool_reference;Object.assign(nodes.a,{name:'기준 문서 확인',result_block:'human_confirm',human_confirmation:true,instructions:'페이지 ID를 입력하세요.',api_binding:{operation_id:'page',version:1,inputs:{id:{input:'page-id'}},outputs:['title','id']},inputs:[{id:'page-id',name:'페이지 ID',type:'text',scope:'run',required:true,example:'123456789'}]});
 nodes.b={id:'b',type:'j',parent:'t',name:'하위 문서 목록 조회',mode:'tool',result_block:'list_confirm',human_confirmation:true,deps:['a'],api_binding:{operation_id:'children',version:1,inputs:{id:{result:{job_id:'a',field:'id',confirmed:true}},limit:{constant:5}},outputs:['title','id']}};
 Object.assign(h.state.run,{inputs:{},jobs:{a:{status:'ready',can_execute:true,can_decide:true},b:{status:'pending',can_execute:true,can_decide:true}}});
 Object.assign(h.state.workflow,{published:{name:'가이드',execution_scope:'system',nodes},published_version:1,revision:3});
 const run=h.state.run;if(!started)delete h.state.run;
 // the fields a person types into: one fake field for each field of the open job
 const typed={},unmarked=[];
 const panelOf=job=>({dataset:{jobId:job},querySelectorAll:selector=>selector==='[data-work-input]'?Object.entries(typed[job] || {}).map(([name,field])=>({name,type:'text',disabled:false,getAttribute:()=>null,focus(){},...field})):[]});
 const panel={isConnected:true,addEventListener(){},removeEventListener(){},querySelectorAll:selector=>selector==='[data-stage-values]'?Object.keys(typed).map(panelOf):[],querySelector:()=>null};
 h.context.window.__eesSourceShellV1.hosts=()=>({panel});
 const target=(job,name,value)=>({name,value,matches:selector=>selector==='[data-work-input]'||selector==='input[data-work-input]',closest:selector=>selector==='[data-stage-values]'?panelOf(job):selector==='[data-ees-work]'?{}:null,removeAttribute(name){unmarked.push(name);}});
 const type=(job,name,value,inputType='text')=>{typed[job]={...(typed[job] || {}),[name]:{value,dataset:{inputType}}};h.api.handleEvent({type:'input',target:target(job,name,value)});};
 const seen=()=>h.api.drawn().selection;
 const body=()=>html('workStageHTML(state,selection,workOperationDefinition(state).nodes.t).body',{state:h.api.snapshot().state,selection:seen()});
 const row=id=>{const text=body(),at=text.indexOf('data-stage-job="'+id+'"'),from=text.lastIndexOf('<section class="ew-vd-entry',at),next=text.indexOf('<section class="ew-vd-entry',at);return text.slice(from,next<0?undefined:next);};
 const sent=(...actions)=>h.calls.filter(call=>actions.includes(call.body?.action)).map(call=>call.body);
 return {...h,run,type,seen,body,row,sent,unmarked,typed,panelOf,target};
}
test('values of a job: the row is unchanged, its name opens the area under it, and the area holds what is asked',()=>{
 const h=askFixture(),closed=h.row('a');
 assert.match(closed,/<button type="button" class="ew-vd-name" data-action="stage_values" data-job-id="a" aria-expanded="false">기준 문서 확인<\/button>/);
 assert.doesNotMatch(closed,/ew-vd-under|data-stage-values/);assert.match(closed,/<button type="button" class="ew-vd-run" data-action="stage_execute" data-job-id="a"/);
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'a'});const open=h.row('a');
 // what is on the row itself does not change when the area opens
 const head=text=>text.slice(0,text.indexOf('</div></div>')).replace(/ aria-(expanded|controls)="[^"]*"/g,'').replace(/ data-expanded="[^"]*"/,'');assert.equal(head(open),head(closed));
 assert.match(open,/<div class="ew-vd-under" id="stage-under-a"><div class="ew-vd-evidence ew-vd-job-values" id="stage-values-a"><div class="ew-vd-tool-detail" data-stage-values data-job-id="a"><section><h4>입력<\/h4><dl class="ew-vd-tool-values ew-vd-ask-values"><dt><label for="ew-stage-a-page-id">페이지 ID<\/label><\/dt><dd><input name="page-id" data-work-input[^>]* id="ew-stage-a-page-id" required placeholder="예: 123456789" type="text" value=""><\/dd><\/dl><\/section><\/div><\/div>/);
 assert.match(open,/<p class="ew-vd-more"><button type="button" class="ew-text" data-action="job" data-job-id="a" aria-label="기준 문서 확인 자세히">자세히<\/button><\/p><\/div><\/section>$/);
 assert.doesNotMatch(open,/아직 실행하지 않았습니다|data-stage-result/,'nothing is shown for a run that has not happened');
 // a value already saved with the run, then a value being typed over it
 h.state.run.inputs={'page-id':'111'};assert.match(h.row('a'),/id="ew-stage-a-page-id" required placeholder="예: 123456789" type="text" value="111">/);
 h.type('a','page-id','222');h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});assert.equal(h.api.snapshot().selection.stage_evidence,'');h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});
 assert.match(h.row('a'),/type="text" value="222">/,'what is typed is kept while the area is closed and opened');
});
test('values of a job: a value from an earlier job is shown, and the job waits until that job is confirmed',()=>{
 const h=askFixture();h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'b'});let row=h.row('b');
 assert.match(row,/<button type="button" class="ew-vd-run" data-action="stage_execute" data-job-id="b"[^>]* disabled data-own-disabled="true" data-run-blocked>/);assert.match(row,/<span class="ew-vd-state" data-decision-status><span>대기<\/span><\/span>/);
 assert.match(row,/<section><h4>입력<\/h4><dl class="ew-vd-tool-values ew-vd-ask-values"><dt>페이지 ID<\/dt><dd><span class="ew-vd-given">기준 문서 확인에서<\/span><\/dd><\/dl><\/section>/);assert.doesNotMatch(row,/<input/);
 assert.match(h.body(),/실행 필요 1<\/span><span><i class="ew-vd-dot" data-verdict="none"><\/i>대기 1/);
 // run but not confirmed yet: still waiting. The server marks the job after a job that ran for another review;
 // a job that has done nothing yet has nothing to review again and stays 대기, then 실행 필요.
 Object.assign(h.state.run.jobs.a,{status:'waiting_confirmation',attempt_id:'at',result_revision:1,result:{items:[{id:'row-1',row:{title:'점검 기준서',id:'27182'}}],field_labels:{title:'문서 제목',id:'페이지 ID'}}});
 h.state.run.jobs.b.status='review_required';
 assert.match(h.row('b'),/<span>대기<\/span>/);assert.doesNotMatch(h.body(),/다시 검토 필요/);
 Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}}});row=h.row('b');
 assert.match(row,/<dt>페이지 ID<\/dt><dd><span>27182<\/span><span class="ew-vd-given">기준 문서 확인에서<\/span><\/dd>/);
 assert.match(row,/<button type="button" class="ew-vd-run" data-action="stage_execute" data-job-id="b" aria-label="하위 문서 목록 조회 실행" data-mutation>/);assert.match(row,/<span>실행 필요<\/span>/);
 // once it has run, a run of the job before it does ask for another review
 h.state.run.attempts=[...(h.state.run.attempts || []),{id:'bt',job_id:'b',number:1,status:'succeeded'}];Object.assign(h.state.run.jobs.b,{attempt_id:'bt',current_attempt:'bt'});
 assert.match(h.row('b'),/<span>다시 검토 필요<\/span>/);h.state.run.attempts=h.state.run.attempts.filter(item=>item.id!=='bt');delete h.state.run.jobs.b.attempt_id;delete h.state.run.jobs.b.current_attempt;
 // before a run exists the row cannot start it either
 const before=askFixture({started:false});assert.match(before.row('b'),/data-action="stage_start" data-job-id="b"[^>]* disabled data-own-disabled="true" data-run-blocked>/);assert.match(before.row('a'),/data-action="stage_start" data-job-id="a" aria-label="기준 문서 확인 실행">/);
});
test('values of a job: what an API job brought back is shown under 입력, one record as a list of names and a list as rows',()=>{
 const h=askFixture();h.state.run.inputs={'page-id':'27182'};h.state.run.attempts=[{id:'at',job_id:'a',number:1,status:'succeeded',finished_at:'2026-11-19T01:00:00Z'},{id:'bt',job_id:'b',number:1,status:'succeeded',finished_at:'2026-11-19T01:05:00Z'}];
 Object.assign(h.state.run.jobs.a,{status:'waiting_confirmation',attempt_id:'at',current_attempt:'at',result_revision:1,result:{items:[{id:'row-1',row:{title:'점검 기준서',id:'27182'}}],field_labels:{title:'문서 제목',id:'페이지 ID'}}});
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'a'});let row=h.row('a');
 assert.match(row,/<section data-stage-result><h4>결과<span>1차 · [^<]+<\/span><\/h4><dl class="ew-vd-tool-values"><dt>문서 제목<\/dt><dd>점검 기준서<\/dd><dt>페이지 ID<\/dt><dd>27182<\/dd><\/dl><\/section>/);
 assert.ok(row.indexOf('data-stage-result')>row.indexOf('<h4>입력</h4>'),'입력, then 결과');
 // opened by its name the area holds the values only; 판정 근거 on the row adds the record the product keeps, and
 // pressed again closes the area as it always did
 assert.doesNotMatch(row,/id="stage-evidence-a"/);assert.match(row,/data-stage-result>[\s\S]*<\/section><\/div><\/div><p class="ew-vd-more">/);
 assert.match(row,/class="ew-vd-evidence-toggle" data-action="stage_evidence" data-job-id="a" aria-expanded="false" aria-label="기준 문서 확인 판정 근거 펼치기"/);
 h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a'}});row=h.row('a');
 assert.ok(row.indexOf('data-stage-result')<row.indexOf('id="stage-evidence-a"'),'the record comes after 결과');
 assert.match(row,/id="stage-evidence-a">[\s\S]*현재 실행 결과 · 1차[\s\S]*<p class="ew-vd-more">/);assert.match(row,/class="ew-vd-evidence-toggle" data-action="stage_evidence" data-job-id="a" aria-expanded="true" aria-controls="stage-evidence-a" aria-label="기준 문서 확인 판정 근거 접기"/);
 h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a'}});assert.equal(h.api.snapshot().selection.stage_evidence,'');assert.doesNotMatch(h.row('a'),/ew-vd-under/);
 h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a'}});assert.match(h.row('a'),/id="stage-values-a"[\s\S]*id="stage-evidence-a"/,'from a closed row 판정 근거 opens the area with the record');
 h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});row=h.row('a');assert.doesNotMatch(row,/id="stage-evidence-a"/,'opened again by its name: the values only');
 // a run that failed brought nothing back: no 결과, the record of the run stays
 const came=h.state.run.jobs.a;h.state.run.jobs.a={...came,status:'failed',result:{items:[],field_labels:{}}};
 assert.doesNotMatch(h.row('a'),/data-stage-result/);h.api.handleClick({dataset:{action:'stage_evidence',jobId:'a'}});assert.match(h.row('a'),/<h4>입력<\/h4>[\s\S]*id="stage-evidence-a"/);h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});h.api.handleClick({dataset:{action:'stage_values',jobId:'a'}});h.state.run.jobs.a=came;
 Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed',attempt_id:'at'}}});
 Object.assign(h.state.run.jobs.b,{status:'waiting_confirmation',attempt_id:'bt',current_attempt:'bt',result_revision:1,result:{items:[{id:'r1',row:{title:'주간 점검표',id:'301'}},{id:'r2',row:{title:'월간 점검표',id:'302'}}],field_labels:{title:'문서 제목',id:'페이지 ID'}}});
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'b'});row=h.row('b');
 assert.match(row,/<section data-stage-result><h4>결과<span>2건 · 1차 · [^<]+<\/span><\/h4><ol class="ew-vd-rows" aria-label="하위 문서 목록 조회 결과"><li><span>주간 점검표<\/span><span>301<\/span><\/li><li><span>월간 점검표<\/span><span>302<\/span><\/li><\/ol><\/section>/);
 // the list is confirmed from its row
 assert.match(row,/<span class="ew-vd-confirm"><button type="button" class="ew-vd-confirm-main" data-action="stage_confirm_list" data-job-id="b" data-mutation aria-label="하위 문서 목록 조회 목록 확정">목록 확정<\/button><\/span>/);
 h.state.run.jobs.b.result_stale=true;assert.doesNotMatch(h.row('b'),/stage_confirm_list/);
});
test('values of a job: one press of 실행 before a run starts it with what was typed and runs the job, with no window',async()=>{
 const h=askFixture({started:false});let dialogs=0;h.setDialog(()=>{dialogs++;return Promise.resolve(true);});
 h.setReply(call=>{if(call.body?.action==='start_run'){h.state.run={...h.run,inputs:call.body.inputs};return {ok:true,run:{id:'r'}};}if(call.body?.action==='execute_job')Object.assign(h.state.run.jobs.a,{status:'waiting_confirmation',attempt_id:'at',result_revision:1});return call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true};});
 h.api.setSelection({...h.api.snapshot().selection,run_id:'',stage_evidence:'a'});h.type('a','page-id','123456789');
 await h.api.handleClick({dataset:{action:'stage_start',jobId:'a'}});
 assert.equal(dialogs,0);assert.deepEqual(h.sent('start_run','save_inputs','execute_job').map(body=>body.action),['start_run','execute_job']);
 assert.deepEqual(h.sent('start_run')[0].inputs,{'page-id':'123456789'});assert.deepEqual({run:h.sent('execute_job')[0].run_id,job:h.sent('execute_job')[0].job_id},{run:'r',job:'a'});
 assert.equal(h.api.snapshot().selection.stage_evidence,'a','the job stays open to show what came back');assert.equal(h.api.snapshot().selection.stage_id,'t');
});
test('values of a job: 실행 without the value runs nothing and says so at the field; a refusal of the server lands there too',async()=>{
 const h=askFixture();await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.deepEqual(h.sent('start_run','save_inputs','execute_job'),[]);assert.equal(h.api.snapshot().selection.stage_evidence,'a','a closed job opens');
 assert.match(h.row('a'),/id="ew-stage-a-page-id" aria-invalid="true" aria-describedby="ew-stage-a-page-id-error" required placeholder="예: 123456789" type="text" value=""><small class="ew-vd-ask-error" id="ew-stage-a-page-id-error" role="alert">값을 넣어 주세요<\/small>/);
 const drawn=h.renders.length;h.type('a','page-id','기준 문서');
 assert.equal(h.renders.length,drawn,'the field being typed in is not redrawn');assert.deepEqual(h.unmarked,['aria-invalid','aria-describedby'],'the mark is taken off the field in place');assert.doesNotMatch(h.row('a'),/aria-invalid|ew-vd-ask-error/,'and it does not come back with the next drawing');
 h.setReply(call=>call.body?.action==='execute_job'?{httpError:true,status:400,error:{code:'invalid_inputs',message:'page-id: 숫자만 입력해 주세요.'}}:call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true,revision:9});
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.deepEqual(h.sent('save_inputs','execute_job').map(body=>body.action),['save_inputs','execute_job']);assert.deepEqual(h.sent('save_inputs')[0].inputs,{'page-id':'기준 문서'});
 assert.match(h.row('a'),/<small class="ew-vd-ask-error" id="ew-stage-a-page-id-error" role="alert">숫자만 입력해 주세요\.<\/small>/);assert.equal(h.api.snapshot().error,'','what the field says is not repeated above the screen');
});
test('values of a job: a person\'s answer carries the values typed under the row, and a missing value stops it at the field',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'펌프 상태 기록',mode:'human',result_block:'human_confirm',inputs:[{id:'pressure',name:'압력',type:'number',scope:'run',required:true,unit:'bar',example:'3.2'},{id:'memo',name:'비고',type:'text',scope:'run'}]};
 h.state.run.jobs.c={status:'ready',can_decide:true,can_execute:true};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'c'});
 const open=h.row('c');
 assert.match(open,/<dt><label for="ew-stage-c-pressure">압력<\/label><\/dt><dd><input name="pressure" data-work-input[^>]* id="ew-stage-c-pressure" required placeholder="예: 3\.2" type="number" step="any" value=""><span class="ew-unit">bar<\/span><\/dd><dt><label for="ew-stage-c-memo">비고<\/label><\/dt><dd><input name="memo"[^>]* type="text" value=""><\/dd>/);
 assert.match(open,/<span class="ew-vd-confirm"><button type="button" class="ew-vd-confirm-main" data-action="stage_decide" data-job-id="c"/,'the row keeps its one-click answer');
 assert.doesNotMatch(open,/id="stage-evidence-c"/,'the record of answers is opened by 판정 기록, as before');
 h.api.handleClick({dataset:{action:'stage_evidence',jobId:'c'}});assert.ok(h.row('c').indexOf('id="stage-values-c"')<h.row('c').indexOf('id="stage-evidence-c"'),'the values come before the record of answers');
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'completed'}});
 assert.deepEqual(h.sent('save_inputs','human_confirm'),[]);assert.match(h.row('c'),/id="ew-stage-c-pressure" aria-invalid="true"[^>]*><span class="ew-unit">bar<\/span><small class="ew-vd-ask-error"[^>]*>값을 넣어 주세요<\/small>/);assert.doesNotMatch(h.row('c'),/id="ew-stage-c-memo" aria-invalid/);
 h.type('c','pressure','3.1','number');h.type('c','memo','이상 없음');
 h.setReply(call=>{if(call.body?.action==='save_inputs'){h.state.run.inputs=call.body.inputs;h.state.run.revision=9;}if(call.body?.action==='human_confirm')Object.assign(h.state.run.jobs.c,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}}});return call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true,revision:9};});
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'completed'}});
 assert.deepEqual(h.sent('save_inputs','human_confirm').map(body=>body.action),['save_inputs','human_confirm']);assert.deepEqual(h.sent('save_inputs')[0].inputs,{pressure:3.1,memo:'이상 없음'});assert.equal(h.sent('human_confirm')[0].expected_revision,9);
 assert.equal(h.api.snapshot().selection.stage_evidence,'a','the answered job closes and the next job that asks for a value opens');
 // before a run a person's fields wait for 시작 as the answer does
 const before=askFixture({started:false});before.state.workflow.published.nodes.c=nodes.c;before.api.setSelection({...before.api.snapshot().selection,run_id:'',stage_evidence:'c'});
 assert.match(before.row('c'),/id="ew-stage-c-pressure" required disabled placeholder/);
});
test('values of a job: entering a stage opens the job that asks for a value; a job with nothing to show keeps the way to the job screen',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.plain={id:'plain',type:'j',parent:'t',name:'도구만 실행',mode:'tool',result_block:'values',human_confirmation:false,tool_reference:{tool_id:'native',function:'read',content_hash:'synthetic'}};h.state.run.jobs.plain={status:'ready',can_execute:true};
 h.api.setSelection({...h.api.snapshot().selection,stage_id:'',stage_overview:true,stage_evidence:''});
 await h.api.handleClick({dataset:{action:'stage_open',nodeId:'t'}});assert.equal(h.api.snapshot().selection.stage_evidence,'a');
 assert.match(h.row('plain'),/<button type="button" class="ew-vd-name" data-action="job" data-job-id="plain">도구만 실행<\/button>/);
 // a job that is done is not reopened; the next one that asks or is given a value is
 Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}},result:{items:[{id:'r',row:{id:'27182'}}],field_labels:{id:'페이지 ID'}}});
 h.api.setSelection({...h.api.snapshot().selection,stage_id:'',stage_evidence:''});await h.api.handleClick({dataset:{action:'stage_open',nodeId:'t'}});assert.equal(h.api.snapshot().selection.stage_evidence,'b');
 // a stage where nothing is asked opens nothing
 const quiet=stageRuntimeFixture();quiet.api.setSelection({...quiet.api.snapshot().selection,stage_id:'',stage_evidence:''});await quiet.api.handleClick({dataset:{action:'stage_open',nodeId:'t'}});assert.equal(quiet.api.snapshot().selection.stage_evidence,'');
});
test('values of a job: the start form asks only what belongs to the whole procedure',async()=>{
 const h=askFixture({started:false}),definition=h.state.workflow.published;
 assert.equal(html('workRunStartFields(definition).length',{definition}),0);
 let dialogs=0;h.setDialog(()=>{dialogs++;return Promise.resolve(false);});h.api.setSelection({...h.api.snapshot().selection,run_id:''});
 h.setReply(call=>{if(call.body?.action==='start_run'){h.state.run={...h.run};return {ok:true,run:{id:'r'}};}return call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true};});
 await h.api.handleClick({dataset:{action:'stage_start',nodeId:'t'}});
 assert.equal(dialogs,0);assert.equal(h.sent('start_run').length,1);assert.deepEqual(h.sent('start_run')[0].inputs,{});assert.equal(h.api.snapshot().selection.stage_evidence,'a','after starting, the job that asks for a value is open');
 definition.nodes.p.inputs=[{id:'target',name:'점검 대상',type:'text',scope:'run'},{id:'page-id',name:'페이지 ID',type:'text',scope:'run',required:true,example:'123456789'}];
 // a value asked of the whole procedure is asked once, at the start, also when a job names the same value
 assert.equal(html('workRunStartFields(definition).map(field=>field.id).join()',{definition}),'target,page-id');
 assert.equal(html('workStageAskFields(definition.nodes.a,definition).length',{definition}),0);
 h.state.workflow.published=definition;assert.doesNotMatch(html('workStageRowHTML(workStageRows(state,workOperationDefinition(state).nodes.t)[0],state,{},1)',{state:{...h.state,run:null}}),/stage_values|ew-vd-under/,'and the row of that job is as it was');
 // a value the row cannot draw as it is (choices read from a tool, choices that depend on another value, the form
 // of a shared tool) keeps the start form and is not drawn under the row
 definition.nodes.b.inputs=[{id:'project',name:'프로젝트',type:'single',scope:'run',options_source:'tool'},{id:'status',name:'상태',type:'single',scope:'run',options:['열림'],depends_on:['project']},{id:'shape',name:'조건',type:'text',scope:'run',authored_schema:{type:'string'}},{id:'limit',name:'건수',type:'number',scope:'run'},{id:'site',name:'공장 값',type:'text',scope:'workflow'}];
 assert.equal(html('workRunStartFields(definition).map(field=>field.id).join()',{definition}),'target,page-id,project,status,shape');
 assert.equal(html('workStageAskFields(definition.nodes.b,definition).map(field=>field.id).join()',{definition}),'limit');
});
test('values of a job: a list is confirmed from its row as it came back, with the reason the product asks for',async()=>{
 const h=askFixture();Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}}});
 Object.assign(h.state.run.jobs.b,{status:'waiting_confirmation',attempt_id:'bt',current_attempt:'bt',result_revision:2,result:{items:[{id:'r1',title:'주간 점검표',row:{title:'주간 점검표',id:'301'},required:false},{id:'r2',title:'월간 점검표',row:{title:'월간 점검표',id:'302'},required:false}]}});
 const asked=[];h.context.document.querySelector=selector=>selector==='#ees-list-confirm-reason'?{addEventListener:(kind,fn)=>fn({target:{value:'두 건 확인'}})}:{};
 h.setDialog(options=>{asked.push(options);return Promise.resolve(true);});
 await h.api.handleClick({dataset:{action:'stage_confirm_list',jobId:'b'}});
 assert.equal(asked.length,1);assert.equal(asked[0].confirmLabel,'목록 확정');
 const sent=h.sent('confirm_list');assert.equal(sent.length,1);assert.deepEqual({job:sent[0].job_id,attempt:sent[0].attempt_id,revision:sent[0].result_revision,reason:sent[0].reason,ids:sent[0].items.map(item=>item.id)},{job:'b',attempt:'bt',revision:2,reason:'두 건 확인',ids:['r1','r2']});
 assert.equal(h.api.snapshot().selection.job_id,'','the stage screen stays');
 // as with an answer, the confirmed job closes; here nothing else asks for a value
 Object.assign(h.state.run.jobs.b,{status:'waiting_confirmation'});h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'b'});
 h.setReply(call=>{if(call.body?.action==='confirm_list')Object.assign(h.state.run.jobs.b,{status:'completed'});return call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true};});
 await h.api.handleClick({dataset:{action:'stage_confirm_list',jobId:'b'}});
 assert.equal(h.sent('confirm_list').length,2);assert.equal(h.api.snapshot().selection.stage_evidence,'');
});
// ---- Defects an independent review found in the first implementation (2026-11-19). Each failed before its fix. ----
const settle=()=>new Promise(resolve=>setTimeout(resolve,20));
const replies=(h,change=()=>{})=>h.setReply(call=>{const answer=change(call);return answer || (call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true,revision:9});});
test('values of a job (review): 실행 before a round never runs the job in a round that is already open',async()=>{
 const h=askFixture({started:false}),existing={...h.run,id:'r-other',inputs:{'page-id':'999'}};
 h.state.runs=[{id:'r-other',workflow_id:'w',status:'open',factory_id:''}];
 h.api.setSelection({...h.api.snapshot().selection,run_id:'',stage_evidence:'a'});
 h.setReply(call=>{if(call.url.startsWith('/api/ees-work/workspace?'))return new URL('http://x'+call.url).searchParams.get('run_id')==='r-other'?{...h.state,run:existing}:h.state;return call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true,revision:9};});
 h.type('a','page-id','123');
 await h.api.handleClick({dataset:{action:'stage_start',jobId:'a'}});
 assert.deepEqual(h.sent('start_run','save_inputs','execute_job'),[],'the open round is shown and nothing is started, saved or run');
 assert.equal(h.api.snapshot().state.run?.id,'r-other');
});
test('values of a job (review): a tick carries the values typed under its row, and a missing value stops the tick',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'펌프 점검',mode:'human',result_block:'checklist',confirmation_items:[{id:'pump',name:'누수 없음'},{id:'valve',name:'밸브 닫힘'}],inputs:[{id:'pressure',name:'압력',type:'number',scope:'run',required:true}]};
 h.state.run.jobs.c={status:'ready',can_decide:true,can_execute:true};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'c'});replies(h,call=>{if(call.body?.action==='save_inputs')h.state.run.inputs=call.body.inputs;});
 const tick=item=>h.api.handleEvent({type:'change',target:{checked:true,dataset:{jobId:'c',itemId:item},matches:selector=>selector==='[data-stage-check]',closest:selector=>selector==='[data-ees-work]'?{}:null}});
 tick('pump');await settle();
 assert.deepEqual(h.sent('save_inputs','human_confirm'),[]);assert.match(h.row('c'),/id="ew-stage-c-pressure" aria-invalid="true"/);
 h.type('c','pressure','3.1','number');tick('pump');await settle();
 assert.deepEqual(h.sent('save_inputs','human_confirm').map(body=>body.action+(body.item_id?':'+body.item_id:'')),['save_inputs','human_confirm:pump']);assert.deepEqual(h.sent('save_inputs')[0].inputs,{pressure:3.1});
});
test('values of a job (review): an answered job whose value changes is answered again, also with the same answer',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'펌프 상태 기록',mode:'human',result_block:'human_confirm',inputs:[{id:'pressure',name:'압력',type:'number',scope:'run',required:true}]};
 h.state.run.inputs={pressure:3.1};h.state.run.attempts=[{id:'c1',job_id:'c',number:1,status:'succeeded'}];
 h.state.run.jobs.c={status:'completed',can_decide:true,can_execute:true,attempt_id:'c1',current_attempt:'c1',result_revision:1,decisions:{job:{item_id:'job',verdict:'completed',result_revision:1,attempt_id:'c1',actor_id:'actor'}}};
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'c'});
 replies(h,call=>{if(call.body?.action==='save_inputs'){h.state.run.inputs=call.body.inputs;h.state.run.jobs.c.status='review_required';}if(call.body?.action==='human_confirm')h.state.run.jobs.c.status='completed';});
 h.type('c','pressure','4.2','number');
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'completed'}});
 assert.deepEqual(h.sent('save_inputs','human_confirm').map(body=>body.action),['save_inputs','human_confirm'],'the changed value is not left waiting for a review nobody can give');assert.equal(h.state.run.jobs.c.status,'completed');
 // with nothing changed, the same answer again is still nothing to do
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'completed'}});assert.equal(h.sent('human_confirm').length,1);
});
test('values of a job (review): a held Enter does one thing',async()=>{
 const h=askFixture();h.state.run.inputs={'page-id':'111'};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'a'});replies(h);
 h.typed.a={'page-id':{value:'111',dataset:{inputType:'text'}}};
 const control={dataset:{action:'stage_execute',jobId:'a'},disabled:false},rowElement={querySelector:selector=>selector==='.ew-vd-run'?control:null};
 const press=repeat=>{const field=h.target('a','page-id','111'),base=field.closest,panel=h.panelOf('a');field.closest=selector=>selector==='[data-stage-job]'?rowElement:selector==='[data-mutation]'?null:selector==='[data-stage-values]'?{...panel,querySelectorAll:inner=>inner.startsWith('input[data-work-input]')?[field]:panel.querySelectorAll(inner)}:base(selector);return {type:'keydown',key:'Enter',repeat,isComposing:false,keyCode:13,target:field,preventDefault(){},stopImmediatePropagation(){}};};
 for(const repeat of [false,true,true]){h.api.handleEvent(press(repeat));await settle();}
 assert.equal(h.sent('execute_job').length,1);
});
test('values of a job (review): what is typed is saved and shown for the job that is acted on',async()=>{
 // a refusal about a value two jobs ask for is shown at the job that ran, not at the last job that asks for it
 let h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'둘째 조회',mode:'tool',result_block:'values',human_confirmation:false,api_binding:{operation_id:'page',version:1,inputs:{id:{input:'page-id'}},outputs:['title']},inputs:[{id:'page-id',name:'페이지 ID',type:'text',scope:'run',required:true}]};
 h.state.run.jobs.c={status:'ready',can_execute:true};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'a'});h.type('a','page-id','abc');
 replies(h,call=>call.body?.action==='execute_job'?{httpError:true,status:400,error:{code:'invalid_inputs',message:'page-id: 숫자만 입력해 주세요.'}}:null);
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});assert.equal(h.api.snapshot().selection.stage_evidence,'a');
 // a value typed under another job waits for that job: running this one does not save it over a newer saved value
 h=askFixture();nodes=h.state.run.definition.nodes;
 nodes.q={id:'q',type:'j',parent:'t',name:'메모 확인',mode:'human',result_block:'human_confirm',inputs:[{id:'lot',name:'LOT',type:'text',scope:'run'}]};h.state.run.jobs.q={status:'ready',can_execute:true,can_decide:true};
 h.state.run.inputs={'page-id':'111'};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'q'});h.type('q','lot','OLD-TYPED');
 h.state.run.inputs={'page-id':'111',lot:'NEWER-SAVED'};replies(h);
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.deepEqual(h.sent('save_inputs'),[]);assert.equal(h.sent('execute_job').length,1);
 // a job whose row has nothing that would save a value does not ask for it there: the start form does, as before
 const definition={nodes:{p:{id:'p',type:'p'},t:{id:'t',type:'t',parent:'p'},
  request:{id:'request',type:'j',parent:'t',mode:'tool',result_block:'change_request',inputs:[{id:'lot',name:'LOT',type:'text',scope:'run'}]},
  verdicts:{id:'verdicts',type:'j',parent:'t',mode:'human',result_block:'item_verdict',inputs:[{id:'basis',name:'기준',type:'text',scope:'run'}]},
  shape:{id:'shape',type:'j',parent:'t',mode:'tool',result_block:'values',inputs:[{id:'filter',name:'조건',type:'json_object',scope:'run'},{id:'count',name:'건수',type:'number',scope:'run'}]}}};
 assert.equal(html('["request","verdicts","shape"].map(id=>workStageAskFields(definition.nodes[id],definition).map(field=>field.id).join("+")).join()',{definition}),',,count');
 assert.equal(html('workRunStartFields(definition).map(field=>field.id).join()',{definition}),'lot,basis,filter');
});
test('values of a job (review): a value typed before a round belongs to the place that round would start in',async()=>{
 const h=askFixture({started:false});h.state.workflow.published.execution_scope='factory';h.state.factories=[{id:'F1',name:'1공장'},{id:'F2',name:'2공장'}];
 h.api.setSelection({...h.api.snapshot().selection,run_id:'',factory_id:'F1',stage_evidence:'a'});h.type('a','page-id','F1-ONLY');
 h.setReply(call=>{if(call.body?.action==='start_run'){h.state.run={...h.run,factory_id:call.body.factory_id,inputs:call.body.inputs};return {ok:true,run:{id:'r'}};}return call.url.startsWith('/api/ees-work/workspace?')?h.state:call.url.startsWith('/api/ees-work/operations?')?{}:{ok:true};});
 await h.api.select({factory_id:'F2',stage_id:'',tab:'overview'});
 await h.api.handleClick({dataset:{action:'overview_start'}});
 assert.deepEqual(h.sent('start_run').map(body=>({factory:body.factory_id,inputs:body.inputs})),[{factory:'F2',inputs:{}}]);
});
test('values of a job (review): only the rows a list hands over count as the value a job is given',()=>{
 const h=askFixture();Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}},result:{items:[{id:'r1',selected:false,row:{id:'1'}},{id:'r2',row:{id:'27182'}}],field_labels:{id:'페이지 ID'}}});
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'b'});
 assert.match(h.row('b'),/<dt>페이지 ID<\/dt><dd><span>27182<\/span><span class="ew-vd-given">기준 문서 확인에서<\/span><\/dd>/);
});
// ---- A second review, of the fixes above (2026-11-19). Each failed before its fix. ----
test('values of a job (second review): a field is open only while something on its row can save it',()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes,field=(row,name)=>row.match(new RegExp('<input name="'+name+'"[^>]*>'))?.[0] || '';
 nodes.c={id:'c',type:'j',parent:'t',name:'펌프 점검',mode:'human',result_block:'checklist',confirmation_items:[{id:'pump',name:'누수 없음'}],inputs:[{id:'pressure',name:'압력',type:'number',scope:'run'}]};
 nodes.d={id:'d',type:'j',parent:'t',name:'외관 확인',mode:'human',result_block:'human_confirm',inputs:[{id:'memo',name:'비고',type:'text',scope:'run'}]};
 h.state.run.jobs.c={status:'completed',can_decide:true,can_execute:true,attempt_id:'ct',current_attempt:'ct',decisions:{pump:{item_id:'pump',verdict:'completed',actor_id:'actor'}}};
 h.state.run.jobs.d={status:'ready',can_decide:false,can_execute:true};
 const open=id=>{h.api.setSelection({...h.api.snapshot().selection,stage_evidence:id});return h.row(id);};
 // every item ticked: no tick and no answer is left on the row, so nothing would save the field
 assert.match(field(open('c'),'pressure'),/ disabled/);
 // a person who may not answer the job
 assert.match(field(open('d'),'memo'),/ disabled/);
 // a tool job that may not run now
 h.state.run.jobs.a.can_execute=false;assert.match(field(open('a'),'page-id'),/ disabled/);h.state.run.jobs.a.can_execute=true;
 // still open: a tick to make, an answer to give, a run that is waiting for an earlier job's value
 h.state.run.jobs.c={status:'ready',can_decide:true,can_execute:true};assert.doesNotMatch(field(open('c'),'pressure'),/ disabled/);
 h.state.run.jobs.d.can_decide=true;assert.doesNotMatch(field(open('d'),'memo'),/ disabled/);
 nodes.b.inputs=[{id:'limit',name:'건수',type:'number',scope:'run'}];assert.match(open('b'),/<span>대기<\/span>/);assert.doesNotMatch(field(open('b'),'limit'),/ disabled/);
});
test('values of a job (second review): changed values with the answer someone else gave are sent as a new answer',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'펌프 상태 기록',mode:'human',result_block:'human_confirm',inputs:[{id:'pressure',name:'압력',type:'number',scope:'run'}]};
 h.state.run.inputs={pressure:3.1};h.state.run.attempts=[{id:'c1',job_id:'c',number:1,status:'succeeded',actor_id:'other'}];
 // another person answered 미흡; saving a value does not mark that answer for review
 h.state.run.jobs.c={status:'failed',can_decide:true,can_execute:true,attempt_id:'c1',current_attempt:'c1',result_revision:1,decisions:{job:{item_id:'job',verdict:'failed',result_revision:1,attempt_id:'c1',actor_id:'other'}}};
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'c'});
 replies(h,call=>{if(call.body?.action==='save_inputs')h.state.run.inputs=call.body.inputs;});
 h.type('c','pressure','2.4','number');
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'failed'}});
 assert.deepEqual(h.sent('save_inputs','human_confirm').map(body=>body.action+(body.verdict?':'+body.verdict:'')),['save_inputs','human_confirm:failed']);
 // with nothing changed, the same answer is still nothing to do
 await h.api.handleClick({dataset:{action:'stage_decide',jobId:'c',verdict:'failed'}});assert.equal(h.sent('human_confirm').length,1);
});
test('values of a job (second review): running a stage saves the values of the jobs it runs, not a person\'s',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.c={id:'c',type:'j',parent:'t',name:'외관 확인',mode:'human',result_block:'human_confirm',inputs:[{id:'memo',name:'비고',type:'text',scope:'run'}]};
 h.state.run.jobs.c={status:'completed',can_decide:true,can_execute:true,decisions:{job:{item_id:'job',verdict:'completed'}}};
 h.type('a','page-id','27182');h.type('c','memo','고쳐 둔 메모');replies(h);
 await h.api.handleClick({dataset:{action:'execute_scope',nodeId:'t'}});
 assert.deepEqual(h.sent('save_inputs').map(body=>body.inputs),[{'page-id':'27182'}],'the answered person job is not sent back for review by a stage run');
 assert.equal(h.sent('execute_scope').length,1);
});
test('values of a job (second review): a job placed directly under the procedure keeps its question in the start form',()=>{
 const definition={nodes:{p:{id:'p',type:'p'},t:{id:'t',type:'t',parent:'p'},
  loose:{id:'loose',type:'j',parent:'p',mode:'human',result_block:'human_confirm',inputs:[{id:'note',name:'메모',type:'text',scope:'run'}]},
  staged:{id:'staged',type:'j',parent:'t',mode:'human',result_block:'human_confirm',inputs:[{id:'lot',name:'LOT',type:'text',scope:'run'}]}}};
 assert.equal(html('workRunStartFields(definition).map(field=>field.id).join()',{definition}),'note');
});
// ---- The PR's automated review (Codex, PR #153, 2026-11-19). Each failed before its fix. ----
test('values of a job (PR review): a tool result is not confirmed or answered while its values were changed under the row',async()=>{
 const h=askFixture(),nodes=h.state.run.definition.nodes;
 nodes.b.inputs=[{id:'limit',name:'표시할 문서 수',type:'number',scope:'run'}];nodes.b.api_binding.inputs.limit={input:'limit'};
 h.state.run.inputs={'page-id':'27182',limit:5};
 Object.assign(h.state.run.jobs.a,{status:'completed',decisions:{job:{item_id:'job',verdict:'completed'}},result:{items:[{id:'r',row:{id:'27182'}}]}});
 Object.assign(h.state.run.jobs.b,{status:'waiting_confirmation',attempt_id:'bt',current_attempt:'bt',result_revision:1,result:{items:[{id:'r1',row:{title:'주간 점검표',id:'301'}}]}});
 h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'b'});
 replies(h,call=>{if(call.body?.action==='save_inputs'){h.state.run.inputs=call.body.inputs;h.state.run.jobs.b.status='review_required';}});
 h.type('b','limit','10','number');
 await h.api.handleClick({dataset:{action:'stage_confirm_list',jobId:'b'}});
 assert.deepEqual(h.sent('save_inputs','confirm_list').map(body=>body.action),['save_inputs'],'the changed value is saved and the old list is not confirmed');
 assert.deepEqual(h.sent('save_inputs')[0].inputs,{'page-id':'27182',limit:10});assert.doesNotMatch(h.row('b'),/stage_confirm_list/);
 // a tool job's answer the same way
 const t=askFixture();t.state.run.inputs={'page-id':'111'};
 Object.assign(t.state.run.jobs.a,{status:'waiting_confirmation',attempt_id:'at',current_attempt:'at',result_revision:1,result:{items:[{id:'r',row:{id:'111'}}]}});
 t.api.setSelection({...t.api.snapshot().selection,stage_evidence:'a'});
 replies(t,call=>{if(call.body?.action==='save_inputs'){t.state.run.inputs=call.body.inputs;t.state.run.jobs.a.status='review_required';}});
 t.type('a','page-id','222');
 await t.api.handleClick({dataset:{action:'stage_decide',jobId:'a',verdict:'completed'}});
 assert.deepEqual(t.sent('save_inputs','decide','human_confirm').map(body=>body.action),['save_inputs']);
 // with nothing changed the answer goes as before
 const u=askFixture();u.state.run.inputs={'page-id':'111'};
 Object.assign(u.state.run.jobs.a,{status:'waiting_confirmation',attempt_id:'at',current_attempt:'at',result_revision:1,result:{items:[{id:'r',row:{id:'111'}}]}});
 replies(u);await u.api.handleClick({dataset:{action:'stage_decide',jobId:'a',verdict:'completed'}});
 assert.deepEqual(u.sent('save_inputs','decide').map(body=>body.action),['decide']);
});
test('values of a job (PR review): a value someone else saved in between is shown before it is overwritten',async()=>{
 const h=askFixture();h.state.run.inputs={'page-id':'111'};h.api.setSelection({...h.api.snapshot().selection,stage_evidence:'a'});
 h.type('a','page-id','222');
 h.state.run.inputs={'page-id':'333'};h.state.run.revision=9;replies(h);
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.deepEqual(h.sent('save_inputs','execute_job'),[],'nothing is saved over the other value and nothing runs');
 assert.match(h.row('a'),/type="text" value="222"><small class="ew-vd-ask-error" id="ew-stage-a-page-id-error" role="alert">다른 사람이 바꾼 값 · 333<\/small>/);
 // pressed again after seeing it, the typed value is saved and the job runs
 await h.api.handleClick({dataset:{action:'stage_execute',jobId:'a'}});
 assert.deepEqual(h.sent('save_inputs','execute_job').map(body=>body.action),['save_inputs','execute_job']);assert.deepEqual(h.sent('save_inputs')[0].inputs,{'page-id':'222'});
});
test('check items: before a run and for someone who may not act, the list is shown but cannot be ticked',()=>{
 const h=checkListFixture();h.state.run.jobs.h.can_decide=false;
 assert.equal([...h.row().matchAll(/<input type="checkbox" data-stage-check[^>]* disabled data-own-disabled="true">/g)].length,2);
 const preview=stagePreviewFixture(),nodes=preview.state.workflow.published.nodes;Object.assign(nodes.h,{result_block:'checklist',confirmation_items:[{id:'pump',name:'펌프 누수 없음'}]});
 const body=html('workStageHTML(state,selection,workPublishedDefinition(state).nodes.t).body',{state:preview.state,selection:{stage_id:'t'}}),row=body.match(/<section class="ew-vd-entry[^>]*data-stage-job="h"[\s\S]*?<\/section>/)[0];
 assert.match(row,/<input type="checkbox" data-stage-check data-job-id="h" data-item-id="pump" disabled data-own-disabled="true"><span>펌프 누수 없음<\/span>/);assert.match(row,/0 \/ 1/);
});
test('check items: a list without items and a tool check list behave as before',()=>{
 const empty=checkListFixture();empty.state.run.definition.nodes.h.confirmation_items=[];assert.doesNotMatch(empty.row(),/ew-vd-checks|ew-vd-count/);
 assert.equal(html('workHumanCheckItems(node).length',{node:{mode:'tool',result_block:'checklist',confirmation_items:[{id:'a',name:'하나'}]}}),0);
 assert.equal(html('workHumanCheckItems(node).length',{node:{result_block:'human_confirm',confirmation_items:[{id:'a',name:'하나'}]}}),0);
 assert.equal(html('workHumanCheckItems(node).map(item=>item.id).join()',{node:{result_block:'checklist',confirmation_items:[{id:'a',name:'하나'},{id:'b',name:' '},null]}}),'a');
});
