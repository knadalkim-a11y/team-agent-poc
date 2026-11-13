// The workspace owns storage and authorization. This controller owns the current editor only.
function createWorkApiCatalog({catalog, command, changed, paint, legacyAvailable, returnToJob, contextChanged, focus, newId}) {
  const {esc}=workUI;
  const clone=value=>JSON.parse(JSON.stringify(value));
  const blank=()=>({name:'',purpose:'',service_id:'',method:'GET',url:'',inputs:[],result_path:'',fields:[]});
  const screenNames={list:'API 명세 목록',detail:'API 상세',create:'API 명세 등록',edit:'API 명세 편집',services:'서비스 관리',import:'서비스 명세 URL',impact:'명세 변경 영향',test:'시험 실행'};
  let screen='list', id='', draft=null, original='', serviceName='', query='', filterGroups=new Set();
  let error='', status='', busy=false, legacy=false, advanced=false, missing=false, leave=false;
  let generation=0, serviceEdit=null, importing=null, impact=null, trial=null, example='', fromJob=false;
  let receiptKey='', receiptId='', detailUses=null, detailVersion=0;
  const current=()=>catalog()||{services:[],apis:[],can_manage:false};
  const all=()=>current().apis||[], services=()=>current().services||[];
  const api=()=>all().find(item=>item.id===id);
  const admin=()=>current().can_manage===true;
  const serviceLabel=value=>services().find(item=>item.id===value)?.name||'미분류';
  const snap=()=>JSON.stringify([draft,serviceName,example]);
  const dirty=()=>draft&&snap()!==original;
  const btn=(label,action,kind='',attrs='')=>`<button type="button" data-api-action="${action}" class="ew-api-btn ${kind}" ${attrs}>${esc(label)}</button>`;
  const back=(label,action='cancel')=>btn('‹  '+label,action,'link back');
  const opts=(choices,selected)=>choices.map(([k,v])=>`<option value="${esc(k)}" ${k===selected?'selected':''}>${esc(v)}</option>`).join('');
  const field=(name,label,value,attrs='')=>`<label><span>${esc(label)}</span><input name="api-${name}" value="${esc(value??'')}" ${attrs}></label>`;
  const select=(name,label,pairs,value,attrs='')=>`<label><span>${esc(label)}</span><select name="api-${name}" ${attrs}>${opts(pairs,value)}</select></label>`;
  const json=value=>value===undefined?'':JSON.stringify(value,null,2);
  const methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'];
  const types=['string','integer','number','boolean','array','object'];
  const pairs=list=>list.map(s=>[s,s]);
  const addr=value=>{try{const url=new URL(value);return decodeURI(url.pathname+url.search);}catch{return value||'';}};
  const serviceChoices=()=>[['','미분류'],...services().map(x=>[x.id,x.name]),['__new__','새 서비스 추가…']];
  function announce(){contextChanged?.(context());}
  function context(){
    const record=draft||(['detail','test','impact','import'].includes(screen)?api():null);
    let path='';
    try{path=new URL(record?.url).pathname;}catch{}
    return {screen:screenNames[screen],draftName:record?.name||'',api_id:record?.id||'',method:record?.method||'',
      service:record?(record.service_id==='__new__'?serviceName:serviceLabel(record.service_id)):'',purpose:record?.purpose||'',path,
      inputs:(record?.inputs||[]).slice(0,20).map(p=>p.label||p.name),fields:(record?.fields||[]).slice(0,20).map(p=>p.label||p.path)};
  }
  function go(next,focusSelector){
    screen=next;error='';leave=false;generation++;busy=false;paint();announce();
    if(focusSelector)focus?.(focusSelector);
  }
  function reset(){
    generation++;screen='list';id='';draft=null;original='';serviceName='';query='';filterGroups=new Set();
    error='';status='';busy=false;advanced=false;missing=false;leave=false;legacy=false;fromJob=false;
    serviceEdit=null;importing=null;impact=null;trial=null;example='';receiptKey='';receiptId='';detailUses=null;detailVersion=0;
  }
  function start(record=null,job=false){
    legacy=false;fromJob=job;draft=record?clone(record):blank();id=record?.id||'';
    serviceName='';example=draft.example==null?'':json(draft.example);advanced=false;missing=false;original=snap();importing=null;impact=null;status='';
    go(record?'edit':'create','[data-api-catalog] h2');
  }
  async function exitEditor(force=false){
    if(!force&&(dirty()||importing?.source_text||importing?.source_url)){leave=true;paint();focus?.('[data-api-action=stay]');return;}
    const edit=Boolean(draft?.id),job=fromJob;draft=null;original='';serviceName='';importing=null;impact=null;fromJob=false;go(edit?'detail':'list');
    if(job)await returnToJob(null);
  }
  function listHTML(){
    const needle=query.trim().toLocaleLowerCase(), records=all();
    const groups=[...services().map(s=>[s.id,s.name]),['','미분류']];
    const parts=groups.map(([sid,name])=>{
      const members=records.filter(x=>(x.service_id||'')===sid).sort((a,b)=>addr(a.url).localeCompare(addr(b.url))||methods.indexOf(a.method)-methods.indexOf(b.method)||a.name.localeCompare(b.name));
      const rows=members.filter(x=>[x.name,x.purpose,x.url,name].join(' ').toLocaleLowerCase().includes(needle));
      if(!rows.length)return '';
      return `<details class="ew-api-group" data-group="${esc(sid)}" ${filterGroups.has(sid)?'':'open'}><summary><span>${esc(name)}</span><span>${rows.length}개</span></summary>${rows.map(x=>`<button type="button" class="ew-api-row" data-method="${esc(x.method)}" data-api-action="open" data-id="${esc(x.id)}"><span class="ew-api-line"><b class="ew-api-method">${esc(x.method)}</b><span>${esc(addr(x.url))}</span><strong>${esc(x.name)}</strong><i aria-hidden="true">›</i></span><span class="ew-api-description">${esc(x.purpose)}</span></button>`).join('')}</details>`;
    }).join('');
    return `<div class="ew-api-head"><h2>API 명세 ${records.length}개</h2><div>${admin()?btn('서비스 관리','services')+btn('API 명세 등록','create','primary'):''}</div></div>
      ${field('search','API 찾기',query,'type="search" placeholder="이름, 용도, 서비스 또는 주소로 검색"')}
      <div class="ew-api-groups" aria-label="서비스별 API 명세">${parts||`<p class="ew-api-empty">${needle?'검색 결과가 없습니다.':'등록된 API 명세가 없습니다.'}</p>`}</div>
      ${legacyAvailable()?btn('기존 도구 관리','legacy','link ew-api-legacy'):''}`;
  }
  function gridCell(list,i,key,value,label,choices){
    const attrs=`name="api-${list}-${i}-${key}" data-map="${list}" data-index="${i}" data-key="${key}" aria-label="${esc(label)} ${i+1}"`;
    return `<label><span>${esc(label)}</span>${choices?`<select ${attrs}>${opts(choices,String(value??''))}</select>`:`<input ${attrs} value="${esc(value??'')}">`}</label>`;
  }
  function mappingHTML(){
    const rows=(draft.inputs||[]).map((p,i)=>`<div class="ew-api-map">${gridCell('inputs',i,'name',p.name,'파라미터 이름')}${gridCell('inputs',i,'in',p.in,'전송 위치',pairs(['path','query','header','body']))}${gridCell('inputs',i,'type',p.type,'자료형',pairs(types))}${gridCell('inputs',i,'required',p.required!==false,'필수 여부',[['true','필수'],['false','선택']])}${gridCell('inputs',i,'label',p.label,'업무 입력 이름')}${btn('삭제','remove-row','link',`data-list="inputs" data-index="${i}" aria-label="입력 ${i+1} 삭제"`)}</div>`).join('');
    const fields=(draft.fields||[]).map((p,i)=>`<div class="ew-api-map">${gridCell('fields',i,'path',p.path,'응답 필드')}${gridCell('fields',i,'label',p.label,'표시 이름')}${gridCell('fields',i,'type',p.type||'string','자료형',pairs(types))}${btn('삭제','remove-row','link',`data-list="fields" data-index="${i}" aria-label="결과 ${i+1} 삭제"`)}</div>`).join('');
    return `<details class="ew-api-advanced" data-api-advanced ${advanced?'open':''}><summary>입력·결과 설정</summary>
      <div class="ew-api-subhead"><h3>요청 파라미터</h3>${btn('입력 추가','add-input','link')}</div>${rows}
      <div class="ew-api-subhead"><h3>결과에 표시할 항목</h3>${btn('결과 추가','add-field','link')}</div>
      ${field('result_path','응답에서 결과가 있는 위치',draft.result_path,'placeholder="예: items · 비워두면 전체 응답"')}${fields}
      <label><span>예시 응답 (JSON, 선택)</span><textarea name="api-example" rows="4" maxlength="20000">${esc(example)}</textarea></label></details>`;
  }
  function developmentHelp(){
    let link='';
    try{
      const url=new URL(current().development_url);
      if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password)link=` <a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">EES Web 열기</a>`;
    }catch{}
    return `<p role="note">EES Web 담당자에게 필요한 기능 개발을 요청한 뒤, 공개된 API 주소를 등록하세요.${link}</p>`;
  }
  function editorHTML(){
    const edit=screen==='edit';
    const actions=btn('취소','cancel')+btn(edit?'저장':fromJob?'등록하고 선택':'등록','save','primary',edit&&!dirty()?'disabled':'');
    const sf=select('service_id','서비스',serviceChoices(),draft.service_id);
    const nf=field('name','API 이름',draft.name,'required maxlength="160" placeholder="예: 설비 알람 조회"');
    return `${back(edit?'API 상세':'등록 취소')}<div class="ew-api-head"><h2 tabindex="-1">${edit?'API 명세 편집':'API 명세 등록'}</h2>${edit?`<div>${actions}</div>`:''}</div>
      ${edit?'':`<div class="ew-api-tabs">${btn('API 주소 직접 등록','direct','active')}${btn('서비스 명세 URL','import','link')}</div>`}
      <div class="ew-api-request">${select('method','요청 방식',pairs(methods),draft.method)}${field('url','API 주소',draft.url,'required spellcheck="false" placeholder="https://ems.example/api/equipment/{equipmentId}/alarms"')}</div>
      <div class="ew-api-pair">${edit?sf+nf:nf+sf}</div>${draft.service_id==='__new__'?field('service_name','새 서비스 이름',serviceName,'maxlength="80" placeholder="예: 사내 백업"'):''}
      ${field('purpose','용도',draft.purpose,'required maxlength="1000" placeholder="예: 설비에서 발생한 알람을 조회합니다."')}
      ${edit?'':btn('API 주소가 없나요?','missing','link')}${missing?developmentHelp():''}
      ${mappingHTML()}${edit?'':`<div class="ew-api-foot">${actions}</div>`}`;
  }
  const table=(headers,rows)=>rows.length?`<div class="ew-api-table"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="ew-api-empty">등록된 항목이 없습니다.</p>';
  function detailHTML(){
    const x=api();if(!x)return back('API 명세 목록','list')+'<p role="status">API를 찾을 수 없거나 접근 권한이 변경되었습니다.</p>';
    const used=detailUses||x.uses, source=x.source_url||x.source?.url;
    return `${back('API 명세 목록','list')}<small>${esc(serviceLabel(x.service_id))}</small><div class="ew-api-head"><h2>${esc(x.name)}</h2>${admin()?btn('명세 편집','edit'):''}</div><p>${esc(x.purpose)}</p>
      <div class="ew-api-subhead"><strong>${esc(x.method)}　${esc(x.url)}</strong>${btn('시험 실행','test')}</div>
      ${source?`<p>서비스 명세　${esc(source)} ${admin()?btn('변경 확인','refresh-import','link'):''}</p>`:''}
      <h3>요청</h3>${table(['항목','위치','자료형','필수'],(x.inputs||[]).map(p=>[p.name,p.in,p.type,p.required?'필수':'선택']))}
      <h3>응답</h3><p>결과 위치　${esc(x.result_path||'전체 응답')}</p>${table(['응답 필드','표시 이름'],(x.fields||[]).map(p=>[p.path,p.label]))}
      ${x.example===undefined?'':`<details><summary>응답 예시</summary><pre>${esc(json(x.example))}</pre></details>`}
      <h3>사용 중인 작업</h3>${!used?'<p class="ew-api-empty">사용처를 확인하고 있습니다.</p>':used.length?table(['업무 절차','작업'],used.map(u=>[u.workflow_name||u.workflow_id,u.job_name||u.job_id])):'<p class="ew-api-empty">연결된 작업이 없습니다.</p>'}`;
  }
  function servicesHTML(){
    const editing=serviceEdit;
    return `<div class="ew-api-head"><h2 id="ew-api-modal-title" tabindex="-1">서비스 관리</h2>${editing?'':btn('서비스 추가','service-new')}</div>
      ${editing?`<div class="ew-api-card">${field('service_edit','서비스 이름',editing.name,'maxlength="80" required')}<div class="ew-api-actions">${editing.id&&!all().some(x=>x.service_id===editing.id)?btn(editing.confirm?'삭제 확정':'서비스 삭제','service-delete','link'):''}${btn('취소','service-cancel')}${btn('저장','service-save','primary')}</div></div>`:''}
      ${services().map(s=>`<div class="ew-api-service"><strong>${esc(s.name)}</strong><small>API ${all().filter(x=>x.service_id===s.id).length}개</small>${btn('이름 변경','service-edit','link',`data-id="${esc(s.id)}"`)}</div>`).join('')||'<p class="ew-api-empty">등록된 서비스가 없습니다.</p>'}<div class="ew-api-actions ew-api-service-close">${btn('닫기','list')}</div>`;
  }
  const importable=op=>!op.error&&(fromJob?['new','same','changed'].includes(op.mode)&&op.state!=='withdrawn'&&op.state!=='deprecated':!['blocked','same'].includes(op.mode));
  function importHTML(){
    const m=importing,ops=m.preview?.operations||[];
    const options=ops.map((op,index)=>`<label class="ew-api-choice"><input type="checkbox" name="api-operation-${index}" data-op-index="${index}" ${m.selected.includes(index)?'checked':''} ${importable(op)?'':'disabled'}><span><strong>${esc(op.method)}　${esc(addr(op.url))}　${esc(op.name)}</strong><small>${esc(op.error||({same:'이미 등록됨',removed:'명세에서 제거됨',changed:'변경 있음',new:'새 기능'}[op.mode])||'')}</small></span></label>`).join('');
    return `${back(m.refresh?'API 상세':'등록 취소',m.refresh?'cancel-import':'cancel')}<div class="ew-api-head"><h2>${m.refresh?'명세 변경 확인':'API 명세 등록'}</h2></div>
      ${m.refresh?'':`<div class="ew-api-tabs">${btn('API 주소 직접 등록','direct','link')}${btn('서비스 명세 URL','import','active')}</div>`}
      ${field('import_url','서비스 명세 URL',m.source_url,'type="url" spellcheck="false" placeholder="https://ems.example/openapi.json"')}
      <div class="ew-api-actions">${btn('명세 가져오기','import-url')}</div>
      <details class="ew-api-advanced" ${m.attach?'open':''} data-import-more><summary>파일 또는 텍스트로 가져오기</summary>
      <label><span>명세 파일</span><input type="file" name="api-file" accept=".json,.yaml,.yml"></label>
      <label><span>OpenAPI JSON 또는 YAML</span><textarea name="api-import_text" rows="6">${esc(m.source_text)}</textarea></label>${btn('명세 읽기','import-text')}</details>
      ${m.preview?`<h3>등록할 기능 선택</h3>${options||'<p>가져올 기능이 없습니다.</p>'}${select('import_service','서비스',serviceChoices(),m.service_id)}${m.service_id==='__new__'?field('import_service_name','새 서비스 이름',m.service_name):''}
      <div class="ew-api-foot">${btn('취소','cancel-import')}${btn('선택한 기능 적용','import-confirm','primary',m.selected.length?'':'disabled')}</div>`:''}`;
  }
  function impacted(ops){
    const affected=new Map();
    for(const op of ops){
      const changedPaths=new Set((op.changes||[]).filter(c=>c.kind==='field'&&c.before&&(!c.after||c.before.type!==c.after.type)).map(c=>c.path));
      for(const use of op.uses||[]){
        const key=use.workflow_id+':'+use.kind+':'+(use.version||'')+':'+use.job_id+':'+(op.id||op.key);
        if(!affected.has(key))affected.set(key,{op,use,fields:use.version===op.version?(use.fields||[]).filter(p=>changedPaths.has(p)):[]});
      }
    }
    return [...affected.values()];
  }
  const repairKey=(op,use)=>JSON.stringify([op.id,use.workflow_id]);
  function substitutes(op,path){
    const type=op.changes.find(c=>c.kind==='field'&&c.path===path)?.before?.type;
    return [...(op.fields||[]).filter(f=>!type||f.type===type||type==='number'&&f.type==='integer').map(f=>[f.path,f.label||f.path]),['@manual','결과 표시에서 제외하고 다음 작업에서 직접 입력']];
  }
  function impactHTML(){
    const {operations,values}=impact;
    const uses=impacted(operations);
    return `${back('편집으로 돌아가기','impact-back')}<div class="ew-api-head"><h2 id="ew-api-modal-title" tabindex="-1">명세 변경 영향</h2></div>
      ${operations.map(op=>`<h3>${esc(op.name)}</h3>${table(['변경','항목','차이'],(op.changes||[]).map(c=>[c.kind,c.path,c.change]))}`).join('')}
      <h3>영향받는 작업</h3>${uses.map(({use,op,fields},i)=>`<section class="ew-api-card"><strong>${esc([use.workflow_name||use.workflow_id,use.job_name||use.job_id].join(' › '))}</strong>
        <p>${esc(({draft:'초안',published:'게시 버전',schedule:'예약 버전'}[use.kind])||use.kind)}${use.version?' v'+esc(use.version):''}</p>
        ${(use.dependent_inputs||[]).filter(ref=>fields.includes(ref.field)).map(ref=>`<p>${esc(ref.field)} → ${esc(ref.job_name||ref.job_id)} · ${esc(ref.input)}</p>`).join('')}
        ${fields.map(p=>use.kind==='draft'&&use.editable?select('repair-'+i+'-'+fields.indexOf(p),p+'의 새 결과 필드',[['','결과 필드 선택'],...substitutes(op,p)],values[repairKey(op,use)]?.[p]||'',`data-repair-workflow="${esc(repairKey(op,use))}" data-repair-path="${esc(p)}"`):`<p>${esc(p)}</p>`).join('')}</section>`).join('')||'<p>영향받는 작업이 없습니다.</p>'}
      <div class="ew-api-foot">${btn('돌아가기','impact-back')}${btn('변경 적용','impact-apply','primary')}</div>`;
  }
  function trialHTML(){
    const x=api();if(!x)return detailHTML();
    return `${back('API 상세','detail')}<div class="ew-api-head"><h2>시험 실행</h2></div><p>${esc(x.method)}　${esc(x.url)}</p>
      ${(x.inputs||[]).map((p,i)=>field('trial-'+i,p.label||p.name,trial.values[p.name],`data-trial="${esc(p.name)}" placeholder="${esc(p.type||'string')}"`)).join('')}
      ${btn('시험 실행','test-run','primary')}
      ${trial.result?`<h3>${trial.result.preview?'요청 미리보기':'시험 결과'}</h3><pre>${esc(json(trial.result))}</pre>`:''}`;
  }
  async function loadUses(selected){
    detailUses=null;detailVersion=api()?.version||0;
    const token=generation;
    try{
      const result=await command({action:'api_detail',api_id:selected});
      if(token!==generation||id!==selected||!result)return;
      if(result.ok===false)throw Error(result.error?.message||'사용처를 불러오지 못했습니다.');
      detailUses=result.uses||[];paint();
    }catch(err){if(token===generation){detailUses=[];error=err.message;paint();}}
  }
  function html(){
    const views={list:listHTML,edit:editorHTML,create:editorHTML,detail:detailHTML,services:servicesHTML,import:importHTML,impact:impactHTML,test:trialHTML};
    const message=error?`<p class="ew-api-error" role="alert">${esc(error)}</p>`:status?`<p class="ew-api-status" role="status">${esc(status)}</p>`:'';
    const confirmLeave=`<div class="ew-api-card" role="alert"><h3>저장하지 않은 변경사항</h3><p>이 화면을 떠나면 편집 중인 내용이 사라집니다.</p>${btn('변경 버리고 이동','discard')}${btn('계속 편집','stay','primary')}</div>`;
    const modal=['services','impact'].includes(screen);
    const surface=modal?`<dialog data-api-modal aria-labelledby="ew-api-modal-title">${views[screen]()} ${message}</dialog>`:(leave?confirmLeave:views[screen]())+message;
    return `<section data-api-catalog data-api-screen="${screen}" aria-label="${esc(screenNames[screen])}" ${busy?'aria-busy="true"':''}><fieldset class="ew-api-controls" ${busy?'disabled':''}>${surface}</fieldset></section>`;
  }
  function recordForSave(){
    const source=clone(draft);
    for(const k of ['name','purpose','url'])if(!source[k]?.trim())throw Error(({name:'API 이름',purpose:'용도',url:'API 주소'}[k])+'를 입력하세요.');
    let parsed;try{parsed=new URL(source.url);}catch{throw Error('HTTP(S) API 주소를 확인하세요.');}
    if(!['http:','https:'].includes(parsed.protocol)||parsed.username||parsed.password||parsed.hash)throw Error('계정 정보와 # 표시가 없는 HTTP(S) API 주소를 입력하세요.');
    if(source.service_id==='__new__'&&!serviceName.trim())throw Error('새 서비스 이름을 입력하세요.');
    if(source.service_id==='__new__')source.service_id='';
    const existing=(source.inputs||[]),seen=new Set(existing.map(x=>x.in+'\n'+(x.wire_name||x.name)));
    const add=(name,where)=>{if(!seen.has(where+'\n'+name)){existing.push({name,in:where,type:'string',label:name,required:true});seen.add(where+'\n'+name);}};
    for(const m of decodeURI(parsed.pathname).matchAll(/\{([\w.-]+)\}/g))add(m[1],'path');
    for(const [key,value] of parsed.searchParams)if(/^\{[\w.-]+\}$/.test(value))add(key,'query');
    source.inputs=existing;
    if(example.trim()){try{source.example=JSON.parse(example);}catch{throw Error('예시 응답 JSON을 확인하세요.');}}else source.example=null;
    const allowed=['id','revision','version','name','purpose','service_id','method','url','inputs','result_path','fields','example','state','group_ids','source_url','operation_id'];
    return Object.fromEntries(allowed.filter(k=>Object.hasOwn(source,k)).map(k=>[k,source[k]]));
  }
  async function request(action,body,{write=false}={}){
    const token=generation;
    if(busy)return null;
    const payload={action,...body};
    if(write){
      const key=JSON.stringify(payload);
      if(receiptKey!==key){receiptKey=key;receiptId=newId();}
      payload.request_id=receiptId;
    }
    busy=true;error='';status='';paint();
    try{
      const result=await command(payload);
      if(generation!==token||!result)return null;
      if(result.ok===false)throw Error(result.error?.message||'요청을 완료하지 못했습니다.');
      if(write){receiptKey='';receiptId='';await changed?.();}
      if(generation!==token)return null;
      return result;
    }finally{if(token===generation){busy=false;paint();}}
  }
  function saveBody(record){
    return {api:record,expected_revision:record.revision||0,...(draft.service_id==='__new__'?{service_name:serviceName.trim()}:{})};
  }
  async function save(repairs=[]){
    const record=recordForSave(),payload=saveBody(record);
    if(record.id&&!impact){
      const preview=await request('api_change_preview',payload);if(!preview)return;
      const op=preview.operation;
      if(op?.uses?.length&&op.changes?.length){impact={operations:[op],values:{},from:'edit'};go('impact');return;}
    }
    const result=await request('api_save',{...payload,repairs},{write:true});
    if(!result?.api)return;
    const job=fromJob;fromJob=false;id=result.api.id;draft=null;impact=null;original='';status='API 명세를 저장했습니다.';go('list');
    if(job)await returnToJob(id);
  }
  async function serviceSave(deleting=false){
    const s=serviceEdit;if(!s)return;
    if(deleting&&!s.confirm){s.confirm=true;paint();return;}
    if(!deleting&&!s.name.trim())throw Error('서비스 이름을 입력하세요.');
    const payload=deleting?{service_id:s.id}:{service:{...(s.id?{id:s.id}:{}),name:s.name.trim()}};
    const result=await request(deleting?'api_service_delete':'api_service_save',{...payload,expected_revision:s.revision||0},{write:true});
    if(result){serviceEdit=null;status=deleting?'서비스를 삭제했습니다.':'서비스 이름을 저장했습니다.';paint();}
  }
  async function previewImport(url){
    const m=importing;
    const input=url?{source_url:m.source_url.trim()}:{source_text:m.source_text};
    if(!Object.values(input)[0])throw Error(url?'명세 URL을 입력하세요.':'파일을 선택하거나 명세를 붙여넣으세요.');
    const result=await request('api_import_preview',{...input,service_id:m.service_id==='__new__'?'':m.service_id});
    if(!result)return;
    m.source=input;m.preview=result;m.selected=[];
    if(!m.service_id&&result.service_name){
      const found=services().find(s=>s.name===result.service_name);m.service_id=found?.id||'__new__';m.service_name=result.service_name;
    }
    const enabled=result.operations.map((op,i)=>importable(op)?i:-1).filter(i=>i>=0);
    if(enabled.length===1)m.selected=enabled;
    paint();
  }
  async function applyImport(repairs=[]){
    const m=importing;
    if(!m?.preview||!m.selected.length)throw Error('등록할 기능을 선택하세요.');
    if(fromJob&&m.selected.length!==1)throw Error('작업에서 사용할 기능 하나를 선택하세요.');
    const ops=m.selected.map(i=>m.preview.operations[i]);
    if(!impact&&ops.some(op=>op.uses?.length&&op.changes?.length)){impact={operations:ops,values:{},from:'import'};go('impact');return;}
    const result=await request('api_import_apply',{...m.source,document_hash:m.preview.document_hash,service_id:m.service_id==='__new__'?'':m.service_id,...(m.service_id==='__new__'?{service_name:m.service_name}:{}),selections:ops.map(op=>({key:op.key,expected_revision:op.expected_revision||0})),repairs},{write:true});
    if(!result)return;
    const job=fromJob;fromJob=false;draft=null;impact=null;importing=null;status='선택한 명세를 적용했습니다.';go('list');
    if(job)await returnToJob(result.apis?.[0]?.id||null);
  }
  function repairs(){
    const result=new Map();
    for(const {op,use,fields} of impacted(impact.operations)){
      const key=repairKey(op,use);
      if(use.kind!=='draft'||!use.editable)continue;
      for(const path of fields){
        const dest=impact.values[key]?.[path];
        if(!dest)throw Error('변경된 결과 필드의 연결을 선택하세요.');
        if(!result.has(key))result.set(key,{api_id:op.id,workflow_id:use.workflow_id,expected_revision:use.revision,fields:{}});
        result.get(key).fields[path]=dest;
      }
    }
    return [...result.values()];
  }
  async function testRun(){
    const x=api(),args={};
    for(const p of x.inputs||[]){
      const raw=trial.values[p.name];
      if(raw===undefined||raw===''){if(p.required)throw Error((p.label||p.name)+' 값을 입력하세요.');continue;}
      try{args[p.name]=!p.type||p.type==='string'?raw:JSON.parse(raw);}catch{throw Error((p.label||p.name)+' 자료형을 확인하세요.');}
    }
    const result=await request('api_test',{api_id:x.id,version:x.version,arguments:args,request_id:newId()});
    if(result){trial.result=result.result||result;paint();}
  }
  function importStart(refresh=false){
    if(!importing||refresh){
      const x=refresh?api():null;
      importing={service_id:x?.service_id||draft?.service_id||'',service_name:serviceName,refresh,source_url:x?.source_url||x?.source?.url||'',source_text:'',selected:[],preview:null,attach:false};
    }
    go('import','[name=api-import_url]');
  }
  async function act(action,target){
    if(busy)return;
    const data=target.dataset;
    if(!['open','list','detail','legacy','test','test-run'].includes(action)&&!admin())throw Error('도구를 편집할 권한이 없습니다.');
    error='';status='';
    switch(action){
      case 'create':start();break;
      case 'open':id=data.id;detailUses=null;go('detail');await loadUses(id);break;
      case 'list':{const wasService=screen==='services';serviceEdit=null;go('list',wasService?'[data-api-action=services]':null);break;}
      case 'detail':trial=null;go('detail');break;
      case 'edit':if(api())start(api());break;
      case 'cancel':await exitEditor();break;
      case 'discard':await exitEditor(true);break;
      case 'stay':leave=false;paint();break;
      case 'save':await save();break;
      case 'missing':missing=!missing;paint();break;
      case 'add-input':draft.inputs.push({name:'',in:'query',type:'string',required:true,label:''});advanced=true;paint();break;
      case 'add-field':draft.fields.push({path:'',type:'string',label:''});advanced=true;paint();break;
      case 'remove-row':if(['inputs','fields'].includes(data.list))draft[data.list].splice(Number(data.index),1);advanced=true;paint();break;
      case 'services':serviceEdit=null;go('services','#ew-api-modal-title');break;
      case 'service-new':serviceEdit={name:''};paint();focus?.('[name=api-service_edit]');break;
      case 'service-edit':{const s=services().find(x=>x.id===data.id);if(s)serviceEdit=clone(s);paint();focus?.('[name=api-service_edit]');break;}
      case 'service-cancel':serviceEdit=null;paint();break;
      case 'service-save':await serviceSave();break;
      case 'service-delete':await serviceSave(true);break;
      case 'direct':if(!draft)start();else go('create');break;
      case 'import':importStart();break;
      case 'refresh-import':importStart(true);break;
      case 'cancel-import':if(importing.refresh){importing=null;go('detail');}else if(draft)go('create');else go('list');break;
      case 'import-url':await previewImport(true);break;
      case 'import-text':await previewImport(false);break;
      case 'import-confirm':await applyImport();break;
      case 'impact-back':{const origin=impact.from;impact=null;go(origin);break;}
      case 'impact-apply':{const fixed=repairs();if(impact.from==='import')await applyImport(fixed);else await save(fixed);break;}
      case 'test':trial={values:{},result:null};go('test');break;
      case 'test-run':await testRun();break;
      case 'legacy':legacy=true;paint();announce();break;
    }
  }
  async function fileRead(target){
    const file=target.files?.[0],token=generation,m=importing;if(!file||!m)return;
    if(file.size>2000000)throw Error('2 MB 이내의 명세 파일을 사용하세요.');
    const contents=await file.text();if(token!==generation||m!==importing)return;
    m.source_text=contents;m.preview=null;m.selected=[];m.attach=true;paint();
  }
  function input(target){
    const data=target.dataset||{},v=target.value,name=target.name?.replace(/^api-/,'');
    if(name==='search'){query=v;paint();return;}
    if(data.trial!==undefined&&trial){trial.values[data.trial]=v;return;}
    if(!admin())return;
    if(data.map){const row=draft?.[data.map]?.[Number(data.index)];if(row){row[data.key]=data.key==='required'?v==='true':v;if(data.key==='in'&&v==='path')row.required=true;announce();}return;}
    if(data.repairWorkflow&&impact){(impact.values[data.repairWorkflow]||={})[data.repairPath]=v;paint();return;}
    if(data.opIndex!==undefined&&importing){const i=Number(data.opIndex);importing.selected=importing.selected.filter(x=>x!==i);if(target.checked)importing.selected.push(i);paint();return;}
    if(name==='service_edit'&&serviceEdit){serviceEdit.name=v;return;}
    if(name==='import_url'||name==='import_text'){
      importing[name==='import_url'?'source_url':'source_text']=v;
      if(importing.preview){importing.preview=null;importing.selected=[];paint();}return;
    }
    if(name==='import_service'){importing.service_id=v;paint();return;}
    if(name==='import_service_name'){importing.service_name=v;return;}
    if(draft){
      if(name==='service_name')serviceName=v;
      else if(name==='example')example=v;
      else if(['url','name','method','purpose','service_id','result_path'].includes(name))draft[name]=v;
      if(name==='service_id')paint();
      const root=target.closest?.('[data-api-catalog]');
      const saveButton=root?.querySelector?.('[data-api-action=save]');if(saveButton&&screen==='edit')saveButton.disabled=!dirty();
      if(['name','url','method','purpose','service_id','service_name'].includes(name))announce();
    }
  }
  function handle(event){
    const target=event.target;
    if(!target.closest?.('[data-api-catalog]'))return null;
    const buttons=target.closest?.('[data-api-action]');
    const report=(err,token)=>{if(generation===token){error=err.message||'요청을 완료하지 못했습니다.';paint();}};
    const token=generation;
    if(event.type==='keydown'&&event.key==='Escape'&&!busy&&['services','impact'].includes(screen)){
      const action=screen==='services'?'list':'impact-back';act(action,target).catch(err=>report(err,token));return {handled:true,preventDefault:true};
    }
    if(event.type==='click'&&target.matches?.('dialog[data-api-modal]')){
      const box=target.getBoundingClientRect();
      if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom){
        act(screen==='services'?'list':'impact-back',target).catch(err=>report(err,token));return {handled:true,preventDefault:true};
      }
    }
    if(event.type==='click'&&buttons){act(buttons.dataset.apiAction,buttons).catch(err=>report(err,token));return {handled:true,preventDefault:true};}
    if(event.type==='toggle'){
      if(target.hasAttribute?.('data-api-advanced'))advanced=target.open;
      if(target.hasAttribute?.('data-import-more')&&importing)importing.attach=target.open;
      if(target.hasAttribute?.('data-group')){if(target.open)filterGroups.delete(target.dataset.group);else filterGroups.add(target.dataset.group);}
    }else if(event.type==='input'||event.type==='change'){
      if(target.name==='api-file'){if(event.type==='change')fileRead(target).catch(err=>report(err,token));}
      else if(!busy)input(target);
    }
    return {handled:true,preventDefault:false};
  }
  function reconcile(before,after){
    if(detailVersion&&after?.apis?.find(x=>x.id===id)?.version!==detailVersion){
      detailVersion=0;detailUses=null;
      const selected=id;queueMicrotask(()=>{if(id===selected&&screen==='detail'&&api())loadUses(selected);});
    }
    // Loading a different workspace temporarily omits operations before its authenticated read.
    // The designer resets the whole controller on identity changes and read authorization failures.
    if(!after)return;
    if(!after.can_manage&&(before?.can_manage||draft||importing||impact||serviceEdit||screen==='services')){reset();return;}
    if(id&&!after.apis?.some(x=>x.id===id)&&!['create','list'].includes(screen)){reset();}
  }
  function suggest(values,expected){
    if(!admin()||busy||!draft||!['create','edit'].includes(screen)||!expected||JSON.stringify(context())!==JSON.stringify(expected))return false;
    let applied=false;
    for(const [field,limit] of [['name',160],['purpose',1000]]){
      if(typeof values?.[field]==='string'&&values[field].trim()&&values[field].length<=limit){draft[field]=values[field].trim();applied=true;}
    }
    if(applied){paint();announce();}
    return applied;
  }
  function afterPaint(host){
    const dialog=host?.querySelector?.('dialog[data-api-modal]');
    if(dialog&&!dialog.open&&typeof dialog.showModal==='function')dialog.showModal();
  }
  return {html,handle,start,reset,reconcile,afterPaint,context,suggest,openLegacy:()=>{legacy=true;},isLegacy:()=>legacy,pending:()=>busy,signature:()=>[screen,id,serviceEdit?.id||''],showList:()=>{legacy=false;go('list');}};
}
