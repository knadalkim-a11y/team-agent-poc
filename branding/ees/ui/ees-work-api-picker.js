/* A selection is applied to the workflow draft only when the author confirms. */
function createWorkApiPicker(){
  const esc = value => workUI.esc(String(value ?? ''));
  const fieldTypes = {string:'text', integer:'number', number:'number', boolean:'boolean', array:'list', object:'json_object'};
  const clone = value => JSON.parse(JSON.stringify(value));
  const writable = op => !['GET', 'HEAD', 'OPTIONS'].includes(op.method);
  function address(raw) {
    try { const url = new URL(raw); return url.pathname.replace(/%7B/gi,'{').replace(/%7D/gi,'}') + url.search; }
    catch { return raw || ''; }
  }
  function serviceName(catalog, operation) {
    return catalog.services?.find(service => service.id === operation.service_id)?.name || '';
  }
  function sourceChoices(jobs, node, catalog, targetField) {
    const candidates = [];
    for (const previous of jobs) {
      if (previous.id === node.id) break;
      const binding = previous.api_binding;
      if (!binding) continue;
      const op = catalog.apis.find(op => op.id === binding.operation_id && op.version === binding.version);
      for (const field of op?.fields || []) {
        if (!binding.outputs.includes(field.path)) continue;
        if (!(targetField.type === 'array' || targetField.type === field.type || targetField.type === 'number' && field.type === 'integer')) continue;
        candidates.push({value:JSON.stringify([previous.id, field.path]), label:previous.name+' · '+(field.label || field.path)});
      }
    }
    return candidates;
  }
  function selectable(operation) { return operation.can_use !== false && operation.state === 'active'; }
  function summary(node, catalog, jobs, compact=false) {
    const b = node.api_binding;
    if (!b) return '';
    const op = catalog.apis.find(api => api.id === b.operation_id);
    if (!op) return '<div data-api-job-binding><small>연결한 API의 현재 사용 권한을 확인해 주세요.</small></div>';
    const entries=Object.entries(b.inputs);
    const compactRows=compact&&entries.some(([,ref])=>ref.result)?entries.filter(([,ref])=>ref.result):entries;
    const rows = compactRows.map(([name, ref]) => {
      const field = op.inputs.find(f => f.name === name);
      const label = field?.label || name;
      if (ref.result) {
        const upstream=jobs.find(j=>j.id===ref.result.job_id);
        const labelForSource=catalog.apis.find(api=>api.id===upstream?.api_binding?.operation_id)?.fields.find(f=>f.path===ref.result.field)?.label||ref.result.field;
        return label+' ← '+(upstream?.name || '앞 작업')+(compact?'에서 선택한 결과':' · '+labelForSource);
      }
      if ('constant' in ref) return label+' '+(typeof ref.constant==='string'?ref.constant:JSON.stringify(ref.constant));
      if ('context' in ref) return label+' · 현재 업무의 '+(ref.context==='system_id'?'시스템':'공장');
      return label+' · 실행 시 입력';
    });
    const outputs = b.outputs.map(path=>op.fields.find(f=>f.path===path)?.label || path);
    return `<div data-api-job-binding class="ew-api-job-binding">${rows.map(r=>'<div>'+esc(r)+'</div>').join('')}${outputs.length?'<small>받는 결과 · '+esc(outputs.join(', '))+'</small>':''}<small>${esc(serviceName(catalog,op))}　${esc(op.method)}　${esc(address(op.url))}</small></div>`;
  }
  function defaultDraft(op, node) {
    const b = node.api_binding;
    const same = b?.operation_id === op.id && b.version === op.version;
    const inputs = same ? clone(b.inputs) : Object.fromEntries(op.inputs.filter(f=>f.required || f.default!==undefined).map(f=>[f.name, f.default!==undefined ? {constant:f.default} : fieldTypes[f.type] ? {input:f.name} : {constant:{}}]));
    return {inputs, outputs:same ? [...b.outputs] : op.fields.map(f=>f.path), raw:{}};
  }
  function constant(value, type) {
    if (type==='string') return value;
    if (value.trim()==='') throw Error('값을 입력해 주세요.');
    let parsed;
    try { parsed = JSON.parse(value); } catch { throw Error('입력 형식에 맞는 값을 입력해 주세요.'); }
    const valid = type==='object' ? parsed!==null && typeof parsed==='object' && !Array.isArray(parsed) : type==='array'?Array.isArray(parsed) : type==='integer'?Number.isSafeInteger(parsed):type==='number'?typeof parsed==='number' && Number.isFinite(parsed):type==='boolean'?typeof parsed==='boolean':true;
    if (!valid) throw Error('입력 형식에 맞는 값을 입력해 주세요.');
    return parsed;
  }
  const option = (value, text, current) => '<option value="'+esc(value)+'"'+(value===current?' selected':'')+'>'+esc(text)+'</option>';
  function mappingFields(op, draft, node, jobs, catalog) {
    return op.inputs.map(field => {
      const src = draft.inputs[field.name] || {};
      const sources = sourceChoices(jobs,node,catalog,field);
      const method = 'constant' in src?'constant':src.input?'input':src.context?src.context:src.result?'result':'omit';
      const modes = [...(!field.required?[['omit','전달하지 않음']]:[]), ['constant','고정값'], ...(fieldTypes[field.type]?[['input','실행 시 입력']]:[]),
        ...(field.type==='string'?[['system_id','현재 업무의 시스템'],['factory_id','현재 업무의 공장']]:[]),
        ...(sources.length || src.result?[['result','앞 작업에서 선택한 결과']]:[])];
      const raw = draft.raw[field.name] ?? (typeof src.constant==='string'?src.constant:JSON.stringify(src.constant)??'');
      const selected = src.result ? JSON.stringify([src.result.job_id,src.result.field]) : '';
      const choice = method==='result' ? `<select data-api-result="${esc(field.name)}" aria-label="${esc(field.label||field.name)} 결과 필드"><option value="">결과 선택</option>${sources.map(s=>option(s.value,s.label,selected)).join('')}</select>` : '';
      return `<div class="ew-api-map-row"><label>${esc(field.label || field.name)}${field.required?' <small>필수</small>':''}<select data-api-source="${esc(field.name)}">${modes.map(pair=>option(...pair,method)).join('')}</select></label>${method==='constant'?`<label>값<input data-api-value="${esc(field.name)}" value="${esc(raw)}" placeholder="${esc(field.type==='object'?'{}':field.type==='array'?'[]':'')}"></label>`:choice}</div>`;
    }).join('');
  }
  function buildNode(node, op, draft, jobs) {
    const inputs = {};
    const oldInputs = node.inputs || [];
    const local = oldInputs.filter(f=>!f.source?.api_operation_id && !f.source?.shared_tool_id);
    const existing = new Map(oldInputs.map(f=>[f.id,f]));
    const manualDeps=new Set((node.deps||[]).filter(id=>!(node.api_generated_deps||[]).includes(id)));
    const publishedDeps = new Set(manualDeps);
    const ids = new Set(Object.keys(draft.inputs));
    for (const field of op.inputs) {
      if (field.required && !ids.has(field.name)) throw Error((field.label||field.name)+' 입력을 지정해 주세요.');
      const ref = draft.inputs[field.name];
      if (!ref) continue;
      if ('constant' in ref) inputs[field.name] = {constant:constant(draft.raw[field.name] ?? (typeof ref.constant==='string'?ref.constant:JSON.stringify(ref.constant)),field.type)};
      else if ('input' in ref) {
        const retain = node.api_binding?.operation_id===op.id && node.api_binding.inputs[field.name]?.input;
        const baseId='api_'+node.id.slice(0,100)+'_'+op.inputs.indexOf(field);
        let id=retain || baseId, suffix=0;
        if(!retain)while(local.some(input=>input.id===id))id=baseId+'_'+(++suffix);
        let input = local.find(f=>f.id===id);
        if (!input) {
          const old = retain && existing.get(retain);
          input = old ? clone(old) : {id, name:field.label||field.name, type:fieldTypes[field.type], scope:'run',required:!!field.required,source:{api_operation_id:op.id}};
          local.push(input);
        }
        inputs[field.name] = {input:id};
      } else if (ref.context) inputs[field.name] = {context:ref.context};
      else if (ref.result?.field && jobs.some(n=>n.id===ref.result.job_id)) {
        inputs[field.name] = clone(ref);
        publishedDeps.add(ref.result.job_id);
      } else throw Error((field.label||field.name)+'에 연결할 앞 작업의 결과를 선택해 주세요.');
    }
    const next = clone(node);
    for (const key of ['shared_tool_id','shared_tool_generated','tool_contract_id','tool_contract_revision','tool_reference','argument_bindings','execution','read_retry']) delete next[key];
    next.inputs = local;
    next.mode = 'tool';
    next.deps = [...publishedDeps];
    const generated=[...publishedDeps].filter(id=>!manualDeps.has(id));
    if(generated.length)next.api_generated_deps=generated;else delete next.api_generated_deps;
    next.result_block = writable(op) ? 'change_request' : (op.result_path || Array.isArray(op.example) ? 'list_confirm' : 'human_confirm');
    next.human_confirmation = true;
    next.api_binding = {operation_id:op.id,version:op.version,inputs,outputs:[...draft.outputs]};
    return next;
  }
  async function open({node,catalog,jobs,confirm,initial={},restoreFocus}) {
    let query = initial.query || '', selected = initial.id || node.api_binding?.operation_id || '';
    const drafts = initial.drafts || new Map();
    const choices = catalog.apis.filter(selectable);
    if (!selected && choices.length) selected = choices[0].id;
    const getOp = ()=>choices.find(x=>x.id===selected);
    const getDraft = ()=>{const op=getOp();if(!op)return null;if(!drafts.has(op.id))drafts.set(op.id,defaultDraft(op,node));return drafts.get(op.id);};
    const label = catalog.can_manage ? '<button type="button" class="ew-author-link" data-api-register>API 명세 등록</button>' : '';
    const pending = confirm({title:'작업에 도구 연결', confirmLabel:'연결 저장',restoreFocus,
      html:`<div class="ew-workflow-tool-layout ew-api-picker"><div><label>API 찾기<input type="search" data-api-search placeholder="이름, 용도, 서비스 또는 주소" value="${esc(query)}"></label><div data-api-choices></div>${label}</div><section data-api-config></section></div><p role="alert" data-api-picker-error></p>`});
    const dialog = workUI.$('#ees-work-dialog');
    dialog?.classList?.add('ew-workflow-tool-dialog');
    const drawList=()=>{
      const root=dialog.querySelector('[data-api-choices]');
      const term=query.trim().toLocaleLowerCase();
      root.innerHTML=choices.filter(op=>[op.name,op.purpose,op.method,op.url,serviceName(catalog,op)].join(' ').toLocaleLowerCase().includes(term)).map(op=>`<button type="button" data-api-candidate="${esc(op.id)}" aria-pressed="${op.id===selected}"><strong>${esc(op.name)}</strong><small>${esc(op.purpose)}</small><small>${esc(serviceName(catalog,op))} · ${esc(op.method)} ${esc(address(op.url))}</small></button>`).join('');
      if (!root.children.length) {
        const url=catalog.development_url;
        const request=url&&/^https?:\/\//i.test(url)?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">EES Web에 개발 요청</a>':'EES Web에서 서비스 개발을 요청한 뒤 공개된 API를 등록할 수 있습니다.';
        root.innerHTML='<p>사용할 API를 찾을 수 없습니다.</p>'+request;
      }
    };
    const draw=()=>{
      const op=getOp(),draft=getDraft();
      dialog.querySelector('[data-dialog-confirm]').disabled=!op;
      dialog.querySelector('[data-api-config]').innerHTML=!op?'<p>이 작업에서 사용할 API를 선택하세요.</p>':`<h3>${esc(op.name)}</h3><p>${esc(op.purpose)}</p><small>${esc(serviceName(catalog,op))} · ${esc(op.method)} ${esc(address(op.url))}</small><h4>이 작업에서 사용할 입력</h4>${mappingFields(op,draft,node,jobs,catalog)||'<p>필요한 입력이 없습니다.</p>'}<h4>받는 결과</h4>${op.fields.map(f=>`<label><input type="checkbox" data-api-output="${esc(f.path)}" ${draft.outputs.includes(f.path)?'checked':''}> ${esc(f.label||f.path)}</label>`).join('') || '<p>응답 본문 없음</p>'}<details><summary>API 상세 보기</summary><p>${esc(op.method)} ${esc(op.url)}</p>${op.example!==null&&op.example!==undefined?'<pre>'+esc(JSON.stringify(op.example,null,2))+'</pre>':''}</details>`;
    };
    let next=null, registering=false;
    const events=(event)=>{
      const target=event.target, data=target.dataset || {};
      if (event.type==='input') {
        if (data.apiSearch!==undefined){query=target.value;drawList();}
        if (data.apiValue!==undefined)getDraft().raw[data.apiValue]=target.value;
        return;
      }
      if (event.type==='change') {
        const draft=getDraft();if (!draft)return;
        if(data.apiOutput!==undefined){draft.outputs=target.checked?[...new Set([...draft.outputs,data.apiOutput])]:draft.outputs.filter(k=>k!==data.apiOutput);return;}
        if(data.apiResult!==undefined && target.value){const [job_id,field]=JSON.parse(target.value);draft.inputs[data.apiResult]={result:{job_id,field,confirmed:true}};return;}
        if(data.apiSource!==undefined){const name=data.apiSource; const mode=target.value;
          if(mode==='omit')delete draft.inputs[name];
          else if(mode==='constant')draft.inputs[name]={constant:''};
          else if(mode==='input')draft.inputs[name]={input:name};
          else if(mode==='result')draft.inputs[name]={result:{job_id:'',field:'',confirmed:true}};
          else draft.inputs[name]={context:mode};
          draw();
        }
        return;
      }
      if(target.closest?.('[data-api-register]')){registering=true;dialog.eesClose();return;}
      const candidate=target.closest?.('[data-api-candidate]');
      if(candidate){selected=candidate.dataset.apiCandidate;dialog.querySelector('[data-api-picker-error]').textContent='';drawList();draw();return;}
      if(target.closest?.('[data-dialog-confirm]')){try{next=buildNode(node,getOp(),getDraft(),jobs);}catch(e){event.preventDefault();event.stopImmediatePropagation();dialog.querySelector('[data-api-picker-error]').textContent=e.message;}}
    };
    const handlers=['input','change','click'];
    if (!dialog) return null;
    handlers.forEach(type=>dialog.addEventListener(type,events,type==='click'));drawList();draw();
    try{const accepted=await pending;return registering?{register:{drafts,query,id:selected}}:accepted&&next?{node:next}:null;}
    finally{handlers.forEach(type=>dialog.removeEventListener(type,events,type==='click'));}
  }
  return {summary,open,buildNode};
}
const workApiPicker=createWorkApiPicker();
