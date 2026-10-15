/* Controller render contracts; real Native animation-frame evidence is separate. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {controller,deferred,renderer,run}=require('./ees_workspace_ui_fixture.cjs');
const copy=value=>JSON.parse(JSON.stringify(value));
const settle=()=>new Promise(setImmediate);
const evidence=[];
function record(value){evidence.push(value);if(process.env.EES_NATIVE_RETURN_EVIDENCE)fs.writeFileSync(process.env.EES_NATIVE_RETURN_EVIDENCE,JSON.stringify({runtime:process.version,source:process.env.EES_NATIVE_RETURN_SOURCE || 'working-tree',level:'controller render callbacks, not browser animation frames',cases:evidence},null,2)+'\n','utf8');}
const targets={tools:{action:'tools',mode:'author',tab:'tools'},procedures:{action:'procedures',mode:'author',tab:'overview'},workspace_admin:{action:'workspace_admin',mode:'author',tab:'workspace_admin'},work:{action:'mode',mode:'work',tab:'my_work'}};
function harness(origin){
 const h=controller(),frames=[],authorFrames=[],navigation=[];let phase='initial',time=0,chatReady=true,closed=0,resets=0;
 const capabilities={actor_id:'a',is_admin:true,can_author:true,native_access_available:true,native_access:{skills:true,models:true,admin:true}};
 const state={ok:true,capabilities,systems:['EMS'],workflows:[],runs:[],my_work:[],operations:{tools:[]},ui_state:{revision:0,state:{}}};
 const draft={definition:{name:'kept unsaved author draft'},dirty:true},chat={prompt:'kept chat draft',files:[{id:'kept-file'}]};
 const queued=[],reads=[];
 h.api.setState(state);h.api.setSelection({mode:'author',tab:targets[origin].tab,system_id:'EMS',workflow_id:origin==='procedures'?'draft-workflow':'',run_id:'',job_id:'',panel_width:620});
 h.context.location.pathname='/c/original';h.context.location.search='?keep=1';
 h.context.window.__eesNativeDraftV1={persistent:true,ready:()=>chatReady,read:()=>chat,flush:()=>true,restore(){throw Error('Native return must never replace the live draft');}};
 h.context.window.__eesSourceShellV1.navigate=path=>{navigation.push(path);const url=new URL(path,'http://native.test');h.context.location.pathname=url.pathname;h.context.location.search=url.search;};
 h.designer.canNavigate=()=>true;h.designer.readDraft=()=>draft;h.designer.closeStart=()=>closed++;h.designer.reset=()=>resets++;
 h.view.render=value=>{
  h.renders.push(value);
  // Use the production menu renderer for workspace aria-current, and retain
  // the exact mode/tab published to the source navigation in every render.
  const menuState={...(value.state || {}),capabilities:value.native_capabilities ?? value.state?.capabilities};
  const menuSelection={...value.selection,native_id:value.native_id};
  const menu=(value.native_shell||value.selection.mode==='author')?run(renderer({menuState,menuSelection}),'workWorkspaceMenuHTML(menuState,menuSelection)'):'';
  const current=[...menu.matchAll(/<button\b([^>]*aria-current="page"[^>]*)>/g)].map(match=>({action:match[1].match(/data-action="([^"]+)"/)?.[1],native_id:match[1].match(/data-native-id="([^"]+)"/)?.[1]}));
  frames.push({phase,time,native:value.native_shell,mode:value.selection.mode,tab:value.selection.tab,workflow_id:value.selection.workflow_id,target_loading:value.target_loading,native_return_pending:value.native_return_pending,aria_current:current});
 };
 h.designer.render=value=>authorFrames.push({phase,time,mode:value.selection.mode,tab:value.selection.tab,workflow_id:value.selection.workflow_id});
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?state:{ok:true});
 return {...h,state,draft,chat,frames,authorFrames,navigation,reads,
  counts:()=>({closed,resets}),phase:value=>{phase=value;},setReady:value=>{chatReady=value;},
  async open(id){await h.api.sourceAction({action:'native_open',nativeId:id});h.api.sync();await settle();},
  delayReplies(result=state,other=()=>({ok:true})){h.setReply(call=>{if(!/^\/api\/ees-work\/(workspace|operations)\?/.test(call.url))return other(call);const pending=deferred(),kind=call.url.includes('/workspace?')?'workspace':'operations';reads.push({kind,time,url:call.url});queued.push({at:time+1000,pending,value:kind==='workspace'?(typeof result==='function'?result(call):result):{ok:true,tools:[]}});return pending.promise;});},
  async advance(next){time=next;for(const task of queued.splice(0).filter(task=>{if(task.at<=time){task.pending.resolve(task.value);return false;}return true;}))queued.push(task);await settle();},
  async click(destination){phase='clicked';const target=targets[destination];await h.api.sourceAction({action:target.action,...(target.action==='mode'?{mode:target.mode}:{})});h.api.sync();await settle();},
 };
}

for(const origin of ['tools','procedures','workspace_admin'])for(const native of ['skills','models'])for(const destination of Object.keys(targets).filter(value=>value!==origin)){
 test(`Native return selects ${destination} before any response: ${origin} -> ${native}`,async()=>{
  const h=harness(origin);await h.open(native);h.delayReplies();h.phase('before-click');
  const first=h.frames.length,firstAuthor=h.authorFrames.length,target=targets[destination];
  await h.click(destination);
  h.phase('workspace-wait-999ms');await h.advance(999);
  h.phase('workspace-arrived-1000ms');await h.advance(1000);
  h.phase('operations-wait-1999ms');await h.advance(1999);
  h.phase('operations-arrived-2000ms');await h.advance(2000);
  // The old implementation starts an extra selection read after 2,000ms.
  // Drain it as well so the evidence covers click through completed return.
  h.phase('settled');await h.advance(3000);await h.advance(4000);
  const frames=h.frames.slice(first),authors=h.authorFrames.slice(firstAuthor);
  const wrong=frames.filter(value=>!value.native&&(value.mode!==target.mode||value.tab!==target.tab));
  const staleAuthors=authors.filter(value=>value.mode!==target.mode||value.tab!==target.tab);
  const unexpectedCurrent=frames.flatMap(value=>value.aria_current).filter(value=>!(value.action==='native_open'&&value.native_id===native)&&value.action!==target.action);
  record({origin,native,destination,delay_ms:{workspace:1000,operations:1000},reads:h.reads,frames,author_renders:authors,wrong_selection_renders:wrong.length,stale_panel_snapshots:wrong.length,stale_author_renders:staleAuthors.length,unexpected_aria_current:unexpectedCurrent.length});
  assert.ok(frames.length,'a return must render its destination');
  assert.equal(wrong.length,0,JSON.stringify({origin,native,destination,wrong,staleAuthors}));
  assert.equal(staleAuthors.length,0,'the right-side authoring renderer must never receive the previous section');
  assert.equal(unexpectedCurrent.length,0,'only the clicked Native item or destination may have aria-current');
  assert.equal(h.reads.length,2,'the return needs one workspace read and one operations read, without a duplicate refresh');
  assert.deepEqual(h.reads.slice(0,2).map(({kind,time})=>({kind,time})),[{kind:'workspace',time:0},{kind:'operations',time:1000}]);
  assert.equal(h.api.snapshot().selection.mode,target.mode);assert.equal(h.api.snapshot().selection.tab,target.tab);
  assert.equal(h.context.location.pathname+h.context.location.search,'/c/original?keep=1');
  assert.equal(h.calls.filter(call=>call.body&&call.body.action!=='save_ui').length,0,'navigation cannot mutate shared assets');
 });
}

test('same Native destination retains the exact private author draft and selection during both delayed reads',async()=>{
 for(const origin of ['tools','procedures','workspace_admin']){
  const h=harness(origin);await h.open('skills');const before=copy(h.api.snapshot().selection),counts=h.counts();h.delayReplies();await h.click(origin);
  assert.deepEqual(copy(h.api.snapshot().selection),before);assert.equal(h.designer.readDraft(),h.draft);assert.deepEqual(h.counts(),counts);
  await h.advance(1000);assert.deepEqual(copy(h.api.snapshot().selection),before);await h.advance(2000);
  assert.deepEqual(copy(h.api.snapshot().selection),before);assert.equal(h.designer.readDraft(),h.draft);assert.equal(h.context.window.__eesNativeDraftV1.read(),h.chat);assert.deepEqual(h.counts(),counts);
 }
});

test('Native return publishes no work reference until workspace operations and Chat readiness are confirmed',async()=>{
 const h=harness('tools');await h.open('skills');h.delayReplies({...h.state,workflow:{id:'private',revision:1}});h.setReady(false);await h.click('procedures');
 const reference=()=>h.context.window.__eesNativeWorkV1.captureReference();assert.equal(reference().kind,'none');
 await h.advance(1000);assert.equal(reference().kind,'none');await h.advance(2000);assert.equal(reference().kind,'none');
 h.setReady(true);h.api.sync();await settle();assert.equal(h.api.snapshot().selection.tab,'overview');
});

test('account reset discards a pending Native destination and all prior private state',async()=>{
 const h=harness('tools');await h.open('skills');h.delayReplies();await h.api.sourceAction({action:'workspace_admin'});
 h.setAuth('account-b-token');h.api.sync();await settle();assert.equal(h.api.snapshot().state,null);assert.equal(h.api.snapshot().selection.mode,'work');assert.equal(h.api.snapshot().selection.tab,'my_work');
});

test('a Native return permission denial discards cached author state and cannot execute the queued action',async()=>{
 const h=harness('tools');await h.open('skills');h.delayReplies({httpError:true,status:403,error:{code:'scope_forbidden',message:'access removed'}});await h.click('procedures');
 await h.advance(1000);assert.equal(h.api.snapshot().state,null);assert.equal(h.api.reference().kind,'none');assert.match(h.api.snapshot().error,/access removed/);
 assert.equal(h.calls.some(call=>call.body&&call.body.action!=='save_ui'),false);
});

test('a queued Native destination cannot apply to an unrelated chat route',async()=>{
 const h=harness('tools');await h.open('skills');h.delayReplies();await h.api.sourceAction({action:'procedures'});
 h.context.location.pathname='/c/unrelated';h.context.location.search='';h.api.sync();await settle();await h.advance(1000);await h.advance(2000);
 assert.equal(h.api.snapshot().selection.tab,'tools');
 assert.equal(h.calls.some(call=>call.body&&call.body.action!=='save_ui'),false);
});

for(const outcome of ['saved','save_failed','permission_revoked'])test(`dirty Native return keeps its review-save guard: ${outcome}`,async()=>{
 const h=harness('procedures'),saving=deferred();let dirty=true,revoked=false;
 const selected={mode:'work',tab:'current',workflow_id:'w',run_id:'r',job_id:'j'};
 const state={...h.state,workflow:{id:'w',name:'old review workflow'},run:{id:'r',revision:1,definition:{nodes:{j:{name:'old review job',result_block:'ai_review'}}},jobs:{j:{attempt_id:'a',can_decide:true}}}};
 h.api.setState(state);h.api.setSelection(selected);
 h.view.readReview=()=>({dirty,inputs:{text:'kept unsaved review'},attempt_id:'a',result_revision:1,revision:0,key:'r/j',serial:1});
 h.view.clearReview=()=>{dirty=false;};
 h.setReply(call=>call.url.startsWith('/api/ees-work/workspace?')?state:{ok:true});await h.open('skills');
 h.delayReplies(()=>revoked?{...state,capabilities:{actor_id:'a',is_admin:false,can_author:false,native_access_available:true,native_access:{skills:true}}}:state,call=>call.body?.action==='save_review_draft'?saving.promise:{ok:true});
 const first=h.frames.length,firstAuthor=h.authorFrames.length;await h.click('tools');
 assert.equal(h.api.snapshot().selection.tab,'current','the private selection remains bound to the unsaved review');
 assert.equal(h.frames.at(-1).tab,'tools','the first visible selection is the destination');
 assert.equal(h.frames.at(-1).target_loading,true);assert.equal(h.frames.at(-1).native_return_pending,true);
 assert.equal(h.api.reference().kind,'none');assert.equal(h.calls.some(call=>call.body?.action==='save_review_draft'),false);
 await h.advance(1000);await h.advance(2000);
 const writes=h.calls.filter(call=>call.body?.action==='save_review_draft');assert.equal(writes.length,1);
 assert.equal(writes[0].body.run_id,'r');assert.equal(writes[0].body.job_id,'j');assert.equal(writes[0].body.text,'kept unsaved review');
 assert.equal(h.api.snapshot().selection.tab,'current');
 assert.equal(h.api.reference().kind,'none','the pending destination must not publish the previous review reference while its save waits');
 assert.equal(h.context.window.__eesNativeWorkV1.helpContext(),null,'help cannot bind to the previous review while the destination is pending');
 assert.ok(h.frames.slice(first).filter(value=>!value.native).every(value=>value.mode==='author'&&value.tab==='tools'&&value.target_loading));
 assert.equal(h.authorFrames.length,firstAuthor,'the previous authoring content cannot be painted while saving');
 revoked=outcome==='permission_revoked';
 saving.resolve(outcome==='save_failed'?{ok:false,error:{message:'review save failed'}}:{ok:true,run:{jobs:{j:{review_draft:{revision:1,text:'kept unsaved review'}}}}});
 await settle();for(const time of [3000,4000,5000,6000])await h.advance(time);
 const final=h.api.snapshot();
 if(outcome==='saved'){assert.equal(final.selection.mode,'author');assert.equal(final.selection.tab,'tools');assert.equal(final.selection.run_id,'');assert.equal(dirty,false);}
 else{for(const [name,value] of Object.entries(selected))assert.equal(final.selection[name],value,`${outcome}: ${name}`);if(outcome==='save_failed'){assert.equal(dirty,true);assert.match(final.error,/review save failed/);}}
 assert.equal(h.calls.some(call=>call.body&&call.body.action!=='save_review_draft'&&call.body.action!=='save_ui'),false);
});

test('pending Native return prepares only the destination placeholder without old panel text',()=>{
 const host={dataset:{},isConnected:true,querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){},innerHTML:''},published=[];
 const context=renderer({document:{activeElement:null,querySelector:()=>null}});context.window.__eesSourceShellV1={hosts:()=>({panel:host}),publish:value=>published.push(value)};
 const view=run(context,'createWorkView({callbacks:{}})');
 view.render({native_shell:true,native_return_pending:true,target_loading:true,state:{capabilities:{actor_id:'a',is_admin:true},workflow:{id:'w',name:'old private workflow'},run:{definition:{nodes:{j:{name:'old private job'}}}}},selection:{mode:'author',tab:'tools',workflow_id:'w',job_id:'j'}});
 assert.match(host.innerHTML,/data-ees-target-loading/);assert.doesNotMatch(host.innerHTML,/old private workflow|old private job|ees-work-authoring-panel/);assert.equal(published.at(-1).context_title,'대화');
});
