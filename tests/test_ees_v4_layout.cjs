/* DOM lifecycle checks only; Native browser geometry is checked separately. */
const test=require('node:test'),assert=require('node:assert/strict');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
function dom(extra={}){
 const ids=new Map();let doc;
 function element(id=''){
  const classes=new Set(),events=new Map();let html='';
  const el={id,dataset:{},style:{setProperty(name,value){this[name]=String(value);},removeProperty(name){delete this[name];}},children:[],parentElement:null,isConnected:false,hidden:false,scrollTop:0,attributes:{},classList:{add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value),toggle(value,force){const enabled=force===undefined?!classes.has(value):Boolean(force);if(enabled)classes.add(value);else classes.delete(value);return enabled;}},
   setAttribute(name,value){this.attributes[name]=String(value);},removeAttribute(name){delete this.attributes[name];},getAttribute(name){return name==='id'?this.id:this.attributes[name] ?? null;},hasAttribute(name){return name==='id'?Boolean(this.id):Object.hasOwn(this.attributes,name);},querySelector(selector){return ids.get(selector.slice(1)) || null;},querySelectorAll(selector){return selector==='button,input,select,textarea,a,summary,[data-ees-panel-resize]'?(this.mockControls || []):[];},contains(target){return target===this||this.children.includes(target)||(this.mockControls || []).includes(target);},
   append(child){child.remove();child.parentElement=this;child.isConnected=true;this.children.push(child);if(child.id)ids.set(child.id,child);},prepend(child){this.append(child);this.children.splice(this.children.indexOf(child),1);this.children.unshift(child);},
   replaceChildren(){this.children=[];html='';},remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;this.isConnected=false;},
   insertAdjacentElement(_,child){this.parentElement.append(child);},focus(){doc.activeElement=this;},getBoundingClientRect:()=>({left:0,right:360,top:0,bottom:30,width:360,height:100}),addEventListener(type,fn){events.set(type,fn);},removeEventListener(type,fn){if(events.get(type)===fn)events.delete(type);},dispatch(type,event={}){events.get(type)?.({target:this,...event});},showModal(){this.open=true;},close(){this.open=false;events.get('close')?.();},matches:()=>false};
  Object.defineProperty(el,'innerHTML',{get:()=>html,set(value){html=value;if(el.replaceControls)el.mockControls=el.replaceControls();for(const match of value.matchAll(/id="([^"]+)"/g)){if(!ids.has(match[1]))ids.set(match[1],element(match[1]));}if(value.includes('data-dialog-close')){const cancel=element('cancel');el.querySelector=selector=>selector==='[data-dialog-close]'?cancel:selector==='[data-dialog-confirm]'?element('confirm'):ids.get(selector.slice(1)) || null;}if(value.includes('data-help-close')){const controls=Object.fromEntries(['close','ask','error'].map(name=>['[data-help-'+name+']',element('help-'+name)]));el.querySelector=selector=>controls[selector] || ids.get(selector.slice(1)) || null;} }});
  Object.defineProperty(el,'firstChild',{get:()=>el.children[0] || (html?{}:null)});if(id)ids.set(id,el);return el;
 }
 const body=element('body'),sidebar=element('sidebar'),anchorParent=element('anchor-parent'),anchor=element('sidebar-search-button'),row=element('row'),column=element('native-column'),pane=element('chat-pane');
 body.isConnected=true;body.append(sidebar);sidebar.append(anchorParent);anchorParent.append(anchor);body.append(row);row.append(column);column.append(pane);
 doc={body,activeElement:body,createElement:()=>element(),querySelector:selector=>selector==='#chat-container #chat-pane'?pane:ids.get(selector.slice(1)) || null,querySelectorAll:selector=>selector==='nav'?[]:[],getElementById:id=>ids.get(id)};
 const panel=element('ees-work-panel'),overlays=element('ees-work-overlays');row.append(panel);body.append(overlays);const published=[];
 const context=renderer({...extra,document:doc});context.window.__eesSourceShellV1={hosts:()=>({panel,overlays}),publish:value=>published.push(value)};return {context,ids,body,row,column,pane,panel,overlays,published,document:doc,element};
}
const snapshot=(patch={})=>({state:{capabilities:{actor_id:'a'},systems:['EMS'],factories:[],workflows:[],runs:[],my_work:[]},selection:{mode:'work',tab:'my_work',panel_open:true,system_id:'EMS',factory_id:'',...patch}});
test('legacy content uses only the source-supplied right slot without mutating Native nodes',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),before=[...h.row.children];view.render(snapshot());assert.deepEqual(h.row.children,before);assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),false);assert.equal(h.ids.has('ees-work-entry'),false);assert.match(h.panel.innerHTML,/내 업무/);assert.equal(h.published.at(-1).context_title,'대화');});
test('panel visibility is source state and reset preserves source-owned mount boundary',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());view.render(snapshot({panel_open:false}));assert.equal(h.published.at(-1).selection.panel_open,false);assert.equal(h.panel.hidden,false);const author=snapshot({mode:'author',panel_open:true});author.state.capabilities.can_author=true;view.render(author);assert.ok(view.authoringHost());view.reset();assert.equal(h.pane.parentElement,h.column);assert.equal(h.panel.parentElement,h.row);assert.equal(h.panel.innerHTML,'');});
test('Native capability snapshots publish menu state without legacy menu or content rendering',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value={...snapshot(),native_shell:true,native_id:'skills'};value.state.capabilities={actor_id:'a',can_author:true,native_access_available:true,native_access:{skills:true}};view.render(value);assert.equal(h.published.at(-1).native_id,'skills');assert.equal(h.panel.innerHTML,'');assert.equal(h.ids.has('ees-work-entry'),false);assert.equal(h.ids.has('ees-work-context'),false);assert.equal(h.pane.parentElement,h.column);
});
test('Native navigation preserves the exact source panel and Native chat nodes',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({mode:'author'});value.state.capabilities.can_author=true;view.render(value);const body=h.panel.innerHTML;view.render({...value,native_shell:true,native_id:'models'});assert.equal(h.panel.parentElement,h.row);assert.equal(h.panel.innerHTML,body);assert.equal(h.pane.parentElement,h.column);view.render(value);assert.equal(h.panel.parentElement,h.row);assert.equal(h.pane.parentElement,h.column);
});
test('Native capability refresh cannot turn untouched hidden run inputs into an incomplete draft',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',run_id:'r',job_id:'j',tab:'current'});
 value.state.operations={};value.state.run={id:'r',revision:3,status:'open',inputs:{visible:'saved',hidden:'keep'},definition:{nodes:{j:{id:'j',name:'job',type:'j',mode:'human',inputs:[{id:'visible',name:'Input',type:'text'}]}}},jobs:{j:{can_execute:true}}};
 view.render(value);const form=h.ids.get('ees-work-inputs'),field={name:'visible',value:'saved',type:'text',disabled:false,dataset:{workInput:''}};form.dataset={settings:'false',revision:'3'};form.querySelectorAll=selector=>selector==='[data-work-input]'?[field]:[];
 assert.equal(view.readInputs().dirty,false);
 const native={...value,state:{...value.state,run:null,workflow:null},native_shell:true,native_id:'skills'};
 view.render(native);assert.equal(h.ids.get('ees-work-panel').isConnected,true);view.render(native);view.render(value);
 const returned=view.readInputs();assert.deepEqual(JSON.parse(JSON.stringify(returned.inputs)),{visible:'saved',hidden:'keep'});assert.equal(returned.dirty,false);assert.equal(returned.conflict,false);
});
test('missing source content slot fails closed without constructing a replacement around Native',()=>{
 const h=dom();h.context.window.__eesSourceShellV1.hosts=()=>({});const children=[...h.body.children],view=run(h.context,'createWorkView({callbacks:{}})');assert.equal(view.render({...snapshot(),native_shell:true,native_id:'skills'}),false);assert.deepEqual(h.body.children,children);assert.equal(h.ids.has('ees-work-entry'),false);assert.equal(h.body.dataset.eesIntegrated,undefined);
});
test('panel scroll restores per personal target and never writes a shared run selection',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());h.ids.get('ees-work-content').scrollTop=157;view.render(snapshot({tab:'records'}));h.ids.get('ees-work-content').scrollTop=22;view.render(snapshot());assert.equal(h.ids.get('ees-work-content').scrollTop,157);assert.equal(h.context.document.body.dataset.eesIntegrated,undefined);});
test('confirmation dialog starts on its body and Escape closure never accepts the command',async()=>{const h=dom();const waiting=run(h.context,'workUI.dialog({title:"요청 확인",html:"<p>대상</p>",confirmLabel:"요청"})');const dialog=h.overlays.children.find(item=>item.id==='ees-work-dialog');assert.equal(h.document.activeElement.id,'ees-work-dialog-body');dialog.dispatch('cancel');dialog.close();assert.equal(await waiting,false);assert.equal(h.document.activeElement,h.body);});
test('dialog capture closes nested help before closing the confirmation and cleans it on programmatic close',async()=>{
 const h=dom();h.context.window.innerHeight=800;const waiting=run(h.context,'workUI.dialog({title:"요청 확인",confirmLabel:"요청"})'),dialog=h.overlays.children.find(item=>item.id==='ees-work-dialog'),trigger=h.element('help-trigger');dialog.append(trigger);h.context.trigger=trigger;
 const show=()=>run(h.context,'workUI.showHelp({termId:"category",help:{terms:[{id:"category",name:"분류",summary:"절차 분류"}]},trigger})');let help=show();assert.equal(help.parentElement,dialog);
 // An ancestor capture listener runs before the focused help child's handler.
 dialog.dispatch('keydown',{target:h.document.activeElement,key:'Escape',preventDefault(){},stopPropagation(){}});
 assert.equal(dialog.open,true);assert.equal(help.isConnected,false);assert.equal(h.document.activeElement,trigger);
 help=show();dialog.close();assert.equal(help.isConnected,false);assert.equal(await waiting,false);
});
test('help footer sends question and visible context separately and follows Native response busy state',async()=>{
 const h=dom();h.context.window.innerHeight=800;let busy=true,sent;
 h.context.window.__eesSourceShellV1.helpState=()=>({busy});h.context.onAsk=async(question,context)=>{sent={question,context};return true;};
 const help=run(h.context,'workUI.showHelp({termId:"read_tool",help:{terms:[{id:"read_tool",name:"정보 읽기",summary:"읽기만 합니다"}]},context:{screen:"도구 작성",draftName:"점검 조회"},onAsk})'),button=help.querySelector('[data-help-ask]');
 assert.equal(button.disabled,true);busy=false;run(h.context,'workUI.syncHelpState()');assert.equal(button.disabled,false);button.dispatch('click');await new Promise(setImmediate);
 assert.equal(sent.question,'EES Workflow 도움말 ‘정보 읽기’의 뜻과 지금 화면에서 쓰는 방법을 알려줘.');assert.deepEqual(JSON.parse(JSON.stringify(sent.context)),{screen:'도구 작성',draftName:'점검 조회',term_id:'read_tool'});assert.equal(help.isConnected,false);
});


test('workspace refresh retains active input identity and text selection without taking Native focus',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());const host=h.ids.get('ees-work-panel'),field=h.element('input-original');field.id='ew-run-evidence';field.setAttribute('name','evidence');field.selectionStart=2;field.selectionEnd=5;field.selectionDirection='forward';host.mockControls=[field];field.focus();let replacement;host.replaceControls=()=>{replacement=h.element('ew-run-evidence');replacement.setAttribute('name','evidence');replacement.setSelectionRange=(start,end,direction)=>{replacement.range=[start,end,direction];};return [replacement];};view.render(snapshot());assert.equal(h.document.activeElement,replacement);assert.deepEqual(replacement.range,[2,5,'forward']);h.pane.focus();view.render(snapshot());assert.equal(h.document.activeElement,h.pane);});


test('published procedure overview opens before a run exists without dereferencing run state',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',tab:'overview'});value.state.workflow={id:'w',name:'게시한 절차',published_version:1,published:{nodes:{p:{id:'p',type:'p',children:['j']},j:{id:'j',type:'j',parent:'p',mode:'tool',name:'조회'}}}};view.render(value);assert.match(h.ids.get('ees-work-panel').innerHTML,/data-action="start_run"/);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/data-action="execute_scope"/);});


test('authoring capability and selection are published for the source navigation',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({mode:'author'});value.state.capabilities={actor_id:'a',managed_systems:['EMS'],can_author:true,native_access_available:true,native_access:{skills:true}};value.state.workflows=[{id:'w',name:'저장된 편집',system_id:'EMS',category:'ops',updated_at:'2026-10-02'}];view.render(value);const published=h.published.at(-1);assert.deepEqual(published.state.capabilities,value.state.capabilities);assert.deepEqual(published.state.workflows,value.state.workflows);assert.equal(published.selection.mode,'author');assert.equal(h.ids.get('ees-work-panel').dataset.eesMode,'author');});

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
test('source resize before actor restoration persists its explicit width after the workspace read',async()=>{
 const h=controller();h.api.reset();h.setAuth('actor-b-token');h.api.setIdentity();
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?{ok:true,capabilities:{actor_id:'b'},systems:['EMS'],workflows:[],runs:[],ui_state:{revision:4,state:{selection:{panel_width:720,system_id:'EMS'}}}}:{ok:true,revision:5});
 await h.api.sourceAction({action:'panel_width',width:'400'});assert.equal(h.api.snapshot().selection.panel_width,400);
 await h.api.refresh();assert.equal(h.api.snapshot().selection.panel_width,400);
 for(const callback of [...h.timers.values()])callback();await new Promise(setImmediate);
 const writes=h.calls.filter(call=>call.body?.action==='save_ui');assert.equal(writes.length,1);assert.equal(writes[0].body.state.selection.panel_width,400);assert.equal(writes[0].body.expected_revision,4);assert.equal(writes[0].options.headers.Authorization,'Bearer actor-b-token');
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

test('runtime never arms or releases a document hiding gate on success or failure',async()=>{
 const {launcherSource}=require('./ees_workspace_ui_fixture.cjs');assert.doesNotMatch(launcherSource,/eesStartup|startup-ready|startupReady|visibility/);
 for(const behavior of ['success','missing','exception']){const h=controller(),events=[];h.context.window.dispatchEvent=event=>events.push(event.type);h.view.render=()=>{if(behavior==='exception')throw Error('layout_failed');return behavior==='success';};if(behavior==='exception')await assert.rejects(h.api.refresh(),/layout_failed/);else await h.api.refresh();assert.deepEqual(events,[]);}
});
test('view reports source slot mount success and leaves procedure introduction to source components',()=>{
 const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');assert.equal(view.render(snapshot()),true);
 h.context.window.__eesSourceShellV1.hosts=()=>({});assert.equal(view.render(snapshot()),false);assert.equal(view.sync(snapshot()),false);
 const {viewSource}=require('./ees_workspace_ui_fixture.cjs');assert.doesNotMatch(viewSource,/function workProcedureStartHTML/);
 assert.equal(run(h.context,'workUI.procedureQuestions[2]'),'빈 절차로 시작하면 무엇부터 정하나요?');
});

test('Native portal skin is gated by the first-render source without hiding or moving Native surfaces',()=>{
 const fs=require('node:fs'),path=require('node:path'),css=fs.readFileSync(path.join(__dirname,'../branding/ees/ui/chat-theme.css'),'utf8');
 const sourceSkin=css.slice(css.indexOf('/* Source-present Native skin:'));
 assert.doesNotMatch(sourceSkin,/body\[data-ees-integrated\]|visibility:|display:\s*none|position:/);
 for(const selector of sourceSkin.matchAll(/([^{}]+)\{/g))assert.ok(selector[1].includes('body:has([data-ees-source-shell])'),selector[1]);
 assert.match(sourceSkin,/\.modal\[role="dialog"\]>div/);assert.doesNotMatch(sourceSkin,/::backdrop/);assert.match(sourceSkin,/:focus-visible/);assert.match(sourceSkin,/\.cm-editor/);assert.match(sourceSkin,/\.katex/);
});

test('rapid dialog replacement reverses current visual without duplicate windows or stale focus and resolves decisions immediately',async()=>{
 const timers=new Map();let serial=0;
 const h=dom({getComputedStyle:()=>({opacity:'.38',transform:'matrix(.99, 0, 0, .99, 0, 0)',getPropertyValue:name=>name==='--ees-motion-close'?'150ms':name==='--ees-motion-open'?'200ms':''}),setTimeout:(fn,delay)=>{const id=++serial;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id)});
 const first=run(h.context,'workUI.dialog({title:"first",confirmLabel:"확인"})'),old=h.overlays.children.find(el=>el.id==='ees-work-dialog');old.eesClose();assert.equal(await first,false);assert.equal(old.isConnected,true);assert.equal(old.getAttribute('data-ees-motion'),'closing');
 const second=run(h.context,'workUI.dialog({title:"second",confirmLabel:"확인"})'),current=h.overlays.children.find(el=>el.id==='ees-work-dialog');assert.notEqual(current,old);assert.equal(old.isConnected,false);assert.equal(h.overlays.children.filter(el=>el.id==='ees-work-dialog').length,1);assert.equal(current.style['--ees-motion-from-opacity'],'.38');assert.equal(h.document.activeElement.id,'ees-work-dialog-body');
 current.eesClose();assert.equal(await second,false);run(h.context,'workMotion.finish(document.querySelector("#ees-work-dialog"))');
});

test('dialog caller restores a repainted trigger even when its captured previous focus is connected body',async()=>{
 const h=dom(),replacement=h.element('repainted-create');h.body.append(replacement);h.context.restoreCreate=()=>replacement.focus();
 const pending=run(h.context,'workUI.dialog({title:"새 업무 절차",restoreFocus:restoreCreate})');const dialog=h.overlays.children.find(el=>el.id==='ees-work-dialog');dialog.eesClose();assert.equal(await pending,false);assert.equal(h.document.activeElement,replacement);
});
