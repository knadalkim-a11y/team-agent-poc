/* Native EES workflow: existing sidebar, real chat and shared work panel. */
(() => {
  'use strict';
  if (window.__eesNativeWork) return;
  const $ = (s, p = document) => p.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const categories = {setup:'셋업',ops:'운영',incident:'장애대응'};
  const levels = {p:'프로세스',t:'태스크',j:'잡'};
  const statuses = {unstarted:'시작 전',ready:'준비',pending:'대기',in_progress:'진행 중',running:'실행 중',success:'완료',completed:'완료',passed:'완료',failed:'실패',blocked:'선행 작업 대기',skipped:'적용 제외',draft:'초안',review:'검토 필요'};
  let state = null, generation = 0, request = 0, busy = false, scheduled = false;
  let lastRoute = '', identity = '', pendingId = '', pendingSubmitted = false;
  let category = 'setup', browsingSystem = 'EMS', browsingSite = '', navOpen = true, newCase = false, activeRegistration = null;
  let browseActive = false, browseNodeId = '', runView = 'current', historyCase = null, historyRequest = 0, navigationRequest = 0;
  let desiredCase = '', desiredNode = '', reopenPanel = false, navigationTarget = '';
  const scopeSelections = new Map(), chosenCases = new Map(), draftSnapshots = new Map(), creationTickets = new Map(), createdChats = new Map();
  let creationSerial=0;
  let visibleDraftKey='general', draftTarget=null, draftTimer=null, draftSerial=0;
  let host = null, divider = null, panelOpen = false, width = 520, panelInfo = null;
  let workspaceLink = null, designer = null, hiddenWorkspace = [], editor = null, editorId = '', editorRevision = 0, editorDirty = false;
  let editorTab = 'workflow', errorMessage = '', drag = null;
  const editorCollapsed=new Set();
  // A node ID can belong to several factory scopes and retained case versions.
  const treeExpansions = new Map();
  let scopePicker = '';
  const token = () => {try {return localStorage.getItem('token') || '';} catch (_) {return '';}};
  const chatId = () => {const m = location.pathname.match(/^\/c\/([^/]+)\/?$/); return m ? decodeURIComponent(m[1]) : '';};
  const chatRoute = () => location.pathname === '/' || /^\/c\/[^/]+\/?$/.test(location.pathname);
  const adminRoute = () => location.pathname.startsWith('/workspace') && new URLSearchParams(location.search).get('ees') === 'workflow';
  const available = () => !/^\/(auth|logout)(\/|$)/.test(location.pathname) && Boolean($('#sidebar-new-chat-button'));
  const currentCase = () => state?.case;
  const selectedCase = () => !newCase && currentCase()?.site?.id === browsingSite && currentCase()?.system === browsingSystem ? currentCase() : null;
  const caseMatchesRoute=()=>Boolean(currentCase()&&chatRoute()&&(currentCase().chat_id || '')===chatId());
  const definition = () => selectedCase()?.definition || state?.catalog;
  const selectedId = () => browseActive ? (newCase ? browseNodeId : (selectedCase()?.selected_id || browseNodeId)) : '';
  const node = id => definition()?.nodes?.[id];
  const status = id => selectedCase()?.node_states?.[id] || {};
  const badge = value => `<span class="ew-badge" data-status="${esc(value)}">${esc(statuses[value] || value || '대기')}</span>`;
  const button = (label, action, attrs = '') => `<button type="button" data-action="${action}" ${attrs}>${esc(label)}</button>`;
  const nameOf = id => node(id)?.name || id;
  const lineage = (id, data = definition()) => {const result = [], seen = new Set(); while (id && data?.nodes[id] && !seen.has(id)) {seen.add(id); result.unshift(data.nodes[id]); id = data.nodes[id].parent;} return result;};
  const alertHTML = () => errorMessage ? `<p class="ew-error" role="alert">${esc(errorMessage)}</p>` : '';
  const scopeKey = () => browsingSite + '/' + browsingSystem;
  const caseKey = id => scopeKey() + '/' + id;
  const expansionKey = (data, run) => JSON.stringify([browsingSite,browsingSystem,run?.id || '',run?.version || data?.version || state?.catalog?.version]);
  function expansionState(key) {if(!treeExpansions.has(key))treeExpansions.set(key,new Map());return treeExpansions.get(key);}
  function revealSelection(id,data,run,includeSelf=false) {
    const branches=expansionState(expansionKey(data,run));
    lineage(id,data).forEach(n=>{if(n.children?.length&&(includeSelf||n.id!==id)&&!branches.has(n.id))branches.set(n.id,true);});
  }
  function toggleBranch(id,key,data) {
    const branches=expansionState(key),open=!branches.get(id);branches.set(id,open);
    // Reopening a parent shows one level, even when its selected job is hidden.
    if(!open){const pending=[...(data?.nodes[id]?.children || [])],seen=new Set();while(pending.length){const child=pending.pop();if(seen.has(child))continue;seen.add(child);branches.set(child,false);pending.push(...(data.nodes[child]?.children || []));}}
  }
  const processId = () => lineage(selectedId())[0]?.id || (state?.catalog?.roots?.[category] || [])[0] || '';
  const scopeCases = id => (state?.cases || []).filter(c => c.site?.id === browsingSite && c.system === browsingSystem && (!id || c.process_id === id));
  const finished = c => ['passed','completed','success','skipped'].includes(c?.status);
  function chosenCase(id) {
    const cases=scopeCases(id), remembered=cases.find(c=>c.id===chosenCases.get(caseKey(id)));
    if(remembered)return remembered;
    const active=cases.filter(c=>!finished(c));
    return active.length===1?active[0]:active.length>1?null:cases[0] || null;
  }
  function visibleRoots(group) {
    const data=state?.catalog;if(!data)return [];
    return [...new Set([...(data.roots[group] || []),...scopeCases().filter(c=>c.category===group).map(c=>c.process_id)])].filter(p=>{
      const n=data.nodes[p];return scopeCases(p).length || n&&n.enabled!==false&&(!n.systems||n.systems.includes(browsingSystem));
    });
  }
  function rememberScope() {if(browsingSite)scopeSelections.set(scopeKey(),{category,nodeId:selectedId()});}
  function siteLabel(site) {return [site?.country,site?.name || site?.factory].filter(Boolean).join(' · ');}
  function runLabel(c) {const list=scopeCases(c.process_id),order=list.findIndex(item=>item.id===c.id);return ['실행 '+(order>=0?list.length-order:'기록'),c.created_at?c.created_at.replace('T',' ').slice(0,19)+' UTC':'생성 시각 미기록', c.process_name || c.definition?.nodes[c.process_id]?.name || state?.catalog?.nodes[c.process_id]?.name || '업무', 'v'+c.version].join(' · ');}

  async function api(path, body) {
    const headers = {'Accept':'application/json'};
    const access = token(); if (access) headers.Authorization = 'Bearer ' + access;
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/ees-work/' + path, {method:body ? 'POST' : 'GET',credentials:'same-origin',cache:'no-store',headers,...(body ? {body:JSON.stringify(body)} : {})});
    let result;try{result=await response.json();}catch(_){throw new Error('업무 정보를 가져오지 못했습니다. 배포 상태를 확인해 주세요.');}
    if (!response.ok || result.ok === false) throw new Error(result.error?.message || result.detail?.message || '업무 정보를 가져오지 못했습니다. 로그인과 배포 상태를 확인해 주세요.');
    return result;
  }
  function accept(result) {
    const previousCase=state?.case?.id;state = result;
    if(state.case)browseActive=true;
    if(state.case&&state.case.id!==previousCase){browsingSite=state.case.site.id;browsingSystem=state.case.system;category=state.case.definition.nodes[state.case.process_id]?.category || 'setup';browseNodeId=state.case.selected_id;newCase=false;chosenCases.set(caseKey(state.case.process_id),state.case.id);}
    if(!state.case){const params=new URLSearchParams(location.search);if(params.has('ees_site')){browseActive=true;browsingSite=params.get('ees_site');browsingSystem=params.get('ees_system') || browsingSystem;browseNodeId=params.get('ees_process') || browseNodeId;category=state.catalog.nodes[browseNodeId]?.category || category;}}
    if(!state.catalog.systems.includes(browsingSystem))browsingSystem=state.catalog.systems[0];
    if(!browsingSite || !state.catalog.sites[browsingSite])browsingSite=Object.keys(state.catalog.sites)[0] || '';
    if(!state.case){newCase=true;const roots=visibleRoots(category);if(!roots.includes(lineage(browseNodeId,state.catalog)[0]?.id))browseNodeId=roots[0] || '';}
    if (!editorDirty && state.can_manage) {editor = clone(state.draft || state.catalog); editorRevision = state.draft_revision || 0;}
    if (!editorId || !editor?.nodes?.[editorId]) editorId = Object.keys(editor?.nodes || {})[0] || '';
    if(currentCase())revealSelection(currentCase().selected_id,currentCase().definition,currentCase());
    if (currentCase()?.chat_id) pendingId = '';
    render();
    if(!draftTarget)visibleDraftKey=chatId()?'chat/'+chatId():pendingId?'case/'+pendingId:browseActive?'scope/'+scopeKey()+'/'+processId():'general';
    restoreDraft();
    if(desiredNode && state.case?.id===desiredCase && state.case.chat_id===chatId()) {const wanted=desiredNode;desiredNode='';desiredCase='';reopenPanel=false;action('select',{},wanted).then(result=>{if(result)openPanel();});}
    else if(reopenPanel && chatRoute()){reopenPanel=false;openPanel();}
  }
  async function refresh() {
    if (!available()) return;
    const at = generation, scopeEpoch=navigationRequest, serial = ++request, id = chatId(), auth = token(), route = location.pathname + location.search;
    const query = new URLSearchParams({chat_id:id}); if (!id && pendingId) query.set('case_id', pendingId);
    try {const result = await api('state?' + query); if (at !== generation || scopeEpoch !== navigationRequest || serial !== request || auth !== token() || route !== location.pathname + location.search || !available()) return; errorMessage = ''; accept(result);}
    catch (error) {if (at !== generation || scopeEpoch !== navigationRequest || serial !== request) return; errorMessage = error.message; render();}
  }
  async function action(actionName, payload = {}, nodeId = '', override = {}) {
    if (busy || !state) return null;
    busy = true; errorMessage = ''; setBusy();
    const at = generation, scopeEpoch=navigationRequest, cid = currentCase()?.id || '', auth = token(), route = location.pathname + location.search;
    const isAdmin = ['save_draft','validate_draft','publish'].includes(actionName);
    const body = {action:actionName,chat_id:chatId(),case_id:cid,node_id:nodeId,payload,expected_revision:isAdmin ? editorRevision : (currentCase()?.revision || 0),...override};
    try {
      const result = await api('action', body);
      if (at !== generation || scopeEpoch !== navigationRequest || auth !== token() || route !== location.pathname + location.search || !available()) return null;
      if (isAdmin && actionName !== 'validate_draft') editorDirty = false;
      if (actionName === 'create' && !result.case?.chat_id) pendingId = result.case?.id || '';
      accept(result); return result;
    } catch (error) {if (at === generation && scopeEpoch === navigationRequest) {errorMessage = error.message; render();} return null;}
    finally {busy = false; setBusy();if(scopeEpoch!==navigationRequest&&available()&&auth===token())refresh();}
  }
  function setBusy() {document.querySelectorAll('[data-ees-work] button[data-mutation]').forEach(el => {el.disabled = busy || el.dataset.unavailable === 'true';}); if (host) host.setAttribute('aria-busy',String(busy));}

  function sidebar() {
    const anchor=$('#sidebar-search-button');if(!anchor)return;
    let entry=$('#ees-work-entry');
    if(!entry){entry=document.createElement('section');entry.id='ees-work-entry';entry.dataset.eesWork='';entry.setAttribute('aria-label','공장별 업무');anchor.parentElement.insertAdjacentElement('afterend',entry);renderNavigator();}
    // The native Workspace entry is the single management entrance.
    $('#ees-work-admin-link')?.remove();
  }
  function treeHTML(data, ids, depth=0, editing=false, run=null) {
    return (ids || []).map(id=>{
      const n=data.nodes[id];if(!n||depth>3)return '';
      const children=n.children || [],key=expansionKey(data,run),open=editing?!editorCollapsed.has(id):Boolean(expansionState(key).get(id));
      const active=editing?editorId===id:selectedId()===id && (!run || selectedCase()?.id===run.id);
      const ns=run?.node_states?.[id],itemStatus=ns?.status || 'unstarted';
      const count=ns?.progress,failed=ns?.failed_count || 0,excluded=ns?.excluded_count || 0;
      let summary=ns?`${count?.done || 0}/${count?.total || 0} 완료${excluded?' · 제외 '+excluded:''}`:'시작 전';
      if(n.type==='p'&&!run&&scopeCases(id).filter(c=>!finished(c)).length>1)summary='진행 '+scopeCases(id).filter(c=>!finished(c)).length+'건 · 실행 선택';
      return `<div class="ew-tree-row" style="--depth:${depth}">${children.length?button(open?'⌄':'›','expand',`data-node-id="${esc(id)}" data-expansion-key="${esc(key)}" data-case-id="${esc(run?.id || '')}" class="ew-expand" aria-label="${esc(n.name)} ${open?'접기':'펼치기'}" aria-expanded="${open}"`):'<span class="ew-expand" aria-hidden="true"></span>'}<button type="button" data-action="${editing?'edit_node':'select'}" data-node-id="${esc(id)}" data-process-id="${esc(lineage(id,data)[0]?.id || id)}" aria-current="${active?'step':'false'}"><span class="ew-type" aria-label="${levels[n.type]}">${esc(n.type.toUpperCase())}</span><span class="ew-tree-label">${esc(n.name)}${!editing&&children.length?`<small class="ew-tree-meta">${ns?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${failed?'확인 필요 '+failed:esc(statuses[itemStatus])}</span> · `:''}${esc(summary)}</small>${n.type==='p'&&run?`<small class="ew-tree-meta">${esc(run.created_at?.slice(0,10) || '기존 실행')} · v${esc(run.version)}</small>`:''}`:''}</span>${!editing&&!children.length?`<span class="ew-tree-status" data-status="${esc(itemStatus)}">${esc(statuses[itemStatus])}</span>`:''}</button></div>${children.length&&open?treeHTML(data,children,depth+1,editing,run):''}`;
    }).join('');
  }
  const scopeIcon = kind => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${kind==='site'?'<path d="M3 21V11l6 3V8l6 3V3h4v18H3Z"/><path d="M7 18h1m4 0h1m4 0h1"/>':kind==='system'?'<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5m-18 5 9 5 9-5"/>':'<path d="m8 9 4-4 4 4m-8 6 4 4 4-4"/>'}</svg>`;
  function updateNavHTML(container,html) {
    if(container.__eesHTML===html)return;
    const active=container.contains(document.activeElement)?document.activeElement:null;
    const focused=active?{id:active.id,action:active.dataset.action,node:active.dataset.nodeId,picker:active.dataset.picker,value:active.dataset.value,category:active.dataset.workCategory}:null;
    container.__eesHTML=html;container.innerHTML=html;
    if(focused){const replacement=Array.from(container.querySelectorAll('button')).find(el=>focused.id?el.id===focused.id:el.dataset.action===focused.action&&el.dataset.nodeId===focused.node&&el.dataset.picker===focused.picker&&el.dataset.value===focused.value&&el.dataset.workCategory===focused.category);replacement?.focus({preventScroll:true});}
  }
  function renderScopeControls(container,data) {
    const site=data.sites[browsingSite],label=siteLabel(site);
    updateNavHTML(container,`<div class="ew-scope-card">${['site','system'].map(kind=>`<button type="button" id="ees-work-${kind}-trigger" class="ew-scope-trigger" data-action="scope_toggle" data-picker="${kind}" data-value="${esc(kind==='site'?browsingSite:browsingSystem)}" value="${esc(kind==='site'?browsingSite:browsingSystem)}" aria-haspopup="dialog" aria-expanded="${scopePicker===kind}" aria-controls="ees-work-scope-popover" aria-label="${kind==='site'?'작업 공장 선택: '+esc(label):'시스템 선택: '+esc(browsingSystem)}"><span class="ew-scope-icon">${scopeIcon(kind)}</span><span class="ew-scope-text"><span class="ew-scope-label">${kind==='site'?'작업 공장':'시스템'}</span><span class="ew-scope-value">${kind==='site'?`<span>${esc(site?.name || site?.factory || label)}</span><small>${esc(site?.country || '')}</small>`:esc(browsingSystem)}</span></span><span class="ew-scope-chevron">${scopeIcon('chevron')}</span></button>`).join('<div class="ew-scope-divider"></div>')}</div>`);
    renderScopePopover();
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
    if(!['site','system'].includes(kind)||!state)return;
    scopePicker=kind;renderNavigator();
    const popup=$('#ees-work-scope-popover'),options=popup?.querySelectorAll('[data-action=scope_choose]');
    (last?options?.[options.length-1]:popup?.querySelector('[aria-pressed=true]') || options?.[0])?.focus({preventScroll:true});
  }
  function renderNavigator() {
    $('#ees-work-navigator')?.remove();
    const entry=$('#ees-work-entry');if(!entry)return;
    const data=state?.catalog;
    if(!data){if(!entry.firstChild)entry.innerHTML='<p class="ew-caption">업무</p><p class="ew-muted">업무 절차를 불러오는 중입니다.</p>';return;}
    if(!entry.querySelector('.ew-scope-pickers'))entry.innerHTML='<div class="ew-scope-pickers"></div><div class="ew-work-navigation"></div>';
    renderScopeControls(entry.querySelector('.ew-scope-pickers'),data);
    const html=`<p class="ew-caption">업무 · 현재 진행</p>${Object.entries(categories).map(([id,label])=>{
      const roots=visibleRoots(id);
      return `<button type="button" class="ew-category" data-work-category="${id}" aria-expanded="${navOpen&&category===id}"><span>${label}</span><span aria-hidden="true">${navOpen&&category===id?'⌄':'›'}</span></button>${navOpen&&category===id?`<div class="ew-inline-tree" id="ees-work-tree">${roots.map(p=>{const c=chosenCase(p),tree=c?.tree_nodes?{nodes:c.tree_nodes}:c&&c.id===selectedCase()?.id?selectedCase().definition:data;return treeHTML(tree,[p],0,false,c);}).join('') || '<p class="ew-muted">게시된 절차가 없습니다.</p>'}</div>`:''}`;
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
    divider.addEventListener('pointerdown', event => {if (event.button !== 0) return; divider.dataset.pointer = ''; drag = {id:event.pointerId,start:event.clientX,width:host.getBoundingClientRect().width}; divider.setPointerCapture(event.pointerId); event.preventDefault();});
    divider.addEventListener('pointermove', event => {if (drag?.id === event.pointerId) {width = drag.width + drag.start - event.clientX; sizePanel();}});
    const finish = () => {drag = null; delete divider.dataset.pointer;}; divider.addEventListener('pointerup', finish); divider.addEventListener('pointercancel',finish); divider.addEventListener('lostpointercapture',finish);
    divider.addEventListener('keydown', event => {if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {event.preventDefault(); width = event.key==='Home'?360:event.key==='End'?760:width+(event.key==='ArrowLeft'?24:-24); sizePanel();}});
  }
  function sizePanel() {
    if (!host || !panelOpen) return; const layout = chatLayout(); if (!layout) return;
    const narrow = layout.row.getBoundingClientRect().width < 850;
    host.classList.toggle('ew-narrow',narrow); divider.hidden = narrow;
    width = Math.max(340, Math.min(width, 760, Math.max(340, layout.row.getBoundingClientRect().width - 430)));
    host.style.width = narrow ? 'min(100vw, 520px)' : width + 'px'; host.style.flexBasis = narrow ? 'auto' : width+'px';
    divider.setAttribute('aria-valuenow', String(Math.round(width))); divider.setAttribute('aria-valuemin','340'); divider.setAttribute('aria-valuemax','760');
  }
  let styledColumn=null;
  function openHost() {const layout = chatLayout(); if (!layout || !state || !selectedId()) return; ensureHost(); panelOpen = true; styledColumn=layout.column;styledColumn.classList.add('ees-work-chat-column');layout.row.append(divider,host); sizePanel();}
  function closeHost() {panelOpen = false; host?.remove(); divider?.remove();styledColumn?.classList.remove('ees-work-chat-column');styledColumn=null;}
  function registerPanel() {
    const manager = window.__eesWorkPanelV1, id = chatId();
    if (!chatRoute() || !selectedId() || !state || !manager) return;
    ensureHost();
    if (activeRegistration !== id || !manager.available(id,'workflow')) {
      if (activeRegistration !== null) manager.unregister(activeRegistration,'workflow');
      activeRegistration = id;
      manager.register(id,{key:'workflow',label:'업무 진행',hostId:host.id,open:openHost,close:closeHost,isOpen:()=>Boolean(host?.isConnected),onChange:info=>{panelInfo=info; renderTabs();},focus:()=>$('#ees-work-close',host)?.focus({preventScroll:true})});
    }
    manager.sync();
  }
  function renderTabs() {
    if (!host) return; const tabs = $('#ees-work-tabs',host), screens = panelInfo?.screens || window.__eesWorkPanelV1?.list?.(chatId()) || [{key:'workflow',label:'업무 진행'}];
    const html = screens.map(screen => button(screen.label,'panel_tab',`data-screen="${esc(screen.key)}" aria-selected="${screen.key==='workflow'}"`)).join('');
    if (tabs.innerHTML !== html) tabs.innerHTML = html;
  }
  function openPanel() {if(!chatRoute()||!state||!selectedId())return;registerPanel(); window.__eesWorkPanelV1?.select(chatId(),'workflow',{open:true,focus:false});}
  function nextJob(n) {
    const candidates=n.type==='j'?[n]:(n.children||[]).flatMap(id=>{const child=node(id);return child?.type==='j'?[child]:(child?.children||[]).map(node);});
    return candidates.find(item=>item&&status(item.id).applicable!==false&&status(item.id).status!=='passed'&&!(status(item.id).missing||[]).length);
  }
  function runTabs() {
    const active=scopeCases(processId()).filter(c=>!finished(c)),current=selectedCase();
    const picker=active.length>1?`<label>현재 실행<select id="ees-work-run-select">${active.map(c=>`<option value="${esc(c.id)}" ${c.id===current?.id?'selected':''}>${esc(runLabel(c))}</option>`).join('')}</select></label>`:'';
    return picker+`<nav class="ew-run-tabs" id="ees-work-run-view" aria-label="실행 기록"><button type="button" data-action="current_view" aria-pressed="${runView==='current'}">현재 작업</button><button type="button" data-action="history_view" aria-pressed="${runView==='history'}">실행 이력</button></nav>`;
  }
  function readOnlyNode(c,n) {
    const ns=c.node_states[n.id] || {},job=c.jobs[n.id],children=n.children || [];
    const header=`<div class="ew-heading"><span class="ew-caption">${levels[n.type]}</span>${badge(ns.status)}</div><h2 class="ew-title">${esc(n.name)}</h2>`;
    if(children.length)return header+`<p class="ew-muted">${ns.progress?.done || 0}/${ns.progress?.total || 0} 잡 완료 · 적용 제외 ${ns.excluded_count || 0}개</p><div class="ew-children">${children.map(id=>`<div class="ew-tool"><span class="ew-type">${esc(c.definition.nodes[id].type.toUpperCase())}</span><span>${esc(c.definition.nodes[id].name)}</span>${badge(c.node_states[id].status)}</div>`).join('')}</div>`;
    return header+((job?.checks || []).map(check=>`<section class="ew-check"><div class="ew-heading"><strong>${esc(check.name || check.tool_id || '')}</strong>${badge(check.status)}</div><p>${esc(check.message || check.detail || '')}</p></section>`).join('') || '<p class="ew-muted">기록된 점검 결과가 없습니다.</p>')+(job?.document?`<pre>${esc(job.document)}</pre>`:'');
  }

  function historyHTML() {
    const p=processId(),c=selectedCase(),cases=scopeCases(p);
    if(historyCase){const n=historyCase.definition.nodes[selectedId()] || historyCase.definition.nodes[historyCase.process_id];return `${button('실행 목록으로','history_view')}<p class="ew-notice">이전 실행 · 읽기 전용<br>가운데 대화와 왼쪽 트리는 현재 실행을 유지합니다.</p><p class="ew-muted">${esc(siteLabel(historyCase.site))} · ${esc(historyCase.system)}<br>${esc(runLabel(historyCase))}</p>${readOnlyNode(historyCase,n)}`;}
    return `<h2 class="ew-title">실행 이력</h2><p class="ew-muted">${esc(siteLabel(state.catalog.sites[browsingSite]))} · ${esc(browsingSystem)} · ${esc(nameOf(p))}</p><div class="ew-case-list">${cases.map(item=>`<button type="button" data-action="history_case" data-case-id="${esc(item.id)}" ${item.id===c?.id?'disabled':''}><strong>${esc(runLabel(item))}</strong><span>${item.id===c?.id?'현재 실행 · ':''}${esc(statuses[item.status])} · ${item.progress.done}/${item.progress.total} 완료</span></button>`).join('') || '<p class="ew-notice">아직 기록된 실행이 없습니다.</p>'}</div>`;
  }
  function previewHTML() {
    const n=node(browseNodeId);if(!n)return '<p class="ew-muted">왼쪽에서 업무 절차를 선택하세요.</p>';
    const p=lineage(n.id)[0],cases=scopeCases(p.id),active=cases.filter(c=>!finished(c));
    return `<div class="ew-heading"><span class="ew-caption">${levels[n.type]} · 절차 미리보기</span>${badge(active.length?'in_progress':'unstarted')}</div><h2 class="ew-title">${esc(n.name)}</h2><p class="ew-muted">${esc(n.description || '')}</p><p class="ew-breadcrumb">${esc(siteLabel(state.catalog.sites[browsingSite]))} · ${esc(browsingSystem)}<br>${esc(lineage(n.id).map(v=>v.name).join(' › '))}</p>${active.length?`<section class="ew-card"><h3>이어서 진행할 실행 선택</h3><p class="ew-muted">이 공장에 진행 중인 실행이 ${active.length}건 있습니다.</p><div class="ew-case-list">${active.map(c=>`<button type="button" data-action="open_case" data-case-id="${esc(c.id)}"><strong>${esc(runLabel(c))}</strong><span>${esc(statuses[c.status])} · ${c.progress.done}/${c.progress.total} 완료</span></button>`).join('')}</div></section>`:`<section class="ew-card"><h3>이 공장에서 시작</h3><p class="ew-muted">게시된 절차 v${state.catalog.version}에 공장 조건을 적용합니다. 시작한 실행은 고정된 절차와 별도의 대화를 사용합니다.</p>${button('이 공장에서 시작','start_case','id="ees-work-case-start" class="ew-primary" data-mutation')}</section>`}${n.children?.length?`<h3>${n.type==='p'?'하위 태스크':'하위 잡'}</h3><div class="ew-children">${n.children.map(id=>`<button type="button" data-action="select" data-node-id="${esc(id)}"><span class="ew-type">${esc(node(id).type.toUpperCase())}</span><span>${esc(node(id).name)}</span></button>`).join('')}</div>`:`<section class="ew-card"><h3>점검 기준</h3><p>${esc(n.rule || '')}</p>${(n.tools || []).map(id=>`<div class="ew-tool">${esc(state.catalog.tools[id]?.name || id)}</div>`).join('')}</section>`}`;
  }
  async function showHistory(id) {
    if(!scopeCases(processId()).some(c=>c.id===id))return {ok:false};
    const serial=++historyRequest,at=generation,key=caseKey(processId()),auth=token();runView='history';historyCase=null;
    try{const result=await api('state?'+new URLSearchParams({case_id:id}));if(serial!==historyRequest||at!==generation||key!==caseKey(processId())||auth!==token())return {ok:false};historyCase=result.case;renderPanel();openPanel();return {ok:true};}
    catch(error){if(serial===historyRequest&&at===generation){errorMessage=error.message;renderPanel();}return {ok:false};}
  }
  function renderPanel() {
    if (!chatRoute() || !state || !selectedId()) {closeHost(); return;} ensureHost();
    if(runView==='history' || !selectedCase()) {$('#ees-work-content',host).innerHTML=runTabs()+alertHTML()+(runView==='history'?historyHTML():previewHTML());renderTabs();registerPanel();setBusy();return;}
    const c = currentCase(), n = node(c.selected_id) || node(c.process_id), ns = status(n.id);
    const progress = ns.progress || {done:0,total:0},next=nextJob(n);
    $('#ees-work-content',host).innerHTML = `${runTabs()}${alertHTML()}<div class="ew-heading"><span class="ew-caption">${levels[n.type]} · ${esc(c.system)}</span>${badge(ns.status)}</div><h2 class="ew-title">${esc(n.name)}</h2><p class="ew-muted">${esc(n.description || '')}</p><p class="ew-breadcrumb">${esc(lineage(n.id).map(v=>v.name).join(' › '))}</p>${n.type==='j'?jobHTML(n,c,ns):`<section class="ew-card"><div class="ew-heading"><h3>진행 상황</h3><strong>${progress.done} / ${progress.total}</strong></div><progress max="${Math.max(1,progress.total)}" value="${progress.done}"></progress><p class="ew-muted">${esc(c.site?.name || c.site?.factory)} · 절차 v${c.version}</p>${next?button('다음 작업: '+next.name,'select',`data-node-id="${esc(next.id)}"`):''}</section>${missingHTML(ns)}<section><h3>${n.type==='p'?'단계별 진행':'하위 작업'}</h3><div class="ew-children">${(n.children || []).map(id=>{const child=node(id),s=status(id);return `<button type="button" data-action="select" data-node-id="${esc(id)}"><span class="ew-type">${esc(child?.type?.toUpperCase())}</span><span><strong>${esc(child?.name)}</strong><small>${esc(child?.description || '')}</small></span>${badge(s.status)}</button>`;}).join('')}</div></section><button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation>준비된 하위 작업 실행</button><p class="ew-muted">수동 확인·초안 검토가 필요한 작업에서는 멈춥니다.</p>`}<details class="ew-instructions"><summary>적용 지침과 스킬</summary>${(c.context?.skills || []).map(skill=>`<div><strong>${esc(skill.name)}</strong><p>${esc(skill.body || skill.message || '')}</p></div>`).join('')}${lineage(n.id).map(v => `<div><strong>${esc(v.name)}</strong><p>${esc(v.instructions || '별도 지침 없음')}</p>${(v.skills || []).map(id=>`<span class="ew-badge">${esc(c.definition.skills?.[id]?.name || id)}</span>`).join('')}</div>`).join('')}</details><p class="ew-footnote">연결 점검은 합성 시연 결과입니다. 실제 업무 시스템은 호출하지 않습니다. 가운데 AI 대화는 기존 모델을 사용합니다.</p>`;
    if(finished(c)){$('#ees-work-content',host).innerHTML=runTabs()+alertHTML()+`<p class="ew-muted">${esc(siteLabel(c.site))} · ${esc(c.system)} · ${esc(runLabel(c))}</p><p class="ew-notice">이 실행은 완료됐습니다. 새 실행을 시작해도 기존 기록은 유지됩니다.</p>`+readOnlyNode(c,n)+(n.type==='p'?button('새 실행 시작','start_case','class="ew-primary" data-mutation'):button('프로세스 완료 보기','select',`data-node-id="${esc(c.process_id)}"`));}
    renderTabs(); registerPanel(); setBusy();
  }
  function missingHTML(ns) {return (ns.missing || []).length ? `<p class="ew-notice">먼저 완료할 작업: ${ns.missing.map(id=>esc(nameOf(id))).join(', ')}</p>` : '';}
  function jobHTML(n,c,ns) {
    const job = c.jobs[n.id] || {}, inputs = {db:c.site.db,ap:c.site.ap,site:[c.site.country,c.site.name,c.site.line].join(' · '),interface:c.site.interface?c.system+' · '+c.site.name+' 시스템 간 연계 · 예시':'',...(job.inputs || {})};
    const fields = Array.from(new Set(Object.values(n.bindings || {}).filter(v=>['db','ap','site','interface'].includes(v))));
    const labels = {db:'DB 대상',ap:'AP 대상',site:'공장 확인',interface:'인터페이스 대상'};
    const checks = job.checks || [], history = job.history || [];
    return `${missingHTML(ns)}${!ns.applicable ? '<p class="ew-notice">이 공장 조건에서는 적용하지 않는 작업입니다.</p>':''}${fields.length?`<form id="ees-work-inputs" class="ew-card"><h3>점검 입력</h3>${fields.map(key=>`<label>${labels[key]}<input name="${key}" value="${esc(inputs[key] || '')}" autocomplete="off" placeholder="시연용 대상 입력"></label>`).join('')}<button id="ees-work-inputs-save" type="submit" data-mutation>입력값 저장</button><p class="ew-muted">저장한 입력값은 이 대화의 AI도 참고합니다. 비밀번호·접속 키는 입력하지 마세요.</p></form>`:''}<section class="ew-card"><h3>${n.mode==='manual'?'확인할 내용':n.mode==='draft'?'검토할 초안':'실행 순서와 점검 기준'}</h3><p>${esc(n.rule || n.description)}</p>${(n.tools || []).map((id,i)=>`<div class="ew-tool"><span class="ew-index">${i+1}</span><div><strong>${esc(c.definition.tools?.[id]?.name || id)}</strong><small>${esc(c.definition.tools?.[id]?.description || c.definition.tools?.[id]?.purpose || '')}</small></div></div>`).join('')}${n.mode==='draft'?`<form id="ees-work-document"><label>작업 초안<textarea name="document" rows="6" placeholder="가운데 AI에게 초안을 요청하거나 직접 작성하세요.">${esc(job.document || '')}</textarea></label><button type="submit" data-mutation>초안 저장</button></form>`:''}<button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation ${ns.applicable===false||(ns.missing || []).length?'disabled data-unavailable="true"':''}>${n.mode==='manual'?'확인 완료':n.mode==='draft'?'검토 완료':job.attempt?'다시 점검':'점검 실행'}</button></section>${checks.length?`<section class="ew-card"><div class="ew-heading"><h3>점검 결과</h3><span>${esc(job.attempt || 1)}차 실행</span></div>${checks.map(check=>`<div class="ew-check"><div class="ew-heading"><strong>${esc(check.name || c.definition.tools?.[check.id || check.tool_id || check.tool]?.name || check.id || check.tool_id || check.tool)}</strong>${badge(check.status)}</div><p>${esc(check.message || check.detail || check.summary || '')}</p>${check.evidence?`<pre>${esc(typeof check.evidence==='string'?check.evidence:JSON.stringify(check.evidence,null,2))}</pre>`:''}</div>`).join('')}</section>`:''}${history.length?`<details class="ew-history"><summary>이전 실행 기록 (${history.length})</summary>${history.map((run,i)=>`<section class="ew-card"><strong>${esc(run.attempt || i+1)}차 실행</strong> ${badge(run.status)}<p>${esc(run.at || run.completed_at || '')}</p>${(run.checks || []).map(check=>`<p>${esc(check.name || check.id || check.tool_id || check.tool)} · ${esc(statuses[check.status] || check.status)} · ${esc(check.message || check.detail || '')}</p>`).join('')}</section>`).join('')}</details>`:''}`;
  }

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
    designer.innerHTML=`<header><div><p class="ew-caption">워크스페이스 · 업무 절차</p><h1>업무 설계</h1><p class="ew-muted">시스템 전문가가 절차와 공장 조건을 관리합니다. 게시한 변경은 새 진행 건부터 적용됩니다.</p></div><div class="ew-actions">${button('초안 저장','save_draft','data-mutation')}${button('검증','validate_draft','data-mutation')}${button('게시','publish','data-mutation class="ew-primary"')}</div></header>${alertHTML()}<div class="ew-designer-status">게시 v${esc(state.catalog.version)} · 초안 ${esc(editorRevision)}${editorDirty?' · 저장하지 않은 변경':''} · ${state.validated_revision===editorRevision&&!editorDirty?'검증 완료':'검증 필요'}</div><nav class="ew-editor-tabs">${[['workflow','프로세스 · 태스크 · 잡'],['tools','도구 연결'],['skills','스킬 · 지침'],['sites','공장 조건']].map(([id,label])=>button(label,'editor_tab',`data-tab="${id}" aria-selected="${editorTab===id}"`)).join('')}</nav>${editorTab==='workflow'?workflowEditor():assetEditor()}`;
    setBusy();
  }
  function workflowEditor() {
    const n=editor.nodes[editorId]; if(!n)return `<section class="ew-card"><p class="ew-muted">프로세스를 추가하고 태스크와 잡을 구성해 주세요.</p>${button('프로세스 추가','add_process')}</section>`;
    const parents=Object.values(editor.nodes).filter(x=>x.type===(n.type==='j'?'t':n.type==='t'?'p':'none'));
    const conditions=[['all','모든 공장'],['interface','인터페이스 대상 있음'],['reuse','기존 인프라 재사용'],['new-infra','신규 인프라 준비'],...Array.from(new Set(Object.values(editor.sites).map(s=>s.country))).map(v=>['country:'+v,'국가: '+v]),...Object.values(editor.sites).map(s=>['factory:'+s.id,'공장: '+s.name]),...Array.from(new Set(Object.values(editor.sites).map(s=>s.line).filter(Boolean))).map(v=>['line:'+v,'라인: '+v])];
    return `<div class="ew-editor-layout"><aside><div class="ew-heading"><h3>업무 구조</h3>${button('프로세스 추가','add_process')}</div>${Object.entries(categories).map(([id,label])=>`<h4>${label}</h4>${treeHTML(editor,editor.roots[id],0,true)}`).join('')}</aside><form id="ees-work-node-form" class="ew-node-editor"><div class="ew-heading"><h2>${levels[n.type]} 편집</h2><div class="ew-actions">${n.type!=='j'?button(n.type==='p'?'태스크 추가':'잡 추가','add_child'):''}${button('위로','move_up')}${button('아래로','move_down')}${button('삭제','delete_node')}</div></div><label>이름<input name="name" value="${esc(n.name)}" maxlength="160" required></label><label>설명<textarea name="description" rows="2">${esc(n.description || '')}</textarea></label>${n.type==='p'?`<label>업무 분류<select name="category">${Object.entries(categories).map(([id,name])=>`<option value="${id}" ${n.category===id?'selected':''}>${name}</option>`).join('')}</select></label>`:`<label>상위 ${n.type==='j'?'태스크':'프로세스'}<select name="parent">${parents.map(p=>`<option value="${esc(p.id)}" ${p.id===n.parent?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label>`}<div class="ew-form-grid"><label>적용 조건<select name="condition">${conditions.map(([id,label])=>`<option value="${esc(id)}" ${n.condition===id?'selected':''}>${esc(label)}</option>`).join('')}</select></label><label class="ew-checkbox"><input type="checkbox" name="enabled" ${n.enabled!==false?'checked':''}>이 단계 사용</label></div>${n.type==='j'?`<label>진행 방식<select name="mode">${[['manual','담당자 확인'],['draft','초안 작성 후 검토'],['tool','도구로 자동 점검']].map(([id,label])=>`<option value="${id}" ${n.mode===id?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<label>완료 판정 기준<textarea name="rule" rows="2">${esc(n.rule || '')}</textarea></label><label>이 단계의 지침<textarea name="instructions" rows="4">${esc(n.instructions || '')}</textarea></label><fieldset><legend>적용 시스템</legend>${(editor.systems||[]).map(system=>`<label class="ew-checkbox"><input type="checkbox" name="systems" value="${esc(system)}" ${(!n.systems||n.systems.includes(system))?'checked':''}>${esc(system)}</label>`).join('')}</fieldset><fieldset><legend>선행 작업</legend><div class="ew-option-grid">${Object.values(editor.nodes).filter(x=>x.id!==n.id&&lineage(x.id,editor)[0]?.id===lineage(n.id,editor)[0]?.id&&!lineage(x.id,editor).some(a=>a.id===n.id)&&!lineage(n.id,editor).some(a=>a.id===x.id)).map(x=>`<label class="ew-checkbox"><input type="checkbox" name="deps" value="${esc(x.id)}" ${(n.deps||[]).includes(x.id)?'checked':''}>${esc(x.name)}</label>`).join('')}</div></fieldset><fieldset><legend>사용할 스킬</legend>${Object.values(editor.skills).map(s=>`<label class="ew-checkbox"><input type="checkbox" name="skills" value="${esc(s.id)}" ${s.id==='common'?'checked disabled':(n.skills||[]).includes(s.id)?'checked':''}>${esc(s.name)}</label>`).join('')}</fieldset><fieldset><legend>${n.type==='j'?'실행 도구와 입력 연결':'하위 작업에서 허용할 도구'}</legend><p class="ew-muted">${n.type==='j'?'위에서 아래 순서로 실행합니다. 실제 연결이 없는 도구는 미수행으로 표시합니다.':'선택하면 하위 단계는 이 도구들만 사용할 수 있습니다. 비워두면 별도 제한을 추가하지 않습니다.'}</p>${(n.tools||[]).map((id,index)=>`<div class="ew-tool-editor"><span>${index+1}. ${esc(editor.tools[id]?.name || id)}</span><select name="binding:${esc(id)}" aria-label="${esc(editor.tools[id]?.name || id)} 입력">${[['site','공장'],['db','DB 대상'],['ap','AP 대상'],['interface','인터페이스']].filter(([key])=>key===editor.tools[id]?.input).map(([key,label])=>`<option value="${key}" ${n.bindings?.[id]===key?'selected':''}>${label}</option>`).join('')}</select>${button('위로','tool_up',`data-tool-id="${esc(id)}"`)}${button('삭제','tool_remove',`data-tool-id="${esc(id)}"`)}</div>`).join('')}<div class="ew-inline"><select id="ees-work-tool-add" aria-label="추가할 도구">${Object.values(editor.tools).filter(t=>!(n.tools||[]).includes(t.id)).map(t=>`<option value="${esc(t.id)}">${esc(t.name)}${t.adapter==='unavailable'?' · 실행 연결 필요':''}</option>`).join('')}</select>${button('도구 추가','tool_add')}</div></fieldset><button type="submit">변경 내용 적용</button></form></div>`;
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

  function stashDraft() {
    const bridge=window.__eesNativeDraftV1,snapshot=bridge?.read();
    // ready/read verifies the native editor's chat ID against the route. A
    // newly opened chat may be editable before our state request finishes;
    // never save its text under the previous workflow's draft owner.
    if(snapshot){const key=chatId()?'chat/'+chatId():visibleDraftKey;draftSnapshots.set(key,JSON.stringify(snapshot));bridge.flush();}
  }
  function restoreDraft() {
    if(!draftTarget||draftTarget.url!==location.pathname+location.search)return;
    clearTimeout(draftTimer);const target=draftTarget,serial=draftSerial;
    const apply=async()=>{
      if(serial!==draftSerial||draftTarget!==target||target.url!==location.pathname+location.search)return;
      const bridge=window.__eesNativeDraftV1;
      if(!bridge?.ready()){draftTimer=setTimeout(apply,50);return;}
      const saved=draftSnapshots.get(target.key);
      // Bound conversations reuse the native storage format. An unseen scope
      // starts with an empty composer instead of inheriting another factory.
      if(saved!==undefined||!chatId()){
        const restored=await bridge.restore(saved || JSON.stringify({prompt:'',files:[]}));
        if(!restored){if(serial===draftSerial)draftTimer=setTimeout(apply,50);return;}
      }
      if(serial===draftSerial){visibleDraftKey=target.key;draftTarget=null;}
    };
    apply();
  }
  function navigate(url,draftKey='') {
    stashDraft();navigationTarget=url;
    if(draftKey){draftSerial++;draftTarget={url,key:draftKey};if(url.startsWith('/?')){const saved=draftSnapshots.get(draftKey);try{if(saved)sessionStorage.setItem('chat-input',saved);else sessionStorage.removeItem('chat-input');}catch(_){}}}
    const link=document.createElement('a');link.href=url;link.hidden=true;document.body.append(link);link.click();link.remove();
    restoreDraft();
  }

  let binding = null;
  async function ensureChat(id) {
    if(typeof id!=='string'||!id||!available())return {ok:false};
    if(location.pathname==='/' && pendingId) {
      // A tool from an older chat may arrive while a new case is being prepared.
      // Only the real SPA route identifies which chat owns this submission.
      await new Promise(resolve=>{
        let timer; const check=()=>{if(location.pathname!=='/'||!available()){clearTimeout(timer);window.navigation?.removeEventListener('navigatesuccess',check);window.removeEventListener('popstate',check);resolve();}};
        window.navigation?.addEventListener('navigatesuccess',check);window.addEventListener('popstate',check);
        timer=setTimeout(()=>{window.navigation?.removeEventListener('navigatesuccess',check);window.removeEventListener('popstate',check);resolve();},1200);check();
      });
    }
    if(chatId()!==id)return {ok:false};
    if(!pendingId)return {ok:true,case_id:currentCase()?.id || ''};
    const created=createdChats.get(id);if(!created || created.caseId!==pendingId || created.auth!==token())return {ok:false};
    if(binding)return binding;
    const wanted=pendingId,c=currentCase();
    if(c?.chat_id&&c.id===wanted)return {ok:true,case_id:wanted};
    const at=generation,auth=token();
    binding=(async()=>{
      try{
        const candidate=c?.id===wanted?c:(await api('state?'+new URLSearchParams({case_id:wanted}))).case;
        if(chatId()!==id||auth!==token()||!available()||pendingId!==wanted||!candidate)return {ok:false};
        const result=await api('action',{action:'bind',chat_id:id,case_id:wanted,node_id:'',payload:{},expected_revision:candidate.revision});
        if(pendingId===wanted){pendingId='';pendingSubmitted=false;createdChats.delete(id);}
        if(available()&&auth===token()&&chatId()===id){
          accept(result);
          // A different root preview can clear native message history while
          // creation is in flight. Enter the saved chat through its normal SPA
          // link so native Chat loads those messages as well as the work case.
          if(created.resume)navigate('/c/'+encodeURIComponent(id),'chat/'+id);
          openPanel();
        }
        return {ok:true,case_id:result.case?.id || wanted};
      }catch(error){if(at===generation){errorMessage=error.message;render();}return {ok:false};}
      finally{binding=null;}
    })();return binding;
  }
  function resetHistory() {runView='current';historyCase=null;historyRequest++;}
  function previewRoute(id) {return '/?'+new URLSearchParams({ees_site:browsingSite,ees_system:browsingSystem,ees_process:id});}
  async function openCase(c,id='') {
    if(!c)return {ok:false};
    const epoch=++navigationRequest;resetHistory();chosenCases.set(caseKey(c.process_id),c.id);browseActive=true;newCase=false;pendingId=c.chat_id?'':c.id;pendingSubmitted=false;
    const wanted=id || c.selected_id || c.process_id;
    if(c.chat_id&&c.chat_id!==chatId()) {desiredCase=c.id;desiredNode=wanted;reopenPanel=true;navigate('/c/'+encodeURIComponent(c.chat_id),'chat/'+c.chat_id);return {ok:true};}
    if(!c.chat_id&&(chatId()||!chatRoute())) {desiredCase=c.id;desiredNode=wanted;reopenPanel=true;navigate(previewRoute(c.process_id),'case/'+c.id);return {ok:true};}
    const oldDraft=visibleDraftKey;stashDraft();const targetDraft=c.chat_id?'chat/'+c.chat_id:'case/'+c.id;if(targetDraft!==oldDraft){draftSerial++;draftTarget={url:location.pathname+location.search,key:targetDraft};}
    const at=generation;await refresh();if(at!==generation||epoch!==navigationRequest)return {ok:false};
    if(currentCase()?.id===c.id&&wanted!==currentCase().selected_id)await action('select',{},wanted);
    openPanel();return {ok:true};
  }
  async function selectWork(id,explicitProcess='') {
    if(!state)return {ok:false};navigationRequest++;stashDraft();resetHistory();browseActive=true;navOpen=true;
    const p=explicitProcess || lineage(id)[0]?.id || lineage(id,state.catalog)[0]?.id;
    if(!p)return {ok:false};
    const candidate=chosenCase(p),data=candidate?.tree_nodes?{nodes:candidate.tree_nodes}:state.catalog;
    if(!data.nodes[id])return {ok:false};
    category=data.nodes[p]?.category || state.catalog.nodes[p]?.category || category;
    revealSelection(id,data,candidate,true);browseNodeId=id;rememberScope();
    if(candidate)return openCase(candidate,id);
    newCase=true;
    const targetDraft='scope/'+scopeKey()+'/'+p;
    if(!chatId()&&visibleDraftKey==='general'){const draft=draftSnapshots.get('general');if(draft)draftSnapshots.set(targetDraft,draft);visibleDraftKey=targetDraft;}
    else if(currentCase() || (!chatId()&&visibleDraftKey!==targetDraft)){pendingId='';pendingSubmitted=false;reopenPanel=true;navigate(previewRoute(p),targetDraft);return {ok:true};}
    render();openPanel();return {ok:true};
  }
  async function switchScope(site,system,process='') {
    if(!state?.catalog.sites[site]||!state.catalog.systems.includes(system))return {ok:false};
    closeScopePicker();
    const serial=++navigationRequest;stashDraft();rememberScope();resetHistory();browsingSite=site;browsingSystem=system;browseActive=true;newCase=true;navOpen=true;
    const saved=scopeSelections.get(scopeKey());category=saved?.category || category;
    const roots=visibleRoots(category),requested=process || saved?.nodeId || '';
    const requestedRoot=lineage(requested,state.catalog)[0]?.id || scopeCases().find(c=>c.tree_nodes?.[requested])?.process_id;
    browseNodeId=roots.includes(requestedRoot)?requested:roots[0] || '';
    const p=roots.includes(requestedRoot)?requestedRoot:roots[0] || '',candidate=chosenCase(p);
    if(candidate)return openCase(candidate,browseNodeId);
    pendingId='';pendingSubmitted=false;
    const url=previewRoute(p);reopenPanel=true;
    if(location.pathname+location.search!==url)navigate(url,'scope/'+scopeKey()+'/'+p);else{await refresh();if(serial===navigationRequest)openPanel();}
    return {ok:true};
  }
  async function startCase() {
    const p=processId();if(!p)return;
    const active=scopeCases(p).filter(c=>!finished(c));
    if(active.length){if(active.length===1)await openCase(active[0]);else{newCase=true;render();openPanel();}return;}
    stashDraft();const previousDraftKey=visibleDraftKey,separate=Boolean(currentCase()),result=await action('create',{site_id:browsingSite,system:browsingSystem,process_id:p},'',{case_id:'',chat_id:separate||!chatRoute()?'':chatId(),expected_revision:0});
    if(!result)return;
    browseActive=true;newCase=false;navOpen=true;resetHistory();
    if(separate||!chatRoute()){visibleDraftKey=previousDraftKey;pendingId=result.case.id;pendingSubmitted=false;reopenPanel=true;navigate(previewRoute(p),'case/'+result.case.id);}
    else{render();openPanel();}
  }
  async function handleClick(event) {
    const categoryButton=event.target.closest('[data-work-category]');
    if(categoryButton?.closest('#ees-work-entry')){
      event.stopPropagation();const wanted=categoryButton.dataset.workCategory;
      if(navOpen&&category===wanted){navOpen=false;renderNavigator();return;}
      category=wanted;navOpen=true;const first=visibleRoots(category)[0];
      if(first)await selectWork(first);else renderNavigator();return;
    }
    const target=event.target.closest('[data-action]');if(!target?.closest('[data-ees-work]'))return;
    event.stopPropagation();const a=target.dataset.action;
    if(a==='scope_toggle'){scopePicker===target.dataset.picker?closeScopePicker(true):openScopePicker(target.dataset.picker);}
    else if(a==='scope_choose'){const kind=target.dataset.picker,value=target.dataset.value;if(kind!==scopePicker||!['site','system'].includes(kind)||!(kind==='site'?Object.hasOwn(state.catalog.sites,value):state.catalog.systems.includes(value)))return;closeScopePicker(true);if(value===(kind==='site'?browsingSite:browsingSystem))return;await switchScope(kind==='site'?value:browsingSite,kind==='system'?value:browsingSystem);}
    else if(a==='nav_close'){navOpen=false;renderNavigator();}
    else if(a==='nav_open'){navOpen=true;renderNavigator();}
    else if(a==='expand'){const id=target.dataset.nodeId;if(target.closest('#ees-work-designer')){captureEditor();editorCollapsed.has(id)?editorCollapsed.delete(id):editorCollapsed.add(id);renderDesigner();}else{const run=state?.cases.find(c=>c.id===target.dataset.caseId),data=run?.tree_nodes?{nodes:run.tree_nodes}:run&&run.id===selectedCase()?.id?selectedCase().definition:state?.catalog;toggleBranch(id,target.dataset.expansionKey,data);renderNavigator();}}
    else if(a==='panel_open')openPanel();
    else if(a==='panel_close'){window.__eesWorkPanelV1?.close(chatId());}
    else if(a==='panel_tab'){window.__eesWorkPanelV1?.select(chatId(),target.dataset.screen,{open:true});}
    else if(a==='open_case'){await openCase(state.cases.find(c=>c.id===target.dataset.caseId));}
    else if(a==='start_case'){await startCase();}
    else if(a==='current_view'){resetHistory();renderPanel();}
    else if(a==='history_view'){resetHistory();runView='history';renderPanel();}
    else if(a==='history_case'){await showHistory(target.dataset.caseId);}
    else if(a==='select'){
      await selectWork(target.dataset.nodeId,target.dataset.processId);
    }else if(a==='run'){
      const n=node(target.dataset.nodeId),inputsForm=$('#ees-work-inputs',host),docForm=$('#ees-work-document',host);
      if(inputsForm){const inputs=Object.fromEntries(new FormData(inputsForm));if(Array.from(inputsForm.querySelectorAll('input')).some(input=>input.value!==input.defaultValue)){if(!await action('update_inputs',{inputs},n.id))return;}}
      if(n?.mode==='draft'&&docForm){const documentText=new FormData(docForm).get('document');if(documentText!==currentCase().jobs[n.id]?.document){if(!await action('run',{document:documentText},n.id))return;}}
      await action('run',n?.mode==='manual'||n?.mode==='draft'?{confirm:true}:{},target.dataset.nodeId);
    }else if(['save_draft','validate_draft','publish'].includes(a)){
      captureEditor();
      if(a==='save_draft'){await action(a,{definition:editor});return;}
      if(editorDirty){errorMessage='변경한 초안을 먼저 저장해 주세요.';renderDesigner();return;}
      if(a==='publish'&&!confirm('이 초안을 게시할까요? 새 진행 건부터 적용되며 기존 진행 건의 절차와 결과는 유지됩니다.'))return;
      await action(a);
    }else if(state?.can_manage)localEdit(a,target);
  }
  async function handleSubmit(event) {
    const form=event.target;if(!form.closest?.('[data-ees-work]'))return;event.preventDefault();event.stopPropagation();
    const values=Object.fromEntries(new FormData(form));
    if(form.id==='ees-work-case-create'){await startCase();    }else if(form.id==='ees-work-inputs')await action('update_inputs',{inputs:values},currentCase().selected_id);
    else if(form.id==='ees-work-document')await action('run',{document:values.document},currentCase().selected_id);
    else if(form.id==='ees-work-node-form'||form.classList.contains('ew-asset-form')){captureEditor();renderDesigner();}
  }
  function render(){sidebar();renderNavigator();renderContext();renderPanel();renderDesigner();}
  function cleanup() {
    closeScopePicker();treeExpansions.clear();generation++;request++;state=null;pendingId='';pendingSubmitted=false;browseActive=false;scopeSelections.clear();chosenCases.clear();draftSnapshots.clear();creationTickets.clear();createdChats.clear();draftSerial++;draftTarget=null;clearTimeout(draftTimer);resetHistory();editor=null;editorDirty=false;errorMessage='';navOpen=false;
    if(activeRegistration!==null)window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;closeHost();
    ['ees-work-entry','ees-work-admin-link','ees-work-navigator','ees-work-context'].forEach(id=>document.getElementById(id)?.remove());restoreWorkspace(true);
  }
  function sync() {
    scheduled=false;
    const auth=token();
    if(!available()){if(state||$('#ees-work-entry'))cleanup();lastRoute='';identity=auth;return;}
    if(identity!==auth){cleanup();window.__eesWorkPanelV1?.destroy();identity=auth;lastRoute='';}
    if(!window.__eesWorkPanelV1)window.__eesStartWorkPanelV1?.();
    sidebar();workspaceTab();
    const path=location.pathname+location.search;
    if(lastRoute!==path){
      closeScopePicker();const previous=lastRoute;lastRoute=path;generation++;request++;resetHistory();
      // A first completion can arrive after another factory was previewed on
      // the root route. Its server-issued chat still belongs to the captured
      // creation ticket, not whichever case is currently being browsed.
      const created=createdChats.get(chatId());
      if(previous.split('?')[0]==='/'&&created?.auth===auth){pendingId=created.caseId;pendingSubmitted=true;desiredCase='';desiredNode='';reopenPanel=false;draftSerial++;draftTarget=null;clearTimeout(draftTimer);}
      if(path!==navigationTarget&&!pendingSubmitted){browseActive=false;reopenPanel=false;desiredNode='';desiredCase='';pendingId='';}navigationTarget='';
      if(activeRegistration!==null){window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;}closeHost();$('#ees-work-context')?.remove();
      if(!adminRoute())restoreWorkspace();else{navOpen=false;renderNavigator();sidebar();}
      if(pendingId&&pendingSubmitted&&previous.split('?')[0]==='/'&&chatId()){ensureChat(chatId());return;}
      state=null;refresh();return;
    }
    if(state){
      if(browseActive&&chatRoute()){
        if(!$('#ees-work-context'))renderContext();
        registerPanel();
      }
      if(adminRoute()){if(!designer?.isConnected)renderDesigner();else hideWorkspaceContent();}
    }
    positionNav();
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(sync);}}
  function beginChatCreation() {
    if(!pendingId || location.pathname!=='/' || currentCase()?.id!==pendingId || !available())return null;
    const ticket=String(++creationSerial);creationTickets.set(ticket,{caseId:pendingId,auth:token(),route:location.pathname+location.search});return ticket;
  }
  function finishChatCreation(ticket,id) {
    const record=creationTickets.get(ticket);creationTickets.delete(ticket);
    if(!record||typeof id!=='string'||!id||record.auth!==token()||!available())return;
    record.resume=record.route!==location.pathname+location.search||currentCase()?.id!==record.caseId;
    createdChats.set(id,record);
    if(pendingId===record.caseId){pendingSubmitted=true;schedule();}
  }
  document.addEventListener('click',handleClick,true);document.addEventListener('submit',handleSubmit,true);
  document.addEventListener('input',event=>{if(event.target.closest?.('#ees-work-designer'))editorDirty=true;});
  document.addEventListener('change',event=>{
    if(event.target.id==='ees-work-run-select'){openCase(scopeCases(processId()).find(c=>c.id===event.target.value));return;}
    const form=event.target.closest?.('.ew-asset-form');
    if(form&&event.target.name==='reference'){
      const item=(state.catalog['available_'+form.dataset.kind]||[]).find(item=>item.id===event.target.value),name=form.querySelector('[name=name]');
      if(item&&['기존 도구','새 스킬'].includes(name.value))name.value=item.name;
    }
  });
  document.addEventListener('pointerdown',event=>{if(scopePicker&&!event.target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();},true);
  document.addEventListener('focusin',event=>{if(scopePicker&&!event.target.closest?.('#ees-work-scope-popover, .ew-scope-pickers'))closeScopePicker();});
  document.addEventListener('scroll',positionNav,true);
  document.addEventListener('keydown',event=>{
    const trigger=event.target.closest?.('[data-action=scope_toggle]');
    if(trigger&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();openScopePicker(trigger.dataset.picker,event.key==='ArrowUp');return;}
    if(scopePicker){
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeScopePicker(true);return;}
      const popup=$('#ees-work-scope-popover');
      if(popup?.contains(event.target)&&['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const options=Array.from(popup.querySelectorAll('[data-action=scope_choose]')),index=options.indexOf(event.target),next=event.key==='Home'?0:event.key==='End'?options.length-1:(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;options[next]?.focus();return;}
    }
    if(event.key==='Escape'&&navOpen){navOpen=false;renderNavigator();sidebar();}
  });
  window.addEventListener('ees-work-changed',async event=>{const detail=event.detail||{};if(detail.chat_id!==undefined&&detail.chat_id!==chatId())return;const at=generation;await refresh();if(at===generation&&detail.open_requested)openPanel();});
  window.addEventListener('popstate',schedule);window.navigation?.addEventListener('navigatesuccess',schedule);
  window.addEventListener('storage',schedule);window.addEventListener('resize',()=>{positionNav();sizePanel();});
  const observer=new MutationObserver(schedule);observer.observe(document.documentElement,{childList:true,subtree:true});
  window.__eesNativeWork= true;
  window.__eesNativeWorkV1={ensureChat,beginChatCreation,finishChatCreation,refresh,open:openPanel,display:async(id,options)=>{
    if(typeof id!=='string'||id!==chatId()||!available()||!state||!options||typeof options!=='object'||Array.isArray(options))return {ok:false};
    if(Object.keys(options).some(key=>!['panel_open','navigator_open','pinned','category','system','site_id','process_id','case_id','history_open','history_case_id','workspace'].includes(key)))return {ok:false};
    if(['panel_open','navigator_open','pinned','workspace','history_open'].some(key=>key in options&&typeof options[key]!=='boolean'))return {ok:false};
    if('category' in options&&!Object.hasOwn(categories,options.category))return {ok:false};
    if('system' in options&&!state.catalog.systems.includes(options.system))return {ok:false};
    if('site_id' in options&&!state.catalog.sites[options.site_id])return {ok:false};
    if('process_id' in options&&state.catalog.nodes[options.process_id]?.type!=='p')return {ok:false};
    if(options.workspace){if(!state.can_manage)return {ok:false};navigate('/workspace/models?ees=workflow');return {ok:true};}
    if(options.history_case_id)return showHistory(options.history_case_id);
    if(options.case_id){const c=state.cases.find(c=>c.id===options.case_id);if(!c)return {ok:false};browsingSite=c.site.id;browsingSystem=c.system;return openCase(c);}
    if('category' in options)category=options.category;
    if(options.site_id||options.system){return switchScope(options.site_id || browsingSite,options.system || browsingSystem,options.process_id || '');}
    if(options.process_id)await selectWork(options.process_id);
    if('navigator_open' in options)navOpen=options.navigator_open;
    if('history_open' in options){resetHistory();runView=options.history_open?'history':'current';renderPanel();openPanel();}
    renderNavigator();
    if(options.panel_open===true){browseActive=true;openPanel();}
    else if(options.panel_open===false)window.__eesWorkPanelV1?.close(id);
    return {ok:true};
  }};

  schedule();
})();
