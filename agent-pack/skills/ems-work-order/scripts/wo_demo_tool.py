"""
title: EES WO Demo
description: Sample equipment selection and WO drafting beside the existing chat. No EMS connection or real issuance.
version: 0.1.0
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
      <div class="heading"><h2>설비 WO</h2><span class="badge">시연용</span><span id="stage" class="badge" role="status">발행 전</span></div>
    </div>
    <button id="close" class="close" type="button" aria-label="설비 WO 패널 닫기">닫기</button>
  </header>

  <p class="intro">대화로 요청하거나 이 화면에서 직접 선택·수정할 수 있어요.</p>
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
    </div>
    <p id="count" class="result-count" role="status" aria-live="polite">시연용 설비를 불러오는 중이에요.</p>
    <div id="results" class="equipment-list" aria-label="설비 검색 결과"></div>
  </section>

  <div id="selected" class="selected-equipment" role="status" hidden></div>
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
try {
  const fail = (code, message) => ({ok: false, demo: true, error: {code, message}});
  if (location.pathname !== '/c/' + encodeURIComponent(request.chat_id)) {
    if (window.__eesWODemoV1) window.__eesWODemoV1.destroy();
    return fail('regular_chat_required', '시연은 일반 대화에서 사용할 수 있습니다. 임시 대화나 노트 대신 일반 대화에서 요청해 주세요.');
  }
  const anchor = document.querySelector('#chat-container #chat-pane');
  const column = anchor && anchor.parentElement;
  const row = column && column.parentElement;
  if (!row || getComputedStyle(row).display !== 'flex') {
    return fail('unsupported_layout', '이 화면에서 시연 패널을 열 수 없습니다. 일반 대화 화면과 WebUI 버전을 확인해 주세요.');
  }
  let controller = window.__eesWODemoV1;
  if (controller && (controller.chatId !== request.chat_id || !controller.alive())) {
    controller.destroy(); controller = null;
  }
  if (!controller && request.action !== 'view') {
    return fail('view_required', '먼저 시연 화면의 현재 상태를 확인해 주세요. 이전 화면의 수정 요청은 적용하지 않았습니다.');
  }
  if (!controller) {
    const hierarchy = ['corporation', 'site', 'shop', 'line', 'process'];
    const contentFields = ['title', 'type', 'priority', 'description'];
    const fieldNames = {corporation:'법인',site:'사업장',shop:'SHOP',line:'LINE',process:'PROCESS',query:'설비 검색',equipment_id:'설비',title:'작업 제목',type:'작업 구분',priority:'우선순위',description:'요청 내용'};
    const catalog = [];
    const locations = [['한국','천안','KR-CA'],['한국','울산','KR-US'],['헝가리','헝가리 사업장','HU'],['미국','미국 사업장','US']];
    const shops = [['전극',['믹싱','코팅']],['조립',['권취','조립']]];
    locations.forEach(([corporation,site,prefix]) => shops.forEach(([shop,processes], si) => {
      [1,2].forEach(n => processes.forEach((process, pi) => {
        catalog.push({id:prefix+'-'+(si+1)+n+(pi+1),name:process+' 설비 '+n+'호',corporation,site,shop,line:shop+' '+n+'라인',process});
      }));
    }));
    const state = {revision:Date.now(),phase:'edit',filters:Object.fromEntries([...hierarchy,'query'].map(k=>[k,''])),equipment_id:'',fields:{title:'',type:'점검',priority:'일반',description:''}};
    const origins = {};
    let reviewed = null, lastAI = null, visibleLimit = 8, choosing = true, note = '법인·사업장이나 설비명으로 대상 설비를 찾아보세요.';
    const mountedPath = location.pathname;
    const originalMinWidth = column.style.minWidth;
    const host = document.createElement('aside');
    host.id = 'ees-wo-demo-panel'; host.setAttribute('aria-label','설비 WO 시연');
    host.style.cssText = 'flex:0 0 min(44%,480px);width:min(44%,480px);min-width:350px;height:100%;min-height:0;overflow:auto;border-left:1px solid #8886;z-index:30;';
    const shadow = host.attachShadow({mode:'open'});
    // Only this reviewed, constant template is assigned as HTML. All data use textContent/value.
    shadow.innerHTML = panelHTML;
    const q = id => shadow.getElementById(id);
    const findEquipment = id => catalog.find(e=>e.id===id) || null;
    const path = e => [e.corporation,e.site,e.shop,e.line,e.process].join(' / ');
    const matches = filters => catalog.filter(e=>hierarchy.every(k=>!filters[k] || e[k]===filters[k]) && (!filters.query || (e.id+' '+e.name).toLowerCase().includes(filters.query.toLowerCase().trim())));
    const options = (key, filters) => [...new Set(catalog.filter(e=>hierarchy.slice(0,hierarchy.indexOf(key)).every(k=>!filters[k] || e[k]===filters[k])).map(e=>e[key]))];
    const alive = () => location.pathname === mountedPath && row.isConnected && document.querySelector('#chat-container #chat-pane') === anchor;
    const view = () => {
      const list = matches(state.filters);
      return {ok:true,demo:true,revision:state.revision,phase:state.phase,filters:{...state.filters},equipment:findEquipment(state.equipment_id),fields:{...state.fields},available_options:Object.fromEntries(hierarchy.map(k=>[k,options(k,state.filters)])),matches_count:list.length,matches:list.slice(0,8),matches_truncated:list.length>8,message:note};
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
      q('stage').textContent=complete?'발행 완료 예시':checking?'최종 확인':'발행 전';
      q('filters').hidden=complete || checking || !choosing;
      q('form').hidden=complete || checking || choosing || !state.equipment_id;
      q('choose-again').hidden=complete || checking || choosing || !state.equipment_id;
      q('review').hidden=!checking; q('result').hidden=!complete;
      hierarchy.forEach((key,index)=>{
        const select=q(key), all=document.createElement('option');all.value='';all.textContent='전체';
        select.replaceChildren(all);
        options(key,state.filters).forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option);});
        select.value=state.filters[key];select.disabled=complete || (index>0 && !state.filters[hierarchy[index-1]]);
      });
      q('query').value=state.filters.query;
      const list=matches(state.filters);q('count').textContent=list.length+'개 설비 · 샘플';
      q('results').replaceChildren();
      list.slice(0,visibleLimit).forEach(e=>{
        const button=document.createElement('button');button.type='button';button.className='equipment-option';button.dataset.equipmentId=e.id;button.setAttribute('aria-pressed',String(state.equipment_id===e.id));
        const name=document.createElement('strong'),detail=document.createElement('span');name.textContent=e.name+' · '+e.id;detail.textContent=path(e);button.append(name,detail);
        button.addEventListener('click',()=>apply({equipment_id:e.id},'user'));q('results').append(button);
      });
      if(!list.length){const empty=document.createElement('p');empty.textContent='조건에 맞는 설비가 없습니다. 필터나 검색어를 바꿔보세요.';q('results').append(empty);}
      if(list.length>visibleLimit){const more=document.createElement('button');more.type='button';more.textContent='설비 더 보기';more.addEventListener('click',()=>{visibleLimit+=8;render();});q('results').append(more);}
      const selected=findEquipment(state.equipment_id);q('selected').hidden=!selected;
      q('selected').textContent=selected?'선택 설비: '+selected.name+' · '+selected.id+' — '+path(selected):'';
      contentFields.forEach(key=>{
        q(key).value=state.fields[key];q(key).disabled=complete;
        const badge=shadow.querySelector('[data-origin-for="'+key+'"]');
        badge.textContent=origins[key]==='ai'?'AI 수정':origins[key]==='user'?'직접 수정':'';
        q(key).classList.toggle('ai-changed',origins[key]==='ai');
      });
      q('change-note').textContent=note;
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
    hierarchy.forEach(key=>q(key).addEventListener('change',()=>{const result=apply({[key]:q(key).value},'user');if(!result.ok)displayError(result.error.message);}));
    q('query').addEventListener('input',()=>apply({query:q('query').value},'user'));
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
    const resize = () => {
      if(window.innerWidth<900){host.style.position='fixed';host.style.inset='0 0 0 auto';host.style.width='min(100%,480px)';host.style.minWidth='0';host.style.zIndex='60';}
      else {host.style.position='relative';host.style.inset='auto';host.style.width='min(44%,480px)';host.style.minWidth='350px';host.style.zIndex='30';}
    };
    const theme = () => {host.style.colorScheme=document.documentElement.classList.contains('dark')?'dark':'light';};
    const observer=new MutationObserver(()=>{if(!alive())controller.destroy();});
    const themeObserver=new MutationObserver(theme);
    const open=()=>{if(!host.isConnected)row.append(host);column.style.minWidth='0';host.hidden=false;resize();theme();};
    const destroy=()=>{observer.disconnect();themeObserver.disconnect();window.removeEventListener('resize',resize);host.remove();column.style.minWidth=originalMinWidth;if(window.__eesWODemoV1===controller)delete window.__eesWODemoV1;};
    controller={chatId:request.chat_id,alive,destroy,open,view,update:(revision,changes)=>{
      if(revision!==state.revision)return {...fail('revision_conflict','사용자가 화면을 수정했습니다. 현재 값을 확인하고 요청한 부분만 다시 수정해 주세요.'),current:view()};
      const result=apply(changes,'ai');if(!result.ok)displayError(result.error.message);return result;
    }};
    window.__eesWODemoV1=controller;
    q('close').addEventListener('click',()=>{host.remove();column.style.minWidth=originalMinWidth;});
    observer.observe(document.body,{childList:true,subtree:true});themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['class']});window.addEventListener('resize',resize);
    render();open();
  }
  controller.open();
  return request.action==='view'?controller.view():controller.update(request.expected_revision,request.changes);
} catch (_) {
  return {ok:false,demo:true,error:{code:'panel_error',message:'시연 화면을 처리하지 못했습니다. 화면의 현재 내용을 확인한 뒤 다시 열어 주세요.'}};
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
    async def wo_demo_view(self, __event_call__=None, __metadata__=None) -> dict:
        """Open the SAMPLE WO side panel and read its latest form, revision, filter options and matching equipment. Use before editing, including after manual UI input. This never reads EMS or issues a WO. Keep using the existing chat; no separate mode. Follow returned options and sample equipment IDs, never invent them."""
        return await _call("view", __event_call__, __metadata__)

    async def wo_demo_update(self, expected_revision: int, changes: dict, __event_call__=None, __metadata__=None) -> dict:
        """Edit only requested fields in the SAMPLE panel, preserving other current values. Call wo_demo_view first; use its revision. On revision_conflict read current state and preserve new user input. No issuance action exists.

        :param expected_revision: The latest revision returned by wo_demo_view.
        :param changes: Only changed fields as strings: corporation, site, shop, line, process, query, equipment_id, title, type (점검/수리), priority (일반/긴급), description. Use returned filter values and equipment IDs. title <=100 chars; description <=2500. SHOP > LINE > PROCESS. Empty filter clears it and descendants. To append text, start with the latest description. Never send HTML, code, phase or issuance requests.
        """
        if type(expected_revision) is not int or not 0 <= expected_revision <= 9007199254740991:
            return _error("invalid_revision", "화면의 현재 상태를 먼저 확인해 주세요.")
        if not isinstance(changes, dict) or not changes or any(key not in _LIMITS for key in changes):
            return _error("invalid_changes", "시연 화면에서 지원하는 입력 항목만 수정할 수 있습니다.")
        if any(not isinstance(value, str) or len(value) > _LIMITS[key] for key, value in changes.items()):
            return _error("invalid_changes", "입력값과 길이를 확인해 주세요. 제목은 100자, 요청 내용은 2,500자까지입니다.")
        return await _call("update", __event_call__, __metadata__, expected_revision=expected_revision, changes=changes)
