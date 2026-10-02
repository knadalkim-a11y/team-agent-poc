/* EES Work: shared schema renderers and the Native conversation's side panels.
 * The server owns business state. This file owns only an actor's display/drafts. */
const workUI = (() => {
  const $ = (selector, parent = document) => parent?.querySelector(selector) || null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  const categories = {ops:'운영',setup:'셋업',incident:'장애대응'};
  const levels = {p:'업무 절차',t:'단계',j:'작업'};
  const statuses = {open:'진행 중',unstarted:'미실행',pending:'대기',scheduled:'예약',ready:'시작 가능',running:'실행 중',in_progress:'진행 중',awaiting_input:'입력 필요',awaiting_confirmation:'사람 확인 필요',review_required:'다시 검토 필요',completed:'완료',succeeded:'도구 성공',success:'도구 성공',failed:'실패',partial:'부분 결과',unknown:'결과 미확인',missed:'예약 놓침',excluded:'적용 제외',cancelled:'취소',blocked:'진행 조건 확인',draft:'초안',published:'게시됨',review:'검토 필요',waiting:'대기',waiting_input:'입력 필요',waiting_confirmation:'사람 확인 필요',reported_complete:'완료 보고',accepted:'접수',requested:'요청 보냄',effect_verified:'효과 확인'};
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
  const glyph=['completed','effect_verified'].includes(status)?'d553d':['failed'].includes(status)?'44a96':['awaiting_input','awaiting_confirmation','review_required','review','waiting_input','waiting_confirmation'].includes(status)?'9c63b':['running','in_progress'].includes(status)?'8f8a1':['unknown','missed','partial'].includes(status)?'d448c':'40ef1';
  return `<span class="ew-status" data-status="${esc(status)}">${icon(glyph)}<span>${esc(label || statuses[status] || status || '미실행')}</span></span>`;
}
function workAutoStatusHTML(status){
  const labels={failed:'실패',missed:'놓침',running:'실행 중',succeeded:'정상'},asset={failed:'7495b',succeeded:'c6340',running:'478bf',missed:'ce467'}[status];
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
function workNoticeHTML(title,detail='',tone='attention'){
  const {esc}=workUI;return `<div class="ew-notice" data-tone="${esc(tone)}" role="status"><strong>${esc(title)}</strong>${detail?`<p>${esc(detail)}</p>`:''}</div>`;
}
function workReasonText(reason){
  return ({delivery_unconfigured:'송부 연결 필요 · 본문 검토만 저장했습니다.',effect_criterion_not_met:'효과 확인 실패 · 정한 완료 기준을 충족하지 못했습니다.',effect_criterion_required:'효과 확인 기준을 설정해 주세요.',effect_observation_unknown:'효과 확인 결과가 미확인입니다.',ees_connector_unconfigured:'EES 요청 연결이 아직 설정되지 않았습니다.',request_result_unknown:'요청 결과가 미확인입니다. 같은 작업의 상태를 확인해 주세요.',ees_response_invalid:'EES 응답을 확인하지 못했습니다.',ees_status_unavailable:'EES 상태를 조회하지 못했습니다.',read_retry_deadline:'조회 제한 시간이 지났습니다. 결과를 확인해 주세요.',read_retry_source_changed:'입력이나 근거가 바뀌어 자동 재조회를 중단했습니다.',zero_selection_policy_required:'선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다.'})[reason] || reason || '';
}
function workPersonLabel(person,people=[]){
  const found=people.find(item=>item.value?.kind===person?.kind&&item.value?.id===person?.id);
  return found?.label || found?.name || '이름 확인 필요';
}
function workAssignmentHTML(node,saved,people=[]){
  const {esc}=workUI;
  return `${node.assignee?`<p class="ew-assignee">배정된 ${node.assignee.kind==='group'?'그룹':'담당자'} · ${esc(workPersonLabel(node.assignee,people))}</p>`:''}${saved.claim_actor?`<p class="ew-claimant">현재 담당 · ${esc(workPersonLabel({kind:'user',id:saved.claim_actor},people))}</p>`:''}`;
}
function workListSourceAttempt(run,attemptId){
  const attempts=run?.attempts || [],seen=new Set();let attempt=attempts.find(item=>item.id===attemptId);
  while(attempt){
    if(attempt.evidence_access||seen.has(attempt.id))return null;seen.add(attempt.id);
    const previous=attempt.result?.amendment?.previous_attempt;if(!previous)return attempt;
    const parent=attempts.find(item=>item.id===previous&&item.job_id===attempt.job_id);if(!parent)return null;attempt=parent;
  }
  return null;
}
function workListItems(result={}){
  const actual=Array.isArray(result.items)?result.items:[],ids=new Set(actual.map(item=>item.id));
  return [...actual.map(item=>({...workUI.clone(item),selected:item.selected!==false,manual:item.source?.kind==='human_added'||item.manual===true})),...(Array.isArray(result.suggestions)?result.suggestions:[]).filter(item=>item&&typeof item.id==='string'&&!ids.has(item.id)).map(item=>({...workUI.clone(item),selected:false,candidate:true}))];
}
function workListHTML(saved={}, {readOnly=false,listDraft=null,sourceCount}={}){
  if(saved.evidence_access)return workNoticeHTML('현재 원본 접근 권한을 확인해 주세요','이전 목록이나 작성 중인 선택을 현재 근거로 대신 표시하지 않습니다.');
  const {esc,button,safeURL}=workUI,result=saved.result || {},items=listDraft?.items || workListItems(result),included=items.filter(item=>item.selected),extra=items.filter(item=>item.selected&&item.candidate);
  const confirmed=Object.keys(saved.decisions || {}).length>0,readonly=readOnly||confirmed,queried=sourceCount===undefined?(result.items || []).filter(item=>item.source?.kind!=='human_added'&&!item.manual).length:sourceCount;
  if(['failed','unknown'].includes(saved.status))return workNoticeHTML('조회 결과를 확인하지 못했습니다','지난 회차 목록이나 이전 결과는 보여주지 않습니다. 현재 조회 권한과 연결 상태를 확인해 주세요.',saved.status==='failed'?'danger':'attention');
  if(!items.length&&!Array.isArray(result.items))return '<p class="ew-empty">아직 저장된 결과가 없습니다.</p>';
  const row=item=>`<tr data-candidate="${Boolean(item.candidate)}"><td><input type="checkbox" id="ees-list-${esc(item.id)}" data-item-confirm data-list-include data-item-id="${esc(item.id)}" aria-label="${esc(item.id)} 포함"${item.selected?' checked':''}${readonly?' disabled':''}></td><td>${safeURL(item.url)?`<a href="${esc(safeURL(item.url))}" target="_blank" rel="noopener noreferrer">${esc(item.id)}</a>`:esc(item.id)}</td><td>${esc(item.name || item.title || item.id)}${item.candidate?`<small>${esc(item.reason || item.note || '목록 포함 여부를 사람이 확인해 주세요.')}</small><span class="ew-badge">확인 후보 · 미확정</span>`:''}${item.manual?'<small>사람이 추가 · 원본 조회 확인 전</small>':''}</td><td>${esc(item.status_name || item.status || '미확인')}</td></tr>`;
  return `<div class="ew-list-confirm"><p>${queried===null?'원본 조회 건수 확인 필요':`조회 ${esc(queried)}건`} · 빼거나 더할 항목을 고른 뒤 확정</p><table class="ew-list-table"><thead><tr><th><span class="sr-only">포함</span></th><th>항목</th><th>제목</th><th>상태</th></tr></thead><tbody>${items.filter(item=>!item.candidate).map(row).join('')}</tbody></table>${items.some(item=>item.candidate)?`<h4>조회 조건 외 확인 후보 ${items.filter(item=>item.candidate).length}</h4><table class="ew-list-table ew-list-candidate"><tbody>${items.filter(item=>item.candidate).map(row).join('')}</tbody></table>`:''}${!readonly?`<button type="button" data-action="add_list_item" class="ew-text">${workUI.icon('b456d')} 번호로 항목 추가</button>`:''}<div class="ew-list-toolbar"><small>포함 ${included.length} · 추가 ${extra.length+items.filter(item=>item.manual&&item.selected&&!item.candidate).length} · 제외 ${items.filter(item=>!item.selected&&!item.candidate&&!item.manual).length}</small>${confirmed?'<span class="ew-badge">사람 확정 기록 있음</span>':!readonly?button('선택 목록 저장','save_list_selection','data-mutation class="ew-secondary"')+button(`목록 확정 (${included.length}건)`,'confirm_list',`data-mutation class="ew-primary"${!included.length?' disabled data-own-disabled="true"':''}`):''}</div>${!included.length&&!confirmed?workNoticeHTML('선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다','선택 상태는 저장할 수 있지만 확정은 보류합니다.'):''}${saved.status==='partial'?workNoticeHTML('부분 결과 · 미확인 항목이 남아 있습니다','목록을 확인해도 조회가 완전한 결과로 바뀌지는 않습니다.'):''}</div>`;
}
function workReviewDraftHTML(job,saved,{readOnly=false,reviewDraft=null}={}){
  if(saved.evidence_access)return workNoticeHTML('현재 원본 접근 권한을 확인해 주세요','이전 AI 본문과 편집 중인 초안을 표시하지 않습니다.');
  if(['failed','unknown','running'].includes(saved.status))return workNoticeHTML(saved.status==='running'?'초안을 준비하고 있습니다':'초안 결과를 확인하지 못했습니다','이전 본문을 현재 초안으로 대신 표시하지 않습니다.',saved.status==='failed'?'danger':'attention');
  const delivery=job.completion?.kind==='delivery',canAct=!readOnly;
  readOnly=readOnly||Boolean(saved.decisions?.job)||saved.result_stale||saved.status==='review_required';
  const {esc,button}=workUI,result=saved.result || {},text=reviewDraft?.inputs?.text ?? saved.review_draft?.text ?? result.text ?? result.draft ?? result.summary ?? '',revision=saved.review_draft?.revision || 0;
  return `<div class="ew-dispatch-draft">${saved.result_stale||saved.status==='review_required'?workNoticeHTML('입력이나 선행 근거가 바뀌었습니다','이전 본문은 보존되어 있습니다. 새 근거로 다시 실행한 뒤 검토해 주세요.'):''}<div class="ew-draft-summary"><h4>초안 검토</h4>${workUI.icon('b22ad')}<small>${saved.decisions?.job?(delivery?'본문 검토 확정 · 송부 전':'사람 확정 기록 있음'):'AI 초안 · 사람 미확정'}${result.model?.name?' · '+esc(result.model.name):''}${saved.review_draft?` · ${esc(workUI.time(saved.review_draft.updated_at || saved.review_draft.created_at))} 저장`:''}</small></div>${saved.attempt_id?`<label class="ew-review-text"><span class="sr-only">검토 초안 본문</span><textarea id="ees-review-text" rows="9" data-review-revision="${revision}"${readOnly?' readonly':''}>${esc(text)}</textarea></label>`:`<p>${esc(text || '저장된 AI 제안이 없습니다.')}</p>`}${reviewDraft?.conflict?workNoticeHTML('다른 사람이 초안을 변경했습니다','작성 중인 본문은 보존했습니다. 최신 기록을 확인하고 다시 저장해 주세요.'):'<p class="ew-muted">수정한 본문은 검토 초안으로 저장됩니다. AI 원문과 당시 판정 근거는 실행 기록에 남습니다.</p>'}${saved.attempt_id&&canAct?`<div class="ew-draft-actions">${!readOnly?button('초안 저장','save_review_draft',`data-mutation class="ew-secondary"${reviewDraft?.conflict?' disabled data-own-disabled="true"':''}`):''}${delivery?button('검토하고 보내기','send_review_draft','disabled data-own-disabled="true" aria-describedby="ees-dispatch-block"'):''}</div>`:''}${delivery?'<p id="ees-dispatch-block" class="ew-notice" data-tone="attention">본문 검토와 송부 완료는 다릅니다. 송부 방식과 실제 송부 연결이 정해져야 보낼 수 있습니다.</p>':''}</div>`;
}
function workResultHTML(job,saved={}, {readOnly=false,listDraft=null,reviewDraft=null,actorId='',sourceCount}={}){
  const {esc,button,safeURL}=workUI,result=saved.result ?? saved.output ?? {},items=Array.isArray(result.items)?result.items:Array.isArray(result)?result:[],block=job.result_block || 'human_confirm';
  const verdicts=job.verdicts || [{id:'completed',label:'적합'},{id:'failed',label:'미흡'},{id:'unknown',label:'판단 불가'}];
  const decision=(item)=>{const d=saved.decisions?.[item.id];return `<select data-item-verdict data-item-id="${esc(item.id)}" aria-label="${esc(item.name || item.id)} 판정"${readOnly||d?' disabled':''}><option value="">판정 선택</option>${verdicts.map(v=>`<option value="${esc(v.meaning ?? v.id ?? v.value)}"${d?.verdict===(v.meaning ?? v.id ?? v.value)?' selected':''}>${esc(v.label ?? v.name ?? v.id)}</option>`).join('')}</select>`;};
  const source=value=>safeURL(value)?`<a href="${esc(safeURL(value))}" target="_blank" rel="noopener noreferrer">근거 열기</a>`:'';
  const empty='<p class="ew-empty">아직 저장된 결과가 없습니다.</p>';
  let body='';
  if(block==='schedule')body=`<div class="ew-result-schedule">${esc(result.notice || result.summary || '일정 확인이 필요합니다.')}${result.due_at?`<time datetime="${esc(result.due_at)}">${esc(result.due_at)}</time>`:''}${result.calendar_available===false?'<p>공휴일 달력 미연결 · 일정 확인 필요</p>':''}</div>`;
  else if(block==='list_confirm')body=workListHTML(saved,{readOnly,listDraft,sourceCount});
  else if(block==='checklist')body=items.length?`<ul class="ew-result-list">${items.map(item=>`<li>${workStatusHTML(item.status || 'unknown')}<span>${esc(item.name || item.title || item.id)}</span>${source(item.url)}</li>`).join('')}</ul>`:empty;
  else if(block==='item_verdict')body=items.length?`<div class="ew-result-items">${items.map(item=>`<article><header><strong>${esc(item.name || item.title || item.id)}</strong>${source(item.url)}</header>${item.evidence?.map(e=>`<p>${workStatusHTML(e.status || 'unknown',e.label || e.name)}${e.content_reviewed===false?'<small>내용 적정성 미검토</small>':''}</p>`).join('') || ''}${item.ai_suggestion&&!saved.decisions?.[item.id]?`<p class="ew-ai-proposal">AI 제안 · ${esc(item.ai_suggestion)} · 사람 미확정</p>`:''}${decision(item)}</article>`).join('')}</div>`:empty;
  else if(block==='ai_review')body=workReviewDraftHTML(job,saved,{readOnly,reviewDraft});
  else if(block==='change_request')body=workRequestHTML(saved.request || result.request || {},{...job,actor_id:actorId,can_request:saved.can_request ?? (!readOnly&&saved.can_execute!==false),can_review_request:saved.can_review_request ?? (!readOnly&&saved.can_execute!==false),can_reconcile:saved.can_reconcile ?? (!readOnly&&saved.can_execute!==false)});
  else if(block==='values')body=Object.keys(result).length?`<dl class="ew-facts">${Object.entries(result).filter(([key])=>!['secret','token','pat','credential'].includes(key.toLowerCase())).map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}</dd></div>`).join('')}</dl>`:empty;
  else body=`<p>${esc(job.completion?.description || job.completion_criteria || job.instructions || '결과와 근거를 확인한 뒤 직접 확인해 주세요.')}</p>${result.summary?`<p>${esc(result.summary)}</p>`:''}`;
  return `<section class="ew-result" data-result-block="${esc(block)}">${saved.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한으로 근거를 다시 확인해야 합니다. 이전 기록을 보존하고 현재 권한으로 다시 조회해 주세요.</p>':''}<h3>${esc({values:'확인한 값',schedule:'일정 안내',checklist:'점검 목록',list_confirm:'목록 확정',item_verdict:'항목별 판정',ai_review:'초안 검토',human_confirm:'사람 확인',change_request:'EES 실행 요청'}[block] || '결과')}</h3>${body}${job.result_block==='ai_review'&&saved.attempt_id?button('결과 초안 내보내기','export_result',`data-job-id="${esc(job.id)}" class="ew-text"`):''}${!readOnly&&items.length&&['list_confirm','item_verdict','checklist'].includes(block)?button('목록 수정 · 다시 검토','amend_items','class="ew-text"'):''}</section>`;
}
function workRequestHTML(request={},job={}){
  const {esc,safeURL}=workUI,steps=[['requested','요청 보냄','EES Work'],['accepted','접수','EES'],['running','실행 중','EES'],['reported_complete','완료 보고','EES'],['effect_verified','효과 확인','EES Work']],events=request.events || [];
  return `<div class="ew-request-track">${request.id?`<p>${workStatusHTML(request.state || request.status)} · 승인 ${esc(request.approvals?.length || 0)} / ${esc(request.approval_count || 0)}</p>${job.can_review_request!==false&&request.actor!==job.actor_id&&!(request.approvals || []).some(approval=>approval.actor===job.actor_id)&&request.state==='approval_pending'?workUI.button('요청 승인','approve_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}${job.can_reconcile!==false&&['requested','accepted','running','reported_complete','unknown'].includes(request.state)?workUI.button('상태 다시 확인','reconcile_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}`:''}${(request.external_job_id || request.job_number)?`<p>작업 번호 <strong>${esc((request.external_job_id || request.job_number))}</strong></p>`:''}${steps.map(([state,label,actor])=>{const event=events.find(e=>e.state===state || e.status===state || e.kind===state);return `<div>${workStatusHTML(event?state==='running'?'running':'completed':'waiting',label)}<span class="ew-actor" data-actor="${actor}">${actor}</span><small>${esc(event?workUI.time(event.at ?? event.created_at):'대기')}</small></div>`;}).join('')}${['unknown','partial'].includes(request.status || request.state)?workNoticeHTML('결과를 확인하지 못했습니다','중복 실행을 막기 위해 자동으로 다시 요청하지 않습니다. 같은 작업 번호의 상태만 다시 조회해 주세요.'):request.state==='failed'&&request.reported_complete&&!request.effect_verified?workNoticeHTML('EES는 완료했지만 효과가 확인되지 않았습니다','이 작업은 실패로 남습니다. 절차에 정한 다음 조치와 근거를 확인해 주세요.','danger'):request.reported_complete&&!request.effect_verified?workNoticeHTML('EES 완료 보고 후 효과 확인이 필요합니다','업무 완료로 처리하지 않았습니다.'):''}<p class="ew-muted">EES 완료 보고와 효과 확인이 모두 끝나야 업무를 완료합니다.</p>${(request.block_reason || request.reason)?`<p role="status">${esc(workReasonText(request.block_reason || request.reason))}</p>`:''}${safeURL(request.external_url)?`<a href="${esc(safeURL(request.external_url))}" target="_blank" rel="noopener noreferrer">EES에서 보기</a>`:''}${job.request_contract?.guide_url&&safeURL(job.request_contract.guide_url)?`<a href="${esc(safeURL(job.request_contract.guide_url))}" target="_blank" rel="noopener noreferrer">EES 가이드</a>`:''}</div>`;
}
function workHistoricalValuesHTML(attempt,currentSettings=null){
  const {esc}=workUI,inputs=attempt.inputs ?? attempt.snapshot?.inputs ?? {},fields=attempt.snapshot?.job?.inputs || [];
  if(attempt.evidence_access)return '<p>현재 원본 접근 권한 확인 필요</p>';
  if(!Object.keys(inputs).length)return '<p>기록된 입력 없음</p>';
  return `<dl class="ew-history-values">${Object.entries(inputs).map(([key,value])=>{const field=fields.find(item=>item.id===key),source=attempt.snapshot?.settings_sources?.[key],shared=['workflow','factory'].includes(source?.scope || field?.scope),changed=shared&&currentSettings&&(!Object.hasOwn(currentSettings,key)||JSON.stringify(value)!==JSON.stringify(currentSettings[key]));return `<div><dt>${esc(field?.name || key)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}${changed?'<span class="ew-changed-value">지금과 다름</span>':''}<small>${esc({run:'이번 실행 입력',workflow:'업무 설정',factory:'공장 설정'}[source?.scope || field?.scope || 'run'])}</small></dd></div>`;}).join('')}</dl>`;
}
function workCycleBarHTML(run,definition={}){
  if(!run)return '';const {esc,button,time}=workUI,stages=Object.values(definition.nodes || {}).filter(node=>node.type==='t'),done=stages.filter(stage=>Object.values(definition.nodes || {}).filter(node=>node.type==='j'&&workUI.lineage(node.id,definition).some(parent=>parent.id===stage.id)).every(node=>['completed','excluded'].includes(run.jobs?.[node.id]?.status))).length;
  const mode=run.mode || definition.execution_mode,label=mode==='periodic'?'이번 회차':mode==='emergency'?'진행 중인 대응':'진행 건';
  return `<div class="ew-cycle-bar"><span>${label}</span><strong>${esc(run.cycle?.name || run.name || definition.name || '진행 건')}</strong><small>${esc(time(run.created_at))} 개시${stages.length?` · ${done}/${stages.length}단계`:''}</small>${button(mode==='periodic'?'지난 회차':mode==='emergency'?'다른 대응':'다른 진행 건','workflow_records','class="ew-text"')}</div>`;
}
function workRunRecordsHTML(runs=[],workflowId='',workflowName=''){
  const {esc,button,finished,time}=workUI,rows=runs.filter(run=>!workflowId||run.workflow_id===workflowId).slice().sort((a,b)=>Number(finished(a))-Number(finished(b))||String(b.created_at).localeCompare(String(a.created_at)));
  return `${workflowId?`<div class="ew-record-filter"><strong>${esc(workflowName || '선택한 업무 절차')}</strong><button type="button" data-action="all_records" class="ew-text" aria-label="업무 절차 필터 해제">${workUI.icon('6d84b')}</button></div>`:''}${rows.map(run=>`<button type="button" class="ew-record" data-action="open_run" data-run-id="${esc(run.id)}" data-workflow-id="${esc(run.workflow_id)}"><strong>${esc(run.name || run.definition?.name || run.workflow_name || run.id)}</strong>${workStatusHTML(run.status)}<small>게시 v${esc(run.version || run.published_version)} · 완료 ${esc(run.progress?.completed || 0)}/${esc(run.progress?.total || 0)}${run.closed_at?' · '+esc(time(run.closed_at))+' 닫힘':' · '+esc(time(run.created_at))+' 개시'}</small></button>`).join('') || '<p class="ew-empty">저장된 진행 건이 없습니다.</p>'}`;
}
function workHistoryHTML(run,jobId='',currentSettings=null){
  const {esc}=workUI,attempts=(run?.attempts || []).filter(attempt=>!jobId||attempt.job_id===jobId);
  if(!attempts.length)return '<p class="ew-empty">저장된 실행 시도가 없습니다. 미수행을 성공으로 표시하지 않습니다.</p>';
  return attempts.slice().reverse().map(attempt=>`<details class="ew-history" data-key="history-${esc(attempt.id)}"><summary>${workStatusHTML(attempt.status,attempt.snapshot?.job?.mode==='human'?'사람 확인 기록':'')}<span>${esc(attempt.number || attempt.sequence || attempt.id)}차 · ${esc(workUI.time(attempt.created_at || attempt.started_at))}</span></summary>${attempt.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한을 다시 확인해야 합니다. 다른 사람의 비공개 근거를 표시하지 않습니다.</p>':''}<p>실행 당시 절차 v${esc(attempt.version || run.version)} · 결과 r${esc(attempt.result_revision ?? attempt.number ?? '미기록')}</p><section><h4>이 실행에 쓴 값</h4>${workHistoricalValuesHTML(attempt,currentSettings)}</section><dl class="ew-facts"><div><dt>도구 참조</dt><dd><pre>${esc(JSON.stringify(attempt.tool_reference ?? attempt.snapshot?.tool_reference ?? attempt.snapshot?.job?.tool_reference ?? attempt.snapshot?.job?.tool_contract_id ?? {},null,2))}</pre></dd></div><div><dt>결과</dt><dd><pre>${esc(JSON.stringify(attempt.result ?? {},null,2))}</pre></dd></div></dl>${(attempt.review_history || []).map(review=>`<section class="ew-review-history"><h4>${review.decision_id?'사람 확정 당시 본문':'저장한 검토 초안'} · r${esc(review.revision)}</h4><p>${esc(workUI.time(review.created_at))} · ${esc(review.actor_id)}</p><pre>${esc(review.text)}</pre></section>`).join('')}${(attempt.decisions || (run?.jobs?.[attempt.job_id]?.decision_history ? run.jobs[attempt.job_id].decision_history.filter(decision=>decision.attempt_id===attempt.id) : [])).map(d=>`<p>사람 판정 · ${esc(d.actor_id)} · ${esc(d.verdict)} · ${esc(d.created_at)}</p>`).join('')}<button type="button" data-action="ask_record" data-attempt-id="${esc(attempt.id)}" data-job-id="${esc(attempt.job_id)}" class="ew-text">${workUI.icon('1c98e')} 이 기록에 대해 묻기</button></details>`).join('');
}
function workMyWorkHTML(items=[],operations={}){
  const {esc,button,icon}=workUI,groups={incident:'진행 중 장애',overdue:'기한 지남',today:'오늘',week:'이번 주',future:'예정',undated:'기한 없음'};
  if(!items.length){const next=(operations.schedules || []).filter(item=>item.enabled&&Number.isFinite(item.next_at)).sort((a,b)=>a.next_at-b.next_at)[0];return `<div class="ew-empty ew-my-work-empty"><span class="ew-empty-symbol">${icon('52271')}</span><h3>지금 처리할 내 업무가 없습니다</h3>${next?`<p>${icon('63982')} 다음 자동 실행 · ${esc(workUI.time(next.next_at))} · ${esc(next.name || next.workflow_name || '게시 절차 예약')}</p>`:''}</div>`;}
  return Object.entries(groups).map(([key,title])=>{const list=items.filter(item=>(item.bucket || item.group || 'undated')===key);return list.length?`<section class="ew-todo-group"><h3>${key==='incident'?icon('f49d4'):key==='today'?icon('8fa06'):''}${title}<span>${list.length}</span></h3>${list.map(item=>`<button type="button" class="ew-todo" data-action="open_task" data-task-id="${esc(item.id)}" data-schedule-id="${esc(item.schedule_id || '')}" data-run-id="${esc(item.run_id)}" data-job-id="${esc(item.job_id)}" data-workflow-id="${esc(item.workflow_id)}"><span class="ew-todo-title">${workStatusHTML(item.status || 'awaiting_confirmation',item.name || item.title)}${icon('69549')}</span><small>${esc(item.workflow_name || '')}${item.factory_name?' · '+esc(item.factory_name):''}</small><small>${esc(workReasonText(item.reason))}${item.due_at?' · '+esc(item.due_at):''}</small>${(item.claimed_by || item.claim_actor)?`<small>담당 ${esc(item.claimed_by || item.claim_actor)}</small>`:''}</button>`).join('')}</section>`:'';}).join('');
}

function workExportText(document){
  const run=document.run;if(!run)return '';const lines=[run.definition?.name || run.workflow_name || 'EES Work 기록',`진행 건 ${run.id} · 게시 v${run.version} · ${run.status}`,`내보낸 시각 ${document.exported_at || ''}`];
  for(const attempt of run.attempts || []){lines.push('',`작업 ${run.definition?.nodes?.[attempt.job_id]?.name || attempt.job_id} · 시도 ${attempt.number} · ${attempt.status}`,`기록 시각 ${attempt.created_at || ''}`,'입력',JSON.stringify(attempt.inputs || {},null,2),'결과',JSON.stringify(attempt.result ?? {},null,2));for(const review of attempt.review_history || [])lines.push(`검토 본문 · 시도 ${attempt.id} · 검토 r${review.revision} · ${review.decision_id?'사람 확정':'초안'}`,review.text || '');if(attempt.evidence_access==='requires_current_source_access')lines.push('현재 원본 접근 권한 확인 필요 · 비공개 근거 제외');}
  for(const [id,job] of Object.entries(run.jobs || {}))for(const decision of job.decisions || [])lines.push(`사람 판정 · ${id} · ${decision.item_id} · 결과 r${decision.result_revision} · ${decision.verdict} · ${decision.actor_id} · ${decision.created_at}`);
  return lines.join('\n');
}
function workLegacyHTML(legacy){
  const {esc,button}=workUI;if(!legacy)return '';if(legacy.error)return `<p class="ew-warning">이전 기록 조회 실패 · ${esc(legacy.error)}</p>`;
  return `<section class="ew-legacy"><h3>이전 버전 기록</h3><p class="ew-muted">${esc(legacy.notice || '이전 실행 기능은 사용 중지되었습니다. 남아 있는 과거 기록만 읽습니다.')}</p>${(legacy.records || []).map(item=>button(`${item.process_name || item.id} · ${item.status || '상태 미기록'}${item.simulation?' · 시뮬레이션':''}`,'open_legacy',`data-case-id="${esc(item.id)}" class="ew-record"`)).join('') || '<p class="ew-empty">조회할 이전 기록이 없습니다.</p>'}</section>`;
}

function workHistoricalReferenceHTML(run,reference,workflow,currentSettings=null){
  const {esc}=workUI;
  if(!reference?.run_id&&workflow?.id===reference?.workflow_id){const version=workflow.versions?.find(item=>item.version===reference.version);return version?`<header class="ew-work-heading"><h2>대화에서 참조한 게시 절차</h2><p>게시 v${esc(version.version)} · 읽기 전용</p></header><pre>${esc(JSON.stringify(version.definition,null,2))}</pre>`:'<p class="ew-warning">이 메시지에는 보존된 게시 버전이 지정되지 않았습니다. 현재 편집 초안을 당시 내용으로 대신 표시하지 않습니다.</p>';}
  if(!run||reference?.run_id!==run.id)return '<p class="ew-warning">현재 권한으로 이 진행 건의 기록을 확인하지 못했습니다.</p>';
  if(!reference.attempt_id)return '<p class="ew-warning">이 메시지에는 당시 실행 시도 식별자가 기록되지 않았습니다. 현재 결과를 과거 근거로 대신 표시하지 않습니다.</p>';
  const attempt=(run.attempts || []).find(item=>item.id===reference.attempt_id&&item.job_id===reference.job_id);
  if(!attempt||reference.version!==undefined&&reference.version!==run.version||reference.result_revision!==undefined&&reference.result_revision!==attempt.number)return '<p class="ew-warning">참조한 버전·실행 시도를 현재 권한으로 확인하지 못했습니다. 다른 시도의 결과로 대신 표시하지 않습니다.</p>';
  return `<header class="ew-work-heading"><h2>대화에서 참조한 과거 기록</h2><p>게시 v${esc(run.version)} · 실행 시도 ${esc(attempt.number)} · 읽기 전용</p></header>${workHistoryHTML({...run,attempts:[attempt]},reference.job_id,currentSettings)}`;
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

function workRestorePanelPosition(host,position){
  if(!position)return;
  const expanded=new Set(position.expanded || []);
  for(const detail of host.querySelectorAll('details[data-key]'))detail.open=expanded.has(detail.dataset.key);
  const content=host.querySelector('#ees-work-content');if(content)content.scrollTop=position.scroll;
}

function createWorkView({callbacks}){
  const {$,esc,button,icon,categories,badge,finished}=workUI;
  let snapshot={state:null,selection:{}},entry=null,host=null,chatColumn=null,chatRow=null,header=null,lastKey='',pendingRender=false;
  const drafts=createWorkInputDrafts(),reviewDrafts=createWorkInputDrafts(),listDrafts=new Map(),positions=new Map(),modelChoices=new Map();let currentDraftKey='';
  const state=()=>snapshot.state || {},selection=()=>snapshot.selection || {};
  const definition=()=>state().run?.definition || state().workflow?.published?.definition || state().workflow?.published || state().workflow?.definition || state().workflow?.draft || {};
  const job=()=>definition().nodes?.[selection().job_id];
  const inputKey=()=>[state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id,selection().job_id,selection().tab].join('/');
  const modelKey=()=>[state().capabilities?.actor_id,selection().workflow_id,selection().run_id,selection().job_id].join('/');
  function executionModels(){const operations=state().operations || {},models=operations.models || [],key=modelKey();if(operations.error||models.length<=1||!models.some(model=>model.id===modelChoices.get(key)))modelChoices.delete(key);return workExecutionModelHTML(operations,modelChoices.get(key));}
  const resultKey=()=>[state().capabilities?.actor_id,state().run?.id,selection().job_id,state().run?.jobs?.[selection().job_id]?.attempt_id].join('/');
  function listDraft(){const key=resultKey(),saved=state().run?.jobs?.[selection().job_id] || {};if(!listDrafts.has(key))listDrafts.set(key,{items:workListItems(saved.result || {}),attempt_id:saved.attempt_id,revision:state().run?.revision,result_revision:saved.result_revision});return listDrafts.get(key);}
  function reviewDraft(){const saved=state().run?.jobs?.[selection().job_id] || {},source={text:saved.review_draft?.text ?? saved.result?.text ?? saved.result?.draft ?? saved.result?.summary ?? ''};return {...reviewDrafts.read(resultKey(),source,saved.review_draft?.revision || 0),key:resultKey(),attempt_id:saved.attempt_id,result_revision:saved.result_revision};}
  function captureResults(){
    const list=host?.querySelector('.ew-list-confirm');if(list){const draft=listDraft();for(const field of list.querySelectorAll('[data-list-include]')){const item=draft.items.find(item=>item.id===field.dataset.itemId);if(item&&!field.disabled)item.selected=field.checked;}}
    const text=host?.querySelector('#ees-review-text');if(text&&!text.readOnly){const previous=reviewDraft();if(text.value!==previous.inputs.text)reviewDrafts.edit(resultKey(),{text:text.value},previous.revision,previous.base || previous.inputs);}
  }
  function capture(){captureResults();const model=$('#ees-work-execution-model',host);if(model&&(state().operations?.models || []).length>1)modelChoices.set(modelKey(),model.value);const form=$('#ees-work-inputs',host);if(form&&currentDraftKey){try{const source=form.dataset.settings==='true'?state().settings?.values || {}:state().run?.inputs || {};const previous=drafts.read(currentDraftKey,source,Number(form.dataset.revision)),values={...previous.inputs};for(const field of form.querySelectorAll('[data-work-input]'))if(!field.disabled)delete values[field.name];Object.assign(values,workReadInputs(form));if(JSON.stringify(values)!==JSON.stringify(previous.inputs))drafts.edit(currentDraftKey,values,Number(form.dataset.revision),source);}catch(_){}}if(host)positions.set(lastKey,{scroll:$('#ees-work-content',host)?.scrollTop || 0,expanded:[...host.querySelectorAll('details[open]')].map(el=>el.dataset.key).filter(Boolean)});}
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
  function runOverview(){
    const data=state(),run=data.run,def=definition(),nodes=Object.values(def.nodes || {}),jobs=nodes.filter(node=>node.type==='j'),root=nodes.find(node=>node.type==='p'&&!node.parent),groups=nodes.filter(node=>node.type==='t');
    const automatic=scope=>jobs.filter(node=>['tool','ai'].includes(node.mode)&&node.result_block!=='change_request'&&run?.jobs?.[node.id]?.can_execute!==false&&workUI.lineage(node.id,def).some(parent=>parent.id===scope.id));
    const scopeButton=scope=>scope&&!finished(run)&&run?.can_write!==false&&automatic(scope).length?button(scope.type==='p'?'절차 실행':'단계 실행','execute_scope',`data-node-id="${esc(scope.id)}" data-mutation class="ew-secondary"`):'';
    const actor=node=>({human:['35b2e','사람'],tool:['a28e3','도구'],ai:['b22ad','AI 초안']}[node.mode || 'human']);
    const jobButton=node=>{const saved=run?.jobs?.[node.id] || {},person=actor(node);return `<button type="button" class="ew-phase-job" data-action="job" data-job-id="${esc(node.id)}">${workStatusHTML(saved.status || 'unstarted',node.name)}<span class="ew-job-actor" title="${person[1]}">${icon(person[0],person[1])}</span><small>${esc(workReasonText(saved.reason) || (saved.deadline?.at?'기한 '+workUI.time(saved.deadline.at):saved.deadline?.calendar_status==='unknown'?'일정 기준 확인 필요':'') || (saved.decision_summary?.confirmed?`${saved.decision_summary.confirmed}건 사람 확인`:''))}</small>${icon('69549')}</button>`;};
    const steps=groups.length?groups.map((stage,index)=>{const children=jobs.filter(node=>workUI.lineage(node.id,def).some(parent=>parent.id===stage.id)),states=children.map(node=>run?.jobs?.[node.id]?.status),stageStatus=children.length&&states.every(status=>['completed','excluded'].includes(status))?'completed':states.some(status=>!['unstarted','pending','excluded',undefined].includes(status))?'in_progress':'waiting';return `<section class="ew-phase-overview"><header class="ew-phase-heading"><span>${index+1}</span><h3>${esc(stage.name)}</h3>${run?.cycle?.stage_deadlines?.[stage.id]?`<small>${esc(run.cycle.stage_deadlines[stage.id].start)}${run.cycle.stage_deadlines[stage.id].end!==run.cycle.stage_deadlines[stage.id].start?' ~ '+esc(run.cycle.stage_deadlines[stage.id].end):''}</small>`:''}${workStatusHTML(stageStatus)}</header><div class="ew-run-steps">${children.map(jobButton).join('')}</div>${scopeButton(stage)}</section>`;}).join('')+(jobs.some(node=>node.parent===root?.id)?`<div class="ew-run-steps">${jobs.filter(node=>node.parent===root.id).map(jobButton).join('')}</div>`:''):`<div class="ew-run-steps">${jobs.map(jobButton).join('')}</div>`;
    const next=jobs.find(node=>['waiting_input','awaiting_input','waiting_confirmation','awaiting_confirmation','review_required','ready'].includes(run?.jobs?.[node.id]?.status));
    const scopes=(data.operations?.scope_runs || []).filter(item=>item.run_id===run?.id),scopeStatus=scopes.length?`<section class="ew-scope-status"><h3>절차·단계 실행</h3>${scopes.map(item=>`<p>${workStatusHTML(item.status)} · ${esc(def.nodes?.[item.node_id]?.name || item.node_id)}</p><small>${esc(workReasonText(item.reason))}${item.current_job_id?' · '+esc(def.nodes?.[item.current_job_id]?.name || item.current_job_id):''}</small>`).join('')}</section>`:'';
    const models=jobs.some(node=>node.mode==='ai')?executionModels():'';
    return `${workCycleBarHTML(run,def)}<header class="ew-work-heading"><h2>${esc(run?(run.cycle?.name || run.name || def.name || '진행 건'):'진행 건 시작')}</h2>${run?`<p>${badge(run.status)} · 게시 v${esc(run.version || run.published_version)}${finished(run)?' · 읽기 전용':''}</p><p>단계 ${groups.length} · 작업 ${jobs.length} · 완료 ${run.progress?.completed || 0} · 남은 작업 ${Math.max(0,(run.progress?.total || jobs.length)-(run.progress?.completed || 0))}</p>`:'<p>게시한 절차 버전으로 새 진행 건을 시작합니다.</p>'}</header>${!run?`<div class="ew-empty">${data.workflow?.published_version?button('진행 건 시작','start_run','class="ew-primary"'):'게시된 버전이 없습니다. 워크스페이스에서 검사하고 게시해 주세요.'}</div>`:`${(run.cycle?.warnings || []).map(warning=>workNoticeHTML('일정 확인 필요',warning.message || warning.code)).join('')}${run.cycle?.holidays_checked===false?'<p class="ew-muted">공휴일 달력 미연결 · 공휴일 여부는 확인하지 않았으며 날짜를 자동 이동하지 않았습니다.</p>':''}${steps}${finished(run)?`<section><h3>당시 실행 기록</h3>${workHistoryHTML(run,'',data.settings?.values)}<button type="button" data-action="ask_record" class="ew-text">${icon('1c98e')} 최근 기록에 대해 묻기</button></section>`:`<p class="ew-muted">작업을 누르면 이 패널에서 작업을 엽니다. 작업 이름 옆 아이콘은 사람 · 도구 · AI 초안을 구분합니다.</p>${models}${scopeStatus}${next?`<footer class="ew-next-action"><small>다음 할 일 · ${esc(next.name)}</small>${button(next.name+' 열기','job',`data-job-id="${esc(next.id)}" class="ew-primary"`)}</footer>`:''}${root?`<div class="ew-scope-execution">${scopeButton(root)}<small>저장한 입력으로 실행 가능한 도구·AI 작업을 진행합니다. 사람 확인과 EES 변경 요청은 자동 확정하지 않습니다.</small></div>`:''}`}<footer class="ew-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}${!finished(run)&&run.can_write!==false?button('진행 건 종료','close_run')+button('진행 건 취소','cancel_run'):''}</footer>`}`;
  }
  function jobPanel(){const data=state(),s=selection(),node=job(),run=data.run,saved=run?.jobs?.[node.id] || {},readonly=finished(run)||run?.can_write===false,fields=node.inputs || [],settings=s.tab==='settings',source=settings?data.settings?.values || {}:run?.inputs || {},revision=settings?data.settings?.revision || 0:run?.revision || 0;
    currentDraftKey=inputKey();const draft=drafts.read(currentDraftKey,source,revision),visibleFields=fields.filter(field=>(['workflow','factory'].includes(field.scope))===settings);
    const header=`${workCycleBarHTML(run,definition())}<button class="ew-text" type="button" data-action="overview">← 회차 개요</button><header class="ew-work-heading"><h2>${esc(node.name)}</h2>${workStatusHTML(saved.status || 'unstarted')}<p>${esc(node.instructions || '')}</p>${workAssignmentHTML(node,saved,data.people)}${saved.claim_actor===data.capabilities?.actor_id&&!readonly&&saved.status!=='running'?button('맡기 해제','release_task','class="ew-text"'):''}</header><nav class="ew-tabs" aria-label="작업 보기">${[['current','현재 상태'],['history','실행 기록'],['settings','업무 설정']].map(([tab,label])=>button(label,'tab',`data-tab="${tab}" aria-pressed="${s.tab===tab}"`)).join('')}</nav>`;
    if(s.tab==='history')return header+`<div class="ew-export-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}</div>`+workHistoryHTML(run,node.id,data.settings?.values)+`<button type="button" data-action="ask_record" data-job-id="${esc(node.id)}" class="ew-text">${icon('1c98e')} 최근 기록에 대해 묻기</button>`;
    const modelControls=node.mode==='ai'?executionModels():'';
    const inputs=visibleFields.length?`<section><h3>${settings?'업무 설정':'이번 진행 건 입력'} <small>${settings?'다음 실행에도 계속 사용':'이번 실행에 사용'}</small></h3>${!settings&&!readonly&&saved.can_execute!==false?button('AI 입력 초안','propose_inputs','class="ew-text"'):''}<form id="ees-work-inputs" data-settings="${settings}" data-revision="${draft.revision}">${visibleFields.map(field=>workInputHTML(field,draft.inputs[field.id],{disabled:readonly||(settings?saved.can_manage_settings===false:saved.can_execute===false),prefix:settings?'settings':'run',people:data.people || [],lookup:data.input_options?.[field.id]})).join('')}${draft.conflict?'<p class="ew-warning" role="alert">다른 사람이 값을 변경했습니다. 작성 중인 값은 보존했습니다. 최신 값과 비교해 다시 입력해 주세요.</p>'+button('최신 값으로 돌아가기','discard_inputs'):''}${!readonly&&(settings?saved.can_manage_settings!==false:saved.can_execute!==false)?button(settings?'설정 저장':'입력 저장','save_inputs',`data-mutation class="ew-secondary"${draft.conflict?' disabled':''}`):''}</form></section>`:'';
    const queryAttempt=workListSourceAttempt(run,saved.attempt_id),querySummary=node.result_block==='list_confirm'&&!settings&&queryAttempt&&!queryAttempt.evidence_access?`<section class="ew-query-summary"><header><h4>${icon('f1e53')} 조회 조건</h4><small>${esc(workUI.time(queryAttempt.created_at))} 조회</small>${button('업무 설정 보기','tab','data-tab="settings" class="ew-text"')}</header><p>${Object.entries(queryAttempt.inputs || {}).map(([key,value])=>`${esc(fields.find(field=>field.id===key)?.name || key)} · ${esc(typeof value==='object'?JSON.stringify(value):value)}`).join(' · ') || '이 실행에 선언된 조회 입력 없음'}</p></section>`:'';
    const proposal=data.input_proposal;const proposalHTML=!settings&&proposal?`<section class="ew-input-proposal ew-ai-proposal"><h3>AI 입력 초안 · 저장 전</h3><pre>${esc(JSON.stringify(proposal.values,null,2))}</pre>${(proposal.warnings || []).map(warning=>`<p>${esc(warning)}</p>`).join('')}<p>편집 중인 입력에 반영해도 저장·실행되지 않습니다.</p>${button('입력에 반영','apply_input_proposal','class="ew-secondary"')}${button('제안 닫기','discard_input_proposal','class="ew-text"')}</section>`:'';
    return header+inputs+proposalHTML+modelControls+querySummary+(settings?`<p class="ew-muted">개인 PAT와 비밀정보는 Native 개인 설정에서 관리합니다. 여기에 입력하지 마세요.</p>`:workResultHTML(node,saved,{readOnly:readonly||saved.can_decide===false,actorId:data.capabilities?.actor_id,sourceCount:Array.isArray(queryAttempt?.result?.items)?queryAttempt.result.items.filter(item=>item.source?.kind!=='human_added').length:null,listDraft:node.result_block==='list_confirm'?listDraft():null,reviewDraft:node.result_block==='ai_review'?reviewDraft():null})+`<footer class="ew-job-actions">${(saved.block_reason || saved.reason)?`<p class="ew-warning">${esc((saved.block_reason || saved.reason)==='delivery_unconfigured'?'본문 검토는 저장했습니다. 실제 송부와 결과 확인 전에는 이 작업을 완료하지 않습니다.':workReasonText(saved.block_reason || saved.reason))}</p>`:''}${readonly||saved.can_execute===false?`<p>${esc(finished(run)?'종료된 진행 건 · 당시 기록을 조회하고 있습니다.':({assignee_required:'보기 전용 · 배정된 담당자나 그룹이 처리할 수 있습니다.',task_claimed:'보기 전용 · 다른 담당자가 처리 중입니다.',scope_forbidden:'보기 전용 · 업무 참여 권한이 필요합니다.',run_closed:'종료된 진행 건 · 당시 기록을 조회하고 있습니다.'}[saved.permission_reason || run.permission_reason] || '보기 전용 · 현재 계정은 이 작업을 수행할 수 없습니다.'))}</p>`:node.result_block==='change_request'?(saved.can_request===false?'<p>보기 전용 · EES 요청 권한이 있는 담당자가 처리할 수 있습니다.</p>':button('요청 내용 확인…','request_intent','data-mutation class="ew-primary"')):node.mode==='human'?button('확인 완료','confirm','data-mutation class="ew-primary"'):button(saved.evidence_access==='requires_current_source_access'&&node.mode==='tool'?'현재 권한으로 다시 조회':['failed','unknown'].includes(saved.status)&&node.mode==='tool'?'다시 조회':saved.attempt_id?'다시 실행':'지금 실행','execute','data-mutation class="ew-primary"')+(saved.can_decide!==false&&!saved.decisions?.job&&node.human_confirmation!==false&&!['list_confirm','item_verdict','checklist'].includes(node.result_block)?button(node.completion?.kind==='delivery'?'본문 검토 확정':'판정 확정','confirm','data-mutation class="ew-secondary"'):'')}</footer>`);
  }
  function panel(){if(!host)return;const s=selection(),data=state(),key=[s.mode,s.tab,s.run_id,s.workflow_id,s.job_id].join('/');lastKey=key;host.dataset.eesMode=s.mode || 'work';host.hidden=s.panel_open===false;
    const title=s.mode==='author'?'워크스페이스':s.tab==='my_work'?'내 업무':s.tab==='records'?'실행 기록':'업무';
    const top=`<header class="ew-panel-header"><strong>${title}</strong><span>${esc(data.workflow?.name || '')}</span>${button('닫기','close_panel','aria-label="업무 패널 닫기" class="ew-icon-button"')}</header>`;
    if(s.mode==='author'&&s.tab!=='workspace_admin'){if(!$('#ees-work-authoring-panel',host))host.innerHTML=top+'<div id="ees-work-authoring-panel" class="ew-scroll"></div>';return;}
    let body='';currentDraftKey='';
    if(snapshot.error&&!snapshot.state)body=`<div class="ew-error" role="alert"><p>${esc(snapshot.error)}</p>${button('다시 조회','refresh')}</div>`;
    else if(!snapshot.state)body='<p role="status" class="ew-empty">업무 정보를 불러오는 중입니다.</p>';
    else if(s.tab==='historical_reference')body=workHistoricalReferenceHTML(data.run,s.historical_reference,data.workflow,data.settings?.values);
    else if(s.tab==='workspace_admin')body=workAdminHTML(data);
    else if(s.tab==='my_work')body=workMyWorkHTML(data.my_work || [],data.operations);
    else if(s.tab==='records')body=workRunRecordsHTML(data.runs || [],s.records_workflow || '',data.workflow?.name)+(s.records_workflow?'':workLegacyHTML(data.legacy));
    else if(!s.workflow_id)body='<div class="ew-empty"><h3>업무 절차를 선택해 주세요</h3><p>왼쪽에서 업무를 찾거나 워크스페이스에서 새 절차를 작성할 수 있습니다.</p></div>';
    else if(job()&&data.run)body=jobPanel();else body=runOverview();
    host.innerHTML=top+`<div id="ees-work-content" class="ew-scroll">${snapshot.error&&snapshot.state?`<div class="ew-error" role="alert">${esc(snapshot.error)}</div>`:''}${data.operations?.error?`<p class="ew-warning" role="alert">실행·예약 정보를 조회하지 못했습니다. ${esc(data.operations.error)}</p>`:''}${body}</div>`;
    workRestorePanelPosition(host,positions.get(key));setBusy(snapshot.busy);
  }
  function context(){if(!header)return;const node=job(),run=state().run,reference=selection().chat_reference;const html=`<span>${esc(node?.name || state().workflow?.name || '대화')}</span><div><small>참고</small><span class="ew-reference">${esc(reference?`과거 기록 · v${reference.version} · ${reference.result_revision}차 · ${workUI.time(reference.created_at)}`:node?.name || (run?'진행 건':'일반 대화'))}</span>${button('업무 열기','open_panel','aria-label="업무 패널 열기"')}${button('새 대화','new_chat')}</div>`;if(header.innerHTML!==html)header.innerHTML=html;}
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
  function refreshResults(){const focus=focusSnapshot();capture();panel();restoreFocus(focus);}
  function render(value){const focus=focusSnapshot();capture();snapshot=value;if(!ensure())return;navigator();panel();context();restoreFocus(focus);}
  function sync(value){snapshot=value;if(!ensure())return;if(!entry.firstChild)navigator();if(!host.firstChild)panel();context();}
  function readInputs(){capture();const settings=selection().tab==='settings';return {...drafts.read(inputKey(),settings?state().settings?.values || {}:state().run?.inputs || {},settings?state().settings?.revision || 0:state().run?.revision || 0),key:inputKey(),settings};}
  function applyInputValues(values){capture();const source=state().run?.inputs || {},revision=state().run?.revision || 0,existing=drafts.read(inputKey(),source,revision);drafts.edit(inputKey(),{...existing.inputs,...values},revision,source);panel();}
  function clearInputs(key,serial,revision,values){drafts.acknowledge(key,serial,revision,values);}
  function scopeDialog(){const data=state(),s=selection();return workUI.dialog({title:'작업 위치 선택',note:'공장과 시스템을 바꾸어도 대화와 작성 중인 글은 유지됩니다.',html:`<div class="ew-scope-columns${s.mode==='author'?' ew-system-only':''}"><section${s.mode==='author'?' hidden':''}><h3>공장</h3><input type="search" id="ees-factory-search" placeholder="공장 검색" aria-label="공장 검색"><div id="ees-factory-list"><button type="button" data-action="choose_factory" data-factory-id="" aria-pressed="${!s.factory_id}">${icon('40095')}<span>전체 공장<small>시스템 단위 업무를 볼 때</small></span></button>${(data.factories || []).map(f=>`<button type="button" data-action="choose_factory" data-factory-id="${esc(f.id)}" aria-pressed="${s.factory_id===f.id}"${f.allowed===false?' disabled':''}>${icon('40095')}<span>${esc(f.name)}<small>${esc([f.country,f.line].filter(Boolean).join(' · '))}</small></span></button>`).join('')}</div></section><section><h3>시스템</h3>${(data.systems || []).map(system=>typeof system==='string'?{id:system,name:system}:system).map(system=>`<button type="button" data-action="choose_system" data-system-id="${esc(system.id)}" aria-pressed="${s.system_id===system.id}"${system.allowed===false?' disabled':''}>${icon('f34f3')}<span>${esc(system.name || system.id)}<small>${system.allowed===false?'권한 없음':system.role==='owner'?'담당':'참여'}</small></span></button>`).join('')}</section></div>`});}
  function suspend(){workUI.closeDialog();capture();entry?.remove();host?.remove();header?.remove();chatColumn?.classList.remove('ees-integrated-chat');chatRow?.classList.remove('ees-integrated-row');chatColumn=null;chatRow=null;delete document.body.dataset.eesIntegrated;}
  function reset(){workUI.closeDialog();drafts.clear();reviewDrafts.clear();listDrafts.clear();positions.clear();modelChoices.clear();entry?.remove();host?.remove();header?.remove();chatColumn?.classList.remove('ees-integrated-chat');chatRow?.classList.remove('ees-integrated-row');entry=null;host=null;header=null;chatColumn=null;chatRow=null;snapshot={state:null,selection:{}};delete document.body.dataset.eesIntegrated;}
  return Object.freeze({render,sync,reset,suspend,setBusy,readList:()=>{capture();return workUI.clone(listDraft());},addListItem:item=>{capture();const draft=listDraft();if(draft.items.some(old=>old.id===item.id))throw new Error('이미 목록에 있는 항목입니다. 포함 여부를 확인해 주세요.');draft.items.push({...item,manual:true,selected:true});refreshResults();},readReview:()=>{capture();return reviewDraft();},clearReview:(key,serial,revision,text)=>reviewDrafts.acknowledge(key,serial,revision,{text}),refreshResults,readInputs,clearInputs,applyInputValues,discardInputs:()=>{drafts.discard(inputKey());panel();},scopeDialog,authoringHost:()=>$('#ees-work-authoring-panel',host),hasPendingInputs:()=>drafts.hasDirty([state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id].join('/')+'/'),capture,handleEvent:()=>({handled:false})});
}
