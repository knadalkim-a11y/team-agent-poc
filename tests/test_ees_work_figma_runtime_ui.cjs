/* Reconstructed from recorded source reads and patches after workspace loss.
 * These are controller/renderer contracts, not Native product evidence. */
const test=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {renderer,run,controller,deferred}=require('./ees_workspace_ui_fixture.cjs');
const html=(source,values={})=>run(renderer(values),source);

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
