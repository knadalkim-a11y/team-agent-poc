/* Native EES workflow: existing sidebar, real chat and shared work panel. */
(() => {
  'use strict';
  if (window.__eesNativeWork) return;
  const $ = (s, p = document) => p.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const categories = {setup:'셋업',ops:'운영',incident:'장애대응'};
  const levels = {p:'프로세스',t:'태스크',j:'잡'};
  const statuses = {ready:'준비',pending:'대기',running:'실행 중',success:'완료',completed:'완료',passed:'완료',failed:'실패',blocked:'선행 작업 필요',skipped:'적용 제외',draft:'초안',review:'검토 필요'};
  let state = null, generation = 0, request = 0, busy = false, scheduled = false;
  let lastRoute = '', identity = '', pendingId = '', pendingSubmitted = false;
  let category = 'setup', browsingSystem = 'EMS', navOpen = false, pinned = false, newCase = false, activeRegistration = null;
  let host = null, divider = null, panelOpen = false, width = 520, panelInfo = null;
  let designer = null, hiddenWorkspace = [], editor = null, editorId = '', editorRevision = 0, editorDirty = false;
  let editorTab = 'workflow', errorMessage = '', drag = null;
  let createSelection={};
  const editorCollapsed=new Set();
  const expanded = new Set(['setup-p','prep-t','infra-t','install-t','interface-t']);
  const token = () => {try {return localStorage.getItem('token') || '';} catch (_) {return '';}};
  const chatId = () => {const m = location.pathname.match(/^\/c\/([^/]+)\/?$/); return m ? decodeURIComponent(m[1]) : '';};
  const chatRoute = () => location.pathname === '/' || /^\/c\/[^/]+\/?$/.test(location.pathname);
  const adminRoute = () => location.pathname.startsWith('/workspace') && new URLSearchParams(location.search).get('ees') === 'workflow';
  const available = () => !/^\/(auth|logout)(\/|$)/.test(location.pathname) && Boolean($('#sidebar-new-chat-button'));
  const currentCase = () => state?.case;
  const caseMatchesRoute=()=>Boolean(currentCase()&&chatRoute()&&(currentCase().chat_id || '')===chatId());
  const definition = () => currentCase()?.definition || state?.catalog;
  const node = id => definition()?.nodes?.[id];
  const status = id => currentCase()?.node_states?.[id] || {};
  const badge = value => `<span class="ew-badge" data-status="${esc(value)}">${esc(statuses[value] || value || '대기')}</span>`;
  const button = (label, action, attrs = '') => `<button type="button" data-action="${action}" ${attrs}>${esc(label)}</button>`;
  const nameOf = id => node(id)?.name || id;
  const lineage = (id, data = definition()) => {const result = [], seen = new Set(); while (id && data?.nodes[id] && !seen.has(id)) {seen.add(id); result.unshift(data.nodes[id]); id = data.nodes[id].parent;} return result;};
  const alertHTML = () => errorMessage ? `<p class="ew-error" role="alert">${esc(errorMessage)}</p>` : '';

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
    if(state.case&&state.case.id!==previousCase){browsingSystem=state.case.system;category=state.case.definition.nodes[state.case.process_id]?.category || 'setup';}
    if (!editorDirty && state.can_manage) {editor = clone(state.draft || state.catalog); editorRevision = state.draft_revision || 0;}
    if (!editorId || !editor?.nodes?.[editorId]) editorId = Object.keys(editor?.nodes || {})[0] || '';
    if(currentCase()){lineage(currentCase().selected_id).forEach(item=>expanded.add(item.id));}
    if (currentCase()?.chat_id) pendingId = '';
    render();
  }
  async function refresh() {
    if (!available()) return;
    const at = generation, serial = ++request, id = chatId(), auth = token(), route = location.pathname + location.search;
    const query = new URLSearchParams({chat_id:id}); if (!id && pendingId) query.set('case_id', pendingId);
    try {const result = await api('state?' + query); if (at !== generation || serial !== request || auth !== token() || route !== location.pathname + location.search || !available()) return; errorMessage = ''; accept(result);}
    catch (error) {if (at !== generation || serial !== request) return; errorMessage = error.message; render();}
  }
  async function action(actionName, payload = {}, nodeId = '', override = {}) {
    if (busy || !state) return null;
    busy = true; errorMessage = ''; setBusy();
    const at = generation, cid = currentCase()?.id || '', auth = token(), route = location.pathname + location.search;
    const isAdmin = ['save_draft','validate_draft','publish'].includes(actionName);
    const body = {action:actionName,chat_id:chatId(),case_id:cid,node_id:nodeId,payload,expected_revision:isAdmin ? editorRevision : (currentCase()?.revision || 0),...override};
    try {
      const result = await api('action', body);
      if (at !== generation || auth !== token() || route !== location.pathname + location.search || !available()) return null;
      if (isAdmin && actionName !== 'validate_draft') editorDirty = false;
      if (actionName === 'create' && !result.case?.chat_id) pendingId = result.case?.id || '';
      accept(result); return result;
    } catch (error) {if (at === generation) {errorMessage = error.message; render();} return null;}
    finally {busy = false; setBusy();}
  }
  function setBusy() {document.querySelectorAll('[data-ees-work] button[data-mutation]').forEach(el => {el.disabled = busy || el.dataset.unavailable === 'true';}); if (host) host.setAttribute('aria-busy',String(busy));}

  function sidebar() {
    const anchor = $('#sidebar-search-button'); if (!anchor) return;
    let entry = $('#ees-work-entry');
    if (!entry) {
      entry = document.createElement('div'); entry.id = 'ees-work-entry'; entry.dataset.eesWork = '';
      entry.innerHTML = `<p class="ew-caption">업무</p>${Object.entries(categories).map(([id,name]) => `<button type="button" data-work-category="${id}" aria-expanded="false"><span>${name}</span><span aria-hidden="true">›</span></button>`).join('')}`;
      anchor.parentElement.insertAdjacentElement('afterend', entry);
    }
    entry.querySelectorAll('[data-work-category]').forEach(el => {el.setAttribute('aria-expanded',String(navOpen && el.dataset.workCategory === category));});
    let link = $('#ees-work-admin-link');
    if (state?.can_manage && !link) {
      link = document.createElement('a'); link.id = 'ees-work-admin-link'; link.dataset.eesWork = ''; link.href = '/workspace/models?ees=workflow'; link.textContent = '업무 절차';
      const workspace = $('#sidebar-workspace-button');
      (workspace?.parentElement || entry).insertAdjacentElement('afterend', link);
    } else if (!state?.can_manage) link?.remove();
  }
  function treeHTML(data, ids, depth = 0, editing = false) {
    return (ids || []).map(id => {
      const n = data.nodes[id]; if (!n || depth > 3) return '';
      const children = n.children || [], open = editing ? !editorCollapsed.has(id) : expanded.has(id);
      const active = editing ? editorId === id : !newCase && currentCase()?.selected_id === id;
      const itemStatus = editing || data!==currentCase()?.definition || newCase ? null : status(id).status;
      return `<div class="ew-tree-row" style="--depth:${depth}">${children.length ? button(open?'−':'+','expand',`data-node-id="${esc(id)}" class="ew-expand" aria-label="${esc(n.name)} ${open?'접기':'펼치기'}" aria-expanded="${open}"`) : '<span class="ew-expand"></span>'}<button type="button" data-action="${editing?'edit_node':'select'}" data-node-id="${esc(id)}" aria-current="${active?'step':'false'}"><span class="ew-type">${esc(n.type.toUpperCase())}</span><span>${esc(n.name)}</span>${itemStatus ? `<span class="ew-dot" data-status="${esc(itemStatus)}" title="${esc(statuses[itemStatus] || itemStatus)}"></span>` : ''}</button></div>${children.length && open ? treeHTML(data, children, depth + 1, editing) : ''}`;
    }).join('');
  }
  function renderNavigator() {
    const existingForm=$('#ees-work-case-create');if(existingForm)createSelection=Object.fromEntries(new FormData(existingForm));
    let nav = $('#ees-work-navigator');
    if (!navOpen || !available()) {nav?.remove(); return;}
    if (!nav) {nav = document.createElement('aside'); nav.id = 'ees-work-navigator'; nav.dataset.eesWork = ''; nav.setAttribute('aria-label','업무 탐색'); document.body.append(nav);}
    const c=currentCase(),showCurrent=c&&!newCase&&c.system===browsingSystem&&c.definition.nodes[c.process_id]?.category===category;
    const data=showCurrent?c.definition:state?.catalog;
    const cases = (state?.cases || []).filter(item => (state.catalog?.nodes[item.process_id]?.category || 'setup') === category && item.system===browsingSystem);
    nav.innerHTML = `<header><div><p class="ew-caption">업무 탐색</p><h2>${categories[category]}</h2></div><div class="ew-actions">${button(pinned?'고정 해제':'고정','pin',`aria-pressed="${pinned}"`)}${button('닫기','nav_close','aria-label="업무 탐색 닫기"')}</div></header>${alertHTML()}<div class="ew-scroll"><label class="ew-system-filter">시스템<select id="ees-work-system-filter">${(state?.catalog?.systems || ['EMS','APC','FDC','EGIS','EPT']).map(system=>`<option ${system===browsingSystem?'selected':''}>${esc(system)}</option>`).join('')}</select></label><div class="ew-heading"><h3>진행 중인 업무</h3>${button('새 진행 건','new_case')}</div><div class="ew-case-list">${cases.map(item => `<button type="button" data-action="open_case" data-case-id="${esc(item.id)}" aria-pressed="${c?.id===item.id}"><strong>${esc(item.site?.name || item.site?.factory || item.site?.id)} · ${esc(item.system)}</strong><span>${esc(state.catalog?.nodes[item.process_id]?.name || '업무 진행')} · v${esc(item.version)}</span></button>`).join('') || '<p class="ew-muted">진행 중인 업무가 없습니다.</p>'}</div>${!showCurrent ? createForm() : `<section class="ew-scope"><span>${esc(c.site?.name || c.site?.factory)} · ${esc(c.system)}</span><small>적용 절차 v${esc(c.version)}</small></section>`}${data ? `<h3 class="ew-tree-heading">${showCurrent ? '현재 업무 단계' : '사용 가능한 절차'}</h3><div id="ees-work-tree">${treeHTML(data,showCurrent ? [c.process_id] : (data.roots?.[category] || []).filter(id=>!data.nodes[id]?.systems||data.nodes[id].systems.includes(browsingSystem)))}</div>` : '<p class="ew-muted">업무 목록을 불러오는 중입니다.</p>'}</div>`;
    positionNav();
  }
  function createForm() {
    const data = state?.catalog; if (!data) return '';
    const selectedSystem = browsingSystem;
    return `<form id="ees-work-case-create" class="ew-card"><h3>업무 시작</h3><label>국가 · 공장<select id="ees-work-site" name="site_id">${Object.values(data.sites || {}).map(s => `<option value="${esc(s.id)}" ${createSelection.site_id===s.id?'selected':''}>${esc(s.country)} · ${esc(s.name || s.factory)}${s.line ? ' · '+esc(s.line) : ''}</option>`).join('')}</select></label><label>시스템<select id="ees-work-system" name="system">${(data.systems || ['EMS','APC','FDC','EGIS','EPT']).map(s => `<option ${s===selectedSystem?'selected':''}>${esc(s)}</option>`).join('')}</select></label><label>프로세스<select id="ees-work-process" name="process_id">${(data.roots?.[category] || []).filter(id=>!data.nodes[id]?.systems||data.nodes[id].systems.includes(selectedSystem)).map(id => `<option value="${esc(id)}" ${createSelection.process_id===id?'selected':''}>${esc(data.nodes[id]?.name)}</option>`).join('')}</select></label><p class="ew-muted">공장 조건과 현재 게시된 절차로 새 진행 건을 만듭니다. 공통 예시 절차는 시스템 전문가의 조정이 필요합니다.</p><button id="ees-work-case-start" type="submit" class="ew-primary" data-mutation>${currentCase()?.chat_id?'새 대화에서 시작':'이 대화에서 시작'}</button></form>`;
  }
  function positionNav() {
    const nav = $('#ees-work-navigator'); if (!nav) return;
    const sidebar = $('#sidebar-search-button')?.closest('#sidebar');
    const boundary = sidebar?.getBoundingClientRect().right || 0;
    const left = innerWidth < 760 ? 0 : Math.min(boundary, innerWidth - 330);
    const layout=chatLayout(),docked=pinned&&innerWidth>=1400&&Boolean(layout);
    nav.classList.toggle('ew-docked',docked);nav.dataset.pinned=String(pinned);
    if(docked){if(nav.parentElement!==layout.row)layout.row.insertBefore(nav,layout.column);nav.style.left='auto';}
    else{if(nav.parentElement!==document.body)document.body.append(nav);nav.style.left=left+'px';}
  }

  function chatLayout() {
    const anchor = $('#chat-container #chat-pane'), column = anchor?.parentElement, row = column?.parentElement;
    return row && column && chatRoute() ? {anchor,column,row} : null;
  }
  function renderContext() {
    const c = currentCase(), layout = chatLayout(); let strip = $('#ees-work-context');
    if (!c || !layout || !caseMatchesRoute()) {strip?.remove(); return;}
    if (!strip) {strip = document.createElement('div'); strip.id = 'ees-work-context'; strip.dataset.eesWork = ''; layout.column.insertBefore(strip,layout.anchor);}
    strip.innerHTML = `<button type="button" data-action="nav_open" title="업무 탐색"><span class="ew-context-dot"></span><strong>${esc(c.site?.name || c.site?.factory)} · ${esc(c.system)}</strong><span>${esc(lineage(c.selected_id).map(n=>n.name).join(' › '))}</span></button>${button('업무 패널','panel_open','id="ees-work-context-open"')}<small>${c.chat_id?'이 대화에 연결됨':'첫 메시지를 보내면 이 대화에 연결됩니다'}</small>`;
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
  function openHost() {const layout = chatLayout(); if (!layout || !currentCase()) return; ensureHost(); panelOpen = true; styledColumn=layout.column;styledColumn.classList.add('ees-work-chat-column');layout.row.append(divider,host); sizePanel();}
  function closeHost() {panelOpen = false; host?.remove(); divider?.remove();styledColumn?.classList.remove('ees-work-chat-column');styledColumn=null;}
  function registerPanel() {
    const manager = window.__eesWorkPanelV1, id = chatId();
    if (!caseMatchesRoute() || !manager) return;
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
  function openPanel() {if(!caseMatchesRoute())return;registerPanel(); window.__eesWorkPanelV1?.select(chatId(),'workflow',{open:true,focus:false});}
  function nextJob(n) {
    const candidates=n.type==='j'?[n]:(n.children||[]).flatMap(id=>{const child=node(id);return child?.type==='j'?[child]:(child?.children||[]).map(node);});
    return candidates.find(item=>item&&status(item.id).applicable!==false&&status(item.id).status!=='passed'&&!(status(item.id).missing||[]).length);
  }
  function renderPanel() {
    if (!caseMatchesRoute()) {closeHost(); return;} ensureHost();
    const c = currentCase(), n = node(c.selected_id) || node(c.process_id), ns = status(n.id);
    const progress = ns.progress || {done:0,total:0},next=nextJob(n);
    $('#ees-work-content',host).innerHTML = `${alertHTML()}<div class="ew-heading"><span class="ew-caption">${levels[n.type]} · ${esc(c.system)}</span>${badge(ns.status)}</div><h2 class="ew-title">${esc(n.name)}</h2><p class="ew-muted">${esc(n.description || '')}</p><p class="ew-breadcrumb">${esc(lineage(n.id).map(v=>v.name).join(' › '))}</p>${n.type==='j'?jobHTML(n,c,ns):`<section class="ew-card"><div class="ew-heading"><h3>진행 상황</h3><strong>${progress.done} / ${progress.total}</strong></div><progress max="${Math.max(1,progress.total)}" value="${progress.done}"></progress><p class="ew-muted">${esc(c.site?.name || c.site?.factory)} · 절차 v${c.version}</p>${next?button('다음 작업: '+next.name,'select',`data-node-id="${esc(next.id)}"`):''}</section>${missingHTML(ns)}<section><h3>${n.type==='p'?'단계별 진행':'하위 작업'}</h3><div class="ew-children">${(n.children || []).map(id=>{const child=node(id),s=status(id);return `<button type="button" data-action="select" data-node-id="${esc(id)}"><span class="ew-type">${esc(child?.type?.toUpperCase())}</span><span><strong>${esc(child?.name)}</strong><small>${esc(child?.description || '')}</small></span>${badge(s.status)}</button>`;}).join('')}</div></section><button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation>준비된 하위 작업 실행</button><p class="ew-muted">수동 확인·초안 검토가 필요한 작업에서는 멈춥니다.</p>`}<details class="ew-instructions"><summary>적용 지침과 스킬</summary>${(c.context?.skills || []).map(skill=>`<div><strong>${esc(skill.name)}</strong><p>${esc(skill.body || skill.message || '')}</p></div>`).join('')}${lineage(n.id).map(v => `<div><strong>${esc(v.name)}</strong><p>${esc(v.instructions || '별도 지침 없음')}</p>${(v.skills || []).map(id=>`<span class="ew-badge">${esc(c.definition.skills?.[id]?.name || id)}</span>`).join('')}</div>`).join('')}</details><p class="ew-footnote">연결 점검은 합성 시연 결과입니다. 실제 업무 시스템은 호출하지 않습니다. 가운데 AI 대화는 기존 모델을 사용합니다.</p>`;
    renderTabs(); registerPanel(); setBusy();
  }
  function missingHTML(ns) {return (ns.missing || []).length ? `<p class="ew-notice">먼저 완료할 작업: ${ns.missing.map(id=>esc(nameOf(id))).join(', ')}</p>` : '';}
  function jobHTML(n,c,ns) {
    const job = c.jobs[n.id] || {}, inputs = {db:c.site.db,ap:c.site.ap,site:[c.site.country,c.site.name,c.site.line].join(' · '),interface:c.site.interface?c.system+' · '+c.site.name+' 시스템 간 연계 · 예시':'',...(job.inputs || {})};
    const fields = Array.from(new Set(Object.values(n.bindings || {}).filter(v=>['db','ap','site','interface'].includes(v))));
    const labels = {db:'DB 대상',ap:'AP 대상',site:'공장 확인',interface:'인터페이스 대상'};
    const checks = job.checks || [], history = job.history || [];
    return `${missingHTML(ns)}${!ns.applicable ? '<p class="ew-notice">이 공장 조건에서는 적용하지 않는 작업입니다.</p>':''}${fields.length?`<form id="ees-work-inputs" class="ew-card"><h3>점검 입력</h3>${fields.map(key=>`<label>${labels[key]}<input name="${key}" value="${esc(inputs[key] || '')}" autocomplete="off" placeholder="시연용 대상 입력"></label>`).join('')}<button id="ees-work-inputs-save" type="submit" data-mutation>입력값 저장</button><p class="ew-muted">저장한 입력값은 이 대화의 AI도 참고합니다. 비밀번호·접속 키는 입력하지 마세요.</p></form>`:''}<section class="ew-card"><h3>${n.mode==='manual'?'확인할 내용':n.mode==='draft'?'검토할 초안':'실행 순서와 점검 기준'}</h3><p>${esc(n.rule || n.description)}</p>${(n.tools || []).map((id,i)=>`<div class="ew-tool"><span class="ew-index">${i+1}</span><div><strong>${esc(c.definition.tools?.[id]?.name || id)}</strong><small>${esc(c.definition.tools?.[id]?.description || c.definition.tools?.[id]?.purpose || '')}</small></div></div>`).join('')}${n.mode==='draft'?`<form id="ees-work-document"><label>작업 초안<textarea name="document" rows="6" placeholder="가운데 AI에게 초안을 요청하거나 직접 작성하세요.">${esc(job.document || '')}</textarea></label><button type="submit" data-mutation>초안 저장</button></form>`:''}<button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation ${ns.applicable===false?'disabled data-unavailable="true"':''}>${n.mode==='manual'?'확인 완료':n.mode==='draft'?'검토 완료':job.attempt?'다시 점검':'점검 실행'}</button></section>${checks.length?`<section class="ew-card"><div class="ew-heading"><h3>점검 결과</h3><span>${esc(job.attempt || 1)}차 실행</span></div>${checks.map(check=>`<div class="ew-check"><div class="ew-heading"><strong>${esc(check.name || c.definition.tools?.[check.id || check.tool_id || check.tool]?.name || check.id || check.tool_id || check.tool)}</strong>${badge(check.status)}</div><p>${esc(check.message || check.detail || check.summary || '')}</p>${check.evidence?`<pre>${esc(typeof check.evidence==='string'?check.evidence:JSON.stringify(check.evidence,null,2))}</pre>`:''}</div>`).join('')}</section>`:''}${history.length?`<details class="ew-history"><summary>이전 실행 기록 (${history.length})</summary>${history.map((run,i)=>`<section class="ew-card"><strong>${esc(run.attempt || i+1)}차 실행</strong> ${badge(run.status)}<p>${esc(run.at || run.completed_at || '')}</p>${(run.checks || []).map(check=>`<p>${esc(check.name || check.id || check.tool_id || check.tool)} · ${esc(statuses[check.status] || check.status)} · ${esc(check.message || check.detail || '')}</p>`).join('')}</section>`).join('')}</details>`:''}`;
  }

  function hideWorkspaceContent() {
    const container=$('#workspace-container');if(!container||!designer||!state?.can_manage||!adminRoute())return;
    const controls=container.parentElement.querySelector('nav .ml-auto.shrink-0');
    [...container.children,...(controls?[controls]:[])].filter(element=>element!==designer).forEach(element=>{
      if(!hiddenWorkspace.some(([known])=>known===element))hiddenWorkspace.push([element,element.hidden]);
      if(!element.hidden)element.hidden=true;element.classList.add('ees-work-native-hidden');
    });
  }
  function restoreWorkspace() {
    designer?.remove(); designer = null;
    hiddenWorkspace.forEach(([element,previous])=>{element.hidden=previous;element.classList.remove('ees-work-native-hidden');}); hiddenWorkspace=[];
    $('#ees-work-workspace-tab')?.remove();
  }
  function workspaceTab() {
    if (!state?.can_manage) return;
    const container = $('#workspace-container'), original = container?.parentElement.querySelector('nav a[href="/workspace/models"]');
    if (!original || $('#ees-work-workspace-tab')) return;
    const link = document.createElement('a'); link.id='ees-work-workspace-tab'; link.href='/workspace/models?ees=workflow'; link.textContent='업무 절차'; link.className=original.className; link.setAttribute('aria-current',adminRoute()?'page':'false'); original.parentElement.append(link);
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

  function navigate(url) {const link=document.createElement('a');link.href=url;link.hidden=true;document.body.append(link);link.click();link.remove();}
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
    if(binding)return binding;
    const wanted=pendingId,c=currentCase();
    if(c?.chat_id&&c.id===wanted)return {ok:true,case_id:wanted};
    const at=generation,auth=token();
    binding=(async()=>{
      try{
        const candidate=c?.id===wanted?c:(await api('state?'+new URLSearchParams({case_id:wanted}))).case;
        if(chatId()!==id||auth!==token()||!available()||pendingId!==wanted||!candidate)return {ok:false};
        const result=await api('action',{action:'bind',chat_id:id,case_id:wanted,node_id:'',payload:{},expected_revision:candidate.revision});
        if(pendingId===wanted){pendingId='';pendingSubmitted=false;}
        if(available()&&auth===token()&&chatId()===id){accept(result);openPanel();}
        return {ok:true,case_id:result.case?.id || wanted};
      }catch(error){if(at===generation){errorMessage=error.message;render();}return {ok:false};}
      finally{binding=null;}
    })();return binding;
  }
  async function handleClick(event) {
    const categoryButton=event.target.closest('[data-work-category]');
    if(categoryButton?.closest('#ees-work-entry')){event.stopPropagation();category=categoryButton.dataset.workCategory;navOpen=true;newCase=currentCase()&&definition().nodes[currentCase().process_id]?.category!==category;renderNavigator();sidebar();return;}
    const target=event.target.closest('[data-action]');if(!target?.closest('[data-ees-work]'))return;
    event.stopPropagation();const a=target.dataset.action;
    if(a==='nav_close'){navOpen=false;renderNavigator();sidebar();}
    else if(a==='nav_open'){navOpen=true;renderNavigator();sidebar();}
    else if(a==='pin'){pinned=!pinned;renderNavigator();}
    else if(a==='new_case'){newCase=!newCase;renderNavigator();}
    else if(a==='expand'){const id=target.dataset.nodeId;if(target.closest('#ees-work-designer')){captureEditor();editorCollapsed.has(id)?editorCollapsed.delete(id):editorCollapsed.add(id);renderDesigner();}else{expanded.has(id)?expanded.delete(id):expanded.add(id);renderNavigator();}}
    else if(a==='panel_open')openPanel();
    else if(a==='panel_close'){window.__eesWorkPanelV1?.close(chatId());}
    else if(a==='panel_tab'){window.__eesWorkPanelV1?.select(chatId(),target.dataset.screen,{open:true});}
    else if(a==='open_case'){
      const c=state.cases.find(item=>item.id===target.dataset.caseId);if(!c)return;
      if(c.chat_id&&c.chat_id!==chatId()){navigate('/c/'+encodeURIComponent(c.chat_id));return;}
      if(!c.chat_id&&(chatId()||!chatRoute())){pendingId=c.id;navigate('/');return;}
      pendingId=c.chat_id?'':c.id;newCase=false;const at=generation;await refresh();if(at===generation)openPanel();
    }else if(a==='select'){
      if(!currentCase()||newCase){newCase=true;renderNavigator();const select=$('#ees-work-process');const p=lineage(target.dataset.nodeId,state.catalog)[0];if(select&&p)select.value=p.id;return;}
      if(await action('select',{},target.dataset.nodeId)){openPanel();if(!pinned){navOpen=false;renderNavigator();sidebar();}}
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
    if(form.id==='ees-work-case-create'){
      const separate=Boolean(currentCase()?.chat_id),result=await action('create',values,'',{case_id:'',chat_id:separate?'':chatId(),expected_revision:0});
      if(result){newCase=false;navOpen=true;if(separate||!chatRoute()){pendingId=result.case.id;navigate('/');}else{renderNavigator();openPanel();}}
    }else if(form.id==='ees-work-inputs')await action('update_inputs',{inputs:values},currentCase().selected_id);
    else if(form.id==='ees-work-document')await action('run',{document:values.document},currentCase().selected_id);
    else if(form.id==='ees-work-node-form'||form.classList.contains('ew-asset-form')){captureEditor();renderDesigner();}
  }
  function render(){sidebar();renderNavigator();renderContext();renderPanel();renderDesigner();}
  function cleanup() {
    generation++;request++;state=null;pendingId='';pendingSubmitted=false;editor=null;editorDirty=false;errorMessage='';navOpen=false;
    if(activeRegistration!==null)window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;closeHost();
    ['ees-work-entry','ees-work-admin-link','ees-work-navigator','ees-work-context'].forEach(id=>document.getElementById(id)?.remove());restoreWorkspace();
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
      const previous=lastRoute;lastRoute=path;generation++;request++;
      if(activeRegistration!==null){window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;}closeHost();$('#ees-work-context')?.remove();
      if(!adminRoute())restoreWorkspace();else{navOpen=false;renderNavigator();sidebar();}
      if(pendingId&&pendingSubmitted&&previous==='/'&&chatId()){ensureChat(chatId());return;}
      state=null;refresh();return;
    }
    if(state){
      if(currentCase()&&chatRoute()){
        if(!$('#ees-work-context'))renderContext();
        registerPanel();
      }
      if(adminRoute()){if(!designer?.isConnected)renderDesigner();else hideWorkspaceContent();}
    }
    positionNav();
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(sync);}}
  function noteSubmit(event) {
    if(!pendingId||location.pathname!=='/')return;
    const composer=$('#chat-input');if(!composer)return;
    if((event.type==='submit'&&event.target.contains?.(composer))||(event.type==='click'&&event.target.closest?.('#send-message-button'))||(event.type==='keydown'&&composer.contains(event.target)&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing))pendingSubmitted=true;
  }
  document.addEventListener('click',handleClick,true);document.addEventListener('submit',handleSubmit,true);
  document.addEventListener('click',noteSubmit,true);document.addEventListener('submit',noteSubmit,true);document.addEventListener('keydown',noteSubmit,true);
  document.addEventListener('input',event=>{if(event.target.closest?.('#ees-work-designer'))editorDirty=true;});
  document.addEventListener('change',event=>{
    if(['ees-work-system-filter','ees-work-system'].includes(event.target.id)){
      browsingSystem=event.target.value;newCase=Boolean(currentCase()&&currentCase().system!==browsingSystem);renderNavigator();return;
    }
    const form=event.target.closest?.('.ew-asset-form');
    if(form&&event.target.name==='reference'){
      const item=(state.catalog['available_'+form.dataset.kind]||[]).find(item=>item.id===event.target.value),name=form.querySelector('[name=name]');
      if(item&&['기존 도구','새 스킬'].includes(name.value))name.value=item.name;
    }
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&navOpen&&!pinned){navOpen=false;renderNavigator();sidebar();}});
  window.addEventListener('ees-work-changed',async event=>{const detail=event.detail||{};if(detail.chat_id!==undefined&&detail.chat_id!==chatId())return;const at=generation;await refresh();if(at===generation&&detail.open_requested)openPanel();});
  window.addEventListener('popstate',schedule);window.navigation?.addEventListener('navigatesuccess',schedule);
  window.addEventListener('storage',schedule);window.addEventListener('resize',()=>{positionNav();sizePanel();});
  const observer=new MutationObserver(schedule);observer.observe(document.documentElement,{childList:true,subtree:true});
  window.__eesNativeWork= true;
  window.__eesNativeWorkV1={ensureChat,refresh,open:openPanel,display:async(id,options)=>{
    if(typeof id!=='string'||id!==chatId()||!available()||!options||typeof options!=='object'||Array.isArray(options))return {ok:false};
    if(Object.keys(options).some(key=>!['panel_open','navigator_open','pinned','category','system','workspace'].includes(key)))return {ok:false};
    if(['panel_open','navigator_open','pinned','workspace'].some(key=>key in options&&typeof options[key]!=='boolean'))return {ok:false};
    if('category' in options&&!Object.hasOwn(categories,options.category))return {ok:false};
    if('system' in options&&!(state?.catalog?.systems || []).includes(options.system))return {ok:false};
    if(options.workspace){if(!state?.can_manage)return {ok:false};navigate('/workspace/models?ees=workflow');return {ok:true};}
    if('category' in options)category=options.category;
    if('system' in options){browsingSystem=options.system;newCase=Boolean(currentCase()&&currentCase().system!==browsingSystem);}
    if('navigator_open' in options)navOpen=options.navigator_open;
    if('pinned' in options)pinned=options.pinned;
    renderNavigator();sidebar();
    if(options.panel_open===true){if(!currentCase())return {ok:false};openPanel();}
    else if(options.panel_open===false)window.__eesWorkPanelV1?.close(id);
    return {ok:true};
  }};
  schedule();
})();
