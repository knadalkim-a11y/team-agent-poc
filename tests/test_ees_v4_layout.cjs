/* DOM lifecycle checks only; Native browser geometry is checked separately. */
const test=require('node:test'),assert=require('node:assert/strict');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
function dom(){
 const ids=new Map();let doc;
 function element(id=''){
  const classes=new Set(),events=new Map();let html='';
  const el={id,dataset:{},style:{setProperty(name,value){this[name]=String(value);},removeProperty(name){delete this[name];}},children:[],parentElement:null,isConnected:false,hidden:false,scrollTop:0,attributes:{},classList:{add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value),toggle(value,force){const enabled=force===undefined?!classes.has(value):Boolean(force);if(enabled)classes.add(value);else classes.delete(value);return enabled;}},
   setAttribute(name,value){this.attributes[name]=String(value);},removeAttribute(name){delete this.attributes[name];},getAttribute(name){return name==='id'?this.id:this.attributes[name] ?? null;},hasAttribute(name){return name==='id'?Boolean(this.id):Object.hasOwn(this.attributes,name);},querySelector(selector){return ids.get(selector.slice(1)) || null;},querySelectorAll(selector){return selector==='button,input,select,textarea,a,summary,[data-ees-panel-resize]'?(this.mockControls || []):[];},contains(target){return target===this||this.children.includes(target)||(this.mockControls || []).includes(target);},
   append(child){child.remove();child.parentElement=this;child.isConnected=true;this.children.push(child);if(child.id)ids.set(child.id,child);},prepend(child){this.append(child);this.children.splice(this.children.indexOf(child),1);this.children.unshift(child);},
   remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;this.isConnected=false;},
   insertAdjacentElement(_,child){this.parentElement.append(child);},focus(){doc.activeElement=this;},addEventListener(type,fn){events.set(type,fn);},dispatch(type){events.get(type)?.({target:this});},showModal(){this.open=true;},close(){this.open=false;events.get('close')?.();},matches:()=>false};
  Object.defineProperty(el,'innerHTML',{get:()=>html,set(value){html=value;if(el.replaceControls)el.mockControls=el.replaceControls();for(const match of value.matchAll(/id="([^"]+)"/g)){if(!ids.has(match[1]))ids.set(match[1],element(match[1]));}if(value.includes('data-dialog-close')){const cancel=element('cancel');el.querySelector=selector=>selector==='[data-dialog-close]'?cancel:selector==='[data-dialog-confirm]'?element('confirm'):ids.get(selector.slice(1)) || null;} }});
  Object.defineProperty(el,'firstChild',{get:()=>el.children[0] || (html?{}:null)});if(id)ids.set(id,el);return el;
 }
 const body=element('body'),sidebar=element('sidebar'),anchorParent=element('anchor-parent'),anchor=element('sidebar-search-button'),row=element('row'),column=element('native-column'),pane=element('chat-pane');
 body.isConnected=true;body.append(sidebar);sidebar.append(anchorParent);anchorParent.append(anchor);body.append(row);row.append(column);column.append(pane);
 doc={body,activeElement:body,createElement:()=>element(),querySelector:selector=>selector==='#chat-container #chat-pane'?pane:ids.get(selector.slice(1)) || null,querySelectorAll:selector=>selector==='nav'?[]:[],getElementById:id=>ids.get(id)};
 const context=renderer({document:doc});return {context,ids,body,row,column,pane,document:doc,element};
}
const snapshot=(patch={})=>({state:{capabilities:{actor_id:'a'},systems:['EMS'],factories:[],workflows:[],runs:[],my_work:[]},selection:{mode:'work',tab:'my_work',panel_open:true,system_id:'EMS',factory_id:'',...patch}});
test('Native conversation remains the original center DOM while the work panel mounts after it',()=>{const h=dom();const view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());assert.equal(h.row.children[0],h.column);assert.equal(h.row.children[1].id,'ees-work-panel');assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),true);assert.match(h.ids.get('ees-work-entry').innerHTML,/전체 공장/);});
test('closing or changing work mode preserves Native chat and the authoring mount boundary',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());view.render(snapshot({panel_open:false}));assert.equal(h.ids.get('ees-work-panel').hidden,true);assert.equal(h.pane.parentElement,h.column);const author=snapshot({mode:'author',panel_open:true});author.state.capabilities.can_author=true;view.render(author);assert.ok(view.authoringHost());assert.equal(h.pane.parentElement,h.column);view.reset();assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),false);});
test('Native shell mounts only the EES menu with the verified sidebar anchor and no chat pane',()=>{
 const h=dom(),original=h.document.querySelector;h.document.querySelector=selector=>selector==='#chat-container #chat-pane'?null:original(selector);h.context.location.pathname='/workspace/skills';h.context.location.search='';const view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot();value.native_shell=true;value.native_id='skills';value.state.capabilities={actor_id:'a',can_author:true,native_access_available:true,native_access:{skills:true,models:false,knowledge:false,prompts:false,tools:false,admin:false}};view.render(value);const entry=h.ids.get('ees-work-entry');assert.equal(entry.isConnected,true);assert.match(entry.innerHTML,/업무 만들기/);assert.match(entry.innerHTML,/data-native-id="skills"[^>]*aria-current="page"/);assert.doesNotMatch(entry.innerHTML,/AI 설정|관리자만|native_return/);assert.equal(h.ids.has('ees-work-panel'),false);assert.equal(h.ids.has('ees-work-context'),false);assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),false);
});
test('Native shell suspends chat layout and restores the same panel and Native chat nodes on return',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({mode:'author'});value.state.capabilities.can_author=true;view.render(value);const panel=h.ids.get('ees-work-panel'),entry=h.ids.get('ees-work-entry'),original=h.document.querySelector;h.document.querySelector=selector=>selector==='#chat-container #chat-pane'?null:original(selector);h.context.location.pathname='/workspace/models';h.context.location.search='';view.render({...value,native_shell:true,native_id:'models'});assert.equal(entry.isConnected,true);assert.equal(panel.isConnected,false);assert.equal(h.column.classList.contains('ees-integrated-chat'),false);assert.equal(h.pane.parentElement,h.column);h.document.querySelector=original;h.context.location.pathname='/c/original';view.render(value);assert.equal(h.ids.get('ees-work-panel'),panel);assert.equal(panel.parentElement,h.row);assert.equal(h.ids.get('ees-work-entry'),entry);assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),true);
});
test('Native capability refresh cannot turn untouched hidden run inputs into an incomplete draft',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});
 value.state.operations={};value.state.run={id:'r',revision:3,status:'open',inputs:{visible:'saved',hidden:'keep'},definition:{nodes:{j:{id:'j',name:'job',type:'j',mode:'human',inputs:[{id:'visible',name:'Input',type:'text'}]}}},jobs:{j:{can_execute:true}}};
 view.render(value);const form=h.ids.get('ees-work-inputs'),field={name:'visible',value:'saved',type:'text',disabled:false,dataset:{workInput:''}};form.dataset={settings:'false',revision:'3'};form.querySelectorAll=selector=>selector==='[data-work-input]'?[field]:[];
 assert.equal(view.readInputs().dirty,false);
 const native={...value,state:{...value.state,run:null,workflow:null},native_shell:true,native_id:'skills'};
 view.render(native);assert.equal(h.ids.get('ees-work-panel').isConnected,false);view.render(native);view.render(value);
 const returned=view.readInputs();assert.deepEqual(JSON.parse(JSON.stringify(returned.inputs)),{visible:'saved',hidden:'keep'});assert.equal(returned.dirty,false);assert.equal(returned.conflict,false);
});
test('missing sidebar anchor leaves Native screen untouched and creates no EES shell',()=>{
 const h=dom(),original=h.document.querySelector;h.document.querySelector=selector=>['#sidebar-search-button','#chat-container #chat-pane'].includes(selector)?null:original(selector);h.context.location.pathname='/workspace/skills';h.context.location.search='';const children=[...h.body.children],view=run(h.context,'createWorkView({callbacks:{}})');view.render({...snapshot(),native_shell:true,native_id:'skills'});assert.deepEqual(h.body.children,children);assert.equal(h.ids.has('ees-work-entry'),false);assert.equal(h.ids.has('ees-work-panel'),false);assert.equal(h.body.dataset.eesIntegrated,undefined);
});
test('panel scroll restores per personal target and never writes a shared run selection',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());h.ids.get('ees-work-content').scrollTop=157;view.render(snapshot({tab:'records'}));h.ids.get('ees-work-content').scrollTop=22;view.render(snapshot());assert.equal(h.ids.get('ees-work-content').scrollTop,157);assert.equal(h.context.document.body.dataset.eesIntegrated,'true');});
test('confirmation dialog starts on cancel and Escape closure never accepts the command',async()=>{const h=dom();const waiting=run(h.context,'workUI.dialog({title:"요청 확인",html:"<p>대상</p>",confirmLabel:"요청"})');const dialog=h.body.children.find(item=>item.id==='ees-work-dialog');assert.equal(h.document.activeElement.id,'cancel');dialog.dispatch('cancel');dialog.close();assert.equal(await waiting,false);assert.equal(h.document.activeElement,h.body);});


test('workspace refresh retains active input identity and text selection without taking Native focus',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());const host=h.ids.get('ees-work-panel'),field=h.element('input-original');field.id='ew-run-evidence';field.setAttribute('name','evidence');field.selectionStart=2;field.selectionEnd=5;field.selectionDirection='forward';host.mockControls=[field];field.focus();let replacement;host.replaceControls=()=>{replacement=h.element('ew-run-evidence');replacement.setAttribute('name','evidence');replacement.setSelectionRange=(start,end,direction)=>{replacement.range=[start,end,direction];};return [replacement];};view.render(snapshot());assert.equal(h.document.activeElement,replacement);assert.deepEqual(replacement.range,[2,5,'forward']);h.pane.focus();view.render(snapshot());assert.equal(h.document.activeElement,h.pane);});


test('published procedure overview opens before a run exists without dereferencing run state',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',tab:'overview'});value.state.workflow={id:'w',name:'게시한 절차',published_version:1,published:{nodes:{p:{id:'p',type:'p',children:['j']},j:{id:'j',type:'j',parent:'p',mode:'tool',name:'조회'}}}};view.render(value);assert.match(h.ids.get('ees-work-panel').innerHTML,/data-action="start_run"/);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/data-action="execute_scope"/);});


test('workspace navigation separates managed-system authoring from work scope and actual tasks',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({mode:'author'});value.state.capabilities={actor_id:'a',managed_systems:['EMS'],can_author:true,native_access_available:true,native_access:{models:false,knowledge:false,prompts:false,skills:true,tools:false,admin:false}};value.state.workflows=[{id:'w',name:'저장된 편집',system_id:'EMS',category:'ops',updated_at:'2026-10-02'}];view.render(value);const nav=h.ids.get('ees-work-entry').innerHTML;assert.match(nav,/관리 시스템/);assert.match(nav,/최근 편집/);assert.match(nav,/저장된 편집/);assert.match(nav,/스킬·지침/);assert.doesNotMatch(nav,/data-action="my_work"|전체 공장/);assert.equal(h.ids.get('ees-work-panel').dataset.eesMode,'author');});

test('polling preserves an explicit model choice only for its actor and work target while revocation clears it',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});
 value.state.run={id:'r',revision:1,status:'open',inputs:{},definition:{nodes:{j:{id:'j',type:'j',mode:'ai',result_block:'ai_review',inputs:[]}}},jobs:{j:{}}};value.state.operations={models:[{id:'first'},{id:'chosen'}]};
 view.render(value);h.ids.get('ees-work-execution-model').value='chosen';view.render(value);assert.match(h.ids.get('ees-work-panel').innerHTML,/value="chosen" selected/);
 const revoked=JSON.parse(JSON.stringify(value));revoked.state.operations.models=[{id:'first'}];view.render(revoked);view.render(value);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/value="chosen" selected/);
 h.ids.get('ees-work-execution-model').value='chosen';view.render(value);const differentRun=JSON.parse(JSON.stringify(value));differentRun.selection.run_id='another';differentRun.state.run.id='another';view.render(differentRun);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/value="chosen" selected/);
 view.render(value);const other=JSON.parse(JSON.stringify(value));other.state.capabilities.actor_id='other';view.render(other);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/value="chosen" selected/);
 view.reset();view.render(value);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/value="chosen" selected/);
});

test('a delayed workspace read never rolls private UI revision behind a completed width save',async()=>{
 const h=controller(),operations=deferred(),started=deferred();let revision=0,waiting=true;
 h.setReply(call=>{
  if(call.body?.action==='save_ui'){if(call.body.expected_revision!==revision)return {httpError:true,status:409,error:{message:'revision conflict'}};revision++;return {ok:true,revision};}
  if(call.url.startsWith('/api/ees-work/workspace?'))return {ok:true,systems:[],workflows:[],runs:[],ui_state:{revision,state:{}}};
  if(waiting&&call.url.startsWith('/api/ees-work/operations?')){started.resolve();return operations.promise;}
  return {ok:true};
 });
 const reading=h.api.refresh();await started.promise;
 h.view.callbacks.panelWidth(640);[...h.timers.values()].at(-1)();await new Promise(setImmediate);assert.equal(revision,1);
 waiting=false;operations.resolve({ok:true});await reading;
 h.view.callbacks.panelWidth(720);[...h.timers.values()].at(-1)();await new Promise(setImmediate);
 assert.deepEqual(h.calls.filter(c=>c.body?.action==='save_ui').map(c=>c.body.expected_revision),[0,1]);assert.equal(revision,2);
 // A different Native identity starts from its own revision, not the maximum
 // of another account's acknowledged preferences.
 h.api.reset();h.setAuth('actor-b-token');h.api.setIdentity();revision=0;await h.api.refresh();
 h.view.callbacks.panelWidth(400);[...h.timers.values()].at(-1)();await new Promise(setImmediate);
 assert.equal(h.calls.filter(c=>c.body?.action==='save_ui').at(-1).body.expected_revision,0);assert.equal(revision,1);
});
test('an explicit early panel resize wins over an older saved width and stays actor scoped',async()=>{
 const h=controller();h.api.setRestored(false);h.view.callbacks.panelWidth(640);
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,systems:[],workflows:[],runs:[],ui_state:{revision:5,state:{selection:{panel_width:720,tab:'my_work'}}}}:{ok:true});
 await h.api.refresh();assert.equal(h.api.snapshot().selection.panel_width,640);
 h.api.reset();h.setAuth('actor-b-token');h.api.setIdentity();
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,systems:[],workflows:[],runs:[],ui_state:{revision:1,state:{selection:{panel_width:400}}}}:{ok:true});
 await h.api.refresh();assert.equal(h.api.snapshot().selection.panel_width,400);
});

test('a width conflict retries only that preference while preserving another tab private draft',async()=>{
 const h=controller(),stored={selection:{tab:'current',panel_width:480,verdict_drafts:{other:{item:{verdict:'pending'}}},start_inputs:{other:{name:'keep'}}},other:'preserved'};let saves=0;
 h.setReply(call=>{if(call.body?.action==='save_ui'){saves++;return saves===1?{httpError:true,status:409,error:{code:'revision_conflict',message:'changed'}}:{ok:true,revision:2};}return {ok:true,ui_state:{revision:1,state:stored}};});
 h.view.callbacks.panelWidth(640);[...h.timers.values()].at(-1)();await new Promise(setImmediate);
 const writes=h.calls.filter(c=>c.body?.action==='save_ui');assert.equal(writes.length,2);assert.equal(writes[1].body.expected_revision,1);assert.deepEqual(writes[1].body.state,{...stored,selection:{...stored.selection,panel_width:640}});
});
test('width conflict recovery stops on account change and never retries twice',async()=>{
 const h=controller(),read=deferred(),started=deferred();let saves=0;
 h.setReply(call=>{if(call.body?.action==='save_ui'){saves++;return {httpError:true,status:409,error:{code:'revision_conflict',message:'changed'}};}started.resolve();return read.promise;});
 h.view.callbacks.panelWidth(640);[...h.timers.values()].at(-1)();await started.promise;h.setAuth('other-token');h.api.reset();h.api.setIdentity();read.resolve({ok:true,ui_state:{revision:8,state:{selection:{panel_width:400}}}});await new Promise(setImmediate);assert.equal(saves,1);
 const second=controller();second.setReply(call=>call.body?{httpError:true,status:409,error:{code:'revision_conflict',message:'changed again'}}:{ok:true,ui_state:{revision:2,state:{selection:{}}}});
 second.view.callbacks.panelWidth(720);[...second.timers.values()].at(-1)();await new Promise(setImmediate);assert.equal(second.calls.filter(c=>c.body).length,2);assert.match(second.api.snapshot().error,/자동 저장 실패/);assert.equal(second.api.snapshot().selection.panel_width,720);
});

// Execute the source app.html gate that the pinned build applies, rather than a
// separately maintained copy of its timing or route logic.
function startupGate({pathname='/',search='',token='fixture-token',storageError=false,execute=true}={}){
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
 const patch=fs.readFileSync(path.join(__dirname,'../frontend/patches/0001-ees-native-hooks.patch'),'utf8');
 const added=patch.split(/\r?\n/).filter(line=>line.startsWith('+')&&!line.startsWith('+++')).map(line=>line.slice(1)).join('\n');
 const scripts=[...added.matchAll(/<script id="ees-startup-gate">([\s\S]*?)<\/script>/g)];
 assert.equal(scripts.length,1,'The exact source app.html startup gate must be present once');
 const css=added.match(/<style id="ees-startup-style">([\s\S]*?)<\/style>/)?.[1];
 assert.match(css,/html\[data-ees-startup='pending'\] body \*\s*\{ visibility: hidden !important; \}/);
 const dataset={},timers=new Map(),listeners=new Map();let id=0,now=0;
 const window={addEventListener(type,callback){listeners.set(type,callback);},removeEventListener(type,callback){if(listeners.get(type)===callback)listeners.delete(type);},dispatchEvent(event){listeners.get(event.type)?.(event);}};
 const context={document:{documentElement:{dataset}},location:{pathname,search},URLSearchParams,window,localStorage:{getItem(){if(storageError)throw Error('Storage unavailable');return token;}},setTimeout(callback,ms){const key=++id;timers.set(key,{at:now+ms,callback});return key;},clearTimeout:key=>timers.delete(key)};
 if(execute)vm.runInNewContext(scripts[0][1],context);
 return {dataset,window,context,timers,listeners,advance(ms){now+=ms;for(const [key,timer] of [...timers])if(timer.at<=now){timers.delete(key);timer.callback();}}};
}
test('source head gate hides root and existing conversation until successful EES layout',()=>{
 for(const pathname of ['/','/c/existing-chat','/c/existing-chat/']){
  const h=startupGate({pathname});assert.equal(h.dataset.eesStartup,'pending');
  h.advance(3999);assert.equal(h.dataset.eesStartup,'pending');
  h.window.dispatchEvent({type:'ees:startup-ready'});assert.equal(h.dataset.eesStartup,undefined);assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);
  h.context.location.pathname='/c/another-chat';h.window.dispatchEvent({type:'popstate'});assert.equal(h.dataset.eesStartup,undefined,'SPA navigation does not re-arm a completed gate');
 }
});
test('missing launcher and stalled API always fail open at the independent four-second bound',()=>{
 for(const pathname of ['/','/c/existing-chat']){
  const h=startupGate({pathname});assert.equal(h.dataset.eesStartup,'pending');
  h.advance(4000);assert.equal(h.dataset.eesStartup,undefined);assert.equal(h.listeners.size,0);
  h.window.dispatchEvent({type:'ees:startup-ready'});assert.equal(h.dataset.eesStartup,undefined);
 }
});
test('Native routes, signed-out or unavailable storage and disabled JavaScript are never hidden',()=>{
 for(const pathname of ['/auth','/logout','/workspace/models','/admin/settings','/c/extra/path','/s/shared'])assert.equal(startupGate({pathname}).dataset.eesStartup,undefined,pathname);
 for(const options of [{search:'?settings=admin:general'},{token:''},{storageError:true},{execute:false}])assert.equal(startupGate(options).dataset.eesStartup,undefined,JSON.stringify(options));
});
test('launcher releases startup only after a completed view and authoring render',async()=>{
 const h=controller(),events=[];h.context.document.documentElement.dataset={eesStartup:'pending'};h.context.Event=class{constructor(type){this.type=type;}};
 h.context.window.dispatchEvent=event=>events.push(event.type);
 h.api.setSelection({mode:'author'});
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'a',can_author:true},systems:[],workflows:[],runs:[],ui_state:{revision:0,state:{}}}:{ok:true});
 const order=[];h.view.render=()=>{order.push('view');return true;};h.designer.render=()=>{order.push('designer');assert.equal(events.length,0);};
 await h.api.refresh();assert.deepEqual(order,['view','designer']);assert.deepEqual(events,['ees:startup-ready']);
});
test('a missing mount or throwing layout never reports successful startup',async()=>{
 for(const behavior of ['missing','exception']){
  const h=controller(),events=[];h.context.document.documentElement.dataset={eesStartup:'pending'};h.context.Event=class{constructor(type){this.type=type;}};h.context.window.dispatchEvent=event=>events.push(event.type);
  h.view.render=()=>{if(behavior==='exception')throw Error('layout_failed');return false;};
  if(behavior==='exception')await assert.rejects(h.api.refresh(),/layout_failed/);else await h.api.refresh();
  assert.deepEqual(events,[],behavior);assert.equal(h.context.document.documentElement.dataset.eesStartup,'pending');
 }
});
test('view completion signal follows actual mount success and the creation card states current capability exactly',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');assert.equal(view.render(snapshot()),true);
 const original=h.document.querySelector;h.document.querySelector=selector=>selector==='#sidebar-search-button'?null:original(selector);assert.equal(view.render(snapshot()),false);assert.equal(view.sync(snapshot()),false);
 const card=run(h.context,'workProcedureStartHTML({kind:"new"})');
 assert.ok(card.includes('새 업무 절차는 비슷한 예시를 복사해 고치는 것이 가장 쉽습니다. 오른쪽에서 예시를 고르거나 빈 절차로 시작하세요. 만드는 방법이 궁금하면 아래 질문을 보내 보세요. 지금은 대화 내용으로 초안을 바로 만들지는 않습니다. 초안은 게시하기 전까지 업무 화면에 나타나지 않습니다.'));
 assert.doesNotMatch(card,/하시는 일을 순서대로 말해 주시면/);
});
