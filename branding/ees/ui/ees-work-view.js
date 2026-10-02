/* EES Work: shared schema renderers and the Native conversation's side panels.
 * The server owns business state. This file owns only an actor's display/drafts. */
const workUI = (() => {
  const $ = (selector, parent = document) => parent?.querySelector(selector) || null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  const categories = {ops:'운영',setup:'셋업',incident:'장애대응'};
  const levels = {p:'업무 절차',t:'단계',j:'작업'};
  const statuses = {unstarted:'미실행',pending:'대기',scheduled:'예약',ready:'시작 가능',running:'실행 중',in_progress:'진행 중',awaiting_input:'입력 필요',awaiting_confirmation:'사람 확인 필요',review_required:'다시 검토 필요',completed:'완료',succeeded:'도구 성공',success:'도구 성공',failed:'실패',partial:'부분 결과',unknown:'결과 미확인',missed:'예약 놓침',excluded:'적용 제외',cancelled:'취소',blocked:'진행 조건 확인',draft:'초안',published:'게시됨',review:'검토 필요',waiting:'대기',waiting_input:'입력 필요',waiting_confirmation:'사람 확인 필요',reported_complete:'완료 보고',accepted:'접수',requested:'요청 보냄',effect_verified:'효과 확인'};
  const icon = (name,label='') => `<img class="ew-icon" src="/_ees13/v4/${esc(String(name).replace(/\.svg$/,''))}.svg" alt="${esc(label)}"${label?'':' aria-hidden="true"'}>`;
  const button = (label,action,attrs='') => `<button type="button" data-action="${esc(action)}" ${attrs}>${esc(label)}</button>`;
  const finished = run => ['completed','cancelled'].includes(run?.status);
  const lineage = (id, definition) => {const path=[],seen=new Set();while(id && definition?.nodes?.[id] && !seen.has(id)){seen.add(id);const node=definition.nodes[id];path.unshift(node);id=node.parent;}return path;};
  const badge = status => `<span class="ew-badge" data-status="${esc(status)}">${esc(statuses[status] || status || '미확인')}</span>`;
  const time = value => {if(value===undefined||value===null||value==='')return '';const date=typeof value==='number'?new Date(value*1000):new Date(value);return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date);};
  const safeURL = value => {try{const url=new URL(String(value),location.origin);return ['https:','http:'].includes(url.protocol)?url.href:'';}catch(_){return '';}};
  let activeDialog=null;
  function closeDialog(){activeDialog?.close();}
  function dialog({title,html='',confirmLabel='',note='',restoreFocus=null,readOnlyDetail=false}){
    closeDialog();const previous=document.activeElement,element=document.createElement('dialog');
    element.id='ees-work-dialog';element.dataset.eesWork='';element.setAttribute('aria-labelledby','ees-work-dialog-title');
    element.innerHTML=`<h2 id="ees-work-dialog-title">${esc(title)}</h2>${note?`<p class="ew-muted">${esc(note)}</p>`:''}<div class="ew-dialog-body">${html}</div><footer><button type="button" data-dialog-close data-dialog-cancel id="ees-work-dialog-cancel">${confirmLabel?'취소':'닫기'}</button>${confirmLabel&&!readOnlyDetail?`<button type="button" class="ew-primary" data-dialog-confirm>${esc(confirmLabel)}</button>`:''}</footer>`;
    document.body.append(element);activeDialog=element;
    return new Promise(resolve=>{
      let accepted=false;
      element.querySelector('[data-dialog-confirm]')?.addEventListener('click',()=>{const invalid=[...element.querySelectorAll('input,select,textarea')].find(field=>!field.checkValidity());if(invalid){invalid.reportValidity();return;}accepted=true;element.close();});
      element.querySelector('[data-dialog-close]').addEventListener('click',()=>element.close());
      element.addEventListener('cancel',()=>{accepted=false;});
      element.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();accepted=false;element.close();}},true);
      element.addEventListener('close',()=>{element.remove();if(activeDialog===element)activeDialog=null;if(previous?.isConnected)previous.focus({preventScroll:true});else restoreFocus?.();resolve(accepted);},{once:true});
      element.showModal();element.querySelector('[data-dialog-close]').focus({preventScroll:true});
    });
  }
  return Object.freeze({$,esc,clone,categories,levels,statuses,icon,button,finished,lineage,badge,safeURL,time,dialog,closeDialog});
})();

function workStatusHTML(status,label=''){
  const {esc,icon,statuses}=workUI;
  const glyph=['completed','effect_verified'].includes(status)?'d553d':['failed'].includes(status)?'44a96':['awaiting_input','awaiting_confirmation','review_required','review','waiting_input','waiting_confirmation'].includes(status)?'9c63b':['running','in_progress'].includes(status)?'8f8a1':['unknown','missed','partial'].includes(status)?'49833':'40ef1';
  return `<span class="ew-status" data-status="${esc(status)}">${icon(glyph)}<span>${esc(label || statuses[status] || status || '미실행')}</span></span>`;
}
function workAutoStatusHTML(status){
  const labels={failed:'실패',missed:'놓침',running:'실행 중',succeeded:'정상'},asset={failed:'7495b',succeeded:'c6340',running:'8f8a1',missed:'49833'}[status];
  return asset?`<span class="ew-auto-status" data-status="${status}" title="마지막 자동 실행 · ${labels[status]}">${workUI.icon(asset,labels[status])}</span>`:'';
}
function workExecutionModelHTML(operations={},selected=''){
  const {esc}=workUI,models=operations.models || [];
  if(operations.error)return `<p class="ew-warning">모델·실행 연결 조회 실패 · ${esc(operations.error)}</p>`;
  if(!models.length)return '<p class="ew-warning">사용할 수 있는 모델이 없습니다. Native 모델 연결과 권한을 확인해 주세요.</p>';
  if(models.length===1)return `<p class="ew-model-select" data-execution-model="${esc(models[0].id)}">AI 모델 · ${esc(models[0].name || models[0].id)}</p>`;
  return `<label class="ew-model-select">AI 모델 <select id="ees-work-execution-model"><option value="">모델 선택</option>${models.map(model=>`<option value="${esc(model.id)}"${model.id===selected?' selected':''}>${esc(model.name || model.id)}</option>`).join('')}</select></label>`;
}
function workInputHTML(field,value,{disabled=false,prefix='run',people=[],lookup=null}={}){
  const dynamic=['single','multi'].includes(field.type)&&field.options_source&&field.options_source!=='manual';
  const {esc}=workUI,id=`ew-${prefix}-${field.id}`,required=field.required?' required':'',off=disabled||(dynamic&&lookup?.status!=='ready')?' disabled':'',name=`name="${esc(field.id)}" data-work-input data-value-present="${value!==undefined}" data-input-type="${esc(field.type)}" id="${esc(id)}"${required}${off}`;
  const valueText=v=>typeof v==='string'?v:JSON.stringify(v),choice=option=>typeof option==='object'&&option!==null?{value:option.value ?? option.id,label:option.label ?? option.name ?? option.id}: {value:option,label:option};
  let control='';
  if(field.type==='boolean')control=`<select ${name}><option value="">선택 안 함</option><option value="true"${value===true?' selected':''}>예</option><option value="false"${value===false?' selected':''}>아니요</option></select>`;
  else if(['single','multi','person'].includes(field.type)){
    const options=(field.type==='person'?(field.options?.length?field.options:people):(dynamic?(lookup?.status==='ready'?lookup.options:[]):field.options || [])).map(choice);
    const previous=field.type==='multi'?(Array.isArray(value)?value:[]):value===undefined?[]:[value];
    for(const old of previous)if(!options.some(option=>JSON.stringify(option.value)===JSON.stringify(old)))options.push({value:old,label:'이전 선택 · 현재 목록 확인 필요',stale:true});
    control=`<select ${name}${field.type==='multi'?' multiple':''}>${field.type!=='multi'?'<option value="">선택 안 함</option>':''}${options.map(option=>`<option value="${esc(JSON.stringify(option.value))}"${(field.type==='multi'?Array.isArray(value)&&value.some(v=>JSON.stringify(v)===JSON.stringify(option.value)):JSON.stringify(value)===JSON.stringify(option.value))?' selected':''}${option.stale?' data-stale-option':''}>${esc(option.label)}</option>`).join('')}</select>`;
  }else if(field.type==='list')control=`<textarea ${name} rows="3" placeholder="한 줄에 하나씩 입력">${esc(Array.isArray(value)?value.map(valueText).join('\n'):value ?? '')}</textarea>`;
  else control=`<input ${name} type="${field.type==='number'?'number':field.type==='datetime'?(/^\d{4}-\d{2}-\d{2}$/.test(value || '')?'date':/(Z|[+-]\d{2}:\d{2})$/.test(value || '')?'text':'datetime-local'):'text'}"${field.type==='number'?' step="any"':''} value="${esc(value ?? '')}">${field.unit?`<span class="ew-unit">${esc(field.unit)}</span>`:''}`;
  if(dynamic)control+=`<small class="ew-option-source" role="status">${esc(lookup?.status==='ready'?`현재 권한으로 조회 · ${lookup.source?.kind || field.options_source} · ${lookup.options.length}개`:lookup?.status==='failed'?`목록 조회 실패 · ${lookup.error}`:'선택 목록을 확인하는 중입니다.')}</small>${!disabled?workUI.button('목록 다시 조회','reload_options',`data-field-id="${esc(field.id)}" class="ew-text"${lookup?.status==='loading'?' disabled':''}`):''}`;
  return `<label class="ew-input-row" for="${esc(id)}"><span>${esc(field.name || field.id)}${field.required?'<span aria-label="필수"> *</span>':''}</span><span class="ew-input-control">${control}${field.help?`<small>${esc(field.help)}</small>`:''}</span></label>`;
}
function workReadInputs(container){
  const values={};
  for(const field of container.querySelectorAll('[data-work-input]')){
    if(field.disabled)continue;const key=field.name,type=field.dataset.inputType;
    if(type==='multi'){values[key]=[...field.selectedOptions].map(option=>JSON.parse(option.value));continue;}
    if(field.value===''&&!(field.dataset.valuePresent==='true'&&['text','list'].includes(type)))continue;
    if(type==='boolean')values[key]=field.value==='true';
    else if(['single','person'].includes(type))values[key]=JSON.parse(field.value);
    else if(type==='number'){const number=Number(field.value);if(!Number.isFinite(number))throw new Error('숫자 입력을 확인해 주세요.');values[key]=number;}
    else if(type==='list')values[key]=field.value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
    else values[key]=field.value;
  }
  return values;
}
function workInputProposal(payload,run,jobId){
  const fields=run?.definition?.nodes?.[jobId]?.inputs || [],allowed=new Set(fields.filter(field=>(field.scope || 'run')==='run').map(field=>field.id));
  if(payload?.proposal_kind!=='inputs'||payload.run_id!==run?.id||payload.workflow_id!==run.workflow_id||payload.job_id!==jobId||payload.base_revision!==run.revision||!payload.proposal||typeof payload.proposal!=='object'||Array.isArray(payload.proposal)||Object.keys(payload.proposal).some(key=>!allowed.has(key)))throw new Error('현재 진행 건·작업·저장 버전과 다른 입력 제안입니다.');
  return workUI.clone(payload.proposal);
}

function workSettingsOverrides(settings,draft,fields){
  const values={...(settings.overrides || {})};
  for(const field of fields || [])if(['workflow','factory'].includes(field.scope)){
    if(!Object.hasOwn(draft,field.id))delete values[field.id];
    else if(JSON.stringify(draft[field.id])!==JSON.stringify(settings.values?.[field.id]))values[field.id]=workUI.clone(draft[field.id]);
  }
  return values;
}

function createWorkInputDrafts(){
  const entries=new Map(),{clone}=workUI,same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  return Object.freeze({
    edit(key,inputs,revision,base){const old=entries.get(key);entries.set(key,{inputs:clone(inputs),revision:old?.revision ?? revision,base:old?.base ?? clone(base),serial:(old?.serial || 0)+1});},
    read(key,values,revision){let entry=entries.get(key);if(entry&&same(entry.inputs,values)){entries.delete(key);entry=null;}else if(entry&&entry.revision!==revision&&same(entry.base,values)){entry.revision=revision;}return entry?{...clone(entry),dirty:!same(entry.inputs,values),conflict:entry.revision!==revision&&!same(entry.base,values)}:{inputs:clone(values || {}),revision,dirty:false,conflict:false,serial:0};},
    acknowledge(key,serial,revision,values){const entry=entries.get(key);if(!entry)return;if(entry.serial===serial)entries.delete(key);else{entry.revision=revision;entry.base=clone(values);}},
    discard:key=>entries.delete(key),hasDirty:prefix=>[...entries].some(([key,entry])=>key.startsWith(prefix)&&!same(entry.inputs,entry.base)),clear:()=>entries.clear()
  });
}
function workResultHTML(job,saved={}, {readOnly=false}={}){
  const {esc,button,safeURL}=workUI,result=saved.result ?? saved.output ?? {},items=Array.isArray(result.items)?result.items:Array.isArray(result)?result:[],block=job.result_block || 'human_confirm';
  const verdicts=job.verdicts || [{id:'completed',label:'적합'},{id:'failed',label:'미흡'},{id:'unknown',label:'판단 불가'}];
  const decision=(item)=>{const d=saved.decisions?.[item.id];return `<select data-item-verdict data-item-id="${esc(item.id)}" aria-label="${esc(item.name || item.id)} 판정"${readOnly||d?' disabled':''}><option value="">판정 선택</option>${verdicts.map(v=>`<option value="${esc(v.meaning ?? v.id ?? v.value)}"${d?.verdict===(v.meaning ?? v.id ?? v.value)?' selected':''}>${esc(v.label ?? v.name ?? v.id)}</option>`).join('')}</select>`;};
  const source=value=>safeURL(value)?`<a href="${esc(safeURL(value))}" target="_blank" rel="noopener noreferrer">근거 열기</a>`:'';
  const empty='<p class="ew-empty">아직 저장된 결과가 없습니다.</p>';
  let body='';
  if(block==='schedule')body=`<div class="ew-result-schedule">${esc(result.notice || result.summary || '일정 확인이 필요합니다.')}${result.due_at?`<time datetime="${esc(result.due_at)}">${esc(result.due_at)}</time>`:''}${result.calendar_available===false?'<p>공휴일 달력 미연결 · 일정 확인 필요</p>':''}</div>`;
  else if(['checklist','list_confirm'].includes(block))body=items.length?`<ul class="ew-result-list">${items.map(item=>`<li>${workStatusHTML(item.status || 'unknown')}<span>${esc(item.name || item.title || item.id)}</span>${source(item.url)}${block==='list_confirm'?`<label><input type="checkbox" data-item-confirm data-item-id="${esc(item.id)}"${saved.decisions?.[item.id]?.verdict==='completed'?' checked':''}${readOnly||saved.decisions?.[item.id]?' disabled':''}>확인</label>`:''}</li>`).join('')}</ul>`:empty;
  else if(block==='item_verdict')body=items.length?`<div class="ew-result-items">${items.map(item=>`<article><header><strong>${esc(item.name || item.title || item.id)}</strong>${source(item.url)}</header>${item.evidence?.map(e=>`<p>${workStatusHTML(e.status || 'unknown',e.label || e.name)}${e.content_reviewed===false?'<small>내용 적정성 미검토</small>':''}</p>`).join('') || ''}${item.ai_suggestion&&!saved.decisions?.[item.id]?`<p class="ew-ai-proposal">AI 제안 · ${esc(item.ai_suggestion)} · 사람 미확정</p>`:''}${decision(item)}</article>`).join('')}</div>`:empty;
  else if(block==='ai_review')body=`<div class="ew-ai-proposal"><span>${saved.decisions?.job?'사람 판정 기록 있음 · '+esc(saved.decisions.job.verdict):'AI 초안 · 사람 미확정'}</span><pre>${esc(result.text || result.draft || result.summary || '저장된 AI 제안이 없습니다.')}</pre>${source(result.source_url)}</div>`;
  else if(block==='change_request')body=workRequestHTML(saved.request || result.request || {},job);
  else if(block==='values')body=Object.keys(result).length?`<dl class="ew-facts">${Object.entries(result).filter(([key])=>!['secret','token','pat','credential'].includes(key.toLowerCase())).map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}</dd></div>`).join('')}</dl>`:empty;
  else body=`<p>${esc(job.completion?.description || job.completion_criteria || job.instructions || '결과와 근거를 확인한 뒤 직접 확인해 주세요.')}</p>${result.summary?`<p>${esc(result.summary)}</p>`:''}`;
  return `<section class="ew-result" data-result-block="${esc(block)}">${saved.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한으로 근거를 다시 확인해야 합니다. 이전 기록을 보존하고 현재 권한으로 다시 조회해 주세요.</p>':''}<h3>${esc({values:'확인한 값',schedule:'일정 안내',checklist:'점검 목록',list_confirm:'목록 확인',item_verdict:'항목별 판정',ai_review:'AI 초안 검토',human_confirm:'사람 확인',change_request:'EES 실행 요청'}[block] || '결과')}</h3>${body}${job.result_block==='ai_review'&&saved.attempt_id?button('결과 초안 내보내기','export_result',`data-job-id="${esc(job.id)}" class="ew-text"`):''}${!readOnly&&items.length&&['list_confirm','item_verdict','checklist'].includes(block)?button('목록 수정 · 다시 검토','amend_items','class="ew-text"'):''}</section>`;
}
function workRequestHTML(request={},job={}){
  const {esc,safeURL}=workUI,steps=[['requested','요청 보냄','EES Work'],['accepted','접수','EES'],['running','실행 중','EES'],['reported_complete','완료 보고','EES'],['effect_verified','효과 확인','EES Work']],events=request.events || [];
  return `<div class="ew-request-track">${request.id?`<p>${workStatusHTML(request.state || request.status)} · 승인 ${esc(request.approvals?.length || 0)} / ${esc(request.approval_count || 0)}</p>${request.state==='approval_pending'?workUI.button('요청 승인','approve_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}${['requested','accepted','running','reported_complete','unknown'].includes(request.state)?workUI.button('상태 다시 확인','reconcile_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}`:''}${(request.external_job_id || request.job_number)?`<p>작업 번호 <strong>${esc((request.external_job_id || request.job_number))}</strong></p>`:''}${steps.map(([state,label,actor])=>{const event=events.find(e=>e.state===state || e.status===state || e.kind===state);return `<div>${workStatusHTML(event?state==='running'?'running':'completed':'waiting',label)}<span class="ew-actor" data-actor="${actor}">${actor}</span><small>${esc(event?workUI.time(event.at ?? event.created_at):'대기')}</small></div>`;}).join('')}${['unknown','partial'].includes(request.status || request.state)?'<p class="ew-warning">결과 미확인 · 중복 실행을 막기 위해 자동으로 다시 요청하지 않습니다.</p>':''}<p class="ew-muted">EES 완료 보고와 효과 확인이 모두 끝나야 업무를 완료합니다.</p>${(request.block_reason || request.reason)?`<p role="status">${esc(request.block_reason || request.reason)}</p>`:''}${safeURL(request.external_url)?`<a href="${esc(safeURL(request.external_url))}" target="_blank" rel="noopener noreferrer">EES에서 보기</a>`:''}${job.request_contract?.guide_url&&safeURL(job.request_contract.guide_url)?`<a href="${esc(safeURL(job.request_contract.guide_url))}" target="_blank" rel="noopener noreferrer">EES 가이드</a>`:''}</div>`;
}
function workHistoryHTML(run,jobId=''){
  const {esc}=workUI,attempts=(run?.attempts || []).filter(attempt=>!jobId||attempt.job_id===jobId);
  if(!attempts.length)return '<p class="ew-empty">저장된 실행 시도가 없습니다. 미수행을 성공으로 표시하지 않습니다.</p>';
  return attempts.slice().reverse().map(attempt=>`<details class="ew-history"><summary>${workStatusHTML(attempt.status,attempt.snapshot?.job?.mode==='human'?'사람 확인 기록':'')}<span>${esc(attempt.number || attempt.sequence || attempt.id)}차 · ${esc(workUI.time(attempt.created_at || attempt.started_at))}</span></summary>${attempt.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한을 다시 확인해야 합니다. 다른 사람의 비공개 근거를 표시하지 않습니다.</p>':''}<p>실행 당시 절차 v${esc(attempt.version || run.version)} · 결과 r${esc(attempt.result_revision ?? attempt.number ?? '미기록')}</p><dl class="ew-facts"><div><dt>입력</dt><dd><pre>${esc(JSON.stringify(attempt.inputs ?? attempt.snapshot?.inputs ?? {},null,2))}</pre></dd></div><div><dt>도구 참조</dt><dd><pre>${esc(JSON.stringify(attempt.tool_reference ?? attempt.snapshot?.tool_reference ?? attempt.snapshot?.job?.tool_reference ?? attempt.snapshot?.job?.tool_contract_id ?? {},null,2))}</pre></dd></div><div><dt>결과</dt><dd><pre>${esc(JSON.stringify(attempt.result ?? {},null,2))}</pre></dd></div></dl>${(attempt.decisions || (run?.jobs?.[attempt.job_id]?.decision_history ? run.jobs[attempt.job_id].decision_history.filter(decision=>decision.attempt_id===attempt.id) : [])).map(d=>`<p>사람 판정 · ${esc(d.actor_id)} · ${esc(d.verdict)} · ${esc(d.created_at)}</p>`).join('')}</details>`).join('');
}
function workMyWorkHTML(items=[]){
  const {esc,button,icon}=workUI,groups={incident:'진행 중 장애',overdue:'기한 지남',today:'오늘',week:'이번 주',future:'예정',undated:'기한 없음'};
  if(!items.length)return '<div class="ew-empty"><h3>지금 처리할 내 업무가 없습니다</h3><p>사람의 입력·확인과 점검이 필요한 일이 여기에 나타납니다.</p></div>';
  return Object.entries(groups).map(([key,title])=>{const list=items.filter(item=>(item.bucket || item.group || 'undated')===key);return list.length?`<section class="ew-todo-group"><h3>${key==='incident'?icon('f49d4'):key==='today'?icon('8fa06'):''}${title}<span>${list.length}</span></h3>${list.map(item=>`<button type="button" class="ew-todo" data-action="open_task" data-task-id="${esc(item.id)}" data-schedule-id="${esc(item.schedule_id || '')}" data-run-id="${esc(item.run_id)}" data-job-id="${esc(item.job_id)}" data-workflow-id="${esc(item.workflow_id)}"><span class="ew-todo-title">${workStatusHTML(item.status || 'awaiting_confirmation',item.name || item.title)}${icon('69549')}</span><small>${esc(item.workflow_name || '')}${item.factory_name?' · '+esc(item.factory_name):''}</small><small>${esc(item.reason || '')}${item.due_at?' · '+esc(item.due_at):''}</small>${(item.claimed_by || item.claim_actor)?`<small>담당 ${esc(item.claimed_by || item.claim_actor)}</small>`:''}</button>`).join('')}</section>`:'';}).join('');
}

function workExportText(document){
  const run=document.run;if(!run)return '';const lines=[run.definition?.name || run.workflow_name || 'EES Work 기록',`진행 건 ${run.id} · 게시 v${run.version} · ${run.status}`,`내보낸 시각 ${document.exported_at || ''}`];
  for(const attempt of run.attempts || []){lines.push('',`작업 ${run.definition?.nodes?.[attempt.job_id]?.name || attempt.job_id} · 시도 ${attempt.number} · ${attempt.status}`,`기록 시각 ${attempt.created_at || ''}`,'입력',JSON.stringify(attempt.inputs || {},null,2),'결과',JSON.stringify(attempt.result ?? {},null,2));if(attempt.evidence_access==='requires_current_source_access')lines.push('현재 원본 접근 권한 확인 필요 · 비공개 근거 제외');}
  for(const [id,job] of Object.entries(run.jobs || {}))for(const decision of job.decisions || [])lines.push(`사람 판정 · ${id} · ${decision.item_id} · 결과 r${decision.result_revision} · ${decision.verdict} · ${decision.actor_id} · ${decision.created_at}`);
  return lines.join('\n');
}
function workLegacyHTML(legacy){
  const {esc,button}=workUI;if(!legacy)return '';if(legacy.error)return `<p class="ew-warning">이전 기록 조회 실패 · ${esc(legacy.error)}</p>`;
  return `<section class="ew-legacy"><h3>이전 버전 기록</h3><p class="ew-muted">${esc(legacy.notice || '이전 실행 기능은 사용 중지되었습니다. 남아 있는 과거 기록만 읽습니다.')}</p>${(legacy.records || []).map(item=>button(`${item.process_name || item.id} · ${item.status || '상태 미기록'}${item.simulation?' · 시뮬레이션':''}`,'open_legacy',`data-case-id="${esc(item.id)}" class="ew-record"`)).join('') || '<p class="ew-empty">조회할 이전 기록이 없습니다.</p>'}</section>`;
}

function workHistoricalReferenceHTML(run,reference,workflow){
  const {esc}=workUI;
  if(!reference?.run_id&&workflow?.id===reference?.workflow_id){const version=workflow.versions?.find(item=>item.version===reference.version);return version?`<header class="ew-work-heading"><h2>대화에서 참조한 게시 절차</h2><p>게시 v${esc(version.version)} · 읽기 전용</p></header><pre>${esc(JSON.stringify(version.definition,null,2))}</pre>`:'<p class="ew-warning">이 메시지에는 보존된 게시 버전이 지정되지 않았습니다. 현재 편집 초안을 당시 내용으로 대신 표시하지 않습니다.</p>';}
  if(!run||reference?.run_id!==run.id)return '<p class="ew-warning">현재 권한으로 이 진행 건의 기록을 확인하지 못했습니다.</p>';
  if(!reference.attempt_id)return '<p class="ew-warning">이 메시지에는 당시 실행 시도 식별자가 기록되지 않았습니다. 현재 결과를 과거 근거로 대신 표시하지 않습니다.</p>';
  const attempt=(run.attempts || []).find(item=>item.id===reference.attempt_id&&item.job_id===reference.job_id);
  if(!attempt||reference.version!==undefined&&reference.version!==run.version||reference.result_revision!==undefined&&reference.result_revision!==attempt.number)return '<p class="ew-warning">참조한 버전·실행 시도를 현재 권한으로 확인하지 못했습니다. 다른 시도의 결과로 대신 표시하지 않습니다.</p>';
  return `<header class="ew-work-heading"><h2>대화에서 참조한 과거 기록</h2><p>게시 v${esc(run.version)} · 실행 시도 ${esc(attempt.number)} · 읽기 전용</p></header>${workHistoryHTML({...run,attempts:[attempt]},reference.job_id)}`;
}
function workMessageReferenceHTML(reference,messageId){
  if(reference?.kind!=='workspace'||!reference.workflow_id)return '';
  const {esc,icon}=workUI,label=reference.attempt_id?`업무 근거 · v${reference.version ?? '?'} · ${reference.result_revision ?? '?'}차`:reference.run_id?'업무 참조 · 당시 시도 미지정':'업무 절차 참조';
  return `<button type="button" data-action="open_reference" data-message-id="${esc(messageId)}">${icon('522b5')}<span>${esc(label)}</span></button>`;
}

function workAdminHTML(data){
  const {esc,button}=workUI;if(!data.capabilities?.is_admin)return '<p class="ew-warning">Native 관리자 권한이 필요합니다.</p>';
  const roles={viewer:'조회',participant:'참여·실행',manager:'절차·설정 관리',requester:'EES 요청',reviewer:'요청 검토'};
  return `<header class="ew-work-heading"><h2>공장·접근 범위</h2><p>기존 Native 사용자와 그룹에 업무 범위를 연결합니다. 개인 PAT는 여기에서 관리하지 않습니다.</p></header><section><h3>Native 대화의 Work 연결</h3><p class="ew-muted">현재 제품의 읽기·제안 전용 도구를 확인하고, 선택한 Native 사용자·그룹에만 연결합니다.</p>${button('Work 도구 설정 확인','admin_work_tool','class="ew-secondary"')}</section><section><h3>공장 정보</h3>${button('공장 등록','admin_factory','class="ew-secondary"')}<div class="ew-admin-list">${(data.factories || []).map(item=>`<article><strong>${esc(item.name)}</strong><small>${esc(item.system_id)} · ${esc(item.id)} · r${esc(item.revision)}</small>${button('수정','admin_factory',`data-id="${esc(item.id)}"`)}</article>`).join('') || '<p class="ew-empty">등록된 공장이 없습니다.</p>'}</div></section><section><h3>업무 접근 범위</h3>${button('접근 범위 등록','admin_access','class="ew-secondary"')}<div class="ew-admin-list">${(data.access || []).map(item=>{const person=(data.people || []).find(person=>person.value?.id===item.principal_id&&person.value?.kind===item.principal_kind);return `<article><strong>${esc(person?.label || person?.name || item.principal_id)}</strong><small>${esc(item.principal_kind)} · ${esc(item.principal_id)}</small><p>${esc(item.system_id)} · ${esc(item.factory_id==='*'?'시스템 전체 범위':item.factory_id)} · ${esc(item.roles.map(role=>roles[role] || role).join(', '))} · ${item.active?'사용':'중지'}</p>${button('수정','admin_access',`data-id="${esc(item.id)}"`)}</article>`;}).join('') || '<p class="ew-empty">등록된 업무 접근 범위가 없습니다.</p>'}</div></section>`;
}

function createWorkView({callbacks}){
  const {$,esc,button,icon,categories,badge,finished}=workUI;
  let snapshot={state:null,selection:{}},entry=null,host=null,chatColumn=null,chatRow=null,header=null,lastKey='',pendingRender=false;
  const drafts=createWorkInputDrafts(),positions=new Map(),modelChoices=new Map();let currentDraftKey='';
  const state=()=>snapshot.state || {},selection=()=>snapshot.selection || {};
  const definition=()=>state().run?.definition || state().workflow?.published?.definition || state().workflow?.published || state().workflow?.definition || state().workflow?.draft || {};
  const job=()=>definition().nodes?.[selection().job_id];
  const inputKey=()=>[state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id,selection().job_id,selection().tab].join('/');
  const modelKey=()=>[state().capabilities?.actor_id,selection().workflow_id,selection().run_id,selection().job_id].join('/');
  function executionModels(){const operations=state().operations || {},models=operations.models || [],key=modelKey();if(operations.error||models.length<=1||!models.some(model=>model.id===modelChoices.get(key)))modelChoices.delete(key);return workExecutionModelHTML(operations,modelChoices.get(key));}
  function capture(){const model=$('#ees-work-execution-model',host);if(model&&(state().operations?.models || []).length>1)modelChoices.set(modelKey(),model.value);const form=$('#ees-work-inputs',host);if(form&&currentDraftKey){try{const source=form.dataset.settings==='true'?state().settings?.values || {}:state().run?.inputs || {};const previous=drafts.read(currentDraftKey,source,Number(form.dataset.revision)),values={...previous.inputs};for(const field of form.querySelectorAll('[data-work-input]'))if(!field.disabled)delete values[field.name];Object.assign(values,workReadInputs(form));if(JSON.stringify(values)!==JSON.stringify(previous.inputs))drafts.edit(currentDraftKey,values,Number(form.dataset.revision),source);}catch(_){}}if(host)positions.set(lastKey,{scroll:$('#ees-work-content',host)?.scrollTop || 0,expanded:[...host.querySelectorAll('details[open]')].map(el=>el.dataset.key).filter(Boolean)});}
  function ensure(){
    const anchor=$('#sidebar-search-button'),pane=$('#chat-container #chat-pane');if(!anchor||!pane)return false;
    document.body.dataset.eesIntegrated='true';
    if(!entry?.isConnected){entry=document.createElement('section');entry.id='ees-work-entry';entry.dataset.eesWork='';entry.setAttribute('aria-label','업무 탐색');anchor.parentElement.insertAdjacentElement('afterend',entry);}
    const column=pane.parentElement,row=column?.parentElement;if(!row)return false;
    if(chatColumn!==column){chatColumn?.classList.remove('ees-integrated-chat');chatRow?.classList.remove('ees-integrated-row');chatColumn=column;chatRow=row;column.classList.add('ees-integrated-chat');row.classList.add('ees-integrated-row');}
    if(!host){host=document.createElement('aside');host.id='ees-work-panel';host.dataset.eesWork='';host.setAttribute('aria-label','업무 패널');}
    if(!host.isConnected||host.parentElement!==row)row.append(host);
    if(!header?.isConnected){header=document.createElement('div');header.id='ees-work-context';header.dataset.eesWork='';column.prepend(header);}
    return true;
  }
  function navigator(){
    if(!entry)return;const s=selection(),data=state(),systems=data.systems || [],factories=data.factories || [],author=s.mode==='author';
    const system=systems.find(item=>(item.id ?? item)===s.system_id),factory=factories.find(item=>item.id===s.factory_id),current=(data.workflows || []).filter(workflow=>!s.system_id||workflow.system_id===s.system_id);
    const mode=`<nav class="ew-mode" aria-label="작업 모드">${button('업무','mode',`data-mode="work" aria-pressed="${!author}"`)}${button('워크스페이스','mode',`data-mode="author" aria-pressed="${author}"`)}</nav>`;
    const systemControl=`<button type="button" data-action="scope" id="ees-work-system-trigger" aria-haspopup="dialog">${icon('f34f3')}${!author?'<small>시스템</small>':''}<span>${esc(system?.name || system?.id || system || '선택 필요')}</span>${author?`<small>${data.capabilities?.managed_systems?.includes(s.system_id)?'담당':'조회'}</small>`:''}${icon('ead50')}</button>`;
    const scope=`<p class="ew-nav-caption">${author?'관리 시스템':'작업 위치'}</p><div class="ew-scope">${!author?`<button type="button" data-action="scope" id="ees-work-site-trigger" aria-haspopup="dialog">${icon('40095')}<small>공장</small><span>${esc(factory?.name || '전체 공장')}</span>${icon('ead50')}</button>`:''}${systemControl}</div>`;
    const navItem=(action,asset,label,count,active)=>`<button type="button" data-action="${action}"${active?' aria-current="page"':''}>${icon(asset)}<span>${label}</span>${count===undefined?'':`<small>${count}</small>`}</button>`;
    let links='',details='';
    if(author){
      links=`<nav class="ew-nav-links">${navItem('procedures','e8a37','업무 절차',current.length,!['tools','workspace_admin'].includes(s.tab))}${navItem('tools','cece5','도구',data.operations?.error?undefined:(data.operations?.tools || []).length,s.tab==='tools')}${navItem('native_skills','f908d','스킬·지침',undefined,false)}</nav>`;
      const recent=current.filter(workflow=>workflow.updated_at).slice().sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))).slice(0,8);
      details=`<p class="ew-nav-caption">최근 편집</p><nav class="ew-workflows ew-recent">${recent.map(workflow=>`<button type="button" data-action="workflow" data-workflow-id="${esc(workflow.id)}"${workflow.id===s.workflow_id?' aria-current="page"':''}>${icon({ops:'126c7',setup:'f6bbc',incident:'4fb09'}[workflow.category] || 'e8a37')}<span>${esc(workflow.name)}</span></button>`).join('') || '<p class="ew-empty">최근 편집한 절차가 없습니다.</p>'}</nav><nav class="ew-native-management">${button('Native 모델·도구 관리','native_workspace')}${data.capabilities?.is_admin?button('공장·접근 범위','workspace_admin'):''}</nav>`;
    }else{
      links=`<nav class="ew-nav-links">${[['my_work','4df0d','내 업무'],['find','2e769','워크플로우 찾기'],['records','c325d','실행 기록'],['chats','093d6','대화 기록']].map(([action,asset,label])=>navItem(action,asset,label,action==='my_work'&&data.my_work?.length?data.my_work.length:undefined,s.tab===action)).join('')}</nav>`;
      details=`<p class="ew-nav-caption">업무</p><nav class="ew-workflows">${Object.entries(categories).map(([category,label])=>`<details data-category="${category}"${s.collapsed?.includes(category)?'':' open'}><summary>${icon({ops:'126c7',setup:'f6bbc',incident:'4fb09'}[category])}<span>${label}</span><span class="ew-category-auto">${workAutoStatusHTML(['failed','missed','running','succeeded'].find(status=>current.some(workflow=>workflow.category===category&&workflow.last_auto_status===status)))}</span></summary>${current.filter(w=>w.category===category).map(w=>`<button type="button" data-action="workflow" data-workflow-id="${esc(w.id)}"${w.id===s.workflow_id?' aria-current="page"':''}><span>${esc(w.name)}</span>${workAutoStatusHTML(w.last_auto_status)}</button>`).join('')}</details>`).join('')}${!current.length?'<p class="ew-empty">등록된 업무 절차가 없습니다.</p>':''}</nav>`;
    }
    const html=mode+scope+links+details;if(entry.innerHTML!==html)entry.innerHTML=html;
  }
  function runOverview(){const data=state(),run=data.run,def=definition(),nodes=Object.values(def.nodes || {}),jobs=nodes.filter(node=>node.type==='j'),root=nodes.find(node=>node.type==='p'&&!node.parent);
    const automatic=scope=>jobs.filter(node=>['tool','ai'].includes(node.mode)&&node.result_block!=='change_request'&&workUI.lineage(node.id,def).some(parent=>parent.id===scope.id));
    const scopeButton=scope=>scope&&!finished(run)&&automatic(scope).length?button(scope.type==='p'?'절차 실행':'단계 실행','execute_scope',`data-node-id="${esc(scope.id)}" data-mutation class="ew-secondary"`):'';
    const jobButton=node=>`<button type="button" data-action="job" data-job-id="${esc(node.id)}">${workStatusHTML(run?.jobs?.[node.id]?.status || 'unstarted',node.name)}${icon('69549')}</button>`;
    const groups=nodes.filter(node=>node.type==='t');
    const steps=groups.length?groups.map(stage=>`<section class="ew-stage"><header><h3>${esc(stage.name)}</h3>${scopeButton(stage)}</header><div class="ew-run-steps">${jobs.filter(node=>workUI.lineage(node.id,def).some(parent=>parent.id===stage.id)).map(jobButton).join('')}</div></section>`).join('')+(jobs.some(node=>node.parent===root?.id)?`<div class="ew-run-steps">${jobs.filter(node=>node.parent===root.id).map(jobButton).join('')}</div>`:''):`<div class="ew-run-steps">${jobs.map(jobButton).join('')}</div>`;
    const scopes=(data.operations?.scope_runs || []).filter(item=>item.run_id===run?.id);
    const scopeStatus=scopes.length?`<section class="ew-scope-status"><h3>절차·단계 실행</h3>${scopes.map(item=>`<p>${workStatusHTML(item.status)} · ${esc(def.nodes?.[item.node_id]?.name || item.node_id)}</p><small>${esc(item.reason || '')}${item.current_job_id?' · '+esc(def.nodes?.[item.current_job_id]?.name || item.current_job_id):''}</small>`).join('')}</section>`:'';
    const models=jobs.some(node=>node.mode==='ai')?executionModels():'';

    return `<header class="ew-work-heading"><p>${esc(data.workflow?.name || def.name || '업무 절차')}</p><h2>${run?'진행 건':'진행 건 시작'}</h2>${run?`<p>${badge(run.status)} · 게시 v${esc(run.version || run.published_version)} · ${esc(run.id)}</p>`:'<p>게시한 절차 버전으로 새 진행 건을 시작합니다.</p>'}</header>${!run?`<div class="ew-empty">${data.workflow?.published_version?button('진행 건 시작','start_run','class="ew-primary"'):'게시된 버전이 없습니다. 워크스페이스에서 검사하고 게시해 주세요.'}</div>`:`${steps}${models}${scopeStatus}${root?`<div class="ew-scope-execution">${scopeButton(root)}<small>저장한 입력으로 실행 가능한 도구·AI 작업을 진행합니다. 사람 확인과 EES 변경 요청은 자동 확정하지 않습니다.</small></div>`:''}<footer class="ew-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}${!finished(run)?button('진행 건 종료','close_run')+button('진행 건 취소','cancel_run'):''}</footer>`}`;
  }
  function jobPanel(){const data=state(),s=selection(),node=job(),run=data.run,saved=run?.jobs?.[node.id] || {},readonly=finished(run),fields=node.inputs || [],settings=s.tab==='settings',source=settings?data.settings?.values || {}:run?.inputs || {},revision=settings?data.settings?.revision || 0:run?.revision || 0;
    currentDraftKey=inputKey();const draft=drafts.read(currentDraftKey,source,revision),visibleFields=fields.filter(field=>(['workflow','factory'].includes(field.scope))===settings);
    const header=`<button class="ew-text" type="button" data-action="overview">← 절차 개요</button><header class="ew-work-heading"><h2>${esc(node.name)}</h2>${workStatusHTML(saved.status || 'unstarted')}<p>${esc(node.instructions || '')}</p>${saved.claim_actor===data.capabilities?.actor_id&&!readonly&&saved.status!=='running'?button('맡기 해제','release_task','class="ew-text"'):''}</header><nav class="ew-tabs" aria-label="작업 보기">${[['current','현재 상태'],['history','실행 기록'],['settings','업무 설정']].map(([tab,label])=>button(label,'tab',`data-tab="${tab}" aria-pressed="${s.tab===tab}"`)).join('')}</nav>`;
    if(s.tab==='history')return header+`<div class="ew-export-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}</div>`+workHistoryHTML(run,node.id);
    const modelControls=node.mode==='ai'?executionModels():'';
    const inputs=visibleFields.length?`<section><h3>${settings?'업무 설정':'이번 진행 건 입력'} <small>${settings?'다음 실행에도 계속 사용':'이번 실행에 사용'}</small></h3>${!settings&&!readonly?button('AI 입력 초안','propose_inputs','class="ew-text"'):''}<form id="ees-work-inputs" data-settings="${settings}" data-revision="${draft.revision}">${visibleFields.map(field=>workInputHTML(field,draft.inputs[field.id],{disabled:readonly,prefix:settings?'settings':'run',people:data.people || [],lookup:data.input_options?.[field.id]})).join('')}${draft.conflict?'<p class="ew-warning" role="alert">다른 사람이 값을 변경했습니다. 작성 중인 값은 보존했습니다. 최신 값과 비교해 다시 입력해 주세요.</p>'+button('최신 값으로 돌아가기','discard_inputs'):''}${!readonly?button(settings?'설정 저장':'입력 저장','save_inputs',`data-mutation class="ew-secondary"${draft.conflict?' disabled':''}`):''}</form></section>`:'';
    const proposal=data.input_proposal;const proposalHTML=!settings&&proposal?`<section class="ew-input-proposal ew-ai-proposal"><h3>AI 입력 초안 · 저장 전</h3><pre>${esc(JSON.stringify(proposal.values,null,2))}</pre>${(proposal.warnings || []).map(warning=>`<p>${esc(warning)}</p>`).join('')}<p>편집 중인 입력에 반영해도 저장·실행되지 않습니다.</p>${button('입력에 반영','apply_input_proposal','class="ew-secondary"')}${button('제안 닫기','discard_input_proposal','class="ew-text"')}</section>`:'';
    return header+inputs+proposalHTML+modelControls+(settings?`<p class="ew-muted">개인 PAT와 비밀정보는 Native 개인 설정에서 관리합니다. 여기에 입력하지 마세요.</p>`:workResultHTML(node,saved,{readOnly:readonly})+`<footer class="ew-job-actions">${(saved.block_reason || saved.reason)?`<p class="ew-warning">${esc(saved.block_reason || saved.reason)}</p>`:''}${readonly?'<p>종료된 진행 건 · 당시 기록을 조회하고 있습니다.</p>':node.result_block==='change_request'?button('요청 내용 확인…','request_intent','data-mutation class="ew-primary"'):node.mode==='human'?button('확인 완료','confirm','data-mutation class="ew-primary"'):button(saved.evidence_access==='requires_current_source_access'&&node.mode==='tool'?'현재 권한으로 다시 조회':saved.attempt_id?'다시 실행':'지금 실행','execute','data-mutation class="ew-primary"')+(node.human_confirmation&&!['list_confirm','item_verdict','checklist'].includes(node.result_block)?button('판정 확정','confirm','data-mutation class="ew-secondary"'):'')}</footer>`);
  }
  function panel(){if(!host)return;const s=selection(),data=state(),key=[s.mode,s.tab,s.run_id,s.workflow_id,s.job_id].join('/');lastKey=key;host.dataset.eesMode=s.mode || 'work';host.hidden=s.panel_open===false;
    const title=s.mode==='author'?'워크스페이스':s.tab==='my_work'?'내 업무':s.tab==='records'?'실행 기록':'업무';
    const top=`<header class="ew-panel-header"><strong>${title}</strong><span>${esc(data.workflow?.name || '')}</span>${button('닫기','close_panel','aria-label="업무 패널 닫기" class="ew-icon-button"')}</header>`;
    if(s.mode==='author'&&s.tab!=='workspace_admin'){if(!$('#ees-work-authoring-panel',host))host.innerHTML=top+'<div id="ees-work-authoring-panel" class="ew-scroll"></div>';return;}
    let body='';currentDraftKey='';
    if(snapshot.error&&!snapshot.state)body=`<div class="ew-error" role="alert"><p>${esc(snapshot.error)}</p>${button('다시 조회','refresh')}</div>`;
    else if(!snapshot.state)body='<p role="status" class="ew-empty">업무 정보를 불러오는 중입니다.</p>';
    else if(s.tab==='historical_reference')body=workHistoricalReferenceHTML(data.run,s.historical_reference,data.workflow);
    else if(s.tab==='workspace_admin')body=workAdminHTML(data);
    else if(s.tab==='my_work')body=workMyWorkHTML(data.my_work || []);
    else if(s.tab==='records')body=((data.runs || []).length?(data.runs || []).map(run=>`<button type="button" class="ew-record" data-action="open_run" data-run-id="${esc(run.id)}" data-workflow-id="${esc(run.workflow_id)}"><strong>${esc(run.name || run.workflow_name || run.id)}</strong>${workStatusHTML(run.status)}<small>게시 v${esc(run.version || run.published_version)} · ${esc(workUI.time(run.created_at))}</small></button>`).join(''):'<p class="ew-empty">저장된 진행 건이 없습니다.</p>')+workLegacyHTML(data.legacy);
    else if(!s.workflow_id)body='<div class="ew-empty"><h3>업무 절차를 선택해 주세요</h3><p>왼쪽에서 업무를 찾거나 워크스페이스에서 새 절차를 작성할 수 있습니다.</p></div>';
    else if(job()&&data.run)body=jobPanel();else body=runOverview();
    host.innerHTML=top+`<div id="ees-work-content" class="ew-scroll">${snapshot.error&&snapshot.state?`<div class="ew-error" role="alert">${esc(snapshot.error)}</div>`:''}${data.operations?.error?`<p class="ew-warning" role="alert">실행·예약 정보를 조회하지 못했습니다. ${esc(data.operations.error)}</p>`:''}${body}</div>`;
    const position=positions.get(key);if(position)$('#ees-work-content',host).scrollTop=position.scroll;setBusy(snapshot.busy);
  }
  function context(){if(!header)return;const node=job(),run=state().run;const html=`<span>${esc(node?.name || state().workflow?.name || '대화')}</span><div><small>참고</small><span class="ew-reference">${esc(node?.name || (run?'진행 건':'일반 대화'))}</span>${button('업무 열기','open_panel','aria-label="업무 패널 열기"')}${button('새 대화','new_chat')}</div>`;if(header.innerHTML!==html)header.innerHTML=html;}
  function setBusy(value){host?.querySelectorAll('[data-mutation]').forEach(el=>{if(el.dataset.ownDisabled!=='true')el.disabled=Boolean(value)||el.closest('form')?.querySelector('.ew-warning')!==null&&Boolean(el.closest('form'));});host?.setAttribute('aria-busy',String(Boolean(value)));}
  function focusSnapshot(){
    const active=document.activeElement;if(!active||!(host?.contains(active)||entry?.contains(active)||header?.contains(active)))return null;
    const attributes=['id','name','data-action','data-job-id','data-workflow-id','data-tab','data-mode','data-item-id','data-item-verdict','data-item-confirm','data-field-id'];
    return {attributes:attributes.filter(name=>active.hasAttribute?.(name)).map(name=>[name,active.getAttribute(name)]),start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection};
  }
  function restoreFocus(saved){
    if(!saved?.attributes.length||$('#ees-work-dialog'))return;
    for(const root of [host,entry,header]){const target=[...(root?.querySelectorAll('button,input,select,textarea,a,summary') || [])].find(item=>saved.attributes.every(([name,value])=>item.getAttribute(name)===value));if(!target||target.disabled)continue;target.focus({preventScroll:true});if(typeof saved.start==='number'&&typeof target.setSelectionRange==='function'){try{target.setSelectionRange(saved.start,saved.end,saved.direction);}catch(_){}}return;}
  }
  function render(value){const focus=focusSnapshot();capture();snapshot=value;if(!ensure())return;navigator();panel();context();restoreFocus(focus);}
  function sync(value){snapshot=value;if(!ensure())return;if(!entry.firstChild)navigator();if(!host.firstChild)panel();context();}
  function readInputs(){capture();const settings=selection().tab==='settings';return {...drafts.read(inputKey(),settings?state().settings?.values || {}:state().run?.inputs || {},settings?state().settings?.revision || 0:state().run?.revision || 0),key:inputKey(),settings};}
  function applyInputValues(values){capture();const source=state().run?.inputs || {},revision=state().run?.revision || 0,existing=drafts.read(inputKey(),source,revision);drafts.edit(inputKey(),{...existing.inputs,...values},revision,source);panel();}
  function clearInputs(key,serial,revision,values){drafts.acknowledge(key,serial,revision,values);}
  function scopeDialog(){const data=state(),s=selection();return workUI.dialog({title:'작업 위치 선택',note:'공장과 시스템을 바꾸어도 대화와 작성 중인 글은 유지됩니다.',html:`<div class="ew-scope-columns${s.mode==='author'?' ew-system-only':''}"><section${s.mode==='author'?' hidden':''}><h3>공장</h3><input type="search" id="ees-factory-search" placeholder="공장 검색" aria-label="공장 검색"><div id="ees-factory-list"><button type="button" data-action="choose_factory" data-factory-id="" aria-pressed="${!s.factory_id}">${icon('40095')}<span>전체 공장<small>시스템 단위 업무를 볼 때</small></span></button>${(data.factories || []).map(f=>`<button type="button" data-action="choose_factory" data-factory-id="${esc(f.id)}" aria-pressed="${s.factory_id===f.id}"${f.allowed===false?' disabled':''}>${icon('40095')}<span>${esc(f.name)}<small>${esc([f.country,f.line].filter(Boolean).join(' · '))}</small></span></button>`).join('')}</div></section><section><h3>시스템</h3>${(data.systems || []).map(system=>typeof system==='string'?{id:system,name:system}:system).map(system=>`<button type="button" data-action="choose_system" data-system-id="${esc(system.id)}" aria-pressed="${s.system_id===system.id}"${system.allowed===false?' disabled':''}>${icon('f34f3')}<span>${esc(system.name || system.id)}<small>${system.allowed===false?'권한 없음':system.role==='owner'?'담당':'참여'}</small></span></button>`).join('')}</section></div>`});}
  function suspend(){workUI.closeDialog();capture();entry?.remove();host?.remove();header?.remove();chatColumn?.classList.remove('ees-integrated-chat');chatRow?.classList.remove('ees-integrated-row');chatColumn=null;chatRow=null;delete document.body.dataset.eesIntegrated;}
  function reset(){workUI.closeDialog();drafts.clear();positions.clear();modelChoices.clear();entry?.remove();host?.remove();header?.remove();chatColumn?.classList.remove('ees-integrated-chat');chatRow?.classList.remove('ees-integrated-row');entry=null;host=null;header=null;chatColumn=null;chatRow=null;snapshot={state:null,selection:{}};delete document.body.dataset.eesIntegrated;}
  return Object.freeze({render,sync,reset,suspend,setBusy,readInputs,clearInputs,applyInputValues,discardInputs:()=>{drafts.discard(inputKey());panel();},scopeDialog,authoringHost:()=>$('#ees-work-authoring-panel',host),hasPendingInputs:()=>drafts.hasDirty([state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id].join('/')+'/'),capture,handleEvent:()=>({handled:false})});
}
