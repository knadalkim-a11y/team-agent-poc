/* Pure rendering helpers shared by the native workflow view and designer. */
const workUI = (() => {
  const $ = (s, p = document) => p.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const categories = {setup:'셋업',ops:'운영',incident:'장애대응'};
  const levels = {p:'프로세스',t:'태스크',j:'잡'};
  const statuses = {unstarted:'시작 전',ready:'준비',pending:'대기',in_progress:'진행 중',running:'실행 중',success:'완료',completed:'완료',passed:'완료',failed:'실패',blocked:'선행 작업 대기',skipped:'적용 제외',draft:'초안',review:'검토 필요'};
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

/* Owns display state and DOM; server snapshots are copied and never mutated. */
function createWorkView({callbacks}) {
  const {$, esc, clone, categories, levels, statuses, badge, button, finished, siteLabel} = workUI;
  let snapshot = {}, state = null, category = 'setup', browsingSystem = 'EMS', browsingSite = '', browseNodeId = '', runView = 'current', historyCase = null, errorMessage = '', busy = false;
  let serverSource=null,historySource=null;
  let navOpen = true, scopePicker = '', host = null, divider = null, panelOpen = false, width = 520, panelInfo = null, drag = null, styledColumn = null;
  // Expansion belongs to the factory scope and the retained case version.
  const treeExpansions = new Map();
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
  function readSnapshot(value) {
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
  function closeHost() {panelOpen = false; drag=null;if(divider)delete divider.dataset.pointer;host?.remove(); divider?.remove();styledColumn?.classList.remove('ees-work-chat-column');styledColumn=null;}
  function renderTabs() {
    if (!host) return; const tabs = $('#ees-work-tabs',host), screens = panelInfo?.screens || window.__eesWorkPanelV1?.list?.(chatId()) || [{key:'workflow',label:'업무 진행'}];
    const html = screens.map(screen => button(screen.label,'panel_tab',`data-screen="${esc(screen.key)}" aria-selected="${screen.key==='workflow'}"`)).join('');
    if (tabs.innerHTML !== html) tabs.innerHTML = html;
  }
  function openPanel() {if(!chatRoute()||!state||!selectedId())return;callbacks.registerPanel(); window.__eesWorkPanelV1?.select(chatId(),'workflow',{open:true,focus:false});}
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
  function renderPanel() {
    if (!chatRoute() || !state || !selectedId()) {closeHost(); return;} ensureHost();
    if(runView==='history' || !selectedCase()) {$('#ees-work-content',host).innerHTML=runTabs()+alertHTML()+(runView==='history'?historyHTML():previewHTML());renderTabs();callbacks.registerPanel();setBusy();return;}
    const c = currentCase(), n = node(c.selected_id) || node(c.process_id), ns = status(n.id);
    const progress = ns.progress || {done:0,total:0},next=nextJob(n);
    $('#ees-work-content',host).innerHTML = `${runTabs()}${alertHTML()}<div class="ew-heading"><span class="ew-caption">${levels[n.type]} · ${esc(c.system)}</span>${badge(ns.status)}</div><h2 class="ew-title">${esc(n.name)}</h2><p class="ew-muted">${esc(n.description || '')}</p><p class="ew-breadcrumb">${esc(lineage(n.id).map(v=>v.name).join(' › '))}</p>${n.type==='j'?jobHTML(n,c,ns):`<section class="ew-card"><div class="ew-heading"><h3>진행 상황</h3><strong>${progress.done} / ${progress.total}</strong></div><progress max="${Math.max(1,progress.total)}" value="${progress.done}"></progress><p class="ew-muted">${esc(c.site?.name || c.site?.factory)} · 절차 v${c.version}</p>${next?button('다음 작업: '+next.name,'select',`data-node-id="${esc(next.id)}"`):''}</section>${missingHTML(ns)}<section><h3>${n.type==='p'?'단계별 진행':'하위 작업'}</h3><div class="ew-children">${(n.children || []).map(id=>{const child=node(id),s=status(id);return `<button type="button" data-action="select" data-node-id="${esc(id)}"><span class="ew-type">${esc(child?.type?.toUpperCase())}</span><span><strong>${esc(child?.name)}</strong><small>${esc(child?.description || '')}</small></span>${badge(s.status)}</button>`;}).join('')}</div></section><button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation>준비된 하위 작업 실행</button><p class="ew-muted">수동 확인·초안 검토가 필요한 작업에서는 멈춥니다.</p>`}<details class="ew-instructions"><summary>적용 지침과 스킬</summary>${(c.context?.skills || []).map(skill=>`<div><strong>${esc(skill.name)}</strong><p>${esc(skill.body || skill.message || '')}</p></div>`).join('')}${lineage(n.id).map(v => `<div><strong>${esc(v.name)}</strong><p>${esc(v.instructions || '별도 지침 없음')}</p>${(v.skills || []).map(id=>`<span class="ew-badge">${esc(c.definition.skills?.[id]?.name || id)}</span>`).join('')}</div>`).join('')}</details><p class="ew-footnote">연결 점검은 합성 시연 결과입니다. 실제 업무 시스템은 호출하지 않습니다. 가운데 AI 대화는 기존 모델을 사용합니다.</p>`;
    if(finished(c)){$('#ees-work-content',host).innerHTML=runTabs()+alertHTML()+`<p class="ew-muted">${esc(siteLabel(c.site))} · ${esc(c.system)} · ${esc(runLabel(c))}</p><p class="ew-notice">이 실행은 완료됐습니다. 새 실행을 시작해도 기존 기록은 유지됩니다.</p>`+readOnlyNode(c,n)+(n.type==='p'?button('새 실행 시작','start_case','class="ew-primary" data-mutation'):button('프로세스 완료 보기','select',`data-node-id="${esc(c.process_id)}"`));}
    renderTabs(); callbacks.registerPanel(); setBusy();
  }
  function missingHTML(ns) {return (ns.missing || []).length ? `<p class="ew-notice">먼저 완료할 작업: ${ns.missing.map(id=>esc(nameOf(id))).join(', ')}</p>` : '';}
  function jobHTML(n,c,ns) {
    const job = c.jobs[n.id] || {}, inputs = {db:c.site.db,ap:c.site.ap,site:[c.site.country,c.site.name,c.site.line].join(' · '),interface:c.site.interface?c.system+' · '+c.site.name+' 시스템 간 연계 · 예시':'',...(job.inputs || {})};
    const fields = Array.from(new Set(Object.values(n.bindings || {}).filter(v=>['db','ap','site','interface'].includes(v))));
    const labels = {db:'DB 대상',ap:'AP 대상',site:'공장 확인',interface:'인터페이스 대상'};
    const checks = job.checks || [], history = job.history || [];
    return `${missingHTML(ns)}${!ns.applicable ? '<p class="ew-notice">이 공장 조건에서는 적용하지 않는 작업입니다.</p>':''}${fields.length?`<form id="ees-work-inputs" class="ew-card"><h3>점검 입력</h3>${fields.map(key=>`<label>${labels[key]}<input name="${key}" value="${esc(inputs[key] || '')}" autocomplete="off" placeholder="시연용 대상 입력"></label>`).join('')}<button id="ees-work-inputs-save" type="submit" data-mutation>입력값 저장</button><p class="ew-muted">저장한 입력값은 이 대화의 AI도 참고합니다. 비밀번호·접속 키는 입력하지 마세요.</p></form>`:''}<section class="ew-card"><h3>${n.mode==='manual'?'확인할 내용':n.mode==='draft'?'검토할 초안':'실행 순서와 점검 기준'}</h3><p>${esc(n.rule || n.description)}</p>${(n.tools || []).map((id,i)=>`<div class="ew-tool"><span class="ew-index">${i+1}</span><div><strong>${esc(c.definition.tools?.[id]?.name || id)}</strong><small>${esc(c.definition.tools?.[id]?.description || c.definition.tools?.[id]?.purpose || '')}</small></div></div>`).join('')}${n.mode==='draft'?`<form id="ees-work-document"><label>작업 초안<textarea name="document" rows="6" placeholder="가운데 AI에게 초안을 요청하거나 직접 작성하세요.">${esc(job.document || '')}</textarea></label><button type="submit" data-mutation>초안 저장</button></form>`:''}<button type="button" id="ees-work-run" data-action="run" data-node-id="${esc(n.id)}" class="ew-primary" data-mutation ${ns.applicable===false||(ns.missing || []).length?'disabled data-unavailable="true"':''}>${n.mode==='manual'?'확인 완료':n.mode==='draft'?'검토 완료':job.attempt?'다시 점검':'점검 실행'}</button></section>${checks.length?`<section class="ew-card"><div class="ew-heading"><h3>점검 결과</h3><span>${esc(job.attempt || 1)}차 실행</span></div>${checks.map(check=>`<div class="ew-check"><div class="ew-heading"><strong>${esc(check.name || c.definition.tools?.[check.id || check.tool_id || check.tool]?.name || check.id || check.tool_id || check.tool)}</strong>${badge(check.status)}</div><p>${esc(check.message || check.detail || check.summary || '')}</p>${check.evidence?`<pre>${esc(typeof check.evidence==='string'?check.evidence:JSON.stringify(check.evidence,null,2))}</pre>`:''}</div>`).join('')}</section>`:''}${history.length?`<details class="ew-history"><summary>이전 실행 기록 (${history.length})</summary>${history.map((run,i)=>`<section class="ew-card"><strong>${esc(run.attempt || i+1)}차 실행</strong> ${badge(run.status)}<p>${esc(run.at || run.completed_at || '')}</p>${(run.checks || []).map(check=>`<p>${esc(check.name || check.id || check.tool_id || check.tool)} · ${esc(statuses[check.status] || check.status)} · ${esc(check.message || check.detail || '')}</p>`).join('')}</section>`).join('')}</details>`:''}`;
  }


  function panelRegistration() {
    ensureHost();
    return {key:'workflow',label:'업무 진행',hostId:host.id,open:openHost,close:closeHost,isOpen:()=>Boolean(host?.isConnected),onChange:info=>{panelInfo=info;renderTabs();},focus:()=>$('#ees-work-close',host)?.focus({preventScroll:true})};
  }
  function readJobEdits() {
    const inputsForm=host?.querySelector('#ees-work-inputs'),docForm=host?.querySelector('#ees-work-document');
    return {inputs:inputsForm?Object.fromEntries(new FormData(inputsForm)):null,inputsChanged:Boolean(inputsForm&&Array.from(inputsForm.querySelectorAll('input')).some(input=>input.value!==input.defaultValue)),document:docForm?new FormData(docForm).get('document'):null};
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
    if(event.type==='change'&&target.id==='ees-work-run-select'){callbacks.openCase(target.value);return handled();}
    if(event.type==='submit'&&inside){
      const values=Object.fromEntries(new FormData(target));
      if(target.id==='ees-work-case-create')callbacks.startCase();
      else if(target.id==='ees-work-inputs')callbacks.saveInputs(values);
      else if(target.id==='ees-work-document')callbacks.saveDocument(values.document);
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
    const action=buttonTarget.dataset.action;
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
    else return unhandled;
    return handled();
  }
  function render(value) {readSnapshot(value);sidebar();renderNavigator();renderContext();renderPanel();}
  function prepare(value) {readSnapshot(value);sidebar();updateScopeReadiness();}
  function sync(value) {prepare(value);if(state&&snapshot.browseActive&&chatRoute()){if(!$('#ees-work-context'))renderContext();callbacks.registerPanel();}positionNav();}
  function updateLayout() {positionNav();sizePanel();}
  function detach() {closeScopePicker();closeHost();$('#ees-work-context')?.remove();}
  function reset() {
    detach();treeExpansions.clear();snapshot={};state=null;serverSource=null;historySource=null;historyCase=null;navOpen=false;busy=false;width=520;panelInfo=null;drag=null;
    host=null;divider=null;
    ['ees-work-entry','ees-work-admin-link','ees-work-navigator'].forEach(id=>document.getElementById(id)?.remove());
  }
  return Object.freeze({render,prepare,sync,renderNavigator:value=>{readSnapshot(value);renderNavigator();},renderPanel:value=>{readSnapshot(value);renderPanel();},setBusy,openPanel,closeHost,reset,readJobEdits,handleEvent,updateLayout,panelRegistration,revealSelection,closeScopePicker,detach,setNavigatorOpen:value=>{navOpen=Boolean(value);},updateScopeReadiness});
}
