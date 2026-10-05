/* DOM lifecycle checks only; Native browser geometry is checked separately. */
const test=require('node:test'),assert=require('node:assert/strict');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
function dom(){
 const ids=new Map();let doc;
 function element(id=''){
  const classes=new Set(),events=new Map();let html='';
  const el={id,dataset:{},style:{setProperty(name,value){this[name]=String(value);},removeProperty(name){delete this[name];}},children:[],parentElement:null,isConnected:false,hidden:false,scrollTop:0,attributes:{},classList:{add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value)},
   setAttribute(name,value){this.attributes[name]=String(value);},removeAttribute(name){delete this.attributes[name];},getAttribute(name){return name==='id'?this.id:this.attributes[name] ?? null;},hasAttribute(name){return name==='id'?Boolean(this.id):Object.hasOwn(this.attributes,name);},querySelector(selector){return ids.get(selector.slice(1)) || null;},querySelectorAll(selector){return selector==='button,input,select,textarea,a,summary,[data-ees-panel-resize]'?(this.mockControls || []):[];},contains(target){return target===this||this.children.includes(target)||(this.mockControls || []).includes(target);},
   append(child){child.remove();child.parentElement=this;child.isConnected=true;this.children.push(child);if(child.id)ids.set(child.id,child);},prepend(child){this.append(child);this.children.splice(this.children.indexOf(child),1);this.children.unshift(child);},
   remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;this.isConnected=false;},
   insertAdjacentElement(_,child){this.parentElement.append(child);},focus(){doc.activeElement=this;},addEventListener(type,fn){events.set(type,fn);},dispatch(type){events.get(type)?.({target:this});},showModal(){this.open=true;},close(){this.open=false;events.get('close')?.();},matches:()=>false};
  Object.defineProperty(el,'innerHTML',{get:()=>html,set(value){html=value;if(el.replaceControls)el.mockControls=el.replaceControls();for(const match of value.matchAll(/id="([^"]+)"/g)){if(!ids.has(match[1]))ids.set(match[1],element(match[1]));}if(value.includes('data-dialog-close')){const cancel=element('cancel');el.querySelector=selector=>selector==='[data-dialog-close]'?cancel:selector==='[data-dialog-confirm]'?element('confirm'):ids.get(selector.slice(1)) || null;} }});
  Object.defineProperty(el,'firstChild',{get:()=>el.children[0] || (html?{}:null)});if(id)ids.set(id,el);return el;
 }
 const body=element('body'),sidebar=element('sidebar'),anchorParent=element('anchor-parent'),anchor=element('sidebar-search-button'),row=element('row'),column=element('native-column'),pane=element('chat-pane');
 body.isConnected=true;body.append(sidebar);sidebar.append(anchorParent);anchorParent.append(anchor);body.append(row);row.append(column);column.append(pane);
 doc={body,activeElement:body,createElement:()=>element(),querySelector:selector=>selector==='#chat-container #chat-pane'?pane:ids.get(selector.slice(1)) || null,getElementById:id=>ids.get(id)};
 const context=renderer({document:doc});return {context,ids,body,row,column,pane,document:doc,element};
}
const snapshot=(patch={})=>({state:{capabilities:{actor_id:'a'},systems:['EMS'],factories:[],workflows:[],runs:[],my_work:[]},selection:{mode:'work',tab:'my_work',panel_open:true,system_id:'EMS',factory_id:'',...patch}});
test('Native conversation remains the original center DOM while the work panel mounts after it',()=>{const h=dom();const view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());assert.equal(h.row.children[0],h.column);assert.equal(h.row.children[1].id,'ees-work-panel');assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),true);assert.match(h.ids.get('ees-work-entry').innerHTML,/전체 공장/);});
test('closing or changing work mode preserves Native chat and the authoring mount boundary',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());view.render(snapshot({panel_open:false}));assert.equal(h.ids.get('ees-work-panel').hidden,true);assert.equal(h.pane.parentElement,h.column);view.render(snapshot({mode:'author',panel_open:true}));assert.ok(view.authoringHost());assert.equal(h.pane.parentElement,h.column);view.reset();assert.equal(h.pane.parentElement,h.column);assert.equal(h.column.classList.contains('ees-integrated-chat'),false);});
test('panel scroll restores per personal target and never writes a shared run selection',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());h.ids.get('ees-work-content').scrollTop=157;view.render(snapshot({tab:'records'}));h.ids.get('ees-work-content').scrollTop=22;view.render(snapshot());assert.equal(h.ids.get('ees-work-content').scrollTop,157);assert.equal(h.context.document.body.dataset.eesIntegrated,'true');});
test('confirmation dialog starts on cancel and Escape closure never accepts the command',async()=>{const h=dom();const waiting=run(h.context,'workUI.dialog({title:"요청 확인",html:"<p>대상</p>",confirmLabel:"요청"})');const dialog=h.body.children.find(item=>item.id==='ees-work-dialog');assert.equal(h.document.activeElement.id,'cancel');dialog.dispatch('cancel');dialog.close();assert.equal(await waiting,false);assert.equal(h.document.activeElement,h.body);});


test('workspace refresh retains active input identity and text selection without taking Native focus',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})');view.render(snapshot());const host=h.ids.get('ees-work-panel'),field=h.element('input-original');field.id='ew-run-evidence';field.setAttribute('name','evidence');field.selectionStart=2;field.selectionEnd=5;field.selectionDirection='forward';host.mockControls=[field];field.focus();let replacement;host.replaceControls=()=>{replacement=h.element('ew-run-evidence');replacement.setAttribute('name','evidence');replacement.setSelectionRange=(start,end,direction)=>{replacement.range=[start,end,direction];};return [replacement];};view.render(snapshot());assert.equal(h.document.activeElement,replacement);assert.deepEqual(replacement.range,[2,5,'forward']);h.pane.focus();view.render(snapshot());assert.equal(h.document.activeElement,h.pane);});


test('published procedure overview opens before a run exists without dereferencing run state',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({workflow_id:'w',tab:'overview'});value.state.workflow={id:'w',name:'게시한 절차',published_version:1,published:{nodes:{p:{id:'p',type:'p',children:['j']},j:{id:'j',type:'j',parent:'p',mode:'tool',name:'조회'}}}};view.render(value);assert.match(h.ids.get('ees-work-panel').innerHTML,/data-action="start_run"/);assert.doesNotMatch(h.ids.get('ees-work-panel').innerHTML,/data-action="execute_scope"/);});


test('workspace navigation separates managed-system authoring from work scope and actual tasks',()=>{const h=dom(),view=run(h.context,'createWorkView({callbacks:{}})'),value=snapshot({mode:'author'});value.state.capabilities={actor_id:'a',managed_systems:['EMS']};value.state.workflows=[{id:'w',name:'저장된 편집',system_id:'EMS',category:'ops',updated_at:'2026-10-02'}];view.render(value);const nav=h.ids.get('ees-work-entry').innerHTML;assert.match(nav,/관리 시스템/);assert.match(nav,/최근 편집/);assert.match(nav,/저장된 편집/);assert.match(nav,/스킬·지침/);assert.doesNotMatch(nav,/data-action="my_work"|전체 공장/);assert.equal(h.ids.get('ees-work-panel').dataset.eesMode,'author');});

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
