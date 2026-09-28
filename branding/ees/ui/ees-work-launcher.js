/* Native EES workflow: existing sidebar, real chat and shared work panel. */
(() => {
  'use strict';
  if (window.__eesNativeWork) return;
  const $ = (s, p = document) => p.querySelector(s);
  const {categories,finished,lineage:workLineage} = workUI;
  let state = null, generation = 0, request = 0, busy = false, scheduled = false;
  let lastRoute = '', acceptedRoute = '', identity = '', pendingId = '', pendingSubmitted = false;
  let category = 'setup', browsingSystem = 'EMS', browsingSite = '', newCase = false, previewVersion = 0;
  let browseActive = false, browseNodeId = '', runView = 'current', historyCase = null, historyRequest = 0, navigationRequest = 0;
  let desiredCase = '', desiredNode = '', reopenPanel = false, navigationTarget = '';
  const scopeSelections = new Map(), chosenCases = new Map(), draftSnapshots = new Map(), creationTickets = new Map(), createdChats = new Map();
  const previewChats = new Map(), actionRequests = new Map();
  const heldWorkKeys = new Set();
  let actionSerial=0;
  let creationSerial=0;
  let visibleDraftKey='general', draftTarget=null, draftTimer=null, draftSerial=0;
  let errorMessage = '', recordLookupError = null, historyLookupError = null, activeRegistration = null;
  let personalSettingsOpened=false;
  let scopeReadinessTimer=null;
  let execution=null,executionError='',executionTimer=null,executionSerial=0,historyExecution=null;
  const executionStarts=new Map();
  const token = () => {try {return localStorage.getItem('token') || '';} catch (_) {return '';}};
  const chatId = () => {const m = location.pathname.match(/^\/c\/([^/]+)\/?$/); return m ? decodeURIComponent(m[1]) : '';};
  const authoringRoute = () => (location.pathname==='/'||location.pathname.startsWith('/workspace')) && new URLSearchParams(location.search).get('ees')==='workflow';
  const chatRoute = () => !authoringRoute()&&(location.pathname === '/' || /^\/c\/[^/]+\/?$/.test(location.pathname));
  const adminRoute = authoringRoute;
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
  const view = createWorkView({callbacks:{scopeReady,registerPanel,selectWork,switchScope,startCase,showHistory,saveInputs,saveDocument,runJob,executionRefresh:retryExecutionRead,executionControl,
    openCase:id=>openCase(state?.cases.find(c=>c.id===id)),
    selectCategory:async wanted=>{category=wanted;const first=visibleRoots(category)[0];if(first)await selectWork(first);else renderNavigator();},
    showHistoryView:show=>{resetHistory();runView=show?'history':'current';renderPanel();},
    closePanel:()=>window.__eesWorkPanelV1?.close(chatId()),
    selectPanel:screen=>window.__eesWorkPanelV1?.select(chatId(),screen,{open:true})
  }});
  const designer = createWorkDesigner({callbacks:{
    authoringModels,authoringReply,authoringRead:path=>authoringAPI(path),authoringWrite:(body,path='authoring/action')=>authoringAPI(path,body)
  }});
  function snapshot() {
    // Each successful read only validates its own current or historical case.
    // Opening a tab must never turn a failed current read into fresh evidence.
    const lookupError=runView==='history'?(historyCase?historyLookupError:historyLookupError || recordLookupError):recordLookupError;
    return {state,category,browsingSystem,browsingSite,browseNodeId,browseActive,runView,historyCase,errorMessage,recordLookupError:lookupError,busy,
      chatId:chatId(),chatRoute:chatRoute(),adminRoute:adminRoute(),acceptedRoute,execution:execution?.run?.case_id===selectedCase()?.id?execution:null,executionError:selectedCase()?executionError:'',historyExecution,
      selectedCaseId:selectedCase()?.id || '',selectedId:selectedId(),processId:processId(),
      roots:Object.fromEntries(Object.keys(categories).map(group=>[group,visibleRoots(group)])),
      chosenCases:Object.fromEntries(Object.keys(categories).flatMap(group=>visibleRoots(group).map(id=>[id,chosenCase(id)?.id || ''])))};
  }
  function renderView() {view.render(snapshot());}
  function renderNavigator() {view.renderNavigator(snapshot());}
  function renderPanel() {view.renderPanel(snapshot());}
  function renderDesigner() {designer.render(snapshot());}
  function setBusy() {view.setBusy(busy);designer.setBusy(busy);}
  function clearScopeReadinessWait() {clearTimeout(scopeReadinessTimer);scopeReadinessTimer=null;}
  function updateScopeReadiness() {
    view.updateScopeReadiness();clearScopeReadinessWait();
    const route=location.pathname+location.search;
    if(!state||!chatRoute()||acceptedRoute!==route||lastRoute!==route||window.__eesNativeDraftV1?.ready())return;
    // Native draft stores can finish loading without another DOM mutation.
    // Recheck only this pending route, stopping as soon as its editor is ready.
    const at=generation,auth=token();
    scopeReadinessTimer=setTimeout(()=>{scopeReadinessTimer=null;if(at===generation&&auth===token()&&route===location.pathname+location.search&&available())schedule();},50);
  }
  function openPanel() {view.prepare(snapshot());view.openPanel();}
  function revealSelection(id,data,run,includeSelf=false) {view.revealSelection(id,data,run,includeSelf,{site:browsingSite,system:browsingSystem});}
  async function api(path, body) {
    const headers = {'Accept':'application/json'};
    const access = token(); if (access) headers.Authorization = 'Bearer ' + access;
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/ees-work/' + path, {method:body ? 'POST' : 'GET',credentials:'same-origin',cache:'no-store',headers,...(body ? {body:JSON.stringify(body)} : {})});
    let result;try{result=await response.json();}catch(_){const failure=new Error('업무 정보를 가져오지 못했습니다. 배포 상태를 확인해 주세요.');failure.status=response.status;throw failure;}
    if (!response.ok || result?.ok === false) {const failure=new Error(result?.error?.message || result?.detail?.message || '업무 정보를 가져오지 못했습니다. 로그인과 배포 상태를 확인해 주세요.');failure.result=result;failure.status=response.status;failure.code=result?.error?.code || result?.detail?.code;throw failure;}
    return result;
  }
  async function authoringAPI(path,body){
    const auth=token(),at=generation,route=location.pathname+location.search;
    try{const result=await api(path,body);if(auth!==token()||at!==generation||route!==location.pathname+location.search||!available())return null;return result;}
    catch(error){if(auth!==token()||at!==generation||route!==location.pathname+location.search||!available())return null;throw error;}
  }
  function lookupFailure(error) {
    // Only read callers use this state. A rejected action is not evidence that
    // stored records are absent or unreadable; ambiguous not-found stays failed.
    const restricted=error.status===403 || ['chat_forbidden','admin_required'].includes(error.code);
    return {kind:restricted?'restricted':'failed',message:restricted?'이 기록에 접근할 권한이 없습니다.':'기록을 조회하지 못했습니다. 다시 조회해 주세요.'};
  }
  async function authoringModels() {
    const headers={Accept:'application/json',Authorization:'Bearer '+token()},options={credentials:'same-origin',cache:'no-store',headers};
    const [response,settings]=await Promise.all([fetch('/api/models',options),fetch('/api/v1/users/user/settings',options).then(r=>r.ok?r.json():{}).catch(()=>({}))]);
    if(!response.ok)throw new Error('models_unavailable');
    const result=await response.json();
    return {models:(result.data || []).filter(model=>typeof model.id==='string'&&model.id&&!model.direct&&model.type!=='embedding').map(model=>({id:model.id,name:model.name || model.id})),preferred:Array.isArray(settings.ui?.models)?settings.ui.models:[]};
  }
  async function authoringReply({model,messages,signal}) {
    const controller=new AbortController(),abort=()=>controller.abort();signal.addEventListener('abort',abort,{once:true});
    const timeout=setTimeout(abort,90000),auth=token();
    try {
      if(signal.aborted||!designer.canAuthor()||!authoringRoute())throw new Error('작성 요청을 중단했습니다. 현재 초안은 그대로입니다.');
      // Use the existing authenticated model path without chat creation or tool resolution.
      // The pinned middleware explicitly treats tools: [] as opting out of builtins.
      const response=await fetch('/api/chat/completions',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json',Authorization:'Bearer '+auth},signal:controller.signal,body:JSON.stringify({model,messages,stream:false,tools:[],tool_ids:[],features:{}})});
      if(!response.ok)throw new Error('답변을 받지 못했습니다. 기존 모델 연결과 권한을 확인해 주세요.');
      let text='';
      if((response.headers.get('content-type') || '').includes('text/event-stream')){
        const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',complete=false;
        while(true){const {done,value}=await reader.read();buffer=(buffer+decoder.decode(value || new Uint8Array(),{stream:!done})).replace(/\r\n/g,'\n');let end;
          while((end=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,end);buffer=buffer.slice(end+2);const data=frame.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');if(!data)continue;if(data==='[DONE]'){complete=true;continue;}const chunk=JSON.parse(data);if(chunk.error)throw new Error('모델 응답이 중단됐습니다. 현재 초안은 그대로입니다.');const choice=chunk.choices?.[0];if(choice?.delta?.tool_calls||choice?.message?.tool_calls)throw new Error('도구 실행 응답은 이 작성 영역에서 사용할 수 없습니다.');text+=choice?.delta?.content || choice?.message?.content || '';if(choice?.finish_reason)complete=true;}
          if(text.length+buffer.length>48000)throw new Error('답변이 너무 깁니다. 수정할 안내를 나누어 요청해 주세요.');
          if(done)break;
        }
        if(!complete)throw new Error('모델 응답이 끝나기 전에 연결이 종료됐습니다. 초안은 그대로입니다.');
      }else{
        const result=await response.json(),message=result.choices?.[0]?.message;
        if(message?.tool_calls?.length)throw new Error('도구 실행 응답은 이 작성 영역에서 사용할 수 없습니다.');
        text=message?.content;
      }
      if(auth!==token()||signal.aborted)throw new Error('작성 요청을 중단했습니다. 현재 초안은 그대로입니다.');
      if(typeof text!=='string'||!text.trim()||text.length>48000)throw new Error('답변을 읽지 못했습니다. 현재 초안은 그대로입니다.');
      return text;
    }catch(error){if(controller.signal.aborted)throw new Error(signal.aborted?'작성을 중단했습니다.':'응답 대기 시간이 지났습니다. 현재 초안은 그대로입니다.');throw error;}
    finally{clearTimeout(timeout);signal.removeEventListener('abort',abort);}
  }
  function accept(result) {
    const previousCase=state?.case?.id,firstForRoute=acceptedRoute!==location.pathname+location.search;state = result;recordLookupError=null;acceptedRoute=location.pathname+location.search;
    if(state.case){browseActive=true;if(chatId())previewChats.delete(chatId());}
    if(state.case&&state.case.id!==previousCase){browsingSite=state.case.site.id;browsingSystem=state.case.system;category=state.case.definition.nodes[state.case.process_id]?.category || 'setup';browseNodeId=state.case.selected_id;newCase=false;chosenCases.set(caseKey(state.case.process_id),state.case.id);}
    if(!state.case){const params=new URLSearchParams(location.search),saved=previewChats.get(chatId());if(saved&&saved.auth===token()){browseActive=true;browsingSite=saved.selection.site_id;browsingSystem=saved.selection.system;browseNodeId=saved.selection.node_id;previewVersion=saved.selection.version;category=state.catalog.nodes[saved.selection.process_id]?.category || category;}else if(params.has('ees_site')&&(firstForRoute||!browseActive)){browseActive=true;browsingSite=params.get('ees_site');browsingSystem=params.get('ees_system') || browsingSystem;browseNodeId=params.get('ees_node') || params.get('ees_process') || browseNodeId;const version=Number(params.get('ees_version'));if(Number.isSafeInteger(version)&&version>0)previewVersion=version;category=state.catalog.nodes[lineage(browseNodeId,state.catalog)[0]?.id]?.category || category;}if(!previewVersion)previewVersion=state.catalog.version;}
    if(!state.catalog.systems.includes(browsingSystem))browsingSystem=state.catalog.systems[0];
    if(!browsingSite || !state.catalog.sites[browsingSite])browsingSite=Object.keys(state.catalog.sites)[0] || '';
    if(!state.case){newCase=true;const roots=visibleRoots(category);if(!roots.includes(lineage(browseNodeId,state.catalog)[0]?.id))browseNodeId=roots[0] || '';if(browseActive&&previewVersion!==state.catalog.version&&!errorMessage)errorMessage='게시된 업무 절차가 변경되었습니다. 왼쪽에서 업무를 다시 선택해 새 기준을 확인해 주세요.';}
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
    try {const result = await api('state?' + query); if (at !== generation || scopeEpoch !== navigationRequest || serial !== request || auth !== token() || route !== location.pathname + location.search || !available()) return; errorMessage = ''; accept(result);await refreshExecution();await designer.refreshAuthoring();}
    catch (error) {if (at !== generation || scopeEpoch !== navigationRequest || serial !== request || auth !== token() || route !== location.pathname + location.search || !available()) return; errorMessage = error.message; recordLookupError=lookupFailure(error); render();}
  }
  async function action(actionName, payload = {}, nodeId = '', override = {}) {
    if (busy || !state) return null;
    busy = true; errorMessage = ''; setBusy();
    const at = generation, scopeEpoch=navigationRequest, active=selectedCase(), cid = active?.id || '', auth = token(), route = location.pathname + location.search;
    const isAdmin = ['save_draft','validate_draft','publish'].includes(actionName);
    const submittedDraft=isAdmin?designer.readDraft():null;
    const body = {action:actionName,chat_id:chatId(),case_id:cid,node_id:nodeId,payload,expected_revision:isAdmin ? submittedDraft.revision : (active?.revision || 0),...override};
    const firstWrite=['update_inputs','run'].includes(actionName)&&!body.case_id;
    if(firstWrite)body.scope={site_id:browsingSite,system:browsingSystem,process_id:processId(),version:previewVersion || state.catalog.version};
    if(['create','update_inputs','run'].includes(actionName)){
      // Keep the same key/body for a response-loss retry. State changes or a
      // different payload are a new intent, still checked by the server CAS.
      const key=JSON.stringify(body);if(!actionRequests.has(key))actionRequests.set(key,window.crypto?.randomUUID?.() || 'ui-'+Date.now().toString(36)+'-'+(++actionSerial)+'-'+Math.random().toString(36).slice(2));
      body.request_id=actionRequests.get(key);
    }
    try {
      const result = await api('action', body);
      if (at !== generation || scopeEpoch !== navigationRequest || auth !== token() || route !== location.pathname + location.search || !available()) return null;
      if (isAdmin && actionName !== 'validate_draft') designer.markSaved(submittedDraft.definition,result.draft_revision);
      if ((actionName === 'create'||firstWrite) && !result.case?.chat_id) pendingId = result.case?.id || '';
      if(firstWrite&&result.case)view.adoptPreviewDraft(result.case.id,nodeId);
      accept(result); return result;
    } catch (error) {if (at === generation && scopeEpoch === navigationRequest && auth===token() && route===location.pathname+location.search) {
      errorMessage = error.message;
      // A first write can create its case and then fail validation/execution.
      // Keep that exact case and the user's draft instead of creating another.
      const saved=error.result;
      if(firstWrite&&saved?.case&&saved.catalog){if(!saved.case.chat_id)pendingId=saved.case.id;view.adoptPreviewDraft(saved.case.id,nodeId);accept({...saved,ok:true});}
      else if(['case_selection_required','revision_conflict'].includes(saved?.error?.code)){await refresh();if(at===generation&&scopeEpoch===navigationRequest&&auth===token()&&route===location.pathname+location.search){errorMessage=error.message;render();if(saved.error.code==='revision_conflict')workUI.dialog({title:'저장된 업무가 먼저 변경되었습니다',html:'<p>오래된 화면의 요청으로 기존 기록을 덮어쓰지 않았습니다.</p><p>개인 대화와 작성 중인 초안은 그대로 유지했습니다. 최신 상태와 비교해 이어가세요.</p>',confirmLabel:'최신 상태 보기'}).then(accepted=>{if(accepted&&at===generation&&auth===token())refresh();});}}
      else render();
    } return null;}
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
    const serial=++historyRequest,at=generation,scopeEpoch=navigationRequest,key=caseKey(processId()),auth=token(),route=location.pathname+location.search;runView='history';historyCase=null;historyExecution=null;
    try{const result=await api('state?'+new URLSearchParams({case_id:id}));if(serial!==historyRequest||at!==generation||scopeEpoch!==navigationRequest||key!==caseKey(processId())||auth!==token()||route!==location.pathname+location.search||!available())return {ok:false};historyCase=result.case;historyLookupError=null;errorMessage='';renderPanel();openPanel();
      if(workHasExecution(result.case.definition,result.case.process_id)){const saved=await api('execution/state?'+new URLSearchParams({case_id:id}));if(serial!==historyRequest||at!==generation||scopeEpoch!==navigationRequest||key!==caseKey(processId())||auth!==token()||route!==location.pathname+location.search||!available())return {ok:false};historyExecution=saved;renderPanel();}
      return {ok:true};}
    catch(error){if(serial===historyRequest&&at===generation&&scopeEpoch===navigationRequest&&key===caseKey(processId())&&auth===token()&&route===location.pathname+location.search&&available()){errorMessage=error.message;historyLookupError=lookupFailure(error);renderPanel();}return {ok:false};}
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
    if(typeof id!=='string'||!id||!available()||!chatRoute())return {ok:false};
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
  function resetHistory() {runView='current';historyCase=null;historyExecution=null;historyRequest++;historyLookupError=null;}
  function previewRoute(id) {const values={ees_site:browsingSite,ees_system:browsingSystem,ees_process:id,ees_version:previewVersion || state?.catalog.version};if(browseNodeId&&browseNodeId!==id&&lineage(browseNodeId,state?.catalog)[0]?.id===id)values.ees_node=browseNodeId;return '/?'+new URLSearchParams(values);}
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
    newCase=true;previewVersion=state.catalog.version;errorMessage='';
    const targetDraft='scope/'+scopeKey()+'/'+p;
    if(!chatId()&&visibleDraftKey==='general'){const draft=draftSnapshots.get('general');if(draft)draftSnapshots.set(targetDraft,draft);visibleDraftKey=targetDraft;}
    else if(currentCase() || (!chatId()&&visibleDraftKey!==targetDraft)){pendingId='';pendingSubmitted=false;reopenPanel=true;navigate(previewRoute(p),targetDraft);return {ok:true};}
    if(chatId())previewChats.set(chatId(),{auth:token(),selection:publishedSelection()});
    render();openPanel();return {ok:true};
  }
  async function switchScope(site,system,process='') {
    if(!state?.catalog.sites[site]||!state.catalog.systems.includes(system))return {ok:false};
    view.closeScopePicker();
    const serial=++navigationRequest;stashDraft();rememberScope();resetHistory();browsingSite=site;browsingSystem=system;browseActive=true;newCase=true;previewVersion=state.catalog.version;view.setNavigatorOpen(true);
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
    stashDraft();const previousDraftKey=visibleDraftKey,separate=Boolean(currentCase()),result=await action('create',{site_id:browsingSite,system:browsingSystem,process_id:p,version:state.catalog.version},'',{case_id:'',chat_id:separate||!chatRoute()?'':chatId(),expected_revision:0});
    if(!result)return;
    browseActive=true;newCase=false;view.setNavigatorOpen(true);resetHistory();
    if(separate||!chatRoute()){visibleDraftKey=previousDraftKey;pendingId=result.case.id;pendingSubmitted=false;reopenPanel=true;navigate(previewRoute(p),'case/'+result.case.id);}
    else{render();openPanel();}
  }
  function canWriteEdits(id) {
    const edits=view.readJobEdits(id);
    if(edits.conflict){errorMessage='저장된 내용이 변경되었습니다. 작성 중인 값과 최신 내용을 확인해 주세요.';renderPanel();return false;}
    if(edits.nodeId&&edits.nodeId!==id){errorMessage='입력을 작성한 업무를 다시 선택해 주세요.';renderPanel();return false;}
    if(workLegacyExecutionLocked(execution,selectedCase()?.id)){errorMessage='연결 실행이 종료되기 전에는 입력·초안을 반영하거나 이 작업을 완료할 수 없습니다. 작성 중인 내용은 이 화면에 보존됩니다.';renderPanel();return false;}
    return true;
  }
  async function saveInputs(inputs,id=selectedId()) {if(!canWriteEdits(id))return null;return action('update_inputs',{inputs},id);}
  async function saveDocument(document,id=selectedId()) {
    if(!canWriteEdits(id))return null;
    const saved=selectedCase()?.node_states?.[id];
    if(saved?.applicable===false||saved?.status==='skipped'||saved?.missing?.length||saved?.block_reason==='skill_unavailable'){errorMessage='초안을 반영하려면 작업의 적용 조건·선행 작업·필수 스킬 권한을 확인해 주세요. 작성 중인 내용은 이 화면에 보존됩니다.';renderPanel();return null;}
    return action('run',{document},id);
  }
  async function executionForm(schema,values,title,extra='',confirmLabel='확인') {
    let submitted=null;
    const html='<form id="ees-runtime-input-form">'+workExecutionInputsHTML(schema,values)+'</form>'+extra;
    const promise=workUI.dialog({title,html,confirmLabel}),dialog=document.querySelector('#ees-work-dialog'),form=dialog?.querySelector('form');
    dialog?.querySelector('[data-dialog-confirm]')?.addEventListener('click',event=>{
      try {if(!form.reportValidity()){event.stopImmediatePropagation();return;}submitted=workExecutionInputsRead(form,schema);}
      catch(error){event.stopImmediatePropagation();let note=dialog.querySelector('[data-input-error]');if(!note){note=document.createElement('p');note.dataset.inputError='';note.setAttribute('role','alert');form.append(note);}note.textContent='입력 형식을 확인해 주세요. '+error.message;}
    },true);
    dialog?.querySelectorAll('[data-candidate-id]').forEach(button=>button.addEventListener('click',()=>{const input=form.elements.namedItem(button.dataset.inputKey || 'page_id');if(input){input.value=button.dataset.candidateId;input.focus();}}));
    return await promise?submitted:null;
  }
  function executionRequestId(body) {
    const key='execution:'+JSON.stringify(body);if(!actionRequests.has(key))actionRequests.set(key,window.crypto?.randomUUID?.() || 'runtime-'+Date.now().toString(36)+'-'+(++actionSerial));return actionRequests.get(key);
  }
  function retryExecutionRead() {
    if(runView==='history'&&historyCase)return showHistory(historyCase.id);
    // Revalidate the read that failed even when the execution revision is unchanged.
    return recordLookupError?refresh():refreshExecution();
  }
  async function refreshExecution() {
    clearTimeout(executionTimer);executionTimer=null;
    if(!available()||!state||!selectedCase()||!workHasExecution(definition(),processId())){execution=null;executionError='';return;}
    const at=generation,epoch=navigationRequest,auth=token(),route=location.pathname+location.search,cid=selectedCase().id,serial=++executionSerial;
    const current=()=>at===generation&&epoch===navigationRequest&&auth===token()&&route===location.pathname+location.search&&serial===executionSerial&&cid===selectedCase()?.id&&available();
    try {const result=await api('execution/state?'+new URLSearchParams({case_id:cid,chat_id:chatId()}));if(!current())return;
      const changed=result.run?.id!==execution?.run?.id||result.run?.revision!==execution?.run?.revision;
      if(changed&&!busy){const projected=await api('state?'+new URLSearchParams({case_id:cid,chat_id:chatId()}));if(!current())return;
        // The view captures unsaved inputs before replacing its server snapshot.
        // A newer selection/write must never be replaced by this polling read.
        if(projected.case?.id===cid&&projected.case.revision>=(selectedCase()?.revision || 0)){execution=result;executionError='';accept(projected);}
      }
      if(!changed||!busy){execution=result;executionError='';renderPanel();}
      if(busy||result.runs?.some(run=>['queued','running'].includes(run.status))||['queued','running'].includes(result.run?.status))executionTimer=setTimeout(()=>{executionTimer=null;if(current())refreshExecution();},1800);
    }catch(error){if(current()){executionError=error.message;renderPanel();}}
  }
  async function startExecution(id) {
    if(busy)return;const at=generation,epoch=navigationRequest,auth=token(),route=location.pathname+location.search;
    const current=()=>at===generation&&epoch===navigationRequest&&auth===token()&&route===location.pathname+location.search&&available();
    busy=true;errorMessage='';setBusy();
    try {
      const c=selectedCase(),body={node_id:id,chat_id:chatId(),inputs:{},...(c?{case_id:c.id}:{scope:{site_id:browsingSite,system:browsingSystem,process_id:processId(),version:previewVersion || state.catalog.version}})};
      let response=await api('execution/plan',body);if(!current())return;
      const plan=response.plan,limits=plan.limits?.duration_seconds?'<p>허용 실행 시간 '+Math.ceil(plan.limits.duration_seconds/60)+'분</p>':'';
      const scope='<ul>'+plan.jobs.map(jobId=>{const job=node(jobId);return '<li>'+workUI.esc(job?.name || jobId)+' · '+workUI.esc(job?.execution?.kind==='ai'?'근거 요약':job?.execution?.kind==='human'?'사람 확인':(job?.execution?.calls || []).map(call=>call.reference.function).join(', '))+'</li>';}).join('')+'</ul>';
      const expiry=typeof plan.expires_at==='number'?new Date(plan.expires_at*1000).toLocaleString():plan.expires_at || '미기록';
      const inputs=await executionForm(plan.input_schema || {},plan.inputs || {},node(id).name+' · 실행 계획','<p>대상 작업 '+plan.jobs.length+'개 · 승인 유효 시각 '+workUI.esc(expiry)+'</p>'+scope+limits+'<p>계획 확인만으로 실행되지 않습니다. 실행 시작을 선택하면 위 범위와 입력으로 접수합니다.</p><p>개인 연결은 기존 도구 설정을 사용합니다. 계정·키는 입력하지 마세요.</p>','실행 시작');
      if(!current()||inputs===null)return;
      const intent=JSON.stringify({...body,inputs});let start=executionStarts.get(intent);
      if(!start){response=await api('execution/plan',{...body,inputs});if(!current())return;const accepted=response.plan;start={action:'start',plan_id:accepted.id,plan_hash:accepted.hash,chat_id:chatId()};start.request_id=executionRequestId(start);executionStarts.set(intent,start);}
      let result;try{result=await api('execution/action',start);executionStarts.delete(intent);}
      catch(error){if(error.result?.ok===false||(error.status>=400&&error.status<500))executionStarts.delete(intent);throw error;}
      if(!current())return;
      execution={ok:true,run:result.run,runs:[result.run]};executionError='';
      if(result.run?.case_id){if(!chatId())pendingId=result.run.case_id;await refresh();}
      else renderPanel();
    }catch(error){if(current()){errorMessage=error.message;renderPanel();}}
    finally {busy=false;setBusy();}
  }
  async function executionControl(data) {
    if(busy)return;
    // A selected J/T may belong to an earlier, disjoint run in the same case.
    // Use the displayed run receipt, never the latest unrelated run.
    const run=[execution?.run,...(execution?.runs || [])].find(item=>item?.id===data.runId);
    if(recordLookupError)return refresh();
    if(executionError||!run||String(run.revision)!==data.revision)return refreshExecution();
    const at=generation,epoch=navigationRequest,auth=token(),route=location.pathname+location.search,current=()=>at===generation&&epoch===navigationRequest&&auth===token()&&route===location.pathname+location.search&&available();
    let action=data.runtimeAction,inputs;
    if(action==='inputs'){
      const candidates=(run.calls || []).flatMap(call=>call.result?.data?.results || []);
      const choices=candidates.filter(item=>item.page_id || item.id).map(item=>'<p><button type="button" data-candidate-id="'+workUI.esc(item.page_id || item.id)+'">'+workUI.esc(item.title || item.name || item.page_id || item.id)+' · '+workUI.esc(item.page_id || item.id)+'</button></p>').join('');
      inputs=await executionForm(run.input_schema || {},run.inputs || {},'실행 입력 확인','<p>입력을 반영한 뒤 이어가기를 선택해야 다음 호출이 진행됩니다. 이미 실행한 호출의 입력·결과는 변경되지 않습니다.</p>'+(candidates.length?'<details open><summary>조회된 후보 · 선택해 주세요</summary>'+choices+'<pre>'+workUI.esc(JSON.stringify(candidates,null,2))+'</pre></details>':''),'입력 반영');
      if(inputs===null||!current())return;
    }
    if(action==='confirm'&&!await workUI.dialog({title:'내용을 직접 확인하셨나요?',html:'<p>'+workUI.esc(node(data.jobId)?.rule || '등록된 완료 조건을 직접 확인해 주세요.')+'</p>',confirmLabel:'확인 완료'}))return;
    if(action==='cancel'&&!await workUI.dialog({title:'이 실행을 취소할까요?',html:'<p>다음 호출을 중지합니다. 이미 보낸 요청의 결과가 취소되었다고 판단하지 않습니다.</p>',confirmLabel:'실행 취소'}))return;
    if(!current())return;busy=true;setBusy();
    const body={action,run_id:run.id,expected_revision:run.revision,chat_id:chatId(),...(inputs?{inputs}:{}),...(data.jobId?{job_id:data.jobId}:{})};body.request_id=executionRequestId(body);
    try{const result=await api('execution/action',body);if(!current())return;execution={ok:true,run:result.run,runs:[result.run]};executionError='';await refresh();}
    catch(error){if(current()){errorMessage=error.message;await refreshExecution();renderPanel();}}
    finally{busy=false;setBusy();}
  }
  async function runJob(id,activation=null) {
    // A second click in the save gesture is not a separate execution intent.
    if(activation?.detail>1)return;
    const n=node(id);if(!n)return;
    if(workHasExecution(definition(),id)){await startExecution(id);return;}
    if(n.type==='j'){
      if(!canWriteEdits(id))return;
      const edits=view.readJobEdits(id);
      if(edits.inputsChanged||edits.documentChanged){errorMessage='작성한 입력이나 초안을 먼저 반영한 뒤 진행해 주세요.';renderPanel();return;}
      if(['manual','draft'].includes(n.mode)&&!confirm(`${n.name || '선택한 업무'}\n${n.rule || '등록된 완료 조건을 직접 확인해 주세요.'}\n\n직접 확인한 내용으로 완료를 기록할까요?`))return;
    }
    await action('run',n.type!=='j'?{retry_failed:false}:n.mode==='manual'||n.mode==='draft'?{confirm:true}:{},id);
  }
  async function editAction(name) {
    const draft=designer.readDraft();
    if(name==='save_draft'){await action(name,{definition:draft.definition});return;}
    if(draft.dirty){errorMessage='변경한 초안을 먼저 저장해 주세요.';renderDesigner();return;}
    if(name==='publish'&&!await designer.confirmPublish())return;
    await action(name);
  }
  function render() {renderView();renderDesigner();updateScopeReadiness();}
  function cleanup() {
    clearScopeReadinessWait();clearTimeout(executionTimer);executionTimer=null;execution=null;executionError='';executionSerial++;executionStarts.clear();
    personalSettingsOpened=false;$('#ees-personal-settings-guide')?.remove();
    generation++;request++;state=null;acceptedRoute='';pendingId='';pendingSubmitted=false;browseActive=false;previewVersion=0;scopeSelections.clear();chosenCases.clear();draftSnapshots.clear();creationTickets.clear();createdChats.clear();previewChats.clear();actionRequests.clear();draftSerial++;draftTarget=null;clearTimeout(draftTimer);resetHistory();errorMessage='';recordLookupError=null;
    if(activeRegistration!==null)window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;
    view.reset();designer.reset();
  }
  function sync() {
    scheduled=false;
    const auth=token();
    if(!available()){if(state||$('#ees-work-entry'))cleanup();lastRoute='';identity=auth;return;}
    if(identity!==auth){cleanup();window.__eesWorkPanelV1?.destroy();identity=auth;lastRoute='';}
    openPersonalSettings();
    if(!window.__eesWorkPanelV1)window.__eesStartWorkPanelV1?.();
    view.prepare(snapshot());designer.prepare(snapshot());
    const path=location.pathname+location.search;
    if(lastRoute!==path){
      clearScopeReadinessWait();clearTimeout(executionTimer);executionTimer=null;execution=null;executionError='';executionSerial++;
      view.closeScopePicker();const previous=lastRoute;lastRoute=path;generation++;request++;resetHistory();
      // A first completion can arrive after another factory was previewed on
      // the root route. Its server-issued chat still belongs to the captured
      // creation ticket, not whichever case is currently being browsed.
      const created=createdChats.get(chatId());
      if(previous.split('?')[0]==='/'&&created?.auth===auth){pendingId=created.caseId || '';pendingSubmitted=true;desiredCase='';desiredNode='';reopenPanel=false;draftSerial++;draftTarget=null;clearTimeout(draftTimer);if(created.selection){previewChats.set(chatId(),{auth,selection:created.selection});createdChats.delete(chatId());}}
      if(path!==navigationTarget&&!pendingSubmitted){browseActive=false;reopenPanel=false;desiredNode='';desiredCase='';pendingId='';}navigationTarget='';
      if(activeRegistration!==null){window.__eesWorkPanelV1?.unregister(activeRegistration,'workflow');activeRegistration=null;}view.detach();
      if(!adminRoute())designer.restoreWorkspace();else{view.setNavigatorOpen(false);renderNavigator();}
      if(pendingId&&pendingSubmitted&&previous.split('?')[0]==='/'&&chatId()){ensureChat(chatId());return;}
      // A captured published selection has no pending case to bind. Its
      // one-time route transition must not keep unrelated chats in this scope.
      if(!pendingId)pendingSubmitted=false;
      state=null;recordLookupError=null;view.prepare(snapshot());designer.prepare(snapshot());refresh();return;
    }
    view.sync(snapshot());designer.sync(snapshot());updateScopeReadiness();
  }
  function openPersonalSettings() {
    if(new URLSearchParams(location.search).get('ees')!=='tool-settings'||!chatRoute()){
      personalSettingsOpened=false;$('#ees-personal-settings-guide')?.remove();return;
    }
    if(personalSettingsOpened||!window.__eesNativeDraftV1?.ready()||!$('#chat-input.ProseMirror'))return;
    // This is the pinned Native button, including its native permission check.
    // Opening Controls does not select a Tool, read a key or write UserValves.
    const control=$('nav button[aria-label="Controls"]');if(!control)return;
    personalSettingsOpened=true;
    const pane=$('#controls-container'),bounds=pane?.getBoundingClientRect();
    if(!bounds||bounds.width<40||bounds.height<40)control.click();
    const guide=document.createElement('p');guide.id='ees-personal-settings-guide';guide.setAttribute('role','status');
    guide.textContent='개인 도구 설정: Controls의 Valves(밸브)에서 도구를 선택하세요. 권한과 도구에 따라 설정 항목이 다릅니다. 업무 초안은 원래 탭에 보존됩니다.';
    const host=$('#controls-container') || control.closest('nav');host?.prepend(guide);
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(sync);}}
  function publishedSelection() {return {site_id:browsingSite,system:browsingSystem,process_id:processId(),node_id:selectedId(),version:previewVersion || state?.catalog.version};}
  function selection(id) {
    if(typeof id!=='string'||id!==chatId()||!available()||!chatRoute())return {ok:false,code:'selection_unconfirmed'};
    // The native first-message hook captures a preview before its new chat
    // route exists. Reading that capture never creates or binds a work case.
    if(!state||acceptedRoute!==location.pathname+location.search){const saved=previewChats.get(id);if(saved?.auth===token())return {ok:true,kind:'published',selection:{...saved.selection}};const created=createdChats.get(id);if(created?.auth===token()&&created.caseId)return {ok:true,kind:'case',case_id:created.caseId,node_id:created.nodeId,revision:created.revision};return {ok:false,code:'selection_unconfirmed'};}
    if(runView==='history')return historyCase?{ok:true,kind:'history',case_id:historyCase.id,node_id:historyCase.process_id,revision:historyCase.revision}:{ok:false,code:'selection_required'};
    if(!browseActive||!selectedId())return {ok:true,kind:'none'};
    const c=selectedCase();return c?{ok:true,kind:'case',case_id:c.id,node_id:selectedId(),revision:c.revision}:{ok:true,kind:'published',selection:publishedSelection()};
  }
  function beginChatCreation() {
    if(!chatRoute())return '';
    if(location.pathname!=='/'||!available()||!browseActive||!state)return null;
    const c=selectedCase();if(c&&c.id!==pendingId)return null;
    const ticket=String(++creationSerial);creationTickets.set(ticket,{caseId:c?pendingId:'',nodeId:c?.selected_id,revision:c?.revision,selection:c?null:publishedSelection(),auth:token(),route:location.pathname+location.search});return ticket;
  }
  function finishChatCreation(ticket,id) {
    const record=creationTickets.get(ticket);creationTickets.delete(ticket);
    if(!record||typeof id!=='string'||!id||record.auth!==token()||!available())return;
    record.resume=record.route!==location.pathname+location.search||Boolean(record.caseId&&currentCase()?.id!==record.caseId);
    createdChats.set(id,record);
    if(record.selection)previewChats.set(id,{auth:record.auth,selection:record.selection});
    if(record.selection||pendingId===record.caseId){pendingSubmitted=true;schedule();}
  }
  // The controller is the only owner of global listeners and route observation.
  function handleEvent(event) {
    if(event.type==='keyup')heldWorkKeys.delete(event.key);
    if(event.type==='keydown'&&['Enter',' ','Spacebar'].includes(event.key)){
      const target=event.target;
      const workControl=target.closest?.('#ees-work-panel button[data-mutation]') ||
        event.key==='Enter'&&target.closest?.('#ees-work-inputs');
      // A render can remove the focused save control while Enter is held.
      // Keep consuming its repeats until release, including when focus is body.
      if(event.repeat&&(workControl||heldWorkKeys.has(event.key))){event.preventDefault();event.stopImmediatePropagation();return;}
      if(workControl)heldWorkKeys.add(event.key);
    }
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
  window.addEventListener('blur',()=>heldWorkKeys.clear());
  document.addEventListener('keydown',handleEvent);
  window.addEventListener('ees-work-changed',async event=>{const detail=event.detail||{};if(detail.chat_id!==undefined&&detail.chat_id!==chatId())return;const at=generation;await refresh();if(at===generation&&detail.open_requested)openPanel();});
  window.addEventListener('popstate',schedule);window.navigation?.addEventListener('navigatesuccess',schedule);
  window.addEventListener('storage',schedule);window.addEventListener('resize',handleEvent);
  const observer=new MutationObserver(schedule);observer.observe(document.documentElement,{childList:true,subtree:true});
  window.__eesNativeWork= true;
  window.__eesNativeWorkV1={ensureChat,beginChatCreation,finishChatCreation,selection,refresh,open:openPanel,display:async(id,options)=>{
    if(typeof id!=='string'||id!==chatId()||!available()||!state||!options||typeof options!=='object'||Array.isArray(options))return {ok:false};
    if(Object.keys(options).some(key=>!['panel_open','navigator_open','pinned','category','system','site_id','process_id','node_id','case_id','history_open','history_case_id','workspace'].includes(key)))return {ok:false};
    if(['panel_open','navigator_open','pinned','workspace','history_open'].some(key=>key in options&&typeof options[key]!=='boolean'))return {ok:false};
    if('category' in options&&!Object.hasOwn(categories,options.category))return {ok:false};
    if('system' in options&&!state.catalog.systems.includes(options.system))return {ok:false};
    if('site_id' in options&&!state.catalog.sites[options.site_id])return {ok:false};
    if('process_id' in options&&state.catalog.nodes[options.process_id]?.type!=='p')return {ok:false};
    if('node_id' in options&&typeof options.node_id!=='string')return {ok:false};
    if(options.node_id&&!node(options.node_id)&&!state.catalog.nodes[options.node_id])return {ok:false};
    if(options.node_id&&options.process_id&&lineage(options.node_id,state.catalog)[0]?.id!==options.process_id)return {ok:false};
    if(options.workspace){if(!designer.canAuthor())return {ok:false};navigate('/?ees=workflow');return {ok:true};}
    if(options.history_case_id)return showHistory(options.history_case_id);
    if(options.case_id){const c=state.cases.find(c=>c.id===options.case_id);if(!c)return {ok:false};browsingSite=c.site.id;browsingSystem=c.system;return openCase(c);}
    if('category' in options)category=options.category;
    if(options.site_id||options.system){return switchScope(options.site_id || browsingSite,options.system || browsingSystem,options.node_id || options.process_id || '');}
    if(options.node_id||options.process_id)await selectWork(options.node_id || options.process_id,options.process_id || '');
    if('navigator_open' in options)view.setNavigatorOpen(options.navigator_open);
    if('history_open' in options){resetHistory();runView=options.history_open?'history':'current';renderPanel();openPanel();}
    renderNavigator();
    if(options.panel_open===true){browseActive=true;openPanel();}
    else if(options.panel_open===false)window.__eesWorkPanelV1?.close(id);
    return {ok:true};
  }};

  schedule();
})();
