"""
title: EES WO Demo
description: Sample equipment selection and WO drafting beside the existing chat. No EMS connection or real issuance.
version: 0.1.6
required_open_webui_version: 0.11.3
"""

import asyncio
import json


EVENT_TIMEOUT_SECONDS = 8
_LIMITS = {
    "corporation": 100, "site": 100, "shop": 100, "line": 100,
    "process": 100, "query": 100, "equipment_id": 100,
    "title": 100, "type": 100, "priority": 100, "description": 2500,
}
_HIERARCHY = ("corporation", "site", "shop", "line", "process")
_EQUIPMENT_FILTERS = (*_HIERARCHY, "query", "equipment_id")


def _demo_catalog():
    """Single sample source shared by independent lookup and the WO panel."""
    locations = (("한국", "천안", "KR-CA"), ("한국", "울산", "KR-US"),
                 ("헝가리", "헝가리 사업장", "HU"), ("미국", "미국 사업장", "US"))
    shops = (("전극", ("믹싱", "코팅")), ("조립", ("권취", "조립")))
    return tuple(
        {"id": f"{prefix}-{si}{number}{pi}", "name": f"{process} 설비 {number}호",
         "corporation": corporation, "site": site, "shop": shop,
         "line": f"{shop} {number}라인", "process": process}
        for corporation, site, prefix in locations
        for si, (shop, processes) in enumerate(shops, 1)
        for number in (1, 2)
        for pi, process in enumerate(processes, 1)
    )


_DEMO_EQUIPMENT = _demo_catalog()


def _find_demo_equipment(filters):
    """Shared lookup; no browser, model invocation, selection or EMS writes."""
    if any(key not in _EQUIPMENT_FILTERS or not isinstance(value, str) or len(value) > 100
           for key, value in filters.items()):
        return _error("invalid_filters", "설비 검색 조건은 100자 이내의 문자열로 입력해 주세요.")
    selected = {key: filters.get(key, "").strip() for key in _EQUIPMENT_FILTERS}
    query = selected["query"].lower()
    matches = [dict(item) for item in _DEMO_EQUIPMENT
               if all(not selected[key] or item[key] == selected[key] for key in _HIERARCHY)
               and (not selected["equipment_id"] or item["id"] == selected["equipment_id"])
               and (not query or query in (item["id"] + " " + item["name"]).lower())]
    options = {
        key: list(dict.fromkeys(item[key] for item in _DEMO_EQUIPMENT
                               if all(not selected[parent] or item[parent] == selected[parent]
                                      for parent in _HIERARCHY[:index])))
        for index, key in enumerate(_HIERARCHY)
    }
    return {"ok": True, "demo": True, "filters": selected, "available_options": options,
            "matches_count": len(matches), "matches": matches[:8], "matches_truncated": len(matches) > 8,
            "message": "샘플 설비 조회 결과입니다. 실제 EMS 조회가 아니며 설비를 선택하거나 WO를 작성하지 않았습니다."}

# A single copy/paste Tool is the deployment unit. No CDN, credentials,
# arbitrary model-generated JavaScript, package imports, or backend state.
PANEL_HTML = r"""<style>
  :host {
    color-scheme: inherit;
    --wo-bg: light-dark(#ffffff, #202124);
    --wo-soft: light-dark(#f6f7f9, #292b30);
    --wo-text: light-dark(#202735, #eef0f4);
    --wo-muted: light-dark(#626c7c, #b6bdc9);
    --wo-line: light-dark(#dce1e8, #454952);
    --wo-accent: light-dark(#2458b8, #a4c4ff);
    --wo-accent-soft: light-dark(#edf3ff, #273954);
    --wo-primary: light-dark(#2458b8, #b0ccff);
    --wo-primary-text: light-dark(#ffffff, #142b50);
    --wo-error: light-dark(#a52e2e, #ffb5b5);
    display: block;
    width: 420px;
    max-width: 100%;
    background: var(--wo-bg);
    color: var(--wo-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  *, *::before, *::after { box-sizing: border-box; }
  [hidden] { display: none !important; }
  h2, h3, p, dl { margin: 0; }
  button, input, select, textarea { font: inherit; }
  button, input, select, textarea { border: 1px solid var(--wo-line); border-radius: 8px; }
  input, select, textarea {
    width: 100%;
    min-width: 0;
    background: var(--wo-bg);
    color: var(--wo-text);
    font-size: 16px;
  }
  input, select { min-height: 44px; padding: 9px 11px; }
  textarea { display: block; padding: 11px; line-height: 1.6; resize: vertical; }
  input::placeholder, textarea::placeholder { color: var(--wo-muted); opacity: 1; }
  button {
    min-height: 44px;
    padding: 10px 14px;
    background: var(--wo-bg);
    color: var(--wo-text);
    font-weight: 600;
    cursor: pointer;
  }
  button:hover:not(:disabled) { background: var(--wo-soft); }
  button:disabled { cursor: default; opacity: .55; }
  :is(button, input, select, textarea):focus-visible { outline: 3px solid var(--wo-accent); outline-offset: 2px; }
  .panel { padding: 20px; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding-bottom: 18px; }
  .eyebrow { color: var(--wo-muted); font-size: 12px; font-weight: 600; margin-bottom: 5px; }
  .heading { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
  h2 { font-size: 21px; font-weight: 700; letter-spacing: -.4px; }
  h3 { font-size: 16px; font-weight: 650; letter-spacing: -.2px; }
  .badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 5px; background: var(--wo-soft); color: var(--wo-muted); font-size: 11px; font-weight: 600; }
  .close { flex: 0 0 auto; padding-inline: 12px; font-size: 13px; }
  .intro { padding: 12px; margin-bottom: 20px; background: var(--wo-soft); border-radius: 9px; color: var(--wo-muted); font-size: 13px; }
  .section-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 13px; }
  .section-title .badge { color: var(--wo-accent); background: var(--wo-accent-soft); }
  .field-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
  .field { min-width: 0; }
  .full { grid-column: 1 / -1; }
  label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; }
  .label-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
  .label-line label { margin: 0; }
  .origin { flex: 0 0 auto; color: var(--wo-accent); font-size: 11px; font-weight: 500; }
  .origin:empty { display: none; }
  .ai-changed { border-color: var(--wo-accent); background: var(--wo-accent-soft); }
  .required { color: var(--wo-muted); font-size: 11px; font-weight: 400; margin-left: 4px; }
  .result-count { margin: 15px 0 8px; color: var(--wo-muted); font-size: 12px; min-height: 18px; }
  .equipment-list { display: grid; gap: 8px; }
  .equipment-list:empty::before { content: "조건을 선택하거나 설비명·코드로 검색해 주세요."; padding: 18px 12px; text-align: center; color: var(--wo-muted); font-size: 13px; border: 1px dashed var(--wo-line); border-radius: 8px; }
  .equipment-option { display: grid; gap: 4px; width: 100%; padding: 12px; text-align: left; font-weight: 400; }
  .equipment-option strong { font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
  .equipment-option span { font-size: 12px; color: var(--wo-muted); line-height: 1.6; overflow-wrap: anywhere; }
  .equipment-option[aria-pressed="true"], .equipment-option.selected { border-color: var(--wo-accent); background: var(--wo-accent-soft); }
  .selected-equipment { padding: 12px; margin-top: 18px; border: 1px solid var(--wo-line); border-left: 3px solid var(--wo-accent); border-radius: 8px; background: var(--wo-soft); font-size: 13px; white-space: pre-line; overflow-wrap: anywhere; }
  .work-form { margin-top: 20px; padding-top: 19px; border-top: 1px solid var(--wo-line); }
  .work-form .field-grid { gap: 15px 12px; }
  .hint { color: var(--wo-muted); font-size: 12px; margin-top: 7px; }
  .change-note { margin-top: 13px; color: var(--wo-accent); font-size: 12px; white-space: pre-line; }
  .change-note:empty { display: none; }
  .undo { margin-top: 8px; font-size: 12px; padding-inline: 11px; }
  .validation { margin-top: 13px; color: var(--wo-error); font-size: 13px; }
  .actions { display: flex; align-items: stretch; gap: 8px; margin-top: 18px; }
  .actions button { flex: 1; }
  .primary { background: var(--wo-primary); border-color: var(--wo-primary); color: var(--wo-primary-text); }
  .primary:hover:not(:disabled) { background: var(--wo-primary); filter: brightness(.94); }
  .review, .complete { margin-top: 20px; padding-top: 19px; border-top: 1px solid var(--wo-line); }
  .section-copy { color: var(--wo-muted); margin-top: 7px; font-size: 13px; }
  .summary { margin-top: 16px; }
  .summary > div { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--wo-line); }
  .summary dt { color: var(--wo-muted); font-size: 12px; }
  .summary dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; white-space: pre-wrap; }
  .number { display: inline-block; margin-top: 12px; padding: 6px 10px; border-radius: 6px; color: var(--wo-accent); background: var(--wo-accent-soft); font-size: 14px; font-weight: 650; }
  .footer { margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--wo-line); color: var(--wo-muted); font-size: 11px; line-height: 1.7; }
  @media (max-width: 360px) {
    .panel { padding: 16px; }
    .field-grid { gap: 10px; }
    .summary > div { grid-template-columns: 62px minmax(0, 1fr); gap: 9px; }
  }
</style>
<div class="panel">
  <header class="header">
    <div>
      <p class="eyebrow">EES Assistant</p>
      <div class="heading"><h2 id="panel-title">설비 WO</h2><span class="badge">시연용</span><span id="stage" class="badge" role="status">발행 전</span></div>
    </div>
    <button id="close" class="close" type="button" aria-label="설비 WO 패널 닫기">닫기</button>
  </header>

  <p id="intro" class="intro">대화로 요청하거나 이 화면에서 직접 선택·수정할 수 있어요.</p>
  <div class="section-title">
    <button id="browse-equipment" type="button">설비 조회</button>
    <button id="back-to-wo" type="button" hidden>작성 중인 WO 보기</button>
  </div>
  <p id="change-note" class="change-note" role="status" aria-live="polite"></p>
  <p id="validation" class="validation" role="alert" hidden></p>

  <section id="filters" aria-labelledby="equipment-heading">
    <div class="section-title"><h3 id="equipment-heading">설비 찾기</h3></div>
    <div class="field-grid">
      <div class="field">
        <label for="corporation">법인</label>
        <select id="corporation"><option value="">전체</option></select>
      </div>
      <div class="field">
        <label for="site">사업장</label>
        <select id="site"><option value="">전체</option></select>
      </div>
      <div class="field">
        <label for="shop">SHOP</label>
        <select id="shop"><option value="">전체</option></select>
      </div>
      <div class="field">
        <label for="line">LINE</label>
        <select id="line"><option value="">전체</option></select>
      </div>
      <div class="field full">
        <label for="process">PROCESS</label>
        <select id="process"><option value="">전체</option></select>
      </div>
      <div class="field full">
        <label for="query">설비 검색</label>
        <input id="query" type="search" maxlength="100" placeholder="설비명 또는 설비 코드" autocomplete="off">
      </div>
      <div id="equipment-code-field" class="field full" hidden>
        <label for="equipment-code">설비 코드 · 정확히 일치</label>
        <input id="equipment-code" type="search" maxlength="100" placeholder="예: KR-CA-211" autocomplete="off">
      </div>
    </div>
    <p id="count" class="result-count" role="status" aria-live="polite">시연용 설비를 불러오는 중이에요.</p>
    <div id="results" class="equipment-list" aria-label="설비 검색 결과"></div>
  </section>

  <div id="selected" class="selected-equipment" role="status" hidden></div>
  <p id="search-hint" class="hint" hidden>설비를 선택한 뒤 대화에서 “이 설비로 WO 초안 작성해줘”라고 요청해 주세요. 선택만으로 WO를 작성하지 않아요.</p>
  <button id="choose-again" class="undo" type="button" hidden>설비 다시 선택</button>

  <form id="form" class="work-form" novalidate hidden>
    <div class="section-title"><h3>WO 작성</h3></div>
    <div class="field-grid">
      <div class="field full">
        <div class="label-line"><label for="title">작업 제목<span class="required">필수</span></label><span class="origin" data-origin-for="title"></span></div>
        <input id="title" type="text" maxlength="100" required placeholder="예: 권취기 모터 이상 소음 점검" autocomplete="off">
      </div>
      <div class="field">
        <div class="label-line"><label for="type">작업 유형</label><span class="origin" data-origin-for="type"></span></div>
        <select id="type"><option value="점검">점검</option><option value="수리">수리</option></select>
      </div>
      <div class="field">
        <div class="label-line"><label for="priority">우선순위</label><span class="origin" data-origin-for="priority"></span></div>
        <select id="priority"><option value="일반">일반</option><option value="긴급">긴급</option></select>
      </div>
      <div class="field full">
        <div class="label-line"><label for="description">작업 내용<span class="required">필수</span></label><span class="origin" data-origin-for="description"></span></div>
        <textarea id="description" rows="4" maxlength="2500" required placeholder="증상과 요청할 작업 내용을 입력해 주세요."></textarea>
        <p class="hint">대화에서 수정을 요청하면 이 내용에 반영돼요.</p>
      </div>
    </div>
    <button id="undo" class="undo" type="button" hidden>AI 수정 되돌리기</button>
    <div class="actions"><button id="review-button" class="primary" type="submit">발행 내용 확인</button></div>
  </form>

  <section id="review" class="review" aria-labelledby="review-heading" hidden>
    <h3 id="review-heading">발행 내용 확인</h3>
    <p class="section-copy">설비와 작업 내용을 확인한 뒤 직접 발행해 주세요.</p>
    <dl id="review-values" class="summary"></dl>
    <div class="actions">
      <button id="edit" type="button">돌아가서 수정</button>
      <button id="issue" class="primary" type="button">WO 발행 · 시연</button>
    </div>
  </section>

  <section id="result" class="complete" aria-labelledby="result-heading" hidden>
    <h3 id="result-heading">발행 완료 예시</h3>
    <p class="section-copy">시연용 발행 흐름이 완료됐어요. 실제 WO는 생성되지 않았어요.</p>
    <p id="result-number" class="number"></p>
    <dl id="result-values" class="summary"></dl>
  </section>

  <footer class="footer">샘플 설비와 입력 항목으로 동작하며 실제 EMS에 저장되지 않아요.<br>새로고침하면 시연 내용이 초기화돼요.</footer>
</div>
"""

PANEL_SCRIPT = r"""
let panelStage='route_check';
try {
  const fail = (code, message) => ({ok: false, demo: true, error: {code, message}});
  if (location.pathname !== '/c/' + encodeURIComponent(request.chat_id)) {
    // A late response from another chat must not clear the currently open draft.
    window.__eesWODemoManagerV1?.sync();
    return fail('regular_chat_required', '시연은 일반 대화에서 사용할 수 있습니다. 임시 대화나 노트 대신 일반 대화에서 요청해 주세요.');
  }
  const getLayout = () => {
    const anchor=document.querySelector('#chat-container #chat-pane'),column=anchor?.parentElement,row=column?.parentElement;
    // v0.11.3 keeps the English aria-label even when the Controls tooltip is translated.
    const controls=column?.querySelector('nav button[aria-label="Controls"]'),controlsWrapper=controls?.parentElement;
    const toolbar=controlsWrapper?.parentElement || column?.querySelector('nav .flex-none.items-center.gap-2.self-center');
    return row?.isConnected && toolbar?.isConnected && getComputedStyle(row).display==='flex'?{anchor,column,row,toolbar,controlsWrapper}:null;
  };
  panelStage='layout_lookup';
  const layout=getLayout();
  if (!layout) {
    return fail('unsupported_layout', '이 화면에서 시연 패널을 열 수 없습니다. 일반 대화 화면과 WebUI 버전을 확인해 주세요.');
  }
  panelStage='manager_setup';
  let manager=window.__eesWODemoManagerV1;
  if(!manager){
    // v0.1.2 had one disposable controller. A refresh is recommended on upgrade.
    window.__eesWODemoV1?.destroy();
    const chats=new Map();let active=null,disposed=false;
    const sync=records=>{
      if(disposed)return;
      if(/^\/(auth|logout)(\/|$)/.test(location.pathname)){destroy();return;}
      const current=Array.from(chats.values()).find(item=>item.pathname===location.pathname)||null;
      const nextLayout=current?getLayout():null;
      if(active && (active!==current || !active.alive())){
        active.detach();active=null;delete window.__eesWODemoV1;
      }
      if(current && nextLayout){
        if(!active){active=current;active.attach(nextLayout);window.__eesWODemoV1=active;}
        else active.layoutChanged(Array.isArray(records)?records:[]);
      }
    };
    const theme=()=>active?.theme();
    const observer=new MutationObserver(sync),themeObserver=new MutationObserver(theme);
    const navigation=window.navigation;
    const destroy=()=>{
      if(disposed)return;disposed=true;
      observer.disconnect();themeObserver.disconnect();
      window.removeEventListener('popstate',sync);window.removeEventListener('pagehide',destroy);
      navigation?.removeEventListener('navigatesuccess',sync);
      chats.forEach(item=>item.detach());chats.clear();active=null;
      delete window.__eesWODemoV1;delete window.__eesWODemoManagerV1;
    };
    manager={chats,sync,destroy};window.__eesWODemoManagerV1=manager;
    observer.observe(document.body,{childList:true,subtree:true});
    themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['class']});
    window.addEventListener('popstate',sync);window.addEventListener('pagehide',destroy);
    navigation?.addEventListener('navigatesuccess',sync);
  }
  panelStage='state_restore';
  manager.sync();
  let controller=manager.chats.get(request.chat_id);
  if (!controller && !['view','equipment'].includes(request.action)) {
    return fail('view_required', '먼저 시연 화면의 현재 상태를 확인해 주세요. 이전 화면의 수정 요청은 적용하지 않았습니다.');
  }
  if (!controller) {
    panelStage='panel_create';
    let {anchor,column,row,toolbar}=layout;
    const hierarchy = ['corporation', 'site', 'shop', 'line', 'process'];
    const contentFields = ['title', 'type', 'priority', 'description'];
    const fieldNames = {corporation:'법인',site:'사업장',shop:'SHOP',line:'LINE',process:'PROCESS',query:'설비 검색',equipment_id:'설비',title:'작업 제목',type:'작업 구분',priority:'우선순위',description:'요청 내용'};
    const catalog = equipmentCatalog;
    const state = {revision:Date.now(),phase:'edit',filters:Object.fromEntries([...hierarchy,'query'].map(k=>[k,''])),equipment_id:'',fields:{title:'',type:'점검',priority:'일반',description:''}};
    // Browsing equipment is independent of a draft, including a reviewed or issued WO.
    const search = {filters:Object.fromEntries([...hierarchy,'query','equipment_id'].map(k=>[k,''])),selected_id:''};
    let screen=request.action==='equipment'?'equipment':'wo', searchNote='샘플 설비를 조회하고 선택할 수 있어요.';
    const origins = {};
    let reviewed = null, lastAI = null, visibleLimit = 8, choosing = true, note = '법인·사업장이나 설비명으로 대상 설비를 찾아보세요.';
    const mountedPath = location.pathname;
    let originalMinWidth,attached=false,wantsOpen=true;
    const host = document.createElement('aside');
    host.id = 'ees-wo-demo-panel'; host.setAttribute('aria-label','설비 WO 시연');
    host.style.cssText = 'flex:0 0 420px;width:420px;min-width:0;box-sizing:border-box;height:100%;min-height:0;overflow:auto;border-left:1px solid #8886;z-index:30;';
    const divider = document.createElement('div');
    divider.id='ees-wo-demo-resizer';divider.tabIndex=0;
    divider.setAttribute('role','separator');divider.setAttribute('aria-orientation','vertical');
    divider.setAttribute('aria-label','대화와 업무 화면 너비 조절');divider.setAttribute('aria-controls',host.id);
    divider.title='드래그하거나 좌우 방향키로 화면 너비를 조절하세요.';
    divider.style.cssText='flex:0 0 10px;width:10px;align-self:stretch;display:flex;align-items:center;justify-content:center;cursor:col-resize;touch-action:none;user-select:none;z-index:31;';
    const grip=document.createElement('span');grip.style.cssText='width:3px;height:36px;border-radius:2px;background:#8888;pointer-events:none;';divider.append(grip);
    panelStage='template_load';
    const shadow = host.attachShadow({mode:'open'});
    // Only this reviewed, constant template is assigned as HTML. All data use textContent/value.
    shadow.innerHTML = panelHTML;
    panelStage='controls_create';
    const launcherSlot=document.createElement('div');launcherSlot.className='flex';
    const launcher=document.createElement('button');
    launcher.id='ees-work-panel-toggle';launcher.type='button';
    launcher.setAttribute('aria-controls',host.id);
    launcher.className='flex size-6 cursor-pointer items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-50/40 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800/40 dark:hover:text-gray-200';
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
    Object.entries({viewBox:'0 0 24 24',width:'20',height:'20',fill:'none',stroke:'currentColor','stroke-width':'1','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}).forEach(([key,value])=>icon.setAttribute(key,value));
    const iconPath=document.createElementNS('http://www.w3.org/2000/svg','path');
    iconPath.setAttribute('d','M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm10 0v18');
    icon.append(iconPath);launcher.append(icon);launcherSlot.append(launcher);
    const q = id => shadow.getElementById(id);
    const findEquipment = id => catalog.find(e=>e.id===id) || null;
    const path = e => [e.corporation,e.site,e.shop,e.line,e.process].join(' / ');
    const matches = filters => catalog.filter(e=>hierarchy.every(k=>!filters[k] || e[k]===filters[k]) && (!filters.equipment_id?.trim() || e.id===filters.equipment_id.trim()) && (!filters.query || (e.id+' '+e.name).toLowerCase().includes(filters.query.toLowerCase().trim())));
    const options = (key, filters) => [...new Set(catalog.filter(e=>hierarchy.slice(0,hierarchy.indexOf(key)).every(k=>!filters[k] || e[k]===filters[k])).map(e=>e[key]))];
    const alive = () => attached && location.pathname === mountedPath && row.isConnected && document.querySelector('#chat-container #chat-pane') === anchor && anchor.parentElement===column && column.parentElement===row && launcher.isConnected && launcherSlot.parentElement===toolbar;
    const searchView = () => {
      const list=matches(search.filters);
      return {filters:{...search.filters},selected_equipment:findEquipment(search.selected_id),available_options:Object.fromEntries(hierarchy.map(k=>[k,options(k,search.filters)])),matches_count:list.length,matches:list.slice(0,8),matches_truncated:list.length>8};
    };
    const view = () => {
      const list = matches(state.filters);
      return {ok:true,demo:true,screen,revision:state.revision,phase:state.phase,filters:{...state.filters},equipment:findEquipment(state.equipment_id),fields:{...state.fields},equipment_search:searchView(),available_options:Object.fromEntries(hierarchy.map(k=>[k,options(k,state.filters)])),matches_count:list.length,matches:list.slice(0,8),matches_truncated:list.length>8,message:screen==='equipment'?searchNote:note};
    };
    const displayError = message => { q('validation').textContent=message; q('validation').hidden=false; };
    const renderValues = (target, values) => {
      target.replaceChildren();
      const equipment = findEquipment(values.equipment_id);
      const entries = [['설비',equipment ? equipment.name+' · '+equipment.id : '미선택'],['위치',equipment ? path(equipment) : ''],...contentFields.map(k=>[fieldNames[k],values.fields[k]])];
      entries.forEach(([label,text])=>{const wrapper=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=text;wrapper.append(dt,dd);target.append(wrapper);});
    };
    const render = () => {
      const complete=state.phase==='issued', checking=state.phase==='review';
      const browsing=screen==='equipment', filters=browsing?search.filters:state.filters;
      q('panel-title').textContent=browsing?'설비 조회':'설비 WO';
      host.setAttribute('aria-label',browsing?'설비 조회 시연':'설비 WO 시연');
      q('close').setAttribute('aria-label',browsing?'설비 조회 패널 닫기':'설비 WO 패널 닫기');
      q('intro').textContent=browsing?'대화에서 받은 검색 조건을 보여드려요. 필터를 바꾸거나 설비를 눌러 상세 정보를 확인하세요.':'대화로 요청하거나 이 화면에서 직접 선택·수정할 수 있어요.';
      q('stage').textContent=complete?'발행 완료 예시':checking?'최종 확인':'발행 전';
      q('stage').hidden=browsing;
      q('browse-equipment').hidden=browsing;
      q('back-to-wo').hidden=!browsing || !(state.equipment_id || state.fields.title || state.fields.description || checking || complete);
      q('back-to-wo').textContent=complete?'발행 완료 예시 보기':'작성 중인 WO 보기';
      q('filters').hidden=!browsing && (complete || checking || !choosing);
      q('form').hidden=browsing || complete || checking || choosing || !state.equipment_id;
      q('choose-again').hidden=browsing || complete || checking || choosing || !state.equipment_id;
      q('review').hidden=browsing || !checking; q('result').hidden=browsing || !complete;
      q('equipment-code-field').hidden=!browsing;q('equipment-code').value=search.filters.equipment_id;
      q('search-hint').hidden=!browsing;
      hierarchy.forEach((key,index)=>{
        const select=q(key), all=document.createElement('option');all.value='';all.textContent='전체';
        select.replaceChildren(all);
        const values=options(key,filters);
        // Even an unknown/conflicting chat condition stays visible with its zero results.
        if(filters[key] && !values.includes(filters[key]))values.push(filters[key]);
        values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option);});
        select.value=filters[key];select.disabled=!browsing && (complete || (index>0 && !state.filters[hierarchy[index-1]]));
      });
      q('query').value=filters.query;
      const list=matches(filters);q('count').textContent=list.length+'개 설비 · 샘플';
      q('results').replaceChildren();
      list.slice(0,visibleLimit).forEach(e=>{
        const button=document.createElement('button');button.type='button';button.className='equipment-option';button.dataset.equipmentId=e.id;button.setAttribute('aria-pressed',String((browsing?search.selected_id:state.equipment_id)===e.id));
        const name=document.createElement('strong'),detail=document.createElement('span');name.textContent=e.name+' · '+e.id;detail.textContent=path(e);button.append(name,detail);
        button.addEventListener('click',()=>{
          if(screen==='equipment'){search.selected_id=e.id;searchNote='설비 상세 정보를 확인해 주세요. WO가 필요하면 대화에서 작성을 요청하세요.';render();}
          else apply({equipment_id:e.id},'user');
        });q('results').append(button);
      });
      if(!list.length){const empty=document.createElement('p');empty.textContent='조건에 맞는 설비가 없습니다. 필터나 검색어를 바꿔보세요.';q('results').append(empty);}
      if(list.length>visibleLimit){const more=document.createElement('button');more.type='button';more.textContent='설비 더 보기';more.addEventListener('click',()=>{visibleLimit+=8;render();});q('results').append(more);}
      const selected=findEquipment(browsing?search.selected_id:state.equipment_id);q('selected').hidden=!selected;
      q('selected').textContent=selected?'선택 설비: '+selected.name+' · '+selected.id+' — '+path(selected):'';
      contentFields.forEach(key=>{
        q(key).value=state.fields[key];q(key).disabled=complete;
        const badge=shadow.querySelector('[data-origin-for="'+key+'"]');
        badge.textContent=origins[key]==='ai'?'AI 수정':origins[key]==='user'?'직접 수정':'';
        q(key).classList.toggle('ai-changed',origins[key]==='ai');
      });
      q('change-note').textContent=browsing?searchNote:note;
      q('undo').hidden=!lastAI || complete;
      if(checking && reviewed)renderValues(q('review-values'),reviewed);
    };
    const apply = (changes, origin) => {
      if(state.phase==='issued')return fail('already_issued','발행 완료 예시는 수정하지 않습니다. 새 시연은 새 대화에서 시작해 주세요.');
      const next={filters:{...state.filters},equipment_id:state.equipment_id,fields:{...state.fields}};
      for(const key of hierarchy){
        if(!(key in changes))continue;
        const value=changes[key];
        const parentKey=hierarchy[hierarchy.indexOf(key)-1];
        if(value && parentKey && !next.filters[parentKey])return fail('parent_required',fieldNames[parentKey]+'부터 선택해 주세요.');
        if(value && !options(key,next.filters).includes(value))return fail('invalid_option',fieldNames[key]+' 값을 현재 선택 범위에서 찾을 수 없습니다.');
        if(value!==next.filters[key]){
          next.filters[key]=value;
          hierarchy.slice(hierarchy.indexOf(key)+1).forEach(child=>next.filters[child]='');
        }
      }
      if('query' in changes)next.filters.query=changes.query;
      if('equipment_id' in changes){
        const equipment=findEquipment(changes.equipment_id);
        if(changes.equipment_id && !equipment)return fail('unknown_equipment','샘플 목록에 있는 설비 코드를 선택해 주세요.');
        if(equipment){
          // Explicit conditions must agree with an explicitly selected equipment.
          if(hierarchy.some(k=>(k in changes) && changes[k] && changes[k]!==equipment[k]))return fail('equipment_scope_mismatch','선택한 설비와 법인·사업장·필터 조건이 다릅니다.');
          hierarchy.forEach(k=>next.filters[k]=equipment[k]);next.filters.query='';
        }
        next.equipment_id=changes.equipment_id;
      }else if(next.equipment_id && !matches(next.filters).some(e=>e.id===next.equipment_id))next.equipment_id='';
      for(const key of contentFields){
        if(!(key in changes))continue;
        if(key==='type' && !['점검','수리'].includes(changes[key]))return fail('invalid_option','작업 구분은 점검 또는 수리입니다.');
        if(key==='priority' && !['일반','긴급'].includes(changes[key]))return fail('invalid_option','우선순위는 일반 또는 긴급입니다.');
        next.fields[key]=changes[key];
      }
      const touched=[...hierarchy,'query'].filter(k=>next.filters[k]!==state.filters[k]);
      if(next.equipment_id!==state.equipment_id)touched.push('equipment_id');
      touched.push(...contentFields.filter(k=>next.fields[k]!==state.fields[k]));
      if(!touched.length){if(changes.equipment_id){choosing=false;render();}return view();}
      const previous={filters:{...state.filters},equipment_id:state.equipment_id,fields:{...state.fields},origins:{...origins}};
      const wasReview=state.phase==='review';
      const hadEquipment=state.equipment_id;
      state.filters=next.filters;state.equipment_id=next.equipment_id;state.fields=next.fields;state.revision+=1;state.phase='edit';reviewed=null;visibleLimit=8;
      if(changes.equipment_id)choosing=false;
      else if([...hierarchy,'query'].some(k=>k in changes))choosing=true;
      contentFields.filter(k=>touched.includes(k)).forEach(k=>origins[k]=origin);
      lastAI=origin==='ai'?previous:null;
      note=(origin==='ai'?'AI가 수정한 항목: ':'변경한 항목: ')+touched.map(k=>fieldNames[k]).join(', ');
      if(hadEquipment!==state.equipment_id && (state.fields.title || state.fields.description))note+=' · 작성 내용은 유지했어요. 대상 설비와 맞는지 확인해 주세요.';
      if(wasReview)note+=' · 내용이 바뀌어 다시 최종 확인이 필요해요.';
      q('validation').hidden=true;render();if(changes.equipment_id)host.scrollTop=0;return view();
    };
    const browse = filters => {
      search.filters={...filters};search.selected_id='';screen='equipment';visibleLimit=8;
      searchNote='검색 조건에 맞는 샘플 설비입니다. 설비를 선택하면 상세 정보를 확인할 수 있어요.';
      q('validation').hidden=true;render();host.scrollTop=0;
      return {...view(),opened:host.isConnected};
    };
    const changeSearch = (key,value) => {
      // Keep spaces while typing (e.g. "권취 설비"); matching normalizes text.
      search.filters[key]=['query','equipment_id'].includes(key)?value:value.trim();
      if(hierarchy.includes(key))hierarchy.slice(hierarchy.indexOf(key)+1).forEach(child=>search.filters[child]='');
      if(!matches(search.filters).some(e=>e.id===search.selected_id))search.selected_id='';
      visibleLimit=8;searchNote='검색 조건을 변경했어요. 작성 중인 WO는 그대로 유지돼요.';
      q('validation').hidden=true;render();
    };
    panelStage='event_bind';
    hierarchy.forEach(key=>q(key).addEventListener('change',()=>{
      if(screen==='equipment'){changeSearch(key,q(key).value);return;}
      const result=apply({[key]:q(key).value},'user');if(!result.ok)displayError(result.error.message);
    }));
    q('query').addEventListener('input',()=>screen==='equipment'?changeSearch('query',q('query').value):apply({query:q('query').value},'user'));
    q('equipment-code').addEventListener('input',()=>changeSearch('equipment_id',q('equipment-code').value));
    q('browse-equipment').addEventListener('click',()=>{screen='equipment';q('validation').hidden=true;render();host.scrollTop=0;});
    q('back-to-wo').addEventListener('click',()=>{screen='wo';q('validation').hidden=true;render();host.scrollTop=0;});
    q('choose-again').addEventListener('click',()=>{choosing=true;render();host.scrollTop=0;});
    contentFields.forEach(key=>q(key).addEventListener('input',()=>apply({[key]:q(key).value},'user')));
    q('undo').addEventListener('click',()=>{
      if(!lastAI || state.phase==='issued')return;
      state.filters={...lastAI.filters};state.equipment_id=lastAI.equipment_id;state.fields={...lastAI.fields};
      Object.keys(origins).forEach(k=>delete origins[k]);Object.assign(origins,lastAI.origins);
      lastAI=null;state.revision+=1;state.phase='edit';choosing=!state.equipment_id;reviewed=null;note='마지막 AI 수정을 되돌렸어요.';render();
    });
    q('form').addEventListener('submit',event=>{
      event.preventDefault();if(state.phase!=='edit')return;
      if(!state.equipment_id || !state.fields.title.trim() || !state.fields.description.trim()){
        displayError('설비를 선택하고 작업 제목과 요청 내용을 입력해 주세요.');
        (!state.fields.title.trim()?q('title'):q('description')).focus();return;
      }
      if(state.fields.title.length>100 || state.fields.description.length>2500){displayError('제목은 100자, 요청 내용은 2,500자까지 입력해 주세요.');return;}
      reviewed={revision:state.revision,equipment_id:state.equipment_id,fields:{...state.fields}};
      state.phase='review';q('validation').hidden=true;render();q('issue').focus();
    });
    q('edit').addEventListener('click',()=>{if(state.phase!=='review')return;reviewed=null;state.phase='edit';render();q('title').focus();});
    q('issue').addEventListener('click',()=>{
      if(state.phase!=='review' || !reviewed || reviewed.revision!==state.revision)return;
      const issued={equipment_id:reviewed.equipment_id,fields:{...reviewed.fields}};
      reviewed=null;lastAI=null;state.phase='issued';state.revision+=1;note='샘플 WO 발행 완료. 실제 EMS에는 저장하지 않았습니다.';
      q('issue').disabled=true;q('result-number').textContent='WO-DEMO-0001';renderValues(q('result-values'),issued);render();
    });
    let panelWidth=null, maximumWidth=800, drag=null;
    const finishDrag = event => {
      if(!drag || (event && event.pointerId!==drag.id))return;
      const previous=drag;drag=null;
      if(divider.hasPointerCapture(previous.id))divider.releasePointerCapture(previous.id);
      document.body.style.userSelect=previous.selection;document.body.style.cursor=previous.cursor;
    };
    const setWidth = value => {
      panelWidth=Math.round(Math.max(350,Math.min(maximumWidth,value)));
      host.style.width=panelWidth+'px';host.style.flexBasis=panelWidth+'px';
      divider.setAttribute('aria-valuenow',String(panelWidth));divider.setAttribute('aria-valuetext',panelWidth+'픽셀');
    };
    const resize = () => {
      if(!host.isConnected)return;
      // v0.11.3 chat row has no padding/gap; its native siblings have no margins.
      const others=Array.from(row.children).filter(child=>child!==column && child!==host && child!==divider);
      const occupied=others.reduce((total,child)=>{
        const style=getComputedStyle(child);
        return total+(['absolute','fixed'].includes(style.position)?0:child.getBoundingClientRect().width);
      },0);
      const available=row.clientWidth-occupied;
      const mobile=window.innerWidth<900 || available<720;
      divider.hidden=mobile;divider.style.display=mobile?'none':'flex';
      if(mobile){finishDrag();host.style.position='fixed';host.style.inset='0 0 0 auto';host.style.width='min(100%,480px)';host.style.zIndex='60';}
      else {
        host.style.position='relative';host.style.inset='auto';host.style.zIndex='30';
        maximumWidth=Math.floor(Math.min(800,available-360-10));
        divider.setAttribute('aria-valuemin','350');divider.setAttribute('aria-valuemax',String(Math.floor(maximumWidth)));
        setWidth(panelWidth===null?Math.min(480,available*.44):panelWidth);
      }
    };
    divider.addEventListener('pointerdown',event=>{
      if(divider.hidden || event.button!==0 || event.isPrimary===false)return;
      finishDrag();
      drag={id:event.pointerId,x:event.clientX,width:panelWidth,selection:document.body.style.userSelect,cursor:document.body.style.cursor};
      document.body.style.userSelect='none';document.body.style.cursor='col-resize';
      try{divider.setPointerCapture(event.pointerId);}catch(_){finishDrag();return;}
      divider.focus({preventScroll:true});divider.style.outline='none';event.preventDefault();
    });
    divider.addEventListener('pointermove',event=>{if(drag && event.pointerId===drag.id)setWidth(drag.width+drag.x-event.clientX);});
    ['pointerup','pointercancel','lostpointercapture'].forEach(type=>divider.addEventListener(type,finishDrag));
    divider.addEventListener('keydown',event=>{
      if(divider.hidden || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      divider.style.outline='2px solid #6b91d5';
      event.preventDefault();setWidth(event.key==='Home'?350:event.key==='End'?maximumWidth:panelWidth+(event.key==='ArrowLeft'?20:-20));
    });
    divider.addEventListener('focus',()=>divider.style.outline='2px solid #6b91d5');
    divider.addEventListener('blur',()=>divider.style.outline='');
    panelStage='resize_setup';
    const resizeObserver=new ResizeObserver(resize);
    const observeLayout=()=>{
      resizeObserver.disconnect();if(!host.isConnected)return;
      resizeObserver.observe(row);
      Array.from(row.children).filter(child=>child!==host && child!==divider).forEach(child=>resizeObserver.observe(child));
    };
    const theme = () => {
      const dark=document.documentElement.classList.contains('dark');
      host.style.colorScheme=dark?'dark':'light';
    };
    const updateLauncher=()=>{
      launcher.title=wantsOpen?'업무 패널 닫기':'업무 패널 열기';
      launcher.setAttribute('aria-label',launcher.title);
      launcher.setAttribute('aria-expanded',String(wantsOpen));
      launcher.style.backgroundColor=wantsOpen?'#8882':'';
    };
    const hidePanel=()=>{
      finishDrag();resizeObserver.disconnect();window.removeEventListener('resize',resize);
      divider.remove();host.remove();if(attached)column.style.minWidth=originalMinWidth;
    };
    const close=()=>{wantsOpen=false;hidePanel();updateLauncher();launcher.focus({preventScroll:true});};
    const open=()=>{
      wantsOpen=true;if(!attached)return;
      if(!host.isConnected){row.append(divider,host);observeLayout();window.addEventListener('resize',resize);}
      column.style.minWidth='0';host.hidden=false;updateLauncher();resize();theme();
    };
    const detach=()=>{
      hidePanel();launcherSlot.remove();attached=false;
    };
    const attach=nextLayout=>{
      ({anchor,column,row,toolbar}=nextLayout);originalMinWidth=column.style.minWidth;
      attached=true;toolbar.insertBefore(launcherSlot,nextLayout.controlsWrapper || null);updateLauncher();theme();if(wantsOpen)open();
    };
    controller={chatId:request.chat_id,pathname:mountedPath,alive,attach,detach,theme,open,view,browse,
      layoutChanged:records=>{if(records.some(record=>record.target===row)){observeLayout();resize();}},
      woView:()=>{screen='wo';render();return view();},update:(revision,changes)=>{
      if(revision!==state.revision)return {...fail('revision_conflict','사용자가 화면을 수정했습니다. 현재 값을 확인하고 요청한 부분만 다시 수정해 주세요.'),current:view()};
      const result=apply(changes,'ai');if(!result.ok){displayError(result.error.message);return result;}
      screen='wo';render();return view();
    }};
    q('close').addEventListener('click',close);
    launcher.addEventListener('click',()=>wantsOpen?close():open());
    panelStage='initial_render';
    render();
    // Cache only a fully rendered controller so a failed first render can be retried.
    manager.chats.set(request.chat_id,controller);
    panelStage='panel_mount';
    manager.sync();
  }
  panelStage='panel_open';
  controller.open();
  panelStage=request.action==='equipment'?'equipment_render':request.action==='view'?'wo_render':'wo_update';
  if(request.action==='equipment')return controller.browse(request.filters);
  return request.action==='view'?controller.woView():controller.update(request.expected_revision,request.changes);
} catch (error) {
  // Return fixed diagnostic labels only; exception messages/stacks may contain user data.
  const exception=['TypeError','ReferenceError','RangeError','SyntaxError','Error','NotFoundError','NotSupportedError','SecurityError','InvalidStateError','InvalidCharacterError'].includes(error?.name)?error.name:'Error';
  return {ok:false,demo:true,error:{code:'panel_error',message:'시연 화면을 처리하지 못했습니다. 화면의 현재 내용을 확인한 뒤 다시 열어 주세요.',diagnostic:{script_version:'0.1.6',stage:panelStage,exception}}};
}
"""


def _error(code, message):
    return {"ok": False, "demo": True, "error": {"code": code, "message": message}}


async def _call(action, event_call, metadata, **values):
    chat_id = metadata.get("chat_id") if isinstance(metadata, dict) else None
    if not isinstance(chat_id, str) or not chat_id.strip() or len(chat_id) > 128:
        return _error("chat_required", "기존 WebUI 대화에서 시연을 시작해 주세요.")
    if not callable(event_call):
        return _error("browser_required", "WebUI 대화 화면의 연결을 확인해 주세요.")
    request = {"action": action, "chat_id": chat_id, **values}
    code = "const request = " + json.dumps(request, ensure_ascii=True) + ";\n"
    code += "const equipmentCatalog = " + json.dumps(_DEMO_EQUIPMENT, ensure_ascii=True) + ";\n"
    code += "const panelHTML = " + json.dumps(PANEL_HTML, ensure_ascii=True) + ";\n" + PANEL_SCRIPT
    try:
        result = await asyncio.wait_for(event_call({"type": "execute", "data": {"code": code}}), timeout=EVENT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return _error("browser_response_unconfirmed", "화면 응답을 확인하지 못했습니다. 적용 여부를 단정하지 말고 현재 시연 화면을 다시 확인해 주세요.")
    except Exception:
        return _error("browser_response_unconfirmed", "화면 응답을 확인하지 못했습니다. 현재 시연 화면을 다시 확인해 주세요.")
    if not isinstance(result, dict) or type(result.get("ok")) is not bool:
        return _error("browser_response_unconfirmed", "화면 응답을 확인하지 못했습니다. WebUI 대화 화면에서 다시 시도해 주세요.")
    return {**result, "demo": True}


class Tools:
    async def ems_demo_find_equipment(self, corporation: str = "", site: str = "", shop: str = "",
                                      line: str = "", process: str = "", query: str = "",
                                      equipment_id: str = "", __event_call__=None, __metadata__=None) -> dict:
        """Find SAMPLE equipment and show matching filters/results in the existing chat's resizable side panel. Equipment selection displays details, never creates/retargets a WO. The separate panel.ok reports whether the UI opened; lookup results can succeed even if the panel fails. Zero/multiple matches are normal results. Never invent an ID or select the first of multiple matches. No real EMS connection. A later wo_demo_view returns equipment_search.selected_equipment chosen in the panel; use that ID explicitly when drafting.

        :param corporation: Exact corporation, e.g. 한국. Empty means all.
        :param site: Exact site, e.g. 천안. Known conditions can be supplied without all parents.
        :param shop: Exact SHOP, e.g. 조립.
        :param line: Exact LINE, e.g. 조립 1라인.
        :param process: Exact PROCESS, e.g. 권취. Hierarchy is SHOP > LINE > PROCESS.
        :param query: Equipment name or code substring. At most 100 characters.
        :param equipment_id: Exact returned equipment ID. Combined with other conditions using AND.
        """
        found = _find_demo_equipment({"corporation": corporation, "site": site, "shop": shop,
                                      "line": line, "process": process, "query": query,
                                      "equipment_id": equipment_id})
        if not found["ok"]:
            return found
        panel = await _call("equipment", __event_call__, __metadata__, filters=found["filters"])
        if panel["ok"] and (panel.get("opened") is not True or panel.get("screen") != "equipment"):
            panel = _error("browser_response_unconfirmed", "조회 화면이 열렸는지 확인하지 못했습니다. 현재 화면을 확인한 뒤 다시 요청해 주세요.")
        elif panel["ok"]:
            # Return one search dataset; unrelated WO contents stay in wo_demo_view.
            panel = {"ok": True, "demo": True, "opened": True, "screen": "equipment"}
        message = ("샘플 설비 조회 결과를 옆 패널에 표시했습니다. 설비를 선택해 상세 정보를 확인할 수 있습니다. WO 작성은 별도로 요청해 주세요."
                   if panel["ok"] else "샘플 설비 조회는 완료했지만 옆 패널 표시를 확인하지 못했습니다. 조회 결과를 안내하고 화면 상태를 확인해 주세요.")
        return {**found, "panel": panel, "message": message}

    async def wo_demo_view(self, __event_call__=None, __metadata__=None) -> dict:
        """Open/resume the SAMPLE WO side panel and read its latest form, revision, filter options and matching equipment. Also returns equipment_search.selected_equipment from the independent lookup panel; that selection does not change the existing WO equipment. Use before editing, including after manual UI input. This never reads EMS or issues a WO. Follow returned options and sample equipment IDs, never invent them."""
        return await _call("view", __event_call__, __metadata__)

    async def wo_demo_update(self, expected_revision: int, changes: dict, __event_call__=None, __metadata__=None) -> dict:
        """Edit only requested fields in the SAMPLE panel, preserving other current values. Call wo_demo_view first; use its revision. On revision_conflict read current state and preserve new user input. No issuance action exists. For an initial draft, send the resolved equipment_id and title/type/priority/description together in one update; preserve existing user values.

        :param expected_revision: The latest revision returned by wo_demo_view.
        :param changes: Only changed fields as strings: corporation, site, shop, line, process, query, equipment_id, title, type (점검/수리), priority (일반/긴급), description. Use returned filter values and equipment IDs. title <=100 chars; description <=2500. SHOP > LINE > PROCESS. Empty filter clears it and descendants. To append text, start with the latest description. Never send HTML, code, phase or issuance requests.
        """
        if type(expected_revision) is not int or not 0 <= expected_revision <= 9007199254740991:
            return _error("invalid_revision", "화면의 현재 상태를 먼저 확인해 주세요.")
        if not isinstance(changes, dict) or not changes or any(key not in _LIMITS for key in changes):
            return _error("invalid_changes", "시연 화면에서 지원하는 입력 항목만 수정할 수 있습니다.")
        if any(not isinstance(value, str) or len(value) > _LIMITS[key] for key, value in changes.items()):
            return _error("invalid_changes", "입력값과 길이를 확인해 주세요. 제목은 100자, 요청 내용은 2,500자까지입니다.")
        if changes.get("equipment_id"):
            # Reuse the lookup business function, not a nested model/tool-routing loop.
            found = _find_demo_equipment({"equipment_id": changes["equipment_id"]})
            if found["matches_count"] != 1:
                return _error("unknown_equipment", "샘플 목록에 있는 설비 코드를 선택해 주세요.")
            equipment = found["matches"][0]
            if any(changes.get(key) and changes[key] != equipment[key] for key in _HIERARCHY):
                return _error("equipment_scope_mismatch", "선택한 설비와 법인·사업장·필터 조건이 다릅니다.")
            # An explicit ID resolves its whole path, even when only a child filter was given.
            changes = {**changes, "equipment_id": equipment["id"],
                       **{key: equipment[key] for key in _HIERARCHY}}
        return await _call("update", __event_call__, __metadata__, expected_revision=expected_revision, changes=changes)
