/* Owns the procedure draft and Workspace DOM; all server writes are callbacks. */
function createWorkDesigner({callbacks}) {
  const {$, esc, clone, categories, levels, button, lineage} = workUI;
  let serverSource=null;
  let state=null,category='setup',errorMessage='',busy=false,route={};
  let workspaceLink=null,designer=null,hiddenWorkspace=[],editor=null,editorId='',editorRevision=0,editorDirty=false,editorTab='workflow';
  const editorCollapsed=new Set();
  const adminRoute=()=>Boolean(route.admin);
  const alertHTML=()=>errorMessage?`<p class="ew-error" role="alert">${esc(errorMessage)}</p>`:'';
  function treeHTML(data,ids) {return workUI.treeHTML(data,ids,{editing:true,selectedId:editorId,collapsed:editorCollapsed,expansionKey:JSON.stringify([route.site,route.system,'',data?.version || state?.catalog?.version])});}
  function setBusy(value=busy) {busy=value;designer?.querySelectorAll('button[data-mutation]').forEach(el=>{el.disabled=busy||el.dataset.unavailable==='true';});}
  function acceptServer(result) {
    state=clone(result);serverSource=result;
    if(!editorDirty&&state.can_manage){editor=clone(state.draft || state.catalog);editorRevision=state.draft_revision || 0;}
    if(!editorId||!editor?.nodes?.[editorId])editorId=Object.keys(editor?.nodes || {})[0] || '';
  }
  function readSnapshot(value) {({category,errorMessage,busy}=value);route={admin:value.adminRoute,site:value.browsingSite,system:value.browsingSystem};if(value.state!==serverSource){state=value.state?clone(value.state):null;serverSource=value.state;}}
  function hideWorkspaceContent() {
    const container=$('#workspace-container');if(!container||!designer||!state?.can_manage||!adminRoute())return;
    const controls=container.parentElement.querySelector('nav .ml-auto.shrink-0');
    [...container.children,...(controls?[controls]:[])].filter(element=>element!==designer).forEach(element=>{
      if(!hiddenWorkspace.some(([known])=>known===element))hiddenWorkspace.push([element,element.hidden]);
      if(!element.hidden)element.hidden=true;element.classList.add('ees-work-native-hidden');
    });
  }
  function restoreWorkspace(removeTab=false) {
    designer?.remove(); designer = null;
    hiddenWorkspace.forEach(([element,previous])=>{element.hidden=previous;element.classList.remove('ees-work-native-hidden');}); hiddenWorkspace=[];
    if(removeTab){workspaceLink?.remove();workspaceLink=null;}
  }
  function workspaceTab() {
    if(!state)return;
    if(!state.can_manage){workspaceLink?.remove();workspaceLink=null;return;}
    const container=$('#workspace-container'),original=container?.parentElement.querySelector('nav a[href="/workspace/models"]');
    if(!original)return;
    if(!workspaceLink){workspaceLink=document.createElement('a');workspaceLink.id='ees-work-workspace-tab';workspaceLink.href='/workspace/models?ees=workflow';workspaceLink.textContent='업무 절차';}
    if(workspaceLink.className!==original.className)workspaceLink.className=original.className;
    const active=adminRoute()?'page':'false';
    if(adminRoute()){if(original.getAttribute('aria-current')==='page')original.dataset.eesPreviousCurrent='page';original.setAttribute('aria-current','false');}
    else if(original.dataset.eesPreviousCurrent){if(location.pathname==='/workspace/models')original.setAttribute('aria-current','page');delete original.dataset.eesPreviousCurrent;}
    if(workspaceLink.getAttribute('aria-current')!==active)workspaceLink.setAttribute('aria-current',active);
    if(workspaceLink.parentElement!==original.parentElement)original.parentElement.append(workspaceLink);
  }

  function renderDesigner() {
    workspaceTab();
    if (!adminRoute() || !state?.can_manage) {if (designer) restoreWorkspace(); return;}
    const container=$('#workspace-container'); if (!container || !editor) return;
    if (!designer || designer.parentElement!==container) {
      restoreWorkspace();
      for (const child of container.children) {hiddenWorkspace.push([child,child.hidden]);child.hidden=true;}
      designer=document.createElement('section');designer.id='ees-work-designer';designer.dataset.eesWork='';container.append(designer);workspaceTab();hideWorkspaceContent();
    }
    designer.innerHTML=`<header class="ew-designer-toolbar"><div class="ew-designer-heading"><h1>업무 절차</h1><div class="ew-designer-status">게시 v${esc(state.catalog.version)} · 초안 ${esc(editorRevision)}${editorDirty?' · 저장하지 않은 변경':''} · ${state.validated_revision===editorRevision&&!editorDirty?'게시 전 확인 완료':'게시 전 확인 필요'}</div></div><div class="ew-actions">${button('초안 저장','save_draft','data-mutation')}${button('게시 전 확인','validate_draft','data-mutation')}${button('게시','publish','data-mutation class="ew-primary"')}</div></header>
      <p class="ew-designer-description ew-muted">업무 이름·안내·완료 조건을 중심으로 편집합니다. 초안 저장은 운영 중인 업무에 영향을 주지 않으며, 게시한 변경은 새 진행 건부터 적용됩니다.</p>${alertHTML()}
      <nav class="ew-editor-tabs" aria-label="업무 절차 설정">${[['workflow','업무 절차'],['tools','도구'],['skills','스킬'],['sites','공장 조건']].map(([id,label])=>button(label,'editor_tab',`data-tab="${id}" aria-selected="${editorTab===id}"`)).join('')}</nav>${editorTab==='workflow'?workflowEditor():assetEditor()}`;
    setBusy();
  }
  function workflowEditor() {
    const n=editor.nodes[editorId]; if(!n)return `<section class="ew-card"><p class="ew-muted">업무를 추가하고 필요한 하위 업무를 구성해 주세요.</p>${button('업무 추가','add_process')}</section>`;
    const parents=Object.values(editor.nodes).filter(x=>x.type===(n.type==='j'?'t':n.type==='t'?'p':'none'));
    const conditions=[['all','모든 공장'],['interface','인터페이스 대상 있음'],['reuse','기존 인프라 재사용'],['new-infra','신규 인프라 준비'],...Array.from(new Set(Object.values(editor.sites).map(s=>s.country))).map(v=>['country:'+v,'국가: '+v]),...Object.values(editor.sites).map(s=>['factory:'+s.id,'공장: '+s.name]),...Array.from(new Set(Object.values(editor.sites).map(s=>s.line).filter(Boolean))).map(v=>['line:'+v,'라인: '+v])];
    return `<div class="ew-editor-layout"><aside><div class="ew-heading"><h3>업무 구조</h3>${button('업무 추가','add_process')}</div>${Object.entries(categories).map(([id,label])=>`<h4>${label}</h4>${treeHTML(editor,editor.roots[id])}`).join('')}</aside><form id="ees-work-node-form" class="ew-node-editor"><div class="ew-heading"><div><h2>${esc(n.name)}</h2><p class="ew-editor-kind">${({p:'업무',t:'하위 업무',j:'확인/실행 업무'})[n.type]}</p></div><div class="ew-actions">${n.type!=='j'?button(n.type==='p'?'하위 업무 추가':'확인/실행 업무 추가','add_child'):''}${button('위로','move_up')}${button('아래로','move_down')}${button('삭제','delete_node')}</div></div><label>업무 이름<input name="name" value="${esc(n.name)}" maxlength="160" required></label><label>업무 목적<textarea name="description" rows="2">${esc(n.description || '')}</textarea></label>${n.type==='p'?`<label>업무 분류<select name="category">${Object.entries(categories).map(([id,name])=>`<option value="${id}" ${n.category===id?'selected':''}>${name}</option>`).join('')}</select></label>`:`<label>상위 업무<select name="parent">${parents.map(p=>`<option value="${esc(p.id)}" ${p.id===n.parent?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label>`}<div class="ew-form-grid"><label>적용 조건<select name="condition">${conditions.map(([id,label])=>`<option value="${esc(id)}" ${n.condition===id?'selected':''}>${esc(label)}</option>`).join('')}</select></label><label class="ew-checkbox"><input type="checkbox" name="enabled" ${n.enabled!==false?'checked':''}>이 단계 사용</label></div>${n.type==='j'?`<label>수행 방식<select name="mode">${[['manual','담당자 확인'],['draft','초안 작성 후 검토'],['tool','연결된 도구로 점검']].map(([id,label])=>`<option value="${id}" ${n.mode===id?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<label>완료 조건<textarea name="rule" rows="2">${esc(n.rule || '')}</textarea></label><label>업무 수행 안내<textarea name="instructions" rows="4">${esc(n.instructions || '')}</textarea></label><details class="ew-designer-advanced"><summary>고급 설정</summary><fieldset><legend>적용 시스템</legend>${(editor.systems||[]).map(system=>`<label class="ew-checkbox"><input type="checkbox" name="systems" value="${esc(system)}" ${(!n.systems||n.systems.includes(system))?'checked':''}>${esc(system)}</label>`).join('')}</fieldset><fieldset><legend>선행 작업</legend><div class="ew-option-grid">${Object.values(editor.nodes).filter(x=>x.id!==n.id&&lineage(x.id,editor)[0]?.id===lineage(n.id,editor)[0]?.id&&!lineage(x.id,editor).some(a=>a.id===n.id)&&!lineage(n.id,editor).some(a=>a.id===x.id)).map(x=>`<label class="ew-checkbox"><input type="checkbox" name="deps" value="${esc(x.id)}" ${(n.deps||[]).includes(x.id)?'checked':''}>${esc(x.name)}</label>`).join('')}</div></fieldset><fieldset><legend>사용할 스킬</legend>${Object.values(editor.skills).map(s=>`<label class="ew-checkbox"><input type="checkbox" name="skills" value="${esc(s.id)}" ${s.id==='common'?'checked disabled':(n.skills||[]).includes(s.id)?'checked':''}>${esc(s.name)}</label>`).join('')}</fieldset><fieldset><legend>${n.type==='j'?'실행 도구와 입력 연결':'하위 작업에서 허용할 도구'}</legend><p class="ew-muted">${n.type==='j'?'위에서 아래 순서로 실행합니다. 실제 연결이 없는 도구는 미수행으로 표시합니다.':'선택하면 하위 단계는 이 도구들만 사용할 수 있습니다. 비워두면 별도 제한을 추가하지 않습니다.'}</p>${(n.tools||[]).map((id,index)=>`<div class="ew-tool-editor"><span>${index+1}. ${esc(editor.tools[id]?.name || id)}</span><select name="binding:${esc(id)}" aria-label="${esc(editor.tools[id]?.name || id)} 입력">${[['site','공장'],['db','DB 대상'],['ap','AP 대상'],['interface','인터페이스']].filter(([key])=>key===editor.tools[id]?.input).map(([key,label])=>`<option value="${key}" ${n.bindings?.[id]===key?'selected':''}>${label}</option>`).join('')}</select>${button('위로','tool_up',`data-tool-id="${esc(id)}"`)}${button('삭제','tool_remove',`data-tool-id="${esc(id)}"`)}</div>`).join('')}<div class="ew-inline"><select id="ees-work-tool-add" aria-label="추가할 도구">${Object.values(editor.tools).filter(t=>!(n.tools||[]).includes(t.id)).map(t=>`<option value="${esc(t.id)}">${esc(t.name)}${t.adapter==='unavailable'?' · 실행 연결 필요':''}</option>`).join('')}</select>${button('도구 추가','tool_add')}</div></fieldset></details><button type="submit">변경 내용 적용</button><p class="ew-preservation">초안 변경은 게시 후 새 진행 건부터 적용됩니다. 기존 진행 건은 게시 당시 버전을 유지합니다.</p></form></div>`;
  }
  function registeredOptions(kind,selected) {
    const items=state?.catalog?.['available_'+kind] || [], found=items.some(item=>item.id===selected);
    return (selected&&!found?`<option value="${esc(selected)}" selected>${esc(selected)} · 현재 접근 불가</option>`:'')+items.map(item=>`<option value="${esc(item.id)}" ${item.id===selected?'selected':''}>${esc(item.name)} · ${esc(item.id)}</option>`).join('');
  }
  function assetEditor() {
    const kind=editorTab;
    return `<div class="ew-assets">${state.catalog.assets_available===false?'<p class="ew-notice">등록된 도구·스킬 목록을 읽지 못했습니다. 기존 워크스페이스의 접근 상태를 확인해 주세요.</p>':''}<div class="ew-heading"><h2>${{tools:'사용할 도구',skills:'스킬과 지침',sites:'국가 · 공장별 조건'}[kind]}</h2>${button(kind==='sites'?'공장 추가':kind==='skills'?'스킬 추가':'기존 도구 연결','add_asset',`data-kind="${kind}"`)}</div>${kind==='tools'?'<p class="ew-muted">기존 워크스페이스에 등록된 도구를 연결할 수 있습니다. 실행 어댑터가 없는 참조는 자동 실행하지 않습니다.</p><a href="/workspace/tools">기존 도구 관리 열기</a>':kind==='skills'?'<p class="ew-muted">업무 지침을 작성하거나 기존 스킬을 참조합니다. 공통 정책은 개별 단계에서 해제하지 않습니다.</p><a href="/workspace/skills">기존 스킬 관리 열기</a>':'<p class="ew-muted">공장 조건 변경은 새 진행 건부터 적용됩니다.</p>'}${Object.values(editor[kind]||{}).map(asset=>`<form class="ew-card ew-asset-form" data-kind="${kind}" data-asset-id="${esc(asset.id)}"><label>이름<input name="name" value="${esc(asset.name)}" ${asset.locked?'readonly':''}></label>${kind==='sites'?`<div class="ew-form-grid"><label>국가<input name="country" value="${esc(asset.country)}"></label><label>공장명<input name="factory" value="${esc(asset.factory || asset.name)}"></label><label>라인<input name="line" value="${esc(asset.line || '')}"></label><label>시간대<input name="zone" value="${esc(asset.zone || 'Asia/Seoul')}"></label><label>DB 대상<input name="db" value="${esc(asset.db || '')}"></label><label>AP 대상<input name="ap" value="${esc(asset.ap || '')}"></label></div><label class="ew-checkbox"><input type="checkbox" name="reuse" ${asset.reuse?'checked':''}>기존 인프라 재사용</label><label class="ew-checkbox"><input type="checkbox" name="interface" ${asset.interface?'checked':''}>시스템간 인터페이스 있음</label>`:kind==='skills'?`<label>스킬 지침<textarea name="body" rows="4" ${asset.locked?'readonly':''}>${esc(asset.body || '')}</textarea></label><label>기존 스킬 (선택)<select name="reference" ${asset.locked?'disabled':''}><option value="">직접 작성한 스킬</option>${registeredOptions('skills',asset.reference)}</select></label>${asset.locked?'<p class="ew-muted">공통 지침 · 변경 불가</p>':''}`:`<label>설명<textarea name="description" rows="2">${esc(asset.description || '')}</textarea></label>${asset.adapter==='unavailable'?`<label>기존 도구<select name="reference"><option value="">등록된 도구 선택</option>${registeredOptions('tools',asset.reference)}</select></label>`:''}<p class="ew-muted">${asset.adapter==='unavailable'?'실행 연결 필요': '합성 시연 점검'}</p>`}<button type="submit" ${asset.locked?'disabled':''}>변경 내용 적용</button></form>`).join('')}</div>`;
  }
  function captureNode() {
    const form=$('#ees-work-node-form'); if (!form || !editor?.nodes[editorId])return;
    const values=new FormData(form), n=editor.nodes[editorId], before=JSON.stringify(n), oldParent=n.parent, oldCategory=n.category;
    for(const key of ['name','description','condition','mode','rule','instructions']) if(values.has(key))n[key]=String(values.get(key));
    n.enabled=values.has('enabled');n.systems=values.getAll('systems');n.deps=values.getAll('deps');n.skills=values.getAll('skills');n.bindings=n.bindings||{};
    for(const id of n.tools||[])n.bindings[id]=String(values.get('binding:'+id)||'site');
    if(n.type==='p') {
      n.category=String(values.get('category'));
      if(oldCategory!==n.category){editor.roots[oldCategory]=editor.roots[oldCategory].filter(id=>id!==n.id);editor.roots[n.category].push(n.id);}
    }else{
      n.parent=String(values.get('parent'));
      if(oldParent!==n.parent){editor.nodes[oldParent].children=editor.nodes[oldParent].children.filter(id=>id!==n.id);editor.nodes[n.parent].children.push(n.id);}
      n.category=editor.nodes[n.parent].category;
    }
    const setCategory=id=>{editor.nodes[id].category=n.category;(editor.nodes[id].children||[]).forEach(setCategory);};setCategory(n.id);
    if(JSON.stringify(n)!==before)editorDirty=true;
  }
  function captureAssets() {
    designer?.querySelectorAll('.ew-asset-form').forEach(form=>{
      const asset=editor[form.dataset.kind][form.dataset.assetId];if(asset.locked)return;
      const before=JSON.stringify(asset),values=new FormData(form);
      for(const key of ['name','country','factory','line','zone','db','ap','body','description','reference'])if(values.has(key))asset[key]=String(values.get(key));
      if(form.dataset.kind==='sites'){asset.reuse=values.has('reuse');asset.interface=values.has('interface');}
      if(form.dataset.kind==='skills'){if(asset.reference)asset.source='open_webui';else delete asset.source;}
      if(JSON.stringify(asset)!==before)editorDirty=true;
    });
  }
  function captureEditor(){captureNode();captureAssets();}
  function localEdit(actionName,target) {
    captureEditor();const n=editor.nodes[editorId];
    if(actionName==='edit_node')editorId=target.dataset.nodeId;
    else if(actionName==='editor_tab')editorTab=target.dataset.tab;
    else if(actionName==='add_child'||actionName==='add_process') {
      const type=actionName==='add_process'?'p':n.type==='p'?'t':'j',id='custom-'+type+'-'+Date.now().toString(36);
      const cat=actionName==='add_process'?category:n.category;
      editor.nodes[id]={id,type,name:'새 '+levels[type],parent:type==='p'?null:n.id,children:[],category:cat,description:'',condition:'all',mode:'manual',tools:[],bindings:{},skills:[],instructions:'',deps:[],rule:'담당자 확인',enabled:true};
      if(type==='p')editor.roots[cat].push(id);else n.children.push(id);editorId=id;editorDirty=true;
    }else if(actionName==='delete_node') {
      if(!confirm('이 단계와 하위 단계를 초안에서 삭제할까요? 진행 중인 업무에는 영향이 없습니다.'))return;
      const ids=Object.keys(editor.nodes).filter(id=>lineage(id,editor).some(v=>v.id===n.id));
      if(n.parent)editor.nodes[n.parent].children=editor.nodes[n.parent].children.filter(id=>id!==n.id);else editor.roots[n.category]=editor.roots[n.category].filter(id=>id!==n.id);
      ids.forEach(id=>delete editor.nodes[id]);Object.values(editor.nodes).forEach(v=>{v.deps=(v.deps||[]).filter(id=>!ids.includes(id));});editorId=Object.keys(editor.nodes)[0];editorDirty=true;
    }else if(['move_up','move_down'].includes(actionName)) {
      const list=n.parent?editor.nodes[n.parent].children:editor.roots[n.category],index=list.indexOf(n.id),next=index+(actionName==='move_up'?-1:1);
      if(next>=0&&next<list.length){[list[index],list[next]]=[list[next],list[index]];editorDirty=true;}
    }else if(actionName==='tool_add'){const id=$('#ees-work-tool-add')?.value;if(id&&!(n.tools||[]).includes(id)){n.tools.push(id);n.bindings[id]=editor.tools[id].input || 'site';editorDirty=true;}}
    else if(actionName==='tool_remove'){n.tools=n.tools.filter(id=>id!==target.dataset.toolId);delete n.bindings[target.dataset.toolId];editorDirty=true;}
    else if(actionName==='tool_up'){const index=n.tools.indexOf(target.dataset.toolId);if(index>0){[n.tools[index],n.tools[index-1]]=[n.tools[index-1],n.tools[index]];editorDirty=true;}}
    else if(actionName==='add_asset'){
      const kind=target.dataset.kind,id='custom-'+kind+'-'+Date.now().toString(36);
      editor[kind][id]=kind==='sites'?{id,name:'새 공장',country:'한국',factory:'새 공장',line:'조립 1라인',zone:'Asia/Seoul',db:'새 공장 DB 진단 경로 · 예시',ap:'새 공장 AP 진단 경로 · 예시',reuse:false,interface:false}:kind==='skills'?{id,name:'새 스킬',type:'skill',body:'',locked:false,reference:''}:{id,name:'기존 도구',description:'',reference:'',source:'open_webui',adapter:'unavailable',input:'site',enabled:true,type:'등록 도구',success:'연결 후 기준 설정'};editorDirty=true;
    }
    renderDesigner();
  }

  function readDraft() {captureEditor();return {definition:editor?clone(editor):null,revision:editorRevision,dirty:editorDirty};}
  function markSaved() {editorDirty=false;}
  function render(value) {if(value)readSnapshot(value);renderDesigner();}
  function prepare(value) {readSnapshot(value);workspaceTab();}
  function sync(value) {prepare(value);if(adminRoute()&&state){if(!designer?.isConnected)renderDesigner();else hideWorkspaceContent();}}
  function handleEvent(event) {
    const target=event.target;if(!target.closest?.('#ees-work-designer'))return {handled:false,preventDefault:false};
    const handled=preventDefault=>({handled:true,preventDefault:Boolean(preventDefault)});
    if(event.type==='input'){editorDirty=true;return handled();}
    if(event.type==='change'){
      const form=target.closest('.ew-asset-form');
      if(form&&target.name==='reference'){const item=(state.catalog['available_'+form.dataset.kind]||[]).find(item=>item.id===target.value),name=form.querySelector('[name=name]');if(item&&['기존 도구','새 스킬'].includes(name.value))name.value=item.name;}
      return handled();
    }
    if(event.type==='submit'){if(target.id==='ees-work-node-form'||target.classList.contains('ew-asset-form')){captureEditor();renderDesigner();return handled(true);}return handled(false);}
    if(event.type!=='click')return {handled:false,preventDefault:false};
    const buttonTarget=target.closest('[data-action]');if(!buttonTarget)return {handled:false,preventDefault:false};
    const action=buttonTarget.dataset.action;
    if(action==='expand'){captureEditor();const id=buttonTarget.dataset.nodeId;editorCollapsed.has(id)?editorCollapsed.delete(id):editorCollapsed.add(id);renderDesigner();}
    else if(['save_draft','validate_draft','publish'].includes(action))callbacks[action]();
    else if(state?.can_manage)localEdit(action,buttonTarget);
    return handled(false);
  }
  function reset() {restoreWorkspace(true);state=null;serverSource=null;editor=null;editorId='';editorRevision=0;editorDirty=false;editorTab='workflow';editorCollapsed.clear();category='setup';errorMessage='';busy=false;route={};}
  return Object.freeze({acceptServer,readDraft,markSaved,render,prepare,sync,setBusy,restoreWorkspace,reset,handleEvent});
}
