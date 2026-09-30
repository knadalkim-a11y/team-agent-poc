/* Pure rendering helpers shared by the native workflow view and designer. */
const workUI = (() => {
  const $ = (s, p = document) => p.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const categories = {setup:'셋업',ops:'운영',incident:'장애대응'};
  const levels = {p:'워크플로우',t:'단계',j:'작업'};
  const statuses = {unstarted:'시작 전',ready:'준비',pending:'대기',in_progress:'진행 중',running:'실행 중',success:'완료',completed:'완료',passed:'완료',failed:'실패',blocked:'진행 조건 확인',skipped:'적용 제외',draft:'초안',review:'검토 필요'};
  const badge = value => `<span class="ew-badge" data-status="${esc(value)}">${esc(statuses[value] || value || '대기')}</span>`;
  const button = (label, action, attrs = '') => `<button type="button" data-action="${action}" ${attrs}>${esc(label)}</button>`;
  const finished = c => ['passed','completed','success','skipped'].includes(c?.status);
  function siteLabel(site) {return [site?.country,site?.name || site?.factory].filter(Boolean).join(' · ');}
  const lineage = (id, data) => {const result = [], seen = new Set(); while (id && data?.nodes[id] && !seen.has(id)) {seen.add(id); result.unshift(data.nodes[id]); id = data.nodes[id].parent;} return result;};
  let activeDialog=null;
  function closeDialog() {activeDialog?.close();}
  function dialog({title,html,confirmLabel='',note='',readOnlyDetail=false,detailNavigation=false,restoreFocus=null}) {
    closeDialog();
    const previous=document.activeElement,element=document.createElement('dialog');
    element.id='ees-work-dialog';element.dataset.eesWork='';element.setAttribute('aria-labelledby','ees-work-dialog-title');
    if(readOnlyDetail)element.classList.add('ew-readonly-dialog');
    if(detailNavigation)element.classList.add('ew-execution-dialog');
    element.innerHTML=readOnlyDetail?`<header class="ew-dialog-header"><h2 id="ees-work-dialog-title">${esc(title)}</h2><button type="button" data-dialog-close aria-label="상세 닫기">닫기</button></header>${note?`<p class="ew-muted ew-dialog-note">${esc(note)}</p>`:''}<div class="ew-dialog-body">${html}</div>`:`<h2 id="ees-work-dialog-title">${esc(title)}</h2>${note?`<p class="ew-muted ew-dialog-note">${esc(note)}</p>`:''}<div class="ew-dialog-body">${html}</div><footer class="ew-actions">${confirmLabel?`<button type="button" class="ew-primary" data-dialog-confirm>${esc(confirmLabel)}</button>`:''}<button type="button" data-dialog-close>${confirmLabel?'취소':'닫기'}</button></footer>`;
    if(detailNavigation){element.querySelector('h2').classList.add('ew-visually-hidden');element.querySelector('.ew-dialog-header').insertAdjacentHTML('afterbegin',button('‹ 실행 이력','detail_tab','data-detail-tab="history" class="ew-detail-back"')+'<span class="ew-detail-record-kind">읽기 전용</span>');element.querySelector('.ew-dialog-note')?.classList.add('ew-visually-hidden');}
    document.body.append(element);activeDialog=element;
    return new Promise(resolve=>{
      let accepted=false;
      element.querySelector('[data-dialog-confirm]')?.addEventListener('click',()=>{accepted=true;element.close();});
      element.querySelector('[data-dialog-close]').addEventListener('click',()=>element.close());
      element.addEventListener('click',event=>{if(event.target===element){const r=element.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)element.close();}});
      element.addEventListener('close',()=>{element.remove();if(activeDialog===element){activeDialog=null;if(previous?.isConnected)previous.focus({preventScroll:true});else restoreFocus?.();}resolve(accepted);},{once:true});
      element.showModal();element.querySelector('[data-dialog-close]').focus();
    });
  }
  function treeHTML(data, ids, options = {}, depth = 0) {
    const {editing = false, selectedId = '', collapsed = new Set(), expanded = new Map(), statuses: nodeStatuses = {}, summaries = {}, expansionKey = '', run = null} = options;
    return (ids || []).map(id=>{
      const n=data.nodes[id];if(!n||depth>3)return '';
      const children=n.children || [],open=editing?!collapsed.has(id):Boolean(expanded.get(id)),active=selectedId===id;
      const ns=nodeStatuses[id],itemStatus=ns?.status || 'unstarted';
      const count=ns?.progress,attention=ns?.attention_count ?? ns?.failed_count ?? 0,excluded=ns?.excluded_count || 0;
      const summary=summaries[id] || (ns?`${count?.done || 0}/${count?.total || 0} 작업 완료${excluded?' · 제외 '+excluded:''}`:'시작 전');
      const limited=children.length>25&&children.every(child=>data.nodes[child]?.type==='j');
      const visibleChildren=limited?children.slice(0,25):children;
      if(limited&&children.includes(selectedId)&&!visibleChildren.includes(selectedId))visibleChildren.push(selectedId);
      const more=limited?'<div class="ew-tree-row" style="--depth:'+(depth+1)+'"><span class="ew-expand"></span>'+button('전체 '+children.length+'개 작업 찾기',editing?'edit_node':'select','data-node-id="'+esc(id)+'" data-process-id="'+esc(lineage(id,data)[0]?.id || id)+'"')+'</div>':'';
      return `<div class="ew-tree-row" style="--depth:${depth}">${children.length?button(open?'⌄':'›','expand',`data-node-id="${esc(id)}" data-expansion-key="${esc(expansionKey)}" data-case-id="${esc(run?.id || '')}" class="ew-expand" aria-label="${esc(n.name)} ${open?'접기':'펼치기'}" aria-expanded="${open}"`):'<span class="ew-expand" aria-hidden="true"></span>'}<button type="button" data-action="${editing?'edit_node':'select'}" data-node-id="${esc(id)}" data-process-id="${esc(lineage(id,data)[0]?.id || id)}" aria-current="${active?'step':'false'}"><span class="ew-tree-label">${esc(n.name)}${!editing&&children.length?`<small class="ew-tree-meta">${ns?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${attention?'조치 필요 '+attention:esc(statuses[itemStatus])}</span> · `:''}${esc(summary)}</small>${n.type==='p'&&run?`<small class="ew-tree-meta">${esc(run.created_at?.slice(0,10) || '기존 실행')} · v${esc(run.version)}</small>`:''}`:''}</span>${!editing&&!children.length?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${esc(statuses[itemStatus])}</span>`:''}</button></div>${children.length&&open?treeHTML(data,visibleChildren,options,depth+1)+more:''}`;
    }).join('');
  }
  return Object.freeze({$, esc, clone, categories, levels, statuses, badge, button, finished, siteLabel, lineage, treeHTML,dialog,closeDialog});
})();

/* Runtime navigation is a step list; the editable Workspace tree stays separate. */
function workNavigationLeaves(data,n) {return n.type==='j'?[n]:(n.children || []).flatMap(id=>data.nodes[id]?workNavigationLeaves(data,data.nodes[id]):[]);}
function workNavigationApplies(data,n,site,system) {
  return workUI.lineage(n.id,data).every(parent=>{
    const condition=parent.condition || 'all';
    if(parent.enabled===false||(system&&parent.systems&&!parent.systems.includes(system)))return false;
    if(!site)return true;
    if(condition==='interface')return Boolean(site.interface);
    if(condition==='reuse')return Boolean(site.reuse);
    if(condition==='new-infra')return !site.reuse;
    for(const [prefix,key] of [['country:','country'],['factory:','id'],['line:','line']])if(condition.startsWith(prefix))return condition.slice(prefix.length)===site[key];
    return true;
  });
}
function workNavigationState(data,n,run,{site=run?.site,system=run?.system}={}) {
  let saved=run?.node_states?.[n.id];
  if(!run){
    const eligible=workNavigationLeaves(data,n).filter(item=>workNavigationApplies(data,item,site,system));
    saved={status:eligible.length?'unstarted':'skipped',applicable:workNavigationApplies(data,n,site,system)};
    if(n.type==='j'&&eligible.length){
      const tools=(n.tools || []).map(id=>data.tools?.[id]),values={db:site?.db || '',ap:site?.ap || '',site:[site?.country,site?.name,site?.line].filter(Boolean).join(' · '),interface:site?.interface?(system || '')+' · '+site.name:''};
      const path=workUI.lineage(n.id,data),deps=[...new Set(path.flatMap(parent=>parent.deps || []))];
      const missing=deps.filter(id=>data.nodes[id]&&workNavigationLeaves(data,data.nodes[id]).some(item=>workNavigationApplies(data,item,site,system)));
      const skills=path.flatMap(parent=>(parent.skills || []).map(id=>data.skills?.[id])).filter(Boolean);
      if(skills.some(skill=>skill.source==='open_webui'&&Array.isArray(data.available_skills)&&!data.available_skills.some(item=>item.id===skill.reference)))saved.block_reason='skill_unavailable';
      else if(n.execution)saved.block_reason=missing.length?'prerequisite_required':'execution_plan_required';
      else if(n.mode==='tool'&&(!tools.length||tools.some(tool=>!tool||tool.adapter!=='mock'||tool.source==='open_webui'||tool.enabled===false)))saved.block_reason='connection_required';
      else if(n.mode==='tool'&&tools.some(tool=>!String(values[n.bindings?.[tool.id] || tool.input] ?? '').trim()))saved.block_reason='input_required';
      else if(missing.length)saved.block_reason='prerequisite_required';
      saved.missing=missing;saved.ready_for_run=n.mode==='tool'&&!saved.block_reason;
      saved.attention=Boolean(saved.block_reason&&saved.block_reason!=='prerequisite_required');
    }
  }
  const labels={passed:'완료',skipped:'적용 제외',running:'진행 중',failed:'실패',input_required:'입력 필요',ready:'점검 가능',waiting:'선행 대기',review:'검토 대기',confirmation:'확인 대기',connection_required:'실행 연결 필요',skill_unavailable:'권한 확인',execution_plan_required:'계획 확인',pending:'대기',unstarted:'시작 전',blocked:'진행 조건 확인',in_progress:'진행 중'};
  let key=saved?.status || 'unstarted';
  if(saved?.applicable===false)key='skipped';
  if(n.type!=='j'&&saved?.missing?.length&&!saved.attention_count&&['unstarted','pending','blocked'].includes(key))key='waiting';
  // Here run is the saved workflow case, whose status is a child aggregate,
  // not the Native execution run. Only completed or failed attempts establish
  // parent progress; attention alone must keep an unstarted parent blocked.
  if(n.type!=='j'&&run&&['failed','blocked'].includes(key)&&(saved?.progress?.done>0||saved?.failed_count>0))key='in_progress';
  if(n.type==='j'&&!['passed','skipped','failed','running'].includes(key)){
    const reason=saved?.block_reason;
    if(['input_required','connection_required','skill_unavailable','execution_plan_required'].includes(reason))key=reason;
    else if(saved?.missing?.length||reason==='prerequisite_required')key='waiting';
    else if(saved?.ready_for_run)key='ready';
    else if(run&&n.mode==='manual')key='confirmation';
    else if(run&&n.mode==='draft')key='review';
  }
  return {key,label:labels[key] || workUI.statuses[key] || '확인 필요',attention:Boolean(saved?.attention),ready:Boolean(saved?.ready_for_run)};
}

function createWorkStepSummaries() {
  const saved=new Map();
  function choose(key,jobs,selectedId,nodeStates={}) {
    const ids=jobs.map(job=>job.id),selected=ids.includes(selectedId)?selectedId:'',limit=4;
    let chosen=(saved.get(key) || []).filter(id=>ids.includes(id));
    if(!saved.has(key)){
      const current=jobs.find(job=>job.id===selected) || jobs[0];
      const completedPrerequisites=(current?.deps || []).filter(id=>ids.includes(id)&&nodeStates[id]?.status==='passed');
      chosen=[...new Set([...completedPrerequisites,current?.id,...ids].filter(Boolean))].slice(0,limit);
    }else if(selected&&!chosen.includes(selected)){
      if(chosen.length>=limit)chosen.pop();
      chosen.push(selected);
    }
    // A refresh updates state labels, not list order/membership. In particular,
    // a completed selected result must remain visible until another selection.
    saved.set(key,chosen);
    return chosen;
  }
  return Object.freeze({choose,clear:()=>saved.clear()});
}

function workStepProgressHTML(data,process,{run=null,selectedId='',selectedTaskId='',summaryIds=[],site=run?.site,system=run?.system}={}) {
  const {esc,button}=workUI,nodes=data.nodes,tasks=(process.children || []).map(id=>nodes[id]).filter(Boolean);
  const stateHTML=n=>{const state=workNavigationState(data,n,run,{site,system});return '<span class="ew-work-state" data-status="'+esc(state.key)+'">'+esc(state.label)+'</span>';};
  const count=n=>{const saved=run?.node_states?.[n.id],children=workNavigationLeaves(data,n),total=children.filter(item=>workNavigationApplies(data,item,site,system)).length;return saved?.progress?`${saved.progress.done} / ${saved.progress.total} 작업 완료`:`0 / ${total} 작업 완료${children.length>total?' · 제외 '+(children.length-total):''}`;};
  return '<div id="ees-work-tree" class="ew-step-progress"><ol class="ew-steps">'+tasks.map((task,index)=>{
    const expanded=task.id===selectedTaskId,jobs=(task.children || []).map(id=>nodes[id]).filter(n=>n?.type==='j');
    const visible=expanded?summaryIds.map(id=>jobs.find(job=>job.id===id)).filter(Boolean):[];
    const items=visible.length?'<ul class="ew-step-jobs" aria-label="'+esc(task.name)+' 작업">'+visible.map(job=>'<li><button type="button" class="ew-step-job" data-action="select" data-node-id="'+esc(job.id)+'" data-process-id="'+esc(process.id)+'" aria-current="'+(selectedId===job.id?'step':'false')+'"><span class="ew-step-job-name">'+esc(job.name)+'</span>'+stateHTML(job)+'</button></li>').join('')+'</ul>':'';
    return '<li class="ew-step" data-step-id="'+esc(task.id)+'" data-expanded="'+expanded+'"><button type="button" class="ew-step-button" data-action="select" data-node-id="'+esc(task.id)+'" data-process-id="'+esc(process.id)+'" aria-current="'+(selectedId===task.id?'step':'false')+'"><span class="ew-step-number" aria-hidden="true">'+(index+1)+'</span><span class="ew-step-label"><strong>'+esc(task.name)+'</strong><span class="ew-step-meta">'+esc(count(task))+'</span></span>'+stateHTML(task)+'</button>'+items+(expanded&&jobs.length>visible.length?'<div class="ew-step-all">'+button('전체 '+jobs.length+'개 작업 보기','select','data-node-id="'+esc(task.id)+'" data-process-id="'+esc(process.id)+'"')+'</div>':'')+'</li>';
  }).join('')+'</ol></div>';
}

/* V4 presentation derives ordering and progress from the saved procedure only.
 * Procedure order is a display number; it never creates a dependency or authority. */
function workV4Facts(c,definition,execution=null,{site=c?.site,system=c?.system}={}) {
  const nodes=definition?.nodes || {},ordered=Object.values(nodes).filter(item=>item.type==='p').flatMap(item=>workNavigationLeaves(definition,item)),all=[...ordered,...Object.values(nodes).filter(item=>item.type==='j'&&!ordered.some(leaf=>leaf.id===item.id))];
  const path=item=>workUI.lineage(item.id,definition),deps=item=>[...new Set(path(item).flatMap(parent=>parent.deps || []))];
  const recorded=item=>{const history=c?.jobs?.[item.id]?.history || [];return history[history.length-1];};
  const applies=item=>c?c.node_states?.[item.id]?.applicable!==false&&c.node_states?.[item.id]?.status!=='skipped':workNavigationApplies(definition,item,site,system);
  const state=item=>{
    const run=workExecutionForNode(execution,item.id,definition)?.run,job=item.execution?run?.jobs?.[item.id]:null;
    const ordinary=workNavigationState(definition,item,c,{site,system});
    let key=job?.status || ordinary.key,label=job?workExecutionStatus(key):ordinary.label;
    if(!applies(item))return {key:'skipped',label:'적용 제외',group:'excluded',glyph:'waiting',complete:false};
    if(job&&(job.status==='unknown'||job.validation?.status==='unknown'||run?.calls?.some(call=>call.job_id===item.id&&call.status==='unknown'))){key='unknown';label='판정 미확인';}
    const prior=recorded(item),simulation=!item.execution&&key==='passed'&&(prior?.kind==='simulation'||prior?.simulation||item.mode==='tool');
    const complete=item.execution?job?.validation?.status==='succeeded'&&job?.status==='succeeded':key==='passed'&&!simulation;
    if(simulation)return {key:'simulation',label:'모의 통과 · 실제 미확인',group:'simulation',glyph:'waiting',complete:false};
    if(complete)return {key,label:'완료',group:'done',glyph:'done',complete:true};
    if(['queued','running'].includes(key))return {key,label:'실행 중',group:'running',glyph:'running',complete:false};
    if(['waiting','waiting_dependency'].includes(key))return {key,label:'선행 대기',group:'waiting',glyph:'waiting',complete:false};
    if(key==='unknown')label='판정 미확인';
    else if(key==='ready')label='실행 가능';
    else if(key==='waiting_input'&&job?.reason==='human_confirmation_required')label='확인 필요';
    else if(key==='succeeded')label='완료 판정 확인 필요';
    return {key,label,group:'todo',glyph:key==='failed'?'failed':key==='unknown'?'unknown':'action',complete:false};
  };
  const dependsOn=(item,target)=>deps(item).some(id=>id===target.id||(nodes[id]&&workNavigationLeaves(definition,nodes[id]).some(leaf=>leaf.id===target.id)));
  const following=item=>all.filter(other=>other.id!==item.id&&path(other)[0]?.id===path(item)[0]?.id&&applies(other)&&!state(other).complete&&dependsOn(other,item));
  const order=item=>{const line=path(item),task=line.find(parent=>parent.type==='t'),process=line[0],stage=task?(process.children || []).indexOf(task.id)+1:0,index=((task || process).children || []).indexOf(item.id)+1;return item.type==='j'?(stage?stage+'.':'')+String(Math.max(1,index)).padStart(2,'0'):String((process.children || []).indexOf(item.id)+1);};
  const index=item=>all.findIndex(other=>other.id===item.id);
  const unmet=item=>deps(item).filter(id=>nodes[id]&&workNavigationLeaves(definition,nodes[id]).some(leaf=>applies(leaf)&&!['passed','succeeded'].includes(c?.node_states?.[leaf.id]?.status || state(leaf).key)));
  const recommended=(items=all)=>items.filter(item=>applies(item)&&state(item).group==='todo'&&!unmet(item).length&&state(item).key!=='unknown').sort((a,b)=>following(b).length-following(a).length||index(a)-index(b))[0]?.id || '';
  const assigned=item=>{const value=item.assignee || item.owner || '';return typeof value==='string'?value:value?.name || value?.display_name || '';};
  const lastAt=item=>{const run=workExecutionForNode(execution,item.id,definition)?.run;return item.execution?(run?.jobs?.[item.id]?.completed_at || run?.updated_at || run?.created_at || ''):(recorded(item)?.at || recorded(item)?.completed_at || '');};
  return {all,path,deps,recorded,applies,state,following,order,index,unmet,recommended,assigned,lastAt};
}
function workV4StatusHTML(state,{label=true}={}) {return '<span class="ew-v4-status" data-status="'+workUI.esc(state.key)+'">'+workV4Icon(state.glyph.slice(0,1).toUpperCase()+state.glyph.slice(1))+(label?'<span>'+workUI.esc(state.label)+'</span>':'<span class="ew-visually-hidden">'+workUI.esc(state.label)+'</span>')+'</span>';}
function workV4AIReceiptHTML(draft) {
  const receipt=draft?.aiReceipt;if(!receipt||receipt.undone)return '';
  return '<div class="ew-v4-ai-note" data-ai-proposal="'+workUI.esc(receipt.proposalId)+'"><span class="ew-v4-ai-label">AI</span><span>EES Assistant가 입력함 · 근거: '+workUI.esc(receipt.source || '출처 미기록')+'</span>'+workUI.button('되돌리기','undo_ai_draft','data-proposal-id="'+workUI.esc(receipt.proposalId)+'"')+'</div>';
}
function workV4DetailHTML(c,n,{definition,execution=null,site,system,draft=null,header='',content='',mode='',history=false}={}) {
  const {esc,button}=workUI,facts=workV4Facts(c,definition,execution,{site,system}),savedState=facts.state(n),path=facts.path(n),parent=path[path.length-2],sameStage=facts.all.filter(item=>item.parent===n.parent),recommended=facts.recommended(sameStage)===n.id;
  const required=n.execution?(path[0]?.execution_inputs?.required || []):[...new Set((n.tools || []).map(id=>n.bindings?.[id] || definition.tools?.[id]?.input).filter(Boolean))],draftValues={...(n.execution?c?.execution_inputs:c?.jobs?.[n.id]?.inputs),...(draft?.inputs || {})};
  const needsInput=required.some(key=>!Object.hasOwn(draftValues,key)||draftValues[key]==='');
  const state=draft?.inputsChanged&&savedState.group==='todo'&&savedState.key!=='unknown'?{...savedState,key:needsInput?'input_required':'draft',label:needsInput?'입력 필요':'저장 필요'}:savedState;
  const records=c?.jobs?.[n.id]?.history || [],run=workExecutionForNode(execution,n.id,definition)?.run,hasRecord=Boolean(records.length||run);
  const row=(label,value)=>'<div class="ew-v4-info-row"><dt>'+label+'</dt><dd>'+value+'</dd></div>';
  const link=item=>history?'<span>'+esc(item.name)+'</span>':button(item.name,'select','data-node-id="'+esc(item.id)+'" class="ew-work-link"');
  const toolIds=[...new Set(n.tools || [])],skillIds=[...new Set(['common',...path.flatMap(item=>item.skills || [])])].filter(id=>definition.skills?.[id]),calls=n.execution?.calls || [],refs=n.execution?.skill_refs || [];
  const technical='<details class="ew-v4-technical"><summary>기술 정보 <span>도구 '+(n.execution?calls.length:toolIds.length)+' · 스킬 '+(n.execution?refs.length:skillIds.length)+'</span></summary>'+toolIds.map(id=>'<p>'+esc(definition.tools?.[id]?.name || id)+'</p>').join('')+calls.map(call=>'<p>'+esc(call.reference?.function || call.function || call.id || '등록된 기능')+'</p>').join('')+skillIds.map(id=>'<p>'+esc(definition.skills?.[id]?.name || id)+'</p>').join('')+refs.map(ref=>'<p>'+esc(ref.name || ref.id || ref.reference || '등록된 스킬')+'</p>').join('')+(!history&&!n.execution?button('사용 구성 보기','work_detail','data-node-id="'+esc(n.id)+'" data-detail-tab="config"'):'')+'</details>';
  const successor=facts.following(n),prerequisites=facts.deps(n).map(id=>definition.nodes[id]).filter(Boolean),version=c?.version ?? definition.version,published=definition.published_at;
  const info='<aside class="ew-v4-info" aria-label="작업 정보"><h3>정보</h3><dl>'+row('상태',workV4StatusHTML(state))+row('순서','<span class="ew-v4-order">'+esc(facts.order(n))+'</span> · '+esc(parent?.execution_mode==='parallel'||parent?.parallel===true?'병렬 허용':parent?.execution_mode==='serial'||parent?.parallel===false?'순차 진행':'관계는 선행 조건 기준'))+row('담당',esc(facts.assigned(n)||'미지정'))+row('수행 방식',esc(mode))+row('선행 작업',prerequisites.length?prerequisites.map(item=>'<div>'+link(item)+'</div>').join(''):'없음')+row('후속 작업',successor.length?'<p>'+successor.length+'개가 이 작업을 기다리는 중</p>'+successor.map(item=>'<div>'+link(item)+'</div>').join(''):'없음')+row('절차',esc(version!==undefined?'v'+version:'버전 미기록')+(published?' · '+esc(String(published).slice(0,10))+' 게시':''))+row('작업 공간',esc([site?.name || site?.country,system].filter(Boolean).join(' · ') || '미기록'))+'</dl>'+technical+'</aside>';
  const step=state.group==='running'?2:hasRecord?3:1;
  const heading='<div class="ew-v4-detail-heading ew-work-identity"><div class="ew-heading ew-work-heading"><h2 class="ew-title">'+esc(n.name)+'</h2>'+workV4StatusHTML(state)+(recommended?'<span class="ew-v4-first">먼저 처리 권장</span>':'')+'</div><p class="ew-v4-job-meta"><span class="ew-v4-id">'+esc(n.id)+'</span><span>'+esc(mode)+'</span><span>'+ (hasRecord?'실행 기록 있음':'실행 기록 없음')+'</span></p></div>';
  const steps='<ol class="ew-v4-steps" aria-label="업무 진행 단계">'+['입력',n.execution?.kind==='human'||n.mode==='manual'?'확인':n.mode==='draft'?'검토':'점검','판정'].map((label,index)=>'<li'+(step===index+1?' aria-current="step"':'')+'><span>'+(index+1)+'</span>'+label+'</li>').join('')+'</ol>';
  const back=parent&&!history?'<nav class="ew-v4-back">'+button('작업 목록','panel_parent','data-node-id="'+esc(parent.id)+'" class="ew-work-link"')+'</nav>':'';
  return header+'<div class="ew-v4-detail"><div class="ew-v4-detail-main">'+back+heading+steps+'<div class="ew-v4-detail-content">'+content+'</div></div>'+info+'</div>';
}
function workV4ListHTML(c,n,{definition,execution=null,site,system,listView={},modeLabel,reasonFor,conditionsFor,previewActions='',controls=''}={}) {
  const {esc,button}=workUI,facts=workV4Facts(c,definition,execution,{site,system}),all=workNavigationLeaves(definition,n),path=facts.path(n),parent=path[0],stage=(parent.children || []).indexOf(n.id)+1;
  const query=String(listView.query || ''),needle=query.trim().toLocaleLowerCase(),filter=listView.filter || 'all',assignee=listView.assignee || 'all',sort=['recommended','procedure','recent'].includes(listView.sort)?listView.sort:'recommended';
  const matches={all:()=>true,attention:item=>['failed','unknown','input_required','waiting_input','waiting_authorization','connection_required','skill_unavailable'].includes(facts.state(item).key),incomplete:item=>facts.applies(item)&&!facts.state(item).complete,completed:item=>facts.state(item).complete,excluded:item=>!facts.applies(item)};
  const matching=all.filter(item=>(matches[filter] || matches.all)(item)&&(!needle||(item.name || '').toLocaleLowerCase().includes(needle))&&(assignee==='all'||(assignee==='unassigned'?!facts.assigned(item):facts.assigned(item)===assignee)));
  const sortItems=items=>[...items].sort((a,b)=>sort==='recent'?String(facts.lastAt(b)).localeCompare(String(facts.lastAt(a)))||facts.index(a)-facts.index(b):sort==='recommended'?(facts.unmet(a).length?1:0)-(facts.unmet(b).length?1:0)||facts.following(b).length-facts.following(a).length||facts.index(a)-facts.index(b):facts.index(a)-facts.index(b));
  // Recommendation is scoped to the currently visible assignee/search result;
  // this provisional product choice is disclosed in the toolbar, not an approval.
  const recommended=facts.recommended(matching),done=all.filter(item=>facts.state(item).complete).length,eligible=all.filter(facts.applies),simulated=all.filter(item=>facts.state(item).group==='simulation').length;
  const assigned=[...new Set(all.map(facts.assigned).filter(Boolean))],version=c?.version ?? definition.version;
  const heading='<header class="ew-v4-list-heading"><p class="ew-v4-stage-label">'+(n.type==='t'?'단계 '+stage+' / '+(parent.children || []).length:'워크플로우')+'</p><div class="ew-v4-list-title"><h2 class="ew-title">'+esc(n.name)+'</h2><div class="ew-v4-progress"><progress aria-label="실제 작업 완료 수" value="'+done+'" max="'+Math.max(1,eligible.length)+'"></progress><span>'+done+' / '+eligible.length+' 완료</span></div></div><p class="ew-v4-list-meta">'+esc(n.description || '등록된 작업을 확인하고 수행합니다.')+'<span>일정 미등록</span><span>담당 '+(assigned.length?assigned.length+'명':'미지정')+'</span><span>절차 '+esc(version!==undefined?'v'+version:'버전 미기록')+'</span>'+(simulated?'<span>모의 통과 '+simulated+'건 · 실제 미확인</span>':'')+'</p></header>';
  const filterOptions=[['all','전체'],['attention','조치 필요'],['incomplete','미완료'],['completed','완료'],['excluded','적용 제외']];
  const toolbar='<div class="ew-v4-toolbar"><label class="ew-work-search">'+workV4Icon('search')+'<span class="ew-visually-hidden">작업 이름으로 검색</span><input id="ees-work-job-search" type="search" value="'+esc(query)+'" placeholder="작업 이름으로 검색" autocomplete="off"></label><label class="ew-v4-select">담당 <select id="ees-v4-assignee-filter" aria-label="담당 필터"><option value="all">전체</option><option value="unassigned"'+(assignee==='unassigned'?' selected':'')+'>미지정</option>'+assigned.map(name=>'<option value="'+esc(name)+'"'+(assignee===name?' selected':'')+'>'+esc(name)+'</option>').join('')+'</select></label><label class="ew-v4-select">정렬 <select id="ees-v4-sort" aria-label="작업 정렬">'+[['recommended','권장 순서'],['procedure','절차 순서'],['recent','최근 실행']].map(([key,label])=>'<option value="'+key+'"'+(sort===key?' selected':'')+'>'+label+'</option>').join('')+'</select></label><details class="ew-v4-filter-menu"><summary>상태</summary><div class="ew-work-filters">'+filterOptions.map(([key,label])=>button(label+' '+all.filter(matches[key]).length,'job_filter','data-filter="'+key+'" aria-pressed="'+(filter===key)+'"')).join('')+'</div></details><span class="ew-v4-list-count">'+matching.length+'개 작업</span></div>';
  const displayTime=value=>{if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?'시각 미기록':String(date.getMonth()+1).padStart(2,'0')+'.'+String(date.getDate()).padStart(2,'0')+' '+String(date.getHours()).padStart(2,'0')+':'+String(date.getMinutes()).padStart(2,'0');};
  const jobRow=item=>{
    const state=facts.state(item),following=facts.following(item),assigned=facts.assigned(item),at=facts.lastAt(item),condition=conditionsFor?.(item) || '',open=Boolean(listView.expanded?.includes(item.id)&&condition),conditionId='ees-work-condition-'+item.id;
    const action=state.key==='unknown'?'상태 조회':state.key==='failed'?'결과 보기':['confirmation','review'].includes(state.key)||item.execution?.kind==='human'||['manual','draft'].includes(item.mode)?'확인':['input_required','waiting_input'].includes(state.key)?'입력':'보기';
    const reason=state.group==='waiting'?'선행 작업 대기 · '+facts.unmet(item).map(id=>definition.nodes[id]?.name).filter(Boolean).join(', '):reasonFor(item);
    const toggle=condition?button(open?'사유 접기':'사유 보기','job_condition','data-node-id="'+esc(item.id)+'" aria-expanded="'+open+'" aria-controls="'+esc(conditionId)+'" class="ew-v4-condition-toggle"'):'';
    return '<tr class="ew-v4-job-row" data-work-job="'+esc(item.id)+'" data-action="select" data-node-id="'+esc(item.id)+'" data-group="'+state.group+'" tabindex="0" aria-label="'+esc(item.name+' · '+state.label)+'"><td>'+workV4StatusHTML(state,{label:false})+'</td><td class="ew-v4-order">'+esc(facts.order(item))+'</td><td><div class="ew-v4-job-name">'+button(item.name,'select','data-node-id="'+esc(item.id)+'" class="ew-work-link"')+(recommended===item.id?'<span class="ew-v4-first">먼저</span>':'')+'</div><div class="ew-v4-job-reason" data-status="'+esc(state.key)+'"><span>'+esc(reason)+'</span>'+toggle+'</div></td><td>'+esc(modeLabel(item))+'</td><td>'+(assigned?'<span class="ew-v4-avatar" aria-hidden="true">'+esc(assigned.slice(0,1))+'</span>'+esc(assigned):'미지정')+'</td><td>'+(following.length?following.length+'개 대기 중':'—')+'</td><td><time title="'+esc(at)+'">'+esc(displayTime(at))+'</time></td><td>'+(state.group==='todo'?button(action,'select','data-node-id="'+esc(item.id)+'" class="ew-v4-row-action"'):'')+'</td></tr>'+(open?'<tr data-work-condition="'+esc(item.id)+'"><td colspan="8" id="'+esc(conditionId)+'">'+condition+'</td></tr>':'');
  };
  const groups=[['todo','할 일'],['running','진행 중'],['waiting','대기'],['done','완료'],['simulation','모의 통과 · 실제 미확인'],['excluded','적용 제외']];
  const rows=groups.map(([key,label])=>{const items=sortItems(matching.filter(item=>facts.state(item).group===key));if(!items.length)return '';const open=listView.groups?.[key]??!['done','simulation','excluded'].includes(key),visible=key==='waiting'&&!listView.moreWaiting?items.slice(0,2):items;return '<tr class="ew-v4-group-row"><th colspan="8" scope="rowgroup">'+button(label+' '+items.length,'job_group','data-group="'+key+'" aria-expanded="'+open+'"')+'</th></tr>'+(open?visible.map(jobRow).join('')+(visible.length<items.length?'<tr class="ew-v4-show-more"><td colspan="8">'+button((items.length-visible.length)+'개 더 보기','job_more','data-group="'+key+'"')+'</td></tr>':''):'');}).join('');
  const note='<details class="ew-v4-order-note"><summary>권장 순서 · 임시 기준</summary><p>현재 검색·담당 필터 안에서 선행 조건이 충족된 미완료 작업을 후속 작업 수, 절차 순서로 정렬합니다. 후속 수는 같은 워크플로우의 직접·상속 선행 관계를 기준으로 계산합니다. 실행 권한·승인은 별도로 확인합니다.</p></details>';
  return heading+previewActions+'<section class="ew-work-browser ew-work-list ew-v4-list" data-work-section="job-list">'+toolbar+'<div class="ew-v4-table-scroll"><table class="ew-work-job-table ew-v4-task-table"><colgroup><col class="ew-v4-col-state"><col class="ew-v4-col-order"><col><col class="ew-v4-col-mode"><col class="ew-v4-col-assignee"><col class="ew-v4-col-following"><col class="ew-v4-col-recent"><col class="ew-v4-col-action"></colgroup><thead><tr><th><span class="ew-visually-hidden">상태</span></th><th>순서</th><th>작업</th><th>수행 방식</th><th>담당</th><th>후속 작업</th><th>최근 실행</th><th><span class="ew-visually-hidden">행동</span></th></tr></thead><tbody>'+rows+'</tbody></table></div>'+(!matching.length?'<p class="ew-muted" role="status">일치하는 작업이 없습니다.</p>':'')+note+'</section>'+controls;
}

/* One saved record supplies both the summary and its folded evidence. */
function workPanelNodeHTML(c,n,{definition=c?.definition,readOnly=false,history=false,previewActions='',site=c?.site,system=c?.system,previewBlocked=false,draft=null,listView={},execution:runtimeExecution=null,executionError=null}={}) {
  const {esc,levels,statuses,badge,button,finished,lineage,siteLabel}=workUI;
  const preview=!c,locked=readOnly||history||finished(c),nodes=definition.nodes,tools=definition.tools || {};
  const legacyExecutionLocked=Boolean(!n.execution&&workLegacyExecutionLocked(runtimeExecution,c?.id));
  const ns=c?.node_states?.[n.id] || {},job=c?.jobs?.[n.id] || {};
  const labels={db:'DB 대상',ap:'AP 대상',site:'공장 확인',interface:'인터페이스 대상'};
  const children=(n.children || []).map(id=>nodes[id]).filter(Boolean),path=lineage(n.id,definition);
  const descendants=item=>item.type==='j'?[item]:(item.children || []).flatMap(id=>nodes[id]?descendants(nodes[id]):[]);
  const applies=item=>{
    if(!preview)return c.node_states?.[item.id]?.applicable!==false&&c.node_states?.[item.id]?.status!=='skipped';
    return lineage(item.id,definition).every(parent=>{
      const condition=parent.condition || 'all';
      if(parent.enabled===false||(system&&parent.systems&&!parent.systems.includes(system)))return false;
      if(!site)return true;
      if(condition==='interface')return Boolean(site.interface);
      if(condition==='reuse')return Boolean(site.reuse);
      if(condition==='new-infra')return !site.reuse;
      for(const [prefix,key] of [['country:','country'],['factory:','id'],['line:','line']])if(condition.startsWith(prefix))return condition.slice(prefix.length)===site[key];
      return true;
    });
  };
  const nodeState=item=>!applies(item)||(preview&&item.type!=='j'&&(item.children || []).length&&!descendants(item).some(applies))?'skipped':preview?'unstarted':c.node_states?.[item.id]?.status || 'pending';
  const valuesFor=item=>({db:site?.db || '',ap:site?.ap || '',site:[site?.country,site?.name,site?.line].filter(Boolean).join(' · '),interface:site?.interface?(system || '')+' · '+site.name+' 시스템 간 연계 · 예시':'',...(c?.jobs?.[item.id]?.inputs || {})});
  const fieldsFor=item=>Array.from(new Set((item.tools || []).map(id=>item.bindings?.[id] || tools[id]?.input).filter(key=>Object.hasOwn(labels,key))));
  const runtimeJobFor=item=>!executionError&&item.execution?workExecutionForNode(runtimeExecution,item.id,definition)?.run?.jobs?.[item.id]:null;
  const presentation=workV4Facts(c,definition,executionError?null:runtimeExecution,{site,system});
  const scopeComplete=item=>item.type==='j'?presentation.state(item).complete:descendants(item).filter(applies).length>0&&descendants(item).filter(applies).every(child=>presentation.state(child).complete)&&['passed','succeeded'].includes(nodeState(item));
  const navigationStateFor=item=>{
    const saved=runtimeJobFor(item),ordinary=saved&&applies(item)?{key:saved.status,label:saved.reason==='human_confirmation_required'?'확인 대기':workExecutionStatus(saved.status),attention:['failed','unknown','waiting_input','waiting_authorization'].includes(saved.status),ready:false}:workNavigationState(definition,item,c,{site,system});
    if(!applies(item))return ordinary;
    if(item.type==='j'&&presentation.state(item).group==='simulation')return {...ordinary,key:'simulation',label:'모의 통과 · 실제 미확인',attention:false};
    if(item.type!=='j'&&['passed','succeeded'].includes(ordinary.key)&&!scopeComplete(item))return {...ordinary,key:'unverified',label:descendants(item).some(child=>presentation.state(child).group==='simulation')?'모의 통과 포함 · 실제 미확인':'완료 판정 확인 필요',attention:false};
    return ordinary;
  };
  const skillUnavailable=item=>c?.node_states?.[item.id]?.block_reason==='skill_unavailable'||(preview&&navigationStateFor(item).key==='skill_unavailable');
  const unavailable=item=>!item.execution&&item.mode==='tool'&&(!(item.tools || []).length||(item.tools || []).some(id=>!tools[id]||tools[id].adapter!=='mock'||tools[id].source==='open_webui'||tools[id].enabled===false));
  const modeLabel=item=>item.execution?({fixed:'자동 조회',ai:'AI 작업',human:'사람 확인'}[item.execution.kind] || '실행 연결 확인'):item.mode==='manual'?'사람 확인':item.mode==='draft'?'초안 검토':unavailable(item)?'실행 연결 필요':'모의 점검';
  const nameOf=id=>nodes[id]?.name || '선행 업무';
  const prerequisites=item=>Array.from(new Set(lineage(item.id,definition).flatMap(parent=>parent.deps || [])));
  const missingFor=item=>preview?prerequisites(item).filter(id=>nodes[id]&&applies(nodes[id])&&descendants(nodes[id]).some(applies)):c.node_states?.[item.id]?.missing || [];
  const reasonFor=item=>{
    const saved=c?.jobs?.[item.id] || {},s=nodeState(item),missing=missingFor(item);
    if(s==='skipped')return '현장 조건에 따라 적용 제외';
    if(s==='passed')return !item.execution&&item.mode==='tool'?'모의 점검 통과 · 실제 업무 미확인':'완료 기록 있음';
    if(runtimeJobFor(item)?.reason)return workExecutionReason(runtimeJobFor(item).reason);
    if(saved.blocked_reason)return item.execution?workExecutionReason(saved.blocked_reason):saved.blocked_reason;
    if(skillUnavailable(item))return '필수 스킬을 현재 계정으로 사용할 수 없습니다. 권한·사용 여부를 확인하세요.';
    if(missing.length)return '선행 작업 확인: '+missing.map(nameOf).join(', ');
    if(item.execution)return '실행 시 현재 기능·버전·권한·공개 입력을 확인합니다.';
    if(unavailable(item))return '업무 실행 연결이 없어 점검할 수 없습니다.';
    const values=valuesFor(item),missingInputs=fieldsFor(item).filter(key=>!String(values[key] ?? '').trim());
    if(missingInputs.length)return '입력 필요: '+missingInputs.map(key=>labels[key]).join(', ');
    if(item.mode==='manual')return '담당자 확인 필요';
    if(item.mode==='draft')return saved.document?'저장된 초안 · 검토 필요':'검토할 초안 미등록';
    if(s==='failed')return (saved.checks || []).filter(check=>check.status==='failed').map(check=>check.detail || check.message).filter(Boolean).join(' · ') || '실패 사유 미기록';
    if(s==='blocked')return '입력·연결·접근 권한과 선행 작업을 확인하세요.';
    return '등록된 조건 충족 시 모의 점검 가능';
  };
  const selectButton=(item,text,primary=false)=>button(text || item.name,'select','data-node-id="'+esc(item.id)+'" class="'+(primary?'ew-primary ':'')+'ew-work-link"');
  const runButton=(text,disabled=false,primary=true,attrs='')=>button(text,'run','id="ees-work-run" data-node-id="'+esc(n.id)+'" class="'+(primary?'ew-primary':'')+'" data-mutation '+attrs+(disabled?' disabled data-unavailable="true"':''));
  const parent=path.length>1?path[path.length-2]:null;
  const breadcrumb='<nav class="ew-work-path" aria-label="업무 위치">'+(parent?(history?'<span>‹  '+esc(parent.name)+'</span>':selectButton(parent,'‹  '+parent.name)):'<span>워크플로우</span>')+'</nav>';
  const scopeText=[site?.name || site?.factory || site?.country,system,site?.line].filter(Boolean).join(' · ');
  const runtime=workExecutionForNode(runtimeExecution,n.id,definition),runtimeJob=runtime?.run?.jobs?.[n.id];
  const shownState=applies(n)?n.type==='j'&&n.execution&&runtimeJob&&!executionError?{key:runtimeJob.status,label:workExecutionStatus(runtimeJob.status)}:navigationStateFor(n):null;
  const scopeHTML='<span class="ew-work-scope">'+esc(n.type==='t'?[site?.name || site?.factory || site?.country,system,path[0]?.name].filter(Boolean).join(' · '):scopeText)+(preview?' · 시작 전':'')+'</span>';
  const header=breadcrumb+'<div class="ew-work-identity"><p class="ew-work-level">'+esc(levels[n.type])+(n.type==='j'?' / '+scopeHTML:'')+'</p><div class="ew-heading ew-work-heading"><h2 class="ew-title">'+esc(n.name)+'</h2>'+(shownState?'<span class="ew-badge" data-status="'+esc(shownState.key)+'">'+esc(shownState.label)+'</span>':badge(nodeState(n)))+'</div>'+(n.description?'<p class="ew-work-goal">'+esc(n.description)+'</p>':'')+(n.type==='j'?'':scopeHTML)+'</div>';
  const criterion='<div class="ew-work-criterion"><span>완료 조건</span><p>'+esc(n.rule || '등록된 완료 조건을 확인해 주세요.')+'</p></div>';
  const applicableLeaves=descendants(n).filter(applies),mixedRuntimeScope=descendants(n).some(item=>item.execution)&&applicableLeaves.some(item=>!item.execution);
  const runtimeHTML=()=>workExecutionRuntimeHTML(runtime,{nodeId:n.id,definition,readOnly:locked,history,error:executionError,case:c,applicable:applies(n),mixedScope:mixedRuntimeScope,planButton:!locked&&applies(n)&&nodeState(n)!=='passed'&&!mixedRuntimeScope?runButton('실행 계획 확인',previewBlocked):''});
  if(n.execution){
    // An execution lookup failure cannot expose retained schema/input/result facts.
    if(executionError)return breadcrumb+workExecutionRuntimeHTML(null,{error:executionError,history});
    const schema=runtime?.run?.input_schema || path[0]?.execution_inputs || {},savedValues=runtime?.run?.inputs || c?.execution_inputs || {},values={...savedValues,...(draft?.inputs || {})};
    const run=runtime?.run,uncertain=run&&(run.status==='unknown'||Object.values(run.jobs || {}).some(item=>item.status==='unknown'||item.validation?.status==='unknown')||(run.calls || []).some(call=>call.status==='unknown'));
    const editable=!locked&&applies(n)&&!run&&!uncertain,fields=Object.keys(schema.properties || {}),changed=Boolean(draft?.inputsChanged),saveBlocked=Boolean(previewBlocked||draft?.conflict);
    const inputs=editable&&fields.length?'<form id="ees-work-inputs" class="ew-work-form ew-v4-input-form" data-work-section="runtime-inputs" data-runtime-inputs data-node-id="'+esc(n.id)+'" data-work-save-blocked="'+saveBlocked+'"><div class="ew-section-heading"><h3>실행 입력</h3><span data-work-input-status>'+ (changed?'저장되지 않은 변경':'저장된 입력 확인')+'</span></div>'+workExecutionInputsHTML(schema,values)+workV4AIReceiptHTML(draft)+'<div class="ew-v4-mode-row"><span>수행 방식</span><p>'+esc(modeLabel(n))+' · 시작 전에 범위·권한·승인을 확인합니다.</p></div></form>':'';
    const save=inputs?'<button id="ees-work-inputs-save" type="submit" form="ees-work-inputs" data-mutation data-work-saved-inputs="'+Boolean(c)+'" data-work-save-blocked="'+saveBlocked+'"'+(saveBlocked?' disabled data-unavailable="true"':'')+'>저장</button>':'';
    let executionHTML=history?criterion:workExecutionRuntimeHTML(runtime,{nodeId:n.id,definition,readOnly:locked,history,case:c,applicable:applies(n),suppressInputs:Boolean(inputs),planButton:!locked&&applies(n)&&nodeState(n)!=='passed'?runButton('점검 시작',previewBlocked||changed):''});
    if(save){if(executionHTML.includes('<div class="ew-work-actions">'))executionHTML=executionHTML.replace('<div class="ew-work-actions">','<div class="ew-work-actions">'+save);else executionHTML+='<section class="ew-work-execute ew-work-action-region"><div class="ew-work-actions">'+save+'</div><p class="ew-work-action-note">입력 저장은 실행을 시작하지 않습니다.</p></section>';}
    const conflict=draft?.conflict?'<p class="ew-notice" role="alert">저장된 값이 변경되었습니다. 작성 중인 입력은 보존했습니다. 현재 저장값을 다시 확인해 주세요.</p>':'';
    const procedure='<details class="ew-work-procedure"><summary data-work-overlay="'+esc(n.name)+' · 절차·근거">절차·근거</summary>'+criterion+path.filter(item=>String(item.instructions || '').trim()).map(item=>'<p>'+esc(item.instructions)+'</p>').join('')+'<p class="ew-muted">등록된 절차와 저장된 실행 결과는 구분됩니다.</p></details>';
    return workV4DetailHTML(c,n,{definition,execution:runtimeExecution,site,system,draft,header:breadcrumb,history,mode:modeLabel(n),content:(preview?previewActions:'')+conflict+inputs+'<div class="ew-v4-runtime">'+executionHTML+'</div>'+procedure});
  }
  // Node instructions are business-facing work guidance; configuration lists
  // and Skill/prompt source bodies belong in Workspace, not this surface.
  const guidance=path.filter(item=>String(item.instructions || '').trim()).map(item=>'<p>'+esc(item.instructions)+'</p>').join('');
  const guidanceHTML=guidance?'<details class="ew-work-guidance"><summary>업무 안내</summary>'+guidance+'</details>':'';
  const deps=prerequisites(n),depsHTML=deps.length?'<div class="ew-work-prerequisites"><span>선행 작업</span>'+deps.map(id=>nodes[id]?(history?'<span>'+esc(nameOf(id))+'</span>':selectButton(nodes[id],nameOf(id)))+'<span>'+esc(preview?'시작 전':statuses[c.node_states?.[id]?.status] || '확인 필요')+'</span>':'<span>선행 작업 미기록</span>').join('')+'</div>':'';
  const leafJobs=descendants(n),eligibleJobs=leafJobs.filter(applies);
  const missingInputsFor=item=>fieldsFor(item).filter(key=>!String(valuesFor(item)[key] ?? '').trim());
  const attentionFor=item=>{
    if(!applies(item)||nodeState(item)==='passed')return false;
    const saved=c?.node_states?.[item.id];
    if(typeof saved?.attention==='boolean')return saved.attention;
    if(preview)return navigationStateFor(item).attention;
    return nodeState(item)==='failed'||unavailable(item)||missingInputsFor(item).length>0||(nodeState(item)==='blocked'&&!missingFor(item).length);
  };
  const readyFor=item=>{
    const saved=c?.node_states?.[item.id];
    if(typeof saved?.ready_for_run==='boolean')return saved.ready_for_run;
    if(preview)return navigationStateFor(item).ready;
    return applies(item)&&item.mode==='tool'&&!['passed','failed','running'].includes(nodeState(item))&&!unavailable(item)&&!missingFor(item).length&&!missingInputsFor(item).length;
  };
  const jobProgress=item=>{const jobs=descendants(item),eligible=jobs.filter(applies);return {total:eligible.length,done:eligible.filter(child=>presentation.state(child).complete).length,simulation:eligible.filter(child=>presentation.state(child).group==='simulation').length,excluded:jobs.length-eligible.length};};
  const taskProgress=item=>{
    const eligible=(item.children || []).map(id=>nodes[id]).filter(child=>child&&applies(child)&&(child.type==='j'||descendants(child).some(applies)));
    return {total:eligible.length,done:eligible.filter(scopeComplete).length,excluded:(item.children || []).length-eligible.length};
  };
  if(n.type!=='j') {
    const count=taskProgress(n),jobs=jobProgress(n),unit=n.type==='p'?'단계':'작업';
    const remaining=eligibleJobs.filter(item=>nodeState(item)!=='passed'),actualRemaining=eligibleJobs.filter(item=>!presentation.state(item).complete),problems=remaining.filter(attentionFor),ready=remaining.filter(readyFor);
    const next=problems[0] || remaining.find(item=>item.id===ns.next_node_id) || remaining.find(item=>!missingFor(item).length) || remaining[0];
    const counts={simulation:0,human:0,unavailable:0,fixed:0,ai:0};remaining.forEach(item=>counts[item.execution?.kind || (item.mode!=='tool'?'human':unavailable(item)?'unavailable':'simulation')]++);
    const metric=(key,label,value,extra='')=>'<div data-work-metric="'+key+'"><span>'+label+'</span><strong>'+value+'</strong>'+extra+'</div>';
    const fraction=(done,total,attributes='')=>'<span'+attributes+'>'+done+'<small> / '+total+'</small></span>';
    const amount=value=>value+'<small>개 작업</small>';
    const completionBar=jobs.total?'<progress aria-label="작업 완료 수" value="'+jobs.done+'" max="'+jobs.total+'"></progress>':'';
    const attentionGroups=new Map();for(const item of problems){const label=navigationStateFor(item).label;attentionGroups.set(label,(attentionGroups.get(label)||0)+1);}
    const attentionDetail=attentionGroups.size?'<p class="ew-work-attention-detail">'+Array.from(attentionGroups,([label,total])=>esc(label)+' '+total).join(' · ')+'</p>':'';
    const progress='<div class="ew-work-progress" data-work-section="progress"><div class="ew-work-metrics">'+(n.type==='p'?metric('stages','단계 완료',fraction(count.done,count.total,' data-work-done="'+count.done+'" data-work-total="'+count.total+'"')):'')+metric('jobs','작업 완료',fraction(jobs.done,jobs.total,n.type==='t'?' data-work-done="'+jobs.done+'" data-work-total="'+jobs.total+'"':''),completionBar)+(n.type==='t'?metric('incomplete','미완료',amount(actualRemaining.length)):'')+metric('attention','미완료 중 조치 필요',amount(problems.length),attentionDetail)+(jobs.simulation?metric('simulation','모의 통과 · 실제 미확인',amount(jobs.simulation)):'')+'</div>'+(jobs.excluded?'<p class="ew-muted">적용 제외 '+jobs.excluded+'개 작업'+(n.type==='p'&&count.excluded?' · '+count.excluded+'개 단계':'')+'</p>':'')+(!jobs.total?'<p class="ew-muted">'+(children.length?'이 범위는 적용 제외입니다.':'등록된 하위 작업이 없습니다.')+'</p>':'')+'</div>';
    const conditionsFor=child=>{
      const saved=c?.jobs?.[child.id] || {},facts=[];
      for(const item of lineage(child.id,definition)){
        if(item.condition&&item.condition!=='all')facts.push('<p>적용 조건 · '+esc(item.condition)+'</p>');
        if(item.enabled===false)facts.push('<p>사용 중지된 작업</p>');
      }
      for(const id of prerequisites(child)){
        const dep=nodes[id];
        const depState=dep?navigationStateFor(dep):null,depDone=dep&&nodeState(dep)==='passed';
        facts.push('<div class="ew-work-dependency" data-dependency-complete="'+Boolean(depDone)+'"><div class="ew-work-condition-fact"><span>선행 작업</span><div>'+(dep?selectButton(dep,dep.name):'<span>선행 작업 미기록</span>')+'<span> · '+esc(depState?.label || '상태 미기록')+'</span></div></div><div class="ew-work-condition-fact"><span>충족 조건</span><p>'+esc(dep?.rule || '충족 조건 미기록')+' · '+(depDone?'충족':'현재 미충족')+'</p></div></div>');
      }
      const executionJob=runtimeJobFor(child);
      if(executionJob?.reason)facts.push('<p>'+esc(workExecutionStatus(executionJob.status))+' · '+esc(workExecutionReason(executionJob.reason))+'</p>');
      else if(saved.blocked_reason)facts.push('<p>'+esc(child.execution?workExecutionReason(saved.blocked_reason):saved.blocked_reason)+'</p>');
      for(const check of saved.checks || [])if(['failed','blocked','skipped'].includes(check.status))facts.push('<p>'+esc(check.name || '점검')+' · '+esc(check.detail || check.message || '사유 미기록')+'</p>');
      if(nodeState(child)==='failed'&&!(saved.checks || []).some(check=>check.status==='failed'))facts.push('<p>실패 사유 미기록</p>');
      const missing=missingInputsFor(child);if(missing.length)facts.push('<p>필수 입력 · '+esc(missing.map(key=>labels[key]).join(', '))+'</p>');
      if(skillUnavailable(child))facts.push('<p>필수 스킬을 현재 계정으로 사용할 수 없습니다.</p>');
      if(unavailable(child))facts.push('<p>실행 연결 필요 · 실제 호출 미수행</p>');
      return facts.join('');
    };
    const jobRow=child=>{
      const shown=navigationStateFor(child),facts=conditionsFor(child),open=Boolean(listView.expanded?.includes(child.id)&&facts),conditionId='ees-work-condition-'+child.id;
      const toggle=facts?'<button type="button" data-action="job_condition" data-node-id="'+esc(child.id)+'" aria-label="'+esc(child.name)+' 조건·사유 '+(open?'접기':'펼치기')+'" aria-expanded="'+open+'" aria-controls="'+esc(conditionId)+'" class="ew-work-condition-toggle"><img src="/_ees12/work-condition-'+(open?'expanded':'collapsed')+'.svg" alt="" aria-hidden="true"></button>':'';
      return '<tr data-work-job="'+esc(child.id)+'"'+(attentionFor(child)?' class="ew-work-problem"':'')+'><td>'+selectButton(child)+'</td><td>'+esc(modeLabel(child))+'</td><td><span class="ew-badge" data-status="'+esc(shown.key)+'">'+esc(shown.label)+'</span></td><td>'+toggle+'</td></tr>'+(open?'<tr data-work-condition="'+esc(child.id)+'"><td colspan="4" id="'+esc(conditionId)+'">'+facts+'</td></tr>':'');
    };
    const query=String(listView.query || ''),needle=query.trim().toLocaleLowerCase(),filter=['all','attention','incomplete','completed','excluded'].includes(listView.filter)?listView.filter:'all';
    const matches={all:()=>true,attention:attentionFor,incomplete:item=>applies(item)&&!presentation.state(item).complete,completed:item=>applies(item)&&presentation.state(item).complete,excluded:item=>!applies(item)};
    const matching=leafJobs.filter(item=>matches[filter](item)&&(!needle||item.name.toLocaleLowerCase().includes(needle)));
    const pageSize=6,page=Math.min(Math.max(0,Number.isFinite(listView.page)?Math.floor(listView.page):0),Math.max(0,Math.ceil(matching.length/pageSize)-1)),offset=page*pageSize;
    const filters=[['all','전체'],['attention','조치 필요'],['incomplete','미완료'],['completed','완료'],['excluded','적용 제외']];
    const pages=matching.length>pageSize?button('이전','job_page','data-page="'+Math.max(0,page-1)+'"'+(!page?' disabled':''))+button('다음','job_page','data-page="'+(page+1)+'"'+(offset+pageSize>=matching.length?' disabled':'')):'';
    const browser='<section class="ew-work-browser ew-work-list" data-work-section="job-list"><h3>작업 현황</h3><div class="ew-work-job-toolbar"><label class="ew-work-search"><span class="ew-visually-hidden">작업 이름 검색</span><img src="/_ees12/work-search.svg" alt="" aria-hidden="true"><input id="ees-work-job-search" type="search" value="'+esc(query)+'" placeholder="작업 이름 검색" autocomplete="off"></label><div class="ew-work-filters" aria-label="작업 상태 필터">'+filters.filter(([key])=>key!=='excluded'||leafJobs.some(matches.excluded)||filter==='excluded').map(([key,label])=>button(label+' '+leafJobs.filter(matches[key]).length,'job_filter','data-filter="'+key+'" aria-pressed="'+(key===filter)+'"')).join('')+'</div></div><table class="ew-work-job-table"><thead><tr><th scope="col">작업</th><th scope="col">수행 방식</th><th scope="col">상태</th><th scope="col">조건·사유</th></tr></thead><tbody>'+matching.slice(offset,offset+pageSize).map(jobRow).join('')+'</tbody></table>'+(!matching.length?'<p class="ew-muted" role="status">일치하는 작업이 없습니다.</p>':'')+'<div class="ew-work-pagination"><span role="status">'+(matching.length?offset+1:0)+'–'+Math.min(offset+pageSize,matching.length)+' / '+matching.length+'개 작업</span>'+pages+'</div></section>';
    const rows=children.map(child=>{
      const childStatus=navigationStateFor(child),childJobs=jobProgress(child),childProblems=descendants(child).filter(attentionFor).length;
      if(history)return '<tr><td colspan="3"><details class="ew-history-node"><summary>'+esc(child.name)+'</summary>'+workPanelNodeHTML(c,child,{definition,readOnly:true,history:true})+'</details></td></tr>';
      const distribution=new Map();for(const job of descendants(child).filter(applies)){const state=navigationStateFor(job);if(!['passed','succeeded','ready','unstarted'].includes(state.key))distribution.set(state.label,{key:state.key,count:(distribution.get(state.label)?.count||0)+1});}
      const breakdown=childProblems&&distribution.size?'<small data-work-distribution="'+esc(child.id)+'">'+[...distribution].map(([label,value])=>'<span data-status="'+esc(value.key)+'">'+esc(label)+' '+value.count+'</span>').join(' ')+'</small>':'';
      return '<tr'+(childProblems?' class="ew-work-problem"':'')+'><td>'+selectButton(child)+(child.description?'<small>'+esc(child.description)+'</small>':'')+breakdown+'</td><td>'+childJobs.done+' / '+childJobs.total+(childJobs.simulation?'<small>모의 통과 '+childJobs.simulation+' · 실제 미확인</small>':'')+(childJobs.excluded?'<small>적용 제외 '+childJobs.excluded+'</small>':'')+'</td><td><span class="ew-badge" data-status="'+esc(childStatus.key)+'">'+esc(childStatus.label)+'</span></td></tr>';
    }).join('');
    const table=history||n.type==='p'?'<section class="ew-work-list'+(!history&&n.type==='p'?' ew-work-stage-list':'')+'"><h3>'+(n.type==='p'?'단계별 수행·진행':unit+'별 진행')+'</h3><table'+(!history&&n.type==='p'?' class="ew-work-stage-table"':'')+'><thead><tr><th scope="col">'+unit+'</th><th scope="col">작업 완료</th><th scope="col">상태</th></tr></thead><tbody>'+rows+'</tbody></table></section>':'';
    const execution=!locked&&remaining.length?'<details class="ew-work-execution" data-work-section="execution-scope"><summary>진행 범위 자세히</summary><p>'+((counts.fixed||counts.ai)?'자동 조회 <span data-work-count="fixed">'+counts.fixed+'</span>개 · AI 작업 <span data-work-count="ai">'+counts.ai+'</span>개 · ':'')+'모의 점검 <span data-work-count="simulation">'+counts.simulation+'</span>개 · 사람 확인/검토 <span data-work-count="human">'+counts.human+'</span>개 · 실행 연결 필요 <span data-work-count="unavailable">'+counts.unavailable+'</span>개</p><p class="ew-muted">적용 대상 미완료 작업의 구성입니다. 이번 실행 예정 수가 아닙니다. 선행 점검이 완료되면 범위 안의 다음 점검도 이어집니다. 실행 시 입력·권한·연결을 다시 확인하며 진행할 수 없으면 차단 이유를 기록합니다. 실패 재시도와 사람 확인은 별도입니다.</p></details>':'';
    const runtimeScope=workHasExecution(definition,n.id);
    const actionHTML=runtimeScope&&!history?runtimeHTML():!locked&&remaining.length?'<section class="ew-work-scope-action'+(ready.length?' ew-work-action-region':'')+'"><div class="ew-work-scope-row">'+(ready.length?'<div class="ew-work-actions">'+runButton('범위 모의 점검 실행',previewBlocked||legacyExecutionLocked)+'</div>':'')+'<p class="ew-work-ready" data-work-ready="'+ready.length+'">현재 점검 가능 '+ready.length+'개 · '+esc(n.name)+' 범위</p></div><p class="ew-work-scope-boundary">'+(legacyExecutionLocked?'연결 실행이 종료되기 전에는 모의 점검을 할 수 없습니다. 현재 실행 상태를 확인하세요.':'사람 확인·실패 재시도는 별도입니다. 미연결 작업은 호출 없이 차단 사유를 기록합니다.<br>현재 점검 가능 수는 최종 처리 수가 아닙니다.')+'</p></section>':'';
    const finder=!history&&n.type==='p'?'<details class="ew-work-job-finder"'+(query||filter!=='all'?' open':'')+'><summary>전체 작업 찾아보기</summary><p class="ew-work-remaining" data-work-metric="incomplete">미완료 <strong>'+actualRemaining.length+'개 작업</strong></p>'+browser+'</details>':'';
    if(!history&&n.type==='t'){
      const management='<details class="ew-v4-stage-controls"><summary>단계 수행·관리</summary>'+progress+criterion+depsHTML+actionHTML+guidanceHTML+execution+(c?'<div class="ew-work-read-links">'+button('업무 기록 보기','work_records')+'</div>':'')+'</details>';
      return breadcrumb+workV4ListHTML(c,n,{definition,execution:executionError?null:runtimeExecution,site,system,listView,modeLabel,reasonFor,conditionsFor,previewActions:preview?previewActions:'',controls:management});
    }
    return header+(preview?previewActions:'')+progress+(n.type==='p'?table+criterion:criterion+table)+depsHTML+(!history&&n.type!=='p'?browser:'')+actionHTML+finder+guidanceHTML+execution+(!history&&c?'<div class="ew-work-read-links">'+button('업무 기록 보기','work_records')+'</div>':'');
  }
  const dataHTML=(values,document)=>Object.entries(values || {}).filter(([key])=>Object.hasOwn(labels,key)).map(([key,value])=>'<p><strong>'+esc(labels[key])+'</strong> · '+esc(value)+'</p>').join('')+(document?'<p><strong>저장된 초안</strong></p><pre>'+esc(document)+'</pre>':'');
  const checksHTML=checks=>(checks || []).map((check,index)=>'<div class="ew-check"><div class="ew-heading"><strong>'+esc(check.name || tools[check.id || check.tool_id || check.tool]?.name || '점검 '+(index+1))+'</strong>'+(check.status==='skipped'?'<span class="ew-badge" data-status="skipped">미수행</span>':badge(check.status))+'</div><p>'+esc(check.message || check.detail || check.summary || '')+'</p>'+(check.input!==undefined?'<p>점검 대상 · '+esc(check.input)+'</p>':'')+(check.at?'<p>확인 시각 · '+esc(check.at)+'</p>':'')+'</div>').join('');
  const recordKind=record=>record.kind==='human_confirmation'?'담당자 확인':record.kind==='execution_blocked'?'미수행 · 실행 연결 필요':record.kind==='simulation'||record.simulation?'모의 점검':'저장된 실행';
  const recordHTML=record=>'<p class="ew-muted">'+esc(record.at || record.completed_at || '실행 시각 미기록')+' · '+recordKind(record)+'</p>'+(record.detail?'<p>'+esc(record.detail)+'</p>':'')+checksHTML(record.checks)+dataHTML(record.inputs,record.document);
  const records=job.history || [],last=records[records.length-1],checks=job.checks || [];
  const latest=!preview&&applies(n)&&!['pending','review'].includes(job.status)&&last&&last.status===job.status&&last.attempt===job.attempt&&(n.mode!=='tool'||checks.length)?last:null;
  const previous=latest?records.slice(0,-1):records;
  const failure=latest?.checks?.find(check=>['failed','blocked'].includes(check.status));
  const currentText=!applies(n)?'이 업무는 현재 범위에서 적용 제외입니다.':nodeState(n)==='running'?'점검 결과를 기다리고 있습니다.':nodeState(n)==='blocked'&&job.blocked_reason?job.blocked_reason:shownState?.key==='input_required'?'점검할 대상을 입력해 주세요.':shownState?.key==='ready'?'모의 점검을 시작할 수 있습니다.':shownState?.key==='waiting'?'선행 작업 완료를 기다리고 있습니다.':preview?'아직 시작하지 않은 업무입니다.':latest&&nodeState(n)==='passed'&&['manual','draft'].includes(n.mode)?(n.mode==='draft'?'초안 검토가 완료됐습니다.':'담당자 확인이 완료됐습니다.'):latest&&nodeState(n)==='passed'?'모의 점검을 통과했습니다. 실제 업무 완료는 확인하지 않았습니다.':unavailable(n)?'실행 연결이 필요합니다.':nodeState(n)==='failed'?(failure?.detail || failure?.message || '실패 사유 미기록'):nodeState(n)==='blocked'?reasonFor(n):n.mode==='manual'?'담당자의 확인이 필요합니다.':n.mode==='draft'?'초안 검토가 필요합니다.':latest?(failure?.detail || failure?.message || latest.detail || '점검 결과가 저장되었습니다.'):records.length?'현재 조건의 유효한 결과가 없습니다. 재점검이 필요합니다.':'아직 수행한 결과가 없습니다.';
  const currentMeta=!applies(n)?'현재 공장·시스템 조건에서는 실행 대상이 아닙니다.':nodeState(n)==='running'?'결과 대기 · 완료 여부는 실행 종료 후 판정합니다.':preview?'미수행 · 아직 실행 기록이 없습니다.':latest?esc((latest.at || latest.completed_at || '실행 시각 미기록')+' · '+recordKind(latest)):unavailable(n)?'실행 연결 전에는 수행된 것으로 기록하지 않습니다.':n.mode==='manual'?'아직 확인 완료 기록이 없습니다.':n.mode==='draft'?(job.document?'저장된 초안을 직접 검토해 주세요.':'검토할 초안이 아직 없습니다.'):(records.length?'이전 결과는 실행 이력에 보존됩니다.':'미수행');
  const checkDetail=check=>{for(const key of ['detail','message','summary'])if(Object.hasOwn(check,key)&&check[key]!==null&&check[key]!==undefined)return check[key]===''?'빈 결과':check[key];return '결과 설명 미기록';};
  const checkSummary=latest&&checks.length?'<div class="ew-work-check-summary" aria-label="수행 결과">'+checks.map((check,index)=>'<div><span>'+esc(check.name || tools[check.id || check.tool_id || check.tool]?.name || '점검 '+(index+1))+'</span><p>'+esc(checkDetail(check))+'</p>'+(check.status==='skipped'?'<span class="ew-badge" data-status="skipped">미수행</span>':badge(check.status))+'</div>').join('')+'</div>':'';
  const planned=!latest&&(n.tools || []).length?'<div class="ew-work-check-summary ew-work-planned" aria-label="예정된 점검">'+(n.tools || []).map((id,index)=>'<div><span>'+esc(tools[id]?.name || '점검 '+(index+1))+'</span><p>'+esc(tools[id]?.purpose || '등록된 확인 내용 없음')+'</p></div>').join('')+'</div>':'';
  const completed=Boolean(latest&&nodeState(n)==='passed');
  const resultCriterion=latest?'<div class="ew-work-criterion" data-work-criterion-status="'+(completed?'passed':'failed')+'"><span>완료 기준</span><p>'+(completed?(latest?.kind==='simulation'||latest?.simulation?'모의 조건 충족 · 실제 완료 미확인':'충족'):'미충족')+' · '+esc(n.rule || '등록된 완료 조건을 확인해 주세요.')+'</p></div>':criterion.replace('>완료 조건<','>완료 기준<');
  const showCurrent=latest||n.mode!=='tool'||unavailable(n)||!applies(n)||job.blocked_reason;
  const result='<section class="ew-work-result" data-work-section="current-result" data-work-recorded="'+Boolean(latest)+'"><h3>'+ (latest?'확인 결과':'확인 내용과 완료 기준')+'</h3>'+(showCurrent?'<p class="ew-work-current-title">'+esc(currentText)+'</p>':'')+(latest?'':'<p class="ew-muted'+(showCurrent?'':' ew-visually-hidden')+'">'+currentMeta+'</p>')+checkSummary+planned+resultCriterion+(latest&&history?recordHTML(latest):'')+'</section>';
  const inputs={...valuesFor(n),...(draft?.inputs || {})},fields=fieldsFor(n),document=draft?.document ?? job.document ?? '';
  const nodeId=' data-node-id="'+esc(n.id)+'"',changed=Boolean(draft?.inputsChanged||draft?.documentChanged),conflict=Boolean(draft?.conflict);
  const unavailableNow=previewBlocked||legacyExecutionLocked||!applies(n)||nodeState(n)==='running'||missingFor(n).length||missingInputsFor(n).length||unavailable(n)||skillUnavailable(n)||conflict;
  // Defaults are suggestions, not proof that the user saved this task's inputs.
  const savedInputs=fields.length>0&&fields.every(key=>Object.hasOwn(job.inputs || {},key));
  const saveBlocked=Boolean(previewBlocked||legacyExecutionLocked||conflict),saveUnavailable=saveBlocked||(savedInputs&&!changed);
  const inputHTML=!locked&&applies(n)&&fields.length?'<form id="ees-work-inputs" class="ew-work-form'+(fields.length===1?' ew-single-field':'')+'" data-work-stage="input" data-work-save-blocked="'+saveBlocked+'"'+nodeId+'><div class="ew-section-heading"><h3>실행 입력</h3><span data-work-input-status>'+(!savedInputs||changed?'저장 전':'저장됨')+' · '+(latest?'이전 결과 있음':'점검 미수행')+'</span></div>'+fields.map(key=>'<label><span class="ew-input-field-name">'+labels[key]+'</span><input name="'+key+'" value="'+esc(inputs[key] || '')+'" autocomplete="off"></label>').join('')+'<p class="ew-muted">'+esc(modeLabel(n))+(n.mode==='tool'?' · 실제 시스템 접속·변경 없음':' · 입력값을 확인한 뒤 저장하세요.')+'<span class="ew-visually-hidden"> · 비밀번호·접속 키는 입력하지 마세요.</span></p></form>':'';
  const inputSave=inputHTML?'<button id="ees-work-inputs-save" type="submit" form="ees-work-inputs" class="'+(!savedInputs||changed?'ew-primary':'')+'" data-mutation data-work-saved-inputs="'+savedInputs+'" data-work-save-blocked="'+saveBlocked+'"'+(saveUnavailable?' disabled data-unavailable="true"':'')+'>저장</button>':'';
  const documentRequirementsBlocked=Boolean(missingFor(n).length||skillUnavailable(n)),documentBlocked=saveBlocked||documentRequirementsBlocked;
  const documentHTML=!locked&&applies(n)&&n.mode==='draft'?'<form id="ees-work-document" class="ew-work-form" data-work-save-blocked="'+documentBlocked+'"'+nodeId+'><label>검토할 초안<textarea name="document" rows="6" placeholder="대화로 작성을 요청하거나 직접 입력하세요.">'+esc(document)+'</textarea></label></form>':'';
  const documentSave=documentHTML?'<button type="submit" form="ees-work-document" data-mutation'+(documentBlocked?' disabled data-unavailable="true"':'')+'>초안 반영</button>':'';
  const conflictHTML=conflict?'<div class="ew-notice" role="alert">저장된 값이 변경되었습니다. 작성 중인 입력은 보존했습니다. 최신 저장값과 비교한 뒤 다시 반영하세요.<details><summary>최신 저장값</summary>'+dataHTML(valuesFor(n),job.document)+'</details>'+button('저장값으로 되돌리기','discard_job_edits',nodeId)+button('현재 입력 계속 편집','rebase_job_edits',nodeId)+'</div>':'';
  const formHTML=inputHTML+workV4AIReceiptHTML(draft)+documentHTML;
  const dirtyHTML=formHTML?'<p class="ew-work-dirty ew-visually-hidden" data-work-dirty role="status"'+(changed?'':' hidden')+'>입력 변경됨</p>':'';
  const editable=(latest||nodeState(n)==='passed')&&formHTML?'<details class="ew-work-edit"><summary>입력 변경</summary>'+formHTML+'</details>':formHTML;
  const saved=locked?'<details class="ew-work-detail"><summary>저장된 입력과 초안</summary>'+dataHTML(valuesFor(n),job.document)+'</details>':'';
  const old=previous.length?'<details class="ew-history" data-work-section="history"><summary data-work-overlay="'+esc(n.name)+' 실행 이력">실행 이력 '+previous.length+'건 · 읽기 전용</summary>'+[...previous].reverse().map(record=>'<details class="ew-history-attempt"><summary>'+esc(record.attempt || '?')+'차 · '+esc(statuses[record.status] || record.status)+' · '+esc(record.at || record.completed_at || '시각 미기록')+'</summary>'+recordHTML(record)+'</details>').join('')+'</details>':'';
  const review=['manual','draft'].includes(n.mode)?'<details class="ew-work-detail"><summary data-work-overlay="'+esc(n.name)+' 검토 자료">검토 자료 보기</summary><p>'+esc(n.description || '등록된 업무 목적을 확인해 주세요.')+'</p>'+guidanceHTML+criterion+dataHTML(valuesFor(n),job.document)+'<p class="ew-muted">등록된 안내와 저장된 자료입니다. 실제 외부 시스템의 설정 차이를 조회한 결과는 아닙니다.</p></details>':'';
  let action='';
  const baseUnavailable=Boolean(unavailableNow||(n.mode==='draft'&&!job.document));
  if(!locked&&(nodeState(n)!=='passed'||n.mode==='tool')&&applies(n))action=runButton(n.mode==='manual'?'확인 완료':n.mode==='draft'?'검토 완료':job.attempt?'다시 모의 점검':'모의 점검',baseUnavailable||changed,!completed&&(!inputHTML||(savedInputs&&!changed)),'data-work-draft-sensitive data-work-base-unavailable="'+baseUnavailable+'" data-work-retry-complete="'+completed+'"');
  const returnAction=completed&&parent&&!history?button(parent.type==='t'?'단계로 돌아가기':'상위 업무로 돌아가기','panel_parent','data-node-id="'+esc(parent.id)+'" class="ew-primary ew-work-link"'):'';
  const actionNote=legacyExecutionLocked?'연결 실행이 종료되기 전에는 입력·초안을 반영하거나 이 작업을 완료할 수 없습니다. 작성 중인 내용은 이 화면에 보존됩니다. 현재 실행 상태를 확인하세요.':documentHTML&&documentRequirementsBlocked?reasonFor(n):changed?'작성 중인 입력을 저장한 뒤 점검하세요.':completed?(latest?.kind==='simulation'||latest?.simulation?'모의 점검 기록을 저장했습니다. 실제 업무 완료는 미확인입니다.':'이 작업의 완료 기록을 저장했습니다. 상위 업무의 진행 상태를 확인하세요.'):!savedInputs&&fields.length?'현재 대상 값을 확인하고 입력 저장 또는 모의 점검을 진행하세요.':job.attempt&&n.mode==='tool'?'이전 이력은 보존되며 재시도 결과를 완료 조건에 따라 판정합니다.':n.mode==='tool'?'저장된 입력으로 모의 점검합니다. 실제 업무 시스템을 호출하지 않습니다.':'확인한 내용만 완료로 기록합니다.';
  const execution=action||inputSave||documentSave||returnAction?'<section class="ew-work-execute ew-work-action-region" data-work-stage="execute" aria-label="입력 저장과 실행"><div class="ew-work-actions">'+inputSave+documentSave+action+returnAction+'</div><p class="ew-work-action-note" data-work-next data-work-edit-locked="'+Boolean(legacyExecutionLocked||(documentHTML&&documentRequirementsBlocked))+'" data-work-saved-next="'+esc(actionNote)+'">'+esc(actionNote)+'</p></section>':'';
  const inputStage=conflictHTML+editable+dirtyHTML;
  const targetValues=fields.map(key=>'<div class="ew-work-target-field"><span>'+esc(fields.length===1?'수행 대상':labels[key])+'</span><p>'+esc((latest?.inputs || valuesFor(n))[key] || '입력 필요')+'</p></div>').join('');
  const recordedAt=latest?.at || latest?.completed_at;
  const recordedDate=recordedAt?new Date(recordedAt):null;
  const shortTime=recordedDate&&!Number.isNaN(recordedDate.getTime())?recordedDate.getFullYear()+'.'+String(recordedDate.getMonth()+1).padStart(2,'0')+'.'+String(recordedDate.getDate()).padStart(2,'0')+' '+String(recordedDate.getHours()).padStart(2,'0')+':'+String(recordedDate.getMinutes()).padStart(2,'0')+':'+String(recordedDate.getSeconds()).padStart(2,'0'):(recordedAt || '시각 미기록');
  const target='<section class="ew-work-target" data-work-section="target"><div class="ew-section-heading"><h3>'+(latest?'수행 기록':'수행 대상')+'</h3>'+(latest?'<span>실행 #'+esc(latest.attempt || job.attempt || '미기록')+' · <time datetime="'+esc(recordedAt || '')+'" title="'+esc(recordedAt || '시각 미기록')+'">'+esc(shortTime)+'</time></span>':'')+(latest&&!history?button('상세 보기','work_detail','data-detail-tab="output" data-node-id="'+esc(n.id)+'" class="ew-work-output-link"'):'')+'</div>'+targetValues+(!targetValues?'<p>'+esc(scopeText || '대상 미기록')+'</p>':'')+'<p class="ew-muted">'+esc(latest?recordKind(latest):modeLabel(n))+(latest?.simulation||latest?.kind==='simulation'?' · 실제 시스템 접속·변경 없음':'')+'</p>'+'</section>';
  const procedure='<details class="ew-work-procedure"><summary data-work-overlay="'+esc(n.name)+' · 절차·근거">절차·근거</summary><p>'+esc(c?'진행 건에 고정된 절차':'시작 전 게시 절차')+((c?.version ?? definition.version)!==undefined?' v'+esc(c?.version ?? definition.version):' · 버전 미기록')+'</p>'+(n.description?'<p>'+esc(n.description)+'</p>':'')+criterion+(guidance || '<p>등록된 업무 지침 없음</p>')+'<p class="ew-muted">등록된 절차입니다. 실제 호출 당시 전달·준수 기록을 뜻하지 않습니다.</p></details>';
  const detailLinks=!history?'<nav class="ew-work-detail-links" aria-label="수행 자료">'+button('사용 구성','work_detail','data-detail-tab="config" data-node-id="'+esc(n.id)+'"')+procedure+button('실행 이력 '+records.length+'건','work_detail','data-detail-tab="history" data-node-id="'+esc(n.id)+'"')+'</nav>':'';
  const blockers=skillUnavailable(n)?'<p class="ew-notice" role="status">필수 스킬을 현재 계정으로 사용할 수 없습니다.</p>':'';
  const content=blockers+(latest?result+execution+target+detailLinks+inputStage:inputStage+execution+result+(!fields.length?target:'')+detailLinks);
  const checkItems=(n.tools || []).map((id,index)=>{const check=latest?.checks?.find(item=>[item.id,item.tool_id,item.tool].includes(id)) || latest?.checks?.[index];return '<tr><th scope="row">'+esc(tools[id]?.name || '점검 '+(index+1))+'</th><td>'+esc(tools[id]?.purpose || n.rule || '등록된 완료 기준')+'</td><td>'+esc(check?(check.status==='passed'?'모의 통과':statuses[check.status] || check.status):'미실행')+'</td></tr>';}).join('');
  const checksTable='<section class="ew-v4-checks"'+(!latest?' data-work-section="current-result" data-work-recorded="false"':'')+'><h3>확인 항목</h3>'+(!latest&&(showCurrent||records.length)?'<p>'+esc(currentText)+'</p><p class="ew-muted">'+currentMeta+'</p>':'')+(checkItems?'<table><thead><tr><th>항목</th><th>기준</th><th>결과</th></tr></thead><tbody>'+checkItems+'</tbody></table>':'')+'<p>완료 기준 · '+esc(n.rule || '등록된 완료 조건을 확인해 주세요.')+'</p></section>';
  const recordSection='<section class="ew-v4-records"><h3>실행 기록</h3>'+(records.length?detailLinks:'<p class="ew-muted">아직 실행한 기록이 없습니다.</p>')+'</section>';
  const actualResult=latest?result+target:'';
  const v4Content=(preview?previewActions:'')+blockers+(latest?actualResult+inputStage+checksTable:inputStage+checksTable)+recordSection+execution+(history?old:'')+review+depsHTML+(history?guidanceHTML:'')+saved+(!records.length?procedure:'');
  return workV4DetailHTML(c,n,{definition,execution:runtimeExecution,site,system,draft,header:breadcrumb,content:v4Content,mode:modeLabel(n),history});
}

/* Read-only, allowlisted facts from the applied definition and one saved attempt.
 * No current form values, raw snapshot map or latest draft are evidence sources. */
function workExecutionDetailHTML(c,n,{definition=c?.definition,tab='config',attemptIndex=null,callIndex=0,lookupError=null,assetsAvailable=definition?.assets_available,availableSkills=definition?.available_skills || []}={}) {
  const {esc,button,lineage}=workUI,job=c?.jobs?.[n.id] || {},records=job.history || [];
  const tabs=[['config','사용 구성'],['history','실행 이력'],['input','전달 입력'],['output','반환 출력']];
  if(!tabs.some(([key])=>key===tab))tab='config';
  const nav='<nav class="ew-detail-tabs" aria-label="수행 상세">'+tabs.map(([key,label])=>button(label,'detail_tab','data-detail-tab="'+key+'" aria-pressed="'+(key===tab)+'"')).join('')+'</nav>';
  const section=body=>nav+'<section data-work-detail-content="'+tab+'">'+body+'</section>';
  const fact=(label,value)=>'<div class="ew-detail-fact"><dt>'+esc(label)+'</dt><dd>'+esc(value ?? '미기록')+'</dd></div>';
  const text=value=>typeof value==='string'?value:JSON.stringify(value);
  const resultLabel=(status,record)=>status==='passed'&&(record?.kind==='simulation'||record?.simulation)?'모의 통과 · 실제 미확인':({passed:'업무 통과',failed:'업무 실패',blocked:'업무 미완료 · 실행 차단',skipped:'미수행',pending:'미수행',review:'검토 필요'}[status] || '업무 판정 미기록');
  if(lookupError)return section('<p role="alert" data-record-state="'+(lookupError.kind==='restricted'?'restricted':'failed')+'">'+(lookupError.kind==='restricted'?'접근 제한':'조회 실패')+' · '+esc(lookupError.message)+'</p><p>현재 조회가 완료되지 않아 이전 저장 자료를 표시하지 않습니다.</p>');
  const version=c?.version ?? definition?.version;
  const provenance='<p class="ew-detail-provenance">'+(c?'진행 건에 고정된 절차':'시작 전 게시 절차')+(version!==undefined?' v'+esc(version):' · 버전 미기록')+' · '+esc(n.name)+'</p>';
  if(tab==='config'){
    const path=lineage(n.id,definition),tools=definition?.tools || {},skills=definition?.skills || {};
    const skillIds=[...new Set(['common',...path.flatMap(item=>item.skills || [])])];
    const toolHTML=(n.tools || []).map(id=>{
      const tool=tools[id];if(!tool)return '<p>도구 구성 미기록 · '+esc(id)+'</p>';
      return '<article class="ew-detail-config"><h3>'+esc(tool.name || id)+'</h3><dl>'+fact('식별자',id)+fact('역할',tool.purpose || tool.type)+fact('개별 도구 버전',tool.version ?? '미기록')+fact('실행 연결',tool.adapter==='mock'&&tool.source!=='open_webui'?'모의 점검':'실행 연결 필요')+fact('입력 정의',n.bindings?.[id] || tool.input)+fact('업무 판정 기준',tool.success || '미등록')+fact('출력 형식 정의','미기록')+(tool.reference?fact('등록 연결 참조',tool.reference):'')+'</dl></article>';
    }).join('') || '<p>등록된 도구 없음 · '+esc(n.mode==='manual'?'사람 확인':n.mode==='draft'?'초안 검토':'미등록')+'</p>';
    const skillHTML=skillIds.filter(id=>skills[id]).map(id=>{
      const configured=skills[id],allowed=c?.context?.skills?.find(item=>item.id===id || item.reference&&item.reference===configured.reference),external=configured.source==='open_webui';
      const info=allowed || configured;
      const accessible=c?allowed?.available:availableSkills.some(item=>item.id===configured.reference);
      const availability=external&&assetsAvailable===false?'조회 실패':external&&!accessible?'현재 계정 사용 불가':'등록됨';
      return '<article class="ew-detail-config"><h3>'+esc(configured.name || id)+'</h3><dl>'+fact('식별자',id)+fact('역할',configured.purpose || configured.type || '업무 스킬')+fact('상태',availability)+fact('고정본 수정 시각',allowed?.snapshot_updated_at ?? '미기록')+'</dl>'+(!external&&info.body?'<details><summary>등록된 업무 지침</summary><pre>'+esc(info.body)+'</pre></details>':'')+'</article>';
    }).join('');
    const instructions=path.filter(item=>item.instructions).map(item=>'<article class="ew-detail-config"><h3>'+esc(item.name)+'</h3><p>'+esc(item.instructions)+'</p></article>').join('') || '<p>등록된 업무 지침 없음</p>';
    return section(provenance+'<p>설정된 구성입니다. 실제 호출·전달·준수 완료를 뜻하지 않습니다.</p><h2>도구</h2>'+toolHTML+'<h2>스킬</h2>'+skillHTML+'<h2>업무 지침</h2>'+instructions+'<p class="ew-muted">실제 지침 전달·준수 판정은 미기록입니다.</p>');
  }
  if(!records.length)return section(provenance+'<p data-record-state="'+(job.attempt?'unrecorded':'not-executed')+'">'+(job.attempt?'실행 상세 미기록':'미수행 · 실행 기록 없음')+'</p><p>현재 입력이나 설정으로 과거 호출을 채우지 않습니다.</p>');
  const requested=attemptIndex===null?records.length-1:Number(attemptIndex),index=Number.isInteger(requested)&&requested>=0&&requested<records.length?requested:records.length-1;
  const record=records[index],calls=record.checks || [],selected=Math.min(Math.max(0,Number.isInteger(Number(callIndex))?Number(callIndex):0),Math.max(0,calls.length-1)),check=calls[selected];
  const choices='<nav class="ew-detail-attempts" aria-label="실행 선택">'+records.map((item,i)=>button((item.attempt ?? '?')+'차 · '+resultLabel(item.status,item)+' · '+(item.at || '시각 미기록'),'detail_attempt','data-attempt-index="'+i+'" aria-pressed="'+(i===index)+'"')).reverse().join('')+'</nav>';
  const summary='<div class="ew-detail-outcome" data-attempt-index="'+index+'"><strong data-status="'+esc(record.status)+'">'+esc(resultLabel(record.status,record))+'</strong><p>'+esc((record.attempt ?? '?')+'차 · '+(record.at || '실행 시각 미기록'))+'</p><p>'+esc(record.kind==='human_confirmation'?'담당자의 명시적 확인 기록':record.kind==='simulation'||record.simulation?'모의 점검 기록 · 외부 업무 시스템 미호출':'저장된 실행 기록')+'</p></div>';
  const callsHTML=calls.length>1?'<nav class="ew-detail-calls" aria-label="호출 선택">'+calls.map((item,i)=>button((i+1)+'. '+(item.name || item.id || '이름 미기록')+' · '+(item.at || '시각 미기록'),'detail_call','data-call-index="'+i+'" aria-pressed="'+(i===selected)+'"')).join('')+'</nav>':'';
  let body='';
  if(tab==='history')body='<p>이 진행 건의 고정 절차를 적용합니다. 호출별 버전 스냅샷은 미기록입니다.</p>'+(record.detail?'<p>'+esc(record.detail)+'</p>':'')+calls.map((item,i)=>'<article class="ew-check"><h3>'+esc((i+1)+'. '+(item.name || item.id || '점검'))+'</h3><p>'+esc(['blocked','skipped'].includes(item.status)?'미수행':item.status==='passed'?'점검 통과':item.status==='failed'?'점검 실패':'상태 미기록')+'</p><p>'+esc(Object.hasOwn(item,'detail')&&item.detail!==null&&item.detail!==undefined?(item.detail===''?'빈 결과':item.detail):'결과 미기록')+'</p>'+button('입출력 보기','detail_call','data-call-index="'+i+'" data-detail-tab="output"')+'</article>').join('')+(record.kind==='human_confirmation'?'<p>사람 확인 기록이며 도구 호출은 없습니다.</p>'+(record.document?'<h3>확인한 초안</h3><pre>'+esc(record.document)+'</pre>':''):!calls.length?'<p>호출 상세 미기록</p>':'');
  else if(!check){
    body='<p data-record-state="'+(record.kind==='human_confirmation'?'not-executed':'unrecorded')+'">'+(record.kind==='human_confirmation'?'사람 확인 · 도구 호출 없음':'호출 상세 미기록')+'</p>';
    if(record.kind==='human_confirmation'&&tab==='input')body+='<h3>확인 당시 저장 자료</h3><dl>'+Object.entries(record.inputs || {}).filter(([key])=>['db','ap','site','interface'].includes(key)).map(([key,value])=>fact(key,value)).join('')+'</dl>'+(record.document?'<h3>확인한 초안</h3><pre>'+esc(record.document)+'</pre>':'')+'<p>도구에 전달된 입력을 뜻하지 않습니다.</p>';
  }
  else {
    const notCalled=['blocked','skipped'].includes(check.status),simulated=check.simulation===true;
    const recordedText=Object.hasOwn(check,'detail')&&check.detail!==null&&check.detail!==undefined?(check.detail===''?'반환 내용 없음 · 빈 결과':check.detail):'반환 내용 미기록';
    const valueRows=(tab==='input'?Object.hasOwn(check,'input')?[['전달 입력',text(check.input),'data-call-input']]:[]:[['점검 판정',check.status==='passed'?'점검 통과':check.status==='failed'?'점검 실패':'판정 미기록','data-call-verdict'],['기록된 결과',recordedText,'data-call-output']]).map(([label,value,attribute])=>'<tr><th scope="row">'+esc(label)+'</th><td '+attribute+'>'+esc(value)+'</td><td>미기록</td><td>미기록</td></tr>').join('');
    const ioTabs='<nav class="ew-detail-tabs ew-detail-io-tabs" aria-label="호출 입출력">'+tabs.filter(([key])=>['input','output'].includes(key)).map(([key,label])=>button(label,'detail_tab','data-detail-tab="'+key+'" aria-pressed="'+(key===tab)+'"')).join('')+'</nav>';
    const target=!notCalled&&Object.hasOwn(check,'input')?text(check.input):'';
    const identity='<div class="ew-detail-identity"><h2>실행 #'+esc(record.attempt ?? '?')+' · '+esc(n.name)+'</h2><p>'+esc(record.at || '실행 시각 미기록')+(target?' · '+esc(target):'')+'</p><p class="ew-muted">'+esc((simulated?'모의 기록':notCalled?'미수행 기록':'저장된 기록')+' · '+resultLabel(record.status,record)+' · 소요 미기록')+'</p></div>';
    const invocation='<div class="ew-detail-invocation"><h3>'+esc(check.name || check.id || '호출 상세')+'</h3><p>호출 #'+(selected+1)+' · '+(notCalled?'미수행':simulated?'모의 저장값':'호출 상태 미기록')+' · 형식 검사 미기록</p>'+(notCalled?'<p>'+esc(check.detail || '미수행 사유 미기록')+'</p>':'')+'</div>';
    const recorded=notCalled?'<p data-record-state="not-executed">'+(tab==='input'?'전달 입력 없음 · 미수행':'반환 출력 없음 · 미수행')+'</p>':tab==='input'&&!Object.hasOwn(check,'input')?'<p data-record-state="unrecorded">전달 입력 미기록</p>':tab==='output'&&!simulated?'<p data-record-state="unrecorded">반환 출력 미기록</p>':'<section class="ew-detail-fields"><h3>'+(tab==='input'?(simulated?'실제 모의 점검 입력':'기록된 전달 입력'):'기록된 모의 점검 결과')+'</h3><div class="ew-detail-field-scroll"><table><thead><tr><th>항목</th><th>'+(tab==='input'?'전달값':simulated?'모의 반환값':'기록된 반환값')+'</th><th>형식 정의 기록</th><th>형식 검사</th></tr></thead><tbody>'+valueRows+'</tbody></table></div><p class="ew-muted" data-format-check>출력 형식 확인 · 미확인 (검사 기록 없음)</p></section>';
    const verdict='<section class="ew-detail-verdict"><h3 data-status="'+esc(record.status)+'">작업 완료 기준 · '+(record.status==='passed'?'충족':record.status==='failed'?'미충족':'미완료')+'</h3><p>'+esc(n.rule || '완료 기준 미등록')+'</p></section>';
    const recordedConfig='<section class="ew-detail-record-config"><h3>적용 절차와 호출 당시 기록</h3><dl>'+fact('적용 절차',version===undefined?'미기록':'v'+version+' · 진행 건에 고정된 정의')+fact('도구 식별자',check.id ?? '미기록')+fact('호출 고유 ID','미기록')+fact('개별 도구 버전','미기록')+fact('기록 시각',check.at ?? '미기록')+fact('스킬 제공','미기록')+fact('지침 제공','미기록')+'</dl><p class="ew-muted">고정 절차와 호출 당시 제공·준수 기록은 다릅니다. 없는 기록은 채우지 않습니다.</p>'+button('사용 구성 보기','detail_tab','data-detail-tab="config"')+'</section>';
    return '<section class="ew-detail-call-view" data-work-detail-content="'+tab+'" data-attempt-index="'+index+'" data-record-kind="'+(simulated?'모의 기록':notCalled?'미수행':'저장된 기록')+'">'+identity+invocation+ioTabs+recorded+verdict+recordedConfig+'<p class="ew-muted">'+(tab==='input'?'입력 출처·이전 출력 연결 기록 · 미기록':'도구 정상 반환 여부 · 미기록 · 외부 도구 원시 응답 · '+(simulated||notCalled?'미호출':'미기록'))+'</p>'+callsHTML+choices+'</section>';
  }
  return nav+provenance+choices+callsHTML+'<section data-work-detail-content="'+tab+'">'+summary+body+'</section>';
}

/* Session-only drafts never update a server snapshot or completed evidence. */
function createWorkInputDrafts() {
  const entries=new Map(),copy=value=>JSON.parse(JSON.stringify(value));
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function edit(scope,saved,patch,revision) {
    const entry=entries.get(scope.key) || {scope:copy(scope),base:copy(saved),revision,inputs:{}};
    if(patch.replaceInputs){entry.inputs=copy(patch.inputs || {});entry.replaceInputs=true;}
    else if(patch.inputs)Object.assign(entry.inputs,patch.inputs);
    if(Object.hasOwn(patch,'document'))entry.document=patch.document;
    entries.set(scope.key,entry);
  }
  function read(scope,saved,revision) {
    const entry=entries.get(scope.key);
    if(!entry)return {nodeId:scope.nodeId,caseId:scope.caseId || '',revision,inputs:{...saved.inputs},inputsChanged:false,document:saved.document,documentChanged:false,conflict:false};
    if(entry.replaceInputs){
      const inputsChanged=!same(entry.inputs,saved.inputs),documentChanged=Object.hasOwn(entry,'document')&&!same(entry.document,saved.document);
      // A full schema form owns its complete value set. Any server input
      // change must conflict, including an otherwise untouched sibling field.
      const conflict=(inputsChanged&&!same(saved.inputs,entry.base.inputs))||(documentChanged&&!same(saved.document,entry.base.document))||((inputsChanged||documentChanged)&&!scope.caseId&&scope.version!==entry.scope.version);
      if(!inputsChanged&&!documentChanged)entries.delete(scope.key);
      return {nodeId:scope.nodeId,caseId:scope.caseId || '',revision:conflict?entry.revision:revision,definitionVersion:entry.scope.version,inputs:copy(entry.inputs),inputsChanged,document:documentChanged?entry.document:saved.document,documentChanged,conflict};
    }
    for(const key of Object.keys(entry.inputs))if(same(entry.inputs[key],saved.inputs[key]))delete entry.inputs[key];
    if(Object.hasOwn(entry,'document')&&same(entry.document,saved.document))delete entry.document;
    const inputsChanged=Boolean(Object.keys(entry.inputs).length),documentChanged=Object.hasOwn(entry,'document');
    const conflict=Object.keys(entry.inputs).some(key=>!same(saved.inputs[key],entry.base.inputs[key]))||(documentChanged&&!same(saved.document,entry.base.document))||((inputsChanged||documentChanged)&&!scope.caseId&&scope.version!==entry.scope.version);
    if(!inputsChanged&&!documentChanged)entries.delete(scope.key);
    return {nodeId:scope.nodeId,caseId:scope.caseId || '',revision:conflict?entry.revision:revision,definitionVersion:entry.scope.version,inputs:{...saved.inputs,...entry.inputs},inputsChanged,document:documentChanged?entry.document:saved.document,documentChanged,conflict};
  }
  function adopt(from,to){const entry=entries.get(from.key);if(entry){entries.delete(from.key);entry.scope=copy(to);entries.set(to.key,entry);}}
  function adoptPreview(from,caseId){
    for(const entry of [...entries.values()]){
      const scope=entry.scope;
      if(scope.caseId||!['siteId','system','processId','version'].every(key=>scope[key]===from[key]))continue;
      const to={...scope,caseId};to.key=JSON.stringify([caseId,to.siteId,to.system,to.processId,to.nodeId]);adopt(scope,to);
    }
  }
  function rebase(scope,saved,revision){const entry=entries.get(scope.key);if(entry){entry.scope=copy(scope);entry.base=copy(saved);entry.revision=revision;}}
  return Object.freeze({edit,read,adopt,adoptPreview,rebase,discard:scope=>entries.delete(scope.key),clear:()=>entries.clear()});
}

/* Owns display state and DOM; server snapshots are copied and never mutated. */
// Pure renderers consume stored execution evidence; this browser never dispatches a job loop.
function workHasExecution(definition,id,seen=new Set()) {
  const node=definition?.nodes?.[id];if(!node||seen.has(id))return false;seen.add(id);
  return Boolean(node.execution)||(node.children || []).some(child=>workHasExecution(definition,child,seen));
}
function workLegacyExecutionLocked(execution,caseId) {
  // The existing service blocks legacy writes for every nonterminal run in
  // this case, including waits and UNKNOWN; another case never locks it.
  return Boolean(caseId&&[execution?.run,...(execution?.runs || [])].some(run=>run?.case_id===caseId&&!['succeeded','failed','cancelled'].includes(run.status)));
}
function workExecutionInputsHTML(schema={},values={}) {
  const {esc}=workUI,required=new Set(schema.required || []);
  return Object.entries(schema.properties || {}).map(([key,field])=>{
    const value=values[key],attrs=' name="'+esc(key)+'" data-execution-input'+(required.has(key)?' required':'');
    let control;
    if(field.enum)control='<select'+attrs+'><option value="">선택해 주세요</option>'+field.enum.map(item=>'<option value="'+esc(JSON.stringify(item))+'" '+(JSON.stringify(value)===JSON.stringify(item)?'selected':'')+'>'+esc(String(item))+'</option>').join('')+'</select>';
    else if(field.type==='boolean')control='<select'+attrs+'><option value="">선택해 주세요</option><option value="true" '+(value===true?'selected':'')+'>예</option><option value="false" '+(value===false?'selected':'')+'>아니요</option></select>';
    else if(['array','object'].includes(field.type))control='<textarea'+attrs+' rows="3" maxlength="12000" placeholder="'+esc(field.type==='array'?'["항목"]':'{"항목":"값"}')+'">'+esc(value===undefined?'':JSON.stringify(value,null,2))+'</textarea>';
    else control='<input'+attrs+' type="'+(field.type==='integer'?'number':'text')+'" '+(field.type==='integer'?'step="1"':'maxlength="'+(field.maxLength || 2000)+'"')+' value="'+esc(value ?? '')+'">';
    return '<label><span class="ew-input-field-name">'+esc(field.title || key)+(required.has(key)?' · 필수':'')+'</span><div class="ew-v4-input-control">'+control+(field.description?'<small>'+esc(field.description)+'</small>':'')+'</div></label>';
  }).join('');
}
function workExecutionInputsRead(form,schema={}) {
  const values=new FormData(form),result={};
  for(const [key,field] of Object.entries(schema.properties || {})){
    const raw=values.get(key);if(raw===null||raw==='')continue;
    const value=field.enum||['boolean','array','object'].includes(field.type)?JSON.parse(raw):field.type==='integer'?Number(raw):String(raw);
    if(field.type==='integer'&&!Number.isSafeInteger(value))throw new Error((field.title || key)+'에 정수를 입력해 주세요.');
    result[key]=value;
  }return result;
}
function workExecutionStatus(status) {
  return ({unstarted:'시작 전',pending:'대기',in_progress:'진행 중',blocked:'진행 조건 확인',skipped:'적용 제외',passed:'완료',queued:'접수됨',running:'실행 중',waiting_input:'입력 필요',waiting_authorization:'권한·연결 확인',waiting_dependency:'선행 대기',paused:'일시 중지',unknown:'판정 미확인',succeeded:'완료',failed:'실패',cancelled:'취소됨'})[status] || status || '미기록';
}
function workExecutionReason(reason) {
  return ({verified_complete:'완료 조건을 충족했습니다.',required_jobs_verified:'범위의 필수 작업과 최종 완료 조건을 확인했습니다.',grounded_observations:'저장된 근거에서 확인한 관찰값입니다.',observed_limited:'일부 범위의 결과입니다. 전체 범위 완료와 구분해 주세요.',prerequisite_required:'선행 작업의 확인 결과가 필요합니다.',input_required:'필요한 입력을 보완한 뒤 이어가기를 선택해 주세요.',invalid_inputs:'입력 형식을 확인해 주세요.',invalid_selection:'조회된 후보 중에서 선택해 주세요.',result_reference_missing:'연결할 선행 결과를 먼저 확인해 주세요.',human_confirmation_required:'완료 조건과 자료를 직접 확인해 주세요.',human_input_confirmed:'담당자가 공개 입력을 확인했습니다.',human_confirmation_declined:'입력된 확인 값이 완료 조건을 충족하지 않습니다.',pause_requested:'요청에 따라 다음 호출을 멈췄습니다.',human_confirmed:'담당자 확인을 저장했습니다. 이어가기를 선택해 주세요.',timeout:'요청의 결과를 확정하지 못했습니다. 자동으로 다시 실행하지 않습니다.',cancelled_before_dispatch:'다음 호출을 취소했습니다. 이전 호출 기록은 보존됩니다.',cancellation_unconfirmed:'이미 보낸 요청의 취소 여부는 미확정입니다.',approval_required:'관리자의 기능 승인을 확인해 주세요.',approval_invalid:'승인된 기능과 현재 버전이 일치하는지 확인해 주세요.',approval_stale:'기능 변경에 대한 관리자 재검토가 필요합니다.',asset_forbidden:'현재 계정의 기능 접근 권한을 확인해 주세요.',tool_forbidden:'현재 계정의 기능 접근 권한을 확인해 주세요.',skill_unavailable:'현재 계정의 필수 스킬 접근 권한을 확인해 주세요.',user_valves_required:'기존 기능의 개인 연결 설정을 확인해 주세요.',execution_expired:'허용 실행 시간이 만료됐습니다. 기존 기록을 확인해 주세요.',call_limit_reached:'허용 호출 수에 도달했습니다. 기존 기록을 확인해 주세요.',result_missing:'호출 결과가 기록되지 않아 완료를 판정할 수 없습니다.',completeness_missing:'반환 결과의 범위가 미기록되어 완료를 판정할 수 없습니다.',final_condition_missing:'범위의 최종 완료 조건을 확인할 수 없습니다.',child_final_incomplete:'하위 단계의 최종 완료 조건을 충족하지 않았습니다.',required_jobs_incomplete:'필수 작업의 완료 검증이 남아 있습니다.',source_scope_limited:'근거가 일부 범위에 한정되어 전체 완료로 판정하지 않습니다.',summary_missing:'AI 결과가 기록되지 않아 완료를 판정할 수 없습니다.',call_failed:'호출이 실패했습니다. 저장된 사유와 기록을 확인해 주세요.',call_unknown:'호출 결과를 확정할 수 없습니다. 자동으로 다시 실행하지 않습니다.'})[reason] || '저장된 사유를 확인하고 필요한 조건을 보완해 주세요.';
}
function workExecutionForNode(execution,nodeId,definition) {
  if(!execution)return null;
  const selected=definition?.nodes?.[nodeId];
  const ids=selected?new Set(selected.type==='j'?[nodeId]:workNavigationLeaves(definition,selected).map(node=>node.id)):null;
  const candidates=[execution.run,...(execution.runs || [])].filter(Boolean);
  const run=candidates.find(item=>!ids||Object.keys(item.jobs || {}).some(id=>ids.has(id)));
  return run?{...execution,run}:null;
}
function workExecutionObservationsHTML(claims,definition) {
  const {esc}=workUI,groups=new Map();
  const labels={summary:'집계',pagination:'페이지',page:'문서',total:'전체',open:'열림',returned:'반환 수',has_next:'다음 페이지',title:'제목',version:'버전'};
  for(const claim of claims){const id=claim.source?.job_id || '';if(!groups.has(id))groups.set(id,[]);groups.get(id).push(claim);}
  return [...groups].map(([id,items])=>'<section><h4>'+esc(definition?.nodes?.[id]?.name || id || '근거 이름 미기록')+'</h4>'+items.map(claim=>{
    const path=(claim.path || []).filter(part=>part!=='data').map(part=>labels[part] || String(part)).join(' / ') || '관찰값';
    const value=typeof claim.value==='boolean'?(claim.value?'예':'아니요'):typeof claim.value==='string'?claim.value:JSON.stringify(claim.value ?? '미기록');
    return '<div class="ew-work-target-row" data-runtime-observation><span>'+esc(path)+'</span><p>'+esc(value)+'</p></div>';
  }).join('')+'</section>').join('');
}
function workExecutionRuntimeHTML(execution,{nodeId='',definition,readOnly=false,history=false,error=null,case:c=null,applicable=true,mixedScope=false,planButton='',suppressInputs=false}={}) {
  const {esc,button}=workUI,node=definition?.nodes?.[nodeId],isJob=node?.type==='j';
  const actionRegion=(controls,note='')=>controls?'<section class="ew-work-execute ew-work-action-region" data-work-stage="execute" aria-label="실행과 다음 행동"><div class="ew-work-actions">'+controls+'</div>'+(note?'<p class="ew-work-action-note">'+esc(note)+'</p>':'')+'</section>':'';
  // Fail closed before looking at any retained response or snapshot.
  if(error)return '<section class="ew-work-result" data-runtime-record="lookup-failed"><h3>실행 기록 조회 실패</h3><p role="alert">'+esc(error)+'</p><p>현재 기록을 확인할 수 없습니다. 이전 응답을 결과로 표시하지 않습니다.</p></section>'+(!history?actionRegion(button('다시 조회','execution_refresh'),'현재 접근 권한과 저장 기록을 다시 확인합니다.'):'');
  const run=execution?.run,scope=workUI.lineage(nodeId,definition)[0],schema=run?.input_schema || scope?.execution_inputs || {},values=run?.inputs || c?.execution_inputs || {};
  const fields=Object.entries(schema.properties || {}),fact=value=>esc(typeof value==='string'?value:JSON.stringify(value ?? '미기록',null,2));
  const currentInputs=!suppressInputs&&fields.length?'<section class="ew-work-target" data-work-section="runtime-inputs"><h3>'+(run?'현재 실행 입력':'공개 입력')+'</h3>'+fields.map(([key,field])=>'<div class="ew-work-target-row"><span>'+esc(field.title || key)+'</span><p>'+esc(Object.hasOwn(values,key)?typeof values[key]==='string'?values[key]:JSON.stringify(values[key]):'계획 확인에서 입력')+'</p></div>').join('')+'<p class="ew-muted">'+(run?'이 실행에 저장된 현재 입력입니다. 호출 당시 전달값은 수행 상세에서 확인하세요.':'실행 계획에서 입력과 범위를 확인합니다. 입력만으로는 실행되거나 저장되지 않습니다.')+'</p></section>':'';
  const rule='<div class="ew-work-criterion"><span>완료 조건</span><p>'+esc(node?.rule || '저장된 완료 검증을 확인해 주세요.')+'</p></div>';
  const mixedNotice=mixedScope?'<p class="ew-notice" data-runtime-mixed-scope>모의 업무와 연결 실행이 함께 있는 범위입니다. 전체를 한 실행으로 진행할 수 없습니다. 목록에서 같은 수행 방식의 단계 또는 개별 작업을 선택하세요.</p>':'';
  if(!run)return '<section class="ew-work-result" data-runtime-record="unrecorded" data-work-recorded="false"><h3>확인할 내용</h3><p class="ew-work-current-title">'+(applicable?'아직 수행한 결과가 없습니다.':'현재 범위에서 적용 제외입니다.')+'</p><p class="ew-muted">'+(applicable?'실행 계획 확인은 조회입니다. 계획에서 명시적으로 시작해야 서버가 실행합니다.':'적용 조건에 맞는 공장·시스템에서 확인해 주세요.')+'</p>'+rule+'</section>'+mixedNotice+currentInputs+actionRegion(!readOnly&&applicable?planButton:'','범위·공개 입력·현재 권한을 확인한 뒤 실행합니다.');
  const ids=node?new Set(isJob?[nodeId]:workNavigationLeaves(definition,node).map(item=>item.id)):null;
  const jobs=Object.entries(run.jobs || {}).filter(([id])=>!ids||ids.has(id)),calls=(run.calls || []).filter(call=>!ids||ids.has(call.job_id));
  const job=isJob?run.jobs?.[nodeId]:null,validation=isJob?job?.validation:run.node_id===nodeId?run.final_validation:c?.execution_final_validations?.[nodeId];
  // A completed child execution is not a completed parent scope. Its stored
  // projection/final validator remains the source of the P/T status.
  const status=isJob?job?.status || 'pending':!nodeId||run.node_id===nodeId?run.status:validation?.status || c?.node_states?.[nodeId]?.status || 'pending';
  const evidenceAvailable=run.evidence_available!==false,terminal=['succeeded','failed','cancelled'].includes(run.status),uncertain=run.status==='unknown'||Object.values(run.jobs || {}).some(item=>item.status==='unknown'||item.validation?.status==='unknown')||(run.calls || []).some(call=>call.status==='unknown');
  const moving=['queued','running'].includes(run.status),editable=!readOnly&&!terminal&&!uncertain,complete=validation?.status==='succeeded'&&(isJob||validation?.scope_complete!==false);
  const control=(label,action,attrs='')=>button(label,'execution_control','data-runtime-action="'+action+'" data-run-id="'+esc(run.id)+'" data-revision="'+esc(run.revision)+'" data-mutation '+attrs);
  const confirms=jobs.filter(([,item])=>item.kind==='human'&&item.status==='waiting_input'&&item.reason==='human_confirmation_required');
  let controls='';
  if(editable){
    if(!moving&&fields.length)controls+=control('입력 확인','inputs','class="'+(run.status==='waiting_input'?'ew-primary':'')+'"');
    if(moving)controls+=control('일시 중지','pause','class="ew-primary"');
    else if(confirms.length)controls+=confirms.map(([id])=>{const key=definition?.nodes?.[id]?.execution?.completion?.input_key,missing=key&&!Object.hasOwn(values,key);return control('내용을 확인했습니다','confirm','data-job-id="'+esc(id)+'" class="'+(!missing?'ew-primary':'')+'"'+(missing?' disabled data-unavailable="true"':''));}).join('');
    else controls+=control('이어가기','resume',run.status==='waiting_input'&&fields.length?'':'class="ew-primary"');
    controls+=control('실행 취소','cancel');
  }
  const parent=node?.parent&&definition?.nodes?.[node.parent];
  if(!history&&isJob&&job?.status==='succeeded'&&parent)controls=button(parent.type==='t'?'단계로 돌아가기':'상위 업무로 돌아가기','panel_parent','data-node-id="'+esc(parent.id)+'" class="ew-primary ew-work-link"')+controls;
  else if(!readOnly&&!uncertain&&terminal&&applicable)controls+=planButton;
  const reason=isJob?job?.reason:!nodeId||run.node_id===nodeId?run.reason:validation?.reason,notice=uncertain?'미확정 결과는 자동 재실행하지 않습니다. 저장 기록과 원래 요청의 결과를 확인해 주세요.':moving?'접수 후에는 서버가 진행합니다. 화면을 닫아도 취소되지 않습니다. 중지·취소는 이후 호출에 적용됩니다.':editable?'입력 보완과 확인은 각각 저장됩니다. 이어가기를 눌러 다음 호출을 진행하세요.':terminal?'이 실행의 기록은 보존됩니다. 호출 성공과 업무·범위의 완료 판정은 구분됩니다.':'';
  const summary=jobs.map(([id,item])=>'<div><span>'+esc(definition?.nodes?.[id]?.name || id)+'</span><p>'+esc(item.reason?workExecutionReason(item.reason):item.status==='pending'?'아직 수행한 결과가 없습니다.':workExecutionStatus(item.status))+'</p><span class="ew-badge" data-status="'+esc(item.status)+'">'+esc(workExecutionStatus(item.status))+'</span></div>').join('');
  const claims=evidenceAvailable&&Array.isArray(job?.result?.claims)?'<div class="ew-work-observations">'+workExecutionObservationsHTML(job.result.claims,definition)+(job.result.limitations?.length?'<p>결과의 한계</p><ul>'+job.result.limitations.map(item=>'<li>'+fact(item)+'</li>').join('')+'</ul>':'')+(job.result.notice?'<p class="ew-muted">'+esc(job.result.notice)+'</p>':'')+'</div>':'';
  const partial=calls.some(call=>call.result?.completeness==='partial'||call.result?.completeness==='truncated');
  const result='<section class="ew-work-result" data-runtime-record="'+esc(run.status)+'" data-work-recorded="'+Boolean(validation)+'"><h3>확인 결과</h3>'+(history?'<p class="ew-muted">실행 대상 · '+esc(definition?.nodes?.[run.node_id]?.name || run.node_id || '미기록')+'</p>':'')+'<p class="ew-work-current-title" role="status">'+esc(workExecutionStatus(status))+(partial?' · 일부 범위 결과':'')+'</p>'+(reason?'<p>'+esc(workExecutionReason(reason))+'</p>':'')+(!evidenceAvailable?'<p class="ew-notice" role="status">현재 권한으로 결과 근거를 볼 수 없습니다. 이전 자료를 표시하지 않습니다.</p>':'<div class="ew-work-check-summary">'+summary+'</div>'+claims)+'<div class="ew-work-criterion" data-work-criterion-status="'+(complete?'passed':validation?'failed':'pending')+'"><span>완료 조건</span><p>'+esc(!evidenceAvailable?'근거 접근 제한 · 완료 판정 상세 확인 불가':complete?'충족':validation?'미충족 · 전체 범위 완료 아님':'아직 판정하지 않음')+' · '+esc(node?.rule || '저장된 완료 검증을 확인해 주세요.')+'</p></div>'+(run.node_id&&run.node_id!==nodeId?'<p class="ew-muted">실행 범위 · '+esc(definition?.nodes?.[run.node_id]?.name || run.node_id)+(readOnly?'':' · 아래 제어는 이 실행 범위에 적용됩니다.')+'</p>':'')+'</section>';
  const details='<details class="ew-work-runtime-detail" data-runtime-run="'+esc(run.id)+'"><summary data-work-overlay="'+esc(node?.name || '업무')+' · 수행 상세">수행 상세 보기 · '+calls.length+'개 호출</summary><h3>저장된 실행</h3><p>'+esc(run.id)+' · r'+esc(run.revision)+' · '+esc(workExecutionStatus(run.status))+'</p><p>사유 · '+fact(run.reason)+'</p><h4>현재 실행 입력</h4><pre>'+fact(run.inputs)+'</pre><p>현재 입력과 아래 호출 당시의 전달값은 서로 다른 기록입니다.</p>'+jobs.map(([id,item])=>'<section><h4>'+esc(definition?.nodes?.[id]?.name || id)+' · '+esc(workExecutionStatus(item.status))+'</h4><p>'+esc(({fixed:'자동 조회',ai:'AI 작업',human:'사람 확인'})[item.kind] || '수행 방식 미기록')+'</p>'+(evidenceAvailable?'<h5>업무 완료 검증</h5><pre>'+fact(item.validation)+'</pre><h5>확정 결과</h5><pre>'+fact(item.result)+'</pre>':'<p>현재 권한으로 근거에 접근할 수 없습니다.</p>')+'</section>').join('')+(evidenceAvailable?'<h4>범위 최종 검증</h4><pre>'+fact(run.final_validation)+'</pre>':'')+'<h3>실제 호출·반환 기록 '+calls.length+'건</h3>'+(calls.length?calls.map(call=>'<article class="ew-detail-config"><h4>'+esc(call.reference?.function || call.function || call.id)+'</h4><p>'+esc(workExecutionStatus(call.status))+' · '+fact(call.result?.provenance || call.provenance || '기록된 환경 범위를 확인해 주세요')+'</p>'+(evidenceAvailable&&call.evidence_available!==false?'<h5>참조·버전</h5><pre>'+fact(call.reference)+'</pre><h5>전달 입력·연결 · 호출 당시 snapshot</h5><pre>'+fact(call.arguments)+'</pre><pre>'+fact(call.bindings || call.input_sources)+'</pre><h5>정규화 결과·검증</h5><pre>'+fact(call.result)+'</pre><pre>'+fact(call.checks || call.validation)+'</pre>':'<p>현재 권한으로 이 호출의 입력·결과를 볼 수 없습니다.</p>')+'</article>').join(''):'<p>호출 기록 없음 · 실제 호출 완료를 의미하지 않습니다.</p>')+'</details>';
  const links='<nav class="ew-work-detail-links" aria-label="실행 자료">'+details+(!history?button('상태 다시 조회','execution_refresh'):'')+'</nav>';
  return result+mixedNotice+(!controls&&notice?'<p class="ew-notice">'+esc(notice)+'</p>':'')+currentInputs+actionRegion(controls,notice)+links+'<p class="ew-muted ew-work-runtime-boundary">미확정·대기는 완료가 아닙니다. 일부 범위 결과를 전체 범위 완료로 해석하지 마세요. 조회 자동화는 Windows 설치 완료를 의미하지 않습니다.</p>';
}

function workV4Icon(name) {
  const icons={"panel-right":["a9175.svg",16,16],"chevron-down":["92ec5.svg",16,16],"list-checks":["4df0d.svg",16,16],"compass":["2e769.svg",16,16],"history":["c325d.svg",16,16],"message":["093d6.svg",16,16],"chevron-down-14":["e1049.svg",14,14],"package":["f6bbc.svg",16,16],"activity":["126c7.svg",16,16],"chevron-right":["69549.svg",14,14],"triangle-alert":["4fb09.svg",16,16],"Ellipse":["07d31.svg",6,6],"settings":["88026.svg",16,16],"file-text":["730b1.svg",16,16],"more":["a953c.svg",16,16],"search":["b8bc6.svg",14,14],"plus":["721d7.svg",16,16],"panel-right-16":["7bb4a.svg",16,16],"file-text-12":["522b5.svg",12,12],"x":["87d9b.svg",12,12],"message-14":["cf77a.svg",14,14],"paperclip":["ea639.svg",16,16],"chevron-down-12":["34f85.svg",12,12],"arrow-up":["bddb4.svg",16,16],"arrow-left":["eb94a.svg",14,14],"Ellipse-6":["e1472.svg",6,6],"Action":["9c63b.svg",16,16],"Failed":["44a96.svg",16,16],"Running":["49833.svg",16,16],"Waiting":["40ef1.svg",16,16],"Done":["d553d.svg",16,16],"Unknown":["d448c.svg",16,16]};
  const asset=icons[name];
  return asset?'<img class="ew-v4-icon" src="/_ees12/v4/'+asset[0]+'" width="'+asset[1]+'" height="'+asset[2]+'" alt="" aria-hidden="true">':'';
}

function createWorkView({callbacks}) {
  const {$, esc, clone, categories, levels, statuses, badge, button, finished, siteLabel} = workUI;
  let snapshot = {}, state = null, category = 'setup', browsingSystem = 'EMS', browsingSite = '', browseNodeId = '', runView = 'current', historyCase = null, errorMessage = '', busy = false;
  let serverSource=null,historySource=null;
  let navOpen = true, scopePicker = '', host = null, divider = null, panelOpen = false, width = 0, preferredWidth = null, panelInfo = null, drag = null, styledColumn = null;
  // Expansion belongs to the factory scope and the retained case version.
  const treeExpansions = new Map(),jobDrafts=createWorkInputDrafts(),jobLists=new Map(),stepSummaries=createWorkStepSummaries(),selectedSteps=new Map();
  let renderedEditContext=null,renderedPanelTarget='',pendingReturn=null,detailContext=null,runtimeDetailContext=null,actionLayoutKey='';
  const panelPositions=new Map(),panelDisclosures=new Map(),navigationTrail=[];
  const aiReceipts=new Map(),runtimeRawInputs=new Map(),runtimeInputErrors=new Map(),draftVersions=new Map();
  let assistantOpen=true,historyNavOpen=false;
  const chatId = () => snapshot.chatId || '';
  const chatRoute = () => Boolean(snapshot.chatRoute);
  const currentCase = () => state?.case;
  const selectedCase = () => snapshot.selectedCaseId&&state?.case?.id===snapshot.selectedCaseId?state.case:null;
  const selectedId = () => snapshot.selectedId || '';
  const definition = () => selectedCase()?.definition || state?.catalog;
  const jobListKey = () => JSON.stringify([selectedCase()?.id || '',browsingSite,browsingSystem,definition()?.version,selectedId()]);
  const jobListState = () => jobLists.get(jobListKey()) || {};
  function updateJobList(patch,renderNow=true) {jobLists.set(jobListKey(),{...jobListState(),...patch});if(renderNow)renderPanel();}
  const node = id => definition()?.nodes?.[id];
  const status = id => selectedCase()?.node_states?.[id] || {};
  const nameOf = id => node(id)?.name || id;
  const lineage = (id, data = definition()) => workUI.lineage(id, data);
  const alertHTML = () => errorMessage ? `<p class="ew-error" role="alert">${esc(errorMessage)}</p>` : '';
  const processId = () => snapshot.processId || '';
  const scopeCases = id => (state?.cases || []).filter(c=>c.site?.id===browsingSite&&c.system===browsingSystem&&(!id||c.process_id===id));
  const visibleRoots = group => snapshot.roots?.[group] || [];
  const chosenCase = id => state?.cases?.find(c=>c.id===snapshot.chosenCases?.[id]) || null;
  const expansionKey = (data, run, scope = {site:browsingSite,system:browsingSystem}) => JSON.stringify([scope.site,scope.system,run?.id || '',run?.version || data?.version || state?.catalog?.version]);
  function expansionState(key) {if(!treeExpansions.has(key))treeExpansions.set(key,new Map());return treeExpansions.get(key);}
  function revealSelection(id,data,run,includeSelf=false,scope) {
    const branches=expansionState(expansionKey(data,run,scope));
    lineage(id,data).forEach(n=>{if(n.children?.length&&(includeSelf||n.id!==id)&&!branches.has(n.id))branches.set(n.id,true);});
  }
  function toggleBranch(id,key,data) {
    const branches=expansionState(key),open=!branches.get(id);branches.set(id,open);
    // Reopening a parent shows one level, even when its selected job is hidden.
    if(!open){const pending=[...(data?.nodes[id]?.children || [])],seen=new Set();while(pending.length){const child=pending.pop();if(seen.has(child))continue;seen.add(child);branches.set(child,false);pending.push(...(data.nodes[child]?.children || []));}}
  }
  function runLabel(c) {const list=scopeCases(c.process_id),order=list.findIndex(item=>item.id===c.id);return ['실행 '+(order>=0?list.length-order:'기록'),c.created_at?c.created_at.replace('T',' ').slice(0,19)+' UTC':'생성 시각 미기록', c.process_name || c.definition?.nodes[c.process_id]?.name || state?.catalog?.nodes[c.process_id]?.name || '업무', 'v'+c.version].join(' · ');}
  function editContext(id,caseOverride) {
    const c=caseOverride || selectedCase(),data=c?.definition || state?.catalog,n=data?.nodes?.[id];
    if(!n||n.type!=='j')return null;
    const site=c?.site || data.sites?.[browsingSite],system=c?.system || browsingSystem;
    const caseId=c?.id || '',process=workUI.lineage(id,data)[0]?.id || '',version=c?.version || data.version;
    const runtime=Boolean(n.execution),schema=runtime?data.nodes[process]?.execution_inputs || {properties:{}}:null;
    const fields=runtime?Object.keys(schema.properties || {}):Array.from(new Set((n.tools || []).map(tool=>n.bindings?.[tool] || data.tools?.[tool]?.input).filter(key=>['db','ap','site','interface'].includes(key))));
    const all=runtime?{...Object.fromEntries(Object.entries(schema.properties || {}).filter(([,field])=>Object.hasOwn(field,'default')).map(([key,field])=>[key,field.default])),...(c?.execution_inputs || {})}:{db:site?.db || '',ap:site?.ap || '',site:[site?.country,site?.name,site?.line].filter(Boolean).join(' · '),interface:site?.interface?system+' · '+site.name+' 시스템 간 연계 · 예시':'',...(c?.jobs?.[id]?.inputs || {})};
    const scope={caseId,nodeId:id,siteId:site?.id || browsingSite,system,processId:process,version};
    scope.key=JSON.stringify([caseId,scope.siteId,system,process,id]);
    return {scope,saved:{inputs:Object.fromEntries(fields.filter(key=>Object.hasOwn(all,key)).map(key=>[key,all[key]])),document:c?.jobs?.[id]?.document || ''},revision:c?.revision ?? -1,hasInputs:fields.length>0,hasDocument:!runtime&&n.mode==='draft',runtime,schema};
  }

  function captureJobEdits(changedField=null) {
    if(host&&renderedPanelTarget)panelDisclosures.set(renderedPanelTarget,new Map(Array.from(host.querySelectorAll('#ees-work-content details')).map(el=>[el.className+'|'+(el.querySelector(':scope > summary')?.textContent || ''),el.open])));
    if(!renderedEditContext||!host)return;
    const inputs=host.querySelector('#ees-work-inputs'),documentForm=host.querySelector('#ees-work-document'),patch={};
    if(changedField)draftVersions.set(renderedEditContext.scope.key,(draftVersions.get(renderedEditContext.scope.key)||0)+1);
    if(inputs){
      const controls=Array.from(inputs.querySelectorAll('input,textarea,select'));
      if(renderedEditContext.runtime){
        if(changedField&&inputs.contains(changedField))runtimeRawInputs.set(renderedEditContext.scope.key,Object.fromEntries(controls.map(field=>[field.name,field.value])));
        if(runtimeRawInputs.has(renderedEditContext.scope.key)){
          try {patch.inputs=workExecutionInputsRead(inputs,renderedEditContext.schema);patch.replaceInputs=true;runtimeInputErrors.delete(renderedEditContext.scope.key);} catch (error) {runtimeInputErrors.set(renderedEditContext.scope.key,error.message);return;}
        }
      }else{
        const changed=controls.filter(field=>field===changedField||field.value!==field.defaultValue);
        if(changed.length)patch.inputs=Object.fromEntries(changed.map(field=>[field.name,field.value]));
      }
    }
    const text=documentForm?.querySelector('textarea');if(text&&(text===changedField||text.value!==text.defaultValue))patch.document=text.value;
    if(patch.inputs||Object.hasOwn(patch,'document'))jobDrafts.edit(renderedEditContext.scope,renderedEditContext.saved,patch,renderedEditContext.revision);
  }

  function draftFor(context) {
    if(!context)return null;
    const draft=jobDrafts.read(context.scope,context.saved,context.revision),receipt=aiReceipts.get(context.scope.key);
    if(receipt)draft.aiReceipt={proposalId:receipt.proposalId,source:receipt.source,changedFields:receipt.changedFields,undone:receipt.undone};
    if(runtimeInputErrors.has(context.scope.key)){draft.inputError=runtimeInputErrors.get(context.scope.key);draft.inputsChanged=true;}
    if(!draft.inputsChanged)runtimeRawInputs.delete(context.scope.key);
    if(context.runtime&&runtimeRawInputs.has(context.scope.key))draft.rawInputs=runtimeRawInputs.get(context.scope.key);
    return draft;
  }

  function adoptPreviewDraft(caseId,nodeId) {
    if(typeof caseId!=='string'||!caseId||!nodeId)return;
    captureJobEdits();
    const data=definition(),n=data?.nodes?.[nodeId];if(!n)return;
    const scope={siteId:browsingSite,system:browsingSystem,processId:workUI.lineage(nodeId,data)[0]?.id,version:data.version,caseId:''};
    // All drafts of this exact preview become drafts of its first case, even
    // when first execution was requested from its parent process or task.
    jobDrafts.adoptPreview(scope,caseId);
    for(const values of [runtimeRawInputs,runtimeInputErrors,draftVersions,aiReceipts])for(const [key,value] of [...values]){
      const parts=JSON.parse(key);
      if(parts[0]===''&&parts[1]===scope.siteId&&parts[2]===scope.system&&parts[3]===scope.processId){
        parts[0]=caseId;const next=JSON.stringify(parts);
        if(!values.has(next))values.set(next,value);
        values.delete(key);
      }
    }
  }
  function draftVersion(id=selectedId()) {
    captureJobEdits();const context=editContext(id);return context?draftVersions.get(context.scope.key)||0:0;
  }
  function aiContext(proposal) {
    captureJobEdits();
    const context=editContext(proposal.nodeId);
    if(!context||busy||runView!=='current'||snapshot.recordLookupError||snapshot.executionError||proposal.nodeId!==selectedId()||String(proposal.caseId || '')!==context.scope.caseId||proposal.revision!==context.revision||finished(selectedCase()))return null;
    if(workLegacyExecutionLocked(snapshot.execution,context.scope.caseId))return null;
    if(draftFor(context)?.conflict||runtimeInputErrors.has(context.scope.key))return null;
    return context;
  }
  function applyAIDraft(proposal) {
    const context=aiContext(proposal);if(!context)return {ok:false,code:'draft_target_changed'};
    if(!Number.isInteger(proposal.expectedDraftVersion)||proposal.expectedDraftVersion!==(draftVersions.get(context.scope.key)||0))return {ok:false,code:'draft_changed'};
    if(typeof proposal.proposalId!=='string'||!proposal.proposalId||typeof proposal.source!=='string'||!proposal.source.trim())return {ok:false,code:'draft_proposal_invalid'};
    const old=draftFor(context),inputs=proposal.inputs || {};
    if(!inputs||typeof inputs!=='object'||Array.isArray(inputs)||Object.keys(inputs).some(key=>!Object.hasOwn(context.runtime?context.schema.properties || {}:context.saved.inputs,key)))return {ok:false,code:'draft_fields_invalid'};
    if(Object.hasOwn(proposal,'document')&&!context.hasDocument)return {ok:false,code:'draft_fields_invalid'};
    const patch={inputs:clone(inputs)};if(Object.hasOwn(proposal,'document'))patch.document=proposal.document;
    const before={inputs:clone(old.inputs),document:old.document};
    const after={inputs:{...before.inputs,...inputs},document:Object.hasOwn(patch,'document')?patch.document:before.document};
    const changedFields=Object.keys(inputs).filter(key=>JSON.stringify(before.inputs[key])!==JSON.stringify(after.inputs[key]));
    if(before.document!==after.document)changedFields.push('document');
    if(!changedFields.length)return {ok:false,code:'draft_unchanged'};
    jobDrafts.edit(context.scope,context.saved,patch,context.revision);
    runtimeRawInputs.delete(context.scope.key);
    draftVersions.set(context.scope.key,(draftVersions.get(context.scope.key)||0)+1);
    aiReceipts.set(context.scope.key,{proposalId:proposal.proposalId,source:proposal.source.slice(0,500),changedFields,before,after,saved:clone(context.saved),revision:context.revision,undone:false});
    // The old DOM is about to be replaced; do not recapture it over the proposal.
    renderedEditContext=null;renderPanel();
    return {ok:true,id:proposal.proposalId,status:'applied',node_id:context.scope.nodeId,case_id:context.scope.caseId,fields:changedFields,source:proposal.source.slice(0,500),persisted:false,executed:false};
  }
  function undoAIDraft(proposal) {
    const context=aiContext(proposal),receipt=context&&aiReceipts.get(context.scope.key);
    if(!context||!receipt||receipt.proposalId!==proposal.proposalId||receipt.undone)return {ok:false,code:'draft_target_changed'};
    const current=draftFor(context),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
    if(receipt.revision!==context.revision||!same(receipt.saved,context.saved)||!same({inputs:current.inputs,document:current.document},receipt.after))return {ok:false,code:'draft_changed'};
    jobDrafts.discard(context.scope);
    jobDrafts.edit(context.scope,context.saved,{...receipt.before,replaceInputs:context.runtime},context.revision);
    receipt.undone=true;runtimeRawInputs.delete(context.scope.key);draftVersions.set(context.scope.key,(draftVersions.get(context.scope.key)||0)+1);
    renderedEditContext=null;renderPanel();
    return {ok:true,id:receipt.proposalId,status:'undone',node_id:context.scope.nodeId,case_id:context.scope.caseId,fields:receipt.changedFields,source:receipt.source,persisted:false,executed:false};
  }
  function readSnapshot(value) {
    captureJobEdits();
    const {state:server,historyCase:history,...display}=value;
    // Server objects are read only identity keys; display never receives a live
    // object to mutate. Observer ticks reuse the copies of unchanged responses.
    if(server!==serverSource){state=server?clone(server):null;serverSource=server;}
    if(history!==historySource){historyCase=history?clone(history):null;historySource=history;}
    snapshot=clone(display);
    ({category,browsingSystem,browsingSite,browseNodeId,runView,errorMessage,busy}=snapshot);
  }
  function setBusy(value = busy) {
    busy = value;
    for (const container of [host, $('#ees-work-entry')]) container?.querySelectorAll('button[data-mutation]').forEach(el=>{el.disabled=busy||el.dataset.unavailable==='true';});
    if(host){
      host.setAttribute('aria-busy',String(busy));
      const pending=host.querySelector('#ees-work-pending-status');if(pending)pending.hidden=!busy;
      const result=host.querySelector('[data-work-section="current-result"]'),heading=result?.querySelector('h3');
      if(heading){if(!heading.dataset.savedLabel)heading.dataset.savedLabel=heading.textContent;heading.textContent=busy?(result.dataset.workRecorded==='true'?'이전 저장 결과 · 요청 처리 중':'결과 대기 · 미판정'):heading.dataset.savedLabel;}
    }
  }
  function treeHTML(data, ids, run) {
    const key=expansionKey(data,run),summaries={};
    for(const id of ids || [])if(data.nodes[id]?.type==='p'&&!run){const active=scopeCases(id).filter(c=>!finished(c));if(active.length>1)summaries[id]='진행 '+active.length+'건 · 실행 선택';}
    return workUI.treeHTML(data,ids,{selectedId:!run||selectedCase()?.id===run.id?selectedId():'',expanded:expansionState(key),statuses:run?.node_states || {},summaries,expansionKey:key,run});
  }
  function sidebar() {
    const anchor=$('#sidebar-search-button');if(!anchor)return;
    let entry=$('#ees-work-entry');
    if(!entry){entry=document.createElement('section');entry.id='ees-work-entry';entry.dataset.eesWork='';entry.setAttribute('aria-label','공장별 업무');anchor.parentElement.insertAdjacentElement('afterend',entry);renderNavigator();}
    // The native Workspace entry is the single management entrance.
    $('#ees-work-admin-link')?.remove();
  }
  const scopeIcon = kind => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${kind==='site'?'<path d="M3 21V11l6 3V8l6 3V3h4v18H3Z"/><path d="M7 18h1m4 0h1m4 0h1"/>':kind==='system'?'<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5m-18 5 9 5 9-5"/>':'<path d="m8 9 4-4 4 4m-8 6 4 4 4-4"/>'}</svg>`;
  function updateNavHTML(container,html) {
    if(container.__eesHTML===html)return;
    const active=container.contains(document.activeElement)?document.activeElement:null;
    const focused=active?{id:active.id,action:active.dataset.action,node:active.dataset.nodeId,picker:active.dataset.picker,value:active.dataset.value,category:active.dataset.workCategory}:null;
    container.__eesHTML=html;container.innerHTML=html;
    if(focused){const replacement=Array.from(container.querySelectorAll('button')).find(el=>focused.id?el.id===focused.id:el.dataset.action===focused.action&&el.dataset.nodeId===focused.node&&el.dataset.picker===focused.picker&&el.dataset.value===focused.value&&el.dataset.workCategory===focused.category);replacement?.focus({preventScroll:true});}
  }
  const scopeReady = () => callbacks.scopeReady();
  function updateScopeReadiness() {
    const controls=$('#ees-work-entry .ew-scope-pickers');if(!controls)return;
    const ready=scopeReady(),busy=String(!ready),route=ready?snapshot.acceptedRoute:'';
    if(controls.getAttribute('aria-busy')!==busy)controls.setAttribute('aria-busy',busy);
    if(controls.dataset.readyRoute!==route)controls.dataset.readyRoute=route;
    controls.querySelectorAll('[data-action=scope_toggle]').forEach(el=>{if(el.disabled!==!ready)el.disabled=!ready;});
  }
  function renderScopeControls(container,data) {
    const site=data.sites[browsingSite],label=site?.name || site?.factory || siteLabel(site);
    updateNavHTML(container,`<div class="ew-v4-workspace"><button type="button" id="ees-work-site-trigger" class="ew-scope-trigger" data-action="scope_toggle" data-picker="site" data-value="${esc(browsingSite)}" aria-haspopup="dialog" aria-expanded="${scopePicker==='site'}" aria-controls="ees-work-scope-popover" aria-label="작업 공장 선택: ${esc(label)}"><span class="ew-v4-factory-mark">${esc(label?.slice(0,2))}</span><span class="ew-scope-text"><span class="ew-scope-value" title="${esc(siteLabel(site))}">${esc(label)}</span><span class="ew-v4-system-name">${esc(browsingSystem)}</span></span>${workV4Icon('chevron-down')}</button><button type="button" id="ees-work-system-trigger" class="ew-v4-system-switch" data-action="scope_toggle" data-picker="system" data-value="${esc(browsingSystem)}" aria-haspopup="dialog" aria-expanded="${scopePicker==='system'}" aria-label="시스템 선택: ${esc(browsingSystem)}" title="시스템 선택">시스템 선택</button></div>`);
    updateScopeReadiness();renderScopePopover();
  }

  function renderScopePopover() {
    let popup=$('#ees-work-scope-popover');
    if(!scopePicker||!state){popup?.remove();return;}
    if(!popup){popup=document.createElement('div');popup.id='ees-work-scope-popover';popup.dataset.eesWork='';popup.className='ew-scope-popover';popup.setAttribute('role','dialog');popup.setAttribute('aria-modal','false');popup.setAttribute('popover','manual');document.body.appendChild(popup);}
    popup.dataset.picker=scopePicker;popup.setAttribute('aria-label',scopePicker==='site'?'작업 공장 선택':'시스템 선택');
    const data=state.catalog,option=(value,label,selected)=>`<button type="button" class="ew-scope-option" data-action="scope_choose" data-picker="${scopePicker}" data-value="${esc(value)}" aria-pressed="${selected}" tabindex="-1"><span>${esc(label)}</span>${selected?'<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m4 10 4 4 8-8"/></svg>':''}</button>`;
    const options=scopePicker==='system'?data.systems.map(s=>option(s,s,s===browsingSystem)).join(''):[...new Set(Object.values(data.sites).map(s=>s.country || '공장'))].map(country=>`<p class="ew-scope-group">${esc(country)}</p>${Object.values(data.sites).filter(s=>(s.country || '공장')===country).map(s=>option(s.id,s.name || s.factory || siteLabel(s),s.id===browsingSite)).join('')}`).join('');
    updateNavHTML(popup,`<p class="ew-scope-title">${scopePicker==='site'?'작업 공장':'시스템'} 선택</p>${options}`);
    if(popup.showPopover&&!popup.matches(':popover-open'))popup.showPopover();
    positionNav();
    if(document.activeElement===document.body)popup.querySelector('[aria-pressed=true]')?.focus({preventScroll:true});
  }
  function closeScopePicker(restoreFocus=false) {
    const kind=scopePicker;if(!kind)return;scopePicker='';$('#ees-work-scope-popover')?.remove();
    document.querySelectorAll('#ees-work-entry [data-action=scope_toggle]').forEach(el=>el.setAttribute('aria-expanded','false'));
    const controls=$('#ees-work-entry .ew-scope-pickers');if(controls)controls.__eesHTML='';
    if(restoreFocus)$(`#ees-work-${kind}-trigger`)?.focus({preventScroll:true});
  }
  function openScopePicker(kind,last=false) {
    if(!['site','system'].includes(kind))return;
    if(!scopeReady()){updateScopeReadiness();return;}
    scopePicker=kind;renderNavigator();
    const popup=$('#ees-work-scope-popover'),options=popup?.querySelectorAll('[data-action=scope_choose]');
    (last?options?.[options.length-1]:popup?.querySelector('[aria-pressed=true]') || options?.[0])?.focus({preventScroll:true});
  }
  function renderNavigator() {
    $('#ees-work-navigator')?.remove();const entry=$('#ees-work-entry');if(!entry)return;
    const data=state?.catalog;
    if(!data){if(!entry.firstChild)entry.innerHTML='<p class="ew-muted">업무 절차를 불러오는 중입니다.</p>';updateScopeReadiness();return;}
    if(!entry.querySelector('.ew-scope-pickers'))entry.innerHTML='<div class="ew-scope-pickers"></div><div class="ew-work-navigation"></div>';
    renderScopeControls(entry.querySelector('.ew-scope-pickers'),data);
    const icons={setup:'package',ops:'activity',incident:'triangle-alert'};
    const links=[['my_work','내 업무','list-checks'],['find_work','워크플로우 찾기','compass'],['history_view','실행 기록','history'],['native_history','대화 기록','message']];
    let html='<nav class="ew-v4-nav-links" aria-label="주 메뉴">'+links.map(([action,label,icon])=>'<button type="button" data-action="'+action+'">'+workV4Icon(icon)+'<span>'+label+'</span></button>').join('')+'</nav><p class="ew-caption">업무</p><nav class="ew-v4-tree" aria-label="업무 분류와 단계">';
    for(const [group,label] of Object.entries(categories)){
      const roots=visibleRoots(group),open=category===group&&navOpen;
      const active=(state.cases || []).filter(c=>c.site?.id===browsingSite&&c.system===browsingSystem&&roots.includes(c.process_id)&&!finished(c));
      html+='<button type="button" class="ew-v4-category" data-work-category="'+group+'" aria-expanded="'+open+'">'+workV4Icon(open?'chevron-down-14':'chevron-right')+workV4Icon(icons[group])+'<span>'+label+'</span>'+(group==='incident'&&active.length?'<span class="ew-v4-incident-dot">'+workV4Icon('Ellipse')+'</span>':'')+'<small>'+active.length+'</small></button>';
      if(!open)continue;
      for(const rootId of roots){
        const selected=chosenCase(rootId),c=selected?.id===selectedCase()?.id?selectedCase():selected;
        const source=c?.definition || (c?.tree_nodes?{...data,nodes:c.tree_nodes,version:c.version}:data),process=source.nodes[rootId];if(!process)continue;
        const key=expansionKey(source,c),branches=expansionState(key),isCurrent=processId()===rootId;
        const facts=workV4Facts(c,source,c?.id===selectedCase()?.id?snapshot.execution:null,{site:c?.site || data.sites[browsingSite],system:browsingSystem});
        const actualCount=n=>workNavigationLeaves(source,n).filter(item=>facts.state(item).complete).length;
        const simulationCount=n=>workNavigationLeaves(source,n).filter(item=>facts.state(item).group==='simulation').length;
        if(!branches.has(rootId))branches.set(rootId,isCurrent);
        const expanded=branches.get(rootId),counts=c?.node_states?.[rootId]?.progress,total=counts?.total ?? workNavigationLeaves(source,process).filter(n=>workNavigationApplies(source,n,c?.site || data.sites[browsingSite],browsingSystem)).length;
        html+='<div class="ew-v4-process"><button type="button" data-action="expand" data-node-id="'+esc(rootId)+'" data-case-id="'+esc(c?.id || '')+'" data-expansion-key="'+esc(key)+'" aria-expanded="'+expanded+'" aria-label="'+esc(process.name)+(expanded?' 접기':' 펼치기')+'">'+workV4Icon(expanded?'chevron-down-14':'chevron-right')+'</button><button type="button" data-action="select" data-node-id="'+esc(rootId)+'" data-process-id="'+esc(rootId)+'" title="'+esc(process.name)+'" aria-current="'+(selectedId()===rootId?'step':'false')+'"><span>'+esc(process.name)+'</span><small title="저장된 진행 집계 · 모의 진행은 실제 업무 완료와 다릅니다">'+actualCount(process)+'/'+total+(simulationCount(process)?' · 모의 '+simulationCount(process):'')+'</small></button></div>';
        if(expanded)(process.children || []).map(id=>source.nodes[id]).filter(n=>n?.type==='t').forEach((task,index)=>{
          const shown=workNavigationState(source,task,c,{site:c?.site || data.sites[browsingSite],system:browsingSystem}),progress=c?.node_states?.[task.id]?.progress;
          const total=progress?.total ?? workNavigationLeaves(source,task).filter(n=>workNavigationApplies(source,n,c?.site || data.sites[browsingSite],browsingSystem)).length;
          const active=selectedId()===task.id||workUI.lineage(selectedId(),source).some(n=>n.id===task.id),shownLabel=simulationCount(task)?'모의 진행 포함 · 실제 완료 미확인':shown.label;
          const glyph=simulationCount(task)?'Waiting':['passed','completed'].includes(shown.key)?'Done':['running','in_progress'].includes(shown.key)?'Running':shown.key==='failed'?'Failed':shown.key==='unknown'?'Unknown':shown.key==='waiting'?'Waiting':'Action';
          html+='<button type="button" class="ew-v4-task" data-action="select" data-node-id="'+esc(task.id)+'" data-process-id="'+esc(rootId)+'" aria-current="'+(active?'step':'false')+'" title="'+esc(task.name+' · '+shownLabel)+'">'+workV4Icon(glyph)+'<span>'+esc((index+1)+' '+task.name)+'</span><small>'+actualCount(task)+'/'+total+(simulationCount(task)?' · 모의 '+simulationCount(task):'')+'</small><span class="ew-visually-hidden">'+esc(shownLabel)+'</span></button>';
        });
      }
      if(!roots.length)html+='<p class="ew-muted">게시된 절차가 없습니다.</p>';
    }
    html+='</nav>';updateNavHTML(entry.querySelector('.ew-work-navigation'),html);
  }

  function positionNav() {
    const popup=$('#ees-work-scope-popover'),trigger=$(`#ees-work-${scopePicker}-trigger`);if(!popup||!trigger)return;
    const rect=trigger.getBoundingClientRect(),margin=8;
    if(rect.width===0||rect.bottom<0||rect.top>innerHeight){closeScopePicker();return;}
    const availableWidth=Math.max(0,innerWidth-margin*2),width=Math.min(Math.max(rect.width,224),availableWidth);
    popup.style.width=width+'px';popup.style.left=Math.max(margin,Math.min(rect.left,innerWidth-width-margin))+'px';
    const below=Math.max(0,innerHeight-rect.bottom-margin-6),above=Math.max(0,rect.top-margin-6),useAbove=below<180&&above>below;
    popup.style.maxHeight=Math.min(360,useAbove?above:below)+'px';
    popup.style.top=(useAbove?Math.max(margin,rect.top-popup.getBoundingClientRect().height-6):rect.bottom+6)+'px';
  }

  function chatLayout() {
    const anchor = $('#chat-container #chat-pane'), column = anchor?.parentElement, row = column?.parentElement;
    return row && column && chatRoute() ? {anchor,column,row} : null;
  }
  function renderContext() {
    const c=selectedCase(),layout=chatLayout();let strip=$('#ees-work-context');
    if(!layout||!state||!selectedId()){strip?.remove();return;}
    if(!strip){strip=document.createElement('div');strip.id='ees-work-context';strip.dataset.eesWork='';layout.column.insertBefore(strip,layout.anchor);}
    const target=snapshot.reference,current=target?.kind==='history'?historyCase?.definition?.nodes?.[target.node_id]:node(target?.node_id || selectedId()),reference=snapshot.referenceEnabled!==false&&target?.kind!=='none';
    const referenceLabel=target?.kind==='history'?`${current?.name || '이전 실행'} · ${runLabel(historyCase)}`:current?.name || '현재 업무';
    const connection=c?c.chat_id?'이 대화에 연결됨':'첫 메시지를 보내면 이 대화에 연결됩니다':'절차 미리보기 · 시작 전';
    const html='<header class="ew-v4-assistant-header"><strong>EES Assistant</strong><button type="button" data-action="native_new_chat" aria-label="새 대화">'+workV4Icon('plus')+'</button><button type="button" data-action="assistant_toggle" aria-label="Assistant 접기" aria-expanded="'+assistantOpen+'">'+workV4Icon('panel-right-16')+'</button></header><div class="ew-v4-reference"><span>참고</span>'+(reference?'<span class="ew-v4-reference-tag">'+workV4Icon('file-text-12')+'<span title="'+esc(referenceLabel)+'">'+esc(referenceLabel)+'</span><button type="button" data-action="reference_toggle" aria-label="참고 해제">'+workV4Icon('x')+'</button></span>':button('일반 대화 · 현재 업무 참고','reference_toggle'))+'</div><small class="ew-visually-hidden" role="status">'+esc(connection)+'</small>';
    if(strip.innerHTML!==html)strip.innerHTML=html;
    let questions=$('#ees-v4-suggestions');
    const hasMessages=Boolean($('#messages-container .user-message, #messages-container .chat-user'));
    if(!hasMessages&&reference){
      if(!questions){questions=document.createElement('div');questions.id='ees-v4-suggestions';questions.dataset.eesWork='';strip.after(questions);}
      const label=current?.name || '현재 업무',prompts=current?.type==='j'?[label+'의 필요한 입력을 알려 주세요.',label+'의 완료 기준은 무엇인가요?',label+'의 입력을 근거를 확인하고 초안으로 채워 주세요.']:['이 단계에서 먼저 할 일은 무엇인가요?',label+'의 진행 조건을 설명해 주세요.','현재 할 일의 필요한 입력을 알려 주세요.'];
      const markup='<p>이 화면의 단계와 작업을 참고해 답변합니다. 업무와 관계없는 질문도 할 수 있습니다.</p><span>추천 질문</span><div>'+prompts.map(text=>'<button type="button" data-action="suggest" data-question="'+esc(text)+'">'+workV4Icon('message-14')+'<span>'+esc(text)+'</span>'+workV4Icon('chevron-right')+'</button>').join('')+'</div>';
      if(questions.innerHTML!==markup)questions.innerHTML=markup;
    }else questions?.remove();
  }

  function ensureHost() {
    if (host) return;
    host = document.createElement('main'); host.id = 'ees-work-panel'; host.dataset.eesWork = ''; host.dataset.eesV4 = ''; host.setAttribute('aria-label','업무 수행');
    host.innerHTML = `<header><div class="ew-panel-toolbar"><div id="ees-work-parent"></div>${button('절차 편집','authoring_open','id="ees-work-authoring-open" title="현재 공개 절차 편집 · 기존 진행과 이력 유지" hidden')}<details class="ew-panel-menu"><summary aria-label="업무 패널 더 보기"><span class="ew-visually-hidden">더 보기</span><span aria-hidden="true">···</span></summary><div class="ew-panel-menu-body"><nav id="ees-work-tabs" aria-label="업무 화면"></nav><div id="ees-work-view-menu"></div></div></details>${button('Assistant','assistant_toggle','id="ees-v4-assistant-open" aria-label="Assistant 열기 또는 접기"')}${button('닫기','panel_close','id="ees-work-close" aria-label="업무 화면 닫기 · 대화로 돌아가기"')}</div><div id="ees-work-identity-slot"></div><p id="ees-work-pending-status" role="status" hidden>요청 처리 중 · 결과를 기다리고 있습니다. 완료 여부는 처리 결과 확인 후 반영됩니다.</p></header><div id="ees-work-content" class="ew-scroll"></div><div id="ees-work-action-dock"></div>`;
    divider = document.createElement('div'); divider.id = 'ees-work-resizer'; divider.tabIndex = 0; divider.setAttribute('role','separator'); divider.setAttribute('aria-label','대화와 업무 패널 너비 조절'); divider.setAttribute('aria-orientation','vertical'); divider.setAttribute('aria-controls',host.id); divider.innerHTML = '<span></span>';
    host.addEventListener?.('toggle',event=>{if(event.target.matches?.('.ew-work-edit'))layoutActions();},true);
  }
  function layoutActions() {
    const content=host?.querySelector('#ees-work-content'),dock=host?.querySelector('#ees-work-action-dock');if(!content||!dock)return;
    const detail=content.querySelector('.ew-v4-detail');
    if(!detail){dock.hidden=true;return;}
    const action=detail.querySelector('.ew-work-action-region');
    if(action&&!dock.contains(action))dock.append(action);
    dock.hidden=!dock.children.length;
    host.style.setProperty('--ees-v4-dock-height',(dock.hidden?0:dock.getBoundingClientRect().height)+'px');
    host.dataset.scrollActions='false';
  }

  function sizePanel() {
    if(!host||!panelOpen)return;const layout=chatLayout();if(!layout)return;
    const overlay=window.innerWidth<1280;
    document.body.dataset.eesAssistantOpen=String(assistantOpen);
    host.classList.toggle('ew-narrow',window.innerWidth<900);
    host.style.width='';host.style.flexBasis='';host.dataset.compact=String(layout.row.getBoundingClientRect().width<1200);
    layout.column.style.setProperty('--ees-v4-assistant-width',(preferredWidth ?? (window.innerWidth<1536?320:360))+'px');
    width=preferredWidth ?? (window.innerWidth<1536?320:360);
    if(divider){divider.hidden=overlay||!assistantOpen;divider.setAttribute('aria-valuenow',String(Math.round(width)));divider.setAttribute('aria-valuemin','280');divider.setAttribute('aria-valuemax','600');}
    layoutActions();
  }

  function openHost() {
    const layout = chatLayout(); if (!layout || !state || !selectedId()) return; ensureHost();
    const reopening=!host.isConnected;
    panelOpen = true; styledColumn=layout.column;styledColumn.classList.add('ees-work-chat-column');document.body.dataset.eesV4='';layout.row.insertBefore(host,layout.column);layout.row.insertBefore(divider,layout.column);sizePanel();renderContext();
    if(reopening&&renderedPanelTarget)host.querySelector('#ees-work-content').scrollTop=panelPositions.get(renderedPanelTarget)||0;
  }
  function closeHost() {
    captureJobEdits();
    if(host?.isConnected&&renderedPanelTarget)panelPositions.set(renderedPanelTarget,host.querySelector('#ees-work-content').scrollTop||0);
    panelOpen = false; drag=null;if(divider)delete divider.dataset.pointer;host?.remove(); divider?.remove();styledColumn?.classList.remove('ees-work-chat-column');styledColumn=null;delete document.body.dataset.eesV4;delete document.body.dataset.eesAssistantOpen;renderContext();
  }
  function renderTabs() {
    if (!host) return; const tabs = $('#ees-work-tabs',host), screens = panelInfo?.screens || window.__eesWorkPanelV1?.list?.(chatId()) || [{key:'workflow',label:'업무 진행'}];
    const html = screens.map(screen => button(screen.label,'panel_tab',`data-screen="${esc(screen.key)}" aria-selected="${screen.key==='workflow'}"`)).join('');
    if (tabs.innerHTML !== html) tabs.innerHTML = html;
    tabs.hidden=screens.length<2;
  }
  function openPanel() {if(!chatRoute()||!state||!selectedId())return;callbacks.registerPanel(); window.__eesWorkPanelV1?.select(chatId(),'workflow',{open:true,focus:false});}
  function runTabs() {
    const active=scopeCases(processId()).filter(c=>!finished(c)),current=selectedCase();
    const picker=active.length>1?`<label>현재 실행<select id="ees-work-run-select">${active.map(c=>`<option value="${esc(c.id)}" ${c.id===current?.id?'selected':''}>${esc(runLabel(c))}</option>`).join('')}</select></label>`:'';
    return picker+`<nav class="ew-run-tabs" id="ees-work-run-view" aria-label="실행 기록"><button type="button" data-action="current_view" aria-pressed="${runView==='current'}">현재 작업</button><button type="button" data-action="history_view" aria-pressed="${runView==='history'}">실행 이력</button></nav>`;
  }
  function readOnlyNode(c,n,history=false) {return workPanelNodeHTML(c,n,{readOnly:true,history});}

  function historyHTML() {
    const p=processId(),c=selectedCase(),cases=scopeCases(p);
    if(historyCase){const n=historyCase.definition.nodes[historyCase.process_id];return `${button('실행 목록으로','history_view')}<p class="ew-notice">이전 실행 · 읽기 전용<br>오른쪽 대화와 왼쪽 단계별 진행은 현재 진행 건을 유지합니다.</p><p class="ew-muted">${esc(siteLabel(historyCase.site))} · ${esc(historyCase.system)}<br>${esc(runLabel(historyCase))}</p>${readOnlyNode(historyCase,n,true)}`;}
    return `<h2 class="ew-title">실행 이력</h2><p class="ew-muted">${esc(siteLabel(state.catalog.sites[browsingSite]))} · ${esc(browsingSystem)} · ${esc(nameOf(p))}</p><div class="ew-case-list">${cases.map(item=>`<button type="button" data-action="history_case" data-case-id="${esc(item.id)}" ${item.id===c?.id?'disabled':''}><strong>${esc(runLabel(item))}</strong><span>${item.id===c?.id?'현재 실행 · ':''}${item.status==='passed'?'기록 종료':esc(statuses[item.status])} · 저장된 진행 ${item.progress.done}/${item.progress.total} · 실제 판정은 상세에서 확인</span></button>`).join('') || '<p class="ew-notice">아직 기록된 실행이 없습니다.</p>'}</div>`;
  }
  function previewHTML() {
    const n=node(browseNodeId || selectedId());if(!n)return '<p class="ew-muted">왼쪽에서 업무 절차를 선택하세요.</p>';
    const p=lineage(n.id)[0],cases=scopeCases(p.id),active=cases.filter(c=>!finished(c));
    const picker=active.length?`<section class="ew-work-cases"><h3>이어서 진행할 업무</h3><p class="ew-muted">${active.length>1?'진행 건을 선택한 뒤 입력을 반영하거나 점검하세요.':'기존 진행 건에서 이어갈 수 있습니다.'}</p><div class="ew-case-list">${active.map(c=>`<button type="button" data-action="open_case" data-case-id="${esc(c.id)}"><strong>${esc(runLabel(c))}</strong><span>${esc(statuses[c.status])} · 저장된 진행 ${c.progress.done}/${c.progress.total} · 실제 판정은 상세에서 확인</span></button>`).join('')}</div></section>`:'<p class="ew-work-preview-note">'+(workHasExecution(definition(),n.id)?'실행 계획에서 범위와 공개 입력을 확인하세요. 명시적으로 시작하면 진행 건과 실행 입력을 저장합니다.':'업무를 살펴본 뒤 필요한 입력을 반영하거나 점검하세요. 첫 저장 시 진행 건을 만듭니다.')+'</p>';
    const completed=cases.filter(finished);
    const previous=completed.length?`<p class="ew-muted">종료 기록 ${completed.length}건은 실행 이력에 보존됩니다.</p>`:'';
    renderedEditContext=editContext(n.id);
    return workPanelNodeHTML(null,n,{definition:definition(),site:state.catalog.sites[browsingSite],system:browsingSystem,previewActions:picker+previous,previewBlocked:active.length>1,draft:draftFor(renderedEditContext),listView:jobListState()});
  }
  function renderPanel() {
    captureJobEdits();
    if (!chatRoute() || !state || !selectedId()) {closeHost(); return;} ensureHost();
    const content=$('#ees-work-content',host),focused=host.contains(document.activeElement)?document.activeElement:null;
    const authoring=host.querySelector('#ees-work-authoring-open');if(authoring)authoring.hidden=runView!=='current'||!callbacks.canAuthor?.()||!state?.catalog?.nodes?.[processId()];
    const panelTarget=JSON.stringify([browsingSite,browsingSystem,selectedCase()?.id || '',definition()?.version,runView,historyCase?.id || '',selectedId()]);
    if(renderedPanelTarget&&host.isConnected)panelPositions.set(renderedPanelTarget,content.scrollTop || 0);
    const returning=pendingReturn?.to===selectedId()?pendingReturn:null;
    const retainedScroll=panelTarget===renderedPanelTarget?(host.isConnected?content.scrollTop || 0:panelPositions.get(panelTarget)||0):returning?panelPositions.get(panelTarget)||0:0;
    const focusState=focused?{id:focused.id,name:focused.name,node:focused.dataset.nodeId,action:focused.dataset.action,runtimeAction:focused.dataset.runtimeAction,runId:focused.dataset.runId,start:focused.selectionStart,end:focused.selectionEnd}:null;
    const oldNode=renderedEditContext?.scope.nodeId;
    host.querySelector('#ees-work-action-dock')?.replaceChildren();actionLayoutKey='';
    if(snapshot.recordLookupError){
      // Retained snapshots are not fresh evidence after a failed case read.
      // captureJobEdits above keeps local edits for a successful revalidation.
      renderedEditContext=null;
      content.innerHTML=runTabs()+alertHTML()+workExecutionRuntimeHTML(null,{error:snapshot.recordLookupError.message});
    }else if(runView==='history' || !selectedCase()) {
      if(runView==='history')renderedEditContext=null;
      content.innerHTML=runTabs()+alertHTML()+(runView==='history'?historyHTML():previewHTML());
    }else{
      const c=selectedCase(),n=node(selectedId()) || node(c.selected_id) || node(c.process_id),done=finished(c);
      const closed=done?`<p class="ew-work-preview-note">${c.status==='skipped'?'이 진행 건에는 적용 대상 업무가 없습니다.':'이 진행 기록이 종료되어 읽기만 가능합니다. 실제 업무 판정은 각 작업의 결과를 확인해 주세요.'} 기존 기록은 보존됩니다.</p>`:'';
      renderedEditContext=done?null:editContext(n.id);
      content.innerHTML=runTabs()+alertHTML()+closed+workPanelNodeHTML(c,n,{readOnly:done,draft:draftFor(renderedEditContext),listView:jobListState(),execution:snapshot.execution,executionError:snapshot.recordLookupError?.message || snapshot.executionError})+(done&&n.type==='p'&&!snapshot.recordLookupError&&!snapshot.executionError?'<section class="ew-work-execute ew-work-action-region"><div class="ew-work-actions">'+button('새 실행','start_case','class="ew-primary" data-mutation')+'</div></section>':'')+(workHasExecution(c.definition,n.id)?'':'<p class="ew-footnote">연결 점검은 모의 결과이며 실제 업무 시스템을 호출하지 않습니다.</p>');
    }
    if(runView==='history'&&historyCase&&!snapshot.recordLookupError&&workHasExecution(historyCase.definition,historyCase.process_id))content.insertAdjacentHTML('beforeend',(snapshot.historyExecution?.runs || []).map(run=>workExecutionRuntimeHTML({run},{nodeId:run.node_id,definition:historyCase.definition,case:historyCase,readOnly:true,history:true})).join(''));
    if(runView==='current'&&!snapshot.executionError&&!snapshot.recordLookupError&&snapshot.execution?.runs?.length>1){
      const relevant=snapshot.execution.runs.filter(run=>workExecutionForNode({run},selectedId(),definition())),current=workExecutionForNode(snapshot.execution,selectedId(),definition())?.run;
      const previous=relevant.filter(run=>run.id!==current?.id);
      if(previous.length)content.insertAdjacentHTML('beforeend','<details class="ew-history"><summary data-work-overlay="이 진행 건의 앞 실행">이 진행 건의 앞 실행 '+previous.length+'건</summary>'+previous.map(run=>workExecutionRuntimeHTML({run},{nodeId:selectedId(),definition:definition(),readOnly:true,history:true})).join('')+'</details>');
    }
    const disclosures=panelDisclosures.get(panelTarget);
    if(disclosures)content.querySelectorAll('details').forEach(el=>{const key=el.className+'|'+(el.querySelector(':scope > summary')?.textContent || '');if(disclosures.has(key))el.open=disclosures.get(key);});
    const back=navigationTrail[navigationTrail.length-1];
    if(back&&back.to===selectedId()&&back.scope===navigationScope())content.insertAdjacentHTML('afterbegin',button('‹  '+nameOf(back.from),'panel_back','class="ew-work-return" aria-label="‹ '+esc(nameOf(back.from))+'로 돌아가기" title="'+esc(nameOf(back.from))+'로 돌아가기"'));
    const parentSlot=host.querySelector('#ees-work-parent'),identitySlot=host.querySelector('#ees-work-identity-slot'),menuSlot=host.querySelector('#ees-work-view-menu');
    if(parentSlot&&identitySlot&&menuSlot){
      identitySlot.replaceChildren();menuSlot.replaceChildren();
      const path=lineage(selectedId());
      parentSlot.innerHTML='<nav class="ew-v4-breadcrumb" aria-label="현재 업무 경로"><span>'+esc(categories[category])+'</span>'+path.map(n=>'<span aria-hidden="true">/</span><button type="button" data-action="select" data-node-id="'+esc(n.id)+'" aria-current="'+(n.id===selectedId()?'page':'false')+'">'+esc(n.name)+'</button>').join('')+'</nav>';
      content.querySelector(':scope > .ew-work-path')?.remove();
      const currentTabs=content.querySelector('#ees-work-run-view');if(currentTabs)menuSlot.append(currentTabs);
      host.dataset.workLevel=runView==='current'&&node(selectedId())?.type==='j'?'j':'management';
      const backControl=content.querySelector(':scope > .ew-work-return');
      if(backControl&&host.dataset.workLevel==='j'){
        if(content.querySelector('.ew-v4-back'))backControl.remove();
        else{backControl.textContent='← 작업 목록';content.querySelector('.ew-v4-detail-main')?.prepend(backControl);}
      }
    }
    const detailBody=content.querySelector('.ew-v4-detail-content');
    if(detailBody)for(const extra of Array.from(content.children)){
      if(extra.matches('.ew-footnote,.ew-history,.ew-work-preview-note,.ew-error'))detailBody.append(extra);
    }
    if(renderedEditContext?.runtime&&runtimeRawInputs.has(renderedEditContext.scope.key)){
      const raw=runtimeRawInputs.get(renderedEditContext.scope.key);
      content.querySelectorAll('#ees-work-inputs [name]').forEach(field=>{if(Object.hasOwn(raw,field.name))field.value=raw[field.name];});
    }
    if(focusState&&!focused?.isConnected&&(focusState.id||focusState.name||focusState.action)&&oldNode===renderedEditContext?.scope.nodeId){
      const replacement=Array.from(host.querySelectorAll('input,textarea,select,button')).find(el=>focusState.id?el.id===focusState.id:focusState.name?el.name===focusState.name:el.dataset.action===focusState.action&&el.dataset.nodeId===focusState.node&&el.dataset.runtimeAction===focusState.runtimeAction&&el.dataset.runId===focusState.runId);
      replacement?.focus({preventScroll:true});if(replacement?.setSelectionRange&&typeof focusState.start==='number')replacement.setSelectionRange(focusState.start,focusState.end);
    }
    renderedPanelTarget=panelTarget;
    renderTabs();callbacks.registerPanel();setBusy();
    // Read a newly selected task from its heading. Refreshes of that same
    // task keep the user's position while inputs/results are updated.
    layoutActions();
    content.scrollTop=retainedScroll;
    // Detached scroll containers report zero; retain their position until open.
    panelPositions.set(panelTarget,retainedScroll);
    if(returning){
      // Completing a job may remove its row from the retained list filter.
      const returnedNode=node(returning.focusNode),completed=returnedNode&&returning.wasComplete===false&&!snapshot.recordLookupError&&!snapshot.executionError&&workV4Facts(selectedCase(),definition(),snapshot.execution).state(returnedNode).complete;
      if(completed){
        const notice=document.createElement('p');notice.className='ew-notice';notice.setAttribute('role','status');
        notice.innerHTML=esc(returnedNode.name)+'이 완료로 이동했습니다 · '+button('완료 보기','select','data-node-id="'+esc(returnedNode.id)+'" aria-label="'+esc(returnedNode.name)+' 완료 상세 보기"');
        content.querySelector('.ew-v4-list')?.prepend(notice);
      }
      const origin=!completed&&Array.from(content.querySelectorAll('[data-action]')).find(el=>el.dataset.action===returning.action&&el.dataset.nodeId===returning.focusNode);
      const control=origin || content.querySelector('[data-group=todo] [data-action=select]') || content.querySelector('#ees-work-job-search');
      control?.focus({preventScroll:true});
      if(!origin)control?.scrollIntoView({block:'nearest',inline:'nearest'});
      pendingReturn=null;
    }
    if(detailContext){if(detailContext.scope!==navigationScope()){$('#ees-work-dialog .ew-dialog-body')?.replaceChildren();workUI.closeDialog();}else renderDetail();}
    if(runtimeDetailContext){
      const source=runView==='history'?snapshot.historyExecution:snapshot.execution,runs=[source?.run,...(source?.runs || [])].filter(Boolean);
      const available=runtimeDetailContext.runIds.every(id=>{const run=runs.find(item=>item.id===id);return run&&run.evidence_available!==false&&!(run.calls || []).some(call=>call.evidence_available===false);});
      if(runtimeDetailContext.scope!==navigationScope()||snapshot.recordLookupError||snapshot.executionError||!available){
        // dialog.close() queues its close event. Remove copied private evidence
        // immediately, before that event restores focus and removes the shell.
        $('#ees-work-dialog .ew-dialog-body')?.replaceChildren();runtimeDetailContext=null;workUI.closeDialog();
      }
    }
  }
  function navigationScope(){return JSON.stringify([selectedCase()?.id || '',browsingSite,browsingSystem,definition()?.version,runView,historyCase?.id || '']);}
  function returnPanel(parentId=null){
    const entry=navigationTrail[navigationTrail.length-1];
    if(entry&&entry.scope===navigationScope()&&entry.to===selectedId()&&(!parentId||entry.from===parentId)){
      navigationTrail.pop();pendingReturn={...entry,to:entry.from};callbacks.selectWork(entry.from);
    }else if(parentId){
      // Direct sidebar entry has no parent-list visit to restore. Do not
      // turn an explicit parent return into a new J→T history entry.
      navigationTrail.length=0;pendingReturn=null;callbacks.selectWork(parentId);
    }
  }
  function renderDetail(){
    const dialog=$('#ees-work-dialog'),context=detailContext,data=definition(),n=data?.nodes?.[context?.nodeId];
    if(!dialog||!context||!n)return;
    if(context.attemptIndex===null){const records=selectedCase()?.jobs?.[context.nodeId]?.history || [];if(records.length)context.attemptIndex=records.length-1;}
    const body=dialog.querySelector('.ew-dialog-body'),scroll=body.scrollTop,focused=document.activeElement?.closest?.('[data-action]');
    const previous=focused?{action:focused.dataset.action,tab:focused.dataset.detailTab,attempt:focused.dataset.attemptIndex,call:focused.dataset.callIndex}:null;
    body.innerHTML=workExecutionDetailHTML(selectedCase(),n,{definition:data,...context,lookupError:snapshot.recordLookupError,assetsAvailable:state?.catalog?.assets_available,availableSkills:state?.catalog?.available_skills});
    const kind=dialog.querySelector('.ew-detail-record-kind');if(kind)kind.textContent=body.querySelector('[data-record-kind]')?.dataset.recordKind || '읽기 전용';
    body.scrollTop=scroll;
    if(previous)Array.from(body.querySelectorAll('[data-action]')).find(el=>el.dataset.action===previous.action&&el.dataset.detailTab===previous.tab&&el.dataset.attemptIndex===previous.attempt&&el.dataset.callIndex===previous.call)?.focus({preventScroll:true});
  }
  function panelFocusRestorer(origin){
    const scope=navigationScope(),id=selectedId(),tag=origin.tagName,attributes={...origin.dataset},controlId=origin.id;
    return ()=>{if(scope===navigationScope()&&id===selectedId())Array.from(document.querySelectorAll('#ees-work-content button,#ees-work-content summary')).find(el=>el.tagName===tag&&(controlId?el.id===controlId:Object.entries(attributes).every(([key,value])=>el.dataset[key]===value)))?.focus({preventScroll:true});};
  }
  function openDetail(id,tab){
    captureJobEdits();const data=definition(),n=data?.nodes?.[id];if(!n)return;
    const records=selectedCase()?.jobs?.[id]?.history || [];
    const context={nodeId:id,tab,attemptIndex:records.length?records.length-1:null,callIndex:0,scope:navigationScope()};detailContext=context;
    const restoreFocus=()=>{if(context.scope===navigationScope()&&selectedId()===id)Array.from(document.querySelectorAll('#ees-work-content [data-action="work_detail"]')).find(el=>el.dataset.nodeId===id&&el.dataset.detailTab===tab)?.focus({preventScroll:true});};
    workUI.dialog({title:n.name+' · 수행 상세',html:workExecutionDetailHTML(selectedCase(),n,{definition:data,...context,lookupError:snapshot.recordLookupError,assetsAvailable:state?.catalog?.assets_available,availableSkills:state?.catalog?.available_skills}),note:'읽기 전용 · 적용 구성과 저장된 실행 기록',readOnlyDetail:true,detailNavigation:true,restoreFocus}).then(()=>{if(detailContext===context)detailContext=null;});
    renderDetail();
  }

  function panelRegistration() {
    ensureHost();
    return {key:'workflow',label:'업무 진행',hostId:host.id,open:openHost,close:closeHost,isOpen:()=>Boolean(host?.isConnected),onChange:info=>{panelInfo=info;renderTabs();},focus:()=>$('#ees-work-close',host)?.focus({preventScroll:true})};
  }
  function readJobEdits(nodeId) {
    captureJobEdits();
    const context=editContext(nodeId || renderedEditContext?.scope.nodeId || selectedId());
    if(!context)return {nodeId:nodeId || selectedId(),caseId:selectedCase()?.id || '',revision:selectedCase()?.revision ?? -1,inputs:null,inputsChanged:false,document:null,documentChanged:false,conflict:false};
    const result=draftFor(context);
    if(!context.hasInputs)result.inputs=null;if(!context.hasDocument)result.document=null;
    if(result.inputError)result.conflict=true;
    return result;
  }
  function handleEvent(event) {
    const unhandled={handled:false,preventDefault:false},handled=(preventDefault=false)=>({handled:true,preventDefault});
    const target=event.target,inside=target.closest?.('[data-ees-work]');
    if(event.type==='scroll'){positionNav();return unhandled;}
    if(event.type==='resize'){updateLayout();return unhandled;}
    if(event.type==='pointerdown'){
      if(scopePicker&&!target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();
      if(target.closest?.('#ees-work-resizer')&&event.button===0){divider.dataset.pointer='';drag={id:event.pointerId,start:event.clientX,width:styledColumn.getBoundingClientRect().width};divider.setPointerCapture(event.pointerId);return handled(true);}
      return unhandled;
    }
    if(event.type==='pointermove'&&drag?.id===event.pointerId){preferredWidth=Math.max(280,Math.min(600,drag.width+drag.start-event.clientX));sizePanel();preferredWidth=width;return handled();}
    if(['pointerup','pointercancel','lostpointercapture'].includes(event.type)&&drag?.id===event.pointerId){drag=null;if(divider)delete divider.dataset.pointer;return handled();}
    if(event.type==='focusin'){if(scopePicker&&!target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();return unhandled;}
    if(event.type==='keyup')return ['Enter',' ','Spacebar'].includes(event.key)&&target.closest?.('#ees-work-entry [data-action=scope_toggle], #ees-work-scope-popover [data-action=scope_choose]')?handled(true):unhandled;
    if(event.type==='keydown'){
      const row=target.closest?.('tr[data-action=select]');if(row&&event.key==='Enter'&&!event.isComposing&&!target.closest('button,input,select,textarea')){row.click();return handled(true);}
      const dialog=$('#ees-work-dialog');
      if(dialog?.open&&event.key==='Escape'){workUI.closeDialog();return handled(true);}
      if(dialog?.open&&event.key==='Tab'){
        const controls=Array.from(dialog.querySelectorAll('button,input,textarea,select,a[href],summary,[tabindex]')).filter(el=>!el.disabled&&el.tabIndex>=0&&el.getClientRects().length),index=controls.indexOf(document.activeElement);
        const next=index<0?(event.shiftKey?controls.length-1:0):(index+(event.shiftKey?-1:1)+controls.length)%controls.length;
        (controls[next] || dialog).focus();return handled(true);
      }
      if(event.key==='Escape'&&target.closest?.('.ew-panel-menu')){const menu=target.closest('.ew-panel-menu');menu.open=false;menu.querySelector('summary')?.focus();return handled(true);}
      if(target.closest?.('#ees-work-resizer')&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){preferredWidth=event.key==='Home'?280:event.key==='End'?600:Math.max(280,Math.min(600,width+(event.key==='ArrowLeft'?24:-24)));sizePanel();preferredWidth=width;return handled(true);}
      const trigger=target.closest?.('#ees-work-entry [data-action=scope_toggle]'),popup=$('#ees-work-scope-popover'),inPicker=scopePicker&&popup?.contains(target);
      if(trigger||inPicker){
        const activate=['Enter',' ','Spacebar'].includes(event.key);
        if(!activate&&!['ArrowDown','ArrowUp','Home','End','Escape'].includes(event.key))return unhandled;
        if(activate){if(!event.repeat)(trigger || target.closest('[data-action=scope_choose]'))?.click();return handled(true);}
        if(event.key==='Escape'){closeScopePicker(true);return handled(true);}
        if(trigger){if(['ArrowDown','ArrowUp'].includes(event.key))openScopePicker(trigger.dataset.picker,event.key==='ArrowUp');return handled(true);}
        const options=Array.from(popup.querySelectorAll('[data-action=scope_choose]')),index=options.indexOf(target),next=event.key==='Home'?0:event.key==='End'?options.length-1:(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;
        options[next]?.focus();return handled(true);
      }
      if(event.currentTarget===document&&event.key==='Escape'&&navOpen){navOpen=false;renderNavigator();sidebar();}
      return unhandled;
    }
    if(target.closest?.('#ees-work-designer'))return unhandled;
    if(event.type==='input'&&target.id==='ees-work-job-search'){
      updateJobList({query:target.value,page:0},!event.isComposing);return handled();
    }
    if(['input','change'].includes(event.type)&&target.closest?.('#ees-work-inputs,#ees-work-document')){
      captureJobEdits(target);const edits=readJobEdits(),dirty=Boolean(edits.inputsChanged||edits.documentChanged),note=host?.querySelector('[data-work-dirty]');if(note)note.hidden=!dirty;
      const save=host?.querySelector('#ees-work-inputs-save');if(save){const needsSave=dirty||save.dataset.workSavedInputs!=='true';save.classList.toggle('ew-primary',needsSave);save.dataset.unavailable=String(!needsSave||save.dataset.workSaveBlocked==='true');save.disabled=busy||save.dataset.unavailable==='true';}
      const next=host?.querySelector('[data-work-next]');if(next)next.textContent=dirty&&next.dataset.workEditLocked!=='true'?'작성 중인 값이 있습니다. 입력을 반영한 뒤 점검하세요.':next.dataset.workSavedNext;
      const inputStatus=host?.querySelector('[data-work-input-status]');if(inputStatus)inputStatus.textContent=(dirty?'입력 변경됨 · 저장 전':save?.dataset.workSavedInputs==='true'?'저장됨':'저장 전')+' · '+(host?.querySelector('[data-work-recorded="true"]')?'이전 결과 있음':'점검 미수행');
      const run=host?.querySelector('[data-work-draft-sensitive]');if(run){run.classList.toggle('ew-primary',run.dataset.workRetryComplete!=='true'&&!dirty&&(!save||save.dataset.workSavedInputs==='true'));run.dataset.unavailable=String(dirty||edits.conflict||run.dataset.workBaseUnavailable==='true');run.disabled=busy||run.dataset.unavailable==='true';}
      return handled();
    }
    if(event.type==='change'&&target.id==='ees-v4-assignee-filter'){updateJobList({assignee:target.value});return handled();}
    if(event.type==='change'&&target.id==='ees-v4-sort'){updateJobList({sort:target.value});return handled();}
    if(event.type==='change'&&target.id==='ees-work-run-select'){callbacks.openCase(target.value);return handled();}
    if(event.type==='submit'&&inside){
      if(['ees-work-inputs','ees-work-document'].includes(target.id)){
        captureJobEdits(target);
        if(busy||target.dataset.workSaveBlocked==='true')return handled(true);
      }
      let values;try {values=target.id==='ees-work-inputs'&&renderedEditContext?.runtime?workExecutionInputsRead(target,renderedEditContext.schema):Object.fromEntries(new FormData(target));}catch(error){errorMessage=error.message;renderPanel();return handled(true);}
      if(target.id==='ees-work-case-create')callbacks.startCase();
      else if(target.id==='ees-work-inputs')callbacks.saveInputs(values,target.dataset.nodeId);
      else if(target.id==='ees-work-document')callbacks.saveDocument(values.document,target.dataset.nodeId);
      else return unhandled;
      return handled(true);
    }
    if(event.type!=='click')return unhandled;
    const summary=target.closest?.('summary[data-work-overlay]');
    if(summary&&inside){
      const html=Array.from(summary.parentElement.children).filter(el=>el!==summary).map(el=>el.outerHTML).join('');
      const records=[...(summary.parentElement.matches('[data-runtime-run]')?[summary.parentElement]:[]),...summary.parentElement.querySelectorAll('[data-runtime-run]')];
      const context={scope:navigationScope(),runIds:records.map(item=>item.dataset.runtimeRun)};runtimeDetailContext=context;
      workUI.dialog({title:summary.dataset.workOverlay,html,note:'읽기 전용 · 저장된 업무 자료',readOnlyDetail:true,restoreFocus:panelFocusRestorer(summary)}).then(()=>{if(runtimeDetailContext===context)runtimeDetailContext=null;});return handled(true);
    }
    const categoryButton=target.closest?.('[data-work-category]');
    if(categoryButton?.closest('#ees-work-entry')){
      const wanted=categoryButton.dataset.workCategory;
      if(category===wanted){navOpen=!navOpen;renderNavigator();return handled();}
      navOpen=true;callbacks.selectCategory(wanted);return handled();
    }
    const buttonTarget=target.closest?.('[data-action]');if(!buttonTarget?.closest('[data-ees-work]'))return unhandled;
    const action=buttonTarget.dataset.action;if(buttonTarget.disabled)return handled();
    if(action==='undo_ai_draft'){callbacks.undoAIDraft?.(buttonTarget.dataset.proposalId);}
    else if(action==='reference_toggle'){callbacks.toggleReference?.();}
    else if(action==='suggest'){callbacks.suggest?.(buttonTarget.dataset.question);}
    else if(action==='assistant_toggle'){assistantOpen=!assistantOpen;sizePanel();if(assistantOpen)$('#chat-input')?.focus();else $('#ees-v4-assistant-open')?.focus();renderContext();}
    else if(action==='native_new_chat'){$('#sidebar-new-chat-button')?.click();}
    else if(action==='native_history'){historyNavOpen=!historyNavOpen;document.body.dataset.eesNativeHistory=String(historyNavOpen);$('#sidebar-search-button')?.focus();}
    else if(action==='my_work'){const task=lineage(selectedId()).find(n=>n.type==='t');callbacks.showHistoryView(false);if(task)callbacks.selectWork(task.id);else openPanel();}
    else if(action==='find_work'){workUI.dialog({title:'워크플로우 찾기',html:Object.entries(categories).map(([group,label])=>'<section><h3>'+label+'</h3>'+visibleRoots(group).map(id=>button(state.catalog.nodes[id]?.name || id,'select','data-node-id="'+esc(id)+'" data-process-id="'+esc(id)+'"')).join('')+'</section>').join('')});}
    else if(action==='job_group'){const key=buttonTarget.dataset.group,groups={...(jobListState().groups || {})};groups[key]=!(groups[key] ?? !['done','simulation','excluded'].includes(key));updateJobList({groups});}
    else if(action==='job_more')updateJobList({moreWaiting:true});
    else if(action==='scope_toggle'){scopePicker===buttonTarget.dataset.picker?closeScopePicker(true):openScopePicker(buttonTarget.dataset.picker);}
    else if(action==='scope_choose'){
      if(!scopeReady()){closeScopePicker();updateScopeReadiness();return handled();}
      const kind=buttonTarget.dataset.picker,value=buttonTarget.dataset.value;
      if(kind!==scopePicker||!['site','system'].includes(kind)||!(kind==='site'?Object.hasOwn(state.catalog.sites,value):state.catalog.systems.includes(value)))return handled();
      closeScopePicker(true);if(value===(kind==='site'?browsingSite:browsingSystem))return handled();
      callbacks.switchScope(kind==='site'?value:browsingSite,kind==='system'?value:browsingSystem);
    }
    else if(action==='nav_close'||action==='nav_open'){navOpen=action==='nav_open';renderNavigator();}
    else if(action==='expand'){const run=state?.cases.find(c=>c.id===buttonTarget.dataset.caseId),data=run?.tree_nodes?{nodes:run.tree_nodes}:run&&run.id===selectedCase()?.id?selectedCase().definition:state?.catalog;toggleBranch(buttonTarget.dataset.nodeId,buttonTarget.dataset.expansionKey,data);renderNavigator();}
    else if(action==='panel_open')openPanel();
    else if(action==='panel_close')callbacks.closePanel();
    else if(action==='panel_tab')callbacks.selectPanel(buttonTarget.dataset.screen);
    else if(action==='open_case')callbacks.openCase(buttonTarget.dataset.caseId);
    else if(action==='start_case')callbacks.startCase();
    else if(action==='current_view'||action==='history_view')callbacks.showHistoryView(action==='history_view');
    else if(action==='history_case')callbacks.showHistory(buttonTarget.dataset.caseId);
    else if(action==='select'){
      if(buttonTarget.closest('#ees-work-dialog')&&!detailContext)workUI.closeDialog();
      if(buttonTarget.closest('#ees-work-content')&&selectedId()!==buttonTarget.dataset.nodeId)navigationTrail.push({scope:navigationScope(),from:selectedId(),to:buttonTarget.dataset.nodeId,action:'select',focusNode:buttonTarget.dataset.nodeId,wasComplete:node(buttonTarget.dataset.nodeId)?.type==='j'?workV4Facts(selectedCase(),definition(),snapshot.execution).state(node(buttonTarget.dataset.nodeId)).complete:undefined});
      else if(buttonTarget.closest('#ees-work-entry'))navigationTrail.length=0;
      callbacks.selectWork(buttonTarget.dataset.nodeId,buttonTarget.dataset.processId);
    }
    else if(action==='panel_back')returnPanel();
    else if(action==='panel_parent'){
      const parentId=node(selectedId())?.parent;
      if(parentId&&parentId===buttonTarget.dataset.nodeId&&node(parentId))returnPanel(parentId);
    }
    else if(action==='job_condition'){
      const expanded=new Set(jobListState().expanded || []),id=buttonTarget.dataset.nodeId;
      if(expanded.has(id))expanded.delete(id);else expanded.add(id);updateJobList({expanded:[...expanded]});
    }
    else if(action==='work_detail')openDetail(buttonTarget.dataset.nodeId,buttonTarget.dataset.detailTab || 'config');
    else if(['detail_tab','detail_attempt','detail_call'].includes(action)&&detailContext){
      if(action==='detail_tab')detailContext.tab=buttonTarget.dataset.detailTab;
      if(action==='detail_attempt'){detailContext.attemptIndex=Number(buttonTarget.dataset.attemptIndex);detailContext.callIndex=0;}
      if(action==='detail_call'){detailContext.callIndex=Number(buttonTarget.dataset.callIndex);if(buttonTarget.dataset.detailTab)detailContext.tab=buttonTarget.dataset.detailTab;}
      renderDetail();
    }
    else if(action==='job_filter')updateJobList({filter:buttonTarget.dataset.filter,page:0});
    else if(action==='job_page')updateJobList({page:Number(buttonTarget.dataset.page)});
    else if(action==='execution_refresh')callbacks.executionRefresh();
    else if(action==='execution_control')callbacks.executionControl(buttonTarget.dataset);
    else if(action==='run')callbacks.runJob(buttonTarget.dataset.nodeId,event);
    else if(action==='authoring_open'){if(runView==='current'&&callbacks.canAuthor?.())callbacks.openAuthoring?.(processId(),browsingSystem);}
    else if(action==='work_summary'||action==='work_records'){
      captureJobEdits();const c=selectedCase(),data=definition(),root=data.nodes[lineage(selectedId())[0]?.id];
      if(!root)return handled();
      const note=c?`게시된 절차 v${c.version} · 현재 진행 건의 저장 상태`:'게시된 절차 · 시작 전';
      const html=action==='work_summary'?workPanelNodeHTML(c,root,{definition:data,readOnly:true,history:true,site:c?.site || state.catalog.sites[browsingSite],system:browsingSystem}):Object.entries(c?.jobs || {}).filter(([,job])=>job.history?.length).map(([id,job])=>`<section class="ew-record-group"><h3>${esc(data.nodes[id]?.name || id)}</h3>${job.history.map(record=>`<p>${esc(record.at)} · ${record.kind==='human_confirmation'?'담당자 확인':record.kind==='execution_blocked'?'미수행 · 실행 연결 필요':record.kind==='simulation'||record.simulation?'모의 점검':'저장된 기록'} · ${esc(statuses[record.status] || record.status)} · ${esc(record.attempt)}차</p>`).join('')}</section>`).join('') || '<p>저장된 업무 기록이 없습니다.</p>';
      const context={scope:navigationScope(),runIds:[]};runtimeDetailContext=context;
      workUI.dialog({title:action==='work_summary'?root.name:'업무 기록',html,note,readOnlyDetail:true,restoreFocus:panelFocusRestorer(buttonTarget)}).then(()=>{if(runtimeDetailContext===context)runtimeDetailContext=null;});
    }
    else if(action==='discard_job_edits'||action==='rebase_job_edits'){const context=editContext(buttonTarget.dataset.nodeId);if(context){if(action==='discard_job_edits'){jobDrafts.discard(context.scope);runtimeRawInputs.delete(context.scope.key);runtimeInputErrors.delete(context.scope.key);aiReceipts.delete(context.scope.key);}else jobDrafts.rebase(context.scope,context.saved,context.revision);draftVersions.set(context.scope.key,(draftVersions.get(context.scope.key)||0)+1);renderedEditContext=null;renderPanel();}}
    else return unhandled;
    return handled();
  }
  function render(value) {readSnapshot(value);sidebar();renderNavigator();renderContext();renderPanel();}
  function prepare(value) {readSnapshot(value);sidebar();updateScopeReadiness();}
  function sync(value) {prepare(value);if(state&&snapshot.browseActive&&chatRoute()){renderContext();callbacks.registerPanel();}positionNav();}
  function updateLayout() {positionNav();sizePanel();}
  function detach() {workUI.closeDialog();closeScopePicker();closeHost();$('#ees-work-context')?.remove();$('#ees-v4-suggestions')?.remove();delete document.body.dataset.eesNativeHistory;}
  function reset() {
    detach();panelPositions.clear();panelDisclosures.clear();navigationTrail.length=0;pendingReturn=null;detailContext=null;runtimeDetailContext=null;treeExpansions.clear();jobDrafts.clear();aiReceipts.clear();runtimeRawInputs.clear();runtimeInputErrors.clear();draftVersions.clear();jobLists.clear();stepSummaries.clear();selectedSteps.clear();renderedEditContext=null;renderedPanelTarget='';snapshot={};state=null;serverSource=null;historySource=null;historyCase=null;navOpen=false;busy=false;width=0;preferredWidth=null;panelInfo=null;drag=null;
    host=null;divider=null;
    ['ees-work-entry','ees-work-admin-link','ees-work-navigator'].forEach(id=>document.getElementById(id)?.remove());
  }
  return Object.freeze({render,prepare,sync,renderNavigator:value=>{readSnapshot(value);renderNavigator();},renderPanel:value=>{readSnapshot(value);renderPanel();},setBusy,openPanel,closeHost,reset,readJobEdits,draftVersion,applyAIDraft,undoAIDraft,adoptPreviewDraft,handleEvent,updateLayout,panelRegistration,revealSelection,closeScopePicker,detach,setNavigatorOpen:value=>{navOpen=Boolean(value);},updateScopeReadiness});
}
