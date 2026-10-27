/* Authenticated workspace controller. Native owns chat, attachments and models.
 * Display selection is private UI state, never a shared run mutation. */
(() => {
  'use strict';
  if(window.__eesNativeWork)return;
  const {$,clone,esc,button,dialog,closeDialog}=workUI;
  const token=()=>{try{return localStorage.getItem('token') || '';}catch(_){return '';}};
  const blankChatPath=path=>/^\/(?:folders\/[^/]+\/?)?$/.test(String(path || '').split('?')[0]);
  const chatId=()=>{const match=location.pathname.match(/^\/c\/([^/]+)\/?$/);return match?decodeURIComponent(match[1]):'';};
  const source=()=>window.__eesSourceShellV1;
  const screen=()=>source()?.screen?.() || {};
  const available=()=>Boolean(token()&&screen().active&&!screen().native&&screen().chatReady);
  let state=null,identity='',epoch=0,serial=0,busy=false,scheduled=false,error='',commandError='',route='',readyRoute='',refreshTimer=null,uiTimer=null,uiRevision=0,restored=false,initialSelectionPatch=null;
  let procedureStart=null,nativeCapabilities=null,nativeScope=null,stateKey='',targetLoading=false,scopeLoading=false,evidenceUnavailable=false;
  const workspaceCache=new Map();
  const pendingInputMessage='업무 도우미 입력 제안을 먼저 반영하거나 버려 주세요.';
  let nativeTicket=null,nativeNavigationBusy=false,pendingNativeAction=null;
  let selection={mode:'work',tab:'my_work',panel_open:true,system_id:'',factory_id:'',workflow_id:'',run_id:'',job_id:'',collapsed:[]};
  const receipts=new Map(),optionCache=new Map(),chatCreations=new Map(),chatAliases=new Map();let workEpoch=0;let referenceChat='',referenceTimer=null,referenceRead=0,messageReferences=new Map();let uiWrites=Promise.resolve(),optionTimer=null,pendingInputProposal=null,inputProposalApplied=null,reviewTimer=null,reviewSaving=null;
  const context=()=>JSON.stringify([epoch,token()===identity,location.pathname,location.search,selection.system_id,selection.factory_id,selection.workflow_id,selection.run_id,selection.job_id]);
  const view=createWorkView({callbacks:{panelWidth:width=>{if(!restored)initialSelectionPatch={...initialSelectionPatch,panel_width:width};selection.panel_width=width;remember(width);}}});
  const designer=createWorkDesigner({callbacks:{command,read,openNative,models:models,askHelp,helpState:()=>source()?.helpState?.(),startContextChanged:value=>{procedureStart=value;if(state&&available()&&chatPrepared())view.sync(snapshot());},openWorkflow:async(id,systemId)=>select({...(systemId&&systemId!==selection.system_id?{system_id:systemId,factory_id:''}:{}),workflow_id:id,run_id:'',job_id:'',mode:'author',tab:'overview'}),changed:refresh,navigate:mode=>select({mode}),operationsRead,operationsCommand,options:async body=>{const at=context();const result=await api('workspace/options',body);if(at!==context())throw new Error('작업 위치가 바뀌어 선택 목록을 적용하지 않았습니다.');return result;},resources:async()=>{const at=context();const result=await api('resources');return at===context()?result:null;}}});
  const capabilities=()=>nativeCapabilities ?? state?.capabilities;
  const nativeReturnPreview=()=>pendingNativeAction?.patch&&!pendingNativeAction.same&&pendingNativeAction.auth===token()&&pendingNativeAction.actor===actor()&&(nativePage()||pendingNativeAction.path===location.pathname+location.search)?navigationPatch(pendingNativeAction.dataset):null;
  const snapshot=()=>{const destination=nativeReturnPreview();return {state:state?{...state,input_proposal:pendingInputProposal?{values:pendingInputProposal.values,warnings:pendingInputProposal.warnings}:null,input_proposal_applied:inputProposalApplied}:null,native_capabilities:nativeCapabilities,native_scope:nativeScope,target_loading:targetLoading||Boolean(destination),scope_loading:scopeLoading,evidence_unavailable:evidenceUnavailable,selection:{...clone(selection),...(destination?{mode:destination.mode,tab:destination.tab}:{}),chat_id:chatId()},native_return_pending:Boolean(destination),native_shell:nativePage()&&!destination,native_id:nativePage()&&!destination?(workNativeTargets.find(item=>location.pathname===item.path||location.pathname.startsWith(item.path+'/'))?.id || (adminNativePage()?'admin':'native')):'',busy,error:error || commandError,procedure_start:destination?null:procedureStart};};
  // The last successful workspace remains visible during route validation.
  // References and queued actions still wait for the current route and Chat.
  const chatPrepared=()=>readyRoute===route&&(!route||route===location.pathname+location.search+'#chat')&&(!nativeTicket||nativeTicket.phase==='leaving');
  function render(){bindHosts();const value=snapshot();view.render(value);positionStageMenu();if(available()&&!value.target_loading&&!evidenceUnavailable&&!(scopeLoading&&error)&&state&&selection.mode==='author'&&selection.tab!=='workspace_admin'&&workCanCreate(capabilities()))designer.render({state:{...state,capabilities:capabilities()},scope_loading:scopeLoading,selection:{...clone(selection),chat_id:chatId()},host:view.authoringHost()});}
  function setBusy(value){busy=value;view.setBusy(value);designer.setBusy?.(value);if(value){clearTimeout(refreshTimer);refreshTimer=setTimeout(refresh,250);}}
  const adminNativePage=()=>Boolean(screen().admin);
  const nativePage=()=>Boolean(screen().native);
  const shellAvailable=()=>Boolean(token()&&screen().active&&nativePage());
  const screenAvailable=()=>available()||shellAvailable();
  const actor=()=>capabilities()?.actor_id || '';
  const nativeTicketIdentity=ticket=>ticket&&ticket===nativeTicket&&ticket.auth===token()&&ticket.auth===identity;
  const nativeTicketCurrent=ticket=>nativeTicketIdentity(ticket)&&Boolean(actor())&&ticket.actor===actor();
  function clearNativeTicket(){nativeTicket=null;}
  function nativeAnchor(path){return source()?.navigate?.(path);}
  async function openNative(id){
    const target=workNativeTargets.find(item=>item.id===id);
    if(!screenAvailable()||!actor()||!target||!workNativeAllowed(capabilities(),id))return;
    if(busy||helpWriting||reviewSaving||nativeNavigationBusy||designer.canNavigate?.()===false)throw new Error('저장 또는 화면 준비가 끝난 뒤 다시 열어 주세요. 작성 중인 내용은 유지됩니다.');
    if(nativePage()){
      if(nativeTicketCurrent(nativeTicket)){nativeTicket.target=id;nativeTicket.adminSeen=false;nativeTicket.phase='native';}
      nativeAnchor(target.path);return;
    }
    const bridge=window.__eesNativeDraftV1,at=context(),auth=token(),owner=actor();
    if(bridge?.persistent!==true||!bridge.ready?.()||typeof bridge.flush!=='function')throw new Error('대화 입력창을 준비한 뒤 다시 열어 주세요. 작성 중인 내용은 유지됩니다.');
    const draft=bridge.read();
    if(!draft||typeof draft!=='object'||Array.isArray(draft))throw new Error('작성 중인 대화 내용을 확인하지 못했습니다. 현재 화면에서 다시 시도해 주세요.');
    view.capture();designer.readDraft?.();workUI.closeHelp({restoreFocus:false});
    const navigationOperation={};nativeNavigationBusy=navigationOperation;
    try{
      if(await bridge.flush()===false)throw new Error('작성 중인 대화를 보존하지 못했습니다. 현재 화면에서 다시 시도해 주세요.');
      if(at!==context()||auth!==token()||owner!==actor()||bridge!==window.__eesNativeDraftV1||!bridge.ready())return;
      designer.readDraft?.();view.capture();
      // The Native flush owns persistence. The return ticket and authoring
      // drafts stay in this document only; no token or new draft store is written.
      nativeTicket={auth,actor:owner,boundary:chatBoundary(),path:location.pathname+location.search,target:id,name:target.name,phase:'leaving',adminSeen:false};
      nativeAnchor(target.path);
    }finally{if(nativeNavigationBusy===navigationOperation)nativeNavigationBusy=false;}
  }
  function navigationPatch(dataset){
    const action=dataset.action;
    if(action==='workspace_admin')return capabilities()?.is_admin===true?{mode:'author',tab:'workspace_admin',workflow_id:'',run_id:'',job_id:''}:null;
    if(action==='mode')return ['work','author'].includes(dataset.mode)&&(dataset.mode!=='author'||workCanWorkspace(capabilities()))?{mode:dataset.mode,tab:dataset.mode==='author'?'overview':'my_work'}:null;
    if(action==='procedures'||action==='tools')return workCanCreate(capabilities())?{mode:'author',tab:action==='tools'?'tools':'overview',workflow_id:'',run_id:'',job_id:''}:null;
    if(action==='my_work'||action==='records')return {mode:'work',tab:action,panel_open:true,job_id:'',records_workflow:''};
    if(action==='chats')return {mode:'work',tab:'chats'};
    return null;
  }
  async function returnFromNative(target){
    if(!shellAvailable()||!actor())return;
    const ticket=nativeTicketCurrent(nativeTicket)?nativeTicket:null;
    // A menu click returns through Native's route, then applies its destination.
    // Keep the exact unsaved editor when it is the section the user left.
    const action=target.dataset.action;
    const same=ticket&&(action==='mode'&&target.dataset.mode===selection.mode||
      action==='procedures'&&selection.mode==='author'&&!['tools','workspace_admin'].includes(selection.tab)||
      action==='tools'&&selection.mode==='author'&&selection.tab==='tools'||
      action==='workspace_admin'&&selection.tab==='workspace_admin');
    pendingNativeAction={auth:token(),actor:actor(),path:ticket?.path || '/',dataset:{...target.dataset},patch:navigationPatch(target.dataset),same};
    // Prepare the hidden EES panel before Native reveals it. Keep run/job keys
    // until select's review-save guard finishes; only the destination is shown.
    if(!same&&pendingNativeAction.patch)render();
    source()?.closeSettings?.();
    if(ticket)ticket.phase='returning';
    const pending=pendingNativeAction;
    try{await nativeAnchor(ticket?.path || '/');}
    catch(_){
      if(pendingNativeAction!==pending||pending.auth!==token()||pending.actor!==actor()||!nativePage())return;
      pendingNativeAction=null;
      if(nativeTicket===ticket&&ticket)ticket.phase='native';
      error='화면으로 돌아가지 못했습니다. 현재 화면에서 메뉴를 다시 눌러 주세요.';render();
    }
  }
  async function resumeNativeAction(){
    const pending=pendingNativeAction;
    if(!pending||pending.running||!available()||!chatPrepared()||nativeTicket)return;
    if(pending.auth!==token()||pending.actor!==actor()||pending.path!==location.pathname+location.search||pending.same){pendingNativeAction=null;return;}
    if(pending.applied){if(readyRoute!==route)return;pendingNativeAction=null;render();return;}
    pending.running=true;
    try{
      if(pending.patch){
        const validate=()=>pendingNativeAction===pending&&pending.auth===token()&&pending.actor===actor()&&pending.path===location.pathname+location.search&&Boolean(navigationPatch(pending.dataset));
        const patch=navigationPatch(pending.dataset);if(patch)await select(patch,{fetch:pending.dataset.action!=='chats',validate});
      }else await handleClick({dataset:pending.dataset});
    }
    finally{if(pendingNativeAction===pending){pendingNativeAction=null;render();}}
  }
  function applyNativeDestination(){
    const pending=pendingNativeAction;
    if(!pending||pending.same||pending.running||!available()||nativeTicket||pending.auth!==token()||pending.actor!==actor()||pending.path!==location.pathname+location.search)return;
    const patch=navigationPatch(pending.dataset);
    if(!patch)return;
    // Dirty reviews use the existing guarded select path after validation.
    if(state?.run?.definition?.nodes?.[selection.job_id]?.result_block==='ai_review'&&view.readReview?.().dirty)return;
    workUI.closeHelp({restoreFocus:false});designer.closeStart?.();procedureStart=null;view.capture();
    commitSelection(patch);pending.applied=true; // Keep the placeholder until fresh workspace and operations access succeed.
  }
  function resumeNativeView(ticket){
    if(!nativeTicketCurrent(ticket)||location.pathname+location.search!==ticket.path)return;
    const bridge=window.__eesNativeDraftV1;
    // Source retains the same Chat instance. Flush only supports Native reload
    // recovery; menu round trips never reimport or reconstruct its draft.
    if(!available()||bridge?.persistent!==true||!bridge.ready?.())return;
    clearNativeTicket();
  }
  function syncNativeReturn(){
    const ticket=nativeTicket;
    if(!ticket)return;
    if(!nativeTicketIdentity(ticket)||actor()&&ticket.actor!==actor()){clearNativeTicket();return;}
    // A failed capability read is not an identity change. Keep the private
    // ticket, but do not use it until the current actor is confirmed again.
    if(!actor())return;
    if(nativePage()){
      if(ticket.phase==='leaving')ticket.phase='native';
      if(adminNativePage())ticket.adminSeen=true;
      return;
    }
    if(ticket.adminSeen&&ticket.phase!=='returning'){ticket.phase='returning';nativeAnchor(ticket.path);return;}
    if(location.pathname+location.search!==ticket.path){clearNativeTicket();return;}
    if(ticket.phase==='leaving')return;
    if(ticket.phase==='native')ticket.phase='returning'; // Browser Back is also an explicit return.
    // The same SPA document kept private selection and designer state. Avoid
    // select(), whose normal work navigation deliberately closes the C starter.
    resumeNativeView(ticket);
  }
  async function api(path,body,signal){
    const bridge=source();
    if(typeof bridge?.request!=='function')throw new Error('업무 화면 연결을 준비한 뒤 다시 시도해 주세요.');
    return bridge.request(path,body,signal);
  }
  async function operationsRead(query={}){const at=context();const result=await api('operations?'+new URLSearchParams(query));return at===context()?result:null;}
  async function operationsCommand(body){return sendCommand('operations',body);}
  let helpWriting=null;
  function syncHelpState(){workUI.syncHelpState?.();designer.syncHelpState?.();}
  async function askHelp(question,visible={}){
    const bridge=source(),at=context(),auth=token();
    if(helpWriting||bridge?.helpState?.()?.busy)throw new Error('앞선 답변을 마친 뒤 질문을 보내 주세요.');
    if(typeof question!=='string'||!question.trim()||question.length>8000)throw new Error('대화에 보낼 질문을 확인해 주세요.');
    if(!available()||!chatPrepared()||nativeReturnPreview()||typeof bridge?.askHelp!=='function')throw new Error('업무 도우미 연결을 준비한 뒤 다시 시도해 주세요. 작성 중인 내용은 그대로입니다.');
    const reference={kind:'help',system_id:selection.system_id || '',context_id:at};
    for(const [name,value,limit] of [['screen',visible.screen,200],['term_id',visible.term_id,100],['title',visible.title ?? visible.draftName,200]]){
      if(value===undefined||value==='')continue;
      if(typeof value!=='string'||value.length>limit)throw new Error('질문의 참고 정보를 확인해 주세요.');
      reference[name]=value;
    }
    if(auth!==token()||at!==context()||bridge!==source())return false;
    const operation={};helpWriting=operation;
    try{
      // Source Chat owns one real send. Never read, replace or restore the live
      // composer; its text, attachments and selected assets stay untouched.
      const result=await bridge.askHelp({question:question.trim(),reference:Object.freeze(reference)});
      if(auth!==token()||at!==context()||bridge!==source())return false;
      if(result?.accepted===false)return false; // Source already owns the one-line notice.
      if(result?.accepted!==true)throw new Error('질문을 보내지 못했습니다. 업무 도우미 연결을 확인해 주세요.');
      return true;
    }finally{if(helpWriting===operation)helpWriting=null;syncHelpState();}
  }
  async function read(query={}){const at=context();const result=await api('workspace?'+new URLSearchParams(Object.entries(query).filter(([,value])=>value!==undefined&&value!==null)));if(at!==context())return null;return result;}
  function normalized(result){
    const next=clone(result),workflow=next.workflow;
    const attention=next.operations?.actionable || [];next.my_work=[...(next.my_work || []),...attention.map(item=>({...item,bucket:'overdue',name:'예약 실행 확인',status:item.state,reason:item.reason}))];
    const rank={failed:0,missed:1,running:2,succeeded:3};for(const workflow of next.workflows || []){const candidates=(next.operations?.automatic_statuses || []).filter(item=>item.workflow_id===workflow.id&&(!selection.factory_id||item.factory_id===selection.factory_id)).sort((a,b)=>rank[a.status]-rank[b.status]);if(candidates.length)workflow.last_auto_status=candidates[0].status;}
    if(workflow){workflow.definition=workflow.published?.definition || workflow.published || workflow.definition || workflow.draft;workflow.name=workflow.name || workflow.draft?.name;}
    const settings=next.settings || workflow?.settings || [];
    if(Array.isArray(settings)){
      const factoryId=next.run?.factory_id ?? selection.factory_id,common=settings.find(item=>!item.factory_id),specific=settings.find(item=>item.factory_id===factoryId);
      next.settings={values:{...(common?.values || {}),...(specific?.values || {})},base_values:common?.values || {},overrides:specific?.values || {},revision:specific?.revision || 0,factory_id:factoryId};
    }
    if(next.run){const attempts=next.run.attempts || [];for(const [id,job] of Object.entries(next.run.jobs || {})){
      const attempt=attempts.find(item=>item.id===job.current_attempt) || attempts.filter(item=>item.job_id===id).at(-1);
      if(attempt){job.result=attempt.result;job.attempt_id=attempt.id;job.evidence_access=attempt.evidence_access;}
      if(Array.isArray(job.decisions)){job.decision_history=clone(job.decisions);job.decisions=Object.fromEntries(job.decisions.filter(item=>item.result_revision===job.result_revision).map(item=>[item.item_id,item]));}
      const external=(next.operations?.requests || []).filter(item=>item.job_id===id).at(-1);if(external)job.request=external;
    }}
    return next;
  }
  const workspaceKey=()=>JSON.stringify([selection.system_id || '',selection.factory_id || '',selection.workflow_id || '',selection.run_id || '']);
  function cacheWorkspace(){
    if(!state||targetLoading||scopeLoading||evidenceUnavailable||!stateKey)return;
    workspaceCache.delete(stateKey);workspaceCache.set(stateKey,state);
    // Private snapshots live only in this authenticated document. Retain each
    // visited target until account changes or access failures discard them.
  }
  function changeWorkspace(previous){
    const key=workspaceKey();if(key===stateKey)return;
    const cached=workspaceCache.get(key);stateKey=key;
    if(cached){state=cached;targetLoading=false;scopeLoading=false;return;}
    const sameScope=previous.system_id===selection.system_id&&previous.factory_id===selection.factory_id;
    // A list is known after any successful target read in that exact scope.
    // Keep its received rows when returning without the old selected target.
    const scopeKey=JSON.stringify([selection.system_id || '',selection.factory_id || '']);
    const received=!sameScope&&[...workspaceCache].reverse().find(([key])=>JSON.stringify(JSON.parse(key).slice(0,2))===scopeKey)?.[1];
    // Operations' requests and scope_runs belong to one run; the other
    // received values describe this actor/system's tools, models and schedules.
    const operations=received?{...received.operations,requests:[],scope_runs:[]}:{};
    if(state||received)state={...(received || state),workflow:null,run:null,settings:{values:{},revision:0},legacy:null,operations,...(!sameScope&&!received?{workflows:[],runs:[],my_work:[]}: {})};
    if(!sameScope)scopeLoading=!received;
    targetLoading=Boolean(selection.workflow_id||selection.run_id);
  }
  function invalidateWorkspace(){
    workspaceCache.clear();state=null;stateKey='';targetLoading=false;scopeLoading=false;pendingInputProposal=null;inputProposalApplied=null;optionCache.clear();
    view.reset();designer.reset();
  }
  function acceptWorkspace(next){
    const previous=state;
    if(previous&&JSON.stringify(previous.capabilities)!==JSON.stringify(next.capabilities))workspaceCache.clear();
    // Unchanged sections retain their identity; renderers can update a changed
    // section without remounting unrelated menus, forms or their scroll areas.
    if(previous)for(const key of Object.keys(next))if(JSON.stringify(previous[key])===JSON.stringify(next[key]))next[key]=previous[key];
    if(inputProposalApplied&&next.run?.id===selection.run_id){
      for(const [key,value] of Object.entries(inputProposalApplied.values))if(workValuesEqual(value,next.run.inputs?.[key]))delete inputProposalApplied.values[key];
      if(!Object.keys(inputProposalApplied.values).length)inputProposalApplied=null;
    }
    state=next;stateKey=workspaceKey();targetLoading=false;scopeLoading=false;evidenceUnavailable=false;nativeCapabilities=null;cacheWorkspace();
  }
  const accessFailure=failure=>[401,403,404].includes(failure.status)||['auth_required','unauthorized','scope_forbidden','run_forbidden','access_denied','workflow_manage_forbidden','admin_required','workflow_not_found','run_not_found'].includes(failure.code);
  async function refresh(){
    if(!screenAvailable())return null;clearTimeout(refreshTimer);const at=context(),n=++serial;
    try{
      // Native navigation needs current capabilities, not a possibly revoked
      // EES run. The normal chat path validates the saved selection on return.
      const result=await api('workspace?'+new URLSearchParams(nativePage()?{}:{system_id:selection.system_id,factory_id:selection.factory_id,workflow_id:selection.workflow_id,run_id:selection.run_id}));
      if(at!==context()||n!==serial||!screenAvailable())return null;
      const previousActor=state?.capabilities?.actor_id || nativeCapabilities?.actor_id;
      if(previousActor&&result.capabilities?.actor_id&&previousActor!==result.capabilities.actor_id){reset();nativeCapabilities=result.capabilities;return refresh();}
      if(!restored){restored=true;uiRevision=Math.max(uiRevision,result.ui_state?.revision || 0);const saved=result.ui_state?.state?.selection,explicit=initialSelectionPatch;initialSelectionPatch=null;if(saved&&typeof saved==='object')selection={...selection,...saved,...explicit};if(!selection.system_id)selection.system_id=(result.systems?.[0]?.id || result.systems?.[0] || '');if(explicit)remember(explicit.panel_width ?? null);if(at!==context())return refresh();}
      if(nativePage()){nativeCapabilities=result.capabilities || {};nativeScope={systems:result.systems || [],factories:result.factories || [],scope_options:result.scope_options};error='';render();refreshTimer=setTimeout(refresh,30000);return state;}
      if(selection.mode==='author'&&!['tools','workspace_admin'].includes(selection.tab)&&result.initial_procedures_ready===false&&(result.capabilities?.managed_systems || []).includes(selection.system_id)){
        await command({action:'initialize_procedures',system_id:selection.system_id,expected_revision:0});
        if(at!==context()||n!==serial||!screenAvailable())return null;
        return refresh();
      }
      let operations={};try{operations=await api('operations?'+new URLSearchParams({system_id:selection.system_id,run_id:selection.run_id}));}catch(failure){if(accessFailure(failure))throw failure;operations={error:failure.message};}if(at!==context()||n!==serial)return null;uiRevision=Math.max(uiRevision,result.ui_state?.revision ?? uiRevision);let legacy;if(selection.tab==='records'){try{legacy=await api('legacy');}catch(failure){legacy={error:failure.message};}if(at!==context()||n!==serial)return null;}acceptWorkspace(normalized({...result,operations,legacy}));if(selection.mode==='author'&&!workCanWorkspace(state.capabilities)){selection={...selection,mode:'work',tab:'my_work'};}error='';readyRoute=route;syncNativeReturn();render();loadOptions();
      const active=Object.values(state.run?.jobs || {}).some(job=>job.status==='running')||(state.operations?.scope_runs || []).some(scope=>['queued','running'].includes(scope.status))||(state.operations?.requests || []).some(request=>['requested','accepted','running','reported_complete'].includes(request.state));refreshTimer=setTimeout(refresh,active||busy?2500:30000);
      return state;
    }catch(failure){if(at!==context()||n!==serial)return null;error=failure.message;if(!nativePage()&&pendingNativeAction?.applied){pendingNativeAction=null;invalidateWorkspace();}if(nativePage()){nativeCapabilities={};nativeScope=null;}if(accessFailure(failure)){invalidateWorkspace();nativeCapabilities={};nativeScope=null;}
      else if(!nativePage()&&(selection.mode!=='author'||['history','records','historical_reference'].includes(selection.tab))){
        // Previously displayed attempts and their private inputs require a
        // successful current lookup. Preserve editor drafts and navigation,
        // but never expose old results after a failed work-state read.
        evidenceUnavailable=true;workspaceCache.delete(stateKey);
        if(state?.run?.id)for(const [key,value] of workspaceCache)if(value.run?.id===state.run.id)workspaceCache.delete(key);
      }targetLoading=false;render();return null;}
  }
  function revisionFor(action){if(['save_draft','validate_workflow','publish_workflow','start_run','run_start'].includes(action))return state?.workflow?.revision || 0;if(action==='save_settings')return state?.settings?.revision || 0;if(action==='save_ui')return uiRevision;return state?.run?.revision || 0;}
  async function command(body){return sendCommand('workspace/command',body);}
  async function sendCommand(path,body){
    if(!available())throw new Error('로그인을 확인해 주세요.');
    const at=context(),auth=token(),payload={...body,expected_revision:body.expected_revision ?? revisionFor(body.action)};
    const key=path+JSON.stringify(payload);if(!payload.request_id)payload.request_id=receipts.get(key) || workUI.newId();receipts.set(key,payload.request_id);
    let result;
    try{result=await api(path,payload);receipts.delete(key);}
    catch(failure){if(failure.status&&failure.status<500)receipts.delete(key);if(auth===token()&&at===context()){commandError=failure.message;render();}throw failure;}
    if(auth!==token()||at!==context())return null;
    commandError='';return result;
  }
  function remember(panelWidth=null){
    clearTimeout(uiTimer);const at=context(),auth=token(),saved=clone(selection);
    uiTimer=setTimeout(()=>{uiWrites=uiWrites.catch(()=>{}).then(async()=>{
      if(at!==context()||auth!==token()||!available())return;
      try{if(JSON.stringify({selection:saved}).length>39000)throw new Error('개인 초안 저장 범위를 초과했습니다. 현재 판정 선택을 확정한 뒤 다시 시도해 주세요.');let result;try{result=await api('workspace/command',{action:'save_ui',expected_revision:uiRevision,request_id:workUI.newId(),state:{selection:saved}});}
      catch(failure){
        if(failure.code!=='revision_conflict'||panelWidth===null)throw failure;
        if(auth!==token()||at!==context()||!available())return;
        const current=await api('workspace?');if(auth!==token()||at!==context()||!available())return;
        const stored=current.ui_state?.state || {},revision=current.ui_state?.revision || 0;uiRevision=Math.max(uiRevision,revision);
        // A concurrent tab's private drafts stay intact. Only the explicit
        // width preference is merged once, never a shared business command.
        result=await api('workspace/command',{action:'save_ui',expected_revision:revision,request_id:workUI.newId(),state:{...stored,selection:{...(stored.selection || {}),panel_width:panelWidth}}});
      }if(auth===token()){uiRevision=Math.max(uiRevision,result.ui_state?.revision ?? result.revision ?? uiRevision+1);if(commandError.startsWith('작성한 선택의 자동 저장 실패')){commandError='';render();}}}
      catch(failure){if(auth===token()&&at===context()&&(panelWidth!==null||Object.keys(saved.verdict_drafts || {}).length||Object.keys(saved.start_inputs || {}).length||Object.keys(saved.request_reasons || {}).length)){commandError='작성한 선택의 자동 저장 실패 · '+failure.message+' 화면의 값은 보존했습니다. 저장을 다시 시도해 주세요.';render();}}
    });},400);
  }
  async function setPanelOpen(open){
    if((selection.panel_open!==false)===open)return state;
    // Visibility does not change the selected work, help context or chat epoch.
    if(!open)workUI.closeHelp({restoreFocus:false});
    view.capture();designer.readDraft?.();
    if(!restored)initialSelectionPatch={...initialSelectionPatch,panel_open:open};
    selection={...selection,panel_open:open};remember();render();
    await source()?.focusPanel?.(open);
    if(open)loadOptions();
    return state;
  }
  function commitSelection(patch){
    if(pendingNativeAction?.applied)pendingNativeAction=null;clearTimeout(reviewTimer);
    const previous={...selection},before=context(),next={...selection,chat_reference:null,...patch};
    if(['system_id','factory_id','workflow_id','run_id'].some(key=>previous[key]!==next[key]))Object.assign(next,{stage_id:'',stage_overview:false,stage_tab:'work',stage_evidence:'',stage_tool:'',stage_attempts:{},stage_approved_expanded:false,stage_verdict_job:''});
    const sameInputTarget=token()===identity&&previous.run_id&&previous.job_id&&
      ['mode','system_id','factory_id','workflow_id','run_id','job_id'].every(key=>previous[key]===next[key])&&
      Object.keys(patch).every(key=>key==='tab'||JSON.stringify(patch[key])===JSON.stringify(previous[key]));
    if(state&&!stateKey)stateKey=workspaceKey();cacheWorkspace();
    if(!restored)initialSelectionPatch={...initialSelectionPatch,chat_reference:null,...patch};
    selection=next;changeWorkspace(previous);epoch++;workEpoch++;chatCreations.clear();chatAliases.clear();
    // A tab visit changes request epochs, but the same job's unsaved proposal
    // remains reviewable. Never revive one invalidated before this navigation.
    if(sameInputTarget){if(pendingInputProposal?.context===before)pendingInputProposal.context=context();else pendingInputProposal=null;}
    else{pendingInputProposal=null;inputProposalApplied=null;}
    error='';commandError='';clearTimeout(refreshTimer);remember();
  }
  async function select(patch,{fetch=true,validate=null}={}){workUI.closeHelp({restoreFocus:false});designer.closeStart?.();procedureStart=null;view.capture();const before=context();while(state?.run?.definition?.nodes?.[selection.job_id]?.result_block==='ai_review'&&view.readReview?.().dirty){if(!await saveReviewDraft()||before!==context())return null;view.capture();}if(validate&&!validate())return null;commitSelection(patch);render();if(fetch)return refresh();refreshTimer=setTimeout(refresh,2500);loadOptions();return state;}
  async function mutate(body,{refreshAfter=true,accept=null}={}){if(busy)return null;const at=context();setBusy(true);try{const result=await command(body);if(result&&accept)accept(result);if(result&&refreshAfter&&!await refresh())return null;return at===context()?result:null;}catch(failure){if(at===context()){commandError=failure.message;render();}return null;}finally{setBusy(false);}}
  async function models(){
    const auth=token(),headers={Accept:'application/json',Authorization:'Bearer '+auth};
    const response=await fetch('/api/models',{headers,credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error('사용 가능한 모델을 조회하지 못했습니다.');
    const result=await response.json();if(auth!==token()||auth!==identity)return [];
    const list=(result.data || []).filter(model=>model.id&&!model.direct&&model.type!=='embedding').map(model=>({id:model.id,name:model.name || model.id}));
    source()?.modelCount?.(list.length);return list;
  }
  function optionContext({includeHidden=false}={}){
    const run=state?.run,node=run?.definition?.nodes?.[selection.job_id];
    if(!node||selection.mode==='author'||!includeHidden&&selection.panel_open===false||!['current','settings'].includes(selection.tab))return null;
    const draft=view.readInputs(),values={...(run.jobs?.[node.id]?.effective_inputs || {}),...(state.settings?.values || {})};
    for(const field of node.inputs || [])if((['workflow','factory'].includes(field.scope))===(selection.tab==='settings'))delete values[field.id];Object.assign(values,draft.inputs || {});
    const inputs=Object.fromEntries((node.inputs || []).filter(field=>Object.hasOwn(values,field.id)).map(field=>[field.id,values[field.id]]));
    return {node,inputs,marker:context()+JSON.stringify([run.revision,state.settings?.revision,inputs,node.inputs])};
  }
  async function loadOptions(forceField=''){
    const current=optionContext();if(!current)return;
    const fields=(current.node.inputs || []).filter(field=>['single','multi'].includes(field.type)&&field.options_source&&field.options_source!=='manual'&&(['workflow','factory'].includes(field.scope))===(selection.tab==='settings'));
    if(!fields.length)return;const at=context();state.input_options ||= {};
    const pending=[];
    for(const field of fields){
      const key=selection.run_id+'/'+selection.job_id+'/'+field.id,marker=current.marker;
      const cached=optionCache.get(key);if(cached?.marker===marker&&forceField!==field.id){state.input_options[field.id]=cached;continue;}
      const entry={marker,status:'loading',options:[]};optionCache.set(key,entry);state.input_options[field.id]=entry;
      const body={workflow_id:selection.workflow_id,run_id:selection.run_id,job_id:selection.job_id,field_id:field.id,factory_id:state.settings?.factory_id ?? selection.factory_id,inputs:current.inputs};
      pending.push((async()=>{
        try{const result=await api('workspace/options',body);if(at!==context()||optionContext({includeHidden:true})?.marker!==marker||optionCache.get(key)!==entry)return;
          Object.assign(entry,{status:'ready',options:result.options || [],source:result.source,source_context:result.context});
        }catch(failure){if(at!==context()||optionContext({includeHidden:true})?.marker!==marker||optionCache.get(key)!==entry)return;Object.assign(entry,{status:'failed',options:[],error:failure.message});}
      })());
    }
    if(!pending.length)return;render();await Promise.all(pending);if(at===context()&&optionContext()?.marker===current.marker)render();
  }
  async function saveInputs(){if(busy)return;const form=$('#ees-work-inputs');if(form?.querySelectorAll&&[...form.querySelectorAll('input,select,textarea')].some(field=>!field.reportValidity()))return;const draft=view.readInputs(),applied=inputProposalApplied;if(pendingInputProposal&&!draft.settings){error=pendingInputMessage;render();return;}if(draft.conflict){error='다른 사람이 바꾼 값과 먼저 비교해 주세요.';render();return;}const body=draft.settings?{action:'save_settings',workflow_id:selection.workflow_id,factory_id:state.settings?.factory_id ?? selection.factory_id,values:state.settings?.factory_id?workSettingsOverrides(state.settings,draft.inputs,state.run?.definition?.nodes?.[selection.job_id]?.inputs):draft.inputs}:{action:'save_inputs',run_id:selection.run_id,inputs:draft.inputs};await mutate({...body,expected_revision:draft.revision},{accept:result=>{view.clearInputs(draft.key,draft.serial,result.revision || draft.revision+1,draft.inputs);if(!draft.settings&&inputProposalApplied===applied)inputProposalApplied=null;}});}
  function executionModel(){const available=state?.operations?.error?[]:state?.operations?.models || [];return available.length===1?available[0].id:$('#ees-work-execution-model')?.value;}
  function inputsSaved(all=false){if(pendingInputProposal){error=pendingInputMessage;render();return false;}const draft=view.readInputs();if(draft.dirty||(all&&view.hasPendingInputs?.())){error='변경한 입력을 먼저 저장해 주세요. 저장하지 않은 값으로 실행하거나 판정하지 않았습니다.';render();return false;}return true;}
  async function requestIntent(){
    if(!inputsSaved())return;
    const at=context(),run=state?.run,node=run?.definition?.nodes?.[selection.job_id];if(!node)return;
    setBusy(true);
    try{
      let request=(state.operations?.requests || []).filter(item=>item.job_id===node.id&&!['cancelled','failed','rejected'].includes(item.state)).at(-1);
      const reason=selection.request_reasons?.[run.id+'/'+node.id] || '';
      if(request&&request.actor===state.capabilities?.actor_id&&['ready','approval_pending'].includes(request.state)&&(request.request_reason || '')!==reason){await operationsCommand({action:'request_cancel',external_request_id:request.id,expected_revision:request.revision});if(at!==context())return;request=null;}
      if(!request){const prepared=await operationsCommand({action:'request_prepare',run_id:run.id,job_id:node.id,tool_contract_id:node.tool_contract_id || node.tool_reference?.contract_id,request_reason:selection.request_reasons?.[run.id+'/'+node.id] || '',expected_revision:run.revision});if(!prepared||at!==context())return;request=prepared.request;}
      if(request.state==='approval_pending'){await refresh();return;}
      const intent=await operationsCommand({action:'request_intent',external_request_id:request.id,expected_revision:request.revision});if(!intent||at!==context())return;
      const info=intent.request || request,requestValues=Object.fromEntries((workRequestFields(node,state.operations?.tools) || []).map(field=>[field.name,field.constant?field.value:run.jobs[node.id].effective_inputs?.[field.id]]));
      const approved=await confirmDialog({title:node.request_contract?.confirmation_title || (info.execution_actor==='EES Work'?'직접 실행 · 예외 내용을 확인할까요?':'EES에 요청할까요?'),html:`<div class="ew-confirm-target"><strong>${esc(node.name)}</strong><pre>${esc(JSON.stringify(info.inputs || requestValues,null,2))}</pre></div><p>${esc(info.impact || '등록된 EES 기능이 대상 시스템의 상태를 변경합니다.')}</p><p>${esc(workUI.executionActorLabel(info.execution_actor || 'EES'))} 완료 보고 뒤 효과를 따로 확인합니다.</p><p>요청 사유 · ${esc(info.request_reason || '미기재')}</p><p>요청한 사람·시각·사유가 기록에 남습니다.</p>`,confirmLabel:node.request_contract?.button_label || '요청 보내기'});
      if(!approved||at!==context())return;
      await operationsCommand({action:'request_dispatch',external_request_id:request.id,intent_token:intent.intent_token,expected_revision:info.revision});await refresh();
    }catch(failure){if(at===context()){error=failure.message;render();}}finally{setBusy(false);}
  }
  async function amendItems(){
    if(busy||!inputsSaved())return;const at=context(),run=state?.run,job=run?.jobs?.[selection.job_id],original=job?.result?.items || [];let items=original.map(item=>({id:item.id,name:item.name || item.title || item.id,note:item.note || ''})),reason='';
    const rows=()=>items.map((item,index)=>`<fieldset class="ew-amend-row" data-index="${index}"><label>항목 ID<input data-amend-field="id" value="${esc(item.id)}" required></label><label>이름<input data-amend-field="name" value="${esc(item.name)}" required></label><label>보완 내용<input data-amend-field="note" value="${esc(item.note)}"></label><button type="button" data-amend-remove="${index}">목록에서 제외</button></fieldset>`).join('');
    const pending=dialog({title:'목록 수정 · 다시 검토',note:'이전 근거와 판정은 남깁니다. 바뀐 목록으로 새 시도를 기록하고 후속 확인을 다시 검토합니다.',html:`<div id="ees-amend-list">${rows()}</div><button type="button" id="ees-amend-add">항목 추가</button><label>변경 이유<input id="ees-amend-reason" required></label>`,confirmLabel:'수정한 목록 저장'}),element=$('#ees-work-dialog');
    element.addEventListener('input',event=>{if(event.target.id==='ees-amend-reason')reason=event.target.value;const row=event.target.closest('[data-index]');if(row&&event.target.dataset.amendField)items[Number(row.dataset.index)][event.target.dataset.amendField]=event.target.value;});
    element.addEventListener('click',event=>{if(event.target.id==='ees-amend-add'){items.push({id:'',name:'',note:''});$('#ees-amend-list').innerHTML=rows();}if(event.target.dataset.amendRemove!==undefined){items.splice(Number(event.target.dataset.amendRemove),1);$('#ees-amend-list').innerHTML=rows();}});
    if(await pending&&at===context())await mutate({action:'amend_items',run_id:run.id,job_id:selection.job_id,result_revision:job.result_revision,expected_revision:run.revision,items,reason});
  }
  async function addListItem(){
    if(busy)return;const at=context();let id='',name='';const pending=dialog({title:'번호로 항목 추가',note:'사람이 추가한 항목으로 기록합니다. 실제 원본 조회나 AI 판정을 대신하지 않습니다.',html:'<label>항목 번호<input id="ees-list-add-id" required></label><label>이름<input id="ees-list-add-name" required></label>',confirmLabel:'검토 목록에 추가'});
    $('#ees-work-dialog').addEventListener('input',()=>{id=$('#ees-list-add-id').value.trim();name=$('#ees-list-add-name').value.trim();});
    if(await pending&&at===context())view.addListItem({id,name});
  }
  async function confirmList(confirm=true){
    if(busy||!inputsSaved())return;const at=context(),run=state?.run,jobId=selection.job_id,saved=run?.jobs?.[jobId],draft=view.readList();
    if(!saved||saved.can_decide===false||draft.attempt_id!==saved.attempt_id||draft.result_revision!==saved.result_revision)throw new Error('현재 목록의 근거와 처리 권한을 다시 확인해 주세요.');
    const selected=draft.items.filter(item=>item.selected),sharedSearch=Boolean(run.definition?.nodes?.[jobId]?.shared_tool_id)&&saved.result?.scope==='single_page',emptyConfirmation=confirm&&!selected.length;
    if(emptyConfirmation&&!sharedSearch)throw new Error('포함할 항목이 없습니다. 빈 목록의 완료 정책을 먼저 확인해 주세요.');
    const source=workListSourceAttempt(run,saved.attempt_id),noResults=emptyConfirmation&&Array.isArray(source?.result?.items)&&source.result.items.length===0;
    let reason=noResults?'0건 확인':emptyConfirmation?'맞는 문서 없음 · 0개 선택':'';
    const pending=noResults?Promise.resolve(true):dialog({title:emptyConfirmation?'맞는 문서가 없는 것으로 확정할까요?':confirm?'이 목록으로 확정할까요?':'선택한 목록을 저장할까요?',note:confirm?'선택한 포함·제외와 사람의 확인을 함께 저장합니다. AI 후보를 자동 확정하지 않습니다.':'새 검토 시도로 선택 상태를 저장합니다. 업무 완료로 확정하지 않습니다.',html:`<p>포함 ${selected.length}건 · 제외 ${draft.items.filter(item=>!item.selected).length}건</p>${emptyConfirmation?'':'<label>확인·변경 이유<input id="ees-list-confirm-reason" required></label>'}`,confirmLabel:confirm?'목록 확정':'선택 목록 저장'});
    if(!emptyConfirmation)$('#ees-list-confirm-reason').addEventListener('input',event=>{reason=event.target.value;});
    if(await pending&&at===context())await mutate({action:confirm?'confirm_list':'amend_items',run_id:run.id,job_id:jobId,attempt_id:draft.attempt_id,result_revision:draft.result_revision,expected_revision:run.revision,items:draft.items.filter(item=>!item.candidate||item.selected).map(item=>({...clone(item),selected:Boolean(item.selected),required:Boolean(item.selected)})),reason});
  }
  function saveReviewDraft(){if(reviewSaving)return reviewSaving;const pending=performSaveReviewDraft().finally(()=>{if(reviewSaving===pending)reviewSaving=null;});reviewSaving=pending;return pending;}
  async function performSaveReviewDraft(){
    clearTimeout(reviewTimer);if(busy||!state?.run||!selection.job_id)return false;
    const draft=view.readReview(),run=state.run,jobId=selection.job_id,saved=run.jobs[jobId];if(!draft.dirty)return true;
    if(draft.conflict)throw new Error('검토 본문이 다른 곳에서 변경되었습니다. 작성한 값을 보존하고 최신 기록을 먼저 확인해 주세요.');
    if(saved.can_decide===false||draft.attempt_id!==saved.attempt_id)throw new Error('초안의 실행 근거와 저장 권한을 다시 확인해 주세요.');
    const result=await mutate({action:'save_review_draft',run_id:run.id,job_id:jobId,attempt_id:draft.attempt_id,result_revision:draft.result_revision,expected_revision:run.revision,review_revision:draft.revision,text:draft.inputs.text},{accept:result=>{const savedReview=result.run?.jobs?.[jobId]?.review_draft;if(!savedReview)throw new Error('저장된 검토 초안의 버전을 확인하지 못했습니다.');view.clearReview(draft.key,draft.serial,savedReview.revision,savedReview.text);}});
    return Boolean(result);
  }
  function scheduleReviewSave(){const at=context();clearTimeout(reviewTimer);reviewTimer=setTimeout(()=>{if(at!==context())return;if(busy){scheduleReviewSave();return;}saveReviewDraft().catch(failure=>{if(at===context()){error=failure.message;render();}});},600);}
  async function confirmDialog(options){const at=context();const accepted=await dialog(options);return accepted&&at===context();}
  function previewInputProposal(payload){
    const values=workInputProposal(payload,state?.run,selection.job_id,state?.operations?.tools || []),draft=view.readInputs({runInputs:true});
    const fields=state.run.definition.nodes[selection.job_id]?.inputs || [],reasons={options_dependency_required:'선행 입력을 먼저 보완해 주세요.',options_unconfigured:'선택 목록 연결을 먼저 설정해 주세요.',options_unavailable:'현재 권한의 선택 목록을 조회하지 못했습니다.'};
    const warnings=[...(payload.warnings || []),...(payload.unresolved_fields || []).map(item=>`${fields.find(field=>field.id===item.field_id)?.name || item.field_id} · ${reasons[item.reason] || '현재 선택 목록을 먼저 확인해 주세요.'} 이 항목은 AI 초안에 포함하지 않았습니다.`)];
    pendingInputProposal={values,warnings,context:context(),run_id:selection.run_id,job_id:selection.job_id,revision:state.run.revision,draft:JSON.stringify(draft.inputs)};render();return {ok:true,preview:true,saved:false,executed:false};
  }
  function applyInputProposal(){
    const pending=pendingInputProposal,draft=view.readInputs({runInputs:true});
    if(!pending||pending.context!==context()||pending.run_id!==selection.run_id||pending.job_id!==selection.job_id||pending.revision!==state?.run?.revision||pending.draft!==JSON.stringify(draft.inputs))throw new Error('제안 이후 입력이나 저장 상태가 바뀌었습니다. 현재 값을 보존하고 새 제안을 요청해 주세요.');
    workInputProposal({proposal_kind:'inputs',workflow_id:state.run.workflow_id,run_id:pending.run_id,job_id:pending.job_id,base_revision:pending.revision,proposal:pending.values},state.run,selection.job_id,state.operations?.tools || []);
    // A later preview does not erase an earlier accepted draft. Attribute only
    // actual changes that remain different from the saved run values.
    const previous=inputProposalApplied,saved=state.run.inputs || {};
    const changes=Object.fromEntries(Object.entries(pending.values).filter(([key,value])=>!workValuesEqual(value,draft.inputs[key])));
    const values=Object.fromEntries(Object.entries(previous?.values || {}).filter(([key,value])=>workValuesEqual(value,draft.inputs[key])&&!workValuesEqual(value,saved[key])));
    for(const [key,value] of Object.entries(changes)){delete values[key];if(!workValuesEqual(value,saved[key]))values[key]=clone(value);}
    pendingInputProposal=null;if(error===pendingInputMessage)error='';
    if(Object.keys(changes).length)view.applyInputValues(changes);
    inputProposalApplied=Object.keys(values).length?(previous&&workValuesEqual(values,previous.values)?previous:{values,at:new Date().toISOString()}):null;
    render();if(Object.keys(changes).length)loadOptions();
  }
  async function downloadRun(format,jobId=''){
    const at=context(),runId=state?.run?.id;if(!runId)return;
    const result=await api('export?'+new URLSearchParams({run_id:runId}));if(at!==context())return;
    if(result.format!=='ees-work-run'||result.run?.id!==runId)throw new Error('내보낼 기록의 대상과 형식을 확인하지 못했습니다.');
    const document=clone(result);
    if(jobId){const job=document.run.jobs?.[jobId];if(!job)throw new Error('내보낼 결과를 확인하지 못했습니다.');document.run.attempts=(document.run.attempts || []).filter(attempt=>attempt.id===job.current_attempt&&attempt.job_id===jobId);document.run.jobs={[jobId]:job};}
    const contents=format==='json'?JSON.stringify(document,null,2):workExportText(document),blob=new Blob([contents],{type:format==='json'?'application/json;charset=utf-8':'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=window.document.createElement('a');
    link.href=url;link.download='ees-work-'+runId.replace(/[^a-zA-Z0-9_-]/g,'_')+(jobId?'-result':'')+(format==='json'?'.json':'.txt');source()?.hosts?.()?.overlays?.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function openLegacy(id){
    const at=context(),legacy=await api('legacy?'+new URLSearchParams({case_id:id}));if(at!==context())return;
    if(!legacy.read_only||legacy.record?.id!==id)throw new Error('읽기 전용 과거 기록을 확인하지 못했습니다.');
    const record=legacy.record;
    return dialog({title:record.process_name || '이전 기록',note:legacy.notice || '사용 중지된 이전 버전의 기록입니다. 여기에서 다시 실행하지 않습니다.',readOnlyDetail:true,html:`${record.simulation?'<p class="ew-warning">시뮬레이션 기록 · 실제 업무 성공을 뜻하지 않습니다.</p>':''}<p>이전 게시 v${esc(record.version)} · ${esc(record.status)}</p><pre>${esc(JSON.stringify({inputs:record.inputs,jobs:record.jobs,progress:record.progress,created_at:record.created_at},null,2))}</pre>`});
  }
  async function setupWorkTool(){
    if(!state?.capabilities?.is_admin)throw new Error('Native 관리자 권한이 필요합니다.');
    const at=context(),auth=token(),current=()=>at===context()&&auth===token();
    const setupAPI=async(body,path=body?'setup':'status')=>{const response=await fetch('/api/v1/ees/assets/work-tool/'+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',Authorization:'Bearer '+auth,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const result=await response.json();if(!response.ok||result.ok===false)throw new Error(result.error?.message || result.detail?.message || (typeof result.detail==='string'?result.detail:result.reason) || 'Native Work 도구 설정을 확인하지 못했습니다.');return result;};
    const status=await setupAPI();if(!current())return;
    const description=`<p>Native 도구 ID · ${esc(status.id)}</p><p>등록 원본 SHA256</p><pre>${esc(status.registered_source_sha256 || '미등록')}</pre><p>지금 프로그램 원본 SHA256</p><pre>${esc(status.source_sha256)}</pre>`;
    const preserve='<p>그대로 두는 것 · 이름·소유자·읽기 권한·설정</p><p>바뀌는 것 · 코드 원본</p>';
    const date=value=>esc(value || '날짜 확인 불가');
    let confirmation='register_readonly_work_tool',path='setup',body;
    if(status.state==='blocked_existing')return dialog({title:'등록 원본이 지원 형태와 다릅니다',readOnlyDetail:true,html:`<p>등록된 코드가 알려진 제품 원본과 다릅니다.</p><p>이 화면은 코드를 바꾸지 않습니다. 등록 해시 앞 8자리를 개발 담당에게 알려 주세요.</p><p>등록 해시 앞 8자리 · <code>${esc(String(status.registered_source_sha256 || '미확인').slice(0,8))}</code></p>`+description});
    if(['ready','update_available'].includes(status.state)){
      let restore=false;const canRestore=status.backup?.can_restore===true;
      const pending=dialog({title:status.state==='ready'?'Work 대화 도구가 연결되어 있습니다':'이전 제품 원본이 등록되어 있습니다',readOnlyDetail:status.state==='ready',confirmLabel:status.state==='update_available'?'지금 프로그램 원본으로 바꾸기':'',html:description+`<p>${esc(status.reason || '현재 등록 항목의 소유자·권한·설정을 유지합니다.')}</p>`+(canRestore?`<p>비공개 백업 · ${date(status.backup.created_at)}</p><button type="button" data-work-tool-restore class="ew-secondary">이전 코드 원본으로 되돌리기</button>`:'')});
      $('#ees-work-dialog')?.addEventListener('click',event=>{if(canRestore&&event.target.closest?.('[data-work-tool-restore]')){restore=true;closeDialog();}});
      const accepted=await pending;if(!current()||!accepted&&!restore||!restore&&status.state!=='update_available')return;
      if(restore){
        const approved=await dialog({title:'이전 코드 원본으로 되돌릴까요?',confirmLabel:'백업 코드 원본으로 되돌리기',html:`<p>비공개 백업 시각 · ${date(status.backup.created_at)}</p><p>되돌릴 코드 SHA256</p><pre>${esc(status.backup.from_source_sha256)}</pre>${preserve}<p>이전 프로그램 원본으로 되돌리면 업무 도우미가 다시 사용 불가 상태가 될 수 있습니다.</p>`});
        if(!approved||!current())return;
        path='restore';confirmation='restore_previous_work_tool';body={backup_id:status.backup.id,backup_sha256:status.backup.sha256};
      }else{
        const approved=await dialog({title:'지금 프로그램 원본으로 바꿀까요?',confirmLabel:'지금 프로그램 원본으로 바꾸기',html:`<p>이전 원본 (${date(status.registered_source?.date)}) → 지금 원본 (${date(status.program_source?.date)})</p>${preserve}<p>바꾸기 전 코드 원본은 관리자만 접근하는 비공개 백업으로 남깁니다. 같은 설정 화면에서 백업 코드로 되돌릴 수 있습니다.</p>`});
        if(!approved||!current())return;
        confirmation='update_readonly_work_tool';body={};
      }
    }else if(status.state==='missing'){
      let grants=[];const people=(state.people || []).filter(person=>person.value?.kind==='user'),groups=state.native_groups || [];
      const pending=dialog({title:'Native 대화에 Work 도구를 등록할까요?',note:'조회·제안 기능만 등록합니다. 저장·게시·실행·확정 도구를 AI에 추가하지 않습니다.',html:description+`<p>허용 함수</p><pre>${esc(JSON.stringify(status.functions || [],null,2))}</pre><fieldset class="ew-admin-grants"><legend>읽기·제안 권한</legend><p>선택하지 않으면 등록 관리자 개인 범위입니다. 공개 권한은 만들지 않습니다.</p>${people.map(person=>`<label><input type="checkbox" data-work-grant data-kind="user" value="${esc(person.id)}">${esc(person.name)} · ${esc(person.id)}</label>`).join('')}${groups.map(group=>`<label><input type="checkbox" data-work-grant data-kind="group" value="${esc(group.id)}">${esc(group.name)} · ${esc(group.id)}</label>`).join('')}</fieldset>`,confirmLabel:'확인한 원본 등록'});
      $('#ees-work-dialog')?.addEventListener('change',()=>{grants=[...document.querySelectorAll('#ees-work-dialog [data-work-grant]:checked')].map(field=>({principal_type:field.dataset.kind,principal_id:field.value,permission:'read'}));});
      if(!await pending||!current())return;body={access_grants:grants};
    }else return dialog({title:'Work 도구 상태를 확인해 주세요',readOnlyDetail:true,html:description+`<p>${esc(status.reason || '지원되는 상태를 확인하지 못해 변경하지 않았습니다.')}</p>`});
    try{const result=await setupAPI({expected_token:status.expected_token,source_sha256:status.source_sha256,confirmation,...body},path);if(!current())return;commandError='';await refresh();if(!current())return;const message=path==='restore'?'비공개 백업의 코드 원본으로 되돌렸습니다.':confirmation==='update_readonly_work_tool'?'지금 프로그램 원본으로 바꿨습니다. 이전 코드 원본은 비공개 백업으로 보존했습니다.':result.changed?'확인한 제품 원본을 등록했습니다.':'기존 원본과 권한을 유지했습니다.';return dialog({title:'Native Work 도구 확인',readOnlyDetail:true,html:`<p>${esc(message)}</p>${confirmation==='register_readonly_work_tool'?'':'<p>이름·소유자·읽기 권한·설정을 유지했습니다.</p>'}<p>업무 도우미의 사용 가능 상태를 다시 확인해 주세요. 현재 대화의 도구 선택은 자동으로 바꾸지 않았습니다.</p>`});}
    catch(failure){if(current()){commandError=failure.message;render();}throw failure;}
  }
  async function adminDialog(kind,id=''){
    if(!state?.capabilities?.is_admin)throw new Error('Native 관리자 권한이 필요합니다.');
    const at=context(),record=(kind==='factory'?state.factories:state.access)?.find(item=>item.id===id),systems=(state.systems || []).map(item=>typeof item==='string'?item:item.id);
    const sys=record?.system_id || selection.system_id || systems[0];
    const option=(value,label,current)=>`<option value="${esc(value)}"${value===current?' selected':''}>${esc(label)}</option>`;
    const systemSelect=`<label>시스템<select name="system_id"${kind==='factory'&&record?' disabled':''}>${systems.map(value=>option(value,value,sys)).join('')}</select></label>`;
    let values=kind==='factory'?{factory_id:record?.id || '',system_id:sys,name:record?.name || '',attributes:JSON.stringify(record?.attributes || {},null,2)}:{access_id:record?.id || '',system_id:sys,factory_id:record?.factory_id || '*',principal_kind:record?.principal_kind || 'group',principal_id:record?.principal_kind==='user'?record.principal_id:'',group_id:record?.principal_kind==='group'?record.principal_id:state.native_groups?.[0]?.id || '',roles:record?.roles || [],active:record?Boolean(record.active):true};
    const html=kind==='factory'?`<div class="ew-admin-form">${systemSelect}<label>공장 ID<input name="factory_id" value="${esc(values.factory_id)}"${record?' readonly':''} placeholder="비우면 새 ID 생성"></label><label>공장 이름<input name="name" value="${esc(values.name)}" required></label><label>공장 속성 · JSON 객체<textarea name="attributes" rows="6">${esc(values.attributes)}</textarea></label><small>기존 공장의 시스템과 ID는 바꾸지 않습니다. 업무 입력·비밀정보를 공장 속성에 넣지 마세요.</small></div>`:`<div class="ew-admin-form">${systemSelect}<label>공장 범위<select name="factory_id">${option('*','시스템 전체 범위',values.factory_id)}${(state.factories || []).map(item=>`<option data-system="${esc(item.system_id)}" value="${esc(item.id)}"${item.id===values.factory_id?' selected':''}${item.system_id!==sys?' disabled':''}>${esc(item.name)}</option>`).join('')}</select></label><label>Native 대상<select name="principal_kind">${option('group','그룹',values.principal_kind)}${option('user','사용자',values.principal_kind)}</select></label><label data-admin-group>Native 그룹<select name="group_id"${values.principal_kind!=='group'?' disabled':''}>${option('','선택 필요',values.group_id)}${(state.native_groups || []).map(group=>option(group.id,group.name+' · '+group.id,values.group_id)).join('')}</select></label><label data-admin-user>기존 Native 사용자 ID<input name="principal_id" value="${esc(values.principal_id)}" list="ees-admin-native-users"${values.principal_kind!=='user'?' disabled':''}><datalist id="ees-admin-native-users">${(state.people || []).filter(person=>person.value?.kind==='user').map(person=>`<option value="${esc(person.id)}">${esc(person.name)}</option>`).join('')}</datalist></label><small>이름으로 사용자를 만들거나 찾지 않습니다. 서버가 현재 승인된 Native ID인지 확인합니다.</small><fieldset><legend>역할</legend>${Object.entries({viewer:'조회',participant:'참여·실행',manager:'절차·설정 관리',requester:'EES 요청',reviewer:'요청 검토'}).map(([role,label])=>`<label><input type="checkbox" name="roles" value="${role}"${values.roles.includes(role)?' checked':''}>${label}</label>`).join('')}</fieldset><label><input type="checkbox" name="active"${values.active?' checked':''}>사용</label></div>`;
    const pending=dialog({title:kind==='factory'?'공장 정보 저장':'업무 접근 범위 저장',html,confirmLabel:'변경 저장'}),element=$('#ees-work-dialog');
    const collect=()=>{for(const field of element.querySelectorAll('[name]')){if(field.name==='roles')continue;values[field.name]=field.type==='checkbox'?field.checked:field.value;}if(kind==='access'){values.roles=[...element.querySelectorAll('[name="roles"]:checked')].map(field=>field.value);const user=element.querySelector('[name="principal_id"]'),group=element.querySelector('[name="group_id"]');user.disabled=values.principal_kind!=='user';group.disabled=values.principal_kind!=='group';user.required=values.principal_kind==='user';group.required=values.principal_kind==='group';const factory=element.querySelector('[name="factory_id"]');for(const option of factory.options)option.disabled=Boolean(option.dataset.system&&option.dataset.system!==values.system_id);if(factory.selectedOptions[0]?.disabled){factory.value='*';values.factory_id='*';}}else{const attributes=element.querySelector('[name="attributes"]');try{const parsed=JSON.parse(attributes.value);attributes.setCustomValidity(parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?'':'JSON 객체를 입력해 주세요.');}catch(_){attributes.setCustomValidity('유효한 JSON 객체를 입력해 주세요.');}}};
    element.addEventListener('input',collect);element.addEventListener('change',collect);collect();
    if(!await pending||at!==context())return;
    const body=kind==='factory'?{action:'save_factory',factory_id:values.factory_id,system_id:values.system_id,name:values.name,attributes:JSON.parse(values.attributes)}:{action:'save_access',access_id:values.access_id,system_id:values.system_id,factory_id:values.factory_id,principal_kind:values.principal_kind,principal_id:values.principal_kind==='group'?values.group_id:values.principal_id,roles:values.roles,active:values.active};
    await mutate({...body,expected_revision:record?.revision || 0});
  }
  function stageJob(id){
    const run=state?.run,definition=run?.definition,node=definition?.nodes?.[id],stage=workStageTarget(state,selection);
    if(!run||selection.mode!=='work'||!stage||node?.type!=='j'||!workUI.lineage(id,definition).some(parent=>parent.id===stage.id))return null;
    return {run,node,saved:run.jobs?.[id] || {},definition};
  }
  function positionStageMenu(){
    if(!selection.stage_verdict_job)return;
    const menu=source()?.hosts?.()?.panel?.querySelector?.('#ees-stage-verdict-menu');if(!menu?.getBoundingClientRect)return;
    const panel=menu.parentElement,trigger=[...(panel?.querySelectorAll('[data-action="stage_verdict"]') || [])].find(item=>item.dataset.jobId===selection.stage_verdict_job);
    if(!trigger?.getBoundingClientRect)return;
    const bounds=panel.getBoundingClientRect(),anchor=trigger.getBoundingClientRect(),rect=menu.getBoundingClientRect();
    const top=anchor.bottom+6+rect.height<=bounds.bottom-8?anchor.bottom+6:anchor.top-6-rect.height;
    menu.style.left=Math.max(8,Math.min(anchor.left-bounds.left,bounds.width-rect.width-8))+'px';
    menu.style.top=Math.max(8,top-bounds.top)+'px';
  }
  function closeStageMenu(restoreFocus=false){
    const id=selection.stage_verdict_job;if(!id)return;selection.stage_verdict_job='';render();
    if(restoreFocus)[...(source()?.hosts?.()?.panel?.querySelectorAll?.('[data-action="stage_verdict"]') || [])].find(item=>item.dataset.jobId===id)?.focus?.({preventScroll:true});
  }
  function stageMenuEvent(event){
    if(!selection.stage_verdict_job)return false;
    const target=event.target,inMenu=target.closest?.('#ees-stage-verdict-menu');
    if(event.type==='click'&&!inMenu&&!target.closest?.('[data-action="stage_verdict"]')){closeStageMenu();return false;}
    if(event.type!=='keydown'||!inMenu&&!target.closest?.('[data-action="stage_verdict"]'))return false;
    if(event.key==='Escape'||event.key==='Tab'){closeStageMenu(true);if(event.key==='Escape'){event.preventDefault();event.stopPropagation();}return event.key==='Escape';}
    if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
      const options=[...(source()?.hosts?.()?.panel?.querySelectorAll?.('#ees-stage-verdict-menu [role="menuitemradio"]') || [])];if(!options.length)return false;
      const at=options.indexOf(target),next=event.key==='Home'?0:event.key==='End'?options.length-1:(at+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;
      options[next].focus();event.preventDefault();event.stopPropagation();return true;
    }
    return false;
  }
  async function stageAction(action,target){
    const data=target.dataset;
    if(action==='stage_open'){
      if(state?.run?.definition?.nodes?.[data.nodeId]?.type!=='t')return;
      return select({stage_id:data.nodeId,stage_overview:false,stage_tab:'work',stage_evidence:'',stage_tool:'',stage_verdict_job:'',job_id:'',tab:'overview'},{fetch:false});
    }
    if(action==='stage_back')return select({stage_id:'',stage_overview:true,stage_verdict_job:'',job_id:'',tab:'overview'},{fetch:false});
    if(!workStageTarget(state,selection))return;
    if(action==='stage_tab'){if(!['work','log','rules'].includes(data.tab))return;selection.stage_tab=data.tab;selection.stage_verdict_job='';render();remember();return;}
    if(action==='stage_approved'){selection.stage_approved_expanded=!selection.stage_approved_expanded;render();remember();return;}
    const current=stageJob(data.jobId);if(!current)return;
    const {run,node,saved,definition}=current;
    if(action==='stage_evidence'){if(data.attemptId){if(!(run.attempts || []).some(attempt=>attempt.id===data.attemptId&&attempt.job_id===node.id))return;selection.stage_attempts={...(selection.stage_attempts || {}),[node.id]:data.attemptId};selection.stage_tab='work';selection.stage_evidence=node.id;}else selection.stage_evidence=selection.stage_evidence===node.id?'':node.id;selection.stage_tool='';selection.stage_verdict_job='';render();return;}
    if(action==='stage_tool'){selection.stage_evidence=node.id;selection.stage_tool=selection.stage_tool===data.toolKey?'':data.toolKey;render();return;}
    if(action==='stage_execute'){
      if(busy||!workStageCanExecute(node,saved,run,state)||!inputsSaved(true))return;
      setBusy(true);try{const model=executionModel();await operationsCommand({action:'execute_job',run_id:run.id,job_id:node.id,expected_revision:run.revision,...(model?{model_id:model}:{})});await refresh();}finally{setBusy(false);}return;
    }
    if(!workStageCanDecide(node,saved,run))return;
    if(action==='stage_verdict'){
      selection.stage_verdict_job=selection.stage_verdict_job===node.id?'':node.id;render();
      if(selection.stage_verdict_job)source()?.hosts?.()?.panel?.querySelector?.('#ees-work-content')?.addEventListener?.('scroll',()=>closeStageMenu(),{once:true});
      const menu=source()?.hosts?.()?.panel?.querySelector?.('#ees-stage-verdict-menu');(menu?.querySelector?.('[aria-checked="true"]') || menu?.querySelector?.('[role="menuitemradio"]'))?.focus?.({preventScroll:true});return;
    }
    if(action==='stage_decide'){
      if(busy||!inputsSaved(true))return;
      const judgment=workStageJudgments(node,definition).find(item=>String(item.id)===(data.judgmentId || data.verdict)&&String(item.status)===data.verdict);
      if(!judgment)return;
      const existing=workStageDecision(node,saved,definition);if(existing?.judgment_id===judgment.id)return closeStageMenu(true);
      selection.stage_verdict_job='';selection.stage_approved_expanded=true;
      await mutate({action:(node.mode || 'human')==='human'?'human_confirm':'decide',run_id:run.id,job_id:node.id,item_id:'job',expected_revision:run.revision,result_revision:saved.result_revision,verdict:judgment.status,...(!judgment.legacy?{judgment_id:judgment.id}:{})});
      [...(source()?.hosts?.()?.panel?.querySelectorAll?.('[data-action="stage_verdict"]') || [])].find(item=>item.dataset.jobId===node.id)?.focus?.({preventScroll:true});return;
    }
  }
  async function handleClick(target){
    const action=target.dataset.action;if(!action)return;
    if(action.startsWith('stage_'))return stageAction(action,target);
    if(action==='panel_width'){const width=Number(target.dataset.width);if(Number.isFinite(width)){selection.panel_width=Math.max(400,Math.min(720,Math.round(width)));if(!restored)initialSelectionPatch={...initialSelectionPatch,panel_width:selection.panel_width};remember(selection.panel_width);render();}return;}
    if(action==='category'){const value=target.dataset.category;if(!Object.hasOwn(workUI.categories,value))return;const collapsed=new Set(selection.collapsed || []);if(target.dataset.open==='true')collapsed.delete(value);else collapsed.add(value);selection.collapsed=[...collapsed];remember();return;}
    if(action==='procedure_question'){
      const current=designer.readStartContext?.(),index=Number(target.dataset.questionIndex),fallback=workUI.procedureQuestions[index];
      if(!current||!Number.isInteger(index)||!fallback||selection.mode!=='author')return;
      return askHelp(typeof target.dataset.question==='string'?target.dataset.question:fallback,current);
    }
    if(action==='open_reference')return openMessageReference(target.dataset.messageId);
    if(action==='add_list_item')return addListItem();
    if(action==='confirm_list')return confirmList();
    if(action==='save_list_selection')return confirmList(false);
    if(action==='save_review_draft')return saveReviewDraft();
    if(action==='workflow_records')return select({tab:'records',job_id:'',records_workflow:selection.workflow_id});
    if(action==='all_records')return select({tab:'records',records_workflow:'',workflow_id:'',run_id:'',job_id:''});
    if(action==='ask_record'){const run=state?.run,attempts=(run?.attempts || []).filter(attempt=>!target.dataset.jobId||attempt.job_id===target.dataset.jobId).slice().sort((a,b)=>String(a.created_at || '').localeCompare(String(b.created_at || ''))||a.number-b.number),attempt=target.dataset.attemptId?attempts.find(item=>item.id===target.dataset.attemptId):attempts.at(-1);if(!run||!attempt)throw new Error('참고할 당시 실행 기록이 없습니다.');selection.chat_reference={kind:'workspace',reference_kind:'historical',workflow_id:run.workflow_id,run_id:run.id,job_id:attempt.job_id,attempt_id:attempt.id,version:run.version,result_revision:attempt.number,created_at:attempt.created_at,revision:run.revision,system_id:run.system_id,factory_id:run.factory_id};remember();render();source()?.focusComposer?.();return;}
    if(action==='apply_input_proposal')return applyInputProposal();
    if(action==='discard_input_proposal'){pendingInputProposal=null;if(error===pendingInputMessage)error='';render();return;}
    if(action==='export_json'||action==='export_text'||action==='export_result'){if(action==='export_result'&&!workUI.finished(state?.run)&&state?.run?.jobs?.[selection.job_id]?.can_decide!==false&&!await saveReviewDraft())return;return downloadRun(action==='export_json'?'json':'text',action==='export_result'?target.dataset.jobId:'');}
    if(action==='open_legacy')return openLegacy(target.dataset.caseId);
    if(action==='admin_work_tool')return setupWorkTool();
    if(['workspace_admin','mode','procedures','tools','my_work','records','chats'].includes(action)){const patch=navigationPatch(target.dataset);if(patch)return select(patch,{fetch:action!=='chats'});return;}
    if(action==='admin_factory'||action==='admin_access')return adminDialog(action==='admin_factory'?'factory':'access',target.dataset.id);
    if(action==='choose_factory'||action==='choose_system'){
      const factory=action==='choose_factory',id=factory?target.dataset.factoryId:target.dataset.systemId;
      const catalog=nativePage()?nativeScope:state;
      const item=(factory?catalog?.factories:catalog?.systems)?.find(value=>(typeof value==='string'?value:value.id)===id);
      const option=(factory?catalog?.scope_options?.factories:catalog?.scope_options?.systems)?.find(value=>value.id===id);
      if(typeof id!=='string'||factory&&(nativePage()||selection.mode==='author')||!(factory&&id==='')&&(!item||item.allowed===false||option?.allowed===false))return;
      if(id===selection[factory?'factory_id':'system_id'])return;
      designer.readDraft?.();
      const author=nativePage()||selection.mode==='author';
      return select({[factory?'factory_id':'system_id']:id,...(!factory?{factory_id:''}:{}),...(author?{mode:'author'}:{}),workflow_id:'',run_id:'',job_id:'',tab:author?'overview':'my_work'});
    }
    if(action==='workflow'){const id=target.dataset.workflowId,workflow=(state?.workflows || []).find(item=>item.id===id),adhoc=(workflow?.execution_mode || workflow?.mode || 'on_demand')==='on_demand';const runs=(state?.runs || []).filter(run=>run.workflow_id===id&&!workUI.finished(run));return select({workflow_id:id,run_id:!adhoc&&runs.length===1?runs[0].id:'',job_id:'',tab:'overview',panel_open:true});}
    if(action==='open_task'){
      if(target.dataset.scheduleId){const item=state.operations?.schedules?.find(value=>value.id===target.dataset.scheduleId);if(!item)return;if(await confirmDialog({title:'예약 실행 결과를 확인하셨나요?',html:'<p>실패·놓친 예약을 확인한 사실을 기록합니다. 실행 성공이나 재실행을 뜻하지 않습니다.</p>',confirmLabel:'확인 기록'})){await operationsCommand({action:'schedule_check',schedule_id:item.id,slot_id:target.dataset.taskId,expected_revision:item.revision});await refresh();}return;}
      await select({workflow_id:target.dataset.workflowId,run_id:target.dataset.runId,job_id:target.dataset.jobId,mode:'work',tab:'current',panel_open:true});
      const job=state?.run?.jobs?.[target.dataset.jobId];if(job&&!job.claim_actor&&state.run.sharing?.group_ids?.length&&await confirmDialog({title:'이 작업을 맡을까요?',html:'<p>목록을 여는 것만으로 담당자가 지정되지는 않습니다.</p>',confirmLabel:'담당하기'}))await mutate({action:'claim_task',run_id:selection.run_id,job_id:selection.job_id});return;
    }
    if(action==='open_run')return select({workflow_id:target.dataset.workflowId,run_id:target.dataset.runId,job_id:'',mode:'work',tab:'overview',panel_open:true});
    if(action==='job')return select({job_id:target.dataset.jobId,tab:'current'});
    if(action==='overview')return select({job_id:'',tab:'overview'},{fetch:false});
    if(action==='tab')return select({tab:target.dataset.tab},{fetch:false});
    if(action==='close_panel'||action==='open_panel')return setPanelOpen(action==='open_panel');
    if(action==='refresh')return refresh();
    if(action==='reload_options')return loadOptions(target.dataset.fieldId);
    if(action==='discard_inputs'){if(!view.readInputs().settings)inputProposalApplied=null;view.discardInputs();render();return;}
    if(action==='save_inputs')return saveInputs();
    if(action==='native_open')return openNative(target.dataset.nativeId);
    if(action==='new_chat'){return source()?.newChat?.();}
    if(action==='start_run'){
      const at=context(),workflow=state?.workflow;let version=workflow?.published_version,groups=[],link=false;
      if(target.dataset.startInline!==undefined){const form=$('#ees-work-start');if(!form||[...form.querySelectorAll('input,select,textarea')].some(field=>!field.reportValidity()))return;const def=workflow.definition || workflow.published?.definition || workflow.draft,factory=def.execution_scope==='system'?'':($('#ees-start-factory')?.value || ''),inputs=workReadInputs(form);const result=await mutate({action:'start_run',expected_revision:workflow.revision,workflow_id:workflow.id,factory_id:factory,version,inputs,sharing:{group_ids:[...form.querySelectorAll('[data-start-group]:checked')].map(field=>field.value)}},{refreshAfter:false});if(result&&at===context()){const id=result.run?.id || result.run_id || result.id;delete selection.start_inputs?.[workflow.id];await select({factory_id:factory,run_id:id,tab:'overview'});}return;}
      const pending=dialog({title:'진행 건 시작',note:'선택한 게시 버전과 이번 진행 건을 따로 보존합니다.',html:`<label>게시 버전<select id="ees-start-version">${(workflow?.versions || []).map(item=>`<option value="${item.version}"${item.version===version?' selected':''}>v${item.version} · ${esc(item.published_at || '')}</option>`).join('')}</select></label><fieldset><legend>함께 처리할 Native 그룹</legend><p class="ew-muted">선택하지 않으면 개인 진행 건입니다. 개인 대화 내용은 공유하지 않습니다.</p>${(state.native_groups || []).map(group=>`<label><input type="checkbox" data-start-group value="${esc(group.id)}">${esc(group.name || group.id)}</label>`).join('') || '<p>현재 참여 중인 그룹이 없습니다.</p>'}</fieldset>${chatId()?'<label><input type="checkbox" id="ees-start-chat-link">현재 개인 대화를 이 진행 건에 연결</label>':''}`,confirmLabel:'진행 건 시작'});
      $('#ees-work-dialog').addEventListener('change',()=>{version=Number($('#ees-start-version').value);groups=[...document.querySelectorAll('[data-start-group]:checked')].map(field=>field.value);link=Boolean($('#ees-start-chat-link')?.checked);});
      if(!await pending||at!==context())return;
      const result=await mutate({action:'start_run',expected_revision:workflow.revision,workflow_id:selection.workflow_id,factory_id:selection.factory_id,version,inputs:{},sharing:{group_ids:groups}},{refreshAfter:false});if(result){const id=result.run?.id || result.run_id || result.id;await select({run_id:id,tab:'overview'});if(link)await mutate({action:'link_chat',run_id:id,chat_id:chatId()});}return;
    }
    if(action==='execute_scope'){if(busy||!inputsSaved(true))return;setBusy(true);try{const model=executionModel();await operationsCommand({action:'execute_scope',run_id:selection.run_id,node_id:target.dataset.nodeId,expected_revision:state.run.revision,...(model?{model_id:model}:{})});await refresh();}finally{setBusy(false);}return;}
    if(action==='shared_accept_version'){if(busy)return;const item=state.operations?.shared_tools?.find(item=>item.id===target.dataset.sharedId);if(!item)return;if(!await confirmDialog({title:'이 회차에서 v'+item.version+'으로 계속할까요?',html:'<p>이 회차에서 같은 도구를 쓰는 다음 실행부터 새 버전을 사용합니다. 이미 남긴 실행 기록은 그대로 유지됩니다.</p>',confirmLabel:'새 버전으로 계속'}))return;await operationsCommand({action:'shared_tool_accept_version',run_id:selection.run_id,shared_tool_id:item.id,version:item.version,expected_revision:state.run.revision});await refresh();return;}
    if(action==='execute'){if(busy||!inputsSaved())return;setBusy(true);try{const model=executionModel();await operationsCommand({action:'execute_job',run_id:selection.run_id,job_id:selection.job_id,expected_revision:state.run.revision,...(model?{model_id:model}:{})});await refresh();}finally{setBusy(false);}return;}
    if(action==='retry_private_save'){remember();return;}
    if(action==='confirm_verdicts'){
      if(busy||!inputsSaved())return;const at=context(),run=state.run,jobId=selection.job_id,saved=run.jobs[jobId],key=run.id+'/'+jobId+'/'+saved.attempt_id,draft=selection.verdict_drafts?.[key] || {},items=saved.result?.items || [];
      if(!items.length||items.some(item=>!saved.decisions?.[item.id]&&!draft[item.id]?.verdict))throw new Error('모든 항목의 판정을 직접 선택해 주세요.');
      if(!await confirmDialog({title:'선택한 판정을 확정할까요?',html:`<p>${items.length}개 항목의 판정을 최종 반영합니다. 확정 뒤에는 현재 판정을 수정하지 않습니다.</p>`,confirmLabel:'판정 확정'})||at!==context())return;
      const result=await mutate({action:'confirm_verdicts',run_id:run.id,job_id:jobId,attempt_id:saved.attempt_id,result_revision:saved.result_revision,expected_revision:run.revision,verdicts:items.map(item=>({item_id:item.id,verdict:saved.decisions?.[item.id]?.verdict || draft[item.id].verdict,...(draft[item.id]?.judgment_id?{judgment_id:draft[item.id].judgment_id}:{}),...(draft[item.id]?.note?{note:draft[item.id].note}:{})}))});if(result){delete selection.verdict_drafts?.[key];remember();render();}return;
    }
    if(action==='confirm'){
      if(busy||!inputsSaved())return;if(state?.run?.definition?.nodes?.[selection.job_id]?.result_block==='ai_review'&&!await saveReviewDraft())return;const selectedRun=state?.run,selectedJob=selection.job_id;
      const delivery=selectedRun?.definition?.nodes?.[selectedJob]?.completion?.kind==='delivery';
      if(!await confirmDialog({title:delivery?'본문 검토를 확정할까요?':'결과와 근거를 확인하셨나요?',html:'<p>사람의 판정이 실행 당시 결과에 연결되어 저장됩니다. AI 제안은 자동 확정하지 않습니다.</p>'+(delivery?'<p>본문 검토를 저장해도 송부하거나 업무를 완료하지 않습니다. 실제 송부와 결과 확인은 별도입니다.</p>':''),confirmLabel:delivery?'본문 검토 확정':'확인 완료'}))return;
      const node=selectedRun?.definition?.nodes?.[selectedJob],job=selectedRun?.jobs?.[selectedJob];return mutate({action:node?.mode==='human'?'human_confirm':'decide',run_id:selectedRun.id,job_id:selectedJob,expected_revision:selectedRun.revision,item_id:'job',result_revision:job?.result_revision,...(job?.review_draft?{review_revision:job.review_draft.revision}:{}),verdict:'completed'});
    }
    if(action==='release_task'){const at=context(),run=state.run,job=selection.job_id;if(run?.jobs?.[job]?.claim_actor!==state.capabilities?.actor_id)return;if(await confirmDialog({title:'맡은 작업을 내려놓을까요?',html:'<p>진행 중인 실행과 결과 불명 요청은 먼저 확인해야 합니다. 다른 참여자는 본인의 현재 권한으로 근거를 다시 조회할 수 있습니다.</p>',confirmLabel:'맡기 해제'})&&at===context())return mutate({action:'release_task',run_id:run.id,job_id:job,expected_revision:run.revision});return;}
    if(action==='amend_items')return amendItems();
    if(action==='request_intent')return requestIntent();
    if(action==='approve_request'||action==='reconcile_request'){if(busy)return;setBusy(true);try{await operationsCommand({action:action==='approve_request'?'request_approve':'request_reconcile',external_request_id:target.dataset.requestId,expected_revision:Number(target.dataset.requestRevision)});await refresh();}finally{setBusy(false);}return;}
    if(action==='close_run'||action==='cancel_run'){const at=context(),run=state.run;let reason='';const pending=dialog({title:action==='close_run'?'이 진행 건을 종료할까요?':'이 진행 건을 취소할까요?',html:'<p>종료 후에는 이 진행 건의 당시 버전과 기록을 읽기 전용으로 보존합니다.</p>'+(action==='cancel_run'?'<label>취소 이유<input id="ees-cancel-reason" required></label>':''),confirmLabel:action==='close_run'?'진행 건 종료':'진행 건 취소'});$('#ees-cancel-reason')?.addEventListener('input',event=>{reason=event.target.value;});if(await pending&&at===context())return mutate({action,run_id:run.id,expected_revision:run.revision,...(reason?{reason}:{})});}
  }
  async function sourceAction(dataset){
    if(!dataset||typeof dataset!=='object')return;
    try{if(nativePage()&&!['native_open','refresh','category','choose_system'].includes(dataset.action)){return await returnFromNative({dataset});}return await handleClick({dataset});}
    catch(failure){error=failure.message;render();}
  }
  function handleEvent(event){
    if(stageMenuEvent(event)||workUI.menuEvent(event))return;
    const author=designer.handleEvent?.(event);if(author?.handled){if(author.preventDefault){event.preventDefault();if(event.type==='keydown'&&event.key==='Escape')event.stopPropagation();}return;}
    const target=event.target;if(event.type==='submit'&&target.closest?.('[data-ees-work]')){event.preventDefault();return;}if(event.type==='keydown'&&event.repeat&&target.closest?.('[data-mutation]')){event.preventDefault();event.stopImmediatePropagation();return;}if(!target?.closest?.('[data-ees-work]'))return;
    if(event.type==='click'){const buttonTarget=target.closest('button[data-action]');if(!buttonTarget||buttonTarget.disabled)return;event.preventDefault();if(nativePage()&&buttonTarget.closest('#ees-work-entry')&&!['native_open','refresh'].includes(buttonTarget.dataset.action)){returnFromNative(buttonTarget);return;}Promise.resolve(handleClick(buttonTarget)).catch(failure=>{error=failure.message;render();});}
    if(event.type==='input'){
      if(target.closest?.('#ees-work-start')){const form=target.closest('#ees-work-start');selection.start_inputs ||= {};selection.start_inputs[selection.workflow_id]=workReadInputs(form);selection.start_groups ||= {};selection.start_groups[selection.workflow_id]=[...form.querySelectorAll('[data-start-group]:checked')].map(field=>field.value);remember();return;}
      if(target.id==='ees-request-reason'){selection.request_reasons ||= {};selection.request_reasons[selection.run_id+'/'+selection.job_id]=target.value;remember();return;}
      if(target.id==='ees-review-text'){view.capture();scheduleReviewSave();}
    }
    if((event.type==='input'||event.type==='compositionend'&&inputProposalApplied&&selection.tab==='current')&&target.matches?.('[data-work-input]')){
      view.capture();clearTimeout(optionTimer);
      const applied=inputProposalApplied&&selection.tab==='current';
      if(applied&&event.isComposing)return;
      if(applied){
        // Keep this proposal identity for any in-flight save acknowledgement.
        delete inputProposalApplied.values[target.name];
        if(!Object.keys(inputProposalApplied.values).length)inputProposalApplied=null;
        render();
      }
      optionTimer=setTimeout(()=>loadOptions(),300);
    }
    if(event.type==='change'&&target.matches?.('[data-stage-attempt]')){const current=stageJob(target.dataset.jobId);if(!current||!(current.run.attempts || []).some(attempt=>attempt.id===target.value&&attempt.job_id===current.node.id))return;selection.stage_attempts={...(selection.stage_attempts || {}),[current.node.id]:target.value};selection.stage_tool='';render();return;}
    if(event.type==='change'&&target.id==='ees-start-factory'){select({factory_id:target.value,start_factory_id:target.value});return;}
    if(event.type==='change'&&target.matches?.('[data-item-verdict]')){const saved=state?.run?.jobs?.[selection.job_id];if(!saved||saved.can_decide===false||saved.decisions?.[target.dataset.itemId])return;const key=selection.run_id+'/'+selection.job_id+'/'+saved.attempt_id;selection.verdict_drafts ||= {};selection.verdict_drafts[key] ||= {};const option=target.selectedOptions?.[0];selection.verdict_drafts[key][target.dataset.itemId]={verdict:option?.dataset.verdict || target.value,...(option?.dataset.judgmentId?{judgment_id:option.dataset.judgmentId}:{})};remember();render();return;}
    if(event.type==='change'&&target.matches?.('[data-list-include]')){view.refreshResults();return;}
    if(event.type==='change'&&(target.matches?.('[data-item-verdict]')||target.matches?.('[data-item-confirm]'))){const verdict=target.matches('[data-item-confirm]')?(target.checked?'completed':'unknown'):target.value;if(verdict)mutate({action:'decide',run_id:selection.run_id,job_id:selection.job_id,item_id:target.dataset.itemId,result_revision:state?.run?.jobs?.[selection.job_id]?.result_revision,verdict});}
  }
  function reset(){helpWriting=null;nativeCapabilities=null;nativeScope=null;workspaceCache.clear();stateKey='';targetLoading=false;scopeLoading=false;evidenceUnavailable=false;readyRoute='';pendingNativeAction=null;clearNativeTicket();nativeNavigationBusy=false;procedureStart=null;workUI.closeHelp({restoreFocus:false});reviewSaving=null;clearTimeout(reviewTimer);clearTimeout(referenceTimer);referenceTimer=null;referenceRead++;referenceChat='';messageReferences.clear();clearMessageReferences();epoch++;workEpoch++;serial++;chatCreations.clear();chatAliases.clear();clearTimeout(refreshTimer);clearTimeout(uiTimer);state=null;pendingInputProposal=null;inputProposalApplied=null;error='';commandError='';receipts.clear();optionCache.clear();clearTimeout(optionTimer);view.reset();designer.reset();restored=false;initialSelectionPatch=null;uiRevision=0;source()?.modelCount?.(0);selection={mode:'work',tab:'my_work',panel_open:true,system_id:'',factory_id:'',workflow_id:'',run_id:'',job_id:'',collapsed:[]};}
  function sync(){
    scheduled=false;bindHosts();syncHelpState();const auth=token();if(auth!==identity){reset();identity=auth;route='';}
    syncNativeReturn();
    if(!screenAvailable()){
      if(!auth||/^\/(auth|logout)(\/|$)/.test(location.pathname)){if(state)reset();}
      else if(route){epoch++;serial++;clearTimeout(refreshTimer);clearTimeout(uiTimer);view.suspend?.();}
      route='';readyRoute='';return;
    }
    const current=location.pathname+location.search+(nativePage()?'#native':'#chat');
    if(route!==current){
      workUI.closeHelp({restoreFocus:false});for(const [key,alias] of chatAliases)if(alias.chat_id!==chatId())chatAliases.delete(key);
      route=current;readyRoute='';epoch++;applyNativeDestination();render();
      refresh().then(()=>resumeNativeAction()).catch(failure=>{error=failure.message;render();});
      if(available())models().catch(()=>{});
    }else{if(nativePage()||chatPrepared())view.sync(snapshot());resumeNativeAction().catch(failure=>{error=failure.message;render();});}
    if(available())syncMessageReferences();
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(sync);}}
  const boundHosts=new Set(),renderedReferenceHosts=new Set(),eventTypes=['click','input','compositionend','change','toggle','keydown','submit'];
  function bindHosts(){
    // Visible message cards remain owned hosts between reference polls.
    const hosts=source()?.hosts?.() || {},current=new Set([hosts.panel,hosts.overlays,...[...renderedReferenceHosts].filter(host=>host.isConnected)].filter(Boolean));
    for(const host of boundHosts)if(!current.has(host)){for(const type of eventTypes)host.removeEventListener(type,handleEvent,true);boundHosts.delete(host);}
    for(const host of current)if(!boundHosts.has(host)){for(const type of eventTypes)host.addEventListener(type,handleEvent,true);boundHosts.add(host);}
  }
  // Source lifecycle explicitly publishes route/account/ready changes.
  // No observer, document event interception or history monkey patch is needed.

  window.__eesNativeWork=true;
  const reference=()=>!chatPrepared()||nativeReturnPreview()||targetLoading||evidenceUnavailable?{kind:'none'}:available()&&selection.mode==='author'&&(selection.tab==='tools'||designer.readStartContext?.())?{kind:'help',system_id:selection.system_id || '',context_id:context()}:available()&&selection.chat_reference&&selection.chat_reference.run_id===state?.run?.id?{...clone(selection.chat_reference),context_id:context()}:available()&&(state?.workflow||state?.run)&&selection.workflow_id?{kind:'workspace',workflow_id:selection.workflow_id,run_id:selection.run_id,job_id:selection.job_id,system_id:state?.run?.system_id || selection.system_id,factory_id:state?.run?.factory_id ?? selection.factory_id,version:state?.run?.version ?? state?.workflow?.published_version,workflow_revision:state?.workflow?.revision,attempt_id:state?.run?.jobs?.[selection.job_id]?.current_attempt,result_revision:state?.run?.jobs?.[selection.job_id]?.result_revision,revision:state?.run?.revision ?? state?.workflow?.revision ?? 0,created_at:state?.run?.updated_at ?? state?.workflow?.updated_at,context_id:context()}:{kind:'none'};
  function clearMessageReferences(){for(const host of renderedReferenceHosts)host.replaceChildren();renderedReferenceHosts.clear();}
  function renderMessageReferences(){
    if(!chatId()||referenceChat!==chatId())return;
    for(const host of renderedReferenceHosts)if(!host.isConnected)renderedReferenceHosts.delete(host);
    for(const [id,reference] of messageReferences){
      const host=source()?.referenceHost?.(id),html=workMessageReferenceHTML(reference,id);if(!host||!html)continue;
      renderedReferenceHosts.add(host);if(host.innerHTML!==html)host.innerHTML=html;
      if(!boundHosts.has(host)){for(const type of eventTypes)host.addEventListener(type,handleEvent,true);boundHosts.add(host);}
    }
  }
  async function readMessageReferences(){
    referenceTimer=null;const id=chatId(),auth=token(),n=++referenceRead;if(!id||!available())return;
    try{const response=await fetch('/api/v1/chats/'+encodeURIComponent(id),{headers:{Accept:'application/json',Authorization:'Bearer '+auth},credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error('Native 대화 참조 조회 실패');const result=await response.json();if(id!==chatId()||auth!==token()||n!==referenceRead)return;
      const messages=Object.values(result.chat?.history?.messages || {}),next=new Map();for(const message of messages){const ref=message.meta?.ees_work_reference;if(message.id&&ref?.kind==='workspace'&&ref.workflow_id)next.set(message.id,clone(ref));}
      referenceChat=id;messageReferences=next;renderMessageReferences();
    }catch(_){if(id===chatId()&&auth===token()&&n===referenceRead){referenceChat=id;messageReferences.clear();clearMessageReferences();}}
  }
  function syncMessageReferences(){
    if(referenceChat!==chatId()){referenceChat=chatId();messageReferences.clear();clearTimeout(referenceTimer);referenceTimer=null;referenceRead++;}
    renderMessageReferences();if(chatId()&&referenceTimer===null)referenceTimer=setTimeout(readMessageReferences,700);
  }
  async function openMessageReference(id){
    const ref=messageReferences.get(id);if(!ref||referenceChat!==chatId())throw new Error('이 대화의 업무 참조를 다시 확인해 주세요.');
    const copied={workflow_id:ref.workflow_id,run_id:ref.run_id || '',job_id:ref.job_id || '',attempt_id:ref.attempt_id,version:ref.version,result_revision:ref.result_revision};
    return select({mode:'work',tab:'historical_reference',panel_open:true,workflow_id:ref.workflow_id,run_id:ref.run_id || '',job_id:ref.job_id || '',system_id:ref.system_id || selection.system_id,factory_id:ref.factory_id || '',historical_reference:copied});
  }
  function chatBoundary(){
    const draft=selection.mode==='author'?designer.readDraft?.():null;
    return JSON.stringify([workEpoch,selection.mode,selection.system_id,selection.factory_id,selection.workflow_id,selection.run_id,selection.job_id,state?.run?.revision ?? state?.workflow?.revision ?? 0,draft?.revision,draft?.definition]);
  }
  function beginChatCreation(){
    if(!available()||chatId()||!blankChatPath(location.pathname))return '';
    const id=workUI.newId();chatCreations.set(id,{actor:token(),context_id:context(),path:location.pathname+location.search,boundary:chatBoundary()});
    while(chatCreations.size>8)chatCreations.delete(chatCreations.keys().next().value);return id;
  }
  function finishChatCreation(id,createdChatId){
    const captured=chatCreations.get(id);chatCreations.delete(id);
    const returning=nativeTicketCurrent(nativeTicket)&&blankChatPath(nativeTicket.path)&&nativeTicket.path===captured?.path;
    if(!captured||typeof createdChatId!=='string'||!createdChatId||captured.actor!==token()||captured.boundary!==(returning?nativeTicket.boundary:chatBoundary())||(chatId()&&chatId()!==createdChatId)||(!chatId()&&!blankChatPath(location.pathname)&&!returning))return;
    chatAliases.set(captured.context_id,{...captured,chat_id:createdChatId});
    while(chatAliases.size>8)chatAliases.delete(chatAliases.keys().next().value);
  }
  function chatCreated(id){
    // Only the source Chat calls this after accepting its own first-chat ID.
    // A late completion may update the return destination without leaving Native.
    const ticket=nativeTicket;
    if(typeof id!=='string'||!id||id.length>200||/[/?#]/.test(id)||!nativeTicketCurrent(ticket)||!blankChatPath(ticket.path))return false;
    const previous=ticket.path,next='/c/'+encodeURIComponent(id);ticket.path=next;
    if(pendingNativeAction?.auth===ticket.auth&&pendingNativeAction.actor===ticket.actor&&pendingNativeAction.path===previous)pendingNativeAction.path=next;
    return true;
  }
  function acceptNativeProposal(id,payload){
    if(id!==chatId()||!available()||selection.chat_reference)return {ok:false,code:'context_changed'};
    if(payload?.context_id!==context()){
      const alias=chatAliases.get(payload?.context_id);
      if(!alias||alias.actor!==token()||alias.chat_id!==id||alias.boundary!==chatBoundary())return {ok:false,code:'context_changed'};
    }
    if(payload?.proposal_kind==='inputs')return previewInputProposal(payload);
    if(selection.mode==='author')designer.render({state,selection:{...clone(selection),chat_id:id},host:view.authoringHost()});
    return designer.acceptProposal(payload,{chatId:id});
  }
  window.__eesNativeWorkV1=Object.freeze({sync:schedule,action:sourceAction,dismissHelp:workUI.dismissHelp,refresh,open:()=>setPanelOpen(true),selection:id=>id===chatId()?{ok:true,...reference()}:{ok:false,code:'selection_unconfirmed'},captureReference:()=>reference(),helpContext:()=>available()&&chatPrepared()&&!nativeReturnPreview()?{context_id:context(),system_id:selection.system_id || ''}:null,chatCreated,beginChatCreation,finishChatCreation,ensureChat:async()=>({ok:true}),refreshActionRecords:()=>{},propose:acceptNativeProposal,display:async(id,options)=>{if(id!==chatId()||!available())return {ok:false};const allowed=['panel_open','workflow_id','run_id','job_id'];if(Object.keys(options || {}).some(key=>!allowed.includes(key)))return {ok:false};const result=await select(options);if(!result||options.workflow_id&&result.workflow?.id!==options.workflow_id||options.run_id&&result.run?.id!==options.run_id||options.job_id&&!result.run?.definition?.nodes?.[options.job_id])return {ok:false};return {ok:true};}});
  schedule();
})();
