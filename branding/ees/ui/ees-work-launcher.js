/* Native EES workflow: existing sidebar, real chat and shared work panel. */
(() => {
  'use strict';
  if (window.__eesNativeWork) return;
  const $ = (s, p = document) => p.querySelector(s);
  const {categories,finished,lineage:workLineage} = workUI;
  let state = null, generation = 0, request = 0, busy = false, scheduled = false;
  let lastRoute = '', acceptedRoute = '', identity = '', pendingId = '', pendingSubmitted = false;
  let category = 'setup', browsingSystem = 'EMS', browsingSite = '', newCase = false;
  let browseActive = false, browseNodeId = '', runView = 'current', historyCase = null, historyRequest = 0, navigationRequest = 0;
  let desiredCase = '', desiredNode = '', reopenPanel = false, navigationTarget = '';
  const scopeSelections = new Map(), chosenCases = new Map(), draftSnapshots = new Map(), creationTickets = new Map(), createdChats = new Map();
  let creationSerial=0;
  let visibleDraftKey='general', draftTarget=null, draftTimer=null, draftSerial=0;
  let errorMessage = '', activeRegistration = null;
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
  const lineage = (id, data = definition()) => workLineage(id,data);
  const scopeKey = () => browsingSite + '/' + browsingSystem;
  const caseKey = id => scopeKey() + '/' + id;
  const processId = () => lineage(selectedId())[0]?.id || (state?.catalog?.roots?.[category] || [])[0] || '';
  const scopeCases = id => (state?.cases || []).filter(c => c.site?.id === browsingSite && c.system === browsingSystem && (!id || c.process_id === id));
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
  const scopeReady = () => Boolean(state&&acceptedRoute===location.pathname+location.search&&lastRoute===acceptedRoute&&(!chatRoute()||window.__eesNativeDraftV1?.ready()));
  const view = createWorkView({callbacks:{scopeReady,registerPanel,selectWork,switchScope,startCase,showHistory,saveInputs,saveDocument,runJob,
    openCase:id=>openCase(state?.cases.find(c=>c.id===id)),
    selectCategory:async wanted=>{category=wanted;const first=visibleRoots(category)[0];if(first)await selectWork(first);else renderNavigator();},
    showHistoryView:show=>{resetHistory();runView=show?'history':'current';renderPanel();},
    closePanel:()=>window.__eesWorkPanelV1?.close(chatId()),
    selectPanel:screen=>window.__eesWorkPanelV1?.select(chatId(),screen,{open:true})
  }});
  const designer = createWorkDesigner({callbacks:{
    save_draft:()=>editAction('save_draft'),validate_draft:()=>editAction('validate_draft'),publish:()=>editAction('publish')
  }});
  function snapshot() {
    return {state,category,browsingSystem,browsingSite,browseNodeId,browseActive,runView,historyCase,errorMessage,busy,
      chatId:chatId(),chatRoute:chatRoute(),adminRoute:adminRoute(),acceptedRoute,
      selectedCaseId:selectedCase()?.id || '',selectedId:selectedId(),processId:processId(),
      roots:Object.fromEntries(Object.keys(categories).map(group=>[group,visibleRoots(group)])),
      chosenCases:Object.fromEntries(Object.keys(categories).flatMap(group=>visibleRoots(group).map(id=>[id,chosenCase(id)?.id || ''])))};
  }
  function renderView() {view.render(snapshot());}
  function renderNavigator() {view.renderNavigator(snapshot());}
  function renderPanel() {view.renderPanel(snapshot());}
  function renderDesigner() {designer.render(snapshot());}
  function setBusy() {view.setBusy(busy);designer.setBusy(busy);}
  function updateScopeReadiness() {view.updateScopeReadiness();}
  function openPanel() {view.prepare(snapshot());view.openPanel();}
  function revealSelection(id,data,run,includeSelf=false) {view.revealSelection(id,data,run,includeSelf,{site:browsingSite,system:browsingSystem});}
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
    const previousCase=state?.case?.id;state = result;acceptedRoute=location.pathname+location.search;
    if(state.case)browseActive=true;
    if(state.case&&state.case.id!==previousCase){browsingSite=state.case.site.id;browsingSystem=state.case.system;category=state.case.definition.nodes[state.case.process_id]?.category || 'setup';browseNodeId=state.case.selected_id;newCase=false;chosenCases.set(caseKey(state.case.process_id),state.case.id);}
    if(!state.case){const params=new URLSearchParams(location.search);if(params.has('ees_site')){browseActive=true;browsingSite=params.get('ees_site');browsingSystem=params.get('ees_system') || browsingSystem;browseNodeId=params.get('ees_process') || browseNodeId;category=state.catalog.nodes[browseNodeId]?.category || category;}}
    if(!state.catalog.systems.includes(browsingSystem))browsingSystem=state.catalog.systems[0];
    if(!browsingSite || !state.catalog.sites[browsingSite])browsingSite=Object.keys(state.catalog.sites)[0] || '';
    if(!state.case){newCase=true;const roots=visibleRoots(category);if(!roots.includes(lineage(browseNodeId,state.catalog)[0]?.id))browseNodeId=roots[0] || '';}
    designer.acceptServer(state);
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
    const body = {action:actionName,chat_id:chatId(),case_id:cid,node_id:nodeId,payload,expected_revision:isAdmin ? designer.readDraft().revision : (currentCase()?.revision || 0),...override};
    try {
      const result = await api('action', body);
      if (at !== generation || scopeEpoch !== navigationRequest || auth !== token() || route !== location.pathname + location.search || !available()) return null;
      if (isAdmin && actionName !== 'validate_draft') designer.markSaved();
      if (actionName === 'create' && !result.case?.chat_id) pendingId = result.case?.id || '';
      accept(result); return result;
    } catch (error) {if (at === generation && scopeEpoch === navigationRequest) {errorMessage = error.message; render();} return null;}
    finally {busy = false; setBusy();if(scopeEpoch!==navigationRequest&&available()&&auth===token())refresh();}
  }
  function registerPanel() {
    const manager=window.__eesWorkPanelV1,id=chatId();
    if(!chatRoute()||!selectedId()||!state||!manager)return;
    if(activeRegistration!==id||!manager.available(id,'workflow')){
      if(activeRegistration!==null)manager.unregister(activeRegistration,'workflow');
      activeRegistration=id;manager.register(id,view.panelRegistration());
    }
    manager.sync();
  }
  async function showHistory(id) {
    if(!scopeCases(processId()).some(c=>c.id===id))return {ok:false};
    const serial=++historyRequest,at=generation,key=caseKey(processId()),auth=token();runView='history';historyCase=null;
    try{const result=await api('state?'+new URLSearchParams({case_id:id}));if(serial!==historyRequest||at!==generation||key!==caseKey(processId())||auth!==token())return {ok:false};historyCase=result.case;renderPanel();openPanel();return {ok:true};}
    catch(error){if(serial===historyRequest&&at===generation){errorMessage=error.message;renderPanel();}return {ok:false};}
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
      if(serial===draftSerial){visibleDraftKey=target.key;draftTarget=null;updateScopeReadiness();}
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
    if(!state)return {ok:false};navigationRequest++;stashDraft();resetHistory();browseActive=true;view.setNavigatorOpen(true);
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
    view.closeScopePicker();
    const serial=++navigationRequest;stashDraft();rememberScope();resetHistory();browsingSite=site;browsingSystem=system;browseActive=true;newCase=true;view.setNavigatorOpen(true);
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
    browseActive=true;newCase=false;view.setNavigatorOpen(true);resetHistory();
    if(separate||!chatRoute()){visibleDraftKey=previousDraftKey;pendingId=result.case.id;pendingSubmitted=false;reopenPanel=true;navigate(previewRoute(p),'case/'+result.case.id);}
    else{render();openPanel();}
  }
  async function saveInputs(inputs) {return action('update_inputs',{inputs},currentCase().selected_id);}
  async function saveDocument(document) {return action('run',{document},currentCase().selected_id);}
  async function runJob(id) {
    const n=node(id),edits=view.readJobEdits();
    if(edits.inputs&&edits.inputsChanged){if(!await action('update_inputs',{inputs:edits.inputs},n.id))return;}
    if(n?.mode==='draft'&&edits.document!==null&&edits.document!==currentCase().jobs[n.id]?.document){if(!await action('run',{document:edits.document},n.id))return;}
    await action('run',n?.mode==='manual'||n?.mode==='draft'?{confirm:true}:{},id);
  }
  async function editAction(name) {
    const draft=designer.readDraft();
    if(name==='save_draft'){await action(name,{definition:draft.definition});return;}
    if(draft.dirty){errorMessage='변경한 초안을 먼저 저장해 주세요.';renderDesigner();return;}
    if(name==='publish'&&!confirm('이 초안을 게시할까요? 새 진행 건부터 적용되며 기존 진행 건의 절차와 결과는 유지됩니다.'))return;
    await action(name);
  }
  function render() {renderView();renderDesigner();}
  function cleanup() {
    generation++;request++;state=null;acceptedRoute='';pendingId='';pendingSubmitted=false;browseActive=false;scopeSelections.clear();chosenCases.clear();draftSnapshots.clear();creationTickets.clear();createdChats.clear();draftSerial++;draftTarget=null;clearTimeout(draftTimer);resetHistory();errorMessage='';
    if(activeRegistration!==null)window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;
    view.reset();designer.reset();
  }
  function sync() {
    scheduled=false;
    const auth=token();
    if(!available()){if(state||$('#ees-work-entry'))cleanup();lastRoute='';identity=auth;return;}
    if(identity!==auth){cleanup();window.__eesWorkPanelV1?.destroy();identity=auth;lastRoute='';}
    if(!window.__eesWorkPanelV1)window.__eesStartWorkPanelV1?.();
    view.prepare(snapshot());designer.prepare(snapshot());
    const path=location.pathname+location.search;
    if(lastRoute!==path){
      view.closeScopePicker();const previous=lastRoute;lastRoute=path;generation++;request++;resetHistory();
      // A first completion can arrive after another factory was previewed on
      // the root route. Its server-issued chat still belongs to the captured
      // creation ticket, not whichever case is currently being browsed.
      const created=createdChats.get(chatId());
      if(previous.split('?')[0]==='/'&&created?.auth===auth){pendingId=created.caseId;pendingSubmitted=true;desiredCase='';desiredNode='';reopenPanel=false;draftSerial++;draftTarget=null;clearTimeout(draftTimer);}
      if(path!==navigationTarget&&!pendingSubmitted){browseActive=false;reopenPanel=false;desiredNode='';desiredCase='';pendingId='';}navigationTarget='';
      if(activeRegistration!==null){window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;}view.detach();
      if(!adminRoute())designer.restoreWorkspace();else{view.setNavigatorOpen(false);renderNavigator();}
      if(pendingId&&pendingSubmitted&&previous.split('?')[0]==='/'&&chatId()){ensureChat(chatId());return;}
      state=null;view.prepare(snapshot());designer.prepare(snapshot());refresh();return;
    }
    view.sync(snapshot());designer.sync(snapshot());
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
  // The controller is the only owner of global listeners and route observation.
  function handleEvent(event) {
    const result=designer.handleEvent(event);
    const outcome=result.handled?result:view.handleEvent(event);
    if(outcome.preventDefault)event.preventDefault();
    if(outcome.handled){
      if(event.type==='keydown'||event.type==='keyup')event.stopImmediatePropagation();
      else if(event.type==='click'||event.type==='submit')event.stopPropagation();
    }
  }
  document.addEventListener('click',handleEvent,true);document.addEventListener('submit',handleEvent,true);
  for(const kind of ['input','change','focusin','pointermove','pointerup','pointercancel','lostpointercapture'])document.addEventListener(kind,handleEvent);
  document.addEventListener('pointerdown',handleEvent,true);document.addEventListener('scroll',handleEvent,true);
  // Picker activation is captured before the native global composer keys.
  window.addEventListener('keydown',handleEvent,true);window.addEventListener('keyup',handleEvent,true);
  document.addEventListener('keydown',handleEvent);
  window.addEventListener('ees-work-changed',async event=>{const detail=event.detail||{};if(detail.chat_id!==undefined&&detail.chat_id!==chatId())return;const at=generation;await refresh();if(at===generation&&detail.open_requested)openPanel();});
  window.addEventListener('popstate',schedule);window.navigation?.addEventListener('navigatesuccess',schedule);
  window.addEventListener('storage',schedule);window.addEventListener('resize',handleEvent);
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
    if('navigator_open' in options)view.setNavigatorOpen(options.navigator_open);
    if('history_open' in options){resetHistory();runView=options.history_open?'history':'current';renderPanel();openPanel();}
    renderNavigator();
    if(options.panel_open===true){browseActive=true;openPanel();}
    else if(options.panel_open===false)window.__eesWorkPanelV1?.close(id);
    return {ok:true};
  }};

  schedule();
})();
