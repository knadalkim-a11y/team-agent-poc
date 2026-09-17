/* Pure rendering helpers shared by the native workflow view and designer. */
const workUI = (() => {
  const $ = (s, p = document) => p.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const categories = {setup:'셋업',ops:'운영',incident:'장애대응'};
  const levels = {p:'프로세스',t:'태스크',j:'잡'};
  const statuses = {unstarted:'시작 전',ready:'준비',pending:'대기',in_progress:'진행 중',running:'실행 중',success:'완료',completed:'완료',passed:'완료',failed:'실패',blocked:'진행 조건 확인',skipped:'적용 제외',draft:'초안',review:'검토 필요'};
  const badge = value => `<span class="ew-badge" data-status="${esc(value)}">${esc(statuses[value] || value || '대기')}</span>`;
  const button = (label, action, attrs = '') => `<button type="button" data-action="${action}" ${attrs}>${esc(label)}</button>`;
  const finished = c => ['passed','completed','success','skipped'].includes(c?.status);
  function siteLabel(site) {return [site?.country,site?.name || site?.factory].filter(Boolean).join(' · ');}
  const lineage = (id, data) => {const result = [], seen = new Set(); while (id && data?.nodes[id] && !seen.has(id)) {seen.add(id); result.unshift(data.nodes[id]); id = data.nodes[id].parent;} return result;};
  function treeHTML(data, ids, options = {}, depth = 0) {
    const {editing = false, selectedId = '', collapsed = new Set(), expanded = new Map(), statuses: nodeStatuses = {}, summaries = {}, expansionKey = '', run = null} = options;
    return (ids || []).map(id=>{
      const n=data.nodes[id];if(!n||depth>3)return '';
      const children=n.children || [],open=editing?!collapsed.has(id):Boolean(expanded.get(id)),active=selectedId===id;
      const ns=nodeStatuses[id],itemStatus=ns?.status || 'unstarted';
      const count=ns?.progress,failed=ns?.failed_count || 0,excluded=ns?.excluded_count || 0;
      const summary=summaries[id] || (ns?`${count?.done || 0}/${count?.total || 0} 완료${excluded?' · 제외 '+excluded:''}`:'시작 전');
      return `<div class="ew-tree-row" style="--depth:${depth}">${children.length?button(open?'⌄':'›','expand',`data-node-id="${esc(id)}" data-expansion-key="${esc(expansionKey)}" data-case-id="${esc(run?.id || '')}" class="ew-expand" aria-label="${esc(n.name)} ${open?'접기':'펼치기'}" aria-expanded="${open}"`):'<span class="ew-expand" aria-hidden="true"></span>'}<button type="button" data-action="${editing?'edit_node':'select'}" data-node-id="${esc(id)}" data-process-id="${esc(lineage(id,data)[0]?.id || id)}" aria-current="${active?'step':'false'}"><span class="ew-type" aria-label="${levels[n.type]}">${esc(n.type.toUpperCase())}</span><span class="ew-tree-label">${esc(n.name)}${!editing&&children.length?`<small class="ew-tree-meta">${ns?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${failed?'확인 필요 '+failed:esc(statuses[itemStatus])}</span> · `:''}${esc(summary)}</small>${n.type==='p'&&run?`<small class="ew-tree-meta">${esc(run.created_at?.slice(0,10) || '기존 실행')} · v${esc(run.version)}</small>`:''}`:''}</span>${!editing&&!children.length?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${esc(statuses[itemStatus])}</span>`:''}</button></div>${children.length&&open?treeHTML(data,children,options,depth+1):''}`;
    }).join('');
  }
  return Object.freeze({$, esc, clone, categories, levels, statuses, badge, button, finished, siteLabel, lineage, treeHTML});
})();

/* One saved record supplies both the summary and its folded evidence. */
function workPanelNodeHTML(c,n,{definition=c?.definition,readOnly=false,history=false,previewActions='',site=c?.site,system=c?.system,previewBlocked=false,draft=null}={}) {
  const {esc,levels,statuses,badge,button,finished,lineage,siteLabel}=workUI;
  const preview=!c,locked=readOnly||history||finished(c),nodes=definition.nodes,tools=definition.tools || {};
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
  const unavailable=item=>item.mode==='tool'&&(!(item.tools || []).length||(item.tools || []).some(id=>!tools[id]||tools[id].adapter!=='mock'||tools[id].source==='open_webui'||tools[id].enabled===false));
  const modeLabel=item=>item.mode==='manual'?'사람 확인':item.mode==='draft'?'초안 검토':unavailable(item)?'실행 연결 필요':'모의 점검';
  const nameOf=id=>nodes[id]?.name || '선행 업무';
  const prerequisites=item=>Array.from(new Set(lineage(item.id,definition).flatMap(parent=>parent.deps || [])));
  const missingFor=item=>preview?prerequisites(item).filter(id=>nodes[id]&&applies(nodes[id])):c.node_states?.[item.id]?.missing || [];
  const reasonFor=item=>{
    const saved=c?.jobs?.[item.id] || {},s=nodeState(item),missing=missingFor(item);
    if(s==='skipped')return '현장 조건에 따라 적용 제외';
    if(s==='passed')return '완료 기록을 확인할 수 있습니다.';
    if(saved.blocked_reason)return saved.blocked_reason;
    if(missing.length)return '선행 작업 확인: '+missing.map(nameOf).join(', ');
    if(unavailable(item))return '업무 실행 연결이 없어 점검할 수 없습니다.';
    const values=valuesFor(item),missingInputs=fieldsFor(item).filter(key=>!String(values[key] ?? '').trim());
    if(missingInputs.length)return '입력 필요: '+missingInputs.map(key=>labels[key]).join(', ');
    if(item.mode==='manual')return '업무 내용을 직접 확인한 뒤 완료를 기록하세요.';
    if(item.mode==='draft')return saved.document?'저장한 초안을 검토한 뒤 완료를 기록하세요.':'초안을 작성해 반영한 뒤 내용을 검토하세요.';
    if(s==='failed')return '실패한 점검을 확인한 뒤 다시 점검하세요.';
    if(s==='blocked')return '입력·연결·접근 권한과 선행 작업을 확인하세요.';
    return '점검 대상을 확인한 뒤 진행하세요.';
  };
  const selectButton=(item,text,primary=false)=>button(text || item.name,'select','data-node-id="'+esc(item.id)+'" class="'+(primary?'ew-primary ':'')+'ew-work-link"');
  const runButton=(text,disabled=false,primary=true,attrs='')=>button(text,'run','id="ees-work-run" data-node-id="'+esc(n.id)+'" class="'+(primary?'ew-primary':'')+'" data-mutation '+attrs+(disabled?' disabled data-unavailable="true"':''));
  const breadcrumb='<nav class="ew-work-path" aria-label="업무 위치">'+path.slice(0,-1).map(item=>history?'<span>'+esc(item.name)+'</span>':selectButton(item)).join('<span aria-hidden="true"> / </span>')+(path.length>1?'<span aria-hidden="true"> / </span>':'')+'<span>'+levels[n.type]+'</span></nav>';
  const header=breadcrumb+'<div class="ew-heading ew-work-heading"><h2 class="ew-title">'+esc(n.name)+'</h2>'+badge(nodeState(n))+'</div><p class="ew-work-scope">'+esc([siteLabel(site),system].filter(Boolean).join(' · '))+' · '+(preview?'시작 전':'예시 업무')+'</p>';
  const criterion='<div class="ew-work-criterion"><span>완료 조건</span><p>'+esc(n.rule || '등록된 완료 조건을 확인해 주세요.')+'</p></div>';
  // Node instructions are business-facing work guidance; configuration lists
  // and Skill/prompt source bodies belong in Workspace, not this surface.
  const guidance=path.filter(item=>String(item.instructions || '').trim()).map(item=>'<p>'+esc(item.instructions)+'</p>').join('');
  const guidanceHTML=guidance?'<details class="ew-work-guidance"><summary>업무 수행 안내</summary>'+guidance+'</details>':'';
  const deps=prerequisites(n),depsHTML=deps.length?'<div class="ew-work-prerequisites"><span>선행 작업</span>'+deps.map(id=>'<span>'+esc(nameOf(id))+(preview?'':' · '+esc(statuses[c.node_states?.[id]?.status] || '확인 필요'))+'</span>').join('')+'</div>':'';
  const taskProgress=item=>{
    const eligible=(item.children || []).map(id=>nodes[id]).filter(child=>child&&applies(child)&&(child.type==='j'||descendants(child).some(applies)));
    return {total:eligible.length,done:eligible.filter(child=>nodeState(child)==='passed').length,excluded:(item.children || []).length-eligible.length};
  };
  if(n.type!=='j') {
    const count=taskProgress(n),unit=n.type==='p'?'태스크':'잡';
    const remaining=descendants(n).filter(item=>applies(item)&&nodeState(item)!=='passed');
    const failed=remaining.find(item=>nodeState(item)==='failed');
    const ready=remaining.filter(item=>item.mode==='tool'&&nodeState(item)!=='failed'&&!unavailable(item)&&!missingFor(item).length&&fieldsFor(item).every(key=>String(valuesFor(item)[key] ?? '').trim()));
    const next=failed || remaining.find(item=>!missingFor(item).length) || remaining[0];
    const directFor=item=>children.find(child=>descendants(child).some(leaf=>leaf.id===item.id));
    const counts={simulation:0,human:0,unavailable:0};remaining.forEach(item=>counts[item.mode!=='tool'?'human':unavailable(item)?'unavailable':'simulation']++);
    const progress='<div class="ew-work-progress" data-work-section="progress"><div><span>'+unit+' 진행</span><strong data-work-done="'+count.done+'" data-work-total="'+count.total+'">'+(preview?'시작 전 · ':'')+count.done+' / '+count.total+' 완료</strong></div>'+(!preview&&count.total?'<progress aria-label="'+unit+' 완료 수" value="'+count.done+'" max="'+count.total+'"></progress>':'')+(count.excluded?'<p class="ew-muted">적용 제외 '+count.excluded+'개</p>':'')+(!count.total?'<p class="ew-muted">'+(children.length?'이 범위는 적용 제외입니다.':'등록된 하위 업무가 없습니다.')+'</p>':'')+'</div>';
    const rows=children.map(child=>{
      const childState=c?.node_states?.[child.id] || {},detail=child.type==='j'?reasonFor(child):descendants(child).some(j=>nodeState(j)==='failed')?'실패한 점검 확인 필요':nodeState(child)==='blocked'?'진행 조건 확인 필요':'';
      const jobCount=childState.progress || {done:0,total:descendants(child).filter(applies).length};
      const link=history?'<details class="ew-history-node"><summary>'+esc(child.name)+'</summary>'+workPanelNodeHTML(c,child,{definition,readOnly:true,history:true})+'</details>':selectButton(child);
      if(history)return '<tr><td colspan="3">'+link+'</td></tr>';
      return '<tr'+(nodeState(child)==='failed'?' class="ew-work-problem"':'')+'><td>'+link+(!history&&detail&&!['passed','unstarted'].includes(nodeState(child))?'<small class="ew-work-row-note">'+esc(detail)+'</small>':'')+'</td><td>'+(child.type==='t'?jobCount.done+'/'+jobCount.total+(childState.excluded_count?'<small>제외 '+childState.excluded_count+'</small>':''):esc(modeLabel(child)))+'</td><td>'+badge(nodeState(child))+'</td></tr>';
    }).join('');
    const table='<section class="ew-work-list"><h3>'+unit+' 현황</h3><table><thead><tr><th scope="col">'+unit+'</th><th scope="col">'+(n.type==='p'?'잡 완료':'수행 방식')+'</th><th scope="col">상태</th></tr></thead><tbody>'+rows+'</tbody></table></section>';
    let primary='',secondary='',nextText='';
    if(!locked&&next){
      const direct=directFor(next);
      if(failed){primary=direct?selectButton(direct,'문제 확인',true):'';nextText='실패한 점검과 필요한 조치를 먼저 확인하세요.';if(ready.length)secondary=runButton('가능한 점검 진행',previewBlocked,false);}
      else if(ready.length){primary=runButton('계속 진행',previewBlocked);nextText='선행 조건을 충족하는 모의 점검을 진행합니다. 사람 확인은 별도로 남습니다.';}
      else{primary=direct?selectButton(direct,'다음 업무 열기',true):'';nextText=reasonFor(next);}
    }else if(locked)nextText=count.total?'완료 결과와 근거를 확인할 수 있습니다.':'적용 대상 업무가 없습니다.';
    const execution=!locked&&remaining.length?'<details class="ew-work-execution" data-work-section="execution-scope"><summary>진행 범위 · 모의 점검</summary><p>모의 점검 <span data-work-count="simulation">'+counts.simulation+'</span>개 · 사람 확인/검토 <span data-work-count="human">'+counts.human+'</span>개 · 실행 연결 필요 <span data-work-count="unavailable">'+counts.unavailable+'</span>개</p><p class="ew-muted">적용 대상 미완료 잡의 구성입니다. 이번 실행 예정 수가 아닙니다. 실행 시 입력·권한·연결을 다시 확인하며 사람 확인의 후속은 대기합니다. 독립적인 다른 점검은 진행할 수 있습니다.</p></details>':'';
    return header+(n.description?'<p class="ew-work-goal">'+esc(n.description)+'</p>':'')+(preview?previewActions:'')+progress+(n.type==='t'?criterion+depsHTML:'')+table+(n.type==='p'?criterion:'')+guidanceHTML+execution+(nextText?'<div class="ew-work-next"><span>다음 할 일</span><p>'+esc(nextText)+'</p></div>':'')+(primary||secondary?'<div class="ew-work-actions">'+secondary+primary+'</div>':'');
  }
  const dataHTML=(values,document)=>Object.entries(values || {}).filter(([key])=>Object.hasOwn(labels,key)).map(([key,value])=>'<p><strong>'+esc(labels[key])+'</strong> · '+esc(value)+'</p>').join('')+(document?'<p><strong>저장된 초안</strong></p><pre>'+esc(document)+'</pre>':'');
  const checksHTML=checks=>(checks || []).map((check,index)=>'<div class="ew-check"><div class="ew-heading"><strong>'+esc(check.name || tools[check.id || check.tool_id || check.tool]?.name || '점검 '+(index+1))+'</strong>'+(check.status==='skipped'?'<span class="ew-badge" data-status="skipped">미수행</span>':badge(check.status))+'</div><p>'+esc(check.message || check.detail || check.summary || '')+'</p>'+(check.input!==undefined?'<p>점검 대상 · '+esc(check.input)+'</p>':'')+(check.at?'<p>확인 시각 · '+esc(check.at)+'</p>':'')+'</div>').join('');
  const recordKind=record=>record.kind==='human_confirmation'?'담당자 확인':record.kind==='simulation'||record.simulation?'모의 점검':'저장된 실행';
  const recordHTML=record=>'<p class="ew-muted">'+esc(record.at || record.completed_at || '실행 시각 미기록')+' · '+recordKind(record)+'</p>'+(record.detail?'<p>'+esc(record.detail)+'</p>':'')+checksHTML(record.checks)+dataHTML(record.inputs,record.document);
  const records=job.history || [],last=records[records.length-1],checks=job.checks || [];
  const latest=!preview&&applies(n)&&!['pending','review'].includes(job.status)&&last&&last.status===job.status&&last.attempt===job.attempt&&(n.mode!=='tool'||checks.length)?last:null;
  const previous=latest?records.slice(0,-1):records;
  const failure=latest?.checks?.find(check=>['failed','blocked'].includes(check.status));
  const resultText=latest?(latest.kind==='human_confirmation'?latest.detail || '담당자 확인이 기록되었습니다.':failure?.detail || failure?.message || '모의 점검을 완료했습니다.'):!applies(n)?'현장 조건에 따라 적용 제외된 잡입니다.':records.length?'현재 조건의 유효한 결과가 없습니다. 재점검이 필요합니다.':'아직 수행한 결과가 없습니다.';
  const result='<section class="ew-work-result" data-work-section="current-result"><h3>최근 결과</h3><p>'+esc(resultText)+'</p>'+(latest?'<p class="ew-muted">'+esc(latest.at || latest.completed_at || '실행 시각 미기록')+' · '+recordKind(latest)+'</p><details class="ew-work-detail"><summary>수행 내역'+(failure?' · 확인 필요':'')+'</summary>'+recordHTML(latest)+'</details>':'<span class="ew-muted">'+(records.length?'이전 결과는 실행 이력에 보존됩니다.':'미수행')+'</span>')+'</section>';
  const inputs={...valuesFor(n),...(draft?.inputs || {})},fields=fieldsFor(n),document=draft?.document ?? job.document ?? '';
  const nodeId=' data-node-id="'+esc(n.id)+'"',changed=Boolean(draft?.inputsChanged||draft?.documentChanged),conflict=Boolean(draft?.conflict);
  const unavailableNow=previewBlocked||!applies(n)||missingFor(n).length||unavailable(n)||conflict;
  const inputHTML=!locked&&applies(n)&&fields.length?'<form id="ees-work-inputs" class="ew-work-form"'+nodeId+'><h3>업무 입력</h3>'+fields.map(key=>'<label>'+labels[key]+'<input name="'+key+'" value="'+esc(inputs[key] || '')+'" autocomplete="off"></label>').join('')+'<button id="ees-work-inputs-save" type="submit" data-mutation'+(previewBlocked||conflict?' disabled data-unavailable="true"':'')+'>입력 반영</button><p class="ew-muted">입력 반영 후 점검하세요. 비밀번호·접속 키는 입력하지 마세요.</p></form>':'';
  const documentHTML=!locked&&applies(n)&&n.mode==='draft'?'<form id="ees-work-document" class="ew-work-form"'+nodeId+'><label>검토할 초안<textarea name="document" rows="6" placeholder="대화로 작성을 요청하거나 직접 입력하세요.">'+esc(document)+'</textarea></label><button type="submit" data-mutation'+(previewBlocked||conflict?' disabled data-unavailable="true"':'')+'>초안 반영</button></form>':'';
  const conflictHTML=conflict?'<div class="ew-notice" role="alert">저장된 값이 변경되었습니다. 작성 중인 입력은 보존했습니다. 최신 저장값과 비교한 뒤 다시 반영하세요.<details><summary>최신 저장값</summary>'+dataHTML(valuesFor(n),job.document)+'</details>'+button('저장값으로 되돌리기','discard_job_edits',nodeId)+button('현재 입력 계속 편집','rebase_job_edits',nodeId)+'</div>':'';
  const formHTML=inputHTML+documentHTML;
  const dirtyHTML=formHTML?'<p class="ew-work-dirty" data-work-dirty role="status"'+(changed?'':' hidden')+'>작성 중인 값이 있습니다. 반영한 뒤 점검하세요.</p>':'';
  const editable=nodeState(n)==='passed'&&formHTML?'<details class="ew-work-edit"><summary>입력 변경</summary>'+formHTML+'</details>':formHTML;
  const saved=locked?'<details class="ew-work-detail"><summary>저장된 입력과 초안</summary>'+dataHTML(valuesFor(n),job.document)+'</details>':'';
  const old=previous.length?'<details class="ew-history" data-work-section="history"><summary>이전 시도 ('+previous.length+') · 현재 판정 아님</summary>'+[...previous].reverse().map(record=>'<details class="ew-history-attempt"><summary>'+esc(record.attempt || '?')+'차 · '+esc(statuses[record.status] || record.status)+' · '+esc(record.at || record.completed_at || '시각 미기록')+'</summary>'+recordHTML(record)+'</details>').join('')+'</details>':'';
  const planned=!latest&&(n.tools || []).length?'<details class="ew-work-detail"><summary>예정된 점검</summary><ol>'+(n.tools || []).map((id,index)=>'<li>'+esc(tools[id]?.name || '점검 '+(index+1))+'</li>').join('')+'</ol></details>':'';
  const next=locked?'저장된 결과와 근거를 확인할 수 있습니다.':changed?'작성 중인 값이 있습니다. 입력을 반영한 뒤 점검하세요.':reasonFor(n);
  let action='';
  const baseUnavailable=Boolean(unavailableNow||(n.mode==='draft'&&!job.document));
  if(!locked&&nodeState(n)!=='passed'&&applies(n))action=runButton(n.mode==='manual'?'확인 완료':n.mode==='draft'?'검토 완료':job.attempt?'다시 점검':'점검 실행',baseUnavailable||changed,true,'data-work-draft-sensitive data-work-base-unavailable="'+baseUnavailable+'"');
  else if(!history&&n.parent)action=selectButton(nodes[n.parent],'상위 업무 보기',true);
  return header+(n.description?'<p class="ew-work-goal">'+esc(n.description)+'</p>':'')+(preview?previewActions:'')+result+conflictHTML+editable+dirtyHTML+criterion+depsHTML+guidanceHTML+saved+planned+old+'<div class="ew-work-next"><span>다음 할 일</span><p data-work-next data-work-saved-next="'+esc(locked?'저장된 결과와 근거를 확인할 수 있습니다.':reasonFor(n))+'">'+esc(next)+'</p></div>'+(action?'<div class="ew-work-actions">'+action+'</div>':'');
}

/* Session-only drafts never update a server snapshot or completed evidence. */
function createWorkInputDrafts() {
  const entries=new Map(),copy=value=>JSON.parse(JSON.stringify(value));
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function edit(scope,saved,patch,revision) {
    const entry=entries.get(scope.key) || {scope:copy(scope),base:copy(saved),revision,inputs:{}};
    if(patch.inputs)Object.assign(entry.inputs,patch.inputs);
    if(Object.hasOwn(patch,'document'))entry.document=patch.document;
    entries.set(scope.key,entry);
  }
  function read(scope,saved,revision) {
    const entry=entries.get(scope.key);
    if(!entry)return {nodeId:scope.nodeId,caseId:scope.caseId || '',revision,inputs:{...saved.inputs},inputsChanged:false,document:saved.document,documentChanged:false,conflict:false};
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
function createWorkView({callbacks}) {
  const {$, esc, clone, categories, levels, statuses, badge, button, finished, siteLabel} = workUI;
  let snapshot = {}, state = null, category = 'setup', browsingSystem = 'EMS', browsingSite = '', browseNodeId = '', runView = 'current', historyCase = null, errorMessage = '', busy = false;
  let serverSource=null,historySource=null;
  let navOpen = true, scopePicker = '', host = null, divider = null, panelOpen = false, width = 520, panelInfo = null, drag = null, styledColumn = null;
  // Expansion belongs to the factory scope and the retained case version.
  const treeExpansions = new Map(),jobDrafts=createWorkInputDrafts();
  let renderedEditContext=null;
  const chatId = () => snapshot.chatId || '';
  const chatRoute = () => Boolean(snapshot.chatRoute);
  const currentCase = () => state?.case;
  const selectedCase = () => snapshot.selectedCaseId&&state?.case?.id===snapshot.selectedCaseId?state.case:null;
  const selectedId = () => snapshot.selectedId || '';
  const definition = () => selectedCase()?.definition || state?.catalog;
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
    const fields=Array.from(new Set((n.tools || []).map(tool=>n.bindings?.[tool] || data.tools?.[tool]?.input).filter(key=>['db','ap','site','interface'].includes(key))));
    const all={db:site?.db || '',ap:site?.ap || '',site:[site?.country,site?.name,site?.line].filter(Boolean).join(' · '),interface:site?.interface?system+' · '+site.name+' 시스템 간 연계 · 예시':'',...(c?.jobs?.[id]?.inputs || {})};
    const scope={caseId,nodeId:id,siteId:site?.id || browsingSite,system,processId:process,version};
    scope.key=JSON.stringify([caseId,scope.siteId,system,process,id]);
    return {scope,saved:{inputs:Object.fromEntries(fields.map(key=>[key,all[key]])),document:c?.jobs?.[id]?.document || ''},revision:c?.revision ?? -1,hasInputs:fields.length>0,hasDocument:n.mode==='draft'};
  }
  function captureJobEdits(changedField=null) {
    if(!renderedEditContext||!host)return;
    const inputs=host.querySelector('#ees-work-inputs'),documentForm=host.querySelector('#ees-work-document'),patch={};
    // Capture the input event even when the user has restored defaultValue:
    // the earlier keystroke may still be present in the session draft.
    if(inputs){const changed=Array.from(inputs.querySelectorAll('input')).filter(field=>field===changedField||field.value!==field.defaultValue);if(changed.length)patch.inputs=Object.fromEntries(changed.map(field=>[field.name,field.value]));}
    const text=documentForm?.querySelector('textarea');if(text&&(text===changedField||text.value!==text.defaultValue))patch.document=text.value;
    if(patch.inputs||Object.hasOwn(patch,'document'))jobDrafts.edit(renderedEditContext.scope,renderedEditContext.saved,patch,renderedEditContext.revision);
  }
  function draftFor(context) {return context?jobDrafts.read(context.scope,context.saved,context.revision):null;}
  function adoptPreviewDraft(caseId,nodeId) {
    if(typeof caseId!=='string'||!caseId||!nodeId)return;
    captureJobEdits();
    const data=definition(),n=data?.nodes?.[nodeId];if(!n)return;
    const scope={siteId:browsingSite,system:browsingSystem,processId:workUI.lineage(nodeId,data)[0]?.id,version:data.version,caseId:''};
    // All drafts of this exact preview become drafts of its first case, even
    // when first execution was requested from its parent process or task.
    jobDrafts.adoptPreview(scope,caseId);
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
    if(host)host.setAttribute('aria-busy',String(busy));
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
    const site=data.sites[browsingSite],label=siteLabel(site);
    updateNavHTML(container,`<div class="ew-scope-card">${['site','system'].map(kind=>`<button type="button" id="ees-work-${kind}-trigger" class="ew-scope-trigger" data-action="scope_toggle" data-picker="${kind}" data-value="${esc(kind==='site'?browsingSite:browsingSystem)}" value="${esc(kind==='site'?browsingSite:browsingSystem)}" aria-haspopup="dialog" aria-expanded="${scopePicker===kind}" aria-controls="ees-work-scope-popover" aria-label="${kind==='site'?'작업 공장 선택: '+esc(label):'시스템 선택: '+esc(browsingSystem)}"><span class="ew-scope-icon">${scopeIcon(kind)}</span><span class="ew-scope-text"><span class="ew-scope-label">${kind==='site'?'작업 공장':'시스템'}</span><span class="ew-scope-value">${kind==='site'?`<span>${esc(site?.name || site?.factory || label)}</span><small>${esc(site?.country || '')}</small>`:esc(browsingSystem)}</span></span><span class="ew-scope-chevron">${scopeIcon('chevron')}</span></button>`).join('<div class="ew-scope-divider"></div>')}</div>`);
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
    $('#ees-work-navigator')?.remove();
    const entry=$('#ees-work-entry');if(!entry)return;
    const data=state?.catalog;
    if(!data){if(!entry.firstChild)entry.innerHTML='<p class="ew-caption">업무</p><p class="ew-muted">업무 절차를 불러오는 중입니다.</p>';updateScopeReadiness();return;}
    if(!entry.querySelector('.ew-scope-pickers'))entry.innerHTML='<div class="ew-scope-pickers"></div><div class="ew-work-navigation"></div>';
    renderScopeControls(entry.querySelector('.ew-scope-pickers'),data);
    const html=`<p class="ew-caption">업무</p>${Object.entries(categories).map(([id,label])=>{
      const roots=visibleRoots(id);
      return `<button type="button" class="ew-category" data-work-category="${id}" aria-expanded="${navOpen&&category===id}"><span>${label}</span><span aria-hidden="true">${navOpen&&category===id?'⌄':'›'}</span></button>${navOpen&&category===id?`<div class="ew-inline-tree" id="ees-work-tree">${roots.map(p=>{const c=chosenCase(p),tree=c?.tree_nodes?{nodes:c.tree_nodes}:c&&c.id===selectedCase()?.id?selectedCase().definition:data;return treeHTML(tree,[p],c);}).join('') || '<p class="ew-muted">게시된 절차가 없습니다.</p>'}</div>`:''}`;
    }).join('')}`;
    // Tree refreshes do not replace an open picker or its focused option.
    updateNavHTML(entry.querySelector('.ew-work-navigation'),html);
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
    const site=c?.site || state.catalog.sites[browsingSite];
    const html=`<button type="button" data-action="nav_open" aria-label="업무 트리 펼치기"><span class="ew-context-dot"></span><strong>${esc(siteLabel(site))} · ${esc(browsingSystem)}</strong><span>${esc(lineage(selectedId()).map(n=>n.name).join(' › '))}</span></button>${button('업무 패널','panel_open','id="ees-work-context-open"')}<small>${c?c.chat_id?'이 대화에 연결됨':'첫 메시지를 보내면 이 대화에 연결됩니다':'절차 미리보기 · 시작 전'}</small>`;
    if(strip.innerHTML!==html)strip.innerHTML=html;
  }

  function ensureHost() {
    if (host) return;
    host = document.createElement('aside'); host.id = 'ees-work-panel'; host.dataset.eesWork = ''; host.setAttribute('aria-label','업무 진행 패널');
    host.innerHTML = `<header><div class="ew-heading"><h2>업무 패널</h2>${button('닫기','panel_close','id="ees-work-close" aria-label="업무 패널 닫기"')}</div><nav id="ees-work-tabs" aria-label="업무 화면"></nav></header><div id="ees-work-content" class="ew-scroll"></div>`;
    divider = document.createElement('div'); divider.id = 'ees-work-resizer'; divider.tabIndex = 0; divider.setAttribute('role','separator'); divider.setAttribute('aria-label','대화와 업무 패널 너비 조절'); divider.setAttribute('aria-orientation','vertical'); divider.setAttribute('aria-controls',host.id); divider.innerHTML = '<span></span>';

  }
  function sizePanel() {
    if (!host || !panelOpen) return; const layout = chatLayout(); if (!layout) return;
    const narrow = layout.row.getBoundingClientRect().width < 850;
    host.classList.toggle('ew-narrow',narrow); divider.hidden = narrow;
    width = Math.max(340, Math.min(width, 760, Math.max(340, layout.row.getBoundingClientRect().width - 430)));
    host.style.width = narrow ? 'min(100vw, 520px)' : width + 'px'; host.style.flexBasis = narrow ? 'auto' : width+'px';
    divider.setAttribute('aria-valuenow', String(Math.round(width))); divider.setAttribute('aria-valuemin','340'); divider.setAttribute('aria-valuemax','760');
  }
  function openHost() {const layout = chatLayout(); if (!layout || !state || !selectedId()) return; ensureHost(); panelOpen = true; styledColumn=layout.column;styledColumn.classList.add('ees-work-chat-column');layout.row.append(divider,host); sizePanel();}
  function closeHost() {captureJobEdits();panelOpen = false; drag=null;if(divider)delete divider.dataset.pointer;host?.remove(); divider?.remove();styledColumn?.classList.remove('ees-work-chat-column');styledColumn=null;}
  function renderTabs() {
    if (!host) return; const tabs = $('#ees-work-tabs',host), screens = panelInfo?.screens || window.__eesWorkPanelV1?.list?.(chatId()) || [{key:'workflow',label:'업무 진행'}];
    const html = screens.map(screen => button(screen.label,'panel_tab',`data-screen="${esc(screen.key)}" aria-selected="${screen.key==='workflow'}"`)).join('');
    if (tabs.innerHTML !== html) tabs.innerHTML = html;
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
    if(historyCase){const n=historyCase.definition.nodes[historyCase.process_id];return `${button('실행 목록으로','history_view')}<p class="ew-notice">이전 실행 · 읽기 전용<br>가운데 대화와 왼쪽 트리는 현재 실행을 유지합니다.</p><p class="ew-muted">${esc(siteLabel(historyCase.site))} · ${esc(historyCase.system)}<br>${esc(runLabel(historyCase))}</p>${readOnlyNode(historyCase,n,true)}`;}
    return `<h2 class="ew-title">실행 이력</h2><p class="ew-muted">${esc(siteLabel(state.catalog.sites[browsingSite]))} · ${esc(browsingSystem)} · ${esc(nameOf(p))}</p><div class="ew-case-list">${cases.map(item=>`<button type="button" data-action="history_case" data-case-id="${esc(item.id)}" ${item.id===c?.id?'disabled':''}><strong>${esc(runLabel(item))}</strong><span>${item.id===c?.id?'현재 실행 · ':''}${esc(statuses[item.status])} · ${item.progress.done}/${item.progress.total} 완료</span></button>`).join('') || '<p class="ew-notice">아직 기록된 실행이 없습니다.</p>'}</div>`;
  }
  function previewHTML() {
    const n=node(browseNodeId || selectedId());if(!n)return '<p class="ew-muted">왼쪽에서 업무 절차를 선택하세요.</p>';
    const p=lineage(n.id)[0],cases=scopeCases(p.id),active=cases.filter(c=>!finished(c));
    const picker=active.length?`<section class="ew-work-cases"><h3>이어서 진행할 업무</h3><p class="ew-muted">${active.length>1?'진행 건을 선택한 뒤 입력을 반영하거나 점검하세요.':'기존 진행 건에서 이어갈 수 있습니다.'}</p><div class="ew-case-list">${active.map(c=>`<button type="button" data-action="open_case" data-case-id="${esc(c.id)}"><strong>${esc(runLabel(c))}</strong><span>${esc(statuses[c.status])} · 잡 ${c.progress.done}/${c.progress.total} 완료</span></button>`).join('')}</div></section>`:'<p class="ew-work-preview-note">업무를 살펴본 뒤 필요한 입력을 반영하거나 점검하세요. 첫 저장 시 진행 건을 만듭니다.</p>';
    const completed=cases.filter(finished);
    const previous=completed.length?`<p class="ew-muted">완료 기록 ${completed.length}건은 실행 이력에 보존됩니다.</p>`:'';
    renderedEditContext=editContext(n.id);
    return workPanelNodeHTML(null,n,{definition:definition(),site:state.catalog.sites[browsingSite],system:browsingSystem,previewActions:picker+previous,previewBlocked:active.length>1,draft:draftFor(renderedEditContext)});
  }
  function renderPanel() {
    captureJobEdits();
    if (!chatRoute() || !state || !selectedId()) {closeHost(); return;} ensureHost();
    const content=$('#ees-work-content',host),focused=content.contains(document.activeElement)?document.activeElement:null;
    const focusState=focused?{id:focused.id,name:focused.name,node:focused.dataset.nodeId,action:focused.dataset.action,start:focused.selectionStart,end:focused.selectionEnd}:null;
    const oldNode=renderedEditContext?.scope.nodeId;
    if(runView==='history' || !selectedCase()) {
      if(runView==='history')renderedEditContext=null;
      content.innerHTML=runTabs()+alertHTML()+(runView==='history'?historyHTML():previewHTML());
    }else{
      const c=selectedCase(),n=node(selectedId()) || node(c.selected_id) || node(c.process_id),done=finished(c);
      const closed=done?`<p class="ew-work-preview-note">${c.status==='skipped'?'이 진행 건에는 적용 대상 잡이 없습니다.':'이 진행 건은 완료되어 읽기만 가능합니다.'} 기존 기록은 보존됩니다.</p>`:'';
      renderedEditContext=done?null:editContext(n.id);
      content.innerHTML=runTabs()+alertHTML()+closed+workPanelNodeHTML(c,n,{readOnly:done,draft:draftFor(renderedEditContext)})+(done&&n.type==='p'?button('새 실행','start_case','class="ew-primary" data-mutation'):'')+'<p class="ew-footnote">연결 점검은 모의 결과이며 실제 업무 시스템을 호출하지 않습니다.</p>';
    }
    if(focusState&&oldNode===renderedEditContext?.scope.nodeId){
      const replacement=Array.from(content.querySelectorAll('input,textarea,button')).find(el=>focusState.id?el.id===focusState.id:focusState.name?el.name===focusState.name:el.dataset.action===focusState.action&&el.dataset.nodeId===focusState.node);
      replacement?.focus({preventScroll:true});if(replacement?.setSelectionRange&&typeof focusState.start==='number')replacement.setSelectionRange(focusState.start,focusState.end);
    }
    renderTabs();callbacks.registerPanel();setBusy();
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
    return result;
  }
  function handleEvent(event) {
    const unhandled={handled:false,preventDefault:false},handled=(preventDefault=false)=>({handled:true,preventDefault});
    const target=event.target,inside=target.closest?.('[data-ees-work]');
    if(event.type==='scroll'){positionNav();return unhandled;}
    if(event.type==='resize'){updateLayout();return unhandled;}
    if(event.type==='pointerdown'){
      if(scopePicker&&!target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();
      if(target.closest?.('#ees-work-resizer')&&event.button===0){divider.dataset.pointer='';drag={id:event.pointerId,start:event.clientX,width:host.getBoundingClientRect().width};divider.setPointerCapture(event.pointerId);return handled(true);}
      return unhandled;
    }
    if(event.type==='pointermove'&&drag?.id===event.pointerId){width=drag.width+drag.start-event.clientX;sizePanel();return handled();}
    if(['pointerup','pointercancel','lostpointercapture'].includes(event.type)&&drag?.id===event.pointerId){drag=null;if(divider)delete divider.dataset.pointer;return handled();}
    if(event.type==='focusin'){if(scopePicker&&!target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();return unhandled;}
    if(event.type==='keyup')return ['Enter',' ','Spacebar'].includes(event.key)&&target.closest?.('#ees-work-entry [data-action=scope_toggle], #ees-work-scope-popover [data-action=scope_choose]')?handled(true):unhandled;
    if(event.type==='keydown'){
      if(event.currentTarget===document){if(event.key==='Escape'&&navOpen){navOpen=false;renderNavigator();sidebar();}return unhandled;}
      if(target.closest?.('#ees-work-resizer')&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){width=event.key==='Home'?360:event.key==='End'?760:width+(event.key==='ArrowLeft'?24:-24);sizePanel();return handled(true);}
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
      return unhandled;
    }
    if(target.closest?.('#ees-work-designer'))return unhandled;
    if(event.type==='input'&&target.closest?.('#ees-work-inputs,#ees-work-document')){
      captureJobEdits(target);const edits=readJobEdits(),dirty=Boolean(edits.inputsChanged||edits.documentChanged),note=host?.querySelector('[data-work-dirty]');if(note)note.hidden=!dirty;
      const next=host?.querySelector('[data-work-next]');if(next)next.textContent=dirty?'작성 중인 값이 있습니다. 입력을 반영한 뒤 점검하세요.':next.dataset.workSavedNext;
      const run=host?.querySelector('[data-work-draft-sensitive]');if(run){run.dataset.unavailable=String(dirty||edits.conflict||run.dataset.workBaseUnavailable==='true');run.disabled=busy||run.dataset.unavailable==='true';}
      return handled();
    }
    if(event.type==='change'&&target.id==='ees-work-run-select'){callbacks.openCase(target.value);return handled();}
    if(event.type==='submit'&&inside){
      const values=Object.fromEntries(new FormData(target));
      if(target.id==='ees-work-case-create')callbacks.startCase();
      else if(target.id==='ees-work-inputs')callbacks.saveInputs(values,target.dataset.nodeId);
      else if(target.id==='ees-work-document')callbacks.saveDocument(values.document,target.dataset.nodeId);
      else return unhandled;
      return handled(true);
    }
    if(event.type!=='click')return unhandled;
    const categoryButton=target.closest?.('[data-work-category]');
    if(categoryButton?.closest('#ees-work-entry')){
      const wanted=categoryButton.dataset.workCategory;
      if(navOpen&&category===wanted){navOpen=false;renderNavigator();return handled();}
      navOpen=true;callbacks.selectCategory(wanted);return handled();
    }
    const buttonTarget=target.closest?.('[data-action]');if(!buttonTarget?.closest('[data-ees-work]'))return unhandled;
    const action=buttonTarget.dataset.action;if(buttonTarget.disabled)return handled();
    if(action==='scope_toggle'){scopePicker===buttonTarget.dataset.picker?closeScopePicker(true):openScopePicker(buttonTarget.dataset.picker);}
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
    else if(action==='select')callbacks.selectWork(buttonTarget.dataset.nodeId,buttonTarget.dataset.processId);
    else if(action==='run')callbacks.runJob(buttonTarget.dataset.nodeId);
    else if(action==='discard_job_edits'||action==='rebase_job_edits'){const context=editContext(buttonTarget.dataset.nodeId);if(context){if(action==='discard_job_edits')jobDrafts.discard(context.scope);else jobDrafts.rebase(context.scope,context.saved,context.revision);renderedEditContext=null;renderPanel();}}
    else return unhandled;
    return handled();
  }
  function render(value) {readSnapshot(value);sidebar();renderNavigator();renderContext();renderPanel();}
  function prepare(value) {readSnapshot(value);sidebar();updateScopeReadiness();}
  function sync(value) {prepare(value);if(state&&snapshot.browseActive&&chatRoute()){if(!$('#ees-work-context'))renderContext();callbacks.registerPanel();}positionNav();}
  function updateLayout() {positionNav();sizePanel();}
  function detach() {closeScopePicker();closeHost();$('#ees-work-context')?.remove();}
  function reset() {
    detach();treeExpansions.clear();jobDrafts.clear();renderedEditContext=null;snapshot={};state=null;serverSource=null;historySource=null;historyCase=null;navOpen=false;busy=false;width=520;panelInfo=null;drag=null;
    host=null;divider=null;
    ['ees-work-entry','ees-work-admin-link','ees-work-navigator'].forEach(id=>document.getElementById(id)?.remove());
  }
  return Object.freeze({render,prepare,sync,renderNavigator:value=>{readSnapshot(value);renderNavigator();},renderPanel:value=>{readSnapshot(value);renderPanel();},setBusy,openPanel,closeHost,reset,readJobEdits,adoptPreviewDraft,handleEvent,updateLayout,panelRegistration,revealSelection,closeScopePicker,detach,setNavigatorOpen:value=>{navOpen=Boolean(value);},updateScopeReadiness});
}
