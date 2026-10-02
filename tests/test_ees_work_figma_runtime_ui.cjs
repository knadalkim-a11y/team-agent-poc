/* Reconstructed from recorded source reads and patches after workspace loss.
 * These are controller/renderer contracts, not Native product evidence. */
const test=require('node:test'),assert=require('node:assert/strict');
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
