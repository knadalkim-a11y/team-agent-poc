/* EES Work: shared schema renderers and the Native conversation's side panels.
 * The server owns business state. This file owns only an actor's display/drafts. */
/* C3 timings live only in CSS. This lifecycle is shared with the Svelte shell.
 * A closing surface releases interaction first; completion owns cleanup/focus. */
const workMotion = (() => {
  const closing=new WeakMap(),opening=new WeakMap(),released=new WeakMap();
  const styleOf=element=>typeof getComputedStyle==='function'?getComputedStyle(element):null;
  function settings(element=document.documentElement){
    const style=styleOf(element),read=name=>style?.getPropertyValue?.(name)?.trim() || '';
    const reduced=Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
    const duration=name=>{const value=read(name),number=parseFloat(value);return reduced||!Number.isFinite(number)?0:Math.max(0,number*(value.endsWith('ms')?1:1000));};
    return {fast:duration('--ees-motion-fast'),open:duration('--ees-motion-open'),close:duration('--ees-motion-close'),openEasing:read('--ees-motion-open-easing'),closeEasing:read('--ees-motion-close-easing'),reduced};
  }
  function restoreInteraction(element){
    const saved=released.get(element);if(!saved)return;
    element.inert=saved.inert;
    if(saved.hidden===null)element.removeAttribute('aria-hidden');else element.setAttribute('aria-hidden',saved.hidden);
    released.delete(element);
  }
  function stopOpening(element){opening.get(element)?.();}
  function cancel(element){
    stopOpening(element);
    const pending=closing.get(element);if(pending){pending.stop();closing.delete(element);pending.resolve(false);}
    restoreInteraction(element);element?.removeAttribute?.('data-ees-motion');
  }
  function capture(element){
    const style=styleOf(element);return {opacity:style?.opacity || '1',transform:style?.transform || 'none'};
  }
  function open(element,{from=null}={}){
    if(!element)return;
    const interrupted=from || (closing.has(element)?capture(element):null);
    cancel(element);
    for(const [key,value] of Object.entries(interrupted || {opacity:'',transform:''})){
      if(value)element.style?.setProperty?.('--ees-motion-from-'+key,value);
      else element.style?.removeProperty?.('--ees-motion-from-'+key);
    }
    // Reset only the surface animation. No width or surrounding layout tween.
    void element.offsetWidth;
    element.setAttribute('data-ees-motion','opening');
    const duration=settings(element).open;if(!duration){element.removeAttribute('data-ees-motion');return;}
    const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');let timer=null;
    const complete=()=>{if(opening.get(element)!==stop)return;stop();if(element.getAttribute('data-ees-motion')==='opening')element.removeAttribute('data-ees-motion');};
    const onEnd=event=>{if(event.target===element&&event.animationName==='ees-motion-open')complete();};
    const onReduced=()=>{if(media?.matches)complete();};
    const stop=()=>{if(timer!==null)clearTimeout(timer);element.removeEventListener('animationend',onEnd);media?.removeEventListener?.('change',onReduced);opening.delete(element);};
    opening.set(element,stop);element.addEventListener('animationend',onEnd);media?.addEventListener?.('change',onReduced);timer=setTimeout(complete,duration+50);
  }
  function finish(element,{restoreFocus=true}={}){closing.get(element)?.finish(restoreFocus);}
  function close(element,{cleanup=()=>{},release=()=>{},restoreFocus=null}={}){
    if(!element)return Promise.resolve(true);
    if(closing.has(element))return closing.get(element).promise;
    const from=capture(element);stopOpening(element);
    const duration=settings(element).close,media=window.matchMedia?.('(prefers-reduced-motion: reduce)');
    for(const [key,value] of Object.entries(from))element.style?.setProperty?.('--ees-motion-from-'+key,value);
    if(!released.has(element))released.set(element,{inert:Boolean(element.inert),hidden:element.getAttribute('aria-hidden')});
    let resolve,timer=null,done=false;const focusAtStart=document.activeElement;
    const promise=new Promise(yes=>{resolve=yes;});
    const stop=()=>{if(timer!==null)clearTimeout(timer);element.removeEventListener('animationend',onEnd);element.removeEventListener('transitionend',onEnd);media?.removeEventListener?.('change',onReduced);};
    const complete=(focus=true)=>{
      if(done||closing.get(element)!==pending)return;done=true;stop();closing.delete(element);
      const active=document.activeElement,focusStillOwned=!active||active===document.body||active===document.documentElement||active===focusAtStart||element.contains?.(active);
      element.removeAttribute('data-ees-motion');cleanup();
      if(focus&&focusStillOwned){if(typeof restoreFocus==='function')restoreFocus();else if(restoreFocus?.isConnected)restoreFocus.focus({preventScroll:true});}
      resolve(true);
    };
    const onReduced=()=>{if(media?.matches)complete();};
    const onEnd=event=>{if(event.target!==element)return;if(event.type==='animationend'&&event.animationName&&!event.animationName.startsWith('ees-motion-close'))return;if(event.type==='transitionend'&&event.propertyName&&!['opacity','transform'].includes(event.propertyName))return;complete();};
    const pending={promise,resolve,stop,finish:complete};closing.set(element,pending);
    element.setAttribute('data-ees-motion','closing');element.inert=true;element.setAttribute('aria-hidden','true');
    element.addEventListener('animationend',onEnd);element.addEventListener('transitionend',onEnd);
    media?.addEventListener?.('change',onReduced);
    release();
    if(duration===0)complete();else timer=setTimeout(complete,duration+50);
    return promise;
  }
  return Object.freeze({settings,open,close,cancel,finish,frame:capture});
})();
window.__eesMotionV1=workMotion;
const workUI = (() => {
  const $ = (selector, parent = document) => parent?.querySelector(selector) || null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  function newId(){
    const provider=globalThis.crypto;
    if(typeof provider?.randomUUID==='function')return provider.randomUUID();
    // Intranet HTTP has getRandomValues but may not expose randomUUID.
    // Keep UUID v4 request/node IDs without weakening randomness or patching Native globals.
    if(typeof provider?.getRandomValues!=='function')throw new Error('요청 번호를 만들 수 없습니다. 지원되는 브라우저에서 다시 시도해 주세요.');
    const bytes=provider.getRandomValues(new Uint8Array(16));
    bytes[6]=(bytes[6]&0x0f)|0x40;bytes[8]=(bytes[8]&0x3f)|0x80;
    const hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  // Keep persisted actor identifiers unchanged; only their product label is current.
  const executionActorLabel = value => value === 'EES Work' ? 'EES Workflow' : value;
  const categories = {ops:'운영',setup:'셋업',incident:'장애대응'};
  const procedureQuestions = Object.freeze(['신규 공장 횡전개 예시를 복사해서 우리 공장에 맞게 고치고 싶어','분류와 실행 방식(주기 · 수시 · 비상)이 뭔지 알려줘','빈 절차로 시작하면 무엇부터 정하나요?']);
  const levels = {p:'업무 절차',t:'단계',j:'작업'};
  const statuses = {open:'진행 중',unstarted:'미실행',pending:'대기',scheduled:'예약',ready:'시작 가능',running:'실행 중',in_progress:'진행 중',awaiting_input:'입력 필요',awaiting_confirmation:'사람 확인 필요',review_required:'다시 검토 필요',completed:'완료',succeeded:'도구 성공',success:'도구 성공',failed:'실패',partial:'부분 결과',unknown:'결과 미확인',missed:'예약 놓침',excluded:'적용 제외',cancelled:'취소',blocked:'진행 조건 확인',draft:'초안',published:'게시됨',review:'검토 필요',waiting:'대기',waiting_input:'입력 필요',waiting_confirmation:'사람 확인 필요',reported_complete:'완료 보고',accepted:'접수',requested:'요청 보냄',effect_verified:'효과 확인'};
  const icon = (name,label='') => `<img class="ew-icon" src="/_ees14/v4/${esc(String(name).replace(/\.svg$/,''))}.svg" alt="${esc(label)}"${label?'':' aria-hidden="true"'}>`;
  const button = (label,action,attrs='') => `<button type="button" data-action="${esc(action)}" ${attrs}>${esc(label)}</button>`;
  const finished = run => ['completed','cancelled'].includes(run?.status);
  const lineage = (id, definition) => {const path=[],seen=new Set();while(id && definition?.nodes?.[id] && !seen.has(id)){seen.add(id);const node=definition.nodes[id];path.unshift(node);id=node.parent;}return path;};
  const badge = status => `<span class="ew-badge" data-status="${esc(status)}">${esc(statuses[status] || status || '미확인')}</span>`;
  const time = value => {if(value===undefined||value===null||value==='')return '';const date=typeof value==='number'?new Date(value*1000):new Date(value);return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date);};
  const safeURL = value => {if(typeof value!=='string'||!value.trim())return '';try{const url=new URL(value,location.origin);return ['https:','http:'].includes(url.protocol)?url.href:'';}catch(_){return '';}};
  let activeDialog=null,activeHelp=null,activeMenu=null;
  const overlayHost=()=>window.__eesSourceShellV1?.hosts?.()?.overlays;
  function mountOverlay(element,trigger=null){const host=trigger&&activeDialog?.contains?.(trigger)?activeDialog:overlayHost();if(!host)throw new Error('업무 화면을 준비한 뒤 다시 시도해 주세요.');host.append(element);}
  function dismissHelp(event){if(activeMenu&&!activeMenu.details.contains(event.target))closeMenu(false);if(activeHelp&&!activeHelp.element.contains(event.target)&&!activeHelp.trigger?.contains?.(event.target))activeHelp.close(false);}
  function closeMenu(restoreFocus=true){
    if(!activeMenu)return;const menu=activeMenu;
    return workMotion.close(menu.content,{release:()=>menu.summary.setAttribute('aria-expanded','false'),cleanup:()=>{menu.details.open=false;if(activeMenu===menu)activeMenu=null;},restoreFocus:restoreFocus?menu.summary:null});
  }
  function menuEvent(event){
    const target=event.target,details=target?.closest?.('.ew-procedure-menu,.ew-shared-picker');
    if(event.type==='click'&&activeMenu&&!activeMenu.details.contains(target))closeMenu(false);
    if(!details)return false;
    if(event.type==='keydown'&&event.key==='Escape'&&details.open){closeMenu();event.preventDefault();event.stopPropagation();return true;}
    const summary=details.querySelector('summary'),content=details.querySelector(':scope > div');if(!summary||!content)return false;
    const opening=()=>{
      if(activeMenu&&activeMenu.details!==details){const old=activeMenu;closeMenu(false);workMotion.finish(old.content,{restoreFocus:false});}
      activeMenu={details,summary,content};content.dataset.eesMotionKind='menu';details.open=true;summary.setAttribute('aria-expanded','true');workMotion.open(content);
    };
    if(event.type==='click'&&summary.contains(target)){
      event.preventDefault();
      if(!details.open||content.getAttribute('data-ees-motion')==='closing')opening();else closeMenu();
      return true;
    }
    // Search repaints may supply a fresh, already-open details node.
    if(event.type==='toggle'&&details.open&&activeMenu?.details!==details){
      if(activeMenu&&!activeMenu.details.isConnected&&activeMenu.details.className===details.className){
        // Filtering repaints an existing popup: retain its visible state without
        // replaying an entrance on every typed character.
        workMotion.cancel(activeMenu.content);activeMenu={details,summary,content};content.dataset.eesMotionKind='menu';summary.setAttribute('aria-expanded','true');
      }else opening();
    }
    if(event.type==='click'&&content.contains(target)&&target.closest?.('button'))closeMenu(false);
    return false;
  }
  const helpQuestion=term=>`EES Workflow 도움말 ‘${term.name || term.id}’의 뜻과 지금 화면에서 쓰는 방법을 알려줘.`;
  function syncHelpState(){if(activeHelp)activeHelp.element.querySelector('[data-help-ask]').disabled=typeof activeHelp.onAsk!=='function'||Boolean(window.__eesSourceShellV1?.helpState?.()?.busy);}
  function closeHelp({restoreFocus=true,immediate=false}={}){if(!activeHelp)return;const element=activeHelp.element;activeHelp.close(restoreFocus);if(immediate)workMotion.finish(element,{restoreFocus});}
  function reanchorHelp(root,context){activeHelp?.reanchor(root,context);}
  function showHelp({termId,help,context={},trigger,onAsk}){
    if(activeHelp?.termId===termId&&activeHelp.trigger===trigger){activeHelp.reopen();return activeHelp.element;}
    closeHelp({restoreFocus:false,immediate:true});
    const terms=Array.isArray(help?.terms)?help.terms:[],term=terms.find(item=>item.id===termId);
    const selected=term || {id:termId,name:'도움말 확인',summary:'도움말에 없는 내용입니다. 담당자에게 확인해 주세요.'};
    const related=(selected.related || []).map(id=>terms.find(item=>item.id===id)).filter(Boolean);
    const element=document.createElement('section'),scrollHosts=[...new Set(Object.values(window.__eesSourceShellV1?.hosts?.() || {}).filter(Boolean))];let previous=trigger || document.activeElement;
    const position=()=>{
      if(!element.isConnected)return;if(trigger&&!trigger.isConnected){closeHelp({restoreFocus:false});return;}
      const viewportWidth=window.innerWidth || document.documentElement.clientWidth,viewportHeight=window.innerHeight || document.documentElement.clientHeight;
      const rect=trigger?.getBoundingClientRect?.() || {left:12,right:viewportWidth-12,top:12,bottom:12};
      const width=Math.min(360,Math.max(0,viewportWidth-24));element.style.width=width+'px';element.style.maxHeight=Math.max(0,viewportHeight-24)+'px';
      element.style.left=Math.max(12,Math.min(rect.right-width,viewportWidth-width-12))+'px';
      const height=element.getBoundingClientRect().height,below=rect.bottom+8;
      element.style.top=Math.max(12,below+height<=viewportHeight-12?below:Math.min(rect.top-height-8,viewportHeight-height-12))+'px';
    };
    element.id='ees-work-help';element.className='ew-help-popover';element.dataset.eesWork='';element.dataset.eesMotionKind='help';element.setAttribute('role','dialog');element.setAttribute('aria-labelledby','ees-work-help-title');
    const aliases=item=>(item.aliases || []).length?`<small>예전 이름: ${esc(item.aliases.join(' · '))}</small>`:'';
    element.innerHTML=`<header><div><strong id="ees-work-help-title">${esc(selected.name)}</strong>${aliases(selected)}</div><button type="button" class="ew-help-close" data-help-close aria-label="도움말 닫기">닫기</button></header><p class="ew-help-summary" id="ees-work-help-body" tabindex="-1">${esc(selected.summary)}</p>${selected.example?`<p class="ew-help-example">예: ${esc(selected.example)}</p>`:''}${related.length?`<section class="ew-help-related"><h3>관련 도움말</h3>${related.map(item=>`<article><div><strong>${esc(item.name)}</strong>${aliases(item)}</div><p>${esc(item.summary)}</p></article>`).join('')}</section>`:''}<p class="ew-help-error" data-help-error role="alert" hidden></p><footer><button type="button" class="ew-help-ask" data-help-ask${typeof onAsk!=='function'?' disabled':''}>${icon('1c98e')}대화창에서 더 묻기</button><small>도움말 · ${esc(selected.name)}</small></footer>`;
    const priorExpanded=previous?.getAttribute?.('aria-expanded'),priorControls=previous?.getAttribute?.('aria-controls');
    previous?.setAttribute?.('aria-expanded','true');previous?.setAttribute?.('aria-controls',element.id);
    const restoreAttribute=(name,value)=>value===null||value===undefined?previous?.removeAttribute?.(name):previous?.setAttribute?.(name,value);
    const reopen=()=>{workMotion.open(element);previous?.setAttribute?.('aria-expanded','true');previous?.setAttribute?.('aria-controls',element.id);element.querySelector('#ees-work-help-body').focus({preventScroll:true});};
    const close=restoreFocus=>{
      if(activeHelp?.element!==element)return;
      return workMotion.close(element,{release:()=>{restoreAttribute('aria-expanded',priorExpanded);restoreAttribute('aria-controls',priorControls);},cleanup:()=>{
        if(activeHelp?.element===element)activeHelp=null;element.remove();
        element.removeEventListener('keydown',onKey,true);window.removeEventListener('resize',position);for(const host of scrollHosts)host.removeEventListener('scroll',position,true);
      },restoreFocus:restoreFocus?()=>{if(previous?.isConnected)previous.focus({preventScroll:true});}:null});
    };
    const onKey=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close(true);}};
    const reanchor=(root,nextContext)=>{
      const replacement=[...(root?.querySelectorAll?.('[data-author-action="help"]') || [])].find(control=>control.dataset.id===termId);
      if(!replacement){const focused=element.contains(document.activeElement);close(false);if(focused)root?.querySelector?.('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')?.focus?.({preventScroll:true});return;}
      if(trigger!==replacement){restoreAttribute('aria-expanded',priorExpanded);restoreAttribute('aria-controls',priorControls);trigger=replacement;previous=replacement;previous.setAttribute('aria-expanded','true');previous.setAttribute('aria-controls',element.id);}
      if(nextContext)context=nextContext;position();
    };
    activeHelp={element,close,reopen,reanchor,trigger,onAsk,termId};mountOverlay(element,trigger);position();syncHelpState();workMotion.open(element);
    element.addEventListener('keydown',onKey,true);window.addEventListener('resize',position);for(const host of scrollHosts)host.addEventListener('scroll',position,true);
    element.querySelector('[data-help-close]').addEventListener('click',()=>close(true));
    element.querySelector('[data-help-ask]').addEventListener('click',async()=>{
      const button=element.querySelector('[data-help-ask]'),message=element.querySelector('[data-help-error]');button.disabled=true;message.hidden=true;
      try{const result=await onAsk(helpQuestion(selected),{...context,term_id:selected.id});if(result===false)return;close(false);}catch(error){if(activeHelp?.element===element){message.textContent=error.message || '질문을 보내지 못했습니다. 다시 시도해 주세요.';message.hidden=false;position();}}finally{syncHelpState();}
    });
    element.querySelector('#ees-work-help-body').focus({preventScroll:true});return element;
  }
  function closeDialog(){activeDialog?.eesClose?.();}
  function dialog({title,html='',confirmLabel='',note='',restoreFocus=null,readOnlyDetail=false}){
    // Flush a replaced window before mounting the next one: no duplicate IDs,
    // stale focus return, or old completion removing a newly opened window.
    const previous=activeDialog?.eesPrevious || document.activeElement;
    const openingFrame=activeDialog?.getAttribute('data-ees-motion')==='closing'?workMotion.frame(activeDialog):null;
    if(activeDialog){const previousDialog=activeDialog;previousDialog.eesClose?.();workMotion.finish(previousDialog,{restoreFocus:false});}
    const element=document.createElement('dialog');element.eesPrevious=previous;
    element.id='ees-work-dialog';element.dataset.eesWork='';element.dataset.eesMotionKind='dialog';element.setAttribute('aria-labelledby','ees-work-dialog-title');
    element.innerHTML=`<h2 id="ees-work-dialog-title">${esc(title)}</h2>${note?`<p class="ew-muted">${esc(note)}</p>`:''}<div class="ew-dialog-body" id="ees-work-dialog-body" tabindex="-1">${html}</div><footer><button type="button" data-dialog-close data-dialog-cancel id="ees-work-dialog-cancel">${confirmLabel?'취소':'닫기'}</button>${confirmLabel&&!readOnlyDetail?`<button type="button" class="ew-primary" data-dialog-confirm>${esc(confirmLabel)}</button>`:''}</footer>`;
    mountOverlay(element);activeDialog=element;
    return new Promise(resolve=>{
      let accepted=false,closing=false,backdrop=null;
      const nativeClose=element.close.bind(element);
      const close=()=>{
        if(closing)return;closing=true;
        if(activeHelp&&element.contains(activeHelp.element))closeHelp({restoreFocus:false,immediate:true});
        const duration=workMotion.settings(element).close;
        if(duration){backdrop=document.createElement('div');backdrop.className='ew-dialog-exit-backdrop';backdrop.dataset.eesMotionKind='backdrop';backdrop.style.opacity=typeof getComputedStyle==='function'?getComputedStyle(element,'::backdrop').opacity || '1':'1';backdrop.setAttribute('aria-hidden','true');mountOverlay(backdrop);workMotion.close(backdrop,{cleanup:()=>backdrop.remove()});}
        const motion=workMotion.close(element,{release:()=>{if(element.open){const wasInert=previous?.inert;if(previous)previous.inert=true;try{nativeClose();}finally{if(previous)previous.inert=wasInert;}}},cleanup:()=>{
          if(backdrop){workMotion.finish(backdrop,{restoreFocus:false});backdrop.remove();}
          element.remove();if(activeDialog===element)activeDialog=null;
        },restoreFocus:()=>{if(restoreFocus)restoreFocus();else if(previous?.isConnected)previous.focus({preventScroll:true});}});
        // The decision is immediate; animation never delays save/publish/run.
        resolve(accepted);return motion;
      };
      element.eesClose=close;
      element.querySelector('[data-dialog-confirm]')?.addEventListener('click',()=>{const invalid=[...element.querySelectorAll('input,select,textarea')].find(field=>!field.checkValidity());if(invalid){invalid.reportValidity();return;}accepted=true;close();});
      element.querySelector('[data-dialog-close]').addEventListener('click',close);
      element.addEventListener('cancel',event=>{event.preventDefault?.();accepted=false;close();});
      element.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();if(activeHelp&&element.contains(activeHelp.element)){closeHelp();return;}accepted=false;close();}},true);
      // Native programmatic closure follows the same lifecycle as Escape/buttons.
      element.addEventListener('close',close);
      element.showModal();workMotion.open(element,{from:openingFrame});(element.querySelector('input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea:not([disabled])') || element.querySelector('#ees-work-dialog-body')).focus({preventScroll:true});
    });
  }

  return Object.freeze({$,esc,clone,newId,categories,procedureQuestions,executionActorLabel,levels,statuses,icon,button,finished,lineage,badge,safeURL,time,dialog,closeDialog,helpQuestion,showHelp,closeHelp,reanchorHelp,dismissHelp,syncHelpState,menuEvent});
})();

function workStatusHTML(status,label=''){
  const {esc,icon,statuses}=workUI;
  const glyph=['completed','effect_verified'].includes(status)?'d553d':['failed'].includes(status)?'44a96':['awaiting_input','awaiting_confirmation','review_required','review','waiting_input','waiting_confirmation'].includes(status)?'9c63b':['running','in_progress'].includes(status)?'8f8a1':['unknown','missed','partial'].includes(status)?'d448c':'40ef1';
  return `<span class="ew-status" data-status="${esc(status)}">${icon(glyph)}<span>${esc(label || statuses[status] || status || '미실행')}</span></span>`;
}
function workAutoStatusHTML(status){
  const labels={failed:'실패',missed:'놓침',running:'실행 중',succeeded:'정상'},asset={failed:'7495b',succeeded:'c6340',running:'478bf',missed:'ce467'}[status];
  return asset?`<span class="ew-auto-status" data-status="${status}" title="마지막 자동 실행 · ${labels[status]}">${workUI.icon(asset,labels[status])}</span>`:'';
}
function workExecutionModelHTML(operations={},selected=''){
  const {esc}=workUI,models=operations.models || [];
  if(operations.error)return `<p class="ew-warning">모델·실행 연결 조회 실패 · ${esc(operations.error)}</p>`;
  if(!models.length)return '<p class="ew-warning">사용할 수 있는 모델이 없습니다. Native 모델 연결과 권한을 확인해 주세요.</p>';
  if(models.length===1)return `<p class="ew-model-select" data-execution-model="${esc(models[0].id)}">AI 모델 · ${esc(models[0].name || models[0].id)}</p>`;
  return `<label class="ew-model-select">AI 모델 <select id="ees-work-execution-model"><option value="">모델 선택</option>${models.map(model=>`<option value="${esc(model.id)}"${model.id===selected?' selected':''}>${esc(model.name || model.id)}</option>`).join('')}</select></label>`;
}
function workInputHTML(field,value,{disabled=false,prefix='run',people=[],lookup=null,proposal=null,applied=false}={}){
  const dynamic=['single','multi'].includes(field.type)&&field.options_source&&field.options_source!=='manual';
  const {esc}=workUI,id=`ew-${prefix}-${field.id}`,required=field.required?' required':'',off=disabled||(dynamic&&lookup?.status!=='ready')?' disabled':'',name=`name="${esc(field.id)}" data-work-input data-value-present="${value!==undefined}" data-input-type="${esc(field.type)}" id="${esc(id)}"${proposal?` aria-describedby="${esc(id)}-proposal"`:""}${required}${off}`;
  const valueText=v=>typeof v==='string'?v:JSON.stringify(v),choice=option=>typeof option==='object'&&option!==null?{value:option.value ?? option.id,label:option.label ?? option.name ?? option.id}: {value:option,label:option};
  let control='';
  if(field.type==='boolean')control=`<select ${name}><option value="">선택 안 함</option><option value="true"${value===true?' selected':''}>예</option><option value="false"${value===false?' selected':''}>아니요</option></select>`;
  else if(['single','multi','person'].includes(field.type)){
    const options=(field.type==='person'?(field.options?.length?field.options:people):(dynamic?(lookup?.status==='ready'?lookup.options:[]):field.options || [])).map(choice);
    const previous=field.type==='multi'?(Array.isArray(value)?value:[]):value===undefined?[]:[value];
    for(const old of previous)if(!options.some(option=>JSON.stringify(option.value)===JSON.stringify(old)))options.push({value:old,label:'이전 선택 · 현재 목록 확인 필요',stale:true});
    control=`<select ${name}${field.type==='multi'?' multiple':''}>${field.type!=='multi'?'<option value="">선택 안 함</option>':''}${options.map(option=>`<option value="${esc(JSON.stringify(option.value))}"${(field.type==='multi'?Array.isArray(value)&&value.some(v=>JSON.stringify(v)===JSON.stringify(option.value)):JSON.stringify(value)===JSON.stringify(option.value))?' selected':''}${option.stale?' data-stale-option':''}>${esc(option.label)}</option>`).join('')}</select>`;
  }else if(field.type==='list')control=`<textarea ${name} rows="3" placeholder="한 줄에 하나씩 입력">${esc(Array.isArray(value)?value.map(valueText).join('\n'):value ?? '')}</textarea>`;
  else control=`<input ${name} type="${field.type==='number'?'number':field.type==='datetime'?(/^\d{4}-\d{2}-\d{2}$/.test(value || '')?'date':/(Z|[+-]\d{2}:\d{2})$/.test(value || '')?'text':'datetime-local'):'text'}"${field.type==='number'?` step="${field.integer?'1':'any'}"${field.minimum!==undefined?` min="${esc(field.minimum)}"`:''}${field.maximum!==undefined?` max="${esc(field.maximum)}"`:''}`:''} value="${esc(value ?? '')}">${field.unit?`<span class="ew-unit">${esc(field.unit)}</span>`:''}`;
  if(dynamic)control+=`<small class="ew-option-source" role="status">${esc(lookup?.status==='ready'?`현재 권한으로 조회 · ${lookup.source?.kind || field.options_source} · ${lookup.options.length}개`:lookup?.status==='failed'?`목록 조회 실패 · ${lookup.error}`:'선택 목록을 확인하는 중입니다.')}</small>${!disabled?workUI.button('목록 다시 조회','reload_options',`data-field-id="${esc(field.id)}" class="ew-text"${lookup?.status==='loading'?' disabled':''}`):''}`;
  return `<label class="ew-input-row${proposal?' ew-input-proposed':''}"${proposal?` data-proposal-field="${esc(field.id)}"`:''} for="${esc(id)}"><span>${esc(field.name || field.id)}${field.required?'<span aria-label="필수"> *</span>':''}</span><span class="ew-input-control">${applied?'<small class="ew-input-proposal-source">도우미</small>':''}${control}${proposal?`<small id="${esc(id)}-proposal" class="ew-input-proposal-value">제안 · ${esc(workInputProposalValue(field,proposal.value,{people,lookup}))}</small>`:''}${field.help?`<small>${esc(field.help)}</small>`:''}</span></label>`;
}
function workInputProposalValue(field,value,{people=[],lookup=null}={}){
  const options=field.type==='person'?(field.options?.length?field.options:people):(lookup?.options || field.options || []);
  const text=item=>{
    const option=options.find(option=>workValuesEqual(typeof option==='object'&&option!==null?option.value ?? option.id:option,item));
    if(option!==undefined)return typeof option==='object'?option.label || option.name || option.id:String(option);
    if(Array.isArray(item))return item.map(text).join(' · ');
    if(typeof item==='boolean')return item?'예':'아니요';
    if(item&&typeof item==='object')return Object.values(item).map(text).join(' · ');
    return item==null?'':String(item);
  };
  return text(value);
}
function workInputProposalBar(proposal,node,{disabled=false}={}){
  const {button}=workUI,count=Object.keys(proposal.values || {}).length;
  return `<footer class="ew-job-actions ew-input-proposal-bar"><p>업무 도우미 입력 제안 · ${count}칸 · 반영하거나 버린 뒤 ${node.result_block==='change_request'?'요청합니다':'저장합니다'}</p>${button('버리기','discard_input_proposal','class="ew-secondary"')}${button('반영','apply_input_proposal',`data-mutation class="ew-primary"${disabled?' disabled data-own-disabled="true"':''}`)}</footer>`;
}
function workReadInputs(container){
  const values={};
  for(const field of container.querySelectorAll('[data-work-input]')){
    if(field.disabled)continue;const key=field.name,type=field.dataset.inputType;
    if(type==='multi'){values[key]=[...field.selectedOptions].map(option=>JSON.parse(option.value));continue;}
    if(field.value===''&&!(field.dataset.valuePresent==='true'&&['text','list'].includes(type)))continue;
    if(type==='boolean')values[key]=field.value==='true';
    else if(['single','person'].includes(type))values[key]=JSON.parse(field.value);
    else if(type==='number'){const number=Number(field.value);if(!Number.isFinite(number))throw new Error('숫자 입력을 확인해 주세요.');values[key]=number;}
    else if(type==='list')values[key]=field.value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
    else values[key]=field.value;
  }
  return values;
}
function workInputProposal(payload,run,jobId,tools=[]){
  const node=run?.definition?.nodes?.[jobId],fields=node?.result_block==='change_request'?(workRequestFields(node,tools) || []):node?.inputs || [],allowed=new Set(fields.filter(field=>!field.constant&&(field.scope || 'run')==='run').map(field=>field.id));
  if(payload?.proposal_kind!=='inputs'||payload.run_id!==run?.id||payload.workflow_id!==run.workflow_id||payload.job_id!==jobId||payload.base_revision!==run.revision||!payload.proposal||typeof payload.proposal!=='object'||Array.isArray(payload.proposal)||Object.keys(payload.proposal).some(key=>!allowed.has(key)))throw new Error('현재 진행 건·작업·저장 버전과 다른 입력 제안입니다.');
  return workUI.clone(payload.proposal);
}

function workSettingsOverrides(settings,draft,fields){
  const values={...(settings.overrides || {})};
  for(const field of fields || [])if(['workflow','factory'].includes(field.scope)){
    if(!Object.hasOwn(draft,field.id))delete values[field.id];
    else if(JSON.stringify(draft[field.id])!==JSON.stringify(settings.values?.[field.id]))values[field.id]=workUI.clone(draft[field.id]);
  }
  return values;
}

function workRequestFields(node,tools=[]){
  const contract=tools.find(tool=>tool.id===(node.tool_contract_id || node.tool_reference?.contract_id)),schema=contract?.input_schema;
  if(!schema||schema.type!=='object'||!schema.properties)return null;
  const fields=Object.entries(schema.properties).map(([argument,spec])=>{
    const binding=node.argument_bindings?.[argument],constant=binding&&Object.hasOwn(binding,'constant'),id=typeof binding==='string'?binding:binding?.input || argument,field=constant?{id,name:argument,scope:'run',constant:true,value:binding.constant}:(node.inputs || []).find(field=>field.id===id);
    if(!field)return null;
    const type=spec.enum?'single':{integer:'number',number:'number',boolean:'boolean',array:'list',string:spec.format==='date-time'?'datetime':'text'}[spec.type];
    if(!type)return null;
    return {...field,id,name:spec.title || field.name || argument,type,required:(schema.required || []).includes(argument),help:spec.description || field.help,options:spec.enum || field.options,minimum:spec.minimum,maximum:spec.maximum,integer:spec.type==='integer',argument};
  });
  return fields.some(field=>!field)?null:fields;
}
function workPartialSourceHTML(attempt,run={}){
  const confirmed=attempt?.snapshot?.partial_prerequisites;if(confirmed?.length)return workNoticeHTML('부분 결과에서 시작함',confirmed.map(source=>source.name || source.job_id).join(' · '));
  const sources=Object.entries(attempt?.snapshot?.prerequisite_sources || {}).filter(([,source])=>{const evidence=(run.attempts || []).find(item=>item.id===source.attempt_id);return source.status==='partial'||evidence?.status==='partial'||evidence?.result?.completeness==='partial';});
  return sources.length?workNoticeHTML('부분 결과에서 시작함',sources.map(([id])=>attempt.snapshot.definition?.nodes?.[id]?.name || id).join(' · ')):'';
}
function workChecklistHTML(items,saved={},human=false){
  const {esc,safeURL,icon}=workUI;
  const status=(value,label)=>`<span class="ew-status" data-status="${esc(value)}">${icon(['completed','succeeded','success'].includes(value)?'f4cb1':value==='failed'?'44a96':value==='unknown'?'3dae2':'40ef1')}<span>${esc(label || workUI.statuses[value] || value)}</span></span>`;
  if(!items.length)return `<p class="ew-empty">${human?'항목별 확인 기준이 등록되지 않았습니다. 작업의 확인 기준을 따릅니다.':'아직 저장된 결과가 없습니다.'}</p>`;
  return `<div class="ew-check-block"><header><strong>${human?'확인할 항목':'확인 항목'}</strong><small>${esc(workUI.time(saved.updated_at || saved.created_at))}</small></header>${items.map(item=>{const decision=saved.decisions?.[item.id],itemStatus=decision?.verdict || item.status || 'unknown';return `<article class="ew-check-item">${status(itemStatus,item.name || item.title || item.id)}${item.criterion || item.pass_criteria?`<p>통과 기준 · ${esc(item.criterion || item.pass_criteria)}</p>`:''}${decision?`<small>확인 · ${esc(decision.actor_id)} · ${esc(workUI.time(decision.created_at))}${decision.note?' · '+esc(decision.note):''}</small>`:''}${(item.evidence || []).map(e=>`<details class="ew-check-evidence"><summary>${status(e.status || 'unknown',e.name || e.label || '도구 결과')}<span class="ew-check-chevron">${icon('1a06f')}</span><small>${esc(e.tool_id || '')}</small></summary><p>한 일 · ${esc(e.action || e.description || '기록 없음')}</p><p>정상 실행 기준 · ${esc(e.success_criterion || '기록 없음')}</p><p>실제 결과 · ${esc(typeof e.result==='object'?JSON.stringify(e.result):e.result || e.summary || '미확인')}</p></details>`).join('')}${safeURL(item.url)?`<a href="${esc(safeURL(item.url))}" target="_blank" rel="noopener noreferrer">근거 열기</a>`:''}</article>`;}).join('')}</div>`;
}
function workAdhocStartHTML(data,selection,definition){
  const {esc,button,finished,time}=workUI,workflow=data.workflow || {},active=(data.workflow_active_runs || data.runs || []).filter(run=>run.workflow_id===workflow.id&&!finished(run));
  const factories=(data.factories || []).filter(factory=>!factory.system_id||factory.system_id===selection.system_id),used=new Set(active.map(run=>run.factory_id).filter(Boolean)),system=definition.execution_scope==='system';
  const selected=system?'':selection.factory_id ?? '',draft=selection.start_inputs?.[workflow.id] || {},fields=[...new Map(Object.values(definition.nodes || {}).flatMap(node=>node.inputs || []).filter(field=>(field.scope || 'run')==='run').map(field=>[field.id,field])).values()];
  const pending=used.has(selected),blocked=definition.execution_scope==='factory'&&!selected;
  const overrides=selected===(data.settings?.factory_id || '')?data.settings?.overrides || {}:{};
  return `<header class="ew-work-heading"><h2>${esc(definition.name || workflow.name)}</h2><p>수시 · 게시 v${esc(workflow.published_version || '없음')} · 진행 중 ${active.length}건</p></header><section class="ew-active-runs"><h3>진행 중 ${active.length}</h3>${active.map(run=>`<button type="button" class="ew-record" data-action="open_run" data-run-id="${esc(run.id)}" data-workflow-id="${esc(workflow.id)}">${workStatusHTML(run.status || 'open',factories.find(factory=>factory.id===run.factory_id)?.name || run.factory_name || (run.factory_id?'공장 이름 확인 필요':'시스템 전체'))}<small>${Number.isInteger(run.progress?.completed)&&Number.isInteger(run.progress?.total)&&run.progress.total>0?`완료 ${esc(run.progress.completed)}/${esc(run.progress.total)} · `:''}${esc(time(run.created_at))} 시작</small></button>`).join('') || '<p class="ew-muted">진행 중인 건이 없습니다.</p>'}</section><section class="ew-adhoc-start"><h3>새로 시작</h3><form id="ees-work-start"><label class="ew-input-row"><span>${system?'':workUI.icon('b355c')}대상 ${system?'시스템':'공장'}</span><span class="ew-input-control">${system?`<span>${esc(selection.system_id)} · 전체 공장 설정</span>`:`<select id="ees-start-factory"><option value="">${definition.execution_scope==='factory'?'공장 선택':'시스템 전체'}</option>${factories.map(factory=>`<option value="${esc(factory.id)}"${factory.id===selected?' selected':''}${used.has(factory.id)||factory.allowed===false?' disabled':''}>${esc(factory.name)}${used.has(factory.id)?' · 이미 진행 중':''}</option>`).join('')}</select><small>진행 중인 공장은 새로 시작할 수 없습니다.</small>`}</span></label>${fields.map(field=>workInputHTML(field,draft[field.id],{prefix:'start',people:data.people || []})).join('')}${(data.native_groups || []).length?`<details><summary>함께 처리할 Native 그룹</summary><p class="ew-muted">선택하지 않으면 개인 진행 건입니다. 개인 대화는 공유하지 않습니다.</p>${data.native_groups.map(group=>`<label><input type="checkbox" data-start-group value="${esc(group.id)}"${selection.start_groups?.[workflow.id]?.includes(group.id)?' checked':''}>${esc(group.name || group.id)}</label>`).join('')}</details>`:''}</form><section class="ew-start-preview"><h4>적용되는 절차 · v${esc(workflow.published_version || '없음')}</h4><p>${esc(system?'시스템 전체':factories.find(factory=>factory.id===selected)?.name || '시스템 전체')} 기준</p>${Object.keys(overrides).length?`<details><summary>기본과 다른 점 ${Object.keys(overrides).length}</summary>${Object.entries(overrides).map(([id,value])=>`<p>${esc(id)} · ${esc(typeof value==='object'?JSON.stringify(value):value)}</p>`).join('')}</details>`:'<p>저장된 공장별 차이 없음</p>'}</section></section><footer class="ew-job-actions"><small>시작하면 진행 건이 만들어지고 기록에 남습니다.</small>${workflow.published_version?button('진행 건 시작','start_run',`data-start-inline data-mutation class="ew-primary"${pending||blocked?' disabled data-own-disabled="true"':''}`):'<p>게시된 버전이 없습니다.</p>'}${pending?workNoticeHTML('이미 진행 중인 공장입니다','위 진행 건을 열어 이어서 처리해 주세요.'):''}</footer>`;
}

function workValuesEqual(left,right){
  const order=value=>Array.isArray(value)?value.map(order):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,order(value[key])])):value;
  return JSON.stringify(order(left))===JSON.stringify(order(right));
}
function createWorkInputDrafts(){
  const entries=new Map(),{clone}=workUI,same=workValuesEqual;
  return Object.freeze({
    edit(key,inputs,revision,base){const old=entries.get(key);entries.set(key,{inputs:clone(inputs),revision:old?.revision ?? revision,base:old?.base ?? clone(base),serial:(old?.serial || 0)+1});},
    read(key,values,revision){let entry=entries.get(key);if(entry&&same(entry.inputs,values)){entries.delete(key);entry=null;}else if(entry&&entry.revision!==revision&&same(entry.base,values)){entry.revision=revision;}return entry?{...clone(entry),dirty:!same(entry.inputs,values),conflict:entry.revision!==revision&&!same(entry.base,values)}:{inputs:clone(values || {}),revision,dirty:false,conflict:false,serial:0};},
    acknowledge(key,serial,revision,values){const entry=entries.get(key);if(!entry)return;if(entry.serial===serial)entries.delete(key);else{entry.revision=revision;entry.base=clone(values);}},
    discard:key=>entries.delete(key),hasDirty:prefix=>[...entries].some(([key,entry])=>key.startsWith(prefix)&&!same(entry.inputs,entry.base)),clear:()=>entries.clear()
  });
}
function workNoticeHTML(title,detail='',tone='attention'){
  const {esc}=workUI;return `<div class="ew-notice" data-tone="${esc(tone)}" role="status"><strong>${esc(title)}</strong>${detail?`<p>${esc(detail)}</p>`:''}</div>`;
}
function workReasonText(reason,messages={},params={}){
  if(Object.hasOwn(messages,reason))return messages[reason].replace(/\{(\w+)\}/g,(_,key)=>String(params[key] ?? '미확인'));
  return ({delivery_unconfigured:'송부 연결 필요 · 본문 검토만 저장했습니다.',effect_criterion_not_met:'효과 확인 실패 · 정한 완료 기준을 충족하지 못했습니다.',effect_criterion_required:'효과 확인 기준을 설정해 주세요.',effect_observation_unknown:'효과 확인 결과가 미확인입니다.',ees_connector_unconfigured:'EES 요청 연결이 아직 설정되지 않았습니다.',direct_executor_unconfigured:'직접 실행 · 예외 도구의 실행 연결 확인 필요. 실제 작업을 실행하지 않았습니다.',request_result_unknown:'요청 결과가 미확인입니다. 같은 작업의 상태를 확인해 주세요.',ees_response_invalid:'EES 응답을 확인하지 못했습니다.',ees_status_unavailable:'EES 상태를 조회하지 못했습니다.',read_retry_deadline:'조회 제한 시간이 지났습니다. 결과를 확인해 주세요.',read_retry_source_changed:'입력이나 근거가 바뀌어 자동 재조회를 중단했습니다.',zero_selection_policy_required:'선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다.'})[reason] || reason || '';
}
function workPersonLabel(person,people=[]){
  const found=people.find(item=>item.value?.kind===person?.kind&&item.value?.id===person?.id);
  return found?.label || found?.name || '이름 확인 필요';
}
function workAssignmentHTML(node,saved,people=[]){
  const {esc}=workUI;
  return `${node.assignee?`<p class="ew-assignee">배정된 ${node.assignee.kind==='group'?'그룹':'담당자'} · ${esc(workPersonLabel(node.assignee,people))}</p>`:''}${saved.claim_actor?`<p class="ew-claimant">현재 담당 · ${esc(workPersonLabel({kind:'user',id:saved.claim_actor},people))}</p>`:''}`;
}
function workListSourceAttempt(run,attemptId){
  const attempts=run?.attempts || [],seen=new Set();let attempt=attempts.find(item=>item.id===attemptId);
  while(attempt){
    if(attempt.evidence_access||seen.has(attempt.id))return null;seen.add(attempt.id);
    const previous=attempt.result?.amendment?.previous_attempt;if(!previous)return attempt;
    const parent=attempts.find(item=>item.id===previous&&item.job_id===attempt.job_id);if(!parent)return null;attempt=parent;
  }
  return null;
}
function workListItems(result={}){
  const actual=Array.isArray(result.items)?result.items:[],ids=new Set(actual.map(item=>item.id));
  return [...actual.map(item=>({...workUI.clone(item),selected:item.selected!==false,manual:item.source?.kind==='human_added'||item.manual===true})),...(Array.isArray(result.suggestions)?result.suggestions:[]).filter(item=>item&&typeof item.id==='string'&&!ids.has(item.id)).map(item=>({...workUI.clone(item),selected:false,candidate:true}))];
}
function workListHTML(saved={}, {readOnly=false,listDraft=null,sourceCount,sharedSearch=false,target=''}={}){
  if(saved.evidence_access)return workNoticeHTML('현재 원본 접근 권한을 확인해 주세요','이전 목록이나 작성 중인 선택을 현재 근거로 대신 표시하지 않습니다.');
  const {esc,button,safeURL}=workUI,result=saved.result || {},items=listDraft?.items || workListItems(result),included=items.filter(item=>item.selected),extra=items.filter(item=>item.selected&&item.candidate);
  const confirmed=Object.keys(saved.decisions || {}).length>0,readonly=readOnly||confirmed,queried=sourceCount===undefined?(result.items || []).filter(item=>item.source?.kind!=='human_added'&&!item.manual).length:sourceCount;
  if(['failed','unknown'].includes(saved.status))return workNoticeHTML(sharedSearch?`${target || 'Confluence'}에서 결과를 받지 못했습니다`:'조회 결과를 확인하지 못했습니다','지난 회차 목록이나 이전 결과는 보여주지 않습니다. 현재 조회 권한과 연결 상태를 확인해 주세요.',saved.status==='failed'?'danger':'attention');
  if(!items.length&&!Array.isArray(result.items))return '<p class="ew-empty">아직 저장된 결과가 없습니다.</p>';
  const noResults=sharedSearch&&queried===0,partial=sharedSearch&&queried>0&&saved.status!=='completed'&&(saved.status==='partial'||result.completeness==='partial');
  const resultNotice=noResults?`<span class="ew-badge">결과 없음</span>${workNoticeHTML('찾은 문서가 없습니다.')}`:partial?`<span class="ew-badge">부분 결과</span>${workNoticeHTML(`찾은 문서 앞쪽 ${queried}건`,'더 있을 수 있습니다. 필요한 문서를 골라 확정하면 다음 작업으로 넘어갑니다. 이 작업은 기록에 ‘부분 결과’로 남습니다.')}`:'';
  const row=item=>`<tr data-candidate="${Boolean(item.candidate)}"><td><input type="checkbox" id="ees-list-${esc(item.id)}" data-item-confirm data-list-include data-item-id="${esc(item.id)}" aria-label="${esc(item.id)} 포함"${item.selected?' checked':''}${readonly?' disabled':''}></td><td>${safeURL(item.url)?`<a href="${esc(safeURL(item.url))}" target="_blank" rel="noopener noreferrer">${esc(item.id)}</a>`:esc(item.id)}</td><td>${esc(item.name || item.title || item.id)}${item.candidate?`<small>${esc(item.reason || item.note || '목록 포함 여부를 사람이 확인해 주세요.')}</small><span class="ew-badge">확인 후보 · 미확정</span>`:''}${item.manual?'<small>사람이 추가 · 원본 조회 확인 전</small>':''}</td><td>${esc(item.status_name || item.status || '미확인')}</td></tr>`;
  return `<div class="ew-list-confirm">${resultNotice}${!sharedSearch&&result.scope==='single_page'?'<p class="ew-muted">완결성 · 한 쪽 — 이번 검색에서 받은 페이지 목록입니다.</p>':''}<p>${queried===null?'원본 조회 건수 확인 필요':`조회 ${esc(queried)}건`} · 빼거나 더할 항목을 고른 뒤 확정</p><table class="ew-list-table"><thead><tr><th><span class="sr-only">포함</span></th><th>항목</th><th>제목</th><th>상태</th></tr></thead><tbody>${items.filter(item=>!item.candidate).map(row).join('')}</tbody></table>${items.some(item=>item.candidate)?`<h4>조회 조건 외 확인 후보 ${items.filter(item=>item.candidate).length}</h4><table class="ew-list-table ew-list-candidate"><tbody>${items.filter(item=>item.candidate).map(row).join('')}</tbody></table>`:''}${!readonly?`<button type="button" data-action="add_list_item" class="ew-text">${workUI.icon('b456d')} 번호로 항목 추가</button>`:''}<div class="ew-list-toolbar"><small>포함 ${included.length} · 추가 ${extra.length+items.filter(item=>item.manual&&item.selected&&!item.candidate).length} · 제외 ${items.filter(item=>!item.selected&&!item.candidate&&!item.manual).length}</small>${confirmed?'<span class="ew-badge">사람 확정 기록 있음</span>':!readonly?button('선택 목록 저장','save_list_selection','data-mutation class="ew-secondary"')+button(noResults?'찾은 문서 없음 확인':`목록 확정 (${included.length}건)`,'confirm_list',`data-mutation class="ew-primary"${!included.length&&!sharedSearch?' disabled data-own-disabled="true"':''}`):''}</div>${!included.length&&!confirmed&&!sharedSearch?workNoticeHTML('선택 항목이 없는 목록의 완료 정책이 정해지지 않았습니다','선택 상태는 저장할 수 있지만 확정은 보류합니다.'):''}${!sharedSearch&&(saved.status==='partial'||saved.result?.completeness==='partial')?workNoticeHTML('부분 결과 · 미확인 항목이 남아 있습니다','목록을 확인해도 조회가 완전한 결과로 바뀌지는 않습니다.'):''}</div>`;
}
function workReviewDraftHTML(job,saved,{readOnly=false,reviewDraft=null}={}){
  if(saved.evidence_access)return workNoticeHTML('현재 원본 접근 권한을 확인해 주세요','이전 AI 본문과 편집 중인 초안을 표시하지 않습니다.');
  if(['failed','unknown','running'].includes(saved.status))return workNoticeHTML(saved.status==='running'?'초안을 준비하고 있습니다':'초안 결과를 확인하지 못했습니다','이전 본문을 현재 초안으로 대신 표시하지 않습니다.',saved.status==='failed'?'danger':'attention');
  const delivery=job.completion?.kind==='delivery',canAct=!readOnly;
  readOnly=readOnly||Boolean(saved.decisions?.job)||saved.result_stale||saved.status==='review_required';
  const {esc,button}=workUI,result=saved.result || {},text=reviewDraft?.inputs?.text ?? saved.review_draft?.text ?? result.text ?? result.draft ?? result.summary ?? '',revision=saved.review_draft?.revision || 0;
  return `<div class="ew-dispatch-draft">${saved.result_stale||saved.status==='review_required'?workNoticeHTML('입력이나 선행 근거가 바뀌었습니다','이전 본문은 보존되어 있습니다. 새 근거로 다시 실행한 뒤 검토해 주세요.'):''}<div class="ew-draft-summary"><h4>초안 검토</h4>${workUI.icon('b22ad')}<small>${saved.decisions?.job?(delivery?'본문 검토 확정 · 송부 전':'사람 확정 기록 있음'):'AI 초안 · 사람 미확정'}${result.model?.name?' · '+esc(result.model.name):''}${saved.review_draft?` · ${esc(workUI.time(saved.review_draft.updated_at || saved.review_draft.created_at))} 저장`:''}</small></div>${saved.attempt_id?`<label class="ew-review-text"><span class="sr-only">검토 초안 본문</span><textarea id="ees-review-text" rows="9" data-review-revision="${revision}"${readOnly?' readonly':''}>${esc(text)}</textarea></label>`:`<p>${esc(text || '저장된 AI 제안이 없습니다.')}</p>`}${reviewDraft?.conflict?workNoticeHTML('다른 사람이 초안을 변경했습니다','작성 중인 본문은 보존했습니다. 최신 기록을 확인하고 다시 저장해 주세요.'):'<p class="ew-muted">수정한 본문은 자동 저장됩니다. AI 원문과 당시 판정 근거는 실행 기록에 남습니다.</p>'}${saved.attempt_id&&canAct?`<div class="ew-draft-actions">${!readOnly?`<small role="status">${reviewDraft?.conflict?'자동 저장 충돌 · 작성한 본문 보존':reviewDraft?.dirty?'자동 저장 대기 중':'자동 저장됨'}</small>`:''}${delivery?button('검토하고 보내기','send_review_draft','disabled data-own-disabled="true" aria-describedby="ees-dispatch-block"'):''}</div>`:''}${delivery?'<p id="ees-dispatch-block" class="ew-notice" data-tone="attention">본문 검토와 송부 완료는 다릅니다. 송부 방식과 실제 송부 연결이 정해져야 보낼 수 있습니다.</p>':''}</div>`;
}
function workResultHTML(job,saved={}, {readOnly=false,listDraft=null,reviewDraft=null,actorId='',sourceCount,verdictDraft={},messages={},target=''}={}){
  const {esc,button,safeURL}=workUI,result=saved.result ?? saved.output ?? {},items=Array.isArray(result.items)?result.items:Array.isArray(result)?result:[],block=job.result_block || 'human_confirm';
  readOnly=readOnly||saved.status==='completed';
  const judgments=job.judgments?.length?job.judgments:null,verdicts=judgments || job.verdicts || [{id:'completed',label:'적합'},{id:'failed',label:'미흡'},{id:'unknown',label:'판단 불가'}];
  const decision=item=>{const d=saved.decisions?.[item.id],pending=verdictDraft[item.id],chosen=pending?.judgment_id || pending?.verdict;
    if(d)return `<div class="ew-confirmed-verdict">${workStatusHTML(d.verdict,'판정 확정 · '+(workUI.statuses[d.verdict] || d.verdict))}${d.note?`<p>${esc(d.note)}</p>`:''}<small>${esc(d.actor_id)} · ${esc(workUI.time(d.created_at))}</small></div>`;
    return `<select data-item-verdict data-item-id="${esc(item.id)}" aria-label="${esc(item.name || item.id)} 판정"${readOnly?' disabled':''}><option value="">판정 선택</option>${verdicts.map(v=>{const state=v.status ?? v.meaning ?? v.id ?? v.value,id=v.id ?? v.value ?? state;return `<option value="${esc(id)}" data-verdict="${esc(state)}"${judgments?` data-judgment-id="${esc(id)}"`:''}${chosen===id?' selected':''}>${esc(v.label ?? v.name ?? id)}</option>`;}).join('')}</select>`;};
  const source=value=>safeURL(value)?`<a href="${esc(safeURL(value))}" target="_blank" rel="noopener noreferrer">근거 열기</a>`:'';
  const empty='<p class="ew-empty">아직 저장된 결과가 없습니다.</p>';
  let body='';
  if(block==='schedule')body=`<div class="ew-result-schedule">${esc(result.notice || result.summary || '일정 확인이 필요합니다.')}${result.due_at?`<time datetime="${esc(result.due_at)}">${esc(result.due_at)}</time>`:''}${result.calendar_available===false?'<p>공휴일 달력 미연결 · 일정 확인 필요</p>':''}</div>`;
  else if(block==='list_confirm')body=workListHTML(saved,{readOnly,listDraft,sourceCount,sharedSearch:Boolean(job.shared_tool_id)&&(job.shared_function==='search_pages'||result.scope==='single_page'),target});
  else if(block==='checklist')body=workChecklistHTML(items,saved);
  else if(block==='item_verdict')body=items.length?`<div class="ew-result-items">${items.map(item=>`<article><header><strong>${esc(item.name || item.title || item.id)}</strong>${source(item.url)}</header>${item.evidence?.map(e=>`<p>${workStatusHTML(e.status || 'unknown',e.label || e.name)}${e.content_reviewed===false?'<small>내용 적정성 미검토</small>':''}</p>`).join('') || ''}${item.ai_suggestion&&!saved.decisions?.[item.id]?`<p class="ew-ai-proposal">AI 제안 · ${esc(item.ai_suggestion)} · 사람 미확정</p>`:''}${decision(item)}${!saved.decisions?.[item.id]&&verdictDraft[item.id]?.verdict?'<small>내 선택 · 확정 전 · 자동 저장</small>':''}</article>`).join('')}<p class="ew-muted">선택은 자동 저장되는 확정 전 초안입니다. 모든 항목을 선택한 뒤 판정 확정으로 최종 반영합니다.</p>${items.every(item=>saved.decisions?.[item.id])?'<p>모든 항목의 판정이 확정되었습니다.</p>':!readOnly?button('판정 확정','confirm_verdicts',`data-mutation class="ew-primary"${items.every(item=>saved.decisions?.[item.id]||verdictDraft[item.id]?.verdict)?'':' disabled data-own-disabled="true"'}`):''}</div>`:empty;
  else if(block==='ai_review')body=workReviewDraftHTML(job,saved,{readOnly,reviewDraft});
  else if(block==='change_request')body=workRequestHTML(saved.request || result.request || {},{...job,actor_id:actorId,execution_actor:job.execution_actor,can_request:saved.can_request ?? (!readOnly&&saved.can_execute!==false),can_review_request:saved.can_review_request ?? (!readOnly&&saved.can_execute!==false),can_reconcile:saved.can_reconcile ?? (!readOnly&&saved.can_execute!==false)});
  else if(block==='values')body=Object.keys(result).length?`<dl class="ew-facts">${Object.entries(result).filter(([key])=>!['secret','token','pat','credential'].includes(key.toLowerCase())).map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}</dd></div>`).join('')}</dl>`:empty;
  else body=workChecklistHTML(Array.isArray(job.confirmation_items)?job.confirmation_items:[],saved,true)+`<p>${esc(job.completion?.description || job.completion_criteria || job.instructions || '결과와 근거를 확인한 뒤 직접 확인해 주세요.')}</p>${result.summary?`<p>${esc(result.summary)}</p>`:''}`;
  if(result.result_kind==='evidence')body+=`<section class="ew-read-evidence"><h4>조회 근거</h4>${(result.evidence || []).map(item=>source(item.url)).join('')}<pre>${esc(result.data?.content || '')}</pre>${result.completeness==='truncated'?'<span class="ew-badge">부분 결과</span><p>본문이 길어 일부만 받았습니다.</p>':''}</section>`;
  return `<section class="ew-result" data-result-block="${esc(block)}">${result.error?workNoticeHTML('조회 연결 확인',result.error.message||workReasonText(result.error.code,messages)):''}${saved.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한으로 근거를 다시 확인해야 합니다. 이전 기록을 보존하고 현재 권한으로 다시 조회해 주세요.</p>':''}${block!=='list_confirm'&&(saved.status==='partial'||saved.result?.completeness==='partial')?workNoticeHTML('부분 결과','받은 범위만 확인했습니다. 사람 판정 뒤에도 조회 범위가 완전해지지는 않습니다.'):''}<h3>${esc({values:'확인한 값',schedule:'일정 안내',checklist:'확인 항목 결과',list_confirm:'목록 확정',item_verdict:'항목별 판정',ai_review:'초안 검토',human_confirm:'사람 확인',change_request:'EES 요청'}[block] || '결과')}</h3>${body}${job.result_block==='ai_review'&&saved.attempt_id?button('결과 초안 내보내기','export_result',`data-job-id="${esc(job.id)}" class="ew-text"`):''}${!readOnly&&items.length&&['list_confirm','item_verdict','checklist'].includes(block)&&!(block==='item_verdict'&&Object.keys(saved.decisions || {}).length)?button('목록 수정 · 다시 검토','amend_items','class="ew-text"'):''}</section>`;
}
function workRequestHTML(request={},job={}){
  const {esc,safeURL}=workUI,executionActor=request.execution_actor || job.execution_actor || 'EES',direct=executionActor==='EES Work',steps=[['requested','요청 보냄','EES Work'],['accepted','접수',executionActor],['running','실행 중',executionActor],['reported_complete','완료 보고',executionActor],['effect_verified','효과 확인','EES Work']],events=request.events || [];
  return `<div class="ew-request-track">${direct?workNoticeHTML('직접 실행 · 예외','실행 주체 EES Workflow · 실행 연결 확인 필요. 등록·검토만으로 실제 작업을 실행하지 않습니다.'):''}${request.id?`<p>${workStatusHTML(request.state || request.status)} · 승인 ${esc(request.approvals?.length || 0)} / ${esc(request.approval_count || 0)}</p>${job.can_review_request!==false&&request.actor!==job.actor_id&&!(request.approvals || []).some(approval=>approval.actor===job.actor_id)&&request.state==='approval_pending'?workUI.button('요청 승인','approve_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}${job.can_reconcile!==false&&['requested','accepted','running','reported_complete','unknown'].includes(request.state)?workUI.button('상태 다시 확인','reconcile_request',`data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}"`):''}`:''}${(request.external_job_id || request.job_number)?`<p>작업 번호 <strong>${esc((request.external_job_id || request.job_number))}</strong></p>`:''}${steps.map(([state,label,actor])=>{const event=events.find(e=>e.state===state || e.status===state || e.kind===state);return `<div>${workStatusHTML(event?state==='running'?'running':'completed':'waiting',label)}<span class="ew-actor" data-actor="${esc(actor)}">${esc(workUI.executionActorLabel(actor))}</span><small>${esc(event?workUI.time(event.at ?? event.created_at):'대기')}</small></div>`;}).join('')}${['unknown','partial'].includes(request.status || request.state)?workNoticeHTML('결과를 확인하지 못했습니다','중복 실행을 막기 위해 자동으로 다시 요청하지 않습니다. 같은 작업 번호의 상태만 다시 조회해 주세요.'):request.state==='failed'&&request.reported_complete&&!request.effect_verified?workNoticeHTML('EES는 완료했지만 효과가 확인되지 않았습니다','이 작업은 실패로 남습니다. 절차에 정한 다음 조치와 근거를 확인해 주세요.','danger'):request.reported_complete&&!request.effect_verified?workNoticeHTML('EES 완료 보고 후 효과 확인이 필요합니다','업무 완료로 처리하지 않았습니다.'):''}<p class="ew-muted">${esc(workUI.executionActorLabel(executionActor))} 완료 보고와 효과 확인이 모두 끝나야 업무를 완료합니다.</p>${(request.block_reason || request.reason)?`<p role="status">${esc(workReasonText(request.block_reason || request.reason))}</p>`:''}${safeURL(request.external_url)?`<a href="${esc(safeURL(request.external_url))}" target="_blank" rel="noopener noreferrer">EES에서 보기</a>`:''}${job.request_contract?.guide_url&&safeURL(job.request_contract.guide_url)?`<a href="${esc(safeURL(job.request_contract.guide_url))}" target="_blank" rel="noopener noreferrer">EES 가이드</a>`:''}</div>`;
}
function workHistoricalValuesHTML(attempt,currentSettings=null){
  const {esc}=workUI,inputs=attempt.inputs ?? attempt.snapshot?.inputs ?? {},fields=attempt.snapshot?.job?.inputs || [];
  if(attempt.evidence_access)return '<p>현재 원본 접근 권한 확인 필요</p>';
  if(!Object.keys(inputs).length)return '<p>기록된 입력 없음</p>';
  return `<dl class="ew-history-values">${Object.entries(inputs).map(([key,value])=>{const field=fields.find(item=>item.id===key),source=attempt.snapshot?.settings_sources?.[key],shared=['workflow','factory'].includes(source?.scope || field?.scope),changed=shared&&currentSettings&&(!Object.hasOwn(currentSettings,key)||JSON.stringify(value)!==JSON.stringify(currentSettings[key]));return `<div><dt>${esc(field?.name || key)}</dt><dd>${esc(typeof value==='object'?JSON.stringify(value):value)}${changed?'<span class="ew-changed-value">지금과 다름</span>':''}<small>${esc({run:'이번 실행 입력',workflow:'업무 설정',factory:'공장 설정'}[source?.scope || field?.scope || 'run'])}</small></dd></div>`;}).join('')}</dl>`;
}
function workCycleBarHTML(run,definition={}){
  if(!run)return '';const {esc,button,time}=workUI,stages=Object.values(definition.nodes || {}).filter(node=>node.type==='t'),done=stages.filter(stage=>Object.values(definition.nodes || {}).filter(node=>node.type==='j'&&workUI.lineage(node.id,definition).some(parent=>parent.id===stage.id)).every(node=>['completed','excluded'].includes(run.jobs?.[node.id]?.status))).length;
  const mode=run.mode || definition.execution_mode,label=mode==='periodic'?'이번 회차':mode==='emergency'?'진행 중인 대응':'진행 건';
  return `<div class="ew-cycle-bar"><span>${label}</span><strong>${esc(run.cycle?.name || run.name || definition.name || '진행 건')}</strong><small>${esc(time(run.created_at))} 개시${stages.length?` · ${done}/${stages.length}단계`:''}</small>${button(mode==='periodic'?'지난 회차':mode==='emergency'?'다른 대응':'다른 진행 건','workflow_records','class="ew-text"')}</div>`;
}
function workRunRecordsHTML(runs=[],workflowId='',workflowName=''){
  const {esc,button,finished,time}=workUI,rows=runs.filter(run=>!workflowId||run.workflow_id===workflowId).slice().sort((a,b)=>Number(finished(a))-Number(finished(b))||String(b.created_at).localeCompare(String(a.created_at)));
  return `${workflowId?`<div class="ew-record-filter"><strong>${esc(workflowName || '선택한 업무 절차')}</strong><button type="button" data-action="all_records" class="ew-text" aria-label="업무 절차 필터 해제">${workUI.icon('6d84b')}</button></div>`:''}${rows.map(run=>`<button type="button" class="ew-record" data-action="open_run" data-run-id="${esc(run.id)}" data-workflow-id="${esc(run.workflow_id)}"><strong>${esc(run.name || run.definition?.name || run.workflow_name || run.id)}</strong>${workStatusHTML(run.status)}<small>게시 v${esc(run.version || run.published_version)} · 완료 ${esc(run.progress?.completed || 0)}/${esc(run.progress?.total || 0)}${run.closed_at?' · '+esc(time(run.closed_at))+' 닫힘':' · '+esc(time(run.created_at))+' 개시'}</small></button>`).join('') || '<p class="ew-empty">저장된 진행 건이 없습니다.</p>'}`;
}
function workHistoryHTML(run,jobId='',currentSettings=null){
  const {esc}=workUI,attempts=(run?.attempts || []).filter(attempt=>!jobId||attempt.job_id===jobId);
  if(!attempts.length)return '<p class="ew-empty">저장된 실행 시도가 없습니다. 미수행을 성공으로 표시하지 않습니다.</p>';
  return attempts.slice().reverse().map(attempt=>`<details class="ew-history" data-key="history-${esc(attempt.id)}"><summary>${workStatusHTML(attempt.status,attempt.snapshot?.job?.mode==='human'?'사람 확인 기록':'')}<span>${esc(attempt.number || attempt.sequence || attempt.id)}차 · ${esc(workUI.time(attempt.created_at || attempt.started_at))}</span></summary>${attempt.evidence_access==='requires_current_source_access'?'<p class="ew-warning">현재 계정의 원본 접근 권한을 다시 확인해야 합니다. 다른 사람의 비공개 근거를 표시하지 않습니다.</p>':''}<p>실행 당시 절차 v${esc(attempt.version || run.version)}${attempt.snapshot?.shared_tool?' · 공용 도구 v'+esc(attempt.snapshot.shared_tool.version):''} · 결과 r${esc(attempt.result_revision ?? attempt.number ?? '미기록')}</p>${workPartialSourceHTML(attempt,run)}<section><h4>이 실행에 쓴 값</h4>${workHistoricalValuesHTML(attempt,currentSettings)}</section><dl class="ew-facts"><div><dt>도구 참조</dt><dd><pre>${esc(JSON.stringify(attempt.tool_reference ?? attempt.snapshot?.tool_reference ?? attempt.snapshot?.job?.tool_reference ?? attempt.snapshot?.job?.tool_contract_id ?? {},null,2))}</pre></dd></div><div><dt>결과</dt><dd><pre>${esc(JSON.stringify(attempt.result ?? {},null,2))}</pre></dd></div></dl>${(attempt.review_history || []).map(review=>`<section class="ew-review-history"><h4>${review.decision_id?'사람 확정 당시 본문':'저장한 검토 초안'} · r${esc(review.revision)}</h4><p>${esc(workUI.time(review.created_at))} · ${esc(review.actor_id)}</p><pre>${esc(review.text)}</pre></section>`).join('')}${(attempt.decisions || (run?.jobs?.[attempt.job_id]?.decision_history ? run.jobs[attempt.job_id].decision_history.filter(decision=>decision.attempt_id===attempt.id) : [])).map(d=>`<p>사람 판정 · ${esc(d.actor_id)} · ${esc(d.verdict)} · ${esc(d.created_at)}${d.note?' · '+esc(d.note):''}</p>`).join('')}<button type="button" data-action="ask_record" data-attempt-id="${esc(attempt.id)}" data-job-id="${esc(attempt.job_id)}" class="ew-text">${workUI.icon('1c98e')} 이 기록에 대해 묻기</button></details>`).join('');
}
function workMyWorkHTML(items=[],operations={}){
  const {esc,button,icon}=workUI,groups={incident:'진행 중 장애',overdue:'기한 지남',today:'오늘',week:'이번 주',future:'예정',undated:'기한 없음'};
  if(!items.length){const next=(operations.schedules || []).filter(item=>item.enabled&&Number.isFinite(item.next_at)).sort((a,b)=>a.next_at-b.next_at)[0];return `<div class="ew-empty ew-my-work-empty"><span class="ew-empty-symbol">${icon('52271')}</span><h3>지금 처리할 내 업무가 없습니다</h3>${next?`<p>${icon('63982')} 다음 자동 실행 · ${esc(workUI.time(next.next_at))} · ${esc(next.name || next.workflow_name || '게시 절차 예약')}</p>`:''}</div>`;}
  return Object.entries(groups).map(([key,title])=>{const list=items.filter(item=>(item.bucket || item.group || 'undated')===key);return list.length?`<section class="ew-todo-group"><h3>${key==='incident'?icon('f49d4'):key==='today'?icon('8fa06'):''}${title}<span>${list.length}</span></h3>${list.map(item=>`<button type="button" class="ew-todo" data-action="open_task" data-task-id="${esc(item.id)}" data-schedule-id="${esc(item.schedule_id || '')}" data-run-id="${esc(item.run_id)}" data-job-id="${esc(item.job_id)}" data-workflow-id="${esc(item.workflow_id)}"><span class="ew-todo-title">${workStatusHTML(item.status || 'awaiting_confirmation',item.name || item.title)}${icon('69549')}</span><small>${esc(item.workflow_name || '')}${item.factory_name?' · '+esc(item.factory_name):''}</small><small>${esc(workReasonText(item.reason,operations.shared_tool_messages))}${item.due_at?' · '+esc(item.due_at):''}</small>${(item.claimed_by || item.claim_actor)?`<small>담당 ${esc(item.claimed_by || item.claim_actor)}</small>`:''}</button>`).join('')}</section>`:'';}).join('');
}

function workExportText(document){
  const run=document.run;if(!run)return '';const lines=[run.definition?.name || run.workflow_name || 'EES Workflow 기록',`진행 건 ${run.id} · 게시 v${run.version} · ${run.status}`,`내보낸 시각 ${document.exported_at || ''}`];
  for(const attempt of run.attempts || []){lines.push('',`작업 ${run.definition?.nodes?.[attempt.job_id]?.name || attempt.job_id} · 시도 ${attempt.number} · ${attempt.status}`,`기록 시각 ${attempt.created_at || ''}`,'입력',JSON.stringify(attempt.inputs || {},null,2),'결과',JSON.stringify(attempt.result ?? {},null,2));for(const review of attempt.review_history || [])lines.push(`검토 본문 · 시도 ${attempt.id} · 검토 r${review.revision} · ${review.decision_id?'사람 확정':'초안'}`,review.text || '');if(attempt.evidence_access==='requires_current_source_access')lines.push('현재 원본 접근 권한 확인 필요 · 비공개 근거 제외');}
  for(const [id,job] of Object.entries(run.jobs || {}))for(const decision of job.decisions || [])lines.push(`사람 판정 · ${id} · ${decision.item_id} · 결과 r${decision.result_revision} · ${decision.verdict} · ${decision.actor_id} · ${decision.created_at}`);
  return lines.join('\n');
}
function workLegacyHTML(legacy){
  const {esc,button}=workUI;if(!legacy)return '';if(legacy.error)return `<p class="ew-warning">이전 기록 조회 실패 · ${esc(legacy.error)}</p>`;
  return `<section class="ew-legacy"><h3>이전 버전 기록</h3><p class="ew-muted">${esc(legacy.notice || '이전 실행 기능은 사용 중지되었습니다. 남아 있는 과거 기록만 읽습니다.')}</p>${(legacy.records || []).map(item=>button(`${item.process_name || item.id} · ${item.status || '상태 미기록'}${item.simulation?' · 시뮬레이션':''}`,'open_legacy',`data-case-id="${esc(item.id)}" class="ew-record"`)).join('') || '<p class="ew-empty">조회할 이전 기록이 없습니다.</p>'}</section>`;
}

function workHistoricalReferenceHTML(run,reference,workflow,currentSettings=null){
  const {esc}=workUI;
  if(!reference?.run_id&&workflow?.id===reference?.workflow_id){const version=workflow.versions?.find(item=>item.version===reference.version);return version?`<header class="ew-work-heading"><h2>대화에서 참조한 게시 절차</h2><p>게시 v${esc(version.version)} · 읽기 전용</p></header><pre>${esc(JSON.stringify(version.definition,null,2))}</pre>`:'<p class="ew-warning">이 메시지에는 보존된 게시 버전이 지정되지 않았습니다. 현재 편집 초안을 당시 내용으로 대신 표시하지 않습니다.</p>';}
  if(!run||reference?.run_id!==run.id)return '<p class="ew-warning">현재 권한으로 이 진행 건의 기록을 확인하지 못했습니다.</p>';
  if(!reference.attempt_id)return '<p class="ew-warning">이 메시지에는 당시 실행 시도 식별자가 기록되지 않았습니다. 현재 결과를 과거 근거로 대신 표시하지 않습니다.</p>';
  const attempt=(run.attempts || []).find(item=>item.id===reference.attempt_id&&item.job_id===reference.job_id);
  if(!attempt||reference.version!==undefined&&reference.version!==run.version||reference.result_revision!==undefined&&reference.result_revision!==attempt.number)return '<p class="ew-warning">참조한 버전·실행 시도를 현재 권한으로 확인하지 못했습니다. 다른 시도의 결과로 대신 표시하지 않습니다.</p>';
  return `<header class="ew-work-heading"><h2>대화에서 참조한 과거 기록</h2><p>게시 v${esc(run.version)} · 실행 시도 ${esc(attempt.number)} · 읽기 전용</p></header>${workHistoryHTML({...run,attempts:[attempt]},reference.job_id,currentSettings)}`;
}
function workMessageReferenceHTML(reference,messageId){
  if(reference?.kind!=='workspace'||!reference.workflow_id)return '';
  const {esc,icon}=workUI,label=reference.attempt_id?`업무 근거 · v${reference.version ?? '?'} · ${reference.result_revision ?? '?'}차`:reference.run_id?'업무 참조 · 당시 시도 미지정':'업무 절차 참조';
  return `<button type="button" data-action="open_reference" data-message-id="${esc(messageId)}">${icon('522b5')}<span>${esc(label)}<small>기준 시각 · ${esc(workUI.time(reference.created_at || reference.basis_at) || '기록 없음')}</small></span></button>`;
}

function workAdminHTML(data){
  const {esc,button}=workUI;if(!data.capabilities?.is_admin)return '<p class="ew-warning">Native 관리자 권한이 필요합니다.</p>';
  const roles={viewer:'조회',participant:'참여·실행',manager:'절차·설정 관리',requester:'EES 요청',reviewer:'요청 검토'};
  return `<header class="ew-work-heading"><h2>공장·접근 범위</h2><p>기존 Native 사용자와 그룹에 업무 범위를 연결합니다. 개인 PAT는 여기에서 관리하지 않습니다.</p></header><section><h3>Native 대화의 Work 연결</h3><p class="ew-muted">현재 제품의 읽기·제안 전용 도구를 확인하고, 선택한 Native 사용자·그룹에만 연결합니다.</p>${button('Work 도구 설정 확인','admin_work_tool','class="ew-secondary"')}</section><section><h3>공장 정보</h3>${button('공장 등록','admin_factory','class="ew-secondary"')}<div class="ew-admin-list">${(data.factories || []).map(item=>`<article><strong>${esc(item.name)}</strong><small>${esc(item.system_id)} · ${esc(item.id)} · r${esc(item.revision)}</small>${button('수정','admin_factory',`data-id="${esc(item.id)}"`)}</article>`).join('') || '<p class="ew-empty">등록된 공장이 없습니다.</p>'}</div></section><section><h3>업무 접근 범위</h3>${button('접근 범위 등록','admin_access','class="ew-secondary"')}<div class="ew-admin-list">${(data.access || []).map(item=>{const person=(data.people || []).find(person=>person.value?.id===item.principal_id&&person.value?.kind===item.principal_kind);return `<article><strong>${esc(person?.label || person?.name || item.principal_id)}</strong><small>${esc(item.principal_kind)} · ${esc(item.principal_id)}</small><p>${esc(item.system_id)} · ${esc(item.factory_id==='*'?'시스템 전체 범위':item.factory_id)} · ${esc(item.roles.map(role=>roles[role] || role).join(', '))} · ${item.active?'사용':'중지'}</p>${button('수정','admin_access',`data-id="${esc(item.id)}"`)}</article>`;}).join('') || '<p class="ew-empty">등록된 업무 접근 범위가 없습니다.</p>'}</div></section>`;
}

// Reconcile only the source-supplied EES content slot. Retained controls keep
// focus, selection and browser state; no Native-owned DOM is read or changed.
function workPatchContent(host,html){
  const template=document.createElement('template');
  if(!template.content){host.innerHTML=html;return;} // lightweight test DOM
  template.innerHTML=html;
  const footer=template.content.querySelector('#ees-work-content>.ew-job-actions, #ees-work-content>.ew-next-action');if(footer)template.content.append(footer);
  const key=node=>node.nodeType===1?(node.id || ['name','data-key','data-author-action','data-action'].map(name=>node.getAttribute(name) || '').join('|')+'|'+['data-id','data-job-id','data-workflow-id','data-tab'].map(name=>node.getAttribute(name) || '').join('|')+(['checkbox','radio'].includes(node.type)||node.tagName==='OPTION'?'|'+node.getAttribute('value'):'')):'';
  const same=(a,b)=>a.nodeType===b.nodeType&&a.nodeName===b.nodeName&&key(a)===key(b);
  function children(parent,next){
    let cursor=parent.firstChild;
    for(const wanted of [...next.childNodes]){
      let current=cursor;
      if(!current||!same(current,wanted)){
        current=[...parent.childNodes].slice(cursor?[...parent.childNodes].indexOf(cursor):parent.childNodes.length).find(node=>same(node,wanted));
        if(current)parent.insertBefore(current,cursor);else{current=wanted.cloneNode(true);parent.insertBefore(current,cursor);}
      }
      patch(current,wanted);cursor=current.nextSibling;
    }
    while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
  }
  function patch(current,wanted){
    if(current.nodeType!==1){if(current.nodeValue!==wanted.nodeValue)current.nodeValue=wanted.nodeValue;return;}
    const open=current.tagName==='DETAILS'&&!current.matches('.ew-author-ai,.ew-tool-advanced')?current.open:null;
    for(const attr of [...current.attributes])if(!wanted.hasAttribute(attr.name))current.removeAttribute(attr.name);
    for(const attr of [...wanted.attributes])if(current.getAttribute(attr.name)!==attr.value)current.setAttribute(attr.name,attr.value);
    if(current.tagName==='TEXTAREA'){
      if(current.value!==wanted.value)current.value=wanted.value;
      if(current.defaultValue!==wanted.defaultValue)current.defaultValue=wanted.defaultValue;
    }else{
      children(current,wanted);
      if(current.tagName==='INPUT'){
        if(current.type!=='file'&&current.value!==wanted.value)current.value=wanted.value;
        if(current.checked!==wanted.checked)current.checked=wanted.checked;
      }else if(current.tagName==='SELECT'){
        for(let i=0;i<current.options.length;i++)if(current.options[i].selected!==wanted.options[i]?.selected)current.options[i].selected=Boolean(wanted.options[i]?.selected);
      }
    }
    if(open!==null)current.open=open;
  }
  children(host,template.content);
}

function workRestorePanelPosition(host,position){
  if(!position)return;
  const expanded=new Set(position.expanded || []);
  for(const detail of host.querySelectorAll('details[data-key]'))detail.open=expanded.has(detail.dataset.key);
  const content=host.querySelector('#ees-work-content');if(content)content.scrollTop=position.scroll;
}

// These are the pinned Native destinations, not URLs supplied by a page or user.
const workNativeTargets=Object.freeze([
  {id:'skills',label:'스킬·지침',name:'스킬',path:'/workspace/skills',icon:'f908d'},
  {id:'models',label:'AI 도우미',name:'모델',path:'/workspace/models',icon:'cf77a'},
  {id:'knowledge',label:'참고 문서',name:'지식',path:'/workspace/knowledge',icon:'730b1'},
  {id:'prompts',label:'빠른 문장',name:'프롬프트',path:'/workspace/prompts',icon:'093d6'},
  {id:'tools',label:'Open WebUI 도구',name:'도구',path:'/workspace/tools',icon:'cece5',admin:true},
  {id:'admin',label:'관리자 설정',name:'관리자',path:'/admin/settings',icon:'f34f3',admin:true}
].map(Object.freeze));
function workNativeAllowed(capabilities,id){
  const target=workNativeTargets.find(item=>item.id===id);
  return Boolean(target&&capabilities?.native_access_available===true&&capabilities.native_access?.[id]===true&&(!target.admin||capabilities.is_admin===true));
}
function workCanCreate(capabilities){return capabilities?.is_admin===true||capabilities?.can_author===true||capabilities?.can_manage===true;}
function workCanWorkspace(capabilities){
  return workCanCreate(capabilities)||Boolean(capabilities?.managed_systems?.length)||Boolean(capabilities?.native_access_available===true&&['models','knowledge','prompts','skills','tools'].some(id=>capabilities.native_access?.[id]===true));
}
function workWorkspaceMenuHTML(state,selection,error=''){
  const {esc,icon}=workUI,capabilities=state.capabilities || {},current=(state.workflows || []).filter(workflow=>!selection.system_id||workflow.system_id===selection.system_id);
  const item=(action,asset,label,{active=false,count,native,id}={})=>`<button type="button" class="ew-nav-button" data-action="${action}"${id?` data-native-id="${id}"`:''} aria-label="${label}" title="${label}"${active?' aria-current="page"':''}>${['models','tools','admin'].includes(id)||action==='workspace_admin'?`<span class="ew-icon ew-native-icon" data-native-icon="${action==='workspace_admin'?'factory':id}" aria-hidden="true"></span>`:icon(asset)}<span class="ew-nav-label">${label}</span>${native?`<small class="ew-nav-native-name">${native}</small>`:count===undefined?'':`<small>${count}</small>`}</button>`;
  const native=target=>item('native_open',target.icon,target.label,{native:target.name,id:target.id,active:selection.native_id===target.id});
  const group=(title,items)=>items?`<section class="ew-nav-group"><h3 class="ew-nav-group-title">${title}</h3><nav class="ew-nav-links">${items}</nav></section>`:'';
  const create=workCanCreate(capabilities)?item('procedures','e8a37','업무 절차',{count:current.length,active:!selection.native_id&&!['tools','workspace_admin'].includes(selection.tab)})+item('tools','d1220','도구',{count:state.operations?.error?undefined:(state.operations?.tools || []).length+(state.operations?.shared_tools || []).length,active:!selection.native_id&&selection.tab==='tools'}):'';
  const skill=workNativeAllowed(capabilities,'skills')?native(workNativeTargets.find(item=>item.id==='skills')):'';
  const ordinary=workNativeTargets.filter(target=>!target.admin&&target.id!=='skills'&&workNativeAllowed(capabilities,target.id)).map(native).join('');
  const admin=capabilities.is_admin===true?[item('workspace_admin','f34f3','공장·접근 범위',{active:!selection.native_id&&selection.tab==='workspace_admin'}),workNativeAllowed(capabilities,'admin')?native(workNativeTargets.find(target=>target.id==='admin')):''].join(''):'';
  const groups=group('업무 만들기',create+skill)+group('AI 설정',ordinary)+group('관리자만',admin);
  const recent=workCanCreate(capabilities)?current.filter(workflow=>workflow.updated_at).slice().sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))).slice(0,8):[];
  return groups+(recent.length?`<p class="ew-nav-caption">최근 편집</p><nav class="ew-workflows ew-recent">${recent.map(workflow=>`<button type="button" data-action="workflow" data-workflow-id="${esc(workflow.id)}"${!selection.native_id&&workflow.id===selection.workflow_id?' aria-current="page"':''}>${icon({ops:'126c7',setup:'f6bbc',incident:'4fb09'}[workflow.category] || 'e8a37')}<span>${esc(workflow.name)}</span></button>`).join('')}</nav>`:'')+(!groups?'<p class="ew-empty">EES Workflow에서 열 수 있는 항목이 없습니다</p>':'')+(error?`<p class="ew-error" role="alert" data-native-navigation-error>${esc(error)}</p><button type="button" data-action="refresh">다시 확인</button>`:'');
}

// Operations25 presents actual Jobs. Result items remain inside their Job;
// execution status never becomes an inferred approval or an AI final verdict.
function workPublishedDefinition(data={}){
  const workflow=data?.workflow || {},published=workflow.published;
  if(published?.definition?.nodes)return published.definition;
  if(published?.nodes)return published;
  return workflow.versions?.find(item=>item.version===workflow.published_version)?.definition || {};
}
function workOperationDefinition(data={}){return data?.run?.definition || workPublishedDefinition(data);}
function workOperationTarget(data={},selection={}){
  const definition=workOperationDefinition(data),factoryId=data.run?.factory_id ?? selection.factory_id,factory=(data.factories || []).find(item=>item.id===factoryId);
  const system=data.run?.system_id || data.workflow?.system_id || selection.system_id || '';
  return [definition.execution_scope==='system'?'전체 공장':factory?.name || data.run?.factory_name || (factoryId?'공장 이름 확인 필요':'전체 공장'),system].filter(Boolean).join(' · ');
}
function workStageNoteKey(data,node){const saved=data.run?.jobs?.[node.id] || {};return [data.capabilities?.actor_id,data.run?.id,node.id,saved.attempt_id || saved.current_attempt || '',saved.result_revision || 0].join('/');}
function workStageTarget(data,selection={}){
  if(!data||selection.mode==='author'||selection.job_id||['historical_reference','workspace_admin','my_work','records','start','run_details'].includes(selection.tab))return null;
  const stages=Object.values(workOperationDefinition(data).nodes || {}).filter(node=>node.type==='t');
  return stages.find(node=>node.id===selection.stage_id) || (data.run&&!selection.stage_overview&&!workUI.finished(data.run)&&stages.length===1?stages[0]:null);
}
function workStageJudgments(node={},definition={}){
  const configured=Array.isArray(node.judgments)?node.judgments:definition.judgments;
  if(Array.isArray(configured)&&configured.length)return configured.filter(item=>item&&typeof item.id==='string'&&typeof item.label==='string'&&['completed','failed','unknown','action_required'].includes(item.status));
  const legacy=Array.isArray(node.verdicts)?node.verdicts:[];
  if(legacy.length)return legacy.map(item=>({id:item.id ?? item.value,label:item.label ?? item.name ?? item.id,status:item.status ?? item.meaning ?? item.id ?? item.value,legacy:true})).filter(item=>typeof item.id==='string'&&['completed','failed','unknown','action_required'].includes(item.status));
  return [{id:'completed',label:'적합',status:'completed',legacy:true},{id:'failed',label:'미흡',status:'failed',legacy:true},{id:'unknown',label:'판단 불가',status:'unknown',legacy:true}];
}
function workStageNoteLimit(node,definition){
  // The existing API stores its configured-judgment marker in the same 4,000
  // character field. Reserve it before input so a saved reason is never cut.
  const marker=workStageJudgments(node,definition).filter(word=>!word.legacy).map(word=>Array.from('\n선택한 판정: '+word.label+' ('+word.id+')').length);
  return Math.max(0,4000-Math.max(0,...marker));
}
function workStageDecision(node,saved={},definition={},attempt=null){
  const decision=saved.decisions?.job;if(!decision)return null;
  const sourceNode=attempt?.snapshot?.job || node,sourceDefinition=attempt?.snapshot?.definition || definition,words=workStageJudgments(sourceNode,sourceDefinition),note=String(decision.note || '');
  const exact=words.find(word=>!word.legacy&&word.status===decision.verdict&&note.endsWith('\n선택한 판정: '+word.label+' ('+word.id+')'));
  const same=words.filter(word=>word.status===decision.verdict),word=exact || (same.length===1?same[0]:null);
  return {...decision,decision_id:decision.id,id:word?.id || decision.verdict,label:word?.label || workUI.statuses[decision.verdict] || decision.verdict,judgment_id:word?.id || '',note:exact?note.slice(0,-('\n선택한 판정: '+exact.label+' ('+exact.id+')').length):note};
}
function workStageCanDecide(node,saved={},run={}){
  if(workUI.finished(run)||run.can_write===false||saved.can_decide===false||saved.can_execute===false||['running','excluded'].includes(saved.status)||['item_verdict','list_confirm','checklist','ai_review','change_request'].includes(node.result_block))return false;
  if((node.mode || 'human')==='human')return true;
  return node.human_confirmation!==false&&Boolean(saved.attempt_id || saved.current_attempt)&&!saved.decisions?.job&&!saved.evidence_access&&!saved.result_stale&&['waiting_confirmation','awaiting_confirmation','partial'].includes(saved.status);
}
function workStageAutomatic(node){return node.mode!=='human'&&Boolean(node.mode)&&node.human_confirmation===false&&!['item_verdict','ai_review','change_request'].includes(node.result_block);}
function workStageTone(value,label=''){return label==='조건부 승인'?'cond':value==='completed'?'ok':value==='failed'?'bad':'none';}
function workStageCanExecute(node,saved,run,data){
  if(!['tool','ai'].includes(node.mode)||node.result_block==='change_request'||workUI.finished(run)||run.can_write===false||saved.can_execute===false||['running','excluded'].includes(saved.status))return false;
  if(node.shared_tool_id){const shared=data.operations?.shared_tools?.find(item=>item.id===node.shared_tool_id),pin=run.shared_tools?.find(item=>item.id===node.shared_tool_id),access=data.operations?.shared_tool_access?.[node.id];if(!shared||shared.state!=='available'||shared.can_use===false||access?.can_use===false||(pin&&pin.version!==shared.version))return false;}
  return true;
}
function workStageRows(data,stage){
  const run=data.run || {},definition=workOperationDefinition(data);
  return Object.values(definition.nodes || {}).filter(node=>node.type==='j'&&workUI.lineage(node.id,definition).some(parent=>parent.id===stage.id)).map(node=>{
    const saved=run.jobs?.[node.id] || {},attempts=(run.attempts || []).filter(item=>item.job_id===node.id),attempt=attempts.find(item=>item.id===(saved.attempt_id || saved.current_attempt)),decision=workStageDecision(node,saved,definition,attempt),automatic=workStageAutomatic(node),state=saved.status || 'unstarted';
    let group='waiting',label='',tone='none';
    if(state==='running'){group='running';label='실행 중';}
    else if(saved.result_stale||state==='review_required')label='다시 검토 필요';
    else if(decision){group='result';label=decision.label;tone=workStageTone(decision.verdict,label);}
    else if(state==='completed'){group='result';label=automatic?'실행 완료':'완료';tone='ok';}
    else if(['failed','partial','unknown','cancelled','excluded'].includes(state)){group='result';label=state==='failed'?'실행 실패':workUI.statuses[state] || state;}
    else if(['waiting_input','awaiting_input','blocked','scheduled'].includes(state))label=workUI.statuses[state];
    else if((node.mode || 'human')==='human'||['waiting_confirmation','awaiting_confirmation'].includes(state))label='판정 필요';
    else label='실행 필요';
    return {node,saved,attempt,attempts,decision,automatic,state,group,label,tone,canDecide:Boolean(data.run)&&workStageCanDecide(node,saved,run),canExecute:Boolean(data.run)&&workStageCanExecute(node,saved,run,data)};
  });
}
const workStageActionIcons=Object.freeze({play:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M4.5 2.75L11 7L4.5 11.25V2.75Z" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>',retry:'<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5V5h-2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'});
function workStageValuesHTML(value){
  const {esc}=workUI,entries=value&&typeof value==='object'&&!Array.isArray(value)?Object.entries(value):[['값',value]];
  return entries.length?`<dl class="ew-vd-tool-values">${entries.map(([key,item])=>`<dt>${esc(key)}</dt><dd>${item&&typeof item==='object'?`<pre>${esc(JSON.stringify(item,null,2))}</pre>`:esc(item ?? '기록 없음')}</dd>`).join('')}</dl>`:'<p>기록된 값이 없습니다.</p>';
}
function workStageNoteHTML(row,data,selection,savedNote='',recorded=false){
  const {esc}=workUI,key=workStageNoteKey(data,row.node),readonly=recorded||!data.run||!row.canDecide,value=recorded?savedNote:selection.stage_notes?.[key] || '',limit=workStageNoteLimit(row.node,workOperationDefinition(data));
  return `<label class="ew-vd-note"><span>사유 <small>(선택)</small></span><textarea data-stage-note data-job-id="${esc(row.node.id)}" maxlength="${limit}" aria-label="${esc(row.node.name)} 판정 사유"${readonly?` readonly aria-readonly="true" title="${recorded?'저장된 판정 사유':'읽기 전용 판정 사유'}"`:' placeholder="판정과 함께 남길 사유를 입력해 주세요."'}>${esc(value)}</textarea></label>`;
}
function workStageEvidenceHTML(row,data,selection){
  const {esc,icon,time}=workUI,{node,saved,attempts,automatic}=row,run=data.run || {},id=node.id;
  if(!automatic&&(!node.mode||node.mode==='human')){
    const decisions=Array.isArray(saved.decision_history)?saved.decision_history:Object.values(saved.decisions || {}),records=decisions.filter(item=>item.item_id==='job').slice().sort((a,b)=>(b.result_revision || 0)-(a.result_revision || 0)||String(b.created_at || '').localeCompare(String(a.created_at || '')));
    const recordHTML=record=>{const attempt=attempts.find(item=>item.id===record.attempt_id),decision=workStageDecision(node,{decisions:{job:record}},workOperationDefinition(data),attempt),person=(data.people || []).find(item=>item.id===record.actor_id || item.value?.id===record.actor_id);return `<div class="ew-vd-selection-record"><p data-human-selection><b>${esc(decision.label)} 선택</b><span>${esc(person?.name || person?.label || record.actor_id)} · ${esc(time(record.created_at))}</span></p></div>${workStageNoteHTML(row,data,selection,decision.note,true)}`;};
    return `<div class="ew-vd-evidence ew-vd-human-record" id="stage-evidence-${esc(id)}">${records.length?recordHTML(records[0])+(records.length>1?`<details class="ew-vd-prior-selections"><summary>이전 판정 ${records.length-1}건</summary>${records.slice(1).map(recordHTML).join('')}</details>`:''):`<div class="ew-vd-selection-record"><p>아직 판정을 선택하지 않았습니다.</p></div>${workStageNoteHTML(row,data,selection)}`}</div>`;
  }
  const selected=attempts.find(item=>item.id===selection.stage_attempts?.[id]),attempt=selected || (row.state==='running'?attempts.filter(item=>item.status!=='running').at(-1):row.attempt) || (row.state==='running'?null:attempts.at(-1)),pending=row.state==='running'?'<p class="ew-execution-pending" role="status">실행 중 · 이번 실행 결과는 아직 없습니다.</p>':'';
  const selector=attempts.length>1?`<label class="ew-attempt-select"><span>실행 내역</span><select data-stage-attempt data-job-id="${esc(id)}" aria-label="${esc(node.name)} 실행 내역">${attempts.slice().reverse().map(item=>`<option value="${esc(item.id)}"${item.id===(attempt?.id || selected?.id || saved.current_attempt)?' selected':''}>${esc(item.number)}차 · ${esc(time(item.finished_at || item.created_at))}</option>`).join('')}</select></label>`:'';
  if(!attempt||attempt.status==='running')return `<div class="ew-vd-evidence" id="stage-evidence-${esc(id)}">${selector}${pending || '<p>아직 실행하지 않았습니다.</p>'}</div>`;
  if(attempt.evidence_access || (attempt.id===saved.attempt_id&&saved.evidence_access))return `<div class="ew-vd-evidence" id="stage-evidence-${esc(id)}">${selector}<p>현재 계정으로 근거를 다시 확인해야 합니다.</p></div>`;
  const attemptRecord=(saved.decision_history || Object.values(saved.decisions || {})).find(item=>item.item_id==='job'&&item.attempt_id===attempt.id),attemptDecision=attemptRecord?workStageDecision(node,{decisions:{job:attemptRecord}},run.definition,attempt):null,old=attempt.id!==(saved.attempt_id || saved.current_attempt),snapshot=attempt.snapshot || {},reference=snapshot.tool_reference || snapshot.job?.tool_reference || {},shared=snapshot.shared_tool || {},toolKey=attempt.id+':tool',opened=selection.stage_tool===toolKey,toolName=shared.name || reference.name || reference.function || reference.tool_id || (node.mode==='ai'?'AI 실행':'작업 실행'),result=attempt.result ?? {},status=attempt.status==='succeeded'?'실행 완료':attempt.status==='failed'?'실행 실패':workUI.statuses[attempt.status] || attempt.status,criterion=snapshot.job?.completion?.rule || snapshot.job?.instructions || '',skills=Array.isArray(snapshot.skills)?snapshot.skills:[],argumentsUsed=snapshot.arguments ?? attempt.inputs ?? {};
  const details=`<div class="ew-vd-tool-detail" id="stage-tool-${esc(id)}"><section><h4>입력 <span>Input</span></h4>${workStageValuesHTML(argumentsUsed)}</section><section><h4>출력 <span>Output</span></h4>${workStageValuesHTML(result)}</section>${criterion?`<section><h4>실행 당시 작업 기준</h4><p>${esc(criterion)}</p></section>`:''}${skills.length?`<section><h4>실행 당시 연결 지침</h4>${skills.map(skill=>`<p>${esc(skill.name || skill.title || skill.id || '지침')}</p>${skill.body || skill.content || skill.instructions?`<p>${esc(skill.body || skill.content || skill.instructions)}</p>`:''}`).join('')}</section>`:''}<section class="ew-vd-tool-result"><h4>실행 결과 · <span>${esc(status)}</span></h4>${typeof result.summary==='string'?`<p>${esc(result.summary)}</p>`:''}</section></div>`;
  return `<div class="ew-vd-evidence ew-vd-service-evidence" id="stage-evidence-${esc(id)}">${pending}${selector}<p class="ew-attempt-caption" data-attempt-number="${esc(attempt.number)}"><b>${old?'이전 실행 결과':'현재 실행 결과'} · ${esc(attempt.number)}차</b><span>${esc(time(attempt.finished_at || attempt.created_at))}</span></p><div class="ew-vd-evidence-caption"><b>${node.mode==='tool'&&['succeeded','failed','partial'].includes(attempt.status)?'실행 도구 1개':'실행 기록'}</b></div><section class="ew-vd-tool"><button type="button" class="ew-vd-tool-toggle" data-action="stage_tool" data-job-id="${esc(id)}" data-tool-key="${esc(toolKey)}" aria-expanded="${opened}"${opened?' aria-controls="stage-tool-'+esc(id)+'"':''}><span class="ew-vd-tool-heading"><span><b>${esc(toolName)}</b></span><small>${esc(status)} · ${esc(time(attempt.finished_at || attempt.created_at))}</small></span>${icon('f17e6')}</button>${opened?details:''}</section>${attemptDecision?`<p class="ew-vd-task-result"><b>${old?'당시 작업 판정':'작업 판정'} · ${esc(attemptDecision.label)}</b>${attemptDecision.note?`<span>${esc(attemptDecision.note)}</span>`:''}</p>`:''}</div>`;
}
function workStageRowHTML(row,data,selection){
  const {esc,icon}=workUI,{node,saved,automatic,group,label,tone,canDecide,canExecute}=row,id=node.id,opened=selection.stage_evidence===id;
  const hasExecution=['tool','ai'].includes(node.mode)&&node.result_block!=='change_request',runLabel=row.state==='running'?'실행 중':row.attempts.length?'다시 실행':'실행';
  const execution=hasExecution?`<button type="button" class="ew-vd-run" data-action="${data.run?'stage_execute':'stage_start'}" data-job-id="${esc(id)}" aria-label="${esc(node.name+' '+runLabel)}"${data.run?' data-mutation':''}${!data.run||canExecute?'':' disabled data-own-disabled="true"'}>${row.attempts.length?workStageActionIcons.retry:workStageActionIcons.play}<span>${runLabel}</span></button>`:'';
  const dot=group==='result'?`<i class="ew-vd-dot" data-verdict="${tone}"></i>`:'',choice=canDecide||!data.run&&!automatic?`<button type="button" class="ew-vd-pick" data-action="${data.run?'stage_verdict':'stage_start'}" data-job-id="${esc(id)}"${group==='result'?` data-verdict="${tone}"`:''} ${data.run?`aria-haspopup="menu" aria-expanded="${selection.stage_verdict_job===id}" aria-controls="ees-stage-verdict-menu"`:''} aria-label="${esc(data.run?node.name+' '+label:node.name+' 판정을 위한 진행 건 시작 설정')}">${dot}<span>${esc(label)}</span>${icon('f17e6')}</button>`:`<span class="${group==='result'?'ew-vd-final':'ew-vd-state'}" data-decision-status>${dot}<span>${esc(label)}</span></span>`;
  const hasEvidence=(!node.mode||node.mode==='human')||row.attempts.length,evidenceLabel=(!node.mode||node.mode==='human')?'판정 기록':'판정 근거',evidence=hasEvidence?`<button type="button" class="ew-vd-evidence-toggle" data-action="stage_evidence" data-job-id="${esc(id)}" aria-expanded="${opened}"${opened?` aria-controls="stage-evidence-${esc(id)}"`:''} aria-label="${esc(node.name+' '+evidenceLabel+' '+(opened?'접기':'펼치기'))}">${evidenceLabel}${icon('f17e6')}</button>`:'';
  return `<section class="ew-vd-entry" data-stage-job="${esc(id)}" data-vd-item="${esc(id)}" data-handler="${automatic?'service':'human'}"><div class="ew-vd-item"><div class="ew-vd-item-top"><button type="button" class="ew-vd-name" data-action="job" data-job-id="${esc(id)}">${esc(node.name)}</button>${execution}</div><div class="ew-vd-item-meta"><b data-decision-actor>${automatic?'자동 판정':'직접 판정'}</b><div class="ew-vd-decision">${choice}${evidence}</div></div></div>${opened?workStageEvidenceHTML(row,data,selection):''}</section>`;
}
function workStageMenuHTML(data,selection,rows){
  const row=rows.find(item=>item.node.id===selection.stage_verdict_job);if(!row?.canDecide)return '';
  const {esc,icon}=workUI;
  return `<div id="ees-stage-verdict-menu" class="ew-vd-menu" role="menu" data-job-id="${esc(row.node.id)}" aria-label="${esc(row.node.name)} 판정 고르기">${workStageJudgments(row.node,workOperationDefinition(data)).map(word=>`<button type="button" role="menuitemradio" class="ew-vd-option" data-action="stage_decide" data-job-id="${esc(row.node.id)}"${word.legacy?'':` data-judgment-id="${esc(word.id)}"`} data-verdict="${esc(word.status)}" aria-checked="${row.decision?.judgment_id===word.id}" tabindex="-1" data-mutation><i class="ew-vd-dot" data-verdict="${workStageTone(word.status,word.label)}"></i><span><b>${esc(word.label)}</b></span>${row.decision?.judgment_id===word.id?icon('9d8d5'):''}</button>`).join('')}</div>`;
}
function workStageLogHTML(rows,data){
  const {esc,time}=workUI,events=[];
  for(const row of rows){for(const attempt of row.attempts)events.push({at:attempt.finished_at || attempt.created_at,text:row.node.name+' · '+attempt.number+'차 · '+(attempt.status==='succeeded'?'실행 완료':workUI.statuses[attempt.status] || attempt.status),job:row.node.id,attempt:attempt.id});for(const decision of (row.saved.decision_history || Object.values(row.saved.decisions || {})).filter(item=>item.item_id==='job')){const attempt=row.attempts.find(item=>item.id===decision.attempt_id),parsed=workStageDecision(row.node,{decisions:{job:decision}},data.run.definition,attempt);events.push({at:decision.created_at,text:row.node.name+' · '+parsed.label+' · '+decision.actor_id,job:row.node.id});}}
  events.sort((a,b)=>String(b.at || '').localeCompare(String(a.at || '')));
  return `<ol class="ew-vd-log">${events.map(event=>`<li><time datetime="${esc(event.at || '')}" title="${esc(time(event.at))}" aria-label="${esc(time(event.at))}">${esc(Number.isNaN(new Date(event.at).valueOf())?time(event.at):new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(event.at)))}</time><span>${esc(event.text)}${event.attempt?`<button type="button" class="ew-vd-evidence-toggle" data-action="stage_evidence" data-job-id="${esc(event.job)}" data-attempt-id="${esc(event.attempt)}">실행 내역 보기</button>`:''}</span></li>`).join('') || '<li><span>아직 기록이 없습니다.</span></li>'}</ol>`;
}
function workStageRulesHTML(rows,data){
  const {esc}=workUI,definitions=new Map();
  for(const row of rows)for(const word of workStageJudgments(row.node,workOperationDefinition(data)))definitions.set(word.id+'|'+word.label,word);
  return `<div class="ew-vd-rules"><section><h3>판정 단어</h3><ul>${[...definitions.values()].map(word=>`<li><i class="ew-vd-dot" data-verdict="${workStageTone(word.status,word.label)}"></i><b>${esc(word.label)}</b><span>${esc(word.consequence || workUI.statuses[word.status] || word.status)}</span></li>`).join('')}</ul></section>${rows.filter(row=>row.node.completion?.rule || row.node.instructions).map(row=>`<section><h3>${esc(row.node.name)}</h3><p>${esc(row.node.completion?.rule || row.node.instructions)}</p></section>`).join('')}</div>`;
}
function workStagePositiveGroup(rows,selection={}){
  const positive=rows.filter(row=>row.group==='result'&&row.tone==='ok');
  const visible=positive.find(row=>row.automatic&&row.node.id===selection.stage_evidence)||positive.find(row=>row.automatic);
  const rest=positive.filter(row=>row!==visible);
  return {positive,visible,rest,expanded:Boolean(selection.stage_approved_expanded)||rest.some(row=>row.node.id===selection.stage_evidence)};
}
function workStageHTML(data,selection,stage,options={}){
  const {esc,icon,time}=workUI,run=data.run || {},definition=workOperationDefinition(data),rows=workStageRows(data,stage),direct=rows.filter(row=>!row.automatic),automatic=rows.filter(row=>row.automatic),results=rows.filter(row=>row.group==='result'),scopes=(data.operations?.scope_runs || []).filter(scope=>scope.run_id===run.id&&(scope.node_id===stage.id||(scope.job_ids || []).some(id=>rows.some(row=>row.node.id===id)))&&['queued','running','waiting'].includes(scope.status)),active=rows.some(row=>row.state==='running')||scopes.length>0,scopeLabel=rows.some(row=>row.state==='running')||scopes.some(scope=>scope.status==='running')?'실행 중':'실행 대기',executable=rows.some(row=>row.canExecute&&!row.attempts.length),tab=['work','log','rules'].includes(selection.stage_tab)?selection.stage_tab:'work';
  const counts={ok:0,cond:0,bad:0,none:0};for(const row of rows)counts[row.group==='result'?row.tone:'none']++;
  const bar=Object.entries(counts).filter(([,n])=>n).map(([tone,n])=>`<i data-verdict="${tone}" style="flex:${n} 1 0"></i>`).join(''),workflowName=definition.name || data.workflow?.name || '업무',qualifier=run.cycle?.name || run.name || '';
  const context=' / '+workOperationTarget(data,selection);
  const header=`<header class="ew-panel-header ew-run-nav"><button type="button" class="ew-run-back" data-action="stage_back">${icon('eb94a')}<span>${esc(workflowName+context)}</span></button><span></span><button type="button" class="ew-icon-button" aria-label="더 보기" data-action="stage_details">${icon('a953c')}</button><button type="button" class="ew-icon-button" aria-label="업무 패널 닫기" data-action="close_panel">${icon('7bb4a')}</button></header>`;
  const head=`<div class="ew-vd-head"><div class="ew-stage-heading"><div class="ew-vd-title"><h2>${esc(stage.name)}</h2></div><button type="button" class="ew-primary ew-stage-run-button" data-action="${data.run?'execute_scope':'stage_start'}" data-node-id="${esc(stage.id)}"${data.run?' data-mutation':''} aria-label="${esc(stage.name)} 단계 실행"${(!data.run||executable)&&!active?'':' disabled data-own-disabled="true"'}>${workStageActionIcons.play}<span>${active?scopeLabel:'이 단계 실행'}</span></button></div><p class="ew-vd-sub"><span>작업 ${rows.length}개</span></p><div class="ew-vd-progress"><div class="ew-vd-bar" role="img" aria-label="작업 ${rows.length}개, 대기 ${rows.filter(row=>row.group==='waiting').length}개, 실행 중 ${rows.filter(row=>row.group==='running').length}개, 결과 ${results.length}개">${bar}</div><p class="ew-vd-statusline" data-person><b>직접 판정</b><span>선택 ${direct.filter(row=>row.decision).length}/${direct.length}</span></p><p class="ew-vd-statusline" data-service><b>자동 실행 완료 ${automatic.filter(row=>row.state==='completed').length}/${automatic.length}</b><span>${automatic.filter(row=>row.state==='failed').length?'실행 실패 '+automatic.filter(row=>row.state==='failed').length:automatic.some(row=>row.state==='running')?'실행 중 '+automatic.filter(row=>row.state==='running').length:''}</span></p></div></div>`;
  const tabs=`<nav class="ew-tabs" aria-label="작업 화면">${[['work','작업'],['log','기록'],['rules','기준']].map(([key,label])=>`<button type="button" data-action="stage_tab" data-tab="${key}" aria-pressed="${tab===key}">${label}</button>`).join('')}</nav>`;
  const modelControls=data.run&&rows.some(row=>row.node.mode==='ai')&&!workUI.finished(run)?(options.modelControls ?? workExecutionModelHTML(data.operations || {},selection.stage_model_id || '')):'',scopeNotice=scopes.filter(scope=>scope.reason).map(scope=>`<p class="ew-muted" role="status">${esc(workReasonText(scope.reason,data.operations?.shared_tool_messages))}</p>`).join(''),runtime=modelControls||scopeNotice?`<div class="ew-stage-runtime">${modelControls}${scopeNotice}</div>`:'';
  let list='';
  for(const [group,label] of [['waiting','대기'],['running','실행 중'],['result','판정 결과']]){const items=rows.filter(row=>row.group===group).sort((a,b)=>group==='waiting'?Number(b.label==='실행 필요')-Number(a.label==='실행 필요'):group==='result'?({cond:0,bad:1,none:2,ok:3}[a.tone]-{cond:0,bad:1,none:2,ok:3}[b.tone]):0);if(!items.length)continue;const {positive,visible,rest,expanded}=workStagePositiveGroup(items,selection);list+=`<section data-task-group="${group}"><h3 class="ew-vd-label">${label}<b>${items.length}</b></h3>${items.filter(row=>!positive.includes(row)).map(row=>workStageRowHTML(row,data,selection)).join('')}${visible?workStageRowHTML(visible,data,selection):''}${rest.length?`<button type="button" class="ew-vd-group" data-action="stage_approved" aria-expanded="${expanded}">${icon('69549')}<i class="ew-vd-dot" data-verdict="ok"></i><span class="ew-vd-group-label">나머지 ${rest.every(row=>row.label==='승인')?'승인':'완료'} ${rest.length}건</span></button>${expanded?rest.map(row=>workStageRowHTML(row,data,selection)).join(''):''}`:''}</section>`;}
  return {header,body:head+runtime+tabs+(tab==='log'?workStageLogHTML(rows,data):tab==='rules'?workStageRulesHTML(rows,data):`<div class="ew-vd-body">${list || '<p class="ew-empty">등록된 작업이 없습니다.</p>'}</div>`),menu:workStageMenuHTML(data,selection,rows)};
}

function workOperationOverviewHTML(data,selection){
  const {esc,icon}=workUI,definition=workOperationDefinition(data),nodes=Object.values(definition.nodes || {}),stages=nodes.filter(node=>node.type==='t');
  const mode=definition.mode || data.workflow?.mode || definition.execution_mode || data.workflow?.execution_mode || 'on_demand',schedules=(data.operations?.schedules || []).filter(item=>item.workflow_id===data.workflow?.id&&item.enabled),period={on_demand:'수시',periodic:'주기',emergency:'비상'}[mode] || mode;
  const timing=period+' · '+(schedules.length?'예약 '+schedules.length+'개':'예약 없음');
  const summaries=stages.map(stage=>{
    const rows=workStageRows(data,stage),counts=new Map();
    for(const row of rows){if(row.decision)counts.set(row.decision.label,(counts.get(row.decision.label)||0)+1);else if(row.group==='result'){const label=row.saved.partial_confirmed?'부분 결과 확정':row.label;counts.set(label,(counts.get(label)||0)+1);}}
    const status=[...counts].map(([label,count])=>label+' '+count).join(' · ');
    return `<button type="button" class="ew-operation-stage" data-action="stage_open" data-node-id="${esc(stage.id)}"><span><strong>${esc(stage.name)}</strong><small>작업 ${rows.length}개${status?' · '+esc(status):''}</small></span>${icon('69549')}</button>`;
  }).join('');
  return `<section class="ew-operation-overview"><h2>${esc(definition.name || data.workflow?.name || '업무')}</h2><dl class="ew-operation-context"><dt>주기</dt><dd>${esc(timing)}</dd><dt>적용 대상</dt><dd>${esc(workOperationTarget(data,selection))}</dd></dl><section class="ew-operation-stages"><h3>업무 단계</h3>${summaries || '<p class="ew-empty">게시된 단계가 없습니다.</p>'}</section></section>`;
}

function createWorkView({callbacks}){
  const {$,esc,button,icon,categories,badge,finished}=workUI;
  let snapshot={state:null,selection:{}},host=null,lastKey='';
  const drafts=createWorkInputDrafts(),reviewDrafts=createWorkInputDrafts(),listDrafts=new Map(),positions=new Map(),modelChoices=new Map();let currentDraftKey='';
  const state=()=>snapshot.native_capabilities!=null?{...(snapshot.state || {}),capabilities:snapshot.native_capabilities}:snapshot.state || {},selection=()=>snapshot.selection || {};
  const definition=()=>workOperationDefinition(state());
  const job=()=>definition().nodes?.[selection().job_id];
  const inputKey=(tab=selection().tab)=>[state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id,selection().job_id,tab].join('/');
  const modelKey=()=>[state().capabilities?.actor_id,selection().workflow_id,selection().run_id,selection().job_id].join('/');
  function executionModels(){const operations=state().operations || {},models=operations.models || [],key=modelKey();if(operations.error||models.length<=1||!models.some(model=>model.id===modelChoices.get(key)))modelChoices.delete(key);return workExecutionModelHTML(operations,modelChoices.get(key));}
  const resultKey=()=>[state().capabilities?.actor_id,state().run?.id,selection().job_id,state().run?.jobs?.[selection().job_id]?.attempt_id].join('/');
  function listDraft(){const key=resultKey(),saved=state().run?.jobs?.[selection().job_id] || {};if(!listDrafts.has(key))listDrafts.set(key,{items:workListItems(saved.result || {}),attempt_id:saved.attempt_id,revision:state().run?.revision,result_revision:saved.result_revision});return listDrafts.get(key);}
  function reviewDraft(){const saved=state().run?.jobs?.[selection().job_id] || {},source={text:saved.review_draft?.text ?? saved.result?.text ?? saved.result?.draft ?? saved.result?.summary ?? ''};return {...reviewDrafts.read(resultKey(),source,saved.review_draft?.revision || 0),key:resultKey(),attempt_id:saved.attempt_id,result_revision:saved.result_revision};}
  function captureResults(){
    const list=host?.querySelector('.ew-list-confirm');if(list){const draft=listDraft();for(const field of list.querySelectorAll('[data-list-include]')){const item=draft.items.find(item=>item.id===field.dataset.itemId);if(item&&!field.disabled)item.selected=field.checked;}}
    const text=host?.querySelector('#ees-review-text');if(text&&!text.readOnly){const previous=reviewDraft();if(text.value!==previous.inputs.text)reviewDrafts.edit(resultKey(),{text:text.value},previous.revision,previous.base || previous.inputs);}
  }
  function capture(){if(!host?.isConnected||snapshot.native_shell||!snapshot.state)return;captureResults();const model=$('#ees-work-execution-model',host);if(model&&(state().operations?.models || []).length>1)modelChoices.set(modelKey(),model.value);const form=$('#ees-work-inputs',host);if(form&&currentDraftKey){try{const source=form.dataset.settings==='true'?state().settings?.values || {}:state().run?.inputs || {};const previous=drafts.read(currentDraftKey,source,Number(form.dataset.revision)),values={...previous.inputs};for(const field of form.querySelectorAll('[data-work-input]'))if(!field.disabled)delete values[field.name];Object.assign(values,workReadInputs(form));if(!workValuesEqual(values,previous.inputs))drafts.edit(currentDraftKey,values,Number(form.dataset.revision),source);}catch(_){}}if(host)positions.set(lastKey,{scroll:$('#ees-work-content',host)?.scrollTop || 0,expanded:[...host.querySelectorAll('details[open]')].map(el=>el.dataset.key).filter(Boolean)});}
  function ensure(){
    // The source shell owns layout and supplies the only legacy content slot.
    // Never locate, move, hide or replace Native-owned elements.
    const supplied=window.__eesSourceShellV1?.hosts?.()?.panel;
    if(!supplied)return false;
    if(host!==supplied){capture();host=supplied;}
    return true;
  }
  function publish(){
    const node=job();
    window.__eesSourceShellV1?.publish?.({...snapshot,
      context_title:snapshot.native_return_pending?'대화':snapshot.procedure_start?'새 업무 절차 만들기':node?.name || workStageTarget(state(),selection())?.name || state().workflow?.name || '대화'});
  }
  function runOverview(){
    const data=state(),run=data.run,def=definition(),nodes=Object.values(def.nodes || {}),jobs=nodes.filter(node=>node.type==='j'),root=nodes.find(node=>node.type==='p'&&!node.parent),groups=nodes.filter(node=>node.type==='t');
    if(groups.length&&!['start','run_details'].includes(selection().tab))return workOperationOverviewHTML(data,selection());
    if(!run&&(def.mode || data.workflow?.mode || def.execution_mode || data.workflow?.execution_mode || 'on_demand')==='on_demand')return workAdhocStartHTML(data,selection(),def);
    const automatic=scope=>jobs.filter(node=>['tool','ai'].includes(node.mode)&&node.result_block!=='change_request'&&run?.jobs?.[node.id]?.can_execute!==false&&workUI.lineage(node.id,def).some(parent=>parent.id===scope.id));
    const scopeButton=scope=>scope&&!finished(run)&&run?.can_write!==false&&automatic(scope).length?button(scope.type==='p'?'절차 실행':'단계 실행','execute_scope',`data-node-id="${esc(scope.id)}" data-mutation class="ew-secondary"`):'';
    const actor=node=>({human:['35b2e','사람'],tool:['a28e3','도구'],ai:['b22ad','AI 초안']}[node.mode || 'human']);
    const jobButton=node=>{const saved=run?.jobs?.[node.id] || {},person=actor(node);return `<button type="button" class="ew-phase-job" data-action="job" data-job-id="${esc(node.id)}">${workStatusHTML(saved.status || 'unstarted',node.name)}<span class="ew-job-actor" title="${person[1]}">${icon(person[0],person[1])}</span><small>${esc(workReasonText(saved.reason,data.operations?.shared_tool_messages) || (saved.deadline?.at?'기한 '+workUI.time(saved.deadline.at):saved.deadline?.calendar_status==='unknown'?'일정 기준 확인 필요':'') || (saved.decision_summary?.confirmed?`${saved.decision_summary.confirmed}건 사람 확인`:''))}</small>${icon('69549')}</button>`;};
    const steps=groups.length?groups.map((stage,index)=>{const children=jobs.filter(node=>workUI.lineage(node.id,def).some(parent=>parent.id===stage.id)),states=children.map(node=>run?.jobs?.[node.id] || {}),resolved=children.length&&states.every(item=>['completed','excluded'].includes(item.status)||item.partial_confirmed),stageStatus=resolved?(states.some(item=>item.partial_confirmed)?'partial':'completed'):states.some(item=>!['unstarted','pending','excluded',undefined].includes(item.status))?'in_progress':'waiting';return `<section class="ew-phase-overview"><header class="ew-phase-heading"><span>${index+1}</span><h3>${button(stage.name,'stage_open',`data-node-id="${esc(stage.id)}" class="ew-text"`)}</h3>${run?.cycle?.stage_deadlines?.[stage.id]?`<small>${esc(run.cycle.stage_deadlines[stage.id].start)}${run.cycle.stage_deadlines[stage.id].end!==run.cycle.stage_deadlines[stage.id].start?' ~ '+esc(run.cycle.stage_deadlines[stage.id].end):''}</small>`:''}${workStatusHTML(stageStatus)}</header><div class="ew-run-steps">${children.map(jobButton).join('')}</div>${scopeButton(stage)}</section>`;}).join('')+(jobs.some(node=>node.parent===root?.id)?`<div class="ew-run-steps">${jobs.filter(node=>node.parent===root.id).map(jobButton).join('')}</div>`:''):`<div class="ew-run-steps">${jobs.map(jobButton).join('')}</div>`;
    const next=jobs.find(node=>['waiting_input','awaiting_input','waiting_confirmation','awaiting_confirmation','review_required','ready'].includes(run?.jobs?.[node.id]?.status));
    const scopes=(data.operations?.scope_runs || []).filter(item=>item.run_id===run?.id),scopeStatus=scopes.length?`<section class="ew-scope-status"><h3>절차·단계 실행</h3>${scopes.map(item=>`<p>${workStatusHTML(item.status)} · ${esc(def.nodes?.[item.node_id]?.name || item.node_id)}</p><small>${esc(workReasonText(item.reason,data.operations?.shared_tool_messages))}${item.current_job_id?' · '+esc(def.nodes?.[item.current_job_id]?.name || item.current_job_id):''}</small>`).join('')}</section>`:'';
    const models=jobs.some(node=>node.mode==='ai')?executionModels():'';
    const progress=run?.progress || {},confirmedPartial=progress.confirmed_partial ?? Object.values(run?.jobs || {}).filter(item=>item.partial_confirmed).length,excluded=progress.excluded ?? Object.values(run?.jobs || {}).filter(item=>item.status==='excluded').length,remaining=progress.remaining ?? Math.max(0,(progress.total ?? jobs.length-excluded)-(progress.completed || 0)-confirmedPartial);
    return `${workCycleBarHTML(run,def)}<header class="ew-work-heading"><h2>${esc(run?(run.cycle?.name || run.name || def.name || '진행 건'):'진행 건 시작')}</h2>${run?`<p>${badge(run.status)} · 게시 v${esc(run.version || run.published_version)}${finished(run)?' · 읽기 전용':''}</p><p>단계 ${groups.length} · 작업 ${jobs.length} · 완료 ${progress.completed || 0}${confirmedPartial?' · 부분 결과 확정 '+confirmedPartial:''} · 남은 작업 ${remaining}</p>`:'<p>게시한 절차 버전으로 새 진행 건을 시작합니다.</p>'}</header>${!run?`<div class="ew-empty">${data.workflow?.published_version?button('진행 건 시작','start_run','class="ew-primary"'):'게시된 버전이 없습니다. 워크스페이스에서 검사하고 게시해 주세요.'}</div>`:`${(run.cycle?.warnings || []).map(warning=>workNoticeHTML('일정 확인 필요',warning.message || warning.code)).join('')}${run.cycle?.holidays_checked===false?'<p class="ew-muted">공휴일 달력 미연결 · 공휴일 여부는 확인하지 않았으며 날짜를 자동 이동하지 않았습니다.</p>':''}${steps}${finished(run)?`${run.closure_summary?.partial_jobs?.length?workNoticeHTML('부분 결과로 확정한 작업',run.closure_summary.partial_jobs.map(item=>item.name || item.job_id).join(' · ')):''}<section><h3>당시 실행 기록</h3>${workHistoryHTML(run,'',data.settings?.values)}<button type="button" data-action="ask_record" class="ew-text">${icon('1c98e')} 최근 기록에 대해 묻기</button></section>`:`<p class="ew-muted">작업을 누르면 이 패널에서 작업을 엽니다. 작업 이름 옆 아이콘은 사람 · 도구 · AI 초안을 구분합니다.</p>${models}${scopeStatus}${next?`<footer class="ew-next-action"><small>다음 할 일 · ${esc(next.name)}</small>${button(next.name+' 열기','job',`data-job-id="${esc(next.id)}" class="ew-primary"`)}</footer>`:''}${root?`<div class="ew-scope-execution">${scopeButton(root)}<small>저장한 입력으로 실행 가능한 도구·AI 작업을 진행합니다. 사람 확인과 EES 변경 요청은 자동 확정하지 않습니다.</small></div>`:''}`}<footer class="ew-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}${!finished(run)&&run.can_write!==false?button('진행 건 종료','close_run')+button('진행 건 취소','cancel_run'):''}</footer>`}`;
  }
  function jobPanel(){const data=state(),s=selection(),node=job(),run=data.run,saved=run?.jobs?.[node.id] || {},readonly=finished(run)||run?.can_write===false,fields=node.result_block==='change_request'?(workRequestFields(node,data.operations?.tools) || []):node.inputs || [],settings=s.tab==='settings',source=settings?data.settings?.values || {}:run?.inputs || {},revision=settings?data.settings?.revision || 0:run?.revision || 0;
    currentDraftKey=inputKey();const draft=drafts.read(currentDraftKey,source,revision),visibleFields=fields.filter(field=>(['workflow','factory'].includes(field.scope))===settings);
    const header=`${workCycleBarHTML(run,definition())}<button class="ew-text" type="button" data-action="overview">← 회차 개요</button><header class="ew-work-heading"><h2>${esc(node.name)}</h2>${workStatusHTML(saved.status || 'unstarted')}<p>${esc(node.instructions || '')}</p>${workAssignmentHTML(node,saved,data.people)}${saved.partial_prerequisites?.length?workNoticeHTML('부분 결과에서 시작함',saved.partial_prerequisites.map(source=>source.name || source.job_id).join(' · ')):''}${saved.claim_actor===data.capabilities?.actor_id&&!readonly&&saved.status!=='running'?button('맡기 해제','release_task','class="ew-text"'):''}</header><nav class="ew-tabs" aria-label="작업 보기">${[['current','현재 상태'],['history','실행 기록'],['settings','업무 설정']].map(([tab,label])=>button(label,'tab',`data-tab="${tab}" aria-pressed="${s.tab===tab}"`)).join('')}</nav>`;
    if(s.tab==='history')return header+`<div class="ew-export-actions">${button('기록 JSON 내보내기','export_json')}${button('기록 텍스트 내보내기','export_text')}</div>`+workHistoryHTML(run,node.id,data.settings?.values)+`<button type="button" data-action="ask_record" data-job-id="${esc(node.id)}" class="ew-text">${icon('1c98e')} 최근 기록에 대해 묻기</button>`;
    const shared=(data.operations?.shared_tools || []).find(item=>item.id===node.shared_tool_id),pin=(run?.shared_tools || []).find(item=>item.id===node.shared_tool_id),access=data.operations?.shared_tool_access?.[node.id] || {},messages=data.operations?.shared_tool_messages || {},changed=!!(shared&&pin&&shared.version!==pin.version),groupDenied=!!node.shared_tool_id&&(access.can_use===false||shared?.can_use===false),sharedBlocked=!!node.shared_tool_id&&(!shared||groupDenied||shared.state!=='available'||changed);
    const running=Object.values(run?.jobs || {}).some(item=>item.status==='running'),canAccept=changed&&shared.state==='available'&&!groupDenied&&!readonly&&!running&&access.can_accept_version===true;
    const sharedMessage=!shared?data.operations?.shared_tools_notice || workReasonText('shared_tool_review_required',messages):shared.state==='disabled'?workReasonText('shared_tool_disabled',messages):shared.state!=='available'?(shared.unavailable_message||workReasonText('shared_tool_review_required',messages)):changed?workReasonText('shared_tool_version_changed',messages,{pinned:pin.version,current:shared.version}):'개인 PAT(기존 방식)';
    const sharedNotice=node.shared_tool_id?`<section class="ew-shared-runtime"><h3>${esc(shared?.name || '공용 도구')} · 회차 v${esc(pin?.version || '미확인')}</h3>${groupDenied?`<span class="ew-badge">보기 전용</span><p>이 도구로 실행할 수 있는 사람 · ${esc((access.group_names || []).join(' · ') || '그룹 확인 필요')}</p><p>지금 담당 · ${esc(access.assignee_name || '미지정')}</p>`:`<p>${esc(sharedMessage)}</p>`}${canAccept?button('v'+shared.version+' 버전으로 계속하기','shared_accept_version',`data-shared-id="${esc(shared.id)}" data-version="${shared.version}" data-mutation`):''}</section>`:'';
    const modelControls=node.mode==='ai'?executionModels():'';
    const proposal=!settings?data.input_proposal:null,applied=!settings?data.input_proposal_applied:null;
    const canEditInputs=!readonly&&!groupDenied&&(settings?saved.can_manage_settings!==false:saved.can_execute!==false),appliedUnsaved=Boolean(applied&&draft.dirty);
    const inputs=visibleFields.length?`<section><h3>${settings?'업무 설정':'이번 진행 건 입력'} <small>${settings?'다음 실행에도 계속 사용':'이번 실행에 사용'}</small>${proposal?'<span class="ew-input-proposal-status">업무 도우미 제안 · 반영 전</span>':appliedUnsaved?'<span class="ew-input-proposal-applied" role="status">저장 전</span>':''}</h3><form id="ees-work-inputs" data-settings="${settings}" data-revision="${draft.revision}">${visibleFields.map(field=>workInputHTML(field,field.constant?field.value:draft.inputs[field.id],{disabled:field.constant||readonly||groupDenied||(settings?saved.can_manage_settings===false:saved.can_execute===false),prefix:settings?'settings':'run',people:data.people || [],lookup:data.input_options?.[field.id],proposal:proposal&&Object.hasOwn(proposal.values,field.id)?{value:proposal.values[field.id]}:null,applied:Boolean(applied&&Object.hasOwn(applied.values,field.id)&&workValuesEqual(applied.values[field.id],draft.inputs[field.id]))})).join('')}${draft.conflict?'<p class="ew-warning" role="alert">다른 사람이 값을 변경했습니다. 작성 중인 값은 보존했습니다. 최신 값과 비교해 다시 입력해 주세요.</p>'+button('최신 값으로 돌아가기','discard_inputs'):''}${canEditInputs&&!proposal&&!appliedUnsaved?button(settings?'설정 저장':'입력 저장','save_inputs',`data-mutation class="ew-secondary"${draft.conflict?' disabled':''}`):''}</form></section>`:'';
    const queryAttempt=workListSourceAttempt(run,saved.attempt_id),querySummary=node.result_block==='list_confirm'&&!settings&&queryAttempt&&!queryAttempt.evidence_access?`<section class="ew-query-summary"><header><h4>${icon('f1e53')} 조회 조건</h4><small>${esc(workUI.time(queryAttempt.created_at))} 조회</small>${button('업무 설정 보기','tab','data-tab="settings" class="ew-text"')}</header><p>${Object.entries(queryAttempt.inputs || {}).map(([key,value])=>`${esc(fields.find(field=>field.id===key)?.name || key)} · ${esc(typeof value==='object'?JSON.stringify(value):value)}`).join(' · ') || '이 실행에 선언된 조회 입력 없음'}</p></section>`:'';
    const proposalHTML=proposal?(proposal.warnings || []).map(warning=>`<p class="ew-warning" role="status">${esc(warning)}</p>`).join(''):'';
    const requestReason=node.result_block==='change_request'&&!settings?`<label class="ew-input-row"><span>요청 사유</span><textarea id="ees-request-reason" rows="2" maxlength="4000"${readonly||saved.can_request===false?' readonly':''}>${esc(s.request_reasons?.[run.id+'/'+node.id] || saved.request?.request_reason || '')}</textarea></label>${workRequestFields(node,data.operations?.tools)===null?workNoticeHTML('EES 입력 정의 확인 필요','도구의 입력 정의를 확인한 뒤 요청할 수 있습니다.'):''}`:'';
    return header+sharedNotice+inputs+requestReason+proposalHTML+modelControls+querySummary+(saved.partial_prerequisites?.length?'':workPartialSourceHTML((run.attempts || []).find(attempt=>attempt.id===saved.attempt_id),run))+(settings?`<p class="ew-muted">개인 PAT와 비밀정보는 Native 개인 설정에서 관리합니다. 여기에 입력하지 마세요.</p>`:workResultHTML({...node,shared_function:shared?.function || pin?.reference?.function,judgments:node.judgments || definition().judgments,execution_actor:data.operations?.tools?.find(tool=>tool.id===node.tool_contract_id)?.kind==='direct'?'EES Work':'EES'},saved,{readOnly:readonly||groupDenied||saved.can_decide===false,messages,target:shared?.target,actorId:data.capabilities?.actor_id,verdictDraft:s.verdict_drafts?.[run.id+'/'+node.id+'/'+saved.attempt_id] || {},sourceCount:Array.isArray(queryAttempt?.result?.items)?queryAttempt.result.items.filter(item=>item.source?.kind!=='human_added').length:null,listDraft:node.result_block==='list_confirm'?listDraft():null,reviewDraft:node.result_block==='ai_review'?reviewDraft():null})+(proposal?workInputProposalBar(proposal,node,{disabled:!canEditInputs}):appliedUnsaved&&canEditInputs?`<footer class="ew-job-actions ew-input-applied-bar"><p>${node.result_block==='change_request'?'저장해야 요청할 수 있습니다':node.mode==='human'||node.result_block==='human_confirm'?'저장해야 확인할 수 있습니다':'저장해야 실행할 수 있습니다'}</p>${button('최신 값으로 돌아가기','discard_inputs','class="ew-secondary"')}${button('입력 저장','save_inputs',`data-mutation class="ew-primary"${draft.conflict?' disabled data-own-disabled="true"':''}`)}</footer>`:`<footer class="ew-job-actions">${(saved.block_reason || saved.reason)?`<p class="ew-warning">${esc((saved.block_reason || saved.reason)==='delivery_unconfigured'?'본문 검토는 저장했습니다. 실제 송부와 결과 확인 전에는 이 작업을 완료하지 않습니다.':workReasonText(saved.block_reason || saved.reason,data.operations?.shared_tool_messages,{pinned:pin?.version,current:shared?.version}))}</p>`:''}${groupDenied?'':readonly||saved.can_execute===false?`<p>${esc(finished(run)?'종료된 진행 건 · 당시 기록을 조회하고 있습니다.':({assignee_required:'보기 전용 · 배정된 담당자나 그룹이 처리할 수 있습니다.',task_claimed:'보기 전용 · 다른 담당자가 처리 중입니다.',scope_forbidden:'보기 전용 · 업무 참여 권한이 필요합니다.',run_closed:'종료된 진행 건 · 당시 기록을 조회하고 있습니다.'}[saved.permission_reason || run.permission_reason] || '보기 전용 · 현재 계정은 이 작업을 수행할 수 없습니다.'))}</p>`:node.result_block==='change_request'?(saved.can_request===false?'<p>보기 전용 · EES 요청 권한이 있는 담당자가 처리할 수 있습니다.</p>':button('요청 내용 확인…','request_intent',`data-mutation class="ew-primary"${workRequestFields(node,data.operations?.tools)===null?' disabled data-own-disabled="true"':''}`)):node.mode==='human'?button('확인 완료','confirm','data-mutation class="ew-primary"'):button(saved.evidence_access==='requires_current_source_access'&&node.mode==='tool'?'현재 권한으로 다시 조회':['failed','unknown'].includes(saved.status)&&node.mode==='tool'?'다시 조회':saved.attempt_id?'다시 실행':'지금 실행','execute',`data-mutation class="ew-primary"${sharedBlocked?' disabled data-own-disabled="true"':''}`)+(saved.can_decide!==false&&!saved.decisions?.job&&node.human_confirmation!==false&&!['list_confirm','item_verdict','checklist'].includes(node.result_block)?button(node.completion?.kind==='delivery'?'본문 검토 확정':'판정 확정','confirm','data-mutation class="ew-secondary"'):'')}</footer>`));
  }
  function panel(){if(!host)return;const s=selection(),data=state(),key=[data.capabilities?.actor_id,s.system_id,s.factory_id,s.mode,s.tab,s.run_id,s.workflow_id,s.job_id].join('/'),sameTarget=lastKey===key;lastKey=key;host.dataset.eesMode=s.mode || 'work';
    const paint=html=>{if(sameTarget)workPatchContent(host,html);else host.innerHTML=html;};
    const overview=!snapshot.target_loading&&!snapshot.scope_loading&&snapshot.state&&s.mode!=='author'&&s.workflow_id&&!s.job_id&&s.tab==='overview'&&!workStageTarget(data,s)&&Object.values(definition().nodes || {}).some(node=>node.type==='t');
    const stage=!snapshot.target_loading&&!snapshot.scope_loading&&!snapshot.evidence_unavailable&&snapshot.state?workStageTarget(data,s):null,stageScreen=stage?workStageHTML(data,s,stage,{modelControls:Object.values(data.run?.definition?.nodes || {}).some(node=>node.type==='j'&&node.mode==='ai'&&workUI.lineage(node.id,data.run.definition).some(parent=>parent.id===stage.id))?executionModels():''}):null;
    host.classList?.toggle('ew-vd',Boolean(stageScreen||overview));
    const title=s.mode==='author'?'워크스페이스':s.tab==='my_work'?'내 업무':s.tab==='records'?'실행 기록':'업무';
    const top=stageScreen?.header || (overview?`<header class="ew-panel-header ew-operation-nav"><strong>업무</strong><span></span><button type="button" class="ew-icon-button" aria-label="업무 패널 닫기" data-action="close_panel">${icon('7bb4a')}</button></header>`:null) || `<header class="ew-panel-header"><strong>${title}</strong><span>${esc(snapshot.native_return_pending?'':s.mode==='author'?data.workflow?.name || '':definition().name || data.workflow?.name || '')}</span>${button('닫기','close_panel','aria-label="업무 패널 닫기" class="ew-icon-button"')}</header>`;
    if(snapshot.evidence_unavailable){paint(top+`<div class="ew-scroll"><div class="ew-error" role="alert"><p>${esc(snapshot.error || '기록을 다시 조회해 주세요.')}</p>${button('다시 조회','refresh')}</div></div>`);setBusy(snapshot.busy);return;}
    if(!snapshot.target_loading&&!(snapshot.scope_loading&&snapshot.error)&&snapshot.state&&s.mode==='author'&&s.tab!=='workspace_admin'){if(!workCanCreate(data.capabilities)){paint(top+'<div class="ew-scroll"><p class="ew-empty">'+(workNativeTargets.some(target=>workNativeAllowed(data.capabilities,target.id))?'왼쪽 메뉴에서 사용할 화면을 여세요.':'현재 계정으로 EES Workflow에서 열 수 있는 항목이 없습니다.')+'</p></div>');return;}if(!$('#ees-work-authoring-panel',host))paint('<div id="ees-work-authoring-panel" class="ew-scroll"></div>');return;}
    let body='';currentDraftKey='';
    if(snapshot.error&&!snapshot.state)body=`<div class="ew-error" role="alert"><p>${esc(snapshot.error)}</p>${button('다시 조회','refresh')}</div>`;
    else if(snapshot.scope_loading&&snapshot.state)body='<p role="status" class="ew-empty" data-ees-scope-loading="panel">'+(snapshot.error?'목록을 받지 못했습니다.':'받는 중')+'</p>';
    else if(!snapshot.state||snapshot.target_loading)body='<p role="status" class="ew-empty" data-ees-target-loading>업무 정보를 불러오는 중입니다.</p>';
    else if(s.tab==='historical_reference')body=workHistoricalReferenceHTML(data.run,s.historical_reference,data.workflow,data.settings?.values);
    else if(s.tab==='workspace_admin')body=workAdminHTML(data);
    else if(s.tab==='my_work')body=workMyWorkHTML(data.my_work || [],data.operations);
    else if(s.tab==='records')body=workRunRecordsHTML(data.runs || [],s.records_workflow || '',data.workflow?.name)+(s.records_workflow?'':workLegacyHTML(data.legacy));
    else if(!s.workflow_id)body='<div class="ew-empty"><h3>업무 절차를 선택해 주세요</h3><p>왼쪽에서 업무를 찾거나 워크스페이스에서 새 절차를 작성할 수 있습니다.</p></div>';
    else if(stageScreen)body=stageScreen.body;
    else if(job()&&data.run)body=jobPanel();else if(job())body=`<button type="button" class="ew-text" data-action="stage_return">← 단계로 돌아가기</button><header class="ew-work-heading"><h2>${esc(job().name)}</h2><p>${esc(job().instructions || '')}</p></header><section><h3>확인 기준</h3><p>${esc(job().completion?.rule || '등록된 확인 기준이 없습니다.')}</p></section>${(job().inputs || []).length?`<section><h3>필요한 입력</h3>${(job().inputs || []).map(field=>`<p>${esc(field.name || field.id)}${field.required?' · 필수':''}</p>`).join('')}</section>`:''}`;else body=(['start','run_details'].includes(s.tab)?`<button type="button" class="ew-text" data-action="stage_return">← 단계로 돌아가기</button>`:'')+runOverview();
    paint(top+`<div id="ees-work-content" class="ew-scroll${stageScreen||overview?' ew-vd-padding-reset':''}">${snapshot.error&&snapshot.state?`<div class="ew-error" role="alert">${esc(snapshot.error)}${snapshot.error.startsWith('작성한 선택의 자동 저장 실패')?button('자동 저장 다시 시도','retry_private_save'):''}</div>`:''}${data.operations?.error?`<p class="ew-warning" role="alert">실행·예약 정보를 조회하지 못했습니다. ${esc(data.operations.error)}</p>`:''}${body}</div>${stageScreen?.menu || ''}`);
    const footer=host.querySelector('#ees-work-content>.ew-job-actions, #ees-work-content>.ew-next-action');if(footer)host.append(footer);
    workRestorePanelPosition(host,positions.get(key));setBusy(snapshot.busy);
  }
  function setBusy(value){host?.querySelectorAll('[data-mutation]').forEach(el=>{if(el.dataset.ownDisabled!=='true')el.disabled=Boolean(value)||el.closest('form')?.querySelector('.ew-warning')!==null&&Boolean(el.closest('form'));});host?.setAttribute('aria-busy',String(Boolean(value)));}
  function focusSnapshot(){
    const active=document.activeElement;if(!active||!host?.contains(active))return null;
    const attributes=['id','name','data-action','data-job-id','data-workflow-id','data-tab','data-mode','data-item-id','data-item-verdict','data-item-confirm','data-field-id','data-ees-panel-resize','data-judgment-id','data-verdict','data-stage-attempt','data-tool-key'];
    return {attributes:attributes.filter(name=>active.hasAttribute?.(name)).map(name=>[name,active.getAttribute(name)]),start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection};
  }
  function restoreFocus(saved){
    if(!saved?.attributes.length||$('#ees-work-dialog'))return;
    for(const root of [host]){const target=[...(root?.querySelectorAll('button,input,select,textarea,a,summary,[data-ees-panel-resize]') || [])].find(item=>saved.attributes.every(([name,value])=>item.getAttribute(name)===value));if(!target||target.disabled)continue;target.focus({preventScroll:true});if(typeof saved.start==='number'&&typeof target.setSelectionRange==='function'){try{target.setSelectionRange(saved.start,saved.end,saved.direction);}catch(_){}}return;}
  }
  function refreshResults(){const focus=focusSnapshot();capture();panel();restoreFocus(focus);}
  function render(value){const focus=focusSnapshot();capture();snapshot=value;publish();if(!ensure())return false;if(!snapshot.native_shell)panel();restoreFocus(focus);return true;}
  function sync(value){snapshot=value;publish();if(!ensure())return false;if(!snapshot.native_shell&&!host.firstChild)panel();return true;}
  function readInputs({runInputs=false}={}){capture();const settings=!runInputs&&selection().tab==='settings',key=inputKey(runInputs?'current':selection().tab);return {...drafts.read(key,settings?state().settings?.values || {}:state().run?.inputs || {},settings?state().settings?.revision || 0:state().run?.revision || 0),key,settings};}
  function applyInputValues(values){capture();const source=state().run?.inputs || {},revision=state().run?.revision || 0,key=inputKey('current'),existing=drafts.read(key,source,revision);drafts.edit(key,{...existing.inputs,...values},revision,source);panel();}
  function clearInputs(key,serial,revision,values){drafts.acknowledge(key,serial,revision,values);}

  function suspend(){workUI.closeDialog();capture();}
  function reset(){workUI.closeDialog();drafts.clear();reviewDrafts.clear();listDrafts.clear();positions.clear();modelChoices.clear();if(host)host.replaceChildren();host=null;snapshot={state:null,selection:{}};publish();}
  return Object.freeze({render,sync,reset,suspend,setBusy,readList:()=>{capture();return workUI.clone(listDraft());},addListItem:item=>{capture();const draft=listDraft();if(draft.items.some(old=>old.id===item.id))throw new Error('이미 목록에 있는 항목입니다. 포함 여부를 확인해 주세요.');draft.items.push({...item,manual:true,selected:true});refreshResults();},readReview:()=>{capture();return reviewDraft();},clearReview:(key,serial,revision,text)=>reviewDrafts.acknowledge(key,serial,revision,{text}),refreshResults,readInputs,clearInputs,applyInputValues,discardInputs:()=>{drafts.discard(inputKey());panel();},authoringHost:()=>$('#ees-work-authoring-panel',host),hasPendingInputs:()=>drafts.hasDirty([state().capabilities?.actor_id,selection().system_id,selection().factory_id,state().run?.id].join('/')+'/'),capture,handleEvent:()=>({handled:false})});
}
